from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base
from app.database.mixins import TimestampRevisionMixin


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "latest_version_id"],
            ["submission_versions.submission_id", "submission_versions.id"],
            name="fk_submissions_latest_version_same_submission",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        Index(
            "uq_submissions_assignment_owner",
            "assignment_id",
            "owner_user_id",
            unique=True,
            postgresql_where=text("assignment_id IS NOT NULL"),
        ),
        Index(
            "uq_submissions_competition_task_owner",
            "competition_task_id",
            "owner_team_id",
            unique=True,
            postgresql_where=text("competition_task_id IS NOT NULL"),
        ),
        CheckConstraint(
            "(assignment_id IS NOT NULL AND competition_task_id IS NULL "
            "AND owner_user_id IS NOT NULL AND owner_team_id IS NULL) OR "
            "(assignment_id IS NULL AND competition_task_id IS NOT NULL "
            "AND owner_user_id IS NULL AND owner_team_id IS NOT NULL)",
            name="owner_target_pair",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    assignment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assignments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    competition_task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("competition_tasks.id", ondelete="RESTRICT"),
        nullable=True,
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    owner_team_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=True,
    )
    latest_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SubmissionVersion(Base):
    __tablename__ = "submission_versions"
    __table_args__ = (
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint(
            "total_file_bytes BETWEEN 0 AND 2147483648",
            name="total_file_bytes_range",
        ),
        UniqueConstraint(
            "submission_id",
            "id",
            name="uq_submission_versions_submission_id_id",
        ),
        Index(
            "uq_submission_versions_number",
            "submission_id",
            "version_number",
            unique=True,
        ),
        Index(
            "uq_submission_versions_submitter_idempotency",
            "submitted_by",
            "idempotency_key",
            unique=True,
        ),
        Index(
            "ix_submission_versions_submission_submitted_at",
            "submission_id",
            "submitted_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    text_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    total_file_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VersionFile(Base):
    __tablename__ = "version_files"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        Index("uq_version_files_file_id", "file_id", unique=True),
        Index(
            "uq_version_files_display_order",
            "version_id",
            "display_order",
            unique=True,
        ),
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("submission_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("files.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Feedback(TimestampRevisionMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("length(trim(body_markdown)) > 0", name="body_present"),
        Index("uq_feedback_version_id", "version_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("submission_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("response_status BETWEEN 100 AND 599", name="response_status_range"),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="request_hash_format",
        ),
        Index(
            "uq_idempotency_records_scope",
            "user_id",
            "endpoint_key",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_idempotency_records_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    endpoint_key: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
