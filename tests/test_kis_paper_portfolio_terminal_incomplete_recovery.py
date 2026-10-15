"""Native SYN recovery keeps old Paper outcomes distinct from new daily targets."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from test_kis_paper_current_daily_session import record
from test_kis_paper_current_daily_session import session as session
from test_kis_paper_portfolio_cycle import advance, checkpoint, mixed
from test_kis_paper_portfolio_cycle import call as call
from test_kis_paper_portfolio_cycle import owned as owned
from test_kis_paper_portfolio_execute import harness as harness
from test_kis_paper_portfolio_execute import (
    no_actual_provider_or_credentials as no_actual_provider_or_credentials,
)
from thericher_v2.execution import kis_paper_current_daily_session as daily

budget, canary, cycle = daily.budget, daily.canary, daily.cycle
D = Decimal


def state_store(call, intent):
    return canary.KisPaperCanaryStateStore(call["state_root"] / (intent.run_id + ".json"))


def rehash(value):
    value["ref"] = "sha256:" + budget._digest({k: v for k, v in value.items() if k != "ref"})
    return value


def forbid(*args, **kwargs):
    pytest.fail("unexpected_submit_data_or_credentials")


def cancellation_client(client, monkeypatch, *, proof=True, zero=False):
    original_request, original_reconcile = client.request, client.reconcile
    cancelled = []

    def request(packet):
        response = original_request(packet)
        if zero:
            order = client.orders[client.intent.run_id]
            client.funds -= order["filled"] * client.intent.limit_price
            order.update(filled=D(0), remaining=client.intent.quantity)
        return response

    def cancel(intent, *, broker_order_id):
        order = client.orders[intent.run_id]
        assert broker_order_id == order["id"]
        cancelled.append(intent)
        order["remaining"] = D(0)
        return True

    def reconcile(state, *, now):
        result = original_reconcile(state, now=now)
        if state.intent in cancelled and result.execution is not None and zero and proof:
            result = replace(result, execution=replace(
                result.execution, row_count=2, cancellation_confirmed=True,
            ))
        return result

    monkeypatch.setattr(client, "request", request)
    monkeypatch.setattr(client, "cancel_order", cancel)
    monkeypatch.setattr(client, "reconcile", reconcile)
    return cancelled


@pytest.mark.parametrize("zero", (False, True))
def test_expired_exact_sell_cancel_retains_partial_or_zero_proof(call, monkeypatch, zero):
    mixed(call)
    client = call["client"]
    client.partial = True
    cancelled = cancellation_client(client, monkeypatch, zero=zero)
    assert advance(call).status == "pending"
    intent = client.submits[0]
    terms = checkpoint(call).read_bytes()
    original = budget._load_binding(call["state_root"])
    client.now += timedelta(minutes=10)
    monkeypatch.setattr(client, "submit_limit", forbid)
    assert advance(call).status == "pending"
    assert cancelled == [intent] and len(client.wire) == 1
    result = advance(call)
    assert (result.status, result.reason) == ("terminal_incomplete", "cycle_terminal_incomplete")
    assert not checkpoint(call, "buy.json").exists() and checkpoint(call).read_bytes() == terms
    binding = budget._load_binding(call["state_root"])
    assert binding["basis_ref"] == original["basis_ref"]
    assert binding["allocated_usd"] == original["allocated_usd"]
    terminal = binding["terminal_evidence"][intent.run_id]
    assert (terminal["cancellation"] is not None) is zero
    saved = state_store(call, intent).read()
    assert saved.intent == intent and saved.current_fill.quantity == D(not zero)
    assert budget._terminal(saved, None if not zero else cycle._project(
        call["state_root"], binding, client.now
    )[2][intent.run_id])


def test_expired_zero_cancel_without_exact_proof_remains_pending(call, monkeypatch):
    mixed(call)
    client = call["client"]
    client.partial = True
    cancellation_client(client, monkeypatch, zero=True, proof=False)
    advance(call)
    intent = client.submits[0]
    client.now += timedelta(minutes=10)
    advance(call)
    assert advance(call).status == "pending"
    assert intent.run_id not in budget._load_binding(call["state_root"])["terminal_evidence"]
    assert not checkpoint(call, "buy.json").exists() and len(client.wire) == 1


def test_zero_cancel_proof_is_recovered_after_retention_crash_without_recancel(call, monkeypatch):
    mixed(call)
    client = call["client"]
    client.partial = True
    cancelled = cancellation_client(client, monkeypatch, zero=True)
    advance(call)
    intent = client.submits[0]
    client.now += timedelta(minutes=10)
    original = cycle._reconcile_stage

    def interrupted(*args, **kwargs):
        raise OSError("SYN-after-cancel-before-terminal-retention")

    monkeypatch.setattr(cycle, "_reconcile_stage", interrupted)
    with pytest.raises(OSError):
        advance(call)
    assert state_store(call, intent).read().phase == "cancelled"
    assert intent.run_id not in budget._load_binding(call["state_root"])["terminal_evidence"]
    monkeypatch.setattr(cycle, "_reconcile_stage", original)
    monkeypatch.setattr(client, "cancel_order", forbid)
    assert advance(call).status == "pending"
    assert advance(call).status == "terminal_incomplete"
    assert cancelled == [intent] and len(client.wire) == 1


def test_uncertain_cancel_resumes_only_after_exact_positive_open_observation(call, monkeypatch):
    mixed(call)
    client = call["client"]
    client.partial = True
    cancelled = cancellation_client(client, monkeypatch)
    exact_cancel = client.cancel_order
    advance(call)
    intent = client.submits[0]
    client.now += timedelta(minutes=10)

    def interrupted(*args, **kwargs):
        raise canary.KisPaperCanaryError("cancel_transport_unknown")

    monkeypatch.setattr(client, "cancel_order", interrupted)
    assert advance(call).status == "pending"
    assert state_store(call, intent).read().phase == "outcome_unknown"
    monkeypatch.setattr(client, "cancel_order", exact_cancel)
    monkeypatch.setattr(client, "submit_limit", forbid)
    assert advance(call).status == "pending"
    assert advance(call).status == "terminal_incomplete"
    assert cancelled == [intent] and len(client.wire) == 1


def test_exact_provider_rejection_is_terminal_incomplete_not_target_success(call, monkeypatch):
    mixed(call)

    def rejected(request):
        raise canary.KisPaperSubmitRejected()

    monkeypatch.setattr(call["client"], "request", rejected)
    assert advance(call).status == "pending"
    assert advance(call).status == "terminal_incomplete"
    assert not checkpoint(call, "buy.json").exists()


@pytest.mark.parametrize("fault", ("foreign", "stale", "incomplete", "history_unavailable"))
def test_expired_cancel_requires_fresh_exact_account_and_fill(call, monkeypatch, fault):
    mixed(call)
    client = call["client"]
    client.partial = True
    cancelled = cancellation_client(client, monkeypatch)
    advance(call)
    client.now += timedelta(minutes=10)
    setattr(client, fault, True)
    try:
        advance(call)
    except (cycle._RecoveryRequired, ValueError):
        pass
    assert not cancelled and len(client.wire) == 1
    assert not checkpoint(call, "buy.json").exists()


def test_unknown_attempt_cannot_cancel_expire_or_create_another_leg(call, monkeypatch):
    mixed(call)
    client = call["client"]
    client.unknown = client.partial = True
    advance(call)
    before = copy.deepcopy(budget._load_binding(call["state_root"]))
    client.now += timedelta(days=1)
    monkeypatch.setattr(client, "cancel_order", forbid)
    monkeypatch.setattr(client, "submit_limit", forbid)
    for _ in range(3):
        assert advance(call).status == "pending"
    assert budget._load_binding(call["state_root"]) == before
    assert len(client.wire) == 1 and not checkpoint(call, "buy.json").exists()


def test_expired_unattempted_seeds_close_without_submit_or_expiry_renewal(call, monkeypatch):
    call["weights_by_symbol"] = dict.fromkeys(cycle.SYMBOLS, D(".1"))
    advance(call)
    client = call["client"]
    terms = checkpoint(call).read_bytes()
    plan = budget._read_json(checkpoint(call))["sell"]["proposed"]["portfolio"]["plans"][-1]
    seeds = budget._portfolio_seed_states(budget._load_binding(call["state_root"]))
    client.now += timedelta(minutes=10)
    monkeypatch.setattr(client, "submit_limit", forbid)
    for _ in range(3):
        result = advance(call)
    assert result.status == "terminal_incomplete" and len(client.wire) == 1
    binding = budget._load_binding(call["state_root"])
    assert set(plan["states"]) <= set(binding["terminal_evidence"])
    for run in plan["states"]:
        state = state_store(call, seeds[run].intent).read()
        assert state.intent == seeds[run].intent
        if state.submission_started_at is None:
            assert state.reason_code == "intent_expired"
            assert state.updated_at >= state.intent.valid_until
    assert checkpoint(call).read_bytes() == terms and not checkpoint(call, "buy.json").exists()


def test_missing_unattempted_journal_with_lock_witness_cannot_be_retired(call):
    call["weights_by_symbol"] = dict.fromkeys(cycle.SYMBOLS, D(".1"))
    advance(call)
    binding = budget._load_binding(call["state_root"])
    plan = binding["portfolio"]["plans"][-1]
    run = next(r for r in plan["states"]
               if not (call["state_root"] / (r + ".json")).exists())
    (call["state_root"] / ("." + run + ".json.lock")).touch()
    call["client"].now += timedelta(minutes=10)
    with pytest.raises(cycle._RecoveryRequired, match="portfolio_materialized_state_missing"):
        advance(call)
    assert not (call["state_root"] / (run + ".json")).exists()
    assert budget._load_binding(call["state_root"]) == binding


@pytest.fixture
def incomplete(session):
    args, control, loads = session
    control = replace(control, weights_by_symbol=dict.fromkeys(cycle.SYMBOLS, D(".1")))
    args["data_loader"] = lambda: control
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    args["client"].now += timedelta(minutes=10)
    for _ in range(3):
        result = daily.run_kis_paper_current_daily_session(**args)
    assert (result.status, result.reason) == ("no_intent", "terminal_cycle_incomplete")
    retained = record(session)
    assert retained["version"] == 2 and retained["terminal_state"] == "incomplete"
    assert retained["completed"] is False
    return args, control, retained, daily._incomplete_path(args["state_root"], retained)


def later_control(args, control, **changes):
    shift = timedelta(days=1)
    args["client"].now += shift
    value = replace(control, input_ref="sha256:" + "e" * 64,
                    control_ref="sha256:" + "a" * 64,
                    session_date=control.session_date + shift,
                    target_as_of=control.target_as_of + shift,
                    available_at=control.available_at + shift,
                    valid_until=control.valid_until + shift, **changes)
    args["data_loader"] = lambda: value
    return value


def test_terminal_incomplete_restart_same_day_never_reloads_or_claims_complete(incomplete):
    args, _, retained, path = incomplete
    before = path.read_bytes()
    pointer = args["state_root"] / daily.POINTER
    frozen = pointer.read_bytes()
    args["data_loader"] = forbid
    for _ in range(2):
        result = daily.run_kis_paper_current_daily_session(**args)
        assert (result.status, result.reason) == ("no_intent", "terminal_cycle_incomplete")
    assert path.read_bytes() == before and pointer.read_bytes() == frozen
    assert budget._read_json(path)["record"] == retained


@pytest.mark.parametrize("kind", ["is_symlink", "is_junction"])
def test_archive_restart_rejects_redirected_lock_before_acquisition(incomplete, monkeypatch, kind):
    args, _, _, archive = incomplete
    lock = archive.parent / "..advance.lock"
    sentinel = args["state_root"].parent / "owned-sentinel"
    sentinel.write_bytes(b"unchanged")
    original_flag = getattr(Path, kind)
    monkeypatch.setattr(Path, kind, lambda p: p == lock or original_flag(p))
    original_lock = daily.canary.exclusive_kis_paper_canary_state_lock
    acquired = []

    def trap_acquisition(path):
        if path == archive.parent / ".advance":
            acquired.append(path)
            sentinel.write_bytes(b"redirected-lock-write")
        return original_lock(path)

    monkeypatch.setattr(daily.canary, "exclusive_kis_paper_canary_state_lock", trap_acquisition)
    args["data_loader"] = forbid
    before = archive.read_bytes(), (args["state_root"] / daily.POINTER).read_bytes()
    wire_count = len(args["client"].wire)
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.status == "unavailable" and not acquired
    assert sentinel.read_bytes() == b"unchanged"
    assert before == (archive.read_bytes(), (args["state_root"] / daily.POINTER).read_bytes())
    assert len(args["client"].wire) == wire_count


def test_archive_write_crash_recovers_incomplete_marker_without_data(session, monkeypatch):
    args, control, _ = session
    control = replace(control, weights_by_symbol=dict.fromkeys(cycle.SYMBOLS, D(".1")))
    args["data_loader"] = lambda: control
    daily.run_kis_paper_current_daily_session(**args)
    args["client"].now += timedelta(minutes=10)
    daily.run_kis_paper_current_daily_session(**args)
    daily.run_kis_paper_current_daily_session(**args)
    original = cycle._record

    def interrupted(path, value):
        if path.name == "terminal-incomplete.json":
            raise OSError("SYN-archive-write-interrupted")
        return original(path, value)

    monkeypatch.setattr(cycle, "_record", interrupted)
    assert daily.run_kis_paper_current_daily_session(**args).status == "unavailable"
    retained = record(session)
    assert retained["terminal_state"] == "incomplete" and not retained["completed"]
    monkeypatch.setattr(cycle, "_record", original)
    args["data_loader"] = forbid
    assert daily.run_kis_paper_current_daily_session(**args).reason == "terminal_cycle_incomplete"
    assert record(session) == retained
    assert daily._incomplete_path(args["state_root"], retained).exists()


def test_fresh_later_daily_input_rolls_forward_without_reset_or_old_artifact_mutation(incomplete):
    args, control, retained, archive = incomplete
    evidence = {p: p.read_bytes() for p in archive.parent.glob("*.json")}
    before = budget._load_binding(args["state_root"])
    current = later_control(args, control)
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.status in {"pending", "complete"}
    updated = budget._read_json(args["state_root"] / daily.POINTER)
    assert updated["context"]["native"]["session_id"] == current.session_id
    assert updated["context"]["expected_basis_ref"] == retained["context"]["expected_basis_ref"]
    binding = budget._load_binding(args["state_root"])
    for key in ("basis_ref", "basis_usd", "allocated_usd", "orders", "qqq"):
        assert binding[key] == before[key]
    assert all(p.read_bytes() == raw for p, raw in evidence.items())


def test_rollover_write_crash_retains_archive_and_original_pointer(incomplete, monkeypatch):
    args, control, retained, archive = incomplete
    later_control(args, control)
    original = budget._atomic_json
    frozen = archive.read_bytes()

    def interrupted(path, payload):
        if path.name == daily.POINTER:
            raise OSError("SYN-new-pointer-write-interrupted")
        return original(path, payload)

    monkeypatch.setattr(budget, "_atomic_json", interrupted)
    assert daily.run_kis_paper_current_daily_session(**args).status == "unavailable"
    assert budget._read_json(args["state_root"] / daily.POINTER) == retained
    assert archive.read_bytes() == frozen and len(args["client"].wire) == 1
    monkeypatch.setattr(budget, "_atomic_json", original)
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    assert len(args["client"].wire) == 2 and archive.read_bytes() == frozen


def test_direct_rollover_rechecks_fresh_session_before_snapshot(incomplete, monkeypatch):
    args, _, retained, _ = incomplete
    proposal = daily._record(copy.deepcopy(retained["context"]))
    monkeypatch.setattr(args["client"], "snapshot", forbid)
    with pytest.raises(ValueError):
        daily._rollover_incomplete(
            args["state_root"], args["state_root"] / daily.POINTER, retained, proposal,
            retained["context"]["paths"], retained["context"]["expected_account_ref"],
            args["client"], args["clock"],
        )


def test_new_context_requires_no_global_buy_reservation(incomplete, monkeypatch):
    args, control, retained, _ = incomplete
    later_control(args, control)
    original = cycle._project

    def reserved(*a, **k):
        states, replayed, proofs, projection = original(*a, **k)
        return states, replayed, proofs, replace(projection, reserved_buys=D(1))

    monkeypatch.setattr(cycle, "_project", reserved)
    assert daily.run_kis_paper_current_daily_session(**args).status == "unavailable"
    assert budget._read_json(args["state_root"] / daily.POINTER) == retained


def test_different_account_cannot_roll_over_retained_basis(incomplete):
    args, control, retained, _ = incomplete
    later_control(args, control)
    args["client"]._config = replace(args["client"]._config, account_number="87654321")
    assert daily.run_kis_paper_current_daily_session(**args).status == "unavailable"
    assert budget._read_json(args["state_root"] / daily.POINTER) == retained


@pytest.mark.parametrize("witness", ("cycle", "journal_lock"))
def test_future_context_existing_native_witness_cannot_be_replaced(
    incomplete, monkeypatch, witness,
):
    args, control, retained, _ = incomplete
    current = later_control(args, control)
    binding = budget._load_binding(args["state_root"])
    context = copy.deepcopy(retained["context"])
    native = current.native_arguments()
    context["native"].update(
        session_id=native["session_id"], input_ref=native["input_ref"],
        control_ref=native["control_ref"], target_as_of=native["target_as_of"].isoformat(),
    )
    context.update(expected_binding_ref="sha256:" + budget._digest(binding),
                   expected_owner_refs={o.owner_ref: pin for o, pin in budget._owners(binding)},
                   available_at=current.available_at.isoformat(),
                   valid_until=current.valid_until.isoformat())
    if witness == "cycle":
        directory = daily._incomplete_path(args["state_root"], daily._record(context)).parent
        budget._atomic_json(directory / "cycle.json", {"synthetic": True})
    else:
        run = next(iter(daily._preintent_request_runs(context)[1]))
        (args["state_root"] / ("." + run + ".json.lock")).touch()
    monkeypatch.setattr(args["client"], "snapshot", forbid)
    assert daily.run_kis_paper_current_daily_session(**args).status == "unavailable"
    assert budget._read_json(args["state_root"] / daily.POINTER) == retained


@pytest.mark.parametrize("field", ("input_ref", "session_date", "target_as_of"))
def test_same_input_session_or_daily_target_cannot_roll_forward(incomplete, field):
    args, control, _, archive = incomplete
    current = later_control(args, control)
    if field == "session_date":
        current = replace(current, session_date=control.session_date,
                          control_ref=control.control_ref)
    else:
        current = replace(current, **{field: getattr(control, field)})
    args["data_loader"] = lambda: current
    before = (args["state_root"] / daily.POINTER).read_bytes()
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.reason == "terminal_cycle_incomplete" and result.status == "no_intent"
    assert (args["state_root"] / daily.POINTER).read_bytes() == before and archive.exists()


@pytest.mark.parametrize("fault", ("foreign", "duplicate_position", "incomplete", "stale"))
def test_rollover_requires_current_owned_quantity_agreement(incomplete, fault):
    args, control, _, archive = incomplete
    later_control(args, control)
    setattr(args["client"], fault, True)
    before = (args["state_root"] / daily.POINTER).read_bytes()
    frozen = archive.read_bytes()
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.status == "unavailable"
    assert (args["state_root"] / daily.POINTER).read_bytes() == before
    assert archive.read_bytes() == frozen


@pytest.mark.parametrize("fault", ("archive", "cycle", "terminal_evidence", "basis"))
def test_mutated_retained_proof_blocks_only_new_context(incomplete, fault):
    args, control, retained, archive = incomplete
    later_control(args, control)
    if fault in {"archive", "cycle"}:
        path = archive if fault == "archive" else archive.parent / "cycle.json"
        value = budget._read_json(path)
        value["ref"] = "sha256:" + "0" * 64
        budget._atomic_json(path, value)
    else:
        binding = budget._load_binding(args["state_root"])
        if fault == "terminal_evidence":
            binding["terminal_evidence"].pop(next(iter(binding["terminal_evidence"])))
        else:
            binding["basis_ref"] = "sha256:" + "0" * 64
        budget._atomic_json(args["state_root"] / budget.BUDGET_FILE, binding)
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.status == "unavailable"
    assert budget._read_json(args["state_root"] / daily.POINTER) == retained


def test_v1_pointer_remains_valid_and_v2_incomplete_cannot_claim_success(incomplete):
    _, _, retained, _ = incomplete
    paths = retained["context"]["paths"]
    account = retained["context"]["expected_account_ref"]
    legacy = copy.deepcopy(retained)
    legacy["version"] = 1
    legacy.pop("terminal_state")
    daily._validate(rehash(legacy), paths, account)
    broken = dict(retained, completed=True)
    with pytest.raises(ValueError):
        daily._validate(rehash(broken), paths, account)
    assert "terminal_state" not in json.dumps(daily.CurrentDailySessionOutcome(
        "no_intent", "terminal_cycle_incomplete"
    ).safe_payload())
