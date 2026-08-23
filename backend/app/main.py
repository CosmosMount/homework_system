from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.health.router import router as health_router


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
    return application


app = create_app()
