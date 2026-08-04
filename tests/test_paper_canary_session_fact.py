"""Offline contracts for explicit KIS virtual-Paper scheduled-session evidence."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.execution.paper_canary_lifecycle import (
    PaperCanaryLifecycleError,
    read_paper_canary_lifecycle_fact_from_artifact_root,
    read_paper_canary_session_fact_from_artifact_root,
)


def _session_payload(
    session_id: str,
    *,
    status: str = "quote_unavailable",
    reason_code: str = "quote_timestamp_stale",
    run_id: str | None = None,
    canary_phase: str | None = None,
    canary_reason_code: str | None = None,
    submit_upstream_code: str | None = None,
    reconciliation_status: str | None = None,
    reconciliation_reason_code: str | None = None,
) -> dict[str, object]:
    return {
        "kind": "kis_paper_canary_session_evidence",
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "status": status,
        "reason_code": reason_code,
        "observed_at": "2026-08-04T14:35:00+00:00",
        "run_id": run_id,
        "canary_phase": canary_phase,
        "canary_reason_code": canary_reason_code,
        "submit_upstream_code": submit_upstream_code,
        "reconciliation_status": reconciliation_status,
        "reconciliation_reason_code": reconciliation_reason_code,
        "paper_only": True,
        "evidence_path": "C:/private/do-not-output-secret/evidence.json",
    }


def _write_session_evidence(
    artifact_root: Path,
    session_id: str,
    **kwargs: object,
) -> Path:
    evidence_path = (
        artifact_root
        / "execution"
        / "kis-paper-canary-session"
        / session_id
        / "evidence.json"
    )
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(
        json.dumps(_session_payload(session_id, **kwargs), sort_keys=True),
        encoding="utf-8",
    )
    return evidence_path


def test_session_fact_is_explicit_read_only_and_never_prints_evidence_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_id = "paper-session-quote-unavailable-1"
    evidence_path = _write_session_evidence(tmp_path, session_id)
    original_bytes = evidence_path.read_bytes()

    def network_forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline session projection must not open a network connection")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    fact = read_paper_canary_session_fact_from_artifact_root(tmp_path, session_id)

    assert fact.result_class == "no_new_intent"
    assert fact.run_id is None
    assert evidence_path.read_bytes() == original_bytes
    projected = json.dumps(fact.safe_payload(), sort_keys=True)
    assert "evidence_path" not in projected
    assert "do-not-output-secret" not in projected
    assert "lifecycle_state" not in projected


def test_session_fact_preserves_prior_submission_recovery_without_claiming_no_intent(
    tmp_path: Path,
) -> None:
    session_id = "paper-session-prior-unknown-2"
    _write_session_evidence(
        tmp_path,
        session_id,
        status="recovery_required",
        reason_code="prior_submission_unresolved",
        run_id="canary-prior-unknown-1",
        canary_phase="outcome_unknown",
        canary_reason_code="submit_transport_unknown",
        submit_upstream_code="5xx",
        reconciliation_status="unresolved",
        reconciliation_reason_code="transport_failure",
    )

    fact = read_paper_canary_session_fact_from_artifact_root(tmp_path, session_id)

    assert fact.result_class == "recovery_required"
    assert fact.run_id == "canary-prior-unknown-1"
    assert fact.canary_phase == "outcome_unknown"
    assert fact.safe_payload()["result_class"] != "no_new_intent"
    projected = json.dumps(fact.safe_payload(), sort_keys=True)
    assert "submit_upstream_code" not in projected
    assert "reconciliation_reason_code" not in projected
    assert "transport_failure" not in projected


def test_completed_session_fact_requires_direct_lifecycle_projection(tmp_path: Path) -> None:
    session_id = "paper-session-completed-1"
    _write_session_evidence(
        tmp_path,
        session_id,
        status="canary_completed",
        reason_code="reconciliation_clean",
        run_id="canary-completed-1",
        canary_phase="cancelled",
        canary_reason_code="reconciliation_clean",
        reconciliation_status="clean",
    )

    fact = read_paper_canary_session_fact_from_artifact_root(tmp_path, session_id)

    assert fact.result_class == "direct_lifecycle_required"
    assert fact.safe_payload()["kind"] == "kis_paper_canary_session_fact"
    assert fact.safe_payload()["reason_code"] is None
    assert "lifecycle_state" not in fact.safe_payload()


@pytest.mark.parametrize(
    ("requested_session_id", "recorded_session_id", "kwargs"),
    [
        (
            "paper-session-requested-1",
            "paper-session-recorded-1",
            {},
        ),
        (
            "paper-session-extra-field-1",
            "paper-session-extra-field-1",
            {"run_id": "canary-unexpected-1"},
        ),
    ],
)
def test_session_fact_rejects_mismatched_or_invalid_no_intent_receipts(
    tmp_path: Path,
    requested_session_id: str,
    recorded_session_id: str,
    kwargs: dict[str, object],
) -> None:
    _write_session_evidence(tmp_path, requested_session_id, **kwargs)
    evidence_path = (
        tmp_path
        / "execution"
        / "kis-paper-canary-session"
        / requested_session_id
        / "evidence.json"
    )
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["session_id"] = recorded_session_id
    evidence_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(PaperCanaryLifecycleError):
        read_paper_canary_session_fact_from_artifact_root(tmp_path, requested_session_id)


def test_session_fact_rejects_reparse_selected_session_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_id = "paper-session-reparse-1"
    _write_session_evidence(tmp_path, session_id)
    session_root = tmp_path / "execution" / "kis-paper-canary-session" / session_id
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        metadata = original_lstat(path)
        if path == session_root:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(Path, "lstat", marked_lstat)

    with pytest.raises(PaperCanaryLifecycleError):
        read_paper_canary_session_fact_from_artifact_root(tmp_path, session_id)


def test_session_fact_rejects_writer_shape_drift(tmp_path: Path) -> None:
    session_id = "paper-session-shape-drift-1"
    evidence_path = _write_session_evidence(tmp_path, session_id)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    evidence_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(PaperCanaryLifecycleError):
        read_paper_canary_session_fact_from_artifact_root(tmp_path, session_id)


@pytest.mark.parametrize("session_id", [".", ".."])
def test_session_fact_rejects_dot_path_component_ids(tmp_path: Path, session_id: str) -> None:
    with pytest.raises(PaperCanaryLifecycleError):
        read_paper_canary_session_fact_from_artifact_root(tmp_path, session_id)


@pytest.mark.parametrize("run_id", [".", ".."])
def test_lifecycle_fact_rejects_dot_path_component_ids(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(PaperCanaryLifecycleError):
        read_paper_canary_lifecycle_fact_from_artifact_root(tmp_path, run_id)
