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

from thericher_v2.contracts import Bar, OrderIntent, Timeframe
from thericher_v2.dashboard.server import DashboardServer
from thericher_v2.dashboard.view import build_snapshot
from thericher_v2.execution import EmergencyStore, LocalPaperBroker
from thericher_v2.execution.paper_account_snapshot import (
    PAPER_ACCOUNT_SNAPSHOT_TTL,
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
def _dashboard(tmp_path: Path, *, token: str = ""):
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")
    server = DashboardServer(
        ("127.0.0.1", 0),
        event_store=events,
        emergency_store=emergency,
        token=token,
        mode="off",
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
    assert snapshot.local_paper_pnl_status == "unavailable"
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


def test_empty_and_malformed_local_event_logs_remain_distinct(tmp_path) -> None:
    events = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    events.bootstrap()
    emergency = EmergencyStore(tmp_path / "emergency.json")

    empty_snapshot = build_snapshot(events, emergency)
    assert empty_snapshot.status == "local_monitor_only"
    assert empty_snapshot.local_paper_status == "no_local_paper_activity"
    assert empty_snapshot.position_count == 0
    assert empty_snapshot.local_paper_cash is None

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
                Decimal("1"),
            ),
            positions=(PaperAccountPosition("NASD", "SPY", "USD", Decimal("2")),),
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

    from thericher_v2.dashboard.view import render_dashboard

    html = render_dashboard(snapshot, form_nonce="form-nonce")
    assert "KIS orderable foreign funds" in html
    assert "Reference orderability" in html
    assert "KIS positions" in html
    assert "KIS price quotes" in html
    assert "general buying power" in html

    stale_snapshot = build_snapshot(
        events,
        emergency,
        paper_account_snapshot_path=paper_snapshot_path,
        now=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL + timedelta(seconds=1),
    )
    assert stale_snapshot.paper_account_status == "unavailable"
    assert stale_snapshot.paper_account is None
    assert stale_snapshot.kis_holdings_status == "unavailable"


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
        cookie_header = _cookies(headers)
        nonce = _nonce(html)

        status, _, state_body = _request(server, "GET", "/state")
        assert status == 200
        state = json.loads(state_body)
        assert state["local_paper_fill_count"] == 1
        assert state["kis_prices_status"] == "unknown"

        status, _, _ = _request(server, "POST", "/emergency/stop-new-orders")
        assert status == 403
        assert events.jsonl_path.read_bytes() == event_bytes
        assert not emergency.read().stop_new_orders

        form = urlencode({"csrf": nonce})
        form_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": cookie_header,
        }
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
        assert status == 200
        state = emergency.read()
        assert state.stop_new_orders
        assert state.cancel_open_orders_requested
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

    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    engine_section = compose.split("\n  engine:\n", maxsplit=1)[1].split(
        "\n  web:\n", maxsplit=1
    )[0]
    web_section = compose.split("\n  web:\n", maxsplit=1)[1].split(
        "\n  research:\n", maxsplit=1
    )[0]
    assert '"127.0.0.1:8787:8787"' in web_section
    assert "KIS_" not in web_section
    assert "TIINGO" not in web_section
    assert "thericher-v2-runtime:/app/runtime" in engine_section
    assert "thericher-v2-runtime:/app/runtime:ro" in web_section
    assert "thericher-v2-web-emergency:/app/emergency" in web_section

    kis_section = compose.split("\n  kis-readonly:\n", maxsplit=1)[1].split(
        "\n  kis-paper-canary:\n", maxsplit=1
    )[0]
    assert "profiles: [\"kis-readonly\"]" in kis_section
    assert "KIS_PAPER_APP_KEY" in kis_section
    assert "KIS_LIVE" not in kis_section
    assert ".env" not in kis_section

    canary_section = compose.split("\n  kis-paper-canary:\n", maxsplit=1)[1].split(
        "\nvolumes:\n", maxsplit=1
    )[0]
    assert 'profiles: ["kis-paper-canary"]' in canary_section
    assert "--execute" in canary_section
    assert "--cancel-after-submit" in canary_section
    assert "KIS_PAPER_APP_KEY" in canary_section
    assert "KIS_LIVE" not in canary_section
    assert "thericher-v2-paper-canary-private:/app/private" in canary_section

    assert "\n  paper-capital-proposal:\n" not in compose

    dockerignore = (repo_root / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in dockerignore
    assert "!.env.example" in dockerignore
