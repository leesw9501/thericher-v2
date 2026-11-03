from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.data.kis_historical_capture import (
    CaptureIssue,
    RawMinuteClock,
    UnqualifiedHistoricalCaptureError,
    assess_historical_capture,
)
from thericher_v2.execution import kis_market_data as market

NY = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")


def labels(stamp="20261029155900", offset=0):
    local = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=NY)
    korea = local.astimezone(KST) + timedelta(seconds=offset)
    return RawMinuteClock(local.strftime("%Y%m%d"), local.strftime("%H%M%S"),
                          korea.strftime("%Y%m%d"), korea.strftime("%H%M%S"))


def assess(rows, key="20261029155900"):
    return assess_historical_capture(
        rows, requested_key=key, exchange_timezone=NY, korea_timezone=KST,
    )


@pytest.mark.parametrize("offset", [0, 3600, -3600, 1800])
def test_raw_retention_advances_without_repair_or_promotion(offset):
    raw = labels(offset=offset)
    result = assess([raw])
    assert result.rows[0].raw is raw
    assert result.rows[0].raw == raw
    assert result.rows[0].korea_minus_exchange_seconds == offset
    assert result.rows[0].exchange_label_utc == datetime(2026, 10, 29, 19, 59, tzinfo=UTC)
    assert result.cursor_can_advance
    assert result.next_exchange_key == "20261029155800"
    assert result.captured_count == 1 and result.qualified_count == 0
    assert result.training_eligible is False
    assert result.exchange_clock_asserted is True
    assert result.clock_basis == "exchange_local_label_proxy"
    with pytest.raises(UnqualifiedHistoricalCaptureError):
        result.require_qualified()
    with pytest.raises(FrozenInstanceError):
        raw.korea_time = "000000"


@pytest.mark.parametrize("bad", [None, "", "not-time", "256100"])
def test_missing_or_bad_secondary_clock_is_quality_not_cursor_gate(bad):
    raw = replace(labels(), korea_time=bad)
    result = assess([raw])
    assert result.cursor_can_advance
    assert result.korea_unavailable_count == 1
    assert CaptureIssue.KOREA_CLOCK_UNAVAILABLE in result.issues
    assert result.rows[0].raw.korea_time == bad
    assert result.qualified_count == 0


def test_mixed_korea_offsets_are_not_hardcoded_one_hour():
    result = assess([labels("20261029155900", 3600), labels("20261029155800", 0)])
    assert result.cursor_can_advance
    assert result.korea_mismatch_count == 1
    assert [r.korea_minus_exchange_seconds for r in result.rows] == [3600, 0]


@pytest.mark.parametrize("field,value", [
    ("exchange_date", None), ("exchange_date", "20260230"),
    ("exchange_time", "246000"), ("exchange_time", " 155900"),
    ("exchange_time", "１５５９００"),
])
def test_bad_exchange_clock_closes_only_exact_cursor(field, value):
    result = assess([replace(labels(), **{field: value})])
    assert not result.cursor_can_advance and result.next_exchange_key is None
    assert result.cursor_action == "close_exact_cursor"
    assert CaptureIssue.MALFORMED_EXCHANGE_CLOCK in result.issues
    assert assess([labels()]).cursor_can_advance


@pytest.mark.parametrize("stamp,issue", [
    ("20261101013000", CaptureIssue.AMBIGUOUS_EXCHANGE_CLOCK),
    ("20260308023000", CaptureIssue.NONEXISTENT_EXCHANGE_CLOCK),
])
def test_dst_ambiguous_and_nonexistent_exchange_labels_are_not_guessed(stamp, issue):
    raw = RawMinuteClock(stamp[:8], stamp[8:], None, None)
    result = assess([raw], key=None)
    assert not result.cursor_can_advance
    assert result.rows[0].exchange_label_utc is None
    assert issue in result.issues
    assert result.rows[0].raw is raw


def test_exchange_proxy_tracks_real_dst_without_modifying_korea_labels():
    before = assess([labels("20261030155900")], "20261030155900")
    after = assess([labels("20261102155900")], "20261102155900")
    assert before.rows[0].exchange_label_utc.hour == 19
    assert after.rows[0].exchange_label_utc.hour == 20
    assert before.korea_mismatch_count == after.korea_mismatch_count == 0


@pytest.mark.parametrize("rows,issue", [
    ([labels(), labels()], CaptureIssue.DUPLICATE_EXCHANGE_STAMP),
    ([labels("20261029155900"), labels("20261029155700"), labels("20261029155800")],
     CaptureIssue.NON_MONOTONIC_EXCHANGE_STAMPS),
    ([labels("20261029160000")], CaptureIssue.NEWER_THAN_REQUEST_KEY),
])
def test_duplicate_order_and_max_key_checks_stay_strict(rows, issue):
    result = assess(rows)
    assert not result.cursor_can_advance and result.next_exchange_key is None
    assert issue in result.issues
    assert result.captured_count == len(rows) and result.qualified_count == 0


@pytest.mark.parametrize("key", ["bad", "20260230093000", "20261101013000", "20260308023000"])
def test_invalid_or_ambiguous_query_key_does_not_advance(key):
    result = assess([labels()], key)
    assert CaptureIssue.INVALID_REQUEST_KEY in result.issues
    assert not result.cursor_can_advance


def test_empty_is_exact_cursor_evidence_not_source_floor():
    result = assess([])
    assert result.captured_count == result.qualified_count == 0
    assert result.issues == frozenset({CaptureIssue.EMPTY_PAGE})
    assert not result.cursor_can_advance


def test_both_monotonic_directions_are_measured_without_reordering_raw():
    rows = [labels("20261029155800"), labels("20261029155900")]
    result = assess(rows)
    assert result.cursor_can_advance and result.exchange_ascending
    assert not result.exchange_descending
    assert [row.raw for row in result.rows] == rows
    assert result.next_exchange_key == "20261029155700"


def test_real_native_parser_to_assessment_keeps_old_strict_sdk_unchanged():
    scope = {"AMD": frozenset({"NAS"})}
    raw_clock = labels(offset=3600)
    payload = dict(rt_cd="0", output1={}, output2=[dict(
        xymd=raw_clock.exchange_date, xhms=raw_clock.exchange_time,
        kymd=raw_clock.korea_date, khms=raw_clock.korea_time,
        open="100", high="102", low="99", last="101", evol="1",
    )])

    class InventedTransport:
        def __init__(self):
            self.calls = []
            self.parsed = None

        def request(self, request):
            self.calls.append(request)
            if request.method == "POST":
                return market.KisMarketDataResponse.from_payload({"access_token": "invented"})
            self.parsed = market._parse_minute_bar(payload["output2"][0])
            return market.KisMarketDataResponse.from_payload(payload)

    transport = InventedTransport()
    client = market.KisPaperMarketDataClient(
        config=market.KisPaperMarketDataConfig(app_key="invented", app_secret="invented"),
        transport=transport, minute_route="historical_timestamp", minute_symbol_exchanges=scope,
    )
    query = market.KisPaperHistoricalMinuteQuery(
        symbol="AMD", exchange="NAS", continuation_key="20261029155900",
        include_previous_day=True, continuation_next="1", approved_symbol_exchanges=scope,
    )
    with pytest.raises(market.KisPaperMarketDataError, match="historical_minute_clock_mismatch"):
        client.fetch_minute_page(query)
    parsed = transport.parsed
    result = assess([RawMinuteClock(
        parsed.exchange_date, parsed.exchange_time, parsed.korea_date, parsed.korea_time,
    )])
    assert result.cursor_can_advance and result.korea_mismatch_count == 1
    assert result.qualified_count == 0 and result.rows[0].raw == raw_clock
    assert [request.method for request in transport.calls] == ["POST", "GET"]
    assert query.continuation_key == "20261029155900"
    assert market.KIS_PAPER_MARKET_DATA_BASE_URL == "https://openapivts.koreainvestment.com:29443"
    with pytest.raises(ValueError):
        market.KisPaperMinuteQuery(symbol="IWM", exchange="AMS", include_previous_day=True)
