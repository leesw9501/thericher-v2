"""Deterministic timeframe resampling for complete OHLCV bars."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import Bar, Timeframe, require_utc

SUPPORTED_RESAMPLE_TIMEFRAMES = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M10,
    Timeframe.H1,
    Timeframe.H3,
)
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class SessionWindow:
    """One caller-declared UTC market session; this class infers no calendar."""

    open_ts: datetime
    close_ts: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_ts", require_utc(self.open_ts, "open_ts"))
        object.__setattr__(self, "close_ts", require_utc(self.close_ts, "close_ts"))
        if self.close_ts <= self.open_ts:
            raise ValueError("close_ts must be after open_ts")

    @property
    def duration(self) -> timedelta:
        return self.close_ts - self.open_ts


@dataclass(frozen=True)
class SessionResampleResult:
    """Complete bars plus explicitly visible incomplete or terminal buckets."""

    bars: tuple[Bar, ...]
    skipped_bucket_starts: tuple[datetime, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))
        skipped = tuple(
            require_utc(timestamp, "skipped_bucket_start")
            for timestamp in self.skipped_bucket_starts
        )
        if skipped != tuple(sorted(set(skipped))):
            raise ValueError("skipped_bucket_starts must be unique and sorted")
        object.__setattr__(self, "skipped_bucket_starts", skipped)


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


def resample_session_bars(
    bars: list[Bar] | tuple[Bar, ...],
    target_timeframe: Timeframe,
    *,
    session: SessionWindow,
) -> SessionResampleResult:
    """Resample 1m bars from one explicit session, anchored at its open.

    The caller owns exchange-calendar and daylight-saving interpretation. This
    function rejects bars outside that declared window and surfaces skipped
    target buckets instead of joining another session or silently filling gaps.
    """

    target_timeframe = Timeframe(target_timeframe)
    if target_timeframe not in SUPPORTED_RESAMPLE_TIMEFRAMES:
        raise ValueError(f"unsupported target timeframe: {target_timeframe}")
    if session.duration % Timeframe.M1.duration != timedelta(0):
        raise ValueError("session window must align to the 1m source timeframe")
    full_bucket_starts, terminal_bucket_start = _session_bucket_plan(session, target_timeframe)
    if not bars:
        skipped = full_bucket_starts
        if terminal_bucket_start is not None:
            skipped = (*skipped, terminal_bucket_start)
        return SessionResampleResult((), skipped)

    ordered = sorted(bars, key=lambda bar: bar.start_ts)
    source_timeframe = ordered[0].timeframe
    symbol = ordered[0].symbol
    market = ordered[0].market
    if any(
        bar.timeframe != source_timeframe or bar.symbol != symbol or bar.market != market
        for bar in ordered
    ):
        raise ValueError("bars must have one symbol, market, and source timeframe")
    if source_timeframe != Timeframe.M1:
        raise ValueError("session resampling requires 1m source bars")
    if target_timeframe.duration < source_timeframe.duration:
        raise ValueError("target timeframe must be greater than or equal to source timeframe")
    if target_timeframe.duration % source_timeframe.duration != timedelta(0):
        raise ValueError("target timeframe must be an integer multiple of source timeframe")
    if any(
        bar.start_ts < session.open_ts or bar.end_ts > session.close_ts for bar in ordered
    ):
        raise ValueError("bars must remain inside the declared session window")

    expected_count = target_timeframe.duration // source_timeframe.duration
    complete_buckets: dict[datetime, list[Bar]] = defaultdict(list)
    for bar in ordered:
        if not bar.complete:
            continue
        bucket_index = (bar.start_ts - session.open_ts) // target_timeframe.duration
        bucket_start = session.open_ts + target_timeframe.duration * bucket_index
        complete_buckets[bucket_start].append(bar)

    resampled: list[Bar] = []
    skipped: list[datetime] = []
    for bucket_start in full_bucket_starts:
        bucket_bars = sorted(complete_buckets.get(bucket_start, ()), key=lambda bar: bar.start_ts)
        expected_starts = [
            bucket_start + source_timeframe.duration * offset for offset in range(expected_count)
        ]
        if (
            len(bucket_bars) != expected_count
            or [bar.start_ts for bar in bucket_bars] != expected_starts
        ):
            skipped.append(bucket_start)
            continue
        resampled.append(
            Bar(
                symbol=symbol,
                market=market,
                timeframe=target_timeframe,
                start_ts=bucket_start,
                open=bucket_bars[0].open,
                high=max(bar.high for bar in bucket_bars),
                low=min(bar.low for bar in bucket_bars),
                close=bucket_bars[-1].close,
                volume=sum((bar.volume for bar in bucket_bars), Decimal("0")),
                complete=True,
            )
        )

    if terminal_bucket_start is not None:
        skipped.append(terminal_bucket_start)
    return SessionResampleResult(tuple(resampled), tuple(skipped))


def _session_bucket_plan(
    session: SessionWindow,
    target_timeframe: Timeframe,
) -> tuple[tuple[datetime, ...], datetime | None]:
    full_bucket_count = session.duration // target_timeframe.duration
    starts = tuple(
        session.open_ts + target_timeframe.duration * index for index in range(full_bucket_count)
    )
    terminal_start = session.open_ts + target_timeframe.duration * full_bucket_count
    return starts, None if terminal_start == session.close_ts else terminal_start
