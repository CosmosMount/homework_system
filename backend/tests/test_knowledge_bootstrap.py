import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.knowledge.bootstrap as bootstrap_module
import app.knowledge.service as knowledge_service_module
from app.core.config import Settings
from app.knowledge.bootstrap import bootstrap_active_run
from app.knowledge.feishu_client import FeishuClient, KnowledgeSyncError
from app.knowledge.models import KnowledgeAsset
from app.knowledge.normalizer import AssetReference
from app.knowledge.service import KnowledgeSynchronizer
from app.uploads.object_store import MinioObjectStore


class RecordingSynchronizer:
    def __init__(self, *, error: KnowledgeSyncError | None = None) -> None:
        self.error = error
        self.calls: list[UUID] = []

    async def synchronize(self, run_id: UUID) -> None:
        self.calls.append(run_id)
        if self.error is not None:
            raise self.error


def fake_factory() -> async_sessionmaker[AsyncSession]:
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(spec=AsyncSession))
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return cast(async_sessionmaker[AsyncSession], factory)


@pytest.mark.asyncio
async def test_bootstrap_requires_exactly_one_active_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(active_run=AsyncMock(return_value=None))
    monkeypatch.setattr(
        bootstrap_module,
        "KnowledgeRepository",
        lambda session: repository,
    )
    synchronizer = RecordingSynchronizer()

    result = await bootstrap_active_run(
        fake_factory(),
        Settings(app_env="test"),
        synchronizer=synchronizer,
    )

    assert result == 2
    assert synchronizer.calls == []


@pytest.mark.asyncio
async def test_bootstrap_reuses_active_run_for_complete_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    repository = SimpleNamespace(active_run=AsyncMock(return_value=SimpleNamespace(id=run_id)))
    monkeypatch.setattr(
        bootstrap_module,
        "KnowledgeRepository",
        lambda session: repository,
    )
    synchronizer = RecordingSynchronizer()

    result = await bootstrap_active_run(
        fake_factory(),
        Settings(app_env="test"),
        synchronizer=synchronizer,
    )

    assert result == 0
    assert synchronizer.calls == [run_id]


@pytest.mark.asyncio
async def test_bootstrap_returns_failure_without_exposing_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    repository = SimpleNamespace(active_run=AsyncMock(return_value=SimpleNamespace(id=run_id)))
    monkeypatch.setattr(
        bootstrap_module,
        "KnowledgeRepository",
        lambda session: repository,
    )
    synchronizer = RecordingSynchronizer(
        error=KnowledgeSyncError("KNOWLEDGE_SYNC_FAILED", permanent=False)
    )

    result = await bootstrap_active_run(
        fake_factory(),
        Settings(app_env="test"),
        synchronizer=synchronizer,
    )

    assert result == 1
    assert synchronizer.calls == [run_id]


def test_bootstrap_no_longer_accepts_initial_text_only() -> None:
    with pytest.raises(SystemExit):
        bootstrap_module._parse_args(["--initial-text-only"])


class SequentialFeishuClient:
    def __init__(
        self,
        *,
        document_count: int,
        rejected_documents: set[str] | None = None,
        rejected_titles: set[str] | None = None,
        standalone_file: bool = False,
    ) -> None:
        self.document_count = document_count
        self.rejected_documents = rejected_documents or set()
        self.rejected_titles = rejected_titles or set()
        self.standalone_file = standalone_file
        self.calls: list[str] = []

    async def tenant_token(self) -> str:
        self.calls.append("tenant_token")
        return "tenant-token"

    async def list_nodes(self) -> list[dict[str, object]]:
        self.calls.append("list_nodes")
        nodes: list[dict[str, object]] = [
            {
                "node_token": f"node-{index}",
                "obj_token": f"doc-{index}",
                "obj_type": "docx",
                "title": f"文档 {index}",
            }
            for index in range(self.document_count)
        ]
        if self.standalone_file:
            nodes.append(
                {
                    "node_token": "standalone-file-node",
                    "obj_token": "standalone-file-token",
                    "obj_type": "file",
                    "title": "训练资料.pdf",
                }
            )
        return nodes

    async def document_blocks(self, document_id: str) -> list[dict[str, object]]:
        self.calls.append(f"blocks:{document_id}")
        if document_id in self.rejected_documents:
            raise KnowledgeSyncError("FEISHU_REQUEST_REJECTED", permanent=True)
        return [
            {
                "block_id": f"image-{document_id}",
                "block_type": 27,
                "image": {"token": f"image-{document_id}"},
            },
            {
                "block_id": f"file-{document_id}",
                "block_type": 23,
                "file": {"token": f"file-{document_id}", "name": "说明.pdf"},
            },
        ]

    async def document_title(self, document_id: str) -> str:
        self.calls.append(f"title:{document_id}")
        if document_id in self.rejected_titles:
            raise KnowledgeSyncError("FEISHU_REQUEST_REJECTED", permanent=True)
        return f"接口标题 {document_id}"

    def source_url(self, node_token: str) -> str:
        return f"https://pnx.feishu.cn/wiki/{node_token}"


class VisualAssetFeishuClient(SequentialFeishuClient):
    async def document_blocks(self, document_id: str) -> list[dict[str, object]]:
        self.calls.append(f"blocks:{document_id}")
        return [
            {
                "block_id": f"image-{document_id}",
                "block_type": 27,
                "image": {"token": f"image-{document_id}"},
            },
            {
                "block_id": f"file-{document_id}",
                "block_type": 23,
                "file": {"token": f"file-{document_id}", "name": "说明.pdf"},
            },
            {
                "block_id": f"board-{document_id}",
                "block_type": 43,
                "board": {"whiteboard_id": f"board-{document_id}"},
            },
        ]


def configured_settings() -> Settings:
    return Settings(
        app_env="test",
        feishu_app_id="app-id",
        feishu_app_secret="app-secret-value",
        feishu_wiki_url="https://pnx.feishu.cn/wiki/space/7666438057763015890",
    )


@pytest.mark.asyncio
async def test_synchronizer_matches_reference_document_and_asset_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SequentialFeishuClient(document_count=2, standalone_file=True)
    monkeypatch.setattr(
        knowledge_service_module,
        "FeishuClient",
        lambda settings, transport=None: client,
    )
    synchronizer = KnowledgeSynchronizer(
        fake_factory(),
        configured_settings(),
        object_store=cast(MinioObjectStore, SimpleNamespace()),
    )
    monkeypatch.setattr(synchronizer, "_set_running", AsyncMock(return_value=True))
    monkeypatch.setattr(
        synchronizer,
        "_read_existing_assets",
        AsyncMock(return_value={}),
    )
    persist = AsyncMock()
    monkeypatch.setattr(synchronizer, "_persist", persist)

    async def prepare_asset(
        client: SequentialFeishuClient,
        reference: AssetReference,
        *,
        now: datetime,
        standalone_file: bool = False,
    ) -> KnowledgeAsset:
        source = "file" if standalone_file else "media"
        client.calls.append(f"asset:{source}:{reference.kind}:{reference.token}")
        return KnowledgeAsset(
            id=uuid4(),
            external_asset_token=reference.token,
            asset_kind=reference.kind,
            object_key=f"knowledge/test/{reference.token}",
            file_name="说明.pdf" if reference.kind == "attachment" else "知识库图片.png",
            media_type="application/pdf" if reference.kind == "attachment" else "image/png",
            size_bytes=8,
            sha256="0" * 64,
            width=None,
            height=None,
            created_at=now,
            last_seen_at=now,
        )

    monkeypatch.setattr(synchronizer, "_prepare_asset", prepare_asset)

    await synchronizer.synchronize(uuid4())

    assert client.calls == [
        "tenant_token",
        "list_nodes",
        "blocks:doc-0",
        "title:doc-0",
        "asset:media:attachment:file-doc-0",
        "asset:media:image:image-doc-0",
        "blocks:doc-1",
        "title:doc-1",
        "asset:media:attachment:file-doc-1",
        "asset:media:image:image-doc-1",
        "asset:file:attachment:standalone-file-token",
    ]
    assert persist.await_args is not None
    persisted_call = persist.await_args
    persisted_documents = persisted_call.kwargs["documents"]
    assert [item.display_order for item in persisted_documents] == [0, 1]
    assert [item.title for item in persisted_documents] == [
        "接口标题 doc-0",
        "接口标题 doc-1",
    ]
    assert len(persisted_call.kwargs["new_assets"]) == 5
    assert ("standalone-file-token", "attachment") in persisted_call.kwargs["assets"]
    assert persisted_call.kwargs["raw_nodes"][-1]["obj_type"] == "file"


@pytest.mark.asyncio
async def test_drive_downloads_wait_350ms_while_whiteboard_bypasses_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    object_store = SimpleNamespace(
        import_bytes=AsyncMock(return_value=SimpleNamespace(size_bytes=8, sha256="0" * 64))
    )
    client = SimpleNamespace(
        download_asset=AsyncMock(return_value=(b"\x89PNG\r\n\x1a\n", "image/png")),
        download_file=AsyncMock(return_value=(b"%PDF-1.7\nfile", "application/pdf")),
    )
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    synchronizer = KnowledgeSynchronizer(
        fake_factory(),
        configured_settings(),
        object_store=cast(MinioObjectStore, object_store),
    )
    now = datetime.now(UTC)

    await synchronizer._prepare_asset(
        cast(FeishuClient, client),
        AssetReference(token="image-token", kind="image", file_name="知识库图片"),
        now=now,
    )
    await synchronizer._prepare_asset(
        cast(FeishuClient, client),
        AssetReference(token="board-token", kind="whiteboard", file_name="白板.png"),
        now=now,
    )
    await synchronizer._prepare_asset(
        cast(FeishuClient, client),
        AssetReference(token="standalone-token", kind="attachment", file_name="资料.pdf"),
        now=now,
        standalone_file=True,
    )

    assert sleep.await_args_list == [call(0.35), call(0.35)]
    assert client.download_asset.await_args_list[0].args == ("image-token", "image")
    assert client.download_asset.await_args_list[1].args == ("board-token", "whiteboard")
    client.download_file.assert_awaited_once_with("standalone-token")


@pytest.mark.asyncio
async def test_visual_assets_match_promise_all_while_documents_remain_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = VisualAssetFeishuClient(document_count=1)
    monkeypatch.setattr(
        knowledge_service_module,
        "FeishuClient",
        lambda settings, transport=None: client,
    )
    synchronizer = KnowledgeSynchronizer(
        fake_factory(),
        configured_settings(),
        object_store=cast(MinioObjectStore, SimpleNamespace()),
    )
    monkeypatch.setattr(synchronizer, "_set_running", AsyncMock(return_value=True))
    monkeypatch.setattr(
        synchronizer,
        "_read_existing_assets",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(synchronizer, "_persist", AsyncMock())
    board_started = asyncio.Event()
    events: list[str] = []

    async def prepare_asset(
        client: object,
        reference: AssetReference,
        *,
        now: datetime,
        standalone_file: bool = False,
    ) -> KnowledgeAsset:
        if reference.kind == "attachment":
            events.append("attachment")
        elif reference.kind == "image":
            events.append("image_started")
            await board_started.wait()
            events.append("image_finished")
        else:
            events.append("whiteboard_started")
            board_started.set()
        return KnowledgeAsset(
            id=uuid4(),
            external_asset_token=reference.token,
            asset_kind=reference.kind,
            object_key=f"knowledge/test/{reference.token}",
            file_name="asset.png",
            media_type="image/png",
            size_bytes=8,
            sha256="0" * 64,
            width=None,
            height=None,
            created_at=now,
            last_seen_at=now,
        )

    monkeypatch.setattr(synchronizer, "_prepare_asset", prepare_asset)

    await asyncio.wait_for(synchronizer.synchronize(uuid4()), timeout=1)

    assert events == [
        "attachment",
        "image_started",
        "whiteboard_started",
        "image_finished",
    ]
    assert client.calls[:4] == [
        "tenant_token",
        "list_nodes",
        "blocks:doc-0",
        "title:doc-0",
    ]


@pytest.mark.asyncio
async def test_sync_fails_on_first_rejected_document_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SequentialFeishuClient(document_count=2, rejected_documents={"doc-0"})
    monkeypatch.setattr(
        knowledge_service_module,
        "FeishuClient",
        lambda settings, transport=None: client,
    )
    synchronizer = KnowledgeSynchronizer(
        fake_factory(),
        configured_settings(),
        object_store=cast(MinioObjectStore, SimpleNamespace()),
    )
    monkeypatch.setattr(synchronizer, "_set_running", AsyncMock(return_value=True))
    monkeypatch.setattr(
        synchronizer,
        "_read_existing_assets",
        AsyncMock(return_value={}),
    )
    persist = AsyncMock()
    monkeypatch.setattr(synchronizer, "_persist", persist)
    mark_failed = AsyncMock()
    monkeypatch.setattr(synchronizer, "mark_failed", mark_failed)
    run_id = uuid4()

    with pytest.raises(KnowledgeSyncError) as exc_info:
        await synchronizer.synchronize(run_id)

    assert exc_info.value.code == "FEISHU_REQUEST_REJECTED"
    assert client.calls == ["tenant_token", "list_nodes", "blocks:doc-0"]
    persist.assert_not_awaited()
    mark_failed.assert_awaited_once_with(run_id, exc_info.value)


@pytest.mark.asyncio
async def test_sync_fails_when_document_metadata_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SequentialFeishuClient(document_count=1, rejected_titles={"doc-0"})
    monkeypatch.setattr(
        knowledge_service_module,
        "FeishuClient",
        lambda settings, transport=None: client,
    )
    synchronizer = KnowledgeSynchronizer(
        fake_factory(),
        configured_settings(),
        object_store=cast(MinioObjectStore, SimpleNamespace()),
    )
    monkeypatch.setattr(synchronizer, "_set_running", AsyncMock(return_value=True))
    monkeypatch.setattr(
        synchronizer,
        "_read_existing_assets",
        AsyncMock(return_value={}),
    )
    persist = AsyncMock()
    monkeypatch.setattr(synchronizer, "_persist", persist)

    mark_failed = AsyncMock()
    monkeypatch.setattr(synchronizer, "mark_failed", mark_failed)
    run_id = uuid4()

    with pytest.raises(KnowledgeSyncError) as exc_info:
        await synchronizer.synchronize(run_id)

    assert exc_info.value.code == "FEISHU_REQUEST_REJECTED"
    assert client.calls == [
        "tenant_token",
        "list_nodes",
        "blocks:doc-0",
        "title:doc-0",
    ]
    persist.assert_not_awaited()
    mark_failed.assert_awaited_once_with(run_id, exc_info.value)


@pytest.mark.asyncio
async def test_sync_fails_when_all_documents_are_rejected_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SequentialFeishuClient(
        document_count=2,
        rejected_documents={"doc-0", "doc-1"},
    )
    monkeypatch.setattr(
        knowledge_service_module,
        "FeishuClient",
        lambda settings, transport=None: client,
    )
    synchronizer = KnowledgeSynchronizer(
        fake_factory(),
        configured_settings(),
        object_store=cast(MinioObjectStore, SimpleNamespace()),
    )
    monkeypatch.setattr(synchronizer, "_set_running", AsyncMock(return_value=True))
    persist = AsyncMock()
    monkeypatch.setattr(synchronizer, "_persist", persist)
    mark_failed = AsyncMock()
    monkeypatch.setattr(synchronizer, "mark_failed", mark_failed)
    run_id = uuid4()

    with pytest.raises(KnowledgeSyncError) as exc_info:
        await synchronizer.synchronize(run_id)

    assert exc_info.value.code == "FEISHU_REQUEST_REJECTED"
    assert exc_info.value.permanent is True
    persist.assert_not_awaited()
    mark_failed.assert_awaited_once_with(run_id, exc_info.value)


@pytest.mark.asyncio
async def test_sync_fails_when_space_has_no_readable_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SequentialFeishuClient(document_count=0)
    monkeypatch.setattr(
        knowledge_service_module,
        "FeishuClient",
        lambda settings, transport=None: client,
    )
    synchronizer = KnowledgeSynchronizer(
        fake_factory(),
        configured_settings(),
        object_store=cast(MinioObjectStore, SimpleNamespace()),
    )
    monkeypatch.setattr(synchronizer, "_set_running", AsyncMock(return_value=True))
    persist = AsyncMock()
    monkeypatch.setattr(synchronizer, "_persist", persist)
    mark_failed = AsyncMock()
    monkeypatch.setattr(synchronizer, "mark_failed", mark_failed)
    run_id = uuid4()

    with pytest.raises(KnowledgeSyncError) as exc_info:
        await synchronizer.synchronize(run_id)

    assert exc_info.value.code == "KNOWLEDGE_DOCUMENTS_NOT_FOUND"
    assert exc_info.value.permanent is True
    persist.assert_not_awaited()
    mark_failed.assert_awaited_once_with(run_id, exc_info.value)
