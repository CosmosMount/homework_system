from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

HelpRequestType = Literal["system_feedback", "question"]
HelpRequestStatus = Literal["open", "resolved"]


def _strip_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("内容不能为空")
    return normalized


class HelpRequestCreateRequest(BaseModel):
    request_type: HelpRequestType
    title: str = Field(min_length=1, max_length=200)
    content_markdown: str = Field(min_length=1, max_length=20_000)

    @field_validator("title", "content_markdown")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _strip_required(value)


class HelpRequestResolutionRequest(BaseModel):
    resolution_markdown: str = Field(min_length=1, max_length=20_000)
    revision: int = Field(ge=1)

    @field_validator("resolution_markdown")
    @classmethod
    def normalize_resolution(cls, value: str) -> str:
        return _strip_required(value)


class HelpRequestSummary(BaseModel):
    id: UUID
    request_type: HelpRequestType
    status: HelpRequestStatus
    title: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    revision: int


class HelpRequestDetail(HelpRequestSummary):
    content_html: str
    resolution_html: str | None
    notification_ids: list[UUID]


class PublicHelpRequestDetail(HelpRequestSummary):
    content_html: str
    resolution_html: str


class HelpRequestPage(BaseModel):
    items: list[HelpRequestSummary]
    page: int
    page_size: int
    total: int


class HelpRequestSubmitter(BaseModel):
    id: UUID
    full_name: str
    student_number: str
    email: str


class AdminHelpRequestSummary(HelpRequestSummary):
    created_by: HelpRequestSubmitter


class AdminHelpRequestDetail(AdminHelpRequestSummary):
    content_markdown: str
    content_html: str
    resolution_markdown: str | None
    resolution_html: str | None
    resolved_by: UUID | None


class AdminHelpRequestPage(BaseModel):
    items: list[AdminHelpRequestSummary]
    page: int
    page_size: int
    total: int
