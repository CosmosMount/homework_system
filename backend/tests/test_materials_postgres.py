"""Run only against a disposable database explicitly named material_test."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.service import AuthenticatedContext
from app.core.errors import ApplicationError
from app.materials.models import Material, MaterialLoan
from app.materials.schemas import MaterialCreateRequest, MaterialScanRequest
from app.materials.service import MaterialService
from app.notifications.models import OutboxJob
from app.uploads.object_store import MinioObjectStore
from app.users.models import User


def _context(user: User, *, admin: bool = False) -> AuthenticatedContext:
    return cast(
        AuthenticatedContext,
        SimpleNamespace(user=user, is_admin=admin),
    )


def _user(role: str) -> User:
    now = datetime.now(UTC)
    key = uuid4().hex[:12]
    email = f"material-{key}@connect.hkust-gz.edu.cn"
    return User(
        id=uuid4(),
        email=email,
        email_normalized=email,
        student_number=key,
        full_name=f"测试{key}",
        password_hash="test-only",
        role=role,
        status="active",
        email_verified_at=now,
        password_changed_at=now,
        created_at=now,
        updated_at=now,
        revision=1,
    )


@pytest.mark.asyncio
async def test_material_cycle_with_real_postgres_constraints_and_account_erasure() -> None:
    url = os.environ.get("MATERIAL_TEST_DATABASE_URL", "")
    if (
        not url
        or make_url(url).database != "material_test"
        or make_url(url).host not in {"127.0.0.1", "localhost"}
    ):
        pytest.skip("仅在显式隔离 material_test 数据库运行")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = Mock(spec=MinioObjectStore)
    store.import_bytes = AsyncMock()
    store.delete_object = AsyncMock()
    users = [_user("admin"), _user("student"), _user("student")]
    try:
        async with factory() as session:
            session.add_all(users)
            await session.commit()

        async with factory() as session:
            svc = MaterialService(session, cast(MinioObjectStore, store))
            created = await svc.create(
                _context(users[1]),
                MaterialCreateRequest(
                    name="无线麦克",
                    price="200",
                    tech_group="通用",
                    paired=True,
                    companion_name="接收器",
                    companion_price="100",
                    companion_tech_group="硬件",
                    idempotency_key=uuid4(),
                ),
                request_id="material-pg-test",
                ip_prefix="127.0.0.0/24",
            )
            first = await session.get(Material, created.material_id)
            assert first is not None
            assert first.registration_count == 2
            pair = list(
                (
                    await session.scalars(
                        select(Material).where(Material.pair_key == first.pair_key)
                    )
                ).all()
            )
            assert len(pair) == 2
            replay = await svc.create(
                _context(users[1]),
                MaterialCreateRequest(
                    name="无线麦克",
                    price="200",
                    tech_group="通用",
                    paired=True,
                    companion_name="接收器",
                    companion_price="100",
                    companion_tech_group="硬件",
                    idempotency_key=first.registration_key,
                ),
                request_id="material-pg-test",
                ip_prefix="127.0.0.0/24",
            )
            assert replay.material_id == first.id and replay.created_count == 2
            with pytest.raises(ApplicationError) as changed:
                await svc.create(
                    _context(users[1]),
                    MaterialCreateRequest(
                        name="无线麦克",
                        price="200",
                        tech_group="通用",
                        quantity=3,
                        paired=True,
                        companion_name="接收器",
                        companion_price="100",
                        companion_tech_group="硬件",
                        idempotency_key=first.registration_key,
                    ),
                    request_id="material-pg-test",
                    ip_prefix="127.0.0.0/24",
                )
            assert changed.value.code == "IDEMPOTENCY_CONFLICT"

        async def checkout(user: User) -> str:
            async with factory() as session:
                svc = MaterialService(session, cast(MinioObjectStore, store))
                try:
                    await svc.checkout(
                        _context(user),
                        MaterialScanRequest(
                            qr_token=first.qr_token,
                            operation="CHECKOUT",
                            expected_active_loan_id=None,
                            idempotency_key=uuid4(),
                        ),
                        request_id="material-pg-test",
                        ip_prefix="127.0.0.0/24",
                    )
                    return "success"
                except ApplicationError as exc:
                    return exc.code

        outcomes = await asyncio.gather(checkout(users[1]), checkout(users[2]))
        assert sorted(outcomes) == ["STATE_CONFLICT", "success"]
        async with factory() as session:
            active = list(
                (
                    await session.scalars(
                        select(MaterialLoan).where(MaterialLoan.returned_at.is_(None))
                    )
                ).all()
            )
            assert len(active) == 2
            borrower = next(user for user in users[1:] if user.id == active[0].borrower_user_id)
            other = next(user for user in users[1:] if user.id != borrower.id)
            scanned_loan = next(loan for loan in active if loan.material_id == first.id)

        async with factory() as session:
            svc = MaterialService(session, cast(MinioObjectStore, store))
            payload = MaterialScanRequest(
                qr_token=first.qr_token,
                operation="RETURN",
                expected_active_loan_id=scanned_loan.id,
                idempotency_key=uuid4(),
            )
            with pytest.raises(ApplicationError) as denied:
                await svc.return_material(
                    _context(other),
                    payload,
                    photo=b"\x89PNG\r\n\x1a\n",
                    declared_mime="image/png",
                    request_id="material-pg-test",
                    ip_prefix="127.0.0.0/24",
                )
            assert denied.value.code == "FORBIDDEN"

        async with factory() as session:
            svc = MaterialService(session, cast(MinioObjectStore, store))
            await svc.return_material(
                _context(borrower),
                payload,
                photo=b"\x89PNG\r\n\x1a\n",
                declared_mime="image/png",
                request_id="material-pg-test",
                ip_prefix="127.0.0.0/24",
            )
            returned = list(
                (
                    await session.scalars(
                        select(MaterialLoan).where(MaterialLoan.returned_at.is_not(None))
                    )
                ).all()
            )
            assert len(returned) == 2
            assert returned[0].photo_object_key == returned[1].photo_object_key
            old_photo_key = returned[0].photo_object_key

        assert await checkout(other) == "success"
        async with factory() as session:
            returned = list(
                (
                    await session.scalars(
                        select(MaterialLoan).where(MaterialLoan.returned_at.is_not(None))
                    )
                ).all()
            )
            assert all(loan.photo_object_key is None and loan.photo_cleared_at for loan in returned)
            jobs = list(
                (
                    await session.scalars(
                        select(OutboxJob).where(OutboxJob.job_type == "delete_material_photo")
                    )
                ).all()
            )
            assert len([job for job in jobs if job.payload.get("object_key") == old_photo_key]) == 1
            await session.execute(text("SET LOCAL pnx.account_erasure = 'on'"))
            await session.delete(other)
            await session.commit()

        async with factory() as session:
            svc = MaterialService(session, cast(MinioObjectStore, store))
            view = await svc.scan_view(first.qr_token, _context(users[0], admin=True))
            assert view.active_loan and view.active_loan.borrower_user_id is None
            assert view.can_reclaim
            await svc.return_material(
                _context(users[0], admin=True),
                MaterialScanRequest(
                    qr_token=first.qr_token,
                    operation="RECLAIM",
                    expected_active_loan_id=view.active_loan.id,
                    idempotency_key=uuid4(),
                ),
                photo=b"\x89PNG\r\n\x1a\n",
                declared_mime="image/png",
                request_id="material-pg-test",
                ip_prefix="127.0.0.0/24",
            )
            await svc.delete(
                _context(users[0], admin=True),
                first.id,
                request_id="material-pg-test",
                ip_prefix="127.0.0.0/24",
            )
            assert (await svc.list_materials()).total_count == 0
            assert (await svc.detail(first.id, _context(users[0], admin=True))).deleted_at

        async with factory() as session:
            svc = MaterialService(session, cast(MinioObjectStore, store))
            for name, quantity in [("库存件", 100), ("库存补充", 2)]:
                await svc.create(
                    _context(users[0], admin=True),
                    MaterialCreateRequest(
                        name=name,
                        price="1",
                        tech_group="通用",
                        quantity=quantity,
                        idempotency_key=uuid4(),
                    ),
                    request_id="material-pg-test",
                    ip_prefix="127.0.0.0/24",
                )
            page_one = await svc.list_materials(page=1)
            page_two = await svc.list_materials(page=2)
            assert len(page_one.items) == 100 and page_one.has_more
            assert len(page_two.items) == 2 and not page_two.has_more
            assert page_one.total_count == page_two.total_count == 102
            assert [item.name for item in [*page_one.items, *page_two.items]] == [
                "库存补充-1",
                "库存补充-2",
                *[f"库存件-{i}" for i in range(1, 101)],
            ]
            # Updating an old item must not move it out of numeric registration order.
            old = await session.get(Material, page_two.items[-1].id)
            assert old is not None
            old.updated_at = datetime.now(UTC) + timedelta(hours=1)
            await session.commit()
            assert [item.id for item in (await svc.list_materials(page=2)).items] == [
                item.id for item in page_two.items
            ]
            await svc.create(
                _context(users[0], admin=True),
                MaterialCreateRequest(
                    name="排序主件",
                    price="1",
                    tech_group="通用",
                    quantity=100,
                    paired=True,
                    companion_name="排序配件",
                    companion_price="1",
                    companion_tech_group="硬件",
                    idempotency_key=uuid4(),
                ),
                request_id="material-order-test",
                ip_prefix="127.0.0.0/24",
            )
            first_page = await svc.list_materials(query="排序", page=1)
            second_page = await svc.list_materials(query="排序", page=2)
            assert [item.name for item in first_page.items] == [
                f"排序主件-{i}" for i in range(1, 101)
            ]
            assert [item.name for item in second_page.items] == [
                f"排序配件-{i}" for i in range(1, 101)
            ]
            assert first_page.has_more and not second_page.has_more
    finally:
        await engine.dispose()
