from types import SimpleNamespace
from typing import cast

import pytest

from app.core.config import Settings
from app.operations.capacity_seed import (
    CAPACITY_ADMIN_COUNT,
    CAPACITY_STUDENT_COUNT,
    CapacityDataset,
    CapacityDatasetSeeder,
    capacity_student_email,
)
from app.operations.synthetic_seed import SyntheticSeedError


class FakePasswordManager:
    def hash(self, password: str) -> str:
        assert password == "Correct-Horse-Battery-Staple-2026!"
        return "$argon2id$synthetic-capacity-hash"


class FakeCapacitySeedRepository:
    def __init__(self) -> None:
        self.dataset: CapacityDataset | None = None
        self.commits = 0

    async def has_capacity_dataset(self) -> bool:
        return self.dataset is not None

    async def store_capacity_dataset(self, dataset: CapacityDataset) -> None:
        assert self.dataset is None
        self.dataset = dataset

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_capacity_seed_builds_exact_idempotent_synthetic_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.operations.capacity_seed.get_password_manager",
        lambda: FakePasswordManager(),
    )
    repository = FakeCapacitySeedRepository()
    seeder = CapacityDatasetSeeder(repository, Settings(app_env="test"))

    first = await seeder.seed(password="Correct-Horse-Battery-Staple-2026!")
    second = await seeder.seed(password="Correct-Horse-Battery-Staple-2026!")

    assert first == {"created": True, **CapacityDatasetSeeder.expected_summary()}
    assert second == {"created": False, **CapacityDatasetSeeder.expected_summary()}
    assert repository.commits == 1
    assert repository.dataset is not None

    dataset = repository.dataset
    assert len(dataset.users) == CAPACITY_STUDENT_COUNT + CAPACITY_ADMIN_COUNT
    assert len(dataset.announcements) == 100
    assert len(dataset.student_notifications) == 30_000
    assert len(dataset.assignments) == 40
    assert len(dataset.assignment_audience_users) == 12_000
    assert len(dataset.competitions) == 10
    assert len(dataset.teams) == 100
    assert len(dataset.team_members) == 300
    assert len(dataset.submissions) == 12_090
    assert len(dataset.submission_versions) == 24_180
    assert len(dataset.audit_logs) == 1

    allowed_extension_rows = [
        *dataset.assignments,
        *dataset.competition_tasks,
    ]
    assert all(
        all(
            not str(extension).startswith(".")
            for extension in cast(list[object], row["allowed_extensions"])
        )
        for row in allowed_extension_rows
    )
    user_ids = [row["id"] for row in dataset.users]
    assert all(getattr(value, "version", None) == 7 for value in user_ids)
    assert all(
        str(row["email"]).startswith("capacity-")
        and str(row["email"]).endswith("@connect.hkust-gz.edu.cn")
        for row in dataset.users
    )
    assert {row["password_hash"] for row in dataset.users} == {"$argon2id$synthetic-capacity-hash"}
    assert dataset.teams[-1]["status"] == "forming"
    assert dataset.competitions[-1]["status"] == "registration_open"


@pytest.mark.asyncio
async def test_capacity_seed_refuses_production_before_repository_access() -> None:
    repository = FakeCapacitySeedRepository()
    production_settings = cast(
        Settings,
        SimpleNamespace(app_env="production"),
    )

    with pytest.raises(SyntheticSeedError) as captured:
        await CapacityDatasetSeeder(repository, production_settings).seed(
            password="Correct-Horse-Battery-Staple-2026!"
        )

    assert captured.value.code == "SYNTHETIC_SEED_FORBIDDEN_IN_PRODUCTION"
    assert repository.dataset is None
    assert repository.commits == 0


def test_capacity_student_email_is_fixed_and_range_checked() -> None:
    assert capacity_student_email(0) == "capacity-student-001@connect.hkust-gz.edu.cn"
    assert capacity_student_email(299) == "capacity-student-300@connect.hkust-gz.edu.cn"
    with pytest.raises(ValueError):
        capacity_student_email(300)
