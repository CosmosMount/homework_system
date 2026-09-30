"""Assignment access after removing deadline and extension rules."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_assignments import make_assignment

from app.assignments.policy import can_submit_assignment
from app.assignments.repository import StudentAssignmentRecord
from app.assignments.service import AssignmentService
from app.submissions.models import Submission, SubmissionVersion
from app.submissions.repository import AssignmentSubmissionRecord


@pytest.mark.parametrize("feedback", [False, True])
@pytest.mark.parametrize("days_after_legacy_deadline", [0, 1, 100])
def test_published_assignment_stays_open_regardless_of_feedback_or_legacy_time(
    feedback: bool,
    days_after_legacy_deadline: int,
) -> None:
    now = datetime.now(UTC)
    assignment = make_assignment(
        status="published", deadline=now - timedelta(days=days_after_legacy_deadline)
    )
    assert can_submit_assignment(assignment)
    assignment.deadline = None
    assignment.review_deadline = None
    assert can_submit_assignment(assignment)


@pytest.mark.parametrize("completion", ["none", "current", "previous"])
def test_student_summary_completion_follows_latest_version(completion: str) -> None:
    now = datetime.now(UTC)
    assignment = make_assignment(status="published")
    submission_id, latest_id, previous_id = uuid4(), uuid4(), uuid4()
    completed_id = {"none": None, "current": latest_id, "previous": previous_id}[completion]
    submission = Submission(
        id=submission_id,
        assignment_id=assignment.id,
        owner_user_id=uuid4(),
        latest_version_id=latest_id,
        completed_version_id=completed_id,
        completed_at=now if completed_id else None,
        created_at=now,
        updated_at=now,
    )
    version = SubmissionVersion(
        id=latest_id,
        submission_id=submission_id,
        version_number=2,
        submitted_by=submission.owner_user_id,
        text_markdown="修正内容",
        text_html="<p>修正内容</p>",
        external_url=None,
        total_file_bytes=0,
        idempotency_key="completion-summary",
        submitted_at=now,
    )
    service = AssignmentService(cast(AsyncSession, AsyncMock(spec=AsyncSession)), clock=lambda: now)
    result = service._student_summary(
        StudentAssignmentRecord(assignment=assignment),
        submission_record=AssignmentSubmissionRecord(
            submission=submission, latest_version=version, has_feedback=True
        ),
    )
    assert result.latest_submission is not None
    assert result.latest_submission.is_completed is (completion == "current")
    assert result.latest_submission.completed_at == (now if completion == "current" else None)
