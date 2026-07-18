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
from thericher_v2.data.norgate_trial_raw_d1 import (
    NorgateCapitalEventEvidence,
    NorgateDividendMarkerEvidence,
    build_norgate_trial_dividend_exclusion_snapshot,
    build_norgate_trial_raw_d1_snapshot,
    default_norgate_trial_dividend_exclusion_snapshot_dir,
    load_norgate_dividend_marker_evidence,
    verify_norgate_trial_dividend_exclusion_snapshot,
)

_START = date(2024, 1, 2)
_END = date(2024, 1, 3)
_SYMBOLS = ("SPY", "QQQ", "IWM")


class _Dtype:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.dtype = _Dtype(("Date", "Dividend"))
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeClient:
    class StockPriceAdjustmentType:
        NONE = "none"

    class PaddingType:
        NONE = "none"

    def __init__(self, rows: _Rows) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def price_timeseries(self, symbol: str, **kwargs: Any) -> _Rows:
        self.calls.append((symbol, kwargs))
        return self.rows


def test_loads_ordered_dividend_markers_without_retaining_values() -> None:
    client = _FakeClient(
        _Rows(
            [
                {"Date": "2024-01-02", "Dividend": 0},
                {"Date": "2024-01-03", "Dividend": 1},
            ]
        )
    )

    evidence = load_norgate_dividend_marker_evidence(
        "spy",
        _START,
        _END,
        client_loader=lambda: client,
    )

    assert evidence == NorgateDividendMarkerEvidence(
        returned_row_count=2,
        session_dates=(_START, _END),
        marker_dates=(_END,),
    )
    assert client.calls == [
        (
            "SPY",
            {
                "stock_price_adjustment_setting": "none",
                "padding_setting": "none",
                "start_date": "2024-01-02",
                "end_date": "2024-01-03",
                "timeseriesformat": "numpy-recarray",
                "interval": "D",
            },
        )
    ]


def test_builds_external_exclusion_sidecar_without_network_or_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repo, parent, destination = _paths(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dividend exclusion build crossed a forbidden boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("dividend exclusion build must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    result = _build(destination, root, repo, parent)

    assert result.snapshot_dir == destination
    assert result.parent_snapshot_dir == parent
    assert result.parent_dataset_hash.startswith("sha256:")
    assert result.marker_count == 3
    assert result.excluded_session_count == 6
    assert result.common_session_count == 2
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    exclusions = (destination / "dividend_marker_exclusions.csv").read_text(encoding="utf-8")
    assert manifest["norgate_source_contract"]["marker_semantics_verified"] is False
    assert manifest["source_marker_evidence"]["all_symbols_have_nonzero_marker"] is True
    assert manifest["scope"]["development_training_eligible"] is False
    assert manifest["scope"]["gpu_eligible"] is False
    assert exclusions.splitlines() == [
        "symbol,source_marker_date,excluded_session_date",
        "SPY,2024-01-03,2024-01-02",
        "SPY,2024-01-03,2024-01-03",
        "QQQ,2024-01-03,2024-01-02",
        "QQQ,2024-01-03,2024-01-03",
        "IWM,2024-01-03,2024-01-02",
        "IWM,2024-01-03,2024-01-03",
    ]
    assert verify_norgate_trial_dividend_exclusion_snapshot(
        destination,
        market_data_root=root,
        repo_root=repo,
    ) == result


def test_sidecar_tampering_or_missing_nonzero_marker_fails_closed(tmp_path: Path) -> None:
    root, repo, parent, destination = _paths(tmp_path)
    result = _build(destination, root, repo, parent)
    path = result.snapshot_dir / "dividend_marker_exclusions.csv"
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="hash mismatch"):
        verify_norgate_trial_dividend_exclusion_snapshot(
            result.snapshot_dir,
            market_data_root=root,
            repo_root=repo,
        )

    rejected_root, rejected_repo, rejected_parent, rejected = _paths(tmp_path / "rejected")
    with pytest.raises(ValueError, match="require nonzero"):
        _build(
            rejected,
            rejected_root,
            rejected_repo,
            rejected_parent,
            evidence=lambda symbol, _start, _end: _evidence(symbol, marker=symbol != "IWM"),
        )
    assert not rejected.exists()


def test_rejects_uneven_parent_session_response_and_unsafe_destination(tmp_path: Path) -> None:
    root, repo, parent, destination = _paths(tmp_path)

    with pytest.raises(ValueError, match="do not match"):
        _build(
            destination,
            root,
            repo,
            parent,
            evidence=lambda symbol, _start, _end: NorgateDividendMarkerEvidence(
                returned_row_count=1,
                session_dates=(_END,),
                marker_dates=(_END,),
            ),
        )
    assert not destination.exists()

    with pytest.raises(ValueError, match="under market data"):
        _build(repo / destination.name, root, repo, parent)


def test_default_destination_is_external() -> None:
    assert default_norgate_trial_dividend_exclusion_snapshot_dir(date(2026, 7, 19)) == Path(
        "D:/market_data/us_equities/fixed_etf_daily/canonical/norgate_trial_raw_d1/"
        "dividend_marker_exclusions/"
        "snapshot=2026-07-19-norgate-trial-raw-d1-r3-dividend-exclusions-r1"
    )


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "market_data"
    root.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    parent = root / "fixed" / "snapshot=2026-07-19-norgate-trial-raw-d1-r2"
    build_norgate_trial_raw_d1_snapshot(
        destination=parent,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        norgate_bars=lambda symbol, _start, _end: _bars(symbol),
        capital_event_evidence=lambda symbol, _start, _end: _capital_events(symbol),
        norgate_package_version="test-version",
        market_data_root=root,
        repo_root=repo,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )
    destination = root / "fixed" / "dividend" / (
        "snapshot=2026-07-19-norgate-trial-raw-d1-r3-dividend-exclusions-r1"
    )
    return root, repo, parent, destination


def _build(
    destination: Path,
    root: Path,
    repo: Path,
    parent: Path,
    *,
    evidence: Callable[[str, date, date], NorgateDividendMarkerEvidence] = (
        lambda symbol, _start, _end: _evidence(symbol)
    ),
):
    return build_norgate_trial_dividend_exclusion_snapshot(
        destination=destination,
        parent_snapshot=parent,
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        dividend_evidence=evidence,
        norgate_package_version="test-version",
        market_data_root=root,
        repo_root=repo,
        platform_name="win32",
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )


def _bars(symbol: str) -> Sequence[Bar]:
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


def _capital_events(_symbol: str) -> NorgateCapitalEventEvidence:
    return NorgateCapitalEventEvidence(
        returned_row_count=2,
        returned_start=_START,
        returned_end=_END,
        clipped_session_count=2,
        marker_dates=(),
    )


def _evidence(_symbol: str, *, marker: bool = True) -> NorgateDividendMarkerEvidence:
    return NorgateDividendMarkerEvidence(
        returned_row_count=2,
        session_dates=(_START, _END),
        marker_dates=(_END,) if marker else (),
    )
