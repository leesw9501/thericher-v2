"""Causal completed-bar momentum evidence for the target-position policy graph."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from thericher_v2.contracts import (
    Bar,
    ModelPrediction,
    TargetInputStatus,
    Timeframe,
    decimal_value,
    require_utc,
)
from thericher_v2.market.resample import (
    SUPPORTED_RESAMPLE_TIMEFRAMES,
    SessionWindow,
    resample_session_bars,
)

from .momentum import MomentumModel

_INPUT_STATUSES: Final = frozenset(
    {
        "ready",
        "missing",
        "stale",
        "incomplete",
        "duplicate",
        "non_contiguous",
        "misaligned",
        "future",
        "unqualified",
    }
)


@dataclass(frozen=True)
class MultiTimeframeMomentumSpec:
    """One caller-frozen completed-bar momentum expert configuration."""

    timeframe: Timeframe
    lookback: int
    buy_threshold_bps: Decimal
    sell_threshold_bps: Decimal
    model_version: str = "0.1.0"

    def __post_init__(self) -> None:
        if self.timeframe not in SUPPORTED_RESAMPLE_TIMEFRAMES:
            raise ValueError("timeframe is not supported for intraday momentum evidence")
        if not isinstance(self.lookback, int) or self.lookback < 1:
            raise ValueError("lookback must be a positive integer")
        if not self.model_version.strip():
            raise ValueError("model_version must be nonempty")
        buy_threshold_bps = decimal_value(self.buy_threshold_bps, "buy_threshold_bps")
        sell_threshold_bps = decimal_value(self.sell_threshold_bps, "sell_threshold_bps")
        if sell_threshold_bps >= buy_threshold_bps:
            raise ValueError("sell_threshold_bps must be below buy_threshold_bps")
        object.__setattr__(self, "buy_threshold_bps", buy_threshold_bps)
        object.__setattr__(self, "sell_threshold_bps", sell_threshold_bps)

    @property
    def model_id(self) -> str:
        return f"momentum_close_{self.timeframe.value}_v1"


@dataclass(frozen=True)
class MultiTimeframeMomentumConfig:
    """The explicit set of experts; there is intentionally no default strategy."""

    feature_schema_id: str
    experts: tuple[MultiTimeframeMomentumSpec, ...]

    def __post_init__(self) -> None:
        if not self.feature_schema_id.strip():
            raise ValueError("feature_schema_id must be nonempty")
        experts = tuple(self.experts)
        if not experts or any(not isinstance(item, MultiTimeframeMomentumSpec) for item in experts):
            raise ValueError("experts must contain momentum specifications")
        timeframes = tuple(item.timeframe for item in experts)
        if len(set(timeframes)) != len(timeframes):
            raise ValueError("momentum expert timeframes must be unique")
        object.__setattr__(self, "experts", experts)


@dataclass(frozen=True)
class MultiTimeframeMomentumEvidence:
    """Causal model evidence or one categorical input condition for the whole graph."""

    symbol: str
    market: str
    as_of: datetime
    input_status: TargetInputStatus
    reason: str
    predictions: tuple[ModelPrediction, ...]
    feature_window_end: datetime | None

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.market.strip() or not self.reason.strip():
            raise ValueError("evidence identifiers and reason must be nonempty")
        if self.input_status not in _INPUT_STATUSES:
            raise ValueError("evidence input_status is invalid")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))
        predictions = tuple(self.predictions)
        if self.input_status == "ready":
            if not predictions or self.feature_window_end is None:
                raise ValueError("ready evidence must have predictions and a feature window end")
            if any(
                prediction.symbol != self.symbol
                or prediction.market != self.market
                or prediction.feature_window_end > self.as_of
                for prediction in predictions
            ):
                raise ValueError("ready evidence predictions are misaligned")
            if len({prediction.signal.timeframe for prediction in predictions}) != len(predictions):
                raise ValueError("ready evidence timeframes must be unique")
        elif predictions or self.feature_window_end is not None:
            raise ValueError("unready evidence cannot retain model predictions")
        object.__setattr__(self, "predictions", predictions)
        if self.feature_window_end is not None:
            object.__setattr__(
                self,
                "feature_window_end",
                require_utc(self.feature_window_end, "feature_window_end"),
            )


def build_multitimeframe_momentum_evidence(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    config: MultiTimeframeMomentumConfig,
    as_of: datetime,
) -> MultiTimeframeMomentumEvidence:
    """Build only causal predictions from one session's completed 1m source bars."""

    if not isinstance(session, SessionWindow):
        raise TypeError("session must be a SessionWindow")
    if not isinstance(config, MultiTimeframeMomentumConfig):
        raise TypeError("config must be a MultiTimeframeMomentumConfig")
    now = require_utc(as_of, "as_of")
    if now < session.open_ts or now > session.close_ts:
        raise ValueError("as_of must remain inside the declared session")
    source_bars, source_status = _source_bars_before_as_of(bars, session=session, as_of=now)
    if source_status is not None:
        return _unready_evidence(source_bars, now, source_status, f"source_{source_status}")

    symbol = source_bars[0].symbol
    market = source_bars[0].market
    predictions: list[ModelPrediction] = []
    for spec in config.experts:
        resampled = resample_session_bars(source_bars, spec.timeframe, session=session).bars
        expected_end = _last_expected_completed_bucket_end(
            session=session,
            timeframe=spec.timeframe,
            as_of=now,
        )
        if expected_end is None:
            return _unready_evidence(source_bars, now, "missing", f"missing_{spec.timeframe.value}")
        candidate = tuple(bar for bar in resampled if bar.end_ts <= expected_end)
        if not candidate or candidate[-1].end_ts != expected_end:
            return _unready_evidence(
                source_bars,
                now,
                "incomplete",
                f"incomplete_{spec.timeframe.value}",
            )
        required_count = spec.lookback + 1
        if len(candidate) < required_count:
            return _unready_evidence(
                source_bars,
                now,
                "missing",
                f"missing_{spec.timeframe.value}",
            )
        window = candidate[-required_count:]
        if any(
            current.start_ts != prior.end_ts
            for prior, current in zip(window, window[1:], strict=False)
        ):
            return _unready_evidence(
                source_bars,
                now,
                "non_contiguous",
                f"non_contiguous_{spec.timeframe.value}",
            )
        model = MomentumModel(
            model_id=spec.model_id,
            model_version=spec.model_version,
            lookback=spec.lookback,
            buy_threshold_bps=spec.buy_threshold_bps,
            sell_threshold_bps=spec.sell_threshold_bps,
        )
        predictions.append(model.predict(list(window)))
    return MultiTimeframeMomentumEvidence(
        symbol=symbol,
        market=market,
        as_of=now,
        input_status="ready",
        reason="completed_bar_momentum_evidence",
        predictions=tuple(predictions),
        feature_window_end=max(item.feature_window_end for item in predictions),
    )


def _source_bars_before_as_of(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    as_of: datetime,
) -> tuple[tuple[Bar, ...], TargetInputStatus | None]:
    source = tuple(bar for bar in bars if isinstance(bar, Bar) and bar.end_ts <= as_of)
    if len(source) != len(tuple(bars)):
        invalid_values = tuple(bar for bar in bars if not isinstance(bar, Bar))
        if invalid_values:
            raise TypeError("bars must contain Bar values")
    if not source:
        return (), "missing"
    ordered = tuple(sorted(source, key=lambda bar: bar.start_ts))
    first = ordered[0]
    if any(
        bar.symbol != first.symbol
        or bar.market != first.market
        or bar.timeframe != Timeframe.M1
        or bar.start_ts < session.open_ts
        or bar.end_ts > session.close_ts
        for bar in ordered
    ):
        return ordered, "misaligned"
    if any(not bar.complete for bar in ordered):
        return ordered, "incomplete"
    if any(
        current.start_ts == prior.start_ts
        for prior, current in zip(ordered, ordered[1:], strict=False)
    ):
        return ordered, "duplicate"
    return ordered, None


def _last_expected_completed_bucket_end(
    *,
    session: SessionWindow,
    timeframe: Timeframe,
    as_of: datetime,
) -> datetime | None:
    completed_bucket_count = (as_of - session.open_ts) // timeframe.duration
    if completed_bucket_count <= 0:
        return None
    return session.open_ts + timeframe.duration * completed_bucket_count


def _unready_evidence(
    source_bars: Sequence[Bar],
    as_of: datetime,
    input_status: TargetInputStatus,
    reason: str,
) -> MultiTimeframeMomentumEvidence:
    symbol = source_bars[0].symbol if source_bars else "UNKNOWN"
    market = source_bars[0].market if source_bars else "US"
    return MultiTimeframeMomentumEvidence(
        symbol=symbol,
        market=market,
        as_of=as_of,
        input_status=input_status,
        reason=reason,
        predictions=(),
        feature_window_end=None,
    )
