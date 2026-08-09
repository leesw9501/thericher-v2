from __future__ import annotations

import json
import os
import socket
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from thericher_v2.data.norgate_trial_tail_readiness import (
    NORGATE_TAIL_MINIMUM_COMMON_SESSIONS,
    NorgateLocalDatabaseConfigurationError,
    NorgateTailReferenceObservation,
    NorgateTrialTailReadinessError,
    build_norgate_trial_tail_readiness_receipt,
    collect_norgate_tail_reference_observation,
    resolve_active_norgate_us_database_root,
    verify_norgate_trial_tail_readiness_receipt,
)


class _Rows:
    def __init__(self, sessions: list[date]) -> None:
        self.dtype = SimpleNamespace(names=("Date", "Open"))
        self._rows = [{"Date": session.isoformat(), "Open": "ignored"} for session in sessions]

    def __iter__(self):
        return iter(self._rows)


class _Client:
    __version__ = "fixture"

    class PaddingType:
        NONE = "none"

    class StockPriceAdjustmentType:
        NONE = "none"

    def __init__(
        self,
        sessions_by_symbol: dict[str, list[date]],
        *,
        databases: tuple[str, ...] = ("US Equities",),
    ) -> None:
        self._sessions_by_symbol = sessions_by_symbol
        self._databases = databases
        self.metadata_calls = 0
        self.price_calls = 0

    def databases(self) -> list[str]:
        return list(self._databases)

    def last_database_update_time(self, _database: str) -> datetime:
        self.metadata_calls += 1
        return datetime(2026, 8, 1, 18, 59, 55, tzinfo=UTC)

    def price_timeseries(self, symbol: str, **_kwargs: Any) -> _Rows:
        self.price_calls += 1
        return _Rows(self._sessions_by_symbol[symbol])


def test_short_tail_receipt_is_source_safe_and_replayable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = _sessions(date(2026, 6, 23), 28)
    observation = collect_norgate_tail_reference_observation(
        requested_end=date(2026, 8, 1),
        client_loader=lambda: _Client({symbol: sessions for symbol in ("SPY", "QQQ", "IWM")}),
    )
    root = tmp_path / "artifacts"
    root.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    active_root = tmp_path / "norgate"
    active_root.mkdir()

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("tail receipt must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    result = build_norgate_trial_tail_readiness_receipt(
        destination=root / "tail-fixture",
        observation=observation,
        active_database_root=active_root,
        database_build_metadata_sha256="sha256:" + "a" * 64,
        retrieved_at_utc=datetime(2026, 8, 2, tzinfo=UTC),
        artifact_root=root,
        repo_root=repo,
    )

    assert result.status == "input_unavailable"
    assert result.reason == "calendar_interval_below_predeclared_minimum"
    assert result.common_session_count == 28
    assert result.calendar_day_upper_bound == 40
    assert result.per_symbol_session_counts == {"SPY": 28, "QQQ": 28, "IWM": 28}
    summary = json.loads((result.receipt_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["rebuild_performed"] is False
    assert summary["membership_verification_performed"] is False
    assert summary["model_training_allowed"] is False
    assert "ignored" not in json.dumps(summary)
    assert verify_norgate_trial_tail_readiness_receipt(
        result.receipt_dir,
        artifact_root=root,
        repo_root=repo,
    ) == result


@pytest.mark.parametrize(
    ("databases", "reason"),
    [
        ((), "no_configured_databases"),
        (("AU Equities",), "us_equities_database_not_configured"),
    ],
)
def test_unusable_local_catalog_fails_before_metadata_or_price_reads(
    databases: tuple[str, ...], reason: str
) -> None:
    client = _Client(
        {symbol: [] for symbol in ("SPY", "QQQ", "IWM")},
        databases=databases,
    )

    with pytest.raises(NorgateLocalDatabaseConfigurationError) as raised:
        collect_norgate_tail_reference_observation(
            requested_end=date(2026, 8, 1),
            client_loader=lambda: client,
        )

    assert raised.value.reason == reason
    assert client.metadata_calls == 0
    assert client.price_calls == 0


def test_calendar_upper_bound_fails_before_a_panel_rebuild(tmp_path: Path) -> None:
    requested_start = date(2026, 6, 23)
    observation = NorgateTailReferenceObservation(
        package_version="fixture",
        source_update_at_utc=datetime(2026, 8, 1, tzinfo=UTC),
        requested_start=requested_start,
        requested_end=date(2026, 7, 1),
        sessions_by_symbol={symbol: () for symbol in ("SPY", "QQQ", "IWM")},
    )
    root = tmp_path / "artifacts"
    active_root = tmp_path / "norgate"
    active_root.mkdir()
    result = build_norgate_trial_tail_readiness_receipt(
        destination=root / "tail-empty",
        observation=observation,
        active_database_root=active_root,
        database_build_metadata_sha256="sha256:" + "b" * 64,
        retrieved_at_utc=datetime(2026, 8, 2, tzinfo=UTC),
        artifact_root=root,
    )

    assert result.status == "input_unavailable"
    assert result.common_session_count == 0
    assert result.calendar_day_upper_bound < NORGATE_TAIL_MINIMUM_COMMON_SESSIONS
    assert result.receipt_dir.parent == root


def test_tail_can_only_be_ready_after_calendar_and_common_session_minimum(tmp_path: Path) -> None:
    sessions = _sessions(date(2026, 6, 23), NORGATE_TAIL_MINIMUM_COMMON_SESSIONS)
    observation = NorgateTailReferenceObservation(
        package_version="fixture",
        source_update_at_utc=datetime(2026, 11, 1, tzinfo=UTC),
        requested_start=date(2026, 6, 23),
        requested_end=date(2026, 12, 1),
        sessions_by_symbol={symbol: sessions for symbol in ("SPY", "QQQ", "IWM")},
    )
    root = tmp_path / "artifacts"
    root.mkdir()
    active_root = tmp_path / "norgate"
    active_root.mkdir()
    result = build_norgate_trial_tail_readiness_receipt(
        destination=root / "tail-ready",
        observation=observation,
        active_database_root=active_root,
        database_build_metadata_sha256="sha256:" + "c" * 64,
        retrieved_at_utc=datetime(2026, 12, 2, tzinfo=UTC),
        artifact_root=root,
    )

    assert result.status == "ready"
    assert result.reason == "tail_minimum_attested"


def test_active_root_requires_one_timestamp_matching_candidate(tmp_path: Path) -> None:
    source_update = datetime(2026, 8, 1, 18, 59, 55, tzinfo=UTC)
    active = _database_root(tmp_path / "active", source_update)
    stale = _database_root(tmp_path / "stale", source_update - timedelta(days=1))

    assert resolve_active_norgate_us_database_root(
        source_update,
        candidates=(stale, active),
    ) == active.resolve()
    with pytest.raises(NorgateTrialTailReadinessError, match="unresolved"):
        resolve_active_norgate_us_database_root(source_update, candidates=(active, active))


def test_receipt_rejects_git_workspace_destination(tmp_path: Path) -> None:
    observation = NorgateTailReferenceObservation(
        package_version="fixture",
        source_update_at_utc=datetime(2026, 8, 1, tzinfo=UTC),
        requested_start=date(2026, 6, 23),
        requested_end=date(2026, 8, 1),
        sessions_by_symbol={symbol: () for symbol in ("SPY", "QQQ", "IWM")},
    )
    repo = tmp_path / "repo"
    root = repo / "artifacts"
    root.mkdir(parents=True)
    with pytest.raises(NorgateTrialTailReadinessError, match="outside the Git workspace"):
        build_norgate_trial_tail_readiness_receipt(
            destination=root / "tail-repo",
            observation=observation,
            active_database_root=tmp_path,
            database_build_metadata_sha256="sha256:" + "d" * 64,
            retrieved_at_utc=datetime(2026, 8, 2, tzinfo=UTC),
            artifact_root=root,
            repo_root=repo,
        )


def _sessions(start: date, count: int) -> list[date]:
    return [start + timedelta(days=index) for index in range(count)]


def _database_root(root: Path, timestamp: datetime) -> Path:
    root.mkdir()
    core = root / "core_us.ngdb"
    core.write_bytes(b"metadata")
    os.utime(core, (timestamp.timestamp(), timestamp.timestamp()))
    return root
