from __future__ import annotations

import json
import socket
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_membership import build_norgate_sp500_membership_snapshot
from thericher_v2.data.norgate_trial_development_panel import (
    build_norgate_trial_development_panel_snapshot,
    default_norgate_trial_development_panel_snapshot_dir,
    verify_norgate_trial_development_panel_snapshot,
)
from thericher_v2.data.norgate_trial_raw_d1 import (
    NorgateCapitalEventEvidence,
    build_norgate_trial_raw_d1_snapshot,
)

_START = date(2024, 1, 2)
_END = date(2024, 1, 3)
_CANDIDATES = ("AAA", "BBB", "CCC")


class _Dtype:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.dtype = _Dtype(("Date", "Index Constituent"))
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _MembershipClient:
    class PaddingType:
        NONE = "none"

    __version__ = "test-version"

    def watchlist_symbols(self, _watchlist: str) -> list[str]:
        return list(_CANDIDATES)

    def index_constituent_timeseries(
        self, symbol: str, _index_name: str, **_kwargs: Any
    ) -> _Rows:
        return _Rows(
            [
                {"Date": _START.isoformat(), "Index Constituent": int(symbol != "CCC")},
                {"Date": _END.isoformat(), "Index Constituent": int(symbol != "CCC")},
            ]
        )


def test_builds_external_static_panel_without_network_or_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("development panel crossed a forbidden boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("development panel must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    result = _build(destination, root, repo, membership, calendar)

    assert result.snapshot_dir == destination
    assert result.candidate_count == 3
    assert result.selected_symbol_count == 2
    assert result.session_mismatch_count == 1
    assert result.development_training_eligible is True
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    availability = (destination / "candidate_availability.csv").read_text(encoding="utf-8")
    assert manifest["static_panel_contract"]["threshold_is_not_coverage_or_quality_proof"] is True
    assert manifest["static_panel_contract"]["membership_values_used_for_selection"] is False
    assert manifest["scope"]["development_training_eligible"] is True
    assert manifest["scope"]["gpu_eligible"] is False
    assert availability.splitlines() == [
        "candidate_rank,symbol,status,returned_row_count",
        "1,AAA,selected,2",
        "2,BBB,selected,2",
        "3,CCC,session_mismatch,1",
    ]
    assert verify_norgate_trial_development_panel_snapshot(
        destination,
        market_data_root=root,
        repo_root=repo,
    ) == result


def test_retains_noneligible_source_evidence_and_rejects_tampering(tmp_path: Path) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)
    result = _build(
        destination,
        root,
        repo,
        membership,
        calendar,
        load_bars=lambda _symbol, _start, _end: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )

    assert result.selected_symbol_count == 0
    assert result.unavailable_count == 3
    assert result.development_training_eligible is False
    path = result.snapshot_dir / "panel_ohlcv_1d.csv.gz"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_norgate_trial_development_panel_snapshot(
            result.snapshot_dir,
            market_data_root=root,
        repo_root=repo,
    )


def test_rejects_manifest_dataset_hash_and_limitations_tampering(tmp_path: Path) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)
    result = _build(destination, root, repo, membership, calendar)
    manifest_path = result.snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    manifest["dataset_hash"] = "sha256:" + "0" * 64
    _write_manifest(manifest_path, manifest)
    with pytest.raises(ValueError, match="dataset hash is inconsistent"):
        verify_norgate_trial_development_panel_snapshot(
            result.snapshot_dir,
            market_data_root=root,
            repo_root=repo,
        )

    manifest["dataset_hash"] = result.dataset_hash
    manifest["limitations"] = []
    _write_manifest(manifest_path, manifest)
    with pytest.raises(ValueError, match="limitations are invalid"):
        verify_norgate_trial_development_panel_snapshot(
            result.snapshot_dir,
            market_data_root=root,
            repo_root=repo,
        )


def test_rejects_bad_calendar_response_low_storage_and_git_destination(tmp_path: Path) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)

    with pytest.raises(FileExistsError, match="destination already exists"):
        destination.mkdir(parents=True)
        _build(destination, root, repo, membership, calendar)

    fresh_root, fresh_repo, membership, calendar, destination = _parents(tmp_path / "fresh")
    with pytest.raises(ValueError, match="hard free-space"):
        _build(
            destination,
            fresh_root,
            fresh_repo,
            membership,
            calendar,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )

    with pytest.raises(ValueError, match="under market data"):
        _build(repo / destination.name, root, repo, membership, calendar)


def test_default_destination_is_external() -> None:
    assert default_norgate_trial_development_panel_snapshot_dir(date(2026, 7, 19)) == Path(
        "D:/market_data/us_equities/norgate_trial_broad_development_panel/canonical/ohlcv_1d/"
        "snapshot=2026-07-19-norgate-trial-broad-d1-panel-r1"
    )


def _parents(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    root = tmp_path / "market_data"
    root.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    membership = root / "membership" / "snapshot=2026-07-19-norgate-sp500-membership-r1"
    build_norgate_sp500_membership_snapshot(
        destination=membership,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        expected_candidate_count=len(_CANDIDATES),
        client_loader=_MembershipClient,
        market_data_root=root,
        repo_root=repo,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    calendar = root / "calendar" / "snapshot=2026-07-19-norgate-trial-raw-d1-r2"
    build_norgate_trial_raw_d1_snapshot(
        destination=calendar,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        norgate_bars=lambda symbol, _start, _end: _bars(symbol),
        capital_event_evidence=lambda _symbol, _start, _end: _events(),
        norgate_package_version="test-version",
        market_data_root=root,
        repo_root=repo,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    destination = root / "panel" / "snapshot=2026-07-19-norgate-trial-broad-d1-panel-r1"
    return root, repo, membership, calendar, destination


def _build(
    destination: Path,
    root: Path,
    repo: Path,
    membership: Path,
    calendar: Path,
    *,
    load_bars: Callable[[str, date, date], Sequence[Bar]] = (
        lambda symbol, _start, _end: _candidate_bars(symbol)
    ),
    disk_usage: Any | None = None,
):
    return build_norgate_trial_development_panel_snapshot(
        destination=destination,
        membership_snapshot=membership,
        calendar_snapshot=calendar,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        load_bars=load_bars,
        norgate_package_version="test-version",
        minimum_selected_symbols=2,
        market_data_root=root,
        repo_root=repo,
        platform_name="win32",
        disk_usage=disk_usage or (lambda _path: SimpleNamespace(total=100, free=50)),
    )


def _candidate_bars(symbol: str) -> Sequence[Bar]:
    return _bars(symbol) if symbol != "CCC" else [_bar(symbol, _START)]


def _bars(symbol: str) -> list[Bar]:
    return [_bar(symbol, _START), _bar(symbol, _END)]


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


def _events() -> NorgateCapitalEventEvidence:
    return NorgateCapitalEventEvidence(
        returned_row_count=2,
        returned_start=_START,
        returned_end=_END,
        clipped_session_count=2,
        marker_dates=(),
    )


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
