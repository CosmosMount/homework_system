from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.announcements.router import router as announcements_router
from app.assignments.router import router as assignments_router
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.competitions.router import router as competitions_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.health.router import router as health_router
from app.notifications.center_router import router as notification_center_router
from app.notifications.router import router as notifications_router
from app.submissions.router import router as submissions_router
from app.uploads.router import router as uploads_router
from app.users.router import router as users_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        docs_url=None if resolved_settings.app_env == "production" else "/docs",
        redoc_url=None,
    )
    application.state.settings = resolved_settings
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=resolved_settings.trusted_host_list,
    )
    application.add_middleware(RequestContextMiddleware)
    register_error_handlers(application)
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(users_router, prefix="/api/v1")
    application.include_router(announcements_router, prefix="/api/v1")
    application.include_router(assignments_router, prefix="/api/v1")
    application.include_router(competitions_router, prefix="/api/v1")
    application.include_router(submissions_router, prefix="/api/v1")
    application.include_router(notification_center_router, prefix="/api/v1")
    application.include_router(notifications_router, prefix="/api/v1")
    application.include_router(uploads_router, prefix="/api/v1")
    application.include_router(audit_router, prefix="/api/v1")
    return application


app = create_app()
