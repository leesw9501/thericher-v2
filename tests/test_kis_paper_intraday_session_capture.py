from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.data.kis_paper_intraday_session_capture import (
    build_and_write_kis_paper_intraday_session_capture,
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
    run_kis_paper_private_intraday_backfill_cycle,
)

_KOREA = ZoneInfo("Asia/Seoul")


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
    assert cumulative_coverage["regular_session_coverage"] == coverage[
        "regular_session_coverage"
    ]
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
    assert [
        item.session_date for item in current_session_cumulative_coverage.session_coverage
    ] == [date(2026, 7, 22)]
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
