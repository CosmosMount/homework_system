from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.repository import AssignmentRepository
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.submissions.repository import SubmissionRepository
from app.submissions.schemas import SubmissionVersionCreateRequest
from app.submissions.service import SubmissionService
from app.uploads.models import StoredFile
from app.uploads.object_store import MinioObjectStore
from app.uploads.repository import UploadRepository
from app.uploads.service import UploadService


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
    service = SubmissionService(cast(AsyncSession, AsyncMock()))
    uploads = SimpleNamespace(
        get_files=AsyncMock(return_value=[stored_file]),
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
        allowed_extensions=["pdf"],
        max_total_bytes=1024,
        file_ids=[stored_file.id],
    )
    assert files == [stored_file]
    assert total == 700

    with pytest.raises(ApplicationError) as oversized:
        await service._validate_files(
            assignment_id=assignment_id,
            actor_user_id=actor_id,
            allowed_extensions=["pdf"],
            max_total_bytes=699,
            file_ids=[stored_file.id],
        )
    assert oversized.value.code == "SUBMISSION_SIZE_EXCEEDED"

    stored_file.owner_user_id = uuid4()
    with pytest.raises(ApplicationError) as foreign_file:
        await service._validate_files(
            assignment_id=assignment_id,
            actor_user_id=actor_id,
            allowed_extensions=["pdf"],
            max_total_bytes=1024,
            file_ids=[stored_file.id],
        )
    assert foreign_file.value.code == "FILE_NOT_AVAILABLE"


def test_submission_request_hash_is_stable_and_content_sensitive() -> None:
    first = SubmissionVersionCreateRequest(text_markdown="第一版")
    same = SubmissionVersionCreateRequest(text_markdown="第一版")
    changed = SubmissionVersionCreateRequest(text_markdown="第二版")

    assert SubmissionService._request_hash(first) == SubmissionService._request_hash(same)
    assert SubmissionService._request_hash(first) != SubmissionService._request_hash(changed)


@pytest.mark.asyncio
async def test_excellent_submission_attachment_download_requires_marker_and_audience() -> None:
    owner_id = uuid4()
    viewer_id = uuid4()
    assignment_id = uuid4()
    version_id = uuid4()
    stored_file = make_available_file(owner_user_id=owner_id)
    store = SimpleNamespace(
        presign_download=AsyncMock(return_value="https://storage.invalid/presigned")
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
    assert response.url == "https://storage.invalid/presigned"

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
