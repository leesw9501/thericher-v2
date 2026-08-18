from __future__ import annotations

import csv
import hashlib
import io
import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import firstrate_free_intraday_timeframe_mechanics as mechanics
from thericher_v2.data.local import CSV_FIELDS, bar_to_record


def test_builds_source_safe_actual_geometry_for_every_supported_timeframe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    spy_bars, spy_hash, spy_timestamp_hash = _write_canonical(
        market_data_root, symbol="SPY", count=180
    )
    _, qqq_hash, qqq_timestamp_hash = _write_canonical(
        market_data_root, symbol="QQQ", count=180
    )
    normalization_receipt = artifact_root / "data-receipts" / "normalization.json"
    _write_normalization_receipt(
        normalization_receipt,
        specs=(
            ("SPY", spy_hash, len(spy_bars), spy_timestamp_hash),
            ("QQQ", qqq_hash, 180, qqq_timestamp_hash),
        ),
    )

    def unexpected_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("timeframe mechanics must not access the network")

    monkeypatch.setattr(socket, "create_connection", unexpected_network)
    first = mechanics.build_firstrate_source_local_timeframe_mechanics(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        normalization_receipt_path=normalization_receipt,
    )
    second = mechanics.build_firstrate_source_local_timeframe_mechanics(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        normalization_receipt_path=normalization_receipt,
    )

    assert first == second
    assert first["status"] == "completed"
    assert first["manifest_path_relative_to_artifact_root"] == (
        "data-receipts/firstrate-free-intraday/"
        "firstrate-free-intraday-source-local-timeframe-mechanics-v1.json"
    )
    assert [item["symbol"] for item in first["symbols"]] == ["SPY", "QQQ"]
    for item in first["symbols"]:
        assert item["source_bar_count"] == 180
        assert item["source_timestamps_strictly_ordered_unique"] is True
        assert item["source_bars_complete"] is True
        assert [frame["timeframe"] for frame in item["timeframes"]] == [
            "1m",
            "5m",
            "10m",
            "1h",
            "3h",
        ]
        assert [frame["bar_count"] for frame in item["timeframes"]] == [180, 36, 18, 3, 1]
        assert all(frame["timestamps_strictly_ordered_unique"] for frame in item["timeframes"])
        assert all(frame["bars_complete"] for frame in item["timeframes"])
        assert all(frame["output_timestamps_are_source_starts"] for frame in item["timeframes"])
        assert all(frame["ohlcv_aggregation_verified"] for frame in item["timeframes"])
        assert all(
            frame["non_emitted_bucket_interpretation"]
            == "not_emitted_from_observed_source_set"
            for frame in item["timeframes"]
        )

    manifest_path = artifact_root / str(first["manifest_path_relative_to_artifact_root"])
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["resampling_contract"] == {
        "bucket_anchor": "utc_epoch",
        "bucket_retention": "complete_unique_contiguous_source_minutes_only",
        "reindex_or_fill": False,
        "resampled_bars_persisted": False,
        "source_timeframe": "1m",
        "target_timeframes": ["1m", "5m", "10m", "1h", "3h"],
    }
    assert manifest["safety"]["raw_market_rows_retained_in_manifest"] is False
    assert "100.5" not in manifest_text


def test_skips_only_the_incomplete_observed_source_bucket_without_gap_inference(
    tmp_path: Path,
) -> None:
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    spy_bars, spy_hash, spy_timestamp_hash = _write_canonical(
        market_data_root, symbol="SPY", count=10, excluded_offsets={2}
    )
    qqq_bars, qqq_hash, qqq_timestamp_hash = _write_canonical(
        market_data_root, symbol="QQQ", count=10, excluded_offsets={2}
    )
    normalization_receipt = artifact_root / "data-receipts" / "normalization.json"
    _write_normalization_receipt(
        normalization_receipt,
        specs=(
            ("SPY", spy_hash, len(spy_bars), spy_timestamp_hash),
            ("QQQ", qqq_hash, len(qqq_bars), qqq_timestamp_hash),
        ),
    )

    result = mechanics.build_firstrate_source_local_timeframe_mechanics(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        normalization_receipt_path=normalization_receipt,
    )

    spy_timeframes = result["symbols"][0]["timeframes"]
    assert [frame["bar_count"] for frame in spy_timeframes] == [9, 1, 0, 0, 0]
    assert all(
        frame["non_emitted_bucket_interpretation"]
        == "not_emitted_from_observed_source_set"
        for frame in spy_timeframes
    )


def test_rejects_a_canonical_hash_mismatch_before_writing_a_manifest(tmp_path: Path) -> None:
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    spy_bars, spy_hash, spy_timestamp_hash = _write_canonical(
        market_data_root, symbol="SPY", count=10
    )
    qqq_bars, qqq_hash, qqq_timestamp_hash = _write_canonical(
        market_data_root, symbol="QQQ", count=10
    )
    normalization_receipt = artifact_root / "data-receipts" / "normalization.json"
    _write_normalization_receipt(
        normalization_receipt,
        specs=(
            ("SPY", "sha256:" + "0" * 64, len(spy_bars), spy_timestamp_hash),
            ("QQQ", qqq_hash, len(qqq_bars), qqq_timestamp_hash),
        ),
    )

    with pytest.raises(ValueError, match="hash does not match"):
        mechanics.build_firstrate_source_local_timeframe_mechanics(
            market_data_root=market_data_root,
            artifact_root=artifact_root,
            normalization_receipt_path=normalization_receipt,
        )

    assert not (
        artifact_root
        / "data-receipts/firstrate-free-intraday/"
        "firstrate-free-intraday-source-local-timeframe-mechanics-v1.json"
    ).exists()


def test_timeframe_payload_is_deterministic_for_reverse_input_order() -> None:
    bars = _bars("SPY", count=180)

    forward = [
        mechanics._timeframe_payload(bars, timeframe) for timeframe in _timeframes()
    ]
    reverse = [
        mechanics._timeframe_payload(list(reversed(bars)), timeframe)
        for timeframe in _timeframes()
    ]

    assert forward == reverse


def _write_canonical(
    market_data_root: Path,
    *,
    symbol: str,
    count: int,
    excluded_offsets: set[int] | None = None,
) -> tuple[list[Bar], str, str]:
    bars = _bars(symbol, count=count, excluded_offsets=excluded_offsets)
    path = market_data_root / "us_equities/firstrate_free_intraday/canonical" / f"{symbol}_1m.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(bar_to_record(bar) for bar in bars)
    payload = buffer.getvalue().encode("utf-8")
    path.write_bytes(payload)
    return (
        bars,
        "sha256:" + hashlib.sha256(payload).hexdigest(),
        _timestamp_set_sha256(bar.start_ts for bar in bars),
    )


def _write_normalization_receipt(
    path: Path,
    *,
    specs: tuple[tuple[str, str, int, str], tuple[str, str, int, str]],
) -> None:
    payload = {
        "schema_version": "firstrate-free-intraday-normalization-receipt-v1",
        "status": "completed",
        "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
        "normalizations": [
            {
                "symbol": symbol,
                "market": "US",
                "timeframe": "1m",
                "canonical_market_data_relative_path": (
                    f"us_equities/firstrate_free_intraday/canonical/{symbol}_1m.csv"
                ),
                "canonical_sha256": canonical_sha256,
                "bar_count": bar_count,
                "emitted_timestamp_set_sha256": timestamp_set_sha256,
                "timestamp_set_equal": True,
            }
            for symbol, canonical_sha256, bar_count, timestamp_set_sha256 in specs
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _bars(
    symbol: str,
    *,
    count: int,
    excluded_offsets: set[int] | None = None,
) -> list[Bar]:
    excluded = excluded_offsets or set()
    start = datetime(2024, 3, 11, 12, 0, tzinfo=UTC)
    return [
        Bar(
            symbol=symbol,
            market="US",
            timeframe=Timeframe.M1,
            start_ts=start + timedelta(minutes=index),
            open=Decimal("100") + index,
            high=Decimal("101") + index,
            low=Decimal("99") + index,
            close=Decimal("100.5") + index,
            volume=Decimal("10") + index,
            complete=True,
        )
        for index in range(count)
        if index not in excluded
    ]


def _timeframes() -> tuple[Timeframe, ...]:
    return (Timeframe.M1, Timeframe.M5, Timeframe.M10, Timeframe.H1, Timeframe.H3)


def _timestamp_set_sha256(timestamps: object) -> str:
    payload = "".join(f"{timestamp.isoformat()}\n" for timestamp in timestamps).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
