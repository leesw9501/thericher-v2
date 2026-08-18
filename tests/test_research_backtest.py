from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from thericher_v2.backtest import run_next_bar_backtest
from thericher_v2.contracts import Timeframe
from thericher_v2.data import generate_trending_bars
from thericher_v2.ensemble import decide
from thericher_v2.models import MomentumModel


def test_momentum_research_slice_is_deterministic() -> None:
    bars_a = generate_trending_bars(seed=11, count=20)
    bars_b = generate_trending_bars(seed=11, count=20)
    model = MomentumModel(lookback=3)

    prediction_a = model.predict(bars_a[:8])
    prediction_b = model.predict(bars_b[:8])
    decision = decide([prediction_a])

    assert bars_a == bars_b
    assert prediction_a == prediction_b
    assert decision.symbol == "AAPL"
    assert decision.action in {"buy", "sell", "hold"}


def test_backtest_uses_next_bar_execution_after_signal_bar() -> None:
    bars = generate_trending_bars(seed=3, count=30, drift_bps=Decimal("12"))
    result = run_next_bar_backtest(bars, model=MomentumModel(lookback=3))

    assert result.trades
    first = result.trades[0]
    assert first.execution_ts >= first.signal_bar_end
    assert result.equity > Decimal("0")


@pytest.mark.parametrize(
    ("bars", "message"),
    [
        (
            lambda source: source[:15]
            + [replace(bar, symbol="MSFT") for bar in source[15:]],
            "share one symbol",
        ),
        (
            lambda source: source[:15]
            + [replace(bar, timeframe=Timeframe.M10) for bar in source[15:]],
            "share one symbol",
        ),
        (
            lambda source: source[:15]
            + [replace(bar, complete=False) for bar in source[15:]],
            "must be complete",
        ),
        (
            lambda source: source[:16]
            + [replace(source[16], start_ts=source[15].start_ts)]
            + source[17:],
            "must not overlap",
        ),
        (lambda source: list(reversed(source)), "must be chronological"),
    ],
)
def test_backtest_rejects_noncausal_caller_supplied_sequences(bars, message: str) -> None:
    source = generate_trending_bars(seed=3, count=30, drift_bps=Decimal("12"))

    with pytest.raises(ValueError, match=message):
        run_next_bar_backtest(bars(source), model=MomentumModel(lookback=3))


def test_backtest_allows_a_gap_to_the_next_observed_session_bar() -> None:
    source = generate_trending_bars(seed=3, count=30, drift_bps=Decimal("12"))
    gap = timedelta(hours=16)
    bars = source[:15] + [replace(bar, start_ts=bar.start_ts + gap) for bar in source[15:]]

    result = run_next_bar_backtest(bars, model=MomentumModel(lookback=3))

    assert result.equity > Decimal("0")
