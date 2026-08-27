"""Create student intention surveys and responses."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0009"
down_revision: str | None = "20260826_0008"
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
        "intention_surveys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description_markdown", sa.Text(), server_default="", nullable=False),
        sa.Column("description_html", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("allow_multiple", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("public_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "status IN ('draft', 'open', 'closed', 'archived')", name="status_allowed"
        ),
        sa.CheckConstraint("length(trim(title)) BETWEEN 1 AND 200", name="title_present"),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at", name="window_order"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_token_hash"),
    )
    op.create_index(
        "ix_intention_surveys_status_window",
        "intention_surveys",
        ["status", "starts_at", "ends_at"],
    )

    op.create_table(
        "intention_options",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("survey_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(trim(label)) BETWEEN 1 AND 200", name="label_present"),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.ForeignKeyConstraint(["survey_id"], ["intention_surveys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("survey_id", "display_order"),
    )

    op.create_table(
        "intention_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("survey_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("free_text", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps_and_revision(),
        sa.ForeignKeyConstraint(["survey_id"], ["intention_surveys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("survey_id", "user_id"),
    )

    op.create_table(
        "intention_response_options",
        sa.Column("response_id", sa.Uuid(), nullable=False),
        sa.Column("option_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["response_id"], ["intention_responses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["option_id"], ["intention_options.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("response_id", "option_id"),
    )


def downgrade() -> None:
    op.drop_table("intention_response_options")
    op.drop_table("intention_responses")
    op.drop_table("intention_options")
    op.drop_index("ix_intention_surveys_status_window", table_name="intention_surveys")
    op.drop_table("intention_surveys")
