from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DatabaseOperationsMetrics:
    outbox_counts: dict[str, int]
    oldest_active_outbox_at: datetime | None
    upload_file_counts: dict[str, int]
    stale_upload_sessions: int
    orphaned_available_files: int
    cleanup_due_available_files: int
