from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.models import Assignment, AssignmentAudienceUser, AssignmentExtension
from app.assignments.policy import can_submit_assignment
from app.assignments.repository import AssignmentRepository, AssignmentStats
from app.assignments.schemas import (
    AssignmentCreateRequest,
    AssignmentPatchRequest,
)
from app.assignments.service import AssignmentAuditContext, AssignmentService
from app.auth.service import AuthenticatedContext
from app.core.errors import ApplicationError
from app.notifications.mailer import render_mail
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.notifications.service import OutboxProcessor
from app.users.models import User


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
        deleted_at=None,
        updated_at=now,
        revision=1,
    )


def make_patch_request(
    assignment: Assignment,
    *,
    deadline: datetime | None = None,
    title: str | None = None,
    audience: dict[str, object] | None = None,
) -> AssignmentPatchRequest:
    return AssignmentPatchRequest(
        revision=assignment.revision,
        title=title or assignment.title,
        description_markdown=assignment.description_markdown,
        training_url=assignment.training_url,
        submission_instructions=assignment.submission_instructions,
        audience=audience or {"all_students": True},
        allowed_extensions=list(assignment.allowed_extensions),
        max_total_bytes=assignment.max_total_bytes,
        publish_at=assignment.publish_at,
        deadline=deadline or assignment.deadline,
    )


def make_patch_service(
    assignment: Assignment,
    *,
    now: datetime,
    last_submitted_at: datetime | None,
) -> tuple[AssignmentService, AsyncMock, SimpleNamespace, SimpleNamespace, Mock]:
    session = AsyncMock(spec=AsyncSession)
    service = AssignmentService(cast(AsyncSession, session), clock=lambda: now)
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=assignment),
        audience_ids=AsyncMock(return_value=(set(), set())),
        replace_audience=AsyncMock(),
        replace_audience_snapshot=AsyncMock(return_value=(0, 0)),
        last_submitted_at=AsyncMock(return_value=last_submitted_at),
        actual_audience_count=AsyncMock(return_value=1),
        stats=AsyncMock(
            return_value=AssignmentStats(
                target_count=1,
                submitted_count=1 if last_submitted_at is not None else 0,
                completed_count=0,
                feedback_submission_count=0,
                last_submitted_at=last_submitted_at,
            )
        ),
    )
    outbox = SimpleNamespace(
        get_by_event_key=AsyncMock(return_value=None),
        add=Mock(),
    )
    audit_repository = Mock()
    service._assignments = cast(AssignmentRepository, repository)
    service._outbox = cast(OutboxRepository, outbox)
    service._audit = audit_repository
    return service, session, repository, outbox, audit_repository


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


@pytest.mark.asyncio
async def test_patch_published_assignment_allows_safe_deadline_shortening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    assignment = make_assignment(
        status="published",
        deadline=now + timedelta(days=2),
    )
    new_deadline = now + timedelta(days=1)
    last_submitted_at = now + timedelta(hours=12)
    service, session, repository, outbox, audit_repository = make_patch_service(
        assignment,
        now=now,
        last_submitted_at=last_submitted_at,
    )
    monkeypatch.setattr(
        "app.assignments.service.validate_audience",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.assignments.service.active_students_for_audience",
        AsyncMock(return_value=[]),
    )
    admin = cast(User, SimpleNamespace(id=uuid4()))

    response = await service.patch(
        assignment.id,
        make_patch_request(assignment, deadline=new_deadline, title="修正后的作业"),
        audit=AssignmentAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="update-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert response.title == "修正后的作业"
    assert assignment.title == "修正后的作业"
    assert assignment.deadline == new_deadline
    assert assignment.revision == 2
    repository.last_submitted_at.assert_awaited_once_with(assignment.id)
    session.commit.assert_awaited_once()
    close_job = outbox.add.call_args.args[0]
    assert close_job.job_type == "close_assignment"
    assert close_job.available_at == new_deadline
    audit = audit_repository.add.call_args.args[0]
    assert audit.change_summary["changed_fields"] == ["title", "deadline"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["published", "closed"])
async def test_patch_existing_assignment_replaces_current_audience_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    now = datetime.now(UTC)
    assignment = make_assignment(
        status=status,
        deadline=now + timedelta(days=2),
        closed_at=now if status == "closed" else None,
    )
    service, session, repository, _outbox, audit_repository = make_patch_service(
        assignment,
        now=now,
        last_submitted_at=None,
    )
    direction_id = uuid4()
    target_users = [
        cast(User, SimpleNamespace(id=uuid4(), cohort_id=None, direction_id=direction_id))
    ]
    monkeypatch.setattr("app.assignments.service.validate_audience", AsyncMock())
    monkeypatch.setattr(
        "app.assignments.service.active_students_for_audience",
        AsyncMock(return_value=target_users),
    )
    repository.replace_audience_snapshot.return_value = (1, 2)
    repository.audience_ids.side_effect = [
        (set(), set()),
        (set(), {direction_id}),
    ]
    admin = cast(User, SimpleNamespace(id=uuid4()))

    await service.patch(
        assignment.id,
        make_patch_request(
            assignment,
            audience={
                "all_students": False,
                "direction_ids": [direction_id],
                "match": "intersection",
            },
        ),
        audit=AssignmentAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="audience-update-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert not assignment.all_students
    repository.replace_audience.assert_awaited_once_with(
        assignment.id,
        cohort_ids=[],
        direction_ids=[direction_id],
    )
    repository.replace_audience_snapshot.assert_awaited_once_with(
        assignment_id=assignment.id,
        users=target_users,
        created_at=now,
    )
    audit = audit_repository.add.call_args.args[0]
    assert audit.change_summary == {
        "changed_fields": ["audience"],
        "audience_added": 1,
        "audience_removed": 2,
        "audience_target_count": 1,
    }
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_published_assignment_rejects_deadline_before_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    assignment = make_assignment(
        status="published",
        deadline=now + timedelta(days=2),
    )
    last_submitted_at = now + timedelta(hours=36)
    service, session, repository, outbox, _audit = make_patch_service(
        assignment,
        now=now,
        last_submitted_at=last_submitted_at,
    )
    monkeypatch.setattr(
        "app.assignments.service.validate_audience",
        AsyncMock(),
    )
    admin = cast(User, SimpleNamespace(id=uuid4()))

    with pytest.raises(ApplicationError) as exc_info:
        await service.patch(
            assignment.id,
            make_patch_request(assignment, deadline=now + timedelta(days=1)),
            audit=AssignmentAuditContext(
                actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
                request_id="rejected-update-request",
                ip_prefix="127.0.0.0/24",
            ),
        )

    assert exc_info.value.code == "STATE_CONFLICT"
    assert exc_info.value.message == "截止时间不能早于已有正式提交时间。"
    assert assignment.deadline == now + timedelta(days=2)
    assert assignment.title == "测试作业"
    assert assignment.revision == 1
    repository.last_submitted_at.assert_awaited_once_with(assignment.id)
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    outbox.add.assert_not_called()


@pytest.mark.asyncio
async def test_patch_automatically_closed_assignment_reopens_only_for_future_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    old_deadline = now - timedelta(days=1)
    assignment = make_assignment(
        status="closed",
        deadline=old_deadline,
        closed_at=old_deadline,
    )
    new_deadline = now + timedelta(days=1)
    service, session, _repository, outbox, _audit = make_patch_service(
        assignment,
        now=now,
        last_submitted_at=old_deadline,
    )
    monkeypatch.setattr("app.assignments.service.validate_audience", AsyncMock())
    monkeypatch.setattr(
        "app.assignments.service.active_students_for_audience",
        AsyncMock(return_value=[]),
    )
    admin = cast(User, SimpleNamespace(id=uuid4()))

    response = await service.patch(
        assignment.id,
        make_patch_request(assignment, deadline=new_deadline),
        audit=AssignmentAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="reopen-update-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert response.status == "published"
    assert assignment.closed_at is None
    close_job = outbox.add.call_args.args[0]
    assert close_job.available_at == new_deadline
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_early_closed_assignment_keeps_manual_close_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    assignment = make_assignment(
        status="closed",
        deadline=now + timedelta(days=2),
        closed_at=now - timedelta(hours=1),
    )
    new_deadline = now + timedelta(days=3)
    service, session, _repository, outbox, _audit = make_patch_service(
        assignment,
        now=now,
        last_submitted_at=now - timedelta(hours=2),
    )
    monkeypatch.setattr("app.assignments.service.validate_audience", AsyncMock())
    monkeypatch.setattr(
        "app.assignments.service.active_students_for_audience",
        AsyncMock(return_value=[]),
    )
    admin = cast(User, SimpleNamespace(id=uuid4()))

    response = await service.patch(
        assignment.id,
        make_patch_request(assignment, deadline=new_deadline),
        audit=AssignmentAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="closed-update-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert response.status == "closed"
    assert assignment.closed_at == now - timedelta(hours=1)
    outbox.add.assert_not_called()
    session.commit.assert_awaited_once()


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


class CapturingSession:
    def __init__(self) -> None:
        self.statement: Select[tuple[bool]] | None = None

    async def scalar(self, statement: Select[tuple[bool]]) -> bool:
        self.statement = statement
        return True


class CapturingAudienceEnrollmentSession:
    def __init__(self, assignment_id: UUID) -> None:
        self.assignment_id = assignment_id
        self.statement: Select[tuple[UUID]] | None = None
        self.added: list[AssignmentAudienceUser] = []

    async def scalars(self, statement: Select[tuple[UUID]]) -> SimpleNamespace:
        self.statement = statement
        return SimpleNamespace(all=lambda: [self.assignment_id])

    def add_all(self, records: list[AssignmentAudienceUser]) -> None:
        self.added.extend(records)


@pytest.mark.asyncio
async def test_new_student_is_added_to_matching_open_assignment_snapshots() -> None:
    now = datetime(2026, 8, 27, 6, 30, tzinfo=UTC)
    assignment_id = uuid4()
    user = cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            cohort_id=None,
            direction_id=uuid4(),
        ),
    )
    session = CapturingAudienceEnrollmentSession(assignment_id)
    repository = AssignmentRepository(cast(AsyncSession, session))

    added = await repository.add_open_assignment_audiences_for_student(
        user=user,
        created_at=now,
    )

    assert added == 1
    assert session.statement is not None
    sql = str(session.statement)
    assert "assignments.status" in sql
    assert "assignments.deadline" in sql
    assert "assignment_audience_users" in sql
    assert "NOT (EXISTS" in sql
    assert len(session.added) == 1
    assert session.added[0].assignment_id == assignment_id
    assert session.added[0].user_id == user.id
    assert session.added[0].created_at == now


@pytest.mark.asyncio
async def test_student_view_preview_uses_live_audience_without_changing_snapshot() -> None:
    session = CapturingSession()
    repository = AssignmentRepository(cast(AsyncSession, session))
    preview_user = cast(
        User,
        SimpleNamespace(cohort_id=None, direction_id=uuid4()),
    )

    await repository.is_audience_user(
        uuid4(),
        uuid4(),
        preview_user=preview_user,
    )
    assert session.statement is not None
    preview_sql = str(session.statement)
    assert "assignment_audience_users" in preview_sql
    assert "assignment_directions" in preview_sql

    await repository.is_audience_user(uuid4(), uuid4())
    assert session.statement is not None
    snapshot_sql = str(session.statement)
    assert "assignment_audience_users" in snapshot_sql
    assert "assignment_directions" not in snapshot_sql


@pytest.mark.asyncio
async def test_admin_submission_query_includes_current_audience_and_historical_submitters() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 0
    rows = Mock()
    rows.all.return_value = []
    session.execute.return_value = rows
    repository = AssignmentRepository(cast(AsyncSession, session))

    records, total = await repository.submissions_for_admin(
        uuid4(),
        page=1,
        page_size=100,
        cohort_id=None,
        direction_id=None,
        submission_status=None,
        feedback_status=None,
    )

    assert records == []
    assert total == 0
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "LEFT OUTER JOIN assignment_audience_users" in sql
    assert "LEFT OUTER JOIN submissions" in sql
    assert "assignment_audience_users.user_id IS NOT NULL OR submissions.id IS NOT NULL" in sql


@pytest.mark.asyncio
async def test_replace_audience_snapshot_reports_added_and_removed_users() -> None:
    assignment_id = uuid4()
    retained_user_id = uuid4()
    removed_user_id = uuid4()
    added_user_id = uuid4()
    created_at = datetime.now(UTC)
    session = AsyncMock(spec=AsyncSession)
    existing = Mock()
    existing.all.return_value = [retained_user_id, removed_user_id]
    session.scalars.return_value = existing
    repository = AssignmentRepository(cast(AsyncSession, session))
    users = [
        cast(
            User,
            SimpleNamespace(id=retained_user_id, cohort_id=None, direction_id=None),
        ),
        cast(
            User,
            SimpleNamespace(id=added_user_id, cohort_id=None, direction_id=None),
        ),
    ]

    result = await repository.replace_audience_snapshot(
        assignment_id=assignment_id,
        users=users,
        created_at=created_at,
    )

    assert result == (1, 1)
    delete_sql = str(session.execute.await_args.args[0])
    assert "DELETE FROM assignment_audience_users" in delete_sql
    snapshots = session.add_all.call_args.args[0]
    assert {snapshot.user_id for snapshot in snapshots} == {
        retained_user_id,
        added_user_id,
    }
    assert all(snapshot.assignment_id == assignment_id for snapshot in snapshots)
    assert all(snapshot.created_at == created_at for snapshot in snapshots)


@pytest.mark.asyncio
async def test_assignment_stats_count_only_current_audience_submissions_and_feedback() -> None:
    assignment_id = uuid4()
    last_submitted_at = datetime.now(UTC)
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [2, 1, 0, 1, last_submitted_at]
    repository = AssignmentRepository(cast(AsyncSession, session))

    stats = await repository.stats(assignment_id)

    assert stats == AssignmentStats(
        target_count=2,
        submitted_count=1,
        completed_count=0,
        feedback_submission_count=1,
        last_submitted_at=last_submitted_at,
    )
    submitted_sql = str(session.scalar.await_args_list[1].args[0])
    feedback_sql = str(session.scalar.await_args_list[3].args[0])
    assert "JOIN assignment_audience_users" in submitted_sql
    assert "assignment_audience_users.user_id = submissions.owner_user_id" in submitted_sql
    assert "JOIN assignment_audience_users" in feedback_sql
    assert "assignment_audience_users.user_id = submissions.owner_user_id" in feedback_sql


@pytest.mark.asyncio
async def test_student_assignment_queries_exclude_archived_resources() -> None:
    session = AsyncMock(spec=AsyncSession)
    rows = Mock()
    rows.all.return_value = []
    session.execute.return_value = rows
    session.scalar.return_value = 0
    repository = AssignmentRepository(cast(AsyncSession, session))

    await repository.list_for_student(
        user_id=uuid4(),
        page=1,
        page_size=20,
        status=None,
        query=None,
        now=datetime.now(UTC),
    )

    statement = session.execute.await_args.args[0]
    assert "assignments.status IN" in str(statement)
    assert "assignments.status !=" not in str(statement)


@pytest.mark.asyncio
async def test_repository_hides_deleted_assignments_from_regular_reads() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = AssignmentRepository(cast(AsyncSession, session))
    assignment_id = uuid4()

    await repository.get_by_id(assignment_id)
    detail_sql = str(session.scalar.await_args.args[0])
    assert "assignments.deleted_at IS NULL" in detail_sql

    session.scalar.reset_mock()
    await repository.get_by_id(assignment_id, include_deleted=True)
    delete_sql = str(session.scalar.await_args.args[0])
    assert "assignments.deleted_at IS NULL" not in delete_sql

    rows = Mock()
    rows.all.return_value = []
    session.scalar.return_value = 0
    session.scalars.return_value = rows
    await repository.list_admin(
        page=1,
        page_size=20,
        status=None,
        query=None,
    )
    count_sql = str(session.scalar.await_args.args[0])
    items_sql = str(session.scalars.await_args.args[0])
    assert "assignments.deleted_at IS NULL" in count_sql
    assert "assignments.deleted_at IS NULL" in items_sql


@pytest.mark.asyncio
async def test_remove_draft_assignment_deletes_record_and_active_schedule() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = AssignmentService(cast(AsyncSession, session))
    assignment = make_assignment(
        status="draft",
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    assignment.published_at = None
    admin = cast(User, SimpleNamespace(id=uuid4()))
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=assignment),
        delete=AsyncMock(),
    )
    outbox = SimpleNamespace(delete_active_by_event_key=AsyncMock())
    audit_repository = Mock()
    service._assignments = cast(AssignmentRepository, repository)
    service._outbox = cast(OutboxRepository, outbox)
    service._audit = audit_repository

    await service.remove(
        assignment.id,
        audit=AssignmentAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="delete-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    outbox.delete_active_by_event_key.assert_awaited_once_with(
        f"assignment:{assignment.id}:publish"
    )
    repository.delete.assert_awaited_once_with(assignment)
    session.commit.assert_awaited_once()
    audit = audit_repository.add.call_args.args[0]
    assert audit.action == "assignment.delete"
    assert audit.change_summary["deletion_mode"] == "physical"


@pytest.mark.asyncio
async def test_remove_published_assignment_archives_and_hides_excellent_work_from_student() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = AssignmentService(cast(AsyncSession, session))
    assignment = make_assignment(
        status="published",
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    admin = cast(User, SimpleNamespace(id=uuid4()))
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=assignment),
        delete=AsyncMock(),
        is_audience_user=AsyncMock(return_value=True),
    )
    service._assignments = cast(AssignmentRepository, repository)
    service._audit = Mock()

    await service.remove(
        assignment.id,
        audit=AssignmentAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="delete-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert assignment.status == "archived"
    assert assignment.deleted_at == assignment.archived_at
    repository.delete.assert_not_awaited()
    session.commit.assert_awaited_once()

    student_context = cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4(), role="student"),
            is_admin=False,
            is_student_view=False,
        ),
    )
    with pytest.raises(ApplicationError) as exc_info:
        await service.list_excellent(assignment.id, context=student_context)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_remove_manually_archived_assignment_sets_deleted_marker() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = AssignmentService(cast(AsyncSession, session))
    assignment = make_assignment(
        status="archived",
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    assignment.archived_at = datetime.now(UTC)
    admin = cast(User, SimpleNamespace(id=uuid4()))
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=assignment),
        delete=AsyncMock(),
    )
    audit_repository = Mock()
    service._assignments = cast(AssignmentRepository, repository)
    service._audit = audit_repository

    await service.remove(
        assignment.id,
        audit=AssignmentAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="archived-delete-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    repository.get_by_id.assert_awaited_once_with(
        assignment.id, for_update=True, include_deleted=True
    )
    repository.delete.assert_not_awaited()
    assert assignment.deleted_at is not None
    assert assignment.updated_by == admin.id
    assert assignment.revision == 2
    audit = audit_repository.add.call_args.args[0]
    assert audit.action == "assignment.delete"
    assert audit.change_summary == {
        "previous_status": "archived",
        "deletion_mode": "archive",
    }
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_deleted_assignment_is_idempotent() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = AssignmentService(cast(AsyncSession, session))
    assignment = make_assignment(
        status="archived",
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    assignment.archived_at = datetime.now(UTC)
    assignment.deleted_at = assignment.archived_at
    admin = cast(User, SimpleNamespace(id=uuid4()))
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=assignment),
        delete=AsyncMock(),
    )
    audit_repository = Mock()
    service._assignments = cast(AssignmentRepository, repository)
    service._audit = audit_repository

    await service.remove(
        assignment.id,
        audit=AssignmentAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="repeat-delete-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    repository.get_by_id.assert_awaited_once_with(
        assignment.id, for_update=True, include_deleted=True
    )
    repository.delete.assert_not_awaited()
    audit_repository.add.assert_not_called()
    session.commit.assert_awaited_once()
