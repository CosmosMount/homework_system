from pathlib import Path


def test_standalone_team_migration_archives_legacy_data_without_deleting_it() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration = (
        backend_root / "migrations" / "versions" / "20260904_0020_standalone_teams.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "20260904_0020"' in migration
    assert 'down_revision: str | None = "20260904_0019"' in migration
    assert 'op.rename_table("teams", "legacy_competition_teams")' in migration
    assert 'op.rename_table("team_members", "legacy_competition_team_members")' in migration
    assert 'op.create_table(\n        "teams"' in migration
    assert 'op.create_table(\n        "team_members"' in migration
    assert "DELETE FROM competitions" not in migration
    assert "DELETE FROM submissions" not in migration
    assert "DELETE FROM teams" not in migration
    assert (
        "competition_id"
        not in migration.split("def _create_standalone_tables", 1)[1].split("def upgrade", 1)[0]
    )


def test_standalone_team_migration_downgrade_preserves_new_teams() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration = (
        backend_root / "migrations" / "versions" / "20260904_0020_standalone_teams.py"
    ).read_text(encoding="utf-8")
    downgrade = migration.split("def downgrade() -> None:", 1)[1]

    assert "INSERT INTO legacy_competition_teams" in downgrade
    assert "INSERT INTO legacy_competition_team_members" in downgrade
    assert "独立队伍迁移占位赛事" in downgrade
    assert 'op.rename_table("legacy_competition_teams", "teams")' in downgrade
    assert 'op.rename_table("legacy_competition_team_members", "team_members")' in downgrade
