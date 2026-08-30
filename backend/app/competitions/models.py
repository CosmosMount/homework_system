from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base
from app.database.mixins import TimestampRevisionMixin


class Competition(TimestampRevisionMixin, Base):
    __tablename__ = "competitions"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="name_present"),
        CheckConstraint(
            "status IN ('draft', 'registration_open', 'registration_closed', "
            "'submission_open', 'submission_closed', 'archived')",
            name="status_allowed",
        ),
        CheckConstraint("registration_start < registration_end", name="registration_window_order"),
        CheckConstraint(
            "registration_end <= submission_start", name="registration_before_submission"
        ),
        CheckConstraint("submission_start < submission_end", name="submission_window_order"),
        CheckConstraint(
            "min_team_size BETWEEN 1 AND 20 AND max_team_size BETWEEN min_team_size AND 20",
            name="team_size_range",
        ),
        CheckConstraint(
            "status = 'draft' OR published_at IS NOT NULL",
            name="published_at_present",
        ),
        CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="archived_at_present",
        ),
        Index("ix_competitions_status_registration_start", "status", "registration_start"),
        Index("ix_competitions_status_submission_start", "status", "submission_start"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    description_html: Mapped[str] = mapped_column(Text, nullable=False)
    rules_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    registration_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registration_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submission_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submission_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    min_team_size: Mapped[int] = mapped_column(Integer, nullable=False)
    max_team_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompetitionRegistration(TimestampRevisionMixin, Base):
    __tablename__ = "competition_registrations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('registered', 'withdrawn', 'disqualified')",
            name="status_allowed",
        ),
        CheckConstraint(
            "(status = 'registered' AND withdrawn_at IS NULL "
            "AND disqualified_at IS NULL AND disqualified_by IS NULL "
            "AND disqualification_reason IS NULL) OR "
            "(status = 'withdrawn' AND withdrawn_at IS NOT NULL "
            "AND disqualified_at IS NULL AND disqualified_by IS NULL "
            "AND disqualification_reason IS NULL) OR "
            "(status = 'disqualified' AND disqualified_at IS NOT NULL "
            "AND length(trim(disqualification_reason)) > 0)",
            name="status_metadata_consistent",
        ),
        UniqueConstraint(
            "competition_id",
            "user_id",
            name="uq_competition_registrations_competition_user",
        ),
        Index(
            "ix_competition_registrations_competition_status",
            "competition_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disqualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disqualified_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    disqualification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class CompetitionTask(TimestampRevisionMixin, Base):
    __tablename__ = "competition_tasks"
    __table_args__ = (
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 200", name="title_present"),
        CheckConstraint("cardinality(allowed_extensions) >= 1", name="allowed_extensions_present"),
        CheckConstraint("max_total_bytes BETWEEN 1 AND 2147483648", name="max_total_bytes_range"),
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        UniqueConstraint(
            "competition_id",
            "display_order",
            name="uq_competition_tasks_competition_display_order",
        ),
        Index("ix_competition_tasks_competition_deadline", "competition_id", "deadline"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    description_html: Mapped[str] = mapped_column(Text, nullable=False)
    resource_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    allowed_extensions: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False)
    max_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Team(TimestampRevisionMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="name_present"),
        CheckConstraint(
            "status IN ('forming', 'dissolved', 'locked', 'invalid', 'disqualified', 'archived')",
            name="status_allowed",
        ),
        CheckConstraint("invite_code_hash ~ '^[0-9a-f]{64}$'", name="invite_code_hash_format"),
        CheckConstraint(
            "(status = 'dissolved' AND captain_user_id IS NULL "
            "AND dissolved_at IS NOT NULL) OR "
            "(status <> 'dissolved' AND captain_user_id IS NOT NULL)",
            name="captain_and_dissolution_consistent",
        ),
        CheckConstraint(
            "(min_size_waived_at IS NULL AND min_size_waived_by IS NULL "
            "AND waiver_reason IS NULL) OR "
            "(min_size_waived_at IS NOT NULL "
            "AND length(trim(waiver_reason)) > 0)",
            name="waiver_metadata_consistent",
        ),
        CheckConstraint(
            "(status <> 'disqualified' AND disqualified_at IS NULL "
            "AND disqualified_by IS NULL AND disqualification_reason IS NULL) OR "
            "(status = 'disqualified' AND disqualified_at IS NOT NULL "
            "AND length(trim(disqualification_reason)) > 0)",
            name="disqualification_metadata_consistent",
        ),
        CheckConstraint(
            "status NOT IN ('locked', 'archived') OR locked_at IS NOT NULL",
            name="locked_at_present",
        ),
        UniqueConstraint("id", "competition_id", name="uq_teams_id_competition_id"),
        Index(
            "uq_teams_competition_active_name",
            "competition_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("status <> 'dissolved'"),
        ),
        Index("ix_teams_competition_status", "competition_id", "status"),
        Index("ix_teams_invite_code_hash", "invite_code_hash"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    captain_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    invite_code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invite_code_rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    min_size_waived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    min_size_waived_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    waiver_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    disqualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disqualified_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    disqualification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dissolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        CheckConstraint(
            "(added_by_admin AND length(trim(admin_reason)) > 0) "
            "OR (NOT added_by_admin AND admin_reason IS NULL)",
            name="admin_reason_consistent",
        ),
        ForeignKeyConstraint(
            ["team_id", "competition_id"],
            ["teams.id", "teams.competition_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "team_id",
            "user_id",
            "joined_at",
            name="uq_team_members_team_user_joined_at",
        ),
        Index(
            "uq_team_members_current_competition_user",
            "competition_id",
            "user_id",
            unique=True,
            postgresql_where=text("left_at IS NULL"),
        ),
        Index("ix_team_members_team_left_at", "team_id", "left_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    team_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    added_by_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    admin_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
