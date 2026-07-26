from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.data.kis_paper_minute_capability_probe import (
    run_kis_paper_minute_capability_probe,
    write_kis_paper_minute_capability_probe_evidence,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)


class _MinuteClient:
    def __init__(self, responses: list[KisPaperMinutePage | BaseException]) -> None:
        self._responses = list(responses)
        self._token_attempts = 0
        self._minute_page_attempts = 0
        self.queries: list[KisPaperMinuteQuery] = []

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts:
        return KisPaperMarketDataCallCounts(
            token_attempts=self._token_attempts,
            minute_page_attempts=self._minute_page_attempts,
            daily_page_attempts=0,
        )

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: object | None = None,
    ) -> KisPaperMinutePage:
        self.queries.append(query)
        if self._token_attempts == 0:
            self._token_attempts = 1
        self._minute_page_attempts += 1
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def test_probe_discards_raw_bars_and_records_single_client_cursor_chain() -> None:
    start = datetime(2026, 7, 24, 9, 29, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page((start + timedelta(minutes=3), start + timedelta(minutes=2)), "1"),
            _page((start + timedelta(minutes=2), start + timedelta(minutes=1)), "1"),
            _page((start + timedelta(minutes=1), start), None),
        ]
    )
    request_starts = tuple(
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC) + timedelta(seconds=1.25 * index)
        for index in range(4)
    )

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=request_starts,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 4.0),
    )

    assert outcome.status == "complete"
    assert outcome.accepted_page_count == 3
    assert outcome.continuation_category == "terminal"
    assert outcome.probe_pattern_category == "cursor_chain"
    assert outcome.historical_range_category == "single_exchange_date"
    assert outcome.minute_spacing_category == "contiguous_after_deduplication"
    assert outcome.token_reuse_category == "single_token_reused"
    assert outcome.request_start_category == "at_or_below_existing_gate"
    assert outcome.calibration_fact == "single_client_cursor_chain_under_existing_gate"
    assert client.queries[1].continuation_next == "1"
    assert client.queries[1].continuation_key == "20260724093000"
    assert client.queries[2].continuation_key == "20260724092900"

    serialized = json.dumps(outcome.safe_payload(), sort_keys=True)
    assert "12345.67" not in serialized
    assert "20260724" not in serialized
    assert "access_token" not in serialized


def test_probe_repeats_one_terminal_head_to_measure_token_reuse_and_request_spacing() -> None:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page((start + timedelta(minutes=1), start), None),
            _page((start + timedelta(minutes=1), start), None),
        ]
    )
    request_starts = tuple(
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC) + timedelta(seconds=1.25 * index)
        for index in range(3)
    )

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=request_starts,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 3.0),
    )

    assert outcome.status == "complete"
    assert outcome.accepted_page_count == 2
    assert outcome.continuation_category == "terminal"
    assert outcome.probe_pattern_category == "terminal_head_repeat"
    assert outcome.token_reuse_category == "single_token_reused"
    assert outcome.request_start_category == "at_or_below_existing_gate"
    assert outcome.calibration_fact == "single_client_terminal_head_reuse_under_existing_gate"
    assert all(query.continuation_next is None for query in client.queries)


def test_probe_records_partial_continuation_failure_without_retaining_rows() -> None:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page((start + timedelta(minutes=1), start), "1"),
            KisPaperMarketDataError("rate_limited"),
        ]
    )

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(),
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 5.0),
    )

    assert outcome.status == "partial"
    assert outcome.response_class == "rate_limited"
    assert outcome.continuation_category == "continuation_failed"
    assert outcome.request_start_category == "timestamps_incomplete"
    assert outcome.safe_payload()["raw_market_data_retained"] is False


def test_probe_evidence_stays_outside_repository_and_is_source_safe(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    client = _MinuteClient([_page((datetime(2026, 7, 24, 9, 30, tzinfo=UTC),), None)])
    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(datetime(2026, 7, 24, 12, 0, tzinfo=UTC),) * 2,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        repeat_terminal_head_once=False,
        monotonic_clock=_monotonic(0.0, 0.1),
    )

    path = write_kis_paper_minute_capability_probe_evidence(
        outcome,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert path.is_relative_to(artifact_root)
    assert json.loads(path.read_text(encoding="utf-8")) == outcome.safe_payload()
    assert "12345.67" not in path.read_text(encoding="utf-8")


def _page(
    timestamps: tuple[datetime, ...],
    next_cursor: str | None,
) -> KisPaperMinutePage:
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"),
        bars=tuple(_bar(timestamp) for timestamp in timestamps),
        next_cursor=next_cursor,
        more="",
    )


def _bar(timestamp: datetime) -> KisPaperMinuteRawBar:
    return KisPaperMinuteRawBar(
        exchange_date=timestamp.strftime("%Y%m%d"),
        exchange_time=timestamp.strftime("%H%M%S"),
        korea_date=timestamp.strftime("%Y%m%d"),
        korea_time=timestamp.strftime("%H%M%S"),
        open=Decimal("12345.67"),
        high=Decimal("12345.68"),
        low=Decimal("12345.66"),
        last=Decimal("12345.67"),
        volume=Decimal("123"),
    )


def _monotonic(*values: float):
    iterator = iter(values)
    return lambda: next(iterator)
