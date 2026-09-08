"""增加学生组队开放开关。

Revision ID: 20260908_0022
Revises: 20260907_0021
Create Date: 2026-09-08 12:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0022"
down_revision: str | None = "20260907_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team_settings",
        sa.Column("id", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_team_open", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("id", name="singleton_id_true"),
        sa.PrimaryKeyConstraint("id", name="pk_team_settings"),
    )
    op.execute("INSERT INTO team_settings (id, is_team_open) VALUES (true, false)")


def downgrade() -> None:
    op.drop_table("team_settings")
