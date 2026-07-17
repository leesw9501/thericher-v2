"""Offline market-data providers backed by local files or deterministic samples."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
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


@dataclass(frozen=True, init=False)
class CatalogedBars:
    dataset_id: str
    dataset_hash: str
    source_path: Path
    bars: tuple[Bar, ...]

    def __init__(
        self,
        dataset_id: str,
        dataset_hash: str,
        source_path: Path,
        bars: tuple[Bar, ...],
    ) -> None:
        raise ValueError("use load_cataloged_yahoo_intraday_1m_bars")


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


def load_cataloged_yahoo_intraday_1m_bars(
    path: Path,
    *,
    dataset_id: str,
    expected_dataset_hash: str,
    symbol: str | None = None,
    market: str = "US",
    max_bars: int = 120,
) -> CatalogedBars:
    """Load hash-bound Yahoo canonical 1m bars without network or credentials."""

    if not dataset_id.strip():
        raise ValueError("dataset_id is required")
    _validate_sha256(expected_dataset_hash, "expected_dataset_hash")
    if max_bars <= 0:
        raise ValueError("max_bars must be positive")
    resolved_market = market.strip().upper()
    if not resolved_market:
        raise ValueError("market is required")
    selected_symbol = symbol.strip().upper() if symbol is not None else None
    if symbol is not None and not selected_symbol:
        raise ValueError("symbol must be nonempty when supplied")

    source_path = Path(path)
    compressed_bytes = source_path.read_bytes()
    actual_hash = "sha256:" + hashlib.sha256(compressed_bytes).hexdigest()
    if actual_hash != expected_dataset_hash:
        raise ValueError(
            f"dataset hash mismatch: expected {expected_dataset_hash}, observed {actual_hash}"
        )

    bars: list[Bar] = []
    with gzip.open(
        io.BytesIO(compressed_bytes),
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        for row in csv.DictReader(handle):
            row_symbol = str(row["symbol"]).strip().upper()
            if selected_symbol is None:
                selected_symbol = row_symbol
            if row_symbol != selected_symbol:
                if bars:
                    break
                continue
            bars.append(
                Bar(
                    symbol=row_symbol,
                    market=resolved_market,
                    timeframe=Timeframe.M1,
                    start_ts=require_utc(
                        datetime.fromisoformat(
                            str(row["timestamp_utc"]).replace("Z", "+00:00")
                        ),
                        "timestamp_utc",
                    ),
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=Decimal(str(row["volume"])),
                    complete=True,
                )
            )
            if len(bars) >= max_bars:
                break
    if not bars:
        raise ValueError("no bars loaded from yahoo intraday file")
    return _cataloged_bars_from_verified_loader(
        dataset_id=dataset_id,
        dataset_hash=actual_hash,
        source_path=source_path,
        bars=tuple(bars),
    )


def _cataloged_bars_from_verified_loader(
    *,
    dataset_id: str,
    dataset_hash: str,
    source_path: Path,
    bars: tuple[Bar, ...],
) -> CatalogedBars:
    resolved_dataset_id = dataset_id.strip()
    if not resolved_dataset_id:
        raise ValueError("dataset_id is required")
    _validate_sha256(dataset_hash, "dataset_hash")
    raw_path = str(source_path).strip()
    if not raw_path or raw_path == ".":
        raise ValueError("source_path is required")
    resolved_bars = tuple(bars)
    if not resolved_bars:
        raise ValueError("bars are required")
    stream = (
        resolved_bars[0].symbol,
        resolved_bars[0].market,
        resolved_bars[0].timeframe,
    )
    if any(
        (bar.symbol, bar.market, bar.timeframe) != stream for bar in resolved_bars[1:]
    ):
        raise ValueError("bars must have homogeneous symbol, market, and timeframe")
    result = object.__new__(CatalogedBars)
    object.__setattr__(result, "dataset_id", resolved_dataset_id)
    object.__setattr__(result, "dataset_hash", dataset_hash)
    object.__setattr__(result, "source_path", Path(source_path))
    object.__setattr__(result, "bars", resolved_bars)
    return result


def _validate_sha256(value: str, field_name: str) -> None:
    prefix, separator, digest = value.partition(":")
    if (
        prefix != "sha256"
        or separator != ":"
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


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
