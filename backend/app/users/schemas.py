from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Role = Literal["student", "admin"]
UserStatus = Literal["pending_email", "active", "disabled"]


class CategorySummary(BaseModel):
    id: UUID
    code: str
    name: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    student_number: str
    full_name: str
    role: Role
    status: UserStatus
    student_view: bool = False
    cohort: CategorySummary | None = None
    direction: CategorySummary | None = None
    email_verified_at: datetime | None
    created_at: datetime
    revision: int


class UserPage(BaseModel):
    items: list[UserResponse]
    page: int
    page_size: int
    total: int


class UserDisableRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class UserRestoreRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class UserRoleRequest(BaseModel):
    role: Role
    reason: str = Field(min_length=3, max_length=500)


class UserPatchRequest(BaseModel):
    revision: int = Field(ge=1)
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    student_number: str | None = Field(default=None, min_length=1, max_length=64)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    cohort_id: UUID | None = None
    direction_id: UUID | None = None


class CohortCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    start_year: int = Field(ge=2000, le=2200)


class CohortPatchRequest(BaseModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    start_year: int | None = Field(default=None, ge=2000, le=2200)
    is_active: bool | None = None


class CohortResponse(BaseModel):
    id: UUID
    code: str
    name: str
    start_year: int
    is_active: bool
    revision: int


class DirectionCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class DirectionPatchRequest(BaseModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class DirectionResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    revision: int
