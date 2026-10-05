from __future__ import annotations

import hashlib
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.kis_paper_minute_capability_probe as capability_probe
import thericher_v2.execution.kis_market_data as market_data
from thericher_v2.data.kis_paper_minute_capability_probe import (
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS,
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_NATIVE_TARGET_KEYS,
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_OBSERVED_TARGET_KEYS,
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET_KEYS,
    KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS,
    KisPaperMinuteFixedKeyProbeOutcome,
    probe_and_write_kis_paper_minute_fixed_key_capability,
    run_kis_paper_minute_capability_probe,
    run_kis_paper_minute_fixed_key_probe,
    write_kis_paper_minute_capability_probe_evidence,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
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


def test_capability_route_classes_keep_observed_only_target_out_of_collector() -> None:
    assert KIS_PAPER_MINUTE_CAPABILITY_PROBE_NATIVE_TARGET_KEYS == {
        "QQQ/NAS/1m",
        "SPY/AMS/1m",
    }
    assert KIS_PAPER_MINUTE_CAPABILITY_PROBE_OBSERVED_TARGET_KEYS == {"SPY/NAS/1m"}
    assert KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS == {"IWM/AMS/1m"}
    assert (
        KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET_KEYS
        == KIS_PAPER_MINUTE_CAPABILITY_PROBE_NATIVE_TARGET_KEYS
        | KIS_PAPER_MINUTE_CAPABILITY_PROBE_OBSERVED_TARGET_KEYS
        | KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS
    )
    collector_targets = {
        f"{symbol}/{exchange}/1m" for symbol, exchange in KIS_PAPER_PRIVATE_INTRADAY_TARGETS
    }
    assert collector_targets == KIS_PAPER_MINUTE_CAPABILITY_PROBE_NATIVE_TARGET_KEYS
    assert collector_targets.isdisjoint(KIS_PAPER_MINUTE_CAPABILITY_PROBE_OBSERVED_TARGET_KEYS)
    assert collector_targets.isdisjoint(KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS)


def test_candidate_target_requires_one_current_day_page() -> None:
    client = _MinuteClient([])
    request_starts: tuple[datetime, ...] = ()

    with pytest.raises(ValueError, match="candidate capability target"):
        run_kis_paper_minute_capability_probe(
            client=client,
            request_start_times=request_starts,
            max_pages=2,
            target=("IWM", "AMS"),
            monotonic_clock=_monotonic(0.0, 1.0),
        )
    with pytest.raises(ValueError, match="candidate capability target"):
        run_kis_paper_minute_capability_probe(
            client=client,
            request_start_times=request_starts,
            include_previous_day=True,
            target=("IWM", "AMS"),
            monotonic_clock=_monotonic(0.0, 1.0),
        )
    assert client.queries == []


def test_probe_discards_raw_bars_and_records_single_client_cursor_chain() -> None:
    start = datetime(2026, 7, 24, 9, 29, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page((start + timedelta(minutes=3), start + timedelta(minutes=2)), "1"),
            _page((start + timedelta(minutes=1), start), "1"),
            _page((start - timedelta(minutes=1), start - timedelta(minutes=2)), None),
        ]
    )
    request_starts = tuple(
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
        + timedelta(seconds=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS * index)
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
    assert outcome.page_progress_categories == (
        "initial",
        "strictly_older_nonoverlapping",
        "strictly_older_nonoverlapping",
    )
    assert outcome.cursor_progress_category == "strictly_backward_nonoverlapping"
    assert outcome.probe_pattern_category == "cursor_chain"
    assert outcome.historical_range_category == "single_exchange_date"
    assert outcome.minute_spacing_category == "contiguous_after_deduplication"
    assert outcome.token_reuse_category == "single_token_reused"
    assert outcome.request_start_category == "at_or_below_existing_gate"
    assert outcome.tested_request_interval_seconds == (
        KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
    )
    assert outcome.token_request_count == 1
    assert outcome.minute_page_request_count == 3
    assert outcome.daily_page_request_count == 0
    assert outcome.request_attempt_count == 4
    assert outcome.categorical_limit_or_error_count == 0
    assert outcome.calibration_fact == "single_client_cursor_chain_under_existing_gate"
    assert outcome.pacing_recalibration_fact == "existing_gate_measurement_only"
    assert client.queries[1].continuation_next == "1"
    assert client.queries[1].continuation_key == "20260724093000"
    assert client.queries[2].continuation_key == "20260724092800"

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
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
        + timedelta(seconds=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS * index)
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
    assert outcome.page_progress_categories == ("initial", "terminal_head_repeat")
    assert outcome.cursor_progress_category == "terminal_head_repeat"
    assert outcome.probe_pattern_category == "terminal_head_repeat"
    assert outcome.token_reuse_category == "single_token_reused"
    assert outcome.request_start_category == "at_or_below_existing_gate"
    assert outcome.token_request_count == 1
    assert outcome.minute_page_request_count == 2
    assert outcome.request_attempt_count == 3
    assert outcome.categorical_limit_or_error_count == 0
    assert outcome.calibration_fact == "single_client_terminal_head_reuse_under_existing_gate"
    assert all(query.continuation_next is None for query in client.queries)
    assert "explicit_older_key_once" not in outcome.safe_payload()


def test_probe_allows_spy_nas_prior_day_scope_from_its_first_request() -> None:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient([_page((start + timedelta(minutes=1), start), None)])

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(datetime(2026, 7, 24, 12, 0, tzinfo=UTC),) * 2,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        include_previous_day=True,
        target=("SPY", "NAS"),
        repeat_terminal_head_once=False,
        monotonic_clock=_monotonic(0.0, 0.1),
    )

    assert outcome.include_previous_day is True
    assert outcome.safe_payload()["request_scope"] == "current_and_previous_day"
    assert outcome.safe_payload()["target_key"] == "SPY/NAS/1m"
    assert client.queries[0].include_previous_day is True
    assert client.queries[0].symbol == "SPY"
    assert client.queries[0].exchange == "NAS"


def test_probe_limits_a_native_control_to_one_minute_get() -> None:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient([_page((start + timedelta(minutes=1), start), None)])

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(datetime(2026, 7, 24, 12, 0, tzinfo=UTC),) * 2,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        max_pages=1,
        include_previous_day=True,
        target=("SPY", "AMS"),
        monotonic_clock=_monotonic(0.0, 0.1),
    )

    assert outcome.accepted_page_count == 1
    assert outcome.target_key == "SPY/AMS/1m"
    assert outcome.minute_page_request_count == 1
    assert outcome.token_request_count == 1
    assert len(client.queries) == 1


def test_probe_closes_duplicate_or_non_backward_cursor_chain_without_retaining_rows() -> None:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page((start + timedelta(minutes=2), start + timedelta(minutes=1)), "1"),
            _page((start + timedelta(minutes=1), start), "1"),
        ]
    )

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(
            datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
            datetime(2026, 7, 24, 12, 0, 1, tzinfo=UTC),
            datetime(2026, 7, 24, 12, 0, 2, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        include_previous_day=True,
        target=("SPY", "NAS"),
        monotonic_clock=_monotonic(0.0, 2.0),
    )

    assert outcome.status == "complete"
    assert outcome.accepted_page_count == 2
    assert outcome.continuation_category == "duplicate_conflict"
    assert outcome.page_progress_categories == ("initial", "overlap_or_not_older")
    assert outcome.cursor_progress_category == "duplicate_or_not_older"
    assert outcome.calibration_fact == "single_client_duplicate_or_non_backward_page"
    assert len(client.queries) == 2
    serialized = json.dumps(outcome.safe_payload(), sort_keys=True)
    assert "12345.67" not in serialized
    assert "20260724" not in serialized


def test_probe_closes_a_duplicate_within_one_page_without_requesting_a_cursor() -> None:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient([_page((start, start), "1")])

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(
            datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
            datetime(2026, 7, 24, 12, 0, 1, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        target=("SPY", "NAS"),
        monotonic_clock=_monotonic(0.0, 0.1),
    )

    assert outcome.status == "complete"
    assert outcome.accepted_page_count == 1
    assert outcome.continuation_category == "duplicate_conflict"
    assert outcome.page_progress_categories == ("duplicate_within_page",)
    assert outcome.cursor_progress_category == "duplicate_or_not_older"
    assert len(client.queries) == 1
    assert "20260724" not in json.dumps(outcome.safe_payload(), sort_keys=True)


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
    assert outcome.token_request_count == 1
    assert outcome.minute_page_request_count == 2
    assert outcome.request_attempt_count == 3
    assert outcome.categorical_limit_or_error_count == 1
    assert outcome.pacing_recalibration_fact == "rate_limit_observed_at_tested_interval"
    assert outcome.safe_payload()["raw_market_data_retained"] is False


def test_probe_records_empty_route_without_starting_a_collector() -> None:
    client = _MinuteClient([KisPaperMarketDataError("minute_response_empty")])

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(datetime(2026, 7, 24, 12, 0, tzinfo=UTC),) * 2,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        include_previous_day=True,
        target=("SPY", "NAS"),
        monotonic_clock=_monotonic(0.0, 0.1),
    )

    assert outcome.status == "unavailable"
    assert outcome.accepted_page_count == 0
    assert outcome.continuation_category == "not_observed"
    assert outcome.cursor_progress_category == "not_observed"
    assert outcome.response_class == "minute_response_empty"
    assert outcome.categorical_limit_or_error_count == 1
    assert len(client.queries) == 1
    assert "20260724" not in json.dumps(outcome.safe_payload(), sort_keys=True)


def test_probe_records_the_installed_one_second_pace_without_retaining_rows() -> None:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page((start + timedelta(minutes=1), start), None),
            _page((start + timedelta(minutes=1), start), None),
        ]
    )
    request_starts = tuple(
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC) + timedelta(seconds=index) for index in range(3)
    )

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=request_starts,
        observed_at=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        tested_request_interval_seconds=1.0,
        monotonic_clock=_monotonic(0.0, 2.5),
    )

    assert outcome.status == "complete"
    assert outcome.request_start_category == "at_or_below_existing_gate"
    assert outcome.tested_request_interval_seconds == 1.0
    assert outcome.token_request_count == 1
    assert outcome.minute_page_request_count == 2
    assert outcome.request_attempt_count == 3
    assert outcome.accepted_page_count == 2
    assert outcome.categorical_limit_or_error_count == 0
    assert outcome.pacing_recalibration_fact == "existing_gate_measurement_only"
    payload = outcome.safe_payload()
    assert payload["provider_request_start_ceiling"] == "bounded_candidate_only"
    assert "12345.67" not in json.dumps(payload, sort_keys=True)


def test_probe_rejects_an_invalid_tested_interval() -> None:
    client = _MinuteClient([])

    for tested_interval_seconds in (
        0.0,
        0.5,
        KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS + 0.25,
    ):
        try:
            run_kis_paper_minute_capability_probe(
                client=client,
                request_start_times=(),
                tested_request_interval_seconds=tested_interval_seconds,
                monotonic_clock=_monotonic(0.0),
            )
        except ValueError as error:
            assert str(error) == "capability probe tested request interval is invalid"
        else:
            raise AssertionError("unsupported tested interval must be rejected")


def test_probe_does_not_accept_starts_faster_than_the_tested_interval() -> None:
    start = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    client = _MinuteClient(
        [
            _page((start + timedelta(minutes=1), start), None),
            _page((start + timedelta(minutes=1), start), None),
        ]
    )
    request_starts = (
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        datetime(2026, 7, 24, 12, 0, 0, 500000, tzinfo=UTC),
        datetime(2026, 7, 24, 12, 0, 1, tzinfo=UTC),
    )

    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=request_starts,
        tested_request_interval_seconds=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
        monotonic_clock=_monotonic(0.0, 1.5),
    )

    assert outcome.status == "complete"
    assert outcome.request_start_category == "faster_than_existing_gate"
    assert outcome.pacing_recalibration_fact == "request_starts_faster_than_tested_interval"


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


@pytest.fixture
def offline_explicit_probe(monkeypatch):
    def deny(*_args, **_kwargs):
        raise AssertionError("real network, credentials and state must remain untouched")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(market_data, "load_kis_paper_market_data_config", deny)
    monkeypatch.setattr(market_data.UrllibKisPaperMarketDataTransport, "request", deny)


def _full_head():
    oldest = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    return _page(tuple(oldest + timedelta(minutes=index) for index in range(120)), None)


def _explicit_probe(client, **kwargs):
    return run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(),
        observed_at=datetime(2026, 7, 25, tzinfo=UTC),
        explicit_older_key_once=True,
        monotonic_clock=_monotonic(0.0, 2.0),
        **kwargs,
    )


@pytest.mark.usefixtures("offline_explicit_probe")
def test_full_legacy_head_still_repeats_without_explicit_opt_in():
    head = _full_head()
    client = _MinuteClient([head, head, head])
    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=(),
        monotonic_clock=_monotonic(0.0, 2.0),
    )
    assert len(client.queries) == 2
    assert all(query.continuation_next is None for query in client.queries)
    assert all(query.include_previous_day is False for query in client.queries)
    assert outcome.probe_pattern_category == "terminal_head_repeat"
    assert "explicit_older_key_once" not in outcome.safe_payload()


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize("signal", ["blank_or_absent", "unrecognized_nonblank"])
@pytest.mark.parametrize("older_signal", ["recognized_continuation", "recognized_terminal"])
def test_explicit_no_mf_full_head_requests_one_older_page_with_previous_day(
    signal, older_signal, capsys
):
    head = replace(_full_head(), continuation_signal=signal, more="1")
    oldest = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    older = replace(
        _page(tuple(oldest - timedelta(minutes=index) for index in range(1, 121)), "1"),
        next_cursor="1" if older_signal == "recognized_continuation" else None,
        continuation_signal=older_signal,
        more="private-body-metadata",
    )
    client = _MinuteClient([head, older, KisPaperMarketDataError("must_not_request_page3")])
    outcome = _explicit_probe(client, max_pages=3)
    assert len(client.queries) == 2
    assert client.queries[0].include_previous_day is False
    assert client.queries[0].continuation_next is None
    assert client.queries[1].include_previous_day is True
    assert client.queries[1].continuation_next == "1"
    assert client.queries[1].continuation_key == "20260724092900"
    assert all((query.symbol, query.exchange) == ("QQQ", "NAS") for query in client.queries)
    assert outcome.minute_page_request_count == 2
    assert outcome.token_request_count == 1
    assert outcome.accepted_page_count == 2
    assert outcome.explicit_older_key_category == "older_keys_observed"
    assert outcome.new_older_key_count == 120 and outcome.overlap_key_count == 0
    assert outcome.cursor_progress_category == "strictly_backward_nonoverlapping"
    assert outcome.continuation_signal_categories == (signal, older_signal)
    assert outcome.body_more_categories == ("one", "other_nonblank")
    assert len(client._responses) == 1
    serialized = json.dumps(outcome.safe_payload())
    for forbidden in (
        "12345.67",
        "20260724",
        "20260724092900",
        "private-body-metadata",
        "2026-07-25T00:00:00+00:00",
    ):
        assert forbidden not in serialized
    assert outcome.safe_payload()["raw_market_data_retained"] is False
    assert outcome.calibration_fact == "single_client_explicit_older_key_measurement_only"
    assert capsys.readouterr() == ("", "")


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize("case", ["overlap", "repeat", "newer", "rejected", "duplicate"])
def test_explicit_page2_kill_cases_close_without_retry(case):
    head = _full_head()
    oldest = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    if case == "rejected":
        second = KisPaperMarketDataError("minute_response_rejected")
    elif case == "repeat":
        second = head
    elif case == "newer":
        second = _page((oldest + timedelta(minutes=121),), None)
    elif case == "duplicate":
        second = _page((oldest - timedelta(minutes=1),) * 2, None)
    else:
        second = _page((oldest, oldest - timedelta(minutes=1)), None)
    client = _MinuteClient([head, second, head])
    outcome = _explicit_probe(client)
    assert len(client.queries) == 2 and len(client._responses) == 1
    assert client.queries[1].include_previous_day is True
    assert client.queries[1].continuation_next == "1"
    assert outcome.minute_page_request_count == 2
    assert (
        outcome.explicit_older_key_category
        == {
            "overlap": "overlap_with_older_keys",
            "repeat": "no_older_keys",
            "newer": "no_older_keys",
            "rejected": "page2_rejected",
            "duplicate": "duplicate_keys",
        }[case]
    )
    assert outcome.new_older_key_count == (1 if case in {"overlap", "duplicate"} else 0)
    assert outcome.overlap_key_count == {"overlap": 1, "repeat": 120}.get(case, 0)
    assert outcome.accepted_page_count == (1 if case == "rejected" else 2)
    assert outcome.continuation_category == (
        "continuation_failed" if case == "rejected" else "duplicate_conflict"
    )


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize(
    "case", ["short", "recognized_header", "recognized_terminal", "duplicate_head", "head_rejected"]
)
def test_explicit_request_requires_full_head_and_no_recognized_header(case):
    head = _full_head()
    if case == "short":
        head = replace(head, bars=head.bars[:-1])
    elif case == "recognized_header":
        head = replace(head, next_cursor="1", continuation_signal="recognized_continuation")
    elif case == "recognized_terminal":
        head = replace(head, continuation_signal="recognized_terminal")
    elif case == "duplicate_head":
        head = replace(head, bars=(head.bars[0],) * 120)
    else:
        head = KisPaperMarketDataError("minute_response_rejected")
    client = _MinuteClient([head, _full_head()])
    outcome = _explicit_probe(client)
    assert len(client.queries) == 1
    assert outcome.new_older_key_count == outcome.overlap_key_count == 0
    assert (
        outcome.explicit_older_key_category
        == {
            "short": "head_not_full",
            "recognized_header": "header_continuation_present",
            "recognized_terminal": "header_continuation_present",
            "duplicate_head": "duplicate_keys",
            "head_rejected": "head_unavailable",
        }[case]
    )


@pytest.mark.usefixtures("offline_explicit_probe")
def test_recognized_terminal_category_is_written_without_a_raw_header(tmp_path: Path) -> None:
    client = _MinuteClient(
        [replace(_full_head(), continuation_signal="recognized_terminal"), _full_head()]
    )
    outcome = _explicit_probe(client)
    assert outcome.accepted_page_count == outcome.minute_page_request_count == 1
    assert len(client._responses) == 1
    assert outcome.continuation_signal_categories == ("recognized_terminal",)
    repository = tmp_path / "repo"
    repository.mkdir()
    path = write_kis_paper_minute_capability_probe_evidence(
        outcome, artifact_root=tmp_path / "artifacts", repository_root=repository
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == outcome.safe_payload()
    assert payload["continuation_signal_categories"] == ["recognized_terminal"]
    assert "tr_cont" not in payload and payload["raw_market_data_retained"] is False


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize(
    "kwargs",
    [
        {"target": ("SPY", "AMS")},
        {"target": ("SPY", "NAS")},
        {"target": ("IWM", "AMS")},
        {"include_previous_day": True},
        {"max_pages": 1},
    ],
)
def test_explicit_scope_rejected_before_client_request(kwargs):
    client = _MinuteClient([])
    with pytest.raises(ValueError, match="explicit older-key probe requires"):
        _explicit_probe(client, **kwargs)
    assert client.queries == []


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize("second_rejected", [False, True])
def test_existing_client_allowlist_sends_next1_pinc1_without_mf_or_production_changes(
    second_rejected,
):
    head = _full_head()
    oldest = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)
    older = _page((oldest - timedelta(minutes=1),), None)
    requests = []
    pages = iter([head, older])

    class Transport:
        def request(self, request):
            requests.append(request)
            if request.method == "POST":
                return market_data.KisMarketDataResponse.from_payload(
                    {"access_token": "fake-token"}
                )
            assert market_data._is_approved_minute_request(request)
            if len(requests) == 3 and second_rejected:
                return market_data.KisMarketDataResponse.from_payload(
                    {"rt_cd": "1", "msg1": "private-response-body"}
                )
            page = next(pages)
            return market_data.KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {"more": "1"},
                    "output2": [bar.as_document() for bar in page.bars],
                }
            )

    client = market_data.KisPaperMarketDataClient(
        config=market_data.KisPaperMarketDataConfig(app_key="fake-key", app_secret="fake-secret"),
        transport=Transport(),
        max_minute_page_attempts=2,
    )
    outcome = _explicit_probe(client)
    assert len(requests) == 3 and requests[0].method == "POST"
    assert requests[1].query["PINC"] == "0" and requests[1].query["NEXT"] == ""
    assert requests[2].query["PINC"] == "1" and requests[2].query["NEXT"] == "1"
    assert requests[2].query["KEYB"] == "20260724092900"
    assert requests[2].headers["tr_cont"] == "N"
    assert outcome.minute_page_request_count == 2 and outcome.token_request_count == 1
    assert outcome.continuation_signal_categories == (
        ("blank_or_absent",) if second_rejected else ("blank_or_absent", "blank_or_absent")
    )
    assert outcome.new_older_key_count == (0 if second_rejected else 1)
    assert outcome.explicit_older_key_category == (
        "page2_rejected" if second_rejected else "older_keys_observed"
    )
    payload = json.dumps(outcome.safe_payload())
    assert not any(secret in payload for secret in ("fake-token", "fake-key", "fake-secret"))
    assert "private-response-body" not in payload


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


def _fixed_key_page(key: str, *, offset: int = 0, duplicate: bool = False):
    timestamp = datetime.strptime(key, "%Y%m%d%H%M%S") + timedelta(minutes=offset)
    stamps = (timestamp, timestamp if duplicate else timestamp - timedelta(minutes=1))
    return replace(
        _page(stamps, None),
        query=KisPaperMinuteQuery(
            symbol="QQQ",
            exchange="NAS",
            include_previous_day=True,
            continuation_next="1",
            continuation_key=key,
        ),
    )


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize("header", [None, "M", "F", "D", ""])
def test_fixed_keys_use_two_gets_one_token_and_ignore_all_continuation_headers(header):
    requests = []

    class Transport:
        def request(self, request):
            market_data._validate_request(request)
            requests.append(request)
            if request.method == "POST":
                return market_data.KisMarketDataResponse.from_payload(
                    {"access_token": "synthetic-private-token"}
                )
            page = _fixed_key_page(request.query["KEYB"])
            return market_data.KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "msg1": "synthetic-private-provider-body",
                    "output1": {"more": "1", "next": "provider-key-must-not-be-followed"},
                    "output2": [bar.as_document() for bar in page.bars],
                },
                headers={} if header is None else {"tr_cont": header},
            )

    client = market_data.KisPaperMarketDataClient(
        config=market_data.KisPaperMarketDataConfig(
            app_key="synthetic-private-key", app_secret="synthetic-private-secret"
        ),
        transport=Transport(),
        max_minute_page_attempts=2,
    )
    outcome = run_kis_paper_minute_fixed_key_probe(
        client=client, observed_at=datetime(2026, 10, 3, tzinfo=UTC)
    )
    gets = [request for request in requests if request.method == "GET"]
    assert len(requests) == 3 and requests[0].method == "POST"
    assert (
        tuple(request.query["KEYB"] for request in gets) == KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS
    )
    assert all(
        request.query["PINC"] == request.query["NEXT"] == "1"
        and request.query["SYMB"] == "QQQ"
        and request.query["EXCD"] == "NAS"
        and request.headers["tr_cont"] == "N"
        for request in gets
    )
    assert outcome.call_counts == KisPaperMarketDataCallCounts(1, 2, 0)
    assert all(page.category == "requested_date_observed" for page in outcome.pages)
    payload = json.dumps(outcome.safe_payload())
    assert all(
        value not in payload
        for value in (
            "synthetic-private-token",
            "synthetic-private-key",
            "synthetic-private-secret",
            "synthetic-private-provider-body",
            "provider-key-must-not-be-followed",
            "12345.67",
        )
    )
    with pytest.raises(KisPaperMarketDataError, match="minute_page_limit_exceeded"):
        client.fetch_minute_page(_fixed_key_page(outcome.pages[0].requested_key).query)
    assert len(requests) == 3


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize("offset", [0, -1, -1440, 1, 44640])
def test_fixed_key_date_honoring_rejects_newer_time_or_latest_fallback(offset):
    client = _MinuteClient(
        [_fixed_key_page(key, offset=offset) for key in KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS]
    )
    outcome = run_kis_paper_minute_fixed_key_probe(
        client=client, observed_at=datetime(2026, 10, 3, tzinfo=UTC)
    )
    expected = (
        "newer_than_key"
        if offset > 0
        else "earlier_only"
        if offset <= -1440
        else "requested_date_observed"
    )
    assert [page.category for page in outcome.pages] == [expected, expected]
    assert tuple(query.continuation_key for query in client.queries) == (
        KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS
    )


@pytest.mark.usefixtures("offline_explicit_probe")
def test_both_fixed_keys_returning_identical_latest_window_never_claim_date_honoring():
    latest = _page((datetime(2026, 10, 2, 17, 48, tzinfo=UTC),), None)
    client = _MinuteClient(
        [
            replace(latest, query=_fixed_key_page(key).query)
            for key in KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS
        ]
    )
    outcome = run_kis_paper_minute_fixed_key_probe(
        client=client, observed_at=datetime(2026, 10, 3, tzinfo=UTC)
    )
    assert outcome.status == "complete"
    assert [page.category for page in outcome.pages] == ["newer_than_key"] * 2
    assert outcome.pages[0].oldest_exchange_key == outcome.pages[1].oldest_exchange_key


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize(
    "reason,category",
    [
        ("minute_response_empty", "empty"),
        ("minute_response_rejected", "rejected"),
        ("minute_response_invalid", "invalid"),
        ("minute_exchange_timestamp_invalid", "invalid"),
    ],
)
def test_fixed_key_semantic_failure_does_not_retry_or_suppress_second_key(reason, category):
    client = _MinuteClient(
        [
            KisPaperMarketDataError(reason),
            _fixed_key_page(KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS[1]),
        ]
    )
    outcome = run_kis_paper_minute_fixed_key_probe(
        client=client, observed_at=datetime(2026, 10, 3, tzinfo=UTC)
    )
    assert [page.category for page in outcome.pages] == [category, "requested_date_observed"]
    assert outcome.pages[0].row_count == 0 and outcome.pages[0].oldest_exchange_key is None
    assert len(client.queries) == 2 and len({q.continuation_key for q in client.queries}) == 2


@pytest.mark.usefixtures("offline_explicit_probe")
def test_fixed_key_untrusted_failure_stops_without_printing_exception_text():
    client = _MinuteClient([KisPaperMarketDataError("synthetic-private-token body account")])
    outcome = run_kis_paper_minute_fixed_key_probe(
        client=client, observed_at=datetime(2026, 10, 3, tzinfo=UTC)
    )
    assert len(client.queries) == 1 and outcome.pages[0].category == "rejected"
    assert "synthetic-private" not in json.dumps(outcome.safe_payload())


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize(
    "failure",
    [
        "auth_rejected",
        "auth_response_invalid",
        "token_request_not_due",
        "transport_failure",
    ],
)
def test_fixed_key_auth_failure_never_attempts_a_second_token_or_any_get(failure):
    requests = []

    class Transport:
        def request(self, request):
            market_data._validate_request(request)
            requests.append(request)
            assert request.method == "POST"
            if failure == "token_request_not_due":
                raise KisPaperMarketDataError(
                    market_data.KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON
                )
            if failure == "transport_failure":
                raise KisPaperMarketDataError("transport_failure")
            return market_data.KisMarketDataResponse.from_payload(
                {"private-error": "synthetic-private-body"},
                status_code=403 if failure == "auth_rejected" else 200,
            )

    client = market_data.KisPaperMarketDataClient(
        config=market_data.KisPaperMarketDataConfig(app_key="fake-key", app_secret="fake-secret"),
        transport=Transport(),
        max_minute_page_attempts=2,
    )
    outcome = run_kis_paper_minute_fixed_key_probe(
        client=client, observed_at=datetime(2026, 10, 3, tzinfo=UTC)
    )
    assert len(requests) == 1 and requests[0].method == "POST"
    assert outcome.call_counts.token_attempts == (0 if failure == "token_request_not_due" else 1)
    assert outcome.call_counts.minute_page_attempts == 0
    assert len(outcome.pages) == 1 and outcome.pages[0].category == "rejected"
    assert "synthetic-private-body" not in json.dumps(outcome.safe_payload())


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize(
    "failure,category",
    [
        ("empty", "empty"),
        ("rejected", "rejected"),
        ("invalid", "invalid"),
    ],
)
def test_fixed_key_market_failure_uses_the_valid_token_for_second_independent_key(
    failure, category
):
    requests = []
    get_count = 0

    class Transport:
        def request(self, request):
            nonlocal get_count
            market_data._validate_request(request)
            requests.append(request)
            if request.method == "POST":
                return market_data.KisMarketDataResponse.from_payload(
                    {"access_token": "fake-token"}
                )
            get_count += 1
            if get_count == 1:
                payload = {
                    "empty": {"rt_cd": "0", "output1": {}, "output2": []},
                    "rejected": {"rt_cd": "1", "msg1": "synthetic-private-body"},
                    "invalid": {"rt_cd": "0", "output1": [], "output2": []},
                }[failure]
            else:
                page = _fixed_key_page(request.query["KEYB"])
                payload = {
                    "rt_cd": "0",
                    "output1": {"more": "0"},
                    "output2": [bar.as_document() for bar in page.bars],
                }
            return market_data.KisMarketDataResponse.from_payload(payload)

    client = market_data.KisPaperMarketDataClient(
        config=market_data.KisPaperMarketDataConfig(app_key="fake-key", app_secret="fake-secret"),
        transport=Transport(),
        max_minute_page_attempts=2,
    )
    outcome = run_kis_paper_minute_fixed_key_probe(
        client=client, observed_at=datetime(2026, 10, 3, tzinfo=UTC)
    )
    assert [request.method for request in requests] == ["POST", "GET", "GET"]
    assert outcome.call_counts == KisPaperMarketDataCallCounts(1, 2, 0)
    assert [page.category for page in outcome.pages] == [category, "requested_date_observed"]
    assert [request.query["KEYB"] for request in requests[1:]] == list(
        KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS
    )


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize(
    "keys,reason",
    [
        (("20260901120000", "20260901120000"), "distinct dates"),
        (("20260901120000", "20260803130000"), "same exchange clock"),
        (("20260901120000", "20260230120000"), "exchange key is invalid"),
    ],
)
def test_future_fixed_constant_edit_cannot_silently_change_calendar_question(
    monkeypatch, keys, reason
):
    monkeypatch.setattr(capability_probe, "KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS", keys)

    class UnusedClient:
        @property
        def call_counts(self):
            raise AssertionError("client must remain untouched")

    with pytest.raises(ValueError, match=reason):
        run_kis_paper_minute_fixed_key_probe(
            client=UnusedClient(), observed_at=datetime(2026, 10, 3, tzinfo=UTC), keys=keys
        )


@pytest.mark.usefixtures("offline_explicit_probe")
@pytest.mark.parametrize(
    "keys",
    [
        (),
        ("20260901120000",),
        ("20260901120000", "20260901120000"),
        ("20260901120000", "20260230120000"),
        ("20260901120000", "2026080312000x"),
        ["20260901120000", "20260803120000"],
    ],
)
def test_fixed_key_invalid_plan_fails_before_client_access(keys):
    class UnusedClient:
        @property
        def call_counts(self):
            raise AssertionError("client must remain untouched")

    with pytest.raises(ValueError, match="predeclared"):
        run_kis_paper_minute_fixed_key_probe(
            client=UnusedClient(), observed_at=datetime(2026, 10, 3, tzinfo=UTC), keys=keys
        )


@pytest.mark.usefixtures("offline_explicit_probe")
def test_fixed_key_evidence_hash_only_metadata_and_no_cache_access(tmp_path, monkeypatch):
    import thericher_v2.data.kis_paper_intraday as reader
    import thericher_v2.execution.kis_private_intraday_backfill as backfill

    def deny(*_args, **_kwargs):
        raise AssertionError("cache and collector access forbidden")

    monkeypatch.setattr(reader, "load_verified_kis_paper_private_intraday_catalog", deny)
    monkeypatch.setattr(backfill, "run_kis_paper_private_intraday_backfill_cycle", deny)
    monkeypatch.setattr(backfill, "_read_or_create_index", deny)
    client = _MinuteClient(
        [
            _fixed_key_page(key, duplicate=index == 0)
            for index, key in enumerate(KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS)
        ]
    )
    result = probe_and_write_kis_paper_minute_fixed_key_capability(
        client=client,
        observed_at=datetime(2026, 10, 3, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
    )
    encoded = result.evidence_path.read_bytes()
    assert result.evidence_sha256 == "sha256:" + hashlib.sha256(encoded).hexdigest()
    assert result.evidence_path.name.startswith("fixed-key-pair-")
    assert result.evidence_path.parent == (
        tmp_path / "artifacts" / "data" / "kis-paper-minute-capability-probe"
    )
    assert json.loads(encoded) == result.outcome.safe_payload()
    assert [page.category for page in result.outcome.pages] == [
        "invalid",
        "requested_date_observed",
    ]
    assert list((tmp_path / "artifacts").rglob("*.*")) == [result.evidence_path]
    assert not (tmp_path / "repo").exists()
    assert b"12345.67" not in encoded and b"ohlcv" not in encoded
    with pytest.raises(ValueError, match="outcome"):
        KisPaperMinuteFixedKeyProbeOutcome(
            result.outcome.observed_at,
            tuple(reversed(result.outcome.pages)),
            result.outcome.call_counts,
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
