from __future__ import annotations

import builtins
import gzip
import hashlib
import json
import os
import shutil
import socket
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import thericher_v2.data.norgate_trial_development_panel as panel_module
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.norgate_membership import build_norgate_sp500_membership_snapshot
from thericher_v2.data.norgate_trial_development_panel import (
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_COMMON_SESSION_COUNT,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_END,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SELECTED_SYMBOL_COUNT,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_START,
    build_norgate_trial_development_panel_snapshot,
    default_norgate_trial_development_panel_snapshot_dir,
    load_verified_norgate_trial_development_panel_catalog,
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


def test_reattests_parent_lineage_from_a_different_market_data_mount(tmp_path: Path) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)
    result = _build(destination, root, repo, membership, calendar)
    mounted_root = tmp_path / "mounted" / root.name
    mounted_root.parent.mkdir()
    shutil.copytree(root, mounted_root)
    mounted_panel = mounted_root / destination.relative_to(root)
    manifest_path = mounted_panel / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for parent_key in ("membership_parent", "calendar_parent"):
        original = Path(manifest[parent_key]["snapshot_dir"])
        relative = original.relative_to(root)
        manifest[parent_key]["snapshot_dir"] = "D:\\market_data\\" + "\\".join(
            relative.parts
        )
    _write_manifest(manifest_path, manifest)

    loaded = verify_norgate_trial_development_panel_snapshot(
        mounted_panel,
        market_data_root=mounted_root,
        repo_root=repo,
    )

    assert loaded.dataset_hash == result.dataset_hash
    assert loaded.selected_symbol_count == result.selected_symbol_count
    assert loaded.membership_snapshot_dir.is_relative_to(mounted_root)
    assert loaded.calendar_snapshot_dir.is_relative_to(mounted_root)


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


def test_loads_read_only_catalog_without_network_sdk_credentials_or_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)
    result = _build(destination, root, repo, membership, calendar)
    artifact_root = tmp_path / "model-artifacts"
    before = _file_bytes(root)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("catalog loader crossed a forbidden boundary")

    original_import = builtins.__import__
    original_read_text = Path.read_text

    def guard_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "norgatedata" or name.startswith("norgatedata."):
            raise AssertionError("catalog loader must not import norgatedata")
        return original_import(name, *args, **kwargs)

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("catalog loader must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setenv("THERICHER_HOST_MODEL_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.setenv("THERICHER_MODEL_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.setattr(builtins, "__import__", guard_import)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    catalog = load_verified_norgate_trial_development_panel_catalog(
        destination,
        expected_dataset_id=_dataset_id(destination),
        expected_dataset_hash=result.dataset_hash,
        market_data_root=root,
        repo_root=repo,
    )

    assert catalog.source.dataset_id == _dataset_id(destination)
    assert catalog.source.dataset_hash == result.dataset_hash
    assert catalog.source.manifest_hash == result.manifest_hash
    assert catalog.source.provider == "Norgate Data"
    assert catalog.source.interval == "D"
    assert catalog.source.adjustment_semantics_verified is False
    assert catalog.candidate_count == 3
    assert catalog.selected_symbol_count == 2
    assert dict(catalog.candidate_ranks_by_symbol) == {"AAA": 1, "BBB": 2}
    assert tuple(catalog.bars_by_symbol) == ("AAA", "BBB")
    assert all(isinstance(series, CatalogedBars) for series in catalog.bars_by_symbol.values())
    assert all(
        series.dataset_hash == result.dataset_hash
        and series.source_path == destination / "panel_ohlcv_1d.csv.gz"
        and tuple(bar.start_ts.date() for bar in series.bars) == catalog.common_sessions
        for series in catalog.bars_by_symbol.values()
    )
    assert tuple(type(catalog.scope).__dataclass_fields__) == (
        "development_panel_attested",
        "development_training_eligible",
        "point_in_time_eligible",
        "ranking_eligible",
        "sealed_holdout_eligible",
        "campaign_eligible",
        "model_eligible",
        "gpu_eligible",
        "paper_trading_eligible",
    )
    assert catalog.scope.development_panel_attested is True
    assert catalog.scope.development_training_eligible is True
    assert catalog.scope.point_in_time_eligible is False
    assert catalog.scope.ranking_eligible is False
    assert catalog.scope.sealed_holdout_eligible is False
    assert catalog.scope.campaign_eligible is False
    assert catalog.scope.model_eligible is False
    assert catalog.scope.gpu_eligible is False
    assert catalog.scope.paper_trading_eligible is False
    with pytest.raises(TypeError):
        catalog.candidate_ranks_by_symbol["TAMPERED"] = 4  # type: ignore[index]
    with pytest.raises(TypeError):
        catalog.bars_by_symbol["TAMPERED"] = catalog.bars_by_symbol["AAA"]  # type: ignore[index]
    assert _file_bytes(root) == before
    assert not artifact_root.exists()


def test_catalog_preserves_nonsequential_candidate_ranks(tmp_path: Path) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)

    def load_bars(symbol: str, _start: date, _end: date) -> Sequence[Bar]:
        if symbol == "BBB":
            raise RuntimeError("unavailable")
        return _bars(symbol)

    result = _build(
        destination,
        root,
        repo,
        membership,
        calendar,
        load_bars=load_bars,
    )
    catalog = load_verified_norgate_trial_development_panel_catalog(
        destination,
        expected_dataset_id=_dataset_id(destination),
        expected_dataset_hash=result.dataset_hash,
        market_data_root=root,
        repo_root=repo,
    )

    assert dict(catalog.candidate_ranks_by_symbol) == {"AAA": 1, "CCC": 3}
    assert tuple(catalog.bars_by_symbol) == ("AAA", "CCC")
    assert catalog.bars_by_symbol["CCC"].bars == tuple(_bars("CCC"))


def test_catalog_requires_matching_expected_identity(tmp_path: Path) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)
    result = _build(destination, root, repo, membership, calendar)

    with pytest.raises(ValueError, match="dataset id mismatch"):
        load_verified_norgate_trial_development_panel_catalog(
            destination,
            expected_dataset_id="unexpected.dataset",
            expected_dataset_hash=result.dataset_hash,
            market_data_root=root,
            repo_root=repo,
        )
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        load_verified_norgate_trial_development_panel_catalog(
            destination,
            expected_dataset_id=_dataset_id(destination),
            expected_dataset_hash="sha256:" + "0" * 64,
            market_data_root=root,
            repo_root=repo,
        )


def test_catalog_uses_verified_panel_bytes_after_source_file_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)
    result = _build(destination, root, repo, membership, calendar)
    original_read_verified_file = panel_module._read_verified_file

    def swap_after_verified_read(
        snapshot: Path,
        document: object,
        *,
        expected_name: str,
        label: str,
    ) -> bytes:
        data = original_read_verified_file(
            snapshot,
            document,
            expected_name=expected_name,
            label=label,
        )
        if label == "panel data":
            (destination / "panel_ohlcv_1d.csv.gz").write_bytes(b"replaced-after-attestation")
        return data

    monkeypatch.setattr(panel_module, "_read_verified_file", swap_after_verified_read)
    catalog = load_verified_norgate_trial_development_panel_catalog(
        destination,
        expected_dataset_id=_dataset_id(destination),
        expected_dataset_hash=result.dataset_hash,
        market_data_root=root,
        repo_root=repo,
    )

    assert tuple(catalog.bars_by_symbol) == ("AAA", "BBB")
    assert catalog.bars_by_symbol["AAA"].bars == tuple(_bars("AAA"))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.replace("candidate_rank", "candidate_position", 1), "schema"),
        (lambda value: value.replace("\n1,AAA,", "\n2,AAA,", 1), "ordering"),
        (lambda value: value.replace("\n1,AAA,", "\n1,TAMPERED,", 1), "selected rows"),
        (
            lambda value: value.replace(
                "\n1,AAA,2024-01-03,", "\n1,AAA,2024-01-02,", 1
            ),
            "ordering",
        ),
        (
            lambda value: value.replace(
                "\n1,AAA,2024-01-03,", "\n1,AAA,2024-01-04,", 1
            ),
            "selected rows",
        ),
    ],
    ids=("schema", "rank", "symbol", "duplicate", "common-session"),
)
def test_catalog_rejects_self_consistent_semantic_panel_corruption(
    tmp_path: Path,
    mutate: Callable[[str], str],
    message: str,
) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)
    _build(destination, root, repo, membership, calendar)
    tampered_hash = _rewrite_panel_data(destination, mutate)

    with pytest.raises(ValueError, match=message):
        load_verified_norgate_trial_development_panel_catalog(
            destination,
            expected_dataset_id=_dataset_id(destination),
            expected_dataset_hash=tampered_hash,
            market_data_root=root,
            repo_root=repo,
        )


def test_catalog_rejects_panel_hash_tampering(tmp_path: Path) -> None:
    root, repo, membership, calendar, destination = _parents(tmp_path)
    result = _build(destination, root, repo, membership, calendar)
    data_path = destination / "panel_ohlcv_1d.csv.gz"
    data_path.write_bytes(data_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="panel data hash mismatch"):
        load_verified_norgate_trial_development_panel_catalog(
            destination,
            expected_dataset_id=_dataset_id(destination),
            expected_dataset_hash=result.dataset_hash,
            market_data_root=root,
            repo_root=repo,
        )


def test_loads_frozen_external_panel_when_available() -> None:
    if not FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR.is_dir():
        pytest.skip("frozen Norgate trial panel is not available on this host")

    catalog = load_verified_norgate_trial_development_panel_catalog(
        FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
        expected_dataset_id=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
        expected_dataset_hash=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
    )

    assert catalog.source.snapshot_dir == FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR
    assert (
        catalog.selected_symbol_count
        == FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SELECTED_SYMBOL_COUNT
    )
    assert (
        len(catalog.bars_by_symbol)
        == FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SELECTED_SYMBOL_COUNT
    )
    assert (
        len(catalog.common_sessions)
        == FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_COMMON_SESSION_COUNT
    )
    assert catalog.common_sessions[0] == FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_START
    assert catalog.common_sessions[-1] == FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_END
    assert sum(len(series.bars) for series in catalog.bars_by_symbol.values()) == 252_609
    assert catalog.scope.model_eligible is False
    assert catalog.scope.gpu_eligible is False
    assert catalog.scope.paper_trading_eligible is False


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


def _dataset_id(snapshot: Path) -> str:
    return f"us_equities.norgate_trial_broad_development_panel.1d.{snapshot.name}"


def _file_bytes(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _rewrite_panel_data(snapshot: Path, mutate: Callable[[str], str]) -> str:
    data_path = snapshot / "panel_ohlcv_1d.csv.gz"
    source = gzip.decompress(data_path.read_bytes()).decode("utf-8")
    rewritten = mutate(source)
    if rewritten == source:
        raise AssertionError("test mutation did not alter panel data")
    data = gzip.compress(rewritten.encode("utf-8"), mtime=0)
    data_path.write_bytes(data)
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_hash"] = digest
    manifest["files"]["panel_ohlcv"]["sha256"] = digest
    manifest["files"]["panel_ohlcv"]["size_bytes"] = len(data)
    _write_manifest(manifest_path, manifest)
    return digest
