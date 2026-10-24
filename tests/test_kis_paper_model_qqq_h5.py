"""Invented QQQ custody/read projections only; no clients, private data or IO."""

import copy
import hashlib
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from test_kis_paper_portfolio_preview import _scope as old_scope
from test_kis_paper_stock_plan import _state as old_state
from test_model_paper_weights_h5 import _metadata, _prepared
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_model_qqq_h5 as core
from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryClient, KisPaperCanaryState
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    fill_identity_ref,
)
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
from thericher_v2.research.model_paper_weights import (
    MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    ModelPaperWeightRow,
    prepare_model_paper_weights_input,
)

D = Decimal
PIN = "sha256:" + "a" * 64
SOURCE = "sha256:" + "b" * 64
MASKED = "****5678-**01"


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("pure_qqq_h5_must_not_use_operational_IO")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", denied)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config", denied)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", denied)
    monkeypatch.setattr(KisPaperCanaryClient, "submit_limit", denied)
    monkeypatch.setattr(budget, "_load_binding", denied)
    monkeypatch.setattr(budget, "_atomic_json", denied)


def value(first=date(2026, 10, 26), last=date(2026, 10, 30)):
    original = _prepared(first, last)
    rows = tuple(
        ModelPaperWeightRow(i, route, True, D(weight))
        for i, (route, weight) in enumerate(
            (("SPY/AMS", "0.0"), ("QQQ/NAS", "1.0"), ("IWM/AMS", "0.0"))
        )
    )
    return prepare_model_paper_weights_input(
        _metadata(original.entry_session, original.exit_session, rows),
        entry_session=original.entry_session,
        exit_session=original.exit_session,
        profile=MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    )


def _refresh(binding):
    for owner, _ in budget._owners(binding):
        if owner.owner_ref == "spy-baseline":
            binding["spy_owner_ref"] = owner.fingerprint
        elif owner.owner_ref.startswith("qqq-"):
            binding["qqq"]["owner_ref"] = owner.fingerprint
        elif owner.owner_ref.startswith("portfolio-"):
            binding["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint


def _pins(binding):
    return dict(
        expected_account_ref=binding["account_ref"],
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={o.owner_ref: r for o, r in budget._owners(binding)},
        expected_binding_ref=core._ref(binding),
    )


def _legacy_state(run, **kwargs):
    state = old_state("invented-" + run[-4:], **kwargs)
    return replace(state, intent=replace(state.intent, run_id=run))


def _boundary(binding, states, v, at):
    return core.QqqH5WriterBoundary(
        SOURCE,
        core.qqq_h5_custody_ref(binding, states),
        PIN,
        at,
        v.exit_session.close_ts + timedelta(days=1),
        (SOURCE,),
        (SOURCE,),
    )


def _reads(v, account, at, *, price="10", cash="1000", funds="1000", quantity="0", side="buy"):
    from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput

    p = D(price)
    identity = KisPaperAccountIdentity(MASKED, at)
    orders = KisPaperOpenOrdersSnapshot((), at)
    positions = (
        () if D(quantity) == 0 else (KisPaperPosition("QQQ", "NASD", "USD", D(quantity), p, p, at),)
    )
    quote = KisPaperSpyLimitInput(p, 2, D(".01"), at, p, p)
    instrument = KisPaperStockInstrument("QQQ", v.targets[0].receipt.instrument_binding_ref)
    if side == "sell":
        return KisPaperStockExitReads(
            account,
            instrument,
            KisPaperStockExitAccountSnapshot(identity, positions, orders, at),
            quote,
            at,
            at,
            0.0,
        )
    money = KisPaperCashSnapshot("USD", D(cash), at)
    orderable = KisPaperOrderableFundsSnapshot("USD", D(funds), "NASD", "QQQ", p, at)
    snapshot = KisPaperReadOnlySnapshot(identity, money, orderable, positions, orders, at)
    return KisPaperStockPreviewReads(
        account, instrument, snapshot, quote, p, money, orderable, at, at, 0.0
    )


def _entry(*old, **read_changes):
    v = value()
    base = old_scope(*old)
    binding = base["binding"]
    binding.update(
        version=4,
        portfolio={"owner_refs": dict.fromkeys(("SPY", "TLT", "GLD")), "plans": []},
        stocks={},
    )
    _refresh(binding)
    at = v.entry_session.open_ts + timedelta(minutes=10)
    boundary = _boundary(binding, base["states"], v, at)
    return dict(
        value=v,
        execution_source_ref=SOURCE,
        binding=binding,
        states=base["states"],
        **_pins(binding),
        writer_boundary=boundary,
        expected_writer_ref=boundary.reference,
        reads=_reads(v, binding["account_ref"], at, **read_changes),
        expected_masked_account=MASKED,
        as_of=at,
        valid_until=at + timedelta(seconds=60),
    )


def _admit(args):
    return core.admit_qqq_h5_boundary(
        **{
            k: v
            for k, v in args.items()
            if k not in {"reads", "expected_masked_account", "valid_until"}
        }
    )


def _settle(plan, states, *, filled=None, remaining="0", closed=True, observed=None):
    intent = plan.seed.intent
    at = intent.created_at + timedelta(seconds=1)
    when = observed or at + timedelta(seconds=1)
    count = intent.quantity if filled is None else D(filled)
    order_id = "SYNTHETIC-" + intent.run_id[-16:]
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id=order_id,
            order_at=at,
            symbol="QQQ",
            exchange="NASD",
            side=intent.side,
            quantity=intent.quantity,
        ),
        intent.quantity,
        count,
        count * intent.limit_price,
        when,
        D(remaining),
    )
    state = KisPaperCanaryState(
        intent,
        "submitted",
        when,
        "reconciliation_clean",
        broker_order_id=order_id,
        submission_started_at=at,
        submitted_at=at,
        cumulative_fill=fill,
        fill_observation_status="available",
        fill_observed_at=when,
    )
    binding = copy.deepcopy(plan.binding)
    binding["qqq"]["orders"][-1]["closed"] = closed
    if closed:
        binding["terminal_evidence"][intent.run_id] = budget._terminal_payload(state)
    return binding, dict(states) | {intent.run_id: state}


def _exit(args, plan, binding, states, *, at=None, quantity="5", **read_changes):
    v = args["value"]
    at = at or v.metadata.exit_not_before
    boundary = _boundary(binding, states, v, at)
    return dict(
        value=v,
        journal=plan.journal,
        binding=binding,
        states=states,
        **_pins(binding),
        writer_boundary=boundary,
        expected_writer_ref=boundary.reference,
        reads=_reads(v, binding["account_ref"], at, quantity=quantity, side="sell", **read_changes),
        expected_masked_account=MASKED,
        as_of=at,
        valid_until=at + timedelta(seconds=60),
    )


def test_pure_entry_preserves_v4_bank_real_owner_and_model_receipt(monkeypatch):
    args = _entry()
    before = copy.deepcopy(args)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", lambda *_: pytest.fail("pure_reader_IO"))
        plan = core.plan_qqq_h5_entry(**args)
    assert args == before
    assert plan.status == "prepared" and plan.runtime_authorized is False
    assert plan.seed.intent.quantity == 5
    assert plan.seed.intent.exchange == "NASD"
    assert (
        plan.seed.intent.decision_id
        == "receipt-" + args["value"].targets[0].receipt.decision_id[16:]
    )
    assert set(plan.binding) == budget._V4_KEYS
    assert (
        plan.binding["stocks"] == {} and plan.binding["portfolio"] == before["binding"]["portfolio"]
    )
    assert plan.binding["qqq"]["cycle_id"] == before["binding"]["qqq"]["cycle_id"]
    assert plan.binding["qqq"]["owner_ref"] != before["binding"]["qqq"]["owner_ref"]
    assert plan.binding["basis_ref"] == before["binding"]["basis_ref"]
    assert plan.journal.input_ref == args["value"].input_ref
    assert plan.journal.policy_ref == args["value"].policy_ref
    assert set(plan.binding["qqq"]["orders"][0]) == {"run_id", "intent_ref", "closed"}


@pytest.mark.parametrize(
    ("price", "funds", "expected"),
    [("51", "1000", 0), ("50", "1000", 1), ("10", "29", 2), ("10", "0", 0)],
)
def test_whole_share_no_force_or_allocated_bank_multiplier(price, funds, expected):
    plan = core.plan_qqq_h5_entry(**_entry(price=price, funds=funds))
    assert (0 if plan.seed is None else plan.seed.intent.quantity) == expected
    assert plan.status == ("prepared" if expected else "no_intent")


def test_other_owner_unknown_reservation_counted_once_not_global_hold():
    pending = _legacy_state("bs-" + "1" * 64, quantity="9", phase="intent_recorded")
    args = _entry(pending, funds="920", cash="920")
    plan = core.plan_qqq_h5_entry(**args)
    assert plan.seed.intent.quantity == 2  # 920 - 900; not a second subtraction from the bank.
    assert plan.binding["orders"] == args["binding"]["orders"]
    assert plan.binding["terminal_evidence"] == args["binding"]["terminal_evidence"]


@pytest.mark.parametrize("kind", ["pending", "filled", "no_terminal_proof"])
def test_unresolved_or_owned_legacy_qqq_cannot_be_adopted(kind):
    state = _legacy_state(
        "bq-" + "1" * 64,
        symbol="QQQ",
        phase="intent_recorded" if kind == "pending" else "submitted",
        filled=None if kind == "pending" else "1",
        gross="100",
    )
    args = _entry(state)
    if kind == "no_terminal_proof":
        args["binding"]["terminal_evidence"].clear()
        args.update(_pins(args["binding"]))
    with pytest.raises((ValueError, RuntimeError)):
        _admit(args)


@pytest.mark.parametrize(
    "change",
    [
        "bool",
        "not_excluded",
        "unresolved",
        "wrong_pin",
        "wrong_custody",
        "stale",
        "expires_before_exit",
    ],
)
def test_writer_projection_is_not_a_caller_permission_bool(change):
    args = _entry()
    boundary = args["writer_boundary"]
    if change == "bool":
        args["writer_boundary"] = True
    elif change == "not_excluded":
        args["writer_boundary"] = replace(boundary, excluded_sources=())
    elif change == "unresolved":
        args["writer_boundary"] = replace(boundary, unresolved_sources=(PIN,))
    elif change == "wrong_pin":
        args["expected_writer_ref"] = PIN
    elif change == "wrong_custody":
        args["writer_boundary"] = replace(boundary, custody_ref=PIN)
    elif change == "stale":
        args["writer_boundary"] = replace(
            boundary, observed_at=args["as_of"] - timedelta(seconds=121)
        )
    else:
        args["writer_boundary"] = replace(
            boundary, excluded_until=args["value"].metadata.exit_not_before
        )
    if change not in {"bool", "wrong_pin"}:
        args["expected_writer_ref"] = args["writer_boundary"].reference
    with pytest.raises(ValueError):
        _admit(args)


def test_empty_source_bound_writer_inventory_is_not_invented_runtime_proof():
    args = _entry()
    boundary = replace(args["writer_boundary"], legacy_sources=(), excluded_sources=())
    args.update(writer_boundary=boundary, expected_writer_ref=boundary.reference)
    assert core.plan_qqq_h5_entry(**args).runtime_authorized is False


@pytest.mark.parametrize(
    "change", ["foreign", "wrong_funds_route", "stale", "wrong_account", "open_order"]
)
def test_fresh_read_negatives(change):
    args = _entry(quantity="1" if change == "foreign" else "0")
    reads = args["reads"]
    if change == "wrong_funds_route":
        reads = replace(reads, orderable=replace(reads.orderable, reference_exchange="AMEX"))
    elif change == "stale":
        reads = replace(
            reads, cash=replace(reads.cash, captured_at=args["as_of"] - timedelta(seconds=121))
        )
    elif change == "wrong_account":
        args["expected_masked_account"] = "****0000-**00"
    elif change == "open_order":
        order = KisPaperOpenOrder(
            "open-SYNTHETIC", "QQQ", "NASD", "USD", "buy", D(1), D(0), D(1), D(10), args["as_of"]
        )
        reads = replace(
            reads,
            snapshot=replace(
                reads.snapshot, open_orders=KisPaperOpenOrdersSnapshot((order,), args["as_of"])
            ),
        )
    args["reads"] = reads
    with pytest.raises(ValueError):
        core.plan_qqq_h5_entry(**args)


def test_fresh_buy_read_must_start_at_or_after_model_decision():
    args = _entry()
    v = args["value"]
    at = v.entry_session.open_ts
    decided = at - timedelta(seconds=30)
    v = prepare_model_paper_weights_input(
        replace(v.metadata, weights_observed_at=decided),
        entry_session=v.entry_session,
        exit_session=v.exit_session,
        profile=MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    )
    assert v.targets[0].proposal.decided_at == decided
    boundary = _boundary(args["binding"], args["states"], v, at)
    args.update(
        value=v,
        as_of=at,
        valid_until=at + timedelta(seconds=60),
        writer_boundary=boundary,
        expected_writer_ref=boundary.reference,
    )
    reads = _reads(v, args["binding"]["account_ref"], at)
    args["reads"] = replace(reads, started_at=decided - timedelta(seconds=1))
    with pytest.raises(core.QqqH5PlanningError, match="qqq_h5_read_clock"):
        core.plan_qqq_h5_entry(**args)
    args["reads"] = replace(reads, started_at=decided)
    assert core.plan_qqq_h5_entry(**args).runtime_authorized is False


def test_native_legacy_early_exit_hazard_is_not_the_h5_policy():
    args = _entry(price="50")
    plan = core.plan_qqq_h5_entry(**args)
    binding, states = _settle(plan, args["states"])
    old_entry = budget._qqq_filled_entry(
        binding["qqq"]["orders"], list(states.values()), binding["terminal_evidence"]
    )
    assert old_entry is not None  # Legacy unit policy would regard the whole owner as sellable.
    early = args["as_of"] + timedelta(minutes=2)
    result = core.plan_qqq_h5_exit(**_exit(args, plan, binding, states, at=early, quantity="1"))
    assert result.status == "hold" and result.seed is None


def test_linked_partial_entry_pending_then_terminal_residual_exit_and_closure():
    args = _entry()
    plan = core.plan_qqq_h5_entry(**args)
    raw = core.serialize_qqq_h5_journal(plan.journal)
    plan = replace(
        plan, journal=core.load_qqq_h5_journal(raw, expected_sha256=hashlib.sha256(raw).hexdigest())
    )
    binding, states = _settle(plan, args["states"], filled="2", remaining="3", closed=False)
    result = core.plan_qqq_h5_exit(**_exit(args, plan, binding, states, quantity="2"))
    assert result.status == "reconcile" and result.seed is None
    binding, states = _settle(plan, args["states"], filled="2", remaining="0")
    sell = core.plan_qqq_h5_exit(**_exit(args, plan, binding, states, quantity="2"))
    assert sell.status == "prepared" and sell.seed.intent.quantity == 2
    assert (
        sell.seed.intent.side == "sell"
        and sell.seed.intent.created_at == args["value"].metadata.exit_not_before
    )
    assert sell.journal.entry == plan.journal.entry
    assert sell.journal.exits[0].intent_ref == sell.seed.intent.fingerprint
    ended, final_states = _settle(sell, states)
    closed = core.plan_qqq_h5_exit(
        **_exit(
            args,
            sell,
            ended,
            final_states,
            at=sell.seed.intent.created_at + timedelta(seconds=3),
            quantity="0",
        )
    )
    assert closed.status == "closed" and closed.runtime_authorized is False


def test_partial_terminal_exit_only_plans_new_linked_residual():
    args = _entry()
    entry = core.plan_qqq_h5_entry(**args)
    binding, states = _settle(entry, args["states"])
    sell = core.plan_qqq_h5_exit(**_exit(args, entry, binding, states))
    binding, states = _settle(sell, states, filled="2", remaining="0")
    at = sell.seed.intent.created_at + timedelta(seconds=3)
    again = core.plan_qqq_h5_exit(**_exit(args, sell, binding, states, at=at, quantity="3"))
    assert again.seed.intent.quantity == 3
    assert again.seed.intent.run_id != sell.seed.intent.run_id
    assert again.journal.entry == entry.journal.entry and len(again.journal.exits) == 2


def test_later_distinct_model_cohort_reuses_real_owner_without_unit_history_gate():
    args = _entry()
    entry = core.plan_qqq_h5_entry(**args)
    binding, states = _settle(entry, args["states"])
    sell = core.plan_qqq_h5_exit(**_exit(args, entry, binding, states))
    binding, states = _settle(sell, states)
    prefix = copy.deepcopy(binding)
    later = value(date(2026, 11, 2), date(2026, 11, 6))
    at = later.entry_session.open_ts + timedelta(minutes=10)
    boundary = _boundary(binding, states, later, at)
    next_args = args | dict(
        value=later,
        binding=binding,
        states=states,
        **_pins(binding),
        writer_boundary=boundary,
        expected_writer_ref=boundary.reference,
        as_of=at,
        valid_until=at + timedelta(seconds=60),
        reads=_reads(later, binding["account_ref"], at),
    )
    new = core.plan_qqq_h5_entry(**next_args)
    assert new.status == "prepared" and new.seed.intent.quantity == 5
    assert new.journal.owner_id == entry.journal.owner_id
    assert new.journal.input_ref != entry.journal.input_ref
    assert new.seed.intent.decision_id != entry.seed.intent.decision_id
    assert new.binding["qqq"]["orders"][:2] == prefix["qqq"]["orders"]
    assert new.binding["terminal_evidence"] == prefix["terminal_evidence"]
    assert new.binding["basis_ref"] == prefix["basis_ref"]


def test_prefix_costs_and_realized_loss_preserved_once_for_new_cohort():
    buy = _legacy_state(
        "bq-" + "1" * 64, symbol="QQQ", quantity="2", filled="2", gross="200", index=1
    )
    sell = _legacy_state(
        "bq-" + "2" * 64,
        symbol="QQQ",
        quantity="2",
        filled="2",
        gross="180",
        side="sell",
        limit="90",
        index=2,
    )
    args = _entry(buy, sell)
    before = copy.deepcopy(args["binding"])
    plan = core.plan_qqq_h5_entry(**args)
    assert plan.seed.intent.quantity == 5
    assert plan.binding["qqq"]["orders"][:2] == before["qqq"]["orders"]
    assert plan.binding["terminal_evidence"] == before["terminal_evidence"]
    projection = budget.project_shared_budget(
        binding=plan.binding,
        states=args["states"] | {plan.seed.intent.run_id: plan.seed},
        **{k: v for k, v in _pins(plan.binding).items() if k != "expected_binding_ref"},
        as_of=args["as_of"],
    )
    assert projection.gross_cash == 980 and projection.reserved_buys == 50


@pytest.mark.parametrize(
    "change", ["foreign_row", "changed_input", "changed_prefix", "foreign_inventory"]
)
def test_exit_cannot_use_other_request_or_inventory(change):
    args = _entry()
    plan = core.plan_qqq_h5_entry(**args)
    binding, states = _settle(plan, args["states"])
    out = _exit(args, plan, binding, states, quantity="6" if change == "foreign_inventory" else "5")
    if change == "foreign_row":
        out["journal"] = replace(
            plan.journal, entry=replace(plan.journal.entry, run_id="bq-" + "f" * 64)
        )
    elif change == "changed_input":
        out["journal"] = replace(plan.journal, input_ref=PIN)
    elif change == "changed_prefix":
        out["journal"] = replace(plan.journal, legacy_ref=PIN)
    with pytest.raises(ValueError):
        core.plan_qqq_h5_exit(**out)


def test_journal_strict_cold_roundtrip_and_hash():
    plan = core.plan_qqq_h5_entry(**_entry())
    raw = core.serialize_qqq_h5_journal(plan.journal)

    def load(payload):
        return core.load_qqq_h5_journal(
            payload, expected_sha256=hashlib.sha256(payload).hexdigest()
        )

    assert load(raw) == plan.journal
    changed = json.loads(raw)
    changed["runtime_authorized"] = True
    with pytest.raises(ValueError):
        load(json.dumps(changed).encode())
    with pytest.raises(ValueError):
        load(raw.replace(b'"schema":', b'"schema":"duplicate","schema":'))
    with pytest.raises(ValueError):
        load(b" " + raw)
    with pytest.raises(ValueError):
        core.load_qqq_h5_journal(raw, expected_sha256="0" * 64)


@pytest.mark.parametrize("cycle_id", ["bad cycle", "bad/cycle"])
def test_journal_cycle_id_rejects_whitespace_and_slash_in_constructor_and_cold_load(cycle_id):
    plan = core.plan_qqq_h5_entry(**_entry())
    with pytest.raises(core.QqqH5PlanningError, match="qqq_h5_cycle_invalid"):
        replace(plan.journal, cycle_id=cycle_id)
    document = json.loads(core.serialize_qqq_h5_journal(plan.journal))
    document["cycle_id"] = cycle_id
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
    with pytest.raises(core.QqqH5PlanningError, match="qqq_h5_cycle_invalid"):
        core.load_qqq_h5_journal(payload, expected_sha256=hashlib.sha256(payload).hexdigest())


def test_stale_whole_book_pin_rejects_without_overwrite():
    args = _entry()
    before = copy.deepcopy(args)
    args["expected_binding_ref"] = PIN
    with pytest.raises(ValueError, match="book_changed"):
        core.plan_qqq_h5_entry(**args)
    assert args["binding"] == before["binding"] and args["states"] == before["states"]


def test_forged_input_cannot_expand_original_cohort_ceiling():
    args = _entry()
    forged = copy.deepcopy(args["value"])
    object.__setattr__(forged.metadata, "original_basis_gross_ceiling", D(".05"))
    args["value"] = forged
    before = copy.deepcopy(args["binding"])
    with pytest.raises((ValueError, RuntimeError)):
        core.plan_qqq_h5_entry(**args)
    assert args["binding"] == before


def test_unbound_qqq_request_in_supplied_state_membership_withholds():
    args = _entry()
    unknown = _legacy_state("bq-" + "f" * 64, symbol="QQQ", phase="intent_recorded")
    args["states"][unknown.intent.run_id] = unknown
    with pytest.raises((ValueError, RuntimeError)):
        _admit(args)


@pytest.mark.parametrize("change", ["nested_field", "naive_clock", "wrong_list_shape"])
def test_malformed_journal_never_becomes_a_plan(change):
    plan = core.plan_qqq_h5_entry(**_entry())
    document = json.loads(core.serialize_qqq_h5_journal(plan.journal))
    if change == "nested_field":
        document["entry"].pop("intent_ref")
    elif change == "naive_clock":
        document["entry_open"] = "2026-10-26T13:30:00"
    else:
        document["exits"] = {}
    payload = json.dumps(document).encode()
    with pytest.raises(ValueError):
        core.load_qqq_h5_journal(payload, expected_sha256=hashlib.sha256(payload).hexdigest())


@pytest.mark.parametrize("precision", [8, 28, 60])
def test_fraction_sizing_not_local_decimal_rounding(precision):
    args = _entry(price="10.01")
    with localcontext() as ctx:
        ctx.prec = precision
        plan = core.plan_qqq_h5_entry(**args)
    assert plan.seed.intent.quantity == 4
