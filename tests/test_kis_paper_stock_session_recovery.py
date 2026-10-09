"""Synthetic exact-request routing; no private state, account reads or wire."""

from __future__ import annotations

import copy
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_UP, Decimal, Inexact, Rounded, localcontext
from pathlib import Path

import pytest

from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_portfolio_budget as portfolio
from thericher_v2.execution import kis_paper_stock_session_recovery as router
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_paper_stock_execute import KisPaperStockExecutionBinding
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.execution.kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
    KisPaperStockPreviewReads,
)
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)

D = Decimal
PIN = "sha256:" + "a" * 64
ACCOUNT = "b" * 64
OPEN = datetime(2026, 10, 9, 13, 30, tzinfo=UTC)
CLOSE = OPEN.replace(hour=20, minute=0)


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pure recovery planner must not perform I/O or broker operations")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(canary.KisPaperCanaryStateStore, "read", forbidden)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", forbidden)
    for method in ("reconcile", "submit_limit", "cancel_order"):
        monkeypatch.setattr(canary.KisPaperCanaryClient, method, forbidden)


def request(*, symbol="AAPL", side="buy", opened=OPEN, closed=CLOSE, tag="c", created=None):
    at = opened + timedelta(minutes=1) if created is None else created
    instrument = KisPaperStockInstrument(symbol, "ref:" + tag * 64)
    owner = budget._stock_owner_id(instrument.binding_ref)
    intent = canary.KisPaperCanaryIntent(
        "bk-" + tag * 64,
        "stock-" + tag * 64,
        "stock-" + tag * 64,
        symbol,
        "NASD",
        D(4),
        D(100),
        at,
        at + timedelta(minutes=5),
        side=side,
        price_contract_ref=PIN,
    )
    seed = canary.KisPaperCanaryState(intent, "intent_recorded", at, "preview")
    proof = KisPaperStockExecutionBinding(
        state_root=Path("C:/synthetic-only-unused-state"),
        instrument=instrument,
        account_ref=ACCOUNT,
        basis_ref=PIN,
        owner_refs=((owner, PIN),),
        binding_ref=PIN,
        request_id="synthetic-" + tag,
        parent_binding_ref=PIN,
        input_ref=PIN,
        plan_ref=PIN,
        run_id=intent.run_id,
        intent_ref=intent.fingerprint,
        side=side,
    )
    return dict(
        proof=proof,
        seed=seed,
        state=seed,
        session_open=opened,
        session_close=closed,
        as_of=at + timedelta(seconds=10),
    )


def observed(
    call,
    *,
    filled="0",
    outstanding="4",
    phase="submitted",
    owned="0",
    broker_owned=None,
    open_order=True,
    cancellation=False,
):
    intent, at = call["seed"].intent, call["as_of"]
    order_at = intent.created_at + timedelta(seconds=1)
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id="123",
            order_at=order_at,
            symbol=intent.symbol,
            exchange="NASD",
            side=intent.side,
            quantity=intent.quantity,
        ),
        intent.quantity,
        D(filled),
        D(filled) * intent.limit_price,
        at,
        D(outstanding),
    )
    state = replace(
        call["seed"],
        phase=phase,
        updated_at=at,
        reason_code="reconciliation_clean",
        submission_started_at=order_at,
        submitted_at=order_at,
        broker_order_id="123",
        cumulative_fill=fill,
        fill_observation_status="available",
        fill_observed_at=at,
    )
    orders = (
        ()
        if not open_order
        else (
            KisPaperOpenOrder(
                canary._redacted_open_order_reference("123"),
                intent.symbol,
                "NASD",
                "USD",
                intent.side,
                intent.quantity,
                D(filled),
                D(outstanding),
                intent.limit_price,
                at,
            ),
        )
    )
    quantity = D(owned if broker_owned is None else broker_owned)
    positions = (
        ()
        if quantity == 0
        else (KisPaperPosition(intent.symbol, "NASD", "USD", quantity, D(100), D(100), at),)
    )
    snapshot = KisPaperReadOnlySnapshot(
        KisPaperAccountIdentity("****0000-**", at),
        KisPaperCashSnapshot("USD", D(0), at),
        KisPaperOrderableFundsSnapshot("USD", D(0), "NASD", intent.symbol, D(100), at),
        positions,
        KisPaperOpenOrdersSnapshot(orders, at),
        at,
    )
    reads = KisPaperStockPreviewReads(
        ACCOUNT,
        call["proof"].instrument,
        snapshot,
        None,
        D(0),
        snapshot.cash,
        snapshot.orderable_funds,
        at,
        at,
        0.0,
    )
    observation = KisPaperExecutionObservation(
        2 if cancellation else 1,
        True,
        "available",
        fill,
        at,
        cancellation,
    )
    reconciliation = canary.KisPaperCanaryReconciliation(
        snapshot,
        "available",
        1,
        open_order,
        True,
        "unresolved" if open_order else "clean",
        execution=observation,
    )
    row = portfolio.KisPaperPortfolioStock(
        budget._stock_owner_id(call["proof"].instrument.binding_ref),
        intent.symbol,
        "NASD",
        D(owned),
        D(owned) * D(100),
        D(400),
    )
    projection = portfolio.KisPaperPortfolioBudgetProjection(
        D(10000),
        D(1000),
        (row,),
        (row,),
        row.entry_cost,
        D(400),
        D(600),
        D(1000),
        D(600),
    )
    return call | dict(
        state=state, reads=reads, reconciliation=reconciliation, projection=projection
    )


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_new_seed_then_exact_expiry_without_renewal(side):
    call = request(side=side)
    before = copy.deepcopy(call)
    result = router.plan_stock_session_recovery(**call)
    assert result.action == "submit_exact_seed" and result.intent == call["seed"].intent
    assert result.original_valid_until == before["seed"].intent.valid_until
    with pytest.raises(FrozenInstanceError):
        result.action = "terminal_owned_flat"
    expired = router.plan_stock_session_recovery(**(call | {"as_of": result.original_valid_until}))
    assert expired.action == "expired_unsubmitted" and expired.outstanding_quantity is None
    assert expired.safe_payload()["reservation_effect"] == "unchanged" and call == before


def test_two_sessions_and_different_symbols_never_adopt_or_reset_old_request():
    first = request()
    second_open = OPEN + timedelta(days=3)
    second = request(
        symbol="MSFT", opened=second_open, closed=second_open.replace(hour=17, minute=0), tag="d"
    )
    assert router.plan_stock_session_recovery(**second).intent.symbol == "MSFT"
    old = router.plan_stock_session_recovery(**(first | {"as_of": second["as_of"]}))
    assert old.action == "expired_unsubmitted" and old.intent == first["seed"].intent
    assert old.request_id != second["proof"].request_id
    with pytest.raises(ValueError, match="original_session_mismatch"):
        router.plan_stock_session_recovery(
            **(first | {"session_open": second_open, "session_close": second["session_close"]})
        )


def test_preopen_awaits_original_window_and_early_close_is_not_extended():
    call = request(created=OPEN - timedelta(minutes=1))
    call["as_of"] = OPEN - timedelta(seconds=30)
    assert router.plan_stock_session_recovery(**call).action == "await_original_session"
    with pytest.raises(ValueError, match="original_session_mismatch"):
        router.plan_stock_session_recovery(
            **(call | {"session_close": OPEN + timedelta(minutes=1)})
        )


@pytest.mark.parametrize("phase", ["submission_started", "outcome_unknown", "cancel_started"])
@pytest.mark.parametrize("late", [False, True])
def test_unknown_attempt_never_submits_or_cancels_and_preserves_unknown_quantity(phase, late):
    call = request()
    at = call["seed"].intent.created_at + timedelta(seconds=1)
    call["state"] = replace(
        call["seed"],
        phase=phase,
        updated_at=at,
        submission_started_at=at,
        reason_code="submit_transport_unknown",
    )
    if late:
        call["as_of"] = CLOSE + timedelta(days=1)
    result = router.plan_stock_session_recovery(**call)
    assert result.action == "reconcile_unknown"
    assert result.outstanding_quantity is result.retained_fill_quantity is None
    assert result.remaining_owned_exit_quantity is None


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_attempted_exact_positive_open_order_cancels_at_original_expiry(side):
    call = request(side=side)
    call["as_of"] = call["seed"].intent.valid_until
    call = observed(call, filled="1", outstanding="3", owned="1")
    result = router.plan_stock_session_recovery(**call)
    assert result.action == "cancel_exact_expired" and result.outstanding_quantity == D(3)
    assert result.retained_fill_quantity == D(1) and not call["state"].cancel_after_submit
    assert result.remaining_owned_exit_quantity is None
    inside = request(side=side)
    assert router.plan_stock_session_recovery(**observed(inside)).action == "reconcile_open"


def test_expired_open_requires_current_identity_history_not_just_an_order_id():
    call = request()
    call["as_of"] = call["seed"].intent.valid_until
    call = observed(call)
    call["reconciliation"] = replace(call["reconciliation"], execution=None)
    assert router.plan_stock_session_recovery(**call).action == "reconcile_open"
    call["reconciliation"] = None
    assert router.plan_stock_session_recovery(**call).action == "reconcile_open"


@pytest.mark.parametrize("change", ["limit_price", "side", "symbol", "requested_quantity"])
def test_foreign_open_identity_cannot_be_cancelled(change):
    call = request()
    call["as_of"] = call["seed"].intent.valid_until
    call = observed(call)
    order = call["reads"].snapshot.open_orders.orders[0]
    changes = dict(
        limit_price=D(99),
        side="sell",
        symbol="MSFT",
        requested_quantity=D(5),
        remaining_quantity=D(5),
    )
    changed = {change: changes[change]}
    if change == "requested_quantity":
        changed["remaining_quantity"] = D(5)
    snapshot = replace(
        call["reads"].snapshot,
        open_orders=replace(
            call["reads"].snapshot.open_orders, orders=(replace(order, **changed),)
        ),
    )
    call["reads"] = replace(call["reads"], snapshot=snapshot)
    with pytest.raises(ValueError, match="open_identity_mismatch"):
        router.plan_stock_session_recovery(**call)


@pytest.mark.parametrize("side,owned", [("buy", "4"), ("sell", "0")])
def test_terminal_fill_requires_complete_broker_owned_join(side, owned):
    call = observed(request(side=side), filled="4", outstanding="0", owned=owned, open_order=False)
    expected = "remaining_owned_exit" if D(owned) else "terminal_owned_flat"
    result = router.plan_stock_session_recovery(**call)
    assert result.action == expected and result.remaining_owned_exit_quantity == D(owned)
    assert (
        router.plan_stock_session_recovery(**(call | {"projection": None})).action
        == "reconcile_owned"
    )
    result = router.plan_stock_session_recovery(**(call | {"reads": None, "reconciliation": None}))
    assert result.action == "reconcile_owned" and result.remaining_owned_exit_quantity is None


def test_closed_partial_retains_owned_exit_quantity_and_original_reservation():
    call = observed(request(), filled="1", outstanding="0", owned="1", open_order=False)
    before = copy.deepcopy(call)
    result = router.plan_stock_session_recovery(**call)
    assert result.action == "remaining_owned_exit" and result.remaining_owned_exit_quantity == D(1)
    assert result.retained_fill_quantity == D(1) and call == before
    assert result.safe_payload()["reservation_effect"] == "unchanged"


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize(
    "phase,cancellation", [("submitted", False), ("cancelled", False), ("submitted", True)]
)
def test_zero_fill_and_no_open_order_require_exact_cancelled_proof(side, phase, cancellation):
    call = observed(
        request(side=side),
        filled="0",
        outstanding="0",
        phase=phase,
        owned="0",
        open_order=False,
        cancellation=cancellation,
    )
    before = copy.deepcopy(call)
    result = router.plan_stock_session_recovery(**call)
    assert result.action in {"reconcile_unknown", "reconcile_open", "reconcile_owned"}
    assert result.remaining_owned_exit_quantity is None
    assert result.retained_fill_quantity == D(0)
    assert result.safe_payload()["reservation_effect"] == "unchanged" and call == before


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_zero_fill_cancellation_is_not_flat_without_current_owned_evidence(side):
    call = observed(
        request(side=side),
        filled="0",
        outstanding="0",
        phase="cancelled",
        owned="0",
        open_order=False,
        cancellation=True,
    )
    assert router.plan_stock_session_recovery(**call).action == "terminal_owned_flat"
    assert (
        router.plan_stock_session_recovery(**(call | {"projection": None})).action
        == "reconcile_owned"
    )


def test_truthy_cancellation_flag_is_not_typed_terminal_proof():
    call = observed(
        request(),
        filled="0",
        outstanding="0",
        phase="cancelled",
        open_order=False,
        cancellation=True,
    )
    object.__setattr__(call["reconciliation"].execution, "cancellation_confirmed", 1)
    with pytest.raises(ValueError, match="cancellation observation invalid"):
        router.plan_stock_session_recovery(**call)


def test_cancellation_proof_must_match_current_retained_observation():
    call = observed(
        request(),
        filled="0",
        outstanding="0",
        phase="cancelled",
        open_order=False,
        cancellation=True,
    )
    call["state"] = replace(call["state"], fill_observation_status="unavailable")
    with pytest.raises(ValueError, match="fill_binding_or_time_mismatch"):
        router.plan_stock_session_recovery(**call)


def test_foreign_holding_is_not_adopted_and_terminal_phase_is_not_false_flat():
    call = observed(
        request(side="sell"),
        filled="4",
        outstanding="0",
        owned="0",
        broker_owned="9",
        open_order=False,
    )
    with pytest.raises(ValueError, match="broker_owned_quantity_mismatch"):
        router.plan_stock_session_recovery(**call)
    call = request()
    call["state"] = replace(call["seed"], phase="cancelled", reason_code="reconciliation_clean")
    assert router.plan_stock_session_recovery(**call).action == "reconcile_unknown"


@pytest.mark.parametrize("field,value", [("account_ref", "e" * 64), ("instrument", None)])
def test_reads_binding_cannot_cross_account_or_instrument(field, value):
    call = observed(request())
    call["reads"] = replace(call["reads"], **{field: value})
    with pytest.raises(ValueError, match="reads_binding_mismatch"):
        router.plan_stock_session_recovery(**call)


@pytest.mark.parametrize("delta", [-timedelta(minutes=3), timedelta(seconds=1)])
def test_stale_or_future_observation_does_not_produce_a_cancellation(delta):
    call = request()
    call["as_of"] = call["seed"].intent.valid_until
    call = observed(call)
    altered = replace(call["reads"].snapshot, captured_at=call["as_of"] + delta)
    call["reads"] = replace(call["reads"], snapshot=altered)
    with pytest.raises(ValueError, match="observation_stale_or_future"):
        router.plan_stock_session_recovery(**call)


@pytest.mark.parametrize("field", ["intent_ref", "run_id", "side"])
def test_request_identity_mismatch_is_scoped_error(field):
    call = request()
    changed = dict(intent_ref="sha256:" + "f" * 64, run_id="bk-" + "f" * 64, side="sell")
    call["proof"] = replace(call["proof"], **{field: changed[field]})
    with pytest.raises(ValueError, match="request_binding_mismatch"):
        router.plan_stock_session_recovery(**call)


def test_dirty_decimal_context_is_preserved_and_no_private_fields_are_projected():
    call = observed(request(), filled="1", outstanding="0", owned="1", open_order=False)
    with localcontext() as context:
        context.prec, context.rounding = 2, ROUND_UP
        context.traps[Inexact] = context.traps[Rounded] = True
        context.flags[Inexact] = context.flags[Rounded] = True
        before = context.copy()
        result = router.plan_stock_session_recovery(**call)
        assert result.action == "remaining_owned_exit"
        assert context.prec == before.prec and context.traps == before.traps
        assert context.flags == before.flags and context.rounding == before.rounding
    payload = str(result.safe_payload())
    assert all(value not in payload for value in ("AAPL", "123", ACCOUNT, call["proof"].run_id))


def test_invalid_bool_schema_and_mutated_frozen_state_are_rejected():
    call = request()
    with pytest.raises(ValueError, match="schema_invalid"):
        router.plan_stock_session_recovery(
            **(call | {"state": replace(call["state"], schema_version=True)})
        )
    state = copy.deepcopy(call["state"])
    object.__setattr__(state, "submission_started_at", state.intent.created_at)
    with pytest.raises(ValueError, match="unsubmitted_state_conflict"):
        router.plan_stock_session_recovery(**(call | {"state": state}))


def test_cash_free_exit_reads_support_recovery_without_buying_power():
    call = observed(request(side="sell"), filled="4", outstanding="0", owned="0", open_order=False)
    old, at = call["reads"].snapshot, call["as_of"]
    snapshot = KisPaperStockExitAccountSnapshot(old.identity, old.positions, old.open_orders, at)
    reads = KisPaperStockExitReads(
        ACCOUNT,
        call["proof"].instrument,
        snapshot,
        KisPaperSpyLimitInput(D(100), 2, D(".01"), at, D(100), D(100)),
        at,
        at,
        0.0,
    )
    call["reads"] = reads
    call["reconciliation"] = replace(call["reconciliation"], snapshot=snapshot)
    assert not hasattr(snapshot, "cash") and not hasattr(snapshot, "orderable_funds")
    assert router.plan_stock_session_recovery(**call).action == "terminal_owned_flat"


def test_partial_retained_when_later_history_is_unavailable_is_not_current_zero():
    call = observed(request(), filled="1", outstanding="3", owned="1")
    call["state"] = replace(call["state"], fill_observation_status="unavailable")
    call["reads"] = call["reconciliation"] = None
    result = router.plan_stock_session_recovery(**call)
    assert result.action == "reconcile_open" and result.retained_fill_quantity == D(1)
    assert result.outstanding_quantity is result.remaining_owned_exit_quantity is None


def test_unknown_original_attempt_time_never_becomes_submit_or_cancel():
    call = request()
    call["state"] = replace(
        call["state"], phase="submitted", reason_code="reconciliation_unresolved"
    )
    call["as_of"] = call["state"].intent.valid_until
    assert router.plan_stock_session_recovery(**call).action == "reconcile_unknown"


def test_cancel_after_close_keeps_original_seed_and_expiry():
    call = request()
    call["as_of"] = CLOSE + timedelta(minutes=1)
    call = observed(call)
    result = router.plan_stock_session_recovery(**call)
    assert result.action == "cancel_exact_expired"
    assert result.intent == call["seed"].intent and result.original_valid_until < CLOSE


def test_stale_component_of_complete_snapshot_cannot_prove_flat():
    call = observed(request(side="sell"), filled="4", outstanding="0", owned="0", open_order=False)
    snapshot = call["reads"].snapshot
    snapshot = replace(
        snapshot,
        open_orders=replace(
            snapshot.open_orders,
            captured_at=call["as_of"] - timedelta(seconds=1),
        ),
    )
    call["reads"] = replace(call["reads"], snapshot=snapshot)
    call["reconciliation"] = replace(call["reconciliation"], snapshot=snapshot)
    result = router.plan_stock_session_recovery(**call)
    assert result.action == "reconcile_owned" and result.remaining_owned_exit_quantity is None


def test_unrelated_open_owner_does_not_pause_request_but_exact_overlap_is_scoped():
    call = observed(request())
    call["state"] = call["seed"]
    call["reconciliation"] = None
    snapshot = call["reads"].snapshot
    order = replace(snapshot.open_orders.orders[0], symbol="MSFT")
    snapshot = replace(snapshot, open_orders=replace(snapshot.open_orders, orders=(order,)))
    call["reads"] = replace(call["reads"], snapshot=snapshot)
    assert router.plan_stock_session_recovery(**call).action == "submit_exact_seed"
    snapshot = replace(
        snapshot,
        open_orders=replace(
            snapshot.open_orders,
            orders=(replace(order, symbol="AAPL"),),
        ),
    )
    call["reads"] = replace(call["reads"], snapshot=snapshot)
    assert router.plan_stock_session_recovery(**call).reason == "exact_instrument_overlap"


def test_provider_rejection_without_actual_attempt_is_not_current_flat():
    call = request()
    call["state"] = replace(
        call["seed"],
        phase="rejected",
        reason_code="submit_rejected",
        submit_response_category="provider_rejected",
    )
    assert router.plan_stock_session_recovery(**call).action == "reconcile_unknown"


@pytest.mark.parametrize("field", ["seed", "state"])
def test_missing_persisted_state_is_not_an_unattempted_seed(field):
    with pytest.raises(ValueError, match="state_invalid"):
        router.plan_stock_session_recovery(**(request() | {field: None}))


def test_truthy_incomplete_order_flag_cannot_publish_exact_cancel():
    call = request()
    call["as_of"] = call["seed"].intent.valid_until
    call = observed(call)
    object.__setattr__(call["reads"].snapshot.open_orders, "complete", 1)
    with pytest.raises(ValueError, match="open_orders_incomplete"):
        router.plan_stock_session_recovery(**call)
