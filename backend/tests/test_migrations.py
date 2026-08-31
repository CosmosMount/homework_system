from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import Settings


def test_migration_chain_has_single_head() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))

    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20260831_0017"]


def test_persistent_login_migration_is_reversible_and_follows_account_deletion() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration_path = (
        backend_root / "migrations" / "versions" / "20260830_0016_persistent_login_ip_binding.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "20260830_0016"' in source
    assert 'down_revision: str | None = "20260829_0015"' in source
    assert 'sa.Column("ip_binding_hash", sa.String(length=64), nullable=True)' in source
    assert 'op.drop_column("sessions", "ip_binding_hash")' in source


def test_admin_content_deleted_visibility_migration_has_safe_contract() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration_path = (
        backend_root
        / "migrations"
        / "versions"
        / "20260831_0017_admin_content_deleted_visibility.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "20260831_0017"' in source
    assert 'down_revision: str | None = "20260830_0016"' in source
    assert source.count('sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)') == 2
    assert "announcement.delete" in source
    assert "assignment.delete" in source
    assert "MIN(created_at) AS deleted_at" in source
    assert "change_summary ->> 'deletion_mode' = 'archive'" in source
    assert source.count('"deleted_requires_archived"') == 4
    assert source.count('op.drop_column("') >= 2
    assert source.index("op.drop_constraint") < source.index(
        'op.drop_column("assignments", "deleted_at")'
    )


def test_account_activity_migration_has_reversible_static_contract() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration_path = (
        backend_root / "migrations" / "versions" / "20260827_0012_account_activity_cleanup.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "20260827_0012"' in source
    assert 'down_revision: str | None = "20260827_0011"' in source
    assert 'sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True)' in source
    assert "MAX(last_seen_at) AS last_seen_at" in source
    assert "GROUP BY user_id" in source
    assert source.index("MAX(last_seen_at)") < source.index("op.drop_constraint")
    assert '"fk_assignment_audience_users_user_id_users"' in source
    assert 'ondelete="CASCADE"' in source
    assert 'ondelete="RESTRICT"' in source
    assert 'op.drop_column("users", "last_active_at")' in source


def test_questionnaire_migration_preserves_existing_surveys_and_is_reversible() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration_path = (
        backend_root / "migrations" / "versions" / "20260828_0013_intention_questionnaires.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "20260828_0013"' in source
    assert 'down_revision: str | None = "20260827_0012"' in source
    assert '"intention_questions"' in source
    assert "SELECT id, id, title, allow_multiple, 0" in source
    assert "UPDATE intention_options SET question_id = survey_id" in source
    assert "GREATEST(revision, 1)" in source
    assert "ROW_NUMBER() OVER" in source
    assert 'op.drop_table("intention_questions")' in source
    assert 'op.drop_column("intention_surveys", "max_submissions")' in source


def test_help_request_migration_is_reversible_and_follows_questionnaires() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration_path = backend_root / "migrations" / "versions" / "20260828_0014_help_requests.py"
    source = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "20260828_0014"' in source
    assert 'down_revision: str | None = "20260828_0013"' in source
    assert '"help_requests"' in source
    assert '"request_type_allowed"' in source
    assert '"resolution_state_consistent"' in source
    assert '"ix_help_requests_student_list"' in source
    assert '"ix_help_requests_admin_list"' in source
    assert 'ondelete="RESTRICT"' in source
    assert 'op.drop_table("help_requests")' in source


def test_account_deletion_migration_has_safe_static_contract() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration_path = backend_root / "migrations" / "versions" / "20260829_0015_account_deletion.py"
    source = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "20260829_0015"' in source
    assert 'down_revision: str | None = "20260828_0014"' in source
    assert "_SHARED_REFERENCES" in source
    assert "_PERSONAL_REFERENCES" in source
    assert 'ondelete="SET NULL"' in source
    assert 'ondelete="CASCADE"' in source
    assert '"fk_files_owner_user_id_users"' in source
    assert '"fk_submissions_owner_user_id_users"' in source
    assert '"fk_help_requests_created_by_users"' in source
    assert '"fk_assignment_excellent_version_submission_versions"' in source
    assert "current_setting('pnx.account_erasure', true) = 'on'" in source
    assert "NOT EXISTS" in source
    assert "submission versions are immutable" in source
    assert "_restore_original_version_guard()" in source
    assert "ACCOUNT_ERASURE_DOWNGRADE_REQUIRES_BACKUP_RESTORE_OR_FORWARD_FIX" in source
    assert "captain_user_id" not in source


def test_alembic_config_accepts_percent_encoded_database_password() -> None:
    settings = Settings(
        app_env="test",
        database_password="password/with+reserved%characters",
    )
    config = Config()

    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    assert config.get_main_option("sqlalchemy.url") == settings.database_url
