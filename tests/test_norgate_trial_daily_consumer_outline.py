from __future__ import annotations

import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from thericher_v2.data.norgate_trial_daily_capability_probe import (
    build_norgate_trial_daily_capability_probe,
)
from thericher_v2.research.norgate_trial_daily_consumer_outline import (
    NORGATE_TRIAL_DAILY_CONSUMER_OUTLINE_ID,
    build_norgate_trial_daily_consumer_outline,
    require_attested_norgate_trial_daily_consumer_outline,
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

    def watchlist_symbols(self, _watchlist: str) -> list[str]:
        return ["AAL", "AAPL", "PLTR"]

    def index_constituent_timeseries(self, symbol: str, _index_name: str, **kwargs: Any) -> _Rows:
        if symbol == "AAPL":
            values = (1, 1)
        elif symbol == "PLTR" and self.membership_change:
            values = (0, 1)
        elif symbol == "PLTR":
            values = (1, 1)
        else:
            values = (0, 0)
        return _Rows(
            [
                {"Date": session, "Index Constituent": value}
                for session, value in zip(_dates(kwargs), values, strict=True)
            ],
            ("Date", "Index Constituent"),
        )

    def major_exchange_listed_timeseries(self, _symbol: str, **kwargs: Any) -> _Rows:
        return _Rows(
            [{"Date": session, "Major Exchange Listed": 1} for session in _dates(kwargs)],
            ("Date", "Major Exchange Listed"),
        )

    def price_timeseries(self, _symbol: str, **kwargs: Any) -> _Rows:
        return _Rows(
            [
                {
                    "Date": session,
                    "Open": "10",
                    "High": "11",
                    "Low": "9",
                    "Close": "10",
                    "Volume": "100",
                }
                for session in _dates(kwargs)
            ],
            ("Date", "Open", "High", "Low", "Close", "Volume"),
        )

    def capital_event_timeseries(self, _symbol: str, **kwargs: Any) -> _Rows:
        start, end = _dates(kwargs)
        return _Rows(
            [
                {"Date": start, "Capital Event": 0},
                {"Date": end, "Capital Event": 0},
            ],
            ("Date", "Capital Event"),
        )


def _dates(kwargs: dict[str, Any]) -> tuple[str, str]:
    return kwargs["start_date"], kwargs["end_date"]


def test_builds_only_a_non_executable_kis_shaped_daily_outline(tmp_path: Path) -> None:
    probe = _qualified_probe(tmp_path)

    outline = build_norgate_trial_daily_consumer_outline(probe)

    assert outline.outline_id == NORGATE_TRIAL_DAILY_CONSUMER_OUTLINE_ID
    assert outline.completed_bar_rule == "consume completed D1 OHLCV only"
    assert "next US regular-session open" in outline.causal_decision_timestamp_rule
    assert "chronological" in outline.temporal_split_rule
    assert "KIS Paper cost" in outline.cost_rule
    assert outline.naive_baseline == "always_flat"
    assert "availability timestamp" in outline.strongest_leakage_kill_test
    assert outline.model_eligible is False
    assert outline.gpu_eligible is False
    assert outline.ranking_eligible is False
    assert outline.paper_trading_eligible is False
    assert require_attested_norgate_trial_daily_consumer_outline(outline) is outline


def test_rejects_unqualified_source_and_route_widening(tmp_path: Path) -> None:
    market_root = tmp_path / "market_data"
    market_root.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    result = build_norgate_trial_daily_capability_probe(
        destination=market_root
        / "us_equities"
        / "norgate_trial"
        / "daily_capability_probe"
        / "probe=20260801T010000Z-norgate-trial-daily-capability-r1",
        retrieved_at_utc=datetime(2026, 8, 1, tzinfo=UTC),
        database_build_metadata_sha256="sha256:" + "2" * 64,
        market_data_root=market_root,
        repo_root=repo,
        client_loader=lambda: _FakeNorgate(membership_change=False),
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )

    with pytest.raises(ValueError, match="not qualified"):
        build_norgate_trial_daily_consumer_outline(result)

    qualified = _qualified_probe(tmp_path)
    with pytest.raises(ValueError, match="offline research only"):
        build_norgate_trial_daily_consumer_outline(qualified, requested_use="paper")


def test_outline_needs_no_network_credentials_or_broker_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _qualified_probe(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("consumer outline crossed a forbidden boundary")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", fail)
    monkeypatch.setattr(Path, "write_text", fail)
    monkeypatch.setattr(Path, "write_bytes", fail)

    outline = build_norgate_trial_daily_consumer_outline(probe)

    assert outline.source_namespace == "norgate_trial_daily_offline_research_only"


def _qualified_probe(tmp_path: Path):
    market_root = tmp_path / "market_data"
    market_root.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    return build_norgate_trial_daily_capability_probe(
        destination=market_root
        / "us_equities"
        / "norgate_trial"
        / "daily_capability_probe"
        / "probe=20260801T000000Z-norgate-trial-daily-capability-r1",
        retrieved_at_utc=datetime(2026, 8, 1, tzinfo=UTC),
        database_build_metadata_sha256="sha256:" + "3" * 64,
        market_data_root=market_root,
        repo_root=repo,
        client_loader=_FakeNorgate,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
