"""Isolated synthetic stock ownership and persist-before-wire execution."""

from __future__ import annotations

import socket
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_portfolio_execute import ACCOUNT, CONFIG, SyntheticPaperClient
from test_kis_paper_portfolio_preview import NOW
from test_kis_paper_stock_budget_binding import REF, _binding
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_stock_execute as execute
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
from thericher_v2.execution.kis_paper_stock_canary import KisPaperStockCanaryClient
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument

D = Decimal


@pytest.fixture(autouse=True)
def no_actual_wire(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic stock executor cannot access wire or credentials")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", forbidden)
    monkeypatch.setattr(canary.UrllibKisPaperCanaryTransport, "request", forbidden)


class SyntheticStockClient(KisPaperStockCanaryClient):
    def __init__(self, root, instrument):
        super().__init__(config=CONFIG, transport=None, instrument=instrument)
        self.__dict__.update(SyntheticPaperClient(root).__dict__)

    snapshot = SyntheticPaperClient.snapshot
    orderable_funds_at_limit = SyntheticPaperClient.orderable_funds_at_limit
    reconcile = SyntheticPaperClient.reconcile
    cancel_order = SyntheticPaperClient.cancel_order

    def submit_limit(self, intent, **kwargs):
        state = canary.KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.intent == intent and state.phase == "submission_started"
        binding = budget._load_binding(self.root, ACCOUNT)
        assert budget._stock_seed_states(binding)[intent.run_id].intent == intent
        projection = budget.project_budget(
            self.root, binding, as_of=self.now, stock_symbol=intent.symbol
        )
        assert projection.entry_cost + projection.reserved_buys <= D(binding["allocated_usd"])
        self.submits.append(intent)
        filled = D(1) if self.partial else intent.quantity
        self.orders[intent.run_id] = dict(
            intent=intent,
            id=str(100 + len(self.submits)),
            filled=filled,
            remaining=intent.quantity - filled,
        )
        if self.unknown:
            raise canary.KisPaperCanaryError("submit_transport_unknown")
        self.funds -= filled * intent.limit_price
        self.exact_funds = self.funds
        return True, self.orders[intent.run_id]["id"]


@pytest.fixture
def harness(tmp_path):
    root = tmp_path / "p"
    binding, seed = _binding(account=ACCOUNT)
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    instrument = KisPaperStockInstrument("AAPL", REF)
    plan = binding["stocks"]["AAPL"]["plans"][0]
    proof = execute.KisPaperStockExecutionBinding(
        state_root=root.resolve(),
        instrument=instrument,
        account_ref=ACCOUNT,
        basis_ref=binding["basis_ref"],
        owner_refs=tuple((o.owner_ref, ref) for o, ref in budget._owners(binding)),
        binding_ref="sha256:" + budget._digest(binding),
        request_id=plan["request_id"],
        parent_binding_ref=plan["parent_binding_ref"],
        input_ref=plan["input_ref"],
        plan_ref="sha256:" + budget._digest(plan),
        run_id=seed.intent.run_id,
        intent_ref=seed.intent.fingerprint,
    )
    client = SyntheticStockClient(root, instrument)
    return dict(
        proof=proof,
        state_root=root,
        client=client,
        execute=True,
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        execution_control_path=tmp_path / "control.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        clock=lambda: client.now,
    )


def state(call):
    return canary.KisPaperCanaryStateStore(
        call["state_root"] / (call["proof"].run_id + ".json")
    ).read()


def test_exact_stock_executes_once_and_replays_owned_fill(harness):
    original_basis = budget._load_binding(harness["state_root"])["basis_ref"]
    first = execute.execute_kis_paper_stock_buy(**harness)
    assert first.phase == "submitted" and len(harness["client"].submits) == 1
    retained = state(harness)
    assert retained.cumulative_fill.status == "filled"
    assert retained.intent.client_order_id.startswith("stock-")
    second = execute.execute_kis_paper_stock_buy(**harness)
    assert second.phase == "submitted" and len(harness["client"].submits) == 1
    assert state(harness).intent == retained.intent
    binding = budget._load_binding(harness["state_root"])
    assert binding["basis_ref"] == original_basis
    assert (
        budget.project_budget(
            harness["state_root"], binding, as_of=NOW, stock_symbol="AAPL"
        ).quantity
        == retained.intent.quantity
    )


def test_unknown_submission_keeps_identity_and_never_reissues(harness):
    harness["client"].unknown = True
    execute.execute_kis_paper_stock_buy(**harness)
    original = state(harness)
    assert original.phase == "outcome_unknown"
    execute.execute_kis_paper_stock_buy(**harness)
    assert len(harness["client"].submits) == 1
    assert state(harness).intent == original.intent


def test_partial_fill_survives_later_unavailable_observation(harness):
    harness["client"].partial = True
    execute.execute_kis_paper_stock_buy(**harness)
    first = state(harness)
    assert first.cumulative_fill.quantity == D(1)
    harness["client"].history_unavailable = True
    execute.execute_kis_paper_stock_buy(**harness)
    assert state(harness).cumulative_fill == first.cumulative_fill
    assert len(harness["client"].submits) == 1


@pytest.mark.parametrize("field", ["input_ref", "binding_ref", "plan_ref", "intent_ref"])
def test_wrong_proof_never_materializes_or_calls_client(harness, field):
    harness["proof"] = replace(harness["proof"], **{field: "sha256:" + "f" * 64})
    with pytest.raises(_RecoveryRequired):
        execute.execute_kis_paper_stock_buy(**harness)
    assert harness["client"].submits == [] and harness["client"].limit_reads == []
    assert not (harness["state_root"] / (harness["proof"].run_id + ".json")).exists()


@pytest.mark.parametrize("fault", ["wrong_limit", "stale", "incomplete"])
def test_call_time_funds_and_account_failure_never_submits(harness, fault):
    setattr(harness["client"], fault, True)
    with pytest.raises((_RecoveryRequired, ValueError)):
        execute.execute_kis_paper_stock_buy(**harness)
    assert harness["client"].submits == []
    assert state(harness).submission_started_at is None


def test_expiry_after_funds_read_does_not_submit(harness):
    harness["client"].on_limit_read = lambda: setattr(
        harness["client"], "now", NOW + timedelta(minutes=2)
    )
    execute.execute_kis_paper_stock_buy(**harness)
    assert harness["client"].submits == []


def test_unrelated_foreign_holding_is_not_adopted_or_a_global_pause(harness):
    harness["client"].foreign = True
    execute.execute_kis_paper_stock_buy(**harness)
    assert len(harness["client"].submits) == 1
    binding = budget._load_binding(harness["state_root"])
    assert (
        budget.project_budget(
            harness["state_root"], binding, as_of=NOW, qqq_cycle_id=binding["qqq"]["cycle_id"]
        ).quantity
        == 0
    )


def test_unattempted_stock_is_not_bare_canary_submit_permission(harness):
    proof = harness["proof"]
    binding = budget._load_binding(harness["state_root"])
    intent = budget._stock_seed_states(binding)[proof.run_id].intent
    assert canary._conflicts_with_owned_spy_cycle(harness["state_root"], intent)
    assert not execute.allows_kis_paper_stock_execution(
        harness["state_root"], intent.run_id, intent.symbol, proof
    )


def test_default_inert(harness):
    harness["execute"] = False
    assert execute.execute_kis_paper_stock_buy(**harness) is None
    assert harness["client"].submits == []
