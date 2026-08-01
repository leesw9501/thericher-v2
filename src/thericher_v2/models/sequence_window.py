"""Pure causal multi-timeframe ``Bar`` windows for future model inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import Bar, Timeframe, require_utc

CAUSAL_SEQUENCE_WINDOW_SCHEMA_ID = "causal-multitimeframe-sequence-window-v1"
SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M10,
    Timeframe.H1,
    Timeframe.H3,
)
SequenceWindowInputStatus = Literal[
    "missing",
    "incomplete",
    "duplicate",
    "non_contiguous",
    "misaligned",
    "future",
]


class SequenceWindowInputError(ValueError):
    """A categorical structural failure in caller-supplied bar input."""

    def __init__(
        self,
        status: SequenceWindowInputStatus,
        message: str,
        *,
        timeframe: Timeframe | None = None,
    ) -> None:
        self.status = status
        self.timeframe = timeframe
        prefix = status if timeframe is None else f"{status}_{timeframe.value}"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True, slots=True)
class CausalSequenceWindow:
    """One ordered, completed, caller-selected timeframe window."""

    timeframe: Timeframe
    bars: tuple[Bar, ...] = field(repr=False)
    cutoff: datetime

    def __post_init__(self) -> None:
        if self.timeframe not in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
            raise ValueError("timeframe is not supported for a causal sequence window")
        bars = tuple(self.bars)
        if not bars or any(not isinstance(bar, Bar) for bar in bars):
            raise ValueError("bars must contain at least one Bar")
        if any(bar.timeframe != self.timeframe for bar in bars):
            raise ValueError("window bars must match the declared timeframe")
        object.__setattr__(self, "bars", bars)
        object.__setattr__(self, "cutoff", require_utc(self.cutoff, "cutoff"))

    @property
    def start_ts(self) -> datetime:
        return self.bars[0].start_ts

    @property
    def end_ts(self) -> datetime:
        return self.bars[-1].end_ts


@dataclass(frozen=True, slots=True)
class CausalMultiTimeframeSequenceWindow:
    """A provider-neutral, model-free group of causal bar windows."""

    symbol: str
    market: str
    cutoff: datetime
    windows: Mapping[Timeframe, CausalSequenceWindow] = field(repr=False)

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.market.strip():
            raise ValueError("symbol and market must be nonempty")
        normalized_windows = dict(self.windows)
        if tuple(normalized_windows) != SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
            raise ValueError("windows must cover the supported timeframes in canonical order")
        if any(
            timeframe != window.timeframe
            for timeframe, window in normalized_windows.items()
        ):
            raise ValueError("window mapping keys must match window timeframes")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "cutoff", require_utc(self.cutoff, "cutoff"))
        object.__setattr__(self, "windows", MappingProxyType(normalized_windows))

    def structural_metadata(self) -> dict[str, object]:
        """Return timestamps and counts without exposing OHLCV values."""

        return {
            "schema_id": CAUSAL_SEQUENCE_WINDOW_SCHEMA_ID,
            "symbol": self.symbol,
            "market": self.market,
            "cutoff": self.cutoff.isoformat(),
            "windows": {
                timeframe.value: {
                    "bar_count": len(window.bars),
                    "window_start": window.start_ts.isoformat(),
                    "window_end": window.end_ts.isoformat(),
                    "cutoff_lag_microseconds": _timedelta_microseconds(
                        self.cutoff - window.end_ts
                    ),
                }
                for timeframe, window in self.windows.items()
            },
        }


def build_causal_multitimeframe_sequence_window(
    bars_by_timeframe: Mapping[Timeframe, Sequence[Bar]],
    *,
    lookbacks: Mapping[Timeframe, int],
    cutoff: datetime,
) -> CausalMultiTimeframeSequenceWindow:
    """Build a causal model-input window without data access or model behavior.

    Every supplied sequence is a caller-owned continuous observation segment.
    Session calendars, exchange halts, data vintage, and resampling remain
    upstream responsibilities. This contract verifies only the selected tail's
    shape and its relationship to one declared UTC decision cutoff.
    """

    normalized_cutoff = require_utc(cutoff, "cutoff")
    normalized_lookbacks = _normalize_lookbacks(lookbacks)
    normalized_bars = _normalize_bars_by_timeframe(bars_by_timeframe)

    windows: dict[Timeframe, CausalSequenceWindow] = {}
    identities: set[tuple[str, str]] = set()
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        window = _select_causal_window(
            normalized_bars[timeframe],
            timeframe=timeframe,
            lookback=normalized_lookbacks[timeframe],
            cutoff=normalized_cutoff,
        )
        windows[timeframe] = window
        identities.add((window.bars[0].symbol, window.bars[0].market))

    if len(identities) != 1:
        raise SequenceWindowInputError(
            "misaligned",
            "all timeframe windows must share one symbol and market",
        )
    symbol, market = identities.pop()
    return CausalMultiTimeframeSequenceWindow(
        symbol=symbol,
        market=market,
        cutoff=normalized_cutoff,
        windows=windows,
    )


def _normalize_lookbacks(lookbacks: Mapping[Timeframe, int]) -> dict[Timeframe, int]:
    if set(lookbacks) != set(SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES):
        raise SequenceWindowInputError(
            "missing",
            "lookbacks must cover exactly 1m, 5m, 10m, 1h, and 3h",
        )
    normalized: dict[Timeframe, int] = {}
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        lookback = lookbacks[timeframe]
        if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
            raise ValueError(f"lookback for {timeframe.value} must be a positive integer")
        normalized[timeframe] = lookback
    return normalized


def _normalize_bars_by_timeframe(
    bars_by_timeframe: Mapping[Timeframe, Sequence[Bar]],
) -> dict[Timeframe, tuple[Bar, ...]]:
    if set(bars_by_timeframe) != set(SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES):
        raise SequenceWindowInputError(
            "missing",
            "bars_by_timeframe must cover exactly 1m, 5m, 10m, 1h, and 3h",
        )
    normalized: dict[Timeframe, tuple[Bar, ...]] = {}
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        bars = tuple(bars_by_timeframe[timeframe])
        if not bars:
            raise SequenceWindowInputError("missing", "no bars supplied", timeframe=timeframe)
        if any(not isinstance(bar, Bar) for bar in bars):
            raise TypeError("bars_by_timeframe values must contain Bar objects")
        normalized[timeframe] = bars
    return normalized


def _select_causal_window(
    bars: tuple[Bar, ...],
    *,
    timeframe: Timeframe,
    lookback: int,
    cutoff: datetime,
) -> CausalSequenceWindow:
    ordered = tuple(sorted(bars, key=lambda bar: bar.start_ts))
    if any(bar.timeframe != timeframe for bar in ordered):
        raise SequenceWindowInputError(
            "misaligned",
            "bar timeframe does not match its mapping key",
            timeframe=timeframe,
        )
    if len({bar.start_ts for bar in ordered}) != len(ordered):
        raise SequenceWindowInputError("duplicate", "duplicate bar start", timeframe=timeframe)
    if len({bar.symbol for bar in ordered}) != 1 or len({bar.market for bar in ordered}) != 1:
        raise SequenceWindowInputError(
            "misaligned",
            "bars must share one symbol and market",
            timeframe=timeframe,
        )
    if any(not bar.complete for bar in ordered):
        raise SequenceWindowInputError(
            "incomplete",
            "incomplete bars are not eligible",
            timeframe=timeframe,
        )
    if any(bar.end_ts > cutoff for bar in ordered):
        raise SequenceWindowInputError(
            "future",
            "future bars are not eligible",
            timeframe=timeframe,
        )
    if len(ordered) < lookback:
        raise SequenceWindowInputError(
            "missing",
            f"requires {lookback} bars but received {len(ordered)}",
            timeframe=timeframe,
        )

    selected = ordered[-lookback:]
    if any(
        later.start_ts != earlier.start_ts + timeframe.duration
        for earlier, later in zip(selected[:-1], selected[1:], strict=True)
    ):
        raise SequenceWindowInputError(
            "non_contiguous",
            "selected bars must be exactly contiguous",
            timeframe=timeframe,
        )
    if cutoff - selected[-1].end_ts >= timeframe.duration:
        raise SequenceWindowInputError(
            "misaligned",
            "last completed bar is older than one timeframe at cutoff",
            timeframe=timeframe,
        )
    return CausalSequenceWindow(timeframe=timeframe, bars=selected, cutoff=cutoff)


def _timedelta_microseconds(value) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds
