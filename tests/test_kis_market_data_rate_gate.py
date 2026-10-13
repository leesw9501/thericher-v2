from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MIN_PAGE_INTERVAL_SECONDS,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_MIN_REQUEST_INTERVAL_SECONDS,
)


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
        clock=clock,
        sleeper=clock.sleep,
    )
    second = KisPaperMarketDataRateGate(
        control_root=tmp_path / "control",
        clock=clock,
        sleeper=clock.sleep,
    )

    first.wait_for_request_slot()
    second.wait_for_request_slot()

    assert clock.sleep_calls == [KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS]
    snapshot = first.snapshot()
    assert snapshot.last_request_started_at_utc == datetime(
        2026,
        7,
        24,
        12,
        0,
        1,
        0,
        tzinfo=UTC,
    )
    assert snapshot.retry_not_before_utc is None
    assert (tmp_path / "control" / "request-rate.json").is_file()


def test_rate_limit_cooldown_is_shared_without_storing_response_data(tmp_path: Path) -> None:
    clock = _Clock()
    gate = KisPaperMarketDataRateGate(
        control_root=tmp_path / "control",
        minimum_request_interval_seconds=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
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


def test_private_kis_market_data_pacing_layers_share_the_installed_interval() -> None:
    assert KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS == 1.0
    assert (
        KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MIN_PAGE_INTERVAL_SECONDS
        == KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
    )
    assert (
        KIS_PAPER_PRIVATE_INTRADAY_MIN_REQUEST_INTERVAL_SECONDS
        == KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
    )


def test_request_start_callback_receives_only_the_reserved_safe_timestamp(tmp_path: Path) -> None:
    clock = _Clock()
    observed: list[datetime] = []
    gate = KisPaperMarketDataRateGate(
        control_root=tmp_path / "control",
        clock=clock,
        sleeper=clock.sleep,
        on_request_started=observed.append,
    )

    gate.wait_for_request_slot()

    assert observed == [datetime(2026, 7, 24, 12, 0, tzinfo=UTC)]
    assert clock.sleep_calls == []


def test_shared_token_start_gate_yields_without_sleep_or_secret_state(tmp_path: Path) -> None:
    clock = _Clock()
    first = KisPaperMarketDataTokenStartGate(
        control_root=tmp_path / "control",
        minimum_request_interval_seconds=300,
        clock=clock,
    )
    second = KisPaperMarketDataTokenStartGate(
        control_root=tmp_path / "control",
        minimum_request_interval_seconds=300,
        clock=clock,
    )

    assert first.token_request_is_due() is True
    assert first.claim_token_request_start() is True
    assert second.token_request_is_due() is False
    assert second.claim_token_request_start() is False
    assert clock.sleep_calls == []

    snapshot = second.snapshot()
    assert snapshot.last_token_request_started_at_utc == datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    assert snapshot.next_token_request_not_before_utc == datetime(
        2026,
        7,
        24,
        12,
        5,
        tzinfo=UTC,
    )
    state_path = tmp_path / "control" / "token-request.json"
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "last_token_request_started_at_utc": "2026-07-24T12:00:00Z",
        "schema_version": 1,
    }

    clock.now += timedelta(minutes=5)

    assert second.token_request_is_due() is True
    assert second.claim_token_request_start() is True


def test_atomic_token_guard_defers_a_competitor_without_touching_owner(tmp_path):
    from thericher_v2.execution.kis_market_data_rate_gate import (
        KisPaperTokenStartGateBusy,
        _atomic_token_state_guard,
    )

    root = tmp_path / "control"
    root.mkdir()
    gate = KisPaperMarketDataTokenStartGate(control_root=root, clock=lambda: _Clock().now)
    with _atomic_token_state_guard(root):
        assert gate.claim_token_request_start() is False
        assert gate.token_request_is_due() is False
        with pytest.raises(KisPaperTokenStartGateBusy):
            gate.snapshot()
        assert not (root / "token-request.json").exists()
        assert (root / "token-request.lock.d").is_dir()
    assert not (root / "token-request.lock.d").exists()
    assert gate.claim_token_request_start() is True


def test_interrupted_atomic_token_guard_is_not_reclaimed_by_age(tmp_path):
    import os

    from thericher_v2.execution.kis_market_data_rate_gate import KisPaperTokenStartGateBusy

    root = tmp_path / "control"
    directory = root / "token-request.lock.d"
    directory.mkdir(parents=True)
    os.utime(directory, (0, 0))
    gate = KisPaperMarketDataTokenStartGate(control_root=root)
    assert gate.claim_token_request_start() is False
    with pytest.raises(KisPaperTokenStartGateBusy):
        gate.snapshot()
    assert directory.is_dir() and not (root / "token-request.json").exists()


def test_failed_atomic_token_state_write_releases_only_the_empty_owned_guard(tmp_path, monkeypatch):
    import thericher_v2.execution.kis_market_data_rate_gate as module

    root = tmp_path / "control"
    gate = KisPaperMarketDataTokenStartGate(control_root=root)
    def fail(*args):
        raise OSError("synthetic state write failure")
    monkeypatch.setattr(module, "_write_state", fail)
    with pytest.raises(OSError, match="synthetic state write"):
        gate.claim_token_request_start()
    assert not (root / "token-request.lock.d").exists()
    assert not (root / "token-request.json").exists()
