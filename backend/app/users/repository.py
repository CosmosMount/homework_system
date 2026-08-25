from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import Cohort, Direction, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        result: User | None = await self._session.scalar(statement)
        return result

    async def get_by_email(self, email_normalized: str) -> User | None:
        result: User | None = await self._session.scalar(
            select(User).where(User.email_normalized == email_normalized)
        )
        return result

    async def get_by_student_number(self, student_number: str) -> User | None:
        result: User | None = await self._session.scalar(
            select(User).where(User.student_number == student_number)
        )
        return result

    async def has_other_accounts(self, user_id: UUID) -> bool:
        return bool(await self._session.scalar(select(exists().where(User.id != user_id))))

    def add(self, user: User) -> None:
        self._session.add(user)

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

    async def active_students_for_audience(
        self,
        *,
        all_students: bool,
        match: str,
        cohort_ids: Sequence[UUID],
        direction_ids: Sequence[UUID],
    ) -> list[User]:
        filters = [
            User.role == "student",
            User.status == "active",
        ]
        if not all_students:
            cohort_match = User.cohort_id.in_(cohort_ids) if cohort_ids else false()
            direction_match = User.direction_id.in_(direction_ids) if direction_ids else false()
            if match == "union":
                filters.append(or_(cohort_match, direction_match))
            else:
                if cohort_ids:
                    filters.append(cohort_match)
                if direction_ids:
                    filters.append(direction_match)
        return list(
            (await self._session.scalars(select(User).where(*filters).order_by(User.id))).all()
        )

    async def active_admin_count(self) -> int:
        value = await self._session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == "admin",
                User.status == "active",
            )
        )
        return int(value or 0)

    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        role: str | None,
        cohort_id: UUID | None,
        direction_id: UUID | None,
        search: str | None,
    ) -> tuple[list[User], int]:
        filters = []
        if status is not None:
            filters.append(User.status == status)
        if role is not None:
            filters.append(User.role == role)
        if cohort_id is not None:
            filters.append(User.cohort_id == cohort_id)
        if direction_id is not None:
            filters.append(User.direction_id == direction_id)
        if search:
            query = f"%{search.strip()}%"
            filters.append(
                or_(
                    User.email_normalized.ilike(query),
                    User.full_name.ilike(query),
                    User.student_number.ilike(query),
                )
            )

        count_statement = select(func.count()).select_from(User).where(*filters)
        total = int(await self._session.scalar(count_statement) or 0)
        statement: Select[tuple[User]] = (
            select(User)
            .where(*filters)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        users = list((await self._session.scalars(statement)).all())
        return users, total

    async def get_cohort(self, cohort_id: UUID, *, for_update: bool = False) -> Cohort | None:
        statement = select(Cohort).where(Cohort.id == cohort_id)
        if for_update:
            statement = statement.with_for_update()
        result: Cohort | None = await self._session.scalar(statement)
        return result

    async def get_cohort_by_code(self, code: str) -> Cohort | None:
        result: Cohort | None = await self._session.scalar(
            select(Cohort).where(Cohort.code == code)
        )
        return result

    async def list_cohorts(self) -> list[Cohort]:
        return list(
            (
                await self._session.scalars(
                    select(Cohort).order_by(Cohort.start_year.desc(), Cohort.code)
                )
            ).all()
        )

    def add_cohort(self, cohort: Cohort) -> None:
        self._session.add(cohort)

    async def get_direction(
        self, direction_id: UUID, *, for_update: bool = False
    ) -> Direction | None:
        statement = select(Direction).where(Direction.id == direction_id)
        if for_update:
            statement = statement.with_for_update()
        result: Direction | None = await self._session.scalar(statement)
        return result

    async def get_direction_by_code(self, code: str) -> Direction | None:
        result: Direction | None = await self._session.scalar(
            select(Direction).where(Direction.code == code)
        )
        return result

    async def list_directions(self) -> list[Direction]:
        return list(
            (
                await self._session.scalars(
                    select(Direction).order_by(Direction.name, Direction.code)
                )
            ).all()
        )

    def add_direction(self, direction: Direction) -> None:
        self._session.add(direction)
