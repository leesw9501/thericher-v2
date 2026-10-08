from __future__ import annotations

import json
import runpy
import socket
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.execution.kis_market_data as market_data
import thericher_v2.execution.kis_private_intraday_backfill as collector
from thericher_v2.data.kis_paper_intraday import (
    load_verified_kis_paper_private_intraday_catalog,
    require_complete_kis_paper_private_intraday_session,
)
from thericher_v2.data.kis_paper_intraday_session_capture import (
    build_and_write_kis_paper_intraday_session_capture,
)
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_market_data import (
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_market_data_rate_gate import KisPaperMarketDataTokenStartGate


@pytest.fixture(autouse=True)
def deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network and credential access forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(market_data.UrllibKisPaperMarketDataTransport, "request", deny)
    monkeypatch.setattr(market_data, "load_kis_paper_market_data_config", deny)
    monkeypatch.setattr(market_data, "load_kis_paper_market_data_environment_config", deny)


class _Client:
    def __init__(
        self,
        qqq: list[KisPaperMinutePage | KisPaperMarketDataError],
        spy: list[KisPaperMinutePage | KisPaperMarketDataError] | None = None,
    ) -> None:
        self.responses = {
            "QQQ": list(qqq),
            "SPY": list(spy) if spy is not None else [_page(_rows(120), symbol="SPY")],
        }
        self.queries: list[KisPaperMinuteQuery] = []
        self.paced_calls = 0

    def fetch_minute_page(
        self, query: KisPaperMinuteQuery, *, before_request: Callable[[], None] | None = None
    ) -> KisPaperMinutePage:
        if before_request is not None:
            before_request()
            self.paced_calls += 1
        self.queries.append(query)
        response = self.responses[query.symbol].pop(0)
        if isinstance(response, KisPaperMarketDataError):
            raise response
        if (response.query.symbol, response.query.exchange) == (query.symbol, query.exchange):
            response = replace(response, query=query)
        return response


def _rows(count: int, *, offset: int = 0) -> tuple[KisPaperMinuteRawBar, ...]:
    result = []
    for index in range(offset, offset + count):
        exchange = datetime(2026, 7, 22, 9, 30) + timedelta(minutes=index)
        korea = exchange + timedelta(hours=13)
        result.append(
            KisPaperMinuteRawBar(
                exchange_date=exchange.strftime("%Y%m%d"),
                exchange_time=exchange.strftime("%H%M%S"),
                korea_date=korea.strftime("%Y%m%d"),
                korea_time=korea.strftime("%H%M%S"),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                last=Decimal("100"),
                volume=Decimal("10"),
            )
        )
    return tuple(result)


def _page(
    rows: tuple[KisPaperMinuteRawBar, ...],
    *,
    symbol: str = "QQQ",
    signal: str = "blank_or_absent",
) -> KisPaperMinutePage:
    return KisPaperMinutePage(
        query=KisPaperMinuteQuery(symbol=symbol, exchange="NAS" if symbol == "QQQ" else "AMS"),
        bars=rows,
        next_cursor="1" if signal == "recognized_continuation" else None,
        more="0",
        continuation_signal=signal,
    )


def _run(tmp_path: Path, client: object, **kwargs: object) -> tuple[object, ...]:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    options = {
        "pages_per_target": 4,
        "resume_cursor": False,
        "explicit_qqq_head_continuation": True,
        "observed_at": datetime(2026, 7, 24, 0, 0, tzinfo=UTC),
        "sleeper": lambda _seconds: None,
        "monotonic_clock": lambda: 0.0,
    }
    options.update(kwargs)
    return collector.run_kis_paper_private_intraday_backfill_cycle(
        client=client,
        cache_root=tmp_path / "market-data",
        repo_root=repo,
        code_revision="synthetic-head-continuation",
        **options,
    )


def _catalog(tmp_path: Path) -> object:
    return load_verified_kis_paper_private_intraday_catalog(
        cache_root=tmp_path / "market-data",
        repo_root=tmp_path / "repo",
        symbol="QQQ",
        exchange="NAS",
    )


def _index(tmp_path: Path) -> dict[str, object]:
    return json.loads((tmp_path / "market-data" / "v1" / "index.json").read_text())


def _run_pair(tmp_path: Path, client: object, **kwargs: object) -> tuple[object, ...]:
    return _run(
        tmp_path,
        client,
        explicit_qqq_head_continuation=False,
        explicit_pair_head_continuation=True,
        **kwargs,
    )


@pytest.mark.parametrize(
    "signal", ["blank_or_absent", "unrecognized_nonblank", "recognized_continuation"]
)
@pytest.mark.parametrize("descending", [False, True])
def test_paired_head_retains_complete_sessions_serially_without_cursor_changes(
    tmp_path: Path, signal: str, descending: bool
) -> None:
    rows = _rows(480, offset=-90)
    seed = _Client(
        *[
            [_page(rows[360:], symbol=symbol, signal="recognized_continuation")]
            for symbol in ("QQQ", "SPY")
        ]
    )
    _run(
        tmp_path, seed, pages_per_target=1, resume_cursor=True, explicit_qqq_head_continuation=False
    )
    prior_cursors = [state["next_cursor"] for state in _index(tmp_path)["targets"]]
    assert all(cursor is not None for cursor in prior_cursors)
    prior_manifests = {
        path: path.read_bytes()
        for path in (tmp_path / "market-data/v1/snapshots").glob("*/manifest.json")
    }
    responses = []
    for symbol in ("QQQ", "SPY"):
        responses.append(
            [
                _page(
                    tuple(reversed(rows[offset : offset + 120]))
                    if descending
                    else rows[offset : offset + 120],
                    symbol=symbol,
                    signal=signal,
                )
                for offset in (360, 240, 120, 0)
            ]
        )
    client = _Client(*responses)
    sleeps: list[float] = []
    results = _run_pair(tmp_path, client, sleeper=sleeps.append)
    assert [(result.status, result.row_count) for result in results] == [("collected", 480)] * 2
    assert [query.symbol for query in client.queries] == ["QQQ"] * 4 + ["SPY"] * 4
    assert client.paced_calls == len(sleeps) == 8
    for offset, symbol, exchange in ((0, "QQQ", "NAS"), (4, "SPY", "AMS")):
        queries = client.queries[offset : offset + 4]
        assert queries[0].continuation_next is None and not queries[0].include_previous_day
        for query, page_offset in zip(queries[1:], (360, 240, 120), strict=True):
            assert (query.symbol, query.exchange) == (symbol, exchange)
            assert query.continuation_key == collector._one_exchange_minute_before(
                rows[page_offset]
            )
            assert query.continuation_next == "1" and query.include_previous_day
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=tmp_path / "market-data",
            repo_root=tmp_path / "repo",
            symbol=symbol,
            exchange=exchange,
        )
        session = us_equity_2026_session(date(2026, 7, 22))
        assert (
            len(
                require_complete_kis_paper_private_intraday_session(
                    catalog, session=session.window
                ).bars
            )
            == 390
        )
    assert [state["next_cursor"] for state in _index(tmp_path)["targets"]] == prior_cursors
    assert all(path.read_bytes() == blob for path, blob in prior_manifests.items())
    for state in _index(tmp_path)["targets"]:
        assert state["chunks"][-1]["collection_scope"] == "head"
        assert state["chunks"][-1]["input_cursor"] is None
        assert state["chunks"][-1]["output_cursor"] is None


@pytest.mark.parametrize("symbol", ["QQQ", "SPY"])
@pytest.mark.parametrize(
    "failure",
    [
        "wrong_symbol",
        "wrong_exchange",
        "prior_day",
        "mixed_day",
        "unordered_exchange",
        "unordered_korea",
        "repeat",
        "overlap",
        "canonical_overlap",
        "duplicate_exchange",
        "duplicate_korea",
        "rate_limited",
    ],
)
def test_paired_invalid_page_preserves_prefix_and_stops_only_its_target(
    tmp_path: Path, symbol: str, failure: str
) -> None:
    head = _rows(120, offset=120)
    older = _rows(120)
    candidate = _page(older, symbol=symbol)
    if failure == "wrong_symbol":
        candidate = _page(older, symbol="SPY" if symbol == "QQQ" else "QQQ")
    elif failure == "wrong_exchange":
        query = replace(candidate.query)
        object.__setattr__(query, "exchange", "AMS" if symbol == "QQQ" else "NAS")
        candidate = replace(candidate, query=query)
    elif failure == "prior_day":
        candidate = _page(_rows(120, offset=-690), symbol=symbol)
    elif failure == "mixed_day":
        candidate = _page(_rows(120, offset=-630), symbol=symbol)
    elif failure == "unordered_exchange":
        candidate = _page((older[1], older[0], *older[2:]), symbol=symbol)
    elif failure == "unordered_korea":
        candidate = _page(
            tuple(
                replace(row, korea_date=other.korea_date, korea_time=other.korea_time)
                for row, other in zip(older, reversed(older), strict=True)
            ),
            symbol=symbol,
        )
    elif failure == "repeat":
        candidate = _page(head, symbol=symbol)
    elif failure == "overlap":
        candidate = _page(_rows(120, offset=1), symbol=symbol)
    elif failure == "canonical_overlap":
        candidate = _page(
            tuple(
                replace(row, korea_date=other.korea_date, korea_time=other.korea_time)
                for row, other in zip(older, head, strict=True)
            ),
            symbol=symbol,
        )
    elif failure == "duplicate_exchange":
        candidate = _page(
            (older[0], replace(older[1], exchange_time=older[0].exchange_time), *older[2:]),
            symbol=symbol,
        )
    elif failure == "duplicate_korea":
        candidate = _page(
            (older[0], replace(older[1], korea_time=older[0].korea_time), *older[2:]), symbol=symbol
        )
    elif failure == "rate_limited":
        candidate = KisPaperMarketDataError("rate_limited")
    full = [
        _page(_rows(120, offset=offset), symbol="SPY" if symbol == "QQQ" else "QQQ")
        for offset in (360, 240, 120, 0)
    ]
    failing = [_page(head, symbol=symbol), candidate, _page(older, symbol=symbol)]
    client = _Client(failing, full) if symbol == "QQQ" else _Client(full, failing)
    results = _run_pair(tmp_path, client)
    failed, other = results if symbol == "QQQ" else reversed(results)
    assert failed.status == "partial" and failed.row_count == 120
    assert failed.reason == (
        "rate_limited"
        if failure == "rate_limited"
        else "minute_cursor_stalled"
        if failure in {"prior_day", "repeat", "overlap", "canonical_overlap"}
        else "minute_response_invalid"
    )
    if failed.reason == "minute_response_invalid":
        assert (failed.failure_phase, failed.failure_code, failed.failure_page_ordinal) == (
            "head_contract",
            {
                "wrong_symbol": "response_identity_mismatch",
                "wrong_exchange": "response_identity_mismatch",
                "mixed_day": "mixed_exchange_dates",
                "unordered_exchange": "timestamp_order_invalid",
                "unordered_korea": "timestamp_order_invalid",
                "duplicate_exchange": "duplicate_exchange_timestamp",
                "duplicate_korea": "duplicate_korea_timestamp",
            }[failure],
            2,
        )
    else:
        assert failed.failure_phase is failed.failure_code is failed.failure_page_ordinal is None
    assert other.status == "collected" and other.row_count == 480
    assert len(client.responses[symbol]) == 1 and len(client.queries) == 6
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=tmp_path / "market-data",
        repo_root=tmp_path / "repo",
        symbol=symbol,
        exchange="NAS" if symbol == "QQQ" else "AMS",
    )
    assert len(catalog.bars) == 120


@pytest.mark.parametrize("symbol", ["QQQ", "SPY"])
@pytest.mark.parametrize("attempt_count", [1, 2])
def test_pair_mixed_fourth_page_keeps_360_and_bound_diagnostic_without_retry(
    tmp_path: Path, symbol: str, attempt_count: int, capsys: pytest.CaptureFixture[str]
) -> None:
    failing = [
        *[_page(_rows(120, offset=offset), symbol=symbol) for offset in (0, -120, -240)],
        _page(_rows(120, offset=810), symbol=symbol),
        _page(_rows(120, offset=-360), symbol=symbol),
    ]
    other_symbol = "SPY" if symbol == "QQQ" else "QQQ"
    first_observed_at = datetime(2026, 7, 22, 15, 30, tzinfo=UTC)
    retained_state = retained_manifest_bytes = retained_raw_bytes = None
    for attempt in range(attempt_count):
        good = [
            _page(_rows(120, offset=offset + attempt * 120), symbol=other_symbol)
            for offset in (360, 240, 120, 0)
        ]
        client = _Client(failing, good) if symbol == "QQQ" else _Client(good, failing)
        observed_at = first_observed_at + timedelta(minutes=attempt)
        results = _run_pair(tmp_path, client, observed_at=observed_at)
        state = next(t for t in _index(tmp_path)["targets"] if t["symbol"] == symbol)
        manifest_path = tmp_path / "market-data" / "v1" / state["chunks"][0]["manifest_path"]
        manifest = json.loads(manifest_path.read_text())
        raw_path = manifest_path.parent / manifest["files"]["raw_minute_rows"]["path"]
        if attempt == 0:
            retained_state = state["chunks"]
            retained_manifest_bytes = manifest_path.read_bytes()
            retained_raw_bytes = raw_path.read_bytes()
        else:
            assert state["chunks"] == retained_state
            assert manifest_path.read_bytes() == retained_manifest_bytes
            assert raw_path.read_bytes() == retained_raw_bytes
            assert state["last_reason"] == "minute_response_invalid"
            assert state["last_observed_at_utc"] == "2026-07-22T15:31:00Z"
        assert len(client.responses[symbol]) == 1
        assert len(client.queries) == client.paced_calls == 8
    failed, other = results if symbol == "QQQ" else reversed(results)
    assert (failed.status, failed.row_count, failed.reason) == (
        "partial",
        360,
        "minute_response_invalid",
    )
    assert (failed.failure_phase, failed.failure_code, failed.failure_page_ordinal) == (
        "head_contract",
        "mixed_exchange_dates",
        4,
    )
    assert other.status == "collected" and other.row_count == 480
    assert failed.requested_pages_per_target == 4
    script = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts" / "backfill_kis_paper_private_intraday.py")
    )
    assert script["_collection_succeeded"](results) is False
    assert len(client.responses[symbol]) == 1
    assert len(client.queries) == client.paced_calls == 8
    state = next(t for t in _index(tmp_path)["targets"] if t["symbol"] == symbol)
    chunk = state["chunks"][-1]
    manifest = json.loads((tmp_path / "market-data" / "v1" / chunk["manifest_path"]).read_text())
    assert len(manifest["pages"]) == 3
    assert chunk["input_cursor"] is chunk["output_cursor"] is state["next_cursor"] is None
    assert not any(key.startswith("failure_") for key in chunk)
    capture = build_and_write_kis_paper_intraday_session_capture(
        runs=results,
        cache_root=tmp_path / "market-data",
        repository_root=tmp_path / "repo",
        observed_at=observed_at,
        schedule_run_id=f"intraday-head-{observed_at.strftime('%Y%m%dT%H%M%SZ')}",
    )
    target = next(
        t for t in capture.safe_output_payload()["targets"] if t["target_key"] == failed.target_key
    )
    assert {key: target[key] for key in target if key.startswith("failure_")} == {
        "failure_phase": "head_contract",
        "failure_code": "mixed_exchange_dates",
        "failure_page_ordinal": 4,
    }
    assert target["requested_pages_per_target"] == 4
    assert capture.outcome.observed_at == observed_at
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    ("http_status", "upstream", "reason", "status_class", "code"),
    [
        (403, "synthetic-secret-must-not-leak", "auth_rejected", "4xx", None),
        (500, "EGW00201", "rate_limited", "5xx", "EGW00201"),
    ],
)
def test_pair_token_http_diagnostic_never_leaks_to_locally_blocked_companion(
    tmp_path: Path,
    http_status: int,
    upstream: str,
    reason: str,
    status_class: str,
    code: str | None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed_at = datetime(2026, 7, 24, 0, 0, tzinfo=UTC)
    token_gate = KisPaperMarketDataTokenStartGate(
        control_root=tmp_path / "control", clock=lambda: observed_at
    )

    class Transport:
        def __init__(self) -> None:
            self.http_count = 0

        def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
            market_data._validate_request(request)
            assert request.method == "POST"
            if not token_gate.claim_token_request_start():
                raise KisPaperMarketDataError("token_request_not_due")
            self.http_count += 1
            return KisMarketDataResponse.from_payload(
                {"msg_cd": upstream, "msg1": "synthetic-secret-must-not-leak"},
                status_code=http_status,
            )

    transport = Transport()
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="synthetic-key", app_secret="synthetic-secret"),
        transport=transport,
        max_minute_page_attempts=8,
    )
    runs = _run_pair(tmp_path, client)
    qqq, spy = runs
    assert qqq.status == spy.status == "rejected"
    assert qqq.reason == reason
    assert (qqq.token_http_status_class, qqq.token_upstream_code) == (status_class, code)
    assert spy.reason == "token_request_not_due"
    assert spy.token_http_status_class is spy.token_upstream_code is None
    assert transport.http_count == client.call_counts.token_attempts == 1
    assert client.call_counts.minute_page_attempts == 0
    capture = build_and_write_kis_paper_intraday_session_capture(
        runs=runs,
        cache_root=tmp_path / "market-data",
        repository_root=tmp_path / "repo",
        observed_at=observed_at,
        schedule_run_id="intraday-head-20260724T0000000000000Z",
    )
    payload = capture.safe_output_payload()
    qqq_payload, spy_payload = payload["targets"]
    assert qqq_payload["token_http_status_class"] == status_class
    assert qqq_payload.get("token_upstream_code") == code
    if code is None:
        assert "token_upstream_code" not in qqq_payload
    assert "token_http_status_class" not in spy_payload
    assert "token_upstream_code" not in spy_payload
    assert "synthetic-secret" not in json.dumps(payload) + capture.evidence_path.read_text()
    assert capsys.readouterr() == ("", "")


def test_duplicate_cached_prefix_preserves_current_token_diagnostic_and_other_progress(
    tmp_path: Path,
) -> None:
    retained_chunks = retained_manifest = None
    for attempt in range(2):
        error = KisPaperMarketDataError(
            "rate_limited", token_http_status_class="5xx", token_upstream_code="EGW00201"
        )
        client = _Client(
            [_page(_rows(120, offset=120)), error, _page(_rows(120))],
            [_page(_rows(1, offset=attempt), symbol="SPY")],
        )
        failed, companion = _run_pair(
            tmp_path, client, observed_at=datetime(2026, 7, 24, 0, attempt, tzinfo=UTC)
        )
        assert (failed.status, failed.row_count, failed.reason) == ("partial", 120, "rate_limited")
        assert (failed.token_http_status_class, failed.token_upstream_code) == ("5xx", "EGW00201")
        assert failed.failure_phase is failed.requested_pages_per_target is None
        assert companion.status == "collected"
        assert companion.token_http_status_class is companion.token_upstream_code is None
        assert len(client.queries) == 3 and len(client.responses["QQQ"]) == 1
        state = next(t for t in _index(tmp_path)["targets"] if t["symbol"] == "QQQ")
        manifest_path = tmp_path / "market-data" / "v1" / state["chunks"][0]["manifest_path"]
        if attempt == 0:
            retained_chunks = state["chunks"]
            retained_manifest = manifest_path.read_bytes()
        else:
            assert state["chunks"] == retained_chunks
            assert manifest_path.read_bytes() == retained_manifest
            assert state["last_reason"] == "rate_limited"
            assert state["last_observed_at_utc"] == "2026-07-24T00:01:00Z"


@pytest.mark.parametrize(
    "diagnostic",
    [
        {"token_http_status_class": "4XX"},
        {"token_http_status_class": []},
        {"token_http_status_class": "4xx", "token_upstream_code": "synthetic-secret"},
        {"token_http_status_class": "4xx", "token_upstream_code": "EGW00201"},
        {"token_upstream_code": "EGW00201"},
    ],
)
def test_mutated_token_diagnostic_is_omitted_without_changing_partial_prefix(
    tmp_path: Path, diagnostic: dict[str, object]
) -> None:
    error = KisPaperMarketDataError("auth_rejected")
    for key, value in diagnostic.items():
        setattr(error, key, value)
    client = _Client(
        [_page(_rows(120, offset=120)), error, _page(_rows(120))],
        [_page(_rows(1), symbol="SPY")],
    )
    failed, companion = _run_pair(tmp_path, client)
    assert (failed.status, failed.row_count, failed.reason) == ("partial", 120, "auth_rejected")
    assert failed.token_http_status_class is failed.token_upstream_code is None
    assert companion.status == "collected"
    assert len(client.responses["QQQ"]) == 1


def test_invalid_error_diagnostic_does_not_change_the_retained_prefix(tmp_path: Path) -> None:
    error = KisPaperMarketDataError("minute_response_invalid")
    error.failure_phase = "head_contract"
    error.failure_code = "synthetic-secret-must-not-leak"
    client = _Client(
        [_page(_rows(120, offset=120)), error, _page(_rows(120))],
        [_page(_rows(1), symbol="SPY")],
    )
    failed = _run_pair(tmp_path, client)[0]
    assert (failed.status, failed.row_count, failed.reason) == (
        "partial",
        120,
        "minute_response_invalid",
    )
    assert failed.failure_phase is failed.failure_code is failed.failure_page_ordinal is None
    assert len(client.responses["QQQ"]) == 1


@pytest.mark.parametrize("symbol", ["QQQ", "SPY"])
def test_paired_checker_enforces_requested_frontier_even_without_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, symbol: str
) -> None:
    original = collector._one_exchange_minute_before
    monkeypatch.setattr(
        collector,
        "_one_exchange_minute_before",
        lambda row: (
            datetime.strptime(original(row), "%Y%m%d%H%M%S") - timedelta(hours=1)
        ).strftime("%Y%m%d%H%M%S"),
    )
    pages = [_page(_rows(120, offset=120), symbol=symbol), _page(_rows(120), symbol=symbol)]
    other = [_page(_rows(1), symbol="SPY" if symbol == "QQQ" else "QQQ")]
    client = _Client(pages, other) if symbol == "QQQ" else _Client(other, pages)
    result = _run_pair(tmp_path, client, pages_per_target=2)[0 if symbol == "QQQ" else 1]
    assert (result.status, result.row_count, result.reason) == (
        "partial",
        120,
        "minute_cursor_stalled",
    )


@pytest.mark.parametrize(
    "signal", ["blank_or_absent", "unrecognized_nonblank", "recognized_continuation"]
)
@pytest.mark.parametrize("count", [1, 119, 120])
def test_paired_short_or_midnight_terminal_does_not_request_another_day(
    tmp_path: Path, signal: str, count: int
) -> None:
    rows = _rows(count, offset=-570 if count == 120 else 0)
    client = _Client(
        *[
            [_page(rows, symbol=symbol, signal=signal), _page(_rows(120), symbol=symbol)]
            for symbol in ("QQQ", "SPY")
        ]
    )
    results = _run_pair(tmp_path, client, pages_per_target=8)
    assert [(result.status, result.row_count, result.reason) for result in results] == [
        ("collected", count, None)
    ] * 2
    assert [query.symbol for query in client.queries] == ["QQQ", "SPY"]
    assert all(len(pages) == 1 for pages in client.responses.values())
    for state in _index(tmp_path)["targets"]:
        assert state["next_cursor"] is None
        assert state["chunks"][-1]["input_cursor"] is None
        assert state["chunks"][-1]["output_cursor"] is None


@pytest.mark.parametrize("symbol", ["QQQ", "SPY"])
@pytest.mark.parametrize("terminal_page", [1, 2])
@pytest.mark.parametrize("mode", ["pair", "qqq", "default"])
def test_full_recognized_terminal_page_stops_at_exact_frontier(
    tmp_path: Path, symbol: str, terminal_page: int, mode: str
) -> None:
    responses = []
    for target_symbol in ("QQQ", "SPY"):
        pages = [
            _page(
                _rows(120, offset=(4 - page_number) * 120),
                symbol=target_symbol,
                signal="recognized_terminal"
                if target_symbol == symbol and page_number == terminal_page
                else "recognized_continuation",
            )
            for page_number in range(1, 5)
        ]
        responses.append(pages)
    client = _Client(*responses)
    if mode == "pair":
        results = _run_pair(tmp_path, client)
    else:
        results = _run(tmp_path, client, explicit_qqq_head_continuation=(mode == "qqq"))
    target_index = 0 if symbol == "QQQ" else 1
    assert [(result.status, result.row_count, result.reason) for result in results] == [
        ("collected", 120 * (terminal_page if index == target_index else 4), None)
        for index in range(2)
    ]
    assert [query.symbol for query in client.queries] == ["QQQ"] * (
        terminal_page if symbol == "QQQ" else 4
    ) + ["SPY"] * (terminal_page if symbol == "SPY" else 4)
    assert len(client.responses[symbol]) == 4 - terminal_page
    for target_symbol, exchange in (("QQQ", "NAS"), ("SPY", "AMS")):
        queries = [query for query in client.queries if query.symbol == target_symbol]
        assert queries[0].continuation_next is None and not queries[0].include_previous_day
        frontiers = ("20260722152900", "20260722132900", "20260722112900")
        for query, frontier in zip(queries[1:], frontiers[: len(queries) - 1], strict=True):
            assert query.exchange == exchange and query.continuation_next == "1"
            assert query.continuation_key == frontier
            assert query.include_previous_day is (
                mode == "pair" or (mode == "qqq" and target_symbol == "QQQ")
            )
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=tmp_path / "market-data",
            repo_root=tmp_path / "repo",
            symbol=target_symbol,
            exchange=exchange,
        )
        count = terminal_page if target_symbol == symbol else 4
        expected_rows = _rows(120 * count, offset=(4 - count) * 120)
        assert [bar.start_ts for bar in catalog.bars] == [
            datetime.strptime(row.korea_date + row.korea_time, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            - timedelta(hours=9)
            for row in expected_rows
        ]
    for state in _index(tmp_path)["targets"]:
        chunk = state["chunks"][-1]
        assert state["next_cursor"] is None
        assert chunk["collection_scope"] == "head"
        assert chunk["input_cursor"] is None and chunk["output_cursor"] is None


@pytest.mark.parametrize("signal", ["blank_or_absent", "recognized_continuation"])
def test_pair_nonolder_derived_cursor_rejects_before_retaining_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signal: str
) -> None:
    head = _rows(120, offset=120)
    monkeypatch.setattr(
        collector,
        "_one_exchange_minute_before",
        lambda row: row.exchange_date + row.exchange_time,
    )
    client = _Client(
        [_page(head, signal=signal)],
        [_page(_rows(1), symbol="SPY")],
    )
    result = _run_pair(tmp_path, client)[0]
    assert (result.status, result.row_count, result.reason) == (
        "rejected",
        0,
        "minute_cursor_stalled",
    )
    assert [query.symbol for query in client.queries] == ["QQQ", "SPY"]
    assert _index(tmp_path)["targets"][0]["chunks"] == []


@pytest.mark.parametrize("signal", ["blank_or_absent", "unrecognized_nonblank"])
def test_four_headerless_pages_are_retained_and_historical_cursor_unchanged(
    tmp_path: Path, signal: str, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _rows(480)
    seed = _Client([_page(rows[360:], signal="recognized_continuation")])
    _run(
        tmp_path, seed, pages_per_target=1, resume_cursor=True, explicit_qqq_head_continuation=False
    )
    prior_cursors = [target["next_cursor"] for target in _index(tmp_path)["targets"]]
    client = _Client(
        [_page(rows[offset : offset + 120], signal=signal) for offset in (360, 240, 120, 0)]
    )
    sleeps: list[float] = []

    results = _run(tmp_path, client, sleeper=sleeps.append)

    assert [(result.status, result.row_count) for result in results] == [
        ("collected", 480),
        ("recovered", 120),
    ]
    assert len(_catalog(tmp_path).bars) == 480
    assert [target["next_cursor"] for target in _index(tmp_path)["targets"]] == prior_cursors
    assert len(client.queries) == client.paced_calls == len(sleeps) == 5
    assert all(
        delay == collector.KIS_PAPER_PRIVATE_INTRADAY_MIN_REQUEST_INTERVAL_SECONDS
        for delay in sleeps
    )
    assert [query.symbol for query in client.queries] == ["QQQ"] * 4 + ["SPY"]
    assert client.queries[0].continuation_next is None
    assert not client.queries[0].include_previous_day
    for query, offset in zip(client.queries[1:4], (360, 240, 120), strict=True):
        expected = datetime(2026, 7, 22, 9, 30) + timedelta(minutes=offset - 1)
        assert query.continuation_key == expected.strftime("%Y%m%d%H%M%S")
        assert query.continuation_next == "1" and query.include_previous_day
    assert client.queries[-1].continuation_next is None
    qqq_chunk = _index(tmp_path)["targets"][0]["chunks"][-1]
    manifest = json.loads(
        (tmp_path / "market-data" / "v1" / qqq_chunk["manifest_path"]).read_text()
    )
    assert len(manifest["pages"]) == 4
    assert all(
        not page["continuation_available"] and page["more"] == "0" for page in manifest["pages"]
    )
    assert qqq_chunk["input_cursor"] is None and qqq_chunk["output_cursor"] is None
    assert not any((tmp_path / "repo").iterdir())
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("budget", range(1, 9))
def test_opt_in_obeys_exact_page_budget(tmp_path: Path, budget: int) -> None:
    rows = _rows(960, offset=-570)
    client = _Client([_page(rows[offset : offset + 120]) for offset in range(840, -1, -120)])
    results = _run(tmp_path, client, pages_per_target=budget)
    assert results[0].row_count == 120 * budget
    assert len(client.queries) == budget + 1
    assert len(client.responses["QQQ"]) == 8 - budget
    for query, offset in zip(client.queries[1:budget], range(840, 0, -120), strict=False):
        oldest = rows[offset]
        expected = datetime.strptime(
            oldest.exchange_date + oldest.exchange_time, "%Y%m%d%H%M%S"
        ) - timedelta(minutes=1)
        assert query.continuation_key == expected.strftime("%Y%m%d%H%M%S")
        assert query.continuation_next == "1" and query.include_previous_day
    assert len(_catalog(tmp_path).bars) == 120 * budget
    chunk = _index(tmp_path)["targets"][0]["chunks"][-1]
    manifest = json.loads((tmp_path / "market-data" / "v1" / chunk["manifest_path"]).read_text())
    assert len(manifest["pages"]) == budget
    assert chunk["input_cursor"] is None and chunk["output_cursor"] is None


@pytest.mark.parametrize("failure", ["rate_limited", "prior_day", "mixed_day"])
def test_eighth_page_failure_retains_only_seven_same_day_pages(
    tmp_path: Path, failure: str
) -> None:
    rows = _rows(960, offset=-570)
    pages = [_page(rows[offset : offset + 120]) for offset in range(840, 0, -120)]
    if failure == "rate_limited":
        pages.append(KisPaperMarketDataError("rate_limited"))
    elif failure == "prior_day":
        pages.append(_page(_rows(120, offset=-690)))
    else:
        pages.append(_page(_rows(120, offset=-630)))
    client = _Client(pages + [_page(rows[:120])])
    result = _run(tmp_path, client, pages_per_target=8)[0]
    assert (result.status, result.row_count, result.reason) == (
        "partial",
        840,
        {
            "rate_limited": "rate_limited",
            "prior_day": "minute_cursor_stalled",
            "mixed_day": "minute_response_invalid",
        }[failure],
    )
    assert len(_catalog(tmp_path).bars) == 840
    assert [query.symbol for query in client.queries] == ["QQQ"] * 8 + ["SPY"]
    assert len(client.responses["QQQ"]) == 1
    chunk = _index(tmp_path)["targets"][0]["chunks"][-1]
    assert chunk["input_cursor"] is None and chunk["output_cursor"] is None


@pytest.mark.parametrize("signal", ["blank_or_absent", "recognized_continuation"])
def test_midnight_cursor_stops_without_requesting_previous_exchange_day(
    tmp_path: Path, signal: str
) -> None:
    rows = _rows(120, offset=-570)
    client = _Client([_page(rows, signal=signal), _page(_rows(120, offset=-690))])
    result = _run(tmp_path, client, pages_per_target=8)[0]
    assert (result.status, result.row_count) == ("collected", 120)
    assert [query.symbol for query in client.queries] == ["QQQ", "SPY"]
    assert len(client.responses["QQQ"]) == 1


def test_recover_published_head_after_index_failure_preserves_historical_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _Client([_page(_rows(120), signal="recognized_continuation")])
    seed.responses["SPY"] = [_page(_rows(120), symbol="SPY", signal="recognized_continuation")]
    _run(
        tmp_path, seed, pages_per_target=1, resume_cursor=True, explicit_qqq_head_continuation=False
    )
    index_path = tmp_path / "market-data" / "v1" / "index.json"
    seeded_bytes = index_path.read_bytes()
    seeded_cursors = [target["next_cursor"] for target in _index(tmp_path)["targets"]]
    assert all(cursor is not None for cursor in seeded_cursors)
    seed_manifests = set(index_path.parent.glob("snapshots/*/manifest.json"))
    write_index = collector._write_index
    published: list[Path] = []

    def fail_after_publish(**_kwargs: object) -> None:
        published.extend(set(index_path.parent.glob("snapshots/*/manifest.json")) - seed_manifests)
        assert len(published) == 1
        raise OSError("synthetic index commit failure")

    monkeypatch.setattr(collector, "_write_index", fail_after_publish)
    head = _Client([_page(_rows(120, offset=offset)) for offset in (360, 240, 120, 0)])
    with pytest.raises(OSError, match="synthetic index commit failure"):
        _run(tmp_path, head)
    assert index_path.read_bytes() == seeded_bytes
    manifest = json.loads(published[0].read_text())
    orphan = manifest["backfill"]["index_chunk"]
    assert orphan["collection_scope"] == "head" and orphan["output_cursor"] is None
    assert orphan["row_count"] == 480

    monkeypatch.setattr(collector, "_write_index", write_index)
    restart = _Client([])
    recovered = _run(tmp_path, restart)
    assert (recovered[0].status, recovered[0].row_count, recovered[0].manifest_path) == (
        "recovered",
        480,
        published[0],
    )
    assert [target["next_cursor"] for target in _index(tmp_path)["targets"]] == seeded_cursors
    assert [query.symbol for query in restart.queries] == ["SPY"]
    assert len(_catalog(tmp_path).bars) == 480
    assert _index(tmp_path)["targets"][0]["chunks"][-1]["collection_scope"] == "head"


@pytest.mark.parametrize("count", [1, 119])
@pytest.mark.parametrize("signal", ["blank_or_absent", "unrecognized_nonblank"])
def test_short_headerless_head_stops_without_older_request(
    tmp_path: Path, count: int, signal: str
) -> None:
    client = _Client([_page(_rows(count), signal=signal), _page(_rows(120))])
    assert _run(tmp_path, client)[0].row_count == count
    assert len(client.queries) == 2
    assert len(client.responses["QQQ"]) == 1


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("count", [1, 119])
@pytest.mark.parametrize("signal", ["blank_or_absent", "unrecognized_nonblank"])
def test_short_older_page_is_retained_then_stops(
    tmp_path: Path, paired: bool, count: int, signal: str
) -> None:
    responses = [
        [
            _page(_rows(120, offset=120), symbol=symbol),
            _page(_rows(count, offset=120 - count), symbol=symbol, signal=signal),
            _page(_rows(120), symbol=symbol),
        ]
        for symbol in ("QQQ", "SPY")
    ]
    client = _Client(*responses)
    run = _run_pair if paired else _run
    results = run(tmp_path, client)
    assert [(result.status, result.row_count, result.reason) for result in results] == [
        ("collected", 120 + count, None),
        ("collected", 120 + count if paired else 120, None),
    ]
    assert [query.symbol for query in client.queries] == ["QQQ"] * 2 + ["SPY"] * (
        2 if paired else 1
    )
    for symbol, exchange in (("QQQ", "NAS"), ("SPY", "AMS")):
        queries = [query for query in client.queries if query.symbol == symbol]
        assert queries[0].continuation_next is None and not queries[0].include_previous_day
        if len(queries) == 2:
            assert queries[1].exchange == exchange
            assert queries[1].continuation_next == "1" and queries[1].include_previous_day
            assert queries[1].continuation_key == "20260722112900"
        assert len(client.responses[symbol]) == (1 if len(queries) == 2 else 2)
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=tmp_path / "market-data",
            repo_root=tmp_path / "repo",
            symbol=symbol,
            exchange=exchange,
        )
        expected_rows = _rows(
            120 + count if len(queries) == 2 else 120,
            offset=120 - count if len(queries) == 2 else 120,
        )
        assert [bar.start_ts for bar in catalog.bars] == [
            datetime.strptime(row.korea_date + row.korea_time, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            - timedelta(hours=9)
            for row in expected_rows
        ]


@pytest.mark.parametrize("failure", ["repeat", "overlap", "newer", "canonical_overlap"])
def test_nonolder_page_aborts_before_retention_without_retry(tmp_path: Path, failure: str) -> None:
    head = _rows(120, offset=120)
    candidates = {
        "repeat": head,
        "overlap": _rows(120, offset=1),
        "newer": _rows(120, offset=240),
        "canonical_overlap": tuple(
            replace(row, korea_date=head[index].korea_date, korea_time=head[index].korea_time)
            for index, row in enumerate(_rows(120))
        ),
    }
    client = _Client([_page(head), _page(candidates[failure]), _page(_rows(120))])
    result = _run(tmp_path, client)[0]
    expected_reason = (
        "minute_duplicate_conflict" if failure == "canonical_overlap" else "minute_cursor_stalled"
    )
    assert result.reason == expected_reason
    assert result.row_count == (0 if failure == "canonical_overlap" else 120)
    assert result.status == ("rejected" if failure == "canonical_overlap" else "partial")
    if result.row_count:
        assert len(_catalog(tmp_path).bars) == 120
    assert len(client.queries) == 3
    assert len(client.responses["QQQ"]) == 1


@pytest.mark.parametrize("position", ["head", "older"])
def test_same_page_duplicates_are_not_retained(tmp_path: Path, position: str) -> None:
    duplicate = _page((_rows(120)[0],) * 120)
    client = _Client(
        [duplicate] if position == "head" else [_page(_rows(120, offset=120)), duplicate]
    )
    result = _run(tmp_path, client)[0]
    assert result.reason == "minute_response_invalid"
    assert result.row_count == (0 if position == "head" else 120)
    assert len(client.queries) == (2 if position == "head" else 3)


@pytest.mark.parametrize(
    "reason",
    [
        "minute_response_rejected",
        "minute_response_invalid",
        "minute_exchange_timestamp_invalid",
        "minute_ohlc_invalid",
        "rate_limited",
    ],
)
def test_invalid_or_rejected_older_page_preserves_only_valid_prefix(
    tmp_path: Path, reason: str
) -> None:
    client = _Client(
        [_page(_rows(120, offset=120)), KisPaperMarketDataError(reason), _page(_rows(120))]
    )
    result = _run(tmp_path, client)[0]
    assert (result.status, result.row_count, result.reason) == ("partial", 120, reason)
    assert len(_catalog(tmp_path).bars) == 120
    assert len(client.queries) == 3
    assert len(client.responses["QQQ"]) == 1


def test_wrong_response_identity_is_rejected(tmp_path: Path) -> None:
    client = _Client([_page(_rows(120), symbol="SPY")])
    result = _run(tmp_path, client)[0]
    assert (result.status, result.row_count, result.reason) == (
        "rejected",
        0,
        "minute_response_invalid",
    )


@pytest.mark.parametrize("invalid_key", ["invalid", "20260722000000bad"])
def test_invalid_derived_cursor_rejects_head_before_an_older_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_key: str
) -> None:
    monkeypatch.setattr(collector, "_one_exchange_minute_before", lambda _row: invalid_key)
    client = _Client([_page(_rows(120))])
    result = _run(tmp_path, client)[0]
    assert (result.status, result.row_count, result.reason) == (
        "rejected",
        0,
        "minute_cursor_invalid",
    )
    assert len(client.queries) == 2
    assert _index(tmp_path)["targets"][0]["chunks"] == []


def test_stalled_derived_cursor_does_not_leak_an_otherwise_older_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _rows(120, offset=120)
    stalled_key = collector._one_exchange_minute_before(head[0])
    monkeypatch.setattr(collector, "_one_exchange_minute_before", lambda _row: stalled_key)
    client = _Client([_page(head), _page(_rows(120)), _page(_rows(120))])
    result = _run(tmp_path, client)[0]
    assert (result.status, result.row_count, result.reason) == (
        "partial",
        120,
        "minute_cursor_stalled",
    )
    assert len(_catalog(tmp_path).bars) == 120
    assert len(client.queries) == 3
    assert len(client.responses["QQQ"]) == 1


def test_opt_in_cannot_be_forwarded_to_iwm_scope(tmp_path: Path) -> None:
    client = _Client([])
    with pytest.raises(ValueError, match="requires QQQ/SPY head mode"):
        collector._run_kis_paper_private_intraday_cycle(
            client=client,
            cache_root=tmp_path / "market-data",
            repo_root=tmp_path / "repo",
            code_revision="synthetic-head-continuation",
            targets=(("IWM", "AMS"),),
            pages_per_target=1,
            resume_cursor=False,
            quarantine_retained_head_conflicts=False,
            explicit_qqq_head_continuation=True,
            observed_at=datetime(2026, 7, 24, 0, 0, tzinfo=UTC),
            sleeper=lambda _seconds: None,
            monotonic_clock=lambda: 0.0,
        )
    assert client.queries == []
    assert not (tmp_path / "market-data").exists()


def test_conflicting_overlap_still_rejects_entire_candidate_batch(tmp_path: Path) -> None:
    head = _rows(120, offset=120)
    conflicting = replace(head[0], last=Decimal("100.5"))
    client = _Client([_page(head), _page((conflicting, *_rows(119)))])
    result = _run(tmp_path, client)[0]
    assert (result.status, result.row_count, result.reason, result.conflict_origin) == (
        "rejected",
        0,
        "minute_duplicate_conflict",
        "candidate_batch",
    )
    assert _index(tmp_path)["targets"][0]["chunks"] == []
    assert len(client.queries) == 3


@pytest.mark.parametrize(
    "option", ["explicit_qqq_head_continuation", "explicit_pair_head_continuation"]
)
@pytest.mark.parametrize("flag", [None, 1, "true"])
def test_flag_type_rejected_before_cache_or_request(
    tmp_path: Path, flag: object, option: str
) -> None:
    client = _Client([])
    with pytest.raises(ValueError, match="must be a boolean"):
        _run(tmp_path, client, **{"explicit_qqq_head_continuation": False, option: flag})
    assert client.queries == []
    assert not (tmp_path / "market-data").exists()


@pytest.mark.parametrize("options", [{"resume_cursor": True}, {"pages_per_target": 9}])
@pytest.mark.parametrize(
    "option", ["explicit_qqq_head_continuation", "explicit_pair_head_continuation"]
)
def test_scope_or_budget_rejected_before_cache_or_request(
    tmp_path: Path, options: dict[str, object], option: str
) -> None:
    client = _Client([])
    with pytest.raises(ValueError, match="requires QQQ/SPY head mode"):
        _run(tmp_path, client, **{"explicit_qqq_head_continuation": False, option: True}, **options)
    assert client.queries == []
    assert not (tmp_path / "market-data").exists()


def test_paired_and_qqq_options_cannot_be_combined(tmp_path: Path) -> None:
    client = _Client([])
    with pytest.raises(ValueError, match="mutually exclusive"):
        _run(tmp_path, client, explicit_pair_head_continuation=True)
    assert client.queries == [] and not (tmp_path / "market-data").exists()


@pytest.mark.parametrize("targets", [(("IWM", "AMS"),), (("QQQ", "NAS"),)])
def test_pair_option_cannot_widen_iwm_or_dated_scope(tmp_path: Path, targets: tuple) -> None:
    client = _Client([])
    with pytest.raises(ValueError, match="requires QQQ/SPY head mode"):
        collector._run_kis_paper_private_intraday_cycle(
            client=client,
            cache_root=tmp_path / "market-data",
            repo_root=tmp_path / "repo",
            code_revision="synthetic-pair",
            targets=targets,
            pages_per_target=4,
            resume_cursor=False,
            quarantine_retained_head_conflicts=False,
            explicit_pair_head_continuation=True,
            dated_qqq_session=date(2026, 7, 22) if targets[0][0] == "QQQ" else None,
            observed_at=datetime(2026, 7, 24, tzinfo=UTC),
            sleeper=lambda _seconds: None,
            monotonic_clock=lambda: 0.0,
        )
    assert client.queries == [] and not (tmp_path / "market-data").exists()


@pytest.mark.parametrize("symbol", ["QQQ", "SPY"])
def test_pair_invalid_first_head_rejects_only_its_target(tmp_path: Path, symbol: str) -> None:
    wrong = [_page(_rows(120), symbol="SPY" if symbol == "QQQ" else "QQQ")]
    good = [
        _page(_rows(120, offset=offset), symbol="SPY" if symbol == "QQQ" else "QQQ")
        for offset in (360, 240, 120, 0)
    ]
    client = _Client(wrong, good) if symbol == "QQQ" else _Client(good, wrong)
    results = _run_pair(tmp_path, client)
    assert results[0 if symbol == "QQQ" else 1].row_count == 0
    assert results[0 if symbol == "QQQ" else 1].status == "rejected"
    assert results[1 if symbol == "QQQ" else 0].row_count == 480
    assert len(client.queries) == 5


@pytest.mark.parametrize("signal", ["blank_or_absent", "unrecognized_nonblank"])
@pytest.mark.parametrize("count", [1, 119, 120])
def test_default_still_stops_on_headerless_head(tmp_path: Path, signal: str, count: int) -> None:
    client = _Client(
        *[
            [
                _page(_rows(count, offset=120), symbol=symbol, signal=signal),
                _page(_rows(120), symbol=symbol),
            ]
            for symbol in ("QQQ", "SPY")
        ]
    )
    results = _run(tmp_path, client, explicit_qqq_head_continuation=False)
    assert [(result.status, result.row_count, result.reason) for result in results] == [
        ("collected", count, None)
    ] * 2
    assert [query.symbol for query in client.queries] == ["QQQ", "SPY"]
    assert all(len(pages) == 1 for pages in client.responses.values())


def test_default_header_continuation_still_accepts_exact_overlap(tmp_path: Path) -> None:
    rows = _rows(180)
    client = _Client(
        [
            _page(rows[60:], signal="recognized_continuation"),
            _page((rows[60], *rows[:60])),
        ]
    )
    result = _run(tmp_path, client, explicit_qqq_head_continuation=False)[0]
    assert (result.row_count, result.exact_overlap_rows) == (180, 1)
    assert not client.queries[1].include_previous_day
    assert client.queries[1].continuation_next == "1"


@pytest.mark.parametrize("paired", [False, True])
def test_existing_cache_lock_still_prevents_all_requests(tmp_path: Path, paired: bool) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    root = collector._backfill_root(cache_root=tmp_path / "market-data", repo_root=repo)
    lock = collector._acquire_worker_lock(root)
    assert lock is not None
    client = _Client([])
    try:
        run = _run_pair if paired else _run
        assert [result.status for result in run(tmp_path, client)] == ["locked", "locked"]
        assert client.queries == []
    finally:
        collector._release_worker_lock(lock)


@pytest.mark.parametrize("paired", [False, True])
def test_real_client_fake_transport_reuses_token_and_sends_next_one_pinc_one(
    tmp_path: Path,
    paired: bool,
) -> None:
    class Transport:
        def __init__(self) -> None:
            self.requests: list[KisMarketDataRequest] = []
            rows = _rows(960, offset=-570)
            self.qqq_pages = [rows[offset : offset + 120] for offset in range(840, -1, -120)]
            self.spy_pages = [rows[offset : offset + 120] for offset in range(840, -1, -120)]

        def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
            market_data._validate_request(request)
            self.requests.append(request)
            if request.method == "POST":
                return KisMarketDataResponse.from_payload({"access_token": "synthetic-token"})
            rows = (self.qqq_pages if request.query["SYMB"] == "QQQ" else self.spy_pages).pop(0)
            return KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {"more": "0"},
                    "output2": [row.as_document() for row in rows],
                }
            )

    transport = Transport()
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="synthetic-key", app_secret="synthetic-secret"),
        transport=transport,
        max_minute_page_attempts=16,
    )
    run = _run_pair if paired else _run
    results = run(tmp_path, client, pages_per_target=8)
    assert [result.row_count for result in results] == [960, 960 if paired else 120]
    assert client.call_counts.token_attempts == 1
    assert client.call_counts.minute_page_attempts == (16 if paired else 9)
    assert client.call_counts.daily_page_attempts == 0
    gets = [request for request in transport.requests if request.method == "GET"]
    assert gets[0].query["PINC"] == "0" and gets[0].query["NEXT"] == ""
    for request in gets[1:8]:
        assert request.query["PINC"] == request.query["NEXT"] == "1"
        assert request.headers["tr_cont"] == "N"
        assert request.query["SYMB"] == "QQQ" and request.query["EXCD"] == "NAS"
    assert gets[8].query["SYMB"] == "SPY" and gets[8].query["NEXT"] == ""
    if paired:
        for request in gets[9:]:
            assert request.query["SYMB"] == "SPY" and request.query["EXCD"] == "AMS"
            assert request.query["PINC"] == request.query["NEXT"] == "1"
            assert request.headers["tr_cont"] == "N"


def _boundary_pages(
    *, missing: bool = False, descending: bool = False
) -> list[list[dict[str, str]]]:
    rows = _rows(390)
    oldest = rows[:30]
    if missing:
        oldest = tuple(row for index, row in enumerate(oldest) if index != 15)
    excluded = _rows(120 - len(oldest), offset=-1140 - int(missing))
    pages = [rows[270:], rows[150:270], rows[30:150], (*excluded, *oldest)]
    return [
        [row.as_document() for row in (reversed(page) if descending else page)] for page in pages
    ]


class _BoundaryTransport:
    def __init__(
        self,
        qqq: list[list[dict[str, str]]],
        spy: list[list[dict[str, str]]] | None = None,
        *,
        boundary_header: str = "",
    ):
        self.pages = {"QQQ": qqq, "SPY": spy if spy is not None else _boundary_pages()}
        self.requests: list[KisMarketDataRequest] = []
        self.boundary_header = boundary_header

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        market_data._validate_request(request)
        self.requests.append(request)
        if request.method == "POST":
            return KisMarketDataResponse.from_payload({"access_token": "synthetic-token"})
        rows = self.pages[request.query["SYMB"]].pop(0)
        return KisMarketDataResponse.from_payload(
            {
                "rt_cd": "0",
                "output1": {"more": "0"},
                "output2": rows,
            },
            headers={"tr_cont": self.boundary_header}
            if len({row["xymd"] for row in rows}) > 1
            else {},
        )


def _boundary_client(transport: _BoundaryTransport) -> KisPaperMarketDataClient:
    return KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="synthetic-key", app_secret="synthetic-secret"),
        transport=transport,
        max_minute_page_attempts=16,
    )


@pytest.mark.parametrize("descending", [False, True])
@pytest.mark.parametrize("header", ["", "M"])
def test_real_client_boundary_retains_bound_day_and_stops_without_fifth_get(
    tmp_path: Path, descending: bool, header: str, capsys: pytest.CaptureFixture[str]
) -> None:
    transport = _BoundaryTransport(_boundary_pages(descending=descending), boundary_header=header)
    client = _boundary_client(transport)
    observed = datetime(2026, 7, 22, 20, 0, tzinfo=UTC)
    results = _run_pair(tmp_path, client, pages_per_target=8, observed_at=observed)
    assert [(run.status, run.row_count, run.reason) for run in results] == [
        ("collected", 390, None)
    ] * 2
    assert client.call_counts.token_attempts == 1
    assert client.call_counts.minute_page_attempts == 8
    assert client.call_counts.daily_page_attempts == 0
    gets = [request for request in transport.requests if request.method == "GET"]
    for symbol in ("QQQ", "SPY"):
        requests = [request for request in gets if request.query["SYMB"] == symbol]
        assert len(requests) == 4
        assert requests[0].query["PINC"] == "0"
        assert requests[0].query["NEXT"] == requests[0].query["KEYB"] == ""
        for request, offset in zip(requests[1:], (270, 150, 30), strict=True):
            assert request.query["PINC"] == request.query["NEXT"] == "1"
            assert request.query["KEYB"] == collector._one_exchange_minute_before(
                _rows(390)[offset]
            )
            assert request.headers["tr_cont"] == "N"
    for run in results:
        manifest = json.loads(run.manifest_path.read_text())
        page = manifest["pages"][-1]
        assert len(manifest["pages"]) == 4
        assert (
            page["row_count"],
            page["retained_row_count"],
            page["excluded_older_row_count"],
        ) == (120, 30, 90)
        assert page["retained_exchange_date"] == "20260722"
        assert page["continuation_available"] is (header == "M")
        assert page["oldest_exchange_timestamp"] == "20260721T143000"
        assert page["newest_exchange_timestamp"] == "20260722T095900"
        assert page["oldest_korea_timestamp"] == "20260722T033000"
        assert page["newest_korea_timestamp"] == "20260722T225900"
        assert manifest["deduplication"]["input_row_count"] == 390
        assert sum(p["row_count"] for p in manifest["pages"]) == 480
        assert manifest["deduplication"]["unique_row_count"] == 390
        chunk = manifest["backfill"]["index_chunk"]
        assert chunk["input_cursor"] is chunk["output_cursor"] is None
        assert chunk["collection_scope"] == "head"
        symbol, exchange, _ = run.target_key.split("/")
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=tmp_path / "market-data",
            repo_root=tmp_path / "repo",
            symbol=symbol,
            exchange=exchange,
        )
        session = us_equity_2026_session(date(2026, 7, 22))
        assert (
            len(
                require_complete_kis_paper_private_intraday_session(
                    catalog, session=session.window
                ).bars
            )
            == 390
        )
        assert all(bar.start_ts.astimezone(UTC).date() == date(2026, 7, 22) for bar in catalog.bars)
    assert all(state["next_cursor"] is None for state in _index(tmp_path)["targets"])
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("limitation", ["missing", "forming"])
def test_valid_boundary_does_not_impute_or_complete_a_short_session(
    tmp_path: Path, limitation: str
) -> None:
    transport = _BoundaryTransport(_boundary_pages(missing=limitation == "missing"))
    observed = (
        datetime(2026, 7, 22, 19, 59, 30, tzinfo=UTC)
        if limitation == "forming"
        else datetime(2026, 7, 22, 20, 0, tzinfo=UTC)
    )
    runs = _run_pair(
        tmp_path, _boundary_client(transport), pages_per_target=8, observed_at=observed
    )
    assert runs[0].status == "collected" and runs[0].reason is None
    assert runs[0].row_count == (389 if limitation == "missing" else 390)
    catalog = _catalog(tmp_path)
    session = us_equity_2026_session(date(2026, 7, 22))
    with pytest.raises(ValueError, match="session is incomplete"):
        require_complete_kis_paper_private_intraday_session(catalog, session=session.window)
    capture = build_and_write_kis_paper_intraday_session_capture(
        runs=runs,
        cache_root=tmp_path / "market-data",
        repository_root=tmp_path / "repo",
        observed_at=observed,
    )
    assert capture.outcome.current_session_cumulative_coverage_category == "incomplete"
    coverage = capture.outcome.current_session_cumulative_coverage.session_coverage[0]
    assert coverage.complete_minute_count == 389 and coverage.expected_minute_count == 390


@pytest.mark.parametrize(
    "failure",
    [
        "bad_older_ohlc",
        "duplicate_older",
        "unordered_older",
        "clock_disagreement",
        "future_date",
        "third_date",
        "stale_head",
    ],
)
def test_entire_boundary_page_is_validated_before_any_older_row_is_excluded(
    tmp_path: Path, failure: str
) -> None:
    pages = _boundary_pages()
    boundary = pages[-1]
    if failure == "bad_older_ohlc":
        boundary[0]["high"] = "99"
    elif failure == "duplicate_older":
        boundary[1] = dict(boundary[0])
    elif failure == "unordered_older":
        boundary[0], boundary[1] = boundary[1], boundary[0]
    elif failure == "clock_disagreement":
        boundary[0]["khms"] = "043000"
    elif failure == "future_date":
        for record in boundary[:90]:
            record["xymd"] = "20260723"
            record["kymd"] = "20260724"
    elif failure == "third_date":
        boundary[0]["xymd"] = "20260720"
        boundary[0]["kymd"] = "20260721"
    observed = datetime(2026, 7, 23 if failure == "stale_head" else 22, 20, 0, tzinfo=UTC)
    transport = _BoundaryTransport(pages)
    client = _boundary_client(transport)
    runs = _run_pair(tmp_path, client, pages_per_target=8, observed_at=observed)
    assert (runs[0].status, runs[0].row_count) == ("partial", 360)
    assert runs[0].reason == (
        "minute_ohlc_invalid" if failure == "bad_older_ohlc" else "minute_response_invalid"
    )
    if failure != "bad_older_ohlc":
        assert (
            runs[0].failure_phase,
            runs[0].failure_page_ordinal,
            runs[0].requested_pages_per_target,
        ) == ("head_contract", 4, 8)
    assert client.call_counts.minute_page_attempts == 8
    assert len(_catalog(tmp_path).bars) == 360
    manifest = json.loads(runs[0].manifest_path.read_text())
    assert len(manifest["pages"]) == 3
    assert all("excluded_older_row_count" not in page for page in manifest["pages"])
    assert runs[1].status == ("partial" if failure == "stale_head" else "collected")


@pytest.mark.parametrize("old_only", [False, True])
def test_collected_boundary_revision_requires_zero_active_key_loss(
    tmp_path: Path, old_only: bool
) -> None:
    old = _rows(391, offset=-1) if old_only else _rows(390)
    seed = _Client(
        *[
            [
                _page(old[offset : offset + 120], symbol=symbol)
                for offset in (len(old) - 120, len(old) - 240, len(old) - 360)
            ]
            + [_page(old[: len(old) - 360], symbol=symbol)]
            for symbol in ("QQQ", "SPY")
        ]
    )
    observed = datetime(2026, 7, 22, 20, 0, tzinfo=UTC)
    _run_pair(tmp_path, seed, observed_at=observed)
    prior = _index(tmp_path)["targets"][0]["chunks"]
    originals = {
        path: path.read_bytes()
        for path in (tmp_path / "market-data/v1/snapshots").rglob("*")
        if path.is_file()
    }
    pages = _boundary_pages()
    pages[-1][-30]["last"] = "100.5"
    client = _boundary_client(_BoundaryTransport(pages))
    runs = _run_pair(
        tmp_path,
        client,
        pages_per_target=8,
        observed_at=observed + timedelta(minutes=1),
        quarantine_retained_head_conflicts=True,
    )
    diagnostic = runs[0].retained_head_conflict_diagnostic
    assert diagnostic.fresh_status == "collected" and diagnostic.fresh_reason is None
    assert diagnostic.prospective_active_key_loss_count == int(old_only)
    assert diagnostic.failed_predicates == (("boundary_active_key_loss",) if old_only else ())
    assert runs[0].status == ("rejected" if old_only else "collected")
    assert runs[0].retained_head_conflict_disposition == (
        "preserved" if old_only else "not_applicable"
    )
    assert all(path.read_bytes() == payload for path, payload in originals.items())
    if old_only:
        assert _index(tmp_path)["targets"][0]["chunks"] == prior
        assert len(_catalog(tmp_path).bars) == 391
    else:
        assert len(_catalog(tmp_path).bars) == 390
        state = _index(tmp_path)
        assert (
            collector._recover_orphan_snapshots(root=tmp_path / "market-data/v1", index=state) == ()
        )
        assert any(
            chunk.get("raw_market_data_retained") is False
            for chunk in state["targets"][0]["chunks"]
        )
