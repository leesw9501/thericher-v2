from __future__ import annotations

import importlib.util
import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.ops import kis_paper_intraday_causal_attestation_writer as writer


def test_writer_creates_one_canonical_external_attestation_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, fact = _roots_and_fact(tmp_path)
    _write_input(artifact_root=artifact_root, fact=fact)
    monkeypatch.setattr(
        writer,
        "read_kis_paper_intraday_head_schedule_fact_from_artifact_root",
        lambda *_args, **_kwargs: fact,
    )

    def network_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("causal attestation writer must stay networkless")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    result = writer.write_current_kis_paper_intraday_causal_attestation(
        artifact_root=artifact_root,
        repository_root=repository_root,
        capture_cache_root=tmp_path / "cache",
    )

    assert result.status == "written"
    assert result.reason is None
    assert result.attestation_sha256 is not None
    assert result.evidence_path is not None
    payload = json.loads(result.evidence_path.read_text(encoding="ascii"))
    assert payload["schedule_run_id"] == fact.run_id
    assert payload["schedule_observed_at"] == "2026-08-17T21:20:00Z"
    assert payload["session_capture_receipt_sha256"] == fact.session_capture_receipt_sha256
    assert payload["availability_summary_sha256"] == fact.availability_summary_sha256
    assert payload["observation_attempt_sha256"] == fact.observation_attempt_sha256
    assert "decision_time_utc" not in payload
    assert "availability_observed_at" not in payload
    assert "finality_observed_at" not in payload
    assert "assumed-honest" in writer._INPUT_CLAIM
    assert result.safe_payload()["artifact_policy"]["raw_market_data_in_receipt"] is False


def test_writer_is_idempotent_for_one_exact_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, fact = _roots_and_fact(tmp_path)
    _write_input(artifact_root=artifact_root, fact=fact)
    monkeypatch.setattr(
        writer,
        "read_kis_paper_intraday_head_schedule_fact_from_artifact_root",
        lambda *_args, **_kwargs: fact,
    )

    first = writer.write_current_kis_paper_intraday_causal_attestation(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    second = writer.write_current_kis_paper_intraday_causal_attestation(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert first.status == "written"
    assert second.status == "already_written"
    assert second.attestation_sha256 == first.attestation_sha256
    assert second.evidence_path == first.evidence_path


def test_writer_default_denies_the_current_incomplete_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root, artifact_root, fact = _roots_and_fact(
        tmp_path,
        current_session_cumulative_coverage_category="incomplete",
    )
    _write_input(artifact_root=artifact_root, fact=fact)
    monkeypatch.setattr(
        writer,
        "read_kis_paper_intraday_head_schedule_fact_from_artifact_root",
        lambda *_args, **_kwargs: fact,
    )

    result = writer.write_current_kis_paper_intraday_causal_attestation(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.status == "not_written"
    assert result.reason == "session_coverage_incomplete"
    output_root = (
        artifact_root
        / "data"
        / writer.KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_ARTIFACT_DIRECTORY
    )
    assert not output_root.exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"schedule_run_id": "different-run"},
        {"schedule_observed_at": "2026-08-16T21:20:00Z"},
        {"attestation_origin": "task_derived"},
        {"availability_observed_at": "2026-08-17T19:31:00Z"},
    ],
)
def test_writer_rejects_replayed_task_derived_or_time_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    overrides: dict[str, str],
) -> None:
    repository_root, artifact_root, fact = _roots_and_fact(tmp_path)
    _write_input(artifact_root=artifact_root, fact=fact, overrides=overrides)
    monkeypatch.setattr(
        writer,
        "read_kis_paper_intraday_head_schedule_fact_from_artifact_root",
        lambda *_args, **_kwargs: fact,
    )

    result = writer.write_current_kis_paper_intraday_causal_attestation(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert result.status == "not_written"
    assert result.reason in {"input_invalid", "input_binding_mismatch", "input_time_order_invalid"}
    assert result.evidence_path is None


def test_writer_rejects_an_artifact_root_inside_git(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="external directory"):
        writer.write_current_kis_paper_intraday_causal_attestation(
            artifact_root=repository_root / "model-artifacts",
            repository_root=repository_root,
        )


def test_script_requires_explicit_execute(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    script = _load_script()

    assert script.main([]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "reason": "execute_flag_required",
        "status": "not_executed",
    }
    monkeypatch.setattr(
        script,
        "write_current_kis_paper_intraday_causal_attestation",
        lambda **_kwargs: SimpleNamespace(
            safe_payload=lambda: {"status": "not_written", "reason": "input_missing"}
        ),
    )

    assert script.main(["--execute"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "reason": "input_missing",
        "status": "not_written",
    }


def _roots_and_fact(
    tmp_path: Path,
    *,
    current_session_cumulative_coverage_category: str = "complete",
) -> tuple[Path, Path, SimpleNamespace]:
    repository_root = tmp_path / "repository"
    artifact_root = tmp_path / "model-artifacts"
    repository_root.mkdir()
    artifact_root.mkdir()
    fact = SimpleNamespace(
        run_id="intraday-head-unit",
        observed_at=datetime(2026, 8, 17, 21, 20, tzinfo=UTC),
        terminal_status="complete",
        coverage_binding_status="verified",
        current_session_cumulative_coverage_category=current_session_cumulative_coverage_category,
        session_capture_receipt_sha256="sha256:" + "a" * 64,
        availability_binding_status="verified",
        availability_status="qualified_for_prospective_input",
        availability_summary_sha256="sha256:" + "b" * 64,
        observation_binding_status="verified",
        observation_attempt_status="observed",
        observation_store_outcome="appended",
        observation_attempt_sha256="sha256:" + "c" * 64,
        causal_attestation_binding_status="not_recorded",
    )
    return repository_root, artifact_root, fact


def _write_input(
    *,
    artifact_root: Path,
    fact: SimpleNamespace,
    overrides: dict[str, str] | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": writer.KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_INPUT_KIND,
        "schedule_run_id": fact.run_id,
        "schedule_observed_at": fact.observed_at.isoformat().replace("+00:00", "Z"),
        "decision_time_utc": "2026-08-17T19:30:00Z",
        "availability_observed_at": "2026-08-17T19:29:00Z",
        "finality_observed_at": "2026-08-17T21:00:00Z",
        "attestation_origin": "independent_observer",
        "clock_authority": "independent_utc_clock",
        "timezone_dst_session_rule": "America_New_York_IANA_DST",
        "completed_bar_geometry": "m1_regular_session_complete_through_1530_et",
        "chronological_boundary": "non_overlapping",
        "decision_time_availability": "observed_at_decision_time",
        "provider_finality": "observed_final",
        "artifact_policy": dict(writer._ARTIFACT_POLICY),
        "claim": writer._INPUT_CLAIM,
    }
    if overrides:
        payload.update(overrides)
    destination = (
        artifact_root
        / "data"
        / writer.KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_INPUT_DIRECTORY
        / f"{fact.run_id}.json"
    )
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="ascii")


def _load_script() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "write_kis_paper_intraday_causal_attestation.py"
    )
    spec = importlib.util.spec_from_file_location("causal_attestation_writer_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
