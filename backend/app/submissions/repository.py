from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.submissions.models import (
    Feedback,
    IdempotencyRecord,
    Submission,
    SubmissionVersion,
    VersionFile,
)
from app.uploads.models import StoredFile


@dataclass(frozen=True, slots=True)
class VersionSubmissionRecord:
    version: SubmissionVersion
    submission: Submission


@dataclass(frozen=True, slots=True)
class AssignmentSubmissionRecord:
    submission: Submission
    latest_version: SubmissionVersion | None
    has_feedback: bool


class SubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_submission(self, submission: Submission) -> None:
        self._session.add(submission)

    def add_version(self, version: SubmissionVersion) -> None:
        self._session.add(version)

    def add_version_files(
        self,
        *,
        version_id: UUID,
        file_ids: Sequence[UUID],
    ) -> None:
        self._session.add_all(
            [
                VersionFile(
                    version_id=version_id,
                    file_id=file_id,
                    display_order=index,
                )
                for index, file_id in enumerate(file_ids)
            ]
        )

    async def get_for_assignment_owner(
        self,
        assignment_id: UUID,
        owner_user_id: UUID,
        *,
        for_update: bool = False,
    ) -> Submission | None:
        statement = select(Submission).where(
            Submission.assignment_id == assignment_id,
            Submission.owner_user_id == owner_user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: Submission | None = await self._session.scalar(statement)
        return result

    async def get_for_competition_team(
        self,
        competition_task_id: UUID,
        owner_team_id: UUID,
        *,
        for_update: bool = False,
    ) -> Submission | None:
        statement = select(Submission).where(
            Submission.competition_task_id == competition_task_id,
            Submission.owner_team_id == owner_team_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: Submission | None = await self._session.scalar(statement)
        return result

    async def get_by_id(
        self,
        submission_id: UUID,
        *,
        for_update: bool = False,
    ) -> Submission | None:
        statement = select(Submission).where(Submission.id == submission_id)
        if for_update:
            statement = statement.with_for_update()
        result: Submission | None = await self._session.scalar(statement)
        return result

    async def get_version(
        self,
        version_id: UUID,
        *,
        submission_id: UUID | None = None,
    ) -> SubmissionVersion | None:
        statement = select(SubmissionVersion).where(SubmissionVersion.id == version_id)
        if submission_id is not None:
            statement = statement.where(SubmissionVersion.submission_id == submission_id)
        result: SubmissionVersion | None = await self._session.scalar(statement)
        return result

    async def version_with_submission(
        self,
        version_id: UUID,
    ) -> VersionSubmissionRecord | None:
        row = (
            await self._session.execute(
                select(SubmissionVersion, Submission)
                .join(Submission, Submission.id == SubmissionVersion.submission_id)
                .where(SubmissionVersion.id == version_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return VersionSubmissionRecord(version=row[0], submission=row[1])

    async def versions(self, submission_id: UUID) -> list[SubmissionVersion]:
        return list(
            (
                await self._session.scalars(
                    select(SubmissionVersion)
                    .where(SubmissionVersion.submission_id == submission_id)
                    .order_by(
                        SubmissionVersion.version_number.desc(),
                        SubmissionVersion.id.desc(),
                    )
                )
            ).all()
        )

    async def latest_version(self, submission: Submission) -> SubmissionVersion | None:
        if submission.latest_version_id is None:
            return None
        return await self.get_version(
            submission.latest_version_id,
            submission_id=submission.id,
        )

    async def assignment_summaries_for_user(
        self,
        *,
        assignment_ids: Sequence[UUID],
        owner_user_id: UUID,
    ) -> dict[UUID, AssignmentSubmissionRecord]:
        if not assignment_ids:
            return {}
        feedback_exists = exists(
            select(Feedback.id)
            .select_from(SubmissionVersion)
            .join(Feedback, Feedback.version_id == SubmissionVersion.id)
            .where(SubmissionVersion.submission_id == Submission.id)
        )
        rows = (
            await self._session.execute(
                select(
                    Submission,
                    SubmissionVersion,
                    feedback_exists.label("has_feedback"),
                )
                .outerjoin(
                    SubmissionVersion,
                    SubmissionVersion.id == Submission.latest_version_id,
                )
                .where(
                    Submission.assignment_id.in_(assignment_ids),
                    Submission.owner_user_id == owner_user_id,
                )
            )
        ).all()
        summaries: dict[UUID, AssignmentSubmissionRecord] = {}
        for row in rows:
            assignment_id = row[0].assignment_id
            if assignment_id is not None:
                summaries[assignment_id] = AssignmentSubmissionRecord(
                    submission=row[0],
                    latest_version=row[1],
                    has_feedback=bool(row[2]),
                )
        return summaries

    async def files_for_version(self, version_id: UUID) -> list[StoredFile]:
        return list(
            (
                await self._session.scalars(
                    select(StoredFile)
                    .join(VersionFile, VersionFile.file_id == StoredFile.id)
                    .where(VersionFile.version_id == version_id)
                    .order_by(VersionFile.display_order)
                )
            ).all()
        )

    async def feedback_for_version(
        self,
        version_id: UUID,
        *,
        for_update: bool = False,
    ) -> Feedback | None:
        statement = select(Feedback).where(Feedback.version_id == version_id)
        if for_update:
            statement = statement.with_for_update()
        result: Feedback | None = await self._session.scalar(statement)
        return result

    async def submission_has_feedback(self, submission_id: UUID) -> bool:
        value = await self._session.scalar(
            select(
                exists().where(
                    SubmissionVersion.submission_id == submission_id,
                    Feedback.version_id == SubmissionVersion.id,
                )
            )
        )
        return bool(value)

    def add_feedback(self, feedback: Feedback) -> None:
        self._session.add(feedback)

    async def get_idempotency(
        self,
        *,
        user_id: UUID,
        endpoint_key: str,
        idempotency_key: str,
        for_update: bool = False,
    ) -> IdempotencyRecord | None:
        statement = select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.endpoint_key == endpoint_key,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        if for_update:
            statement = statement.with_for_update()
        result: IdempotencyRecord | None = await self._session.scalar(statement)
        return result

    def add_idempotency(self, record: IdempotencyRecord) -> None:
        self._session.add(record)

    async def has_version_after(
        self,
        *,
        assignment_id: UUID,
        owner_user_id: UUID,
        after: datetime,
    ) -> bool:
        value = await self._session.scalar(
            select(
                exists().where(
                    Submission.assignment_id == assignment_id,
                    Submission.owner_user_id == owner_user_id,
                    SubmissionVersion.submission_id == Submission.id,
                    SubmissionVersion.submitted_at > after,
                )
            )
        )
        return bool(value)

    async def file_is_bound(self, file_id: UUID) -> bool:
        value = await self._session.scalar(select(exists().where(VersionFile.file_id == file_id)))
        return bool(value)

    async def version_belongs_to_assignment(
        self,
        *,
        version_id: UUID,
        assignment_id: UUID,
    ) -> bool:
        value = await self._session.scalar(
            select(
                exists().where(
                    SubmissionVersion.id == version_id,
                    Submission.id == SubmissionVersion.submission_id,
                    Submission.assignment_id == assignment_id,
                )
            )
        )
        return bool(value)

    async def feedback_exists_for_latest(self, submission: Submission) -> bool:
        if submission.latest_version_id is None:
            return False
        value = await self._session.scalar(
            select(
                exists().where(
                    and_(
                        Feedback.version_id == submission.latest_version_id,
                    )
                )
            )
        )
        return bool(value)
