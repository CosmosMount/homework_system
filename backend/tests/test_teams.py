from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import Table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.auth.repository import AuthRepository
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.teams.models import Team, TeamInvitation, TeamMember, TeamProfile, TeamSettings
from app.teams.repository import TeamListRecord, TeamProfileRecord, TeamRepository
from app.teams.schemas import (
    TeamInvitationCreateRequest,
    TeamProfileUpsertRequest,
    TeamResponse,
    TeamSettingsUpdateRequest,
)
from app.teams.service import TeamAuditContext, TeamService
from app.users.models import User
from app.users.repository import UserRepository


def make_context(*, role: str = "student") -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(
                id=uuid4(),
                role=role,
                full_name="测试同学",
                direction_id=None,
                status="active",
            ),
            effective_role=role,
            is_admin=role == "admin",
            session=SimpleNamespace(student_view=False),
        ),
    )


def make_audit_context(*, role: str = "student") -> TeamAuditContext:
    return TeamAuditContext(
        actor=make_context(role=role),
        request_id="standalone-team-regression",
        ip_prefix="127.0.0.0/24",
    )


def make_team(
    name: str,
    *,
    captain_user_id: object | None = None,
    created_at: datetime | None = None,
) -> Team:
    now = created_at or datetime.now(UTC)
    captain_id = captain_user_id if captain_user_id is not None else uuid4()
    return Team(
        id=uuid4(),
        name=name,
        status="forming",
        captain_user_id=captain_id,
        invite_code_hash="a" * 64,
        invite_code_rotated_at=now,
        max_members=5,
        dissolved_at=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_team_settings(now: datetime, *, is_team_open: bool) -> TeamSettings:
    return TeamSettings(
        id=True,
        is_team_open=is_team_open,
        created_at=now,
        updated_at=now,
        revision=1,
    )


def make_service(now: datetime) -> tuple[TeamService, AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    service = TeamService(
        cast(AsyncSession, session),
        Settings(app_env="test"),
        clock=lambda: now,
    )
    service._audit = cast(AuditRepository, SimpleNamespace(add=Mock()))
    service._team_settings = cast(
        TeamRepository,
        SimpleNamespace(
            team_settings=AsyncMock(return_value=make_team_settings(now, is_team_open=True))
        ),
    )
    return service, session


def configure_invite_attempts(service: TeamService) -> None:
    service._auth = cast(
        AuthRepository,
        SimpleNamespace(
            count_security_events=AsyncMock(return_value=0),
            add_security_event=Mock(),
        ),
    )


def test_team_models_have_no_competition_dependency_and_enforce_global_membership() -> None:
    assert "competition_id" not in Team.__table__.columns
    assert "competition_id" not in TeamMember.__table__.columns
    member_table = cast(Table, TeamMember.__table__)
    team_table = cast(Table, Team.__table__)
    current_user_index = next(
        index for index in member_table.indexes if index.name == "uq_team_members_current_user"
    )
    assert current_user_index.unique is True
    assert str(current_user_index.dialect_options["postgresql"]["where"])
    team_indexes = {index.name for index in team_table.indexes}
    assert "uq_teams_active_name" in team_indexes


@pytest.mark.asyncio
async def test_closed_team_enrollment_blocks_mutation_but_not_profile_editing() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    service, session = make_service(now)
    service._team_settings = cast(
        TeamRepository,
        SimpleNamespace(
            team_settings=AsyncMock(return_value=make_team_settings(now, is_team_open=False))
        ),
    )
    profiles: list[TeamProfile] = []

    async def profile_for_user(_user_id: object, *, for_update: bool = False) -> TeamProfile | None:
        del for_update
        return profiles[0] if profiles else None

    def add_profile(profile: TeamProfile) -> None:
        profiles.append(profile)

    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            profile_for_user=profile_for_user,
            add_profile=add_profile,
        ),
    )

    profile = await service.upsert_profile(
        TeamProfileUpsertRequest(introduction="仍可完善简介"),
        audit_context=audit_context,
    )
    assert profile.introduction == "仍可完善简介"

    with pytest.raises(ApplicationError) as captured:
        await service.create_team("尚未开放", audit_context=audit_context)

    assert captured.value.code == "TEAM_REGISTRATION_CLOSED"
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_admin_can_update_team_opening_with_revision_and_audit() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context(role="admin")
    service, session = make_service(now)
    settings = make_team_settings(now, is_team_open=False)
    service._team_settings = cast(
        TeamRepository,
        SimpleNamespace(team_settings=AsyncMock(return_value=settings)),
    )

    result = await service.update_admin_team_settings(
        TeamSettingsUpdateRequest(is_team_open=True, revision=1),
        audit_context=audit_context,
    )

    assert result.is_team_open is True
    assert result.revision == 2
    audit = cast(Mock, service._audit.add).call_args.args[0]
    assert audit.action == "team.settings_update"
    assert audit.change_summary == {"is_team_open": True}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_student_creates_team_without_competition_and_receives_invite_once() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    service, session = make_service(now)
    add_team = Mock()
    add_member = Mock()
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(return_value=None),
            add_team=add_team,
            add_member=add_member,
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.create_team("  原子队  ", audit_context=audit_context)

    team = cast(Team, add_team.call_args.args[0])
    member = cast(TeamMember, add_member.call_args.args[0])
    assert team.name == "原子队"
    assert team.max_members == 5
    assert member.team_id == team.id
    assert member.user_id == audit_context.actor.user.id
    assert result.invite_code
    assert result.invite_code not in team.invite_code_hash
    assert "competition_id" not in result.model_dump()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_team_rejects_existing_global_membership() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    existing = make_team("已有队伍", captain_user_id=audit_context.actor.user.id)
    service, session = make_service(now)
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(team_for_user=AsyncMock(return_value=existing)),
    )

    with pytest.raises(ApplicationError) as captured:
        await service.create_team("另一支队伍", audit_context=audit_context)

    assert captured.value.code == "ALREADY_IN_TEAM"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_team_directory_exposes_summary_only() -> None:
    now = datetime.now(UTC)
    context = make_context()
    team = make_team("公开队名", created_at=now)
    service, _session = make_service(now)
    list_public_teams = AsyncMock(return_value=([TeamListRecord(team=team, member_count=2)], 1))
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            list_public_teams=list_public_teams,
            team_for_user=AsyncMock(return_value=None),
        ),
    )

    result = await service.public_teams(
        context=context,
        query="公开",
        page=1,
        page_size=20,
    )

    assert result.items[0].name == "公开队名"
    assert result.items[0].can_join is True
    assert "members" not in result.items[0].model_dump()
    assert "invite_code" not in result.items[0].model_dump()


@pytest.mark.asyncio
async def test_student_joins_team_without_registration_or_competition_window() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    team = make_team("第一队", created_at=now)
    service, session = make_service(now)
    configure_invite_attempts(service)
    add_member = Mock()
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(return_value=None),
            team_by_invite_hash=AsyncMock(return_value=team),
            member_count=AsyncMock(return_value=1),
            add_member=add_member,
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.join_team("join-code", audit_context=audit_context)

    member = cast(TeamMember, add_member.call_args.args[0])
    assert result.id == team.id
    assert member.user_id == audit_context.actor.user.id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_assign_joins_smallest_available_team() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    larger = make_team("三人队", created_at=now - timedelta(minutes=2))
    smaller = make_team("一人队", created_at=now - timedelta(minutes=1))
    counts = {larger.id: 3, smaller.id: 1}
    service, session = make_service(now)
    add_member = Mock()
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(return_value=None),
            forming_teams_for_update=AsyncMock(return_value=[larger, smaller]),
            member_count=AsyncMock(side_effect=lambda team_id: counts[team_id]),
            add_member=add_member,
            add_team=Mock(),
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.auto_assign(audit_context=audit_context)

    assert result.assignment == "joined"
    assert result.id == smaller.id
    assert cast(TeamMember, add_member.call_args.args[0]).team_id == smaller.id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_assign_rolls_back_global_membership_conflict() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    service, session = make_service(now)
    session.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(return_value=None),
            forming_teams_for_update=AsyncMock(return_value=[]),
            add_member=Mock(),
            add_team=Mock(),
        ),
    )

    with pytest.raises(ApplicationError) as captured:
        await service.auto_assign(audit_context=audit_context)

    assert captured.value.code == "TEAM_MEMBERSHIP_CONFLICT"
    session.rollback.assert_awaited_once()


def test_team_profile_and_invitation_models_enforce_privacy_boundaries() -> None:
    profile_table = cast(Table, TeamProfile.__table__)
    invitation_table = cast(Table, TeamInvitation.__table__)
    settings_table = cast(Table, TeamSettings.__table__)
    assert set(settings_table.columns.keys()) == {
        "id",
        "is_team_open",
        "created_at",
        "updated_at",
        "revision",
    }

    assert set(profile_table.columns.keys()) == {
        "user_id",
        "introduction",
        "created_at",
        "updated_at",
        "revision",
    }
    assert "email" not in invitation_table.columns
    assert "invite_code" not in invitation_table.columns
    pending_index = next(
        index
        for index in invitation_table.indexes
        if index.name == "uq_team_invitations_pending_team_invitee"
    )
    assert pending_index.unique is True
    assert str(pending_index.dialect_options["postgresql"]["where"])


@pytest.mark.asyncio
async def test_student_creates_team_profile_and_audit_omits_body() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    service, session = make_service(now)
    profiles: list[TeamProfile] = []

    async def profile_for_user(_user_id: object, *, for_update: bool = False) -> TeamProfile | None:
        del for_update
        return profiles[0] if profiles else None

    def add_profile(profile: TeamProfile) -> None:
        profiles.append(profile)

    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            profile_for_user=profile_for_user,
            add_profile=add_profile,
        ),
    )

    result = await service.upsert_profile(
        TeamProfileUpsertRequest(introduction="  擅长视觉，希望学习嵌入式。  "),
        audit_context=audit_context,
    )

    assert result.introduction == "擅长视觉，希望学习嵌入式。"
    assert profiles[0].revision == 1
    audit = cast(Mock, service._audit.add).call_args.args[0]
    assert audit.action == "team.profile_upsert"
    assert "introduction" not in audit.change_summary
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_directory_allows_any_team_member_to_invite_available_student() -> None:
    now = datetime.now(UTC)
    context = make_context()
    team = make_team("开放邀请队", captain_user_id=uuid4())
    target = SimpleNamespace(id=uuid4(), full_name="候选同学")
    profile = TeamProfile(
        user_id=target.id,
        introduction="熟悉机械设计。",
        created_at=now,
        updated_at=now,
        revision=1,
    )
    service, _session = make_service(now)
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            list_profiles=AsyncMock(
                return_value=(
                    [
                        TeamProfileRecord(
                            profile=profile,
                            user=cast(User, target),
                            direction_name="机械组",
                            team_id=None,
                        )
                    ],
                    1,
                )
            ),
            team_for_user=AsyncMock(return_value=team),
            list_active_directions=AsyncMock(return_value=[]),
            member_count=AsyncMock(return_value=2),
            pending_invitee_ids=AsyncMock(return_value=set()),
        ),
    )

    result = await service.profiles(
        context=context,
        query=None,
        direction_id=None,
        page=1,
        page_size=20,
    )

    assert result.items[0].can_invite is True
    assert result.items[0].direction_name == "机械组"
    assert "student_number" not in result.items[0].model_dump()


@pytest.mark.asyncio
async def test_non_captain_team_member_can_create_profile_invitation() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    team = make_team("开放邀请队", captain_user_id=uuid4())
    target_id = uuid4()
    target = SimpleNamespace(id=target_id, role="student", status="active")
    target_profile = TeamProfile(
        user_id=target_id,
        introduction="希望组队。",
        created_at=now,
        updated_at=now,
        revision=1,
    )
    service, session = make_service(now)
    add_invitation = Mock()
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(side_effect=[team, None]),
            member_count=AsyncMock(return_value=2),
            profile_for_user=AsyncMock(return_value=target_profile),
            pending_invitation=AsyncMock(return_value=None),
            add_invitation=add_invitation,
        ),
    )
    service._users = cast(
        UserRepository,
        SimpleNamespace(get_by_id=AsyncMock(return_value=target)),
    )

    result = await service.create_invitation(
        TeamInvitationCreateRequest(invitee_user_id=target_id),
        audit_context=audit_context,
    )

    invitation = cast(TeamInvitation, add_invitation.call_args.args[0])
    assert result.team_id == team.id
    assert invitation.invited_by_user_id == audit_context.actor.user.id
    assert team.captain_user_id != audit_context.actor.user.id
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_duplicate_invitation_returns_existing_pending_invitation() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    team = make_team("并发邀请队", captain_user_id=uuid4())
    target_id = uuid4()
    target = SimpleNamespace(id=target_id, role="student", status="active")
    inviter = SimpleNamespace(id=uuid4(), full_name="已有发送者")
    profile = TeamProfile(
        user_id=target_id,
        introduction="希望组队。",
        created_at=now,
        updated_at=now,
        revision=1,
    )
    existing = TeamInvitation(
        id=uuid4(),
        team_id=team.id,
        invitee_user_id=target_id,
        invited_by_user_id=inviter.id,
        status="pending",
        responded_at=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )
    service, session = make_service(now)
    session.commit.side_effect = IntegrityError("insert", {}, RuntimeError("unique"))
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            team_for_user=AsyncMock(side_effect=[team, None]),
            member_count=AsyncMock(return_value=2),
            profile_for_user=AsyncMock(return_value=profile),
            pending_invitation=AsyncMock(side_effect=[None, existing]),
            add_invitation=Mock(),
            get_team=AsyncMock(return_value=team),
        ),
    )
    service._users = cast(
        UserRepository,
        SimpleNamespace(get_by_id=AsyncMock(side_effect=[target, inviter])),
    )

    result = await service.create_invitation(
        TeamInvitationCreateRequest(invitee_user_id=target_id),
        audit_context=audit_context,
    )

    assert result.id == existing.id
    assert result.invited_by_full_name == "已有发送者"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_invitee_accepts_invitation_and_other_pending_invitations_are_cancelled() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    team = make_team("邀请队")
    invitation = TeamInvitation(
        id=uuid4(),
        team_id=team.id,
        invitee_user_id=audit_context.actor.user.id,
        invited_by_user_id=uuid4(),
        status="pending",
        responded_at=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )
    service, session = make_service(now)
    add_member = Mock()
    cancel_pending = AsyncMock()
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(
            invitation_for_invitee=AsyncMock(return_value=invitation),
            get_team=AsyncMock(return_value=team),
            team_for_user=AsyncMock(return_value=None),
            member_count=AsyncMock(return_value=2),
            add_member=add_member,
            cancel_pending_for_invitee=cancel_pending,
            current_members=AsyncMock(return_value=[]),
        ),
    )

    result = await service.respond_to_invitation(
        invitation.id,
        accept=True,
        audit_context=audit_context,
    )

    assert cast(TeamResponse, result).id == team.id
    assert invitation.status == "accepted"
    assert cast(TeamMember, add_member.call_args.args[0]).user_id == audit_context.actor.user.id
    cancel_pending.assert_awaited_once_with(
        audit_context.actor.user.id,
        responded_at=now,
        exclude_id=invitation.id,
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_invitee_declines_invitation_without_joining_team() -> None:
    now = datetime.now(UTC)
    audit_context = make_audit_context()
    invitation = TeamInvitation(
        id=uuid4(),
        team_id=uuid4(),
        invitee_user_id=audit_context.actor.user.id,
        invited_by_user_id=uuid4(),
        status="pending",
        responded_at=None,
        created_at=now,
        updated_at=now,
        revision=1,
    )
    service, session = make_service(now)
    service._teams = cast(
        TeamRepository,
        SimpleNamespace(invitation_for_invitee=AsyncMock(return_value=invitation)),
    )

    result = await service.respond_to_invitation(
        invitation.id,
        accept=False,
        audit_context=audit_context,
    )

    assert result.status == "ok"
    assert invitation.status == "declined"
    assert invitation.responded_at == now
    session.commit.assert_awaited_once()
