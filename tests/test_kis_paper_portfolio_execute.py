from __future__ import annotations

import copy
import inspect
import re
import socket
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from test_kis_paper_portfolio_preview import NOW, _reads, _scope
from test_kis_paper_portfolio_preview import _state as historical_state
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_portfolio_execute as execute
from thericher_v2.execution.emergency import PaperExecutionControlStore
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_portfolio_plan import build_kis_paper_portfolio_plan
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
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

D = Decimal
CONFIG = KisPaperConfig("synthetic-key", "synthetic-secret", "12345678", "01")
ACCOUNT = budget._digest([CONFIG.base_url, CONFIG.account_number, CONFIG.account_product_code])


@pytest.fixture(autouse=True)
def no_actual_provider_or_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic executor tests cannot access provider or credentials")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(canary.UrllibKisPaperCanaryTransport, "request", forbidden)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", forbidden)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", forbidden)


class SyntheticPaperClient(canary.KisPaperCanaryClient):
    def __init__(self, root):
        super().__init__(config=CONFIG, transport=None)
        self.root, self.now = root, NOW
        self.orders, self.submits, self.limit_reads = {}, [], []
        self.funds, self.exact_funds = D(10000), D(10000)
        self.partial = self.unknown = False
        self.foreign = self.duplicate_position = self.incomplete = False
        self.stale = self.wrong_limit = self.history_unavailable = False
        self.on_limit_read = None

    def snapshot(self):
        positions, opens = [], []
        for order in self.orders.values():
            intent, filled, remaining = order["intent"], order["filled"], order["remaining"]
            if filled:
                positions.append(
                    KisPaperPosition(
                        intent.symbol,
                        intent.exchange,
                        "USD",
                        filled,
                        intent.limit_price,
                        filled * intent.limit_price,
                        self.now,
                    )
                )
            if remaining:
                opens.append(
                    KisPaperOpenOrder(
                        canary._redacted_open_order_reference(order["id"]),
                        intent.symbol,
                        intent.exchange,
                        "USD",
                        "buy",
                        intent.quantity,
                        filled,
                        remaining,
                        intent.limit_price,
                        self.now,
                    )
                )
        if self.foreign:
            positions.append(KisPaperPosition("QQQ", "NASD", "USD", D(1), D(100), D(100), self.now))
        if self.duplicate_position and positions:
            positions.append(positions[0])
        captured = self.now - timedelta(minutes=3) if self.stale else self.now
        return KisPaperReadOnlySnapshot(
            KisPaperAccountIdentity(self._config.masked_account_identity, captured),
            KisPaperCashSnapshot("USD", self.funds, captured),
            KisPaperOrderableFundsSnapshot("USD", self.funds, "NASD", "SPY", D(1), captured),
            tuple(positions),
            KisPaperOpenOrdersSnapshot(tuple(opens), captured, complete=not self.incomplete),
            captured,
        )

    def orderable_funds_at_limit(self, *, symbol, exchange, limit_price):
        self.limit_reads.append((symbol, exchange, limit_price))
        if self.on_limit_read is not None:
            self.on_limit_read()
        return (
            KisPaperCashSnapshot("USD", self.exact_funds, self.now),
            KisPaperOrderableFundsSnapshot(
                "USD",
                self.exact_funds,
                exchange,
                symbol,
                limit_price + D(1) if self.wrong_limit else limit_price,
                self.now,
            ),
        )

    def submit_limit(self, intent, **kwargs):
        state = canary.KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.intent == intent and state.phase == "submission_started"
        binding = budget._load_binding(self.root, ACCOUNT)
        assert budget._portfolio_seed_states(binding)[intent.run_id].intent == intent
        projection = budget.project_budget(self.root, binding, as_of=self.now)
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

    def reconcile(self, state, *, now):
        order = self.orders.get(state.intent.run_id)
        known = order is not None and order["id"] == state.broker_order_id
        observation = None
        if known:
            fill = (
                None
                if self.history_unavailable
                else KisPaperCumulativeFill(
                    fill_identity_ref(
                        raw_order_id=order["id"],
                        order_at=state.submission_started_at,
                        symbol=state.intent.symbol,
                        exchange=state.intent.exchange,
                        side="buy",
                        quantity=state.intent.quantity,
                    ),
                    state.intent.quantity,
                    order["filled"],
                    order["filled"] * state.intent.limit_price,
                    now,
                    order["remaining"],
                )
            )
            observation = KisPaperExecutionObservation(
                1,
                True,
                "unavailable" if fill is None else "available",
                fill,
                now,
            )
        return canary.KisPaperCanaryReconciliation(
            snapshot=self.snapshot(),
            account_status="available",
            ccnl_row_count=int(known),
            matching_open_order=bool(known and order["remaining"]),
            matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
        )

    def cancel_order(self, *args, **kwargs):
        pytest.fail("retained BUY execution must not introduce a cancel path")


@pytest.fixture
def harness(tmp_path):
    root = tmp_path / "p"
    arguments = _scope()
    binding = arguments["binding"]
    binding["account_ref"] = ACCOUNT
    binding["basis_ref"] = budget._basis(binding).fingerprint
    binding["spy_owner_ref"] = budget._owners(binding)[0][0].fingerprint
    binding["qqq"]["owner_ref"] = budget._owners(binding)[1][0].fingerprint
    arguments.update(
        expected_account_ref=ACCOUNT,
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs={owner.owner_ref: pin for owner, pin in budget._owners(binding)},
        reads=replace(_reads(spy=D(0)), account_ref=ACCOUNT),
        request_id="synthetic-portfolio",
        input_ref="sha256:" + "d" * 64,
        expected_binding_ref="sha256:" + budget._digest(binding),
        valid_until=NOW + timedelta(minutes=5),
    )
    result = build_kis_paper_portfolio_plan(**arguments)
    assert result.status == "prepared" and result.reservation == D(900)
    budget._atomic_json(root / budget.BUDGET_FILE, result.binding)
    intent = result.intents[0]
    proof = execute.KisPaperPortfolioExecutionBinding(
        state_root=root.resolve(),
        account_ref=ACCOUNT,
        basis_ref=binding["basis_ref"],
        owner_refs=tuple((owner.owner_ref, ref) for owner, ref in budget._owners(result.binding)),
        binding_ref="sha256:" + budget._digest(result.binding),
        request_id=arguments["request_id"],
        parent_binding_ref=arguments["expected_binding_ref"],
        input_ref=arguments["input_ref"],
        plan_ref=result.plan_ref,
        run_id=intent.run_id,
        intent_ref=intent.fingerprint,
    )
    client = SyntheticPaperClient(root)
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


def _state(call):
    return canary.KisPaperCanaryStateStore(
        call["state_root"] / (call["proof"].run_id + ".json")
    ).read()


def _leg(call, symbol):
    binding = budget._load_binding(call["state_root"])
    intent = next(
        s.intent
        for s in budget._portfolio_seed_states(binding).values()
        if s.intent.symbol == symbol
    )
    return {
        **call,
        "proof": replace(call["proof"], run_id=intent.run_id, intent_ref=intent.fingerprint),
    }


def test_default_is_inert_and_uses_existing_private_pool_default(harness, monkeypatch):
    monkeypatch.setattr(budget, "_load_binding", lambda *a, **k: pytest.fail("inert means no read"))
    assert execute.execute_kis_paper_portfolio_buy(**{**harness, "execute": False}) is None
    default = inspect.signature(execute.execute_kis_paper_portfolio_buy).parameters["state_root"]
    assert default.default == canary.DEFAULT_KIS_PAPER_CANARY_STATE_ROOT
    assert not harness["client"].submits and not harness["client"].limit_reads


def test_all_five_existing_writers_share_the_current_pool_without_a_public_bypass():
    parameters = inspect.signature(canary.run_kis_paper_canary).parameters
    assert "portfolio_execution" not in parameters
    source = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text("utf-8")
    for name in (
        "kis-paper-canary",
        "kis-paper-session",
        "kis-paper-daily-spy-session",
        "kis-paper-prospective-spy-cycle",
        "kis-paper-prospective-qqq-session",
    ):
        section = re.split(
            r"\n  [a-z][a-z0-9-]*:\n",
            source.split(f"\n  {name}:\n", 1)[1],
            maxsplit=1,
        )[0]
        assert "      - --state-root\n      - /app/private/canary\n" in section
        assert "      - thericher-v2-paper-canary-private:/app/private\n" in section
    implementation = inspect.getsource(execute.execute_kis_paper_portfolio_buy)
    assert 'exclusive_kis_paper_canary_state_lock(root / ".session_execution")' in implementation
    assert 'exclusive_kis_paper_canary_state_lock(root / ".canary_execution")' in implementation


@pytest.mark.parametrize("symbol", ["SPY", "TLT", "GLD"])
def test_exact_retained_buy_and_duplicate_recovery_never_resize_or_submit_twice(harness, symbol):
    call = _leg(harness, symbol)
    before = (call["state_root"] / budget.BUDGET_FILE).read_bytes()
    outcome = execute.execute_kis_paper_portfolio_buy(**call)
    state = _state(call)
    assert outcome.phase == "submitted" and state.current_fill.quantity == D(3)
    original = state.intent
    assert original.client_order_id.startswith("portfolio-")
    assert call["client"].limit_reads == [(symbol, original.exchange, original.limit_price)]
    assert budget.conflicts_with_budget_strategy(call["state_root"], original.run_id, symbol)
    for _ in range(2):
        call["client"].now += timedelta(minutes=10)
        execute.execute_kis_paper_portfolio_buy(**call)
        assert _state(call).intent == original
    assert call["client"].submits == [original]
    assert (call["state_root"] / budget.BUDGET_FILE).read_bytes() == before


def test_two_completed_legs_use_the_same_joint_reservation_without_finalizing_binding(harness):
    root, client = harness["state_root"], harness["client"]
    original = (root / budget.BUDGET_FILE).read_bytes()
    for symbol, cost, reserved in (("SPY", D(300), D(600)), ("TLT", D(600), D(300))):
        call = _leg(harness, symbol)
        assert execute.execute_kis_paper_portfolio_buy(**call).phase == "submitted"
        projection = budget.project_budget(root, budget._load_binding(root), as_of=client.now)
        assert (projection.entry_cost, projection.reserved_buys) == (cost, reserved)
        assert (root / budget.BUDGET_FILE).read_bytes() == original
        client.now += timedelta(seconds=1)
    assert [intent.symbol for intent in client.submits] == ["SPY", "TLT"]
    binding = budget._load_binding(root)
    assert not binding["terminal_evidence"] and len(binding["portfolio"]["plans"]) == 1


def test_another_owners_valid_pending_sell_cannot_authorize_a_fresh_buy(harness):
    root = harness["state_root"]
    binding = budget._load_binding(root)
    buy = historical_state(21, symbol="QQQ")
    pending = historical_state(22, symbol="QQQ", pending=True)
    sell = replace(pending, intent=replace(pending.intent, side="sell"))
    for state, closed in ((buy, True), (sell, False)):
        binding["qqq"]["orders"].append(
            dict(
                run_id=state.intent.run_id,
                intent_ref=state.intent.fingerprint,
                closed=closed,
            )
        )
        budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
    binding["terminal_evidence"][buy.intent.run_id] = budget._terminal_payload(buy)
    binding["qqq"]["owner_ref"] = next(
        owner.fingerprint for owner, _ in budget._owners(binding) if owner.symbol == "QQQ"
    )
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    call = {
        **harness,
        "proof": replace(
            harness["proof"],
            binding_ref="sha256:" + budget._digest(binding),
            owner_refs=tuple((owner.owner_ref, pin) for owner, pin in budget._owners(binding)),
        ),
    }
    with pytest.raises(_RecoveryRequired, match="portfolio_pending_identity"):
        execute.execute_kis_paper_portfolio_buy(**call)
    assert not harness["client"].submits and not harness["client"].limit_reads
    assert budget.project_budget(root, binding, as_of=NOW).reserved_buys == D(900)


def _cancelled_other_owner(call, *, with_proof):
    root = call["state_root"]
    binding = budget._load_binding(root)
    saved = replace(
        historical_state(21, symbol="QQQ", filled="0", remaining="0"),
        phase="cancelled",
    )
    observation = KisPaperExecutionObservation(
        row_count=2,
        same_day_order_id_seen=True,
        status="available",
        fill=saved.current_fill,
        observed_at=saved.fill_observed_at,
        cancellation_confirmed=True,
    )
    current = replace(
        saved,
        updated_at=NOW,
        fill_observation_status="unavailable",
        fill_observed_at=NOW,
    )
    binding["qqq"]["orders"].append(
        dict(run_id=saved.intent.run_id, intent_ref=saved.intent.fingerprint, closed=False)
    )
    if with_proof:
        binding["terminal_evidence"][saved.intent.run_id] = budget._terminal_payload(
            saved, observation
        )
    binding["qqq"]["owner_ref"] = next(
        owner.fingerprint for owner, _ in budget._owners(binding) if owner.symbol == "QQQ"
    )
    budget._atomic_json(root / (current.intent.run_id + ".json"), current.to_dict())
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    return {
        **call,
        "proof": replace(
            call["proof"],
            binding_ref="sha256:" + budget._digest(binding),
            owner_refs=tuple((owner.owner_ref, pin) for owner, pin in budget._owners(binding)),
        ),
    }


def test_proven_other_owner_zero_fill_cancel_allows_next_buy(harness):
    call = _cancelled_other_owner(harness, with_proof=True)
    root = call["state_root"]
    before = (root / budget.BUDGET_FILE).read_bytes()
    binding = budget._load_binding(root)
    other_path = root / (binding["qqq"]["orders"][0]["run_id"] + ".json")
    other_before = other_path.read_bytes()
    assert budget.project_budget(root, binding, as_of=NOW).reserved_buys == D(900)
    assert execute.execute_kis_paper_portfolio_buy(**call).phase == "submitted"
    assert call["client"].submits == [_state(call).intent]
    assert len(call["client"].limit_reads) == 1
    assert budget.project_budget(root, binding, as_of=NOW).reserved_buys == D(600)
    assert (root / budget.BUDGET_FILE).read_bytes() == before
    assert other_path.read_bytes() == other_before


def test_other_owner_zero_fill_cancel_without_retained_proof_blocks_next_buy(harness):
    call = _cancelled_other_owner(harness, with_proof=False)
    root = call["state_root"]
    before = (root / budget.BUDGET_FILE).read_bytes()
    with pytest.raises(_RecoveryRequired, match="portfolio_pending_identity"):
        execute.execute_kis_paper_portfolio_buy(**call)
    assert not call["client"].submits and not call["client"].limit_reads
    assert _state(call).submission_started_at is None
    projection = budget.project_budget(root, budget._load_binding(root), as_of=NOW)
    assert projection.reserved_buys == D(1000)
    assert (root / budget.BUDGET_FILE).read_bytes() == before


@pytest.mark.parametrize("available", [D(999), D(1000)])
def test_known_unattempted_other_owner_buy_remains_in_observed_funds_requirement(
    harness, available
):
    root = harness["state_root"]
    binding = budget._load_binding(root)
    pending = historical_state(21, symbol="QQQ", pending=True)
    binding["qqq"]["orders"].append(
        dict(
            run_id=pending.intent.run_id,
            intent_ref=pending.intent.fingerprint,
            closed=False,
        )
    )
    binding["qqq"]["owner_ref"] = next(
        owner.fingerprint for owner, _ in budget._owners(binding) if owner.symbol == "QQQ"
    )
    budget._atomic_json(root / (pending.intent.run_id + ".json"), pending.to_dict())
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    call = {
        **harness,
        "proof": replace(
            harness["proof"],
            binding_ref="sha256:" + budget._digest(binding),
            owner_refs=tuple((owner.owner_ref, pin) for owner, pin in budget._owners(binding)),
        ),
    }
    harness["client"].funds = available
    assert budget.project_budget(root, binding, as_of=NOW).reserved_buys == D(1000)
    if available == D(999):
        with pytest.raises(_RecoveryRequired, match="buying_power_changed"):
            execute.execute_kis_paper_portfolio_buy(**call)
        assert not harness["client"].submits
    else:
        assert execute.execute_kis_paper_portfolio_buy(**call).phase == "submitted"
        assert len(harness["client"].submits) == 1
        assert budget.project_budget(root, binding, as_of=NOW).reserved_buys == D(700)


def test_duplicate_account_position_rows_cannot_be_adopted_by_a_second_leg(harness):
    execute.execute_kis_paper_portfolio_buy(**harness)
    harness["client"].duplicate_position = True
    with pytest.raises(_RecoveryRequired, match="pre_submit_ownership_changed"):
        execute.execute_kis_paper_portfolio_buy(**_leg(harness, "TLT"))
    assert len(harness["client"].submits) == 1


@pytest.mark.parametrize(
    "field",
    [
        "state_root",
        "account_ref",
        "basis_ref",
        "owner_refs",
        "binding_ref",
        "request_id",
        "parent_binding_ref",
        "input_ref",
        "plan_ref",
        "run_id",
        "intent_ref",
    ],
)
def test_each_independent_custody_pin_rejects_wrong_identity_before_attempt(harness, field):
    proof = harness["proof"]
    wrong = "sha256:" + "f" * 64
    if field == "state_root":
        wrong = proof.state_root.parent / "foreign-root"
    elif field == "account_ref":
        wrong = "f" * 64
    elif field == "owner_refs":
        wrong = (("foreign-owner", wrong),)
    elif field == "request_id":
        wrong = "foreign-request"
    elif field == "run_id":
        wrong = "bp-" + "f" * 64
    call = {**harness, "proof": replace(proof, **{field: wrong})}
    before = (harness["state_root"] / budget.BUDGET_FILE).read_bytes()
    with pytest.raises((_RecoveryRequired, ValueError)):
        execute.execute_kis_paper_portfolio_buy(**call)
    assert not harness["client"].submits and not harness["client"].limit_reads
    assert not list(harness["state_root"].glob("bp-*.json"))
    assert (harness["state_root"] / budget.BUDGET_FILE).read_bytes() == before


@pytest.mark.parametrize(
    "failure",
    ["foreign", "incomplete", "stale", "funds", "exact_funds", "wrong_limit", "wrong_client"],
)
def test_only_fresh_observed_account_and_exact_limit_funds_can_submit(harness, failure):
    client = harness["client"]
    if failure in {"funds", "exact_funds"}:
        setattr(client, failure, D(899))
    elif failure == "wrong_client":
        client._config = replace(CONFIG, account_number="87654321")
    else:
        setattr(client, failure, True)
    with pytest.raises((_RecoveryRequired, ValueError)):
        execute.execute_kis_paper_portfolio_buy(**harness)
    assert not client.submits
    assert budget.project_budget(
        harness["state_root"], budget._load_binding(harness["state_root"]), as_of=NOW
    ).reserved_buys == D(900)


@pytest.mark.parametrize("unknown", [False, True])
def test_expired_partial_or_unknown_recovery_preserves_counts_and_all_reservations(
    harness, unknown
):
    client = harness["client"]
    client.partial, client.unknown = True, unknown
    execute.execute_kis_paper_portfolio_buy(**harness)
    before = _state(harness)
    with pytest.raises(_RecoveryRequired, match="portfolio_pending_identity"):
        execute.execute_kis_paper_portfolio_buy(**_leg(harness, "TLT"))
    client.history_unavailable = True
    client.now += timedelta(minutes=10)
    execute.execute_kis_paper_portfolio_buy(**harness)
    after = _state(harness)
    assert after.intent == before.intent and len(client.submits) == 1
    assert after.cumulative_fill == before.cumulative_fill
    assert after.phase == ("outcome_unknown" if unknown else "submitted")
    projection = budget.project_budget(
        harness["state_root"], budget._load_binding(harness["state_root"]), as_of=client.now
    )
    assert projection.entry_cost == (D(0) if unknown else D(100))
    assert projection.reserved_buys == (D(900) if unknown else D(800))
    assert len(client.submits) == 1


def test_original_expiry_and_late_callback_never_refresh_ttl_or_submit(harness):
    client = harness["client"]
    client.on_limit_read = lambda: setattr(client, "now", client.now + timedelta(minutes=6))
    with pytest.raises((_RecoveryRequired, ValueError)):
        execute.execute_kis_paper_portfolio_buy(**harness)
    original = _state(harness).intent
    assert original.valid_until == NOW + timedelta(minutes=5)
    outcome = execute.execute_kis_paper_portfolio_buy(**harness)
    assert outcome.reason_code == "intent_expired" and _state(harness).intent == original
    assert not client.submits and len(client.limit_reads) == 1


def test_already_expired_zero_fill_seed_materializes_original_identity_without_account_reads(
    harness,
):
    client = harness["client"]
    client.now += timedelta(hours=1)
    client.reconcile = lambda *a, **k: pytest.fail("expired unattempted seed needs no account read")
    seed = budget._portfolio_seed_states(budget._load_binding(harness["state_root"]))[
        harness["proof"].run_id
    ]
    for _ in range(2):
        outcome = execute.execute_kis_paper_portfolio_buy(**harness)
        assert outcome.reason_code == "intent_expired" and _state(harness).intent == seed.intent
        assert _state(harness).submission_started_at is None
    assert not client.submits and not client.limit_reads


def test_final_canary_deadline_after_fresh_funds_callback_is_not_extended(harness):
    root = harness["state_root"]
    binding = budget._load_binding(root)
    plan = binding["portfolio"]["plans"][0]
    for run, state in budget._portfolio_seed_states(binding).items():
        plan["states"][run] = replace(
            state,
            intent=replace(state.intent, valid_until=NOW + timedelta(seconds=1)),
        ).to_dict()
    for owner, _ in budget._owners(binding):
        if owner.owner_ref.startswith("portfolio-"):
            binding["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    intent = budget._portfolio_seed_states(binding)[harness["proof"].run_id].intent
    proof = replace(
        harness["proof"],
        binding_ref="sha256:" + budget._digest(binding),
        plan_ref="sha256:" + budget._digest(plan),
        intent_ref=intent.fingerprint,
        owner_refs=tuple((owner.owner_ref, ref) for owner, ref in budget._owners(binding)),
    )
    client = harness["client"]
    client.on_limit_read = lambda: setattr(client, "now", NOW + timedelta(seconds=2))
    call = {**harness, "proof": proof}
    outcome = execute.execute_kis_paper_portfolio_buy(**call)
    assert outcome.reason_code == "intent_expired"
    assert _state(call).intent == intent and _state(call).submission_started_at is None
    assert not client.submits and len(client.limit_reads) == 1


@pytest.mark.parametrize("change", ["control", "session", "binding"])
def test_pre_post_recheck_catches_control_session_or_shared_binding_drift(
    harness, monkeypatch, change
):
    def change_during_read():
        if change == "control":
            PaperExecutionControlStore(harness["execution_control_path"]).set_pause_buys(True)
        elif change == "session":
            monkeypatch.setattr(execute, "is_us_equity_regular_session_window", lambda _: False)
        else:
            binding = budget._load_binding(harness["state_root"])
            binding["portfolio"]["owner_refs"]["TLT"] = "sha256:" + "f" * 64
            budget._atomic_json(harness["state_root"] / budget.BUDGET_FILE, binding)

    harness["client"].on_limit_read = change_during_read
    with pytest.raises((_RecoveryRequired, ValueError)):
        execute.execute_kis_paper_portfolio_buy(**harness)
    assert not harness["client"].submits
    assert _state(harness).submission_started_at is None


def test_missing_materialized_attempt_cannot_fall_back_to_seed(harness):
    execute.execute_kis_paper_portfolio_buy(**harness)
    (harness["state_root"] / (harness["proof"].run_id + ".json")).unlink()
    with pytest.raises(_RecoveryRequired, match="portfolio_materialized_state_missing"):
        execute.execute_kis_paper_portfolio_buy(**harness)
    assert len(harness["client"].submits) == 1


def test_guard_never_admits_bare_foreign_or_forged_intents(harness):
    proof, root = harness["proof"], harness["state_root"]
    seed = budget._portfolio_seed_states(budget._load_binding(root))[proof.run_id]
    assert not execute.allows_kis_paper_portfolio_execution(root, proof.run_id, "SPY", proof)
    canary.KisPaperCanaryStateStore(root / (proof.run_id + ".json")).record_intent(
        seed.intent,
        cancel_after_submit=False,
        now=NOW,
    )
    assert budget.conflicts_with_budget_strategy(root, proof.run_id, "SPY")
    assert execute.allows_kis_paper_portfolio_execution(root, proof.run_id, "SPY", proof)
    assert not execute.allows_kis_paper_portfolio_execution(root, proof.run_id, "TLT", proof)
    assert not execute.allows_kis_paper_portfolio_execution(root, proof.run_id, "SPY", True)
    requested = replace(seed.intent, client_order_id="canary-" + proof.run_id)
    assert execute.bind_kis_paper_portfolio_execution_intent(root, requested, proof) == seed.intent
    with pytest.raises(_RecoveryRequired, match="portfolio_intent_mismatch"):
        execute.bind_kis_paper_portfolio_execution_intent(
            root, replace(requested, quantity=D(1)), proof
        )
    bad = copy.deepcopy(budget._load_binding(root))
    bad["portfolio"]["plans"].append(copy.deepcopy(bad["portfolio"]["plans"][0]))
    budget._atomic_json(root / budget.BUDGET_FILE, bad)
    assert not execute.allows_kis_paper_portfolio_execution(root, proof.run_id, "SPY", proof)


def test_concurrent_same_leg_has_one_submission_under_the_existing_global_locks(harness):
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(lambda _: execute.execute_kis_paper_portfolio_buy(**harness), range(2))
        )
    assert all(o.phase == "submitted" for o in outcomes)
    assert len(harness["client"].submits) == len(harness["client"].limit_reads) == 1


def test_competing_shared_writer_cannot_change_custody_during_orderability(harness):
    inside, release, written = threading.Event(), threading.Event(), threading.Event()

    def hold_read():
        inside.set()
        assert release.wait(3)

    def writer():
        assert inside.wait(3)
        root = harness["state_root"]
        with canary.exclusive_kis_paper_canary_state_lock(root / ".session_execution"):
            with canary.exclusive_kis_paper_canary_state_lock(root / ".canary_execution"):
                binding = budget._load_binding(root)
                state = _state(harness)
                binding["terminal_evidence"][state.intent.run_id] = budget._terminal_payload(state)
                budget._atomic_json(root / budget.BUDGET_FILE, binding)
                written.set()

    harness["client"].on_limit_read = hold_read
    with ThreadPoolExecutor(max_workers=2) as pool:
        dispatch = pool.submit(execute.execute_kis_paper_portfolio_buy, **harness)
        competing = pool.submit(writer)
        assert inside.wait(3)
        try:
            assert not written.wait(0.05)
        finally:
            release.set()
        assert dispatch.result(timeout=4).phase == "submitted"
        competing.result(timeout=4)
    assert written.is_set() and len(harness["client"].submits) == 1
    with pytest.raises(_RecoveryRequired, match="portfolio_binding_mismatch"):
        execute.execute_kis_paper_portfolio_buy(**harness)
