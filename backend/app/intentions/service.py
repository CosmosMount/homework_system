from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from urllib.parse import quote
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, context_effective_role, context_is_admin
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.core.markdown import render_markdown
from app.core.security import random_urlsafe_token, sha256_hexdigest
from app.intentions.models import (
    IntentionOption,
    IntentionResponse,
    IntentionResponseOption,
    IntentionSurvey,
)
from app.intentions.repository import IntentionRepository, SurveyListRecord
from app.intentions.schemas import (
    AdminIntentionSurvey,
    AdminIntentionSurveyPage,
    IntentionOptionResponse,
    IntentionQrResponse,
    IntentionResponseRequest,
    IntentionResponseResponse,
    IntentionStatsOption,
    IntentionStatsResponse,
    IntentionStatus,
    IntentionSurveyCreateRequest,
    IntentionSurveyDetail,
    IntentionSurveyPage,
    IntentionSurveyPatchRequest,
    IntentionSurveySummary,
)


@dataclass(frozen=True, slots=True)
class IntentionAuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


class IntentionService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._repo = IntentionRepository(session)
        self._audit = AuditRepository(session)

    @staticmethod
    def _not_found() -> ApplicationError:
        return ApplicationError(
            status_code=404, code="RESOURCE_NOT_FOUND", message="调查不存在或当前不可见。"
        )

    @staticmethod
    def _require_student(context: AuthenticatedContext) -> None:
        if context_effective_role(context) != "student":
            raise ApplicationError(
                status_code=403, code="FORBIDDEN", message="管理员不能通过学生意向接口填写。"
            )

    @staticmethod
    def _require_admin(context: AuthenticatedContext) -> None:
        if not context_is_admin(context):
            raise ApplicationError(
                status_code=403, code="FORBIDDEN", message="仅管理员可以管理意向调查。"
            )

    @staticmethod
    def _conflict(code: str, message: str) -> ApplicationError:
        return ApplicationError(status_code=409, code=code, message=message)

    @staticmethod
    def _is_open(survey: IntentionSurvey, now: datetime) -> bool:
        return (
            survey.status == "open"
            and (survey.starts_at is None or survey.starts_at <= now)
            and (survey.ends_at is None or now < survey.ends_at)
        )

    def _add_audit(
        self,
        context: IntentionAuditContext,
        *,
        action: str,
        target_id: UUID,
        now: datetime,
        change_summary: dict[str, object] | None = None,
    ) -> None:
        self._audit.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=context.actor.user.id,
                action=action,
                target_type="intention_survey",
                target_id=target_id,
                request_id=context.request_id,
                ip_prefix=context.ip_prefix,
                result="success",
                change_summary=change_summary or {},
                created_at=now,
            )
        )

    def _summary(
        self, record: SurveyListRecord, *, student: bool
    ) -> IntentionSurveySummary | AdminIntentionSurvey:
        survey = record.survey
        if student:
            return IntentionSurveySummary(
                id=survey.id,
                title=survey.title,
                description_html=survey.description_html,
                status=cast(IntentionStatus, survey.status),
                allow_multiple=survey.allow_multiple,
                starts_at=survey.starts_at,
                ends_at=survey.ends_at,
                option_count=record.option_count,
                has_response=record.has_response,
            )
        return AdminIntentionSurvey(
            id=survey.id,
            title=survey.title,
            description_markdown=survey.description_markdown,
            status=cast(IntentionStatus, survey.status),
            allow_multiple=survey.allow_multiple,
            starts_at=survey.starts_at,
            ends_at=survey.ends_at,
            option_count=record.option_count,
            responded_count=record.responded_count,
            created_at=survey.created_at,
            updated_at=survey.updated_at,
            revision=survey.revision,
        )

    async def list_student(self, *, context: AuthenticatedContext) -> IntentionSurveyPage:
        self._require_student(context)
        now = self._clock()
        records = await self._repo.list_surveys(student_user_id=context.user.id, open_only=True)
        visible = [record for record in records if self._is_open(record.survey, now)]
        return IntentionSurveyPage(
            items=[
                cast(IntentionSurveySummary, self._summary(record, student=True))
                for record in visible
            ],
            total=len(visible),
        )

    async def student_detail(
        self, survey_id: UUID, *, context: AuthenticatedContext, token: str | None
    ) -> IntentionSurveyDetail:
        self._require_student(context)
        survey = await self._repo.get_survey(survey_id)
        if survey is None or not self._is_open(survey, self._clock()):
            raise self._not_found()
        if token is not None and sha256_hexdigest(token) != survey.public_token_hash:
            raise self._not_found()
        options = await self._repo.options(survey_id)
        response = await self._repo.get_response(survey_id, context.user.id)
        response_schema: IntentionResponseResponse | None = None
        if response is not None:
            selected = await self._repo.response_options(response.id)
            response_schema = IntentionResponseResponse(
                selected_option_ids=[item.option_id for item in selected],
                free_text=response.free_text,
                submitted_at=response.submitted_at,
            )
        return IntentionSurveyDetail(
            id=survey.id,
            title=survey.title,
            description_html=survey.description_html,
            status=cast(IntentionStatus, survey.status),
            allow_multiple=survey.allow_multiple,
            starts_at=survey.starts_at,
            ends_at=survey.ends_at,
            option_count=len(options),
            has_response=response is not None,
            options=[
                IntentionOptionResponse(
                    id=item.id, label=item.label, display_order=item.display_order
                )
                for item in options
            ],
            response=response_schema,
            revision=survey.revision,
        )

    async def submit_response(
        self,
        survey_id: UUID,
        payload: IntentionResponseRequest,
        *,
        audit_context: IntentionAuditContext,
    ) -> IntentionResponseResponse:
        self._require_student(audit_context.actor)
        survey = await self._repo.get_survey(survey_id, for_update=True)
        now = self._clock()
        if survey is None or not self._is_open(survey, now):
            await self._session.rollback()
            raise self._conflict("INTENTION_CLOSED", "当前调查已关闭或不在填写时间内。")
        options = await self._repo.options(survey_id)
        option_ids = {item.id for item in options}
        selected = list(payload.selected_option_ids)
        if any(item not in option_ids for item in selected):
            await self._session.rollback()
            raise ApplicationError(
                status_code=400, code="VALIDATION_ERROR", message="包含无效调查选项。"
            )
        if not survey.allow_multiple and len(selected) != 1:
            await self._session.rollback()
            raise ApplicationError(
                status_code=422, code="VALIDATION_ERROR", message="该调查只能选择一个选项。"
            )
        response = await self._repo.get_response(
            survey_id, audit_context.actor.user.id, for_update=True
        )
        if response is None:
            response = IntentionResponse(
                id=uuid7(),
                survey_id=survey_id,
                user_id=audit_context.actor.user.id,
                free_text=payload.free_text.strip()
                if payload.free_text and payload.free_text.strip()
                else None,
                submitted_at=now,
                created_at=now,
                updated_at=now,
                revision=1,
            )
            self._repo.add_response(response)
        else:
            for old in await self._repo.response_options(response.id):
                await self._session.delete(old)
            await self._session.flush()
            response.free_text = (
                payload.free_text.strip()
                if payload.free_text and payload.free_text.strip()
                else None
            )
            response.submitted_at = now
            response.updated_at = now
            response.revision += 1
        for option_id in selected:
            self._repo.add_response_option(
                IntentionResponseOption(response_id=response.id, option_id=option_id)
            )
        self._add_audit(
            audit_context, action="intention.response_submit", target_id=survey_id, now=now
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "INTENTION_RESPONSE_CONFLICT", "回答保存发生并发冲突，请重试。"
            ) from exc
        return IntentionResponseResponse(
            selected_option_ids=selected, free_text=response.free_text, submitted_at=now
        )

    async def list_admin(self, *, context: AuthenticatedContext) -> AdminIntentionSurveyPage:
        self._require_admin(context)
        records = await self._repo.list_surveys()
        items = [
            cast(AdminIntentionSurvey, self._summary(record, student=False)) for record in records
        ]
        return AdminIntentionSurveyPage(items=items, total=len(items))

    async def create(
        self,
        payload: IntentionSurveyCreateRequest,
        *,
        audit_context: IntentionAuditContext,
    ) -> AdminIntentionSurvey:
        self._require_admin(audit_context.actor)
        now = self._clock()
        token = random_urlsafe_token(24)
        survey = IntentionSurvey(
            id=uuid7(),
            title=payload.title.strip(),
            description_markdown=payload.description_markdown,
            description_html=render_markdown(payload.description_markdown),
            status="draft",
            allow_multiple=payload.allow_multiple,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            public_token_hash=sha256_hexdigest(token),
            created_by=audit_context.actor.user.id,
            updated_by=audit_context.actor.user.id,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._repo.add_survey(survey)
        for index, item in enumerate(payload.options):
            self._repo.add_option(
                IntentionOption(
                    id=uuid7(), survey_id=survey.id, label=item.label.strip(), display_order=index
                )
            )
        self._add_audit(audit_context, action="intention.create", target_id=survey.id, now=now)
        await self._session.commit()
        return cast(
            AdminIntentionSurvey,
            self._summary(SurveyListRecord(survey, len(payload.options), 0, False), student=False),
        )

    async def patch(
        self,
        survey_id: UUID,
        payload: IntentionSurveyPatchRequest,
        *,
        audit_context: IntentionAuditContext,
    ) -> AdminIntentionSurvey:
        self._require_admin(audit_context.actor)
        survey = await self._repo.get_survey(survey_id, for_update=True)
        if survey is None:
            await self._session.rollback()
            raise self._not_found()
        if survey.status != "draft":
            await self._session.rollback()
            raise self._conflict("INTENTION_ALREADY_OPEN", "调查开放后不能修改题目结构。")
        if survey.revision != payload.revision:
            await self._session.rollback()
            raise self._conflict("REVISION_CONFLICT", "调查已被其他管理员修改。")
        old_options = await self._repo.options(survey_id)
        for old in old_options:
            await self._session.delete(old)
        await self._session.flush()
        survey.title = payload.title.strip()
        survey.description_markdown = payload.description_markdown
        survey.description_html = render_markdown(payload.description_markdown)
        survey.allow_multiple = payload.allow_multiple
        survey.starts_at = payload.starts_at
        survey.ends_at = payload.ends_at
        survey.updated_by = audit_context.actor.user.id
        survey.updated_at = self._clock()
        survey.revision += 1
        for index, item in enumerate(payload.options):
            self._repo.add_option(
                IntentionOption(
                    id=uuid7(), survey_id=survey_id, label=item.label.strip(), display_order=index
                )
            )
        self._add_audit(
            audit_context, action="intention.update", target_id=survey.id, now=survey.updated_at
        )
        await self._session.commit()
        return cast(
            AdminIntentionSurvey,
            self._summary(
                SurveyListRecord(
                    survey, len(payload.options), await self._repo.responded_count(survey_id), False
                ),
                student=False,
            ),
        )

    async def transition(
        self,
        survey_id: UUID,
        target: Literal["open", "closed", "archived"],
        *,
        audit_context: IntentionAuditContext,
    ) -> AdminIntentionSurvey:
        self._require_admin(audit_context.actor)
        survey = await self._repo.get_survey(survey_id, for_update=True)
        if survey is None:
            await self._session.rollback()
            raise self._not_found()
        allowed = {"draft": {"open"}, "open": {"closed"}, "closed": {"archived"}}
        if target not in allowed.get(survey.status, set()):
            await self._session.rollback()
            raise self._conflict("STATE_CONFLICT", "调查状态不能逆序变更。")
        survey.status = target
        survey.updated_by = audit_context.actor.user.id
        survey.updated_at = self._clock()
        survey.revision += 1
        self._add_audit(
            audit_context, action="intention." + target, target_id=survey.id, now=survey.updated_at
        )
        await self._session.commit()
        records = await self._repo.list_surveys()
        record = next(item for item in records if item.survey.id == survey_id)
        return cast(AdminIntentionSurvey, self._summary(record, student=False))

    async def stats(
        self, survey_id: UUID, *, context: AuthenticatedContext
    ) -> IntentionStatsResponse:
        self._require_admin(context)
        survey = await self._repo.get_survey(survey_id)
        if survey is None:
            raise self._not_found()
        responded = await self._repo.responded_count(survey_id)
        total_students = await self._repo.active_student_count()
        options = await self._repo.option_counts(survey_id)
        return IntentionStatsResponse(
            survey_id=survey_id,
            total_active_students=total_students,
            responded_count=responded,
            response_rate=round((responded / total_students * 100) if total_students else 0.0, 2),
            options=[
                IntentionStatsOption(
                    option_id=item.option.id,
                    label=item.option.label,
                    response_count=item.response_count,
                    percentage=round(
                        (item.response_count / responded * 100) if responded else 0.0, 2
                    ),
                )
                for item in options
            ],
        )

    async def qr_token(
        self,
        survey_id: UUID,
        *,
        audit_context: IntentionAuditContext,
    ) -> IntentionQrResponse:
        self._require_admin(audit_context.actor)
        survey = await self._repo.get_survey(survey_id, for_update=True)
        if survey is None or survey.status == "archived":
            await self._session.rollback()
            raise self._not_found()
        if survey.status == "closed":
            await self._session.rollback()
            raise self._conflict("INTENTION_CLOSED", "调查已关闭，不能再生成填写二维码。")
        token = random_urlsafe_token(24)
        survey.public_token_hash = sha256_hexdigest(token)
        survey.updated_by = audit_context.actor.user.id
        survey.updated_at = self._clock()
        survey.revision += 1
        self._add_audit(
            audit_context,
            action="intention.qr_token_rotate",
            target_id=survey.id,
            now=survey.updated_at,
        )
        await self._session.commit()
        fill_url = (
            str(self._settings.app_base_url).rstrip("/")
            + "/intentions/"
            + str(survey.id)
            + "?token="
            + quote(token, safe="")
        )
        return IntentionQrResponse(
            survey_id=survey.id, token=token, fill_url=fill_url, generated_at=survey.updated_at
        )
