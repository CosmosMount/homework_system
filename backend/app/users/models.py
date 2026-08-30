from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base
from app.database.mixins import TimestampRevisionMixin


class Cohort(TimestampRevisionMixin, Base):
    __tablename__ = "cohorts"
    __table_args__ = (CheckConstraint("start_year BETWEEN 2000 AND 2200", name="start_year_range"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )


class Direction(TimestampRevisionMixin, Base):
    __tablename__ = "directions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )


class User(TimestampRevisionMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'admin')", name="role_allowed"),
        CheckConstraint(
            "status IN ('pending_email', 'active', 'disabled')",
            name="status_allowed",
        ),
        CheckConstraint(
            "email_normalized ~ '^[^@[:space:]]+@(connect\\.)?hkust-gz\\.edu\\.cn$'",
            name="campus_email",
        ),
        CheckConstraint(
            "status <> 'active' OR email_verified_at IS NOT NULL",
            name="active_email_verified",
        ),
        CheckConstraint(
            "status <> 'disabled' OR (disabled_at IS NOT NULL AND disabled_reason IS NOT NULL)",
            name="disabled_reason_present",
        ),
        Index("ix_users_status_created_at", "status", "created_at"),
        Index(
            "ix_users_cohort_direction_status",
            "cohort_id",
            "direction_id",
            "status",
        ),
        Index("ix_users_role_status", "role", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    student_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="student",
        server_default="student",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_email",
        server_default="pending_email",
    )
    cohort_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cohorts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    direction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("directions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
