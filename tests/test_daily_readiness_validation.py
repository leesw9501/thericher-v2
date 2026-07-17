from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import EmergencyState, PositionSnapshot, RiskLimits
from thericher_v2.execution import (
    AccountSnapshot,
    BrokerOrderRequest,
    InMemoryBrokerTransport,
    OpenOrderSnapshot,
    ReconciliationResult,
    evaluate_pre_submit_risk,
)


def test_full_long_exit_is_not_misclassified_by_higher_sell_limit(tmp_path) -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    request = BrokerOrderRequest(
        client_order_id="full-long-exit",
        symbol="AAPL",
        market="US",
        side="sell",
        quantity=Decimal("4"),
        limit_price=Decimal("110"),
        decision_id="reduce-long",
        created_at=now,
    )
    transport = InMemoryBrokerTransport(state_path=tmp_path / "broker-state.json")
    transport.record_intent(request)

    decision = evaluate_pre_submit_risk(
        request=request,
        transport=transport,
        risk_limits=RiskLimits(Decimal("1000"), Decimal("100"), 3, 2),
        account=AccountSnapshot(
            "USD",
            Decimal("0"),
            Decimal("400"),
            Decimal("400"),
            now,
        ),
        buying_power=None,
        open_orders=OpenOrderSnapshot((), now),
        reconciliation=ReconciliationResult(now, True),
        emergency_state=EmergencyState(False, False, "clear", now),
        reference_price=Decimal("100"),
        position=PositionSnapshot(
            symbol="AAPL",
            market="US",
            quantity=Decimal("4"),
            average_price=Decimal("100"),
            market_price=Decimal("95"),
            captured_at=now,
        ),
        realized_daily_pnl=Decimal("0"),
        orders_today=0,
        evaluated_at=now,
        max_evidence_age=timedelta(minutes=1),
    )

    assert decision.allowed is True
    assert decision.projected_position_notional == Decimal("0")
