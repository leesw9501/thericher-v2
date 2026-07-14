from __future__ import annotations

import json

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


def test_daily_report_writes_single_bundle(tmp_path) -> None:
    bundle = write_bundle(tmp_path)

    assert bundle.summary_path.exists()
    assert bundle.metrics_path.exists()
    assert bundle.next_goal_path.exists()
    assert bundle.metrics["kis_api_calls"] is False
    assert bundle.metrics["market_data_root"] == "D:\\market_data"
    assert bundle.metrics["data_operator_help_needed"] == []
    assert len(list(tmp_path.iterdir())) == 3
