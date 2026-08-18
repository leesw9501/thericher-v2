from __future__ import annotations

import json
import socket
import sys
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import assess_bar_quality, resample_bars
from thericher_v2.execution import BROKER_DISABLED_SOURCE, LOCAL_PAPER_SOURCE
from thericher_v2.research.validation import main as validation_main


def test_bar_quality_report_is_warning_only_for_clean_contiguous_bars() -> None:
    report = assess_bar_quality(tuple(_bar(index) for index in range(180)))

    assert report.bars_seen == 180
    assert report.warning_count == 0
    assert report.has_warnings is False
    assert report.blocks_research is False
    assert "no warning-only issues found" in report.notes


def test_bar_quality_detects_duplicate_non_monotonic_missing_and_incomplete_buckets() -> None:
    bars = (_bar(0), _bar(2), _bar(1), _bar(2), _bar(5))

    report = assess_bar_quality(bars, target_timeframes=(Timeframe.M5,))
    codes = {warning.code for warning in report.warnings}

    assert report.blocks_research is False
    assert codes == {
        "duplicate_bar",
        "non_monotonic_timestamp",
        "missing_1m_interval",
        "incomplete_resample_bucket",
    }
    missing = [warning for warning in report.warnings if warning.code == "missing_1m_interval"]
    assert missing[0].count == 2
    assert all("promotion" not in warning.message.lower() for warning in report.warnings)


def test_bar_quality_explains_resample_skipped_gap_bucket_without_filling() -> None:
    bars = tuple(_bar(index) for index in range(10) if index != 3)

    report = assess_bar_quality(bars, target_timeframes=(Timeframe.M5,))
    resampled = resample_bars(bars, Timeframe.M5)

    assert len(resampled) == 1
    assert any(
        warning.code == "incomplete_resample_bucket"
        and warning.start_ts == datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        for warning in report.warnings
    )
    assert report.blocks_research is False


def test_bar_quality_explains_resample_skip_from_incomplete_duplicate() -> None:
    bars = tuple(_bar(index) for index in range(10)) + (
        replace(_bar(0), complete=False),
    )

    report = assess_bar_quality(bars, target_timeframes=(Timeframe.M5,))
    resampled = resample_bars(bars, Timeframe.M5)

    assert [bar.start_ts for bar in resampled] == [
        datetime(2026, 1, 2, 0, 5, tzinfo=UTC)
    ]
    warning = next(
        warning
        for warning in report.warnings
        if warning.code == "incomplete_resample_bucket"
        and warning.start_ts == datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
    )
    assert warning.count == 6
    assert "5 complete 1m bars across 6 source record(s)" in warning.message


def test_bar_quality_is_offline_and_does_not_read_credentials(monkeypatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("data-quality checks must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("data-quality checks must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    report = assess_bar_quality(tuple(_bar(index) for index in range(5)))

    assert report.blocks_research is False


def test_bar_quality_does_not_change_execution_source_boundaries() -> None:
    report = assess_bar_quality(tuple(_bar(index) for index in range(5)))

    assert report.blocks_research is False
    assert LOCAL_PAPER_SOURCE == "local_paper"
    assert BROKER_DISABLED_SOURCE == "broker_disabled"
    assert BROKER_DISABLED_SOURCE != LOCAL_PAPER_SOURCE


def test_validation_cli_outputs_warning_only_data_quality(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["thericher-v2-validation-smoke", "--max-bars", "12"],
    )

    validation_main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["data_quality"]["blocks_research"] is False
    assert payload["data_quality"]["bars_seen"] == 12
    assert payload["result"]["bars_seen"] == 12


def _bar(index: int, *, complete: bool = True) -> Bar:
    open_price = Decimal("100") + Decimal(index)
    close = open_price + Decimal("0.25")
    return Bar(
        symbol="aapl",
        market="us",
        timeframe=Timeframe.M1,
        start_ts=datetime(2026, 1, 2, tzinfo=UTC) + Timeframe.M1.duration * index,
        open=open_price,
        high=close + Decimal("0.5"),
        low=open_price - Decimal("0.5"),
        close=close,
        volume=Decimal("1000"),
        complete=complete,
    )
