import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.request_context import current_request_id


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", "backend"),
            "event": getattr(record, "event", record.getMessage()),
            "request_id": getattr(record, "request_id", None) or current_request_id(),
        }
        for key in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "worker_name",
            "stage",
            "completed",
            "total",
            "error_code",
            "exception_type",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
