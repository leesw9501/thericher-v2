from __future__ import annotations

import json
from datetime import UTC, datetime

from thericher_v2.dashboard import build_snapshot
from thericher_v2.execution import EmergencyStore
from thericher_v2.ops.daily_report import write_bundle
from thericher_v2.state import EventStore


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
