from __future__ import annotations

import ast
import importlib.util
import json
import socket
import subprocess
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_trial_raw_d1 import (
    NorgateCapitalEventEvidence,
    NorgateTrialRawD1Result,
    build_norgate_trial_raw_d1_snapshot,
)

_SCRIPT_PATH = (
    Path(__file__).parents[1] / "scripts" / "run_norgate_fixed_etf_d1_structural_integrity.py"
)
_SESSIONS = (date(2031, 2, 3), date(2031, 2, 4))
_RAW_DATE = "2031-02-03"
_RAW_PRICE = "913.777"
_RAW_PATH = r"D:\private-source\norgate"
_CREDENTIAL = "unit-secret-must-not-persist"


def test_assessment_reattests_the_newest_snapshot_and_writes_source_safe_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    market_root, snapshot_root, snapshot, source = _snapshot_fixture(tmp_path)
    artifact_root = tmp_path / "external-artifacts"

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("structural assessment crossed a forbidden boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("structural assessment must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    _run(script, snapshot_root, artifact_root, market_root)

    output = json.loads(capsys.readouterr().out)
    receipt_path = artifact_root / f"assessment={source.dataset_hash[7:]}" / "assessment.json"
    receipt_text = receipt_path.read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert output["source_dataset_sha256"] == source.dataset_hash
    assert output["source_manifest_sha256"] == source.manifest_hash
    assert output["row_count"] == 6
    assert output["common_session_count"] == 2
    assert receipt["status"] == "integrity_attested"
    assert receipt["geometry"] == {
        "common_session_count": 2,
        "per_symbol_rows_equal_common_session_count": True,
        "row_count": 6,
        "symbol_count": 3,
    }
    assert receipt["scope"]["target_free_integrity_only"] is True
    assert receipt["scope"]["model_eligible"] is False
    assert receipt["scope"]["paper_trading_eligible"] is False
    assert receipt["scope"]["pnl_eligible"] is False
    assert receipt["receipt_constraints"] == {
        "credential_access_used": False,
        "provider_or_network_used": False,
        "raw_ohlcv_persisted": False,
        "session_dates_persisted": False,
        "source_paths_persisted": False,
        "target_or_label_computed": False,
    }
    for forbidden in (_RAW_DATE, _RAW_PRICE, _RAW_PATH, _CREDENTIAL, str(snapshot)):
        assert forbidden not in receipt_text
        assert forbidden not in json.dumps(output, sort_keys=True)


def test_existing_receipt_reattaches_only_after_the_source_snapshot_reverifies(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    market_root, snapshot_root, snapshot, source = _snapshot_fixture(tmp_path)
    artifact_root = tmp_path / "external-artifacts"
    _run(script, snapshot_root, artifact_root, market_root)
    first_output = json.loads(capsys.readouterr().out)
    receipt_path = artifact_root / f"assessment={source.dataset_hash[7:]}" / "assessment.json"
    first_bytes = receipt_path.read_bytes()

    _run(script, snapshot_root, artifact_root, market_root)
    assert json.loads(capsys.readouterr().out) == first_output
    assert receipt_path.read_bytes() == first_bytes

    data_path = snapshot / "norgate_ohlcv_1d.csv.gz"
    data_path.write_bytes(data_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        _run(script, snapshot_root, artifact_root, market_root)
    assert receipt_path.read_bytes() == first_bytes


def test_receipt_tampering_and_git_artifact_root_fail_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    market_root, snapshot_root, _snapshot, source = _snapshot_fixture(tmp_path)
    artifact_root = tmp_path / "external-artifacts"
    _run(script, snapshot_root, artifact_root, market_root)
    capsys.readouterr()
    receipt_path = artifact_root / f"assessment={source.dataset_hash[7:]}" / "assessment.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["unexpected_raw_field"] = _RAW_PRICE
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="receipt is invalid"):
        _run(script, snapshot_root, artifact_root, market_root)

    with pytest.raises(ValueError, match="outside the Git workspace"):
        _run(script, snapshot_root, script.REPOSITORY_ROOT / "artifacts", market_root)


def test_existing_receipt_under_a_link_like_parent_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    market_root, snapshot_root, _snapshot, source = _snapshot_fixture(tmp_path)
    artifact_root = tmp_path / "external-artifacts"
    _run(script, snapshot_root, artifact_root, market_root)
    capsys.readouterr()
    receipt_parent = artifact_root / f"assessment={source.dataset_hash[7:]}"
    original_is_link_like = script._is_link_like

    def link_like(path: Path) -> bool:
        return path == receipt_parent or original_is_link_like(path)

    monkeypatch.setattr(script, "_is_link_like", link_like)
    with pytest.raises(ValueError, match="receipt is unavailable"):
        _run(script, snapshot_root, artifact_root, market_root)


def test_newest_snapshot_selection_uses_only_immediate_matching_directories(tmp_path: Path) -> None:
    script = _load_script()
    root = tmp_path / "snapshots"
    first = root / "snapshot=first-norgate-trial-raw-d1-r2"
    second = root / "snapshot=second-norgate-trial-raw-d1-r2"
    ignored = root / "other"
    for path in (first, second, ignored):
        path.mkdir(parents=True)
    first.touch()
    second.touch()

    assert script._newest_snapshot(root) == second.resolve()


def test_script_excludes_provider_credentials_network_broker_and_model_surfaces() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert imported_modules.isdisjoint(
        {"norgatedata", "socket", "subprocess", "requests", "httpx", "dotenv", "torch"}
    )
    assert "environ" not in attributes
    assert "NorgateRawDailyBarProvider" not in source
    for forbidden in (".env", "kis", "broker", "fit("):
        assert forbidden not in source.casefold()


def _run(script: ModuleType, snapshot_root: Path, artifact_root: Path, market_root: Path) -> None:
    assert script.main(
        [
            "--snapshot-root",
            str(snapshot_root),
            "--artifact-root",
            str(artifact_root),
            "--market-data-root",
            str(market_root),
        ]
    ) == 0


def _snapshot_fixture(tmp_path: Path) -> tuple[Path, Path, Path, NorgateTrialRawD1Result]:
    market_root = tmp_path / "market_data"
    market_root.mkdir()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot_root = market_root / "us_equities" / "norgate_trial" / "local_d1_etf"
    snapshot = snapshot_root / "snapshot=fixture-norgate-trial-raw-d1-r2"
    result = build_norgate_trial_raw_d1_snapshot(
        destination=snapshot,
        requested_start=_SESSIONS[0],
        requested_end=_SESSIONS[-1],
        retrieved_at_utc=datetime(2031, 2, 5, tzinfo=UTC),
        norgate_bars=lambda symbol, _start, _end: _bars(symbol),
        capital_event_evidence=lambda symbol, _start, _end: _events(symbol),
        norgate_package_version="fixture",
        market_data_root=market_root,
        repo_root=repo_root,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    return market_root, snapshot_root, snapshot, result


def _bars(symbol: str) -> list[Bar]:
    return [
        Bar(
            symbol=symbol,
            market="US",
            timeframe=Timeframe.D1,
            start_ts=datetime.combine(session, datetime.min.time(), UTC),
            open=Decimal(_RAW_PRICE),
            high=Decimal(_RAW_PRICE) + Decimal("1"),
            low=Decimal(_RAW_PRICE) - Decimal("1"),
            close=Decimal(_RAW_PRICE) + Decimal("0.25"),
            volume=Decimal("1000"),
        )
        for session in _SESSIONS
    ]


def _events(_symbol: str) -> NorgateCapitalEventEvidence:
    return NorgateCapitalEventEvidence(
        returned_row_count=2,
        returned_start=_SESSIONS[0],
        returned_end=_SESSIONS[-1],
        clipped_session_count=2,
        marker_dates=(),
    )


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "norgate_structural_integrity_script",
        _SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
