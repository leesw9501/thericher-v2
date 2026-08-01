from __future__ import annotations

import builtins
import importlib
import json
import socket
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from thericher_v2.data.norgate_trial_daily_capability_probe import (
    NorgateTrialDailyCapabilityProbeError,
    build_norgate_trial_daily_capability_probe,
    fingerprint_norgate_us_database_build,
    require_attested_norgate_trial_daily_capability_probe,
    verify_norgate_trial_daily_capability_probe,
)


class _Dtype:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names


class _Rows:
    def __init__(self, rows: list[dict[str, Any]], names: tuple[str, ...]) -> None:
        self.dtype = _Dtype(names)
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeNorgate:
    class PaddingType:
        NONE = "none"

    class StockPriceAdjustmentType:
        NONE = "none"

    __version__ = "test-norgate-1.0"

    def __init__(self, *, membership_change: bool = True) -> None:
        self.membership_change = membership_change
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def watchlist_symbols(self, watchlist: str) -> list[str]:
        self.calls.append(("watchlist", watchlist, {}))
        return ["AAL", "AAPL", "PLTR"]

    def index_constituent_timeseries(self, symbol: str, index_name: str, **kwargs: Any) -> _Rows:
        self.calls.append(("membership", f"{symbol}:{index_name}", kwargs))
        dates = _requested_dates(kwargs)
        if symbol == "AAPL":
            values = [1, 1]
        elif symbol == "PLTR" and self.membership_change:
            values = [0, 1]
        elif symbol == "PLTR":
            values = [1, 1]
        else:
            values = [0, 0]
        return _Rows(
            [
                {"Date": session.isoformat(), "Index Constituent": value}
                for session, value in zip(dates, values, strict=True)
            ],
            ("Date", "Index Constituent"),
        )

    def major_exchange_listed_timeseries(self, symbol: str, **kwargs: Any) -> _Rows:
        self.calls.append(("listing", symbol, kwargs))
        return _Rows(
            [
                {"Date": session.isoformat(), "Major Exchange Listed": 1}
                for session in _requested_dates(kwargs)
            ],
            ("Date", "Major Exchange Listed"),
        )

    def price_timeseries(self, symbol: str, **kwargs: Any) -> _Rows:
        self.calls.append(("price", symbol, kwargs))
        return _Rows(
            [
                {
                    "Date": session.isoformat(),
                    "Open": "10.0",
                    "High": "11.0",
                    "Low": "9.0",
                    "Close": "10.5",
                    "Volume": "100",
                }
                for session in _requested_dates(kwargs)
            ],
            ("Date", "Open", "High", "Low", "Close", "Volume"),
        )

    def capital_event_timeseries(self, symbol: str, **kwargs: Any) -> _Rows:
        self.calls.append(("capital_event", symbol, kwargs))
        start, end = _requested_dates(kwargs)
        return _Rows(
            [
                {"Date": (start.replace(day=1)).isoformat(), "Capital Event": 1},
                {"Date": start.isoformat(), "Capital Event": 1},
                {"Date": end.isoformat(), "Capital Event": 0},
            ],
            ("Date", "Capital Event"),
        )


def test_module_keeps_optional_norgate_import_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "thericher_v2.data.norgate_trial_daily_capability_probe"
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


def test_writes_precommitted_aggregate_only_external_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_root, repo, destination = _paths(tmp_path)
    client = _FakeNorgate()

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("capability probe crossed a forbidden boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("capability probe must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = _build(destination, market_root, repo, client)

    assert result.status == "qualified_for_offline_research"
    assert result.source_namespace == "norgate_trial_daily_offline_research_only"
    assert result.scope == {
        "offline_research_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "model_eligible": False,
        "gpu_eligible": False,
        "paper_trading_eligible": False,
        "pnl_eligible": False,
        "live_eligible": False,
    }
    assert require_attested_norgate_trial_daily_capability_probe(result) is result
    assert {path.name for path in destination.iterdir()} == {
        "precommit.json",
        "receipt.json",
        "DELETE_NORGATE_DATA_ON_EXPIRY.txt",
    }
    precommit = json.loads((destination / "precommit.json").read_text(encoding="utf-8"))
    receipt_text = (destination / "receipt.json").read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert precommit["constraints"]["raw_source_rows_persisted"] is False
    assert receipt["source_observations"]["cases"]["membership_change"]["membership"] == {
        "end": "2024-09-27",
        "false_count": 1,
        "latest_value": True,
        "required_fields_present": True,
        "row_count": 2,
        "start": "2024-09-18",
        "transition_count": 1,
        "true_count": 1,
    }
    assert receipt["receipt_constraints"]["raw_ohlcv_persisted"] is False
    assert "10.0" not in receipt_text
    assert "10.5" not in receipt_text
    assert (
        verify_norgate_trial_daily_capability_probe(
            destination, market_data_root=market_root, repo_root=repo
        ).receipt_hash
        == result.receipt_hash
    )
    assert [call[0] for call in client.calls].count("price") == 3
    price_call = next(call for call in client.calls if call[0] == "price")
    assert price_call[2]["stock_price_adjustment_setting"] == "none"
    assert price_call[2]["padding_setting"] == "none"
    assert price_call[2]["interval"] == "D"


def test_unqualified_membership_shape_cannot_be_promoted(tmp_path: Path) -> None:
    market_root, repo, destination = _paths(tmp_path)

    result = _build(destination, market_root, repo, _FakeNorgate(membership_change=False))

    assert result.status == "unqualified"
    receipt = json.loads((destination / "receipt.json").read_text(encoding="utf-8"))
    assert "in_horizon_membership_change_not_confirmed" in receipt["qualification_reasons"]
    assert receipt["scope"]["model_eligible"] is False
    assert receipt["scope"]["paper_trading_eligible"] is False


def test_unavailable_client_writes_only_a_categorical_receipt(tmp_path: Path) -> None:
    market_root, repo, destination = _paths(tmp_path)

    def unavailable() -> None:
        raise ModuleNotFoundError("norgatedata")

    result = _build(destination, market_root, repo, None, client_loader=unavailable)

    assert result.status == "input_unavailable"
    receipt = json.loads((destination / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["source_observations"] == {}
    assert receipt["qualification_reasons"] == ["source_client_unavailable"]
    assert receipt["source"]["package_version"] == "unavailable"


def test_rejects_git_destination_low_storage_and_receipt_tampering(tmp_path: Path) -> None:
    market_root, repo, destination = _paths(tmp_path)
    repo_under_market = market_root / "repo"
    repo_under_market.mkdir()
    with pytest.raises(NorgateTrialDailyCapabilityProbeError, match="outside Git"):
        _build(
            repo_under_market / destination.name,
            market_root,
            repo_under_market,
            _FakeNorgate(),
        )
    with pytest.raises(NorgateTrialDailyCapabilityProbeError, match="hard free-space"):
        _build(
            destination,
            market_root,
            repo,
            _FakeNorgate(),
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )

    result = _build(destination, market_root, repo, _FakeNorgate())
    receipt_path = result.receipt_dir / "receipt.json"
    receipt_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(NorgateTrialDailyCapabilityProbeError, match="receipt is invalid"):
        verify_norgate_trial_daily_capability_probe(
            result.receipt_dir,
            market_data_root=market_root,
            repo_root=repo,
        )


def test_database_build_fingerprint_uses_only_fixed_metadata_files(tmp_path: Path) -> None:
    data_root = tmp_path / "Norgate Data"
    data_root.mkdir()
    names = (
        "core_us.ngdb",
        "us.databaseinfo.cobra",
        "us.price.index.cobra",
        "us.ich.index.cobra",
        "us.dilutions.index.cobra",
    )
    for index, name in enumerate(names):
        (data_root / name).write_text(str(index), encoding="ascii")

    first = fingerprint_norgate_us_database_build(data_root)
    (data_root / "unrelated.price.data.cobra").write_text("ignored", encoding="ascii")

    assert fingerprint_norgate_us_database_build(data_root) == first
    assert first.startswith("sha256:")


def _build(
    destination: Path,
    market_root: Path,
    repo: Path,
    client: _FakeNorgate | None,
    *,
    client_loader: Any | None = None,
    disk_usage: Any | None = None,
):
    return build_norgate_trial_daily_capability_probe(
        destination=destination,
        retrieved_at_utc=datetime(2026, 8, 1, tzinfo=UTC),
        database_build_metadata_sha256="sha256:" + "1" * 64,
        market_data_root=market_root,
        repo_root=repo,
        client_loader=client_loader or (lambda: client),
        platform_name="win32",
        disk_usage=disk_usage or (lambda _path: SimpleNamespace(total=100, free=50)),
    )


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    market_root = tmp_path / "market_data"
    market_root.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    destination = (
        market_root
        / "us_equities"
        / "norgate_trial"
        / "daily_capability_probe"
        / "probe=20260801T000000Z-norgate-trial-daily-capability-r1"
    )
    return market_root, repo, destination


def _requested_dates(kwargs: dict[str, Any]) -> tuple[date, date]:
    return (date.fromisoformat(kwargs["start_date"]), date.fromisoformat(kwargs["end_date"]))
