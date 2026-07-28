from __future__ import annotations

import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution import kis_market_data
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_DAILY_TR_ID,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MARKET_DATA_MAX_DAILY_PAGE_ATTEMPTS,
    KIS_PAPER_MARKET_DATA_MAX_MINUTE_PAGE_ATTEMPTS,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_MINUTE_TR_ID,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperDailyQuery,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    KisPaperMinuteClient,
    KisPaperMinuteQuery,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import KisPaperMarketDataTokenStartGate


class _RecordingTransport:
    def __init__(self, responses: list[KisMarketDataResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[KisMarketDataRequest] = []

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def test_minute_client_parses_kis_shaped_page_and_explicit_continuation() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            _page("195900", "180000", next_value="0", continuation="M"),
            _page("175900", "160000", next_value="1", continuation=""),
        ]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    first = client.fetch_page(
        KisPaperMinuteQuery(exchange="NAS", symbol="QQQ", include_previous_day=True)
    )
    second = client.fetch_page(
        KisPaperMinuteQuery(
            exchange="NAS",
            symbol="QQQ",
            continuation_next=first.next_cursor,
            continuation_key="20260717175900",
        )
    )

    assert first.next_cursor == "1"
    assert second.next_cursor is None
    assert transport.requests[1].query["PINC"] == "1"
    assert transport.requests[1].query["NEXT"] == ""
    assert first.more == "0"
    assert first.bars[0].exchange_time == "195900"
    assert first.bars[-1].exchange_time == "180000"
    assert first.bars[0].korea_time == "070000"
    assert first.bars[0].volume == Decimal("1000")
    assert first.bars[0].as_document() == {
        "evol": "1000",
        "high": "102",
        "kymd": "20260718",
        "khms": "070000",
        "last": "101",
        "low": "99",
        "open": "100",
        "xhms": "195900",
        "xymd": "20260717",
    }
    assert second.bars[0].exchange_time == "175900"

    assert [request.method for request in transport.requests] == ["POST", "GET", "GET"]
    request_paths = [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL)
        for request in transport.requests
    ]
    assert request_paths == [
        KIS_PAPER_TOKEN_PATH,
        KIS_PAPER_MINUTE_PATH,
        KIS_PAPER_MINUTE_PATH,
    ]
    assert transport.requests[0].headers == {
        "content-type": "application/json",
        "accept": "application/json",
    }
    assert transport.requests[1].headers == {
        "authorization": "Bearer test-token",
        "appkey": "paper-key",
        "appsecret": "paper-secret",
        "tr_id": KIS_PAPER_MINUTE_TR_ID,
        "tr_cont": "",
        "custtype": "P",
        "accept": "application/json",
    }
    assert transport.requests[1].query == {
        "AUTH": "",
            "EXCD": "NAS",
            "SYMB": "QQQ",
            "NMIN": "1",
            "PINC": "1",
            "NREC": "120",
        "FILL": "",
        "KEYB": "",
        "NEXT": "",
    }
    assert transport.requests[2].headers == {
        "authorization": "Bearer test-token",
        "appkey": "paper-key",
        "appsecret": "paper-secret",
        "tr_id": KIS_PAPER_MINUTE_TR_ID,
        "tr_cont": "N",
        "custtype": "P",
        "accept": "application/json",
    }
    assert transport.requests[2].query == {
        "AUTH": "",
        "EXCD": "NAS",
        "SYMB": "QQQ",
        "NMIN": "1",
        "PINC": "1",
        "NREC": "120",
        "FILL": "",
        "KEYB": "20260717175900",
        "NEXT": "1",
    }
    kis_market_data._validate_request(transport.requests[1])
    kis_market_data._validate_request(transport.requests[2])
    assert all("trading" not in request.url for request in transport.requests)


def test_minute_client_accepts_f_continuation_header() -> None:
    transport = _RecordingTransport(
        [_token(), _page("195900", "180000", next_value="", continuation="F")]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    page = client.fetch_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))

    assert page.next_cursor == "1"


def test_historical_session_reuses_one_token_for_daily_and_minute_metadata_reads() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            _daily_page("20260717", "20260716", continuation="F"),
            _page("195900", "180000", next_value=""),
        ]
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    daily = client.fetch_daily_page(KisPaperDailyQuery(symbol="QQQ", by_date="20260719"))
    minute = client.fetch_minute_page(KisPaperMinuteQuery(exchange="NAS", symbol="SPY"))

    assert daily.row_count == 2
    assert daily.newest_date == "20260717"
    assert daily.oldest_date == "20260716"
    assert daily.required_ohlcv_fields_present is True
    assert daily.continuation_available is True
    assert daily.continuation_value == "F"
    assert minute.bars[0].exchange_time == "195900"
    assert client.call_counts.token_attempts == 1
    assert client.call_counts.daily_page_attempts == 1
    assert client.call_counts.minute_page_attempts == 1
    paths = [
        request.url.removeprefix(KIS_PAPER_MARKET_DATA_BASE_URL)
        for request in transport.requests
    ]
    assert paths == [
        KIS_PAPER_TOKEN_PATH,
        KIS_PAPER_DAILY_PATH,
        KIS_PAPER_MINUTE_PATH,
    ]
    assert transport.requests[1].headers["tr_cont"] == ""
    assert transport.requests[1].query == {
        "AUTH": "",
        "EXCD": "NAS",
        "SYMB": "QQQ",
        "GUBN": "0",
        "BYMD": "20260719",
        "MODP": "0",
    }


def test_daily_historical_query_rejects_unapproved_scope() -> None:
    with pytest.raises(ValueError, match="symbol"):
        KisPaperDailyQuery(symbol="IWM", by_date="20260719")
    with pytest.raises(ValueError, match="continuation"):
        KisPaperDailyQuery(symbol="QQQ", by_date="20260719", continuation="M")


def test_daily_query_can_bind_a_separate_immutable_probe_scope_without_widening_default() -> None:
    probe_scope = {"AAPL": frozenset({"NAS"})}
    query = KisPaperDailyQuery(
        symbol="AAPL",
        exchange="NAS",
        by_date="20260719",
        approved_symbol_exchanges=probe_scope,
    )
    request = KisMarketDataRequest(
        method="GET",
        url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}",
        headers={"tr_id": KIS_PAPER_DAILY_TR_ID, "tr_cont": ""},
        query={
            "AUTH": "",
            "EXCD": "NAS",
            "SYMB": "AAPL",
            "GUBN": "0",
            "BYMD": "20260719",
            "MODP": "0",
        },
    )

    assert "AAPL" not in kis_market_data.KIS_PAPER_DAILY_SYMBOL_EXCHANGES
    assert query.approved_symbol_exchanges == probe_scope
    with pytest.raises(TypeError):
        query.approved_symbol_exchanges["MSFT"] = frozenset({"NAS"})  # type: ignore[index]
    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        kis_market_data._validate_request(request)
    kis_market_data._validate_request(
        request,
        daily_symbol_exchanges=query.approved_symbol_exchanges,
    )


def test_daily_query_scope_reaches_urllib_transport_without_widening_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[urllib.request.Request] = []
    responses = [_token(), _daily_page("20260717", "20260716", continuation="")]

    class _Response:
        def __init__(self, response: KisMarketDataResponse) -> None:
            self.status = response.status_code
            self.headers = response.headers
            self._body = response.body

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return self._body

    class _RecordingOpener:
        def open(self, request: urllib.request.Request, **_kwargs: object) -> _Response:
            opened.append(request)
            return _Response(responses.pop(0))

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: _RecordingOpener())
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=UrllibKisPaperMarketDataTransport(),
    )

    page = client.fetch_daily_raw_page(
        KisPaperDailyQuery(
            symbol="AAPL",
            exchange="NAS",
            by_date="20260719",
            approved_symbol_exchanges={"AAPL": frozenset({"NAS"})},
        )
    )

    assert page.page.row_count == 2
    assert [request.full_url for request in opened] == [
        f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
        f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_DAILY_PATH}"
        "?AUTH=&EXCD=NAS&SYMB=AAPL&GUBN=0&BYMD=20260719&MODP=0",
    ]
    assert "AAPL" not in kis_market_data.KIS_PAPER_DAILY_SYMBOL_EXCHANGES


@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"AAPL": frozenset()},
        {"AAPL-": frozenset({"NAS"})},
        {"AAPL": frozenset({"NASDAQ"})},
    ],
)
def test_daily_query_rejects_invalid_separate_scope(
    scope: dict[str, frozenset[str]],
) -> None:
    with pytest.raises(ValueError, match="scope"):
        KisPaperDailyQuery(
            symbol="AAPL",
            exchange="NAS",
            by_date="20260719",
            approved_symbol_exchanges=scope,
        )


def test_minute_query_requires_a_supported_us_venue_and_complete_cursor() -> None:
    assert KisPaperMinuteQuery(exchange="AMS", symbol="SPY").exchange == "AMS"
    with pytest.raises(ValueError, match="exchange"):
        KisPaperMinuteQuery(exchange="NASD", symbol="QQQ")
    with pytest.raises(ValueError, match="symbol/exchange"):
        KisPaperMinuteQuery(exchange="NAS", symbol="IWM")
    with pytest.raises(ValueError, match="continuation"):
        KisPaperMinuteQuery(exchange="NAS", symbol="QQQ", continuation_next="1")


def test_minute_client_classifies_a_successful_empty_list_after_payload_validation() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {"next": "", "more": "0"},
                    "output2": [],
                }
            ),
        ]
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    with pytest.raises(KisPaperMarketDataError, match="^minute_response_empty$"):
        client.fetch_minute_page(
            KisPaperMinuteQuery(exchange="AMS", symbol="SPY", include_previous_day=True)
        )

    assert client.call_counts.token_attempts == 1
    assert client.call_counts.minute_page_attempts == 1
    assert [request.method for request in transport.requests] == ["POST", "GET"]


def test_minute_client_keeps_rejected_and_malformed_payloads_out_of_empty_category() -> None:
    rejected_transport = _RecordingTransport(
        [_token(), KisMarketDataResponse.from_payload({"rt_cd": "1"})]
    )
    rejected_client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=rejected_transport,
    )
    malformed_transport = _RecordingTransport(
        [
            _token(),
            KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {"next": "", "more": "0"},
                    "output2": "",
                }
            ),
        ]
    )
    malformed_client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=malformed_transport,
    )

    with pytest.raises(KisPaperMarketDataError, match="^minute_response_rejected$"):
        rejected_client.fetch_minute_page(KisPaperMinuteQuery(exchange="AMS", symbol="SPY"))
    with pytest.raises(KisPaperMarketDataError, match="^minute_response_invalid$"):
        malformed_client.fetch_minute_page(KisPaperMinuteQuery(exchange="AMS", symbol="SPY"))

    assert rejected_client.call_counts.minute_page_attempts == 1
    assert malformed_client.call_counts.minute_page_attempts == 1


def test_minute_raw_bar_rejects_invalid_calendar_timestamps() -> None:
    with pytest.raises(KisPaperMarketDataError, match="minute_exchange_timestamp_invalid"):
        kis_market_data.KisPaperMinuteRawBar(
            exchange_date="20260230",
            exchange_time="093000",
            korea_date="20260301",
            korea_time="013000",
            open="100",
            high="101",
            low="99",
            last="100.5",
            volume="100",
        )


def test_market_data_config_repr_does_not_expose_credentials() -> None:
    config = KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret")

    assert "paper-key" not in repr(config)
    assert "paper-secret" not in repr(config)


def test_auth_failure_stops_before_any_market_data_get() -> None:
    transport = _RecordingTransport(
        [KisMarketDataResponse.from_payload({"rt_cd": "1"}, status_code=403)]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    with pytest.raises(KisPaperMarketDataError, match="auth_rejected"):
        client.fetch_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))

    assert [request.method for request in transport.requests] == ["POST"]


def test_market_data_client_classifies_the_safe_kis_rate_limit_code() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            KisMarketDataResponse.from_payload({"rt_cd": "1", "msg_cd": "EGW00201"}),
        ]
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    with pytest.raises(KisPaperMarketDataError, match="rate_limited"):
        client.fetch_daily_page(KisPaperDailyQuery(symbol="QQQ", by_date="20260719"))


def test_market_data_client_classifies_rate_limit_before_token_auth_rejection() -> None:
    transport = _RecordingTransport(
        [KisMarketDataResponse.from_payload({"rt_cd": "1", "msg_cd": "EGW00201"})]
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    with pytest.raises(KisPaperMarketDataError, match="rate_limited"):
        client.fetch_daily_page(KisPaperDailyQuery(symbol="QQQ", by_date="20260719"))

    assert [request.method for request in transport.requests] == ["POST"]


def test_urllib_transport_gates_each_allowed_request_and_records_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Gate:
        def __init__(self) -> None:
            self.slot_count = 0
            self.rate_limit_count = 0

        def wait_for_request_slot(self) -> None:
            self.slot_count += 1

        def record_rate_limit(self) -> None:
            self.rate_limit_count += 1

    class _HttpErrorOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            raise urllib.error.HTTPError(
                url="https://example.test",
                code=429,
                msg="rate limited",
                hdrs=None,
                fp=None,
            )

    gate = _Gate()
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: _HttpErrorOpener())
    transport = UrllibKisPaperMarketDataTransport(request_gate=gate)  # type: ignore[arg-type]

    response = transport.request(
        KisMarketDataRequest(
            method="POST",
            url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
            headers={"content-type": "application/json", "accept": "application/json"},
            json_body={"grant_type": "client_credentials", "appkey": "key", "appsecret": "secret"},
        )
    )

    assert response.status_code == 429
    assert gate.slot_count == 1
    assert gate.rate_limit_count == 1


def test_urllib_transport_yields_before_request_pacing_when_token_is_not_due(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _RequestGate:
        def __init__(self) -> None:
            self.slot_count = 0

        def wait_for_request_slot(self) -> None:
            self.slot_count += 1

        def record_rate_limit(self) -> None:
            raise AssertionError("a deferred token must not record a rate limit")

    class _FailingOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("a deferred token must not make an HTTP request")

    def clock() -> datetime:
        return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)

    token_gate = KisPaperMarketDataTokenStartGate(control_root=tmp_path / "control", clock=clock)
    assert token_gate.claim_token_request_start() is True
    request_gate = _RequestGate()
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: _FailingOpener())
    transport = UrllibKisPaperMarketDataTransport(
        request_gate=request_gate,  # type: ignore[arg-type]
        token_start_gate=token_gate,
    )

    with pytest.raises(KisPaperMarketDataError, match="token_request_not_due"):
        transport.request(
            KisMarketDataRequest(
                method="POST",
                url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
                headers={"content-type": "application/json", "accept": "application/json"},
                json_body={
                    "grant_type": "client_credentials",
                    "appkey": "key",
                    "appsecret": "secret",
                },
            )
        )

    assert request_gate.slot_count == 0


def test_urllib_transport_disables_proxies_and_installs_a_redirect_rejecting_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed: list[object] = []

    class _UnusedOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("redirect test must not make an HTTP request")

    def build_opener(*handlers: object) -> _UnusedOpener:
        installed.extend(handlers)
        return _UnusedOpener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    UrllibKisPaperMarketDataTransport()

    assert len(installed) == 2
    proxy_handler, handler = installed
    assert isinstance(proxy_handler, urllib.request.ProxyHandler)
    assert proxy_handler.proxies == {}
    assert isinstance(handler, kis_market_data._RejectRedirectHandler)
    with pytest.raises(KisPaperMarketDataError, match="redirect_rejected"):
        handler.redirect_request()


def test_urllib_transport_encodes_the_sample_aligned_minute_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[urllib.request.Request] = []
    responses = [
        _token(),
        _page("195900", "180000", next_value="0", continuation="M"),
        _page("175900", "160000", next_value="1", continuation=""),
    ]

    class _Response:
        def __init__(self, response: KisMarketDataResponse) -> None:
            self.status = response.status_code
            self.headers = response.headers
            self._body = response.body

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return self._body

    class _RecordingOpener:
        def open(self, request: urllib.request.Request, **_kwargs: object) -> _Response:
            opened.append(request)
            return _Response(responses.pop(0))

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: _RecordingOpener())
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=UrllibKisPaperMarketDataTransport(),
    )

    first = client.fetch_minute_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))
    client.fetch_minute_page(
        KisPaperMinuteQuery(
            exchange="NAS",
            symbol="QQQ",
            continuation_next=first.next_cursor,
            continuation_key="20260717175900",
        )
    )

    minute_url = f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_MINUTE_PATH}"
    assert [request.get_method() for request in opened] == ["POST", "GET", "GET"]
    assert [request.full_url for request in opened] == [
        f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_TOKEN_PATH}",
        f"{minute_url}?AUTH=&EXCD=NAS&SYMB=QQQ&NMIN=1&PINC=0&NREC=120&FILL=&KEYB=&NEXT=",
        f"{minute_url}?AUTH=&EXCD=NAS&SYMB=QQQ&NMIN=1&PINC=1&NREC=120&FILL=&KEYB=20260717175900&NEXT=1",
    ]
    assert [
        {name.lower(): value for name, value in request.header_items()}
        for request in opened[1:]
    ] == [
        {
            "authorization": "Bearer test-token",
            "appkey": "paper-key",
            "appsecret": "paper-secret",
            "tr_id": KIS_PAPER_MINUTE_TR_ID,
            "tr_cont": "",
            "custtype": "P",
            "accept": "application/json",
        },
        {
            "authorization": "Bearer test-token",
            "appkey": "paper-key",
            "appsecret": "paper-secret",
            "tr_id": KIS_PAPER_MINUTE_TR_ID,
            "tr_cont": "N",
            "custtype": "P",
            "accept": "application/json",
        },
    ]


@pytest.mark.parametrize(
    "url",
    [
        f"{KIS_PAPER_MARKET_DATA_BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance",
        f"{KIS_PAPER_MARKET_DATA_BASE_URL}/uapi/overseas-stock/v1/trading/order",
        f"{KIS_PAPER_MARKET_DATA_BASE_URL}/uapi/overseas-stock/v1/trading/order-rvsecncl",
        "https://openapi.koreainvestment.com:9443/oauth2/tokenP",
    ],
)
def test_transport_rejects_account_order_and_live_requests_before_opening(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    opened = False

    class _UnusedOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            nonlocal opened
            opened = True
            raise AssertionError("allowlist rejection must precede opener.open")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: _UnusedOpener())
    transport = UrllibKisPaperMarketDataTransport()

    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        transport.request(
            KisMarketDataRequest(method="GET", url=url, headers={}, query={})
        )

    assert opened is False


@pytest.mark.parametrize(
    ("path", "headers", "query"),
    [
        (
            KIS_PAPER_MINUTE_PATH,
            {"tr_id": KIS_PAPER_MINUTE_TR_ID, "custtype": "P", "tr_cont": ""},
            {
                "AUTH": "",
                "EXCD": "NYS",
                "SYMB": "QQQ",
                "NMIN": "1",
                "PINC": "0",
                "NREC": "120",
                "FILL": "",
                "KEYB": "",
                "NEXT": "",
            },
        ),
        (
            KIS_PAPER_MINUTE_PATH,
            {"tr_id": KIS_PAPER_MINUTE_TR_ID, "custtype": "P", "tr_cont": ""},
            {
                "AUTH": "",
                "EXCD": "NAS",
                "SYMB": "IWM",
                "NMIN": "1",
                "PINC": "0",
                "NREC": "120",
                "FILL": "",
                "KEYB": "",
                "NEXT": "",
            },
        ),
        (
            KIS_PAPER_MINUTE_PATH,
            {"tr_id": KIS_PAPER_MINUTE_TR_ID, "custtype": "P", "tr_cont": ""},
            {
                "AUTH": "",
                "EXCD": "NAS",
                "SYMB": "QQQ",
                "NMIN": "5",
                "PINC": "0",
                "NREC": "120",
                "FILL": "",
                "KEYB": "",
                "NEXT": "",
            },
        ),
        (
            KIS_PAPER_DAILY_PATH,
            {"tr_id": KIS_PAPER_DAILY_TR_ID, "tr_cont": ""},
            {
                "AUTH": "",
                "EXCD": "NAS",
                "SYMB": "IWM",
                "GUBN": "0",
                "BYMD": "20260719",
                "MODP": "0",
            },
        ),
    ],
)
def test_transport_rejects_out_of_scope_market_data_values_before_opening(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    headers: dict[str, str],
    query: dict[str, str],
) -> None:
    opened = False

    class _UnusedOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            nonlocal opened
            opened = True
            raise AssertionError("scope rejection must precede opener.open")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: _UnusedOpener())
    transport = UrllibKisPaperMarketDataTransport()

    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{path}",
                headers=headers,
                query=query,
            )
        )

    assert opened is False


@pytest.mark.parametrize(
    ("headers", "continuation", "include_unsupported_fill_gubn"),
    [
        ({"tr_id": KIS_PAPER_MINUTE_TR_ID, "custtype": "P", "tr_cont": ""}, False, True),
        ({"tr_id": KIS_PAPER_MINUTE_TR_ID, "custtype": "I", "tr_cont": ""}, False, False),
        ({"tr_id": KIS_PAPER_MINUTE_TR_ID, "custtype": "P", "tr_cont": "N"}, False, False),
        ({"tr_id": KIS_PAPER_MINUTE_TR_ID, "custtype": "P", "tr_cont": ""}, True, False),
    ],
)
def test_transport_rejects_minute_contract_drift_before_opening(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    continuation: bool,
    include_unsupported_fill_gubn: bool,
) -> None:
    opened = False

    class _UnusedOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            nonlocal opened
            opened = True
            raise AssertionError("contract rejection must precede opener.open")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: _UnusedOpener())
    transport = UrllibKisPaperMarketDataTransport()
    query = {
        "AUTH": "",
        "EXCD": "NAS",
        "SYMB": "QQQ",
        "NMIN": "1",
        "PINC": "1" if continuation else "0",
        "NREC": "120",
        "FILL": "",
        "KEYB": "20260717175900" if continuation else "",
        "NEXT": "1" if continuation else "",
    }
    if include_unsupported_fill_gubn:
        query["FILL_GUBN"] = "0"

    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{KIS_PAPER_MARKET_DATA_BASE_URL}{KIS_PAPER_MINUTE_PATH}",
                headers=headers,
                query=query,
            )
        )

    assert opened is False


def test_market_data_client_stops_before_a_fourth_minute_page_request() -> None:
    transport = _RecordingTransport(
        [_token(), *[_page("195900", "180000", next_value="") for _ in range(3)]]
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    for _ in range(KIS_PAPER_MARKET_DATA_MAX_MINUTE_PAGE_ATTEMPTS):
        client.fetch_minute_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))

    with pytest.raises(KisPaperMarketDataError, match="minute_page_limit_exceeded"):
        client.fetch_minute_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))

    assert client.call_counts.minute_page_attempts == KIS_PAPER_MARKET_DATA_MAX_MINUTE_PAGE_ATTEMPTS
    assert len(transport.requests) == 1 + KIS_PAPER_MARKET_DATA_MAX_MINUTE_PAGE_ATTEMPTS


def test_market_data_client_stops_before_a_fourth_daily_page_request() -> None:
    transport = _RecordingTransport(
        [_token(), *[_daily_page("20260717", "20260716", continuation="") for _ in range(3)]]
    )
    client = KisPaperMarketDataClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    for _ in range(KIS_PAPER_MARKET_DATA_MAX_DAILY_PAGE_ATTEMPTS):
        client.fetch_daily_page(KisPaperDailyQuery(symbol="QQQ", by_date="20260719"))

    with pytest.raises(KisPaperMarketDataError, match="daily_page_limit_exceeded"):
        client.fetch_daily_page(KisPaperDailyQuery(symbol="QQQ", by_date="20260719"))

    assert client.call_counts.daily_page_attempts == KIS_PAPER_MARKET_DATA_MAX_DAILY_PAGE_ATTEMPTS
    assert len(transport.requests) == 1 + KIS_PAPER_MARKET_DATA_MAX_DAILY_PAGE_ATTEMPTS


def test_minute_client_rejects_more_than_documented_page_limit() -> None:
    transport = _RecordingTransport(
        [
            _token(),
            KisMarketDataResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output1": {"next": "", "more": "0"},
                    "output2": [_row("195900") for _ in range(121)],
                }
            ),
        ]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    with pytest.raises(KisPaperMarketDataError, match="minute_response_invalid"):
        client.fetch_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))

    assert [request.method for request in transport.requests] == ["POST", "GET"]


def test_dotenv_loader_stops_before_later_live_bytes(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_bytes(
        b"THERICHER_MODE=off\n"
        b"KIS_PAPER_APP_KEY=paper-key\n"
        b"KIS_PAPER_APP_SECRET=paper-secret\n"
        b"KIS_LIVE_APP_SECRET=\xff"
    )

    config = load_kis_paper_market_data_config(dotenv_path)

    assert config.app_key == "paper-key"
    assert config.app_secret == "paper-secret"


def test_dotenv_loader_rejects_an_unapproved_key_before_the_paper_block(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_bytes(
        b"THERICHER_MODE=off\n"
        b"KIS_LIVE_APP_KEY=\xff\n"
        b"KIS_PAPER_APP_KEY=paper-key\n"
        b"KIS_PAPER_APP_SECRET=paper-secret\n"
    )

    with pytest.raises(KisPaperMarketDataError, match="config_missing"):
        load_kis_paper_market_data_config(dotenv_path)


def test_dotenv_loader_rejects_a_missing_paper_key_before_a_later_live_value(
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_bytes(
        b"THERICHER_MODE=off\n"
        b"KIS_PAPER_APP_KEY=paper-key\n"
        b"KIS_LIVE_APP_SECRET=\xff\n"
    )

    with pytest.raises(KisPaperMarketDataError, match="config_missing"):
        load_kis_paper_market_data_config(dotenv_path)


def test_dotenv_loader_accepts_the_approved_nonsecret_prefix(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "THERICHER_MODE=off\n"
        "THERICHER_HOST_MODEL_ARTIFACT_ROOT=\n"
        "THERICHER_MODEL_ARTIFACT_ROOT=\n"
        "# KIS mock/paper trading credentials.\n"
        "KIS_PAPER_APP_KEY=paper-key\n"
        "KIS_PAPER_APP_SECRET=paper-secret\n",
        encoding="utf-8",
    )

    config = load_kis_paper_market_data_config(dotenv_path)

    assert config.app_key == "paper-key"
    assert config.app_secret == "paper-secret"


def test_dotenv_loader_accepts_a_blank_dashboard_placeholder_before_paper_keys(
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "THERICHER_MODE=off\n"
        "THERICHER_DASHBOARD_TOKEN=\n"
        "THERICHER_HOST_MODEL_ARTIFACT_ROOT=\n"
        "THERICHER_MODEL_ARTIFACT_ROOT=\n"
        "KIS_PAPER_APP_KEY=paper-key\n"
        "KIS_PAPER_APP_SECRET=paper-secret\n",
        encoding="utf-8",
    )

    config = load_kis_paper_market_data_config(dotenv_path)

    assert config.app_key == "paper-key"
    assert config.app_secret == "paper-secret"


def test_dotenv_loader_rejects_nonempty_dashboard_value_without_reading_the_line(
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_bytes(
        b"THERICHER_MODE=off\n"
        b"THERICHER_DASHBOARD_TOKEN=must-not-be-retained\xff\n"
        b"KIS_PAPER_APP_KEY=paper-key\n"
        b"KIS_PAPER_APP_SECRET=paper-secret\n"
    )

    with pytest.raises(KisPaperMarketDataError, match="config_missing"):
        load_kis_paper_market_data_config(dotenv_path)


def test_dotenv_loader_accepts_kis_paper_mode_before_the_paper_credentials(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "THERICHER_MODE=kis_paper\n"
        "KIS_PAPER_APP_KEY=paper-key\n"
        "KIS_PAPER_APP_SECRET=paper-secret\n",
        encoding="utf-8",
    )

    config = load_kis_paper_market_data_config(dotenv_path)

    assert config.app_key == "paper-key"
    assert config.app_secret == "paper-secret"


def test_dotenv_loader_rejects_live_mode_before_reading_paper_credentials(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "THERICHER_MODE=kis_live\n"
        "KIS_PAPER_APP_KEY=paper-key\n"
        "KIS_PAPER_APP_SECRET=paper-secret\n",
        encoding="utf-8",
    )

    with pytest.raises(KisPaperMarketDataError, match="config_missing"):
        load_kis_paper_market_data_config(dotenv_path)


def test_market_data_loader_accepts_complete_paper_environment_without_dotenv(
    tmp_path: Path,
) -> None:
    config = load_kis_paper_market_data_config(
        tmp_path / "missing.env",
        environment={
            "THERICHER_MODE": "off",
            "KIS_PAPER_APP_KEY": "paper-key",
            "KIS_PAPER_APP_SECRET": "paper-secret",
        },
    )

    assert config.app_key == "paper-key"
    assert config.app_secret == "paper-secret"


def test_market_data_loader_rejects_partial_environment_without_dotenv_fallback(
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "THERICHER_MODE=off\n"
        "KIS_PAPER_APP_KEY=dotenv-key\n"
        "KIS_PAPER_APP_SECRET=dotenv-secret\n",
        encoding="utf-8",
    )

    with pytest.raises(KisPaperMarketDataError, match="config_missing"):
        load_kis_paper_market_data_config(
            dotenv_path,
            environment={"KIS_PAPER_APP_KEY": "environment-key"},
        )


def test_market_data_loader_rejects_live_environment_before_dotenv_fallback(
    tmp_path: Path,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "THERICHER_MODE=off\n"
        "KIS_PAPER_APP_KEY=dotenv-key\n"
        "KIS_PAPER_APP_SECRET=dotenv-secret\n",
        encoding="utf-8",
    )

    with pytest.raises(KisPaperMarketDataError, match="config_missing"):
        load_kis_paper_market_data_config(
            dotenv_path,
            environment={"THERICHER_MODE": "kis_live"},
        )


def test_market_data_loader_environment_never_reads_live_values(tmp_path: Path) -> None:
    class PaperOnlyEnvironment(dict[str, str]):
        def get(self, key: str, default: str | None = None) -> str | None:
            if key.startswith("KIS_LIVE_"):
                raise AssertionError("live credential names must stay unread")
            return super().get(key, default)

    config = load_kis_paper_market_data_config(
        tmp_path / "missing.env",
        environment=PaperOnlyEnvironment(
            {
                "THERICHER_MODE": "off",
                "KIS_PAPER_APP_KEY": "paper-key",
                "KIS_PAPER_APP_SECRET": "paper-secret",
                "KIS_LIVE_APP_KEY": "must-not-be-read",
            }
        ),
    )

    assert config.app_key == "paper-key"


def _token() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"access_token": "test-token"})


def _page(
    first_time: str,
    second_time: str,
    *,
    next_value: str,
    continuation: str = "",
) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {"next": next_value, "more": "0"},
            "output2": [_row(first_time), _row(second_time)],
        },
        headers={"tr_cont": continuation},
    )


def _daily_page(first_date: str, second_date: str, *, continuation: str) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {"nrec": "100"},
            "output2": [
                {
                    "xymd": first_date,
                    "open": "100",
                    "high": "102",
                    "low": "99",
                    "clos": "101",
                    "tvol": "1000",
                },
                {
                    "xymd": second_date,
                    "open": "98",
                    "high": "101",
                    "low": "97",
                    "clos": "100",
                    "tvol": "900",
                },
            ],
        },
        headers={"tr_cont": continuation},
    )


def _row(exchange_time: str) -> dict[str, str]:
    return {
        "xymd": "20260717",
        "xhms": exchange_time,
        "kymd": "20260718",
        "khms": "070000",
        "open": "100",
        "high": "102",
        "low": "99",
        "last": "101",
        "evol": "1000",
    }
