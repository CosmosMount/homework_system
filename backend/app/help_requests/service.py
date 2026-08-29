from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, context_effective_role, context_is_admin
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.core.markdown import render_markdown
from app.help_requests.models import HelpRequest
from app.help_requests.repository import AdminHelpRequestRecord, HelpRequestRepository
from app.help_requests.schemas import (
    AdminHelpRequestDetail,
    AdminHelpRequestPage,
    AdminHelpRequestSummary,
    HelpRequestCreateRequest,
    HelpRequestDetail,
    HelpRequestPage,
    HelpRequestResolutionRequest,
    HelpRequestStatus,
    HelpRequestSubmitter,
    HelpRequestSummary,
    HelpRequestType,
    PublicHelpRequestDetail,
)
from app.notifications.models import StudentNotification
from app.notifications.repository import StudentNotificationRepository


@dataclass(frozen=True, slots=True)
class HelpRequestAuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


class HelpRequestService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))
        self._repo = HelpRequestRepository(session)
        self._audit = AuditRepository(session)
        self._notifications = StudentNotificationRepository(session)

    @staticmethod
    def _not_found() -> ApplicationError:
        return ApplicationError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="反馈答疑记录不存在或当前不可见。",
        )

    @staticmethod
    def _require_student(context: AuthenticatedContext) -> None:
        if context_effective_role(context) != "student":
            raise ApplicationError(
                status_code=403,
                code="FORBIDDEN",
                message="管理员不能通过学生接口提交反馈答疑。",
            )

    @staticmethod
    def _require_admin(context: AuthenticatedContext) -> None:
        if not context_is_admin(context):
            raise ApplicationError(
                status_code=403,
                code="FORBIDDEN",
                message="仅管理员可以处理反馈答疑。",
            )

    @staticmethod
    def _summary(request: HelpRequest) -> HelpRequestSummary:
        return HelpRequestSummary(
            id=request.id,
            request_type=cast(HelpRequestType, request.request_type),
            status=cast(HelpRequestStatus, request.status),
            title=request.title,
            created_at=request.created_at,
            updated_at=request.updated_at,
            resolved_at=request.resolved_at,
            revision=request.revision,
        )

    @classmethod
    def _detail(
        cls,
        request: HelpRequest,
        *,
        notification_ids: list[UUID] | None = None,
    ) -> HelpRequestDetail:
        return HelpRequestDetail(
            **cls._summary(request).model_dump(),
            content_html=request.content_html,
            resolution_html=request.resolution_html,
            notification_ids=notification_ids or [],
        )

    @classmethod
    def _public_detail(cls, request: HelpRequest) -> PublicHelpRequestDetail:
        resolution_html = request.resolution_html
        if resolution_html is None:
            raise cls._not_found()
        return PublicHelpRequestDetail(
            **cls._summary(request).model_dump(),
            content_html=request.content_html,
            resolution_html=resolution_html,
        )

    @staticmethod
    def _submitter(record: AdminHelpRequestRecord) -> HelpRequestSubmitter:
        user = record.submitter
        return HelpRequestSubmitter(
            id=user.id,
            full_name=user.full_name,
            student_number=user.student_number,
            email=user.email,
        )

    @classmethod
    def _admin_summary(cls, record: AdminHelpRequestRecord) -> AdminHelpRequestSummary:
        return AdminHelpRequestSummary(
            **cls._summary(record.request).model_dump(),
            created_by=cls._submitter(record),
        )

    @classmethod
    def _admin_detail(cls, record: AdminHelpRequestRecord) -> AdminHelpRequestDetail:
        request = record.request
        return AdminHelpRequestDetail(
            **cls._admin_summary(record).model_dump(),
            content_markdown=request.content_markdown,
            content_html=request.content_html,
            resolution_markdown=request.resolution_markdown,
            resolution_html=request.resolution_html,
            resolved_by=request.resolved_by,
        )

    def _add_audit(
        self,
        context: HelpRequestAuditContext,
        *,
        action: str,
        request: HelpRequest,
        now: datetime,
    ) -> None:
        self._audit.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=context.actor.user.id,
                action=action,
                target_type="help_request",
                target_id=request.id,
                request_id=context.request_id,
                ip_prefix=context.ip_prefix,
                result="success",
                change_summary={
                    "request_type": request.request_type,
                    "status": request.status,
                    "revision": request.revision,
                },
                created_at=now,
            )
        )

    async def list_public(
        self,
        *,
        context: AuthenticatedContext,
        page: int,
        page_size: int,
    ) -> HelpRequestPage:
        # Authentication is established by the typed context dependency; both
        # active roles intentionally share the same anonymous public view.
        _ = context.user.id
        requests, total = await self._repo.list_public(
            page=page,
            page_size=page_size,
        )
        return HelpRequestPage(
            items=[self._summary(item) for item in requests],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def public_detail(
        self,
        request_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> PublicHelpRequestDetail:
        # Keep valid Session enforcement explicit at this Service boundary.
        _ = context.user.id
        request = await self._repo.get_public(request_id)
        if request is None:
            raise self._not_found()
        return self._public_detail(request)

    async def list_student(
        self,
        *,
        context: AuthenticatedContext,
        request_type: HelpRequestType | None,
        status: HelpRequestStatus | None,
        page: int,
        page_size: int,
    ) -> HelpRequestPage:
        self._require_student(context)
        requests, total = await self._repo.list_student(
            user_id=context.user.id,
            request_type=request_type,
            status=status,
            page=page,
            page_size=page_size,
        )
        return HelpRequestPage(
            items=[self._summary(item) for item in requests],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def student_detail(
        self, request_id: UUID, *, context: AuthenticatedContext
    ) -> HelpRequestDetail:
        self._require_student(context)
        request = await self._repo.get_student(request_id, context.user.id)
        if request is None:
            raise self._not_found()
        notification_ids = await self._notifications.unread_ids_for_target(
            user_id=context.user.id,
            target_type="help_request",
            target_id=request.id,
        )
        return self._detail(request, notification_ids=notification_ids)

    async def create(
        self,
        payload: HelpRequestCreateRequest,
        *,
        audit_context: HelpRequestAuditContext,
    ) -> HelpRequestDetail:
        self._require_student(audit_context.actor)
        now = self._clock()
        request = HelpRequest(
            id=uuid7(),
            request_type=payload.request_type,
            status="open",
            title=payload.title,
            content_markdown=payload.content_markdown,
            content_html=render_markdown(payload.content_markdown),
            resolution_markdown=None,
            resolution_html=None,
            created_by=audit_context.actor.user.id,
            resolved_by=None,
            resolved_at=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        try:
            self._repo.add(request)
            self._add_audit(
                audit_context,
                action="help_request.created",
                request=request,
                now=now,
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return self._detail(request)

    async def list_admin(
        self,
        *,
        context: AuthenticatedContext,
        request_type: HelpRequestType | None,
        status: HelpRequestStatus | None,
        query: str | None,
        page: int,
        page_size: int,
    ) -> AdminHelpRequestPage:
        self._require_admin(context)
        normalized_query = query.strip() if query is not None else None
        records, total = await self._repo.list_admin(
            request_type=request_type,
            status=status,
            query=normalized_query or None,
            page=page,
            page_size=page_size,
        )
        return AdminHelpRequestPage(
            items=[self._admin_summary(item) for item in records],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def admin_detail(
        self, request_id: UUID, *, context: AuthenticatedContext
    ) -> AdminHelpRequestDetail:
        self._require_admin(context)
        record = await self._repo.get_admin(request_id)
        if record is None:
            raise self._not_found()
        return self._admin_detail(record)

    async def resolve(
        self,
        request_id: UUID,
        payload: HelpRequestResolutionRequest,
        *,
        audit_context: HelpRequestAuditContext,
    ) -> AdminHelpRequestDetail:
        self._require_admin(audit_context.actor)
        request = await self._repo.get_by_id(request_id, for_update=True)
        if request is None:
            await self._session.rollback()
            raise self._not_found()
        if request.revision != payload.revision:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="REVISION_CONFLICT",
                message="反馈答疑记录已被其他管理员更新，请刷新后重试。",
            )
        submitter = await self._repo.get_submitter(request.created_by)
        if submitter is None:
            await self._session.rollback()
            raise self._not_found()

        try:
            was_resolved = request.status == "resolved"
            now = self._clock()
            request.status = "resolved"
            request.resolution_markdown = payload.resolution_markdown
            request.resolution_html = render_markdown(payload.resolution_markdown)
            request.resolved_by = audit_context.actor.user.id
            request.resolved_at = now
            request.updated_at = now
            request.revision += 1
            self._add_audit(
                audit_context,
                action=(
                    "help_request.resolution_revised" if was_resolved else "help_request.resolved"
                ),
                request=request,
                now=now,
            )
            self._notifications.add_all(
                [
                    StudentNotification(
                        id=uuid7(),
                        user_id=request.created_by,
                        notification_type="help_request_resolved",
                        event_key=f"help_request_resolved:{request.id}:{request.revision}",
                        title=f"反馈答疑已处理：{request.title}"[:200],
                        target_type="help_request",
                        target_id=request.id,
                        target_url=f"/help/{request.id}",
                        created_at=now,
                        read_at=None,
                    )
                ]
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return self._admin_detail(AdminHelpRequestRecord(request=request, submitter=submitter))
