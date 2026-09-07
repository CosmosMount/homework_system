"""增加组队个人简介和站内邀请。

Revision ID: 20260907_0021
Revises: 20260904_0020
Create Date: 2026-09-07 10:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0021"
down_revision: str | None = "20260904_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps_and_revision() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "team_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("introduction", sa.Text(), nullable=False),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "length(trim(introduction)) BETWEEN 1 AND 2000", name="introduction_present"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_team_profiles_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_team_profiles"),
    )
    op.create_index("ix_team_profiles_updated_at", "team_profiles", ["updated_at"])
    op.create_table(
        "team_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("invitee_user_id", sa.Uuid(), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')", name="status_allowed"
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND responded_at IS NULL) OR "
            "(status <> 'pending' AND responded_at IS NOT NULL)",
            name="response_state_consistent",
        ),
        sa.CheckConstraint("invitee_user_id <> invited_by_user_id", name="different_users"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="fk_team_invitations_team_id_teams", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["invitee_user_id"],
            ["users.id"],
            name="fk_team_invitations_invitee_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name="fk_team_invitations_invited_by_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_team_invitations"),
    )
    op.create_index(
        "uq_team_invitations_pending_team_invitee",
        "team_invitations",
        ["team_id", "invitee_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_team_invitations_invitee_status_created",
        "team_invitations",
        ["invitee_user_id", "status", "created_at"],
    )
    op.create_index("ix_team_invitations_team_status", "team_invitations", ["team_id", "status"])


def downgrade() -> None:
    op.drop_table("team_invitations")
    op.drop_index("ix_team_profiles_updated_at", table_name="team_profiles")
    op.drop_table("team_profiles")
