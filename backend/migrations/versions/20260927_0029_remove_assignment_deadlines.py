"""Remove assignment deadline behavior while preserving legacy timestamps for rollback."""

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0029"
down_revision: str | None = "20260927_0028"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        WITH reopened AS (
            UPDATE assignments AS assignment
            SET status = 'published', closed_at = NULL,
                revision = revision + 1, updated_at = now()
            WHERE assignment.status = 'closed'
              AND assignment.deleted_at IS NULL
              AND (
                  SELECT log.action FROM audit_logs AS log
                  WHERE log.target_type = 'assignment'
                    AND log.target_id = assignment.id
                    AND log.action IN ('assignment.close', 'assignment.close_automatic')
                  ORDER BY log.created_at DESC, log.id DESC LIMIT 1
              ) = 'assignment.close_automatic'
            RETURNING assignment.id
        )
        INSERT INTO audit_logs (
            id, actor_user_id, action, target_type, target_id,
            request_id, ip_prefix, result, change_summary, created_at
        )
        SELECT gen_random_uuid(), NULL, 'assignment.reopen_deadline_removal',
               'assignment', reopened.id, 'migration:20260927_0029',
               'migration', 'success', '{}'::jsonb, now()
        FROM reopened
    """)
    op.execute("""
        UPDATE outbox_jobs
        SET status = 'dead', locked_by = NULL, locked_at = NULL,
            last_error_code = 'DEADLINE_REMOVED',
            last_error_summary = '作业截止规则已移除，任务已取消。'
        WHERE job_type IN ('close_assignment', 'assignment_extension_email')
          AND status IN ('pending', 'retry', 'processing')
    """)
    op.drop_index("ix_assignments_status_deadline", table_name="assignments")
    op.drop_constraint(
        op.f("ck_assignments_review_deadline_after_deadline"), "assignments", type_="check"
    )
    op.drop_constraint(op.f("ck_assignments_deadline_after_publish"), "assignments", type_="check")
    op.alter_column(
        "assignments", "deadline", existing_type=sa.DateTime(timezone=True), nullable=True
    )
    op.alter_column(
        "assignments", "review_deadline", existing_type=sa.DateTime(timezone=True), nullable=True
    )


def downgrade() -> None:
    op.execute("""
        UPDATE assignments AS assignment
        SET status = 'closed', closed_at = assignment.deadline,
            revision = revision + 1, updated_at = now()
        WHERE assignment.status = 'published'
          AND EXISTS (
              SELECT 1 FROM audit_logs AS log
              WHERE log.target_type = 'assignment'
                AND log.target_id = assignment.id
                AND log.action = 'assignment.reopen_deadline_removal'
                AND log.request_id = 'migration:20260927_0029'
          )
    """)
    op.execute("""
        UPDATE assignments
        SET deadline = GREATEST(publish_at + interval '1 day', now() + interval '1 day')
        WHERE deadline IS NULL OR deadline <= publish_at
    """)
    op.execute("""
        UPDATE assignments SET review_deadline = deadline
        WHERE review_deadline IS NULL OR review_deadline < deadline
    """)
    op.alter_column(
        "assignments", "review_deadline", existing_type=sa.DateTime(timezone=True), nullable=False
    )
    op.alter_column(
        "assignments", "deadline", existing_type=sa.DateTime(timezone=True), nullable=False
    )
    op.create_check_constraint("deadline_after_publish", "assignments", "deadline > publish_at")
    op.create_check_constraint(
        "review_deadline_after_deadline", "assignments", "review_deadline >= deadline"
    )
    op.create_index("ix_assignments_status_deadline", "assignments", ["status", "deadline"])
