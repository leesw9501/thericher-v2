from __future__ import annotations

import csv
import socket
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from thericher_v2.backtest import run_next_bar_backtest
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import (
    CSV_FIELDS,
    BarQuery,
    LocalCsvBarProvider,
    SampleBarProvider,
    bar_from_record,
    bar_to_record,
    resample_bars,
)
from thericher_v2.models import MomentumModel


def _bar(index: int, *, start: datetime = datetime(2026, 1, 2, tzinfo=UTC)) -> Bar:
    open_price = Decimal("100") + Decimal(index)
    close = open_price + Decimal("0.5")
    return Bar(
        symbol="aapl",
        market="us",
        timeframe=Timeframe.M1,
        start_ts=start + Timeframe.M1.duration * index,
        open=open_price,
        high=close + Decimal("0.25"),
        low=open_price - Decimal("0.25"),
        close=close,
        volume=Decimal(100 + index),
    )


def test_resampling_is_deterministic_for_supported_timeframes() -> None:
    bars = [_bar(index) for index in range(180)]

    expected_lengths = {
        Timeframe.M1: 180,
        Timeframe.M5: 36,
        Timeframe.M10: 18,
        Timeframe.H1: 3,
        Timeframe.H3: 1,
    }
    for timeframe, expected_length in expected_lengths.items():
        first = resample_bars(bars, timeframe)
        second = resample_bars(list(reversed(bars)), timeframe)

        assert first == second
        assert len(first) == expected_length
        assert all(bar.complete for bar in first)
        assert all(bar.start_ts.tzinfo == UTC for bar in first)

    first_5m = resample_bars(bars, Timeframe.M5)[0]
    assert first_5m.start_ts == datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
    assert first_5m.open == Decimal("100")
    assert first_5m.high == Decimal("104.75")
    assert first_5m.low == Decimal("99.75")
    assert first_5m.close == Decimal("104.5")
    assert first_5m.volume == Decimal("510")


def test_resampling_skips_gap_buckets_without_filling() -> None:
    bars = [_bar(index) for index in range(10) if index != 3]

    resampled = resample_bars(bars, Timeframe.M5)

    assert len(resampled) == 1
    assert resampled[0].start_ts == datetime(2026, 1, 2, 0, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    "extra",
    [
        lambda bar: bar,
        lambda bar: replace(bar, complete=False),
    ],
    ids=("complete-duplicate", "incomplete-duplicate"),
)
def test_resampling_skips_any_bucket_with_a_duplicate_source_timestamp(extra) -> None:
    bars = [_bar(index) for index in range(10)]
    duplicated = [*bars, extra(bars[0])]

    minute_bars = resample_bars(duplicated, Timeframe.M1)
    five_minute_bars = resample_bars(duplicated, Timeframe.M5)

    assert [bar.start_ts for bar in minute_bars] == [bar.start_ts for bar in bars[1:]]
    assert [bar.start_ts for bar in five_minute_bars] == [bars[5].start_ts]


def test_bar_csv_round_trip_and_local_provider(tmp_path) -> None:
    csv_path = tmp_path / "bars.csv"
    source_bars = [_bar(index) for index in range(6)]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(bar_to_record(bar) for bar in source_bars)

    provider = LocalCsvBarProvider(csv_path)
    query = BarQuery(
        symbol="AAPL",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=datetime(2026, 1, 2, 0, 2, tzinfo=UTC),
        end_ts=datetime(2026, 1, 2, 0, 5, tzinfo=UTC),
    )

    loaded = provider.get_bars(query)

    assert loaded == source_bars[2:5]
    assert bar_from_record(bar_to_record(source_bars[0])) == source_bars[0]
    incomplete = replace(source_bars[0], complete=False)
    assert bar_from_record(bar_to_record(incomplete)) == incomplete


def test_local_provider_rejects_duplicate_timestamps_in_direct_stream(tmp_path) -> None:
    csv_path = tmp_path / "bars.csv"
    source_bars = [_bar(index) for index in range(6)]
    duplicate = replace(source_bars[2], volume=Decimal("999"))
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(bar_to_record(bar) for bar in [*source_bars, duplicate])

    provider = LocalCsvBarProvider(csv_path)
    query = BarQuery(
        symbol="AAPL",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
        end_ts=datetime(2026, 1, 2, 0, 6, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="duplicate bar timestamps"):
        provider.get_bars(query)


def test_local_provider_rejects_noncanonical_header(tmp_path) -> None:
    csv_path = tmp_path / "bars.csv"
    fieldnames = tuple(field for field in CSV_FIELDS if field != "complete")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        row = bar_to_record(_bar(0))
        writer.writerow({field: row[field] for field in fieldnames})

    provider = LocalCsvBarProvider(csv_path)
    query = BarQuery(symbol="AAPL", market="US", timeframe=Timeframe.M1)

    with pytest.raises(ValueError, match="header must exactly match"):
        provider.get_bars(query)


def test_bar_from_record_rejects_naive_timestamps() -> None:
    record = bar_to_record(_bar(0))
    record["start_ts"] = "2026-01-02T00:00:00"

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        bar_from_record(record)


def test_sample_provider_is_offline_and_returns_complete_utc_bars(monkeypatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is not expected for sample data")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    provider = SampleBarProvider.trending_1m(count=60, seed=17)
    bars = provider.get_bars(
        BarQuery(
            symbol="aapl",
            market="us",
            timeframe=Timeframe.M10,
            start_ts=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            end_ts=datetime(2026, 1, 2, 1, 0, tzinfo=UTC),
        )
    )

    assert len(bars) == 6
    assert all(bar.symbol == "AAPL" and bar.market == "US" for bar in bars)
    assert all(bar.timeframe == Timeframe.M10 for bar in bars)
    assert all(bar.complete for bar in bars)
    assert all(bar.start_ts.tzinfo == UTC for bar in bars)


def test_query_rejects_invalid_ranges() -> None:
    with pytest.raises(ValueError, match="end_ts must be after start_ts"):
        BarQuery(
            symbol="AAPL",
            market="US",
            timeframe=Timeframe.M1,
            start_ts=datetime(2026, 1, 2, 1, 0, tzinfo=UTC),
            end_ts=datetime(2026, 1, 2, 1, 0, tzinfo=UTC),
        )


def test_backtest_consumes_resampled_market_data() -> None:
    provider = SampleBarProvider.trending_1m(count=90, seed=3)
    bars = provider.get_bars(
        BarQuery(
            symbol="AAPL",
            market="US",
            timeframe=Timeframe.M5,
            start_ts=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            end_ts=datetime(2026, 1, 2, 1, 30, tzinfo=UTC),
        )
    )

    result = run_next_bar_backtest(bars, model=MomentumModel(lookback=3))

    assert len(bars) == 18
    assert result.trades
    assert result.equity > Decimal("0")
