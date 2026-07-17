from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from thericher_v2.contracts import EmergencyState, PositionSnapshot, RiskLimits
from thericher_v2.execution import (
    BROKER_DISABLED_SOURCE,
    BROKER_FAKE_SOURCE,
    LOCAL_PAPER_SOURCE,
    AccountSnapshot,
    BrokerOrderRequest,
    BuyingPowerSnapshot,
    InMemoryBrokerTransport,
    OpenOrderSnapshot,
    ReconciliationResult,
    evaluate_pre_submit_risk,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _position(
    *,
    symbol: str = "AAPL",
    market: str = "US",
    quantity: str = "1",
    average_price: str = "100",
    market_price: str = "100",
    captured_at: datetime = NOW,
) -> PositionSnapshot:
    return PositionSnapshot(
        symbol=symbol,
        market=market,
        quantity=Decimal(quantity),
        average_price=Decimal(average_price),
        market_price=Decimal(market_price),
        captured_at=captured_at,
    )


def test_allows_bounded_durable_request_without_submitting(tmp_path) -> None:
    inputs = _inputs(tmp_path)

    decision = evaluate_pre_submit_risk(**inputs)

    assert decision.allowed is True
    assert decision.reasons == ()
    assert decision.notional == Decimal("440")
    assert decision.projected_position_notional == Decimal("550")
    transport = inputs["transport"]
    request = inputs["request"]
    assert transport.order_status(request.client_order_id).status == "recorded"
    assert transport.export_state()["acks"] == []


def test_full_sell_exit_uses_quantity_instead_of_conflicting_notional_evidence(
    tmp_path,
) -> None:
    request = replace(_request("sell-reduction"), side="sell")
    position = _position(quantity="4", average_price="105", market_price="95")
    inputs = _inputs(tmp_path, request=request, position=position)

    decision = _evaluate(
        inputs,
        account=replace(inputs["account"], settled_cash=Decimal("0")),
        buying_power=None,
    )

    assert decision.allowed is True
    assert decision.reasons == ()
    assert position.market_value < request.quantity * inputs["reference_price"]
    assert decision.notional == Decimal("400")
    assert decision.projected_position_notional == Decimal("0")
    assert inputs["transport"].order_status(request.client_order_id).status == "recorded"
    assert inputs["transport"].export_state()["acks"] == []


def test_oversized_sell_uses_quantity_even_when_market_value_looks_sufficient(
    tmp_path,
) -> None:
    request = replace(_request("naked-sell"), side="sell")
    position = _position(quantity="3", market_price="150")
    inputs = _inputs(tmp_path, request=request, position=position)

    decision = _evaluate(
        inputs,
        buying_power=None,
    )

    assert decision.allowed is False
    assert decision.reasons == ("sell_exceeds_long_position",)
    assert position.market_value > request.quantity * inputs["reference_price"]
    assert decision.notional == Decimal("600")
    assert decision.projected_position_notional is None


def test_partial_sell_reduction_values_remaining_quantity_consistently(tmp_path) -> None:
    request = replace(
        _request("partial-reduction"),
        side="sell",
        quantity=Decimal("2"),
    )
    inputs = _inputs(
        tmp_path,
        request=request,
        position=_position(quantity="4", average_price="105", market_price="95"),
    )

    decision = _evaluate(inputs, buying_power=None)

    assert decision.allowed is True
    assert decision.notional == Decimal("200")
    assert decision.projected_position_notional == Decimal("200")


def test_true_reduction_bypasses_entry_caps_but_remains_a_pure_decision(tmp_path) -> None:
    request = replace(
        _request("capped-reduction"),
        side="sell",
        quantity=Decimal("1"),
    )
    inputs = _inputs(
        tmp_path,
        request=request,
        position=_position(quantity="10"),
    )
    status = inputs["transport"].order_status(request.client_order_id)
    open_orders = OpenOrderSnapshot(
        (
            replace(status, client_order_id="existing-1"),
            replace(status, client_order_id="existing-2"),
        ),
        NOW,
    )

    decision = _evaluate(
        inputs,
        risk_limits=RiskLimits(Decimal("500"), Decimal("100"), 3, 2),
        account=replace(inputs["account"], settled_cash=Decimal("0")),
        buying_power=None,
        open_orders=open_orders,
        emergency_state=EmergencyState(True, False, "stop_new_entries", NOW),
        realized_daily_pnl=Decimal("-100"),
        orders_today=3,
    )

    assert decision.allowed is True
    assert decision.reasons == ()
    assert decision.projected_position_notional == Decimal("900")
    assert inputs["transport"].export_state()["acks"] == []


def test_true_reduction_still_rejects_invalid_counts_and_pnl(tmp_path) -> None:
    request = replace(_request("invalid-reduction-evidence"), side="sell")
    inputs = _inputs(
        tmp_path,
        request=request,
        position=_position(quantity="4"),
    )

    invalid_count = _evaluate(inputs, buying_power=None, orders_today=-1)
    invalid_pnl = _evaluate(
        inputs,
        buying_power=None,
        realized_daily_pnl=Decimal("NaN"),
    )

    assert invalid_count.allowed is False
    assert "orders_today_invalid" in invalid_count.reasons
    assert invalid_pnl.allowed is False
    assert "realized_daily_pnl_invalid" in invalid_pnl.reasons


def test_buy_still_adds_exposure_and_requires_buying_power(tmp_path) -> None:
    inputs = _inputs(tmp_path)

    decision = _evaluate(
        inputs,
        buying_power=replace(
            inputs["buying_power"],
            available_cash=Decimal("400"),
            max_order_notional=Decimal("400"),
        ),
    )

    assert decision.allowed is False
    assert decision.reasons == ("buying_power_exceeded",)
    assert decision.notional == Decimal("440")
    assert decision.projected_position_notional == Decimal("550")


def test_buy_uses_market_price_in_conservative_notional_and_position_limit(
    tmp_path,
) -> None:
    inputs = _inputs(
        tmp_path,
        position=_position(market_price="120"),
        risk_limits=RiskLimits(Decimal("550"), Decimal("100"), 3, 2),
    )

    decision = _evaluate(inputs)

    assert decision.allowed is False
    assert decision.notional == Decimal("480")
    assert decision.projected_position_notional == Decimal("600")
    assert decision.reasons == ("max_position_notional_exceeded",)


@pytest.mark.parametrize(
    ("field_name", "reason"),
    (
        ("risk_limits", "risk_limits_missing"),
        ("account", "account_missing"),
        ("buying_power", "buying_power_missing"),
        ("open_orders", "open_orders_missing"),
        ("reconciliation", "reconciliation_missing"),
        ("emergency_state", "emergency_state_missing"),
        ("reference_price", "reference_price_missing"),
        ("position", "position_missing"),
        ("realized_daily_pnl", "realized_daily_pnl_missing"),
        ("orders_today", "orders_today_missing"),
        ("max_evidence_age", "evidence_age_invalid"),
    ),
)
def test_missing_evidence_fails_closed(tmp_path, field_name: str, reason: str) -> None:
    inputs = _inputs(tmp_path)
    inputs[field_name] = None

    decision = evaluate_pre_submit_risk(**inputs)

    assert decision.allowed is False
    assert reason in decision.reasons


def test_requires_exact_request_to_be_durably_recorded(tmp_path) -> None:
    inputs = _inputs(tmp_path)
    inputs["request"] = replace(inputs["request"], quantity=Decimal("5"))
    mismatch = evaluate_pre_submit_risk(**inputs)

    volatile = InMemoryBrokerTransport()
    request = _request("volatile")
    volatile.record_intent(request)
    inputs = _inputs(tmp_path / "second", transport=volatile, request=request)
    not_persisted = evaluate_pre_submit_risk(**inputs)

    assert mismatch.allowed is False
    assert mismatch.reasons[0] == "intent_not_durable"
    assert not_persisted.allowed is False
    assert not_persisted.reasons[0] == "intent_not_durable"


def test_snapshot_time_boundaries_fail_closed(tmp_path) -> None:
    inputs = _inputs(tmp_path)
    non_utc_position = replace(inputs["position"])
    object.__setattr__(
        non_utc_position,
        "captured_at",
        NOW.astimezone(timezone(timedelta(hours=9))),
    )

    non_utc = _evaluate(inputs, position=non_utc_position)
    stale = _evaluate(
        inputs,
        position=replace(inputs["position"], captured_at=NOW - timedelta(minutes=2)),
    )
    future = _evaluate(
        inputs,
        position=replace(inputs["position"], captured_at=NOW + timedelta(seconds=1)),
    )
    bad_clock = _evaluate(inputs, evaluated_at=NOW.astimezone(timezone(timedelta(hours=9))))

    assert "evidence_not_utc" in non_utc.reasons
    assert "evidence_stale" in stale.reasons
    assert "evidence_from_future" in future.reasons
    assert "evaluated_at_not_utc" in bad_clock.reasons
    assert not any((non_utc.allowed, stale.allowed, future.allowed, bad_clock.allowed))


@pytest.mark.parametrize(
    ("position", "reason"),
    (
        (_position(symbol="MSFT", quantity="4"), "position_mismatch"),
        (_position(market="KR", quantity="4"), "position_mismatch"),
        (
            _position(quantity="4", captured_at=NOW - timedelta(minutes=2)),
            "evidence_stale",
        ),
        (
            _position(quantity="4", captured_at=NOW + timedelta(seconds=1)),
            "evidence_from_future",
        ),
    ),
    ids=("symbol", "market", "stale", "future"),
)
def test_sell_reduction_requires_fresh_matching_position(
    tmp_path,
    position,
    reason: str,
) -> None:
    request = replace(_request("position-evidence"), side="sell")
    inputs = _inputs(tmp_path, request=request, position=position)

    decision = _evaluate(inputs, buying_power=None)

    assert decision.allowed is False
    assert reason in decision.reasons


@pytest.mark.parametrize(
    ("position", "reason"),
    (
        (_position(quantity="-1"), "position_quantity_invalid"),
        (
            _position(quantity="0", average_price="100", market_price="100"),
            "position_price_invalid",
        ),
        (_position(quantity="1", average_price="0", market_price="0"), "position_price_invalid"),
    ),
    ids=("negative-quantity", "zero-quantity-with-prices", "long-with-zero-prices"),
)
def test_invalid_long_only_position_evidence_fails_closed(
    tmp_path,
    position,
    reason: str,
) -> None:
    decision = _evaluate(_inputs(tmp_path), position=position)

    assert decision.allowed is False
    assert reason in decision.reasons


def test_currency_reconciliation_emergency_and_open_order_conflicts_fail(tmp_path) -> None:
    inputs = _inputs(tmp_path)
    unsafe_reconciliation = ReconciliationResult(
        reconciled_at=NOW,
        safe_to_submit=False,
        duplicates=("client:duplicate",),
        mismatches=("open_order:mismatch",),
        stale_snapshots=("account",),
        outcome_unknown_ids=("unknown",),
    )
    status = inputs["transport"].order_status(inputs["request"].client_order_id)
    conflicting_orders = OpenOrderSnapshot(
        orders=(status, status),
        captured_at=NOW,
        complete=False,
    )

    currency = _evaluate(
        inputs,
        buying_power=replace(inputs["buying_power"], currency="KRW"),
    )
    reconciliation = _evaluate(inputs, reconciliation=unsafe_reconciliation)
    emergency = _evaluate(
        inputs,
        emergency_state=EmergencyState(True, False, "test_stop", NOW),
    )
    open_order = _evaluate(inputs, open_orders=conflicting_orders)

    assert "currency_mismatch" in currency.reasons
    assert {
        "reconciliation_unsafe",
        "reconciliation_duplicate",
        "reconciliation_mismatch",
        "reconciliation_unknown",
        "reconciliation_stale",
    } <= set(reconciliation.reasons)
    assert "emergency_stop_active" in emergency.reasons
    assert "open_orders_incomplete" in open_order.reasons
    assert "open_order_conflict" in open_order.reasons


def test_true_reduction_still_requires_account_and_order_state_integrity(tmp_path) -> None:
    request = replace(_request("reduction-integrity"), side="sell")
    inputs = _inputs(
        tmp_path,
        request=request,
        position=_position(quantity="4"),
    )
    status = inputs["transport"].order_status(request.client_order_id)
    incomplete = OpenOrderSnapshot((status,), NOW, complete=False)
    unsafe = ReconciliationResult(
        reconciled_at=NOW,
        safe_to_submit=False,
        outcome_unknown_ids=(request.client_order_id,),
    )

    missing_account = _evaluate(inputs, account=None, buying_power=None)
    stale_account = _evaluate(
        inputs,
        account=replace(inputs["account"], captured_at=NOW - timedelta(minutes=2)),
        buying_power=None,
    )
    open_order = _evaluate(inputs, open_orders=incomplete, buying_power=None)
    reconciliation = _evaluate(inputs, reconciliation=unsafe, buying_power=None)

    assert "account_missing" in missing_account.reasons
    assert "evidence_stale" in stale_account.reasons
    assert {"open_orders_incomplete", "open_order_conflict"} <= set(open_order.reasons)
    assert {"reconciliation_unsafe", "reconciliation_unknown"} <= set(reconciliation.reasons)
    assert not any(
        (
            missing_account.allowed,
            stale_account.allowed,
            open_order.allowed,
            reconciliation.allowed,
        )
    )


def test_counts_buying_power_position_and_daily_loss_limits_fail_closed(tmp_path) -> None:
    inputs = _inputs(tmp_path)
    status = inputs["transport"].order_status(inputs["request"].client_order_id)
    two_open_orders = OpenOrderSnapshot(
        orders=(
            replace(status, client_order_id="open-1"),
            replace(status, client_order_id="open-2"),
        ),
        captured_at=NOW,
    )

    orders = _evaluate(inputs, orders_today=3)
    open_count = _evaluate(inputs, open_orders=two_open_orders)
    buying_power = _evaluate(
        inputs,
        buying_power=replace(inputs["buying_power"], available_cash=Decimal("400")),
    )
    position = _evaluate(inputs, position=_position(quantity="7"))
    daily_loss = _evaluate(inputs, realized_daily_pnl=Decimal("-100"))

    assert "max_orders_per_day_exceeded" in orders.reasons
    assert "max_open_orders_exceeded" in open_count.reasons
    assert "buying_power_exceeded" in buying_power.reasons
    assert "max_position_notional_exceeded" in position.reasons
    assert "max_daily_loss_exceeded" in daily_loss.reasons


def test_persisted_restart_remains_eligible_for_same_pure_decision(tmp_path) -> None:
    inputs = _inputs(tmp_path)
    state_path = tmp_path / "broker-state.json"
    restored = InMemoryBrokerTransport.from_state(
        json.loads(state_path.read_text(encoding="utf-8")),
        state_path=state_path,
    )

    decision = _evaluate(inputs, transport=restored)

    assert decision.allowed is True
    assert restored.order_status(inputs["request"].client_order_id).status == "recorded"
    assert restored.export_state()["acks"] == []


def test_risk_decision_needs_no_network_credentials_or_broker_source(monkeypatch, tmp_path) -> None:
    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pre-submit risk must remain offline")

    monkeypatch.setattr(socket, "create_connection", fail_io)
    monkeypatch.setattr(urllib.request, "urlopen", fail_io)
    monkeypatch.setattr(os, "getenv", fail_io)

    decision = evaluate_pre_submit_risk(**_inputs(tmp_path))

    assert decision.allowed is True
    assert len({BROKER_DISABLED_SOURCE, BROKER_FAKE_SOURCE, LOCAL_PAPER_SOURCE}) == 3


def _inputs(tmp_path, **overrides):
    request = overrides.pop("request", _request())
    transport = overrides.pop("transport", None)
    if transport is None:
        transport = InMemoryBrokerTransport(state_path=tmp_path / "broker-state.json")
        transport.record_intent(request)
    inputs = {
        "request": request,
        "transport": transport,
        "risk_limits": RiskLimits(Decimal("1000"), Decimal("100"), 3, 2),
        "account": AccountSnapshot(
            "USD",
            Decimal("1000"),
            Decimal("1000"),
            Decimal("100"),
            NOW,
        ),
        "buying_power": BuyingPowerSnapshot(
            "USD",
            Decimal("1000"),
            Decimal("1000"),
            NOW,
        ),
        "open_orders": OpenOrderSnapshot((), NOW),
        "reconciliation": ReconciliationResult(NOW, True),
        "emergency_state": EmergencyState(False, False, "clear", NOW),
        "reference_price": Decimal("100"),
        "position": _position(),
        "realized_daily_pnl": Decimal("0"),
        "orders_today": 0,
        "evaluated_at": NOW,
        "max_evidence_age": timedelta(minutes=1),
    }
    inputs.update(overrides)
    return inputs


def _evaluate(inputs, **overrides):
    return evaluate_pre_submit_risk(**{**inputs, **overrides})


def _request(client_order_id: str = "risk-order-1") -> BrokerOrderRequest:
    return BrokerOrderRequest(
        client_order_id=client_order_id,
        symbol="AAPL",
        market="US",
        side="buy",
        quantity=Decimal("4"),
        limit_price=Decimal("110"),
        decision_id="risk-decision-1",
        created_at=NOW,
    )
