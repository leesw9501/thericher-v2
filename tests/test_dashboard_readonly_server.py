"""Invented public DTOs only; no broker, credentials, Task or artifact imports."""

from __future__ import annotations

import ast
import copy
import http.client
import json
import os
import socket
import stat
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.dashboard import readonly_server as readonly
from thericher_v2.dashboard.readonly_view import render_readonly_dashboard

AS_OF = datetime(2025, 1, 2, 0, 0, tzinfo=UTC)


@pytest.fixture
def public_summary() -> dict:
    """The adapter fixture is invented, not an actual run/account observation."""
    return {
        "schema": readonly.PUBLIC_SCHEMA,
        "as_of": AS_OF.isoformat(),
        "runs": [
            {
                "key": "invented-input",
                "label": "합성 입력 A (INVENTED)",
                "installation": "installed",
                "plan": [
                    {"stage": "producer", "at": "2025-01-01T14:25:00+00:00"},
                    {"stage": "entry", "at": "2025-01-01T15:17:00+00:00"},
                    {"stage": "exit", "at": "2025-01-03T20:54:00+00:00"},
                ],
                "outcome": {
                    "status": "abstain",
                    "observed_at": "2025-01-01T14:26:00+00:00",
                    "failure": {
                        "reason": "missing_runtime_files",
                        "exception": "key_error",
                        "stage": "pre_model",
                    },
                    "task_exit_codes": [2, 20, 20],
                },
                "financial": {"submit": "unknown", "fill": "unknown", "owned": "unknown"},
                "evidence": {
                    "kind": "technical_diagnosis",
                    "reference": "invented-diagnosis",
                    "sha256": "a" * 64,
                },
            }
        ],
        "control": {"saved_request": "pause_requested", "worker_ack": "unknown"},
    }


@pytest.fixture
def public_root(tmp_path: Path, public_summary: dict) -> Path:
    root = tmp_path / "public"
    root.mkdir()
    (root / readonly.SUMMARY_NAME).write_text(json.dumps(public_summary), encoding="utf-8")
    return root


@pytest.fixture
def native_server(public_root: Path):
    with readonly.ReadonlyServer(public_root, port=0) as server:
        assert server.server_address[0] == "127.0.0.1"
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        worker.start()
        try:
            yield server
        finally:
            server.shutdown()
            worker.join(timeout=3)
            assert not worker.is_alive()


def request(server, method="GET", path="/", *, headers=None, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_parse_native_adapter_and_independent_categories(public_summary):
    result = readonly.parse_public_summary(json.dumps(public_summary).encode())
    assert result == public_summary
    run = result["runs"][0]
    assert run["installation"] == "installed"
    assert run["outcome"]["status"] == "abstain"
    assert set(run["financial"].values()) == {"unknown"}
    assert result["control"] == {"saved_request": "pause_requested", "worker_ack": "unknown"}


@pytest.mark.parametrize(
    ("where", "field", "value"),
    [
        ("top", "account", "invented"),
        ("top", "env", {}),
        ("run", "bank", "invented"),
        ("run", "private_root", "invented"),
        ("run", "model_code", "invented.py"),
        ("outcome", "orders", []),
        ("outcome", "price", 12.3),
        ("outcome", "raw_error", "invented"),
        ("financial", "net_pnl", 0),
        ("financial", "account_number", "invented"),
        ("financial", "fill", 0),
        ("financial", "owned", False),
        ("evidence", "path", "invented"),
        ("control", "available", True),
        ("control", "credentials", {}),
    ],
)
def test_private_and_unqualified_fields_rejected(public_summary, where, field, value):
    target = public_summary
    if where == "run":
        target = public_summary["runs"][0]
    elif where not in {"top", "control"}:
        target = public_summary["runs"][0][where]
    elif where == "control":
        target = public_summary[where]
    target[field] = value
    with pytest.raises(readonly.InvalidPublicSummary, match="^invalid_public_summary$"):
        readonly.parse_public_summary(json.dumps(public_summary).encode())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x.update(schema="unknown"),
        lambda x: x.update(as_of="2025-01-02T00:00:00"),
        lambda x: x.update(runs=[x["runs"][0]] * 21),
        lambda x: x["runs"].append(copy.deepcopy(x["runs"][0])),
        lambda x: x["runs"][0].update(label="<script>alert(1)</script>"),
        lambda x: x["runs"][0].update(label="a" * 49),
        lambda x: x["runs"][0].update(key="../invented"),
        lambda x: x["runs"][0].update(installation="filled"),
        lambda x: x["runs"][0]["plan"].append(x["runs"][0]["plan"][0]),
        lambda x: x["runs"][0]["plan"][0].update(stage="order"),
        lambda x: x["runs"][0]["outcome"].update(observed_at="2026-01-02T00:00:00Z"),
        lambda x: x["runs"][0]["outcome"].update(status="completed"),
        lambda x: x["runs"][0]["outcome"].update(task_exit_codes=[True]),
        lambda x: x["runs"][0]["outcome"].update(task_exit_codes=[2**32]),
        lambda x: x["runs"][0]["outcome"]["failure"].update(reason="raw_exception_text"),
        lambda x: x["runs"][0]["evidence"].update(reference="https://invented.invalid/"),
        lambda x: x["runs"][0]["evidence"].update(sha256="not-a-digest"),
        lambda x: x["control"].update(worker_ack="all_workers_paused"),
    ],
)
def test_invalid_schema_categories_and_clocks(public_summary, mutation):
    mutation(public_summary)
    with pytest.raises(readonly.InvalidPublicSummary):
        readonly.parse_public_summary(json.dumps(public_summary).encode())


@pytest.mark.parametrize(
    "raw",
    [
        b"[]",
        b"null",
        b"{bad",
        b'{"schema":"one","schema":"two"}',
        b'{"schema":NaN}',
        b'{"schema":Infinity}',
        b"\xff",
        b"x" * (readonly.MAX_SUMMARY_BYTES + 1),
        b"[" * 1100 + b"]" * 1100,
    ],
    ids=[
        "array",
        "null",
        "syntax",
        "duplicate",
        "nan",
        "infinity",
        "encoding",
        "oversize",
        "depth",
    ],
)
def test_bounded_strict_json(raw):
    with pytest.raises(readonly.InvalidPublicSummary):
        readonly.parse_public_summary(raw)


def test_task_metadata_never_qualifies_a_fill(public_summary):
    public_summary["runs"][0]["financial"]["fill"] = "linked"
    public_summary["runs"][0]["evidence"]["kind"] = "task_metadata"
    with pytest.raises(readonly.InvalidPublicSummary):
        readonly.parse_public_summary(json.dumps(public_summary).encode())
    run = public_summary["runs"][0]
    run["evidence"]["kind"] = "public_outcome"
    assert readonly.parse_public_summary(json.dumps(public_summary).encode()) == public_summary
    run["evidence"]["sha256"] = None
    with pytest.raises(readonly.InvalidPublicSummary):
        readonly.parse_public_summary(json.dumps(public_summary).encode())
    run["evidence"]["sha256"] = "a" * 64
    run["outcome"]["observed_at"] = None
    with pytest.raises(readonly.InvalidPublicSummary):
        readonly.parse_public_summary(json.dumps(public_summary).encode())


@pytest.mark.parametrize(
    "status", ["unknown", "abstain", "not_entered", "technical_failure", "completed"]
)
def test_all_public_actual_categories_render_without_financial_inference(public_summary, status):
    run = public_summary["runs"][0]
    run["outcome"].update(status=status, failure=None)
    parsed = readonly.parse_public_summary(json.dumps(public_summary).encode())
    snapshot = readonly.ReadonlySnapshot("stale", parsed, 1000).to_dict()
    html = render_readonly_dashboard(snapshot)
    assert status.upper() in html
    assert set(snapshot["runs"][0]["financial"].values()) == {"unknown"}


def test_fresh_stale_unknown_and_no_synthetic_zero(public_root, tmp_path):
    assert readonly.load_snapshot(public_root, now=AS_OF).source_state == "fresh"
    assert (
        readonly.load_snapshot(public_root, now=AS_OF + timedelta(seconds=300)).source_state
        == "fresh"
    )
    stale = readonly.load_snapshot(public_root, now=AS_OF + timedelta(seconds=301))
    assert stale.source_state == "stale" and stale.age_seconds == 301
    unknown = readonly.load_snapshot(tmp_path / "missing").to_dict()
    assert unknown["source_state"] == "unknown"
    assert unknown["counts"] == {"runs": None}
    assert unknown["control"] == {
        "available": False,
        "saved_request": "unknown",
        "worker_ack": "unknown",
    }
    assert (
        readonly.load_snapshot(public_root, now=AS_OF - timedelta(seconds=1)).source_state
        == "unknown"
    )
    assert (
        readonly.load_snapshot(public_root, now=AS_OF - timedelta(milliseconds=1)).source_state
        == "unknown"
    )
    assert (
        readonly.load_snapshot(public_root, now=AS_OF + timedelta(seconds=300.1)).source_state
        == "stale"
    )


def test_valid_empty_summary_is_not_missing(public_root, public_summary):
    public_summary["runs"] = []
    (public_root / readonly.SUMMARY_NAME).write_text(json.dumps(public_summary), encoding="utf-8")
    assert readonly.load_snapshot(public_root, now=AS_OF).to_dict()["counts"] == {"runs": 0}


def test_no_implicit_env_or_directory_listing(public_root, monkeypatch):
    (public_root / ".env").write_text("INVENTED_DO_NOT_READ=fixture", encoding="ascii")
    original_open = os.open
    calls = []

    def only_summary(path, *args, **kwargs):
        assert Path(path) == public_root / readonly.SUMMARY_NAME
        calls.append(Path(path).name)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", only_summary)
    monkeypatch.setattr(Path, "iterdir", lambda _path: pytest.fail("no directory listing"))
    assert readonly.load_snapshot(public_root, now=AS_OF).source_state == "fresh"
    assert calls == ["summary.json"]


def test_hardlinks_rejected_before_open(public_root, tmp_path, monkeypatch):
    link = tmp_path / "invented-link.json"
    os.link(public_root / readonly.SUMMARY_NAME, link)
    try:
        monkeypatch.setattr(os, "open", lambda *_a, **_k: pytest.fail("hardlink must not open"))
        assert readonly.load_snapshot(public_root).source_state == "unknown"
    finally:
        link.unlink()


@pytest.mark.parametrize("alias", ["root_reparse", "file_reparse", "file_symlink"])
def test_aliases_rejected_before_open(public_root, monkeypatch, alias):
    original = Path.lstat

    def altered(path):
        info = original(path)
        chosen = public_root if alias == "root_reparse" else public_root / readonly.SUMMARY_NAME
        if path != chosen:
            return info
        fields = {k: getattr(info, k) for k in dir(info) if k.startswith("st_")}
        if alias == "file_symlink":
            fields["st_mode"] = stat.S_IFLNK | 0o777
        else:
            fields["st_file_attributes"] = fields.get("st_file_attributes", 0) | 1024
        return SimpleNamespace(**fields)

    monkeypatch.setattr(Path, "lstat", altered)
    monkeypatch.setattr(os, "open", lambda *_a, **_k: pytest.fail("alias must not open"))
    assert readonly.load_snapshot(public_root).source_state == "unknown"


def test_changed_file_is_not_parsed(public_root, monkeypatch):
    original = os.read
    changed = False

    def unstable(fd, size):
        nonlocal changed
        raw = original(fd, size)
        if not changed:
            changed = True
            p = public_root / readonly.SUMMARY_NAME
            info = p.stat()
            os.utime(p, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
        return raw

    monkeypatch.setattr(os, "read", unstable)
    monkeypatch.setattr(
        readonly, "parse_public_summary", lambda _raw: pytest.fail("unstable parse")
    )
    assert readonly.load_snapshot(public_root).source_state == "unknown"


def test_oversized_file_and_directory_not_opened(public_root, monkeypatch):
    path = public_root / readonly.SUMMARY_NAME
    path.write_bytes(b"x" * (readonly.MAX_SUMMARY_BYTES + 1))
    monkeypatch.setattr(os, "open", lambda *_a, **_k: pytest.fail("invalid source must not open"))
    assert readonly.load_snapshot(public_root).source_state == "unknown"
    path.unlink()
    path.mkdir()
    assert readonly.load_snapshot(public_root).source_state == "unknown"


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("path", ["/", "/health", "/summary.json"])
def test_native_get_head_routes(native_server, method, path):
    status, headers, body = request(native_server, method, path)
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "form-action 'none'" in headers["Content-Security-Policy"]
    assert "Set-Cookie" not in headers
    if method == "HEAD":
        assert body == b"" and int(headers["Content-Length"]) > 0
    elif path == "/summary.json":
        api = json.loads(body)
        assert api["readonly"] is True and api["broker_calls"] is False
        assert api["source_state"] == "stale"
        assert api["control"]["available"] is False
    elif path == "/health":
        assert json.loads(body) == {"status": "ok", "readonly": True, "broker_calls": False}


@pytest.mark.parametrize(
    "method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT", "BREW"]
)
def test_native_mutating_and_unknown_methods_405(native_server, monkeypatch, method):
    monkeypatch.setattr(readonly, "load_snapshot", lambda *_a: pytest.fail("no source for methods"))
    status, headers, body = request(native_server, method, "/controls/pause-buys", body=b"invented")
    assert status == 405 and headers["Allow"] == "GET, HEAD"
    assert json.loads(body) == {"error": "read_only"}


@pytest.mark.parametrize(
    "path",
    [
        "/../../.env",
        "/%2e%2e/.env",
        "/?path=.env",
        "/summary.json?file=.env",
        "/public/",
        "/.env",
        "/server.py",
        "/state",
        "/login",
    ],
)
def test_native_arbitrary_paths_never_read(native_server, monkeypatch, path):
    monkeypatch.setattr(readonly, "load_snapshot", lambda *_a: pytest.fail("no arbitrary source"))
    assert request(native_server, path=path)[0] == 404


@pytest.mark.parametrize(
    "headers",
    [{"Host": "example.invalid"}, {"Origin": "https://example.invalid"}, {"Origin": "null"}],
)
def test_native_host_and_origin_rejected(native_server, headers):
    assert request(native_server, headers=headers)[0] == 403


def test_duplicate_host_rejected(native_server):
    with socket.create_connection(("127.0.0.1", native_server.server_port), timeout=3) as client:
        host = native_server.expected_host.encode()
        client.sendall(b"GET / HTTP/1.0\r\nHost: " + host + b"\r\nHost: " + host + b"\r\n\r\n")
        assert client.recv(4096).startswith(b"HTTP/1.0 403")


def test_unknown_source_health_is_not_financial_evidence(native_server, public_root):
    (public_root / readonly.SUMMARY_NAME).write_text('{"private_amount":123}', encoding="ascii")
    for method in ("GET", "HEAD"):
        status, _, body = request(native_server, method, "/summary.json")
        assert status == 503
        if method == "GET":
            assert b"private_amount" not in body and b"123" not in body
            assert json.loads(body)["counts"]["runs"] is None
        else:
            assert body == b""
    assert request(native_server, path="/health")[0] == 200


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.1", "localhost"])
def test_no_non_loopback_bind(public_root, host):
    with pytest.raises(ValueError, match="loopback_required"):
        readonly.ReadonlyServer(public_root, host=host, port=0)


def test_default_bind_is_loopback(public_root):
    with readonly.ReadonlyServer(public_root, port=0) as server:
        assert server.server_address[0] == "127.0.0.1"
        assert server.expected_host == f"127.0.0.1:{server.server_port}"


@pytest.mark.parametrize("in_container", [False, True])
def test_container_wildcard_without_flag_rejected_before_bind(
    public_root, monkeypatch, in_container
):
    monkeypatch.setattr(readonly, "_is_container_runtime", lambda: in_container)
    monkeypatch.setattr(
        readonly.ThreadingHTTPServer, "__init__", lambda *_a, **_k: pytest.fail("no host bind")
    )
    with pytest.raises(ValueError, match="loopback_required"):
        readonly.ReadonlyServer(public_root, host="0.0.0.0")


def test_container_flag_outside_container_rejected_before_bind(public_root, monkeypatch):
    monkeypatch.setattr(readonly, "_is_container_runtime", lambda: False)
    monkeypatch.setattr(
        readonly.ThreadingHTTPServer, "__init__", lambda *_a, **_k: pytest.fail("no host bind")
    )
    with pytest.raises(ValueError, match="loopback_required"):
        readonly.ReadonlyServer(public_root, host="0.0.0.0", allow_container_bind=True)


def test_approved_container_bind_declaration_uses_strict_loopback_host(public_root, monkeypatch):
    # Exercise the exact constructor without ever binding a wildcard on the host.
    addresses = []

    def declared(server, address, handler):
        addresses.append((address, handler))
        server.server_port = address[1]

    monkeypatch.setattr(readonly, "_is_container_runtime", lambda: True)
    monkeypatch.setattr(readonly.ThreadingHTTPServer, "__init__", declared)
    server = readonly.ReadonlyServer(
        public_root, host="0.0.0.0", port=8788, allow_container_bind=True
    )
    assert addresses == [(("0.0.0.0", 8788), readonly.ReadonlyHandler)]
    assert server.expected_host == "127.0.0.1:8788"


@pytest.mark.parametrize("port", [0, 8787, 8789])
def test_container_mapping_requires_same_qualified_8788_port(public_root, monkeypatch, port):
    monkeypatch.setattr(readonly, "_is_container_runtime", lambda: True)
    monkeypatch.setattr(
        readonly.ThreadingHTTPServer, "__init__", lambda *_a, **_k: pytest.fail("no host bind")
    )
    with pytest.raises(ValueError, match="container_port_must_be_8788"):
        readonly.ReadonlyServer(public_root, host="0.0.0.0", port=port, allow_container_bind=True)


def test_container_cli_passes_explicit_flag_without_a_wildcard_host_listener(
    public_root, monkeypatch
):
    captured = []

    class DeclaredServer:
        def __init__(self, root, **kwargs):
            captured.append((root, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def serve_forever(self):
            pass

    monkeypatch.setattr(readonly, "ReadonlyServer", DeclaredServer)
    assert (
        readonly.main(
            ["--public-root", str(public_root), "--host", "0.0.0.0", "--allow-container-bind"]
        )
        == 0
    )
    assert captured == [
        (public_root, {"host": "0.0.0.0", "port": 8788, "allow_container_bind": True})
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "0.0.0.0:8788"},
        {"Host": "127.0.0.1:8787"},
        {"Host": "example.invalid:8788"},
        {"Origin": "http://0.0.0.0:8788"},
        {"Origin": "http://127.0.0.1:8787"},
    ],
)
def test_container_mode_never_relaxes_native_host_or_origin_checks(
    native_server, public_root, monkeypatch, headers
):
    monkeypatch.setattr(readonly, "_is_container_runtime", lambda: True)
    native_server.expected_host = "127.0.0.1:8788"
    supplied = {"Host": "127.0.0.1:8788", **headers}
    assert request(native_server, headers=supplied)[0] == 403


def test_native_container_host_contract_accepts_only_matching_loopback_origin(native_server):
    # The socket remains on loopback/port0; this checks the forwarded HTTP contract.
    native_server.expected_host = "127.0.0.1:8788"
    status, _, _ = request(
        native_server,
        headers={"Host": "127.0.0.1:8788", "Origin": "http://127.0.0.1:8788"},
    )
    assert status == 200


def test_fixed_refresh_get_preserves_stale_asof(native_server, public_summary):
    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.refresh = []

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == "meta" and attributes.get("http-equiv", "").lower() == "refresh":
                self.refresh.append(attributes.get("content"))

    for _ in range(2):
        status, _, body = request(native_server)
        assert status == 200
        tags = Tags()
        tags.feed(body.decode("utf-8"))
        assert tags.refresh == ["30;url=/"]
        assert "STALE" in body.decode("utf-8")
        _, _, api = request(native_server, path="/summary.json")
        payload = json.loads(api)
        assert payload["as_of"] == public_summary["as_of"]
        assert payload["source_state"] == "stale"
        assert payload["readonly"] is True and payload["control"]["available"] is False


def test_explicit_public_root_and_cli_only(tmp_path):
    with pytest.raises(ValueError, match="absolute_public_root_required"):
        readonly.ReadonlyServer(Path("relative"), port=0)
    with pytest.raises(SystemExit):
        readonly.main([])
    with pytest.raises(SystemExit):
        readonly.main(["--public-root", str(tmp_path), "--host", "0.0.0.0"])


def test_korean_view_unknown_stale_rollover_and_disabled_controls(public_root):
    snapshot = readonly.load_snapshot(public_root, now=AS_OF + timedelta(hours=1)).to_dict()
    html = render_readonly_dashboard(snapshot)
    assert '<html lang="ko">' in html
    assert "STALE" in html and "현재 상태 미확인" in html
    assert "2025-01-04 05:54:00 KST" in html and "2025-01-03 20:54:00 UTC" in html
    assert "2025-01-02 00:17:00 KST" in html
    assert "missing_runtime_files" in html and "금융 결과 아님" in html
    assert 'class="details installation"' in html and "<details open" not in html
    assert "설치 ≠ 실행·체결" in html
    assert "PAUSE_REQUESTED" in html and "실행기 확인" in html and "UNKNOWN" in html
    assert "<fieldset disabled>" in html and 'type="button" disabled' in html
    assert not any(tag in html for tag in ("<script", "<form", "<iframe", "<img", "<object"))


def test_import_and_runtime_authority_surface_is_only_stdlib_and_own_view():
    source = Path(readonly.__file__).read_text(encoding="utf-8")
    allowed = {
        "__future__",
        "argparse",
        "copy",
        "json",
        "os",
        "re",
        "stat",
        "sys",
        "dataclasses",
        "datetime",
        "http.server",
        "pathlib",
        "typing",
        "thericher_v2.dashboard.readonly_view",
        "readonly_view",
    }
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert not (node.value.id == "os" and node.attr in {"environ", "getenv", "system"})
    assert "importlib" not in source and "subprocess" not in source


def test_direct_isolated_entry_avoids_legacy_dashboard_initializer(tmp_path):
    source_directory = str(Path(readonly.__file__).resolve().parent)
    code = (
        "import sys;sys.path.append(" + repr(source_directory) + ");"
        "import readonly_server;"
        "assert not any(n.startswith('thericher_v2') for n in sys.modules);"
        "assert 'readonly_view' in sys.modules;"
        "assert readonly_server.render_readonly_dashboard.__module__ == 'readonly_view'"
    )
    environment = {k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ}
    environment.update(TEMP=str(tmp_path), TMP=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", code],
        env=environment,
        capture_output=True,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0
    assert result.stdout == b"" and result.stderr == b""
