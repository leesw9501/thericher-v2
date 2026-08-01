from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_MODULE = "thericher_v2.research.tiingo_d1_trend_mean_reversion_rotation"


def test_rotation_import_has_no_external_side_effects() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {"imported": _MODULE}


def test_rotation_evaluation_is_offline_route_free_and_aggregate_only(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    artifact_root = tmp_path / "external-artifacts"
    source_root = tmp_path / "external-source-data"
    repository.mkdir()
    artifact_root.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _EVALUATION_SCRIPT,
            str(repository),
            str(artifact_root),
            str(source_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "artifact_file_count": 2,
        "evaluation_completed": True,
        "route_free": True,
        "status": "falsified",
    }


# `thericher_v2.research` still performs legacy eager imports. The tests below
# guard behavior rather than claiming that those unrelated modules were absent.
_IMPORT_SCRIPT = rf'''
import builtins
import io
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path


def fail_external(*_args, **_kwargs):
    raise AssertionError("Tiingo D1 rotation import must not open a network connection")


def fail_environment(*_args, **_kwargs):
    raise AssertionError("Tiingo D1 rotation import must not read environment credentials")


class CredentialGuardedEnvironment:
    _MARKERS = ("KIS", "TIINGO", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "API_KEY", "ACCOUNT")

    def __init__(self, values):
        self._values = values

    def _guard(self, key):
        if isinstance(key, str) and any(marker in key.upper() for marker in self._MARKERS):
            fail_environment()

    def __getitem__(self, key):
        self._guard(key)
        return self._values[key]

    def get(self, key, default=None):
        self._guard(key)
        return self._values.get(key, default)

    def __contains__(self, key):
        self._guard(key)
        return key in self._values


original_open = builtins.open
original_io_open = io.open
original_path_open = Path.open
original_getenv = os.getenv


def reject_dotenv(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("Tiingo D1 rotation import must not read .env")
    return original_open(file, *args, **kwargs)


def reject_dotenv_io(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("Tiingo D1 rotation import must not read .env")
    return original_io_open(file, *args, **kwargs)


def reject_dotenv_path(path, *args, **kwargs):
    if path.name.casefold().endswith(".env"):
        raise AssertionError("Tiingo D1 rotation import must not read .env")
    return original_path_open(path, *args, **kwargs)


sys.dont_write_bytecode = True
builtins.open = reject_dotenv
io.open = reject_dotenv_io
Path.open = reject_dotenv_path
socket.socket = fail_external
socket.create_connection = fail_external
urllib.request.urlopen = fail_external
os.environ = CredentialGuardedEnvironment(os.environ)
os.getenv = original_getenv

import {_MODULE}

print(json.dumps({{"imported": "{_MODULE}"}}, sort_keys=True))
'''


_EVALUATION_SCRIPT = r"""
import builtins
import io
import json
import os
import socket
import sys
import urllib.request
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import thericher_v2.research.tiingo_d1_trend_mean_reversion_rotation as rotation
from thericher_v2.data import tiingo_etf_daily


repository = Path(sys.argv[1]).resolve()
artifact_root = Path(sys.argv[2]).resolve()
source_root = Path(sys.argv[3]).resolve()


def fail_external(*_args, **_kwargs):
    raise AssertionError("Tiingo D1 rotation must not call a provider or network")


def fail_environment(*_args, **_kwargs):
    raise AssertionError("Tiingo D1 rotation must not read environment credentials")


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
original_mkdir = Path.mkdir
original_replace = os.replace


def is_artifact_path(candidate):
    return Path(candidate).resolve(strict=False).is_relative_to(artifact_root)


def assert_safe_path(file, mode="r"):
    try:
        candidate = Path(os.fspath(file))
    except TypeError:
        return
    rendered = str(candidate).casefold()
    if rendered.endswith(".env"):
        raise AssertionError("Tiingo D1 rotation must not read .env")
    if "sealed" in rendered:
        raise AssertionError("Tiingo D1 rotation must not access a sealed-tail surface")
    if any(flag in mode for flag in ("w", "a", "x", "+")) and not is_artifact_path(candidate):
        raise AssertionError("Tiingo D1 rotation must not write source data")


def guarded_open(file, *args, **kwargs):
    mode = args[0] if args else kwargs.get("mode", "r")
    assert_safe_path(file, mode)
    return original_open(file, *args, **kwargs)


def guarded_io_open(file, *args, **kwargs):
    mode = args[0] if args else kwargs.get("mode", "r")
    assert_safe_path(file, mode)
    return original_io_open(file, *args, **kwargs)


def guarded_path_open(path, *args, **kwargs):
    mode = args[0] if args else kwargs.get("mode", "r")
    assert_safe_path(path, mode)
    return original_path_open(path, *args, **kwargs)


def guarded_mkdir(path, *args, **kwargs):
    if not is_artifact_path(path):
        raise AssertionError("Tiingo D1 rotation must not create a source-data directory")
    return original_mkdir(path, *args, **kwargs)


def guarded_replace(source, destination, *args, **kwargs):
    if not (is_artifact_path(source) and is_artifact_path(destination)):
        raise AssertionError("Tiingo D1 rotation must not replace source data")
    return original_replace(source, destination, *args, **kwargs)


socket.socket = fail_external
socket.create_connection = fail_external
urllib.request.urlopen = fail_external
os.getenv = fail_environment
os.environ = DeniedEnvironment()
builtins.open = guarded_open
io.open = guarded_io_open
Path.open = guarded_path_open
Path.mkdir = guarded_mkdir
os.replace = guarded_replace
tiingo_etf_daily.acquire_tiingo_etf_d1_snapshot = fail_external
tiingo_etf_daily.load_verified_tiingo_etf_d1_snapshot = fail_external

count = 2400
rows_by_symbol = {}
for symbol in tiingo_etf_daily.TIINGO_ETF_D1_SYMBOLS:
    rows_by_symbol[symbol] = tuple(
        tiingo_etf_daily.TiingoEtfDailyRow(
            symbol=symbol,
            session_date=date(2010, 1, 1) + timedelta(days=index),
            open=price - Decimal("0.01"),
            high=price + Decimal("0.02"),
            low=price - Decimal("0.03"),
            close=price,
            volume=Decimal("24680"),
            div_cash=Decimal("0"),
            split_factor=Decimal("1"),
        )
        for index in range(count)
        for price in (
            Decimal("777.123456")
            + Decimal(index) * Decimal("0.2")
            - Decimal(index % 6) * Decimal("0.5"),
        )
    )

snapshot = tiingo_etf_daily.TiingoEtfDailySnapshot(
    snapshot_dir=source_root / "snapshot=fixture",
    dataset_id="us_equities.tiingo_etf_daily.snapshot=execution-isolation-fixture",
    dataset_hash="sha256:" + "a" * 64,
    manifest_hash="sha256:" + "b" * 64,
    raw_hashes={
        symbol: "sha256:" + character * 64
        for symbol, character in zip(tiingo_etf_daily.TIINGO_ETF_D1_SYMBOLS, "cde", strict=True)
    },
    session_counts={symbol: count for symbol in tiingo_etf_daily.TIINGO_ETF_D1_SYMBOLS},
    date_ranges={
        symbol: (rows[0].session_date, rows[-1].session_date)
        for symbol, rows in rows_by_symbol.items()
    },
    event_session_counts={symbol: 0 for symbol in tiingo_etf_daily.TIINGO_ETF_D1_SYMBOLS},
    row_count=count * len(tiingo_etf_daily.TIINGO_ETF_D1_SYMBOLS),
    free_percent=40.0,
)
loaded = tiingo_etf_daily.LoadedTiingoEtfDailySnapshot(
    snapshot=snapshot,
    rows_by_symbol=rows_by_symbol,
)

forbidden_calls = []


def profile(frame, event, _argument):
    if event != "call":
        return profile
    module_name = str(frame.f_globals.get("__name__", ""))
    receiver = frame.f_locals.get("self")
    receiver_name = type(receiver).__name__.casefold() if receiver is not None else ""
    module_tokens = ("broker", "local_paper", "order", "account")
    receiver_tokens = ("broker", "localpaper", "order", "intent", "fill", "account")
    if (
        module_name.startswith("thericher_v2.execution")
        or any(token in module_name.casefold() for token in module_tokens)
        or any(token in receiver_name for token in receiver_tokens)
    ):
        forbidden_calls.append(f"{module_name}:{frame.f_code.co_name}:{receiver_name}")
    return profile


sys.setprofile(profile)
try:
    prepared = rotation.prepare_tiingo_d1_trend_mean_reversion_rotation(loaded)
    evaluated = rotation.evaluate_tiingo_d1_trend_mean_reversion_rotation(prepared)
    run = rotation.run_tiingo_d1_trend_mean_reversion_rotation(
        loaded,
        artifact_root=artifact_root,
        run_label="execution-isolation",
        repo_root=repository,
    )
finally:
    sys.setprofile(None)

assert not forbidden_calls, forbidden_calls
assert evaluated.status == run.result.status == "falsified"
assert run.precommit_path.is_relative_to(artifact_root)
assert run.summary_path.is_relative_to(artifact_root)
assert not source_root.exists()
assert sorted(path.name for path in artifact_root.rglob("*.json")) == [
    "precommit.json",
    "summary.json",
]

precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
serialized = json.dumps({"precommit": precommit, "summary": summary}, sort_keys=True).casefold()
for forbidden in (
    "777.123456",
    "24680",
    "account",
    "broker",
    "credential",
    "fill",
    "intent",
    "kis_",
    "live",
    "local_paper",
    "\"order\"",
    "token",
    "volume",
):
    assert forbidden not in serialized
assert summary["result"]["raw_market_data_written"] is False
assert summary["result"]["input"]["source"]["sealed_tail_claim_allowed"] is False
assert summary["result"]["paper_input_allowed"] is False
assert summary["result"]["promotion_allowed"] is False

for payload in (precommit, summary):
    keys = []
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            keys.extend(value)
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    assert not {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "div_cash",
        "split_factor",
        "session_date",
        "snapshot_dir",
        "raw_hashes",
    }.intersection(keys)

print(json.dumps({
    "artifact_file_count": sum(path.is_file() for path in artifact_root.rglob("*")),
    "evaluation_completed": True,
    "route_free": True,
    "status": run.result.status,
}, sort_keys=True))
"""
