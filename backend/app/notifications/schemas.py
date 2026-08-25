from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OutboxJobResponse(BaseModel):
    id: UUID
    job_type: str
    status: str
    recipient_masked: str
    available_at: datetime
    attempt_count: int
    max_attempts: int
    last_error_code: str | None
    last_error_summary: str | None
    created_at: datetime
    sent_at: datetime | None


class OutboxJobPage(BaseModel):
    items: list[OutboxJobResponse]
    page: int
    page_size: int
    total: int
