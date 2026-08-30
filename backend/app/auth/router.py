from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.auth.dependencies import (
    AdminContextDependency,
    AuthenticatedContextDependency,
    AuthenticationServiceDependency,
    CsrfDependency,
    SessionDependency,
    request_settings,
    require_public_same_origin,
)
from app.auth.schemas import (
    AccountDeleteRequest,
    AdminSessionResponse,
    CsrfResponse,
    EmailRequest,
    EmailVerificationResponse,
    LoginRequest,
    LoginResponse,
    PasswordResetConfirmRequest,
    RegisterRequest,
    RegisterResponse,
    SessionResponse,
    TokenRequest,
)
from app.core.network import request_ip_prefix, summarize_user_agent
from app.core.request_context import current_request_id
from app.users.schemas import UserResponse
from app.users.service import AuditContext, UserAdministrationService

router = APIRouter(prefix="/auth", tags=["authentication"])
PublicOriginDependency = Annotated[None, Depends(require_public_same_origin)]


def _set_auth_cookies(
    response: Response,
    request: Request,
    *,
    session_token: str,
    csrf_token: str,
) -> None:
    settings = request_settings(request)
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=14 * 24 * 60 * 60,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=14 * 24 * 60 * 60,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )


def _clear_auth_cookies(response: Response, request: Request) -> None:
    settings = request_settings(request)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    service: AuthenticationServiceDependency,
    _origin: PublicOriginDependency,
) -> RegisterResponse:
    return await service.register(payload, ip_prefix=request_ip_prefix(request))


@router.post(
    "/email-verifications/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
)
async def resend_verification(
    payload: EmailRequest,
    request: Request,
    service: AuthenticationServiceDependency,
    _origin: PublicOriginDependency,
) -> Response:
    await service.resend_verification(payload.email, ip_prefix=request_ip_prefix(request))
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/email-verifications/confirm",
    response_model=EmailVerificationResponse,
)
async def confirm_email(
    payload: TokenRequest,
    request: Request,
    service: AuthenticationServiceDependency,
    _origin: PublicOriginDependency,
) -> EmailVerificationResponse:
    return await service.confirm_email(
        payload.token,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthenticationServiceDependency,
    _origin: PublicOriginDependency,
) -> LoginResponse:
    result = await service.login(
        identifier=payload.identifier,
        password=payload.password,
        ip_prefix=request_ip_prefix(request),
        user_agent_summary=summarize_user_agent(request.headers.get("user-agent")),
        request_id=current_request_id() or "unknown",
    )
    _set_auth_cookies(
        response,
        request,
        session_token=result.credentials.session_token,
        csrf_token=result.credentials.csrf_token,
    )
    return LoginResponse(user=result.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    service: AuthenticationServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> None:
    await service.logout(context)
    _clear_auth_cookies(response, request)
    response.status_code = status.HTTP_204_NO_CONTENT


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_own_account(
    payload: AccountDeleteRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> None:
    service = UserAdministrationService(session, request_settings(request))
    await service.delete_own_account(
        current_password=payload.current_password,
        confirmation_email=payload.confirmation_email,
        audit=AuditContext(
            actor=context,
            request_id=current_request_id() or "unknown",
            ip_prefix=request_ip_prefix(request),
        ),
    )
    _clear_auth_cookies(response, request)
    response.status_code = status.HTTP_204_NO_CONTENT


@router.get("/me", response_model=UserResponse)
async def me(
    service: AuthenticationServiceDependency,
    context: AuthenticatedContextDependency,
) -> UserResponse:
    return await service.user_response(context.user, student_view=context.is_student_view)


@router.get("/csrf", response_model=CsrfResponse)
async def csrf(
    request: Request,
    response: Response,
    service: AuthenticationServiceDependency,
    context: AuthenticatedContextDependency,
) -> CsrfResponse:
    token = await service.rotate_csrf(context)
    settings = request_settings(request)
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        max_age=14 * 24 * 60 * 60,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )
    return CsrfResponse(csrf_token=token)


@router.post("/student-view", response_model=UserResponse)
async def enable_student_view(
    request: Request,
    service: AuthenticationServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> UserResponse:
    return await service.set_student_view(
        context,
        enabled=True,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.delete("/student-view", response_model=UserResponse)
async def disable_student_view(
    request: Request,
    service: AuthenticationServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> UserResponse:
    return await service.set_student_view(
        context,
        enabled=False,
        request_id=current_request_id() or "unknown",
        ip_prefix=request_ip_prefix(request),
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def sessions(
    service: AuthenticationServiceDependency,
    context: AuthenticatedContextDependency,
) -> list[SessionResponse]:
    return await service.list_sessions(context)


@router.get("/admin/sessions", response_model=list[AdminSessionResponse])
async def admin_sessions(
    service: AuthenticationServiceDependency,
    admin: AdminContextDependency,
) -> list[AdminSessionResponse]:
    return await service.list_admin_sessions(admin)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    service: AuthenticationServiceDependency,
    context: AuthenticatedContextDependency,
    _csrf: CsrfDependency,
) -> None:
    await service.revoke_session(context, session_id)


@router.post(
    "/password-resets/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
)
async def request_password_reset(
    payload: EmailRequest,
    request: Request,
    service: AuthenticationServiceDependency,
    _origin: PublicOriginDependency,
) -> Response:
    await service.request_password_reset(payload.email, ip_prefix=request_ip_prefix(request))
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/password-resets/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    service: AuthenticationServiceDependency,
    _origin: PublicOriginDependency,
) -> None:
    await service.confirm_password_reset(
        token=payload.token,
        new_password=payload.new_password,
    )
