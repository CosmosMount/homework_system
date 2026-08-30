"""Allow complete account erasure while retaining shared business records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0015"
down_revision: str | None = "20260828_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHARED_REFERENCES: tuple[tuple[str, str, str, bool], ...] = (
    ("users", "disabled_by", "fk_users_disabled_by_users", True),
    ("announcements", "created_by", "fk_announcements_created_by_users", False),
    ("announcements", "updated_by", "fk_announcements_updated_by_users", False),
    ("assignments", "created_by", "fk_assignments_created_by_users", False),
    ("assignments", "updated_by", "fk_assignments_updated_by_users", False),
    ("assignment_extensions", "granted_by", "fk_assignment_extensions_granted_by_users", False),
    (
        "assignment_excellent_submissions",
        "marked_by",
        "fk_assignment_excellent_submissions_marked_by_users",
        False,
    ),
    ("competitions", "created_by", "fk_competitions_created_by_users", False),
    ("competitions", "updated_by", "fk_competitions_updated_by_users", False),
    (
        "competition_registrations",
        "disqualified_by",
        "fk_competition_registrations_disqualified_by_users",
        True,
    ),
    ("teams", "min_size_waived_by", "fk_teams_min_size_waived_by_users", True),
    ("teams", "disqualified_by", "fk_teams_disqualified_by_users", True),
    ("intention_surveys", "created_by", "fk_intention_surveys_created_by_users", False),
    ("intention_surveys", "updated_by", "fk_intention_surveys_updated_by_users", False),
    ("knowledge_sync_runs", "triggered_by", "fk_knowledge_sync_runs_triggered_by_users", False),
    ("help_requests", "resolved_by", "fk_help_requests_resolved_by_users", True),
    ("files", "owner_user_id", "fk_files_owner_user_id_users", False),
    ("submission_versions", "submitted_by", "fk_submission_versions_submitted_by_users", False),
    ("feedback", "created_by", "fk_feedback_created_by_users", False),
)

_PERSONAL_REFERENCES: tuple[tuple[str, str, str, str], ...] = (
    (
        "assignment_extensions",
        "user_id",
        "fk_assignment_extensions_user_id_users",
        "users",
    ),
    ("submissions", "owner_user_id", "fk_submissions_owner_user_id_users", "users"),
    (
        "submission_versions",
        "submission_id",
        "fk_submission_versions_submission_id_submissions",
        "submissions",
    ),
    (
        "version_files",
        "version_id",
        "fk_version_files_version_id_submission_versions",
        "submission_versions",
    ),
    ("feedback", "version_id", "fk_feedback_version_id_submission_versions", "submission_versions"),
    (
        "assignment_excellent_submissions",
        "version_id",
        "fk_assignment_excellent_version_submission_versions",
        "submission_versions",
    ),
    (
        "competition_registrations",
        "user_id",
        "fk_competition_registrations_user_id_users",
        "users",
    ),
    ("team_members", "user_id", "fk_team_members_user_id_users", "users"),
    ("intention_responses", "user_id", "fk_intention_responses_user_id_users", "users"),
    ("upload_sessions", "user_id", "fk_upload_sessions_user_id_users", "users"),
    ("help_requests", "created_by", "fk_help_requests_created_by_users", "users"),
)


def _replace_fk(
    table_name: str,
    column_name: str,
    constraint_name: str,
    referred_table: str,
    *,
    ondelete: str,
) -> None:
    op.drop_constraint(op.f(constraint_name), table_name, type_="foreignkey")
    op.create_foreign_key(
        op.f(constraint_name),
        table_name,
        referred_table,
        [column_name],
        ["id"],
        ondelete=ondelete,
    )


def _drop_actor_checks() -> None:
    op.drop_constraint(
        op.f("ck_competition_registrations_status_metadata_consistent"),
        "competition_registrations",
        type_="check",
    )
    op.drop_constraint(op.f("ck_teams_waiver_metadata_consistent"), "teams", type_="check")
    op.drop_constraint(
        op.f("ck_teams_disqualification_metadata_consistent"), "teams", type_="check"
    )
    op.drop_constraint(
        op.f("ck_help_requests_resolution_state_consistent"),
        "help_requests",
        type_="check",
    )


def _create_erasure_compatible_checks() -> None:
    op.create_check_constraint(
        op.f("ck_competition_registrations_status_metadata_consistent"),
        "competition_registrations",
        """
        (status = 'registered' AND withdrawn_at IS NULL
            AND disqualified_at IS NULL AND disqualified_by IS NULL
            AND disqualification_reason IS NULL)
        OR
        (status = 'withdrawn' AND withdrawn_at IS NOT NULL
            AND disqualified_at IS NULL AND disqualified_by IS NULL
            AND disqualification_reason IS NULL)
        OR
        (status = 'disqualified' AND disqualified_at IS NOT NULL
            AND length(trim(disqualification_reason)) > 0)
        """,
    )
    op.create_check_constraint(
        op.f("ck_teams_waiver_metadata_consistent"),
        "teams",
        """
        (min_size_waived_at IS NULL AND min_size_waived_by IS NULL
            AND waiver_reason IS NULL)
        OR
        (min_size_waived_at IS NOT NULL AND length(trim(waiver_reason)) > 0)
        """,
    )
    op.create_check_constraint(
        op.f("ck_teams_disqualification_metadata_consistent"),
        "teams",
        """
        (status <> 'disqualified' AND disqualified_at IS NULL
            AND disqualified_by IS NULL AND disqualification_reason IS NULL)
        OR
        (status = 'disqualified' AND disqualified_at IS NOT NULL
            AND length(trim(disqualification_reason)) > 0)
        """,
    )
    op.create_check_constraint(
        op.f("ck_help_requests_resolution_state_consistent"),
        "help_requests",
        """
        (status = 'open'
            AND resolution_markdown IS NULL
            AND resolution_html IS NULL
            AND resolved_by IS NULL
            AND resolved_at IS NULL)
        OR
        (status = 'resolved'
            AND length(trim(resolution_markdown)) BETWEEN 1 AND 20000
            AND resolution_html IS NOT NULL
            AND resolved_at IS NOT NULL)
        """,
    )


def _create_original_checks() -> None:
    op.create_check_constraint(
        op.f("ck_competition_registrations_status_metadata_consistent"),
        "competition_registrations",
        """
        (status = 'registered' AND withdrawn_at IS NULL
            AND disqualified_at IS NULL AND disqualified_by IS NULL
            AND disqualification_reason IS NULL)
        OR
        (status = 'withdrawn' AND withdrawn_at IS NOT NULL
            AND disqualified_at IS NULL AND disqualified_by IS NULL
            AND disqualification_reason IS NULL)
        OR
        (status = 'disqualified' AND disqualified_at IS NOT NULL
            AND disqualified_by IS NOT NULL
            AND length(trim(disqualification_reason)) > 0)
        """,
    )
    op.create_check_constraint(
        op.f("ck_teams_waiver_metadata_consistent"),
        "teams",
        """
        (min_size_waived_at IS NULL AND min_size_waived_by IS NULL
            AND waiver_reason IS NULL)
        OR
        (min_size_waived_at IS NOT NULL AND min_size_waived_by IS NOT NULL
            AND length(trim(waiver_reason)) > 0)
        """,
    )
    op.create_check_constraint(
        op.f("ck_teams_disqualification_metadata_consistent"),
        "teams",
        """
        (status <> 'disqualified' AND disqualified_at IS NULL
            AND disqualified_by IS NULL AND disqualification_reason IS NULL)
        OR
        (status = 'disqualified' AND disqualified_at IS NOT NULL
            AND disqualified_by IS NOT NULL
            AND length(trim(disqualification_reason)) > 0)
        """,
    )
    op.create_check_constraint(
        op.f("ck_help_requests_resolution_state_consistent"),
        "help_requests",
        """
        (status = 'open'
            AND resolution_markdown IS NULL
            AND resolution_html IS NULL
            AND resolved_by IS NULL
            AND resolved_at IS NULL)
        OR
        (status = 'resolved'
            AND length(trim(resolution_markdown)) BETWEEN 1 AND 20000
            AND resolution_html IS NOT NULL
            AND resolved_by IS NOT NULL
            AND resolved_at IS NOT NULL)
        """,
    )


def _install_account_erasure_version_guard() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pnx_reject_submission_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE'
                AND current_setting('pnx.account_erasure', true) = 'on'
                AND NOT EXISTS (
                    SELECT 1
                    FROM submissions
                    WHERE id = OLD.submission_id
                )
            THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = 'submission versions are immutable';
        END;
        $$;
        """
    )


def _restore_original_version_guard() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pnx_reject_submission_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = 'submission versions are immutable';
        END;
        $$;
        """
    )


def _ensure_downgrade_is_safe() -> None:
    connection = op.get_bind()
    unsafe_predicates = [
        f"{table_name}.{column_name} IS NULL"
        for table_name, column_name, _constraint_name, originally_nullable in _SHARED_REFERENCES
        if not originally_nullable
    ]
    unsafe_predicates.extend(
        (
            "competition_registrations.status = 'disqualified' "
            "AND competition_registrations.disqualified_by IS NULL",
            "teams.min_size_waived_at IS NOT NULL AND teams.min_size_waived_by IS NULL",
            "teams.status = 'disqualified' AND teams.disqualified_by IS NULL",
            "help_requests.status = 'resolved' AND help_requests.resolved_by IS NULL",
        )
    )
    for predicate in unsafe_predicates:
        table_name = predicate.split(".", maxsplit=1)[0]
        found = connection.execute(
            sa.text(f"SELECT 1 FROM {table_name} WHERE {predicate} LIMIT 1")
        ).first()
        if found is not None:
            raise RuntimeError("ACCOUNT_ERASURE_DOWNGRADE_REQUIRES_BACKUP_RESTORE_OR_FORWARD_FIX")


def upgrade() -> None:
    _drop_actor_checks()
    _create_erasure_compatible_checks()

    for table_name, column_name, constraint_name, originally_nullable in _SHARED_REFERENCES:
        op.drop_constraint(op.f(constraint_name), table_name, type_="foreignkey")
        if not originally_nullable:
            op.alter_column(table_name, column_name, existing_type=sa.Uuid(), nullable=True)
        op.create_foreign_key(
            op.f(constraint_name),
            table_name,
            "users",
            [column_name],
            ["id"],
            ondelete="SET NULL",
        )

    for table_name, column_name, constraint_name, referred_table in _PERSONAL_REFERENCES:
        _replace_fk(
            table_name,
            column_name,
            constraint_name,
            referred_table,
            ondelete="CASCADE",
        )
    _install_account_erasure_version_guard()


def downgrade() -> None:
    _ensure_downgrade_is_safe()

    for table_name, column_name, constraint_name, referred_table in reversed(_PERSONAL_REFERENCES):
        _replace_fk(
            table_name,
            column_name,
            constraint_name,
            referred_table,
            ondelete="RESTRICT",
        )

    for table_name, column_name, constraint_name, originally_nullable in reversed(
        _SHARED_REFERENCES
    ):
        op.drop_constraint(op.f(constraint_name), table_name, type_="foreignkey")
        if not originally_nullable:
            op.alter_column(table_name, column_name, existing_type=sa.Uuid(), nullable=False)
        op.create_foreign_key(
            op.f(constraint_name),
            table_name,
            "users",
            [column_name],
            ["id"],
            ondelete="RESTRICT",
        )

    _drop_actor_checks()
    _create_original_checks()
    _restore_original_version_guard()
