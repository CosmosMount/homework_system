from urllib.parse import urlsplit

from fastapi import Request

from app.core.config import Settings
from app.core.errors import ApplicationError


def _origin_from_referer(value: str) -> str | None:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def require_same_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        origin = _origin_from_referer(referer) if referer is not None else None
    if origin != settings.app_origin:
        raise ApplicationError(
            status_code=403,
            code="CSRF_FAILED",
            message="请求来源校验失败。",
        )
