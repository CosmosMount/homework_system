"""允许 Connect 邮箱并保留旧域名存量兼容。

Revision ID: 20260825_0006
Revises: 20260825_0005
Create Date: 2026-08-25 16:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0006"
down_revision: str | None = "20260825_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONNECT_DOMAIN_SUFFIX = "%@connect.hkust-gz.edu.cn"


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_users_campus_email"),
        "users",
        type_="check",
    )
    op.create_check_constraint(
        "campus_email",
        "users",
        "email_normalized ~ '^[^@[:space:]]+@(connect\\.)?hkust-gz\\.edu\\.cn$'",
    )


def downgrade() -> None:
    users = sa.table(
        "users",
        sa.column("email_normalized", sa.String()),
    )
    connect_user_count = int(
        op.get_bind().scalar(
            sa.select(sa.func.count())
            .select_from(users)
            .where(users.c.email_normalized.like(_CONNECT_DOMAIN_SUFFIX))
        )
        or 0
    )
    if connect_user_count:
        raise RuntimeError(
            "cannot downgrade while connect.hkust-gz.edu.cn accounts exist; "
            "use a reviewed forward recovery"
        )
    op.drop_constraint(
        op.f("ck_users_campus_email"),
        "users",
        type_="check",
    )
    op.create_check_constraint(
        "campus_email",
        "users",
        "email_normalized ~ '^[^@[:space:]]+@hkust-gz\\.edu\\.cn$'",
    )
