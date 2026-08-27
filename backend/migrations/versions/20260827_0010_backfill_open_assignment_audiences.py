"""Backfill open assignment audiences for students activated after publication."""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0010"
down_revision: str | None = "20260827_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKFILL_CREATED_AT = datetime(2026, 8, 27, 6, 30, tzinfo=UTC)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO assignment_audience_users (
                assignment_id,
                user_id,
                cohort_id_at_publish,
                direction_id_at_publish,
                created_at
            )
            SELECT
                assignment.id,
                student.id,
                student.cohort_id,
                student.direction_id,
                :backfill_created_at
            FROM assignments AS assignment
            CROSS JOIN users AS student
            WHERE assignment.status = 'published'
              AND assignment.deadline > now()
              AND student.role = 'student'
              AND student.status = 'active'
              AND (
                  assignment.all_students
                  OR (
                      NOT assignment.all_students
                      AND (
                          (
                              assignment.audience_match = 'union'
                              AND (
                                  EXISTS (
                                      SELECT 1
                                      FROM assignment_cohorts AS assignment_cohort
                                      WHERE assignment_cohort.assignment_id = assignment.id
                                        AND assignment_cohort.cohort_id = student.cohort_id
                                  )
                                  OR EXISTS (
                                      SELECT 1
                                      FROM assignment_directions AS assignment_direction
                                      WHERE assignment_direction.assignment_id = assignment.id
                                        AND assignment_direction.direction_id = student.direction_id
                                  )
                              )
                          )
                          OR (
                              assignment.audience_match = 'intersection'
                              AND (
                                  EXISTS (
                                      SELECT 1 FROM assignment_cohorts
                                      WHERE assignment_id = assignment.id
                                  )
                                  OR EXISTS (
                                      SELECT 1 FROM assignment_directions
                                      WHERE assignment_id = assignment.id
                                  )
                              )
                              AND (
                                  NOT EXISTS (
                                      SELECT 1 FROM assignment_cohorts
                                      WHERE assignment_id = assignment.id
                                  )
                                  OR EXISTS (
                                      SELECT 1
                                      FROM assignment_cohorts AS assignment_cohort
                                      WHERE assignment_cohort.assignment_id = assignment.id
                                        AND assignment_cohort.cohort_id = student.cohort_id
                                  )
                              )
                              AND (
                                  NOT EXISTS (
                                      SELECT 1 FROM assignment_directions
                                      WHERE assignment_id = assignment.id
                                  )
                                  OR EXISTS (
                                      SELECT 1
                                      FROM assignment_directions AS assignment_direction
                                      WHERE assignment_direction.assignment_id = assignment.id
                                        AND assignment_direction.direction_id = student.direction_id
                                  )
                              )
                          )
                      )
                  )
              )
            ON CONFLICT (assignment_id, user_id) DO NOTHING
            """
        ),
        {"backfill_created_at": _BACKFILL_CREATED_AT},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM assignment_audience_users
            WHERE created_at = :backfill_created_at
            """
        ),
        {"backfill_created_at": _BACKFILL_CREATED_AT},
    )
