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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base
from app.database.mixins import TimestampRevisionMixin


class IntentionSurvey(TimestampRevisionMixin, Base):
    __tablename__ = "intention_surveys"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'open', 'closed', 'archived')", name="status_allowed"),
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 200", name="title_present"),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at", name="window_order"
        ),
        CheckConstraint(
            "max_submissions IS NULL OR max_submissions > 0",
            name="max_submissions_positive",
        ),
        Index("ix_intention_surveys_status_window", "status", "starts_at", "ends_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    max_submissions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    public_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class IntentionQuestion(Base):
    __tablename__ = "intention_questions"
    __table_args__ = (
        CheckConstraint("length(trim(prompt)) BETWEEN 1 AND 200", name="prompt_present"),
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        UniqueConstraint("survey_id", "display_order"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    survey_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("intention_surveys.id", ondelete="CASCADE"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(String(200), nullable=False)
    allow_multiple: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class IntentionOption(Base):
    __tablename__ = "intention_options"
    __table_args__ = (
        CheckConstraint("length(trim(label)) BETWEEN 1 AND 200", name="label_present"),
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        UniqueConstraint("question_id", "display_order"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    question_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intention_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class IntentionResponse(TimestampRevisionMixin, Base):
    __tablename__ = "intention_responses"
    __table_args__ = (
        CheckConstraint("submission_count > 0", name="submission_count_positive"),
        UniqueConstraint("survey_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    survey_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("intention_surveys.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    free_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntentionResponseOption(Base):
    __tablename__ = "intention_response_options"

    response_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intention_responses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    option_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intention_options.id", ondelete="RESTRICT"),
        primary_key=True,
    )
