from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "run_norgate_trial_tail_readiness.py"


def test_runner_prints_the_safe_success_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()
    expected = {"status": "input_unavailable", "reason": "calendar_short"}
    calls: dict[str, object] = {}
    observation = SimpleNamespace(source_update_at_utc=datetime(2026, 8, 9, tzinfo=UTC))

    def collect(**kwargs: object) -> SimpleNamespace:
        calls["observation"] = kwargs
        return observation

    def resolve(*_args: object, **_kwargs: object) -> Path:
        return Path("D:/norgate")

    def fingerprint(_root: Path) -> str:
        return "sha256:" + "a" * 64

    monkeypatch.setattr(runner, "collect_norgate_tail_reference_observation", collect)
    monkeypatch.setattr(runner, "resolve_active_norgate_us_database_root", resolve)
    monkeypatch.setattr(runner, "fingerprint_norgate_us_database_build", fingerprint)
    monkeypatch.setattr(
        runner,
        "build_norgate_trial_tail_readiness_receipt",
        lambda **kwargs: _Result(expected, kwargs),
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == 0
    assert calls["observation"] == {"requested_end": runner.date.today()}
    assert json.loads(capsys.readouterr().out) == expected


def test_runner_sanitizes_local_source_failures_without_calling_later_steps(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()

    def fail_observation(**_kwargs: object) -> object:
        raise runner.NorgateTrialTailReadinessError("provider detail must not be printed")

    monkeypatch.setattr(runner, "collect_norgate_tail_reference_observation", fail_observation)
    monkeypatch.setattr(
        runner,
        "resolve_active_norgate_us_database_root",
        lambda *_args, **_kwargs: pytest.fail("source failure must stop before root resolution"),
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == runner._RECOVERY_EXIT_CODE
    assert json.loads(capsys.readouterr().out) == {
        "kind": "norgate_trial_tail_readiness",
        "reason": "local_source_unavailable",
        "recovery": "retry_after_local_source_recovery",
        "status": "unavailable",
    }


class _Result:
    def __init__(self, payload: dict[str, object], kwargs: dict[str, object]) -> None:
        self._payload = payload
        self.kwargs = kwargs

    def safe_payload(self) -> dict[str, object]:
        return self._payload


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("norgate_trial_tail_runner", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
