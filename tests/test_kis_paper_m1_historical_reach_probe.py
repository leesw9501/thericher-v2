from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data.kis_paper_m1_historical_reach_probe import (
    KIS_PAPER_M1_HISTORICAL_REACH_ARTIFACT_DIRECTORY,
    KIS_PAPER_M1_HISTORICAL_REACH_TARGETS,
    run_kis_paper_m1_historical_reach_probe,
    write_kis_paper_m1_historical_reach_evidence,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)


class _MinuteClient:
    def __init__(
        self,
        responses: list[object],
        request_start_times: list[datetime],
    ) -> None:
        self._responses = list(responses)
        self._request_start_times = request_start_times
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

    def fetch_minute_page(self, query: KisPaperMinuteQuery) -> KisPaperMinutePage:
        self.queries.append(query)
        if self._token_attempts == 0:
            self._token_attempts = 1
            self._request_start_times.append(
                datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
                + timedelta(seconds=len(self._request_start_times))
            )
        self._minute_page_attempts += 1
        self._request_start_times.append(
            datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
            + timedelta(seconds=len(self._request_start_times))
        )
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response  # type: ignore[return-value]


def test_probe_uses_one_client_and_keeps_target_counts_isolated() -> None:
    request_start_times: list[datetime] = []
    qqq_start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    spy_start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page(
                "QQQ",
                "NAS",
                (qqq_start + timedelta(minutes=2), qqq_start + timedelta(minutes=1)),
                "1",
            ),
            _page("QQQ", "NAS", (qqq_start, qqq_start - timedelta(minutes=1)), None),
            _page("SPY", "AMS", (spy_start + timedelta(minutes=1), spy_start), None),
        ],
        request_start_times,
    )

    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        tested_request_interval_seconds=1.0,
        monotonic_clock=_monotonic(0.0, 0.1, 0.2, 0.3),
    )

    assert tuple(outcome.target_key for outcome in outcomes) == ("QQQ/NAS/1m", "SPY/AMS/1m")
    assert outcomes[0].status == "complete"
    assert outcomes[0].accepted_page_count == 2
    assert outcomes[0].continuation_category == "terminal"
    assert outcomes[0].cursor_progress_category == "strictly_backward_nonoverlapping"
    assert outcomes[0].token_request_count == 1
    assert outcomes[0].minute_page_request_count == 2
    assert outcomes[0].token_context_category == "issued_for_shared_client"
    assert outcomes[0].request_start_category == "at_or_below_existing_gate"
    assert outcomes[1].status == "complete"
    assert outcomes[1].accepted_page_count == 1
    assert outcomes[1].token_request_count == 0
    assert outcomes[1].minute_page_request_count == 1
    assert outcomes[1].token_context_category == "reused_shared_client_token"
    assert outcomes[1].request_start_category == "single_get"
    assert len(client.queries) == 3
    assert [(query.symbol, query.exchange) for query in client.queries] == [
        ("QQQ", "NAS"),
        ("QQQ", "NAS"),
        ("SPY", "AMS"),
    ]
    assert client.queries[1].continuation_next == "1"
    assert client.queries[1].continuation_key == "20260724093000"


def test_probe_uses_explicit_previous_day_scope_on_each_fixed_first_request() -> None:
    request_start_times: list[datetime] = []
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page("QQQ", "NAS", (start,), None),
            _page("SPY", "AMS", (start,), None),
        ],
        request_start_times,
    )

    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        include_previous_day=True,
        monotonic_clock=_monotonic(0.0, 0.1, 0.2, 0.3),
    )

    assert [query.include_previous_day for query in client.queries] == [True, True]
    assert [outcome.request_scope for outcome in outcomes] == [
        "current_and_previous_day",
        "current_and_previous_day",
    ]


def test_probe_enforces_the_two_page_budget_and_closes_duplicate_cursor_progress() -> None:
    request_start_times: list[datetime] = []
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page("QQQ", "NAS", (start + timedelta(minutes=2), start + timedelta(minutes=1)), "1"),
            _page("QQQ", "NAS", (start + timedelta(minutes=2), start + timedelta(minutes=1)), "1"),
            _page("SPY", "AMS", (start + timedelta(minutes=1), start), "1"),
            _page("SPY", "AMS", (start - timedelta(minutes=1), start - timedelta(minutes=2)), "1"),
        ],
        request_start_times,
    )

    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 0.1, 0.2, 0.3),
    )

    assert len(client.queries) == 4
    assert outcomes[0].status == "partial"
    assert outcomes[0].accepted_page_count == 2
    assert outcomes[0].continuation_category == "duplicate_conflict"
    assert outcomes[0].response_class == "duplicate_conflict"
    assert outcomes[0].cursor_progress_category == "duplicate_or_not_older"
    assert outcomes[1].accepted_page_count == 2
    assert outcomes[1].continuation_category == "available_at_probe_cap"
    assert outcomes[1].cursor_progress_category == "strictly_backward_nonoverlapping"


def test_probe_rejects_a_provider_target_mismatch_without_contaminating_the_next_target() -> None:
    request_start_times: list[datetime] = []
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page("SPY", "AMS", (start,), None),
            _page("SPY", "AMS", (start,), None),
        ],
        request_start_times,
    )

    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 0.1, 0.2, 0.3),
    )

    assert outcomes[0].status == "unavailable"
    assert outcomes[0].response_class == "minute_target_mismatch"
    assert outcomes[0].accepted_page_count == 0
    assert outcomes[1].status == "complete"
    assert outcomes[1].target_key == "SPY/AMS/1m"


def test_probe_records_shared_cooldown_without_retrying_the_second_target() -> None:
    request_start_times: list[datetime] = []
    client = _MinuteClient(
        [KisPaperMarketDataError("rate_limited")],
        request_start_times,
    )

    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 0.1),
    )

    assert len(client.queries) == 1
    assert outcomes[0].status == "unavailable"
    assert outcomes[0].next_due == "provider_rate_limit_backoff"
    assert outcomes[1].status == "skipped"
    assert outcomes[1].continuation_category == "skipped"
    assert outcomes[1].next_due == "provider_rate_limit_backoff"


def test_probe_closes_an_empty_page_as_a_categorical_unavailable_outcome() -> None:
    request_start_times: list[datetime] = []
    empty_page = SimpleNamespace(
        query=KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"),
        bars=(),
        next_cursor=None,
        continuation_signal="blank_or_absent",
    )
    client = _MinuteClient(
        [
            empty_page,
            _page("SPY", "AMS", (datetime(2026, 7, 24, 9, 30, tzinfo=UTC),), None),
        ],
        request_start_times,
    )

    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 0.1, 0.2, 0.3),
    )

    assert outcomes[0].status == "unavailable"
    assert outcomes[0].response_class == "minute_response_empty"
    assert outcomes[1].status == "complete"


def test_probe_evidence_is_target_isolated_source_safe_and_idempotent(tmp_path: Path) -> None:
    request_start_times: list[datetime] = []
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page("QQQ", "NAS", (start,), None),
            _page("SPY", "AMS", (start,), None),
        ],
        request_start_times,
    )
    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 0.1, 0.2, 0.3),
    )
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    first_paths = write_kis_paper_m1_historical_reach_evidence(
        outcomes,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    second_paths = write_kis_paper_m1_historical_reach_evidence(
        outcomes,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )

    assert first_paths == second_paths
    assert len(first_paths) == 2
    assert all(path.is_relative_to(artifact_root) for path in first_paths)
    assert {path.parent.name for path in first_paths} == {"target=QQQ-NAS", "target=SPY-AMS"}
    assert {path.parent.parent.name for path in first_paths} == {"scope=current_day_only"}
    artifact_parts = tuple(KIS_PAPER_M1_HISTORICAL_REACH_ARTIFACT_DIRECTORY.split("/"))
    assert all(
        any(
            path.parts[index : index + len(artifact_parts)] == artifact_parts
            for index in range(len(path.parts))
        )
        for path in first_paths
    )
    serialized = "\n".join(path.read_text(encoding="utf-8") for path in first_paths)
    assert "12345.67" not in serialized
    assert "20260724" not in serialized
    assert "access_token" not in serialized
    assert (
        json.loads(first_paths[0].read_text(encoding="utf-8"))["raw_market_data_retained"] is False
    )


def test_probe_rejects_repository_or_linked_artifact_root(tmp_path: Path) -> None:
    request_start_times: list[datetime] = []
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page("QQQ", "NAS", (start,), None),
            _page("SPY", "AMS", (start,), None),
        ],
        request_start_times,
    )
    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        monotonic_clock=_monotonic(0.0, 0.1, 0.2, 0.3),
    )
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        write_kis_paper_m1_historical_reach_evidence(
            outcomes,
            artifact_root=repository_root / "artifacts",
            repository_root=repository_root,
        )

    target = tmp_path / "external"
    target.mkdir()
    linked_root = tmp_path / "linked"
    try:
        linked_root.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(ValueError, match="must not contain links"):
        write_kis_paper_m1_historical_reach_evidence(
            outcomes,
            artifact_root=linked_root,
            repository_root=repository_root,
        )


def test_fixed_target_contract_never_expands_to_the_current_head_only_route() -> None:
    assert KIS_PAPER_M1_HISTORICAL_REACH_TARGETS == (("QQQ", "NAS"), ("SPY", "AMS"))


def _page(
    symbol: str,
    exchange: str,
    timestamps: tuple[datetime, ...],
    next_cursor: str | None,
) -> KisPaperMinutePage:
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(exchange=exchange, symbol=symbol),
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
