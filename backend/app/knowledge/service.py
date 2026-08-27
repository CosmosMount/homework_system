import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, context_is_admin
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.knowledge.feishu_client import FeishuClient, HttpTransport, KnowledgeSyncError
from app.knowledge.models import (
    KnowledgeAsset,
    KnowledgeDocument,
    KnowledgeDocumentAsset,
    KnowledgeNode,
    KnowledgeSyncRun,
)
from app.knowledge.normalizer import (
    AssetReference,
    discover_asset_references,
    normalize_document,
)
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import (
    KnowledgeAdminResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentSummary,
    KnowledgeNodeResponse,
    KnowledgeOverviewResponse,
    KnowledgeRunStatus,
    KnowledgeSnapshotMetadata,
    KnowledgeSyncCreatedResponse,
    KnowledgeSyncRunResponse,
)
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.uploads.object_store import MinioObjectStore, ObjectInspection, ObjectStoreError
from app.uploads.service import FileValidationError, detect_media_type, normalize_file_name

logger = logging.getLogger(__name__)
_PROGRESS_LOG_INTERVAL = 10
_DRIVE_DOWNLOAD_DELAY_SECONDS = 0.35


@dataclass(frozen=True, slots=True)
class KnowledgeAuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


@dataclass(slots=True)
class _PreparedDocument:
    node_token: str
    external_document_id: str
    title: str
    source_url: str
    raw_blocks: list[dict[str, Any]]
    asset_references: list[AssetReference]
    display_order: int


def _sync_error_summary(code: str) -> str:
    summaries = {
        "KNOWLEDGE_SYNC_NOT_CONFIGURED": "飞书知识库同步尚未配置。",
        "FEISHU_WIKI_URL_INVALID": "飞书知识库 URL 格式无效，请检查空间或文档链接。",
        "FEISHU_WIKI_NODE_UNSUPPORTED": "飞书知识库 URL 指向的节点不是可读取的新版文档。",
        "FEISHU_AUTHENTICATION_FAILED": "飞书应用认证失败，请检查应用权限与凭证。",
        "FEISHU_API_REJECTED": "飞书拒绝了知识库读取请求，请检查应用权限。",
        "KNOWLEDGE_DOCUMENT_LIMIT_EXCEEDED": "知识库文档数量超过当前同步上限。",
        "KNOWLEDGE_ASSET_LIMIT_EXCEEDED": "知识库媒体数量超过当前同步上限。",
        "KNOWLEDGE_NODE_LIMIT_EXCEEDED": "知识库目录节点数量超过当前同步上限。",
        "KNOWLEDGE_DOCUMENTS_NOT_FOUND": "知识库中没有找到可读取的新版文档。",
    }
    return summaries.get(code, "知识库同步失败，现有成功快照保持不变。")


def _snapshot(run: KnowledgeSyncRun | None) -> KnowledgeSnapshotMetadata | None:
    if run is None or run.finished_at is None:
        return None
    return KnowledgeSnapshotMetadata(
        run_id=run.id,
        synced_at=run.finished_at,
        source_url=run.source_url,
        document_count=run.document_count,
        asset_count=run.asset_count,
    )


def _run_response(run: KnowledgeSyncRun) -> KnowledgeSyncRunResponse:
    return KnowledgeSyncRunResponse(
        id=run.id,
        status=cast(KnowledgeRunStatus, run.status),
        source_url=run.source_url,
        started_at=run.started_at,
        finished_at=run.finished_at,
        document_count=run.document_count,
        asset_count=run.asset_count,
        error_code=run.error_code,
        error_summary=run.error_summary,
        created_at=run.created_at,
    )


class KnowledgeService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        object_store: MinioObjectStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repo = KnowledgeRepository(session)
        self._outbox = OutboxRepository(session)
        self._audit = AuditRepository(session)
        self._object_store = object_store or MinioObjectStore(settings)
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _not_found() -> ApplicationError:
        return ApplicationError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="知识库资源不存在或当前不可见。",
        )

    async def overview(self) -> KnowledgeOverviewResponse:
        run = await self._repo.latest_succeeded_run()
        if run is None:
            return KnowledgeOverviewResponse(snapshot=None)
        nodes = await self._repo.list_nodes(run.id)
        documents = await self._repo.list_documents(run.id)
        document_by_node = {document.node_id: document for document in documents}
        return KnowledgeOverviewResponse(
            snapshot=_snapshot(run),
            nodes=[
                KnowledgeNodeResponse(
                    id=node.id,
                    parent_id=node.parent_id,
                    document_id=(
                        document_by_node[node.id].id if node.id in document_by_node else None
                    ),
                    title=node.title,
                    node_type=cast(Any, node.node_type),
                    depth=node.depth,
                    display_order=node.display_order,
                    source_url=node.source_url,
                )
                for node in nodes
            ],
            documents=[
                KnowledgeDocumentSummary(
                    id=document.id,
                    title=document.title,
                    source_url=document.source_url,
                    source_token=document.external_document_id,
                    display_order=document.display_order,
                )
                for document in documents
            ],
        )

    async def document(self, document_id: UUID) -> KnowledgeDocumentResponse:
        run = await self._repo.latest_succeeded_run()
        if run is None or run.finished_at is None:
            raise self._not_found()
        document = await self._repo.get_document(run.id, document_id)
        if document is None:
            raise self._not_found()
        return KnowledgeDocumentResponse(
            id=document.id,
            title=document.title,
            source_url=document.source_url,
            source_token=document.external_document_id,
            display_order=document.display_order,
            synced_at=run.finished_at,
            blocks=document.blocks,
        )

    async def admin_status(self, *, context: AuthenticatedContext) -> KnowledgeAdminResponse:
        if not context_is_admin(context):
            raise ApplicationError(
                status_code=403, code="FORBIDDEN", message="仅管理员可以查看同步状态。"
            )
        succeeded = await self._repo.latest_succeeded_run()
        latest = await self._repo.latest_run()
        return KnowledgeAdminResponse(
            configured=self._settings.feishu_knowledge_configured,
            current_snapshot=_snapshot(succeeded),
            latest_run=_run_response(latest) if latest is not None else None,
        )

    async def trigger_sync(
        self,
        *,
        audit_context: KnowledgeAuditContext,
    ) -> KnowledgeSyncCreatedResponse:
        if not context_is_admin(audit_context.actor):
            raise ApplicationError(
                status_code=403, code="FORBIDDEN", message="仅管理员可以触发知识库同步。"
            )
        if not self._settings.feishu_knowledge_configured:
            raise ApplicationError(
                status_code=503,
                code="KNOWLEDGE_SYNC_NOT_CONFIGURED",
                message="飞书知识库同步尚未配置，请联系部署管理员。",
            )
        if await self._repo.active_run() is not None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="KNOWLEDGE_SYNC_IN_PROGRESS",
                message="已有知识库同步正在进行。",
            )
        now = self._clock()
        run = KnowledgeSyncRun(
            id=uuid7(),
            status="pending",
            source_url=str(self._settings.feishu_wiki_url),
            triggered_by=audit_context.actor.user.id,
            started_at=None,
            finished_at=None,
            document_count=0,
            asset_count=0,
            error_code=None,
            error_summary=None,
            created_at=now,
        )
        self._repo.add_run(run)
        self._outbox.add(
            OutboxJob(
                id=uuid7(),
                job_type="sync_knowledge",
                event_key=f"knowledge_sync:{run.id}",
                payload={"run_id": str(run.id)},
                secret_payload_ciphertext=None,
                status="pending",
                available_at=now,
                attempt_count=0,
                max_attempts=3,
                locked_by=None,
                locked_at=None,
                last_error_code=None,
                last_error_summary=None,
                created_at=now,
                sent_at=None,
            )
        )
        self._audit.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=audit_context.actor.user.id,
                action="knowledge.sync_trigger",
                target_type="knowledge_sync_run",
                target_id=run.id,
                request_id=audit_context.request_id,
                ip_prefix=audit_context.ip_prefix,
                result="success",
                change_summary={},
                created_at=now,
            )
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="KNOWLEDGE_SYNC_IN_PROGRESS",
                message="已有知识库同步正在进行。",
            ) from exc
        return KnowledgeSyncCreatedResponse(run=_run_response(run))

    async def asset_url(self, asset_id: UUID) -> str:
        run = await self._repo.latest_succeeded_run()
        if run is None:
            raise self._not_found()
        asset = await self._repo.current_asset(run.id, asset_id)
        if asset is None:
            raise self._not_found()
        try:
            if asset.asset_kind in {"image", "whiteboard"}:
                return await self._object_store.presign_inline(
                    object_key=asset.object_key,
                    file_name=asset.file_name,
                    content_type=asset.media_type,
                    expires_seconds=300,
                )
            return await self._object_store.presign_download(
                object_key=asset.object_key,
                file_name=asset.file_name,
                expires_seconds=300,
            )
        except ObjectStoreError as exc:
            raise ApplicationError(
                status_code=503,
                code="DEPENDENCY_UNAVAILABLE",
                message="知识库媒体暂时不可用，请稍后重试。",
            ) from exc


class KnowledgeSynchronizer:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        transport: HttpTransport | None = None,
        object_store: MinioObjectStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._transport = transport
        self._object_store = object_store or MinioObjectStore(settings)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._drive_download_lock = asyncio.Lock()

    @staticmethod
    def _log_progress(stage: str, completed: int, total: int) -> None:
        if completed == total or completed % _PROGRESS_LOG_INTERVAL == 0:
            logger.info(
                "knowledge_sync_progress",
                extra={
                    "event": "knowledge_sync_progress",
                    "stage": stage,
                    "completed": completed,
                    "total": total,
                },
            )

    async def _set_running(self, run_id: UUID) -> bool:
        async with self._factory() as session, session.begin():
            run = await KnowledgeRepository(session).get_run(run_id, for_update=True)
            if run is None:
                raise KnowledgeSyncError("KNOWLEDGE_RUN_NOT_FOUND", permanent=True)
            if run.status == "succeeded":
                return False
            run.status = "running"
            run.started_at = run.started_at or self._clock()
            run.finished_at = None
            run.error_code = None
            run.error_summary = None
        return True

    async def mark_failed(self, run_id: UUID, error: KnowledgeSyncError) -> None:
        async with self._factory() as session, session.begin():
            run = await KnowledgeRepository(session).get_run(run_id, for_update=True)
            if run is None or run.status == "succeeded":
                return
            run.status = "failed"
            run.finished_at = self._clock()
            run.error_code = error.code[:100]
            run.error_summary = _sync_error_summary(error.code)

    @staticmethod
    def _image_type(content: bytes) -> tuple[str, str]:
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png", "image/png"
        if content.startswith(b"\xff\xd8\xff"):
            return "jpg", "image/jpeg"
        if content.startswith((b"GIF87a", b"GIF89a")):
            return "gif", "image/gif"
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            return "webp", "image/webp"
        raise FileValidationError("FILE_CONTENT_MISMATCH")

    async def _prepare_asset(
        self,
        client: FeishuClient,
        reference: AssetReference,
        *,
        now: datetime,
    ) -> KnowledgeAsset:
        if reference.kind == "whiteboard":
            return await self._download_and_store_asset(client, reference, now=now)
        async with self._drive_download_lock:
            await asyncio.sleep(_DRIVE_DOWNLOAD_DELAY_SECONDS)
            return await self._download_and_store_asset(client, reference, now=now)

    async def _download_and_store_asset(
        self,
        client: FeishuClient,
        reference: AssetReference,
        *,
        now: datetime,
    ) -> KnowledgeAsset:
        content, reported_type = await client.download_asset(reference.token, reference.kind)
        asset_id = uuid7()
        if reference.kind in {"image", "whiteboard"}:
            extension, media_type = self._image_type(content)
            file_name = (
                "白板." + extension if reference.kind == "whiteboard" else "知识库图片." + extension
            )
        else:
            file_name, extension = normalize_file_name(reference.file_name)
            inspection = ObjectInspection(
                size_bytes=len(content),
                sha256="",
                first_bytes=content[:32],
                content_type=(reported_type or "").split(";", 1)[0].strip() or None,
            )
            media_type = detect_media_type(extension, inspection)
        object_key = f"knowledge/{asset_id}/{uuid7()}.{extension}"
        stored = await self._object_store.import_bytes(
            object_key,
            content,
            content_type=media_type,
        )
        return KnowledgeAsset(
            id=asset_id,
            external_asset_token=reference.token,
            asset_kind=reference.kind,
            object_key=object_key,
            file_name=file_name,
            media_type=media_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            width=reference.width,
            height=reference.height,
            created_at=now,
            last_seen_at=now,
        )

    async def _read_existing_assets(
        self, references: list[AssetReference]
    ) -> dict[tuple[str, str], KnowledgeAsset]:
        async with self._factory() as session:
            return await KnowledgeRepository(session).assets_by_external_keys(
                (reference.token, reference.kind) for reference in references
            )

    async def _persist(
        self,
        run_id: UUID,
        *,
        raw_nodes: list[dict[str, Any]],
        documents: list[_PreparedDocument],
        assets: dict[tuple[str, str], KnowledgeAsset],
        new_assets: list[KnowledgeAsset],
        now: datetime,
    ) -> None:
        async with self._factory() as session, session.begin():
            repo = KnowledgeRepository(session)
            run = await repo.get_run(run_id, for_update=True)
            if run is None:
                raise KnowledgeSyncError("KNOWLEDGE_RUN_NOT_FOUND", permanent=True)
            if run.status == "succeeded":
                return
            await repo.clear_run_snapshot(run_id)
            for asset in new_assets:
                repo.add_asset(asset)
            await repo.touch_assets(
                (asset.id for asset in assets.values() if asset not in new_assets),
                now,
            )

            nodes_by_token: dict[str, KnowledgeNode] = {}
            for order, raw in enumerate(raw_nodes):
                node_token = raw.get("node_token")
                if not isinstance(node_token, str) or not node_token:
                    continue
                object_token = raw.get("obj_token")
                object_type = str(raw.get("obj_type") or "unknown")[:32]
                is_document = object_type == "docx" and isinstance(object_token, str)
                has_child = raw.get("has_child") is True
                node_type = (
                    "document"
                    if is_document
                    else "folder"
                    if object_type == "folder" or has_child
                    else "unsupported"
                )
                node = KnowledgeNode(
                    id=uuid7(),
                    sync_run_id=run_id,
                    parent_id=None,
                    external_node_token=node_token,
                    external_object_token=object_token if isinstance(object_token, str) else None,
                    object_type=object_type,
                    node_type=node_type,
                    title=str(raw.get("title") or "未命名文档")[:500],
                    depth=int(raw.get("_depth") or 0),
                    display_order=order,
                    source_url=client_source_url(self._settings, node_token),
                )
                nodes_by_token[node_token] = node
                repo.add_node(node)
            for raw in raw_nodes:
                node_token = raw.get("node_token")
                parent_token = raw.get("_parent_node_token")
                if (
                    isinstance(node_token, str)
                    and isinstance(parent_token, str)
                    and node_token in nodes_by_token
                    and parent_token in nodes_by_token
                ):
                    nodes_by_token[node_token].parent_id = nodes_by_token[parent_token].id

            await session.flush()

            documents_to_link: list[tuple[KnowledgeDocument, list[AssetReference]]] = []
            for prepared in documents:
                document_node = nodes_by_token.get(prepared.node_token)
                if document_node is None:
                    continue
                document = KnowledgeDocument(
                    id=uuid7(),
                    sync_run_id=run_id,
                    node_id=document_node.id,
                    external_document_id=prepared.external_document_id,
                    title=prepared.title,
                    source_url=prepared.source_url,
                    blocks=normalize_document(
                        prepared.raw_blocks,
                        assets={key: value.id for key, value in assets.items()},
                        asset_names={key: value.file_name for key, value in assets.items()},
                        fallback_url=prepared.source_url,
                        asset_sizes={key: value.size_bytes for key, value in assets.items()},
                        asset_media_types={key: value.media_type for key, value in assets.items()},
                    ),
                    display_order=prepared.display_order,
                    created_at=now,
                )
                repo.add_document(document)
                documents_to_link.append((document, prepared.asset_references))

            await session.flush()
            for document, asset_references in documents_to_link:
                linked: set[tuple[UUID, str]] = set()
                for display_order, reference in enumerate(asset_references):
                    linked_asset = assets.get((reference.token, reference.kind))
                    if linked_asset is None or (linked_asset.id, reference.kind) in linked:
                        continue
                    linked.add((linked_asset.id, reference.kind))
                    repo.add_document_asset(
                        KnowledgeDocumentAsset(
                            document_id=document.id,
                            asset_id=linked_asset.id,
                            usage_type=reference.kind,
                            display_order=display_order,
                        )
                    )
            run.status = "succeeded"
            run.finished_at = now
            run.document_count = len(documents)
            run.asset_count = len({asset.id for asset in assets.values()})
            run.error_code = None
            run.error_summary = None

    async def synchronize(self, run_id: UUID) -> None:
        if not await self._set_running(run_id):
            return
        stage = "initializing"
        try:
            client = FeishuClient(self._settings, transport=self._transport)
            await client.tenant_token()
            stage = "listing_nodes"
            raw_nodes = await client.list_nodes()
            document_nodes = [
                node
                for node in raw_nodes
                if node.get("obj_type") == "docx" and isinstance(node.get("obj_token"), str)
            ]
            if not document_nodes:
                raise KnowledgeSyncError("KNOWLEDGE_DOCUMENTS_NOT_FOUND", permanent=True)
            if len(document_nodes) > self._settings.feishu_knowledge_max_documents:
                raise KnowledgeSyncError("KNOWLEDGE_DOCUMENT_LIMIT_EXCEEDED", permanent=True)

            now = self._clock()
            documents: list[_PreparedDocument] = []
            all_references: dict[tuple[str, str], AssetReference] = {}
            assets: dict[tuple[str, str], KnowledgeAsset] = {}
            new_assets: list[KnowledgeAsset] = []
            stage = "documents"
            for display_order, node in enumerate(document_nodes):
                object_token = cast(str, node["obj_token"])
                node_token = cast(str, node["node_token"])
                blocks = await client.document_blocks(object_token)
                title = await client.document_title(object_token)
                references = discover_asset_references(blocks)
                for reference in references:
                    all_references[(reference.token, reference.kind)] = reference
                if len(all_references) > self._settings.feishu_knowledge_max_assets:
                    raise KnowledgeSyncError("KNOWLEDGE_ASSET_LIMIT_EXCEEDED", permanent=True)

                existing_assets = await self._read_existing_assets(references)
                assets.update(existing_assets)
                stage = "assets"

                async def prepare_reference(
                    reference: AssetReference,
                ) -> tuple[tuple[str, str], KnowledgeAsset | None]:
                    key = (reference.token, reference.kind)
                    if key in assets:
                        return key, assets[key]
                    try:
                        asset = await self._prepare_asset(client, reference, now=now)
                    except (KnowledgeSyncError, FileValidationError, ObjectStoreError):
                        logger.warning(
                            "knowledge_asset_fallback",
                            extra={
                                "event": "knowledge_asset_fallback",
                                "asset_kind": reference.kind,
                            },
                        )
                        return key, None
                    return key, asset

                attachment_references = [
                    reference for reference in references if reference.kind == "attachment"
                ]
                visual_references = [
                    reference for reference in references if reference.kind != "attachment"
                ]
                for reference in attachment_references:
                    key, asset = await prepare_reference(reference)
                    if asset is None or key in assets:
                        continue
                    assets[key] = asset
                    new_assets.append(asset)

                prepared_visuals = await asyncio.gather(
                    *(prepare_reference(reference) for reference in visual_references)
                )
                for key, asset in prepared_visuals:
                    if asset is None or key in assets:
                        continue
                    assets[key] = asset
                    new_assets.append(asset)
                documents.append(
                    _PreparedDocument(
                        node_token=node_token,
                        external_document_id=object_token,
                        title=title[:500],
                        source_url=client.source_url(node_token),
                        raw_blocks=blocks,
                        asset_references=references,
                        display_order=display_order,
                    )
                )
                self._log_progress("documents", len(documents), len(document_nodes))
                stage = "documents"

            stage = "persisting"
            await self._persist(
                run_id,
                raw_nodes=raw_nodes,
                documents=documents,
                assets=assets,
                new_assets=new_assets,
                now=self._clock(),
            )
            self._log_progress("completed", len(documents), len(documents))
        except KnowledgeSyncError as exc:
            logger.warning(
                "knowledge_sync_stage_failed",
                extra={
                    "event": "knowledge_sync_stage_failed",
                    "stage": stage,
                    "error_code": exc.code,
                },
            )
            if exc.permanent:
                await self.mark_failed(run_id, exc)
            raise
        except Exception as exc:
            logger.error(
                "knowledge_sync_unexpected_failure",
                extra={
                    "event": "knowledge_sync_unexpected_failure",
                    "stage": stage,
                    "exception_type": type(exc).__name__,
                },
            )
            raise KnowledgeSyncError("KNOWLEDGE_SYNC_FAILED", permanent=False) from exc


def client_source_url(settings: Settings, node_token: str) -> str:
    configured = settings.feishu_wiki_url
    if configured is None:
        raise KnowledgeSyncError("KNOWLEDGE_SYNC_NOT_CONFIGURED", permanent=True)
    from urllib.parse import quote, urlsplit

    parts = urlsplit(str(configured))
    base = f"{parts.scheme}://{parts.netloc}/wiki/"
    return base + quote(node_token, safe="")
