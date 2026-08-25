import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.core.config import Settings
from app.core.security import get_password_manager, validate_password
from app.operations.synthetic_seed import SyntheticSeedError

CAPACITY_DATASET_VERSION = 1
CAPACITY_MARKER_REQUEST_ID = "capacity-seed-v1"
CAPACITY_STUDENT_COUNT = 300
CAPACITY_ADMIN_COUNT = 10
CAPACITY_ANNOUNCEMENT_COUNT = 100
CAPACITY_ASSIGNMENT_COUNT = 40
CAPACITY_COMPETITION_COUNT = 10
CAPACITY_TEAM_COUNT = 100
CAPACITY_COHORT_COUNT = 4
CAPACITY_DIRECTION_COUNT = 8

_UUID_EPOCH_MS = 1_767_225_600_000
_PUBLISHED_BASE = datetime(2025, 9, 1, 8, tzinfo=UTC)
_FUTURE_END = datetime(2030, 7, 1, 8, tzinfo=UTC)

type Row = dict[str, object]


@dataclass(slots=True)
class CapacityDataset:
    cohorts: list[Row]
    directions: list[Row]
    users: list[Row]
    announcements: list[Row]
    student_notifications: list[Row]
    assignments: list[Row]
    assignment_audience_users: list[Row]
    competitions: list[Row]
    competition_tasks: list[Row]
    competition_registrations: list[Row]
    teams: list[Row]
    team_members: list[Row]
    submissions: list[Row]
    submission_versions: list[Row]
    audit_logs: list[Row]


class CapacitySeedRepositoryProtocol(Protocol):
    async def has_capacity_dataset(self) -> bool: ...

    async def store_capacity_dataset(self, dataset: CapacityDataset) -> None: ...

    async def commit(self) -> None: ...


def capacity_student_email(index: int) -> str:
    if not 0 <= index < CAPACITY_STUDENT_COUNT:
        raise ValueError("capacity student index is out of range")
    return f"capacity-student-{index + 1:03d}@connect.hkust-gz.edu.cn"


def _capacity_uuid(category: str, index: int) -> UUID:
    digest = hashlib.sha256(f"pnx-capacity-v1:{category}:{index}".encode()).digest()
    timestamp_ms = _UUID_EPOCH_MS + index % 86_400_000
    random_a = int.from_bytes(digest[:2]) & ((1 << 12) - 1)
    random_b = int.from_bytes(digest[2:10]) & ((1 << 62) - 1)
    value = (timestamp_ms << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    return UUID(int=value)


def _mixin_fields(at: datetime) -> Row:
    return {"created_at": at, "updated_at": at, "revision": 1}


def _summary(dataset: CapacityDataset) -> dict[str, int]:
    return {
        "dataset_version": CAPACITY_DATASET_VERSION,
        "cohorts": len(dataset.cohorts),
        "directions": len(dataset.directions),
        "students": CAPACITY_STUDENT_COUNT,
        "admins": CAPACITY_ADMIN_COUNT,
        "announcements": len(dataset.announcements),
        "student_notifications": len(dataset.student_notifications),
        "assignments": len(dataset.assignments),
        "assignment_audience_users": len(dataset.assignment_audience_users),
        "competitions": len(dataset.competitions),
        "competition_tasks": len(dataset.competition_tasks),
        "competition_registrations": len(dataset.competition_registrations),
        "teams": len(dataset.teams),
        "team_members": len(dataset.team_members),
        "submissions": len(dataset.submissions),
        "submission_versions": len(dataset.submission_versions),
    }


class CapacityDatasetBuilder:
    def __init__(self, *, password_hash: str) -> None:
        self._password_hash = password_hash
        self._cohort_ids = [
            _capacity_uuid("cohort", index) for index in range(CAPACITY_COHORT_COUNT)
        ]
        self._direction_ids = [
            _capacity_uuid("direction", index) for index in range(CAPACITY_DIRECTION_COUNT)
        ]
        self._admin_ids = [_capacity_uuid("admin", index) for index in range(CAPACITY_ADMIN_COUNT)]
        self._student_ids = [
            _capacity_uuid("student", index) for index in range(CAPACITY_STUDENT_COUNT)
        ]

    def build(self) -> CapacityDataset:
        cohorts = self._build_cohorts()
        directions = self._build_directions()
        users = self._build_users()
        announcements, student_notifications = self._build_announcements()
        (
            assignments,
            assignment_audience_users,
            assignment_submissions,
            assignment_versions,
        ) = self._build_assignments()
        (
            competitions,
            competition_tasks,
            registrations,
            teams,
            team_members,
            competition_submissions,
            competition_versions,
        ) = self._build_competitions()
        dataset = CapacityDataset(
            cohorts=cohorts,
            directions=directions,
            users=users,
            announcements=announcements,
            student_notifications=student_notifications,
            assignments=assignments,
            assignment_audience_users=assignment_audience_users,
            competitions=competitions,
            competition_tasks=competition_tasks,
            competition_registrations=registrations,
            teams=teams,
            team_members=team_members,
            submissions=assignment_submissions + competition_submissions,
            submission_versions=assignment_versions + competition_versions,
            audit_logs=[],
        )
        dataset.audit_logs.append(self._build_marker(_summary(dataset)))
        return dataset

    def _build_cohorts(self) -> list[Row]:
        rows: list[Row] = []
        for index, cohort_id in enumerate(self._cohort_ids):
            rows.append(
                {
                    "id": cohort_id,
                    "code": f"CAPACITY-{index + 1}",
                    "name": f"虚构容量届次 {index + 1}",
                    "start_year": 2025 + index,
                    "is_active": True,
                    **_mixin_fields(_PUBLISHED_BASE),
                }
            )
        return rows

    def _build_directions(self) -> list[Row]:
        rows: list[Row] = []
        for index, direction_id in enumerate(self._direction_ids):
            rows.append(
                {
                    "id": direction_id,
                    "code": f"CAPACITY-DIRECTION-{index + 1}",
                    "name": f"虚构容量方向 {index + 1}",
                    "description": "仅用于非生产容量与性能验收。",
                    "is_active": True,
                    **_mixin_fields(_PUBLISHED_BASE),
                }
            )
        return rows

    def _build_users(self) -> list[Row]:
        rows: list[Row] = []
        for index, user_id in enumerate(self._admin_ids):
            email = f"capacity-admin-{index + 1:02d}@connect.hkust-gz.edu.cn"
            rows.append(
                self._user_row(
                    user_id=user_id,
                    email=email,
                    student_number=f"CAP-ADM-{index + 1:02d}",
                    full_name=f"虚构容量管理员 {index + 1:02d}",
                    role="admin",
                    cohort_id=None,
                    direction_id=None,
                )
            )
        for index, user_id in enumerate(self._student_ids):
            rows.append(
                self._user_row(
                    user_id=user_id,
                    email=capacity_student_email(index),
                    student_number=f"CAP-STU-{index + 1:03d}",
                    full_name=f"虚构容量学生 {index + 1:03d}",
                    role="student",
                    cohort_id=self._cohort_ids[index % len(self._cohort_ids)],
                    direction_id=self._direction_ids[index % len(self._direction_ids)],
                )
            )
        return rows

    def _user_row(
        self,
        *,
        user_id: UUID,
        email: str,
        student_number: str,
        full_name: str,
        role: str,
        cohort_id: UUID | None,
        direction_id: UUID | None,
    ) -> Row:
        return {
            "id": user_id,
            "email": email,
            "email_normalized": email,
            "student_number": student_number,
            "full_name": full_name,
            "password_hash": self._password_hash,
            "role": role,
            "status": "active",
            "cohort_id": cohort_id,
            "direction_id": direction_id,
            "email_verified_at": _PUBLISHED_BASE,
            "disabled_at": None,
            "disabled_by": None,
            "disabled_reason": None,
            "password_changed_at": _PUBLISHED_BASE,
            **_mixin_fields(_PUBLISHED_BASE),
        }

    def _build_announcements(self) -> tuple[list[Row], list[Row]]:
        announcements: list[Row] = []
        notifications: list[Row] = []
        for announcement_index in range(CAPACITY_ANNOUNCEMENT_COUNT):
            announcement_id = _capacity_uuid("announcement", announcement_index)
            published_at = _PUBLISHED_BASE + timedelta(hours=announcement_index)
            archived = announcement_index >= 90
            announcements.append(
                {
                    "id": announcement_id,
                    "title": f"容量通知 {announcement_index + 1:03d}",
                    "summary": "虚构容量数据通知摘要。",
                    "body_markdown": "这是用于容量验收的虚构通知。",
                    "body_html": "<p>这是用于容量验收的虚构通知。</p>",
                    "status": "archived" if archived else "published",
                    "all_students": True,
                    "audience_match": "intersection",
                    "publish_at": published_at,
                    "published_at": published_at,
                    "pinned_until": None,
                    "send_email": False,
                    "created_by": self._admin_ids[announcement_index % CAPACITY_ADMIN_COUNT],
                    "updated_by": self._admin_ids[announcement_index % CAPACITY_ADMIN_COUNT],
                    "archived_at": published_at + timedelta(days=30) if archived else None,
                    **_mixin_fields(published_at),
                }
            )
            for student_index, student_id in enumerate(self._student_ids):
                notifications.append(
                    {
                        "id": _capacity_uuid(
                            "student-notification",
                            announcement_index * CAPACITY_STUDENT_COUNT + student_index,
                        ),
                        "user_id": student_id,
                        "notification_type": "announcement",
                        "event_key": f"capacity-announcement:{announcement_index:03d}",
                        "title": f"容量通知 {announcement_index + 1:03d}",
                        "target_type": "announcement",
                        "target_id": announcement_id,
                        "target_url": f"/announcements/{announcement_id}",
                        "created_at": published_at,
                        "read_at": (
                            published_at + timedelta(hours=1)
                            if (announcement_index + student_index) % 4
                            else None
                        ),
                    }
                )
        return announcements, notifications

    def _build_assignments(
        self,
    ) -> tuple[list[Row], list[Row], list[Row], list[Row]]:
        assignments: list[Row] = []
        audience_rows: list[Row] = []
        submissions: list[Row] = []
        versions: list[Row] = []
        version_index = 0
        for assignment_index in range(CAPACITY_ASSIGNMENT_COUNT):
            assignment_id = _capacity_uuid("assignment", assignment_index)
            publish_at = _PUBLISHED_BASE + timedelta(days=assignment_index)
            archived = assignment_index >= 30
            deadline = publish_at + timedelta(days=60) if archived else _FUTURE_END
            assignments.append(
                {
                    "id": assignment_id,
                    "title": f"容量作业 {assignment_index + 1:02d}",
                    "description_markdown": "虚构容量作业说明。",
                    "description_html": "<p>虚构容量作业说明。</p>",
                    "training_url": "https://example.invalid/capacity-training",
                    "submission_instructions": "提交虚构文本，不上传真实文件。",
                    "status": "archived" if archived else "published",
                    "all_students": True,
                    "audience_match": "intersection",
                    "allowed_extensions": ["txt", "pdf", "zip"],
                    "max_total_bytes": 2_147_483_648,
                    "publish_at": publish_at,
                    "published_at": publish_at,
                    "deadline": deadline,
                    "created_by": self._admin_ids[assignment_index % CAPACITY_ADMIN_COUNT],
                    "updated_by": self._admin_ids[assignment_index % CAPACITY_ADMIN_COUNT],
                    "closed_at": deadline if archived else None,
                    "archived_at": deadline + timedelta(days=1) if archived else None,
                    **_mixin_fields(publish_at),
                }
            )
            for student_index, student_id in enumerate(self._student_ids):
                audience_rows.append(
                    {
                        "assignment_id": assignment_id,
                        "user_id": student_id,
                        "cohort_id_at_publish": self._cohort_ids[
                            student_index % len(self._cohort_ids)
                        ],
                        "direction_id_at_publish": self._direction_ids[
                            student_index % len(self._direction_ids)
                        ],
                        "created_at": publish_at,
                    }
                )
                submission_index = assignment_index * CAPACITY_STUDENT_COUNT + student_index
                submission_id = _capacity_uuid("assignment-submission", submission_index)
                version_count = (assignment_index + student_index) % 3 + 1
                version_ids = [
                    _capacity_uuid("assignment-version", version_index + offset)
                    for offset in range(version_count)
                ]
                first_submitted_at = publish_at + timedelta(days=2)
                latest_submitted_at = first_submitted_at + timedelta(hours=version_count - 1)
                submissions.append(
                    {
                        "id": submission_id,
                        "assignment_id": assignment_id,
                        "competition_task_id": None,
                        "owner_user_id": student_id,
                        "owner_team_id": None,
                        "latest_version_id": version_ids[-1],
                        "created_at": first_submitted_at,
                        "updated_at": latest_submitted_at,
                    }
                )
                for offset, version_id in enumerate(version_ids):
                    number = offset + 1
                    submitted_at = first_submitted_at + timedelta(hours=offset)
                    versions.append(
                        {
                            "id": version_id,
                            "submission_id": submission_id,
                            "version_number": number,
                            "submitted_by": student_id,
                            "text_markdown": (
                                f"虚构容量作业 {assignment_index + 1:02d} "
                                f"学生 {student_index + 1:03d} 版本 {number}。"
                            ),
                            "text_html": (
                                f"<p>虚构容量作业 {assignment_index + 1:02d} "
                                f"学生 {student_index + 1:03d} 版本 {number}。</p>"
                            ),
                            "external_url": None,
                            "total_file_bytes": 0,
                            "idempotency_key": (
                                f"capacity-assignment-{assignment_index:02d}-v{number}"
                            ),
                            "submitted_at": submitted_at,
                        }
                    )
                version_index += version_count
        return assignments, audience_rows, submissions, versions

    def _build_competitions(
        self,
    ) -> tuple[
        list[Row],
        list[Row],
        list[Row],
        list[Row],
        list[Row],
        list[Row],
        list[Row],
    ]:
        competitions: list[Row] = []
        tasks: list[Row] = []
        registrations: list[Row] = []
        teams: list[Row] = []
        members: list[Row] = []
        submissions: list[Row] = []
        versions: list[Row] = []
        competition_version_index = 0
        for competition_index in range(CAPACITY_COMPETITION_COUNT):
            competition_id = _capacity_uuid("competition", competition_index)
            task_id = _capacity_uuid("competition-task", competition_index)
            if competition_index < 6:
                status = "archived"
                registration_start = datetime(2024, 1, 1, tzinfo=UTC)
                registration_end = datetime(2024, 2, 1, tzinfo=UTC)
                submission_start = datetime(2024, 2, 2, tzinfo=UTC)
                submission_end = datetime(2024, 6, 1, tzinfo=UTC)
                archived_at = datetime(2024, 7, 1, tzinfo=UTC)
            elif competition_index < 9:
                status = "submission_open"
                registration_start = datetime(2025, 1, 1, tzinfo=UTC)
                registration_end = datetime(2025, 12, 1, tzinfo=UTC)
                submission_start = datetime(2026, 1, 1, tzinfo=UTC)
                submission_end = _FUTURE_END
                archived_at = None
            else:
                status = "registration_open"
                registration_start = datetime(2025, 1, 1, tzinfo=UTC)
                registration_end = datetime(2029, 1, 1, tzinfo=UTC)
                submission_start = datetime(2029, 1, 2, tzinfo=UTC)
                submission_end = _FUTURE_END
                archived_at = None
            published_at = registration_start - timedelta(days=1)
            competitions.append(
                {
                    "id": competition_id,
                    "name": f"容量赛事 {competition_index + 1:02d}",
                    "description_markdown": "虚构容量赛事说明。",
                    "description_html": "<p>虚构容量赛事说明。</p>",
                    "rules_url": "https://example.invalid/capacity-rules",
                    "status": status,
                    "registration_start": registration_start,
                    "registration_end": registration_end,
                    "submission_start": submission_start,
                    "submission_end": submission_end,
                    "min_team_size": 3,
                    "max_team_size": 5,
                    "created_by": self._admin_ids[competition_index % CAPACITY_ADMIN_COUNT],
                    "updated_by": self._admin_ids[competition_index % CAPACITY_ADMIN_COUNT],
                    "published_at": published_at,
                    "archived_at": archived_at,
                    **_mixin_fields(published_at),
                }
            )
            tasks.append(
                {
                    "id": task_id,
                    "competition_id": competition_id,
                    "title": f"容量赛题 {competition_index + 1:02d}",
                    "description_markdown": "虚构容量赛题说明。",
                    "description_html": "<p>虚构容量赛题说明。</p>",
                    "resource_url": "https://example.invalid/capacity-task",
                    "allowed_extensions": ["txt", "pdf", "zip"],
                    "max_total_bytes": 2_147_483_648,
                    "deadline": submission_end - timedelta(days=1),
                    "display_order": 0,
                    **_mixin_fields(published_at),
                }
            )
            for local_team_index in range(10):
                global_team_index = competition_index * 10 + local_team_index
                team_id = _capacity_uuid("team", global_team_index)
                student_indexes = [
                    (competition_index * 30 + local_team_index * 3 + offset)
                    % CAPACITY_STUDENT_COUNT
                    for offset in range(3)
                ]
                captain_id = self._student_ids[student_indexes[0]]
                forming = status == "registration_open"
                team_status = "forming" if forming else status.replace("submission_open", "locked")
                locked_at = None if forming else registration_end
                teams.append(
                    {
                        "id": team_id,
                        "competition_id": competition_id,
                        "name": f"容量队伍 {global_team_index + 1:03d}",
                        "status": team_status,
                        "captain_user_id": captain_id,
                        "invite_code_hash": hashlib.sha256(
                            f"capacity-team-{global_team_index}".encode()
                        ).hexdigest(),
                        "invite_code_rotated_at": registration_start,
                        "min_size_waived_at": None,
                        "min_size_waived_by": None,
                        "waiver_reason": None,
                        "disqualified_at": None,
                        "disqualified_by": None,
                        "disqualification_reason": None,
                        "locked_at": locked_at,
                        "dissolved_at": None,
                        **_mixin_fields(registration_start),
                    }
                )
                for member_offset, student_index in enumerate(student_indexes):
                    student_id = self._student_ids[student_index]
                    registrations.append(
                        {
                            "id": _capacity_uuid(
                                "competition-registration",
                                global_team_index * 3 + member_offset,
                            ),
                            "competition_id": competition_id,
                            "user_id": student_id,
                            "status": "registered",
                            "registered_at": registration_start,
                            "withdrawn_at": None,
                            "disqualified_at": None,
                            "disqualified_by": None,
                            "disqualification_reason": None,
                            **_mixin_fields(registration_start),
                        }
                    )
                    members.append(
                        {
                            "id": _capacity_uuid(
                                "team-member", global_team_index * 3 + member_offset
                            ),
                            "team_id": team_id,
                            "competition_id": competition_id,
                            "user_id": student_id,
                            "joined_at": registration_start,
                            "left_at": None,
                            "added_by_admin": False,
                            "admin_reason": None,
                        }
                    )
                if forming:
                    continue
                submission_id = _capacity_uuid("competition-submission", global_team_index)
                version_count = global_team_index % 3 + 1
                version_ids = [
                    _capacity_uuid("competition-version", competition_version_index + offset)
                    for offset in range(version_count)
                ]
                first_submitted_at = submission_start + timedelta(days=2)
                submissions.append(
                    {
                        "id": submission_id,
                        "assignment_id": None,
                        "competition_task_id": task_id,
                        "owner_user_id": None,
                        "owner_team_id": team_id,
                        "latest_version_id": version_ids[-1],
                        "created_at": first_submitted_at,
                        "updated_at": first_submitted_at + timedelta(hours=version_count - 1),
                    }
                )
                for offset, version_id in enumerate(version_ids):
                    number = offset + 1
                    versions.append(
                        {
                            "id": version_id,
                            "submission_id": submission_id,
                            "version_number": number,
                            "submitted_by": captain_id,
                            "text_markdown": (
                                f"虚构容量赛事 {competition_index + 1:02d} "
                                f"队伍 {global_team_index + 1:03d} 版本 {number}。"
                            ),
                            "text_html": (
                                f"<p>虚构容量赛事 {competition_index + 1:02d} "
                                f"队伍 {global_team_index + 1:03d} 版本 {number}。</p>"
                            ),
                            "external_url": None,
                            "total_file_bytes": 0,
                            "idempotency_key": (
                                f"capacity-competition-{competition_index:02d}-"
                                f"team-{local_team_index:02d}-v{number}"
                            ),
                            "submitted_at": first_submitted_at + timedelta(hours=offset),
                        }
                    )
                competition_version_index += version_count
        return (
            competitions,
            tasks,
            registrations,
            teams,
            members,
            submissions,
            versions,
        )

    def _build_marker(self, summary: dict[str, int]) -> Row:
        return {
            "id": _capacity_uuid("audit-marker", 0),
            "actor_user_id": None,
            "action": "test_data.seed_capacity",
            "target_type": "capacity_dataset",
            "target_id": self._admin_ids[0],
            "request_id": CAPACITY_MARKER_REQUEST_ID,
            "ip_prefix": "local",
            "result": "success",
            "change_summary": {"synthetic": True, **summary},
            "created_at": _PUBLISHED_BASE,
        }


class CapacityDatasetSeeder:
    def __init__(
        self,
        repository: CapacitySeedRepositoryProtocol,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    async def seed(self, *, password: str) -> dict[str, int | bool]:
        if self._settings.app_env == "production":
            raise SyntheticSeedError("SYNTHETIC_SEED_FORBIDDEN_IN_PRODUCTION")
        if await self._repository.has_capacity_dataset():
            return {"created": False, **self.expected_summary()}
        validate_password(
            password,
            email=capacity_student_email(0),
            student_number="CAP-STU-001",
        )
        password_hash = get_password_manager().hash(password)
        dataset = CapacityDatasetBuilder(password_hash=password_hash).build()
        await self._repository.store_capacity_dataset(dataset)
        await self._repository.commit()
        return {"created": True, **_summary(dataset)}

    @staticmethod
    def expected_summary() -> dict[str, int]:
        assignment_versions = CAPACITY_ASSIGNMENT_COUNT * CAPACITY_STUDENT_COUNT * 2
        competition_versions = 90 * 2
        return {
            "dataset_version": CAPACITY_DATASET_VERSION,
            "cohorts": CAPACITY_COHORT_COUNT,
            "directions": CAPACITY_DIRECTION_COUNT,
            "students": CAPACITY_STUDENT_COUNT,
            "admins": CAPACITY_ADMIN_COUNT,
            "announcements": CAPACITY_ANNOUNCEMENT_COUNT,
            "student_notifications": (CAPACITY_ANNOUNCEMENT_COUNT * CAPACITY_STUDENT_COUNT),
            "assignments": CAPACITY_ASSIGNMENT_COUNT,
            "assignment_audience_users": (CAPACITY_ASSIGNMENT_COUNT * CAPACITY_STUDENT_COUNT),
            "competitions": CAPACITY_COMPETITION_COUNT,
            "competition_tasks": CAPACITY_COMPETITION_COUNT,
            "competition_registrations": CAPACITY_TEAM_COUNT * 3,
            "teams": CAPACITY_TEAM_COUNT,
            "team_members": CAPACITY_TEAM_COUNT * 3,
            "submissions": (CAPACITY_ASSIGNMENT_COUNT * CAPACITY_STUDENT_COUNT + 90),
            "submission_versions": assignment_versions + competition_versions,
        }
