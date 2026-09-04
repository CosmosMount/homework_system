from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intentions.models import (
    IntentionOption,
    IntentionQuestion,
    IntentionResponse,
    IntentionResponseOption,
    IntentionSurvey,
    IntentionSurveyDirection,
)
from app.users.models import Direction, User


@dataclass(frozen=True, slots=True)
class SurveyListRecord:
    survey: IntentionSurvey
    question_count: int
    responded_count: int
    has_response: bool
    submissions_used: int = 0
    direction_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class SurveyOptionCount:
    question: IntentionQuestion
    option: IntentionOption
    response_count: int


@dataclass(frozen=True, slots=True)
class SurveyRosterRecord:
    response: IntentionResponse
    user: User


@dataclass(frozen=True, slots=True)
class FirstChoiceDirectionRecord:
    user: User
    option_id: UUID


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

    async def delete_response_options_for_survey(self, survey_id: UUID) -> None:
        await self._session.execute(
            delete(IntentionResponseOption).where(
                IntentionResponseOption.response_id.in_(
                    select(IntentionResponse.id).where(IntentionResponse.survey_id == survey_id)
                )
            )
        )

    async def delete_survey(self, survey: IntentionSurvey) -> None:
        await self._session.delete(survey)

    async def replace_audience(self, survey_id: UUID, direction_ids: Sequence[UUID]) -> None:
        await self._session.execute(
            delete(IntentionSurveyDirection).where(IntentionSurveyDirection.survey_id == survey_id)
        )
        self._session.add_all(
            [
                IntentionSurveyDirection(survey_id=survey_id, direction_id=direction_id)
                for direction_id in direction_ids
            ]
        )

    async def audience_direction_ids(self, survey_id: UUID) -> list[UUID]:
        return list(
            (
                await self._session.scalars(
                    select(IntentionSurveyDirection.direction_id)
                    .where(IntentionSurveyDirection.survey_id == survey_id)
                    .order_by(IntentionSurveyDirection.direction_id)
                )
            ).all()
        )

    async def _audience_direction_ids_for_surveys(
        self, survey_ids: Sequence[UUID]
    ) -> dict[UUID, tuple[UUID, ...]]:
        if not survey_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    IntentionSurveyDirection.survey_id,
                    IntentionSurveyDirection.direction_id,
                )
                .where(IntentionSurveyDirection.survey_id.in_(survey_ids))
                .order_by(
                    IntentionSurveyDirection.survey_id,
                    IntentionSurveyDirection.direction_id,
                )
            )
        ).all()
        grouped: dict[UUID, list[UUID]] = {}
        for survey_id, direction_id in rows:
            grouped.setdefault(survey_id, []).append(direction_id)
        return {survey_id: tuple(direction_ids) for survey_id, direction_ids in grouped.items()}

    async def student_direction_is_targeted(
        self, survey_id: UUID, direction_id: UUID | None
    ) -> bool:
        if direction_id is None:
            return False
        return bool(
            await self._session.scalar(
                select(func.count())
                .select_from(IntentionSurveyDirection)
                .where(
                    IntentionSurveyDirection.survey_id == survey_id,
                    IntentionSurveyDirection.direction_id == direction_id,
                )
            )
        )

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
        student_direction_id: UUID | None = None,
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
        if student_user_id is not None:
            audience_filter: ColumnElement[bool] = IntentionSurvey.all_students.is_(True)
            if student_direction_id is not None:
                audience_filter = or_(
                    audience_filter,
                    IntentionSurvey.id.in_(
                        select(IntentionSurveyDirection.survey_id).where(
                            IntentionSurveyDirection.direction_id == student_direction_id
                        )
                    ),
                )
            filters.append(audience_filter)
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
        directions_by_survey = await self._audience_direction_ids_for_surveys(
            [row[0].id for row in rows]
        )
        return [
            SurveyListRecord(
                survey=row[0],
                question_count=int(row[1]),
                responded_count=int(row[2]),
                has_response=row[0].id in student_responses,
                submissions_used=student_responses.get(row[0].id, 0),
                direction_ids=directions_by_survey.get(row[0].id, ()),
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

    async def active_student_count(self, *, direction_ids: Sequence[UUID] | None) -> int:
        statement = (
            select(func.count())
            .select_from(User)
            .where(User.role == "student", User.status == "active")
        )
        if direction_ids is not None:
            statement = statement.where(User.direction_id.in_(direction_ids))
        return int(await self._session.scalar(statement) or 0)

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

    async def active_directions_by_ids(self, direction_ids: Sequence[UUID]) -> list[Direction]:
        if not direction_ids:
            return []
        return list(
            (
                await self._session.scalars(
                    select(Direction)
                    .where(
                        Direction.id.in_(direction_ids),
                        Direction.is_active.is_(True),
                    )
                    .order_by(Direction.id)
                    .with_for_update()
                )
            ).all()
        )

    async def active_student_first_choices(
        self, survey_id: UUID, question_id: UUID
    ) -> list[FirstChoiceDirectionRecord]:
        rows = (
            await self._session.execute(
                select(User, IntentionResponseOption.option_id)
                .select_from(User)
                .join(IntentionResponse, IntentionResponse.user_id == User.id)
                .join(
                    IntentionResponseOption,
                    IntentionResponseOption.response_id == IntentionResponse.id,
                )
                .join(
                    IntentionOption,
                    IntentionOption.id == IntentionResponseOption.option_id,
                )
                .where(
                    IntentionResponse.survey_id == survey_id,
                    IntentionOption.question_id == question_id,
                    User.role == "student",
                    User.status == "active",
                )
                .order_by(User.id)
                .with_for_update(of=User)
            )
        ).all()
        return [FirstChoiceDirectionRecord(user=row[0], option_id=row[1]) for row in rows]

    async def active_students_for_email_scope(
        self, *, direction_ids: Sequence[UUID] | None
    ) -> list[User]:
        statement = select(User).where(User.role == "student", User.status == "active")
        if direction_ids is not None:
            statement = statement.where(User.direction_id.in_(direction_ids))
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
