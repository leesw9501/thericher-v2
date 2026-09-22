from __future__ import annotations

import importlib.util
import json
import subprocess
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.kis_readonly import KisPaperConfig

SPEC = importlib.util.spec_from_file_location(
    "budget_strategy_launcher",
    Path(__file__).resolve().parents[1] / "scripts/run_kis_paper_budget_strategy.py",
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class GuardedEnvironment(Mapping[str, str]):
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.reads: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.reads.append(key)
        if key.upper().startswith("KIS_"):
            raise AssertionError("inherited KIS values must not be read")
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)


def _unexpected(*_args, **_kwargs):
    raise AssertionError("unexpected external or credential work")


@pytest.fixture(autouse=True)
def isolated_launcher(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    fixture = SimpleNamespace(
        project_root=tmp_path / "repo",
        artifact_root=tmp_path / "external artifacts",
    )
    fixture.environment = GuardedEnvironment({
        "THERICHER_HOST_MODEL_ARTIFACT_ROOT": str(fixture.artifact_root),
        "PATH": "synthetic-path",
        "KIS_LIVE_APP_KEY": "must-not-read-live",
        "KIS_PAPER_APP_KEY": "must-not-read-inherited-paper",
        "KIS_PAPER_BASE_URL": "must-not-inherit-route",
        "kis_live_app_secret": "must-not-read-mixed-case",
        "KIS_OTHER": "must-not-read-other-kis-values",
    })
    monkeypatch.setattr(runner, "os", SimpleNamespace(environ=fixture.environment))
    monkeypatch.setattr(runner, "load_kis_paper_config", _unexpected)
    monkeypatch.setattr(runner, "subprocess", SimpleNamespace(
        run=_unexpected,
        DEVNULL=subprocess.DEVNULL,
        TimeoutExpired=subprocess.TimeoutExpired,
    ))
    return fixture


@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize("visits", [1, 24])
def test_scoped_launch_uses_exact_existing_service_paths_and_paper_only_environment(
    monkeypatch: pytest.MonkeyPatch, isolated_launcher: SimpleNamespace, execute: bool, visits: int
) -> None:
    calls, reads = [], []
    config = KisPaperConfig("synthetic-app", "synthetic-secret", "12345678", "01")

    def load(path):
        reads.append(path)
        return config

    def run(command, **kwargs):
        calls.append((command, {**kwargs, "env": dict(kwargs["env"])}))
        return SimpleNamespace(returncode=1 if "inspect" in command else 0)

    monkeypatch.setattr(runner, "load_kis_paper_config", load)
    monkeypatch.setattr(runner.subprocess, "run", run)
    outcome = runner.run(
        project_root=isolated_launcher.project_root, execute=execute, visits=visits
    )

    assert outcome == {
        "kind": "kis_paper_spy_budget_dispatch", "paper_only": True,
        "status": "worker_exited", "worker_exit_code": 0,
    }
    assert reads == ([isolated_launcher.project_root / ".env"] if execute else [])
    assert len(calls) == 2
    assert calls[0][0] == ["docker", "container", "inspect", "thericher-spy-budget-strategy"]
    assert calls[0][1]["timeout"] == 30
    command, options = calls[-1]
    assert command[:4] == [
        "docker", "compose", "--project-directory", str(isolated_launcher.project_root)
    ]
    expected_options = {
        "--env-file": str(isolated_launcher.project_root / ".env.example"),
        "--profile": "kis-paper-daily-spy-session",
        "--pull": "never",
        "--name": "thericher-spy-budget-strategy",
        "--budget-visits": str(visits),
        "--repository-root": "/app",
        "--cache-root": "/app/market_data/us_equities/kis_paper_private/daily",
        "--head-cache-root": "/app/market_data/us_equities/kis_paper_private/daily-head/v1",
        "--availability-root": (
            "/app/model_artifacts/_control/kis-paper-daily-spy-input-availability-v1"
        ),
        "--state-root": "/app/private/canary",
        "--runtime-projection": "/app/runtime/state/kis_paper_canary.json",
        "--paper-account-snapshot": "/app/runtime/state/paper_account_snapshot.json",
        "--emergency-state": "/app/emergency/emergency_state.json",
        "--execution-control": "/app/emergency/paper_execution_control.json",
        "--artifact-root": "/app/model_artifacts",
    }
    for option, value in expected_options.items():
        assert command.count(option) == 1
        assert command[command.index(option) + 1] == value
    timeout_index = command.index("timeout")
    assert command[timeout_index - 1:timeout_index + 7] == [
        "kis-paper-daily-spy-session", "timeout", "--signal=TERM", "--kill-after=30s", "1260s",
        "python", "-m", "thericher_v2.execution.kis_paper_daily_spy_session",
    ]
    for flag in ("--rm", "--no-deps", "-T", "--budget-trial"):
        assert flag in command
    assert "--cancel-after-submit" not in command
    assert "--build" not in command
    assert ("--execute" in command) is execute
    assert options["timeout"] == 1350
    assert options["cwd"] == isolated_launcher.project_root
    assert options["stdout"] == options["stderr"] == subprocess.DEVNULL
    assert options["env"]["THERICHER_HOST_MODEL_ARTIFACT_ROOT"] == (
        isolated_launcher.artifact_root.as_posix()
    )
    assert options["env"]["PATH"] == "synthetic-path"
    assert not any(key.upper().startswith("KIS_") for key in calls[0][1]["env"])
    assert {key for key in options["env"] if key.upper().startswith("KIS_")} == (
        {"KIS_PAPER_APP_KEY", "KIS_PAPER_APP_SECRET", "KIS_PAPER_ACCOUNT_NO",
         "KIS_PAPER_ACCOUNT_PRODUCT_CODE"} if execute else set()
    )
    if execute:
        assert options["env"]["KIS_PAPER_APP_KEY"] == config.app_key
        assert options["env"]["KIS_PAPER_APP_SECRET"] == config.app_secret
        assert options["env"]["KIS_PAPER_ACCOUNT_NO"] == config.account_number
        assert options["env"]["KIS_PAPER_ACCOUNT_PRODUCT_CODE"] == config.account_product_code
    assert not any(key.upper().startswith("KIS_") for key in isolated_launcher.environment.reads)
    for secret in (config.app_key, config.app_secret, config.account_number):
        assert secret not in str(command)
        assert secret not in json.dumps(outcome)


@pytest.mark.parametrize("execute", [False, True])
def test_existing_owned_container_prevents_launch_and_credential_read(
    monkeypatch: pytest.MonkeyPatch, isolated_launcher: SimpleNamespace, execute: bool
) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    outcome = runner.run(project_root=isolated_launcher.project_root, execute=execute, visits=24)

    assert outcome["status"] == "owned_container_present"
    assert calls == [["docker", "container", "inspect", "thericher-spy-budget-strategy"]]


@pytest.mark.parametrize("visits", [0, 25, -1, 1.5, True, "24"])
def test_invalid_visits_reject_before_subprocess_or_credentials(
    isolated_launcher: SimpleNamespace, visits: object
) -> None:
    with pytest.raises(ValueError, match="invalid bounded budget visits"):
        runner.run(project_root=isolated_launcher.project_root, execute=True, visits=visits)
    assert isolated_launcher.environment.reads == []


@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize("mode", ["kis_live", "KIS_LIVE", " kis_live "])
def test_live_mode_rejects_before_credentials_docker_or_other_environment_reads(
    isolated_launcher: SimpleNamespace, execute: bool, mode: str
) -> None:
    isolated_launcher.environment.values["THERICHER_MODE"] = mode

    with pytest.raises(ValueError, match="live_mode_unavailable"):
        runner.run(project_root=isolated_launcher.project_root, execute=execute, visits=24)

    assert isolated_launcher.environment.reads == ["THERICHER_MODE"]


@pytest.mark.parametrize("exit_code", [0, 1, 124, 137])
def test_worker_exit_is_categorical_and_does_not_stop_another_container(
    monkeypatch: pytest.MonkeyPatch, isolated_launcher: SimpleNamespace, exit_code: int
) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1 if "inspect" in command else exit_code)

    monkeypatch.setattr(runner.subprocess, "run", run)
    outcome = runner.run(project_root=isolated_launcher.project_root, execute=False, visits=1)

    assert outcome["status"] == ("worker_exited" if exit_code == 0 else "worker_failed")
    assert outcome["worker_exit_code"] == exit_code
    assert len(calls) == 2
    assert all("stop" not in command for command in calls)


@pytest.mark.parametrize("stop_result", [0, 1, "os_error", "timeout"])
def test_host_timeout_stops_only_fixed_owned_worker_and_categorizes_stop_result(
    monkeypatch: pytest.MonkeyPatch, isolated_launcher: SimpleNamespace, stop_result: object
) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if "compose" in command:
            assert kwargs["timeout"] == 1350
            raise subprocess.TimeoutExpired(command, 1350, output="private-output")
        if "stop" in command:
            if stop_result == "os_error":
                raise OSError("private-stop-error")
            if stop_result == "timeout":
                raise subprocess.TimeoutExpired(command, 45, stderr="private-stop-error")
            return SimpleNamespace(returncode=stop_result)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(runner.subprocess, "run", run)
    outcome = runner.run(project_root=isolated_launcher.project_root, execute=False, visits=24)

    assert outcome["status"] == "worker_timeout"
    assert outcome["container_stop_confirmed"] is (stop_result == 0)
    assert len(calls) == 3
    assert calls[-1][0] == ["docker", "stop", "--time", "30", "thericher-spy-budget-strategy"]
    assert calls[-1][1]["timeout"] == 45
    assert calls[-1][1]["stdout"] == calls[-1][1]["stderr"] == subprocess.DEVNULL
    assert "private" not in json.dumps(outcome)


def test_dispatch_record_uses_only_the_scoped_external_path(
    isolated_launcher: SimpleNamespace,
) -> None:
    result = {
        "kind": "kis_paper_spy_budget_dispatch", "status": "worker_timeout", "paper_only": True
    }
    runner.write_dispatch_result(result, isolated_launcher.project_root)

    expected = isolated_launcher.artifact_root / "execution/kis-paper-spy-budget/dispatch.json"
    assert json.loads(expected.read_text(encoding="utf-8")) == result
    assert list(isolated_launcher.artifact_root.rglob("dispatch.json")) == [expected]


@pytest.mark.parametrize("inside", [".", "artifacts"])
def test_repository_artifact_root_rejects_before_subprocess_or_credentials(
    monkeypatch: pytest.MonkeyPatch, isolated_launcher: SimpleNamespace, inside: str
) -> None:
    environment = GuardedEnvironment({
        "THERICHER_HOST_MODEL_ARTIFACT_ROOT": str(isolated_launcher.project_root / inside)
    })
    monkeypatch.setattr(runner, "os", SimpleNamespace(environ=environment))
    with pytest.raises(ValueError, match="outside the repository"):
        runner.run(project_root=isolated_launcher.project_root, execute=True, visits=24)
    with pytest.raises(ValueError, match="outside the repository"):
        runner.write_dispatch_result({"status": "synthetic"}, isolated_launcher.project_root)


@pytest.mark.parametrize("execute", [False, True])
def test_main_defaults_to_24_visits_and_requires_explicit_execute(
    monkeypatch: pytest.MonkeyPatch,
    isolated_launcher: SimpleNamespace,
    capsys: pytest.CaptureFixture[str],
    execute: bool,
) -> None:
    captured = {}
    result = {
        "kind": "kis_paper_spy_budget_dispatch", "status": "worker_exited", "paper_only": True
    }

    def run(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setattr(runner, "run", run)
    argv = ["--project-root", str(isolated_launcher.project_root)]
    assert runner.main(argv + (["--execute"] if execute else [])) == 0
    assert captured == {
        "project_root": isolated_launcher.project_root, "execute": execute, "visits": 24
    }
    assert json.loads(capsys.readouterr().out) == result
    expected = isolated_launcher.artifact_root / "execution/kis-paper-spy-budget/dispatch.json"
    assert json.loads(expected.read_text(encoding="utf-8")) == result


@pytest.mark.parametrize("visits", ["0", "25", "-1", "1.5"])
def test_main_rejects_invalid_visit_flags_without_dispatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], visits: str
) -> None:
    monkeypatch.setattr(runner, "run", _unexpected)
    with pytest.raises(SystemExit) as exc_info:
        runner.main(["--execute", "--visits", visits])
    assert exc_info.value.code == 2
    assert "--visits" in capsys.readouterr().err


@pytest.mark.parametrize("failure_stage", ["inspect", "config", "compose"])
def test_main_catches_dispatch_errors_without_raw_exception_or_subprocess_output(
    monkeypatch: pytest.MonkeyPatch,
    isolated_launcher: SimpleNamespace,
    capsys: pytest.CaptureFixture[str],
    failure_stage: str,
) -> None:
    calls = []

    def load(_path):
        if failure_stage == "config":
            raise ValueError("private-credential-and-account")
        return KisPaperConfig("synthetic-app", "synthetic-secret", "12345678", "01")

    def run(command, **kwargs):
        calls.append(command)
        if failure_stage in command:
            raise OSError("private-subprocess-diagnostic")
        return SimpleNamespace(returncode=1 if "inspect" in command else 0)

    monkeypatch.setattr(runner, "load_kis_paper_config", load)
    monkeypatch.setattr(runner.subprocess, "run", run)
    assert runner.main(["--project-root", str(isolated_launcher.project_root), "--execute"]) == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "private" not in captured.out
    result = json.loads(captured.out)
    assert result == {
        "kind": "kis_paper_spy_budget_dispatch",
        "status": "dispatch_unavailable",
        "paper_only": True,
    }
    expected = isolated_launcher.artifact_root / "execution/kis-paper-spy-budget/dispatch.json"
    assert json.loads(expected.read_text(encoding="utf-8")) == result
    assert all("stop" not in command for command in calls)


def test_main_records_inspect_timeout_without_stopping_an_unlaunched_worker(
    monkeypatch: pytest.MonkeyPatch,
    isolated_launcher: SimpleNamespace,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 30, output="private-inspect-output")

    monkeypatch.setattr(runner.subprocess, "run", run)
    assert runner.main(["--project-root", str(isolated_launcher.project_root)]) == 2
    assert calls == [["docker", "container", "inspect", "thericher-spy-budget-strategy"]]
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "dispatch_unavailable"
    assert "private" not in json.dumps(result)


def test_dispatch_record_failure_is_safe_and_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
    isolated_launcher: SimpleNamespace,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run(**_kwargs):
        return {
            "kind": "kis_paper_spy_budget_dispatch", "status": "worker_exited", "paper_only": True
        }

    def write(*_args):
        raise OSError("private-artifact-details")

    monkeypatch.setattr(runner, "run", run)
    monkeypatch.setattr(runner, "write_dispatch_result", write)
    assert runner.main(["--project-root", str(isolated_launcher.project_root)]) == 2
    captured = capsys.readouterr()
    assert "private" not in captured.out
    assert captured.err == ""
    assert json.loads(captured.out)["dispatch_record_written"] is False
