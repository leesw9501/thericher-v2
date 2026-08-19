from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import json
import re
import socket
import urllib.request
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from thericher_v2.data import CatalogedBars, load_cataloged_yahoo_intraday_1m_bars
from thericher_v2.data.catalog import (
    build_training_readiness_catalog,
    derive_catalog_id,
    inspect_ohlcv_file,
    select_catalog_dataset,
    write_training_readiness_catalog,
)

FIELDS = ("symbol", "timestamp_utc", "session_date", "open", "high", "low", "close", "volume")


def test_inspection_records_quality_lineage_and_postdated_holdout(tmp_path: Path) -> None:
    path = tmp_path / "snapshot=2026-01-05" / "ohlcv_1m.csv.gz"
    _write_rows(
        path,
        [
            _row("AAA", "2026-01-02T14:30:00Z", "2026-01-02"),
            _row("AAA", "2026-01-02T14:32:00Z", "2026-01-02"),
            _row("AAA", "2026-01-02T14:32:00Z", "2026-01-02"),
            _row("AAA", "2026-01-02T14:31:00Z", "2026-01-02", high="8", volume=""),
        ],
    )

    result = inspect_ohlcv_file(
        path,
        timeframe="1m",
        proposed_holdout_start=date(2026, 1, 3),
        provenance_proves_point_in_time=True,
        minimum_training_sessions=1,
    )

    assert result["row_count"] == 4
    assert result["as_of_construction_date"] == "2026-01-05"
    assert result["as_of_construction_date_derivation"].startswith("snapshot_partition:")
    assert len(result["sha256"]) == 64
    assert result["dataset_hash"] == f"sha256:{result['sha256']}"
    assert result["dataset_id"]
    assert datetime.fromisoformat(result["constructed_as_of_utc"]).tzinfo is UTC
    assert result["ranking_eligible"] is result["training_eligible"]
    assert result["duplicate_symbol_timestamp_count"] == 1
    assert result["duplicate_count_is_exact"] is True
    assert result["non_monotonic_count"] == 1
    assert result["critical_nulls"]["volume"] == 1
    assert result["ohlcv_invariant_failures"]["counts"]["high_below_ohlc"] == 1
    assert result["interval_gaps"]["gap_transition_count"] == 1
    assert result["training_eligible"] is False
    assert result["sealed_holdout_eligible"] is False
    assert any(
        "postdates" in reason for reason in result["sealed_holdout_eligibility_reasons"]
    )


def test_unproven_point_in_time_provenance_rejects_sealed_holdout(tmp_path: Path) -> None:
    path = tmp_path / "snapshot=2026-01-01" / "ohlcv_daily.csv.gz"
    _write_rows(
        path,
        [
            _row("AAA", "2026-01-02", "2026-01-02"),
            _row("AAA", "2026-01-03", "2026-01-03"),
        ],
    )

    result = inspect_ohlcv_file(
        path,
        timeframe="1d",
        proposed_holdout_start=date(2026, 1, 3),
        provenance_proves_point_in_time=False,
        minimum_training_sessions=1,
    )

    assert result["training_eligible"] is False
    assert result["sealed_holdout_eligible"] is False
    assert any(
        "point-in-time provenance" in reason
        for reason in result["sealed_holdout_eligibility_reasons"]
    )


def test_inspection_derives_session_from_timestamp_date_column(tmp_path: Path) -> None:
    path = tmp_path / "snapshot=2026-01-02" / "ohlcv_1m.csv.gz"
    fieldnames = ("symbol", "date", "open", "high", "low", "close", "volume")
    _write_rows(
        path,
        [
            _date_timestamp_row("AAA", "2026-01-02T14:30:00Z"),
            _date_timestamp_row("AAA", "2026-01-02T14:32:00Z"),
        ],
        fieldnames=fieldnames,
    )

    result = inspect_ohlcv_file(
        path,
        timeframe="1m",
        proposed_holdout_start=None,
        provenance_proves_point_in_time=True,
        minimum_training_sessions=1,
    )

    assert result["timestamp"]["column"] == "date"
    assert result["session"] == {
        "column": "date",
        "min": "2026-01-02",
        "max": "2026-01-02",
        "count": 1,
        "row_counts": {"2026-01-02": 2},
        "invalid_count": 0,
    }
    assert result["interval_gaps"]["gap_transition_count"] == 1
    assert result["interval_gaps"]["missing_interval_count"] == 1
    assert result["training_eligible"] is True


def test_catalog_bounds_daily_inventory_and_writes_one_external_json(tmp_path: Path) -> None:
    intraday_paths = []
    for index in range(3):
        path = tmp_path / "intraday" / f"snapshot=2026-01-0{index + 1}" / "ohlcv_1m.csv.gz"
        _write_rows(path, [_row(f"S{index}", "2026-01-02T14:30:00Z", "2026-01-02")])
        intraday_paths.append(path)
    daily_root = tmp_path / "daily"
    for day in (1, 2, 3):
        _write_rows(
            daily_root / f"snapshot=2026-02-0{day}" / "ohlcv_daily.csv.gz",
            [_row("AAA", f"2025-12-0{day}", f"2025-12-0{day}")],
        )
    catalog = build_training_readiness_catalog(
        intraday_paths=intraday_paths,
        daily_root=daily_root,
        proposed_holdout_start=date(2026, 1, 1),
        generated_at=datetime(2026, 7, 18, tzinfo=UTC),
        daily_inventory_limit=2,
        daily_sample_limit=1,
    )
    later_catalog = build_training_readiness_catalog(
        intraday_paths=intraday_paths,
        daily_root=daily_root,
        proposed_holdout_start=date(2026, 1, 1),
        generated_at=datetime(2026, 7, 19, tzinfo=UTC),
        daily_inventory_limit=2,
        daily_sample_limit=1,
    )

    assert len(catalog["intraday_files"]) == 3
    assert catalog["daily_universe"]["discovered_file_count"] == 3
    assert catalog["daily_universe"]["inventory_truncated"] is True
    assert len(catalog["daily_universe"]["inventory"]) == 2
    assert len(catalog["daily_universe"]["samples"]) == 1
    assert "snapshot=2026-02-03" in catalog["daily_universe"]["samples"][0]["path"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", catalog["catalog_id"])
    assert later_catalog["catalog_id"] == catalog["catalog_id"]

    volatile_copy = copy.deepcopy(catalog)
    volatile_copy["generated_at"] = "2099-01-01T00:00:00+00:00"
    volatile_copy["storage"]["free_bytes"] = 1
    volatile_copy["storage"]["free_percent"] = 0.01
    assert derive_catalog_id(volatile_copy) == catalog["catalog_id"]

    dataset = select_catalog_dataset(
        catalog,
        catalog["intraday_files"][0]["dataset_id"],
    )
    assert set(
        (
            "dataset_id",
            "dataset_hash",
            "constructed_as_of_utc",
            "ranking_eligible",
            "sealed_holdout_eligible",
        )
    ) <= dataset.keys()
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", dataset["dataset_hash"])
    assert datetime.fromisoformat(dataset["constructed_as_of_utc"]).utcoffset() == (
        datetime.min.replace(tzinfo=UTC).utcoffset()
    )
    with pytest.raises(KeyError, match="dataset_id not found"):
        select_catalog_dataset(catalog, "missing-dataset")

    artifact = write_training_readiness_catalog(
        catalog,
        artifact_root=tmp_path / "artifacts",
        run_id="catalog-test-r1",
        repo_root=tmp_path / "repo",
    )
    assert artifact.name == "catalog.json"
    assert json.loads(artifact.read_text(encoding="utf-8"))["kind"] == (
        "training_readiness_catalog"
    )
    assert list(artifact.parent.iterdir()) == [artifact]
    with pytest.raises(FileExistsError):
        write_training_readiness_catalog(
            catalog,
            artifact_root=tmp_path / "artifacts",
            run_id="catalog-test-r1",
        )


def test_cataloged_bars_bind_actual_gzip_hash_and_reject_replaced_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "snapshot=2026-07-18" / "ohlcv_1m.csv.gz"
    _write_rows(
        path,
        [
            _row("AAA", "2026-01-02T14:30:00Z", "2026-01-02"),
            _row("BBB", "2026-01-02T14:30:00Z", "2026-01-02"),
            _row("AAA", "2026-01-02T14:31:00Z", "2026-01-02"),
        ],
    )
    expected_hash = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("cataloged local bars must not use network")

    original_open = Path.open

    def guard_credentials(candidate: Path, *args: object, **kwargs: object):
        lowered = candidate.name.lower()
        if lowered.startswith(".env") or any(
            marker in lowered for marker in ("credential", "secret", "token")
        ):
            raise AssertionError("cataloged local bars must not read credentials")
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(Path, "open", guard_credentials)

    loaded = load_cataloged_yahoo_intraday_1m_bars(
        path,
        dataset_id="unit.yahoo.1m.snapshot=2026-07-18",
        expected_dataset_hash=expected_hash,
        max_bars=2,
    )

    assert tuple(CatalogedBars.__dataclass_fields__) == (
        "dataset_id",
        "dataset_hash",
        "source_path",
        "bars",
    )
    assert loaded.dataset_hash == expected_hash
    assert loaded.source_path == path
    assert len(loaded.bars) == 2
    assert [bar.start_ts for bar in loaded.bars] == [
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 14, 31, tzinfo=UTC),
    ]
    assert all(
        bar.symbol == "AAA"
        and bar.market == "US"
        and bar.timeframe.value == "1m"
        and bar.complete
        for bar in loaded.bars
    )
    with pytest.raises(ValueError, match="use load_cataloged_yahoo_intraday_1m_bars"):
        CatalogedBars(
            dataset_id=loaded.dataset_id,
            dataset_hash=loaded.dataset_hash,
            source_path=tmp_path / "arbitrary.csv.gz",
            bars=loaded.bars,
        )
    with pytest.raises(FrozenInstanceError):
        loaded.dataset_id = "changed"  # type: ignore[misc]

    with pytest.raises(FileNotFoundError):
        load_cataloged_yahoo_intraday_1m_bars(
            tmp_path / "missing.csv.gz",
            dataset_id=loaded.dataset_id,
            expected_dataset_hash=expected_hash,
        )

    arbitrary_path = tmp_path / "arbitrary.csv.gz"
    arbitrary_path.write_bytes(b"not gzip campaign evidence")
    arbitrary_hash = "sha256:" + hashlib.sha256(arbitrary_path.read_bytes()).hexdigest()
    with pytest.raises(gzip.BadGzipFile):
        load_cataloged_yahoo_intraday_1m_bars(
            arbitrary_path,
            dataset_id=loaded.dataset_id,
            expected_dataset_hash=arbitrary_hash,
        )

    path.write_bytes(b"replaced after cataloging")
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        load_cataloged_yahoo_intraday_1m_bars(
            path,
            dataset_id=loaded.dataset_id,
            expected_dataset_hash=expected_hash,
        )


def _row(
    symbol: str,
    timestamp: str,
    session: str,
    *,
    high: str = "11",
    volume: str = "100",
) -> dict[str, str]:
    return {
        "symbol": symbol,
        "timestamp_utc": timestamp,
        "session_date": session,
        "open": "10",
        "high": high,
        "low": "9",
        "close": "10.5",
        "volume": volume,
    }


def _date_timestamp_row(symbol: str, timestamp: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "date": timestamp,
        "open": "10",
        "high": "11",
        "low": "9",
        "close": "10.5",
        "volume": "100",
    }


def _write_rows(
    path: Path,
    rows: list[dict[str, str]],
    *,
    fieldnames: tuple[str, ...] = FIELDS,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
