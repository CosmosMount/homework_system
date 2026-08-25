import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE_DIRECTORY = ROOT / "infra/performance"


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(PERFORMANCE_DIRECTORY))
    try:
        spec = importlib.util.spec_from_file_location(name, PERFORMANCE_DIRECTORY / f"{name}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PERFORMANCE_DIRECTORY))


common = _load("_common")
read_load = _load("read_load")
multipart_load = _load("multipart_load")


def test_password_file_must_be_absolute_private_and_single_line(tmp_path: Path) -> None:
    password_file = tmp_path / "password"
    password_file.write_text("synthetic-secret\n", encoding="utf-8")
    password_file.chmod(0o600)

    assert common.read_password_file(str(password_file)) == "synthetic-secret"
    with pytest.raises(common.ConfigurationError, match="PASSWORD_FILE_MUST_BE_ABSOLUTE"):
        common.read_password_file("password")

    password_file.chmod(0o640)
    with pytest.raises(common.ConfigurationError, match="PASSWORD_FILE_PERMISSIONS_TOO_OPEN"):
        common.read_password_file(str(password_file))


def test_percentiles_and_metric_summary_are_deterministic() -> None:
    metrics = [
        common.RequestMetric("dashboard", 10.0, True),
        common.RequestMetric("dashboard", 20.0, True),
        common.RequestMetric("dashboard", 30.0, False, "http_503"),
    ]

    assert common.percentile([10.0, 20.0, 30.0], 0.5) == 20.0
    assert common.percentile([10.0, 20.0], 0.95) == pytest.approx(19.5)
    assert common.summarize_metrics(metrics, 1.5) == {
        "total": 3,
        "successful": 2,
        "errors": 1,
        "error_rate": 0.333333,
        "throughput_rps": 2.0,
        "latency_ms": {"p50": 20.0, "p95": 29.0, "p99": 29.8, "max": 30.0},
        "error_codes": {"http_503": 1},
    }


def test_pattern_stream_is_offset_aware_and_digest_plan_matches_bytes() -> None:
    source = multipart_load.PatternSource("test-seed", 17)
    expected = b"".join(source.iter_range(0, 113))
    reconstructed = b"".join(source.iter_range(0, 31)) + b"".join(source.iter_range(31, 82))

    assert reconstructed == expected
    plan = multipart_load.build_digest_plan(source, size_bytes=113, part_size_bytes=31)
    assert plan.full_sha256 == hashlib.sha256(expected).hexdigest()
    assert len(plan.part_checksums_base64) == 4


def test_performance_cli_defaults_match_stage_six_capacity_targets() -> None:
    read_args = read_load.build_parser().parse_args(
        ["--base-url", "http://127.0.0.1:5000", "--password-file", "/tmp/password"]
    )
    upload_args = multipart_load.build_parser().parse_args(
        ["--base-url", "http://127.0.0.1:5000", "--password-file", "/tmp/password"]
    )

    assert read_args.sessions == 100
    assert read_args.rounds == 5
    assert upload_args.uploads == 20
    assert upload_args.expected_part_size_bytes == 16_777_216
    assert upload_args.stream_block_size_bytes == 1_048_576


def test_performance_tools_never_accept_inline_passwords() -> None:
    for script in ("read_load.py", "multipart_load.py"):
        source = (PERFORMANCE_DIRECTORY / script).read_text(encoding="utf-8")
        assert '"--password"' not in source
        assert "response.text" not in source
