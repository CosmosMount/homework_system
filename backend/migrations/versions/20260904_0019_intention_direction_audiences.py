"""让问卷按一个或多个技术组限制填写受众。

Revision ID: 20260904_0019
Revises: 20260831_0018
Create Date: 2026-09-04 12:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0019"
down_revision: str | None = "20260831_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "intention_surveys",
        sa.Column(
            "all_students",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.create_table(
        "intention_survey_directions",
        sa.Column("survey_id", sa.Uuid(), nullable=False),
        sa.Column("direction_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["survey_id"],
            ["intention_surveys.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["direction_id"],
            ["directions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("survey_id", "direction_id"),
    )
    op.create_index(
        "ix_intention_survey_directions_direction_id",
        "intention_survey_directions",
        ["direction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intention_survey_directions_direction_id",
        table_name="intention_survey_directions",
    )
    op.drop_table("intention_survey_directions")
    op.drop_column("intention_surveys", "all_students")
