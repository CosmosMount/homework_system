from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.repository import AssignmentRepository
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.notifications.mailer import render_mail
from app.notifications.repository import OutboxRepository, StudentNotificationRepository
from app.submissions.models import Submission
from app.submissions.repository import SubmissionRepository
from app.submissions.schemas import FeedbackPutRequest, SubmissionVersionCreateRequest
from app.submissions.service import SubmissionAuditContext, SubmissionService
from app.uploads.models import StoredFile
from app.uploads.object_store import MinioObjectStore
from app.uploads.repository import UploadRepository
from app.uploads.service import UploadService
from app.users.repository import UserRepository


def make_available_file(*, owner_user_id: object, size_bytes: int = 700) -> StoredFile:
    now = datetime.now(UTC)
    return StoredFile(
        id=uuid4(),
        owner_user_id=owner_user_id,
        purpose="assignment_submission",
        object_key=f"objects/{uuid4()}",
        original_name="solution.pdf",
        extension="pdf",
        declared_media_type="application/pdf",
        detected_media_type="application/pdf",
        size_bytes=size_bytes,
        sha256="a" * 64,
        status="available",
        created_at=now,
        available_at=now,
        deleted_at=None,
    )


def test_submission_schema_requires_content_and_rejects_duplicates_or_unsafe_urls() -> None:
    with pytest.raises(ValidationError):
        SubmissionVersionCreateRequest()
    duplicate_id = uuid4()
    with pytest.raises(ValidationError):
        SubmissionVersionCreateRequest(file_ids=[duplicate_id, duplicate_id])
    with pytest.raises(ValidationError):
        SubmissionVersionCreateRequest(external_url="javascript:alert(1)")

    request = SubmissionVersionCreateRequest(
        text_markdown="  正文  ",
        external_url="https://example.invalid/result",
    )
    assert request.text_markdown == "正文"
    assert request.external_url == "https://example.invalid/result"


@pytest.mark.asyncio
async def test_submission_file_binding_rechecks_owner_context_type_and_total_limit() -> None:
    actor_id = uuid4()
    assignment_id = uuid4()
    stored_file = make_available_file(owner_user_id=actor_id)
    second_file = make_available_file(owner_user_id=actor_id, size_bytes=300)
    second_file.original_name = "diagram.png"
    second_file.extension = "png"
    second_file.declared_media_type = "image/png"
    second_file.detected_media_type = "image/png"
    service = SubmissionService(cast(AsyncSession, AsyncMock()))
    uploads = SimpleNamespace(
        get_files=AsyncMock(return_value=[second_file, stored_file]),
        get_session_by_file=AsyncMock(
            return_value=SimpleNamespace(
                context_type="assignment",
                context_id=assignment_id,
            )
        ),
        bound_announcement_id=AsyncMock(return_value=None),
    )
    submissions = SimpleNamespace(file_is_bound=AsyncMock(return_value=False))
    service._uploads = cast(UploadRepository, uploads)
    service._submissions = cast(SubmissionRepository, submissions)

    files, total = await service._validate_files(
        assignment_id=assignment_id,
        actor_user_id=actor_id,
        allowed_extensions=["pdf", "png"],
        max_total_bytes=1024,
        file_ids=[stored_file.id, second_file.id],
    )
    assert files == [stored_file, second_file]
    assert total == 1000

    with pytest.raises(ApplicationError) as oversized:
        await service._validate_files(
            assignment_id=assignment_id,
            actor_user_id=actor_id,
            allowed_extensions=["pdf", "png"],
            max_total_bytes=999,
            file_ids=[stored_file.id, second_file.id],
        )
    assert oversized.value.code == "SUBMISSION_SIZE_EXCEEDED"

    stored_file.owner_user_id = uuid4()
    with pytest.raises(ApplicationError) as foreign_file:
        await service._validate_files(
            assignment_id=assignment_id,
            actor_user_id=actor_id,
            allowed_extensions=["pdf", "png"],
            max_total_bytes=1024,
            file_ids=[stored_file.id, second_file.id],
        )
    assert foreign_file.value.code == "FILE_NOT_AVAILABLE"


def test_submission_request_hash_is_stable_and_content_sensitive() -> None:
    first = SubmissionVersionCreateRequest(text_markdown="第一版")
    same = SubmissionVersionCreateRequest(text_markdown="第一版")
    changed = SubmissionVersionCreateRequest(text_markdown="第二版")

    assert SubmissionService._request_hash(first) == SubmissionService._request_hash(same)
    assert SubmissionService._request_hash(first) != SubmissionService._request_hash(changed)


@pytest.mark.asyncio
async def test_feedback_queues_private_notification_and_email_in_same_transaction() -> None:
    now = datetime.now(UTC)
    assignment_id = uuid4()
    submission_id = uuid4()
    version_id = uuid4()
    owner_id = uuid4()
    admin_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    service = SubmissionService(cast(AsyncSession, session), clock=lambda: now)
    submissions = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                id=submission_id,
                assignment_id=assignment_id,
                owner_user_id=owner_id,
            )
        ),
        get_version=AsyncMock(
            return_value=SimpleNamespace(id=version_id, submission_id=submission_id)
        ),
        feedback_for_version=AsyncMock(return_value=None),
        add_feedback=Mock(),
    )
    notifications = SimpleNamespace(add_all=Mock())
    outbox = SimpleNamespace(add=Mock())
    service._submissions = cast(SubmissionRepository, submissions)
    service._assignments = cast(
        AssignmentRepository,
        SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(title="电控作业"))),
    )
    service._users = cast(
        UserRepository,
        SimpleNamespace(
            get_by_id=AsyncMock(
                return_value=SimpleNamespace(
                    id=owner_id,
                    email="student@connect.hkust-gz.edu.cn",
                    full_name="测试同学",
                )
            )
        ),
    )
    service._notifications = cast(StudentNotificationRepository, notifications)
    service._outbox = cast(OutboxRepository, outbox)
    service._audit = Mock()

    await service.put_feedback(
        submission_id,
        version_id,
        FeedbackPutRequest(body_markdown="只在站内显示的评语"),
        audit=SubmissionAuditContext(
            actor=cast(
                AuthenticatedContext,
                SimpleNamespace(user=SimpleNamespace(id=admin_id)),
            ),
            request_id="feedback-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    notification = notifications.add_all.call_args.args[0][0]
    email_job = outbox.add.call_args.args[0]
    assert notification.user_id == owner_id
    assert email_job.job_type == "submission_feedback_email"
    assert email_job.event_key.endswith(":revision:1:email")
    assert email_job.payload["recipient"] == "student@connect.hkust-gz.edu.cn"
    assert email_job.payload["target_url"] == (
        f"/assignments/{assignment_id}/submissions/{submission_id}"
    )
    assert "只在站内显示的评语" not in str(email_job.payload)
    session.commit.assert_awaited_once()

    rendered = render_mail(
        email_job,
        {},
        app_base_url="https://training.example.invalid",
    )
    assert "作业评语更新" in rendered.subject
    assert "只在站内显示的评语" not in rendered.text
    assert str(submission_id) in rendered.text

    created_feedback = submissions.add_feedback.call_args.args[0]
    submissions.feedback_for_version.return_value = created_feedback
    await service.put_feedback(
        submission_id,
        version_id,
        FeedbackPutRequest(body_markdown="修订后的站内评语", revision=1),
        audit=SubmissionAuditContext(
            actor=cast(
                AuthenticatedContext,
                SimpleNamespace(user=SimpleNamespace(id=admin_id)),
            ),
            request_id="feedback-revision-request",
            ip_prefix="127.0.0.0/24",
        ),
    )

    revised_email_job = outbox.add.call_args.args[0]
    assert created_feedback.revision == 2
    assert revised_email_job.event_key.endswith(":revision:2:email")
    assert "修订后的站内评语" not in str(revised_email_job.payload)
    assert outbox.add.call_count == 2
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_excellent_submission_attachment_download_requires_marker_and_audience() -> None:
    owner_id = uuid4()
    viewer_id = uuid4()
    assignment_id = uuid4()
    version_id = uuid4()
    stored_file = make_available_file(owner_user_id=owner_id)
    store = SimpleNamespace(
        presign_download=AsyncMock(return_value="https://storage.invalid/presigned"),
        presign_inline=AsyncMock(return_value="https://storage.invalid/preview"),
    )
    service = UploadService(
        cast(AsyncSession, AsyncMock()),
        Settings(app_env="test"),
        object_store=cast(MinioObjectStore, store),
        clock=lambda: datetime.now(UTC),
    )
    uploads = SimpleNamespace(
        get_file=AsyncMock(return_value=stored_file),
        bound_announcement_id=AsyncMock(return_value=None),
        bound_version_id=AsyncMock(return_value=version_id),
    )
    submissions = SimpleNamespace(
        version_with_submission=AsyncMock(
            return_value=SimpleNamespace(
                submission=SimpleNamespace(
                    assignment_id=assignment_id,
                    owner_user_id=owner_id,
                )
            )
        )
    )
    assignment = SimpleNamespace(status="published")
    assignments = SimpleNamespace(
        get_by_id=AsyncMock(return_value=assignment),
        get_excellent_marker=AsyncMock(return_value=object()),
        is_audience_user=AsyncMock(return_value=True),
    )
    service._uploads = cast(UploadRepository, uploads)
    service._submissions = cast(SubmissionRepository, submissions)
    service._assignments = cast(AssignmentRepository, assignments)
    context = cast(
        AuthenticatedContext,
        SimpleNamespace(user=SimpleNamespace(id=viewer_id, role="student")),
    )

    response = await service.download_url(stored_file.id, context=context)
    preview = await service.preview_url(stored_file.id, context=context)
    assert response.url == "https://storage.invalid/presigned"
    assert preview.url == "https://storage.invalid/preview"

    assignment.status = "archived"
    with pytest.raises(ApplicationError) as removed:
        await service.download_url(stored_file.id, context=context)
    assert removed.value.status_code == 404

    assignment.status = "published"
    assignments.get_excellent_marker = AsyncMock(return_value=None)
    with pytest.raises(ApplicationError) as hidden:
        await service.download_url(stored_file.id, context=context)
    assert hidden.value.status_code == 404
    assert hidden.value.code == "RESOURCE_NOT_FOUND"

    owner_context = cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=owner_id, role="student"),
            is_admin=False,
        ),
    )
    owner_preview = await service.preview_url(stored_file.id, context=owner_context)
    assert owner_preview.url == "https://storage.invalid/preview"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_name", "extension", "media_type", "response_content_type"),
    [
        ("report.pdf", "pdf", "application/pdf", "application/pdf"),
        ("diagram.png", "png", "image/png", "image/png"),
        ("demo.mp4", "mp4", "video/mp4", "video/mp4"),
        ("demo.webm", "webm", "video/webm", "video/webm"),
        ("notes.txt", "txt", "text/plain", "text/plain; charset=utf-8"),
    ],
)
async def test_attachment_preview_allows_only_detected_browser_safe_types(
    file_name: str,
    extension: str,
    media_type: str,
    response_content_type: str,
) -> None:
    stored_file = make_available_file(owner_user_id=uuid4())
    stored_file.original_name = file_name
    stored_file.extension = extension
    stored_file.declared_media_type = media_type
    stored_file.detected_media_type = media_type
    store = SimpleNamespace(
        presign_inline=AsyncMock(return_value="https://storage.invalid/preview")
    )
    service = UploadService(
        cast(AsyncSession, AsyncMock()),
        Settings(app_env="test"),
        object_store=cast(MinioObjectStore, store),
        clock=lambda: datetime.now(UTC),
    )
    service._uploads = cast(
        UploadRepository,
        SimpleNamespace(
            get_file=AsyncMock(return_value=stored_file),
            bound_announcement_id=AsyncMock(return_value=uuid4()),
        ),
    )
    context = cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4(), role="admin"),
            is_admin=True,
        ),
    )

    result = await service.preview_url(stored_file.id, context=context)

    assert result.media_type == media_type
    store.presign_inline.assert_awaited_once_with(
        object_key=stored_file.object_key,
        file_name=file_name,
        content_type=response_content_type,
        expires_seconds=300,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_name", "extension", "media_type"),
    [
        ("page.html", "html", "text/html"),
        ("drawing.svg", "svg", "image/svg+xml"),
        ("sheet.xlsx", "xlsx", "application/zip"),
        ("archive.zip", "zip", "application/zip"),
        ("tool.exe", "exe", "application/x-msdownload"),
    ],
)
async def test_attachment_preview_rejects_active_content_and_download_only_types(
    file_name: str,
    extension: str,
    media_type: str,
) -> None:
    stored_file = make_available_file(owner_user_id=uuid4())
    stored_file.original_name = file_name
    stored_file.extension = extension
    stored_file.declared_media_type = media_type
    stored_file.detected_media_type = media_type
    store = SimpleNamespace(presign_inline=AsyncMock())
    service = UploadService(
        cast(AsyncSession, AsyncMock()),
        Settings(app_env="test"),
        object_store=cast(MinioObjectStore, store),
    )
    service._uploads = cast(
        UploadRepository,
        SimpleNamespace(
            get_file=AsyncMock(return_value=stored_file),
            bound_announcement_id=AsyncMock(return_value=uuid4()),
        ),
    )
    context = cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=uuid4(), role="admin"),
            is_admin=True,
        ),
    )

    with pytest.raises(ApplicationError) as unsupported:
        await service.preview_url(stored_file.id, context=context)

    assert unsupported.value.status_code == 415
    assert unsupported.value.code == "FILE_PREVIEW_NOT_SUPPORTED"
    store.presign_inline.assert_not_awaited()


def completion_audit_context(admin_id: object) -> SubmissionAuditContext:
    return SubmissionAuditContext(
        actor=cast(
            AuthenticatedContext,
            SimpleNamespace(user=SimpleNamespace(id=admin_id)),
        ),
        request_id="completion-request",
        ip_prefix="127.0.0.0/24",
    )


@pytest.mark.asyncio
async def test_admin_confirms_latest_submission_version_with_audit() -> None:
    now = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
    submission_id = uuid4()
    assignment_id = uuid4()
    version_id = uuid4()
    admin_id = uuid4()
    submission = SimpleNamespace(
        id=submission_id,
        assignment_id=assignment_id,
        latest_version_id=version_id,
        completed_version_id=None,
        completed_at=None,
        completed_by=None,
        updated_at=now,
    )
    version = SimpleNamespace(id=version_id, version_number=3)
    session = AsyncMock(spec=AsyncSession)
    service = SubmissionService(cast(AsyncSession, session), clock=lambda: now)
    submissions = SimpleNamespace(
        get_by_id=AsyncMock(return_value=submission),
        get_version=AsyncMock(return_value=version),
    )
    audit = Mock()
    service._submissions = cast(SubmissionRepository, submissions)
    service._audit = audit

    response = await service.confirm_completion(
        submission_id,
        audit=completion_audit_context(admin_id),
    )

    assert response.submission_id == submission_id
    assert response.latest_version_id == version_id
    assert response.completed_version_id == version_id
    assert response.completed_at == now
    assert response.is_completed is True
    assert submission.completed_by == admin_id
    submissions.get_by_id.assert_awaited_once_with(submission_id, for_update=True)
    submissions.get_version.assert_awaited_once_with(
        version_id,
        submission_id=submission_id,
    )
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    entry = audit.add.call_args.args[0]
    assert entry.action == "submission.completion_confirm"
    assert entry.target_type == "submission"
    assert entry.target_id == submission_id
    assert entry.actor_user_id == admin_id
    assert entry.change_summary == {
        "assignment_id": str(assignment_id),
        "completed_version_id": str(version_id),
        "version_number": 3,
    }


@pytest.mark.asyncio
async def test_completion_confirmation_is_idempotent_for_current_version() -> None:
    version_id = uuid4()
    completed_at = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
    submission = SimpleNamespace(
        id=uuid4(),
        assignment_id=uuid4(),
        latest_version_id=version_id,
        completed_version_id=version_id,
        completed_at=completed_at,
    )
    session = AsyncMock(spec=AsyncSession)
    service = SubmissionService(cast(AsyncSession, session))
    submissions = SimpleNamespace(
        get_by_id=AsyncMock(return_value=submission),
        get_version=AsyncMock(),
    )
    audit = Mock()
    service._submissions = cast(SubmissionRepository, submissions)
    service._audit = audit

    response = await service.confirm_completion(
        submission.id,
        audit=completion_audit_context(uuid4()),
    )

    assert response.is_completed is True
    assert response.completed_at == completed_at
    submissions.get_version.assert_not_awaited()
    audit.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_revokes_completion_and_repeated_revoke_is_idempotent() -> None:
    now = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)
    version_id = uuid4()
    submission = SimpleNamespace(
        id=uuid4(),
        assignment_id=uuid4(),
        latest_version_id=version_id,
        completed_version_id=version_id,
        completed_at=now,
        completed_by=uuid4(),
        updated_at=now,
    )
    session = AsyncMock(spec=AsyncSession)
    service = SubmissionService(cast(AsyncSession, session), clock=lambda: now)
    service._submissions = cast(
        SubmissionRepository,
        SimpleNamespace(get_by_id=AsyncMock(return_value=submission)),
    )
    audit = Mock()
    service._audit = audit

    first = await service.revoke_completion(
        submission.id,
        audit=completion_audit_context(uuid4()),
    )
    second = await service.revoke_completion(
        submission.id,
        audit=completion_audit_context(uuid4()),
    )

    assert first.is_completed is False
    assert second.is_completed is False
    assert submission.completed_version_id is None
    assert submission.completed_at is None
    assert submission.completed_by is None
    assert audit.add.call_count == 1
    entry = audit.add.call_args.args[0]
    assert entry.action == "submission.completion_revoke"
    assert entry.change_summary["previous_completed_version_id"] == str(version_id)
    assert session.commit.await_count == 2


def test_new_latest_version_requires_fresh_completion_confirmation() -> None:
    response = SubmissionService._completion_response(
        cast(
            Submission,
            SimpleNamespace(
                id=uuid4(),
                latest_version_id=uuid4(),
                completed_version_id=uuid4(),
                completed_at=datetime.now(UTC),
            ),
        )
    )

    assert response.is_completed is False
