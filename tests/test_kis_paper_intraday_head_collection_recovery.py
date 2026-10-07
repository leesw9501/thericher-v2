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
_DIAGNOSTIC_RUN_ID = "intraday-head-20260728T1530000000000Z"
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
            "conflict_origin": "not_recorded_legacy",
            "retained_head_conflict_disposition": "not_recorded_legacy",
        },
        {
            "target_key": "SPY/AMS/1m",
            "status": "rejected",
            "reason": "minute_duplicate_conflict",
            "conflict_origin": "not_recorded_legacy",
            "retained_head_conflict_disposition": "not_recorded_legacy",
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
    "diagnostic",
    [
        {
            "failure_phase": "head_contract",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": 4,
            "requested_pages_per_target": 4,
        },
        {},
        {"failure_phase": "head_contract"},
        {
            "failure_phase": "head_contract",
            "failure_code": _SECRET_SENTINEL,
            "failure_page_ordinal": 4,
            "requested_pages_per_target": 4,
        },
        {
            "failure_phase": "row_parse",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": 4,
            "requested_pages_per_target": 4,
        },
        {
            "failure_phase": "head_contract",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": True,
            "requested_pages_per_target": 4,
        },
        {
            "failure_phase": None,
            "failure_code": None,
            "failure_page_ordinal": None,
            "requested_pages_per_target": None,
        },
    ],
)
def test_collection_recovery_projects_only_valid_bound_optional_diagnostics(
    tmp_path: Path, diagnostic: dict[str, object]
) -> None:
    repository_root, artifact_root, cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(
        cache_root=cache_root,
        run_id=_DIAGNOSTIC_RUN_ID,
        target_status="partial",
        target_reason="minute_response_invalid",
        target_provenance={
            "conflict_origin": None,
            "retained_head_conflict_disposition": "not_applicable",
            **diagnostic,
        },
    )
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
        run_id=_DIAGNOSTIC_RUN_ID,
    )
    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root, repository_root=repository_root, capture_cache_root=cache_root
    )
    payload = result.safe_payload()
    valid = (
        not diagnostic
        or diagnostic.get("failure_phase") == "head_contract"
        and (
            diagnostic.get("failure_code") == "mixed_exchange_dates"
            and type(diagnostic.get("failure_page_ordinal")) is int
            and diagnostic["failure_page_ordinal"] == 4
            and diagnostic.get("requested_pages_per_target") == 4
        )
    )
    if valid:
        assert payload["capture_binding_status"] == "verified"
        for target in payload["targets"]:
            assert {
                k: v
                for k, v in target.items()
                if k.startswith("failure_") or k == "requested_pages_per_target"
            } == diagnostic
    else:
        assert payload["status"] == "evidence_unavailable" and payload["targets"] == []
    assert _SECRET_SENTINEL not in json.dumps(payload)


def test_collection_recovery_never_projects_mutated_diagnostic_bytes(tmp_path: Path) -> None:
    repository_root, artifact_root, cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(
        cache_root=cache_root,
        run_id=_DIAGNOSTIC_RUN_ID,
        target_status="partial",
        target_reason="minute_response_invalid",
        target_provenance={
            "conflict_origin": None,
            "retained_head_conflict_disposition": "not_applicable",
            "failure_phase": "head_contract",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": 4,
            "requested_pages_per_target": 4,
        },
    )
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
        run_id=_DIAGNOSTIC_RUN_ID,
    )
    capture.path.write_bytes(
        capture.encoded.replace(b'"failure_page_ordinal":4', b'"failure_page_ordinal":3')
    )
    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root, repository_root=repository_root, capture_cache_root=cache_root
    )
    assert result.safe_payload()["targets"] == []
    assert result.safe_payload()["capture_binding_status"] == "evidence_unavailable"


@pytest.mark.parametrize(
    ("budget", "ordinal"),
    [(4, 5), (8, 5), (2, 2), (999999, 5), (True, 1), (4.0, 4), (None, 4)],
)
def test_collection_recovery_rejects_hash_consistent_unbound_page_budget(
    tmp_path: Path, budget: object, ordinal: int
) -> None:
    repository_root, artifact_root, cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(
        cache_root=cache_root,
        run_id=_DIAGNOSTIC_RUN_ID,
        target_status="partial",
        target_reason="minute_response_invalid",
        target_provenance={
            "conflict_origin": None,
            "retained_head_conflict_disposition": "not_applicable",
            "failure_phase": "head_contract",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": ordinal,
            "requested_pages_per_target": budget,
        },
    )
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
        run_id=_DIAGNOSTIC_RUN_ID,
    )
    assert "sha256:" + sha256(capture.path.read_bytes()).hexdigest() == capture.receipt_sha256
    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root, repository_root=repository_root, capture_cache_root=cache_root
    )
    assert result.safe_payload()["status"] == "evidence_unavailable"
    assert result.safe_payload()["targets"] == []


@pytest.mark.parametrize(
    ("run_stamp", "budget"),
    [("20260728T2019599999999Z", 4), ("20260728T2020000000000Z", 8)],
)
def test_collection_recovery_verifies_actual_budget_at_frozen_invocation_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_stamp: str, budget: int
) -> None:
    monkeypatch.setitem(
        globals(), "_CAPTURE_OBSERVED_AT", datetime(2026, 7, 28, 20, 20, 1, tzinfo=UTC)
    )
    monkeypatch.setitem(
        globals(), "_TERMINAL_OBSERVED_AT", datetime(2026, 7, 28, 20, 21, tzinfo=UTC)
    )
    run_id = f"intraday-head-{run_stamp}"
    repository_root, artifact_root, cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(
        cache_root=cache_root,
        run_id=run_id,
        target_status="partial",
        target_reason="minute_response_invalid",
        target_provenance={
            "conflict_origin": None,
            "retained_head_conflict_disposition": "not_applicable",
            "failure_phase": "head_contract",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": budget,
            "requested_pages_per_target": budget,
        },
    )
    _write_bound_recovery_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture=capture,
        run_id=run_id,
    )
    result = read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
        artifact_root, repository_root=repository_root, capture_cache_root=cache_root
    )
    assert result.safe_payload()["capture_binding_status"] == "verified"
    assert all(t["failure_page_ordinal"] == budget for t in result.safe_payload()["targets"])


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
        {
            "target_key": "QQQ/NAS/1m",
            "status": "source_exhausted",
            "reason": None,
            "conflict_origin": "not_recorded_legacy",
            "retained_head_conflict_disposition": "not_recorded_legacy",
        },
        {
            "target_key": "SPY/AMS/1m",
            "status": "source_exhausted",
            "reason": None,
            "conflict_origin": "not_recorded_legacy",
            "retained_head_conflict_disposition": "not_recorded_legacy",
        },
    ]


@pytest.mark.parametrize(
    ("target_status", "target_reason", "provenance", "expected_origin", "expected_disposition"),
    [
        (
            "rejected",
            "minute_duplicate_conflict",
            {
                "conflict_origin": "candidate_batch",
                "retained_head_conflict_disposition": "not_applicable",
            },
            "candidate_batch",
            "not_applicable",
        ),
        (
            "rejected",
            "minute_duplicate_conflict",
            {
                "conflict_origin": "retained_cache",
                "retained_head_conflict_disposition": "quarantined",
            },
            "retained_cache",
            "quarantined",
        ),
        (
            "source_exhausted",
            None,
            {
                "conflict_origin": None,
                "retained_head_conflict_disposition": "not_applicable",
            },
            "not_applicable",
            "not_applicable",
        ),
    ],
)
def test_collection_recovery_projects_new_immutable_conflict_provenance(
    tmp_path: Path,
    target_status: str,
    target_reason: str | None,
    provenance: dict[str, object],
    expected_origin: str,
    expected_disposition: str,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(
        cache_root=capture_cache_root,
        target_status=target_status,
        target_reason=target_reason,
        target_provenance=provenance,
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

    assert all(
        target["conflict_origin"] == expected_origin
        and target["retained_head_conflict_disposition"] == expected_disposition
        for target in result.safe_payload()["targets"]
    )


@pytest.mark.parametrize(
    "target_provenance",
    [
        {"conflict_origin": "candidate_batch"},
        {
            "conflict_origin": "unknown_origin",
            "retained_head_conflict_disposition": "not_applicable",
        },
        {
            "conflict_origin": "candidate_batch",
            "retained_head_conflict_disposition": "quarantined",
        },
    ],
)
def test_collection_recovery_rejects_partial_or_unknown_future_provenance(
    tmp_path: Path,
    target_provenance: dict[str, object],
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(
        cache_root=capture_cache_root,
        target_provenance=target_provenance,
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

    _assert_evidence_unavailable(result.safe_payload(), schema_version=result.schema_version)


def test_collection_recovery_rejects_mixed_legacy_and_future_target_provenance(
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, capture_cache_root = _roots(tmp_path)
    capture = _write_capture_receipt(
        cache_root=capture_cache_root,
        target_provenance_by_key={
            "QQQ/NAS/1m": None,
            "SPY/AMS/1m": {
                "conflict_origin": "retained_cache",
                "retained_head_conflict_disposition": "preserved",
            },
        },
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

    _assert_evidence_unavailable(result.safe_payload(), schema_version=result.schema_version)


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
    target_provenance: dict[str, object] | None = None,
    target_provenance_by_key: dict[str, dict[str, object] | None] | None = None,
    run_id: str = _RUN_ID,
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
        "schedule_run_id": run_id,
        "observed_at": _CAPTURE_OBSERVED_AT.isoformat().replace("+00:00", "Z"),
        "current_session_cumulative_coverage_digest": coverage_digest,
        "current_session_cumulative_coverage_category": "incomplete",
        "current_session_cumulative_coverage": coverage,
        "targets": _capture_target_payloads(
            status=target_status,
            reason=target_reason,
            provenance=target_provenance,
            provenance_by_key=target_provenance_by_key,
        ),
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


def _capture_target_payloads(
    *,
    status: str,
    reason: str | None,
    provenance: dict[str, object] | None,
    provenance_by_key: dict[str, dict[str, object] | None] | None,
) -> list[dict[str, object]]:
    targets = [
        {
            "target_key": target_key,
            "status": status,
            "row_count": 0,
            "exact_overlap_rows": 0,
            "reason": reason,
        }
        for target_key in ("QQQ/NAS/1m", "SPY/AMS/1m")
    ]
    for target in targets:
        target_provenance = (
            provenance if provenance_by_key is None else provenance_by_key.get(target["target_key"])
        )
        if target_provenance is not None:
            target.update(target_provenance)
    return targets


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
    run_id: str = _RUN_ID,
) -> None:
    binding: dict[str, object] = {
        "session_capture_run_id": run_id,
        "session_capture_observed_at": _CAPTURE_OBSERVED_AT,
        "session_capture_receipt_sha256": capture.receipt_sha256,
        "session_capture_coverage_digest": capture.coverage_digest,
        "session_capture_coverage_category": "incomplete",
    }
    if binding_overrides is not None:
        binding.update(binding_overrides)
    write_kis_paper_intraday_head_schedule_receipt(
        run_id=run_id,
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
