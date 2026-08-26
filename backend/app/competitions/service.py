import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.models import AuthSecurityEvent
from app.auth.repository import AuthRepository
from app.auth.service import AuthenticatedContext, context_effective_role, context_is_admin
from app.competitions.models import (
    Competition,
    CompetitionRegistration,
    CompetitionTask,
    Team,
    TeamMember,
)
from app.competitions.policy import (
    registration_is_open,
    team_can_change,
    team_is_valid_for_lock,
    timed_competition_status,
)
from app.competitions.repository import (
    CompetitionRepository,
    CompetitionUserRecord,
    RegistrationListRecord,
)
from app.competitions.schemas import (
    AdminCaptainTransferRequest,
    AdminCompetitionDetailResponse,
    AdminMemberAddRequest,
    AdminReasonRequest,
    AdminRegistrationItem,
    AdminRegistrationListResponse,
    AdminTeamDetailResponse,
    AdminTeamListItem,
    AdminTeamListResponse,
    AdminTeamSubmissionItem,
    CaptainTransferRequest,
    CompetitionCreateRequest,
    CompetitionDetailResponse,
    CompetitionListResponse,
    CompetitionPatchRequest,
    CompetitionStatus,
    CompetitionSummaryResponse,
    CompetitionTaskCreateRequest,
    CompetitionTaskPatchRequest,
    CompetitionTaskResponse,
    InviteCodeRotatedResponse,
    OperationResponse,
    RegistrationResponse,
    RegistrationStatus,
    TeamCreatedResponse,
    TeamMemberResponse,
    TeamResponse,
    TeamStatus,
)
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.core.markdown import render_markdown
from app.users.repository import UserRepository


@dataclass(frozen=True, slots=True)
class CompetitionAuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


class CompetitionService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._competitions = CompetitionRepository(session)
        self._users = UserRepository(session)
        self._auth = AuthRepository(session)
        self._audit = AuditRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _not_found() -> ApplicationError:
        return ApplicationError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="资源不存在或当前用户无权查看。",
        )

    @staticmethod
    def _conflict(code: str, message: str) -> ApplicationError:
        return ApplicationError(status_code=409, code=code, message=message)

    @staticmethod
    def _require_student(context: AuthenticatedContext) -> None:
        if context_effective_role(context) != "student":
            raise ApplicationError(
                status_code=403,
                code="FORBIDDEN",
                message="管理员不能通过学生接口执行赛事操作。",
            )

    @staticmethod
    def _require_admin(context: AuthenticatedContext) -> None:
        if not context_is_admin(context):
            raise ApplicationError(
                status_code=403,
                code="FORBIDDEN",
                message="仅管理员可以执行此操作。",
            )

    def _invite_hash(self, invite_code: str) -> str:
        normalized = invite_code.strip().upper().encode()
        return hmac.new(
            self._settings.team_invite_code_pepper.get_secret_value().encode(),
            normalized,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _new_invite_code() -> str:
        return secrets.token_hex(6).upper()

    def _add_audit(
        self,
        audit_context: CompetitionAuditContext,
        *,
        action: str,
        target_type: str,
        target_id: UUID,
        change_summary: dict[str, object],
        now: datetime,
    ) -> None:
        self._audit.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=audit_context.actor.user.id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                request_id=audit_context.request_id,
                ip_prefix=audit_context.ip_prefix,
                result="success",
                change_summary=change_summary,
                created_at=now,
            )
        )

    @staticmethod
    def _registration_response(
        registration: CompetitionRegistration,
    ) -> RegistrationResponse:
        return RegistrationResponse(
            competition_id=registration.competition_id,
            user_id=registration.user_id,
            status=cast(RegistrationStatus, registration.status),
            registered_at=registration.registered_at,
            withdrawn_at=registration.withdrawn_at,
            disqualified_at=registration.disqualified_at,
            disqualification_reason=registration.disqualification_reason,
            revision=registration.revision,
        )

    @staticmethod
    def _admin_registration_item(record: RegistrationListRecord) -> AdminRegistrationItem:
        return AdminRegistrationItem(
            user_id=record.user.id,
            full_name=record.user.full_name,
            student_number=record.user.student_number,
            status=cast(RegistrationStatus, record.registration.status),
            registered_at=record.registration.registered_at,
            withdrawn_at=record.registration.withdrawn_at,
            disqualified_at=record.registration.disqualified_at,
            disqualification_reason=record.registration.disqualification_reason,
            team_id=record.team_id,
            team_name=record.team_name,
        )

    async def _task_response(
        self,
        task: CompetitionTask,
        *,
        team: Team | None,
    ) -> CompetitionTaskResponse:
        submission = (
            await self._competitions.task_submission(task.id, team.id) if team is not None else None
        )
        return CompetitionTaskResponse(
            id=task.id,
            competition_id=task.competition_id,
            title=task.title,
            description_markdown=task.description_markdown,
            description_html=task.description_html,
            resource_url=task.resource_url,
            allowed_extensions=list(task.allowed_extensions),
            max_total_bytes=task.max_total_bytes,
            deadline=task.deadline,
            display_order=task.display_order,
            revision=task.revision,
            submission_id=submission.id if submission is not None else None,
            latest_version_id=(submission.latest_version_id if submission is not None else None),
        )

    def _summary(
        self,
        competition: Competition,
        *,
        user_record: CompetitionUserRecord | None,
    ) -> CompetitionSummaryResponse:
        registration = user_record.registration if user_record is not None else None
        team = user_record.team if user_record is not None else None
        return CompetitionSummaryResponse(
            id=competition.id,
            name=competition.name,
            status=cast(CompetitionStatus, competition.status),
            registration_start=competition.registration_start,
            registration_end=competition.registration_end,
            submission_start=competition.submission_start,
            submission_end=competition.submission_end,
            min_team_size=competition.min_team_size,
            max_team_size=competition.max_team_size,
            registration_status=(
                cast(RegistrationStatus, registration.status) if registration is not None else None
            ),
            registration_disqualification_reason=(
                registration.disqualification_reason if registration is not None else None
            ),
            team_id=team.id if team is not None else None,
            team_name=team.name if team is not None else None,
            team_status=cast(TeamStatus, team.status) if team is not None else None,
        )

    async def list_competitions(
        self,
        *,
        context: AuthenticatedContext,
        page: int,
        page_size: int,
        status: str | None,
        query: str | None,
        admin: bool = False,
    ) -> CompetitionListResponse:
        if admin:
            self._require_admin(context)
        competitions, total = await self._competitions.list_competitions(
            page=page,
            page_size=page_size,
            status=status,
            query=query,
            public_only=not admin,
        )
        user_records = await self._competitions.user_records(
            competition_ids=[competition.id for competition in competitions],
            user_id=context.user.id,
        )
        return CompetitionListResponse(
            items=[
                self._summary(
                    competition,
                    user_record=user_records.get(competition.id),
                )
                for competition in competitions
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def _detail_response(
        self,
        competition: Competition,
        *,
        user_id: UUID,
    ) -> CompetitionDetailResponse:
        registration = await self._competitions.get_registration(competition.id, user_id)
        team = await self._competitions.team_for_user(competition.id, user_id)
        tasks = await self._competitions.tasks(competition.id)
        return CompetitionDetailResponse(
            id=competition.id,
            name=competition.name,
            description_markdown=competition.description_markdown,
            description_html=competition.description_html,
            rules_url=competition.rules_url,
            status=cast(CompetitionStatus, competition.status),
            registration_start=competition.registration_start,
            registration_end=competition.registration_end,
            submission_start=competition.submission_start,
            submission_end=competition.submission_end,
            min_team_size=competition.min_team_size,
            max_team_size=competition.max_team_size,
            published_at=competition.published_at,
            archived_at=competition.archived_at,
            revision=competition.revision,
            registration_status=(
                cast(RegistrationStatus, registration.status) if registration is not None else None
            ),
            registration_disqualification_reason=(
                registration.disqualification_reason if registration is not None else None
            ),
            team_id=team.id if team is not None else None,
            team_name=team.name if team is not None else None,
            team_status=cast(TeamStatus, team.status) if team is not None else None,
            tasks=[await self._task_response(task, team=team) for task in tasks],
        )

    async def get_competition(
        self,
        competition_id: UUID,
        *,
        context: AuthenticatedContext,
        admin: bool = False,
    ) -> CompetitionDetailResponse:
        if admin:
            self._require_admin(context)
        competition = await self._competitions.get_competition(competition_id)
        if competition is None or (
            not admin and (competition.published_at is None or competition.status == "draft")
        ):
            raise self._not_found()
        return await self._detail_response(
            competition,
            user_id=context.user.id,
        )

    async def register(
        self,
        competition_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> RegistrationResponse:
        self._require_student(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        now = self._clock()
        if competition is None or competition.published_at is None:
            await self._session.rollback()
            raise self._not_found()
        await self._advance_locked(competition, now)
        if not registration_is_open(competition, now):
            await self._session.rollback()
            raise self._conflict(
                "COMPETITION_REGISTRATION_CLOSED",
                "当前不在赛事报名期。",
            )
        registration = await self._competitions.get_registration(
            competition_id,
            audit_context.actor.user.id,
            for_update=True,
        )
        if registration is not None and registration.status == "disqualified":
            await self._session.rollback()
            raise self._conflict(
                "COMPETITION_DISQUALIFIED",
                "当前账号已被取消本赛事参赛资格。",
            )
        if registration is None:
            registration = CompetitionRegistration(
                id=uuid7(),
                competition_id=competition_id,
                user_id=audit_context.actor.user.id,
                status="registered",
                registered_at=now,
                withdrawn_at=None,
                disqualified_at=None,
                disqualified_by=None,
                disqualification_reason=None,
                created_at=now,
                updated_at=now,
                revision=1,
            )
            self._competitions.add_registration(registration)
        elif registration.status == "withdrawn":
            registration.status = "registered"
            registration.registered_at = now
            registration.withdrawn_at = None
            registration.updated_at = now
            registration.revision += 1
        self._add_audit(
            audit_context,
            action="competition.registration_create",
            target_type="competition",
            target_id=competition_id,
            change_summary={},
            now=now,
        )
        await self._session.commit()
        return self._registration_response(registration)

    async def withdraw_registration(
        self,
        competition_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> OperationResponse:
        self._require_student(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        now = self._clock()
        if competition is None or competition.published_at is None:
            await self._session.rollback()
            raise self._not_found()
        await self._advance_locked(competition, now)
        if not registration_is_open(competition, now):
            await self._session.rollback()
            raise self._conflict(
                "COMPETITION_REGISTRATION_CLOSED",
                "当前不在赛事报名期。",
            )
        registration = await self._competitions.get_registration(
            competition_id,
            audit_context.actor.user.id,
            for_update=True,
        )
        if registration is None or registration.status != "registered":
            await self._session.rollback()
            raise self._not_found()
        if (
            await self._competitions.team_for_user(
                competition_id,
                audit_context.actor.user.id,
                for_update=True,
            )
            is not None
        ):
            await self._session.rollback()
            raise self._conflict(
                "TEAM_MEMBERSHIP_EXISTS",
                "请先退出当前队伍，再撤回赛事报名。",
            )
        registration.status = "withdrawn"
        registration.withdrawn_at = now
        registration.updated_at = now
        registration.revision += 1
        self._add_audit(
            audit_context,
            action="competition.registration_withdraw",
            target_type="competition",
            target_id=competition_id,
            change_summary={},
            now=now,
        )
        await self._session.commit()
        return OperationResponse()

    async def _team_response(
        self,
        team: Team,
        *,
        actor_user_id: UUID,
        competition: Competition | None = None,
    ) -> TeamResponse:
        resolved_competition = competition or await self._competitions.get_competition(
            team.competition_id
        )
        if resolved_competition is None:
            raise self._not_found()
        members = await self._competitions.current_members(team.id)
        now = self._clock()
        is_captain = team.captain_user_id == actor_user_id
        return TeamResponse(
            id=team.id,
            competition_id=team.competition_id,
            name=team.name,
            status=cast(TeamStatus, team.status),
            captain_user_id=team.captain_user_id,
            member_count=len(members),
            min_team_size=resolved_competition.min_team_size,
            max_team_size=resolved_competition.max_team_size,
            min_size_waived=team.min_size_waived_at is not None,
            waiver_reason=team.waiver_reason,
            disqualification_reason=team.disqualification_reason,
            locked_at=team.locked_at,
            dissolved_at=team.dissolved_at,
            revision=team.revision,
            members=[
                TeamMemberResponse(
                    user_id=record.user.id,
                    full_name=record.user.full_name,
                    student_id=record.user.student_number,
                    joined_at=record.member.joined_at,
                    added_by_admin=record.member.added_by_admin,
                    is_captain=record.user.id == team.captain_user_id,
                )
                for record in members
            ],
            can_manage=(is_captain and team_can_change(resolved_competition, team, now)),
            can_submit=(
                is_captain
                and team.status == "locked"
                and resolved_competition.status == "submission_open"
                and resolved_competition.submission_start
                <= now
                < resolved_competition.submission_end
            ),
        )

    async def my_team(
        self,
        competition_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> TeamResponse:
        self._require_student(context)
        team = await self._competitions.team_for_user(competition_id, context.user.id)
        if team is None:
            raise self._not_found()
        return await self._team_response(team, actor_user_id=context.user.id)

    async def _require_registered(
        self, competition_id: UUID, user_id: UUID
    ) -> CompetitionRegistration:
        registration = await self._competitions.get_registration(
            competition_id, user_id, for_update=True
        )
        if registration is None or registration.status != "registered":
            raise self._conflict(
                "REGISTRATION_REQUIRED",
                "请先完成本赛事报名。",
            )
        return registration

    async def create_team(
        self,
        competition_id: UUID,
        name: str,
        *,
        audit_context: CompetitionAuditContext,
    ) -> TeamCreatedResponse:
        self._require_student(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        now = self._clock()
        if competition is None or competition.published_at is None:
            await self._session.rollback()
            raise self._not_found()
        await self._advance_locked(competition, now)
        if not registration_is_open(competition, now):
            await self._session.rollback()
            raise self._conflict(
                "COMPETITION_REGISTRATION_CLOSED",
                "当前不在赛事报名期。",
            )
        await self._require_registered(competition_id, audit_context.actor.user.id)
        if (
            await self._competitions.team_for_user(
                competition_id,
                audit_context.actor.user.id,
                for_update=True,
            )
            is not None
        ):
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "当前账号已加入本赛事的其他队伍。")
        invite_code = self._new_invite_code()
        team = Team(
            id=uuid7(),
            competition_id=competition_id,
            name=name.strip(),
            status="forming",
            captain_user_id=audit_context.actor.user.id,
            invite_code_hash=self._invite_hash(invite_code),
            invite_code_rotated_at=now,
            min_size_waived_at=None,
            min_size_waived_by=None,
            waiver_reason=None,
            disqualified_at=None,
            disqualified_by=None,
            disqualification_reason=None,
            locked_at=None,
            dissolved_at=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._competitions.add_team(team)
        self._competitions.add_member(
            TeamMember(
                id=uuid7(),
                team_id=team.id,
                competition_id=competition_id,
                user_id=audit_context.actor.user.id,
                joined_at=now,
                left_at=None,
                added_by_admin=False,
                admin_reason=None,
            )
        )
        self._add_audit(
            audit_context,
            action="team.create",
            target_type="team",
            target_id=team.id,
            change_summary={"competition_id": str(competition_id), "name": team.name},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "TEAM_NAME_OR_MEMBERSHIP_CONFLICT",
                "队伍名称已存在，或当前账号已加入其他队伍。",
            ) from exc
        response = await self._team_response(
            team,
            actor_user_id=audit_context.actor.user.id,
            competition=competition,
        )
        return TeamCreatedResponse(
            **response.model_dump(),
            invite_code=invite_code,
        )

    async def _record_invite_attempt(
        self,
        *,
        user_id: UUID,
        ip_prefix: str,
        now: datetime,
    ) -> None:
        window = timedelta(minutes=15)
        user_count = await self._auth.count_security_events(
            event_type="team_invite_attempt",
            since=now - window,
            user_id=user_id,
        )
        ip_count = await self._auth.count_security_events(
            event_type="team_invite_attempt",
            since=now - window,
            ip_prefix=ip_prefix,
        )
        if user_count >= 10 or ip_count >= 60:
            raise ApplicationError(
                status_code=429,
                code="RATE_LIMITED",
                message="邀请码尝试过于频繁，请稍后重试。",
                headers={"Retry-After": str(int(window.total_seconds()))},
            )
        self._auth.add_security_event(
            AuthSecurityEvent(
                id=uuid7(),
                event_type="team_invite_attempt",
                email_normalized=None,
                user_id=user_id,
                ip_prefix=ip_prefix,
                occurred_at=now,
                event_metadata={},
            )
        )

    async def join_team(
        self,
        competition_id: UUID,
        invite_code: str,
        *,
        audit_context: CompetitionAuditContext,
    ) -> TeamResponse:
        self._require_student(audit_context.actor)
        now = self._clock()
        await self._record_invite_attempt(
            user_id=audit_context.actor.user.id,
            ip_prefix=audit_context.ip_prefix,
            now=now,
        )
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        if competition is None or competition.published_at is None:
            await self._session.commit()
            raise self._not_found()
        await self._advance_locked(competition, now)
        if not registration_is_open(competition, now):
            await self._session.commit()
            raise self._conflict(
                "COMPETITION_REGISTRATION_CLOSED",
                "当前不在赛事报名期。",
            )
        try:
            await self._require_registered(competition_id, audit_context.actor.user.id)
        except ApplicationError:
            await self._session.commit()
            raise
        if (
            await self._competitions.team_for_user(
                competition_id,
                audit_context.actor.user.id,
                for_update=True,
            )
            is not None
        ):
            await self._session.commit()
            raise self._conflict("ALREADY_IN_TEAM", "当前账号已加入本赛事的其他队伍。")
        team = await self._competitions.team_by_invite_hash(
            competition_id,
            self._invite_hash(invite_code),
            for_update=True,
        )
        if team is None:
            await self._session.commit()
            raise ApplicationError(
                status_code=400,
                code="INVITE_CODE_INVALID",
                message="邀请码无效或已轮换。",
            )
        if await self._competitions.member_count(team.id) >= competition.max_team_size:
            await self._session.commit()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        self._competitions.add_member(
            TeamMember(
                id=uuid7(),
                team_id=team.id,
                competition_id=competition_id,
                user_id=audit_context.actor.user.id,
                joined_at=now,
                left_at=None,
                added_by_admin=False,
                admin_reason=None,
            )
        )
        self._add_audit(
            audit_context,
            action="team.member_join",
            target_type="team",
            target_id=team.id,
            change_summary={"user_id": str(audit_context.actor.user.id)},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "ALREADY_IN_TEAM",
                "并发操作后当前账号已加入本赛事的一支队伍。",
            ) from exc
        return await self._team_response(
            team,
            actor_user_id=audit_context.actor.user.id,
            competition=competition,
        )

    async def rotate_invite_code(
        self,
        team_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> InviteCodeRotatedResponse:
        self._require_student(audit_context.actor)
        team, competition = await self._mutable_team_for_captain(
            team_id, audit_context.actor.user.id
        )
        now = self._clock()
        invite_code = self._new_invite_code()
        team.invite_code_hash = self._invite_hash(invite_code)
        team.invite_code_rotated_at = now
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="team.invite_rotate",
            target_type="team",
            target_id=team.id,
            change_summary={},
            now=now,
        )
        await self._session.commit()
        return InviteCodeRotatedResponse(
            team_id=team.id,
            invite_code=invite_code,
            rotated_at=team.invite_code_rotated_at,
            revision=team.revision,
        )

    async def _mutable_team_for_captain(
        self,
        team_id: UUID,
        actor_user_id: UUID,
    ) -> tuple[Team, Competition]:
        team = await self._competitions.get_team(team_id, for_update=True)
        if team is None:
            await self._session.rollback()
            raise self._not_found()
        competition = await self._competitions.get_competition(team.competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        now = self._clock()
        await self._advance_locked(competition, now)
        if team.captain_user_id != actor_user_id:
            await self._session.rollback()
            raise ApplicationError(
                status_code=403,
                code="TEAM_CAPTAIN_REQUIRED",
                message="只有当前队长可以执行此操作。",
            )
        if not team_can_change(competition, team, now):
            await self._session.rollback()
            raise self._conflict("TEAM_LOCKED", "报名结束后队伍不能再修改。")
        return team, competition

    async def remove_member(
        self,
        team_id: UUID,
        user_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> OperationResponse:
        self._require_student(audit_context.actor)
        team = await self._competitions.get_team(team_id, for_update=True)
        if team is None:
            await self._session.rollback()
            raise self._not_found()
        competition = await self._competitions.get_competition(team.competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        now = self._clock()
        await self._advance_locked(competition, now)
        actor_member = await self._competitions.current_member(
            team.id, audit_context.actor.user.id, for_update=True
        )
        target_member = await self._competitions.current_member(team.id, user_id, for_update=True)
        if actor_member is None or target_member is None:
            await self._session.rollback()
            raise self._not_found()
        if not team_can_change(competition, team, now):
            await self._session.rollback()
            raise self._conflict("TEAM_LOCKED", "报名结束后队伍不能再修改。")
        is_self = user_id == audit_context.actor.user.id
        if not is_self and team.captain_user_id != audit_context.actor.user.id:
            await self._session.rollback()
            raise ApplicationError(
                status_code=403,
                code="TEAM_CAPTAIN_REQUIRED",
                message="只有当前队长可以移除其他成员。",
            )
        if user_id == team.captain_user_id:
            await self._session.rollback()
            raise self._conflict(
                "CAPTAIN_TRANSFER_REQUIRED",
                "队长退出前必须先转让队长。",
            )
        target_member.left_at = now
        self._add_audit(
            audit_context,
            action="team.member_leave" if is_self else "team.member_remove",
            target_type="team",
            target_id=team.id,
            change_summary={"user_id": str(user_id)},
            now=now,
        )
        await self._session.commit()
        return OperationResponse()

    async def transfer_captain(
        self,
        team_id: UUID,
        payload: CaptainTransferRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> TeamResponse:
        self._require_student(audit_context.actor)
        team, competition = await self._mutable_team_for_captain(
            team_id, audit_context.actor.user.id
        )
        if (
            await self._competitions.current_member(
                team.id,
                payload.new_captain_user_id,
                for_update=True,
            )
            is None
        ):
            await self._session.rollback()
            raise self._not_found()
        old_captain = team.captain_user_id
        team.captain_user_id = payload.new_captain_user_id
        team.updated_at = self._clock()
        team.revision += 1
        self._add_audit(
            audit_context,
            action="team.captain_transfer",
            target_type="team",
            target_id=team.id,
            change_summary={
                "old_captain_user_id": str(old_captain),
                "new_captain_user_id": str(payload.new_captain_user_id),
            },
            now=team.updated_at,
        )
        await self._session.commit()
        return await self._team_response(
            team,
            actor_user_id=audit_context.actor.user.id,
            competition=competition,
        )

    async def dissolve_team(
        self,
        team_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> OperationResponse:
        self._require_student(audit_context.actor)
        team, _ = await self._mutable_team_for_captain(team_id, audit_context.actor.user.id)
        members = await self._competitions.current_members(team.id)
        if len(members) > 1:
            await self._session.rollback()
            raise self._conflict(
                "TEAM_NOT_EMPTY",
                "请先移除其他成员，再解散队伍。",
            )
        now = self._clock()
        for record in members:
            record.member.left_at = now
        team.status = "dissolved"
        team.captain_user_id = None
        team.dissolved_at = now
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="team.dissolve",
            target_type="team",
            target_id=team.id,
            change_summary={},
            now=now,
        )
        await self._session.commit()
        return OperationResponse()

    async def get_task(
        self,
        competition_id: UUID,
        task_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> CompetitionTaskResponse:
        competition = await self._competitions.get_competition(competition_id)
        task = await self._competitions.get_task(task_id, competition_id=competition_id)
        if (
            competition is None
            or task is None
            or competition.published_at is None
            or competition.status == "draft"
        ):
            raise self._not_found()
        team = await self._competitions.team_for_user(competition_id, context.user.id)
        return await self._task_response(task, team=team)

    async def create_competition(
        self,
        payload: CompetitionCreateRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> CompetitionDetailResponse:
        self._require_admin(audit_context.actor)
        now = self._clock()
        competition = Competition(
            id=uuid7(),
            name=payload.name.strip(),
            description_markdown=payload.description_markdown,
            description_html=render_markdown(payload.description_markdown),
            rules_url=str(payload.rules_url) if payload.rules_url is not None else None,
            status="draft",
            registration_start=payload.registration_start,
            registration_end=payload.registration_end,
            submission_start=payload.submission_start,
            submission_end=payload.submission_end,
            min_team_size=payload.min_team_size,
            max_team_size=payload.max_team_size,
            created_by=audit_context.actor.user.id,
            updated_by=audit_context.actor.user.id,
            published_at=None,
            archived_at=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._competitions.add_competition(competition)
        self._add_audit(
            audit_context,
            action="competition.create",
            target_type="competition",
            target_id=competition.id,
            change_summary={"name": competition.name},
            now=now,
        )
        await self._session.commit()
        return await self._detail_response(competition, user_id=audit_context.actor.user.id)

    @staticmethod
    def _validate_windows(
        registration_start: datetime,
        registration_end: datetime,
        submission_start: datetime,
        submission_end: datetime,
        min_team_size: int,
        max_team_size: int,
    ) -> None:
        if not (registration_start < registration_end <= submission_start < submission_end) or not (
            1 <= min_team_size <= max_team_size <= 20
        ):
            raise ApplicationError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="赛事时间或队伍人数范围不合法。",
            )

    async def patch_competition(
        self,
        competition_id: UUID,
        payload: CompetitionPatchRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> CompetitionDetailResponse:
        self._require_admin(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        if competition.revision != payload.revision:
            await self._session.rollback()
            raise self._conflict("REVISION_CONFLICT", "赛事已被其他管理员修改。")
        if competition.status == "archived":
            await self._session.rollback()
            raise self._conflict("COMPETITION_ARCHIVED", "归档赛事不能修改。")
        values = payload.model_dump(exclude_unset=True)
        values.pop("revision", None)
        now = self._clock()
        if competition.status != "draft":
            forbidden = {"registration_start", "min_team_size", "max_team_size"}
            if forbidden & values.keys():
                await self._session.rollback()
                raise self._conflict(
                    "COMPETITION_ALREADY_PUBLISHED",
                    "发布后不能修改报名开始或人数规则。",
                )
            for field in ("registration_end", "submission_start", "submission_end"):
                value = values.get(field)
                if value is not None and value < getattr(competition, field):
                    await self._session.rollback()
                    raise self._conflict(
                        "DEADLINE_CANNOT_MOVE_EARLIER",
                        "发布后的时间节点只能延后。",
                    )
        resolved = {
            "registration_start": values.get("registration_start", competition.registration_start),
            "registration_end": values.get("registration_end", competition.registration_end),
            "submission_start": values.get("submission_start", competition.submission_start),
            "submission_end": values.get("submission_end", competition.submission_end),
            "min_team_size": values.get("min_team_size", competition.min_team_size),
            "max_team_size": values.get("max_team_size", competition.max_team_size),
        }
        self._validate_windows(**resolved)
        tasks = await self._competitions.tasks(competition.id)
        if any(
            task.deadline < resolved["submission_start"]
            or task.deadline > resolved["submission_end"]
            for task in tasks
        ):
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="TASK_DEADLINE_OUTSIDE_WINDOW",
                message="修改后的提交窗口不能排除现有赛题截止时间。",
            )
        changed: list[str] = []
        for field, value in values.items():
            normalized: object = value
            if field in {"rules_url"}:
                normalized = str(value) if value is not None else None
            if field == "description_markdown":
                competition.description_html = render_markdown(cast(str, value))
            if getattr(competition, field) != normalized:
                setattr(competition, field, normalized)
                changed.append(field)
        competition.updated_by = audit_context.actor.user.id
        competition.updated_at = now
        competition.revision += 1
        self._add_audit(
            audit_context,
            action="competition.update",
            target_type="competition",
            target_id=competition.id,
            change_summary={"changed_fields": changed},
            now=now,
        )
        await self._session.commit()
        return await self._detail_response(competition, user_id=audit_context.actor.user.id)

    async def publish_competition(
        self,
        competition_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> CompetitionDetailResponse:
        self._require_admin(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        if competition.status != "draft":
            await self._session.rollback()
            raise self._conflict("STATE_CONFLICT", "赛事已经发布。")
        now = self._clock()
        competition.published_at = now
        competition.status = "registration_open"
        await self._advance_locked(competition, now)
        competition.updated_by = audit_context.actor.user.id
        competition.updated_at = now
        competition.revision += 1
        self._add_audit(
            audit_context,
            action="competition.publish",
            target_type="competition",
            target_id=competition.id,
            change_summary={"status": competition.status},
            now=now,
        )
        await self._session.commit()
        return await self._detail_response(competition, user_id=audit_context.actor.user.id)

    async def _lock_forming_teams(self, competition: Competition, now: datetime) -> None:
        teams = await self._competitions.forming_teams_for_update(competition.id)
        for team in teams:
            member_count = await self._competitions.member_count(team.id)
            if team_is_valid_for_lock(competition, team, member_count):
                team.status = "locked"
                team.locked_at = now
            else:
                team.status = "invalid"
            team.updated_at = now
            team.revision += 1

    async def _advance_locked(self, competition: Competition, now: datetime) -> bool:
        previous = competition.status
        target = timed_competition_status(competition, now)
        crossing_registration_end = previous in {"draft", "registration_open"} and target in {
            "registration_closed",
            "submission_open",
            "submission_closed",
        }
        if crossing_registration_end:
            await self._lock_forming_teams(competition, now)
        if target == previous:
            return False
        competition.status = target
        competition.updated_at = now
        competition.revision += 1
        return True

    async def close_registration(
        self,
        competition_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> CompetitionDetailResponse:
        self._require_admin(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        if competition.status != "registration_open":
            await self._session.rollback()
            raise self._conflict("STATE_CONFLICT", "当前赛事不能关闭报名。")
        now = self._clock()
        await self._lock_forming_teams(competition, now)
        competition.status = (
            "submission_open" if now >= competition.submission_start else "registration_closed"
        )
        competition.updated_at = now
        competition.updated_by = audit_context.actor.user.id
        competition.revision += 1
        self._add_audit(
            audit_context,
            action="competition.registration_close",
            target_type="competition",
            target_id=competition.id,
            change_summary={"status": competition.status},
            now=now,
        )
        await self._session.commit()
        return await self._detail_response(competition, user_id=audit_context.actor.user.id)

    async def close_submissions(
        self,
        competition_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> CompetitionDetailResponse:
        self._require_admin(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        if competition.status not in {"registration_closed", "submission_open"}:
            await self._session.rollback()
            raise self._conflict("STATE_CONFLICT", "当前赛事不能关闭提交。")
        now = self._clock()
        competition.status = "submission_closed"
        competition.updated_at = now
        competition.updated_by = audit_context.actor.user.id
        competition.revision += 1
        self._add_audit(
            audit_context,
            action="competition.submission_close",
            target_type="competition",
            target_id=competition.id,
            change_summary={},
            now=now,
        )
        await self._session.commit()
        return await self._detail_response(competition, user_id=audit_context.actor.user.id)

    async def archive_competition(
        self,
        competition_id: UUID,
        *,
        audit_context: CompetitionAuditContext,
    ) -> CompetitionDetailResponse:
        self._require_admin(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        if competition.status != "submission_closed":
            await self._session.rollback()
            raise self._conflict("STATE_CONFLICT", "只有已关闭提交的赛事可以归档。")
        now = self._clock()
        competition.status = "archived"
        competition.archived_at = now
        competition.updated_at = now
        competition.updated_by = audit_context.actor.user.id
        competition.revision += 1
        for record in await self._competitions.list_teams(competition.id):
            # Invalid/disqualified teams retain their terminal eligibility result
            # after the competition is archived. Only a valid locked team becomes
            # archived; this also preserves the database invariant that archived
            # teams have previously been locked.
            if record.team.status == "locked":
                record.team.status = "archived"
                record.team.updated_at = now
                record.team.revision += 1
        self._add_audit(
            audit_context,
            action="competition.archive",
            target_type="competition",
            target_id=competition.id,
            change_summary={},
            now=now,
        )
        await self._session.commit()
        return await self._detail_response(competition, user_id=audit_context.actor.user.id)

    async def create_task(
        self,
        competition_id: UUID,
        payload: CompetitionTaskCreateRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> CompetitionTaskResponse:
        self._require_admin(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        if competition.status not in {
            "draft",
            "registration_open",
            "registration_closed",
        }:
            await self._session.rollback()
            raise self._conflict("COMPETITION_TASKS_LOCKED", "当前赛事不能新增赛题。")
        if not (competition.submission_start <= payload.deadline <= competition.submission_end):
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="TASK_DEADLINE_OUTSIDE_WINDOW",
                message="赛题截止必须位于赛事提交窗口内。",
            )
        now = self._clock()
        task = CompetitionTask(
            id=uuid7(),
            competition_id=competition_id,
            title=payload.title.strip(),
            description_markdown=payload.description_markdown,
            description_html=render_markdown(payload.description_markdown),
            resource_url=(str(payload.resource_url) if payload.resource_url is not None else None),
            allowed_extensions=list(payload.allowed_extensions),
            max_total_bytes=payload.max_total_bytes,
            deadline=payload.deadline,
            display_order=payload.display_order,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._competitions.add_task(task)
        self._add_audit(
            audit_context,
            action="competition.task_create",
            target_type="competition_task",
            target_id=task.id,
            change_summary={"competition_id": str(competition_id)},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "TASK_DISPLAY_ORDER_CONFLICT",
                "赛题显示顺序已被占用。",
            ) from exc
        return await self._task_response(task, team=None)

    async def patch_task(
        self,
        task_id: UUID,
        payload: CompetitionTaskPatchRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> CompetitionTaskResponse:
        self._require_admin(audit_context.actor)
        task = await self._competitions.get_task(task_id, for_update=True)
        if task is None:
            await self._session.rollback()
            raise self._not_found()
        competition = await self._competitions.get_competition(task.competition_id, for_update=True)
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        if task.revision != payload.revision:
            await self._session.rollback()
            raise self._conflict("REVISION_CONFLICT", "赛题已被其他管理员修改。")
        if competition.status in {"submission_open", "submission_closed", "archived"}:
            await self._session.rollback()
            raise self._conflict("COMPETITION_TASKS_LOCKED", "提交开始后不能修改赛题。")
        values = payload.model_dump(exclude_unset=True)
        values.pop("revision", None)
        deadline = cast(datetime, values.get("deadline", task.deadline))
        if not competition.submission_start <= deadline <= competition.submission_end:
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="TASK_DEADLINE_OUTSIDE_WINDOW",
                message="赛题截止必须位于赛事提交窗口内。",
            )
        changed: list[str] = []
        for field, value in values.items():
            normalized: object = value
            if field == "resource_url":
                normalized = str(value) if value is not None else None
            if field == "description_markdown":
                task.description_html = render_markdown(cast(str, value))
            if getattr(task, field) != normalized:
                setattr(task, field, normalized)
                changed.append(field)
        now = self._clock()
        task.updated_at = now
        task.revision += 1
        self._add_audit(
            audit_context,
            action="competition.task_update",
            target_type="competition_task",
            target_id=task.id,
            change_summary={"changed_fields": changed},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "TASK_DISPLAY_ORDER_CONFLICT",
                "赛题显示顺序已被占用。",
            ) from exc
        return await self._task_response(task, team=None)

    async def admin_detail(
        self,
        competition_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> AdminCompetitionDetailResponse:
        self._require_admin(context)
        competition = await self._competitions.get_competition(competition_id)
        if competition is None:
            raise self._not_found()
        detail = await self._detail_response(competition, user_id=context.user.id)
        teams = await self._competitions.list_teams(competition_id)
        return AdminCompetitionDetailResponse(
            **detail.model_dump(),
            registration_count=await self._competitions.registration_count(competition_id),
            team_count=len(teams),
            valid_team_count=sum(record.team.status in {"locked", "archived"} for record in teams),
            invalid_team_count=sum(
                record.team.status in {"invalid", "disqualified"} for record in teams
            ),
        )

    async def admin_teams(
        self,
        competition_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> AdminTeamListResponse:
        self._require_admin(context)
        if await self._competitions.get_competition(competition_id) is None:
            raise self._not_found()
        records = await self._competitions.list_teams(competition_id)
        return AdminTeamListResponse(
            items=[
                AdminTeamListItem(
                    id=record.team.id,
                    competition_id=record.team.competition_id,
                    name=record.team.name,
                    status=cast(TeamStatus, record.team.status),
                    captain_user_id=record.team.captain_user_id,
                    member_count=record.member_count,
                    min_size_waived=record.team.min_size_waived_at is not None,
                    latest_submission_count=record.submission_count,
                )
                for record in records
            ],
            total=len(records),
        )

    async def admin_registrations(
        self,
        competition_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> AdminRegistrationListResponse:
        self._require_admin(context)
        if await self._competitions.get_competition(competition_id) is None:
            raise self._not_found()
        records = await self._competitions.registrations(competition_id)
        return AdminRegistrationListResponse(
            items=[self._admin_registration_item(record) for record in records],
            total=len(records),
        )

    async def disqualify_registration(
        self,
        competition_id: UUID,
        user_id: UUID,
        payload: AdminReasonRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> AdminRegistrationItem:
        self._require_admin(audit_context.actor)
        competition = await self._competitions.get_competition(competition_id, for_update=True)
        registration = await self._competitions.get_registration(
            competition_id,
            user_id,
            for_update=True,
        )
        user = await self._users.get_by_id(user_id)
        if competition is None or registration is None or user is None:
            await self._session.rollback()
            raise self._not_found()
        if competition.status == "archived":
            await self._session.rollback()
            raise self._conflict("COMPETITION_ARCHIVED", "归档赛事不能修改报名资格。")
        if registration.status == "disqualified":
            await self._session.rollback()
            raise self._conflict(
                "COMPETITION_DISQUALIFIED",
                "该学生已被取消本赛事参赛资格。",
            )

        now = self._clock()
        reason = payload.reason.strip()
        team = await self._competitions.team_for_user(
            competition_id,
            user_id,
            for_update=True,
        )
        if team is not None and team.status not in {"dissolved", "disqualified", "archived"}:
            team.status = "disqualified"
            team.disqualified_at = now
            team.disqualified_by = audit_context.actor.user.id
            team.disqualification_reason = "队内成员被取消个人参赛资格。"
            team.updated_at = now
            team.revision += 1
            self._add_audit(
                audit_context,
                action="admin.team.disqualify_by_registration",
                target_type="team",
                target_id=team.id,
                change_summary={"user_id": str(user_id)},
                now=now,
            )

        registration.status = "disqualified"
        registration.disqualified_at = now
        registration.disqualified_by = audit_context.actor.user.id
        registration.disqualification_reason = reason
        registration.updated_at = now
        registration.revision += 1
        self._add_audit(
            audit_context,
            action="admin.competition.registration_disqualify",
            target_type="competition_registration",
            target_id=registration.id,
            change_summary={
                "competition_id": str(competition_id),
                "user_id": str(user_id),
                "reason": reason,
            },
            now=now,
        )
        await self._session.commit()
        return AdminRegistrationItem(
            user_id=user.id,
            full_name=user.full_name,
            student_number=user.student_number,
            status="disqualified",
            registered_at=registration.registered_at,
            withdrawn_at=registration.withdrawn_at,
            disqualified_at=registration.disqualified_at,
            disqualification_reason=registration.disqualification_reason,
            team_id=team.id if team is not None else None,
            team_name=team.name if team is not None else None,
        )

    async def admin_team(
        self,
        team_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> AdminTeamDetailResponse:
        self._require_admin(context)
        team = await self._competitions.get_team(team_id)
        if team is None:
            raise self._not_found()
        detail = await self._team_response(team, actor_user_id=context.user.id)
        submissions: list[AdminTeamSubmissionItem] = []
        for task in await self._competitions.tasks(team.competition_id):
            submission = await self._competitions.task_submission(task.id, team.id)
            submissions.append(
                AdminTeamSubmissionItem(
                    task_id=task.id,
                    task_title=task.title,
                    deadline=task.deadline,
                    submission_id=submission.id if submission is not None else None,
                    latest_version_id=(
                        submission.latest_version_id if submission is not None else None
                    ),
                )
            )
        return AdminTeamDetailResponse(
            **detail.model_dump(),
            submissions=submissions,
        )

    async def admin_add_member(
        self,
        team_id: UUID,
        payload: AdminMemberAddRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> TeamResponse:
        self._require_admin(audit_context.actor)
        team = await self._competitions.get_team(team_id, for_update=True)
        if team is None or team.status in {"dissolved", "disqualified", "archived"}:
            await self._session.rollback()
            raise self._not_found()
        competition = await self._competitions.get_competition(team.competition_id, for_update=True)
        user = await self._users.get_by_id(payload.user_id, for_update=True)
        if competition is None or user is None or user.role != "student" or user.status != "active":
            await self._session.rollback()
            raise self._not_found()
        await self._require_registered(competition.id, user.id)
        if (
            await self._competitions.team_for_user(competition.id, user.id, for_update=True)
            is not None
        ):
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "该学生已加入本赛事其他队伍。")
        if await self._competitions.member_count(team.id) >= competition.max_team_size:
            await self._session.rollback()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        now = self._clock()
        self._competitions.add_member(
            TeamMember(
                id=uuid7(),
                team_id=team.id,
                competition_id=competition.id,
                user_id=user.id,
                joined_at=now,
                left_at=None,
                added_by_admin=True,
                admin_reason=payload.reason.strip(),
            )
        )
        member_count = await self._competitions.member_count(team.id)
        if team.status == "invalid" and (
            team.min_size_waived_at is not None or member_count + 1 >= competition.min_team_size
        ):
            team.status = "locked"
            team.locked_at = now
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="admin.team.member_add",
            target_type="team",
            target_id=team.id,
            change_summary={"user_id": str(user.id), "reason": payload.reason.strip()},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "并发操作后该学生已有队伍。") from exc
        return await self._team_response(
            team,
            actor_user_id=audit_context.actor.user.id,
            competition=competition,
        )

    async def admin_remove_member(
        self,
        team_id: UUID,
        user_id: UUID,
        payload: AdminReasonRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> TeamResponse:
        self._require_admin(audit_context.actor)
        team = await self._competitions.get_team(team_id, for_update=True)
        if team is None or team.status in {"dissolved", "archived"}:
            await self._session.rollback()
            raise self._not_found()
        if team.captain_user_id == user_id:
            await self._session.rollback()
            raise self._conflict(
                "CAPTAIN_TRANSFER_REQUIRED",
                "移除队长前必须先转让队长。",
            )
        member = await self._competitions.current_member(team.id, user_id, for_update=True)
        if member is None:
            await self._session.rollback()
            raise self._not_found()
        competition = await self._competitions.get_competition(
            team.competition_id,
            for_update=True,
        )
        if competition is None:
            await self._session.rollback()
            raise self._not_found()
        member_count = await self._competitions.member_count(team.id)
        now = self._clock()
        member.left_at = now
        if (
            team.status == "locked"
            and team.min_size_waived_at is None
            and member_count - 1 < competition.min_team_size
        ):
            team.status = "invalid"
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="admin.team.member_remove",
            target_type="team",
            target_id=team.id,
            change_summary={"user_id": str(user_id), "reason": payload.reason.strip()},
            now=now,
        )
        await self._session.commit()
        return await self._team_response(
            team,
            actor_user_id=audit_context.actor.user.id,
            competition=competition,
        )

    async def admin_transfer_captain(
        self,
        team_id: UUID,
        payload: AdminCaptainTransferRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> TeamResponse:
        self._require_admin(audit_context.actor)
        team = await self._competitions.get_team(team_id, for_update=True)
        if team is None or team.status in {"dissolved", "archived"}:
            await self._session.rollback()
            raise self._not_found()
        if (
            await self._competitions.current_member(
                team.id,
                payload.new_captain_user_id,
                for_update=True,
            )
            is None
        ):
            await self._session.rollback()
            raise self._not_found()
        old_captain = team.captain_user_id
        now = self._clock()
        team.captain_user_id = payload.new_captain_user_id
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="admin.team.captain_transfer",
            target_type="team",
            target_id=team.id,
            change_summary={
                "old_captain_user_id": str(old_captain),
                "new_captain_user_id": str(payload.new_captain_user_id),
                "reason": payload.reason.strip(),
            },
            now=now,
        )
        await self._session.commit()
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    async def waive_min_size(
        self,
        team_id: UUID,
        payload: AdminReasonRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> TeamResponse:
        self._require_admin(audit_context.actor)
        team = await self._competitions.get_team(team_id, for_update=True)
        if team is None or team.status in {"dissolved", "disqualified", "archived"}:
            await self._session.rollback()
            raise self._not_found()
        now = self._clock()
        team.min_size_waived_at = now
        team.min_size_waived_by = audit_context.actor.user.id
        team.waiver_reason = payload.reason.strip()
        if team.status == "invalid":
            team.status = "locked"
            team.locked_at = now
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="admin.team.waive_min_size",
            target_type="team",
            target_id=team.id,
            change_summary={"reason": payload.reason.strip()},
            now=now,
        )
        await self._session.commit()
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    async def disqualify_team(
        self,
        team_id: UUID,
        payload: AdminReasonRequest,
        *,
        audit_context: CompetitionAuditContext,
    ) -> TeamResponse:
        self._require_admin(audit_context.actor)
        team = await self._competitions.get_team(team_id, for_update=True)
        if team is None or team.status in {"dissolved", "disqualified", "archived"}:
            await self._session.rollback()
            raise self._not_found()
        now = self._clock()
        team.status = "disqualified"
        team.disqualified_at = now
        team.disqualified_by = audit_context.actor.user.id
        team.disqualification_reason = payload.reason.strip()
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="admin.team.disqualify",
            target_type="team",
            target_id=team.id,
            change_summary={"reason": payload.reason.strip()},
            now=now,
        )
        await self._session.commit()
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    async def advance_due(self) -> int:
        now = self._clock()
        ids = await self._competitions.lifecycle_candidate_ids(now)
        changed = 0
        for competition_id in ids:
            competition = await self._competitions.get_competition(competition_id, for_update=True)
            if competition is None:
                continue
            if await self._advance_locked(competition, now):
                changed += 1
        if changed:
            await self._session.commit()
        else:
            await self._session.rollback()
        return changed


class CompetitionLifecycleProcessor:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._clock = clock

    async def run_once(self) -> int:
        async with self._factory() as session:
            service = CompetitionService(
                session,
                self._settings,
                clock=self._clock,
            )
            return await service.advance_due()
