from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, EmergencyState, Timeframe


def test_bar_requires_utc_and_normalizes_symbol() -> None:
    bar = Bar(
        symbol="aapl",
        market="us",
        timeframe=Timeframe.M5,
        start_ts=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("1000"),
    )

    assert bar.symbol == "AAPL"
    assert bar.market == "US"
    assert bar.end_ts == datetime(2026, 1, 2, 14, 35, tzinfo=UTC)


def test_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        Bar(
            symbol="AAPL",
            market="US",
            timeframe=Timeframe.M1,
            start_ts=datetime(2026, 1, 2, 14, 30),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )


def test_bar_normalizes_timeframe_at_construction() -> None:
    bar = Bar(
        symbol="AAPL",
        market="US",
        timeframe="1m",  # type: ignore[arg-type]
        start_ts=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )

    assert bar.timeframe is Timeframe.M1
    assert bar.end_ts == datetime(2026, 1, 2, 14, 31, tzinfo=UTC)

    with pytest.raises(ValueError):
        Bar(
            symbol="AAPL",
            market="US",
            timeframe="invalid",  # type: ignore[arg-type]
            start_ts=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )


def test_emergency_state_blocks_new_orders_only_when_stop_is_active() -> None:
    clear = EmergencyState(
        stop_new_orders=False,
        cancel_open_orders_requested=True,
        reason="cancel_only",
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    stopped = EmergencyState(
        stop_new_orders=True,
        cancel_open_orders_requested=False,
        reason="stop",
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert not clear.blocks_new_orders
    assert stopped.blocks_new_orders
