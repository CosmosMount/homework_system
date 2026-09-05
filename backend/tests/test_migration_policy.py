from dataclasses import dataclass

from app.database.migration_policy import include_schema_object


@dataclass
class _Table:
    name: str


@dataclass
class _Object:
    table: _Table


def test_migration_policy_excludes_only_named_legacy_tables() -> None:
    assert not include_schema_object(None, "competitions", "table", True, None)
    assert not include_schema_object(
        None,
        "legacy_competition_teams",
        "table",
        True,
        None,
    )
    assert include_schema_object(None, "assignments", "table", True, None)
    assert include_schema_object(None, "competitions", "table", False, None)


def test_migration_policy_excludes_only_known_submission_objects() -> None:
    submission_object = _Object(table=_Table(name="submissions"))

    assert not include_schema_object(
        submission_object,
        "fk_submissions_owner_team_id_teams",
        "foreign_key_constraint",
        True,
        None,
    )
    assert not include_schema_object(
        submission_object,
        "uq_submissions_competition_task_owner",
        "index",
        True,
        None,
    )
    assert include_schema_object(
        submission_object,
        "uq_submissions_assignment_owner",
        "index",
        True,
        None,
    )
    assert include_schema_object(
        _Object(table=_Table(name="assignments")),
        "fk_submissions_owner_team_id_teams",
        "foreign_key_constraint",
        True,
        None,
    )
