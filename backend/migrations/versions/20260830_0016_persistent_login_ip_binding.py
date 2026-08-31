"""为可选持久登录增加精确来源 IP 绑定摘要。

Revision ID: 20260830_0016
Revises: 20260829_0015
Create Date: 2026-08-30 10:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0016"
down_revision: str | None = "20260829_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("ip_binding_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "ip_binding_hash")
