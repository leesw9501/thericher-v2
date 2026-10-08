from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from thericher_v2.data import kis_daily_price_endpoints as e
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperDailyQuery,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    _parse_daily_raw_row,
)

KEY, SECRET, TOKEN = "synthetic-key-canary", "synthetic-secret-canary", "synthetic-token-canary"


def query(symbol="GLD", exchange="AMS", by_date="20210820", continuation="F"):
    return KisPaperDailyQuery(
        symbol=symbol,
        exchange=exchange,
        by_date=by_date,
        continuation=continuation,
        approved_symbol_exchanges=e.SCOPE,
    )


def row(**changes):
    return {
        "xymd": "20210820",
        "open": "10.01",
        "high": "12",
        "low": "10.50",
        "clos": "10.02",
        "tvol": "123",
        **changes,
    }


def response(rows=None, **changes):
    payload = {"rt_cd": "0", "output1": {}, "output2": [row()] if rows is None else rows, **changes}
    return KisMarketDataResponse(200, {"tr_cont": "F"}, json.dumps(payload).encode())


def parse(rows=None, **changes):
    return e.parse_kis_daily_price_endpoints(response(rows, **changes), query=query())


def test_oc_eligibility_does_not_weaken_strict_bar_and_never_fabricates_low():
    source = row()
    before = dict(source)
    with pytest.raises(KisPaperMarketDataError, match="daily_response_invalid"):
        _parse_daily_raw_row(source)
    page = parse([source])
    assert source == before
    assert page.rows[0].open == "10.01" and page.rows[0].close == "10.02"
    assert page.rows[0].unused_ohlcv_faults == ("low_above_open_close",)
    assert page.safe_facts()["unused_ohlcv_fault_counts"] == {"low_above_open_close": 1}
    assert page.safe_facts()["strict_ohlcv_grade"] is False
    assert "10.01" not in repr(page) + repr(page.rows[0]) + repr(page.safe_facts())
    assert not hasattr(page.rows[0], "low") and not hasattr(page, "bars")


@pytest.mark.parametrize(
    "field,value",
    [
        ("open", "0"),
        ("clos", "-1"),
        ("open", "NaN"),
        ("clos", "Infinity"),
        ("open", ""),
        ("clos", None),
        ("open", 1),
        ("clos", "not-number"),
        ("xymd", "20210230"),
        ("xymd", "20210821"),
        ("xymd", "2021082"),
        ("xymd", 20210820),
    ],
)
def test_required_fields_and_calendar_fail_entire_exact_query(field, value):
    with pytest.raises(KisPaperMarketDataError):
        parse([row(**{field: value})])


@pytest.mark.parametrize(
    "changes,fault",
    [
        ({"high": "9"}, "high_below_open_close"),
        ({"high": None}, "unused_high_invalid"),
        ({"low": "NaN"}, "unused_low_invalid"),
        ({"tvol": "-1"}, "unused_tvol_invalid"),
        ({"tvol": None}, "unused_tvol_invalid"),
    ],
)
def test_unused_defects_remain_explicit_but_not_oc_permission_gate(changes, fault):
    assert fault in parse([row(**changes)]).rows[0].unused_ohlcv_faults


def test_empty_exact_query_has_no_rows_not_invalid_required_values():
    page = parse([])
    assert page.rows == () and page.source_row_count == 0
    with pytest.raises(KisPaperMarketDataError):
        parse([row(open="0")])


def test_duplicates_preserve_all_original_fingerprints_and_warning_union():
    a, b = row(low="1"), row(high="9")
    page = parse([a, b, a])
    assert len(page.rows) == 1 and page.source_row_count == 3 and page.duplicate_row_count == 2
    assert len(page.source_row_fingerprints) == 3
    assert page.source_row_fingerprints[0] != page.source_row_fingerprints[1]
    assert page.rows[0].provider_row_sha256 == page.source_row_fingerprints[0][1]
    assert set(page.rows[0].unused_ohlcv_faults) == {
        "high_below_open_close",
        "low_above_open_close",
    }
    with pytest.raises(KisPaperMarketDataError, match="endpoint_duplicate_conflict"):
        parse([a, row(clos="11")])


@pytest.mark.parametrize(
    "rows,changes",
    [
        ([row()] * 101, {}),
        ([None], {}),
        ([], {"output1": []}),
        ([], {"output2": "not-array"}),
        ([], {"rt_cd": "1"}),
    ],
)
def test_page_schema_failures_are_closed_categories(rows, changes):
    with pytest.raises(KisPaperMarketDataError):
        parse(rows, **changes)


@pytest.mark.parametrize("location", ["string", "escaped", "key", "nested"])
def test_known_credential_echo_rejects_before_retention_even_valid_prices(location):
    payload = {"rt_cd": "0", "output1": {}, "output2": [row()]}
    if location == "key":
        payload[SECRET] = "unused"
    elif location == "nested":
        payload["unused"] = [{"value": SECRET}]
    else:
        payload["unused"] = SECRET
    raw = json.dumps(payload).encode()
    if location == "escaped":
        raw = raw.replace(SECRET.encode(), ("".join(f"\\u{ord(c):04x}" for c in SECRET)).encode())
    with pytest.raises(KisPaperMarketDataError, match="credential_echo_rejected"):
        e.parse_kis_daily_price_endpoints(
            KisMarketDataResponse(200, {}, raw), query=query(), credential_values=(SECRET,)
        )


def test_frozen_types_reject_forged_inconsistent_metadata():
    page = parse()
    with pytest.raises(FrozenInstanceError):
        page.rows = ()
    with pytest.raises(KisPaperMarketDataError):
        replace(page.rows[0], open="0")
    with pytest.raises(KisPaperMarketDataError):
        replace(page, source_row_fingerprints=())
    with pytest.raises(KisPaperMarketDataError):
        replace(page, duplicate_row_count=True)
    duplicates = parse([row(), row(high="13")])
    forged = replace(
        duplicates.rows[0], provider_row_sha256=duplicates.source_row_fingerprints[1][1]
    )
    with pytest.raises(KisPaperMarketDataError, match="endpoint_page_invalid"):
        replace(duplicates, rows=(forged,))


def test_full_page_keeps_all_oc_rows_when_one_unused_low_is_invalid():
    rows = [row(xymd=f"202107{day:02d}", low="1") for day in range(1, 32)]
    rows += [row(xymd=f"202106{day:02d}", low="1") for day in range(1, 31)]
    rows += [row(xymd=f"202105{day:02d}", low="1") for day in range(1, 32)]
    rows += [row(xymd=f"202104{day:02d}", low="1") for day in range(1, 9)]
    rows[19]["low"] = "11"
    page = parse(rows)
    assert page.source_row_count == len(page.rows) == 100
    assert len(page.source_row_fingerprints) == 100 and page.duplicate_row_count == 0
    assert page.safe_facts()["unused_ohlcv_fault_counts"] == {"low_above_open_close": 1}


def test_rejected_dispatched_page_consumes_attempt_but_reuses_token():
    class Failing(Transport):
        def request(self, request):
            if request.method == "GET":
                self.requests.append(request)
                return response([row(open="0")])
            return super().request(request)

    transport = Failing()
    client = e.KisPaperDailyEndpointClient(
        config=KisPaperMarketDataConfig(app_key=KEY, app_secret=SECRET),
        transport=transport,
        max_daily_page_attempts=2,
    )
    for _ in range(2):
        with pytest.raises(KisPaperMarketDataError, match="endpoint_numeric_invalid"):
            client.fetch_daily_endpoint_page(query())
    assert client.call_counts.token_attempts == 1 and client.call_counts.daily_page_attempts == 2


class Transport:
    def __init__(self):
        self.requests = []

    def request(self, request):
        self.requests.append(request)
        if request.method == "POST":
            return KisMarketDataResponse(200, {}, json.dumps({"access_token": TOKEN}).encode())
        return response()


def test_one_token_reused_exact_headers_scope_counters_and_exhausted_limit():
    transport = Transport()
    client = e.KisPaperDailyEndpointClient(
        config=KisPaperMarketDataConfig(app_key=KEY, app_secret=SECRET),
        transport=transport,
        max_daily_page_attempts=2,
    )
    for symbol, venue in (("GLD", "AMS"), ("TLT", "NAS")):
        client.fetch_daily_endpoint_page(query(symbol, venue))
    assert client.call_counts.token_attempts == 1 and client.call_counts.daily_page_attempts == 2
    assert client.call_counts.minute_page_attempts == 0
    with pytest.raises(KisPaperMarketDataError, match="daily_page_limit_exceeded"):
        client.fetch_daily_endpoint_page(query())
    assert len(transport.requests) == 3
    first = transport.requests[1]
    assert first.url.endswith(KIS_PAPER_DAILY_PATH) and first.headers["tr_cont"] == "F"
    assert first.headers["authorization"] == "Bearer " + TOKEN
    assert first.query["MODP"] == "0" and first.daily_symbol_exchanges == e.SCOPE


@pytest.mark.parametrize(
    "path,method",
    [
        ("/uapi/overseas-stock/v1/trading/order", "POST"),
        ("/uapi/overseas-stock/v1/trading/inquire-balance", "GET"),
        ("/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice", "GET"),
    ],
)
def test_transport_rejects_accounts_orders_minute_without_wire(path, method):
    transport = e.KisPaperDailyEndpointTransport()
    with pytest.raises(KisPaperMarketDataError, match="request_not_allowlisted"):
        transport.request(KisMarketDataRequest(method, e.KIS_PAPER_MARKET_DATA_BASE_URL + path, {}))


def test_client_preserves_strict_parent_and_rejects_unsupported_scope_before_auth():
    transport = Transport()
    client = e.KisPaperDailyEndpointClient(
        config=KisPaperMarketDataConfig(app_key=KEY, app_secret=SECRET), transport=transport
    )
    with pytest.raises(KisPaperMarketDataError, match="endpoint_query_invalid"):
        client.fetch_daily_endpoint_page(
            KisPaperDailyQuery(symbol="QQQ", exchange="NAS", by_date="20210820")
        )
    assert not transport.requests
    with pytest.raises(KisPaperMarketDataError, match="daily_response_invalid"):
        client.fetch_daily_raw_page(query())
    assert transport.requests[0].url.endswith(KIS_PAPER_TOKEN_PATH)
