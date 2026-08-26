"""Persist the temporary admin student-view mode on each Session."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0008"
down_revision: str | None = "20260825_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("student_view", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("sessions", "student_view", server_default=None)


def downgrade() -> None:
    op.drop_column("sessions", "student_view")
