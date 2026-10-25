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
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.teams.composition import (
    TeamCompositionService,
    composition_for,
    effective_team_capacity,
)
from app.teams.models import (
    Team,
    TeamApplication,
    TeamInvitation,
    TeamMember,
    TeamProfile,
    TeamSettings,
)
from app.teams.repository import TeamApplicationRecord, TeamRepository
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
    TeamApplicationListResponse,
    TeamApplicationResponse,
    TeamCreatedResponse,
    TeamDirectoryItem,
    TeamDirectoryResponse,
    TeamInvitationCreateRequest,
    TeamInvitationListResponse,
    TeamInvitationResponse,
    TeamMemberResponse,
    TeamProfileDirectionResponse,
    TeamProfilePage,
    TeamProfileResponse,
    TeamProfileUpsertRequest,
    TeamRenameRequest,
    TeamResponse,
    TeamSettingsResponse,
    TeamSettingsUpdateRequest,
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
        self._team_settings = TeamRepository(session)
        self._composition = TeamCompositionService(session)
        self._users = UserRepository(session)
        self._auth = AuthRepository(session)
        self._audit = AuditRepository(session)
        self._outbox = OutboxRepository(session)
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

    async def _team_settings_record(self, *, for_update: bool = False) -> TeamSettings:
        settings = await self._team_settings.team_settings(for_update=for_update)
        if settings is None:
            raise RuntimeError("team_settings singleton is missing")
        return settings

    async def _require_team_open(self) -> None:
        if not (await self._team_settings_record(for_update=True)).is_team_open:
            raise self._conflict(
                "TEAM_REGISTRATION_CLOSED",
                "管理员暂未开放组队，请先完善个人简介。",
            )

    @staticmethod
    def _settings_response(settings: TeamSettings) -> TeamSettingsResponse:
        return TeamSettingsResponse(
            is_team_open=settings.is_team_open,
            is_direction_change_open=settings.is_direction_change_open,
            updated_at=settings.updated_at,
            revision=settings.revision,
        )

    async def _team_response(self, team: Team, *, actor_user_id: UUID) -> TeamResponse:
        members = await self._teams.current_members(team.id)
        captain_email = next(
            (record.user.email for record in members if record.user.id == team.captain_user_id),
            None,
        )
        return TeamResponse(
            id=team.id,
            name=team.name,
            status=cast(TeamStatus, team.status),
            captain_user_id=team.captain_user_id,
            member_count=len(members),
            composition=composition_for(record.direction_name for record in members),
            max_members=effective_team_capacity(team.max_members),
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
            captain_email=captain_email,
            contact_wechat=team.contact_wechat,
        )

    async def team_settings(self, *, context: AuthenticatedContext) -> TeamSettingsResponse:
        self._require_student(context)
        return self._settings_response(await self._team_settings_record())

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
        direction_id: UUID | None,
        page: int,
        page_size: int,
    ) -> TeamProfilePage:
        self._require_student(context)
        settings = await self._team_settings_record()
        records, total = await self._teams.list_profiles(
            query=query,
            direction_id=direction_id,
            page=page,
            page_size=page_size,
        )
        directions = await self._teams.list_active_directions()
        actor_team = (
            await self._teams.team_for_user(context.user.id) if settings.is_team_open else None
        )
        can_send = False
        pending_invitees: set[UUID] = set()
        if actor_team is not None:
            can_send = await self._teams.member_count(actor_team.id) < effective_team_capacity(
                actor_team.max_members
            )
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
                        settings.is_team_open
                        and can_send
                        and record.user.id != context.user.id
                        and record.team_id is None
                        and record.user.id not in pending_invitees
                        and actor_team is not None
                        and await self._composition.can_add(actor_team.id, record.user.id)
                    ),
                    invitation_pending=settings.is_team_open and record.user.id in pending_invitees,
                )
                for record in records
            ],
            total=total,
            page=page,
            page_size=page_size,
            team_open=settings.is_team_open,
            directions=[
                TeamProfileDirectionResponse(id=direction.id, name=direction.name)
                for direction in directions
            ],
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
        if not (await self._team_settings_record()).is_team_open:
            return TeamInvitationListResponse(items=[])
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
        await self._require_team_open()
        team = await self._teams.team_for_user(audit_context.actor.user.id, for_update=True)
        if team is None:
            await self._session.rollback()
            raise self._conflict("TEAM_REQUIRED", "请先创建或加入一支队伍，再邀请成员。")
        if await self._teams.member_count(team.id) >= effective_team_capacity(team.max_members):
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
        await self._composition.require_add(team.id, target.id)
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
        await self._require_team_open()
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
        if await self._teams.member_count(team.id) >= effective_team_capacity(team.max_members):
            await self._session.rollback()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        await self._composition.require_add(team.id, audit_context.actor.user.id)
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
        await self._require_team_open()
        records, total = await self._teams.list_public_teams(
            query=query,
            page=page,
            page_size=page_size,
        )
        current_team = await self._teams.team_for_user(context.user.id)
        return TeamDirectoryResponse(
            items=[
                TeamDirectoryItem(
                    id=record.team.id,
                    name=record.team.name,
                    status=cast(TeamStatus, record.team.status),
                    member_count=record.member_count,
                    max_members=effective_team_capacity(record.team.max_members),
                    can_join=(
                        current_team is None
                        and record.team.status == "forming"
                        and record.member_count < effective_team_capacity(record.team.max_members)
                        and await self._composition.can_add(record.team.id, context.user.id)
                    ),
                    can_apply=(
                        (current_team is None or current_team.id != record.team.id)
                        and (
                            current_team is None or current_team.captain_user_id != context.user.id
                        )
                        and record.member_count < effective_team_capacity(record.team.max_members)
                        and await self._composition.can_add(record.team.id, context.user.id)
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
        contact_wechat: str | None = None,
        audit_context: TeamAuditContext,
    ) -> TeamCreatedResponse:
        self._require_student(audit_context.actor)
        await self._require_team_open()
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
        await self._composition.require_add(None, audit_context.actor.user.id)
        team = Team(
            id=uuid7(),
            name=name.strip(),
            contact_wechat=(
                contact_wechat.strip() if contact_wechat and contact_wechat.strip() else None
            ),
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
            change_summary={
                "name": team.name,
                "max_members": effective_team_capacity(team.max_members),
            },
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
        await self._require_team_open()
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
        if await self._teams.member_count(team.id) >= effective_team_capacity(team.max_members):
            await self._session.commit()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        await self._composition.require_add(team.id, audit_context.actor.user.id)
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
        await self._require_team_open()
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
        await self._composition.require_add(None, audit_context.actor.user.id)
        for candidate in await self._teams.forming_teams_for_update():
            candidate_count = await self._teams.member_count(candidate.id)
            if candidate_count >= effective_team_capacity(candidate.max_members):
                continue
            if not await self._composition.can_add(candidate.id, audit_context.actor.user.id):
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

    async def rename_team(
        self, team_id: UUID, payload: TeamRenameRequest, *, audit_context: TeamAuditContext
    ) -> TeamResponse:
        self._require_student(audit_context.actor)
        await self._require_team_open()
        team = await self._mutable_team_for_captain(team_id, audit_context.actor.user.id)
        if team.revision != payload.revision:
            await self._session.rollback()
            raise self._conflict("REVISION_CONFLICT", "队伍信息已更新，请刷新后重试。")
        if team.name != payload.name:
            old_name = team.name
            team.name = payload.name
            team.updated_at = self._clock()
            team.revision += 1
            self._add_audit(
                audit_context,
                action="team.rename",
                target_id=team.id,
                change_summary={"old_name": old_name, "new_name": payload.name},
                now=team.updated_at,
            )
            try:
                await self._session.commit()
            except IntegrityError as exc:
                await self._session.rollback()
                raise self._conflict("TEAM_NAME_CONFLICT", "已有同名队伍。") from exc
        else:
            await self._session.rollback()
        return await self._team_response(team, actor_user_id=audit_context.actor.user.id)

    @staticmethod
    def _application_response(record: TeamApplicationRecord) -> TeamApplicationResponse:
        return TeamApplicationResponse(
            id=record.application.id,
            team_id=record.team.id,
            team_name=record.team.name,
            applicant_user_id=record.applicant.id,
            applicant_full_name=record.applicant.full_name,
            status=cast(
                Literal["pending", "accepted", "declined", "cancelled"], record.application.status
            ),
            created_at=record.application.created_at,
            responded_at=record.application.responded_at,
        )

    async def my_applications(
        self, *, context: AuthenticatedContext
    ) -> TeamApplicationListResponse:
        self._require_student(context)
        if not (await self._team_settings_record()).is_team_open:
            return TeamApplicationListResponse(items=[])
        records = await self._teams.applications_for_applicant(context.user.id)
        return TeamApplicationListResponse(
            items=[self._application_response(record) for record in records]
        )

    async def captain_applications(
        self, team_id: UUID, *, context: AuthenticatedContext
    ) -> TeamApplicationListResponse:
        self._require_student(context)
        if not (await self._team_settings_record()).is_team_open:
            return TeamApplicationListResponse(items=[])
        await self._mutable_team_for_captain(team_id, context.user.id)
        records = await self._teams.applications_for_team(team_id)
        return TeamApplicationListResponse(
            items=[self._application_response(record) for record in records]
        )

    async def apply_to_team(
        self, team_id: UUID, *, audit_context: TeamAuditContext
    ) -> TeamApplicationResponse:
        self._require_student(audit_context.actor)
        await self._require_team_open()
        await self._composition.lock()
        team = await self._teams.get_team(team_id, for_update=True)
        if team is None or team.status != "forming":
            await self._session.rollback()
            raise self._not_found()
        current = await self._teams.team_for_user(audit_context.actor.user.id, for_update=True)
        if current is not None and current.id == team.id:
            await self._session.rollback()
            raise self._conflict("ALREADY_IN_TEAM", "已经是该队伍成员。")
        if current is not None and current.captain_user_id == audit_context.actor.user.id:
            await self._session.rollback()
            raise self._conflict("CAPTAIN_TRANSFER_REQUIRED", "请先转让当前队伍的队长身份。")
        existing = await self._teams.pending_application(team.id, audit_context.actor.user.id)
        if existing is not None:
            return TeamApplicationResponse(
                id=existing.id,
                team_id=team.id,
                team_name=team.name,
                applicant_user_id=audit_context.actor.user.id,
                applicant_full_name=audit_context.actor.user.full_name,
                status="pending",
                created_at=existing.created_at,
                responded_at=None,
            )
        if await self._teams.member_count(team.id) >= effective_team_capacity(team.max_members):
            await self._session.rollback()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        await self._composition.require_add(team.id, audit_context.actor.user.id)
        captain = (
            await self._users.get_by_id(team.captain_user_id) if team.captain_user_id else None
        )
        if captain is None or captain.status != "active":
            await self._session.rollback()
            raise self._conflict("TEAM_CAPTAIN_UNAVAILABLE", "目标队伍暂无可处理申请的队长。")
        now = self._clock()
        application = TeamApplication(
            id=uuid7(),
            team_id=team.id,
            applicant_user_id=audit_context.actor.user.id,
            status="pending",
            responded_at=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._teams.add_application(application)
        self._outbox.add(
            OutboxJob(
                id=uuid7(),
                job_type="team_application_email",
                event_key=f"team_application:{application.id}",
                payload={
                    "recipient": captain.email,
                    "full_name": captain.full_name,
                    "applicant_user_id": str(audit_context.actor.user.id),
                    "applicant_name": audit_context.actor.user.full_name,
                    "team_name": team.name,
                    "target_url": "/competitions",
                },
                secret_payload_ciphertext=None,
                status="pending",
                available_at=now,
                attempt_count=0,
                max_attempts=8,
                locked_by=None,
                locked_at=None,
                last_error_code=None,
                last_error_summary=None,
                created_at=now,
                sent_at=None,
            )
        )
        self._add_audit(
            audit_context,
            action="team.application_create",
            target_id=application.id,
            target_type="team_application",
            change_summary={"team_id": str(team.id)},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            existing = await self._teams.pending_application(team_id, audit_context.actor.user.id)
            if existing is not None:
                return TeamApplicationResponse(
                    id=existing.id,
                    team_id=team.id,
                    team_name=team.name,
                    applicant_user_id=audit_context.actor.user.id,
                    applicant_full_name=audit_context.actor.user.full_name,
                    status="pending",
                    created_at=existing.created_at,
                    responded_at=None,
                )
            raise self._conflict(
                "TEAM_APPLICATION_CONFLICT", "申请状态发生变化，请刷新后重试。"
            ) from exc
        return TeamApplicationResponse(
            id=application.id,
            team_id=team.id,
            team_name=team.name,
            applicant_user_id=audit_context.actor.user.id,
            applicant_full_name=audit_context.actor.user.full_name,
            status="pending",
            created_at=now,
            responded_at=None,
        )

    async def respond_to_application(
        self, team_id: UUID, application_id: UUID, *, accept: bool, audit_context: TeamAuditContext
    ) -> TeamResponse | OperationResponse:
        self._require_student(audit_context.actor)
        await self._require_team_open()
        if accept:
            await self._composition.lock()
        team = await self._mutable_team_for_captain(team_id, audit_context.actor.user.id)
        application = await self._teams.application_for_team(
            application_id, team.id, for_update=True
        )
        if application is None:
            await self._session.rollback()
            raise self._not_found()
        if application.status != "pending":
            await self._session.rollback()
            raise self._conflict("APPLICATION_NOT_PENDING", "该申请已经处理。")
        now = self._clock()
        if accept:
            applicant = await self._users.get_by_id(application.applicant_user_id, for_update=True)
            if (
                applicant is None
                or applicant.role not in {"student", "admin"}
                or applicant.status != "active"
            ):
                await self._session.rollback()
                raise self._conflict("APPLICATION_UNAVAILABLE", "申请人已无法加入队伍。")
            current = await self._teams.team_for_user(applicant.id, for_update=True)
            if current is not None and current.id == team.id:
                await self._session.rollback()
                raise self._conflict("ALREADY_IN_TEAM", "申请人已在当前队伍。")
            if current is not None and current.captain_user_id == applicant.id:
                await self._session.rollback()
                raise self._conflict("CAPTAIN_TRANSFER_REQUIRED", "申请人须先转让原队队长身份。")
            if await self._teams.member_count(team.id) >= effective_team_capacity(team.max_members):
                await self._session.rollback()
                raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
            await self._composition.require_add(team.id, applicant.id)
            if current is not None:
                old_member = await self._teams.current_member(
                    current.id, applicant.id, for_update=True
                )
                if old_member is None:
                    await self._session.rollback()
                    raise self._conflict("TEAM_MEMBERSHIP_CONFLICT", "原队伍成员状态已变化。")
                old_member.left_at = now
                current.updated_at = now
                current.revision += 1
                await self._session.flush()
            self._teams.add_member(
                TeamMember(
                    id=uuid7(),
                    team_id=team.id,
                    user_id=applicant.id,
                    joined_at=now,
                    left_at=None,
                    added_by_admin=False,
                    admin_reason=None,
                )
            )
            await self._teams.cancel_pending_for_invitee(applicant.id, responded_at=now)
            await self._teams.cancel_pending_applications_for_applicant(
                applicant.id, responded_at=now, exclude_id=application.id
            )
            team.updated_at = now
            team.revision += 1
        application.status = "accepted" if accept else "declined"
        application.responded_at = now
        application.updated_at = now
        application.revision += 1
        self._add_audit(
            audit_context,
            action="team.application_accept" if accept else "team.application_decline",
            target_id=application.id,
            target_type="team_application",
            change_summary={
                "team_id": str(team.id),
                "switched_from_team_id": (
                    str(current.id) if accept and current is not None else None
                ),
            },
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._conflict(
                "TEAM_MEMBERSHIP_CONFLICT", "组队状态发生变化，请刷新后重试。"
            ) from exc
        if accept:
            return await self._team_response(team, actor_user_id=audit_context.actor.user.id)
        return OperationResponse()

    async def rotate_invite_code(
        self,
        team_id: UUID,
        *,
        audit_context: TeamAuditContext,
    ) -> InviteCodeRotatedResponse:
        self._require_student(audit_context.actor)
        await self._require_team_open()
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
        await self._require_team_open()
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
        await self._require_team_open()
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
        await self._require_team_open()
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
        await self._teams.cancel_pending_applications_for_team(team.id, responded_at=now)
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
                    max_members=effective_team_capacity(record.team.max_members),
                )
                for record in records
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def admin_team_settings(self, *, context: AuthenticatedContext) -> TeamSettingsResponse:
        self._require_admin(context)
        return self._settings_response(await self._team_settings_record())

    async def update_admin_team_settings(
        self,
        payload: TeamSettingsUpdateRequest,
        *,
        audit_context: TeamAuditContext,
    ) -> TeamSettingsResponse:
        self._require_admin(audit_context.actor)
        settings = await self._team_settings_record(for_update=True)
        if payload.revision != settings.revision:
            await self._session.rollback()
            raise self._conflict("REVISION_CONFLICT", "组队开放状态已发生变化，请刷新后重试。")
        changes: dict[str, object] = {
            field: getattr(payload, field)
            for field in ("is_team_open", "is_direction_change_open")
            if field in payload.model_fields_set
            and getattr(payload, field) != getattr(settings, field)
        }
        if not changes:
            response = self._settings_response(settings)
            await self._session.rollback()
            return response
        now = self._clock()
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_at = now
        settings.revision += 1
        self._add_audit(
            audit_context,
            action="team.settings_update",
            target_id=audit_context.actor.user.id,
            target_type="team_settings",
            change_summary=changes,
            now=now,
        )
        await self._session.commit()
        return self._settings_response(settings)

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
        await self._composition.lock()
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
        if await self._teams.member_count(team.id) >= effective_team_capacity(team.max_members):
            await self._session.rollback()
            raise self._conflict("TEAM_FULL", "目标队伍人数已满。")
        now = self._clock()
        await self._composition.require_add(team.id, user.id)
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
