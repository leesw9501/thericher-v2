from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path

from thericher_v2.dashboard import server as dashboard_server
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.state.event_log import EventStore


@contextmanager
def _serve(tmp_path: Path, *, token: str = ""):
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    store.bootstrap()
    server = dashboard_server.DashboardServer(
        ("127.0.0.1", 0),
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        mode="off",
        token=token,
        operations_artifact_root=tmp_path / "public-operations",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _get(server, path: str):
    connection = HTTPConnection(*server.server_address[:2], timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        connection.close()


def test_state_uses_explicit_operations_root(tmp_path, monkeypatch):
    calls = []
    projected = {"observed_at": datetime.now(UTC).isoformat(), "runs": []}

    def read_operations(root):
        calls.append(root)
        return projected

    monkeypatch.setattr(dashboard_server, "build_operations_snapshot", read_operations)
    with _serve(tmp_path) as server:
        status, body = _get(server, "/state")
    assert status == 200
    operations = json.loads(body)["operations_snapshot"]
    assert operations["observed_at"] == projected["observed_at"]
    assert {run["key"] for run in operations["runs"]} == {"h20", "googl", "h3"}
    assert all(run["fill"] == "unknown" for run in operations["runs"])
    assert calls == [tmp_path / "public-operations"]


def test_unauthorized_state_does_not_read_operations(tmp_path, monkeypatch):
    def unexpected_read(_root):
        raise AssertionError("unauthenticated request reached the outcome reader")

    monkeypatch.setattr(dashboard_server, "build_operations_snapshot", unexpected_read)
    with _serve(tmp_path, token="invented-test-token") as server:
        status, body = _get(server, "/state")
    assert status == 401
    assert json.loads(body) == {"error": "unauthorized"}


def test_health_does_not_read_outcomes_or_broker(tmp_path, monkeypatch):
    def unexpected_read(_root):
        raise AssertionError("health must not inspect financial outcomes")

    monkeypatch.setattr(dashboard_server, "build_operations_snapshot", unexpected_read)
    with _serve(tmp_path) as server:
        status, body = _get(server, "/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok", "broker_calls": False}


def test_login_is_korean_primary_without_exposing_token(tmp_path):
    with _serve(tmp_path, token="invented-test-token") as server:
        status, body = _get(server, "/login")
    assert status == 200
    assert '<html lang="ko">' in body
    assert "접속 토큰" in body
    assert "TheRicher v2" in body
    assert "invented-test-token" not in body
