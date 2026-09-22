import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.kis_readonly import KisPaperConfig

SPEC = importlib.util.spec_from_file_location(
    "fill_cycle_launcher",
    Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_spy_fill_cycle.py",
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.mark.parametrize("execute", (False, True))
def test_scoped_launch_reuses_existing_service_without_real_compose_env(
    monkeypatch, tmp_path, execute
):
    calls, reads = [], []
    config = KisPaperConfig("fake-app", "fake-secret", "12345678", "01")

    def load(path):
        reads.append(path)
        return config

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=1 if "inspect" in command else 0)

    monkeypatch.setenv("KIS_LIVE_APP_KEY", "synthetic-forbidden")
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "inherited-not-approved-source")
    monkeypatch.setattr(runner, "load_kis_paper_config", load)
    monkeypatch.setattr(runner.subprocess, "run", run)
    outcome = runner.run(project_root=tmp_path, cycle_id="synthetic", execute=execute, visits=20)
    assert outcome["status"] == "worker_exited"
    assert reads == ([tmp_path / ".env"] if execute else [])
    command, options = calls[-1]
    assert command[command.index("--env-file") + 1] == str(tmp_path / ".env.example")
    assert "--cancel-after-submit" not in command
    assert "--no-deps" in command and "--pull" in command
    assert command[command.index("timeout"):command.index("timeout") + 4] == [
        "timeout", "--signal=TERM", "--kill-after=30s", "1260s"
    ]
    assert ("--execute" in command) == execute
    assert "KIS_LIVE_APP_KEY" not in options["env"]
    assert options["env"].get("KIS_PAPER_APP_KEY") == (config.app_key if execute else None)
    assert options["stdout"] == options["stderr"] == subprocess.DEVNULL
    assert all(secret not in str(command) for secret in (config.app_key, config.app_secret))
    assert "12345678" not in str(outcome)


def test_existing_owned_container_is_not_replaced(monkeypatch, tmp_path):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    outcome = runner.run(project_root=tmp_path, cycle_id="synthetic", execute=False, visits=1)
    assert outcome["status"] == "owned_container_present"
    assert len(calls) == 1


def test_timeout_stops_only_named_launched_worker(monkeypatch, tmp_path):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "compose" in command:
            raise subprocess.TimeoutExpired(command, 1350)
        return SimpleNamespace(returncode=1 if "inspect" in command else 0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    outcome = runner.run(project_root=tmp_path, cycle_id="synthetic", execute=False, visits=1)
    assert outcome["status"] == "worker_timeout"
    assert outcome["container_stop_confirmed"]
    assert calls[0][-1] == calls[-1][-1]
    assert calls[-1][1:4] == ["stop", "--time", "30"]


def test_launcher_errors_never_relay_exception_text(monkeypatch, capsys):
    def fail(**kwargs):
        raise RuntimeError("synthetic-private-token-and-account")

    monkeypatch.setattr(runner, "run", fail)
    monkeypatch.setattr(runner, "write_dispatch_result", lambda *args: None)
    assert runner.main(["--cycle-id", "synthetic", "--execute"]) == 2
    assert "synthetic-private" not in capsys.readouterr().out


def test_dispatch_error_has_durable_categorical_result(monkeypatch, tmp_path):
    import json

    monkeypatch.setenv("THERICHER_HOST_MODEL_ARTIFACT_ROOT", str(tmp_path / "external"))
    result = {"cycle_ref": "a" * 64, "status": "worker_timeout", "paper_only": True}
    runner.write_dispatch_result(result, tmp_path / "repo")
    paths = list((tmp_path / "external").rglob("dispatch.json"))
    assert len(paths) == 1
    assert json.loads(paths[0].read_text()) == result
