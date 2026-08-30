from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.help_requests.models import HelpRequest
from app.users.models import User


@dataclass(frozen=True, slots=True)
class AdminHelpRequestRecord:
    request: HelpRequest
    submitter: User


class HelpRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, request: HelpRequest) -> None:
        self._session.add(request)

    async def delete(self, request: HelpRequest) -> None:
        await self._session.delete(request)

    async def get_student(self, request_id: UUID, user_id: UUID) -> HelpRequest | None:
        result: HelpRequest | None = await self._session.scalar(
            select(HelpRequest).where(
                HelpRequest.id == request_id,
                HelpRequest.created_by == user_id,
            )
        )
        return result

    async def get_public(self, request_id: UUID) -> HelpRequest | None:
        result: HelpRequest | None = await self._session.scalar(
            select(HelpRequest).where(
                HelpRequest.id == request_id,
                HelpRequest.request_type == "question",
                HelpRequest.status == "resolved",
            )
        )
        return result

    async def get_by_id(self, request_id: UUID, *, for_update: bool = False) -> HelpRequest | None:
        statement = select(HelpRequest).where(HelpRequest.id == request_id)
        if for_update:
            statement = statement.with_for_update()
        result: HelpRequest | None = await self._session.scalar(statement)
        return result

    async def get_submitter(self, user_id: UUID) -> User | None:
        result: User | None = await self._session.scalar(select(User).where(User.id == user_id))
        return result

    async def list_student(
        self,
        *,
        user_id: UUID,
        request_type: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[HelpRequest], int]:
        filters: list[ColumnElement[bool]] = [HelpRequest.created_by == user_id]
        if request_type is not None:
            filters.append(HelpRequest.request_type == request_type)
        if status is not None:
            filters.append(HelpRequest.status == status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(HelpRequest).where(*filters)
            )
            or 0
        )
        requests = list(
            (
                await self._session.scalars(
                    select(HelpRequest)
                    .where(*filters)
                    .order_by(HelpRequest.created_at.desc(), HelpRequest.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return requests, total

    async def list_public(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[HelpRequest], int]:
        filters: list[ColumnElement[bool]] = [
            HelpRequest.request_type == "question",
            HelpRequest.status == "resolved",
        ]
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(HelpRequest).where(*filters)
            )
            or 0
        )
        requests = list(
            (
                await self._session.scalars(
                    select(HelpRequest)
                    .where(*filters)
                    .order_by(HelpRequest.created_at.desc(), HelpRequest.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return requests, total

    async def get_admin(self, request_id: UUID) -> AdminHelpRequestRecord | None:
        row = (
            await self._session.execute(
                select(HelpRequest, User)
                .join(User, User.id == HelpRequest.created_by)
                .where(HelpRequest.id == request_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return AdminHelpRequestRecord(request=row[0], submitter=row[1])

    async def list_admin(
        self,
        *,
        request_type: str | None,
        status: str | None,
        query: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminHelpRequestRecord], int]:
        filters: list[ColumnElement[bool]] = []
        if request_type is not None:
            filters.append(HelpRequest.request_type == request_type)
        if status is not None:
            filters.append(HelpRequest.status == status)
        if query is not None:
            filters.append(
                or_(
                    HelpRequest.title.icontains(query, autoescape=True),
                    HelpRequest.content_markdown.icontains(query, autoescape=True),
                    User.full_name.icontains(query, autoescape=True),
                    User.student_number.icontains(query, autoescape=True),
                    User.email.icontains(query, autoescape=True),
                )
            )
        total = int(
            await self._session.scalar(
                select(func.count())
                .select_from(HelpRequest)
                .join(User, User.id == HelpRequest.created_by)
                .where(*filters)
            )
            or 0
        )
        rows = (
            await self._session.execute(
                select(HelpRequest, User)
                .join(User, User.id == HelpRequest.created_by)
                .where(*filters)
                .order_by(HelpRequest.created_at.desc(), HelpRequest.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return [AdminHelpRequestRecord(request=row[0], submitter=row[1]) for row in rows], total
