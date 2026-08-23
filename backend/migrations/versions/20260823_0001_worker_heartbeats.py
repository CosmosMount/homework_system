"""创建 Worker 心跳表。

Revision ID: 20260823_0001
Revises:
Create Date: 2026-08-23 00:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_name", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_name", name="pk_worker_heartbeats"),
    )
    op.create_index(
        "ix_worker_heartbeats_last_heartbeat_at",
        "worker_heartbeats",
        ["last_heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeats_last_heartbeat_at", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
