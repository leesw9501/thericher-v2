from __future__ import annotations

import builtins
import importlib
import json
import socket
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_raw_alignment import (
    NorgateRawAlignmentError,
    TiingoRawD1Reference,
    build_norgate_raw_d1_alignment_snapshot,
    verify_norgate_raw_d1_alignment_snapshot,
)

_START = date(2024, 1, 2)
_END = date(2024, 1, 3)
_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64


def test_module_does_not_import_optional_norgate_package(monkeypatch) -> None:
    module_name = "thericher_v2.data.norgate_raw_alignment"
    original_import = builtins.__import__

    def guard_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "norgatedata":
            raise AssertionError("alignment module must not import the optional Norgate package")
        return original_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, module_name, raising=False)
    monkeypatch.delitem(sys.modules, "norgatedata", raising=False)
    monkeypatch.setattr(builtins, "__import__", guard_import)

    imported = importlib.import_module(module_name)

    assert "norgatedata" not in imported.__dict__


def test_builds_external_alignment_with_fixed_sources_only(tmp_path: Path, monkeypatch) -> None:
    root, reference = _root_and_reference(tmp_path)
    destination = _destination(root)
    calls: list[tuple[str, str, date, date]] = []

    def source(name: str, mismatch: bool = False):
        def load(symbol: str, start: date, end: date) -> Sequence[Bar]:
            calls.append((name, symbol, start, end))
            return _bars(symbol, mismatch=mismatch and symbol == "QQQ")

        return load

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("alignment must not cross this boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("alignment must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = _build(
        destination,
        root,
        reference,
        norgate_bars=source("norgate"),
        tiingo_bars=source("tiingo"),
    )

    assert result.snapshot_dir == destination
    assert result.row_count == 6
    assert result.comparison_status == "literal_raw_ohlcv_match"
    assert result.requested_start == _START
    assert result.requested_end == _END
    assert calls == [
        ("norgate", "SPY", _START, _END),
        ("tiingo", "SPY", _START, _END),
        ("norgate", "QQQ", _START, _END),
        ("tiingo", "QQQ", _START, _END),
        ("norgate", "IWM", _START, _END),
        ("tiingo", "IWM", _START, _END),
    ]
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["storage"]["root"] == str(root)
    assert manifest["comparison"]["status"] == "literal_raw_ohlcv_match"
    assert manifest["scope"] == {
        "data_alignment_only": True,
        "source_preference_eligible": False,
        "point_in_time_eligible": False,
        "campaign_eligible": False,
        "model_eligible": False,
        "paper_trading_eligible": False,
    }
    marker = (destination / "DELETE_NORGATE_DATA_ON_EXPIRY.txt").read_text(encoding="ascii")
    assert "Do not use this snapshot to choose a source" in marker
    assert verify_norgate_raw_d1_alignment_snapshot(
        destination, market_data_root=root, repo_root=tmp_path / "repo"
    ) == result
    assert list(tmp_path.rglob(".env*")) == []


def test_records_raw_difference_without_claiming_a_source_winner(tmp_path: Path) -> None:
    root, reference = _root_and_reference(tmp_path)
    result = _build(
        _destination(root),
        root,
        reference,
        norgate_bars=lambda symbol, _start, _end: _bars(symbol, mismatch=symbol == "QQQ"),
        tiingo_bars=lambda symbol, _start, _end: _bars(symbol),
    )

    manifest = json.loads((result.snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result.comparison_status == "literal_raw_ohlcv_difference"
    assert manifest["comparison"]["source_preference"] == "not evaluated"
    assert manifest["comparison"]["symbols"]["QQQ"]["all_ohlcv_equal_session_count"] == 1


@pytest.mark.parametrize(
    "norgate_bars",
    [
        lambda symbol, _start, _end: _bars(symbol, duplicate=True),
        lambda symbol, _start, _end: [],
    ],
)
def test_source_contract_failure_leaves_no_published_snapshot(
    tmp_path: Path,
    norgate_bars: Callable[[str, date, date], Sequence[Bar]],
) -> None:
    root, reference = _root_and_reference(tmp_path)
    destination = _destination(root)

    with pytest.raises(ValueError, match="ordered|no bars"):
        _build(
            destination,
            root,
            reference,
            norgate_bars=norgate_bars,
            tiingo_bars=lambda symbol, _start, _end: _bars(symbol),
        )

    assert not destination.exists()
    assert not list(destination.parent.glob(".stage-*"))


def test_non_windows_low_disk_and_existing_destination_fail_closed(tmp_path: Path) -> None:
    root, reference = _root_and_reference(tmp_path)
    destination = _destination(root)

    def loader(symbol: str, _start: date, _end: date) -> Sequence[Bar]:
        return _bars(symbol)

    with pytest.raises(NorgateRawAlignmentError, match="requires Windows"):
        _build(
            destination,
            root,
            reference,
            norgate_bars=loader,
            tiingo_bars=loader,
            platform_name="linux",
        )
    with pytest.raises(ValueError, match="hard free-space"):
        _build(
            destination,
            root,
            reference,
            norgate_bars=loader,
            tiingo_bars=loader,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )
    assert not destination.exists()

    _build(destination, root, reference, norgate_bars=loader, tiingo_bars=loader)
    with pytest.raises(FileExistsError, match="already exists"):
        _build(destination, root, reference, norgate_bars=loader, tiingo_bars=loader)


def test_tampered_external_data_fails_verification(tmp_path: Path) -> None:
    root, reference = _root_and_reference(tmp_path)
    result = _build(
        _destination(root),
        root,
        reference,
        norgate_bars=lambda symbol, _start, _end: _bars(symbol),
        tiingo_bars=lambda symbol, _start, _end: _bars(symbol),
    )
    data_path = result.snapshot_dir / "norgate_ohlcv_1d.csv.gz"
    data_path.write_bytes(data_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="hash mismatch"):
        verify_norgate_raw_d1_alignment_snapshot(
            result.snapshot_dir, market_data_root=root, repo_root=tmp_path / "repo"
        )


def _build(
    destination: Path,
    root: Path,
    reference: TiingoRawD1Reference,
    *,
    norgate_bars: Callable[[str, date, date], Sequence[Bar]],
    tiingo_bars: Callable[[str, date, date], Sequence[Bar]],
    platform_name: str = "win32",
    disk_usage: Callable[[str | Path], object] | None = None,
):
    return build_norgate_raw_d1_alignment_snapshot(
        destination=destination,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        tiingo_reference=reference,
        norgate_bars=norgate_bars,
        tiingo_bars=tiingo_bars,
        norgate_package_version="test-version",
        market_data_root=root,
        repo_root=root.parent / "repo",
        platform_name=platform_name,
        disk_usage=disk_usage or (lambda _path: SimpleNamespace(total=100, free=50)),
    )


def _root_and_reference(tmp_path: Path) -> tuple[Path, TiingoRawD1Reference]:
    root = tmp_path / "market_data"
    root.mkdir()
    snapshot = root / "tiingo" / "snapshot=fixture-tiingo-raw-d1"
    snapshot.mkdir(parents=True)
    return root, TiingoRawD1Reference(
        snapshot_dir=snapshot,
        dataset_id="unit.tiingo.raw-d1",
        dataset_hash=_HASH_A,
        manifest_hash=_HASH_B,
    )


def _destination(root: Path) -> Path:
    return root / "snapshot=2026-07-19-norgate-raw-d1-alignment-r1"


def _bars(symbol: str, *, mismatch: bool = False, duplicate: bool = False) -> list[Bar]:
    rows = [_bar(symbol, _START, "10"), _bar(symbol, _END, "11" if mismatch else "10")]
    return [rows[0], rows[0], rows[1]] if duplicate else rows


def _bar(symbol: str, session: date, close: str) -> Bar:
    value = Decimal(close)
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime.combine(session, datetime.min.time(), UTC),
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("100"),
    )
