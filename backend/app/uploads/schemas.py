from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class UploadInitRequest(BaseModel):
    purpose: Literal[
        "announcement_attachment",
        "assignment_submission",
        "competition_submission",
    ]
    context_id: UUID
    file_name: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0, le=2_147_483_648)
    media_type: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class UploadedPartResponse(BaseModel):
    part_number: int
    etag: str
    checksum_sha256: str
    size_bytes: int


class UploadSessionResponse(BaseModel):
    upload_id: UUID
    file_id: UUID
    status: str
    part_size_bytes: int
    part_count: int
    uploaded_parts: list[UploadedPartResponse]
    expires_at: datetime
    failure_code: str | None


class PresignPartsRequest(BaseModel):
    part_numbers: list[int] = Field(min_length=1, max_length=10)

    @field_validator("part_numbers")
    @classmethod
    def unique_part_numbers(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("part_numbers 不得重复")
        return value


class PresignedPartResponse(BaseModel):
    part_number: int
    url: str
    checksum_header: Literal["x-amz-checksum-sha256"]


class PresignPartsResponse(BaseModel):
    parts: list[PresignedPartResponse]
    expires_in_seconds: int


class CompletePartRequest(BaseModel):
    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1, max_length=200)
    checksum_sha256: str = Field(pattern=r"^[A-Za-z0-9+/]{43}=$")


class CompleteUploadRequest(BaseModel):
    parts: list[CompletePartRequest] = Field(min_length=1, max_length=10_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_unique_parts(self) -> "CompleteUploadRequest":
        numbers = [part.part_number for part in self.parts]
        if len(numbers) != len(set(numbers)):
            raise ValueError("parts 中的 part_number 不得重复")
        return self


class CompletedFileResponse(BaseModel):
    file_id: UUID
    status: str
    file_name: str
    size_bytes: int
    media_type: str
    sha256: str


class DownloadUrlResponse(BaseModel):
    url: str
    expires_at: datetime
    file_name: str
    size_bytes: int
    media_type: str
    sha256: str
