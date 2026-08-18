"""Tiny next-bar backtest harness.

Signals are generated only after a completed bar and can execute only on the
next bar open. This is the first anti-look-ahead invariant for v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from thericher_v2.contracts import Bar
from thericher_v2.ensemble.simple import decide
from thericher_v2.models.momentum import MomentumModel


@dataclass(frozen=True)
class Trade:
    symbol: str
    market: str
    side: str
    quantity: Decimal
    signal_bar_end: str
    execution_ts: str
    execution_price: Decimal
    fee: Decimal


@dataclass(frozen=True)
class BacktestResult:
    starting_cash: Decimal
    ending_cash: Decimal
    position: Decimal
    last_price: Decimal
    equity: Decimal
    trades: tuple[Trade, ...]

    @property
    def pnl(self) -> Decimal:
        return self.equity - self.starting_cash


def _cost_adjusted_price(price: Decimal, side: str, slippage_bps: Decimal) -> Decimal:
    adjustment = Decimal("1") + (slippage_bps / Decimal("10000"))
    if side == "sell":
        adjustment = Decimal("1") - (slippage_bps / Decimal("10000"))
    return (price * adjustment).quantize(Decimal("0.0001"))


def _validate_next_observed_bar_sequence(bars: list[Bar]) -> None:
    """Reject inputs that could turn list ordering into look-ahead bias.

    Session gaps are valid: a next observed bar can be the next market session.
    Overlap, reordering, mixed instruments, and incomplete bars are not valid
    inputs to a completed-bar next-observed-bar simulation.
    """

    first = bars[0]
    if not isinstance(first, Bar):
        raise TypeError("bars must contain Bar values")
    for bar in bars:
        if not isinstance(bar, Bar):
            raise TypeError("bars must contain Bar values")
        if (bar.symbol, bar.market, bar.timeframe) != (
            first.symbol,
            first.market,
            first.timeframe,
        ):
            raise ValueError("bars must share one symbol, market, and timeframe")
        if not bar.complete:
            raise ValueError("backtest bars must be complete")

    for prior, current in zip(bars, bars[1:], strict=False):
        if current.start_ts < prior.start_ts:
            raise ValueError("bars must be chronological")
        if current.start_ts < prior.end_ts:
            raise ValueError("bars must not overlap")


def run_next_bar_backtest(
    bars: list[Bar],
    *,
    model: MomentumModel | None = None,
    starting_cash: Decimal = Decimal("10000"),
    quantity: Decimal = Decimal("1"),
    fee_bps: Decimal = Decimal("1"),
    slippage_bps: Decimal = Decimal("2"),
) -> BacktestResult:
    if len(bars) < 6:
        raise ValueError("at least 6 bars are required")
    _validate_next_observed_bar_sequence(bars)
    model = model or MomentumModel()
    cash = starting_cash
    position = Decimal("0")
    trades: list[Trade] = []

    for index in range(model.lookback + 1, len(bars) - 1):
        signal_window = bars[: index + 1]
        execution_bar = bars[index + 1]
        prediction = model.predict(signal_window)
        decision = decide([prediction])
        if decision.action == "buy" and position <= 0:
            side = "buy"
        elif decision.action == "sell" and position > 0:
            side = "sell"
        else:
            continue

        execution_price = _cost_adjusted_price(execution_bar.open, side, slippage_bps)
        notional = execution_price * quantity
        fee = (notional * fee_bps / Decimal("10000")).quantize(Decimal("0.0001"))
        if side == "buy" and cash >= notional + fee:
            cash -= notional + fee
            position += quantity
        elif side == "sell":
            cash += notional - fee
            position -= quantity
        else:
            continue
        trades.append(
            Trade(
                symbol=execution_bar.symbol,
                market=execution_bar.market,
                side=side,
                quantity=quantity,
                signal_bar_end=signal_window[-1].end_ts.isoformat(),
                execution_ts=execution_bar.start_ts.isoformat(),
                execution_price=execution_price,
                fee=fee,
            )
        )

    last_price = bars[-1].close
    equity = cash + position * last_price
    return BacktestResult(
        starting_cash=starting_cash,
        ending_cash=cash,
        position=position,
        last_price=last_price,
        equity=equity,
        trades=tuple(trades),
    )
