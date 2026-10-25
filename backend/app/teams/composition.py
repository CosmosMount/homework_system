from collections.abc import Iterable, Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.teams.repository import TeamRepository
from app.teams.schemas import TeamCompositionResponse
from app.users.repository import UserRepository

COMPOSITION_RULE = "每队需要机械 1～2 人、嵌入式控制 1 人、嵌入式硬件 1 人、算法 1 人。"
MAX_COMPOSITION_MEMBERS = 5


def effective_team_capacity(max_members: int) -> int:
    return min(max_members, MAX_COMPOSITION_MEMBERS)


def direction_category(name: str | None) -> str:
    normalized = (name or "").strip().removesuffix("组")
    if normalized == "机械":
        return "mechanical"
    if normalized in {"嵌入式控制", "嵌入式-控制"}:
        return "embedded_control"
    if normalized in {"嵌入式硬件", "嵌入式-硬件", "硬件"}:
        return "embedded_hardware"
    if normalized == "算法":
        return "algorithm"
    return "unassigned"


def composition_for(names: Iterable[str | None]) -> TeamCompositionResponse:
    counts = {
        "mechanical": 0,
        "embedded_control": 0,
        "embedded_hardware": 0,
        "algorithm": 0,
        "unassigned": 0,
    }
    for name in names:
        counts[direction_category(name)] += 1
    return TeamCompositionResponse(
        **counts,
        is_complete=(
            1 <= counts["mechanical"] <= 2
            and counts["embedded_control"] == 1
            and counts["embedded_hardware"] == 1
            and counts["algorithm"] == 1
            and counts["unassigned"] == 0
        ),
    )


def fits_composition(names: Iterable[str | None]) -> bool:
    counts = composition_for(names)
    return (
        counts.mechanical <= 2
        and counts.embedded_control <= 1
        and counts.embedded_hardware <= 1
        and counts.algorithm <= 1
        and counts.unassigned == 0
    )


class TeamCompositionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._teams = TeamRepository(session)
        self._users = UserRepository(session)

    async def lock(self) -> None:
        if await self._teams.team_settings(for_update=True) is None:
            raise RuntimeError("team_settings singleton is missing")

    async def direction_name(self, direction_id: UUID | None) -> str | None:
        direction = await self._users.get_direction(direction_id) if direction_id else None
        return direction.name if direction is not None else None

    async def can_add(self, team_id: UUID | None, user_id: UUID) -> bool:
        user = await self._users.get_by_id(user_id)
        if user is None:
            return False
        name = await self.direction_name(user.direction_id)
        names = (
            [record.direction_name for record in await self._teams.current_members(team_id)]
            if team_id is not None
            else []
        )
        return fits_composition([*names, name])

    async def require_add(self, team_id: UUID | None, user_id: UUID) -> None:
        user = await self._users.get_by_id(user_id, for_update=True)
        name = await self.direction_name(user.direction_id) if user else None
        if direction_category(name) == "unassigned":
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="TEAM_DIRECTION_REQUIRED",
                message="请先在个人资料中选择机械、嵌入式控制、嵌入式硬件或算法技术方向。",
            )
        if not await self.can_add(team_id, user_id):
            await self._reject()

    async def _reject(self) -> None:
        await self._session.rollback()
        raise ApplicationError(
            status_code=409,
            code="TEAM_COMPOSITION_CONFLICT",
            message="操作后队伍技术方向名额不符合要求。" + COMPOSITION_RULE,
        )

    async def validate_direction_changes(self, changes: Mapping[UUID, UUID | None]) -> None:
        teams = {}
        for user_id in sorted(changes):
            team = await self._teams.team_for_user(user_id, for_update=True)
            if team is not None:
                teams[team.id] = team
        for team_id in sorted(teams):
            names = []
            for record in await self._teams.current_members(team_id):
                names.append(
                    await self.direction_name(changes[record.user.id])
                    if record.user.id in changes
                    else record.direction_name
                )
            if not fits_composition(names):
                await self._reject()

    async def validate_direction_rename(self, direction_id: UUID, name: str) -> None:
        for team in await self._teams.forming_teams_for_update():
            members = await self._teams.current_members(team.id)
            if not any(record.user.direction_id == direction_id for record in members):
                continue
            if not fits_composition(
                name if record.user.direction_id == direction_id else record.direction_name
                for record in members
            ):
                await self._reject()
