from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base
from app.database.mixins import TimestampRevisionMixin

_ASSIGNMENT_STATUS_SQL = "('draft', 'published', 'closed', 'archived')"


class Assignment(TimestampRevisionMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(f"status IN {_ASSIGNMENT_STATUS_SQL}", name="status_allowed"),
        CheckConstraint(
            "audience_match IN ('union', 'intersection')",
            name="audience_match_allowed",
        ),
        CheckConstraint(
            "max_total_bytes BETWEEN 1 AND 2147483648",
            name="max_total_bytes_range",
        ),
        CheckConstraint(
            "cardinality(allowed_extensions) >= 1",
            name="allowed_extensions_present",
        ),
        CheckConstraint("deadline > publish_at", name="deadline_after_publish"),
        CheckConstraint(
            "status = 'draft' OR published_at IS NOT NULL",
            name="published_at_present",
        ),
        CheckConstraint(
            "status NOT IN ('closed', 'archived') OR closed_at IS NOT NULL",
            name="closed_at_present",
        ),
        CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="archived_at_present",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="deleted_requires_archived",
        ),
        Index("ix_assignments_status_publish_at", "status", "publish_at"),
        Index("ix_assignments_status_deadline", "status", "deadline"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    description_html: Mapped[str] = mapped_column(Text, nullable=False)
    training_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    submission_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    all_students: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    audience_match: Mapped[str] = mapped_column(
        String(16), nullable=False, default="intersection", server_default="intersection"
    )
    allowed_extensions: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)),
        nullable=False,
    )
    max_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssignmentCohort(Base):
    __tablename__ = "assignment_cohorts"

    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assignments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cohort_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cohorts.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class AssignmentDirection(Base):
    __tablename__ = "assignment_directions"

    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assignments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    direction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("directions.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class AssignmentAudienceUser(Base):
    __tablename__ = "assignment_audience_users"
    __table_args__ = (
        Index(
            "ix_assignment_audience_users_user_assignment",
            "user_id",
            "assignment_id",
        ),
    )

    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assignments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cohort_id_at_publish: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cohorts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    direction_id_at_publish: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("directions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssignmentExtension(TimestampRevisionMixin, Base):
    __tablename__ = "assignment_extensions"
    __table_args__ = (
        CheckConstraint("length(trim(reason)) > 0", name="reason_present"),
        Index("ix_assignment_extensions_user_assignment", "user_id", "assignment_id"),
    )

    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assignments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    extended_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    granted_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class AssignmentExcellentSubmission(Base):
    __tablename__ = "assignment_excellent_submissions"
    __table_args__ = (
        Index(
            "uq_assignment_excellent_submissions_version_id",
            "version_id",
            unique=True,
        ),
    )

    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assignments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "submission_versions.id",
            name="fk_assignment_excellent_version_submission_versions",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    marked_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
