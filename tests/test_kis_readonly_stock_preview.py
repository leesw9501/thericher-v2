from __future__ import annotations

import builtins
import io
import socket
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution import kis_paper_stock_readonly as stock
from thericher_v2.execution import kis_readonly as old
from thericher_v2.execution.kis_paper_quote import (
    KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
    KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
    build_kis_paper_preview_quote_request,
)
from thericher_v2.execution.kis_paper_spy_fill_cycle import _digest
from thericher_v2.execution.kis_paper_stock_quote import (
    KisPaperStockInstrument,
    build_kis_paper_stock_quote_request,
    validate_kis_paper_stock_quote_request,
)

D = Decimal
INSTRUMENT = KisPaperStockInstrument("SYNTH", "ref:" + "a" * 64)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("actual_network_forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)


def config():
    return old.KisPaperConfig("synthetic-key", "synthetic-secret", "12345678", "01")


def funds_response():
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


@dataclass
class FakeTransport:
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    requests: list = field(default_factory=list)
    quote_age: int = 0
    final_delay: int = 0
    bad_tick: bool = False
    quote_continuation: str = ""
    funds_fault: str = ""

    def request(self, request):
        try:
            old.validate_kis_paper_readonly_request(request)
        except old.KisPaperReadOnlyError:
            validate_kis_paper_stock_quote_request(request, instrument=INSTRUMENT)
        self.requests.append(request)
        if request.method == "POST":
            assert request.url.endswith("/oauth2/tokenP")
            return old.KisHttpResponse.from_payload({"access_token": "synthetic-token"})
        tr_id = request.headers["tr_id"]
        if tr_id == old.KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
            return old.KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == old.KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            return old.KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
        if tr_id == old.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            if request.query["ITEM_CD"] == INSTRUMENT.symbol:
                self.now += timedelta(seconds=self.final_delay)
                if self.funds_fault == "duplicate":
                    return old.KisHttpResponse(200, {}, b'{"rt_cd":"0","output":{},"output":{}}')
                if self.funds_fault == "continuation":
                    response = funds_response()
                    return replace(response, headers={"tr_cont": "M"})
            return funds_response()
        if tr_id == KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID:
            return old.KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "zdiv": "2",
                        "e_hogau": "0" if self.bad_tick else "0.01",
                    },
                },
                headers={"tr_cont": self.quote_continuation},
            )
        assert tr_id == KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID
        korea = (self.now - timedelta(seconds=self.quote_age)).astimezone(ZoneInfo("Asia/Seoul"))
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
            },
            headers={"tr_cont": self.quote_continuation},
        )


def client(transport, token=None):
    return stock.KisPaperStockReadOnlyClient(
        config=config(), transport=transport, access_token=token
    )


def account_ref(value):
    cfg = value._config
    return _digest([cfg.base_url, cfg.account_number, cfg.account_product_code])


def preview(value, transport, **changes):
    return value.stock_preview_snapshot(
        **(
            dict(
                instrument=INSTRUMENT,
                expected_account_ref=account_ref(value),
                clock=lambda: transport.now,
            )
            | changes
        )
    )


def quote_request(kind="asking_price"):
    return build_kis_paper_stock_quote_request(
        config=config(),
        access_token="synthetic-token",
        instrument=INSTRUMENT,
        kind=kind,
    )


def test_account_first_two_quotes_exact_funds_one_token_reused():
    transport = FakeTransport()
    value = client(transport)
    result = preview(value, transport)
    assert type(result) is stock.KisPaperStockPreviewReads
    assert result.instrument == INSTRUMENT
    assert len(transport.requests) == 9
    assert [r.headers.get("tr_id") for r in transport.requests[6:8]] == [
        KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
        KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
    ]
    exact = transport.requests[-1]
    assert exact.query["ITEM_CD"] == INSTRUMENT.symbol
    assert exact.query["OVRS_EXCG_CD"] == "NASD"
    assert exact.query["OVRS_ORD_UNPR"] == "100.01"
    assert result.buy_limit == D("100.01")
    assert (
        result.orderable.reference_symbol,
        result.orderable.reference_exchange,
        result.orderable.reference_price,
    ) == (INSTRUMENT.symbol, "NASD", result.buy_limit)
    assert account_ref(value) not in repr(result) and INSTRUMENT.symbol not in repr(result)
    preview(value, transport)
    assert sum(r.method == "POST" for r in transport.requests) == 1
    assert all(r.url.endswith("/oauth2/tokenP") for r in transport.requests if r.method == "POST")


def test_wrong_account_precedes_authentication():
    transport = FakeTransport()
    with pytest.raises(old.KisPaperReadOnlyError, match="stock_account_binding_mismatch"):
        preview(client(transport), transport, expected_account_ref="b" * 64)
    assert transport.requests == []


@pytest.mark.parametrize("instrument", [None, "SYNTH", object()])
def test_wrong_instrument_precedes_authentication(instrument):
    transport = FakeTransport()
    with pytest.raises(old.KisPaperReadOnlyError, match="stock_instrument_invalid"):
        preview(client(transport), transport, instrument=instrument)
    assert transport.requests == []


@pytest.mark.parametrize("field,value", [("symbol", "lower"), ("binding_ref", "ref:wrong")])
def test_tampered_frozen_instrument_revalidated_before_authentication(field, value):
    bound = replace(INSTRUMENT)
    object.__setattr__(bound, field, value)
    transport = FakeTransport()
    with pytest.raises(old.KisPaperReadOnlyError, match="stock_instrument_invalid"):
        preview(client(transport), transport, instrument=bound)
    assert transport.requests == []


@pytest.mark.parametrize(
    "price", [True, 100.0, D("NaN"), D("Infinity"), D(0), D(-1), D("0.000000001"), D("1e23")]
)
def test_invalid_exact_limit_precedes_token(price):
    transport = FakeTransport()
    with pytest.raises(old.KisPaperReadOnlyError, match="orderability_price_invalid"):
        client(transport).stock_orderable_funds_at_limit(instrument=INSTRUMENT, limit_price=price)
    assert transport.requests == []


def test_exact_limit_keeps_precision_and_existing_token():
    transport = FakeTransport()
    value = client(transport, token="synthetic-token")
    cash, funds = value.stock_orderable_funds_at_limit(
        instrument=INSTRUMENT,
        limit_price=D("100.01000000"),
        clock=lambda: transport.now,
    )
    assert len(transport.requests) == 1
    assert transport.requests[0].query["OVRS_ORD_UNPR"] == "100.01000000"
    assert cash.currency == funds.currency == "USD"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"quote_age": 121}, "quote_timestamp_stale"),
        ({"bad_tick": True}, "quote_tick_invalid"),
        ({"quote_continuation": "M"}, "stock_quote_incomplete"),
        ({"final_delay": 121}, "stock_snapshot_stale"),
        ({"funds_fault": "duplicate"}, "response_invalid"),
        ({"funds_fault": "continuation"}, "orderable_funds_pagination_incomplete"),
    ],
)
def test_stale_or_invalid_observation_is_scoped_unavailable(change, reason):
    transport = FakeTransport(**change)
    with pytest.raises(old.KisPaperReadOnlyError, match=reason):
        preview(client(transport), transport)


@pytest.mark.parametrize(
    "change",
    [
        {"query": {"AUTH": "", "EXCD": "NAS", "SYMB": "OTHER"}},
        {"query": {"AUTH": "", "EXCD": "NYS", "SYMB": "SYNTH"}},
        {
            "url": "https://openapi.koreainvestment.com:9443/uapi/overseas-price/v1/quotations/price-detail"
        },
        {"method": "POST"},
    ],
)
def test_client_validates_stock_scope_before_injected_transport(change):
    transport = FakeTransport()
    request = replace(quote_request(), **change)
    with pytest.raises(old.KisPaperReadOnlyError, match="request_not_allowlisted"):
        client(transport)._dispatch_stock_quote(request, instrument=INSTRUMENT)
    assert transport.requests == []


def test_shadow_has_no_filesystem_environment_or_store_access(monkeypatch):
    transport = FakeTransport()
    value = client(transport)

    def deny(*args, **kwargs):
        raise AssertionError("private_write_or_environment_forbidden")

    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(old.os, "getenv", deny)
    result = preview(value, transport)
    assert result.snapshot.open_orders.complete is True


class FakeResponse:
    status = 200
    headers = {"content-type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"rt_cd":"0"}'


def wired_transport(monkeypatch, *, instrument=INSTRUMENT):
    calls, slots = [], []
    transport = stock.UrllibKisPaperStockHttpTransport(instrument=instrument, timeout_seconds=3)

    def fake_open(request, *, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(transport._opener, "open", fake_open)
    monkeypatch.setattr(transport._pacer, "wait_for_request_slot", lambda: slots.append(True))
    return transport, calls, slots


def test_scoped_wire_uses_inherited_opener_timeout_and_single_pacer(monkeypatch):
    transport, calls, slots = wired_transport(monkeypatch)
    response = transport.request(quote_request())
    assert response.status_code == 200
    assert len(calls) == len(slots) == 1
    wire, timeout = calls[0]
    assert timeout == 3 and wire.method == "GET" and wire.data is None
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(wire.full_url).query)["SYMB"] == ["SYNTH"]


def test_legacy_request_delegates_unchanged_to_super(monkeypatch):
    calls = []
    monkeypatch.setattr(
        old.UrllibKisHttpTransport, "request", lambda self, request: calls.append(request)
    )
    transport = stock.UrllibKisPaperStockHttpTransport(instrument=INSTRUMENT)
    request = old.KisHttpRequest(
        "POST",
        old.KIS_PAPER_BASE_URL + old.KIS_PAPER_TOKEN_PATH,
        {"content-type": "application/json", "accept": "application/json"},
        json_body={"grant_type": "client_credentials", "appkey": "fake", "appsecret": "fake"},
    )
    transport.request(request)
    assert calls == [request]


@pytest.mark.parametrize(
    "change",
    [
        {"query": {"AUTH": "", "EXCD": "NAS", "SYMB": "OTHER"}},
        {"method": "POST"},
        {"url": old.KIS_PAPER_BASE_URL + "/uapi/overseas-stock/v1/trading/order"},
    ],
)
def test_native_scope_rejects_before_pace_or_wire(monkeypatch, change):
    transport, calls, slots = wired_transport(monkeypatch)
    with pytest.raises(old.KisPaperReadOnlyError):
        transport.request(replace(quote_request(), **change))
    assert calls == slots == []


@pytest.mark.parametrize("failure", ["timeout", "http", "redirect"])
def test_native_wire_failure_keeps_existing_categories(monkeypatch, failure):
    transport, _, _ = wired_transport(monkeypatch)

    def fail(*args, **kwargs):
        if failure == "http":
            raise urllib.error.HTTPError(
                "https://synthetic.invalid", 429, "not retained", {}, io.BytesIO(b'{"rt_cd":"1"}')
            )
        if failure == "redirect":
            raise old.KisPaperReadOnlyError("redirect_rejected")
        raise TimeoutError

    monkeypatch.setattr(transport._opener, "open", fail)
    if failure == "http":
        assert transport.request(quote_request()).status_code == 429
    else:
        with pytest.raises(
            old.KisPaperReadOnlyError,
            match="redirect_rejected" if failure == "redirect" else "transport_failure",
        ):
            transport.request(quote_request())


def test_native_failure_suppresses_private_exception_chain(monkeypatch):
    transport, _, _ = wired_transport(monkeypatch)

    def fail(*args, **kwargs):
        raise urllib.error.URLError("synthetic-private-sentinel")

    monkeypatch.setattr(transport._opener, "open", fail)
    with pytest.raises(old.KisPaperReadOnlyError, match="transport_failure") as caught:
        transport.request(quote_request())
    assert "synthetic-private-sentinel" not in "".join(traceback.format_exception(caught.value))


def test_native_constructor_keeps_empty_proxy_and_redirect_rejector(monkeypatch):
    handlers = []
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: handlers.extend(args))
    stock.UrllibKisPaperStockHttpTransport(instrument=INSTRUMENT)
    assert type(handlers[0]) is urllib.request.ProxyHandler and handlers[0].proxies == {}
    assert type(handlers[1]) is old._RejectRedirectHandler


def test_legacy_default_still_rejects_stock():
    with pytest.raises(old.KisPaperReadOnlyError):
        old.validate_kis_paper_readonly_request(quote_request())


@pytest.mark.parametrize("symbol", ["SPY", "TLT", "GLD"])
@pytest.mark.parametrize("kind", ["asking_price", "price_detail"])
def test_aapl_transport_rejects_valid_legacy_etf_quotes_before_wire(monkeypatch, symbol, kind):
    bound = KisPaperStockInstrument("AAPL", "ref:" + "b" * 64)
    transport, calls, slots = wired_transport(monkeypatch, instrument=bound)
    request = build_kis_paper_preview_quote_request(
        config=config(),
        access_token="synthetic-token",
        symbol=symbol,
        kind=kind,
    )
    old.validate_kis_paper_readonly_request(request)
    with pytest.raises(old.KisPaperReadOnlyError, match="request_not_allowlisted"):
        transport.request(request)
    assert calls == slots == []
