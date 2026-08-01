from __future__ import annotations

import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.models.sequence_window import (
    CAUSAL_SEQUENCE_WINDOW_SCHEMA_ID,
    SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
    SequenceWindowInputError,
    build_causal_multitimeframe_sequence_window,
)

_CUTOFF = datetime(2026, 8, 4, 15, 0, tzinfo=UTC)
_LOOKBACKS = {
    Timeframe.M1: 300,
    Timeframe.M5: 120,
    Timeframe.M10: 60,
    Timeframe.H1: 30,
    Timeframe.H3: 30,
}


def test_builds_all_five_ordered_completed_windows_with_variable_lookbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    result = build_causal_multitimeframe_sequence_window(
        _bars_by_timeframe(),
        lookbacks=_LOOKBACKS,
        cutoff=_CUTOFF,
    )

    assert tuple(result.windows) == SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    assert result.symbol == "QQQ"
    assert result.market == "US"
    assert all(window.end_ts == _CUTOFF for window in result.windows.values())
    assert {
        timeframe: len(window.bars) for timeframe, window in result.windows.items()
    } == _LOOKBACKS
    assert all(
        tuple(bar.start_ts for bar in window.bars)
        == tuple(sorted(bar.start_ts for bar in window.bars))
        for window in result.windows.values()
    )


def test_preserves_per_timeframe_completed_end_when_cutoff_is_between_boundaries() -> None:
    cutoff = datetime(2026, 8, 4, 16, 2, tzinfo=UTC)
    ends = {
        Timeframe.M1: cutoff,
        Timeframe.M5: cutoff - timedelta(minutes=2),
        Timeframe.M10: cutoff - timedelta(minutes=2),
        Timeframe.H1: cutoff - timedelta(minutes=2),
        Timeframe.H3: cutoff - timedelta(hours=1, minutes=2),
    }
    result = build_causal_multitimeframe_sequence_window(
        {
            timeframe: _bars(timeframe, _LOOKBACKS[timeframe], end_ts=ends[timeframe])
            for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
        },
        lookbacks=_LOOKBACKS,
        cutoff=cutoff,
    )

    assert {timeframe: window.end_ts for timeframe, window in result.windows.items()} == ends
    metadata = result.structural_metadata()
    assert metadata["schema_id"] == CAUSAL_SEQUENCE_WINDOW_SCHEMA_ID
    assert "100" not in str(metadata)
    assert metadata["windows"]["3h"]["cutoff_lag_microseconds"] == 3_720_000_000


@pytest.mark.parametrize(
    ("mutate", "status"),
    [
        (
            lambda bars: (*bars[:-1], replace(bars[-1], complete=False)),
            "incomplete",
        ),
        (lambda bars: (*bars, bars[-1]), "duplicate"),
        (lambda bars: (*bars[:-1], replace(bars[-1], start_ts=_CUTOFF)), "future"),
        (lambda bars: _gapped_m1_bars(bars), "non_contiguous"),
        (
            lambda bars: (*bars[:-1], replace(bars[-1], timeframe=Timeframe.M5)),
            "misaligned",
        ),
    ],
)
def test_rejects_invalid_selected_window_shapes(mutate, status: str) -> None:
    supplied = _bars_by_timeframe()
    supplied[Timeframe.M1] = mutate(supplied[Timeframe.M1])

    with pytest.raises(SequenceWindowInputError) as raised:
        build_causal_multitimeframe_sequence_window(
            supplied,
            lookbacks=_LOOKBACKS,
            cutoff=_CUTOFF,
        )

    assert raised.value.status == status
    assert raised.value.timeframe == Timeframe.M1


def test_rejects_cross_timeframe_symbol_market_and_cutoff_misalignment() -> None:
    supplied = _bars_by_timeframe()
    supplied[Timeframe.H1] = _bars(Timeframe.H1, _LOOKBACKS[Timeframe.H1], symbol="SPY")
    with pytest.raises(SequenceWindowInputError, match="all timeframe windows") as symbol_error:
        build_causal_multitimeframe_sequence_window(
            supplied,
            lookbacks=_LOOKBACKS,
            cutoff=_CUTOFF,
        )

    assert symbol_error.value.status == "misaligned"
    supplied = _bars_by_timeframe()
    supplied[Timeframe.H1] = _bars(Timeframe.H1, _LOOKBACKS[Timeframe.H1], market="NYSE")
    with pytest.raises(SequenceWindowInputError, match="all timeframe windows") as market_error:
        build_causal_multitimeframe_sequence_window(
            supplied,
            lookbacks=_LOOKBACKS,
            cutoff=_CUTOFF,
        )

    assert market_error.value.status == "misaligned"
    supplied = _bars_by_timeframe()
    supplied[Timeframe.H3] = _bars(
        Timeframe.H3,
        _LOOKBACKS[Timeframe.H3],
        end_ts=_CUTOFF - Timeframe.H3.duration,
    )
    with pytest.raises(SequenceWindowInputError, match="older than one timeframe") as cutoff_error:
        build_causal_multitimeframe_sequence_window(
            supplied,
            lookbacks=_LOOKBACKS,
            cutoff=_CUTOFF,
        )

    assert cutoff_error.value.status == "misaligned"
    assert cutoff_error.value.timeframe == Timeframe.H3


def test_requires_exact_coverage_and_lookback_contract() -> None:
    supplied = _bars_by_timeframe()
    supplied.pop(Timeframe.H3)
    with pytest.raises(SequenceWindowInputError) as missing_bars:
        build_causal_multitimeframe_sequence_window(
            supplied,
            lookbacks=_LOOKBACKS,
            cutoff=_CUTOFF,
        )

    assert missing_bars.value.status == "missing"
    invalid_lookbacks = dict(_LOOKBACKS)
    invalid_lookbacks[Timeframe.M1] = 0
    with pytest.raises(ValueError, match="positive integer"):
        build_causal_multitimeframe_sequence_window(
            _bars_by_timeframe(),
            lookbacks=invalid_lookbacks,
            cutoff=_CUTOFF,
        )


def test_canonicalizes_input_order_deterministically() -> None:
    ordered = build_causal_multitimeframe_sequence_window(
        _bars_by_timeframe(),
        lookbacks=_LOOKBACKS,
        cutoff=_CUTOFF,
    )
    reversed_input = {
        timeframe: tuple(reversed(bars))
        for timeframe, bars in _bars_by_timeframe().items()
    }
    reversed_result = build_causal_multitimeframe_sequence_window(
        reversed_input,
        lookbacks=_LOOKBACKS,
        cutoff=_CUTOFF,
    )

    assert reversed_result == ordered


def _bars_by_timeframe() -> dict[Timeframe, tuple[Bar, ...]]:
    return {
        timeframe: _bars(timeframe, _LOOKBACKS[timeframe])
        for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    }


def _gapped_m1_bars(bars: tuple[Bar, ...]) -> tuple[Bar, ...]:
    extended = _bars(Timeframe.M1, len(bars) + 1)
    return (*extended[:20], *extended[21:])


def _bars(
    timeframe: Timeframe,
    count: int,
    *,
    end_ts: datetime = _CUTOFF,
    symbol: str = "QQQ",
    market: str = "US",
) -> tuple[Bar, ...]:
    start = end_ts - timeframe.duration * count
    return tuple(
        _bar(
            timeframe=timeframe,
            start_ts=start + timeframe.duration * index,
            symbol=symbol,
            market=market,
            price=Decimal("100") + Decimal(index) / Decimal("100"),
        )
        for index in range(count)
    )


def _bar(
    *,
    timeframe: Timeframe,
    start_ts: datetime,
    symbol: str,
    market: str,
    price: Decimal,
) -> Bar:
    return Bar(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        start_ts=start_ts,
        open=price,
        high=price + Decimal("0.02"),
        low=price - Decimal("0.02"),
        close=price + Decimal("0.01"),
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("sequence windows must remain in-memory and offline")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
