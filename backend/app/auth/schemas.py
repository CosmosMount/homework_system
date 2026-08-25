from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field

from app.users.schemas import UserResponse


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    student_number: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RegisterResponse(BaseModel):
    user_id: UUID
    status: Literal["pending_email"] = "pending_email"
    verification_expires_at: datetime


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class EmailVerificationResponse(BaseModel):
    status: Literal["active"] = "active"


class LoginRequest(BaseModel):
    identifier: str = Field(
        min_length=1, max_length=320, validation_alias=AliasChoices("identifier", "email")
    )
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    user: UserResponse


class CsrfResponse(BaseModel):
    csrf_token: str


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    revoked_at: datetime | None
    ip_prefix: str
    user_agent_summary: str
    is_current: bool


class AdminSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_full_name: str
    user_email: str
    user_role: Literal["student", "admin"]
    user_status: Literal["pending_email", "active", "disabled"]
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    ip_prefix: str
    user_agent_summary: str

    is_current: bool


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    new_password: str = Field(min_length=1, max_length=128)
