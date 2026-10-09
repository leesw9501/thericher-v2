"""Synthetic session decisions feed one retained bank; no model or broker I/O."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_kis_paper_stock_plan_reservation import _arguments, _fresh_target, _persist, _refs
from test_kis_stock_session_decision import KEYS, decide, make_case
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_stock_plan as stock
from thericher_v2.execution import kis_paper_stock_session_recovery as recovery
from thericher_v2.execution.kis_paper_stock_execute import KisPaperStockExecutionBinding
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.research import kis_stock_session_decision as session

D = Decimal


def session_case(day):
    envelope, bars = make_case(day)
    instruments = {
        key: session.SessionInstrument(key, "SYN" + chr(65 + i // 26) + chr(65 + i % 26))
        for i, key in enumerate(KEYS)
    }
    envelope = replace(
        envelope,
        instruments=instruments,
        instrument_map_sha256=session.instrument_map_sha256(instruments),
    )
    return envelope, {
        (key, day): replace(bar, symbol=instruments[key].symbol) for (key, day), bar in bars.items()
    }


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic integration cannot call a provider or load credentials")

    for name in ("submit_limit", "cancel_order", "reconcile"):
        monkeypatch.setattr(canary.KisPaperCanaryClient, name, forbidden)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", forbidden)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", forbidden)


def plan_arguments(base, prior, decision, *, states=None):
    opened = decision.envelope.plan.open_clocks[-1]
    instrument = KisPaperStockInstrument(
        decision.proposal.symbol, decision.receipt.instrument_binding_ref
    )
    args = _fresh_target(
        base,
        prior,
        symbol=instrument.symbol,
        at=opened + timedelta(minutes=1),
        states=states,
    )
    return args | dict(
        instrument=instrument,
        reads=replace(args["reads"], instrument=instrument),
        proposal=decision.proposal,
        receipt=decision.receipt,
        input_ref=decision.envelope.binding_sha256,
    )


def routed(args, plan, decision, state=None, *, as_of=None):
    intent = plan.intents[0]
    seed = budget._stock_seed_states(plan.binding)[intent.run_id]
    proof = KisPaperStockExecutionBinding(
        state_root=Path("C:/synthetic-only-unused-state"),
        instrument=args["instrument"],
        account_ref=args["expected_account_ref"],
        basis_ref=args["expected_basis_ref"],
        owner_refs=tuple(_refs(plan.binding).items()),
        binding_ref="sha256:" + budget._digest(plan.binding),
        request_id=args["request_id"],
        parent_binding_ref=args["expected_binding_ref"],
        input_ref=args["input_ref"],
        plan_ref=plan.plan_ref,
        run_id=intent.run_id,
        intent_ref=intent.fingerprint,
    )
    return recovery.plan_stock_session_recovery(
        proof=proof,
        seed=seed,
        state=state or seed,
        session_open=decision.envelope.plan.open_clocks[-1],
        session_close=decision.envelope.plan.close_clocks[-1],
        as_of=as_of or args["as_of"],
    )


@pytest.mark.parametrize("unknown", [False, True])
def test_different_session_top1_keeps_original_bank_and_exact_prior_request(unknown):
    first_decision = decide(
        session_case(date(2026, 10, 12)),
        scorer=lambda batch: {key: float(key == KEYS[3]) for key in batch.keys},
    )
    second_decision = decide(
        session_case(date(2026, 11, 27)),
        scorer=lambda batch: {key: float(key == KEYS[7]) for key in batch.keys},
    )
    assert first_decision.status == second_decision.status == "prepared"
    assert first_decision.proposal.symbol != second_decision.proposal.symbol
    base = _arguments()
    original_bank = copy.deepcopy(base["binding"])
    first_args = plan_arguments(base, SimpleNamespace(binding=original_bank), first_decision)
    first = stock.build_kis_paper_stock_plan(**first_args)
    assert first.status == "prepared" and first.reservation == D(100)
    assert routed(first_args, first, first_decision).action == "submit_exact_seed"
    old_intent = first.intents[0]
    old_seed = budget._stock_seed_states(first.binding)[old_intent.run_id]
    old_state = (
        replace(
            old_seed,
            phase="outcome_unknown",
            updated_at=old_intent.created_at + timedelta(seconds=1),
            submission_started_at=old_intent.created_at + timedelta(seconds=1),
            reason_code="submit_transport_unknown",
        )
        if unknown
        else old_seed
    )
    frozen_first = copy.deepcopy(first.binding)
    second_args = plan_arguments(
        base, first, second_decision, states={old_intent.run_id: old_state}
    )
    second = stock.build_kis_paper_stock_plan(**second_args)
    assert second.status == "prepared" and second.reservation == D(100)
    assert second.binding["basis_usd"] == original_bank["basis_usd"] == "10000"
    assert second.binding["allocated_usd"] == original_bank["allocated_usd"] == "1000"
    assert all(
        second.binding[key] == value for key, value in original_bank.items() if key != "version"
    )
    assert second.binding["stocks"][old_intent.symbol] == frozen_first["stocks"][old_intent.symbol]
    assert first.binding == frozen_first and base["binding"] == original_bank
    assert _refs(second.binding).items() >= _refs(first.binding).items()
    assert second.intents[0].created_at != old_intent.created_at
    assert second.intents[0].valid_until < second_decision.proposal.valid_until
    assert second_decision.proposal.valid_until.hour == 18  # Official early close.
    states = budget._stock_seed_states(second.binding) | {old_intent.run_id: old_state}
    projection = budget.project_shared_budget(
        binding=second.binding,
        states=states,
        expected_account_ref=base["expected_account_ref"],
        expected_basis_ref=base["expected_basis_ref"],
        expected_owner_refs=_refs(second.binding),
        as_of=second_args["as_of"],
    )
    assert projection.reserved_buys == D(200) and projection.remaining_gross_cash == D(800)
    assert len(projection.stocks_by_owner) == 7  # Five legacy plus two stock owners.
    assert routed(second_args, second, second_decision).action == "submit_exact_seed"
    old_recovery = routed(first_args, first, first_decision, old_state, as_of=second_args["as_of"])
    assert old_recovery.action == ("reconcile_unknown" if unknown else "expired_unsubmitted")
    assert old_recovery.intent == old_intent
    assert old_recovery.original_valid_until == old_intent.valid_until
    retry = first_args | dict(
        binding=second.binding,
        states=states,
        expected_owner_refs=_refs(second.binding),
        as_of=second_args["as_of"],
        proposal=None,
        receipt=None,
        reads=None,
    )
    exact = stock.build_kis_paper_stock_plan(**retry)
    assert exact.status == "replayed" and exact.intents == first.intents
    assert exact.plan_ref == first.plan_ref and exact.binding == second.binding


def test_durable_second_session_restart_does_not_replace_unknown_prior_intent(tmp_path):
    first_decision = decide(
        session_case(date(2026, 10, 12)),
        scorer=lambda batch: {key: float(key == KEYS[3]) for key in batch.keys},
    )
    second_decision = decide(
        session_case(date(2026, 11, 27)),
        scorer=lambda batch: {key: float(key == KEYS[7]) for key in batch.keys},
    )
    base = _arguments()
    args = plan_arguments(base, SimpleNamespace(binding=base["binding"]), first_decision)
    first_io = _persist(tmp_path, args)
    first = stock.reserve_kis_paper_stock_plan(**first_io)
    assert first.status == "reserved"
    intent = first.intents[0]
    unknown = canary.KisPaperCanaryState(
        intent,
        "outcome_unknown",
        intent.created_at + timedelta(seconds=1),
        "submit_transport_unknown",
        submission_started_at=intent.created_at + timedelta(seconds=1),
    )
    old_path = first_io["state_root"] / (intent.run_id + ".json")
    budget._atomic_json(old_path, unknown.to_dict())
    old_raw = old_path.read_bytes()
    fresh = plan_arguments(base, first, second_decision, states={intent.run_id: unknown})
    second_io = fresh | {
        name: first_io[name] for name in ("state_root", "repository_root", "artifact_root")
    }
    second_io = {key: value for key, value in second_io.items() if key not in {"binding", "states"}}
    second = stock.reserve_kis_paper_stock_plan(**second_io)
    assert second.status == "reserved"
    frozen_bank = (first_io["state_root"] / budget.BUDGET_FILE).read_bytes()
    restarted = stock.reserve_kis_paper_stock_plan(
        **(
            second_io
            | dict(
                as_of=fresh["as_of"] + timedelta(days=3), proposal=None, receipt=None, reads=None
            )
        )
    )
    assert restarted.status == "replayed" and restarted.intents == second.intents
    assert (first_io["state_root"] / budget.BUDGET_FILE).read_bytes() == frozen_bank
    assert old_path.read_bytes() == old_raw
    assert (
        budget._load_binding(first_io["state_root"])["stocks"][intent.symbol]
        == first.binding["stocks"][intent.symbol]
    )
    projection = budget.project_budget(
        first_io["state_root"],
        second.binding,
        as_of=fresh["as_of"],
        stock_symbol=second.intents[0].symbol,
    )
    assert projection.reserved_buys == D(200) and projection.remaining_gross_cash == D(800)
