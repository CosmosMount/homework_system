from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base

_UPLOAD_STATUS_SQL = (
    "('initialized', 'uploading', 'verifying', 'available', 'rejected', 'aborted', 'expired')"
)


class StoredFile(Base):
    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('announcement_attachment', 'assignment_submission', "
            "'competition_submission')",
            name="purpose_allowed",
        ),
        CheckConstraint(f"status IN {_UPLOAD_STATUS_SQL}", name="status_allowed"),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        Index("ix_files_owner_status_created_at", "owner_user_id", "status", "created_at"),
        Index("ix_files_status_created_at", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    declared_media_type: Mapped[str] = mapped_column(String(200), nullable=False)
    detected_media_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UploadSession(Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        CheckConstraint(f"status IN {_UPLOAD_STATUS_SQL}", name="status_allowed"),
        CheckConstraint("part_size_bytes >= 5242880", name="part_size_minimum"),
        CheckConstraint("part_count >= 1", name="part_count_positive"),
        CheckConstraint("expected_size_bytes >= 0", name="expected_size_nonnegative"),
        CheckConstraint("expected_sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        Index(
            "uq_upload_sessions_user_idempotency",
            "user_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_upload_sessions_status_expiry", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    context_type: Mapped[str] = mapped_column(String(40), nullable=False)
    context_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    minio_upload_id: Mapped[str] = mapped_column(Text, nullable=False)
    part_size_bytes: Mapped[int] = mapped_column(nullable=False)
    part_count: Mapped[int] = mapped_column(nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class UploadPart(Base):
    __tablename__ = "upload_parts"
    __table_args__ = (
        CheckConstraint("part_number >= 1", name="part_number_positive"),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
    )

    upload_session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("upload_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    part_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    etag: Mapped[str] = mapped_column(String(200), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
