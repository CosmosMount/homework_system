from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements import service as announcement_service_module
from app.announcements.models import Announcement
from app.announcements.repository import AnnouncementRepository
from app.announcements.schemas import AnnouncementAudience
from app.announcements.service import AnnouncementAuditContext, AnnouncementService
from app.auth.service import AuthenticatedContext
from app.core.errors import ApplicationError
from app.notifications.mailer import render_mail
from app.notifications.models import OutboxJob
from app.notifications.repository import (
    NotificationUnreadCounts,
    OutboxRepository,
    StudentNotificationRepository,
)
from app.notifications.service import OutboxProcessor
from app.uploads.object_store import ObjectInspection
from app.uploads.service import FileValidationError, detect_media_type, normalize_file_name
from app.users.models import User


def make_announcement(
    *,
    all_students: bool,
    audience_match: str = "intersection",
) -> Announcement:
    now = datetime.now(UTC)
    actor_id = uuid4()
    return Announcement(
        id=uuid4(),
        title="测试通知",
        summary="测试摘要",
        body_markdown="正文",
        body_html="<p>正文</p>",
        status="published",
        all_students=all_students,
        audience_match=audience_match,
        publish_at=now,
        published_at=now,
        pinned_until=None,
        send_email=True,
        created_by=actor_id,
        updated_by=actor_id,
        archived_at=None,
        created_at=now,
        deleted_at=None,
        updated_at=now,
        revision=1,
    )


def make_student(
    *,
    cohort_id: UUID | None,
    direction_id: UUID | None,
) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email="student@connect.hkust-gz.edu.cn",
        email_normalized="student@connect.hkust-gz.edu.cn",
        student_number=str(uuid4()),
        full_name="测试学生",
        password_hash="argon2id",
        role="student",
        status="active",
        cohort_id=cohort_id,
        direction_id=direction_id,
        email_verified_at=now,
        disabled_at=None,
        disabled_by=None,
        disabled_reason=None,
        password_changed_at=now,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def test_audience_matching_covers_all_union_intersection_and_unclassified() -> None:
    cohort_id = uuid4()
    direction_id = uuid4()
    other_direction_id = uuid4()

    assert AnnouncementService._audience_matches(
        make_announcement(all_students=True),
        make_student(cohort_id=None, direction_id=None),
        set(),
        set(),
    )
    assert AnnouncementService._audience_matches(
        make_announcement(all_students=False, audience_match="union"),
        make_student(cohort_id=cohort_id, direction_id=None),
        {cohort_id},
        {direction_id},
    )
    assert not AnnouncementService._audience_matches(
        make_announcement(all_students=False, audience_match="intersection"),
        make_student(cohort_id=cohort_id, direction_id=other_direction_id),
        {cohort_id},
        {direction_id},
    )
    assert AnnouncementService._audience_matches(
        make_announcement(all_students=False, audience_match="intersection"),
        make_student(cohort_id=cohort_id, direction_id=None),
        {cohort_id},
        set(),
    )
    assert not AnnouncementService._audience_matches(
        make_announcement(all_students=False, audience_match="union"),
        make_student(cohort_id=None, direction_id=None),
        {cohort_id},
        {direction_id},
    )


@pytest.mark.asyncio
async def test_dashboard_includes_published_assignment_for_admin_student_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    user = make_student(cohort_id=None, direction_id=None)
    user.role = "admin"
    assignment_id = uuid4()
    assignment_record = SimpleNamespace(
        assignment=SimpleNamespace(
            id=assignment_id,
            title="电控第一次作业",
            deadline=datetime(2026, 9, 3, 14, 9, tzinfo=UTC),
        ),
        extension=None,
    )
    assignment_repository = SimpleNamespace(
        list_for_student=AsyncMock(return_value=([assignment_record], 1)),
    )
    competition_repository = SimpleNamespace(
        dashboard_competitions=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        announcement_service_module,
        "AssignmentRepository",
        lambda _session: assignment_repository,
    )
    monkeypatch.setattr(
        announcement_service_module,
        "CompetitionRepository",
        lambda _session: competition_repository,
    )
    service = AnnouncementService(
        cast(AsyncSession, SimpleNamespace()),
        clock=lambda: now,
    )
    service._announcements = cast(
        AnnouncementRepository,
        SimpleNamespace(
            list_for_student=AsyncMock(return_value=([], 0)),
            unread_target_ids=AsyncMock(return_value=set()),
            announcement_ids_with_attachments=AsyncMock(return_value=set()),
        ),
    )
    service._notifications = cast(
        StudentNotificationRepository,
        SimpleNamespace(
            unread_counts=AsyncMock(
                return_value=NotificationUnreadCounts(
                    announcements=1,
                    assignments=2,
                    competitions=3,
                    help_requests=4,
                )
            )
        ),
    )
    context = cast(
        AuthenticatedContext,
        SimpleNamespace(user=user, effective_role="student", is_student_view=True),
    )

    result = await service.dashboard(context=context)

    assert [(item.id, item.title) for item in result.assignments] == [
        (assignment_id, "电控第一次作业"),
    ]
    assert result.unread_count == 10
    assert result.unread_counts.announcements == 1
    assert result.unread_counts.help_requests == 4
    assignment_repository.list_for_student.assert_awaited_once_with(
        user_id=user.id,
        preview_user=user,
        page=1,
        page_size=5,
        status=None,
        query=None,
        now=now,
        limit=5,
    )


@pytest.mark.asyncio
async def test_unread_counts_are_grouped_and_exclude_inactive_announcements() -> None:
    session = AsyncMock(spec=AsyncSession)
    query_result = Mock()
    query_result.one.return_value = (2, 3, 4, 5)
    session.execute.return_value = query_result
    repository = StudentNotificationRepository(cast(AsyncSession, session))

    counts = await repository.unread_counts(uuid4())

    assert counts.total == 14
    assert counts.announcements == 2
    assert counts.assignments == 3
    assert counts.competitions == 4
    assert counts.help_requests == 5
    statement = str(session.execute.await_args.args[0])
    assert "LEFT OUTER JOIN announcements" in statement
    assert "announcements.status" in statement
    assert "student_notifications.read_at IS NULL" in statement


@pytest.mark.parametrize(
    "payload",
    [
        {
            "all_students": True,
            "cohort_ids": [uuid4()],
            "direction_ids": [],
            "match": "intersection",
        },
        {
            "all_students": False,
            "cohort_ids": [],
            "direction_ids": [],
            "match": "intersection",
        },
    ],
)
def test_audience_schema_rejects_inconsistent_selection(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AnnouncementAudience.model_validate(payload)


def make_announcement_mail_job(job_type: str) -> OutboxJob:
    now = datetime.now(UTC)
    return OutboxJob(
        id=uuid4(),
        job_type=job_type,
        event_key=f"{job_type}:{uuid4()}",
        payload={
            "recipient": "student@connect.hkust-gz.edu.cn",
            "full_name": "测试 <同学>",
            "announcement_id": str(uuid4()),
            "title": "重要 <script>alert(1)</script>",
            "summary": "请查看 & 确认",
            "target_url": f"/announcements/{uuid4()}",
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


@pytest.mark.parametrize(
    "job_type",
    ["announcement_email", "announcement_update_email"],
)
def test_announcement_mail_escapes_user_content_and_contains_no_attachment_url(
    job_type: str,
) -> None:
    rendered = render_mail(
        make_announcement_mail_job(job_type),
        {},
        app_base_url="https://training.example.invalid",
    )

    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html
    assert "https://training.example.invalid/announcements/" in rendered.text
    assert "/storage/" not in rendered.text
    assert "/storage/" not in rendered.html


def test_file_name_and_signature_validation_rejects_active_or_mismatched_files() -> None:
    with pytest.raises(FileValidationError):
        normalize_file_name("notice.pdf.exe")
    with pytest.raises(FileValidationError):
        normalize_file_name("../notice.pdf")
    with pytest.raises(FileValidationError):
        detect_media_type(
            "pdf",
            ObjectInspection(
                size_bytes=4,
                sha256="0" * 64,
                first_bytes=b"MZ\x00\x00",
                content_type="application/pdf",
            ),
        )

    file_name, extension = normalize_file_name("training-notice.pdf")
    detected = detect_media_type(
        extension,
        ObjectInspection(
            size_bytes=8,
            sha256="0" * 64,
            first_bytes=b"%PDF-1.7",
            content_type="application/pdf",
        ),
    )
    assert file_name == "training-notice.pdf"
    assert extension == "pdf"
    assert detected == "application/pdf"


class FakePublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def publish(self, announcement_id: UUID, job_id: UUID) -> None:
        self.calls.append((announcement_id, job_id))


class ProcessorHarness(OutboxProcessor):
    def __init__(self, job: OutboxJob, publisher: FakePublisher) -> None:
        self._test_job = job
        self._announcement_publisher = publisher
        self.sent_ids: list[UUID] = []
        self.failed_ids: list[UUID] = []

    async def _claim(self, now: datetime) -> list[OutboxJob]:
        return [self._test_job]

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
async def test_worker_dispatches_scheduled_publication_without_using_mail_sender() -> None:
    announcement_id = uuid4()
    job = make_announcement_mail_job("publish_announcement")
    job.payload = {"announcement_id": str(announcement_id)}
    publisher = FakePublisher()
    processor = ProcessorHarness(job, publisher)

    processed = await processor.run_once()

    assert processed == 1
    assert publisher.calls == [(announcement_id, job.id)]
    assert processor.sent_ids == [job.id]
    assert processor.failed_ids == []


@pytest.mark.asyncio
async def test_archive_refreshes_server_updated_fields_after_commit() -> None:
    session = AsyncMock()
    service = AnnouncementService(session)
    announcement = make_announcement(all_students=True)
    admin = make_student(cohort_id=None, direction_id=None)
    admin.role = "admin"
    student = make_student(cohort_id=None, direction_id=None)

    repository = Mock()
    repository.get_by_id = AsyncMock(return_value=announcement)
    repository.audience_ids = AsyncMock(return_value=(set(), set()))
    repository.attachment_file_ids = AsyncMock(return_value=[])
    repository.audience_users = AsyncMock(return_value=[student])
    repository.published_recipient_count = AsyncMock(return_value=1)
    service._announcements = repository
    service._audit = Mock()
    unread_notifications = [SimpleNamespace(read_at=None), SimpleNamespace(read_at=None)]
    unread_for_target = AsyncMock(return_value=unread_notifications)
    service._notifications = cast(
        StudentNotificationRepository,
        SimpleNamespace(unread_for_target=unread_for_target),
    )

    result = await service.archive(
        announcement.id,
        audit=AnnouncementAuditContext(
            actor=cast(
                AuthenticatedContext,
                SimpleNamespace(user=admin),
            ),
            request_id="request-id",
            ip_prefix="127.0.0.0/24",
        ),
    )

    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(announcement)
    assert result.status == "archived"
    assert result.actual_recipient_count == 1
    unread_for_target.assert_awaited_once_with(
        target_type="announcement",
        target_id=announcement.id,
        for_update=True,
    )
    assert all(item.read_at == announcement.archived_at for item in unread_notifications)


@pytest.mark.asyncio
async def test_repository_hides_deleted_announcements_from_regular_reads() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = AnnouncementRepository(cast(AsyncSession, session))
    announcement_id = uuid4()

    await repository.get_by_id(announcement_id)
    detail_sql = str(session.scalar.await_args.args[0])
    assert "announcements.deleted_at IS NULL" in detail_sql

    session.scalar.reset_mock()
    await repository.get_by_id(announcement_id, include_deleted=True)
    delete_sql = str(session.scalar.await_args.args[0])
    assert "announcements.deleted_at IS NULL" not in delete_sql

    rows = Mock()
    rows.all.return_value = []
    session.scalar.return_value = 0
    session.scalars.return_value = rows
    await repository.list_for_admin(
        page=1,
        page_size=20,
        status=None,
        query=None,
    )
    count_sql = str(session.scalar.await_args.args[0])
    items_sql = str(session.scalars.await_args.args[0])
    assert "announcements.deleted_at IS NULL" in count_sql
    assert "announcements.deleted_at IS NULL" in items_sql


@pytest.mark.asyncio
async def test_remove_draft_deletes_record_and_active_schedule_in_one_commit() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = AnnouncementService(cast(AsyncSession, session))
    announcement = make_announcement(all_students=True)
    announcement.status = "draft"
    announcement.published_at = None
    admin = make_student(cohort_id=None, direction_id=None)
    admin.role = "admin"
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=announcement),
        delete=AsyncMock(),
    )
    outbox = SimpleNamespace(delete_active_by_event_key=AsyncMock())
    audit_repository = Mock()
    service._announcements = cast(AnnouncementRepository, repository)
    service._outbox = cast(OutboxRepository, outbox)
    service._audit = audit_repository

    await service.remove(
        announcement.id,
        audit=AnnouncementAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="delete-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    repository.get_by_id.assert_awaited_once_with(
        announcement.id, for_update=True, include_deleted=True
    )
    outbox.delete_active_by_event_key.assert_awaited_once_with(
        f"announcement:{announcement.id}:publish"
    )
    repository.delete.assert_awaited_once_with(announcement)
    session.commit.assert_awaited_once()
    audit = audit_repository.add.call_args.args[0]
    assert audit.action == "announcement.delete"
    assert audit.change_summary == {
        "previous_status": "draft",
        "deletion_mode": "physical",
    }


@pytest.mark.asyncio
async def test_remove_published_archives_and_student_detail_becomes_not_found() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = AnnouncementService(cast(AsyncSession, session))
    announcement = make_announcement(all_students=True)
    admin = make_student(cohort_id=None, direction_id=None)
    admin.role = "admin"
    student = make_student(cohort_id=None, direction_id=None)
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=announcement),
        delete=AsyncMock(),
    )
    unread = [SimpleNamespace(read_at=None)]
    notifications = SimpleNamespace(unread_for_target=AsyncMock(return_value=unread))
    service._announcements = cast(AnnouncementRepository, repository)
    service._notifications = cast(StudentNotificationRepository, notifications)
    service._audit = Mock()

    await service.remove(
        announcement.id,
        audit=AnnouncementAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="delete-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    assert announcement.status == "archived"
    assert announcement.deleted_at == announcement.archived_at
    assert unread[0].read_at == announcement.archived_at
    repository.delete.assert_not_awaited()
    session.commit.assert_awaited_once()

    with pytest.raises(ApplicationError) as exc_info:
        await service.get_student(
            announcement.id,
            context=cast(AuthenticatedContext, SimpleNamespace(user=student)),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_remove_manually_archived_announcement_sets_deleted_marker() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = AnnouncementService(cast(AsyncSession, session))
    announcement = make_announcement(all_students=True)
    announcement.status = "archived"
    announcement.archived_at = datetime.now(UTC)
    admin = make_student(cohort_id=None, direction_id=None)
    admin.role = "admin"
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=announcement),
        delete=AsyncMock(),
    )
    audit_repository = Mock()
    service._announcements = cast(AnnouncementRepository, repository)
    service._audit = audit_repository

    await service.remove(
        announcement.id,
        audit=AnnouncementAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="archived-delete-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    repository.get_by_id.assert_awaited_once_with(
        announcement.id, for_update=True, include_deleted=True
    )
    repository.delete.assert_not_awaited()
    assert announcement.deleted_at is not None
    assert announcement.updated_by == admin.id
    assert announcement.revision == 2
    audit = audit_repository.add.call_args.args[0]
    assert audit.action == "announcement.delete"
    assert audit.change_summary == {
        "previous_status": "archived",
        "deletion_mode": "archive",
    }
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_deleted_announcement_is_idempotent() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = AnnouncementService(cast(AsyncSession, session))
    announcement = make_announcement(all_students=True)
    announcement.status = "archived"
    announcement.archived_at = datetime.now(UTC)
    announcement.deleted_at = announcement.archived_at
    admin = make_student(cohort_id=None, direction_id=None)
    admin.role = "admin"
    repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=announcement),
        delete=AsyncMock(),
    )
    audit_repository = Mock()
    service._announcements = cast(AnnouncementRepository, repository)
    service._audit = audit_repository

    await service.remove(
        announcement.id,
        audit=AnnouncementAuditContext(
            actor=cast(AuthenticatedContext, SimpleNamespace(user=admin)),
            request_id="repeat-delete-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    repository.get_by_id.assert_awaited_once_with(
        announcement.id, for_update=True, include_deleted=True
    )
    repository.delete.assert_not_awaited()
    audit_repository.add.assert_not_called()
    session.commit.assert_awaited_once()
