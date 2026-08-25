from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    target_type: str
    target_id: UUID
    request_id: str
    ip_prefix: str
    result: str
    change_summary: dict[str, Any]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    page: int
    page_size: int
    total: int
