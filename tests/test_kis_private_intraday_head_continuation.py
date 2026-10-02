from __future__ import annotations

import json
import socket
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.execution.kis_market_data as market_data
import thericher_v2.execution.kis_private_intraday_backfill as collector
from thericher_v2.data.kis_paper_intraday import load_verified_kis_paper_private_intraday_catalog
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
    def __init__(self, qqq: list[KisPaperMinutePage | KisPaperMarketDataError]) -> None:
        self.responses = {"QQQ": list(qqq), "SPY": [_page(_rows(120), symbol="SPY")]}
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


@pytest.mark.parametrize("budget", [1, 2, 3, 4])
def test_opt_in_obeys_exact_page_budget(tmp_path: Path, budget: int) -> None:
    client = _Client([_page(_rows(120, offset=offset)) for offset in (360, 240, 120, 0)])
    results = _run(tmp_path, client, pages_per_target=budget)
    assert results[0].row_count == 120 * budget
    assert len(client.queries) == budget + 1
    assert len(client.responses["QQQ"]) == 4 - budget


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
def test_short_headerless_head_stops_without_older_request(tmp_path: Path, count: int) -> None:
    client = _Client([_page(_rows(count)), _page(_rows(120))])
    assert _run(tmp_path, client)[0].row_count == count
    assert len(client.queries) == 2
    assert len(client.responses["QQQ"]) == 1


def test_short_older_page_is_retained_then_stops(tmp_path: Path) -> None:
    client = _Client([_page(_rows(120, offset=120)), _page(_rows(119)), _page(_rows(120))])
    assert _run(tmp_path, client)[0].row_count == 239
    assert len(_catalog(tmp_path).bars) == 239
    assert len(client.queries) == 3


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


@pytest.mark.parametrize("flag", [None, 1, "true"])
def test_flag_type_rejected_before_cache_or_request(tmp_path: Path, flag: object) -> None:
    client = _Client([])
    with pytest.raises(ValueError, match="must be a boolean"):
        _run(tmp_path, client, explicit_qqq_head_continuation=flag)
    assert client.queries == []
    assert not (tmp_path / "market-data").exists()


@pytest.mark.parametrize(
    "options", [{"resume_cursor": True}, {"pages_per_target": 5}, {"pages_per_target": 8}]
)
def test_scope_or_budget_rejected_before_cache_or_request(
    tmp_path: Path, options: dict[str, object]
) -> None:
    client = _Client([])
    with pytest.raises(ValueError, match="requires QQQ/SPY head mode"):
        _run(tmp_path, client, **options)
    assert client.queries == []
    assert not (tmp_path / "market-data").exists()


def test_default_still_stops_on_full_headerless_head(tmp_path: Path) -> None:
    client = _Client([_page(_rows(120, offset=120)), _page(_rows(120))])
    result = _run(tmp_path, client, explicit_qqq_head_continuation=False)[0]
    assert (result.status, result.row_count) == ("collected", 120)
    assert len(client.queries) == 2


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


def test_existing_cache_lock_still_prevents_all_requests(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    root = collector._backfill_root(cache_root=tmp_path / "market-data", repo_root=repo)
    lock = collector._acquire_worker_lock(root)
    assert lock is not None
    client = _Client([])
    try:
        assert [result.status for result in _run(tmp_path, client)] == ["locked", "locked"]
        assert client.queries == []
    finally:
        collector._release_worker_lock(lock)


def test_real_client_fake_transport_reuses_token_and_sends_next_one_pinc_one(
    tmp_path: Path,
) -> None:
    class Transport:
        def __init__(self) -> None:
            self.requests: list[KisMarketDataRequest] = []
            self.qqq_pages = [_rows(120, offset=offset) for offset in (360, 240, 120, 0)]

        def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
            market_data._validate_request(request)
            self.requests.append(request)
            if request.method == "POST":
                return KisMarketDataResponse.from_payload({"access_token": "synthetic-token"})
            rows = self.qqq_pages.pop(0) if request.query["SYMB"] == "QQQ" else _rows(120)
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
        max_minute_page_attempts=8,
    )
    assert _run(tmp_path, client)[0].row_count == 480
    assert client.call_counts.token_attempts == 1
    assert client.call_counts.minute_page_attempts == 5
    assert client.call_counts.daily_page_attempts == 0
    gets = [request for request in transport.requests if request.method == "GET"]
    assert gets[0].query["PINC"] == "0" and gets[0].query["NEXT"] == ""
    for request in gets[1:4]:
        assert request.query["PINC"] == request.query["NEXT"] == "1"
        assert request.headers["tr_cont"] == "N"
        assert request.query["SYMB"] == "QQQ" and request.query["EXCD"] == "NAS"
    assert gets[-1].query["SYMB"] == "SPY" and gets[-1].query["NEXT"] == ""
