from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.notifications.schemas import OutboxJobPage, OutboxJobResponse


def mask_email(value: object) -> str:
    email = str(value or "")
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    visible = local[:1] if local else ""
    return f"{visible}***@{domain}"


class OutboxAdministrationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._outbox = OutboxRepository(session)
        self._audit = AuditRepository(session)

    @staticmethod
    def _response(job: OutboxJob) -> OutboxJobResponse:
        return OutboxJobResponse(
            id=job.id,
            job_type=job.job_type,
            status=job.status,
            recipient_masked=mask_email(job.payload.get("recipient")),
            available_at=job.available_at,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            last_error_code=job.last_error_code,
            last_error_summary=job.last_error_summary,
            created_at=job.created_at,
            sent_at=job.sent_at,
        )

    async def list_jobs(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        job_type: str | None,
    ) -> OutboxJobPage:
        jobs, total = await self._outbox.list_jobs(
            page=page,
            page_size=page_size,
            status=status,
            job_type=job_type,
        )
        return OutboxJobPage(
            items=[self._response(job) for job in jobs],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def retry(
        self,
        job_id: UUID,
        *,
        admin: AuthenticatedContext,
        request_id: str,
        ip_prefix: str,
    ) -> OutboxJobResponse:
        job = await self._outbox.get_by_id(job_id, for_update=True)
        if job is None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=404,
                code="RESOURCE_NOT_FOUND",
                message="邮件任务不存在。",
            )
        if job.status != "dead":
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="只有最终失败的邮件任务可以人工重试。",
            )
        now = datetime.now(UTC)
        job.status = "retry"
        job.available_at = now
        job.max_attempts = min(32, max(job.max_attempts, job.attempt_count + 8))
        job.locked_by = None
        job.locked_at = None
        job.last_error_code = None
        job.last_error_summary = None
        self._audit.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=admin.user.id,
                action="mail_outbox.retry",
                target_type="outbox_job",
                target_id=job.id,
                request_id=request_id,
                ip_prefix=ip_prefix,
                result="success",
                change_summary={"event_key": job.event_key, "attempt_count": job.attempt_count},
                created_at=now,
            )
        )
        await self._session.commit()
        return self._response(job)
