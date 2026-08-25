from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.assignments.models import Assignment, AssignmentExtension
from app.assignments.policy import can_submit_assignment
from app.assignments.schemas import AssignmentCreateRequest
from app.notifications.mailer import render_mail
from app.notifications.models import OutboxJob
from app.notifications.service import OutboxProcessor


def make_assignment(
    *,
    status: str,
    deadline: datetime,
    closed_at: datetime | None = None,
) -> Assignment:
    now = datetime.now(UTC)
    actor_id = uuid4()
    return Assignment(
        id=uuid4(),
        title="测试作业",
        description_markdown="说明",
        description_html="<p>说明</p>",
        training_url="https://example.invalid/training",
        submission_instructions="至少提交一种内容",
        status=status,
        all_students=True,
        audience_match="intersection",
        allowed_extensions=["pdf", "zip"],
        max_total_bytes=1024,
        publish_at=now - timedelta(hours=2),
        published_at=now - timedelta(hours=1),
        deadline=deadline,
        created_by=actor_id,
        updated_by=actor_id,
        closed_at=closed_at,
        archived_at=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_extension(assignment: Assignment, deadline: datetime) -> AssignmentExtension:
    now = datetime.now(UTC)
    return AssignmentExtension(
        assignment_id=assignment.id,
        user_id=uuid4(),
        extended_deadline=deadline,
        reason="仅管理员可见的理由",
        granted_by=uuid4(),
        created_at=now,
        updated_at=now,
        revision=1,
    )


def test_submit_policy_distinguishes_public_extension_automatic_and_early_close() -> None:
    now = datetime.now(UTC)
    published = make_assignment(
        status="published",
        deadline=now + timedelta(minutes=10),
    )
    assert can_submit_assignment(published, None, now)
    assert not can_submit_assignment(published, None, now + timedelta(minutes=11))

    automatic = make_assignment(
        status="closed",
        deadline=now - timedelta(minutes=1),
        closed_at=now - timedelta(minutes=1),
    )
    extension = make_extension(automatic, now + timedelta(hours=1))
    assert can_submit_assignment(automatic, extension, now)

    early = make_assignment(
        status="closed",
        deadline=now + timedelta(hours=1),
        closed_at=now,
    )
    assert not can_submit_assignment(
        early,
        make_extension(early, now + timedelta(hours=2)),
        now,
    )


def test_assignment_schema_normalizes_extensions_and_rejects_invalid_times() -> None:
    now = datetime.now(UTC)
    request = AssignmentCreateRequest(
        title="作业",
        description_markdown="说明",
        training_url="https://example.invalid/training",
        submission_instructions="提交说明",
        audience={"all_students": True},
        allowed_extensions=[".PDF", "zip"],
        max_total_bytes=1024,
        publish_at=now,
        deadline=now + timedelta(days=1),
    )
    assert request.allowed_extensions == ["pdf", "zip"]

    with pytest.raises(ValidationError):
        AssignmentCreateRequest(
            **{
                **request.model_dump(),
                "publish_at": now,
                "deadline": now,
            }
        )


def make_extension_mail_job() -> OutboxJob:
    now = datetime.now(UTC)
    return OutboxJob(
        id=uuid4(),
        job_type="assignment_extension_email",
        event_key=f"assignment-extension:{uuid4()}",
        payload={
            "recipient": "student@connect.hkust-gz.edu.cn",
            "full_name": "测试 <同学>",
            "assignment_id": str(uuid4()),
            "title": "作业 <script>alert(1)</script>",
            "extended_deadline": (now + timedelta(days=1)).isoformat(),
            "target_url": f"/assignments/{uuid4()}",
        },
        secret_payload_ciphertext=None,
        status="processing",
        available_at=now,
        attempt_count=0,
        max_attempts=8,
        locked_by="worker",
        locked_at=now,
        last_error_code=None,
        last_error_summary=None,
        created_at=now,
        sent_at=None,
    )


def test_extension_mail_uses_shanghai_time_and_contains_no_reason() -> None:
    rendered = render_mail(
        make_extension_mail_job(),
        {},
        app_base_url="https://training.example.invalid",
    )

    assert "Asia/Shanghai" in rendered.text
    assert "仅管理员可见的理由" not in rendered.text
    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html


class FakeAssignmentProcessor:
    def __init__(self) -> None:
        self.publish_calls: list[tuple[UUID, UUID]] = []
        self.close_calls: list[tuple[UUID, UUID]] = []

    async def publish(self, assignment_id: UUID, job_id: UUID) -> None:
        self.publish_calls.append((assignment_id, job_id))

    async def close(self, assignment_id: UUID, job_id: UUID) -> None:
        self.close_calls.append((assignment_id, job_id))


class AssignmentProcessorHarness(OutboxProcessor):
    def __init__(self, job: OutboxJob, processor: FakeAssignmentProcessor) -> None:
        self._job = job
        self._assignment_processor = processor
        self.sent_ids: list[UUID] = []
        self.failed_ids: list[UUID] = []

    async def _claim(self, now: datetime) -> list[OutboxJob]:
        return [self._job]

    async def _mark_sent(self, job_id: UUID, now: datetime) -> None:
        self.sent_ids.append(job_id)

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
@pytest.mark.parametrize("job_type", ["publish_assignment", "close_assignment"])
async def test_worker_dispatches_assignment_schedule_jobs(job_type: str) -> None:
    assignment_id = uuid4()
    job = make_extension_mail_job()
    job.job_type = job_type
    job.payload = {"assignment_id": str(assignment_id)}
    processor = FakeAssignmentProcessor()
    harness = AssignmentProcessorHarness(job, processor)

    assert await harness.run_once() == 1
    expected = [(assignment_id, job.id)]
    assert processor.publish_calls == (expected if job_type == "publish_assignment" else [])
    assert processor.close_calls == (expected if job_type == "close_assignment" else [])
    assert harness.sent_ids == [job.id]
    assert harness.failed_ids == []
