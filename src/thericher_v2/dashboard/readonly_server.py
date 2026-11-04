"""Local GET/HEAD monitor for an explicitly supplied public summary.

The producer owns public-source qualification. This reader accepts categorical
observations only; it never derives a financial outcome from a Task exit or plan.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if __package__:
    from thericher_v2.dashboard.readonly_view import render_readonly_dashboard
else:
    # Direct -I -S execution avoids the legacy dashboard package initializer.
    sys.path.append(str(Path(__file__).resolve().parent))
    from readonly_view import render_readonly_dashboard

SUMMARY_NAME = "summary.json"
PUBLIC_SCHEMA = "readonly-paper-summary-v1"
MAX_SUMMARY_BYTES = 65536
MAX_RUNS = 20
FRESH_SECONDS = 300
_STAGES = {"producer", "startup", "capture", "entry", "exit"}
_STATUS = {"unknown", "abstain", "not_entered", "technical_failure", "completed"}
_REASONS = {
    "missing_runtime_files",
    "source_metadata_unavailable",
    "guest_fault_unknown",
    "invalid_public_input",
    "runtime_failure",
    "unknown",
}
_FINANCIAL = {
    "submit": {"unknown", "not_attempted", "attempted", "accepted"},
    "fill": {"unknown", "not_observed", "linked"},
    "owned": {"unknown", "not_observed", "observed"},
}
_SLUG = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class InvalidPublicSummary(ValueError):
    """A categorical error, never a raw payload or private exception message."""


def _require(condition: bool) -> None:
    if not condition:
        raise InvalidPublicSummary("invalid_public_summary")


def _object(value: Any, keys: set[str]) -> None:
    _require(type(value) is dict and set(value) == keys)


def _choice(value: Any, allowed: set[str]) -> None:
    _require(type(value) is str and value in allowed)


def _clock(value: Any) -> datetime:
    _require(type(value) is str and len(value) <= 40)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidPublicSummary("invalid_public_summary") from None
    _require(result.utcoffset() is not None and 2000 <= result.year <= 2100)
    return result.astimezone(UTC)


def _slug(value: Any) -> None:
    _require(type(value) is str and _SLUG.fullmatch(value) is not None)


def _label(value: Any) -> None:
    _require(type(value) is str and 0 < len(value) <= 48 and value == value.strip())
    _require(all(c.isalnum() or c in " _-()." for c in value))


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise InvalidPublicSummary("invalid_public_summary")


def parse_public_summary(raw: bytes) -> dict[str, Any]:
    """Validate the finite public DTO, without imports, paths or executable hooks."""
    _require(type(raw) is bytes and len(raw) <= MAX_SUMMARY_BYTES)
    try:
        value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise InvalidPublicSummary("invalid_public_summary") from None
    _object(value, {"schema", "as_of", "runs", "control"})
    _require(value["schema"] == PUBLIC_SCHEMA)
    as_of = _clock(value["as_of"])
    runs = value["runs"]
    _require(type(runs) is list and len(runs) <= MAX_RUNS)
    seen: set[str] = set()
    for run in runs:
        _object(run, {"key", "label", "installation", "plan", "outcome", "financial", "evidence"})
        _slug(run["key"])
        _require(run["key"] not in seen)
        seen.add(run["key"])
        _label(run["label"])
        _choice(run["installation"], {"unknown", "installed", "not_installed"})
        _require(type(run["plan"]) is list and len(run["plan"]) <= len(_STAGES))
        stages: set[str] = set()
        for event in run["plan"]:
            _object(event, {"stage", "at"})
            _choice(event["stage"], _STAGES)
            _require(event["stage"] not in stages)
            stages.add(event["stage"])
            _clock(event["at"])
        actual = run["outcome"]
        _object(actual, {"status", "observed_at", "failure", "task_exit_codes"})
        _choice(actual["status"], _STATUS)
        if actual["observed_at"] is not None:
            _require(_clock(actual["observed_at"]) <= as_of)
        failure = actual["failure"]
        if failure is not None:
            _object(failure, {"reason", "exception", "stage"})
            _choice(failure["reason"], _REASONS)
            _choice(failure["exception"], {"unknown", "key_error", "value_error", "runtime_error"})
            _choice(failure["stage"], {"unknown", "pre_model", "startup", "admission", "runtime"})
            _require(actual["status"] != "completed")
        codes = actual["task_exit_codes"]
        _require(type(codes) is list and len(codes) <= 3)
        _require(all(c is None or (type(c) is int and -(2**31) <= c < 2**32) for c in codes))
        evidence = run["evidence"]
        _object(evidence, {"kind", "reference", "sha256"})
        _choice(evidence["kind"], {"public_outcome", "technical_diagnosis", "task_metadata"})
        _slug(evidence["reference"])
        digest = evidence["sha256"]
        _require(digest is None or (type(digest) is str and _DIGEST.fullmatch(digest) is not None))
        financial = run["financial"]
        _object(financial, set(_FINANCIAL))
        for field, allowed in _FINANCIAL.items():
            _choice(financial[field], allowed)
        if any(v != "unknown" for v in financial.values()):
            _require(
                evidence["kind"] == "public_outcome"
                and evidence["sha256"] is not None
                and actual["observed_at"] is not None
            )
    control = value["control"]
    _object(control, {"saved_request", "worker_ack"})
    _choice(control["saved_request"], {"unknown", "none", "pause_requested", "resume_requested"})
    _choice(control["worker_ack"], {"unknown", "acknowledged", "not_acknowledged"})
    return value


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_nlink)


def _ordinary_root(root: Path) -> list[tuple[int, ...]]:
    _require(root.is_absolute())
    result = []
    for part in (root, *root.parents):
        info = part.lstat()
        _require(stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 1024)
        result.append(_identity(info))
    return result


def read_public_summary(public_root: Path) -> bytes:
    """Read only summary.json, rejecting aliases, hardlinks and unstable reads."""
    root = Path(public_root)
    parents = _ordinary_root(root)
    path = root / SUMMARY_NAME
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1)
    _require(not getattr(before, "st_file_attributes", 0) & 1024)
    _require(before.st_size <= MAX_SUMMARY_BYTES)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        _require(_identity(before) == _identity(opened))
        chunks = []
        remaining = MAX_SUMMARY_BYTES + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        _require(len(raw) <= MAX_SUMMARY_BYTES)
        _require(_identity(opened) == _identity(os.fstat(fd)) == _identity(path.lstat()))
        _require(parents == _ordinary_root(root))
        return raw
    finally:
        os.close(fd)


@dataclass(frozen=True)
class ReadonlySnapshot:
    source_state: str
    summary: dict[str, Any] | None = None
    age_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        summary = self.summary
        return {
            "schema": "readonly-paper-snapshot-v1",
            "source_state": self.source_state,
            "as_of": None if summary is None else summary["as_of"],
            "age_seconds": self.age_seconds,
            "counts": {"runs": None if summary is None else len(summary["runs"])},
            "runs": [] if summary is None else copy.deepcopy(summary["runs"]),
            "control": {
                "available": False,
                **(
                    {"saved_request": "unknown", "worker_ack": "unknown"}
                    if summary is None
                    else summary["control"]
                ),
            },
            "broker_calls": False,
            "readonly": True,
        }


def load_snapshot(public_root: Path, *, now: datetime | None = None) -> ReadonlySnapshot:
    now = datetime.now(UTC) if now is None else now
    try:
        _require(now.utcoffset() is not None)
        value = parse_public_summary(read_public_summary(public_root))
        elapsed = (now - _clock(value["as_of"])).total_seconds()
        _require(elapsed >= 0)
        return ReadonlySnapshot(
            "fresh" if elapsed <= FRESH_SECONDS else "stale", value, int(elapsed)
        )
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return ReadonlySnapshot("unknown")


class ReadonlyHandler(BaseHTTPRequestHandler):
    server: ReadonlyServer

    def setup(self) -> None:
        self.request.settimeout(2.0)
        super().setup()

    def log_message(self, _format: str, *_args: object) -> None:
        """Never retain URLs, headers, request bodies or source exceptions."""

    def send_error(self, code: int, *_args: object, **_kwargs: object) -> None:
        self._reply(code, b'{"error":"request_rejected"}', "application/json")

    def _reply(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802
        host = self.server.expected_host
        if self.headers.get_all("Host", []) != [host] or self.headers.get_all(
            "Origin", ["http://" + host]
        ) != ["http://" + host]:
            self._reply(403, b'{"error":"request_rejected"}', "application/json")
            return
        if self.path == "/health":
            self._reply(
                200, b'{"status":"ok","readonly":true,"broker_calls":false}', "application/json"
            )
            return
        if self.path not in ("/", "/summary.json"):
            self._reply(404, b'{"error":"not_found"}', "application/json")
            return
        value = load_snapshot(self.server.public_root).to_dict()
        status = 503 if value["source_state"] == "unknown" else 200
        if self.path == "/summary.json":
            self._reply(
                status, json.dumps(value, sort_keys=True).encode("utf-8"), "application/json"
            )
        else:
            self._reply(
                status, render_readonly_dashboard(value).encode("utf-8"), "text/html; charset=utf-8"
            )

    do_HEAD = do_GET  # noqa: N815

    def _reject_method(self) -> None:
        self._reply(405, b'{"error":"read_only"}', "application/json")

    def __getattr__(self, name: str) -> Any:
        if name.startswith("do_"):
            return self._reject_method
        raise AttributeError(name)


class ReadonlyServer(ThreadingHTTPServer):
    """A separate server, with no execution/control stores or environment loading."""

    def __init__(
        self,
        public_root: Path,
        *,
        host: str = "127.0.0.1",
        port: int = 8788,
        allow_container_bind: bool = False,
    ) -> None:
        host = _validated_bind_host(host, allow_container_bind=allow_container_bind)
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("invalid_port")
        if host == "0.0.0.0" and port != 8788:
            raise ValueError("container_port_must_be_8788")
        self.public_root = Path(public_root)
        if not self.public_root.is_absolute():
            raise ValueError("absolute_public_root_required")
        super().__init__((host, port), ReadonlyHandler)
        self.expected_host = f"127.0.0.1:{self.server_port}"


def _validated_bind_host(host: str, *, allow_container_bind: bool) -> str:
    """The opt-in is not proof of host publication; deployment must attest that tuple."""
    if host == "127.0.0.1":
        return host
    if host == "0.0.0.0" and allow_container_bind is True and _is_container_runtime():
        return host
    raise ValueError("loopback_required_container_bind_needs_explicit_flag_and_container")


def _is_container_runtime() -> bool:
    return Path("/.dockerenv").is_file()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local readonly public Paper monitor")
    parser.add_argument("--public-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "0.0.0.0"])
    parser.add_argument(
        "--allow-container-bind",
        action="store_true",
        help="allow Docker-only 0.0.0.0:8788 behind a qualified 127.0.0.1:8788 publish",
    )
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args(argv)
    try:
        server = ReadonlyServer(
            args.public_root,
            host=args.host,
            port=args.port,
            allow_container_bind=args.allow_container_bind,
        )
    except ValueError as error:
        parser.error(str(error))
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
