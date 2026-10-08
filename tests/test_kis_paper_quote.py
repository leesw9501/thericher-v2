from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution.emergency import PaperExecutionControlStore
from thericher_v2.execution.kis_paper_canary import (
    KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID,
    KIS_PAPER_US_CANCEL_TR_ID,
    KIS_PAPER_US_CCNCL_TR_ID,
    KisPaperCanaryError,
    validate_kis_paper_canary_request,
)
from thericher_v2.execution.kis_paper_quote import (
    KIS_PAPER_US_QQQ_ASKING_PRICE_EXCHANGE,
    KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
    KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
    KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
    KIS_PAPER_US_SPY_QUOTE_TR_ID,
    KisPaperQqqLimitInput,
    KisPaperQuoteError,
    build_kis_paper_qqq_asking_price_request,
    build_kis_paper_qqq_price_detail_request,
    build_kis_paper_qqq_quote_request,
    build_kis_paper_spy_asking_price_request,
    build_kis_paper_spy_price_detail_request,
    build_kis_paper_spy_quote_request,
    derive_kis_paper_nonmarket_limit,
    inspect_kis_paper_spy_asking_price_response,
    inspect_kis_paper_spy_price_detail_response,
    parse_kis_paper_qqq_limit_input,
    parse_kis_paper_qqq_quote,
    parse_kis_paper_spy_limit_input,
    parse_kis_paper_spy_quote,
    validate_kis_paper_qqq_asking_price_request,
    validate_kis_paper_qqq_price_detail_request,
    validate_kis_paper_qqq_quote_request,
    validate_kis_paper_spy_asking_price_request,
    validate_kis_paper_spy_price_detail_request,
    validate_kis_paper_spy_quote_request,
)
from thericher_v2.execution.kis_paper_session import (
    is_us_equity_regular_session_window,
    run_kis_paper_quote_session,
)
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_BASE_URL,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperConfig,
)
from thericher_v2.execution.paper_canary_lifecycle import (
    read_paper_canary_session_fact_from_artifact_root,
)
from thericher_v2.execution.paper_canary_runtime import read_paper_canary_runtime


@pytest.mark.parametrize("symbol,venue", [("SPY", "AMS"), ("TLT", "NAS"), ("GLD", "AMS")])
@pytest.mark.parametrize("kind", ["price_detail", "asking_price"])
def test_preview_quote_fixed_readonly_routes(symbol, venue, kind):
    from thericher_v2.execution.kis_paper_quote import (
        build_kis_paper_preview_quote_request,
        validate_kis_paper_preview_quote_request,
    )
    from thericher_v2.execution.kis_readonly import validate_kis_paper_readonly_request

    request = build_kis_paper_preview_quote_request(
        config=_config(), access_token="synthetic-token", symbol=symbol, kind=kind,
    )
    assert request.method == "GET" and request.json_body is None
    assert request.query == {"AUTH": "", "EXCD": venue, "SYMB": symbol}
    validate_kis_paper_preview_quote_request(request)
    validate_kis_paper_readonly_request(request)
    for change in (
        {"method": "POST"},
        {"url": request.url.replace("openapivts", "openapi")},
        {"query": {**request.query, "SYMB": "QQQ"}},
        {"query": {**request.query, "EXCD": "NYSE"}},
        {"query": {**request.query, "extra": "unknown"}},
        {"headers": {**request.headers, "tr_id": "VTTT1002U"}},
    ):
        with pytest.raises(KisPaperQuoteError):
            validate_kis_paper_preview_quote_request(replace(request, **change))


@pytest.mark.parametrize("symbol", ["QQQ", "tlt", " TLT", "IWM", None, True])
def test_preview_quote_cannot_become_a_generic_symbol_route(symbol):
    from thericher_v2.execution.kis_paper_quote import build_kis_paper_preview_quote_request

    with pytest.raises(KisPaperQuoteError, match="preview_symbol_invalid"):
        build_kis_paper_preview_quote_request(
            config=_config(), access_token="synthetic-token", symbol=symbol, kind="asking_price",
        )
NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


@dataclass
class FakeKisPaperQuoteTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)
    quote_status_code: int = 200
    quote_payload: dict[str, object] = field(
        default_factory=lambda: {"rt_cd": "0", "output": {"last": "600.12", "zdiv": "2"}}
    )
    price_detail_status_code: int = 200
    price_detail_payload: dict[str, object] = field(
        default_factory=lambda: {
            "rt_cd": "0",
            "output": {"last": "600.12", "zdiv": "2", "e_hogau": "0.01"},
        }
    )
    asking_price_status_code: int = 200
    asking_price_payload: dict[str, object] = field(
        default_factory=lambda: {
            "rt_cd": "0",
            "output1": {
                "last": "600.12",
                "zdiv": "2",
                "pbid1": "600.11",
                "pask1": "600.13",
                "dymd": "20260722",
                "dhms": "233000",
            },
        }
    )
    matching_open_order: bool = False
    submit_response_missing_order_id: bool = False
    matching_ccnl_after_cancel: bool = False
    fail_cancel: bool = False
    cancellation_seen: bool = False

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        tr_id = request.headers.get("tr_id", "")
        if request.method == "POST" and request.url.endswith("/oauth2/tokenP"):
            return KisHttpResponse.from_payload({"access_token": "test-access-token"})
        if tr_id == KIS_PAPER_US_SPY_QUOTE_TR_ID:
            return KisHttpResponse.from_payload(
                self.quote_payload,
                status_code=self.quote_status_code,
            )
        if tr_id == KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID:
            return KisHttpResponse.from_payload(
                self.price_detail_payload,
                status_code=self.price_detail_status_code,
            )
        if tr_id == KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID:
            return KisHttpResponse.from_payload(
                self.asking_price_payload,
                status_code=self.asking_price_status_code,
            )
        if tr_id == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
            if self.matching_open_order and request.query["OVRS_EXCG_CD"] == "NASD":
                return KisHttpResponse.from_payload(
                    {"rt_cd": "0", "output": [_matching_spy_open_order_payload()]}
                )
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
        if tr_id == KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "tr_crcy_cd": "USD",
                        "ord_psbl_frcr_amt": "1200.50",
                        "ovrs_ord_psbl_amt": "1199.75",
                    },
                }
            )
        if tr_id == KIS_PAPER_US_CCNCL_TR_ID:
            if self.matching_ccnl_after_cancel and self.cancellation_seen:
                return KisHttpResponse.from_payload(
                    {"rt_cd": "0", "output": [{"odno": "ORD-123456789"}]}
                )
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID:
            if self.submit_response_missing_order_id:
                return KisHttpResponse.from_payload({"rt_cd": "0", "output": {}})
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": {"ODNO": "ORD-123456789"}})
        if tr_id == KIS_PAPER_US_CANCEL_TR_ID:
            self.cancellation_seen = True
            if self.fail_cancel:
                raise KisPaperCanaryError("cancel_transport_failure")
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": {}})
        raise AssertionError(f"unexpected KIS request: {request!r}")


def test_quote_request_is_virtual_only_and_limit_rounds_down() -> None:
    request = build_kis_paper_spy_quote_request(config=_config(), access_token="test-access-token")

    validate_kis_paper_spy_quote_request(request)
    validate_kis_paper_canary_request(request)
    quote = parse_kis_paper_spy_quote(
        {"rt_cd": "0", "output": {"last": "600.12", "zdiv": "2"}}
    )

    assert derive_kis_paper_nonmarket_limit(quote) == Decimal("598.61")
    assert "600.12" not in repr(quote)
    with pytest.raises(KisPaperQuoteError, match="quote_request_not_allowlisted"):
        validate_kis_paper_spy_quote_request(
            replace(request, query={**request.query, "EXCD": "NYS"})
        )
    with pytest.raises(KisPaperCanaryError, match="quote_request_not_allowlisted"):
        validate_kis_paper_canary_request(replace(request, query={**request.query, "EXCD": "NYS"}))


def test_price_detail_probe_request_is_an_exact_paper_only_tuple() -> None:
    request = build_kis_paper_spy_price_detail_request(
        config=_config(),
        access_token="test-access-token",
    )

    validate_kis_paper_spy_price_detail_request(request)
    validate_kis_paper_canary_request(request)
    with pytest.raises(KisPaperQuoteError, match="price_detail_request_not_allowlisted"):
        validate_kis_paper_spy_price_detail_request(
            replace(request, query={**request.query, "EXCD": "NAS"})
        )
    with pytest.raises(KisPaperQuoteError, match="price_detail_request_not_allowlisted"):
        validate_kis_paper_spy_price_detail_request(
            replace(request, query={**request.query, "SYMB": "QQQ"})
        )
    with pytest.raises(KisPaperCanaryError, match="price_detail_request_not_allowlisted"):
        validate_kis_paper_canary_request(
            replace(request, headers={**request.headers, "tr_id": KIS_PAPER_US_SPY_QUOTE_TR_ID})
        )


def test_asking_price_probe_request_is_an_exact_paper_only_tuple() -> None:
    request = build_kis_paper_spy_asking_price_request(
        config=_config(),
        access_token="test-access-token",
    )

    validate_kis_paper_spy_asking_price_request(request)
    validate_kis_paper_canary_request(request)
    with pytest.raises(KisPaperQuoteError, match="asking_price_request_not_allowlisted"):
        validate_kis_paper_spy_asking_price_request(
            replace(request, query={**request.query, "EXCD": "NAS"})
        )
    with pytest.raises(KisPaperCanaryError, match="asking_price_request_not_allowlisted"):
        validate_kis_paper_canary_request(
            replace(
                request,
                headers={**request.headers, "tr_id": KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID},
            )
        )


def test_qqq_price_routes_are_fixed_nas_tuples_on_the_virtual_host() -> None:
    routes = (
        (
            build_kis_paper_qqq_quote_request,
            validate_kis_paper_qqq_quote_request,
        ),
        (
            build_kis_paper_qqq_price_detail_request,
            validate_kis_paper_qqq_price_detail_request,
        ),
        (
            build_kis_paper_qqq_asking_price_request,
            validate_kis_paper_qqq_asking_price_request,
        ),
    )

    for builder, validator in routes:
        request = builder(config=_config(), access_token="test-access-token")

        validator(request)
        validate_kis_paper_canary_request(request)
        assert request.url.startswith(KIS_PAPER_BASE_URL)
        assert request.query == {
            "AUTH": "",
            "EXCD": KIS_PAPER_US_QQQ_ASKING_PRICE_EXCHANGE,
            "SYMB": KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
        }
        with pytest.raises(KisPaperCanaryError, match="request_not_allowlisted"):
            validate_kis_paper_canary_request(
                replace(request, query={**request.query, "SYMB": "AAPL"})
            )
        with pytest.raises(KisPaperCanaryError, match="paper_host_required"):
            validate_kis_paper_canary_request(
                replace(
                    request,
                    url=request.url.replace(
                        KIS_PAPER_BASE_URL,
                        "https://openapi.koreainvestment.com:9443",
                    ),
                )
            )


def test_qqq_limit_input_and_probes_keep_provider_prices_transient() -> None:
    raw_price_text = "500.25"
    transport = FakeKisPaperQuoteTransport(
        quote_payload={"rt_cd": "0", "output": {"last": raw_price_text, "zdiv": "2"}},
        price_detail_payload={
            "rt_cd": "0",
            "output": {"last": raw_price_text, "zdiv": "2", "e_hogau": "0.01"},
        },
        asking_price_payload={
            "rt_cd": "0",
            "output1": {
                "last": raw_price_text,
                "zdiv": "2",
                "pbid1": "500.24",
                "pask1": "500.26",
                "dymd": "20260722",
                "dhms": "233000",
            },
        },
    )

    from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient

    client = KisPaperCanaryClient(config=_config(), transport=transport)
    quote = client.fetch_qqq_quote()
    detail_probe = client.probe_qqq_price_detail()
    asking_probe = client.probe_qqq_asking_price(observed_at=NOW)
    limit_input = client.fetch_qqq_limit_input(observed_at=NOW)
    parsed_quote = parse_kis_paper_qqq_quote(transport.quote_payload)
    parsed_limit_input = parse_kis_paper_qqq_limit_input(
        asking_price_payload=transport.asking_price_payload,
        price_detail_payload=transport.price_detail_payload,
        observed_at=NOW,
    )

    assert isinstance(limit_input, KisPaperQqqLimitInput)
    assert quote.last == Decimal(raw_price_text)
    assert parsed_quote == quote
    assert parsed_limit_input == limit_input
    assert detail_probe.safe_payload()["tick_state"] == "positive_decimal"
    assert asking_probe.safe_payload()["bid_ask_state"] == "non_crossed"
    assert raw_price_text not in repr(quote)
    assert raw_price_text not in repr(limit_input)
    assert raw_price_text not in str(detail_probe.safe_payload())
    assert raw_price_text not in str(asking_probe.safe_payload())
    qqq_requests = [
        request
        for request in transport.requests
        if request.query.get("SYMB") == KIS_PAPER_US_QQQ_QUOTE_SYMBOL
    ]
    assert len(qqq_requests) == 5
    assert all(
        request.query == {"AUTH": "", "EXCD": "NAS", "SYMB": "QQQ"}
        and request.url.startswith(KIS_PAPER_BASE_URL)
        for request in qqq_requests
    )


def test_spy_price_tuple_remains_unchanged_after_qqq_sibling_route() -> None:
    request = build_kis_paper_spy_asking_price_request(
        config=_config(),
        access_token="test-access-token",
    )

    validate_kis_paper_spy_asking_price_request(request)
    validate_kis_paper_canary_request(request)
    assert request.query == {"AUTH": "", "EXCD": "AMS", "SYMB": "SPY"}


@pytest.mark.parametrize(
    "payload",
    (
        {"rt_cd": "0"},
        {"rt_cd": "0", "output": {"last": "0", "zdiv": "2"}},
        {"rt_cd": "0", "output": {"last": "600.12", "zdiv": "7"}},
        {"rt_cd": "0", "output": {"last": "600.12", "zdiv": "not-a-scale"}},
    ),
)
def test_quote_parser_rejects_incomplete_or_invalid_values(payload: dict[str, object]) -> None:
    with pytest.raises(KisPaperQuoteError, match="quote_response_incomplete"):
        parse_kis_paper_spy_quote(payload)


def test_quote_parser_classifies_both_blank_required_fields_without_retaining_values() -> None:
    with pytest.raises(KisPaperQuoteError, match="quote_response_blank"):
        parse_kis_paper_spy_quote({"rt_cd": "0", "output": {"last": " ", "zdiv": ""}})


def test_quote_parser_rejects_a_success_http_response_with_kis_error_code() -> None:
    with pytest.raises(KisPaperQuoteError, match="quote_rejected"):
        parse_kis_paper_spy_quote(
            {"rt_cd": "1", "output": {"last": "600.12", "zdiv": "2"}}
        )


def test_price_detail_probe_keeps_price_fields_transient_and_category_only() -> None:
    raw_price_text = "600.12"
    transport = FakeKisPaperQuoteTransport(
        price_detail_payload={
            "rt_cd": "0",
            "output": {"last": raw_price_text, "zdiv": "2", "e_hogau": "0.01"},
        }
    )

    from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient

    probe = KisPaperCanaryClient(config=_config(), transport=transport).probe_spy_price_detail()

    assert probe.safe_payload() == {
        "http_status_class": "2xx",
        "payload_mapping": "mapping",
        "result": "success",
        "last_state": "positive_decimal",
        "decimal_scale_state": "valid_scale",
        "tick_state": "positive_decimal",
        "paper_only": True,
    }
    assert raw_price_text not in repr(probe)
    assert raw_price_text not in str(probe.safe_payload())
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


def test_price_detail_probe_classifies_blank_required_fields_as_unusable() -> None:
    probe = inspect_kis_paper_spy_price_detail_response(
        KisHttpResponse.from_payload(
            {"rt_cd": "0", "output": {"last": "", "zdiv": "", "e_hogau": ""}}
        )
    )

    assert probe.last_state == "blank"
    assert probe.decimal_scale_state == "blank"
    assert probe.tick_state == "blank"


def test_asking_price_probe_keeps_best_price_fields_transient_and_category_only() -> None:
    raw_price_text = "600.12"
    transport = FakeKisPaperQuoteTransport(
        asking_price_payload={
            "rt_cd": "0",
            "output1": {
                "last": raw_price_text,
                "zdiv": "2",
                "pbid1": "600.11",
                "pask1": "600.13",
                "dymd": "20260722",
                "dhms": "233000",
            },
        }
    )

    from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient

    probe = KisPaperCanaryClient(
        config=_config(),
        transport=transport,
    ).probe_spy_asking_price(observed_at=NOW)

    assert probe.safe_payload() == {
        "http_status_class": "2xx",
        "payload_mapping": "mapping",
        "result": "success",
        "last_state": "positive_decimal",
        "decimal_scale_state": "valid_scale",
        "best_bid_state": "positive_decimal",
        "best_ask_state": "positive_decimal",
        "bid_ask_state": "non_crossed",
        "quote_timestamp_state": "valid_date_and_time",
        "quote_timestamp_age_state": "age_within_120s_under_korea_interpretation",
        "paper_only": True,
    }
    assert raw_price_text not in repr(probe)
    assert raw_price_text not in str(probe.safe_payload())
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


def test_asking_price_probe_classifies_blank_fields_as_unusable() -> None:
    probe = inspect_kis_paper_spy_asking_price_response(
        KisHttpResponse.from_payload(
            {
                "rt_cd": "0",
                "output1": {
                    "last": "",
                    "zdiv": "",
                    "pbid1": "",
                    "pask1": "",
                    "dymd": "",
                    "dhms": "",
                },
            }
        )
    )

    assert probe.last_state == "blank"
    assert probe.decimal_scale_state == "blank"
    assert probe.best_bid_state == "blank"
    assert probe.best_ask_state == "blank"
    assert probe.bid_ask_state == "not_checked"
    assert probe.quote_timestamp_state == "blank"


def test_limit_input_requires_fresh_korea_timestamp_scale_and_valid_limit_tick() -> None:
    raw_price_text = "600.12"
    limit_input = parse_kis_paper_spy_limit_input(
        asking_price_payload={
            "rt_cd": "0",
            "output1": {
                "last": raw_price_text,
                "zdiv": "2",
                "dymd": "20260722",
                "dhms": "233000",
            },
        },
        price_detail_payload={
            "rt_cd": "0",
            "output": {"last": raw_price_text, "zdiv": "2", "e_hogau": "0.01"},
        },
        observed_at=NOW,
    )

    assert derive_kis_paper_nonmarket_limit(
        limit_input.as_quote(),
        tick_size=limit_input.tick_size,
    ) == Decimal("598.61")
    assert raw_price_text not in repr(limit_input)
    with pytest.raises(KisPaperQuoteError, match="quote_timestamp_stale"):
        parse_kis_paper_spy_limit_input(
            asking_price_payload={
                "rt_cd": "0",
                "output1": {
                    "last": raw_price_text,
                    "zdiv": "2",
                    "dymd": "20260722",
                    "dhms": "230000",
                },
            },
            price_detail_payload={
                "rt_cd": "0",
                "output": {"last": raw_price_text, "zdiv": "2", "e_hogau": "0.01"},
            },
            observed_at=NOW,
        )
    sub_tick_last_input = parse_kis_paper_spy_limit_input(
        asking_price_payload={
            "rt_cd": "0",
            "output1": {
                "last": "600.121",
                "zdiv": "3",
                "dymd": "20260722",
                "dhms": "233000",
            },
        },
        price_detail_payload={
            "rt_cd": "0",
            "output": {"last": raw_price_text, "zdiv": "3", "e_hogau": "0.01"},
        },
        observed_at=NOW,
    )
    assert derive_kis_paper_nonmarket_limit(
        sub_tick_last_input.as_quote(),
        tick_size=sub_tick_last_input.tick_size,
    ) == Decimal("598.62")


def test_session_outside_regular_window_never_reads_credentials_or_dispatches(
    tmp_path: Path,
) -> None:
    class UnusedEnvironment(dict[str, str]):
        def get(self, key: str, default: str = "") -> str:
            raise AssertionError(f"outside-session runner must not read environment: {key}")

    transport = FakeKisPaperQuoteTransport()
    outcome = run_kis_paper_quote_session(
        environment=UnusedEnvironment(),
        transport=transport,
        now=NOW.replace(hour=1),
        session_id="outside-session-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "not_due"
    assert outcome.reason_code == "outside_regular_session"
    assert transport.requests == []
    assert outcome.evidence_path.exists()


def test_buy_pause_prevents_a_due_session_before_credentials_or_network(tmp_path: Path) -> None:
    class UnusedEnvironment(dict[str, str]):
        def get(self, key: str, default: str = "") -> str:
            raise AssertionError(f"paused session must not read environment: {key}")

    control_path = tmp_path / "emergency" / "paper_execution_control.json"
    PaperExecutionControlStore(control_path).set_pause_buys(True)
    transport = FakeKisPaperQuoteTransport()

    outcome = run_kis_paper_quote_session(
        environment=UnusedEnvironment(),
        transport=transport,
        now=NOW,
        session_id="buy-paused-1",
        execute=True,
        cancel_after_submit=True,
        execution_control_path=control_path,
        **_paths(tmp_path),
    )

    assert outcome.status == "paused"
    assert outcome.reason_code == "pause_buys_active"
    assert transport.requests == []
    assert "paper-app-secret" not in outcome.evidence_path.read_text(encoding="utf-8")
    runtime = read_paper_canary_runtime(_paths(tmp_path)["runtime_projection_path"], now=NOW)
    assert runtime.status == "available"
    assert runtime.snapshot is not None
    assert runtime.snapshot.run_id == "buy-paused-1"
    assert runtime.snapshot.status == "unavailable"
    assert runtime.snapshot.reconciliation_status == "not_run"
    assert runtime.snapshot.account_status == "unknown"
    session_fact = read_paper_canary_session_fact_from_artifact_root(
        _paths(tmp_path)["artifact_root"],
        "buy-paused-1",
    )
    assert session_fact.result_class == "no_new_intent"
    assert session_fact.reason_code == "pause_buys_active"


@pytest.mark.parametrize("session_id", [".", ".."])
def test_quote_session_rejects_dot_path_ids_before_writing(
    tmp_path: Path,
    session_id: str,
) -> None:
    paths = _paths(tmp_path)

    with pytest.raises(ValueError, match="session_id is invalid"):
        run_kis_paper_quote_session(
            environment={},
            transport=FakeKisPaperQuoteTransport(),
            now=NOW,
            session_id=session_id,
            execute=False,
            cancel_after_submit=True,
            **paths,
        )

    assert not paths["artifact_root"].exists()


@pytest.mark.parametrize(
    ("observed_at", "expected"),
    (
        (datetime(2026, 7, 22, 13, 29, 59, tzinfo=UTC), False),
        (datetime(2026, 7, 22, 13, 30, tzinfo=UTC), True),
        (datetime(2026, 7, 22, 19, 59, 59, tzinfo=UTC), True),
        (datetime(2026, 7, 22, 20, 0, tzinfo=UTC), False),
        (datetime(2026, 11, 27, 17, 59, 59, tzinfo=UTC), True),
        (datetime(2026, 11, 27, 18, 0, tzinfo=UTC), False),
    ),
)
def test_session_eligibility_uses_explicit_2026_exchange_windows(
    observed_at: datetime,
    expected: bool,
) -> None:
    assert is_us_equity_regular_session_window(observed_at) is expected


@pytest.mark.parametrize(
    ("observed_at", "session_id"),
    (
        (datetime(2026, 7, 3, 14, 30, tzinfo=UTC), "holiday-session-1"),
        (datetime(2027, 1, 4, 14, 30, tzinfo=UTC), "out-of-scope-session-1"),
    ),
)
def test_closed_or_out_of_scope_session_never_reads_credentials_or_dispatches(
    tmp_path: Path,
    observed_at: datetime,
    session_id: str,
) -> None:
    class UnusedEnvironment(dict[str, str]):
        def get(self, key: str, default: str = "") -> str:
            raise AssertionError(f"unavailable-session runner must not read environment: {key}")

    transport = FakeKisPaperQuoteTransport()
    outcome = run_kis_paper_quote_session(
        environment=UnusedEnvironment(),
        transport=transport,
        now=observed_at,
        session_id=session_id,
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "not_due"
    assert outcome.reason_code == "session_unavailable"
    assert transport.requests == []


def test_due_session_uses_transient_quote_and_sanitizes_all_public_outputs(tmp_path: Path) -> None:
    raw_quote_text = "600.12"
    derived_limit_text = "598.61"
    transport = FakeKisPaperQuoteTransport()
    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="due-session-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.run_id == "canary-due-session-1"
    assert outcome.canary_phase == "cancelled"
    buy_request = next(
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
    )
    assert buy_request.json_body is not None
    assert buy_request.json_body["OVRS_ORD_UNPR"] == derived_limit_text
    assert buy_request.json_body["OVRS_EXCG_CD"] == "AMEX"
    asking_price_request = next(
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID
    )
    assert asking_price_request.query == {"AUTH": "", "EXCD": "AMS", "SYMB": "SPY"}
    price_detail_request = next(
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID
    )
    assert price_detail_request.query == {"AUTH": "", "EXCD": "AMS", "SYMB": "SPY"}
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    safe_output = str(outcome.safe_payload())
    for forbidden in (raw_quote_text, derived_limit_text, "paper-app-secret", "12345678"):
        assert forbidden not in evidence
        assert forbidden not in safe_output


def test_repeated_due_sessions_create_distinct_intents_without_a_one_shot_latch(
    tmp_path: Path,
) -> None:
    transport = FakeKisPaperQuoteTransport()
    first = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="due-session-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )
    transport.asking_price_payload = {
        "rt_cd": "0",
        "output1": {
            "last": "600.12",
            "zdiv": "2",
            "pbid1": "600.11",
            "pask1": "600.13",
            "dymd": "20260722",
            "dhms": "234500",
        },
    }
    second = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW + timedelta(minutes=15),
        session_id="due-session-2",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert first.run_id != second.run_id
    assert first.status == second.status == "canary_completed"
    assert sum(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    ) == 2


def test_same_session_reuses_its_exact_unknown_state_without_a_second_submission(
    tmp_path: Path,
) -> None:
    transport = FakeKisPaperQuoteTransport(submit_response_missing_order_id=True)
    first = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="prior-unknown-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )
    assert first.canary_phase == "outcome_unknown"
    assert sum(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    ) == 1
    transport.asking_price_payload = _fresh_asking_price_payload()
    second = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW + timedelta(minutes=15),
        session_id="prior-unknown-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert second.status == "canary_completed"
    assert second.run_id == first.run_id
    assert second.canary_phase == "outcome_unknown"
    assert sum(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    ) == 1
def test_distinct_session_can_submit_without_mutating_an_old_unknown_state(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    transport = FakeKisPaperQuoteTransport(submit_response_missing_order_id=True)
    first = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="prior-unknown-1",
        execute=True,
        cancel_after_submit=True,
        **paths,
    )

    assert first.canary_phase == "outcome_unknown"
    prior_state = paths["state_root"] / f"{first.run_id}.json"
    before = prior_state.read_bytes()
    transport.submit_response_missing_order_id = False
    transport.asking_price_payload = _fresh_asking_price_payload()

    second = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW + timedelta(minutes=15),
        session_id="fresh-after-prior-unknown-2",
        execute=True,
        cancel_after_submit=True,
        **paths,
    )

    assert second.status == "canary_completed"
    assert second.run_id != first.run_id
    assert second.canary_phase == "cancelled"
    assert sum(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    ) == 2
    assert prior_state.read_bytes() == before


def test_distinct_session_rejects_a_current_matching_open_order_without_submitting(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    transport = FakeKisPaperQuoteTransport(submit_response_missing_order_id=True)
    first = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="prior-unknown-with-open-order-1",
        execute=True,
        cancel_after_submit=True,
        **paths,
    )
    assert first.canary_phase == "outcome_unknown"
    transport.submit_response_missing_order_id = False
    transport.matching_open_order = True
    transport.asking_price_payload = _fresh_asking_price_payload()

    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW + timedelta(minutes=15),
        session_id="current-open-order-after-prior-2",
        execute=True,
        cancel_after_submit=True,
        **paths,
    )

    assert outcome.status == "canary_completed"
    assert outcome.run_id != first.run_id
    assert outcome.reason_code == "matching_open_order"
    assert outcome.canary_phase == "intent_recorded"
    state = json.loads((paths["state_root"] / f"{outcome.run_id}.json").read_text())
    assert state["submission_started_at"] is None
    assert state["submitted_at"] is None
    assert state["broker_order_id"] is None
    assert sum(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    ) == 1


def test_malformed_unrelated_state_is_source_safe_and_does_not_block_a_fresh_session(
    tmp_path: Path,
) -> None:
    raw_state_text = "paper-app-secret account 12345678 broker detail"
    state_root = _paths(tmp_path)["state_root"]
    state_root.mkdir(parents=True)
    (state_root / "canary-corrupt-state.json").write_text(
        '{"unexpected":"' + raw_state_text + '"}',
        encoding="utf-8",
    )
    transport = FakeKisPaperQuoteTransport()

    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="corrupt-prior-state-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.canary_phase == "cancelled"
    assert any(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    safe_output = str(outcome.safe_payload())
    for forbidden in (raw_state_text, "paper-app-secret", "12345678"):
        assert forbidden not in evidence
        assert forbidden not in safe_output


def test_quote_failure_writes_safe_no_submit_evidence(tmp_path: Path) -> None:
    raw_broker_text = "paper-app-secret account 12345678 broker detail"
    transport = FakeKisPaperQuoteTransport(
        asking_price_status_code=503,
        asking_price_payload={"msg1": raw_broker_text},
    )
    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="quote-failure-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "quote_unavailable"
    assert outcome.reason_code == "quote_rejected"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert raw_broker_text not in evidence
    assert "paper-app-secret" not in evidence
    assert "12345678" not in evidence
    runtime = read_paper_canary_runtime(_paths(tmp_path)["runtime_projection_path"], now=NOW)
    assert runtime.status == "available"
    assert runtime.snapshot is not None
    assert runtime.snapshot.run_id == "quote-failure-1"
    assert runtime.snapshot.status == "unavailable"
    assert runtime.snapshot.reconciliation_status == "not_run"


def test_kis_quote_error_code_writes_safe_no_submit_evidence(tmp_path: Path) -> None:
    transport = FakeKisPaperQuoteTransport(
        asking_price_payload={"rt_cd": "1", "output1": {"last": "600.12", "zdiv": "2"}}
    )
    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="quote-result-error-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "quote_unavailable"
    assert outcome.reason_code == "quote_rejected"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


def test_blank_kis_quote_fields_write_safe_no_submit_evidence(tmp_path: Path) -> None:
    transport = FakeKisPaperQuoteTransport(
        asking_price_payload={
            "rt_cd": "0",
            "output1": {"last": "", "zdiv": " ", "dymd": "", "dhms": ""},
        }
    )
    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="quote-blank-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "quote_unavailable"
    assert outcome.reason_code == "quote_response_blank"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert '"quote_response_blank"' in evidence
    assert '"last"' not in evidence
    assert '"zdiv"' not in evidence


@dataclass
class SteppingClock:
    values: list[datetime]

    def __call__(self) -> datetime:
        if not self.values:
            raise AssertionError("clock ran more often than expected")
        return self.values.pop(0)


def test_session_rechecks_the_regular_window_immediately_before_submit(tmp_path: Path) -> None:
    before_close = datetime(2026, 7, 22, 19, 59, 59, tzinfo=UTC)
    clock = SteppingClock(
        [
            before_close,
            before_close,
            before_close,
            before_close + timedelta(seconds=1),
        ]
    )
    transport = FakeKisPaperQuoteTransport(
        asking_price_payload={
            "rt_cd": "0",
            "output1": {
                "last": "600.12",
                "zdiv": "2",
                "pbid1": "600.11",
                "pask1": "600.13",
                "dymd": "20260723",
                "dhms": "045959",
            },
        }
    )

    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        clock=clock,
        session_id="session-close-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.reason_code == "session_closed"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


def test_session_rechecks_limit_validity_immediately_before_submit(tmp_path: Path) -> None:
    clock = SteppingClock([NOW, NOW, NOW, NOW + timedelta(seconds=2)])
    transport = FakeKisPaperQuoteTransport()

    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        clock=clock,
        session_id="session-expiry-1",
        execute=True,
        cancel_after_submit=True,
        valid_seconds=1,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.reason_code == "intent_expired"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


def test_session_uses_the_kis_quote_timestamp_for_submit_freshness(tmp_path: Path) -> None:
    clock = SteppingClock([NOW, NOW, NOW + timedelta(seconds=121)])
    transport = FakeKisPaperQuoteTransport()

    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        clock=clock,
        session_id="quote-age-submit-1",
        execute=True,
        cancel_after_submit=True,
        valid_seconds=300,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.reason_code == "intent_expired"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


def _config() -> KisPaperConfig:
    return KisPaperConfig(
        app_key="paper-app-key",
        app_secret="paper-app-secret",
        account_number="12345678",
        account_product_code="01",
    )


def _paper_environment() -> dict[str, str]:
    return {
        "KIS_PAPER_APP_KEY": "paper-app-key",
        "KIS_PAPER_APP_SECRET": "paper-app-secret",
        "KIS_PAPER_ACCOUNT_NO": "12345678",
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
        "KIS_LIVE_APP_KEY": "must-not-be-read",
    }


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "state_root": tmp_path / "private" / "canary",
        "runtime_projection_path": tmp_path / "runtime" / "canary.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": tmp_path / "repo",
    }


def _matching_spy_open_order_payload() -> dict[str, str]:
    return {
        "odno": "ORD-123456789",
        "pdno": "SPY",
        "ovrs_excg_cd": "AMEX",
        "tr_crcy_cd": "USD",
        "sll_buy_dvsn_cd": "02",
        "ft_ord_qty": "1",
        "ft_ccld_qty": "0",
        "nccs_qty": "1",
        "ft_ord_unpr3": "500.25",
    }


def _fresh_asking_price_payload() -> dict[str, object]:
    return {
        "rt_cd": "0",
        "output1": {
            "last": "600.12",
            "zdiv": "2",
            "pbid1": "600.11",
            "pask1": "600.13",
            "dymd": "20260722",
            "dhms": "234500",
        },
    }
