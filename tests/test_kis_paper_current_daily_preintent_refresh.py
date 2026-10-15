"""Native SYN checks for refreshing one retained, unstarted daily context."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_current_daily_session import PATHS
from test_kis_paper_current_daily_session import mixed_control as mixed_control
from test_kis_paper_current_daily_session import session as session
from test_kis_paper_portfolio_cycle import CycleClient
from test_kis_paper_portfolio_cycle import call as call
from test_kis_paper_portfolio_cycle import owned as owned
from test_kis_paper_portfolio_execute import _leg
from test_kis_paper_portfolio_execute import harness as harness
from test_kis_paper_portfolio_execute import (
    no_actual_provider_or_credentials as no_actual_provider_or_credentials,
)
from test_kis_paper_portfolio_preview import _reads, _scope
from test_kis_paper_stock_budget_binding import _binding as stock_binding
from test_kis_paper_stock_budget_binding import _submitted as stock_submitted
from thericher_v2.execution import kis_paper_current_daily_session as daily
from thericher_v2.execution.kis_paper_portfolio_plan import (
    build_kis_paper_portfolio_plan,
    reconcile_kis_paper_portfolio_plan,
)
from thericher_v2.research.kis_paper_current_daily_control import CurrentDailyControl

D = Decimal
PRIVATE = "SYN-private-error-body-must-not-escape"
FAILURES = (ValueError, daily.cycle._RecoveryRequired)


def forbidden(*args, **kwargs):
    pytest.fail("unexpected_data_or_callback")


def pointer_path(args):
    return args["state_root"] / daily.POINTER


def pointer_record(args):
    return daily.budget._read_json(pointer_path(args))


def rehash(record):
    record["ref"] = "sha256:" + daily.budget._digest(
        {k: v for k, v in record.items() if k != "ref"}
    )
    return record


def book(args):
    return daily.budget._load_binding(args["state_root"])


def book_bytes(args):
    return (args["state_root"] / daily.budget.BUDGET_FILE).read_bytes()


def directory(args, record):
    c = record["context"]
    key = daily.budget._digest(
        [c["expected_account_ref"], c["expected_basis_ref"], c["native"]["session_id"]]
    )
    return args["state_root"] / ".portfolio_cycles" / key


def refreshed_context(record, binding):
    return dict(
        record["context"],
        expected_binding_ref="sha256:" + daily.budget._digest(binding),
        expected_owner_refs={o.owner_ref: pin for o, pin in daily.budget._owners(binding)},
    )


def refresh(args, record=None):
    record = pointer_record(args) if record is None else record
    c = record["context"]
    root = args["state_root"]
    with daily.canary.exclusive_kis_paper_canary_state_lock(
        root / ".current_daily_portfolio_worker"
    ):
        return daily._refresh_preintent_context(
            record,
            root=root,
            pointer=pointer_path(args),
            paths=c["paths"],
            account=c["expected_account_ref"],
            clock=args["clock"],
        )


@pytest.fixture
def preintent(harness, monkeypatch):
    """A real daily pointer predates native completion of another registered plan."""
    original_client = harness["client"]
    scope = _scope()
    control = CurrentDailyControl(
        "sha256:" + "d" * 64,
        "sha256:" + "c" * 64,
        original_client.now.date(),
        scope["target_as_of"],
        original_client.now - timedelta(minutes=10),
        original_client.now.replace(hour=20, minute=0, second=0),
        scope["weights_by_symbol"],
        scope["covariance_by_symbol"],
    )
    loads = []

    def loader():
        loads.append(True)
        return control

    def before_native_checkpoint():
        raise RuntimeError("SYN-read-before-checkpoint")

    monkeypatch.setattr(daily, "build_current_daily_control", lambda value, as_of: value)
    args = {k: harness[k] for k in PATHS}
    args.update(
        client=original_client,
        data_loader=loader,
        reads_factory=before_native_checkpoint,
        clock=lambda: original_client.now,
        execute=True,
    )
    first = daily.run_kis_paper_current_daily_session(**args)
    assert first.status == "unavailable" and loads == [True]
    old = copy.deepcopy(pointer_record(args))
    assert old["cycle_ref"] is None and old["completed"] is False
    assert not (directory(args, old) / "cycle.json").exists()
    assert original_client.submits == []

    for symbol in daily.cycle.SYMBOLS:
        daily.execution.execute_kis_paper_portfolio_buy(**_leg(harness, symbol))
    proof = harness["proof"]
    closed = reconcile_kis_paper_portfolio_plan(
        state_root=harness["state_root"],
        repository_root=harness["repository_root"],
        artifact_root=harness["artifact_root"],
        expected_account_ref=proof.account_ref,
        expected_basis_ref=proof.basis_ref,
        expected_owner_refs=dict(proof.owner_refs),
        request_id=proof.request_id,
        expected_plan_ref=proof.plan_ref,
        as_of=original_client.now,
    )
    assert closed.status == "reconciled"
    client = CycleClient(original_client)

    def reads_factory():
        base = _reads(spy=D(0), funds=client.funds)
        rows = tuple(
            replace(
                row,
                quote=replace(row.quote, quoted_at=client.now),
                cash=replace(row.cash, captured_at=client.now),
                orderable=replace(row.orderable, captured_at=client.now),
            )
            for row in base.instruments
        )
        return replace(
            base,
            account_ref=proof.account_ref,
            snapshot=client.snapshot(),
            instruments=rows,
            started_at=client.now,
            completed_at=client.now,
        )

    args.update(
        client=client, clock=lambda: client.now, reads_factory=reads_factory, data_loader=forbidden
    )
    assert book(args)["basis_ref"] == old["context"]["expected_basis_ref"]
    assert "sha256:" + daily.budget._digest(book(args)) != old["context"]["expected_binding_ref"]
    return args, old, loads


def add_stock_owner(args, *, phase="terminal"):
    binding = copy.deepcopy(book(args))
    extra, seed = stock_binding(quantity="1", price="50", account=binding["account_ref"])
    assert extra["basis_ref"] == binding["basis_ref"]
    binding.update(version=4, stocks=copy.deepcopy(extra["stocks"]))
    plan = binding["stocks"]["AAPL"]["plans"][0]
    plan["parent_binding_ref"] = "sha256:" + daily.budget._digest(book(args))
    state = (
        seed
        if phase == "reserved"
        else stock_submitted(
            seed,
            quantity="1",
            amount="50",
            unknown=phase == "unknown",
        )
    )
    if phase == "terminal":
        binding["terminal_evidence"][seed.intent.run_id] = daily.budget._terminal_payload(state)
    daily.budget._atomic_json(args["state_root"] / daily.budget.BUDGET_FILE, binding)
    if phase != "reserved":
        daily.budget._atomic_json(
            args["state_root"] / (seed.intent.run_id + ".json"), state.to_dict()
        )
    if phase == "terminal":
        args["client"].orders[seed.intent.run_id] = dict(
            intent=seed.intent,
            id="SYN-added-stock",
            filled=seed.intent.quantity,
            remaining=D(0),
        )
        args["client"].funds -= D(50)
        args["client"].exact_funds = args["client"].funds
    checked = book(args)
    daily.cycle._project(args["state_root"], checked, args["clock"]())
    return checked, state


def native_plan(args, context, side, symbol="SPY", *, quantity=1):
    binding = book(args)
    at = args["clock"]()
    requests, _ = daily._preintent_request_runs(context)
    request = next(r for r in requests if r.startswith("portfolio-" + side + "-"))
    common = dict(
        binding=binding,
        states=daily.cycle._project(args["state_root"], binding, at)[0],
        expected_account_ref=binding["account_ref"],
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={o.owner_ref: pin for o, pin in daily.budget._owners(binding)},
        expected_binding_ref="sha256:" + daily.budget._digest(binding),
        request_id=request,
        input_ref=context["native"]["input_ref"],
        as_of=at,
        valid_until=at + timedelta(minutes=5),
    )
    if side == "sell":
        result = daily.execution.build_kis_paper_portfolio_sell_plan(
            **common,
            reductions_by_symbol={
                s: D(quantity if s == symbol else 0) for s in daily.cycle.SYMBOLS
            },
            limits_by_symbol={symbol: D(100)},
        )
    else:
        result = build_kis_paper_portfolio_plan(
            **common,
            reads=args["reads_factory"](),
            weights_by_symbol={s: D(".4") if s == symbol else D(".3") for s in daily.cycle.SYMBOLS},
            covariance_by_symbol=daily._native(context)["covariance_by_symbol"],
            target_as_of=daily._native(context)["target_as_of"],
        )
    assert result.status == "prepared"
    return result


def test_real_pointer_refresh_preserves_all_context_book_owners_and_restart(preintent):
    args, old, loads = preintent
    binding, stock = add_stock_owner(args)
    before = book_bytes(args)
    old_refs = old["context"]["expected_owner_refs"]
    result = refresh(args)
    assert result == pointer_record(args) and result != old
    assert len(result["context"]["expected_owner_refs"]) == len(old_refs) + 1
    assert result["context"] == refreshed_context(old, binding)
    assert result["cycle_ref"] is None and result["completed"] is False
    assert book_bytes(args) == before and stock.intent.run_id in book(args)["terminal_evidence"]
    before_pointer = pointer_path(args).read_bytes()
    assert refresh(args) == result
    assert pointer_path(args).read_bytes() == before_pointer
    native_result = daily.run_kis_paper_current_daily_session(**args)
    assert native_result.status == "complete", native_result.safe_payload()
    assert pointer_record(args)["context"] == result["context"]
    assert book_bytes(args) == before and loads == [True] and args["client"].submits == []


def test_preintent_contract_equals_real_native_checkpoint_and_run_identities(preintent):
    args, _, _ = preintent
    updated = refresh(args)
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.status == "complete"
    checkpoint = daily.budget._read_json(directory(args, updated) / "cycle.json")
    assert daily._preintent_contract(updated["context"]) == checkpoint["contract"]
    requests, runs = daily._preintent_request_runs(updated["context"])
    digest = daily.budget._digest(checkpoint["contract"])
    assert requests == {"portfolio-buy-" + digest, "portfolio-sell-" + digest}
    generated = set()
    for side in ("buy", "sell"):
        for symbol in daily.cycle.SYMBOLS:
            plan = native_plan(args, updated["context"], side, symbol)
            assert plan.binding["portfolio"]["plans"][-1]["request_id"] in requests
            generated.update(plan.binding["portfolio"]["plans"][-1]["states"])
    assert runs == generated and len(generated) == 6


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_registered_original_plan_without_disk_state_prevents_refresh(preintent, side):
    args, old, _ = preintent
    plan = native_plan(args, old["context"], side)
    daily.budget._atomic_json(args["state_root"] / daily.budget.BUDGET_FILE, plan.binding)
    added = set(plan.binding["portfolio"]["plans"][-1]["states"])
    assert added <= set(daily.budget._portfolio_seed_states(book(args)))
    assert not any((args["state_root"] / (r + ".json")).exists() for r in added)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    with pytest.raises(FAILURES):
        refresh(args)
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


@pytest.mark.parametrize("phase", ["unknown", "partial", "filled_unreconciled"])
def test_original_registered_outcome_is_never_rebound_or_reissued(preintent, phase):
    args, old, _ = preintent
    plan = native_plan(args, old["context"], "sell", quantity=2)
    payload = next(iter(plan.binding["portfolio"]["plans"][-1]["states"].values()))
    seed = daily.canary.KisPaperCanaryState.from_dict(payload)
    state = stock_submitted(
        seed,
        quantity="2" if phase == "filled_unreconciled" else "1",
        amount="200" if phase == "filled_unreconciled" else "100",
        unknown=phase == "unknown",
    )
    daily.budget._atomic_json(args["state_root"] / daily.budget.BUDGET_FILE, plan.binding)
    state_path = args["state_root"] / (seed.intent.run_id + ".json")
    daily.budget._atomic_json(state_path, state.to_dict())
    assert seed.intent.run_id in daily.budget._portfolio_seed_states(book(args))
    before = pointer_path(args).read_bytes(), book_bytes(args), state_path.read_bytes()
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.status == "unavailable"
    assert (pointer_path(args).read_bytes(), book_bytes(args), state_path.read_bytes()) == before
    assert args["client"].submits == []


@pytest.mark.parametrize("scope", ["original", "proposed"])
@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("symbol", ["SPY", "TLT", "GLD"])
def test_native_registered_seed_collision_old_and_proposed_scope_before_commit(
    preintent,
    monkeypatch,
    scope,
    side,
    symbol,
):
    args, old, _ = preintent
    binding = book(args)
    context = old["context"] if scope == "original" else refreshed_context(old, binding)
    plan = native_plan(args, context, side, symbol)
    runs = set(plan.binding["portfolio"]["plans"][-1]["states"])
    assert runs <= daily._preintent_request_runs(context)[1]
    native_project = daily.cycle._project
    before = pointer_path(args).read_bytes()

    def concurrent_registered_seed(root, observed_binding, at):
        assert observed_binding == binding
        daily.budget._atomic_json(root / daily.budget.BUDGET_FILE, plan.binding)
        assert not any((root / (r + ".json")).exists() for r in runs)
        current = daily.budget._load_binding(root)
        return native_project(root, current, at)

    monkeypatch.setattr(daily.cycle, "_project", concurrent_registered_seed)
    with pytest.raises(FAILURES):
        refresh(args)
    assert pointer_path(args).read_bytes() == before
    assert book(args) == plan.binding


@pytest.mark.parametrize("stage", ["cycle.json", "buy.json", "sell.json", ".binding-crash.tmp"])
def test_existing_stage_skips_refresh_without_loading_book(preintent, monkeypatch, stage):
    args, old, _ = preintent
    target = directory(args, old) / stage
    daily.budget._atomic_json(target, {"synthetic_partial": True})
    before = pointer_path(args).read_bytes(), target.read_bytes()
    monkeypatch.setattr(daily.budget, "_load_binding", forbidden)
    assert refresh(args) == old
    assert (pointer_path(args).read_bytes(), target.read_bytes()) == before


@pytest.mark.parametrize("completed", [False, True])
def test_cycle_ref_present_returns_before_book_load(preintent, monkeypatch, completed):
    args, old, _ = preintent
    retained = rehash(dict(old, cycle_ref="sha256:" + "e" * 64, completed=completed))
    daily.budget._atomic_json(pointer_path(args), retained)
    monkeypatch.setattr(daily.budget, "_load_binding", forbidden)
    monkeypatch.setattr(daily.cycle, "_shared", forbidden)
    assert refresh(args) == retained


def test_stage_present_pointer_without_ref_preserves_real_pending_native_recovery(session):
    args = mixed_control(session)
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    original = copy.deepcopy(pointer_record(args))
    first_intent = args["client"].submits[0]
    retained = rehash(dict(original, cycle_ref=None))
    daily.budget._atomic_json(pointer_path(args), retained)
    assert refresh(args) == retained
    args["data_loader"] = forbidden
    for _ in range(4):
        result = daily.run_kis_paper_current_daily_session(**args)
        if result.status == "complete":
            break
    assert result.status == "complete"
    assert pointer_record(args)["context"] == original["context"]
    assert pointer_record(args)["cycle_ref"] == original["cycle_ref"]
    assert args["client"].submits.count(first_intent) == 1


@pytest.mark.parametrize("fault", ["expired", "basis", "orphan", "pointer_hash"])
def test_invalid_expired_basis_or_orphan_never_commits(preintent, fault):
    args, old, _ = preintent
    if fault == "expired":
        args["client"].now = daily.datetime.fromisoformat(old["context"]["valid_until"])
    elif fault == "basis":
        binding = book(args)
        binding["basis_usd"] = "20000"
        binding["allocated_usd"] = "2000"
        binding["basis_ref"] = daily.budget._basis(binding).fingerprint
        daily.budget._atomic_json(args["state_root"] / daily.budget.BUDGET_FILE, binding)
    elif fault == "orphan":
        daily.budget._atomic_json(args["state_root"] / ("bp-" + "f" * 64 + ".json"), {})
    else:
        old["ref"] = "sha256:" + "0" * 64
        daily.budget._atomic_json(pointer_path(args), old)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    with pytest.raises(FAILURES):
        refresh(args)
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


@pytest.mark.parametrize("phase", ["reserved", "unknown"])
def test_unrelated_reservation_or_unknown_is_not_erased_or_replaced(preintent, phase):
    args, _, _ = preintent
    _, state = add_stock_owner(args, phase=phase)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    assert state.intent.run_id in daily.budget._stock_seed_states(book(args))
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.status == "unavailable"
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before
    assert args["client"].submits == []


@pytest.mark.parametrize("changed", ["pointer", "book"])
def test_second_snapshot_change_before_commit_is_rejected(preintent, monkeypatch, changed):
    args, old, _ = preintent
    before = pointer_path(args).read_bytes(), book_bytes(args)
    native_project = daily.cycle._project

    def project_then_change(root, binding, at):
        result = native_project(root, binding, at)
        if changed == "pointer":
            altered = rehash(dict(old, cycle_ref="sha256:" + "9" * 64))
            daily.budget._atomic_json(pointer_path(args), altered)
        else:
            add_stock_owner(args)
        return result

    if changed == "book":
        original_add = add_stock_owner

        def native_add(args):
            monkeypatch.setattr(daily.cycle, "_project", native_project)
            return original_add(args)

        monkeypatch.setitem(globals(), "add_stock_owner", native_add)
    monkeypatch.setattr(daily.cycle, "_project", project_then_change)
    with pytest.raises(FAILURES):
        refresh(args)
    if changed == "pointer":
        assert book_bytes(args) == before[1]
        assert pointer_record(args)["cycle_ref"] == "sha256:" + "9" * 64
    else:
        assert pointer_path(args).read_bytes() == before[0]
        assert "AAPL" in book(args)["stocks"]


def test_expiry_at_final_commit_check_does_not_roll_ttl(preintent):
    args, old, _ = preintent
    until = daily.datetime.fromisoformat(old["context"]["valid_until"])
    ticks = iter((args["client"].now, until))
    args["clock"] = lambda: next(ticks)
    before = pointer_path(args).read_bytes(), book_bytes(args)
    with pytest.raises(FAILURES):
        refresh(args)
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before


@pytest.mark.parametrize("fault", ["write", "readback"])
def test_pointer_write_or_readback_failure_is_unavailable_and_restart_safe(
    preintent, monkeypatch, fault
):
    args, old, _ = preintent
    before = book_bytes(args)
    native_write = daily.budget._atomic_json
    native_read = daily.budget._read_json
    wrote = []

    def write(path, payload):
        if path == pointer_path(args):
            if fault == "write":
                raise OSError(PRIVATE)
            native_write(path, payload)
            wrote.append(True)
        else:
            native_write(path, payload)

    def read(path):
        if path == pointer_path(args) and wrote:
            raise OSError(PRIVATE)
        return native_read(path)

    monkeypatch.setattr(daily.budget, "_atomic_json", write)
    monkeypatch.setattr(daily.budget, "_read_json", read)
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.status == "unavailable" and PRIVATE not in json.dumps(result.safe_payload())
    assert book_bytes(args) == before and args["client"].submits == []
    monkeypatch.setattr(daily.budget, "_atomic_json", native_write)
    monkeypatch.setattr(daily.budget, "_read_json", native_read)
    saved = pointer_record(args)
    assert (
        saved == old if fault == "write" else saved["context"] == refreshed_context(old, book(args))
    )
    assert daily.run_kis_paper_current_daily_session(**args).status == "complete"
    assert book_bytes(args) == before


def test_unstructured_refresh_error_does_not_format_or_leak_exception(preintent, monkeypatch):
    args, _, _ = preintent

    class NoText(RuntimeError):
        def __str__(self):
            raise AssertionError("error_text_must_not_be_inspected")

    def fail(*a, **k):
        raise NoText(PRIVATE)

    before = pointer_path(args).read_bytes(), book_bytes(args)
    monkeypatch.setattr(daily.cycle, "_project", fail)
    result = daily.run_kis_paper_current_daily_session(**args)
    assert result.reason == "retained_context_recovery_required"
    assert PRIVATE not in json.dumps(result.safe_payload())
    assert set(result.safe_payload()) == {"kind", "status", "reason", "limitation"}
    assert (pointer_path(args).read_bytes(), book_bytes(args)) == before
