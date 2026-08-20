from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "run_norgate_trial_host_readiness_reconciliation.py"
)


def test_runner_invokes_one_safe_reconciliation_and_prints_receipt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()
    expected = {
        "status": "input_unavailable",
        "reason": "local_api_not_ready_updater_not_observed",
        "recovery": "ensure_norgate_data_updater_is_installed_and_running",
        "summary_sha256": "sha256:" + "a" * 64,
    }
    calls: dict[str, object] = {}

    def run_diagnostic(**kwargs: object) -> _Result:
        calls.update(kwargs)
        return _Result(expected)

    monkeypatch.setattr(
        runner, "run_norgate_trial_host_readiness_reconciliation", run_diagnostic
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out) == expected
    assert calls["run_label"] == "unit-r1"
    assert calls["client_loader"] is not None
    assert (
        calls["updater_installation_marker_probe"]
        is runner.default_updater_installation_marker_status
    )
    assert calls["updater_process_probe"] is runner._updater_process_status


def test_verify_only_does_not_invoke_host_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()
    expected = SimpleNamespace(
        status="verified",
        summary_sha256="sha256:" + "b" * 64,
        prior_receipt_sha256="sha256:" + "c" * 64,
    )
    calls: dict[str, object] = {}

    def validate(**kwargs: object) -> SimpleNamespace:
        calls.update(kwargs)
        return expected

    monkeypatch.setattr(
        runner, "validate_norgate_trial_host_readiness_reconciliation", validate
    )
    monkeypatch.setattr(
        runner,
        "run_norgate_trial_host_readiness_reconciliation",
        lambda **_kwargs: pytest.fail("verify-only must not invoke the host"),
    )
    monkeypatch.setattr(
        sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1", "--verify-only"]
    )

    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "verified",
        "summary_sha256": expected.summary_sha256,
        "prior_receipt_sha256": expected.prior_receipt_sha256,
    }
    assert calls["run_label"] == "unit-r1"


def test_runner_suppresses_local_client_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()
    expected = {"status": "input_unavailable", "reason": "diagnosis_unavailable"}

    def noisy_diagnostic(**_kwargs: object) -> _Result:
        print("private local client detail")
        return _Result(expected)

    monkeypatch.setattr(
        runner, "run_norgate_trial_host_readiness_reconciliation", noisy_diagnostic
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == 0
    assert capsys.readouterr().out == json.dumps(expected, sort_keys=True) + "\n"


def test_runner_sanitizes_unexpected_diagnostic_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()

    def fail_diagnostic(**_kwargs: object) -> object:
        raise RuntimeError("private host detail")

    monkeypatch.setattr(
        runner, "run_norgate_trial_host_readiness_reconciliation", fail_diagnostic
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == runner._RECOVERY_EXIT_CODE
    assert json.loads(capsys.readouterr().out) == {
        "status": "input_unavailable",
        "reason": "diagnosis_unavailable",
        "recovery": "restore_local_norgate_api_readiness",
    }


@pytest.mark.parametrize(
    ("rows", "returncode", "expected"),
    [
        ('"NDU.exe","1","x"\n', 0, "observed"),
        ('"other.exe","1","x"\n', 0, "not_observed"),
        ("", 1, "unavailable"),
    ],
)
def test_process_probe_returns_only_safe_category(
    rows: str, returncode: int, expected: str
) -> None:
    runner = _load_runner()
    calls: dict[str, object] = {}

    def run_process(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["command"] = command
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, returncode, stdout=rows)

    assert runner._updater_process_status(process_runner=run_process) == expected
    assert calls["command"] == ["tasklist", "/fo", "csv", "/nh"]
    assert calls["kwargs"]["capture_output"] is True


def test_runner_has_no_secret_or_external_route_strings() -> None:
    source = _SCRIPT.read_text(encoding="utf-8").casefold()

    for prohibited in (".env", "kis", "broker", "order", "http"):
        assert prohibited not in source


class _Result:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def safe_payload(self) -> dict[str, object]:
        return self._payload


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "norgate_trial_host_readiness_reconciliation_runner", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
