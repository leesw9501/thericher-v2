from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.data import kis_paper_token_cadence_probe as probe
from thericher_v2.execution.kis_market_data import KisPaperMarketDataError


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> datetime:
        return datetime(2026, 8, 5, tzinfo=UTC) + timedelta(seconds=self.value)

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _attempt(clock: _Clock) -> probe.KisPaperTokenCadenceProbeAttempt:
    return probe.KisPaperTokenCadenceProbeAttempt(
        request_started_at=clock(),
        monotonic_started_seconds=clock.monotonic(),
    )


def test_two_authentication_attempts_at_the_frozen_token_cadence_are_source_safe() -> None:
    clock = _Clock()
    calls: list[str] = []

    outcome = probe.run_kis_paper_token_cadence_probe(
        authenticate_once=lambda: (calls.append("secret-token-never-retained") or _attempt(clock)),
        monotonic_clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert calls == ["secret-token-never-retained", "secret-token-never-retained"]
    assert outcome.status == "accepted"
    assert outcome.accepted_authentication_count == 2
    assert outcome.failure_stage == "none"
    assert outcome.spacing_category == "at_or_above_requested_interval"
    assert (
        outcome.observed_monotonic_start_spacing_seconds
        == probe.KIS_PAPER_TOKEN_CADENCE_PROBE_INTERVAL_SECONDS
    )
    assert clock.value == probe.KIS_PAPER_TOKEN_CADENCE_PROBE_INTERVAL_SECONDS
    assert "secret-token-never-retained" not in json.dumps(outcome.safe_payload(), sort_keys=True)


@pytest.mark.parametrize(
    ("failure_stage", "error", "accepted_count", "expected_spacing"),
    [
        ("first", KisPaperMarketDataError("auth_rejected"), 0, "not_started"),
        ("second", KisPaperMarketDataError("rate_limited"), 1, "at_or_above_requested_interval"),
    ],
)
def test_authentication_failures_stay_categorical(
    failure_stage: str,
    error: KisPaperMarketDataError,
    accepted_count: int,
    expected_spacing: str,
) -> None:
    clock = _Clock()
    calls = 0

    def authenticate_once() -> probe.KisPaperTokenCadenceProbeAttempt:
        nonlocal calls
        calls += 1
        if (failure_stage == "first" and calls == 1) or (
            failure_stage == "second" and calls == 2
        ):
            raise error
        return _attempt(clock)

    outcome = probe.run_kis_paper_token_cadence_probe(
        authenticate_once=authenticate_once,
        monotonic_clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert outcome.status == "unavailable"
    assert outcome.failure_stage == failure_stage
    assert outcome.failure_reason == str(error)
    assert outcome.accepted_authentication_count == accepted_count
    assert outcome.spacing_category == expected_spacing
    assert outcome.observed_monotonic_start_spacing_seconds == (
        None if failure_stage == "first" else probe.KIS_PAPER_TOKEN_CADENCE_PROBE_INTERVAL_SECONDS
    )
    assert calls == accepted_count + 1


def test_probe_refuses_a_wall_clock_shift_when_monotonic_start_is_early() -> None:
    clock = _Clock()
    starts = iter(
        (
            probe.KisPaperTokenCadenceProbeAttempt(
                request_started_at=datetime(2026, 8, 5, tzinfo=UTC),
                monotonic_started_seconds=0,
            ),
            probe.KisPaperTokenCadenceProbeAttempt(
                request_started_at=datetime(2026, 8, 5, tzinfo=UTC) + timedelta(seconds=30),
                monotonic_started_seconds=15,
            ),
        )
    )

    outcome = probe.run_kis_paper_token_cadence_probe(
        authenticate_once=lambda: next(starts),
        monotonic_clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    assert outcome.status == "unavailable"
    assert outcome.accepted_authentication_count == 1
    assert outcome.failure_stage == "second"
    assert outcome.failure_reason == "transport_failure"
    assert outcome.spacing_category == "below_requested_interval"
    assert outcome.observed_monotonic_start_spacing_seconds == 15


def test_probe_evidence_is_external_and_immutable(tmp_path: Path) -> None:
    clock = _Clock()
    outcome = probe.run_kis_paper_token_cadence_probe(
        authenticate_once=lambda: _attempt(clock),
        monotonic_clock=clock.monotonic,
        sleeper=clock.sleep,
    )
    repository = tmp_path / "repo"
    repository.mkdir()
    artifacts = tmp_path / "artifacts"

    run = probe.write_kis_paper_token_cadence_probe(
        outcome,
        artifact_root=artifacts,
        repo_root=repository,
        run_label="unit-test",
        observed_at=datetime(2026, 8, 5, 0, 0, tzinfo=UTC),
    )

    assert run.summary_path.is_relative_to(artifacts)
    payload = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert payload["outcome"]["scope"] == {
        "account_or_order_requested": False,
        "credentials_written": False,
        "live_route": False,
        "market_data_requested": False,
        "model_or_pnl_result": False,
        "paper_only": True,
        "token_only": True,
        "token_value_retained": False,
    }
    with pytest.raises(ValueError, match="evidence conflicts"):
        probe.write_kis_paper_token_cadence_probe(
            probe.KisPaperTokenCadenceProbeOutcome(
                status="unavailable",
                requested_interval_seconds=30.0,
                accepted_authentication_count=1,
                failure_stage="second",
                failure_reason="rate_limited",
                spacing_category="at_or_above_requested_interval",
                observed_monotonic_start_spacing_seconds=30.0,
            ),
            artifact_root=artifacts,
            repo_root=repository,
            run_label="unit-test",
            observed_at=datetime(2026, 8, 5, 0, 0, tzinfo=UTC),
        )


def test_cli_does_not_load_credentials_without_execute(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_token_cadence.py"
    spec = importlib.util.spec_from_file_location("probe_kis_paper_token_cadence_for_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def unexpected_config(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("credential loading must require --execute")

    monkeypatch.setattr(module, "load_kis_paper_market_data_config", unexpected_config)

    assert module.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "reason": "execute_flag_required",
        "status": "not_executed",
    }


def test_cli_yields_without_reading_credentials_when_shared_token_window_is_not_due(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_token_cadence.py"
    spec = importlib.util.spec_from_file_location("probe_kis_paper_token_cadence_due_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class _NotDueGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def token_request_is_due(self) -> bool:
            return False

    def unexpected_config(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("credential loading must wait for a due token window")

    monkeypatch.setattr(module, "KisPaperMarketDataTokenStartGate", _NotDueGate)
    monkeypatch.setattr(module, "load_kis_paper_market_data_config", unexpected_config)

    assert module.main(["--execute"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "kind": probe.KIS_PAPER_TOKEN_CADENCE_PROBE_KIND,
        "paper_only": True,
        "reason": "token_request_not_due",
        "status": "unavailable",
        "token_value_retained": False,
    }


def test_cli_does_not_start_a_transport_when_atomic_token_reservation_loses_race(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_token_cadence.py"
    spec = importlib.util.spec_from_file_location("probe_kis_paper_token_cadence_race_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class _LostRaceGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def token_request_is_due(self) -> bool:
            return True

        def claim_token_request_start(self) -> bool:
            return False

    def unexpected_transport(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a lost reservation must not start a token transport")

    monkeypatch.setattr(module, "KisPaperMarketDataTokenStartGate", _LostRaceGate)
    monkeypatch.setattr(module, "UrllibKisPaperMarketDataTransport", unexpected_transport)
    monkeypatch.setattr(module, "load_kis_paper_market_data_config", lambda _path: object())

    assert module.main(["--execute"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "kind": probe.KIS_PAPER_TOKEN_CADENCE_PROBE_KIND,
        "paper_only": True,
        "reason": "token_request_not_due",
        "status": "unavailable",
        "token_value_retained": False,
    }


def test_cli_execute_runs_exactly_two_mocked_token_authentications(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_token_cadence.py"
    spec = importlib.util.spec_from_file_location(
        "probe_kis_paper_token_cadence_execute_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = _Clock()
    clients: list[object] = []
    transports: list[object] = []

    class _TokenGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def token_request_is_due(self) -> bool:
            return True

        def claim_token_request_start(self) -> bool:
            return True

    class _RateGate:
        def __init__(self, *, on_request_started: object = None, **_kwargs: object) -> None:
            self.on_request_started = on_request_started

    class _Transport:
        def __init__(self, *, request_gate: _RateGate, **kwargs: object) -> None:
            self.request_gate = request_gate
            self.kwargs = kwargs
            transports.append(self)

    class _Client:
        def __init__(self, *, config: object, transport: _Transport) -> None:
            assert config == "mocked-paper-config"
            self.transport = transport
            clients.append(self)

        def ensure_authenticated(self) -> None:
            callback = self.transport.request_gate.on_request_started
            assert callable(callback)
            callback(clock())

    monkeypatch.setattr(module, "KisPaperMarketDataTokenStartGate", _TokenGate)
    monkeypatch.setattr(module, "KisPaperMarketDataRateGate", _RateGate)
    monkeypatch.setattr(module, "UrllibKisPaperMarketDataTransport", _Transport)
    monkeypatch.setattr(module, "KisPaperMarketDataClient", _Client)
    monkeypatch.setattr(
        module,
        "load_kis_paper_market_data_config",
        lambda _path: "mocked-paper-config",
    )

    assert (
        module.main(
            [
                "--execute",
                "--artifact-root",
                str(tmp_path),
                "--interval-seconds",
                "60",
            ],
            clock=clock,
            monotonic_clock=clock.monotonic,
            sleeper=clock.sleep,
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert len(clients) == 2
    assert len(transports) == 2
    assert transports[0].kwargs == {}
    assert set(transports[1].kwargs) == {"token_start_gate"}
    assert payload["status"] == "accepted"
    assert payload["requested_interval_seconds"] == 60
    assert payload["accepted_authentication_count"] == 2
    assert payload["scope"]["market_data_requested"] is False
    assert payload["scope"]["account_or_order_requested"] is False
    assert Path(payload["summary_path"]).is_relative_to(tmp_path)


def test_cli_rejects_a_mocked_authentication_without_its_transport_start_marker(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_token_cadence.py"
    spec = importlib.util.spec_from_file_location("probe_kis_paper_token_cadence_marker_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class _TokenGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def token_request_is_due(self) -> bool:
            return True

        def claim_token_request_start(self) -> bool:
            return True

    class _RateGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

    class _Transport:
        def __init__(self, **_kwargs: object) -> None:
            pass

    class _Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def ensure_authenticated(self) -> None:
            return None

    monkeypatch.setattr(module, "KisPaperMarketDataTokenStartGate", _TokenGate)
    monkeypatch.setattr(module, "KisPaperMarketDataRateGate", _RateGate)
    monkeypatch.setattr(module, "UrllibKisPaperMarketDataTransport", _Transport)
    monkeypatch.setattr(module, "KisPaperMarketDataClient", _Client)
    monkeypatch.setattr(module, "load_kis_paper_market_data_config", lambda _path: object())

    assert module.main(["--execute", "--artifact-root", str(tmp_path)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "unavailable"
    assert payload["accepted_authentication_count"] == 0
    assert payload["failure"] == {"reason": "transport_failure", "stage": "first"}
