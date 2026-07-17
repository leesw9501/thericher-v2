from __future__ import annotations

import csv
import gzip
import hashlib
import json
import socket
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.data import (
    DEVELOPMENT_MIN_SESSIONS,
    FACTOR_CHANGE_RELATIVE_THRESHOLD,
    FIXED_ETF_DAILY_SYMBOLS,
    build_fixed_etf_daily_raw_subset,
    build_fixed_etf_daily_subset,
    load_cataloged_yahoo_daily_1d_bars,
    load_fixed_etf_daily_factor_change_dates,
)

SOURCE_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
    "asset_type",
    "yahoo_symbol",
    "source",
)


def test_derives_raw_r2_without_mutating_or_overwriting_r1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.csv.gz"
    start = date(2020, 1, 1)
    rows = [_source_row("AAPL", start)]
    for offset in reversed(range(DEVELOPMENT_MIN_SESSIONS)):
        session = start + timedelta(days=offset)
        for symbol in reversed(FIXED_ETF_DAILY_SYMBOLS):
            rows.append(_source_row(symbol, session))
    _write_source(source, rows)
    expected_source_hash = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()

    source_open_count = 0
    original_open = Path.open

    def count_source_open(candidate: Path, *args: object, **kwargs: object):
        nonlocal source_open_count
        if candidate == source:
            source_open_count += 1
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", count_source_open)
    output = tmp_path / "snapshot=2026-07-18-r1"
    manifest_path = build_fixed_etf_daily_subset(
        source,
        output,
        constructed_at_utc=datetime(2026, 7, 18, tzinfo=UTC),
    )

    assert source_open_count == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"]["sha256"] == expected_source_hash
    assert manifest["row_count"] == DEVELOPMENT_MIN_SESSIONS * 3
    assert manifest["symbols"] == ["SPY", "QQQ", "IWM"]
    assert manifest["quality_counts"]["duplicate_symbol_date"] == 0
    assert manifest["eligibility"]["parser"]["eligible"] is True
    assert manifest["eligibility"]["development_training"]["eligible"] is True
    assert manifest["eligibility"]["ranking"]["eligible"] is False
    assert manifest["eligibility"]["sealed_holdout"]["eligible"] is False
    assert "raw_volume (unchanged)" in manifest["adjustment_policy"]["volume_formula"]

    with gzip.open(output / "ohlcv_1d.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        subset_rows = list(csv.DictReader(handle))
    assert [row["symbol"] for row in subset_rows[:DEVELOPMENT_MIN_SESSIONS]] == [
        "SPY"
    ] * DEVELOPMENT_MIN_SESSIONS
    spy_dates = [row["date"] for row in subset_rows[:DEVELOPMENT_MIN_SESSIONS]]
    assert spy_dates == sorted(spy_dates)
    first = subset_rows[0]
    assert Decimal(first["adjustment_factor"]) == Decimal("0.5")
    assert Decimal(first["open"]) == Decimal("50")
    assert Decimal(first["high"]) == Decimal("55")
    assert Decimal(first["low"]) == Decimal("45")
    assert Decimal(first["close"]) == Decimal("50")
    assert Decimal(first["volume"]) == Decimal("1000")

    r1_subset = output / "ohlcv_1d.csv.gz"
    r1_manifest_bytes = manifest_path.read_bytes()
    r1_subset_bytes = r1_subset.read_bytes()
    r2_output = tmp_path / "snapshot=2026-07-18-r2"
    r2_manifest_path = build_fixed_etf_daily_raw_subset(
        output,
        r2_output,
        constructed_at_utc=datetime(2026, 7, 18, tzinfo=UTC),
    )
    r2_manifest = json.loads(r2_manifest_path.read_text(encoding="utf-8"))
    assert source_open_count == 1
    assert manifest_path.read_bytes() == r1_manifest_bytes
    assert r1_subset.read_bytes() == r1_subset_bytes
    assert r2_manifest["lineage"]["parent_r1"]["dataset_hash"] == manifest["dataset_hash"]
    assert r2_manifest["lineage"]["original_source"]["sha256"] == expected_source_hash
    assert r2_manifest["supersedes"]["for_campaign_use"] is True
    assert r2_manifest["eligibility"]["development_training"]["eligible"] is True
    assert r2_manifest["eligibility"]["ranking"]["eligible"] is False
    assert r2_manifest["eligibility"]["sealed_holdout"]["eligible"] is False
    assert r2_manifest["raw_execution_policy"]["excluded_from_campaign"] == [
        "features",
        "labels",
        "fills",
        "thresholds",
        "metrics",
    ]
    assert FACTOR_CHANGE_RELATIVE_THRESHOLD == Decimal("0.0001")

    with gzip.open(
        r2_output / "ohlcv_1d.csv.gz", "rt", encoding="utf-8", newline=""
    ) as handle:
        raw_rows = list(csv.DictReader(handle))
    assert Decimal(raw_rows[0]["open"]) == Decimal("100")
    assert Decimal(raw_rows[0]["close"]) == Decimal("100")
    assert Decimal(raw_rows[0]["diagnostic_adjusted_open"]) == Decimal("50")
    assert Decimal(raw_rows[0]["diagnostic_adj_close"]) == Decimal("50")

    with pytest.raises(FileExistsError, match="immutable output snapshot"):
        build_fixed_etf_daily_subset(source, output)
    with pytest.raises(FileExistsError, match="immutable output snapshot"):
        build_fixed_etf_daily_raw_subset(output, r2_output)
    assert manifest_path.read_bytes() == r1_manifest_bytes
    assert r1_subset.read_bytes() == r1_subset_bytes


@pytest.mark.parametrize("fault", ["duplicate", "null", "invalid_ohlc"])
def test_rejects_duplicate_null_and_invalid_selected_rows(tmp_path: Path, fault: str) -> None:
    source = tmp_path / f"{fault}.csv.gz"
    rows = [_source_row(symbol, date(2026, 1, 2)) for symbol in FIXED_ETF_DAILY_SYMBOLS]
    if fault == "duplicate":
        rows.append(dict(rows[0]))
    elif fault == "null":
        rows[0]["open"] = ""
    else:
        rows[0]["high"] = "9"
    _write_source(source, rows)
    output = tmp_path / f"snapshot-{fault}"

    with pytest.raises(ValueError):
        build_fixed_etf_daily_subset(source, output)
    assert not output.exists()


def test_daily_loader_is_hash_bound_per_symbol_and_floor_can_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "small-source.csv.gz"
    rows = [
        _source_row(symbol, date(2026, 1, 2) + timedelta(days=offset))
        for offset in reversed(range(2))
        for symbol in reversed(FIXED_ETF_DAILY_SYMBOLS)
    ]
    _write_source(source, rows)
    r1_output = tmp_path / "snapshot-small-r1"
    build_fixed_etf_daily_subset(source, r1_output)
    r2_output = tmp_path / "snapshot-small-r2"
    manifest_path = build_fixed_etf_daily_raw_subset(r1_output, r2_output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    subset = r2_output / "ohlcv_1d.csv.gz"

    assert manifest["eligibility"]["parser"]["eligible"] is True
    assert manifest["eligibility"]["development_training"]["eligible"] is False
    assert manifest["eligibility"]["ranking"]["eligible"] is False
    assert manifest["eligibility"]["sealed_holdout"]["eligible"] is False

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("daily loader must remain offline")

    original_open = Path.open

    def guard_credentials(candidate: Path, *args: object, **kwargs: object):
        lowered = candidate.name.lower()
        if lowered.startswith(".env") or any(
            marker in lowered for marker in ("credential", "secret", "token")
        ):
            raise AssertionError("daily loader must not read credentials")
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(Path, "open", guard_credentials)

    with pytest.raises(ValueError, match="dataset_id mismatch"):
        load_cataloged_yahoo_daily_1d_bars(
            subset,
            dataset_id="caller-invented-dataset-id",
            expected_dataset_hash=manifest["dataset_hash"],
            symbol="SPY",
        )

    for symbol in FIXED_ETF_DAILY_SYMBOLS:
        loaded = load_cataloged_yahoo_daily_1d_bars(
            subset,
            dataset_id=manifest["dataset_id"],
            expected_dataset_hash=manifest["dataset_hash"],
            symbol=symbol,
        )
        assert len(loaded.bars) == 2
        assert loaded.dataset_hash == manifest["dataset_hash"]
        assert all(
            bar.symbol == symbol
            and bar.timeframe == Timeframe.D1
            and bar.complete
            and bar.open == Decimal("100")
            and bar.high == Decimal("110")
            and bar.low == Decimal("90")
            and bar.close == Decimal("100")
            for bar in loaded.bars
        )
        assert loaded.bars[0].start_ts < loaded.bars[1].start_ts
        assert (
            load_fixed_etf_daily_factor_change_dates(
                subset,
                expected_dataset_hash=manifest["dataset_hash"],
                symbol=symbol,
            )
            == ()
        )

    subset.write_bytes(b"tampered subset")
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        load_cataloged_yahoo_daily_1d_bars(
            subset,
            dataset_id=manifest["dataset_id"],
            expected_dataset_hash=manifest["dataset_hash"],
            symbol="SPY",
        )
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        load_fixed_etf_daily_factor_change_dates(
            subset,
            expected_dataset_hash=manifest["dataset_hash"],
            symbol="SPY",
        )


def test_daily_loaders_require_consistent_sibling_manifest_and_hash_lineage(
    tmp_path: Path,
) -> None:
    source = tmp_path / "manifest-source.csv.gz"
    _write_source(
        source,
        [_source_row(symbol, date(2026, 1, 2)) for symbol in FIXED_ETF_DAILY_SYMBOLS],
    )
    r1_output = tmp_path / "manifest-r1"
    build_fixed_etf_daily_subset(source, r1_output)
    r2_output = tmp_path / "manifest-r2"
    manifest_path = build_fixed_etf_daily_raw_subset(r1_output, r2_output)
    subset = r2_output / "ohlcv_1d.csv.gz"
    original_manifest_bytes = manifest_path.read_bytes()
    original_manifest = json.loads(original_manifest_bytes)
    dataset_hash = original_manifest["dataset_hash"]

    def load_bars() -> None:
        load_cataloged_yahoo_daily_1d_bars(
            subset,
            dataset_id=original_manifest["dataset_id"],
            expected_dataset_hash=dataset_hash,
            symbol="SPY",
        )

    def load_factor_dates() -> None:
        load_fixed_etf_daily_factor_change_dates(
            subset,
            expected_dataset_hash=dataset_hash,
            symbol="SPY",
        )

    manifest_path.unlink()
    with pytest.raises(ValueError, match="sibling manifest is required"):
        load_bars()
    with pytest.raises(ValueError, match="sibling manifest is required"):
        load_factor_dates()

    manifest_path.write_bytes(b"\xffnot-utf8")
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        load_bars()

    wrong_kind = dict(original_manifest)
    wrong_kind["kind"] = "tampered_kind"
    manifest_path.write_text(json.dumps(wrong_kind), encoding="utf-8")
    with pytest.raises(ValueError, match="required r2 dataset kind"):
        load_factor_dates()

    wrong_dataset_hash = dict(original_manifest)
    wrong_dataset_hash["dataset_hash"] = "sha256:" + "0" * 64
    manifest_path.write_text(json.dumps(wrong_dataset_hash), encoding="utf-8")
    with pytest.raises(ValueError, match="do not match the actual subset bytes"):
        load_bars()

    wrong_subset_hash = json.loads(original_manifest_bytes)
    wrong_subset_hash["subset"]["sha256"] = "sha256:" + "1" * 64
    manifest_path.write_text(json.dumps(wrong_subset_hash), encoding="utf-8")
    with pytest.raises(ValueError, match="do not match the actual subset bytes"):
        load_factor_dates()

    missing_lineage = dict(original_manifest)
    missing_lineage.pop("lineage")
    manifest_path.write_text(json.dumps(missing_lineage), encoding="utf-8")
    with pytest.raises(ValueError, match="missing hash lineage"):
        load_bars()
    with pytest.raises(ValueError, match="missing hash lineage"):
        load_factor_dates()


def test_daily_loader_allows_mount_relocation_but_preserves_path_tail_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "relocation-source.csv.gz"
    _write_source(
        source,
        [_source_row(symbol, date(2026, 1, 2)) for symbol in FIXED_ETF_DAILY_SYMBOLS],
    )
    r1_output = tmp_path / "snapshot=2026-07-18-r1"
    build_fixed_etf_daily_subset(source, r1_output)
    r2_output = tmp_path / "original-root" / "snapshot=2026-07-18-r2"
    manifest_path = build_fixed_etf_daily_raw_subset(r1_output, r2_output)
    subset_path = r2_output / "ohlcv_1d.csv.gz"
    manifest_bytes = manifest_path.read_bytes()
    subset_bytes = subset_path.read_bytes()
    manifest = json.loads(manifest_bytes)

    relocated = tmp_path / "docker-mount" / "market_data" / r2_output.name
    relocated.mkdir(parents=True)
    relocated_manifest = relocated / "manifest.json"
    relocated_subset = relocated / "ohlcv_1d.csv.gz"
    relocated_manifest.write_bytes(manifest_bytes)
    relocated_subset.write_bytes(subset_bytes)

    loaded = load_cataloged_yahoo_daily_1d_bars(
        relocated_subset,
        dataset_id=manifest["dataset_id"],
        expected_dataset_hash=manifest["dataset_hash"],
        symbol="SPY",
    )
    assert len(loaded.bars) == 1
    assert relocated_manifest.read_bytes() == manifest_bytes
    assert load_fixed_etf_daily_factor_change_dates(
        relocated_subset,
        expected_dataset_hash=manifest["dataset_hash"],
        symbol="SPY",
    ) == ()

    wrong_snapshot = tmp_path / "other-root" / "snapshot=wrong-r2"
    wrong_snapshot.mkdir(parents=True)
    (wrong_snapshot / "manifest.json").write_bytes(manifest_bytes)
    wrong_snapshot_subset = wrong_snapshot / "ohlcv_1d.csv.gz"
    wrong_snapshot_subset.write_bytes(subset_bytes)
    with pytest.raises(ValueError, match="inconsistent with its snapshot path"):
        load_cataloged_yahoo_daily_1d_bars(
            wrong_snapshot_subset,
            dataset_id=manifest["dataset_id"],
            expected_dataset_hash=manifest["dataset_hash"],
            symbol="SPY",
        )

    wrong_basename = relocated / "different.csv.gz"
    wrong_basename.write_bytes(subset_bytes)
    with pytest.raises(ValueError, match="expected file basename"):
        load_cataloged_yahoo_daily_1d_bars(
            wrong_basename,
            dataset_id=manifest["dataset_id"],
            expected_dataset_hash=manifest["dataset_hash"],
            symbol="SPY",
        )


def test_factor_change_uses_prespecified_relative_threshold_and_helper(
    tmp_path: Path,
) -> None:
    source = tmp_path / "factor-change.csv.gz"
    start = date(2026, 1, 2)
    factors = (Decimal("1"), Decimal("1.00009"), Decimal("1.000190009"))
    rows: list[dict[str, str]] = []
    for offset, factor in enumerate(factors):
        session = start + timedelta(days=offset)
        for symbol in FIXED_ETF_DAILY_SYMBOLS:
            row = _source_row(symbol, session)
            row["adj_close"] = str(Decimal(row["close"]) * factor)
            rows.append(row)
    _write_source(source, rows)
    r1_output = tmp_path / "factor-r1"
    build_fixed_etf_daily_subset(source, r1_output)
    r2_output = tmp_path / "factor-r2"
    manifest_path = build_fixed_etf_daily_raw_subset(r1_output, r2_output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    subset = r2_output / "ohlcv_1d.csv.gz"

    spy_evidence = manifest["factor_change_diagnostic"]["per_symbol"]["SPY"]
    expected_date = start + timedelta(days=2)
    assert manifest["factor_change_diagnostic"]["formula"] == (
        "abs(current_factor / previous_factor - 1)"
    )
    assert manifest["factor_change_diagnostic"]["threshold_relative"] == "0.0001"
    assert spy_evidence == {"count": 1, "dates": [expected_date.isoformat()]}
    assert load_fixed_etf_daily_factor_change_dates(
        subset,
        expected_dataset_hash=manifest["dataset_hash"],
        symbol="SPY",
    ) == (expected_date,)

    with gzip.open(subset, "rt", encoding="utf-8", newline="") as handle:
        spy_rows = [row for row in csv.DictReader(handle) if row["symbol"] == "SPY"]
    assert [row["factor_change"] for row in spy_rows] == ["0", "0", "1"]
    loaded = load_cataloged_yahoo_daily_1d_bars(
        subset,
        dataset_id=manifest["dataset_id"],
        expected_dataset_hash=manifest["dataset_hash"],
        symbol="SPY",
    )
    assert all(bar.open == Decimal("100") for bar in loaded.bars)
    assert Decimal(spy_rows[-1]["diagnostic_adjusted_open"]) != loaded.bars[-1].open


def _source_row(symbol: str, session: date) -> dict[str, str]:
    return {
        "symbol": symbol,
        "date": session.isoformat(),
        "open": "100",
        "high": "110",
        "low": "90",
        "close": "100",
        "volume": "1000",
        "adj_close": "50",
        "asset_type": "stock",
        "yahoo_symbol": symbol,
        "source": "synthetic_fixture",
    }


def _write_source(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
