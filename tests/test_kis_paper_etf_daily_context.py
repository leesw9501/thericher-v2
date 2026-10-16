from __future__ import annotations

import gzip
import json
import posixpath
from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_etf_daily_context as data
from thericher_v2.execution import kis_market_data as native


class Clock:
    def __init__(self) -> None:
        self.start = datetime(2026, 10, 13, 17, 30, tzinfo=UTC)
        self.elapsed = 0.0

    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.elapsed)

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, delay: float) -> None:
        self.elapsed += delay


class Response:
    status = 200
    headers = {"tr_cont": "F"}

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def row(day: date, *, close: str = "101") -> dict[str, str]:
    return dict(
        xymd=day.strftime("%Y%m%d"), open="100", high="110", low="90", clos=close, tvol="1000"
    )


class Opener:
    def __init__(self, clock: Clock, sessions: tuple[data.CompletedSession, ...]) -> None:
        self.clock = clock
        self.calls: list[tuple[str, dict, float]] = []
        self.rows = [row(date(2026, 10, 13)), *[row(s.provider_date) for s in reversed(sessions)]]
        self.short_symbol = None
        self.conflict = False
        self.stuck = False
        self.rate_limit = False
        self.fail_after = None

    def open(self, request: object, *, timeout: float) -> Response:
        method = request.get_method()
        query = {k: v[0] for k, v in parse_qs(urlsplit(request.full_url).query).items()}
        self.calls.append((method, query, self.clock.monotonic()))
        assert 0 < timeout <= 15
        if method == "POST":
            return Response({"access_token": "synthetic-token"})
        assert urlsplit(request.full_url).path == native.KIS_PAPER_DAILY_PATH
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise OSError("private body must not escape")
        if self.rate_limit:
            result = Response({"msg_cd": "EGW00201"})
            result.status = 429
            return result
        candidate = self.rows
        if self.short_symbol == query["SYMB"]:
            candidate = candidate[:-1]
        rows = [r for r in candidate if r["xymd"] <= query["BYMD"]][:100]
        if self.stuck and sum(c[0] == "GET" for c in self.calls) > 1:
            rows = self.rows[:100]
        if self.conflict and sum(c[0] == "GET" for c in self.calls) > 1:
            rows = [dict(self.rows[1], clos="102"), *rows[:99]]
        return Response(dict(rt_cd="0", output1={}, output2=rows))


@pytest.fixture
def intake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    clock = Clock()
    calendar = data.completed_sessions(clock.now())
    opener = Opener(clock, calendar)
    monkeypatch.setattr(native.urllib.request, "build_opener", lambda *args: opener)
    cache = tmp_path / "market" / data.CACHE_ROOT.name
    artifacts = tmp_path / "artifacts" / data.ARTIFACT_ROOT.name
    kwargs = dict(
        cache_root=cache,
        artifact_root=artifacts,
        control_root=cache.parent / "collection-control-v1",
        repository_root=tmp_path / "repo",
        clock=clock.now,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )
    # File publication is variable work and must precede final pacing.
    original_write = data.storage._write_bytes_and_sync

    def slow_write(path: Path, payload: bytes) -> None:
        original_write(path, payload)
        clock.sleep(0.07)

    monkeypatch.setattr(data.storage, "_write_bytes_and_sync", slow_write)
    return clock, opener, kwargs


def collect(intake, **extra):
    clock, opener, kwargs = intake
    return data.collect_daily_contexts(
        native.KisPaperMarketDataConfig("synthetic-key", "secret"), **{**kwargs, **extra}
    )


def load_ref(ref, kwargs, count=253):
    return data.read_daily_context(
        *ref,
        cache_root=kwargs["cache_root"],
        required_count=count,
        repository_root=kwargs["repository_root"],
    )


def test_complete_native_input_and_early_spy_two(intake) -> None:
    clock, opener, kwargs = intake
    result = collect(intake)
    assert (result.status, result.reason, result.token_posts, result.daily_gets) == (
        "complete",
        None,
        1,
        12,
    )
    assert len(result.receipts) == 5
    assert clock.elapsed < 120
    baseline = load_ref(result.receipts[0], kwargs, 2)
    assert baseline.receipt.symbol == "SPY" and not baseline.receipt.complete_253
    assert [o.provider_date for o in baseline.observations] == [
        date(2026, 10, 9),
        date(2026, 10, 12),
    ]
    assert baseline.receipt.first_available_at_utc > baseline.receipt.observed_at_utc
    for ref, symbol in zip(result.receipts[1:], data.ETF_VENUES, strict=True):
        context = load_ref(ref, kwargs)
        assert context.receipt.complete_253 and len(context.bars) == 253
        assert context.receipt.symbol == symbol
        assert all(type(b) is Bar and b.timeframe is Timeframe.D1 for b in context.bars)
        assert context.receipt.provider_dates[0] == date(2025, 10, 9)
        assert context.receipt.provider_dates[-1] == date(2026, 10, 12)
        assert context.receipt.outside_window_count == 1
        assert context.receipt.page_count == 3
        last = context.observations[-1]
        assert last.provider_date == last.bar.start_ts.date() == date(2026, 10, 12)
        assert last.bar.start_ts.astimezone(ZoneInfo("America/New_York")).date() == date(
            2026, 10, 11
        )
        assert len(load_ref(ref, kwargs, 21).bars) == 21
        assert "historical_point_in_time_not_qualified" in context.receipt.qualifications
        assert context.receipt.first_available_at_utc != last.bar.start_ts
        assert all(h.startswith("sha256:") for _, h in context.receipt.source_code_sha256)
    assert {q["EXCD"] for m, q, _ in opener.calls if m == "GET"} == {"AMS", "NAS"}
    assert not (kwargs["cache_root"] / ".collector.lock.d").exists()
    safe = json.dumps(result.safe_payload())
    assert "synthetic-key" not in safe and "secret" not in safe and "synthetic-token" not in safe
    for path in kwargs["artifact_root"].rglob("*.json"):
        text = path.read_text()
        assert "synthetic-token" not in text and '"open"' not in text and '"clos"' not in text


@pytest.mark.parametrize("options", [{}, {"requested_symbols": None},
                                      {"requested_symbols": tuple(data.ETF_VENUES)}])
def test_default_symbol_scope_and_result_schema_stay_four(intake, options):
    _, opener, _ = intake
    result = collect(intake, **options)
    assert result.status == "complete" and result.daily_gets == 12
    assert result.requested_symbols == tuple(data.ETF_VENUES)
    assert list(dict.fromkeys(q["SYMB"] for method, q, _ in opener.calls if method == "GET")) == [
        "SPY", "QQQ", "TLT", "GLD",
    ]
    assert "requested_symbols" not in result.safe_payload()


def test_required_three_scope_omits_short_qqq_without_weakening_tails(intake):
    _, opener, kwargs = intake
    opener.short_symbol = "QQQ"
    symbols = ("SPY", "TLT", "GLD")
    result = collect(intake, requested_symbols=symbols)
    assert (result.status, result.reason, result.token_posts, result.daily_gets) == (
        "complete", None, 1, 9,
    )
    assert result.requested_symbols == symbols
    assert result.safe_payload()["requested_symbols"] == list(symbols)
    assert {q["SYMB"] for method, q, _ in opener.calls if method == "GET"} == set(symbols)
    assert all(gap >= 1.25 - 1e-9 for gap in result.http_start_gaps_seconds)
    refs = [ref for ref in result.receipts if ref[0].parent.name != "SPY-baseline2"]
    assert [load_ref(ref, kwargs).receipt.symbol for ref in refs] == list(symbols)
    assert all(load_ref(ref, kwargs).receipt.complete_253 for ref in refs)


@pytest.mark.parametrize("symbol", ["SPY", "TLT", "GLD"])
def test_subset_missing_required_tail_stays_incomplete(intake, symbol):
    _, opener, kwargs = intake
    opener.short_symbol = symbol
    result = collect(intake, requested_symbols=("SPY", "TLT", "GLD"))
    assert result.status == "incomplete" and result.reason == "completed_sessions_missing"
    ref = next(ref for ref in result.receipts if ref[0].parent.name == symbol)
    with pytest.raises(data.DailyContextError, match="completed_sessions_missing"):
        load_ref(ref, kwargs)


@pytest.mark.parametrize("symbols", [("GLD",), ("TLT", "SPY"), tuple(data.ETF_VENUES)])
def test_explicit_scope_preserves_requested_order_and_page_bounds(intake, symbols):
    _, opener, _ = intake
    result = collect(intake, requested_symbols=symbols)
    assert result.status == "complete" and result.daily_gets == 3 * len(symbols)
    assert result.requested_symbols == symbols
    actual = list(dict.fromkeys(q["SYMB"] for method, q, _ in opener.calls if method == "GET"))
    assert actual == list(symbols)


class _SymbolSubclass(str):
    pass


@pytest.mark.parametrize("symbols", [(), [], ["SPY"], "SPY", {"SPY"}, {"SPY": "AMS"},
    ("SPY", "SPY"), ("SPY", "QQQ", "TLT", "GLD", "SPY"), ("spy",), (" SPY",),
    ("SPY ",), ("IWM",), (True,), (None,), ([],), (_SymbolSubclass("SPY"),)])
def test_invalid_symbol_scope_rejected_before_files_or_client(intake, symbols, monkeypatch):
    _, opener, kwargs = intake

    def denied(*args, **kwargs):
        pytest.fail("invalid_scope_must_not_reach_files_or_client")

    monkeypatch.setattr(data, "_external", denied)
    monkeypatch.setattr(data.native, "KisPaperMarketDataClient", denied)
    with pytest.raises(data.DailyContextError, match="invalid_contract"):
        collect(intake, requested_symbols=symbols)
    assert not opener.calls and not kwargs["cache_root"].exists()


@pytest.mark.parametrize("fault,reason", [("conflict", "daily_duplicate_conflict"),
                                         ("stuck", "cursor_not_advancing"),
                                         ("rate_limit", "rate_limited")])
def test_subset_preserves_native_first_faults(intake, fault, reason):
    _, opener, _ = intake
    setattr(opener, fault, True)
    result = collect(intake, requested_symbols=("SPY", "TLT", "GLD"))
    assert result.status == "incomplete" and result.reason == reason
    assert result.daily_gets <= 2 and result.token_posts == 1


def test_archive_replay_ignores_today_and_auth(intake, monkeypatch: pytest.MonkeyPatch) -> None:
    clock, opener, kwargs = intake
    result = collect(intake)
    before = load_ref(result.receipts[1], kwargs)
    files = {
        p: data._sha(p.read_bytes())
        for root in (kwargs["cache_root"], kwargs["artifact_root"])
        for p in root.rglob("*")
        if p.is_file()
    }
    monkeypatch.setattr(data, "completed_sessions", lambda *args: pytest.fail("calendar(now)"))
    monkeypatch.setattr(data, "_source_pins", lambda: pytest.fail("current source equality gate"))
    monkeypatch.setattr(
        native.KisPaperMarketDataClient,
        "ensure_authenticated",
        lambda *args: pytest.fail("archive authenticated"),
    )
    for offset in (timedelta(days=1), timedelta(days=366)):
        clock.start += offset
        assert load_ref(result.receipts[1], kwargs) == before
    assert len(opener.calls) == 13
    assert files == {p: data._sha(p.read_bytes()) for p in files}


@pytest.mark.parametrize("kind", ["raw", "source", "receipt"])
def test_hash_tamper_kills(intake, kind: str) -> None:
    _, _, kwargs = intake
    result = collect(intake)
    ref = result.receipts[1]
    context = load_ref(ref, kwargs)
    path = (
        kwargs["cache_root"] / context.receipt.raw_relative_path
        if kind == "raw"
        else ref[0].with_name("source.json")
        if kind == "source"
        else ref[0]
    )
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(data.DailyContextError, match="hash_mismatch"):
        load_ref(ref, kwargs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("page_count", True),
        ("page_count", 5),
        ("token_interval_seconds", 1),
        ("exchange", "NAS"),
        ("excluded_current_us_date", "2026-10-14"),
        ("raw_relative_path", "../private.csv.gz"),
        ("kind", "other"),
        ("qualifications", ["provider_final"]),
        ("raw_size_bytes", "500"),
    ],
)
def test_receipt_structural_type_and_date_kills(intake, field, value) -> None:
    _, _, kwargs = intake
    ref = collect(intake).receipts[1]
    document = json.loads(ref[0].read_bytes())
    document[field] = value
    payload = data._json(document)
    ref[0].write_bytes(payload)
    with pytest.raises(data.DailyContextError):
        load_ref((ref[0], data._sha(payload)), kwargs)


def test_retained_calendar_dated_session_kills(intake) -> None:
    _, _, kwargs = intake
    ref = collect(intake).receipts[1]
    document = json.loads(ref[0].read_bytes())
    document["calendar"][-1]["provider_date"] = "2026-10-13"
    payload = data._json(document)
    ref[0].write_bytes(payload)
    with pytest.raises(data.DailyContextError):
        load_ref((ref[0], data._sha(payload)), kwargs)


def test_missing_session_is_partial_not_imputed(intake) -> None:
    _, opener, kwargs = intake
    opener.short_symbol = "GLD"
    result = collect(intake)
    assert result.status == "incomplete" and result.reason == "completed_sessions_missing"
    assert result.daily_gets == 13 and result.token_posts == 1
    document = json.loads(result.receipts[-1][0].read_bytes())
    assert len(document["provider_dates"]) == 252
    with pytest.raises(data.DailyContextError, match="completed_sessions_missing"):
        load_ref(result.receipts[-1], kwargs)
    assert len(load_ref(result.receipts[-1], kwargs, 21).bars) == 21


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("conflict", "daily_duplicate_conflict"),
        ("stuck", "cursor_not_advancing"),
        ("rate_limit", "rate_limited"),
    ],
)
def test_first_fault_stops_without_retries(intake, fault, reason) -> None:
    _, opener, _ = intake
    setattr(opener, fault, True)
    result = collect(intake)
    assert result.status == "incomplete" and result.reason == reason
    assert result.daily_gets <= 2 and result.token_posts == 1
    assert len(opener.calls) == result.daily_gets + 1


def test_identical_overlaps_deduplicated(intake, monkeypatch: pytest.MonkeyPatch) -> None:
    _, opener, kwargs = intake
    original = opener.open

    def overlap(request, *, timeout):
        response = original(request, timeout=timeout)
        if request.get_method() == "GET":
            response.payload["output2"] = (
                response.payload["output2"][:99] + response.payload["output2"][:1]
            )
        return response

    monkeypatch.setattr(opener, "open", overlap)
    result = collect(intake)
    assert result.status == "complete" and result.daily_gets == 12
    assert load_ref(result.receipts[1], kwargs).receipt.duplicate_count == 3


def test_transport_failure_preserves_published_spy_baseline(intake) -> None:
    _, opener, kwargs = intake
    opener.fail_after = 2
    result = collect(intake)
    assert result.reason == "transport_failure" and result.daily_gets == 2
    assert len(result.receipts) == 1
    assert len(load_ref(result.receipts[0], kwargs, 2).bars) == 2
    assert "private body" not in json.dumps(result.safe_payload())


def test_slow_rechecks_and_publication_cannot_shorten_final_start_gaps(intake) -> None:
    clock, opener, _ = intake
    result = collect(intake, before_http=lambda: clock.sleep(0.2))
    assert result.status == "complete"
    actual = [start for _, _, start in opener.calls]
    assert all(b - a >= 1.25 - 1e-9 for a, b in zip(actual, actual[1:], strict=False))
    assert all(gap >= 1.25 - 1e-9 for gap in result.http_start_gaps_seconds)


def test_failed_recheck_never_marks_or_delegates_http(intake) -> None:
    _, opener, kwargs = intake

    def fail():
        raise data.DailyContextError("invalid_contract")

    result = collect(intake, before_http=fail)
    assert result.reason == "invalid_contract" and result.token_posts == result.daily_gets == 0
    assert opener.calls == [] and result.http_start_gaps_seconds == ()
    assert not (kwargs["control_root"] / "token-request.json").exists()


def test_global_deadline_includes_recheck_work(intake) -> None:
    clock, opener, kwargs = intake
    result = collect(intake, before_http=lambda: clock.sleep(121))
    assert result.reason == "deadline_exceeded"
    assert opener.calls == [] and result.token_posts == 0
    assert not (kwargs["control_root"] / "token-request.json").exists()


def test_global_maximum_sixteen_gets_with_four_short_pages_each(intake) -> None:
    _, opener, _ = intake
    opener.rows = opener.rows[:90]
    # A sparse page with progressively older valid dates consumes the finite budget.
    original = opener.open

    def small(request, *, timeout):
        response = original(request, timeout=timeout)
        if request.get_method() == "GET":
            query = parse_qs(urlsplit(request.full_url).query)
            anchor = datetime.strptime(query["BYMD"][0], "%Y%m%d").date()
            response.payload["output2"] = [row(anchor - timedelta(days=1))]
        return response

    opener.open = small
    result = collect(intake)
    assert (result.daily_gets, result.token_posts) == (16, 1)
    assert result.status == "incomplete"
    assert len(opener.calls) == 17


@pytest.mark.parametrize("floor", [60, 300])
def test_not_due_yields_without_sleep_or_timestamp_reset(intake, floor: int) -> None:
    clock, opener, kwargs = intake
    root = kwargs["control_root"]
    root.mkdir(parents=True)
    path = root / "token-request.json"
    payload = data._json(
        dict(schema_version=1, last_token_request_started_at_utc=clock.now().isoformat())
    )
    path.write_bytes(payload)
    result = collect(intake, token_interval_seconds=floor)
    assert result.reason == "token_request_not_due" and result.token_posts == 0
    assert result.next_due_utc == clock.start + timedelta(seconds=floor)
    assert opener.calls == [] and clock.elapsed == 0 and path.read_bytes() == payload


@pytest.mark.parametrize("fault", ["owner", "token_busy", "token_corrupt"])
def test_claim_busy_corrupt_fail_closed_no_reclamation(intake, fault: str) -> None:
    clock, opener, kwargs = intake
    if fault == "owner":
        root = kwargs["cache_root"] / ".collector.lock.d"
        root.mkdir(parents=True)
        before = list(root.iterdir())
    elif fault == "token_busy":
        root = kwargs["control_root"] / "token-request.lock.d"
        root.mkdir(parents=True)
        before = list(root.iterdir())
    else:
        root = kwargs["control_root"] / "token-request.json"
        root.parent.mkdir(parents=True)
        root.write_bytes(b"corrupt")
        before = root.read_bytes()
    result = collect(intake)
    assert result.status == "incomplete" and opener.calls == [] and clock.elapsed == 0
    assert root.exists()
    assert (root.read_bytes() if root.is_file() else list(root.iterdir())) == before


@pytest.mark.parametrize(
    "now,last",
    [
        ("2026-10-14T03:59:00+00:00", "2026-10-12"),
        ("2026-10-14T04:01:00+00:00", "2026-10-13"),
        ("2026-11-27T23:00:00+00:00", "2026-11-25"),
        ("2026-03-09T15:00:00+00:00", "2026-03-06"),
        ("2026-11-02T15:00:00+00:00", "2026-10-30"),
        ("2026-09-07T17:00:00+00:00", "2026-09-04"),
    ],
)
def test_current_calendar_midnight_holidays_dst_and_early_close(now, last) -> None:
    captured = datetime.fromisoformat(now)
    sessions = data.completed_sessions(captured)
    assert len(sessions) == len({s.provider_date for s in sessions}) == 253
    assert sessions[-1].provider_date.isoformat() == last
    assert all(
        s.provider_date < captured.astimezone(ZoneInfo("America/New_York")).date()
        and s.calendar_close_utc < captured
        for s in sessions
    )


def test_early_close_retained_as_calendar_not_finality() -> None:
    sessions = data.completed_sessions(datetime(2026, 11, 30, 15, tzinfo=UTC))
    assert sessions[-1].provider_date == date(2026, 11, 27)
    assert sessions[-1].calendar_close_utc.hour == 18


def test_old_namespace_and_repository_rejected_before_client(intake) -> None:
    _, opener, kwargs = intake
    with pytest.raises(data.DailyContextError, match="invalid_paths"):
        collect(intake, cache_root=kwargs["cache_root"].with_name("current-paper-etf-input-v1"))
    with pytest.raises(data.DailyContextError, match="invalid_paths"):
        collect(intake, repository_root=kwargs["cache_root"].parent)
    assert opener.calls == []


def test_source_tamper_new_date_even_with_valid_raw_hash_rejected(intake) -> None:
    _, _, kwargs = intake
    ref = collect(intake).receipts[1]
    context = load_ref(ref, kwargs)
    path = kwargs["cache_root"] / context.receipt.raw_relative_path
    packed = gzip.compress(gzip.decompress(path.read_bytes()).replace(b"2026-10-12", b"2026-10-13"))
    path.write_bytes(packed)
    document = json.loads(ref[0].read_bytes())
    document["raw_sha256"], document["raw_size_bytes"] = data._sha(packed), len(packed)
    source = dict(document)
    source.pop("source_sha256")
    source.pop("first_available_at_utc")
    encoded_source = data._json(source)
    ref[0].with_name("source.json").write_bytes(encoded_source)
    document["source_sha256"] = data._sha(encoded_source)
    encoded = data._json(document)
    ref[0].write_bytes(encoded)
    with pytest.raises(data.DailyContextError, match="archive_invalid"):
        load_ref((ref[0], data._sha(encoded)), kwargs)


def test_invalid_provider_date_even_outside_window_kills(intake) -> None:
    _, opener, _ = intake
    opener.rows[0]["xymd"] = "20260231"
    result = collect(intake)
    assert result.reason == "daily_response_invalid" and result.daily_gets == 1
    assert result.receipts == ()


def test_overdue_response_cannot_be_published_complete(intake) -> None:
    clock, opener, _ = intake
    original = opener.open

    def late(request, *, timeout):
        response = original(request, timeout=timeout)
        if request.get_method() == "GET":
            clock.sleep(121)
        return response

    opener.open = late
    result = collect(intake)
    assert result.reason == "deadline_exceeded" and result.daily_gets == 1
    assert result.receipts == ()


@pytest.mark.parametrize("fault", ["venue", "minute", "adjustment", "host"])
def test_daily_only_native_boundary_rejects_route_drift(intake, fault: str) -> None:
    _, opener, _ = intake
    query = dict(AUTH="", EXCD="AMS", SYMB="SPY", GUBN="0", BYMD="20261013", MODP="0")
    url = native.KIS_PAPER_MARKET_DATA_BASE_URL + native.KIS_PAPER_DAILY_PATH
    if fault == "venue":
        query["EXCD"] = "NAS"
    elif fault == "minute":
        url = native.KIS_PAPER_MARKET_DATA_BASE_URL + native.KIS_PAPER_MINUTE_PATH
    elif fault == "adjustment":
        query["MODP"] = "1"
    else:
        url = "https://example.invalid" + native.KIS_PAPER_DAILY_PATH
    with pytest.raises((data.DailyContextError, native.KisPaperMarketDataError)):
        data._DailyOnlyTransport().request(
            native.KisMarketDataRequest(
                "GET",
                url,
                {"tr_id": native.KIS_PAPER_DAILY_TR_ID},
                query=query,
                daily_symbol_exchanges=data._SCOPE,
            )
        )
    assert opener.calls == []


def test_archive_missing_pin_fails_before_file_io(tmp_path: Path) -> None:
    with pytest.raises(data.DailyContextError, match="invalid_contract"):
        data.read_daily_context(tmp_path / "absent", None)


def test_rate_cooldown_yields_named_next_due_no_foreground_wait(intake) -> None:
    clock, opener, kwargs = intake
    root = kwargs["control_root"]
    root.mkdir(parents=True)
    state = dict(
        schema_version=1,
        last_request_started_at_utc=None,
        retry_not_before_utc=(clock.now() + timedelta(seconds=60)).isoformat(),
        last_rate_limit_at_utc=clock.now().isoformat(),
    )
    (root / "request-rate.json").write_bytes(data._json(state))
    result = collect(intake)
    assert result.reason == "request_not_due" and result.daily_gets == result.token_posts == 0
    assert result.next_due_utc == clock.start + timedelta(seconds=60)
    assert opener.calls == [] and clock.elapsed == 0


def test_observation_rejects_nominal_date_shift() -> None:
    nominal = date(2026, 10, 12)
    bar = Bar(
        "SPY",
        "US",
        Timeframe.D1,
        datetime(2026, 10, 12, tzinfo=UTC),
        "100",
        "110",
        "90",
        "101",
        "1000",
    )
    with pytest.raises(data.DailyContextError, match="invalid_contract"):
        data.DailyObservation(nominal - timedelta(days=1), bar)


@pytest.mark.parametrize("floor", [60, 300])
def test_token_mark_is_after_slow_recheck_and_request_wait(intake, floor: int) -> None:
    clock, opener, kwargs = intake
    root = kwargs["control_root"]
    root.mkdir(parents=True)
    rate = dict(
        schema_version=1,
        last_request_started_at_utc=clock.now().isoformat(),
        retry_not_before_utc=None,
        last_rate_limit_at_utc=None,
    )
    (root / "request-rate.json").write_bytes(data._json(rate))
    result = collect(intake, token_interval_seconds=floor, before_http=lambda: clock.sleep(2))
    assert result.status == "complete" and result.token_posts == 1
    first_http = opener.calls[0][2]
    assert first_http == 3
    state = json.loads((root / "token-request.json").read_bytes())
    mark = datetime.fromisoformat(state["last_token_request_started_at_utc"])
    assert mark == clock.start + timedelta(seconds=first_http)
    gate = data.gates.KisPaperMarketDataTokenStartGate(
        control_root=root, clock=clock.now, minimum_request_interval_seconds=floor
    )
    assert gate.snapshot().next_token_request_not_before_utc == mark + timedelta(seconds=floor)
    assert not (root / "token-request.lock.d").exists()


@pytest.mark.parametrize("floor", [60, 300])
def test_atomic_competing_claim_after_precheck_defers_without_post(intake, floor: int) -> None:
    clock, opener, kwargs = intake
    gate = data.gates.KisPaperMarketDataTokenStartGate(
        control_root=kwargs["control_root"], clock=clock.now, minimum_request_interval_seconds=floor
    )

    def competing_claim() -> None:
        clock.sleep(0.2)
        assert gate.claim_token_request_start()

    result = collect(intake, token_interval_seconds=floor, before_http=competing_claim)
    assert result.reason == "token_request_not_due"
    assert result.token_posts == result.daily_gets == 0 and opener.calls == []
    state = gate.snapshot()
    assert state.last_token_request_started_at_utc == clock.start + timedelta(seconds=0.2)
    assert result.next_due_utc == state.next_token_request_not_before_utc


@pytest.fixture
def linux_paths(monkeypatch: pytest.MonkeyPatch):
    # Execute the actual helper with Linux path semantics and synthetic mount facts.
    class LinuxPath(PurePosixPath):
        mounts = {"/app/market_data", "/app/model_artifacts"}
        links = set()
        junctions = set()

        def absolute(self):
            return self

        def resolve(self):
            return type(self)(posixpath.normpath(str(self)))

        def is_mount(self):
            return str(self) in self.mounts

        def is_symlink(self):
            return str(self) in self.links

        def is_junction(self):
            return str(self) in self.junctions

    monkeypatch.setattr(data, "Path", LinuxPath)
    monkeypatch.setattr(data, "os", SimpleNamespace(name="posix"))
    return LinuxPath


@pytest.mark.parametrize(
    "kind,relative",
    [
        ("market_data", "us_equities/kis_paper_private/etf-daily-context-v1"),
        ("market_data", "us_equities/kis_paper_private/collection-control-v1"),
        ("model_artifacts", "data/etf-daily-context-v1/run/SPY/receipt.json"),
    ],
)
def test_linux_known_actual_mount_descendants_accepted(linux_paths, kind, relative) -> None:
    path = linux_paths("/app") / kind / relative
    assert data._external(path, linux_paths("/app"), kind) == path


@pytest.mark.parametrize(
    "path,kind",
    [
        ("/app/market_data/us_equities", "market_data"),
        ("/app/model_artifacts/data", "model_artifacts"),
        ("/app/src/artifacts", "model_artifacts"),
        ("/app/ordinary/market_data/data", "market_data"),
    ],
)
def test_linux_unmounted_repository_children_rejected(linux_paths, path, kind) -> None:
    linux_paths.mounts = {"/app"}
    with pytest.raises(data.DailyContextError, match="invalid_paths"):
        data._external(linux_paths(path), linux_paths("/app"), kind)


@pytest.mark.parametrize(
    "path,kind",
    [
        ("/app/model_artifacts/data", "market_data"),
        ("/app/market_data/data", "model_artifacts"),
        ("/app/model_artifacts/../src", "model_artifacts"),
    ],
)
def test_linux_mount_role_swap_or_escape_rejected(linux_paths, path, kind) -> None:
    with pytest.raises(data.DailyContextError, match="invalid_paths"):
        data._external(linux_paths(path), linux_paths("/app"), kind)


@pytest.mark.parametrize("fault", ["links", "junctions"])
def test_linux_mount_does_not_bypass_reparse_checks(linux_paths, fault) -> None:
    setattr(linux_paths, fault, {"/app/model_artifacts/data"})
    with pytest.raises(data.DailyContextError, match="invalid_paths"):
        data._external(linux_paths("/app/model_artifacts/data/run"), linux_paths("/app"))


def test_linux_ordinary_repo_with_similarly_named_child_rejected(linux_paths) -> None:
    linux_paths.mounts = {"/tmp/repo/model_artifacts"}
    with pytest.raises(data.DailyContextError, match="invalid_paths"):
        data._external(linux_paths("/tmp/repo/model_artifacts/data"), linux_paths("/tmp/repo"))


@pytest.mark.parametrize("token_state", ["not_due", "busy", "corrupt", "absent"])
def test_borrowed_paper_token_reuses_only_gets_without_touching_token_state(
    intake, monkeypatch, token_state
) -> None:
    clock, opener, kwargs = intake
    borrowed = "synthetic-owned-bearer"
    control = kwargs["control_root"]
    control.mkdir(parents=True)
    token_path = control / "token-request.json"
    lock = control / "token-request.lock.d"
    if token_state == "not_due":
        token_path.write_bytes(
            data._json(
                dict(schema_version=1, last_token_request_started_at_utc=clock.now().isoformat())
            )
        )
    elif token_state == "busy":
        lock.mkdir()
    elif token_state == "corrupt":
        token_path.write_bytes(b"corrupt")
    before = token_path.read_bytes() if token_path.exists() else None
    original = opener.open
    authorizations = []

    def using_same_bearer(request, *, timeout):
        assert request.get_method() == "GET"
        authorizations.append(request.get_header("Authorization"))
        return original(request, timeout=timeout)

    monkeypatch.setattr(opener, "open", using_same_bearer)
    result = collect(intake, access_token=borrowed)
    assert result.status == "complete" and result.token_posts == 0 and result.daily_gets == 12
    assert authorizations == [f"Bearer {borrowed}"] * 12
    assert (token_path.read_bytes() if token_path.exists() else None) == before
    assert lock.exists() == (token_state == "busy")
    assert all(method == "GET" for method, _, _ in opener.calls)
    safe = json.dumps(result.safe_payload())
    assert borrowed not in safe
    for root in (kwargs["cache_root"], kwargs["artifact_root"]):
        assert all(borrowed.encode() not in p.read_bytes() for p in root.rglob("*") if p.is_file())
    assert len(load_ref(result.receipts[1], kwargs).bars) == 253


@pytest.mark.parametrize(
    "token", ["", " ", "leading space", "\n", "bad\rheader", "\u2603", 1, False, b"bytes", object()]
)
def test_invalid_borrowed_token_fails_before_files_or_client(intake, token) -> None:
    _, opener, kwargs = intake
    with pytest.raises(data.DailyContextError, match="invalid_contract"):
        collect(intake, access_token=token)
    assert opener.calls == []
    assert not kwargs["cache_root"].exists() and not kwargs["artifact_root"].exists()


def test_rejected_borrowed_token_does_not_retry_or_authenticate(intake, monkeypatch) -> None:
    _, opener, kwargs = intake
    calls = []

    def reject(request, *, timeout):
        calls.append(request.get_method())
        response = Response(dict(rt_cd="1"))
        response.status = 401
        return response

    monkeypatch.setattr(opener, "open", reject)
    result = collect(intake, access_token="synthetic-rejected-bearer")
    assert calls == ["GET"]
    assert result.reason == "daily_response_rejected" and result.token_posts == 0
    assert result.daily_gets == 1 and result.receipts == ()
    assert not (kwargs["control_root"] / "token-request.json").exists()


def test_borrowed_token_rate_cooldown_ignores_corrupt_fresh_token_gate(intake) -> None:
    clock, opener, kwargs = intake
    control = kwargs["control_root"]
    control.mkdir(parents=True)
    token_path = control / "token-request.json"
    token_path.write_bytes(b"corrupt")
    state = dict(
        schema_version=1,
        last_request_started_at_utc=None,
        retry_not_before_utc=(clock.now() + timedelta(seconds=60)).isoformat(),
        last_rate_limit_at_utc=clock.now().isoformat(),
    )
    (control / "request-rate.json").write_bytes(data._json(state))
    result = collect(intake, access_token="synthetic-borrowed-bearer")
    assert result.reason == "request_not_due" and result.next_due_utc == clock.now() + timedelta(
        seconds=60
    )
    assert result.token_posts == result.daily_gets == 0 and opener.calls == []
    assert clock.elapsed == 0 and token_path.read_bytes() == b"corrupt"
