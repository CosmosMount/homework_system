from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.repository import AuditRepository
from app.auth.dependencies import require_admin, require_csrf
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.knowledge.feishu_client import FeishuClient, KnowledgeSyncError
from app.knowledge.models import KnowledgeAsset, KnowledgeSyncRun
from app.knowledge.normalizer import AssetReference
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.router import router as knowledge_router
from app.knowledge.service import (
    KnowledgeAuditContext,
    KnowledgeService,
    KnowledgeSynchronizer,
)
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.notifications.service import OutboxProcessor
from app.uploads.object_store import MinioObjectStore
from app.uploads.service import FileValidationError


def configured_settings() -> Settings:
    return Settings(
        app_env="test",
        feishu_app_id="app-id",
        feishu_app_secret="app-secret-value",
        feishu_wiki_url="https://pnx.feishu.cn/wiki/space/7666438057763015890",
    )


class RecordingObjectStore:
    def __init__(self) -> None:
        self.inline_keys: list[str] = []
        self.import_called = False

    async def presign_inline(
        self,
        *,
        object_key: str,
        file_name: str,
        content_type: str,
        expires_seconds: int,
    ) -> str:
        self.inline_keys.append(object_key)
        return "https://storage.example.edu/signed-image"

    async def presign_download(
        self,
        *,
        object_key: str,
        file_name: str,
        expires_seconds: int,
    ) -> str:
        return "https://storage.example.edu/signed-download"

    async def import_bytes(
        self,
        object_key: str,
        content: bytes,
        *,
        content_type: str,
    ) -> object:
        self.import_called = True
        return SimpleNamespace(
            size_bytes=len(content),
            sha256="0" * 64,
            first_bytes=content[:32],
            content_type=content_type,
        )


@pytest.mark.asyncio
async def test_overview_keeps_latest_successful_snapshot_when_newer_run_failed() -> None:
    now = datetime.now(UTC)
    successful_run = cast(
        KnowledgeSyncRun,
        SimpleNamespace(
            id=uuid4(),
            finished_at=now,
            source_url="https://pnx.feishu.cn/wiki/",
            document_count=2,
            asset_count=1,
        ),
    )
    repository = SimpleNamespace(
        latest_succeeded_run=AsyncMock(return_value=successful_run),
        list_nodes=AsyncMock(return_value=[]),
        list_documents=AsyncMock(return_value=[]),
    )
    service = KnowledgeService(
        cast(AsyncSession, AsyncMock(spec=AsyncSession)),
        Settings(app_env="test"),
        object_store=cast(MinioObjectStore, RecordingObjectStore()),
    )
    service._repo = cast(KnowledgeRepository, repository)

    overview = await service.overview()

    assert overview.snapshot is not None
    assert overview.snapshot.run_id == successful_run.id
    repository.latest_succeeded_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_overview_exposes_protected_standalone_file_metadata() -> None:
    run_id = uuid4()
    asset_id = uuid4()
    node_id = uuid4()
    file_token = "standalone-file-token"
    repository = SimpleNamespace(
        latest_succeeded_run=AsyncMock(
            return_value=cast(
                KnowledgeSyncRun,
                SimpleNamespace(
                    id=run_id,
                    finished_at=datetime.now(UTC),
                    source_url="https://pnx.feishu.cn/wiki/",
                    document_count=1,
                    asset_count=1,
                ),
            )
        ),
        list_nodes=AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=node_id,
                    parent_id=None,
                    asset_id=asset_id,
                    external_object_token=file_token,
                    title="训练资料.pdf",
                    node_type="file",
                    depth=0,
                    display_order=0,
                    source_url="https://pnx.feishu.cn/wiki/file-node",
                )
            ]
        ),
        list_documents=AsyncMock(return_value=[]),
        assets_by_external_keys=AsyncMock(
            return_value={
                (file_token, "attachment"): SimpleNamespace(
                    id=asset_id,
                    size_bytes=2048,
                    media_type="application/pdf",
                )
            }
        ),
    )
    service = KnowledgeService(
        cast(AsyncSession, AsyncMock(spec=AsyncSession)),
        Settings(app_env="test"),
        object_store=cast(MinioObjectStore, RecordingObjectStore()),
    )
    service._repo = cast(KnowledgeRepository, repository)

    overview = await service.overview()

    assert overview.nodes[0].node_type == "file"
    assert overview.nodes[0].asset_id == asset_id
    assert overview.nodes[0].file_size == 2048
    assert overview.nodes[0].mime_type == "application/pdf"
    repository.assets_by_external_keys.assert_awaited_once_with([(file_token, "attachment")])


@pytest.mark.asyncio
async def test_asset_url_only_uses_asset_referenced_by_current_successful_snapshot() -> None:
    current_run_id = uuid4()
    asset_id = uuid4()
    asset = cast(
        KnowledgeAsset,
        SimpleNamespace(
            id=asset_id,
            asset_kind="image",
            object_key="knowledge/server-generated/object.png",
            file_name="知识库图片.png",
            media_type="image/png",
        ),
    )
    repository = SimpleNamespace(
        latest_succeeded_run=AsyncMock(
            return_value=cast(KnowledgeSyncRun, SimpleNamespace(id=current_run_id))
        ),
        current_asset=AsyncMock(return_value=asset),
    )
    object_store = RecordingObjectStore()
    service = KnowledgeService(
        cast(AsyncSession, AsyncMock(spec=AsyncSession)),
        Settings(app_env="test"),
        object_store=cast(MinioObjectStore, object_store),
    )
    service._repo = cast(KnowledgeRepository, repository)

    signed_url = await service.asset_url(asset_id)

    assert signed_url == "https://storage.example.edu/signed-image"
    repository.current_asset.assert_awaited_once_with(current_run_id, asset_id)
    assert object_store.inline_keys == ["knowledge/server-generated/object.png"]


@pytest.mark.asyncio
async def test_asset_from_noncurrent_snapshot_is_not_visible() -> None:
    current_run_id = uuid4()
    asset_id = uuid4()
    repository = SimpleNamespace(
        latest_succeeded_run=AsyncMock(
            return_value=cast(KnowledgeSyncRun, SimpleNamespace(id=current_run_id))
        ),
        current_asset=AsyncMock(return_value=None),
    )
    service = KnowledgeService(
        cast(AsyncSession, AsyncMock(spec=AsyncSession)),
        Settings(app_env="test"),
        object_store=cast(MinioObjectStore, RecordingObjectStore()),
    )
    service._repo = cast(KnowledgeRepository, repository)

    with pytest.raises(ApplicationError) as exc_info:
        await service.asset_url(asset_id)

    assert exc_info.value.status_code == 404
    repository.current_asset.assert_awaited_once_with(current_run_id, asset_id)


@pytest.mark.asyncio
async def test_admin_student_view_cannot_trigger_knowledge_sync() -> None:
    actor = cast(
        AuthenticatedContext,
        SimpleNamespace(
            is_admin=False,
            user=SimpleNamespace(id=uuid4(), role="admin"),
        ),
    )
    service = KnowledgeService(
        cast(AsyncSession, AsyncMock(spec=AsyncSession)),
        configured_settings(),
        object_store=cast(MinioObjectStore, RecordingObjectStore()),
    )

    with pytest.raises(ApplicationError) as exc_info:
        await service.trigger_sync(
            audit_context=KnowledgeAuditContext(
                actor=actor,
                request_id="request-id",
                ip_prefix="192.0.2.0/24",
            )
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_concurrent_trigger_unique_conflict_returns_domain_conflict() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.commit.side_effect = IntegrityError(
        "insert knowledge_sync_runs",
        {},
        RuntimeError("unique violation"),
    )
    repository = SimpleNamespace(
        active_run=AsyncMock(return_value=None),
        add_run=lambda run: None,
    )
    recorder = SimpleNamespace(add=lambda value: None)
    actor = cast(
        AuthenticatedContext,
        SimpleNamespace(
            is_admin=True,
            user=SimpleNamespace(id=uuid4(), role="admin"),
        ),
    )
    service = KnowledgeService(
        cast(AsyncSession, session),
        configured_settings(),
        object_store=cast(MinioObjectStore, RecordingObjectStore()),
    )
    service._repo = cast(KnowledgeRepository, repository)
    service._outbox = cast(OutboxRepository, recorder)
    service._audit = cast(AuditRepository, recorder)

    with pytest.raises(ApplicationError) as exc_info:
        await service.trigger_sync(
            audit_context=KnowledgeAuditContext(
                actor=actor,
                request_id="request-id",
                ip_prefix="192.0.2.0/24",
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "KNOWLEDGE_SYNC_IN_PROGRESS"
    session.rollback.assert_awaited_once()


def test_sync_route_requires_admin_and_csrf_dependencies() -> None:
    route = next(
        item
        for item in knowledge_router.routes
        if isinstance(item, APIRoute)
        and item.path == "/admin/knowledge/sync"
        and item.methods is not None
        and "POST" in item.methods
    )
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}

    assert require_admin in dependency_calls
    assert require_csrf in dependency_calls


class HtmlAttachmentClient:
    async def download_asset(self, token: str, kind: str) -> tuple[bytes, str | None]:
        return b"<html><script>alert(1)</script></html>", "text/html"


@pytest.mark.asyncio
async def test_dangerous_attachment_is_rejected_before_minio_import() -> None:
    object_store = RecordingObjectStore()
    synchronizer = KnowledgeSynchronizer(
        cast(async_sessionmaker[AsyncSession], SimpleNamespace()),
        configured_settings(),
        object_store=cast(MinioObjectStore, object_store),
    )

    with pytest.raises(FileValidationError):
        await synchronizer._prepare_asset(
            cast(FeishuClient, HtmlAttachmentClient()),
            AssetReference(
                token="asset-token",
                kind="attachment",
                file_name="payload.html",
            ),
            now=datetime.now(UTC),
        )

    assert object_store.import_called is False


class FailingKnowledgeSync:
    def __init__(self, error: KnowledgeSyncError) -> None:
        self.error = error
        self.run_ids: list[UUID] = []
        self.failed_run_ids: list[UUID] = []

    async def synchronize(self, run_id: UUID) -> None:
        self.run_ids.append(run_id)
        raise self.error

    async def mark_failed(self, run_id: UUID, error: KnowledgeSyncError) -> None:
        self.failed_run_ids.append(run_id)


class FailureHarness(OutboxProcessor):
    def __init__(self, job: OutboxJob, error: KnowledgeSyncError) -> None:
        self._job = job
        self.knowledge_sync = FailingKnowledgeSync(error)
        self._knowledge_sync = self.knowledge_sync
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


def make_knowledge_job(
    *,
    attempt_count: int,
    max_attempts: int = 3,
) -> tuple[OutboxJob, UUID]:
    now = datetime.now(UTC)
    run_id = uuid4()
    return (
        OutboxJob(
            id=uuid4(),
            job_type="sync_knowledge",
            event_key=f"knowledge_sync:{run_id}",
            payload={"run_id": str(run_id)},
            secret_payload_ciphertext=None,
            status="processing",
            available_at=now,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
            locked_by="worker",
            locked_at=now,
            last_error_code=None,
            last_error_summary=None,
            created_at=now,
            sent_at=None,
        ),
        run_id,
    )


@pytest.mark.asyncio
async def test_permanent_knowledge_failure_marks_run_and_job_failed() -> None:
    job, run_id = make_knowledge_job(attempt_count=0)
    processor = FailureHarness(
        job,
        KnowledgeSyncError("FEISHU_API_REJECTED", permanent=True),
    )

    assert await processor.run_once() == 1
    assert processor.knowledge_sync.failed_run_ids == [run_id]
    assert processor.failed_ids == [job.id]
    assert processor.sent_ids == []


@pytest.mark.asyncio
async def test_transient_failure_marks_run_failed_only_when_retries_exhausted() -> None:
    retry_job, _retry_run_id = make_knowledge_job(attempt_count=1)
    retry_processor = FailureHarness(
        retry_job,
        KnowledgeSyncError("FEISHU_NETWORK_UNAVAILABLE", permanent=False),
    )

    assert await retry_processor.run_once() == 1
    assert retry_processor.knowledge_sync.failed_run_ids == []
    assert retry_processor.failed_ids == [retry_job.id]

    final_job, final_run_id = make_knowledge_job(attempt_count=2)
    final_processor = FailureHarness(
        final_job,
        KnowledgeSyncError("FEISHU_NETWORK_UNAVAILABLE", permanent=False),
    )

    assert await final_processor.run_once() == 1
    assert final_processor.knowledge_sync.failed_run_ids == [final_run_id]
    assert final_processor.failed_ids == [final_job.id]
