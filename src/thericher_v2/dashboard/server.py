"""Small authenticated local dashboard server.

This server is intentionally stdlib-only. It exposes a read endpoint and two
local emergency-state actions. It never calls KIS or any broker.
"""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from thericher_v2.dashboard.view import build_snapshot
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.serialization import to_jsonable
from thericher_v2.state.event_log import EventStore


def _json_response(
    handler: BaseHTTPRequestHandler,
    status: HTTPStatus,
    payload: dict[str, Any],
) -> None:
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def _authorized(self) -> bool:
        expected = self.server.token
        if not expected:
            return True
        return self.headers.get("Authorization") == f"Bearer {expected}"

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return False

    def do_GET(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        if self.path in {"/", "/state"}:
            snapshot = build_snapshot(
                self.server.event_store,
                self.server.emergency_store,
                self.server.mode,
            )
            _json_response(self, HTTPStatus.OK, snapshot.to_dict())
        elif self.path == "/health":
            _json_response(self, HTTPStatus.OK, {"status": "ok", "broker_calls": False})
        else:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        if self.path == "/emergency/stop-new-orders":
            state = self.server.emergency_store.stop_new_orders("dashboard_stop_new_orders")
            _json_response(
                self,
                HTTPStatus.OK,
                {"status": "stop_new_orders_set", "state": to_jsonable(state)},
            )
        elif self.path == "/emergency/cancel-open-orders":
            state = self.server.emergency_store.request_cancel_open_orders(
                "dashboard_cancel_open_orders"
            )
            _json_response(
                self,
                HTTPStatus.OK,
                {"status": "cancel_open_orders_requested", "state": to_jsonable(state)},
            )
        else:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})


class DashboardServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        *,
        event_store: EventStore,
        emergency_store: EmergencyStore,
        token: str,
        mode: str,
    ) -> None:
        super().__init__(address, DashboardHandler)
        self.event_store = event_store
        self.emergency_store = emergency_store
        self.token = token
        self.mode = mode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--state-db", type=Path, default=Path("runtime/state/thericher.sqlite"))
    parser.add_argument("--event-log", type=Path, default=Path("runtime/state/events.jsonl"))
    parser.add_argument(
        "--emergency-state",
        type=Path,
        default=Path("runtime/emergency_state.json"),
    )
    parser.add_argument("--mode", default=os.environ.get("THERICHER_MODE", "off"))
    parser.add_argument("--token", default=os.environ.get("THERICHER_DASHBOARD_TOKEN", ""))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = EventStore(args.state_db, args.event_log)
    store.bootstrap()
    emergency = EmergencyStore(args.emergency_state)
    server = DashboardServer(
        (args.host, args.port),
        event_store=store,
        emergency_store=emergency,
        token=args.token,
        mode=args.mode,
    )
    print(f"dashboard listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
