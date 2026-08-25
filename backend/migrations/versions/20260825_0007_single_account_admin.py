"""保证唯一已验证账号持久化为管理员。

Revision ID: 20260825_0007
Revises: 20260825_0006
Create Date: 2026-08-25 18:00:00+08:00
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.identifiers import uuid7

revision: str = "20260825_0007"
down_revision: str | None = "20260825_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PNX_ADVISORY_LOCK_NAMESPACE = 5_267_800
_INITIAL_ADMIN_BOOTSTRAP_RESOURCE = 1


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.select(
            sa.func.pg_advisory_xact_lock(
                _PNX_ADVISORY_LOCK_NAMESPACE,
                _INITIAL_ADMIN_BOOTSTRAP_RESOURCE,
            )
        )
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("role", sa.String()),
        sa.column("status", sa.String()),
        sa.column("email_verified_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("revision", sa.Integer()),
    )
    user_rows = list(
        bind.execute(
            sa.select(
                users.c.id,
                users.c.role,
                users.c.status,
                users.c.email_verified_at,
            ).limit(2)
        ).mappings()
    )
    if len(user_rows) != 1:
        return
    user = user_rows[0]
    if user["role"] != "student" or user["status"] != "active" or user["email_verified_at"] is None:
        return

    now = datetime.now(UTC)
    result = bind.execute(
        sa.update(users)
        .where(
            users.c.id == user["id"],
            users.c.role == "student",
            users.c.status == "active",
            users.c.email_verified_at.is_not(None),
        )
        .values(
            role="admin",
            updated_at=now,
            revision=users.c.revision + 1,
        )
    )
    if result.rowcount != 1:
        return

    sessions = sa.table(
        "sessions",
        sa.column("user_id", sa.Uuid()),
        sa.column("revoked_at", sa.DateTime(timezone=True)),
    )
    bind.execute(
        sa.update(sessions)
        .where(
            sessions.c.user_id == user["id"],
            sessions.c.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    audit_logs = sa.table(
        "audit_logs",
        sa.column("id", sa.Uuid()),
        sa.column("actor_user_id", sa.Uuid()),
        sa.column("action", sa.String()),
        sa.column("target_type", sa.String()),
        sa.column("target_id", sa.Uuid()),
        sa.column("request_id", sa.String()),
        sa.column("ip_prefix", sa.String()),
        sa.column("result", sa.String()),
        sa.column("change_summary", postgresql.JSONB()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    bind.execute(
        sa.insert(audit_logs).values(
            id=uuid7(),
            actor_user_id=user["id"],
            action="user.single_account_admin_granted",
            target_type="user",
            target_id=user["id"],
            request_id="migration:20260825_0007",
            ip_prefix="local",
            result="success",
            change_summary={
                "from": "student",
                "to": "admin",
                "reason": "single_verified_account_migration",
            },
            created_at=now,
        )
    )


def downgrade() -> None:
    # 角色授予属于安全修正；自动降级会重新造成系统无人管理。
    # 回退应用镜像时保留 admin，后续调整必须使用受审计的角色接口。
    return
