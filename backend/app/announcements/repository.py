from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, delete, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements.models import (
    Announcement,
    AnnouncementCohort,
    AnnouncementDirection,
    AnnouncementFile,
)
from app.notifications.models import StudentNotification
from app.uploads.models import StoredFile
from app.users.models import Cohort, Direction, User


class AnnouncementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, announcement: Announcement) -> None:
        self._session.add(announcement)

    async def get_by_id(
        self,
        announcement_id: UUID,
        *,
        for_update: bool = False,
    ) -> Announcement | None:
        statement = select(Announcement).where(Announcement.id == announcement_id)
        if for_update:
            statement = statement.with_for_update()
        result: Announcement | None = await self._session.scalar(statement)
        return result

    async def audience_ids(self, announcement_id: UUID) -> tuple[set[UUID], set[UUID]]:
        cohort_ids = set(
            (
                await self._session.scalars(
                    select(AnnouncementCohort.cohort_id).where(
                        AnnouncementCohort.announcement_id == announcement_id
                    )
                )
            ).all()
        )
        direction_ids = set(
            (
                await self._session.scalars(
                    select(AnnouncementDirection.direction_id).where(
                        AnnouncementDirection.announcement_id == announcement_id
                    )
                )
            ).all()
        )
        return cohort_ids, direction_ids

    async def replace_audience(
        self,
        announcement_id: UUID,
        *,
        cohort_ids: Sequence[UUID],
        direction_ids: Sequence[UUID],
    ) -> None:
        await self._session.execute(
            delete(AnnouncementCohort).where(AnnouncementCohort.announcement_id == announcement_id)
        )
        await self._session.execute(
            delete(AnnouncementDirection).where(
                AnnouncementDirection.announcement_id == announcement_id
            )
        )
        self._session.add_all(
            [
                AnnouncementCohort(announcement_id=announcement_id, cohort_id=cohort_id)
                for cohort_id in cohort_ids
            ]
        )
        self._session.add_all(
            [
                AnnouncementDirection(
                    announcement_id=announcement_id,
                    direction_id=direction_id,
                )
                for direction_id in direction_ids
            ]
        )

    async def existing_cohort_ids(self, cohort_ids: Sequence[UUID]) -> set[UUID]:
        if not cohort_ids:
            return set()
        return set(
            (await self._session.scalars(select(Cohort.id).where(Cohort.id.in_(cohort_ids)))).all()
        )

    async def existing_direction_ids(self, direction_ids: Sequence[UUID]) -> set[UUID]:
        if not direction_ids:
            return set()
        return set(
            (
                await self._session.scalars(
                    select(Direction.id).where(Direction.id.in_(direction_ids))
                )
            ).all()
        )

    @staticmethod
    def _student_visible_condition(user: User) -> ColumnElement[bool]:
        cohort_configured = exists(
            select(1).where(AnnouncementCohort.announcement_id == Announcement.id)
        )
        direction_configured = exists(
            select(1).where(AnnouncementDirection.announcement_id == Announcement.id)
        )
        cohort_matches: ColumnElement[bool]
        if user.cohort_id is None:
            cohort_matches = false()
        else:
            cohort_matches = exists(
                select(1).where(
                    AnnouncementCohort.announcement_id == Announcement.id,
                    AnnouncementCohort.cohort_id == user.cohort_id,
                )
            )
        direction_matches: ColumnElement[bool]
        if user.direction_id is None:
            direction_matches = false()
        else:
            direction_matches = exists(
                select(1).where(
                    AnnouncementDirection.announcement_id == Announcement.id,
                    AnnouncementDirection.direction_id == user.direction_id,
                )
            )

        union_matches = and_(
            Announcement.audience_match == "union",
            or_(cohort_matches, direction_matches),
        )
        intersection_matches = and_(
            Announcement.audience_match == "intersection",
            or_(cohort_configured, direction_configured),
            or_(~cohort_configured, cohort_matches),
            or_(~direction_configured, direction_matches),
        )
        return or_(
            Announcement.all_students.is_(True),
            and_(
                Announcement.all_students.is_(False),
                or_(union_matches, intersection_matches),
            ),
        )

    async def list_for_student(
        self,
        *,
        user: User,
        page: int,
        page_size: int,
        query: str | None,
        unread: bool | None,
        now: object,
        include_total: bool = True,
    ) -> tuple[list[Announcement], int]:
        filters: list[ColumnElement[bool]] = [
            Announcement.status == "published",
            self._student_visible_condition(user),
        ]
        if query:
            pattern = f"%{query.strip()}%"
            filters.append(
                or_(
                    Announcement.title.ilike(pattern),
                    Announcement.summary.ilike(pattern),
                )
            )
        if unread is not None:
            unread_exists = exists(
                select(1).where(
                    StudentNotification.user_id == user.id,
                    StudentNotification.target_type == "announcement",
                    StudentNotification.target_id == Announcement.id,
                    StudentNotification.read_at.is_(None),
                )
            )
            filters.append(unread_exists if unread else ~unread_exists)

        count = 0
        if include_total:
            count = int(
                await self._session.scalar(
                    select(func.count()).select_from(Announcement).where(*filters)
                )
                or 0
            )
        is_pinned = and_(
            Announcement.pinned_until.is_not(None),
            Announcement.pinned_until > now,
        )
        statement: Select[tuple[Announcement]] = (
            select(Announcement)
            .where(*filters)
            .order_by(
                is_pinned.desc(),
                Announcement.published_at.desc(),
                Announcement.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self._session.scalars(statement)).all())
        return items, count

    async def list_for_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        query: str | None,
    ) -> tuple[list[Announcement], int]:
        filters: list[ColumnElement[bool]] = []
        if status is not None:
            filters.append(Announcement.status == status)
        if query:
            pattern = f"%{query.strip()}%"
            filters.append(
                or_(
                    Announcement.title.ilike(pattern),
                    Announcement.summary.ilike(pattern),
                )
            )
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(Announcement).where(*filters)
            )
            or 0
        )
        items = list(
            (
                await self._session.scalars(
                    select(Announcement)
                    .where(*filters)
                    .order_by(Announcement.created_at.desc(), Announcement.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return items, total

    async def audience_users(self, announcement: Announcement) -> list[User]:
        cohort_ids, direction_ids = await self.audience_ids(announcement.id)
        filters: list[ColumnElement[bool]] = [
            User.role == "student",
            User.status == "active",
        ]
        if not announcement.all_students:
            cohort_match = User.cohort_id.in_(cohort_ids) if cohort_ids else false()
            direction_match = User.direction_id.in_(direction_ids) if direction_ids else false()
            if announcement.audience_match == "union":
                filters.append(or_(cohort_match, direction_match))
            else:
                if cohort_ids:
                    filters.append(cohort_match)
                if direction_ids:
                    filters.append(direction_match)
        return list(
            (await self._session.scalars(select(User).where(*filters).order_by(User.id))).all()
        )

    async def unread_target_ids(
        self,
        *,
        user_id: UUID,
        announcement_ids: Sequence[UUID],
    ) -> set[UUID]:
        if not announcement_ids:
            return set()
        return set(
            (
                await self._session.scalars(
                    select(StudentNotification.target_id).where(
                        StudentNotification.user_id == user_id,
                        StudentNotification.target_type == "announcement",
                        StudentNotification.target_id.in_(announcement_ids),
                        StudentNotification.read_at.is_(None),
                    )
                )
            ).all()
        )

    async def notification_ids_for_target(
        self,
        *,
        user_id: UUID,
        announcement_id: UUID,
    ) -> list[UUID]:
        return list(
            (
                await self._session.scalars(
                    select(StudentNotification.id).where(
                        StudentNotification.user_id == user_id,
                        StudentNotification.target_type == "announcement",
                        StudentNotification.target_id == announcement_id,
                        StudentNotification.read_at.is_(None),
                    )
                )
            ).all()
        )

    async def attachment_file_ids(
        self,
        announcement_id: UUID,
    ) -> list[UUID]:
        return list(
            (
                await self._session.scalars(
                    select(AnnouncementFile.file_id)
                    .where(AnnouncementFile.announcement_id == announcement_id)
                    .order_by(AnnouncementFile.display_order)
                )
            ).all()
        )

    async def attachments(self, announcement_id: UUID) -> list[StoredFile]:
        return list(
            (
                await self._session.scalars(
                    select(StoredFile)
                    .join(AnnouncementFile, AnnouncementFile.file_id == StoredFile.id)
                    .where(AnnouncementFile.announcement_id == announcement_id)
                    .order_by(AnnouncementFile.display_order)
                )
            ).all()
        )

    async def announcement_ids_with_attachments(
        self,
        announcement_ids: Sequence[UUID],
    ) -> set[UUID]:
        if not announcement_ids:
            return set()
        return set(
            (
                await self._session.scalars(
                    select(AnnouncementFile.announcement_id)
                    .where(AnnouncementFile.announcement_id.in_(announcement_ids))
                    .distinct()
                )
            ).all()
        )

    async def replace_files(
        self,
        announcement_id: UUID,
        file_ids: Sequence[UUID],
    ) -> None:
        await self._session.execute(
            delete(AnnouncementFile).where(AnnouncementFile.announcement_id == announcement_id)
        )
        self._session.add_all(
            [
                AnnouncementFile(
                    announcement_id=announcement_id,
                    file_id=file_id,
                    display_order=index,
                )
                for index, file_id in enumerate(file_ids)
            ]
        )

    async def published_recipient_count(self, announcement_id: UUID) -> int:
        value = await self._session.scalar(
            select(func.count())
            .select_from(StudentNotification)
            .where(
                StudentNotification.target_type == "announcement",
                StudentNotification.target_id == announcement_id,
                StudentNotification.notification_type == "announcement",
            )
        )
        return int(value or 0)
