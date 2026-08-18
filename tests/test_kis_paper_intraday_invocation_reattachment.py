from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest

from thericher_v2.ops import kis_paper_intraday_invocation_reattachment as reattachment
from thericher_v2.ops.kis_paper_intraday_head_invocation_receipt import (
    KisPaperIntradayHeadInvocationRuntimeFact,
    KisPaperIntradayHeadInvocationTerminalFact,
)

_HASH = "sha256:" + "a" * 64
_PROJECTOR = (
    Path(__file__).parents[1]
    / "scripts"
    / "project_kis_paper_intraday_invocation_reattachment.py"
)
_POWERSHELL_PROJECTOR = (
    Path(__file__).parents[1]
    / "scripts"
    / "project_kis_paper_intraday_invocation_reattachment.ps1"
)


def test_reattachment_keeps_a_missing_current_marker_unknown(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data"
    repository_root.mkdir()
    artifact_root.mkdir()
    cache_root.mkdir()

    result = reattachment.reattach_kis_paper_intraday_invocation_from_artifact_root(
        artifact_root=artifact_root,
        capture_cache_root=cache_root,
        repository_root=repository_root,
        task_facts=SimpleNamespace(),
        after_session_date=datetime(2026, 8, 1, tzinfo=UTC).date(),
        required_complete_session_count=1,
    )

    assert result.status == "marker_unavailable"
    assert result.reason == "current_marker_unavailable"
    assert result.safe_payload()["limitations"] == {
        "raw_market_data_read": False,
        "credentials_read": False,
        "broker_or_kis_call": False,
        "marker_proves_scheduler_origin": False,
        "topology_is_exact_run_binding": False,
    }
    assert result.safe_payload()["external_evidence"] == {
        "relative_to_artifact_root": True,
        "invocation_receipt": None,
        "schedule_terminal": None,
    }


def test_projector_exposes_only_source_safe_marker_unavailable_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root = tmp_path / "repository"
    artifact_root = tmp_path / "model-artifacts"
    cache_root = tmp_path / "market-data"
    repository_root.mkdir()
    artifact_root.mkdir()
    cache_root.mkdir()
    spec = importlib.util.spec_from_file_location("reattachment_projector", _PROJECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_REPOSITORY_ROOT", repository_root)

    assert (
        module.main(
            [
                "--artifact-root",
                str(artifact_root),
                "--head-cache-root",
                str(cache_root),
                "--task-name",
                "thericher-kis-paper-intraday-head",
                "--task-state",
                "Ready",
                "--task-enabled",
                "true",
                "--task-action-count",
                "1",
                "--trigger-start-boundary",
                "2026-08-20T11:29:00Z",
                "--last-task-result",
                "0",
                "--missed-run-count",
                "0",
                "--operational-log-state",
                "disabled",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == reattachment.KIS_PAPER_INTRADAY_INVOCATION_REATTACHMENT_KIND
    assert payload["status"] == "marker_unavailable"
    assert payload["external_evidence"]["relative_to_artifact_root"] is True
    assert "path" not in json.dumps(payload, sort_keys=True)


def test_powershell_projector_is_read_only_and_has_no_secret_surface() -> None:
    source = _POWERSHELL_PROJECTOR.read_text(encoding="ascii").lower()

    assert "get-scheduledtask" in source
    assert "get-scheduledtaskinfo" in source
    assert "start-scheduledtask" not in source
    assert "docker" not in source
    assert ".env" not in source
    assert "kis_paper_app_key" not in source
    assert "kis_paper_app_secret" not in source
    assert "kis_paper_account" not in source
    assert "kis_live" not in source


def test_reattachment_keeps_started_marker_distinct_from_terminal_evidence() -> None:
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    runtime = KisPaperIntradayHeadInvocationRuntimeFact(
        phase="started",
        run_id="head-unit",
        observed_at=started_at,
        receipt_sha256=_HASH,
    )

    result = reattachment.classify_kis_paper_intraday_invocation_reattachment(
        runtime=runtime,
        terminal=None,
        schedule=None,
        topology=None,
    )

    assert result.status == "start_only"
    assert result.run_id == "head-unit"
    assert result.started_at == started_at
    assert result.completed_at is None
    assert result.invocation_receipt_pointer.endswith("head-unit/started.json")


def test_reattachment_requires_exact_run_and_schedule_timestamp_binding() -> None:
    runtime, terminal, schedule = _bound_facts()
    mismatched_schedule = _schedule(
        run_id=terminal.run_id,
        observed_at=terminal.schedule_observed_at + timedelta(seconds=1),
    )

    result = reattachment.classify_kis_paper_intraday_invocation_reattachment(
        runtime=runtime,
        terminal=terminal,
        schedule=mismatched_schedule,
        topology=None,
    )

    assert result.status == "terminal_unavailable"
    assert result.reason == "schedule_timestamp_mismatch"
    assert result.schedule_receipt_sha256 is None


def test_reattachment_classifies_complete_session_with_metadata_only_relation() -> None:
    runtime, terminal, schedule = _bound_facts()
    topology = SimpleNamespace(
        sessions=(
            {
                "session_date": "2026-08-19",
                "coverage_status": "complete",
            },
        )
    )

    result = reattachment.classify_kis_paper_intraday_invocation_reattachment(
        runtime=runtime,
        terminal=terminal,
        schedule=schedule,
        topology=topology,
    )

    assert result.status == "complete_session"
    assert result.reason == "current_session_complete"
    assert result.topology_relation == "current_metadata_consistent"
    assert result.topology_session_date.isoformat() == "2026-08-19"
    assert result.completed_at == terminal.completed_at
    assert result.invocation_receipt_pointer.endswith("head-unit/terminal.json")
    assert result.schedule_receipt_pointer.endswith("head-unit.json")


@pytest.mark.parametrize(
    "collection_failure_category",
    ["reason_unavailable", "dispatcher_config", "collector_provider"],
)
def test_reattachment_preserves_each_closed_nonzero_category(
    collection_failure_category: Literal[
        "reason_unavailable", "dispatcher_config", "collector_provider"
    ],
) -> None:
    runtime, terminal, _ = _bound_facts(collection_outcome="nonzero")
    schedule = _schedule(
        run_id=terminal.run_id,
        observed_at=terminal.schedule_observed_at,
        terminal_status="recovery",
        recovery_class="collection_exit_nonzero",
        scheduler_exit_code=1,
        coverage_category="incomplete",
    )
    terminal = KisPaperIntradayHeadInvocationTerminalFact(
        run_id=terminal.run_id,
        started_at=terminal.started_at,
        schedule_observed_at=terminal.schedule_observed_at,
        completed_at=terminal.completed_at,
        receipt_sha256=terminal.receipt_sha256,
        collection_outcome="nonzero",
        collection_failure_category=collection_failure_category,
        schedule_receipt_outcome="recovery",
        terminal_outcome="nonzero",
    )

    result = reattachment.classify_kis_paper_intraday_invocation_reattachment(
        runtime=runtime,
        terminal=terminal,
        schedule=schedule,
        topology=None,
    )

    assert result.status == "collector_nonzero"
    assert result.reason == "collection_exit_nonzero"
    assert result.collection_failure_category == collection_failure_category
    assert result.safe_payload()["invocation"]["collection_failure_category"] == (
        collection_failure_category
    )


def _bound_facts(
    *, collection_outcome: Literal["succeeded", "nonzero"] = "succeeded"
) -> tuple[
    KisPaperIntradayHeadInvocationRuntimeFact,
    KisPaperIntradayHeadInvocationTerminalFact,
    SimpleNamespace,
]:
    started_at = datetime(2026, 8, 19, 15, 29, tzinfo=UTC)
    schedule_observed_at = started_at + timedelta(minutes=1)
    completed_at = schedule_observed_at + timedelta(seconds=15)
    runtime = KisPaperIntradayHeadInvocationRuntimeFact(
        phase="terminal",
        run_id="head-unit",
        observed_at=completed_at,
        receipt_sha256=_HASH,
    )
    terminal = KisPaperIntradayHeadInvocationTerminalFact(
        run_id="head-unit",
        started_at=started_at,
        schedule_observed_at=schedule_observed_at,
        completed_at=completed_at,
        receipt_sha256=_HASH,
        collection_outcome=collection_outcome,
        schedule_receipt_outcome="complete",
        terminal_outcome="succeeded",
    )
    return runtime, terminal, _schedule(
        run_id=terminal.run_id,
        observed_at=terminal.schedule_observed_at,
    )


def _schedule(
    *,
    run_id: str,
    observed_at: datetime,
    terminal_status: str = "complete",
    recovery_class: str = "complete",
    scheduler_exit_code: int = 0,
    coverage_category: str = "complete",
) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=run_id,
        observed_at=observed_at,
        terminal_status=terminal_status,
        recovery_class=recovery_class,
        scheduler_exit_code=scheduler_exit_code,
        receipt_sha256=_HASH,
        coverage_binding_status="verified",
        current_session_cumulative_coverage_category=coverage_category,
    )
