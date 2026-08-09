from __future__ import annotations

import ast
import json
import re
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode

import pytest

from thericher_v2.contracts import Bar, OrderIntent, Timeframe
from thericher_v2.dashboard import server as dashboard_server
from thericher_v2.dashboard.server import DashboardServer
from thericher_v2.dashboard.view import DashboardPosition, build_snapshot, render_dashboard
from thericher_v2.execution import EmergencyStore, LocalPaperBroker
from thericher_v2.execution.kis_paper_console_bridge import run_kis_paper_console_bridge
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KisHttpRequest,
    KisHttpResponse,
)
from thericher_v2.execution.paper_account_snapshot import (
    PAPER_ACCOUNT_SNAPSHOT_TTL,
    PaperAccountOpenOrder,
    PaperAccountOrderableForeignFunds,
    PaperAccountPosition,
    PaperAccountReferenceOrderability,
    PaperAccountSnapshot,
    write_paper_account_snapshot,
)
from thericher_v2.execution.paper_canary_runtime import (
    PAPER_CANARY_RUNTIME_TTL,
    PaperCanaryRuntimeSnapshot,
    write_paper_canary_runtime,
)
from thericher_v2.state import Event, EventStore


@contextmanager
def _dashboard(
    tmp_path: Path,
    *,
    token: str = "",
    paper_account_snapshot_path: Path | None = None,
):
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")
    server = DashboardServer(
        ("127.0.0.1", 0),
        event_store=events,
        emergency_store=emergency,
        token=token,
        mode="off",
        paper_account_snapshot_path=paper_account_snapshot_path,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, events, emergency
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _request(
    server: DashboardServer,
    method: str,
    path: str,
    *,
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, list[tuple[str, str]], str]:
    host, port = server.server_address[:2]
    connection = HTTPConnection(host, port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.getheaders(), response.read().decode("utf-8")
    finally:
        connection.close()


def _cookies(headers: list[tuple[str, str]]) -> str:
    return "; ".join(
        value.split(";", 1)[0]
        for name, value in headers
        if name.lower() == "set-cookie"
    )


def _nonce(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _bar(start_ts: datetime, open_price: str) -> Bar:
    price = Decimal(open_price)
    return Bar(
        symbol="SPY",
        market="NAS",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price,
        volume=Decimal("100"),
    )


def _record_local_fill(events: EventStore, emergency: EmergencyStore) -> None:
    signal_bar = _bar(datetime(2026, 7, 20, 14, 30, tzinfo=UTC), "10")
    execution_bar = _bar(signal_bar.start_ts + timedelta(minutes=1), "11")
    broker = LocalPaperBroker(
        event_store=events,
        emergency_store=emergency,
        starting_cash=Decimal("1000"),
        fee_bps=Decimal("10"),
    )
    result = broker.submit_and_fill_next_bar(
        OrderIntent(
            client_order_id="dashboard-local-fill",
            symbol="SPY",
            market="NAS",
            side="buy",
            quantity=Decimal("2"),
            limit_price=None,
            decision_id="dashboard-decision",
            created_at=signal_bar.end_ts,
        ),
        signal_bar=signal_bar,
        execution_bar=execution_bar,
    )
    assert result.fill is not None


def test_snapshot_uses_allowlisted_local_paper_replay_and_escapes_html(tmp_path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")
    _record_local_fill(events, emergency)
    events.append(
        Event(
            event_type="fill",
            created_at=datetime(2026, 7, 20, 14, 32, tzinfo=UTC),
            payload={
                "source": "in_memory_broker",
                "market": "NAS",
                "symbol": "SHOULD_NOT_RENDER",
                "side": "buy",
                "quantity": "99",
                "price": "1",
                "fee": "0",
            },
        )
    )
    events.append(
        Event(
            event_type="ensemble_decision",
            created_at=datetime(2026, 7, 20, 14, 33, tzinfo=UTC),
            payload={
                "source": "validation",
                "market": "NAS",
                "symbol": "<script>alert(1)</script>",
                "action": "hold",
                "confidence": "0.5",
                "expected_edge_bps": "0",
            },
        )
    )

    snapshot = build_snapshot(events, emergency)

    assert snapshot.local_paper_status == "local_paper_replayed"
    assert snapshot.local_paper_fill_count == 1
    assert snapshot.local_paper_cash == "977.9780"
    actual_positions = [
        (position.market, position.symbol, position.quantity)
        for position in snapshot.local_positions
    ]
    assert actual_positions == [("NAS", "SPY", "2")]
    assert snapshot.local_paper_pnl_status == "No closed local fills"
    assert snapshot.kis_holdings_status == "unknown"
    assert snapshot.latest_decisions[0].source == "validation"

    from thericher_v2.dashboard.view import render_dashboard

    html = render_dashboard(snapshot, form_nonce="form-nonce")
    assert "SHOULD_NOT_RENDER" not in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;SCRIPT&gt;ALERT(1)&lt;/SCRIPT&gt;" in html
    assert "KIS holdings" in html
    assert ">unknown<" in html
    assert "form-nonce" in html


def test_snapshot_reports_only_closed_local_paper_fifo_pnl(tmp_path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")
    _record_local_fill(events, emergency)
    broker = LocalPaperBroker(
        event_store=events,
        emergency_store=emergency,
        starting_cash=Decimal("1000"),
        fee_bps=Decimal("10"),
    )
    signal_bar = _bar(datetime(2026, 7, 20, 14, 31, tzinfo=UTC), "11")
    execution_bar = _bar(datetime(2026, 7, 20, 14, 32, tzinfo=UTC), "12")
    sell = broker.submit_and_fill_next_bar(
        OrderIntent(
            client_order_id="dashboard-local-sell",
            symbol="SPY",
            market="NAS",
            side="sell",
            quantity=Decimal("1"),
            limit_price=None,
            decision_id="dashboard-reduction",
            created_at=signal_bar.end_ts,
        ),
        signal_bar=signal_bar,
        execution_bar=execution_bar,
    )
    assert sell.fill is not None

    snapshot = build_snapshot(events, emergency)

    assert snapshot.local_paper_pnl_status == "0.9770"
    assert snapshot.local_paper_cash == "989.9660"
    assert snapshot.local_positions == (DashboardPosition("NAS", "SPY", "1"),)
    assert "0.9770" in render_dashboard(snapshot, form_nonce="form-nonce")


def test_snapshot_fails_closed_for_an_oversold_local_paper_history(tmp_path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")
    events.append(
        Event(
            event_type="fill",
            created_at=datetime(2026, 7, 20, 14, 30, tzinfo=UTC),
            payload={
                "source": "local_paper",
                "market": "NAS",
                "symbol": "SPY",
                "side": "sell",
                "quantity": "1",
                "price": "11",
                "fee": "0",
            },
        )
    )

    snapshot = build_snapshot(events, emergency)

    assert snapshot.status == "local_monitor_degraded"
    assert snapshot.local_paper_status == "local_paper_replay_unavailable"
    assert snapshot.local_paper_pnl_status == "Unavailable"


def test_empty_and_malformed_local_event_logs_remain_distinct(tmp_path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")

    empty_snapshot = build_snapshot(events, emergency)
    assert empty_snapshot.status == "local_monitor_only"
    assert empty_snapshot.local_paper_status == "no_local_paper_activity"
    assert empty_snapshot.position_count == 0
    assert empty_snapshot.local_paper_cash is None
    assert empty_snapshot.local_paper_pnl_status == "Unavailable"

    events.jsonl_path.write_text("{not-json}\n", encoding="utf-8")
    malformed_snapshot = build_snapshot(events, emergency)
    assert malformed_snapshot.status == "local_monitor_degraded"
    assert malformed_snapshot.local_paper_status == "local_paper_replay_unavailable"
    assert malformed_snapshot.position_count is None
    assert malformed_snapshot.local_paper_fill_count is None
    assert malformed_snapshot.latest_decision_count is None
    assert malformed_snapshot.to_dict()["local_positions"] is None
    assert malformed_snapshot.to_dict()["local_paper_fills"] is None
    assert malformed_snapshot.to_dict()["latest_decisions"] is None
    assert malformed_snapshot.kis_open_orders_status == "unknown"

    from thericher_v2.dashboard.view import render_dashboard

    html = render_dashboard(malformed_snapshot, form_nonce="form-nonce")
    assert "Local replay unavailable" in html
    assert "No local positions" not in html


def test_dashboard_state_marks_a_corrupt_replay_unavailable(tmp_path) -> None:
    with _dashboard(tmp_path) as (server, events, _emergency):
        events.jsonl_path.write_text("{not-json}\n", encoding="utf-8")

        status, _, state_body = _request(server, "GET", "/state")

    state = json.loads(state_body)
    assert status == 200
    assert state["status"] == "local_monitor_degraded"
    assert state["position_count"] is None
    assert state["local_paper_fill_count"] is None
    assert state["latest_decision_count"] is None
    assert state["local_positions"] is None
    assert state["local_paper_fills"] is None
    assert state["latest_decisions"] is None


def test_dashboard_renders_only_a_fresh_sanitized_paper_account_snapshot(tmp_path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")
    observed_at = datetime(2026, 7, 20, 14, 30, tzinfo=UTC)
    paper_snapshot_path = tmp_path / "paper_account_snapshot.json"
    write_paper_account_snapshot(
        PaperAccountSnapshot(
            status="complete",
            observed_at=observed_at,
            expires_at=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL,
            orderable_foreign_funds=PaperAccountOrderableForeignFunds(
                "USD", Decimal("1200.50")
            ),
            reference_orderability=PaperAccountReferenceOrderability(
                "USD",
                Decimal("1199.75"),
                "NASD",
                "SPY",
            ),
            positions=(PaperAccountPosition("NASD", "SPY", "USD", Decimal("2")),),
            open_orders=(
                PaperAccountOpenOrder(
                    "NASD",
                    "SPY",
                    "USD",
                    "buy",
                    Decimal("5"),
                    Decimal("2"),
                    Decimal("3"),
                ),
            ),
        ),
        paper_snapshot_path,
    )

    snapshot = build_snapshot(
        events,
        emergency,
        paper_account_snapshot_path=paper_snapshot_path,
        now=observed_at + timedelta(minutes=1),
    )

    assert snapshot.paper_account_status == "available"
    assert snapshot.paper_account is not None
    assert snapshot.kis_holdings_status == "available"
    assert snapshot.kis_prices_status == "unknown"
    assert snapshot.kis_buying_power_status == "reference_only"
    assert snapshot.kis_open_orders_status == "available"
    state = snapshot.to_dict()
    assert "12345678" not in json.dumps(state)
    assert "order_reference" not in json.dumps(state)
    assert "reference_price" not in json.dumps(state)
    assert "limit_price" not in json.dumps(state)

    from thericher_v2.dashboard.view import render_dashboard

    html = render_dashboard(snapshot, form_nonce="form-nonce")
    assert "KIS orderable foreign funds" in html
    assert "Reference orderability" in html
    assert "KIS positions" in html
    assert "KIS price quotes" in html
    assert "general buying power" in html
    assert "Limit</th>" not in html

    stale_snapshot = build_snapshot(
        events,
        emergency,
        paper_account_snapshot_path=paper_snapshot_path,
        now=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL + timedelta(seconds=1),
    )
    assert stale_snapshot.paper_account_status == "unavailable"
    assert stale_snapshot.paper_account is None
    assert stale_snapshot.kis_holdings_status == "unavailable"


def test_dashboard_state_preserves_canonical_paper_account_envelope(tmp_path) -> None:
    observed_at = datetime.now(UTC)
    paper_snapshot_path = tmp_path / "paper_account_snapshot.json"
    account = PaperAccountSnapshot(
        status="complete",
        observed_at=observed_at,
        expires_at=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL,
        orderable_foreign_funds=PaperAccountOrderableForeignFunds("USD", Decimal("1200.50")),
        reference_orderability=PaperAccountReferenceOrderability(
            "USD",
            Decimal("1199.75"),
            "NASD",
            "SPY",
        ),
        positions=(PaperAccountPosition("NASD", "SPY", "USD", Decimal("2")),),
    )
    write_paper_account_snapshot(account, paper_snapshot_path)

    with _dashboard(
        tmp_path,
        paper_account_snapshot_path=paper_snapshot_path,
    ) as (server, _events, _emergency):
        status, _, state_body = _request(server, "GET", "/state")

    state = json.loads(state_body)
    assert status == 200
    assert state["paper_account"] == account.to_dict()
    assert state["paper_account"]["source"] == "kis_paper"
    assert state["paper_account"]["read_only"] is True
    assert state["paper_account"]["submission_capability"] is False
    assert "account_number" not in json.dumps(state["paper_account"])


def test_dashboard_http_hides_a_malformed_paper_account_snapshot(tmp_path) -> None:
    paper_snapshot_path = tmp_path / "paper_account_snapshot.json"
    raw_marker = "raw-broker-body-must-not-reach-dashboard"
    paper_snapshot_path.write_text(
        json.dumps({"unexpected": raw_marker}),
        encoding="utf-8",
    )

    with _dashboard(
        tmp_path,
        paper_account_snapshot_path=paper_snapshot_path,
    ) as (server, _events, _emergency):
        status, _, state_body = _request(server, "GET", "/state")

    state = json.loads(state_body)
    assert status == 200
    assert state["paper_account_status"] == "unavailable"
    assert state["paper_account"] is None
    assert state["kis_holdings_status"] == "unavailable"
    assert state["kis_prices_status"] == "unavailable"
    assert state["kis_buying_power_status"] == "unavailable"
    assert state["kis_open_orders_status"] == "unavailable"
    assert raw_marker not in json.dumps(state)


def test_dashboard_hides_prior_account_facts_after_a_rejected_bridge_refresh(tmp_path) -> None:
    observed_at = datetime.now(UTC)
    paper_snapshot_path = tmp_path / "paper_account_snapshot.json"
    write_paper_account_snapshot(
        PaperAccountSnapshot(
            status="complete",
            observed_at=observed_at,
            expires_at=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL,
            orderable_foreign_funds=PaperAccountOrderableForeignFunds(
                "USD", Decimal("1200.50")
            ),
            reference_orderability=PaperAccountReferenceOrderability(
                "USD",
                Decimal("1199.75"),
                "NASD",
                "SPY",
            ),
            positions=(PaperAccountPosition("NASD", "SPY", "USD", Decimal("2")),),
        ),
        paper_snapshot_path,
    )

    raw_marker = "raw-broker-body-12345678-must-not-reach-dashboard"

    class RejectedBridgeTransport:
        def __init__(self) -> None:
            self.requests: list[KisHttpRequest] = []

        def request(self, request: KisHttpRequest) -> KisHttpResponse:
            self.requests.append(request)
            if request.method == "POST":
                return KisHttpResponse.from_payload({"access_token": "temporary-access-token"})
            assert request.headers["tr_id"] == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id
            return KisHttpResponse.from_payload(
                {"rt_cd": "1", "msg_cd": "RAW", "msg1": raw_marker},
                status_code=403,
            )

    transport = RejectedBridgeTransport()
    outcome = run_kis_paper_console_bridge(
        environment={
            "KIS_PAPER_APP_KEY": "test-app-key",
            "KIS_PAPER_APP_SECRET": "test-app-secret",
            "KIS_PAPER_ACCOUNT_NO": "12345678",
            "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
            "KIS_LIVE_APP_KEY": "live-secret-must-not-be-read",
        },
        runtime_snapshot_path=paper_snapshot_path,
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        transport=transport,
        clock=lambda: observed_at,
    )

    assert outcome.status == "unavailable"
    assert outcome.reason_code == "open_orders_rejected"
    assert [request.method for request in transport.requests] == ["POST", "GET"]
    assert transport.requests[1].headers["tr_id"] == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id

    with _dashboard(
        tmp_path,
        paper_account_snapshot_path=paper_snapshot_path,
    ) as (server, _events, _emergency):
        state_status, _, state_body = _request(server, "GET", "/state")
        html_status, _, html = _request(server, "GET", "/")

    state = json.loads(state_body)
    assert state_status == 200
    assert html_status == 200
    assert state["paper_account_status"] == "unavailable"
    assert state["paper_account"] is None
    assert state["kis_holdings_status"] == "unavailable"
    assert state["kis_open_orders_status"] == "unavailable"
    assert "KIS snapshot unavailable" in html
    assert raw_marker not in state_body
    assert raw_marker not in html
    assert "1200.50" not in state_body
    assert "1200.50" not in html


def test_dashboard_reads_only_a_fresh_sanitized_virtual_canary_projection(tmp_path: Path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")
    observed_at = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)
    canary_path = tmp_path / "kis_paper_canary.json"
    write_paper_canary_runtime(
        PaperCanaryRuntimeSnapshot(
            run_id="canary-1",
            status="cancelled",
            reconciliation_status="clean",
            account_status="available",
            position_count=0,
            open_order_count=0,
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            observed_at=observed_at,
            expires_at=observed_at + PAPER_CANARY_RUNTIME_TTL,
            order_reference="canary-0123456789abcdef",
            reconciliation_reason_code="auth_rejected",
        ),
        canary_path,
    )

    snapshot = build_snapshot(
        events,
        emergency,
        paper_canary_runtime_path=canary_path,
        now=observed_at + timedelta(minutes=1),
    )

    assert snapshot.paper_canary_status == "cancelled"
    assert snapshot.paper_canary_reconciliation_status == "clean"
    assert snapshot.paper_canary_reconciliation_reason_code == "auth_rejected"
    assert snapshot.paper_canary_account_status == "available"
    state = json.dumps(snapshot.to_dict())
    assert "paper-app-secret" not in state
    assert "raw-order-12345678" not in state

    from thericher_v2.dashboard.view import render_dashboard

    html = render_dashboard(snapshot, form_nonce="form-nonce")
    assert "Virtual-paper canary" in html
    assert "Canary reconciliation" in html
    assert "Reconciliation detail: auth_rejected." in html


def test_dashboard_http_html_json_and_local_actions(tmp_path) -> None:
    with _dashboard(tmp_path) as (server, events, emergency):
        _record_local_fill(events, emergency)
        event_bytes = events.jsonl_path.read_bytes()

        status, headers, html = _request(server, "GET", "/")
        assert status == 200
        assert ("Content-Type", "text/html; charset=utf-8") in headers
        assert "Local paper console" in html
        assert "KIS broker state" in html
        assert "Pause buys" in html
        assert "Pause sells" in html
        cookie_header = _cookies(headers)
        nonce = _nonce(html)

        status, _, state_body = _request(server, "GET", "/state")
        assert status == 200
        state = json.loads(state_body)
        assert state["local_paper_fill_count"] == 1
        assert state["kis_prices_status"] == "unknown"
        assert state["pause_buys"] is False
        assert state["pause_sells"] is False

        status, _, _ = _request(server, "POST", "/controls/pause-buys")
        assert status == 403
        assert events.jsonl_path.read_bytes() == event_bytes
        assert not server.execution_control_store.read().pause_buys

        form = urlencode({"csrf": nonce})
        form_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": cookie_header,
        }
        status, _, action_body = _request(
            server,
            "POST",
            "/controls/pause-buys",
            body=form,
            headers=form_headers,
        )
        assert status == 200
        assert json.loads(action_body)["status"] == "pause_buys_set"
        assert server.execution_control_store.read().pause_buys
        assert events.jsonl_path.read_bytes() == event_bytes

        status, _, action_body = _request(
            server,
            "POST",
            "/controls/pause-sells",
            body=form,
            headers=form_headers,
        )
        assert status == 200
        assert json.loads(action_body)["status"] == "pause_sells_set"
        controls = server.execution_control_store.read()
        assert controls.pause_buys and controls.pause_sells
        assert events.jsonl_path.read_bytes() == event_bytes

        status, _, action_body = _request(
            server,
            "POST",
            "/controls/resume-buys",
            body=form,
            headers=form_headers,
        )
        assert status == 200
        assert json.loads(action_body)["status"] == "pause_buys_cleared"
        controls = server.execution_control_store.read()
        assert not controls.pause_buys and controls.pause_sells
        assert events.jsonl_path.read_bytes() == event_bytes

        status, _, state_body = _request(server, "GET", "/state")
        assert status == 200
        state = json.loads(state_body)
        assert state["pause_buys"] is False
        assert state["pause_sells"] is True

        status, _, action_body = _request(
            server,
            "POST",
            "/emergency/stop-new-orders",
            body=form,
            headers=form_headers,
        )
        assert status == 200
        assert json.loads(action_body)["status"] == "stop_new_orders_set"
        assert emergency.read().stop_new_orders
        assert events.jsonl_path.read_bytes() == event_bytes

        status, _, _ = _request(
            server,
            "POST",
            "/emergency/cancel-open-orders",
            body=form,
            headers=form_headers,
        )
        assert status == 404
        state = emergency.read()
        assert state.stop_new_orders
        assert not state.cancel_open_orders_requested
        assert events.jsonl_path.read_bytes() == event_bytes

        status, _, _ = _request(
            server,
            "POST",
            "/emergency/stop-new-orders",
            body=form,
            headers={
                **form_headers,
                "Origin": "https://untrusted.example",
            },
        )
        assert status == 403


def test_configured_dashboard_token_protects_html_json_and_actions(tmp_path) -> None:
    with _dashboard(tmp_path, token="dashboard-test-token") as (server, _events, emergency):
        status, headers, _ = _request(server, "GET", "/")
        assert status == 303
        assert ("Location", "/login") in headers

        status, _, body = _request(server, "GET", "/state")
        assert status == 401
        assert json.loads(body) == {"error": "unauthorized"}

        status, _, html = _request(
            server,
            "GET",
            "/",
            headers={"Authorization": "Bearer dashboard-test-token"},
        )
        assert status == 200
        assert "dashboard-test-token" not in html

        status, _, body = _request(
            server,
            "GET",
            "/state",
            headers={"Authorization": "Bearer dashboard-test-token"},
        )
        assert status == 200
        assert json.loads(body)["mode"] == "off"

        status, login_headers, _ = _request(
            server,
            "POST",
            "/login",
            body=urlencode({"token": "dashboard-test-token"}),
            headers={
                "Accept": "text/html",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        assert status == 303
        session_cookies = _cookies(login_headers)
        assert "dashboard-test-token" not in session_cookies

        status, _, html = _request(server, "GET", "/", headers={"Cookie": session_cookies})
        assert status == 200
        nonce = _nonce(html)

        status, _, _ = _request(
            server,
            "POST",
            "/emergency/stop-new-orders",
            body=urlencode({"csrf": nonce}),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": session_cookies,
            },
        )
        assert status == 200
        assert emergency.read().stop_new_orders


def test_dashboard_has_no_kis_client_dependency_and_compose_web_is_loopback_bound() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    server_source = (repo_root / "src" / "thericher_v2" / "dashboard" / "server.py").read_text(
        encoding="utf-8"
    )
    module = ast.parse(server_source)
    imports = [
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        node.module or ""
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any("kis" in module_name.lower() for module_name in imports)

    view_source = (repo_root / "src" / "thericher_v2" / "dashboard" / "view.py").read_text(
        encoding="utf-8"
    )
    view_module = ast.parse(view_source)
    view_imports = [
        alias.name
        for node in ast.walk(view_module)
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        node.module or ""
        for node in ast.walk(view_module)
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any("kis_paper_intraday" in module_name for module_name in view_imports)
    assert not any("kis_market_data" in module_name for module_name in view_imports)

    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    engine_section = compose.split("\n  engine:\n", maxsplit=1)[1].split(
        "\n  web:\n", maxsplit=1
    )[0]
    web_section = compose.split("\n  web:\n", maxsplit=1)[1].split(
        "\n  research:\n", maxsplit=1
    )[0]
    assert '"127.0.0.1:8787:8787"' in web_section
    assert "--allow-container-bind" in web_section
    assert "KIS_" not in web_section
    assert "TIINGO" not in web_section
    assert "market_data" not in web_section
    assert "thericher-v2-runtime:/app/runtime" in engine_section
    assert "thericher-v2-runtime:/app/runtime:ro" in web_section
    assert "thericher-v2-web-emergency:/app/emergency" in web_section
    assert "paper_execution_control.json" in web_section
    assert "kis_paper_intraday_freshness.json" in web_section

    kis_section = compose.split("\n  kis-readonly:\n", maxsplit=1)[1].split(
        "\n  kis-paper-canary:\n", maxsplit=1
    )[0]
    assert "profiles: [\"kis-readonly\"]" in kis_section
    assert "KIS_PAPER_APP_KEY" in kis_section
    assert "KIS_LIVE" not in kis_section
    assert ".env" not in kis_section
    assert "read_only: true" in kis_section
    assert "- /tmp" in kis_section

    canary_section = compose.split("\n  kis-paper-canary:\n", maxsplit=1)[1].split(
        "\n  kis-paper-session:\n", maxsplit=1
    )[0]
    assert 'profiles: ["kis-paper-canary"]' in canary_section
    assert "--execute" in canary_section
    assert "--cancel-after-submit" in canary_section
    assert "THERICHER_MODE: kis_paper" in canary_section
    assert "KIS_PAPER_APP_KEY" in canary_section
    assert "KIS_LIVE" not in canary_section
    assert "thericher-v2-paper-canary-private:/app/private" in canary_section

    session_section = compose.split("\n  kis-paper-session:\n", maxsplit=1)[1].split(
        "\n  kis-paper-daily-backfill:\n", maxsplit=1
    )[0]
    assert 'profiles: ["kis-paper-session"]' in session_section
    assert "thericher_v2.execution.kis_paper_session" in session_section
    assert "--execute" in session_section
    assert session_section.count("--execute") == 1
    assert "--cancel-after-submit" in session_section
    assert "THERICHER_MODE: kis_paper" in session_section
    assert "KIS_PAPER_APP_KEY" in session_section
    assert "KIS_LIVE" not in session_section
    assert "ports:" not in session_section
    assert "thericher-v2-paper-canary-private:/app/private" in session_section

    intraday_section = compose.split("\n  kis-paper-intraday-cache:\n", maxsplit=1)[1].split(
        "\n  kis-paper-intraday-head:\n", maxsplit=1
    )[0]
    assert 'profiles: ["kis-paper-intraday-cache"]' in intraday_section
    assert "backfill_kis_paper_private_intraday.py" in intraday_section
    assert "KIS_PAPER_APP_KEY" in intraday_section
    assert "KIS_PAPER_ACCOUNT" not in intraday_section
    assert "KIS_LIVE" not in intraday_section
    assert ".env" not in intraday_section
    assert "kis_paper_intraday_freshness.json" in intraday_section
    assert "thericher-v2-runtime:/app/runtime" in intraday_section

    intraday_head_section = compose.split("\n  kis-paper-intraday-head:\n", maxsplit=1)[1].split(
        "\nvolumes:\n", maxsplit=1
    )[0]
    assert 'profiles: ["kis-paper-intraday-head"]' in intraday_head_section
    assert "backfill_kis_paper_private_intraday.py" in intraday_head_section
    assert "- --mode\n      - session-capture" in intraday_head_section
    assert "--pages-per-target" in intraday_head_section
    assert '"4"' in intraday_head_section
    assert "KIS_PAPER_APP_KEY" in intraday_head_section
    assert "KIS_PAPER_ACCOUNT" not in intraday_head_section
    assert "KIS_LIVE" not in intraday_head_section
    assert ".env" not in intraday_head_section
    assert "kis_paper_intraday_freshness.json" in intraday_head_section
    assert "thericher-v2-runtime:/app/runtime" in intraday_head_section

    assert "\n  paper-capital-proposal:\n" not in compose

    dockerignore = (repo_root / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in dockerignore
    assert "!.env.example" in dockerignore


def test_dashboard_rejects_non_loopback_bind_without_the_explicit_docker_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert dashboard_server._validated_bind_host(
        "127.0.0.1",
        allow_container_bind=False,
    ) == "127.0.0.1"

    monkeypatch.setattr(dashboard_server, "_is_container_runtime", lambda: True)
    assert dashboard_server._validated_bind_host(
        "0.0.0.0",
        allow_container_bind=True,
    ) == "0.0.0.0"

    monkeypatch.setattr(dashboard_server, "_is_container_runtime", lambda: False)
    with pytest.raises(ValueError, match="127.0.0.1"):
        dashboard_server._validated_bind_host("0.0.0.0", allow_container_bind=False)
    with pytest.raises(ValueError, match="127.0.0.1"):
        dashboard_server._validated_bind_host("0.0.0.0", allow_container_bind=True)
    with pytest.raises(ValueError, match="127.0.0.1"):
        dashboard_server._validated_bind_host("192.168.0.10", allow_container_bind=True)
