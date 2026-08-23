import logging
from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    field: str
    reason: str


class ErrorPayload(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorPayload


class ApplicationError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Sequence[ErrorDetail] = (),
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = list(details)


class DependencyUnavailableError(ApplicationError):
    def __init__(self, *, field: str, reason: str) -> None:
        super().__init__(
            status_code=503,
            code="DEPENDENCY_UNAVAILABLE",
            message="必要服务暂时不可用，请稍后重试。",
            details=[ErrorDetail(field=field, reason=reason)],
        )


def request_id_from(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Sequence[ErrorDetail] = (),
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorPayload(
            code=code,
            message=message,
            request_id=request_id_from(request),
            details=list(details) or None,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            ErrorDetail(
                field=".".join(str(part) for part in error["loc"] if part != "body"),
                reason=str(error["type"]),
            )
            for error in exc.errors()
        ]
        return error_response(
            request,
            status_code=400,
            code="VALIDATION_ERROR",
            message="请求参数不符合要求。",
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_by_status = {
            401: "AUTHENTICATION_REQUIRED",
            403: "FORBIDDEN",
            404: "RESOURCE_NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
        }
        code = code_by_status.get(exc.status_code, "INVALID_REQUEST")
        message = "资源不存在或当前用户无权查看。" if exc.status_code == 404 else str(exc.detail)
        return error_response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            exc_info=exc,
            extra={"event": "unhandled_exception", "request_id": request_id_from(request)},
        )
        return error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="服务暂时无法处理请求。",
        )
