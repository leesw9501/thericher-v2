"""Deterministic timeframe resampling for complete OHLCV bars."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import Bar, Timeframe

SUPPORTED_RESAMPLE_TIMEFRAMES = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M10,
    Timeframe.H1,
    Timeframe.H3,
)
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _bucket_start(start_ts: datetime, target_timeframe: Timeframe) -> datetime:
    bucket_index = (start_ts - _UTC_EPOCH) // target_timeframe.duration
    return _UTC_EPOCH + target_timeframe.duration * bucket_index


def resample_bars(bars: list[Bar] | tuple[Bar, ...], target_timeframe: Timeframe) -> list[Bar]:
    """Aggregate complete bars into deterministic UTC-epoch anchored buckets.

    Missing or incomplete source bars make their containing bucket incomplete;
    the function skips those buckets instead of filling gaps.
    """

    target_timeframe = Timeframe(target_timeframe)
    if target_timeframe not in SUPPORTED_RESAMPLE_TIMEFRAMES:
        raise ValueError(f"unsupported target timeframe: {target_timeframe}")
    if not bars:
        return []

    ordered = sorted(bars, key=lambda bar: bar.start_ts)
    source_timeframe = ordered[0].timeframe
    symbol = ordered[0].symbol
    market = ordered[0].market
    if any(
        bar.timeframe != source_timeframe or bar.symbol != symbol or bar.market != market
        for bar in ordered
    ):
        raise ValueError("bars must have one symbol, market, and source timeframe")
    if target_timeframe.duration < source_timeframe.duration:
        raise ValueError("target timeframe must be greater than or equal to source timeframe")
    if target_timeframe.duration % source_timeframe.duration != timedelta(0):
        raise ValueError("target timeframe must be an integer multiple of source timeframe")

    if target_timeframe == source_timeframe:
        return [bar for bar in ordered if bar.complete]

    expected_count = target_timeframe.duration // source_timeframe.duration
    buckets: dict[datetime, list[Bar]] = defaultdict(list)
    for bar in ordered:
        if bar.complete:
            buckets[_bucket_start(bar.start_ts, target_timeframe)].append(bar)

    resampled: list[Bar] = []
    for bucket_ts in sorted(buckets):
        bucket_bars = sorted(buckets[bucket_ts], key=lambda bar: bar.start_ts)
        if len(bucket_bars) != expected_count:
            continue
        expected_starts = [
            bucket_ts + source_timeframe.duration * index for index in range(expected_count)
        ]
        if [bar.start_ts for bar in bucket_bars] != expected_starts:
            continue

        resampled.append(
            Bar(
                symbol=symbol,
                market=market,
                timeframe=target_timeframe,
                start_ts=bucket_ts,
                open=bucket_bars[0].open,
                high=max(bar.high for bar in bucket_bars),
                low=min(bar.low for bar in bucket_bars),
                close=bucket_bars[-1].close,
                volume=sum((bar.volume for bar in bucket_bars), Decimal("0")),
                complete=True,
            )
        )
    return resampled
