from __future__ import annotations

import json
import socket
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.ops.kis_paper_intraday_head_schedule_receipt as schedule_receipt
from thericher_v2.ops.kis_paper_intraday_head_schedule_receipt import (
    KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY,
    KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME,
    SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE,
    KisPaperIntradayHeadScheduleReceiptError,
    read_kis_paper_intraday_head_schedule_fact_from_artifact_root,
    write_kis_paper_intraday_head_schedule_receipt,
)

_COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def test_schedule_receipt_writes_a_complete_source_safe_no_intent_outcome(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    result = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "complete"
    assert result.recovery_class == "complete"
    assert result.scheduler_exit_code == 0
    assert result.evidence_path == (
        artifact_root
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY
        / "intraday-head-unit.json"
    )
    payload = json.loads(result.evidence_path.read_text(encoding="ascii"))
    assert payload["status"] == "complete"
    assert payload["terminal"] == {
        "recovery_class": "complete",
        "scheduler_exit_code": 0,
        "status": "complete",
    }
    assert payload["stages"]["prospective_spy_cycle"] == {
        "canary_run_id": None,
        "collector_process_separate": True,
        "cycle_id": "prospective-spy-cycle-unit",
        "exit_code": 0,
        "status": "no_intent",
    }
    assert payload["stages"]["prospective_loop"] == {
        "exit_code": 0,
        "status": "embedded",
    }
    assert payload["stages"]["prospective_session"] == {
        "exit_code": 0,
        "session_id": "prospective-qqq-unit",
        "status": "no_intent",
    }
    assert payload["stages"]["prospective_validation"] == {
        "contract": "runtime-freshness-v4",
        "exit_code": 0,
        "session_id": "prospective-qqq-unit",
        "status": "validated",
    }
    assert payload["stages"]["profiled_mtf_forward_capture"] == {
        "data_only": True,
        "exit_code": 0,
        "status": "outside_cycle_slot",
    }
    rendered = result.evidence_path.read_bytes().lower()
    assert b"paper-key" not in rendered
    assert b"kis_live" not in rendered


def test_schedule_fact_reads_only_the_task_owned_current_pointer_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    result = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    runtime_path = (
        result.evidence_path.parent
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    )
    receipt_bytes = result.evidence_path.read_bytes()
    runtime_bytes = runtime_path.read_bytes()

    def network_forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("schedule receipt projection must stay offline")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
    )

    assert fact.run_id == result.run_id
    assert fact.terminal_status == "complete"
    assert fact.recovery_class == "complete"
    assert fact.scheduler_exit_code == 0
    assert result.evidence_path.read_bytes() == receipt_bytes
    assert runtime_path.read_bytes() == runtime_bytes
    projected = json.dumps(fact.safe_payload(), sort_keys=True)
    assert "evidence_path" not in projected
    assert str(artifact_root) not in projected
    assert "prospective_spy_cycle" not in projected


def test_schedule_fact_projects_legacy_receipts_as_explicitly_unbound(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
    )

    assert fact.coverage_binding_status == "legacy_unbound"
    assert fact.current_session_cumulative_coverage_digest is None
    assert fact.current_session_cumulative_coverage_category is None


def test_schedule_receipt_marks_a_missing_required_capture_binding_for_recovery(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    result = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        require_session_capture_binding=True,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    payload = json.loads(result.evidence_path.read_text(encoding="ascii"))
    assert result.terminal_status == "recovery"
    assert result.recovery_class == "session_capture_binding_unavailable"
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE
    assert payload["session_capture_binding_required"] is True
    assert "terminal_receipt_binding" not in payload
    with pytest.raises(
        KisPaperIntradayHeadScheduleReceiptError,
        match="schedule_capture_binding_required",
    ):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
        )


def test_schedule_receipt_rejects_an_unsupported_capture_coverage_category(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="terminal receipt binding"):
        write_kis_paper_intraday_head_schedule_receipt(
            **_complete_kwargs(),
            session_capture_run_id="intraday-head-unit",
            session_capture_observed_at=datetime(2026, 7, 28, 15, 30, tzinfo=UTC),
            session_capture_receipt_sha256="sha256:" + "a" * 64,
            session_capture_coverage_digest="sha256:" + "b" * 64,
            session_capture_coverage_category="pending_complete_sessions",
            artifact_root=tmp_path / "model-artifacts",
            repository_root=repository_root,
            observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
        )


def test_schedule_fact_verifies_the_exact_same_run_capture_binding(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data" / "intraday-head"
    capture_observed_at = datetime(2026, 7, 28, 15, 30, tzinfo=UTC)
    capture = _write_capture_receipt(
        cache_root=cache_root,
        observed_at=capture_observed_at,
    )
    result = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    with pytest.raises(
        KisPaperIntradayHeadScheduleReceiptError,
        match="schedule_capture_cache_root_required",
    ):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
        )

    fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=cache_root,
    )

    receipt_payload = json.loads(result.evidence_path.read_text(encoding="ascii"))
    binding = receipt_payload["terminal_receipt_binding"]
    assert binding == {
        "schedule_run_id": "intraday-head-unit",
        "observed_at": "2026-07-28T15:30:00Z",
        "receipt_sha256": capture.receipt_sha256,
        "current_session_cumulative_coverage_digest": capture.coverage_digest,
        "current_session_cumulative_coverage_category": "complete",
    }
    assert fact.coverage_binding_status == "verified"
    assert fact.current_session_cumulative_coverage_digest == capture.coverage_digest
    assert fact.current_session_cumulative_coverage_category == "complete"


def test_schedule_fact_verifies_an_incomplete_observed_session_capture(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data" / "intraday-head"
    capture = _write_capture_receipt(cache_root=cache_root, coverage_status="short")
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=cache_root,
    )

    assert fact.coverage_binding_status == "verified"
    assert fact.current_session_cumulative_coverage_category == "incomplete"


def test_schedule_fact_keeps_a_bound_pair_attempt_input_unavailable_without_attestation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data" / "intraday-head"
    observed_at = datetime(2026, 7, 28, 15, 31, tzinfo=UTC)
    capture = _write_capture_receipt(
        cache_root=cache_root,
        observed_at=datetime(2026, 7, 28, 15, 30, tzinfo=UTC),
    )
    availability_contract_sha256 = "sha256:" + "a" * 64
    availability_receipt_sha256 = "sha256:" + "b" * 64
    availability_precommit_sha256 = "sha256:" + "c" * 64
    availability_summary_sha256 = "sha256:" + "d" * 64
    prospective_contract_sha256 = "sha256:" + "e" * 64
    attempt_sha256 = "sha256:" + "f" * 64
    kwargs = {
        **_complete_kwargs(),
        "availability_status": "qualified_for_prospective_input",
        "availability_contract_sha256": availability_contract_sha256,
        "availability_receipt_sha256": availability_receipt_sha256,
        "availability_precommit_sha256": availability_precommit_sha256,
        "availability_summary_sha256": availability_summary_sha256,
        "observation_status": "observed",
        "observation_attempt_sha256": attempt_sha256,
        "observation_attempt_status": "observed",
        "observation_store_outcome": "appended",
    }
    write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
    )
    monkeypatch.setattr(
        schedule_receipt,
        "read_kis_qqq_spy_mtf_prospective_attempt",
        lambda **_: SimpleNamespace(
            attempt_sha256=attempt_sha256,
            contract_sha256=prospective_contract_sha256,
            status="observed",
            sealed_at=datetime(2026, 7, 28, 15, 30, tzinfo=UTC),
            session_date=date(2026, 7, 28),
        ),
    )
    monkeypatch.setattr(
        schedule_receipt,
        "read_kis_qqq_spy_mtf_prospective_contract",
        lambda **_: SimpleNamespace(
            contract_sha256=prospective_contract_sha256,
            availability_contract_sha256=availability_contract_sha256,
            availability_receipt_sha256=availability_receipt_sha256,
            availability_precommit_sha256=availability_precommit_sha256,
            availability_summary_sha256=availability_summary_sha256,
        ),
    )

    fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=cache_root,
        observation_artifact_root=artifact_root,
    )

    assert fact.availability_status == "qualified_for_prospective_input"
    assert fact.availability_binding_status == "verified"
    assert fact.availability_summary_sha256 == availability_summary_sha256
    assert fact.observation_binding_status == "verified"
    assert fact.observation_attempt_sha256 == attempt_sha256
    assert fact.causal_input_status == "input_unavailable"
    assert fact.causal_input_reason == "decision_time_availability_not_observed"
    assert fact.decision_time_availability == "not_observed"
    assert fact.provider_finality == "not_observed"

    monkeypatch.setattr(
        schedule_receipt,
        "read_kis_qqq_spy_mtf_prospective_contract",
        lambda **_: SimpleNamespace(
            contract_sha256=prospective_contract_sha256,
            availability_contract_sha256=availability_contract_sha256,
            availability_receipt_sha256=availability_receipt_sha256,
            availability_precommit_sha256=availability_precommit_sha256,
            availability_summary_sha256="sha256:" + "0" * 64,
        ),
    )
    with pytest.raises(
        KisPaperIntradayHeadScheduleReceiptError,
        match="schedule_availability_binding_mismatch",
    ):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
            capture_cache_root=cache_root,
            observation_artifact_root=artifact_root,
        )


@pytest.mark.parametrize(
    ("payload_overrides", "error_code"),
    [
        ({"schedule_run_id": "intraday-head-other"}, "schedule_capture_binding_mismatch"),
        ({"observed_at": "2026-07-28T15:29:00Z"}, "schedule_capture_binding_mismatch"),
        (
            {"current_session_cumulative_coverage_digest": "sha256:" + "1" * 64},
            "schedule_capture_binding_mismatch",
        ),
        (
            {"current_session_cumulative_coverage_category": "incomplete"},
            "schedule_capture_binding_mismatch",
        ),
        ({"kind": "other"}, "schedule_capture_receipt_invalid"),
    ],
)
def test_schedule_fact_rejects_capture_binding_payload_mismatches(
    tmp_path: Path,
    payload_overrides: dict[str, object],
    error_code: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data" / "intraday-head"
    capture = _write_capture_receipt(cache_root=cache_root, payload_overrides=payload_overrides)
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    with pytest.raises(KisPaperIntradayHeadScheduleReceiptError, match=error_code):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
            capture_cache_root=cache_root,
        )


def test_schedule_fact_rejects_a_capture_receipt_hash_mismatch(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data" / "intraday-head"
    capture = _write_capture_receipt(cache_root=cache_root)
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    capture.path.write_bytes(capture.path.read_bytes() + b"\n")

    with pytest.raises(
        KisPaperIntradayHeadScheduleReceiptError,
        match="schedule_capture_binding_mismatch",
    ):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
            capture_cache_root=cache_root,
        )


def test_schedule_fact_rejects_capture_receipt_reparse_points(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data" / "intraday-head"
    capture = _write_capture_receipt(cache_root=cache_root)
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        metadata = original_lstat(path)
        if path == capture.path:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(Path, "lstat", marked_lstat)
    with pytest.raises(
        KisPaperIntradayHeadScheduleReceiptError,
        match="schedule_capture_receipt_invalid",
    ):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
            capture_cache_root=cache_root,
        )


def test_schedule_fact_rejects_a_capture_cache_reparse_ancestor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_ancestor = tmp_path / "cache-parent"
    cache_root = cache_ancestor / "market-data" / "intraday-head"
    capture = _write_capture_receipt(cache_root=cache_root)
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        metadata = original_lstat(path)
        if path == cache_ancestor:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(Path, "lstat", marked_lstat)
    with pytest.raises(
        KisPaperIntradayHeadScheduleReceiptError,
        match="schedule_capture_cache_root_invalid",
    ):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
            capture_cache_root=cache_root,
        )


def test_schedule_fact_rejects_an_artifact_root_reparse_ancestor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_ancestor = tmp_path / "artifact-parent"
    artifact_root = artifact_ancestor / "model-artifacts"
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        metadata = original_lstat(path)
        if path == artifact_ancestor:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(Path, "lstat", marked_lstat)
    with pytest.raises(
        KisPaperIntradayHeadScheduleReceiptError,
        match="schedule_runtime_invalid",
    ):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
        )


@pytest.mark.parametrize(
    "capture_observed_at",
    [
        datetime(2026, 7, 28, 15, 32, tzinfo=UTC),
        datetime(2026, 7, 29, 4, 1, tzinfo=UTC),
    ],
)
def test_schedule_fact_rejects_capture_timestamp_conflicts(
    tmp_path: Path,
    capture_observed_at: datetime,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data" / "intraday-head"
    capture = _write_capture_receipt(cache_root=cache_root, observed_at=capture_observed_at)
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    with pytest.raises(
        KisPaperIntradayHeadScheduleReceiptError,
        match="schedule_capture_binding_mismatch",
    ):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
            capture_cache_root=cache_root,
        )


def test_schedule_fact_never_selects_a_newer_capture_receipt(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data" / "intraday-head"
    capture = _write_capture_receipt(
        cache_root=cache_root,
        observed_at=datetime(2026, 7, 28, 15, 29, tzinfo=UTC),
    )
    _write_capture_receipt(
        cache_root=cache_root,
        observed_at=datetime(2026, 7, 28, 15, 30, tzinfo=UTC),
        payload_overrides={"current_session_cumulative_coverage_category": "incomplete"},
    )
    write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        **capture.binding_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
        capture_cache_root=cache_root,
    )

    assert fact.coverage_binding_status == "verified"
    assert fact.current_session_cumulative_coverage_category == "complete"


def test_schedule_receipt_retains_a_newer_current_pointer_against_stale_rollback(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    newer_kwargs = _complete_kwargs()
    newer_kwargs["run_id"] = "intraday-head-newer"
    newer = write_kis_paper_intraday_head_schedule_receipt(
        **newer_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    stale_kwargs = _complete_kwargs()
    stale_kwargs["run_id"] = "intraday-head-stale"
    stale = write_kis_paper_intraday_head_schedule_receipt(
        **stale_kwargs,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 30, tzinfo=UTC),
    )

    fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
        artifact_root,
        repository_root=repository_root,
    )

    assert stale.evidence_path.is_file()
    assert fact.run_id == newer.run_id


def test_schedule_receipt_requires_all_or_none_session_capture_binding_fields(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="terminal receipt binding"):
        write_kis_paper_intraday_head_schedule_receipt(
            **_complete_kwargs(),
            session_capture_run_id="intraday-head-unit",
            artifact_root=tmp_path / "model-artifacts",
            repository_root=repository_root,
            observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
        )


def test_schedule_fact_rejects_pointer_receipt_mismatch(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    result = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    runtime_path = (
        result.evidence_path.parent
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    )
    runtime_payload = json.loads(runtime_path.read_text(encoding="ascii"))
    runtime_payload["receipt_sha256"] = "sha256:" + "0" * 64
    runtime_path.write_text(json.dumps(runtime_payload, sort_keys=True), encoding="ascii")

    with pytest.raises(KisPaperIntradayHeadScheduleReceiptError):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
        )


def test_schedule_fact_rejects_hash_matching_pointer_terminal_mismatch(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    result = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    runtime_path = (
        result.evidence_path.parent
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    )
    runtime_payload = json.loads(runtime_path.read_text(encoding="ascii"))
    runtime_payload.update(
        status="recovery",
        recovery_class="prospective_loop_exit_nonzero",
        scheduler_exit_code=SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE,
    )
    runtime_path.write_text(json.dumps(runtime_payload, sort_keys=True), encoding="ascii")

    with pytest.raises(KisPaperIntradayHeadScheduleReceiptError):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
        )


def test_schedule_fact_rejects_reparse_current_pointer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    result = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )
    runtime_path = (
        result.evidence_path.parent
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    )
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        metadata = original_lstat(path)
        if path == runtime_path:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(Path, "lstat", marked_lstat)

    with pytest.raises(KisPaperIntradayHeadScheduleReceiptError):
        read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
        )


@pytest.mark.parametrize("run_id", [".", "..", "current", "CURRENT"])
def test_schedule_receipt_rejects_reserved_or_dot_component_run_ids(
    tmp_path: Path,
    run_id: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs["run_id"] = run_id

    with pytest.raises(ValueError):
        write_kis_paper_intraday_head_schedule_receipt(
            **kwargs,
            artifact_root=tmp_path / "model-artifacts",
            repository_root=repository_root,
            observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("overrides", "expected_recovery_class"),
    [
        ({"prospective_loop_exit_code": 7}, "prospective_loop_exit_nonzero"),
        ({"prospective_loop_status": "unavailable"}, "prospective_loop_payload_unavailable"),
        ({"prospective_session_exit_code": 9}, "prospective_session_exit_nonzero"),
        ({"prospective_session_status": "unavailable"}, "prospective_session_payload_unavailable"),
        ({"prospective_session_id": None}, "prospective_session_id_unavailable"),
        ({"prospective_validation_exit_code": 11}, "prospective_validation_exit_nonzero"),
        (
            {"prospective_validation_status": "unavailable"},
            "prospective_validation_payload_unavailable",
        ),
        (
            {"prospective_validation_session_id": "prospective-qqq-other"},
            "prospective_validation_session_mismatch",
        ),
    ],
)
def test_schedule_receipt_marks_required_downstream_faults_for_recovery(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_recovery_class: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(overrides)

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == expected_recovery_class
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE
    assert result.safe_payload()["status"] == "recovery"


def test_schedule_receipt_preserves_the_collection_exit_code(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs["collection_exit_code"] = 13

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == "collection_exit_nonzero"
    assert result.scheduler_exit_code == 13


@pytest.mark.parametrize(
    ("overrides", "expected_recovery_class"),
    [
        ({"prospective_spy_cycle_exit_code": 7}, "prospective_spy_cycle_exit_nonzero"),
        (
            {"prospective_spy_cycle_status": "unavailable"},
            "prospective_spy_cycle_payload_unavailable",
        ),
        ({"prospective_spy_cycle_id": None}, "prospective_spy_cycle_id_unavailable"),
        (
            {
                "prospective_spy_cycle_status": "canary_completed",
                "prospective_spy_canary_run_id": None,
            },
            "prospective_spy_canary_run_id_unavailable",
        ),
    ],
)
def test_schedule_receipt_marks_prospective_spy_cycle_faults_for_recovery(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_recovery_class: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(overrides)

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == expected_recovery_class
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


def test_schedule_receipt_is_idempotent_for_one_run_id_and_timestamp(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    observed_at = datetime(2026, 7, 28, 15, 31, tzinfo=UTC)

    first = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
    )
    first_bytes = first.evidence_path.read_bytes()
    second = write_kis_paper_intraday_head_schedule_receipt(
        **_complete_kwargs(),
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
    )

    assert second.evidence_path == first.evidence_path
    assert second.evidence_path.read_bytes() == first_bytes


def test_schedule_receipt_keeps_the_legacy_observer_optional(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(observation_exit_code=17, observation_status="unavailable")

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "complete"
    assert result.scheduler_exit_code == 0


def test_schedule_receipt_accepts_the_explicit_data_only_execution_branch(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(
        prospective_loop_status="not_applicable",
        prospective_session_status="not_applicable",
        prospective_session_id=None,
        prospective_validation_status="not_applicable",
        prospective_validation_session_id=None,
        observation_status="not_observed",
    )

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "complete"
    assert result.scheduler_exit_code == 0
    assert result.safe_payload()["stages"]["observation"] == {
        "exit_code": 0,
        "status": "not_observed",
        "required_for_qqq_cycle": False,
        "data_only_pair_observation": True,
    }


@pytest.mark.parametrize(
    ("overrides", "expected_recovery_class"),
    [
        (
            {"observation_exit_code": 20, "observation_status": "unavailable"},
            "observation_exit_nonzero",
        ),
        ({"observation_status": "unavailable"}, "observation_payload_unavailable"),
        ({"observation_status": "busy"}, "observation_payload_unavailable"),
    ],
)
def test_data_only_schedule_receipt_requires_a_terminal_observation_fact(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_recovery_class: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(
        prospective_loop_status="not_applicable",
        prospective_session_status="not_applicable",
        prospective_session_id=None,
        prospective_validation_status="not_applicable",
        prospective_validation_session_id=None,
    )
    kwargs.update(overrides)

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == expected_recovery_class
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


@pytest.mark.parametrize(
    ("overrides", "expected_recovery_class"),
    [
        (
            {"capture_cycle_exit_code": 20, "capture_cycle_status": "input_unavailable"},
            "capture_cycle_exit_nonzero",
        ),
        ({"capture_cycle_status": "unavailable"}, "capture_cycle_payload_unavailable"),
        ({"capture_cycle_status": "busy"}, "capture_cycle_payload_unavailable"),
    ],
)
def test_data_only_schedule_receipt_requires_a_terminal_capture_cycle_fact(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_recovery_class: str,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    kwargs = _complete_kwargs()
    kwargs.update(
        prospective_loop_status="not_applicable",
        prospective_session_status="not_applicable",
        prospective_session_id=None,
        prospective_validation_status="not_applicable",
        prospective_validation_session_id=None,
    )
    kwargs.update(overrides)

    result = write_kis_paper_intraday_head_schedule_receipt(
        **kwargs,
        artifact_root=tmp_path / "model-artifacts",
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
    )

    assert result.terminal_status == "recovery"
    assert result.recovery_class == expected_recovery_class
    assert result.scheduler_exit_code == SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


def test_schedule_receipt_rejects_a_git_workspace_artifact_root(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        write_kis_paper_intraday_head_schedule_receipt(
            **_complete_kwargs(),
            artifact_root=repository_root / "model-artifacts",
            repository_root=repository_root,
            observed_at=datetime(2026, 7, 28, 15, 31, tzinfo=UTC),
        )


def test_compose_schedule_receipt_service_is_offline_and_has_no_kis_surface() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  kis-paper-intraday-head-receipt:\n", maxsplit=1)[1].split(
        "\n  kis-paper-receipt-observer:\n", maxsplit=1
    )[0]
    lowered = section.lower()

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "network_mode: none" in section
    assert "read_only: true" in section
    assert "thericher_v2.ops.kis_paper_intraday_head_schedule_receipt" in section
    assert "KIS_PAPER_" not in section
    assert "kis_live" not in lowered
    assert "/app/market_data" not in section
    assert "/app/model_artifacts" in section


def test_compose_capture_cycle_service_is_offline_and_has_no_kis_surface() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  profiled-mtf-forward-capture-cycle:\n", maxsplit=1)[1].split(
        "\n  kis-readonly:\n", maxsplit=1
    )[0]
    lowered = section.lower()

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "network_mode: none" in section
    assert "read_only: true" in section
    assert "run_profiled_mtf_forward_capture_cycle.py" in section
    assert "KIS_PAPER_" not in section
    assert "kis_live" not in lowered
    assert "/app/market_data" in section
    assert "/app/model_artifacts" in section


def test_compose_prospective_spy_cycle_has_only_the_virtual_paper_route() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  kis-paper-prospective-spy-cycle:\n", maxsplit=1)[1].split(
        "\n  kis-paper-prospective-spy-timing-probe:\n", maxsplit=1
    )[0]
    lowered = section.lower()

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "thericher_v2.ops.kis_paper_prospective_spy_cycle" in section
    assert "--execute" in section
    assert "--cancel-after-submit" in section
    assert "THERICHER_MODE: kis_paper" in section
    assert "KIS_PAPER_APP_KEY" in section
    assert "KIS_PAPER_ACCOUNT_NO" in section
    assert "KIS_LIVE" not in section
    assert "gpus:" not in section
    assert ":/app/market_data:ro" in section
    assert ":/app/model_artifacts" in section
    assert "network_mode: none" not in lowered


def test_compose_prospective_spy_timing_probe_is_network_disabled_and_credential_free() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  kis-paper-prospective-spy-timing-probe:\n", maxsplit=1)[1].split(
        "\n  kis-paper-qqq-intraday-head-readiness:\n", maxsplit=1
    )[0]

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "thericher_v2.ops.kis_paper_prospective_spy_timing_probe" in section
    assert "network_mode: none" in section
    assert "KIS_" not in section
    assert "THERICHER_MODE" not in section
    assert ":/app/market_data:ro" in section
    assert ":/app/model_artifacts" in section


def test_compose_qqq_intraday_head_readiness_is_fully_isolated() -> None:
    compose = _COMPOSE.read_text(encoding="ascii")
    section = compose.split("\n  kis-paper-qqq-intraday-head-readiness:\n", maxsplit=1)[1].split(
        "\n  kis-paper-prospective-qqq-session:\n", maxsplit=1
    )[0]
    lowered = section.lower()
    environment = section.split("    environment:\n", maxsplit=1)[1].split(
        "    volumes:\n", maxsplit=1
    )[0]
    volumes = section.split("    volumes:\n", maxsplit=1)[1]
    volume_lines = [line.strip() for line in volumes.splitlines() if line.strip().startswith("- ")]
    expected_cache_mount = (
        "- ${THERICHER_HOST_MARKET_DATA_ROOT:-D:/market_data}/us_equities/"
        "kis_paper_private/intraday-head:/app/market_data:ro"
    )
    expected_artifact_mount = (
        "- ${THERICHER_HOST_MODEL_ARTIFACT_ROOT:-D:/thericher-v2/model-artifacts}/data/"
        "kis-qqq-intraday-head-readiness-v1:"
        "/app/model_artifacts"
    )

    assert 'profiles: ["kis-paper-intraday-head"]' in section
    assert "scripts/observe_kis_paper_qqq_intraday_head_readiness.py" in section
    assert "network_mode: none" in section
    assert "read_only: true" in section
    assert "- /tmp" in section
    assert environment.strip() == "THERICHER_MODE: off"
    assert volume_lines == [
        expected_cache_mount,
        expected_artifact_mount,
    ]
    assert "KIS_" not in section
    assert "kis_live" not in lowered
    assert "/app/runtime" not in section
    assert "/app/private" not in section
    assert "/app/emergency" not in section
    assert "local-paper" not in lowered
    assert "./src:/app/src" not in section
    assert "./scripts:/app/scripts" not in section


def _write_capture_receipt(
    *,
    cache_root: Path,
    observed_at: datetime = datetime(2026, 7, 28, 15, 30, tzinfo=UTC),
    coverage_status: str = "complete",
    payload_overrides: dict[str, object] | None = None,
) -> SimpleNamespace:
    coverage_category = "complete" if coverage_status == "complete" else "incomplete"
    current_session_cumulative_coverage = {
        "complete_regular_session_dates": (
            ["2026-07-28"] if coverage_status == "complete" else []
        ),
        "last_reason_category": "none",
        "regular_session_coverage": [
            {
                "session_date": "2026-07-28",
                "status": coverage_status,
            }
        ],
    }
    coverage_digest = "sha256:" + sha256(
        json.dumps(
            current_session_cumulative_coverage,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    payload: dict[str, object] = {
        "kind": "kis_paper_intraday_session_capture",
        "schedule_run_id": "intraday-head-unit",
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "current_session_cumulative_coverage_digest": coverage_digest,
        "current_session_cumulative_coverage_category": coverage_category,
        "current_session_cumulative_coverage": current_session_cumulative_coverage,
    }
    if payload_overrides is not None:
        payload.update(payload_overrides)
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("ascii")
    receipt_sha256 = "sha256:" + sha256(encoded).hexdigest()
    path = (
        cache_root
        / "v1"
        / "session-capture"
        / f"{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{receipt_sha256[7:23]}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return SimpleNamespace(
        path=path,
        receipt_sha256=receipt_sha256,
        coverage_digest=payload["current_session_cumulative_coverage_digest"],
        binding_kwargs={
            "session_capture_run_id": "intraday-head-unit",
            "session_capture_observed_at": observed_at,
            "session_capture_receipt_sha256": receipt_sha256,
            "session_capture_coverage_digest": payload[
                "current_session_cumulative_coverage_digest"
            ],
            "session_capture_coverage_category": payload[
                "current_session_cumulative_coverage_category"
            ],
        },
    )


def _complete_kwargs() -> dict[str, object]:
    return {
        "run_id": "intraday-head-unit",
        "collection_exit_code": 0,
        "prospective_spy_cycle_exit_code": 0,
        "prospective_spy_cycle_status": "no_intent",
        "prospective_spy_cycle_id": "prospective-spy-cycle-unit",
        "prospective_spy_canary_run_id": None,
        "prospective_loop_exit_code": 0,
        "prospective_loop_status": "embedded",
        "prospective_session_exit_code": 0,
        "prospective_session_status": "no_intent",
        "prospective_session_id": "prospective-qqq-unit",
        "prospective_validation_exit_code": 0,
        "prospective_validation_status": "validated",
        "prospective_validation_session_id": "prospective-qqq-unit",
        "prospective_validation_contract": "runtime-freshness-v4",
        "observation_exit_code": 0,
        "observation_status": "pending",
        "capture_cycle_exit_code": 0,
        "capture_cycle_status": "outside_cycle_slot",
    }
