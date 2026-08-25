from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.urls import normalize_http_url


class SubmissionVersionCreateRequest(BaseModel):
    text_markdown: str | None = Field(default=None, max_length=200_000)
    external_url: str | None = Field(default=None, max_length=2000)
    file_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("text_markdown")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("external_url")
    @classmethod
    def validate_external_url(cls, value: str | None) -> str | None:
        return normalize_http_url(value)

    @model_validator(mode="after")
    def validate_content(self) -> "SubmissionVersionCreateRequest":
        if len(self.file_ids) != len(set(self.file_ids)):
            raise ValueError("file_ids 不得重复")
        if self.text_markdown is None and self.external_url is None and not self.file_ids:
            raise ValueError("文本、外部链接和附件至少需要一种")
        return self


class SubmissionVersionCreatedResponse(BaseModel):
    submission_id: UUID
    version_id: UUID
    version_number: int
    submitted_at: datetime
    total_file_bytes: int


class SubmissionAttachmentResponse(BaseModel):
    id: UUID
    file_name: str
    size_bytes: int
    media_type: str
    sha256: str


class FeedbackResponse(BaseModel):
    id: UUID
    body_html: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    revision: int


class SubmissionVersionResponse(BaseModel):
    id: UUID
    submission_id: UUID
    version_number: int
    submitted_by: UUID
    text_html: str | None
    external_url: str | None
    total_file_bytes: int
    submitted_at: datetime
    attachments: list[SubmissionAttachmentResponse]
    feedback: FeedbackResponse | None


class SubmissionResponse(BaseModel):
    id: UUID
    assignment_id: UUID | None
    competition_task_id: UUID | None
    owner_user_id: UUID | None
    owner_team_id: UUID | None
    latest_version_id: UUID
    versions: list[SubmissionVersionResponse]


class FeedbackPutRequest(BaseModel):
    body_markdown: str = Field(min_length=1, max_length=200_000)
    revision: int | None = Field(default=None, ge=1)
