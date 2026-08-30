import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.urls import normalize_http_url

AudienceMatch = Literal["union", "intersection"]
AssignmentStatus = Literal["draft", "published", "closed", "archived"]
_EXTENSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,31}$")


class AssignmentAudience(BaseModel):
    all_students: bool = True
    cohort_ids: list[UUID] = Field(default_factory=list, max_length=50)
    direction_ids: list[UUID] = Field(default_factory=list, max_length=50)
    match: AudienceMatch = "intersection"

    @model_validator(mode="after")
    def validate_selection(self) -> "AssignmentAudience":
        if len(self.cohort_ids) != len(set(self.cohort_ids)):
            raise ValueError("cohort_ids 不得重复")
        if len(self.direction_ids) != len(set(self.direction_ids)):
            raise ValueError("direction_ids 不得重复")
        if self.all_students and (self.cohort_ids or self.direction_ids):
            raise ValueError("面向全部学生时不得同时选择届次或方向")
        if not self.all_students and not (self.cohort_ids or self.direction_ids):
            raise ValueError("定向作业必须至少选择一个届次或方向")
        return self


class AssignmentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description_markdown: str = Field(min_length=1, max_length=200_000)
    training_url: str | None = Field(default=None, max_length=2000)
    submission_instructions: str = Field(min_length=1, max_length=50_000)
    audience: AssignmentAudience
    allowed_extensions: list[str] = Field(min_length=1, max_length=100)
    max_total_bytes: int = Field(ge=1, le=2_147_483_648)
    publish_at: datetime
    deadline: datetime

    @field_validator("training_url")
    @classmethod
    def validate_training_url(cls, value: str | None) -> str | None:
        return normalize_http_url(value)

    @field_validator("allowed_extensions")
    @classmethod
    def normalize_extensions(cls, value: list[str]) -> list[str]:
        normalized = [extension.strip().lower().lstrip(".") for extension in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed_extensions 不得重复")
        if any(not _EXTENSION_PATTERN.fullmatch(extension) for extension in normalized):
            raise ValueError("allowed_extensions 包含无效扩展名")
        return normalized

    @model_validator(mode="after")
    def validate_times(self) -> "AssignmentCreateRequest":
        if self.publish_at.tzinfo is None or self.deadline.tzinfo is None:
            raise ValueError("publish_at 与 deadline 必须包含时区")
        if self.deadline <= self.publish_at:
            raise ValueError("deadline 必须晚于 publish_at")
        return self


class AssignmentPatchRequest(AssignmentCreateRequest):
    revision: int = Field(ge=1)


class AssignmentStatsResponse(BaseModel):
    target_count: int
    submitted_count: int
    unsubmitted_count: int
    feedback_submission_count: int
    last_submitted_at: datetime | None


class AssignmentAdminResponse(BaseModel):
    id: UUID
    title: str
    description_markdown: str
    description_html: str
    training_url: str | None
    submission_instructions: str
    status: AssignmentStatus
    audience: AssignmentAudience
    allowed_extensions: list[str]
    max_total_bytes: int
    publish_at: datetime
    published_at: datetime | None
    deadline: datetime
    closed_at: datetime | None
    archived_at: datetime | None
    estimated_recipient_count: int
    actual_recipient_count: int
    stats: AssignmentStatsResponse
    created_at: datetime
    updated_at: datetime
    revision: int


class AssignmentAdminPage(BaseModel):
    items: list[AssignmentAdminResponse]
    page: int
    page_size: int
    total: int


class AssignmentExtensionRequest(BaseModel):
    extended_deadline: datetime
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_timezone(self) -> "AssignmentExtensionRequest":
        if self.extended_deadline.tzinfo is None:
            raise ValueError("extended_deadline 必须包含时区")
        return self


class AssignmentExtensionResponse(BaseModel):
    assignment_id: UUID
    user_id: UUID
    extended_deadline: datetime
    reason: str
    granted_by: UUID | None
    created_at: datetime
    updated_at: datetime
    revision: int


class AssignmentSubmissionSummary(BaseModel):
    submission_id: UUID
    latest_version_id: UUID
    latest_version_number: int
    submitted_at: datetime
    has_feedback: bool


class ExcellentSubmissionSummaryResponse(BaseModel):
    version_id: UUID
    author_name: str
    version_number: int
    marked_at: datetime


class AssignmentSummaryResponse(BaseModel):
    id: UUID
    title: str
    status: AssignmentStatus
    public_deadline: datetime
    effective_deadline: datetime
    has_personal_extension: bool
    can_submit: bool
    latest_submission: AssignmentSubmissionSummary | None


class AssignmentPage(BaseModel):
    items: list[AssignmentSummaryResponse]
    page: int
    page_size: int
    total: int


class AssignmentDetailResponse(AssignmentSummaryResponse):
    description_html: str
    training_url: str | None
    submission_instructions: str
    allowed_extensions: list[str]
    max_total_bytes: int
    excellent_submissions: list[ExcellentSubmissionSummaryResponse]


class ExcellentAttachmentResponse(BaseModel):
    id: UUID
    file_name: str
    size_bytes: int
    media_type: str
    sha256: str


class ExcellentSubmissionDetailResponse(BaseModel):
    assignment_id: UUID
    assignment_title: str
    version_id: UUID
    version_number: int
    author_name: str
    text_html: str | None
    external_url: str | None
    submitted_at: datetime
    marked_at: datetime
    attachments: list[ExcellentAttachmentResponse]


class AssignmentSubmissionAdminItem(BaseModel):
    user_id: UUID
    full_name: str
    student_number: str
    cohort_id: UUID | None
    direction_id: UUID | None
    submission_id: UUID | None
    latest_version_number: int | None
    last_submitted_at: datetime | None
    has_feedback: bool


class AssignmentSubmissionAdminPage(BaseModel):
    items: list[AssignmentSubmissionAdminItem]
    page: int
    page_size: int
    total: int
