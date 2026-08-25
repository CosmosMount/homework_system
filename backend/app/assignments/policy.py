from datetime import datetime

from app.assignments.models import Assignment, AssignmentExtension


def can_submit_assignment(
    assignment: Assignment,
    extension: AssignmentExtension | None,
    now: datetime,
) -> bool:
    effective_deadline = (
        extension.extended_deadline if extension is not None else assignment.deadline
    )
    if assignment.status == "published":
        return now < effective_deadline
    if (
        assignment.status == "closed"
        and assignment.closed_at is not None
        and assignment.closed_at >= assignment.deadline
    ):
        return now < effective_deadline
    return False
