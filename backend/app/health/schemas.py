from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LiveHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["backend"] = "backend"


class ReadyHealthResponse(BaseModel):
    status: Literal["ready"] = "ready"
    postgresql: Literal["ok"] = "ok"


class WorkerHealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"
    worker_name: str
    started_at: datetime
    last_heartbeat_at: datetime
    age_seconds: float
