from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assignments.models import (
    Assignment,
    AssignmentExcellentSubmission,
    AssignmentExtension,
)
from app.assignments.policy import can_submit_assignment
from app.assignments.repository import (
    AssignmentRepository,
    ExcellentSubmissionRecord,
    StudentAssignmentRecord,
)
from app.assignments.schemas import (
    AssignmentAdminPage,
    AssignmentAdminResponse,
    AssignmentAudience,
    AssignmentCreateRequest,
    AssignmentDetailResponse,
    AssignmentExtensionRequest,
    AssignmentExtensionResponse,
    AssignmentPage,
    AssignmentPatchRequest,
    AssignmentStatsResponse,
    AssignmentSubmissionAdminItem,
    AssignmentSubmissionAdminPage,
    AssignmentSubmissionSummary,
    AssignmentSummaryResponse,
    ExcellentAttachmentResponse,
    ExcellentSubmissionDetailResponse,
    ExcellentSubmissionSummaryResponse,
)
from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, context_is_admin
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.core.markdown import render_markdown
from app.notifications.models import OutboxJob, StudentNotification
from app.notifications.repository import OutboxRepository, StudentNotificationRepository
from app.submissions.repository import (
    AssignmentSubmissionRecord,
    SubmissionRepository,
)
from app.uploads.service import SAFE_EXTENSIONS
from app.users.audience import active_students_for_audience, validate_audience
from app.users.repository import UserRepository


@dataclass(frozen=True, slots=True)
class AssignmentAuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


class AssignmentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._assignments = AssignmentRepository(session)
        self._submissions = SubmissionRepository(session)
        self._users = UserRepository(session)
        self._notifications = StudentNotificationRepository(session)
        self._outbox = OutboxRepository(session)
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
    def _state_conflict(message: str, *, code: str = "STATE_CONFLICT") -> ApplicationError:
        return ApplicationError(
            status_code=409,
            code=code,
            message=message,
        )

    @staticmethod
    def _validate_extensions(extensions: list[str]) -> None:
        if any(extension not in SAFE_EXTENSIONS for extension in extensions):
            raise ApplicationError(
                status_code=415,
                code="FILE_TYPE_NOT_ALLOWED",
                message="作业附件扩展名必须是全局安全白名单的子集。",
            )

    async def _audience(self, assignment: Assignment) -> AssignmentAudience:
        cohort_ids, direction_ids = await self._assignments.audience_ids(assignment.id)
        return AssignmentAudience(
            all_students=assignment.all_students,
            cohort_ids=sorted(cohort_ids, key=str),
            direction_ids=sorted(direction_ids, key=str),
            match=assignment.audience_match,
        )

    def _add_audit(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        assignment_id: UUID,
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
                target_type="assignment",
                target_id=assignment_id,
                request_id=request_id,
                ip_prefix=ip_prefix,
                result="success",
                change_summary=change_summary,
                created_at=now,
            )
        )

    def _job(
        self,
        *,
        assignment: Assignment,
        job_type: str,
        event_key: str,
        available_at: datetime,
        now: datetime,
    ) -> OutboxJob:
        return OutboxJob(
            id=uuid7(),
            job_type=job_type,
            event_key=event_key,
            payload={"assignment_id": str(assignment.id)},
            secret_payload_ciphertext=None,
            status="pending",
            available_at=available_at,
            attempt_count=0,
            max_attempts=8,
            locked_by=None,
            locked_at=None,
            last_error_code=None,
            last_error_summary=None,
            created_at=now,
            sent_at=None,
        )

    async def _upsert_job(
        self,
        *,
        assignment: Assignment,
        job_type: str,
        event_key: str,
        available_at: datetime,
        now: datetime,
    ) -> OutboxJob:
        job = await self._outbox.get_by_event_key(event_key)
        if job is None:
            job = self._job(
                assignment=assignment,
                job_type=job_type,
                event_key=event_key,
                available_at=available_at,
                now=now,
            )
            self._outbox.add(job)
            return job
        job.job_type = job_type
        job.payload = {"assignment_id": str(assignment.id)}
        job.status = "pending"
        job.available_at = available_at
        job.attempt_count = 0
        job.locked_by = None
        job.locked_at = None
        job.last_error_code = None
        job.last_error_summary = None
        job.sent_at = None
        return job

    async def _admin_response(self, assignment: Assignment) -> AssignmentAdminResponse:
        audience = await self._audience(assignment)
        estimated = len(await active_students_for_audience(self._session, audience))
        actual = await self._assignments.actual_audience_count(assignment.id)
        stats = await self._assignments.stats(assignment.id)
        return AssignmentAdminResponse(
            id=assignment.id,
            title=assignment.title,
            description_markdown=assignment.description_markdown,
            description_html=assignment.description_html,
            training_url=assignment.training_url,
            submission_instructions=assignment.submission_instructions,
            status=assignment.status,
            audience=audience,
            allowed_extensions=list(assignment.allowed_extensions),
            max_total_bytes=assignment.max_total_bytes,
            publish_at=assignment.publish_at,
            published_at=assignment.published_at,
            deadline=assignment.deadline,
            closed_at=assignment.closed_at,
            archived_at=assignment.archived_at,
            estimated_recipient_count=estimated,
            actual_recipient_count=actual,
            stats=AssignmentStatsResponse(
                target_count=stats.target_count,
                submitted_count=stats.submitted_count,
                unsubmitted_count=max(0, stats.target_count - stats.submitted_count),
                feedback_submission_count=stats.feedback_submission_count,
                last_submitted_at=stats.last_submitted_at,
            ),
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
            revision=assignment.revision,
        )

    async def create_draft(
        self,
        payload: AssignmentCreateRequest,
        *,
        audit: AssignmentAuditContext,
    ) -> AssignmentAdminResponse:
        await validate_audience(self._session, payload.audience)
        self._validate_extensions(payload.allowed_extensions)
        now = self._clock()
        assignment = Assignment(
            id=uuid7(),
            title=payload.title.strip(),
            description_markdown=payload.description_markdown.strip(),
            description_html=render_markdown(payload.description_markdown),
            training_url=payload.training_url,
            submission_instructions=payload.submission_instructions.strip(),
            status="draft",
            all_students=payload.audience.all_students,
            audience_match=payload.audience.match,
            allowed_extensions=payload.allowed_extensions,
            max_total_bytes=payload.max_total_bytes,
            publish_at=payload.publish_at,
            published_at=None,
            deadline=payload.deadline,
            created_by=audit.actor.user.id,
            updated_by=audit.actor.user.id,
            closed_at=None,
            archived_at=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._assignments.add(assignment)
        await self._session.flush()
        await self._assignments.replace_audience(
            assignment.id,
            cohort_ids=payload.audience.cohort_ids,
            direction_ids=payload.audience.direction_ids,
        )
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="assignment.create",
            assignment_id=assignment.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={
                "all_students": assignment.all_students,
                "allowed_extension_count": len(assignment.allowed_extensions),
                "max_total_bytes": assignment.max_total_bytes,
            },
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._state_conflict("作业创建发生并发冲突，请重试。") from exc
        await self._session.refresh(assignment)
        return await self._admin_response(assignment)

    async def get_admin(self, assignment_id: UUID) -> AssignmentAdminResponse:
        assignment = await self._assignments.get_by_id(assignment_id)
        if assignment is None:
            raise self._not_found()
        return await self._admin_response(assignment)

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        query: str | None,
    ) -> AssignmentAdminPage:
        items, total = await self._assignments.list_admin(
            page=page,
            page_size=page_size,
            status=status,
            query=query,
        )
        return AssignmentAdminPage(
            items=[await self._admin_response(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def patch(
        self,
        assignment_id: UUID,
        payload: AssignmentPatchRequest,
        *,
        audit: AssignmentAuditContext,
    ) -> AssignmentAdminResponse:
        await validate_audience(self._session, payload.audience)
        self._validate_extensions(payload.allowed_extensions)
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None:
            await self._session.rollback()
            raise self._not_found()
        if assignment.status == "archived":
            await self._session.rollback()
            raise self._state_conflict("归档作业不能编辑。")
        if assignment.revision != payload.revision:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="REVISION_CONFLICT",
                message="作业已被其他管理员修改，请刷新后重试。",
            )

        current_audience = await self._audience(assignment)
        published = assignment.status in {"published", "closed"}
        if published and (
            payload.audience != current_audience
            or payload.allowed_extensions != list(assignment.allowed_extensions)
            or payload.max_total_bytes != assignment.max_total_bytes
            or payload.publish_at != assignment.publish_at
        ):
            await self._session.rollback()
            raise self._state_conflict("发布后不能修改受众、发布时间或附件规则。")
        if published and payload.deadline < assignment.deadline:
            await self._session.rollback()
            raise self._state_conflict("发布后的作业截止时间只能延长。")

        old_deadline = assignment.deadline
        now = self._clock()
        changed_fields = [
            field
            for field, before, after in (
                ("title", assignment.title, payload.title.strip()),
                (
                    "description_markdown",
                    assignment.description_markdown,
                    payload.description_markdown.strip(),
                ),
                ("training_url", assignment.training_url, payload.training_url),
                (
                    "submission_instructions",
                    assignment.submission_instructions,
                    payload.submission_instructions.strip(),
                ),
                ("publish_at", assignment.publish_at, payload.publish_at),
                ("deadline", assignment.deadline, payload.deadline),
            )
            if before != after
        ]
        assignment.title = payload.title.strip()
        assignment.description_markdown = payload.description_markdown.strip()
        assignment.description_html = render_markdown(payload.description_markdown)
        assignment.training_url = payload.training_url
        assignment.submission_instructions = payload.submission_instructions.strip()
        assignment.publish_at = payload.publish_at
        assignment.deadline = payload.deadline
        assignment.updated_by = audit.actor.user.id
        assignment.revision += 1

        if assignment.status == "draft":
            assignment.all_students = payload.audience.all_students
            assignment.audience_match = payload.audience.match
            assignment.allowed_extensions = payload.allowed_extensions
            assignment.max_total_bytes = payload.max_total_bytes
            await self._assignments.replace_audience(
                assignment.id,
                cohort_ids=payload.audience.cohort_ids,
                direction_ids=payload.audience.direction_ids,
            )
            scheduled = await self._outbox.get_by_event_key(f"assignment:{assignment.id}:publish")
            if scheduled is not None:
                await self._upsert_job(
                    assignment=assignment,
                    job_type="publish_assignment",
                    event_key=f"assignment:{assignment.id}:publish",
                    available_at=assignment.publish_at,
                    now=now,
                )
        elif payload.deadline > old_deadline:
            if (
                assignment.status == "closed"
                and assignment.closed_at is not None
                and assignment.closed_at >= old_deadline
            ):
                assignment.status = "published"
                assignment.closed_at = None
            await self._upsert_job(
                assignment=assignment,
                job_type="close_assignment",
                event_key=f"assignment:{assignment.id}:close",
                available_at=assignment.deadline,
                now=now,
            )

        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="assignment.update",
            assignment_id=assignment.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={"changed_fields": changed_fields},
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._state_conflict("作业状态发生并发冲突，请刷新后重试。") from exc
        await self._session.refresh(assignment)
        return await self._admin_response(assignment)

    async def _apply_publish(
        self,
        assignment: Assignment,
        *,
        actor_user_id: UUID | None,
        request_id: str,
        ip_prefix: str,
        now: datetime,
    ) -> None:
        audience = await self._audience(assignment)
        users = await active_students_for_audience(self._session, audience)
        self._assignments.add_audience_snapshot(
            assignment_id=assignment.id,
            users=users,
            created_at=now,
        )
        assignment.status = "published"
        assignment.published_at = now
        assignment.updated_by = actor_user_id
        assignment.revision += 1
        await self._upsert_job(
            assignment=assignment,
            job_type="close_assignment",
            event_key=f"assignment:{assignment.id}:close",
            available_at=assignment.deadline,
            now=now,
        )
        self._add_audit(
            actor_user_id=actor_user_id,
            action="assignment.publish",
            assignment_id=assignment.id,
            request_id=request_id,
            ip_prefix=ip_prefix,
            change_summary={"recipient_count": len(users)},
            now=now,
        )

    async def publish(
        self,
        assignment_id: UUID,
        *,
        audit: AssignmentAuditContext,
    ) -> AssignmentAdminResponse:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None:
            await self._session.rollback()
            raise self._not_found()
        if assignment.status in {"published", "closed"}:
            await self._session.commit()
            return await self._admin_response(assignment)
        if assignment.status == "archived":
            await self._session.rollback()
            raise self._state_conflict("归档作业不能发布。")
        now = self._clock()
        if assignment.deadline <= now:
            await self._session.rollback()
            raise self._state_conflict("截止时间已过，不能发布作业。")
        if assignment.publish_at > now:
            existing = await self._outbox.get_by_event_key(f"assignment:{assignment.id}:publish")
            if existing is None or existing.status in {"sent", "dead"}:
                await self._upsert_job(
                    assignment=assignment,
                    job_type="publish_assignment",
                    event_key=f"assignment:{assignment.id}:publish",
                    available_at=assignment.publish_at,
                    now=now,
                )
                assignment.revision += 1
                self._add_audit(
                    actor_user_id=audit.actor.user.id,
                    action="assignment.schedule",
                    assignment_id=assignment.id,
                    request_id=audit.request_id,
                    ip_prefix=audit.ip_prefix,
                    change_summary={"publish_at": assignment.publish_at.isoformat()},
                    now=now,
                )
        else:
            await self._apply_publish(
                assignment,
                actor_user_id=audit.actor.user.id,
                request_id=audit.request_id,
                ip_prefix=audit.ip_prefix,
                now=now,
            )
        await self._session.commit()
        await self._session.refresh(assignment)
        return await self._admin_response(assignment)

    async def publish_scheduled(self, assignment_id: UUID, *, job_id: UUID) -> None:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None or assignment.status != "draft":
            await self._session.commit()
            return
        now = self._clock()
        if assignment.publish_at > now or assignment.deadline <= now:
            await self._session.commit()
            return
        await self._apply_publish(
            assignment,
            actor_user_id=assignment.created_by,
            request_id=f"worker:{job_id}",
            ip_prefix="worker",
            now=now,
        )
        await self._session.commit()

    async def close(
        self,
        assignment_id: UUID,
        *,
        audit: AssignmentAuditContext,
    ) -> AssignmentAdminResponse:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None:
            await self._session.rollback()
            raise self._not_found()
        if assignment.status == "closed":
            await self._session.commit()
            return await self._admin_response(assignment)
        if assignment.status != "published":
            await self._session.rollback()
            raise self._state_conflict("只有已发布作业可以提前关闭。")
        now = self._clock()
        if now >= assignment.deadline:
            assignment.closed_at = assignment.deadline
        else:
            assignment.closed_at = now
        assignment.status = "closed"
        assignment.updated_by = audit.actor.user.id
        assignment.revision += 1
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="assignment.close",
            assignment_id=assignment.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={"early": now < assignment.deadline},
            now=now,
        )
        await self._session.commit()
        await self._session.refresh(assignment)
        return await self._admin_response(assignment)

    async def close_scheduled(self, assignment_id: UUID, *, job_id: UUID) -> None:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None or assignment.status != "published":
            await self._session.commit()
            return
        now = self._clock()
        if assignment.deadline > now:
            await self._session.commit()
            return
        assignment.status = "closed"
        assignment.closed_at = assignment.deadline
        assignment.revision += 1
        self._add_audit(
            actor_user_id=assignment.created_by,
            action="assignment.close_automatic",
            assignment_id=assignment.id,
            request_id=f"worker:{job_id}",
            ip_prefix="worker",
            change_summary={},
            now=now,
        )
        await self._session.commit()

    def _archive_record(
        self,
        assignment: Assignment,
        *,
        audit: AssignmentAuditContext,
        action: str,
        deletion_mode: str | None = None,
    ) -> None:
        now = self._clock()
        assignment.status = "archived"
        assignment.archived_at = now
        if deletion_mode is not None:
            assignment.deleted_at = now
        assignment.closed_at = assignment.closed_at or now
        assignment.updated_by = audit.actor.user.id
        assignment.revision += 1
        change_summary: dict[str, object] = {"status": "archived"}
        if deletion_mode is not None:
            change_summary["deletion_mode"] = deletion_mode
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action=action,
            assignment_id=assignment.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary=change_summary,
            now=now,
        )

    async def archive(
        self,
        assignment_id: UUID,
        *,
        audit: AssignmentAuditContext,
    ) -> AssignmentAdminResponse:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None:
            await self._session.rollback()
            raise self._not_found()
        if assignment.status == "archived":
            await self._session.commit()
            return await self._admin_response(assignment)
        if assignment.status not in {"published", "closed"}:
            await self._session.rollback()
            raise self._state_conflict("草稿作业不能归档。")
        self._archive_record(
            assignment,
            audit=audit,
            action="assignment.archive",
        )
        await self._session.commit()
        await self._session.refresh(assignment)
        return await self._admin_response(assignment)

    async def remove(
        self,
        assignment_id: UUID,
        *,
        audit: AssignmentAuditContext,
    ) -> None:
        assignment = await self._assignments.get_by_id(
            assignment_id,
            for_update=True,
            include_deleted=True,
        )
        if assignment is None:
            await self._session.rollback()
            raise self._not_found()
        if assignment.deleted_at is not None:
            await self._session.commit()
            return
        if assignment.status == "archived":
            now = self._clock()
            assignment.deleted_at = now
            assignment.updated_by = audit.actor.user.id
            assignment.revision += 1
            self._add_audit(
                actor_user_id=audit.actor.user.id,
                action="assignment.delete",
                assignment_id=assignment.id,
                request_id=audit.request_id,
                ip_prefix=audit.ip_prefix,
                change_summary={
                    "previous_status": "archived",
                    "deletion_mode": "archive",
                },
                now=now,
            )
        elif assignment.status == "draft":
            now = self._clock()
            await self._outbox.delete_active_by_event_key(f"assignment:{assignment.id}:publish")
            await self._assignments.delete(assignment)
            self._add_audit(
                actor_user_id=audit.actor.user.id,
                action="assignment.delete",
                assignment_id=assignment.id,
                request_id=audit.request_id,
                ip_prefix=audit.ip_prefix,
                change_summary={
                    "previous_status": "draft",
                    "deletion_mode": "physical",
                },
                now=now,
            )
        else:
            self._archive_record(
                assignment,
                audit=audit,
                action="assignment.delete",
                deletion_mode="archive",
            )
        await self._session.commit()

    @staticmethod
    def _can_submit(
        assignment: Assignment,
        extension: AssignmentExtension | None,
        now: datetime,
    ) -> bool:
        return can_submit_assignment(assignment, extension, now)

    def _student_summary(
        self,
        record: StudentAssignmentRecord,
        *,
        submission_record: AssignmentSubmissionRecord | None,
    ) -> AssignmentSummaryResponse:
        assignment = record.assignment
        latest_summary: AssignmentSubmissionSummary | None = None
        if submission_record is not None and submission_record.latest_version is not None:
            submission = submission_record.submission
            version = submission_record.latest_version
            latest_summary = AssignmentSubmissionSummary(
                submission_id=submission.id,
                latest_version_id=version.id,
                latest_version_number=version.version_number,
                submitted_at=version.submitted_at,
                has_feedback=submission_record.has_feedback,
            )
        effective_deadline = (
            record.extension.extended_deadline
            if record.extension is not None
            else assignment.deadline
        )
        return AssignmentSummaryResponse(
            id=assignment.id,
            title=assignment.title,
            status=assignment.status,
            public_deadline=assignment.deadline,
            effective_deadline=effective_deadline,
            has_personal_extension=record.extension is not None,
            can_submit=self._can_submit(assignment, record.extension, self._clock()),
            latest_submission=latest_summary,
        )

    async def list_student(
        self,
        *,
        context: AuthenticatedContext,
        page: int,
        page_size: int,
        status: str | None,
        query: str | None,
    ) -> AssignmentPage:
        records, total = await self._assignments.list_for_student(
            user_id=context.user.id,
            preview_user=context.user if getattr(context, "is_student_view", False) else None,
            page=page,
            page_size=page_size,
            status=status,
            query=query,
            now=self._clock(),
        )
        submission_records = await self._submissions.assignment_summaries_for_user(
            assignment_ids=[record.assignment.id for record in records],
            owner_user_id=context.user.id,
        )
        return AssignmentPage(
            items=[
                self._student_summary(
                    record,
                    submission_record=submission_records.get(record.assignment.id),
                )
                for record in records
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def _excellent_summaries(
        self,
        assignment_id: UUID,
    ) -> list[ExcellentSubmissionSummaryResponse]:
        return [
            ExcellentSubmissionSummaryResponse(
                version_id=record.version.id,
                author_name=record.author.full_name,
                version_number=record.version.version_number,
                marked_at=record.marker.marked_at,
            )
            for record in await self._assignments.excellent_records(assignment_id)
        ]

    async def get_student(
        self,
        assignment_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> AssignmentDetailResponse:
        record = await self._assignments.get_for_student(
            assignment_id,
            context.user.id,
            preview_user=context.user if getattr(context, "is_student_view", False) else None,
        )
        if record is None:
            raise self._not_found()
        submission_records = await self._submissions.assignment_summaries_for_user(
            assignment_ids=[record.assignment.id],
            owner_user_id=context.user.id,
        )
        summary = self._student_summary(
            record,
            submission_record=submission_records.get(record.assignment.id),
        )
        return AssignmentDetailResponse(
            **summary.model_dump(),
            description_html=record.assignment.description_html,
            training_url=record.assignment.training_url,
            submission_instructions=record.assignment.submission_instructions,
            allowed_extensions=list(record.assignment.allowed_extensions),
            max_total_bytes=record.assignment.max_total_bytes,
            excellent_submissions=await self._excellent_summaries(assignment_id),
        )

    async def put_extension(
        self,
        assignment_id: UUID,
        user_id: UUID,
        payload: AssignmentExtensionRequest,
        *,
        audit: AssignmentAuditContext,
    ) -> AssignmentExtensionResponse:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None or assignment.status == "draft":
            await self._session.rollback()
            raise self._not_found()
        if assignment.status == "archived":
            await self._session.rollback()
            raise self._state_conflict("归档作业不能设置延期。")
        if not await self._assignments.is_audience_user(assignment_id, user_id):
            await self._session.rollback()
            raise self._not_found()
        if payload.extended_deadline <= assignment.deadline:
            await self._session.rollback()
            raise ApplicationError(
                status_code=422,
                code="BUSINESS_RULE_VIOLATION",
                message="个人延期必须晚于公共截止时间。",
            )
        user = await self._users.get_by_id(user_id)
        if user is None or user.role != "student" or user.status != "active":
            await self._session.rollback()
            raise self._not_found()

        now = self._clock()
        extension = await self._assignments.get_extension(
            assignment_id,
            user_id,
            for_update=True,
        )
        if extension is None:
            extension = AssignmentExtension(
                assignment_id=assignment_id,
                user_id=user_id,
                extended_deadline=payload.extended_deadline,
                reason=payload.reason.strip(),
                granted_by=audit.actor.user.id,
                created_at=now,
                updated_at=now,
                revision=1,
            )
            self._assignments.add_extension(extension)
        else:
            extension.extended_deadline = payload.extended_deadline
            extension.reason = payload.reason.strip()
            extension.granted_by = audit.actor.user.id
            extension.revision += 1

        event_key = f"assignment:{assignment_id}:extension:{user_id}:{extension.revision}"
        self._notifications.add_all(
            [
                StudentNotification(
                    id=uuid7(),
                    user_id=user_id,
                    notification_type="assignment_extension",
                    event_key=event_key,
                    title=f"作业延期：{assignment.title}",
                    target_type="assignment",
                    target_id=assignment.id,
                    target_url=f"/assignments/{assignment.id}",
                    created_at=now,
                    read_at=None,
                )
            ]
        )
        self._outbox.add(
            OutboxJob(
                id=uuid7(),
                job_type="assignment_extension_email",
                event_key=f"{event_key}:email",
                payload={
                    "recipient": user.email,
                    "full_name": user.full_name,
                    "assignment_id": str(assignment.id),
                    "title": assignment.title,
                    "extended_deadline": payload.extended_deadline.isoformat(),
                    "target_url": f"/assignments/{assignment.id}",
                },
                secret_payload_ciphertext=None,
                status="pending",
                available_at=now,
                attempt_count=0,
                max_attempts=8,
                locked_by=None,
                locked_at=None,
                last_error_code=None,
                last_error_summary=None,
                created_at=now,
                sent_at=None,
            )
        )
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="assignment.extension_upsert",
            assignment_id=assignment.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={
                "user_id": str(user_id),
                "extended_deadline": payload.extended_deadline.isoformat(),
                "reason_present": True,
            },
            now=now,
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise self._state_conflict("延期状态发生并发冲突，请刷新后重试。") from exc
        await self._session.refresh(extension)
        return AssignmentExtensionResponse(
            assignment_id=extension.assignment_id,
            user_id=extension.user_id,
            extended_deadline=extension.extended_deadline,
            reason=extension.reason,
            granted_by=extension.granted_by,
            created_at=extension.created_at,
            updated_at=extension.updated_at,
            revision=extension.revision,
        )

    async def delete_extension(
        self,
        assignment_id: UUID,
        user_id: UUID,
        *,
        audit: AssignmentAuditContext,
    ) -> None:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        extension = await self._assignments.get_extension(
            assignment_id,
            user_id,
            for_update=True,
        )
        if assignment is None or extension is None:
            await self._session.rollback()
            raise self._not_found()
        now = self._clock()
        if now >= assignment.deadline:
            await self._session.rollback()
            raise self._state_conflict("公共截止后不能移除个人延期。")
        if await self._submissions.has_version_after(
            assignment_id=assignment_id,
            owner_user_id=user_id,
            after=assignment.deadline,
        ):
            await self._session.rollback()
            raise self._state_conflict("该延期已被正式提交使用，不能移除。")
        await self._assignments.delete_extension(assignment_id, user_id)
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="assignment.extension_delete",
            assignment_id=assignment.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={"user_id": str(user_id)},
            now=now,
        )
        await self._session.commit()

    async def list_submissions_admin(
        self,
        assignment_id: UUID,
        *,
        page: int,
        page_size: int,
        cohort_id: UUID | None,
        direction_id: UUID | None,
        submission_status: str | None,
        feedback_status: str | None,
    ) -> AssignmentSubmissionAdminPage:
        assignment = await self._assignments.get_by_id(assignment_id)
        if assignment is None:
            raise self._not_found()
        records, total = await self._assignments.submissions_for_admin(
            assignment_id,
            page=page,
            page_size=page_size,
            cohort_id=cohort_id,
            direction_id=direction_id,
            submission_status=submission_status,
            feedback_status=feedback_status,
        )
        return AssignmentSubmissionAdminPage(
            items=[
                AssignmentSubmissionAdminItem(
                    user_id=record.user.id,
                    full_name=record.user.full_name,
                    student_number=record.user.student_number,
                    cohort_id=record.user.cohort_id,
                    direction_id=record.user.direction_id,
                    submission_id=(record.submission.id if record.submission is not None else None),
                    latest_version_number=(
                        record.latest_version.version_number
                        if record.latest_version is not None
                        else None
                    ),
                    last_submitted_at=(
                        record.latest_version.submitted_at
                        if record.latest_version is not None
                        else None
                    ),
                    has_feedback=record.has_feedback,
                )
                for record in records
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def mark_excellent(
        self,
        assignment_id: UUID,
        version_id: UUID,
        *,
        audit: AssignmentAuditContext,
    ) -> ExcellentSubmissionSummaryResponse:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None or assignment.status == "draft":
            await self._session.rollback()
            raise self._not_found()
        if not await self._submissions.version_belongs_to_assignment(
            version_id=version_id,
            assignment_id=assignment_id,
        ):
            await self._session.rollback()
            raise self._state_conflict("只能标记当前作业的个人提交版本。")
        existing = await self._assignments.get_excellent_marker(
            assignment_id,
            version_id,
            for_update=True,
        )
        if existing is None:
            now = self._clock()
            self._assignments.add_excellent_marker(
                AssignmentExcellentSubmission(
                    assignment_id=assignment_id,
                    version_id=version_id,
                    marked_by=audit.actor.user.id,
                    marked_at=now,
                )
            )
            self._add_audit(
                actor_user_id=audit.actor.user.id,
                action="assignment.excellent_mark",
                assignment_id=assignment.id,
                request_id=audit.request_id,
                ip_prefix=audit.ip_prefix,
                change_summary={"version_id": str(version_id)},
                now=now,
            )
            try:
                await self._session.commit()
            except IntegrityError as exc:
                await self._session.rollback()
                raise self._state_conflict("该版本已经被标记为优秀作业。") from exc
        else:
            await self._session.commit()
        record = await self._assignments.excellent_record(assignment_id, version_id)
        if record is None:
            raise self._not_found()
        return ExcellentSubmissionSummaryResponse(
            version_id=record.version.id,
            author_name=record.author.full_name,
            version_number=record.version.version_number,
            marked_at=record.marker.marked_at,
        )

    async def unmark_excellent(
        self,
        assignment_id: UUID,
        version_id: UUID,
        *,
        audit: AssignmentAuditContext,
    ) -> None:
        marker = await self._assignments.get_excellent_marker(
            assignment_id,
            version_id,
            for_update=True,
        )
        if marker is None:
            await self._session.rollback()
            raise self._not_found()
        now = self._clock()
        await self._assignments.delete_excellent_marker(assignment_id, version_id)
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="assignment.excellent_unmark",
            assignment_id=assignment_id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={"version_id": str(version_id)},
            now=now,
        )
        await self._session.commit()

    async def list_excellent(
        self,
        assignment_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> list[ExcellentSubmissionSummaryResponse]:
        if not context_is_admin(context) and not await self._assignments.is_audience_user(
            assignment_id,
            context.user.id,
            preview_user=context.user if getattr(context, "is_student_view", False) else None,
        ):
            raise self._not_found()
        assignment = await self._assignments.get_by_id(assignment_id)
        if (
            assignment is None
            or assignment.status == "draft"
            or (assignment.status == "archived" and not context_is_admin(context))
        ):
            raise self._not_found()
        return await self._excellent_summaries(assignment_id)

    async def get_excellent(
        self,
        assignment_id: UUID,
        version_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> ExcellentSubmissionDetailResponse:
        if not context_is_admin(context) and not await self._assignments.is_audience_user(
            assignment_id,
            context.user.id,
            preview_user=context.user if getattr(context, "is_student_view", False) else None,
        ):
            raise self._not_found()
        assignment = await self._assignments.get_by_id(assignment_id)
        record: ExcellentSubmissionRecord | None = await self._assignments.excellent_record(
            assignment_id, version_id
        )
        if (
            assignment is None
            or record is None
            or assignment.status == "draft"
            or (assignment.status == "archived" and not context_is_admin(context))
        ):
            raise self._not_found()
        files = await self._submissions.files_for_version(version_id)
        return ExcellentSubmissionDetailResponse(
            assignment_id=assignment.id,
            assignment_title=assignment.title,
            version_id=record.version.id,
            version_number=record.version.version_number,
            author_name=record.author.full_name,
            text_html=record.version.text_html,
            external_url=record.version.external_url,
            submitted_at=record.version.submitted_at,
            marked_at=record.marker.marked_at,
            attachments=[
                ExcellentAttachmentResponse(
                    id=file.id,
                    file_name=file.original_name,
                    size_bytes=file.size_bytes,
                    media_type=file.detected_media_type or file.declared_media_type,
                    sha256=file.sha256,
                )
                for file in files
            ],
        )


class ScheduledAssignmentProcessor:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._factory = factory
        self._clock = clock

    async def publish(self, assignment_id: UUID, job_id: UUID) -> None:
        async with self._factory() as session:
            await AssignmentService(session, clock=self._clock).publish_scheduled(
                assignment_id,
                job_id=job_id,
            )

    async def close(self, assignment_id: UUID, job_id: UUID) -> None:
        async with self._factory() as session:
            await AssignmentService(session, clock=self._clock).close_scheduled(
                assignment_id,
                job_id=job_id,
            )
