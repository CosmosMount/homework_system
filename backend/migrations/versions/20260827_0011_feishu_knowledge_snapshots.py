"""Create versioned Feishu knowledge snapshots and protected assets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0011"
down_revision: str | None = "20260827_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("triggered_by", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("asset_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="status_allowed",
        ),
        sa.CheckConstraint("document_count >= 0", name="document_count_nonnegative"),
        sa.CheckConstraint("asset_count >= 0", name="asset_count_nonnegative"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_knowledge_sync_runs_active",
        "knowledge_sync_runs",
        [sa.text("(1)")],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_index(
        "ix_knowledge_sync_runs_finished",
        "knowledge_sync_runs",
        ["status", "finished_at"],
    )

    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sync_run_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("external_node_token", sa.String(length=200), nullable=False),
        sa.Column("external_object_token", sa.String(length=200), nullable=True),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.CheckConstraint("depth >= 0", name="depth_nonnegative"),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.CheckConstraint(
            "node_type IN ('document', 'folder', 'unsupported')",
            name="node_type_allowed",
        ),
        sa.ForeignKeyConstraint(["sync_run_id"], ["knowledge_sync_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sync_run_id", "external_node_token"),
    )
    op.create_index(
        "ix_knowledge_nodes_run_parent_order",
        "knowledge_nodes",
        ["sync_run_id", "parent_id", "display_order"],
    )

    op.create_table(
        "knowledge_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_asset_token", sa.String(length=200), nullable=False),
        sa.Column("asset_kind", sa.String(length=16), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "asset_kind IN ('image', 'whiteboard', 'attachment')",
            name="asset_kind_allowed",
        ),
        sa.CheckConstraint("size_bytes > 0", name="size_bytes_positive"),
        sa.CheckConstraint("width IS NULL OR width > 0", name="width_positive"),
        sa.CheckConstraint("height IS NULL OR height > 0", name="height_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_asset_token", "asset_kind"),
        sa.UniqueConstraint("object_key"),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sync_run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("external_document_id", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("blocks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["knowledge_sync_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sync_run_id", "external_document_id"),
        sa.UniqueConstraint("node_id"),
    )
    op.create_index(
        "ix_knowledge_documents_run_order",
        "knowledge_documents",
        ["sync_run_id", "display_order"],
    )

    op.create_table(
        "knowledge_document_assets",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("usage_type", sa.String(length=16), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.CheckConstraint(
            "usage_type IN ('image', 'whiteboard', 'attachment')",
            name="usage_type_allowed",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["knowledge_assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("document_id", "asset_id", "usage_type"),
    )
    op.create_index(
        "ix_knowledge_document_assets_asset",
        "knowledge_document_assets",
        ["asset_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_document_assets_asset",
        table_name="knowledge_document_assets",
    )
    op.drop_table("knowledge_document_assets")
    op.drop_index("ix_knowledge_documents_run_order", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_assets")
    op.drop_index("ix_knowledge_nodes_run_parent_order", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")
    op.drop_index("ix_knowledge_sync_runs_finished", table_name="knowledge_sync_runs")
    op.drop_index("uq_knowledge_sync_runs_active", table_name="knowledge_sync_runs")
    op.drop_table("knowledge_sync_runs")
