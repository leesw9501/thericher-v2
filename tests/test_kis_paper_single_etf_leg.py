"""Canonical single-ETF planning/persistence and native mock lifecycle only."""

from __future__ import annotations

import copy
import json
import socket
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import pytest

from test_kis_paper_portfolio_execute import ACCOUNT, SyntheticPaperClient
from test_kis_paper_portfolio_preview import NOW, _reads, _scope
from test_kis_paper_portfolio_preview import _state as prior_state
from test_kis_paper_portfolio_sell import SellClient
from test_kis_paper_stock_plan_reservation import _arguments as stock_arguments
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_portfolio_execute as execute
from thericher_v2.execution import kis_paper_single_etf_leg as leg
from thericher_v2.execution import kis_paper_stock_plan as stock
from thericher_v2.execution.kis_paper_portfolio_plan import (
    _states,
    reconcile_kis_paper_portfolio_plan,
)
from thericher_v2.execution.kis_readonly import KisPaperPosition


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("synthetic_single_etf_cannot_use_network_or_credentials")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(canary.UrllibKisPaperCanaryTransport, "request", denied)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", denied)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", denied)


def _hash(value):
    return "sha256:" + budget._digest(value)


def _refs(binding):
    return {o.owner_ref: ref for o, ref in budget._owners(binding)}


def _contract(binding, **changes):
    value = leg.SingleEtfLegContract(
        request_id="single-etf-synthetic-H20",
        account_ref=ACCOUNT,
        basis_ref=binding["basis_ref"],
        source_ref="sha256:" + "1" * 64,
        proposal_ref="sha256:" + "2" * 64,
        model_ref="sha256:" + "3" * 64,
        input_ref="sha256:" + "4" * 64,
        policy_ref="sha256:" + "5" * 64,
        symbol="SPY",
        action="enter",
        target_exposure=D(".1"),
        point_available_at=NOW - timedelta(hours=1),
        entry_date=NOW.date(),
        entry_starts_at=NOW,
        entry_ends_at=NOW + timedelta(minutes=6),
        exit_window_seconds=360,
    )
    return replace(value, **changes)


def _arguments(*states):
    binding = _scope(*states)["binding"]
    binding["account_ref"] = ACCOUNT
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    reads = _reads(
        spy=sum(
            (
                s.current_fill.quantity
                for s in states
                if s.intent.symbol == "SPY" and s.current_fill
            ),
            D(0),
        )
    )
    return dict(
        binding=binding,
        states={s.intent.run_id: s for s in states},
        contract=_contract(binding),
        expected_owner_refs=_refs(binding),
        expected_binding_ref=_hash(binding),
        reads=replace(reads, account_ref=ACCOUNT, instruments=reads.instruments[:1]),
        as_of=NOW,
    )


def _persist(tmp_path, args):
    root = tmp_path / "private" / "canary"
    root.mkdir(parents=True)
    budget._atomic_json(root / budget.BUDGET_FILE, args["binding"])
    for run, state in args["states"].items():
        budget._atomic_json(root / (run + ".json"), state.to_dict())
    return dict(
        state_root=root,
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "artifacts",
        **{k: v for k, v in args.items() if k not in {"binding", "states"}},
    )


def _reserved(tmp_path):
    args = _arguments()
    io = _persist(tmp_path, args)
    result = leg.reserve_single_etf_leg(**io, phase="entry")
    return args, io, result


def _proof(io, phase, result, *, at=NOW):
    binding = budget._load_binding(io["state_root"])
    return leg.single_etf_execution_binding(
        state_root=io["state_root"],
        contract=io["contract"],
        phase=phase,
        expected_control_ref=_hash(result.control),
        expected_binding_ref=_hash(binding),
        expected_owner_refs=_refs(binding),
        as_of=at,
    )


def _call(io, proof, client):
    parent = io["state_root"].parent.parent
    return dict(
        proof=proof,
        state_root=io["state_root"],
        client=client,
        execute=True,
        runtime_projection_path=parent / "runtime.json",
        paper_account_snapshot_path=parent / "account.json",
        emergency_state_path=parent / "emergency.json",
        execution_control_path=parent / "control.json",
        artifact_root=io["artifact_root"],
        repository_root=io["repository_root"],
        clock=lambda: client.now,
    )


def _filled(tmp_path):
    args, io, entry = _reserved(tmp_path)
    client = SyntheticPaperClient(io["state_root"])
    outcome = execute.execute_kis_paper_portfolio_buy(
        **_call(io, _proof(io, "entry", entry), client)
    )
    assert outcome.phase == "submitted"
    binding = budget._load_binding(io["state_root"])
    reconciled = reconcile_kis_paper_portfolio_plan(
        state_root=io["state_root"],
        repository_root=io["repository_root"],
        artifact_root=io["artifact_root"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=io["contract"].basis_ref,
        expected_owner_refs=_refs(binding),
        request_id=io["contract"].request_id,
        expected_plan_ref=entry.plan_ref,
        as_of=NOW,
    )
    assert reconciled.status == "reconciled"
    return args, io, entry, client


def _exit_args(io, previous):
    at = io["contract"].exit_starts_at + timedelta(seconds=1)
    client = SellClient(previous)
    client.now = at
    snapshot = client.snapshot()
    original = _reads(spy=D(0)).instruments[0]
    row = replace(
        original,
        quote=replace(original.quote, quoted_at=at),
        cash=replace(original.cash, captured_at=at),
        orderable=replace(original.orderable, captured_at=at),
    )
    reads = replace(
        io["reads"], snapshot=snapshot, instruments=(row,), started_at=at, completed_at=at
    )
    binding = budget._load_binding(io["state_root"])
    return (
        io
        | dict(
            expected_owner_refs=_refs(binding),
            expected_binding_ref=_hash(binding),
            reads=reads,
            as_of=at,
        )
    ), client


def test_true_open_offset20_calendar_not_old20_or_h5():
    windows = leg.single_etf_h20_sessions(date(2026, 10, 30))
    assert len(windows) == 21
    assert windows[-1].open_ts == datetime(2026, 11, 30, 14, 30, tzinfo=UTC)
    assert windows[0].open_ts.hour == 13 and windows[1].open_ts.hour == 14
    assert all(w.open_ts.date() != date(2026, 11, 26) for w in windows)
    assert next(w for w in windows if w.open_ts.date() == date(2026, 11, 27)).close_ts.hour == 18
    with pytest.raises(leg.SingleEtfLegError, match="calendar_scope_invalid"):
        leg.single_etf_h20_sessions(date(2026, 12, 15))


def test_pure_canonical_plan_one_original_B10_and_preserved_owners():
    args = _arguments()
    before = copy.deepcopy(args)
    result = leg.build_single_etf_entry_plan(**args)
    assert result.status == "prepared" and args == before
    assert [(i.symbol, i.exchange, i.quantity) for i in result.intents] == [("SPY", "AMEX", D(10))]
    assert result.binding["qqq"] == before["binding"]["qqq"]
    assert result.binding["orders"] == before["binding"]["orders"]
    assert result.binding["basis_ref"] == before["binding"]["basis_ref"]
    assert result.control["exit_at"] == args["contract"].exit_starts_at.isoformat()
    assert list(budget._portfolio_seed_states(result.binding)) == [result.intents[0].run_id]
    assert result.safe_payload()["new_submits"] == 0


def test_persist_restart_expired_input_keeps_identity_and_duty(tmp_path):
    args, io, result = _reserved(tmp_path)
    before = (io["state_root"] / budget.BUDGET_FILE).read_bytes()
    replay = leg.reserve_single_etf_leg(
        **(
            io
            | dict(
                expected_owner_refs=_refs(result.binding),
                reads=None,
                as_of=NOW + timedelta(hours=1),
            )
        ),
        phase="entry",
    )
    assert replay.status == "replayed" and replay.intents == result.intents
    assert replay.control == result.control
    assert (io["state_root"] / budget.BUDGET_FILE).read_bytes() == before
    assert budget.project_budget(io["state_root"], result.binding, as_of=NOW).reserved_buys == 1000
    assert args["binding"]["allocated_usd"] == "1000"


def test_unknown_native_entry_recovery_never_duplicates(tmp_path):
    _, io, entry = _reserved(tmp_path)
    client = SyntheticPaperClient(io["state_root"])
    client.unknown = True
    proof = _proof(io, "entry", entry)
    execute.execute_kis_paper_portfolio_buy(**_call(io, proof, client))
    state = canary.KisPaperCanaryStateStore(io["state_root"] / (proof.run_id + ".json")).read()
    assert state.phase == "outcome_unknown"
    client.now += timedelta(minutes=10)
    execute.execute_kis_paper_portfolio_buy(**_call(io, proof, client))
    assert len(client.submits) == 1
    assert (
        budget.project_budget(io["state_root"], entry.binding, as_of=client.now).reserved_buys
        == 1000
    )


def test_native_owned_exit_persist_and_same_request_wire_once(tmp_path):
    _, io, entry, buy = _filled(tmp_path)
    exit_io, sell = _exit_args(io, buy)
    result = leg.reserve_single_etf_leg(**exit_io, phase="exit")
    assert result.status == "reserved" and result.intents[0].quantity == entry.intents[0].quantity
    assert result.intents[0].side == "sell"
    proof = _proof(io, "exit", result, at=sell.now)
    outcome = execute.execute_kis_paper_portfolio_sell(**_call(io, proof, sell))
    assert outcome.phase == "submitted" and len(sell.wire) == 1
    sell.now += timedelta(minutes=10)
    execute.execute_kis_paper_portfolio_sell(**_call(io, proof, sell))
    assert len(sell.wire) == 1 and sell.snapshot().positions == ()
    assert (
        leg.reserve_single_etf_leg(
            **(
                exit_io
                | dict(reads=None, expected_owner_refs=_refs(result.binding), as_of=sell.now)
            ),
            phase="exit",
        ).intents
        == result.intents
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_ref", "sha256:" + "a" * 64),
        ("input_ref", "sha256:" + "b" * 64),
        ("policy_ref", "sha256:" + "c" * 64),
        ("proposal_ref", "sha256:" + "d" * 64),
    ],
)
def test_same_request_changed_contract_refused(tmp_path, field, value):
    _, io, entry = _reserved(tmp_path)
    with pytest.raises(leg.SingleEtfLegError, match="control_binding_changed"):
        leg.reserve_single_etf_leg(
            **(
                io
                | dict(
                    contract=replace(io["contract"], **{field: value}),
                    expected_owner_refs=_refs(entry.binding),
                )
            ),
            phase="entry",
        )


def test_unknown_entry_never_prepares_exit(tmp_path):
    _, io, entry = _reserved(tmp_path)
    binding = entry.binding
    path = leg._control_path(io["state_root"], io["contract"], "entry")
    state = budget._portfolio_seed_states(binding)[entry.intents[0].run_id]
    unknown = replace(
        state,
        phase="outcome_unknown",
        reason_code="reconciliation_unresolved",
        submission_started_at=NOW,
        updated_at=NOW + timedelta(seconds=1),
    )
    args = dict(
        binding=binding,
        states={unknown.intent.run_id: unknown},
        contract=io["contract"],
        entry_control=json.loads(path.read_bytes()),
        expected_owner_refs=_refs(binding),
        expected_binding_ref=_hash(binding),
        as_of=io["contract"].exit_starts_at,
    )
    with pytest.raises(leg.SingleEtfLegError, match="entry_outcome_unknown"):
        leg.build_single_etf_exit_plan(**args)


def test_control_persisted_before_bank_and_exact_crash_resume(tmp_path, monkeypatch):
    args = _arguments()
    io = _persist(tmp_path, args)
    original = budget._atomic_json
    hit = []

    def crash(path, payload):
        if path.name == budget.BUDGET_FILE:
            hit.append(leg._control_path(io["state_root"], io["contract"], "entry").exists())
            raise OSError("invented_crash")
        return original(path, payload)

    with monkeypatch.context() as patcher:
        patcher.setattr(budget, "_atomic_json", crash)
        with pytest.raises(OSError):
            leg.reserve_single_etf_leg(**io, phase="entry")
    assert hit == [True]
    assert budget._load_binding(io["state_root"]) == args["binding"]
    staged = budget._read_json(leg._control_path(io["state_root"], io["contract"], "entry"))
    result = leg.reserve_single_etf_leg(**(io | dict(reads=None)), phase="entry")
    assert result.control == staged and len(result.intents) == 1


@pytest.mark.parametrize("change", ["inventory", "stale", "funds", "window", "source"])
def test_fresh_native_safety_boundaries(change):
    args = _arguments()
    if change == "inventory":
        reads = args["reads"]
        args["reads"] = replace(
            reads,
            snapshot=replace(
                reads.snapshot,
                positions=(KisPaperPosition("SPY", "AMEX", "USD", D(1), D(100), D(100), NOW),),
            ),
        )
    elif change == "stale":
        reads = args["reads"]
        args["reads"] = replace(
            reads,
            instruments=(
                replace(
                    reads.instruments[0],
                    quote=replace(
                        reads.instruments[0].quote, quoted_at=NOW - timedelta(seconds=121)
                    ),
                ),
            ),
        )
    elif change == "funds":
        reads = args["reads"]
        args["reads"] = replace(
            reads,
            instruments=(
                replace(
                    reads.instruments[0],
                    orderable=replace(reads.instruments[0].orderable, reference_exchange="NASD"),
                ),
            ),
        )
    elif change == "window":
        args["as_of"] = NOW + timedelta(hours=1)
    else:
        args["expected_binding_ref"] = "sha256:" + "f" * 64
    with pytest.raises(leg.SingleEtfLegError):
        leg.build_single_etf_entry_plan(**args)


def test_zero_capacity_no_signal_and_unsupported_selection_never_forced():
    args = _arguments()
    result = leg.build_single_etf_entry_plan(
        **(
            args
            | dict(
                contract=replace(args["contract"], action="abstain", target_exposure=D(0)),
                reads=None,
            )
        )
    )
    assert result.status == "no_intent" and result.intents == ()
    with pytest.raises(leg.SingleEtfLegError, match="single_etf_not_supported"):
        replace(args["contract"], symbol="QQQ")
    reads = args["reads"]
    row = replace(
        reads.instruments[0], cash=replace(reads.instruments[0].cash, available_cash=D(0))
    )
    result = leg.build_single_etf_entry_plan(
        **(args | dict(reads=replace(reads, instruments=(row,))))
    )
    assert result.status == "no_intent" and result.binding is None


def test_due_exit_window_and_fresh_source_effect_binding(tmp_path):
    _, io, entry, client = _filled(tmp_path)
    exit_io, _ = _exit_args(io, client)
    with pytest.raises(leg.SingleEtfLegError, match="exit_window_closed"):
        leg.reserve_single_etf_leg(**(exit_io | dict(as_of=NOW)), phase="exit")
    _, fresh_io, fresh_entry = _reserved(tmp_path / "fresh")
    with pytest.raises(leg.SingleEtfLegError, match="effect_window_closed"):
        _proof(fresh_io, "entry", fresh_entry, at=NOW + timedelta(hours=1))


def test_unrelated_unknown_stock_reservation_counts_once_and_does_not_block_native_buy(tmp_path):
    original = stock_arguments(target=".02")
    binding = original["binding"]
    binding["account_ref"] = ACCOUNT
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    for owner, _ in budget._owners(binding):
        if owner.owner_ref.startswith("portfolio-"):
            binding["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    original.update(
        expected_account_ref=ACCOUNT,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs=_refs(binding),
        expected_binding_ref=_hash(binding),
        reads=replace(original["reads"], account_ref=ACCOUNT),
    )
    f9 = stock.build_kis_paper_stock_plan(**original)
    assert f9.status == "prepared" and f9.reservation == 200
    seed = next(iter(budget._stock_seed_states(f9.binding).values()))
    at = seed.intent.valid_until + timedelta(seconds=1)
    unknown = replace(
        seed,
        phase="outcome_unknown",
        reason_code="reconciliation_unresolved",
        submission_started_at=seed.intent.created_at,
        updated_at=at,
    )
    contract = _contract(
        f9.binding,
        entry_date=at.date(),
        entry_starts_at=original["as_of"],
        entry_ends_at=original["as_of"] + timedelta(minutes=6),
        point_available_at=original["as_of"] - timedelta(hours=1),
    )
    base = _reads(spy=D(0))
    row = base.instruments[0]
    row = replace(
        row,
        quote=replace(row.quote, quoted_at=at),
        cash=replace(row.cash, captured_at=at),
        orderable=replace(row.orderable, captured_at=at),
    )
    snapshot = replace(
        base.snapshot,
        captured_at=at,
        identity=replace(base.snapshot.identity, captured_at=at),
        cash=replace(base.snapshot.cash, captured_at=at),
        orderable_funds=replace(base.snapshot.orderable_funds, captured_at=at),
        open_orders=replace(base.snapshot.open_orders, captured_at=at),
    )
    reads = replace(
        base,
        account_ref=ACCOUNT,
        instruments=(row,),
        snapshot=snapshot,
        started_at=at,
        completed_at=at,
    )
    args = dict(
        binding=f9.binding,
        states={unknown.intent.run_id: unknown},
        contract=contract,
        expected_owner_refs=_refs(f9.binding),
        expected_binding_ref=_hash(f9.binding),
        reads=reads,
        as_of=at,
    )
    io = _persist(tmp_path, args)
    saved = leg.reserve_single_etf_leg(**io, phase="entry")
    assert saved.intents[0].quantity == 8
    client = SyntheticPaperClient(io["state_root"])
    client.now = at
    outcome = execute.execute_kis_paper_portfolio_buy(
        **_call(io, _proof(io, "entry", saved, at=at), client)
    )
    assert outcome.phase == "submitted" and len(client.submits) == 1
    current = budget._load_binding(io["state_root"])
    projection = budget.project_budget(io["state_root"], current, as_of=at)
    assert projection.entry_cost == 800 and projection.reserved_buys == 200
    retained = canary.KisPaperCanaryStateStore(
        io["state_root"] / (unknown.intent.run_id + ".json")
    ).read()
    assert retained == unknown and current["stocks"] == f9.binding["stocks"]


def test_prior_owned_nonflat_baseline_is_not_adopted_or_reset():
    prior = prior_state()
    args = _arguments(prior)
    before = copy.deepcopy(args["binding"])
    result = leg.build_single_etf_entry_plan(**args)
    assert result.status == "prepared" and result.intents[0].quantity == 9
    assert result.binding["orders"] == before["orders"]
    assert result.binding["spy_owner_ref"] == before["spy_owner_ref"]
    assert result.binding["terminal_evidence"] == before["terminal_evidence"]
    assert len(result.control["plan"]["states"]) == 1
    assert prior.intent.run_id not in result.control["plan"]["states"]


def test_missing_entry_duty_cannot_bind_native_sell(tmp_path):
    _, io, _, client = _filled(tmp_path)
    exit_io, sell = _exit_args(io, client)
    result = leg.reserve_single_etf_leg(**exit_io, phase="exit")
    leg._control_path(io["state_root"], io["contract"], "entry").unlink()
    with pytest.raises(leg.SingleEtfLegError, match="control_binding_changed"):
        _proof(io, "exit", result, at=sell.now)


def test_foreign_same_canonical_owner_sell_withholds_only_ambiguous_exit(tmp_path):
    _, io, entry, client = _filled(tmp_path)
    binding = budget._load_binding(io["state_root"])
    at = NOW + timedelta(minutes=1)
    foreign = execute.build_kis_paper_portfolio_sell_plan(
        binding=binding,
        states=_states(io["state_root"], binding),
        expected_account_ref=ACCOUNT,
        expected_basis_ref=io["contract"].basis_ref,
        expected_owner_refs=_refs(binding),
        expected_binding_ref=_hash(binding),
        request_id="portfolio-sell-other-cohort",
        input_ref="sha256:" + "9" * 64,
        reductions_by_symbol=dict(SPY=D(1), TLT=D(0), GLD=D(0)),
        limits_by_symbol=dict(SPY=D(100)),
        as_of=at,
        valid_until=at + timedelta(minutes=1),
    )
    budget._atomic_json(io["state_root"] / budget.BUDGET_FILE, foreign.binding)
    exit_io, _ = _exit_args(io, client)
    before = (io["state_root"] / budget.BUDGET_FILE).read_bytes()
    with pytest.raises(leg.SingleEtfLegError, match="same_owner_lot_interference"):
        leg.reserve_single_etf_leg(**exit_io, phase="exit")
    assert (io["state_root"] / budget.BUDGET_FILE).read_bytes() == before
    assert entry.intents[0].quantity == 10
