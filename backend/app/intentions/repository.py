from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intentions.models import (
    IntentionOption,
    IntentionResponse,
    IntentionResponseOption,
    IntentionSurvey,
)
from app.users.models import User


@dataclass(frozen=True, slots=True)
class SurveyListRecord:
    survey: IntentionSurvey
    option_count: int
    responded_count: int
    has_response: bool


@dataclass(frozen=True, slots=True)
class SurveyOptionCount:
    option: IntentionOption
    response_count: int


class IntentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_survey(self, survey: IntentionSurvey) -> None:
        self._session.add(survey)

    def add_option(self, option: IntentionOption) -> None:
        self._session.add(option)

    def add_response(self, response: IntentionResponse) -> None:
        self._session.add(response)

    def add_response_option(self, option: IntentionResponseOption) -> None:
        self._session.add(option)

    async def get_survey(
        self, survey_id: UUID, *, for_update: bool = False
    ) -> IntentionSurvey | None:
        statement = select(IntentionSurvey).where(IntentionSurvey.id == survey_id)
        if for_update:
            statement = statement.with_for_update()
        result: IntentionSurvey | None = await self._session.scalar(statement)
        return result

    async def list_surveys(
        self,
        *,
        student_user_id: UUID | None = None,
        open_only: bool = False,
    ) -> list[SurveyListRecord]:
        option_count = (
            select(IntentionOption.survey_id.label("survey_id"), func.count().label("value"))
            .group_by(IntentionOption.survey_id)
            .subquery()
        )
        response_count = (
            select(IntentionResponse.survey_id.label("survey_id"), func.count().label("value"))
            .group_by(IntentionResponse.survey_id)
            .subquery()
        )
        filters = []
        if open_only:
            filters.append(IntentionSurvey.status == "open")
        rows = (
            await self._session.execute(
                select(
                    IntentionSurvey,
                    func.coalesce(option_count.c.value, 0),
                    func.coalesce(response_count.c.value, 0),
                )
                .outerjoin(option_count, option_count.c.survey_id == IntentionSurvey.id)
                .outerjoin(response_count, response_count.c.survey_id == IntentionSurvey.id)
                .where(*filters)
                .order_by(IntentionSurvey.created_at.desc(), IntentionSurvey.id.desc())
            )
        ).all()
        response_ids: set[UUID] = set()
        if student_user_id is not None and rows:
            response_ids = set(
                await self._session.scalars(
                    select(IntentionResponse.survey_id).where(
                        IntentionResponse.user_id == student_user_id,
                        IntentionResponse.survey_id.in_([row[0].id for row in rows]),
                    )
                )
            )
        return [
            SurveyListRecord(
                survey=row[0],
                option_count=int(row[1]),
                responded_count=int(row[2]),
                has_response=row[0].id in response_ids,
            )
            for row in rows
        ]

    async def options(self, survey_id: UUID) -> list[IntentionOption]:
        return list(
            (
                await self._session.scalars(
                    select(IntentionOption)
                    .where(IntentionOption.survey_id == survey_id)
                    .order_by(IntentionOption.display_order, IntentionOption.id)
                )
            ).all()
        )

    async def get_response(
        self, survey_id: UUID, user_id: UUID, *, for_update: bool = False
    ) -> IntentionResponse | None:
        statement = select(IntentionResponse).where(
            IntentionResponse.survey_id == survey_id,
            IntentionResponse.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: IntentionResponse | None = await self._session.scalar(statement)
        return result

    async def response_options(self, response_id: UUID) -> list[IntentionResponseOption]:
        return list(
            (
                await self._session.scalars(
                    select(IntentionResponseOption).where(
                        IntentionResponseOption.response_id == response_id
                    )
                )
            ).all()
        )

    async def active_student_count(self) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "student", User.status == "active")
            )
            or 0
        )

    async def option_counts(self, survey_id: UUID) -> list[SurveyOptionCount]:
        rows = (
            await self._session.execute(
                select(IntentionOption, func.count(IntentionResponseOption.response_id))
                .outerjoin(
                    IntentionResponseOption,
                    IntentionResponseOption.option_id == IntentionOption.id,
                )
                .where(IntentionOption.survey_id == survey_id)
                .group_by(IntentionOption.id)
                .order_by(IntentionOption.display_order, IntentionOption.id)
            )
        ).all()
        return [SurveyOptionCount(option=row[0], response_count=int(row[1])) for row in rows]

    async def responded_count(self, survey_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(IntentionResponse)
                .where(IntentionResponse.survey_id == survey_id)
            )
            or 0
        )
