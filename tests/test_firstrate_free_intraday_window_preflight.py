from __future__ import annotations

import csv
import hashlib
import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import firstrate_free_intraday_window_preflight as preflight
from thericher_v2.data.local import CSV_FIELDS, bar_to_record
from thericher_v2.data.resample import resample_bars


def test_builds_only_source_safe_fixed_window_geometry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_data_root, artifact_root = _write_fixture(tmp_path, count=360)

    def unexpected_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("window preflight must not access the network")

    monkeypatch.setattr(socket, "create_connection", unexpected_network)
    result = preflight.build_firstrate_source_local_window_preflight(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
    )

    assert result == {
        "status": "completed",
        "manifest_path_relative_to_artifact_root": (
            "data-receipts/firstrate-free-intraday/"
            "firstrate-free-intraday-source-local-window-preflight-v1.json"
        ),
        "symbol_count": 2,
    }
    manifest = json.loads(
        (
            artifact_root
            / "data-receipts"
            / "firstrate-free-intraday"
            / "firstrate-free-intraday-source-local-window-preflight-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["window_matrix"] == {
        "ordered_timeframes": ["1m", "5m", "10m", "1h", "3h"],
        "windows_by_timeframe": [
            {"timeframe": "1m", "window_sizes_bars": [30, 60, 120, 240]},
            {"timeframe": "5m", "window_sizes_bars": [12, 24, 48]},
            {"timeframe": "10m", "window_sizes_bars": [6, 12, 24]},
            {"timeframe": "1h", "window_sizes_bars": [3, 6, 12]},
            {"timeframe": "3h", "window_sizes_bars": [2, 4, 8]},
        ],
        "window_eligibility": {
            "all_bars_complete": True,
            "adjacent_start_delta_equals_declared_timeframe": True,
            "reindex_or_fill": False,
            "rejected_window_interpretation": "source_local_geometry_only",
            "window_end_definition": "last_bar_end_ts",
        },
    }
    assert manifest["safety"] == {
        "credentials_read": False,
        "network_access": False,
        "kis_or_broker_called": False,
        "raw_market_rows_retained_in_manifest": False,
        "feature_values_retained_in_manifest": False,
        "labels_retained_in_manifest": False,
        "predictions_or_weights_retained_in_manifest": False,
        "resampled_bars_retained_in_manifest": False,
        "market_data_written_outside_market_data_root": False,
        "git_tracked_files_changed": False,
    }
    first_symbol = manifest["symbols"][0]
    first_timeframe = first_symbol["timeframes"][0]
    assert first_symbol["symbol"] == "SPY"
    assert [
        cell["eligible_window_count"] for cell in first_timeframe["cells"]
    ] == [331, 301, 241, 121]
    assert all(
        cell["every_eligible_window_complete_and_strictly_contiguous"] is True
        and cell["eligible_end_timestamp_set_sha256"].startswith("sha256:")
        for symbol in manifest["symbols"]
        for timeframe in symbol["timeframes"]
        for cell in timeframe["cells"]
    )
    assert not {"open", "high", "low", "close", "volume"}.intersection(
        _all_keys(manifest)
    )


def test_gap_does_not_bridge_a_preflight_window(tmp_path: Path) -> None:
    market_data_root, artifact_root = _write_fixture(tmp_path, count=300, skipped_index=100)

    preflight.build_firstrate_source_local_window_preflight(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
    )
    manifest = json.loads(
        (
            artifact_root
            / "data-receipts"
            / "firstrate-free-intraday"
            / "firstrate-free-intraday-source-local-window-preflight-v1.json"
        ).read_text(encoding="utf-8")
    )
    first_cell = manifest["symbols"][0]["timeframes"][0]["cells"][0]

    assert first_cell["window_size_bars"] == 30
    assert first_cell["eligible_window_count"] == 241
    assert first_cell["eligible_window_count"] < 299 - 30 + 1


def test_rejects_canonical_or_mechanics_hash_tampering(tmp_path: Path) -> None:
    market_data_root, artifact_root = _write_fixture(tmp_path, count=360)
    canonical_path = (
        market_data_root / "us_equities" / "firstrate_free_intraday" / "canonical" / "SPY_1m.csv"
    )
    canonical_path.write_text(canonical_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="canonical CSV hash"):
        preflight.build_firstrate_source_local_window_preflight(
            market_data_root=market_data_root,
            artifact_root=artifact_root,
        )

    market_data_root, artifact_root = _write_fixture(tmp_path / "second", count=360)
    mechanics_path = (
        artifact_root
        / "data-receipts"
        / "firstrate-free-intraday"
        / "firstrate-free-intraday-source-local-timeframe-mechanics-v1.json"
    )
    mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
    mechanics["symbols"][0]["timeframes"][0]["bar_content_sha256"] = "sha256:" + "0" * 64
    mechanics_path.write_text(
        json.dumps(mechanics, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="resampled bar content"):
        preflight.build_firstrate_source_local_window_preflight(
            market_data_root=market_data_root,
            artifact_root=artifact_root,
        )


def test_rejects_repository_artifact_destination_and_is_idempotent(tmp_path: Path) -> None:
    market_data_root, artifact_root = _write_fixture(tmp_path, count=360)
    first = preflight.build_firstrate_source_local_window_preflight(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
    )
    second = preflight.build_firstrate_source_local_window_preflight(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
    )

    assert second == first
    with pytest.raises(
        ValueError, match="preflight_manifest_path must stay under its external root"
    ):
        preflight.build_firstrate_source_local_window_preflight(
            market_data_root=market_data_root,
            artifact_root=artifact_root,
            preflight_manifest_path=Path(__file__),
        )


def _write_fixture(
    tmp_path: Path, *, count: int, skipped_index: int | None = None
) -> tuple[Path, Path]:
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    canonical_relative_root = Path("us_equities/firstrate_free_intraday/canonical")
    normalization_rows: list[dict[str, object]] = []
    mechanics_symbols: list[dict[str, object]] = []
    for symbol in ("SPY", "QQQ"):
        bars = _bars(symbol, count=count, skipped_index=skipped_index)
        canonical_relative_path = canonical_relative_root / f"{symbol}_1m.csv"
        canonical_path = market_data_root / canonical_relative_path
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        with canonical_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(bar_to_record(bar) for bar in bars)
        canonical_sha256 = _sha256(canonical_path.read_bytes())
        timestamp_hash = _timestamp_hash(bars)
        normalization_rows.append(
            {
                "symbol": symbol,
                "market": "US",
                "timeframe": "1m",
                "canonical_market_data_relative_path": canonical_relative_path.as_posix(),
                "canonical_sha256": canonical_sha256,
                "bar_count": len(bars),
                "emitted_timestamp_set_sha256": timestamp_hash,
                "timestamp_set_equal": True,
            }
        )
        mechanics_symbols.append(
            {
                "symbol": symbol,
                "market": "US",
                "canonical_market_data_relative_path": canonical_relative_path.as_posix(),
                "canonical_sha256": canonical_sha256,
                "canonical_hash_matches_normalization_receipt": True,
                "source_bar_count": len(bars),
                "source_timestamp_set_sha256": timestamp_hash,
                "source_timestamps_strictly_ordered_unique": True,
                "source_bars_complete": True,
                "timeframes": [
                    _mechanics_timeframe(bars, timeframe) for timeframe in _timeframes()
                ],
            }
        )

    receipt_directory = artifact_root / "data-receipts" / "firstrate-free-intraday"
    normalization_path = receipt_directory / "normalization.json"
    normalization = {
        "schema_version": "firstrate-free-intraday-normalization-receipt-v1",
        "status": "completed",
        "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
        "normalizations": normalization_rows,
    }
    _write_json(normalization_path, normalization)
    mechanics = {
        "schema_version": "firstrate-free-intraday-source-local-timeframe-mechanics-v1",
        "receipt_id": "firstrate-free-intraday-source-local-timeframe-mechanics-v1",
        "status": "completed",
        "normalization_receipt": {
            "relative_to_artifact_root": True,
            "path": "data-receipts/firstrate-free-intraday/normalization.json",
            "sha256": _sha256(normalization_path.read_bytes()),
        },
        "symbols": mechanics_symbols,
        "resampling_contract": {
            "source_timeframe": "1m",
            "target_timeframes": [timeframe.value for timeframe in _timeframes()],
            "bucket_anchor": "utc_epoch",
            "bucket_retention": "complete_unique_contiguous_source_minutes_only",
            "reindex_or_fill": False,
            "resampled_bars_persisted": False,
        },
        "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
    }
    _write_json(
        receipt_directory / "firstrate-free-intraday-source-local-timeframe-mechanics-v1.json",
        mechanics,
    )
    return market_data_root, artifact_root


def _bars(symbol: str, *, count: int, skipped_index: int | None) -> list[Bar]:
    start = datetime(2025, 1, 2, tzinfo=UTC)
    bars: list[Bar] = []
    for index in range(count):
        if index == skipped_index:
            continue
        value = Decimal("100") + Decimal(index)
        bars.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.M1,
                start_ts=start + timedelta(minutes=index),
                open=value,
                high=value + Decimal("1"),
                low=value - Decimal("1"),
                close=value + Decimal("0.5"),
                volume=Decimal("1000"),
                complete=True,
            )
        )
    return bars


def _mechanics_timeframe(bars: list[Bar], timeframe: Timeframe) -> dict[str, object]:
    resampled = resample_bars(bars, timeframe)
    return {
        "timeframe": timeframe.value,
        "bar_count": len(resampled),
        "bar_content_sha256": preflight._bar_content_sha256(resampled),
        "timestamp_set_sha256": _timestamp_hash(resampled),
        "timestamps_strictly_ordered_unique": True,
        "bars_complete": True,
        "output_timestamps_are_source_starts": True,
        "bucket_retention": "complete_unique_contiguous_source_minutes_only",
        "ohlcv_aggregation_verified": True,
        "non_emitted_bucket_interpretation": "not_emitted_from_observed_source_set",
    }


def _timeframes() -> tuple[Timeframe, ...]:
    return (Timeframe.M1, Timeframe.M5, Timeframe.M10, Timeframe.H1, Timeframe.H3)


def _timestamp_hash(bars: list[Bar]) -> str:
    return "sha256:" + hashlib.sha256(
        "".join(f"{bar.start_ts.isoformat()}\n" for bar in bars).encode("utf-8")
    ).hexdigest()


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()
