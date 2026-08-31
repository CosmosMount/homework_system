from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import (
    KnowledgeAsset,
    KnowledgeDocument,
    KnowledgeDocumentAsset,
    KnowledgeNode,
    KnowledgeSyncRun,
)


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_run(self, run: KnowledgeSyncRun) -> None:
        self._session.add(run)

    def add_node(self, node: KnowledgeNode) -> None:
        self._session.add(node)

    def add_document(self, document: KnowledgeDocument) -> None:
        self._session.add(document)

    def add_asset(self, asset: KnowledgeAsset) -> None:
        self._session.add(asset)

    def add_document_asset(self, link: KnowledgeDocumentAsset) -> None:
        self._session.add(link)

    async def get_run(self, run_id: UUID, *, for_update: bool = False) -> KnowledgeSyncRun | None:
        statement = select(KnowledgeSyncRun).where(KnowledgeSyncRun.id == run_id)
        if for_update:
            statement = statement.with_for_update()
        result: KnowledgeSyncRun | None = await self._session.scalar(statement)
        return result

    async def latest_run(self) -> KnowledgeSyncRun | None:
        result: KnowledgeSyncRun | None = await self._session.scalar(
            select(KnowledgeSyncRun).order_by(
                KnowledgeSyncRun.created_at.desc(), KnowledgeSyncRun.id.desc()
            )
        )
        return result

    async def active_run(self) -> KnowledgeSyncRun | None:
        result: KnowledgeSyncRun | None = await self._session.scalar(
            select(KnowledgeSyncRun)
            .where(KnowledgeSyncRun.status.in_(("pending", "running")))
            .order_by(KnowledgeSyncRun.created_at.desc())
            .with_for_update()
        )
        return result

    async def latest_succeeded_run(self) -> KnowledgeSyncRun | None:
        result: KnowledgeSyncRun | None = await self._session.scalar(
            select(KnowledgeSyncRun)
            .where(KnowledgeSyncRun.status == "succeeded")
            .order_by(
                KnowledgeSyncRun.finished_at.desc(),
                KnowledgeSyncRun.created_at.desc(),
                KnowledgeSyncRun.id.desc(),
            )
        )
        return result

    async def list_nodes(self, run_id: UUID) -> list[KnowledgeNode]:
        return list(
            (
                await self._session.scalars(
                    select(KnowledgeNode)
                    .where(KnowledgeNode.sync_run_id == run_id)
                    .order_by(KnowledgeNode.display_order, KnowledgeNode.id)
                )
            ).all()
        )

    async def list_documents(self, run_id: UUID) -> list[KnowledgeDocument]:
        return list(
            (
                await self._session.scalars(
                    select(KnowledgeDocument)
                    .where(KnowledgeDocument.sync_run_id == run_id)
                    .order_by(KnowledgeDocument.display_order, KnowledgeDocument.id)
                )
            ).all()
        )

    async def get_document(self, run_id: UUID, document_id: UUID) -> KnowledgeDocument | None:
        result: KnowledgeDocument | None = await self._session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.sync_run_id == run_id,
            )
        )
        return result

    async def assets_by_external_keys(
        self, keys: Iterable[tuple[str, str]]
    ) -> dict[tuple[str, str], KnowledgeAsset]:
        values = list(keys)
        if not values:
            return {}
        tokens = {token for token, _ in values}
        kinds = {kind for _, kind in values}
        assets = list(
            (
                await self._session.scalars(
                    select(KnowledgeAsset).where(
                        KnowledgeAsset.external_asset_token.in_(tokens),
                        KnowledgeAsset.asset_kind.in_(kinds),
                    )
                )
            ).all()
        )
        requested = set(values)
        return {
            (asset.external_asset_token, asset.asset_kind): asset
            for asset in assets
            if (asset.external_asset_token, asset.asset_kind) in requested
        }

    async def touch_assets(self, asset_ids: Iterable[UUID], seen_at: datetime) -> None:
        values = list(asset_ids)
        if values:
            await self._session.execute(
                update(KnowledgeAsset)
                .where(KnowledgeAsset.id.in_(values))
                .values(last_seen_at=seen_at)
            )

    async def current_asset(self, run_id: UUID, asset_id: UUID) -> KnowledgeAsset | None:
        document_asset_ids = (
            select(KnowledgeDocumentAsset.asset_id)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeDocumentAsset.document_id,
            )
            .where(KnowledgeDocument.sync_run_id == run_id)
        )
        node_asset_ids = select(KnowledgeNode.asset_id).where(
            KnowledgeNode.sync_run_id == run_id,
            KnowledgeNode.asset_id.is_not(None),
        )
        result: KnowledgeAsset | None = await self._session.scalar(
            select(KnowledgeAsset)
            .where(
                KnowledgeAsset.id == asset_id,
                or_(
                    KnowledgeAsset.id.in_(document_asset_ids),
                    KnowledgeAsset.id.in_(node_asset_ids),
                ),
            )
            .limit(1)
        )
        return result

    async def clear_run_snapshot(self, run_id: UUID) -> None:
        await self._session.execute(
            delete(KnowledgeNode).where(KnowledgeNode.sync_run_id == run_id)
        )
        await self._session.flush()
