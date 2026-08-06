"""Pure causal session-reset VWAP feature construction.

This module deliberately exposes no directional state, signal, target, or
execution concept.  It computes one session-local feature from completed bars
already available at a caller-declared cutoff.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from thericher_v2.contracts import Bar, require_utc
from thericher_v2.market.resample import SessionWindow

SESSION_RESET_VWAP_FEATURE_SCHEMA_ID = "session-reset-vwap-feature-v1"
_THREE = Decimal("3")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class SessionResetVwapFeature:
    """One in-memory, session-local VWAP feature at a completed-bar cutoff."""

    feature_window_end: datetime
    bar_count: int
    cumulative_volume: Decimal
    vwap: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "feature_window_end",
            require_utc(self.feature_window_end, "feature_window_end"),
        )
        if self.bar_count < 1:
            raise ValueError("bar_count must be positive")
        if not self.cumulative_volume.is_finite() or self.cumulative_volume <= _ZERO:
            raise ValueError("cumulative_volume must be positive and finite")
        if not self.vwap.is_finite() or self.vwap <= _ZERO:
            raise ValueError("vwap must be positive and finite")


def build_session_reset_vwap_feature(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    as_of: datetime,
) -> SessionResetVwapFeature:
    """Compute a cumulative typical-price VWAP from completed in-session bars.

    Bars ending after ``as_of`` are ignored.  The selected prefix must be
    complete, homogeneous, and contiguous; no missing minutes are inferred.
    """

    if not isinstance(session, SessionWindow):
        raise TypeError("session must be a SessionWindow")
    cutoff = require_utc(as_of, "as_of")
    if cutoff < session.open_ts or cutoff > session.close_ts:
        raise ValueError("as_of must remain inside the declared session")

    source = tuple(bars)
    if any(not isinstance(bar, Bar) for bar in source):
        raise TypeError("bars must contain Bar values")
    selected = tuple(
        bar
        for bar in source
        if bar.start_ts >= session.open_ts
        and bar.end_ts <= session.close_ts
        and bar.end_ts <= cutoff
    )
    _validate_selected_bars(selected, session=session)

    cumulative_volume = sum((bar.volume for bar in selected), _ZERO)
    if cumulative_volume <= _ZERO:
        raise ValueError("session VWAP requires positive cumulative volume")
    numerator = sum(
        (((bar.high + bar.low + bar.close) / _THREE) * bar.volume for bar in selected),
        _ZERO,
    )
    vwap = numerator / cumulative_volume
    return SessionResetVwapFeature(
        feature_window_end=selected[-1].end_ts,
        bar_count=len(selected),
        cumulative_volume=cumulative_volume,
        vwap=vwap,
    )


def _validate_selected_bars(bars: Sequence[Bar], *, session: SessionWindow) -> None:
    if not bars:
        raise ValueError("session VWAP requires at least one completed in-session bar")
    if bars[0].start_ts != session.open_ts:
        raise ValueError("session VWAP requires the opening bar")
    if any(not bar.complete for bar in bars):
        raise ValueError("session VWAP requires completed bars")
    first = bars[0]
    if any(
        bar.symbol != first.symbol
        or bar.market != first.market
        or bar.timeframe != first.timeframe
        for bar in bars
    ):
        raise ValueError("session VWAP bars must be homogeneous")
    if any(
        bar.start_ts < session.open_ts or bar.end_ts > session.close_ts
        for bar in bars
    ):
        raise ValueError("session VWAP bars must stay inside the declared session")
    if any(
        current.start_ts != prior.end_ts
        for prior, current in zip(bars, bars[1:], strict=False)
    ):
        raise ValueError("session VWAP bars must be contiguous")
