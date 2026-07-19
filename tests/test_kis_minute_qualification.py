from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution import kis_minute_qualification
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperMarketDataConfig,
    KisPaperMinuteCallCounts,
    KisPaperMinuteClient,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_minute_qualification import (
    KIS_PAPER_MINUTE_QUALIFICATION_SESSION_DATE,
    KisPaperMinuteQualificationEvidence,
    KisPaperMinuteQualificationFacts,
    KisPaperMinuteQualificationFailure,
    assess_kis_paper_minute_qualification,
    is_kis_paper_minute_qualification_window,
    kis_paper_minute_qualification_attempt_is_reserved,
    mark_kis_paper_minute_qualification_network_started,
    mark_kis_paper_minute_qualification_summary_written,
    reserve_kis_paper_minute_qualification_attempt,
    run_bounded_kis_paper_minute_qualification,
    sanitized_kis_paper_minute_failure_summary,
    sanitized_kis_paper_minute_qualification_summary,
    write_kis_paper_minute_qualification_summary,
)

_NEW_YORK = ZoneInfo("America/New_York")
_SEOUL = ZoneInfo("Asia/Seoul")
_PROBE_START = datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC)
_PROBE_END = datetime(2026, 7, 20, 17, 30, 57, tzinfo=UTC)


class _RecordingTransport:
    def __init__(self, responses: list[KisMarketDataResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[KisMarketDataRequest] = []

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def test_bounded_probe_requires_one_token_two_pages_and_produces_metadata_only() -> None:
    first_rows = _rows(_PROBE_START.replace(second=0), 120)
    second_rows = _rows(_PROBE_START.replace(second=0) - timedelta(minutes=120), 120)
    transport = _RecordingTransport(
        [
            KisMarketDataResponse.from_payload({"access_token": "test-token"}),
            KisMarketDataResponse.from_payload(_page_payload(first_rows)),
            KisMarketDataResponse.from_payload(_page_payload(second_rows)),
        ]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )
    clock = _clock(
        _PROBE_START,
        _PROBE_START + timedelta(seconds=1),
        _PROBE_START + timedelta(seconds=2),
        _PROBE_END,
    )

    evidence = run_bounded_kis_paper_minute_qualification(client, clock=clock)

    assert evidence.facts.all_runtime_facts_passed is True
    assert evidence.call_counts == KisPaperMinuteCallCounts(1, 2)
    assert evidence.first_page_row_count == 120
    assert evidence.continuation_page_row_count == 120
    assert evidence.exact_overlap_count == 0
    assert evidence.facts.continuation_has_no_overlap is True
    assert evidence.facts.continuation_boundary_is_contiguous is True
    assert evidence.facts.probe_window_valid is True
    assert evidence.excluded_current_or_future_row_count == 1
    assert evidence.newest_completed_end == _PROBE_START.replace(second=0)
    assert [request.method for request in transport.requests] == ["POST", "GET", "GET"]
    assert [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL) for request in transport.requests
    ] == [KIS_PAPER_TOKEN_PATH, KIS_PAPER_MINUTE_PATH, KIS_PAPER_MINUTE_PATH]
    assert transport.requests[1].query["PINC"] == "0"
    assert transport.requests[2].query["PINC"] == "1"
    assert transport.requests[2].query["KEYB"] == "20260720113000"

    summary = sanitized_kis_paper_minute_qualification_summary(evidence)
    rendered = json.dumps(summary, sort_keys=True)
    assert summary["status"] == "observed"
    assert summary["promotion"] == "not_available_from_one_shot_probe"
    assert (
        summary["session_gate"]["local_date"]
        == KIS_PAPER_MINUTE_QUALIFICATION_SESSION_DATE.isoformat()
    )
    assert summary["storage"]["raw_market_data_retained"] is False
    assert "123.45" not in rendered
    assert '"open":' not in rendered
    assert "paper-key" not in rendered
    assert "test-token" not in rendered
    assert summary["observation"]["continuation_exchange_timestamp_bounds_utc"] == {
        "newest": "2026-07-20T15:30:00Z",
        "oldest": "2026-07-20T13:31:00Z",
    }


def test_qualification_rejects_nonmatching_overlap_without_retaining_rows() -> None:
    first = _page(_rows(_PROBE_START.replace(second=0), 120))
    conflicting_rows = _rows(_PROBE_START.replace(second=0) - timedelta(minutes=119), 120)
    conflicting_rows[0] = KisPaperMinuteRawBar(
        exchange_date=conflicting_rows[0].exchange_date,
        exchange_time=conflicting_rows[0].exchange_time,
        korea_date=conflicting_rows[0].korea_date,
        korea_time=conflicting_rows[0].korea_time,
        open=Decimal("123.46"),
        high=Decimal("124"),
        low=Decimal("123"),
        last=Decimal("123.50"),
        volume=Decimal("1000"),
    )
    evidence = assess_kis_paper_minute_qualification(
        first_page=first,
        continuation_page=_continuation_page(first, conflicting_rows),
        observed_at_start=_PROBE_START,
        observed_at_end=_PROBE_END,
        call_counts=KisPaperMinuteCallCounts(1, 2),
    )

    assert evidence.facts.continuation_has_no_overlap is False
    assert evidence.facts.continuation_boundary_is_contiguous is False
    assert evidence.facts.conflicting_overlap_count == 1
    assert sanitized_kis_paper_minute_qualification_summary(evidence)["status"] == "observed"


@pytest.mark.parametrize(
    ("first_rows", "failed_fact"),
    (
        (
            lambda rows: [
                replace(rows[0], korea_time="063000"),
                *rows[1:],
            ],
            "exchange_and_korea_map_to_same_utc",
        ),
        (
            lambda rows: [rows[1], rows[0], *rows[2:]],
            "first_page_descends_one_minute",
        ),
    ),
)
def test_qualification_records_timestamp_corruption_as_metadata_only(
    first_rows: Callable[[list[KisPaperMinuteRawBar]], list[KisPaperMinuteRawBar]],
    failed_fact: str,
) -> None:
    rows = _rows(_PROBE_START.replace(second=0), 120)
    first = _page(first_rows(rows))
    evidence = assess_kis_paper_minute_qualification(
        first_page=first,
        continuation_page=_continuation_page(
            first,
            _rows(_PROBE_START.replace(second=0) - timedelta(minutes=120), 120),
        ),
        observed_at_start=_PROBE_START,
        observed_at_end=_PROBE_END,
        call_counts=KisPaperMinuteCallCounts(1, 2),
    )

    summary = sanitized_kis_paper_minute_qualification_summary(evidence)
    rendered = json.dumps(summary, sort_keys=True)
    assert summary["predeclared_facts"][failed_fact] is False
    assert summary["predeclared_facts"]["all_runtime_facts_passed"] is False
    assert "123.45" not in rendered
    assert '"open":' not in rendered


def test_qualification_rejects_an_identical_duplicate_boundary_row() -> None:
    first = _page(_rows(_PROBE_START.replace(second=0), 120))
    evidence = assess_kis_paper_minute_qualification(
        first_page=first,
        continuation_page=_continuation_page(
            first,
            _rows(_PROBE_START.replace(second=0) - timedelta(minutes=119), 120)
        ),
        observed_at_start=_PROBE_START,
        observed_at_end=_PROBE_END,
        call_counts=KisPaperMinuteCallCounts(1, 2),
    )

    assert evidence.facts.continuation_has_no_overlap is False
    assert evidence.facts.continuation_boundary_is_contiguous is False
    assert evidence.exact_overlap_count == 1
    assert evidence.facts.conflicting_overlap_count == 0


def test_runtime_facts_do_not_promote_a_one_shot_probe() -> None:
    first = _page(_rows(_PROBE_START.replace(second=0), 120))
    evidence = assess_kis_paper_minute_qualification(
        first_page=first,
        continuation_page=_continuation_page(
            first,
            _rows(_PROBE_START.replace(second=0) - timedelta(minutes=120), 120)
        ),
        observed_at_start=_PROBE_START,
        observed_at_end=_PROBE_END,
        call_counts=KisPaperMinuteCallCounts(1, 2),
    )

    assert evidence.facts.all_runtime_facts_passed
    summary = sanitized_kis_paper_minute_qualification_summary(evidence)
    assert summary["status"] == "observed"
    assert summary["promotion"] == "not_available_from_one_shot_probe"


def test_qualification_rejects_a_gapped_continuation_even_without_overlap() -> None:
    first = _page(_rows(_PROBE_START.replace(second=0), 120))
    evidence = assess_kis_paper_minute_qualification(
        first_page=first,
        continuation_page=_continuation_page(
            first,
            _rows(_PROBE_START.replace(second=0) - timedelta(minutes=121), 120)
        ),
        observed_at_start=_PROBE_START,
        observed_at_end=_PROBE_END,
        call_counts=KisPaperMinuteCallCounts(1, 2),
    )

    assert evidence.facts.continuation_has_no_overlap is True
    assert evidence.facts.continuation_boundary_is_contiguous is False


def test_qualification_rejects_a_fabricated_continuation_query() -> None:
    with pytest.raises(ValueError, match="continuation_contract_invalid"):
        assess_kis_paper_minute_qualification(
            first_page=_page(_rows(_PROBE_START.replace(second=0), 120)),
            continuation_page=_page(
                _rows(_PROBE_START.replace(second=0) - timedelta(minutes=120), 120)
            ),
            observed_at_start=_PROBE_START,
            observed_at_end=_PROBE_END,
            call_counts=KisPaperMinuteCallCounts(1, 2),
        )


def test_window_rejects_non_session_and_non_boundary_times() -> None:
    assert is_kis_paper_minute_qualification_window(_PROBE_START)
    assert not is_kis_paper_minute_qualification_window(_PROBE_START + timedelta(minutes=1))
    assert not is_kis_paper_minute_qualification_window(
        datetime(2026, 7, 19, 17, 30, 20, tzinfo=UTC)
    )
    assert not is_kis_paper_minute_qualification_window(
        datetime(2026, 7, 21, 17, 30, 20, tzinfo=UTC)
    )


def test_probe_rejects_a_slow_completion_but_not_ordinary_completion_seconds() -> None:
    first = _page(_rows(_PROBE_START.replace(second=0), 120))
    continuation = _continuation_page(
        first,
        _rows(_PROBE_START.replace(second=0) - timedelta(minutes=120), 120),
    )

    ordinary = assess_kis_paper_minute_qualification(
        first_page=first,
        continuation_page=continuation,
        observed_at_start=_PROBE_START,
        observed_at_end=_PROBE_END,
        call_counts=KisPaperMinuteCallCounts(1, 2),
    )
    slow = assess_kis_paper_minute_qualification(
        first_page=first,
        continuation_page=continuation,
        observed_at_start=_PROBE_START,
        observed_at_end=_PROBE_START + timedelta(minutes=2, seconds=1),
        call_counts=KisPaperMinuteCallCounts(1, 2),
    )

    assert ordinary.facts.probe_window_valid is True
    assert slow.facts.probe_window_valid is False


def test_bounded_probe_refuses_outside_window_before_any_transport_request() -> None:
    transport = _RecordingTransport([])
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    with pytest.raises(ValueError, match="qualification_window_closed"):
        run_bounded_kis_paper_minute_qualification(
            client,
            clock=lambda: datetime(2026, 7, 19, 17, 30, 20, tzinfo=UTC),
        )

    assert transport.requests == []
    assert client.call_counts == KisPaperMinuteCallCounts(0, 0)


def test_bounded_probe_rechecks_the_window_immediately_before_the_first_request() -> None:
    transport = _RecordingTransport([])
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    with pytest.raises(ValueError, match="window_recheck_closed"):
        run_bounded_kis_paper_minute_qualification(
            client,
            clock=_clock(
                _PROBE_START,
                _PROBE_START + timedelta(minutes=1),
            ),
        )

    assert transport.requests == []
    assert client.call_counts == KisPaperMinuteCallCounts(0, 0)


def test_bounded_probe_skips_continuation_after_the_narrow_envelope_closes() -> None:
    first_rows = _rows(_PROBE_START.replace(second=0), 120)
    transport = _RecordingTransport(
        [
            KisMarketDataResponse.from_payload({"access_token": "test-token"}),
            KisMarketDataResponse.from_payload(_page_payload(first_rows)),
        ]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    evidence = run_bounded_kis_paper_minute_qualification(
        client,
        clock=_clock(
            _PROBE_START,
            _PROBE_START + timedelta(seconds=1),
            _PROBE_START + timedelta(minutes=2, seconds=2),
        ),
    )

    assert evidence.call_counts == KisPaperMinuteCallCounts(1, 1)
    assert evidence.continuation_available is True
    assert evidence.continuation_requested is False
    assert evidence.facts.probe_window_valid is False
    assert [request.method for request in transport.requests] == ["POST", "GET"]


def test_writer_rejects_git_artifact_path_and_failure_summary_stays_sanitized(
    tmp_path: Path,
) -> None:
    failure = KisPaperMinuteQualificationFailure(
        observed_at=_PROBE_START,
        call_counts=KisPaperMinuteCallCounts(1, 0),
        reason="https://secret.example/?token=not-allowed",
    )
    rendered = json.dumps(
        sanitized_kis_paper_minute_failure_summary(
            observed_at=failure.observed_at,
            call_counts=failure.call_counts,
            reason=failure.reason,
        ),
        sort_keys=True,
    )
    assert "secret.example" not in rendered
    assert failure.reason == "unexpected_probe_error"

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        write_kis_paper_minute_qualification_summary(
            result=failure,
            artifact_root=repo_root / "artifacts",
            run_id="20260720T173020Z",
            repo_root=repo_root,
        )
    assert not (repo_root / "artifacts").exists()

    path, digest = write_kis_paper_minute_qualification_summary(
        result=failure,
        artifact_root=tmp_path / "external",
        run_id="20260720T173020Z",
        repo_root=repo_root,
    )
    assert path.exists()
    assert digest.startswith("sha256:")
    assert "unexpected_probe_error" in path.read_text(encoding="utf-8")

    with pytest.raises(TypeError, match="typed evidence or failure"):
        write_kis_paper_minute_qualification_summary(
            result={"open": "123.45", "raw_rows": ["must-not-persist"]},
            artifact_root=tmp_path / "outside",
            run_id="20260720T173021Z",
            repo_root=repo_root,
        )
    assert not (tmp_path / "outside").exists()


def test_one_shot_reservation_records_recoverable_lifecycle_state(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "external-control"
    marker = reserve_kis_paper_minute_qualification_attempt(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_PROBE_START,
    )

    assert kis_paper_minute_qualification_attempt_is_reserved(
        control_root=control_root,
        repo_root=repo_root,
    )
    reserved = json.loads(marker.read_text(encoding="utf-8"))
    assert reserved["phase"] == "reserved"
    assert reserved["raw_market_data_retained"] is False
    mark_kis_paper_minute_qualification_network_started(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_PROBE_START,
    )
    assert json.loads(marker.read_text(encoding="utf-8"))["phase"] == "network_started"
    mark_kis_paper_minute_qualification_summary_written(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_PROBE_END,
        summary_hash="sha256:unit",
        result_status="observed",
    )
    completed = json.loads(marker.read_text(encoding="utf-8"))
    assert completed["phase"] == "summary_written"
    assert completed["result_status"] == "observed"
    with pytest.raises(ValueError, match="already_reserved"):
        reserve_kis_paper_minute_qualification_attempt(
            control_root=control_root,
            repo_root=repo_root,
            observed_at=_PROBE_END,
        )


def test_reservation_and_lifecycle_transitions_sync_the_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "external-control"
    synced_descriptors: list[int] = []
    monkeypatch.setattr(
        kis_minute_qualification.os,
        "fsync",
        lambda descriptor: synced_descriptors.append(descriptor),
    )

    reserve_kis_paper_minute_qualification_attempt(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_PROBE_START,
    )
    mark_kis_paper_minute_qualification_network_started(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_PROBE_START,
    )

    assert len(synced_descriptors) >= 3


def test_reservation_rejects_a_child_symlink_that_points_into_git(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "external-control"
    control_root.mkdir()
    reservations = control_root / "reservations"
    try:
        reservations.symlink_to(repo_root, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink is unavailable on this host")

    with pytest.raises(ValueError, match="reservation_marker_invalid"):
        reserve_kis_paper_minute_qualification_attempt(
            control_root=control_root,
            repo_root=repo_root,
            observed_at=_PROBE_START,
        )
    assert not list(repo_root.iterdir())


def test_control_ledger_blocks_retry_even_if_the_marker_snapshot_disappears(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "external-control"
    marker = reserve_kis_paper_minute_qualification_attempt(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=_PROBE_START,
    )

    marker.unlink()

    assert kis_paper_minute_qualification_attempt_is_reserved(
        control_root=control_root,
        repo_root=repo_root,
    )
    with pytest.raises(ValueError, match="already_reserved"):
        reserve_kis_paper_minute_qualification_attempt(
            control_root=control_root,
            repo_root=repo_root,
            observed_at=_PROBE_END,
        )


def test_summary_writer_revalidates_scope_and_call_counts_before_persisting(tmp_path: Path) -> None:
    evidence = _sanitizable_evidence()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    object.__setattr__(evidence, "exchange", "token-secret-must-not-persist")
    with pytest.raises(ValueError, match="scope"):
        write_kis_paper_minute_qualification_summary(
            result=evidence,
            artifact_root=tmp_path / "external-a",
            run_id="20260720T173020Z",
            repo_root=repo_root,
        )
    assert not (tmp_path / "external-a").exists()

    evidence = _sanitizable_evidence()
    object.__setattr__(evidence, "call_counts", KisPaperMinuteCallCounts(2, 3))
    with pytest.raises(ValueError, match="call counts"):
        write_kis_paper_minute_qualification_summary(
            result=evidence,
            artifact_root=tmp_path / "external-b",
            run_id="20260720T173021Z",
            repo_root=repo_root,
        )
    assert not (tmp_path / "external-b").exists()


def _clock(*values: datetime):
    iterator: Iterator[datetime] = iter(values)
    return lambda: next(iterator)


def _page(rows: list[KisPaperMinuteRawBar]) -> KisPaperMinutePage:
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"),
        bars=tuple(rows),
        next_cursor="1",
        more="0",
    )


def _continuation_page(
    first_page: KisPaperMinutePage,
    rows: list[KisPaperMinuteRawBar],
) -> KisPaperMinutePage:
    oldest = first_page.bars[-1]
    exchange_local = datetime.strptime(
        f"{oldest.exchange_date}{oldest.exchange_time}", "%Y%m%d%H%M%S"
    ).replace(tzinfo=_NEW_YORK)
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(
            exchange="NAS",
            symbol="QQQ",
            continuation_next=first_page.next_cursor or "missing",
            continuation_key=(exchange_local - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S"),
        ),
        bars=tuple(rows),
        next_cursor="1",
        more="0",
    )


def _page_payload(rows: list[KisPaperMinuteRawBar]) -> dict[str, object]:
    return {
        "rt_cd": "0",
        "output1": {"next": "1", "more": "0"},
        "output2": [
            {
                "xymd": row.exchange_date,
                "xhms": row.exchange_time,
                "kymd": row.korea_date,
                "khms": row.korea_time,
                "open": str(row.open),
                "high": str(row.high),
                "low": str(row.low),
                "last": str(row.last),
                "evol": str(row.volume),
            }
            for row in rows
        ],
    }


def _rows(newest: datetime, count: int) -> list[KisPaperMinuteRawBar]:
    result: list[KisPaperMinuteRawBar] = []
    for index in range(count):
        timestamp = newest - timedelta(minutes=index)
        exchange = timestamp.astimezone(_NEW_YORK)
        korea = timestamp.astimezone(_SEOUL)
        result.append(
            KisPaperMinuteRawBar(
                exchange_date=exchange.strftime("%Y%m%d"),
                exchange_time=exchange.strftime("%H%M%S"),
                korea_date=korea.strftime("%Y%m%d"),
                korea_time=korea.strftime("%H%M%S"),
                open=Decimal("123.45"),
                high=Decimal("124"),
                low=Decimal("123"),
                last=Decimal("123.50"),
                volume=Decimal("1000"),
            )
        )
    return result


def _sanitizable_evidence() -> KisPaperMinuteQualificationEvidence:
    newest = _PROBE_START.replace(second=0)
    return KisPaperMinuteQualificationEvidence(
        observed_at_start=_PROBE_START,
        observed_at_end=_PROBE_END,
        exchange="NAS",
        symbol="QQQ",
        call_counts=KisPaperMinuteCallCounts(1, 2),
        first_page_row_count=120,
        continuation_page_row_count=120,
        continuation_available=True,
        continuation_requested=True,
        first_exchange_newest=newest,
        first_exchange_oldest=newest - timedelta(minutes=119),
        first_korea_newest=newest,
        first_korea_oldest=newest - timedelta(minutes=119),
        continuation_exchange_newest=newest - timedelta(minutes=120),
        continuation_exchange_oldest=newest - timedelta(minutes=239),
        continuation_korea_newest=newest - timedelta(minutes=120),
        continuation_korea_oldest=newest - timedelta(minutes=239),
        exact_overlap_count=0,
        excluded_current_or_future_row_count=1,
        newest_completed_end=newest,
        facts=KisPaperMinuteQualificationFacts(
            probe_window_valid=True,
            first_page_descends_one_minute=True,
            continuation_page_descends_one_minute=True,
            exchange_and_korea_map_to_same_utc=True,
            continuation_has_no_overlap=True,
            continuation_boundary_is_contiguous=True,
            conflicting_overlap_count=0,
            current_minute_row_observed=True,
            current_minute_row_excluded=True,
            completed_bars_available=True,
            completed_window_fresh=True,
            baseline_boundary_aligned=True,
        ),
    )
