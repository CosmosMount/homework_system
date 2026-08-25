from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthSecurityEvent, OneTimeToken, Session
from app.users.models import User

_PNX_ADVISORY_LOCK_NAMESPACE = 5_267_800
_INITIAL_ADMIN_BOOTSTRAP_RESOURCE = 1


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_session(self, session_record: Session) -> None:
        self._session.add(session_record)

    async def find_session_with_user(
        self,
        token_hashes: tuple[str, ...],
        *,
        for_update: bool = False,
    ) -> tuple[Session, User] | None:
        statement = (
            select(Session, User)
            .join(User, User.id == Session.user_id)
            .where(Session.token_hash.in_(token_hashes))
        )
        if for_update:
            statement = statement.with_for_update(of=Session)
        row = (await self._session.execute(statement)).one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def list_sessions(self, user_id: UUID) -> list[Session]:
        return list(
            (
                await self._session.scalars(
                    select(Session)
                    .where(Session.user_id == user_id)
                    .order_by(Session.created_at.desc())
                )
            ).all()
        )

    async def list_active_sessions(self, *, now: datetime) -> list[tuple[Session, User]]:
        statement = (
            select(Session, User)
            .join(User, User.id == Session.user_id)
            .where(
                Session.revoked_at.is_(None),
                Session.idle_expires_at > now,
                Session.absolute_expires_at > now,
                User.status == "active",
            )
            .order_by(Session.last_seen_at.desc(), Session.created_at.desc())
        )
        return [(row[0], row[1]) for row in (await self._session.execute(statement)).all()]

    async def get_owned_session(
        self, *, session_id: UUID, user_id: UUID, for_update: bool = False
    ) -> Session | None:
        statement = select(Session).where(
            Session.id == session_id,
            Session.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result: Session | None = await self._session.scalar(statement)
        return result

    async def revoke_all_sessions(self, user_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_other_sessions(
        self, *, user_id: UUID, current_session_id: UUID, now: datetime
    ) -> None:
        await self._session.execute(
            update(Session)
            .where(
                Session.user_id == user_id,
                Session.id != current_session_id,
                Session.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def add_one_time_token(self, token: OneTimeToken) -> None:
        self._session.add(token)

    async def get_one_time_token_by_id(self, token_id: UUID) -> OneTimeToken | None:
        result: OneTimeToken | None = await self._session.scalar(
            select(OneTimeToken).where(OneTimeToken.id == token_id)
        )
        return result

    async def get_one_time_token_for_update(self, token_hash: str) -> OneTimeToken | None:
        result: OneTimeToken | None = await self._session.scalar(
            select(OneTimeToken).where(OneTimeToken.token_hash == token_hash).with_for_update()
        )
        return result

    async def acquire_initial_admin_bootstrap_lock(self) -> None:
        await self._session.execute(
            select(
                func.pg_advisory_xact_lock(
                    _PNX_ADVISORY_LOCK_NAMESPACE,
                    _INITIAL_ADMIN_BOOTSTRAP_RESOURCE,
                )
            )
        )

    async def has_active_user(self) -> bool:
        return bool(await self._session.scalar(select(exists().where(User.status == "active"))))

    async def invalidate_tokens(
        self,
        *,
        user_id: UUID,
        purpose: str,
        now: datetime,
        exclude_id: UUID | None = None,
    ) -> None:
        conditions = [
            OneTimeToken.user_id == user_id,
            OneTimeToken.purpose == purpose,
            OneTimeToken.used_at.is_(None),
        ]
        if exclude_id is not None:
            conditions.append(OneTimeToken.id != exclude_id)
        await self._session.execute(update(OneTimeToken).where(*conditions).values(used_at=now))

    def add_security_event(self, event: AuthSecurityEvent) -> None:
        self._session.add(event)

    async def count_security_events(
        self,
        *,
        event_type: str,
        since: datetime,
        email_normalized: str | None = None,
        ip_prefix: str | None = None,
        user_id: UUID | None = None,
    ) -> int:
        conditions = [
            AuthSecurityEvent.event_type == event_type,
            AuthSecurityEvent.occurred_at >= since,
        ]
        dimensions = []
        if email_normalized is not None:
            dimensions.append(AuthSecurityEvent.email_normalized == email_normalized)
        if ip_prefix is not None:
            dimensions.append(AuthSecurityEvent.ip_prefix == ip_prefix)
        if user_id is not None:
            dimensions.append(AuthSecurityEvent.user_id == user_id)
        if dimensions:
            conditions.append(or_(*dimensions))
        value = await self._session.scalar(
            select(func.count()).select_from(AuthSecurityEvent).where(*conditions)
        )
        return int(value or 0)
