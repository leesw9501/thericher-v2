from __future__ import annotations

import json
import socket
import urllib.request
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_spy_fill_cycle import ENV, SyntheticClient
from thericher_v2.execution import kis_paper_spy_fill_cycle as cycle
from thericher_v2.execution.emergency import EmergencyStore, PaperExecutionControlStore
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryError,
    KisPaperCanaryReconciliation,
    KisPaperCanaryStateStore,
    _redacted_open_order_reference,
)
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
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

D = Decimal


class SuccessorClient(SyntheticClient):
    """Each POST creates a new order, without any client-ID deduplication."""

    def __init__(self, root):
        super().__init__(root)
        self.proof_override = {}
        self.reconciled = []
        self.submit_fault = None

    def snapshot(self):
        self.calls.append("snapshot")
        if self.before_snapshot:
            self.before_snapshot()
        quantity = sum(
            order["quantity"] * (1 if order["intent"].side == "buy" else -1)
            for order in self.orders.values()
        ) if self.position_override is None else self.position_override

        def stamp(component):
            return self.now - timedelta(seconds=self.component_age.get(component, 0))

        positions = () if quantity == 0 else (
            KisPaperPosition("SPY", "AMEX", "USD", D(quantity), D(600), D(600), stamp("position")),
        )
        orders = [
            KisPaperOpenOrder(
                _redacted_open_order_reference(order["id"]), "SPY", "AMEX", "USD",
                order["intent"].side, D(1), D(order["quantity"]),
                D(1) - order["quantity"], order["intent"].limit_price, stamp("order"),
            )
            for order in self.orders.values() if order["open"]
        ]
        if self.foreign_open:
            orders.append(KisPaperOpenOrder(
                "open-foreign", "SPY", "AMEX", "USD", "sell", D(1), D(0), D(1),
                D(600), stamp("order"),
            ))
        return KisPaperReadOnlySnapshot(
            KisPaperAccountIdentity(self._config.masked_account_identity, stamp("identity")),
            KisPaperCashSnapshot("USD", D(10000), stamp("cash")),
            KisPaperOrderableFundsSnapshot(
                "USD", D(10000), "AMEX", "SPY", D(600), stamp("funds")
            ),
            positions,
            KisPaperOpenOrdersSnapshot(tuple(orders), stamp("open_orders")),
            stamp("snapshot"),
        )

    def reconcile(self, state, *, now):
        self.reconciled.append(state.intent.run_id)
        order = self.orders.get(state.intent.run_id)
        known = order is not None and state.broker_order_id == order["id"]
        observation = None
        if known:
            fill = KisPaperCumulativeFill(
                fill_identity_ref(
                    raw_order_id=order["id"], order_at=state.submission_started_at,
                    symbol="SPY", exchange="AMEX", side=state.intent.side, quantity=D(1),
                ),
                D(1), D(order["quantity"]), D(order["quantity"]) * state.intent.limit_price,
                now, remaining_quantity=D(int(order["open"])),
            )
            observation = KisPaperExecutionObservation(
                2 if order["cancelled"] else 1, True, "available", fill,
                observed_at=now, cancellation_confirmed=order["cancelled"],
            )
        rec = KisPaperCanaryReconciliation(
            snapshot=self.snapshot(), account_status="available", ccnl_row_count=int(known),
            matching_open_order=bool(known and order["open"]), matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
        )
        change = self.proof_override.get(state.intent.run_id)
        return change(rec) if change else rec

    def submit_limit(self, intent, **kwargs):
        state = KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.phase == "submission_started"
        active = cycle._read_json(self.root / ".spy_fill_active.json")
        binding = cycle._read_json(self.root / ".spy_fill_cycles" / (active["cycle_ref"] + ".json"))
        if intent.run_id.endswith("-x"):
            assert binding["sell_successors_recorded"] == len(binding["sell_successors"])
            assert binding["sell_successors"][-1]["intent_ref"] == intent.fingerprint
            assert binding["sell_successors"][-1]["intent"] == intent.to_dict()
        else:
            assert binding[intent.side + "_intent_ref"] == intent.fingerprint
        assert intent.run_id not in self.submits, "duplicate POST; broker does not deduplicate"
        self.submits.append(intent.run_id)
        self.orders[intent.run_id] = {
            "id": f"SYNTHETIC-{len(self.submits)}", "intent": intent,
            "quantity": D(int(self.fill_immediately)), "open": not self.fill_immediately,
            "cancelled": False,
        }
        if self.submit_fault is not None:
            raise self.submit_fault("synthetic POST outcome lost")
        return True, self.orders[intent.run_id]["id"]

    def cancel_order(self, intent, *, broker_order_id):
        assert self.orders[intent.run_id]["id"] == broker_order_id
        self.cancels.append(broker_order_id)
        self.orders[intent.run_id].update(open=False, cancelled=True)
        return True


@pytest.fixture
def harness(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network access forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    paths = {
        "state_root": tmp_path / "private",
        "runtime_projection_path": tmp_path / "runtime" / "canary.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency.json",
        "execution_control_path": tmp_path / "control.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": tmp_path / "repo",
    }
    client = SuccessorClient(paths["state_root"])

    def visit(**kwargs):
        return cycle.run_kis_paper_spy_fill_cycle(**({
            **paths, "cycle_id": "synthetic-successor", "environment": ENV,
            "execute": True, "client": client, "now": client.now,
        } | kwargs))

    assert visit().status == "pending"
    client.fill_immediately = False
    assert visit().status == "pending"
    binding = cycle._binding("synthetic-successor", client._config)
    original = binding["sell_run_id"]
    store = KisPaperCanaryStateStore(paths["state_root"] / (original + ".json"))
    state = store.read()
    client.orders[original].update(open=False, cancelled=True)
    store.transition(
        state.intent, expected=frozenset({"submitted"}), phase="cancelled",
        reason_code="reconciliation_clean", now=client.now,
    )
    client.fill_immediately = True
    return paths, client, visit


def binding_path(paths):
    return (
        paths["state_root"] / ".spy_fill_cycles" / (cycle._digest("synthetic-successor") + ".json")
    )


def binding_read(paths):
    return cycle._read_json(binding_path(paths))


def state_store(paths, run_id):
    return KisPaperCanaryStateStore(paths["state_root"] / (run_id + ".json"))


def assert_owned(paths):
    assert (paths["state_root"] / ".spy_fill_active.json").exists()


def leave_plan(paths, visit, monkeypatch, *, recorded=False):
    original = cycle._atomic_json

    def interrupt(path, payload):
        original(path, payload)
        if path == binding_path(paths) and payload.get("sell_successors"):
            if (payload["sell_successors_recorded"] == len(payload["sell_successors"])) == recorded:
                raise SystemExit("synthetic binding crash")

    with monkeypatch.context() as patch:
        patch.setattr(cycle, "_atomic_json", interrupt)
        with pytest.raises(SystemExit):
            visit()
    return binding_read(paths)["sell_successors"][-1]


def test_legacy_cancelled_exit_appends_one_link_and_closes_flat(harness):
    paths, client, visit = harness
    original = binding_read(paths)
    identities = {
        side: state_store(paths, original[side + "_run_id"]).read().intent
        for side in ("buy", "sell")
    }
    client.now += timedelta(days=1)
    result = visit()
    assert result.status == "complete", json.dumps(result.safe_payload())
    binding = binding_read(paths)
    assert {key: binding[key] for key in original} == original
    link = binding["sell_successors"][0]
    assert binding["sell_successors_recorded"] == 1
    assert link["predecessor_run_id"] == identities["sell"].run_id
    assert link["predecessor_intent_ref"] == identities["sell"].fingerprint
    assert link["run_id"] not in {intent.run_id for intent in identities.values()}
    for intent in identities.values():
        assert state_store(paths, intent.run_id).read().intent == intent
    cancelled = state_store(paths, identities["sell"].run_id).read()
    assert cancelled.phase == "cancelled" and cancelled.current_fill.observed_at == client.now
    assert result.entry_gross_cashflow == D("-600.13")
    assert result.exit_gross_cashflow == D("600.11")
    assert len(client.submits) == 3
    assert visit().status == "complete" and len(client.submits) == 3
    assert not (paths["state_root"] / ".spy_fill_active.json").exists()
    assert json.dumps(result.safe_payload()).find(link["run_id"]) == -1


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("boundary", ["plan", "intent", "commit", "started", "ack", "fill"])
def test_restart_at_each_persist_boundary_never_duplicates(harness, monkeypatch, boundary, after):
    paths, client, visit = harness
    atomic = cycle._atomic_json
    ledger_write = KisPaperCanaryStateStore._write_unlocked
    fired = []

    def hit(write, *args):
        if not after:
            fired.append(boundary)
            raise SystemExit("synthetic persistence loss")
        write(*args)
        fired.append(boundary)
        raise SystemExit("synthetic persistence loss")

    def binding_write(path, payload):
        if path == binding_path(paths) and payload.get("sell_successors"):
            kind = "commit" if payload["sell_successors_recorded"] else "plan"
            if boundary == kind:
                return hit(atomic, path, payload)
        return atomic(path, payload)

    def state_write(store, state):
        if state.intent.run_id.endswith("-x"):
            kind = {"intent_recorded": "intent", "submission_started": "started"}.get(state.phase)
            if state.phase == "submitted":
                kind = "fill" if state.current_fill is not None else "ack"
            if boundary == kind:
                return hit(ledger_write, store, state)
        return ledger_write(store, state)

    with monkeypatch.context() as patch:
        patch.setattr(cycle, "_atomic_json", binding_write)
        patch.setattr(KisPaperCanaryStateStore, "_write_unlocked", state_write)
        with pytest.raises(SystemExit):
            visit()
    assert fired == [boundary]
    post_count = len(client.submits)
    lost_identity = (boundary == "started" and after) or (boundary == "ack" and not after)
    for _ in range(2):
        outcome = visit()
        if lost_identity:
            assert outcome.status == "recovery_required"
            assert_owned(paths)
            assert len(client.submits) == post_count
        else:
            assert outcome.status == "complete"
            assert len(client.submits) == 3


@pytest.mark.parametrize("fault", [SystemExit, KisPaperCanaryError])
def test_unknown_post_never_reposts_or_reprices(harness, fault):
    paths, client, visit = harness
    client.submit_fault = fault
    if fault is SystemExit:
        with pytest.raises(SystemExit):
            visit()
    else:
        assert visit().status == "recovery_required"
    link = binding_read(paths)["sell_successors"][0]
    original_intent = state_store(paths, link["run_id"]).read().intent
    client.submit_fault = None
    client.now += timedelta(days=1)
    for _ in range(3):
        assert visit().status == "recovery_required"
    assert len(client.submits) == 3
    assert state_store(paths, link["run_id"]).read().intent == original_intent
    assert len(binding_read(paths)["sell_successors"]) == 1
    assert_owned(paths)


@pytest.mark.parametrize("recorded", [False, True])
def test_expired_unsubmitted_plan_is_scoped_unresolved(harness, monkeypatch, recorded):
    paths, client, visit = harness
    link = leave_plan(paths, visit, monkeypatch, recorded=recorded)
    before = binding_path(paths).read_bytes()
    client.now += timedelta(seconds=121)
    for _ in range(2):
        assert visit().reason_code == "exit_not_submitted_expired"
    assert binding_path(paths).read_bytes() == before
    assert len(client.submits) == 2
    assert len(binding_read(paths)["sell_successors"]) == 1
    assert link["intent"]["limit_price"] == "600.11"
    assert_owned(paths)


def test_resume_plan_preserves_price_when_fresh_quote_changes(harness, monkeypatch):
    paths, client, visit = harness
    link = leave_plan(paths, visit, monkeypatch)
    fetch = client.fetch_spy_limit_input
    monkeypatch.setattr(client, "fetch_spy_limit_input", lambda **kw: replace(
        fetch(**kw), best_bid=D("600.10")
    ))
    assert visit().reason_code == "unsubmitted_price_changed"
    assert binding_read(paths)["sell_successors"][0] == link
    assert state_store(paths, link["run_id"]).read().intent.limit_price == D("600.11")
    assert len(client.submits) == 2


@pytest.mark.parametrize(
    "change", ["missing", "fingerprint", "predecessor", "run", "price", "count"]
)
def test_invalid_links_fail_before_broker_reads(harness, monkeypatch, change):
    paths, client, visit = harness
    link = leave_plan(paths, visit, monkeypatch, recorded=True)
    binding = binding_read(paths)
    if change == "missing":
        state_store(paths, link["run_id"]).path.unlink()
    elif change == "fingerprint":
        binding["sell_successors"][0]["predecessor_intent_ref"] = "sha256:" + "0" * 64
    elif change == "predecessor":
        binding["sell_successors"][0]["predecessor_run_id"] = binding["buy_run_id"]
    elif change == "run":
        binding["sell_successors"][0]["run_id"] += "-arbitrary"
    elif change == "price":
        binding["sell_successors"][0]["intent"]["limit_price"] = "599"
    else:
        binding["sell_successors_recorded"] = False
    cycle._atomic_json(binding_path(paths), binding)
    calls = len(client.calls)
    assert visit().status == "recovery_required"
    assert len(client.calls) == calls and len(client.submits) == 2
    assert cycle.conflicts_with_active_spy_fill_cycle(paths["state_root"], link["run_id"], "SPY")


@pytest.mark.parametrize("proof", [
    "cancel_ack_only", "no_history", "stale", "remaining", "unavailable", "incomplete",
    "identity", "unresolved", "matching_open", "untyped", "account_stale",
])
def test_cancelled_phase_alone_cannot_admit_successor(harness, proof):
    paths, client, visit = harness
    original = binding_read(paths)["sell_run_id"]

    def change(rec):
        observation = rec.execution
        if proof == "cancel_ack_only":
            return replace(rec, execution=replace(observation, cancellation_confirmed=False))
        if proof == "no_history":
            return replace(rec, matching_ccnl=False, execution=None)
        if proof == "stale":
            old = client.now - timedelta(seconds=121)
            return replace(rec, execution=replace(
                observation, observed_at=old, fill=replace(observation.fill, observed_at=old)
            ))
        if proof == "remaining":
            return replace(rec, execution=replace(
                observation, cancellation_confirmed=False,
                fill=replace(observation.fill, remaining_quantity=D(1)),
            ))
        if proof == "unavailable":
            return replace(rec, account_status="unavailable")
        if proof == "incomplete":
            return replace(rec, snapshot=replace(rec.snapshot, open_orders=replace(
                rec.snapshot.open_orders, complete=False
            )))
        if proof == "identity":
            return replace(rec, snapshot=replace(rec.snapshot, identity=replace(
                rec.snapshot.identity, masked_account="invalid"
            )))
        if proof == "unresolved":
            return replace(rec, status="unresolved")
        if proof == "matching_open":
            return replace(rec, matching_open_order=True)
        if proof == "untyped":
            from types import SimpleNamespace

            return replace(rec, execution=SimpleNamespace(**observation.__dict__))
        return replace(rec, snapshot=replace(
            rec.snapshot, captured_at=client.now - timedelta(seconds=121)
        ))

    # Keep stale history later than the persisted submission time.
    client.now += timedelta(seconds=180)
    client.proof_override[original] = change
    assert visit().status in {"pending", "recovery_required"}
    assert "sell_successors" not in binding_read(paths)
    assert len(client.submits) == 2
    assert_owned(paths)


@pytest.mark.parametrize("block", ["market", "pause", "emergency", "inventory", "open", "buy"])
def test_admission_checks_precede_planning(harness, block):
    paths, client, visit = harness
    if block == "market":
        client.now = client.now.replace(hour=2)
    elif block == "pause":
        PaperExecutionControlStore(paths["execution_control_path"]).set_pause_sells(True)
    elif block == "emergency":
        EmergencyStore(paths["emergency_state_path"]).stop_new_orders("synthetic")
    elif block == "inventory":
        client.position_override = 0
    elif block == "open":
        client.foreign_open = True
    else:
        client.proof_override[binding_read(paths)["buy_run_id"]] = lambda rec: replace(
            rec, execution=None
        )
    assert visit().status != "complete"
    assert len(client.submits) == 2
    assert "sell_successors" not in binding_read(paths)
    assert_owned(paths)


def test_cancelled_successor_can_extend_chain_one_link_per_visit(harness):
    paths, client, visit = harness
    client.fill_immediately = False
    assert visit().status == "pending"
    first = binding_read(paths)["sell_successors"][0]
    assert visit().status == "pending" and len(client.submits) == 3
    client.now += timedelta(seconds=301)
    assert visit().reason_code == "cancellation_reconciled"
    assert len(client.submits) == 3
    client.fill_immediately = True
    result = visit()
    assert result.status == "complete"
    links = binding_read(paths)["sell_successors"]
    assert len(links) == 2 and links[0] == first
    assert links[1]["predecessor_intent_ref"] == first["intent_ref"]
    assert result.exit_gross_cashflow == D("600.11")
    assert len(client.submits) == 4


@pytest.mark.parametrize("change", ["reorder", "remove", "pending", "partial", "stale"])
def test_all_ancestors_remain_validated(harness, monkeypatch, change):
    paths, client, visit = harness
    client.fill_immediately = False
    visit()
    client.now += timedelta(seconds=301)
    visit()
    client.fill_immediately = True
    leave_plan(paths, visit, monkeypatch, recorded=False)
    binding = binding_read(paths)
    original = binding["sell_run_id"]
    if change == "reorder":
        binding["sell_successors"].reverse()
    elif change == "remove":
        binding["sell_successors"].pop(0)
    elif change == "pending":
        store = state_store(paths, original)
        store._write_unlocked(replace(store.read(), phase="submitted"))
        client.proof_override[original] = lambda rec: replace(rec, execution=replace(
            rec.execution, cancellation_confirmed=False
        ))
    elif change == "partial":
        # One share cannot have a valid fractional cumulative fill; reject the
        # malformed partial ledger, too, rather than adopting a residual.
        store = state_store(paths, original)
        payload = json.loads(store.path.read_text())
        payload["cumulative_fill"]["quantity"] = "0.5"
        store.path.write_text(json.dumps(payload))
    else:
        client.proof_override[original] = lambda rec: replace(rec, execution=None)
    cycle._atomic_json(binding_path(paths), binding)
    assert visit().status in {"pending", "recovery_required"}
    assert len(client.submits) == 3
    assert_owned(paths)


@pytest.mark.parametrize("closure", ["position", "open", "stale", "write_failure"])
def test_flat_closure_required_after_successor_fill(harness, monkeypatch, closure):
    paths, client, visit = harness
    run = cycle._run_kis_paper_canary

    def after_sell(**kwargs):
        outcome = run(**kwargs)
        if kwargs["run_id"].endswith("-x"):
            if closure == "position":
                client.position_override = 1
            elif closure == "open":
                client.foreign_open = True
            elif closure == "stale":
                client.component_age["snapshot"] = 121
            else:
                raise OSError("synthetic projection failure after persisted fill")
        return outcome

    with monkeypatch.context() as patch:
        patch.setattr(cycle, "_run_kis_paper_canary", after_sell)
        assert visit().status == "recovery_required"
    assert_owned(paths)
    client.position_override, client.foreign_open = None, False
    client.component_age.clear()
    assert visit().status == "complete"
    assert len(client.submits) == 3


def test_only_committed_bound_tail_can_share_owner(harness, monkeypatch):
    paths, client, visit = harness
    link = leave_plan(paths, visit, monkeypatch)
    root = paths["state_root"]
    assert cycle.conflicts_with_active_spy_fill_cycle(root, link["run_id"], "SPY")
    leave_plan(paths, visit, monkeypatch, recorded=True)
    assert not cycle.conflicts_with_active_spy_fill_cycle(root, link["run_id"], "SPY")
    for run_id in (link["run_id"] + "-arbitrary", link["run_id"] + "2", "budget-other"):
        assert cycle.conflicts_with_active_spy_fill_cycle(root, run_id, "SPY")
        assert not cycle.conflicts_with_active_spy_fill_cycle(root, run_id, "QQQ")
    calls = len(client.calls)
    assert visit(cycle_id="different-cycle").reason_code == "another_cycle_unresolved"
    assert len(client.calls) == calls
    assert visit().status == "complete"


def test_budget_conflict_still_owns_its_exclusion(harness, monkeypatch):
    from thericher_v2.execution import kis_paper_budget_strategy as budget

    paths, client, visit = harness
    seen = []

    def conflicting(root, run_id, symbol):
        assert symbol == "SPY"
        seen.append((root, run_id))
        return True

    monkeypatch.setattr(budget, "conflicts_with_budget_strategy", conflicting)
    assert visit().reason_code == "submission_not_started"
    assert len(seen) == 1 and seen[0][1].endswith("-x")
    assert len(client.submits) == 2
    assert_owned(paths)


def test_orphan_state_is_not_adopted_after_binding_loss(harness, monkeypatch):
    paths, client, visit = harness
    original = binding_read(paths)
    link = leave_plan(paths, visit, monkeypatch, recorded=True)
    before = state_store(paths, link["run_id"]).path.read_bytes()
    cycle._atomic_json(binding_path(paths), original)
    assert visit().reason_code == "successor_state_unbound"
    assert state_store(paths, link["run_id"]).path.read_bytes() == before
    assert binding_read(paths) == original and len(client.submits) == 2


def test_started_intent_cannot_reattach_to_uncommitted_plan(harness, monkeypatch):
    paths, client, visit = harness
    link = leave_plan(paths, visit, monkeypatch, recorded=True)
    store = state_store(paths, link["run_id"])
    store.transition(
        store.read().intent, expected=frozenset({"intent_recorded"}),
        phase="submission_started", reason_code="preview", now=client.now,
        submission_started_at=client.now,
    )
    binding = binding_read(paths)
    binding["sell_successors_recorded"] = 0
    cycle._atomic_json(binding_path(paths), binding)
    calls = len(client.calls)
    assert visit().reason_code == "successor_binding_mismatch"
    assert len(client.calls) == calls and len(client.submits) == 2


@pytest.mark.parametrize("change", ["predecessor", "inventory", "pause", "emergency", "market"])
def test_pre_post_callback_rechecks_successor_admission(harness, monkeypatch, change):
    paths, client, visit = harness
    run = cycle._run_kis_paper_canary
    original = binding_read(paths)["sell_run_id"]
    client.now = client.now.replace(hour=19, minute=59, second=50)

    def inject(**kwargs):
        if kwargs["run_id"].endswith("-x"):
            permitted = kwargs["submit_permitted"]

            def changed(submit_at):
                if change == "predecessor":
                    client.proof_override[original] = lambda rec: replace(rec, execution=replace(
                        rec.execution, cancellation_confirmed=False
                    ))
                elif change == "inventory":
                    client.position_override = 0
                elif change == "pause":
                    PaperExecutionControlStore(paths["execution_control_path"]).set_pause_sells(True)
                elif change == "emergency":
                    EmergencyStore(paths["emergency_state_path"]).stop_new_orders("synthetic")
                else:
                    client.now += timedelta(seconds=10)
                return permitted(submit_at)

            kwargs["submit_permitted"] = changed
        return run(**kwargs)

    monkeypatch.setattr(cycle, "_run_kis_paper_canary", inject)
    outcome = visit(now=None, clock=lambda: client.now)
    assert outcome.status in {"recovery_required", "no_intent"}
    link = binding_read(paths)["sell_successors"][0]
    assert state_store(paths, link["run_id"]).read().phase == "intent_recorded"
    assert len(client.submits) == 2
    assert_owned(paths)


@pytest.mark.parametrize("after", [False, True])
def test_restart_at_ownership_release_does_not_repeat_exit(harness, monkeypatch, after):
    paths, client, visit = harness
    active = paths["state_root"] / ".spy_fill_active.json"
    unlink = type(active).unlink

    def fail_release(path, *args, **kwargs):
        if path == active:
            if after:
                unlink(path, *args, **kwargs)
            raise SystemExit("synthetic release crash")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(type(active), "unlink", fail_release)
        with pytest.raises(SystemExit):
            visit()
    assert len(client.submits) == 3
    assert visit().status == "complete"
    assert len(client.submits) == 3 and not active.exists()
