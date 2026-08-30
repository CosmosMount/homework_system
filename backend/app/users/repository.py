from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, delete, exists, false, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.announcements.models import AnnouncementFile
from app.assignments.models import AssignmentExtension
from app.auth.models import AuthSecurityEvent, OneTimeToken
from app.competitions.models import Competition, CompetitionRegistration, Team, TeamMember
from app.help_requests.models import HelpRequest
from app.intentions.models import IntentionResponse
from app.notifications.models import OutboxJob, StudentNotification
from app.notifications.repository import MAIL_JOB_TYPES
from app.submissions.models import Submission, SubmissionVersion, VersionFile
from app.uploads.models import StoredFile, UploadSession
from app.users.models import Cohort, Direction, User

AccountSearchTerms = Sequence[tuple[str, Sequence[str]]]

_ACCOUNT_ROLE_SEARCH_TERMS: AccountSearchTerms = (
    ("student", ("student", "学生")),
    ("admin", ("admin", "管理员")),
)
_ACCOUNT_STATUS_SEARCH_TERMS: AccountSearchTerms = (
    ("active", ("active", "正常")),
    ("pending_email", ("pending_email", "待验证")),
    ("disabled", ("disabled", "已禁用")),
)


def _matching_account_values(search: str, terms: AccountSearchTerms) -> tuple[str, ...]:
    normalized = search.casefold()
    return tuple(
        value for value, labels in terms if any(normalized in label.casefold() for label in labels)
    )


def _escape_like_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True, slots=True)
class AccountObjectCleanup:
    file_id: UUID
    object_key: str
    minio_upload_id: str | None


@dataclass(frozen=True, slots=True)
class AccountErasurePreparation:
    object_cleanups: tuple[AccountObjectCleanup, ...]
    deletion_counts: dict[str, int]
    teams_transferred: int
    teams_dissolved: int
    teams_invalidated: int


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

    async def touch_activity(self, user: User, *, at: datetime) -> datetime:
        latest = await self._session.scalar(
            update(User)
            .where(User.id == user.id)
            .values(
                last_active_at=func.greatest(
                    func.coalesce(User.last_active_at, at),
                    at,
                )
            )
            .returning(User.last_active_at)
            .execution_options(synchronize_session=False)
        )
        if latest is None:
            raise RuntimeError("user disappeared while updating account activity")
        set_committed_value(user, "last_active_at", latest)
        return latest

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
        activity: str | None,
        inactive_before: datetime | None,
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
        normalized_search = search.strip() if search is not None else ""
        if normalized_search:
            query = f"%{_escape_like_literal(normalized_search)}%"
            search_filters = [
                User.email_normalized.ilike(query, escape="\\"),
                User.full_name.ilike(query, escape="\\"),
                User.student_number.ilike(query, escape="\\"),
            ]
            matching_roles = _matching_account_values(
                normalized_search,
                _ACCOUNT_ROLE_SEARCH_TERMS,
            )
            matching_statuses = _matching_account_values(
                normalized_search,
                _ACCOUNT_STATUS_SEARCH_TERMS,
            )
            if matching_roles:
                search_filters.append(User.role.in_(matching_roles))
            if matching_statuses:
                search_filters.append(User.status.in_(matching_statuses))
            filters.append(or_(*search_filters))
        if activity == "inactive":
            if inactive_before is None:
                raise ValueError("inactive_before is required for inactive filtering")
            activity_reference = func.coalesce(
                User.last_active_at,
                User.email_verified_at,
                User.created_at,
            )
            filters.extend(
                (
                    User.status == "active",
                    activity_reference < inactive_before,
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

    async def _account_deletion_counts(
        self,
        user_id: UUID,
        *,
        personal_file_count: int,
        shared_file_count: int,
    ) -> dict[str, int]:
        async def count(model: type[Any], *conditions: Any) -> int:
            value = await self._session.scalar(
                select(func.count()).select_from(model).where(*conditions)
            )
            return int(value or 0)

        return {
            "assignment_extensions": await count(
                AssignmentExtension,
                AssignmentExtension.user_id == user_id,
            ),
            "submissions": await count(Submission, Submission.owner_user_id == user_id),
            "competition_registrations": await count(
                CompetitionRegistration,
                CompetitionRegistration.user_id == user_id,
            ),
            "team_memberships": await count(TeamMember, TeamMember.user_id == user_id),
            "intention_responses": await count(
                IntentionResponse,
                IntentionResponse.user_id == user_id,
            ),
            "help_requests": await count(HelpRequest, HelpRequest.created_by == user_id),
            "upload_sessions": await count(UploadSession, UploadSession.user_id == user_id),
            "student_notifications": await count(
                StudentNotification,
                StudentNotification.user_id == user_id,
            ),
            "personal_files": personal_file_count,
            "shared_files_retained": shared_file_count,
        }

    async def _prepare_account_teams(
        self,
        user_id: UUID,
        *,
        now: datetime,
    ) -> tuple[int, int, int]:
        current_team_rows = (
            await self._session.execute(
                select(Team, Competition.min_team_size)
                .join(Competition, Competition.id == Team.competition_id)
                .join(
                    TeamMember,
                    and_(
                        TeamMember.team_id == Team.id,
                        TeamMember.user_id == user_id,
                        TeamMember.left_at.is_(None),
                    ),
                )
                .order_by(Team.id)
                .with_for_update(of=Team)
            )
        ).all()
        captain_team_rows = (
            await self._session.execute(
                select(Team, Competition.min_team_size)
                .join(Competition, Competition.id == Team.competition_id)
                .where(Team.captain_user_id == user_id)
                .order_by(Team.id)
                .with_for_update(of=Team)
            )
        ).all()

        impacted: dict[UUID, tuple[Team, int]] = {}
        for row in (*current_team_rows, *captain_team_rows):
            impacted[row[0].id] = (row[0], int(row[1]))
        if not impacted:
            return 0, 0, 0

        members = list(
            (
                await self._session.scalars(
                    select(TeamMember)
                    .where(
                        TeamMember.team_id.in_(tuple(impacted)),
                        TeamMember.left_at.is_(None),
                    )
                    .order_by(TeamMember.team_id, TeamMember.joined_at, TeamMember.id)
                    .with_for_update()
                )
            ).all()
        )
        members_by_team: dict[UUID, list[TeamMember]] = {}
        for member in members:
            members_by_team.setdefault(member.team_id, []).append(member)

        transferred = 0
        dissolved = 0
        invalidated = 0
        for team, min_team_size in impacted.values():
            remaining = [
                member for member in members_by_team.get(team.id, []) if member.user_id != user_id
            ]
            changed = False
            if team.captain_user_id == user_id:
                if remaining:
                    team.captain_user_id = remaining[0].user_id
                    transferred += 1
                else:
                    team.captain_user_id = None
                    team.status = "dissolved"
                    team.dissolved_at = now
                    team.disqualified_at = None
                    team.disqualified_by = None
                    team.disqualification_reason = None
                    dissolved += 1
                changed = True
            if (
                team.status == "locked"
                and len(remaining) < min_team_size
                and team.min_size_waived_at is None
            ):
                team.status = "invalid"
                invalidated += 1
                changed = True
            if changed:
                team.revision += 1
        return transferred, dissolved, invalidated

    async def prepare_account_erasure(
        self,
        user: User,
        *,
        now: datetime,
    ) -> AccountErasurePreparation:
        transferred, dissolved, invalidated = await self._prepare_account_teams(
            user.id,
            now=now,
        )

        await self._session.execute(
            update(Submission)
            .where(Submission.owner_user_id == user.id)
            .values(latest_version_id=None)
        )

        owned_files = list(
            (
                await self._session.scalars(
                    select(StoredFile)
                    .where(StoredFile.owner_user_id == user.id)
                    .order_by(StoredFile.id)
                    .with_for_update()
                )
            ).all()
        )
        owned_file_ids = tuple(item.id for item in owned_files)
        shared_file_ids: set[UUID] = set()
        if owned_file_ids:
            shared_file_ids.update(
                (
                    await self._session.scalars(
                        select(AnnouncementFile.file_id).where(
                            AnnouncementFile.file_id.in_(owned_file_ids)
                        )
                    )
                ).all()
            )
            shared_file_ids.update(
                (
                    await self._session.scalars(
                        select(VersionFile.file_id)
                        .join(
                            SubmissionVersion,
                            SubmissionVersion.id == VersionFile.version_id,
                        )
                        .join(
                            Submission,
                            Submission.id == SubmissionVersion.submission_id,
                        )
                        .where(
                            VersionFile.file_id.in_(owned_file_ids),
                            Submission.owner_team_id.is_not(None),
                        )
                    )
                ).all()
            )
        personal_files = [item for item in owned_files if item.id not in shared_file_ids]

        upload_sessions = list(
            (
                await self._session.scalars(
                    select(UploadSession)
                    .where(UploadSession.user_id == user.id)
                    .order_by(UploadSession.id)
                    .with_for_update()
                )
            ).all()
        )
        upload_by_file = {item.file_id: item for item in upload_sessions}
        object_cleanups = tuple(
            AccountObjectCleanup(
                file_id=item.id,
                object_key=item.object_key,
                minio_upload_id=(
                    upload_by_file[item.id].minio_upload_id if item.id in upload_by_file else None
                ),
            )
            for item in personal_files
        )

        await self._session.execute(
            update(AuthSecurityEvent)
            .where(
                or_(
                    AuthSecurityEvent.user_id == user.id,
                    AuthSecurityEvent.email_normalized == user.email_normalized,
                )
            )
            .values(user_id=None, email_normalized=None)
        )
        token_ids = tuple(
            (
                await self._session.scalars(
                    select(OneTimeToken.id)
                    .where(OneTimeToken.user_id == user.id)
                    .order_by(OneTimeToken.id)
                    .with_for_update()
                )
            ).all()
        )
        token_event_keys = tuple(
            f"{job_type}:{token_id}"
            for token_id in token_ids
            for job_type in ("email_verification", "password_reset")
        )
        mail_identity_predicates: list[Any] = [
            OutboxJob.payload["recipient"].as_string().in_((user.email, user.email_normalized)),
            OutboxJob.event_key.endswith(f":{user.id}"),
            OutboxJob.event_key.contains(f":{user.id}:"),
        ]
        if token_event_keys:
            mail_identity_predicates.append(OutboxJob.event_key.in_(token_event_keys))
        mail_jobs = list(
            (
                await self._session.scalars(
                    select(OutboxJob)
                    .where(
                        OutboxJob.job_type.in_(MAIL_JOB_TYPES),
                        or_(*mail_identity_predicates),
                    )
                    .with_for_update()
                )
            ).all()
        )
        for job in mail_jobs:
            redacted_payload = dict(job.payload)
            redacted_payload["recipient"] = None
            redacted_payload.pop("full_name", None)
            job.payload = redacted_payload
            job.secret_payload_ciphertext = None
            if job.status in {"pending", "processing", "retry"}:
                job.status = "dead"
                job.locked_by = None
                job.locked_at = None
                job.last_error_code = "USER_DELETED"
                job.last_error_summary = "账号已删除，邮件任务已取消。"

        deletion_counts = await self._account_deletion_counts(
            user.id,
            personal_file_count=len(personal_files),
            shared_file_count=len(shared_file_ids),
        )
        await self._session.flush()
        return AccountErasurePreparation(
            object_cleanups=object_cleanups,
            deletion_counts=deletion_counts,
            teams_transferred=transferred,
            teams_dissolved=dissolved,
            teams_invalidated=invalidated,
        )

    async def erase_account(
        self,
        user: User,
        preparation: AccountErasurePreparation,
    ) -> None:
        await self._session.execute(text("SET LOCAL pnx.account_erasure = 'on'"))
        await self._session.delete(user)
        await self._session.flush()
        personal_file_ids = tuple(item.file_id for item in preparation.object_cleanups)
        if personal_file_ids:
            await self._session.execute(
                delete(StoredFile).where(StoredFile.id.in_(personal_file_ids))
            )
            await self._session.flush()

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
