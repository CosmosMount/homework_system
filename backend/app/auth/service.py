from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.repository import AssignmentRepository
from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.auth.models import AuthSecurityEvent, OneTimeToken, Session
from app.auth.repository import AuthRepository
from app.auth.schemas import (
    AdminSessionResponse,
    EmailVerificationResponse,
    RegisterRequest,
    RegisterResponse,
    SessionResponse,
)
from app.core.config import Settings
from app.core.errors import ApplicationError, ErrorDetail
from app.core.identifiers import uuid7
from app.core.security import (
    OutboxCipher,
    PasswordManager,
    PasswordPolicyViolation,
    PepperedTokenHasher,
    get_password_manager,
    is_campus_email,
    normalize_email,
    normalize_login_identifier,
    random_urlsafe_token,
    sha256_hexdigest,
    tokens_match,
    validate_password,
)
from app.notifications.models import OutboxJob
from app.notifications.repository import OutboxRepository
from app.users.models import User
from app.users.repository import UserRepository
from app.users.schemas import CategorySummary, UserResponse


@dataclass(frozen=True, slots=True)
class SessionCredentials:
    session_token: str
    csrf_token: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: UserResponse
    credentials: SessionCredentials


@dataclass(frozen=True, slots=True)
class AuthenticatedContext:
    user: User
    session: Session

    @property
    def is_student_view(self) -> bool:
        return self.user.role == "admin" and bool(getattr(self.session, "student_view", False))

    @property
    def effective_role(self) -> str:
        return "student" if self.is_student_view else self.user.role

    @property
    def is_admin(self) -> bool:
        return self.user.role == "admin" and not self.is_student_view


def context_effective_role(context: AuthenticatedContext) -> str:
    return str(getattr(context, "effective_role", context.user.role))


def context_is_admin(context: AuthenticatedContext) -> bool:
    return bool(getattr(context, "is_admin", context.user.role == "admin"))


class AuthenticationService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        clock: Any | None = None,
        password_manager: PasswordManager | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._assignments = AssignmentRepository(session)
        self._auth = AuthRepository(session)
        self._audit = AuditRepository(session)
        self._users = UserRepository(session)
        self._outbox = OutboxRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._passwords = password_manager or get_password_manager()
        previous_secret = (
            settings.session_previous_secret.get_secret_value()
            if settings.session_previous_secret is not None
            else None
        )
        self._sessions = PepperedTokenHasher(
            settings.session_current_secret.get_secret_value(),
            previous_secret,
        )
        self._csrf = PepperedTokenHasher(settings.csrf_secret.get_secret_value())
        self._outbox_cipher = OutboxCipher(settings.outbox_encryption_key.get_secret_value())

    async def _category_summary(
        self, cohort_id: UUID | None, direction_id: UUID | None
    ) -> tuple[CategorySummary | None, CategorySummary | None]:
        cohort = await self._users.get_cohort(cohort_id) if cohort_id is not None else None
        direction = (
            await self._users.get_direction(direction_id) if direction_id is not None else None
        )
        return (
            CategorySummary(id=cohort.id, code=cohort.code, name=cohort.name)
            if cohort is not None
            else None,
            CategorySummary(id=direction.id, code=direction.code, name=direction.name)
            if direction is not None
            else None,
        )

    async def user_response(self, user: User, *, student_view: bool = False) -> UserResponse:
        cohort, direction = await self._category_summary(user.cohort_id, user.direction_id)
        return UserResponse(
            id=user.id,
            email=user.email,
            student_number=user.student_number,
            full_name=user.full_name,
            role=user.role,
            status=user.status,
            student_view=student_view,
            cohort=cohort,
            direction=direction,
            email_verified_at=user.email_verified_at,
            created_at=user.created_at,
            revision=user.revision,
        )

    async def _event_count(
        self,
        *,
        event_type: str,
        window: timedelta,
        email_normalized: str | None,
        ip_prefix: str,
    ) -> tuple[int, int]:
        since = self._clock() - window
        email_count = 0
        if email_normalized is not None:
            email_count = await self._auth.count_security_events(
                event_type=event_type,
                since=since,
                email_normalized=email_normalized,
            )
        ip_count = await self._auth.count_security_events(
            event_type=event_type,
            since=since,
            ip_prefix=ip_prefix,
        )
        return email_count, ip_count

    @staticmethod
    def _raise_rate_limited(retry_after: int) -> None:
        raise ApplicationError(
            status_code=429,
            code="RATE_LIMITED",
            message="请求过于频繁，请稍后重试。",
            headers={"Retry-After": str(retry_after)},
        )

    async def _check_rate_limit(
        self,
        *,
        event_type: str,
        window: timedelta,
        ip_prefix: str,
        email_normalized: str | None = None,
        email_limit: int | None = None,
        ip_limit: int,
    ) -> tuple[int, int]:
        email_count, ip_count = await self._event_count(
            event_type=event_type,
            window=window,
            email_normalized=email_normalized,
            ip_prefix=ip_prefix,
        )
        if (email_limit is not None and email_count >= email_limit) or ip_count >= ip_limit:
            self._raise_rate_limited(int(window.total_seconds()))
        return email_count, ip_count

    def _security_event(
        self,
        *,
        event_type: str,
        ip_prefix: str,
        email_normalized: str | None = None,
        user_id: UUID | None = None,
    ) -> AuthSecurityEvent:
        return AuthSecurityEvent(
            id=uuid7(),
            event_type=event_type,
            email_normalized=email_normalized,
            user_id=user_id,
            ip_prefix=ip_prefix,
            occurred_at=self._clock(),
            event_metadata={},
        )

    def _enqueue_token_email(
        self,
        *,
        user: User,
        purpose: str,
        token: str,
        token_record: OneTimeToken,
    ) -> None:
        job_type = "email_verification" if purpose == "email_verification" else "password_reset"
        self._outbox.add(
            OutboxJob(
                id=uuid7(),
                job_type=job_type,
                event_key=f"{job_type}:{token_record.id}",
                payload={
                    "recipient": user.email,
                    "full_name": user.full_name,
                    "expires_at": token_record.expires_at.isoformat(),
                },
                secret_payload_ciphertext=self._outbox_cipher.encrypt({"token": token}),
                status="pending",
                available_at=self._clock(),
                attempt_count=0,
                max_attempts=8,
                created_at=self._clock(),
            )
        )

    async def _issue_token(self, *, user: User, purpose: str) -> tuple[str, datetime]:
        now = self._clock()
        lifetime = timedelta(hours=24) if purpose == "email_verification" else timedelta(minutes=30)
        await self._auth.invalidate_tokens(
            user_id=user.id,
            purpose=purpose,
            now=now,
        )
        raw_token = random_urlsafe_token()
        token_record = OneTimeToken(
            id=uuid7(),
            user_id=user.id,
            purpose=purpose,
            token_hash=sha256_hexdigest(raw_token),
            expires_at=now + lifetime,
            used_at=None,
            created_at=now,
        )
        self._auth.add_one_time_token(token_record)
        self._enqueue_token_email(
            user=user,
            purpose=purpose,
            token=raw_token,
            token_record=token_record,
        )
        return raw_token, token_record.expires_at

    async def issue_email_verification_for_user(self, user: User) -> datetime:
        _, expires_at = await self._issue_token(
            user=user,
            purpose="email_verification",
        )
        return expires_at

    async def revoke_all_sessions_for_user(self, user_id: UUID) -> None:
        await self._auth.revoke_all_sessions(user_id, self._clock())

    async def acquire_admin_lifecycle_lock(self) -> None:
        await self._auth.acquire_initial_admin_bootstrap_lock()

    async def lock_sessions_for_user(self, user_id: UUID) -> datetime | None:
        return await self._auth.lock_sessions_for_user(user_id)

    async def lock_one_time_tokens_for_user(self, user_id: UUID) -> None:
        await self._auth.lock_one_time_tokens_for_user(user_id)

    def enqueue_security_alert(self, *, user: User, event: str) -> None:
        self._enqueue_security_alert(user=user, event=event)

    async def register(self, payload: RegisterRequest, *, ip_prefix: str) -> RegisterResponse:
        normalized_email = normalize_email(payload.email)
        window = timedelta(hours=1)
        await self._check_rate_limit(
            event_type="registration",
            window=window,
            ip_prefix=ip_prefix,
            ip_limit=5,
        )
        self._auth.add_security_event(
            self._security_event(event_type="registration", ip_prefix=ip_prefix)
        )
        await self._session.commit()

        if not is_campus_email(
            normalized_email,
            domain=self._settings.campus_email_domain,
        ):
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="请求参数不符合要求。",
                details=[ErrorDetail(field="email", reason="INVALID_CAMPUS_EMAIL")],
            )
        try:
            validate_password(
                payload.password,
                email=normalized_email,
                student_number=payload.student_number.strip(),
            )
        except PasswordPolicyViolation as exc:
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="密码不符合安全要求。",
                details=[ErrorDetail(field="password", reason=exc.reason)],
            ) from exc

        now = self._clock()
        user = User(
            id=uuid7(),
            email=normalized_email,
            email_normalized=normalized_email,
            student_number=payload.student_number.strip(),
            full_name=payload.full_name.strip(),
            password_hash=self._passwords.hash(payload.password),
            role="student",
            status="pending_email",
            cohort_id=None,
            direction_id=None,
            email_verified_at=None,
            disabled_at=None,
            disabled_by=None,
            disabled_reason=None,
            password_changed_at=now,
        )
        self._users.add(user)
        _, expires_at = await self._issue_token(user=user, purpose="email_verification")
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            constraint_name = getattr(getattr(exc, "orig", None), "constraint_name", "")
            if constraint_name == "uq_users_email_normalized":
                reason = "EMAIL_ALREADY_REGISTERED"
                field = "email"
            elif constraint_name == "uq_users_student_number":
                reason = "STUDENT_NUMBER_ALREADY_REGISTERED"
                field = "student_number"
            else:
                raise
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="请求参数不符合要求。",
                details=[ErrorDetail(field=field, reason=reason)],
            ) from exc
        return RegisterResponse(user_id=user.id, verification_expires_at=expires_at)

    async def resend_verification(self, email: str, *, ip_prefix: str) -> None:
        normalized_email = normalize_email(email)
        window = timedelta(hours=1)
        await self._check_rate_limit(
            event_type="verification_resend",
            window=window,
            ip_prefix=ip_prefix,
            email_normalized=normalized_email,
            email_limit=3,
            ip_limit=20,
        )
        self._auth.add_security_event(
            self._security_event(
                event_type="verification_resend",
                ip_prefix=ip_prefix,
                email_normalized=normalized_email,
            )
        )
        await self._session.commit()

        user = await self._users.get_by_email(normalized_email)
        if user is not None and user.status == "pending_email":
            await self._issue_token(user=user, purpose="email_verification")
        await self._session.commit()

    async def confirm_email(
        self,
        token: str,
        *,
        request_id: str,
        ip_prefix: str,
    ) -> EmailVerificationResponse:
        await self._auth.acquire_initial_admin_bootstrap_lock()
        now = self._clock()
        token_record = await self._auth.get_one_time_token_for_update(sha256_hexdigest(token))
        if token_record is None or token_record.purpose != "email_verification":
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="INVALID_TOKEN",
                message="验证链接无效。",
            )
        if token_record.used_at is not None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=410,
                code="TOKEN_ALREADY_USED",
                message="验证链接已使用。",
            )
        if token_record.expires_at <= now:
            await self._session.rollback()
            raise ApplicationError(
                status_code=410,
                code="TOKEN_EXPIRED",
                message="验证链接已过期。",
            )
        user = await self._users.get_by_id(token_record.user_id, for_update=True)
        if user is None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="INVALID_TOKEN",
                message="验证链接无效。",
            )

        initial_admin_granted = user.role == "student" and not await self._auth.has_active_user()
        if initial_admin_granted:
            user.role = "admin"

        token_record.used_at = now
        await self._auth.invalidate_tokens(
            user_id=user.id,
            purpose="email_verification",
            now=now,
            exclude_id=token_record.id,
        )
        user.status = "active"
        user.email_verified_at = now
        user.disabled_at = None
        user.disabled_by = None
        user.disabled_reason = None
        user.revision += 1
        if user.role == "student":
            await self._assignments.add_open_assignment_audiences_for_student(
                user=user,
                created_at=now,
            )
        if initial_admin_granted:
            self._audit.add(
                AuditLog(
                    id=uuid7(),
                    actor_user_id=user.id,
                    action="user.initial_admin_granted",
                    target_type="user",
                    target_id=user.id,
                    request_id=request_id,
                    ip_prefix=ip_prefix,
                    result="success",
                    change_summary={
                        "from": "student",
                        "to": "admin",
                        "reason": "first_verified_user",
                    },
                    created_at=now,
                )
            )
        await self._session.commit()
        return EmailVerificationResponse()

    async def login(
        self,
        *,
        identifier: str,
        password: str,
        ip_prefix: str,
        user_agent_summary: str,
        request_id: str = "unknown",
    ) -> LoginResult:
        normalized_email = normalize_login_identifier(
            identifier,
            domain=self._settings.campus_email_domain,
        )
        window = timedelta(minutes=15)
        email_count, ip_count = await self._check_rate_limit(
            event_type="login_failed",
            window=window,
            ip_prefix=ip_prefix,
            email_normalized=normalized_email,
            email_limit=5,
            ip_limit=30,
        )
        user = await self._users.get_by_email(normalized_email)
        if user is None:
            self._passwords.consume_dummy_verification(password)
            verification_valid = False
            needs_rehash = False
        else:
            verification = self._passwords.verify(user.password_hash, password)
            verification_valid = verification.valid
            needs_rehash = verification.needs_rehash

        if user is None or not verification_valid or user.status != "active":
            self._auth.add_security_event(
                self._security_event(
                    event_type="login_failed",
                    ip_prefix=ip_prefix,
                    email_normalized=normalized_email,
                    user_id=user.id if user is not None else None,
                )
            )
            await self._session.commit()
            if email_count + 1 >= 5 or ip_count + 1 >= 30:
                self._raise_rate_limited(int(window.total_seconds()))
            raise ApplicationError(
                status_code=401,
                code="INVALID_CREDENTIALS",
                message="登录失败。请检查用户名或邮箱与密码；新注册账号需先完成邮箱验证。",
            )

        verified_password_hash = user.password_hash
        now = self._clock()
        if user.role == "student":
            await self._auth.acquire_initial_admin_bootstrap_lock()
            await self._auth.lock_sessions_for_user(user.id)
            locked_user = await self._users.get_by_id(user.id, for_update=True)
            if locked_user is None or locked_user.status != "active":
                await self._session.rollback()
                raise ApplicationError(
                    status_code=401,
                    code="INVALID_CREDENTIALS",
                    message="登录失败。请检查用户名或邮箱与密码；新注册账号需先完成邮箱验证。",
                )
            user = locked_user
            if user.password_hash != verified_password_hash:
                current_verification = self._passwords.verify(user.password_hash, password)
                if not current_verification.valid:
                    await self._session.rollback()
                    raise ApplicationError(
                        status_code=401,
                        code="INVALID_CREDENTIALS",
                        message="登录失败。请检查用户名或邮箱与密码；新注册账号需先完成邮箱验证。",
                    )
                needs_rehash = current_verification.needs_rehash
            if user.role == "student" and not await self._users.has_other_accounts(user.id):
                user.role = "admin"
                user.revision += 1
                await self._auth.revoke_all_sessions(user.id, now)
                self._audit.add(
                    AuditLog(
                        id=uuid7(),
                        actor_user_id=user.id,
                        action="user.single_account_admin_granted",
                        target_type="user",
                        target_id=user.id,
                        request_id=request_id,
                        ip_prefix=ip_prefix,
                        result="success",
                        change_summary={
                            "from": "student",
                            "to": "admin",
                            "reason": "single_verified_account",
                        },
                        created_at=now,
                    )
                )

        if needs_rehash:
            user.password_hash = self._passwords.hash(password)

        await self._users.touch_activity(user, at=now)
        absolute_expires_at = now + timedelta(days=14)
        idle_lifetime = timedelta(hours=4 if user.role == "admin" else 12)
        raw_session = random_urlsafe_token()
        raw_csrf = random_urlsafe_token()
        session_record = Session(
            id=uuid7(),
            user_id=user.id,
            token_hash=self._sessions.current_hash(raw_session),
            csrf_secret_hash=self._csrf.current_hash(raw_csrf),
            created_at=now,
            last_seen_at=now,
            idle_expires_at=min(now + idle_lifetime, absolute_expires_at),
            absolute_expires_at=absolute_expires_at,
            revoked_at=None,
            ip_prefix=ip_prefix,
            user_agent_summary=user_agent_summary,
        )
        self._auth.add_session(session_record)
        response = await self.user_response(user)
        await self._session.commit()
        return LoginResult(
            user=response,
            credentials=SessionCredentials(
                session_token=raw_session,
                csrf_token=raw_csrf,
            ),
        )

    async def authenticate(self, raw_session_token: str | None) -> AuthenticatedContext:
        if not raw_session_token:
            raise ApplicationError(
                status_code=401,
                code="AUTHENTICATION_REQUIRED",
                message="请先登录。",
            )
        candidates = self._sessions.candidate_hashes(raw_session_token)
        pair = await self._auth.find_session_with_user(candidates, for_update=True)
        if pair is None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=401,
                code="AUTHENTICATION_REQUIRED",
                message="登录状态已失效，请重新登录。",
            )
        session_record, user = pair
        now = self._clock()
        expired = (
            session_record.revoked_at is not None
            or session_record.idle_expires_at <= now
            or session_record.absolute_expires_at <= now
            or user.status != "active"
        )
        if expired:
            if session_record.revoked_at is None:
                session_record.revoked_at = now
                await self._session.commit()
            else:
                await self._session.rollback()
            raise ApplicationError(
                status_code=401,
                code="AUTHENTICATION_REQUIRED",
                message="登录状态已失效，请重新登录。",
            )

        changed = False
        current_hash = self._sessions.current_hash(raw_session_token)
        if session_record.token_hash != current_hash:
            session_record.token_hash = current_hash
            changed = True
        activity_refresh_due = now - session_record.last_seen_at >= timedelta(minutes=5)
        if activity_refresh_due:
            idle_lifetime = timedelta(hours=4 if user.role == "admin" else 12)
            session_record.last_seen_at = now
            session_record.idle_expires_at = min(
                now + idle_lifetime,
                session_record.absolute_expires_at,
            )
            changed = True
        if (
            activity_refresh_due
            or user.last_active_at is None
            or session_record.last_seen_at > user.last_active_at
        ):
            await self._users.touch_activity(user, at=now)
            changed = True
        if changed:
            await self._session.commit()
        return AuthenticatedContext(user=user, session=session_record)

    async def rotate_csrf(self, context: AuthenticatedContext) -> str:
        raw_csrf = random_urlsafe_token()
        context.session.csrf_secret_hash = self._csrf.current_hash(raw_csrf)
        await self._session.commit()
        return raw_csrf

    def verify_csrf(
        self,
        context: AuthenticatedContext,
        *,
        cookie_token: str | None,
        header_token: str | None,
    ) -> None:
        if (
            cookie_token is None
            or header_token is None
            or not tokens_match(cookie_token, header_token)
            or not tokens_match(
                self._csrf.current_hash(header_token),
                context.session.csrf_secret_hash,
            )
        ):
            raise ApplicationError(
                status_code=403,
                code="CSRF_FAILED",
                message="CSRF 校验失败。",
            )

    async def logout(self, context: AuthenticatedContext) -> None:
        if context.session.revoked_at is None:
            context.session.revoked_at = self._clock()
        await self._session.commit()

    async def set_student_view(
        self,
        context: AuthenticatedContext,
        *,
        enabled: bool,
        request_id: str,
        ip_prefix: str,
    ) -> UserResponse:
        if context.user.role != "admin":
            raise ApplicationError(
                status_code=403,
                code="FORBIDDEN",
                message="只有管理员可以切换学生视图。",
            )
        current = bool(getattr(context.session, "student_view", False))
        if current != enabled:
            now = self._clock()
            context.session.student_view = enabled
            self._audit.add(
                AuditLog(
                    id=uuid7(),
                    actor_user_id=context.user.id,
                    action="auth.student_view.enable" if enabled else "auth.student_view.disable",
                    target_type="session",
                    target_id=context.session.id,
                    request_id=request_id,
                    ip_prefix=ip_prefix,
                    result="success",
                    change_summary={"enabled": enabled},
                    created_at=now,
                )
            )
        await self._session.commit()
        return await self.user_response(context.user, student_view=enabled)

    async def list_sessions(self, context: AuthenticatedContext) -> list[SessionResponse]:
        records = await self._auth.list_sessions(context.user.id)
        return [
            SessionResponse(
                id=record.id,
                created_at=record.created_at,
                last_seen_at=record.last_seen_at,
                idle_expires_at=record.idle_expires_at,
                absolute_expires_at=record.absolute_expires_at,
                revoked_at=record.revoked_at,
                ip_prefix=record.ip_prefix,
                user_agent_summary=record.user_agent_summary,
                is_current=record.id == context.session.id,
            )
            for record in records
        ]

    async def list_admin_sessions(
        self, context: AuthenticatedContext
    ) -> list[AdminSessionResponse]:
        records = await self._auth.list_active_sessions(now=self._clock())
        return [
            AdminSessionResponse(
                id=session.id,
                user_id=user.id,
                user_full_name=user.full_name,
                user_email=user.email,
                user_role=user.role,
                user_status=user.status,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                idle_expires_at=session.idle_expires_at,
                absolute_expires_at=session.absolute_expires_at,
                ip_prefix=session.ip_prefix,
                user_agent_summary=session.user_agent_summary,
                is_current=session.id == context.session.id,
            )
            for session, user in records
        ]

    async def revoke_session(self, context: AuthenticatedContext, session_id: UUID) -> None:
        record = await self._auth.get_owned_session(
            session_id=session_id,
            user_id=context.user.id,
            for_update=True,
        )
        if record is None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=404,
                code="RESOURCE_NOT_FOUND",
                message="会话不存在。",
            )
        if record.id == context.session.id:
            await self._session.rollback()
            raise ApplicationError(
                status_code=409,
                code="STATE_CONFLICT",
                message="请使用退出登录结束当前会话。",
            )
        if record.revoked_at is None:
            record.revoked_at = self._clock()
        await self._session.commit()

    async def request_password_reset(self, email: str, *, ip_prefix: str) -> None:
        normalized_email = normalize_email(email)
        window = timedelta(hours=1)
        await self._check_rate_limit(
            event_type="password_reset_request",
            window=window,
            ip_prefix=ip_prefix,
            email_normalized=normalized_email,
            email_limit=3,
            ip_limit=20,
        )
        self._auth.add_security_event(
            self._security_event(
                event_type="password_reset_request",
                ip_prefix=ip_prefix,
                email_normalized=normalized_email,
            )
        )
        await self._session.commit()
        user = await self._users.get_by_email(normalized_email)
        if user is not None and user.status == "active":
            await self._issue_token(user=user, purpose="password_reset")
        await self._session.commit()

    def _enqueue_security_alert(self, *, user: User, event: str) -> None:
        now = self._clock()
        self._outbox.add(
            OutboxJob(
                id=uuid7(),
                job_type="security_alert",
                event_key=f"security_alert:{event}:{user.id}:{uuid7()}",
                payload={
                    "recipient": user.email,
                    "full_name": user.full_name,
                    "event": event,
                },
                secret_payload_ciphertext=None,
                status="pending",
                available_at=now,
                attempt_count=0,
                max_attempts=8,
                created_at=now,
            )
        )

    async def confirm_password_reset(self, *, token: str, new_password: str) -> None:
        now = self._clock()
        token_record = await self._auth.get_one_time_token_for_update(sha256_hexdigest(token))
        if token_record is None or token_record.purpose != "password_reset":
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="INVALID_TOKEN",
                message="重置链接无效。",
            )
        if token_record.used_at is not None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=410,
                code="TOKEN_ALREADY_USED",
                message="重置链接已使用。",
            )
        if token_record.expires_at <= now:
            await self._session.rollback()
            raise ApplicationError(
                status_code=410,
                code="TOKEN_EXPIRED",
                message="重置链接已过期。",
            )
        await self._auth.lock_sessions_for_user(token_record.user_id)
        user = await self._users.get_by_id(token_record.user_id, for_update=True)
        if user is None:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="INVALID_TOKEN",
                message="重置链接无效。",
            )
        try:
            validate_password(
                new_password,
                email=user.email_normalized,
                student_number=user.student_number,
            )
        except PasswordPolicyViolation as exc:
            await self._session.rollback()
            raise ApplicationError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="密码不符合安全要求。",
                details=[ErrorDetail(field="new_password", reason=exc.reason)],
            ) from exc

        token_record.used_at = now
        await self._auth.invalidate_tokens(
            user_id=user.id,
            purpose="password_reset",
            now=now,
            exclude_id=token_record.id,
        )
        user.password_hash = self._passwords.hash(new_password)
        user.password_changed_at = now
        user.revision += 1
        await self._auth.revoke_all_sessions(user.id, now)
        self._enqueue_security_alert(user=user, event="password_changed")
        await self._session.commit()
