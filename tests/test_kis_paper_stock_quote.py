"""Synthetic request scopes only: no credentials, provider, accounts or orders."""

from __future__ import annotations

import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_paper_quote import (
    KIS_PAPER_PREVIEW_VENUES,
    KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
    KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
    KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
    KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
    KisPaperQuoteError,
    build_kis_paper_preview_quote_request,
    validate_kis_paper_preview_quote_request,
)
from thericher_v2.execution.kis_paper_stock_quote import (
    KisPaperStockInstrument,
    build_kis_paper_stock_quote_request,
    validate_kis_paper_stock_quote_request,
)
from thericher_v2.execution.kis_readonly import KIS_PAPER_BASE_URL, KisPaperConfig

BINDING = "ref:" + "a" * 64
SYMBOL = "SYNSTOCK"


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def blocked(*_args, **_kwargs):
        pytest.fail("external_call_forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config", blocked)


@pytest.fixture
def config():
    return KisPaperConfig("fake-app-key", "fake-app-secret", "12345678", "01")


@pytest.fixture
def instrument():
    return KisPaperStockInstrument(SYMBOL, BINDING)


@pytest.mark.parametrize(
    "kind,path,tr_id",
    [
        ("asking_price", KIS_PAPER_US_SPY_ASKING_PRICE_PATH, KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID),
        ("price_detail", KIS_PAPER_US_SPY_PRICE_DETAIL_PATH, KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID),
    ],
)
def test_exact_bound_stock_request(config, instrument, kind, path, tr_id):
    request = build_kis_paper_stock_quote_request(
        config=config, access_token="fake-token", instrument=instrument, kind=kind
    )
    assert request.method == "GET" and request.json_body is None
    assert request.url == KIS_PAPER_BASE_URL + path
    assert request.query == {"AUTH": "", "EXCD": "NAS", "SYMB": SYMBOL}
    assert request.headers == {
        "authorization": "Bearer fake-token",
        "appkey": "fake-app-key",
        "appsecret": "fake-app-secret",
        "tr_id": tr_id,
        "custtype": "P",
        "tr_cont": "",
    }
    validate_kis_paper_stock_quote_request(request, instrument=instrument)
    assert BINDING not in str(request.query)
    for private in (SYMBOL, BINDING, "fake-token", "fake-app-key", "fake-app-secret"):
        assert private not in repr(instrument) and private not in repr(request)


def test_instrument_literal_venues_frozen_and_exact_identity(instrument):
    assert (instrument.market, instrument.quote_exchange, instrument.order_exchange) == (
        "US",
        "NAS",
        "NASD",
    )
    assert instrument == KisPaperStockInstrument(SYMBOL, BINDING)
    assert instrument != KisPaperStockInstrument(SYMBOL, "ref:" + "b" * 64)
    for name, value in (("symbol", "OTHER"), ("binding_ref", "ref:" + "b" * 64)):
        with pytest.raises(FrozenInstanceError):
            setattr(instrument, name, value)


@pytest.mark.parametrize("symbol", ["A", "ABCDEFGHIJ"])
def test_symbol_grammar_boundaries(symbol):
    assert KisPaperStockInstrument(symbol, BINDING).symbol == symbol


@pytest.mark.parametrize(
    "symbol",
    [
        None,
        True,
        123,
        "",
        "lower",
        " Mixed",
        "MIXED ",
        "A\n",
        "A1",
        "A.B",
        "A-B",
        "A/B",
        "ÄBC",
        "ABCDEFGHIJK",
        "https://example.invalid",
    ],
)
def test_invalid_symbol_is_not_normalized_or_exposed(symbol):
    with pytest.raises(KisPaperQuoteError, match="^stock_symbol_invalid$"):
        KisPaperStockInstrument(symbol, BINDING)


@pytest.mark.parametrize(
    "binding",
    [
        None,
        True,
        1,
        "",
        "a" * 64,
        "sha256:" + "a" * 64,
        "ref:" + "A" * 64,
        "ref:" + "a" * 63,
        "ref:" + "a" * 65,
        BINDING + "\n",
        BINDING + " ",
        "ref:fake_secret",
    ],
)
def test_malformed_binding_is_rejected_without_echo(binding):
    with pytest.raises(KisPaperQuoteError, match="^stock_binding_ref_invalid$"):
        KisPaperStockInstrument(SYMBOL, binding)


@pytest.mark.parametrize(
    "kind", [None, True, [], "price", "balance", "ASKING_PRICE", "asking_price "]
)
def test_unknown_route_kind_rejects(config, instrument, kind):
    with pytest.raises(KisPaperQuoteError, match="^stock_quote_kind_invalid$"):
        build_kis_paper_stock_quote_request(
            config=config, access_token="fake-token", instrument=instrument, kind=kind
        )


@pytest.mark.parametrize("token", [None, True, "", " ", "\r\n"])
def test_missing_token_rejects(config, instrument, token):
    with pytest.raises(KisPaperQuoteError, match="^quote_access_token_invalid$"):
        build_kis_paper_stock_quote_request(
            config=config, access_token=token, instrument=instrument, kind="asking_price"
        )


@pytest.mark.parametrize("kind", ["asking_price", "price_detail"])
@pytest.mark.parametrize(
    "change",
    [
        {"method": "POST"},
        {"method": "get"},
        {"method": "DELETE"},
        {"json_body": {}},
        {"url": "https://openapi.koreainvestment.com:9443"},
        {"url": "http://openapivts.koreainvestment.com:29443"},
        {"url": "https://openapivts.koreainvestment.com"},
        {"url": "https://user:pass@openapivts.koreainvestment.com:29443"},
        {"url": "https://openapivts.koreainvestment.com:29443.evil.invalid"},
        {"url": None},
        {"query": {"AUTH": "", "EXCD": "NASD", "SYMB": SYMBOL}},
        {"query": {"AUTH": "", "EXCD": "NYS", "SYMB": SYMBOL}},
        {"query": {"AUTH": "", "EXCD": "AMS", "SYMB": SYMBOL}},
        {"query": {"AUTH": "", "EXCD": "NAS", "SYMB": "OTHER"}},
        {"query": {"AUTH": "", "EXCD": "NAS", "SYMB": SYMBOL.lower()}},
        {"query": {"AUTH": "fake_secret", "EXCD": "NAS", "SYMB": SYMBOL}},
        {"query": {"EXCD": "NAS", "SYMB": SYMBOL}},
        {"query": {"AUTH": "", "EXCD": "NAS", "SYMB": SYMBOL, "extra": ""}},
        {"query": {"AUTH": "", "EXCD": "NAS", "SYMB": 1}},
        {"query": None},
    ],
)
def test_host_method_body_and_query_scope_falsifiers(config, instrument, kind, change):
    request = build_kis_paper_stock_quote_request(
        config=config, access_token="fake-token", instrument=instrument, kind=kind
    )
    with pytest.raises(KisPaperQuoteError, match="^stock_quote_request_invalid$"):
        validate_kis_paper_stock_quote_request(replace(request, **change), instrument=instrument)


@pytest.mark.parametrize("kind", ["asking_price", "price_detail"])
@pytest.mark.parametrize(
    "suffix", ["?SYMB=OTHER", "#fake_secret", ";extra", "/", "/../price", "%3Fextra", "\n", "\t"]
)
def test_url_suffixes_are_not_redirect_or_route_alternatives(config, instrument, kind, suffix):
    request = build_kis_paper_stock_quote_request(
        config=config, access_token="fake-token", instrument=instrument, kind=kind
    )
    with pytest.raises(KisPaperQuoteError, match="stock_quote_request_invalid"):
        validate_kis_paper_stock_quote_request(
            replace(request, url=request.url + suffix), instrument=instrument
        )


@pytest.mark.parametrize("kind", ["asking_price", "price_detail"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("authorization", ""),
        ("authorization", "Bearer "),
        ("authorization", "Basic fake_secret"),
        ("authorization", "Bearer fake_secret\r\nExtra: value"),
        ("appkey", ""),
        ("appkey", True),
        ("appsecret", ""),
        ("appsecret", "fake_secret\n"),
        ("tr_id", "VTTT1002U"),
        ("tr_id", "HHDFS00000300"),
        ("custtype", "B"),
        ("tr_cont", "N"),
        ("tr_cont", "F"),
    ],
)
def test_header_falsifiers(config, instrument, kind, field, value):
    request = build_kis_paper_stock_quote_request(
        config=config, access_token="fake-token", instrument=instrument, kind=kind
    )
    with pytest.raises(KisPaperQuoteError, match="^stock_quote_request_invalid$"):
        validate_kis_paper_stock_quote_request(
            replace(request, headers={**request.headers, field: value}), instrument=instrument
        )


@pytest.mark.parametrize("kind", ["asking_price", "price_detail"])
def test_header_sets_and_crossed_route_transaction_reject(config, instrument, kind):
    request = build_kis_paper_stock_quote_request(
        config=config, access_token="fake-token", instrument=instrument, kind=kind
    )
    opposite_tr = (
        KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID
        if kind == "asking_price"
        else KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID
    )
    changes = [
        {**request.headers, "extra": "fake_secret"},
        {**request.headers, "tr_id": opposite_tr},
        None,
    ]
    changes.extend(
        {k: v for k, v in request.headers.items() if k != missing} for missing in request.headers
    )
    for headers in changes:
        with pytest.raises(KisPaperQuoteError, match="^stock_quote_request_invalid$"):
            validate_kis_paper_stock_quote_request(
                replace(request, headers=headers), instrument=instrument
            )


def test_no_other_endpoint_or_same_shape_fallback(config, instrument):
    request = build_kis_paper_stock_quote_request(
        config=config, access_token="fake-token", instrument=instrument, kind="asking_price"
    )
    for path in (
        "/oauth2/tokenP",
        "/uapi/overseas-stock/v1/trading/order",
        "/uapi/overseas-stock/v1/trading/inquire-psamount",
        "/uapi/overseas-price/v1/quotations/price",
    ):
        with pytest.raises(KisPaperQuoteError, match="^stock_quote_request_invalid$"):
            validate_kis_paper_stock_quote_request(
                replace(request, url=KIS_PAPER_BASE_URL + path), instrument=instrument
            )
    other = KisPaperStockInstrument("OTHER", BINDING)
    with pytest.raises(KisPaperQuoteError, match="^stock_quote_request_invalid$"):
        validate_kis_paper_stock_quote_request(request, instrument=other)


@pytest.mark.parametrize("invalid", [None, {}, SimpleNamespace(symbol=SYMBOL, binding_ref=BINDING)])
def test_instrument_requires_exact_validated_dto(config, invalid):
    with pytest.raises(KisPaperQuoteError, match="^stock_instrument_invalid$"):
        build_kis_paper_stock_quote_request(
            config=config, access_token="fake-token", instrument=invalid, kind="asking_price"
        )


def test_tampered_instrument_and_config_revalidated(config, instrument):
    object.__setattr__(instrument, "binding_ref", "fake_secret")
    with pytest.raises(KisPaperQuoteError, match="^stock_binding_ref_invalid$"):
        build_kis_paper_stock_quote_request(
            config=config, access_token="fake-token", instrument=instrument, kind="asking_price"
        )
    object.__setattr__(instrument, "binding_ref", BINDING)
    object.__setattr__(config, "base_url", "https://openapi.koreainvestment.com:9443")
    with pytest.raises(KisPaperQuoteError, match="^stock_quote_request_invalid$"):
        build_kis_paper_stock_quote_request(
            config=config, access_token="fake-token", instrument=instrument, kind="asking_price"
        )


def test_legacy_etf_allowlist_and_builders_are_unchanged(config, instrument):
    assert dict(KIS_PAPER_PREVIEW_VENUES) == {
        "SPY": ("AMS", "AMEX"),
        "TLT": ("NAS", "NASD"),
        "GLD": ("AMS", "AMEX"),
    }
    request = build_kis_paper_stock_quote_request(
        config=config, access_token="fake-token", instrument=instrument, kind="asking_price"
    )
    with pytest.raises(KisPaperQuoteError, match="^preview_quote_request_invalid$"):
        validate_kis_paper_preview_quote_request(request)
    with pytest.raises(KisPaperQuoteError, match="^preview_symbol_invalid$"):
        build_kis_paper_preview_quote_request(
            config=config, access_token="fake-token", symbol=SYMBOL, kind="asking_price"
        )
    for symbol, (venue, _) in KIS_PAPER_PREVIEW_VENUES.items():
        legacy = build_kis_paper_preview_quote_request(
            config=config, access_token="fake-token", symbol=symbol, kind="asking_price"
        )
        assert legacy.query["EXCD"] == venue
        validate_kis_paper_preview_quote_request(legacy)
