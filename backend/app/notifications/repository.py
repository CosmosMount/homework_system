from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements.models import Announcement
from app.notifications.models import OutboxJob, StudentNotification

MAIL_JOB_TYPES = (
    "email_verification",
    "password_reset",
    "security_alert",
    "announcement_email",
    "announcement_update_email",
    "assignment_extension_email",
)


@dataclass(frozen=True, slots=True)
class NotificationUnreadCounts:
    announcements: int
    assignments: int
    competitions: int
    help_requests: int

    @property
    def total(self) -> int:
        return self.announcements + self.assignments + self.competitions + self.help_requests


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, job: OutboxJob) -> None:
        self._session.add(job)

    async def claim(
        self,
        *,
        worker_name: str,
        now: datetime,
        lease_seconds: int,
        limit: int = 10,
    ) -> list[OutboxJob]:
        stale_before = now - timedelta(seconds=lease_seconds)
        statement = (
            select(OutboxJob)
            .where(
                OutboxJob.available_at <= now,
                or_(
                    OutboxJob.status.in_(("pending", "retry")),
                    ((OutboxJob.status == "processing") & (OutboxJob.locked_at < stale_before)),
                ),
            )
            .order_by(OutboxJob.available_at, OutboxJob.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = list((await self._session.scalars(statement)).all())
        for job in jobs:
            job.status = "processing"
            job.locked_by = worker_name
            job.locked_at = now
        return jobs

    async def get_by_id(self, job_id: UUID, *, for_update: bool = False) -> OutboxJob | None:
        statement = select(OutboxJob).where(OutboxJob.id == job_id)
        if for_update:
            statement = statement.with_for_update()
        result: OutboxJob | None = await self._session.scalar(statement)
        return result

    async def get_by_event_key(self, event_key: str) -> OutboxJob | None:
        result: OutboxJob | None = await self._session.scalar(
            select(OutboxJob).where(OutboxJob.event_key == event_key)
        )
        return result

    async def list_jobs(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        job_type: str | None,
    ) -> tuple[list[OutboxJob], int]:
        filters: list[ColumnElement[bool]] = [OutboxJob.job_type.in_(MAIL_JOB_TYPES)]
        if status is not None:
            filters.append(OutboxJob.status == status)
        if job_type is not None:
            filters.append(OutboxJob.job_type == job_type)
        count: int | None = await self._session.scalar(
            select(func.count()).select_from(OutboxJob).where(*filters)
        )
        jobs = list(
            (
                await self._session.scalars(
                    select(OutboxJob)
                    .where(*filters)
                    .order_by(OutboxJob.created_at.desc(), OutboxJob.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return jobs, int(count or 0)


class StudentNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_all(self, notifications: list[StudentNotification]) -> None:
        self._session.add_all(notifications)

    async def get_for_user(
        self,
        notification_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> StudentNotification | None:
        statement = select(StudentNotification).where(
            StudentNotification.id == notification_id,
            StudentNotification.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: StudentNotification | None = await self._session.scalar(statement)
        return result

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        unread_only: bool,
    ) -> tuple[list[StudentNotification], int]:
        filters = [StudentNotification.user_id == user_id]
        if unread_only:
            filters.append(StudentNotification.read_at.is_(None))
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(StudentNotification).where(*filters)
            )
            or 0
        )
        items = list(
            (
                await self._session.scalars(
                    select(StudentNotification)
                    .where(*filters)
                    .order_by(
                        StudentNotification.created_at.desc(),
                        StudentNotification.id.desc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return items, total

    async def unread_counts(self, user_id: UUID) -> NotificationUnreadCounts:
        announcement_target = StudentNotification.target_type == "announcement"
        help_request_target = StudentNotification.target_type == "help_request"
        competition_target = StudentNotification.target_url.startswith("/competitions/")
        assignment_target = and_(
            StudentNotification.target_type.in_(("assignment", "submission")),
            ~competition_target,
        )
        active_target = or_(
            ~announcement_target,
            Announcement.status == "published",
        )
        statement = (
            select(
                func.count().filter(announcement_target),
                func.count().filter(assignment_target),
                func.count().filter(competition_target),
                func.count().filter(help_request_target),
            )
            .select_from(StudentNotification)
            .outerjoin(
                Announcement,
                and_(
                    announcement_target,
                    Announcement.id == StudentNotification.target_id,
                ),
            )
            .where(
                StudentNotification.user_id == user_id,
                StudentNotification.read_at.is_(None),
                active_target,
            )
        )
        row = (await self._session.execute(statement)).one()
        return NotificationUnreadCounts(
            announcements=int(row[0] or 0),
            assignments=int(row[1] or 0),
            competitions=int(row[2] or 0),
            help_requests=int(row[3] or 0),
        )

    async def unread_count(self, user_id: UUID) -> int:
        return (await self.unread_counts(user_id)).total

    async def unread_ids_for_target(
        self,
        *,
        user_id: UUID,
        target_type: str,
        target_id: UUID,
    ) -> list[UUID]:
        return list(
            (
                await self._session.scalars(
                    select(StudentNotification.id).where(
                        StudentNotification.user_id == user_id,
                        StudentNotification.target_type == target_type,
                        StudentNotification.target_id == target_id,
                        StudentNotification.read_at.is_(None),
                    )
                )
            ).all()
        )

    async def unread_for_target(
        self,
        *,
        target_type: str,
        target_id: UUID,
        for_update: bool = False,
    ) -> list[StudentNotification]:
        statement = select(StudentNotification).where(
            StudentNotification.target_type == target_type,
            StudentNotification.target_id == target_id,
            StudentNotification.read_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return list((await self._session.scalars(statement)).all())

    async def unread_before(
        self,
        *,
        user_id: UUID,
        before: datetime,
        notification_type: str | None,
    ) -> list[StudentNotification]:
        filters = [
            StudentNotification.user_id == user_id,
            StudentNotification.read_at.is_(None),
            StudentNotification.created_at <= before,
        ]
        if notification_type is not None:
            filters.append(StudentNotification.notification_type == notification_type)
        return list(
            (
                await self._session.scalars(
                    select(StudentNotification).where(*filters).with_for_update()
                )
            ).all()
        )
