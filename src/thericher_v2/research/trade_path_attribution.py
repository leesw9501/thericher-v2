"""Bounded trade-path attribution from local-paper event artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from thericher_v2.contracts import SCHEMA_VERSION, Bar
from thericher_v2.execution.fill_source import (
    FillEventArtifact,
    collect_fill_source_evidence,
)
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE


@dataclass(frozen=True)
class TradePathEventArtifact:
    path: Path | None
    expected_fill_count: int
    slice_id: str
    variant_id: str
    symbol: str
    market: str = "US"

    def __post_init__(self) -> None:
        if self.expected_fill_count < 0:
            raise ValueError("expected_fill_count must be non-negative")
        if not self.slice_id:
            raise ValueError("slice_id is required")
        if not self.variant_id:
            raise ValueError("variant_id is required")
        if not self.symbol:
            raise ValueError("symbol is required")

    @property
    def label(self) -> str:
        return f"{self.slice_id}:{self.variant_id}"

    def to_fill_event_artifact(self) -> FillEventArtifact:
        return FillEventArtifact(
            path=self.path,
            expected_fill_count=self.expected_fill_count,
            label=self.label,
        )


@dataclass(frozen=True)
class TradePathAttributionResult:
    checked_at: datetime
    local_paper_verification: dict[str, Any]
    closed_segments: tuple[dict[str, Any], ...]
    open_segments: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checked_at": self.checked_at.isoformat(),
            "status": "trade_path_attributed_only",
            "local_paper_verification": self.local_paper_verification,
            "closed_segments": list(self.closed_segments),
            "open_segments": list(self.open_segments),
            "metrics": self.metrics,
            "result_scope": {
                "mode": "research_trade_path_attribution_only",
                "descriptive_only": True,
                "promotion_gate": False,
            },
        }


@dataclass(frozen=True)
class _FillLot:
    timestamp: datetime
    price: Decimal
    quantity: Decimal
    remaining_quantity: Decimal
    fee_per_unit: Decimal
    source: str


def attribute_trade_paths_from_local_paper_events(
    *,
    event_artifacts: tuple[TradePathEventArtifact, ...],
    bars: tuple[Bar, ...],
    checked_at: datetime | None = None,
) -> TradePathAttributionResult:
    """Pair local-paper buy/sell fills and return descriptive trade-path metrics."""

    checked_at = checked_at or datetime.now(UTC)
    fill_source_evidence = collect_fill_source_evidence(
        tuple(artifact.to_fill_event_artifact() for artifact in event_artifacts)
    )
    bars_by_symbol = _bars_by_symbol(bars)
    closed_segments: list[dict[str, Any]] = []
    open_segments: list[dict[str, Any]] = []
    unmatched_sell_fill_count = 0

    for event_artifact in event_artifacts:
        fills = _read_fill_events(event_artifact)
        open_lots: list[_FillLot] = []
        for fill in fills:
            source = str(fill.get("source") or "")
            if source != LOCAL_PAPER_SOURCE:
                continue
            if (
                str(fill.get("market") or "").upper() != event_artifact.market.upper()
                or str(fill.get("symbol") or "").upper() != event_artifact.symbol.upper()
            ):
                raise ValueError(
                    "local paper fill does not match trade-path artifact instrument"
                )
            side = str(fill.get("side") or "")
            quantity = _positive_decimal(fill.get("quantity"), "quantity")
            price = _positive_decimal(fill.get("price"), "price")
            fee = _non_negative_decimal(fill.get("fee", "0"), "fee")
            timestamp = _timestamp(fill.get("created_at"), "created_at")
            if side == "buy":
                open_lots.append(
                    _FillLot(
                        timestamp=timestamp,
                        price=price,
                        quantity=quantity,
                        remaining_quantity=quantity,
                        fee_per_unit=fee / quantity,
                        source=source,
                    )
                )
                continue
            if side != "sell":
                continue
            sell_remaining = quantity
            sell_fee_per_unit = fee / quantity
            while sell_remaining > 0:
                if not open_lots:
                    unmatched_sell_fill_count += 1
                    break
                entry = open_lots[0]
                segment_quantity = min(entry.remaining_quantity, sell_remaining)
                entry_fee = entry.fee_per_unit * segment_quantity
                exit_fee = sell_fee_per_unit * segment_quantity
                segment = _closed_segment_payload(
                    event_artifact=event_artifact,
                    entry=entry,
                    exit_timestamp=timestamp,
                    exit_price=price,
                    exit_source=source,
                    quantity=segment_quantity,
                    entry_fee=entry_fee,
                    exit_fee=exit_fee,
                    bars=bars_by_symbol.get(event_artifact.symbol.upper(), ()),
                )
                closed_segments.append(segment)
                remaining_quantity = entry.remaining_quantity - segment_quantity
                sell_remaining -= segment_quantity
                if remaining_quantity == 0:
                    open_lots.pop(0)
                else:
                    open_lots[0] = _FillLot(
                        timestamp=entry.timestamp,
                        price=entry.price,
                        quantity=entry.quantity,
                        remaining_quantity=remaining_quantity,
                        fee_per_unit=entry.fee_per_unit,
                        source=entry.source,
                    )
        open_segments.extend(
            _open_segment_payload(
                event_artifact=event_artifact,
                entry=entry,
                bars=bars_by_symbol.get(event_artifact.symbol.upper(), ()),
            )
            for entry in open_lots
        )

    metrics = _metrics(
        local_paper_verification=fill_source_evidence.to_summary(),
        closed_segments=tuple(closed_segments),
        open_segments=tuple(open_segments),
        unmatched_sell_fill_count=unmatched_sell_fill_count,
    )
    return TradePathAttributionResult(
        checked_at=checked_at,
        local_paper_verification=fill_source_evidence.to_summary(),
        closed_segments=tuple(closed_segments),
        open_segments=tuple(open_segments),
        metrics=metrics,
    )


def _closed_segment_payload(
    *,
    event_artifact: TradePathEventArtifact,
    entry: _FillLot,
    exit_timestamp: datetime,
    exit_price: Decimal,
    exit_source: str,
    quantity: Decimal,
    entry_fee: Decimal,
    exit_fee: Decimal,
    bars: tuple[Bar, ...],
) -> dict[str, Any]:
    gross_delta = (exit_price - entry.price) * quantity
    fee_total = entry_fee + exit_fee
    return {
        "slice_id": event_artifact.slice_id,
        "variant_id": event_artifact.variant_id,
        "symbol": event_artifact.symbol.upper(),
        "market": event_artifact.market.upper(),
        "exit_type": "sell_fill",
        "entry": {
            "timestamp": entry.timestamp.isoformat(),
            "side": "buy",
            "price": _format_decimal(entry.price),
            "quantity": _format_decimal(quantity),
            "fee": _format_decimal(entry_fee),
            "source": entry.source,
        },
        "exit": {
            "timestamp": exit_timestamp.isoformat(),
            "side": "sell",
            "price": _format_decimal(exit_price),
            "quantity": _format_decimal(quantity),
            "fee": _format_decimal(exit_fee),
            "source": exit_source,
        },
        "holding_duration_seconds": str(int((exit_timestamp - entry.timestamp).total_seconds())),
        "gross_delta": _format_decimal(gross_delta),
        "fee_total": _format_decimal(fee_total),
        "fee_aware_delta": _format_decimal(gross_delta - fee_total),
        "path_summary": _path_summary(
            bars=bars,
            start_ts=entry.timestamp,
            end_ts=exit_timestamp,
            entry_price=entry.price,
        ),
    }


def _open_segment_payload(
    *,
    event_artifact: TradePathEventArtifact,
    entry: _FillLot,
    bars: tuple[Bar, ...],
) -> dict[str, Any]:
    terminal_bar = bars[-1] if bars else None
    return {
        "slice_id": event_artifact.slice_id,
        "variant_id": event_artifact.variant_id,
        "symbol": event_artifact.symbol.upper(),
        "market": event_artifact.market.upper(),
        "exit_type": "bounded_window_end_mark",
        "entry": {
            "timestamp": entry.timestamp.isoformat(),
            "side": "buy",
            "price": _format_decimal(entry.price),
            "quantity": _format_decimal(entry.remaining_quantity),
            "source": entry.source,
        },
        "window_end": None
        if terminal_bar is None
        else {
            "timestamp": terminal_bar.start_ts.isoformat(),
            "price": _format_decimal(terminal_bar.close),
            "gross_delta": _format_decimal(
                (terminal_bar.close - entry.price) * entry.remaining_quantity
            ),
        },
        "path_summary": None
        if terminal_bar is None
        else _path_summary(
            bars=bars,
            start_ts=entry.timestamp,
            end_ts=terminal_bar.start_ts,
            entry_price=entry.price,
        ),
    }


def _read_fill_events(event_artifact: TradePathEventArtifact) -> tuple[dict[str, Any], ...]:
    if event_artifact.path is None or not event_artifact.path.exists():
        return ()
    fills: list[dict[str, Any]] = []
    for line in event_artifact.path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event_type") != "fill":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        fill = dict(payload)
        fill["created_at"] = event.get("created_at")
        fills.append(fill)
    return tuple(fills)


def _bars_by_symbol(bars: tuple[Bar, ...]) -> dict[str, tuple[Bar, ...]]:
    grouped: dict[str, list[Bar]] = {}
    for bar in bars:
        grouped.setdefault(bar.symbol.upper(), []).append(bar)
    return {
        symbol: tuple(sorted(symbol_bars, key=lambda bar: bar.start_ts))
        for symbol, symbol_bars in grouped.items()
    }


def _path_summary(
    *,
    bars: tuple[Bar, ...],
    start_ts: datetime,
    end_ts: datetime,
    entry_price: Decimal,
) -> dict[str, Any] | None:
    path_bars = tuple(bar for bar in bars if start_ts <= bar.start_ts <= end_ts)
    if not path_bars:
        return None
    low_min = min(bar.low for bar in path_bars)
    high_max = max(bar.high for bar in path_bars)
    close_end = path_bars[-1].close
    return {
        "bar_count": len(path_bars),
        "start_ts": path_bars[0].start_ts.isoformat(),
        "end_ts": path_bars[-1].start_ts.isoformat(),
        "low_min": _format_decimal(low_min),
        "high_max": _format_decimal(high_max),
        "close_end": _format_decimal(close_end),
        "adverse_delta_from_entry": _format_decimal(low_min - entry_price),
        "favorable_delta_from_entry": _format_decimal(high_max - entry_price),
    }


def _metrics(
    *,
    local_paper_verification: dict[str, Any],
    closed_segments: tuple[dict[str, Any], ...],
    open_segments: tuple[dict[str, Any], ...],
    unmatched_sell_fill_count: int,
) -> dict[str, Any]:
    fee_aware_deltas = tuple(
        _decimal(segment["fee_aware_delta"]) for segment in closed_segments
    )
    return {
        "research_trade_path_attribution_only": True,
        "descriptive_only": True,
        "promotion_gate": False,
        "closed_segment_count": len(closed_segments),
        "open_segment_count": len(open_segments),
        "unmatched_sell_fill_count": unmatched_sell_fill_count,
        "negative_fee_aware_segment_count": sum(
            1 for delta in fee_aware_deltas if delta < 0
        ),
        "non_negative_fee_aware_segment_count": sum(
            1 for delta in fee_aware_deltas if delta >= 0
        ),
        "fee_aware_delta_sum": _format_decimal(sum(fee_aware_deltas, Decimal("0"))),
        "fee_aware_delta_min": None
        if not fee_aware_deltas
        else _format_decimal(min(fee_aware_deltas)),
        "fee_aware_delta_max": None
        if not fee_aware_deltas
        else _format_decimal(max(fee_aware_deltas)),
        "local_paper_verification": local_paper_verification,
        "all_fills_local_paper": local_paper_verification.get("all_fills_local_paper")
        is True,
    }


def _timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


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
