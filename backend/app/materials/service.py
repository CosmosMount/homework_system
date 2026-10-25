import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.auth.service import AuthenticatedContext
from app.core.errors import ApplicationError
from app.core.identifiers import uuid7
from app.materials.models import Material, MaterialLoan
from app.materials.repository import MaterialRepository
from app.materials.schemas import (
    MaterialCreateRequest,
    MaterialCreateResponse,
    MaterialDetail,
    MaterialListItem,
    MaterialLoanResponse,
    MaterialPage,
    MaterialScanRequest,
    MaterialScanResponse,
    MaterialScanView,
    PairedMaterialResponse,
)
from app.notifications.models import OutboxJob
from app.uploads.object_store import MinioObjectStore, ObjectStoreError

MAX_RETURN_PHOTO_BYTES = 8 * 1024 * 1024


def _error(status: int, code: str, message: str) -> ApplicationError:
    return ApplicationError(status_code=status, code=code, message=message)


def _not_found() -> ApplicationError:
    return _error(404, "RESOURCE_NOT_FOUND", "物资不存在或已停用。")


def _conflict(message: str = "物资状态已变化，请刷新后重试。") -> ApplicationError:
    return _error(409, "STATE_CONFLICT", message)


def detect_return_photo(content: bytes, declared_mime: str) -> str:
    declared = declared_mime.strip().lower()
    declared = {"image/jpg": "image/jpeg", "image/heif": "image/heic"}.get(declared, declared)
    if declared not in {"image/png", "image/jpeg", "image/webp", "image/heic", "image/avif"}:
        raise _error(415, "FILE_TYPE_NOT_ALLOWED", "归还照片仅支持 PNG、JPG、WebP、HEIC 或 AVIF。")
    if not content or len(content) > MAX_RETURN_PHOTO_BYTES:
        raise _error(413, "SUBMISSION_SIZE_EXCEEDED", "归还照片不能超过 8 MiB。")
    detected = None
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        detected = "image/webp"
    elif len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            detected = "image/heic"
        elif brand == b"avif":
            detected = "image/avif"
    if detected != declared:
        raise _error(415, "FILE_TYPE_NOT_ALLOWED", "归还照片内容与声明格式不一致。")
    return declared


class MaterialService:
    def __init__(self, session: AsyncSession, object_store: MinioObjectStore) -> None:
        self._session = session
        self._repo = MaterialRepository(session)
        self._store = object_store

    @staticmethod
    def _actor_can_delete(context: AuthenticatedContext, material: Material) -> bool:
        return context.is_admin or material.created_by_user_id == context.user.id

    async def _active_actor(self, context: AuthenticatedContext) -> None:
        user = await self._repo.lock_active_user(context.user.id)
        if user is None or user.status != "active":
            raise _error(403, "FORBIDDEN", "当前账号不可操作物资。")

    def _audit(
        self,
        context: AuthenticatedContext,
        *,
        action: str,
        material_id: UUID,
        request_id: str,
        ip_prefix: str,
        summary: dict[str, object],
        now: datetime,
    ) -> None:
        self._session.add(
            AuditLog(
                id=uuid7(),
                actor_user_id=context.user.id,
                action=action,
                target_type="material",
                target_id=material_id,
                request_id=request_id,
                ip_prefix=ip_prefix,
                result="success",
                change_summary=summary,
                created_at=now,
            )
        )

    async def _names_for(
        self, materials: list[Material], loans: list[MaterialLoan]
    ) -> dict[UUID, str]:
        ids = {item.created_by_user_id for item in materials if item.created_by_user_id}
        ids.update(loan.borrower_user_id for loan in loans if loan.borrower_user_id)
        return await self._repo.names(ids)

    @staticmethod
    def _loan_response(loan: MaterialLoan, names: dict[UUID, str]) -> MaterialLoanResponse:
        return MaterialLoanResponse(
            id=loan.id,
            borrower_user_id=loan.borrower_user_id,
            borrower_name=(
                names.get(loan.borrower_user_id, "已注销用户")
                if loan.borrower_user_id
                else "已注销用户"
            ),
            checked_out_at=loan.checked_out_at,
            returned_at=loan.returned_at,
            has_return_photo=loan.photo_object_key is not None,
        )

    def _item(
        self,
        material: Material,
        pair: Material | None,
        active: MaterialLoan | None,
        names: dict[UUID, str],
    ) -> MaterialListItem:
        return MaterialListItem(
            id=material.id,
            qr_token=material.qr_token,
            name=material.name,
            price=f"{material.price:.2f}",
            tech_group=material.tech_group,
            created_at=material.created_at,
            paired_material=(
                PairedMaterialResponse(
                    id=pair.id,
                    name=pair.name,
                    deleted_at=pair.deleted_at,
                )
                if pair
                else None
            ),
            active_loan=self._loan_response(active, names) if active else None,
        )

    async def list_materials(
        self,
        *,
        query: str = "",
        tech_group: str | None = None,
        status: str | None = None,
        page: int = 1,
    ) -> MaterialPage:
        rows, total, in_use = await self._repo.list_page(
            query=query.strip(),
            tech_group=tech_group,
            status=status,
            page=page,
        )
        visible = rows[:100]
        pairs = await self._repo.pair_members({row.pair_key for row in visible if row.pair_key})
        pair_map = {
            row.id: next((p for p in pairs if p.pair_key == row.pair_key and p.id != row.id), None)
            for row in visible
            if row.pair_key
        }
        loans = await self._repo.active_loans([row.id for row in visible]) if visible else []
        by_material = {loan.material_id: loan for loan in loans}
        names = await self._names_for(visible, loans)
        return MaterialPage(
            items=[
                self._item(row, pair_map.get(row.id), by_material.get(row.id), names)
                for row in visible
            ],
            total_count=total,
            in_use_count=in_use,
            available_count=total - in_use,
            has_more=len(rows) > 100,
            page=page,
            page_size=100,
        )

    async def detail(self, material_id: UUID, context: AuthenticatedContext) -> MaterialDetail:
        material = await self._repo.get(material_id)
        if material is None:
            raise _not_found()
        group = await self._repo.group(material)
        pair = next((item for item in group if item.id != material.id), None)
        history = await self._repo.history(material.id)
        names = await self._names_for(group, history)
        active = next((loan for loan in history if loan.returned_at is None), None)
        item = self._item(material, pair, active, names)
        return MaterialDetail(
            **item.model_dump(),
            deleted_at=material.deleted_at,
            created_by_user_id=material.created_by_user_id,
            created_by_name=(
                names.get(material.created_by_user_id, "已注销用户")
                if material.created_by_user_id
                else "已注销用户"
            ),
            can_delete=(material.deleted_at is None and self._actor_can_delete(context, material)),
            history=[self._loan_response(loan, names) for loan in history],
        )

    async def scan_view(self, qr_token: UUID, context: AuthenticatedContext) -> MaterialScanView:
        material = await self._repo.by_qr(qr_token)
        if material is None or material.deleted_at is not None:
            raise _not_found()
        group = await self._repo.group(material)
        if len(group) != (2 if material.pair_key else 1) or any(item.deleted_at for item in group):
            raise _conflict("配套物资状态异常，请联系管理员处理。")
        active_group = await self._repo.active_loans([item.id for item in group])
        if active_group and len(active_group) != len(group):
            raise _conflict("配套物资状态异常，请联系管理员处理。")
        active = [loan for loan in active_group if loan.material_id == material.id]
        names = await self._names_for(group, active)
        item = self._item(
            material,
            next((p for p in group if p.id != material.id), None),
            active[0] if active else None,
            names,
        )
        borrower = active[0].borrower_user_id if active else None
        return MaterialScanView(
            **item.model_dump(),
            can_return=bool(active and borrower == context.user.id),
            can_reclaim=bool(active and borrower is None and context.is_admin),
        )

    async def create(
        self,
        context: AuthenticatedContext,
        payload: MaterialCreateRequest,
        *,
        request_id: str,
        ip_prefix: str,
    ) -> MaterialCreateResponse:
        await self._active_actor(context)
        request_hash = hashlib.sha256(
            json.dumps(
                {"actor_id": str(context.user.id), **payload.model_dump(mode="json")},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        await self._repo.registration_lock(payload.idempotency_key)
        existing = await self._repo.by_registration_key(payload.idempotency_key)
        if existing:
            if existing.registration_request_hash != request_hash:
                raise _error(409, "IDEMPOTENCY_CONFLICT", "请求标识已用于其他登记。")
            return MaterialCreateResponse(
                material_id=existing.id,
                created_count=existing.registration_count,
            )
        first_id = None
        now = datetime.now(UTC)
        registration_count = payload.quantity * (2 if payload.paired else 1)
        for index in range(1, payload.quantity + 1):
            pair_key = uuid7() if payload.paired else None
            members = [
                (
                    payload.name,
                    payload.price,
                    payload.tech_group,
                )
            ]
            if payload.paired:
                assert (
                    payload.companion_name
                    and payload.companion_price
                    and payload.companion_tech_group
                )
                members.append(
                    (payload.companion_name, payload.companion_price, payload.companion_tech_group)
                )
            for member_index, (name, price, tech_group) in enumerate(members):
                material = Material(
                    id=uuid7(),
                    qr_token=uuid7(),
                    registration_key=(
                        payload.idempotency_key if index == 1 and member_index == 0 else uuid7()
                    ),
                    registration_request_hash=request_hash,
                    registration_count=registration_count,
                    name=name if payload.quantity == 1 else f"{name}-{index}",
                    price=Decimal(price),
                    tech_group=tech_group,
                    pair_key=pair_key,
                    created_by_user_id=context.user.id,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                )
                self._session.add(material)
                if first_id is None:
                    first_id = material.id
                self._audit(
                    context,
                    action="material.registered",
                    material_id=material.id,
                    request_id=request_id,
                    ip_prefix=ip_prefix,
                    summary={"paired": payload.paired, "batch_quantity": payload.quantity},
                    now=now,
                )
        await self._session.commit()
        assert first_id is not None
        return MaterialCreateResponse(material_id=first_id, created_count=registration_count)

    async def delete(
        self,
        context: AuthenticatedContext,
        material_id: UUID,
        *,
        request_id: str,
        ip_prefix: str,
    ) -> None:
        await self._active_actor(context)
        target = await self._repo.get(material_id)
        if target is None:
            raise _not_found()
        group = await self._repo.lock_group(target)
        self._assert_group(target, group, allow_deleted=True)
        if any(not self._actor_can_delete(context, member) for member in group):
            raise _error(403, "FORBIDDEN", "只有登记人或管理员可以删除物资。")
        if all(member.deleted_at is not None for member in group):
            return
        if any(member.deleted_at is not None for member in group):
            raise _conflict("配套物资状态异常，请联系管理员处理。")
        if await self._repo.active_loans([member.id for member in group]):
            raise _conflict("物资正在使用中，请先归还后再删除。")
        now = datetime.now(UTC)
        for member in group:
            member.deleted_at = now
            member.updated_at = now
            member.revision += 1
            self._audit(
                context,
                action="material.deleted",
                material_id=member.id,
                request_id=request_id,
                ip_prefix=ip_prefix,
                summary={"paired": target.pair_key is not None},
                now=now,
            )
        await self._session.commit()

    @staticmethod
    def _assert_group(
        target: Material, group: list[Material], *, allow_deleted: bool = False
    ) -> None:
        if len(group) != (2 if target.pair_key else 1) or (
            not allow_deleted and any(member.deleted_at is not None for member in group)
        ):
            raise _conflict("配套物资状态异常，请联系管理员处理。")

    def _scan_result(
        self,
        target: Material,
        group: list[Material],
        operation: Literal["CHECKOUT", "RETURN", "RECLAIM"],
        occurred_at: datetime,
    ) -> MaterialScanResponse:
        return MaterialScanResponse(
            material_id=target.id,
            related_material_ids=[m.id for m in group],
            material_name=" + ".join(m.name for m in group),
            operation=operation,
            occurred_at=occurred_at,
        )

    async def _replay(
        self,
        context: AuthenticatedContext,
        payload: MaterialScanRequest,
        target: Material,
        group: list[Material],
    ) -> MaterialScanResponse | None:
        loan = await self._repo.replay(payload.idempotency_key, operation=payload.operation)
        if loan is None:
            return None
        if loan.material_id != target.id or (
            loan.borrower_user_id != context.user.id
            and not (
                payload.operation == "RECLAIM"
                and context.is_admin
                and loan.borrower_user_id is None
            )
        ):
            raise _error(409, "IDEMPOTENCY_CONFLICT", "请求标识已用于其他物资操作。")
        occurred_at = loan.checked_out_at if payload.operation == "CHECKOUT" else loan.returned_at
        if occurred_at is None:
            raise _conflict()
        return self._scan_result(target, group, payload.operation, occurred_at)

    async def checkout(
        self,
        context: AuthenticatedContext,
        payload: MaterialScanRequest,
        *,
        request_id: str,
        ip_prefix: str,
    ) -> MaterialScanResponse:
        if payload.operation != "CHECKOUT":
            raise _error(400, "VALIDATION_ERROR", "扫码操作无效。")
        await self._active_actor(context)
        target = await self._repo.by_qr(payload.qr_token)
        if target is None:
            raise _not_found()
        group = await self._repo.lock_group(target)
        self._assert_group(target, group)
        replay = await self._replay(context, payload, target, group)
        if replay:
            return replay
        active = await self._repo.active_loans([member.id for member in group])
        if active:
            raise _conflict("该套物资已被领用，请刷新状态后重试。")
        now = datetime.now(UTC)
        for member in group:
            self._session.add(
                MaterialLoan(
                    id=uuid7(),
                    material_id=member.id,
                    borrower_user_id=context.user.id,
                    checkout_idempotency_key=(
                        payload.idempotency_key if member.id == target.id else uuid7()
                    ),
                    checked_out_at=now,
                )
            )
            member.updated_at = now
            member.revision += 1
            self._audit(
                context,
                action="material.checked_out",
                material_id=member.id,
                request_id=request_id,
                ip_prefix=ip_prefix,
                summary={"paired": target.pair_key is not None},
                now=now,
            )
        old_photos = await self._repo.previous_photos([member.id for member in group])
        cleanup_keys: set[str] = set()
        for loan in old_photos:
            if loan.photo_object_key:
                photo_key = loan.photo_object_key
                loan.photo_object_key = None
                loan.photo_mime_type = None
                loan.photo_size = None
                loan.photo_sha256 = None
                loan.photo_cleared_at = now
                cleanup_keys.add(photo_key)
        for photo_key in cleanup_keys:
            self._session.add(
                OutboxJob(
                    id=uuid7(),
                    job_type="delete_material_photo",
                    event_key=f"material-photo:{photo_key.rsplit('/', 1)[-1]}",
                    payload={"object_key": photo_key},
                    status="pending",
                    available_at=now,
                    attempt_count=0,
                    max_attempts=8,
                    created_at=now,
                )
            )
        await self._session.commit()
        return self._scan_result(target, group, "CHECKOUT", now)

    async def return_material(
        self,
        context: AuthenticatedContext,
        payload: MaterialScanRequest,
        *,
        photo: bytes,
        declared_mime: str,
        request_id: str,
        ip_prefix: str,
    ) -> MaterialScanResponse:
        if payload.operation not in {"RETURN", "RECLAIM"}:
            raise _error(400, "VALIDATION_ERROR", "扫码操作无效。")
        mime = detect_return_photo(photo, declared_mime)
        await self._active_actor(context)
        target = await self._repo.by_qr(payload.qr_token)
        if target is None or target.deleted_at is not None:
            raise _not_found()
        group = await self._repo.group(target)
        self._assert_group(target, group)
        replay = await self._replay(context, payload, target, group)
        if replay:
            return replay
        active = await self._repo.active_loans([member.id for member in group])
        self._assert_return_permission(context, payload, target, group, active)
        photo_key = f"materials/returns/{uuid7()}"
        await self._store.import_bytes(photo_key, photo, content_type=mime)
        replayed: MaterialScanResponse | None = None
        result: MaterialScanResponse | None = None
        try:
            await self._active_actor(context)
            current = await self._repo.by_qr(payload.qr_token)
            if current is None:
                raise _not_found()
            locked = await self._repo.lock_group(current)
            self._assert_group(current, locked)
            replay = await self._replay(context, payload, current, locked)
            if replay:
                await self._session.rollback()
                replayed = replay
            else:
                current_active = await self._repo.active_loans([member.id for member in locked])
                self._assert_return_permission(context, payload, current, locked, current_active)
                now = datetime.now(UTC)
                digest = hashlib.sha256(photo).hexdigest()
                for loan in current_active:
                    loan.returned_at = now
                    loan.return_idempotency_key = (
                        payload.idempotency_key if loan.material_id == current.id else uuid7()
                    )
                    loan.photo_object_key = photo_key
                    loan.photo_mime_type = mime
                    loan.photo_size = len(photo)
                    loan.photo_sha256 = digest
                    member = next(member for member in locked if member.id == loan.material_id)
                    member.updated_at = now
                    member.revision += 1
                    self._audit(
                        context,
                        action="material.reclaimed"
                        if payload.operation == "RECLAIM"
                        else "material.returned",
                        material_id=member.id,
                        request_id=request_id,
                        ip_prefix=ip_prefix,
                        summary={"paired": current.pair_key is not None, "photo_recorded": True},
                        now=now,
                    )
                await self._session.commit()
                result = self._scan_result(current, locked, payload.operation, now)
        except Exception:
            await self._session.rollback()
            await self._discard_unattached_photo(photo_key)
            raise
        if replayed is not None:
            await self._discard_unattached_photo(photo_key)
            return replayed
        assert result is not None
        return result

    async def _discard_unattached_photo(self, photo_key: str) -> None:
        try:
            await self._store.delete_object(photo_key)
        except ObjectStoreError:
            now = datetime.now(UTC)
            self._session.add(
                OutboxJob(
                    id=uuid7(),
                    job_type="delete_material_photo",
                    event_key=f"material-photo:{photo_key.rsplit('/', 1)[-1]}",
                    payload={"object_key": photo_key},
                    status="pending",
                    available_at=now,
                    attempt_count=0,
                    max_attempts=8,
                    created_at=now,
                )
            )
            await self._session.commit()

    @staticmethod
    def _assert_return_permission(
        context: AuthenticatedContext,
        payload: MaterialScanRequest,
        target: Material,
        group: list[Material],
        active: list[MaterialLoan],
    ) -> None:
        by_material = {loan.material_id: loan for loan in active}
        selected = by_material.get(target.id)
        if (
            selected is None
            or selected.id != payload.expected_active_loan_id
            or len(active) != len(group)
        ):
            raise _conflict()
        if payload.operation == "RECLAIM":
            if not context.is_admin or any(loan.borrower_user_id is not None for loan in active):
                raise _error(403, "FORBIDDEN", "仅管理员可处理已注销用户的遗留领用。")
        elif any(loan.borrower_user_id != context.user.id for loan in active):
            raise _error(403, "FORBIDDEN", "只有领用人可以归还物资。")

    async def photo_url(self, loan_id: UUID) -> str:
        loan = await self._repo.loan(loan_id)
        if loan is None or loan.photo_object_key is None or loan.photo_mime_type is None:
            raise _not_found()
        return await self._store.presign_inline(
            object_key=loan.photo_object_key,
            file_name="material-return-photo",
            content_type=loan.photo_mime_type,
            expires_seconds=300,
        )
