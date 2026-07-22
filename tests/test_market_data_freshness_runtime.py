from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.data.market_data_freshness_runtime import (
    MarketDataFreshnessRuntimeError,
    MarketDataFreshnessRuntimeSnapshot,
    MarketDataFreshnessStream,
    read_market_data_freshness_runtime,
    write_market_data_freshness_runtime,
)


def test_market_data_freshness_runtime_round_trips_only_sanitized_metadata(tmp_path: Path) -> None:
    now = datetime(2026, 7, 22, 5, 0, tzinfo=UTC)
    path = tmp_path / "kis_paper_intraday_freshness.json"
    snapshot = MarketDataFreshnessRuntimeSnapshot(
        observed_at=now,
        expires_at=now + timedelta(hours=1),
        streams=(
            MarketDataFreshnessStream(
                collection_mode="backfill",
                stream="QQQ/NAS/1m",
                cache_status="present",
                last_observed_at_utc=now,
                latest_collection_outcome="partial",
                retained_chunk_count=14,
                partial_chunk_count=3,
                detail_code="minute_cursor_invalid",
            ),
            MarketDataFreshnessStream(
                collection_mode="head",
                stream="QQQ/NAS/1m",
                cache_status="not_created",
                last_observed_at_utc=None,
                latest_collection_outcome="unknown",
                retained_chunk_count=0,
                partial_chunk_count=0,
            ),
        ),
    )

    write_market_data_freshness_runtime(snapshot, path)
    result = read_market_data_freshness_runtime(path, now=now + timedelta(minutes=1))

    assert result.status == "available"
    assert result.snapshot == snapshot
    payload = json.loads(path.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, sort_keys=True)
    for forbidden in ("manifest", "raw_sha256", "600.12", "12345678", "D:\\\\"):
        assert forbidden not in rendered


def test_market_data_freshness_runtime_rejects_extra_or_malformed_fields(tmp_path: Path) -> None:
    path = tmp_path / "kis_paper_intraday_freshness.json"
    path.write_text('{"raw_rows":["must-not-render"]}', encoding="utf-8")

    result = read_market_data_freshness_runtime(path)

    assert result.status == "unavailable"


def test_market_data_freshness_runtime_rejects_an_incompatible_schema_version() -> None:
    now = datetime(2026, 7, 22, 5, 0, tzinfo=UTC)

    with pytest.raises(MarketDataFreshnessRuntimeError, match="freshness_schema_version_invalid"):
        MarketDataFreshnessRuntimeSnapshot(
            observed_at=now,
            expires_at=now + timedelta(hours=1),
            streams=(
                MarketDataFreshnessStream(
                    collection_mode="backfill",
                    stream="QQQ/NAS/1m",
                    cache_status="present",
                    last_observed_at_utc=now,
                    latest_collection_outcome="committed",
                    retained_chunk_count=1,
                    partial_chunk_count=0,
                ),
            ),
            schema_version=999,
        )
