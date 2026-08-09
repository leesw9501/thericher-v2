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


def test_runner_suppresses_local_client_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()
    expected = {"status": "input_unavailable", "reason": "calendar_short"}
    observation = SimpleNamespace(source_update_at_utc=datetime(2026, 8, 9, tzinfo=UTC))

    def noisy_collect(**_kwargs: object) -> SimpleNamespace:
        print("third-party local client detail")
        return observation

    monkeypatch.setattr(runner, "collect_norgate_tail_reference_observation", noisy_collect)
    monkeypatch.setattr(
        runner,
        "resolve_active_norgate_us_database_root",
        lambda *_args, **_kwargs: Path("D:/norgate"),
    )
    monkeypatch.setattr(
        runner,
        "fingerprint_norgate_us_database_build",
        lambda _root: "sha256:" + "a" * 64,
    )
    monkeypatch.setattr(
        runner,
        "build_norgate_trial_tail_readiness_receipt",
        lambda **kwargs: _Result(expected, kwargs),
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == 0
    assert capsys.readouterr().out == json.dumps(expected, sort_keys=True) + "\n"


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


@pytest.mark.parametrize(
    ("reason", "recovery"),
    [
        ("no_configured_databases", "configure_local_norgate_us_database"),
        ("us_equities_database_not_configured", "configure_local_norgate_us_database"),
    ],
)
def test_runner_reports_source_preflight_without_source_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reason: str, recovery: str
) -> None:
    runner = _load_runner()

    def fail_observation(**_kwargs: object) -> object:
        raise runner.NorgateLocalSourcePreflightError(reason)

    monkeypatch.setattr(runner, "collect_norgate_tail_reference_observation", fail_observation)
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == runner._RECOVERY_EXIT_CODE
    assert json.loads(capsys.readouterr().out) == {
        "kind": "norgate_trial_tail_readiness",
        "reason": reason,
        "recovery": recovery,
        "status": "unavailable",
    }


def test_runner_maps_local_status_http_402_to_subscription_or_update_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()

    def fail_observation(**_kwargs: object) -> object:
        raise runner.NorgateLocalSourcePreflightError("local_api_not_ready")

    monkeypatch.setattr(runner, "collect_norgate_tail_reference_observation", fail_observation)
    monkeypatch.setattr(runner, "_norgate_local_status_http_code", lambda: 402)
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == runner._RECOVERY_EXIT_CODE
    assert json.loads(capsys.readouterr().out) == {
        "kind": "norgate_trial_tail_readiness",
        "reason": "subscription_or_update_unavailable",
        "recovery": "open_norgate_data_updater_and_check_for_updates",
        "status": "unavailable",
    }


@pytest.mark.parametrize("status_probe", [500, None], ids=["unknown", "absent"])
def test_runner_preserves_local_api_not_ready_without_a_402(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status_probe: int | None,
) -> None:
    runner = _load_runner()

    def fail_observation(**_kwargs: object) -> object:
        raise runner.NorgateLocalSourcePreflightError("local_api_not_ready")

    monkeypatch.setattr(runner, "collect_norgate_tail_reference_observation", fail_observation)
    monkeypatch.setattr(runner, "_norgate_local_status_http_code", lambda: status_probe)
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == runner._RECOVERY_EXIT_CODE
    assert json.loads(capsys.readouterr().out) == {
        "kind": "norgate_trial_tail_readiness",
        "reason": "local_api_not_ready",
        "recovery": "restore_local_norgate_api_readiness",
        "status": "unavailable",
    }


def test_runner_preserves_local_api_not_ready_when_status_probe_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _load_runner()

    def fail_observation(**_kwargs: object) -> object:
        raise runner.NorgateLocalSourcePreflightError("local_api_not_ready")

    def fail_status_probe() -> bool:
        raise RuntimeError("status detail must not be printed")

    monkeypatch.setattr(runner, "collect_norgate_tail_reference_observation", fail_observation)
    monkeypatch.setattr(runner, "_norgate_local_status_http_code", fail_status_probe)
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--run-label", "unit-r1"])

    assert runner.main() == runner._RECOVERY_EXIT_CODE
    assert json.loads(capsys.readouterr().out) == {
        "kind": "norgate_trial_tail_readiness",
        "reason": "local_api_not_ready",
        "recovery": "restore_local_norgate_api_readiness",
        "status": "unavailable",
    }


def test_status_probe_classifies_loopback_http_402_without_consuming_response_data() -> None:
    runner = _load_runner()

    class _Response:
        status = 402

        def read(self) -> bytes:
            pytest.fail("status probe must not consume response data")

    class _Connection:
        closed = False
        request_args: tuple[str, str] | None = None

        def request(self, method: str, path: str) -> None:
            self.request_args = (method, path)

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            self.closed = True

    connection = _Connection()

    def make_connection(host: str, port: int, *, timeout: float) -> _Connection:
        assert host == "127.0.0.1"
        assert port == 38889
        assert timeout == 1.0
        return connection

    assert runner._norgate_local_status_http_code(connection_factory=make_connection) == 402
    assert connection.request_args == ("GET", "/api/v1/status")
    assert connection.closed is True


def test_status_probe_reads_only_the_http_code_and_closes_its_connection() -> None:
    runner = _load_runner()

    class _Response:
        status = 500

        def getcode(self) -> int:
            pytest.fail("status probe must use the status code property")

        def read(self) -> bytes:
            pytest.fail("status probe must not consume response data")

    class _Connection:
        closed = False

        def request(self, _method: str, _path: str) -> None:
            pass

        def getresponse(self) -> _Response:
            return response

        def close(self) -> None:
            self.closed = True

    response = _Response()
    connection = _Connection()

    assert (
        runner._norgate_local_status_http_code(
            connection_factory=lambda *_args, **_kwargs: connection
        )
        == 500
    )
    assert connection.closed is True


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
