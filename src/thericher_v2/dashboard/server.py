"""Small local dashboard server with no broker or credential surface."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from thericher_v2.dashboard.view import build_snapshot, render_dashboard
from thericher_v2.execution.emergency import EmergencyStore, PaperExecutionControlStore
from thericher_v2.serialization import to_jsonable
from thericher_v2.state.event_log import EventStore

_MAX_FORM_BYTES = 4096
_SESSION_COOKIE = "thericher_dashboard_session"
_FORM_COOKIE = "thericher_dashboard_form"


def _json_response(
    handler: BaseHTTPRequestHandler,
    status: HTTPStatus,
    payload: dict[str, Any],
) -> None:
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(encoded)


def _html_response(
    handler: BaseHTTPRequestHandler,
    status: HTTPStatus,
    body: str,
    *,
    cookies: tuple[str, ...] = (),
) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'",
    )
    for cookie in cookies:
        handler.send_header("Set-Cookie", cookie)
    handler.end_headers()
    handler.wfile.write(encoded)


def _redirect(
    handler: BaseHTTPRequestHandler,
    location: str,
    *,
    cookies: tuple[str, ...] = (),
) -> None:
    handler.send_response(HTTPStatus.SEE_OTHER)
    handler.send_header("Location", location)
    handler.send_header("Cache-Control", "no-store")
    for cookie in cookies:
        handler.send_header("Set-Cookie", cookie)
    handler.end_headers()


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def do_GET(self) -> None:  # noqa: N802
        path = self._path()
        if path == "/login":
            self._login_page()
            return
        if not self._require_auth(path):
            return
        if path == "/":
            snapshot = build_snapshot(
                self.server.event_store,
                self.server.emergency_store,
                self.server.mode,
                execution_control_store=self.server.execution_control_store,
                paper_account_snapshot_path=self.server.paper_account_snapshot_path,
                paper_canary_runtime_path=self.server.paper_canary_runtime_path,
                market_data_freshness_path=self.server.market_data_freshness_path,
                qqq_gross_receipt_path=self.server.qqq_gross_receipt_path,
                qqq_gross_receipt_sha256=self.server.qqq_gross_receipt_sha256,
            )
            _html_response(
                self,
                HTTPStatus.OK,
                render_dashboard(snapshot, form_nonce=self.server.form_nonce),
                cookies=(self.server.form_cookie(),),
            )
        elif path == "/state":
            snapshot = build_snapshot(
                self.server.event_store,
                self.server.emergency_store,
                self.server.mode,
                execution_control_store=self.server.execution_control_store,
                paper_account_snapshot_path=self.server.paper_account_snapshot_path,
                paper_canary_runtime_path=self.server.paper_canary_runtime_path,
                market_data_freshness_path=self.server.market_data_freshness_path,
                qqq_gross_receipt_path=self.server.qqq_gross_receipt_path,
                qqq_gross_receipt_sha256=self.server.qqq_gross_receipt_sha256,
            )
            _json_response(self, HTTPStatus.OK, snapshot.to_dict())
        elif path == "/health":
            _json_response(self, HTTPStatus.OK, {"status": "ok", "broker_calls": False})
        else:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self._path()
        form = self._read_form()
        if form is None:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_form"})
            return
        if path == "/login":
            self._login(form)
            return
        if path == "/logout":
            self._logout(form)
            return
        if not self._require_auth(path):
            return
        if not self._valid_action_request(form):
            _json_response(self, HTTPStatus.FORBIDDEN, {"error": "action_request_rejected"})
            return
        if path == "/emergency/stop-new-orders":
            state = self.server.emergency_store.stop_new_orders("dashboard_stop_new_orders")
            self._action_response("stop_new_orders_set", state)
        elif path == "/controls/pause-buys":
            state = self.server.execution_control_store.set_pause_buys(True)
            self._action_response("pause_buys_set", state)
        elif path == "/controls/resume-buys":
            state = self.server.execution_control_store.set_pause_buys(False)
            self._action_response("pause_buys_cleared", state)
        elif path == "/controls/pause-sells":
            state = self.server.execution_control_store.set_pause_sells(True)
            self._action_response("pause_sells_set", state)
        elif path == "/controls/resume-sells":
            state = self.server.execution_control_store.set_pause_sells(False)
            self._action_response("pause_sells_cleared", state)
        else:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def log_message(self, _format: str, *_args: object) -> None:
        """Avoid request logging that could accidentally retain sensitive URLs."""

    def _path(self) -> str:
        return urlsplit(self.path).path

    def _authorized(self) -> bool:
        if not self.server.token:
            return True
        return self._valid_bearer_token() or self._valid_session_cookie()

    def _valid_bearer_token(self) -> bool:
        expected = self.server.token
        supplied = self.headers.get("Authorization", "")
        return bool(expected) and hmac.compare_digest(supplied, f"Bearer {expected}")

    def _valid_session_cookie(self) -> bool:
        expected = self.server.session_value
        supplied = self._cookie_value(_SESSION_COOKIE)
        return bool(expected and supplied) and hmac.compare_digest(supplied, expected)

    def _require_auth(self, path: str) -> bool:
        if self._authorized():
            return True
        if path == "/":
            _redirect(self, "/login")
        else:
            _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return False

    def _login_page(self) -> None:
        if not self.server.token:
            _redirect(self, "/")
            return
        if self._authorized():
            _redirect(self, "/")
            return
        _html_response(self, HTTPStatus.OK, _login_html())

    def _login(self, form: dict[str, list[str]]) -> None:
        expected = self.server.token
        supplied = form.get("token", [""])[0]
        if not expected or not hmac.compare_digest(supplied, expected):
            if self._prefers_html():
                _html_response(self, HTTPStatus.UNAUTHORIZED, _login_html(error="Invalid token."))
            else:
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        _redirect(
            self,
            "/",
            cookies=(self.server.session_cookie(), self.server.form_cookie()),
        )

    def _logout(self, form: dict[str, list[str]]) -> None:
        if not self._require_auth("/logout"):
            return
        if not self._valid_action_request(form):
            _json_response(self, HTTPStatus.FORBIDDEN, {"error": "action_request_rejected"})
            return
        _redirect(self, "/login", cookies=(self.server.clear_session_cookie(),))

    def _action_response(self, status: str, state: object) -> None:
        if self._prefers_html():
            _redirect(self, "/", cookies=(self.server.form_cookie(),))
            return
        _json_response(
            self,
            HTTPStatus.OK,
            {"status": status, "state": to_jsonable(state)},
        )

    def _valid_action_request(self, form: dict[str, list[str]]) -> bool:
        if self._valid_bearer_token():
            return True
        if not self._same_origin():
            return False
        submitted = form.get("csrf", [""])[0]
        cookie = self._cookie_value(_FORM_COOKIE)
        expected = self.server.form_nonce
        return bool(
            submitted
            and cookie
            and hmac.compare_digest(submitted, expected)
            and hmac.compare_digest(cookie, expected)
        )

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return hmac.compare_digest(origin, f"http://{host}")

    def _read_form(self) -> dict[str, list[str]] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length < 0 or length > _MAX_FORM_BYTES:
            return None
        try:
            body = self.rfile.read(length).decode("utf-8")
        except UnicodeDecodeError:
            return None
        return parse_qs(body, keep_blank_values=True)

    def _cookie_value(self, name: str) -> str:
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return ""
        morsel = cookies.get(name)
        return "" if morsel is None else morsel.value

    def _prefers_html(self) -> bool:
        return "text/html" in self.headers.get("Accept", "")


class DashboardServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        *,
        event_store: EventStore,
        emergency_store: EmergencyStore,
        token: str,
        mode: str,
        execution_control_store: PaperExecutionControlStore | None = None,
        paper_account_snapshot_path: Path | None = None,
        paper_canary_runtime_path: Path | None = None,
        market_data_freshness_path: Path | None = None,
        qqq_gross_receipt_path: Path | None = None,
        qqq_gross_receipt_sha256: str | None = None,
    ) -> None:
        super().__init__(address, DashboardHandler)
        self.event_store = event_store
        self.emergency_store = emergency_store
        self.execution_control_store = execution_control_store or PaperExecutionControlStore(
            emergency_store.path.with_name("paper_execution_control.json")
        )
        self.token = token
        self.mode = mode
        self.paper_account_snapshot_path = paper_account_snapshot_path
        self.paper_canary_runtime_path = paper_canary_runtime_path
        self.market_data_freshness_path = market_data_freshness_path
        self.qqq_gross_receipt_path = qqq_gross_receipt_path
        self.qqq_gross_receipt_sha256 = qqq_gross_receipt_sha256
        self.form_nonce = secrets.token_urlsafe(32)
        self.session_value = _session_value(token) if token else ""

    def form_cookie(self) -> str:
        return _cookie(_FORM_COOKIE, self.form_nonce)

    def session_cookie(self) -> str:
        return _cookie(_SESSION_COOKIE, self.session_value)

    def clear_session_cookie(self) -> str:
        return _cookie(_SESSION_COOKIE, "", max_age=0)


def _session_value(token: str) -> str:
    return hmac.new(
        token.encode("utf-8"),
        b"thericher-v2-dashboard-session-v1",
        "sha256",
    ).hexdigest()


def _cookie(name: str, value: str, *, max_age: int | None = None) -> str:
    cookie = SimpleCookie()
    cookie[name] = value
    morsel = cookie[name]
    morsel["path"] = "/"
    morsel["httponly"] = True
    morsel["samesite"] = "Strict"
    if max_age is not None:
        morsel["max-age"] = str(max_age)
    return morsel.OutputString()


def _login_html(*, error: str = "") -> str:
    error_markup = "" if not error else f'<p role="alert">{error}</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TheRicher v2 Dashboard</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #f6f7f8;
      color: #18222d;
      font-family: system-ui, sans-serif;
    }}
    main {{
      width: min(360px, calc(100% - 32px));
      border-top: 3px solid #18222d;
      background: #ffffff;
      padding: 24px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 20px; }}
    p {{ color: #63707d; }}
    form {{ display: grid; gap: 10px; margin-top: 20px; }}
    input, button {{
      min-height: 38px;
      border: 1px solid #aeb8c2;
      border-radius: 4px;
      font: inherit;
      padding: 7px 9px;
    }}
    button {{ border-color: #18222d; background: #18222d; color: #ffffff; cursor: pointer; }}
    [role=\"alert\"] {{ color: #b42318; }}
  </style>
</head>
<body>
  <main>
    <h1>TheRicher v2</h1>
    <p>Local paper console</p>
    {error_markup}
    <form method="post" action="/login">
      <label for="token">Dashboard token</label>
      <input id="token" name="token" type="password" autocomplete="current-password" required>
      <button type="submit">Open console</button>
    </form>
  </main>
</body>
</html>"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--allow-container-bind",
        action="store_true",
        help="allow the Docker-only 0.0.0.0 listener behind a loopback host publish",
    )
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--state-db", type=Path, default=Path("runtime/state/thericher.sqlite"))
    parser.add_argument("--event-log", type=Path, default=Path("runtime/state/events.jsonl"))
    parser.add_argument(
        "--emergency-state",
        type=Path,
        default=Path("runtime/emergency_state.json"),
    )
    parser.add_argument(
        "--execution-control",
        type=Path,
        default=Path("runtime/paper_execution_control.json"),
    )
    parser.add_argument(
        "--paper-account-snapshot",
        type=Path,
        default=Path("runtime/state/paper_account_snapshot.json"),
    )
    parser.add_argument(
        "--paper-canary-runtime",
        type=Path,
        default=Path("runtime/state/kis_paper_canary.json"),
    )
    parser.add_argument(
        "--market-data-freshness",
        type=Path,
        default=Path("runtime/state/kis_paper_intraday_freshness.json"),
    )
    parser.add_argument("--mode", default=os.environ.get("THERICHER_MODE", "off"))
    parser.add_argument("--qqq-gross-receipt", type=Path)
    parser.add_argument("--qqq-gross-receipt-sha256")
    parser.add_argument("--token", default=os.environ.get("THERICHER_DASHBOARD_TOKEN", ""))
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        host = _validated_bind_host(args.host, allow_container_bind=args.allow_container_bind)
    except ValueError as error:
        parser.error(str(error))
    store = EventStore(args.state_db, args.event_log)
    emergency = EmergencyStore(args.emergency_state)
    execution_control = PaperExecutionControlStore(args.execution_control)
    server = DashboardServer(
        (host, args.port),
        event_store=store,
        emergency_store=emergency,
        execution_control_store=execution_control,
        token=args.token,
        mode=args.mode,
        paper_account_snapshot_path=args.paper_account_snapshot,
        paper_canary_runtime_path=args.paper_canary_runtime,
        market_data_freshness_path=args.market_data_freshness,
        qqq_gross_receipt_path=args.qqq_gross_receipt,
        qqq_gross_receipt_sha256=args.qqq_gross_receipt_sha256,
    )
    print(f"dashboard listening on http://{host}:{args.port}")
    server.serve_forever()


def _validated_bind_host(host: str, *, allow_container_bind: bool) -> str:
    """Allow local serving, plus the explicit Docker listener behind loopback publish."""

    if host == "127.0.0.1":
        return host
    if host == "0.0.0.0" and allow_container_bind and _is_container_runtime():
        return host
    raise ValueError(
        "dashboard host must be 127.0.0.1; Docker requires --allow-container-bind in a container"
    )


def _is_container_runtime() -> bool:
    return Path("/.dockerenv").is_file()


if __name__ == "__main__":
    main()
