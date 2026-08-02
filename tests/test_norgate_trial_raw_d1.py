from __future__ import annotations

import builtins
import importlib
import json
import socket
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_trial_raw_d1 import (
    FIXED_NORGATE_TRIAL_SYMBOLS,
    NorgateCapitalEventEvidence,
    NorgateTrialRawD1Error,
    build_norgate_trial_raw_d1_snapshot,
    default_norgate_trial_raw_d1_snapshot_dir,
    load_norgate_capital_event_evidence,
    verify_norgate_trial_raw_d1_snapshot,
)

_START = date(2024, 1, 2)
_END = date(2024, 1, 3)


class _Dtype:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.dtype = _Dtype(("Date", "Capital Event"))
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeClient:
    def __init__(self, rows: _Rows) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def capital_event_timeseries(self, symbol: str, **kwargs: Any) -> _Rows:
        self.calls.append((symbol, kwargs))
        return self.rows


def test_module_keeps_optional_norgate_import_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "thericher_v2.data.norgate_trial_raw_d1"
    original_import = builtins.__import__

    def guard_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "norgatedata":
            raise AssertionError("trial raw-D1 module must keep Norgate optional")
        return original_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, module_name, raising=False)
    monkeypatch.delitem(sys.modules, "norgatedata", raising=False)
    monkeypatch.setattr(builtins, "__import__", guard_import)

    imported = importlib.import_module(module_name)

    assert "norgatedata" not in imported.__dict__


def test_loads_and_explicitly_clips_range_padded_capital_events() -> None:
    client = _FakeClient(
        _Rows(
            [
                {"Date": "2024-01-01", "Capital Event": 0},
                {"Date": "2024-01-02", "Capital Event": 0},
                {"Date": "2024-01-03", "Capital Event": 1},
                {"Date": "2024-01-04", "Capital Event": 0},
            ]
        )
    )

    evidence = load_norgate_capital_event_evidence(
        "spy",
        _START,
        _END,
        client_loader=lambda: client,
    )

    assert evidence == NorgateCapitalEventEvidence(
        returned_row_count=4,
        returned_start=date(2024, 1, 1),
        returned_end=date(2024, 1, 4),
        clipped_session_count=2,
        marker_dates=(_END,),
    )
    assert client.calls == [
        (
            "SPY",
            {
                "start_date": "2024-01-02",
                "end_date": "2024-01-03",
                "limit": -1,
                "timeseriesformat": "numpy-recarray",
            },
        )
    ]


def test_builds_external_trial_snapshot_without_network_or_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repo, destination = _paths(tmp_path)
    calls: list[tuple[str, str, date, date]] = []

    def bars(symbol: str, start: date, end: date) -> Sequence[Bar]:
        calls.append(("bars", symbol, start, end))
        return _bars(symbol)

    def events(symbol: str, start: date, end: date) -> NorgateCapitalEventEvidence:
        calls.append(("events", symbol, start, end))
        return _events(symbol)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("trial snapshot must not cross this boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("trial snapshot must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    result = _build(destination, root, repo, bars=bars, events=events)

    assert result.snapshot_dir == destination
    assert not result.snapshot_dir.is_relative_to(repo)
    assert result.row_count == 6
    assert result.common_session_count == 2
    assert result.event_marker_count == 1
    assert result.excluded_session_count == 2
    assert result.actual_start == _START
    assert result.actual_end == _END
    assert calls == [
        *[("bars", symbol, _START, _END) for symbol in FIXED_NORGATE_TRIAL_SYMBOLS],
        *[("events", symbol, _START, _END) for symbol in FIXED_NORGATE_TRIAL_SYMBOLS],
    ]
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    marker = (destination / "DELETE_NORGATE_DATA_ON_EXPIRY.txt").read_text(encoding="ascii")
    event_rows = (destination / "capital_event_exclusions.csv").read_text(encoding="utf-8")
    assert manifest["norgate_source_contract"]["requested_stock_price_adjustment_setting"] == "NONE"
    assert manifest["norgate_source_contract"]["adjustment_semantics_verified"] is False
    assert manifest["capital_event_evidence"]["query_window_clipped_explicitly"] is True
    assert manifest["capital_event_evidence"]["per_symbol"]["QQQ"][
        "response_was_range_padded"
    ] is True
    assert manifest["capital_event_evidence"]["observed_marker_count_interpretation"] == (
        "not_established_from_clipped_or_padded_query"
    )
    assert manifest["scope"]["development_source_attested"] is True
    assert manifest["scope"]["development_training_eligible"] is False
    assert manifest["scope"]["model_eligible"] is False
    assert "must delete this snapshot directory" in marker
    assert "does not establish that no events occurred" in marker
    assert event_rows.splitlines() == [
        "symbol,event_marker_date,excluded_session_date",
        "QQQ,2024-01-03,2024-01-02",
        "QQQ,2024-01-03,2024-01-03",
    ]
    assert verify_norgate_trial_raw_d1_snapshot(
        destination, market_data_root=root, repo_root=repo
    ) == result


@pytest.mark.parametrize(
    "filename", ("norgate_ohlcv_1d.csv.gz", "DELETE_NORGATE_DATA_ON_EXPIRY.txt")
)
def test_external_tampering_fails_closed(tmp_path: Path, filename: str) -> None:
    root, repo, destination = _paths(tmp_path)
    result = _build(destination, root, repo)
    path = result.snapshot_dir / filename
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="hash mismatch"):
        verify_norgate_trial_raw_d1_snapshot(
            result.snapshot_dir, market_data_root=root, repo_root=repo
        )


def test_matching_existing_snapshot_reattests_without_new_provider_calls(tmp_path: Path) -> None:
    root, repo, destination = _paths(tmp_path)
    first = _build(destination, root, repo)

    def fail_provider(*_args: object, **_kwargs: object) -> Sequence[Bar]:
        raise AssertionError("matching immutable snapshot must not recollect bars")

    def fail_events(*_args: object, **_kwargs: object) -> NorgateCapitalEventEvidence:
        raise AssertionError("matching immutable snapshot must not recollect events")

    rerun = _build(
        destination,
        root,
        repo,
        bars=fail_provider,
        events=fail_events,
    )

    assert rerun == first
    with pytest.raises(ValueError, match="request does not match"):
        build_norgate_trial_raw_d1_snapshot(
            destination=destination,
            requested_start=_START,
            requested_end=date(2024, 1, 4),
            retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
            norgate_bars=fail_provider,
            capital_event_evidence=fail_events,
            norgate_package_version="test-version",
            market_data_root=root,
            repo_root=repo,
        )


def test_uneven_sessions_or_event_coverage_leave_no_published_snapshot(tmp_path: Path) -> None:
    root, repo, destination = _paths(tmp_path)

    with pytest.raises(ValueError, match="uneven fixed-ETF sessions"):
        _build(
            destination,
            root,
            repo,
            bars=lambda symbol, _start, _end: _bars(symbol, short=symbol == "IWM"),
        )
    assert not destination.exists()

    with pytest.raises(ValueError, match="event coverage"):
        _build(
            destination,
            root,
            repo,
            events=lambda symbol, _start, _end: NorgateCapitalEventEvidence(
                returned_row_count=3,
                returned_start=date(2024, 1, 1),
                returned_end=date(2024, 1, 4),
                clipped_session_count=1,
                marker_dates=(),
            ),
        )
    assert not destination.exists()
    assert not list(destination.parent.glob(".stage-*"))


def test_rejects_non_windows_low_storage_and_git_destination(tmp_path: Path) -> None:
    root, repo, destination = _paths(tmp_path)

    with pytest.raises(NorgateTrialRawD1Error, match="requires Windows"):
        _build(destination, root, repo, platform_name="linux")
    with pytest.raises(ValueError, match="hard free-space"):
        _build(
            destination,
            root,
            repo,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )
    with pytest.raises(ValueError, match="outside Git"):
        _build(repo / destination.name, repo, repo)


def test_default_destination_uses_external_market_data_root() -> None:
    assert default_norgate_trial_raw_d1_snapshot_dir(date(2026, 7, 19)) == Path(
        "D:/market_data/us_equities/fixed_etf_daily/canonical/norgate_trial_raw_d1/"
        "snapshot=2026-07-19-norgate-trial-raw-d1-r2"
    )


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "market_data"
    root.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    destination = root / "fixed" / "snapshot=2026-07-19-norgate-trial-raw-d1-r2"
    return root, repo, destination


def _build(
    destination: Path,
    root: Path,
    repo: Path,
    *,
    bars: Callable[[str, date, date], Sequence[Bar]] = lambda symbol, _start, _end: _bars(
        symbol
    ),
    events: Callable[[str, date, date], NorgateCapitalEventEvidence] = (
        lambda symbol, _start, _end: _events(symbol)
    ),
    platform_name: str = "win32",
    disk_usage: Callable[[str | Path], object] | None = None,
):
    return build_norgate_trial_raw_d1_snapshot(
        destination=destination,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        norgate_bars=bars,
        capital_event_evidence=events,
        norgate_package_version="test-version",
        market_data_root=root,
        repo_root=repo,
        platform_name=platform_name,
        disk_usage=disk_usage or (lambda _path: SimpleNamespace(total=100, free=50)),
    )


def _bars(symbol: str, *, short: bool = False) -> list[Bar]:
    sessions = (_START,) if short else (_START, _END)
    return [_bar(symbol, session) for session in sessions]


def _bar(symbol: str, session: date) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime.combine(session, datetime.min.time(), UTC),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=Decimal("100"),
    )


def _events(symbol: str) -> NorgateCapitalEventEvidence:
    return NorgateCapitalEventEvidence(
        returned_row_count=4,
        returned_start=date(2024, 1, 1),
        returned_end=date(2024, 1, 4),
        clipped_session_count=2,
        marker_dates=(_END,) if symbol == "QQQ" else (),
    )
