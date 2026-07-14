"""Offline market-data providers backed by local files or deterministic samples."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from thericher_v2.contracts import Bar, Timeframe, require_utc
from thericher_v2.data.provider import BarQuery, filter_bars
from thericher_v2.data.resample import resample_bars
from thericher_v2.data.synthetic import generate_trending_bars

CSV_FIELDS = (
    "symbol",
    "market",
    "timeframe",
    "start_ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "complete",
)


def bar_to_record(bar: Bar) -> dict[str, str]:
    return {
        "symbol": bar.symbol,
        "market": bar.market,
        "timeframe": bar.timeframe.value,
        "start_ts": bar.start_ts.isoformat(),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
        "complete": str(bar.complete).lower(),
    }


def bar_from_record(record: dict[str, Any]) -> Bar:
    complete_value = str(record.get("complete", "true")).strip().lower()
    if complete_value not in {"true", "false"}:
        raise ValueError("complete must be true or false")
    start_ts = require_utc(datetime.fromisoformat(str(record["start_ts"])), "start_ts")
    return Bar(
        symbol=str(record["symbol"]),
        market=str(record["market"]),
        timeframe=Timeframe(str(record["timeframe"])),
        start_ts=start_ts,
        open=Decimal(str(record["open"])),
        high=Decimal(str(record["high"])),
        low=Decimal(str(record["low"])),
        close=Decimal(str(record["close"])),
        volume=Decimal(str(record["volume"])),
        complete=complete_value == "true",
    )


@dataclass(frozen=True)
class LocalCsvBarProvider:
    path: Path | str

    def get_bars(self, query: BarQuery) -> list[Bar]:
        path = Path(self.path)
        with path.open(newline="", encoding="utf-8") as handle:
            bars = [bar_from_record(row) for row in csv.DictReader(handle)]
        return filter_bars(bars, query)


@dataclass(frozen=True)
class SampleBarProvider:
    base_bars: tuple[Bar, ...]

    @classmethod
    def trending_1m(
        cls,
        *,
        symbol: str = "AAPL",
        market: str = "US",
        start: datetime = datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
        count: int = 240,
        seed: int = 7,
    ) -> SampleBarProvider:
        return cls(
            tuple(
                generate_trending_bars(
                    symbol=symbol,
                    market=market,
                    timeframe=Timeframe.M1,
                    start=start,
                    count=count,
                    seed=seed,
                )
            )
        )

    def get_bars(self, query: BarQuery) -> list[Bar]:
        if not self.base_bars:
            return []
        source_timeframe = self.base_bars[0].timeframe
        if query.timeframe == source_timeframe:
            bars = list(self.base_bars)
        else:
            bars = resample_bars(self.base_bars, query.timeframe)
        return filter_bars(bars, query)
