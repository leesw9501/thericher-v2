"""Deterministic sample OHLCV data for offline tests and examples."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from decimal import Decimal

from thericher_v2.contracts import Bar, Timeframe


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def generate_trending_bars(
    *,
    symbol: str = "AAPL",
    market: str = "US",
    timeframe: Timeframe = Timeframe.M5,
    start: datetime = datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
    count: int = 80,
    seed: int = 7,
    start_price: Decimal = Decimal("100"),
    drift_bps: Decimal = Decimal("8"),
) -> list[Bar]:
    if count <= 0:
        raise ValueError("count must be positive")

    rng = random.Random(seed)
    bars: list[Bar] = []
    close = start_price
    for index in range(count):
        open_price = close
        noise_bps = Decimal(str(rng.randint(-4, 4)))
        move = Decimal("1") + ((drift_bps + noise_bps) / Decimal("10000"))
        close = _money(open_price * move)
        high = max(open_price, close) * Decimal("1.0005")
        low = min(open_price, close) * Decimal("0.9995")
        bars.append(
            Bar(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                start_ts=start + timeframe.duration * index,
                open=_money(open_price),
                high=_money(high),
                low=_money(low),
                close=_money(close),
                volume=Decimal(1000 + index * 10),
                complete=True,
            )
        )
    return bars
