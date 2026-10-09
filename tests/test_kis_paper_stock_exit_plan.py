"""Synthetic owned EXIT custody, persistence and terminal replay only."""

from __future__ import annotations

import builtins
import copy
import json
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import ROUND_UP, Decimal, Inexact, Rounded, localcontext
from pathlib import Path

import pytest

from test_kis_paper_portfolio_preview import _state as _etf_state
from test_kis_paper_stock_plan import AT, REFS
from test_kis_paper_stock_plan_reservation import (
    _arguments as _entry_arguments,
)
from test_kis_paper_stock_plan_reservation import (
    _observed as _entry_observed,
)
from test_kis_paper_stock_plan_reservation import (
    _persist,
    _refs,
)
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_stock_exit_plan as exit_plan
from thericher_v2.execution import kis_paper_stock_plan as entry_plan
from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient, KisPaperCanaryState
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
from thericher_v2.execution.kis_paper_stock_readonly import (
    KisPaperStockExitAccountSnapshot,
    KisPaperStockExitReads,
)
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperPosition,
)
from thericher_v2.research.decision_receipt import receipt_from_target_exposure_proposal

D = Decimal
NOW = AT + timedelta(seconds=10)
MASK = "****1234-**"


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("synthetic_exit_cannot_use_provider_or_credentials")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(KisPaperCanaryClient, "submit_limit", deny)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config_from_environment", deny)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", deny)


def _position(symbol, quantity, *, exchange="NASD", currency="USD", at=NOW):
    return KisPaperPosition(symbol, exchange, currency, D(quantity), D(10), D(10), at)


def _arguments(
    *other_states,
    filled="10",
    remaining="0",
    pending=False,
    bid="10.009",
    tick=".01",
    positions=None,
    orders=(),
    entry_target=".01",
):
    entry_args = _entry_arguments(*other_states, target=entry_target)
    prepared = entry_plan.build_kis_paper_stock_plan(**entry_args)
    (entry,) = prepared.intents
    state = (
        budget._stock_seed_states(prepared.binding)[entry.run_id]
        if pending
        else _entry_observed(entry, filled=filled, remaining=remaining)
    )
    binding = copy.deepcopy(prepared.binding)
    if budget._terminal(state):
        binding["terminal_evidence"][entry.run_id] = budget._terminal_payload(state)
    proposal = replace(
        entry_args["proposal"],
        action="exit",
        target_exposure=D(0),
        confidence=D(0),
        decided_at=NOW,
        valid_until=NOW + timedelta(minutes=5),
    )
    instrument = entry_args["instrument"]
    if positions is None:
        positions = () if filled == "0" else (_position(instrument.symbol, filled),)
    quote = KisPaperSpyLimitInput(D(10), 3, D(tick), NOW, D(bid), D("10.011"))
    snapshot = KisPaperStockExitAccountSnapshot(
        KisPaperAccountIdentity(MASK, NOW),
        tuple(positions),
        KisPaperOpenOrdersSnapshot(tuple(orders), NOW, True),
        NOW,
    )
    return dict(
        binding=binding,
        states=entry_args["states"] | {entry.run_id: state},
        expected_account_ref=entry_args["expected_account_ref"],
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs=_refs(binding),
        expected_binding_ref="sha256:" + budget._digest(binding),
        expected_masked_account=MASK,
        request_id="synthetic-exit-1",
        input_ref="sha256:" + "e" * 64,
        instrument=instrument,
        proposal=proposal,
        receipt=receipt_from_target_exposure_proposal(proposal, references=REFS),
        reads=KisPaperStockExitReads(
            entry_args["expected_account_ref"], instrument, snapshot, quote, NOW, NOW, 0.0
        ),
        as_of=NOW,
        valid_until=proposal.valid_until,
    )


def _retained(args, result, *, original_refs=False):
    seeds = budget._stock_seed_states(result.binding)
    return args | dict(
        binding=result.binding,
        states=seeds | args["states"],
        expected_owner_refs=args["expected_owner_refs"] if original_refs else _refs(result.binding),
    )


def _reconcile(io, result, **changes):
    keys = (
        "state_root",
        "repository_root",
        "artifact_root",
        "expected_account_ref",
        "expected_basis_ref",
        "expected_binding_ref",
        "input_ref",
        "instrument",
        "request_id",
    )
    return (
        {key: io[key] for key in keys}
        | dict(
            expected_owner_refs=_refs(result.binding),
            expected_plan_ref=result.plan_ref,
            as_of=NOW + timedelta(minutes=6),
        )
        | changes
    )


def _observed(intent, *, filled="0", remaining=None, unavailable=False, phase="submitted"):
    started = intent.created_at + timedelta(seconds=1)
    observed = started + timedelta(seconds=1)
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id="SYNTHETIC-EXIT",
            order_at=started,
            symbol=intent.symbol,
            exchange=intent.exchange,
            side="sell",
            quantity=intent.quantity,
        ),
        intent.quantity,
        D(filled),
        D(filled) * intent.limit_price,
        observed,
        intent.quantity - D(filled) if remaining is None else D(remaining),
    )
    return KisPaperCanaryState(
        intent,
        phase,
        observed + timedelta(seconds=1),
        "reconciliation_unresolved",
        broker_order_id="SYNTHETIC-EXIT",
        submission_started_at=started,
        submitted_at=started,
        cumulative_fill=fill,
        fill_observation_status="unavailable" if unavailable else "available",
        fill_observed_at=observed + timedelta(seconds=1) if unavailable else observed,
    )


def test_builder_pure_whole_owner_exit_preserves_entry_binding_bank_and_other_owners(monkeypatch):
    args = _arguments()
    before = copy.deepcopy(args)
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", lambda *a, **k: pytest.fail("pure_exit_builder_io"))
        patch.setattr(Path, "read_bytes", lambda *a, **k: pytest.fail("pure_exit_builder_io"))
        result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert args == before and result.status == "prepared"
    (intent,) = result.intents
    assert (intent.side, intent.quantity, intent.limit_price) == ("sell", D(10), D(10))
    assert result.reservation == 0 and result.projection.reserved_buys == 0
    assert result.owned_quantity == 10
    assert args["receipt"].instrument_binding_ref != args["instrument"].binding_ref
    for key in args["binding"]:
        if key != "stocks":
            assert result.binding[key] == args["binding"][key]
    before_entry = args["binding"]["stocks"][intent.symbol]
    after_entry = result.binding["stocks"][intent.symbol]
    assert after_entry["instrument_binding_ref"] == before_entry["instrument_binding_ref"]
    assert after_entry["plans"][:-1] == before_entry["plans"]
    assert result.binding["basis_usd"] == "10000" and result.binding["allocated_usd"] == "1000"
    assert {k: v for k, v in _refs(result.binding).items() if not k.startswith("stock-")} == {
        k: v for k, v in args["expected_owner_refs"].items() if not k.startswith("stock-")
    }


@pytest.mark.parametrize(
    ("bid", "tick", "limit"),
    [
        ("10.009", ".01", "10"),
        ("10.011", ".01", "10.01"),
        ("10.007", ".005", "10.005"),
        (".009", ".001", ".009"),
    ],
)
def test_sell_floor_exact_independent_of_decimal_precision_rounding_and_traps(bid, tick, limit):
    args = _arguments(bid=bid, tick=tick)
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = context.traps[Rounded] = True
        result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "prepared" and result.intents[0].limit_price == D(limit)


@pytest.mark.parametrize("action", ["enter", "hold", "reduce", "abstain"])
def test_only_explicit_exit_zero_receipt_can_sell(action):
    args = _arguments()
    args["proposal"] = replace(
        args["proposal"], action=action, target_exposure=D(".01") if action == "enter" else D(0)
    )
    args["receipt"] = receipt_from_target_exposure_proposal(args["proposal"], references=REFS)
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "no_intent" and result.reason == "explicit_exit_required"


@pytest.mark.parametrize("field", ["receipt", "proposal", "reads"])
def test_missing_typed_input_returns_scoped_no_intent(field):
    args = _arguments()
    args[field] = None
    assert exit_plan.build_kis_paper_stock_exit_plan(**args).status == "no_intent"


@pytest.mark.parametrize(
    "kind",
    [
        "entry_receipt",
        "wrong_clock",
        "wrong_source",
        "nonzero",
        "schema",
        "wrong_symbol",
        "future",
        "expired",
    ],
)
def test_exit_receipt_constructor_references_target_and_original_ttl(kind):
    args = _arguments()
    if kind == "entry_receipt":
        args["receipt"] = _entry_arguments()["receipt"]
    elif kind in {"wrong_clock", "wrong_source", "wrong_symbol"}:
        proposal = replace(
            args["proposal"],
            **(
                {"decided_at": NOW - timedelta(seconds=1)}
                if kind == "wrong_clock"
                else {"symbol": "OTHER"}
            ),
        )
        if kind == "wrong_source":
            # Valid but separately referenced EXIT evidence is not the supplied proposal.
            proposal = replace(args["proposal"], action="abstain", input_status="stale")
        args["receipt"] = receipt_from_target_exposure_proposal(proposal, references=REFS)
    elif kind in {"nonzero", "schema"}:
        object.__setattr__(
            args["proposal"],
            "target_exposure" if kind == "nonzero" else "schema_version",
            D(".01") if kind == "nonzero" else True,
        )
    else:
        args["as_of"] = (
            NOW - timedelta(seconds=1) if kind == "future" else args["proposal"].valid_until
        )
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "no_intent" and not result.intents


@pytest.mark.parametrize(
    "kind",
    [
        "digest",
        "mask",
        "loose_mask",
        "instrument",
        "incomplete",
        "stale",
        "future_quote",
        "crossed_quote",
        "zero_tick",
        "wrong_snapshot_type",
        "wrong_quote_type",
    ],
)
def test_read_binding_completeness_freshness_and_invalid_typed_falsifiers(kind):
    args = _arguments()
    reads = args["reads"]
    if kind == "digest":
        args["reads"] = replace(reads, account_ref="b" * 64)
    elif kind in {"mask", "loose_mask"}:
        args["expected_masked_account"] = "****9999-**" if kind == "mask" else "****raw-**"
    elif kind == "instrument":
        args["reads"] = replace(reads, instrument=replace(reads.instrument, symbol="OTHER"))
    elif kind == "incomplete":
        object.__setattr__(reads.snapshot.open_orders, "complete", False)
    elif kind == "stale":
        args["as_of"] = NOW + timedelta(seconds=121)
    elif kind == "future_quote":
        object.__setattr__(reads.quote, "quoted_at", NOW + timedelta(seconds=1))
    elif kind == "crossed_quote":
        object.__setattr__(reads.quote, "best_bid", D(11))
    elif kind == "zero_tick":
        object.__setattr__(reads.quote, "tick_size", D(0))
    else:
        object.__setattr__(
            reads, "snapshot" if kind == "wrong_snapshot_type" else "quote", object()
        )
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "no_intent" and not result.intents


def _delayed_reads(args, quote_at):
    reads = args["reads"]
    captured = NOW + timedelta(seconds=3)
    snapshot = replace(
        reads.snapshot,
        identity=replace(reads.snapshot.identity, captured_at=captured),
        positions=tuple(replace(row, captured_at=captured) for row in reads.positions),
        open_orders=replace(reads.snapshot.open_orders, captured_at=captured),
        captured_at=captured,
    )
    return replace(
        reads,
        snapshot=snapshot,
        quote=replace(reads.quote, quoted_at=quote_at),
        started_at=NOW + timedelta(seconds=2),
        completed_at=NOW + timedelta(seconds=4),
        elapsed_seconds=2.0,
    )


@pytest.mark.parametrize("quote_seconds", [0, 1])
def test_fresh_quote_after_decision_before_read_start_can_prepare_exit(quote_seconds):
    args = _arguments()
    quote_at = NOW + timedelta(seconds=quote_seconds)
    args["reads"] = _delayed_reads(args, quote_at)
    args["as_of"] = args["reads"].completed_at
    assert args["proposal"].decided_at <= quote_at < args["reads"].started_at
    before = copy.deepcopy(args)
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert args == before and result.status == "prepared"
    assert (result.intents[0].side, result.intents[0].quantity, result.intents[0].limit_price) == (
        "sell",
        D(10),
        D(10),
    )
    assert result.intents[0].valid_until == args["proposal"].valid_until


@pytest.mark.parametrize(
    ("quote_seconds", "status"), [(-1, "no_intent"), (4, "prepared"), (5, "no_intent")]
)
def test_quote_decision_completion_and_nonfuture_boundaries_preserved(quote_seconds, status):
    args = _arguments()
    args["reads"] = _delayed_reads(args, NOW + timedelta(seconds=quote_seconds))
    args["as_of"] = args["reads"].completed_at
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == status
    if status == "no_intent":
        assert result.reason == "reads_stale" and not result.intents


@pytest.mark.parametrize(("age_seconds", "status"), [(120, "prepared"), (121, "no_intent")])
def test_quote_before_read_start_still_has_exact_120_second_freshness_boundary(age_seconds, status):
    args = _arguments()
    args["reads"] = _delayed_reads(args, NOW)
    args["as_of"] = NOW + timedelta(seconds=age_seconds)
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == status
    if status == "no_intent":
        assert result.reason == "reads_stale" and not result.intents


def test_quote_before_read_start_does_not_relax_utc_validation():
    args = _arguments()
    args["reads"] = _delayed_reads(args, NOW + timedelta(seconds=1))
    args["as_of"] = args["reads"].completed_at
    object.__setattr__(args["reads"].quote, "quoted_at", NOW.replace(tzinfo=None))
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "no_intent" and not result.intents


@pytest.mark.parametrize("quantity", ["9", "11", "10.5", "1"])
def test_foreign_or_missing_target_inventory_never_adopted_or_oversold(quantity):
    args = _arguments(positions=(_position("SYNSTOCK", quantity),))
    assert exit_plan.build_kis_paper_stock_exit_plan(**args).status == "no_intent"


@pytest.mark.parametrize("kind", ["absent", "wrong_venue", "wrong_currency", "duplicate"])
def test_target_broker_position_scope_exact(kind):
    positions = (
        ()
        if kind == "absent"
        else (_position("SYNSTOCK", "10", exchange="NYSE"),)
        if kind == "wrong_venue"
        else (_position("SYNSTOCK", "10", currency="KRW"),)
        if kind == "wrong_currency"
        else (_position("SYNSTOCK", "10"), _position("SYNSTOCK", "1", exchange="NYSE"))
    )
    assert (
        exit_plan.build_kis_paper_stock_exit_plan(**_arguments(positions=positions)).status
        == "no_intent"
    )


def test_foreign_different_stock_position_does_not_expand_or_block_owned_exit():
    args = _arguments(positions=(_position("SYNSTOCK", "10"), _position("OTHER", "200")))
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "prepared" and result.intents[0].quantity == 10


@pytest.mark.parametrize("same_target", [True, False])
def test_target_open_order_blocks_only_this_instrument(same_target):
    order = KisPaperOpenOrder(
        "open-synthetic",
        "SYNSTOCK" if same_target else "OTHER",
        "NASD",
        "USD",
        "sell",
        D(1),
        D(0),
        D(1),
        D(10),
        NOW,
    )
    result = exit_plan.build_kis_paper_stock_exit_plan(**_arguments(orders=(order,)))
    assert result.status == ("no_intent" if same_target else "prepared")


def test_unresolved_partial_entry_blocks_but_terminal_partial_can_sell_owned_remainder():
    pending = exit_plan.build_kis_paper_stock_exit_plan(**_arguments(filled="3", remaining="7"))
    assert pending.reason == "stock_owner_pending" and not pending.intents
    terminal = exit_plan.build_kis_paper_stock_exit_plan(**_arguments(filled="3", remaining="0"))
    assert terminal.status == "prepared" and terminal.intents[0].quantity == 3


def test_owned_flat_returns_no_intent_without_reopening_or_borrowing_bank():
    args = _arguments(filled="0", pending=True, positions=())
    run, state = next(iter(args["states"].items()))
    state = replace(
        state,
        phase="rejected",
        reason_code="submit_rejected",
        submit_response_category="provider_rejected",
    )
    args["states"][run] = state
    args["binding"]["terminal_evidence"][run] = budget._terminal_payload(state)
    args["expected_binding_ref"] = "sha256:" + budget._digest(args["binding"])
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "no_intent" and result.reason == "stock_owner_flat"


@pytest.mark.parametrize("original_refs", [False, True])
def test_exact_retry_after_expiry_reuses_original_seed_not_new_receipt_market_or_ttl(original_refs):
    args = _arguments()
    first = exit_plan.build_kis_paper_stock_exit_plan(**args)
    retry = _retained(args, first, original_refs=original_refs)
    retry.update(
        proposal=None,
        receipt=None,
        reads=None,
        expected_masked_account=None,
        as_of=NOW + timedelta(days=1),
        valid_until=NOW + timedelta(days=2),
    )
    result = exit_plan.build_kis_paper_stock_exit_plan(**retry)
    assert result.status == "replayed" and result.intents == first.intents
    assert result.binding == first.binding and result.plan_ref == first.plan_ref


@pytest.mark.parametrize(
    "field",
    [
        "input_ref",
        "expected_binding_ref",
        "expected_account_ref",
        "expected_basis_ref",
        "expected_owner_refs",
    ],
)
def test_retry_scope_conflict_rejected(field):
    args = _arguments()
    first = exit_plan.build_kis_paper_stock_exit_plan(**args)
    retry = _retained(args, first)
    retry[field] = (
        {}
        if field == "expected_owner_refs"
        else "f" * 64
        if field == "expected_account_ref"
        else "sha256:" + "f" * 64
    )
    with pytest.raises(_RecoveryRequired):
        exit_plan.build_kis_paper_stock_exit_plan(**retry)


def test_distinct_sell_request_cannot_double_reserve_same_owned_inventory():
    args = _arguments()
    first = exit_plan.build_kis_paper_stock_exit_plan(**args)
    second = _retained(args, first)
    second.update(
        request_id="synthetic-exit-2",
        expected_binding_ref="sha256:" + budget._digest(first.binding),
    )
    result = exit_plan.build_kis_paper_stock_exit_plan(**second)
    assert result.status == "no_intent" and result.reason == "stock_owner_pending"


@pytest.mark.parametrize("seconds", [0, -1, 301])
def test_order_lifetime_never_renews_original_proposal(seconds):
    args = _arguments()
    args["valid_until"] = NOW + timedelta(seconds=seconds)
    with pytest.raises(_RecoveryRequired, match="stock_validity_invalid"):
        exit_plan.build_kis_paper_stock_exit_plan(**args)


def test_shorter_original_ttl_is_not_extended():
    args = _arguments()
    args["proposal"] = replace(args["proposal"], valid_until=NOW + timedelta(seconds=30))
    args["receipt"] = receipt_from_target_exposure_proposal(args["proposal"], references=REFS)
    with pytest.raises(_RecoveryRequired, match="stock_validity_invalid"):
        exit_plan.build_kis_paper_stock_exit_plan(**args)
    args["valid_until"] = args["proposal"].valid_until
    assert (
        exit_plan.build_kis_paper_stock_exit_plan(**args).intents[0].valid_until
        == args["valid_until"]
    )


def test_reservation_seed_only_restart_exact_and_no_new_bank(tmp_path):
    args = _arguments()
    io = _persist(tmp_path, args)
    existing = set(io["state_root"].glob("*.json"))
    result = exit_plan.reserve_kis_paper_stock_exit_plan(**io)
    assert result.status == "reserved" and set(io["state_root"].glob("*.json")) == existing
    retry = io | dict(proposal=None, receipt=None, reads=None, as_of=NOW + timedelta(days=1))
    replay = exit_plan.reserve_kis_paper_stock_exit_plan(**retry)
    assert replay.status == "replayed" and replay.intents == result.intents
    assert replay.plan_ref == result.plan_ref and replay.binding == result.binding


def test_no_intent_reservation_does_not_write_binding_or_sell_file(tmp_path):
    io = _persist(tmp_path, _arguments(positions=()))
    path = io["state_root"] / budget.BUDGET_FILE
    before = path.read_bytes()
    assert exit_plan.reserve_kis_paper_stock_exit_plan(**io).status == "no_intent"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("filled", "remaining", "unavailable", "status", "owned"),
    [
        ("0", None, True, "pending", "10"),
        ("3", None, False, "pending", "7"),
        ("3", None, True, "pending", "7"),
        ("3", "0", False, "reconciled", "7"),
        ("10", "0", False, "reconciled", "0"),
        ("10", "0", True, "reconciled", "0"),
    ],
)
def test_terminal_order_and_current_owned_flat_are_separate_idempotent_facts(
    tmp_path,
    filled,
    remaining,
    unavailable,
    status,
    owned,
):
    io = _persist(tmp_path, _arguments())
    result = exit_plan.reserve_kis_paper_stock_exit_plan(**io)
    (intent,) = result.intents
    state = _observed(intent, filled=filled, remaining=remaining, unavailable=unavailable)
    budget._atomic_json(io["state_root"] / (intent.run_id + ".json"), state.to_dict())
    args = _reconcile(io, result)
    reconciled = exit_plan.reconcile_kis_paper_stock_exit_plan(**args)
    assert reconciled.status == status and reconciled.owned_quantity == D(owned)
    assert reconciled.safe_payload()["inventory"] == (
        "owned_flat" if owned == "0" else "owned_remaining"
    )
    again = exit_plan.reconcile_kis_paper_stock_exit_plan(**args)
    assert again.binding == reconciled.binding and again.projection == reconciled.projection
    assert again.plan_ref == result.plan_ref


def test_exact_cancelled_unfilled_proof_closes_order_not_unsold_inventory(tmp_path):
    io = _persist(tmp_path, _arguments())
    result = exit_plan.reserve_kis_paper_stock_exit_plan(**io)
    intent = result.intents[0]
    state = _observed(intent, filled="0", remaining="0", phase="cancelled")
    budget._atomic_json(io["state_root"] / (intent.run_id + ".json"), state.to_dict())
    args = _reconcile(io, result)
    pending = exit_plan.reconcile_kis_paper_stock_exit_plan(**args)
    assert pending.status == "pending" and pending.owned_quantity == 10
    proof = KisPaperExecutionObservation(
        2, True, "available", state.current_fill, state.fill_observed_at, True
    )
    closed = exit_plan.reconcile_kis_paper_stock_exit_plan(
        **args, cancellation_proofs={intent.run_id: proof}
    )
    assert closed.status == "reconciled" and closed.owned_quantity == 10
    assert closed.binding["terminal_evidence"][intent.run_id]["cancellation"] is not None


def test_zero_remaining_bank_cash_is_not_an_exit_gate():
    args = _arguments(filled="100", entry_target=".10")
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "prepared" and result.intents[0].quantity == 100
    assert result.projection.remaining_cap == result.projection.remaining_gross_cash == 0
    assert not hasattr(args["reads"], "cash") and not hasattr(args["reads"], "orderable")


@pytest.mark.parametrize("unknown", [False, True])
def test_other_lane_pending_buy_consumes_budget_without_global_exit_hold(unknown):
    pending = _etf_state(pending=True)
    args = _arguments(pending)
    if unknown:
        args["states"][pending.intent.run_id] = replace(
            pending,
            phase="outcome_unknown",
            reason_code="reconciliation_unresolved",
            submission_started_at=pending.updated_at,
        )
    result = exit_plan.build_kis_paper_stock_exit_plan(**args)
    assert result.status == "prepared" and result.intents[0].quantity == 10
    assert result.projection.reserved_buys == 100


def test_existing_buy_request_is_not_replayed_as_exit():
    args = _arguments()
    plan = args["binding"]["stocks"][args["instrument"].symbol]["plans"][0]
    args.update(
        request_id=plan["request_id"],
        input_ref=plan["input_ref"],
        expected_binding_ref=plan["parent_binding_ref"],
    )
    with pytest.raises(_RecoveryRequired, match="stock_exit_plan_invalid"):
        exit_plan.build_kis_paper_stock_exit_plan(**args)


def test_reconciliation_does_not_overwrite_or_regress_terminal_fill(tmp_path):
    io = _persist(tmp_path, _arguments())
    result = exit_plan.reserve_kis_paper_stock_exit_plan(**io)
    intent = result.intents[0]
    path = io["state_root"] / (intent.run_id + ".json")
    full = _observed(intent, filled="10", remaining="0")
    budget._atomic_json(path, full.to_dict())
    closed = exit_plan.reconcile_kis_paper_stock_exit_plan(**_reconcile(io, result))
    binding_path = io["state_root"] / budget.BUDGET_FILE
    retained = binding_path.read_bytes()
    budget._atomic_json(path, _observed(intent, filled="3").to_dict())
    with pytest.raises((ValueError, RuntimeError)):
        exit_plan.reconcile_kis_paper_stock_exit_plan(**_reconcile(io, closed))
    assert binding_path.read_bytes() == retained


def test_canonical_replay_rejects_oversized_sell_seed_before_action():
    args = _arguments()
    prepared = exit_plan.build_kis_paper_stock_exit_plan(**args)
    retry = _retained(args, prepared)
    binding = retry["binding"]
    entry = binding["stocks"][args["instrument"].symbol]
    plan = entry["plans"][-1]
    run = prepared.intents[0].run_id
    original = budget._stock_seed_states(binding)[run]
    seed = replace(original, intent=replace(original.intent, quantity=D(11)))
    plan["states"][run] = seed.to_dict()
    retry["states"][run] = seed
    entry["owner_ref"] = next(
        o.fingerprint for o, _ in budget._owners(binding) if o.owner_ref.startswith("stock-")
    )
    retry["expected_owner_refs"] = _refs(binding)
    with pytest.raises(ValueError):
        exit_plan.build_kis_paper_stock_exit_plan(**retry)


def test_wrong_plan_and_out_of_scope_proof_cannot_mutate_reservation(tmp_path):
    io = _persist(tmp_path, _arguments())
    result = exit_plan.reserve_kis_paper_stock_exit_plan(**io)
    path = io["state_root"] / budget.BUDGET_FILE
    before = path.read_bytes()
    with pytest.raises(_RecoveryRequired):
        exit_plan.reconcile_kis_paper_stock_exit_plan(
            **(_reconcile(io, result) | {"expected_plan_ref": "sha256:" + "f" * 64})
        )
    with pytest.raises(_RecoveryRequired, match="stock_proof_scope_invalid"):
        exit_plan.reconcile_kis_paper_stock_exit_plan(
            **_reconcile(io, result), cancellation_proofs={"foreign-run": object()}
        )
    assert path.read_bytes() == before


def test_concurrent_exact_reservation_has_one_canonical_sell_seed(tmp_path):
    io = _persist(tmp_path, _arguments())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: exit_plan.reserve_kis_paper_stock_exit_plan(**io), range(2))
        )
    assert sorted(r.status for r in results) == ["replayed", "reserved"]
    assert results[0].intents == results[1].intents
    binding = json.loads((io["state_root"] / budget.BUDGET_FILE).read_text())
    assert len(binding["stocks"][io["instrument"].symbol]["plans"]) == 2


def test_result_repr_and_safe_payload_have_only_categorical_public_facts():
    result = exit_plan.build_kis_paper_stock_exit_plan(**_arguments())
    encoded = json.dumps(result.safe_payload())
    assert all(type(value) is str for value in result.safe_payload().values())
    for secret in ("SYNSTOCK", MASK, "a" * 64, result.plan_ref, result.intents[0].run_id):
        assert secret not in encoded and secret not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.status = "foreign"
