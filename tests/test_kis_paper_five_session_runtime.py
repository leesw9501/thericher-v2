"""Synthetic canonical reservations and crash custody; no provider/client calls."""

from __future__ import annotations

import copy
import json
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import replace
from datetime import timedelta
from decimal import Context, Decimal, localcontext

import pytest

from test_kis_paper_five_session_successor import arguments, closed, entered
from test_kis_paper_stock_exit_plan import MASK
from test_kis_paper_stock_exit_plan import _arguments as exit_arguments
from test_kis_paper_stock_exit_plan import _observed as exit_observed
from test_kis_paper_stock_plan import AT, REFS
from test_kis_paper_stock_plan_reservation import _observed
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_five_session_runtime as runtime
from thericher_v2.execution import kis_paper_stock_exit_plan as exits
from thericher_v2.execution import kis_paper_stock_plan as entries
from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryStateStore
from thericher_v2.execution.kis_paper_fill_accounting import KisPaperExecutionObservation
from thericher_v2.execution.kis_paper_five_session import cohort_from_paper_decision
from thericher_v2.execution.kis_paper_five_session_history_store import (
    KisPaperFiveSessionHistoryStore,
)
from thericher_v2.research import five_session_paper_decision as paper
from thericher_v2.research.decision_receipt import receipt_from_target_exposure_proposal


@pytest.fixture(autouse=True)
def deny_operations(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("operational_api_forbidden")

    for obj, name in (
        (socket, "create_connection"),
        (socket.socket, "connect"),
        (urllib.request, "urlopen"),
        (urllib.request.OpenerDirector, "open"),
        (kis_readonly, "load_kis_paper_config"),
        (kis_readonly, "load_kis_paper_config_from_environment"),
    ):
        monkeypatch.setattr(obj, name, deny)


def finite_decision(args):
    first = args["cohort"].session_opens[0]
    completed, prior = first - timedelta(minutes=30), first - timedelta(days=1)
    pins = (("fixture", "sha256:" + "d" * 64),)
    frame, allocation, model = "sha256:" + "e" * 64, "ref:" + "f" * 64, REFS.model_ref
    input_ref = args["cohort"].source_ref
    cohort_ref = paper._ref(
        dict(
            campaign=REFS.campaign_ref,
            frame=frame[7:],
            input=input_ref,
            model=model,
            sources=pins,
            allocation=allocation,
            slot=0,
            instrument=args["cohort"].instrument.binding_ref,
        )
    )
    proposal_ref = paper._ref(
        dict(
            cohort=cohort_ref,
            completed=completed.isoformat(),
            valid_until=args["cohort"].entry_window_end.isoformat(),
            target=format(args["proposal"].target_exposure, "f"),
        )
    )
    proposal = replace(
        args["proposal"],
        proposal_id=proposal_ref,
        decided_at=completed,
        confidence=Decimal(1),
        feature_window_end=prior,
        feature_schema_id=paper.FEATURE_SCHEMA_ID,
    )
    receipt = receipt_from_target_exposure_proposal(
        proposal, references=replace(REFS, input_manifest_ref=input_ref, proposal_ref=proposal_ref)
    )
    dto = paper.FiveSessionPaperDecision(
        "prepared",
        "fixed_slot",
        cohort_ref,
        0,
        proposal.symbol + "/NAS",
        args["cohort"].instrument.binding_ref,
        frame,
        "sha256:" + "a" * 64,
        allocation,
        pins,
        input_ref,
        model,
        proposal_ref,
        first - timedelta(hours=1),
        prior,
        args["cohort"].session_opens,
        args["cohort"].session_closes,
        args["cohort"].entry_window_end,
        completed,
        completed,
        proposal,
        receipt,
    )
    cohort = cohort_from_paper_decision(dto, calendar_ref=args["cohort"].calendar_ref)
    return dto, cohort


class Bank:
    def __init__(self, tmp_path, args):
        self.args, self.at = args, args["as_of"]
        self.root = tmp_path / "bank"
        self.root.mkdir()
        self.repo, self.artifacts = tmp_path / "repo", tmp_path / "artifacts"
        budget._atomic_json(self.root / budget.BUDGET_FILE, args["binding"])
        for run, state in args["states"].items():
            budget._atomic_json(self.root / (run + ".json"), state.to_dict())
        self.store = KisPaperFiveSessionHistoryStore(
            tmp_path / "history", repository_root=self.repo, artifact_root=self.artifacts
        )
        self.reserved, self.executed, self.observed = [], [], []
        self.cancelled, self.read_calls, self.factories = [], [], []
        self.fault, self.observation = None, None
        self.exit_quantity = Decimal(10)

    def load(self):
        binding = budget._load_binding(self.root, self.args["expected_account_ref"])
        return runtime.LifecycleScope(
            binding,
            entries._states(self.root, binding),
            self.root,
            self.args["expected_account_ref"],
            self.args["expected_basis_ref"],
            MASK,
        )

    def reserve(self, side, args):
        journal = self.store.read()
        assert journal.pending is not None
        self.reserved.append(copy.deepcopy(args))
        if self.fault == "before_reserve":
            raise ValueError("PRIVATE-ORDER-SECRET")
        function = (
            entries.reserve_kis_paper_stock_plan
            if side == "buy"
            else exits.reserve_kis_paper_stock_exit_plan
        )
        result = function(
            state_root=self.root, repository_root=self.repo, artifact_root=self.artifacts, **args
        )
        if self.fault == "after_reserve":
            raise ValueError("PRIVATE-ORDER-SECRET")
        return result

    def execute(self, proof, clock):
        journal = self.store.read()
        assert journal.pending is None and journal.record_count >= 3
        self.executed.append(proof)
        seed = budget._stock_seed_states(self.load().binding)[proof.run_id]
        store = KisPaperCanaryStateStore(self.root / (proof.run_id + ".json"))
        store.record_intent(seed.intent, cancel_after_submit=False, now=clock())
        store.transition(
            seed.intent,
            expected=frozenset({"intent_recorded"}),
            phase="submission_started",
            reason_code="preview",
            now=clock(),
            submission_started_at=clock(),
        )
        if self.fault == "after_submission":
            raise ValueError("PRIVATE-ORDER-SECRET")

    def reads(self, side, instrument, clock):
        self.read_calls.append(side)
        if side == "buy":
            return self.args["reads"]
        source = exit_arguments()["reads"]
        at = clock()
        snapshot = source.snapshot
        return replace(
            source,
            started_at=at,
            completed_at=at,
            quote=replace(source.quote, quoted_at=at),
            snapshot=replace(
                snapshot,
                captured_at=at,
                identity=replace(snapshot.identity, captured_at=at),
                positions=tuple(
                    replace(p, captured_at=at, quantity=self.exit_quantity)
                    for p in snapshot.positions
                ),
                open_orders=replace(snapshot.open_orders, captured_at=at),
            ),
        )

    def observe(self, proof, clock):
        self.observed.append(proof)
        return runtime.LifecycleObservation(self.load(), None, None)

    def adapters(self):
        return runtime.LifecycleAdapters(
            self.load,
            self.reads,
            self.reserve,
            self.execute,
            self.observe,
            self.cancel,
            lambda _: True,
        )

    def cancel(self, directive, clock):
        self.cancelled.append(directive)

    def visit(
        self, decision=None, cohort=None, *, phase="enter", execute=True, owner_refs=None, **changes
    ):
        cohort = cohort or self.args["cohort"]
        return runtime.run_five_session_runtime(
            decision,
            cohort=cohort,
            expected_cohort_ref=cohort.fingerprint,
            history_store=self.store,
            history=self.args["history"],
            expected_history_refs=self.args["expected_history_refs"],
            expected_account_ref=self.args["expected_account_ref"],
            expected_basis_ref=self.args["expected_basis_ref"],
            expected_owner_refs=(
                runtime._owner_refs(self.load().binding) if owner_refs is None else owner_refs
            ),
            adapters=self.adapters(),
            phase=phase,
            clock=lambda: self.at,
            deadline=time.monotonic() + 30,
            execute=execute,
            **changes,
        )


def fresh_bank(tmp_path):
    args = arguments()
    dto, cohort = finite_decision(args)
    return Bank(tmp_path, args), dto, cohort


def test_default_is_inert_without_loading_or_writing(tmp_path):
    bank, dto, cohort = fresh_bank(tmp_path)
    assert bank.visit(dto, cohort, execute=False)["status"] == "inert"
    assert not bank.store.root.exists() and not bank.reserved and not bank.executed


def test_actual_reservation_committed_before_execute_and_exact_restart(tmp_path):
    bank, dto, cohort = fresh_bank(tmp_path)
    result = bank.visit(dto, cohort)
    assert result["execute_calls"] == 1, result
    assert len(bank.executed) == 1 and len(bank.reserved) == 1
    bank.at += timedelta(minutes=20)
    again = bank.visit(None, cohort, phase="recover")
    assert again["execute_calls"] == 0 and len(bank.executed) == 1, again
    assert again["action"] == "reconcile_unknown" and again["outcome_unknown"] is True
    meta = runtime.load_retained_runtime_metadata(bank.store, cohort.fingerprint)
    assert meta.decision == dto and meta.cohort == cohort
    assert runtime._proposal(meta.decision, meta.policy)[2] == cohort.instrument


def test_native_mandatory_delivery_argument_is_exact_current_scope(tmp_path, monkeypatch):
    bank, dto, cohort = fresh_bank(tmp_path)
    scoped, delivered = [], []
    validate_scope = runtime._scope

    def track_scope(*args, **kwargs):
        result = validate_scope(*args, **kwargs)
        scoped.append(result[0])
        return result

    def delivery(scope):
        assert type(scope) is runtime.LifecycleScope and scope is scoped[-1]
        canonical = bank.load()
        assert scope.binding == canonical.binding and scope.states == canonical.states
        assert (scope.state_root, scope.account_ref, scope.basis_ref) == (
            canonical.state_root, canonical.account_ref, canonical.basis_ref
        )
        if not delivered:
            assert not bank.store.root.exists() and not bank.reserved and not bank.read_calls
        else:
            with bank.store.root.joinpath("00000002.json").open() as handle:
                assert json.load(handle)["kind"] == "committed"
            assert not bank.executed
        delivered.append(scope)
        return True

    adapters = bank.adapters()
    monkeypatch.setattr(runtime, "_scope", track_scope)
    monkeypatch.setattr(bank, "adapters", lambda: replace(adapters, delivery=delivery))
    result = bank.visit(dto, cohort)
    assert result["execute_calls"] == 1 and len(delivered) == 2, result
    assert delivered[0] is not delivered[1]
    assert runtime._row(delivered[0].binding, cohort.instrument, cohort.entry_request_id) is None
    assert (
        runtime._row(delivered[1].binding, cohort.instrument, cohort.entry_request_id) is not None
    )


@pytest.mark.parametrize("fault", ["before_reserve", "after_reserve", "after_submission"])
def test_crash_boundary_restart_never_changes_seed_or_submits_twice(tmp_path, fault):
    bank, dto, cohort = fresh_bank(tmp_path)
    bank.fault = fault
    failed = bank.visit(dto, cohort)
    assert failed["status"] == "recovery" and "SECRET" not in json.dumps(failed)
    with bank.store.locked():
        journal = bank.store.read()
        expected = (
            journal.pending["row"]
            if journal.pending is not None
            else runtime._row(bank.load().binding, cohort.instrument, cohort.entry_request_id)
        )
    bank.fault = None
    again = bank.visit(None, cohort, phase="recover")
    assert len(bank.executed) == 1, again
    assert runtime._row(bank.load().binding, cohort.instrument, cohort.entry_request_id) == expected
    assert bank.executed[0].intent_ref == runtime._seed(expected).intent.fingerprint


@pytest.mark.parametrize("published", [False, True])
def test_commit_failure_after_reservation_forbids_execute_then_resumes(
    tmp_path, monkeypatch, published
):
    bank, dto, cohort = fresh_bank(tmp_path)
    commit = bank.store.commit

    def fault(ref):
        if published:
            commit(ref)
        raise OSError("secret")

    monkeypatch.setattr(bank.store, "commit", fault)
    failed = bank.visit(dto, cohort)
    assert failed["execute_calls"] == 0 and not bank.executed
    monkeypatch.setattr(bank.store, "commit", commit)
    resumed = bank.visit(None, cohort, phase="recover")
    assert resumed["execute_calls"] == 1 and len(bank.reserved) == 1, resumed


def test_two_closed_cohorts_then_third_entry_and_restart_preserve_whole_book(tmp_path):
    binding, states, history = closed(arguments())
    binding, states, history = closed(
        arguments(binding, states, history, at=AT + timedelta(days=7))
    )
    args = arguments(binding, states, history, at=AT + timedelta(days=14))
    dto, cohort = finite_decision(args)
    bank = Bank(tmp_path, args)
    before = copy.deepcopy(binding)
    result = bank.visit(dto, cohort)
    assert result["execute_calls"] == 1, result
    after = bank.load().binding
    assert after["basis_ref"] == before["basis_ref"]
    assert (
        after["stocks"][cohort.instrument.symbol]["plans"][:-1]
        == before["stocks"][cohort.instrument.symbol]["plans"]
    )
    assert all(after[k] == before[k] for k in before if k != "stocks")
    with bank.store.locked():
        journal = bank.store.read()
        assert len(journal.history) == 3 and journal.history[:2] == history
    bank.at += timedelta(minutes=20)
    assert bank.visit(None, cohort)["execute_calls"] == 0
    projection = budget.project_shared_budget(
        binding=after,
        states=bank.load().states,
        expected_account_ref=args["expected_account_ref"],
        expected_basis_ref=args["expected_basis_ref"],
        expected_owner_refs=runtime._owner_refs(after),
        as_of=bank.at,
    )
    assert projection.basis_usd == Decimal(10000) and projection.allocated_usd == Decimal(1000)
    assert projection.gross_cash == Decimal(980)


@pytest.mark.parametrize("phase", ["submission_started", "outcome_unknown", "submitted"])
def test_prior_unknown_partial_recovers_prior_policy_without_new_buy(tmp_path, phase):
    initial = arguments()
    from thericher_v2.execution.kis_paper_five_session_successor import (
        prepare_five_session_successor,
    )

    prepared = prepare_five_session_successor(**initial)
    intent = prepared.plan.intents[0]
    state = _observed(intent, phase=phase, filled="3", remaining="7", unavailable=True)
    args = arguments(
        prepared.plan.binding,
        initial["states"] | {intent.run_id: state},
        prepared.history,
        at=AT + timedelta(days=7),
    )
    bank = Bank(tmp_path, args)

    def factory(meta):
        bank.factories.append(meta)
        return bank.adapters()

    result = bank.visit(None, phase="recover", adapter_factory=factory)
    assert result["execute_calls"] == 0 and not bank.read_calls and not bank.reserved, result
    assert bank.observed[0].run_id == intent.run_id
    assert bank.factories[0].policy == runtime.horizon_policy(initial["cohort"])
    assert result["outcome_unknown"] is True


@pytest.mark.parametrize("day", [0, 1, 2, 3])
def test_first_four_session_closes_hold_without_sell(tmp_path, day):
    initial = arguments()
    binding, states, history = entered(initial)
    args = arguments(binding, states, history, at=AT + timedelta(days=7))
    bank = Bank(tmp_path, args)
    bank.at = initial["cohort"].session_closes[day]
    result = bank.visit(None, phase="close")
    assert result["status"] == "hold" and not bank.reserved and not bank.read_calls, result


@pytest.mark.parametrize("late", [False, True])
def test_fifth_due_or_missed_exit_sells_only_owned_segment(tmp_path, late):
    initial = arguments()
    binding, states, history = entered(initial)
    args = arguments(binding, states, history, at=AT + timedelta(days=7))
    bank = Bank(tmp_path, args)
    bank.at = (
        initial["cohort"].session_closes[-1] + timedelta(days=3)
        if late
        else initial["cohort"].exit_due
    )
    result = bank.visit(None, phase="close")
    assert len(bank.executed) == 1 and bank.executed[0].side == "sell", result
    intent = runtime._seed(
        runtime._row(bank.load().binding, initial["cohort"].instrument, bank.executed[0].request_id)
    ).intent
    assert intent.quantity == Decimal(10)
    assert intent.created_at == bank.at and intent.valid_until <= bank.at + timedelta(minutes=5)
    assert bank.executed[0].request_id == "five-exit-" + initial["cohort"].fingerprint[7:] + "-0"
    again = bank.visit(None, phase="recover")
    assert again["execute_calls"] == 0 and len(bank.executed) == 1
    assert again["action"] == "reconcile_unknown" and len(bank.observed) == 2, again


def test_registered_expired_seed_is_reconciled_not_aborted_or_replaced(tmp_path):
    bank, dto, cohort = fresh_bank(tmp_path)
    bank.fault = "after_reserve"
    bank.visit(dto, cohort)
    bank.fault = None
    bank.at += timedelta(days=1)
    result = bank.visit(None, cohort, phase="recover")
    assert result["execute_calls"] == 0 and result["local_expiry_calls"] == 1, result
    assert len(bank.reserved) == 1 and not bank.executed and not bank.observed
    state = next(
        s for s in bank.load().states.values() if s.intent.symbol == cohort.instrument.symbol
    )
    assert state.phase == "intent_recorded" and state.reason_code == "intent_expired"
    assert state.submission_started_at is None
    with bank.store.locked():
        journal = bank.store.read()
        assert journal.pending is None and len(journal.history) == 1
        assert journal.record_count == 3
    assert bank.visit(None, cohort, phase="recover")["execute_calls"] == 0


@pytest.mark.parametrize("confirmed", [False, True])
def test_partial_exit_requires_exact_terminal_reconciliation_before_residual(tmp_path, confirmed):
    initial = arguments()
    binding, states, history = entered(initial)
    args = arguments(binding, states, history, at=AT + timedelta(days=7))
    bank = Bank(tmp_path, args)
    bank.at = initial["cohort"].exit_due
    first = bank.visit(None, phase="close")
    assert first["execute_calls"] == 1
    proof = bank.executed[0]
    seed = budget._stock_seed_states(bank.load().binding)[proof.run_id]
    observed = exit_observed(
        seed.intent,
        filled="4",
        remaining="0" if confirmed else "6",
        phase="cancelled" if confirmed else "outcome_unknown",
    )
    budget._atomic_json(bank.root / (proof.run_id + ".json"), observed.to_dict())
    bank.at += timedelta(seconds=10)
    if confirmed:
        observation = KisPaperExecutionObservation(
            1, True, "available", observed.current_fill, observed.fill_observed_at, False
        )
        exits.reconcile_kis_paper_stock_exit_plan(
            state_root=bank.root,
            repository_root=bank.repo,
            artifact_root=bank.artifacts,
            expected_account_ref=proof.account_ref,
            expected_basis_ref=proof.basis_ref,
            expected_owner_refs=dict(proof.owner_refs),
            expected_binding_ref=proof.parent_binding_ref,
            request_id=proof.request_id,
            input_ref=proof.input_ref,
            instrument=proof.instrument,
            expected_plan_ref=proof.plan_ref,
            as_of=bank.at,
            cancellation_proofs={proof.run_id: observation},
        )
        bank.exit_quantity = Decimal(6)
    resumed = bank.visit(None, phase="recover")
    if confirmed:
        assert resumed["execute_calls"] == 1 and len(bank.executed) == 2, resumed
        final = bank.executed[-1]
        assert final.request_id.endswith("-1") and final.run_id != proof.run_id
        retained = budget._stock_seed_states(bank.load().binding)[final.run_id]
        assert retained.intent.quantity == Decimal(6)
    else:
        assert resumed["execute_calls"] == 0 and len(bank.reserved) == 1, resumed
        assert resumed["outcome_unknown"] is True and bank.observed[-1].run_id == proof.run_id


def test_foreign_same_symbol_position_is_not_sold_or_adopted(tmp_path):
    initial = arguments()
    binding, states, history = entered(initial)
    bank = Bank(tmp_path, arguments(binding, states, history, at=AT + timedelta(days=7)))
    bank.at = initial["cohort"].exit_due
    bank.exit_quantity = Decimal(11)
    before = (bank.root / budget.BUDGET_FILE).read_bytes()
    result = bank.visit(None, phase="close")
    assert result["reason"] == "owned_exit_unavailable" and not bank.executed and not bank.reserved
    assert (bank.root / budget.BUDGET_FILE).read_bytes() == before


def test_original_other_owner_reservation_and_prior_loss_remain_in_full_book(tmp_path):
    from test_kis_paper_portfolio_preview import _state

    other = _state(2, symbol="QQQ", pending=True, requested="2")
    initial = arguments(other_states=(other,))
    binding, states, history = closed(initial)
    args = arguments(binding, states, history, at=AT + timedelta(days=7))
    bank = Bank(tmp_path, args)
    dto, cohort = finite_decision(args)
    result = bank.visit(dto, cohort)
    assert result["execute_calls"] == 1, result
    after = bank.load().binding
    assert after["qqq"] == binding["qqq"] and after["basis_ref"] == binding["basis_ref"]
    projection = budget.project_shared_budget(
        binding=after,
        states=bank.load().states,
        expected_account_ref=args["expected_account_ref"],
        expected_basis_ref=args["expected_basis_ref"],
        expected_owner_refs=runtime._owner_refs(after),
        as_of=bank.at,
    )
    assert projection.gross_cash == Decimal(990) and projection.reserved_buys == Decimal(300)


def test_missing_prior_terminal_evidence_observes_exact_old_request(tmp_path):
    binding, states, history = closed(arguments())
    missing = history[0].custody.entry.run_id
    binding["terminal_evidence"].pop(missing)
    args = arguments(binding, states, history, at=AT + timedelta(days=7))
    bank = Bank(tmp_path, args)
    result = bank.visit(None, phase="recover")
    assert len(bank.observed) == 1 and bank.observed[0].run_id == missing, result
    assert not bank.reserved and not bank.executed


@pytest.mark.parametrize("mutation", ["omitted", "reordered", "wrong_input"])
def test_selected_history_conflict_never_sliced_or_adopted(tmp_path, mutation):
    binding, states, history = closed(arguments())
    binding, states, history = closed(
        arguments(binding, states, history, at=AT + timedelta(days=7))
    )
    if mutation == "omitted":
        history = history[1:]
    elif mutation == "reordered":
        history = tuple(reversed(history))
    args = arguments(binding, states, history, at=AT + timedelta(days=14))
    if mutation == "wrong_input":
        args["binding"]["stocks"][history[0].cohort.instrument.symbol]["plans"][0]["input_ref"] = (
            "sha256:" + "0" * 64
        )
    bank = Bank(tmp_path, args)
    before = (bank.root / budget.BUDGET_FILE).read_bytes()
    result = bank.visit(None, phase="recover", owner_refs=args["expected_owner_refs"])
    assert result["execute_calls"] == 0 and not bank.reserved and not bank.observed, result
    assert (bank.root / budget.BUDGET_FILE).read_bytes() == before


def test_valid_legacy_same_symbol_row_never_sliced_into_five_session_history(tmp_path):
    from test_kis_paper_stock_plan_reservation import _arguments

    old = _arguments()
    legacy = entries.build_kis_paper_stock_plan(**old)
    intent = legacy.intents[0]
    state = _observed(intent, filled=str(intent.quantity), remaining="0")
    binding = copy.deepcopy(legacy.binding)
    binding["terminal_evidence"][intent.run_id] = budget._terminal_payload(state)
    args = arguments(binding, old["states"] | {intent.run_id: state}, (), at=AT + timedelta(days=7))
    bank = Bank(tmp_path, args)
    before = (bank.root / budget.BUDGET_FILE).read_bytes()
    result = bank.visit(None, phase="recover")
    assert result["execute_calls"] == 0 and not bank.reserved and not bank.observed
    assert (bank.root / budget.BUDGET_FILE).read_bytes() == before


def test_expired_unreserved_prepared_seed_does_not_renew_ttl(tmp_path):
    bank, dto, cohort = fresh_bank(tmp_path)
    bank.fault = "before_reserve"
    bank.visit(dto, cohort)
    bank.fault = None
    bank.at += timedelta(days=1)
    result = bank.visit(None, cohort, phase="recover")
    assert result["reason"] == "unreserved_seed_expired" and not bank.executed
    assert len(bank.reserved) == 1
    with bank.store.locked():
        retired = bank.store.read()
        assert retired.pending is None and retired.history == () and retired.record_count == 3
    old_bytes = (bank.store.root / "00000001.json").read_bytes()
    bank.args = arguments(bank.load().binding, bank.load().states, (), at=AT + timedelta(days=7))
    bank.at = bank.args["as_of"]
    fresh, successor = finite_decision(bank.args)
    progressed = bank.visit(fresh, successor)
    assert progressed["execute_calls"] == 1 and len(bank.executed) == 1, progressed
    assert (bank.store.root / "00000001.json").read_bytes() == old_bytes
    assert bank.load().binding["basis_ref"] == bank.args["expected_basis_ref"]


@pytest.mark.parametrize("precision", [2, 28, 80])
def test_runtime_uses_fixed_context_without_mutating_ambient(tmp_path, precision):
    bank, dto, cohort = fresh_bank(tmp_path)
    with localcontext(Context(prec=precision)) as context:
        result = bank.visit(dto, cohort)
        assert context.prec == precision
    assert result["execute_calls"] == 1, result


def test_new_runtime_import_does_not_import_numerical_or_model_runtime():
    source = """
import importlib.abc, sys
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'numpy','torch','sklearn','pickle'} or fullname.endswith(
            ('.five_session_tree','.five_session_cohort')):
            raise AssertionError('forbidden_import')
sys.meta_path.insert(0,Deny())
import thericher_v2.execution.kis_paper_five_session_runtime
"""
    result = subprocess.run([sys.executable, "-B", "-c", source], capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode()
