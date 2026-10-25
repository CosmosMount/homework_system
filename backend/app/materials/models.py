from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base
from app.database.mixins import TimestampRevisionMixin


class Material(TimestampRevisionMixin, Base):
    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 200", name="name_present"),
        CheckConstraint("price >= 0 AND price <= 9999999999.99", name="price_range"),
        CheckConstraint("registration_count BETWEEN 1 AND 200", name="registration_count_range"),
        CheckConstraint(
            "registration_request_hash ~ '^[0-9a-f]{64}$'", name="registration_hash_format"
        ),
        CheckConstraint(
            "tech_group IN ('机械', '硬件', '电控', '算法', '宣运', '通用')",
            name="tech_group_allowed",
        ),
        Index("ix_materials_tech_group_created", "tech_group", "created_at"),
        Index("ix_materials_pair_key", "pair_key"),
        Index("ix_materials_visible_updated", "deleted_at", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    qr_token: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True, default=uuid7
    )
    registration_key: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True
    )
    registration_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    registration_count: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tech_group: Mapped[str] = mapped_column(String(32), nullable=False)
    pair_key: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MaterialLoan(Base):
    __tablename__ = "material_loans"
    __table_args__ = (
        CheckConstraint(
            "(returned_at IS NULL AND return_idempotency_key IS NULL AND "
            "photo_object_key IS NULL AND photo_cleared_at IS NULL) OR "
            "(returned_at IS NOT NULL AND return_idempotency_key IS NOT NULL AND "
            "((photo_object_key IS NOT NULL AND photo_cleared_at IS NULL) OR "
            "(photo_object_key IS NULL AND photo_cleared_at IS NOT NULL)))",
            name="return_photo_lifecycle",
        ),
        CheckConstraint("returned_at IS NULL OR returned_at >= checked_out_at", name="return_time"),
        CheckConstraint(
            "(photo_object_key IS NULL AND photo_mime_type IS NULL AND photo_size IS NULL "
            "AND photo_sha256 IS NULL) OR (photo_object_key IS NOT NULL AND "
            "photo_mime_type IS NOT NULL AND photo_size > 0 AND photo_size <= 8388608 "
            "AND photo_sha256 ~ '^[0-9a-f]{64}$')",
            name="photo_metadata_consistent",
        ),
        Index(
            "uq_material_loans_active_material",
            "material_id",
            unique=True,
            postgresql_where=text("returned_at IS NULL"),
        ),
        Index("ix_material_loans_material_history", "material_id", "checked_out_at"),
        Index("ix_material_loans_borrower_active", "borrower_user_id", "returned_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    material_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("materials.id", ondelete="RESTRICT"), nullable=False
    )
    borrower_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    checkout_idempotency_key: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True
    )
    return_idempotency_key: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, unique=True
    )
    checked_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    photo_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_mime_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    photo_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    photo_cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
