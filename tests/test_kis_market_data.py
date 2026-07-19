from __future__ import annotations

from decimal import Decimal

import pytest

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    KisPaperMinuteClient,
    KisPaperMinuteQuery,
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
            _page("180000", "160100", next_value="1"),
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
            continuation_key="20260717180000",
        )
    )

    assert first.next_cursor == "1"
    assert first.more == "0"
    assert first.bars[0].exchange_time == "195900"
    assert first.bars[-1].exchange_time == "180000"
    assert first.bars[0].korea_time == "070000"
    assert first.bars[0].volume == Decimal("1000")
    assert second.bars[0].exchange_time == "180000"

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
    assert transport.requests[1].query["NEXT"] == ""
    assert transport.requests[1].query["KEYB"] == ""
    assert transport.requests[2].query["NEXT"] == "1"
    assert transport.requests[2].query["KEYB"] == "20260717180000"
    assert all("trading" not in request.url for request in transport.requests)


def test_minute_query_requires_the_observed_us_exchange_scope_and_complete_cursor() -> None:
    with pytest.raises(ValueError, match="exchange"):
        KisPaperMinuteQuery(exchange="NASD", symbol="QQQ")
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
