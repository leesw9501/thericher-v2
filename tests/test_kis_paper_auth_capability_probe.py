from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import kis_paper_auth_capability_probe as probe
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
)


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
        lambda outcome, **_kwargs: artifact_payloads.append(outcome) or _run(tmp_path, outcome),
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


@pytest.mark.parametrize("code", ["EGW00103", "EGW00105", "EGW00132", "EGW00133", "EGW00201"])
@pytest.mark.parametrize("field", ["msg_cd", "error_code"])
def test_token_probe_projects_only_exact_single_field_codes(code: str, field: str) -> None:
    response = KisMarketDataResponse.from_payload(
        {field: code, "error_description": "private-description-canary"}, status_code=400
    )
    payload = probe.project_kis_paper_token_probe_envelope(response).safe_payload()

    assert payload[field] == code
    assert payload["agreed_code"] == code
    assert payload["code_relation"] == "single"
    assert payload["http_status_class"] == "4xx"
    assert "private-description-canary" not in json.dumps(payload)
    if code == "EGW00133":
        assert payload["semantic_support"] == {code: "not_in_verified_catalog"}


@pytest.mark.parametrize("code", ["EGW00103", "EGW00105", "EGW00132", "EGW00133", "EGW00201"])
def test_token_probe_agreement_is_exact_not_semantic(code: str) -> None:
    envelope = probe.project_kis_paper_token_probe_envelope(
        KisMarketDataResponse.from_payload({"msg_cd": code, "error_code": code})
    ).safe_payload()
    assert envelope["code_relation"] == "agreement"
    assert envelope["agreed_code"] == code
    assert envelope["http_2xx_with_allowlisted_error_code"] is True


@pytest.mark.parametrize(
    "msg_cd,error_code",
    [
        ("EGW00201", "EGW00103"),
        ("EGW00133", "private-unknown-canary"),
        ("private-unknown-canary", "EGW00105"),
        ("private-unknown-canary", "different-private-canary"),
        ("EGW00132", {"secret": "private-unknown-canary"}),
    ],
)
def test_token_probe_conflicting_fields_never_become_an_agreed_cause(
    msg_cd: object, error_code: object
) -> None:
    envelope = probe.project_kis_paper_token_probe_envelope(
        KisMarketDataResponse.from_payload({"msg_cd": msg_cd, "error_code": error_code})
    ).safe_payload()
    assert envelope["code_relation"] == "conflict"
    assert "agreed_code" not in envelope
    assert envelope["http_2xx_with_allowlisted_error_code"] == bool(
        envelope.get("msg_cd") or envelope.get("error_code")
    )
    assert "private" not in json.dumps(envelope)


@pytest.mark.parametrize(
    "value", ["egw00133", " EGW00133 ", "EGW99999", "private-canary", [], 1, True]
)
def test_token_probe_omits_arbitrary_or_normalized_codes(value: object) -> None:
    payload = probe.project_kis_paper_token_probe_envelope(
        KisMarketDataResponse.from_payload({"error_code": value})
    ).safe_payload()
    assert payload["code_relation"] == "unclassified"
    assert "error_code" not in payload
    assert "agreed_code" not in payload
    assert payload["http_2xx_with_allowlisted_error_code"] is False


@pytest.mark.parametrize("body", [b"private-invalid-json-canary", b"[]"])
def test_token_probe_invalid_body_retains_only_class(body: bytes) -> None:
    payload = probe.project_kis_paper_token_probe_envelope(
        KisMarketDataResponse(status_code=503, headers={}, body=body)
    ).safe_payload()
    assert payload == {
        "http_status_class": "5xx",
        "code_relation": "invalid_body",
        "http_2xx_with_allowlisted_error_code": False,
    }


def _page_response(rows: list[dict[str, str]] | None = None) -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload(
        {
            "rt_cd": "0",
            "output1": {"next": "", "more": "0"},
            "output2": rows
            if rows is not None
            else [
                {
                    "xymd": "20261007",
                    "xhms": "110000",
                    "kymd": "20261008",
                    "khms": "000000",
                    "open": "100",
                    "high": "102",
                    "low": "99",
                    "last": "101",
                    "evol": "1000",
                }
            ],
        }
    )


def _head_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    responses: list[KisMarketDataResponse],
    *,
    latency: float = 1.1,
) -> SimpleNamespace:
    script = _script_module()
    now = datetime(2026, 10, 8, tzinfo=UTC)
    state = {"elapsed": 0.0}
    requests = []
    factories = []
    sleeps = []
    original_transport = script.UrllibKisPaperMarketDataTransport

    class _HttpResponse:
        def __init__(self, response: KisMarketDataResponse) -> None:
            self.status = response.status_code
            self.headers = response.headers
            self.body = response.body

        def __enter__(self) -> _HttpResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    class _Opener:
        def open(self, request: object, *, timeout: float) -> _HttpResponse:
            requests.append(request)
            assert timeout == 15.0
            response = responses.pop(0)
            state["elapsed"] += latency
            if "after_response" in state:
                state["after_response"]()
            return _HttpResponse(response)

    def transport_factory(**kwargs: object) -> object:
        factories.append(kwargs)
        transport = original_transport(**kwargs)
        transport._opener = _Opener()
        return transport

    monkeypatch.setattr(script, "UrllibKisPaperMarketDataTransport", transport_factory)
    monkeypatch.setattr(
        script,
        "load_kis_paper_market_data_environment_config",
        lambda: KisPaperMarketDataConfig(
            app_key="private-key-canary", app_secret="private-secret-canary"
        ),
    )

    def pacing_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        state["elapsed"] += seconds

    return SimpleNamespace(
        script=script,
        now=now,
        state=state,
        requests=requests,
        factories=factories,
        sleeps=sleeps,
        control_root=tmp_path / "control",
        clock=lambda: now + timedelta(seconds=state["elapsed"]),
        monotonic=lambda: state["elapsed"],
        pacing_sleeper=pacing_sleep,
    )


def _head_run(fixture: SimpleNamespace) -> probe.KisPaperAuthCapabilityProbeOutcome:
    return fixture.script._run_head_page_probe(
        control_root=fixture.control_root,
        observed_at=fixture.now,
        clock=fixture.clock,
        monotonic=fixture.monotonic,
        pacing_sleeper=fixture.pacing_sleeper,
    )


def _token_response() -> KisMarketDataResponse:
    return KisMarketDataResponse.from_payload({"access_token": "private-token-canary"})


def test_head_probe_reuses_one_token_for_one_parsed_page_and_retains_no_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [_token_response(), _page_response()])
    monkeypatch.setattr(
        fixture.script.KisPaperMarketDataClient,
        "authenticate_token_only",
        lambda _self: pytest.fail("new mode must not clear the token"),
    )
    outcome = _head_run(fixture)
    payload = outcome.safe_payload()
    assert outcome.status == "authenticated"
    assert [request.method for request in fixture.requests] == ["POST", "GET"]
    assert fixture.requests[1].get_header("Authorization") == "Bearer private-token-canary"
    assert payload["page_probe"]["accepted_rows"] == 1
    assert payload["page_probe"]["transport_dispatch_counts"] == {"token": 1, "minute_page": 1}
    assert payload["route_isolation"]["token_only"] is False
    assert payload["route_isolation"]["raw_market_rows_retained"] is False
    assert "canary" not in json.dumps(payload)
    assert "output2" not in json.dumps(payload)


@pytest.mark.parametrize(
    "response,reason,page_status",
    [
        (_page_response([]), "minute_response_empty", "empty"),
        (
            KisMarketDataResponse.from_payload({"rt_cd": "0", "output1": {}, "output2": None}),
            "minute_response_invalid",
            "invalid",
        ),
        (
            KisMarketDataResponse(status_code=200, headers={}, body=b"private-body-canary"),
            "response_invalid",
            "invalid",
        ),
        (
            KisMarketDataResponse.from_payload({"rt_cd": "1", "msg1": "private-body-canary"}),
            "minute_response_rejected",
            "rejected",
        ),
    ],
)
def test_head_probe_distinguishes_token_success_from_page_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: KisMarketDataResponse,
    reason: str,
    page_status: str,
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [_token_response(), response])
    outcome = _head_run(fixture)
    assert outcome.status == "unavailable"
    assert outcome.reason == reason
    assert outcome.page_probe.token_status == "accepted"
    assert outcome.page_probe.page_status == page_status
    assert "canary" not in json.dumps(outcome.safe_payload())


@pytest.mark.parametrize(
    "body,status,reason",
    [
        ({"error_code": "EGW00133", "error_description": "private-canary"}, 400, "auth_rejected"),
        ({"error_code": "EGW00201"}, 400, "auth_rejected"),
        ({"msg_cd": "EGW00201", "error_code": "EGW00103"}, 400, "rate_limited"),
        ({"error_code": "EGW00105"}, 429, "rate_limited"),
        ({"error_code": "EGW00103"}, 200, "auth_response_invalid"),
    ],
)
def test_head_probe_observes_error_code_without_changing_production_rate_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: dict[str, str], status: int, reason: str
) -> None:
    fixture = _head_fixture(
        monkeypatch, tmp_path, [KisMarketDataResponse.from_payload(body, status_code=status)]
    )
    outcome = _head_run(fixture)
    assert outcome.reason == reason
    assert len(fixture.requests) == 1
    assert outcome.page_probe.page_transport_calls == 0
    assert outcome.page_probe.token_envelope.error_code == body["error_code"]
    assert "canary" not in json.dumps(outcome.safe_payload())


def test_fast_token_response_uses_only_bounded_normal_worker_pacing_without_extra_post(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _head_fixture(
        monkeypatch, tmp_path, [_token_response(), _page_response()], latency=0.1
    )
    outcome = _head_run(fixture)
    assert outcome.status == "authenticated"
    assert outcome.page_probe.token_status == "accepted"
    assert outcome.page_probe.page_status == "nonempty"
    assert fixture.sleeps == [pytest.approx(0.9)]
    assert [request.method for request in fixture.requests] == ["POST", "GET"]


@pytest.mark.parametrize("external", ["cooldown", "owner"])
def test_post_token_external_wait_yields_without_normal_pacing_sleep(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, external: str
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [_token_response()], latency=0.1)

    def external_change() -> None:
        gate = fixture.script.KisPaperMarketDataRateGate(
            control_root=fixture.control_root,
            clock=fixture.clock,
            minimum_request_interval_seconds=0.01,
        )
        if external == "cooldown":
            gate.record_rate_limit()
        else:
            gate.wait_for_request_slot()

    fixture.state["after_response"] = external_change
    outcome = _head_run(fixture)
    assert outcome.reason == ("rate_limited" if external == "cooldown" else "request_not_due")
    assert outcome.page_probe.token_status == "accepted"
    assert fixture.sleeps == []
    assert len(fixture.requests) == 1


def test_normal_pacing_cannot_extend_probe_initiation_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [_token_response()], latency=0.1)
    fixture.monotonic = lambda: (
        fixture.state["elapsed"] + (59.8 if fixture.state["elapsed"] else 0.0)
    )
    outcome = _head_run(fixture)
    assert outcome.reason == "probe_expired"
    assert fixture.sleeps == []
    assert len(fixture.requests) == 1


def test_pacing_delay_above_existing_interval_yields_instead_of_sleeping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [_token_response()])
    original_factory = fixture.script.UrllibKisPaperMarketDataTransport

    def factory(**kwargs: object) -> object:
        transport = original_factory(**kwargs)
        gate = kwargs["request_gate"]
        original_wait = gate.wait_for_request_slot
        calls = 0

        def wait() -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                gate._sleeper(1.01)
            else:
                original_wait()

        monkeypatch.setattr(gate, "wait_for_request_slot", wait)
        return transport

    monkeypatch.setattr(fixture.script, "UrllibKisPaperMarketDataTransport", factory)
    outcome = _head_run(fixture)
    assert outcome.reason == "request_not_due"
    assert fixture.sleeps == []
    assert len(fixture.requests) == 1


@pytest.mark.parametrize("gate", ["token", "request"])
def test_head_probe_not_due_skips_config_and_has_no_http_diagnostics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, gate: str
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [])
    if gate == "token":
        fixture.script.KisPaperMarketDataTokenStartGate(
            control_root=fixture.control_root, clock=fixture.clock
        ).claim_token_request_start()
    else:
        fixture.script.KisPaperMarketDataRateGate(
            control_root=fixture.control_root, clock=fixture.clock
        ).wait_for_request_slot()
    monkeypatch.setattr(
        fixture.script,
        "load_kis_paper_market_data_environment_config",
        lambda: pytest.fail("deferred probe must not load config"),
    )
    outcome = _head_run(fixture)
    assert outcome.reason == ("token_request_not_due" if gate == "token" else "request_not_due")
    assert outcome.page_probe.token_envelope is None
    assert not fixture.requests
    assert outcome.page_probe.next_due is not None


def test_head_probe_atomic_token_claim_race_has_no_http_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [])
    monkeypatch.setattr(
        fixture.script.KisPaperMarketDataTokenStartGate,
        "claim_token_request_start",
        lambda _self: False,
    )
    outcome = _head_run(fixture)
    assert outcome.reason == "token_request_not_due"
    assert not fixture.requests
    assert outcome.page_probe.token_envelope is None
    assert outcome.page_probe.token_status == "not_attempted"
    assert outcome.page_probe.token_transport_calls == 1


def test_head_probe_request_race_yields_in_existing_sleeper_hook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [])
    original_factory = fixture.script.UrllibKisPaperMarketDataTransport

    def race(**kwargs: object) -> object:
        kwargs["request_gate"].wait_for_request_slot()
        return original_factory(**kwargs)

    monkeypatch.setattr(fixture.script, "UrllibKisPaperMarketDataTransport", race)
    outcome = _head_run(fixture)
    assert outcome.reason == "request_not_due"
    assert not fixture.requests
    assert outcome.page_probe.token_envelope is None
    assert outcome.page_probe.token_status == "not_attempted"
    assert outcome.page_probe.token_transport_calls == 1


def test_head_probe_expiration_between_post_and_get_does_not_reauthenticate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [_token_response()], latency=60.0)
    outcome = _head_run(fixture)
    assert outcome.reason == "probe_expired"
    assert outcome.page_probe.token_status == "accepted"
    assert outcome.page_probe.page_transport_calls == 0
    assert len(fixture.requests) == 1


@pytest.mark.parametrize("expire_call", [2, 4])
def test_head_probe_expiration_before_config_or_at_guard_cannot_start_http(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, expire_call: int
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [])
    calls = 0

    def monotonic() -> float:
        nonlocal calls
        calls += 1
        return 60.0 if calls >= expire_call else 0.0

    fixture.monotonic = monotonic
    if expire_call == 2:
        monkeypatch.setattr(
            fixture.script,
            "load_kis_paper_market_data_environment_config",
            lambda: pytest.fail("expired probe must not load config"),
        )
    outcome = _head_run(fixture)
    assert outcome.reason == "probe_expired"
    assert not fixture.requests
    assert outcome.page_probe.token_status == "not_attempted"
    assert outcome.page_probe.token_transport_calls == (1 if expire_call == 4 else 0)


def test_probe_wrapper_caps_delegation_rejects_foreign_routes_and_expired_requests() -> None:
    script = _script_module()
    calls = []
    delegate = SimpleNamespace(request=lambda request: calls.append(request) or _token_response())
    wrapper = script._ProbeTransport(delegate, deadline=60.0, monotonic=lambda: 0.0)
    request = KisMarketDataRequest(
        method="POST", url=KIS_PAPER_MARKET_DATA_BASE_URL + KIS_PAPER_TOKEN_PATH, headers={}
    )
    wrapper.request(request)
    with pytest.raises(KisPaperMarketDataError, match="probe_request_budget_exhausted"):
        wrapper.request(request)
    with pytest.raises(KisPaperMarketDataError, match="probe_request_not_allowed"):
        wrapper.request(replace(request, url="https://foreign.invalid/token"))
    expired = script._ProbeTransport(delegate, deadline=60.0, monotonic=lambda: 60.0)
    with pytest.raises(KisPaperMarketDataError, match="probe_expired"):
        expired.request(request)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"token_transport_calls": 2},
        {"page_transport_calls": True},
        {"accepted_rows": 1},
        {"page_status": "private-canary"},
        {"token_status": "private-canary"},
        {"page_status": "nonempty"},
        {"token_envelope": probe.KisPaperTokenProbeEnvelope("4xx")},
    ],
)
def test_page_probe_receipt_rejects_unbounded_or_inconsistent_facts(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        probe.KisPaperAuthPageProbeDetails(completed_at=datetime(2026, 10, 8, tzinfo=UTC), **kwargs)


def test_head_mode_cli_writes_hash_bound_safe_receipt_and_restricts_control_alias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _head_fixture(monkeypatch, tmp_path, [_token_response(), _page_response()])
    original_run = fixture.script._run_head_page_probe
    monkeypatch.setattr(
        fixture.script,
        "_run_head_page_probe",
        lambda **kwargs: original_run(**{**kwargs, "control_root": fixture.control_root}),
    )
    repository = tmp_path / "repo"
    repository.mkdir()
    original_writer = fixture.script.write_kis_paper_auth_capability_probe
    monkeypatch.setattr(
        fixture.script,
        "write_kis_paper_auth_capability_probe",
        lambda outcome, **kwargs: original_writer(
            outcome, **{**kwargs, "artifact_root": tmp_path / "artifacts", "repo_root": repository}
        ),
    )
    args = [
        "--execute",
        "--head-page-once",
        "--control-root",
        str(fixture.script._HEAD_CONTROL_ROOT),
    ]
    assert fixture.script.main(args, clock=fixture.clock, monotonic=fixture.monotonic) == 0
    output = json.loads(capsys.readouterr().out)
    receipt = Path(output["receipt_path"]).read_bytes()
    assert output["receipt_sha256"] == "sha256:" + hashlib.sha256(receipt).hexdigest()
    assert output["page_probe"] == json.loads(receipt)["outcome"]["page_probe"]
    assert b"canary" not in receipt
    assert "canary" not in json.dumps(output)
    assert (
        fixture.script.main(["--execute", "--control-root", str(fixture.script._HEAD_CONTROL_ROOT)])
        == 2
    )
    assert (
        fixture.script.main(["--execute", "--head-page-once", "--control-root", "/arbitrary"]) == 2
    )
