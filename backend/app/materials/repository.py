from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import ColumnElement, Numeric, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.materials.models import Material, MaterialLoan
from app.users.models import User


class MaterialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, material_id: UUID) -> Material | None:
        return cast(Material | None, await self.session.get(Material, material_id))

    async def by_qr(self, qr_token: UUID) -> Material | None:
        return cast(
            Material | None,
            await self.session.scalar(select(Material).where(Material.qr_token == qr_token)),
        )

    async def by_registration_key(self, key: UUID) -> Material | None:
        return cast(
            Material | None,
            await self.session.scalar(select(Material).where(Material.registration_key == key)),
        )

    async def lock_group(self, target: Material) -> list[Material]:
        condition = (
            Material.pair_key == target.pair_key if target.pair_key else Material.id == target.id
        )
        return list(
            (
                await self.session.scalars(
                    select(Material).where(condition).order_by(Material.id).with_for_update()
                )
            ).all()
        )

    async def group(self, target: Material) -> list[Material]:
        condition = (
            Material.pair_key == target.pair_key if target.pair_key else Material.id == target.id
        )
        return list((await self.session.scalars(select(Material).where(condition))).all())

    async def active_loans(self, material_ids: Sequence[UUID]) -> list[MaterialLoan]:
        return list(
            (
                await self.session.scalars(
                    select(MaterialLoan)
                    .where(
                        MaterialLoan.material_id.in_(material_ids),
                        MaterialLoan.returned_at.is_(None),
                    )
                    .order_by(MaterialLoan.material_id)
                )
            ).all()
        )

    async def history(self, material_id: UUID, *, limit: int = 20) -> list[MaterialLoan]:
        return list(
            (
                await self.session.scalars(
                    select(MaterialLoan)
                    .where(MaterialLoan.material_id == material_id)
                    .order_by(MaterialLoan.checked_out_at.desc(), MaterialLoan.id.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def previous_photos(self, material_ids: Sequence[UUID]) -> list[MaterialLoan]:
        return list(
            (
                await self.session.scalars(
                    select(MaterialLoan)
                    .where(
                        MaterialLoan.material_id.in_(material_ids),
                        MaterialLoan.returned_at.is_not(None),
                        MaterialLoan.photo_object_key.is_not(None),
                    )
                    .with_for_update()
                )
            ).all()
        )

    async def replay(self, key: UUID, *, operation: str) -> MaterialLoan | None:
        column = (
            MaterialLoan.checkout_idempotency_key
            if operation == "CHECKOUT"
            else MaterialLoan.return_idempotency_key
        )
        return cast(
            MaterialLoan | None,
            await self.session.scalar(select(MaterialLoan).where(column == key)),
        )

    async def loan(self, loan_id: UUID) -> MaterialLoan | None:
        return cast(MaterialLoan | None, await self.session.get(MaterialLoan, loan_id))

    async def names(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = await self.session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
        return {user_id: full_name for user_id, full_name in rows.all()}

    async def list_page(
        self, *, query: str, tech_group: str | None, status: str | None, page: int
    ) -> tuple[list[Material], int, int]:
        visible = Material.deleted_at.is_(None)
        total = int(
            await self.session.scalar(select(func.count()).select_from(Material).where(visible))
            or 0
        )
        in_use = int(
            await self.session.scalar(
                select(func.count())
                .select_from(MaterialLoan)
                .join(Material, Material.id == MaterialLoan.material_id)
                .where(MaterialLoan.returned_at.is_(None), visible)
            )
            or 0
        )
        filters: list[ColumnElement[bool]] = [visible]
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            filters.append(Material.name.ilike(f"%{escaped}%", escape="\\"))
        if tech_group:
            filters.append(Material.tech_group == tech_group)
        if status == "AVAILABLE":
            filters.append(
                ~select(MaterialLoan.id)
                .where(
                    MaterialLoan.material_id == Material.id,
                    MaterialLoan.returned_at.is_(None),
                )
                .exists()
            )
        elif status == "IN_USE":
            filters.append(
                select(MaterialLoan.id)
                .where(
                    MaterialLoan.material_id == Material.id,
                    MaterialLoan.returned_at.is_(None),
                )
                .exists()
            )
        rows = list(
            (
                await self.session.scalars(
                    select(Material)
                    .where(*filters)
                    .order_by(
                        Material.created_at.desc(),
                        func.regexp_replace(Material.name, r"-[0-9]+$", ""),
                        func.coalesce(
                            func.substring(Material.name, r"-([0-9]+)$").cast(Numeric), 0
                        ),
                        Material.name,
                        Material.id,
                    )
                    .limit(101)
                    .offset((page - 1) * 100)
                )
            ).all()
        )
        return rows, total, in_use

    async def pair_members(self, pair_keys: set[UUID]) -> list[Material]:
        if not pair_keys:
            return []
        return list(
            (
                await self.session.scalars(select(Material).where(Material.pair_key.in_(pair_keys)))
            ).all()
        )

    async def lock_active_user(self, user_id: UUID) -> User | None:
        return cast(
            User | None,
            await self.session.scalar(select(User).where(User.id == user_id).with_for_update()),
        )

    async def registration_lock(self, key: UUID) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"material:register:{key}"},
        )
