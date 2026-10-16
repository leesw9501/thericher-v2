from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.execution import kis_market_data as m

SCOPE = {"AAPL": frozenset({"NAS"}), "JPM": frozenset({"NYS"}), "IWM": frozenset({"AMS"})}


class Transport:
    def __init__(self, *, empty=False, fault=None):
        self.requests = []
        self.empty, self.fault = empty, fault

    def request(self, request):
        m._validate_request(request)
        self.requests.append(request)
        if request.method == "POST":
            return m.KisMarketDataResponse.from_payload({"access_token": "synthetic"})
        stamp = datetime.strptime(request.query["KEYB"] or "20261015160000", "%Y%m%d%H%M%S")
        rows = []
        for i in range(0 if self.empty else 3):
            x = stamp - timedelta(minutes=i)
            k = x.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("Asia/Seoul"))
            rows.append(
                dict(
                    xymd=x.strftime("%Y%m%d"),
                    xhms=x.strftime("%H%M%S"),
                    kymd=k.strftime("%Y%m%d"),
                    khms=k.strftime("%H%M%S"),
                    open="10",
                    high="12",
                    low="9",
                    last="11",
                    evol="100",
                )
            )
        if self.fault == "duplicate":
            rows[1] = rows[0]
        elif self.fault == "clock":
            rows[0]["khms"] = "000000"
        elif self.fault == "range":
            rows[0]["xhms"] = "170000"
        elif self.fault == "ohlc":
            rows[0]["high"] = "1"
        return m.KisMarketDataResponse.from_payload(
            {"rt_cd": "0", "output1": {}, "output2": rows}, headers={"tr_cont": "N"}
        )


def query(symbol="AAPL", key=None):
    return m.KisPaperHistoricalMinuteQuery(
        symbol=symbol,
        exchange=next(iter(SCOPE[symbol])),
        approved_symbol_exchanges=SCOPE,
        continuation_key=key,
        include_previous_day=key is not None,
        continuation_next="1" if key else None,
    )


def client(t, cap=4):
    return m.KisPaperMarketDataClient(
        config=m.KisPaperMarketDataConfig(app_key="syn-key", app_secret="syn-secret"),
        transport=t,
        minute_route="historical_timestamp",
        minute_symbol_exchanges=SCOPE,
        max_minute_page_attempts=cap,
    )


def test_explicit_timestamp_lookup_ignores_header_as_pagination_authority():
    t = Transport()
    c = client(t)
    for symbol in SCOPE:
        page = c.fetch_minute_page(query(symbol, "20261015000100"))
        assert len(page.bars) == 3
        assert page.continuation_signal == "unrecognized_nonblank"
        assert len({b.exchange_date for b in page.bars}) == 2
    assert c.call_counts == m.KisPaperMarketDataCallCounts(1, 3, 0)


@pytest.mark.parametrize("fault", ["duplicate", "clock", "range", "ohlc"])
def test_native_validation_is_not_weakened(fault):
    with pytest.raises(m.KisPaperMarketDataError):
        client(Transport(fault=fault)).fetch_minute_page(query(key="20261015150000"))


def test_empty_historical_lookup_is_valid_exact_cursor_evidence():
    page = client(Transport(empty=True)).fetch_minute_page(query(key="20261015150000"))
    assert page.bars == () and page.next_cursor is None


def test_map_is_explicit_frozen_and_client_bound():
    with pytest.raises(ValueError):
        m.KisPaperHistoricalMinuteQuery(symbol="AAPL", exchange="NAS")
    q = query()
    with pytest.raises(TypeError):
        q.approved_symbol_exchanges["MSFT"] = frozenset({"NAS"})
    t = Transport()
    with pytest.raises(m.KisPaperMarketDataError):
        client(t).fetch_minute_page(
            replace(q, approved_symbol_exchanges={"AAPL": frozenset({"NAS"})})
        )
    assert t.requests == []


def test_no_cross_route_authority_or_future_timestamp():
    t = Transport()
    with pytest.raises(m.KisPaperMarketDataError):
        m.KisPaperMarketDataClient(
            config=m.KisPaperMarketDataConfig(app_key="x", app_secret="y"), transport=t
        ).fetch_minute_page(query())
    with pytest.raises(m.KisPaperMarketDataError):
        client(t).fetch_minute_page(m.KisPaperMinuteQuery(symbol="QQQ", exchange="NAS"))
    with pytest.raises(m.KisPaperMarketDataError):
        client(t).fetch_minute_page(query(key="20991015150000"))
    assert t.requests == []


def test_transport_scope_and_positional_legacy_fields():
    t = Transport()
    client(t).fetch_minute_page(query())
    r = t.requests[-1]
    for bad in [
        replace(r, historical_minute_query=None),
        replace(r, query={**r.query, "SYMB": "MSFT"}),
        replace(r, url=m.KIS_PAPER_MARKET_DATA_BASE_URL + "/account"),
        replace(r, url="https://example.invalid" + m.KIS_PAPER_MINUTE_PATH),
    ]:
        with pytest.raises(m.KisPaperMarketDataError):
            m._validate_request(bad)
    legacy = m.KisMarketDataRequest("GET", "x", {}, {}, None, SCOPE, frozenset({"0"}), None)
    assert legacy.daily_symbol_exchanges == SCOPE and legacy.stock_minute_query is None
    assert legacy.historical_minute_query is None


def test_job_owned_attempt_cap_and_legacy_iwm_default_unchanged():
    t = Transport()
    c = client(t, cap=1)
    c.fetch_minute_page(query())
    with pytest.raises(m.KisPaperMarketDataError, match="limit"):
        c.fetch_minute_page(query(key="20261015140000"))
    with pytest.raises(ValueError):
        m.KisPaperMinuteQuery(symbol="IWM", exchange="AMS", include_previous_day=True)
    assert t.requests[-1].query == dict(
        AUTH="", EXCD="NAS", SYMB="AAPL", NMIN="1", PINC="0", NREC="120", FILL="", KEYB="", NEXT=""
    )
