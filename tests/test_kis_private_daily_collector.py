from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
)
from thericher_v2.execution.kis_minute_qualification import (
    mark_external_one_shot_network_started,
    mark_external_one_shot_summary_written,
    reserve_external_one_shot_attempt,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
    KisPaperPrivateDailyCollectionResult,
    mark_private_daily_collector_completed,
    mark_private_daily_collector_network_started,
    private_daily_collector_recovery_state,
    reserve_private_daily_collector_attempt,
    run_bounded_kis_paper_private_daily_collection,
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
        self.delays: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)
        self.value += seconds


def test_private_daily_collector_paces_deduplicates_and_writes_atomic_cache(tmp_path: Path) -> None:
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page(
                [
                    _row("20260717", close="101", volume="777.777"),
                    _row("20260224", close="100", volume="776.776"),
                ],
                continuation="F",
            ),
            _daily_page(
                [
                    _row("20260224", close="100", volume="776.776"),
                    _row("20251001", close="99", volume="775.775"),
                ],
                continuation="F",
            ),
        ]
    )
    pacing = _PacingClock()
    result = run_bounded_kis_paper_private_daily_collection(
        _client(transport),
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        sleeper=pacing.sleep,
        monotonic_clock=pacing.monotonic,
    )

    assert result.status == "observed"
    assert result.call_counts == KisPaperMarketDataCallCounts(1, 0, 2)
    assert result.dedupe_count == 1
    assert result.conflicting_duplicate_rows == 0
    assert [row.xymd for row in result.rows] == ["20251001", "20260224", "20260717"]
    assert result.inter_page_delay_seconds == (2.0,)
    assert pacing.delays == [2.0]
    assert [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL) for request in transport.requests
    ] == [KIS_PAPER_TOKEN_PATH, KIS_PAPER_DAILY_PATH, KIS_PAPER_DAILY_PATH]
    assert transport.requests[2].headers["tr_cont"] == "F"
    assert transport.requests[2].query["BYMD"] == "20260224"

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "daily"
    manifest_path, manifest_hash = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=cache_root,
        run_id="20260721T180000Z",
        repo_root=repo_root,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_document = manifest["files"]["raw_daily_rows"]
    raw_path = manifest_path.parent / raw_document["path"]
    raw_payload = raw_path.read_bytes()
    rendered = json.dumps(manifest, sort_keys=True)
    with gzip.open(raw_path, mode="rt", encoding="utf-8") as handle:
        rows = handle.read().splitlines()

    assert manifest["status"] == "completed"
    assert manifest["completed"] is True
    assert manifest["stop_outcome"] == "two_pages_completed"
    assert manifest["returned_date_bounds"] == {
        "newest_session_date": "2026-07-17",
        "oldest_session_date": "2025-10-01",
    }
    assert manifest["deduplication"]["exact_duplicate_rows_removed"] == 1
    assert manifest["requests"]["observed_inter_page_delay_ms"] == [2000]
    assert raw_document["sha256"] == "sha256:" + hashlib.sha256(raw_payload).hexdigest()
    assert rows[0] == "symbol,exchange,session_date,open,high,low,close,volume"
    assert rows[1].startswith("QQQ,NAS,2025-10-01,")
    assert "777.777" not in rendered
    assert "cache-token" not in rendered
    assert "paper-key" not in rendered
    assert manifest["requested_date_bounds"]["continuation_cursor_persisted"] is False
    assert manifest["redaction"]["continuation_cursors_persisted"] is False
    assert manifest_hash.startswith("sha256:")


def test_private_daily_collector_retains_explicit_incomplete_partial_cache_on_rejection(
    tmp_path: Path,
) -> None:
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page([_row("20260717"), _row("20260224")], continuation="F"),
            _rejected(),
        ]
    )
    pacing = _PacingClock()
    result = run_bounded_kis_paper_private_daily_collection(
        _client(transport),
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        sleeper=pacing.sleep,
        monotonic_clock=pacing.monotonic,
    )

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    manifest_path, _ = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=tmp_path / "market-data",
        run_id="20260721T180001Z",
        repo_root=repo_root,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result.status == "rejected"
    assert result.reason == "daily_response_rejected"
    assert result.call_counts == KisPaperMarketDataCallCounts(1, 0, 2)
    assert len(result.rows) == 2
    assert result.inter_page_delay_seconds == (2.0,)
    assert len(transport.requests) == 3
    assert manifest["status"] == "rejected"
    assert manifest["completed"] is False
    assert manifest["stop_outcome"] == "daily_response_rejected"
    assert manifest["files"]["raw_daily_rows"] is not None


def test_private_daily_collector_rejects_conflicting_date_without_silent_selection() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page([_row("20260717"), _row("20260224", close="100")], continuation="F"),
            _daily_page([_row("20260224", close="101")], continuation=""),
        ]
    )
    pacing = _PacingClock()

    result = run_bounded_kis_paper_private_daily_collection(
        _client(transport),
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
        sleeper=pacing.sleep,
        monotonic_clock=pacing.monotonic,
    )

    assert result.status == "rejected"
    assert result.reason == "daily_duplicate_conflict"
    assert result.conflicting_duplicate_rows == 1
    assert [row.xymd for row in result.rows] == ["20260224", "20260717"]
    assert len(transport.requests) == 3


def test_private_daily_control_tracks_retention_and_blocks_replay(tmp_path: Path) -> None:
    transport = _RecordingTransport([_token(), _daily_page([_row("20260717")], continuation="")])
    result = run_bounded_kis_paper_private_daily_collection(
        _client(transport),
        code_revision="git:test",
        observed_at=_OBSERVED_AT,
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    cache_root = tmp_path / "market-data"

    reserve_private_daily_collector_attempt(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_OBSERVED_AT,
    )
    assert private_daily_collector_recovery_state(
        control_root=control_root,
        repo_root=repo_root,
    ) == "reconcile"
    mark_private_daily_collector_network_started(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_OBSERVED_AT,
    )
    manifest_path, manifest_hash = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=cache_root,
        run_id="20260721T180002Z",
        repo_root=repo_root,
    )
    marker = mark_private_daily_collector_completed(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_OBSERVED_AT,
        manifest_hash=manifest_hash,
        manifest_path=manifest_path,
        result=result,
    )

    marker_document = json.loads(marker.read_text(encoding="utf-8"))
    assert private_daily_collector_recovery_state(
        control_root=control_root,
        repo_root=repo_root,
    ) == "complete"
    assert marker_document["raw_market_data_retained"] is True
    assert marker_document["manifest_hash"] == manifest_hash
    with pytest.raises(ValueError, match="already_reserved"):
        reserve_private_daily_collector_attempt(
            control_root=control_root,
            repo_root=repo_root,
            observed_at=_OBSERVED_AT,
        )


def test_private_daily_cache_stays_outside_git(tmp_path: Path) -> None:
    result = KisPaperPrivateDailyCollectionResult(
        observed_at=_OBSERVED_AT,
        requested_anchor_date="20260717",
        code_revision="git:test",
        call_counts=KisPaperMarketDataCallCounts(1, 0, 0),
        pages=(),
        rows=(),
        dedupe_count=0,
        conflicting_duplicate_rows=0,
        inter_page_delay_seconds=(),
        status="rejected",
        reason="daily_response_rejected",
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        write_kis_paper_private_daily_cache(
            result=result,
            cache_root=repo_root / "market-data",
            run_id="20260721T180003Z",
            repo_root=repo_root,
        )


def test_generic_one_shot_can_record_raw_retention_without_rewriting_history(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    objective_id = "raw-cache-control-test-v1"

    marker = reserve_external_one_shot_attempt(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
        observed_at=_OBSERVED_AT,
        raw_market_data_retained=True,
    )
    mark_external_one_shot_network_started(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
        observed_at=_OBSERVED_AT,
    )
    mark_external_one_shot_summary_written(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
        observed_at=_OBSERVED_AT,
        summary_hash="sha256:unit",
        result_status="observed",
    )

    assert json.loads(marker.read_text(encoding="utf-8"))["raw_market_data_retained"] is True
    ledger = next((control_root / "ledger").glob("*.jsonl"))
    assert all(
        json.loads(line)["raw_market_data_retained"] is True
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("objective_id") == objective_id
    )


def _client(transport: _RecordingTransport) -> KisPaperMarketDataClient:
    return KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
        max_daily_page_attempts=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
    )


def _token() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"access_token": "cache-token"})


def _rejected() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"rt_cd": "1", "msg1": "secret server text"})


def _daily_page(rows: list[dict[str, str]], *, continuation: str) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {"rt_cd": "0", "output1": {"nrec": str(len(rows))}, "output2": rows},
        headers={"tr_cont": continuation},
    )


def _row(date: str, *, close: str = "101", volume: str = "777") -> dict[str, str]:
    return {
        "xymd": date,
        "open": "100",
        "high": "102",
        "low": "99",
        "clos": close,
        "tvol": volume,
    }
