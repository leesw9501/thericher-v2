from __future__ import annotations

import builtins
import importlib
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.data import (
    BarQuery,
    NorgateRawDailyBarProvider,
    NorgateUnavailableError,
)
from thericher_v2.data.norgate_daily import (
    NorgateClientUnavailableError,
    NorgateLocalUpdaterUnavailableError,
    NorgateMalformedResponseError,
)


class _Dtype:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.dtype = _Dtype(("Date", "Open", "High", "Low", "Close", "Volume"))
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeNorgate:
    class StockPriceAdjustmentType:
        NONE = "none"

    class PaddingType:
        NONE = "none"

    def __init__(self, rows: _Rows) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.global_adjustment = "unchanged"

    def price_timeseries(self, symbol: str, **kwargs: Any) -> _Rows:
        self.calls.append((symbol, kwargs))
        return self.rows


def test_module_does_not_import_optional_norgate_package(monkeypatch) -> None:
    module_name = "thericher_v2.data.norgate_daily"
    original_import = builtins.__import__

    def guard_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "norgatedata":
            raise AssertionError("optional Norgate package must remain lazy")
        return original_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, module_name, raising=False)
    monkeypatch.delitem(sys.modules, "norgatedata", raising=False)
    monkeypatch.setattr(builtins, "__import__", guard_import)

    imported = importlib.import_module(module_name)

    assert "norgatedata" not in imported.__dict__


def test_maps_one_bounded_raw_daily_query_with_query_local_none() -> None:
    client = _FakeNorgate(
        _Rows(
            [
                _row("2024-01-02", "10", "12", "9", "11", "100"),
                _row("2024-01-03", "11", "13", "10", "12", "200"),
            ]
        )
    )
    provider = NorgateRawDailyBarProvider(
        client_loader=lambda: client,
        platform_name="win32",
    )

    bars = provider.get_bars(_query())

    assert [bar.start_ts for bar in bars] == [
        datetime(2024, 1, 2, tzinfo=UTC),
        datetime(2024, 1, 3, tzinfo=UTC),
    ]
    assert [str(bar.close) for bar in bars] == ["11", "12"]
    assert client.calls == [
        (
            "SPY",
            {
                "stock_price_adjustment_setting": "none",
                "padding_setting": "none",
                "start_date": "2024-01-02",
                "end_date": "2024-01-03",
                "timeseriesformat": "numpy-recarray",
                "interval": "D",
            },
        )
    ]
    assert client.global_adjustment == "unchanged"


def test_provider_needs_no_network_credentials_persistence_or_docker(monkeypatch) -> None:
    client = _FakeNorgate(_Rows([_row("2024-01-02", "10", "12", "9", "11", "100")]))

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Norgate adapter must not use this boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("Norgate adapter must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    monkeypatch.setattr(Path, "write_text", fail)
    monkeypatch.setattr(Path, "write_bytes", fail)

    bars = NorgateRawDailyBarProvider(
        client_loader=lambda: client,
        platform_name="win32",
    ).get_bars(_query(end=datetime(2024, 1, 3, tzinfo=UTC)))

    assert len(bars) == 1
    assert client.calls[0][1]["stock_price_adjustment_setting"] == "none"


def test_non_windows_fails_before_optional_client_load() -> None:
    calls = 0

    def loader() -> _FakeNorgate:
        nonlocal calls
        calls += 1
        return _FakeNorgate(_Rows([]))

    provider = NorgateRawDailyBarProvider(client_loader=loader, platform_name="linux")

    with pytest.raises(NorgateUnavailableError, match="requires Windows"):
        provider.get_bars(_query())

    assert calls == 0


def test_missing_optional_client_fails_closed() -> None:
    def unavailable() -> None:
        raise ModuleNotFoundError("norgatedata")

    provider = NorgateRawDailyBarProvider(client_loader=unavailable, platform_name="win32")

    with pytest.raises(NorgateClientUnavailableError, match="unavailable"):
        provider.get_bars(_query())


def test_local_updater_failure_has_its_own_category() -> None:
    class _UnavailableClient(_FakeNorgate):
        def price_timeseries(self, symbol: str, **kwargs: Any) -> _Rows:
            raise RuntimeError("local service unavailable")

    provider = NorgateRawDailyBarProvider(
        client_loader=lambda: _UnavailableClient(_Rows([])),
        platform_name="win32",
    )

    with pytest.raises(NorgateLocalUpdaterUnavailableError, match="unavailable"):
        provider.get_bars(_query())


def test_rejects_non_midnight_bounds_and_invalid_raw_ohlcv() -> None:
    provider = NorgateRawDailyBarProvider(
        client_loader=lambda: _FakeNorgate(
            _Rows([_row("2024-01-02", "10", "9", "8", "11", "100")])
        ),
        platform_name="win32",
    )

    with pytest.raises(ValueError, match="UTC-midnight"):
        provider.get_bars(
            _query(
                start=datetime(2024, 1, 2, 1, tzinfo=UTC),
                end=datetime(2024, 1, 3, 1, tzinfo=UTC),
            )
        )
    with pytest.raises(NorgateMalformedResponseError, match="malformed"):
        provider.get_bars(_query())


def _query(
    *,
    start: datetime = datetime(2024, 1, 2, tzinfo=UTC),
    end: datetime = datetime(2024, 1, 4, tzinfo=UTC),
) -> BarQuery:
    return BarQuery(symbol="spy", market="us", timeframe=Timeframe.D1, start_ts=start, end_ts=end)


def _row(
    session: str,
    open_price: str,
    high: str,
    low: str,
    close: str,
    volume: str,
) -> dict[str, str]:
    return {
        "Date": session,
        "Open": open_price,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }
