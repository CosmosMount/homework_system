"""创建赛事、报名、队伍并扩展团队提交所有者。

Revision ID: 20260825_0005
Revises: 20260824_0004
Create Date: 2026-08-25 10:00:00+08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0005"
down_revision: str | None = "20260824_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def upgrade() -> None:
    op.create_table(
        "competitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description_markdown", sa.Text(), nullable=False),
        sa.Column("description_html", sa.Text(), nullable=False),
        sa.Column("rules_url", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("registration_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submission_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submission_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("min_team_size", sa.Integer(), nullable=False),
        sa.Column("max_team_size", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 200",
            name="name_present",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'registration_open', 'registration_closed', "
            "'submission_open', 'submission_closed', 'archived')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "registration_start < registration_end",
            name="registration_window_order",
        ),
        sa.CheckConstraint(
            "registration_end <= submission_start",
            name="registration_before_submission",
        ),
        sa.CheckConstraint(
            "submission_start < submission_end",
            name="submission_window_order",
        ),
        sa.CheckConstraint(
            "min_team_size BETWEEN 1 AND 20 AND max_team_size BETWEEN min_team_size AND 20",
            name="team_size_range",
        ),
        sa.CheckConstraint(
            "status = 'draft' OR published_at IS NOT NULL",
            name="published_at_present",
        ),
        sa.CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="archived_at_present",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_competitions_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_competitions_updated_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competitions"),
    )
    op.create_index(
        "ix_competitions_status_registration_start",
        "competitions",
        ["status", "registration_start"],
    )
    op.create_index(
        "ix_competitions_status_submission_start",
        "competitions",
        ["status", "submission_start"],
    )

    op.create_table(
        "competition_registrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disqualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disqualified_by", sa.Uuid(), nullable=True),
        sa.Column("disqualification_reason", sa.Text(), nullable=True),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "status IN ('registered', 'withdrawn', 'disqualified')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "(status = 'registered' AND withdrawn_at IS NULL "
            "AND disqualified_at IS NULL AND disqualified_by IS NULL "
            "AND disqualification_reason IS NULL) OR "
            "(status = 'withdrawn' AND withdrawn_at IS NOT NULL "
            "AND disqualified_at IS NULL AND disqualified_by IS NULL "
            "AND disqualification_reason IS NULL) OR "
            "(status = 'disqualified' AND disqualified_at IS NOT NULL "
            "AND disqualified_by IS NOT NULL "
            "AND length(trim(disqualification_reason)) > 0)",
            name="status_metadata_consistent",
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competitions.id"],
            name="fk_competition_registrations_competition_id_competitions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_competition_registrations_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["disqualified_by"],
            ["users.id"],
            name="fk_competition_registrations_disqualified_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competition_registrations"),
        sa.UniqueConstraint(
            "competition_id",
            "user_id",
            name="uq_competition_registrations_competition_user",
        ),
    )
    op.create_index(
        "ix_competition_registrations_competition_status",
        "competition_registrations",
        ["competition_id", "status"],
    )

    op.create_table(
        "competition_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description_markdown", sa.Text(), nullable=False),
        sa.Column("description_html", sa.Text(), nullable=False),
        sa.Column("resource_url", sa.String(length=2000), nullable=True),
        sa.Column(
            "allowed_extensions",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
        ),
        sa.Column("max_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 200",
            name="title_present",
        ),
        sa.CheckConstraint(
            "cardinality(allowed_extensions) >= 1",
            name="allowed_extensions_present",
        ),
        sa.CheckConstraint(
            "max_total_bytes BETWEEN 1 AND 2147483648",
            name="max_total_bytes_range",
        ),
        sa.CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competitions.id"],
            name="fk_competition_tasks_competition_id_competitions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competition_tasks"),
        sa.UniqueConstraint(
            "competition_id",
            "display_order",
            name="uq_competition_tasks_competition_display_order",
        ),
    )
    op.create_index(
        "ix_competition_tasks_competition_deadline",
        "competition_tasks",
        ["competition_id", "deadline"],
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("captain_user_id", sa.Uuid(), nullable=True),
        sa.Column("invite_code_hash", sa.String(length=64), nullable=False),
        sa.Column("invite_code_rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("min_size_waived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("min_size_waived_by", sa.Uuid(), nullable=True),
        sa.Column("waiver_reason", sa.Text(), nullable=True),
        sa.Column("disqualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disqualified_by", sa.Uuid(), nullable=True),
        sa.Column("disqualification_reason", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dissolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps_and_revision(),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 120",
            name="name_present",
        ),
        sa.CheckConstraint(
            "status IN ('forming', 'dissolved', 'locked', 'invalid', 'disqualified', 'archived')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "invite_code_hash ~ '^[0-9a-f]{64}$'",
            name="invite_code_hash_format",
        ),
        sa.CheckConstraint(
            "(status = 'dissolved' AND captain_user_id IS NULL "
            "AND dissolved_at IS NOT NULL) OR "
            "(status <> 'dissolved' AND captain_user_id IS NOT NULL)",
            name="captain_and_dissolution_consistent",
        ),
        sa.CheckConstraint(
            "(min_size_waived_at IS NULL AND min_size_waived_by IS NULL "
            "AND waiver_reason IS NULL) OR "
            "(min_size_waived_at IS NOT NULL AND min_size_waived_by IS NOT NULL "
            "AND length(trim(waiver_reason)) > 0)",
            name="waiver_metadata_consistent",
        ),
        sa.CheckConstraint(
            "(status <> 'disqualified' AND disqualified_at IS NULL "
            "AND disqualified_by IS NULL AND disqualification_reason IS NULL) OR "
            "(status = 'disqualified' AND disqualified_at IS NOT NULL "
            "AND disqualified_by IS NOT NULL "
            "AND length(trim(disqualification_reason)) > 0)",
            name="disqualification_metadata_consistent",
        ),
        sa.CheckConstraint(
            "status NOT IN ('locked', 'archived') OR locked_at IS NOT NULL",
            name="locked_at_present",
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competitions.id"],
            name="fk_teams_competition_id_competitions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["captain_user_id"],
            ["users.id"],
            name="fk_teams_captain_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["min_size_waived_by"],
            ["users.id"],
            name="fk_teams_min_size_waived_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["disqualified_by"],
            ["users.id"],
            name="fk_teams_disqualified_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
        sa.UniqueConstraint(
            "id",
            "competition_id",
            name="uq_teams_id_competition_id",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_teams_competition_active_name
        ON teams (competition_id, lower(name))
        WHERE status <> 'dissolved'
        """
    )
    op.create_index(
        "ix_teams_competition_status",
        "teams",
        ["competition_id", "status"],
    )
    op.create_index(
        "ix_teams_invite_code_hash",
        "teams",
        ["invite_code_hash"],
    )

    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
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
            ["team_id", "competition_id"],
            ["teams.id", "teams.competition_id"],
            name="fk_team_members_team_competition_teams",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competitions.id"],
            name="fk_team_members_competition_id_competitions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_team_members_user_id_users",
            ondelete="RESTRICT",
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
        "uq_team_members_current_competition_user",
        "team_members",
        ["competition_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.create_index(
        "ix_team_members_team_left_at",
        "team_members",
        ["team_id", "left_at"],
    )

    op.execute(
        """
        CREATE FUNCTION pnx_validate_competition_task_deadline()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            window_start timestamptz;
            window_end timestamptz;
        BEGIN
            SELECT submission_start, submission_end
            INTO window_start, window_end
            FROM competitions
            WHERE id = NEW.competition_id;

            IF NOT FOUND
               OR NEW.deadline < window_start
               OR NEW.deadline > window_end THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'competition task deadline is outside submission window';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_competition_tasks_validate_deadline
        BEFORE INSERT OR UPDATE OF competition_id, deadline ON competition_tasks
        FOR EACH ROW
        EXECUTE FUNCTION pnx_validate_competition_task_deadline();
        """
    )
    op.execute(
        """
        CREATE FUNCTION pnx_validate_competition_window_tasks()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM competition_tasks
                WHERE competition_id = NEW.id
                  AND (
                    deadline < NEW.submission_start
                    OR deadline > NEW.submission_end
                  )
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'competition window excludes an existing task deadline';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_competitions_validate_task_deadlines
        BEFORE UPDATE OF submission_start, submission_end ON competitions
        FOR EACH ROW
        EXECUTE FUNCTION pnx_validate_competition_window_tasks();
        """
    )
    op.execute(
        """
        CREATE FUNCTION pnx_validate_team_captain()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            target_team_id uuid;
            target_captain_id uuid;
            target_status text;
        BEGIN
            IF TG_TABLE_NAME = 'teams' THEN
                target_team_id := NEW.id;
            ELSE
                target_team_id := COALESCE(NEW.team_id, OLD.team_id);
            END IF;

            SELECT captain_user_id, status
            INTO target_captain_id, target_status
            FROM teams
            WHERE id = target_team_id;

            IF NOT FOUND OR target_status = 'dissolved' THEN
                RETURN NULL;
            END IF;

            IF target_captain_id IS NULL OR NOT EXISTS (
                SELECT 1
                FROM team_members
                WHERE team_id = target_team_id
                  AND user_id = target_captain_id
                  AND left_at IS NULL
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'team captain must be a current member';
            END IF;
            RETURN NULL;
        END;
        $$;
        """
    )
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

    op.drop_index("uq_submissions_assignment_owner", table_name="submissions")
    op.alter_column("submissions", "assignment_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("submissions", "owner_user_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("submissions", sa.Column("competition_task_id", sa.Uuid(), nullable=True))
    op.add_column("submissions", sa.Column("owner_team_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_submissions_competition_task_id_competition_tasks",
        "submissions",
        "competition_tasks",
        ["competition_task_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_submissions_owner_team_id_teams",
        "submissions",
        "teams",
        ["owner_team_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "owner_target_pair",
        "submissions",
        """
        (
          assignment_id IS NOT NULL
          AND competition_task_id IS NULL
          AND owner_user_id IS NOT NULL
          AND owner_team_id IS NULL
        )
        OR
        (
          assignment_id IS NULL
          AND competition_task_id IS NOT NULL
          AND owner_user_id IS NULL
          AND owner_team_id IS NOT NULL
        )
        """,
    )
    op.create_index(
        "uq_submissions_assignment_owner",
        "submissions",
        ["assignment_id", "owner_user_id"],
        unique=True,
        postgresql_where=sa.text("assignment_id IS NOT NULL"),
    )
    op.create_index(
        "uq_submissions_competition_task_owner",
        "submissions",
        ["competition_task_id", "owner_team_id"],
        unique=True,
        postgresql_where=sa.text("competition_task_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_submissions_competition_task_owner",
        table_name="submissions",
    )
    op.drop_index("uq_submissions_assignment_owner", table_name="submissions")
    op.drop_constraint(
        op.f("ck_submissions_owner_target_pair"),
        "submissions",
        type_="check",
    )
    op.drop_constraint(
        "fk_submissions_owner_team_id_teams",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_competition_task_id_competition_tasks",
        "submissions",
        type_="foreignkey",
    )
    op.drop_column("submissions", "owner_team_id")
    op.drop_column("submissions", "competition_task_id")
    op.alter_column("submissions", "owner_user_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("submissions", "assignment_id", existing_type=sa.Uuid(), nullable=False)
    op.create_index(
        "uq_submissions_assignment_owner",
        "submissions",
        ["assignment_id", "owner_user_id"],
        unique=True,
    )

    op.execute("DROP TRIGGER IF EXISTS tr_team_members_current_captain ON team_members")
    op.execute("DROP TRIGGER IF EXISTS tr_teams_current_captain ON teams")
    op.execute("DROP FUNCTION IF EXISTS pnx_validate_team_captain()")
    op.execute("DROP TRIGGER IF EXISTS tr_competitions_validate_task_deadlines ON competitions")
    op.execute("DROP FUNCTION IF EXISTS pnx_validate_competition_window_tasks()")
    op.execute("DROP TRIGGER IF EXISTS tr_competition_tasks_validate_deadline ON competition_tasks")
    op.execute("DROP FUNCTION IF EXISTS pnx_validate_competition_task_deadline()")

    op.drop_table("team_members")
    op.drop_index("ix_teams_invite_code_hash", table_name="teams")
    op.drop_index("ix_teams_competition_status", table_name="teams")
    op.execute("DROP INDEX IF EXISTS uq_teams_competition_active_name")
    op.drop_table("teams")
    op.drop_table("competition_tasks")
    op.drop_table("competition_registrations")
    op.drop_table("competitions")
