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
    require_complete_kis_paper_private_intraday_session,
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
    assert (
        len(
            resample_verified_kis_paper_private_intraday_catalog(
                catalog, timeframe=Timeframe.M1, session=session
            ).bars
        )
        == 180
    )
    assert (
        len(
            resample_verified_kis_paper_private_intraday_catalog(
                catalog, timeframe=Timeframe.M5, session=session
            ).bars
        )
        == 36
    )
    assert (
        len(
            resample_verified_kis_paper_private_intraday_catalog(
                catalog, timeframe=Timeframe.M10, session=session
            ).bars
        )
        == 18
    )
    assert (
        len(
            resample_verified_kis_paper_private_intraday_catalog(
                catalog, timeframe=Timeframe.H1, session=session
            ).bars
        )
        == 3
    )
    assert (
        len(
            resample_verified_kis_paper_private_intraday_catalog(
                catalog, timeframe=Timeframe.H3, session=session
            ).bars
        )
        == 1
    )


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
    snapshots_root = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION / "snapshots"
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


def test_head_conflict_quarantines_old_snapshot_and_retains_same_capture(
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
    original_raw = original_manifest.parent / "raw" / "ohlcv_1m.csv.gz"
    original_raw_bytes = original_raw.read_bytes()
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

    replacement_client = _MinuteClient(
        [
            _page(symbol="QQQ", exchange="NAS", rows=fresh_rows, next_cursor=None),
            _page(symbol="SPY", exchange="AMS", rows=spy_rows, next_cursor=None),
        ]
    )
    quarantined = run_kis_paper_private_intraday_backfill_cycle(
        client=replacement_client,
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
        ("QQQ/NAS/1m", "collected"),
        ("SPY/AMS/1m", "recovered"),
    ]
    assert [query.symbol for query in replacement_client.queries] == ["QQQ", "SPY"]
    assert quarantined[0].conflict_origin is None and quarantined[0].reason is None
    assert quarantined[0].retained_head_conflict_disposition == "not_applicable"
    assert quarantined[0].manifest_path is not None and quarantined[0].row_count == 2
    assert quarantined[0].exact_overlap_rows == 0
    assert quarantined[1].conflict_origin is None
    assert quarantined[1].retained_head_conflict_disposition == "not_applicable"
    assert original_manifest.exists()
    assert original_manifest.read_bytes() == original_manifest_bytes
    assert original_raw.read_bytes() == original_raw_bytes
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["chunks"][0] == {
        "historical_note": "quarantined_head_retained_cache_conflict",
        "quarantined_chunk_key": original_chunk["chunk_key"],
        "quarantined_manifest_hash": original_chunk["manifest_hash"],
        "quarantined_raw_sha256": original_chunk["raw_sha256"],
        "raw_market_data_retained": False,
    }
    assert [chunk["raw_market_data_retained"] for chunk in qqq["chunks"]] == [False, True]
    assert qqq["next_cursor"] is None and qqq["last_reason"] is None
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root, repo_root=repo_root, symbol="QQQ", exchange="NAS"
    )
    assert len(catalog.bars) == 2 and catalog.bars[0].close == changed.last

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
        ("QQQ/NAS/1m", "recovered"),
        ("SPY/AMS/1m", "recovered"),
    ]
    assert retried[0].conflict_origin is None
    assert retried[0].retained_head_conflict_disposition == "not_applicable"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert [chunk["raw_market_data_retained"] for chunk in qqq["chunks"]] == [False, True]


@pytest.fixture(params=("committed", "partial"))
def head_revision_case(tmp_path: Path, request: pytest.FixtureRequest) -> dict[str, object]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "head"
    historical = _rows(start_korea=datetime(2026, 7, 21, 9, 30), count=2)
    original = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=3)
    disjoint = _rows(start_korea=datetime(2026, 7, 22, 10, 30), count=2)
    args = dict(
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
    for index, rows in enumerate((historical, original, disjoint)):
        partial = index == 1 and request.param == "partial"
        responses = [
            _page(
                symbol="QQQ",
                exchange="NAS",
                rows=rows,
                next_cursor="1" if index == 0 or partial else None,
            ),
        ]
        if partial:
            responses.append(KisPaperMarketDataError("minute_response_invalid"))
        responses.append(
            _page(
                symbol="SPY",
                exchange="AMS",
                rows=historical,
                next_cursor=None if partial else "1",
            )
        )
        seeded = run_kis_paper_private_intraday_backfill_cycle(
            **(
                args
                | {
                    "client": _MinuteClient(responses),
                    "pages_per_target": 2 if partial else 1,
                    "resume_cursor": index == 0,
                    "quarantine_retained_head_conflicts": index != 0,
                    "observed_at": datetime(2026, 7, 22, 5, index, tzinfo=UTC),
                }
            )
        )
        if partial:
            assert seeded[0].status == "partial"
            assert seeded[0].reason == "minute_response_invalid"
    root = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
    index_path = root / "index.json"
    before = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in before["targets"] if target["target_key"] == "QQQ/NAS/1m")
    revised = replace(
        original[0], high=original[0].high + Decimal(1), last=original[0].last + Decimal(1)
    )
    candidate = (
        revised,
        *original[1:],
        *_rows(start_korea=datetime(2026, 7, 22, 9, 33), count=1),
        disjoint[0],
    )
    immutable = {
        path: path.read_bytes()
        for pattern in ("snapshots/*/manifest.json", "snapshots/*/raw/*.gz")
        for path in root.glob(pattern)
    }
    assert len(qqq["chunks"]) == 3 and qqq["chunks"][0]["collection_scope"] == "historical"
    return dict(
        args=args,
        root=root,
        index_path=index_path,
        before=before,
        qqq=qqq,
        original=original,
        historical=historical,
        candidate=candidate,
        immutable=immutable,
    )


@pytest.mark.parametrize(
    "boundary", ["before_marker", "before_snapshot", "after_snapshot", "after_attachment"]
)
def test_head_revision_crash_preserves_custody_and_recovers_without_refetch(
    head_revision_case: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    case = head_revision_case
    args, root, qqq = case["args"], case["root"], case["qqq"]
    original_write_index = private_intraday_backfill._write_index
    original_write_snapshot = private_intraday_backfill._write_snapshot
    written = []

    def interrupted_index(*, root, index, expected_targets):
        target = next(row for row in index["targets"] if row["target_key"] == "QQQ/NAS/1m")
        quarantined = any(
            chunk.get("quarantined_chunk_key") == qqq["chunks"][1]["chunk_key"]
            for chunk in target["chunks"]
        )
        replacement_attached = any(
            chunk.get("manifest_hash") in written for chunk in target["chunks"]
        )
        if quarantined and boundary == "before_marker":
            raise OSError("synthetic before quarantine marker")
        if replacement_attached and boundary == "after_snapshot":
            raise OSError("synthetic before replacement attachment")
        original_write_index(root=root, index=index, expected_targets=expected_targets)
        if replacement_attached and boundary == "after_attachment":
            raise OSError("synthetic after replacement attachment")

    def interrupted_snapshot(**kwargs):
        persisted = json.loads(case["index_path"].read_text(encoding="utf-8"))
        target = next(row for row in persisted["targets"] if row["target_key"] == "QQQ/NAS/1m")
        assert target["chunks"][1]["quarantined_chunk_key"] == qqq["chunks"][1]["chunk_key"]
        assert target["next_cursor"] == qqq["next_cursor"]
        if boundary == "before_snapshot":
            raise OSError("synthetic before replacement snapshot")
        result = original_write_snapshot(**kwargs)
        written.append(result[1])
        return result

    client = _MinuteClient(
        [
            _page(symbol="QQQ", exchange="NAS", rows=case["candidate"], next_cursor=None),
        ]
    )
    with monkeypatch.context() as patch:
        patch.setattr(private_intraday_backfill, "_write_index", interrupted_index)
        patch.setattr(private_intraday_backfill, "_write_snapshot", interrupted_snapshot)
        with pytest.raises(OSError, match="synthetic"):
            run_kis_paper_private_intraday_backfill_cycle(**(args | {"client": client}))
    assert [query.symbol for query in client.queries] == ["QQQ"]
    index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    target = next(row for row in index["targets"] if row["target_key"] == "QQQ/NAS/1m")
    assert target["chunks"][0] == qqq["chunks"][0]
    assert target["chunks"][2] == qqq["chunks"][2]
    assert target["next_cursor"] == qqq["next_cursor"]
    assert next(row for row in index["targets"] if row["symbol"] == "SPY") == next(
        row for row in case["before"]["targets"] if row["symbol"] == "SPY"
    )

    if boundary == "before_marker":
        assert target["chunks"] == qqq["chunks"] and not written
    elif boundary == "before_snapshot":
        assert len(target["chunks"]) == 3 and not written
        with pytest.raises(ValueError, match="incomplete"):
            require_complete_kis_paper_private_intraday_session(
                load_verified_kis_paper_private_intraday_catalog(
                    cache_root=args["cache_root"],
                    repo_root=args["repo_root"],
                    symbol="QQQ",
                    exchange="NAS",
                ),
                session=SessionWindow(
                    open_ts=datetime(2026, 7, 22, 0, 30, tzinfo=UTC),
                    close_ts=datetime(2026, 7, 22, 1, 32, tzinfo=UTC),
                ),
            )
    elif boundary == "after_snapshot":
        assert len(target["chunks"]) == 3 and len(written) == 1
        recovery_client = _MinuteClient(
            [
                _page(symbol="SPY", exchange="AMS", rows=case["historical"], next_cursor=None),
            ]
        )
        recovered = run_kis_paper_private_intraday_backfill_cycle(
            **(args | {"client": recovery_client})
        )
        assert recovered[0].status == "recovered" and recovered[0].manifest_hash == written[0]
        assert recovered[0].exact_overlap_rows == 1
        assert [query.symbol for query in recovery_client.queries] == ["SPY"]
        index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    else:
        assert len(target["chunks"]) == 4 and len(written) == 1
    assert private_intraday_backfill._recover_orphan_snapshots(root=root, index=index) == ()
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())
    assert all(
        not path.is_symlink() and path.stat().st_nlink == 1
        for pattern in ("snapshots/*/manifest.json", "snapshots/*/raw/*.gz")
        for path in root.glob(pattern)
    )
    if written:
        target = next(row for row in index["targets"] if row["target_key"] == "QQQ/NAS/1m")
        assert len(target["chunks"]) == 4
        assert target["chunks"][-1]["manifest_hash"] == written[0]
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=args["cache_root"], repo_root=args["repo_root"], symbol="QQQ", exchange="NAS"
        )
        assert len(catalog.bars) == 8 and len({bar.start_ts for bar in catalog.bars}) == 8
        revised_bar = next(
            bar for bar in catalog.bars if bar.start_ts == datetime(2026, 7, 22, 0, 30, tzinfo=UTC)
        )
        assert revised_bar.close == case["candidate"][0].last


@pytest.mark.parametrize(
    "kind", ["mixed_historical", "partial_mixed_historical", "partial_candidate", "candidate_batch"]
)
def test_head_revision_never_salvages_cross_scope_or_invalid_candidates(
    head_revision_case: dict[str, object],
    kind: str,
) -> None:
    case = head_revision_case
    args = case["args"]
    rows = case["candidate"]
    partial = kind in {"partial_candidate", "partial_mixed_historical"}
    historical = kind in {"mixed_historical", "partial_mixed_historical"}
    if historical:
        old = case["historical"][0]
        rows = (*rows, replace(old, high=old.high + Decimal(1), last=old.last + Decimal(1)))
    elif kind == "candidate_batch":
        rows = (*rows, case["original"][0])
    responses = [
        _page(
            symbol="QQQ",
            exchange="NAS",
            rows=rows,
            next_cursor="1" if partial else None,
        )
    ]
    if partial:
        responses.append(KisPaperMarketDataError(
            "minute_response_invalid" if historical else "minute_response_empty"
        ))
    responses.append(_page(symbol="SPY", exchange="AMS", rows=case["historical"], next_cursor=None))
    client = _MinuteClient(responses)
    results = run_kis_paper_private_intraday_backfill_cycle(
        **(args | {"client": client, "pages_per_target": 2 if partial else 1})
    )
    assert results[0].status == "rejected" and results[0].reason == "minute_duplicate_conflict"
    assert results[0].conflict_origin == (
        "candidate_batch" if kind == "candidate_batch" else "retained_cache"
    )
    diagnostic = results[0].retained_head_conflict_diagnostic
    if kind == "candidate_batch":
        assert diagnostic is None
    else:
        assert diagnostic is not None
        assert diagnostic.conflicting_minute_count == (2 if historical else 1)
        assert diagnostic.conflicting_chunk_count == (2 if historical else 1)
        assert diagnostic.fresh_status == ("partial" if partial else "collected")
        assert diagnostic.fresh_reason == (
            ("minute_response_invalid" if historical else "minute_response_empty")
            if partial else None
        )
        assert ("fresh_not_collected" in diagnostic.failed_predicates) == (
            kind == "partial_candidate"
        )
        assert ("predecessor_not_head" in diagnostic.failed_predicates) == (
            historical
        )
    index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    target = next(row for row in index["targets"] if row["target_key"] == "QQQ/NAS/1m")
    assert target["chunks"] == case["qqq"]["chunks"]
    assert target["next_cursor"] == case["qqq"]["next_cursor"]
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())
    assert len(list(case["root"].glob("snapshots/*/manifest.json"))) == 4
    assert [query.symbol for query in client.queries] == (
        ["QQQ", "QQQ", "SPY"] if partial else ["QQQ", "SPY"]
    )


def test_head_revision_with_shorter_support_does_not_backfill_quarantined_rows(
    head_revision_case: dict[str, object],
) -> None:
    case = head_revision_case
    args = case["args"]
    results = run_kis_paper_private_intraday_backfill_cycle(
        **(
            args
            | {
                "client": _MinuteClient(
                    [
                        _page(
                            symbol="QQQ",
                            exchange="NAS",
                            rows=(case["candidate"][0],),
                            next_cursor=None,
                        ),
                        _page(
                            symbol="SPY", exchange="AMS", rows=case["historical"], next_cursor=None
                        ),
                    ]
                ),
            }
        )
    )
    assert results[0].status == "collected" and results[0].row_count == 1
    diagnostic = results[0].retained_head_conflict_diagnostic
    assert diagnostic is not None
    assert diagnostic.failed_predicates == ()
    assert diagnostic.prospective_active_key_loss_count == 2
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=args["cache_root"], repo_root=args["repo_root"], symbol="QQQ", exchange="NAS"
    )
    assert len(catalog.bars) == 5
    with pytest.raises(ValueError, match="incomplete"):
        require_complete_kis_paper_private_intraday_session(
            catalog,
            session=SessionWindow(
                open_ts=datetime(2026, 7, 22, 0, 30, tzinfo=UTC),
                close_ts=datetime(2026, 7, 22, 0, 33, tzinfo=UTC),
            ),
        )
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())


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


@pytest.mark.parametrize(
    "reason",
    ["minute_response_empty", "auth_rejected", "transport_failure", "token_request_not_due"],
)
def test_partial_head_snapshot_cannot_be_quarantined_by_head_option(
    tmp_path: Path,
    reason: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    original_rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    initial = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page(symbol="QQQ", exchange="NAS", rows=original_rows, next_cursor="1"),
                KisPaperMarketDataError(reason),
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
    assert results[0].retained_head_conflict_diagnostic is not None
    assert results[0].retained_head_conflict_diagnostic.failed_predicates == (
        "predecessor_outcome_reason_ineligible",
    )
    assert original_manifest.read_bytes() == original_manifest_bytes
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in index["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert qqq["chunks"] == [original_chunk]
    assert qqq["next_cursor"] is None


@pytest.mark.parametrize("reverse_chunks", [False, True])
@pytest.mark.parametrize("fresh_status", ["collected", "partial"])
def test_mixed_partial_head_predecessors_reject_revision_independent_of_chunk_order(
    tmp_path: Path,
    reverse_chunks: bool,
    fresh_status: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "head"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=3)
    args = dict(
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=2,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    for minute, (prefix, reason) in enumerate(
        ((rows, "minute_response_invalid"), (rows[:1], "auth_rejected"))
    ):
        seeded = run_kis_paper_private_intraday_backfill_cycle(
            **(
                args
                | {
                    "client": _MinuteClient(
                        [
                            _page(symbol="QQQ", exchange="NAS", rows=prefix, next_cursor="1"),
                            KisPaperMarketDataError(reason),
                            _page(symbol="SPY", exchange="AMS", rows=rows, next_cursor=None),
                        ]
                    ),
                    "observed_at": datetime(2026, 7, 22, 5, minute, tzinfo=UTC),
                }
            )
        )
        assert seeded[0].status == "partial" and seeded[0].reason == reason
    root = cache_root / "v1"
    index_path = root / "index.json"
    before = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = next(target for target in before["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert len(qqq["chunks"]) == 2
    assert all(chunk["outcome"] == "partial" for chunk in qqq["chunks"])
    if reverse_chunks:
        qqq["chunks"].reverse()
    index_path.write_text(json.dumps(before), encoding="utf-8")
    immutable = {
        path: path.read_bytes()
        for pattern in ("snapshots/*/manifest.json", "snapshots/*/raw/*.gz")
        for path in root.glob(pattern)
    }
    changed = replace(rows[0], high=rows[0].high + 1, last=rows[0].last + 1)
    responses = [
        _page(
            symbol="QQQ", exchange="NAS", rows=(changed, *rows[1:]),
            next_cursor="1" if fresh_status == "partial" else None,
        ),
    ]
    if fresh_status == "partial":
        responses.append(KisPaperMarketDataError("minute_response_invalid"))
    responses.append(_page(symbol="SPY", exchange="AMS", rows=rows, next_cursor=None))
    client = _MinuteClient(responses)
    results = run_kis_paper_private_intraday_backfill_cycle(
        **(
            args
            | {
                "client": client,
                "pages_per_target": 2 if fresh_status == "partial" else 1,
                "observed_at": datetime(2026, 7, 22, 5, 5, tzinfo=UTC),
            }
        )
    )
    assert results[0].status == "rejected" and results[0].reason == "minute_duplicate_conflict"
    assert results[0].conflict_origin == "retained_cache"
    assert results[0].retained_head_conflict_disposition == "preserved"
    assert results[0].manifest_path is None and results[0].row_count == 0
    diagnostic = results[0].retained_head_conflict_diagnostic
    assert diagnostic is not None and diagnostic.fresh_status == fresh_status
    assert diagnostic.conflicting_chunk_count == 2 and diagnostic.conflicting_minute_count == 1
    assert diagnostic.failed_predicates == ("predecessor_outcome_reason_ineligible",)
    assert results[1].status == "recovered"
    assert [query.symbol for query in client.queries] == (
        ["QQQ", "QQQ", "SPY"] if fresh_status == "partial" else ["QQQ", "SPY"]
    )
    after = json.loads(index_path.read_text(encoding="utf-8"))
    retained = next(target for target in after["targets"] if target["target_key"] == "QQQ/NAS/1m")
    assert retained["chunks"] == qqq["chunks"] and retained["next_cursor"] == qqq["next_cursor"]
    assert after["generation"] == before["generation"]
    assert {
        path: path.read_bytes()
        for pattern in ("snapshots/*/manifest.json", "snapshots/*/raw/*.gz")
        for path in root.glob(pattern)
    } == immutable


@pytest.mark.parametrize("fresh_status", ["collected", "partial"])
def test_three_page_partial_head_revision_preserves_bytes_and_measures_fresh_predicate(
    tmp_path: Path,
    fresh_status: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "head"
    original = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=360)
    mixed = (*_rows(start_korea=datetime(2026, 7, 21, 15, 59), count=1), original[0])

    def pages(symbol, exchange, rows, *, fail_fourth=False):
        result = [
            _page(
                symbol=symbol,
                exchange=exchange,
                rows=rows[max(0, end - 120) : end],
                next_cursor=None,
            )
            for end in range(len(rows), 0, -120)
        ]
        if fail_fourth:
            result.append(_page(symbol=symbol, exchange=exchange, rows=mixed, next_cursor=None))
        return result

    args = dict(
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=4,
        resume_cursor=False,
        quarantine_retained_head_conflicts=True,
        explicit_pair_head_continuation=True,
        observed_at=datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    initial = run_kis_paper_private_intraday_backfill_cycle(
        **(
            args
            | {
                "client": _MinuteClient(
                    pages("QQQ", "NAS", original, fail_fourth=True)
                    + pages("SPY", "AMS", original, fail_fourth=True)
                )
            }
        )
    )
    assert all(run.status == "partial" and run.row_count == 360 for run in initial)
    assert all(run.failure_page_ordinal == 4 for run in initial)
    root = cache_root / "v1"
    index_path = root / "index.json"
    before = json.loads(index_path.read_text(encoding="utf-8"))
    old = before["targets"][0]["chunks"][0]
    immutable = {path: path.read_bytes() for path in root.glob("snapshots/*/*") if path.is_file()}
    immutable.update({path: path.read_bytes() for path in root.glob("snapshots/*/raw/*.gz")})
    changed = list(original)
    changed[100] = replace(changed[100], high=changed[100].high + 1, last=changed[100].last + 1)
    fresh = tuple(changed if fresh_status == "partial" else changed[:-1])
    client = _MinuteClient(
        pages("QQQ", "NAS", fresh, fail_fourth=fresh_status == "partial")
        + pages("SPY", "AMS", original[:1])
    )
    results = run_kis_paper_private_intraday_backfill_cycle(
        **(args | {"client": client, "observed_at": datetime(2026, 7, 22, 8, 5, tzinfo=UTC)})
    )
    diagnostic = results[0].retained_head_conflict_diagnostic
    assert diagnostic is not None
    assert diagnostic.fresh_status == fresh_status
    assert diagnostic.fresh_reason == (
        "minute_response_invalid" if fresh_status == "partial" else None
    )
    assert diagnostic.accepted_page_count == 3
    assert diagnostic.accepted_row_count == len(fresh)
    assert diagnostic.conflicting_chunk_count == diagnostic.conflicting_minute_count == 1
    assert diagnostic.failed_predicates == ()
    assert diagnostic.prospective_active_key_loss_count == (0 if fresh_status == "partial" else 1)
    assert results[0].status == fresh_status
    assert results[1].status == "collected"
    assert [query.symbol for query in client.queries] == (
        ["QQQ"] * (4 if fresh_status == "partial" else 3) + ["SPY"]
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    qqq = index["targets"][0]
    assert qqq["next_cursor"] == before["targets"][0]["next_cursor"]
    assert qqq["chunks"][0]["quarantined_manifest_hash"] == old["manifest_hash"]
    assert qqq["chunks"][0]["quarantined_raw_sha256"] == old["raw_sha256"]
    assert qqq["chunks"][1]["row_count"] == len(fresh)
    assert qqq["chunks"][1]["outcome"] == (
        "partial" if fresh_status == "partial" else "committed"
    )
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=cache_root, repo_root=repo_root, symbol="QQQ", exchange="NAS"
    )
    assert len(catalog.bars) == len(fresh)
    if fresh_status == "partial":
        assert results[0].reason == "minute_response_invalid"
        assert results[0].failure_phase == "head_contract"
        assert results[0].failure_code == "mixed_exchange_dates"
        assert results[0].failure_page_ordinal == 4
    assert private_intraday_backfill._recover_orphan_snapshots(root=root, index=index) == ()
    assert all(path.read_bytes() == data for path, data in immutable.items())


def test_seven_page_partial_revision_and_later_head_observations_preserve_custody(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "head"
    original = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=840)
    mixed = (*_rows(start_korea=datetime(2026, 7, 21, 15, 59), count=1), original[0])
    targets = (("QQQ", "NAS"), ("SPY", "AMS"))

    def pages(rows):
        return [
            page
            for symbol, exchange in targets
            for page in (
                *(
                    _page(
                        symbol=symbol, exchange=exchange, rows=rows[end - 120:end],
                        next_cursor=None,
                    )
                    for end in range(840, 0, -120)
                ),
                _page(symbol=symbol, exchange=exchange, rows=mixed, next_cursor=None),
            )
        ]

    args = dict(
        cache_root=cache_root, repo_root=repo_root, code_revision="git:test",
        pages_per_target=8, resume_cursor=False, quarantine_retained_head_conflicts=True,
        explicit_pair_head_continuation=True,
        sleeper=lambda _seconds: None, monotonic_clock=lambda: 0.0,
    )
    historical = _rows(start_korea=datetime(2026, 7, 21, 9, 30), count=2)
    run_kis_paper_private_intraday_backfill_cycle(
        **(args | dict(
            client=_MinuteClient([
                _page(symbol=symbol, exchange=exchange, rows=historical, next_cursor="1")
                for symbol, exchange in targets
            ]),
            resume_cursor=True, quarantine_retained_head_conflicts=False,
            explicit_pair_head_continuation=False, pages_per_target=1,
            observed_at=datetime(2026, 7, 22, 4, 0, tzinfo=UTC),
        ))
    )
    run_kis_paper_private_intraday_backfill_cycle(
        **(args | dict(client=_MinuteClient(pages(original)),
                      observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC)))
    )
    root = cache_root / "v1"
    index_path = root / "index.json"
    before = json.loads(index_path.read_text(encoding="utf-8"))
    immutable = {
        path: path.read_bytes()
        for pattern in ("snapshots/*/manifest.json", "snapshots/*/raw/*.gz")
        for path in root.glob(pattern)
    }
    changed = list(original)
    changed[100] = replace(changed[100], high=changed[100].high + 1, last=changed[100].last + 1)
    client = _MinuteClient(pages(tuple(changed)))
    results = run_kis_paper_private_intraday_backfill_cycle(
        **(args | dict(client=client, observed_at=datetime(2026, 7, 22, 5, 5, tzinfo=UTC)))
    )
    assert [query.symbol for query in client.queries] == ["QQQ"] * 8 + ["SPY"] * 8
    after = json.loads(index_path.read_text(encoding="utf-8"))
    for result, previous, current in zip(results, before["targets"], after["targets"], strict=True):
        assert result.status == "partial" and result.reason == "minute_response_invalid"
        assert result.row_count == 840 and result.failure_page_ordinal == 8
        assert result.failure_phase == "head_contract"
        assert result.failure_code == "mixed_exchange_dates"
        assert result.requested_pages_per_target == 8
        diagnostic = result.retained_head_conflict_diagnostic
        assert diagnostic is not None and len(diagnostic.to_payload()) == 8
        assert diagnostic.failed_predicates == ()
        assert diagnostic.prospective_active_key_loss_count == 0
        assert diagnostic.accepted_page_count == 7
        assert diagnostic.conflicting_chunk_count == diagnostic.conflicting_minute_count == 1
        assert current["next_cursor"] == previous["next_cursor"]
        assert current["chunks"][0] == previous["chunks"][0]
        assert (
            current["chunks"][1]["quarantined_manifest_hash"]
            == previous["chunks"][1]["manifest_hash"]
        )
        assert current["chunks"][2]["outcome"] == "partial"
        assert current["chunks"][2]["input_cursor"] is current["chunks"][2]["output_cursor"] is None
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert manifest["status"] == "partial" and len(manifest["pages"]) == 7
        assert manifest["failure_page_ordinal"] == manifest["requested_pages_per_target"] == 8
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=cache_root, repo_root=repo_root,
            symbol=current["symbol"], exchange=current["exchange"],
        )
        assert len(catalog.bars) == 842
    assert all(path.read_bytes() == data for path, data in immutable.items())
    assert private_intraday_backfill._recover_orphan_snapshots(root=root, index=after) == ()

    repeat = run_kis_paper_private_intraday_backfill_cycle(
        **(args | dict(client=_MinuteClient(pages(tuple(changed))),
                      observed_at=datetime(2026, 7, 22, 5, 10, tzinfo=UTC)))
    )
    assert all(result.status == "partial" and result.failure_page_ordinal == 8 for result in repeat)
    repeated_index = json.loads(index_path.read_text(encoding="utf-8"))
    assert repeated_index["generation"] == after["generation"]
    changed[200] = replace(changed[200], high=changed[200].high + 1, last=changed[200].last + 1)
    later = run_kis_paper_private_intraday_backfill_cycle(
        **(args | dict(client=_MinuteClient(pages(tuple(changed))),
                      observed_at=datetime(2026, 7, 22, 5, 15, tzinfo=UTC)))
    )
    assert all(result.status == "partial" and result.row_count == 840 for result in later)
    final = json.loads(index_path.read_text(encoding="utf-8"))
    assert all(current["next_cursor"] == previous["next_cursor"]
               for current, previous in zip(final["targets"], before["targets"], strict=True))
    assert private_intraday_backfill._recover_orphan_snapshots(root=root, index=final) == ()
    assert all(path.read_bytes() == data for path, data in immutable.items())


@pytest.mark.parametrize("reason", [
    "auth_rejected", "rate_limited", "transport_failure", "minute_response_empty",
    "minute_cursor_stalled", "private-unallowlisted-body",
])
def test_partial_head_revision_rejects_other_stop_reasons(
    head_revision_case: dict[str, object], reason: str,
) -> None:
    case = head_revision_case
    client = _MinuteClient([
        _page(symbol="QQQ", exchange="NAS", rows=case["candidate"], next_cursor="1"),
        KisPaperMarketDataError(reason),
        _page(symbol="SPY", exchange="AMS", rows=case["historical"], next_cursor=None),
    ])
    results = run_kis_paper_private_intraday_backfill_cycle(
        **(case["args"] | dict(client=client, pages_per_target=2))
    )
    assert results[0].status == "rejected" and results[0].manifest_path is None
    diagnostic = results[0].retained_head_conflict_diagnostic
    assert diagnostic is not None and diagnostic.failed_predicates == ("fresh_not_collected",)
    index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    assert index["targets"][0]["chunks"] == case["qqq"]["chunks"]
    assert [query.symbol for query in client.queries] == ["QQQ", "QQQ", "SPY"]
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())


def test_partial_head_revision_rejects_positive_active_key_loss(
    head_revision_case: dict[str, object],
) -> None:
    case = head_revision_case
    client = _MinuteClient([
        _page(symbol="QQQ", exchange="NAS", rows=case["candidate"][:1], next_cursor="1"),
        KisPaperMarketDataError("minute_response_invalid"),
        _page(symbol="SPY", exchange="AMS", rows=case["historical"], next_cursor=None),
    ])
    results = run_kis_paper_private_intraday_backfill_cycle(
        **(case["args"] | dict(client=client, pages_per_target=2))
    )
    assert results[0].status == "rejected" and results[0].manifest_path is None
    diagnostic = results[0].retained_head_conflict_diagnostic
    assert diagnostic is not None and diagnostic.failed_predicates == ("partial_active_key_loss",)
    assert diagnostic.prospective_active_key_loss_count == 2
    index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    assert index["targets"][0]["chunks"] == case["qqq"]["chunks"]
    assert index["targets"][0]["next_cursor"] == case["qqq"]["next_cursor"]
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())


def test_partial_revision_snapshot_crash_keeps_diagnostic_only_in_original_manifest(
    head_revision_case: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = head_revision_case
    original_index = private_intraday_backfill._write_index
    original_snapshot = private_intraday_backfill._write_snapshot
    written = []

    def record_snapshot(**kwargs):
        result = original_snapshot(**kwargs)
        written.append(result)
        return result

    def interrupt_attachment(*, root, index, expected_targets):
        qqq = index["targets"][0]
        if written and any(chunk.get("manifest_hash") == written[0][1] for chunk in qqq["chunks"]):
            raise OSError("synthetic partial snapshot before index")
        original_index(root=root, index=index, expected_targets=expected_targets)

    client = _MinuteClient([
        _page(symbol="QQQ", exchange="NAS", rows=case["candidate"], next_cursor="1"),
        KisPaperMarketDataError(
            "minute_response_invalid",
            failure_phase="row_parse", failure_code="required_field_invalid",
        ),
    ])
    with monkeypatch.context() as patch:
        patch.setattr(private_intraday_backfill, "_write_snapshot", record_snapshot)
        patch.setattr(private_intraday_backfill, "_write_index", interrupt_attachment)
        with pytest.raises(OSError, match="synthetic partial snapshot before index"):
            run_kis_paper_private_intraday_backfill_cycle(
                **(case["args"] | dict(client=client, pages_per_target=2))
            )
    assert len(written) == 1 and [query.symbol for query in client.queries] == ["QQQ", "QQQ"]
    replacement_bytes = written[0][0].read_bytes()
    recovery_client = _MinuteClient([
        _page(symbol="SPY", exchange="AMS", rows=case["historical"], next_cursor=None),
    ])
    recovered = run_kis_paper_private_intraday_backfill_cycle(
        **(case["args"] | dict(client=recovery_client, pages_per_target=2,
                              observed_at=datetime(2026, 7, 22, 5, 10, tzinfo=UTC)))
    )
    result = recovered[0]
    assert result.status == "partial" and result.reason == "minute_response_invalid"
    assert result.manifest_hash == written[0][1] and result.manifest_path == written[0][0]
    assert result.failure_phase is result.failure_code is None
    assert result.failure_page_ordinal is result.requested_pages_per_target is None
    original_manifest = json.loads(replacement_bytes)
    assert original_manifest["failure_phase"] == "row_parse"
    assert original_manifest["failure_code"] == "required_field_invalid"
    assert (
        original_manifest["failure_page_ordinal"]
        == original_manifest["requested_pages_per_target"] == 2
    )
    assert [query.symbol for query in recovery_client.queries] == ["SPY"]
    index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    qqq = index["targets"][0]
    assert qqq["next_cursor"] == case["qqq"]["next_cursor"]
    assert qqq["chunks"][0] == case["qqq"]["chunks"][0]
    assert (
        qqq["chunks"][1]["quarantined_manifest_hash"]
        == case["qqq"]["chunks"][1]["manifest_hash"]
    )
    assert qqq["chunks"][-1]["outcome"] == "partial"
    assert qqq["chunks"][-1]["reason"] == "minute_response_invalid"
    assert private_intraday_backfill._recover_orphan_snapshots(root=case["root"], index=index) == ()
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())
    assert written[0][0].read_bytes() == replacement_bytes

    from thericher_v2.data.kis_paper_intraday_session_capture import (
        build_kis_paper_intraday_session_capture_outcome,
    )

    outcome = build_kis_paper_intraday_session_capture_outcome(
        runs=recovered, cache_root=case["args"]["cache_root"],
        repository_root=case["args"]["repo_root"],
        observed_at=datetime(2026, 7, 22, 5, 10, tzinfo=UTC),
    )
    assert outcome.status == "incomplete"


@pytest.mark.parametrize(
    "original_budget,new_budget,original_at,new_at",
    [
        (8, 4, "2026-07-22T22:21:00+00:00", "2026-07-23T00:29:00+00:00"),
        (4, 8, "2026-07-22T19:29:00+00:00", "2026-07-22T22:21:00+00:00"),
        (4, 4, "2026-07-22T19:29:00+00:00", "2026-07-22T19:30:00+00:00"),
        (8, 8, "2026-07-22T22:21:00+00:00", "2026-07-22T22:22:00+00:00"),
    ],
)
def test_partial_orphan_new_schedule_capture_never_projects_original_failure_fields(
    head_revision_case: dict[str, object], monkeypatch: pytest.MonkeyPatch,
    original_budget: int, new_budget: int, original_at: str, new_at: str,
) -> None:
    from thericher_v2.data.kis_paper_intraday_session_capture import (
        build_and_write_kis_paper_intraday_session_capture,
        build_kis_paper_intraday_session_capture_outcome,
        kis_paper_intraday_head_requested_page_budget,
    )
    from thericher_v2.ops import kis_paper_intraday_head_schedule_receipt as receipt_reader

    case = head_revision_case
    original_observed = datetime.fromisoformat(original_at)
    new_observed = datetime.fromisoformat(new_at)
    original_run_id = "intraday-head-" + original_observed.strftime("%Y%m%dT%H%M%S%fZ")
    new_run_id = "intraday-head-" + new_observed.strftime("%Y%m%dT%H%M%S%fZ")
    assert new_observed > original_observed and new_run_id != original_run_id
    assert kis_paper_intraday_head_requested_page_budget(original_run_id) == original_budget
    assert kis_paper_intraday_head_requested_page_budget(new_run_id) == new_budget
    prefix = list(_rows(
        start_korea=datetime(2026, 7, 22, 9, 30), count=120 * (original_budget - 1),
    ))
    prefix[0] = replace(prefix[0], high=prefix[0].high + 1, last=prefix[0].last + 1)
    responses = [
        _page(symbol="QQQ", exchange="NAS", rows=tuple(prefix[end - 120:end]), next_cursor=None)
        for end in range(len(prefix), 0, -120)
    ]
    responses.append(KisPaperMarketDataError(
        "minute_response_invalid", failure_phase="row_parse", failure_code="required_field_invalid",
    ))
    client = _MinuteClient(responses)
    original_index = private_intraday_backfill._write_index
    original_snapshot = private_intraday_backfill._write_snapshot
    written = []

    def record_snapshot(**kwargs):
        result = original_snapshot(**kwargs)
        written.append(result)
        return result

    def interrupt_attachment(*, root, index, expected_targets):
        if written and any(
            chunk.get("manifest_hash") == written[0][1] for chunk in index["targets"][0]["chunks"]
        ):
            raise OSError("synthetic canonical partial orphan")
        original_index(root=root, index=index, expected_targets=expected_targets)

    with monkeypatch.context() as patch:
        patch.setattr(private_intraday_backfill, "_write_snapshot", record_snapshot)
        patch.setattr(private_intraday_backfill, "_write_index", interrupt_attachment)
        with pytest.raises(OSError, match="synthetic canonical partial orphan"):
            run_kis_paper_private_intraday_backfill_cycle(
                **(case["args"] | dict(
                    client=client, pages_per_target=original_budget,
                    explicit_pair_head_continuation=True, observed_at=original_observed,
                ))
            )
    assert [query.symbol for query in client.queries] == ["QQQ"] * original_budget
    assert len(written) == 1
    source_path, source_hash = written[0]
    source_bytes = source_path.read_bytes()
    assert source_hash == "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    original_manifest = json.loads(source_bytes)
    assert original_manifest["status"] == "partial"
    assert len(original_manifest["pages"]) == original_budget - 1
    original_fields = {
        "failure_phase": "row_parse", "failure_code": "required_field_invalid",
        "failure_page_ordinal": original_budget, "requested_pages_per_target": original_budget,
    }
    assert {key: original_manifest[key] for key in original_fields} == original_fields

    recovery_client = _MinuteClient([
        _page(symbol="SPY", exchange="AMS", rows=case["historical"], next_cursor=None),
    ])
    recovered = run_kis_paper_private_intraday_backfill_cycle(
        **(case["args"] | dict(
            client=recovery_client, pages_per_target=new_budget,
            explicit_pair_head_continuation=True, observed_at=new_observed,
        ))
    )
    result = recovered[0]
    assert result.status == "partial" and result.reason == "minute_response_invalid"
    assert result.manifest_hash == source_hash and result.manifest_path == source_path
    assert all(getattr(result, field) is None for field in original_fields)
    assert [query.symbol for query in recovery_client.queries] == ["SPY"]
    capture_args = dict(
        cache_root=case["args"]["cache_root"], repository_root=case["args"]["repo_root"],
        observed_at=new_observed, schedule_run_id=new_run_id,
    )
    capture = build_and_write_kis_paper_intraday_session_capture(runs=recovered, **capture_args)
    assert capture.outcome.status == "incomplete"
    assert capture.outcome.targets[0].status == "partial"
    capture_bytes = capture.evidence_path.read_bytes()
    payload = json.loads(capture_bytes)
    assert payload["schedule_run_id"] == new_run_id and payload["status"] == "incomplete"
    assert not set(original_fields).intersection(payload["targets"][0])
    assert capture.evidence_sha256 == "sha256:" + hashlib.sha256(capture_bytes).hexdigest()
    binding = receipt_reader.KisPaperIntradayHeadTerminalReceiptBinding(
        **(capture.terminal_receipt_binding() | dict(observed_at=new_observed))
    )
    receipt_reader._verify_capture_payload_binding(payload, binding)
    projected = receipt_reader._collection_recovery_targets_from_capture_payload(payload)
    assert projected[0].status == "partial" and projected[0].reason == "minute_response_invalid"
    assert all(getattr(projected[0], field) is None for field in original_fields)
    if original_budget != new_budget:
        with pytest.raises(ValueError, match="session capture requested page budget is invalid"):
            build_kis_paper_intraday_session_capture_outcome(
                runs=(replace(result, **original_fields), recovered[1]), **capture_args,
            )
    index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    private_intraday_backfill._attest_committed_snapshots(root=case["root"], index=index)
    assert private_intraday_backfill._recover_orphan_snapshots(root=case["root"], index=index) == ()
    assert source_path.read_bytes() == source_bytes
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())


@pytest.mark.parametrize("resume_cursor", [False, True])
@pytest.mark.parametrize(
    "reason", ["minute_response_invalid", "auth_rejected", "minute_response_empty"]
)
def test_legacy_partial_orphan_preserves_partial_reason_in_head_and_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, resume_cursor: bool, reason: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=3)
    args = dict(
        cache_root=cache_root, repo_root=repo_root, code_revision="git:test",
        pages_per_target=2, resume_cursor=resume_cursor,
        observed_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
        sleeper=lambda _seconds: None, monotonic_clock=lambda: 0.0,
    )
    original_index = private_intraday_backfill._write_index

    def interrupt_attachment(*, root, index, expected_targets):
        if index["targets"][0]["chunks"]:
            raise OSError("synthetic legacy partial orphan")
        original_index(root=root, index=index, expected_targets=expected_targets)

    client = _MinuteClient([
        _page(symbol="QQQ", exchange="NAS", rows=rows, next_cursor="1"),
        KisPaperMarketDataError(reason),
    ])
    with monkeypatch.context() as patch:
        patch.setattr(private_intraday_backfill, "_write_index", interrupt_attachment)
        with pytest.raises(OSError, match="synthetic legacy partial orphan"):
            run_kis_paper_private_intraday_backfill_cycle(**(args | dict(client=client)))
    recovery_client = _MinuteClient([
        _page(symbol="SPY", exchange="AMS", rows=rows, next_cursor=None),
    ])
    recovered = run_kis_paper_private_intraday_backfill_cycle(
        **(args | dict(client=recovery_client))
    )
    assert recovered[0].status == "partial" and recovered[0].reason == reason
    assert recovered[0].failure_phase is recovered[0].failure_code is None
    assert recovered[0].failure_page_ordinal is recovered[0].requested_pages_per_target is None
    assert [query.symbol for query in recovery_client.queries] == ["SPY"]
    root = cache_root / "v1"
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert index["targets"][0]["chunks"][0]["outcome"] == "partial"
    expected_cursor = {"next": "1", "keyb": "20260722092900"} if resume_cursor else None
    assert index["targets"][0]["next_cursor"] == expected_cursor
    assert private_intraday_backfill._recover_orphan_snapshots(root=root, index=index) == ()


def test_partial_orphan_is_not_masked_by_later_collected_orphan() -> None:
    target = private_intraday_backfill.KisPaperPrivateIntradayTarget("QQQ", "NAS")
    partial = private_intraday_backfill._RecoveredSnapshot(
        target=target, manifest_path=Path("partial.json"), manifest_hash="sha256:" + "a" * 64,
        chunk=dict(outcome="partial", reason="auth_rejected", row_count=3, exact_overlap_rows=0),
    )
    committed = private_intraday_backfill._RecoveredSnapshot(
        target=target, manifest_path=Path("committed.json"), manifest_hash="sha256:" + "b" * 64,
        chunk=dict(outcome="committed", reason=None, row_count=4, exact_overlap_rows=0),
    )
    result = private_intraday_backfill._recovered_target_run(
        target=target, snapshots=[partial, committed]
    )
    assert result.status == "partial" and result.reason == "auth_rejected"
    assert result.manifest_hash == partial.manifest_hash


@pytest.mark.parametrize("mutation", [
    {"failure_phase": None}, {"failure_code": "sensitive-body"},
    {"failure_page_ordinal": True}, {"failure_page_ordinal": 3},
    {"requested_pages_per_target": 1}, {"status": "collected"}, {"pages": []},
])
def test_snapshot_failure_diagnostic_rejects_invalid_original_metadata(mutation) -> None:
    manifest = dict(
        status="partial", pages=[{}],
        failure_phase="row_parse", failure_code="required_field_invalid",
        failure_page_ordinal=2, requested_pages_per_target=2,
    )
    chunk = dict(outcome="partial", reason="minute_response_invalid")
    with pytest.raises(ValueError, match="diagnostic is invalid"):
        private_intraday_backfill._snapshot_failure_diagnostic(manifest | mutation, chunk)
    with pytest.raises(ValueError, match="diagnostic is invalid"):
        private_intraday_backfill._snapshot_failure_diagnostic(
            {key: value for key, value in manifest.items() if key != "failure_code"}, chunk,
        )
    assert private_intraday_backfill._snapshot_failure_diagnostic(
        dict(status="partial", pages=[{}]), chunk,
    ) == {}


def test_partial_conflict_diagnostic_keeps_legacy_rejection_and_scoped_success() -> None:
    fields = dict(
        fresh_status="partial", fresh_reason="minute_response_invalid", accepted_row_count=840,
        accepted_page_count=7, conflicting_chunk_count=1, conflicting_minute_count=1,
        failed_predicates=("fresh_not_collected",), prospective_active_key_loss_count=0,
    )
    legacy = private_intraday_backfill.KisPaperRetainedHeadConflictDiagnostic(**fields)
    successful = private_intraday_backfill.KisPaperRetainedHeadConflictDiagnostic(
        **(fields | dict(failed_predicates=()))
    )
    assert len(legacy.to_payload()) == len(successful.to_payload()) == 8
    assert legacy.to_payload()["failed_predicates"] == ["fresh_not_collected"]
    for mutation in (
        dict(fresh_reason="auth_rejected", failed_predicates=()),
        dict(failed_predicates=(), prospective_active_key_loss_count=1),
        dict(failed_predicates=("partial_active_key_loss",)),
    ):
        with pytest.raises(ValueError, match="retained conflict diagnostic is invalid"):
            private_intraday_backfill.KisPaperRetainedHeadConflictDiagnostic(**(fields | mutation))


@pytest.mark.parametrize(
    "field,value",
    [
        ("collection_scope", "historical"),
        ("input_cursor", {"next": "1", "keyb": "20260722092900"}),
        ("output_cursor", {"next": "1", "keyb": "20260722092900"}),
        ("outcome", "partial"),
        ("reason", "minute_response_empty"),
        ("conflict_origin", "retained_cache"),
    ],
)
def test_head_eligibility_binds_all_fields_to_hash_matched_immutable_manifest(
    head_revision_case: dict[str, object],
    field: str,
    value: object,
) -> None:
    case = head_revision_case
    index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    chunk = index["targets"][0]["chunks"][1]
    manifest_path = case["root"] / chunk["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    embedded = manifest["backfill"]["index_chunk"]
    embedded[field] = "committed" if field == "outcome" and value == embedded[field] else value
    payload = json.dumps(manifest).encode("utf-8")
    manifest_path.write_bytes(payload)
    chunk["manifest_hash"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    case["index_path"].write_text(json.dumps(index), encoding="utf-8")
    client = _MinuteClient([])
    with pytest.raises(ValueError, match="private intraday snapshot eligibility mismatch"):
        run_kis_paper_private_intraday_backfill_cycle(**(case["args"] | {"client": client}))
    assert client.queries == []
    assert manifest_path.read_bytes() == payload


def test_index_only_cursor_free_head_forgery_cannot_confer_revision_eligibility(
    head_revision_case: dict[str, object],
) -> None:
    case = head_revision_case
    index = json.loads(case["index_path"].read_text(encoding="utf-8"))
    historical = index["targets"][0]["chunks"][0]
    historical["collection_scope"] = "head"
    historical["output_cursor"] = None
    case["index_path"].write_text(json.dumps(index), encoding="utf-8")
    client = _MinuteClient([])
    with pytest.raises(ValueError, match="private intraday snapshot eligibility mismatch"):
        run_kis_paper_private_intraday_backfill_cycle(**(case["args"] | {"client": client}))
    assert client.queries == []
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())


def test_index_only_partial_reason_forgery_cannot_confer_revision_eligibility(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "head"
    rows = _rows(start_korea=datetime(2026, 7, 22, 9, 30), count=2)
    args = dict(
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
    run_kis_paper_private_intraday_backfill_cycle(
        **(
            args
            | {
                "client": _MinuteClient(
                    [
                        _page(symbol="QQQ", exchange="NAS", rows=rows, next_cursor="1"),
                        KisPaperMarketDataError("minute_response_empty"),
                        _page(symbol="SPY", exchange="AMS", rows=rows, next_cursor=None),
                    ]
                )
            }
        )
    )
    index_path = cache_root / "v1/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    chunk = index["targets"][0]["chunks"][0]
    manifest_path = index_path.parent / chunk["manifest_path"]
    before = manifest_path.read_bytes()
    chunk["reason"] = "minute_response_invalid"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    client = _MinuteClient([])
    with pytest.raises(ValueError, match="private intraday snapshot eligibility mismatch"):
        run_kis_paper_private_intraday_backfill_cycle(**(args | {"client": client}))
    assert client.queries == [] and manifest_path.read_bytes() == before


def test_head_revision_counts_distinct_conflicts_and_only_lost_active_keys(
    head_revision_case: dict[str, object],
) -> None:
    case = head_revision_case
    args = case["args"]
    for row in case["original"][:2]:
        run_kis_paper_private_intraday_backfill_cycle(
            **(
                args
                | {
                    "client": _MinuteClient(
                        [
                            _page(symbol="QQQ", exchange="NAS", rows=(row,), next_cursor=None),
                            _page(
                                symbol="SPY",
                                exchange="AMS",
                                rows=case["historical"],
                                next_cursor=None,
                            ),
                        ]
                    )
                }
            )
        )
    results = run_kis_paper_private_intraday_backfill_cycle(
        **(
            args
            | {
                "client": _MinuteClient(
                    [
                        _page(
                            symbol="QQQ",
                            exchange="NAS",
                            rows=(case["candidate"][0],),
                            next_cursor=None,
                        ),
                        _page(
                            symbol="SPY", exchange="AMS", rows=case["historical"], next_cursor=None
                        ),
                    ]
                )
            }
        )
    )
    diagnostic = results[0].retained_head_conflict_diagnostic
    assert diagnostic is not None and diagnostic.failed_predicates == ()
    assert diagnostic.conflicting_chunk_count == 2 and diagnostic.conflicting_minute_count == 1
    assert diagnostic.prospective_active_key_loss_count == 1
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=args["cache_root"], repo_root=args["repo_root"], symbol="QQQ", exchange="NAS"
    )
    assert len(catalog.bars) == 6
    assert all(path.read_bytes() == data for path, data in case["immutable"].items())


@pytest.mark.parametrize(
    "field,value",
    [
        ("fresh_status", "unknown"),
        ("fresh_status", []),
        ("fresh_reason", "sensitive-body"),
        ("fresh_reason", {}),
        ("accepted_row_count", True),
        ("accepted_page_count", 0),
        ("conflicting_chunk_count", -1),
        ("conflicting_minute_count", 2),
        ("failed_predicates", ("sensitive-body",)),
        ("failed_predicates", ({},)),
        ("failed_predicates", ("fresh_not_collected",)),
        ("prospective_active_key_loss_count", -1),
    ],
)
def test_retained_head_conflict_diagnostic_rejects_noncontract_values(field, value) -> None:
    fields = dict(
        fresh_status="collected",
        fresh_reason=None,
        accepted_row_count=1,
        accepted_page_count=1,
        conflicting_chunk_count=1,
        conflicting_minute_count=1,
        failed_predicates=(),
        prospective_active_key_loss_count=0,
    )
    with pytest.raises(
        ValueError, match="^private intraday retained conflict diagnostic is invalid$"
    ):
        private_intraday_backfill.KisPaperRetainedHeadConflictDiagnostic(
            **(fields | {field: value})
        )
    valid = private_intraday_backfill.KisPaperRetainedHeadConflictDiagnostic(**fields)
    assert valid.to_payload()["failed_predicates"] == []
    assert len(valid.to_payload()) == 8


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
                _page(symbol="QQQ", exchange="NAS", rows=original_rows, next_cursor=None),
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
                _page(symbol="QQQ", exchange="NAS", rows=replacement_rows, next_cursor=None),
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


def test_removing_legacy_candidate_batch_conflict_derives_backfill_cursor_from_valid_chunk() -> (
    None
):
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
    manifest["timestamp_contract"]["completed_bar_rule"] = "bar_end_at_or_before_collection_minute"
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
