"""Counts-only holdings contract; synthetic transports, no operational IO."""

from __future__ import annotations

import builtins
import io
import json
import os
import socket
import subprocess
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_kis_paper_stock_exit_reads import ExitTransport
from thericher_v2.execution import kis_paper_holdings as holdings
from thericher_v2.execution import kis_readonly as old
from thericher_v2.execution.kis_paper_quote import build_kis_paper_preview_quote_request

NOW = datetime(2026, 10, 24, 5, 30, tzinfo=UTC)
INVOCATION = "8db529ee-55cf-43ed-8a4d-0782f8e47c83"
PRIVATE = "private_reason_canary_83"
_DEFAULT_TRANSPORT = object()
FAKE_ENV = {
    "KIS_PAPER_APP_KEY": "synthetic-key-canary",
    "KIS_PAPER_APP_SECRET": "synthetic-secret-canary",
    "KIS_PAPER_ACCOUNT_NO": "12345678",
    "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
}


@pytest.fixture(autouse=True)
def no_operational_io(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("holdings_test_attempted_operational_io")

    for obj, name in (
        (socket, "create_connection"),
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
        (urllib.request, "urlopen"),
        (urllib.request.OpenerDirector, "open"),
        (subprocess, "Popen"),
        (os, "system"),
        (old, "load_kis_paper_config"),
        (old.KisPaperReadOnlyClient, "_cash_and_orderable_funds"),
        (old.KisPaperReadOnlyClient, "snapshot"),
    ):
        monkeypatch.setattr(obj, name, denied)
    original_open, original_io_open = builtins.open, io.open

    def checked_open(delegate):
        def open_file(file, *args, **kwargs):
            if not isinstance(file, int):
                assert not any(part.lower().startswith(".env") for part in Path(file).parts)
            return delegate(file, *args, **kwargs)

        return open_file

    monkeypatch.setattr(builtins, "open", checked_open(original_open))
    monkeypatch.setattr(io, "open", checked_open(original_io_open))


class PaperEnvironment(Mapping):
    """No enumeration or access to ambient/live keys, even accidentally."""

    def __init__(self, values=None):
        self.values = FAKE_ENV if values is None else values
        self.reads = []

    def __getitem__(self, key):
        assert key in old.KIS_PAPER_ENV_KEYS, "environment_scope_changed"
        self.reads.append(key)
        return self.values[key]

    def __iter__(self):
        pytest.fail("whole_environment_enumeration")

    def __len__(self):
        return len(self.values)


class Gate:
    def __init__(self, allowed=True, due=None, on_claim=None):
        self.allowed, self.due, self.on_claim = allowed, due, on_claim
        self.claims = 0

    def claim_token_request_start(self):
        self.claims += 1
        if self.on_claim:
            self.on_claim()
        return self.allowed

    def snapshot(self):
        if isinstance(self.due, Exception):
            raise self.due
        return SimpleNamespace(next_token_request_not_before_utc=self.due)


@pytest.fixture
def run(tmp_path):
    def execute(transport=_DEFAULT_TRANSPORT, **changes):
        values = {
            "environment": PaperEnvironment(),
            "token_control_root": tmp_path / "control",
            "artifact_root": tmp_path / "artifacts",
            "repository_root": tmp_path / "repository",
            "transport": (ExitTransport(now=NOW) if transport is _DEFAULT_TRANSPORT else transport),
            "token_gate": Gate(),
            "clock": lambda: NOW,
            "monotonic": lambda: 0.0,
            "invocation_id": INVOCATION,
        }
        values.update(changes)
        return holdings.run_kis_paper_holdings(**values)

    return execute


def safe_output(outcome, capsys):
    payload = outcome.evidence_payload()
    text = json.dumps(payload, allow_nan=False) + repr(outcome)
    if outcome.evidence_path:
        text += outcome.evidence_path.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    text += captured.out + captured.err
    for canary in (
        *(value for value in FAKE_ENV.values() if len(value) >= 8),
        "synthetic-token",
        "SYNTH",
        PRIVATE,
    ):
        assert canary not in text
    assert payload["read_only"] is True and payload["paper_only"] is True
    assert payload["submit_capability"] is False
    assert payload["owned_inventory_or_fill_proven"] is False
    assert payload["account_risk_snapshot_complete"] is False
    return payload


def test_complete_native_account_groups_one_token_no_funds_quotes(run, capsys):
    transport, gate, environment = ExitTransport(now=NOW), Gate(), PaperEnvironment()
    outcome = run(transport, token_gate=gate, environment=environment)
    assert type(outcome) is holdings.KisPaperHoldingsOutcome
    assert (outcome.status, outcome.reason_code) == ("complete", None)
    assert outcome.provider_reason is None
    assert (outcome.position_count, outcome.open_order_count) == (1, 0)
    assert (outcome.post_attempts, outcome.get_attempts, gate.claims) == (1, 4, 1)
    assert outcome.observed_at == outcome.completed_at == NOW
    assert set(environment.reads) == set(old.KIS_PAPER_ENV_KEYS)
    assert {
        request.query["OVRS_EXCG_CD"]
        for request in transport.requests
        if request.headers.get("tr_id") == old.KIS_PAPER_BALANCE_ENDPOINT.tr_id
    } == set(old.KIS_PAPER_US_EXCHANGES)
    assert all(
        urllib.parse.urlsplit(request.url).path
        in {
            old.KIS_PAPER_TOKEN_PATH,
            old.KIS_PAPER_BALANCE_ENDPOINT.path,
            old.KIS_PAPER_OPEN_ORDERS_ENDPOINT.path,
        }
        for request in transport.requests
    )
    assert json.loads(outcome.evidence_path.read_text()) == safe_output(outcome, capsys)


def test_transient_token_reuse_does_not_claim_post_gate(run):
    gate, transport = Gate(allowed=False), ExitTransport(now=NOW)
    outcome = run(transport, token_gate=gate, access_token="synthetic-token")
    assert outcome.status == "complete"
    assert (outcome.post_attempts, outcome.get_attempts, gate.claims) == (0, 4, 0)
    assert all(request.method == "GET" for request in transport.requests)


def test_gate_false_returns_typed_deferred_with_known_utc_due(run, capsys):
    due = NOW + timedelta(minutes=5)
    transport, gate = ExitTransport(now=NOW), Gate(False, due)
    outcome = run(transport, token_gate=gate)
    assert outcome.status == "deferred" and outcome.next_due == due
    assert outcome.position_count is outcome.open_order_count is None
    assert outcome.post_attempts == outcome.get_attempts == 0
    assert gate.claims == 1 and transport.requests == []
    safe_output(outcome, capsys)


def test_unknown_busy_due_is_not_invented_or_provider_text(run, capsys):
    outcome = run(token_gate=Gate(False, OSError(PRIVATE)))
    assert outcome.status == "deferred" and outcome.next_due is None
    assert outcome.position_count is None and outcome.post_attempts == 0
    safe_output(outcome, capsys)


def test_token_opener_failure_consumes_durable_claim_and_attempt(run, tmp_path, capsys):
    class FailingToken(ExitTransport):
        def request(self, request):
            assert request.method == "POST"
            self.requests.append(request)
            raise OSError(PRIVATE)

    transport = FailingToken(now=NOW)
    outcome = run(transport, token_gate=None)
    assert outcome.status == "unavailable"
    assert (outcome.post_attempts, outcome.get_attempts) == (1, 0)
    assert len(transport.requests) == 1
    timing = tmp_path / "control" / "token-request.json"
    assert timing.is_file() and NOW.isoformat().replace("+00:00", "Z") in timing.read_text()
    safe_output(outcome, capsys)


def test_get_failure_is_predebited_once_and_not_retried(run, capsys):
    class FailingGet(ExitTransport):
        def request(self, request):
            if request.method == "GET":
                self.requests.append(request)
                raise TimeoutError(PRIVATE)
            return super().request(request)

    transport = FailingGet(now=NOW)
    outcome = run(transport)
    assert (outcome.status, outcome.post_attempts, outcome.get_attempts) == ("unavailable", 1, 1)
    assert len(transport.requests) == 2
    assert outcome.position_count is outcome.open_order_count is None
    safe_output(outcome, capsys)


def test_later_venue_failure_never_returns_partial_count(run, capsys):
    class LaterVenue(ExitTransport):
        def request(self, request):
            if request.query.get("OVRS_EXCG_CD") == "NYSE":
                self.requests.append(request)
                return old.KisHttpResponse.from_payload({"rt_cd": "1", "msg1": PRIVATE})
            return super().request(request)

    outcome = run(LaterVenue(now=NOW))
    assert outcome.status == "unavailable" and outcome.get_attempts == 3
    assert outcome.position_count is outcome.open_order_count is None
    safe_output(outcome, capsys)


def test_known_numeric_rejection_retains_only_normalized_provider_reason(run, capsys):
    class ExpiredBalance(ExitTransport):
        def request(self, request):
            if request.headers.get("tr_id") == old.KIS_PAPER_BALANCE_ENDPOINT.tr_id:
                self.requests.append(request)
                return old.KisHttpResponse.from_payload(
                    {"rt_cd": "1", "msg_cd": "40910000", "msg1": PRIVATE}
                )
            return super().request(request)

    outcome = run(ExpiredBalance(now=NOW))
    assert outcome.status == "unavailable"
    assert outcome.provider_reason == "paper_account_expired"
    assert outcome.position_count is outcome.open_order_count is None
    assert (outcome.post_attempts, outcome.get_attempts) == (1, 2)
    payload = safe_output(outcome, capsys)
    assert payload["provider_reason"] == "paper_account_expired"
    assert "40910000" not in json.dumps(payload)


def test_raw_codes_and_invented_diagnostics_do_not_become_provider_reasons(run, capsys):
    class UntrustedBalance(ExitTransport):
        def __init__(self, variant):
            super().__init__(now=NOW)
            self.variant = variant

        def request(self, request):
            if request.headers.get("tr_id") != old.KIS_PAPER_BALANCE_ENDPOINT.tr_id:
                return super().request(request)
            self.requests.append(request)
            if self.variant == "raw_response":
                return old.KisHttpResponse.from_payload(
                    {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": PRIVATE}
                )
            raise old.KisPaperReadOnlyError(
                "balance_rejected",
                diagnostic={
                    "upstream_code": "40910000" if self.variant == "raw_numeric" else [PRIVATE],
                    "invented": PRIVATE,
                },
            )

    for index, variant in enumerate(("raw_response", "raw_numeric", "invented"), start=1):
        outcome = run(
            UntrustedBalance(variant),
            invocation_id=f"8db529ee-55cf-43ed-8a4d-0782f8e47c8{index}",
        )
        assert outcome.status == "unavailable" and outcome.provider_reason is None
        assert outcome.position_count is outcome.open_order_count is None
        payload = safe_output(outcome, capsys)
        assert payload["provider_reason"] is None
        assert all(value not in json.dumps(payload) for value in ("EGW00201", "40910000", PRIVATE))


def test_second_page_failure_never_returns_partial_count(run):
    class LaterPage(ExitTransport):
        pages = 0

        def request(self, request):
            if request.headers.get("tr_id") != old.KIS_PAPER_BALANCE_ENDPOINT.tr_id:
                return super().request(request)
            self.pages += 1
            self.requests.append(request)
            if self.pages == 1:
                return old.KisHttpResponse.from_payload(
                    {
                        "rt_cd": "0",
                        "output1": [],
                        "ctx_area_fk200": "SYN-FK",
                        "ctx_area_nk200": "SYN-NK",
                    },
                    headers={"tr_cont": "M"},
                )
            return old.KisHttpResponse.from_payload({"rt_cd": "1", "msg1": PRIVATE})

    transport = LaterPage(now=NOW)
    outcome = run(transport)
    assert outcome.status == "unavailable" and transport.pages == 2
    assert outcome.position_count is outcome.open_order_count is None


@pytest.mark.parametrize("fault", ["endless", "conflicting_balance", "invalid_header"])
def test_native_incomplete_groups_withhold_counts_and_bound_requests(run, fault):
    transport = ExitTransport(now=NOW)
    transport.account_fault = fault
    outcome = run(transport)
    assert outcome.status == "unavailable"
    assert outcome.position_count is outcome.open_order_count is None
    assert outcome.post_attempts == 1 and outcome.get_attempts <= 40
    assert len(transport.requests) == outcome.post_attempts + outcome.get_attempts


@pytest.mark.parametrize("unhashable", [False, True])
def test_untrusted_reason_shaped_code_never_leaks(run, capsys, unhashable):
    class ReasonInjection(ExitTransport):
        def request(self, request):
            code = [PRIVATE] if unhashable else PRIVATE
            raise old.KisPaperReadOnlyError(code, diagnostic={"detail": PRIVATE})

    outcome = run(ReasonInjection(now=NOW))
    assert outcome.status == "unavailable"
    assert outcome.reason_code == "account_snapshot_unavailable"
    safe_output(outcome, capsys)


def test_deadline_before_first_wire_does_not_claim_or_debit(run):
    elapsed = iter([0.0, 121.0, 121.0, 121.0])
    gate, transport = Gate(), ExitTransport(now=NOW)
    outcome = run(transport, token_gate=gate, monotonic=lambda: next(elapsed))
    assert outcome.reason_code == "holdings_deadline_exceeded"
    assert gate.claims == 0 and transport.requests == []
    assert outcome.post_attempts == outcome.get_attempts == 0


def test_deadline_after_gate_claim_keeps_mark_but_sends_no_post(run):
    elapsed = [0.0]
    gate = Gate(on_claim=lambda: elapsed.__setitem__(0, 121.0))
    transport = ExitTransport(now=NOW)
    outcome = run(transport, token_gate=gate, monotonic=lambda: elapsed[0])
    assert outcome.reason_code == "holdings_deadline_exceeded" and gate.claims == 1
    assert transport.requests == [] and outcome.post_attempts == outcome.get_attempts == 0


def test_deadline_after_partial_reads_withholds_counts(run):
    elapsed = [0.0]

    class DelayedGet(ExitTransport):
        def request(self, request):
            response = super().request(request)
            if request.method == "GET":
                elapsed[0] = 121.0
            return response

    outcome = run(DelayedGet(now=NOW), monotonic=lambda: elapsed[0])
    assert outcome.reason_code == "holdings_deadline_exceeded"
    assert (outcome.post_attempts, outcome.get_attempts) == (1, 1)
    assert outcome.position_count is outcome.open_order_count is None


def test_real_urllib_adapter_hook_clamps_timeout_before_mocked_opener(run, monkeypatch):
    elapsed, timeouts = [0.0], []
    delegate = ExitTransport(now=NOW)

    class Response(io.BytesIO):
        def __init__(self, response):
            super().__init__(response.body)
            self.status, self.headers = response.status_code, response.headers

    class Opener:
        def open(self, request, *, timeout):
            timeouts.append(timeout)
            parsed = urllib.parse.urlsplit(request.full_url)
            response = delegate.request(
                old.KisHttpRequest(
                    method=request.method,
                    url=urllib.parse.urlunsplit(
                        (parsed.scheme, parsed.netloc, parsed.path, "", "")
                    ),
                    headers={key.lower(): value for key, value in request.header_items()},
                    query=dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)),
                    json_body=None if request.data is None else json.loads(request.data),
                )
            )
            return Response(response)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(old.KisPaperRequestPacer, "wait_for_request_slot", lambda self: None)
    monkeypatch.setattr(old.KisPaperRequestPacer, "record_request_start", lambda self: None)
    outcome = run(
        transport=None,
        token_gate=Gate(on_claim=lambda: elapsed.__setitem__(0, 119.0)),
        monotonic=lambda: elapsed[0],
    )
    assert outcome.status == "complete"
    assert len(timeouts) == 5 and all(0 < value <= 1.0 for value in timeouts)


def test_existing_invocation_evidence_denies_requery(run):
    transport = ExitTransport(now=NOW)
    first = run(transport)
    original = first.evidence_path.read_bytes()
    with pytest.raises(ValueError):
        run(transport)
    assert len(transport.requests) == 5 and first.evidence_path.read_bytes() == original


@pytest.mark.parametrize("which", ["artifact_root", "token_control_root"])
def test_in_repository_root_denied_before_loader_or_wire(run, tmp_path, monkeypatch, which):
    def forbidden_loader(*args, **kwargs):
        pytest.fail("unsafe_root_reached_config_loader")

    monkeypatch.setattr(holdings, "load_kis_paper_config_from_environment", forbidden_loader)
    transport = ExitTransport(now=NOW)
    with pytest.raises(ValueError):
        run(transport, **{which: tmp_path / "repository" / "unsafe"})
    assert transport.requests == []


def test_invalid_invocation_denied_before_loader_or_wire(run, monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("invalid_invocation_reached_loader")

    monkeypatch.setattr(holdings, "load_kis_paper_config_from_environment", denied)
    transport = ExitTransport(now=NOW)
    with pytest.raises(ValueError):
        run(transport, invocation_id="../not-a-uuid")
    assert transport.requests == []


@pytest.mark.parametrize("kind", ["funds", "quote", "order_post", "live"])
def test_narrow_route_guard_rejects_before_delegate_gate_or_debit(run, monkeypatch, kind):
    path, method, host = old.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.path, "GET", old.KIS_PAPER_BASE_URL
    if kind == "quote":
        path = "/uapi/overseas-price/v1/quotations/price-detail"
    elif kind == "order_post":
        path, method = "/uapi/overseas-stock/v1/trading/order", "POST"
    elif kind == "live":
        path, host = old.KIS_PAPER_TOKEN_PATH, "https://openapi.koreainvestment.com:9443"
        method = "POST"
    quote = None
    if kind == "quote":
        quote = build_kis_paper_preview_quote_request(
            config=old.load_kis_paper_config_from_environment(FAKE_ENV),
            access_token="synthetic-token",
            symbol="SPY",
            kind="price_detail",
        )
        old.validate_kis_paper_readonly_request(quote)

    def attack(client, **kwargs):
        headers = {
            "authorization": "Bearer synthetic-token",
            "appkey": FAKE_ENV["KIS_PAPER_APP_KEY"],
            "appsecret": FAKE_ENV["KIS_PAPER_APP_SECRET"],
            "tr_id": old.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id,
            "custtype": "P",
            "tr_cont": "",
        }
        request = old.KisHttpRequest(method, host + path, headers)
        if kind == "funds":
            request = replace(
                request,
                query={key: "SYN" for key in old.KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.query_keys},
            )
            old.validate_kis_paper_readonly_request(request)
        elif kind == "quote":
            request = quote
        return client._transport.request(request)

    monkeypatch.setattr(holdings.KisPaperStockReadOnlyClient, "stock_exit_account_snapshot", attack)
    transport, gate = ExitTransport(now=NOW), Gate()
    outcome = run(transport, token_gate=gate)
    assert outcome.status == "unavailable"
    assert outcome.reason_code in {"request_not_allowlisted", "paper_host_required"}
    assert transport.requests == [] and gate.claims == 0
    assert outcome.post_attempts == outcome.get_attempts == 0


def test_cli_default_is_inert_without_files_config_or_transport(monkeypatch, capsys):
    def denied(*args, **kwargs):
        pytest.fail("inert_cli_attempted_io")

    with monkeypatch.context() as isolated:
        isolated.setattr(holdings, "run_kis_paper_holdings", denied)
        isolated.setattr(builtins, "open", denied)
        isolated.setattr(io, "open", denied)
        isolated.setattr(Path, "mkdir", denied)
        assert holdings.main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "inert" and output["submit_capability"] is False


def test_cli_missing_named_environment_is_safe_unavailable(tmp_path, monkeypatch, capsys):
    environment = PaperEnvironment({})
    monkeypatch.setattr(
        holdings, "os", SimpleNamespace(environ=environment, fsync=os.fsync, replace=os.replace)
    )
    assert (
        holdings.main(
            [
                "--execute",
                "--repository-root",
                str(tmp_path / "repository"),
                "--artifact-root",
                str(tmp_path / "artifacts"),
                "--token-control-root",
                str(tmp_path / "control"),
                "--invocation-id",
                INVOCATION,
            ]
        )
        == 2
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "unavailable" and output["reason_code"] == "config_missing"
    assert output["position_count"] is output["open_order_count"] is None
    assert output["post_attempts"] == output["get_attempts"] == 0
    assert set(environment.reads) == set(old.KIS_PAPER_ENV_KEYS)


@pytest.mark.parametrize(
    "change", [{"position_count": True}, {"get_attempts": 41}, {"post_attempts": 2}]
)
def test_outcome_rejects_nonprimitive_or_out_of_cap_counts(change):
    outcome = holdings.KisPaperHoldingsOutcome(
        status="complete",
        reason_code=None,
        observed_at=NOW,
        completed_at=NOW,
        invocation_id=INVOCATION,
        position_count=1,
        open_order_count=0,
    )
    with pytest.raises(ValueError):
        replace(outcome, **change)
