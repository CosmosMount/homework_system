"""Add captain reviewed team applications."""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_0030"
down_revision: str | None = "20260927_0029"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "team_applications",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "applicant_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
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
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')", name="status_allowed"
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND responded_at IS NULL) OR "
            "(status <> 'pending' AND responded_at IS NOT NULL)",
            name="response_state_consistent",
        ),
    )
    op.create_index(
        "uq_team_applications_pending_team_applicant",
        "team_applications",
        ["team_id", "applicant_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_team_applications_team_status_created",
        "team_applications",
        ["team_id", "status", "created_at"],
    )
    op.create_index(
        "ix_team_applications_applicant_status",
        "team_applications",
        ["applicant_user_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("team_applications")
