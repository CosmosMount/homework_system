from app.assignments.models import Assignment


def can_submit_assignment(assignment: Assignment) -> bool:
    return assignment.status == "published" and assignment.deleted_at is None
