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
    IntentionQuestion,
    IntentionResponse,
    IntentionResponseOption,
    IntentionSurvey,
)
from app.intentions.repository import (
    FirstChoiceDirectionRecord,
    IntentionRepository,
    SurveyListRecord,
    SurveyOptionCount,
)
from app.intentions.schemas import (
    AdminIntentionSurvey,
    AdminIntentionSurveyDetail,
    AdminIntentionSurveyPage,
    IntentionAnswerResponse,
    IntentionAudienceResponse,
    IntentionDirectionAssignmentRequest,
    IntentionDirectionAssignmentResponse,
    IntentionEmailNotificationRequest,
    IntentionEmailNotificationResponse,
    IntentionOptionResponse,
    IntentionQrResponse,
    IntentionQuestionInput,
    IntentionQuestionResponse,
    IntentionResponseRequest,
    IntentionResponseResponse,
    IntentionRosterAnswer,
    IntentionRosterItem,
    IntentionRosterResponse,
    IntentionStatsOption,
    IntentionStatsQuestion,
    IntentionStatsResponse,
    IntentionStatus,
    IntentionSurveyCreateRequest,
    IntentionSurveyDetail,
    IntentionSurveyPage,
    IntentionSurveyPatchRequest,
    IntentionSurveySummary,
)
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.users.models import User

DIRECTION_ASSIGNMENT_SURVEY_TITLE = "意向选择"


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
        self._outbox = OutboxRepository(session)

    @staticmethod
    def _not_found() -> ApplicationError:
        return ApplicationError(
            status_code=404, code="RESOURCE_NOT_FOUND", message="问卷不存在或当前不可见。"
        )

    @staticmethod
    def _require_student(context: AuthenticatedContext) -> None:
        if context_effective_role(context) != "student":
            raise ApplicationError(
                status_code=403, code="FORBIDDEN", message="管理员不能通过学生问卷接口填写。"
            )

    @staticmethod
    def _require_admin(context: AuthenticatedContext) -> None:
        if not context_is_admin(context):
            raise ApplicationError(
                status_code=403, code="FORBIDDEN", message="仅管理员可以管理问卷。"
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

    async def _student_is_targeted(
        self, survey: IntentionSurvey, context: AuthenticatedContext
    ) -> bool:
        if survey.all_students:
            return True
        return await self._repo.student_direction_is_targeted(
            survey.id,
            context.user.direction_id,
        )

    async def _validate_audience_direction_ids(self, direction_ids: list[UUID]) -> None:
        if not direction_ids:
            return
        requested = set(direction_ids)
        active = await self._repo.active_directions_by_ids(direction_ids)
        if {direction.id for direction in active} != requested:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="INVALID_INTENTION_AUDIENCE",
                message="问卷受众中包含不存在或已停用的技术组，请刷新后重试。",
            )

    def _add_audit(
        self,
        context: IntentionAuditContext,
        *,
        action: str,
        target_id: UUID,
        now: datetime,
        change_summary: dict[str, object] | None = None,
        target_type: str = "intention_survey",
    ) -> None:
        self._audit.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=context.actor.user.id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                request_id=context.request_id,
                ip_prefix=context.ip_prefix,
                result="success",
                change_summary=change_summary or {},
                created_at=now,
            )
        )

    @staticmethod
    def _question_schemas(
        questions: list[IntentionQuestion], options: list[IntentionOption]
    ) -> list[IntentionQuestionResponse]:
        options_by_question: dict[UUID, list[IntentionOption]] = {}
        for option in options:
            options_by_question.setdefault(option.question_id, []).append(option)
        return [
            IntentionQuestionResponse(
                id=question.id,
                prompt=question.prompt,
                allow_multiple=question.allow_multiple,
                display_order=question.display_order,
                options=[
                    IntentionOptionResponse(
                        id=option.id,
                        label=option.label,
                        display_order=option.display_order,
                    )
                    for option in options_by_question.get(question.id, [])
                ],
            )
            for question in questions
        ]

    @staticmethod
    def _response_schema(
        response: IntentionResponse,
        questions: list[IntentionQuestion],
        options: list[IntentionOption],
        selected_links: list[IntentionResponseOption],
    ) -> IntentionResponseResponse:
        selected_ids = {item.option_id for item in selected_links}
        option_ids_by_question: dict[UUID, list[UUID]] = {}
        for option in options:
            if option.id in selected_ids:
                option_ids_by_question.setdefault(option.question_id, []).append(option.id)
        return IntentionResponseResponse(
            answers=[
                IntentionAnswerResponse(
                    question_id=question.id,
                    selected_option_ids=option_ids_by_question.get(question.id, []),
                )
                for question in questions
            ],
            free_text=response.free_text,
            submitted_at=response.submitted_at,
            submission_count=response.submission_count,
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
                starts_at=survey.starts_at,
                ends_at=survey.ends_at,
                question_count=record.question_count,
                has_response=record.has_response,
                submissions_used=record.submissions_used,
                max_submissions=survey.max_submissions,
            )
        return AdminIntentionSurvey(
            id=survey.id,
            title=survey.title,
            description_markdown=survey.description_markdown,
            status=cast(IntentionStatus, survey.status),
            starts_at=survey.starts_at,
            ends_at=survey.ends_at,
            question_count=record.question_count,
            responded_count=record.responded_count,
            max_submissions=survey.max_submissions,
            audience=IntentionAudienceResponse(
                all_students=survey.all_students,
                direction_ids=list(record.direction_ids),
            ),
            created_at=survey.created_at,
            updated_at=survey.updated_at,
            revision=survey.revision,
        )

    async def list_student(self, *, context: AuthenticatedContext) -> IntentionSurveyPage:
        self._require_student(context)
        now = self._clock()
        records = await self._repo.list_surveys(
            student_user_id=context.user.id,
            student_direction_id=context.user.direction_id,
            open_only=True,
        )
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
        if (
            survey is None
            or not self._is_open(survey, self._clock())
            or not await self._student_is_targeted(survey, context)
        ):
            raise self._not_found()
        if token is not None and sha256_hexdigest(token) != survey.public_token_hash:
            raise self._not_found()
        questions = await self._repo.questions(survey_id)
        options = await self._repo.options(survey_id)
        response = await self._repo.get_response(survey_id, context.user.id)
        response_schema: IntentionResponseResponse | None = None
        if response is not None:
            response_schema = self._response_schema(
                response,
                questions,
                options,
                await self._repo.response_options(response.id),
            )
        return IntentionSurveyDetail(
            id=survey.id,
            title=survey.title,
            description_html=survey.description_html,
            status=cast(IntentionStatus, survey.status),
            starts_at=survey.starts_at,
            ends_at=survey.ends_at,
            question_count=len(questions),
            has_response=response is not None,
            submissions_used=response.submission_count if response is not None else 0,
            max_submissions=survey.max_submissions,
            questions=self._question_schemas(questions, options),
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
            raise self._conflict("INTENTION_CLOSED", "当前问卷已关闭或不在填写时间内。")
        if not await self._student_is_targeted(survey, audit_context.actor):
            await self._session.rollback()
            raise self._not_found()
        questions = await self._repo.questions(survey_id)
        options = await self._repo.options(survey_id)
        question_by_id = {question.id: question for question in questions}
        options_by_question: dict[UUID, set[UUID]] = {}
        for option in options:
            options_by_question.setdefault(option.question_id, set()).add(option.id)
        answer_by_question = {answer.question_id: answer for answer in payload.answers}
        if set(answer_by_question) != set(question_by_id):
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="请完成问卷中的全部题目。",
            )
        selected: list[UUID] = []
        for question in questions:
            answer = answer_by_question[question.id]
            valid_options = options_by_question.get(question.id, set())
            if any(option_id not in valid_options for option_id in answer.selected_option_ids):
                await self._session.rollback()
                raise ApplicationError(
                    status_code=400,
                    code="VALIDATION_ERROR",
                    message="答案中包含不属于当前题目的选项。",
                )
            if not question.allow_multiple and len(answer.selected_option_ids) != 1:
                await self._session.rollback()
                raise ApplicationError(
                    status_code=422,
                    code="VALIDATION_ERROR",
                    message="单选题必须且只能选择一个选项。",
                )
            selected.extend(answer.selected_option_ids)

        response = await self._repo.get_response(
            survey_id, audit_context.actor.user.id, for_update=True
        )
        submissions_used = response.submission_count if response is not None else 0
        if survey.max_submissions is not None and submissions_used >= survey.max_submissions:
            await self._session.rollback()
            raise self._conflict(
                "INTENTION_SUBMISSION_LIMIT_REACHED", "已达到该问卷允许的提交次数。"
            )
        if response is None:
            response = IntentionResponse(
                id=uuid7(),
                survey_id=survey_id,
                user_id=audit_context.actor.user.id,
                free_text=payload.free_text.strip()
                if payload.free_text and payload.free_text.strip()
                else None,
                submission_count=1,
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
            response.submission_count += 1
            response.submitted_at = now
            response.updated_at = now
            response.revision += 1
        for option_id in selected:
            self._repo.add_response_option(
                IntentionResponseOption(response_id=response.id, option_id=option_id)
            )
        self._add_audit(
            audit_context,
            action="intention.response_submit",
            target_id=survey_id,
            now=now,
            change_summary={"submission_count": response.submission_count},
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "INTENTION_RESPONSE_CONFLICT", "问卷保存发生并发冲突，请重试。"
            ) from exc
        return self._response_schema(
            response,
            questions,
            options,
            [IntentionResponseOption(response_id=response.id, option_id=item) for item in selected],
        )

    async def list_admin(self, *, context: AuthenticatedContext) -> AdminIntentionSurveyPage:
        self._require_admin(context)
        records = await self._repo.list_surveys()
        items = [
            cast(AdminIntentionSurvey, self._summary(record, student=False)) for record in records
        ]
        return AdminIntentionSurveyPage(items=items, total=len(items))

    async def admin_detail(
        self, survey_id: UUID, *, context: AuthenticatedContext
    ) -> AdminIntentionSurveyDetail:
        self._require_admin(context)
        survey = await self._repo.get_survey(survey_id)
        if survey is None:
            raise self._not_found()
        questions = await self._repo.questions(survey_id)
        options = await self._repo.options(survey_id)
        summary = cast(
            AdminIntentionSurvey,
            self._summary(
                SurveyListRecord(
                    survey,
                    len(questions),
                    await self._repo.responded_count(survey_id),
                    False,
                    direction_ids=tuple(await self._repo.audience_direction_ids(survey_id)),
                ),
                student=False,
            ),
        )
        return AdminIntentionSurveyDetail(
            **summary.model_dump(),
            questions=self._question_schemas(questions, options),
        )

    async def _add_questions(self, survey_id: UUID, payload: IntentionSurveyCreateRequest) -> None:
        question_records: list[tuple[IntentionQuestion, IntentionQuestionInput]] = []
        for question_index, question_payload in enumerate(payload.questions):
            question = IntentionQuestion(
                id=uuid7(),
                survey_id=survey_id,
                prompt=question_payload.prompt.strip(),
                allow_multiple=question_payload.allow_multiple,
                display_order=question_index,
            )
            self._repo.add_question(question)
            question_records.append((question, question_payload))
        await self._session.flush()
        for question, question_payload in question_records:
            for option_index, option in enumerate(question_payload.options):
                self._repo.add_option(
                    IntentionOption(
                        id=uuid7(),
                        question_id=question.id,
                        label=option.label.strip(),
                        display_order=option_index,
                    )
                )

    async def _update_opened_questions(
        self,
        survey_id: UUID,
        payload_questions: list[IntentionQuestionInput],
    ) -> int:
        questions = await self._repo.questions(survey_id)
        options = await self._repo.options(survey_id)
        options_by_question: dict[UUID, list[IntentionOption]] = {}
        for option in options:
            options_by_question.setdefault(option.question_id, []).append(option)

        structure_matches = len(questions) == len(payload_questions)
        if structure_matches:
            for question, submitted in zip(questions, payload_questions, strict=True):
                current_options = options_by_question.get(question.id, [])
                structure_matches = question.allow_multiple == submitted.allow_multiple and [
                    option.label for option in current_options
                ] == [option.label for option in submitted.options]
                if not structure_matches:
                    break
        if not structure_matches:
            await self._session.rollback()
            raise self._conflict(
                "INTENTION_ANSWER_STRUCTURE_IMMUTABLE",
                "问卷开放后不能修改题目数量、题型或选项。",
            )

        prompt_change_count = 0
        for question, submitted in zip(questions, payload_questions, strict=True):
            if question.prompt != submitted.prompt:
                question.prompt = submitted.prompt
                prompt_change_count += 1
        return prompt_change_count

    async def create(
        self,
        payload: IntentionSurveyCreateRequest,
        *,
        audit_context: IntentionAuditContext,
    ) -> AdminIntentionSurvey:
        self._require_admin(audit_context.actor)
        await self._validate_audience_direction_ids(payload.audience.direction_ids)
        now = self._clock()
        token = random_urlsafe_token(24)
        survey = IntentionSurvey(
            id=uuid7(),
            title=payload.title.strip(),
            description_markdown=payload.description_markdown,
            description_html=render_markdown(payload.description_markdown),
            status="draft",
            all_students=payload.audience.all_students,
            max_submissions=payload.max_submissions,
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
        await self._session.flush()
        await self._repo.replace_audience(survey.id, payload.audience.direction_ids)
        await self._add_questions(survey.id, payload)
        self._add_audit(
            audit_context,
            action="intention.create",
            target_id=survey.id,
            now=now,
            change_summary={
                "all_students": payload.audience.all_students,
                "direction_count": len(payload.audience.direction_ids),
            },
        )
        await self._session.commit()
        return cast(
            AdminIntentionSurvey,
            self._summary(
                SurveyListRecord(
                    survey,
                    len(payload.questions),
                    0,
                    False,
                    direction_ids=tuple(sorted(payload.audience.direction_ids)),
                ),
                student=False,
            ),
        )

    async def patch(
        self,
        survey_id: UUID,
        payload: IntentionSurveyPatchRequest,
        *,
        audit_context: IntentionAuditContext,
    ) -> AdminIntentionSurveyDetail:
        self._require_admin(audit_context.actor)
        survey = await self._repo.get_survey(survey_id, for_update=True)
        if survey is None:
            await self._session.rollback()
            raise self._not_found()
        if survey.status == "archived":
            await self._session.rollback()
            raise self._conflict("INTENTION_ARCHIVED", "已归档问卷不能修改。")
        if survey.revision != payload.revision:
            await self._session.rollback()
            raise self._conflict("REVISION_CONFLICT", "问卷已被其他管理员修改。")
        await self._validate_audience_direction_ids(payload.audience.direction_ids)
        old_audience_direction_ids = await self._repo.audience_direction_ids(survey_id)
        old_title = survey.title
        old_description = survey.description_markdown
        old_max_submissions = survey.max_submissions
        old_starts_at = survey.starts_at
        old_ends_at = survey.ends_at
        old_all_students = survey.all_students
        prompt_change_count = 0
        if survey.status == "draft":
            old_questions = await self._repo.questions(survey_id)
            prompt_change_count = sum(
                old.prompt != submitted.prompt
                for old, submitted in zip(
                    old_questions,
                    payload.questions,
                    strict=False,
                )
            ) + abs(len(old_questions) - len(payload.questions))
            for old in old_questions:
                await self._session.delete(old)
            await self._session.flush()
            await self._add_questions(survey_id, payload)
        else:
            prompt_change_count = await self._update_opened_questions(
                survey_id,
                payload.questions,
            )
        survey.title = payload.title.strip()
        survey.description_markdown = payload.description_markdown
        survey.description_html = render_markdown(payload.description_markdown)
        survey.all_students = payload.audience.all_students
        survey.max_submissions = payload.max_submissions
        survey.starts_at = payload.starts_at
        survey.ends_at = payload.ends_at
        survey.updated_by = audit_context.actor.user.id
        survey.updated_at = self._clock()
        survey.revision += 1
        await self._repo.replace_audience(survey_id, payload.audience.direction_ids)
        self._add_audit(
            audit_context,
            action="intention.update",
            target_id=survey.id,
            now=survey.updated_at,
            change_summary={
                "status": survey.status,
                "title_changed": old_title != survey.title,
                "description_changed": old_description != survey.description_markdown,
                "submission_limit_changed": old_max_submissions != survey.max_submissions,
                "schedule_changed": (
                    old_starts_at != survey.starts_at or old_ends_at != survey.ends_at
                ),
                "audience_changed": (
                    old_all_students != survey.all_students
                    or set(old_audience_direction_ids) != set(payload.audience.direction_ids)
                ),
                "question_prompt_change_count": prompt_change_count,
                "all_students": payload.audience.all_students,
                "direction_count": len(payload.audience.direction_ids),
            },
        )
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return await self.admin_detail(survey_id, context=audit_context.actor)

    @staticmethod
    def _mail_event_key(survey: IntentionSurvey, user_id: UUID) -> str:
        return f"intention:{survey.id}:open:{survey.revision}:email:{user_id}"

    @classmethod
    def _mail_job(
        cls,
        *,
        survey: IntentionSurvey,
        user: User,
        now: datetime,
    ) -> OutboxJob:
        return OutboxJob(
            id=uuid7(),
            job_type="intention_open_email",
            event_key=cls._mail_event_key(survey, user.id),
            payload={
                "recipient": user.email,
                "full_name": user.full_name,
                "survey_id": str(survey.id),
                "title": survey.title,
                "target_url": f"/intentions/{survey.id}",
            },
            secret_payload_ciphertext=None,
            status="pending",
            available_at=now,
            attempt_count=0,
            max_attempts=8,
            locked_by=None,
            locked_at=None,
            last_error_code=None,
            last_error_summary=None,
            created_at=now,
            sent_at=None,
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
        allowed = {
            "draft": {"open"},
            "open": {"closed"},
            "closed": {"open", "archived"},
        }
        if target not in allowed.get(survey.status, set()):
            await self._session.rollback()
            raise self._conflict("STATE_CONFLICT", "问卷状态不允许执行该变更。")
        previous_status = survey.status
        if previous_status == "draft" and target == "open" and not survey.all_students:
            await self._validate_audience_direction_ids(
                await self._repo.audience_direction_ids(survey.id)
            )
        survey.status = target
        survey.updated_by = audit_context.actor.user.id
        survey.updated_at = self._clock()
        survey.revision += 1
        action = (
            "intention.reopen"
            if previous_status == "closed" and target == "open"
            else "intention." + target
        )
        self._add_audit(
            audit_context,
            action=action,
            target_id=survey.id,
            now=survey.updated_at,
            change_summary={"from_status": previous_status, "to_status": target},
        )
        await self._session.commit()
        records = await self._repo.list_surveys()
        record = next(item for item in records if item.survey.id == survey_id)
        return cast(AdminIntentionSurvey, self._summary(record, student=False))

    async def send_email_notifications(
        self,
        survey_id: UUID,
        payload: IntentionEmailNotificationRequest,
        *,
        audit_context: IntentionAuditContext,
    ) -> IntentionEmailNotificationResponse:
        self._require_admin(audit_context.actor)
        survey = await self._repo.get_survey(survey_id, for_update=True)
        now = self._clock()
        if survey is None:
            await self._session.rollback()
            raise self._not_found()
        if not self._is_open(survey, now):
            await self._session.rollback()
            raise self._conflict(
                "INTENTION_CLOSED",
                "当前问卷未开放或不在填写时间内，不能发送邮件通知。",
            )

        audience_direction_ids: list[UUID] | None = None
        if not survey.all_students:
            audience_direction_ids = await self._repo.audience_direction_ids(survey.id)

        direction_ids: list[UUID] | None = None
        if payload.recipient_scope == "manual":
            recipients = await self._repo.active_students_by_ids(payload.recipient_user_ids)
            requested_ids = set(payload.recipient_user_ids)
            if {user.id for user in recipients} != requested_ids:
                await self._session.rollback()
                raise ApplicationError(
                    status_code=400,
                    code="INVALID_INTENTION_EMAIL_RECIPIENTS",
                    message="所选成员中包含非激活学生，请刷新成员列表后重试。",
                )
            if audience_direction_ids is not None and any(
                user.direction_id not in audience_direction_ids for user in recipients
            ):
                await self._session.rollback()
                raise ApplicationError(
                    status_code=400,
                    code="INVALID_INTENTION_EMAIL_RECIPIENTS",
                    message="所选成员中包含不属于该问卷目标技术组的学生。",
                )
        else:
            if payload.recipient_scope == "direction":
                if payload.direction_ids:
                    direction_ids = list(payload.direction_ids)
                else:
                    assert payload.direction_id is not None
                    direction_ids = [payload.direction_id]
                requested_direction_ids = set(direction_ids)
                if audience_direction_ids is not None and not requested_direction_ids.issubset(
                    audience_direction_ids
                ):
                    await self._session.rollback()
                    raise ApplicationError(
                        status_code=400,
                        code="INVALID_INTENTION_EMAIL_DIRECTION",
                        message="所选技术组不属于该问卷的填写受众。",
                    )
                active_directions = await self._repo.active_directions_by_ids(direction_ids)
                if {direction.id for direction in active_directions} != requested_direction_ids:
                    await self._session.rollback()
                    raise ApplicationError(
                        status_code=400,
                        code="INVALID_INTENTION_EMAIL_DIRECTION",
                        message="所选技术组中包含不存在或已停用的组，请刷新后重试。",
                    )
            recipient_direction_ids = (
                direction_ids if payload.recipient_scope == "direction" else audience_direction_ids
            )
            recipients = await self._repo.active_students_for_email_scope(
                direction_ids=recipient_direction_ids
            )
            if not recipients:
                await self._session.rollback()
                raise ApplicationError(
                    status_code=400,
                    code="NO_INTENTION_EMAIL_RECIPIENTS",
                    message="当前发送范围内没有激活学生。",
                )

        event_keys = {user.id: self._mail_event_key(survey, user.id) for user in recipients}
        existing = await self._outbox.existing_event_keys(list(event_keys.values()))
        queued_count = 0
        for user in recipients:
            event_key = event_keys[user.id]
            if event_key in existing:
                continue
            self._outbox.add(self._mail_job(survey=survey, user=user, now=now))
            queued_count += 1

        already_queued_count = len(recipients) - queued_count
        change_summary: dict[str, object] = {
            "recipient_scope": payload.recipient_scope,
            "requested_count": len(recipients),
            "queued_count": queued_count,
            "already_queued_count": already_queued_count,
        }
        if direction_ids is not None:
            change_summary["direction_ids"] = sorted(
                str(direction_id) for direction_id in direction_ids
            )
        self._add_audit(
            audit_context,
            action="intention.email_notify",
            target_id=survey.id,
            now=now,
            change_summary=change_summary,
        )
        await self._session.commit()
        return IntentionEmailNotificationResponse(
            survey_id=survey.id,
            requested_count=len(recipients),
            queued_count=queued_count,
            already_queued_count=already_queued_count,
        )

    async def apply_first_choice_directions(
        self,
        survey_id: UUID,
        payload: IntentionDirectionAssignmentRequest,
        *,
        audit_context: IntentionAuditContext,
    ) -> IntentionDirectionAssignmentResponse:
        self._require_admin(audit_context.actor)
        survey = await self._repo.get_survey(survey_id, for_update=True)
        if survey is None:
            await self._session.rollback()
            raise self._not_found()
        if survey.title.strip() != DIRECTION_ASSIGNMENT_SURVEY_TITLE:
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="INVALID_INTENTION_DIRECTION_SURVEY",
                message="仅标题为“意向选择”的问卷可以按第一志愿配置技术方向。",
            )

        questions = await self._repo.questions(survey_id)
        if not questions or questions[0].id != payload.question_id:
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="INVALID_INTENTION_FIRST_CHOICE",
                message="只能使用问卷按题序排列的第一道题配置技术方向。",
            )
        first_question = questions[0]
        if first_question.allow_multiple:
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="INTENTION_FIRST_CHOICE_MUST_BE_SINGLE",
                message="第一志愿必须是单选题，才能配置唯一技术方向。",
            )

        options = [
            option
            for option in await self._repo.options(survey_id)
            if option.question_id == first_question.id
        ]
        mapping_by_option = {item.option_id: item.direction_id for item in payload.option_mappings}
        if set(mapping_by_option) != {option.id for option in options}:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="INVALID_INTENTION_DIRECTION_MAPPING",
                message="必须为第一志愿的每个选项配置一个技术方向。",
            )

        requested_direction_ids = set(mapping_by_option.values())
        active_directions = await self._repo.active_directions_by_ids(
            sorted(requested_direction_ids)
        )
        if {direction.id for direction in active_directions} != requested_direction_ids:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="INVALID_INTENTION_DIRECTION_MAPPING",
                message="映射中包含不存在或已停用的技术方向，请刷新后重试。",
            )

        total_responses = await self._repo.responded_count(survey_id)
        records: list[FirstChoiceDirectionRecord] = await self._repo.active_student_first_choices(
            survey_id,
            first_question.id,
        )
        if not records:
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="NO_INTENTION_DIRECTION_RESPONSES",
                message="当前没有可配置方向的激活学生回答。",
            )
        if len({record.user.id for record in records}) != len(records):
            await self._session.rollback()
            raise self._conflict(
                "INTENTION_RESPONSE_CONFLICT",
                "第一志愿回答存在冲突，请检查问卷数据后重试。",
            )

        now = self._clock()
        updated_count = 0
        unchanged_count = 0
        for record in records:
            target_direction_id = mapping_by_option[record.option_id]
            if record.user.direction_id == target_direction_id:
                unchanged_count += 1
                continue
            previous_direction_id = record.user.direction_id
            record.user.direction_id = target_direction_id
            record.user.revision += 1
            updated_count += 1
            self._add_audit(
                audit_context,
                action="user.direction_assign_from_intention",
                target_type="user",
                target_id=record.user.id,
                now=now,
                change_summary={
                    "direction_id": {
                        "from": (
                            str(previous_direction_id)
                            if previous_direction_id is not None
                            else None
                        ),
                        "to": str(target_direction_id),
                    },
                    "source_survey_id": str(survey.id),
                },
            )

        skipped_response_count = max(total_responses - len(records), 0)
        self._add_audit(
            audit_context,
            action="intention.first_choice_directions_apply",
            target_id=survey.id,
            now=now,
            change_summary={
                "question_id": str(first_question.id),
                "mapping_count": len(mapping_by_option),
                "eligible_response_count": len(records),
                "updated_count": updated_count,
                "unchanged_count": unchanged_count,
                "skipped_response_count": skipped_response_count,
            },
        )
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return IntentionDirectionAssignmentResponse(
            survey_id=survey.id,
            question_id=first_question.id,
            eligible_response_count=len(records),
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            skipped_response_count=skipped_response_count,
        )

    async def stats(
        self, survey_id: UUID, *, context: AuthenticatedContext
    ) -> IntentionStatsResponse:
        self._require_admin(context)
        survey = await self._repo.get_survey(survey_id)
        if survey is None:
            raise self._not_found()
        responded = await self._repo.responded_count(survey_id)
        direction_ids = (
            None if survey.all_students else await self._repo.audience_direction_ids(survey_id)
        )
        total_students = await self._repo.active_student_count(direction_ids=direction_ids)
        questions = await self._repo.questions(survey_id)
        counts = await self._repo.option_counts(survey_id)
        counts_by_question: dict[UUID, list[SurveyOptionCount]] = {}
        for item in counts:
            counts_by_question.setdefault(item.question.id, []).append(item)
        return IntentionStatsResponse(
            survey_id=survey_id,
            total_active_students=total_students,
            responded_count=responded,
            response_rate=round((responded / total_students * 100) if total_students else 0.0, 2),
            questions=[
                IntentionStatsQuestion(
                    question_id=question.id,
                    prompt=question.prompt,
                    allow_multiple=question.allow_multiple,
                    options=[
                        IntentionStatsOption(
                            option_id=item.option.id,
                            label=item.option.label,
                            response_count=item.response_count,
                            percentage=round(
                                (item.response_count / responded * 100) if responded else 0.0,
                                2,
                            ),
                        )
                        for item in counts_by_question.get(question.id, [])
                    ],
                )
                for question in questions
            ],
        )

    async def roster(
        self, survey_id: UUID, *, context: AuthenticatedContext
    ) -> IntentionRosterResponse:
        self._require_admin(context)
        survey = await self._repo.get_survey(survey_id)
        if survey is None:
            raise self._not_found()
        questions = await self._repo.questions(survey_id)
        options = await self._repo.options(survey_id)
        options_by_question: dict[UUID, list[IntentionOption]] = {}
        for option in options:
            options_by_question.setdefault(option.question_id, []).append(option)
        records = await self._repo.roster(survey_id)
        selected_by_response = await self._repo.response_options_for_responses(
            [record.response.id for record in records]
        )
        items: list[IntentionRosterItem] = []
        for record in records:
            selected_ids = {
                link.option_id for link in selected_by_response.get(record.response.id, [])
            }
            items.append(
                IntentionRosterItem(
                    user_id=record.user.id,
                    full_name=record.user.full_name,
                    student_number=record.user.student_number,
                    email=record.user.email,
                    answers=[
                        IntentionRosterAnswer(
                            question_id=question.id,
                            prompt=question.prompt,
                            selected_options=[
                                option.label
                                for option in options_by_question.get(question.id, [])
                                if option.id in selected_ids
                            ],
                        )
                        for question in questions
                    ],
                    free_text=record.response.free_text,
                    submission_count=record.response.submission_count,
                    submitted_at=record.response.submitted_at,
                )
            )
        return IntentionRosterResponse(survey_id=survey_id, items=items, total=len(items))

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
            raise self._conflict("INTENTION_CLOSED", "问卷已关闭，不能再生成填写二维码。")
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
