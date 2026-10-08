from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_portfolio_execute import ACCOUNT
from test_kis_paper_portfolio_execute import (
    harness as harness,
)
from test_kis_paper_portfolio_execute import (
    no_actual_provider_or_credentials as no_actual_provider_or_credentials,
)
from test_kis_paper_portfolio_preview import _reads, _scope
from test_kis_paper_portfolio_preview import _state as historical_state
from test_kis_paper_portfolio_sell import SellClient
from test_kis_paper_portfolio_sell import owned as owned
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_portfolio_cycle as cycle
from thericher_v2.execution import kis_paper_portfolio_execute as execution
from thericher_v2.execution.kis_paper_portfolio_plan import reconcile_kis_paper_portfolio_plan
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
from thericher_v2.execution.kis_readonly import KisHttpResponse

D = Decimal


class CycleClient(SellClient):
    require_cycle = True

    def request(self, request):
        if self.intent.side == "sell":
            return super().request(request)
        canary.validate_kis_paper_canary_request(request)
        assert request.headers["tr_id"] == canary.KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        self.wire.append(request)
        intent = self.intent
        order_id = str(400 + len(self.wire))
        filled = D(1) if self.partial else intent.quantity
        self.orders[intent.run_id] = dict(
            intent=intent, id=order_id, filled=filled, remaining=intent.quantity - filled
        )
        self.funds -= filled * intent.limit_price
        self.exact_funds = self.funds
        if self.unknown:
            raise canary.KisPaperCanaryError("submit_transport_unknown")
        return KisHttpResponse.from_payload({"rt_cd": "0", "output": {"ODNO": order_id}})

    def submit_limit(self, intent, **kwargs):
        path = self.root / (intent.run_id + ".json")
        state = canary.KisPaperCanaryStateStore(path).read()
        assert state.phase == "submission_started" and state.intent == intent
        if self.require_cycle:
            assert self.root.joinpath(".portfolio_cycles").exists()
        self.submits.append(intent)
        self.intent = intent
        return canary.KisPaperCanaryClient.submit_limit(self, intent, **kwargs)


@pytest.fixture
def call(owned):
    client = CycleClient(owned["client"])
    binding = budget._load_binding(owned["state_root"])
    reads = []

    def factory():
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
        result = replace(
            base,
            account_ref=ACCOUNT,
            snapshot=client.snapshot(),
            instruments=rows,
            started_at=client.now,
            completed_at=client.now,
        )
        reads.append((copy.deepcopy(budget._load_binding(client.root)), len(client.wire)))
        return result

    control = _scope()
    return dict(
        state_root=owned["state_root"],
        repository_root=owned["repository_root"],
        artifact_root=owned["artifact_root"],
        runtime_projection_path=owned["runtime_projection_path"],
        paper_account_snapshot_path=owned["paper_account_snapshot_path"],
        emergency_state_path=owned["emergency_state_path"],
        execution_control_path=owned["execution_control_path"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={o.owner_ref: ref for o, ref in budget._owners(binding)},
        expected_binding_ref="sha256:" + budget._digest(binding),
        session_id="synthetic-session",
        input_ref="sha256:" + "d" * 64,
        control_ref="sha256:" + "c" * 64,
        weights_by_symbol=control["weights_by_symbol"],
        covariance_by_symbol=control["covariance_by_symbol"],
        target_as_of=control["target_as_of"],
        reads_factory=factory,
        client=client,
        clock=lambda: client.now,
        execute=True,
        _reads=reads,
    )


def advance(call, **changes):
    return cycle.advance_kis_paper_portfolio_cycle(
        **{k: v for k, v in call.items() if k != "_reads"}, **changes
    )


def checkpoint(call, name="cycle.json"):
    key = budget._digest([ACCOUNT, call["expected_basis_ref"], call["session_id"]])
    return call["state_root"] / ".portfolio_cycles" / key / name


def mixed(call):
    call["weights_by_symbol"] = dict(SPY=D(".11"), TLT=D(".41"), GLD=D(".41"))


def test_inert(call, monkeypatch):
    def deny(*a, **kw):
        pytest.fail("inert must not read or create anything")

    monkeypatch.setattr(budget, "_load_binding", deny)
    call["execute"] = False
    assert advance(call).status == "inert"
    assert not checkpoint(call).exists() and not call["client"].wire


def test_no_delta(call):
    before = (call["state_root"] / budget.BUDGET_FILE).read_bytes()
    first = advance(call)
    assert first.status == "complete" and first.reason == "no_target_delta" and first.leg_count == 0
    frozen = checkpoint(call).read_bytes()
    call["expected_cycle_ref"] = first.cycle_ref
    again = advance(call)
    assert again == first and checkpoint(call).read_bytes() == frozen
    assert (call["state_root"] / budget.BUDGET_FILE).read_bytes() == before
    assert len(call["_reads"]) == 2 and not call["client"].wire
    assert first.cycle_ref not in json.dumps(first.safe_payload()) + repr(first)


def test_sell_fresh_funds_buy(call):
    mixed(call)
    original = budget._load_binding(call["state_root"])
    first = advance(call)
    assert (first.status, first.stage) == ("pending", "sell")
    assert [(i.side, i.symbol, i.quantity) for i in call["client"].submits] == [
        ("sell", "SPY", D(2))
    ]
    record = checkpoint(call).read_bytes()
    call["expected_cycle_ref"] = first.cycle_ref
    for _ in range(4):
        result = advance(call)
        if result.status == "complete":
            break
    assert result.status == "complete"
    assert [(i.side, i.symbol, i.quantity) for i in call["client"].submits] == [
        ("sell", "SPY", D(2)),
        ("buy", "TLT", D(1)),
        ("buy", "GLD", D(1)),
    ]
    assert checkpoint(call).read_bytes() == record
    after = budget._load_binding(call["state_root"])
    assert after["basis_ref"] == original["basis_ref"] and after["orders"] == original["orders"]
    assert after["qqq"] == original["qqq"] and len(after["portfolio"]["plans"]) == 3
    for read_book, wire_count in call["_reads"][1:]:
        sell = read_book["portfolio"]["plans"][1]
        assert all(run in read_book["terminal_evidence"] for run in sell["states"])
        assert wire_count >= 1
    count = len(call["client"].wire)
    assert advance(call).status == "complete" and len(call["client"].wire) == count


@pytest.mark.parametrize("unknown", [False, True])
def test_partial_or_unknown_never_funds_buy(call, unknown):
    mixed(call)
    call["client"].partial, call["client"].unknown = True, unknown
    first = advance(call)
    terms = checkpoint(call).read_bytes()
    call["client"].now += timedelta(minutes=10)
    for _ in range(2):
        assert advance(call).stage == "sell"
    assert len(call["client"].wire) == 1 and not checkpoint(call, "buy.json").exists()
    assert checkpoint(call).read_bytes() == terms and len(call["_reads"]) == 1
    assert first.stage == "sell" and not call["client"].limit_reads


def test_sell_only(call):
    call["weights_by_symbol"] = dict(SPY=D(".2"), TLT=D(".2"), GLD=D(".2"))
    # First reduce all three; each invocation advances only one original leg.
    for expected in ("SPY", "TLT", "GLD"):
        assert advance(call).stage == "sell"
        assert call["client"].submits[-1].symbol == expected
    assert advance(call).status == "complete"
    assert len(call["client"].wire) == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_account_ref", "0" * 64),
        ("expected_basis_ref", "sha256:" + "0" * 64),
        ("expected_owner_refs", {}),
        ("expected_binding_ref", "sha256:" + "0" * 64),
    ],
)
def test_independent_custody(call, field, value):
    call[field] = value
    with pytest.raises(_RecoveryRequired):
        advance(call)
    assert not call["client"].wire and not call["_reads"]


@pytest.mark.parametrize(
    "change",
    ["input_ref", "control_ref", "weights_by_symbol", "covariance_by_symbol", "target_as_of"],
)
def test_frozen_contract(call, change):
    advance(call)
    before = checkpoint(call).read_bytes()
    if change in {"input_ref", "control_ref"}:
        call[change] = "sha256:" + "f" * 64
    elif change == "weights_by_symbol":
        call[change] = dict(SPY=D(".3"), TLT=D(".3"), GLD=D(".3"))
    elif change == "covariance_by_symbol":
        call[change] = {
            s: {t: D(".000002") if s == t else D(0) for t in call[change]} for s in call[change]
        }
    else:
        call[change] -= timedelta(seconds=1)
    with pytest.raises(_RecoveryRequired, match="cycle_contract_conflict"):
        advance(call)
    assert checkpoint(call).read_bytes() == before and not call["client"].wire


def test_foreign_inventory(call):
    call["client"].foreign = True
    with pytest.raises(_RecoveryRequired):
        advance(call)
    assert not checkpoint(call).exists() and not call["client"].wire


def test_pre_reservation_crash(call, monkeypatch):
    mixed(call)
    original = budget._atomic_json

    def fail(path, payload):
        if path.name == budget.BUDGET_FILE:
            raise OSError("synthetic crash before reservation")
        return original(path, payload)

    monkeypatch.setattr(budget, "_atomic_json", fail)
    with pytest.raises(OSError):
        advance(call)
    before = checkpoint(call).read_bytes()
    proposal = budget._read_json(checkpoint(call))["sell"]["proposed"]
    intent = next(
        s.intent
        for run, s in budget._portfolio_seed_states(proposal).items()
        if run in proposal["portfolio"]["plans"][-1]["states"]
    )
    monkeypatch.setattr(budget, "_atomic_json", original)
    call["client"].now += timedelta(seconds=30)
    assert advance(call).stage == "sell"
    assert call["client"].submits == [intent] and checkpoint(call).read_bytes() == before
    assert len(call["_reads"]) == 1


def test_frozen_buy_pre_reservation(call, monkeypatch):
    mixed(call)
    advance(call)
    original = budget._atomic_json

    def fail(path, payload):
        if path.name == budget.BUDGET_FILE and len(payload["portfolio"]["plans"]) == 3:
            raise OSError("synthetic crash before BUY reservation")
        return original(path, payload)

    monkeypatch.setattr(budget, "_atomic_json", fail)
    with pytest.raises(OSError):
        advance(call)
    before = checkpoint(call, "buy.json").read_bytes()
    monkeypatch.setattr(budget, "_atomic_json", original)
    call["client"].now += timedelta(seconds=30)
    assert advance(call).stage == "buy"
    assert checkpoint(call, "buy.json").read_bytes() == before
    assert len(call["_reads"]) == 2


def test_target_tamper(call):
    advance(call)
    record = budget._read_json(checkpoint(call))
    record["targets"]["SPY"] = "0"
    budget._atomic_json(checkpoint(call), record)
    with pytest.raises(_RecoveryRequired, match="cycle_contract_conflict"):
        advance(call)
    assert not call["client"].wire


def test_book_mutation(call):
    mixed(call)
    advance(call)
    binding = budget._load_binding(call["state_root"])
    binding["qqq"]["cycle_id"] = "foreign-custody"
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    budget._atomic_json(call["state_root"] / budget.BUDGET_FILE, binding)
    with pytest.raises(_RecoveryRequired):
        advance(call)
    assert len(call["client"].wire) == 1


def test_buy_only(call):
    call["client"].require_cycle = False
    binding = budget._load_binding(call["state_root"])
    states = cycle._states(call["state_root"], binding)
    proposed = execution.build_kis_paper_portfolio_sell_plan(
        binding=binding,
        states=states,
        expected_account_ref=ACCOUNT,
        expected_basis_ref=call["expected_basis_ref"],
        expected_owner_refs=call["expected_owner_refs"],
        expected_binding_ref=call["expected_binding_ref"],
        request_id="portfolio-sell-synthetic-predecessor",
        input_ref=call["input_ref"],
        reductions_by_symbol=dict.fromkeys(("SPY", "TLT", "GLD"), D(1)),
        limits_by_symbol=dict.fromkeys(("SPY", "TLT", "GLD"), D(100)),
        as_of=call["client"].now,
        valid_until=call["client"].now + timedelta(minutes=5),
    )
    budget._atomic_json(call["state_root"] / budget.BUDGET_FILE, proposed.binding)
    paths = {
        k: call[k]
        for k in (
            "repository_root",
            "artifact_root",
            "runtime_projection_path",
            "paper_account_snapshot_path",
            "emergency_state_path",
            "execution_control_path",
        )
    }
    plan = proposed.binding["portfolio"]["plans"][-1]
    for intent in proposed.intents:
        execution.execute_kis_paper_portfolio_sell(
            proof=cycle._proof(call["state_root"], proposed.binding, plan, intent),
            state_root=call["state_root"],
            client=call["client"],
            clock=call["clock"],
            execute=True,
            **paths,
        )
    closed = reconcile_kis_paper_portfolio_plan(
        state_root=call["state_root"],
        repository_root=call["repository_root"],
        artifact_root=call["artifact_root"],
        expected_account_ref=ACCOUNT,
        expected_basis_ref=call["expected_basis_ref"],
        expected_owner_refs={o.owner_ref: ref for o, ref in budget._owners(proposed.binding)},
        request_id=plan["request_id"],
        expected_plan_ref=proposed.plan_ref,
        as_of=call["client"].now,
    )
    call["expected_binding_ref"] = "sha256:" + budget._digest(closed.binding)
    call["expected_owner_refs"] = {o.owner_ref: ref for o, ref in budget._owners(closed.binding)}
    call["client"].submits.clear()
    call["client"].wire.clear()
    call["client"].require_cycle = True
    for symbol in ("SPY", "TLT", "GLD"):
        assert advance(call).stage == "buy"
        assert call["client"].submits[-1].symbol == symbol
    assert advance(call).status == "complete"
    assert len(call["client"].wire) == 3 and all(
        i.side == "buy" and i.quantity == D(1) for i in call["client"].submits
    )


def test_baseline_not_borrowed(call):
    binding = budget._load_binding(call["state_root"])
    baseline = historical_state(30)
    budget._atomic_json(call["state_root"] / (baseline.intent.run_id + ".json"), baseline.to_dict())
    binding["orders"].append(
        dict(run_id=baseline.intent.run_id, intent_ref=baseline.intent.fingerprint, closed=True)
    )
    binding["terminal_evidence"][baseline.intent.run_id] = budget._terminal_payload(baseline)
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    budget._atomic_json(call["state_root"] / budget.BUDGET_FILE, binding)
    call["client"].orders[baseline.intent.run_id] = dict(
        intent=baseline.intent, id=baseline.broker_order_id, filled=D(1), remaining=D(0)
    )
    call["expected_binding_ref"] = "sha256:" + budget._digest(binding)
    call["expected_owner_refs"] = {o.owner_ref: ref for o, ref in budget._owners(binding)}
    call["weights_by_symbol"] = dict(SPY=D(0), TLT=D(".4"), GLD=D(".4"))
    result = advance(call)
    assert result.status == "unavailable" and result.reason == "baseline_reduction_required"
    assert not checkpoint(call).exists() and not call["client"].wire


def test_expired_original_proposal(call, monkeypatch):
    mixed(call)
    original = budget._atomic_json
    monkeypatch.setattr(
        budget,
        "_atomic_json",
        lambda path, payload: (
            (_ for _ in ()).throw(OSError("synthetic"))
            if path.name == budget.BUDGET_FILE
            else original(path, payload)
        ),
    )
    with pytest.raises(OSError):
        advance(call)
    terms = checkpoint(call).read_bytes()
    monkeypatch.setattr(budget, "_atomic_json", original)
    call["client"].now += timedelta(minutes=10)
    assert advance(call).stage == "sell"
    with pytest.raises(_RecoveryRequired, match="cycle_terminal_incomplete"):
        advance(call)
    assert checkpoint(call).read_bytes() == terms
    assert not call["client"].wire and len(call["_reads"]) == 1


def test_partial_later_full_recovery(call):
    mixed(call)
    call["client"].partial = True
    advance(call)
    original = call["client"].submits[0]
    order = call["client"].orders[original.run_id]
    call["client"].funds += (original.quantity - order["filled"]) * original.limit_price
    order.update(filled=original.quantity, remaining=D(0))
    call["client"].partial = False
    assert advance(call).stage == "sell"
    assert len(call["client"].wire) == 1 and len(call["_reads"]) == 1
    for _ in range(4):
        result = advance(call)
        if result.status == "complete":
            break
    assert result.status == "complete" and len(call["client"].wire) == 3
    assert call["client"].submits[0] == original


def test_after_sell_target_not_resized(call):
    mixed(call)
    advance(call)
    original = call["reads_factory"]

    def changed():
        reads = original()
        rows = tuple(
            replace(
                row,
                quote=replace(row.quote, last=D(200), best_bid=D("199.99"), best_ask=D(200)),
                buy_limit=D(200),
                orderable=replace(row.orderable, reference_price=D(200)),
            )
            for row in reads.instruments
        )
        return replace(reads, instruments=rows)

    call["reads_factory"] = changed
    result = advance(call)
    assert result.status == "unavailable" and result.reason == "target_quantization_changed"
    assert len(call["client"].wire) == 1 and not checkpoint(call, "buy.json").exists()


def test_baseline_spy_plus_two_portfolio_sleeves(call):
    binding = budget._load_binding(call["state_root"])
    plan = binding["portfolio"]["plans"][0]
    run = next(
        run
        for run, seed in budget._portfolio_seed_states(binding).items()
        if seed.intent.symbol == "SPY"
    )
    del plan["states"][run]
    binding["terminal_evidence"].pop(run)
    del call["client"].orders[run]
    (call["state_root"] / (run + ".json")).unlink()
    (call["state_root"] / ("." + run + ".json.lock")).unlink()
    baseline = historical_state(30, requested="3", filled="3")
    baseline = replace(
        baseline, cumulative_fill=replace(baseline.cumulative_fill, gross_amount=D(300))
    )
    budget._atomic_json(call["state_root"] / (baseline.intent.run_id + ".json"), baseline.to_dict())
    binding["orders"].append(
        dict(run_id=baseline.intent.run_id, intent_ref=baseline.intent.fingerprint, closed=True)
    )
    binding["terminal_evidence"][baseline.intent.run_id] = budget._terminal_payload(baseline)
    for owner, _ in budget._owners(binding):
        if owner.owner_ref == "spy-baseline":
            binding["spy_owner_ref"] = owner.fingerprint
        elif owner.owner_ref.startswith("portfolio-"):
            binding["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    budget._atomic_json(call["state_root"] / budget.BUDGET_FILE, binding)
    call["client"].orders[baseline.intent.run_id] = dict(
        intent=baseline.intent, id=baseline.broker_order_id, filled=D(3), remaining=D(0)
    )
    call["expected_binding_ref"] = "sha256:" + budget._digest(binding)
    call["expected_owner_refs"] = {o.owner_ref: ref for o, ref in budget._owners(binding)}
    assert advance(call).status == "complete"
    assert not call["client"].wire and budget._load_binding(call["state_root"]) == binding


def test_book_changes_after_reservation(call, monkeypatch):
    mixed(call)
    original = cycle._reserve

    def concurrent_change(root, stage, at):
        original(root, stage, at)
        binding = budget._load_binding(root)
        binding["qqq"]["cycle_id"] = "foreign-custody"
        binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
        budget._atomic_json(root / budget.BUDGET_FILE, binding)

    monkeypatch.setattr(cycle, "_reserve", concurrent_change)
    with pytest.raises(_RecoveryRequired, match="cycle_book_changed"):
        advance(call)
    assert not call["client"].wire
