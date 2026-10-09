"""Synthetic stock client/transport boundaries; no private IO or real network."""

from __future__ import annotations

import copy
import io
import json
import socket
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution import kis_readonly as old
from thericher_v2.execution.kis_paper_canary import (
    KIS_PAPER_US_BUY_LIMIT_ORDER_PATH,
    KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID,
    KIS_PAPER_US_CANCEL_TR_ID,
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    UrllibKisPaperCanaryTransport,
    validate_kis_paper_canary_request,
)
from thericher_v2.execution.kis_paper_quote import (
    KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
    KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
)
from thericher_v2.execution.kis_paper_spy_fill_cycle import _digest
from thericher_v2.execution.kis_paper_stock_canary import (
    KisPaperStockCanaryClient,
    UrllibKisPaperStockCanaryTransport,
)
from thericher_v2.execution.kis_paper_stock_quote import (
    KisPaperStockInstrument,
    build_kis_paper_stock_quote_request,
    validate_kis_paper_stock_quote_request,
)

D = Decimal
INSTRUMENT = KisPaperStockInstrument("SYNTH", "ref:" + "a" * 64)
NOW = datetime(2026, 10, 9, 14, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_network_or_credentials(monkeypatch):
    def deny(*_args, **_kwargs):
        pytest.fail("actual_network_or_credentials_forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(old, "load_kis_paper_config", deny)
    monkeypatch.setattr(old, "load_kis_paper_config_from_environment", deny)


def _config():
    return old.KisPaperConfig("synthetic-key", "synthetic-secret", "12345678", "01")


class FakeTransport:
    def __init__(self):
        self.requests = []
        self.now = datetime.now(UTC)
        self.bad_detail = False
        self.bad_funds = False

    def request(self, request):
        try:
            validate_kis_paper_canary_request(request)
        except KisPaperCanaryError:
            validate_kis_paper_stock_quote_request(request, instrument=INSTRUMENT)
        self.requests.append(request)
        if request.url.endswith(old.KIS_PAPER_TOKEN_PATH):
            return old.KisHttpResponse.from_payload({"access_token": "synthetic-token"})
        tr_id = request.headers["tr_id"]
        if tr_id == old.KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            return old.KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
        if tr_id in {
            old.KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
            old.KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id,
        }:
            return old.KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == old.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            if self.bad_funds:
                return old.KisHttpResponse.from_payload({"rt_cd": "0", "output": {}})
            return old.KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "tr_crcy_cd": "USD",
                        "ord_psbl_frcr_amt": "1000",
                        "ovrs_ord_psbl_amt": "900",
                    },
                }
            )
        if tr_id == KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID:
            return old.KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {"zdiv": "2", "e_hogau": "0" if self.bad_detail else "0.01"},
                }
            )
        if tr_id == KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID:
            korea = self.now.astimezone(ZoneInfo("Asia/Seoul"))
            return old.KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {
                        "last": "100",
                        "zdiv": "2",
                        "dymd": korea.strftime("%Y%m%d"),
                        "dhms": korea.strftime("%H%M%S"),
                    },
                    "output2": {"pbid1": "99.99", "pask1": "100.01"},
                }
            )
        if tr_id == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID:
            return old.KisHttpResponse.from_payload(
                {"rt_cd": "0", "output": {"ODNO": "SYNTH-ORDER"}}
            )
        assert tr_id == KIS_PAPER_US_CANCEL_TR_ID
        return old.KisHttpResponse.from_payload({"rt_cd": "0", "output": {}})


def _client(transport=None, **changes):
    return KisPaperStockCanaryClient(
        **(
            dict(config=_config(), transport=transport or FakeTransport(), instrument=INSTRUMENT)
            | changes
        )
    )


def _intent():
    return KisPaperCanaryIntent(
        "stock-synthetic",
        "client-synthetic",
        "decision-synthetic",
        INSTRUMENT.symbol,
        "NASD",
        D(1),
        D("100.01"),
        NOW,
        NOW + timedelta(minutes=5),
    )


def _tamper(value, field, bad):
    result = copy.copy(value)
    object.__setattr__(result, field, bad)
    return result


def _call(value, operation, *, symbol=INSTRUMENT.symbol, exchange="NASD"):
    if operation == "funds":
        return value.orderable_funds_at_limit(symbol=symbol, exchange=exchange, limit_price=D(100))
    intent = _tamper(_tamper(_intent(), "symbol", symbol), "exchange", exchange)
    if operation == "submit":
        return value.submit_limit(intent, now=NOW)
    if operation == "submit_buy":
        return value.submit_buy_limit(intent, now=NOW)
    if operation == "cancel":
        return value.cancel_order(intent, broker_order_id="SYNTH-ORDER")
    if operation == "cancel_buy":
        return value.cancel_buy_order(intent, broker_order_id="SYNTH-ORDER")
    return value.reconcile(
        KisPaperCanaryState(_intent(), "intent_recorded", NOW, "preview")
        if symbol == INSTRUMENT.symbol and exchange == "NASD"
        else _tamper(
            KisPaperCanaryState(_intent(), "intent_recorded", NOW, "preview"), "intent", intent
        ),
        now=NOW,
    )


@pytest.mark.parametrize(
    "operation", ["funds", "submit", "submit_buy", "cancel", "cancel_buy", "reconcile"]
)
@pytest.mark.parametrize("symbol", ["OTHER", "SPY", "QQQ", "TLT", "GLD", "synth", None, 1])
def test_unknown_symbol_and_etf_rejected_before_authentication_or_wire(operation, symbol):
    transport = FakeTransport()
    value = _client(transport)
    with pytest.raises(KisPaperCanaryError, match="^stock_instrument_mismatch$"):
        _call(value, operation, symbol=symbol)
    assert transport.requests == [] and value._access_token is None


@pytest.mark.parametrize(
    "operation", ["funds", "submit", "submit_buy", "cancel", "cancel_buy", "reconcile"]
)
@pytest.mark.parametrize("exchange", ["NAS", "AMEX", "NYSE", "nasd", None])
def test_wrong_venue_rejected_before_authentication_or_wire(operation, exchange):
    transport = FakeTransport()
    with pytest.raises(KisPaperCanaryError, match="^stock_instrument_mismatch$"):
        _call(_client(transport), operation, exchange=exchange)
    assert transport.requests == []


@pytest.mark.parametrize(
    "price", [True, 100.0, D("NaN"), D("Infinity"), D(0), D(-1), D("0.000000001"), D("1e23")]
)
def test_invalid_exact_limit_rejected_before_authentication(price):
    transport = FakeTransport()
    with pytest.raises(old.KisPaperReadOnlyError, match="^orderability_price_invalid$"):
        _client(transport).orderable_funds_at_limit(
            symbol=INSTRUMENT.symbol, exchange="NASD", limit_price=price
        )
    assert transport.requests == []


def test_exact_limit_funds_never_use_legacy_qqq_path_and_cache_reader_token(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("legacy_funds_fallback_forbidden")

    monkeypatch.setattr(old.KisPaperReadOnlyClient, "orderable_funds_at_limit", forbidden)
    monkeypatch.setattr(old.KisPaperReadOnlyClient, "preview_orderable_funds_at_limit", forbidden)
    transport = FakeTransport()
    value = _client(transport)
    for _ in range(2):
        cash, funds = value.orderable_funds_at_limit(
            symbol=INSTRUMENT.symbol, exchange="NASD", limit_price=D("100.01000000")
        )
        assert cash.available_cash == 1000 and funds.orderable_funds == 900
        assert (funds.reference_symbol, funds.reference_exchange, funds.reference_price) == (
            INSTRUMENT.symbol,
            "NASD",
            D("100.01000000"),
        )
    assert len(transport.requests) == 3 and value._access_token == "synthetic-token"
    for request in transport.requests[1:]:
        assert request.query["ITEM_CD"] == INSTRUMENT.symbol
        assert request.query["OVRS_EXCG_CD"] == "NASD"
        assert request.query["OVRS_ORD_UNPR"] == "100.01000000"
        assert request.headers["authorization"] == "Bearer synthetic-token"


def test_preview_snapshot_submit_cancel_reconcile_share_one_in_memory_token():
    transport = FakeTransport()
    value = _client(transport)
    cfg = value._config
    account = _digest([cfg.base_url, cfg.account_number, cfg.account_product_code])
    reads = value.stock_preview_snapshot(expected_account_ref=account, clock=lambda: transport.now)
    assert reads.instrument == INSTRUMENT and reads.buy_limit == D("100.01")
    assert len(transport.requests) == 9
    assert [r.headers.get("tr_id") for r in transport.requests[6:8]] == [
        KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
        KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
    ]
    assert transport.requests[-1].query["ITEM_CD"] == INSTRUMENT.symbol
    value.snapshot()
    assert value.submit_limit(_intent(), now=NOW) == (True, "SYNTH-ORDER")
    assert value.cancel_order(_intent(), broker_order_id="SYNTH-ORDER")
    state = KisPaperCanaryState(_intent(), "intent_recorded", NOW, "preview")
    assert value.reconcile(state, now=NOW).status == "clean"
    assert state.phase == "intent_recorded"
    assert sum(r.url.endswith(old.KIS_PAPER_TOKEN_PATH) for r in transport.requests) == 1
    assert value._access_token == "synthetic-token"
    assert all(
        r.headers["authorization"] == "Bearer synthetic-token"
        for r in transport.requests
        if not r.url.endswith(old.KIS_PAPER_TOKEN_PATH)
    )


def test_unknown_outcome_reconciliation_uses_original_identity_and_never_submits():
    transport = FakeTransport()
    value = _client(transport)
    state = KisPaperCanaryState(
        _intent(),
        "outcome_unknown",
        NOW + timedelta(seconds=2),
        "reconciliation_unresolved",
        submission_started_at=NOW,
    )
    result = value.reconcile(state, now=NOW + timedelta(seconds=2))
    assert result.status == "unresolved" and result.recovered_broker_order_id is None
    assert result.idless_history.status == "absent"
    assert not any(r.url.endswith(KIS_PAPER_US_BUY_LIMIT_ORDER_PATH) for r in transport.requests)


def test_preview_wrong_account_rejected_before_token_and_failed_preview_keeps_token():
    transport = FakeTransport()
    value = _client(transport)
    with pytest.raises(old.KisPaperReadOnlyError, match="stock_account_binding_mismatch"):
        value.stock_preview_snapshot(expected_account_ref="f" * 64)
    assert transport.requests == []
    cfg = value._config
    account = _digest([cfg.base_url, cfg.account_number, cfg.account_product_code])
    transport.bad_detail = True
    with pytest.raises(old.KisPaperReadOnlyError):
        value.stock_preview_snapshot(expected_account_ref=account, clock=lambda: transport.now)
    assert value._access_token == "synthetic-token"
    transport.bad_detail = False
    value.orderable_funds_at_limit(symbol=INSTRUMENT.symbol, exchange="NASD", limit_price=D(100))
    assert sum(r.url.endswith(old.KIS_PAPER_TOKEN_PATH) for r in transport.requests) == 1


def test_failed_funds_read_also_returns_acquired_token_to_canary():
    transport = FakeTransport()
    transport.bad_funds = True
    value = _client(transport)
    with pytest.raises(old.KisPaperReadOnlyError):
        value.orderable_funds_at_limit(
            symbol=INSTRUMENT.symbol, exchange="NASD", limit_price=D(100)
        )
    assert value._access_token == "synthetic-token"
    transport.bad_funds = False
    value.orderable_funds_at_limit(symbol=INSTRUMENT.symbol, exchange="NASD", limit_price=D(100))
    assert sum(r.url.endswith(old.KIS_PAPER_TOKEN_PATH) for r in transport.requests) == 1


def _quote_request(kind="asking_price"):
    return build_kis_paper_stock_quote_request(
        config=_config(), access_token="synthetic-token", instrument=INSTRUMENT, kind=kind
    )


def _generic_request(kind="submit"):
    transport = FakeTransport()
    value = _client(transport)
    if kind == "cancel":
        value.cancel_order(_intent(), broker_order_id="SYNTH-ORDER")
    elif kind == "token":
        value._issue_access_token()
    else:
        value.submit_limit(_intent(), now=NOW)
    return transport.requests[-1]


class Response:
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b'{"rt_cd":"0","output":{"ODNO":"SYNTH-ORDER"}}'


class Pacer:
    def __init__(self):
        self.calls = 0

    def wait_for_request_slot(self):
        self.calls += 1


class Opener:
    def __init__(self):
        self.requests = []

    def open(self, request, *, timeout):
        assert timeout == 15.0
        self.requests.append(request)
        return Response()


def _transport():
    pacer, opener = Pacer(), Opener()
    value = UrllibKisPaperStockCanaryTransport(instrument=INSTRUMENT, pacer=pacer)
    value._opener = opener
    return value, pacer, opener


def test_legacy_canary_validator_not_widened_by_stock_transport():
    request = _quote_request()
    with pytest.raises(KisPaperCanaryError):
        validate_kis_paper_canary_request(request)
    with pytest.raises(KisPaperCanaryError):
        UrllibKisPaperCanaryTransport(pacer=Pacer()).request(request)
    transport, pacer, opener = _transport()
    assert transport.request(request).status_code == 200
    assert pacer.calls == len(opener.requests) == 1


@pytest.mark.parametrize("kind", ["asking_price", "price_detail"])
@pytest.mark.parametrize(
    "change", ["other", "etf", "venue", "live", "post", "extra_query", "header", "fragment", "body"]
)
def test_stock_quote_scope_rejected_before_pacing_and_wire(kind, change):
    request = _quote_request(kind)
    if change in {"other", "etf", "venue", "extra_query"}:
        query = dict(request.query)
        query.update(
            {"SYMB": "OTHER"}
            if change == "other"
            else {"SYMB": "QQQ"}
            if change == "etf"
            else {"EXCD": "NYS"}
            if change == "venue"
            else {"EXTRA": "1"}
        )
        request = replace(request, query=query)
    elif change == "live":
        request = replace(
            request, url=request.url.replace("openapivts", "openapi").replace("29443", "9443")
        )
    elif change == "post":
        request = replace(request, method="POST")
    elif change == "header":
        request = replace(request, headers=dict(request.headers) | {"tr_id": "INVALID"})
    elif change == "fragment":
        request = replace(request, url=request.url + "#fragment")
    else:
        request = replace(request, json_body={})
    transport, pacer, opener = _transport()
    with pytest.raises(KisPaperCanaryError, match="request_not_allowlisted"):
        transport.request(request)
    assert pacer.calls == 0 and opener.requests == []


@pytest.mark.parametrize("kind", ["submit", "cancel", "token"])
def test_generic_order_cancel_token_transport_paths_unchanged(kind):
    request = _generic_request(kind)
    validate_kis_paper_canary_request(request)
    transport, pacer, opener = _transport()
    assert transport.request(request).status_code == 200
    assert pacer.calls == len(opener.requests) == 1
    assert (
        urllib.parse.urlsplit(opener.requests[0].full_url).path
        == urllib.parse.urlsplit(request.url).path
    )


@pytest.mark.parametrize("kind", ["submit", "cancel", "token"])
def test_generic_transport_still_rejects_live_host_before_pacing(kind):
    request = _generic_request(kind)
    request = replace(
        request, url=request.url.replace("openapivts", "openapi").replace("29443", "9443")
    )
    transport, pacer, opener = _transport()
    with pytest.raises(KisPaperCanaryError):
        transport.request(request)
    assert pacer.calls == 0 and opener.requests == []


@pytest.mark.parametrize("kind", ["asking_price", "price_detail", "submit", "cancel", "token"])
@pytest.mark.parametrize("failure", [OSError, TimeoutError, urllib.error.URLError])
def test_transport_failure_never_exposes_raw_exception_cause(kind, failure):
    secret = "synthetic-private-url-and-token"
    request = (
        _quote_request(kind) if kind in {"asking_price", "price_detail"} else _generic_request(kind)
    )
    transport, _, _ = _transport()

    class FailingOpener:
        def open(self, *_args, **_kwargs):
            raise failure(secret)

    transport._opener = FailingOpener()
    with pytest.raises(KisPaperCanaryError, match="^transport_failure$") as caught:
        transport.request(request)
    error = caught.value
    assert error.__cause__ is None and error.__suppress_context__
    assert secret not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize("kind", ["asking_price", "price_detail", "submit"])
def test_http_error_retains_generic_response_semantics(kind):
    request = _generic_request() if kind == "submit" else _quote_request(kind)
    transport, _, _ = _transport()

    class FailingOpener:
        def open(self, *_args, **_kwargs):
            raise urllib.error.HTTPError(
                "synthetic", 429, "synthetic", {"tr_cont": "D"}, io.BytesIO(b"{}")
            )

    transport._opener = FailingOpener()
    result = transport.request(request)
    assert result.status_code == 429 and result.body == b"{}" and result.header("tr_cont") == "D"


@pytest.mark.parametrize("kind", ["asking_price", "price_detail", "submit"])
def test_expiry_rechecked_after_shared_pacing_immediately_before_open(kind):
    ticks, sleeps = [0.0], []

    def sleep(delay):
        sleeps.append(delay)
        ticks[0] += delay

    pacer = old.KisPaperRequestPacer(monotonic_clock=lambda: ticks[0], sleeper=sleep)
    transport = UrllibKisPaperStockCanaryTransport(instrument=INSTRUMENT, pacer=pacer)
    opener = Opener()
    transport._opener = opener
    transport.request(_quote_request())
    request = _generic_request() if kind == "submit" else _quote_request(kind)
    with pytest.raises(KisPaperCanaryError, match="^intent_expired$"):
        transport.request_before_deadline(
            request,
            deadline=NOW + timedelta(seconds=1),
            clock=lambda: NOW + timedelta(seconds=ticks[0]),
        )
    assert sleeps == [1.0] and len(opener.requests) == 1


def test_client_submit_uses_inherited_post_pacing_deadline_dispatch():
    ticks = [0.0]

    def sleep(delay):
        ticks[0] += delay

    transport = UrllibKisPaperStockCanaryTransport(
        instrument=INSTRUMENT,
        pacer=old.KisPaperRequestPacer(monotonic_clock=lambda: ticks[0], sleeper=sleep),
    )
    opener = Opener()
    transport._opener = opener
    transport.request(_quote_request())
    value = _client(transport)
    value._access_token = "synthetic-token"
    intent = replace(_intent(), valid_until=NOW + timedelta(seconds=1))
    with pytest.raises(KisPaperCanaryError, match="intent_expired"):
        value.submit_limit(intent, now=NOW, clock=lambda: NOW + timedelta(seconds=ticks[0]))
    assert len(opener.requests) == 1 and ticks[0] == 1.0


@pytest.mark.parametrize("bound", [None, "SYNTH", object()])
def test_invalid_instrument_rejected_at_both_constructors(bound):
    with pytest.raises(KisPaperCanaryError, match="stock_instrument_invalid"):
        _client(instrument=bound)
    with pytest.raises(KisPaperCanaryError, match="stock_instrument_invalid"):
        UrllibKisPaperStockCanaryTransport(instrument=bound, pacer=Pacer())


def test_client_and_transport_exact_binding_must_agree():
    other = KisPaperStockInstrument(INSTRUMENT.symbol, "ref:" + "b" * 64)
    transport = UrllibKisPaperStockCanaryTransport(instrument=other, pacer=Pacer())
    with pytest.raises(KisPaperCanaryError, match="stock_transport_binding_mismatch"):
        _client(transport)


def test_stock_is_canary_subclass_not_an_alternate_execution_engine():
    value = _client()
    assert isinstance(value, KisPaperCanaryClient) and value.instrument == INSTRUMENT
    assert KisPaperStockCanaryClient.snapshot is KisPaperCanaryClient.snapshot
    assert (
        UrllibKisPaperStockCanaryTransport.request_before_deadline
        is UrllibKisPaperCanaryTransport.request_before_deadline
    )
    assert not hasattr(value, "state_root") and not hasattr(value, "intents")


@pytest.mark.parametrize("kind", ["submit", "cancel"])
@pytest.mark.parametrize("change", ["other", "spy", "qqq", "quote_venue", "other_venue", "missing"])
def test_transport_order_body_exact_target_checked_before_pacing(kind, change):
    request = _generic_request(kind)
    body = dict(request.json_body)
    if change == "missing":
        body.pop("PDNO")
    else:
        body.update(
            {
                "other": {"PDNO": "OTHER"},
                "spy": {"PDNO": "SPY"},
                "qqq": {"PDNO": "QQQ"},
                "quote_venue": {"OVRS_EXCG_CD": "NAS"},
                "other_venue": {"OVRS_EXCG_CD": "NYSE"},
            }[change]
        )
    request = replace(request, json_body=body)
    transport, pacer, opener = _transport()
    with pytest.raises(KisPaperCanaryError, match="^stock_instrument_mismatch$"):
        transport.request(request)
    assert pacer.calls == 0 and opener.requests == []


def test_generic_account_context_funds_remain_allowed_by_transport():
    recorded = FakeTransport()
    _client(recorded).snapshot()
    request = next(
        r
        for r in recorded.requests
        if r.headers.get("tr_id") == old.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id
    )
    assert request.query["ITEM_CD"] != INSTRUMENT.symbol
    transport, pacer, opener = _transport()
    assert transport.request(request).status_code == 200
    assert pacer.calls == len(opener.requests) == 1


def test_instrument_property_is_read_only_and_its_value_is_frozen():
    value = _client()
    assert value.instrument == INSTRUMENT
    with pytest.raises(AttributeError):
        value.instrument = KisPaperStockInstrument("OTHER", INSTRUMENT.binding_ref)
    with pytest.raises(FrozenInstanceError):
        value.instrument.symbol = "OTHER"


@pytest.mark.parametrize("operation", ["funds", "submit", "cancel", "reconcile"])
def test_tampered_bound_instrument_revalidated_before_any_wire(operation):
    recorded = FakeTransport()
    value = _client(recorded)
    value._stock_instrument = _tamper(INSTRUMENT, "binding_ref", "synthetic-raw-secret")
    with pytest.raises(KisPaperCanaryError, match="^stock_instrument_invalid$"):
        _call(value, operation)
    assert recorded.requests == []


def test_generic_serialization_delay_is_included_in_last_deadline_check(monkeypatch):
    transport, _, opener = _transport()
    events, ticks = [], [0]
    import json

    original = json.dumps

    def delayed_serialization(*args, **kwargs):
        events.append("serialized")
        ticks[0] += 1
        return original(*args, **kwargs)

    request = _generic_request()
    monkeypatch.setattr("thericher_v2.execution.kis_paper_canary.json.dumps", delayed_serialization)

    def clock():
        events.append("deadline_checked")
        return NOW + timedelta(seconds=ticks[0])

    with pytest.raises(KisPaperCanaryError, match="^intent_expired$"):
        transport.request_before_deadline(request, deadline=NOW + timedelta(seconds=1), clock=clock)
    assert events == ["serialized", "deadline_checked"] and opener.requests == []


@pytest.mark.parametrize("with_deadline", [False, True])
@pytest.mark.parametrize(
    "kind,field",
    [
        ("submit", "json_body"),
        ("cancel", "json_body"),
        ("submit", "headers"),
        ("cancel", "headers"),
        ("asking_price", "headers"),
        ("price_detail", "headers"),
        ("funds", "headers"),
        ("submit", "query"),
        ("cancel", "query"),
        ("asking_price", "query"),
        ("price_detail", "query"),
        ("funds", "query"),
        ("submit", "all"),
        ("cancel", "all"),
        ("asking_price", "all"),
        ("price_detail", "all"),
        ("funds", "all"),
    ],
)
def test_mutable_request_aliases_during_pacing_cannot_change_validated_wire(
    kind, field, with_deadline
):
    if kind in {"asking_price", "price_detail"}:
        request = _quote_request(kind)
    elif kind == "funds":
        recorded = FakeTransport()
        _client(recorded).orderable_funds_at_limit(
            symbol=INSTRUMENT.symbol,
            exchange="NASD",
            limit_price=D("100.01000000"),
        )
        request = recorded.requests[-1]
    else:
        request = _generic_request(kind)
    original_headers, original_query = dict(request.headers), dict(request.query)
    original_body = None if request.json_body is None else dict(request.json_body)
    mutations = {
        "headers": {"authorization": "Bearer synthetic-mutated-token", "tr_id": "FOREIGN"},
        "query": {"SYMB": "OTHER", "EXCD": "NYS", "ITEM_CD": "OTHER"},
        "json_body": {"PDNO": "OTHER", "OVRS_EXCG_CD": "NYSE", "CANO": "87654321"},
    }
    names = ("headers", "query", "json_body") if field == "all" else (field,)
    aliases = {name: getattr(request, name) for name in names if getattr(request, name) is not None}

    class MutatingPacer(Pacer):
        def wait_for_request_slot(self):
            super().wait_for_request_slot()
            for name, alias in aliases.items():
                alias.clear()
                alias.update(mutations[name])

    pacer, opener = MutatingPacer(), Opener()
    transport = UrllibKisPaperStockCanaryTransport(instrument=INSTRUMENT, pacer=pacer)
    transport._opener = opener
    if with_deadline:
        result = transport.request_before_deadline(
            request,
            deadline=NOW + timedelta(seconds=1),
            clock=lambda: NOW,
        )
    else:
        result = transport.request(request)
    assert result.status_code == 200 and pacer.calls == len(opener.requests) == 1
    assert all(getattr(request, name) == mutations[name] for name in aliases)
    sent = opener.requests[0]
    assert {key.lower(): value for key, value in sent.header_items()} == {
        key.lower(): value for key, value in original_headers.items()
    }
    assert urllib.parse.parse_qs(
        urllib.parse.urlsplit(sent.full_url).query, keep_blank_values=True
    ) == {key: [value] for key, value in original_query.items()}
    assert (None if sent.data is None else json.loads(sent.data)) == original_body
