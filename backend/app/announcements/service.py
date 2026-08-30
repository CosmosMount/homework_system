from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.announcements.models import Announcement
from app.announcements.repository import AnnouncementRepository
from app.announcements.schemas import (
    AnnouncementAdminPage,
    AnnouncementAdminResponse,
    AnnouncementAttachmentResponse,
    AnnouncementAudience,
    AnnouncementCreateRequest,
    AnnouncementDetailResponse,
    AnnouncementPage,
    AnnouncementPatchRequest,
    AnnouncementSummaryResponse,
    DashboardAssignmentItem,
    DashboardCompetitionItem,
    DashboardResponse,
    DashboardUnreadCounts,
    DashboardUserResponse,
)
from app.assignments.repository import AssignmentRepository
from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.service import AuthenticatedContext, context_effective_role
from app.competitions.repository import CompetitionRepository
from app.core.errors import ApplicationError, ErrorDetail
from app.core.identifiers import uuid7
from app.core.markdown import render_markdown
from app.notifications.models import OutboxJob, StudentNotification
from app.notifications.repository import OutboxRepository, StudentNotificationRepository
from app.uploads.models import StoredFile
from app.uploads.repository import UploadRepository
from app.users.models import User


@dataclass(frozen=True, slots=True)
class AnnouncementAuditContext:
    actor: AuthenticatedContext
    request_id: str
    ip_prefix: str


class AnnouncementService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._announcements = AnnouncementRepository(session)
        self._uploads = UploadRepository(session)
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
    def _state_conflict(message: str) -> ApplicationError:
        return ApplicationError(
            status_code=409,
            code="STATE_CONFLICT",
            message=message,
        )

    @staticmethod
    def _validate_datetime(value: datetime | None, field: str) -> None:
        if value is not None and value.tzinfo is None:
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="请求参数不符合要求。",
                details=[ErrorDetail(field=field, reason="TIMEZONE_REQUIRED")],
            )

    async def _validate_audience(self, audience: AnnouncementAudience) -> None:
        cohort_ids = set(audience.cohort_ids)
        direction_ids = set(audience.direction_ids)
        if await self._announcements.existing_cohort_ids(audience.cohort_ids) != cohort_ids:
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="受众届次不存在。",
                details=[ErrorDetail(field="audience.cohort_ids", reason="RESOURCE_NOT_FOUND")],
            )
        if (
            await self._announcements.existing_direction_ids(audience.direction_ids)
            != direction_ids
        ):
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="受众方向不存在。",
                details=[
                    ErrorDetail(
                        field="audience.direction_ids",
                        reason="RESOURCE_NOT_FOUND",
                    )
                ],
            )

    @staticmethod
    def _audience_matches(
        announcement: Announcement,
        user: User,
        cohort_ids: set[UUID],
        direction_ids: set[UUID],
    ) -> bool:
        if announcement.all_students:
            return True
        cohort_matches = user.cohort_id is not None and user.cohort_id in cohort_ids
        direction_matches = user.direction_id is not None and user.direction_id in direction_ids
        if announcement.audience_match == "union":
            return cohort_matches or direction_matches
        return (
            bool(cohort_ids or direction_ids)
            and (not cohort_ids or cohort_matches)
            and (not direction_ids or direction_matches)
        )

    async def _validate_and_order_files(
        self,
        *,
        announcement_id: UUID,
        actor_user_id: UUID,
        file_ids: Sequence[UUID],
    ) -> list[StoredFile]:
        if not file_ids:
            return []
        stored_files = await self._uploads.get_files(file_ids, for_update=True)
        by_id = {stored_file.id: stored_file for stored_file in stored_files}
        if set(by_id) != set(file_ids):
            raise self._not_found()
        ordered = [by_id[file_id] for file_id in file_ids]
        for stored_file in ordered:
            if (
                stored_file.owner_user_id != actor_user_id
                or stored_file.purpose != "announcement_attachment"
                or stored_file.status != "available"
                or stored_file.deleted_at is not None
            ):
                raise ApplicationError(
                    status_code=409,
                    code="FILE_NOT_AVAILABLE",
                    message="附件尚未完成校验或不能用于当前通知。",
                )
            upload_session = await self._uploads.get_session_by_file(stored_file.id)
            if upload_session is None or upload_session.context_id != announcement_id:
                raise ApplicationError(
                    status_code=409,
                    code="FILE_CONTEXT_MISMATCH",
                    message="附件不属于当前通知草稿。",
                )
            bound_announcement_id = await self._uploads.bound_announcement_id(stored_file.id)
            if bound_announcement_id is not None and bound_announcement_id != announcement_id:
                raise ApplicationError(
                    status_code=409,
                    code="FILE_ALREADY_BOUND",
                    message="附件已经绑定其他通知。",
                )
        return ordered

    def _add_audit(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        announcement_id: UUID,
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
                target_type="announcement",
                target_id=announcement_id,
                request_id=request_id,
                ip_prefix=ip_prefix,
                result="success",
                change_summary=change_summary,
                created_at=now,
            )
        )

    async def _admin_response(
        self,
        announcement: Announcement,
    ) -> AnnouncementAdminResponse:
        cohort_ids, direction_ids = await self._announcements.audience_ids(announcement.id)
        file_ids = await self._announcements.attachment_file_ids(announcement.id)
        recipient_count = len(await self._announcements.audience_users(announcement))
        actual_count = await self._announcements.published_recipient_count(announcement.id)
        return AnnouncementAdminResponse(
            id=announcement.id,
            title=announcement.title,
            summary=announcement.summary,
            body_markdown=announcement.body_markdown,
            body_html=announcement.body_html,
            status=announcement.status,
            audience=AnnouncementAudience(
                all_students=announcement.all_students,
                cohort_ids=sorted(cohort_ids, key=str),
                direction_ids=sorted(direction_ids, key=str),
                match=announcement.audience_match,
            ),
            attachment_file_ids=file_ids,
            publish_at=announcement.publish_at,
            published_at=announcement.published_at,
            pinned_until=announcement.pinned_until,
            send_email=announcement.send_email,
            archived_at=announcement.archived_at,
            estimated_recipient_count=recipient_count,
            actual_recipient_count=actual_count,
            created_at=announcement.created_at,
            updated_at=announcement.updated_at,
            revision=announcement.revision,
        )

    async def create_draft(
        self,
        payload: AnnouncementCreateRequest,
        *,
        audit: AnnouncementAuditContext,
    ) -> AnnouncementAdminResponse:
        await self._validate_audience(payload.audience)
        self._validate_datetime(payload.publish_at, "publish_at")
        self._validate_datetime(payload.pinned_until, "pinned_until")
        now = self._clock()
        announcement = Announcement(
            id=uuid7(),
            title=payload.title.strip(),
            summary=payload.summary.strip(),
            body_markdown=payload.body_markdown.strip(),
            body_html=render_markdown(payload.body_markdown),
            status="draft",
            all_students=payload.audience.all_students,
            audience_match=payload.audience.match,
            publish_at=payload.publish_at,
            published_at=None,
            pinned_until=payload.pinned_until,
            send_email=payload.send_email,
            created_by=audit.actor.user.id,
            updated_by=audit.actor.user.id,
            archived_at=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        self._announcements.add(announcement)
        await self._announcements.replace_audience(
            announcement.id,
            cohort_ids=payload.audience.cohort_ids,
            direction_ids=payload.audience.direction_ids,
        )
        await self._validate_and_order_files(
            announcement_id=announcement.id,
            actor_user_id=audit.actor.user.id,
            file_ids=payload.attachment_file_ids,
        )
        await self._announcements.replace_files(
            announcement.id,
            payload.attachment_file_ids,
        )
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="announcement.create",
            announcement_id=announcement.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={
                "status": "draft",
                "all_students": payload.audience.all_students,
                "attachment_count": len(payload.attachment_file_ids),
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
                message="通知草稿或附件状态发生冲突，请刷新后重试。",
            ) from exc
        await self._session.refresh(announcement)
        return await self._admin_response(announcement)

    async def get_admin(self, announcement_id: UUID) -> AnnouncementAdminResponse:
        announcement = await self._announcements.get_by_id(announcement_id)
        if announcement is None:
            raise self._not_found()
        return await self._admin_response(announcement)

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        query: str | None,
    ) -> AnnouncementAdminPage:
        items, total = await self._announcements.list_for_admin(
            page=page,
            page_size=page_size,
            status=status,
            query=query,
        )
        return AnnouncementAdminPage(
            items=[await self._admin_response(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def patch(
        self,
        announcement_id: UUID,
        payload: AnnouncementPatchRequest,
        *,
        audit: AnnouncementAuditContext,
    ) -> AnnouncementAdminResponse:
        await self._validate_audience(payload.audience)
        self._validate_datetime(payload.publish_at, "publish_at")
        self._validate_datetime(payload.pinned_until, "pinned_until")
        announcement = await self._announcements.get_by_id(
            announcement_id,
            for_update=True,
        )
        if announcement is None:
            await self._session.rollback()
            raise self._not_found()
        if announcement.status == "archived":
            await self._session.rollback()
            raise self._state_conflict("归档通知不能编辑。")
        if announcement.revision != payload.revision:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="REVISION_CONFLICT",
                message="通知已被其他管理员修改，请刷新后重试。",
            )
        now = self._clock()
        if announcement.status == "scheduled" and (
            payload.publish_at is None or payload.publish_at <= now
        ):
            await self._session.rollback()
            raise self._state_conflict("定时通知必须保留未来的发布时间。")

        await self._validate_and_order_files(
            announcement_id=announcement.id,
            actor_user_id=audit.actor.user.id,
            file_ids=payload.attachment_file_ids,
        )
        changed_fields = [
            field
            for field, before, after in (
                ("title", announcement.title, payload.title.strip()),
                ("summary", announcement.summary, payload.summary.strip()),
                ("body_markdown", announcement.body_markdown, payload.body_markdown.strip()),
                ("all_students", announcement.all_students, payload.audience.all_students),
                ("audience_match", announcement.audience_match, payload.audience.match),
                ("publish_at", announcement.publish_at, payload.publish_at),
                ("pinned_until", announcement.pinned_until, payload.pinned_until),
                ("send_email", announcement.send_email, payload.send_email),
            )
            if before != after
        ]
        announcement.title = payload.title.strip()
        announcement.summary = payload.summary.strip()
        announcement.body_markdown = payload.body_markdown.strip()
        announcement.body_html = render_markdown(payload.body_markdown)
        announcement.all_students = payload.audience.all_students
        announcement.audience_match = payload.audience.match
        announcement.publish_at = payload.publish_at
        announcement.pinned_until = payload.pinned_until
        announcement.send_email = payload.send_email
        announcement.updated_by = audit.actor.user.id
        announcement.revision += 1
        await self._announcements.replace_audience(
            announcement.id,
            cohort_ids=payload.audience.cohort_ids,
            direction_ids=payload.audience.direction_ids,
        )
        await self._announcements.replace_files(
            announcement.id,
            payload.attachment_file_ids,
        )
        if announcement.status == "scheduled":
            scheduled_job = await self._outbox.get_by_event_key(
                f"announcement:{announcement.id}:publish"
            )
            if scheduled_job is not None and payload.publish_at is not None:
                scheduled_job.available_at = payload.publish_at
                scheduled_job.status = "pending"
                scheduled_job.locked_at = None
                scheduled_job.locked_by = None
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="announcement.update",
            announcement_id=announcement.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={
                "changed_fields": changed_fields,
                "attachment_count": len(payload.attachment_file_ids),
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
                message="通知或附件状态发生冲突，请刷新后重试。",
            ) from exc
        await self._session.refresh(announcement)
        return await self._admin_response(announcement)

    def _notification_for(
        self,
        *,
        announcement: Announcement,
        user: User,
        event_key: str,
        notification_type: str,
        now: datetime,
    ) -> StudentNotification:
        return StudentNotification(
            id=uuid7(),
            user_id=user.id,
            notification_type=notification_type,
            event_key=event_key,
            title=announcement.title,
            target_type="announcement",
            target_id=announcement.id,
            target_url=f"/announcements/{announcement.id}",
            created_at=now,
            read_at=None,
        )

    def _mail_job_for(
        self,
        *,
        announcement: Announcement,
        user: User,
        job_type: str,
        event_key: str,
        now: datetime,
    ) -> OutboxJob:
        return OutboxJob(
            id=uuid7(),
            job_type=job_type,
            event_key=event_key,
            payload={
                "recipient": user.email,
                "full_name": user.full_name,
                "announcement_id": str(announcement.id),
                "title": announcement.title,
                "summary": announcement.summary,
                "target_url": f"/announcements/{announcement.id}",
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

    async def _apply_publish(
        self,
        announcement: Announcement,
        *,
        actor_user_id: UUID | None,
        request_id: str,
        ip_prefix: str,
        now: datetime,
    ) -> None:
        users = await self._announcements.audience_users(announcement)
        event_key = f"announcement:{announcement.id}:published"
        self._notifications.add_all(
            [
                self._notification_for(
                    announcement=announcement,
                    user=user,
                    event_key=event_key,
                    notification_type="announcement",
                    now=now,
                )
                for user in users
            ]
        )
        if announcement.send_email:
            for user in users:
                self._outbox.add(
                    self._mail_job_for(
                        announcement=announcement,
                        user=user,
                        job_type="announcement_email",
                        event_key=f"announcement:{announcement.id}:email:{user.id}",
                        now=now,
                    )
                )
        announcement.status = "published"
        announcement.published_at = now
        announcement.publish_at = announcement.publish_at or now
        announcement.updated_by = actor_user_id
        announcement.revision += 1
        self._add_audit(
            actor_user_id=actor_user_id,
            action="announcement.publish",
            announcement_id=announcement.id,
            request_id=request_id,
            ip_prefix=ip_prefix,
            change_summary={
                "recipient_count": len(users),
                "send_email": announcement.send_email,
            },
            now=now,
        )

    async def publish(
        self,
        announcement_id: UUID,
        *,
        audit: AnnouncementAuditContext,
    ) -> AnnouncementAdminResponse:
        announcement = await self._announcements.get_by_id(
            announcement_id,
            for_update=True,
        )
        if announcement is None:
            await self._session.rollback()
            raise self._not_found()
        if announcement.status == "published":
            await self._session.commit()
            return await self._admin_response(announcement)
        if announcement.status == "archived":
            await self._session.rollback()
            raise self._state_conflict("归档通知不能重新发布。")

        now = self._clock()
        if announcement.publish_at is not None and announcement.publish_at > now:
            announcement.status = "scheduled"
            announcement.updated_by = audit.actor.user.id
            announcement.revision += 1
            event_key = f"announcement:{announcement.id}:publish"
            scheduled_job = await self._outbox.get_by_event_key(event_key)
            if scheduled_job is None:
                self._outbox.add(
                    OutboxJob(
                        id=uuid7(),
                        job_type="publish_announcement",
                        event_key=event_key,
                        payload={"announcement_id": str(announcement.id)},
                        secret_payload_ciphertext=None,
                        status="pending",
                        available_at=announcement.publish_at,
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
            else:
                scheduled_job.available_at = announcement.publish_at
                scheduled_job.status = "pending"
            self._add_audit(
                actor_user_id=audit.actor.user.id,
                action="announcement.schedule",
                announcement_id=announcement.id,
                request_id=audit.request_id,
                ip_prefix=audit.ip_prefix,
                change_summary={"publish_at": announcement.publish_at.isoformat()},
                now=now,
            )
        else:
            await self._apply_publish(
                announcement,
                actor_user_id=audit.actor.user.id,
                request_id=audit.request_id,
                ip_prefix=audit.ip_prefix,
                now=now,
            )
        await self._session.commit()
        await self._session.refresh(announcement)
        return await self._admin_response(announcement)

    async def publish_scheduled(
        self,
        announcement_id: UUID,
        *,
        job_id: UUID,
    ) -> None:
        announcement = await self._announcements.get_by_id(
            announcement_id,
            for_update=True,
        )
        if announcement is None or announcement.status == "published":
            await self._session.commit()
            return
        now = self._clock()
        if (
            announcement.status != "scheduled"
            or announcement.publish_at is None
            or announcement.publish_at > now
        ):
            await self._session.commit()
            return
        await self._apply_publish(
            announcement,
            actor_user_id=announcement.created_by,
            request_id=f"worker:{job_id}",
            ip_prefix="worker",
            now=now,
        )
        await self._session.commit()

    async def _archive_record(
        self,
        announcement: Announcement,
        *,
        audit: AnnouncementAuditContext,
        action: str,
        deletion_mode: str | None = None,
    ) -> None:
        now = self._clock()
        announcement.status = "archived"
        announcement.archived_at = now
        announcement.updated_by = audit.actor.user.id
        announcement.revision += 1
        unread_notifications = await self._notifications.unread_for_target(
            target_type="announcement",
            target_id=announcement.id,
            for_update=True,
        )
        for notification in unread_notifications:
            notification.read_at = now
        change_summary: dict[str, object] = {"status": "archived"}
        if deletion_mode is not None:
            change_summary["deletion_mode"] = deletion_mode
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action=action,
            announcement_id=announcement.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary=change_summary,
            now=now,
        )

    async def archive(
        self,
        announcement_id: UUID,
        *,
        audit: AnnouncementAuditContext,
    ) -> AnnouncementAdminResponse:
        announcement = await self._announcements.get_by_id(
            announcement_id,
            for_update=True,
        )
        if announcement is None:
            await self._session.rollback()
            raise self._not_found()
        if announcement.status == "archived":
            await self._session.commit()
            return await self._admin_response(announcement)
        if announcement.status != "published":
            await self._session.rollback()
            raise self._state_conflict("只有已发布通知可以归档。")
        await self._archive_record(
            announcement,
            audit=audit,
            action="announcement.archive",
        )
        await self._session.commit()
        await self._session.refresh(announcement)
        return await self._admin_response(announcement)

    async def remove(
        self,
        announcement_id: UUID,
        *,
        audit: AnnouncementAuditContext,
    ) -> None:
        announcement = await self._announcements.get_by_id(
            announcement_id,
            for_update=True,
        )
        if announcement is None:
            await self._session.rollback()
            raise self._not_found()
        if announcement.status == "archived":
            await self._session.commit()
            return
        if announcement.status in {"draft", "scheduled"}:
            previous_status = announcement.status
            now = self._clock()
            await self._outbox.delete_active_by_event_key(f"announcement:{announcement.id}:publish")
            await self._announcements.delete(announcement)
            self._add_audit(
                actor_user_id=audit.actor.user.id,
                action="announcement.delete",
                announcement_id=announcement.id,
                request_id=audit.request_id,
                ip_prefix=audit.ip_prefix,
                change_summary={
                    "previous_status": previous_status,
                    "deletion_mode": "physical",
                },
                now=now,
            )
        else:
            await self._archive_record(
                announcement,
                audit=audit,
                action="announcement.delete",
                deletion_mode="archive",
            )
        await self._session.commit()

    async def send_update(
        self,
        announcement_id: UUID,
        *,
        audit: AnnouncementAuditContext,
    ) -> AnnouncementAdminResponse:
        announcement = await self._announcements.get_by_id(
            announcement_id,
            for_update=True,
        )
        if announcement is None:
            await self._session.rollback()
            raise self._not_found()
        if announcement.status != "published":
            await self._session.rollback()
            raise self._state_conflict("只有已发布通知可以发送更新提醒。")
        users = await self._announcements.audience_users(announcement)
        revision_event = f"announcement:{announcement.id}:update:{announcement.revision}"
        if users:
            existing = await self._outbox.get_by_event_key(f"{revision_event}:email:{users[0].id}")
            if existing is not None:
                await self._session.commit()
                return await self._admin_response(announcement)
        now = self._clock()
        self._notifications.add_all(
            [
                self._notification_for(
                    announcement=announcement,
                    user=user,
                    event_key=revision_event,
                    notification_type="announcement_update",
                    now=now,
                )
                for user in users
            ]
        )
        for user in users:
            self._outbox.add(
                self._mail_job_for(
                    announcement=announcement,
                    user=user,
                    job_type="announcement_update_email",
                    event_key=f"{revision_event}:email:{user.id}",
                    now=now,
                )
            )
        self._add_audit(
            actor_user_id=audit.actor.user.id,
            action="announcement.send_update",
            announcement_id=announcement.id,
            request_id=audit.request_id,
            ip_prefix=audit.ip_prefix,
            change_summary={
                "recipient_count": len(users),
                "announcement_revision": announcement.revision,
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
                message="本次更新提醒已经发送。",
            ) from exc
        await self._session.refresh(announcement)
        return await self._admin_response(announcement)

    async def _summary_responses(
        self,
        announcements: Sequence[Announcement],
        *,
        user_id: UUID,
    ) -> list[AnnouncementSummaryResponse]:
        now = self._clock()
        announcement_ids = [announcement.id for announcement in announcements]
        unread_ids = await self._announcements.unread_target_ids(
            user_id=user_id,
            announcement_ids=announcement_ids,
        )
        attachment_ids = await self._announcements.announcement_ids_with_attachments(
            announcement_ids
        )
        return [
            AnnouncementSummaryResponse(
                id=announcement.id,
                title=announcement.title,
                summary=announcement.summary,
                published_at=announcement.published_at or announcement.created_at,
                updated_at=announcement.updated_at,
                pinned_until=announcement.pinned_until,
                is_pinned=(
                    announcement.pinned_until is not None and announcement.pinned_until > now
                ),
                is_unread=announcement.id in unread_ids,
                has_attachments=announcement.id in attachment_ids,
            )
            for announcement in announcements
        ]

    async def list_student(
        self,
        *,
        context: AuthenticatedContext,
        page: int,
        page_size: int,
        query: str | None,
        unread: bool | None,
    ) -> AnnouncementPage:
        now = self._clock()
        items, total = await self._announcements.list_for_student(
            user=context.user,
            page=page,
            page_size=page_size,
            query=query,
            unread=unread,
            now=now,
        )
        return AnnouncementPage(
            items=await self._summary_responses(items, user_id=context.user.id),
            page=page,
            page_size=page_size,
            total=total,
        )

    async def get_student(
        self,
        announcement_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> AnnouncementDetailResponse:
        announcement = await self._announcements.get_by_id(announcement_id)
        if announcement is None or announcement.status != "published":
            raise self._not_found()
        cohort_ids, direction_ids = await self._announcements.audience_ids(announcement.id)
        if not self._audience_matches(
            announcement,
            context.user,
            cohort_ids,
            direction_ids,
        ):
            raise self._not_found()
        attachments = await self._announcements.attachments(announcement.id)
        notification_ids = await self._announcements.notification_ids_for_target(
            user_id=context.user.id,
            announcement_id=announcement.id,
        )
        if announcement.all_students:
            audience_description = "全部学生"
        else:
            match_text = "并集" if announcement.audience_match == "union" else "交集"
            audience_description = (
                f"{len(cohort_ids)} 个届次、{len(direction_ids)} 个方向（{match_text}）"
            )
        return AnnouncementDetailResponse(
            id=announcement.id,
            title=announcement.title,
            summary=announcement.summary,
            body_html=announcement.body_html,
            published_at=announcement.published_at or announcement.created_at,
            updated_at=announcement.updated_at,
            pinned_until=announcement.pinned_until,
            audience_description=audience_description,
            attachments=[
                AnnouncementAttachmentResponse(
                    id=stored_file.id,
                    file_name=stored_file.original_name,
                    size_bytes=stored_file.size_bytes,
                    media_type=(stored_file.detected_media_type or stored_file.declared_media_type),
                    sha256=stored_file.sha256,
                )
                for stored_file in attachments
            ],
            notification_ids=notification_ids,
        )

    async def dashboard(
        self,
        *,
        context: AuthenticatedContext,
    ) -> DashboardResponse:
        items, _ = await self._announcements.list_for_student(
            user=context.user,
            page=1,
            page_size=5,
            query=None,
            unread=None,
            now=self._clock(),
            include_total=False,
        )
        assignment_items: list[DashboardAssignmentItem] = []
        if context_effective_role(context) == "student":
            records, _ = await AssignmentRepository(self._session).list_for_student(
                user_id=context.user.id,
                preview_user=context.user if getattr(context, "is_student_view", False) else None,
                page=1,
                page_size=5,
                status=None,
                query=None,
                now=self._clock(),
                limit=5,
            )
            assignment_items = [
                DashboardAssignmentItem(
                    id=record.assignment.id,
                    title=record.assignment.title,
                    deadline=(
                        record.extension.extended_deadline
                        if record.extension is not None
                        else record.assignment.deadline
                    ),
                )
                for record in records
            ]
        competition_items = [
            DashboardCompetitionItem(
                id=competition.id,
                name=competition.name,
                status=competition.status,
            )
            for competition in await CompetitionRepository(self._session).dashboard_competitions()
        ]
        unread_counts = await self._notifications.unread_counts(context.user.id)
        return DashboardResponse(
            current_user=DashboardUserResponse(
                id=context.user.id,
                full_name=context.user.full_name,
                role=context_effective_role(context),
                cohort_id=context.user.cohort_id,
                direction_id=context.user.direction_id,
            ),
            unread_count=unread_counts.total,
            unread_counts=DashboardUnreadCounts(
                announcements=unread_counts.announcements,
                assignments=unread_counts.assignments,
                competitions=unread_counts.competitions,
                help_requests=unread_counts.help_requests,
            ),
            recent_announcements=await self._summary_responses(
                items,
                user_id=context.user.id,
            ),
            assignments=assignment_items,
            competitions=competition_items,
        )


class ScheduledAnnouncementPublisher:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._factory = factory
        self._clock = clock

    async def publish(self, announcement_id: UUID, job_id: UUID) -> None:
        async with self._factory() as session:
            await AnnouncementService(session, clock=self._clock).publish_scheduled(
                announcement_id,
                job_id=job_id,
            )
