from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.execution.kis_market_data_rate_gate import KisPaperMarketDataRateGate


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
        self.sleep_calls: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now += timedelta(seconds=seconds)


def test_shared_gate_serializes_two_worker_instances_through_one_external_state(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    first = KisPaperMarketDataRateGate(
        control_root=tmp_path / "control",
        minimum_request_interval_seconds=1.25,
        clock=clock,
        sleeper=clock.sleep,
    )
    second = KisPaperMarketDataRateGate(
        control_root=tmp_path / "control",
        minimum_request_interval_seconds=1.25,
        clock=clock,
        sleeper=clock.sleep,
    )

    first.wait_for_request_slot()
    second.wait_for_request_slot()

    assert clock.sleep_calls == [1.25]
    snapshot = first.snapshot()
    assert snapshot.last_request_started_at_utc == datetime(
        2026,
        7,
        24,
        12,
        0,
        1,
        250000,
        tzinfo=UTC,
    )
    assert snapshot.retry_not_before_utc is None
    assert (tmp_path / "control" / "request-rate.json").is_file()


def test_rate_limit_cooldown_is_shared_without_storing_response_data(tmp_path: Path) -> None:
    clock = _Clock()
    gate = KisPaperMarketDataRateGate(
        control_root=tmp_path / "control",
        minimum_request_interval_seconds=1.25,
        rate_limit_backoff_seconds=60,
        clock=clock,
        sleeper=clock.sleep,
    )

    gate.wait_for_request_slot()
    gate.record_rate_limit()
    gate.wait_for_request_slot()

    assert clock.sleep_calls == [60.0]
    snapshot = gate.snapshot()
    assert snapshot.last_rate_limit_at_utc == datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    assert snapshot.last_request_started_at_utc == datetime(2026, 7, 24, 12, 1, tzinfo=UTC)
    assert snapshot.retry_not_before_utc == datetime(2026, 7, 24, 12, 1, tzinfo=UTC)
    state = (tmp_path / "control" / "request-rate.json").read_text(encoding="utf-8")
    assert "credential" not in state
    assert "response" not in state
