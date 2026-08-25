from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError, ErrorDetail
from app.users.models import User
from app.users.repository import UserRepository


class AudienceSelection(Protocol):
    @property
    def all_students(self) -> bool: ...

    @property
    def cohort_ids(self) -> Sequence[UUID]: ...

    @property
    def direction_ids(self) -> Sequence[UUID]: ...

    @property
    def match(self) -> str: ...


@dataclass(frozen=True, slots=True)
class AudienceRule:
    all_students: bool
    cohort_ids: tuple[UUID, ...]
    direction_ids: tuple[UUID, ...]
    match: str


def audience_matches(
    *,
    all_students: bool,
    match: str,
    cohort_ids: set[UUID],
    direction_ids: set[UUID],
    user_cohort_id: UUID | None,
    user_direction_id: UUID | None,
) -> bool:
    if all_students:
        return True
    cohort_matches = user_cohort_id is not None and user_cohort_id in cohort_ids
    direction_matches = user_direction_id is not None and user_direction_id in direction_ids
    if match == "union":
        return cohort_matches or direction_matches
    return (
        bool(cohort_ids or direction_ids)
        and (not cohort_ids or cohort_matches)
        and (not direction_ids or direction_matches)
    )


async def validate_audience(
    session: AsyncSession,
    audience: AudienceSelection,
    *,
    field_prefix: str = "audience",
) -> None:
    repository = UserRepository(session)
    cohort_ids = set(audience.cohort_ids)
    direction_ids = set(audience.direction_ids)
    if await repository.existing_cohort_ids(audience.cohort_ids) != cohort_ids:
        raise ApplicationError(
            status_code=400,
            code="VALIDATION_ERROR",
            message="受众届次不存在。",
            details=[
                ErrorDetail(
                    field=f"{field_prefix}.cohort_ids",
                    reason="RESOURCE_NOT_FOUND",
                )
            ],
        )
    if await repository.existing_direction_ids(audience.direction_ids) != direction_ids:
        raise ApplicationError(
            status_code=400,
            code="VALIDATION_ERROR",
            message="受众方向不存在。",
            details=[
                ErrorDetail(
                    field=f"{field_prefix}.direction_ids",
                    reason="RESOURCE_NOT_FOUND",
                )
            ],
        )


async def active_students_for_audience(
    session: AsyncSession,
    audience: AudienceSelection,
) -> list[User]:
    return await UserRepository(session).active_students_for_audience(
        all_students=audience.all_students,
        match=audience.match,
        cohort_ids=audience.cohort_ids,
        direction_ids=audience.direction_ids,
    )
