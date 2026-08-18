from __future__ import annotations

import hashlib
import json
import socket
import zipfile
from pathlib import Path

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.data import firstrate_free_intraday_batch as batch
from thericher_v2.data.local import LocalCsvBarProvider
from thericher_v2.data.provider import BarQuery


def test_batch_normalizes_the_fixed_source_scope_with_a_source_safe_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    acquisition_path = artifact_root / "data-receipts" / "acquisition.json"
    spy_hash = _write_archive(
        market_data_root,
        symbol="SPY",
        rows=(
            ("2024-03-11 09:30:00", "100", "101", "99", "100.5", "10"),
            ("2024-03-11 09:32:00", "102", "103", "101", "102.5", "12"),
        ),
    )
    qqq_hash = _write_archive(
        market_data_root,
        symbol="QQQ",
        rows=(
            ("2024-03-11 09:30:00", "200", "201", "199", "200.5", "20"),
            ("2024-03-11 09:32:00", "202", "203", "201", "202.5", "22"),
        ),
    )
    _write_acquisition_receipt(acquisition_path, spy_hash=spy_hash, qqq_hash=qqq_hash)

    def unexpected_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("batch normalizer must not access the network")

    monkeypatch.setattr(socket, "create_connection", unexpected_network)
    first = batch.normalize_staged_firstrate_free_intraday_archives(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        acquisition_receipt_path=acquisition_path,
    )
    second = batch.normalize_staged_firstrate_free_intraday_archives(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        acquisition_receipt_path=acquisition_path,
    )

    assert first == second
    assert first["status"] == "completed"
    assert first["receipt_path_relative_to_artifact_root"] == (
        "data-receipts/firstrate-free-intraday/"
        "firstrate-free-intraday-source-local-normalization-v1.json"
    )
    spy_path = market_data_root / "us_equities/firstrate_free_intraday/canonical/SPY_1m.csv"
    provider_bars = LocalCsvBarProvider(spy_path).get_bars(
        BarQuery(symbol="SPY", market="US", timeframe=Timeframe.M1)
    )
    assert [bar.start_ts.isoformat() for bar in provider_bars] == [
        "2024-03-11T13:30:00+00:00",
        "2024-03-11T13:32:00+00:00",
    ]
    assert all(bar.start_ts.isoformat() != "2024-03-11T13:31:00+00:00" for bar in provider_bars)
    assert [str(bar.close) for bar in provider_bars] == ["100.5", "102.5"]
    assert all(bar.complete for bar in provider_bars)

    receipt_path = artifact_root / str(first["receipt_path_relative_to_artifact_root"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["safety"] == {
        "credentials_read": False,
        "git_tracked_files_changed": False,
        "kis_or_broker_called": False,
        "market_data_written_outside_market_data_root": False,
        "network_access": False,
        "raw_market_rows_retained_in_receipt": False,
    }
    assert receipt["quality"] == {
        "reindex_or_fill": False,
        "session_coverage": "not_assessed",
        "source_timestamp_semantics": "unverified",
        "timestamp_set_rule": "emitted_must_equal_decoded_source_timestamp_set",
        "timezone_conversion": "America/New_York -> UTC",
    }
    assert [item["symbol"] for item in receipt["normalizations"]] == ["SPY", "QQQ"]
    assert all(item["timestamp_set_equal"] is True for item in receipt["normalizations"])
    assert "100.5" not in receipt_path.read_text(encoding="utf-8")


def test_batch_rejects_an_unexpected_acquisition_scope_without_output(tmp_path: Path) -> None:
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    acquisition_path = artifact_root / "data-receipts" / "acquisition.json"
    spy_hash = _write_archive(
        market_data_root,
        symbol="SPY",
        rows=(("2024-03-11 09:30:00", "100", "101", "99", "100.5", "10"),),
    )
    _write_acquisition_receipt(acquisition_path, spy_hash=spy_hash, qqq_hash=None)

    with pytest.raises(ValueError, match="exactly SPY and QQQ"):
        batch.normalize_staged_firstrate_free_intraday_archives(
            market_data_root=market_data_root,
            artifact_root=artifact_root,
            acquisition_receipt_path=acquisition_path,
        )

    assert not (market_data_root / "us_equities/firstrate_free_intraday/canonical").exists()
    assert not (
        artifact_root
        / "data-receipts/firstrate-free-intraday/"
        "firstrate-free-intraday-source-local-normalization-v1.json"
    ).exists()


def test_batch_rejects_a_root_inside_git(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"

    with pytest.raises(ValueError, match="must stay outside Git"):
        batch.normalize_staged_firstrate_free_intraday_archives(
            market_data_root=Path(__file__).resolve().parents[1],
            artifact_root=artifact_root,
        )


def _write_archive(
    market_data_root: Path,
    *,
    symbol: str,
    rows: tuple[tuple[str, str, str, str, str, str], ...],
) -> str:
    relative_path = Path(
        f"us_equities/firstrate_free_intraday/raw/{symbol}_1min_sample_firstratedata.zip"
    )
    path = market_data_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    source_csv = "timestamp,open,high,low,close,volume\n" + "".join(
        ",".join(row) + "\n" for row in rows
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{symbol}_1min_firstratedata.csv", source_csv)
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_acquisition_receipt(
    path: Path,
    *,
    spy_hash: str,
    qqq_hash: str | None,
) -> None:
    archives = [_archive_receipt_entry("SPY", spy_hash)]
    if qqq_hash is not None:
        archives.append(_archive_receipt_entry("QQQ", qqq_hash))
    payload = {
        "schema_version": "firstrate-free-intraday-acquisition-receipt-v1",
        "source": {"provider": "FirstRate Data"},
        "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
        "archives": archives,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _archive_receipt_entry(symbol: str, archive_hash: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "market_data_relative_path": (
            f"us_equities/firstrate_free_intraday/raw/{symbol}_1min_sample_firstratedata.zip"
        ),
        "sha256": archive_hash,
        "archive_entry_name": f"{symbol}_1min_firstratedata.csv",
        "archive_file_count": 1,
        "archive_paths_safe": True,
    }
