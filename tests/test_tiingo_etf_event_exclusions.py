from __future__ import annotations

import gzip
import hashlib
import json
import socket
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import thericher_v2.data.tiingo_etf_daily as tiingo_etf_daily
from thericher_v2.data.tiingo_eod import TIINGO_EOD_ENDPOINT
from thericher_v2.data.tiingo_etf_daily import TIINGO_ETF_D1_SYMBOLS
from thericher_v2.data.tiingo_etf_event_exclusions import (
    TIINGO_ETF_D1_EVENT_EXCLUSION_VERSION,
    TiingoEtfEventExclusionError,
    build_tiingo_etf_d1_event_exclusion_snapshot,
    default_tiingo_etf_d1_event_exclusion_snapshot_dir,
    verify_tiingo_etf_d1_event_exclusion_snapshot,
)

_RETRIEVED_AT = datetime(2026, 8, 4, 9, 10, 11, tzinfo=UTC)
_SESSIONS = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5))


def test_builds_external_deterministic_sidecar_without_network_or_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repo, parent, destination = _paths(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("event-exclusion sidecar crossed a forbidden boundary")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("event-exclusion sidecar must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    monkeypatch.setattr(tiingo_etf_daily, "read_tiingo_api_token", fail)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = _build(destination, root, repo, parent)

    assert result.snapshot_dir == destination
    assert result.parent_snapshot_dir == parent
    assert result.marker_count == 4
    assert result.excluded_session_count == 10
    assert result.session_counts == {symbol: 4 for symbol in TIINGO_ETF_D1_SYMBOLS}
    assert not tuple(repo.iterdir())
    manifest_text = (destination / "manifest.json").read_text(encoding="utf-8")
    exclusions = (destination / "event_marker_exclusions.csv").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["scope"] == {
        "retrospective_research_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "paper_input_eligible": False,
        "sealed_holdout_eligible": False,
        "event_semantics_verified": False,
    }
    assert manifest["source_marker_evidence"]["event_semantics_verified"] is False
    assert manifest["parent_snapshot"]["canonical_raw_normalized_equivalence_reattested"] is True
    assert "101.11" not in manifest_text
    assert "101.11" not in exclusions
    assert "3.14159" not in manifest_text
    assert "3.14159" not in exclusions
    assert exclusions.splitlines() == [
        "symbol,source_marker_date,excluded_session_date,reason",
        "SPY,2024-01-03,2024-01-02,source_marker_or_adjacent_observed_session",
        "SPY,2024-01-03,2024-01-03,source_marker_or_adjacent_observed_session",
        "SPY,2024-01-03,2024-01-04,source_marker_or_adjacent_observed_session",
        "SPY,2024-01-04,2024-01-03,source_marker_or_adjacent_observed_session",
        "SPY,2024-01-04,2024-01-04,source_marker_or_adjacent_observed_session",
        "SPY,2024-01-04,2024-01-05,source_marker_or_adjacent_observed_session",
        "QQQ,2024-01-02,2024-01-02,source_marker_or_adjacent_observed_session",
        "QQQ,2024-01-02,2024-01-03,source_marker_or_adjacent_observed_session",
        "IWM,2024-01-05,2024-01-04,source_marker_or_adjacent_observed_session",
        "IWM,2024-01-05,2024-01-05,source_marker_or_adjacent_observed_session",
    ]
    assert verify_tiingo_etf_d1_event_exclusion_snapshot(
        destination,
        market_data_root=root,
        repo_root=repo,
    ) == result


def test_verifier_rejects_sidecar_and_parent_mutations(tmp_path: Path) -> None:
    root, repo, parent, destination = _paths(tmp_path)
    result = _build(destination, root, repo, parent)
    exclusions = result.snapshot_dir / "event_marker_exclusions.csv"
    exclusions.write_bytes(exclusions.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="hash mismatch"):
        verify_tiingo_etf_d1_event_exclusion_snapshot(
            result.snapshot_dir,
            market_data_root=root,
            repo_root=repo,
        )

    other_root, other_repo, other_parent, other_destination = _paths(tmp_path / "parent-mutation")
    other_result = _build(other_destination, other_root, other_repo, other_parent)
    raw = other_parent / "raw" / "SPY.json"
    raw.write_bytes(raw.read_bytes() + b" ")

    with pytest.raises(ValueError, match="raw hash mismatch"):
        verify_tiingo_etf_d1_event_exclusion_snapshot(
            other_result.snapshot_dir,
            market_data_root=other_root,
            repo_root=other_repo,
        )


def test_failed_write_leaves_no_destination_or_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repo, parent, destination = _paths(tmp_path)
    original_write_bytes = Path.write_bytes

    def fail_exclusion_write(path: Path, data: bytes) -> int:
        if path.name == "event_marker_exclusions.csv":
            raise OSError("simulated write failure")
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_exclusion_write)
    with pytest.raises(OSError, match="simulated write failure"):
        _build(destination, root, repo, parent)

    assert not destination.exists()
    assert not list(destination.parent.glob(".stage-*"))


def test_rejects_repo_destination_and_storage_floor(tmp_path: Path) -> None:
    root, repo, parent, destination = _paths(tmp_path)

    with pytest.raises(ValueError, match="must remain under market_data"):
        _build(repo / destination.name, root, repo, parent)
    assert not (repo / destination.name).exists()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        build_tiingo_etf_d1_event_exclusion_snapshot(
            destination=destination,
            parent_snapshot=parent,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=root,
            repo_root=tmp_path,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
        )

    with pytest.raises(TiingoEtfEventExclusionError, match="storage floor"):
        build_tiingo_etf_d1_event_exclusion_snapshot(
            destination=destination,
            parent_snapshot=parent,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=root,
            repo_root=repo,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )
    assert not destination.exists()


def test_default_destination_is_external() -> None:
    assert default_tiingo_etf_d1_event_exclusion_snapshot_dir(_RETRIEVED_AT) == Path(
        "D:/market_data/us_equities/tiingo_etf_daily/event_marker_exclusions/"
        f"snapshot=20260804T091011Z-{TIINGO_ETF_D1_EVENT_EXCLUSION_VERSION}"
    )


def _build(destination: Path, root: Path, repo: Path, parent: Path):
    return build_tiingo_etf_d1_event_exclusion_snapshot(
        destination=destination,
        parent_snapshot=parent,
        retrieved_at_utc=_RETRIEVED_AT,
        market_data_root=root,
        repo_root=repo,
        disk_usage=lambda _path: SimpleNamespace(total=100, free=50),
    )


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "m"
    root.mkdir(parents=True)
    repo = tmp_path / "r"
    repo.mkdir()
    parent = root / "p" / "snapshot=fixture-tiingo-etf-d1-r1"
    _write_fixture_snapshot(parent)
    destination = root / "e" / f"snapshot=f-{TIINGO_ETF_D1_EVENT_EXCLUSION_VERSION}"
    return root, repo, parent, destination


def _write_fixture_snapshot(destination: Path) -> None:
    destination.mkdir(parents=True)
    raw_dir = destination / "raw"
    raw_dir.mkdir()
    raw_by_symbol = {symbol: _raw_payload(symbol) for symbol in TIINGO_ETF_D1_SYMBOLS}
    for symbol, payload in raw_by_symbol.items():
        (raw_dir / f"{symbol}.json").write_bytes(payload)
    canonical = _canonical_bytes()
    (destination / "ohlcv_1d.csv.gz").write_bytes(canonical)
    raw_hashes = {symbol: _sha256(payload) for symbol, payload in raw_by_symbol.items()}
    manifest = {
        "schema_version": 1,
        "kind": "tiingo_etf_raw_d1_snapshot",
        "version": "tiingo-etf-d1-r1",
        "immutable_snapshot": True,
        "dataset_id": f"us_equities.tiingo_etf_daily.{destination.name}",
        "dataset_hash": _sha256(canonical),
        "symbols": list(TIINGO_ETF_D1_SYMBOLS),
        "requested_window": {"start": "2024-01-02", "end": "2024-01-05"},
        "retrieved_at_utc": "2026-08-04T09:10:11Z",
        "source_contract": {
            "provider": "Tiingo standard EOD API",
            "endpoint_template": TIINGO_EOD_ENDPOINT,
            "raw_fields": [
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "divCash",
                "splitFactor",
            ],
            "adjusted_fields_used": False,
        },
        "scope": {
            "retrospective_research_only": True,
            "point_in_time_eligible": False,
            "ranking_eligible": False,
            "paper_input_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "per_symbol": {
            symbol: {
                "session_count": 4,
                "first_session": "2024-01-02",
                "last_session": "2024-01-05",
                "event_session_count": {"SPY": 2, "QQQ": 1, "IWM": 1}[symbol],
            }
            for symbol in TIINGO_ETF_D1_SYMBOLS
        },
        "files": {
            "canonical": {
                "path": "ohlcv_1d.csv.gz",
                "format": "csv.gz",
                "columns": [
                    "symbol",
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "div_cash",
                    "split_factor",
                ],
                "sha256": _sha256(canonical),
                "size_bytes": len(canonical),
            },
            "raw_sources": [
                {
                    "symbol": symbol,
                    "filename": f"{symbol}.json",
                    "sha256": raw_hashes[symbol],
                    "size_bytes": len(raw_by_symbol[symbol]),
                }
                for symbol in TIINGO_ETF_D1_SYMBOLS
            ],
        },
        "storage": {"free_percent_before_write": 50.0},
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _raw_payload(symbol: str) -> bytes:
    offset = {"SPY": 0, "QQQ": 20, "IWM": 40}[symbol]
    rows = []
    for index, session in enumerate(_SESSIONS):
        price = 101 + offset + index
        div_cash, split_factor = _event_values(symbol, index)
        rows.append(
            {
                "date": f"{session.isoformat()}T00:00:00.000Z",
                "open": f"{price}.11",
                "high": f"{price + 1}.11",
                "low": f"{price - 1}.11",
                "close": f"{price}.61",
                "volume": str(1000 + index),
                "divCash": div_cash,
                "splitFactor": split_factor,
            }
        )
    return json.dumps(rows, separators=(",", ":")).encode("utf-8")


def _canonical_bytes() -> bytes:
    lines = ["symbol,date,open,high,low,close,volume,div_cash,split_factor"]
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        offset = {"SPY": 0, "QQQ": 20, "IWM": 40}[symbol]
        for index, session in enumerate(_SESSIONS):
            price = 101 + offset + index
            div_cash, split_factor = _event_values(symbol, index)
            lines.append(
                ",".join(
                    (
                        symbol,
                        session.isoformat(),
                        f"{price}.11",
                        f"{price + 1}.11",
                        f"{price - 1}.11",
                        f"{price}.61",
                        str(1000 + index),
                        div_cash,
                        split_factor,
                    )
                )
            )
    return gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), mtime=0)


def _event_values(symbol: str, index: int) -> tuple[str, str]:
    if symbol == "SPY" and index == 1:
        return "3.14159", "1"
    if symbol == "SPY" and index == 2:
        return "0", "2"
    if symbol == "QQQ" and index == 0:
        return "0", "2"
    if symbol == "IWM" and index == 3:
        return "1.25", "1"
    return "0", "1"


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
