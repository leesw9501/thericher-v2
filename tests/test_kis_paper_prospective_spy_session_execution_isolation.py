from __future__ import annotations

import json
import subprocess
import sys

_MODULE = "thericher_v2.execution.kis_paper_prospective_spy_session"


def test_prospective_session_import_has_no_external_side_effects() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {"imported": _MODULE}


_IMPORT_SCRIPT = rf'''
import builtins
import io
import json
import os
import socket
import urllib.request
from pathlib import Path


def fail_external(*_args, **_kwargs):
    raise AssertionError("prospective SPY session import must not open a network connection")


def fail_environment(*_args, **_kwargs):
    raise AssertionError("prospective SPY session import must not read environment credentials")


class DeniedEnvironment:
    def __getitem__(self, _key):
        _deny_secret(_key)
        raise KeyError(_key)

    def get(self, _key, _default=None):
        _deny_secret(_key)
        return _default

    def __contains__(self, _key):
        _deny_secret(_key)
        return False


def _deny_secret(key):
    if key in {{
        "KIS_PAPER_APP_KEY",
        "KIS_PAPER_APP_SECRET",
        "KIS_PAPER_ACCOUNT_NO",
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE",
        "KIS_LIVE_APP_KEY",
        "KIS_LIVE_APP_SECRET",
        "KIS_LIVE_ACCOUNT_NO",
        "KIS_LIVE_ACCOUNT_PRODUCT_CODE",
    }}:
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
        raise AssertionError("prospective SPY session import must not read .env")
    return original_open(file, *args, **kwargs)


def reject_dotenv_io(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("prospective SPY session import must not read .env")
    return original_io_open(file, *args, **kwargs)


def reject_dotenv_path(path, *args, **kwargs):
    if path.name.casefold().endswith(".env"):
        raise AssertionError("prospective SPY session import must not read .env")
    return original_path_open(path, *args, **kwargs)


builtins.open = reject_dotenv
io.open = reject_dotenv_io
Path.open = reject_dotenv_path
socket.socket = fail_external
socket.create_connection = fail_external
urllib.request.urlopen = fail_external
os.environ = DeniedEnvironment()
os.getenv = lambda key, default=None: os.environ.get(key, default)

import {_MODULE}

print(json.dumps({{"imported": "{_MODULE}"}}, sort_keys=True))
'''
