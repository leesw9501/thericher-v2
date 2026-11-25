import hashlib
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from thericher_v2.data.kis_paper_h3_capture import capture_h3_daily_panel_once
from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanelError,
    H3DailyPanelPlan,
    qualify_h3_daily_panel,
)
from thericher_v2.execution import kis_market_data as market
from thericher_v2.execution import kis_paper_data_capture as capture

AXIS = tuple((f"SYN{i:02}", ("NAS", "AMS", "NYS")[i % 3]) for i in range(18, -1, -1))


@pytest.fixture(scope="module")
def plan():
    return H3DailyPanelPlan(AXIS)


def _wire_rows(plan, offset, *, full_page=False):
    return [
        dict(
            xymd=day.strftime("%Y%m%d"),
            open=str(10 + offset),
            high=str(13 + offset),
            low=str(9 + offset),
            clos=str(11 + offset),
            tvol="100",
        )
        for day in reversed(plan.capture_sessions if full_page else plan.sessions)
    ]


def _bound_result(query, rows):
    native = json.dumps(rows).encode("ascii")
    return capture.CaptureResult(
        query.key, "ACCEPTED", len(rows), native={"sha256": hashlib.sha256(native).hexdigest()}
    ), native


def test_exact_dec3_plan(plan):
    assert len(plan.sessions) == 60
    assert plan.sessions[0] == date(2026, 9, 10)
    assert plan.sessions[-1] == date(2026, 12, 3)
    assert date(2026, 11, 26) not in plan.sessions
    assert date(2026, 11, 27) in plan.sessions
    assert plan.as_of_close_utc == datetime(2026, 12, 3, 21, tzinfo=UTC)
    assert H3DailyPanelPlan(AXIS, date(2026, 11, 27)).as_of_close_utc == datetime(
        2026, 11, 27, 18, tzinfo=UTC
    )
    assert len({query.key for query in plan.queries}) == 19
    for (symbol, venue), query in zip(AXIS, plan.queries, strict=True):
        assert type(query) is capture.CaptureQuery
        assert type(query.query) is market.KisPaperDailyAdjustmentProbeQuery
        assert (query.query.symbol, query.query.exchange) == (symbol, venue)
        assert len(plan.capture_sessions) == 100
        assert (query.first_date, query.last_date) == (
            plan.capture_sessions[0].strftime("%Y%m%d"),
            "20261203",
        )
        assert query.document()["parameters"] == dict(BYMD="20261203", MODP="1", continuation=None)
        assert query.document()["require_response_rsym"] is True
        assert query.query.approved_symbol_exchanges == {s: frozenset({v}) for s, v in AXIS}


def test_historical_model_axis_is_ordered_with_two_context_series():
    plan = H3DailyPanelPlan(NET25_H3_AXIS)
    assert tuple(symbol for symbol, _ in plan.axis) == tuple(
        "AAPL AMD AMZN GOOGL META MSFT NVDA TSLA JPM JNJ XOM PG KO HD V DIS UNH SPY QQQ".split()
    )
    assert plan.axis[-2:] == (("SPY", "AMS"), ("QQQ", "NAS"))


@pytest.mark.parametrize("axis", [AXIS[:-1], AXIS[:-1] + (AXIS[0],), (("syn", "NAS"),) + AXIS[1:]])
def test_axis_must_be_exact_and_unique(axis):
    with pytest.raises(H3DailyPanelError, match="h3_panel_axis_invalid"):
        H3DailyPanelPlan(axis)


def test_holiday_as_of_is_not_rolled_back():
    with pytest.raises(H3DailyPanelError, match="h3_panel_as_of_not_session"):
        H3DailyPanelPlan(AXIS, date(2026, 11, 26))


@pytest.mark.parametrize("wrong_identity", [False, True])
def test_native_capture_parser_to_full_panel(wrong_identity, tmp_path, monkeypatch):
    plan = H3DailyPanelPlan(NET25_H3_AXIS)
    tick = 0.0
    start = plan.as_of_close_utc + timedelta(minutes=10)

    def clock():
        return start + timedelta(seconds=tick)

    def sleep(seconds):
        nonlocal tick
        tick += seconds

    class Response:
        status = 200
        headers = {}

        def __init__(self, payload):
            self.body = json.dumps(payload).encode("ascii")

        def read(self, size):
            return self.body[:size]

        def close(self):
            pass

    calls = []

    class Opener:
        def open(self, request, timeout):
            parts = urlsplit(request.full_url)
            calls.append(request.get_method())
            if request.get_method() == "POST":
                assert parts.path == market.KIS_PAPER_TOKEN_PATH
                return Response({"access_token": "synthetic-h3-token"})
            assert parts.path == market.KIS_PAPER_DAILY_PATH
            query = parse_qs(parts.query)
            axis_index = len(calls) - 2
            symbol, venue = NET25_H3_AXIS[axis_index]
            assert query == {
                "SYMB": [symbol],
                "EXCD": [venue],
                "GUBN": ["0"],
                "BYMD": ["20261203"],
                "MODP": ["1"],
            }
            return Response(
                {
                    "rt_cd": "0",
                    "output1": {
                        "rsym": "DNASWRONG"
                        if wrong_identity and axis_index == 2
                        else f"D{venue}{symbol}"
                    },
                    "output2": _wire_rows(plan, axis_index, full_page=axis_index % 2 == 0),
                }
            )

    def no_network(*args, **kwargs):
        pytest.fail("real network forbidden")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr(capture, "_MARKET_BASE", tmp_path / "market")
    monkeypatch.setattr(capture, "_ARTIFACT_BASE", tmp_path / "artifacts")

    options = dict(
        plan=plan,
        market_root=tmp_path / "market/h3",
        artifact_root=tmp_path / "artifacts/h3",
        window_opens_utc=start,
        window_closes_utc=start + timedelta(minutes=2),
        owner_ready=lambda: capture.CaptureReadiness(True),
        config_loader=lambda: market.KisPaperMarketDataConfig(
            app_key="synthetic-h3-key", app_secret="synthetic-h3-secret"
        ),
        clock=clock,
        monotonic=lambda: tick,
        sleeper=sleep,
    )
    if wrong_identity:
        with pytest.raises(H3DailyPanelError, match="page_unavailable"):
            capture_h3_daily_panel_once(**options)
        assert calls == ["POST"] + ["GET"] * 3
        return

    closed = capture_h3_daily_panel_once(**options)
    panel = closed.panel
    assert (
        closed.state_sha256
        == hashlib.sha256(
            (options["artifact_root"] / "capture-state.json").read_bytes()
        ).hexdigest()
    )
    assert start <= closed.closed_at < options["window_closes_utc"]
    with pytest.raises(H3DailyPanelError, match="fresh_scope_required"):
        capture_h3_daily_panel_once(**options)

    assert calls == ["POST"] + ["GET"] * 19
    assert panel.plan is plan
    assert len(panel.rows) == 60 and all(len(row) == 19 for row in panel.rows)
    assert tuple(row[0].xymd for row in panel.rows) == tuple(
        day.strftime("%Y%m%d") for day in plan.sessions
    )
    assert tuple(row.clos for row in panel.rows[-1]) == tuple(str(11 + i) for i in range(19))
    assert panel.rows[0][0].as_document() == _wire_rows(plan, 0)[-1]


def test_h3_worker_refuses_outside_window_before_touching_storage(tmp_path):
    plan = H3DailyPanelPlan(NET25_H3_AXIS)
    opens = plan.as_of_close_utc + timedelta(minutes=30)
    closes = opens + timedelta(minutes=10)
    with pytest.raises(H3DailyPanelError, match="outside_window"):
        capture_h3_daily_panel_once(
            plan=plan,
            market_root=tmp_path / "market",
            artifact_root=tmp_path / "artifacts",
            window_opens_utc=opens,
            window_closes_utc=closes,
            clock=lambda: closes,
            owner_ready=lambda: pytest.fail("outside window"),
            config_loader=lambda: pytest.fail("outside window"),
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("short", "h3_panel_session_coverage"),
        ("missing_symbol", "h3_panel_missing_query"),
        ("missing_session_with_off_calendar_row", "h3_panel_session_coverage"),
        ("duplicate_session", "h3_panel_duplicate_session"),
        ("duplicate_symbol", "h3_panel_duplicate_query"),
        ("mixed_mode", "h3_panel_query_mismatch"),
        ("mixed_as_of", "h3_panel_query_mismatch"),
        ("mixed_venue", "h3_panel_query_mismatch"),
        ("swapped_native_bytes", "h3_panel_native_digest_mismatch"),
        ("bad_ohlc", "h3_panel_native_ohlcv_invalid"),
        ("mixed_schema", "h3_panel_native_schema_invalid"),
        ("nonaccepted", "h3_panel_capture_not_accepted"),
        ("mismatched_count", "h3_panel_native_count_mismatch"),
        ("extra_old_row", "h3_panel_session_coverage"),
    ],
)
def test_rejects_incomplete_or_mixed_capture(plan, case, error):
    rows = _wire_rows(plan, 0)
    if case == "short":
        rows.pop(10)
    elif case == "missing_session_with_off_calendar_row":
        rows[1]["xymd"] = "20261126"
    elif case == "duplicate_session":
        rows[1] = rows[0]
    elif case == "bad_ohlc":
        rows[0]["high"] = "1"
    elif case == "mixed_schema":
        rows[0]["xhms"] = "123456"
    elif case == "extra_old_row":
        rows.append(dict(rows[-1], xymd="20260601"))
    query = plan.queries[0]
    if case == "mixed_mode":
        query = replace(query, query=replace(query.query, adjustment_mode="0"))
    elif case == "mixed_as_of":
        query = H3DailyPanelPlan(AXIS, date(2026, 12, 2)).queries[0]
    elif case == "mixed_venue":
        query = H3DailyPanelPlan(((AXIS[0][0], "NYS"), *AXIS[1:])).queries[0]
    result, native = _bound_result(query, rows)
    if case == "nonaccepted":
        result = replace(result, status="REJECTED")
    elif case == "mismatched_count":
        result = replace(result, row_count=59)
    elif case == "swapped_native_bytes":
        _, native = _bound_result(plan.queries[1], _wire_rows(plan, 1))
    captures = [(result, native)] + [
        _bound_result(query, _wire_rows(plan, i)) for i, query in enumerate(plan.queries[1:], 1)
    ]
    if case == "missing_symbol":
        captures.pop()
    elif case == "duplicate_symbol":
        captures[-1] = captures[0]
    with pytest.raises(H3DailyPanelError, match=error):
        qualify_h3_daily_panel(plan, captures)
