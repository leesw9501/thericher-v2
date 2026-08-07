from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_paper_intraday_index_metadata as intraday_index_metadata
import thericher_v2.execution.kis_private_intraday_backfill as private_intraday_backfill
from thericher_v2.contracts import Timeframe
from thericher_v2.data.kis_paper_intraday import (
    inspect_kis_paper_private_intraday_local_retention,
    load_verified_kis_paper_private_intraday_catalog,
    resample_verified_kis_paper_private_intraday_catalog,
)
from thericher_v2.data.kis_paper_intraday_runtime_window import (
    attest_kis_paper_intraday_runtime_window_local_availability,
    select_kis_paper_intraday_runtime_window,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.data.resample import SessionWindow
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
    run_kis_paper_private_intraday_backfill_cycle,
)


class _MinuteClient:
    def __init__(self, responses: list[KisPaperMinutePage | BaseException]) -> None:
        self.responses = list(responses)
        self.queries: list[KisPaperMinuteQuery] = []

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: object | None = None,
    ) -> KisPaperMinutePage:
        self.queries.append(query)
        if callable(before_request):
            before_request()
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def test_writer_index_validation_delegates_to_shared_contract_and_accepts_legacy_chunk_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    _collect_one_qqq_chunk(cache_root=cache_root, repo_root=repo_root)
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    chunk = qqq["chunks"][0]
    assert isinstance(chunk, dict)
    chunk["chunk_key"] = _legacy_chunk_key(
        target_key="QQQ/NAS/1m",
        input_cursor=chunk["input_cursor"],
    )

    calls: list[tuple[tuple[str, str], ...]] = []
    original = intraday_index_metadata.validate_kis_paper_private_intraday_v1_index_metadata

    def record_shared_contract(
        document: Mapping[str, object],
        *,
        expected_targets: tuple[tuple[str, str], ...],
    ) -> object:
        calls.append(expected_targets)
        return original(document, expected_targets=expected_targets)

    monkeypatch.setattr(
        intraday_index_metadata,
        "validate_kis_paper_private_intraday_v1_index_metadata",
        record_shared_contract,
    )

    private_intraday_backfill._validate_index(index)

    assert calls == [(("QQQ", "NAS"), ("SPY", "AMS"))]


def test_writer_rejects_malformed_index_before_any_client_request(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    _collect_one_qqq_chunk(cache_root=cache_root, repo_root=repo_root)
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    chunk = qqq["chunks"][0]
    assert isinstance(chunk, dict)
    rows = chunk["row_fingerprints"]
    assert isinstance(rows, dict)
    rows[next(iter(rows))] = "not-a-sha256"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    client = _MinuteClient([])

    with pytest.raises(ValueError, match="private intraday index is invalid"):
        run_kis_paper_private_intraday_backfill_cycle(
            client=client,
            cache_root=cache_root,
            repo_root=repo_root,
            code_revision="git:test",
            pages_per_target=1,
            observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
            sleeper=lambda _seconds: None,
            monotonic_clock=lambda: 0.0,
        )

    assert client.queries == []


def test_hydrates_terminal_cursor_without_another_minute_request(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    first = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor=None,
            ),
            _page(
                symbol="SPY",
                exchange="AMS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor=None,
            ),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=first,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for target in index["targets"]:
        target["last_reason"] = None
    index_path.write_text(json.dumps(index), encoding="utf-8")
    second = _MinuteClient([])

    results = run_kis_paper_private_intraday_backfill_cycle(
        client=second,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert second.queries == []
    assert [(result.target_key, result.status, result.reason) for result in results] == [
        ("QQQ/NAS/1m", "source_exhausted", "source_exhausted"),
        ("SPY/AMS/1m", "source_exhausted", "source_exhausted"),
    ]


def test_cycle_writes_only_external_raw_cache_and_loader_resamples_all_timeframes(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    qqq_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=180)
    first_page = _page(
        symbol="QQQ",
        exchange="NAS",
        rows=qqq_rows[60:],
        next_cursor="1",
    )
    second_page = _page(
        symbol="QQQ",
        exchange="NAS",
        rows=(qqq_rows[60], *qqq_rows[:60]),
        next_cursor=None,
    )
    client = _MinuteClient(
        [
            first_page,
            second_page,
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )

    results = run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=2,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert [(result.target_key, result.status, result.row_count) for result in results] == [
        ("QQQ/NAS/1m", "collected", 180),
        ("SPY/AMS/1m", "rejected", 0),
    ]
    assert results[0].exact_overlap_rows == 1
    assert not any(repo_root.iterdir())
    assert [query.exchange for query in client.queries] == ["NAS", "NAS", "AMS"]
    assert client.queries[1].continuation_key == "20260722102900"

    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
    )
    assert len(catalog.bars) == 180
    assert catalog.bars[0].start_ts == datetime(2026, 7, 22, 0, 30, tzinfo=UTC)
    assert catalog.bars[-1].start_ts == datetime(2026, 7, 22, 3, 29, tzinfo=UTC)
    assert all(bar.complete for bar in catalog.bars)

    session = SessionWindow(
        open_ts=datetime(2026, 7, 22, 0, 30, tzinfo=UTC),
        close_ts=datetime(2026, 7, 22, 3, 30, tzinfo=UTC),
    )
    assert len(
        resample_verified_kis_paper_private_intraday_catalog(
            catalog, timeframe=Timeframe.M1, session=session
        ).bars
    ) == 180
    assert len(
        resample_verified_kis_paper_private_intraday_catalog(
            catalog, timeframe=Timeframe.M5, session=session
        ).bars
    ) == 36
    assert len(
        resample_verified_kis_paper_private_intraday_catalog(
            catalog, timeframe=Timeframe.M10, session=session
        ).bars
    ) == 18
    assert len(
        resample_verified_kis_paper_private_intraday_catalog(
            catalog, timeframe=Timeframe.H1, session=session
        ).bars
    ) == 3
    assert len(
        resample_verified_kis_paper_private_intraday_catalog(
            catalog, timeframe=Timeframe.H3, session=session
        ).bars
    ) == 1


def test_local_retention_binds_a_catalog_from_the_verified_loader(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    _collect_one_qqq_chunk(cache_root=cache_root, repo_root=repo_root)

    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
    )
    retention = inspect_kis_paper_private_intraday_local_retention(
        catalog,
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
        selected_bars=catalog.bars,
    )

    assert retention.latest_local_retained_at == datetime(2026, 7, 22, 5, 0, tzinfo=UTC)
    assert retention.selected_bar_count == len(catalog.bars)


def test_runtime_window_local_availability_binds_a_ready_window_to_cache_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    observed_at = datetime(2026, 7, 22, 15, 31, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 22, 30), count=120),
                next_cursor=None,
            ),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=observed_at,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
    )
    window = select_kis_paper_intraday_runtime_window(
        catalog,
        as_of=observed_at,
        max_age=timedelta(minutes=2),
    )
    before_retention = select_kis_paper_intraday_runtime_window(
        catalog,
        as_of=observed_at - timedelta(seconds=1),
        max_age=timedelta(minutes=2),
    )
    assert window.status == "ready"
    assert before_retention.status == "ready"

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime local availability must not open a network connection")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime local availability must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)

    evidence = attest_kis_paper_intraday_runtime_window_local_availability(
        catalog,
        runtime_window=window,
        cache_root=cache_root,
        repo_root=repo_root,
        decided_at=observed_at,
    )
    late_evidence = attest_kis_paper_intraday_runtime_window_local_availability(
        catalog,
        runtime_window=before_retention,
        cache_root=cache_root,
        repo_root=repo_root,
        decided_at=observed_at - timedelta(seconds=1),
    )

    assert evidence.input_manifest_ref == window.input_manifest_ref
    assert evidence.source_catalog_hash == catalog.dataset_hash
    assert evidence.selected_bar_count == 90
    assert evidence.latest_local_retained_at == observed_at
    assert evidence.local_input_available_by_decision is True
    assert late_evidence.local_input_available_by_decision is False
    with pytest.raises(
        ValueError,
        match="runtime local availability decision flag is inconsistent",
    ):
        replace(evidence, local_input_available_by_decision=False)
    payload = evidence.safe_payload()
    assert payload["limitations"] == {
        "local_cache_retention_only": True,
        "provider_decision_time_availability": "not_observed",
        "provider_finality": "not_observed",
    }
    serialized = json.dumps(payload, sort_keys=True)
    assert str(catalog.source_path) not in serialized
    assert '"open"' not in serialized

    with pytest.raises(ValueError, match="decided_at must not precede runtime window as_of"):
        attest_kis_paper_intraday_runtime_window_local_availability(
            catalog,
            runtime_window=window,
            cache_root=cache_root,
            repo_root=repo_root,
            decided_at=observed_at - timedelta(microseconds=1),
        )

    other_catalog = _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash="sha256:" + "0" * 64,
        source_path=catalog.source_path,
        bars=catalog.bars,
    )
    other_window = select_kis_paper_intraday_runtime_window(
        other_catalog,
        as_of=observed_at,
        max_age=timedelta(minutes=2),
    )
    with pytest.raises(ValueError, match="runtime window catalog lineage is invalid"):
        attest_kis_paper_intraday_runtime_window_local_availability(
            catalog,
            runtime_window=other_window,
            cache_root=cache_root,
            repo_root=repo_root,
            decided_at=observed_at,
        )


def test_failed_unretained_attempt_does_not_latch_later_collection(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    failed = _MinuteClient(
        [
            KisPaperMarketDataError("minute_response_empty"),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )

    first_results = run_kis_paper_private_intraday_backfill_cycle(
        client=failed,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    assert all(result.status == "rejected" for result in first_results)
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert all(target["chunks"] == [] for target in index["targets"])

    second = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor=None,
            ),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    second_results = run_kis_paper_private_intraday_backfill_cycle(
        client=second,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert second_results[0].status == "collected"
    assert second_results[0].row_count == 2
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["chunks"][0]["raw_market_data_retained"] is True


def test_historical_unretained_marker_never_blocks_a_fresh_intraday_collection(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    failed = _MinuteClient(
        [
            KisPaperMarketDataError("minute_response_empty"),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=failed,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    qqq["chunks"].append(
        {
            "raw_market_data_retained": False,
            "historical_note": "one-shot observation only",
        }
    )
    index_path.write_text(json.dumps(index), encoding="utf-8")

    fresh = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor=None,
            ),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    results = run_kis_paper_private_intraday_backfill_cycle(
        client=fresh,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert results[0].status == "collected"
    assert fresh.queries[0].continuation_next is None
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert [chunk["raw_market_data_retained"] for chunk in qqq["chunks"]] == [False, True]
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
    )
    assert len(catalog.bars) == 2


def test_invalid_second_page_does_not_leak_rows_into_a_partial_snapshot(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    first_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    stalled_row = KisPaperMinuteRawBar(
        exchange_date="20260722",
        exchange_time="093000",
        korea_date="20260722",
        korea_time="092700",
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        last=Decimal("100.5"),
        volume=Decimal("100"),
    )
    client = _MinuteClient(
        [
            _page(symbol="QQQ", exchange="NAS", rows=first_rows, next_cursor="1"),
            _page(symbol="QQQ", exchange="NAS", rows=(stalled_row,), next_cursor="1"),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )

    results = run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=2,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert results[0].status == "partial"
    assert results[0].reason == "minute_cursor_stalled"
    assert results[0].row_count == len(first_rows)
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
    )
    assert len(catalog.bars) == len(first_rows)


def test_snapshots_symlink_is_rejected_before_raw_data_is_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    snapshots_root = (
        cache_root
        / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
        / "snapshots"
    )
    snapshots_root.parent.mkdir(parents=True)
    try:
        snapshots_root.symlink_to(repo_root, target_is_directory=True)
    except OSError:
        snapshots_root.mkdir()
        original_is_symlink = Path.is_symlink

        def marked_as_symlink(path: Path) -> bool:
            return path == snapshots_root or original_is_symlink(path)

        monkeypatch.setattr(Path, "is_symlink", marked_as_symlink)

    with pytest.raises(ValueError, match="snapshot path"):
        run_kis_paper_private_intraday_backfill_cycle(
            client=_MinuteClient(
                [
                    _page(
                        symbol="QQQ",
                        exchange="NAS",
                        rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                        next_cursor=None,
                    )
                ]
            ),
            cache_root=cache_root,
            repo_root=repo_root,
            code_revision="git:test",
            pages_per_target=1,
            observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
            sleeper=lambda _seconds: None,
            monotonic_clock=lambda: 0.0,
        )

    assert list(repo_root.iterdir()) == []


def test_head_retained_conflict_without_quarantine_preserves_snapshot_and_reports_origin(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    first_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    initial = _MinuteClient(
        [
            _page(symbol="QQQ", exchange="NAS", rows=first_rows, next_cursor="1"),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=initial,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    initial_index = json.loads(index_path.read_text(encoding="utf-8"))
    initial_qqq = next(
        target for target in initial_index["targets"] if target["target_key"] == "QQQ/NAS/1m"
    )
    original_chunk = initial_qqq["chunks"][0]
    original_manifest = index_path.parent / original_chunk["manifest_path"]
    original_manifest_bytes = original_manifest.read_bytes()
    original_raw = original_manifest.parent / "raw" / "ohlcv_1m.csv.gz"
    original_raw_bytes = original_raw.read_bytes()
    original_snapshot_names = sorted(
        path.name for path in original_manifest.parent.parent.iterdir()
    )
    changed = KisPaperMinuteRawBar(
        exchange_date=first_rows[0].exchange_date,
        exchange_time=first_rows[0].exchange_time,
        korea_date=first_rows[0].korea_date,
        korea_time=first_rows[0].korea_time,
        open=first_rows[0].open,
        high=first_rows[0].high + Decimal("1"),
        low=first_rows[0].low,
        last=first_rows[0].last + Decimal("1"),
        volume=first_rows[0].volume,
    )
    conflicting = _MinuteClient(
        [
            _page(symbol="QQQ", exchange="NAS", rows=(changed,), next_cursor=None),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )

    results = run_kis_paper_private_intraday_backfill_cycle(
        client=conflicting,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=False,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert results[0].status == "rejected"
    assert results[0].reason == "minute_duplicate_conflict"
    assert results[0].conflict_origin == "retained_cache"
    assert results[0].retained_head_conflict_disposition == "preserved"
    assert original_manifest.exists()
    assert original_manifest.read_bytes() == original_manifest_bytes
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["chunks"] == [original_chunk]
    assert qqq["last_conflict_origin"] == "retained_cache"
    assert original_raw.read_bytes() == original_raw_bytes
    assert sorted(path.name for path in original_manifest.parent.parent.iterdir()) == (
        original_snapshot_names
    )

    repeated = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=(changed,), next_cursor=None),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=False,
        observed_at=datetime(2026, 7, 22, 5, 10, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert repeated[0].status == "rejected"
    assert repeated[0].reason == "minute_duplicate_conflict"
    assert repeated[0].conflict_origin == "retained_cache"
    assert repeated[0].retained_head_conflict_disposition == "preserved"
    assert original_manifest.read_bytes() == original_manifest_bytes
    assert original_raw.read_bytes() == original_raw_bytes
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["chunks"] == [original_chunk]
    assert qqq["next_cursor"] is None
    assert qqq["last_conflict_origin"] == "retained_cache"
    assert sorted(path.name for path in original_manifest.parent.parent.iterdir()) == (
        original_snapshot_names
    )


def test_head_conflict_quarantines_old_snapshot_before_a_fresh_capture(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    original_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    spy_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=original_rows, next_cursor=None),
                _page(symbol="SPY", exchange="AMS", rows=spy_rows, next_cursor=None),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    initial_index = json.loads(index_path.read_text(encoding="utf-8"))
    initial_qqq = next(
        target for target in initial_index["targets"] if target["target_key"] == "QQQ/NAS/1m"
    )
    original_chunk = initial_qqq["chunks"][0]
    assert original_chunk["collection_scope"] == "head"
    original_manifest = index_path.parent / original_chunk["manifest_path"]
    original_manifest_bytes = original_manifest.read_bytes()
    changed = KisPaperMinuteRawBar(
        exchange_date=original_rows[0].exchange_date,
        exchange_time=original_rows[0].exchange_time,
        korea_date=original_rows[0].korea_date,
        korea_time=original_rows[0].korea_time,
        open=original_rows[0].open,
        high=original_rows[0].high + Decimal("1"),
        low=original_rows[0].low,
        last=original_rows[0].last + Decimal("1"),
        volume=original_rows[0].volume,
    )
    fresh_rows = (changed, original_rows[1])

    quarantined = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=fresh_rows, next_cursor=None),
                _page(symbol="SPY", exchange="AMS", rows=spy_rows, next_cursor=None),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert [(item.target_key, item.status) for item in quarantined] == [
        ("QQQ/NAS/1m", "rejected"),
        ("SPY/AMS/1m", "recovered"),
    ]
    assert quarantined[0].conflict_origin == "retained_cache"
    assert quarantined[0].retained_head_conflict_disposition == "quarantined"
    assert quarantined[1].conflict_origin is None
    assert quarantined[1].retained_head_conflict_disposition == "not_applicable"
    assert original_manifest.exists()
    assert original_manifest.read_bytes() == original_manifest_bytes
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["chunks"] == [
        {
            "historical_note": "quarantined_head_retained_cache_conflict",
            "quarantined_chunk_key": original_chunk["chunk_key"],
            "quarantined_manifest_hash": original_chunk["manifest_hash"],
            "quarantined_raw_sha256": original_chunk["raw_sha256"],
            "raw_market_data_retained": False,
        }
    ]

    retried = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=fresh_rows, next_cursor=None),
                _page(symbol="SPY", exchange="AMS", rows=spy_rows, next_cursor=None),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        observed_at=datetime(2026, 7, 22, 5, 10, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert [(item.target_key, item.status) for item in retried] == [
        ("QQQ/NAS/1m", "collected"),
        ("SPY/AMS/1m", "recovered"),
    ]
    assert retried[0].conflict_origin is None
    assert retried[0].retained_head_conflict_disposition == "not_applicable"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert [chunk["raw_market_data_retained"] for chunk in qqq["chunks"]] == [False, True]


def test_malformed_head_quarantine_marker_fails_closed_before_orphan_recovery(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=rows, next_cursor=None),
                _page(symbol="SPY", exchange="AMS", rows=rows, next_cursor=None),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    original_chunk = qqq["chunks"][0]
    original_manifest = index_path.parent / original_chunk["manifest_path"]
    qqq["chunks"] = [
        {
            "raw_market_data_retained": False,
            "historical_note": "quarantined_head_retained_cache_conflict",
            "quarantined_chunk_key": original_chunk["chunk_key"],
            "quarantined_manifest_hash": original_chunk["manifest_hash"],
        }
    ]
    index_path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ValueError, match="private intraday index is invalid"):
        run_kis_paper_private_intraday_backfill_cycle(
            client=_MinuteClient([]),
            cache_root=cache_root,
            repo_root=repo_root,
            code_revision="git:test",
            pages_per_target=1,
            resume_cursor=False,
            quarantine_retained_head_conflicts=True,
            observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
            sleeper=lambda _seconds: None,
            monotonic_clock=lambda: 0.0,
        )

    assert original_manifest.exists()


def test_cursor_backed_historical_chunk_cannot_be_quarantined_by_head_option(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    original_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=original_rows, next_cursor="1"),
                _page(symbol="SPY", exchange="AMS", rows=original_rows, next_cursor=None),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=True,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    changed = KisPaperMinuteRawBar(
        exchange_date=original_rows[0].exchange_date,
        exchange_time=original_rows[0].exchange_time,
        korea_date=original_rows[0].korea_date,
        korea_time=original_rows[0].korea_time,
        open=original_rows[0].open,
        high=original_rows[0].high + Decimal("1"),
        low=original_rows[0].low,
        last=original_rows[0].last + Decimal("1"),
        volume=original_rows[0].volume,
    )
    results = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(
                    symbol="QQQ",
                    exchange="NAS",
                    rows=(changed, original_rows[1]),
                    next_cursor=None,
                ),
                _page(symbol="SPY", exchange="AMS", rows=original_rows, next_cursor=None),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert results[0].status == "rejected"
    assert results[0].reason == "minute_duplicate_conflict"
    assert results[0].conflict_origin == "retained_cache"
    assert results[0].retained_head_conflict_disposition == "preserved"
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert len(qqq["chunks"]) == 1
    assert qqq["chunks"][0]["raw_market_data_retained"] is True
    assert qqq["chunks"][0]["collection_scope"] == "historical"
    assert qqq["chunks"][0]["output_cursor"] is not None


def test_partial_head_snapshot_cannot_be_quarantined_by_head_option(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    original_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    initial = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=original_rows, next_cursor="1"),
                KisPaperMarketDataError("minute_response_empty"),
                _page(symbol="SPY", exchange="AMS", rows=original_rows, next_cursor=None),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=2,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert initial[0].status == "partial"
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    initial_index = json.loads(index_path.read_text(encoding="utf-8"))
    initial_qqq = next(
        target for target in initial_index["targets"] if target["target_key"] == "QQQ/NAS/1m"
    )
    original_chunk = initial_qqq["chunks"][0]
    original_manifest = index_path.parent / original_chunk["manifest_path"]
    original_manifest_bytes = original_manifest.read_bytes()
    changed = KisPaperMinuteRawBar(
        exchange_date=original_rows[0].exchange_date,
        exchange_time=original_rows[0].exchange_time,
        korea_date=original_rows[0].korea_date,
        korea_time=original_rows[0].korea_time,
        open=original_rows[0].open,
        high=original_rows[0].high + Decimal("1"),
        low=original_rows[0].low,
        last=original_rows[0].last + Decimal("1"),
        volume=original_rows[0].volume,
    )

    results = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(
                    symbol="QQQ",
                    exchange="NAS",
                    rows=(changed, original_rows[1]),
                    next_cursor=None,
                ),
                _page(symbol="SPY", exchange="AMS", rows=original_rows, next_cursor=None),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert results[0].status == "rejected"
    assert results[0].reason == "minute_duplicate_conflict"
    assert results[0].conflict_origin == "retained_cache"
    assert results[0].retained_head_conflict_disposition == "preserved"
    assert original_manifest.read_bytes() == original_manifest_bytes
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["chunks"] == [original_chunk]
    assert qqq["next_cursor"] is None


def test_quarantined_head_marker_requires_exact_snapshot_identity() -> None:
    marker = {
        "raw_market_data_retained": False,
        "historical_note": "quarantined_head_retained_cache_conflict",
        "quarantined_chunk_key": "sha256:" + "a" * 64,
        "quarantined_manifest_hash": "sha256:" + "b" * 64,
        "quarantined_raw_sha256": "sha256:" + "c" * 64,
    }

    assert private_intraday_backfill._is_quarantined_head_snapshot_marker_for(
        marker,
        chunk_key="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "b" * 64,
        raw_hash="sha256:" + "c" * 64,
    )
    assert not private_intraday_backfill._is_quarantined_head_snapshot_marker_for(
        marker,
        chunk_key="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "d" * 64,
        raw_hash="sha256:" + "c" * 64,
    )
    assert not private_intraday_backfill._is_quarantined_head_snapshot_marker_for(
        marker,
        chunk_key="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "b" * 64,
        raw_hash="sha256:" + "d" * 64,
    )


def test_candidate_batch_conflict_is_recorded_without_a_snapshot_or_cursor_advance(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    first = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=1)[0]
    conflicting = KisPaperMinuteRawBar(
        exchange_date=first.exchange_date,
        exchange_time=first.exchange_time,
        korea_date=first.korea_date,
        korea_time=first.korea_time,
        open=first.open,
        high=first.high + Decimal("1"),
        low=first.low,
        last=first.last + Decimal("1"),
        volume=first.volume,
    )

    results = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(
                    symbol="QQQ",
                    exchange="NAS",
                    rows=(first, conflicting),
                    next_cursor=None,
                ),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert results[0].status == "rejected"
    assert results[0].reason == "minute_duplicate_conflict"
    assert results[0].conflict_origin == "candidate_batch"
    assert results[0].retained_head_conflict_disposition == "not_applicable"
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["last_conflict_origin"] == "candidate_batch"
    assert qqq["next_cursor"] is None
    assert qqq["chunks"] == []


def test_candidate_batch_conflict_after_an_accepted_page_never_retains_a_prefix(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    first_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    conflicting = KisPaperMinuteRawBar(
        exchange_date=first_rows[0].exchange_date,
        exchange_time=first_rows[0].exchange_time,
        korea_date=first_rows[0].korea_date,
        korea_time=first_rows[0].korea_time,
        open=first_rows[0].open,
        high=first_rows[0].high + Decimal("1"),
        low=first_rows[0].low,
        last=first_rows[0].last + Decimal("1"),
        volume=first_rows[0].volume,
    )
    results = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(
                    symbol="QQQ",
                    exchange="NAS",
                    rows=first_rows,
                    next_cursor="1",
                ),
                _page(
                    symbol="QQQ",
                    exchange="NAS",
                    rows=(conflicting,),
                    next_cursor=None,
                ),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=2,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert results[0].status == "rejected"
    assert results[0].reason == "minute_duplicate_conflict"
    assert qqq["last_reason"] == "minute_duplicate_conflict"
    assert qqq["last_conflict_origin"] == "candidate_batch"
    assert qqq["next_cursor"] is None
    assert qqq["chunks"] == []


def test_legacy_candidate_batch_conflict_does_not_block_fresh_conflicting_rows(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    original_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(
                    symbol="QQQ", exchange="NAS", rows=original_rows, next_cursor=None
                ),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    _mark_qqq_chunk_as_legacy_candidate_batch_conflict(index_path)
    changed_first = KisPaperMinuteRawBar(
        exchange_date=original_rows[0].exchange_date,
        exchange_time=original_rows[0].exchange_time,
        korea_date=original_rows[0].korea_date,
        korea_time=original_rows[0].korea_time,
        open=original_rows[0].open,
        high=original_rows[0].high + Decimal("1"),
        low=original_rows[0].low,
        last=original_rows[0].last + Decimal("1"),
        volume=original_rows[0].volume,
    )
    replacement_rows = (changed_first, original_rows[1])

    results = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(
                    symbol="QQQ", exchange="NAS", rows=replacement_rows, next_cursor=None
                ),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert results[0].status == "collected"
    assert results[0].exact_overlap_rows == 0
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert len(qqq["chunks"]) == 1


def test_legacy_candidate_batch_conflict_is_not_treated_as_cached_chunk(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=rows, next_cursor=None),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    _mark_qqq_chunk_as_legacy_candidate_batch_conflict(index_path)

    results = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=rows, next_cursor=None),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert results[0].status == "collected"
    assert results[0].exact_overlap_rows == 0
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert len(qqq["chunks"]) == 1


def test_removing_legacy_candidate_batch_conflict_preserves_a_head_cursor() -> None:
    persisted_cursor = {"keyb": "20260722092900", "next": "1"}
    target: dict[str, object] = {
        "next_cursor": dict(persisted_cursor),
        "chunks": [_legacy_candidate_batch_conflict_chunk()],
    }

    changed = private_intraday_backfill._remove_candidate_batch_conflicted_chunks(
        {"targets": [target]}, resume_cursor=False
    )

    assert changed is True
    assert target["chunks"] == []
    assert target["next_cursor"] == persisted_cursor


def test_removing_legacy_candidate_batch_conflict_derives_backfill_cursor_from_valid_chunk(
) -> None:
    valid_cursor = {"keyb": "20260722092900", "next": "1"}
    target: dict[str, object] = {
        "next_cursor": {"keyb": "20260722092500", "next": "1"},
        "chunks": [
            {"output_cursor": dict(valid_cursor)},
            _legacy_candidate_batch_conflict_chunk(),
        ],
    }

    changed = private_intraday_backfill._remove_candidate_batch_conflicted_chunks(
        {"targets": [target]}, resume_cursor=True
    )

    assert changed is True
    assert target["chunks"] == [{"output_cursor": valid_cursor}]
    assert target["next_cursor"] == valid_cursor


def test_legacy_duplicate_conflict_recovery_keeps_origin_unrecorded() -> None:
    target_state: dict[str, object] = {"last_conflict_origin": None}

    private_intraday_backfill._record_target_last_observation(
        target_state=target_state,
        reason="minute_duplicate_conflict",
        observed_at_utc="2026-07-22T05:00:00Z",
        origin_recorded=False,
    )

    assert target_state["last_reason"] == "minute_duplicate_conflict"
    assert "last_conflict_origin" not in target_state


def test_terminal_initial_page_is_not_requested_again_after_source_exhaustion(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=rows, next_cursor=None),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    results = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient([KisPaperMarketDataError("minute_response_empty")]),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    assert results[0].status == "source_exhausted"
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert len(qqq["chunks"]) == 1
    snapshots = list(
        (cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION).glob("snapshots/*/manifest.json")
    )
    assert len(snapshots) == 1


def test_orphan_snapshot_recovers_cursor_before_the_next_page(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    initial = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor="1",
            ),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=initial,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    orphan_chunk = qqq["chunks"][0]
    qqq["chunks"] = [
        {
            "chunk_key": orphan_chunk["chunk_key"],
            "raw_market_data_retained": False,
            "historical_note": "one-shot observation only",
        }
    ]
    qqq["next_cursor"] = None
    index_path.write_text(json.dumps(index), encoding="utf-8")

    recovery = _MinuteClient(
        [
            _page(
                symbol="SPY",
                exchange="AMS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor=None,
            )
        ]
    )
    recovered = run_kis_paper_private_intraday_backfill_cycle(
        client=recovery,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert [(result.target_key, result.status) for result in recovered] == [
        ("QQQ/NAS/1m", "recovered"),
        ("SPY/AMS/1m", "collected"),
    ]
    assert [(query.symbol, query.exchange) for query in recovery.queries] == [("SPY", "AMS")]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["next_cursor"] == {"keyb": "20260722092900", "next": "1"}
    assert [chunk["raw_market_data_retained"] for chunk in qqq["chunks"]] == [False, True]

    resumed = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 28), count=2),
                next_cursor=None,
            ),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=resumed,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert resumed.queries[0].continuation_next == "1"
    assert resumed.queries[0].continuation_key == "20260722092900"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert len(qqq["chunks"]) == 3


def test_loader_rejects_tampered_external_raw_data_and_never_uses_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    client = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor=None,
            ),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    raw_path = next(
        (cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION).glob(
            "snapshots/*/raw/ohlcv_1m.csv.gz"
        )
    )
    raw_path.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="raw hash"):
        load_verified_kis_paper_private_intraday_catalog(
            cache_root=cache_root,
            repo_root=repo_root,
            symbol="QQQ",
            exchange="NAS",
        )
    with pytest.raises(ValueError, match="outside Git"):
        run_kis_paper_private_intraday_backfill_cycle(
            client=_MinuteClient([]),
            cache_root=repo_root,
            repo_root=repo_root,
            code_revision="git:test",
        )


def test_loader_accepts_the_first_v1_timestamp_contract_spelling(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    client = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor=None,
            ),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    index_path = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    chunk = index["targets"][0]["chunks"][0]
    manifest_path = index_path.parent / chunk["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["timestamp_contract"].pop("canonical_start_policy")
    manifest["timestamp_contract"]["completed_bar_rule"] = (
        "bar_end_at_or_before_collection_minute"
    )
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    chunk["manifest_hash"] = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
    )

    assert len(catalog.bars) == 2


def test_verified_loader_is_offline_and_credential_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    client = _MinuteClient(
        [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                next_cursor=None,
            ),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("verified loader must stay offline")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("verified loader must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)

    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root,
        repo_root=repo_root,
        symbol="QQQ",
        exchange="NAS",
    )

    assert len(catalog.bars) == 2


def _collect_one_qqq_chunk(*, cache_root: Path, repo_root: Path) -> None:
    results = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(
                    symbol="QQQ",
                    exchange="NAS",
                    rows=_rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2),
                    next_cursor=None,
                ),
                KisPaperMarketDataError("minute_response_empty"),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    assert [(result.target_key, result.status) for result in results] == [
        ("QQQ/NAS/1m", "collected"),
        ("SPY/AMS/1m", "rejected"),
    ]


def _mark_qqq_chunk_as_legacy_candidate_batch_conflict(index_path: Path) -> None:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    chunk = qqq["chunks"][0]
    conflict_fields = {
        "outcome": "partial",
        "reason": "minute_duplicate_conflict",
        "conflict_origin": "candidate_batch",
    }
    chunk.update(conflict_fields)
    manifest_path = index_path.parent / chunk["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["backfill"]["index_chunk"].update(conflict_fields)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    qqq["last_reason"] = None
    qqq["last_conflict_origin"] = None
    index_path.write_text(json.dumps(index), encoding="utf-8")


def _legacy_candidate_batch_conflict_chunk() -> dict[str, object]:
    return {
        "outcome": "partial",
        "reason": "minute_duplicate_conflict",
        "conflict_origin": "candidate_batch",
    }


def _legacy_chunk_key(*, target_key: str, input_cursor: object) -> str:
    payload = json.dumps(
        {
            "backfill_version": KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
            "input_cursor": dict(input_cursor) if isinstance(input_cursor, Mapping) else None,
            "target_key": target_key,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _page(
    *,
    symbol: str,
    exchange: str,
    rows: tuple[KisPaperMinuteRawBar, ...],
    next_cursor: str | None,
) -> KisPaperMinutePage:
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange=exchange, symbol=symbol),
        bars=rows,
        next_cursor=next_cursor,
        more="0",
    )


def _rows(*, start_korea: datetime, count: int) -> tuple[KisPaperMinuteRawBar, ...]:
    rows: list[KisPaperMinuteRawBar] = []
    for index in range(count):
        timestamp = start_korea + timedelta(minutes=index)
        price = Decimal("100") + Decimal(index) / Decimal("100")
        rows.append(
            KisPaperMinuteRawBar(
                exchange_date=timestamp.strftime("%Y%m%d"),
                exchange_time=timestamp.strftime("%H%M%S"),
                korea_date=timestamp.strftime("%Y%m%d"),
                korea_time=timestamp.strftime("%H%M%S"),
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                last=price + Decimal("0.5"),
                volume=Decimal("100"),
            )
        )
    return tuple(rows)
