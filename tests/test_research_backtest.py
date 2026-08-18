from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from thericher_v2.backtest import run_next_bar_backtest
from thericher_v2.contracts import ModelPrediction, OrderIntent, Signal, Timeframe
from thericher_v2.data import generate_trending_bars
from thericher_v2.ensemble import decide
from thericher_v2.execution import (
    EmergencyStore,
    LocalPaperBroker,
    replay_local_paper_realized_pnl,
)
from thericher_v2.models import MomentumModel
from thericher_v2.state import EventStore


class _TwoStepModel:
    lookback = 1

    def predict(self, bars):
        latest = bars[-1]
        action = {3: "buy", 4: "sell"}.get(len(bars), "hold")
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=Decimal("1"),
            reason="test_scripted_decision",
            timeframe=latest.timeframe,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id="two_step_test_model",
            model_version="1",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=Decimal("1"),
            expected_edge_bps=Decimal("1"),
            feature_window_end=latest.end_ts,
        )


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


def test_backtest_matches_local_paper_for_explicit_costs_at_next_bar_open(tmp_path) -> None:
    bars = generate_trending_bars(seed=3, count=6, drift_bps=Decimal("12"))
    fee_bps = Decimal("7")
    slippage_bps = Decimal("13")
    result = run_next_bar_backtest(
        bars,
        model=_TwoStepModel(),
        starting_cash=Decimal("10000"),
        quantity=Decimal("2"),
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )
    broker = LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        starting_cash=Decimal("10000"),
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )

    assert [trade.side for trade in result.trades] == ["buy", "sell"]
    for index, trade in enumerate(result.trades):
        signal_bar = bars[2 + index]
        execution_bar = bars[3 + index]
        order = OrderIntent(
            client_order_id=f"cost-parity-{index}",
            symbol=trade.symbol,
            market=trade.market,
            side=trade.side,
            quantity=trade.quantity,
            limit_price=None,
            decision_id=f"cost-parity-decision-{index}",
            created_at=signal_bar.end_ts,
        )

        local_result = broker.submit_and_fill_next_bar(
            order,
            signal_bar=signal_bar,
            execution_bar=execution_bar,
        )

        assert local_result.fill is not None
        assert local_result.fill.source == "local_paper"
        assert (
            local_result.fill.price,
            local_result.fill.fee,
            local_result.fill.filled_at.isoformat(),
        ) == (trade.execution_price, trade.fee, trade.execution_ts)

    realized = replay_local_paper_realized_pnl(broker.event_store.iter_events())

    assert broker.account().cash == result.ending_cash
    assert broker.account().positions == ()
    assert realized.realized_after_cost_pnl == result.pnl
    assert realized.open_quantity == Decimal("0")


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


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"starting_cash": Decimal("-1")}, "starting_cash"),
        ({"quantity": Decimal("0")}, "quantity"),
        ({"quantity": Decimal("-1")}, "quantity"),
        ({"fee_bps": Decimal("-1")}, "fee_bps"),
        ({"slippage_bps": Decimal("-1")}, "slippage_bps"),
    ],
)
def test_backtest_rejects_invalid_cash_quantity_and_cost_inputs(kwargs, message: str) -> None:
    bars = generate_trending_bars(seed=3, count=30, drift_bps=Decimal("12"))

    with pytest.raises(ValueError, match=message):
        run_next_bar_backtest(bars, model=MomentumModel(lookback=3), **kwargs)
