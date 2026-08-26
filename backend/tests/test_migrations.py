from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import Settings


def test_migration_chain_has_single_head() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))

    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20260826_0008"]


def test_alembic_config_accepts_percent_encoded_database_password() -> None:
    settings = Settings(
        app_env="test",
        database_password="password/with+reserved%characters",
    )
    config = Config()

    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    assert config.get_main_option("sqlalchemy.url") == settings.database_url
