from __future__ import annotations

import socket
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from thericher_v2.execution import kis_readonly as readonly


@pytest.fixture(autouse=True)
def deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network and credential access forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(readonly.UrllibKisHttpTransport, "request", deny)
    monkeypatch.setattr(readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(readonly, "load_kis_paper_config_from_environment", deny)


def _output() -> dict[str, str]:
    return {
        "tr_crcy_cd": "USD",
        "ord_psbl_frcr_amt": "1200.50",
        "ovrs_ord_psbl_amt": "1199.75",
    }


def _response(output: object = None, **kwargs: object) -> readonly.KisHttpResponse:
    return readonly.KisHttpResponse.from_payload(
        {"rt_cd": "0", "output": _output() if output is None else output}, **kwargs
    )


@dataclass
class _Transport:
    responses: list[readonly.KisHttpResponse | Exception] = field(default_factory=list)
    requests: list[readonly.KisHttpRequest] = field(default_factory=list)

    def request(self, request: readonly.KisHttpRequest) -> readonly.KisHttpResponse:
        self.requests.append(request)
        if request.method == "POST":
            assert request.url == readonly.KIS_PAPER_BASE_URL + readonly.KIS_PAPER_TOKEN_PATH
            return readonly.KisHttpResponse.from_payload({"access_token": "synthetic-token"})
        assert request.headers["tr_id"] == readonly.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id
        assert self.responses, "unexpected additional query"
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _client(transport: object, *, token: str | None = "synthetic-token") -> object:
    return readonly.KisPaperReadOnlyClient(
        config=readonly.KisPaperConfig(
            app_key="synthetic-key",
            app_secret="synthetic-secret",
            account_number="12345678",
            account_product_code="01",
        ),
        transport=transport,
        access_token=token,
    )


@pytest.mark.parametrize(
    ("price", "wire"),
    [
        (Decimal("500.1200"), "500.1200"),
        (Decimal("1E+2"), "100"),
        (Decimal("0.00000001"), "0.00000001"),
        (Decimal("99999999999999999999999.12345678"), "99999999999999999999999.12345678"),
    ],
)
@pytest.mark.parametrize("list_output", [False, True])
def test_exact_query_and_typed_reference_are_not_the_spy_default(
    price: Decimal, wire: str, list_output: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    transport = _Transport([_response([_output()] if list_output else _output())])
    cash, funds = _client(transport).orderable_funds_at_limit(
        symbol="QQQ", exchange="NASD", limit_price=price
    )
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET" and request.json_body is None
    assert (
        request.url
        == readonly.KIS_PAPER_BASE_URL + readonly.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.path
    )
    assert request.query == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",
        "OVRS_ORD_UNPR": wire,
        "ITEM_CD": "QQQ",
    }
    assert request.headers["tr_id"] == "VTTS3007R"
    assert request.headers["tr_cont"] == ""
    assert isinstance(cash, readonly.KisPaperCashSnapshot)
    assert isinstance(funds, readonly.KisPaperOrderableFundsSnapshot)
    assert cash.available_cash == Decimal("1200.50")
    assert funds.orderable_funds == Decimal("1199.75")
    assert (funds.reference_symbol, funds.reference_exchange, funds.reference_price) == (
        "QQQ",
        "NASD",
        price,
    )
    assert cash.currency == funds.currency == "USD"
    assert cash.captured_at == funds.captured_at
    assert "synthetic-secret" not in repr(request) and "12345678" not in repr(request)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("symbol", ["SPY", "IWM", "qqq", " QQQ", "QQQ ", "", None, True, 1])
def test_wrong_symbol_fails_before_token_or_get(symbol: object) -> None:
    transport = _Transport()
    with pytest.raises(readonly.KisPaperReadOnlyError, match="^orderability_symbol_invalid$"):
        _client(transport, token=None).orderable_funds_at_limit(
            symbol=symbol, exchange="NASD", limit_price=Decimal("500")
        )
    assert transport.requests == []


@pytest.mark.parametrize("exchange", ["NAS", "AMEX", "NYSE", "nasd", " NASD", "", None, True, 1])
def test_wrong_exchange_fails_before_token_or_get(exchange: object) -> None:
    transport = _Transport()
    with pytest.raises(readonly.KisPaperReadOnlyError, match="^orderability_exchange_invalid$"):
        _client(transport, token=None).orderable_funds_at_limit(
            symbol="QQQ", exchange=exchange, limit_price=Decimal("500")
        )
    assert transport.requests == []


@pytest.mark.parametrize(
    "price",
    [
        None,
        True,
        False,
        500,
        500.25,
        "500.25",
        Decimal("0"),
        Decimal("-0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("1E-9"),
        Decimal("1.000000000"),
        Decimal("1E+23"),
        Decimal("1E+999999"),
    ],
)
def test_invalid_or_unrepresentable_price_is_not_rounded_or_sent(price: object) -> None:
    transport = _Transport()
    with pytest.raises(readonly.KisPaperReadOnlyError, match="^orderability_price_invalid$"):
        _client(transport, token=None).orderable_funds_at_limit(
            symbol="QQQ", exchange="NASD", limit_price=price
        )
    assert transport.requests == []


@pytest.mark.parametrize("key", ["ord_psbl_frcr_amt", "ovrs_ord_psbl_amt"])
@pytest.mark.parametrize(
    "value", [None, True, 1, 1.25, "", " 1", "1 ", "1e3", "+1", "-1", "NaN", "Infinity"]
)
def test_malformed_amounts_are_not_coerced(key: str, value: object) -> None:
    output = _output() | {key: value}
    transport = _Transport([_response(output)])
    with pytest.raises(
        readonly.KisPaperReadOnlyError, match="^orderable_funds_response_incomplete$"
    ):
        _client(transport).orderable_funds_at_limit(
            symbol="QQQ", exchange="NASD", limit_price=Decimal("500")
        )
    assert len(transport.requests) == 1


@pytest.mark.parametrize("currency", ["KRW", "usd", " USD", None, True])
def test_foreign_or_malformed_currency_is_not_a_qqq_usd_fact(currency: object) -> None:
    transport = _Transport([_response(_output() | {"tr_crcy_cd": currency})])
    with pytest.raises(
        readonly.KisPaperReadOnlyError, match="^orderable_funds_response_incomplete$"
    ):
        _client(transport).orderable_funds_at_limit(
            symbol="QQQ", exchange="NASD", limit_price=Decimal("500")
        )


@pytest.mark.parametrize("output", [[], {}, "raw-untrusted-output", [_output(), _output()]])
def test_missing_or_duplicate_response_rows_fail_closed(output: object) -> None:
    transport = _Transport([_response(output)])
    with pytest.raises(readonly.KisPaperReadOnlyError, match="^orderable_funds_response_"):
        _client(transport).orderable_funds_at_limit(
            symbol="QQQ", exchange="NASD", limit_price=Decimal("500")
        )
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        b'{"rt_cd":"1","rt_cd":"0","output":{}}',
        b'{"rt_cd":"0","output":{},"output":{}}',
        b'{"rt_cd":"0","output":{"ovrs_ord_psbl_amt":"0","ovrs_ord_psbl_amt":"999"}}',
        b'{"rt_cd":"0","output":{"tr_crcy_cd":"KRW","tr_crcy_cd":"USD"}}',
        b"not-json",
        b"[]",
        b"\xff",
    ],
)
def test_duplicate_json_keys_and_malformed_bodies_cannot_override_facts(body: bytes) -> None:
    transport = _Transport([readonly.KisHttpResponse(200, {}, body)])
    with pytest.raises(readonly.KisPaperReadOnlyError, match="^response_invalid$"):
        _client(transport).orderable_funds_at_limit(
            symbol="QQQ", exchange="NASD", limit_price=Decimal("500")
        )
    assert len(transport.requests) == 1


@pytest.mark.parametrize("continuation", ["M", "F", "unexpected"])
def test_incomplete_or_unknown_pagination_is_not_retried(continuation: str) -> None:
    transport = _Transport([_response(headers={"tr_cont": continuation})])
    with pytest.raises(readonly.KisPaperReadOnlyError, match="^orderable_funds_"):
        _client(transport).orderable_funds_at_limit(
            symbol="QQQ", exchange="NASD", limit_price=Decimal("500")
        )
    assert len(transport.requests) == 1


@pytest.mark.parametrize(("status", "rt_cd"), [(403, "0"), (503, "1"), (200, "1"), (200, 0)])
def test_provider_errors_do_not_return_success_or_raw_messages(status: int, rt_cd: object) -> None:
    transport = _Transport(
        [
            readonly.KisHttpResponse.from_payload(
                {
                    "rt_cd": rt_cd,
                    "msg_cd": "KIS1001",
                    "msg1": "raw-secret-message",
                    "output": _output(),
                },
                status_code=status,
            )
        ]
    )
    with pytest.raises(
        readonly.KisPaperReadOnlyError, match="^orderable_funds_rejected$"
    ) as raised:
        _client(transport).orderable_funds_at_limit(
            symbol="QQQ", exchange="NASD", limit_price=Decimal("500")
        )
    assert raised.value.diagnostic == {
        "endpoint": "orderable_funds",
        "tr_id": "VTTS3007R",
        "http_status": str(status),
        "upstream_code": "KIS1001",
    }
    assert "raw-secret-message" not in str(raised.value) + repr(raised.value.diagnostic)
    assert len(transport.requests) == 1


def test_zero_buying_power_is_an_observation_not_a_submission_permission() -> None:
    transport = _Transport(
        [
            _response(
                _output()
                | {
                    "ord_psbl_frcr_amt": "0.00",
                    "ovrs_ord_psbl_amt": "0",
                }
            )
        ]
    )
    cash, funds = _client(transport).orderable_funds_at_limit(
        symbol="QQQ", exchange="NASD", limit_price=Decimal("500")
    )
    assert cash.available_cash == funds.orderable_funds == 0
    assert not hasattr(funds, "safe_to_submit")


def test_reuses_one_in_memory_token_without_any_broker_post() -> None:
    transport = _Transport([_response(), _response()])
    client = _client(transport, token=None)
    for price in (Decimal("500.01"), Decimal("500.02")):
        client.orderable_funds_at_limit(symbol="QQQ", exchange="NASD", limit_price=price)
    assert [request.method for request in transport.requests] == ["POST", "GET", "GET"]
    assert transport.requests[0].url.endswith(readonly.KIS_PAPER_TOKEN_PATH)


def test_transport_failure_has_no_retry_or_fallback_reference() -> None:
    transport = _Transport([readonly.KisPaperReadOnlyError("transport_failure")])
    with pytest.raises(readonly.KisPaperReadOnlyError, match="^transport_failure$"):
        _client(transport).orderable_funds_at_limit(
            symbol="QQQ", exchange="NASD", limit_price=Decimal("500")
        )
    assert len(transport.requests) == 1


def test_full_snapshot_retains_original_spy_reference_and_endpoint_allowlist() -> None:
    class SnapshotTransport:
        def __init__(self) -> None:
            self.requests: list[readonly.KisHttpRequest] = []

        def request(self, request: readonly.KisHttpRequest) -> readonly.KisHttpResponse:
            self.requests.append(request)
            if request.headers["tr_id"] == readonly.KIS_PAPER_BALANCE_ENDPOINT.tr_id:
                return readonly.KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
            if request.headers["tr_id"] == readonly.KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
                return readonly.KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
            return _response()

    transport = SnapshotTransport()
    snapshot = _client(transport).snapshot()
    assert transport.requests[-1].query["ITEM_CD"] == "SPY"
    assert transport.requests[-1].query["OVRS_EXCG_CD"] == "NASD"
    assert transport.requests[-1].query["OVRS_ORD_UNPR"] == "1"
    assert snapshot.orderable_funds.reference_symbol == "SPY"
    assert snapshot.orderable_funds.reference_price == Decimal("1")
    assert readonly.KIS_PAPER_READ_ONLY_ENDPOINTS == (
        readonly.KIS_PAPER_BALANCE_ENDPOINT,
        readonly.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
        readonly.KIS_PAPER_OPEN_ORDERS_ENDPOINT,
        readonly.KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
    )
