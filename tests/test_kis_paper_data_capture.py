from __future__ import annotations

import io
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution import kis_market_data as m
from thericher_v2.execution import kis_paper_data_capture as c
from thericher_v2.execution.kis_market_data_rate_gate import KisPaperMarketDataTokenStartGate
from thericher_v2.execution.kis_stock_intraday_foundation import COHORT, FoundationOwner

KEY, SECRET, TOKEN = "SYN_APP_KEY_9b31", "SYN_APP_SECRET_351c", "SYN_TOKEN_84ef"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
        self.tick = 0.0
        self.sleeps = []

    def utc(self):
        return self.now

    def monotonic(self):
        return self.tick

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.tick += seconds

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.advance(seconds)


class Response:
    def __init__(self, payload, *, on_read=None, status=200, headers=None):
        self.data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status, self.headers = status, headers or {}
        self.on_read, self.closed = on_read, False

    def read(self, size=-1):
        if self.on_read:
            self.on_read()
        return self.data[:size] if size >= 0 else self.data

    def close(self):
        self.closed = True


class Opener:
    def __init__(self):
        self.responses, self.calls = [], []
        self.before_open = None

    def open(self, request, timeout):
        # Deliberately retain only route/method facts, never auth headers/body.
        self.calls.append(
            (request.get_method(), urllib.parse.urlsplit(request.full_url).path, timeout)
        )
        if self.before_open:
            self.before_open(request)
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def minute(symbol="AAPL", *, key="20261016155900", scope=None, first="20261016", last="20261016"):
    scope = scope or {symbol: frozenset({"NAS"})}
    return c.CaptureQuery(
        m.KisPaperHistoricalMinuteQuery(
            symbol=symbol,
            exchange="NAS",
            approved_symbol_exchanges=scope,
            include_previous_day=key is not None,
            continuation_next="1" if key else None,
            continuation_key=key,
        ),
        first,
        last,
    )


def daily(symbol="XLK", *, day="20261016", first="20261016", last="20261016", mode=None):
    scope = {symbol: frozenset({"AMS"})}
    query = (
        m.KisPaperDailyAdjustmentProbeQuery(
            symbol=symbol,
            by_date=day,
            exchange="AMS",
            adjustment_mode=mode,
            approved_symbol_exchanges=scope,
        )
        if mode is not None
        else m.KisPaperDailyQuery(
            symbol=symbol, by_date=day, exchange="AMS", approved_symbol_exchanges=scope
        )
    )
    return c.CaptureQuery(
        query,
        first,
        last,
    )


def token(**kwargs):
    return Response(dict(access_token=TOKEN), **kwargs)


def minute_body(**kwargs):
    row = dict(
        xymd="20261016",
        xhms="155900",
        kymd="20261017",
        khms="045900",
        open="10",
        high="12",
        low="9",
        last="11",
        evol="100",
    )
    return Response(dict(rt_cd="0", output1={}, output2=[row]), **kwargs)


def daily_body(**kwargs):
    row = dict(xymd="20261016", open="10", high="12", low="9", clos="11", tvol="100")
    return Response(dict(rt_cd="0", output1={}, output2=[row]), **kwargs)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    clock, opener = Clock(), Opener()

    class NativeClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now.astimezone(tz) if tz else clock.now.replace(tzinfo=None)

    monkeypatch.setattr(m, "datetime", NativeClock)
    monkeypatch.setattr(c, "_MARKET_BASE", tmp_path / "M")
    monkeypatch.setattr(c, "_ARTIFACT_BASE", tmp_path / "A")
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: opener)
    monkeypatch.setattr(
        socket.socket, "connect", lambda *_args: pytest.fail("real network forbidden")
    )
    root = SimpleNamespace(
        clock=clock,
        opener=opener,
        market=tmp_path / "M/capture",
        artifact=tmp_path / "A/capture",
        loads=[],
    )

    def loader():
        root.loads.append(1)
        return m.KisPaperMarketDataConfig(app_key=KEY, app_secret=SECRET)

    def session(queries=None, **kwargs):
        return c.KisPaperDataCaptureSession(
            queries=queries or (minute(), daily()),
            market_root=kwargs.pop("market_root", root.market),
            artifact_root=kwargs.pop("artifact_root", root.artifact),
            limits=kwargs.pop(
                "limits", c.CaptureLimits(max_get=5, max_retries=2, wall_seconds=120)
            ),
            owner_ready=kwargs.pop("owner_ready", lambda: c.CaptureReadiness(True)),
            config_loader=kwargs.pop("config_loader", loader),
            clock=clock.utc,
            monotonic=clock.monotonic,
            sleeper=clock.sleep,
            **kwargs,
        )

    root.session = session
    return root


def state(rig):
    return json.loads((rig.artifact / "capture-state.json").read_bytes())


def assert_released(rig):
    assert not (rig.market / "owner.lock.d").exists()
    assert not (rig.artifact / "owner.lock.d").exists()


def test_native_mixed_minute_daily_minute_one_client_one_POST_and_private_references(rig):
    q, d = minute(), daily()
    q2 = minute(key="20261016155800")
    rig.opener.responses = [
        token(),
        minute_body(),
        daily_body(),
        Response(dict(rt_cd="0", output1={}, output2=[])),
    ]
    with rig.session((q, d, q2)) as session:
        a = session.capture(q)
        client = session._client
        b = session.capture(d)
        assert session._client is client and client._minute_route == "historical_timestamp"
        session.capture(q2)
        assert session.capture(q).cache_hit
        assert a.status == b.status == "ACCEPTED" and a.row_count == b.row_count == 1
        assert client.call_counts.token_attempts == 1
        assert client.call_counts.minute_page_attempts == 2
        assert client.call_counts.daily_page_attempts == 1
        assert session.progress["GET"] == 3 and session.progress["POST"] == 1
        assert session.progress["pending"] is None
    assert [v[0] for v in rig.opener.calls] == ["POST", "GET", "GET", "GET"]
    assert rig.loads == [1] and len(rig.clock.sleeps) == 3
    for p in rig.artifact.rglob("*"):
        if p.is_file():
            text = p.read_text()
            assert '"open"' not in text and '"output2"' not in text
            assert not any(value in text for value in (KEY, SECRET, TOKEN))
    for p in rig.market.rglob("*"):
        if p.is_file():
            assert not any(value.encode() in p.read_bytes() for value in (KEY, SECRET, TOKEN))
    assert_released(rig)


def test_named_current20_refresh_and_xlk_context_consumer_reuses_one_POST(rig):
    scope = {symbol: frozenset({"NAS"}) for symbol in COHORT}
    frozen = tuple(minute(symbol, scope=scope) for symbol in COHORT) + (daily(mode="1"),)
    rig.opener.responses = [token()] + [minute_body() for _ in COHORT] + [daily_body()]
    with rig.session(frozen, limits=c.CaptureLimits(21, 0, 120)) as session:
        refs = [session.capture(q) for q in frozen]
        assert len(refs) == 21 and all(v.status == "ACCEPTED" for v in refs)
        assert session.progress["GET"] == 21 and session.progress["POST"] == 1
    assert len(rig.opener.calls) == 22


@pytest.mark.parametrize("kind", ["minute", "daily"])
def test_pending_survives_native_body_parse_raw_native_outcome_until_final_commit(
    rig, monkeypatch, kind
):
    q = minute() if kind == "minute" else daily()
    seen = []

    def body_read():
        seen.append("body")
        assert state(rig)["pending"]["method"] == "GET"

    rig.opener.responses = [
        token(),
        (minute_body if kind == "minute" else daily_body)(on_read=body_read),
    ]
    original = c.atomic_json

    def commit(path, document):
        if document["pending"] is None and document["GET"]:
            previous = state(rig)
            assert previous["pending"]["method"] == "GET"
            ordinal = previous["GET"]
            assert all(
                (rig.market / f"GET-{ordinal:06d}.{suffix}").exists()
                for suffix in ("body", "native.json", "outcome.json")
            )
            seen.append("resolve")
        return original(path, document)

    monkeypatch.setattr(c, "atomic_json", commit)
    with rig.session((q,)) as session:
        assert session.capture(q).status == "ACCEPTED"
    assert seen == ["body", "resolve"]


@pytest.mark.parametrize(
    "stage", ["token_body", "market_body", "parse", "raw", "native", "outcome", "state"]
)
def test_interruption_or_storage_failure_keeps_pending_no_resume_or_retry(rig, monkeypatch, stage):
    q = minute()

    def interrupt():
        raise KeyboardInterrupt("SYN interruption")

    rig.opener.responses = [
        token(on_read=interrupt) if stage == "token_body" else token(),
        minute_body(on_read=interrupt) if stage == "market_body" else minute_body(),
    ]
    if stage == "parse":
        monkeypatch.setattr(m, "_parse_minute_bar", lambda *_: interrupt())
    original_atomic = c.atomic_json

    def final_commit(path, document):
        if stage == "state" and document["GET"] and document["pending"] is None:
            raise OSError("SYN storage secret must not escape")
        return original_atomic(path, document)

    monkeypatch.setattr(c, "atomic_json", final_commit)
    with rig.session((q,)) as session:
        original = session._immutable

        def write(name, body):
            suffix = {"raw": ".body", "native": ".native.json", "outcome": ".outcome.json"}.get(
                stage
            )
            if suffix and name.startswith("GET-") and name.endswith(suffix):
                raise c.KisPaperCaptureError("SYN_immutable_fault")
            return original(name, body)

        monkeypatch.setattr(session, "_immutable", write)
        with pytest.raises((KeyboardInterrupt, c.KisPaperCaptureError)):
            session.capture(q)
        frozen = (rig.artifact / "capture-state.json").read_bytes()
        assert state(rig)["pending"]["method"] == ("POST" if stage == "token_body" else "GET")
        with pytest.raises(c.KisPaperCaptureError, match="pending_unknown"):
            session.capture(q, retry=True)
        assert (rig.artifact / "capture-state.json").read_bytes() == frozen
    assert_released(rig)
    with pytest.raises(c.KisPaperCaptureError, match="pending_unknown"), rig.session((q,)):
        pytest.fail("pending resume admitted")
    assert (rig.artifact / "capture-state.json").read_bytes() == frozen
    assert_released(rig)


def test_exact_durable_transport_failure_retry_debits_and_no_automatic_repeat(rig):
    q, other = minute(), daily()
    rig.opener.responses = [token(), OSError("SYN private transport text"), minute_body()]
    with rig.session((q, other)) as session:
        failed = session.capture(q)
        assert failed.status == "REJECTED" and failed.reason == "transport_failure"
        first = state(rig)
        assert first["GET"] == 1 and first["retry"] == 0 and first["pending"] is None
        assert Path(failed.outcome["path"]).exists()
        with pytest.raises(c.KisPaperCaptureError, match="explicit_exact_retry"):
            session.capture(q)
        with pytest.raises(c.KisPaperCaptureError, match="exact_failed_attempt"):
            session.capture(other, retry=True)
        assert state(rig) == first
        result = session.capture(q, retry=True)
        assert result.status == "ACCEPTED"
        final = state(rig)
        assert final["GET"] == 2 and final["retry"] == 1 and final["POST"] == 1
        assert final["failed_attempts"][0]["retried_by"] == 2
        assert session.capture(q, retry=True).cache_hit
    assert len(rig.opener.calls) == 3
    assert "SYN private" not in json.dumps(final)


def test_failed_outcome_write_never_authorizes_retry_or_refunds_attempt(rig, monkeypatch):
    rig.opener.responses = [token(), OSError("SYN failed GET")]
    with rig.session((minute(),)) as session:
        original = session._immutable

        def write(name, body):
            if name.startswith("GET-"):
                raise c.KisPaperCaptureError("SYN_outcome_storage_failure")
            return original(name, body)

        monkeypatch.setattr(session, "_immutable", write)
        with pytest.raises(c.KisPaperCaptureError, match="outcome_storage"):
            session.capture(minute())
        assert state(rig)["GET"] == 1 and not state(rig)["failed_attempts"]
        with pytest.raises(c.KisPaperCaptureError, match="pending_unknown"):
            session.capture(minute(), retry=True)


@pytest.mark.parametrize("code", ["rate_limited", "daily_response_invalid", "response_invalid"])
def test_nontransport_failures_cannot_become_technical_retry(rig, monkeypatch, code):
    rig.opener.responses = [token(), daily_body()]
    monkeypatch.setattr(
        m, "_parse_daily_raw_row", lambda *_: (_ for _ in ()).throw(m.KisPaperMarketDataError(code))
    )
    with rig.session((daily(),)) as session:
        result = session.capture(daily())
        assert result.status == "REJECTED" and result.reason == code
        assert session.capture(daily(), retry=True).cache_hit
        assert session.progress["retry"] == 0 and session.progress["GET"] == 1


def test_retry_cap_and_total_GET_cap_are_aggregate_not_per_endpoint(rig):
    q = minute()
    rig.opener.responses = [token(), OSError("SYN"), OSError("SYN")]
    with rig.session((q, daily()), limits=c.CaptureLimits(2, 1, 120)) as session:
        session.capture(q)
        session.capture(q, retry=True)
        before = state(rig)
        with pytest.raises(c.KisPaperCaptureError, match="GET_cap"):
            session.capture(daily())
        with pytest.raises(c.KisPaperCaptureError, match="GET_cap"):
            session.capture(q, retry=True)
        assert state(rig) == before and before["retry"] == 1
    assert len(rig.opener.calls) == 3


def test_cache_hit_after_restart_does_not_load_credentials_or_auth_again(rig):
    q = minute()
    rig.opener.responses = [token(), minute_body()]
    with rig.session((q, daily())) as session:
        first = session.capture(q)
    frozen = (rig.artifact / "capture-state.json").read_bytes()
    with rig.session(
        (q, daily()), config_loader=lambda: pytest.fail("credentials loaded on cache hit")
    ) as session:
        assert session.capture(q) == replace(first, cache_hit=True)
        with pytest.raises(c.KisPaperCaptureError, match="auth_cap"):
            session.capture(daily())
    assert (rig.artifact / "capture-state.json").read_bytes() == frozen
    assert len(rig.opener.calls) == 2


@pytest.mark.parametrize("target", ["raw", "native", "outcome"])
def test_cache_ref_tamper_is_not_replaced_or_requeried(rig, target):
    rig.opener.responses = [token(), minute_body()]
    with rig.session((minute(),)) as session:
        result = session.capture(minute())
        path = Path(getattr(result, target)["path"])
        path.write_bytes(b"SYN modified")
        with pytest.raises(c.KisPaperCaptureError, match="cache_ref_mismatch"):
            session.capture(minute())
    assert len(rig.opener.calls) == 2


@pytest.mark.parametrize("which", ["market", "artifact"])
def test_loser_owner_acquisition_cannot_create_or_overwrite_ledger(rig, which):
    rig.market.mkdir(parents=True)
    rig.artifact.mkdir(parents=True)
    cursor = rig.artifact / "capture-state.json"
    cursor.write_text('{"SYN":"foreign cursor"}')
    before = cursor.read_bytes()
    with FoundationOwner(getattr(rig, which)):
        with pytest.raises(FileExistsError), rig.session():
            pytest.fail("loser acquired")
        assert cursor.read_bytes() == before
    assert_released(rig)
    assert not rig.opener.calls and not rig.loads


def test_enter_failure_releases_both_owners_and_never_rewrites_mismatched_contract(rig):
    with rig.session():
        pass
    before = (rig.artifact / "capture-state.json").read_bytes()
    with (
        pytest.raises(c.KisPaperCaptureError, match="resume_contract_mismatch"),
        rig.session((minute(),)),
    ):
        pytest.fail("changed scope admitted")
    assert (rig.artifact / "capture-state.json").read_bytes() == before
    assert_released(rig)


def test_owner_loss_during_body_preserves_pending_and_never_removes_foreign_owner(rig):
    session = rig.session((minute(),))
    session.__enter__()
    marker = rig.market / "owner.lock.d/owner.json"

    def lose_owner():
        marker.write_text('{"SYN":"foreign owner"}')

    rig.opener.responses = [token(), minute_body(on_read=lose_owner)]
    with pytest.raises(c.KisPaperCaptureError, match="owner_lost"):
        session.capture(minute())
    before = (rig.artifact / "capture-state.json").read_bytes()
    with pytest.raises(ValueError, match="owner_changed"):
        session.__exit__(None, None, None)
    assert marker.exists() and not (rig.artifact / "owner.lock.d").exists()
    assert state(rig)["pending"]["method"] == "GET"
    assert (rig.artifact / "capture-state.json").read_bytes() == before
    # Test alone restores its own injected marker, never a real owner.
    marker.unlink()
    marker.parent.rmdir()


@pytest.mark.parametrize("due", [None, datetime(2026, 10, 17, 1, tzinfo=UTC)])
def test_owner_due_defer_has_unknown_not_zero_and_no_credentials_or_wire(rig, due):
    with rig.session(owner_ready=lambda: c.CaptureReadiness(False, due)) as session:
        result = session.capture(minute())
        assert result.status == "DEFERRED" and result.next_due == (due.isoformat() if due else None)
        assert session.progress["GET"] == session.progress["POST"] == 0
    assert rig.loads == [1] and not rig.opener.calls


@pytest.mark.parametrize("interval", [300, 60])
def test_token_floor_default_and_explicit_60_are_shared_and_frozen(rig, interval):
    control = c._MARKET_BASE / "collection-control-v1"
    gate = KisPaperMarketDataTokenStartGate(
        control_root=control, clock=rig.clock.utc, minimum_request_interval_seconds=interval
    )
    assert gate.claim_token_request_start()
    mark = (control / "token-request.json").read_bytes()
    kwargs = {} if interval == 300 else dict(token_minimum_interval_seconds=60)
    with rig.session(**kwargs) as session:
        result = session.capture(minute())
        assert result.status == "DEFERRED" and result.reason == "token_request_not_due"
        assert datetime.fromisoformat(result.next_due) == rig.clock.utc() + timedelta(
            seconds=interval
        )
        assert session.progress["POST"] == session.progress["GET"] == 0
        assert (control / "token-request.json").read_bytes() == mark
    with (
        pytest.raises(c.KisPaperCaptureError, match="resume_contract_mismatch"),
        rig.session(token_minimum_interval_seconds=60 if interval == 300 else 300),
    ):
        pytest.fail("token floor changed on resume")
    assert not rig.opener.calls


@pytest.mark.parametrize("stage", ["body", "pacing", "resume"])
def test_wall_timeout_preserves_debits_and_is_not_a_transport_retry(rig, stage):
    q = minute()
    rig.opener.responses = [token(), minute_body(on_read=lambda: rig.clock.advance(4))]
    with rig.session((q,), limits=c.CaptureLimits(5, 2, 3)) as session:
        if stage == "resume":
            pass
        elif stage == "pacing":
            rig.clock.advance(2)
            with pytest.raises(c.KisPaperCaptureError, match="wall_cap"):
                session.capture(q)
            assert session.progress["GET"] == 0 and session.progress["POST"] == 1
        else:
            with pytest.raises(c.KisPaperCaptureError, match="wall_cap"):
                session.capture(q)
            assert session.progress["GET"] == 1 and session.progress["pending"]["method"] == "GET"
    if stage == "resume":
        rig.clock.advance(4)
        with (
            pytest.raises(c.KisPaperCaptureError, match="wall_cap"),
            rig.session((q,), limits=c.CaptureLimits(5, 2, 3)),
        ):
            pytest.fail("expired wall reset")
    assert_released(rig)


def test_body_timeout_is_categorical_durably_failed_and_exact_retry_only(rig):
    q = minute()

    def timeout():
        raise TimeoutError("SYN private exception")

    rig.opener.responses = [token(), minute_body(on_read=timeout), minute_body()]
    with rig.session((q,)) as session:
        assert session.capture(q).reason == "transport_failure"
        assert session.progress["pending"] is None
        assert session.capture(q, retry=True).status == "ACCEPTED"
        assert session.progress["GET"] == 2 and session.progress["retry"] == 1


@pytest.mark.parametrize("which", ["key", "secret", "token"])
def test_secret_echo_never_reaches_any_output_and_keeps_pending(rig, which):
    secret = dict(key=KEY, secret=SECRET, token=TOKEN)[which]
    rig.opener.responses = [token(), Response(dict(rt_cd="0", output1={}, output2=[], echo=secret))]
    with rig.session((minute(),)) as session:
        with pytest.raises(c.KisPaperCaptureError, match="secret_echo"):
            session.capture(minute())
        assert session.progress["pending"]["method"] == "GET"
    for parent in (rig.market, rig.artifact):
        assert all(secret.encode() not in p.read_bytes() for p in parent.rglob("*") if p.is_file())


def test_oversized_body_is_bounded_and_unknown_not_retained(rig):
    rig.opener.responses = [token(), Response(b"x" * (c._MAX_BODY + 2))]
    with rig.session((minute(),)) as session:
        with pytest.raises(c.KisPaperCaptureError, match="response_size"):
            session.capture(minute())
        assert session.progress["pending"]["method"] == "GET"
    assert not list(rig.market.glob("GET-*.body"))


@pytest.mark.parametrize(
    "body",
    [b'{"rt_cd":"1"}', b'{"rt_cd":"0","output1":{},"output2":[{"xymd":"invalid"}]}'],
)
def test_native_parse_rejection_is_durable_and_raw_only_in_market(rig, body):
    rig.opener.responses = [token(), Response(body)]
    with rig.session((daily(),)) as session:
        result = session.capture(daily())
        assert result.status == "REJECTED" and result.raw and not result.native
        assert session.progress["pending"] is None


def test_native_HTTP_error_retains_bounded_market_evidence_not_private_exception_text(rig):
    error = urllib.error.HTTPError(
        "https://example.invalid", 503, "SYN private", {}, io.BytesIO(b'{"rt_cd":"1"}')
    )
    rig.opener.responses = [token(), error]
    with rig.session((daily(),)) as session:
        result = session.capture(daily())
        assert result.status == "REJECTED" and result.reason == "daily_response_rejected"
        assert "SYN private" not in json.dumps(session.progress)


@pytest.mark.parametrize("target", ["live", "account", "order", "symbol", "date"])
def test_final_native_wire_denies_route_or_query_mutation_before_GET_debit(
    rig, monkeypatch, target
):
    rig.opener.responses = [token(), minute_body()]
    original = m._request_url

    def url(request):
        value = original(request)
        if request.method != "GET":
            return value
        return {
            "live": value.replace("openapivts", "openapi"),
            "account": value.replace(
                m.KIS_PAPER_MINUTE_PATH, "/uapi/overseas-stock/v1/trading/inquire-balance"
            ),
            "order": value.replace(
                m.KIS_PAPER_MINUTE_PATH, "/uapi/overseas-stock/v1/trading/order"
            ),
            "symbol": value.replace("SYMB=AAPL", "SYMB=MSFT"),
            "date": value.replace("20261016155900", "20261015155900"),
        }[target]

    monkeypatch.setattr(m, "_request_url", url)
    with rig.session((minute(),)) as session:
        with pytest.raises(c.KisPaperCaptureError, match="route_required|exact_query"):
            session.capture(minute())
        assert session.progress["GET"] == 0 and session.progress["POST"] == 1
    assert len(rig.opener.calls) == 1


@pytest.mark.parametrize("mutation", ["symbol", "venue", "date", "scope", "adjustment"])
def test_frozen_typed_scope_denies_unlisted_query_before_auth(rig, mutation):
    q = minute()
    if mutation == "symbol":
        other = minute("MSFT")
    elif mutation == "venue":
        other = c.CaptureQuery(
            m.KisPaperDailyQuery(
                "XLK",
                "20261016",
                exchange="NYS",
                approved_symbol_exchanges={"XLK": frozenset({"NYS"})},
            ),
            "20261016",
            "20261016",
        )
    elif mutation == "date":
        other = minute(key="20261015155900", first="20261015", last="20261015")
    elif mutation == "scope":
        other = minute(scope={"AAPL": frozenset({"NAS"}), "MSFT": frozenset({"NAS"})})
    else:
        other = daily(mode="1")
    with rig.session((q,)) as session:
        with pytest.raises(c.KisPaperCaptureError, match="outside_frozen_scope"):
            session.capture(other)
        assert session.progress["POST"] == session.progress["GET"] == 0
    assert not rig.loads and not rig.opener.calls


@pytest.mark.parametrize(
    "case", ["market_outside", "artifact_outside", "repo", "shared_control", "base_root"]
)
def test_unsafe_storage_refused_before_any_owner_or_output_write(rig, tmp_path, case):
    kwargs = {
        "market_outside": dict(market_root=tmp_path / "outside"),
        "artifact_outside": dict(artifact_root=tmp_path / "outside"),
        "repo": dict(artifact_root=c._REPO / "capture-SYN-forbidden"),
        "shared_control": dict(market_root=c._MARKET_BASE / "collection-control-v1"),
        "base_root": dict(market_root=c._MARKET_BASE),
    }[case]
    with pytest.raises(c.KisPaperCaptureError, match="storage_scope|control_root_overlap"):
        rig.session(**kwargs)
    assert not rig.market.exists() and not rig.artifact.exists()


def test_hardlink_state_path_refused_without_changing_link_target(rig, tmp_path):
    rig.artifact.mkdir(parents=True)
    target = tmp_path / "foreign.json"
    target.write_text('{"SYN":"foreign"}')
    path = rig.artifact / "capture-state.json"
    assert path.resolve().is_relative_to(tmp_path.resolve())
    assert target.resolve().is_relative_to(tmp_path.resolve())
    path.hardlink_to(target)
    try:
        with pytest.raises(c.KisPaperCaptureError, match="hardlink"), rig.session():
            pytest.fail("hardlink admitted")
        assert target.read_text() == '{"SYN":"foreign"}'
        assert_released(rig)
    finally:
        assert path.resolve().is_relative_to(tmp_path.resolve())
        assert path.samefile(target)
        path.unlink()
    assert target.stat().st_nlink == 1


def test_reparse_ancestor_refused_before_ledger_write(rig, monkeypatch):
    original = Path.lstat

    def lstat(path):
        value = original(path)
        if path == c._ARTIFACT_BASE:
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400, st_nlink=1)
        return value

    c._ARTIFACT_BASE.mkdir()
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(c.KisPaperCaptureError, match="reparse"):
        rig.session()
    assert not rig.market.exists()


def test_disk_floor_fails_with_pending_and_no_market_file(rig, monkeypatch):
    rig.opener.responses = [token()]
    with rig.session((minute(),)) as session:
        monkeypatch.setattr(c.shutil, "disk_usage", lambda _: SimpleNamespace(free=14, total=100))
        with pytest.raises(c.KisPaperCaptureError, match="disk_floor"):
            session.capture(minute())
        assert session.progress["pending"]["method"] == "POST"
    assert not list(rig.market.glob("*.outcome.json"))


def test_immutable_file_collision_is_not_overwritten_and_pending_remains(rig):
    rig.opener.responses = [token(), minute_body()]
    with rig.session((minute(),)) as session:
        target = rig.market / "GET-000001.native.json"
        target.write_bytes(b"SYN prior immutable")
        with pytest.raises(c.KisPaperCaptureError, match="immutable_storage"):
            session.capture(minute())
        assert target.read_bytes() == b"SYN prior immutable"
        assert session.progress["pending"]["method"] == "GET"


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_get", True),
        ("max_get", 0),
        ("max_retries", -1),
        ("max_auth", -1),
        ("wall_seconds", float("inf")),
        ("wall_seconds", float("nan")),
        ("request_timeout_seconds", 0),
        ("request_interval_seconds", 0.5),
    ],
)
def test_invalid_caps_refused(field, value):
    args = dict(max_get=2, max_retries=1, wall_seconds=10)
    args[field] = value
    with pytest.raises(c.KisPaperCaptureError):
        c.CaptureLimits(**args)


@pytest.mark.parametrize(
    "first,last",
    [
        ("20260230", "20261016"),
        ("20261017", "20261016"),
        ("２０２６１０１６", "20261016"),
        ("2026101", "20261016"),
    ],
)
def test_invalid_calendar_dates_and_query_bounds_refused(first, last):
    with pytest.raises(c.KisPaperCaptureError):
        minute(first=first, last=last)


def test_capture_reentrancy_refused_without_second_wire(rig):
    rig.opener.responses = [token(), minute_body()]
    with rig.session((minute(),)) as session:

        def callback(request):
            with pytest.raises(c.KisPaperCaptureError, match="reentrancy"):
                session.capture(minute())

        rig.opener.before_open = callback
        assert session.capture(minute()).status == "ACCEPTED"
    assert len(rig.opener.calls) == 2


def test_one_fresh_full_admission_per_actual_HTTP_after_pacing(rig):
    probes = []
    rig.opener.responses = [token(), minute_body(), daily_body()]

    def ready():
        probes.append((rig.clock.tick, len(rig.opener.calls)))
        return c.CaptureReadiness(True)

    def before_open(request):
        # Calls includes this delegate; its sole probe ran after the last wait.
        assert probes[-1] == (rig.clock.tick, len(rig.opener.calls) - 1)
        assert len(probes) == len(rig.opener.calls)

    rig.opener.before_open = before_open
    with rig.session(owner_ready=ready) as session:
        session.capture(minute())
        session.capture(daily())
        assert session.capture(minute()).cache_hit
    assert probes == [(0, 0), (2, 1), (4, 2)]
    assert len(rig.opener.calls) == 3


def test_actor_appearing_during_rate_wait_blocks_actual_delegate_not_stale_probe(rig):
    probes = []
    actor = dict(active=False)

    def ready():
        probes.append((rig.clock.tick, actor["active"]))
        return c.CaptureReadiness(not actor["active"], None)

    def wait(seconds):
        rig.clock.sleep(seconds)
        actor["active"] = True

    rig.opener.responses = [token(), minute_body()]
    session = rig.session((minute(),), owner_ready=ready)
    session._sleep = wait
    with session:
        result = session.capture(minute())
        assert result.status == "DEFERRED" and result.next_due is None
        assert session.progress["POST"] == 1 and session.progress["GET"] == 0
        assert session.progress["pending"] is None
    assert probes == [(0, False), (2, True)]
    assert [v[0] for v in rig.opener.calls] == ["POST"]


def test_caller_callback_exception_is_not_copied_to_progress_and_debits_none(rig):
    def failed_probe():
        raise RuntimeError("SYN caller probe failure")

    with rig.session(owner_ready=failed_probe) as session:
        with pytest.raises(RuntimeError, match="SYN caller"):
            session.capture(minute())
        assert session.progress["POST"] == session.progress["GET"] == 0
        assert session.progress["pending"] is None
        assert "SYN caller" not in json.dumps(session.progress)
    assert not rig.opener.calls


def test_token_mark_changes_during_final_admission_no_POST_or_mark_reset(rig):
    def ready():
        path = c._MARKET_BASE / "collection-control-v1/token-request.json"
        document = json.loads(path.read_bytes())
        document["last_token_request_started_at_utc"] = (
            rig.clock.utc() + timedelta(seconds=1)
        ).isoformat()
        c.atomic_json(path, document)
        return c.CaptureReadiness(True)

    with rig.session(owner_ready=ready) as session:
        with pytest.raises(c.KisPaperCaptureError, match="token_start_identity_changed"):
            session.capture(minute())
        assert session.progress["POST"] == 0 and session.progress["pending"] is None
    path = c._MARKET_BASE / "collection-control-v1/token-request.json"
    assert (
        json.loads(path.read_bytes())["last_token_request_started_at_utc"]
        == (rig.clock.utc() + timedelta(seconds=1)).isoformat()
    )
    assert not rig.opener.calls


@pytest.mark.parametrize("failure", ["transport", "rejected", "parse"])
def test_auth_failure_is_durable_but_never_reauths_or_becomes_GET_retry(rig, failure):
    response = {
        "transport": OSError("SYN private auth failure"),
        "rejected": Response({"rt_cd": "1"}, status=403),
        "parse": Response(b"bad json"),
    }[failure]
    rig.opener.responses = [response]
    with rig.session() as session:
        with pytest.raises(c.KisPaperCaptureError, match="authentication_rejected"):
            session.capture(minute())
        assert session.progress["POST"] == 1 and session.progress["GET"] == 0
        assert session.progress["pending"] is None
        assert (rig.market / "POST-000001.outcome.json").exists()
        before = state(rig)
        with pytest.raises(c.KisPaperCaptureError, match="auth_cap"):
            session.capture(daily())
        with pytest.raises(c.KisPaperCaptureError, match="exact_failed_attempt"):
            session.capture(minute(), retry=True)
        assert state(rig) == before
    assert len(rig.opener.calls) == 1


def test_auth_outcome_storage_failure_keeps_POST_pending_not_authenticated(rig, monkeypatch):
    rig.opener.responses = [token()]
    with rig.session() as session:
        monkeypatch.setattr(
            session,
            "_immutable",
            lambda *_: (_ for _ in ()).throw(c.KisPaperCaptureError("SYN storage")),
        )
        with pytest.raises(c.KisPaperCaptureError, match="SYN storage"):
            session.capture(minute())
        assert not session._authenticated
        assert session.progress["pending"]["method"] == "POST"
    assert len(rig.opener.calls) == 1


def test_escaped_secret_echo_is_not_retained(rig):
    encoded = json.dumps(dict(rt_cd="0", output1={}, output2=[], echo=SECRET)).encode()
    encoded = encoded.replace(SECRET.encode(), b"\\u0053" + SECRET[1:].encode())
    rig.opener.responses = [token(), Response(encoded)]
    with rig.session() as session:
        with pytest.raises(c.KisPaperCaptureError, match="secret_echo"):
            session.capture(minute())
    assert not list(rig.market.glob("GET-*.body"))


def test_exact_failed_retry_after_restart_keeps_original_debits_and_auth_cap(rig):
    limits = c.CaptureLimits(3, 1, 600, max_auth=2)
    rig.opener.responses = [token(), OSError("SYN GET failure")]
    with rig.session((minute(),), limits=limits) as session:
        session.capture(minute())
        first = session.progress
    rig.clock.advance(301)
    rig.opener.responses = [token(), minute_body()]
    with rig.session((minute(),), limits=limits) as session:
        assert session.progress == first
        assert session.capture(minute(), retry=True).status == "ACCEPTED"
        assert session.progress["GET"] == 2 and session.progress["POST"] == 2
        assert session.progress["retry"] == 1


def test_resume_wall_cap_cannot_be_expanded_to_allow_retry(rig):
    rig.opener.responses = [token(), OSError("SYN GET failure")]
    limits = c.CaptureLimits(3, 1, 120, max_auth=2)
    with rig.session((minute(),), limits=limits) as session:
        session.capture(minute())
    rig.clock.advance(301)
    with (
        pytest.raises(c.KisPaperCaptureError, match="wall_cap"),
        rig.session((minute(),), limits=limits),
    ):
        pytest.fail("wall extended")
    with (
        pytest.raises(c.KisPaperCaptureError, match="resume_contract_mismatch"),
        rig.session((minute(),), limits=replace(limits, wall_seconds=600)),
    ):
        pytest.fail("caps changed")


@pytest.mark.parametrize("key,value", [("GET", -1), ("retry", -1), ("POST", 3), ("GET", True)])
def test_invalid_resume_debits_refused_before_auth(rig, key, value):
    with rig.session():
        pass
    document = state(rig)
    document[key] = value
    c.atomic_json(rig.artifact / "capture-state.json", document)
    before = (rig.artifact / "capture-state.json").read_bytes()
    with pytest.raises(c.KisPaperCaptureError, match="resume_debits_invalid"), rig.session():
        pytest.fail("invalid debit admitted")
    assert before == (rig.artifact / "capture-state.json").read_bytes()
    assert not rig.loads and not rig.opener.calls


def test_native_future_timestamp_refused_with_allowlisted_first_cause(rig):
    q = minute(key="20261017155900", first="20261017", last="20261017")
    rig.opener.responses = [token()]
    with rig.session((q,)) as session:
        with pytest.raises(
            c.KisPaperCaptureError, match="historical_minute_past_timestamp_required"
        ):
            session.capture(q)
        assert session.progress["POST"] == 1 and session.progress["GET"] == 0


def test_callback_durable_state_change_cannot_be_overwritten_by_delegate(rig):
    def ready():
        document = state(rig)
        document["pending"] = dict(method="GET", ordinal=99, query_key="SYN foreign")
        c.atomic_json(rig.artifact / "capture-state.json", document)
        return c.CaptureReadiness(True)

    with rig.session(owner_ready=ready) as session:
        with pytest.raises(c.KisPaperCaptureError, match="pending_or_state_changed"):
            session.capture(minute())
    assert state(rig)["pending"]["ordinal"] == 99
    assert not rig.opener.calls


def test_native_mixed_mode0_mode1_identities_distinct_one_POST_and_cache_hits(rig):
    q, zero, one = minute(), daily(mode="0"), daily(mode="1")
    assert zero.key != one.key and zero.document()["parameters"]["MODP"] == "0"
    assert one.document()["parameters"]["MODP"] == "1"
    rig.opener.responses = [token(), minute_body(), daily_body(), daily_body()]
    with rig.session((q, zero, one)) as session:
        a, b, d = [session.capture(query) for query in (q, zero, one)]
        assert all(v.status == "ACCEPTED" for v in (a, b, d))
        assert b.query_key != d.query_key and b.raw["path"] != d.raw["path"]
        assert session.capture(zero).cache_hit and session.capture(one).cache_hit
        assert session.progress["POST"] == 1 and session.progress["GET"] == 3
        assert type(session._client) is m.KisPaperMarketDataClient
    assert len(rig.opener.calls) == 4


def test_native_daily_only_mode1_uses_explicit_transport_without_minute_scope_mutation(rig):
    q = daily(mode="1")
    rig.opener.responses = [token(), daily_body()]
    with rig.session((q,)) as session:
        assert session._minute_scope is None
        assert session.capture(q).status == "ACCEPTED"
        assert session._client.call_counts.token_attempts == 1
        assert session._client.call_counts.daily_page_attempts == 1
        assert session.capture(q).cache_hit
    assert len(rig.opener.calls) == 2


@pytest.mark.parametrize("kind", ["minute", "daily"])
def test_inconsistent_frozen_native_maps_refused_before_loader_or_owner(rig, kind):
    if kind == "minute":
        queries = (minute(), minute("MSFT"))
    else:
        queries = (daily(), daily("XLF", mode="1"))
    with pytest.raises(c.KisPaperCaptureError, match=kind + "_scope_mismatch"):
        rig.session(queries)
    assert not rig.loads and not rig.opener.calls
    assert not rig.market.exists() and not rig.artifact.exists()


@pytest.mark.parametrize(
    "first,last", [("202610 6", "20261016"), ("2026 116", "20261016"), ("20261016", "202610 6")]
)
def test_canonical_date_roundtrip_rejects_space_padded_components(first, last):
    with pytest.raises(c.KisPaperCaptureError, match="date_scope_invalid"):
        minute(first=first, last=last)


@pytest.mark.parametrize("kind", ["minute", "daily0", "daily1"])
@pytest.mark.parametrize(
    "body_kind",
    [
        "escaped_key",
        "escaped_secret",
        "escaped_token",
        "invalid_utf8",
        "malformed_plain",
        "unicode_surrogate",
    ],
)
def test_failed_secret_inspection_retains_pending_and_no_body_or_refund(rig, kind, body_kind):
    query = minute() if kind == "minute" else daily(mode=kind[-1])
    if body_kind.startswith("escaped_"):
        credential = {"escaped_key": KEY, "escaped_secret": SECRET, "escaped_token": TOKEN}[
            body_kind
        ]
        body = json.dumps(dict(echo=credential)).encode()
        body = body.replace(credential.encode(), b"\\u0053" + credential[1:].encode())[:-1]
        assert credential.encode() not in body
    else:
        body = {
            "invalid_utf8": b"\xff",
            "malformed_plain": b"not JSON",
            "unicode_surrogate": b'{"echo":"\\ud800"}',
        }[body_kind]
    rig.opener.responses = [token(), Response(body)]
    with rig.session((query,)) as session:
        with pytest.raises(c.KisPaperCaptureError, match="capture_response_inspection_failed"):
            session.capture(query)
        progress = session.progress
        assert progress["POST"] == progress["GET"] == 1 and progress["retry"] == 0
        assert progress["pending"]["method"] == "GET"
        assert not progress["completed"] and not progress["failed_attempts"]
        assert (rig.market / "POST-000001.outcome.json").exists()
        assert not list(rig.market.glob("GET-*"))
        frozen = (rig.artifact / "capture-state.json").read_bytes()
        with pytest.raises(c.KisPaperCaptureError, match="pending_unknown"):
            session.capture(query, retry=True)
        assert (rig.artifact / "capture-state.json").read_bytes() == frozen
    assert_released(rig)
    with pytest.raises(c.KisPaperCaptureError, match="pending_unknown"), rig.session((query,)):
        pytest.fail("inspection-unknown resumed")
    assert (rig.artifact / "capture-state.json").read_bytes() == frozen
    assert len(rig.opener.calls) == 2
    assert_released(rig)
