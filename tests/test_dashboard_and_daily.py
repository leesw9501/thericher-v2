from __future__ import annotations

import json
import multiprocessing
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.dashboard import build_snapshot
from thericher_v2.execution import EmergencyStore
from thericher_v2.ops.daily_report import write_bundle
from thericher_v2.state import EventStore


def _update_emergency_state_in_process(
    path_value: str,
    action_name: str,
    first_read_ready,
    release_first_read,
    second_read_started,
) -> None:
    path = Path(path_value)
    original_read_text = Path.read_text

    def synchronized_read_text(candidate: Path, *args, **kwargs) -> str:
        contents = original_read_text(candidate, *args, **kwargs)
        if candidate == path:
            if action_name == "stop":
                first_read_ready.set()
                if not release_first_read.wait(timeout=5):
                    raise TimeoutError("test did not release the first state transition")
            else:
                second_read_started.set()
        return contents

    Path.read_text = synchronized_read_text
    try:
        store = EmergencyStore(path)
        if action_name == "stop":
            store.stop_new_orders("cross_process_stop")
        else:
            store.request_cancel_open_orders("cross_process_cancel")
    finally:
        Path.read_text = original_read_text


def test_emergency_store_writes_local_state_only(tmp_path) -> None:
    store = EmergencyStore(tmp_path / "emergency.json")

    stopped = store.stop_new_orders("unit_test")
    cancel = store.request_cancel_open_orders("unit_test_cancel")

    assert stopped.stop_new_orders
    assert cancel.stop_new_orders
    assert cancel.cancel_open_orders_requested
    assert json.loads((tmp_path / "emergency.json").read_text(encoding="utf-8"))[
        "cancel_open_orders_requested"
    ]


def test_emergency_store_preserves_existing_state_when_replace_fails(monkeypatch, tmp_path) -> None:
    path = tmp_path / "emergency.json"
    store = EmergencyStore(path)
    store.stop_new_orders("unit_test_stop")
    original_contents = path.read_bytes()

    def fail_replace(_source, _destination) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("thericher_v2.execution.emergency.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        store.request_cancel_open_orders("unit_test_cancel")

    assert path.read_bytes() == original_contents
    assert store.read().stop_new_orders
    assert not store.read().cancel_open_orders_requested


def test_emergency_store_merges_concurrent_stop_and_cancel_requests(monkeypatch, tmp_path) -> None:
    path = tmp_path / "emergency.json"
    store = EmergencyStore(path)
    store.clear("initial_clear")
    stop_store = EmergencyStore(path)
    cancel_store = EmergencyStore(path)
    original_read_text = Path.read_text

    def delayed_read_text(self, *args, **kwargs) -> str:
        contents = original_read_text(self, *args, **kwargs)
        if self == path:
            time.sleep(0.05)
        return contents

    monkeypatch.setattr(Path, "read_text", delayed_read_text)
    start = threading.Barrier(3)
    failures: list[Exception] = []

    def request(action, reason: str) -> None:
        try:
            start.wait(timeout=2)
            action(reason)
        except Exception as error:  # pragma: no cover - asserted below
            failures.append(error)

    workers = (
        threading.Thread(target=request, args=(stop_store.stop_new_orders, "concurrent_stop")),
        threading.Thread(
            target=request,
            args=(cancel_store.request_cancel_open_orders, "concurrent_cancel"),
        ),
    )
    for worker in workers:
        worker.start()
    start.wait(timeout=2)
    for worker in workers:
        worker.join(timeout=2)

    assert not failures
    assert all(not worker.is_alive() for worker in workers)
    state = store.read()
    assert state.stop_new_orders
    assert state.cancel_open_orders_requested


def test_emergency_store_serializes_cross_process_stop_and_cancel_requests(tmp_path) -> None:
    path = tmp_path / "emergency.json"
    EmergencyStore(path).clear("initial_clear")
    context = multiprocessing.get_context("spawn")
    first_read_ready = context.Event()
    release_first_read = context.Event()
    second_read_started = context.Event()
    stop_worker = context.Process(
        target=_update_emergency_state_in_process,
        args=(
            str(path),
            "stop",
            first_read_ready,
            release_first_read,
            second_read_started,
        ),
    )
    cancel_worker = context.Process(
        target=_update_emergency_state_in_process,
        args=(
            str(path),
            "cancel",
            first_read_ready,
            release_first_read,
            second_read_started,
        ),
    )

    stop_worker.start()
    assert first_read_ready.wait(timeout=5)
    cancel_worker.start()
    assert not second_read_started.wait(timeout=0.2)
    release_first_read.set()
    stop_worker.join(timeout=5)
    cancel_worker.join(timeout=5)

    assert stop_worker.exitcode == 0
    assert cancel_worker.exitcode == 0
    state = EmergencyStore(path).read()
    assert state.stop_new_orders
    assert state.cancel_open_orders_requested


def test_dashboard_snapshot_reads_event_and_emergency_state(tmp_path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")
    emergency.stop_new_orders("test")

    snapshot = build_snapshot(events, emergency)

    assert snapshot.mode == "off"
    assert snapshot.stop_new_orders
    assert snapshot.status == "local_monitor_only"


def test_daily_report_writes_single_summary(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    agents = repo_root / "agents"
    agents.mkdir(parents=True)
    (repo_root / "NEXT_CODEX_GOAL.md").write_text(
        "# Next Codex Goal\n\n## Objective\n\nRun the next bounded objective.\n",
        encoding="utf-8",
    )
    (agents / "data.md").write_text(
        "# Data Agent\n\n## Operator Help Needed\n\n- None now.\n",
        encoding="utf-8",
    )
    market_data_root = tmp_path / "market-data"
    market_data_root.mkdir()
    runtime_status = tmp_path / "operator_status.json"
    runtime_status.write_text(
        json.dumps(
            {
                "observed_at_utc": "2026-07-17T22:55:00+00:00",
                "mode": "off",
                "broker_calls": 0,
                "kis_api_calls": 0,
                "kis_paper_orders": 0,
                "live_orders": 0,
                "local_paper_fills": 2,
                "after_cost_pnl": "12.34 USD",
                "outcomes": ["CPU baseline completed."],
                "role_work": {"Data": "catalog ready"},
                "recovery_anomalies": [],
                "operator_decisions": [
                    "Approve paid source A.",
                    "Approve paper account read access.",
                    "Choose live-risk cap.",
                    "Approve public exposure.",
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"
    bundle = write_bundle(
        output_dir,
        now=datetime(2026, 7, 17, 23, tzinfo=UTC),
        repo_root=repo_root,
        market_data_root=market_data_root,
        runtime_status_path=runtime_status,
    )

    assert bundle.summary_path.exists()
    assert bundle.date == "2026-07-18"
    assert bundle.metrics["evidence_status"] == "available"
    assert bundle.metrics["kis_api_calls"] == 0
    assert bundle.metrics["local_paper_fills"] == 2
    assert bundle.metrics["market_data_root"] == str(market_data_root)
    assert bundle.metrics["data_operator_help_needed"] == []
    assert len(bundle.metrics["operator_decisions"]) == 4
    assert bundle.metrics["current_objective"] == "Run the next bounded objective."
    assert "[NEXT_CODEX_GOAL.md](../../NEXT_CODEX_GOAL.md)" in (
        bundle.summary_path.read_text(encoding="utf-8")
    )
    assert len(list(output_dir.iterdir())) == 1


def test_daily_report_marks_missing_runtime_evidence_unknown(tmp_path) -> None:
    output_dir = tmp_path / "reports"
    bundle = write_bundle(
        output_dir,
        repo_root=tmp_path / "missing-repo",
        market_data_root=tmp_path / "missing-data",
        runtime_status_path=tmp_path / "missing-status.json",
        configured_mode="off",
    )

    assert bundle.metrics["evidence_status"] == "missing"
    assert bundle.metrics["configured_mode"] == "off"
    assert bundle.metrics["mode"] == "unknown"
    assert bundle.metrics["broker_calls"] is None
    assert "Broker calls: `unknown`" in bundle.summary_path.read_text(
        encoding="utf-8"
    )


def test_daily_report_rejects_stale_runtime_activity(tmp_path) -> None:
    runtime_status = tmp_path / "operator_status.json"
    runtime_status.write_text(
        json.dumps(
            {
                "observed_at_utc": "2026-07-16T23:00:00+00:00",
                "mode": "kis_paper",
                "broker_calls": 0,
                "kis_api_calls": 0,
                "kis_paper_orders": 0,
                "live_orders": 0,
            }
        ),
        encoding="utf-8",
    )

    bundle = write_bundle(
        tmp_path / "reports",
        now=datetime(2026, 7, 17, 23, tzinfo=UTC),
        repo_root=tmp_path / "missing-repo",
        market_data_root=tmp_path / "missing-data",
        runtime_status_path=runtime_status,
        configured_mode="off",
    )

    assert bundle.metrics["evidence_status"] == "stale"
    assert bundle.metrics["configured_mode"] == "off"
    assert bundle.metrics["mode"] == "unknown"
    assert bundle.metrics["broker_calls"] is None
    assert bundle.metrics["kis_paper_orders"] is None
