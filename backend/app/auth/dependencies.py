from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthenticatedContext, AuthenticationService
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.origin import require_same_origin
from app.database.session import get_session

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def request_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_authentication_service(
    request: Request,
    session: SessionDependency,
) -> AuthenticationService:
    return AuthenticationService(session, request_settings(request))


AuthenticationServiceDependency = Annotated[
    AuthenticationService,
    Depends(get_authentication_service),
]


async def get_authenticated_context(
    request: Request,
    service: AuthenticationServiceDependency,
) -> AuthenticatedContext:
    settings = request_settings(request)
    return await service.authenticate(request.cookies.get(settings.session_cookie_name))


AuthenticatedContextDependency = Annotated[
    AuthenticatedContext,
    Depends(get_authenticated_context),
]


def require_public_same_origin(request: Request) -> None:
    require_same_origin(request, request_settings(request))


async def require_csrf(
    request: Request,
    service: AuthenticationServiceDependency,
    context: AuthenticatedContextDependency,
) -> None:
    settings = request_settings(request)
    require_same_origin(request, settings)
    service.verify_csrf(
        context,
        cookie_token=request.cookies.get(settings.csrf_cookie_name),
        header_token=request.headers.get("x-csrf-token"),
    )


CsrfDependency = Annotated[None, Depends(require_csrf)]


def require_admin(context: AuthenticatedContextDependency) -> AuthenticatedContext:
    if not context.is_admin:
        raise ApplicationError(
            status_code=403,
            code="FORBIDDEN",
            message="当前账号无权执行此操作。",
        )
    return context


AdminContextDependency = Annotated[AuthenticatedContext, Depends(require_admin)]
