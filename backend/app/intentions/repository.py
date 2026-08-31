from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intentions.models import (
    IntentionOption,
    IntentionQuestion,
    IntentionResponse,
    IntentionResponseOption,
    IntentionSurvey,
)
from app.users.models import Direction, User


@dataclass(frozen=True, slots=True)
class SurveyListRecord:
    survey: IntentionSurvey
    question_count: int
    responded_count: int
    has_response: bool
    submissions_used: int = 0


@dataclass(frozen=True, slots=True)
class SurveyOptionCount:
    question: IntentionQuestion
    option: IntentionOption
    response_count: int


@dataclass(frozen=True, slots=True)
class SurveyRosterRecord:
    response: IntentionResponse
    user: User


class IntentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_survey(self, survey: IntentionSurvey) -> None:
        self._session.add(survey)

    def add_question(self, question: IntentionQuestion) -> None:
        self._session.add(question)

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
        question_count = (
            select(IntentionQuestion.survey_id.label("survey_id"), func.count().label("value"))
            .group_by(IntentionQuestion.survey_id)
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
                    func.coalesce(question_count.c.value, 0),
                    func.coalesce(response_count.c.value, 0),
                )
                .outerjoin(question_count, question_count.c.survey_id == IntentionSurvey.id)
                .outerjoin(response_count, response_count.c.survey_id == IntentionSurvey.id)
                .where(*filters)
                .order_by(IntentionSurvey.created_at.desc(), IntentionSurvey.id.desc())
            )
        ).all()
        student_responses: dict[UUID, int] = {}
        if student_user_id is not None and rows:
            student_responses = {
                row[0]: int(row[1])
                for row in (
                    await self._session.execute(
                        select(
                            IntentionResponse.survey_id,
                            IntentionResponse.submission_count,
                        ).where(
                            IntentionResponse.user_id == student_user_id,
                            IntentionResponse.survey_id.in_([row[0].id for row in rows]),
                        )
                    )
                ).all()
            }
        return [
            SurveyListRecord(
                survey=row[0],
                question_count=int(row[1]),
                responded_count=int(row[2]),
                has_response=row[0].id in student_responses,
                submissions_used=student_responses.get(row[0].id, 0),
            )
            for row in rows
        ]

    async def questions(self, survey_id: UUID) -> list[IntentionQuestion]:
        return list(
            (
                await self._session.scalars(
                    select(IntentionQuestion)
                    .where(IntentionQuestion.survey_id == survey_id)
                    .order_by(IntentionQuestion.display_order, IntentionQuestion.id)
                )
            ).all()
        )

    async def options(self, survey_id: UUID) -> list[IntentionOption]:
        return list(
            (
                await self._session.scalars(
                    select(IntentionOption)
                    .join(
                        IntentionQuestion,
                        IntentionQuestion.id == IntentionOption.question_id,
                    )
                    .where(IntentionQuestion.survey_id == survey_id)
                    .order_by(
                        IntentionQuestion.display_order,
                        IntentionOption.display_order,
                        IntentionOption.id,
                    )
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

    async def response_options_for_responses(
        self, response_ids: list[UUID]
    ) -> dict[UUID, list[IntentionResponseOption]]:
        if not response_ids:
            return {}
        rows = list(
            (
                await self._session.scalars(
                    select(IntentionResponseOption).where(
                        IntentionResponseOption.response_id.in_(response_ids)
                    )
                )
            ).all()
        )
        grouped: dict[UUID, list[IntentionResponseOption]] = {}
        for row in rows:
            grouped.setdefault(row.response_id, []).append(row)
        return grouped

    async def active_student_count(self) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "student", User.status == "active")
            )
            or 0
        )

    async def active_students_by_ids(self, user_ids: Sequence[UUID]) -> list[User]:
        if not user_ids:
            return []
        return list(
            (
                await self._session.scalars(
                    select(User)
                    .where(User.id.in_(user_ids), User.role == "student", User.status == "active")
                    .order_by(User.id)
                )
            ).all()
        )

    async def active_direction(self, direction_id: UUID) -> Direction | None:
        result: Direction | None = await self._session.scalar(
            select(Direction).where(Direction.id == direction_id, Direction.is_active.is_(True))
        )
        return result

    async def active_students_for_email_scope(self, *, direction_id: UUID | None) -> list[User]:
        statement = select(User).where(User.role == "student", User.status == "active")
        if direction_id is not None:
            statement = statement.where(User.direction_id == direction_id)
        return list((await self._session.scalars(statement.order_by(User.id))).all())

    async def option_counts(self, survey_id: UUID) -> list[SurveyOptionCount]:
        rows = (
            await self._session.execute(
                select(
                    IntentionQuestion,
                    IntentionOption,
                    func.count(IntentionResponseOption.response_id),
                )
                .join(IntentionOption, IntentionOption.question_id == IntentionQuestion.id)
                .outerjoin(
                    IntentionResponseOption,
                    IntentionResponseOption.option_id == IntentionOption.id,
                )
                .where(IntentionQuestion.survey_id == survey_id)
                .group_by(IntentionQuestion.id, IntentionOption.id)
                .order_by(
                    IntentionQuestion.display_order,
                    IntentionOption.display_order,
                    IntentionOption.id,
                )
            )
        ).all()
        return [
            SurveyOptionCount(question=row[0], option=row[1], response_count=int(row[2]))
            for row in rows
        ]

    async def responded_count(self, survey_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(IntentionResponse)
                .where(IntentionResponse.survey_id == survey_id)
            )
            or 0
        )

    async def roster(self, survey_id: UUID) -> list[SurveyRosterRecord]:
        rows = (
            await self._session.execute(
                select(IntentionResponse, User)
                .join(User, User.id == IntentionResponse.user_id)
                .where(IntentionResponse.survey_id == survey_id)
                .order_by(IntentionResponse.submitted_at.desc(), User.full_name, User.id)
            )
        ).all()
        return [SurveyRosterRecord(response=row[0], user=row[1]) for row in rows]
