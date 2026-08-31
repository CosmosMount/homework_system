"""区分手工归档与管理员删除后的通知、作业。

Revision ID: 20260831_0017
Revises: 20260830_0016
Create Date: 2026-08-31 10:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0017"
down_revision: str | None = "20260830_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "announcements",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "assignments",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        UPDATE announcements AS announcement
        SET deleted_at = deleted_events.deleted_at
        FROM (
            SELECT target_id, MIN(created_at) AS deleted_at
            FROM audit_logs
            WHERE action = 'announcement.delete'
              AND target_type = 'announcement'
              AND result = 'success'
              AND change_summary ->> 'deletion_mode' = 'archive'
            GROUP BY target_id
        ) AS deleted_events
        WHERE announcement.id = deleted_events.target_id
          AND announcement.status = 'archived'
        """
    )
    op.execute(
        """
        UPDATE assignments AS assignment
        SET deleted_at = deleted_events.deleted_at
        FROM (
            SELECT target_id, MIN(created_at) AS deleted_at
            FROM audit_logs
            WHERE action = 'assignment.delete'
              AND target_type = 'assignment'
              AND result = 'success'
              AND change_summary ->> 'deletion_mode' = 'archive'
            GROUP BY target_id
        ) AS deleted_events
        WHERE assignment.id = deleted_events.target_id
          AND assignment.status = 'archived'
        """
    )

    op.create_check_constraint(
        "deleted_requires_archived",
        "announcements",
        "deleted_at IS NULL OR status = 'archived'",
    )
    op.create_check_constraint(
        "deleted_requires_archived",
        "assignments",
        "deleted_at IS NULL OR status = 'archived'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "deleted_requires_archived",
        "assignments",
        type_="check",
    )
    op.drop_constraint(
        "deleted_requires_archived",
        "announcements",
        type_="check",
    )
    op.drop_column("assignments", "deleted_at")
    op.drop_column("announcements", "deleted_at")
