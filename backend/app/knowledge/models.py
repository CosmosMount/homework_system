from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base


class KnowledgeSyncRun(Base):
    __tablename__ = "knowledge_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint("document_count >= 0", name="document_count_nonnegative"),
        CheckConstraint("asset_count >= 0", name="asset_count_nonnegative"),
        Index(
            "uq_knowledge_sync_runs_active",
            text("(1)"),
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
        Index("ix_knowledge_sync_runs_finished", "status", "finished_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    triggered_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    asset_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        CheckConstraint("depth >= 0", name="depth_nonnegative"),
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        CheckConstraint(
            "node_type IN ('document', 'folder', 'unsupported')",
            name="node_type_allowed",
        ),
        UniqueConstraint("sync_run_id", "external_node_token"),
        Index("ix_knowledge_nodes_run_parent_order", "sync_run_id", "parent_id", "display_order"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    sync_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=True
    )
    external_node_token: Mapped[str] = mapped_column(String(200), nullable=False)
    external_object_token: Mapped[str | None] = mapped_column(String(200), nullable=True)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        UniqueConstraint("sync_run_id", "external_document_id"),
        UniqueConstraint("node_id"),
        Index("ix_knowledge_documents_run_order", "sync_run_id", "display_order"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    sync_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    external_document_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeAsset(Base):
    __tablename__ = "knowledge_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_kind IN ('image', 'whiteboard', 'attachment')",
            name="asset_kind_allowed",
        ),
        CheckConstraint("size_bytes > 0", name="size_bytes_positive"),
        CheckConstraint("width IS NULL OR width > 0", name="width_positive"),
        CheckConstraint("height IS NULL OR height > 0", name="height_positive"),
        UniqueConstraint("external_asset_token", "asset_kind"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    external_asset_token: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeDocumentAsset(Base):
    __tablename__ = "knowledge_document_assets"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        CheckConstraint(
            "usage_type IN ('image', 'whiteboard', 'attachment')",
            name="usage_type_allowed",
        ),
        Index("ix_knowledge_document_assets_asset", "asset_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_assets.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    usage_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
