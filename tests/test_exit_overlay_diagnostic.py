from __future__ import annotations

import socket
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.exit_overlay_diagnostic import (
    DIAGNOSTIC_OVERLAY_SOURCE,
    ConditionalExitOverlaySpec,
    DiagnosticExitTradeSegment,
    ExitLatencySandboxSegment,
    ExitLatencySignalRecord,
    compute_diagnostic_exit_composite,
    compute_diagnostic_exit_overlays,
    compute_exit_latency_sandbox_marks,
)


def test_exit_overlay_fixed_horizons_use_provided_bars_and_sources() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    bars = tuple(
        _bar("AAA", start + timedelta(minutes=index), low=close - 1, close=close)
        for index, close in enumerate((100, 101, 100, 103, 104, 99, 107))
    )
    segment = DiagnosticExitTradeSegment(
        slice_id="aaa_slice",
        variant_id="t01",
        symbol="AAA",
        entry_timestamp=start + timedelta(minutes=1),
        entry_price=Decimal("101"),
        quantity=Decimal("2"),
        exit_timestamp=start + timedelta(minutes=4),
        exit_price=Decimal("104"),
        exit_fee=Decimal("0.02"),
    )

    result = compute_diagnostic_exit_overlays(
        segments=(segment,),
        bars=bars,
        checked_at=start,
    )

    overlays = result.segments[0]["fixed_horizon_overlays"]
    horizon_two = overlays[0]
    assert tuple(overlay["horizon_bars"] for overlay in overlays) == (2, 3, 5)
    assert horizon_two["source"] == DIAGNOSTIC_OVERLAY_SOURCE
    assert horizon_two["timestamp"] == (start + timedelta(minutes=3)).isoformat()
    assert horizon_two["price"] == "103"
    assert horizon_two["gross_delta"] == "4"
    assert horizon_two["gross_delta_vs_local_paper_exit"] == "-2"
    assert result.metrics["all_overlay_sources_diagnostic"] is True
    assert result.to_payload()["result_scope"]["mode"] == (
        "research_diagnostic_exit_overlay_only"
    )


def test_exit_overlay_missing_horizon_is_reported_without_failure() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    result = compute_diagnostic_exit_overlays(
        segments=(
            DiagnosticExitTradeSegment(
                slice_id="aaa_slice",
                variant_id="t01",
                symbol="AAA",
                entry_timestamp=start + timedelta(minutes=1),
                entry_price=Decimal("101"),
                quantity=Decimal("1"),
            ),
        ),
        bars=tuple(
            _bar("AAA", start + timedelta(minutes=index), low=100, close=101)
            for index in range(4)
        ),
        checked_at=start,
    )

    overlays = result.segments[0]["fixed_horizon_overlays"]
    assert overlays[0]["available"] is True
    assert overlays[1]["available"] is False
    assert overlays[1]["reason"] == "missing_horizon_bar"
    assert overlays[2]["available"] is False
    assert overlays[2]["reason"] == "missing_horizon_bar"
    assert result.metrics["fixed_overlay_missing_horizon_count"] == 2


def test_exit_overlay_keeps_local_paper_segment_sources_unchanged() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    segment = DiagnosticExitTradeSegment(
        slice_id="aaa_slice",
        variant_id="t01",
        symbol="AAA",
        entry_timestamp=start,
        entry_price=Decimal("10.00"),
        quantity=Decimal("1"),
        entry_fee=Decimal("0.01"),
        entry_source=LOCAL_PAPER_SOURCE,
        exit_timestamp=start + timedelta(minutes=2),
        exit_price=Decimal("10.20"),
        exit_source=LOCAL_PAPER_SOURCE,
        exit_fee=Decimal("0.01"),
    )
    before = deepcopy(segment)

    result = compute_diagnostic_exit_overlays(
        segments=(segment,),
        bars=tuple(
            _bar("AAA", start + timedelta(minutes=index), low=9, close=10 + index / 10)
            for index in range(8)
        ),
        checked_at=start,
    )

    assert segment == before
    assert result.segments[0]["entry"]["source"] == LOCAL_PAPER_SOURCE
    assert result.segments[0]["local_paper_exit"]["source"] == LOCAL_PAPER_SOURCE
    assert result.segments[0]["fixed_horizon_overlays"][0]["source"] == (
        DIAGNOSTIC_OVERLAY_SOURCE
    )


def test_exit_overlay_conditional_metadata_does_not_select_policy() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    result = compute_diagnostic_exit_overlays(
        segments=(
            DiagnosticExitTradeSegment(
                slice_id="aaa_slice",
                variant_id="t01",
                symbol="AAA",
                entry_timestamp=start,
                entry_price=Decimal("10"),
                quantity=Decimal("1"),
                bars_to_first_sell_signal=7,
            ),
        ),
        bars=tuple(
            _bar("AAA", start + timedelta(minutes=index), low=10 - index, close=10)
            for index in range(8)
        ),
        conditional_overlays=(
            ConditionalExitOverlaySpec(
                overlay_id="latency_adverse_probe",
                horizon_bars=2,
                min_bars_without_sell_signal=5,
                adverse_delta_at_or_below=Decimal("-1"),
            ),
        ),
        checked_at=start,
    )

    metadata = result.segments[0]["conditional_overlay_metadata"][0]
    assert metadata["source"] == DIAGNOSTIC_OVERLAY_SOURCE
    assert metadata["metadata_only"] is True
    assert metadata["conditions_met"] is True
    assert "selected" not in metadata
    assert "recommendation" not in metadata


def test_exit_overlay_horizons_are_fixed() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    with pytest.raises(ValueError, match="fixed"):
        compute_diagnostic_exit_overlays(
            segments=(
                DiagnosticExitTradeSegment(
                    slice_id="aaa_slice",
                    variant_id="t01",
                    symbol="AAA",
                    entry_timestamp=start,
                    entry_price=Decimal("10"),
                    quantity=Decimal("1"),
                ),
            ),
            bars=tuple(
                _bar("AAA", start + timedelta(minutes=index), low=9, close=10)
                for index in range(8)
            ),
            horizons=(2, 5),
            checked_at=start,
        )


def test_exit_overlay_is_offline_and_does_not_read_credentials(monkeypatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("exit overlay diagnostic must not open network")

    def fail_read_text(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("exit overlay diagnostic must not read files")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", fail_read_text)

    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    result = compute_diagnostic_exit_overlays(
        segments=(
            DiagnosticExitTradeSegment(
                slice_id="aaa_slice",
                variant_id="t01",
                symbol="AAA",
                entry_timestamp=start,
                entry_price=Decimal("10"),
                quantity=Decimal("1"),
            ),
        ),
        bars=tuple(
            _bar("AAA", start + timedelta(minutes=index), low=9, close=10)
            for index in range(8)
        ),
        checked_at=start,
    )

    assert result.metrics["segment_count"] == 1


def test_exit_composite_substitutes_diagnostic_and_retains_local_paper() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    overlay_segments = _composite_overlay_segments(start)

    result = compute_diagnostic_exit_composite(
        segments=overlay_segments,
        condition_overlay_id="latency_ge_5_at_2_bar",
        fixed_horizon_bars=2,
        checked_at=start,
    )

    loss = result.segments[0]
    non_negative = result.segments[1]
    assert loss["condition_met"] is True
    assert loss["composite_status"] == "diagnostic_overlay_substituted"
    assert loss["composite_outcome"]["source"] == DIAGNOSTIC_OVERLAY_SOURCE
    assert non_negative["condition_met"] is False
    assert non_negative["composite_status"] == "condition_not_met_retained_local_paper"
    assert non_negative["composite_outcome"]["source"] == LOCAL_PAPER_SOURCE
    assert result.group_summaries["loss_bearing"]["condition_met_count"] == 1
    assert result.group_summaries["non_negative"]["condition_met_count"] == 0
    assert result.metrics["substituted_outcomes_are_diagnostic_overlay"] is True
    assert result.metrics["retained_outcomes_are_local_paper"] is True
    assert result.to_payload()["result_scope"]["mode"] == (
        "research_diagnostic_exit_composite_only"
    )


def test_exit_composite_does_not_mutate_provided_payloads() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    overlay_segments = _composite_overlay_segments(start)
    before = deepcopy(overlay_segments)

    compute_diagnostic_exit_composite(
        segments=overlay_segments,
        condition_overlay_id="latency_ge_5_at_2_bar",
        fixed_horizon_bars=2,
        checked_at=start,
    )

    assert overlay_segments == before


def test_exit_composite_reports_missing_condition_and_fixed_overlay_offline(
    monkeypatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("exit composite diagnostic must not open network")

    def fail_read_text(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("exit composite diagnostic must not read files")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", fail_read_text)

    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    overlay_segments = _composite_overlay_segments(start)

    missing_condition = compute_diagnostic_exit_composite(
        segments=(overlay_segments[0],),
        condition_overlay_id="missing_condition",
        fixed_horizon_bars=2,
        checked_at=start,
    )

    assert missing_condition.metrics["missing_condition_count"] == 1
    assert missing_condition.segments[0]["composite_outcome"]["source"] == (
        LOCAL_PAPER_SOURCE
    )

    missing_fixed_segment = deepcopy(overlay_segments[0])
    missing_fixed_segment["fixed_horizon_overlays"] = tuple(
        overlay
        for overlay in missing_fixed_segment["fixed_horizon_overlays"]
        if overlay["horizon_bars"] != 2
    )
    missing_fixed = compute_diagnostic_exit_composite(
        segments=(missing_fixed_segment,),
        condition_overlay_id="latency_ge_5_at_2_bar",
        fixed_horizon_bars=2,
        checked_at=start,
    )

    assert missing_fixed.metrics["missing_fixed_overlay_count"] == 1
    assert missing_fixed.segments[0]["composite_status"] == (
        "missing_fixed_overlay_retained_local_paper"
    )
    assert missing_fixed.segments[0]["composite_outcome"]["source"] == (
        LOCAL_PAPER_SOURCE
    )


def test_exit_latency_sandbox_emits_diagnostic_mark_when_latency_condition_met() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    result = compute_exit_latency_sandbox_marks(
        segments=(
            ExitLatencySandboxSegment(
                slice_id="loss",
                variant_id="t01",
                symbol="AAA",
                class_label="loss_bearing",
                entry_timestamp=start,
                entry_price=Decimal("10"),
                quantity=Decimal("1"),
            ),
        ),
        signal_records=(
            ExitLatencySignalRecord(
                symbol="AAA",
                offset=5,
                execution_timestamp=start + timedelta(minutes=5),
                is_exit_signal=True,
                probability=0.25,
            ),
        ),
        bars=tuple(
            _bar(
                "AAA",
                start + timedelta(minutes=index),
                low=10 - index / 2 - 1,
                close=10 - index / 2,
            )
            for index in range(8)
        ),
        min_bars_without_exit_signal=5,
        diagnostic_horizon_bars=2,
        checked_at=start,
    )

    segment = result.segments[0]
    mark = segment["diagnostic_mark"]
    assert mark["available"] is True
    assert mark["source"] == DIAGNOSTIC_OVERLAY_SOURCE
    assert mark["timestamp"] == (start + timedelta(minutes=2)).isoformat()
    assert mark["gross_delta"] == "-1"
    assert segment["latency_condition"]["latency_bars"] == 5
    assert segment["latency_condition"]["condition_met"] is True
    assert result.group_summaries["loss_bearing"]["diagnostic_mark_available_count"] == 1
    assert result.metrics["local_paper_fill_count"] == 0
    assert result.to_payload()["result_scope"]["mode"] == (
        "research_exit_latency_sandbox_only"
    )


def test_exit_latency_sandbox_reports_missing_signal_bar_and_horizon() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    missing_signal = compute_exit_latency_sandbox_marks(
        segments=(
            ExitLatencySandboxSegment(
                slice_id="no_signal",
                variant_id="t01",
                symbol="AAA",
                entry_timestamp=start,
                entry_price=Decimal("10"),
                quantity=Decimal("1"),
            ),
        ),
        signal_records=(),
        bars=tuple(
            _bar("AAA", start + timedelta(minutes=index), low=9, close=10)
            for index in range(4)
        ),
        checked_at=start,
    )

    assert missing_signal.segments[0]["diagnostic_mark"]["reason"] == (
        "missing_exit_signal"
    )
    assert missing_signal.metrics["missing_exit_signal_count"] == 1

    missing_entry_bar = compute_exit_latency_sandbox_marks(
        segments=(
            ExitLatencySandboxSegment(
                slice_id="missing_entry",
                variant_id="t01",
                symbol="BBB",
                entry_timestamp=start,
                entry_price=Decimal("10"),
                quantity=Decimal("1"),
            ),
        ),
        signal_records=(
            ExitLatencySignalRecord(
                symbol="BBB",
                offset=1,
                execution_timestamp=start + timedelta(minutes=1),
                is_exit_signal=True,
            ),
        ),
        bars=(),
        checked_at=start,
    )

    assert missing_entry_bar.segments[0]["diagnostic_mark"]["reason"] == (
        "missing_entry_bar"
    )
    assert missing_entry_bar.metrics["missing_entry_bar_count"] == 1

    missing_horizon = compute_exit_latency_sandbox_marks(
        segments=(
            ExitLatencySandboxSegment(
                slice_id="missing_horizon",
                variant_id="t01",
                symbol="CCC",
                entry_timestamp=start,
                entry_price=Decimal("10"),
                quantity=Decimal("1"),
            ),
        ),
        signal_records=(
            ExitLatencySignalRecord(
                symbol="CCC",
                offset=1,
                execution_timestamp=start + timedelta(minutes=1),
                is_exit_signal=True,
            ),
        ),
        bars=(
            _bar("CCC", start, low=9, close=10),
            _bar("CCC", start + timedelta(minutes=1), low=9, close=10),
        ),
        min_bars_without_exit_signal=1,
        diagnostic_horizon_bars=3,
        checked_at=start,
    )

    assert missing_horizon.segments[0]["diagnostic_mark"]["reason"] == (
        "missing_horizon_bar"
    )
    assert missing_horizon.metrics["missing_horizon_bar_count"] == 1


def test_exit_latency_sandbox_is_offline_and_does_not_mutate_inputs(monkeypatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("exit latency sandbox must not open network")

    def fail_read_text(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("exit latency sandbox must not read files")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", fail_read_text)

    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    segments = (
        ExitLatencySandboxSegment(
            slice_id="offline",
            variant_id="t01",
            symbol="AAA",
            entry_timestamp=start,
            entry_price=Decimal("10"),
            quantity=Decimal("1"),
        ),
    )
    records = (
        ExitLatencySignalRecord(
            symbol="AAA",
            offset=2,
            execution_timestamp=start + timedelta(minutes=2),
            is_exit_signal=True,
        ),
    )
    before_segments = deepcopy(segments)
    before_records = deepcopy(records)

    result = compute_exit_latency_sandbox_marks(
        segments=segments,
        signal_records=records,
        bars=tuple(
            _bar("AAA", start + timedelta(minutes=index), low=9, close=10)
            for index in range(5)
        ),
        min_bars_without_exit_signal=5,
        diagnostic_horizon_bars=2,
        checked_at=start,
    )

    assert segments == before_segments
    assert records == before_records
    assert result.segments[0]["diagnostic_mark"]["source"] == DIAGNOSTIC_OVERLAY_SOURCE
    assert result.metrics["replay_ran"] is False


def _composite_overlay_segments(start: datetime) -> tuple[dict[str, object], ...]:
    conditional = (
        ConditionalExitOverlaySpec(
            overlay_id="latency_ge_5_at_2_bar",
            horizon_bars=2,
            min_bars_without_sell_signal=5,
        ),
    )
    result = compute_diagnostic_exit_overlays(
        segments=(
            DiagnosticExitTradeSegment(
                slice_id="loss",
                variant_id="t01",
                symbol="AAA",
                entry_timestamp=start,
                entry_price=Decimal("10"),
                quantity=Decimal("1"),
                exit_timestamp=start + timedelta(minutes=4),
                exit_price=Decimal("8"),
                bars_to_first_sell_signal=5,
            ),
            DiagnosticExitTradeSegment(
                slice_id="nonneg",
                variant_id="t01",
                symbol="BBB",
                entry_timestamp=start,
                entry_price=Decimal("20"),
                quantity=Decimal("1"),
                exit_timestamp=start + timedelta(minutes=2),
                exit_price=Decimal("22"),
                bars_to_first_sell_signal=2,
            ),
        ),
        bars=tuple(
            _bar(
                "AAA",
                start + timedelta(minutes=index),
                low=10 - index / 2 - 1,
                close=10 - index / 2,
            )
            for index in range(8)
        )
        + tuple(
            _bar("BBB", start + timedelta(minutes=index), low=19, close=20 + index)
            for index in range(8)
        ),
        conditional_overlays=conditional,
        checked_at=start,
    )
    return (
        {**result.segments[0], "class_label": "loss_bearing"},
        {**result.segments[1], "class_label": "non_negative"},
    )


def _bar(
    symbol: str,
    start_ts: datetime,
    *,
    low: float | int,
    close: float | int,
) -> Bar:
    low_decimal = Decimal(str(low))
    close_decimal = Decimal(str(close))
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=close_decimal,
        high=close_decimal + Decimal("1"),
        low=low_decimal,
        close=close_decimal,
        volume=Decimal("100"),
    )
