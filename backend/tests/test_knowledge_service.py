import hashlib
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from io import BytesIO
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
    _asset_unavailable_reason,
)
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.notifications.service import OutboxProcessor
from app.uploads.object_store import MinioObjectStore, ObjectStoreError
from app.uploads.service import KNOWLEDGE_EXECUTABLE_MEDIA_TYPE, FileValidationError


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
        self.download_requests: list[tuple[str, str, str | None]] = []
        self.import_called = False
        self.imported_content = b""

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
        content_type: str | None = None,
    ) -> str:
        self.download_requests.append((object_key, file_name, content_type))
        return "https://storage.example.edu/signed-download"

    async def import_stream(
        self,
        object_key: str,
        chunks: AsyncIterable[bytes],
        *,
        content_type: str,
    ) -> object:
        self.import_called = True
        imported = bytearray()
        async for chunk in chunks:
            imported.extend(chunk)
        content = bytes(imported)
        self.imported_content = content
        return SimpleNamespace(
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            first_bytes=content[:32],
            content_type=content_type,
        )


class BytesAssetDownload:
    def __init__(self, content: bytes, content_type: str | None) -> None:
        self.content_type = content_type
        self._body = BytesIO(content)
        self.closed = False

    async def read(self, size: int) -> bytes:
        return self._body.read(size)

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._body.close()


def pe_executable(
    *,
    machine: int = 0x8664,
    characteristics: int = 0x0022,
    optional_magic: int = 0x020B,
    pe_offset: int = 0x80,
) -> bytes:
    content = bytearray(512)
    content[:2] = b"MZ"
    content[0x3C:0x40] = pe_offset.to_bytes(4, "little")
    if pe_offset + 0xF8 <= len(content):
        content[pe_offset : pe_offset + 4] = b"PE\0\0"
        coff_offset = pe_offset + 4
        content[coff_offset : coff_offset + 2] = machine.to_bytes(2, "little")
        content[coff_offset + 2 : coff_offset + 4] = (3).to_bytes(2, "little")
        optional_size = 0xE0 if optional_magic == 0x010B else 0xF0
        content[coff_offset + 16 : coff_offset + 18] = optional_size.to_bytes(2, "little")
        content[coff_offset + 18 : coff_offset + 20] = characteristics.to_bytes(2, "little")
        content[coff_offset + 20 : coff_offset + 22] = optional_magic.to_bytes(2, "little")
    return bytes(content)


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
async def test_executable_asset_download_forces_attachment_octet_stream() -> None:
    current_run_id = uuid4()
    asset_id = uuid4()
    asset = cast(
        KnowledgeAsset,
        SimpleNamespace(
            id=asset_id,
            asset_kind="attachment",
            object_key="knowledge/server-generated/installer.exe",
            file_name="训练客户端.exe",
            media_type=KNOWLEDGE_EXECUTABLE_MEDIA_TYPE,
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

    assert signed_url == "https://storage.example.edu/signed-download"
    assert object_store.download_requests == [
        (
            "knowledge/server-generated/installer.exe",
            "训练客户端.exe",
            "application/octet-stream",
        )
    ]


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
    def __init__(self) -> None:
        self.download = BytesAssetDownload(
            b"<html><script>alert(1)</script></html>",
            "text/html",
        )

    async def download_asset(self, token: str, kind: str) -> BytesAssetDownload:
        return self.download


@pytest.mark.asyncio
async def test_dangerous_attachment_is_rejected_before_minio_import() -> None:
    object_store = RecordingObjectStore()
    client = HtmlAttachmentClient()
    synchronizer = KnowledgeSynchronizer(
        cast(async_sessionmaker[AsyncSession], SimpleNamespace()),
        configured_settings(),
        object_store=cast(MinioObjectStore, object_store),
    )

    with pytest.raises(FileValidationError):
        await synchronizer._prepare_asset(
            cast(FeishuClient, client),
            AssetReference(
                token="asset-token",
                kind="attachment",
                file_name="payload.html",
            ),
            now=datetime.now(UTC),
        )

    assert object_store.import_called is False
    assert client.download.closed is True


@pytest.mark.asyncio
async def test_drive_file_reference_uses_files_download_path() -> None:
    object_store = RecordingObjectStore()
    download = BytesAssetDownload(b"%PDF-1.7\nvalid", "application/pdf")
    client = SimpleNamespace(
        download_file=AsyncMock(return_value=download),
        download_asset=AsyncMock(),
    )
    synchronizer = KnowledgeSynchronizer(
        cast(async_sessionmaker[AsyncSession], SimpleNamespace()),
        configured_settings(),
        object_store=cast(MinioObjectStore, object_store),
    )

    asset = await synchronizer._prepare_asset(
        cast(FeishuClient, client),
        AssetReference(
            token="drive-file-token",
            kind="attachment",
            file_name="训练说明.pdf",
            download_endpoint="file",
        ),
        now=datetime.now(UTC),
    )

    client.download_file.assert_awaited_once_with("drive-file-token")
    client.download_asset.assert_not_awaited()
    assert asset.file_name == "训练说明.pdf"
    assert asset.media_type == "application/pdf"
    assert object_store.import_called is True
    assert object_store.imported_content == b"%PDF-1.7\nvalid"
    assert download.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("machine", "optional_magic"),
    [
        (0x014C, 0x010B),
        (0x01C0, 0x010B),
        (0x01C4, 0x010B),
        (0x8664, 0x020B),
        (0xAA64, 0x020B),
    ],
)
async def test_knowledge_executable_is_validated_and_streamed_to_minio(
    machine: int,
    optional_magic: int,
) -> None:
    object_store = RecordingObjectStore()
    content = pe_executable(machine=machine, optional_magic=optional_magic)
    download = BytesAssetDownload(content, "application/x-msdownload")
    client = SimpleNamespace(
        download_file=AsyncMock(return_value=download),
        download_asset=AsyncMock(),
    )
    synchronizer = KnowledgeSynchronizer(
        cast(async_sessionmaker[AsyncSession], SimpleNamespace()),
        configured_settings(),
        object_store=cast(MinioObjectStore, object_store),
    )

    asset = await synchronizer._prepare_asset(
        cast(FeishuClient, client),
        AssetReference(
            token="installer-token",
            kind="attachment",
            file_name="训练客户端.1.6.3.exe",
            download_endpoint="file",
        ),
        now=datetime.now(UTC),
    )

    assert asset.file_name == "训练客户端.1.6.3.exe"
    assert asset.media_type == KNOWLEDGE_EXECUTABLE_MEDIA_TYPE
    assert asset.object_key.endswith(".exe")
    assert object_store.imported_content == content
    assert download.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_name", "content"),
    [
        ("伪装.pdf.exe", pe_executable()),
        ("伪装.zip.exe", pe_executable()),
        ("伪装.cmd.exe", pe_executable()),
        ("重复.exe.exe", pe_executable()),
        ("仅有MZ.exe", b"MZ" + b"\0" * 510),
        ("偏移越界.exe", pe_executable(pe_offset=0x1000)),
        ("无执行标志.exe", pe_executable(characteristics=0x0020)),
        ("动态库.exe", pe_executable(characteristics=0x2022)),
        ("未知架构.exe", pe_executable(machine=0xFFFF)),
        ("架构头不匹配.exe", pe_executable(machine=0x8664, optional_magic=0x010B)),
    ],
)
async def test_invalid_or_disguised_executable_is_rejected_before_minio(
    file_name: str,
    content: bytes,
) -> None:
    object_store = RecordingObjectStore()
    download = BytesAssetDownload(content, "application/octet-stream")
    client = SimpleNamespace(download_asset=AsyncMock(return_value=download))
    synchronizer = KnowledgeSynchronizer(
        cast(async_sessionmaker[AsyncSession], SimpleNamespace()),
        configured_settings(),
        object_store=cast(MinioObjectStore, object_store),
    )

    with pytest.raises(FileValidationError):
        await synchronizer._prepare_asset(
            cast(FeishuClient, client),
            AssetReference(
                token="invalid-installer-token",
                kind="attachment",
                file_name=file_name,
            ),
            now=datetime.now(UTC),
        )

    assert object_store.import_called is False
    assert download.closed is True


def test_asset_failure_reasons_are_stable_and_coarse() -> None:
    assert (
        _asset_unavailable_reason(FileValidationError("FILE_TYPE_NOT_ALLOWED"))
        == "type_not_allowed"
    )
    assert (
        _asset_unavailable_reason(KnowledgeSyncError("FEISHU_RESPONSE_TOO_LARGE", permanent=True))
        == "too_large"
    )
    assert _asset_unavailable_reason(FileValidationError("FILE_CONTENT_MISMATCH")) == "unavailable"
    assert _asset_unavailable_reason(ObjectStoreError("storage detail")) == "unavailable"


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
