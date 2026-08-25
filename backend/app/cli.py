import argparse
import asyncio
import getpass
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.audit.models import AuditLog
from app.core.config import get_settings
from app.core.identifiers import uuid7
from app.core.security import (
    PasswordPolicyViolation,
    get_password_manager,
    is_campus_email,
    normalize_email,
    validate_password,
)
from app.database.session import engine, session_factory
from app.operations.capacity_repository import CapacitySeedRepository
from app.operations.capacity_seed import CapacityDatasetSeeder
from app.operations.repository import OperationsRepository
from app.operations.service import OperationsSnapshotService
from app.operations.synthetic_repository import SyntheticSeedRepository
from app.operations.synthetic_seed import (
    SyntheticSeedError,
    SyntheticUserSeeder,
    read_password_file,
)
from app.uploads.object_store import MinioObjectStore, ObjectStoreError
from app.uploads.operations import (
    StorageOperationError,
    StorageReconciler,
    StorageTransfer,
)
from app.uploads.repository import UploadRepository
from app.users.models import User
from app.users.repository import UserRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PNX Training Hub 管理命令")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "create-admin",
        help="交互式创建已验证管理员；密码不会进入命令行参数。",
    )
    subcommands.add_parser(
        "reconcile-storage",
        help="只读核对数据库文件记录与对象存储；不会删除或修改对象。",
    )
    subcommands.add_parser(
        "operations-snapshot",
        help="输出不含个人信息的 Outbox 与上传运维计数。",
    )
    seed_parser = subcommands.add_parser(
        "seed-e2e-users",
        help="仅在非生产环境创建固定虚构学生和管理员账号。",
    )
    seed_parser.add_argument("--password-file", type=Path, required=True)
    seed_parser.add_argument(
        "--confirm-synthetic-data",
        action="store_true",
        required=True,
    )
    capacity_parser = subcommands.add_parser(
        "seed-capacity-data",
        help="仅在非生产环境创建固定规模的虚构容量数据。",
    )
    capacity_parser.add_argument("--password-file", type=Path, required=True)
    capacity_parser.add_argument(
        "--confirm-synthetic-data",
        action="store_true",
        required=True,
    )
    export_parser = subcommands.add_parser(
        "export-objects",
        help="把对象存储流式导出到全新目录并生成完整或增量校验清单。",
    )
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--backup-id")
    export_parser.add_argument("--base-manifest", type=Path)
    import_parser = subcommands.add_parser(
        "import-objects",
        help="从完整导出恢复空桶，或显式应用经过校验的增量。",
    )
    import_parser.add_argument("--input", type=Path, required=True)
    import_parser.add_argument("--base-manifest", type=Path)
    import_mode = import_parser.add_mutually_exclusive_group(required=True)
    import_mode.add_argument(
        "--require-empty-bucket",
        action="store_true",
        help="显式确认目标桶必须为空；该命令不会覆盖已有对象。",
    )
    import_mode.add_argument(
        "--apply-incremental",
        action="store_true",
        help="显式确认目标桶已恢复为指定每周基线并应用每日增量。",
    )
    return parser


async def _create_admin(
    *,
    email_input: str,
    full_name_input: str,
    student_number_input: str,
    password: str,
    confirmation: str,
) -> int:
    settings = get_settings()
    email = normalize_email(email_input)
    full_name = full_name_input.strip()
    student_number = student_number_input.strip()

    if password != confirmation:
        print("两次输入的密码不一致。")
        return 2
    if not full_name or not student_number:
        print("姓名和学号/管理员编号不能为空。")
        return 2
    if not is_campus_email(email, domain=settings.campus_email_domain):
        print("必须使用 @connect.hkust-gz.edu.cn 学校邮箱。")
        return 2
    try:
        validate_password(password, email=email, student_number=student_number)
    except PasswordPolicyViolation as exc:
        print(f"密码不符合安全要求：{exc.reason}")
        return 2

    now = datetime.now(UTC)
    user = User(
        id=uuid7(),
        email=email,
        email_normalized=email,
        student_number=student_number,
        full_name=full_name,
        password_hash=get_password_manager().hash(password),
        role="admin",
        status="active",
        cohort_id=None,
        direction_id=None,
        email_verified_at=now,
        disabled_at=None,
        disabled_by=None,
        disabled_reason=None,
        password_changed_at=now,
    )
    try:
        async with session_factory() as session:
            repository = UserRepository(session)
            repository.add(user)
            session.add(
                AuditLog(
                    id=uuid7(),
                    actor_user_id=None,
                    action="admin.create_cli",
                    target_type="user",
                    target_id=user.id,
                    request_id=str(uuid4()),
                    ip_prefix="local",
                    result="success",
                    change_summary={"role": "admin"},
                    created_at=now,
                )
            )
            await session.commit()
    except IntegrityError as exc:
        constraint_name = getattr(getattr(exc, "orig", None), "constraint_name", "")
        if constraint_name == "uq_users_email_normalized":
            print("该邮箱已存在。")
        elif constraint_name == "uq_users_student_number":
            print("该学号/管理员编号已存在。")
        else:
            print("创建管理员失败：数据约束冲突。")
        return 3
    print(f"管理员已创建：{email}")
    return 0


async def _run_create_admin(
    *,
    email: str,
    full_name: str,
    student_number: str,
    password: str,
    confirmation: str,
) -> int:
    try:
        return await _create_admin(
            email_input=email,
            full_name_input=full_name,
            student_number_input=student_number,
            password=password,
            confirmation=confirmation,
        )
    finally:
        await engine.dispose()


def _write_json(payload: dict[str, object], *, error: bool = False) -> None:
    target = sys.stderr if error else sys.stdout
    print(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        file=target,
    )


async def _run_reconciliation() -> int:
    settings = get_settings()
    try:
        async with session_factory() as session:
            repository = UploadRepository(session)
            report = await StorageReconciler(
                repository,
                MinioObjectStore(settings),
            ).run()
        _write_json(report.to_dict())
        return 0 if report.ok else 4
    except (ObjectStoreError, SQLAlchemyError, OSError, ValueError):
        _write_json(
            {"status": "error", "code": "STORAGE_RECONCILIATION_FAILED"},
            error=True,
        )
        return 5
    finally:
        await engine.dispose()


async def _run_operations_snapshot() -> int:
    settings = get_settings()
    try:
        async with session_factory() as session:
            report = await OperationsSnapshotService(
                OperationsRepository(session),
                orphan_cleanup_delay_seconds=settings.upload_session_ttl_seconds,
            ).snapshot()
        _write_json(report)
        return 0
    except (SQLAlchemyError, OSError, ValueError):
        _write_json(
            {"status": "error", "code": "OPERATIONS_SNAPSHOT_FAILED"},
            error=True,
        )
        return 5
    finally:
        await engine.dispose()


async def _run_seed_e2e_users(password_file: Path) -> int:
    try:
        password = read_password_file(password_file)
        settings = get_settings()
        async with session_factory() as session:
            summary = await SyntheticUserSeeder(
                SyntheticSeedRepository(session),
                settings,
            ).seed(password=password)
        _write_json({"status": "ok", **summary})
        return 0
    except SyntheticSeedError as exc:
        _write_json({"status": "error", "code": exc.code}, error=True)
        return 5
    except PasswordPolicyViolation:
        _write_json(
            {"status": "error", "code": "SYNTHETIC_PASSWORD_POLICY_FAILED"},
            error=True,
        )
        return 5
    except (SQLAlchemyError, OSError, ValueError):
        _write_json({"status": "error", "code": "SYNTHETIC_SEED_FAILED"}, error=True)
        return 5
    finally:
        await engine.dispose()


async def _run_seed_capacity_data(password_file: Path) -> int:
    try:
        password = read_password_file(password_file)
        settings = get_settings()
        async with session_factory() as session:
            summary = await CapacityDatasetSeeder(
                CapacitySeedRepository(session),
                settings,
            ).seed(password=password)
        _write_json({"status": "ok", **summary})
        return 0
    except SyntheticSeedError as exc:
        _write_json({"status": "error", "code": exc.code}, error=True)
        return 5
    except PasswordPolicyViolation:
        _write_json(
            {"status": "error", "code": "SYNTHETIC_PASSWORD_POLICY_FAILED"},
            error=True,
        )
        return 5
    except (SQLAlchemyError, OSError, ValueError):
        _write_json(
            {"status": "error", "code": "SYNTHETIC_CAPACITY_SEED_FAILED"},
            error=True,
        )
        return 5
    finally:
        await engine.dispose()


async def _run_export(
    output: Path,
    *,
    backup_id: str | None,
    base_manifest: Path | None,
) -> int:
    if not output.is_absolute() or (base_manifest is not None and not base_manifest.is_absolute()):
        _write_json({"status": "error", "code": "ABSOLUTE_PATH_REQUIRED"}, error=True)
        return 2
    try:
        summary = await StorageTransfer(MinioObjectStore(get_settings())).export(
            output,
            backup_id=backup_id,
            base_manifest=base_manifest,
        )
        _write_json({"status": "ok", **summary})
        return 0
    except StorageOperationError as exc:
        _write_json({"status": "error", "code": exc.code}, error=True)
        return 5
    except (ObjectStoreError, OSError, ValueError):
        _write_json({"status": "error", "code": "OBJECT_EXPORT_FAILED"}, error=True)
        return 5
    finally:
        await engine.dispose()


async def _run_import(
    source: Path,
    *,
    apply_incremental: bool,
    base_manifest: Path | None,
) -> int:
    if not source.is_absolute() or (base_manifest is not None and not base_manifest.is_absolute()):
        _write_json({"status": "error", "code": "ABSOLUTE_PATH_REQUIRED"}, error=True)
        return 2
    if apply_incremental != (base_manifest is not None):
        _write_json({"status": "error", "code": "IMPORT_MODE_MISMATCH"}, error=True)
        return 2
    try:
        transfer = StorageTransfer(MinioObjectStore(get_settings()))
        if base_manifest is None:
            summary = await transfer.import_into_empty_bucket(source)
        else:
            summary = await transfer.apply_incremental(
                source,
                base_manifest=base_manifest,
            )
        _write_json({"status": "ok", **summary})
        return 0
    except StorageOperationError as exc:
        _write_json({"status": "error", "code": exc.code}, error=True)
        return 5
    except (ObjectStoreError, OSError, ValueError):
        _write_json({"status": "error", "code": "OBJECT_IMPORT_FAILED"}, error=True)
        return 5
    finally:
        await engine.dispose()


def main() -> int:
    arguments = _parser().parse_args()
    if arguments.command == "create-admin":
        email = input("学校邮箱: ")
        full_name = input("姓名: ")
        student_number = input("学号/管理员编号: ")
        password = getpass.getpass("密码（12～128 字符）: ")
        confirmation = getpass.getpass("再次输入密码: ")
        return asyncio.run(
            _run_create_admin(
                email=email,
                full_name=full_name,
                student_number=student_number,
                password=password,
                confirmation=confirmation,
            )
        )
    if arguments.command == "reconcile-storage":
        return asyncio.run(_run_reconciliation())
    if arguments.command == "operations-snapshot":
        return asyncio.run(_run_operations_snapshot())
    if arguments.command == "seed-e2e-users":
        if not arguments.confirm_synthetic_data:
            return 2
        return asyncio.run(_run_seed_e2e_users(arguments.password_file))
    if arguments.command == "seed-capacity-data":
        if not arguments.confirm_synthetic_data:
            return 2
        return asyncio.run(_run_seed_capacity_data(arguments.password_file))
    if arguments.command == "export-objects":
        return asyncio.run(
            _run_export(
                arguments.output,
                backup_id=arguments.backup_id,
                base_manifest=arguments.base_manifest,
            )
        )
    if arguments.command == "import-objects":
        return asyncio.run(
            _run_import(
                arguments.input,
                apply_incremental=arguments.apply_incremental,
                base_manifest=arguments.base_manifest,
            )
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
