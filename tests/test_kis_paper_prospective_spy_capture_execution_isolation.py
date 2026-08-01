from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_MODULE = "thericher_v2.data.kis_paper_prospective_spy_capture"


def test_capture_runner_import_has_no_external_side_effects() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _IMPORT_SCRIPT,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {"imported": _MODULE}


def test_capture_returns_only_a_receipt_without_network_environment_or_broker_behavior(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    artifact_root = tmp_path / "external-artifacts"
    cache_root = tmp_path / "external-market-data"
    repository.mkdir()
    artifact_root.mkdir()
    cache_root.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _CAPTURE_SCRIPT,
            str(repository),
            str(artifact_root),
            str(cache_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "artifact_file_count": 1,
        "receipt_only": True,
        "status": "captured",
    }


_CAPTURE_SCRIPT = r'''
import builtins
import io
import json
import os
import socket
import sys
import urllib.request
from datetime import UTC, date, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session


def fail_external(*_args, **_kwargs):
    raise AssertionError("SPY capture must not open a network connection")


def fail_environment(*_args, **_kwargs):
    raise AssertionError("SPY capture must not read environment credentials")


class DeniedEnvironment:
    def __getitem__(self, _key):
        fail_environment()

    def get(self, _key, _default=None):
        fail_environment()

    def __contains__(self, _key):
        fail_environment()


original_open = builtins.open
original_io_open = io.open
original_path_open = Path.open


def reject_dotenv(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("SPY capture must not read .env")
    return original_open(file, *args, **kwargs)


def reject_dotenv_io(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("SPY capture must not read .env")
    return original_io_open(file, *args, **kwargs)


def reject_dotenv_path(path, *args, **kwargs):
    if path.name.casefold().endswith(".env"):
        raise AssertionError("SPY capture must not read .env")
    return original_path_open(path, *args, **kwargs)


builtins.open = reject_dotenv
io.open = reject_dotenv_io
Path.open = reject_dotenv_path
socket.socket = fail_external
socket.create_connection = fail_external
urllib.request.urlopen = fail_external
os.getenv = fail_environment
os.environ = DeniedEnvironment()

import thericher_v2.data.kis_paper_prospective_spy_capture as capture

repository = Path(sys.argv[1])
artifact_root = Path(sys.argv[2])
cache_root = Path(sys.argv[3])
session_date = date(2026, 7, 20)
session = us_equity_2026_session(session_date)
assert session is not None and session.kind == "regular"
cutoff = session.window.open_ts + timedelta(hours=6)
bars = tuple(
    Bar(
        symbol="SPY",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=session.window.open_ts + timedelta(minutes=index),
        open=Decimal("913.111") + Decimal(index) / Decimal("100"),
        high=Decimal("914.111") + Decimal(index) / Decimal("100"),
        low=Decimal("912.111") + Decimal(index) / Decimal("100"),
        close=Decimal("913.611") + Decimal(index) / Decimal("100"),
        volume=Decimal("7777"),
        complete=True,
    )
    for index in range((cutoff - session.window.open_ts) // timedelta(minutes=1))
)
catalog = _cataloged_bars_from_verified_loader(
    dataset_id="kis.paper.private.intraday.spy.ams.m1.unit-v1",
    dataset_hash="sha256:" + "a" * 64,
    source_path=cache_root / "unit-index.json",
    bars=bars,
)


def load_verified_catalog(**kwargs):
    assert kwargs == {
        "cache_root": cache_root,
        "repo_root": repository.resolve(),
        "symbol": "SPY",
        "exchange": "AMS",
    }
    return catalog


capture.load_verified_kis_paper_private_intraday_catalog = load_verified_catalog
result = capture.capture_kis_paper_prospective_spy_observation(
    cache_root=cache_root,
    artifact_root=artifact_root,
    repo_root=repository,
    session_date=session_date,
    observed_at=cutoff + timedelta(minutes=1),
)

assert result.status == "captured"
assert result.receipt is not None
assert result.artifact_path is not None and result.artifact_path.is_file()
assert not any(
    hasattr(result, field)
    for field in ("proposal", "intent", "order", "fill", "broker", "local_paper_replay")
)
payload = result.safe_payload()
encoded = json.dumps(payload, sort_keys=True).casefold()
for forbidden in (
    "913.111",
    "7777",
    "account",
    "broker",
    "credential",
    "fill",
    "intent",
    "local_paper",
    "order",
    "path",
    "price",
    "token",
    "volume",
):
    assert forbidden not in encoded
assert result.artifact_path.read_text(encoding="utf-8") == result.receipt.canonical_json() + "\n"
print(json.dumps({
    "artifact_file_count": sum(path.is_file() for path in artifact_root.rglob("*")),
    "receipt_only": True,
    "status": result.status,
}, sort_keys=True))
'''


_IMPORT_SCRIPT = rf'''
import builtins
import io
import json
import os
import socket
from pathlib import Path
import urllib.request


def fail_external(*_args, **_kwargs):
    raise AssertionError("SPY capture import must not open a network connection")


def fail_environment(*_args, **_kwargs):
    raise AssertionError("SPY capture import must not read environment credentials")


original_open = builtins.open
original_io_open = io.open
original_path_open = Path.open


def reject_dotenv(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("SPY capture import must not read .env")
    return original_open(file, *args, **kwargs)


def reject_dotenv_io(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("SPY capture import must not read .env")
    return original_io_open(file, *args, **kwargs)


def reject_dotenv_path(path, *args, **kwargs):
    if path.name.casefold().endswith(".env"):
        raise AssertionError("SPY capture import must not read .env")
    return original_path_open(path, *args, **kwargs)


builtins.open = reject_dotenv
io.open = reject_dotenv_io
Path.open = reject_dotenv_path
socket.socket = fail_external
socket.create_connection = fail_external
urllib.request.urlopen = fail_external
os.getenv = fail_environment

import {_MODULE}

print(json.dumps({{"imported": "{_MODULE}"}}, sort_keys=True))
'''
