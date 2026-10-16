from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from thericher_v2.execution import kis_market_data as m


class Transport:
    def __init__(self, *, short=False, continuation="M"):
        self.requests = []
        self.short = short
        self.continuation = continuation

    def request(self, request):
        m._validate_request(request)
        self.requests.append(request)
        if request.method == "POST":
            return m.KisMarketDataResponse.from_payload({"access_token": "synthetic"})
        start = datetime(2026, 10, 15, 16) - timedelta(minutes=120 * (len(self.requests) - 2))
        rows = []
        for i in range(1 if self.short else 120):
            stamp = start - timedelta(minutes=i)
            korea = stamp + timedelta(hours=13)
            rows.append(dict(
                xymd=stamp.strftime("%Y%m%d"), xhms=stamp.strftime("%H%M%S"),
                kymd=korea.strftime("%Y%m%d"), khms=korea.strftime("%H%M%S"),
                open="10", high="12", low="9", last="11", evol="100",
            ))
        return m.KisMarketDataResponse.from_payload(
            {"rt_cd": "0", "output1": {}, "output2": rows},
            headers={"tr_cont": self.continuation},
        )


def client(transport, route="stock_capability_probe"):
    return m.KisPaperMarketDataClient(
        config=m.KisPaperMarketDataConfig(app_key="synthetic", app_secret="synthetic"),
        transport=transport, minute_route=route, max_minute_page_attempts=2,
    )


def head():
    return m.KisPaperStockMinuteQuery(symbol="AAPL", exchange="NAS")


def test_exact_two_page_witness_reuses_auth_and_native_parser():
    t = Transport()
    c = client(t)
    first = c.fetch_minute_page(head())
    key = m.derive_kis_paper_minute_continuation_key(first)
    following = replace(head(), include_previous_day=True, continuation_next="1",
                        continuation_key=key)
    with pytest.raises(m.KisPaperMarketDataError):
        c.fetch_minute_page(replace(following, continuation_key="20261015120000"))
    second = c.fetch_minute_page(following)
    assert len(first.bars) == len(second.bars) == 120
    assert c.call_counts == m.KisPaperMarketDataCallCounts(1, 2, 0)
    with pytest.raises(m.KisPaperMarketDataError):
        c.fetch_minute_page(following)
    assert [r.method for r in t.requests] == ["POST", "GET", "GET"]


@pytest.mark.parametrize("symbol,exchange", [("MSFT", "NAS"), ("AAPL", "NYS"), ("QQQ", "NAS")])
def test_stock_scope_is_closed(symbol, exchange):
    with pytest.raises(ValueError):
        m.KisPaperStockMinuteQuery(symbol=symbol, exchange=exchange)


def test_legacy_and_cross_route_reject_without_auth():
    with pytest.raises(ValueError):
        m.KisPaperMinuteQuery(symbol="AAPL", exchange="NAS")
    t = Transport()
    with pytest.raises(m.KisPaperMarketDataError):
        client(t, "standard").fetch_minute_page(head())
    with pytest.raises(m.KisPaperMarketDataError):
        client(t).fetch_minute_page(m.KisPaperMinuteQuery(symbol="QQQ", exchange="NAS"))
    assert not t.requests


@pytest.mark.parametrize("signal", ["E", "D", "unknown"])
def test_terminal_or_unrecognized_page_cannot_continue(signal):
    t = Transport(continuation=signal)
    c = client(t)
    page = c.fetch_minute_page(head())
    with pytest.raises(m.KisPaperMarketDataError):
        c.fetch_minute_page(replace(
            head(), include_previous_day=True, continuation_next="1",
            continuation_key=m.derive_kis_paper_minute_continuation_key(page),
        ))
    assert c.call_counts.minute_page_attempts == 1


@pytest.mark.parametrize("short", [False, True])
def test_blank_header_admits_only_exact_bounded_probe(short):
    c = client(Transport(short=short, continuation=""))
    page = c.fetch_minute_page(head())
    assert page.next_cursor is None and page.continuation_signal == "blank_or_absent"
    c.fetch_minute_page(replace(
        head(), include_previous_day=True, continuation_next="1",
        continuation_key=m.derive_kis_paper_minute_continuation_key(page),
    ))
    assert c.call_counts == m.KisPaperMarketDataCallCounts(1, 2, 0)


def test_transport_rejects_untyped_stock_and_tampering():
    t = Transport()
    client(t).fetch_minute_page(head())
    request = t.requests[-1]
    for bad in [
        replace(request, stock_minute_query=None),
        replace(request, query={**request.query, "SYMB": "MSFT"}),
        replace(request, url="https://example.invalid" + m.KIS_PAPER_MINUTE_PATH),
        replace(request, url=m.KIS_PAPER_MARKET_DATA_BASE_URL + "/account"),
        replace(request, headers={**request.headers, "tr_id": "wrong"}),
    ]:
        with pytest.raises(m.KisPaperMarketDataError):
            m._validate_request(bad)


def test_stock_route_cannot_read_daily_or_accept_other_caps():
    with pytest.raises(ValueError):
        m.KisPaperMarketDataClient(
            config=m.KisPaperMarketDataConfig(app_key="x", app_secret="y"),
            transport=Transport(), minute_route="stock_capability_probe",
        )
    t = Transport()
    with pytest.raises(m.KisPaperMarketDataError):
        client(t).fetch_daily_raw_page(m.KisPaperDailyQuery(symbol="QQQ", by_date="20261015"))
    assert not t.requests


@pytest.mark.parametrize("fault", ["duplicate", "clock", "order", "ohlc", "mixed_head"])
def test_native_page_faults_are_not_relaxed(fault):
    class Fault(Transport):
        def request(self, request):
            response = super().request(request)
            if request.method == "POST":
                return response
            payload = dict(response.payload())
            rows = payload["output2"]
            if fault == "duplicate":
                rows[1] = rows[0]
            elif fault == "clock":
                rows[0]["khms"] = "000000"
            elif fault == "order":
                rows[1], rows[2] = rows[2], rows[1]
            elif fault == "mixed_head":
                rows[-1].update(xymd="20261014", kymd="20261015")
            else:
                rows[0]["high"] = "1"
            return m.KisMarketDataResponse.from_payload(payload, headers=response.headers)
    with pytest.raises(m.KisPaperMarketDataError):
        client(Fault()).fetch_minute_page(head())


def test_repeated_page_is_not_progress():
    class Repeating(Transport):
        saved = None

        def request(self, request):
            response = super().request(request)
            if request.method == "GET":
                self.saved = self.saved or response
                return self.saved
            return response
    c = client(Repeating())
    page = c.fetch_minute_page(head())
    with pytest.raises(m.KisPaperMarketDataError, match="continuity"):
        c.fetch_minute_page(replace(
            head(), include_previous_day=True, continuation_next="1",
            continuation_key=m.derive_kis_paper_minute_continuation_key(page),
        ))


def test_empty_stock_head_is_valid_and_has_no_cursor():
    class Empty(Transport):
        def request(self, request):
            response = super().request(request)
            if request.method == "GET":
                return m.KisMarketDataResponse.from_payload(
                    {"rt_cd": "0", "output1": {}, "output2": []},
                    headers={"tr_cont": "M"},
                )
            return response
    c = client(Empty())
    page = c.fetch_minute_page(head())
    assert page.bars == () and page.next_cursor is None
    with pytest.raises(m.KisPaperMarketDataError):
        c.fetch_minute_page(replace(
            head(), include_previous_day=True, continuation_next="1",
            continuation_key="20261015120000",
        ))


def test_mixed_date_continuation_keeps_paired_monotone_clocks():
    class Mixed(Transport):
        def request(self, request):
            response = super().request(request)
            if request.method == "POST":
                return response
            start = datetime(2026, 10, 15, 0, 30) - timedelta(
                minutes=len(self.requests) - 2)
            payload = dict(response.payload())
            for i, row in enumerate(payload["output2"]):
                stamp = start - timedelta(minutes=i)
                korea = stamp + timedelta(hours=13)
                row.update(xymd=stamp.strftime("%Y%m%d"), xhms=stamp.strftime("%H%M%S"),
                           kymd=korea.strftime("%Y%m%d"), khms=korea.strftime("%H%M%S"))
            if len(self.requests) == 2:
                payload["output2"] = payload["output2"][:1]
            return m.KisMarketDataResponse.from_payload(payload, headers={"tr_cont": ""})
    c = client(Mixed())
    page = c.fetch_minute_page(head())
    second = c.fetch_minute_page(replace(
        head(), include_previous_day=True, continuation_next="1",
        continuation_key=m.derive_kis_paper_minute_continuation_key(page),
    ))
    assert len(second.bars) == 120
    assert len({row.exchange_date for row in second.bars}) == 2


def test_request_positional_daily_scope_compatibility():
    scope = {"QQQ": frozenset({"NAS"})}
    request = m.KisMarketDataRequest("GET", "test", {}, {}, None, scope, frozenset({"0"}))
    assert request.daily_symbol_exchanges == scope
    assert request.daily_adjustment_modes == frozenset({"0"})
    assert request.stock_minute_query is None
