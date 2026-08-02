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

from thericher_v2.data.norgate_membership import (
    NorgateMembershipSnapshotError,
    build_norgate_sp500_membership_snapshot,
    verify_norgate_sp500_membership_snapshot,
)


class _Dtype:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names


class _Rows:
    def __init__(self, rows: list[dict[str, Any]], names: tuple[str, ...] | None = None) -> None:
        self.dtype = _Dtype(names or ("Date", "Index Constituent"))
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeNorgate:
    class PaddingType:
        NONE = "none"

    __version__ = "test-version"

    def __init__(self, candidates: list[str], series: dict[str, _Rows]) -> None:
        self.candidates = candidates
        self.series = series
        self.watchlist_calls: list[str] = []
        self.membership_calls: list[tuple[str, str, dict[str, Any]]] = []

    def watchlist_symbols(self, watchlist: str) -> list[str]:
        self.watchlist_calls.append(watchlist)
        return self.candidates

    def index_constituent_timeseries(
        self, symbol: str, index_name: str, **kwargs: Any
    ) -> _Rows:
        self.membership_calls.append((symbol, index_name, kwargs))
        return self.series[symbol]


def _rows(*values: str) -> _Rows:
    return _Rows(
        [
            {"Date": values[index], "Index Constituent": values[index + 1]}
            for index in range(0, len(values), 2)
        ]
    )


def test_module_keeps_optional_norgate_import_lazy(monkeypatch) -> None:
    module_name = "thericher_v2.data.norgate_membership"
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


def test_builds_an_external_sparse_snapshot_with_exact_bounded_calls(
    tmp_path: Path, monkeypatch
) -> None:
    root = _market_root(tmp_path)
    client = _client()
    destination = _destination(root)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("membership snapshot must not cross this boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("membership snapshot must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = _build(destination, client, root)

    assert result.snapshot_dir == destination
    assert result.candidate_count == 2
    assert result.membership_row_count == 4
    assert result.actual_start == date(2024, 1, 2)
    assert result.actual_end == date(2024, 1, 3)
    assert result.package_version == "test-version"
    assert result.free_percent == 50.0
    assert client.watchlist_calls == ["S&P 500 Current & Past"]
    assert [call[:2] for call in client.membership_calls] == [
        ("AAA", "S&P 500"),
        ("BBB", "S&P 500"),
    ]
    assert all(
        kwargs
        == {
            "padding_setting": "none",
            "start_date": "2024-01-02",
            "end_date": "2024-01-03",
            "limit": -1,
            "timeseriesformat": "numpy-recarray",
        }
        for _symbol, _index, kwargs in client.membership_calls
    )

    candidate_rows = (destination / "candidate_union.csv").read_text(encoding="utf-8")
    assert candidate_rows.splitlines() == ["candidate_rank,symbol", "1,AAA", "2,BBB"]
    marker = (destination / "DELETE_NORGATE_DATA_ON_EXPIRY.txt").read_text(encoding="ascii")
    assert "operator must delete this snapshot directory" in marker
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["storage"]["root"] == str(root)
    assert manifest["scope"] == {
        "campaign_eligible": False,
        "direct_historical_universe_list": False,
        "model_eligible": False,
        "pit_eligible": False,
        "publication_time_proven": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
    }
    assert verify_norgate_sp500_membership_snapshot(
        destination, market_data_root=root, repo_root=tmp_path / "repo"
    ) == result
    assert list(tmp_path.rglob(".env*")) == []


@pytest.mark.parametrize(
    ("candidates", "series", "expected_count", "message"),
    [
        (["AAA"], {"AAA": _rows("2024-01-02", "1")}, 2, "tripwire"),
        (
            ["AAA", "BBB"],
            {
                "AAA": _rows("2024-01-02", "1"),
                "BBB": _Rows([], names=("Date",)),
            },
            2,
            "required fields",
        ),
        (
            ["AAA", "BBB"],
            {
                "AAA": _rows("2024-01-03", "1", "2024-01-02", "0"),
                "BBB": _rows("2024-01-02", "0"),
            },
            2,
            "strictly ordered",
        ),
        (
            ["AAA", "BBB"],
            {"AAA": _Rows([]), "BBB": _rows("2024-01-02", "0")},
            2,
            "empty",
        ),
    ],
)
def test_source_failure_never_publishes_a_partial_snapshot(
    tmp_path: Path,
    candidates: list[str],
    series: dict[str, _Rows],
    expected_count: int,
    message: str,
) -> None:
    root = _market_root(tmp_path)
    destination = _destination(root)
    client = _FakeNorgate(candidates, series)

    with pytest.raises(ValueError, match=message):
        _build(destination, client, root, expected_candidate_count=expected_count)

    assert not destination.exists()
    assert not list(destination.parent.glob(".*.staging-*"))


def test_unavailable_client_and_non_windows_fail_before_source_or_persistence(
    tmp_path: Path,
) -> None:
    root = _market_root(tmp_path)
    destination = _destination(root)
    calls = 0

    def unavailable() -> None:
        nonlocal calls
        calls += 1
        raise ModuleNotFoundError("norgatedata")

    with pytest.raises(NorgateMembershipSnapshotError, match="unavailable"):
        _build(destination, None, root, client_loader=unavailable)
    assert calls == 1
    assert not destination.exists()

    with pytest.raises(NorgateMembershipSnapshotError, match="requires Windows"):
        _build(destination, _client(), root, platform_name="linux")
    assert not destination.exists()


def test_rejects_low_disk_or_existing_destination_and_detects_tampering(tmp_path: Path) -> None:
    root = _market_root(tmp_path)
    destination = _destination(root)
    with pytest.raises(ValueError, match="hard free-space"):
        _build(
            destination,
            _client(),
            root,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )
    assert not destination.exists()

    result = _build(destination, _client(), root)
    with pytest.raises(FileExistsError, match="already exists"):
        _build(destination, _client(), root)
    matrix_path = result.snapshot_dir / "membership_matrix.csv.gz"
    matrix_path.write_bytes(matrix_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_norgate_sp500_membership_snapshot(
            result.snapshot_dir, market_data_root=root, repo_root=tmp_path / "repo"
        )


@pytest.mark.parametrize("scope_key", ("ranking_eligible", "sealed_holdout_eligible"))
def test_rejects_a_snapshot_that_claims_additional_eligibility(
    tmp_path: Path, scope_key: str
) -> None:
    root = _market_root(tmp_path)
    result = _build(_destination(root), _client(), root)
    manifest_path = result.snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scope"][scope_key] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="scope must stay ineligible"):
        verify_norgate_sp500_membership_snapshot(
            result.snapshot_dir, market_data_root=root, repo_root=tmp_path / "repo"
        )


def _build(
    destination: Path,
    client: _FakeNorgate | None,
    root: Path,
    *,
    expected_candidate_count: int = 2,
    client_loader: Any | None = None,
    platform_name: str = "win32",
    disk_usage: Any | None = None,
):
    return build_norgate_sp500_membership_snapshot(
        destination=destination,
        requested_start=date(2024, 1, 2),
        requested_end=date(2024, 1, 3),
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        market_data_root=root,
        repo_root=root.parent / "repo",
        expected_candidate_count=expected_candidate_count,
        client_loader=client_loader or (lambda: client),
        platform_name=platform_name,
        disk_usage=disk_usage or (lambda _path: SimpleNamespace(total=100, free=50)),
    )


def _market_root(tmp_path: Path) -> Path:
    root = tmp_path / "market_data"
    root.mkdir()
    return root


def _destination(root: Path) -> Path:
    return (
        root
        / "us_equities"
        / "norgate_membership"
        / "canonical"
        / "sp500_current_past"
        / "snapshot=2026-07-19-norgate-sp500-membership-r1"
    )


def _client() -> _FakeNorgate:
    return _FakeNorgate(
        ["BBB", "AAA"],
        {
            "AAA": _rows("2024-01-02", "1", "2024-01-03", "0"),
            "BBB": _rows("2024-01-02", "0", "2024-01-03", "1"),
        },
    )
