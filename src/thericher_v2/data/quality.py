"""Warning-only quality checks for local market-data bars."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.data.resample import SUPPORTED_RESAMPLE_TIMEFRAMES

BarQualityCode = Literal[
    "duplicate_bar",
    "non_monotonic_timestamp",
    "missing_1m_interval",
    "incomplete_resample_bucket",
]

DEFAULT_RESAMPLE_QUALITY_TIMEFRAMES = (
    Timeframe.M5,
    Timeframe.M10,
    Timeframe.H1,
    Timeframe.H3,
)
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class BarQualityWarning:
    code: BarQualityCode
    message: str
    market: str
    symbol: str
    timeframe: Timeframe
    start_ts: datetime | None = None
    target_timeframe: Timeframe | None = None
    count: int = 1
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError("message is required")
        if self.count <= 0:
            raise ValueError("count must be positive")
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "timeframe", Timeframe(self.timeframe))
        if self.target_timeframe is not None:
            object.__setattr__(
                self,
                "target_timeframe",
                Timeframe(self.target_timeframe),
            )
        if self.start_ts is not None:
            object.__setattr__(self, "start_ts", require_utc(self.start_ts, "start_ts"))


@dataclass(frozen=True)
class BarQualityReport:
    bars_seen: int
    warnings: tuple[BarQualityWarning, ...]
    notes: tuple[str, ...]
    blocks_research: bool = False
    schema_version: int = SCHEMA_VERSION

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)


def assess_bar_quality(
    bars: list[Bar] | tuple[Bar, ...],
    *,
    target_timeframes: tuple[Timeframe, ...] = DEFAULT_RESAMPLE_QUALITY_TIMEFRAMES,
) -> BarQualityReport:
    """Return descriptive data-quality warnings without mutating or rejecting bars."""

    source = tuple(bars)
    warnings: list[BarQualityWarning] = []
    if not source:
        return BarQualityReport(
            bars_seen=0,
            warnings=(),
            notes=("no bars supplied; no data-quality checks ran",),
        )

    warnings.extend(_duplicate_warnings(source))
    warnings.extend(_non_monotonic_warnings(source))
    warnings.extend(_missing_1m_interval_warnings(source))
    warnings.extend(_incomplete_resample_bucket_warnings(source, target_timeframes))
    notes = (
        "warnings are descriptive only and do not block research",
        f"{len(warnings)} warning(s) found" if warnings else "no warning-only issues found",
    )
    return BarQualityReport(
        bars_seen=len(source),
        warnings=tuple(warnings),
        notes=notes,
    )


def _duplicate_warnings(bars: tuple[Bar, ...]) -> tuple[BarQualityWarning, ...]:
    key_counts = Counter(_bar_key(bar) for bar in bars)
    warnings: list[BarQualityWarning] = []
    for key, count in sorted(key_counts.items(), key=lambda item: item[0]):
        if count <= 1:
            continue
        market, symbol, timeframe, start_ts = key
        warnings.append(
            BarQualityWarning(
                code="duplicate_bar",
                message=(
                    "duplicate bar key appears "
                    f"{count} times for {market}:{symbol} {timeframe.value}"
                ),
                market=market,
                symbol=symbol,
                timeframe=timeframe,
                start_ts=start_ts,
                count=count,
            )
        )
    return tuple(warnings)


def _non_monotonic_warnings(bars: tuple[Bar, ...]) -> tuple[BarQualityWarning, ...]:
    warnings: list[BarQualityWarning] = []
    for (market, symbol, timeframe), stream in _streams_in_input_order(bars).items():
        for prior, current in zip(stream, stream[1:], strict=False):
            if current.start_ts < prior.start_ts:
                warnings.append(
                    BarQualityWarning(
                        code="non_monotonic_timestamp",
                        message=(
                            "bar timestamp moved backward from "
                            f"{prior.start_ts.isoformat()} to {current.start_ts.isoformat()}"
                        ),
                        market=market,
                        symbol=symbol,
                        timeframe=timeframe,
                        start_ts=current.start_ts,
                    )
                )
    return tuple(warnings)


def _missing_1m_interval_warnings(bars: tuple[Bar, ...]) -> tuple[BarQualityWarning, ...]:
    warnings: list[BarQualityWarning] = []
    for (market, symbol, timeframe), stream in _streams_in_input_order(bars).items():
        if timeframe != Timeframe.M1:
            continue
        starts = sorted({bar.start_ts for bar in stream})
        for prior, current in zip(starts, starts[1:], strict=False):
            delta = current - prior
            if delta <= Timeframe.M1.duration:
                continue
            missing_count = max(int(delta // Timeframe.M1.duration) - 1, 1)
            first_missing = prior + Timeframe.M1.duration
            warnings.append(
                BarQualityWarning(
                    code="missing_1m_interval",
                    message=(
                        f"missing {missing_count} expected 1m interval(s) before "
                        f"{current.isoformat()}"
                    ),
                    market=market,
                    symbol=symbol,
                    timeframe=timeframe,
                    start_ts=first_missing,
                    count=missing_count,
                )
            )
    return tuple(warnings)


def _incomplete_resample_bucket_warnings(
    bars: tuple[Bar, ...],
    target_timeframes: tuple[Timeframe, ...],
) -> tuple[BarQualityWarning, ...]:
    warnings: list[BarQualityWarning] = []
    targets = tuple(Timeframe(timeframe) for timeframe in target_timeframes)
    for (market, symbol, timeframe), stream in _streams_in_input_order(bars).items():
        if timeframe != Timeframe.M1:
            continue
        for target in targets:
            if (
                target not in SUPPORTED_RESAMPLE_TIMEFRAMES
                or target.duration <= timeframe.duration
                or target.duration % timeframe.duration
            ):
                continue
            warnings.extend(
                _target_bucket_warnings(
                    stream=tuple(stream),
                    market=market,
                    symbol=symbol,
                    timeframe=timeframe,
                    target_timeframe=target,
                )
            )
    return tuple(warnings)


def _target_bucket_warnings(
    *,
    stream: tuple[Bar, ...],
    market: str,
    symbol: str,
    timeframe: Timeframe,
    target_timeframe: Timeframe,
) -> tuple[BarQualityWarning, ...]:
    expected_count = target_timeframe.duration // timeframe.duration
    buckets: dict[datetime, list[Bar]] = defaultdict(list)
    for bar in stream:
        if bar.complete:
            buckets[_bucket_start(bar.start_ts, target_timeframe)].append(bar)

    warnings: list[BarQualityWarning] = []
    for bucket_ts in sorted(buckets):
        bucket_bars = sorted(buckets[bucket_ts], key=lambda bar: bar.start_ts)
        expected_starts = tuple(
            bucket_ts + timeframe.duration * index for index in range(expected_count)
        )
        actual_starts = tuple(bar.start_ts for bar in bucket_bars)
        if len(bucket_bars) == expected_count and actual_starts == expected_starts:
            continue
        warnings.append(
            BarQualityWarning(
                code="incomplete_resample_bucket",
                message=(
                    f"incomplete {target_timeframe.value} bucket has "
                    f"{len(bucket_bars)} of {expected_count} expected complete "
                    f"{timeframe.value} bars"
                ),
                market=market,
                symbol=symbol,
                timeframe=timeframe,
                start_ts=bucket_ts,
                target_timeframe=target_timeframe,
                count=len(bucket_bars),
            )
        )
    return tuple(warnings)


def _streams_in_input_order(
    bars: tuple[Bar, ...],
) -> dict[tuple[str, str, Timeframe], list[Bar]]:
    streams: dict[tuple[str, str, Timeframe], list[Bar]] = defaultdict(list)
    for bar in bars:
        streams[(bar.market, bar.symbol, bar.timeframe)].append(bar)
    return streams


def _bar_key(bar: Bar) -> tuple[str, str, Timeframe, datetime]:
    return (bar.market, bar.symbol, bar.timeframe, bar.start_ts)


def _bucket_start(start_ts: datetime, target_timeframe: Timeframe) -> datetime:
    bucket_index = (start_ts - _UTC_EPOCH) // target_timeframe.duration
    return _UTC_EPOCH + target_timeframe.duration * bucket_index
