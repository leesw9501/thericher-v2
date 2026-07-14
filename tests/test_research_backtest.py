from __future__ import annotations

from decimal import Decimal

from thericher_v2.backtest import run_next_bar_backtest
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
