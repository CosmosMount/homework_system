import logging
import re
import unicodedata
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.announcements.repository import AnnouncementRepository
from app.announcements.service import AnnouncementService
from app.assignments.policy import can_submit_assignment
from app.assignments.repository import AssignmentRepository
from app.auth.service import AuthenticatedContext
from app.competitions.policy import task_submission_is_open
from app.competitions.repository import CompetitionRepository
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.submissions.repository import SubmissionRepository
from app.uploads.models import StoredFile, UploadPart, UploadSession
from app.uploads.object_store import (
    MinioObjectStore,
    ObjectInspection,
    ObjectPart,
    ObjectStoreError,
)
from app.uploads.repository import UploadRepository
from app.uploads.schemas import (
    CompletedFileResponse,
    CompleteUploadRequest,
    DownloadUrlResponse,
    PresignedPartResponse,
    PresignPartsResponse,
    UploadedPartResponse,
    UploadInitRequest,
    UploadSessionResponse,
)

logger = logging.getLogger(__name__)


SAFE_EXTENSIONS = {
    "7z",
    "c",
    "cpp",
    "csv",
    "doc",
    "docx",
    "dxf",
    "gif",
    "go",
    "gz",
    "h",
    "hpp",
    "iges",
    "igs",
    "java",
    "jpeg",
    "jpg",
    "json",
    "kicad_pcb",
    "kicad_sch",
    "kt",
    "mat",
    "md",
    "mp4",
    "pdf",
    "png",
    "ppt",
    "pptx",
    "py",
    "rs",
    "slx",
    "step",
    "stp",
    "tar",
    "tar.gz",
    "txt",
    "webm",
    "webp",
    "xls",
    "xlsx",
    "zip",
}
_DANGEROUS_SUFFIXES = {
    "app",
    "bat",
    "cmd",
    "com",
    "dll",
    "dmg",
    "exe",
    "hta",
    "html",
    "htm",
    "iso",
    "jar",
    "js",
    "lnk",
    "msi",
    "msp",
    "ps1",
    "scr",
    "sh",
    "svg",
    "vbs",
}
_DANGEROUS_MEDIA_TYPES = {
    "application/javascript",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-msdownload",
    "image/svg+xml",
    "text/html",
    "text/javascript",
}
_TEXT_EXTENSIONS = {
    "c",
    "cpp",
    "csv",
    "go",
    "h",
    "hpp",
    "java",
    "json",
    "kt",
    "md",
    "py",
    "rs",
    "txt",
}
_SHA256_BASE64 = re.compile(r"^[A-Za-z0-9+/]{43}=$")


class FileValidationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_file_name(file_name: str) -> tuple[str, str]:
    normalized = unicodedata.normalize("NFC", file_name).strip()
    if (
        not normalized
        or len(normalized) > 255
        or "/" in normalized
        or "\\" in normalized
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        or PurePath(normalized).name != normalized
    ):
        raise FileValidationError("INVALID_FILE_NAME")
    suffixes = [suffix.lower().lstrip(".") for suffix in PurePath(normalized).suffixes]
    if not suffixes:
        raise FileValidationError("FILE_TYPE_NOT_ALLOWED")
    if any(suffix in _DANGEROUS_SUFFIXES for suffix in suffixes):
        raise FileValidationError("FILE_TYPE_NOT_ALLOWED")
    extension = "tar.gz" if suffixes[-2:] == ["tar", "gz"] else suffixes[-1]
    if extension not in SAFE_EXTENSIONS:
        raise FileValidationError("FILE_TYPE_NOT_ALLOWED")
    return normalized, extension


def detect_media_type(extension: str, inspection: ObjectInspection) -> str:
    first = inspection.first_bytes
    detected: str | None = None
    if first.startswith(b"%PDF-"):
        detected = "application/pdf"
    elif first.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif first.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif first.startswith((b"GIF87a", b"GIF89a")):
        detected = "image/gif"
    elif first.startswith(b"RIFF") and first[8:12] == b"WEBP":
        detected = "image/webp"
    elif first.startswith(b"PK\x03\x04"):
        detected = "application/zip"
    elif first.startswith(b"7z\xbc\xaf\x27\x1c"):
        detected = "application/x-7z-compressed"
    elif len(first) >= 12 and first[4:8] == b"ftyp":
        detected = "video/mp4"
    elif first.startswith(b"\x1a\x45\xdf\xa3"):
        detected = "video/webm"

    expected_detected = {
        "pdf": {"application/pdf"},
        "png": {"image/png"},
        "jpg": {"image/jpeg"},
        "jpeg": {"image/jpeg"},
        "gif": {"image/gif"},
        "webp": {"image/webp"},
        "zip": {"application/zip"},
        "docx": {"application/zip"},
        "xlsx": {"application/zip"},
        "pptx": {"application/zip"},
        "7z": {"application/x-7z-compressed"},
        "mp4": {"video/mp4"},
        "webm": {"video/webm"},
    }
    expected = expected_detected.get(extension)
    if expected is not None and detected not in expected:
        raise FileValidationError("FILE_CONTENT_MISMATCH")
    if extension in _TEXT_EXTENSIONS:
        if b"\x00" in first:
            raise FileValidationError("FILE_CONTENT_MISMATCH")
        detected = "text/plain"
    return detected or inspection.content_type or "application/octet-stream"


class UploadService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        object_store: MinioObjectStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._uploads = UploadRepository(session)
        self._announcements = AnnouncementRepository(session)
        self._assignments = AssignmentRepository(session)
        self._competitions = CompetitionRepository(session)
        self._submissions = SubmissionRepository(session)
        self._object_store = object_store or MinioObjectStore(settings)
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _not_found() -> ApplicationError:
        return ApplicationError(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message="资源不存在或当前用户无权查看。",
        )

    @staticmethod
    def _store_unavailable(error: ObjectStoreError) -> ApplicationError:
        return ApplicationError(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="对象存储暂时不可用，请稍后重试。",
        )

    @staticmethod
    def _file_validation_error(error: FileValidationError) -> ApplicationError:
        status_code = 415 if error.code == "FILE_TYPE_NOT_ALLOWED" else 400
        return ApplicationError(
            status_code=status_code,
            code=error.code,
            message="文件名称、类型或内容不符合安全要求。",
        )

    async def _session_response(
        self,
        upload_session: UploadSession,
        *,
        use_remote_parts: bool,
    ) -> UploadSessionResponse:
        stored_file = await self._uploads.get_file(upload_session.file_id)
        if stored_file is None:
            raise self._not_found()
        if use_remote_parts and upload_session.status in {"initialized", "uploading"}:
            try:
                object_parts = await self._object_store.list_parts(
                    object_key=stored_file.object_key,
                    upload_id=upload_session.minio_upload_id,
                )
            except ObjectStoreError as exc:
                raise self._store_unavailable(exc) from exc
            uploaded_parts = [
                UploadedPartResponse(
                    part_number=part.part_number,
                    etag=part.etag,
                    checksum_sha256=part.checksum_sha256,
                    size_bytes=part.size_bytes,
                )
                for part in object_parts
            ]
        else:
            uploaded_parts = [
                UploadedPartResponse(
                    part_number=part.part_number,
                    etag=part.etag,
                    checksum_sha256=part.checksum_sha256,
                    size_bytes=part.size_bytes,
                )
                for part in await self._uploads.parts(upload_session.id)
            ]
        return UploadSessionResponse(
            upload_id=upload_session.id,
            file_id=upload_session.file_id,
            status=upload_session.status,
            part_size_bytes=upload_session.part_size_bytes,
            part_count=upload_session.part_count,
            uploaded_parts=uploaded_parts,
            expires_at=upload_session.expires_at,
            failure_code=upload_session.failure_code,
        )

    async def _require_context(
        self,
        *,
        payload: UploadInitRequest,
        context: AuthenticatedContext,
        extension: str,
    ) -> str:
        if payload.purpose == "announcement_attachment":
            announcement = await self._announcements.get_by_id(payload.context_id)
            if (
                context.user.role != "admin"
                or announcement is None
                or announcement.status == "archived"
            ):
                raise self._not_found()
            return "announcement"

        if payload.purpose == "competition_submission":
            task = await self._competitions.get_task(payload.context_id)
            competition = (
                await self._competitions.get_competition(task.competition_id)
                if task is not None
                else None
            )
            team = (
                await self._competitions.team_for_user(
                    task.competition_id,
                    context.user.id,
                )
                if task is not None
                else None
            )
            if (
                context.user.role != "student"
                or task is None
                or competition is None
                or team is None
            ):
                raise self._not_found()
            if team.captain_user_id != context.user.id:
                raise ApplicationError(
                    status_code=403,
                    code="TEAM_CAPTAIN_REQUIRED",
                    message="只有当前队长可以上传团队提交附件。",
                )
            if not task_submission_is_open(
                competition,
                task,
                team,
                self._clock(),
            ):
                code = (
                    "TEAM_INVALID"
                    if team.status == "invalid"
                    else (
                        "TEAM_DISQUALIFIED"
                        if team.status == "disqualified"
                        else "COMPETITION_SUBMISSION_CLOSED"
                    )
                )
                raise ApplicationError(
                    status_code=409,
                    code=code,
                    message="当前队伍或赛事状态不能上传赛题附件。",
                )
            if extension not in task.allowed_extensions:
                raise ApplicationError(
                    status_code=415,
                    code="FILE_TYPE_NOT_ALLOWED",
                    message="附件类型不在当前赛题白名单内。",
                )
            if payload.size_bytes > task.max_total_bytes:
                raise ApplicationError(
                    status_code=413,
                    code="SUBMISSION_SIZE_EXCEEDED",
                    message="文件超过当前赛题的附件总量上限。",
                )
            return "competition_task"

        assignment = await self._assignments.get_by_id(payload.context_id)
        if (
            context.user.role != "student"
            or assignment is None
            or assignment.status in {"draft", "archived"}
            or not await self._assignments.is_audience_user(
                payload.context_id,
                context.user.id,
            )
        ):
            raise self._not_found()
        personal_extension = await self._assignments.get_extension(
            payload.context_id,
            context.user.id,
        )
        if not can_submit_assignment(assignment, personal_extension, self._clock()):
            raise ApplicationError(
                status_code=409,
                code="ASSIGNMENT_CLOSED",
                message="作业已超过当前账号的有效截止时间。",
            )
        if extension not in assignment.allowed_extensions:
            raise ApplicationError(
                status_code=415,
                code="FILE_TYPE_NOT_ALLOWED",
                message="附件类型不在当前作业白名单内。",
            )
        if payload.size_bytes > assignment.max_total_bytes:
            raise ApplicationError(
                status_code=413,
                code="SUBMISSION_SIZE_EXCEEDED",
                message="文件超过当前作业的附件总量上限。",
            )
        return "assignment"

    async def initialize(
        self,
        payload: UploadInitRequest,
        *,
        context: AuthenticatedContext,
        idempotency_key: str,
    ) -> UploadSessionResponse:
        if payload.size_bytes > self._settings.global_max_upload_bytes:
            raise ApplicationError(
                status_code=413,
                code="SUBMISSION_SIZE_EXCEEDED",
                message="文件超过全局 2 GiB 上限。",
            )
        try:
            file_name, extension = normalize_file_name(payload.file_name)
        except FileValidationError as exc:
            raise self._file_validation_error(exc) from exc
        media_type = payload.media_type.lower().split(";", 1)[0].strip()
        context_type = await self._require_context(
            payload=payload,
            context=context,
            extension=extension,
        )
        if media_type in _DANGEROUS_MEDIA_TYPES:
            raise ApplicationError(
                status_code=415,
                code="FILE_TYPE_NOT_ALLOWED",
                message="文件媒体类型不在安全白名单内。",
            )
        existing = await self._uploads.get_by_idempotency(
            user_id=context.user.id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            stored_file = await self._uploads.get_file(existing.file_id)
            if (
                stored_file is None
                or existing.purpose != payload.purpose
                or existing.context_id != payload.context_id
                or existing.expected_size_bytes != payload.size_bytes
                or existing.expected_sha256 != payload.sha256
                or stored_file.original_name != file_name
                or stored_file.declared_media_type != media_type
            ):
                raise ApplicationError(
                    status_code=409,
                    code="IDEMPOTENCY_CONFLICT",
                    message="同一幂等键已经用于不同上传请求。",
                )
            return await self._session_response(existing, use_remote_parts=True)

        now = self._clock()
        file_id = uuid7()
        object_key = f"objects/{now:%Y}/{now:%m}/{uuid7()}"
        try:
            minio_upload_id = await self._object_store.create_multipart(
                object_key=object_key,
                media_type=media_type,
            )
        except ObjectStoreError as exc:
            raise self._store_unavailable(exc) from exc
        part_size = self._settings.upload_part_size_bytes
        part_count = max(1, (payload.size_bytes + part_size - 1) // part_size)
        stored_file = StoredFile(
            id=file_id,
            owner_user_id=context.user.id,
            purpose=payload.purpose,
            object_key=object_key,
            original_name=file_name,
            extension=extension,
            declared_media_type=media_type,
            detected_media_type=None,
            size_bytes=payload.size_bytes,
            sha256=payload.sha256,
            status="initialized",
            created_at=now,
            available_at=None,
            deleted_at=None,
        )
        upload_session = UploadSession(
            id=uuid7(),
            file_id=file_id,
            user_id=context.user.id,
            purpose=payload.purpose,
            context_type=context_type,
            context_id=payload.context_id,
            minio_upload_id=minio_upload_id,
            part_size_bytes=part_size,
            part_count=part_count,
            expected_size_bytes=payload.size_bytes,
            expected_sha256=payload.sha256,
            status="initialized",
            last_activity_at=now,
            expires_at=now + timedelta(seconds=self._settings.upload_session_ttl_seconds),
            idempotency_key=idempotency_key,
            created_at=now,
            completed_at=None,
            failure_code=None,
        )
        self._uploads.add_file(stored_file)
        self._uploads.add_session(upload_session)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            try:
                await self._object_store.abort_multipart(
                    object_key=object_key,
                    upload_id=minio_upload_id,
                )
            except ObjectStoreError:
                logger.warning(
                    "multipart_abort_after_conflict_failed",
                    extra={
                        "event": "multipart_abort_after_conflict_failed",
                        "file_id": str(file_id),
                    },
                )
            raise ApplicationError(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                message="上传请求已被并发创建，请使用原幂等键查询。",
            ) from exc
        return await self._session_response(upload_session, use_remote_parts=False)

    async def _get_owned_session(
        self,
        upload_id: UUID,
        *,
        context: AuthenticatedContext,
        for_update: bool,
    ) -> UploadSession:
        upload_session = await self._uploads.get_session(
            upload_id,
            user_id=context.user.id,
            for_update=for_update,
        )
        if upload_session is None:
            raise self._not_found()
        return upload_session

    async def get(
        self,
        upload_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> UploadSessionResponse:
        upload_session = await self._get_owned_session(
            upload_id,
            context=context,
            for_update=False,
        )
        if (
            upload_session.status in {"initialized", "uploading"}
            and upload_session.expires_at <= self._clock()
        ):
            await self.abort(upload_id, context=context, expired=True)
            raise ApplicationError(
                status_code=410,
                code="UPLOAD_EXPIRED",
                message="上传会话已过期。",
            )
        return await self._session_response(upload_session, use_remote_parts=True)

    async def presign(
        self,
        upload_id: UUID,
        *,
        part_numbers: Sequence[int],
        context: AuthenticatedContext,
    ) -> PresignPartsResponse:
        upload_session = await self._get_owned_session(
            upload_id,
            context=context,
            for_update=True,
        )
        now = self._clock()
        if upload_session.expires_at <= now:
            await self._session.rollback()
            await self.abort(upload_id, context=context, expired=True)
            raise ApplicationError(
                status_code=410,
                code="UPLOAD_EXPIRED",
                message="上传会话已过期。",
            )
        if upload_session.status not in {"initialized", "uploading"}:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="当前上传状态不能签发新分片。",
            )
        if any(
            part_number < 1 or part_number > upload_session.part_count
            for part_number in part_numbers
        ):
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="分片编号超出当前上传范围。",
            )
        stored_file = await self._uploads.get_file(upload_session.file_id)
        if stored_file is None:
            await self._session.rollback()
            raise self._not_found()
        upload_session.status = "uploading"
        upload_session.last_activity_at = now
        upload_session.expires_at = now + timedelta(
            seconds=self._settings.upload_session_ttl_seconds
        )
        try:
            presigned = await self._object_store.presign_parts(
                object_key=stored_file.object_key,
                upload_id=upload_session.minio_upload_id,
                part_numbers=part_numbers,
                expires_seconds=900,
            )
        except ObjectStoreError as exc:
            await self._session.rollback()
            raise self._store_unavailable(exc) from exc
        await self._session.commit()
        return PresignPartsResponse(
            parts=[
                PresignedPartResponse(
                    part_number=part_number,
                    url=url,
                    checksum_header="x-amz-checksum-sha256",
                )
                for part_number, url in presigned
            ],
            expires_in_seconds=900,
        )

    async def complete(
        self,
        upload_id: UUID,
        payload: CompleteUploadRequest,
        *,
        context: AuthenticatedContext,
    ) -> CompletedFileResponse:
        upload_session = await self._get_owned_session(
            upload_id,
            context=context,
            for_update=True,
        )
        stored_file = await self._uploads.get_file(
            upload_session.file_id,
            for_update=True,
        )
        if stored_file is None:
            await self._session.rollback()
            raise self._not_found()
        if upload_session.status == "available":
            await self._session.rollback()
            return self._completed_response(stored_file)
        if upload_session.expires_at <= self._clock():
            await self._session.rollback()
            await self.abort(upload_id, context=context, expired=True)
            raise ApplicationError(
                status_code=410,
                code="UPLOAD_EXPIRED",
                message="上传会话已过期。",
            )
        if upload_session.status not in {"initialized", "uploading"}:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="当前上传状态不能完成。",
            )
        if payload.sha256 != upload_session.expected_sha256:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="HASH_MISMATCH",
                message="完成请求的 SHA-256 与初始化声明不一致。",
            )
        ordered_parts = sorted(payload.parts, key=lambda part: part.part_number)
        expected_numbers = list(range(1, upload_session.part_count + 1))
        if [part.part_number for part in ordered_parts] != expected_numbers:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="分片集合不连续或数量不正确。",
            )
        try:
            remote_parts = await self._object_store.list_parts(
                object_key=stored_file.object_key,
                upload_id=upload_session.minio_upload_id,
            )
        except ObjectStoreError as exc:
            await self._session.rollback()
            raise self._store_unavailable(exc) from exc
        remote_by_number = {part.part_number: part for part in remote_parts}
        if set(remote_by_number) != set(expected_numbers):
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="UPLOAD_INCOMPLETE",
                message="仍有分片未上传完成。",
            )
        object_parts: list[ObjectPart] = []
        for requested in ordered_parts:
            remote = remote_by_number[requested.part_number]
            if remote.etag.strip('"') != requested.etag.strip('"'):
                await self._session.rollback()
                raise ApplicationError(
                    status_code=409,
                    code="UPLOAD_PART_MISMATCH",
                    message="分片 ETag 与对象存储记录不一致。",
                )
            if not _SHA256_BASE64.fullmatch(requested.checksum_sha256):
                await self._session.rollback()
                raise ApplicationError(
                    status_code=400,
                    code="VALIDATION_ERROR",
                    message="分片校验和格式错误。",
                )
            object_parts.append(
                ObjectPart(
                    part_number=requested.part_number,
                    etag=requested.etag,
                    checksum_sha256=requested.checksum_sha256,
                    size_bytes=remote.size_bytes,
                )
            )

        upload_session.status = "verifying"
        stored_file.status = "verifying"
        try:
            await self._object_store.complete_multipart(
                object_key=stored_file.object_key,
                upload_id=upload_session.minio_upload_id,
                parts=object_parts,
            )
            inspection = await self._object_store.inspect(stored_file.object_key)
        except ObjectStoreError as exc:
            upload_session.status = "uploading"
            stored_file.status = "uploading"
            upload_session.failure_code = str(exc)[:100]
            await self._session.commit()
            raise self._store_unavailable(exc) from exc

        try:
            if inspection.size_bytes != upload_session.expected_size_bytes:
                raise FileValidationError("FILE_SIZE_MISMATCH")
            if inspection.sha256 != upload_session.expected_sha256:
                raise FileValidationError("HASH_MISMATCH")
            detected_media_type = detect_media_type(stored_file.extension, inspection)
        except FileValidationError as exc:
            upload_session.status = "rejected"
            stored_file.status = "rejected"
            upload_session.failure_code = exc.code
            await self._session.commit()
            try:
                await self._object_store.delete_object(stored_file.object_key)
            except ObjectStoreError:
                logger.warning(
                    "rejected_object_cleanup_failed",
                    extra={
                        "event": "rejected_object_cleanup_failed",
                        "file_id": str(stored_file.id),
                    },
                )
            raise ApplicationError(
                status_code=400,
                code=exc.code,
                message="对象大小、类型或 SHA-256 校验失败。",
            ) from exc

        now = self._clock()
        await self._uploads.replace_parts(
            upload_session.id,
            [
                UploadPart(
                    upload_session_id=upload_session.id,
                    part_number=part.part_number,
                    etag=part.etag,
                    checksum_sha256=part.checksum_sha256,
                    size_bytes=part.size_bytes,
                    completed_at=now,
                )
                for part in object_parts
            ],
        )
        upload_session.status = "available"
        upload_session.completed_at = now
        upload_session.last_activity_at = now
        upload_session.failure_code = None
        stored_file.status = "available"
        stored_file.size_bytes = inspection.size_bytes
        stored_file.sha256 = inspection.sha256
        stored_file.detected_media_type = detected_media_type
        stored_file.available_at = now
        await self._session.commit()
        return self._completed_response(stored_file)

    @staticmethod
    def _completed_response(stored_file: StoredFile) -> CompletedFileResponse:
        return CompletedFileResponse(
            file_id=stored_file.id,
            status=stored_file.status,
            file_name=stored_file.original_name,
            size_bytes=stored_file.size_bytes,
            media_type=stored_file.detected_media_type or stored_file.declared_media_type,
            sha256=stored_file.sha256,
        )

    async def abort(
        self,
        upload_id: UUID,
        *,
        context: AuthenticatedContext,
        expired: bool = False,
    ) -> None:
        upload_session = await self._get_owned_session(
            upload_id,
            context=context,
            for_update=True,
        )
        stored_file = await self._uploads.get_file(
            upload_session.file_id,
            for_update=True,
        )
        if stored_file is None:
            await self._session.rollback()
            raise self._not_found()
        if upload_session.status in {"aborted", "expired"}:
            await self._session.rollback()
            return
        if upload_session.status == "available":
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="已完成文件不能通过上传会话终止。",
            )
        new_status = "expired" if expired else "aborted"
        upload_session.status = new_status
        stored_file.status = new_status
        upload_session.failure_code = "UPLOAD_EXPIRED" if expired else None
        await self._session.commit()
        try:
            await self._object_store.abort_multipart(
                object_key=stored_file.object_key,
                upload_id=upload_session.minio_upload_id,
            )
        except ObjectStoreError as exc:
            raise self._store_unavailable(exc) from exc

    async def download_url(
        self,
        file_id: UUID,
        *,
        context: AuthenticatedContext,
    ) -> DownloadUrlResponse:
        stored_file = await self._uploads.get_file(file_id)
        if (
            stored_file is None
            or stored_file.status != "available"
            or stored_file.deleted_at is not None
        ):
            raise self._not_found()
        announcement_id = await self._uploads.bound_announcement_id(file_id)
        if announcement_id is not None:
            if context.user.role != "admin":
                await AnnouncementService(self._session).get_student(
                    announcement_id,
                    context=context,
                )
        else:
            version_id = await self._uploads.bound_version_id(file_id)
            if version_id is None:
                raise self._not_found()
            record = await self._submissions.version_with_submission(version_id)
            if record is None:
                raise self._not_found()
            submission = record.submission
            if context.user.role != "admin":
                if submission.assignment_id is not None:
                    if submission.owner_user_id != context.user.id:
                        marker = await self._assignments.get_excellent_marker(
                            submission.assignment_id,
                            version_id,
                        )
                        if marker is None or not await self._assignments.is_audience_user(
                            submission.assignment_id,
                            context.user.id,
                        ):
                            raise self._not_found()
                elif (
                    submission.owner_team_id is None
                    or await self._competitions.current_member(
                        submission.owner_team_id,
                        context.user.id,
                    )
                    is None
                ):
                    raise self._not_found()
        try:
            url = await self._object_store.presign_download(
                object_key=stored_file.object_key,
                file_name=stored_file.original_name,
                expires_seconds=300,
            )
        except ObjectStoreError as exc:
            raise self._store_unavailable(exc) from exc
        now = self._clock()
        return DownloadUrlResponse(
            url=url,
            expires_at=now + timedelta(seconds=300),
            file_name=stored_file.original_name,
            size_bytes=stored_file.size_bytes,
            media_type=stored_file.detected_media_type or stored_file.declared_media_type,
            sha256=stored_file.sha256,
        )


class UploadCleanupProcessor:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        object_store: MinioObjectStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._factory = factory
        self._object_store = object_store or MinioObjectStore(settings)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run_once(self, limit: int = 20) -> int:
        now = self._clock()
        cleaned = 0
        async with self._factory() as session:
            repository = UploadRepository(session)
            stale = await repository.stale_sessions(now=now, limit=limit)
            for upload_session in stale:
                stored_file = await repository.get_file(
                    upload_session.file_id,
                    for_update=True,
                )
                if stored_file is None:
                    continue
                await self._object_store.abort_multipart(
                    object_key=stored_file.object_key,
                    upload_id=upload_session.minio_upload_id,
                )
                upload_session.status = "expired"
                upload_session.failure_code = "UPLOAD_EXPIRED"
                stored_file.status = "expired"
                cleaned += 1
            remaining = max(0, limit - cleaned)
            if remaining:
                terminal_files = await repository.terminal_files_for_cleanup(
                    limit=remaining,
                )
                for stored_file in terminal_files:
                    terminal_session = await repository.get_session_by_file(stored_file.id)
                    if terminal_session is not None:
                        await self._object_store.abort_multipart(
                            object_key=stored_file.object_key,
                            upload_id=terminal_session.minio_upload_id,
                        )
                    await self._object_store.delete_object(stored_file.object_key)
                    stored_file.deleted_at = now
                    cleaned += 1
            remaining = max(0, limit - cleaned)
            if remaining:
                orphaned = await repository.orphaned_available_files(
                    created_before=now - timedelta(hours=24),
                    limit=remaining,
                )
                for stored_file in orphaned:
                    await self._object_store.delete_object(stored_file.object_key)
                    stored_file.status = "expired"
                    stored_file.deleted_at = now
                    cleaned += 1
            await session.commit()
        return cleaned
