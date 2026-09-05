from typing import Any

# 这些对象只为保留 0020 之前的不可变历史数据而存在，运行时不会查询它们。
LEGACY_TABLES = frozenset(
    {
        "competitions",
        "competition_registrations",
        "competition_tasks",
        "legacy_competition_teams",
        "legacy_competition_team_members",
    }
)
LEGACY_SUBMISSION_CONSTRAINTS = frozenset(
    {
        "fk_submissions_competition_task_id_competition_tasks",
        "fk_submissions_owner_team_id_teams",
        "ck_submissions_owner_target_pair",
    }
)
LEGACY_SUBMISSION_INDEXES = frozenset({"uq_submissions_competition_task_owner"})


def include_schema_object(
    obj: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """只排除 0020 明确保留、但不属于当前产品模型的 legacy 数据结构。"""
    del compare_to
    table_name = getattr(getattr(obj, "table", None), "name", None)

    if type_ == "table" and reflected and name in LEGACY_TABLES:
        return False
    if (
        type_ in {"foreign_key_constraint", "check_constraint"}
        and reflected
        and table_name == "submissions"
        and name in LEGACY_SUBMISSION_CONSTRAINTS
    ):
        return False
    return not (
        type_ == "index"
        and reflected
        and table_name == "submissions"
        and name in LEGACY_SUBMISSION_INDEXES
    )
