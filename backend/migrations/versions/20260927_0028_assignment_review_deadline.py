"""Add the final assignment revision deadline, preserving existing extensions."""

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0028"
down_revision: str | None = "20260921_0027"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "assignments", sa.Column("review_deadline", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("""
        UPDATE assignments AS assignment
        SET review_deadline = GREATEST(
            assignment.deadline,
            (SELECT MAX(extension.extended_deadline)
             FROM assignment_extensions AS extension
             WHERE extension.assignment_id = assignment.id)
        )
    """)
    op.alter_column("assignments", "review_deadline", nullable=False)
    op.create_check_constraint(
        "review_deadline_after_deadline", "assignments", "review_deadline >= deadline"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_assignments_review_deadline_after_deadline"), "assignments", type_="check"
    )
    op.drop_column("assignments", "review_deadline")
