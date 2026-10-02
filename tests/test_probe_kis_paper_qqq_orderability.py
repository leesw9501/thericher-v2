"""Offline tests of the production one-shot entry point; no private state."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.kis_market_data_rate_gate import KisPaperMarketDataTokenStartGate
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_BASE_URL,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KIS_PAPER_TOKEN_PATH,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperConfig,
    KisPaperReadOnlyError,
)

SPEC = importlib.util.spec_from_file_location(
    "qqq_orderability_probe",
    Path(__file__).resolve().parents[1] / "scripts" / "probe_kis_paper_qqq_orderability.py",
)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

SECRET = "PRIVATE_SENTINEL_NEVER_PRINT_OR_PERSIST"
ACCOUNT = "87654321"


class _Gate:
    def __init__(self, due=True):
        self.due = due
        self.claims = 0
        self.snapshots = 0

    def claim_token_request_start(self):
        self.claims += 1
        return self.due

    def snapshot(self):
        self.snapshots += 1
        return SimpleNamespace(next_token_request_not_before_utc=datetime(2026, 10, 3, tzinfo=UTC))


class _Transport:
    def __init__(self, response=None, auth=None, gate=None):
        self.response = response or _response()
        self.auth = auth or KisHttpResponse.from_payload({"access_token": SECRET})
        self.requests = []
        self.gate = gate

    def request(self, request):
        if request.method == "POST" and self.gate is not None:
            assert self.gate.claims == 1
        self.requests.append(request)
        return self.auth if request.method == "POST" else self.response


def _response():
    return KisHttpResponse.from_payload(
        {
            "rt_cd": "0",
            "msg1": SECRET,
            "output": {
                "tr_crcy_cd": "USD",
                "ord_psbl_frcr_amt": "987654321.12",
                "ovrs_ord_psbl_amt": "123456789.98",
            },
        }
    )


def _config(_environment):
    return KisPaperConfig(
        app_key=SECRET, app_secret=SECRET, account_number=ACCOUNT, account_product_code="01"
    )


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("real dependency forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(probe, "UrllibKisHttpTransport", deny)
    monkeypatch.setattr(probe, "load_kis_paper_config", deny)
    monkeypatch.setattr(probe, "load_kis_paper_config_from_environment", deny)
    monkeypatch.setattr(probe, "KisPaperMarketDataTokenStartGate", deny)


def _run(tmp_path, capsys, *, response=None, auth=None, due=True, loader=_config):
    gate = _Gate(due)
    transport = _Transport(response, auth, gate)
    code = probe.main(
        ["--execute", "--artifact-root", str(tmp_path / "artifacts")],
        transport=transport,
        token_gate=gate,
        config_loader=loader,
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    paths = list(
        (tmp_path / "artifacts" / "execution" / "kis-paper-qqq-orderability-probe").glob("*.json")
    )
    assert len(paths) == 1
    raw = paths[0].read_bytes()
    assert payload.pop("receipt_sha256") == hashlib.sha256(raw).hexdigest()
    assert json.loads(raw) == payload
    assert payload["evidence_path"] == str(paths[0].resolve())
    assert datetime.fromisoformat(payload["observed_at"]).utcoffset() == UTC.utcoffset(None)
    for private in (SECRET, ACCOUNT, "987654321.12", "123456789.98", "90070000", "40910000"):
        assert private not in captured.out + raw.decode()
    assert payload["environment"] == "paper"
    assert payload["read_only"] is True and payload["submit"] is False
    assert payload["actual_order_limit"] is False and payload["funds_readiness_proof"] is False
    return code, payload, transport, gate


def test_preview_no_operational_io(monkeypatch, capsys):
    def deny(*args, **kwargs):
        raise AssertionError("preview performed IO")

    monkeypatch.setattr(probe, "ensure_external_artifact_directory", deny)
    monkeypatch.setattr(probe, "resolve_model_artifact_root", deny)
    monkeypatch.setattr(Path, "read_bytes", deny)
    monkeypatch.setattr(Path, "read_text", deny)
    monkeypatch.setattr(Path, "open", deny)
    monkeypatch.setattr(Path, "is_file", deny)
    assert probe.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "deferred"
    assert payload["auth_requests"] == payload["query_requests"] == 0
    assert "receipt_sha256" not in payload


def test_exact_pair_in_memory_only(tmp_path, capsys, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("private state read forbidden")

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "read_bytes", deny)
        scoped.setattr(Path, "read_text", deny)
        # Receipt reads occur in _run after the entry point; capture separately here.
        gate = _Gate()
        transport = _Transport(gate=gate)
        assert (
            probe.main(
                ["--execute", "--artifact-root", str(tmp_path / "artifacts")],
                transport=transport,
                token_gate=gate,
                config_loader=_config,
            )
            == 0
        )
    captured = capsys.readouterr().out
    assert SECRET not in captured and ACCOUNT not in captured
    assert len(transport.requests) == 2
    auth, query = transport.requests
    assert auth.method == "POST" and auth.url.endswith(KIS_PAPER_TOKEN_PATH)
    assert query.method == "GET" and query.url.endswith(KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.path)
    assert dict(query.query) == {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",
        "OVRS_ORD_UNPR": "1",
        "ITEM_CD": "QQQ",
    }
    assert query.headers["tr_id"] == "VTTS3007R"
    assert gate.claims == 1 and gate.snapshots == 0
    assert json.loads(captured)["status"] == "accepted"
    receipt = next((tmp_path / "artifacts").rglob("*.json"))
    assert SECRET not in receipt.read_text()
    assert len(list((tmp_path / "artifacts").rglob("*token*"))) == 0


def test_accepted_metadata_receipt(tmp_path, capsys):
    code, payload, _, _ = _run(tmp_path, capsys)
    assert code == 0 and payload["status"] == "accepted"
    assert payload["auth_requests"] == payload["query_requests"] == 1


def test_deferred_no_network_no_sleep(tmp_path, capsys, monkeypatch):
    import time

    monkeypatch.setattr(time, "sleep", lambda _: pytest.fail("must yield, not sleep"))
    code, payload, transport, gate = _run(tmp_path, capsys, due=False)
    assert code == 0 and payload["status"] == "deferred"
    assert payload["category"] == "token_request_not_due"
    assert payload["owned_next_due"] == "2026-10-03T00:00:00+00:00"
    assert not transport.requests and gate.claims == gate.snapshots == 1


@pytest.mark.parametrize("auth_failure", [False, True])
@pytest.mark.parametrize(
    "upstream,category",
    [
        ("90070000", "paper_account_user_mismatch"),
        ("40910000", "paper_account_expired"),
        ("12349876", "upstream_unclassified"),
        ("APBK0918", "upstream_unclassified"),
        (SECRET, "upstream_unclassified"),
    ],
)
def test_categorical_provider_failure(tmp_path, capsys, upstream, category, auth_failure):
    response = KisHttpResponse.from_payload({"rt_cd": "1", "msg_cd": upstream, "msg1": SECRET})
    failure = {"auth": response} if auth_failure else {"response": response}
    code, payload, transport, _ = _run(tmp_path, capsys, **failure)
    assert code == 1 and payload["status"] == "failed" and payload["category"] == category
    assert len(transport.requests) == (1 if auth_failure else 2)


@pytest.mark.parametrize(
    "body",
    [
        b"not json PRIVATE_SENTINEL_NEVER_PRINT_OR_PERSIST",
        b"[]",
        b'{"rt_cd":"0","rt_cd":"0","output":{}}',
        b'{"rt_cd":"0","output":{}}',
        b'{"rt_cd":"0","output":[{},{}]}',
    ],
)
def test_malformed_response_safe(tmp_path, capsys, body):
    code, payload, _, _ = _run(tmp_path, capsys, response=KisHttpResponse(200, {}, body))
    assert code == 1 and payload["category"] == "parse_failure"


def test_exception_text_never_output(tmp_path, capsys):
    def bad_loader(_environment):
        raise ValueError(SECRET)

    code, payload, transport, gate = _run(tmp_path, capsys, loader=bad_loader)
    assert code == 1 and payload["category"] == "local_failure"
    assert not transport.requests and gate.claims == 0


def _auth_request():
    return KisHttpRequest(
        "POST",
        KIS_PAPER_BASE_URL + KIS_PAPER_TOKEN_PATH,
        {"content-type": "application/json", "accept": "application/json"},
        json_body={"grant_type": "client_credentials", "appkey": SECRET, "appsecret": SECRET},
    )


def _query_request(**changes):
    query = {
        "CANO": ACCOUNT,
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",
        "OVRS_ORD_UNPR": "1",
        "ITEM_CD": "QQQ",
        **changes,
    }
    return KisHttpRequest(
        "GET",
        KIS_PAPER_BASE_URL + KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.path,
        {
            "tr_id": "VTTS3007R",
            "authorization": f"Bearer {SECRET}",
            "appkey": SECRET,
            "appsecret": SECRET,
            "custtype": "P",
            "tr_cont": "",
        },
        query=query,
    )


@pytest.mark.parametrize(
    "changes", [{"ITEM_CD": "SPY"}, {"OVRS_EXCG_CD": "AMEX"}, {"OVRS_ORD_UNPR": "2"}]
)
def test_wrong_query_rejected_before_transport(changes):
    gate = _Gate()
    transport = _Transport()
    scoped = probe._ScopedTransport(transport, gate)
    scoped.request(_auth_request())
    with pytest.raises(probe._ProbeFailure):
        scoped.request(_query_request(**changes))
    assert len(transport.requests) == 1 and gate.claims == 1


def test_repeated_requests_and_other_paths_forbidden():
    gate = _Gate()
    transport = _Transport()
    scoped = probe._ScopedTransport(transport, gate)
    with pytest.raises(probe._ProbeFailure):
        scoped.request(_query_request())
    scoped.request(_auth_request())
    with pytest.raises(probe._ProbeFailure):
        scoped.request(_auth_request())
    scoped.request(_query_request())
    with pytest.raises(probe._ProbeFailure):
        scoped.request(_query_request())
    with pytest.raises(KisPaperReadOnlyError):
        scoped.request(
            KisHttpRequest(
                "POST",
                KIS_PAPER_BASE_URL + "/uapi/overseas-stock/v1/trading/order",
                {},
                json_body={},
            )
        )
    balance = KisHttpRequest(
        "GET",
        KIS_PAPER_BASE_URL + KIS_PAPER_BALANCE_ENDPOINT.path,
        {**_query_request().headers, "tr_id": "VTTS3012R"},
        query={
            "CANO": ACCOUNT,
            "ACNT_PRDT_CD": "01",
            "OVRS_EXCG_CD": "NASD",
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        },
    )
    with pytest.raises(probe._ProbeFailure):
        scoped.request(balance)
    assert len(transport.requests) == 2 and gate.claims == 1


def test_existing_receipt_not_overwritten_or_requeried(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(probe.uuid, "uuid4", lambda: SimpleNamespace(hex="fixed"))
    _run(tmp_path, capsys)
    receipt = next((tmp_path / "artifacts").rglob("*.json"))
    before = receipt.read_bytes()
    gate, transport = _Gate(), _Transport()
    assert (
        probe.main(
            ["--execute", "--artifact-root", str(tmp_path / "artifacts")],
            transport=transport,
            token_gate=gate,
            config_loader=_config,
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
    assert receipt.read_bytes() == before
    assert not transport.requests and gate.claims == 0


def test_repo_receipt_root_rejected_before_credentials(capsys):
    root = Path(probe.__file__).resolve().parents[1]
    assert probe.main(["--execute", "--artifact-root", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_existing_token_start_decision_reused_no_secret_cache(tmp_path, capsys):
    now = datetime(2026, 10, 3, tzinfo=UTC)
    control = tmp_path / "existing-data-control"
    args = ["--execute", "--artifact-root", str(tmp_path / "artifacts")]
    first = _Transport()
    gate = KisPaperMarketDataTokenStartGate(control_root=control, clock=lambda: now)
    assert probe.main(args, transport=first, token_gate=gate, config_loader=_config) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "accepted"
    second = _Transport()
    reopened = KisPaperMarketDataTokenStartGate(control_root=control, clock=lambda: now)
    assert probe.main(args, transport=second, token_gate=reopened, config_loader=_config) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "deferred"
    assert payload["owned_next_due"] == "2026-10-03T00:05:00+00:00"
    assert len(first.requests) == 2 and not second.requests
    assert {path.name for path in control.iterdir()} == {"token-request.json", "token-request.lock"}
    assert SECRET not in (control / "token-request.json").read_text()
    assert ACCOUNT not in (control / "token-request.json").read_text()


def test_default_control_root_matches_data_owner(tmp_path, capsys, monkeypatch):
    captured = []
    gate = _Gate(due=False)

    def factory(*, control_root):
        captured.append(control_root)
        return gate

    monkeypatch.setenv("THERICHER_MARKET_DATA_ROOT", str(tmp_path / "market_data"))
    monkeypatch.setattr(probe, "KisPaperMarketDataTokenStartGate", factory)
    transport = _Transport()
    assert (
        probe.main(
            ["--execute", "--artifact-root", str(tmp_path / "artifacts")],
            transport=transport,
            config_loader=_config,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "deferred"
    assert captured == [
        tmp_path / "market_data" / "us_equities" / "kis_paper_private" / "collection-control-v1"
    ]
    assert not transport.requests


def test_deferral_cannot_retry_same_transport():
    gate, transport = _Gate(due=False), _Transport()
    scoped = probe._ScopedTransport(transport, gate)
    with pytest.raises(probe._Deferred):
        scoped.request(_auth_request())
    with pytest.raises(probe._ProbeFailure):
        scoped.request(_auth_request())
    assert gate.claims == 1 and not transport.requests


@pytest.mark.parametrize("docker", [False, True])
def test_default_loader_selection_without_private_reads(tmp_path, capsys, monkeypatch, docker):
    calls = []

    def detect(path):
        assert path == Path("/.dockerenv")
        calls.append("detect")
        return docker

    def native(path):
        assert path == Path(probe.__file__).resolve().parents[1] / ".env"
        calls.append("native")
        return _config(None)

    def environment(mapping):
        assert mapping is probe.os.environ
        calls.append("environment")
        return _config(None)

    monkeypatch.setattr(Path, "is_file", detect)
    monkeypatch.setattr(probe, "load_kis_paper_config", native)
    monkeypatch.setattr(probe, "load_kis_paper_config_from_environment", environment)
    code, payload, transport, _ = _run(tmp_path, capsys, loader=None)
    assert code == 0 and payload["status"] == "accepted"
    assert calls == ["detect", "environment" if docker else "native"]
    assert len(transport.requests) == 2


def test_injected_loader_gets_mapping_without_docker_detection(tmp_path, capsys, monkeypatch):
    def deny(*args):
        raise AssertionError("injected loader must bypass detection")

    def injected(mapping):
        assert mapping is probe.os.environ
        return _config(mapping)

    monkeypatch.setattr(Path, "is_file", deny)
    assert _run(tmp_path, capsys, loader=injected)[0] == 0


@pytest.mark.parametrize("outcome", ["accepted", "failed", "deferred"])
def test_single_final_utc_observation_and_exact_receipt_pointer(
    tmp_path, capsys, monkeypatch, outcome
):
    calls = []
    observed = datetime(2026, 10, 3, 22, 54, 37, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            calls.append(tz)
            return observed

    monkeypatch.setattr(probe, "datetime", Clock)
    # No deferral snapshot date is needed to test the final clock independently.
    gate = _Gate(due=outcome != "deferred")
    if outcome == "deferred":
        gate.snapshot = lambda: SimpleNamespace(next_token_request_not_before_utc=None)
    response = _response() if outcome != "failed" else KisHttpResponse(200, {}, b"invalid")
    transport = _Transport(response=response)
    root = tmp_path / "artifacts"
    code = probe.main(
        ["--execute", "--artifact-root", str(root)],
        transport=transport,
        token_gate=gate,
        config_loader=_config,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == (1 if outcome == "failed" else 0)
    assert payload["status"] == outcome and payload["observed_at"] == observed.isoformat()
    assert calls == [UTC]
    receipt = Path(payload["evidence_path"])
    assert receipt == next(root.rglob("*.json")).resolve()
    raw = receipt.read_bytes()
    assert payload.pop("receipt_sha256") == hashlib.sha256(raw).hexdigest()
    assert json.loads(raw) == payload
