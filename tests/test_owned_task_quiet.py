"""Process-presentation tests; no Scheduler or broker entry point is used."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "owned_task_quiet", Path(__file__).parents[1] / "scripts" / "run_owned_task_quiet.py"
)
quiet = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quiet)


def config(tmp_path):
    return dict(
        task="thericher-synthetic-only",
        execute=str(tmp_path / "synthetic.exe"),
        arguments='--sample "two words" --empty ""',
        working_directory=str(tmp_path),
        receipt_root=str(tmp_path / "receipts"),
    )


def test_inert_by_default(monkeypatch):
    launch = Mock()
    monkeypatch.setattr(quiet, "launch", launch)
    assert quiet.main([]) == 0
    launch.assert_not_called()


def test_exact_hash_and_schema(tmp_path):
    path = tmp_path / "config.json"
    raw = json.dumps(config(tmp_path)).encode()
    path.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    assert quiet.read_config(path, pin) == config(tmp_path)
    with pytest.raises(ValueError, match="config_binding"):
        quiet.read_config(path, "0" * 64)
    path.write_bytes(json.dumps({**config(tmp_path), "extra": True}).encode())
    with pytest.raises(ValueError, match="config_schema"):
        quiet.read_config(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_quiet_child_keeps_arguments_and_exit(tmp_path, monkeypatch):
    value = config(tmp_path)
    popen = Mock(return_value=SimpleNamespace(wait=lambda: 23))
    monkeypatch.setattr(quiet, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        quiet.subprocess, "STARTUPINFO", lambda: SimpleNamespace(dwFlags=0), raising=False
    )
    monkeypatch.setattr(quiet.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(quiet.subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(quiet.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(quiet.subprocess, "Popen", popen)
    assert quiet.launch(value, "a" * 64) == 23
    args, kwargs = popen.call_args
    assert args == (quiet.subprocess.list2cmdline([value["execute"]]) + " " + value["arguments"],)
    assert kwargs["executable"] == value["execute"]
    assert kwargs["cwd"] == value["working_directory"]
    assert kwargs["creationflags"] == 0x08000000
    assert kwargs["startupinfo"].wShowWindow == 0
    assert kwargs["shell"] is False
    assert all(kwargs[k] == quiet.subprocess.DEVNULL for k in ("stdin", "stdout", "stderr"))
    receipt = json.loads(next(Path(value["receipt_root"]).glob("*.json")).read_bytes())
    assert receipt["status"] == "worker_returned" and receipt["exit_code"] == 23
    assert "arguments" not in receipt and "execute" not in receipt


def test_invalid_execution_never_launches(monkeypatch):
    launch = Mock()
    monkeypatch.setattr(quiet, "launch", launch)
    assert quiet.main(["--execute"]) == 3
    launch.assert_not_called()
