from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

IntentionStatus = Literal["draft", "open", "closed", "archived"]


class IntentionOptionInput(BaseModel):
    label: str = Field(min_length=1, max_length=200)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("调查选项不能为空")
        return normalized


class IntentionSurveyCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description_markdown: str = Field(default="", max_length=100_000)
    options: list[IntentionOptionInput] = Field(min_length=1, max_length=30)
    allow_multiple: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("调查标题不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self) -> "IntentionSurveyCreateRequest":
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.starts_at >= self.ends_at
        ):
            raise ValueError("调查开始时间必须早于结束时间")
        labels = [item.label.casefold() for item in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("调查选项不得重复")
        return self


class IntentionSurveyPatchRequest(IntentionSurveyCreateRequest):
    revision: int = Field(ge=1)


class IntentionOptionResponse(BaseModel):
    id: UUID
    label: str
    display_order: int


class IntentionResponseResponse(BaseModel):
    selected_option_ids: list[UUID]
    free_text: str | None
    submitted_at: datetime


class IntentionSurveySummary(BaseModel):
    id: UUID
    title: str
    description_html: str
    status: IntentionStatus
    allow_multiple: bool
    starts_at: datetime | None
    ends_at: datetime | None
    option_count: int
    has_response: bool


class IntentionSurveyDetail(IntentionSurveySummary):
    options: list[IntentionOptionResponse]
    response: IntentionResponseResponse | None
    revision: int


class IntentionSurveyPage(BaseModel):
    items: list[IntentionSurveySummary]
    total: int


class IntentionResponseRequest(BaseModel):
    selected_option_ids: list[UUID] = Field(min_length=1, max_length=30)
    free_text: str | None = Field(default=None, max_length=4_000)

    @model_validator(mode="after")
    def unique_options(self) -> "IntentionResponseRequest":
        if len(self.selected_option_ids) != len(set(self.selected_option_ids)):
            raise ValueError("选项不得重复")
        return self


class IntentionStatsOption(BaseModel):
    option_id: UUID
    label: str
    response_count: int
    percentage: float


class IntentionStatsResponse(BaseModel):
    survey_id: UUID
    total_active_students: int
    responded_count: int
    response_rate: float
    options: list[IntentionStatsOption]


class IntentionQrResponse(BaseModel):
    survey_id: UUID
    token: str
    fill_url: str
    generated_at: datetime


class AdminIntentionSurvey(BaseModel):
    id: UUID
    title: str
    description_markdown: str
    status: IntentionStatus
    allow_multiple: bool
    starts_at: datetime | None
    ends_at: datetime | None
    option_count: int
    responded_count: int
    created_at: datetime
    updated_at: datetime
    revision: int


class AdminIntentionSurveyPage(BaseModel):
    items: list[AdminIntentionSurvey]
    total: int
