from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.users.models import User


class SyntheticSeedRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_email(self, email: str) -> User | None:
        result: User | None = await self._session.scalar(
            select(User).where(User.email_normalized == email)
        )
        return result

    def add_user_with_audit(self, user: User, audit_log: AuditLog) -> None:
        self._session.add_all((user, audit_log))

    async def commit(self) -> None:
        await self._session.commit()
