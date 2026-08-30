from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator

CompetitionStatus = Literal[
    "draft",
    "registration_open",
    "registration_closed",
    "submission_open",
    "submission_closed",
    "archived",
]
RegistrationStatus = Literal["registered", "withdrawn", "disqualified"]
TeamStatus = Literal[
    "forming",
    "dissolved",
    "locked",
    "invalid",
    "disqualified",
    "archived",
]


def _normalize_extensions(values: list[str]) -> list[str]:
    normalized = [value.strip().lower().lstrip(".") for value in values]
    if any(not value or len(value) > 32 for value in normalized):
        raise ValueError("附件扩展名格式错误")
    if len(normalized) != len(set(normalized)):
        raise ValueError("附件扩展名不得重复")
    return normalized


class CompetitionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description_markdown: str = Field(min_length=1, max_length=200_000)
    rules_url: AnyHttpUrl | None = None
    registration_start: datetime
    registration_end: datetime
    submission_start: datetime
    submission_end: datetime
    min_team_size: int = Field(ge=1, le=20)
    max_team_size: int = Field(ge=1, le=20)

    @model_validator(mode="after")
    def validate_windows(self) -> "CompetitionCreateRequest":
        if not (
            self.registration_start
            < self.registration_end
            <= self.submission_start
            < self.submission_end
        ):
            raise ValueError("赛事时间必须满足报名开始 < 报名结束 <= 提交开始 < 提交结束")
        if self.min_team_size > self.max_team_size:
            raise ValueError("最小队伍人数不能大于最大队伍人数")
        return self


class CompetitionPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description_markdown: str | None = Field(default=None, min_length=1, max_length=200_000)
    rules_url: AnyHttpUrl | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    submission_start: datetime | None = None
    submission_end: datetime | None = None
    min_team_size: int | None = Field(default=None, ge=1, le=20)
    max_team_size: int | None = Field(default=None, ge=1, le=20)
    revision: int = Field(ge=1)


class CompetitionTaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description_markdown: str = Field(min_length=1, max_length=200_000)
    resource_url: AnyHttpUrl | None = None
    allowed_extensions: list[str] = Field(min_length=1, max_length=100)
    max_total_bytes: int = Field(ge=1, le=2_147_483_648)
    deadline: datetime
    display_order: int = Field(ge=0)

    @field_validator("allowed_extensions")
    @classmethod
    def normalize_extensions(cls, values: list[str]) -> list[str]:
        return _normalize_extensions(values)


class CompetitionTaskPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description_markdown: str | None = Field(default=None, min_length=1, max_length=200_000)
    resource_url: AnyHttpUrl | None = None
    allowed_extensions: list[str] | None = Field(default=None, min_length=1, max_length=100)
    max_total_bytes: int | None = Field(default=None, ge=1, le=2_147_483_648)
    deadline: datetime | None = None
    display_order: int | None = Field(default=None, ge=0)
    revision: int = Field(ge=1)

    @field_validator("allowed_extensions")
    @classmethod
    def normalize_optional_extensions(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else _normalize_extensions(values)


class CompetitionTaskResponse(BaseModel):
    id: UUID
    competition_id: UUID
    title: str
    description_markdown: str
    description_html: str
    resource_url: str | None
    allowed_extensions: list[str]
    max_total_bytes: int
    deadline: datetime
    display_order: int
    revision: int
    submission_id: UUID | None = None
    latest_version_id: UUID | None = None


class CompetitionSummaryResponse(BaseModel):
    id: UUID
    name: str
    status: CompetitionStatus
    registration_start: datetime
    registration_end: datetime
    submission_start: datetime
    submission_end: datetime
    min_team_size: int
    max_team_size: int
    registration_status: RegistrationStatus | None
    registration_disqualification_reason: str | None
    team_id: UUID | None
    team_name: str | None
    team_status: TeamStatus | None


class CompetitionListResponse(BaseModel):
    items: list[CompetitionSummaryResponse]
    total: int
    page: int
    page_size: int


class CompetitionDetailResponse(BaseModel):
    id: UUID
    name: str
    description_markdown: str
    description_html: str
    rules_url: str | None
    status: CompetitionStatus
    registration_start: datetime
    registration_end: datetime
    submission_start: datetime
    submission_end: datetime
    min_team_size: int
    max_team_size: int
    published_at: datetime | None
    archived_at: datetime | None
    revision: int
    registration_status: RegistrationStatus | None
    registration_disqualification_reason: str | None
    team_id: UUID | None
    team_name: str | None
    team_status: TeamStatus | None
    tasks: list[CompetitionTaskResponse]


class RegistrationResponse(BaseModel):
    competition_id: UUID
    user_id: UUID
    status: RegistrationStatus
    registered_at: datetime
    withdrawn_at: datetime | None
    disqualified_at: datetime | None
    disqualification_reason: str | None
    revision: int


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamJoinRequest(BaseModel):
    invite_code: str = Field(min_length=6, max_length=64)


class TeamDirectoryItem(BaseModel):
    id: UUID
    competition_id: UUID
    name: str
    status: TeamStatus
    member_count: int
    max_team_size: int
    can_join: bool


class TeamDirectoryResponse(BaseModel):
    items: list[TeamDirectoryItem]
    total: int
    page: int
    page_size: int


class CaptainTransferRequest(BaseModel):
    new_captain_user_id: UUID


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
    student_id: str
    joined_at: datetime
    added_by_admin: bool
    is_captain: bool


class TeamResponse(BaseModel):
    id: UUID
    competition_id: UUID
    name: str
    status: TeamStatus
    captain_user_id: UUID | None
    member_count: int
    min_team_size: int
    max_team_size: int
    min_size_waived: bool
    waiver_reason: str | None
    disqualification_reason: str | None
    locked_at: datetime | None
    dissolved_at: datetime | None
    revision: int
    members: list[TeamMemberResponse]
    can_manage: bool
    can_submit: bool


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


class AdminCompetitionDetailResponse(CompetitionDetailResponse):
    registration_count: int
    team_count: int
    valid_team_count: int
    invalid_team_count: int


class AdminRegistrationItem(BaseModel):
    user_id: UUID
    full_name: str
    student_number: str
    status: RegistrationStatus
    registered_at: datetime
    withdrawn_at: datetime | None
    disqualified_at: datetime | None
    disqualification_reason: str | None
    team_id: UUID | None
    team_name: str | None


class AdminRegistrationListResponse(BaseModel):
    items: list[AdminRegistrationItem]
    total: int


class AdminTeamListItem(BaseModel):
    id: UUID
    competition_id: UUID
    name: str
    status: TeamStatus
    captain_user_id: UUID | None
    member_count: int
    min_size_waived: bool
    latest_submission_count: int


class AdminTeamListResponse(BaseModel):
    items: list[AdminTeamListItem]
    total: int


class AdminTeamSubmissionItem(BaseModel):
    task_id: UUID
    task_title: str
    deadline: datetime
    submission_id: UUID | None
    latest_version_id: UUID | None


class AdminTeamDetailResponse(TeamResponse):
    submissions: list[AdminTeamSubmissionItem]


class OperationResponse(BaseModel):
    status: Literal["ok"] = "ok"
