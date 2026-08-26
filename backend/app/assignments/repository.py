from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    delete,
    exists,
    false,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.models import (
    Assignment,
    AssignmentAudienceUser,
    AssignmentCohort,
    AssignmentDirection,
    AssignmentExcellentSubmission,
    AssignmentExtension,
)
from app.submissions.models import Feedback, Submission, SubmissionVersion
from app.users.models import User


@dataclass(frozen=True, slots=True)
class StudentAssignmentRecord:
    assignment: Assignment
    extension: AssignmentExtension | None


@dataclass(frozen=True, slots=True)
class AssignmentStats:
    target_count: int
    submitted_count: int
    feedback_submission_count: int
    last_submitted_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExcellentSubmissionRecord:
    marker: AssignmentExcellentSubmission
    version: SubmissionVersion
    submission: Submission
    author: User


@dataclass(frozen=True, slots=True)
class AdminSubmissionRecord:
    user: User
    submission: Submission | None
    latest_version: SubmissionVersion | None
    has_feedback: bool


class AssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, assignment: Assignment) -> None:
        self._session.add(assignment)

    async def get_by_id(
        self,
        assignment_id: UUID,
        *,
        for_update: bool = False,
    ) -> Assignment | None:
        statement = select(Assignment).where(Assignment.id == assignment_id)
        if for_update:
            statement = statement.with_for_update()
        result: Assignment | None = await self._session.scalar(statement)
        return result

    async def audience_ids(self, assignment_id: UUID) -> tuple[set[UUID], set[UUID]]:
        cohort_ids = set(
            (
                await self._session.scalars(
                    select(AssignmentCohort.cohort_id).where(
                        AssignmentCohort.assignment_id == assignment_id
                    )
                )
            ).all()
        )
        direction_ids = set(
            (
                await self._session.scalars(
                    select(AssignmentDirection.direction_id).where(
                        AssignmentDirection.assignment_id == assignment_id
                    )
                )
            ).all()
        )
        return cohort_ids, direction_ids

    async def replace_audience(
        self,
        assignment_id: UUID,
        *,
        cohort_ids: Sequence[UUID],
        direction_ids: Sequence[UUID],
    ) -> None:
        await self._session.execute(
            delete(AssignmentCohort).where(AssignmentCohort.assignment_id == assignment_id)
        )
        await self._session.execute(
            delete(AssignmentDirection).where(AssignmentDirection.assignment_id == assignment_id)
        )
        self._session.add_all(
            [
                AssignmentCohort(assignment_id=assignment_id, cohort_id=cohort_id)
                for cohort_id in cohort_ids
            ]
        )
        self._session.add_all(
            [
                AssignmentDirection(
                    assignment_id=assignment_id,
                    direction_id=direction_id,
                )
                for direction_id in direction_ids
            ]
        )

    def add_audience_snapshot(
        self,
        *,
        assignment_id: UUID,
        users: Sequence[User],
        created_at: datetime,
    ) -> None:
        self._session.add_all(
            [
                AssignmentAudienceUser(
                    assignment_id=assignment_id,
                    user_id=user.id,
                    cohort_id_at_publish=user.cohort_id,
                    direction_id_at_publish=user.direction_id,
                    created_at=created_at,
                )
                for user in users
            ]
        )

    async def actual_audience_count(self, assignment_id: UUID) -> int:
        value = await self._session.scalar(
            select(func.count())
            .select_from(AssignmentAudienceUser)
            .where(AssignmentAudienceUser.assignment_id == assignment_id)
        )
        return int(value or 0)

    @staticmethod
    def _live_audience_condition(user: User) -> ColumnElement[bool]:
        cohort_configured = exists(select(1).where(AssignmentCohort.assignment_id == Assignment.id))
        direction_configured = exists(
            select(1).where(AssignmentDirection.assignment_id == Assignment.id)
        )
        cohort_matches: ColumnElement[bool]
        if user.cohort_id is None:
            cohort_matches = false()
        else:
            cohort_matches = exists(
                select(1).where(
                    AssignmentCohort.assignment_id == Assignment.id,
                    AssignmentCohort.cohort_id == user.cohort_id,
                )
            )
        direction_matches: ColumnElement[bool]
        if user.direction_id is None:
            direction_matches = false()
        else:
            direction_matches = exists(
                select(1).where(
                    AssignmentDirection.assignment_id == Assignment.id,
                    AssignmentDirection.direction_id == user.direction_id,
                )
            )
        union_matches = and_(
            Assignment.audience_match == "union",
            or_(cohort_matches, direction_matches),
        )
        intersection_matches = and_(
            Assignment.audience_match == "intersection",
            or_(cohort_configured, direction_configured),
            or_(~cohort_configured, cohort_matches),
            or_(~direction_configured, direction_matches),
        )
        return or_(
            Assignment.all_students.is_(True),
            and_(
                Assignment.all_students.is_(False),
                or_(union_matches, intersection_matches),
            ),
        )

    async def is_audience_user(
        self,
        assignment_id: UUID,
        user_id: UUID,
        *,
        preview_user: User | None = None,
    ) -> bool:
        snapshot_match = exists().where(
            AssignmentAudienceUser.assignment_id == assignment_id,
            AssignmentAudienceUser.user_id == user_id,
        )
        audience_match: ColumnElement[bool] = snapshot_match
        if preview_user is not None:
            audience_match = or_(
                snapshot_match,
                self._live_audience_condition(preview_user),
            )
        value = await self._session.scalar(
            select(audience_match).select_from(Assignment).where(Assignment.id == assignment_id)
        )
        return bool(value)

    async def get_extension(
        self,
        assignment_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> AssignmentExtension | None:
        statement = select(AssignmentExtension).where(
            AssignmentExtension.assignment_id == assignment_id,
            AssignmentExtension.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: AssignmentExtension | None = await self._session.scalar(statement)
        return result

    def add_extension(self, extension: AssignmentExtension) -> None:
        self._session.add(extension)

    async def delete_extension(self, assignment_id: UUID, user_id: UUID) -> None:
        await self._session.execute(
            delete(AssignmentExtension).where(
                AssignmentExtension.assignment_id == assignment_id,
                AssignmentExtension.user_id == user_id,
            )
        )

    async def get_for_student(
        self,
        assignment_id: UUID,
        user_id: UUID,
        *,
        preview_user: User | None = None,
    ) -> StudentAssignmentRecord | None:
        snapshot_match = exists().where(
            AssignmentAudienceUser.assignment_id == Assignment.id,
            AssignmentAudienceUser.user_id == user_id,
        )
        audience_match: ColumnElement[bool] = snapshot_match
        if preview_user is not None:
            audience_match = or_(
                snapshot_match,
                self._live_audience_condition(preview_user),
            )
        row = (
            await self._session.execute(
                select(Assignment, AssignmentExtension)
                .outerjoin(
                    AssignmentExtension,
                    and_(
                        AssignmentExtension.assignment_id == Assignment.id,
                        AssignmentExtension.user_id == user_id,
                    ),
                )
                .where(
                    Assignment.id == assignment_id,
                    Assignment.status != "draft",
                    audience_match,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return StudentAssignmentRecord(assignment=row[0], extension=row[1])

    async def list_for_student(
        self,
        *,
        user_id: UUID,
        preview_user: User | None = None,
        page: int,
        page_size: int,
        status: str | None,
        query: str | None,
        now: datetime,
        limit: int | None = None,
    ) -> tuple[list[StudentAssignmentRecord], int]:
        submission_exists = exists().where(
            Submission.assignment_id == Assignment.id,
            Submission.owner_user_id == user_id,
        )
        effective_deadline = func.coalesce(
            AssignmentExtension.extended_deadline,
            Assignment.deadline,
        )
        auto_closed = and_(
            Assignment.status == "closed",
            Assignment.closed_at >= Assignment.deadline,
        )
        accepts_submissions = and_(
            or_(Assignment.status == "published", auto_closed),
            effective_deadline > now,
        )
        snapshot_match = exists().where(
            AssignmentAudienceUser.assignment_id == Assignment.id,
            AssignmentAudienceUser.user_id == user_id,
        )
        audience_match: ColumnElement[bool] = snapshot_match
        if preview_user is not None:
            audience_match = or_(
                snapshot_match,
                self._live_audience_condition(preview_user),
            )
        filters: list[ColumnElement[bool]] = [
            audience_match,
            Assignment.status != "draft",
        ]
        if query:
            filters.append(Assignment.title.ilike(f"%{query.strip()}%"))
        if status == "pending":
            filters.extend([~submission_exists, accepts_submissions])
        elif status == "submitted":
            filters.append(submission_exists)
        elif status == "closed":
            filters.append(
                or_(
                    Assignment.status == "archived",
                    ~accepts_submissions,
                )
            )

        base = (
            select(Assignment, AssignmentExtension)
            .outerjoin(
                AssignmentExtension,
                and_(
                    AssignmentExtension.assignment_id == Assignment.id,
                    AssignmentExtension.user_id == user_id,
                ),
            )
            .where(*filters)
        )
        count = 0
        if limit is None:
            count = int(
                await self._session.scalar(select(func.count()).select_from(base.subquery())) or 0
            )
        statement = base.order_by(
            (effective_deadline <= now),
            effective_deadline,
            Assignment.id,
        )
        if limit is not None:
            statement = statement.limit(limit)
        else:
            statement = statement.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._session.execute(statement)).all()
        return (
            [StudentAssignmentRecord(assignment=row[0], extension=row[1]) for row in rows],
            count,
        )

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        query: str | None,
    ) -> tuple[list[Assignment], int]:
        filters: list[ColumnElement[bool]] = []
        if status is not None:
            filters.append(Assignment.status == status)
        if query:
            filters.append(Assignment.title.ilike(f"%{query.strip()}%"))
        total = int(
            await self._session.scalar(select(func.count()).select_from(Assignment).where(*filters))
            or 0
        )
        statement: Select[tuple[Assignment]] = (
            select(Assignment)
            .where(*filters)
            .order_by(Assignment.created_at.desc(), Assignment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.scalars(statement)).all()), total

    async def stats(self, assignment_id: UUID) -> AssignmentStats:
        target_count = await self.actual_audience_count(assignment_id)
        submitted_count = int(
            await self._session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(Submission.assignment_id == assignment_id)
            )
            or 0
        )
        feedback_submission_count = int(
            await self._session.scalar(
                select(func.count(func.distinct(Submission.id)))
                .select_from(Submission)
                .join(
                    SubmissionVersion,
                    SubmissionVersion.submission_id == Submission.id,
                )
                .join(Feedback, Feedback.version_id == SubmissionVersion.id)
                .where(Submission.assignment_id == assignment_id)
            )
            or 0
        )
        last_submitted_at = await self._session.scalar(
            select(func.max(SubmissionVersion.submitted_at))
            .select_from(SubmissionVersion)
            .join(Submission, Submission.id == SubmissionVersion.submission_id)
            .where(Submission.assignment_id == assignment_id)
        )
        return AssignmentStats(
            target_count=target_count,
            submitted_count=submitted_count,
            feedback_submission_count=feedback_submission_count,
            last_submitted_at=last_submitted_at,
        )

    async def submissions_for_admin(
        self,
        assignment_id: UUID,
        *,
        page: int,
        page_size: int,
        cohort_id: UUID | None,
        direction_id: UUID | None,
        submission_status: str | None,
        feedback_status: str | None,
    ) -> tuple[list[AdminSubmissionRecord], int]:
        feedback_exists = exists().where(
            Feedback.version_id == SubmissionVersion.id,
        )
        filters: list[ColumnElement[bool]] = [AssignmentAudienceUser.assignment_id == assignment_id]
        if cohort_id is not None:
            filters.append(AssignmentAudienceUser.cohort_id_at_publish == cohort_id)
        if direction_id is not None:
            filters.append(AssignmentAudienceUser.direction_id_at_publish == direction_id)
        if submission_status == "submitted":
            filters.append(Submission.id.is_not(None))
        elif submission_status == "unsubmitted":
            filters.append(Submission.id.is_(None))
        if feedback_status == "feedback":
            filters.append(feedback_exists)
        elif feedback_status == "no_feedback":
            filters.append(~feedback_exists)

        base = (
            select(User, Submission, SubmissionVersion, feedback_exists.label("has_feedback"))
            .select_from(AssignmentAudienceUser)
            .join(User, User.id == AssignmentAudienceUser.user_id)
            .outerjoin(
                Submission,
                and_(
                    Submission.assignment_id == assignment_id,
                    Submission.owner_user_id == User.id,
                ),
            )
            .outerjoin(
                SubmissionVersion,
                SubmissionVersion.id == Submission.latest_version_id,
            )
            .where(*filters)
        )
        total = int(
            await self._session.scalar(select(func.count()).select_from(base.subquery())) or 0
        )
        rows = (
            await self._session.execute(
                base.order_by(User.full_name, User.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return (
            [
                AdminSubmissionRecord(
                    user=row[0],
                    submission=row[1],
                    latest_version=row[2],
                    has_feedback=bool(row[3]),
                )
                for row in rows
            ],
            total,
        )

    async def excellent_records(
        self,
        assignment_id: UUID,
    ) -> list[ExcellentSubmissionRecord]:
        rows = (
            await self._session.execute(
                select(
                    AssignmentExcellentSubmission,
                    SubmissionVersion,
                    Submission,
                    User,
                )
                .join(
                    SubmissionVersion,
                    SubmissionVersion.id == AssignmentExcellentSubmission.version_id,
                )
                .join(Submission, Submission.id == SubmissionVersion.submission_id)
                .join(User, User.id == Submission.owner_user_id)
                .where(AssignmentExcellentSubmission.assignment_id == assignment_id)
                .order_by(
                    AssignmentExcellentSubmission.marked_at.desc(),
                    AssignmentExcellentSubmission.version_id,
                )
            )
        ).all()
        return [
            ExcellentSubmissionRecord(
                marker=row[0],
                version=row[1],
                submission=row[2],
                author=row[3],
            )
            for row in rows
        ]

    async def excellent_record(
        self,
        assignment_id: UUID,
        version_id: UUID,
    ) -> ExcellentSubmissionRecord | None:
        row = (
            await self._session.execute(
                select(
                    AssignmentExcellentSubmission,
                    SubmissionVersion,
                    Submission,
                    User,
                )
                .join(
                    SubmissionVersion,
                    SubmissionVersion.id == AssignmentExcellentSubmission.version_id,
                )
                .join(Submission, Submission.id == SubmissionVersion.submission_id)
                .join(User, User.id == Submission.owner_user_id)
                .where(
                    AssignmentExcellentSubmission.assignment_id == assignment_id,
                    AssignmentExcellentSubmission.version_id == version_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return ExcellentSubmissionRecord(
            marker=row[0],
            version=row[1],
            submission=row[2],
            author=row[3],
        )

    async def get_excellent_marker(
        self,
        assignment_id: UUID,
        version_id: UUID,
        *,
        for_update: bool = False,
    ) -> AssignmentExcellentSubmission | None:
        statement = select(AssignmentExcellentSubmission).where(
            AssignmentExcellentSubmission.assignment_id == assignment_id,
            AssignmentExcellentSubmission.version_id == version_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: AssignmentExcellentSubmission | None = await self._session.scalar(statement)
        return result

    def add_excellent_marker(
        self,
        marker: AssignmentExcellentSubmission,
    ) -> None:
        self._session.add(marker)

    async def delete_excellent_marker(
        self,
        assignment_id: UUID,
        version_id: UUID,
    ) -> None:
        await self._session.execute(
            delete(AssignmentExcellentSubmission).where(
                AssignmentExcellentSubmission.assignment_id == assignment_id,
                AssignmentExcellentSubmission.version_id == version_id,
            )
        )
