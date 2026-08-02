from __future__ import annotations

import builtins
import hashlib
import importlib
import json
import runpy
import socket
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import thericher_v2.data.norgate_membership_reattest as reattest_module
from thericher_v2.data.norgate_membership import build_norgate_sp500_membership_snapshot
from thericher_v2.data.norgate_membership_reattest import (
    NorgateMembershipReattestationError,
    reattest_norgate_sp500_membership_snapshot,
)

runner_main = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "reattest_norgate_membership_snapshot.py")
)["main"]


class _Dtype:
    names = ("Date", "Index Constituent")


class _Rows:
    dtype = _Dtype()

    def __init__(self, values: list[dict[str, str]]) -> None:
        self._values = values

    def __iter__(self):
        return iter(self._values)


class _FakeNorgate:
    class PaddingType:
        NONE = "none"

    __version__ = "test-version"

    def watchlist_symbols(self, _watchlist: str) -> list[str]:
        return ["AAA", "BBB"]

    def index_constituent_timeseries(
        self, symbol: str, _index_name: str, **_kwargs: Any
    ) -> _Rows:
        return _Rows(
            [
                {"Date": "2024-01-02", "Index Constituent": "1" if symbol == "AAA" else "0"},
                {"Date": "2024-01-03", "Index Constituent": "0" if symbol == "AAA" else "1"},
            ]
        )


@pytest.fixture
def snapshot(tmp_path: Path) -> tuple[Path, Path, Path]:
    market_data_root = tmp_path / "market_data"
    market_data_root.mkdir()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot_dir = (
        market_data_root
        / "us_equities"
        / "norgate_membership"
        / "canonical"
        / "sp500_current_past"
        / "snapshot=2026-08-03-norgate-sp500-membership-r1"
    )
    build_norgate_sp500_membership_snapshot(
        destination=snapshot_dir,
        requested_start=date(2024, 1, 2),
        requested_end=date(2024, 1, 3),
        retrieved_at_utc=datetime(2026, 8, 3, tzinfo=UTC),
        market_data_root=market_data_root,
        repo_root=repo_root,
        expected_candidate_count=2,
        client_loader=_FakeNorgate,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    return snapshot_dir, market_data_root, repo_root


def test_writes_one_redacted_read_only_receipt_without_external_access(
    snapshot: tuple[Path, Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_dir, market_data_root, repo_root = snapshot
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    source_before = _source_hashes(snapshot_dir)
    original_import = builtins.__import__
    original_read_bytes = Path.read_bytes

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("reattestation must stay offline")

    def guard_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "norgatedata":
            raise AssertionError("reattestation must not import Norgate")
        return original_import(name, *args, **kwargs)

    def guard_read_bytes(path: Path, *args: object, **kwargs: object) -> bytes:
        if path.name.startswith(".env"):
            raise AssertionError("reattestation must not read credentials")
        return original_read_bytes(path, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "norgatedata", raising=False)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(builtins, "__import__", guard_import)
    monkeypatch.setattr(Path, "read_bytes", guard_read_bytes)

    result = reattest_norgate_sp500_membership_snapshot(
        snapshot_dir=snapshot_dir,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
        attempt_id="offline-r1",
        created_at_utc=datetime(2026, 8, 3, tzinfo=UTC),
    )

    receipt_bytes = result.receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    assert result.status == "reattested"
    assert result.receipt_path is not None
    assert result.receipt_sha256 is not None
    assert result.receipt_sha256 == "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
    assert receipt["source_read_only"] is True
    assert receipt["source_identity"]["unchanged"] is True
    assert receipt["scope"] == {
        "campaign_eligible": False,
        "direct_historical_universe_list": False,
        "model_eligible": False,
        "pit_eligible": False,
        "publication_time_proven": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
    }
    assert str(tmp_path) not in receipt_bytes.decode("utf-8")
    assert "AAA" not in receipt_bytes.decode("utf-8")
    assert "BBB" not in receipt_bytes.decode("utf-8")
    assert source_before == _source_hashes(snapshot_dir)
    assert "norgatedata" not in sys.modules


def test_rejects_git_and_symlink_artifact_roots(
    snapshot: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    snapshot_dir, market_data_root, repo_root = snapshot
    (repo_root / "artifacts").mkdir()
    with pytest.raises(NorgateMembershipReattestationError, match="outside Git"):
        _reattest(
            snapshot_dir,
            market_data_root,
            repo_root / "artifacts",
            repo_root,
            attempt_id="in-repo-r1",
        )
    market_artifacts = market_data_root / "artifacts"
    market_artifacts.mkdir()
    with pytest.raises(NorgateMembershipReattestationError, match="outside market data"):
        _reattest(
            snapshot_dir,
            market_data_root,
            market_artifacts,
            repo_root,
            attempt_id="in-market-data-r1",
        )

    real_root = tmp_path / "real-artifacts"
    real_root.mkdir()
    link_root = tmp_path / "artifact-link"
    try:
        link_root.symlink_to(real_root, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(NorgateMembershipReattestationError, match="symlink"):
        _reattest(
            snapshot_dir,
            market_data_root,
            link_root,
            repo_root,
            attempt_id="symlink-r1",
        )


def test_receipt_is_immutable_and_requires_an_external_existing_root(
    snapshot: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    snapshot_dir, market_data_root, repo_root = snapshot
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _reattest(snapshot_dir, market_data_root, artifact_root, repo_root, attempt_id="once-r1")
    with pytest.raises(FileExistsError, match="already exists"):
        _reattest(snapshot_dir, market_data_root, artifact_root, repo_root, attempt_id="once-r1")
    with pytest.raises(NorgateMembershipReattestationError, match="existing directory"):
        _reattest(
            snapshot_dir,
            market_data_root,
            tmp_path / "missing-artifacts",
            repo_root,
            attempt_id="missing-r1",
        )


def test_module_keeps_optional_norgate_import_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "thericher_v2.data.norgate_membership_reattest"
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


def test_source_failures_are_categorical_and_never_publish_a_receipt(
    snapshot: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    snapshot_dir, market_data_root, repo_root = snapshot
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    unavailable = reattest_norgate_sp500_membership_snapshot(
        snapshot_dir=tmp_path / "missing-snapshot",
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
        attempt_id="missing-r1",
        created_at_utc=datetime(2026, 8, 3, tzinfo=UTC),
    )
    assert unavailable.status == "input_unavailable"
    assert unavailable.receipt_path is None

    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scope"]["ranking_eligible"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    malformed = reattest_norgate_sp500_membership_snapshot(
        snapshot_dir=snapshot_dir,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
        attempt_id="malformed-r1",
        created_at_utc=datetime(2026, 8, 3, tzinfo=UTC),
    )
    assert malformed.status == "integrity_mismatch"
    assert malformed.receipt_path is None
    assert not list(artifact_root.iterdir())


def test_changed_source_identity_is_categorical(
    snapshot: tuple[Path, Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_dir, market_data_root, repo_root = snapshot
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    original = reattest_module.verify_norgate_sp500_membership_snapshot
    calls = 0

    def changed(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        return result if calls == 1 else replace(result, package_version="changed")

    monkeypatch.setattr(reattest_module, "verify_norgate_sp500_membership_snapshot", changed)
    result = reattest_norgate_sp500_membership_snapshot(
        snapshot_dir=snapshot_dir,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
        attempt_id="changed-r1",
        created_at_utc=datetime(2026, 8, 3, tzinfo=UTC),
    )
    assert result.status == "integrity_mismatch"
    assert result.receipt_path is None
    assert not list(artifact_root.iterdir())


def test_runner_emits_source_safe_categorical_failure(
    snapshot: tuple[Path, Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _snapshot_dir, market_data_root, repo_root = snapshot
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    runner_main(
        [
            "--snapshot-dir",
            str(tmp_path / "not-present"),
            "--market-data-root",
            str(market_data_root),
            "--artifact-root",
            str(artifact_root),
            "--repo-root",
            str(repo_root),
            "--attempt-id",
            "runner-missing-r1",
        ]
    )
    assert capsys.readouterr().out == '{"status": "input_unavailable"}\n'


def _reattest(
    snapshot_dir: Path,
    market_data_root: Path,
    artifact_root: Path,
    repo_root: Path,
    *,
    attempt_id: str,
) -> None:
    reattest_norgate_sp500_membership_snapshot(
        snapshot_dir=snapshot_dir,
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
        attempt_id=attempt_id,
        created_at_utc=datetime(2026, 8, 3, tzinfo=UTC),
    )


def _source_hashes(snapshot_dir: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(snapshot_dir.iterdir())
        if path.is_file()
    }
