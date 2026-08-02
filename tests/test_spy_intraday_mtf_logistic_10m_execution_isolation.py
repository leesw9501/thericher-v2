from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_MODULE = "thericher_v2.research.spy_intraday_mtf_logistic_10m"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = (
    _REPOSITORY_ROOT / "src" / "thericher_v2" / "research" / "spy_intraday_mtf_logistic_10m.py"
)
_RUNNER = _REPOSITORY_ROOT / "scripts" / "run_spy_intraday_mtf_logistic_10m.py"

pytestmark = pytest.mark.skipif(
    not (_SOURCE.is_file() and _RUNNER.is_file()),
    reason="awaiting the Engine Research module and its CLI runner",
)


def test_mtf_logistic_import_and_runner_help_are_side_effect_free() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_AND_HELP_SCRIPT, str(_RUNNER)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {
        "imported": _MODULE,
        "runner_help": True,
    }


def test_mtf_logistic_is_offline_route_free_and_artifact_safe(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source_root = tmp_path / "external-market-data"
    repository.mkdir()

    # This root is intentionally outside the repository and pytest's managed
    # temp tree. The subprocess denies every write except aggregate receipts here.
    with tempfile.TemporaryDirectory(prefix="thericher-isolation-") as external_root:
        artifact_root = Path(external_root)
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                _EVALUATION_AND_RUNNER_SCRIPT,
                str(repository),
                str(artifact_root),
                str(source_root),
                str(_RUNNER),
            ],
            capture_output=True,
            text=True,
        )

        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)

    assert result["artifact_file_count"] == 4
    assert result["evaluation_completed"] is True
    assert result["route_free"] is True
    assert result["status"] in {
        "falsified",
        "input_unavailable",
        "non_promoting_validation",
    }


_IMPORT_AND_HELP_SCRIPT = rf'''
import builtins
import importlib.util
import io
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path


def fail_external(*_args, **_kwargs):
    raise AssertionError("MTF logistic import must not use a network")


class CredentialGuardedEnvironment:
    _MARKERS = (
        "ACCOUNT",
        "API_KEY",
        "CREDENTIAL",
        "KIS",
        "PASSWORD",
        "SECRET",
        "TIINGO",
        "TOKEN",
    )

    def __init__(self, values):
        self._values = values

    def _guard(self, key):
        if isinstance(key, str) and any(marker in key.upper() for marker in self._MARKERS):
            raise AssertionError("MTF logistic import must not read credentials")

    def __getitem__(self, key):
        self._guard(key)
        return self._values[key]

    def get(self, key, default=None):
        self._guard(key)
        return self._values.get(key, default)

    def __contains__(self, key):
        self._guard(key)
        return key in self._values

    def setdefault(self, key, default=None):
        self._guard(key)
        return self._values.setdefault(key, default)


original_import = builtins.__import__
original_open = builtins.open
original_io_open = io.open
original_path_open = Path.open


def guarded_import(name, *args, **kwargs):
    if name.partition(".")[0] in {{"torch", "tensorflow", "cupy", "jax"}}:
        raise AssertionError("MTF logistic import must remain CPU-only")
    return original_import(name, *args, **kwargs)


def reject_dotenv(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("MTF logistic import must not read .env")
    return original_open(file, *args, **kwargs)


def reject_dotenv_io(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("MTF logistic import must not read .env")
    return original_io_open(file, *args, **kwargs)


def reject_dotenv_path(path, *args, **kwargs):
    if path.name.casefold().endswith(".env"):
        raise AssertionError("MTF logistic import must not read .env")
    return original_path_open(path, *args, **kwargs)


sys.dont_write_bytecode = True
builtins.__import__ = guarded_import
builtins.open = reject_dotenv
io.open = reject_dotenv_io
Path.open = reject_dotenv_path
socket.socket = fail_external
socket.create_connection = fail_external
urllib.request.urlopen = fail_external
os.environ = CredentialGuardedEnvironment(os.environ)

import {_MODULE}

runner_spec = importlib.util.spec_from_file_location("mtf_logistic_runner", sys.argv[1])
assert runner_spec is not None and runner_spec.loader is not None
runner = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner)
try:
    runner.main(["--help"])
except SystemExit as error:
    assert error.code == 0
else:
    raise AssertionError("runner --help must terminate through argparse")

print(json.dumps({{"imported": "{_MODULE}", "runner_help": True}}, sort_keys=True))
'''


_EVALUATION_AND_RUNNER_SCRIPT = rf"""
import builtins
import contextlib
import importlib.util
import io
import json
import os
import socket
import sys
import urllib.request
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
import {_MODULE} as research


repository = Path(sys.argv[1]).resolve()
artifact_root = Path(sys.argv[2]).resolve()
source_root = Path(sys.argv[3]).resolve()
runner_path = Path(sys.argv[4]).resolve()


def fail_external(*_args, **_kwargs):
    raise AssertionError("MTF logistic must not use KIS or a network")


def fail_environment(*_args, **_kwargs):
    raise AssertionError("MTF logistic must not read environment credentials")


class CredentialGuardedEnvironment:
    _MARKERS = (
        "ACCOUNT",
        "API_KEY",
        "CREDENTIAL",
        "KIS",
        "PASSWORD",
        "SECRET",
        "TIINGO",
        "TOKEN",
    )

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

    def setdefault(self, key, default=None):
        self._guard(key)
        return self._values.setdefault(key, default)


def regular_sessions():
    current = date(2026, 6, 22)
    last = date(2026, 7, 21)
    selected = []
    while current <= last:
        session = us_equity_2026_session(current)
        if session is not None and session.kind == "regular":
            selected.append(session)
        current += timedelta(days=1)
    assert len(selected) == 21
    return tuple(selected)


def session_bars(session, session_index):
    values = []
    base = Decimal("901.111") + Decimal(session_index)
    for minute in range(390):
        ten_minute_phase = (minute // 10 + session_index) % 4
        direction = Decimal("1") if ten_minute_phase in {{0, 1}} else Decimal("-1")
        within_block = Decimal(minute % 10)
        price = base + Decimal(minute) / Decimal("100") + direction * within_block / Decimal("20")
        values.append(
            Bar(
                symbol="SPY",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                open=price,
                high=price + Decimal("0.010"),
                low=price - Decimal("0.010"),
                close=price,
                volume=Decimal("7654"),
                complete=True,
            )
        )
    return tuple(values)


all_bars = []
for index, session in enumerate(regular_sessions()):
    all_bars.extend(session_bars(session, index))

catalog = _cataloged_bars_from_verified_loader(
    dataset_id="kis.paper.private.intraday.spy.ams.m1.v1",
    dataset_hash="sha256:64f149f5ff1c9002107f001a44f78c54c8944e9c030d6153898b1229d9c742e6",
    source_path=source_root / "unwritten-index.json",
    bars=tuple(all_bars),
)

original_import = builtins.__import__
original_open = builtins.open
original_io_open = io.open
original_path_open = Path.open
original_mkdir = Path.mkdir
original_os_mkdir = os.mkdir
original_replace = os.replace
original_getenv = os.getenv


def guarded_import(name, *args, **kwargs):
    if name.partition(".")[0] in {{"torch", "tensorflow", "cupy", "jax"}}:
        raise AssertionError("MTF logistic must not import a GPU runtime")
    return original_import(name, *args, **kwargs)


def is_artifact_path(candidate):
    return Path(candidate).resolve(strict=False).is_relative_to(artifact_root)


def assert_safe_path(file, mode="r"):
    try:
        candidate = Path(os.fspath(file))
    except TypeError:
        return
    lower_name = candidate.name.casefold()
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("MTF logistic must not read .env")
    if any(flag in mode for flag in ("w", "a", "x", "+")):
        if not is_artifact_path(candidate):
            raise AssertionError("MTF logistic must not write source data or repository files")
        if lower_name.endswith(
            (".ckpt", ".joblib", ".onnx", ".pkl", ".pt", ".pth", ".safetensors")
        ):
            raise AssertionError("MTF logistic must not write model weights")


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
        raise AssertionError("MTF logistic must not create source or repository paths")
    return original_mkdir(path, *args, **kwargs)


def guarded_os_mkdir(path, *args, **kwargs):
    if not is_artifact_path(path):
        raise AssertionError("MTF logistic must not create source or repository paths")
    return original_os_mkdir(path, *args, **kwargs)


def guarded_replace(source, destination, *args, **kwargs):
    if not (is_artifact_path(source) and is_artifact_path(destination)):
        raise AssertionError("MTF logistic must not replace source data")
    return original_replace(source, destination, *args, **kwargs)


def guarded_getenv(key, default=None):
    if isinstance(key, str) and any(
        marker in key.upper() for marker in CredentialGuardedEnvironment._MARKERS
    ):
        fail_environment()
    return original_getenv(key, default)


builtins.__import__ = guarded_import
socket.socket = fail_external
socket.create_connection = fail_external
urllib.request.urlopen = fail_external
os.getenv = guarded_getenv
os.environ = CredentialGuardedEnvironment(os.environ)
builtins.open = guarded_open
io.open = guarded_io_open
Path.open = guarded_path_open
Path.mkdir = guarded_mkdir
os.mkdir = guarded_os_mkdir
os.replace = guarded_replace

import thericher_v2.data.kis_paper_intraday as kis_paper_intraday
kis_paper_intraday.load_verified_kis_paper_private_intraday_catalog = fail_external

forbidden_calls = []


def profile(frame, event, _argument):
    if event != "call":
        return profile
    module_name = str(frame.f_globals.get("__name__", "")).casefold()
    receiver = frame.f_locals.get("self")
    receiver_name = type(receiver).__name__.casefold() if receiver is not None else ""
    if (
        module_name.startswith("thericher_v2.execution")
        or any(token in module_name for token in ("broker", "local_paper", "order", "account"))
        or any(
            token in receiver_name
            for token in ("account", "broker", "fill", "intent", "localpaper", "order")
        )
    ):
        forbidden_calls.append(f"{{module_name}}:{{frame.f_code.co_name}}:{{receiver_name}}")
    return profile


sys.setprofile(profile)
try:
    prepared = research.prepare_spy_intraday_mtf_logistic_10m(catalog)
    fitted = research.fit_spy_intraday_mtf_logistic_10m(prepared)
    evaluated = research.evaluate_spy_intraday_mtf_logistic_10m(prepared, fitted)
    direct = research.run_spy_intraday_mtf_logistic_10m(
        catalog,
        artifact_root=artifact_root,
        run_label="execution-isolation-direct",
        repo_root=repository,
    )

    runner_spec = importlib.util.spec_from_file_location("mtf_logistic_runner", runner_path)
    assert runner_spec is not None and runner_spec.loader is not None
    runner = importlib.util.module_from_spec(runner_spec)
    runner_spec.loader.exec_module(runner)
    loader_calls = []

    def load_catalog(**kwargs):
        loader_calls.append(kwargs)
        return catalog

    runner.load_verified_kis_paper_private_intraday_catalog = load_catalog
    with contextlib.redirect_stdout(io.StringIO()):
        runner.main(
            [
                "--run-label",
                "execution-isolation-runner",
                "--cache-root",
                str(source_root),
                "--artifact-root",
                str(artifact_root),
            ]
        )
finally:
    sys.setprofile(None)

assert not forbidden_calls, forbidden_calls
assert evaluated.status == direct.result.status
assert direct.precommit_path.is_relative_to(artifact_root)
assert direct.summary_path.is_relative_to(artifact_root)
assert len(loader_calls) == 1
assert loader_calls[0]["symbol"] == "SPY"
assert loader_calls[0]["exchange"] == "AMS"
assert not source_root.exists()

artifact_files = tuple(sorted(artifact_root.rglob("*.json")))
assert len(artifact_files) == 4
serialized = "\n".join(path.read_text(encoding="utf-8") for path in artifact_files).casefold()
for forbidden in (
    "901.111",
    "7654",
    "account",
    "broker",
    "credential",
    "fill",
    "intent",
    "local_paper",
    "\\\"order\\\"",
    "token",
    "volume",
):
    assert forbidden not in serialized

for payload_path in artifact_files:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    pending = [payload]
    keys = []
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            keys.extend(value)
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    assert not {{
        "close",
        "coefficient",
        "high",
        "intercept",
        "label",
        "low",
        "open",
        "prediction",
        "session_date",
        "source_path",
        "start_ts",
        "timestamp",
        "volume",
    }}.intersection(keys)
    assert "raw_market_data_written" not in payload or payload["raw_market_data_written"] is False

assert not any(
    hasattr(direct, field)
    for field in ("account", "broker", "fill", "intent", "local_paper", "order")
)

print(json.dumps({{
    "artifact_file_count": len(artifact_files),
    "evaluation_completed": True,
    "route_free": True,
    "status": direct.result.status,
}}, sort_keys=True))
"""
