import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.models import AuthSecurityEvent
from app.auth.repository import AuthRepository
from app.auth.service import AuthenticatedContext, context_effective_role, context_is_admin
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.teams.models import Team, TeamInvitation, TeamMember, TeamProfile
from app.teams.repository import TeamRepository
from app.teams.schemas import (
    AdminCaptainTransferRequest,
    AdminMemberAddRequest,
    AdminReasonRequest,
    AdminTeamListItem,
    AdminTeamListResponse,
    AutoAssignResponse,
    CaptainTransferRequest,
    InviteCodeRotatedResponse,
    OperationResponse,
    TeamCreatedResponse,
    TeamDirectoryItem,
    TeamDirectoryResponse,
    TeamInvitationCreateRequest,
    TeamInvitationListResponse,
    TeamInvitationResponse,
    TeamMemberResponse,
    TeamProfilePage,
    TeamProfileResponse,
    TeamProfileUpsertRequest,
    TeamResponse,
    TeamStatus,
)
from app.users.repository import UserRepository

DEFAULT_TEAM_MAX_MEMBERS = 5


@dataclass(frozen=True, slots=True)
class TeamAuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


class TeamService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._teams = TeamRepository(session)
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
                message="管理员不能通过学生接口执行队伍操作。",
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
        audit_context: TeamAuditContext,
        *,
        action: str,
        target_id: UUID,
        change_summary: dict[str, object],
        now: datetime,
        target_type: str = "team",
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

    async def _team_response(self, team: Team, *, actor_user_id: UUID) -> TeamResponse:
        members = await self._teams.current_members(team.id)
        return TeamResponse(
            id=team.id,
            name=team.name,
            status=cast(TeamStatus, team.status),
            captain_user_id=team.captain_user_id,
            member_count=len(members),
            max_members=team.max_members,
            dissolved_at=team.dissolved_at,
            revision=team.revision,
            members=[
                TeamMemberResponse(
                    user_id=record.user.id,
                    full_name=record.user.full_name,
                    student_number=record.user.student_number,
                    joined_at=record.member.joined_at,
                    added_by_admin=record.member.added_by_admin,
                    is_captain=record.user.id == team.captain_user_id,
                    direction_name=record.direction_name,
                    introduction=(record.profile.introduction if record.profile else None),
                )
                for record in members
            ],
            can_manage=team.status == "forming" and team.captain_user_id == actor_user_id,
        )

    async def my_profile(self, *, context: AuthenticatedContext) -> TeamProfileResponse | None:
        self._require_student(context)
        profile = await self._teams.profile_for_user(context.user.id)
        if profile is None:
            return None
        direction_name: str | None = None
        if context.user.direction_id is not None:
            direction = await self._users.get_direction(context.user.direction_id)
            direction_name = direction.name if direction is not None else None
        return TeamProfileResponse(
            user_id=context.user.id,
            full_name=context.user.full_name,
            direction_name=direction_name,
            introduction=profile.introduction,
            updated_at=profile.updated_at,
            revision=profile.revision,
        )

    async def profiles(
        self,
        *,
        context: AuthenticatedContext,
        query: str | None,
        page: int,
        page_size: int,
    ) -> TeamProfilePage:
        self._require_student(context)
        records, total = await self._teams.list_profiles(
            query=query, page=page, page_size=page_size
        )
        actor_team = await self._teams.team_for_user(context.user.id)
        can_send = False
        pending_invitees: set[UUID] = set()
        if actor_team is not None:
            can_send = await self._teams.member_count(actor_team.id) < actor_team.max_members
            pending_invitees = await self._teams.pending_invitee_ids(actor_team.id)
        return TeamProfilePage(
            items=[
                TeamProfileResponse(
                    user_id=record.user.id,
                    full_name=record.user.full_name,
                    direction_name=record.direction_name,
                    introduction=record.profile.introduction,
                    updated_at=record.profile.updated_at,
                    revision=record.profile.revision,
                    can_invite=(
                        can_send
                        and record.user.id != context.user.id
                        and record.team_id is None
                        and record.user.id not in pending_invitees
                    ),
                    invitation_pending=record.user.id in pending_invitees,
                )
                for record in records
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def upsert_profile(
        self,
        payload: TeamProfileUpsertRequest,
        *,
        audit_context: TeamAuditContext,
    ) -> TeamProfileResponse:
        self._require_student(audit_context.actor)
        profile = await self._teams.profile_for_user(audit_context.actor.user.id, for_update=True)
        now = self._clock()
        if profile is None:
            if payload.revision is not None:
                await self._session.rollback()
                raise self._conflict("REVISION_CONFLICT", "个人简介已发生变化，请刷新后重试。")
            profile = TeamProfile(
                user_id=audit_context.actor.user.id,
                introduction=payload.introduction,
                created_at=now,
                updated_at=now,
                revision=1,
            )
            self._teams.add_profile(profile)
        else:
            if payload.revision != profile.revision:
                await self._session.rollback()
                raise self._conflict("REVISION_CONFLICT", "个人简介已发生变化，请刷新后重试。")
            profile.introduction = payload.introduction
            profile.updated_at = now
            profile.revision += 1
        self._add_audit(
            audit_context,
            action="team.profile_upsert",
            target_id=audit_context.actor.user.id,
            target_type="team_profile",
            change_summary={"revision": profile.revision},
            now=now,
        )
        await self._session.commit()
        response = await self.my_profile(context=audit_context.actor)
        assert response is not None
        return response

    @staticmethod
    def _invitation_response(
        invitation: TeamInvitation, team: Team, invited_by_full_name: str
    ) -> TeamInvitationResponse:
        return TeamInvitationResponse(
            id=invitation.id,
            team_id=team.id,
            team_name=team.name,
            invited_by_full_name=invited_by_full_name,
            status=cast(Literal["pending", "accepted", "declined", "cancelled"], invitation.status),
            created_at=invitation.created_at,
            responded_at=invitation.responded_at,
            revision=invitation.revision,
        )

    async def invitations(self, *, context: AuthenticatedContext) -> TeamInvitationListResponse:
        self._require_student(context)
        if await self._teams.team_for_user(context.user.id) is not None:
            return TeamInvitationListResponse(items=[])
        records = await self._teams.received_pending_invitations(context.user.id)
        return TeamInvitationListResponse(
            items=[
                self._invitation_response(
                    record.invitation, record.team, record.invited_by.full_name
                )
                for record in records
            ]
        )

    async def create_invitation(
        self,
        payload: TeamInvitationCreateRequest,
        *,
        audit_context: TeamAuditContext,
    ) -> TeamInvitationResponse:
        self._require_student(audit_context.actor)
        team = await self._teams.team_for_user(audit_context.actor.user.id, for_update=True)
        if team is None:
            await self._session.rollback()
            raise self._conflict("TEAM_REQUIRED", "请先创建或加入一支队伍，再邀请成员。")
        if await self._teams.member_count(team.id) >= team.max_members:
            await self._session.rollback()
            raise self._conflict("TEAM_FULL", "当前队伍人数已满。")
        target = await self._users.get_by_id(payload.invitee_user_id, for_update=True)
        if (
            target is None
            or target.id == audit_context.actor.user.id
            or target.role != "student"
            or target.status != "active"
            or await self._teams.profile_for_user(target.id) is None
        ):
            await self._session.rollback()
            raise self._not_found()
        if await self._teams.team_for_user(target.id, for_update=True) is not None:
            await self._session.rollback()
            raise self._conflict("INVITEE_ALREADY_IN_TEAM", "该同学已经加入队伍。")
        existing = await self._teams.pending_invitation(team.id, target.id)
        if existing is not None:
            inviter = await self._users.get_by_id(existing.invited_by_user_id)
            return self._invitation_response(
                existing,
                team,
                inviter.full_name if inviter is not None else "队伍成员",
            )
        now = self._clock()
        team_id = team.id
        target_id = target.id
        invitation = TeamInvitation(
            id=uuid7(),
            team_id=team_id,
            invitee_user_id=target_id,
            invited_by_user_id=audit_context.actor.user.id,
            status="pending",
            responded_at=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._teams.add_invitation(invitation)
        self._add_audit(
            audit_context,
            action="team.invitation_create",
            target_id=invitation.id,
            target_type="team_invitation",
            change_summary={"team_id": str(team_id)},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            existing = await self._teams.pending_invitation(team_id, target_id)
            recovered_team = await self._teams.get_team(team_id) if existing is not None else None
            if existing is not None and recovered_team is not None:
                inviter = await self._users.get_by_id(existing.invited_by_user_id)
                return self._invitation_response(
                    existing,
                    recovered_team,
                    inviter.full_name if inviter is not None else "队伍成员",
                )
            raise self._conflict(
                "TEAM_INVITATION_CONFLICT", "邀请状态发生变化，请刷新后重试。"
            ) from exc
        return self._invitation_response(invitation, team, audit_context.actor.user.full_name)

    async def respond_to_invitation(
        self,
        invitation_id: UUID,
        *,
        accept: bool,
        audit_context: TeamAuditContext,
    ) -> TeamResponse | OperationResponse:
        self._require_student(audit_context.actor)
        invitation = await self._teams.invitation_for_invitee(
            invitation_id, audit_context.actor.user.id, for_update=True
        )
        if invitation is None:
            await self._session.rollback()
            raise self._not_found()
        if invitation.status != "pending":
            await self._session.rollback()
            raise self._conflict("INVITATION_NOT_PENDING", "该邀请已经处理。")
        now = self._clock()
        if not accept:
            invitation.status = "declined"
            invitation.responded_at = now
            invitation.updated_at = now
            invitation.revision += 1
            self._add_audit(
                audit_context,
                action="team.invitation_decline",
                target_id=invitation.id,
                target_type="team_invitation",
                change_summary={"team_id": str(invitation.team_id)},
                now=now,
            )
            await self._session.commit()
            return OperationResponse()
        team = await self._teams.get_team(invitation.team_id, for_update=True)
        if team is None or team.status != "forming":
            invitation.status = "cancelled"
            invitation.responded_at = now
            invitation.updated_at = now
            invitation.revision += 1
            await self._session.commit()
            raise self._conflict("INVITATION_UNAVAILABLE", "邀请对应的队伍已不可加入。")
        if (
            await self._teams.team_for_user(audit_context.actor.user.id, for_update=True)
            is not None
        ):
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "当前账号已经加入一支队伍。")
        if await self._teams.member_count(team.id) >= team.max_members:
            await self._session.rollback()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        self._teams.add_member(
            TeamMember(
                id=uuid7(),
                team_id=team.id,
                user_id=audit_context.actor.user.id,
                joined_at=now,
                left_at=None,
                added_by_admin=False,
                admin_reason=None,
            )
        )
        invitation.status = "accepted"
        invitation.responded_at = now
        invitation.updated_at = now
        invitation.revision += 1
        team.updated_at = now
        team.revision += 1
        await self._teams.cancel_pending_for_invitee(
            audit_context.actor.user.id, responded_at=now, exclude_id=invitation.id
        )
        self._add_audit(
            audit_context,
            action="team.invitation_accept",
            target_id=invitation.id,
            target_type="team_invitation",
            change_summary={"team_id": str(team.id)},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "TEAM_MEMBERSHIP_CONFLICT", "组队状态发生变化，请刷新后重试。"
            ) from exc
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    async def public_teams(
        self,
        *,
        context: AuthenticatedContext,
        query: str | None,
        page: int,
        page_size: int,
    ) -> TeamDirectoryResponse:
        self._require_student(context)
        records, total = await self._teams.list_public_teams(
            query=query,
            page=page,
            page_size=page_size,
        )
        already_in_team = await self._teams.team_for_user(context.user.id) is not None
        return TeamDirectoryResponse(
            items=[
                TeamDirectoryItem(
                    id=record.team.id,
                    name=record.team.name,
                    status=cast(TeamStatus, record.team.status),
                    member_count=record.member_count,
                    max_members=record.team.max_members,
                    can_join=(
                        not already_in_team
                        and record.team.status == "forming"
                        and record.member_count < record.team.max_members
                    ),
                )
                for record in records
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def my_team(self, *, context: AuthenticatedContext) -> TeamResponse | None:
        self._require_student(context)
        team = await self._teams.team_for_user(context.user.id)
        if team is None:
            return None
        return await self._team_response(team, actor_user_id=context.user.id)

    async def create_team(
        self,
        name: str,
        *,
        audit_context: TeamAuditContext,
    ) -> TeamCreatedResponse:
        self._require_student(audit_context.actor)
        if (
            await self._teams.team_for_user(
                audit_context.actor.user.id,
                for_update=True,
            )
            is not None
        ):
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "当前账号已经加入一支队伍。")
        now = self._clock()
        invite_code = self._new_invite_code()
        team = Team(
            id=uuid7(),
            name=name.strip(),
            status="forming",
            captain_user_id=audit_context.actor.user.id,
            invite_code_hash=self._invite_hash(invite_code),
            invite_code_rotated_at=now,
            max_members=DEFAULT_TEAM_MAX_MEMBERS,
            dissolved_at=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._teams.add_team(team)
        self._teams.add_member(
            TeamMember(
                id=uuid7(),
                team_id=team.id,
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
            target_id=team.id,
            change_summary={"name": team.name, "max_members": team.max_members},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "TEAM_NAME_OR_MEMBERSHIP_CONFLICT",
                "队伍名称已存在，或当前账号已经加入其他队伍。",
            ) from exc
        response = await self._team_response(team, actor_user_id=audit_context.actor.user.id)
        return TeamCreatedResponse(**response.model_dump(), invite_code=invite_code)

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
        invite_code: str,
        *,
        audit_context: TeamAuditContext,
    ) -> TeamResponse:
        self._require_student(audit_context.actor)
        now = self._clock()
        await self._record_invite_attempt(
            user_id=audit_context.actor.user.id,
            ip_prefix=audit_context.ip_prefix,
            now=now,
        )
        if (
            await self._teams.team_for_user(
                audit_context.actor.user.id,
                for_update=True,
            )
            is not None
        ):
            await self._session.commit()
            raise self._conflict("ALREADY_IN_TEAM", "当前账号已经加入一支队伍。")
        team = await self._teams.team_by_invite_hash(
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
        if await self._teams.member_count(team.id) >= team.max_members:
            await self._session.commit()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        self._teams.add_member(
            TeamMember(
                id=uuid7(),
                team_id=team.id,
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
                "并发操作后当前账号已经加入一支队伍。",
            ) from exc
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    async def auto_assign(self, *, audit_context: TeamAuditContext) -> AutoAssignResponse:
        self._require_student(audit_context.actor)
        if (
            await self._teams.team_for_user(
                audit_context.actor.user.id,
                for_update=True,
            )
            is not None
        ):
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "当前账号已经加入一支队伍。")
        selected: Team | None = None
        selected_count = 0
        for candidate in await self._teams.forming_teams_for_update():
            candidate_count = await self._teams.member_count(candidate.id)
            if candidate_count >= candidate.max_members:
                continue
            if selected is None or (
                candidate_count,
                candidate.created_at,
                candidate.id,
            ) < (selected_count, selected.created_at, selected.id):
                selected = candidate
                selected_count = candidate_count

        now = self._clock()
        assignment: Literal["joined", "created"] = "joined"
        invite_code: str | None = None
        if selected is None:
            assignment = "created"
            invite_code = self._new_invite_code()
            selected = Team(
                id=uuid7(),
                name="自动组队-" + secrets.token_hex(3).upper(),
                status="forming",
                captain_user_id=audit_context.actor.user.id,
                invite_code_hash=self._invite_hash(invite_code),
                invite_code_rotated_at=now,
                max_members=DEFAULT_TEAM_MAX_MEMBERS,
                dissolved_at=None,
                created_at=now,
                updated_at=now,
                revision=1,
            )
            self._teams.add_team(selected)
        self._teams.add_member(
            TeamMember(
                id=uuid7(),
                team_id=selected.id,
                user_id=audit_context.actor.user.id,
                joined_at=now,
                left_at=None,
                added_by_admin=False,
                admin_reason=None,
            )
        )
        self._add_audit(
            audit_context,
            action="team.auto_assign",
            target_id=selected.id,
            change_summary={"assignment": assignment},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "TEAM_MEMBERSHIP_CONFLICT",
                "队伍分配发生并发冲突，请重试。",
            ) from exc
        response = await self._team_response(
            selected,
            actor_user_id=audit_context.actor.user.id,
        )
        return AutoAssignResponse(
            **response.model_dump(),
            assignment=assignment,
            invite_code=invite_code,
        )

    async def _mutable_team_for_captain(self, team_id: UUID, actor_user_id: UUID) -> Team:
        team = await self._teams.get_team(team_id, for_update=True)
        if team is None or team.status != "forming":
            await self._session.rollback()
            raise self._not_found()
        if team.captain_user_id != actor_user_id:
            await self._session.rollback()
            raise ApplicationError(
                status_code=403,
                code="TEAM_CAPTAIN_REQUIRED",
                message="只有当前队长可以执行此操作。",
            )
        return team

    async def rotate_invite_code(
        self,
        team_id: UUID,
        *,
        audit_context: TeamAuditContext,
    ) -> InviteCodeRotatedResponse:
        self._require_student(audit_context.actor)
        team = await self._mutable_team_for_captain(team_id, audit_context.actor.user.id)
        now = self._clock()
        invite_code = self._new_invite_code()
        team.invite_code_hash = self._invite_hash(invite_code)
        team.invite_code_rotated_at = now
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="team.invite_rotate",
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

    async def remove_member(
        self,
        team_id: UUID,
        user_id: UUID,
        *,
        audit_context: TeamAuditContext,
    ) -> OperationResponse:
        self._require_student(audit_context.actor)
        team = await self._teams.get_team(team_id, for_update=True)
        if team is None or team.status != "forming":
            await self._session.rollback()
            raise self._not_found()
        actor_member = await self._teams.current_member(
            team.id,
            audit_context.actor.user.id,
            for_update=True,
        )
        target_member = await self._teams.current_member(team.id, user_id, for_update=True)
        if actor_member is None or target_member is None:
            await self._session.rollback()
            raise self._not_found()
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
            raise self._conflict("CAPTAIN_TRANSFER_REQUIRED", "队长退出前必须先转让队长。")
        now = self._clock()
        target_member.left_at = now
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="team.member_leave" if is_self else "team.member_remove",
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
        audit_context: TeamAuditContext,
    ) -> TeamResponse:
        self._require_student(audit_context.actor)
        team = await self._mutable_team_for_captain(team_id, audit_context.actor.user.id)
        if (
            await self._teams.current_member(
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
            action="team.captain_transfer",
            target_id=team.id,
            change_summary={
                "old_captain_user_id": str(old_captain),
                "new_captain_user_id": str(payload.new_captain_user_id),
            },
            now=now,
        )
        await self._session.commit()
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    async def dissolve_team(
        self,
        team_id: UUID,
        *,
        audit_context: TeamAuditContext,
    ) -> OperationResponse:
        self._require_student(audit_context.actor)
        team = await self._mutable_team_for_captain(team_id, audit_context.actor.user.id)
        members = await self._teams.current_members_for_update(team.id)
        if len(members) > 1:
            await self._session.rollback()
            raise self._conflict("TEAM_NOT_EMPTY", "请先移除其他成员，再解散队伍。")
        now = self._clock()
        for member in members:
            member.left_at = now
        team.status = "dissolved"
        team.captain_user_id = None
        team.dissolved_at = now
        team.updated_at = now
        team.revision += 1
        await self._teams.cancel_pending_for_team(team.id, responded_at=now)
        self._add_audit(
            audit_context,
            action="team.dissolve",
            target_id=team.id,
            change_summary={},
            now=now,
        )
        await self._session.commit()
        return OperationResponse()

    async def admin_teams(
        self,
        *,
        context: AuthenticatedContext,
        query: str | None,
        page: int,
        page_size: int,
    ) -> AdminTeamListResponse:
        self._require_admin(context)
        records, total = await self._teams.list_admin_teams(
            query=query,
            page=page,
            page_size=page_size,
        )
        return AdminTeamListResponse(
            items=[
                AdminTeamListItem(
                    id=record.team.id,
                    name=record.team.name,
                    status=cast(TeamStatus, record.team.status),
                    captain_user_id=record.team.captain_user_id,
                    member_count=record.member_count,
                    max_members=record.team.max_members,
                )
                for record in records
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def admin_team(
        self,
        team_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> TeamResponse:
        self._require_admin(context)
        team = await self._teams.get_team(team_id)
        if team is None or team.status != "forming":
            raise self._not_found()
        return await self._team_response(team, actor_user_id=context.user.id)

    async def delete_admin_team(
        self,
        team_id: UUID,
        payload: AdminReasonRequest,
        *,
        audit_context: TeamAuditContext,
    ) -> None:
        self._require_admin(audit_context.actor)
        team = await self._teams.get_team(team_id, for_update=True)
        if team is None or team.status != "forming":
            await self._session.rollback()
            raise self._not_found()
        current_members = await self._teams.current_members_for_update(team.id)
        now = self._clock()
        self._add_audit(
            audit_context,
            action="admin.team.delete",
            target_id=team.id,
            change_summary={
                "mode": "physical",
                "released_member_count": len(current_members),
                "reason": payload.reason,
            },
            now=now,
        )
        await self._teams.delete_team(team)
        await self._session.commit()

    async def admin_add_member(
        self,
        team_id: UUID,
        payload: AdminMemberAddRequest,
        *,
        audit_context: TeamAuditContext,
    ) -> TeamResponse:
        self._require_admin(audit_context.actor)
        team = await self._teams.get_team(team_id, for_update=True)
        user = await self._users.get_by_id(payload.user_id, for_update=True)
        if (
            team is None
            or team.status != "forming"
            or user is None
            or user.role != "student"
            or user.status != "active"
        ):
            await self._session.rollback()
            raise self._not_found()
        if await self._teams.team_for_user(user.id, for_update=True) is not None:
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "该学生已经加入其他队伍。")
        if await self._teams.member_count(team.id) >= team.max_members:
            await self._session.rollback()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        now = self._clock()
        self._teams.add_member(
            TeamMember(
                id=uuid7(),
                team_id=team.id,
                user_id=user.id,
                joined_at=now,
                left_at=None,
                added_by_admin=True,
                admin_reason=payload.reason,
            )
        )
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="admin.team.member_add",
            target_id=team.id,
            change_summary={"user_id": str(user.id), "reason": payload.reason},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "并发操作后该学生已有队伍。") from exc
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    async def admin_remove_member(
        self,
        team_id: UUID,
        user_id: UUID,
        payload: AdminReasonRequest,
        *,
        audit_context: TeamAuditContext,
    ) -> TeamResponse:
        self._require_admin(audit_context.actor)
        team = await self._teams.get_team(team_id, for_update=True)
        if team is None or team.status != "forming":
            await self._session.rollback()
            raise self._not_found()
        if team.captain_user_id == user_id:
            await self._session.rollback()
            raise self._conflict("CAPTAIN_TRANSFER_REQUIRED", "移除队长前必须先转让队长。")
        member = await self._teams.current_member(team.id, user_id, for_update=True)
        if member is None:
            await self._session.rollback()
            raise self._not_found()
        now = self._clock()
        member.left_at = now
        team.updated_at = now
        team.revision += 1
        self._add_audit(
            audit_context,
            action="admin.team.member_remove",
            target_id=team.id,
            change_summary={"user_id": str(user_id), "reason": payload.reason},
            now=now,
        )
        await self._session.commit()
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    async def admin_transfer_captain(
        self,
        team_id: UUID,
        payload: AdminCaptainTransferRequest,
        *,
        audit_context: TeamAuditContext,
    ) -> TeamResponse:
        self._require_admin(audit_context.actor)
        team = await self._teams.get_team(team_id, for_update=True)
        if team is None or team.status != "forming":
            await self._session.rollback()
            raise self._not_found()
        if (
            await self._teams.current_member(
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
            target_id=team.id,
            change_summary={
                "old_captain_user_id": str(old_captain),
                "new_captain_user_id": str(payload.new_captain_user_id),
                "reason": payload.reason,
            },
            now=now,
        )
        await self._session.commit()
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)
