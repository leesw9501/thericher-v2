from __future__ import annotations

import urllib.request
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
            _page("195900", "180000", next_value="1"),
            _page("175900", "160000", next_value="1"),
        ]
    )
    client = KisPaperMinuteClient(
        config=KisPaperMarketDataConfig(app_key="paper-key", app_secret="paper-secret"),
        transport=transport,
    )

    first = client.fetch_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))
    second = client.fetch_page(
        KisPaperMinuteQuery(
            exchange="NAS",
            symbol="QQQ",
            continuation_next=first.next_cursor,
            continuation_key="20260717175900",
        )
    )

    assert first.next_cursor == "1"
    assert first.more == "0"
    assert first.bars[0].exchange_time == "195900"
    assert first.bars[-1].exchange_time == "180000"
    assert first.bars[0].korea_time == "070000"
    assert first.bars[0].volume == Decimal("1000")
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
    assert transport.requests[1].query["NREC"] == "120"
    assert transport.requests[1].query["PINC"] == "0"
    assert transport.requests[1].query["NEXT"] == ""
    assert transport.requests[1].query["KEYB"] == ""
    assert transport.requests[2].query["PINC"] == "1"
    assert transport.requests[2].query["NEXT"] == "1"
    assert transport.requests[2].query["KEYB"] == "20260717175900"
    assert all("trading" not in request.url for request in transport.requests)


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


def test_minute_query_requires_the_observed_us_exchange_scope_and_complete_cursor() -> None:
    with pytest.raises(ValueError, match="exchange"):
        KisPaperMinuteQuery(exchange="NASD", symbol="QQQ")
    with pytest.raises(ValueError, match="symbol"):
        KisPaperMinuteQuery(exchange="NAS", symbol="IWM")
    with pytest.raises(ValueError, match="continuation"):
        KisPaperMinuteQuery(exchange="NAS", symbol="QQQ", continuation_next="1")


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
            {"tr_id": KIS_PAPER_MINUTE_TR_ID},
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
                "FILL_GUBN": "0",
            },
        ),
        (
            KIS_PAPER_MINUTE_PATH,
            {"tr_id": KIS_PAPER_MINUTE_TR_ID},
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
                "FILL_GUBN": "0",
            },
        ),
        (
            KIS_PAPER_MINUTE_PATH,
            {"tr_id": KIS_PAPER_MINUTE_TR_ID},
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
                "FILL_GUBN": "0",
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


def test_dotenv_loader_requires_off_mode_before_the_paper_credentials(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "THERICHER_MODE=local_simulation\n"
        "KIS_PAPER_APP_KEY=paper-key\n"
        "KIS_PAPER_APP_SECRET=paper-secret\n",
        encoding="utf-8",
    )

    with pytest.raises(KisPaperMarketDataError, match="config_missing"):
        load_kis_paper_market_data_config(dotenv_path)


def _token() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"access_token": "test-token"})


def _page(first_time: str, second_time: str, *, next_value: str) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {"next": next_value, "more": "0"},
            "output2": [_row(first_time), _row(second_time)],
        }
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
