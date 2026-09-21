"""为作业私密评语增加受保护图片关联。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0026"
down_revision: str | None = "20260910_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OLD_FILE_PURPOSES = (
    "purpose IN ('announcement_attachment', 'assignment_submission', 'competition_submission')"
)
_NEW_FILE_PURPOSES = (
    "purpose IN ('announcement_attachment', 'assignment_submission', "
    "'competition_submission', 'submission_feedback')"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_files_purpose_allowed"), "files", type_="check")
    op.create_check_constraint("purpose_allowed", "files", _NEW_FILE_PURPOSES)
    op.create_table(
        "feedback_files",
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.ForeignKeyConstraint(
            ["feedback_id"],
            ["feedback.id"],
            name="fk_feedback_files_feedback_id_feedback",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="fk_feedback_files_file_id_files",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("feedback_id", "file_id", name="pk_feedback_files"),
    )
    op.create_index(
        "uq_feedback_files_file_id",
        "feedback_files",
        ["file_id"],
        unique=True,
    )
    op.create_index(
        "uq_feedback_files_display_order",
        "feedback_files",
        ["feedback_id", "display_order"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("feedback_files")
    op.execute(
        "UPDATE files SET purpose = 'assignment_submission' WHERE purpose = 'submission_feedback'"
    )
    op.execute(
        "UPDATE upload_sessions SET purpose = 'assignment_submission' "
        "WHERE purpose = 'submission_feedback'"
    )
    op.drop_constraint(op.f("ck_files_purpose_allowed"), "files", type_="check")
    op.create_check_constraint("purpose_allowed", "files", _OLD_FILE_PURPOSES)
