"""创建认证、基础分类、Outbox 与审计表。

Revision ID: 20260824_0002
Revises: 20260823_0001
Create Date: 2026-08-24 14:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0002"
down_revision: str | None = "20260823_0001"
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
        "cohorts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps_and_revision(),
        sa.CheckConstraint("start_year BETWEEN 2000 AND 2200", name="start_year_range"),
        sa.PrimaryKeyConstraint("id", name="pk_cohorts"),
        sa.UniqueConstraint("code", name="uq_cohorts_code"),
    )
    op.create_table(
        "directions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps_and_revision(),
        sa.PrimaryKeyConstraint("id", name="pk_directions"),
        sa.UniqueConstraint("code", name="uq_directions_code"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("student_number", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="student", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending_email", nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=True),
        sa.Column("direction_id", sa.Uuid(), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_by", sa.Uuid(), nullable=True),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps_and_revision(),
        sa.CheckConstraint("role IN ('student', 'admin')", name="role_allowed"),
        sa.CheckConstraint(
            "status IN ('pending_email', 'active', 'disabled')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "email_normalized ~ '^[^@[:space:]]+@hkust-gz\\.edu\\.cn$'",
            name="campus_email",
        ),
        sa.CheckConstraint(
            "status <> 'active' OR email_verified_at IS NOT NULL",
            name="active_email_verified",
        ),
        sa.CheckConstraint(
            "status <> 'disabled' OR (disabled_at IS NOT NULL AND disabled_reason IS NOT NULL)",
            name="disabled_reason_present",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"], ["cohorts.id"], name="fk_users_cohort_id_cohorts", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["direction_id"],
            ["directions.id"],
            name="fk_users_direction_id_directions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["disabled_by"],
            ["users.id"],
            name="fk_users_disabled_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        sa.UniqueConstraint("student_number", name="uq_users_student_number"),
    )
    op.create_index("ix_users_status_created_at", "users", ["status", "created_at"])
    op.create_index(
        "ix_users_cohort_direction_status",
        "users",
        ["cohort_id", "direction_id", "status"],
    )
    op.create_index("ix_users_role_status", "users", ["role", "status"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_secret_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_prefix", sa.String(length=64), nullable=False),
        sa.Column("user_agent_summary", sa.String(length=200), nullable=False),
        sa.CheckConstraint("idle_expires_at <= absolute_expires_at", name="expiry_order"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index(
        "ix_sessions_user_active",
        "sessions",
        ["user_id", "revoked_at", "absolute_expires_at"],
    )
    op.create_table(
        "one_time_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('email_verification', 'password_reset')",
            name="purpose_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_one_time_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_one_time_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_one_time_tokens_token_hash"),
    )
    op.create_index(
        "ix_one_time_tokens_user_purpose",
        "one_time_tokens",
        ["user_id", "purpose", "created_at"],
    )
    op.create_table(
        "auth_security_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("ip_prefix", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_security_events_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_security_events"),
    )
    op.create_index(
        "ix_auth_security_events_email_time",
        "auth_security_events",
        ["email_normalized", "occurred_at"],
    )
    op.create_index(
        "ix_auth_security_events_ip_time",
        "auth_security_events",
        ["ip_prefix", "occurred_at"],
    )
    op.create_table(
        "outbox_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("secret_payload_ciphertext", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("8"), nullable=False),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'retry', 'sent', 'dead')",
            name="status_allowed",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 32", name="max_attempts_range"),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_jobs"),
        sa.UniqueConstraint("event_key", name="uq_outbox_jobs_event_key"),
    )
    op.create_index("ix_outbox_jobs_claim", "outbox_jobs", ["status", "available_at"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("ip_prefix", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column(
            "change_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_logs_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_actor_time", "audit_logs", ["actor_user_id", "created_at"])
    op.create_index(
        "ix_audit_logs_target_time", "audit_logs", ["target_type", "target_id", "created_at"]
    )
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("outbox_jobs")
    op.drop_table("auth_security_events")
    op.drop_table("one_time_tokens")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("directions")
    op.drop_table("cohorts")
