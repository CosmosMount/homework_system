from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WorkerHeartbeatSnapshot:
    worker_name: str
    started_at: datetime
    last_heartbeat_at: datetime
