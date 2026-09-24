from datetime import timedelta

import pytest

from test_kis_paper_canary import (
    NOW,
    FakeKisPaperCanaryTransport,
    _decision,
    _paper_environment,
    _paths,
    _sell_decision,
    _submission_count,
)
from thericher_v2.execution.kis_paper_canary import (
    KIS_PAPER_US_BUY_LIMIT_ORDER_PATH,
    KisPaperCanaryStateStore,
    inspect_kis_paper_buy_limit_response,
    run_kis_paper_canary,
)
from thericher_v2.execution.kis_readonly import KisHttpResponse
from thericher_v2.execution.paper_canary_lifecycle import read_paper_canary_lifecycle_fact


@pytest.mark.parametrize("delay_seconds", [299, 300, 301])
def test_permission_callback_expiry_does_not_record_a_never_sent_attempt(
    tmp_path, delay_seconds,
):
    transport = FakeKisPaperCanaryTransport()
    current = [NOW]
    state_path = tmp_path / "private" / "delayed-permission.json"
    checks = []

    def permitted(at):
        checks.append(at)
        current[0] += timedelta(seconds=delay_seconds)
        return True

    outcome = run_kis_paper_canary(
        decision=_decision(),
        run_id="delayed-permission",
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        clock=lambda: current[0],
        submit_permitted=permitted,
        **_paths(tmp_path),
    )
    state = KisPaperCanaryStateStore(state_path).read()
    assert checks == [NOW]
    if delay_seconds >= 300:
        assert outcome.phase == "intent_recorded"
        assert state.reason_code == "intent_expired"
        assert state.submission_started_at is None and state.broker_order_id is None
        assert _submission_count(transport) == 0
    else:
        assert outcome.phase == "submitted"
        assert state.submission_started_at == current[0]
        assert _submission_count(transport) == 1


@pytest.mark.parametrize(("payload", "category"), [
    ({}, "result_code_missing"),
    ({"output": {"ODNO": "SYNTHETIC-PRIVATE"}}, "result_code_missing"),
    ({"rt_cd": None}, "result_code_invalid"),
    ({"rt_cd": 0}, "result_code_invalid"),
    ({"rt_cd": 1}, "result_code_invalid"),
    ({"rt_cd": False}, "result_code_invalid"),
    ({"rt_cd": []}, "result_code_invalid"),
    ({"rt_cd": " 0"}, "result_code_invalid"),
    ({"rt_cd": "2"}, "result_code_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": "SYNTHETIC-PRIVATE"}},
     "rejection_with_order_reference"),
    ({"rt_cd": "1", "output": {"odno": "SYNTHETIC-PRIVATE"}},
     "rejection_with_order_reference"),
    ({"rt_cd": "1", "ODNO": "SYNTHETIC-PRIVATE"}, "rejection_with_order_reference"),
    ({"rt_cd": "1", "output": "SYNTHETIC-PRIVATE"}, "payload_invalid"),
    ({"rt_cd": "1"}, "provider_rejected"),
    ({"rt_cd": "1", "output": None}, "payload_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": None}}, "payload_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": False}}, "payload_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": 0}}, "payload_invalid"),
    ({"rt_cd": "1", "output": {"ODNO": ""}}, "provider_rejected"),
    ({"rt_cd": "0"}, "success_output_missing"),
    ({"rt_cd": "0", "output": {}}, "success_order_reference_missing"),
])
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_response_structure_survives_unknown_state_without_repost(
    tmp_path, payload, category, side,
):
    class Transport(FakeKisPaperCanaryTransport):
        def request(self, request):
            if request.method == "POST" and request.url.endswith(KIS_PAPER_US_BUY_LIMIT_ORDER_PATH):
                self.requests.append(request)
                return KisHttpResponse.from_payload(payload)
            return super().request(request)

    response = KisHttpResponse.from_payload(payload)
    assert inspect_kis_paper_buy_limit_response(response).category == category
    transport = Transport()
    paths = _paths(tmp_path)
    state_path = tmp_path / "private" / "structure-unknown.json"
    for _ in range(2):
        outcome = run_kis_paper_canary(
            decision=_decision() if side == "buy" else _sell_decision(),
            run_id="structure-unknown", environment=_paper_environment(),
            state_path=state_path, execute=True, cancel_after_submit=False,
            transport=transport, now=NOW, **paths,
        )
        assert outcome.phase == "outcome_unknown"
        assert outcome.submit_response_category == category
        state = KisPaperCanaryStateStore(state_path).read()
        assert state.submit_response_category == category and state.broker_order_id is None
        fact = read_paper_canary_lifecycle_fact(outcome.evidence_path)
        assert fact.submit_response_category == category
        assert fact.lifecycle_state == "outcome_unknown"
        assert "SYNTHETIC-PRIVATE" not in outcome.evidence_path.read_text()
        assert sum(
            request.method == "POST" and request.url.endswith(KIS_PAPER_US_BUY_LIMIT_ORDER_PATH)
            for request in transport.requests
        ) == 1
