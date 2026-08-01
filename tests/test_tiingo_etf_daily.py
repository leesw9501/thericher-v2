from __future__ import annotations

import json
import socket
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

import thericher_v2.data.tiingo_etf_daily as tiingo_etf_daily
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    TiingoEtfDailyError,
    acquire_tiingo_etf_d1_snapshot,
    load_verified_tiingo_etf_d1_snapshot,
    normalize_tiingo_etf_d1_response,
    write_tiingo_etf_d1_receipt,
)

_RETRIEVED_AT = datetime(2026, 8, 1, 1, 2, 3, tzinfo=UTC)
_START = date(2024, 1, 2)
_END = date(2024, 1, 5)


def test_acquisition_is_external_source_safe_and_replayable(tmp_path: Path) -> None:
    market_root = tmp_path / "market-data"
    market_root.mkdir()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    env_path = tmp_path / ".env"
    env_path.write_text("KIS_PAPER_APP_KEY=must-not-be-read\nTIINGO_API_TOKEN=unit-token\n")
    destination = _destination(market_root)
    seen: list[tuple[str, str | None]] = []

    def opener(request, *, timeout: float):
        assert timeout == 30.0
        seen.append((request.full_url, request.get_header("Authorization")))
        symbol = urlparse(request.full_url).path.split("/")[-2]
        return _Response(_payload(symbol))

    snapshot = acquire_tiingo_etf_d1_snapshot(
        env_path=env_path,
        destination=destination,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=_RETRIEVED_AT,
        market_data_root=market_root,
        repo_root=repo_root,
        opener=opener,
    )

    assert tuple(snapshot.raw_hashes) == TIINGO_ETF_D1_SYMBOLS
    assert snapshot.session_counts == {symbol: 4 for symbol in TIINGO_ETF_D1_SYMBOLS}
    assert snapshot.event_session_counts == {symbol: 1 for symbol in TIINGO_ETF_D1_SYMBOLS}
    assert len(seen) == 3
    assert all(header == "Token unit-token" for _, header in seen)
    assert all("unit-token" not in url for url, _ in seen)
    assert all(url.startswith("https://api.tiingo.com/tiingo/daily/") for url, _ in seen)
    assert not tuple(repo_root.iterdir())

    manifest_text = (destination / "manifest.json").read_text(encoding="utf-8")
    assert "unit-token" not in manifest_text
    assert "must-not-be-read" not in manifest_text
    assert "adjClose" not in manifest_text
    assert "100.00" not in manifest_text
    assert (destination / "raw" / "SPY.json").is_file()
    assert (destination / "ohlcv_1d.csv.gz").is_file()

    loaded = load_verified_tiingo_etf_d1_snapshot(
        destination,
        dataset_id=snapshot.dataset_id,
        expected_dataset_hash=snapshot.dataset_hash,
        expected_manifest_hash=snapshot.manifest_hash,
        market_data_root=market_root,
        repo_root=repo_root,
    )

    assert len(loaded.bars_for("QQQ")) == 4
    assert "100.00" not in repr(loaded)


def test_loader_reattests_bytes_without_network_or_credential_access(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _snapshot_fixture(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("verified snapshot loading must stay offline")

    monkeypatch.setattr(tiingo_etf_daily, "read_tiingo_api_token", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    loaded = load_verified_tiingo_etf_d1_snapshot(
        fixture[0],
        dataset_id=fixture[1].dataset_id,
        expected_dataset_hash=fixture[1].dataset_hash,
        expected_manifest_hash=fixture[1].manifest_hash,
        market_data_root=fixture[2],
        repo_root=fixture[3],
    )

    assert set(loaded.rows_by_symbol) == set(TIINGO_ETF_D1_SYMBOLS)


def test_loader_rejects_tampered_canonical_bytes(tmp_path: Path) -> None:
    destination, snapshot, market_root, repo_root = _snapshot_fixture(tmp_path)
    canonical = destination / "ohlcv_1d.csv.gz"
    canonical.write_bytes(canonical.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="canonical hash mismatch"):
        load_verified_tiingo_etf_d1_snapshot(
            destination,
            dataset_id=snapshot.dataset_id,
            expected_dataset_hash=snapshot.dataset_hash,
            expected_manifest_hash=snapshot.manifest_hash,
            market_data_root=market_root,
            repo_root=repo_root,
        )


def test_collection_receipt_is_external_and_aggregate_only(tmp_path: Path) -> None:
    _destination_path, snapshot, _market_root, repo_root = _snapshot_fixture(tmp_path)
    artifact_root = tmp_path / "model-artifacts"

    receipt_path = write_tiingo_etf_d1_receipt(
        snapshot,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    text = receipt_path.read_text(encoding="utf-8")
    assert receipt_path.is_relative_to(artifact_root)
    assert "unit-token" not in text
    assert "100.00" not in text
    assert '"raw_market_data_written": false' in text
    assert '"point_in_time_eligible": false' in text
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_tiingo_etf_d1_receipt(
            snapshot,
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
        )


def test_rejects_storage_floor_before_reading_a_token(tmp_path: Path) -> None:
    market_root = tmp_path / "market-data"
    market_root.mkdir()
    destination = _destination(market_root)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(TiingoEtfDailyError, match="storage floor"):
        acquire_tiingo_etf_d1_snapshot(
            env_path=tmp_path / "missing.env",
            destination=destination,
            requested_start=_START,
            requested_end=_END,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=market_root,
            repo_root=repo_root,
            disk_usage=lambda _path: SimpleNamespace(total=100, free=14),
        )


def test_normalizer_ignores_adjusted_fields_and_rejects_missing_raw_fields() -> None:
    rows = normalize_tiingo_etf_d1_response(symbol="SPY", raw_response=_payload("SPY"))
    assert len(rows) == 4
    assert not hasattr(rows[0], "adj_close")
    malformed = [{"date": "2024-01-02T00:00:00.000Z", "adjClose": "100"}]

    with pytest.raises(ValueError, match="open is invalid"):
        normalize_tiingo_etf_d1_response(
            symbol="SPY",
            raw_response=json.dumps(malformed).encode("utf-8"),
        )


def _snapshot_fixture(tmp_path: Path):
    market_root = tmp_path / "market-data"
    market_root.mkdir()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    env_path = tmp_path / ".env"
    env_path.write_text("TIINGO_API_TOKEN=unit-token\n")
    destination = _destination(market_root)

    def opener(request, *, timeout: float):
        symbol = urlparse(request.full_url).path.split("/")[-2]
        return _Response(_payload(symbol))

    snapshot = acquire_tiingo_etf_d1_snapshot(
        env_path=env_path,
        destination=destination,
        requested_start=_START,
        requested_end=_END,
        retrieved_at_utc=_RETRIEVED_AT,
        market_data_root=market_root,
        repo_root=repo_root,
        opener=opener,
    )
    return destination, snapshot, market_root, repo_root


def _destination(market_root: Path) -> Path:
    return (
        market_root
        / "us_equities"
        / "tiingo_etf_daily"
        / "canonical"
        / "snapshot=20260801T010203Z-tiingo-etf-d1-r1"
    )


def _payload(symbol: str) -> bytes:
    offset = {"SPY": 0, "QQQ": 10, "IWM": 20}[symbol]
    rows = []
    for index, session in enumerate(("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05")):
        price = 100 + offset + index
        rows.append(
            {
                "date": f"{session}T00:00:00.000Z",
                "open": f"{price}.00",
                "high": f"{price + 1}.00",
                "low": f"{price - 1}.00",
                "close": f"{price + 0.50:.2f}",
                "volume": str(1000 + index),
                "divCash": "1.00" if index == 2 else "0.00",
                "splitFactor": "1.00",
                "adjClose": "do-not-use",
            }
        )
    return json.dumps(rows, separators=(",", ":")).encode("utf-8")


class _Response:
    status = 200

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload
