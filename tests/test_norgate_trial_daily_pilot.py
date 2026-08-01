from __future__ import annotations

import builtins
import importlib
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.data.norgate_trial_daily_capability_probe import (
    build_norgate_trial_daily_capability_probe,
)
from thericher_v2.data.norgate_trial_daily_pilot import (
    NorgateTrialDailyPilotError,
    build_norgate_trial_daily_pilot,
    load_attested_norgate_trial_daily_pilot_bars,
    require_attested_norgate_trial_daily_pilot_bars,
    verify_norgate_trial_daily_pilot,
)


class _Rows:
    def __init__(self, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
        self.dtype = SimpleNamespace(names=fields)
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeNorgate:
    __version__ = "test-norgate-1.0"

    class PaddingType:
        NONE = "none"

    class StockPriceAdjustmentType:
        NONE = "none"

    def __init__(
        self,
        *,
        membership_alignment: bool = True,
        source_guard: Any | None = None,
        source_failure: bool = False,
    ) -> None:
        self.membership_alignment = membership_alignment
        self.source_guard = source_guard
        self.source_failure = source_failure
        self.symbol_bases = {"AAPL": 101, "PLTR": 202, "AAL": 303}

    def watchlist_symbols(self, _watchlist: str) -> list[str]:
        self._source_called()
        return list(self.symbol_bases)

    def price_timeseries(self, symbol: str, **kwargs: object) -> _Rows:
        self._source_called()
        rows = []
        for index, session_date in enumerate(_sessions(kwargs)):
            base = 100 + index + self.symbol_bases[symbol] / 1000
            rows.append(
                {
                    "Date": session_date,
                    "Open": f"{base:.3f}",
                    "High": f"{base + 1:.3f}",
                    "Low": f"{base - 1:.3f}",
                    "Close": f"{base + 0.125:.3f}",
                    "Volume": str(1000 + index),
                    "Dividend": 0,
                }
            )
        return _Rows(("Date", "Open", "High", "Low", "Close", "Volume", "Dividend"), rows)

    def index_constituent_timeseries(self, symbol: str, _index: str, **kwargs: object) -> _Rows:
        self._source_called()
        dates = _sessions(kwargs)
        if not self.membership_alignment:
            dates = dates[:-1]
        rows = []
        for index, session_date in enumerate(dates):
            membership = 1 if symbol == "AAPL" else 0 if symbol == "AAL" else index >= 3
            rows.append(
                {
                    "Date": session_date,
                    "Index Constituent": membership,
                }
            )
        return _Rows(("Date", "Index Constituent"), rows)

    def major_exchange_listed_timeseries(self, _symbol: str, **kwargs: object) -> _Rows:
        self._source_called()
        rows = [
            {"Date": session_date, "Major Exchange Listed": 1}
            for session_date in _sessions(kwargs)
        ]
        return _Rows(("Date", "Major Exchange Listed"), rows)

    def capital_event_timeseries(self, _symbol: str, **kwargs: object) -> _Rows:
        self._source_called()
        rows = [
            {"Date": session_date, "Capital Event": 0} for session_date in _sessions(kwargs)
        ]
        return _Rows(("Date", "Capital Event"), rows)

    def _source_called(self) -> None:
        if self.source_guard is not None:
            self.source_guard()
        if self.source_failure:
            raise RuntimeError("source unavailable")


def test_module_keeps_optional_norgate_import_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "thericher_v2.data.norgate_trial_daily_pilot"
    original_import = builtins.__import__

    def guard_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "norgatedata":
            raise AssertionError("Norgate must remain an optional host-only import")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard_import)
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    module = importlib.import_module(module_name)

    assert module.NORGATE_TRIAL_DAILY_PILOT_ID == "norgate-trial-daily-pilot-v1"


def test_materializes_dated_raw_rows_outside_git_and_loads_dynamic_membership(
    tmp_path: Path,
) -> None:
    market_root, repo, capability = _qualified_capability(tmp_path)
    pilot = _build_pilot(market_root, repo, capability, _FakeNorgate())

    assert pilot.status == "qualified_for_offline_research"
    assert pilot.scope["offline_research_only"] is True
    assert pilot.scope["model_eligible"] is False
    assert {path.name for path in pilot.pilot_dir.iterdir()} == {
        "precommit.json",
        "manifest.json",
        "DELETE_NORGATE_DATA_ON_EXPIRY.txt",
        "d1_bars.csv.gz",
        "membership.csv.gz",
        "listing.csv.gz",
    }
    manifest_text = (pilot.pilot_dir / "manifest.json").read_text(encoding="utf-8")
    assert "100.101" not in manifest_text
    assert "100.202" not in manifest_text
    assert "100.303" not in manifest_text
    assert verify_norgate_trial_daily_pilot(
        pilot.pilot_dir, market_data_root=market_root, repo_root=repo
    ).manifest_hash == pilot.manifest_hash

    loaded = load_attested_norgate_trial_daily_pilot_bars(pilot)

    pltr_bars = loaded.bars_for_symbol("pltr")
    assert all(bar.timeframe is Timeframe.D1 and bar.complete for bar in pltr_bars)
    first_state = loaded.membership_state_at("PLTR", pltr_bars[0].start_ts.date())
    last_state = loaded.membership_state_at("PLTR", pltr_bars[-1].start_ts.date())
    assert first_state.index_constituent is False
    assert last_state.index_constituent is True
    assert last_state.major_exchange_listed is True
    with pytest.raises(ValueError, match="source-date state is unavailable"):
        loaded.membership_state_at("PLTR", date(2024, 10, 1))
    assert require_attested_norgate_trial_daily_pilot_bars(loaded) is loaded


def test_precommit_exists_before_any_source_call(tmp_path: Path) -> None:
    market_root, repo, capability = _qualified_capability(tmp_path)
    observed = []

    def source_guard() -> None:
        observed.append(any(market_root.rglob("precommit.json")))
        assert observed[-1] is True

    pilot = _build_pilot(
        market_root,
        repo,
        capability,
        _FakeNorgate(source_guard=source_guard),
    )

    assert pilot.status == "qualified_for_offline_research"
    assert observed


def test_rejects_date_misalignment_without_retaining_raw_rows(tmp_path: Path) -> None:
    market_root, repo, capability = _qualified_capability(tmp_path)
    pilot = _build_pilot(
        market_root,
        repo,
        capability,
        _FakeNorgate(membership_alignment=False),
        label="misaligned",
    )

    assert pilot.status == "unqualified"
    assert {path.name for path in pilot.pilot_dir.iterdir()} == {
        "precommit.json",
        "manifest.json",
        "DELETE_NORGATE_DATA_ON_EXPIRY.txt",
    }
    manifest = json.loads((pilot.pilot_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["qualification_reasons"] == ["source_date_alignment_unavailable"]
    assert manifest["files"] == {}
    outcome = manifest["case_outcomes"]
    assert outcome[0]["role"] == "current_member"
    assert outcome[0]["symbol"] == "AAPL"
    assert outcome[0]["reason"] == "source_date_alignment_unavailable"
    assert outcome[0]["aggregate"]["first_divergent_date"] == "2025-06-13"
    with pytest.raises(ValueError, match="not qualified"):
        load_attested_norgate_trial_daily_pilot_bars(pilot)


def test_loader_is_read_only_and_has_no_norgate_or_route_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_root, repo, capability = _qualified_capability(tmp_path)
    pilot = _build_pilot(market_root, repo, capability, _FakeNorgate())
    module = importlib.import_module("thericher_v2.data.norgate_trial_daily_pilot")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("loader crossed an external or write boundary")

    monkeypatch.setattr(module, "_load_norgatedata", fail)
    monkeypatch.setattr(Path, "write_bytes", fail)
    monkeypatch.setattr(Path, "write_text", fail)

    loaded = load_attested_norgate_trial_daily_pilot_bars(pilot)

    assert len(loaded.bars) > 0
    assert loaded.pilot.scope["paper_trading_eligible"] is False
    assert loaded.pilot.scope["gpu_eligible"] is False


def test_rejects_git_destination_and_tampered_payload(tmp_path: Path) -> None:
    market_root, repo, capability = _qualified_capability(tmp_path)
    repo_under_market = market_root / "repo"
    repo_under_market.mkdir()
    with pytest.raises(NorgateTrialDailyPilotError, match="outside Git"):
        build_norgate_trial_daily_pilot(
            destination=repo_under_market / "pilot=inside-git-norgate-trial-daily-pilot-r2",
            retrieved_at_utc=datetime(2026, 8, 1, tzinfo=UTC),
            capability_probe=capability,
            database_build_metadata_sha256="sha256:" + "1" * 64,
            market_data_root=market_root,
            repo_root=repo_under_market,
            client_loader=_FakeNorgate,
            platform_name="win32",
            disk_usage=_disk_usage,
        )

    pilot = _build_pilot(market_root, repo, capability, _FakeNorgate())
    path = pilot.pilot_dir / "membership.csv.gz"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(NorgateTrialDailyPilotError, match="hash mismatch"):
        verify_norgate_trial_daily_pilot(
            pilot.pilot_dir, market_data_root=market_root, repo_root=repo
        )


def _qualified_capability(
    tmp_path: Path,
) -> tuple[Path, Path, object]:
    market_root = tmp_path / "market"
    market_root.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    capability = build_norgate_trial_daily_capability_probe(
        destination=market_root
        / "us_equities"
        / "norgate_trial"
        / "daily_capability_probe"
        / "probe=unit-norgate-trial-daily-capability-r1",
        retrieved_at_utc=datetime(2026, 8, 1, tzinfo=UTC),
        database_build_metadata_sha256="sha256:" + "1" * 64,
        market_data_root=market_root,
        repo_root=repo,
        client_loader=_FakeNorgate,
        platform_name="win32",
        disk_usage=_disk_usage,
    )
    assert capability.status == "qualified_for_offline_research"
    return market_root, repo, capability


def _build_pilot(
    market_root: Path,
    repo: Path,
    capability: object,
    client: _FakeNorgate,
    *,
    label: str = "unit",
):
    return build_norgate_trial_daily_pilot(
        destination=market_root
        / "us_equities"
        / "norgate_trial"
        / "daily_pilot"
        / f"pilot={label}-norgate-trial-daily-pilot-r2",
        retrieved_at_utc=datetime(2026, 8, 1, tzinfo=UTC),
        capability_probe=capability,  # type: ignore[arg-type]
        database_build_metadata_sha256="sha256:" + "1" * 64,
        market_data_root=market_root,
        repo_root=repo,
        client_loader=lambda: client,
        platform_name="win32",
        disk_usage=_disk_usage,
    )


def _sessions(kwargs: dict[str, object]) -> list[date]:
    start = date.fromisoformat(str(kwargs["start_date"]))
    end = date.fromisoformat(str(kwargs["end_date"]))
    result = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _disk_usage(_path: str | Path) -> SimpleNamespace:
    return SimpleNamespace(total=100, free=50)
