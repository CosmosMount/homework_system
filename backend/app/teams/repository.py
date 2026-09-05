from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Subquery

from app.teams.models import Team, TeamMember
from app.users.models import User


@dataclass(frozen=True, slots=True)
class TeamMemberRecord:
    member: TeamMember
    user: User


@dataclass(frozen=True, slots=True)
class TeamListRecord:
    team: Team
    member_count: int


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_team(self, team: Team) -> None:
        self._session.add(team)

    def add_member(self, member: TeamMember) -> None:
        self._session.add(member)

    async def delete_team(self, team: Team) -> None:
        await self._session.delete(team)

    async def get_team(self, team_id: UUID, *, for_update: bool = False) -> Team | None:
        statement = select(Team).where(Team.id == team_id)
        if for_update:
            statement = statement.with_for_update()
        result: Team | None = await self._session.scalar(statement)
        return result

    async def team_for_user(self, user_id: UUID, *, for_update: bool = False) -> Team | None:
        statement = (
            select(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                Team.status == "forming",
                TeamMember.user_id == user_id,
                TeamMember.left_at.is_(None),
            )
        )
        if for_update:
            statement = statement.with_for_update(of=Team)
        result: Team | None = await self._session.scalar(statement)
        return result

    async def current_member(
        self,
        team_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> TeamMember | None:
        statement = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.left_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        result: TeamMember | None = await self._session.scalar(statement)
        return result

    async def current_members(self, team_id: UUID) -> list[TeamMemberRecord]:
        rows = (
            await self._session.execute(
                select(TeamMember, User)
                .join(User, User.id == TeamMember.user_id)
                .where(TeamMember.team_id == team_id, TeamMember.left_at.is_(None))
                .order_by(TeamMember.joined_at, TeamMember.id)
            )
        ).all()
        return [TeamMemberRecord(member=row[0], user=row[1]) for row in rows]

    async def current_members_for_update(self, team_id: UUID) -> list[TeamMember]:
        return list(
            (
                await self._session.scalars(
                    select(TeamMember)
                    .where(TeamMember.team_id == team_id, TeamMember.left_at.is_(None))
                    .order_by(TeamMember.joined_at, TeamMember.id)
                    .with_for_update()
                )
            ).all()
        )

    async def member_count(self, team_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(TeamMember)
                .where(TeamMember.team_id == team_id, TeamMember.left_at.is_(None))
            )
            or 0
        )

    async def team_by_invite_hash(
        self,
        invite_code_hash: str,
        *,
        for_update: bool = False,
    ) -> Team | None:
        statement = select(Team).where(
            Team.invite_code_hash == invite_code_hash,
            Team.status == "forming",
        )
        if for_update:
            statement = statement.with_for_update()
        result: Team | None = await self._session.scalar(statement)
        return result

    async def forming_teams_for_update(self) -> list[Team]:
        return list(
            (
                await self._session.scalars(
                    select(Team)
                    .where(Team.status == "forming")
                    .order_by(Team.created_at, Team.id)
                    .with_for_update()
                )
            ).all()
        )

    @staticmethod
    def _member_counts() -> Subquery:
        return (
            select(TeamMember.team_id.label("team_id"), func.count().label("member_count"))
            .where(TeamMember.left_at.is_(None))
            .group_by(TeamMember.team_id)
            .subquery()
        )

    async def list_public_teams(
        self,
        *,
        query: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TeamListRecord], int]:
        member_counts = self._member_counts()
        filters = [Team.status == "forming"]
        if query and query.strip():
            filters.append(Team.name.ilike(f"%{query.strip()}%"))
        total = int(
            await self._session.scalar(select(func.count()).select_from(Team).where(*filters)) or 0
        )
        rows = (
            await self._session.execute(
                select(Team, func.coalesce(member_counts.c.member_count, 0))
                .outerjoin(member_counts, member_counts.c.team_id == Team.id)
                .where(*filters)
                .order_by(func.lower(Team.name), Team.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return [TeamListRecord(team=row[0], member_count=int(row[1])) for row in rows], total

    async def list_admin_teams(
        self,
        *,
        query: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TeamListRecord], int]:
        member_counts = self._member_counts()
        filters = [Team.status == "forming"]
        if query and query.strip():
            filters.append(Team.name.ilike(f"%{query.strip()}%"))
        total = int(
            await self._session.scalar(select(func.count()).select_from(Team).where(*filters)) or 0
        )
        statement: Select[tuple[Team, int]] = (
            select(Team, func.coalesce(member_counts.c.member_count, 0))
            .outerjoin(member_counts, member_counts.c.team_id == Team.id)
            .where(*filters)
            .order_by(Team.created_at.desc(), Team.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(statement)).all()
        return [TeamListRecord(team=row[0], member_count=int(row[1])) for row in rows], total
