from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_intraday import (
    build_kis_paper_private_intraday_freshness_snapshot,
)


def test_freshness_projection_ignores_an_unretained_marker_without_reading_raw_data(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "market-data" / "us_equities" / "kis_paper_private" / "intraday"
    index_path = cache_root / "v1" / "index.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(json.dumps(_index_document()), encoding="utf-8")

    snapshot = build_kis_paper_private_intraday_freshness_snapshot(
        cache_root=cache_root,
        repo_root=tmp_path / "repo",
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
    )

    qqq_backfill = next(
        stream
        for stream in snapshot.streams
        if stream.collection_mode == "backfill" and stream.stream == "QQQ/NAS/1m"
    )
    assert qqq_backfill.cache_status == "present"
    assert qqq_backfill.latest_collection_outcome == "committed"
    assert qqq_backfill.retained_chunk_count == 1
    assert qqq_backfill.partial_chunk_count == 0
    assert qqq_backfill.detail_code == "already_cached"

    qqq_head = next(
        stream
        for stream in snapshot.streams
        if stream.collection_mode == "head" and stream.stream == "QQQ/NAS/1m"
    )
    assert qqq_head.cache_status == "not_created"


def _index_document() -> dict[str, object]:
    targets = []
    for symbol, exchange in (("QQQ", "NAS"), ("SPY", "AMS")):
        chunks: list[dict[str, object]] = []
        if symbol == "QQQ":
            chunks = [
                {"raw_market_data_retained": True, "outcome": "committed"},
                {"raw_market_data_retained": False},
            ]
        targets.append(
            {
                "target_key": f"{symbol}/{exchange}/1m",
                "symbol": symbol,
                "exchange": exchange,
                "last_observed_at_utc": "2026-07-22T03:33:08+00:00",
                "last_reason": "already_cached" if symbol == "QQQ" else None,
                "chunks": chunks,
            }
        )
    return {
        "kind": "kis_paper_private_intraday_backfill",
        "backfill_version": "v1",
        "targets": targets,
    }
