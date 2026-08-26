import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.repository import AssignmentRepository
from app.assignments.service import AssignmentService
from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, context_effective_role, context_is_admin
from app.competitions.policy import task_submission_is_open
from app.competitions.repository import CompetitionRepository
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.core.markdown import render_markdown
from app.notifications.models import StudentNotification
from app.notifications.repository import StudentNotificationRepository
from app.submissions.models import (
    Feedback,
    IdempotencyRecord,
    Submission,
    SubmissionVersion,
)
from app.submissions.repository import SubmissionRepository
from app.submissions.schemas import (
    FeedbackPutRequest,
    FeedbackResponse,
    SubmissionAttachmentResponse,
    SubmissionResponse,
    SubmissionVersionCreatedResponse,
    SubmissionVersionCreateRequest,
    SubmissionVersionResponse,
)
from app.uploads.models import StoredFile
from app.uploads.repository import UploadRepository


@dataclass(frozen=True, slots=True)
class SubmissionAuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


class SubmissionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._assignments = AssignmentRepository(session)
        self._competitions = CompetitionRepository(session)
        self._submissions = SubmissionRepository(session)
        self._uploads = UploadRepository(session)
        self._notifications = StudentNotificationRepository(session)
        self._audit = AuditRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _not_found() -> ApplicationError:
        return ApplicationError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="资源不存在或当前用户无权查看。",
        )

    @staticmethod
    def _request_hash(payload: SubmissionVersionCreateRequest) -> str:
        encoded = json.dumps(
            payload.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _idempotency_conflict() -> ApplicationError:
        return ApplicationError(
            status_code=409,
            code="IDEMPOTENCY_CONFLICT",
            message="同一幂等键已经用于不同的正式提交请求。",
        )

    def _add_audit(
        self,
        *,
        actor_user_id: UUID,
        action: str,
        target_id: UUID,
        request_id: str,
        ip_prefix: str,
        change_summary: dict[str, object],
        now: datetime,
    ) -> None:
        self._audit.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=actor_user_id,
                action=action,
                target_type="submission_version",
                target_id=target_id,
                request_id=request_id,
                ip_prefix=ip_prefix,
                result="success",
                change_summary=change_summary,
                created_at=now,
            )
        )

    async def _validate_files(
        self,
        *,
        assignment_id: UUID,
        actor_user_id: UUID,
        allowed_extensions: Sequence[str],
        max_total_bytes: int,
        file_ids: Sequence[UUID],
    ) -> tuple[list[StoredFile], int]:
        if not file_ids:
            return [], 0
        files = await self._uploads.get_files(file_ids, for_update=True)
        by_id = {file.id: file for file in files}
        if set(by_id) != set(file_ids):
            raise self._not_found()
        ordered = [by_id[file_id] for file_id in file_ids]
        total_bytes = 0
        for file in ordered:
            if (
                file.owner_user_id != actor_user_id
                or file.purpose != "assignment_submission"
                or file.status != "available"
                or file.deleted_at is not None
            ):
                raise ApplicationError(
                    status_code=409,
                    code="FILE_NOT_AVAILABLE",
                    message="附件尚未完成校验或不能用于当前作业。",
                )
            upload_session = await self._uploads.get_session_by_file(file.id)
            if (
                upload_session is None
                or upload_session.context_type != "assignment"
                or upload_session.context_id != assignment_id
            ):
                raise ApplicationError(
                    status_code=409,
                    code="FILE_CONTEXT_MISMATCH",
                    message="附件不属于当前作业。",
                )
            if file.extension not in allowed_extensions:
                raise ApplicationError(
                    status_code=415,
                    code="FILE_TYPE_NOT_ALLOWED",
                    message="附件类型不在当前作业白名单内。",
                )
            if await self._uploads.bound_announcement_id(
                file.id
            ) is not None or await self._submissions.file_is_bound(file.id):
                raise ApplicationError(
                    status_code=409,
                    code="FILE_ALREADY_BOUND",
                    message="附件已经绑定其他正式资源。",
                )
            total_bytes += file.size_bytes
        if total_bytes > max_total_bytes:
            raise ApplicationError(
                status_code=413,
                code="SUBMISSION_SIZE_EXCEEDED",
                message="本版本附件合计超过作业上限。",
            )
        return ordered, total_bytes

    async def _validate_competition_files(
        self,
        *,
        competition_task_id: UUID,
        actor_user_id: UUID,
        allowed_extensions: Sequence[str],
        max_total_bytes: int,
        file_ids: Sequence[UUID],
    ) -> tuple[list[StoredFile], int]:
        if not file_ids:
            return [], 0
        files = await self._uploads.get_files(file_ids, for_update=True)
        by_id = {file.id: file for file in files}
        if set(by_id) != set(file_ids):
            raise self._not_found()
        ordered = [by_id[file_id] for file_id in file_ids]
        total_bytes = 0
        for file in ordered:
            if (
                file.owner_user_id != actor_user_id
                or file.purpose != "competition_submission"
                or file.status != "available"
                or file.deleted_at is not None
            ):
                raise ApplicationError(
                    status_code=409,
                    code="FILE_NOT_AVAILABLE",
                    message="附件尚未完成校验或不能用于当前赛题。",
                )
            upload_session = await self._uploads.get_session_by_file(file.id)
            if (
                upload_session is None
                or upload_session.context_type != "competition_task"
                or upload_session.context_id != competition_task_id
            ):
                raise ApplicationError(
                    status_code=409,
                    code="FILE_CONTEXT_MISMATCH",
                    message="附件不属于当前赛题。",
                )
            if file.extension not in allowed_extensions:
                raise ApplicationError(
                    status_code=415,
                    code="FILE_TYPE_NOT_ALLOWED",
                    message="附件类型不在当前赛题白名单内。",
                )
            if await self._uploads.bound_announcement_id(
                file.id
            ) is not None or await self._submissions.file_is_bound(file.id):
                raise ApplicationError(
                    status_code=409,
                    code="FILE_ALREADY_BOUND",
                    message="附件已经绑定其他正式资源。",
                )
            total_bytes += file.size_bytes
        if total_bytes > max_total_bytes:
            raise ApplicationError(
                status_code=413,
                code="SUBMISSION_SIZE_EXCEEDED",
                message="本版本附件合计超过赛题上限。",
            )
        return ordered, total_bytes

    async def _existing_idempotent_response(
        self,
        *,
        user_id: UUID,
        endpoint_key: str,
        idempotency_key: str,
        request_hash: str,
        for_update: bool,
    ) -> SubmissionVersionCreatedResponse | None:
        record = await self._submissions.get_idempotency(
            user_id=user_id,
            endpoint_key=endpoint_key,
            idempotency_key=idempotency_key,
            for_update=for_update,
        )
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise self._idempotency_conflict()
        return SubmissionVersionCreatedResponse.model_validate(record.response_body)

    async def create_assignment_version(
        self,
        assignment_id: UUID,
        payload: SubmissionVersionCreateRequest,
        *,
        context: AuthenticatedContext,
        idempotency_key: str,
        request_id: str,
        ip_prefix: str,
    ) -> SubmissionVersionCreatedResponse:
        if context_effective_role(context) != "student":
            raise ApplicationError(
                status_code=403,
                code="FORBIDDEN",
                message="管理员不能代学生创建正式作业版本。",
            )
        endpoint_key = f"assignments/{assignment_id}/submission-versions"
        request_hash = self._request_hash(payload)
        replay = await self._existing_idempotent_response(
            user_id=context.user.id,
            endpoint_key=endpoint_key,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            for_update=False,
        )
        if replay is not None:
            return replay

        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if (
            assignment is None
            or assignment.status == "draft"
            or not await self._assignments.is_audience_user(
                assignment_id,
                context.user.id,
                preview_user=context.user if getattr(context, "is_student_view", False) else None,
            )
        ):
            await self._session.rollback()
            raise self._not_found()
        extension = await self._assignments.get_extension(
            assignment_id,
            context.user.id,
        )
        now = self._clock()
        if not AssignmentService._can_submit(assignment, extension, now):
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="ASSIGNMENT_CLOSED",
                message="作业已超过当前账号的有效截止时间。",
            )

        _, total_bytes = await self._validate_files(
            assignment_id=assignment_id,
            actor_user_id=context.user.id,
            allowed_extensions=assignment.allowed_extensions,
            max_total_bytes=assignment.max_total_bytes,
            file_ids=payload.file_ids,
        )
        submission = await self._submissions.get_for_assignment_owner(
            assignment_id,
            context.user.id,
            for_update=True,
        )
        if submission is None:
            submission = Submission(
                id=uuid7(),
                assignment_id=assignment_id,
                competition_task_id=None,
                owner_user_id=context.user.id,
                owner_team_id=None,
                latest_version_id=None,
                created_at=now,
                updated_at=now,
            )
            self._submissions.add_submission(submission)
            await self._session.flush()
            version_number = 1
        else:
            latest = await self._submissions.latest_version(submission)
            version_number = 1 if latest is None else latest.version_number + 1

        version = SubmissionVersion(
            id=uuid7(),
            submission_id=submission.id,
            version_number=version_number,
            submitted_by=context.user.id,
            text_markdown=payload.text_markdown,
            text_html=(
                render_markdown(payload.text_markdown)
                if payload.text_markdown is not None
                else None
            ),
            external_url=payload.external_url,
            total_file_bytes=total_bytes,
            idempotency_key=idempotency_key,
            submitted_at=now,
        )
        self._submissions.add_version(version)
        self._submissions.add_version_files(
            version_id=version.id,
            file_ids=payload.file_ids,
        )
        submission.latest_version_id = version.id
        submission.updated_at = now
        response = SubmissionVersionCreatedResponse(
            submission_id=submission.id,
            version_id=version.id,
            version_number=version.version_number,
            submitted_at=version.submitted_at,
            total_file_bytes=version.total_file_bytes,
        )
        self._submissions.add_idempotency(
            IdempotencyRecord(
                id=uuid7(),
                user_id=context.user.id,
                endpoint_key=endpoint_key,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_status=201,
                response_body=response.model_dump(mode="json"),
                resource_id=version.id,
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
        )
        self._add_audit(
            actor_user_id=context.user.id,
            action="submission.version_create",
            target_id=version.id,
            request_id=request_id,
            ip_prefix=ip_prefix,
            change_summary={
                "assignment_id": str(assignment_id),
                "submission_id": str(submission.id),
                "version_number": version.version_number,
                "attachment_count": len(payload.file_ids),
                "total_file_bytes": total_bytes,
                "has_text": payload.text_markdown is not None,
                "has_external_url": payload.external_url is not None,
            },
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            replay = await self._existing_idempotent_response(
                user_id=context.user.id,
                endpoint_key=endpoint_key,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                for_update=False,
            )
            if replay is not None:
                return replay
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="正式版本发生并发冲突，请刷新后重试。",
            ) from exc
        return response

    async def create_competition_version(
        self,
        competition_id: UUID,
        task_id: UUID,
        payload: SubmissionVersionCreateRequest,
        *,
        context: AuthenticatedContext,
        idempotency_key: str,
        request_id: str,
        ip_prefix: str,
    ) -> SubmissionVersionCreatedResponse:
        if context_effective_role(context) != "student":
            raise ApplicationError(
                status_code=403,
                code="FORBIDDEN",
                message="管理员不能代队伍创建正式赛事版本。",
            )
        endpoint_key = f"competitions/{competition_id}/tasks/{task_id}/submission-versions"
        request_hash = self._request_hash(payload)
        replay = await self._existing_idempotent_response(
            user_id=context.user.id,
            endpoint_key=endpoint_key,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            for_update=False,
        )
        if replay is not None:
            return replay

        competition = await self._competitions.get_competition(competition_id, for_update=True)
        task = await self._competitions.get_task(
            task_id,
            competition_id=competition_id,
            for_update=True,
        )
        team = await self._competitions.team_for_user(
            competition_id,
            context.user.id,
            for_update=True,
        )
        if competition is None or task is None or team is None or competition.published_at is None:
            await self._session.rollback()
            raise self._not_found()
        if team.captain_user_id != context.user.id:
            await self._session.rollback()
            raise ApplicationError(
                status_code=403,
                code="TEAM_CAPTAIN_REQUIRED",
                message="只有当前队长可以代表团队创建正式版本。",
            )
        now = self._clock()
        if not task_submission_is_open(competition, task, team, now):
            await self._session.rollback()
            if team.status == "invalid":
                raise ApplicationError(
                    status_code=409,
                    code="TEAM_INVALID",
                    message="队伍人数不满足规则，不能提交。",
                )
            if team.status == "disqualified":
                raise ApplicationError(
                    status_code=409,
                    code="TEAM_DISQUALIFIED",
                    message="队伍已被取消资格，不能提交。",
                )
            if team.status != "locked":
                raise ApplicationError(
                    status_code=409,
                    code="TEAM_NOT_LOCKED",
                    message="队伍尚未锁定为有效队伍。",
                )
            raise ApplicationError(
                status_code=409,
                code="COMPETITION_SUBMISSION_CLOSED",
                message="当前不在赛事或赛题的有效提交期。",
            )

        _, total_bytes = await self._validate_competition_files(
            competition_task_id=task.id,
            actor_user_id=context.user.id,
            allowed_extensions=task.allowed_extensions,
            max_total_bytes=task.max_total_bytes,
            file_ids=payload.file_ids,
        )
        submission = await self._submissions.get_for_competition_team(
            task.id,
            team.id,
            for_update=True,
        )
        if submission is None:
            submission = Submission(
                id=uuid7(),
                assignment_id=None,
                competition_task_id=task.id,
                owner_user_id=None,
                owner_team_id=team.id,
                latest_version_id=None,
                created_at=now,
                updated_at=now,
            )
            self._submissions.add_submission(submission)
            await self._session.flush()
            version_number = 1
        else:
            latest = await self._submissions.latest_version(submission)
            version_number = 1 if latest is None else latest.version_number + 1

        version = SubmissionVersion(
            id=uuid7(),
            submission_id=submission.id,
            version_number=version_number,
            submitted_by=context.user.id,
            text_markdown=payload.text_markdown,
            text_html=(
                render_markdown(payload.text_markdown)
                if payload.text_markdown is not None
                else None
            ),
            external_url=payload.external_url,
            total_file_bytes=total_bytes,
            idempotency_key=idempotency_key,
            submitted_at=now,
        )
        self._submissions.add_version(version)
        self._submissions.add_version_files(
            version_id=version.id,
            file_ids=payload.file_ids,
        )
        submission.latest_version_id = version.id
        submission.updated_at = now
        response = SubmissionVersionCreatedResponse(
            submission_id=submission.id,
            version_id=version.id,
            version_number=version.version_number,
            submitted_at=version.submitted_at,
            total_file_bytes=version.total_file_bytes,
        )
        self._submissions.add_idempotency(
            IdempotencyRecord(
                id=uuid7(),
                user_id=context.user.id,
                endpoint_key=endpoint_key,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_status=201,
                response_body=response.model_dump(mode="json"),
                resource_id=version.id,
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
        )
        self._add_audit(
            actor_user_id=context.user.id,
            action="competition_submission.version_create",
            target_id=version.id,
            request_id=request_id,
            ip_prefix=ip_prefix,
            change_summary={
                "competition_id": str(competition.id),
                "competition_task_id": str(task.id),
                "team_id": str(team.id),
                "submission_id": str(submission.id),
                "version_number": version.version_number,
                "attachment_count": len(payload.file_ids),
                "total_file_bytes": total_bytes,
                "has_text": payload.text_markdown is not None,
                "has_external_url": payload.external_url is not None,
            },
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            replay = await self._existing_idempotent_response(
                user_id=context.user.id,
                endpoint_key=endpoint_key,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                for_update=False,
            )
            if replay is not None:
                return replay
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="正式版本发生并发冲突，请刷新后重试。",
            ) from exc
        return response

    @staticmethod
    def _feedback_response(feedback: Feedback) -> FeedbackResponse:
        return FeedbackResponse(
            id=feedback.id,
            body_html=feedback.body_html,
            created_by=feedback.created_by,
            created_at=feedback.created_at,
            updated_at=feedback.updated_at,
            revision=feedback.revision,
        )

    async def _version_response(
        self,
        version: SubmissionVersion,
    ) -> SubmissionVersionResponse:
        files = await self._submissions.files_for_version(version.id)
        feedback = await self._submissions.feedback_for_version(version.id)
        return SubmissionVersionResponse(
            id=version.id,
            submission_id=version.submission_id,
            version_number=version.version_number,
            submitted_by=version.submitted_by,
            text_html=version.text_html,
            external_url=version.external_url,
            total_file_bytes=version.total_file_bytes,
            submitted_at=version.submitted_at,
            attachments=[
                SubmissionAttachmentResponse(
                    id=file.id,
                    file_name=file.original_name,
                    size_bytes=file.size_bytes,
                    media_type=file.detected_media_type or file.declared_media_type,
                    sha256=file.sha256,
                )
                for file in files
            ],
            feedback=(self._feedback_response(feedback) if feedback is not None else None),
        )

    async def _can_read_submission(
        self,
        submission: Submission,
        context: AuthenticatedContext,
    ) -> bool:
        if context_is_admin(context):
            return True
        if submission.assignment_id is not None:
            return submission.owner_user_id == context.user.id
        if submission.owner_team_id is None:
            return False
        return (
            await self._competitions.current_member(
                submission.owner_team_id,
                context.user.id,
            )
            is not None
        )

    async def get_submission(
        self,
        submission_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> SubmissionResponse:
        submission = await self._submissions.get_by_id(submission_id)
        if (
            submission is None
            or submission.latest_version_id is None
            or not await self._can_read_submission(submission, context)
        ):
            raise self._not_found()
        versions = await self._submissions.versions(submission.id)
        return SubmissionResponse(
            id=submission.id,
            assignment_id=submission.assignment_id,
            competition_task_id=submission.competition_task_id,
            owner_user_id=submission.owner_user_id,
            owner_team_id=submission.owner_team_id,
            latest_version_id=submission.latest_version_id,
            versions=[await self._version_response(version) for version in versions],
        )

    async def get_assignment_submission(
        self,
        assignment_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> SubmissionResponse:
        submission = await self._submissions.get_for_assignment_owner(
            assignment_id,
            context.user.id,
        )
        if submission is None:
            raise self._not_found()
        return await self.get_submission(submission.id, context=context)

    async def get_competition_submission(
        self,
        competition_id: UUID,
        task_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> SubmissionResponse:
        task = await self._competitions.get_task(
            task_id,
            competition_id=competition_id,
        )
        team = await self._competitions.team_for_user(
            competition_id,
            context.user.id,
        )
        if task is None or team is None:
            raise self._not_found()
        submission = await self._submissions.get_for_competition_team(
            task.id,
            team.id,
        )
        if submission is None:
            raise self._not_found()
        return await self.get_submission(submission.id, context=context)

    async def get_version(
        self,
        submission_id: UUID,
        version_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> SubmissionVersionResponse:
        submission = await self._submissions.get_by_id(submission_id)
        if submission is None or not await self._can_read_submission(submission, context):
            raise self._not_found()
        version = await self._submissions.get_version(
            version_id,
            submission_id=submission_id,
        )
        if version is None:
            raise self._not_found()
        return await self._version_response(version)

    async def put_feedback(
        self,
        submission_id: UUID,
        version_id: UUID,
        payload: FeedbackPutRequest,
        *,
        audit: SubmissionAuditContext,
    ) -> FeedbackResponse:
        submission = await self._submissions.get_by_id(submission_id)
        version = await self._submissions.get_version(
            version_id,
            submission_id=submission_id,
        )
        if submission is None or version is None:
            raise self._not_found()
        feedback = await self._submissions.feedback_for_version(
            version_id,
            for_update=True,
        )
        now = self._clock()
        if feedback is None:
            if payload.revision is not None:
                await self._session.rollback()
                raise ApplicationError(
                    status_code=409,
                    code="REVISION_CONFLICT",
                    message="评语尚不存在，请刷新后重试。",
                )
            feedback = Feedback(
                id=uuid7(),
                version_id=version_id,
                body_markdown=payload.body_markdown.strip(),
                body_html=render_markdown(payload.body_markdown),
                created_by=audit.actor.user.id,
                created_at=now,
                updated_at=now,
                revision=1,
            )
            self._submissions.add_feedback(feedback)
        else:
            if payload.revision != feedback.revision:
                await self._session.rollback()
                raise ApplicationError(
                    status_code=409,
                    code="REVISION_CONFLICT",
                    message="评语已被其他管理员修改，请刷新后重试。",
                )
            feedback.body_markdown = payload.body_markdown.strip()
            feedback.body_html = render_markdown(payload.body_markdown)
            feedback.revision += 1

        event_key = f"feedback:{feedback.id}:revision:{feedback.revision}"
        if submission.assignment_id is not None:
            assignment = await self._assignments.get_by_id(submission.assignment_id)
            title = assignment.title if assignment is not None else "作业"
            recipient_ids = (
                [submission.owner_user_id] if submission.owner_user_id is not None else []
            )
            target_url = f"/assignments/{submission.assignment_id}/submissions/{submission.id}"
        else:
            task = (
                await self._competitions.get_task(submission.competition_task_id)
                if submission.competition_task_id is not None
                else None
            )
            competition = (
                await self._competitions.get_competition(task.competition_id)
                if task is not None
                else None
            )
            if task is None or competition is None or submission.owner_team_id is None:
                await self._session.rollback()
                raise self._not_found()
            title = f"{competition.name} · {task.title}"
            recipient_ids = await self._competitions.current_member_ids(submission.owner_team_id)
            target_url = f"/competitions/{competition.id}/tasks/{task.id}"
        self._notifications.add_all(
            [
                StudentNotification(
                    id=uuid7(),
                    user_id=user_id,
                    notification_type="submission_feedback",
                    event_key=event_key,
                    title=f"收到新的私密评语：{title}",
                    target_type="submission",
                    target_id=submission.id,
                    target_url=target_url,
                    created_at=now,
                    read_at=None,
                )
                for user_id in recipient_ids
            ]
        )
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="submission.feedback_upsert",
            target_id=version.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={
                "submission_id": str(submission.id),
                "feedback_revision": feedback.revision,
                "body_present": True,
            },
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="评语状态发生并发冲突，请刷新后重试。",
            ) from exc
        await self._session.refresh(feedback)
        return self._feedback_response(feedback)
