from __future__ import annotations

import json
import os
import runpy
import socket
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.ops.kis_paper_intraday_head_schedule_receipt import (
    KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY,
    KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME,
    read_kis_paper_intraday_head_collection_recovery_from_artifact_root,
    write_kis_paper_intraday_head_schedule_receipt,
)

_CAPTURE_OBSERVED_AT = datetime(2026, 7, 28, 15, 30, tzinfo=UTC)
_TERMINAL_OBSERVED_AT = datetime(2026, 7, 28, 15, 31, tzinfo=UTC)
_RUN_ID = "intraday-head-unit"
_SECRET_SENTINEL = "fixture-secret-must-not-leak"
_RAW_SENTINEL = "fixture-raw-minute-bar-must-not-leak"
_SCRIPT_PATH = (
    Path(__file__).parents[1] / "scripts" / "project_kis_paper_intraday_head_schedule_receipt.py"
)


@dataclass(frozen=True)
class _CaptureReceipt:
    encoded: bytes
    path: Path
    receipt_sha256: str
    coverage_digest: str


def test_collection_recovery_projects_bound_duplicate_conflict_without_sensitive_fields(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(cache_root=capture_cache_root)
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
    )

    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=capture_cache_root,
    )

    payload = result.safe_payload()
    assert payload["kind"] == "kis_paper_intraday_head_collection_recovery_fact"
    assert payload["status"] == "rejected_duplicate_conflict"
    assert payload["capture_binding_status"] == "verified"
    assert payload["targets"] == [
        {
            "target_key": "QQQ/NAS/1m",
            "status": "rejected",
            "reason": "minute_duplicate_conflict",
        },
        {
            "target_key": "SPY/AMS/1m",
            "status": "rejected",
            "reason": "minute_duplicate_conflict",
        },
    ]
    assert set(payload) == {
        "schema_version",
        "kind",
        "status",
        "capture_binding_status",
        "targets",
    }

    rendered = json.dumps(payload, ensure_ascii=True, sort_keys=True).lower()
    for forbidden in (
        "path",
        "raw",
        "secret",
        "credential",
        "row_count",
        "exact_overlap_rows",
        _SECRET_SENTINEL,
        _RAW_SENTINEL,
        str(capture.path).lower(),
        str(artifact_root).lower(),
    ):
        assert forbidden.lower() not in rendered


@pytest.mark.parametrize(
    "binding_mutation",
    ("receipt_sha256", "schedule_run_id", "observed_at", "coverage_digest"),
)
def test_collection_recovery_returns_evidence_unavailable_for_bound_capture_mismatches(
    tmp_path: Path,
    binding_mutation: str,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(cache_root=capture_cache_root)
    binding_overrides: dict[str, object] = {}

    if binding_mutation == "receipt_sha256":
        wrong_sha256 = "sha256:" + "f" * 64
        _write_capture_bytes(
            cache_root=capture_cache_root,
            observed_at=_CAPTURE_OBSERVED_AT,
            receipt_sha256=wrong_sha256,
            encoded=capture.encoded,
        )
        binding_overrides["session_capture_receipt_sha256"] = wrong_sha256
    elif binding_mutation == "schedule_run_id":
        pass
    elif binding_mutation == "observed_at":
        wrong_observed_at = _CAPTURE_OBSERVED_AT - timedelta(minutes=1)
        _write_capture_bytes(
            cache_root=capture_cache_root,
            observed_at=wrong_observed_at,
            receipt_sha256=capture.receipt_sha256,
            encoded=capture.encoded,
        )
        binding_overrides["session_capture_observed_at"] = wrong_observed_at
    else:
        binding_overrides["session_capture_coverage_digest"] = "sha256:" + "e" * 64

    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
        binding_overrides=binding_overrides,
    )
    if binding_mutation == "schedule_run_id":
        _rewrite_terminal_binding_field(
            artifact_root=artifact_root,
            field="schedule_run_id",
            value="intraday-head-other",
        )

    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=capture_cache_root,
    )

    assert result.safe_payload() == {
        "schema_version": result.schema_version,
        "kind": "kis_paper_intraday_head_collection_recovery_fact",
        "status": "evidence_unavailable",
        "capture_binding_status": "evidence_unavailable",
        "targets": [],
    }


def test_collection_recovery_returns_evidence_unavailable_without_its_exact_capture(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(cache_root=capture_cache_root)
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
    )
    capture.path.unlink()
    _write_capture_bytes(
        cache_root=capture_cache_root,
        observed_at=_CAPTURE_OBSERVED_AT + timedelta(minutes=1),
        receipt_sha256=capture.receipt_sha256,
        encoded=capture.encoded,
    )

    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=capture_cache_root,
    )

    _assert_evidence_unavailable(result.safe_payload(), schema_version=result.schema_version)


def test_collection_recovery_returns_evidence_unavailable_for_malformed_capture(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(cache_root=capture_cache_root)
    malformed = b"not-json\n"
    malformed_sha256 = "sha256:" + sha256(malformed).hexdigest()
    _write_capture_bytes(
        cache_root=capture_cache_root,
        observed_at=_CAPTURE_OBSERVED_AT,
        receipt_sha256=malformed_sha256,
        encoded=malformed,
    )
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
        binding_overrides={"session_capture_receipt_sha256": malformed_sha256},
    )

    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=capture_cache_root,
    )

    _assert_evidence_unavailable(result.safe_payload(), schema_version=result.schema_version)


def test_collection_recovery_returns_evidence_unavailable_for_unsafe_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(cache_root=capture_cache_root)
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
    )
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        metadata = original_lstat(path)
        if path == capture.path:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(Path, "lstat", marked_lstat)

    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=capture_cache_root,
    )

    _assert_evidence_unavailable(result.safe_payload(), schema_version=result.schema_version)


def test_collection_recovery_preserves_another_valid_target_category(tmp_path: Path) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(
        cache_root=capture_cache_root,
        target_status="source_exhausted",
        target_reason=None,
    )
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
    )

    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=capture_cache_root,
    )

    assert result.safe_payload()["status"] == "source_exhausted"
    assert result.safe_payload()["targets"] == [
        {"target_key": "QQQ/NAS/1m", "status": "source_exhausted", "reason": None},
        {"target_key": "SPY/AMS/1m", "status": "source_exhausted", "reason": None},
    ]


def test_collection_recovery_returns_evidence_unavailable_outside_collection_exit_terminal(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(cache_root=capture_cache_root)
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
        collection_exit_code=0,
    )

    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=capture_cache_root,
    )

    _assert_evidence_unavailable(result.safe_payload(), schema_version=result.schema_version)


def test_collection_recovery_cli_projects_a_bound_recovery(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(cache_root=capture_cache_root)
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
    )
    script = runpy.run_path(str(_SCRIPT_PATH))

    assert (
        script["main"](
            [
                "--collection-recovery",
                "--artifact-root",
                str(artifact_root),
                "--capture-cache-root",
                str(capture_cache_root),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "rejected_duplicate_conflict"
    assert payload["capture_binding_status"] == "verified"


def test_collection_recovery_cli_prints_a_source_safe_unavailable_fact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    script = runpy.run_path(str(_SCRIPT_PATH))

    assert (
        script["main"](
            [
                "--collection-recovery",
                "--artifact-root",
                str(artifact_root),
                "--capture-cache-root",
                str(tmp_path / "market-data" / "intraday-head"),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    _assert_evidence_unavailable(payload, schema_version=payload["schema_version"])


def test_collection_recovery_projection_never_uses_network_or_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(cache_root=capture_cache_root)
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
    )
    (repository_root / ".env").write_text("TEST_ONLY_SECRET=do-not-read\n", encoding="ascii")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("collection recovery projection must stay offline")

    original_open = Path.open
    original_read_text = Path.read_text

    def guard_open(path: Path, *args: object, **kwargs: object):
        if path.name.startswith(".env"):
            raise AssertionError("collection recovery projection must not read .env")
        return original_open(path, *args, **kwargs)

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("collection recovery projection must not read .env")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(Path, "open", guard_open)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=capture_cache_root,
    )

    assert result.safe_payload()["status"] == "rejected_duplicate_conflict"


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    return (
        repository_root,
        tmp_path / "model-artifacts",
        tmp_path / "market-data" / "intraday-head",
    )


def _write_capture_receipt(
    *,
    cache_root: Path,
    target_status: str = "rejected",
    target_reason: str | None = "minute_duplicate_conflict",
) -> _CaptureReceipt:
    coverage = {
        "complete_regular_session_dates": [],
        "last_reason_category": "minute_duplicate_conflict",
        "regular_session_coverage": [
            {"session_date": "2026-07-28", "status": "short"},
        ],
    }
    coverage_digest = _sha256_json(coverage)
    payload = {
        "kind": "kis_paper_intraday_session_capture",
        "schedule_run_id": _RUN_ID,
        "observed_at": "2026-07-28T15:30:00Z",
        "current_session_cumulative_coverage_digest": coverage_digest,
        "current_session_cumulative_coverage_category": "incomplete",
        "current_session_cumulative_coverage": coverage,
        "targets": [
            {
                "target_key": "QQQ/NAS/1m",
                "status": target_status,
                "row_count": 0,
                "exact_overlap_rows": 0,
                "reason": target_reason,
            },
            {
                "target_key": "SPY/AMS/1m",
                "status": target_status,
                "row_count": 0,
                "exact_overlap_rows": 0,
                "reason": target_reason,
            },
        ],
        "fixture_raw_rows": [_RAW_SENTINEL],
        "fixture_secret": _SECRET_SENTINEL,
        "fixture_path": "D:/market_data/never-project-this.json",
    }
    encoded = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")
    receipt_sha256 = "sha256:" + sha256(encoded).hexdigest()
    path = _write_capture_bytes(
        cache_root=cache_root,
        observed_at=_CAPTURE_OBSERVED_AT,
        receipt_sha256=receipt_sha256,
        encoded=encoded,
    )
    return _CaptureReceipt(
        encoded=encoded,
        path=path,
        receipt_sha256=receipt_sha256,
        coverage_digest=coverage_digest,
    )


def _write_capture_bytes(
    *,
    cache_root: Path,
    observed_at: datetime,
    receipt_sha256: str,
    encoded: bytes,
) -> Path:
    path = (
        cache_root
        / "v1"
        / "session-capture"
        / f"{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{receipt_sha256[7:23]}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return path


def _write_bound_recovery_terminal(
    *,
    artifact_root: Path,
    repository_root: Path,
    capture: _CaptureReceipt,
    binding_overrides: dict[str, object] | None = None,
    collection_exit_code: int = 1,
) -> None:
    binding: dict[str, object] = {
        "session_capture_run_id": _RUN_ID,
        "session_capture_observed_at": _CAPTURE_OBSERVED_AT,
        "session_capture_receipt_sha256": capture.receipt_sha256,
        "session_capture_coverage_digest": capture.coverage_digest,
        "session_capture_coverage_category": "incomplete",
    }
    if binding_overrides is not None:
        binding.update(binding_overrides)
    write_kis_paper_intraday_head_schedule_receipt(
        run_id=_RUN_ID,
        collection_exit_code=collection_exit_code,
        prospective_spy_cycle_exit_code=0,
        prospective_spy_cycle_status="not_applicable",
        prospective_spy_cycle_id=None,
        prospective_spy_canary_run_id=None,
        prospective_loop_exit_code=0,
        prospective_loop_status="not_applicable",
        prospective_session_exit_code=0,
        prospective_session_status="not_applicable",
        prospective_session_id=None,
        prospective_validation_exit_code=0,
        prospective_validation_status="not_applicable",
        prospective_validation_session_id=None,
        prospective_validation_contract=None,
        observation_exit_code=0,
        observation_status="not_applicable",
        capture_cycle_exit_code=0,
        capture_cycle_status="not_applicable",
        require_session_capture_binding=True,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=_TERMINAL_OBSERVED_AT,
        **binding,
    )


def _rewrite_terminal_binding_field(*, artifact_root: Path, field: str, value: object) -> None:
    schedule_root = artifact_root / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY
    runtime_path = schedule_root / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    terminal_path = schedule_root / f"{_RUN_ID}.json"
    terminal = json.loads(terminal_path.read_text(encoding="ascii"))
    terminal["terminal_receipt_binding"][field] = value
    terminal_bytes = _canonical_json_bytes(terminal)
    terminal_path.write_bytes(terminal_bytes)

    runtime = json.loads(runtime_path.read_text(encoding="ascii"))
    runtime["receipt_sha256"] = "sha256:" + sha256(terminal_bytes).hexdigest()
    runtime_path.write_bytes(_canonical_json_bytes(runtime))


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return "sha256:" + sha256(encoded).hexdigest()


def _assert_evidence_unavailable(payload: dict[str, object], *, schema_version: int) -> None:
    assert payload == {
        "schema_version": schema_version,
        "kind": "kis_paper_intraday_head_collection_recovery_fact",
        "status": "evidence_unavailable",
        "capture_binding_status": "evidence_unavailable",
        "targets": [],
    }


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")
