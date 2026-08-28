"""Track account activity and allow safe cleanup of audience-only accounts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0012"
down_revision: str | None = "20260827_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE users AS target
        SET last_active_at = activity.last_seen_at
        FROM (
            SELECT user_id, MAX(last_seen_at) AS last_seen_at
            FROM sessions
            GROUP BY user_id
        ) AS activity
        WHERE target.id = activity.user_id
        """
    )

    op.drop_constraint(
        "fk_assignment_audience_users_user_id_users",
        "assignment_audience_users",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_assignment_audience_users_user_id_users",
        "assignment_audience_users",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_assignment_audience_users_user_id_users",
        "assignment_audience_users",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_assignment_audience_users_user_id_users",
        "assignment_audience_users",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_column("users", "last_active_at")
