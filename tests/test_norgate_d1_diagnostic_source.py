from __future__ import annotations

import ast
import csv
import gzip
import hashlib
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import norgate_d1_diagnostic_source as diagnostic_source
from thericher_v2.data.norgate_trial_raw_d1 import (
    FIXED_NORGATE_TRIAL_SYMBOLS,
    NorgateCapitalEventEvidence,
    NorgateTrialRawD1Result,
    build_norgate_trial_raw_d1_snapshot,
)

_START = date(2024, 1, 2)
_END = date(2024, 1, 3)
_DATA_FILE = "norgate_ohlcv_1d.csv.gz"
_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume")


def test_loads_one_reattested_synthetic_d1_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, snapshot, result = _snapshot_fixture(tmp_path)
    calls: list[str] = []
    original_verify = diagnostic_source.verify_norgate_trial_raw_d1_snapshot

    def verify(*args: object, **kwargs: object) -> NorgateTrialRawD1Result:
        calls.append("verify")
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(diagnostic_source, "verify_norgate_trial_raw_d1_snapshot", verify)

    panel = diagnostic_source.load_verified_norgate_d1_diagnostic_panel(
        snapshot,
        expected_dataset_hash=result.dataset_hash,
        expected_manifest_hash=result.manifest_hash,
        market_data_root=root,
    )

    assert calls == ["verify"]
    assert panel.source_result == result
    assert panel.common_sessions == (_START, _END)
    assert tuple(panel.bars_by_symbol) == FIXED_NORGATE_TRIAL_SYMBOLS
    assert all(len(bars) == 2 for bars in panel.bars_by_symbol.values())
    assert all(
        bar.timeframe is Timeframe.D1
        and bar.complete
        and bar.start_ts.tzinfo is UTC
        and bar.start_ts.time() == datetime.min.time()
        for bars in panel.bars_by_symbol.values()
        for bar in bars
    )
    with pytest.raises(TypeError):
        panel.bars_by_symbol["SPY"] = ()  # type: ignore[index]


@pytest.mark.parametrize(
    ("expected_dataset_hash", "expected_manifest_hash", "match"),
    [
        ("sha256:" + "0" * 64, None, "dataset hash mismatch"),
        (None, "sha256:" + "1" * 64, "manifest hash mismatch"),
    ],
)
def test_rejects_mismatched_attested_hashes(
    tmp_path: Path,
    expected_dataset_hash: str | None,
    expected_manifest_hash: str | None,
    match: str,
) -> None:
    root, snapshot, result = _snapshot_fixture(tmp_path)

    with pytest.raises(ValueError, match=match):
        diagnostic_source.load_verified_norgate_d1_diagnostic_panel(
            snapshot,
            expected_dataset_hash=expected_dataset_hash or result.dataset_hash,
            expected_manifest_hash=expected_manifest_hash or result.manifest_hash,
            market_data_root=root,
        )


def test_rejects_a_snapshot_under_the_repository_root(tmp_path: Path) -> None:
    root, snapshot, result = _snapshot_fixture(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repository_data_root = repo_root / "market_data"
    relocated_snapshot = (
        repository_data_root / "diagnostic" / "snapshot=2026-08-02-norgate-trial-raw-d1-r2"
    )
    relocated_snapshot.parent.mkdir(parents=True)
    snapshot.rename(relocated_snapshot)

    with pytest.raises(ValueError, match="must stay outside Git"):
        diagnostic_source.load_verified_norgate_d1_diagnostic_panel(
            relocated_snapshot,
            expected_dataset_hash=result.dataset_hash,
            expected_manifest_hash=result.manifest_hash,
            market_data_root=repository_data_root,
            repo_root=repo_root,
        )


def test_rejects_misaligned_or_incomplete_rows_after_reattest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, snapshot, result = _snapshot_fixture(tmp_path)
    _rewrite_rows(
        snapshot,
        [
            *_rows_for("SPY"),
            {**_rows_for("QQQ")[0], "date": _START.isoformat()},
            *_rows_for("IWM"),
        ],
    )
    mutated_result = replace(result, dataset_hash=_data_hash(snapshot))
    monkeypatch.setattr(
        diagnostic_source,
        "verify_norgate_trial_raw_d1_snapshot",
        lambda *_args, **_kwargs: mutated_result,
    )

    with pytest.raises(ValueError, match="sessions are not aligned"):
        diagnostic_source.load_verified_norgate_d1_diagnostic_panel(
            snapshot,
            expected_dataset_hash=mutated_result.dataset_hash,
            expected_manifest_hash=mutated_result.manifest_hash,
            market_data_root=root,
        )

    _rewrite_rows(snapshot, [*_rows_for("SPY"), *_rows_for("QQQ")])
    incomplete_result = replace(result, dataset_hash=_data_hash(snapshot))
    monkeypatch.setattr(
        diagnostic_source,
        "verify_norgate_trial_raw_d1_snapshot",
        lambda *_args, **_kwargs: incomplete_result,
    )

    with pytest.raises(ValueError, match="symbols are incomplete"):
        diagnostic_source.load_verified_norgate_d1_diagnostic_panel(
            snapshot,
            expected_dataset_hash=incomplete_result.dataset_hash,
            expected_manifest_hash=incomplete_result.manifest_hash,
            market_data_root=root,
        )


def test_module_statically_excludes_provider_network_environment_and_persistence() -> None:
    source_path = Path(diagnostic_source.__file__)
    source = source_path.read_text(encoding="utf-8")
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
    call_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attribute_names = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert imported_modules.isdisjoint(
        {"norgatedata", "os", "socket", "subprocess", "requests", "httpx", "dotenv"}
    )
    assert "environ" not in attribute_names
    assert "print" not in call_names
    assert ".write_" not in source


def _snapshot_fixture(tmp_path: Path) -> tuple[Path, Path, NorgateTrialRawD1Result]:
    root = tmp_path / "market_data"
    root.mkdir()
    snapshot = root / "diagnostic" / "snapshot=2026-08-02-norgate-trial-raw-d1-r2"
    result = build_norgate_trial_raw_d1_snapshot(
        destination=snapshot,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 8, 2, tzinfo=UTC),
        norgate_bars=lambda symbol, _start, _end: _bars(symbol),
        capital_event_evidence=lambda symbol, _start, _end: _events(symbol),
        norgate_package_version="test-version",
        market_data_root=root,
        repo_root=tmp_path / "repo",
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    return root, snapshot, result


def _bars(symbol: str) -> Sequence[Bar]:
    return [
        Bar(
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
        for session in (_START, _END)
    ]


def _events(symbol: str) -> NorgateCapitalEventEvidence:
    return NorgateCapitalEventEvidence(
        returned_row_count=2,
        returned_start=_START,
        returned_end=_END,
        clipped_session_count=2,
        marker_dates=(),
    )


def _rows_for(symbol: str) -> list[dict[str, str]]:
    return [
        {
            "symbol": symbol,
            "date": session.isoformat(),
            "open": "10",
            "high": "11",
            "low": "9",
            "close": "10",
            "volume": "100",
        }
        for session in (_START, _END)
    ]


def _rewrite_rows(snapshot: Path, rows: list[dict[str, str]]) -> None:
    with gzip.open(snapshot / _DATA_FILE, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _data_hash(snapshot: Path) -> str:
    return "sha256:" + hashlib.sha256((snapshot / _DATA_FILE).read_bytes()).hexdigest()
