from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.teams.composition import (
    TeamCompositionService,
    composition_for,
    direction_category,
    effective_team_capacity,
    fits_composition,
)
from app.teams.schemas import TeamSettingsUpdateRequest
from app.users.direction_service import UserDirectionService
from app.users.schemas import SelfDirectionRequest
from app.users.service import AuditContext


@pytest.mark.parametrize(
    ("names", "fits", "complete"),
    [
        (["机械"], True, False),
        (["机械", "嵌入式控制", "嵌入式-硬件", "算法"], True, True),
        (["机械", "机械组", "嵌入式控制", "硬件", "算法"], True, True),
        (["机械", "机械", "嵌入式-控制", "嵌入式硬件组", "算法组"], True, True),
        (["机械", "机械", "硬件", "算法组"], True, False),
        (["机械", "机械", "嵌入式控制", "硬件", "硬件组", "算法"], False, False),
        (["机械", "机械", "机械"], False, False),
        (["算法", "算法"], False, False),
        (["嵌入式控制", "嵌入式-控制"], False, False),
        (["嵌入式硬件", "嵌入式-硬件"], False, False),
        (["机械", "硬件", "算法"], True, False),
        ([None], False, False),
        (["不明技术组"], False, False),
        (["非机械"], False, False),
    ],
)
def test_composition_limits_and_completion(
    names: list[str | None], fits: bool, complete: bool
) -> None:
    assert fits_composition(names) is fits
    assert composition_for(names).is_complete is complete


@pytest.mark.parametrize("name", ["嵌入式控制", "嵌入式控制组", "嵌入式-控制", "嵌入式-控制组"])
def test_embedded_control_names_share_quota(name: str) -> None:
    assert direction_category(name) == "embedded_control"


@pytest.mark.parametrize(
    "name", ["嵌入式硬件", "嵌入式硬件组", "嵌入式-硬件", "嵌入式-硬件组", "硬件", "硬件组"]
)
def test_embedded_hardware_names_share_quota(name: str) -> None:
    assert direction_category(name) == "embedded_hardware"


@pytest.mark.parametrize("name", ["嵌入式", "嵌入式组", "嵌入式控制/硬件"])
def test_unspecified_embedded_directions_are_not_assigned_a_slot(name: str) -> None:
    assert direction_category(name) == "unassigned"
    assert not fits_composition(["机械", name, "算法"])


def test_composition_response_separates_control_and_hardware() -> None:
    result = composition_for(["机械", "嵌入式-控制", "嵌入式-硬件", "算法"])
    assert result.embedded_control == 1
    assert result.embedded_hardware == 1
    assert result.is_complete


def test_effective_capacity_preserves_five_member_team_and_lower_legacy_limits() -> None:
    assert effective_team_capacity(20) == 5
    assert effective_team_capacity(5) == 5
    assert effective_team_capacity(4) == 4


def composition_service(
    names: list[str | None], incoming: str | None
) -> tuple[TeamCompositionService, Any, Any]:
    session = AsyncMock(spec=AsyncSession)
    service = TeamCompositionService(session)
    user = SimpleNamespace(id=uuid4(), direction_id=uuid4())
    service._users = cast(
        Any,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=user),
            get_direction=AsyncMock(return_value=SimpleNamespace(name=incoming)),
        ),
    )
    service._teams = cast(
        Any,
        SimpleNamespace(
            current_members=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        user=SimpleNamespace(id=uuid4(), direction_id=uuid4()), direction_name=name
                    )
                    for name in names
                ]
            )
        ),
    )
    return service, session, user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("names", "incoming", "code"),
    [
        (["机械", "机械"], "机械", "TEAM_COMPOSITION_CONFLICT"),
        (["算法"], "算法", "TEAM_COMPOSITION_CONFLICT"),
        (["嵌入式控制"], "嵌入式-控制", "TEAM_COMPOSITION_CONFLICT"),
        (["嵌入式硬件"], "嵌入式-硬件", "TEAM_COMPOSITION_CONFLICT"),
        ([], None, "TEAM_DIRECTION_REQUIRED"),
        ([], "其他", "TEAM_DIRECTION_REQUIRED"),
    ],
)
async def test_add_rejects_over_quota_or_unknown_direction(
    names: list[str | None], incoming: str | None, code: str
) -> None:
    service, session, user = composition_service(names, incoming)
    with pytest.raises(ApplicationError) as caught:
        await service.require_add(uuid4(), user.id)
    assert caught.value.code == code
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_accepts_second_mechanical_member() -> None:
    service, session, user = composition_service(
        ["机械", "嵌入式控制", "嵌入式-硬件", "算法"], "机械"
    )
    await service.require_add(uuid4(), user.id)
    session.rollback.assert_not_awaited()
    cast(AsyncMock, service._users.get_by_id).assert_any_await(user.id, for_update=True)


@pytest.mark.asyncio
async def test_batch_direction_swap_uses_final_state() -> None:
    service, session, _user = composition_service(
        ["机械", "机械", "嵌入式控制", "嵌入式-硬件", "算法"], "机械"
    )
    records = await service._teams.current_members(uuid4())
    mechanical, algorithm = records[0].user.id, records[4].user.id
    mechanical_direction, algorithm_direction = uuid4(), uuid4()
    directions = {mechanical_direction: "机械", algorithm_direction: "算法"}
    cast(Any, service._users).get_direction = AsyncMock(
        side_effect=lambda identity: SimpleNamespace(name=directions[identity])
    )
    cast(Any, service._teams).team_for_user = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    await service.validate_direction_changes(
        {mechanical: algorithm_direction, algorithm: mechanical_direction}
    )
    session.rollback.assert_not_awaited()
    with pytest.raises(ApplicationError, match="名额"):
        await service.validate_direction_changes({mechanical: algorithm_direction})


@pytest.mark.asyncio
async def test_direction_rename_cannot_bypass_composition() -> None:
    service, _session, _user = composition_service(["机械", "算法"], "机械")
    members = await service._teams.current_members(uuid4())
    cast(Any, service._teams).forming_teams_for_update = AsyncMock(
        return_value=[SimpleNamespace(id=uuid4())]
    )
    direction_id = members[0].user.direction_id
    assert direction_id is not None
    with pytest.raises(ApplicationError) as caught:
        await service.validate_direction_rename(direction_id, "算法")
    assert caught.value.code == "TEAM_COMPOSITION_CONFLICT"


@pytest.mark.asyncio
async def test_direction_rename_cannot_replace_control_with_second_hardware() -> None:
    service, _session, _user = composition_service(
        ["机械", "嵌入式-控制", "嵌入式-硬件", "算法"], "机械"
    )
    members = await service._teams.current_members(uuid4())
    cast(Any, service._teams).forming_teams_for_update = AsyncMock(
        return_value=[SimpleNamespace(id=uuid4())]
    )
    direction_id = members[1].user.direction_id
    assert direction_id is not None
    with pytest.raises(ApplicationError) as caught:
        await service.validate_direction_rename(direction_id, "嵌入式硬件")
    assert caught.value.code == "TEAM_COMPOSITION_CONFLICT"


@pytest.mark.parametrize(
    "payload",
    [
        {"revision": 1},
        {"revision": 1, "is_team_open": None},
        {"revision": 1, "is_direction_change_open": None},
    ],
)
def test_switch_patch_requires_non_null_explicit_switch(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TeamSettingsUpdateRequest.model_validate(payload)


def test_self_direction_payload_forbids_other_user_fields() -> None:
    with pytest.raises(ValidationError):
        SelfDirectionRequest.model_validate(
            {"direction_id": str(uuid4()), "revision": 1, "role": "admin"}
        )


def direction_service(
    *, opened: bool = True, role: str = "student"
) -> tuple[UserDirectionService, Any, Any, AuditContext, UUID]:
    session = AsyncMock(spec=AsyncSession)
    service = UserDirectionService(session, Settings(app_env="test"))
    user = SimpleNamespace(id=uuid4(), role=role, status="active", direction_id=uuid4(), revision=1)
    direction_id = uuid4()
    direction = SimpleNamespace(id=direction_id, code="mechanical", name="机械", is_active=True)
    service._teams = cast(
        Any,
        SimpleNamespace(
            team_settings=AsyncMock(return_value=SimpleNamespace(is_direction_change_open=opened))
        ),
    )
    service._users = cast(
        Any,
        SimpleNamespace(
            get_by_id=AsyncMock(return_value=user),
            get_direction=AsyncMock(return_value=direction),
            list_directions=AsyncMock(return_value=[direction]),
        ),
    )
    service._composition = cast(Any, SimpleNamespace(validate_direction_changes=AsyncMock()))
    service._assignments = cast(
        Any,
        SimpleNamespace(add_historical_assignment_audiences_for_student=AsyncMock(return_value=2)),
    )
    service._audit = cast(Any, SimpleNamespace(add=Mock()))
    service._auth = cast(Any, SimpleNamespace(user_response=AsyncMock(return_value=user)))
    context = cast(
        AuthenticatedContext, SimpleNamespace(user=user, is_admin=False, effective_role="student")
    )
    audit = AuditContext(actor=context, request_id="direction-test", ip_prefix="127.0.0.0/24")
    return service, session, user, audit, direction_id


@pytest.mark.asyncio
async def test_student_changes_direction_and_appends_history_in_same_transaction() -> None:
    service, session, user, audit, direction_id = direction_service()
    previous = user.direction_id
    await service.change(SelfDirectionRequest(direction_id=direction_id, revision=1), audit=audit)
    assert user.direction_id == direction_id
    assert user.revision == 2
    cast(AsyncMock, service._composition.validate_direction_changes).assert_awaited_once_with(
        {user.id: direction_id}
    )
    history = cast(AsyncMock, service._assignments.add_historical_assignment_audiences_for_student)
    assert history.await_args is not None
    assert history.await_args.kwargs["user"] is user
    assert history.await_args.kwargs["created_at"].tzinfo is not None
    event = cast(Mock, service._audit.add).call_args.args[0]
    assert event.change_summary == {
        "direction_id": {"from": str(previous), "to": str(direction_id)},
        "historical_assignment_audience_added_count": 2,
    }
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "code"),
    [
        ("closed", "DIRECTION_CHANGE_CLOSED"),
        ("admin_student_view", "FORBIDDEN"),
        ("stale", "REVISION_CONFLICT"),
        ("inactive_direction", "INVALID_DIRECTION"),
        ("missing_direction", "INVALID_DIRECTION"),
        ("quota", "TEAM_COMPOSITION_CONFLICT"),
    ],
)
async def test_direction_change_rejections_do_not_write(failure: str, code: str) -> None:
    service, session, user, audit, direction_id = direction_service(
        opened=failure != "closed", role="admin" if failure == "admin_student_view" else "student"
    )
    previous = user.direction_id
    if failure == "inactive_direction":
        cast(AsyncMock, service._users.get_direction).return_value.is_active = False
    if failure == "missing_direction":
        cast(AsyncMock, service._users.get_direction).return_value = None
    if failure == "quota":
        cast(
            AsyncMock, service._composition.validate_direction_changes
        ).side_effect = ApplicationError(status_code=409, code=code, message="名额冲突")
    with pytest.raises(ApplicationError) as caught:
        await service.change(
            SelfDirectionRequest(
                direction_id=direction_id, revision=2 if failure == "stale" else 1
            ),
            audit=audit,
        )
    assert caught.value.code == code
    assert user.direction_id == previous
    assert user.revision == 1
    session.commit.assert_not_awaited()
    cast(Mock, service._audit.add).assert_not_called()
    cast(
        AsyncMock, service._assignments.add_historical_assignment_audiences_for_student
    ).assert_not_awaited()


@pytest.mark.asyncio
async def test_unchanged_direction_does_not_add_audience_or_audit() -> None:
    service, session, user, audit, direction_id = direction_service()
    user.direction_id = direction_id
    await service.change(SelfDirectionRequest(direction_id=direction_id, revision=1), audit=audit)
    assert user.revision == 1
    session.commit.assert_awaited_once()
    cast(Mock, service._audit.add).assert_not_called()
    cast(
        AsyncMock, service._assignments.add_historical_assignment_audiences_for_student
    ).assert_not_awaited()


@pytest.mark.asyncio
async def test_direction_options_exclude_inactive_and_private_fields() -> None:
    service, _session, _user, audit, _direction_id = direction_service(opened=False)
    cast(AsyncMock, service._users.list_directions).return_value.append(
        SimpleNamespace(is_active=False)
    )
    result = await service.options(audit.actor)
    assert result.is_direction_change_open is False
    assert len(result.directions) == 1
    assert set(result.directions[0].model_dump()) == {"id", "code", "name"}
