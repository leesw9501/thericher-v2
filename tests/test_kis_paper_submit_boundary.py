from datetime import timedelta

import pytest

from test_kis_paper_canary import (
    NOW,
    FakeKisPaperCanaryTransport,
    _decision,
    _paper_environment,
    _paths,
    _submission_count,
)
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryStateStore,
    run_kis_paper_canary,
)


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
