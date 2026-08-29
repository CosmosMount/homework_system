"""Add private student feedback and help requests."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0014"
down_revision: str | None = "20260828_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "help_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False),
        sa.Column("resolution_markdown", sa.Text(), nullable=True),
        sa.Column("resolution_html", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "request_type IN ('system_feedback', 'question')",
            name="request_type_allowed",
        ),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="status_allowed"),
        sa.CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 200",
            name="title_present",
        ),
        sa.CheckConstraint(
            "length(trim(content_markdown)) BETWEEN 1 AND 20000",
            name="content_present",
        ),
        sa.CheckConstraint(
            """
            (
                status = 'open'
                AND resolution_markdown IS NULL
                AND resolution_html IS NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
            )
            OR
            (
                status = 'resolved'
                AND length(trim(resolution_markdown)) BETWEEN 1 AND 20000
                AND resolution_html IS NOT NULL
                AND resolved_by IS NOT NULL
                AND resolved_at IS NOT NULL
            )
            """,
            name="resolution_state_consistent",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_help_requests_student_list",
        "help_requests",
        ["created_by", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_help_requests_admin_list",
        "help_requests",
        ["status", "request_type", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_help_requests_admin_list", table_name="help_requests")
    op.drop_index("ix_help_requests_student_list", table_name="help_requests")
    op.drop_table("help_requests")
