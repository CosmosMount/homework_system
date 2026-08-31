"""让知识库目录独立文件关联受保护资源。

Revision ID: 20260831_0018
Revises: 20260831_0017
Create Date: 2026-08-31 16:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0018"
down_revision: str | None = "20260831_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "node_type_allowed",
        "knowledge_nodes",
        type_="check",
    )
    op.create_check_constraint(
        "node_type_allowed",
        "knowledge_nodes",
        "node_type IN ('document', 'folder', 'file', 'unsupported')",
    )
    op.add_column(
        "knowledge_nodes",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_knowledge_nodes_asset_id_knowledge_assets",
        "knowledge_nodes",
        "knowledge_assets",
        ["asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_knowledge_nodes_asset_id",
        "knowledge_nodes",
        ["asset_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE knowledge_nodes
        SET node_type = 'file'
        WHERE object_type = 'file'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE knowledge_nodes
        SET node_type = 'unsupported'
        WHERE node_type = 'file'
        """
    )
    op.drop_index("ix_knowledge_nodes_asset_id", table_name="knowledge_nodes")
    op.drop_constraint(
        "fk_knowledge_nodes_asset_id_knowledge_assets",
        "knowledge_nodes",
        type_="foreignkey",
    )
    op.drop_column("knowledge_nodes", "asset_id")
    op.drop_constraint(
        "node_type_allowed",
        "knowledge_nodes",
        type_="check",
    )
    op.create_check_constraint(
        "node_type_allowed",
        "knowledge_nodes",
        "node_type IN ('document', 'folder', 'unsupported')",
    )
