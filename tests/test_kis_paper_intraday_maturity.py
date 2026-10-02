from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from test_kis_private_intraday_backfill import _MinuteClient, _page, _rows
from thericher_v2.data.kis_paper_intraday import (
    _dataset_hash,
    inspect_kis_paper_private_intraday_local_retention,
    load_verified_kis_paper_private_intraday_catalog,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataError,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    run_kis_paper_private_intraday_backfill_cycle,
)


def _collect(
    cache: Path, repo: Path, rows: tuple[KisPaperMinuteRawBar, ...], at: datetime
) -> None:
    result = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=rows, next_cursor=None),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache,
        repo_root=repo,
        code_revision="git:synthetic-maturity",
        pages_per_target=1,
        resume_cursor=False,
        observed_at=at,
        sleeper=lambda _: None,
        monotonic_clock=lambda: 0.0,
    )
    assert result[0].status == "collected"


def _load(cache: Path, repo: Path):
    return load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache, repo_root=repo, symbol="QQQ", exchange="NAS"
    )


def _bytes(cache: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(cache): path.read_bytes()
        for path in cache.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("reverse", [False, True], ids=["forming-first", "mature-first"])
def test_exact_retained_overlap_is_complete_in_either_chunk_order(
    tmp_path: Path, reverse: bool
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    cache = tmp_path / "cache"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=3)
    observations = [
        (rows[:2], datetime(2026, 7, 22, 0, 31, 30, tzinfo=UTC)),
        (rows[1:], datetime(2026, 7, 22, 0, 32, 30, tzinfo=UTC)),
    ]
    for page, at in reversed(observations) if reverse else observations:
        _collect(cache, repo, page, at)
    before = _bytes(cache)
    index_bytes = before[Path("v1/index.json")]
    chunks = json.loads(index_bytes)["targets"][0]["chunks"]
    assert len(chunks) == 2
    assert all(chunk["raw_market_data_retained"] is True for chunk in chunks)

    catalog = _load(cache, repo)

    assert [bar.complete for bar in catalog.bars] == [True, True, False]
    overlap = catalog.bars[1]
    assert (overlap.open, overlap.high, overlap.low, overlap.close, overlap.volume) == (
        rows[1].open, rows[1].high, rows[1].low, rows[1].last, rows[1].volume
    )
    assert catalog.dataset_hash == _dataset_hash(
        index_bytes=index_bytes,
        lineage=[
            {"manifest_hash": chunk["manifest_hash"], "raw_sha256": chunk["raw_sha256"]}
            for chunk in chunks
        ],
    )
    assert _bytes(cache) == before


def test_two_forming_retained_overlaps_do_not_become_complete(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    cache = tmp_path / "cache"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 29), count=2)
    _collect(cache, repo, (rows[1],), datetime(2026, 7, 22, 0, 30, 10, tzinfo=UTC))
    _collect(cache, repo, rows, datetime(2026, 7, 22, 0, 30, 50, tzinfo=UTC))
    before = _bytes(cache)

    assert [bar.complete for bar in _load(cache, repo).bars] == [True, False]
    assert _bytes(cache) == before


def test_conflicting_retained_fingerprint_is_not_maturity_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    cache = tmp_path / "cache"
    other = tmp_path / "other"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=3)
    _collect(cache, repo, rows[:2], datetime(2026, 7, 22, 0, 31, 30, tzinfo=UTC))
    changed = replace(rows[1], volume=rows[1].volume + Decimal("1"))
    _collect(other, repo, (changed, rows[2]), datetime(2026, 7, 22, 0, 32, 30, tzinfo=UTC))
    # Assemble an inconsistent synthetic index from independently retained snapshots;
    # neither manifest, raw bytes nor collection timestamp is rewritten.
    index_path = cache / "v1/index.json"
    index = json.loads(index_path.read_bytes())
    other_index = json.loads((other / "v1/index.json").read_bytes())
    chunk = other_index["targets"][0]["chunks"][0]
    snapshot = Path(chunk["manifest_path"]).parent
    shutil.copytree(other / "v1" / snapshot, cache / "v1" / snapshot)
    index["targets"][0]["chunks"].append(chunk)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    before = _bytes(cache)

    with pytest.raises(ValueError, match="conflicting overlap rows"):
        _load(cache, repo)
    assert _bytes(cache) == before


def test_promoted_bar_keeps_earliest_complete_local_retention(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    cache = tmp_path / "cache"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=4)
    _collect(cache, repo, rows[:2], datetime(2026, 7, 22, 0, 31, 30, tzinfo=UTC))
    earliest = datetime(2026, 7, 22, 0, 32, 30, tzinfo=UTC)
    _collect(cache, repo, rows[1:3], earliest)
    _collect(cache, repo, rows[1:], datetime(2026, 7, 22, 0, 34, 30, tzinfo=UTC))
    before = _bytes(cache)
    catalog = _load(cache, repo)

    evidence = inspect_kis_paper_private_intraday_local_retention(
        catalog,
        cache_root=cache,
        repo_root=repo,
        symbol="QQQ",
        exchange="NAS",
        selected_bars=(catalog.bars[1],),
    )

    assert evidence.latest_local_retained_at == earliest
    assert evidence.index_metadata_sha256 == (
        "sha256:" + hashlib.sha256(before[Path("v1/index.json")]).hexdigest()
    )
    assert evidence.safe_payload()["limitations"] == {
        "local_cache_retention_only": True,
        "decision_time_availability": "not_observed",
        "provider_finality": "not_observed",
    }
    assert _bytes(cache) == before
