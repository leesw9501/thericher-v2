from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.kis_paper_intraday import (
    _dataset_hash,
    inspect_kis_paper_private_intraday_local_retention,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader


def test_local_retention_uses_earliest_complete_matching_chunk_and_is_source_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    early = _chunk(
        rows=rows,
        collected_at="2026-07-22T00:30:30Z",
        suffix="early",
        input_cursor=None,
    )
    complete = _chunk(
        rows=rows,
        collected_at="2026-07-22T00:32:30Z",
        suffix="complete",
        input_cursor={"keyb": "20260722093000", "next": "1"},
    )
    cache_root, repo_root, catalog = _fixture(tmp_path, chunks=[early, complete])

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("local retention must not open a network connection")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("local retention must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)

    evidence = inspect_kis_paper_private_intraday_local_retention(
        catalog,
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
        selected_bars=catalog.bars,
    )

    assert evidence.latest_local_retained_at == datetime(2026, 7, 22, 0, 32, 30, tzinfo=UTC)
    payload = evidence.safe_payload()
    assert payload["selected_bar_count"] == 2
    assert payload["limitations"] == {
        "local_cache_retention_only": True,
        "decision_time_availability": "not_observed",
        "provider_finality": "not_observed",
    }
    assert "100" not in json.dumps(payload, sort_keys=True)


def test_local_retention_rejects_a_selected_bar_without_a_complete_retention_record(
    tmp_path: Path,
) -> None:
    early = _chunk(
        rows=_rows(),
        collected_at="2026-07-22T00:30:30Z",
        suffix="early",
        input_cursor=None,
    )
    cache_root, repo_root, catalog = _fixture(tmp_path, chunks=[early])

    with pytest.raises(ValueError, match="selected bar is incomplete"):
        inspect_kis_paper_private_intraday_local_retention(
            catalog,
            cache_root=cache_root,
            repo_root=repo_root,
            symbol="QQQ",
            exchange="NAS",
            selected_bars=catalog.bars,
        )


def test_local_retention_rejects_conflicting_retained_fingerprints(
    tmp_path: Path,
) -> None:
    first = _chunk(
        rows=_rows(),
        collected_at="2026-07-22T00:32:30Z",
        suffix="first",
        input_cursor=None,
    )
    conflicting_rows = dict(_rows())
    conflicting_rows["20260722T093000"] = _digest("changed")
    conflicting = _chunk(
        rows=conflicting_rows,
        collected_at="2026-07-22T00:33:30Z",
        suffix="conflicting",
        input_cursor={"keyb": "20260722093000", "next": "1"},
    )
    cache_root, repo_root, catalog = _fixture(tmp_path, chunks=[first, conflicting])

    with pytest.raises(ValueError, match="conflicting overlap rows"):
        inspect_kis_paper_private_intraday_local_retention(
            catalog,
            cache_root=cache_root,
            repo_root=repo_root,
            symbol="QQQ",
            exchange="NAS",
            selected_bars=catalog.bars,
        )


def test_local_retention_excludes_candidate_conflicted_chunks(
    tmp_path: Path,
) -> None:
    rows = _rows()
    good = _chunk(
        rows={"20260722T093000": rows["20260722T093000"]},
        collected_at="2026-07-22T00:32:30Z",
        suffix="good",
        input_cursor=None,
    )
    conflicted = _chunk(
        rows={"20260722T093100": rows["20260722T093100"]},
        collected_at="2026-07-22T00:33:30Z",
        suffix="candidate-conflict",
        input_cursor={"keyb": "20260722093000", "next": "1"},
        candidate_conflicted=True,
    )
    cache_root, repo_root, catalog = _fixture(tmp_path, chunks=[good, conflicted])

    with pytest.raises(ValueError, match="selected bar is incomplete"):
        inspect_kis_paper_private_intraday_local_retention(
            catalog,
            cache_root=cache_root,
            repo_root=repo_root,
            symbol="QQQ",
            exchange="NAS",
            selected_bars=catalog.bars,
        )


def test_local_retention_rejects_a_catalog_without_matching_index_lineage(
    tmp_path: Path,
) -> None:
    complete = _chunk(
        rows=_rows(),
        collected_at="2026-07-22T00:32:30Z",
        suffix="complete",
        input_cursor=None,
    )
    cache_root, repo_root, catalog = _fixture(tmp_path, chunks=[complete])
    object.__setattr__(catalog, "dataset_hash", _digest("wrong-lineage"))

    with pytest.raises(ValueError, match="catalog lineage is invalid"):
        inspect_kis_paper_private_intraday_local_retention(
            catalog,
            cache_root=cache_root,
            repo_root=repo_root,
            symbol="QQQ",
            exchange="NAS",
            selected_bars=catalog.bars,
        )


def _fixture(
    tmp_path: Path,
    *,
    chunks: list[dict[str, object]],
) -> tuple[Path, Path, object]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    index_path = cache_root / "v1" / "index.json"
    index_path.parent.mkdir(parents=True)
    index = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_intraday_backfill",
        "backfill_version": "v1",
        "generation": 1,
        "targets": [
            {
                "target_key": "QQQ/NAS/1m",
                "symbol": "QQQ",
                "exchange": "NAS",
                "next_cursor": None,
                "last_reason": None,
                "last_observed_at_utc": None,
                "chunks": chunks,
            },
            {
                "target_key": "SPY/AMS/1m",
                "symbol": "SPY",
                "exchange": "AMS",
                "next_cursor": None,
                "last_reason": None,
                "last_observed_at_utc": None,
                "chunks": [],
            },
        ],
    }
    index_bytes = json.dumps(index, sort_keys=True, separators=(",", ":")).encode("ascii")
    index_path.write_bytes(index_bytes)
    lineage = [
        {"manifest_hash": chunk["manifest_hash"], "raw_sha256": chunk["raw_sha256"]}
        for chunk in chunks
        if not _candidate_conflicted(chunk)
    ]
    bars = tuple(_bar(index) for index in range(2))
    catalog = _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.v1",
        dataset_hash=_dataset_hash(index_bytes=index_bytes, lineage=lineage),
        source_path=index_path,
        bars=bars,
    )
    return cache_root, repo_root, catalog


def _chunk(
    *,
    rows: dict[str, str],
    collected_at: str,
    suffix: str,
    input_cursor: dict[str, str] | None,
    candidate_conflicted: bool = False,
) -> dict[str, object]:
    payload = {
        "backfill_version": "v1",
        "input_cursor": input_cursor,
        "row_fingerprints": dict(sorted(rows.items())),
        "target_key": "QQQ/NAS/1m",
    }
    chunk: dict[str, object] = {
        "chunk_key": _digest(json.dumps(payload, sort_keys=True, separators=(",", ":"))),
        "outcome": "partial" if candidate_conflicted else "committed",
        "input_cursor": input_cursor,
        "output_cursor": None,
        "manifest_path": f"snapshots/{suffix}/manifest.json",
        "manifest_hash": _digest(f"manifest-{suffix}"),
        "raw_sha256": _digest(f"raw-{suffix}"),
        "raw_market_data_retained": True,
        "row_count": len(rows),
        "row_fingerprints": rows,
        "exact_overlap_rows": 0,
        "conflicting_overlap_rows": 0,
        "collected_at_utc": collected_at,
        "reason": "minute_duplicate_conflict" if candidate_conflicted else None,
        "conflict_origin": "candidate_batch" if candidate_conflicted else None,
    }
    return chunk


def _rows() -> dict[str, str]:
    return {
        "20260722T093000": _digest("first"),
        "20260722T093100": _digest("second"),
    }


def _bar(index: int) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=datetime(2026, 7, 22, 0, 30 + index, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("100"),
        complete=True,
    )


def _candidate_conflicted(chunk: dict[str, object]) -> bool:
    return (
        chunk["outcome"] == "partial"
        and chunk["reason"] == "minute_duplicate_conflict"
        and chunk["conflict_origin"] == "candidate_batch"
    )


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
