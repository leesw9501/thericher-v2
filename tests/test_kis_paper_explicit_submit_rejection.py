from __future__ import annotations

import socket
import urllib.request
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_canary import (
    NOW,
    FakeKisPaperCanaryTransport,
    _decision,
    _paper_environment,
    _paths,
    _sell_decision,
)
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution.kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
    project_kis_paper_portfolio_budget,
)
from thericher_v2.execution.kis_readonly import KisHttpResponse, KisPaperReadOnlyError
from thericher_v2.execution.paper_canary_lifecycle import read_paper_canary_lifecycle_fact

_RAW_MESSAGE = "synthetic-secret-response-body"
_ORDER_REFERENCE = "SYNTHETIC-ORDER-REFERENCE"
_ORDER_IDS = {
    canary.KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID,
    canary.KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID,
}


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic rejection tests must not access the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(canary.UrllibKisPaperCanaryTransport, "request", forbidden)
    monkeypatch.setattr(canary.UrllibKisPaperCanaryTransport, "request_before_deadline", forbidden)
    original = canary.load_kis_paper_config_from_environment

    def synthetic_config(environment=None):
        assert environment == _paper_environment()
        return original(environment)

    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", synthetic_config)


class SubmitTransport(FakeKisPaperCanaryTransport):
    def __init__(self, response=None, *, failure=None, state_path=None):
        super().__init__()
        self.response, self.failure, self.state_path = response, failure, state_path

    def request(self, request):
        if request.headers.get("tr_id") in _ORDER_IDS:
            self.requests.append(request)
            if self.state_path is not None:
                state = canary.KisPaperCanaryStateStore(self.state_path).read()
                assert state.phase == "submission_started"
                assert state.submission_started_at == NOW
            if self.failure is not None:
                raise self.failure
            assert self.response is not None
            return self.response
        return super().request(request)


def _state_path(tmp_path):
    return tmp_path / "synthetic-private" / "explicit-rejection.json"


def _run(tmp_path, transport, *, side="buy", now=NOW):
    return canary.run_kis_paper_canary(
        decision=_decision() if side == "buy" else _sell_decision(),
        run_id="explicit-rejection",
        environment=_paper_environment(),
        state_path=_state_path(tmp_path),
        execution_control_path=tmp_path / "synthetic-controls.json",
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=now,
        **_paths(tmp_path),
    )


def _posts(transport):
    return sum(request.headers.get("tr_id") in _ORDER_IDS for request in transport.requests)


def _projection(state):
    basis = KisPaperPortfolioBudgetBasis("1" * 64, Decimal(10000), Decimal(1000), NOW)
    owner = KisPaperPortfolioOwnerBinding(
        "synthetic-owner",
        basis.account_ref,
        "QQQ",
        "NASD",
        (KisPaperPortfolioStateRef(state.intent.run_id, state.intent.fingerprint),),
    )
    return project_kis_paper_portfolio_budget(
        basis=basis,
        expected_basis_ref=basis.fingerprint,
        owners=(owner,),
        expected_owner_refs={owner.owner_ref: owner.fingerprint},
        states={state.intent.run_id: state},
        as_of=state.updated_at,
    )


def _assert_redacted(tmp_path):
    secrets = (
        _RAW_MESSAGE,
        _ORDER_REFERENCE,
        "test-access-token",
        _paper_environment()["KIS_PAPER_APP_KEY"],
        _paper_environment()["KIS_PAPER_APP_SECRET"],
        _paper_environment()["KIS_PAPER_ACCOUNT_NO"],
    )
    for path in tmp_path.rglob("*.json"):
        assert not path.is_symlink() and path.stat().st_nlink == 1
        text = path.read_text(encoding="utf-8")
        assert all(secret not in text for secret in secrets)


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize(
    "output",
    [None, {}, {"ODNO": ""}, {"odno": ""}],
    ids=[
        "absent-output",
        "empty-output",
        "empty-upper-order",
        "empty-lower-order",
    ],
)
def test_real_client_fresh_http_200_rejection_is_terminal_once(tmp_path, side, output):
    payload = {"rt_cd": "1", "msg_cd": "KIS1001", "msg1": _RAW_MESSAGE}
    if output is not None:
        payload["output"] = output
    response = KisHttpResponse.from_payload(payload)
    assert canary.inspect_kis_paper_buy_limit_response(response).category == "provider_rejected"
    transport = SubmitTransport(response, state_path=_state_path(tmp_path))
    for offset in (0, 1):
        outcome = _run(tmp_path, transport, side=side, now=NOW + timedelta(seconds=offset))
        state = canary.KisPaperCanaryStateStore(_state_path(tmp_path)).read()
        assert outcome.phase == state.phase == "rejected"
        assert outcome.reason_code == state.reason_code == "submit_rejected"
        assert state.submit_response_category == "provider_rejected"
        assert state.submit_upstream_code == "KIS1001"
        assert state.submission_started_at == NOW
        assert state.broker_order_id is state.submitted_at is state.cumulative_fill is None
        fact = read_paper_canary_lifecycle_fact(outcome.evidence_path)
        assert fact.lifecycle_state == "rejected"
        assert fact.submit_response_category == "provider_rejected"
        if side == "buy":
            assert _projection(state).reserved_buys == 0
        assert _posts(transport) == 1
        assert not any(
            request.headers.get("tr_id") == canary.KIS_PAPER_US_CANCEL_TR_ID
            for request in transport.requests
        )
    _assert_redacted(tmp_path)


@pytest.mark.parametrize(
    "code,expected",
    [
        (None, None),
        ("EGW00201", "EGW00201"),
        (True, None),
        (1, None),
        ("private body 123", None),
        ("KIS1001\n", None),
        ({"secret": _RAW_MESSAGE}, None),
    ],
)
def test_fresh_rejection_keeps_only_allowlisted_upstream_code(tmp_path, code, expected):
    response = KisHttpResponse.from_payload(
        {
            "rt_cd": "1",
            "msg_cd": code,
            "msg1": _RAW_MESSAGE,
        }
    )
    transport = SubmitTransport(response)
    outcome = _run(tmp_path, transport)
    state = canary.KisPaperCanaryStateStore(_state_path(tmp_path)).read()
    assert outcome.phase == state.phase == "rejected"
    assert outcome.submit_upstream_code == state.submit_upstream_code == expected
    assert _posts(transport) == 1
    _assert_redacted(tmp_path)


_AMBIGUOUS = [
    ({}, "result_code_missing"),
    ({"rt_cd": None}, "result_code_invalid"),
    ({"rt_cd": True}, "result_code_invalid"),
    ({"rt_cd": 1}, "result_code_invalid"),
    ({"rt_cd": 1.0}, "result_code_invalid"),
    ({"rt_cd": []}, "result_code_invalid"),
    ({"rt_cd": "2"}, "result_code_invalid"),
    ({"rt_cd": " 1"}, "result_code_invalid"),
    ({"rt_cd": "1 "}, "result_code_invalid"),
    ({"rt_cd": "1", "output": None}, "payload_invalid"),
    ({"rt_cd": "1", "output": []}, "payload_invalid"),
    ({"rt_cd": "1", "output": _RAW_MESSAGE}, "payload_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": None}}, "payload_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": True}}, "payload_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": 1}}, "payload_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": _ORDER_REFERENCE}}, "rejection_with_order_reference"),
    ({"rt_cd": "1", "output": {"odno": _ORDER_REFERENCE}}, "rejection_with_order_reference"),
    ({"rt_cd": "1", "ODNO": _ORDER_REFERENCE}, "rejection_with_order_reference"),
    ({"rt_cd": "1", "odno": _ORDER_REFERENCE}, "rejection_with_order_reference"),
    ({"rt_cd": "0"}, "success_output_missing"),
    ({"rt_cd": "0", "output": {}}, "success_order_reference_missing"),
]


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("payload,category", _AMBIGUOUS)
def test_ambiguous_result_or_order_reference_is_unknown_without_repost(
    tmp_path,
    side,
    payload,
    category,
):
    response = KisHttpResponse.from_payload(payload | {"msg1": _RAW_MESSAGE})
    assert canary.inspect_kis_paper_buy_limit_response(response).category == category
    transport = SubmitTransport(response)
    for offset in (0, 1):
        outcome = _run(tmp_path, transport, side=side, now=NOW + timedelta(seconds=offset))
        state = canary.KisPaperCanaryStateStore(_state_path(tmp_path)).read()
        assert outcome.phase == state.phase == "outcome_unknown"
        assert state.submit_response_category == category
        assert state.broker_order_id is state.cumulative_fill is None
        assert _posts(transport) == 1
        if side == "buy":
            assert _projection(state).reserved_buys == Decimal("500.25")
    _assert_redacted(tmp_path)


@pytest.mark.parametrize("status", [201, 204, 400, 401, 429, 500, 503])
def test_non_200_rejection_body_is_unknown_without_repost(tmp_path, status):
    response = KisHttpResponse.from_payload(
        {"rt_cd": "1", "msg_cd": "KIS1001", "msg1": _RAW_MESSAGE},
        status_code=status,
    )
    transport = SubmitTransport(response)
    for offset in (0, 1):
        outcome = _run(tmp_path, transport, now=NOW + timedelta(seconds=offset))
        assert outcome.phase == "outcome_unknown"
        assert outcome.submit_response_category == "http_non_200"
        assert _posts(transport) == 1
    _assert_redacted(tmp_path)


@pytest.mark.parametrize(
    "body",
    [
        b'{"rt_cd":',
        b"[]",
        b"null",
        b"\xff",
        b'{"rt_cd":"0","rt_cd":"1"}',
        b'{"rt_cd":"1","rt_cd":"1"}',
        b'{"rt_cd":"1","output":{"ODNO":"SYNTHETIC-ORDER-REFERENCE"},"output":{}}',
        b'{"rt_cd":"1","output":{"ODNO":"SYNTHETIC-ORDER-REFERENCE","ODNO":""}}',
        b'{"rt_cd":"1","ODNO":"SYNTHETIC-ORDER-REFERENCE","ODNO":""}',
        b'{"rt_cd":"1","output":{"odno":"SYNTHETIC-ORDER-REFERENCE","odno":""}}',
        b'{"rt_cd":"1","msg_cd":"KIS1001","msg_cd":"KIS1001"}',
        b'{"rt_cd":"1","extra":NaN}',
        b'{"rt_cd":"1","extra":Infinity}',
        b'{"rt_cd":"1","extra":-Infinity}',
        b'{"rt_cd":"1","output":{"extra":NaN}}',
    ],
    ids=[
        "truncated",
        "array-root",
        "null-root",
        "invalid-utf8",
        "duplicate-result-conflict",
        "duplicate-result-identical",
        "duplicate-output",
        "duplicate-nested-order",
        "duplicate-root-order",
        "duplicate-lower-order",
        "duplicate-message-code",
        "nan",
        "infinity",
        "negative-infinity",
        "nested-nan",
    ],
)
def test_malformed_or_nonunique_json_never_releases_buy_reservation(tmp_path, body):
    transport = SubmitTransport(KisHttpResponse(200, {}, body))
    for offset in (0, 1):
        outcome = _run(tmp_path, transport, now=NOW + timedelta(seconds=offset))
        state = canary.KisPaperCanaryStateStore(_state_path(tmp_path)).read()
        assert outcome.phase == state.phase == "outcome_unknown"
        assert state.submit_response_category == "payload_invalid"
        assert _projection(state).reserved_buys == Decimal("500.25")
        assert _posts(transport) == 1
    _assert_redacted(tmp_path)


@pytest.mark.parametrize(
    "failure",
    [
        canary.KisPaperCanaryError("transport_failure"),
        KisPaperReadOnlyError("transport_failure"),
        canary.KisPaperCanaryError(
            "submit_kis_rejected",
            upstream_code="KIS1001",
            submit_response_category="provider_rejected",
        ),
    ],
    ids=["transport-failure", "readonly-failure", "generic-rejection-category"],
)
def test_untyped_failure_is_unknown_even_with_rejection_category(tmp_path, failure):
    transport = SubmitTransport(failure=failure)
    for offset in (0, 1):
        outcome = _run(tmp_path, transport, now=NOW + timedelta(seconds=offset))
        state = canary.KisPaperCanaryStateStore(_state_path(tmp_path)).read()
        assert outcome.phase == state.phase == "outcome_unknown"
        assert _projection(state).reserved_buys == Decimal("500.25")
        assert _posts(transport) == 1
    _assert_redacted(tmp_path)


@pytest.mark.parametrize(
    "body",
    [
        b'{"rt_cd":"1","rt_cd":"0","output":{"ODNO":"SYNTHETIC-ORDER-REFERENCE"}}',
        b'{"rt_cd":"0","output":{},"output":{"ODNO":"SYNTHETIC-ORDER-REFERENCE"}}',
        b'{"rt_cd":"0","output":{"ODNO":"","ODNO":"SYNTHETIC-ORDER-REFERENCE"}}',
        b'{"rt_cd":"0","output":{"ODNO":"SYNTHETIC-ORDER-REFERENCE"},"extra":NaN}',
    ],
    ids=["duplicate-result-to-ack", "duplicate-output-to-ack", "duplicate-order-to-ack", "nan-ack"],
)
def test_malformed_ack_shape_cannot_bypass_unknown_disposition(tmp_path, body):
    transport = SubmitTransport(KisHttpResponse(200, {}, body))
    outcome = _run(tmp_path, transport)
    state = canary.KisPaperCanaryStateStore(_state_path(tmp_path)).read()
    assert outcome.phase == state.phase == "outcome_unknown"
    assert state.broker_order_id is None
    assert _projection(state).reserved_buys == Decimal("500.25")
    assert _posts(transport) == 1
    _assert_redacted(tmp_path)


@pytest.mark.parametrize("read_only", [False, True])
def test_legacy_unknown_rejection_category_cannot_become_terminal_on_readback(
    tmp_path,
    read_only,
):
    store = canary.KisPaperCanaryStateStore(_state_path(tmp_path))
    intent = canary.KisPaperCanaryIntent.from_decision(_decision(), run_id="explicit-rejection")
    store.record_intent(intent, cancel_after_submit=False, now=NOW)
    store.transition(
        intent,
        expected=frozenset({"intent_recorded"}),
        phase="submission_started",
        reason_code="preview",
        now=NOW,
        submission_started_at=NOW,
    )
    original = store.transition(
        intent,
        expected=frozenset({"submission_started"}),
        phase="outcome_unknown",
        reason_code="submit_kis_rejected",
        now=NOW,
        submit_upstream_code="KIS1001",
        submit_response_category="provider_rejected",
    )
    raw = _state_path(tmp_path).read_bytes()
    assert store.read() == original and _state_path(tmp_path).read_bytes() == raw
    transport = SubmitTransport(KisHttpResponse.from_payload({"rt_cd": "1"}))
    if read_only:
        outcome = canary.reconcile_kis_paper_canary_unknown_run(
            run_id=intent.run_id,
            environment=_paper_environment(),
            state_path=_state_path(tmp_path),
            execution_control_path=tmp_path / "synthetic-controls.json",
            transport=transport,
            now=NOW + timedelta(seconds=1),
            **_paths(tmp_path),
        )
    else:
        outcome = _run(tmp_path, transport, now=NOW + timedelta(seconds=1))
    state = store.read()
    assert outcome.phase == state.phase == "outcome_unknown"
    assert state.submit_response_category == "provider_rejected"
    assert state.submit_upstream_code == "KIS1001"
    assert state.intent == original.intent and state.submission_started_at == NOW
    assert state.broker_order_id is state.submitted_at is state.cumulative_fill is None
    assert set(state.to_dict()) == set(original.to_dict())
    assert _projection(state).reserved_buys == Decimal("500.25")
    assert _posts(transport) == 0
    assert not any(
        request.method == "POST" and request.url.endswith(canary.KIS_PAPER_US_BUY_LIMIT_ORDER_PATH)
        for request in transport.requests
    )
    _assert_redacted(tmp_path)


def test_explicit_rejection_exception_has_fixed_code_and_category():
    error = canary.KisPaperSubmitRejected(upstream_code="KIS1001")
    assert isinstance(error, canary.KisPaperCanaryError)
    assert error.code == "submit_kis_rejected"
    assert error.submit_response_category == "provider_rejected"
    assert error.upstream_code == "KIS1001"
    with pytest.raises(ValueError):
        canary.KisPaperSubmitRejected(upstream_code=_RAW_MESSAGE)
    with pytest.raises(TypeError):
        canary.KisPaperSubmitRejected(code="transport_failure")
