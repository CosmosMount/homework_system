import re
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.announcements.service import ScheduledAnnouncementPublisher
from app.assignments.service import ScheduledAssignmentProcessor
from app.auth.models import OneTimeToken
from app.auth.repository import AuthRepository
from app.core.config import Settings
from app.core.security import OutboxCipher
from app.knowledge.feishu_client import KnowledgeSyncError
from app.knowledge.service import KnowledgeSynchronizer
from app.notifications.mailer import (
    MailSender,
    PermanentMailError,
    SMTPMailSender,
    TransientMailError,
)
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository

RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=4),
    timedelta(hours=12),
    timedelta(hours=24),
    timedelta(hours=48),
)
_SAFE_ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,100}$")
_TOKEN_JOB_PURPOSES = {
    "email_verification": "email_verification",
    "password_reset": "password_reset",
}


def _token_id_from_job(job: OutboxJob) -> UUID | None:
    purpose = _TOKEN_JOB_PURPOSES.get(job.job_type)
    if purpose is None:
        return None

    prefix, separator, raw_token_id = job.event_key.partition(":")
    if separator != ":" or prefix != purpose or not raw_token_id:
        raise ValueError("invalid token email event key")
    return UUID(raw_token_id)


def token_email_is_deliverable(
    job: OutboxJob,
    token: OneTimeToken | None,
    *,
    now: datetime,
) -> bool:
    token_id = _token_id_from_job(job)
    if token_id is None:
        return True
    expected_purpose = _TOKEN_JOB_PURPOSES[job.job_type]
    return bool(
        token is not None
        and token.id == token_id
        and token.purpose == expected_purpose
        and token.used_at is None
        and token.expires_at > now
    )


def apply_token_superseded(job: OutboxJob) -> None:
    job.attempt_count += 1
    job.status = "dead"
    job.locked_by = None
    job.locked_at = None
    job.last_error_code = "TOKEN_SUPERSEDED"
    job.last_error_summary = "一次性令牌已失效，邮件未投递。"


def apply_delivery_failure(
    job: OutboxJob,
    *,
    now: datetime,
    code: str,
    permanent: bool,
    summary: str | None = None,
) -> None:
    job.attempt_count += 1
    exhausted = job.attempt_count >= job.max_attempts
    job.status = "dead" if permanent or exhausted else "retry"
    if job.status == "retry":
        delay_index = min(job.attempt_count - 1, len(RETRY_DELAYS) - 1)
        job.available_at = now + RETRY_DELAYS[delay_index]
    job.locked_by = None
    job.locked_at = None
    fallback_code = "PERMANENT_FAILURE" if permanent else "TRANSIENT_FAILURE"
    job.last_error_code = code if _SAFE_ERROR_CODE.fullmatch(code) else fallback_code
    job.last_error_summary = summary or "邮件投递失败，未记录收件地址或服务响应正文。"


class AnnouncementPublisher(Protocol):
    async def publish(self, announcement_id: UUID, job_id: UUID) -> None: ...


class AssignmentProcessor(Protocol):
    async def publish(self, assignment_id: UUID, job_id: UUID) -> None: ...
    async def close(self, assignment_id: UUID, job_id: UUID) -> None: ...


class KnowledgeSyncProcessor(Protocol):
    async def synchronize(self, run_id: UUID) -> None: ...
    async def mark_failed(self, run_id: UUID, error: KnowledgeSyncError) -> None: ...


class OutboxProcessor:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        sender: MailSender | None = None,
        announcement_publisher: AnnouncementPublisher | None = None,
        assignment_processor: AssignmentProcessor | None = None,
        knowledge_sync: KnowledgeSyncProcessor | None = None,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._sender = sender or SMTPMailSender(settings)
        self._announcement_publisher = announcement_publisher or ScheduledAnnouncementPublisher(
            factory
        )
        self._assignment_processor = assignment_processor or ScheduledAssignmentProcessor(factory)
        self._knowledge_sync = knowledge_sync or KnowledgeSynchronizer(factory, settings)
        self._cipher = OutboxCipher(settings.outbox_encryption_key.get_secret_value())

    async def _claim(self, now: datetime) -> list[OutboxJob]:
        async with self._factory() as session, session.begin():
            return await OutboxRepository(session).claim(
                worker_name=self._settings.worker_name,
                now=now,
                lease_seconds=self._settings.worker_lock_lease_seconds,
            )

    def _secret_payload(self, job: OutboxJob) -> dict[str, object]:
        if job.secret_payload_ciphertext is None:
            return {}
        decoded = self._cipher.decrypt(job.secret_payload_ciphertext)
        return {str(key): value for key, value in decoded.items()}

    async def _mark_sent(self, job_id: UUID, now: datetime) -> None:
        async with self._factory() as session, session.begin():
            job = await OutboxRepository(session).get_by_id(job_id, for_update=True)
            if job is None or job.status != "processing":
                return
            job.status = "sent"
            job.sent_at = now
            job.attempt_count += 1
            job.locked_by = None
            job.locked_at = None
            job.last_error_code = None
            job.last_error_summary = None

    async def _mark_failed(
        self,
        job_id: UUID,
        *,
        now: datetime,
        code: str,
        permanent: bool,
    ) -> None:
        async with self._factory() as session, session.begin():
            job = await OutboxRepository(session).get_by_id(job_id, for_update=True)
            if job is None or job.status != "processing":
                return
            apply_delivery_failure(
                job,
                now=now,
                code=code,
                permanent=permanent,
                summary=(
                    "知识库同步任务失败，未记录飞书凭证或服务响应正文。"
                    if job.job_type == "sync_knowledge"
                    else None
                ),
            )

    async def _token_email_is_deliverable(
        self,
        job: OutboxJob,
        now: datetime,
    ) -> bool:
        token_id = _token_id_from_job(job)
        if token_id is None:
            return True
        async with self._factory() as session:
            token = await AuthRepository(session).get_one_time_token_by_id(token_id)
        return token_email_is_deliverable(job, token, now=now)

    async def _mark_token_superseded(self, job_id: UUID) -> None:
        async with self._factory() as session, session.begin():
            job = await OutboxRepository(session).get_by_id(job_id, for_update=True)
            if job is None or job.status != "processing":
                return
            apply_token_superseded(job)

    async def run_once(self) -> int:
        now = datetime.now(UTC)
        jobs = await self._claim(now)
        for job in jobs:
            try:
                if job.job_type == "publish_announcement":
                    announcement_id = UUID(str(job.payload["announcement_id"]))
                    await self._announcement_publisher.publish(
                        announcement_id,
                        job.id,
                    )
                elif job.job_type == "publish_assignment":
                    assignment_id = UUID(str(job.payload["assignment_id"]))
                    await self._assignment_processor.publish(assignment_id, job.id)
                elif job.job_type == "close_assignment":
                    assignment_id = UUID(str(job.payload["assignment_id"]))
                    await self._assignment_processor.close(assignment_id, job.id)
                elif job.job_type == "sync_knowledge":
                    run_id = UUID(str(job.payload["run_id"]))
                    await self._knowledge_sync.synchronize(run_id)
                else:
                    if not await self._token_email_is_deliverable(job, datetime.now(UTC)):
                        await self._mark_token_superseded(job.id)
                        continue
                    secret_payload = self._secret_payload(job)
                    await self._sender.send(job, secret_payload)
            except KnowledgeSyncError as exc:
                final_failure = exc.permanent or job.attempt_count + 1 >= job.max_attempts
                if final_failure:
                    await self._knowledge_sync.mark_failed(
                        UUID(str(job.payload["run_id"])),
                        exc,
                    )
                await self._mark_failed(
                    job.id,
                    now=datetime.now(UTC),
                    code=exc.code,
                    permanent=exc.permanent,
                )
            except PermanentMailError as exc:
                await self._mark_failed(
                    job.id,
                    now=datetime.now(UTC),
                    code=str(exc) or "PERMANENT_FAILURE",
                    permanent=True,
                )
            except (TransientMailError, OSError) as exc:
                await self._mark_failed(
                    job.id,
                    now=datetime.now(UTC),
                    code=str(exc) or "TRANSIENT_FAILURE",
                    permanent=False,
                )
            except (KeyError, TypeError, ValueError):
                await self._mark_failed(
                    job.id,
                    now=datetime.now(UTC),
                    code="INVALID_JOB_PAYLOAD",
                    permanent=True,
                )
            else:
                await self._mark_sent(job.id, datetime.now(UTC))
        return len(jobs)
