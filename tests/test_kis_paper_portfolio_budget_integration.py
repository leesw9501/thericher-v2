from __future__ import annotations

import json
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import decision_instrument_binding_ref
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_spy_fill_cycle as cycle
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryReconciliation,
    KisPaperCanaryState,
    KisPaperCanaryStateStore,
    _redacted_open_order_reference,
)
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_readonly import (
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperConfig,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
    KisPaperReadOnlySnapshot,
)
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt, _derive_decision_id

D = Decimal
NOW = datetime(2026, 9, 22, 14, 30, tzinfo=UTC)
ENV = {
    "KIS_PAPER_APP_KEY": "synthetic-key",
    "KIS_PAPER_APP_SECRET": "synthetic-secret",
    "KIS_PAPER_ACCOUNT_NO": "12345678",
    "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
}


def receipt(at, symbol="QQQ", action="enter", digit="a"):
    fields = dict(
        campaign_ref="ref:" + digit * 64,
        model_ref="ref:" + "2" * 64,
        input_manifest_ref="sha256:" + "3" * 64,
        proposal_ref="ref:" + "4" * 64,
        decision_class=action,
        input_status="ready",
        decided_at=at,
        valid_until=at + timedelta(minutes=10),
        reason_class="eligible_" + action,
        instrument_binding_ref=decision_instrument_binding_ref(
            symbol=symbol,
            market="US",
            decision_class=action,
        ),
        target_binding_ref="ref:" + "5" * 64,
        schema_version=1,
    )
    return ResearchDecisionReceipt(decision_id=_derive_decision_id(**fields), **fields)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic integration must not use the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


class Broker(KisPaperCanaryClient):
    def __init__(self, root):
        super().__init__(config=KisPaperConfig(*ENV.values()), transport=None)
        self.root, self.now = root, NOW
        self.funds = D(18000)
        self.foreign = {"SPY": D(0), "QQQ": D(0)}
        self.orders, self.submits, self.cancels = {}, [], []
        self.fill_fraction = D(1)
        self.unknown = False
        self.crash = False
        self.history_available = True
        self.spy_price = D(600)

    def snapshot(self):
        positions, opens = [], []
        for symbol, exchange in (("SPY", "AMEX"), ("QQQ", "NASD")):
            quantity = self.foreign[symbol] + sum(
                (
                    order["filled"] * (1 if order["intent"].side == "buy" else -1)
                    for order in self.orders.values()
                    if order["intent"].symbol == symbol
                ),
                D(0),
            )
            if quantity:
                positions.append(
                    KisPaperPosition(
                        symbol,
                        exchange,
                        "USD",
                        quantity,
                        D(600),
                        D(600),
                        self.now,
                    )
                )
        for order in self.orders.values():
            intent = order["intent"]
            if order["remaining"]:
                opens.append(
                    KisPaperOpenOrder(
                        _redacted_open_order_reference(order["id"]),
                        intent.symbol,
                        intent.exchange,
                        "USD",
                        intent.side,
                        intent.quantity,
                        order["filled"],
                        order["remaining"],
                        intent.limit_price,
                        self.now,
                    )
                )
        return KisPaperReadOnlySnapshot(
            KisPaperAccountIdentity(self._config.masked_account_identity, self.now),
            KisPaperCashSnapshot("USD", self.funds, self.now),
            KisPaperOrderableFundsSnapshot("USD", self.funds, "NASD", "SPY", D(1), self.now),
            tuple(positions),
            KisPaperOpenOrdersSnapshot(tuple(opens), self.now),
            self.now,
        )

    def fetch_spy_limit_input(self, *, observed_at):
        return KisPaperSpyLimitInput(
            self.spy_price,
            2,
            D("0.01"),
            observed_at,
            best_bid=self.spy_price,
            best_ask=self.spy_price,
        )

    def fetch_qqq_limit_input(self, *, observed_at):
        return KisPaperSpyLimitInput(
            D(600),
            2,
            D("0.01"),
            observed_at,
            best_bid=D(600),
            best_ask=D(600),
        )

    def orderable_funds_at_limit(self, *, symbol, exchange, limit_price):
        assert (symbol, exchange) == ("QQQ", "NASD")
        return (
            KisPaperCashSnapshot("USD", self.funds, self.now),
            KisPaperOrderableFundsSnapshot(
                "USD",
                self.funds,
                exchange,
                symbol,
                limit_price,
                self.now,
            ),
        )

    def submit_limit(self, intent, **kwargs):
        state = KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.phase == "submission_started"
        binding = budget._load_binding(self.root)
        rows = budget._orders(binding, "unit-cycle" if intent.symbol == "QQQ" else None)
        assert rows[-1]["intent_ref"] == intent.fingerprint
        projection = budget.project_budget(self.root, binding)
        assert projection.entry_cost + projection.reserved_buys <= D(binding["allocated_usd"])
        self.submits.append(intent)
        filled = (intent.quantity * self.fill_fraction).to_integral_value(rounding="ROUND_FLOOR")
        self.orders[intent.run_id] = {
            "intent": intent,
            "filled": filled,
            "remaining": intent.quantity - filled,
            "id": str(100 + len(self.submits)),
            "cancelled": False,
        }
        if self.crash:
            raise RuntimeError("synthetic post crash")
        if self.unknown:
            raise KisPaperCanaryError("submit_transport_unknown")
        return True, self.orders[intent.run_id]["id"]

    def reconcile(self, state, *, now):
        order = self.orders.get(state.intent.run_id)
        known = order is not None and state.broker_order_id == order["id"]
        observation = None
        if known:
            fill = None
            if self.history_available:
                fill = KisPaperCumulativeFill(
                    fill_identity_ref(
                        raw_order_id=order["id"],
                        order_at=state.submission_started_at,
                        symbol=state.intent.symbol,
                        exchange=state.intent.exchange,
                        side=state.intent.side,
                        quantity=state.intent.quantity,
                    ),
                    state.intent.quantity,
                    order["filled"],
                    order["filled"] * state.intent.limit_price,
                    now,
                    order["remaining"],
                )
            confirmed = bool(order["cancelled"] and fill is not None and fill.quantity == 0)
            observation = KisPaperExecutionObservation(
                2 if confirmed else 1,
                True,
                "available" if fill else "unavailable",
                fill,
                now,
                cancellation_confirmed=confirmed,
            )
        return KisPaperCanaryReconciliation(
            snapshot=self.snapshot(),
            account_status="available",
            ccnl_row_count=int(known),
            matching_open_order=bool(known and order["remaining"]),
            matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
        )

    def cancel_order(self, intent, *, broker_order_id):
        order = self.orders[intent.run_id]
        assert order["id"] == broker_order_id
        order["remaining"], order["cancelled"] = D(0), True
        self.cancels.append(intent.run_id)
        return True


@pytest.fixture
def harness(tmp_path):
    root = tmp_path / "synthetic-private"
    client = Broker(root)
    args = dict(
        environment=ENV,
        state_root=root,
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        execution_control_path=tmp_path / "controls.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        client=client,
        clock=lambda: client.now,
        receipt_loader=lambda at: receipt(at),
        qqq_cycle_id="unit-cycle",
    )
    return root, client, args


def spy_args(args, digit="b"):
    return {
        **args,
        "qqq_cycle_id": None,
        "receipt_loader": lambda at: receipt(at, "SPY", digit=digit),
    }


@pytest.mark.parametrize("symbol", ["SPY", "QQQ"])
@pytest.mark.parametrize("room_available", [False, True])
def test_existing_budget_writers_honor_atomic_v3_portfolio_reservations(
    harness, symbol, room_available,
):
    from dataclasses import replace

    from test_kis_paper_portfolio_preview import NOW as PREVIEW_NOW
    from test_kis_paper_portfolio_preview import _reads, _scope
    from thericher_v2.execution.kis_paper_portfolio_plan import build_kis_paper_portfolio_plan

    root, client, args = harness
    client.now = PREVIEW_NOW
    inputs = _scope()
    binding = inputs["binding"]
    account = budget._digest([client._config.base_url, client._config.account_number,
                              client._config.account_product_code])
    binding["account_ref"] = account
    binding["qqq"]["cycle_id"] = "unit-cycle"
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    inputs.update(
        expected_account_ref=account, expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={owner.owner_ref: ref for owner, ref in budget._owners(binding)},
        reads=replace(_reads(spy=D(0)), account_ref=account),
    )
    if room_available:
        inputs["weights_by_symbol"] = dict(SPY=D(0), TLT=D("0.1"), GLD=D("0.1"))
    plan = build_kis_paper_portfolio_plan(
        **inputs, expected_binding_ref="sha256:" + budget._digest(binding),
        request_id="synthetic-reserved-batch", input_ref="sha256:" + "f" * 64,
        valid_until=PREVIEW_NOW + timedelta(minutes=5),
    )
    reserved = D(200) if room_available else D(900)
    assert plan.status == "prepared" and plan.reservation == reserved
    budget._atomic_json(root / budget.BUDGET_FILE, plan.binding)
    projection = budget.project_budget(root, budget._load_binding(root), as_of=client.now)
    assert projection.entry_cost == 0 and projection.reserved_buys == reserved
    outcome = budget.run_kis_paper_budget_strategy(**(spy_args(args) if symbol == "SPY" else args))
    assert (outcome.status, outcome.reason_code) == (
        ("order_complete", "exact_order_and_position_reconciled")
        if room_available else ("no_intent", "budget_below_one_share")
    )
    retained = budget._load_binding(root)
    assert retained["portfolio"] == plan.binding["portfolio"]
    assert retained["basis_ref"] == binding["basis_ref"]
    if room_available:
        assert len(client.submits) == 1 and client.submits[0].quantity == 1
        assert budget.project_budget(root, retained, as_of=client.now).reserved_buys == reserved
    else:
        assert not client.submits
        assert not list(root.glob("bs-*.json")) and not list(root.glob("bq-*.json"))


def test_v3_default_spy_reconciles_aggregate_but_sells_only_incumbent_owner(harness):
    from dataclasses import replace

    from test_kis_paper_portfolio_preview import NOW as PREVIEW_NOW
    from test_kis_paper_portfolio_preview import _scope, _state
    from thericher_v2.execution.kis_paper_portfolio_plan import build_kis_paper_portfolio_plan

    root, client, args = harness
    client.now = PREVIEW_NOW
    incumbent = _state()
    inputs = _scope(incumbent)
    binding = inputs["binding"]
    account = budget._digest([client._config.base_url, client._config.account_number,
                              client._config.account_product_code])
    binding["account_ref"] = account
    binding["qqq"]["cycle_id"] = "unit-cycle"
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    inputs.update(
        expected_account_ref=account, expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={owner.owner_ref: ref for owner, ref in budget._owners(binding)},
        reads=replace(inputs["reads"], account_ref=account),
    )
    plan = build_kis_paper_portfolio_plan(
        **inputs, expected_binding_ref="sha256:" + budget._digest(binding),
        request_id="synthetic-multi-owner", input_ref="sha256:" + "f" * 64,
        valid_until=PREVIEW_NOW + timedelta(minutes=5),
    )
    portfolio_intent = next(intent for intent in plan.intents if intent.symbol == "SPY")
    fill = KisPaperCumulativeFill(
        fill_identity_ref(raw_order_id="SYNTHETIC-PORTFOLIO", order_at=PREVIEW_NOW,
                          symbol="SPY", exchange="AMEX", side="buy", quantity=D(2)),
        D(2), D(2), D(200), PREVIEW_NOW, D(0),
    )
    portfolio_state = KisPaperCanaryState(
        portfolio_intent, "submitted", PREVIEW_NOW, "reconciliation_clean",
        broker_order_id="SYNTHETIC-PORTFOLIO", submitted_at=PREVIEW_NOW,
        submission_started_at=PREVIEW_NOW, cumulative_fill=fill,
        fill_observation_status="available", fill_observed_at=PREVIEW_NOW,
    )
    for state in (incumbent, portfolio_state):
        budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
        client.orders[state.intent.run_id] = dict(
            intent=state.intent, filled=state.intent.quantity, remaining=D(0),
            id=state.broker_order_id, cancelled=False,
        )
    budget._atomic_json(root / budget.BUDGET_FILE, plan.binding)
    before = budget.project_budget(root, plan.binding, as_of=client.now)
    assert before.quantity == 1 and before.aggregate_quantity == 3
    outcome = budget.run_kis_paper_budget_strategy(**{
        **spy_args(args), "receipt_loader": lambda at: receipt(at, "SPY", "exit", "e"),
    })
    assert outcome.status == "order_complete"
    assert len(client.submits) == 1
    assert client.submits[0].side == "sell" and client.submits[0].quantity == 1
    retained = budget._load_binding(root)
    after = budget.project_budget(root, retained, as_of=client.now)
    assert after.quantity == 0 and after.aggregate_quantity == 2
    assert (
        budget.project_budget(root, retained, as_of=client.now, portfolio_symbol="SPY").quantity
        == 2
    )
    assert retained["portfolio"] == plan.binding["portfolio"]


def _v2_losing_roundtrip(root, client):
    from dataclasses import replace

    from test_kis_paper_portfolio_preview import NOW as PREVIEW_NOW
    from test_kis_paper_portfolio_preview import _scope, _state

    client.now = PREVIEW_NOW
    buy, sell = _state(1), _state(2)
    sell_intent = replace(sell.intent, side="sell", limit_price=D(40))
    sell_fill = replace(
        sell.cumulative_fill, gross_amount=D(40), identity_ref=fill_identity_ref(
            raw_order_id=sell.broker_order_id, order_at=sell.submission_started_at,
            symbol="SPY", exchange="AMEX", side="sell", quantity=D(1),
        ),
    )
    sell = replace(sell, intent=sell_intent, cumulative_fill=sell_fill)
    binding = _scope(buy, sell)["binding"]
    binding.update(
        account_ref=budget._digest([client._config.base_url, client._config.account_number,
                                   client._config.account_product_code]),
        basis_usd="1000", allocated_usd="100",
    )
    binding["qqq"]["cycle_id"] = "unit-cycle"
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    for state in (buy, sell):
        budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
        client.orders[state.intent.run_id] = dict(
            intent=state.intent, filled=D(1), remaining=D(0), id=state.broker_order_id,
            cancelled=False,
        )
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    return binding


@pytest.mark.parametrize("symbol", ["SPY", "QQQ"])
def test_v2_writers_bound_new_buys_by_gross_cash_after_losing_roundtrip(
    harness, monkeypatch, symbol,
):
    root, client, args = harness
    binding = _v2_losing_roundtrip(root, client)
    client.spy_price = D(90)
    monkeypatch.setattr(
        client, "fetch_qqq_limit_input", lambda *, observed_at: KisPaperSpyLimitInput(
            D(90), 2, D("0.01"), observed_at, best_bid=D(90), best_ask=D(90),
        ),
    )
    before = (root / budget.BUDGET_FILE).read_bytes()
    projection = budget.project_budget(root, binding, as_of=client.now)
    assert projection.entry_cost == 0 and projection.reserved_buys == 0
    assert projection.remaining_gross_cash == 80 and binding["allocated_usd"] == "100"
    outcome = budget.run_kis_paper_budget_strategy(**(spy_args(args) if symbol == "SPY" else args))
    assert (outcome.status, outcome.reason_code) == ("no_intent", "budget_below_one_share")
    assert not client.submits
    assert (root / budget.BUDGET_FILE).read_bytes() == before
    assert budget.project_budget(root, budget._load_binding(root), as_of=client.now) == projection
    assert not list(root.glob("bq-*.json"))
    assert len(list(root.glob("bs-*.json"))) == 2


def test_invalid_proposed_binding_is_replayed_before_save_and_does_not_poison_shared_basis(
    harness, monkeypatch,
):
    root, client, args = harness
    _v2_losing_roundtrip(root, client)
    client.spy_price = D(40)
    before = (root / budget.BUDGET_FILE).read_bytes()
    original = budget.project_budget
    checked = []

    def reject_new_proposal(state_root, binding, **kwargs):
        if len(binding["orders"]) > 2:
            checked.append(True)
            raise budget._RecoveryRequired("synthetic_invalid_proposed_binding")
        return original(state_root, binding, **kwargs)

    monkeypatch.setattr(budget, "project_budget", reject_new_proposal)
    outcome = budget.run_kis_paper_budget_strategy(**spy_args(args))
    assert outcome.status == "recovery_required" and checked
    assert not client.submits
    assert (root / budget.BUDGET_FILE).read_bytes() == before
    retained = budget._load_binding(root)
    assert retained["version"] == 2 and len(retained["orders"]) == 2
    assert original(root, retained, as_of=client.now).remaining_gross_cash == 80


def exit_args(args):
    return {**args, "receipt_loader": lambda at: receipt(at, action="exit", digit="c")}


def legacy_spy(root, client):
    binding = cycle._binding("legacy-fixture", client._config)
    states = []
    for index, side in enumerate(("buy", "sell", "sell")):
        at = NOW - timedelta(days=3 - index)
        run_id = binding[side + "_run_id"] if index < 2 else cycle._successor_run_id(binding, 1)
        quote = client.fetch_spy_limit_input(observed_at=at)
        intent = cycle._new_intent(run_id, side, D(600), quote, at)
        broker_id = str(index + 1) if index < 2 else None
        fill = (
            None
            if index == 2
            else KisPaperCumulativeFill(
                fill_identity_ref(
                    raw_order_id=broker_id,
                    order_at=at,
                    symbol="SPY",
                    exchange="AMEX",
                    side=side,
                    quantity=D(1),
                ),
                D(1),
                D(1 if index == 0 else 0),
                D(600 if index == 0 else 0),
                at,
                D(0),
            )
        )
        state = KisPaperCanaryState(
            intent,
            ("submitted", "cancelled", "outcome_unknown")[index],
            at,
            "reconciliation_unresolved",
            broker_order_id=broker_id,
            submission_started_at=at,
            submitted_at=at if broker_id else None,
            cumulative_fill=fill,
            fill_observation_status="available" if fill else "not_observed",
            fill_observed_at=at if fill else None,
            submit_response_category="provider_rejected" if index == 2 else None,
        )
        budget._atomic_json(root / (run_id + ".json"), state.to_dict())
        states.append(state)
        if index < 2:
            binding[side + "_intent_ref"] = intent.fingerprint
    successor = states[2].intent
    binding["sell_successors"] = [
        {
            "run_id": successor.run_id,
            "intent_ref": successor.fingerprint,
            "predecessor_run_id": states[1].intent.run_id,
            "predecessor_intent_ref": states[1].intent.fingerprint,
            "intent": successor.to_dict(),
        }
    ]
    binding["sell_successors_recorded"] = 1
    budget._atomic_json(
        root / ".spy_fill_cycles" / (cycle._digest(binding["cycle_id"]) + ".json"), binding
    )
    budget._atomic_json(
        root / ".spy_fill_active.json",
        {
            "cycle_ref": cycle._digest(binding["cycle_id"]),
            "account_ref": binding["account_ref"],
        },
    )
    client.foreign["SPY"] = D(1)
    return {path: path.read_bytes() for path in root.rglob("*.json")}


def test_legacy_unknown_is_charged_but_qqq_exact_cycle_releases_only_its_cost(harness):
    root, client, args = harness
    original = legacy_spy(root, client)
    assert budget.run_kis_paper_budget_strategy(**args).status == "order_complete"
    binding = budget._load_binding(root)
    assert binding["version"] == 2 and D(binding["allocated_usd"]) == 1800
    assert budget.project_budget(root, binding).entry_cost == 1200
    assert budget.project_budget(root, binding).quantity == 0
    assert budget.run_kis_paper_budget_strategy(**spy_args(args)).reason_code == (
        "existing_inventory_or_order_conflict"
    )
    client.now += timedelta(seconds=1)
    client.funds *= 10
    assert budget.run_kis_paper_budget_strategy(**exit_args(args)).status == "order_complete"
    for _ in range(2):
        binding = budget._load_binding(root)
        projection = budget.project_budget(root, binding, qqq_cycle_id="unit-cycle")
        assert projection.quantity == 0 and projection.entry_cost == 600
        assert projection.reserved_buys == 0 and D(binding["allocated_usd"]) == 1800
        budget.run_kis_paper_budget_strategy(**exit_args(args))
    assert len(client.submits) == 2 and all(intent.quantity == 1 for intent in client.submits)
    assert all(path.read_bytes() == content for path, content in original.items())


@pytest.mark.parametrize("window", ["before_reference", "before_post", "after_post"])
@pytest.mark.parametrize("with_legacy", [False, True])
def test_crash_restart_reservations_reach_default_spy_writer(
    harness,
    monkeypatch,
    window,
    with_legacy,
):
    root, client, args = harness
    legacy_bytes = legacy_spy(root, client) if with_legacy else {}
    original = budget._atomic_json

    def crash(path, payload):
        if (
            path.name == budget.BUDGET_FILE
            and payload.get("version") == 2
            and (payload["qqq"]["orders"])
        ):
            if window == "before_reference":
                raise RuntimeError("synthetic reference crash")
            original(path, payload)
            if window == "before_post":
                raise RuntimeError("synthetic reservation crash")
        return original(path, payload)

    if window == "after_post":
        client.crash = True
    else:
        monkeypatch.setattr(budget, "_atomic_json", crash)
    with pytest.raises(RuntimeError, match="synthetic"):
        budget.run_kis_paper_budget_strategy(**args)
    monkeypatch.setattr(budget, "_atomic_json", original)
    client.crash = False
    client.now += timedelta(seconds=1)
    if window == "after_post":
        assert budget.run_kis_paper_budget_strategy(**args).status == "pending"
        assert len(client.submits) == 1
    else:
        assert not client.submits
        assert budget.run_kis_paper_budget_strategy(**args).status == "order_complete"
    outcome = budget.run_kis_paper_budget_strategy(**spy_args(args))
    if with_legacy:
        assert outcome.reason_code == "existing_inventory_or_order_conflict"
        assert len(client.submits) == 1
        assert all(path.read_bytes() == content for path, content in legacy_bytes.items())
    else:
        assert outcome.status == "order_complete"
        assert client.submits[-1].symbol == "SPY" and client.submits[-1].quantity == 2
    binding = budget._load_binding(root)
    assert budget.project_budget(root, binding).entry_cost + (
        budget.project_budget(root, binding).reserved_buys
    ) == (1200 if with_legacy else 1800)


def test_unknown_spy_buy_does_not_block_distinct_qqq_owner(harness):
    root, client, args = harness
    client.funds = D(19000)
    client.unknown, client.fill_fraction = True, D(0)
    assert budget.run_kis_paper_budget_strategy(**spy_args(args)).status == "pending"
    spy_path = root / (client.submits[0].run_id + ".json")
    original = spy_path.read_bytes()
    # A complete fresh snapshot reports no open order, not a terminal fill.
    client.orders.clear()
    client.unknown, client.fill_fraction = False, D(1)
    assert budget.run_kis_paper_budget_strategy(**args).reason_code == "budget_below_one_share"
    assert spy_path.read_bytes() == original and len(client.submits) == 1
    assert budget.project_budget(root, budget._load_binding(root)).reserved_buys == 1800


def test_unknown_other_owner_with_room_does_not_hold_qqq(harness):
    root, client, args = harness
    client.spy_price = D(1000)
    client.unknown, client.fill_fraction = True, D(0)
    assert budget.run_kis_paper_budget_strategy(**spy_args(args)).status == "pending"
    spy_path = root / (client.submits[0].run_id + ".json")
    original = spy_path.read_bytes()
    client.unknown, client.fill_fraction = False, D(1)
    assert budget.run_kis_paper_budget_strategy(**args).status == "order_complete"
    projection = budget.project_budget(root, budget._load_binding(root))
    assert projection.entry_cost == 600 and projection.reserved_buys == 1000
    assert len(client.submits) == 2 and spy_path.read_bytes() == original


@pytest.mark.parametrize("category", ["provider_rejected", "success_order_reference_missing"])
def test_unknown_category_alone_never_releases_reservation(harness, category):
    root, client, args = harness
    client.unknown = True
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    path = root / (binding["qqq"]["orders"][0]["run_id"] + ".json")
    state = KisPaperCanaryStateStore(path).read()
    payload = state.to_dict() | {"submit_response_category": category}
    budget._atomic_json(path, payload)
    assert budget.project_budget(root, binding).reserved_buys == 600
    assert budget.run_kis_paper_budget_strategy(**args).status == "pending"
    assert len(client.submits) == 1


@pytest.mark.parametrize("symbol", ["SPY", "QQQ"])
def test_foreign_inventory_conflicts_only_with_its_instrument(harness, symbol):
    _root, client, args = harness
    client.foreign[symbol] = D(1)
    if symbol == "QQQ":
        assert budget.run_kis_paper_budget_strategy(**args).reason_code == (
            "existing_inventory_or_order_conflict"
        )
        assert budget.run_kis_paper_budget_strategy(**spy_args(args)).status == "order_complete"
    else:
        assert budget.run_kis_paper_budget_strategy(**args).status == "order_complete"
        assert budget.run_kis_paper_budget_strategy(**spy_args(args)).reason_code == (
            "existing_inventory_or_order_conflict"
        )


def test_v1_basis_and_order_prefix_are_preserved_on_migration(harness):
    root, client, args = harness
    client.funds = D(25000)
    assert budget.run_kis_paper_budget_strategy(**spy_args(args)).status == "order_complete"
    before = budget._load_binding(root)
    client.now += timedelta(seconds=1)
    client.funds *= 10
    # Existing SPY used 2400 of the original 2500, not the enlarged cash snapshot.
    assert budget.run_kis_paper_budget_strategy(**args).reason_code == "budget_below_one_share"
    after = budget._load_binding(root)
    assert after["version"] == 2
    assert all(before[key] == after[key] for key in budget._V1_KEYS - {"version"})
    assert set(after) != budget._V1_KEYS  # The unchanged old v1 loader rejects this shape.


@pytest.mark.parametrize("change", ["basis", "owner", "closed", "account", "lost", "cycle"])
def test_v2_binding_corruption_never_resets_or_submits(harness, change):
    root, client, args = harness
    client.fill_fraction = D(0)
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    if change == "basis":
        binding["basis_usd"], binding["allocated_usd"] = "36000", "3600"
    elif change == "owner":
        binding["qqq"]["orders"][0]["intent_ref"] = "sha256:" + "0" * 64
    elif change == "closed":
        binding["qqq"]["orders"][0]["closed"] = True
    elif change == "account":
        binding["account_ref"] = "0" * 64
    elif change == "cycle":
        args = {**args, "qqq_cycle_id": "other-cycle"}
    if change == "lost":
        (root / budget.BUDGET_FILE).unlink()
    else:
        budget._atomic_json(root / budget.BUDGET_FILE, binding)
    assert budget.run_kis_paper_budget_strategy(**args).status == "recovery_required"
    assert len(client.submits) == 1


def test_zero_fill_cancel_proof_survives_later_unavailable_read(harness):
    root, client, args = harness
    client.fill_fraction = D(0)
    assert budget.run_kis_paper_budget_strategy(**args).status == "pending"
    client.now += timedelta(minutes=6)
    assert (
        budget.run_kis_paper_budget_strategy(**args).reason_code
        == "own_order_cancellation_observed"
    )
    assert budget.project_budget(root, budget._load_binding(root)).reserved_buys == 600
    client.now += timedelta(seconds=1)
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    assert budget.project_budget(root, binding).reserved_buys == 0
    run_id = binding["qqq"]["orders"][0]["run_id"]
    store = KisPaperCanaryStateStore(root / (run_id + ".json"))
    state = store.read()
    retained_at = state.fill_observed_at
    client.now += timedelta(seconds=1)
    store.record_fill_observation(
        state.intent,
        observation=KisPaperExecutionObservation(
            0,
            False,
            "unavailable",
            None,
            client.now,
        ),
        now=client.now,
    )
    assert budget.project_budget(root, budget._load_binding(root)).reserved_buys == 0
    assert store.read().fill_observation_status == "unavailable"
    assert (
        datetime.fromisoformat(binding["terminal_evidence"][run_id]["cancellation"]["observed_at"])
        == retained_at
    )


def test_concurrent_instruments_share_allocation_and_one_binding(harness):
    root, client, args = harness
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda options: budget.run_kis_paper_budget_strategy(**options),
                [args, spy_args(args)],
            )
        )
    assert all(result.status in {"order_complete", "no_intent"} for result in results)
    binding = budget._load_binding(root)
    projection = budget.project_budget(root, binding)
    assert projection.entry_cost + projection.reserved_buys <= 1800
    assert list(root.glob("*budget*json")) == [root / budget.BUDGET_FILE]


def test_qqq_sell_never_adopts_foreign_snapshot_stock(harness):
    _root, client, args = harness
    client.foreign["QQQ"] = D(1)
    assert budget.run_kis_paper_budget_strategy(**exit_args(args)).reason_code == (
        "existing_inventory_or_order_conflict"
    )
    assert not client.submits


def test_legacy_account_binding_cannot_be_normalized_from_flags(harness):
    root, client, args = harness
    original = legacy_spy(root, client)
    active = json.loads((root / ".spy_fill_active.json").read_text())
    active["account_ref"] = "0" * 64
    budget._atomic_json(root / ".spy_fill_active.json", active)
    assert budget.run_kis_paper_budget_strategy(**args).status == "recovery_required"
    assert not client.submits
    assert all(
        path.read_bytes() == content
        for path, content in original.items()
        if path.name != ".spy_fill_active.json"
    )


def test_partial_or_missing_entry_fill_cannot_authorize_qqq_sell(harness):
    root, client, args = harness
    client.history_available = False
    assert budget.run_kis_paper_budget_strategy(**args).status == "pending"
    assert budget.run_kis_paper_budget_strategy(**exit_args(args)).status == "pending"
    assert len(client.submits) == 1
    binding = budget._load_binding(root)
    assert budget.project_budget(root, binding, qqq_cycle_id="unit-cycle").quantity == 0


def test_completed_entry_fact_survives_later_unavailable_read(harness):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    run_id = binding["qqq"]["orders"][0]["run_id"]
    store = KisPaperCanaryStateStore(root / (run_id + ".json"))
    state = store.read()
    client.now += timedelta(seconds=1)
    store.record_fill_observation(
        state.intent,
        observation=KisPaperExecutionObservation(
            0,
            False,
            "unavailable",
            None,
            client.now,
        ),
        now=client.now,
    )
    assert budget.project_budget(root, budget._load_binding(root)).entry_cost == 600
    assert budget.run_kis_paper_budget_strategy(**exit_args(args)).status == "order_complete"
    assert len(client.submits) == 2


def test_future_dated_stored_fill_cannot_authorize_a_current_sell(harness):
    root, client, args = harness
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    path = root / (binding["qqq"]["orders"][0]["run_id"] + ".json")
    state = KisPaperCanaryStateStore(path).read()
    future = client.now + timedelta(seconds=1)
    payload = state.to_dict()
    payload["updated_at"] = payload["fill_observed_at"] = future.isoformat()
    payload["cumulative_fill"]["observed_at"] = future.isoformat()
    budget._atomic_json(path, payload)
    assert budget.run_kis_paper_budget_strategy(**exit_args(args)).status == "recovery_required"
    assert len(client.submits) == 1


@pytest.mark.parametrize("identity", ["", "../escape", True, 1])
def test_invalid_cycle_has_no_io(harness, identity):
    root, client, args = harness
    with pytest.raises(ValueError, match="identity"):
        budget.run_kis_paper_budget_strategy(**{**args, "qqq_cycle_id": identity})
    assert not root.exists() and not client.submits


def test_wrong_qqq_receipt_instrument_does_not_submit(harness):
    _root, client, args = harness
    assert (
        budget.run_kis_paper_budget_strategy(
            **{
                **args,
                "receipt_loader": lambda at: receipt(at, "SPY"),
            }
        ).reason_code
        == "receipt_binding_mismatch"
    )
    assert not client.submits


def test_qqq_outcome_and_canonical_receipt_cannot_replace_scheduled_spy_evidence(harness):
    _root, client, args = harness
    args = {**args, "session_id": "shared-session"}
    qqq = budget.run_kis_paper_budget_strategy(**args)
    payload = qqq.safe_payload()
    assert payload["kind"] == "kis_paper_qqq_unit_cycle"
    assert payload["decision_use"] == "owned_unit_cycle_receipt"
    assert payload["instrument"] == "QQQ" and payload["exchange"] == "NASD"
    digest = budget._digest("unit-cycle")
    assert payload["owned_cycle_ref"] == "sha256:" + digest
    qqq_root = args["artifact_root"] / "execution/kis-paper-qqq-unit-cycle" / digest
    spy_root = args["artifact_root"] / "execution/kis-paper-spy-budget"
    assert json.loads((qqq_root / "shared-session/outcome.json").read_text()) == payload
    assert not (spy_root / "shared-session/outcome.json").exists()
    canonical = list((qqq_root / "decisions").glob("*.json"))
    assert len(canonical) == 1 and json.loads(canonical[0].read_text()) == receipt(NOW).to_payload()
    assert not (spy_root / "decisions" / canonical[0].name).exists()
    assert '"unit-cycle"' not in json.dumps(payload)
    assert not any(
        ENV[key] in json.dumps(payload)
        for key in ("KIS_PAPER_APP_KEY", "KIS_PAPER_APP_SECRET", "KIS_PAPER_ACCOUNT_NO")
    )
    spy = budget.run_kis_paper_budget_strategy(**spy_args(args))
    assert spy.safe_payload()["kind"] == "kis_paper_spy_budget_strategy"
    assert spy.safe_payload()["decision_use"] == "existing_baseline_direction_only"
    assert not {"instrument", "exchange", "owned_cycle_ref"} & set(spy.safe_payload())
    assert json.loads((spy_root / "shared-session/outcome.json").read_text()) == spy.safe_payload()
    assert json.loads((qqq_root / "shared-session/outcome.json").read_text()) == payload
    assert len(client.submits) == 2


def test_qqq_preview_has_scope_but_no_io(harness):
    root, client, args = harness
    outcome = budget.run_kis_paper_budget_strategy(**{**args, "execute": False, "environment": {}})
    assert outcome.safe_payload()["kind"] == "kis_paper_qqq_unit_cycle"
    assert outcome.safe_payload()["owned_cycle_ref"] == "sha256:" + budget._digest("unit-cycle")
    assert not root.exists() and not client.submits


@pytest.mark.parametrize(
    "field,value",
    [
        ("instrument", "SPY"),
        ("exchange", "NAS"),
        ("owned_cycle_ref", "unit-cycle"),
    ],
)
def test_outcome_scope_cannot_mix_or_expose_cycle_identity(field, value):
    fields = {"instrument": "QQQ", "exchange": "NASD", "owned_cycle_ref": "sha256:" + "1" * 64}
    with pytest.raises(ValueError, match="scope"):
        budget.KisPaperBudgetOutcome("preview", "preview", NOW, **(fields | {field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", True),
        ("gross_amount", 0.0),
        ("observed_at", True),
    ],
)
def test_retained_terminal_nested_fill_is_strict(harness, field, value):
    root, client, args = harness
    client.fill_fraction = D(0)
    budget.run_kis_paper_budget_strategy(**args)
    client.now += timedelta(minutes=6)
    budget.run_kis_paper_budget_strategy(**args)
    client.now += timedelta(seconds=1)
    budget.run_kis_paper_budget_strategy(**args)
    binding = budget._load_binding(root)
    run_id = binding["qqq"]["orders"][0]["run_id"]
    binding["terminal_evidence"][run_id]["cancellation"]["fill"][field] = value
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    assert budget.run_kis_paper_budget_strategy(**args).status == "recovery_required"
    assert len(client.submits) == 1
