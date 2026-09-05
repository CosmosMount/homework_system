"""将赛事队伍归档，并建立不依赖赛事的独立队伍表。

Revision ID: 20260904_0020
Revises: 20260904_0019
Create Date: 2026-09-04 18:00:00+08:00

原赛事、报名、赛题、赛事提交和队伍记录保留在 legacy 表中，但不再由运行时
加载或展示。新的 teams/team_members 从空表开始，因此旧队伍在产品语义上全部
解散，新队伍也不再要求管理员先创建赛事。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0020"
down_revision: str | None = "20260904_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLACEHOLDER_COMPETITION_ID = "00000000-0000-0000-0000-000000000020"


def _timestamps_and_revision() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    ]


def _drop_legacy_team_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_team_members_current_captain ON team_members")
    op.execute("DROP TRIGGER IF EXISTS tr_teams_current_captain ON teams")


def _install_team_captain_triggers() -> None:
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER tr_teams_current_captain
        AFTER INSERT OR UPDATE OF captain_user_id, status ON teams
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION pnx_validate_team_captain();
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER tr_team_members_current_captain
        AFTER INSERT OR UPDATE OR DELETE ON team_members
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION pnx_validate_team_captain();
        """
    )


def _rename_legacy_indexes() -> None:
    op.execute("ALTER TABLE teams RENAME CONSTRAINT pk_teams TO pk_legacy_competition_teams")
    op.execute(
        "ALTER TABLE teams RENAME CONSTRAINT uq_teams_id_competition_id "
        "TO uq_legacy_competition_teams_id_competition_id"
    )
    op.execute(
        "ALTER INDEX uq_teams_competition_active_name "
        "RENAME TO uq_legacy_competition_teams_active_name"
    )
    op.execute(
        "ALTER INDEX ix_teams_competition_status RENAME TO ix_legacy_competition_teams_status"
    )
    op.execute(
        "ALTER INDEX ix_teams_invite_code_hash "
        "RENAME TO ix_legacy_competition_teams_invite_code_hash"
    )
    op.execute(
        "ALTER TABLE team_members RENAME CONSTRAINT pk_team_members "
        "TO pk_legacy_competition_team_members"
    )
    op.execute(
        "ALTER TABLE team_members RENAME CONSTRAINT uq_team_members_team_user_joined_at "
        "TO uq_legacy_competition_team_members_team_user_joined_at"
    )
    op.execute(
        "ALTER INDEX uq_team_members_current_competition_user "
        "RENAME TO uq_legacy_competition_team_members_current_user"
    )
    op.execute(
        "ALTER INDEX ix_team_members_team_left_at "
        "RENAME TO ix_legacy_competition_team_members_team_left_at"
    )


def _restore_legacy_index_names() -> None:
    op.execute(
        "ALTER TABLE legacy_competition_teams RENAME CONSTRAINT "
        "pk_legacy_competition_teams TO pk_teams"
    )
    op.execute(
        "ALTER TABLE legacy_competition_teams RENAME CONSTRAINT "
        "uq_legacy_competition_teams_id_competition_id "
        "TO uq_teams_id_competition_id"
    )
    op.execute(
        "ALTER INDEX uq_legacy_competition_teams_active_name "
        "RENAME TO uq_teams_competition_active_name"
    )
    op.execute(
        "ALTER INDEX ix_legacy_competition_teams_status RENAME TO ix_teams_competition_status"
    )
    op.execute(
        "ALTER INDEX ix_legacy_competition_teams_invite_code_hash "
        "RENAME TO ix_teams_invite_code_hash"
    )
    op.execute(
        "ALTER TABLE legacy_competition_team_members RENAME CONSTRAINT "
        "pk_legacy_competition_team_members TO pk_team_members"
    )
    op.execute(
        "ALTER TABLE legacy_competition_team_members RENAME CONSTRAINT "
        "uq_legacy_competition_team_members_team_user_joined_at "
        "TO uq_team_members_team_user_joined_at"
    )
    op.execute(
        "ALTER INDEX uq_legacy_competition_team_members_current_user "
        "RENAME TO uq_team_members_current_competition_user"
    )
    op.execute(
        "ALTER INDEX ix_legacy_competition_team_members_team_left_at "
        "RENAME TO ix_team_members_team_left_at"
    )


def _create_standalone_tables() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="forming", nullable=False),
        sa.Column("captain_user_id", sa.Uuid(), nullable=True),
        sa.Column("invite_code_hash", sa.String(length=64), nullable=False),
        sa.Column("invite_code_rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_members", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("dissolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps_and_revision(),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="name_present"),
        sa.CheckConstraint("status IN ('forming', 'dissolved')", name="status_allowed"),
        sa.CheckConstraint("max_members BETWEEN 1 AND 20", name="max_members_range"),
        sa.CheckConstraint(
            "invite_code_hash ~ '^[0-9a-f]{64}$'",
            name="invite_code_hash_format",
        ),
        sa.CheckConstraint(
            "(status = 'dissolved' AND captain_user_id IS NULL "
            "AND dissolved_at IS NOT NULL) OR "
            "(status = 'forming' AND captain_user_id IS NOT NULL "
            "AND dissolved_at IS NULL)",
            name="captain_and_dissolution_consistent",
        ),
        sa.ForeignKeyConstraint(
            ["captain_user_id"],
            ["users.id"],
            name="fk_teams_captain_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_teams_active_name
        ON teams (lower(name))
        WHERE status = 'forming'
        """
    )
    op.create_index("ix_teams_status_created_at", "teams", ["status", "created_at"])
    op.create_index("ix_teams_invite_code_hash", "teams", ["invite_code_hash"])

    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("added_by_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("admin_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(added_by_admin AND length(trim(admin_reason)) > 0) "
            "OR (NOT added_by_admin AND admin_reason IS NULL)",
            name="admin_reason_consistent",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name="fk_team_members_team_id_teams",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_team_members_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_team_members"),
        sa.UniqueConstraint(
            "team_id",
            "user_id",
            "joined_at",
            name="uq_team_members_team_user_joined_at",
        ),
    )
    op.create_index(
        "uq_team_members_current_user",
        "team_members",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.create_index(
        "ix_team_members_team_left_at",
        "team_members",
        ["team_id", "left_at"],
    )


def upgrade() -> None:
    _drop_legacy_team_triggers()
    _rename_legacy_indexes()
    op.rename_table("team_members", "legacy_competition_team_members")
    op.rename_table("teams", "legacy_competition_teams")
    _create_standalone_tables()
    _install_team_captain_triggers()


def downgrade() -> None:
    # 新独立队伍可兼容挂接到一个占位赛事；原赛事和旧队伍从未删除。
    op.execute(
        f"""
        INSERT INTO competitions (
            id, name, description_markdown, description_html, rules_url,
            status, registration_start, registration_end,
            submission_start, submission_end,
            min_team_size, max_team_size,
            created_by, updated_by, published_at, archived_at,
            created_at, updated_at, revision
        )
        VALUES (
            '{_PLACEHOLDER_COMPETITION_ID}'::uuid,
            '独立队伍迁移占位赛事',
            '由独立队伍迁移降级自动创建。',
            '<p>由独立队伍迁移降级自动创建。</p>',
            NULL,
            'registration_open',
            '2020-01-01 00:00:00+00'::timestamptz,
            '2098-01-01 00:00:00+00'::timestamptz,
            '2098-01-01 00:00:00+00'::timestamptz,
            '2099-01-01 00:00:00+00'::timestamptz,
            1, 20, NULL, NULL, now(), NULL, now(), now(), 1
        )
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO legacy_competition_teams (
            id, competition_id, name, status, captain_user_id,
            invite_code_hash, invite_code_rotated_at,
            min_size_waived_at, min_size_waived_by, waiver_reason,
            disqualified_at, disqualified_by, disqualification_reason,
            locked_at, dissolved_at, created_at, updated_at, revision
        )
        SELECT id,
               '{_PLACEHOLDER_COMPETITION_ID}'::uuid,
               LEFT(name, 70) || ' [独立队伍 ' || id::text || ']',
               status, captain_user_id,
               invite_code_hash, invite_code_rotated_at,
               NULL, NULL, NULL, NULL, NULL, NULL, NULL,
               dissolved_at, created_at, updated_at, revision
        FROM teams
        """
    )
    op.execute(
        f"""
        INSERT INTO legacy_competition_team_members (
            id, team_id, competition_id, user_id, joined_at, left_at,
            added_by_admin, admin_reason
        )
        SELECT id,
               team_id,
               '{_PLACEHOLDER_COMPETITION_ID}'::uuid,
               user_id, joined_at, left_at, added_by_admin, admin_reason
        FROM team_members
        """
    )
    op.execute("DROP TRIGGER IF EXISTS tr_team_members_current_captain ON team_members")
    op.execute("DROP TRIGGER IF EXISTS tr_teams_current_captain ON teams")
    op.drop_table("team_members")
    op.drop_index("uq_teams_active_name", table_name="teams")
    op.drop_index("ix_teams_status_created_at", table_name="teams")
    op.drop_index("ix_teams_invite_code_hash", table_name="teams")
    op.drop_table("teams")
    _restore_legacy_index_names()
    op.rename_table("legacy_competition_teams", "teams")
    op.rename_table("legacy_competition_team_members", "team_members")
    _install_team_captain_triggers()
