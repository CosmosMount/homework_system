from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

TeamStatus = Literal["forming", "dissolved"]
TeamInvitationStatus = Literal["pending", "accepted", "declined", "cancelled"]


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("队伍名称不能为空")
        return normalized


class TeamJoinRequest(BaseModel):
    invite_code: str = Field(min_length=6, max_length=64)


class CaptainTransferRequest(BaseModel):
    new_captain_user_id: UUID


class TeamProfileUpsertRequest(BaseModel):
    introduction: str = Field(min_length=1, max_length=2_000)
    revision: int | None = Field(default=None, ge=1)

    @field_validator("introduction")
    @classmethod
    def normalize_introduction(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("个人简介不能为空")
        return normalized


class TeamInvitationCreateRequest(BaseModel):
    invitee_user_id: UUID


class AdminReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2_000)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("管理员原因不能为空")
        return normalized


class AdminMemberAddRequest(AdminReasonRequest):
    user_id: UUID


class AdminCaptainTransferRequest(AdminReasonRequest):
    new_captain_user_id: UUID


class TeamMemberResponse(BaseModel):
    user_id: UUID
    full_name: str
    student_number: str
    joined_at: datetime
    added_by_admin: bool
    is_captain: bool

    direction_name: str | None = None
    introduction: str | None = None


class TeamResponse(BaseModel):
    id: UUID
    name: str
    status: TeamStatus
    captain_user_id: UUID | None
    member_count: int
    max_members: int
    dissolved_at: datetime | None
    revision: int
    members: list[TeamMemberResponse]
    can_manage: bool


class TeamCreatedResponse(TeamResponse):
    invite_code: str


class AutoAssignResponse(TeamResponse):
    assignment: Literal["joined", "created"]
    invite_code: str | None = None


class InviteCodeRotatedResponse(BaseModel):
    team_id: UUID
    invite_code: str
    rotated_at: datetime
    revision: int


class TeamDirectoryItem(BaseModel):
    id: UUID
    name: str
    status: TeamStatus
    member_count: int
    max_members: int
    can_join: bool


class TeamProfileResponse(BaseModel):
    user_id: UUID
    full_name: str
    direction_name: str | None
    introduction: str
    updated_at: datetime
    revision: int
    can_invite: bool = False
    invitation_pending: bool = False


class TeamProfilePage(BaseModel):
    items: list[TeamProfileResponse]
    total: int
    page: int
    page_size: int


class TeamInvitationResponse(BaseModel):
    id: UUID
    team_id: UUID
    team_name: str
    invited_by_full_name: str
    status: TeamInvitationStatus
    created_at: datetime
    responded_at: datetime | None
    revision: int


class TeamInvitationListResponse(BaseModel):
    items: list[TeamInvitationResponse]


class TeamDirectoryResponse(BaseModel):
    items: list[TeamDirectoryItem]
    total: int
    page: int
    page_size: int


class AdminTeamListItem(BaseModel):
    id: UUID
    name: str
    status: TeamStatus
    captain_user_id: UUID | None
    member_count: int
    max_members: int


class AdminTeamListResponse(BaseModel):
    items: list[AdminTeamListItem]
    total: int
    page: int
    page_size: int


class OperationResponse(BaseModel):
    status: Literal["ok"] = "ok"
