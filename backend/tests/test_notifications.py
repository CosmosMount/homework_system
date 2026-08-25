from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.auth.models import OneTimeToken
from app.notifications.admin_service import OutboxAdministrationService
from app.notifications.models import OutboxJob
from app.notifications.service import (
    OutboxProcessor,
    apply_delivery_failure,
    apply_token_superseded,
    token_email_is_deliverable,
)


def make_job(
    *, attempt_count: int = 0, max_attempts: int = 8, token_id: UUID | None = None
) -> OutboxJob:
    now = datetime.now(UTC)
    return OutboxJob(
        id=uuid4(),
        job_type="email_verification",
        event_key=f"email_verification:{token_id or uuid4()}",
        payload={
            "recipient": "student.secret@connect.hkust-gz.edu.cn",
            "full_name": "测试同学",
        },
        secret_payload_ciphertext="ciphertext-must-not-leak",
        status="processing",
        available_at=now,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        locked_by="worker-1",
        locked_at=now,
        last_error_code=None,
        last_error_summary=None,
        created_at=now,
        sent_at=None,
    )


def test_transient_delivery_failure_uses_backoff_and_redacts_free_form_error() -> None:
    now = datetime.now(UTC)
    job = make_job()

    apply_delivery_failure(
        job,
        now=now,
        code="SMTP failed for student.secret@connect.hkust-gz.edu.cn",
        permanent=False,
    )

    assert job.status == "retry"
    assert job.attempt_count == 1
    assert job.available_at == now + timedelta(minutes=1)
    assert job.locked_by is None
    assert job.locked_at is None
    assert job.last_error_code == "TRANSIENT_FAILURE"
    assert "student.secret" not in (job.last_error_summary or "")


@pytest.mark.parametrize(
    ("attempt_count", "permanent"),
    [
        (7, False),
        (0, True),
    ],
)
def test_delivery_failure_becomes_dead_when_exhausted_or_permanent(
    attempt_count: int,
    permanent: bool,
) -> None:
    job = make_job(attempt_count=attempt_count)

    apply_delivery_failure(
        job,
        now=datetime.now(UTC),
        code="SMTP_550",
        permanent=permanent,
    )

    assert job.status == "dead"
    assert job.last_error_code == "SMTP_550"


def test_outbox_administration_response_excludes_payload_and_ciphertext() -> None:
    job = make_job()
    response = OutboxAdministrationService._response(job)
    serialized = response.model_dump_json()

    assert response.recipient_masked == "s***@connect.hkust-gz.edu.cn"
    assert "student.secret" not in serialized
    assert "ciphertext-must-not-leak" not in serialized
    assert "payload" not in type(response).model_fields
    assert "secret_payload_ciphertext" not in type(response).model_fields


def make_token(
    token_id: UUID,
    *,
    purpose: str = "email_verification",
    used_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> OneTimeToken:
    now = datetime.now(UTC)
    return OneTimeToken(
        id=token_id,
        user_id=uuid4(),
        purpose=purpose,
        token_hash="0" * 64,
        expires_at=expires_at or now + timedelta(hours=1),
        used_at=used_at,
        created_at=now,
    )


def test_token_email_is_deliverable_only_for_matching_active_token() -> None:
    now = datetime.now(UTC)
    token_id = uuid4()
    job = make_job(token_id=token_id)
    token = make_token(token_id, expires_at=now + timedelta(minutes=5))

    assert token_email_is_deliverable(job, token, now=now) is True
    assert token_email_is_deliverable(job, None, now=now) is False

    token.used_at = now
    assert token_email_is_deliverable(job, token, now=now) is False
    token.used_at = None
    token.expires_at = now
    assert token_email_is_deliverable(job, token, now=now) is False
    token.expires_at = now + timedelta(minutes=5)
    token.purpose = "password_reset"
    assert token_email_is_deliverable(job, token, now=now) is False


def test_apply_token_superseded_terminates_job_without_marking_sent() -> None:
    job = make_job(attempt_count=2)

    apply_token_superseded(job)

    assert job.status == "dead"
    assert job.attempt_count == 3
    assert job.locked_by is None
    assert job.locked_at is None
    assert job.sent_at is None
    assert job.last_error_code == "TOKEN_SUPERSEDED"
    assert job.last_error_summary == "一次性令牌已失效，邮件未投递。"


class RecordingSender:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def send(self, job: OutboxJob, secret_payload: dict[str, object]) -> None:
        self.calls.append(job.id)


class TokenProcessorHarness(OutboxProcessor):
    def __init__(self, job: OutboxJob, *, deliverable: bool) -> None:
        self._job = job
        self._deliverable = deliverable
        self._sender = RecordingSender()
        self.sent_ids: list[UUID] = []
        self.superseded_ids: list[UUID] = []
        self.failed_ids: list[UUID] = []

    async def _claim(self, now: datetime) -> list[OutboxJob]:
        return [self._job]

    async def _token_email_is_deliverable(self, job: OutboxJob, now: datetime) -> bool:
        return self._deliverable

    def _secret_payload(self, job: OutboxJob) -> dict[str, object]:
        return {"token": "opaque-test-token"}

    async def _mark_sent(self, job_id: UUID, now: datetime) -> None:
        self.sent_ids.append(job_id)

    async def _mark_token_superseded(self, job_id: UUID) -> None:
        self.superseded_ids.append(job_id)

    async def _mark_failed(
        self,
        job_id: UUID,
        *,
        now: datetime,
        code: str,
        permanent: bool,
    ) -> None:
        self.failed_ids.append(job_id)


@pytest.mark.asyncio
async def test_worker_skips_superseded_token_email_without_calling_sender() -> None:
    job = make_job()
    processor = TokenProcessorHarness(job, deliverable=False)

    assert await processor.run_once() == 1
    assert processor._sender.calls == []
    assert processor.superseded_ids == [job.id]
    assert processor.sent_ids == []
    assert processor.failed_ids == []


@pytest.mark.asyncio
async def test_worker_sends_current_token_email_once() -> None:
    job = make_job()
    processor = TokenProcessorHarness(job, deliverable=True)

    assert await processor.run_once() == 1
    assert processor._sender.calls == [job.id]
    assert processor.sent_ids == [job.id]
    assert processor.superseded_ids == []
    assert processor.failed_ids == []
