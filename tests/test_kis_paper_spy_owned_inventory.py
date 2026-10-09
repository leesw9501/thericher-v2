from __future__ import annotations

import builtins
import copy
import json
import os
import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryIntent, KisPaperCanaryState
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)

D = Decimal
ACCOUNT = "a" * 64
START = datetime(2026, 10, 7, 14, 30, tzinfo=UTC)
AS_OF = START + timedelta(days=2)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("inventory replay must not access the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def _state(
    index=1,
    *,
    symbol="SPY",
    side="buy",
    quantity="2",
    filled="2",
    gross="120",
    remaining="0",
    phase="submitted",
    observation="available",
):
    run = ("bs-" if symbol == "SPY" else "bq-") + f"{index:064x}"
    created = START + timedelta(minutes=index)
    intent = KisPaperCanaryIntent(
        run,
        "client-" + run,
        "decision-" + run,
        symbol,
        "AMEX" if symbol == "SPY" else "NASD",
        D(quantity),
        D(100),
        created,
        created + timedelta(seconds=20),
        side,
    )
    attempt = created + timedelta(seconds=1)
    known = phase not in {"intent_recorded", "rejected"}
    order_id = "SYNTHETIC-" + str(index) if known else None
    fill = (
        None
        if filled is None
        else KisPaperCumulativeFill(
            fill_identity_ref(
                raw_order_id=order_id,
                order_at=attempt,
                symbol=symbol,
                exchange=intent.exchange,
                side=side,
                quantity=intent.quantity,
            ),
            intent.quantity,
            D(filled),
            D(gross),
            created + timedelta(seconds=2),
            None if remaining is None else D(remaining),
        )
    )
    return KisPaperCanaryState(
        intent,
        phase,
        created + timedelta(seconds=30),
        "submit_rejected"
        if phase == "rejected"
        else "intent_expired"
        if phase == "intent_recorded"
        else "reconciliation_clean",
        broker_order_id=order_id,
        submission_started_at=None if phase == "intent_recorded" else attempt,
        submitted_at=attempt if known else None,
        submit_response_category="provider_rejected" if phase == "rejected" else None,
        cumulative_fill=fill,
        fill_observation_status=observation if fill is not None else "not_observed",
        fill_observed_at=None if fill is None else fill.observed_at,
    )


def _scope(*states, qqq_states=()):
    def record(state):
        return dict(run_id=state.intent.run_id, intent_ref=state.intent.fingerprint, closed=True)

    binding = {
        "version": 2,
        "account_ref": ACCOUNT,
        "basis_usd": "10000",
        "allocated_usd": "1000",
        "at": START.isoformat(),
        "orders": list(map(record, states)),
        "basis_ref": None,
        "spy_owner_ref": None,
        "qqq": {
            "cycle_id": "synthetic-unit",
            "owner_ref": None,
            "orders": list(map(record, qqq_states)),
        },
        "legacy_spy": None,
        "terminal_evidence": {
            state.intent.run_id: {"state": state.to_dict(), "cancellation": None}
            for state in (*states, *qqq_states)
        },
    }
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owner(
        binding, "spy-baseline", "SPY", "AMEX", binding["orders"]
    ).fingerprint
    binding["qqq"]["owner_ref"] = budget._owner(
        binding,
        budget._owner_id(binding, binding["qqq"]["cycle_id"]),
        "QQQ",
        "NASD",
        binding["qqq"]["orders"],
    ).fingerprint
    return dict(
        binding=binding,
        states={state.intent.run_id: state for state in states},
        expected_account_ref=ACCOUNT,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_ref=binding["spy_owner_ref"],
        as_of=AS_OF,
    )


def test_exact_current_account_owned_inventory_and_closed_safe_payload():
    state = _state()
    result = budget.project_spy_owned_inventory(**_scope(state))
    assert (result.quantity, result.entry_cost, result.reserved_buys) == (D(2), D(120), D(0))
    assert result.safe_payload() == {
        "kind": "kis_paper_spy_owned_inventory_replay_v1",
        "source": "kis_paper",
        "instrument": "SPY",
        "status": "known_owned_inventory",
        "order_count": 1,
        "matched_fill_count": 1,
        "retained_fill_count": 0,
        "limitation": "owned_state_attribution_not_current_broker_state_or_pnl",
    }
    assert type(result).__repr__ is object.__repr__
    assert repr(result) == object.__repr__(result)
    text = json.dumps(result.safe_payload())
    for private in (
        ACCOUNT,
        state.intent.run_id,
        state.intent.fingerprint,
        state.broker_order_id,
        "120",
        "quantity",
        "entry_cost",
        "reserved_buys",
        "gross_pnl",
        "net_pnl",
        "flat",
    ):
        assert private not in text
    with pytest.raises(FrozenInstanceError):
        result.quantity = D(0)


@pytest.mark.parametrize("leak", ["120", "quantity=2", "SYNTHETIC-ORDER"])
def test_default_repr_assertion_rejects_leaked_amount_field_or_identifier(monkeypatch, leak):
    result = budget.project_spy_owned_inventory(**_scope(_state()))
    monkeypatch.setattr(type(result), "__repr__", lambda value: object.__repr__(value) + leak)
    assert leak not in json.dumps(result.safe_payload())
    with pytest.raises(AssertionError):
        assert repr(result) == object.__repr__(result)


def test_every_spy_state_is_counted_once_and_sell_does_not_report_profit():
    buy = _state()
    second_buy = _state(2, quantity="1", filled="1", gross="80")
    sell = _state(3, side="sell", quantity="1", filled="1", gross="90")
    result = budget.project_spy_owned_inventory(**_scope(buy, second_buy, sell))
    assert result.quantity == D(2)
    assert result.entry_cost >= D(400) / 3
    assert result.reserved_buys == 0
    assert result.order_count == result.matched_fill_count == 3
    assert "profit" not in json.dumps(result.safe_payload())


@pytest.mark.parametrize("phase", ("rejected", "intent_recorded"))
def test_proven_unfilled_terminal_and_empty_scope_never_adopt_holdings(phase):
    state = _state(phase=phase, filled=None)
    for args in (_scope(state), _scope()):
        result = budget.project_spy_owned_inventory(**args)
        assert result.quantity == result.entry_cost == result.reserved_buys == 0
        assert result.matched_fill_count == 0
        assert result.safe_payload()["status"] == "no_known_owned_inventory"
        assert "flat" not in result.safe_payload()


def test_completed_sell_releases_entry_cost_without_returning_realized_pnl():
    buy, sell = _state(), _state(2, side="sell", gross="160")
    result = budget.project_spy_owned_inventory(**_scope(buy, sell))
    assert result.quantity == result.entry_cost == result.reserved_buys == 0
    assert result.matched_fill_count == 2
    assert set(result.safe_payload()) == set(
        budget.project_spy_owned_inventory(**_scope(buy)).safe_payload()
    )


def test_partial_exhausted_fill_keeps_existing_conservative_reservation():
    state = _state(filled="1", gross="60", remaining="0")
    result = budget.project_spy_owned_inventory(**_scope(state))
    assert (result.quantity, result.entry_cost, result.reserved_buys) == (D(1), D(60), D(100))
    assert result.matched_fill_count == 1


def _cancelled_scope():
    state = _state(phase="cancelled", filled="0", gross="0", remaining="0")
    args = _scope(state)
    proof = KisPaperExecutionObservation(
        row_count=2,
        same_day_order_id_seen=True,
        status="available",
        fill=state.current_fill,
        observed_at=state.fill_observed_at,
        cancellation_confirmed=True,
    )
    args["binding"]["terminal_evidence"][state.intent.run_id] = budget._terminal_payload(
        state, proof
    )
    return state, args


def test_exact_zero_fill_cancellation_survives_later_unavailable_without_io():
    state, args = _cancelled_scope()
    original = budget.project_spy_owned_inventory(**args)
    assert original.quantity == original.entry_cost == original.reserved_buys == 0
    args["states"][state.intent.run_id] = replace(
        state,
        updated_at=START + timedelta(days=1),
        fill_observed_at=START + timedelta(days=1),
        fill_observation_status="unavailable",
    )
    before = copy.deepcopy(args)
    assert budget.project_spy_owned_inventory(**args) == original
    assert args == before and original.matched_fill_count == 0


@pytest.mark.parametrize(
    "change", ("missing", "row_count", "seen", "confirmed", "fill", "phase", "current_fill")
)
def test_cancellation_requires_exact_supported_evidence_not_a_closed_marker(change):
    state, args = _cancelled_scope()
    evidence = args["binding"]["terminal_evidence"][state.intent.run_id]
    proof = evidence["cancellation"]
    if change == "missing":
        evidence["cancellation"] = None
    elif change == "row_count":
        proof["row_count"] = True
    elif change == "seen":
        proof["same_day_order_id_seen"] = 1
    elif change == "confirmed":
        proof["cancellation_confirmed"] = 1
    elif change == "fill":
        proof["fill"]["identity_ref"] = "sha256:" + "f" * 64
    elif change == "phase":
        evidence["state"]["phase"] = "submitted"
    else:
        args["states"][state.intent.run_id] = replace(
            state,
            cumulative_fill=None,
            fill_observation_status="unavailable",
            updated_at=START + timedelta(days=1),
            fill_observed_at=START + timedelta(days=1),
        )
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize("observation", ("unavailable", "absent"))
def test_later_unavailable_read_retains_exact_proven_cumulative_fill(observation):
    state = _state()
    args = _scope(state)
    original = budget.project_spy_owned_inventory(**args)
    args["states"][state.intent.run_id] = replace(
        state,
        updated_at=START + timedelta(days=1),
        fill_observed_at=START + timedelta(days=1),
        fill_observation_status=observation,
    )
    result = budget.project_spy_owned_inventory(**args)
    assert (result.quantity, result.entry_cost, result.reserved_buys) == (
        original.quantity,
        original.entry_cost,
        original.reserved_buys,
    )
    assert result.matched_fill_count == result.retained_fill_count == 1
    assert result.safe_payload()["status"] == "known_owned_inventory"


@pytest.mark.parametrize(
    "field,bad",
    (
        ("expected_account_ref", "b" * 64),
        ("expected_account_ref", True),
        ("expected_basis_ref", "sha256:" + "b" * 64),
        ("expected_basis_ref", None),
        ("expected_owner_ref", "sha256:" + "b" * 64),
        ("expected_owner_ref", True),
    ),
)
def test_independent_expected_arguments_cannot_be_flags_or_recomputed_custody(field, bad):
    args = _scope(_state())
    args[field] = bad
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize(
    "field,value",
    (
        ("basis_usd", "20000"),
        ("allocated_usd", "2000"),
        ("at", (START - timedelta(days=1)).isoformat()),
        ("account_ref", "b" * 64),
    ),
)
def test_replacing_binding_and_its_internal_digest_cannot_reset_frozen_basis(field, value):
    args = _scope(_state())
    args["binding"][field] = value
    if field == "basis_usd":
        args["binding"]["allocated_usd"] = "2000"
    if field == "allocated_usd":
        args["binding"]["basis_usd"] = "20000"
    args["binding"]["basis_ref"] = budget._basis(args["binding"]).fingerprint
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize("allocated", ("999", "1001", "NaN", True, 1000.0))
def test_shared_allocation_remains_exact_initial_tenth(allocated):
    args = _scope(_state())
    args["binding"]["allocated_usd"] = allocated
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize(
    "change",
    (
        "version",
        "bool_version",
        "missing",
        "extra",
        "legacy",
        "qqq_shape",
        "qqq_owner",
        "unknown_terminal",
        "orders_shape",
    ),
)
def test_v2_envelope_is_exact_and_legacy_inventory_is_not_adopted(change):
    args = _scope(_state())
    binding = args["binding"]
    if change == "version":
        binding["version"] = 1
    elif change == "bool_version":
        binding["version"] = True
    elif change == "missing":
        del binding["legacy_spy"]
    elif change == "extra":
        binding["holdings"] = {"SPY": "999"}
    elif change == "legacy":
        binding["legacy_spy"] = {"account_ref": "b" * 64}
    elif change == "qqq_shape":
        binding["qqq"]["extra"] = True
    elif change == "qqq_owner":
        binding["qqq"]["owner_ref"] = "sha256:" + "f" * 64
    elif change == "unknown_terminal":
        binding["terminal_evidence"]["unbound"] = {}
    else:
        binding["orders"][0]["closed"] = "true"
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize(
    "change",
    ("missing", "foreign", "qqq", "raw_state", "duplicate", "fingerprint", "run_id", "symbol"),
)
def test_all_and_only_owned_spy_states_and_exact_intent_links_are_required(change):
    state = _state()
    args = _scope(state)
    key = state.intent.run_id
    if change == "missing":
        args["states"].clear()
    elif change == "foreign":
        foreign = _state(2)
        args["states"][foreign.intent.run_id] = foreign
    elif change == "qqq":
        foreign = _state(2, symbol="QQQ")
        args["states"][foreign.intent.run_id] = foreign
    elif change == "raw_state":
        args["states"][key] = state.to_dict()
    elif change == "duplicate":
        args["binding"]["orders"].append(copy.deepcopy(args["binding"]["orders"][0]))
    else:
        intent = replace(
            state.intent,
            **(
                {"limit_price": D(101)}
                if change == "fingerprint"
                else {"run_id": "bs-" + "f" * 64}
                if change == "run_id"
                else {"symbol": "QQQ", "exchange": "NASD"}
            ),
        )
        args["states"][key] = replace(
            state,
            intent=intent,
            cumulative_fill=None,
            fill_observation_status="not_observed",
            fill_observed_at=None,
        )
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize(
    "observation", ("conflict", "identity_mismatch", "ambiguous", "fields_invalid")
)
def test_conflicting_or_unknown_observation_is_a_scoped_replay_failure(observation):
    state = _state()
    args = _scope(state)
    args["states"][state.intent.run_id] = replace(state, fill_observation_status=observation)
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError, match="outcome_unresolved"):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize("phase", ("submission_started", "outcome_unknown", "cancel_started"))
def test_unknown_self_outcome_cannot_use_a_closed_marker_as_proof(phase):
    state = _state()
    args = _scope(state)
    args["states"][state.intent.run_id] = replace(state, phase=phase)
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError, match="outcome_unresolved"):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize(
    "change",
    (
        "open",
        "missing_terminal",
        "partial_unknown",
        "zero_unknown",
        "regressed",
        "changed_amount",
        "terminal_bool_schema",
        "terminal_extra_intent",
        "terminal_unknown",
        "terminal_unavailable",
    ),
)
def test_terminal_evidence_must_be_exact_proven_and_consistent(change):
    state = _state()
    args = _scope(state)
    key = state.intent.run_id
    saved = args["binding"]["terminal_evidence"][key]["state"]
    if change == "open":
        args["binding"]["orders"][0]["closed"] = False
    elif change == "missing_terminal":
        args["binding"]["terminal_evidence"].clear()
    elif change == "partial_unknown":
        state = _state(filled="1", gross="60", remaining=None)
        args = _scope(state)
    elif change == "zero_unknown":
        state = _state(filled="0", gross="0", remaining=None)
        args = _scope(state)
    elif change in {"regressed", "changed_amount"}:
        fill = replace(
            state.cumulative_fill,
            quantity=D(1) if change == "regressed" else D(2),
            gross_amount=D(60) if change == "regressed" else D(121),
        )
        args["states"][key] = replace(state, cumulative_fill=fill)
    elif change == "terminal_bool_schema":
        saved["schema_version"] = True
    elif change == "terminal_extra_intent":
        saved["intent"]["inherited_account"] = "b" * 64
    elif change == "terminal_unknown":
        saved["phase"] = "outcome_unknown"
    else:
        saved["fill_observation_status"] = "unavailable"
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


def test_unowned_sell_and_duplicate_broker_alias_cannot_create_or_release_inventory():
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**_scope(_state(side="sell")))
    first = _state()
    second = _state(2)
    fill = replace(second.cumulative_fill, identity_ref=first.cumulative_fill.identity_ref)
    second = replace(second, broker_order_id=first.broker_order_id, cumulative_fill=fill)
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**_scope(first, second))


@pytest.mark.parametrize("change", ("client_id", "decision_id", "reversed", "over_budget"))
def test_existing_owner_arithmetic_enforces_identity_order_and_original_cap(change):
    first, second = _state(), _state(2)
    if change == "client_id":
        second = replace(
            second, intent=replace(second.intent, client_order_id=first.intent.client_order_id)
        )
    elif change == "decision_id":
        second = replace(
            second, intent=replace(second.intent, decision_id=first.intent.decision_id)
        )
    if change == "reversed":
        args = _scope(second, first)
    elif change == "over_budget":
        args = _scope(_state(quantity="21", filled="21", gross="1050"))
    else:
        args = _scope(first, second)
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


@pytest.mark.parametrize(
    "target,field,bad",
    (
        ("state", "schema_version", True),
        ("state", "cancel_after_submit", 1),
        ("state", "updated_at", "PRIVATE-SENTINEL"),
        ("intent", "schema_version", True),
        ("intent", "quantity", True),
        ("fill", "gross_amount", D("NaN")),
        ("fill", "identity_ref", "PRIVATE-SENTINEL"),
        ("fill", "remaining_quantity", True),
    ),
)
def test_typed_facts_are_revalidated_before_retained_terminal_normalization(target, field, bad):
    state = _state()
    args = _scope(state)
    forged = copy.deepcopy(state)
    value = {"state": forged, "intent": forged.intent, "fill": forged.cumulative_fill}[target]
    object.__setattr__(value, field, bad)
    args["states"][state.intent.run_id] = forged
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError) as error:
        budget.project_spy_owned_inventory(**args)
    assert "PRIVATE-SENTINEL" not in str(error.value)
    assert state.intent.run_id not in str(error.value)


@pytest.mark.parametrize("as_of", (None, START, datetime(2026, 10, 10)))
def test_fixed_asof_is_required_and_future_states_are_rejected(as_of):
    args = _scope(_state())
    args["as_of"] = as_of
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError):
        budget.project_spy_owned_inventory(**args)


def test_only_spy_owner_is_delegated_and_qqq_basis_and_inputs_are_unchanged(monkeypatch):
    spy = _state()
    qqq_buy = _state(10, symbol="QQQ", quantity="1", filled="1", gross="70")
    qqq_sell = _state(11, symbol="QQQ", side="sell", quantity="1", filled="1", gross="69")
    args = _scope(spy, qqq_states=(qqq_buy, qqq_sell))
    before = copy.deepcopy(args)
    calls = []
    original = budget.project_kis_paper_portfolio_budget

    def capture(**kwargs):
        calls.append(kwargs)
        assert len(kwargs["owners"]) == 1 and kwargs["owners"][0].owner_ref == "spy-baseline"
        assert set(kwargs["states"]) == {spy.intent.run_id}
        return original(**kwargs)

    monkeypatch.setattr(budget, "project_kis_paper_portfolio_budget", capture)
    result = budget.project_spy_owned_inventory(**args)
    assert result.quantity == D(2) and result.entry_cost == D(120)
    assert args == before and len(calls) == 1
    assert budget.project_spy_owned_inventory(**args) == result


def test_no_file_store_config_environment_or_broker_io_and_no_input_mutation(monkeypatch):
    args = _scope(_state())
    before = copy.deepcopy(args)

    def forbidden(*args, **kwargs):
        pytest.fail("pure SPY helper must not access mutable I/O")

    with monkeypatch.context() as guard:
        for name in (
            "_load_binding",
            "_state",
            "project_budget",
            "_atomic_json",
            "load_kis_paper_config_from_environment",
        ):
            guard.setattr(budget, name, forbidden)
        guard.setattr(budget.KisPaperCanaryStateStore, "read", forbidden)
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(Path, "open", forbidden)
        guard.setattr(Path, "read_text", forbidden)
        guard.setattr(Path, "write_text", forbidden)
        guard.setattr(os, "getenv", forbidden)
        result = budget.project_spy_owned_inventory(**args)
    assert args == before and result.matched_fill_count == 1


def test_duplicate_json_rejection_is_caller_owned_not_hidden_in_helper():
    args = _scope(_state())
    raw = json.dumps(args["binding"])[:-1] + ', "version": 2}'

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    with pytest.raises(ValueError, match="duplicate_json_key"):
        json.loads(raw, object_pairs_hook=unique)
    args["binding"] = raw
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError, match="binding_invalid"):
        budget.project_spy_owned_inventory(**args)


def test_low_precision_caller_does_not_change_exact_budget_or_fill_projection():
    args = _scope(_state())
    expected = budget.project_spy_owned_inventory(**args)
    with localcontext() as context:
        context.prec = 6
        assert budget.project_spy_owned_inventory(**args) == expected


@pytest.mark.parametrize(
    "field,bad",
    (
        ("quantity", True),
        ("entry_cost", D("NaN")),
        ("reserved_buys", D(-1)),
        ("order_count", ACCOUNT),
        ("matched_fill_count", True),
        ("retained_fill_count", 2),
    ),
)
def test_result_safe_payload_cannot_echo_invalid_constructor_fields(field, bad):
    args = dict(
        quantity=D(2),
        entry_cost=D(120),
        reserved_buys=D(0),
        order_count=1,
        matched_fill_count=1,
        retained_fill_count=0,
    )
    args[field] = bad
    with pytest.raises(budget.KisPaperSpyOwnedInventoryError, match="result_invalid"):
        budget.KisPaperSpyOwnedInventory(**args)
