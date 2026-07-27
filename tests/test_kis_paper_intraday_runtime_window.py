from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_intraday_runtime_window import (
    KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS,
    KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M5_BARS,
    KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M10_BARS,
    KisPaperIntradayRuntimeWindow,
    select_kis_paper_intraday_runtime_window,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.resample import SessionWindow, resample_session_bars
from thericher_v2.data.us_equity_session import us_equity_2026_session

_SESSION_DATE = date(2026, 7, 20)
_CATALOG_ID = "kis.paper.private.intraday.qqq.nas.m1.unit-v1"


def test_selects_newest_ready_window_with_resample_shape_without_full_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _catalog(count=100)
    _deny_external_access(monkeypatch)

    first = select_kis_paper_intraday_runtime_window(
        source,
        as_of=source.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )
    second = select_kis_paper_intraday_runtime_window(
        source,
        as_of=source.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )

    assert first.status == "ready"
    assert isinstance(first, KisPaperIntradayRuntimeWindow)
    assert len(source.bars) == 100 < 390
    assert len(first.decision_bars) == KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS
    assert first.decision_bars == source.bars[-90:]
    assert first.window_end == source.bars[-1].end_ts
    assert first.window_end is not None
    assert first.window_end.minute % 10 == 0
    assert first.replay_bar is None
    assert first.source_catalog_hash == source.dataset_hash
    assert first.input_manifest_ref.startswith("sha256:")
    assert first.input_manifest_ref == second.input_manifest_ref

    window = SessionWindow(open_ts=first.window_start, close_ts=first.window_end)
    m5 = resample_session_bars(first.decision_bars, Timeframe.M5, session=window)
    m10 = resample_session_bars(first.decision_bars, Timeframe.M10, session=window)
    assert len(m5.bars) == KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M5_BARS
    assert len(m10.bars) == KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M10_BARS
    assert not m5.skipped_bucket_starts
    assert not m10.skipped_bucket_starts


def test_returns_optional_immediate_complete_replay_bar() -> None:
    source = _catalog(count=91)

    result = select_kis_paper_intraday_runtime_window(
        source,
        as_of=source.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )

    assert result.status == "ready"
    assert result.decision_bars == source.bars[:90]
    assert result.replay_bar == source.bars[90]
    assert result.replay_bar.start_ts == result.window_end
    assert result.safe_payload()["replay_bar_count"] == 1


def test_returns_stale_without_exposing_candidate_bars() -> None:
    source = _catalog(count=90)

    result = select_kis_paper_intraday_runtime_window(
        source,
        as_of=source.bars[-1].end_ts + timedelta(minutes=6),
        max_age=timedelta(minutes=5),
    )

    assert result.status == "stale"
    assert result.decision_bars == ()
    assert result.replay_bar is None
    assert result.candidate_bar_count == 90
    assert result.window_start == source.bars[0].start_ts
    assert result.window_end == source.bars[-1].end_ts


def test_rejects_a_gap_as_non_contiguous() -> None:
    source = _catalog(count=91, excluded_minutes={45})

    result = select_kis_paper_intraday_runtime_window(
        source,
        as_of=source.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )

    assert result.status == "non_contiguous"
    assert result.decision_bars == ()
    assert result.replay_bar is None


def test_does_not_join_short_windows_across_regular_sessions() -> None:
    first = _bars_for_session(_SESSION_DATE, count=45)
    second = _bars_for_session(date(2026, 7, 21), count=45)
    source = _catalog_from_bars(first + second)

    result = select_kis_paper_intraday_runtime_window(
        source,
        as_of=source.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )

    assert result.status == "missing"
    assert result.decision_bars == ()


def test_rejects_a_wrong_symbol_or_nas_catalog_identity() -> None:
    wrong_symbol = _catalog(count=90, symbol="SPY")
    wrong_nas_identity = _catalog(
        count=90,
        dataset_id="kis.paper.private.intraday.qqq.ams.m1.unit-v1",
    )

    for source in (wrong_symbol, wrong_nas_identity):
        result = select_kis_paper_intraday_runtime_window(
            source,
            as_of=source.bars[-1].end_ts,
            max_age=timedelta(minutes=2),
        )

        assert result.status == "misaligned"
        assert result.decision_bars == ()


def test_distinguishes_current_incomplete_and_future_bars() -> None:
    source = _catalog(count=90)
    current = _catalog_from_bars(
        tuple(
            replace(bar, complete=False) if index == len(source.bars) - 1 else bar
            for index, bar in enumerate(source.bars)
        )
    )

    incomplete = select_kis_paper_intraday_runtime_window(
        current,
        as_of=current.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )
    future = select_kis_paper_intraday_runtime_window(
        source,
        as_of=source.bars[-2].end_ts,
        max_age=timedelta(minutes=2),
    )

    assert incomplete.status == "incomplete"
    assert incomplete.decision_bars == ()
    assert future.status == "future"
    assert future.decision_bars == ()


def test_safe_repr_and_payload_never_include_prices_or_source_path() -> None:
    source = _catalog(count=90, base_price=Decimal("123.4567"))

    result = select_kis_paper_intraday_runtime_window(
        source,
        as_of=source.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )
    rendered = repr(result)
    payload = result.safe_payload()
    serialized = json.dumps(payload, sort_keys=True)

    assert result.status == "ready"
    assert "123.4567" not in rendered
    assert "123.4567" not in serialized
    assert str(source.source_path) not in rendered
    assert str(source.source_path) not in serialized
    assert set(payload) == {
        "kind",
        "schema_id",
        "schema_version",
        "status",
        "source_bar_count",
        "regular_bar_count",
        "candidate_bar_count",
        "decision_bar_count",
        "replay_bar_count",
        "as_of",
        "window_start",
        "window_end",
        "replay_bar_start",
        "replay_bar_end",
        "source_catalog_hash",
        "input_manifest_ref",
    }
    assert "open" not in payload
    assert "close" not in payload
    assert "source_path" not in payload


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime window selection must stay broker-free")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime window selection must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)


def _catalog(
    *,
    count: int,
    excluded_minutes: set[int] | None = None,
    symbol: str = "QQQ",
    dataset_id: str = _CATALOG_ID,
    base_price: Decimal = Decimal("100"),
) -> CatalogedBars:
    bars = _bars_for_session(
        _SESSION_DATE,
        count=count,
        excluded_minutes=excluded_minutes,
        symbol=symbol,
        base_price=base_price,
    )
    return _catalog_from_bars(bars, dataset_id=dataset_id)


def _bars_for_session(
    session_date: date,
    *,
    count: int,
    excluded_minutes: set[int] | None = None,
    symbol: str = "QQQ",
    base_price: Decimal = Decimal("100"),
) -> tuple[Bar, ...]:
    session = us_equity_2026_session(session_date)
    assert session is not None
    return tuple(
        _bar(
            symbol=symbol,
            start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
            price=base_price + Decimal(minute) / Decimal("100"),
        )
        for minute in range(count)
        if excluded_minutes is None or minute not in excluded_minutes
    )


def _catalog_from_bars(
    bars: tuple[Bar, ...],
    *,
    dataset_id: str = _CATALOG_ID,
) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=dataset_id,
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("unit-kis-index.json"),
        bars=bars,
    )


def _bar(*, symbol: str, start_ts, price: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=price,
        high=price + Decimal("0.01"),
        low=price - Decimal("0.01"),
        close=price + Decimal("0.005"),
        volume=Decimal("1000"),
        complete=True,
    )
