"""增加管理员作业提交完成确认。

Revision ID: 20260908_0023
Revises: 20260908_0022
Create Date: 2026-09-08 16:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0023"
down_revision: str | None = "20260908_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("completed_version_id", sa.Uuid(), nullable=True))
    op.add_column(
        "submissions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("submissions", sa.Column("completed_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_submissions_completed_version_same_submission",
        "submissions",
        "submission_versions",
        ["id", "completed_version_id"],
        ["submission_id", "id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_submissions_completed_by_users",
        "submissions",
        "users",
        ["completed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "completion_state_consistent",
        "submissions",
        "(completed_version_id IS NULL AND completed_at IS NULL) OR "
        "(completed_version_id IS NOT NULL AND completed_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "completion_state_consistent",
        "submissions",
        type_="check",
    )
    op.drop_constraint(
        "fk_submissions_completed_by_users",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_completed_version_same_submission",
        "submissions",
        type_="foreignkey",
    )
    op.drop_column("submissions", "completed_by")
    op.drop_column("submissions", "completed_at")
    op.drop_column("submissions", "completed_version_id")
