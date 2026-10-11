"""Synthetic full-book successor/restart parity, never a private bank or broker."""

from __future__ import annotations

import builtins
import copy
import hashlib
import importlib
import socket
import sys
import urllib.request
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from test_kis_paper_portfolio_preview import _state as etf_state
from test_kis_paper_stock_exit_plan import _arguments as exit_arguments
from test_kis_paper_stock_exit_plan import _observed as exit_observed
from test_kis_paper_stock_plan import AT, REFS
from test_kis_paper_stock_plan_reservation import _arguments, _fresh_target, _observed
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_stock_exit_plan as exits
from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient
from thericher_v2.execution.kis_paper_five_session import (
    KisPaperFiveSessionCohort,
    KisPaperFiveSessionCustody,
)
from thericher_v2.execution.kis_paper_five_session_successor import (
    prepare_five_session_successor,
)
from thericher_v2.execution.kis_paper_portfolio_budget import KisPaperPortfolioStateRef
from thericher_v2.execution.kis_paper_stock_plan import KisPaperStockPlan
from thericher_v2.research.decision_receipt import receipt_from_target_exposure_proposal

D = Decimal


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    def deny(*_args, **_kwargs):
        pytest.fail("pure_successor_cannot_use_operational_io")

    for obj, name in (
        (socket, "create_connection"),
        (socket.socket, "connect"),
        (urllib.request, "urlopen"),
        (urllib.request.OpenerDirector, "open"),
        (KisPaperCanaryClient, "submit_limit"),
        (kis_readonly, "load_kis_paper_config"),
        (kis_readonly, "load_kis_paper_config_from_environment"),
        (budget, "load_kis_paper_config_from_environment"),
        (budget, "_load_binding"),
        (budget, "_atomic_json"),
    ):
        monkeypatch.setattr(obj, name, deny)


def arguments(binding=None, states=None, history=(), *, at=AT, other_states=(), **changes):
    base = _arguments(*other_states)
    for row in base["binding"]["orders"]:
        row["closed"] = budget._terminal(base["states"][row["run_id"]])
    base["expected_binding_ref"] = "sha256:" + budget._digest(base["binding"])
    if binding is not None:
        base = _fresh_target(
            base,
            KisPaperStockPlan("fixture", "fixture", binding),
            symbol=base["instrument"].symbol,
            states=states,
            at=at,
        )
    first = at - timedelta(minutes=1)
    opens = tuple(first + timedelta(days=i) for i in (0, 3, 4, 5, 6))
    closes = tuple(t + timedelta(hours=6) for t in opens)
    input_ref = "sha256:" + hashlib.sha256(at.isoformat().encode()).hexdigest()
    proposal = replace(base["proposal"], valid_until=first + timedelta(minutes=10))
    receipt = receipt_from_target_exposure_proposal(
        proposal, references=replace(REFS, input_manifest_ref=input_ref)
    )
    cohort = KisPaperFiveSessionCohort(
        base["instrument"],
        receipt.decision_id,
        "sha256:" + "c" * 64,
        input_ref,
        opens,
        closes,
        proposal.valid_until,
        closes[-1] - timedelta(minutes=10),
    )
    result = {
        k: base[k]
        for k in (
            "binding",
            "states",
            "expected_account_ref",
            "expected_basis_ref",
            "expected_owner_refs",
            "expected_binding_ref",
            "reads",
            "valid_until",
        )
    }
    result.update(
        cohort=cohort,
        expected_cohort_ref=cohort.fingerprint,
        history=history,
        expected_history_refs=tuple(h.fingerprint for h in history),
        input_ref=input_ref,
        proposal=proposal,
        receipt=receipt,
        as_of=at,
        closure_as_of=at,
    )
    result.update(changes)
    return result


def entered(args):
    result = prepare_five_session_successor(**args)
    assert result.status == "prepared", result.safe_payload()
    intent = result.plan.intents[0]
    observed = _observed(intent, filled=str(intent.quantity), remaining="0")
    binding = copy.deepcopy(result.plan.binding)
    binding["terminal_evidence"][intent.run_id] = budget._terminal_payload(observed)
    return binding, args["states"] | {intent.run_id: observed}, result.history


def closed(args, *, price="9"):
    binding, states, history = entered(args)
    cohort = args["cohort"]
    at = cohort.exit_due
    template = exit_arguments()
    proposal = replace(template["proposal"], decided_at=at, valid_until=at + timedelta(minutes=5))
    reads = template["reads"]
    snapshot = reads.snapshot
    reads = replace(
        reads,
        started_at=at,
        completed_at=at,
        quote=replace(reads.quote, quoted_at=at, last=D(price), best_bid=D(price)),
        snapshot=replace(
            snapshot,
            captured_at=at,
            identity=replace(snapshot.identity, captured_at=at),
            positions=tuple(replace(p, captured_at=at) for p in snapshot.positions),
            open_orders=replace(snapshot.open_orders, captured_at=at),
        ),
    )
    exit_args = template | dict(
        binding=binding,
        states=states,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={o.owner_ref: p for o, p in budget._owners(binding)},
        expected_binding_ref="sha256:" + budget._digest(binding),
        request_id="five-exit-" + cohort.fingerprint.removeprefix("sha256:") + "-0",
        input_ref=args["input_ref"],
        proposal=proposal,
        receipt=receipt_from_target_exposure_proposal(proposal, references=REFS),
        reads=reads,
        as_of=at,
        valid_until=proposal.valid_until,
    )
    result = exits.build_kis_paper_stock_exit_plan(**exit_args)
    assert result.status == "prepared", result.safe_payload()
    intent = result.intents[0]
    observed = exit_observed(intent, filled=str(intent.quantity), remaining="0")
    binding = copy.deepcopy(result.binding)
    binding["terminal_evidence"][intent.run_id] = budget._terminal_payload(observed)
    last = history[-1]
    record = replace(
        last,
        custody=KisPaperFiveSessionCustody(
            last.custody.entry, (KisPaperPortfolioStateRef(intent.run_id, intent.fingerprint),)
        ),
        plan_refs=(*last.plan_refs, result.plan_ref),
    )
    return binding, states | {intent.run_id: observed}, (*history[:-1], record)


@pytest.fixture
def successor_args():
    binding, states, history = closed(arguments())
    return arguments(binding, states, history, at=AT + timedelta(days=7))


def test_two_closed_cohorts_then_third_restart_preserves_every_prior_byte(successor_args):
    binding, states, history = closed(successor_args)
    args = arguments(binding, states, history, at=AT + timedelta(days=14))
    before = copy.deepcopy(args)
    result = prepare_five_session_successor(**args)
    assert result.status == "prepared" and len(result.history) == 3
    assert args == before and result.plan.binding["basis_ref"] == binding["basis_ref"]
    symbol = args["cohort"].instrument.symbol
    assert result.plan.binding["stocks"][symbol]["plans"][:-1] == binding["stocks"][symbol]["plans"]
    for key in binding:
        if key != "stocks":
            assert result.plan.binding[key] == binding[key]
    seed = budget._stock_seed_states(result.plan.binding)[result.plan.intents[0].run_id]
    retry = args | dict(
        binding=result.plan.binding,
        states=states | {seed.intent.run_id: seed},
        history=result.history,
        expected_history_refs=tuple(h.fingerprint for h in result.history),
        expected_owner_refs={o.owner_ref: p for o, p in budget._owners(result.plan.binding)},
        proposal=None,
        receipt=None,
        reads=None,
        closure_as_of=None,
        as_of=args["cohort"].session_closes[-1] + timedelta(days=2),
    )
    again = prepare_five_session_successor(**retry)
    assert again.status == "reconcile" and again.pending == result.custody.entry
    assert again.plan.status == "replayed" and again.plan.intents == result.plan.intents
    assert again.plan.binding == result.plan.binding and again.history == result.history


def test_full_original_cash_losses_and_other_reservations_are_not_refunded(successor_args):
    result = prepare_five_session_successor(**successor_args)
    assert result.status == "prepared"
    assert result.projection.basis_usd == D(10000) and result.projection.allocated_usd == D(1000)
    assert result.projection.gross_cash == D(990)
    assert result.plan.reservation == D(100) and result.plan.intents[0].quantity == D(10)
    new_states = budget._stock_seed_states(result.plan.binding) | successor_args["states"]
    projection = budget.project_shared_budget(
        binding=result.plan.binding,
        states=new_states,
        expected_account_ref=successor_args["expected_account_ref"],
        expected_basis_ref=successor_args["expected_basis_ref"],
        expected_owner_refs={o.owner_ref: p for o, p in budget._owners(result.plan.binding)},
        as_of=successor_args["as_of"],
    )
    assert projection.gross_cash == D(990) and projection.remaining_gross_cash == D(890)


@pytest.mark.parametrize("phase", ["submission_started", "outcome_unknown", "submitted"])
def test_prior_unknown_exact_request_requires_its_own_recovery(phase):
    args = arguments()
    result = prepare_five_session_successor(**args)
    intent = result.plan.intents[0]
    state = _observed(intent, phase=phase, filled="3", remaining="7", unavailable=True)
    next_args = arguments(
        result.plan.binding,
        args["states"] | {intent.run_id: state},
        result.history,
        at=AT + timedelta(days=7),
        proposal=None,
        receipt=None,
        reads=None,
    )
    recovery = prepare_five_session_successor(**next_args)
    assert recovery.status == "reconcile" and recovery.reason == "prior_recovery_pending"
    assert recovery.pending == result.custody.entry and recovery.plan is None
    assert recovery.pending_cohort == args["cohort"]


def test_terminal_buy_with_owned_quantity_never_becomes_new_cohort():
    args = arguments()
    binding, states, history = entered(args)
    result = prepare_five_session_successor(
        **arguments(binding, states, history, at=AT + timedelta(days=7))
    )
    assert result.status == "reconcile" and result.reason == "prior_owned_quantity_remaining"
    assert result.plan is None


def test_missing_exact_terminal_evidence_not_inferred_from_flatness(successor_args):
    binding = copy.deepcopy(successor_args["binding"])
    binding["terminal_evidence"].clear()
    result = prepare_five_session_successor(**(successor_args | dict(binding=binding)))
    assert result.status == "reconcile" and result.reason == "prior_terminal_evidence_missing"


@pytest.mark.parametrize("offset", [None, -121, 1])
def test_missing_stale_future_closure_capture_unavailable(successor_args, offset):
    capture = None if offset is None else successor_args["as_of"] + timedelta(seconds=offset)
    result = prepare_five_session_successor(**(successor_args | dict(closure_as_of=capture)))
    assert result.status == "no_intent" and result.reason == "closure_capture_unavailable"


@pytest.mark.parametrize(
    "change",
    [
        "omitted",
        "reordered",
        "wrong_cohort",
        "wrong_input",
        "wrong_plan",
        "wrong_pin",
        "missing_state",
        "omitted_exit",
        "wrong_request",
    ],
)
def test_frozen_history_link_mutations_reject_without_duplicate_plan(successor_args, change):
    args = copy.deepcopy(successor_args)
    item = args["history"][0]
    if change == "omitted":
        args["history"], args["expected_history_refs"] = (), ()
    elif change == "reordered":
        item = replace(
            item,
            custody=KisPaperFiveSessionCustody(item.custody.exits[0], (item.custody.entry,)),
            plan_refs=item.plan_refs[::-1],
        )
        args["history"] = (item,)
        args["expected_history_refs"] = (item.fingerprint,)
    elif change in {"wrong_cohort", "wrong_input"}:
        cohort = (
            replace(item.cohort, entry_decision_id="decision:sha256:" + "e" * 64)
            if change == "wrong_cohort"
            else replace(item.cohort, source_ref="sha256:" + "f" * 64)
        )
        item = replace(item, cohort=cohort, input_ref=cohort.source_ref)
        args["history"], args["expected_history_refs"] = (item,), (item.fingerprint,)
    elif change == "wrong_plan":
        item = replace(item, plan_refs=("sha256:" + "a" * 64, *item.plan_refs[1:]))
        args["history"], args["expected_history_refs"] = (item,), (item.fingerprint,)
    elif change == "wrong_pin":
        args["expected_history_refs"] = ("sha256:" + "0" * 64,)
    elif change == "omitted_exit":
        item = replace(
            item,
            custody=KisPaperFiveSessionCustody(item.custody.entry),
            plan_refs=item.plan_refs[:1],
        )
        args["history"], args["expected_history_refs"] = (item,), (item.fingerprint,)
    elif change == "wrong_request":
        args["binding"]["stocks"][item.cohort.instrument.symbol]["plans"][0]["request_id"] = args[
            "cohort"
        ].entry_request_id
    else:
        args["states"].pop(item.custody.entry.run_id)
    before = copy.deepcopy(args["binding"])
    result = prepare_five_session_successor(**args)
    assert result.status == "no_intent" and result.plan is None
    assert args["binding"] == before


@pytest.mark.parametrize(
    "field", ["expected_cohort_ref", "expected_basis_ref", "expected_binding_ref", "input_ref"]
)
def test_wrong_current_source_or_bank_binding_never_prepares(successor_args, field):
    result = prepare_five_session_successor(**(successor_args | {field: "sha256:" + "0" * 64}))
    assert result.status == "no_intent" and result.plan is None


def test_foreign_same_symbol_broker_quantity_not_adopted(successor_args):
    reads = successor_args["reads"]
    from test_kis_paper_stock_exit_plan import _position

    reads = replace(
        reads,
        snapshot=replace(
            reads.snapshot,
            positions=(
                _position(
                    successor_args["cohort"].instrument.symbol, "1", at=successor_args["as_of"]
                ),
            ),
        ),
    )
    result = prepare_five_session_successor(**(successor_args | dict(reads=reads)))
    assert result.status == "no_intent" and result.plan.reason == "target_inventory_mismatch"
    assert not result.plan.intents


def test_unknown_spy_reserves_without_global_hold():
    seed = etf_state(pending=True, requested="2")
    started = seed.intent.created_at + timedelta(seconds=1)
    spy = replace(
        seed,
        phase="outcome_unknown",
        submission_started_at=started,
        updated_at=started + timedelta(seconds=1),
    )
    binding, states, history = closed(arguments(other_states=(spy,)))
    args = arguments(binding, states, history, at=AT + timedelta(days=7))
    result = prepare_five_session_successor(**args)
    assert result.status == "prepared" and result.projection.reserved_buys == D(200)
    assert result.plan.binding["orders"] == binding["orders"]
    assert args["states"][spy.intent.run_id] == spy


def test_same_closed_request_restart_not_reopened_after_expiry(successor_args):
    binding, states, history = closed(successor_args)
    args = successor_args | dict(
        binding=binding,
        states=states,
        history=history,
        expected_history_refs=tuple(h.fingerprint for h in history),
        expected_owner_refs={o.owner_ref: p for o, p in budget._owners(binding)},
        as_of=AT + timedelta(days=20),
        closure_as_of=None,
        proposal=None,
        receipt=None,
        reads=None,
    )
    result = prepare_five_session_successor(**args)
    assert result.status == "replayed" and result.plan.binding == binding
    assert result.custody == history[-1].custody and len(result.plan.intents) == 1


def test_missing_new_input_local_no_intent_and_zero_capacity_no_replacement(successor_args):
    result = prepare_five_session_successor(
        **(successor_args | dict(proposal=None, receipt=None, reads=None))
    )
    assert result.reason == "input_unavailable" and result.plan is None
    reads = successor_args["reads"]
    reads = replace(reads, cash=replace(reads.cash, available_cash=D(0)))
    result = prepare_five_session_successor(**(successor_args | dict(reads=reads)))
    assert result.status == "no_intent" and not result.plan.intents


def test_initial_empty_history_requires_no_prior_closure_proof():
    result = prepare_five_session_successor(**arguments(closure_as_of=None))
    assert result.status == "prepared" and len(result.history) == 1


def test_current_partial_unknown_exit_recovers_exact_exit_without_new_order(successor_args):
    binding, states, history = closed(successor_args)
    current = history[-1]
    reference = current.custody.exits[0]
    state = states[reference.run_id]
    partial = exit_observed(
        state.intent, filled="4", remaining="6", phase="outcome_unknown", unavailable=True
    )
    binding["terminal_evidence"].pop(reference.run_id)
    args = successor_args | dict(
        binding=binding,
        states=states | {reference.run_id: partial},
        history=history,
        expected_history_refs=tuple(h.fingerprint for h in history),
        expected_owner_refs={o.owner_ref: p for o, p in budget._owners(binding)},
        as_of=current.cohort.session_closes[-1],
        closure_as_of=None,
        proposal=None,
        receipt=None,
        reads=None,
    )
    result = prepare_five_session_successor(**args)
    assert result.status == "reconcile" and result.pending == reference
    assert result.plan.status == "replayed" and result.plan.binding == binding
    assert result.custody == current.custody
    assert all(intent.side == "buy" for intent in result.plan.intents)


def test_closure_capture_cannot_precede_known_selected_state_update(successor_args):
    args = copy.deepcopy(successor_args)
    reference = args["history"][0].custody.exits[0]
    args["states"][reference.run_id] = replace(
        args["states"][reference.run_id], updated_at=args["as_of"]
    )
    capture = args["as_of"] - timedelta(seconds=1)
    args.update(
        closure_as_of=capture,
        reads=replace(args["reads"], started_at=capture, completed_at=capture),
    )
    result = prepare_five_session_successor(**args)
    assert result.status == "no_intent" and result.reason == "closure_capture_before_update"


def test_freshness_is_existing_stock_read_contract_not_extra_closure_rule(successor_args):
    args = copy.deepcopy(successor_args)
    capture = args["as_of"] - timedelta(seconds=121)
    reads, snapshot = args["reads"], args["reads"].snapshot
    reads = replace(
        reads,
        started_at=capture,
        completed_at=capture,
        quote=replace(reads.quote, quoted_at=capture),
        cash=replace(reads.cash, captured_at=capture),
        orderable=replace(reads.orderable, captured_at=capture),
        snapshot=replace(
            snapshot,
            captured_at=capture,
            identity=replace(snapshot.identity, captured_at=capture),
            cash=replace(snapshot.cash, captured_at=capture),
            orderable_funds=replace(snapshot.orderable_funds, captured_at=capture),
            open_orders=replace(snapshot.open_orders, captured_at=capture),
        ),
    )
    proposal = replace(args["proposal"], decided_at=args["as_of"] - timedelta(minutes=5))
    receipt = receipt_from_target_exposure_proposal(
        proposal, references=replace(REFS, input_manifest_ref=args["input_ref"])
    )
    cohort = replace(args["cohort"], entry_decision_id=receipt.decision_id)
    args.update(
        reads=reads,
        closure_as_of=capture,
        proposal=proposal,
        receipt=receipt,
        cohort=cohort,
        expected_cohort_ref=cohort.fingerprint,
    )
    result = prepare_five_session_successor(**args)
    assert result.status == "no_intent" and result.reason == "entry_sizing_unavailable"
    assert result.plan.reason == "reads_stale"


@pytest.mark.parametrize("precision", [2, 28, 80])
def test_caller_context_protects_refs_without_global_decimal_mutation(successor_args, precision):
    with localcontext() as context:
        context.prec = precision
        result = prepare_five_session_successor(**successor_args)
        assert context.prec == precision
    assert result.status == "prepared" and result.plan.intents[0].quantity == D(10)


def test_pure_io_denial_safe_payload_and_lazy_numerical_import(successor_args, monkeypatch):
    def deny(*_args, **_kwargs):
        pytest.fail("pure_successor_file_or_heavy_import")

    original = builtins.__import__

    def light_import(name, *args, **kwargs):
        if name.split(".")[0] in {"numpy", "sklearn", "torch", "pickle"}:
            deny()
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", light_import)
    module = "thericher_v2.execution.kis_paper_five_session_successor"
    parent = importlib.import_module("thericher_v2.execution")
    original_module = sys.modules[module]
    with monkeypatch.context() as isolation:
        isolation.setattr(parent, "kis_paper_five_session_successor", original_module)
        isolation.delitem(sys.modules, module)
        importlib.import_module(module)
    assert sys.modules[module] is original_module
    assert parent.kis_paper_five_session_successor is original_module
    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(Path, "read_bytes", deny)
    result = prepare_five_session_successor(**successor_args)
    assert result.status == "prepared"
    payload = result.safe_payload()
    assert set(payload) == {
        "kind",
        "status",
        "reason",
        "cohort_count",
        "request_count",
        "pending_request_count",
        "scope",
    }
    assert not any(
        k in str(payload)
        for k in (
            successor_args["expected_account_ref"],
            successor_args["input_ref"],
            successor_args["cohort"].instrument.symbol,
        )
    )
