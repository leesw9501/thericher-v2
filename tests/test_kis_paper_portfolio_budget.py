from __future__ import annotations

import copy
import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from thericher_v2.execution.kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_portfolio_budget import (
    KisPaperPortfolioBudgetBasis,
    KisPaperPortfolioBudgetError,
    KisPaperPortfolioOwnerBinding,
    KisPaperPortfolioStateRef,
    project_kis_paper_portfolio_budget,
)

D = Decimal
START = datetime(2026, 9, 22, 14, 30, tzinfo=UTC)
AS_OF = datetime(2026, 10, 3, tzinfo=UTC)
ACCOUNT = "a" * 64
BASIS = KisPaperPortfolioBudgetBasis(ACCOUNT, D("10000"), D("1000"), START)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pure portfolio projection must never use the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def _state(
    run_id,
    *,
    symbol="SPY",
    side="buy",
    quantity="1",
    limit="100",
    index=0,
    filled=None,
    gross="0",
    remaining=None,
    phase="submitted",
    category=None,
    observation="available",
    expired=False,
):
    at = START + timedelta(minutes=index)
    intent = KisPaperCanaryIntent(
        run_id,
        "canary-" + run_id,
        "decision-" + run_id,
        symbol,
        "AMEX" if symbol == "SPY" else "NASD",
        D(quantity),
        D(limit),
        at,
        at + timedelta(seconds=20),
        side,
    )
    attempted = phase != "intent_recorded"
    known = filled is not None or phase in {"submitted", "cancel_started", "cancelled"}
    order_id = "SYNTHETIC-" + run_id if known else None
    order_at = at + timedelta(seconds=1) if attempted else None
    updated = at + timedelta(seconds=30 if expired else 5)
    fill = (
        None
        if filled is None
        else KisPaperCumulativeFill(
            fill_identity_ref(
                raw_order_id=order_id,
                order_at=order_at,
                symbol=symbol,
                exchange=intent.exchange,
                side=side,
                quantity=intent.quantity,
            ),
            intent.quantity,
            D(filled),
            D(gross),
            at + timedelta(seconds=2),
            None if remaining is None else D(remaining),
        )
    )
    return KisPaperCanaryState(
        intent,
        phase,
        updated,
        "reconciliation_unresolved",
        broker_order_id=order_id,
        submission_started_at=order_at,
        submitted_at=order_at if known else None,
        submit_response_category=category,
        cumulative_fill=fill,
        fill_observation_status=(
            observation if fill is not None or observation != "available" else "not_observed"
        ),
        fill_observed_at=(
            (at + timedelta(seconds=2) if observation == "available" else updated)
            if fill is not None or observation not in {"available", "not_observed"}
            else None
        ),
    )


def _owner(name, *states, symbol=None, account=ACCOUNT):
    symbol = symbol or (states[0].intent.symbol if states else "SPY")
    return KisPaperPortfolioOwnerBinding(
        name,
        account,
        symbol,
        "AMEX" if symbol == "SPY" else "NASD",
        tuple(
            KisPaperPortfolioStateRef(state.intent.run_id, state.intent.fingerprint)
            for state in states
        ),
    ), states


def _project(*groups, **changes):
    arguments = dict(
        basis=BASIS,
        expected_basis_ref=BASIS.fingerprint,
        owners=tuple(owner for owner, _ in groups),
        expected_owner_refs={owner.owner_ref: owner.fingerprint for owner, _ in groups},
        states={state.intent.run_id: state for _, states in groups for state in states},
        as_of=AS_OF,
    )
    arguments.update(changes)
    return project_kis_paper_portfolio_budget(**arguments)


def _cancel(state):
    return KisPaperExecutionObservation(
        row_count=2,
        same_day_order_id_seen=True,
        status="available",
        fill=state.current_fill,
        observed_at=state.fill_observed_at,
        cancellation_confirmed=True,
    )


def _tamper(value, field, bad):
    result = copy.deepcopy(value)
    object.__setattr__(result, field, bad)
    return result


def test_zero_trades_and_empty_bound_owner_are_zero_not_account_inventory():
    for projection in (_project(), _project(_owner("empty"))):
        assert projection.entry_cost == projection.reserved_buys == 0
        assert projection.remaining_cap == projection.allocated_usd == D("1000")
        assert tuple(
            (stock.symbol, stock.quantity) for stock in projection.stocks_by_instrument
        ) == (
            ("SPY", D(0)),
            ("QQQ", D(0)),
        )


def test_legacy_spy_truth_stays_charged_while_independent_qqq_roundtrip_replays():
    spy_buy = _state("legacy-buy", filled="1", gross="600", limit="610")
    spy_cancel = _state(
        "legacy-cancel",
        side="sell",
        filled="0",
        remaining="0",
        phase="cancelled",
        index=1,
    )
    spy_unknown = _state(
        "legacy-unknown",
        side="sell",
        phase="outcome_unknown",
        index=2,
        category="provider_rejected",
    )
    qqq_buy = _state("qqq-buy", symbol="QQQ", limit="400", filled="1", gross="390", index=3)
    qqq_sell = _state(
        "qqq-sell",
        symbol="QQQ",
        side="sell",
        limit="400",
        filled="1",
        gross="700",
        index=4,
    )
    states = (spy_buy, spy_cancel, spy_unknown, qqq_buy, qqq_sell)
    before = tuple(state.to_dict() for state in states)
    projection = _project(
        _owner("legacy-spy", *states[:3]),
        _owner("independent-qqq", *states[3:]),
        cancellation_proofs={spy_cancel.intent.run_id: _cancel(spy_cancel)},
    )
    spy, qqq = projection.stocks_by_owner
    assert (spy.quantity, spy.entry_cost, spy.reserved_buys) == (D(1), D(600), D(0))
    assert (qqq.quantity, qqq.entry_cost, qqq.reserved_buys) == (D(0), D(0), D(0))
    assert projection.remaining_cap == D(400)
    assert tuple(state.to_dict() for state in states) == before
    assert spy_unknown.phase == "outcome_unknown" and spy_unknown.broker_order_id is None


def test_qqq_must_fit_remaining_aggregate_not_a_second_tenth():
    spy = _owner("spy", _state("spy", filled="1", gross="600", limit="600"))
    qqq = _owner("qqq", _state("qqq", symbol="QQQ", phase="outcome_unknown", limit="400"))
    result = _project(spy, qqq)
    assert result.entry_cost == 600 and result.reserved_buys == 400 and result.remaining_cap == 0
    excessive = _owner(
        "qqq",
        _state("qqq", symbol="QQQ", phase="outcome_unknown", limit="400.01"),
    )
    with pytest.raises(KisPaperPortfolioBudgetError, match="aggregate_budget_exceeded"):
        _project(spy, excessive)


@pytest.mark.parametrize("phase", ["submission_started", "outcome_unknown", "submitted"])
@pytest.mark.parametrize("observation", ["not_observed", "absent", "unavailable"])
def test_missing_unknown_buy_fills_reserve_full_limit(phase, observation):
    state = _state("unknown", quantity="3", limit="99", phase=phase, observation=observation)
    result = _project(_owner("owner", state))
    assert (result.entry_cost, result.reserved_buys, result.remaining_cap) == (0, 297, 703)


@pytest.mark.parametrize("observation", ["available", "absent", "unavailable", "conflict"])
def test_stored_partial_fill_remains_charged_once_after_later_unavailable_read(observation):
    state = _state(
        "partial",
        quantity="4",
        limit="110",
        filled="3",
        gross="300",
        remaining="1",
        phase="outcome_unknown",
        observation=observation,
    )
    group = _owner("owner", state)
    for _ in range(3):
        result = _project(group)
        assert (result.entry_cost, result.reserved_buys, result.remaining_cap) == (300, 110, 590)
        assert result.stocks_by_owner[0].quantity == 3


def test_partial_sell_releases_only_observed_quantity_not_unknown_residual():
    buy = _state("buy", quantity="4", limit="110", filled="3", gross="300", remaining="1")
    sell = _state(
        "sell",
        side="sell",
        quantity="2",
        filled="1",
        gross="500",
        remaining="1",
        index=1,
        phase="outcome_unknown",
        observation="unavailable",
    )
    projection = _project(_owner("owner", buy, sell))
    stock = projection.stocks_by_owner[0]
    assert (stock.quantity, stock.entry_cost, stock.reserved_buys) == (2, 200, 110)
    assert projection.remaining_cap == 690


def test_weighted_entry_cost_and_profit_do_not_expand_initial_allocation():
    first = _state("first", quantity="2", filled="2", gross="180", limit="100")
    second = _state("second", filled="1", gross="150", limit="150", index=1)
    exit_one = _state("exit", side="sell", filled="1", gross="900", index=2)
    result = _project(_owner("owner", first, second, exit_one))
    assert result.entry_cost == 220 and result.stocks_by_owner[0].quantity == 2
    assert result.allocated_usd == 1000 and result.remaining_cap == 780


def test_full_sell_releases_entry_cost_once_and_resale_cannot_hide_overspend():
    buy = _state("buy", filled="1", gross="900", limit="900")
    sell = _state("sell", side="sell", filled="1", gross="3000", index=1)
    next_buy = _state("next", phase="outcome_unknown", limit="1000", index=2)
    projection = _project(_owner("owner", buy, sell, next_buy))
    assert (projection.entry_cost, projection.reserved_buys, projection.remaining_cap) == (
        0,
        1000,
        0,
    )
    excessive = _state("excessive", filled="1", gross="1001", limit="1001")
    excessive_exit = _state("excessive-exit", side="sell", filled="1", gross="2000", index=1)
    with pytest.raises(KisPaperPortfolioBudgetError, match="aggregate_budget_exceeded"):
        _project(_owner("owner", excessive, excessive_exit))


def test_nonterminating_cost_and_remaining_are_conservative_and_context_independent():
    buy = _state("buy", quantity="3", filled="3", gross="100", limit="100")
    sell = _state("sell", side="sell", filled="1", gross="50", index=1)
    group = _owner("owner", buy, sell)
    ordinary = _project(group)
    with localcontext() as context:
        context.prec = 2
        low_precision = _project(group)
    assert ordinary == low_precision
    assert Fraction(ordinary.entry_cost) >= Fraction(200, 3)
    assert Fraction(ordinary.remaining_cap) <= Fraction(2800, 3)


@pytest.mark.parametrize("phase", ["outcome_unknown", "cancel_started", "cancelled"])
def test_zero_or_absent_unknown_sell_never_releases_entry_cost(phase):
    buy = _state("buy", filled="1", gross="600", limit="600")
    sell = _state(
        "sell",
        side="sell",
        phase=phase,
        filled=None if phase == "outcome_unknown" else "0",
        remaining=None,
        index=1,
    )
    result = _project(_owner("owner", buy, sell))
    assert result.entry_cost == 600 and result.stocks_by_owner[0].quantity == 1


@pytest.mark.parametrize("reason", ["submit_rejected", "submit_kis_rejected", "intent_expired"])
def test_legacy_unknown_provider_rejected_category_or_reason_does_not_release(reason):
    state = replace(
        _state("unknown", phase="outcome_unknown", category="provider_rejected"),
        reason_code=reason,
    )
    assert _project(_owner("owner", state)).reserved_buys == 100


def test_only_known_never_submitted_expiry_or_exact_rejection_releases():
    before_expiry = _state("unsubmitted", phase="intent_recorded")
    expired = _state("expired", phase="intent_recorded", expired=True)
    rejected = _state("rejected", phase="rejected", category="provider_rejected")
    unproven_rejected = _state("unproven", phase="rejected")
    for state, reserved in (
        (before_expiry, 100),
        (expired, 0),
        (rejected, 0),
        (unproven_rejected, 100),
    ):
        assert _project(_owner("owner", state)).reserved_buys == reserved


def test_cancelled_zero_needs_exact_positive_proof_not_phase_or_remaining_alone():
    state = _state("cancel", phase="cancelled", filled="0", remaining="0")
    group = _owner("owner", state)
    assert _project(group).reserved_buys == 100
    proof = _cancel(state)
    assert _project(group, cancellation_proofs={"cancel": proof}).reserved_buys == 0
    for _ in range(3):
        assert _project(group, cancellation_proofs={"cancel": proof}).remaining_cap == 1000


def test_partial_cancel_without_supported_zero_fill_proof_keeps_residual():
    state = _state(
        "cancel",
        phase="cancelled",
        quantity="3",
        filled="2",
        gross="180",
        remaining="0",
    )
    result = _project(_owner("owner", state))
    assert result.entry_cost == 180 and result.reserved_buys == 100


@pytest.mark.parametrize("change", ["other_identity", "unconfirmed", "unknown_phase", "stale_fill"])
def test_cancellation_proof_cannot_be_substituted(change):
    state = _state("cancel", phase="cancelled", filled="0", remaining="0")
    proof = _cancel(state)
    if change == "other_identity":
        proof = _cancel(_state("foreign", phase="cancelled", filled="0", remaining="0"))
    elif change == "unconfirmed":
        proof = replace(proof, cancellation_confirmed=False)
    elif change == "unknown_phase":
        state = replace(state, phase="outcome_unknown")
    else:
        state = replace(
            state, fill_observation_status="unavailable", fill_observed_at=state.updated_at
        )
    with pytest.raises(KisPaperPortfolioBudgetError, match="cancel_proof_mismatch"):
        _project(_owner("owner", state), cancellation_proofs={"cancel": proof})


def test_other_owner_or_instrument_cannot_supply_sell_inventory():
    spy = _owner("spy", _state("spy", filled="1", gross="600", limit="600"))
    for sell_symbol in ("SPY", "QQQ"):
        foreign_sell = _owner(
            "other",
            _state("sell", symbol=sell_symbol, side="sell", filled="1", gross="600", index=1),
        )
        with pytest.raises(KisPaperPortfolioBudgetError, match="unowned_sell"):
            _project(spy, foreign_sell)


def test_same_instrument_separate_owners_aggregate_without_netting():
    first = _owner("first", _state("first", filled="1", gross="200", limit="200"))
    second = _owner("second", _state("second", quantity="2", filled="2", gross="300", limit="200"))
    result = _project(first, second)
    assert tuple(stock.entry_cost for stock in result.stocks_by_owner) == (200, 300)
    assert result.stocks_by_instrument[0].entry_cost == 500
    assert result.stocks_by_instrument[0].quantity == 3


def test_sell_requested_inventory_must_be_known_even_when_fill_missing():
    buy = _state("buy", filled="1", gross="100")
    sell = _state("sell", side="sell", quantity="2", phase="outcome_unknown", index=1)
    with pytest.raises(KisPaperPortfolioBudgetError, match="unowned_sell"):
        _project(_owner("owner", buy, sell))


@pytest.mark.parametrize(
    "changes",
    [
        {"basis_usd": D("20000"), "allocated_usd": D("2000")},
        {"basis_usd": D("5000"), "allocated_usd": D("500")},
        {"account_ref": "b" * 64},
        {"frozen_at": START + timedelta(days=1)},
    ],
)
def test_existing_basis_requires_exact_binding_no_reset_increase_or_recapitalization(changes):
    with pytest.raises(KisPaperPortfolioBudgetError, match="basis_binding_mismatch"):
        _project(basis=replace(BASIS, **changes))


def test_owner_and_account_proofs_are_exact_caller_inputs_not_flags():
    state = _state("buy")
    wrong_account = _owner("owner", state, account="b" * 64)
    with pytest.raises(KisPaperPortfolioBudgetError, match="account_binding_mismatch"):
        _project(wrong_account)
    group = _owner("owner", state)
    with pytest.raises(KisPaperPortfolioBudgetError, match="owner_binding_mismatch"):
        _project(group, expected_owner_refs={"owner": "sha256:" + "0" * 64})
    with pytest.raises(KisPaperPortfolioBudgetError, match="owner_reference_invalid"):
        _project(group, expected_owner_refs={"owner": True})
    with pytest.raises(KisPaperPortfolioBudgetError, match="owner_proof_scope_mismatch"):
        _project(
            group, expected_owner_refs={"owner": group[0].fingerprint, "orphan": BASIS.fingerprint}
        )


def test_fingerprint_and_run_id_drift_rejected_even_when_state_objects_are_valid():
    state = _state("buy")
    group = _owner("owner", state)
    for intent in (
        replace(state.intent, limit_price=D(101)),
        replace(state.intent, run_id="other"),
    ):
        with pytest.raises(KisPaperPortfolioBudgetError, match="intent_binding_mismatch"):
            _project(group, states={"buy": replace(state, intent=intent)})


def test_owner_cannot_change_instrument_or_frozen_reference_order():
    buy = _state("buy", filled="1", gross="100")
    sell = _state("sell", side="sell", filled="1", gross="100", index=1)
    binding, states = _owner("owner", buy, sell)
    for changed in (
        replace(binding, symbol="QQQ", exchange="NASD"),
        replace(binding, state_refs=tuple(reversed(binding.state_refs))),
    ):
        with pytest.raises(KisPaperPortfolioBudgetError, match="owner_binding_mismatch"):
            _project((changed, states), expected_owner_refs={"owner": binding.fingerprint})
    with pytest.raises(KisPaperPortfolioBudgetError, match="owner_order_invalid"):
        _project(_owner("owner", sell, buy))


def test_reobserved_buy_time_is_not_confused_with_trade_chronology():
    buy = _state("buy", filled="1", gross="100")
    sell = _state("sell", side="sell", filled="1", gross="300", index=1)
    later = AS_OF - timedelta(seconds=1)
    buy = replace(
        buy,
        updated_at=later,
        fill_observed_at=later,
        cumulative_fill=replace(buy.cumulative_fill, observed_at=later),
    )
    assert _project(_owner("owner", buy, sell)).entry_cost == 0


@pytest.mark.parametrize("scope", ["same_owner", "other_owner", "duplicate_owner"])
def test_duplicate_state_references_are_invalid_not_silently_double_charged(scope):
    state = _state("buy")
    group = _owner("owner", state)
    if scope == "same_owner":
        groups = (_owner("owner", state, state),)
    elif scope == "other_owner":
        groups = (group, _owner("other", state))
    else:
        groups = (group, group)
    with pytest.raises(KisPaperPortfolioBudgetError, match="duplicate_(state_reference|owner)"):
        _project(*groups)


@pytest.mark.parametrize("field", ["client_order_id", "decision_id"])
def test_distinct_run_names_do_not_evade_duplicate_intent_identity(field):
    first, second = _state("first"), _state("second", index=1)
    second = replace(second, intent=replace(second.intent, **{field: getattr(first.intent, field)}))
    with pytest.raises(KisPaperPortfolioBudgetError, match="duplicate_intent_identity"):
        _project(_owner("owner", first, second))


def test_missing_or_extra_states_and_foreign_snapshot_cannot_be_adopted():
    state = _state("buy")
    group = _owner("owner", state)
    for states, category in (
        ({}, "referenced_state_missing"),
        ({"buy": state, "foreign": _state("foreign")}, "state_scope_mismatch"),
        ({"buy": {"position_quantity": D(1), "account_verified": True}}, "state_invalid"),
    ):
        with pytest.raises(KisPaperPortfolioBudgetError, match=category):
            _project(group, states=states)


BAD_AMOUNTS = [
    True,
    False,
    None,
    1,
    1.0,
    "1",
    "oops",
    D("NaN"),
    D("sNaN"),
    D("Infinity"),
    D("-Infinity"),
    D("-1"),
    D("-0"),
]


@pytest.mark.parametrize("value", BAD_AMOUNTS + [D(0)])
@pytest.mark.parametrize("field", ["basis_usd", "allocated_usd"])
def test_basis_numeric_field_types_and_values_are_strict(field, value):
    with pytest.raises(KisPaperPortfolioBudgetError, match="numeric_field_invalid"):
        replace(BASIS, **{field: value})


@pytest.mark.parametrize("allocated", [D("999"), D("1001")])
def test_fraction_is_exactly_tenth_not_caller_chosen(allocated):
    with pytest.raises(KisPaperPortfolioBudgetError, match="allocation_not_initial_tenth"):
        replace(BASIS, allocated_usd=allocated)


@pytest.mark.parametrize("field", ["quantity", "limit_price"])
@pytest.mark.parametrize("value", BAD_AMOUNTS + [D(0)])
def test_tampered_real_intent_numeric_fields_fail_closed(field, value):
    state = _state("buy")
    group = _owner("owner", state)
    bad = _tamper(state, "intent", _tamper(state.intent, field, value))
    with pytest.raises(KisPaperPortfolioBudgetError, match="numeric_field_invalid"):
        _project(group, states={"buy": bad})


@pytest.mark.parametrize(
    "field", ["requested_quantity", "quantity", "gross_amount", "remaining_quantity"]
)
@pytest.mark.parametrize("value", BAD_AMOUNTS)
def test_tampered_real_fill_numeric_fields_fail_closed(field, value):
    if field == "remaining_quantity" and value is None:
        state = _state("unknown-residual", quantity="2", filled="1", gross="100")
        assert _project(_owner("owner", state)).reserved_buys == 100
        return  # None is the explicit unknown-remaining contract, not malformed.
    state = _state("buy", quantity="2", filled="1", gross="100", remaining="1")
    group = _owner("owner", state)
    bad = _tamper(state, "cumulative_fill", _tamper(state.cumulative_fill, field, value))
    with pytest.raises(KisPaperPortfolioBudgetError, match="numeric_field_invalid"):
        _project(group, states={"buy": bad})


@pytest.mark.parametrize(
    "field,bad",
    [
        ("quantity", D("0.5")),
        ("requested_quantity", D("1.5")),
        ("remaining_quantity", D("0.5")),
        ("quantity", D(3)),
        ("requested_quantity", D(3)),
        ("quantity", D(0)),
        ("gross_amount", D(0)),
        ("remaining_quantity", D(3)),
        ("identity_ref", "sha256:" + "0" * 64),
    ],
)
def test_fractional_contradictory_or_wrong_identity_cumulative_fields_rejected(field, bad):
    state = _state("buy", quantity="2", filled="1", gross="100", remaining="1")
    group = _owner("owner", state)
    state = _tamper(state, "cumulative_fill", _tamper(state.cumulative_fill, field, bad))
    with pytest.raises(KisPaperPortfolioBudgetError):
        _project(group, states={"buy": state})


@pytest.mark.parametrize(
    "field,bad",
    [
        ("phase", True),
        ("phase", []),
        ("reason_code", "private-secret"),
        ("broker_order_id", True),
        ("cancel_after_submit", "yes"),
        ("schema_version", True),
        ("schema_version", 2),
        ("submit_response_category", "arbitrary"),
        ("fill_observation_status", 1),
        ("updated_at", START - timedelta(seconds=1)),
        ("updated_at", AS_OF + timedelta(seconds=1)),
        ("updated_at", START.replace(tzinfo=None)),
        ("submission_started_at", "2026-09-22"),
        ("cumulative_fill", {"quantity": "1"}),
    ],
)
def test_tampered_real_state_field_types_and_lifetime_rejected(field, bad):
    state = _state("buy", filled="1", gross="100")
    group = _owner("owner", state)
    with pytest.raises(KisPaperPortfolioBudgetError):
        _project(group, states={"buy": _tamper(state, field, bad)})


@pytest.mark.parametrize(
    "symbol,exchange",
    [("SPY", "NASD"), ("QQQ", "AMEX"), ("IWM", "AMEX"), (True, "AMEX"), ("SPY", [])],
)
def test_only_two_exact_instrument_pairs_supported(symbol, exchange):
    with pytest.raises(KisPaperPortfolioBudgetError, match="instrument_invalid"):
        KisPaperPortfolioOwnerBinding("owner", ACCOUNT, symbol, exchange, ())


def test_malformed_reference_collections_and_proof_fields_rejected():
    for bad in (True, None, "not-a-digest", "a" * 64):
        with pytest.raises(KisPaperPortfolioBudgetError, match="basis_reference_invalid"):
            _project(expected_basis_ref=bad)
    with pytest.raises(KisPaperPortfolioBudgetError, match="owners_not_frozen"):
        _project(owners=[])
    with pytest.raises(KisPaperPortfolioBudgetError, match="state_references_not_frozen"):
        KisPaperPortfolioOwnerBinding("owner", ACCOUNT, "SPY", "AMEX", [])
    for bad in (True, {}, "raw-account", "A" * 64):
        with pytest.raises(KisPaperPortfolioBudgetError, match="account_binding_invalid"):
            replace(BASIS, account_ref=bad)
    with pytest.raises(KisPaperPortfolioBudgetError, match="intent_reference_invalid"):
        KisPaperPortfolioStateRef("run", True)
    with pytest.raises(KisPaperPortfolioBudgetError, match="state_reference_invalid"):
        KisPaperPortfolioStateRef("../private", BASIS.fingerprint)


def test_numeric_buy_limit_contradiction_is_not_hidden_by_profitable_exit():
    buy = _state("buy", filled="1", gross="100.01", limit="100")
    with pytest.raises(KisPaperPortfolioBudgetError, match="buy_fill_limit_conflict"):
        _project(_owner("owner", buy))


def test_cancel_proof_scope_and_field_types_fail_closed():
    state = _state("cancel", phase="cancelled", filled="0", remaining="0")
    group = _owner("owner", state)
    with pytest.raises(KisPaperPortfolioBudgetError, match="cancel_proof_scope_mismatch"):
        _project(group, cancellation_proofs={"foreign": _cancel(state)})
    with pytest.raises(KisPaperPortfolioBudgetError, match="cancel_proof_invalid"):
        _project(group, cancellation_proofs={"cancel": True})
    with pytest.raises(KisPaperPortfolioBudgetError, match="cancel_proof_invalid"):
        _project(group, cancellation_proofs={"cancel": _tamper(_cancel(state), "row_count", True)})


def test_safe_reprs_and_categorical_errors_never_expose_amounts_or_identifiers():
    state = _state("sensitive-id", filled="1", gross="987.65", limit="999")
    owner, states = _owner("sensitive-owner", state)
    projection = _project((owner, states))
    for value in (
        BASIS,
        owner,
        owner.state_refs[0],
        projection,
        *projection.stocks_by_owner,
        *projection.stocks_by_instrument,
    ):
        representation = repr(value)
        for secret in (ACCOUNT, "987.65", "sensitive-id", "sensitive-owner", "10000"):
            assert secret not in representation
        assert not hasattr(value, "safe_payload")
    with pytest.raises(FrozenInstanceError):
        projection.entry_cost = D(0)
    with pytest.raises(KisPaperPortfolioBudgetError) as error:
        _project((owner, states), expected_owner_refs={owner.owner_ref: "sha256:" + "0" * 64})
    assert str(error.value) == "owner_binding_mismatch"


def test_projection_does_not_read_files_environment_or_modify_real_state_objects(monkeypatch):
    state = _state("buy", filled="1", gross="100")
    group = _owner("owner", state)
    before = state.to_dict()

    def forbidden(*args, **kwargs):
        pytest.fail("projection must perform no file or environment reads")

    with monkeypatch.context() as guard:
        guard.setattr(Path, "read_text", forbidden)
        guard.setattr(Path, "open", forbidden)
        guard.setattr("os.getenv", forbidden)
        assert _project(group).entry_cost == 100
    assert state.to_dict() == before


def test_reused_exact_broker_fill_identity_cannot_create_a_second_owned_lot():
    first = _state("first", filled="1", gross="100")
    second = _state("second", filled="1", gross="100", index=1)
    second = replace(
        second,
        broker_order_id=first.broker_order_id,
        cumulative_fill=replace(
            second.cumulative_fill, identity_ref=first.cumulative_fill.identity_ref
        ),
    )
    with pytest.raises(KisPaperPortfolioBudgetError, match="broker_order_alias"):
        _project(_owner("owner", first, second))


def test_submission_order_cannot_run_backwards_behind_ordered_intent_times():
    first = _state("first")
    later_attempt = START + timedelta(minutes=10)
    first = replace(
        first,
        submission_started_at=later_attempt,
        submitted_at=later_attempt,
        updated_at=later_attempt + timedelta(seconds=5),
    )
    second = _state("second", index=5)
    with pytest.raises(KisPaperPortfolioBudgetError, match="owner_order_invalid"):
        _project(_owner("owner", first, second))


def test_unknown_buy_zero_remaining_is_not_a_cancellation_or_terminal_proof():
    state = _state(
        "unknown",
        phase="outcome_unknown",
        filled="0",
        remaining="0",
        category="provider_rejected",
    )
    assert _project(_owner("owner", state)).reserved_buys == 100


@pytest.mark.parametrize("phase", ["intent_recorded", "rejected"])
def test_unsubmitted_or_rejected_phase_cannot_erase_a_positive_execution_fact(phase):
    state = _state("buy", filled="1", gross="100")
    state = replace(state, phase=phase, submit_response_category="provider_rejected")
    with pytest.raises(KisPaperPortfolioBudgetError, match="state_conflict"):
        _project(_owner("owner", state))


def test_fractional_requested_intent_quantity_is_never_accepted():
    state = _state("buy")
    group = _owner("owner", state)
    bad = _tamper(state, "intent", _tamper(state.intent, "quantity", D("1.5")))
    with pytest.raises(KisPaperPortfolioBudgetError, match="numeric_field_invalid"):
        _project(group, states={"buy": bad})


@pytest.mark.parametrize(
    "changes",
    [
        {"states": []},
        {"expected_owner_refs": True},
        {"cancellation_proofs": []},
        {"as_of": AS_OF.replace(tzinfo=None)},
        {"as_of": True},
    ],
)
def test_malformed_projection_collections_and_clock_rejected(changes):
    with pytest.raises(KisPaperPortfolioBudgetError):
        _project(**changes)


def _with_broker_id(state, broker_id):
    fill = state.cumulative_fill
    if fill is not None:
        fill = replace(
            fill,
            identity_ref=fill_identity_ref(
                raw_order_id=broker_id,
                order_at=state.submission_started_at or state.submitted_at,
                symbol=state.intent.symbol,
                exchange=state.intent.exchange,
                side=state.intent.side,
                quantity=state.intent.quantity,
            ),
        )
    return replace(state, broker_order_id=broker_id, cumulative_fill=fill)


def test_same_broker_qty_alias_cannot_manufacture_three_shares_and_authorize_sell_three():
    first = _state("first", filled="1", gross="100")
    alias = _with_broker_id(
        _state("alias", quantity="2", filled="2", gross="200", index=1),
        first.broker_order_id,
    )
    sell = _state("sell", side="sell", quantity="3", filled="3", gross="300", index=2)
    assert first.cumulative_fill.identity_ref != alias.cumulative_fill.identity_ref
    with pytest.raises(KisPaperPortfolioBudgetError, match="broker_order_alias"):
        _project(_owner("owner", first, alias, sell))


def test_forged_cancel_nested_bool_qty_and_float_gross_cannot_release_reservation():
    state = _state("cancel", phase="cancelled", filled="0", remaining="0")
    forged = _tamper(state.cumulative_fill, "quantity", False)
    forged = _tamper(forged, "gross_amount", 0.0)
    assert forged == state.cumulative_fill
    proof = _tamper(_cancel(state), "fill", forged)
    with pytest.raises(KisPaperPortfolioBudgetError, match="cancel_proof_invalid"):
        _project(_owner("owner", state), cancellation_proofs={"cancel": proof})


@pytest.mark.parametrize("scope", ["same_owner", "other_owner", "other_instrument"])
@pytest.mark.parametrize("observation", ["available", "unavailable", "not_observed"])
def test_broker_alias_rejected_across_owner_scope_even_without_current_fills(scope, observation):
    filled = None if observation == "not_observed" else "1"
    first = _state("first", filled=filled, gross="100", observation=observation)
    symbol = "QQQ" if scope == "other_instrument" else "SPY"
    alias = _with_broker_id(
        _state(
            "alias",
            symbol=symbol,
            quantity="2",
            index=1,
            filled=None if filled is None else "2",
            gross="200",
            observation=observation,
        ),
        first.broker_order_id,
    )
    groups = (
        (_owner("owner", first, alias),)
        if scope == "same_owner"
        else (_owner("first-owner", first), _owner("second-owner", alias))
    )
    with pytest.raises(KisPaperPortfolioBudgetError, match="broker_order_alias"):
        _project(*groups)


def test_positive_numeric_broker_padding_cannot_evade_alias_check():
    first = _with_broker_id(_state("first"), "000123")
    alias = _with_broker_id(_state("alias", quantity="2", index=1), "123")
    with pytest.raises(KisPaperPortfolioBudgetError, match="broker_order_alias"):
        _project(_owner("owner", first, alias))


def test_broker_reference_identity_uses_exact_market_date_not_utc_date():
    first = _state("first")
    alias = _with_broker_id(_state("alias", quantity="2", index=1), first.broker_order_id)

    def at(state, hour):
        created = datetime(2026, 9, 23, hour, tzinfo=UTC)
        attempted = created + timedelta(seconds=1)
        return replace(
            state,
            intent=replace(
                state.intent, created_at=created, valid_until=created + timedelta(seconds=20)
            ),
            submission_started_at=attempted,
            submitted_at=attempted,
            updated_at=created + timedelta(seconds=5),
        )

    first, alias = at(first, 1), at(alias, 5)
    result = _project(_owner("owner", first, alias))
    assert result.reserved_buys == 300  # Same UTC date, distinct New York order dates.
    same_market_date = at(alias, 2)
    with pytest.raises(KisPaperPortfolioBudgetError, match="broker_order_alias"):
        _project(_owner("owner", first, same_market_date))


def test_known_broker_reference_without_order_date_is_not_inferred_from_intent_time():
    state = replace(_state("known"), submission_started_at=None, submitted_at=None)
    with pytest.raises(KisPaperPortfolioBudgetError, match="broker_order_date_missing"):
        _project(_owner("owner", state))


@pytest.mark.parametrize(
    "field,bad",
    [
        ("requested_quantity", True),
        ("requested_quantity", 1.0),
        ("quantity", False),
        ("quantity", 0.0),
        ("gross_amount", False),
        ("gross_amount", 0.0),
        ("remaining_quantity", False),
        ("remaining_quantity", 0.0),
        ("observed_at", START.replace(tzinfo=None)),
        ("observed_at", "2026-09-22"),
        ("identity_ref", True),
        ("identity_ref", "malformed"),
        ("requested_quantity", D("1.5")),
        ("quantity", D("0.5")),
        ("remaining_quantity", D("0.5")),
        ("gross_amount", D("NaN")),
    ],
)
def test_cancel_nested_fill_field_types_and_values_are_revalidated(field, bad):
    state = _state("cancel", phase="cancelled", filled="0", remaining="0")
    fill = _tamper(state.cumulative_fill, field, bad)
    proof = _tamper(_cancel(state), "fill", fill)
    with pytest.raises(KisPaperPortfolioBudgetError, match="cancel_proof_invalid"):
        _project(_owner("owner", state), cancellation_proofs={"cancel": proof})
