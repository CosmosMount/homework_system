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
            raise ValueError("问卷选项不能为空")
        return normalized


class IntentionQuestionInput(BaseModel):
    prompt: str = Field(min_length=1, max_length=200)
    options: list[IntentionOptionInput] = Field(min_length=1, max_length=30)
    allow_multiple: bool = False

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("问卷题目不能为空")
        return normalized

    @model_validator(mode="after")
    def unique_options(self) -> "IntentionQuestionInput":
        labels = [item.label.casefold() for item in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("同一题的选项不得重复")
        return self


class IntentionSurveyCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description_markdown: str = Field(default="", max_length=100_000)
    questions: list[IntentionQuestionInput] = Field(min_length=1, max_length=30)
    max_submissions: int | None = Field(default=1, ge=1, le=100)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("问卷标题不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self) -> "IntentionSurveyCreateRequest":
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.starts_at >= self.ends_at
        ):
            raise ValueError("问卷开始时间必须早于结束时间")
        return self


class IntentionSurveyPatchRequest(IntentionSurveyCreateRequest):
    revision: int = Field(ge=1)


class IntentionOptionResponse(BaseModel):
    id: UUID
    label: str
    display_order: int


class IntentionQuestionResponse(BaseModel):
    id: UUID
    prompt: str
    allow_multiple: bool
    display_order: int
    options: list[IntentionOptionResponse]


class IntentionAnswerRequest(BaseModel):
    question_id: UUID
    selected_option_ids: list[UUID] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_options(self) -> "IntentionAnswerRequest":
        if len(self.selected_option_ids) != len(set(self.selected_option_ids)):
            raise ValueError("同一题的选项不得重复")
        return self


class IntentionAnswerResponse(BaseModel):
    question_id: UUID
    selected_option_ids: list[UUID]


class IntentionResponseRequest(BaseModel):
    answers: list[IntentionAnswerRequest] = Field(min_length=1, max_length=30)
    free_text: str | None = Field(default=None, max_length=4_000)

    @model_validator(mode="after")
    def unique_questions(self) -> "IntentionResponseRequest":
        question_ids = [item.question_id for item in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("同一题只能提交一份答案")
        return self


class IntentionResponseResponse(BaseModel):
    answers: list[IntentionAnswerResponse]
    free_text: str | None
    submitted_at: datetime
    submission_count: int


class IntentionSurveySummary(BaseModel):
    id: UUID
    title: str
    description_html: str
    status: IntentionStatus
    starts_at: datetime | None
    ends_at: datetime | None
    question_count: int
    has_response: bool
    submissions_used: int
    max_submissions: int | None


class IntentionSurveyDetail(IntentionSurveySummary):
    questions: list[IntentionQuestionResponse]
    response: IntentionResponseResponse | None
    revision: int


class IntentionSurveyPage(BaseModel):
    items: list[IntentionSurveySummary]
    total: int


class IntentionStatsOption(BaseModel):
    option_id: UUID
    label: str
    response_count: int
    percentage: float


class IntentionStatsQuestion(BaseModel):
    question_id: UUID
    prompt: str
    allow_multiple: bool
    options: list[IntentionStatsOption]


class IntentionStatsResponse(BaseModel):
    survey_id: UUID
    total_active_students: int
    responded_count: int
    response_rate: float
    questions: list[IntentionStatsQuestion]


class IntentionRosterAnswer(BaseModel):
    question_id: UUID
    prompt: str
    selected_options: list[str]


class IntentionRosterItem(BaseModel):
    user_id: UUID
    full_name: str
    student_number: str
    email: str
    answers: list[IntentionRosterAnswer]
    free_text: str | None
    submission_count: int
    submitted_at: datetime


class IntentionRosterResponse(BaseModel):
    survey_id: UUID
    items: list[IntentionRosterItem]
    total: int


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
    starts_at: datetime | None
    ends_at: datetime | None
    question_count: int
    responded_count: int
    max_submissions: int | None
    created_at: datetime
    updated_at: datetime
    revision: int


class AdminIntentionSurveyDetail(AdminIntentionSurvey):
    questions: list[IntentionQuestionResponse]


class AdminIntentionSurveyPage(BaseModel):
    items: list[AdminIntentionSurvey]
    total: int
