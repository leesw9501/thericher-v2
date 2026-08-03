from __future__ import annotations

import json
import subprocess
import sys

_MODULE = "thericher_v2.research.profiled_mtf_flattened_control"


def test_flattened_control_import_has_no_external_or_torch_side_effects() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORT_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "execution_imported": False,
        "imported": _MODULE,
        "torch_imported": False,
    }


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
    raise AssertionError("flattened control import must not open a network connection")


def fail_secret(*_args, **_kwargs):
    raise AssertionError("flattened control import must not read KIS credentials")


class EnvironmentWithoutKisSecrets:
    def __getitem__(self, key):
        if key.startswith("KIS_"):
            fail_secret()
        raise KeyError(key)

    def get(self, key, default=None):
        if key.startswith("KIS_"):
            fail_secret()
        return default

    def __contains__(self, key):
        if key.startswith("KIS_"):
            fail_secret()
        return False


original_open = builtins.open
original_io_open = io.open
original_path_open = Path.open


def reject_dotenv(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("flattened control import must not read .env")
    return original_open(file, *args, **kwargs)


def reject_dotenv_io(file, *args, **kwargs):
    try:
        candidate = os.fspath(file)
    except TypeError:
        candidate = ""
    if str(candidate).casefold().endswith(".env"):
        raise AssertionError("flattened control import must not read .env")
    return original_io_open(file, *args, **kwargs)


def reject_dotenv_path(path, *args, **kwargs):
    if path.name.casefold().endswith(".env"):
        raise AssertionError("flattened control import must not read .env")
    return original_path_open(path, *args, **kwargs)


builtins.open = reject_dotenv
io.open = reject_dotenv_io
Path.open = reject_dotenv_path
socket.socket = fail_external
socket.create_connection = fail_external
urllib.request.urlopen = fail_external
os.environ = EnvironmentWithoutKisSecrets()
os.getenv = lambda key, default=None: os.environ.get(key, default)

import {_MODULE}

execution_imported = any(
    name == "thericher_v2.execution" or name.startswith("thericher_v2.execution.")
    for name in sys.modules
)
print(json.dumps({{
    "execution_imported": execution_imported,
    "imported": "{_MODULE}",
    "torch_imported": "torch" in sys.modules,
}}, sort_keys=True))
'''
