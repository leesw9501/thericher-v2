"""Bounded diagnostic exit overlays from provided trade segments and bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from thericher_v2.contracts import SCHEMA_VERSION, Bar

DIAGNOSTIC_OVERLAY_SOURCE = "diagnostic_overlay"
DEFAULT_EXIT_OVERLAY_HORIZONS: tuple[int, int, int] = (2, 3, 5)


@dataclass(frozen=True)
class DiagnosticExitTradeSegment:
    slice_id: str
    variant_id: str
    symbol: str
    entry_timestamp: datetime
    entry_price: Decimal
    quantity: Decimal
    entry_source: str = "local_paper"
    market: str = "US"
    entry_fee: Decimal = Decimal("0")
    exit_timestamp: datetime | None = None
    exit_price: Decimal | None = None
    exit_source: str | None = "local_paper"
    exit_fee: Decimal = Decimal("0")
    bars_to_first_sell_signal: int | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.slice_id:
            raise ValueError("slice_id is required")
        if not self.variant_id:
            raise ValueError("variant_id is required")
        if not self.symbol:
            raise ValueError("symbol is required")
        if not self.entry_source:
            raise ValueError("entry_source is required")
        if self.exit_source is not None and not self.exit_source:
            raise ValueError("exit_source must be non-empty when provided")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(
            self,
            "entry_timestamp",
            self.entry_timestamp.astimezone(UTC),
        )
        if self.exit_timestamp is not None:
            object.__setattr__(
                self,
                "exit_timestamp",
                self.exit_timestamp.astimezone(UTC),
            )
        object.__setattr__(
            self,
            "entry_price",
            _positive_decimal(self.entry_price, "entry_price"),
        )
        object.__setattr__(
            self,
            "quantity",
            _positive_decimal(self.quantity, "quantity"),
        )
        object.__setattr__(
            self,
            "entry_fee",
            _non_negative_decimal(self.entry_fee, "entry_fee"),
        )
        object.__setattr__(
            self,
            "exit_fee",
            _non_negative_decimal(self.exit_fee, "exit_fee"),
        )
        if self.exit_price is not None:
            object.__setattr__(
                self,
                "exit_price",
                _positive_decimal(self.exit_price, "exit_price"),
            )
        if (self.exit_timestamp is None) != (self.exit_price is None):
            raise ValueError("exit_timestamp and exit_price must be provided together")
        if self.bars_to_first_sell_signal is not None and self.bars_to_first_sell_signal < 0:
            raise ValueError("bars_to_first_sell_signal must be non-negative")


@dataclass(frozen=True)
class ConditionalExitOverlaySpec:
    overlay_id: str
    horizon_bars: int
    min_bars_without_sell_signal: int | None = None
    adverse_delta_at_or_below: Decimal | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.overlay_id:
            raise ValueError("overlay_id is required")
        if self.horizon_bars not in DEFAULT_EXIT_OVERLAY_HORIZONS:
            raise ValueError("conditional overlay horizon must use fixed 2, 3, or 5 bars")
        if (
            self.min_bars_without_sell_signal is not None
            and self.min_bars_without_sell_signal < 0
        ):
            raise ValueError("min_bars_without_sell_signal must be non-negative")
        if self.adverse_delta_at_or_below is not None:
            object.__setattr__(
                self,
                "adverse_delta_at_or_below",
                _decimal(self.adverse_delta_at_or_below),
            )


@dataclass(frozen=True)
class DiagnosticExitOverlayResult:
    checked_at: datetime
    segments: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checked_at": self.checked_at.isoformat(),
            "status": "diagnostic_exit_overlay_only",
            "segments": list(self.segments),
            "metrics": self.metrics,
            "result_scope": {
                "mode": "research_diagnostic_exit_overlay_only",
                "descriptive_only": True,
                "promotion_gate": False,
            },
        }


def compute_diagnostic_exit_overlays(
    *,
    segments: tuple[DiagnosticExitTradeSegment, ...],
    bars: tuple[Bar, ...],
    conditional_overlays: tuple[ConditionalExitOverlaySpec, ...] = (),
    horizons: tuple[int, ...] = DEFAULT_EXIT_OVERLAY_HORIZONS,
    checked_at: datetime | None = None,
) -> DiagnosticExitOverlayResult:
    """Return descriptive exit overlays without replaying or mutating fills."""

    if horizons != DEFAULT_EXIT_OVERLAY_HORIZONS:
        raise ValueError("diagnostic exit-overlay horizons are fixed at 2, 3, and 5 bars")
    checked_at = checked_at or datetime.now(UTC)
    bars_by_symbol = _bars_by_symbol(bars)
    segment_payloads: list[dict[str, Any]] = []

    for segment in segments:
        symbol_bars = bars_by_symbol.get(segment.symbol, ())
        entry_index = _bar_index(symbol_bars, segment.entry_timestamp)
        fixed_overlays = tuple(
            _fixed_horizon_overlay(
                segment=segment,
                bars=symbol_bars,
                entry_index=entry_index,
                horizon=horizon,
            )
            for horizon in horizons
        )
        conditional_metadata = tuple(
            _conditional_overlay_metadata(
                spec=spec,
                segment=segment,
                fixed_overlays=fixed_overlays,
            )
            for spec in conditional_overlays
        )
        segment_payloads.append(
            {
                "slice_id": segment.slice_id,
                "variant_id": segment.variant_id,
                "symbol": segment.symbol,
                "market": segment.market,
                "status": "diagnostic_exit_overlay_attributed_only",
                "entry": _entry_payload(segment),
                "local_paper_exit": _local_paper_exit_payload(segment),
                "fixed_horizon_overlays": fixed_overlays,
                "conditional_overlay_metadata": conditional_metadata,
                "metrics": _segment_metrics(fixed_overlays, conditional_metadata),
            }
        )

    result_segments = tuple(segment_payloads)
    return DiagnosticExitOverlayResult(
        checked_at=checked_at,
        segments=result_segments,
        metrics=_metrics(result_segments),
    )


def _entry_payload(segment: DiagnosticExitTradeSegment) -> dict[str, Any]:
    return {
        "timestamp": segment.entry_timestamp.isoformat(),
        "side": "buy",
        "price": _format_decimal(segment.entry_price),
        "quantity": _format_decimal(segment.quantity),
        "fee": _format_decimal(segment.entry_fee),
        "source": segment.entry_source,
    }


def _local_paper_exit_payload(
    segment: DiagnosticExitTradeSegment,
) -> dict[str, Any] | None:
    if segment.exit_timestamp is None or segment.exit_price is None:
        return None
    gross_delta = (segment.exit_price - segment.entry_price) * segment.quantity
    fee_total = segment.entry_fee + segment.exit_fee
    return {
        "timestamp": segment.exit_timestamp.isoformat(),
        "side": "sell",
        "price": _format_decimal(segment.exit_price),
        "quantity": _format_decimal(segment.quantity),
        "fee": _format_decimal(segment.exit_fee),
        "source": segment.exit_source,
        "gross_delta": _format_decimal(gross_delta),
        "fee_total": _format_decimal(fee_total),
        "fee_aware_delta": _format_decimal(gross_delta - fee_total),
    }


def _fixed_horizon_overlay(
    *,
    segment: DiagnosticExitTradeSegment,
    bars: tuple[Bar, ...],
    entry_index: int | None,
    horizon: int,
) -> dict[str, Any]:
    if entry_index is None:
        return {
            "horizon_bars": horizon,
            "available": False,
            "reason": "missing_entry_bar",
            "source": DIAGNOSTIC_OVERLAY_SOURCE,
        }
    target_index = entry_index + horizon
    if target_index >= len(bars):
        return {
            "horizon_bars": horizon,
            "available": False,
            "reason": "missing_horizon_bar",
            "source": DIAGNOSTIC_OVERLAY_SOURCE,
        }
    window = bars[entry_index : target_index + 1]
    target = bars[target_index]
    low_min = min(bar.low for bar in window)
    high_max = max(bar.high for bar in window)
    close_delta = target.close - segment.entry_price
    gross_delta = close_delta * segment.quantity
    overlay = {
        "horizon_bars": horizon,
        "available": True,
        "source": DIAGNOSTIC_OVERLAY_SOURCE,
        "timestamp": target.start_ts.isoformat(),
        "price_source": "bar_close",
        "price": _format_decimal(target.close),
        "close_delta_from_entry": _format_decimal(close_delta),
        "gross_delta": _format_decimal(gross_delta),
        "low_delta_from_entry": _format_decimal(low_min - segment.entry_price),
        "high_delta_from_entry": _format_decimal(high_max - segment.entry_price),
        "fee_model": "not_applied_to_diagnostic_overlay",
    }
    if segment.exit_price is not None:
        actual_gross_delta = (segment.exit_price - segment.entry_price) * segment.quantity
        overlay["gross_delta_vs_local_paper_exit"] = _format_decimal(
            gross_delta - actual_gross_delta
        )
    return overlay


def _conditional_overlay_metadata(
    *,
    spec: ConditionalExitOverlaySpec,
    segment: DiagnosticExitTradeSegment,
    fixed_overlays: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    fixed_overlay = _fixed_overlay_for_horizon(fixed_overlays, spec.horizon_bars)
    latency_condition = _latency_condition(
        bars_to_first_sell_signal=segment.bars_to_first_sell_signal,
        min_bars=spec.min_bars_without_sell_signal,
    )
    adverse_condition = _adverse_condition(
        fixed_overlay=fixed_overlay,
        threshold=spec.adverse_delta_at_or_below,
    )
    condition_values = tuple(
        condition["met"]
        for condition in (latency_condition, adverse_condition)
        if condition["configured"]
    )
    conditions_met = (
        None
        if not condition_values or any(value is None for value in condition_values)
        else all(condition_values)
    )
    return {
        "overlay_id": spec.overlay_id,
        "horizon_bars": spec.horizon_bars,
        "source": DIAGNOSTIC_OVERLAY_SOURCE,
        "metadata_only": True,
        "conditions_met": conditions_met,
        "conditions": {
            "latency": latency_condition,
            "adverse": adverse_condition,
        },
        "referenced_fixed_overlay_available": fixed_overlay.get("available") is True,
    }


def _latency_condition(
    *,
    bars_to_first_sell_signal: int | None,
    min_bars: int | None,
) -> dict[str, Any]:
    if min_bars is None:
        return {"configured": False, "met": None}
    if bars_to_first_sell_signal is None:
        return {
            "configured": True,
            "met": None,
            "min_bars_without_sell_signal": min_bars,
            "bars_to_first_sell_signal": None,
            "reason": "sell_signal_timing_not_provided",
        }
    return {
        "configured": True,
        "met": bars_to_first_sell_signal >= min_bars,
        "min_bars_without_sell_signal": min_bars,
        "bars_to_first_sell_signal": bars_to_first_sell_signal,
    }


def _adverse_condition(
    *,
    fixed_overlay: dict[str, Any],
    threshold: Decimal | None,
) -> dict[str, Any]:
    if threshold is None:
        return {"configured": False, "met": None}
    if fixed_overlay.get("available") is not True:
        return {
            "configured": True,
            "met": None,
            "adverse_delta_at_or_below": _format_decimal(threshold),
            "reason": fixed_overlay.get("reason", "fixed_overlay_unavailable"),
        }
    low_delta = _decimal(fixed_overlay["low_delta_from_entry"])
    return {
        "configured": True,
        "met": low_delta <= threshold,
        "adverse_delta_at_or_below": _format_decimal(threshold),
        "observed_low_delta_from_entry": _format_decimal(low_delta),
    }


def _fixed_overlay_for_horizon(
    fixed_overlays: tuple[dict[str, Any], ...],
    horizon: int,
) -> dict[str, Any]:
    for overlay in fixed_overlays:
        if overlay["horizon_bars"] == horizon:
            return overlay
    raise ValueError(f"missing fixed overlay for horizon: {horizon}")


def _segment_metrics(
    fixed_overlays: tuple[dict[str, Any], ...],
    conditional_metadata: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    available = tuple(overlay for overlay in fixed_overlays if overlay["available"])
    return {
        "fixed_overlay_count": len(fixed_overlays),
        "fixed_overlay_available_count": len(available),
        "fixed_overlay_missing_horizon_count": sum(
            1
            for overlay in fixed_overlays
            if overlay.get("reason") == "missing_horizon_bar"
        ),
        "fixed_overlay_missing_entry_count": sum(
            1
            for overlay in fixed_overlays
            if overlay.get("reason") == "missing_entry_bar"
        ),
        "conditional_overlay_metadata_count": len(conditional_metadata),
    }


def _metrics(segments: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    fixed_overlays = tuple(
        overlay
        for segment in segments
        for overlay in segment["fixed_horizon_overlays"]
    )
    conditional_metadata = tuple(
        metadata
        for segment in segments
        for metadata in segment["conditional_overlay_metadata"]
    )
    return {
        "research_diagnostic_exit_overlay_only": True,
        "descriptive_only": True,
        "promotion_gate": False,
        "segment_count": len(segments),
        "fixed_overlay_count": len(fixed_overlays),
        "fixed_overlay_available_count": sum(
            1 for overlay in fixed_overlays if overlay["available"]
        ),
        "fixed_overlay_unavailable_count": sum(
            1 for overlay in fixed_overlays if not overlay["available"]
        ),
        "fixed_overlay_missing_horizon_count": sum(
            1
            for overlay in fixed_overlays
            if overlay.get("reason") == "missing_horizon_bar"
        ),
        "fixed_overlay_missing_entry_count": sum(
            1
            for overlay in fixed_overlays
            if overlay.get("reason") == "missing_entry_bar"
        ),
        "conditional_overlay_metadata_count": len(conditional_metadata),
        "all_overlay_sources_diagnostic": all(
            overlay["source"] == DIAGNOSTIC_OVERLAY_SOURCE
            for overlay in fixed_overlays + conditional_metadata
        ),
    }


def _bars_by_symbol(bars: tuple[Bar, ...]) -> dict[str, tuple[Bar, ...]]:
    grouped: dict[str, list[Bar]] = {}
    for bar in bars:
        grouped.setdefault(bar.symbol.upper(), []).append(bar)
    return {
        symbol: tuple(sorted(symbol_bars, key=lambda bar: bar.start_ts))
        for symbol, symbol_bars in grouped.items()
    }


def _bar_index(bars: tuple[Bar, ...], timestamp: datetime) -> int | None:
    normalized = timestamp.astimezone(UTC)
    for index, bar in enumerate(bars):
        if bar.start_ts == normalized:
            return index
    return None


def _positive_decimal(value: Any, field_name: str) -> Decimal:
    decimal = _decimal(value)
    if decimal <= 0:
        raise ValueError(f"{field_name} must be positive")
    return decimal


def _non_negative_decimal(value: Any, field_name: str) -> Decimal:
    decimal = _decimal(value)
    if decimal < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return decimal


def _decimal(value: Any) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("value must be a finite decimal") from exc
    if not decimal.is_finite():
        raise ValueError("value must be a finite decimal")
    return decimal


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
