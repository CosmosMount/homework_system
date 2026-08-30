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


class Announcement(TimestampRevisionMixin, Base):
    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'published', 'archived')",
            name="status_allowed",
        ),
        CheckConstraint(
            "audience_match IN ('union', 'intersection')",
            name="audience_match_allowed",
        ),
        CheckConstraint(
            "status <> 'scheduled' OR publish_at IS NOT NULL",
            name="scheduled_publish_at_present",
        ),
        CheckConstraint(
            "status NOT IN ('published', 'archived') OR published_at IS NOT NULL",
            name="published_at_present",
        ),
        CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="archived_at_present",
        ),
        Index("ix_announcements_status_published_at", "status", "published_at"),
        Index("ix_announcements_status_publish_at", "status", "publish_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    all_students: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    audience_match: Mapped[str] = mapped_column(
        String(16), nullable=False, default="intersection", server_default="intersection"
    )
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pinned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    send_email: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnnouncementCohort(Base):
    __tablename__ = "announcement_cohorts"

    announcement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("announcements.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cohort_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="RESTRICT"), primary_key=True
    )


class AnnouncementDirection(Base):
    __tablename__ = "announcement_directions"

    announcement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("announcements.id", ondelete="CASCADE"),
        primary_key=True,
    )
    direction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("directions.id", ondelete="RESTRICT"), primary_key=True
    )


class AnnouncementFile(Base):
    __tablename__ = "announcement_files"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        Index(
            "uq_announcement_files_display_order",
            "announcement_id",
            "display_order",
            unique=True,
        ),
        Index("uq_announcement_files_file_id", "file_id", unique=True),
    )

    announcement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("announcements.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id", ondelete="RESTRICT"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
