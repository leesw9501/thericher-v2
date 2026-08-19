from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data import kis_paper_auth_capability_probe as probe
from thericher_v2.execution.kis_market_data import KisPaperMarketDataError


def test_source_safe_outcome_omits_a_reason_after_one_authenticated_token_request() -> None:
    outcome = probe.KisPaperAuthCapabilityProbeOutcome(
        status="authenticated",
        observed_at=datetime(2026, 8, 20, 1, 2, tzinfo=UTC),
    )

    assert outcome.safe_payload() == {
        "schema_version": outcome.schema_version,
        "status": "authenticated",
        "observed_at_bucket": "2026-08-20T01:00Z",
        "route_isolation": {
            "paper_only": True,
            "token_only": True,
            "market_data_requested": False,
            "account_endpoints_used": False,
            "position_endpoints_used": False,
            "open_order_endpoints_used": False,
            "quote_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
            "token_value_retained": False,
            "credentials_written": False,
            "raw_broker_body_retained": False,
        },
    }


def test_dynamic_authentication_error_text_is_reduced_to_a_fixed_reason() -> None:
    private_detail = "private-token-or-body-canary"

    reason = probe.categorize_kis_paper_auth_capability_error(
        KisPaperMarketDataError(private_detail)
    )
    outcome = probe.KisPaperAuthCapabilityProbeOutcome(
        status="unavailable",
        observed_at=datetime(2026, 8, 20, tzinfo=UTC),
        reason=reason,
    )

    assert reason == "transport_failure"
    assert private_detail not in json.dumps(outcome.safe_payload(), sort_keys=True)


def test_probe_receipt_is_immutable_and_external(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    artifacts = tmp_path / "artifacts"
    outcome = probe.KisPaperAuthCapabilityProbeOutcome(
        status="unavailable",
        observed_at=datetime(2026, 8, 20, tzinfo=UTC),
        reason="auth_rejected",
    )

    run = probe.write_kis_paper_auth_capability_probe(
        outcome,
        artifact_root=artifacts,
        repo_root=repository,
        run_label="unit-test",
    )

    assert run.receipt_path.is_relative_to(artifacts)
    payload = json.loads(run.receipt_path.read_text(encoding="utf-8"))
    assert payload["artifact_policy"] == {
        "credentials_in_receipt": False,
        "token_in_receipt": False,
        "raw_broker_body_in_receipt": False,
        "account_data_in_receipt": False,
        "repo_storage_allowed": False,
    }
    assert "private-token-or-body-canary" not in json.dumps(payload, sort_keys=True)
    with pytest.raises(ValueError, match="receipt conflicts"):
        probe.write_kis_paper_auth_capability_probe(
            probe.KisPaperAuthCapabilityProbeOutcome(
                status="authenticated",
                observed_at=datetime(2026, 8, 20, tzinfo=UTC),
            ),
            artifact_root=artifacts,
            repo_root=repository,
            run_label="unit-test",
        )


def test_cli_does_not_read_configuration_without_execute(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script_module()
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("configuration must require --execute"),
    )

    assert script.main([]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "reason": "execute_flag_required",
        "status": "not_executed",
    }


def test_not_due_token_window_skips_configuration_and_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = _script_module()
    artifact_payloads: list[probe.KisPaperAuthCapabilityProbeOutcome] = []

    class _TokenGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def token_request_is_due(self) -> bool:
            return False

    class _RateGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def snapshot(self) -> object:
            return type(
                "Snapshot",
                (),
                {
                    "retry_not_before_utc": None,
                    "last_request_started_at_utc": None,
                },
            )()

    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", _TokenGate)
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", _RateGate)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("not-due token gate must not load configuration"),
    )
    monkeypatch.setattr(
        script,
        "UrllibKisPaperMarketDataTransport",
        lambda **_kwargs: pytest.fail("not-due token gate must not construct transport"),
    )
    monkeypatch.setattr(
        script,
        "write_kis_paper_auth_capability_probe",
        lambda outcome, **_kwargs: artifact_payloads.append(outcome)
        or _run(tmp_path, outcome),
    )

    assert script.main(["--execute"]) == 20
    assert artifact_payloads[0].status == "unavailable"
    assert artifact_payloads[0].reason == "token_request_not_due"


def test_token_claim_race_makes_no_request_and_receipt_never_contains_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = _script_module()
    written: list[probe.KisPaperAuthCapabilityProbeOutcome] = []
    token_request_count = 0
    config_value = "paper-config-private-canary"

    class _TokenGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def token_request_is_due(self) -> bool:
            return True

        def claim_token_request_start(self) -> bool:
            return False

    class _RateGate:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def snapshot(self) -> object:
            return type(
                "Snapshot",
                (),
                {
                    "retry_not_before_utc": None,
                    "last_request_started_at_utc": None,
                },
            )()

    class _Transport:
        def __init__(self, **kwargs: object) -> None:
            self.token_start_gate = kwargs["token_start_gate"]

    class _Client:
        def __init__(self, *, config: object, transport: _Transport) -> None:
            assert config == config_value
            self.transport = transport

        def authenticate_token_only(self) -> None:
            nonlocal token_request_count
            if not self.transport.token_start_gate.claim_token_request_start():
                raise KisPaperMarketDataError("token_request_not_due")
            token_request_count += 1

    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", _TokenGate)
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", _RateGate)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: config_value,
    )
    monkeypatch.setattr(script, "UrllibKisPaperMarketDataTransport", _Transport)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", _Client)
    monkeypatch.setattr(
        script,
        "write_kis_paper_auth_capability_probe",
        lambda outcome, **_kwargs: written.append(outcome) or _run(tmp_path, outcome),
    )

    assert script.main(["--execute"]) == 20
    assert token_request_count == 0
    assert written[0].reason == "token_request_not_due"
    assert config_value not in json.dumps(written[0].safe_payload(), sort_keys=True)
    assert config_value not in capsys.readouterr().out


def test_cli_executes_one_mocked_token_only_authentication(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = _script_module()
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
        def __init__(self, **_kwargs: object) -> None:
            pass

        def snapshot(self) -> object:
            return type(
                "Snapshot",
                (),
                {
                    "retry_not_before_utc": None,
                    "last_request_started_at_utc": None,
                },
            )()

    class _Transport:
        def __init__(self, **kwargs: object) -> None:
            transports.append(kwargs)

    class _Client:
        def __init__(self, *, config: object, transport: object) -> None:
            assert config == "paper-config"
            assert isinstance(transport, _Transport)
            clients.append(self)

        def authenticate_token_only(self) -> None:
            return None

    monkeypatch.setattr(script, "KisPaperMarketDataTokenStartGate", _TokenGate)
    monkeypatch.setattr(script, "KisPaperMarketDataRateGate", _RateGate)
    monkeypatch.setattr(script, "UrllibKisPaperMarketDataTransport", _Transport)
    monkeypatch.setattr(script, "KisPaperMarketDataClient", _Client)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: "paper-config",
    )
    monkeypatch.setattr(
        script,
        "write_kis_paper_auth_capability_probe",
        lambda outcome, **_kwargs: _run(tmp_path, outcome),
    )

    assert script.main(["--execute"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(clients) == 1
    assert len(transports) == 1
    assert set(transports[0]) == {"request_gate", "token_start_gate"}
    assert payload["status"] == "authenticated"
    assert "reason" not in payload


def test_auth_probe_script_has_no_live_or_account_credential_path() -> None:
    path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_auth_capability.py"
    source = path.read_text(encoding="utf-8")

    assert "KIS_LIVE" not in source
    assert "KIS_PAPER_ACCOUNT" not in source
    assert "load_kis_paper_market_data_config" not in source


def _script_module() -> object:
    path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_auth_capability.py"
    spec = importlib.util.spec_from_file_location("probe_kis_paper_auth_capability_for_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(
    tmp_path: Path,
    outcome: probe.KisPaperAuthCapabilityProbeOutcome,
) -> probe.KisPaperAuthCapabilityProbeRun:
    path = tmp_path / "receipt.json"
    path.write_text("{}\n", encoding="utf-8")
    return probe.KisPaperAuthCapabilityProbeRun(
        outcome=outcome,
        receipt_path=path,
        receipt_sha256="sha256:" + "a" * 64,
    )
