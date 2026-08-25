"""创建作业、个人提交、私密评语与优秀作业表。

Revision ID: 20260824_0004
Revises: 20260824_0003
Create Date: 2026-08-24 22:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0004"
down_revision: str | None = "20260824_0003"
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
        "assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description_markdown", sa.Text(), nullable=False),
        sa.Column("description_html", sa.Text(), nullable=False),
        sa.Column("training_url", sa.String(length=2000), nullable=True),
        sa.Column("submission_instructions", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("all_students", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "audience_match",
            sa.String(length=16),
            server_default="intersection",
            nullable=False,
        ),
        sa.Column(
            "allowed_extensions",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
        ),
        sa.Column("max_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'closed', 'archived')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "audience_match IN ('union', 'intersection')",
            name="audience_match_allowed",
        ),
        sa.CheckConstraint(
            "max_total_bytes BETWEEN 1 AND 2147483648",
            name="max_total_bytes_range",
        ),
        sa.CheckConstraint(
            "cardinality(allowed_extensions) >= 1",
            name="allowed_extensions_present",
        ),
        sa.CheckConstraint("deadline > publish_at", name="deadline_after_publish"),
        sa.CheckConstraint(
            "status = 'draft' OR published_at IS NOT NULL",
            name="published_at_present",
        ),
        sa.CheckConstraint(
            "status NOT IN ('closed', 'archived') OR closed_at IS NOT NULL",
            name="closed_at_present",
        ),
        sa.CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="archived_at_present",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_assignments_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_assignments_updated_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assignments"),
    )
    op.create_index(
        "ix_assignments_status_publish_at",
        "assignments",
        ["status", "publish_at"],
    )
    op.create_index(
        "ix_assignments_status_deadline",
        "assignments",
        ["status", "deadline"],
    )

    op.create_table(
        "assignment_cohorts",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name="fk_assignment_cohorts_assignment_id_assignments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"],
            ["cohorts.id"],
            name="fk_assignment_cohorts_cohort_id_cohorts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("assignment_id", "cohort_id", name="pk_assignment_cohorts"),
    )
    op.create_table(
        "assignment_directions",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("direction_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name="fk_assignment_directions_assignment_id_assignments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["direction_id"],
            ["directions.id"],
            name="fk_assignment_directions_direction_id_directions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "assignment_id",
            "direction_id",
            name="pk_assignment_directions",
        ),
    )
    op.create_table(
        "assignment_audience_users",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id_at_publish", sa.Uuid(), nullable=True),
        sa.Column("direction_id_at_publish", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name="fk_assignment_audience_users_assignment_id_assignments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_assignment_audience_users_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id_at_publish"],
            ["cohorts.id"],
            name="fk_assignment_audience_users_cohort_id_at_publish_cohorts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["direction_id_at_publish"],
            ["directions.id"],
            name="fk_assignment_audience_users_direction_id_at_publish_directions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "assignment_id",
            "user_id",
            name="pk_assignment_audience_users",
        ),
    )
    op.create_index(
        "ix_assignment_audience_users_user_assignment",
        "assignment_audience_users",
        ["user_id", "assignment_id"],
    )
    op.create_table(
        "assignment_extensions",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("extended_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=False),
        *_timestamps_and_revision(),
        sa.CheckConstraint("length(trim(reason)) > 0", name="reason_present"),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name="fk_assignment_extensions_assignment_id_assignments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_assignment_extensions_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"],
            ["users.id"],
            name="fk_assignment_extensions_granted_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "assignment_id",
            "user_id",
            name="pk_assignment_extensions",
        ),
    )
    op.create_index(
        "ix_assignment_extensions_user_assignment",
        "assignment_extensions",
        ["user_id", "assignment_id"],
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("latest_version_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name="fk_submissions_assignment_id_assignments",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_submissions_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submissions"),
    )
    op.create_index(
        "uq_submissions_assignment_owner",
        "submissions",
        ["assignment_id", "owner_user_id"],
        unique=True,
    )

    op.create_table(
        "submission_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("text_markdown", sa.Text(), nullable=True),
        sa.Column("text_html", sa.Text(), nullable=True),
        sa.Column("external_url", sa.String(length=2000), nullable=True),
        sa.Column("total_file_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="version_number_positive"),
        sa.CheckConstraint(
            "total_file_bytes BETWEEN 0 AND 2147483648",
            name="total_file_bytes_range",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name="fk_submission_versions_submission_id_submissions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["users.id"],
            name="fk_submission_versions_submitted_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submission_versions"),
        sa.UniqueConstraint(
            "submission_id",
            "id",
            name="uq_submission_versions_submission_id_id",
        ),
    )
    op.create_index(
        "uq_submission_versions_number",
        "submission_versions",
        ["submission_id", "version_number"],
        unique=True,
    )
    op.create_index(
        "uq_submission_versions_submitter_idempotency",
        "submission_versions",
        ["submitted_by", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_submission_versions_submission_submitted_at",
        "submission_versions",
        ["submission_id", "submitted_at"],
    )
    op.create_foreign_key(
        "fk_submissions_latest_version_same_submission",
        "submissions",
        "submission_versions",
        ["id", "latest_version_id"],
        ["submission_id", "id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_table(
        "version_files",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["submission_versions.id"],
            name="fk_version_files_version_id_submission_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="fk_version_files_file_id_files",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("version_id", "file_id", name="pk_version_files"),
    )
    op.create_index(
        "uq_version_files_file_id",
        "version_files",
        ["file_id"],
        unique=True,
    )
    op.create_index(
        "uq_version_files_display_order",
        "version_files",
        ["version_id", "display_order"],
        unique=True,
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        *_timestamps_and_revision(),
        sa.CheckConstraint("length(trim(body_markdown)) > 0", name="body_present"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["submission_versions.id"],
            name="fk_feedback_version_id_submission_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_feedback_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feedback"),
    )
    op.create_index(
        "uq_feedback_version_id",
        "feedback",
        ["version_id"],
        unique=True,
    )

    op.create_table(
        "assignment_excellent_submissions",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("marked_by", sa.Uuid(), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name="fk_assignment_excellent_submissions_assignment_id_assignments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["submission_versions.id"],
            name="fk_assignment_excellent_version_submission_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["marked_by"],
            ["users.id"],
            name="fk_assignment_excellent_submissions_marked_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "assignment_id",
            "version_id",
            name="pk_assignment_excellent_submissions",
        ),
    )
    op.create_index(
        "uq_assignment_excellent_submissions_version_id",
        "assignment_excellent_submissions",
        ["version_id"],
        unique=True,
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_key", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column(
            "response_body",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "response_status BETWEEN 100 AND 599",
            name="response_status_range",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="request_hash_format",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_idempotency_records_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
    )
    op.create_index(
        "uq_idempotency_records_scope",
        "idempotency_records",
        ["user_id", "endpoint_key", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
    )

    op.execute(
        """
        CREATE FUNCTION pnx_reject_submission_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = 'submission versions are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_submission_versions_immutable
        BEFORE UPDATE OR DELETE ON submission_versions
        FOR EACH ROW
        EXECUTE FUNCTION pnx_reject_submission_version_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_submission_versions_immutable ON submission_versions")
    op.execute("DROP FUNCTION IF EXISTS pnx_reject_submission_version_mutation()")
    op.drop_table("idempotency_records")
    op.drop_table("assignment_excellent_submissions")
    op.drop_table("feedback")
    op.drop_table("version_files")
    op.drop_constraint(
        "fk_submissions_latest_version_same_submission",
        "submissions",
        type_="foreignkey",
    )
    op.drop_table("submission_versions")
    op.drop_table("submissions")
    op.drop_table("assignment_extensions")
    op.drop_table("assignment_audience_users")
    op.drop_table("assignment_directions")
    op.drop_table("assignment_cohorts")
    op.drop_table("assignments")
