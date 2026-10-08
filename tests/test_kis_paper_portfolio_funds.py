"""Native Paper client and exact-funds lifecycle; only the wire is synthetic."""

from __future__ import annotations

import socket
import subprocess
import urllib.request
from datetime import datetime
from decimal import Decimal

import pytest

import test_kis_paper_portfolio_execute as examples
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_portfolio_execute as execution
from thericher_v2.execution import kis_readonly as readonly

D = Decimal
VENUES = (("QQQ", "NASD"), ("SPY", "AMEX"), ("TLT", "NASD"), ("GLD", "AMEX"))
TOKEN = "SYNTHETIC_TOKEN"


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("synthetic funds tests cannot access network, credentials or processes")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setattr(readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(readonly, "load_kis_paper_config_from_environment", deny)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", deny)
    monkeypatch.setattr(canary.UrllibKisPaperCanaryTransport, "request", deny)


class Wire:
    def __init__(self):
        self.requests = []
        self.failure = None
        self.before_buy = lambda request: None

    def request(self, request):
        canary.validate_kis_paper_canary_request(request)
        self.requests.append(request)
        if request.url == examples.CONFIG.base_url + readonly.KIS_PAPER_TOKEN_PATH:
            if self.failure == "auth":
                return readonly.KisHttpResponse.from_payload(
                    {"msg1": "BODY_SECRET"}, status_code=403
                )
            return readonly.KisHttpResponse.from_payload({"access_token": TOKEN})
        tr_id = request.headers["tr_id"]
        if tr_id == readonly.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            if self.failure == "transport":
                raise OSError("synthetic wire failure")
            if self.failure == "http":
                return readonly.KisHttpResponse.from_payload(
                    {"msg1": "BODY_SECRET"}, status_code=403
                )
            return readonly.KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "tr_crcy_cd": "USD",
                        "ord_psbl_frcr_amt": "10000",
                        "ovrs_ord_psbl_amt": "BODY_SECRET"
                        if self.failure == "payload"
                        else "10000",
                    },
                }
            )
        if tr_id == readonly.KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            return readonly.KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
        if tr_id in {
            readonly.KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id,
            canary.KIS_PAPER_US_CCNCL_TR_ID,
        }:
            return readonly.KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        assert request.method == "POST" and tr_id == canary.KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        self.before_buy(request)
        return readonly.KisHttpResponse.from_payload(
            {"rt_cd": "0", "output": {"ODNO": "SYNTHETIC_ORDER"}}
        )


def client(wire, *, token=TOKEN):
    result = canary.KisPaperCanaryClient(config=examples.CONFIG, transport=wire)
    result._access_token = token
    return result


@pytest.mark.parametrize("symbol,exchange", VENUES)
def test_exact_funds_native_route_price_and_cached_token(symbol, exchange):
    wire = Wire()
    actual = client(wire)
    price = D("100.0100")
    cash, funds = actual.orderable_funds_at_limit(
        symbol=symbol, exchange=exchange, limit_price=price
    )
    assert len(wire.requests) == 1
    request = wire.requests[0]
    assert request.method == "GET"
    assert (
        request.url == examples.CONFIG.base_url + readonly.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.path
    )
    assert request.query["ITEM_CD"] == symbol and request.query["OVRS_EXCG_CD"] == exchange
    assert request.query["OVRS_ORD_UNPR"] == "100.0100"
    assert request.headers["authorization"] == "Bearer " + TOKEN
    assert (funds.reference_symbol, funds.reference_exchange, funds.reference_price) == (
        symbol,
        exchange,
        price,
    )
    assert cash.currency == funds.currency == "USD" and actual._access_token == TOKEN


@pytest.mark.parametrize(
    "symbol,exchange,reason",
    [
        ("SPY", "NASD", "orderability_exchange_invalid"),
        ("TLT", "AMEX", "orderability_exchange_invalid"),
        ("GLD", "NYSE", "orderability_exchange_invalid"),
        ("QQQ", "AMEX", "orderability_exchange_invalid"),
        ("SPY", None, "orderability_exchange_invalid"),
        ("IWM", "AMEX", "orderability_symbol_invalid"),
        ("tlt", "NASD", "orderability_symbol_invalid"),
        (None, "NASD", "orderability_symbol_invalid"),
        (True, "NASD", "orderability_symbol_invalid"),
        ([], "NASD", "orderability_symbol_invalid"),
    ],
)
def test_wrong_venue_or_unapproved_symbol_rejects_before_any_wire(symbol, exchange, reason):
    wire = Wire()
    actual = client(wire, token=None)
    with pytest.raises(readonly.KisPaperReadOnlyError) as observed:
        actual.orderable_funds_at_limit(symbol=symbol, exchange=exchange, limit_price=D(100))
    assert observed.value.code == reason and wire.requests == [] and actual._access_token is None


@pytest.mark.parametrize("symbol,exchange", VENUES)
@pytest.mark.parametrize(
    "price", [D("NaN"), D("Infinity"), D(0), D(-1), D("1E-9"), D("1E23"), 1, True]
)
def test_same_native_price_domain_rejects_before_token_or_get(symbol, exchange, price):
    wire = Wire()
    with pytest.raises(readonly.KisPaperReadOnlyError, match="orderability_price_invalid"):
        client(wire, token=None).orderable_funds_at_limit(
            symbol=symbol, exchange=exchange, limit_price=price
        )
    assert wire.requests == []


@pytest.mark.parametrize("symbol,exchange", VENUES)
def test_new_token_synced_and_reused_for_next_exact_funds(symbol, exchange):
    wire = Wire()
    actual = client(wire, token=None)
    for price in (D(100), D("100.01")):
        actual.orderable_funds_at_limit(symbol=symbol, exchange=exchange, limit_price=price)
    assert [r.method for r in wire.requests] == ["POST", "GET", "GET"]
    assert wire.requests[0].url.endswith("/oauth2/tokenP")
    assert actual._access_token == TOKEN


@pytest.mark.parametrize("symbol,exchange", VENUES)
@pytest.mark.parametrize(
    "failure,reason",
    [
        ("payload", "orderable_funds_response_incomplete"),
        ("http", "orderable_funds_rejected"),
        ("transport", None),
    ],
)
def test_token_backsync_even_after_exact_funds_failure(symbol, exchange, failure, reason):
    wire = Wire()
    wire.failure = failure
    actual = client(wire, token=None)
    with pytest.raises(OSError if reason is None else readonly.KisPaperReadOnlyError) as observed:
        actual.orderable_funds_at_limit(symbol=symbol, exchange=exchange, limit_price=D(100))
    if reason is not None:
        assert observed.value.code == reason
        assert "BODY_SECRET" not in str(observed.value) + repr(observed.value)
    assert actual._access_token == TOKEN
    assert [r.method for r in wire.requests] == ["POST", "GET"]
    wire.failure = None
    actual.orderable_funds_at_limit(symbol=symbol, exchange=exchange, limit_price=D(100))
    assert [r.method for r in wire.requests] == ["POST", "GET", "GET"]


@pytest.mark.parametrize("symbol,exchange", VENUES)
def test_failed_auth_does_not_create_or_retain_token(symbol, exchange):
    wire = Wire()
    wire.failure = "auth"
    actual = client(wire, token=None)
    with pytest.raises(readonly.KisPaperReadOnlyError, match="auth_rejected"):
        actual.orderable_funds_at_limit(symbol=symbol, exchange=exchange, limit_price=D(100))
    assert actual._access_token is None and [r.method for r in wire.requests] == ["POST"]


@pytest.mark.parametrize("symbol", ["SPY", "TLT", "GLD"])
def test_real_native_client_portfolio_buy_reaches_exact_funds_and_persisted_submit(
    tmp_path, monkeypatch, symbol
):
    call = examples._leg(examples.harness.__wrapped__(tmp_path), symbol)
    now = examples.NOW

    class FixedTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(readonly, "datetime", FixedTime)
    wire = Wire()
    actual = client(wire)
    call.update(client=actual, clock=lambda: now)
    intent = execution._scope(call["state_root"], call["proof"], now)[2].intent

    def before_buy(request):
        state = examples._state(call)
        assert state.phase == "submission_started" and state.intent == intent
        binding = budget._load_binding(call["state_root"])
        assert budget._portfolio_seed_states(binding)[intent.run_id].intent == intent
        assert budget.project_budget(call["state_root"], binding, as_of=now).reserved_buys == D(900)
        assert request.json_body["PDNO"] == symbol
        assert request.json_body["OVRS_EXCG_CD"] == intent.exchange

    wire.before_buy = before_buy
    outcome = execution.execute_kis_paper_portfolio_buy(**call)
    exact = [
        r
        for r in wire.requests
        if r.method == "GET"
        and r.headers["tr_id"] == readonly.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id
        and r.query["ITEM_CD"] == symbol
        and r.query["OVRS_EXCG_CD"] == intent.exchange
        and r.query["OVRS_ORD_UNPR"] == format(intent.limit_price, "f")
    ]
    assert len(exact) == 1 and sum(r.method == "POST" for r in wire.requests) == 1
    assert actual._access_token == TOKEN and outcome.phase == "submitted"
    assert examples._state(call).submitted_at == now
