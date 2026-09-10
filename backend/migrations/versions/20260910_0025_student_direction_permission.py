"""增加管理员控制的学生自助方向权限。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_0025"
down_revision: str | None = "20260908_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "team_settings",
        sa.Column(
            "is_direction_change_open",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("team_settings", "is_direction_change_open")
