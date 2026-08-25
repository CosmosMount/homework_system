"""创建通知、站内提醒与通知附件上传表。

Revision ID: 20260824_0003
Revises: 20260824_0002
Create Date: 2026-08-24 18:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0003"
down_revision: str | None = "20260824_0002"
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
        "announcements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("all_students", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "audience_match",
            sa.String(length=16),
            server_default="intersection",
            nullable=False,
        ),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pinned_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("send_email", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'published', 'archived')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "audience_match IN ('union', 'intersection')",
            name="audience_match_allowed",
        ),
        sa.CheckConstraint(
            "status <> 'scheduled' OR publish_at IS NOT NULL",
            name="scheduled_publish_at_present",
        ),
        sa.CheckConstraint(
            "status NOT IN ('published', 'archived') OR published_at IS NOT NULL",
            name="published_at_present",
        ),
        sa.CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="archived_at_present",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_announcements_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_announcements_updated_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_announcements"),
    )
    op.create_index(
        "ix_announcements_status_published_at",
        "announcements",
        ["status", "published_at"],
    )
    op.create_index(
        "ix_announcements_status_publish_at",
        "announcements",
        ["status", "publish_at"],
    )
    op.create_table(
        "announcement_cohorts",
        sa.Column("announcement_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name="fk_announcement_cohorts_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"],
            ["cohorts.id"],
            name="fk_announcement_cohorts_cohort_id_cohorts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("announcement_id", "cohort_id", name="pk_announcement_cohorts"),
    )
    op.create_table(
        "announcement_directions",
        sa.Column("announcement_id", sa.Uuid(), nullable=False),
        sa.Column("direction_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name="fk_announcement_directions_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["direction_id"],
            ["directions.id"],
            name="fk_announcement_directions_direction_id_directions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "announcement_id", "direction_id", name="pk_announcement_directions"
        ),
    )
    op.create_table(
        "student_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("target_url", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_student_notifications_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_notifications"),
    )
    op.create_index(
        "uq_student_notifications_user_event",
        "student_notifications",
        ["user_id", "event_key"],
        unique=True,
    )
    op.create_index(
        "ix_student_notifications_user_read_created",
        "student_notifications",
        ["user_id", "read_at", sa.text("created_at DESC")],
    )
    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=False),
        sa.Column("declared_media_type", sa.String(length=200), nullable=False),
        sa.Column("detected_media_type", sa.String(length=200), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('announcement_attachment', 'assignment_submission', "
            "'competition_submission')",
            name="purpose_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('initialized', 'uploading', 'verifying', 'available', "
            "'rejected', 'aborted', 'expired')",
            name="status_allowed",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_files_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_files"),
        sa.UniqueConstraint("object_key", name="uq_files_object_key"),
    )
    op.create_index(
        "ix_files_owner_status_created_at",
        "files",
        ["owner_user_id", "status", "created_at"],
    )
    op.create_index("ix_files_status_created_at", "files", ["status", "created_at"])
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("context_type", sa.String(length=40), nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=False),
        sa.Column("minio_upload_id", sa.Text(), nullable=False),
        sa.Column("part_size_bytes", sa.Integer(), nullable=False),
        sa.Column("part_count", sa.Integer(), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "status IN ('initialized', 'uploading', 'verifying', 'available', "
            "'rejected', 'aborted', 'expired')",
            name="status_allowed",
        ),
        sa.CheckConstraint("part_size_bytes >= 5242880", name="part_size_minimum"),
        sa.CheckConstraint("part_count >= 1", name="part_count_positive"),
        sa.CheckConstraint("expected_size_bytes >= 0", name="expected_size_nonnegative"),
        sa.CheckConstraint("expected_sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="fk_upload_sessions_file_id_files",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_upload_sessions_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_upload_sessions"),
        sa.UniqueConstraint("file_id", name="uq_upload_sessions_file_id"),
    )
    op.create_index(
        "uq_upload_sessions_user_idempotency",
        "upload_sessions",
        ["user_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_upload_sessions_status_expiry",
        "upload_sessions",
        ["status", "expires_at"],
    )
    op.create_table(
        "upload_parts",
        sa.Column("upload_session_id", sa.Uuid(), nullable=False),
        sa.Column("part_number", sa.Integer(), nullable=False),
        sa.Column("etag", sa.String(length=200), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("part_number >= 1", name="part_number_positive"),
        sa.CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        sa.ForeignKeyConstraint(
            ["upload_session_id"],
            ["upload_sessions.id"],
            name="fk_upload_parts_upload_session_id_upload_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("upload_session_id", "part_number", name="pk_upload_parts"),
    )
    op.create_table(
        "announcement_files",
        sa.Column("announcement_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name="fk_announcement_files_announcement_id_announcements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="fk_announcement_files_file_id_files",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("announcement_id", "file_id", name="pk_announcement_files"),
    )
    op.create_index(
        "uq_announcement_files_display_order",
        "announcement_files",
        ["announcement_id", "display_order"],
        unique=True,
    )
    op.create_index(
        "uq_announcement_files_file_id",
        "announcement_files",
        ["file_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("announcement_files")
    op.drop_table("upload_parts")
    op.drop_table("upload_sessions")
    op.drop_table("files")
    op.drop_table("student_notifications")
    op.drop_table("announcement_directions")
    op.drop_table("announcement_cohorts")
    op.drop_table("announcements")
