from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.execution.kis_market_data import KisPaperDailyRawRow
from thericher_v2.execution.kis_paper_daily_spy_head import (
    collect_kis_paper_daily_spy_head_once,
    load_verified_kis_paper_daily_spy_head,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


@dataclass
class FakeDailyClient:
    rows: tuple[KisPaperDailyRawRow, ...]
    query: object | None = None

    def fetch_daily_raw_page(self, query):
        self.query = query
        return type("Page", (), {"rows": self.rows})()


def test_head_excludes_current_exchange_date_and_deduplicates_identical_snapshot(
    tmp_path: Path,
) -> None:
    client = FakeDailyClient(rows=(_row("20260720"), _row("20260721"), _row("20260722")))
    root = tmp_path / "daily-head"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    first = collect_kis_paper_daily_spy_head_once(
        client, cache_root=root, repository_root=repo_root, observed_at=NOW
    )
    second = collect_kis_paper_daily_spy_head_once(
        client, cache_root=root, repository_root=repo_root, observed_at=NOW
    )

    assert first.status == "collected"
    assert second.status == "unchanged"
    assert first.snapshot is not None
    assert first.snapshot.last_session == date(2026, 7, 21)
    assert tuple(bar.start_ts.date() for bar in first.snapshot.bars) == (
        date(2026, 7, 20),
        date(2026, 7, 21),
    )
    assert client.query.symbol == "SPY"
    assert client.query.exchange == "AMS"
    assert client.query.by_date == "20260722"
    verified = load_verified_kis_paper_daily_spy_head(cache_root=root, repository_root=repo_root)
    assert verified.dataset_hash == first.snapshot.dataset_hash
    manifest = json.loads(first.snapshot.manifest_path.read_text(encoding="utf-8"))
    raw_path = first.snapshot.manifest_path.parent / manifest["files"]["raw_daily_rows"]["path"]
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        retained = handle.read()
    assert "2026-07-22" not in retained
    assert "2026-07-21" in retained
    assert len(tuple(root.glob("snapshot=*/manifest.json"))) == 1


def test_head_does_not_publish_when_latest_prior_session_is_missing(tmp_path: Path) -> None:
    client = FakeDailyClient(rows=(_row("20260720"), _row("20260722")))
    root = tmp_path / "daily-head"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = collect_kis_paper_daily_spy_head_once(
        client, cache_root=root, repository_root=repo_root, observed_at=NOW
    )

    assert result.status == "unavailable"
    assert result.reason == "insufficient_completed_rows"
    assert not (root / "index.json").exists()


def _row(session: str) -> KisPaperDailyRawRow:
    return KisPaperDailyRawRow(
        xymd=session,
        open="100",
        high="102",
        low="99",
        clos="101",
        tvol="1000",
    )
