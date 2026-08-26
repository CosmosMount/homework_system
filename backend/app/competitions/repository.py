from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.competitions.models import (
    Competition,
    CompetitionRegistration,
    CompetitionTask,
    Team,
    TeamMember,
)
from app.submissions.models import Submission
from app.users.models import User

_PNX_ADVISORY_LOCK_NAMESPACE = 5_267_800
_CAMPUS_COMPETITION_RESOURCE = 2


@dataclass(frozen=True, slots=True)
class TeamMemberRecord:
    member: TeamMember
    user: User


@dataclass(frozen=True, slots=True)
class TeamListRecord:
    team: Team
    member_count: int
    submission_count: int


@dataclass(frozen=True, slots=True)
class RegistrationListRecord:
    registration: CompetitionRegistration
    user: User
    team_id: UUID | None
    team_name: str | None


@dataclass(frozen=True, slots=True)
class CompetitionUserRecord:
    registration: CompetitionRegistration | None
    team: Team | None


class CompetitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_competition(self, competition: Competition) -> None:
        self._session.add(competition)

    def add_registration(self, registration: CompetitionRegistration) -> None:
        self._session.add(registration)

    def add_task(self, task: CompetitionTask) -> None:
        self._session.add(task)

    def add_team(self, team: Team) -> None:
        self._session.add(team)

    def add_member(self, member: TeamMember) -> None:
        self._session.add(member)

    async def get_competition(
        self, competition_id: UUID, *, for_update: bool = False
    ) -> Competition | None:
        statement = select(Competition).where(Competition.id == competition_id)
        if for_update:
            statement = statement.with_for_update()
        result: Competition | None = await self._session.scalar(statement)
        return result

    async def acquire_campus_competition_lock(self) -> None:
        """Serialize creation of the single current campus competition."""
        await self._session.execute(
            select(
                func.pg_advisory_xact_lock(
                    _PNX_ADVISORY_LOCK_NAMESPACE,
                    _CAMPUS_COMPETITION_RESOURCE,
                )
            )
        )

    async def current_competition(self, *, for_update: bool = False) -> Competition | None:
        """Return the single non-archived campus competition, if configured.

        Archived competitions remain available as historical records. The
        product exposes only one current campus competition, so creation uses
        this lookup before inserting another row.
        """
        statement = (
            select(Competition)
            .where(Competition.status != "archived")
            .order_by(Competition.created_at.desc(), Competition.id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        result: Competition | None = await self._session.scalar(statement)
        return result

    async def list_competitions(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        query: str | None,
        public_only: bool,
    ) -> tuple[list[Competition], int]:
        filters = []
        if public_only:
            filters.extend([Competition.published_at.is_not(None), Competition.status != "draft"])
        if status is not None:
            filters.append(Competition.status == status)
        if query:
            filters.append(Competition.name.ilike(f"%{query.strip()}%"))
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(Competition).where(*filters)
            )
            or 0
        )
        statement: Select[tuple[Competition]] = (
            select(Competition)
            .where(*filters)
            .order_by(Competition.registration_start.desc(), Competition.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.scalars(statement)).all()), total

    async def user_records(
        self,
        *,
        competition_ids: list[UUID],
        user_id: UUID,
    ) -> dict[UUID, CompetitionUserRecord]:
        if not competition_ids:
            return {}
        registrations = (
            await self._session.scalars(
                select(CompetitionRegistration).where(
                    CompetitionRegistration.competition_id.in_(competition_ids),
                    CompetitionRegistration.user_id == user_id,
                )
            )
        ).all()
        teams = (
            await self._session.scalars(
                select(Team)
                .join(TeamMember, TeamMember.team_id == Team.id)
                .where(
                    Team.competition_id.in_(competition_ids),
                    TeamMember.user_id == user_id,
                    TeamMember.left_at.is_(None),
                )
            )
        ).all()
        registrations_by_id = {
            registration.competition_id: registration for registration in registrations
        }
        teams_by_id = {team.competition_id: team for team in teams}
        return {
            competition_id: CompetitionUserRecord(
                registration=registrations_by_id.get(competition_id),
                team=teams_by_id.get(competition_id),
            )
            for competition_id in competition_ids
        }

    async def dashboard_competitions(self, *, limit: int = 5) -> list[Competition]:
        return list(
            (
                await self._session.scalars(
                    select(Competition)
                    .where(
                        Competition.published_at.is_not(None),
                        Competition.status.not_in(("draft", "submission_closed", "archived")),
                    )
                    .order_by(Competition.submission_end, Competition.id)
                    .limit(limit)
                )
            ).all()
        )

    async def lifecycle_candidate_ids(self, now: datetime) -> list[UUID]:
        statement = (
            select(Competition.id)
            .where(
                Competition.published_at.is_not(None),
                Competition.status.not_in(("submission_closed", "archived")),
                or_(
                    Competition.registration_end <= now,
                    Competition.submission_start <= now,
                    Competition.submission_end <= now,
                ),
            )
            .order_by(Competition.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_registration(
        self,
        competition_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> CompetitionRegistration | None:
        statement = select(CompetitionRegistration).where(
            CompetitionRegistration.competition_id == competition_id,
            CompetitionRegistration.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: CompetitionRegistration | None = await self._session.scalar(statement)
        return result

    async def registration_count(
        self, competition_id: UUID, *, status: str | None = "registered"
    ) -> int:
        filters = [CompetitionRegistration.competition_id == competition_id]
        if status is not None:
            filters.append(CompetitionRegistration.status == status)
        return int(
            await self._session.scalar(
                select(func.count()).select_from(CompetitionRegistration).where(*filters)
            )
            or 0
        )

    async def registrations(self, competition_id: UUID) -> list[RegistrationListRecord]:
        rows = (
            await self._session.execute(
                select(CompetitionRegistration, User, Team.id, Team.name)
                .join(User, User.id == CompetitionRegistration.user_id)
                .outerjoin(
                    TeamMember,
                    and_(
                        TeamMember.competition_id == CompetitionRegistration.competition_id,
                        TeamMember.user_id == CompetitionRegistration.user_id,
                        TeamMember.left_at.is_(None),
                    ),
                )
                .outerjoin(Team, Team.id == TeamMember.team_id)
                .where(CompetitionRegistration.competition_id == competition_id)
                .order_by(User.student_number, User.id)
            )
        ).all()
        return [
            RegistrationListRecord(
                registration=row[0],
                user=row[1],
                team_id=row[2],
                team_name=row[3],
            )
            for row in rows
        ]

    async def tasks(self, competition_id: UUID) -> list[CompetitionTask]:
        return list(
            (
                await self._session.scalars(
                    select(CompetitionTask)
                    .where(CompetitionTask.competition_id == competition_id)
                    .order_by(CompetitionTask.display_order, CompetitionTask.id)
                )
            ).all()
        )

    async def get_task(
        self,
        task_id: UUID,
        *,
        competition_id: UUID | None = None,
        for_update: bool = False,
    ) -> CompetitionTask | None:
        filters = [CompetitionTask.id == task_id]
        if competition_id is not None:
            filters.append(CompetitionTask.competition_id == competition_id)
        statement = select(CompetitionTask).where(*filters)
        if for_update:
            statement = statement.with_for_update()
        result: CompetitionTask | None = await self._session.scalar(statement)
        return result

    async def get_team(self, team_id: UUID, *, for_update: bool = False) -> Team | None:
        statement = select(Team).where(Team.id == team_id)
        if for_update:
            statement = statement.with_for_update()
        result: Team | None = await self._session.scalar(statement)
        return result

    async def team_for_user(
        self,
        competition_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> Team | None:
        statement = (
            select(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                Team.competition_id == competition_id,
                TeamMember.competition_id == competition_id,
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
                .where(
                    TeamMember.team_id == team_id,
                    TeamMember.left_at.is_(None),
                )
                .order_by(TeamMember.joined_at, TeamMember.id)
            )
        ).all()
        return [TeamMemberRecord(member=row[0], user=row[1]) for row in rows]

    async def current_member_ids(self, team_id: UUID) -> list[UUID]:
        return list(
            (
                await self._session.scalars(
                    select(TeamMember.user_id)
                    .where(
                        TeamMember.team_id == team_id,
                        TeamMember.left_at.is_(None),
                    )
                    .order_by(TeamMember.joined_at, TeamMember.id)
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
        competition_id: UUID,
        invite_code_hash: str,
        *,
        for_update: bool = False,
    ) -> Team | None:
        statement = select(Team).where(
            Team.competition_id == competition_id,
            Team.invite_code_hash == invite_code_hash,
            Team.status == "forming",
        )
        if for_update:
            statement = statement.with_for_update()
        result: Team | None = await self._session.scalar(statement)
        return result

    async def forming_teams_for_update(self, competition_id: UUID) -> list[Team]:
        return list(
            (
                await self._session.scalars(
                    select(Team)
                    .where(
                        Team.competition_id == competition_id,
                        Team.status == "forming",
                    )
                    .order_by(Team.id)
                    .with_for_update()
                )
            ).all()
        )

    async def list_teams(self, competition_id: UUID) -> list[TeamListRecord]:
        member_counts = (
            select(TeamMember.team_id.label("team_id"), func.count().label("member_count"))
            .where(TeamMember.left_at.is_(None))
            .group_by(TeamMember.team_id)
            .subquery()
        )
        submission_counts = (
            select(
                Submission.owner_team_id.label("team_id"),
                func.count().label("submission_count"),
            )
            .join(CompetitionTask, CompetitionTask.id == Submission.competition_task_id)
            .where(CompetitionTask.competition_id == competition_id)
            .group_by(Submission.owner_team_id)
            .subquery()
        )
        rows = (
            await self._session.execute(
                select(
                    Team,
                    func.coalesce(member_counts.c.member_count, 0),
                    func.coalesce(submission_counts.c.submission_count, 0),
                )
                .outerjoin(member_counts, member_counts.c.team_id == Team.id)
                .outerjoin(submission_counts, submission_counts.c.team_id == Team.id)
                .where(Team.competition_id == competition_id)
                .order_by(Team.created_at, Team.id)
            )
        ).all()
        return [
            TeamListRecord(
                team=row[0],
                member_count=int(row[1]),
                submission_count=int(row[2]),
            )
            for row in rows
        ]

    async def task_submission(self, task_id: UUID, team_id: UUID) -> Submission | None:
        result: Submission | None = await self._session.scalar(
            select(Submission).where(
                Submission.competition_task_id == task_id,
                Submission.owner_team_id == team_id,
            )
        )
        return result
