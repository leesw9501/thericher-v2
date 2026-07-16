"""Bounded entry-quality diagnostics from probability traces and bars."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from thericher_v2.contracts import SCHEMA_VERSION, Bar

DEFAULT_ENTRY_QUALITY_HORIZONS: tuple[int, int, int] = (5, 15, 30)


@dataclass(frozen=True)
class EntryQualityTraceEntry:
    offset: int
    probability: float
    signal_bar_start: datetime
    signal_bar_end: datetime
    execution_bar_start: datetime
    execution_bar_end: datetime
    signal_close: Decimal
    execution_open: Decimal
    execution_close: Decimal
    contiguous: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("offset must be non-negative")
        if not math.isfinite(self.probability) or not 0 <= self.probability <= 1:
            raise ValueError("probability must be finite and between 0 and 1")
        object.__setattr__(
            self,
            "signal_bar_start",
            self.signal_bar_start.astimezone(UTC),
        )
        object.__setattr__(self, "signal_bar_end", self.signal_bar_end.astimezone(UTC))
        object.__setattr__(
            self,
            "execution_bar_start",
            self.execution_bar_start.astimezone(UTC),
        )
        object.__setattr__(
            self,
            "execution_bar_end",
            self.execution_bar_end.astimezone(UTC),
        )
        object.__setattr__(self, "signal_close", _decimal(self.signal_close))
        object.__setattr__(self, "execution_open", _decimal(self.execution_open))
        object.__setattr__(self, "execution_close", _decimal(self.execution_close))


@dataclass(frozen=True)
class EntryQualityEntryFill:
    timestamp: datetime
    price: Decimal
    quantity: Decimal
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))
        object.__setattr__(self, "price", _positive_decimal(self.price, "price"))
        object.__setattr__(
            self,
            "quantity",
            _positive_decimal(self.quantity, "quantity"),
        )
        if not self.source:
            raise ValueError("source is required")


@dataclass(frozen=True)
class EntryQualityVariant:
    slice_id: str
    variant_id: str
    symbol: str
    buy_threshold: float
    sell_threshold: float
    entry_fills: tuple[EntryQualityEntryFill, ...] = ()
    market: str = "US"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.slice_id:
            raise ValueError("slice_id is required")
        if not self.variant_id:
            raise ValueError("variant_id is required")
        if not self.symbol:
            raise ValueError("symbol is required")
        if not 0 < self.sell_threshold < self.buy_threshold < 1:
            raise ValueError("thresholds must satisfy 0 < sell < buy < 1")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())


@dataclass(frozen=True)
class EntryQualityDiagnosticResult:
    checked_at: datetime
    local_paper_verification: Mapping[str, Any]
    variants: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checked_at": self.checked_at.isoformat(),
            "status": "entry_quality_diagnostic_only",
            "local_paper_verification": dict(self.local_paper_verification),
            "variants": list(self.variants),
            "metrics": self.metrics,
            "result_scope": {
                "mode": "research_entry_quality_diagnostic_only",
                "descriptive_only": True,
                "promotion_gate": False,
            },
        }


def attribute_entry_quality_from_traces(
    *,
    trace_entries_by_slice: Mapping[str, tuple[EntryQualityTraceEntry, ...]],
    variants: tuple[EntryQualityVariant, ...],
    bars: tuple[Bar, ...],
    local_paper_verification: Mapping[str, Any],
    horizons: tuple[int, ...] = DEFAULT_ENTRY_QUALITY_HORIZONS,
    checked_at: datetime | None = None,
) -> EntryQualityDiagnosticResult:
    """Return descriptive entry-quality diagnostics without replaying execution."""

    if horizons != DEFAULT_ENTRY_QUALITY_HORIZONS:
        raise ValueError("entry-quality horizons are fixed at 5, 15, and 30 bars")
    checked_at = checked_at or datetime.now(UTC)
    bars_by_symbol = _bars_by_symbol(bars)
    variant_payloads: list[dict[str, Any]] = []
    for variant in variants:
        entries = trace_entries_by_slice.get(variant.slice_id)
        if entries is None:
            raise ValueError(f"missing trace entries for slice: {variant.slice_id}")
        symbol_bars = bars_by_symbol.get(variant.symbol)
        if not symbol_bars:
            raise ValueError(f"missing bars for symbol: {variant.symbol}")
        opportunities = tuple(
            entry for entry in entries if entry.probability >= variant.buy_threshold
        )
        observations = tuple(
            _opportunity_payload(
                variant=variant,
                entry=entry,
                entries=entries,
                bars=symbol_bars,
                horizons=horizons,
            )
            for entry in opportunities
        )
        variant_payloads.append(
            {
                "slice_id": variant.slice_id,
                "variant_id": variant.variant_id,
                "symbol": variant.symbol,
                "market": variant.market,
                "buy_threshold": f"{variant.buy_threshold:.6f}",
                "sell_threshold": f"{variant.sell_threshold:.6f}",
                "status": "entry_quality_attributed_only",
                "reason": "buy opportunities attributed from provided trace and bars",
                "buy_opportunity_count": len(observations),
                "entered_opportunity_count": sum(
                    1 for observation in observations if observation["entered"]
                ),
                "observations": observations,
                "metrics": _variant_metrics(observations, horizons),
            }
        )
    metrics = _metrics(
        variants=tuple(variant_payloads),
        horizons=horizons,
        local_paper_verification=local_paper_verification,
    )
    return EntryQualityDiagnosticResult(
        checked_at=checked_at,
        local_paper_verification=local_paper_verification,
        variants=tuple(variant_payloads),
        metrics=metrics,
    )


def _opportunity_payload(
    *,
    variant: EntryQualityVariant,
    entry: EntryQualityTraceEntry,
    entries: tuple[EntryQualityTraceEntry, ...],
    bars: tuple[Bar, ...],
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    bar_index = _bar_index_for_execution(bars, entry.execution_bar_start)
    fill = _matching_fill(variant.entry_fills, entry.execution_bar_start)
    reference_price = entry.execution_open if fill is None else fill.price
    path = _path_summary(
        bars=bars[bar_index:],
        reference_price=reference_price,
    )
    sell_signal = _first_sell_signal(
        entries=entries,
        offset=entry.offset,
        sell_threshold=variant.sell_threshold,
    )
    adverse_ts = None if path is None else _timestamp(path["adverse_extreme_timestamp"])
    return {
        "slice_id": variant.slice_id,
        "variant_id": variant.variant_id,
        "symbol": variant.symbol,
        "market": variant.market,
        "entered": fill is not None,
        "evidence_sources": {
            "decision": "probability_trace",
            "path": "diagnostic_overlay",
            "fill": None if fill is None else fill.source,
        },
        "trace": {
            "offset": entry.offset,
            "probability": f"{entry.probability:.8f}",
            "signal_bar_end": entry.signal_bar_end.isoformat(),
            "execution_bar_start": entry.execution_bar_start.isoformat(),
            "contiguous": entry.contiguous,
        },
        "entry_reference": {
            "timestamp": entry.execution_bar_start.isoformat(),
            "price": _format_decimal(reference_price),
            "price_source": "trace_execution_open"
            if fill is None
            else "local_paper_fill",
        },
        "local_paper_entry_fill": None if fill is None else _fill_payload(fill),
        "forward_horizon_marks": tuple(
            _horizon_mark(
                bars=bars,
                start_index=bar_index,
                horizon=horizon,
                reference_price=reference_price,
            )
            for horizon in horizons
        ),
        "bounded_path": path,
        "sell_threshold_timing": {
            "sell_signal_after_opportunity": sell_signal is not None,
            "first_sell_signal": sell_signal,
            "sell_signal_before_bounded_adverse_extreme": (
                False
                if sell_signal is None or adverse_ts is None
                else _timestamp(sell_signal["signal_bar_end"]) <= adverse_ts
            ),
            "sell_signal_source": None
            if sell_signal is None
            else "probability_trace",
        },
    }


def _fill_payload(fill: EntryQualityEntryFill) -> dict[str, Any]:
    return {
        "timestamp": fill.timestamp.isoformat(),
        "price": _format_decimal(fill.price),
        "quantity": _format_decimal(fill.quantity),
        "source": fill.source,
    }


def _horizon_mark(
    *,
    bars: tuple[Bar, ...],
    start_index: int,
    horizon: int,
    reference_price: Decimal,
) -> dict[str, Any]:
    target_index = start_index + horizon
    if target_index >= len(bars):
        return {
            "horizon_bars": horizon,
            "available": False,
            "source": "diagnostic_overlay",
        }
    window = bars[start_index : target_index + 1]
    target = bars[target_index]
    low_min = min(bar.low for bar in window)
    high_max = max(bar.high for bar in window)
    return {
        "horizon_bars": horizon,
        "available": True,
        "source": "diagnostic_overlay",
        "timestamp": target.start_ts.isoformat(),
        "close": _format_decimal(target.close),
        "close_delta": _format_decimal(target.close - reference_price),
        "low_delta": _format_decimal(low_min - reference_price),
        "high_delta": _format_decimal(high_max - reference_price),
    }


def _path_summary(
    *,
    bars: tuple[Bar, ...],
    reference_price: Decimal,
) -> dict[str, Any] | None:
    if not bars:
        return None
    adverse_bar = min(bars, key=lambda bar: (bar.low, bar.start_ts))
    favorable_bar = max(bars, key=lambda bar: (bar.high, -bar.start_ts.timestamp()))
    terminal_bar = bars[-1]
    return {
        "source": "diagnostic_overlay",
        "bar_count": len(bars),
        "start_ts": bars[0].start_ts.isoformat(),
        "end_ts": terminal_bar.start_ts.isoformat(),
        "reference_price": _format_decimal(reference_price),
        "adverse_delta_from_reference": _format_decimal(
            adverse_bar.low - reference_price
        ),
        "adverse_extreme_timestamp": adverse_bar.start_ts.isoformat(),
        "favorable_delta_from_reference": _format_decimal(
            favorable_bar.high - reference_price
        ),
        "favorable_extreme_timestamp": favorable_bar.start_ts.isoformat(),
        "window_end_close_delta": _format_decimal(terminal_bar.close - reference_price),
    }


def _first_sell_signal(
    *,
    entries: tuple[EntryQualityTraceEntry, ...],
    offset: int,
    sell_threshold: float,
) -> dict[str, Any] | None:
    for entry in sorted(entries, key=lambda item: item.offset):
        if entry.offset <= offset:
            continue
        if entry.probability > sell_threshold:
            continue
        return {
            "offset": entry.offset,
            "probability": f"{entry.probability:.8f}",
            "signal_bar_end": entry.signal_bar_end.isoformat(),
            "execution_bar_start": entry.execution_bar_start.isoformat(),
            "bars_after_opportunity": entry.offset - offset,
            "contiguous": entry.contiguous,
        }
    return None


def _variant_metrics(
    observations: tuple[dict[str, Any], ...],
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    return {
        "buy_opportunity_count": len(observations),
        "entered_opportunity_count": sum(
            1 for observation in observations if observation["entered"]
        ),
        "sell_signal_after_opportunity_count": sum(
            1
            for observation in observations
            if observation["sell_threshold_timing"]["sell_signal_after_opportunity"]
        ),
        "sell_signal_before_bounded_adverse_extreme_count": sum(
            1
            for observation in observations
            if observation["sell_threshold_timing"][
                "sell_signal_before_bounded_adverse_extreme"
            ]
        ),
        "horizon_marks": {
            str(horizon): _horizon_metrics(observations, horizon)
            for horizon in horizons
        },
    }


def _metrics(
    *,
    variants: tuple[dict[str, Any], ...],
    horizons: tuple[int, ...],
    local_paper_verification: Mapping[str, Any],
) -> dict[str, Any]:
    observations = tuple(
        observation
        for variant in variants
        for observation in variant["observations"]
    )
    return {
        "research_entry_quality_diagnostic_only": True,
        "descriptive_only": True,
        "promotion_gate": False,
        "variant_count": len(variants),
        "buy_opportunity_count_total": len(observations),
        "entered_opportunity_count_total": sum(
            1 for observation in observations if observation["entered"]
        ),
        "diagnostic_overlay_observation_count": len(observations),
        "sell_signal_after_opportunity_count": sum(
            1
            for observation in observations
            if observation["sell_threshold_timing"]["sell_signal_after_opportunity"]
        ),
        "sell_signal_before_bounded_adverse_extreme_count": sum(
            1
            for observation in observations
            if observation["sell_threshold_timing"][
                "sell_signal_before_bounded_adverse_extreme"
            ]
        ),
        "buy_opportunity_count_by_slice": _count_by(
            observations,
            key="slice_id",
        ),
        "buy_opportunity_count_by_variant": {
            f"{variant['slice_id']}:{variant['variant_id']}": variant[
                "buy_opportunity_count"
            ]
            for variant in variants
        },
        "horizon_marks": {
            str(horizon): _horizon_metrics(observations, horizon)
            for horizon in horizons
        },
        "local_paper_verification": dict(local_paper_verification),
        "all_fills_local_paper": local_paper_verification.get("all_fills_local_paper")
        is True,
    }


def _horizon_metrics(
    observations: tuple[dict[str, Any], ...],
    horizon: int,
) -> dict[str, int]:
    marks = tuple(
        mark
        for observation in observations
        for mark in observation["forward_horizon_marks"]
        if mark["horizon_bars"] == horizon
    )
    available = tuple(mark for mark in marks if mark["available"])
    return {
        "available_count": len(available),
        "unavailable_count": len(marks) - len(available),
        "negative_close_delta_count": sum(
            1 for mark in available if _decimal(mark["close_delta"]) < 0
        ),
        "non_negative_close_delta_count": sum(
            1 for mark in available if _decimal(mark["close_delta"]) >= 0
        ),
    }


def _count_by(observations: tuple[dict[str, Any], ...], *, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for observation in observations:
        value = str(observation[key])
        counts[value] = counts.get(value, 0) + 1
    return counts


def _bars_by_symbol(bars: tuple[Bar, ...]) -> dict[str, tuple[Bar, ...]]:
    grouped: dict[str, list[Bar]] = {}
    for bar in bars:
        grouped.setdefault(bar.symbol.upper(), []).append(bar)
    return {
        symbol: tuple(sorted(symbol_bars, key=lambda bar: bar.start_ts))
        for symbol, symbol_bars in grouped.items()
    }


def _bar_index_for_execution(bars: tuple[Bar, ...], execution_ts: datetime) -> int:
    normalized = execution_ts.astimezone(UTC)
    for index, bar in enumerate(bars):
        if bar.start_ts == normalized:
            return index
    raise ValueError(f"missing execution bar for timestamp: {normalized.isoformat()}")


def _matching_fill(
    fills: tuple[EntryQualityEntryFill, ...],
    execution_ts: datetime,
) -> EntryQualityEntryFill | None:
    normalized = execution_ts.astimezone(UTC)
    for fill in fills:
        if fill.timestamp == normalized:
            return fill
    return None


def _positive_decimal(value: Any, field_name: str) -> Decimal:
    decimal = _decimal(value)
    if decimal <= 0:
        raise ValueError(f"{field_name} must be positive")
    return decimal


def _decimal(value: Any) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("value must be a finite decimal") from exc
    if not decimal.is_finite():
        raise ValueError("value must be a finite decimal")
    return decimal


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp is required")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
