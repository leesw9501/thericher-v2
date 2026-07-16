from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.entry_quality_diagnostic import (
    EntryQualityEntryFill,
    EntryQualityTraceEntry,
    EntryQualityVariant,
    attribute_entry_quality_from_traces,
)


def test_entry_quality_diagnostic_marks_entered_opportunity_and_sell_timing() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    bars = tuple(
        _bar("AAA", start + timedelta(minutes=index), close=100 - index / 10)
        for index in range(40)
    )
    buy_entry = _trace_entry(
        offset=0,
        probability=0.82,
        signal_end=start + timedelta(minutes=2),
        execution_start=start + timedelta(minutes=2),
    )
    sell_entry = _trace_entry(
        offset=2,
        probability=0.30,
        signal_end=start + timedelta(minutes=4),
        execution_start=start + timedelta(minutes=4),
    )

    result = attribute_entry_quality_from_traces(
        trace_entries_by_slice={"aaa": (buy_entry, sell_entry)},
        variants=(
            EntryQualityVariant(
                slice_id="aaa",
                variant_id="t01",
                symbol="AAA",
                buy_threshold=0.80,
                sell_threshold=0.40,
                entry_fills=(
                    EntryQualityEntryFill(
                        timestamp=start + timedelta(minutes=2),
                        price=Decimal("99.80"),
                        quantity=Decimal("1"),
                        source=LOCAL_PAPER_SOURCE,
                    ),
                ),
            ),
        ),
        bars=bars,
        local_paper_verification={"all_fills_local_paper": True},
        checked_at=start,
    )

    observation = result.variants[0]["observations"][0]
    assert result.metrics["buy_opportunity_count_total"] == 1
    assert result.metrics["entered_opportunity_count_total"] == 1
    assert result.metrics["horizon_marks"]["5"]["available_count"] == 1
    assert result.metrics["horizon_marks"]["5"]["negative_close_delta_count"] == 1
    assert result.metrics["sell_signal_after_opportunity_count"] == 1
    assert result.metrics["sell_signal_before_bounded_adverse_extreme_count"] == 1
    assert observation["entered"] is True
    assert observation["evidence_sources"]["path"] == "diagnostic_overlay"
    assert observation["evidence_sources"]["fill"] == LOCAL_PAPER_SOURCE
    assert observation["sell_threshold_timing"]["first_sell_signal"]["offset"] == 2
    assert result.to_payload()["result_scope"]["mode"] == "research_entry_quality_diagnostic_only"


def test_entry_quality_diagnostic_counts_non_entered_opportunities_and_fixed_horizons() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    bars = tuple(
        _bar("AAA", start + timedelta(minutes=index), close=100 + index / 10)
        for index in range(40)
    )
    trace = (
        _trace_entry(
            offset=0,
            probability=0.90,
            signal_end=start + timedelta(minutes=2),
            execution_start=start + timedelta(minutes=2),
        ),
    )
    variant = EntryQualityVariant(
        slice_id="aaa",
        variant_id="t01",
        symbol="AAA",
        buy_threshold=0.80,
        sell_threshold=0.40,
    )

    result = attribute_entry_quality_from_traces(
        trace_entries_by_slice={"aaa": trace},
        variants=(variant,),
        bars=bars,
        local_paper_verification={"all_fills_local_paper": True},
        checked_at=start,
    )

    assert result.variants[0]["entered_opportunity_count"] == 0
    assert result.metrics["horizon_marks"]["30"]["available_count"] == 1
    assert result.metrics["horizon_marks"]["30"]["non_negative_close_delta_count"] == 1
    with pytest.raises(ValueError, match="fixed"):
        attribute_entry_quality_from_traces(
            trace_entries_by_slice={"aaa": trace},
            variants=(variant,),
            bars=bars,
            local_paper_verification={"all_fills_local_paper": True},
            horizons=(5, 15),
            checked_at=start,
        )


def test_entry_quality_diagnostic_requires_execution_bar() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    trace = (
        _trace_entry(
            offset=0,
            probability=0.90,
            signal_end=start + timedelta(minutes=10),
            execution_start=start + timedelta(minutes=10),
        ),
    )

    with pytest.raises(ValueError, match="missing execution bar"):
        attribute_entry_quality_from_traces(
            trace_entries_by_slice={"aaa": trace},
            variants=(
                EntryQualityVariant(
                    slice_id="aaa",
                    variant_id="t01",
                    symbol="AAA",
                    buy_threshold=0.80,
                    sell_threshold=0.40,
                ),
            ),
            bars=(_bar("AAA", start, close=100),),
            local_paper_verification={"all_fills_local_paper": True},
            checked_at=start,
        )


def test_entry_quality_diagnostic_is_offline_and_does_not_read_credentials(
    monkeypatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("entry-quality diagnostic must not open network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("entry-quality diagnostic must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    result = attribute_entry_quality_from_traces(
        trace_entries_by_slice={
            "aaa": (
                _trace_entry(
                    offset=0,
                    probability=0.90,
                    signal_end=start + timedelta(minutes=1),
                    execution_start=start + timedelta(minutes=1),
                ),
            )
        },
        variants=(
            EntryQualityVariant(
                slice_id="aaa",
                variant_id="t01",
                symbol="AAA",
                buy_threshold=0.80,
                sell_threshold=0.40,
            ),
        ),
        bars=tuple(
            _bar("AAA", start + timedelta(minutes=index), close=100)
            for index in range(40)
        ),
        local_paper_verification={"all_fills_local_paper": True},
        checked_at=start,
    )

    assert result.metrics["buy_opportunity_count_total"] == 1


def _trace_entry(
    *,
    offset: int,
    probability: float,
    signal_end: datetime,
    execution_start: datetime,
) -> EntryQualityTraceEntry:
    return EntryQualityTraceEntry(
        offset=offset,
        probability=probability,
        signal_bar_start=signal_end - timedelta(minutes=1),
        signal_bar_end=signal_end,
        execution_bar_start=execution_start,
        execution_bar_end=execution_start + timedelta(minutes=1),
        signal_close=Decimal("100"),
        execution_open=Decimal("100"),
        execution_close=Decimal("100"),
    )


def _bar(symbol: str, start_ts: datetime, *, close: float | int) -> Bar:
    close_decimal = Decimal(str(close))
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=close_decimal,
        high=close_decimal + Decimal("0.50"),
        low=close_decimal - Decimal("0.50"),
        close=close_decimal,
        volume=Decimal("100"),
    )
