from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.data.kis_paper_intraday_session_capture import (
    KisPaperIntradaySessionCaptureTarget,
    build_and_write_kis_paper_intraday_session_capture,
    kis_paper_intraday_head_requested_page_budget,
    retained_head_conflict_diagnostic_from_payload,
    validate_schedule_run_id,
    write_kis_paper_intraday_session_capture_evidence,
)
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_MINUTE_MAX_ROWS,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KisPaperPrivateIntradayBackfillRun,
    run_kis_paper_private_intraday_backfill_cycle,
)

_KOREA = ZoneInfo("Asia/Seoul")


@pytest.mark.parametrize(
    "diagnostic",
    [
        {"failure_phase": "head_contract"},
        {
            "failure_phase": "head_contract",
            "failure_code": "synthetic-secret",
            "failure_page_ordinal": 4,
            "requested_pages_per_target": 4,
        },
        {
            "failure_phase": "row_parse",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": 4,
            "requested_pages_per_target": 4,
        },
        {
            "failure_phase": "head_contract",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": True,
            "requested_pages_per_target": 4,
        },
        {
            "failure_phase": "head_contract",
            "failure_code": "mixed_exchange_dates",
            "failure_page_ordinal": 0,
            "requested_pages_per_target": 4,
        },
    ],
)
def test_session_capture_rejects_invalid_optional_diagnostics(
    diagnostic: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="minute failure diagnostic is invalid"):
        KisPaperIntradaySessionCaptureTarget(
            target_key="QQQ/NAS/1m",
            status="partial",
            row_count=360,
            exact_overlap_rows=0,
            reason="minute_response_invalid",
            **diagnostic,
        )


def test_session_capture_legacy_targets_have_no_diagnostic_fields() -> None:
    target = KisPaperIntradaySessionCaptureTarget(
        target_key="QQQ/NAS/1m",
        status="partial",
        row_count=360,
        exact_overlap_rows=0,
        reason="minute_response_invalid",
    )
    assert not any(key.startswith("failure_") for key in target.to_payload())
    assert "requested_pages_per_target" not in target.to_payload()
    assert "token_http_status_class" not in target.to_payload()
    assert "token_upstream_code" not in target.to_payload()
    assert "retained_head_conflict_diagnostic" not in target.to_payload()


@pytest.mark.parametrize("status_class", ["1xx", "2xx", "3xx", "4xx", "5xx"])
@pytest.mark.parametrize("status", ["partial", "rejected"])
def test_session_capture_serializes_optional_closed_token_http_class(
    status_class: str, status: str
) -> None:
    target = KisPaperIntradaySessionCaptureTarget(
        target_key="QQQ/NAS/1m",
        status=status,
        row_count=0,
        exact_overlap_rows=0,
        reason="auth_rejected",
        token_http_status_class=status_class,
    )
    assert target.to_payload()["token_http_status_class"] == status_class
    assert "token_upstream_code" not in target.to_payload()
    assert "requested_pages_per_target" not in target.to_payload()


@pytest.mark.parametrize(
    ("status", "reason", "diagnostic"),
    [
        ("collected", "auth_rejected", {"token_http_status_class": "4xx"}),
        ("rejected", "token_request_not_due", {"token_http_status_class": "4xx"}),
        ("partial", "minute_response_invalid", {"token_http_status_class": "2xx"}),
        ("rejected", "rate_limited", {"token_upstream_code": "EGW00201"}),
        (
            "rejected",
            "auth_rejected",
            {"token_http_status_class": "4xx", "token_upstream_code": "EGW00201"},
        ),
        ("rejected", "response_invalid", {"token_http_status_class": "5xx"}),
        ("rejected", "auth_rejected", {"token_http_status_class": "4XX"}),
        ("rejected", "auth_rejected", {"token_http_status_class": True}),
        ("rejected", "auth_rejected", {"token_http_status_class": []}),
        (
            "rejected",
            "rate_limited",
            {"token_http_status_class": "4xx", "token_upstream_code": "synthetic-secret"},
        ),
    ],
)
def test_session_capture_rejects_invalid_token_diagnostic_combinations(
    status: str, reason: str, diagnostic: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="token .*diagnostic is invalid"):
        KisPaperIntradaySessionCaptureTarget(
            target_key="QQQ/NAS/1m",
            status=status,
            row_count=0,
            exact_overlap_rows=0,
            reason=reason,
            **diagnostic,
        )


@pytest.mark.parametrize("budget", [None, True, 4.0, 0, 2, 9, 999999])
def test_session_capture_rejects_missing_invalid_or_insufficient_page_budget(
    budget: object,
) -> None:
    with pytest.raises(ValueError, match="minute failure diagnostic is invalid"):
        KisPaperIntradaySessionCaptureTarget(
            target_key="QQQ/NAS/1m",
            status="partial",
            row_count=360,
            exact_overlap_rows=0,
            reason="minute_response_invalid",
            failure_phase="head_contract",
            failure_code="mixed_exchange_dates",
            failure_page_ordinal=4,
            requested_pages_per_target=budget,
        )


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        ("20260105T2119599999999Z", 4),
        ("20260105T2120000000000Z", 8),
        ("20260106T0059599999999Z", 8),
        ("20260106T0100000000000Z", 4),
        ("20260706T2019599999999Z", 4),
        ("20260706T2020000000000Z", 8),
        ("20260706T2359599999999Z", 8),
        ("20260707T0000000000000Z", 4),
        ("20260711T2120000000000Z", 4),
    ],
)
def test_session_capture_page_budget_matches_existing_weekday_dst_window(
    stamp: str, expected: int
) -> None:
    assert kis_paper_intraday_head_requested_page_budget(f"intraday-head-{stamp}") == expected


@pytest.mark.parametrize(
    ("run_stamp", "requested_pages", "valid"),
    [
        ("20260728T2019599999999Z", 4, True),
        ("20260728T2020000000000Z", 8, True),
        ("20260728T2019599999999Z", 8, False),
        ("20260728T2020000000000Z", 4, False),
    ],
)
def test_session_capture_binds_actual_budget_to_invocation_start_not_capture_clock(
    tmp_path: Path, run_stamp: str, requested_pages: int, valid: bool
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    cache_root = tmp_path / "market-data"
    runs = tuple(
        KisPaperPrivateIntradayBackfillRun(
            status="partial",
            target_key=key,
            row_count=0,
            exact_overlap_rows=0,
            reason="minute_response_invalid",
            failure_phase="head_contract",
            failure_code="mixed_exchange_dates",
            failure_page_ordinal=requested_pages,
            requested_pages_per_target=requested_pages,
        )
        for key in ("QQQ/NAS/1m", "SPY/AMS/1m")
    )
    kwargs = dict(
        runs=runs,
        cache_root=cache_root,
        repository_root=repository_root,
        observed_at=datetime(2026, 7, 28, 20, 20, 1, tzinfo=ZoneInfo("UTC")),
        schedule_run_id=f"intraday-head-{run_stamp}",
    )
    if not valid:
        with pytest.raises(ValueError, match="session capture requested page budget is invalid"):
            build_and_write_kis_paper_intraday_session_capture(**kwargs)
        assert not cache_root.exists()
        return
    capture = build_and_write_kis_paper_intraday_session_capture(**kwargs)
    persisted = json.loads(capture.evidence_path.read_bytes())
    assert all(t["requested_pages_per_target"] == requested_pages for t in persisted["targets"])
    assert "sha256:" + hashlib.sha256(capture.evidence_path.read_bytes()).hexdigest() == (
        capture.evidence_sha256
    )


class _MinuteClient:
    def __init__(self, responses: list[KisPaperMinutePage | BaseException]) -> None:
        self._responses = list(responses)
        self.queries: list[KisPaperMinuteQuery] = []

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: object | None = None,
    ) -> KisPaperMinutePage:
        self.queries.append(query)
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def test_session_capture_receipt_is_d_only_safe_and_classifies_a_complete_session(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    session = us_equity_2026_session(date(2026, 7, 22))
    assert session is not None and session.kind == "regular"
    observed_at = session.window.close_ts + timedelta(minutes=1)
    schedule_run_id = "intraday-head-20260722T2001000000000Z"
    client = _MinuteClient(
        [
            *_pages("QQQ", "NAS", _session_rows(session.window.open_ts, 390)),
            _page("SPY", "AMS", _session_rows(session.window.open_ts, 2)),
        ]
    )

    runs = run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=4,
        resume_cursor=False,
        observed_at=observed_at,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    capture = build_and_write_kis_paper_intraday_session_capture(
        runs=runs,
        cache_root=cache_root,
        repository_root=repo_root,
        observed_at=observed_at,
        schedule_run_id=schedule_run_id,
    )

    assert capture.outcome.status == "complete"
    assert len(client.queries) == 5
    assert all(query.continuation_next == "1" for query in client.queries[1:4])
    assert client.queries[0].continuation_next is None
    assert client.queries[4].continuation_next is None
    assert capture.evidence_path.is_relative_to(cache_root)
    assert not any(repo_root.iterdir())
    payload = json.loads(capture.evidence_path.read_text(encoding="utf-8"))
    assert payload == capture.outcome.safe_payload()
    assert payload["schedule_run_id"] == schedule_run_id
    assert payload["current_session_cumulative_coverage_category"] == "complete"
    assert (
        payload["current_session_cumulative_coverage_digest"]
        == "sha256:"
        + hashlib.sha256(
            json.dumps(
                payload["current_session_cumulative_coverage"],
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
    )
    assert (
        capture.evidence_sha256
        == "sha256:" + hashlib.sha256(capture.evidence_path.read_bytes()).hexdigest()
    )
    output_payload = capture.safe_output_payload()
    assert output_payload["terminal_receipt_binding"] == {
        "schedule_run_id": schedule_run_id,
        "observed_at": observed_at.isoformat(),
        "receipt_sha256": capture.evidence_sha256,
        "current_session_cumulative_coverage_digest": payload[
            "current_session_cumulative_coverage_digest"
        ],
        "current_session_cumulative_coverage_category": "complete",
    }
    assert set(output_payload["terminal_receipt_binding"]) == {
        "schedule_run_id",
        "observed_at",
        "receipt_sha256",
        "current_session_cumulative_coverage_digest",
        "current_session_cumulative_coverage_category",
    }
    assert "evidence_path" not in output_payload
    unbound_capture = build_and_write_kis_paper_intraday_session_capture(
        runs=runs,
        cache_root=cache_root,
        repository_root=repo_root,
        observed_at=observed_at,
    )
    assert "schedule_run_id" not in unbound_capture.outcome.safe_payload()
    assert "terminal_receipt_binding" not in unbound_capture.safe_output_payload()
    assert payload["route_class"] == "kis_paper_market_data"
    assert payload["storage"] == "external_market_data_only"
    coverage = payload["coverage"]
    assert coverage["complete_regular_session_dates"] == ["2026-07-22"]
    assert coverage["regular_session_coverage"] == [
        {
            "complete_minute_count": 390,
            "expected_minute_count": 390,
            "missing_minute_count": 0,
            "missing_minute_ranges": [],
            "session_date": "2026-07-22",
            "status": "complete",
        }
    ]
    cumulative_coverage = payload["current_session_cumulative_coverage"]
    assert cumulative_coverage["complete_regular_session_dates"] == ["2026-07-22"]
    assert cumulative_coverage["regular_session_coverage"] == coverage["regular_session_coverage"]
    rendered_cumulative_coverage = json.dumps(cumulative_coverage, sort_keys=True)
    for forbidden in (
        "manifest_path",
        "row_fingerprints",
        "123.45",
        "paper-key",
        "access_token",
        "SPY",
    ):
        assert forbidden not in rendered_cumulative_coverage
    rendered = json.dumps(payload, sort_keys=True)
    for forbidden in ("manifest_path", "row_fingerprints", "123.45", "paper-key", "access_token"):
        assert forbidden not in rendered


def test_session_capture_schedule_run_id_is_optional_and_canonical() -> None:
    assert validate_schedule_run_id(None) is None
    assert validate_schedule_run_id("intraday-head-20260807T0424001234567Z") == (
        "intraday-head-20260807T0424001234567Z"
    )
    with pytest.raises(ValueError, match="schedule run ID is invalid"):
        validate_schedule_run_id("intraday-head-2026-07-22T200100Z")
    with pytest.raises(ValueError, match="schedule run ID is invalid"):
        validate_schedule_run_id("not-a-schedule-run-id")


def test_session_capture_keeps_partial_terminal_head_data_partial_and_never_repairs_it(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    legacy_session = us_equity_2026_session(date(2026, 7, 21))
    session = us_equity_2026_session(date(2026, 7, 22))
    assert legacy_session is not None and session is not None
    legacy_client = _MinuteClient(
        [
            *_pages("QQQ", "NAS", _session_rows(legacy_session.window.open_ts, 390)),
            _page("SPY", "AMS", _session_rows(legacy_session.window.open_ts, 2)),
        ]
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=legacy_client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=4,
        resume_cursor=False,
        observed_at=legacy_session.window.close_ts + timedelta(minutes=1),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    observed_at = session.window.close_ts + timedelta(minutes=1)
    client = _MinuteClient(
        [
            *_pages("QQQ", "NAS", _session_rows(session.window.open_ts, 239)),
            KisPaperMarketDataError("minute_response_empty"),
        ]
    )
    future_session = us_equity_2026_session(date(2026, 7, 23))
    assert future_session is not None and future_session.kind == "regular"

    runs = run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=2,
        resume_cursor=False,
        observed_at=observed_at,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                *_pages(
                    "QQQ",
                    "NAS",
                    _session_rows(future_session.window.open_ts, 390),
                ),
                _page("SPY", "AMS", _session_rows(future_session.window.open_ts, 2)),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=4,
        resume_cursor=False,
        observed_at=future_session.window.close_ts + timedelta(minutes=1),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    capture = build_and_write_kis_paper_intraday_session_capture(
        runs=runs,
        cache_root=cache_root,
        repository_root=repo_root,
        observed_at=observed_at,
    )

    assert capture.outcome.status == "complete"
    qqq = next(item for item in capture.outcome.targets if item.target_key == "QQQ/NAS/1m")
    assert qqq.status == "collected"
    spy = next(item for item in capture.outcome.targets if item.target_key == "SPY/AMS/1m")
    assert spy.status == "rejected"
    assert capture.outcome.coverage.session_coverage[0].status == "short"
    assert [item.session_date for item in capture.outcome.coverage.session_coverage] == [
        date(2026, 7, 22)
    ]
    assert capture.outcome.coverage.complete_sessions == ()
    assert capture.outcome.coverage.last_reason_category == "none"
    assert capture.outcome.coverage.session_coverage[0].complete_minute_count == 239
    assert capture.outcome.coverage.session_coverage[0].missing_minute_ranges == ((239, 389),)
    current_session_cumulative_coverage = capture.outcome.current_session_cumulative_coverage
    assert [item.session_date for item in current_session_cumulative_coverage.session_coverage] == [
        date(2026, 7, 22)
    ]
    assert current_session_cumulative_coverage.complete_sessions == ()
    assert current_session_cumulative_coverage.session_coverage[0].complete_minute_count == 239
    assert current_session_cumulative_coverage.session_coverage[0].missing_minute_ranges == (
        (239, 389),
    )
    assert date(2026, 7, 23) not in [
        item.session_date for item in current_session_cumulative_coverage.session_coverage
    ]

    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_kis_paper_intraday_session_capture_evidence(
            capture.outcome,
            cache_root=repo_root,
            repository_root=repo_root,
        )


def test_session_capture_preserves_conflict_provenance_and_nonconflict_defaults(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    session = us_equity_2026_session(date(2026, 7, 22))
    assert session is not None and session.kind == "regular"
    original_rows = _session_rows(session.window.open_ts, 2)
    observed_at = session.window.close_ts + timedelta(minutes=1)
    run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page("QQQ", "NAS", original_rows),
                _page("SPY", "AMS", original_rows),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        observed_at=observed_at,
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
    runs = run_kis_paper_private_intraday_backfill_cycle(
        client=_MinuteClient(
            [
                _page("QQQ", "NAS", (changed, original_rows[1])),
                _page("SPY", "AMS", original_rows),
            ]
        ),
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=False,
        observed_at=observed_at + timedelta(minutes=1),
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )

    capture = build_and_write_kis_paper_intraday_session_capture(
        runs=runs,
        cache_root=cache_root,
        repository_root=repo_root,
        observed_at=observed_at + timedelta(minutes=1),
    )
    payload = capture.outcome.safe_payload()
    qqq = next(item for item in payload["targets"] if item["target_key"] == "QQQ/NAS/1m")
    spy = next(item for item in payload["targets"] if item["target_key"] == "SPY/AMS/1m")

    assert qqq["status"] == "rejected"
    assert qqq["reason"] == "minute_duplicate_conflict"
    assert qqq["conflict_origin"] == "retained_cache"
    assert qqq["retained_head_conflict_disposition"] == "preserved"
    assert spy["status"] == "recovered"
    assert spy["conflict_origin"] is None
    assert spy["retained_head_conflict_disposition"] == "not_applicable"


def test_session_capture_rejects_a_symlinked_evidence_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    session = us_equity_2026_session(date(2026, 7, 22))
    assert session is not None
    observed_at = session.window.close_ts + timedelta(minutes=1)
    client = _MinuteClient(
        [
            _page("QQQ", "NAS", _session_rows(session.window.open_ts, 1)),
            _page("SPY", "AMS", _session_rows(session.window.open_ts, 1)),
        ]
    )
    runs = run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        observed_at=observed_at,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    capture = build_and_write_kis_paper_intraday_session_capture(
        runs=runs,
        cache_root=cache_root,
        repository_root=repo_root,
        observed_at=observed_at,
    )
    capture.evidence_path.unlink()
    original_is_symlink = Path.is_symlink

    def is_symlink(path: Path) -> bool:
        return path == capture.evidence_path or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    with pytest.raises(ValueError, match="evidence destination is invalid"):
        write_kis_paper_intraday_session_capture_evidence(
            capture.outcome,
            cache_root=cache_root,
            repository_root=repo_root,
        )


def test_session_capture_excludes_completed_extended_session_rows_from_regular_coverage(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "market-data" / "intraday-head"
    session = us_equity_2026_session(date(2026, 7, 22))
    assert session is not None
    observed_at = session.window.close_ts + timedelta(minutes=1)
    client = _MinuteClient(
        [
            _page(
                "QQQ",
                "NAS",
                _session_rows(session.window.open_ts - timedelta(minutes=120), 120),
            ),
            _page("SPY", "AMS", _session_rows(session.window.open_ts, 2)),
        ]
    )

    runs = run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision="git:test",
        pages_per_target=1,
        resume_cursor=False,
        observed_at=observed_at,
        sleeper=lambda _seconds: None,
        monotonic_clock=lambda: 0.0,
    )
    capture = build_and_write_kis_paper_intraday_session_capture(
        runs=runs,
        cache_root=cache_root,
        repository_root=repo_root,
        observed_at=observed_at,
    )

    assert capture.outcome.status == "complete"
    assert capture.outcome.coverage.session_coverage[0].complete_minute_count == 0
    assert capture.outcome.coverage.session_coverage[0].missing_minute_ranges == ((0, 389),)


def _page(
    symbol: str,
    exchange: str,
    rows: tuple[KisPaperMinuteRawBar, ...],
) -> KisPaperMinutePage:
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange=exchange, symbol=symbol),
        bars=rows,
        next_cursor=None,
        more="",
    )


def _pages(
    symbol: str,
    exchange: str,
    rows: tuple[KisPaperMinuteRawBar, ...],
) -> tuple[KisPaperMinutePage, ...]:
    return tuple(
        KisPaperMinutePage(
            query=KisPaperMinuteQuery(exchange=exchange, symbol=symbol),
            bars=rows[index : index + KIS_PAPER_MINUTE_MAX_ROWS],
            next_cursor=("1" if index + KIS_PAPER_MINUTE_MAX_ROWS < len(rows) else None),
            more="",
        )
        for index in range(0, len(rows), KIS_PAPER_MINUTE_MAX_ROWS)
    )


def _session_rows(start: datetime, count: int) -> tuple[KisPaperMinuteRawBar, ...]:
    return tuple(_raw_bar(start + timedelta(minutes=index)) for index in range(count))


def _raw_bar(timestamp: datetime) -> KisPaperMinuteRawBar:
    korea_timestamp = timestamp.astimezone(_KOREA)
    return KisPaperMinuteRawBar(
        exchange_date=korea_timestamp.strftime("%Y%m%d"),
        exchange_time=korea_timestamp.strftime("%H%M%S"),
        korea_date=korea_timestamp.strftime("%Y%m%d"),
        korea_time=korea_timestamp.strftime("%H%M%S"),
        open=Decimal("123.45"),
        high=Decimal("124.00"),
        low=Decimal("123.00"),
        last=Decimal("123.50"),
        volume=Decimal("100"),
    )


def _retained_conflict_payload(**changes: object) -> dict[str, object]:
    return {
        "fresh_status": "collected", "fresh_reason": None,
        "accepted_row_count": 240, "accepted_page_count": 2,
        "conflicting_chunk_count": 1, "conflicting_minute_count": 1,
        "failed_predicates": ["quarantine_disabled"],
        "prospective_active_key_loss_count": 17,
    } | changes


@pytest.mark.parametrize("status", ["collected", "partial", "recovered", "rejected"])
@pytest.mark.parametrize("run_stamp,pages", [("20260728T201959Z", 4), ("20260728T202000Z", 8)])
def test_retained_conflict_capture_roundtrip_keeps_exact_receipt_chain(
    tmp_path: Path, status: str, run_stamp: str, pages: int,
) -> None:
    diagnostic = retained_head_conflict_diagnostic_from_payload(_retained_conflict_payload(
        fresh_status="partial" if status == "partial" else "collected",
        fresh_reason="minute_response_invalid" if status == "partial" else None,
        accepted_page_count=pages - 1 if status == "partial" else pages,
        failed_predicates=["quarantine_disabled"] if status == "rejected" else [],
        prospective_active_key_loss_count=0 if status == "partial" else 17,
    ))
    runs = (
        KisPaperPrivateIntradayBackfillRun(
            status=status, target_key="QQQ/NAS/1m", row_count=0 if status == "rejected" else 240,
            exact_overlap_rows=0,
            reason="minute_duplicate_conflict" if status == "rejected" else (
                "minute_response_invalid" if status == "partial" else (
                    "already_cached" if status == "recovered" else None
                )
            ),
            conflict_origin="retained_cache" if status == "rejected" else None,
            retained_head_conflict_disposition=(
                "preserved" if status == "rejected" else "not_applicable"
            ),
            retained_head_conflict_diagnostic=diagnostic,
            **({
                "failure_phase": "head_contract", "failure_code": "mixed_exchange_dates",
                "failure_page_ordinal": pages, "requested_pages_per_target": pages,
            } if status == "partial" else {}),
        ),
        KisPaperPrivateIntradayBackfillRun(
            status="collected", target_key="SPY/AMS/1m", row_count=0, exact_overlap_rows=0,
        ),
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    result = build_and_write_kis_paper_intraday_session_capture(
        runs=runs, cache_root=tmp_path / "cache", repository_root=repo,
        observed_at=datetime(2026, 7, 28, 20, 21, tzinfo=ZoneInfo("UTC")),
        schedule_run_id="intraday-head-" + run_stamp,
    )
    payload = json.loads(result.evidence_path.read_bytes())
    assert payload["targets"][0]["retained_head_conflict_diagnostic"] == diagnostic.to_payload()
    assert "retained_head_conflict_diagnostic" not in payload["targets"][1]
    digest = "sha256:" + hashlib.sha256(result.evidence_path.read_bytes()).hexdigest()
    assert result.evidence_sha256 == digest
    assert result.terminal_receipt_binding()["receipt_sha256"] == digest
    assert result.safe_output_payload()["terminal_receipt_binding"]["receipt_sha256"] == digest
    if status == "partial":
        assert payload["status"] == "incomplete"
        assert result.safe_output_payload()["status"] == "incomplete"
        target = payload["targets"][0]
        assert target["status"] == "partial"
        assert target["reason"] == "minute_response_invalid"
        assert target["failure_phase"] == "head_contract"
        assert target["failure_code"] == "mixed_exchange_dates"
        assert target["failure_page_ordinal"] == pages
        assert target["requested_pages_per_target"] == pages
        assert diagnostic.accepted_page_count == pages - 1
        assert target["row_count"] == diagnostic.accepted_row_count
        assert target["conflict_origin"] is None
        assert target["retained_head_conflict_disposition"] == "not_applicable"


@pytest.mark.parametrize("field", list(_retained_conflict_payload()))
def test_retained_conflict_payload_requires_every_field(field: str) -> None:
    value = _retained_conflict_payload()
    value.pop(field)
    with pytest.raises(ValueError, match="diagnostic is invalid"):
        retained_head_conflict_diagnostic_from_payload(value)


@pytest.mark.parametrize("field", [
    "accepted_row_count", "accepted_page_count", "conflicting_chunk_count",
    "conflicting_minute_count", "prospective_active_key_loss_count",
])
@pytest.mark.parametrize("bad", [True, 1.0, -1, "1"])
def test_retained_conflict_payload_rejects_noninteger_and_negative_counts(field, bad) -> None:
    with pytest.raises(ValueError, match="diagnostic is invalid"):
        retained_head_conflict_diagnostic_from_payload(_retained_conflict_payload(**{field: bad}))


@pytest.mark.parametrize("changes", [
    {"unexpected": "synthetic-secret"}, {"fresh_status": "Collected"},
    {"fresh_reason": "synthetic-secret"}, {"accepted_row_count": 0},
    {"conflicting_minute_count": 241}, {"failed_predicates": "quarantine_disabled"},
    {"failed_predicates": ["synthetic-secret"]},
    {"failed_predicates": ["quarantine_disabled", "quarantine_disabled"]},
    {"failed_predicates": ["quarantine_disabled", "predecessor_not_head"]},
    {"fresh_status": "partial", "fresh_reason": "unknown_reason"},
])
def test_retained_conflict_payload_rejects_open_shape_or_categories(changes) -> None:
    with pytest.raises(ValueError, match="diagnostic is invalid"):
        retained_head_conflict_diagnostic_from_payload(_retained_conflict_payload(**changes))


@pytest.mark.parametrize("value", [None, [], "synthetic-secret"])
def test_retained_conflict_payload_null_is_not_legacy_absence(value) -> None:
    with pytest.raises(ValueError, match="diagnostic is invalid"):
        retained_head_conflict_diagnostic_from_payload(value)


@pytest.mark.parametrize("diagnostic_changes,target_changes", [
    ({"fresh_reason": "auth_rejected"}, {"reason": "auth_rejected"}),
    ({}, {"reason": "auth_rejected"}),
    ({"fresh_reason": "auth_rejected"}, {}),
    ({"prospective_active_key_loss_count": 1}, {}),
    ({"failed_predicates": ["fresh_not_collected"]}, {}),
    ({"fresh_status": "collected", "fresh_reason": None}, {}),
    ({}, {"status": "recovered", "reason": "already_cached"}),
    ({}, {"conflict_origin": "retained_cache"}),
    ({}, {"row_count": 239}),
])
def test_partial_replacement_requires_exact_reason_zero_loss_and_no_failed_predicates(
    diagnostic_changes, target_changes,
) -> None:
    payload = _retained_conflict_payload(**(dict(
        fresh_status="partial", fresh_reason="minute_response_invalid",
        failed_predicates=[], prospective_active_key_loss_count=0,
    ) | diagnostic_changes))
    with pytest.raises(ValueError, match="diagnostic is invalid|session capture .*invalid"):
        diagnostic = retained_head_conflict_diagnostic_from_payload(payload)
        KisPaperIntradaySessionCaptureTarget(**(dict(
            target_key="QQQ/NAS/1m", status="partial", row_count=240, exact_overlap_rows=0,
            reason="minute_response_invalid", retained_head_conflict_diagnostic=diagnostic,
        ) | target_changes))


@pytest.mark.parametrize("stamp,pages", [("20260728T201959Z", 5), ("20260728T202000Z", 9)])
def test_partial_replacement_cannot_exceed_invocation_page_budget(tmp_path, stamp, pages) -> None:
    diagnostic = retained_head_conflict_diagnostic_from_payload(_retained_conflict_payload(
        fresh_status="partial", fresh_reason="minute_response_invalid",
        failed_predicates=[], prospective_active_key_loss_count=0, accepted_page_count=pages,
    ))
    runs = tuple(KisPaperPrivateIntradayBackfillRun(
        status="partial", target_key=key, row_count=240, exact_overlap_rows=0,
        reason="minute_response_invalid", retained_head_conflict_diagnostic=diagnostic,
    ) for key in ("QQQ/NAS/1m", "SPY/AMS/1m"))
    with pytest.raises(ValueError, match="retained conflict diagnostic is invalid"):
        build_and_write_kis_paper_intraday_session_capture(
            runs=runs, cache_root=tmp_path / "cache", repository_root=tmp_path / "repo",
            observed_at=datetime(2026, 7, 28, 20, 21, tzinfo=ZoneInfo("UTC")),
            schedule_run_id="intraday-head-" + stamp,
        )


@pytest.mark.parametrize("changes", [
    {"status": "partial"}, {"status": "locked"}, {"conflict_origin": "candidate_batch"},
    {"reason": "minute_response_invalid"}, {"row_count": 1}, {"exact_overlap_rows": 1},
    {"retained_head_conflict_disposition": "not_applicable"},
])
def test_retained_conflict_capture_binds_target_outcome_and_provenance(changes) -> None:
    fields = dict(
        target_key="QQQ/NAS/1m", status="rejected", row_count=0, exact_overlap_rows=0,
        reason="minute_duplicate_conflict", conflict_origin="retained_cache",
        retained_head_conflict_disposition="preserved",
        retained_head_conflict_diagnostic=retained_head_conflict_diagnostic_from_payload(
            _retained_conflict_payload()
        ),
    ) | changes
    with pytest.raises(ValueError, match="session capture .*invalid"):
        KisPaperIntradaySessionCaptureTarget(**fields)


@pytest.mark.parametrize("stamp,pages,rows,valid", [
    ("20260728T201959Z", 4, 480, True), ("20260728T201959Z", 5, 480, False),
    ("20260728T202000Z", 8, 960, True), ("20260728T202000Z", 9, 960, False),
    ("20260728T201959Z", 4, 481, False),
])
def test_retained_conflict_capture_limits_actual_page_and_row_budget(
    tmp_path, stamp, pages, rows, valid,
) -> None:
    diagnostic = retained_head_conflict_diagnostic_from_payload(_retained_conflict_payload(
        fresh_status="partial", fresh_reason="minute_response_invalid",
        accepted_page_count=pages, accepted_row_count=rows,
        failed_predicates=["fresh_not_collected"],
    ))
    runs = tuple(KisPaperPrivateIntradayBackfillRun(
        status="rejected", target_key=key, row_count=0, exact_overlap_rows=0,
        reason="minute_duplicate_conflict", conflict_origin="retained_cache",
        retained_head_conflict_disposition="preserved",
        retained_head_conflict_diagnostic=diagnostic,
    ) for key in ("QQQ/NAS/1m", "SPY/AMS/1m"))
    kwargs = dict(
        runs=runs, cache_root=tmp_path / "cache", repository_root=tmp_path / "repo",
        observed_at=datetime(2026, 7, 28, 20, 21, tzinfo=ZoneInfo("UTC")),
        schedule_run_id="intraday-head-" + stamp,
    )
    if valid:
        result = build_and_write_kis_paper_intraday_session_capture(**kwargs)
        assert result.outcome.targets[0].retained_head_conflict_diagnostic == diagnostic
    else:
        with pytest.raises(ValueError, match="retained conflict diagnostic is invalid"):
            build_and_write_kis_paper_intraday_session_capture(**kwargs)
        assert not kwargs["cache_root"].exists()
