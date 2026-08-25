from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements.models import Announcement
from app.assignments.models import Assignment, AssignmentAudienceUser
from app.audit.models import AuditLog
from app.competitions.models import (
    Competition,
    CompetitionRegistration,
    CompetitionTask,
    Team,
    TeamMember,
)
from app.notifications.models import StudentNotification
from app.operations.capacity_seed import (
    CAPACITY_MARKER_REQUEST_ID,
    CapacityDataset,
)
from app.submissions.models import Submission, SubmissionVersion
from app.users.models import Cohort, Direction, User


class CapacitySeedRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_capacity_dataset(self) -> bool:
        marker_id = await self._session.scalar(
            select(AuditLog.id)
            .where(
                AuditLog.action == "test_data.seed_capacity",
                AuditLog.request_id == CAPACITY_MARKER_REQUEST_ID,
            )
            .limit(1)
        )
        return marker_id is not None

    async def store_capacity_dataset(self, dataset: CapacityDataset) -> None:
        await self._session.execute(insert(Cohort), dataset.cohorts)
        await self._session.execute(insert(Direction), dataset.directions)
        await self._session.execute(insert(User), dataset.users)
        await self._session.execute(insert(Announcement), dataset.announcements)
        await self._session.execute(
            insert(StudentNotification),
            dataset.student_notifications,
        )
        await self._session.execute(insert(Assignment), dataset.assignments)
        await self._session.execute(
            insert(AssignmentAudienceUser),
            dataset.assignment_audience_users,
        )
        await self._session.execute(insert(Competition), dataset.competitions)
        await self._session.execute(
            insert(CompetitionTask),
            dataset.competition_tasks,
        )
        await self._session.execute(
            insert(CompetitionRegistration),
            dataset.competition_registrations,
        )
        await self._session.execute(insert(Team), dataset.teams)
        await self._session.execute(insert(TeamMember), dataset.team_members)
        await self._session.execute(insert(Submission), dataset.submissions)
        await self._session.execute(
            insert(SubmissionVersion),
            dataset.submission_versions,
        )
        await self._session.execute(insert(AuditLog), dataset.audit_logs)

    async def commit(self) -> None:
        await self._session.commit()
