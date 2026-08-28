from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import Settings


def test_migration_chain_has_single_head() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))

    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20260828_0013"]


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


def test_alembic_config_accepts_percent_encoded_database_password() -> None:
    settings = Settings(
        app_env="test",
        database_password="password/with+reserved%characters",
    )
    config = Config()

    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    assert config.get_main_option("sqlalchemy.url") == settings.database_url
