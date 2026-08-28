"""Upgrade single-question intention surveys to multi-question questionnaires."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0013"
down_revision: str | None = "20260827_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "intention_surveys",
        sa.Column("max_submissions", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "max_submissions_positive",
        "intention_surveys",
        "max_submissions IS NULL OR max_submissions > 0",
    )

    op.create_table(
        "intention_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("survey_id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.String(length=200), nullable=False),
        sa.Column("allow_multiple", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(trim(prompt)) BETWEEN 1 AND 200", name="prompt_present"),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.ForeignKeyConstraint(["survey_id"], ["intention_surveys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("survey_id", "display_order"),
    )
    op.execute(
        """
        INSERT INTO intention_questions (id, survey_id, prompt, allow_multiple, display_order)
        SELECT id, id, title, allow_multiple, 0
        FROM intention_surveys
        """
    )

    op.add_column(
        "intention_options",
        sa.Column("question_id", sa.Uuid(), nullable=True),
    )
    op.execute("UPDATE intention_options SET question_id = survey_id")
    op.alter_column("intention_options", "question_id", nullable=False)
    op.drop_constraint(
        op.f("uq_intention_options_survey_id"),
        "intention_options",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_intention_options_survey_id_intention_surveys"),
        "intention_options",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_intention_options_question_id_intention_questions"),
        "intention_options",
        "intention_questions",
        ["question_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_intention_options_question_id"),
        "intention_options",
        ["question_id", "display_order"],
    )
    op.drop_column("intention_options", "survey_id")
    op.drop_column("intention_surveys", "allow_multiple")

    op.add_column(
        "intention_responses",
        sa.Column(
            "submission_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.execute("UPDATE intention_responses SET submission_count = GREATEST(revision, 1)")
    op.create_check_constraint(
        "submission_count_positive",
        "intention_responses",
        "submission_count > 0",
    )


def downgrade() -> None:
    op.add_column(
        "intention_surveys",
        sa.Column(
            "allow_multiple",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE intention_surveys AS survey
        SET allow_multiple = summary.question_count > 1 OR summary.any_multiple
        FROM (
            SELECT survey_id, COUNT(*) AS question_count, BOOL_OR(allow_multiple) AS any_multiple
            FROM intention_questions
            GROUP BY survey_id
        ) AS summary
        WHERE survey.id = summary.survey_id
        """
    )

    op.add_column(
        "intention_options",
        sa.Column("survey_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        """
        UPDATE intention_options AS option
        SET survey_id = question.survey_id
        FROM intention_questions AS question
        WHERE option.question_id = question.id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                option.id,
                ROW_NUMBER() OVER (
                    PARTITION BY question.survey_id
                    ORDER BY question.display_order, option.display_order, option.id
                ) - 1 AS flattened_order
            FROM intention_options AS option
            JOIN intention_questions AS question ON question.id = option.question_id
        )
        UPDATE intention_options AS option
        SET display_order = ranked.flattened_order
        FROM ranked
        WHERE option.id = ranked.id
        """
    )
    op.alter_column("intention_options", "survey_id", nullable=False)
    op.drop_constraint(
        op.f("uq_intention_options_question_id"),
        "intention_options",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_intention_options_question_id_intention_questions"),
        "intention_options",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_intention_options_survey_id_intention_surveys"),
        "intention_options",
        "intention_surveys",
        ["survey_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_intention_options_survey_id"),
        "intention_options",
        ["survey_id", "display_order"],
    )
    op.drop_column("intention_options", "question_id")
    op.drop_table("intention_questions")

    op.drop_constraint(
        op.f("ck_intention_responses_submission_count_positive"),
        "intention_responses",
        type_="check",
    )
    op.drop_column("intention_responses", "submission_count")
    op.drop_constraint(
        op.f("ck_intention_surveys_max_submissions_positive"),
        "intention_surveys",
        type_="check",
    )
    op.drop_column("intention_surveys", "max_submissions")
