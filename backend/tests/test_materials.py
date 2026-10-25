from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_authenticated_context, require_csrf
from app.auth.service import AuthenticatedContext
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.main import create_app
from app.materials.models import Material, MaterialLoan
from app.materials.router import router as materials_router
from app.materials.schemas import MaterialCreateRequest, MaterialScanRequest
from app.materials.service import MaterialService, detect_return_photo
from app.notifications.models import OutboxJob
from app.uploads.object_store import MinioObjectStore, ObjectStoreError


def actor(*, admin: bool = False, user_id: object | None = None) -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(
            user=SimpleNamespace(id=user_id or uuid4(), status="active"),
            is_admin=admin,
        ),
    )


def material(
    *, name: str = "示波器", pair_key: object | None = None, owner_id: object | None = None
) -> Material:
    now = datetime.now(UTC)
    return Material(
        id=uuid4(),
        qr_token=uuid4(),
        registration_key=uuid4(),
        registration_request_hash="a" * 64,
        registration_count=1,
        name=name,
        price=Decimal("12.50"),
        tech_group="硬件",
        pair_key=pair_key,
        created_by_user_id=owner_id or uuid4(),
        created_at=now,
        updated_at=now,
        revision=1,
    )


def loan(item: Material, borrower_id: object, *, photo_key: str | None = None) -> MaterialLoan:
    now = datetime.now(UTC)
    return MaterialLoan(
        id=uuid4(),
        material_id=item.id,
        borrower_user_id=borrower_id,
        checkout_idempotency_key=uuid4(),
        checked_out_at=now,
        returned_at=now if photo_key else None,
        return_idempotency_key=uuid4() if photo_key else None,
        photo_object_key=photo_key,
        photo_mime_type="image/png" if photo_key else None,
        photo_size=8 if photo_key else None,
        photo_sha256="a" * 64 if photo_key else None,
    )


def service() -> tuple[MaterialService, Mock, Mock, Mock]:
    session = Mock(spec=AsyncSession)
    session.add = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    store = Mock(spec=MinioObjectStore)
    store.import_bytes = AsyncMock()
    store.delete_object = AsyncMock()
    result = MaterialService(cast(AsyncSession, session), cast(MinioObjectStore, store))
    repo = Mock()
    repo.lock_active_user = AsyncMock(return_value=SimpleNamespace(status="active"))
    repo.registration_lock = AsyncMock()
    repo.by_registration_key = AsyncMock(return_value=None)
    repo.by_qr = AsyncMock()
    repo.get = AsyncMock()
    repo.group = AsyncMock()
    repo.lock_group = AsyncMock()
    repo.active_loans = AsyncMock(return_value=[])
    repo.previous_photos = AsyncMock(return_value=[])
    repo.replay = AsyncMock(return_value=None)
    result._repo = repo  # type: ignore[assignment]
    return result, session, store, repo


def test_return_photo_rejects_oversize_and_disguised_content() -> None:
    assert detect_return_photo(b"\x89PNG\r\n\x1a\n", "image/png") == "image/png"
    assert detect_return_photo(b"\x00\x00\x00\x0cftypavif", "image/avif") == "image/avif"
    for content, mime in [
        (b"\x89PNG\r\n\x1a\n", "image/jpeg"),
        (b"<svg></svg>", "image/png"),
        (b"\x89PNG\r\n\x1a\n", "image/svg+xml"),
        (b"x" * (8 * 1024 * 1024 + 1), "image/png"),
    ]:
        with pytest.raises(ApplicationError):
            detect_return_photo(content, mime)


@pytest.mark.asyncio
async def test_paired_batch_registration_is_atomic_and_idempotent() -> None:
    svc, session, _, repo = service()
    context = actor()
    payload = MaterialCreateRequest(
        name="无线麦克",
        price="200",
        tech_group="通用",
        quantity=3,
        paired=True,
        companion_name="接收器",
        companion_price="100",
        companion_tech_group="硬件",
        idempotency_key=uuid4(),
    )
    result = await svc.create(context, payload, request_id="test", ip_prefix="127.0.0.0/24")
    created = [
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Material)
    ]
    assert [item.name for item in created] == [
        "无线麦克-1",
        "接收器-1",
        "无线麦克-2",
        "接收器-2",
        "无线麦克-3",
        "接收器-3",
    ]
    assert len({item.qr_token for item in created}) == 6
    assert len({item.pair_key for item in created}) == 3
    assert created[0].registration_key == payload.idempotency_key
    assert all(item.registration_count == 6 for item in created)
    assert result.material_id == created[0].id
    assert result.created_count == 6
    session.commit.assert_awaited_once()
    repo.by_registration_key.return_value = created[0]
    await svc.create(context, payload, request_id="test", ip_prefix="127.0.0.0/24")
    assert session.commit.await_count == 1
    with pytest.raises(ApplicationError) as error:
        await svc.create(
            context,
            payload.model_copy(update={"quantity": 2}),
            request_id="test",
            ip_prefix="127.0.0.0/24",
        )
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_paired_checkout_clears_previous_photo_once_and_stale_checkout_fails() -> None:
    svc, session, _, repo = service()
    context = actor()
    pair = uuid4()
    first = material(pair_key=pair)
    second = material(name="探头", pair_key=pair)
    old_photo = "materials/returns/" + str(uuid4())
    old = [
        loan(first, context.user.id, photo_key=old_photo),
        loan(second, context.user.id, photo_key=old_photo),
    ]
    repo.by_qr.return_value = first
    repo.lock_group.return_value = [first, second]
    repo.previous_photos.return_value = old
    payload = MaterialScanRequest(
        qr_token=first.qr_token,
        operation="CHECKOUT",
        expected_active_loan_id=None,
        idempotency_key=uuid4(),
    )
    result = await svc.checkout(context, payload, request_id="test", ip_prefix="127.0.0.0/24")
    new_loans = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], MaterialLoan)
    ]
    cleanup = [
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], OutboxJob)
    ]
    assert len(new_loans) == 2
    assert len(cleanup) == 1
    assert cleanup[0].payload["object_key"] == old_photo
    assert all(item.photo_object_key is None and item.photo_cleared_at for item in old)
    assert result.related_material_ids == [first.id, second.id]
    repo.active_loans.return_value = new_loans
    with pytest.raises(ApplicationError) as error:
        await svc.checkout(
            context,
            MaterialScanRequest(
                qr_token=first.qr_token,
                operation="CHECKOUT",
                expected_active_loan_id=None,
                idempotency_key=uuid4(),
            ),
            request_id="test",
            ip_prefix="127.0.0.0/24",
        )
    assert error.value.code == "STATE_CONFLICT"


@pytest.mark.asyncio
async def test_paired_return_requires_borrower_and_shares_one_photo() -> None:
    svc, session, store, repo = service()
    context = actor()
    pair = uuid4()
    first = material(pair_key=pair)
    second = material(name="探头", pair_key=pair)
    active = [loan(first, context.user.id), loan(second, context.user.id)]
    repo.by_qr.return_value = first
    repo.group.return_value = [first, second]
    repo.lock_group.return_value = [first, second]
    repo.active_loans.return_value = active
    payload = MaterialScanRequest(
        qr_token=first.qr_token,
        operation="RETURN",
        expected_active_loan_id=active[0].id,
        idempotency_key=uuid4(),
    )
    photo = b"\x89PNG\r\n\x1a\n"
    result = await svc.return_material(
        context,
        payload,
        photo=photo,
        declared_mime="image/png",
        request_id="test",
        ip_prefix="127.0.0.0/24",
    )
    assert result.operation == "RETURN"
    assert active[0].returned_at == active[1].returned_at
    assert active[0].photo_object_key == active[1].photo_object_key
    assert active[0].photo_object_key.startswith("materials/returns/")
    store.import_bytes.assert_awaited_once()
    session.commit.assert_awaited_once()

    other = actor()
    active[0].returned_at = None
    active[1].returned_at = None
    with pytest.raises(ApplicationError) as error:
        await svc.return_material(
            other,
            payload,
            photo=photo,
            declared_mime="image/png",
            request_id="test",
            ip_prefix="127.0.0.0/24",
        )
    assert error.value.code == "FORBIDDEN"
    assert store.import_bytes.await_count == 1


@pytest.mark.asyncio
async def test_return_race_discards_uploaded_photo_with_outbox_fallback() -> None:
    svc, session, store, repo = service()
    context = actor()
    item = material()
    active = loan(item, context.user.id)
    already_returned = loan(item, context.user.id, photo_key="materials/returns/previous")
    repo.by_qr.return_value = item
    repo.group.return_value = [item]
    repo.lock_group.return_value = [item]
    repo.active_loans.return_value = [active]
    repo.replay.side_effect = [None, already_returned]
    store.delete_object.side_effect = ObjectStoreError("OBJECT_DELETE_FAILED")
    result = await svc.return_material(
        context,
        MaterialScanRequest(
            qr_token=item.qr_token,
            operation="RETURN",
            expected_active_loan_id=active.id,
            idempotency_key=uuid4(),
        ),
        photo=b"\x89PNG\r\n\x1a\n",
        declared_mime="image/png",
        request_id="test",
        ip_prefix="127.0.0.0/24",
    )
    assert result.operation == "RETURN"
    session.rollback.assert_awaited_once()
    assert (
        len([call for call in session.add.call_args_list if isinstance(call.args[0], OutboxJob)])
        == 1
    )


@pytest.mark.asyncio
async def test_delete_requires_owner_or_admin_and_no_active_loan() -> None:
    svc, session, _, repo = service()
    owner = actor()
    item = material(owner_id=owner.user.id)
    repo.get.return_value = item
    repo.lock_group.return_value = [item]
    with pytest.raises(ApplicationError) as error:
        await svc.delete(actor(), item.id, request_id="test", ip_prefix="127.0.0.0/24")
    assert error.value.code == "FORBIDDEN"
    repo.active_loans.return_value = [loan(item, owner.user.id)]
    with pytest.raises(ApplicationError) as error:
        await svc.delete(owner, item.id, request_id="test", ip_prefix="127.0.0.0/24")
    assert error.value.code == "STATE_CONFLICT"
    session.commit.assert_not_awaited()


def test_material_routes_require_authentication_and_writes_require_csrf() -> None:
    app = create_app(Settings(app_env="test", trusted_hosts="testserver"))
    assert "/api/v1/materials" in app.openapi()["paths"]
    material_routes = list(materials_router.routes)
    assert len(material_routes) == 8

    def calls(dependant: object) -> set[object]:
        direct = getattr(dependant, "dependencies", [])
        return {getattr(item, "call", None) for item in direct} | {
            call for item in direct for call in calls(item)
        }

    for route in material_routes:
        dependencies = calls(route.dependant)
        assert get_authenticated_context in dependencies
        if route.methods & {"POST", "DELETE"}:
            assert require_csrf in dependencies


def test_material_migration_has_reversible_tables_and_guards() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/20261013_0031_material_management.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20261003_0030"' in source
    assert "uq_material_loans_active_material" in source
    assert "protect_material_identity" in source
    assert "protect_material_loan_history" in source
    assert 'op.drop_table("material_loans")' in source
    assert 'op.drop_table("materials")' in source
