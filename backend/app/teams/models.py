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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.identifiers import uuid7
from app.database.base import Base
from app.database.mixins import TimestampRevisionMixin


class Team(TimestampRevisionMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="name_present"),
        CheckConstraint("status IN ('forming', 'dissolved')", name="status_allowed"),
        CheckConstraint("max_members BETWEEN 1 AND 20", name="max_members_range"),
        CheckConstraint("invite_code_hash ~ '^[0-9a-f]{64}$'", name="invite_code_hash_format"),
        CheckConstraint(
            "(status = 'dissolved' AND captain_user_id IS NULL "
            "AND dissolved_at IS NOT NULL) OR "
            "(status = 'forming' AND captain_user_id IS NOT NULL "
            "AND dissolved_at IS NULL)",
            name="captain_and_dissolution_consistent",
        ),
        Index(
            "uq_teams_active_name",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("status = 'forming'"),
        ),
        Index("ix_teams_status_created_at", "status", "created_at"),
        Index("ix_teams_invite_code_hash", "invite_code_hash"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="forming")
    captain_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    invite_code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invite_code_rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    max_members: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=text("5"),
    )
    dissolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        CheckConstraint(
            "(added_by_admin AND length(trim(admin_reason)) > 0) "
            "OR (NOT added_by_admin AND admin_reason IS NULL)",
            name="admin_reason_consistent",
        ),
        UniqueConstraint(
            "team_id",
            "user_id",
            "joined_at",
            name="uq_team_members_team_user_joined_at",
        ),
        Index(
            "uq_team_members_current_user",
            "user_id",
            unique=True,
            postgresql_where=text("left_at IS NULL"),
        ),
        Index("ix_team_members_team_left_at", "team_id", "left_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
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


class TeamProfile(TimestampRevisionMixin, Base):
    __tablename__ = "team_profiles"
    __table_args__ = (
        CheckConstraint(
            "length(trim(introduction)) BETWEEN 1 AND 2000",
            name="introduction_present",
        ),
        Index("ix_team_profiles_updated_at", "updated_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    introduction: Mapped[str] = mapped_column(Text, nullable=False)


class TeamInvitation(TimestampRevisionMixin, Base):
    __tablename__ = "team_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint(
            "(status = 'pending' AND responded_at IS NULL) OR "
            "(status <> 'pending' AND responded_at IS NOT NULL)",
            name="response_state_consistent",
        ),
        CheckConstraint("invitee_user_id <> invited_by_user_id", name="different_users"),
        Index(
            "uq_team_invitations_pending_team_invitee",
            "team_id",
            "invitee_user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_team_invitations_invitee_status_created",
            "invitee_user_id",
            "status",
            "created_at",
        ),
        Index("ix_team_invitations_team_status", "team_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    invitee_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invited_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeamSettings(TimestampRevisionMixin, Base):
    """管理员维护的全局学生组队开放状态。"""

    __tablename__ = "team_settings"
    __table_args__ = (CheckConstraint("id", name="singleton_id_true"),)

    id: Mapped[bool] = mapped_column(
        Boolean,
        primary_key=True,
        default=True,
        server_default=text("true"),
    )
    is_team_open: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
