from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

AudienceMatch = Literal["union", "intersection"]
AnnouncementStatus = Literal["draft", "scheduled", "published", "archived"]


class AnnouncementAudience(BaseModel):
    all_students: bool = True
    cohort_ids: list[UUID] = Field(default_factory=list, max_length=50)
    direction_ids: list[UUID] = Field(default_factory=list, max_length=50)
    match: AudienceMatch = "intersection"

    @model_validator(mode="after")
    def validate_selection(self) -> "AnnouncementAudience":
        if len(self.cohort_ids) != len(set(self.cohort_ids)):
            raise ValueError("cohort_ids 不得重复")
        if len(self.direction_ids) != len(set(self.direction_ids)):
            raise ValueError("direction_ids 不得重复")
        if self.all_students and (self.cohort_ids or self.direction_ids):
            raise ValueError("面向全部学生时不得同时选择届次或方向")
        if not self.all_students and not (self.cohort_ids or self.direction_ids):
            raise ValueError("定向通知必须至少选择一个届次或方向")
        return self


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=500)
    body_markdown: str = Field(min_length=1, max_length=200_000)
    audience: AnnouncementAudience
    attachment_file_ids: list[UUID] = Field(default_factory=list, max_length=20)
    publish_at: datetime | None = None
    pinned_until: datetime | None = None
    send_email: bool = False

    @model_validator(mode="after")
    def validate_files(self) -> "AnnouncementCreateRequest":
        if len(self.attachment_file_ids) != len(set(self.attachment_file_ids)):
            raise ValueError("attachment_file_ids 不得重复")
        return self


class AnnouncementPatchRequest(AnnouncementCreateRequest):
    revision: int = Field(ge=1)


class AnnouncementAttachmentResponse(BaseModel):
    id: UUID
    file_name: str
    size_bytes: int
    media_type: str
    sha256: str


class AnnouncementSummaryResponse(BaseModel):
    id: UUID
    title: str
    summary: str
    published_at: datetime
    updated_at: datetime
    pinned_until: datetime | None
    is_pinned: bool
    is_unread: bool
    has_attachments: bool


class AnnouncementPage(BaseModel):
    items: list[AnnouncementSummaryResponse]
    page: int
    page_size: int
    total: int


class AnnouncementDetailResponse(BaseModel):
    id: UUID
    title: str
    summary: str
    body_html: str
    published_at: datetime
    updated_at: datetime
    pinned_until: datetime | None
    audience_description: str
    attachments: list[AnnouncementAttachmentResponse]
    notification_ids: list[UUID]


class AnnouncementAdminResponse(BaseModel):
    id: UUID
    title: str
    summary: str
    body_markdown: str
    body_html: str
    status: AnnouncementStatus
    audience: AnnouncementAudience
    attachment_file_ids: list[UUID]
    publish_at: datetime | None
    published_at: datetime | None
    pinned_until: datetime | None
    send_email: bool
    archived_at: datetime | None
    estimated_recipient_count: int
    actual_recipient_count: int
    created_at: datetime
    updated_at: datetime
    revision: int


class AnnouncementAdminPage(BaseModel):
    items: list[AnnouncementAdminResponse]
    page: int
    page_size: int
    total: int


class StudentNotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    target_url: str
    created_at: datetime
    read_at: datetime | None


class StudentNotificationPage(BaseModel):
    items: list[StudentNotificationResponse]
    page: int
    page_size: int
    total: int


class NotificationReadAllRequest(BaseModel):
    before: datetime
    type: str | None = Field(default=None, max_length=64)


class NotificationReadAllResponse(BaseModel):
    updated_count: int


class DashboardUserResponse(BaseModel):
    id: UUID
    full_name: str
    role: Literal["student", "admin"]
    cohort_id: UUID | None
    direction_id: UUID | None


class DashboardAssignmentItem(BaseModel):
    id: UUID
    title: str
    deadline: datetime


class DashboardCompetitionItem(BaseModel):
    id: UUID
    name: str
    status: str


class DashboardUnreadCounts(BaseModel):
    announcements: int
    assignments: int
    competitions: int
    help_requests: int


class DashboardResponse(BaseModel):
    current_user: DashboardUserResponse
    unread_count: int
    unread_counts: DashboardUnreadCounts
    recent_announcements: list[AnnouncementSummaryResponse]
    assignments: list[DashboardAssignmentItem]
    competitions: list[DashboardCompetitionItem]
