from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.execution import kis_private_daily_backfill as daily_backfill
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperDailyQuery,
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
)
from thericher_v2.execution.kis_private_daily_backfill import (
    KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
    load_or_initialize_kis_paper_private_daily_backfill_index,
    run_kis_paper_private_daily_backfill_once,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KisPaperPrivateDailyCollectionResult,
    KisPaperPrivateDailyCollectorPage,
    write_kis_paper_private_daily_cache,
)

_OBSERVED_AT = datetime(2026, 7, 21, 18, 0, tzinfo=UTC)


class _RecordingTransport:
    def __init__(self, responses: list[KisMarketDataResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[KisMarketDataRequest] = []

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.requests.append(request)
        return self._responses.pop(0)


class _PacingClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_daily_backfill_collects_one_resumable_qqq_chunk_outside_git(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page([_row("20260717"), _row("20260701")], continuation="F"),
            _daily_page([_row("20260701"), _row("20260101")], continuation="F"),
        ]
    )
    pacing = _PacingClock()

    result = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        sleeper=pacing.sleep,
        monotonic_clock=pacing.monotonic,
    )

    assert result.status == "collected"
    assert result.target_key == "QQQ/NAS/MODP=0"
    assert result.row_count == 3
    assert result.manifest_path is not None
    assert result.manifest_path.is_relative_to(cache_root)
    assert not result.manifest_path.is_relative_to(repo_root)
    assert [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL) for request in transport.requests
    ] == [KIS_PAPER_TOKEN_PATH, KIS_PAPER_DAILY_PATH, KIS_PAPER_DAILY_PATH]
    assert all(
        "order" not in request.url and "balance" not in request.url
        for request in transport.requests
    )
    assert transport.requests[1].query["EXCD"] == "NAS"
    assert transport.requests[2].query["BYMD"] == "20260701"

    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    qqq = index["targets"][0]
    assert qqq["next_anchor_date"] == "20260101"
    assert qqq["state"] == "ready"
    assert qqq["venue_status"] == "verified_by_kis_response"
    assert qqq["chunks"][0]["raw_market_data_retained"] is True
    assert qqq["chunks"][0]["exact_overlap_rows"] == 0
    rendered_index = json.dumps(index, sort_keys=True)
    assert "paper-key" not in rendered_index
    assert "paper-secret" not in rendered_index

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["backfill"] == {
        "contract_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
        "cursor_strategy": "oldest_session_date_with_exact_overlap",
        "input_cursor_date": "20260717",
        "logical_cursor_persisted": True,
        "output_cursor_date": "20260101",
        "target_key": "QQQ/NAS/MODP=0",
    }


def test_partial_continuation_commits_the_valid_first_page_and_advances_once(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page([_row("20260717"), _row("20260701")], continuation="F"),
            _rejected(),
        ]
    )
    pacing = _PacingClock()

    result = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        sleeper=pacing.sleep,
        monotonic_clock=pacing.monotonic,
    )

    assert result.status == "collected"
    assert result.reason == "partial_daily_response_rejected"
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    qqq = index["targets"][0]
    assert qqq["state"] == "ready"
    assert qqq["next_anchor_date"] == "20260701"
    assert qqq["chunks"][0]["outcome"] == "partial"
    assert qqq["chunks"][0]["output_cursor_date"] == "20260701"
    assert qqq["chunks"][0]["raw_market_data_retained"] is True
    assert index["last_shared_reason"] == "inter_chunk_pace"


def test_deferred_target_does_not_block_spy_venue_confirmation(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    qqq_transport = _RecordingTransport([_token(), _rejected()])

    first = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(qqq_transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
    )

    assert first.status == "deferred"
    assert first.target_key == "QQQ/NAS/MODP=0"
    spy_transport = _RecordingTransport(
        [_token(), _daily_page([_row("20260717")], continuation="")]
    )
    second = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(spy_transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT + timedelta(seconds=1),
    )

    assert second.status == "complete"
    assert second.target_key == "SPY/AMS/MODP=0"
    assert spy_transport.requests[1].query["EXCD"] == "AMS"
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert index["targets"][0]["state"] == "deferred"
    assert index["targets"][1]["state"] == "complete"
    assert index["targets"][1]["venue_status"] == "verified_by_kis_response"


def test_empty_daily_response_is_deferred_without_marking_venue_complete(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    transport = _RecordingTransport([_token(), _daily_page([], continuation="")])

    result = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
    )

    assert result.status == "deferred"
    assert result.reason == "empty_daily_response"
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    qqq = index["targets"][0]
    assert qqq["state"] == "deferred"
    assert qqq["next_anchor_date"] == "20260717"
    assert qqq["venue_status"] == "verified_by_prior_private_snapshot"
    assert qqq["chunks"][-1]["raw_market_data_retained"] is False


def test_unretained_empty_snapshot_is_not_a_one_shot_latch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    empty_transport = _RecordingTransport([_token(), _daily_page([], continuation="")])

    first = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(empty_transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
    )

    assert first.status == "deferred"
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    for target in index["targets"][1:]:
        target["state"] = "complete"
    daily_backfill._write_backfill_index(
        root=daily_backfill._backfill_root(cache_root=cache_root, repo_root=repo_root),
        index=index,
    )
    retry_transport = _RecordingTransport(
        [_token(), _daily_page([_row("20260717")], continuation="")]
    )
    second = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(retry_transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT + timedelta(minutes=3),
    )

    assert second.status == "complete"
    assert second.target_key == "QQQ/NAS/MODP=0"
    assert [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL)
        for request in retry_transport.requests
    ] == [KIS_PAPER_TOKEN_PATH, KIS_PAPER_DAILY_PATH]
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    qqq = index["targets"][0]
    assert qqq["state"] == "complete"
    assert [chunk["raw_market_data_retained"] for chunk in qqq["chunks"]] == [False, True]


def test_backfill_prioritizes_the_target_with_the_shortest_history() -> None:
    index = daily_backfill._initial_index()
    targets = index["targets"]
    targets[0]["next_anchor_date"] = "20220804"
    targets[1]["next_anchor_date"] = "20211020"
    targets[2]["next_anchor_date"] = "20231010"

    selected = daily_backfill._select_ready_target(index=index, observed_at=_OBSERVED_AT)

    assert selected is not None
    assert selected["target_key"] == "IWM/AMS/MODP=0"


def test_auth_rejection_applies_a_short_shared_retry_without_creating_a_new_client(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    rejected_transport = _RecordingTransport([_auth_rejected()])

    first = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(rejected_transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
    )

    assert first.status == "deferred"
    assert first.reason == "auth_rejected"
    second = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not create client")),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT + timedelta(seconds=1),
    )

    assert second.status == "deferred"
    assert second.reason == "shared_retry_not_before"
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert index["last_shared_reason"] == "auth_rejected"
    assert index["network_retry_not_before_utc"] is not None


def test_legacy_nys_venue_attempts_migrate_to_ams_without_dropping_their_records(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    for target in index["targets"][1:]:
        target["exchange"] = "NYS"
        target["target_key"] = f"{target['symbol']}/NYS/MODP=0"
        target["last_reason"] = "daily_response_rejected"
    index_path = cache_root / "backfill-v1" / "index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    migrated = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )

    assert [target["target_key"] for target in migrated["targets"]] == [
        "QQQ/NAS/MODP=0",
        "SPY/AMS/MODP=0",
        "IWM/AMS/MODP=0",
    ]
    assert [attempt["target_key"] for attempt in migrated["venue_attempts"]] == [
        "SPY/NYS/MODP=0",
        "IWM/NYS/MODP=0",
    ]


def test_committed_snapshot_hash_drift_stops_before_a_new_client_is_created(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page([_row("20260717"), _row("20260701")], continuation="F"),
            _daily_page([_row("20260701"), _row("20260101")], continuation="F"),
        ]
    )
    pacing = _PacingClock()
    first = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        sleeper=pacing.sleep,
        monotonic_clock=pacing.monotonic,
    )
    assert first.manifest_path is not None
    raw_path = first.manifest_path.parent / "raw" / "ohlcv_daily.csv.gz"
    raw_path.write_bytes(b"tampered")

    second = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not create client")),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT + timedelta(minutes=3),
    )

    assert second.status == "deferred"
    assert second.reason == "committed_snapshot_reconcile_required"


def test_symlinked_raw_snapshot_is_not_accepted(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    result = _completed_result("20260717", "20260701")
    manifest_path, _ = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=cache_root,
        run_id="20260721T180002Z-000001",
        repo_root=repo_root,
        backfill_context={
            "contract_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
            "cursor_strategy": "oldest_session_date_with_exact_overlap",
            "input_cursor_date": "20260717",
            "logical_cursor_persisted": True,
            "output_cursor_date": "20260701",
            "target_key": "QQQ/NAS/MODP=0",
        },
    )
    raw_path = manifest_path.parent / "raw" / "ohlcv_daily.csv.gz"
    external_target = tmp_path / "external.csv.gz"
    external_target.write_bytes(raw_path.read_bytes())
    raw_path.unlink()
    try:
        os.symlink(external_target, raw_path)
    except OSError:
        pytest.skip("Windows symlink creation is unavailable for this test")

    with pytest.raises(ValueError, match="path is invalid"):
        daily_backfill.inspect_kis_paper_private_daily_backfill_snapshot(
            manifest_path=manifest_path,
            cache_root=cache_root,
            repo_root=repo_root,
        )


def test_process_scoped_lock_prevents_concurrent_reclaim_and_recovers_after_release(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    root = cache_root / "backfill-v1"
    first = daily_backfill._acquire_worker_lock(root=root, observed_at=_OBSERVED_AT)
    assert first is not None
    second = daily_backfill._acquire_worker_lock(
        root=root,
        observed_at=_OBSERVED_AT + timedelta(minutes=16),
    )
    assert second is None

    daily_backfill._release_worker_lock(first)
    replacement = daily_backfill._acquire_worker_lock(
        root=root,
        observed_at=_OBSERVED_AT + timedelta(minutes=16),
    )

    assert replacement is not None
    daily_backfill._release_worker_lock(replacement)


def test_backfill_recovers_orphan_snapshot_without_another_network_call(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    result = KisPaperPrivateDailyCollectionResult(
        observed_at=_OBSERVED_AT,
        requested_anchor_date="20260717",
        code_revision="git:test",
        call_counts=KisPaperMarketDataCallCounts(1, 0, 1),
        pages=(
            KisPaperPrivateDailyCollectorPage(
                page_number=1,
                row_count=1,
                newest_date="20260701",
                oldest_date="20260701",
                continuation_advertised=False,
            ),
        ),
        rows=(_raw_row("20260701"),),
        dedupe_count=0,
        conflicting_duplicate_rows=0,
        inter_page_delay_seconds=(),
        status="observed",
    )
    manifest_path, _ = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=cache_root,
        run_id="20260721T180000Z-000001",
        repo_root=repo_root,
        backfill_context={
            "contract_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
            "cursor_strategy": "oldest_session_date_with_exact_overlap",
            "input_cursor_date": "20260717",
            "logical_cursor_persisted": True,
            "output_cursor_date": "20260701",
            "target_key": "QQQ/NAS/MODP=0",
        },
    )

    def no_network_client() -> KisPaperMarketDataClient:
        raise AssertionError("orphan recovery must precede another KIS request")

    recovered = run_kis_paper_private_daily_backfill_once(
        client_factory=no_network_client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT + timedelta(minutes=1),
    )

    assert recovered.status == "recovered"
    assert recovered.manifest_path == manifest_path
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    assert index["targets"][0]["state"] == "complete"
    assert index["targets"][0]["chunks"][0]["raw_market_data_retained"] is True


def test_cross_chunk_conflict_defers_without_advancing_cursor(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data"
    first_transport = _RecordingTransport(
        [
            _token(),
            _daily_page([_row("20260717"), _row("20260701")], continuation="F"),
            _daily_page([_row("20260701"), _row("20260101")], continuation="F"),
        ]
    )
    pacing = _PacingClock()
    run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(first_transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        sleeper=pacing.sleep,
        monotonic_clock=pacing.monotonic,
    )
    index_path = cache_root / "backfill-v1" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for target in index["targets"][1:]:
        target["state"] = "complete"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    second_transport = _RecordingTransport(
        [
            _token(),
            _daily_page([_row("20260101", close="102"), _row("20251201")], continuation="F"),
            _daily_page([_row("20251201"), _row("20251101")], continuation="F"),
        ]
    )
    second = run_kis_paper_private_daily_backfill_once(
        client_factory=lambda: _client(second_transport),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        observed_at=_OBSERVED_AT + timedelta(minutes=2, seconds=1),
        sleeper=pacing.sleep,
        monotonic_clock=pacing.monotonic,
    )

    assert second.status == "deferred"
    assert second.reason == "cross_chunk_duplicate_conflict"
    index = load_or_initialize_kis_paper_private_daily_backfill_index(
        cache_root=cache_root,
        repo_root=repo_root,
    )
    qqq = index["targets"][0]
    assert qqq["state"] == "deferred"
    assert qqq["next_anchor_date"] == "20260101"
    assert qqq["chunks"][-1]["outcome"] == "conflict"
    assert qqq["chunks"][-1]["conflicting_overlap_rows"] == 1


def test_daily_backfill_refuses_a_cache_root_inside_git(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        run_kis_paper_private_daily_backfill_once(
            client_factory=lambda: (_ for _ in ()).throw(AssertionError("must not create client")),
            cache_root=repo_root / "market-data",
            repo_root=repo_root,
            code_revision="git:test",
            observed_at=_OBSERVED_AT,
        )


def test_daily_query_accepts_ams_backfill_targets_but_not_nas_iwm() -> None:
    assert KisPaperDailyQuery(symbol="SPY", exchange="AMS", by_date="20260717").exchange == "AMS"
    assert KisPaperDailyQuery(symbol="IWM", exchange="AMS", by_date="20260717").symbol == "IWM"
    with pytest.raises(ValueError, match="symbol/exchange"):
        KisPaperDailyQuery(symbol="IWM", exchange="NAS", by_date="20260717")


def _client(transport: _RecordingTransport) -> KisPaperMarketDataClient:
    return KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
        max_daily_page_attempts=2,
    )


def _token() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"access_token": "cache-token"})


def _rejected() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"rt_cd": "1", "msg1": "secret server text"})


def _auth_rejected() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"rt_cd": "1"}, status_code=403)


def _daily_page(rows: list[dict[str, str]], *, continuation: str) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {"rt_cd": "0", "output1": {"nrec": str(len(rows))}, "output2": rows},
        headers={"tr_cont": continuation},
    )


def _row(date: str, *, close: str = "101") -> dict[str, str]:
    return {
        "xymd": date,
        "open": "100",
        "high": "102",
        "low": "99",
        "clos": close,
        "tvol": "777",
    }


def _raw_row(date: str) -> KisPaperDailyRawRow:
    return KisPaperDailyRawRow(
        xymd=date,
        open="100",
        high="102",
        low="99",
        clos="101",
        tvol="777",
    )


def _completed_result(anchor_date: str, row_date: str) -> KisPaperPrivateDailyCollectionResult:
    return KisPaperPrivateDailyCollectionResult(
        observed_at=_OBSERVED_AT,
        requested_anchor_date=anchor_date,
        code_revision="git:test",
        call_counts=KisPaperMarketDataCallCounts(1, 0, 1),
        pages=(
            KisPaperPrivateDailyCollectorPage(
                page_number=1,
                row_count=1,
                newest_date=row_date,
                oldest_date=row_date,
                continuation_advertised=False,
            ),
        ),
        rows=(_raw_row(row_date),),
        dedupe_count=0,
        conflicting_duplicate_rows=0,
        inter_page_delay_seconds=(),
        status="observed",
    )
