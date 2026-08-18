from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import SessionWindow, resample_session_bars


def _bar(index: int, *, start: datetime) -> Bar:
    open_price = Decimal("100") + Decimal(index) / Decimal("100")
    close = open_price + Decimal("0.01")
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start + timedelta(minutes=index),
        open=open_price,
        high=close + Decimal("0.01"),
        low=open_price - Decimal("0.01"),
        close=close,
        volume=Decimal("100") + Decimal(index),
        complete=True,
    )


@pytest.mark.parametrize(
    ("session_open", "expected_open"),
    (
        (datetime(2026, 7, 1, 13, 30, tzinfo=UTC), datetime(2026, 7, 1, 13, 30, tzinfo=UTC)),
        (datetime(2026, 1, 2, 14, 30, tzinfo=UTC), datetime(2026, 1, 2, 14, 30, tzinfo=UTC)),
    ),
    ids=("summer-us-session", "winter-us-session"),
)
def test_session_resampling_anchors_all_timeframes_at_declared_open(
    session_open: datetime,
    expected_open: datetime,
) -> None:
    session = SessionWindow(session_open, session_open + timedelta(minutes=390))
    bars = [_bar(index, start=session.open_ts) for index in range(390)]

    five_minute = resample_session_bars(bars, Timeframe.M5, session=session)
    hourly = resample_session_bars(bars, Timeframe.H1, session=session)
    three_hour = resample_session_bars(bars, Timeframe.H3, session=session)

    assert len(five_minute.bars) == 78
    assert five_minute.bars[0].start_ts == expected_open
    assert five_minute.bars[0].open == Decimal("100")
    assert five_minute.bars[0].high == Decimal("100.06")
    assert five_minute.bars[0].low == Decimal("99.99")
    assert five_minute.bars[0].close == Decimal("100.05")
    assert five_minute.bars[0].volume == Decimal("510")
    assert five_minute.skipped_bucket_starts == ()
    assert [bar.start_ts for bar in hourly.bars] == [
        expected_open + timedelta(hours=offset) for offset in range(6)
    ]
    assert hourly.skipped_bucket_starts == (expected_open + timedelta(hours=6),)
    assert [bar.start_ts for bar in three_hour.bars] == [
        expected_open,
        expected_open + timedelta(hours=3),
    ]
    assert three_hour.skipped_bucket_starts == (expected_open + timedelta(hours=6),)


def test_session_resampling_is_invariant_to_two_newest_first_chunks() -> None:
    session = SessionWindow(
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 16, 0, tzinfo=UTC),
    )
    chronological = _bar_range(session.open_ts, 90)
    newest_first_chunks = [
        *reversed(chronological[47:]),
        *reversed(chronological[:47]),
    ]

    for target_timeframe, expected_count in (
        (Timeframe.M5, 18),
        (Timeframe.M10, 9),
    ):
        chronological_result = resample_session_bars(
            chronological,
            target_timeframe,
            session=session,
        )
        newest_first_result = resample_session_bars(
            newest_first_chunks,
            target_timeframe,
            session=session,
        )

        assert len(chronological_result.bars) == expected_count
        assert chronological_result.skipped_bucket_starts == ()
        assert newest_first_result == chronological_result
        assert all(bar.complete for bar in newest_first_result.bars)


def test_session_resampling_exposes_gap_and_duplicate_buckets() -> None:
    session = SessionWindow(
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
    )
    gapped = [_bar(index, start=session.open_ts) for index in range(30) if index != 7]
    gapped_result = resample_session_bars(gapped, Timeframe.M5, session=session)
    incomplete = [
        replace(_bar(index, start=session.open_ts), complete=False)
        if index == 7
        else _bar(index, start=session.open_ts)
        for index in range(30)
    ]
    incomplete_result = resample_session_bars(incomplete, Timeframe.M5, session=session)
    duplicate = [
        *_bar_range(session.open_ts, 4),
        _bar(3, start=session.open_ts),
        *_bar_range(session.open_ts + timedelta(minutes=5), 5),
    ]
    duplicate_result = resample_session_bars(duplicate, Timeframe.M5, session=session)
    incomplete_duplicate = [
        *_bar_range(session.open_ts, 30),
        replace(_bar(7, start=session.open_ts), complete=False),
    ]
    incomplete_duplicate_result = resample_session_bars(
        incomplete_duplicate,
        Timeframe.M5,
        session=session,
    )

    assert [bar.start_ts for bar in gapped_result.bars] == [
        session.open_ts,
        session.open_ts + timedelta(minutes=10),
        session.open_ts + timedelta(minutes=15),
        session.open_ts + timedelta(minutes=20),
        session.open_ts + timedelta(minutes=25),
    ]
    assert gapped_result.skipped_bucket_starts == (session.open_ts + timedelta(minutes=5),)
    assert incomplete_result == gapped_result
    assert [bar.start_ts for bar in duplicate_result.bars] == [
        session.open_ts + timedelta(minutes=5)
    ]
    assert duplicate_result.skipped_bucket_starts == (
        session.open_ts,
        session.open_ts + timedelta(minutes=10),
        session.open_ts + timedelta(minutes=15),
        session.open_ts + timedelta(minutes=20),
        session.open_ts + timedelta(minutes=25),
    )
    assert [bar.start_ts for bar in incomplete_duplicate_result.bars] == [
        session.open_ts,
        session.open_ts + timedelta(minutes=10),
        session.open_ts + timedelta(minutes=15),
        session.open_ts + timedelta(minutes=20),
        session.open_ts + timedelta(minutes=25),
    ]
    assert incomplete_duplicate_result.skipped_bucket_starts == (
        session.open_ts + timedelta(minutes=5),
    )


def test_session_resampling_rejects_out_of_window_or_adjacent_session_bars() -> None:
    session = SessionWindow(
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 14, 40, tzinfo=UTC),
    )
    current_session = [_bar(index, start=session.open_ts) for index in range(10)]
    adjacent_session = _bar(0, start=session.close_ts)

    with pytest.raises(ValueError, match="inside the declared session"):
        resample_session_bars(
            [*current_session, adjacent_session],
            Timeframe.M5,
            session=session,
        )
    with pytest.raises(ValueError, match="inside the declared session"):
        resample_session_bars(
            [replace(current_session[0], start_ts=session.open_ts - timedelta(minutes=1))],
            Timeframe.M5,
            session=session,
        )


def test_session_resampling_requires_one_minute_source_bars() -> None:
    session = SessionWindow(
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 14, 40, tzinfo=UTC),
    )
    bars = [
        replace(_bar(index, start=session.open_ts), timeframe=Timeframe.M5)
        for index in range(2)
    ]

    with pytest.raises(ValueError, match="requires 1m"):
        resample_session_bars(bars, Timeframe.M5, session=session)


def test_empty_session_exposes_missing_full_and_terminal_buckets() -> None:
    session = SessionWindow(
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 14, 40, tzinfo=UTC),
    )
    five_minute = resample_session_bars([], Timeframe.M5, session=session)
    hourly = resample_session_bars([], Timeframe.H1, session=session)

    assert five_minute.bars == ()
    assert five_minute.skipped_bucket_starts == (
        session.open_ts,
        session.open_ts + timedelta(minutes=5),
    )
    assert hourly.bars == ()
    assert hourly.skipped_bucket_starts == (session.open_ts,)


def _bar_range(start: datetime, count: int) -> list[Bar]:
    return [_bar(index, start=start) for index in range(count)]
