from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base
from app.database.mixins import TimestampRevisionMixin


class HelpRequest(TimestampRevisionMixin, Base):
    __tablename__ = "help_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('system_feedback', 'question')",
            name="request_type_allowed",
        ),
        CheckConstraint("status IN ('open', 'resolved')", name="status_allowed"),
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 200", name="title_present"),
        CheckConstraint(
            "length(trim(content_markdown)) BETWEEN 1 AND 20000",
            name="content_present",
        ),
        CheckConstraint(
            """
            (
                status = 'open'
                AND resolution_markdown IS NULL
                AND resolution_html IS NULL
                AND resolved_by IS NULL
                AND resolved_at IS NULL
            )
            OR
            (
                status = 'resolved'
                AND length(trim(resolution_markdown)) BETWEEN 1 AND 20000
                AND resolution_html IS NOT NULL
                AND resolved_at IS NOT NULL
            )
            """,
            name="resolution_state_consistent",
        ),
        Index("ix_help_requests_student_list", "created_by", "created_at", "id"),
        Index(
            "ix_help_requests_admin_list",
            "status",
            "request_type",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    resolved_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
