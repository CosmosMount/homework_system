from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Subquery

from app.teams.models import Team, TeamInvitation, TeamMember, TeamProfile, TeamSettings
from app.users.models import Direction, User


@dataclass(frozen=True, slots=True)
class TeamMemberRecord:
    member: TeamMember
    user: User
    profile: TeamProfile | None
    direction_name: str | None


@dataclass(frozen=True, slots=True)
class TeamListRecord:
    team: Team
    member_count: int


@dataclass(frozen=True, slots=True)
class TeamProfileRecord:
    profile: TeamProfile
    user: User
    direction_name: str | None
    team_id: UUID | None


@dataclass(frozen=True, slots=True)
class TeamInvitationRecord:
    invitation: TeamInvitation
    team: Team
    invited_by: User


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_team(self, team: Team) -> None:
        self._session.add(team)

    def add_member(self, member: TeamMember) -> None:
        self._session.add(member)

    def add_profile(self, profile: TeamProfile) -> None:
        self._session.add(profile)

    def add_invitation(self, invitation: TeamInvitation) -> None:
        self._session.add(invitation)

    async def team_settings(self, *, for_update: bool = False) -> TeamSettings | None:
        statement = select(TeamSettings).where(TeamSettings.id.is_(True))
        if for_update:
            statement = statement.with_for_update()
        result: TeamSettings | None = await self._session.scalar(statement)
        return result

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
                select(TeamMember, User, TeamProfile, Direction.name)
                .join(User, User.id == TeamMember.user_id)
                .outerjoin(TeamProfile, TeamProfile.user_id == User.id)
                .outerjoin(Direction, Direction.id == User.direction_id)
                .where(TeamMember.team_id == team_id, TeamMember.left_at.is_(None))
                .order_by(TeamMember.joined_at, TeamMember.id)
            )
        ).all()
        return [
            TeamMemberRecord(member=row[0], user=row[1], profile=row[2], direction_name=row[3])
            for row in rows
        ]

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

    async def profile_for_user(
        self, user_id: UUID, *, for_update: bool = False
    ) -> TeamProfile | None:
        statement = select(TeamProfile).where(TeamProfile.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        result: TeamProfile | None = await self._session.scalar(statement)
        return result

    @staticmethod
    def _current_memberships() -> Subquery:
        return (
            select(TeamMember.user_id.label("user_id"), TeamMember.team_id.label("team_id"))
            .where(TeamMember.left_at.is_(None))
            .subquery()
        )

    async def list_profiles(
        self,
        *,
        query: str | None,
        direction_id: UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TeamProfileRecord], int]:
        memberships = self._current_memberships()
        filters = [User.role == "student", User.status == "active"]
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            filters.append(
                or_(
                    User.full_name.ilike(pattern),
                    TeamProfile.introduction.ilike(pattern),
                    Direction.name.ilike(pattern),
                )
            )
        if direction_id is not None:
            filters.append(User.direction_id == direction_id)
        base = (
            select(TeamProfile)
            .join(User, User.id == TeamProfile.user_id)
            .outerjoin(Direction, Direction.id == User.direction_id)
            .where(*filters)
        )
        total = int(
            await self._session.scalar(select(func.count()).select_from(base.subquery())) or 0
        )
        rows = (
            await self._session.execute(
                select(TeamProfile, User, Direction.name, memberships.c.team_id)
                .join(User, User.id == TeamProfile.user_id)
                .outerjoin(Direction, Direction.id == User.direction_id)
                .outerjoin(memberships, memberships.c.user_id == User.id)
                .where(*filters)
                .order_by(TeamProfile.updated_at.desc(), TeamProfile.user_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return [
            TeamProfileRecord(profile=row[0], user=row[1], direction_name=row[2], team_id=row[3])
            for row in rows
        ], total

    async def list_active_directions(self) -> list[Direction]:
        return list(
            (
                await self._session.scalars(
                    select(Direction)
                    .where(Direction.is_active.is_(True))
                    .order_by(Direction.name, Direction.code)
                )
            ).all()
        )

    async def pending_invitee_ids(self, team_id: UUID) -> set[UUID]:
        return set(
            (
                await self._session.scalars(
                    select(TeamInvitation.invitee_user_id).where(
                        TeamInvitation.team_id == team_id,
                        TeamInvitation.status == "pending",
                    )
                )
            ).all()
        )

    async def pending_invitation(
        self, team_id: UUID, invitee_user_id: UUID
    ) -> TeamInvitation | None:
        result: TeamInvitation | None = await self._session.scalar(
            select(TeamInvitation).where(
                TeamInvitation.team_id == team_id,
                TeamInvitation.invitee_user_id == invitee_user_id,
                TeamInvitation.status == "pending",
            )
        )
        return result

    async def received_pending_invitations(
        self, invitee_user_id: UUID
    ) -> list[TeamInvitationRecord]:
        rows = (
            await self._session.execute(
                select(TeamInvitation, Team, User)
                .join(Team, Team.id == TeamInvitation.team_id)
                .join(User, User.id == TeamInvitation.invited_by_user_id)
                .where(
                    TeamInvitation.invitee_user_id == invitee_user_id,
                    TeamInvitation.status == "pending",
                    Team.status == "forming",
                )
                .order_by(TeamInvitation.created_at.desc(), TeamInvitation.id.desc())
            )
        ).all()
        return [
            TeamInvitationRecord(invitation=row[0], team=row[1], invited_by=row[2]) for row in rows
        ]

    async def invitation_for_invitee(
        self, invitation_id: UUID, invitee_user_id: UUID, *, for_update: bool = False
    ) -> TeamInvitation | None:
        statement = select(TeamInvitation).where(
            TeamInvitation.id == invitation_id,
            TeamInvitation.invitee_user_id == invitee_user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: TeamInvitation | None = await self._session.scalar(statement)
        return result

    async def cancel_pending_for_invitee(
        self, invitee_user_id: UUID, *, responded_at: datetime, exclude_id: UUID | None = None
    ) -> None:
        filters = [
            TeamInvitation.invitee_user_id == invitee_user_id,
            TeamInvitation.status == "pending",
        ]
        if exclude_id is not None:
            filters.append(TeamInvitation.id != exclude_id)
        await self._session.execute(
            update(TeamInvitation)
            .where(*filters)
            .values(
                status="cancelled",
                responded_at=responded_at,
                updated_at=responded_at,
                revision=TeamInvitation.revision + 1,
            )
        )

    async def cancel_pending_for_team(self, team_id: UUID, *, responded_at: datetime) -> None:
        await self._session.execute(
            update(TeamInvitation)
            .where(TeamInvitation.team_id == team_id, TeamInvitation.status == "pending")
            .values(
                status="cancelled",
                responded_at=responded_at,
                updated_at=responded_at,
                revision=TeamInvitation.revision + 1,
            )
        )
