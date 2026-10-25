"""Add optional team contact information."""

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0032"
down_revision: str | None = "20261013_0031"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("contact_wechat", sa.String(64), nullable=True))
    op.create_check_constraint(
        "contact_wechat_present",
        "teams",
        "contact_wechat IS NULL OR length(trim(contact_wechat)) BETWEEN 1 AND 64",
    )


def downgrade() -> None:
    op.drop_constraint("contact_wechat_present", "teams", type_="check")
    op.drop_column("teams", "contact_wechat")
