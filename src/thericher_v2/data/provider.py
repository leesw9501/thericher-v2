"""Small market-data provider contracts.

Providers return engine-native ``Bar`` objects and do not imply any broker or
network capability. KIS adapters belong in the execution lane later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from thericher_v2.contracts import Bar, Timeframe, require_utc


@dataclass(frozen=True)
class BarQuery:
    symbol: str
    market: str
    timeframe: Timeframe
    start_ts: datetime | None = None
    end_ts: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "timeframe", Timeframe(self.timeframe))
        if self.start_ts is not None:
            object.__setattr__(self, "start_ts", require_utc(self.start_ts, "start_ts"))
        if self.end_ts is not None:
            object.__setattr__(self, "end_ts", require_utc(self.end_ts, "end_ts"))
        if self.start_ts is not None and self.end_ts is not None and self.end_ts <= self.start_ts:
            raise ValueError("end_ts must be after start_ts")


class MarketDataProvider(Protocol):
    def get_bars(self, query: BarQuery) -> list[Bar]:
        """Return bars matching ``query`` from a local or offline source."""


def filter_bars(bars: list[Bar] | tuple[Bar, ...], query: BarQuery) -> list[Bar]:
    result = [
        bar
        for bar in bars
        if bar.symbol == query.symbol
        and bar.market == query.market
        and bar.timeframe == query.timeframe
        and (query.start_ts is None or bar.start_ts >= query.start_ts)
        and (query.end_ts is None or bar.start_ts < query.end_ts)
    ]
    return sorted(result, key=lambda bar: bar.start_ts)
