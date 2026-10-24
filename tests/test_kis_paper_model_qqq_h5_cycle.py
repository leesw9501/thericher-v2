"""Invented, network-denied real Canary lifecycle and V4 crash transitions."""

import copy
import json
import socket
import urllib.request
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_model_qqq_h5 import PIN, SOURCE, _entry, _legacy_state, _reads, _refresh
from test_kis_paper_portfolio_execute import ACCOUNT, CONFIG
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_canary as canary
from thericher_v2.execution import kis_paper_model_qqq_h5 as core
from thericher_v2.execution import kis_paper_model_qqq_h5_cycle as cycle
from thericher_v2.execution.emergency import PaperExecutionControlStore
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_quote import KisPaperQuoteError
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
from thericher_v2.execution.kis_readonly import KisPaperOpenOrder, KisPaperOpenOrdersSnapshot

D = Decimal


def native_reads(*args, **kwargs):
    reads = _reads(*args, **kwargs)
    return replace(
        reads,
        snapshot=replace(
            reads.snapshot,
            identity=replace(
                reads.snapshot.identity, masked_account=CONFIG.masked_account_identity
            ),
        ),
    )


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("invented_qqq_cycle_must_not_reach_network_or_credentials")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", denied)
    monkeypatch.setattr(canary.UrllibKisPaperCanaryTransport, "request", denied)
    monkeypatch.setattr(canary, "load_kis_paper_config_from_environment", denied)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", denied)


class NativeSyntheticClient(canary.KisPaperCanaryClient):
    def __init__(self, root, value):
        super().__init__(config=CONFIG, transport=None)
        self.root, self.value = root, value
        self.now = value.entry_session.open_ts + timedelta(minutes=10)
        self.orders, self.submits = {}, []
        self.price, self.funds = D(10), D(1000)
        self.partial = self.partial_terminal = self.unknown = False
        self.history_unavailable = self.recover_id = False
        self.account_unavailable = False
        self.reject = False
        self.on_reconcile = None
        self.pins = None

    def quantity(self):
        return sum(
            (o["filled"] * (1 if o["intent"].side == "buy" else -1) for o in self.orders.values()),
            D(0),
        )

    def snapshot(self):
        snapshot = native_reads(
            self.value,
            ACCOUNT,
            self.now,
            price=str(self.price),
            funds=str(self.funds),
            cash=str(self.funds),
            quantity=str(self.quantity()),
        ).snapshot
        opens = tuple(
            KisPaperOpenOrder(
                canary._redacted_open_order_reference(o["id"]),
                "QQQ",
                "NASD",
                "USD",
                o["intent"].side,
                o["intent"].quantity,
                o["filled"],
                o["remaining"],
                o["intent"].limit_price,
                self.now,
            )
            for o in self.orders.values()
            if o["remaining"]
        )
        return replace(snapshot, open_orders=KisPaperOpenOrdersSnapshot(opens, self.now))

    def submit_limit(self, intent, **_kwargs):
        state = canary.KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.intent == intent and state.phase == "submission_started"
        pointer = self.root / ("h5qqq-" + self.pins.input_ref[7:] + ".json")
        record = cycle._load(pointer, self.pins)
        assert record["pending"]["wire_started_at"] is not None
        assert record["pending"]["seed"]["intent"] == intent.to_dict()
        binding = budget._load_binding(self.root, ACCOUNT)
        assert binding["qqq"] == record["pending"]["proposed"]["qqq"]
        assert not budget.conflicts_with_budget_strategy(self.root, intent.run_id, "QQQ")
        cycle._book(self.root, self.pins, self.now)
        self.submits.append(intent)
        if self.reject:
            return False, None
        filled = D(1) if self.partial or self.partial_terminal else intent.quantity
        remaining = intent.quantity - filled if self.partial else D(0)
        self.orders[intent.run_id] = dict(
            intent=intent, filled=filled, remaining=remaining, id=str(100 + len(self.submits))
        )
        if self.unknown:
            raise canary.KisPaperCanaryError(
                "submit_transport_unknown", submit_response_category="transport_unavailable"
            )
        return True, self.orders[intent.run_id]["id"]

    def reconcile(self, state, *, now):
        if self.on_reconcile:
            self.on_reconcile(state)
        order = self.orders.get(state.intent.run_id)
        known = order is not None and order["id"] == state.broker_order_id
        observation = None
        if known and not self.history_unavailable:
            fill = KisPaperCumulativeFill(
                fill_identity_ref(
                    raw_order_id=order["id"],
                    order_at=state.submission_started_at,
                    symbol="QQQ",
                    exchange="NASD",
                    side=state.intent.side,
                    quantity=state.intent.quantity,
                ),
                state.intent.quantity,
                order["filled"],
                order["filled"] * state.intent.limit_price,
                now,
                order["remaining"],
            )
            observation = KisPaperExecutionObservation(1, True, "available", fill, now)
        return canary.KisPaperCanaryReconciliation(
            snapshot=self.snapshot(),
            account_status="unavailable" if self.account_unavailable else "available",
            ccnl_row_count=int(known),
            matching_open_order=bool(known and order["remaining"]),
            matching_ccnl=known,
            status="clean" if known or state.phase == "intent_recorded" else "unresolved",
            execution=observation,
            recovered_broker_order_id=(
                order["id"]
                if self.recover_id and order is not None and state.broker_order_id is None
                else None
            ),
        )

    def cancel_order(self, *_args, **_kwargs):
        pytest.fail("qqq_h5_preparation_does_not_cancel")


class SyntheticProvider:
    def __init__(self, client, pins):
        self.client, self.pins = client, pins
        self.calls = []
        self.on_read = None
        self.market_reads_available = True
        self.market_read_count = 0

    def __call__(self, request):
        self.calls.append(request)
        client, pins = self.client, self.pins
        boundary = core.QqqH5WriterBoundary(
            pins.writer_source_ref,
            request.custody_ref,
            pins.writer_membership_ref,
            client.now,
            client.value.exit_session.close_ts + timedelta(days=1),
            pins.legacy_sources,
            pins.legacy_sources,
        )
        reads = None
        if request.purpose == "pre_submit":
            assert self.market_reads_available, "invented_quote_and_orderability_unavailable"
            self.market_read_count += 1
            reads = native_reads(
                client.value,
                ACCOUNT,
                client.now,
                price=str(client.price),
                cash=str(client.funds),
                funds=str(client.funds),
                quantity=str(client.quantity()),
                side=request.side,
            )
        else:
            assert request.purpose == "custody_reconcile"
        evidence = cycle.QqqH5CycleEvidence(pins.provider_source_ref, boundary, reads)
        return self.on_read(evidence) if self.on_read else evidence


@pytest.fixture
def harness(tmp_path):
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
    binding = args["binding"]
    binding["account_ref"] = ACCOUNT
    binding["basis_ref"] = budget._basis(binding).fingerprint
    _refresh(binding)
    root = tmp_path / "p"
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    for state in args["states"].values():
        budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
    pins = cycle.QqqH5CyclePins(
        account_ref=ACCOUNT,
        basis_ref=binding["basis_ref"],
        cycle_id=binding["qqq"]["cycle_id"],
        input_ref=args["value"].input_ref,
        policy_ref=args["value"].policy_ref,
        execution_source_ref=SOURCE,
        provider_source_ref=PIN,
        writer_source_ref=SOURCE,
        writer_membership_ref=PIN,
        legacy_sources=(SOURCE,),
    )
    paths = cycle.QqqH5CyclePaths(
        state_root=root,
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "a",
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        execution_control_path=tmp_path / "control.json",
    )
    client = NativeSyntheticClient(root, args["value"])
    client.pins = pins
    return dict(
        pins=pins,
        paths=paths,
        value=args["value"],
        phase="entry",
        execute=True,
        clock=lambda: client.now,
        client=client,
        evidence_provider=SyntheticProvider(client, pins),
    )


def record(call):
    return cycle._load(
        call["paths"].state_root / ("h5qqq-" + call["pins"].input_ref[7:] + ".json"), call["pins"]
    )


def pending_state(call):
    run = record(call)["pending"]["seed"]["intent"]["run_id"]
    return canary.KisPaperCanaryStateStore(call["paths"].state_root / (run + ".json")).read()


def foreign_reservation(root):
    state = _legacy_state("bs-" + "e" * 64, symbol="SPY", phase="intent_recorded")
    budget._atomic_json(root / (state.intent.run_id + ".json"), state.to_dict())
    binding = budget._load_binding(root)
    binding["orders"].append(
        dict(run_id=state.intent.run_id, intent_ref=state.intent.fingerprint, closed=False)
    )
    _refresh(binding)
    budget._atomic_json(root / budget.BUDGET_FILE, binding)
    return binding


def test_default_inert_has_no_files_client_or_provider_calls(harness):
    call = dict(harness, execute=False)
    before = sorted(str(p) for p in harness["paths"].state_root.iterdir())
    assert cycle.run_qqq_h5_cycle(**call).status == "inert"
    assert sorted(str(p) for p in harness["paths"].state_root.iterdir()) == before
    assert not harness["evidence_provider"].calls and not harness["client"].submits


def test_native_buy_once_old_prefix_v4_and_due_exit_exact_subset(harness):
    root, client = harness["paths"].state_root, harness["client"]
    before = budget._load_binding(root)
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    after = budget._load_binding(root)
    assert set(after) == budget._V4_KEYS
    assert after["qqq"]["orders"][:2] == before["qqq"]["orders"]
    assert {k: after[k] for k in before if k not in {"qqq", "terminal_evidence"}} == {
        k: before[k] for k in before if k not in {"qqq", "terminal_evidence"}
    }
    assert len(client.submits) == 1 and client.submits[0].quantity == 5
    assert cycle.run_qqq_h5_cycle(**harness).reason == "entry_already_bound"
    harness["phase"] = "exit"
    assert cycle.run_qqq_h5_cycle(**harness).reason == "before_h5_exit"
    client.now = harness["value"].metadata.exit_not_before
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert client.submits[-1].side == "sell" and client.submits[-1].quantity == 5
    assert cycle.run_qqq_h5_cycle(**harness).status == "closed"
    assert cycle.run_qqq_h5_cycle(**harness).runtime_authorized is False
    assert len(client.submits) == 2 and client.quantity() == 0
    assert record(harness)["pending"] is None


@pytest.mark.parametrize("price,funds", [("100", "1000"), ("10", "9")])
def test_whole_share_zero_is_sealed_without_force_or_wire(harness, price, funds):
    harness["client"].price, harness["client"].funds = D(price), D(funds)
    assert cycle.run_qqq_h5_cycle(**harness).status == "no_intent"
    assert cycle.run_qqq_h5_cycle(**harness).status == "no_intent"
    assert not harness["client"].submits and len(harness["evidence_provider"].calls) == 1


def test_unknown_exact_pending_recovery_never_resubmits_or_releases(harness):
    client = harness["client"]
    client.unknown = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    first = pending_state(harness)
    assert first.phase == "outcome_unknown"
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    assert pending_state(harness).intent == first.intent and len(client.submits) == 1
    binding = budget._load_binding(client.root)
    assert not binding["qqq"]["orders"][-1]["closed"]
    client.recover_id = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    assert len(client.submits) == 1 and record(harness)["pending"] is not None


def test_pending_partial_then_exact_terminal_fill_and_partial_exit(harness):
    client = harness["client"]
    client.partial = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    first = pending_state(harness)
    assert first.cumulative_fill.quantity == 1
    order = client.orders[first.intent.run_id]
    client.history_unavailable = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    assert pending_state(harness).cumulative_fill == first.cumulative_fill
    client.history_unavailable = False
    order["remaining"] = D(0)
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    client.partial = False
    client.now = harness["value"].metadata.exit_not_before
    harness["phase"] = "exit"
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert client.submits[-1].quantity == 1 and len(client.submits) == 2


@pytest.mark.parametrize("stage", ["journal", "seed", "book", "marker", "terminal"])
def test_crash_each_legal_write_keeps_identity_and_no_duplicate_wire(harness, monkeypatch, stage):
    original = budget._atomic_json
    original_state = canary.KisPaperCanaryStateStore._write_unlocked
    hit = False

    def crash_state(store, state):
        nonlocal hit
        original_state(store, state)
        if stage == "seed" and not hit and state.phase == "intent_recorded":
            hit = True
            raise OSError("invented_crash")

    def crash(path, payload):
        nonlocal hit
        original(path, payload)
        is_journal = path.name.startswith("h5qqq-")
        trigger = {
            "journal": is_journal and payload["pending"] is not None,
            "seed": path.name.startswith("bq-") and payload.get("phase") == "intent_recorded",
            "book": path.name == budget.BUDGET_FILE and len(payload["qqq"]["orders"]) == 3,
            "marker": is_journal
            and payload["pending"] is not None
            and payload["pending"]["wire_started_at"] is not None,
            "terminal": path.name == budget.BUDGET_FILE and payload["qqq"]["orders"][-1]["closed"],
        }[stage]
        if trigger and not hit:
            hit = True
            raise OSError("invented_crash")

    monkeypatch.setattr(budget, "_atomic_json", crash)
    monkeypatch.setattr(canary.KisPaperCanaryStateStore, "_write_unlocked", crash_state)
    with pytest.raises(OSError, match="invented_crash"):
        cycle.run_qqq_h5_cycle(**harness)
    assert hit
    retained = copy.deepcopy(record(harness))
    monkeypatch.setattr(budget, "_atomic_json", original)
    monkeypatch.setattr(canary.KisPaperCanaryStateStore, "_write_unlocked", original_state)
    result = cycle.run_qqq_h5_cycle(**harness)
    assert result.status in {"pending", "advanced"}
    assert len(harness["client"].submits) == (0 if stage == "marker" else 1)
    current = record(harness)
    assert core.serialize_qqq_h5_journal(
        cycle._journal(current, harness["pins"])
    ) == core.serialize_qqq_h5_journal(cycle._journal(retained, harness["pins"]))
    if stage == "marker":
        assert pending_state(harness).phase == "outcome_unknown"


def test_crash_before_book_then_foreign_change_never_overwrites_or_submits(harness, monkeypatch):
    original = budget._atomic_json

    def fail_book(path, payload):
        if path.name == budget.BUDGET_FILE:
            raise OSError("invented_before_book")
        original(path, payload)

    monkeypatch.setattr(budget, "_atomic_json", fail_book)
    with pytest.raises(OSError):
        cycle.run_qqq_h5_cycle(**harness)
    monkeypatch.setattr(budget, "_atomic_json", original)
    root = harness["paths"].state_root
    foreign_reservation(root)
    raw = (root / budget.BUDGET_FILE).read_bytes()
    with pytest.raises(_RecoveryRequired, match="parent_changed"):
        cycle.run_qqq_h5_cycle(**harness)
    assert (root / budget.BUDGET_FILE).read_bytes() == raw
    assert not harness["client"].submits and record(harness)["pending"] is not None


@pytest.mark.parametrize(
    "change", ["funds", "quote", "foreign", "stale", "writers", "controls", "book", "journal"]
)
def test_fresh_native_callback_rejects_changed_facts_before_wire(harness, change):
    provider, client = harness["evidence_provider"], harness["client"]

    def mutate(evidence):
        if len(provider.calls) != 2:
            return evidence
        if change == "funds":
            return replace(
                evidence,
                reads=replace(
                    evidence.reads,
                    orderable=replace(evidence.reads.orderable, orderable_funds=D(0)),
                ),
            )
        if change == "quote":
            return replace(
                evidence,
                reads=replace(evidence.reads, quote=replace(evidence.reads.quote, best_ask=D(11))),
            )
        if change == "foreign":
            reads = native_reads(client.value, ACCOUNT, client.now, quantity="1")
            return replace(evidence, reads=reads)
        if change == "stale":
            return replace(
                evidence,
                reads=replace(
                    evidence.reads,
                    completed_at=client.now - timedelta(seconds=121),
                    started_at=client.now - timedelta(seconds=122),
                ),
            )
        if change == "writers":
            return replace(
                evidence,
                writer_boundary=replace(evidence.writer_boundary, unresolved_sources=(SOURCE,)),
            )
        if change == "controls":
            PaperExecutionControlStore(harness["paths"].execution_control_path).set_pause_buys(True)
        if change == "book":
            foreign_reservation(client.root)
        if change == "journal":
            pointer = client.root / ("h5qqq-" + client.pins.input_ref[7:] + ".json")
            document = record(harness)
            document["status"] = "no_intent"
            cycle._save(pointer, document)
        return evidence

    provider.on_read = mutate
    with pytest.raises((_RecoveryRequired, ValueError)):
        cycle.run_qqq_h5_cycle(**harness)
    assert not client.submits
    assert not budget._load_binding(client.root)["qqq"]["orders"][-1]["closed"]


def test_exact_unbound_seed_cannot_be_overwritten_after_journal_crash(harness, monkeypatch):
    original = budget._atomic_json

    def crash(path, payload):
        original(path, payload)
        if path.name.startswith("h5qqq-"):
            raise OSError("invented_journal_crash")

    monkeypatch.setattr(budget, "_atomic_json", crash)
    with pytest.raises(OSError):
        cycle.run_qqq_h5_cycle(**harness)
    monkeypatch.setattr(budget, "_atomic_json", original)
    seed = canary.KisPaperCanaryState.from_dict(record(harness)["pending"]["seed"])
    changed = replace(seed, intent=replace(seed.intent, quantity=D(1)))
    path = harness["client"].root / (seed.intent.run_id + ".json")
    original(path, changed.to_dict())
    raw = path.read_bytes()
    with pytest.raises(_RecoveryRequired, match="orphan_seed_changed"):
        cycle.run_qqq_h5_cycle(**harness)
    assert path.read_bytes() == raw and not harness["client"].submits


def test_unbound_qqq_request_does_not_become_latest_recovery(harness):
    unknown = _legacy_state("bq-" + "f" * 64, symbol="QQQ", phase="intent_recorded")
    budget._atomic_json(
        harness["client"].root / (unknown.intent.run_id + ".json"), unknown.to_dict()
    )
    with pytest.raises(_RecoveryRequired, match="unbound_qqq_state"):
        cycle.run_qqq_h5_cycle(**harness)
    assert not harness["client"].submits and not harness["evidence_provider"].calls


def test_wrong_input_or_client_never_stages(harness):
    harness["pins"] = replace(harness["pins"], input_ref=PIN)
    with pytest.raises(_RecoveryRequired, match="input_changed"):
        cycle.run_qqq_h5_cycle(**harness)
    assert not harness["client"].submits and not harness["evidence_provider"].calls


def test_exit_without_this_journal_adopts_nothing(harness):
    harness["phase"] = "exit"
    assert cycle.run_qqq_h5_cycle(**harness).reason == "no_journal_no_inventory_adoption"
    assert not harness["evidence_provider"].calls


def test_expired_entry_and_early_due_are_inert(harness):
    client = harness["client"]
    client.now = harness["value"].entry_session.open_ts - timedelta(seconds=1)
    assert cycle.run_qqq_h5_cycle(**harness).status == "not_due"
    client.now = harness["value"].entry_session.close_ts
    assert cycle.run_qqq_h5_cycle(**harness).status == "not_due"
    assert not harness["evidence_provider"].calls and not client.submits


def test_next_session_marker_recovery_keeps_original_possible_call_anchor_and_ttl(
    harness, monkeypatch
):
    original = budget._atomic_json

    def crash_marker(path, payload):
        original(path, payload)
        if path.name.startswith("h5qqq-") and payload["pending"]["wire_started_at"] is not None:
            raise OSError("invented_possible_call_boundary")

    monkeypatch.setattr(budget, "_atomic_json", crash_marker)
    with pytest.raises(OSError):
        cycle.run_qqq_h5_cycle(**harness)
    first = record(harness)
    initial = pending_state(harness)
    assert initial.phase == "intent_recorded" and not harness["client"].submits
    marker = first["pending"]["wire_started_at"]
    monkeypatch.setattr(budget, "_atomic_json", original)
    harness["client"].now += timedelta(days=1)
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    state = pending_state(harness)
    assert state.phase == "outcome_unknown" and state.intent == initial.intent
    assert state.submission_started_at.isoformat() == marker
    assert state.updated_at == harness["client"].now
    assert state.intent.valid_until == initial.intent.valid_until
    assert record(harness)["pending"]["wire_started_at"] == marker
    binding, _, projection, _, _ = cycle._book(
        harness["client"].root, harness["pins"], harness["client"].now
    )
    assert not binding["qqq"]["orders"][-1]["closed"] and projection.reserved_buys == D(50)
    assert not harness["client"].submits


def test_possible_send_before_native_outcome_write_never_reissues(harness, monkeypatch):
    original = canary.KisPaperCanaryStateStore.transition

    def crash_ack(store, intent, **kwargs):
        if kwargs["phase"] == "submitted":
            raise OSError("invented_after_possible_send")
        return original(store, intent, **kwargs)

    monkeypatch.setattr(canary.KisPaperCanaryStateStore, "transition", crash_ack)
    with pytest.raises(OSError):
        cycle.run_qqq_h5_cycle(**harness)
    state = pending_state(harness)
    assert state.phase == "submission_started" and len(harness["client"].submits) == 1
    monkeypatch.setattr(canary.KisPaperCanaryStateStore, "transition", original)
    harness["client"].now += timedelta(days=1)
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    assert pending_state(harness).intent == state.intent
    assert pending_state(harness).submission_started_at == state.submission_started_at
    assert len(harness["client"].submits) == 1
    assert not budget._load_binding(harness["client"].root)["qqq"]["orders"][-1]["closed"]


def test_native_callback_uses_existing_outer_locks_in_order_without_os_reentry(
    harness, monkeypatch
):
    original = canary.exclusive_kis_paper_canary_state_lock
    stack, acquisitions = [], []

    @contextmanager
    def counted(path):
        with original(path):
            if path.name in {".session_execution", ".canary_execution"}:
                acquisitions.append(path.name)
                stack.append(path.name)
                try:
                    yield
                finally:
                    stack.pop()
            else:
                yield

    monkeypatch.setattr(canary, "exclusive_kis_paper_canary_state_lock", counted)

    def under_locks(evidence):
        assert stack == [".session_execution", ".canary_execution"]
        return evidence

    harness["evidence_provider"].on_read = under_locks
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert acquisitions == [".session_execution", ".canary_execution"] and not stack


def test_callback_native_snapshot_not_wrapper_snapshot_controls_admission(harness):
    client = harness["client"]
    snapshot = client.snapshot

    def foreign_snapshot():
        return replace(
            snapshot(), identity=replace(snapshot().identity, masked_account="****0000-**")
        )

    client.snapshot = foreign_snapshot
    with pytest.raises(ValueError, match="account_incomplete"):
        cycle.run_qqq_h5_cycle(**harness)
    assert len(harness["evidence_provider"].calls) == 2 and not client.submits


def test_already_reserved_unknown_preserves_new_foreign_reservation_during_recovery(harness):
    harness["client"].unknown = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    foreign = foreign_reservation(harness["client"].root)
    row = copy.deepcopy(foreign["orders"][-1])
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    after = budget._load_binding(harness["client"].root)
    assert after["orders"][-1] == row and after["spy_owner_ref"] == foreign["spy_owner_ref"]
    assert len(harness["client"].submits) == 1


@pytest.mark.parametrize(
    "kind", ["bool_provider", "provider_source", "membership", "client_account"]
)
def test_dependency_pins_cannot_be_replaced_by_caller_permission(harness, kind):
    if kind == "bool_provider":
        harness["evidence_provider"] = lambda _request: True
    elif kind == "client_account":
        harness["client"]._config = replace(CONFIG, account_number="00000000")
    else:

        def changed(evidence):
            if kind == "provider_source":
                return replace(evidence, provider_source_ref=SOURCE)
            return replace(
                evidence, writer_boundary=replace(evidence.writer_boundary, membership_ref=SOURCE)
            )

        harness["evidence_provider"].on_read = changed
    with pytest.raises(_RecoveryRequired):
        cycle.run_qqq_h5_cycle(**harness)
    assert not harness["client"].submits


@pytest.mark.parametrize("kind", ["pause", "account"])
def test_nonsent_diagnostics_resume_same_intent_before_ttl(harness, kind):
    client = harness["client"]
    controls = PaperExecutionControlStore(harness["paths"].execution_control_path)
    if kind == "pause":
        controls.set_pause_buys(True)
    else:
        client.account_unavailable = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    seed = pending_state(harness)
    client.now += timedelta(seconds=5)
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    diagnostic = pending_state(harness)
    assert diagnostic.updated_at > seed.updated_at
    assert diagnostic.submission_started_at is None and not client.submits
    assert record(harness)["pending"]["wire_started_at"] is None
    controls.set_pause_buys(False)
    client.account_unavailable = False
    client.now += timedelta(seconds=5)
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert len(client.submits) == 1 and client.submits[0] == seed.intent
    assert record(harness)["pending"] is None


@pytest.mark.parametrize("funds", ["1000", "100"])
def test_published_qqq_reservation_replays_current_other_owner_book(harness, funds):
    client = harness["client"]
    controls = PaperExecutionControlStore(harness["paths"].execution_control_path)
    controls.set_pause_buys(True)
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    retained = pending_state(harness).intent
    before = record(harness)
    foreign = foreign_reservation(client.root)
    client.funds = D(funds)
    controls.set_pause_buys(False)
    client.now += timedelta(seconds=5)
    if funds == "1000":
        assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
        assert client.submits == [retained]
    else:
        with pytest.raises(_RecoveryRequired, match="funds_changed"):
            cycle.run_qqq_h5_cycle(**harness)
        assert not client.submits and pending_state(harness).intent == retained
    after = budget._load_binding(client.root)
    assert after["orders"] == foreign["orders"]
    assert after["spy_owner_ref"] == foreign["spy_owner_ref"]
    assert before["pending"]["proposed"]["orders"] != after["orders"]


def test_invalid_terminal_payload_never_publishes_invalid_canonical_book(harness, monkeypatch):
    original_payload = budget._terminal_payload
    original_write = budget._atomic_json
    book_writes = []

    def corrupt(state, observation=None):
        payload = original_payload(state, observation)
        payload["cancellation"] = {"unrepresentable_nonzero_cancel": True}
        return payload

    def capture(path, payload):
        if path.name == budget.BUDGET_FILE:
            book_writes.append(copy.deepcopy(payload))
        original_write(path, payload)

    monkeypatch.setattr(budget, "_terminal_payload", corrupt)
    monkeypatch.setattr(budget, "_atomic_json", capture)
    result = cycle.run_qqq_h5_cycle(**harness)
    assert (result.status, result.reason) == ("held", "terminal_evidence_unrepresentable")
    binding = budget._load_binding(harness["client"].root)
    assert len(book_writes) == 1 and binding == book_writes[0]
    assert not binding["qqq"]["orders"][-1]["closed"]
    assert binding["qqq"]["orders"][-1]["run_id"] not in binding["terminal_evidence"]
    assert record(harness)["pending"] is not None
    cycle._book(harness["client"].root, harness["pins"], harness["client"].now)
    monkeypatch.setattr(budget, "_terminal_payload", original_payload)
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert len(harness["client"].submits) == 1


def test_terminal_partial_exit_next_visit_only_sells_exact_remaining_subset(harness):
    client = harness["client"]
    cycle.run_qqq_h5_cycle(**harness)
    client.now = harness["value"].metadata.exit_not_before
    harness["phase"] = "exit"
    client.partial_terminal = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert client.submits[-1].quantity == 5 and client.quantity() == 4
    client.partial_terminal = False
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert client.submits[-1].quantity == 4
    assert client.submits[-1].run_id != client.submits[-2].run_id
    assert cycle.run_qqq_h5_cycle(**harness).status == "closed"
    assert len(client.submits) == 3 and client.quantity() == 0


def test_rejected_entry_closes_only_exact_request_and_never_replaces_it(harness):
    harness["client"].reject = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert cycle.run_qqq_h5_cycle(**harness).reason == "entry_already_bound"
    harness["phase"] = "exit"
    assert cycle.run_qqq_h5_cycle(**harness).status == "closed"
    assert len(harness["client"].submits) == 1 and not harness["client"].orders


@pytest.mark.parametrize("kind", ["duplicate", "checksum", "noncanonical", "marker_date"])
def test_malformed_private_record_is_not_recovered_or_overwritten(harness, monkeypatch, kind):
    original = budget._atomic_json

    def crash_marker(path, payload):
        original(path, payload)
        if path.name.startswith("h5qqq-") and payload["pending"]["wire_started_at"] is not None:
            raise OSError("invented_marker_crash")

    monkeypatch.setattr(budget, "_atomic_json", crash_marker)
    with pytest.raises(OSError):
        cycle.run_qqq_h5_cycle(**harness)
    monkeypatch.setattr(budget, "_atomic_json", original)
    pointer = harness["client"].root / ("h5qqq-" + harness["pins"].input_ref[7:] + ".json")
    document = record(harness)
    if kind == "marker_date":
        document["pending"]["wire_started_at"] = (
            harness["client"].now + timedelta(days=1)
        ).isoformat()
        cycle._save(pointer, document)
    elif kind == "checksum":
        document["ref"] = PIN
        original(pointer, document)
    elif kind == "duplicate":
        raw = pointer.read_bytes().replace(b'"schema":', b'"schema":"duplicate","schema":')
        pointer.write_bytes(raw)
    else:
        pointer.write_text(json.dumps(document, indent=2), encoding="ascii")
    raw = pointer.read_bytes()
    with pytest.raises((_RecoveryRequired, ValueError)):
        cycle.run_qqq_h5_cycle(**harness)
    assert pointer.read_bytes() == raw and not harness["client"].submits


def test_shared_public_path_cannot_alias_private_custody(harness):
    harness["paths"] = replace(
        harness["paths"], runtime_projection_path=harness["client"].root / "runtime.json"
    )
    with pytest.raises(_RecoveryRequired, match="private_root_invalid"):
        cycle.run_qqq_h5_cycle(**harness)
    assert not harness["evidence_provider"].calls and not harness["client"].submits


def test_exact_pending_fill_closes_without_provider_quote_or_funds(harness):
    client, provider = harness["client"], harness["evidence_provider"]
    client.partial = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    retained = pending_state(harness)
    order = client.orders[retained.intent.run_id]
    order.update(filled=retained.intent.quantity, remaining=D(0))
    provider.market_reads_available = False
    before = provider.market_read_count

    def custody_only(evidence):
        assert provider.calls[-1].purpose == "custody_reconcile" and evidence.reads is None
        return evidence

    provider.on_read = custody_only
    assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
    assert provider.market_read_count == before and len(client.submits) == 1
    binding = budget._load_binding(client.root)
    state = canary.KisPaperCanaryStateStore(client.root / (retained.intent.run_id + ".json")).read()
    assert (
        state.intent == retained.intent
        and state.cumulative_fill.quantity == retained.intent.quantity
    )
    assert binding["qqq"]["orders"][-1]["closed"] and record(harness)["pending"] is None


def test_unknown_recovery_without_provider_market_reads_keeps_exact_reservation(harness):
    client, provider = harness["client"], harness["evidence_provider"]
    client.unknown = True
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    retained = pending_state(harness)
    provider.market_reads_available = False
    before = provider.market_read_count
    assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    assert (
        provider.calls[-1].purpose == "custody_reconcile" and provider.market_read_count == before
    )
    assert pending_state(harness).intent == retained.intent and len(client.submits) == 1
    binding, _, projection, _, _ = cycle._book(client.root, harness["pins"], client.now)
    assert not binding["qqq"]["orders"][-1]["closed"] and projection.reserved_buys == D(50)


@pytest.mark.parametrize("stage", ["entry", "callback"])
def test_pre_submit_purpose_still_requires_typed_market_reads(harness, stage):
    provider = harness["evidence_provider"]

    def missing(evidence):
        assert provider.calls[-1].purpose == "pre_submit"
        if stage == "entry" or len(provider.calls) == 2:
            return replace(evidence, reads=None)
        return evidence

    provider.on_read = missing
    with pytest.raises(ValueError, match="market_reads_required"):
        cycle.run_qqq_h5_cycle(**harness)
    assert not harness["client"].submits
    if stage == "callback":
        assert record(harness)["pending"]["wire_started_at"] is None


@pytest.mark.parametrize("phase", ["entry", "exit", "custody_reconcile"])
def test_provider_completion_uses_fresh_clock_without_backdating_facts(harness, phase):
    client, provider = harness["client"], harness["evidence_provider"]
    if phase == "exit":
        assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
        harness["phase"] = "exit"
        client.now = harness["value"].exit_session.close_ts - timedelta(minutes=10)
    elif phase == "custody_reconcile":
        client.unknown = True
        assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
        provider.market_reads_available = False
    observed = []

    def completed_later(request):
        client.now += timedelta(seconds=2)
        evidence = provider(request)
        observed.append((request, evidence, client.now))
        return evidence

    harness["evidence_provider"] = completed_later
    outcome = cycle.run_qqq_h5_cycle(**harness)
    assert outcome.status == ("pending" if phase == "custody_reconcile" else "advanced")
    for request, evidence, completed in observed:
        assert request.observed_at < completed == evidence.writer_boundary.observed_at
        if evidence.reads is not None:
            assert evidence.reads.completed_at == completed
    if phase != "custody_reconcile":
        intent = client.submits[-1]
        assert intent.created_at == observed[0][2]
        state = canary.KisPaperCanaryStateStore(client.root / (intent.run_id + ".json")).read()
        assert state.submission_started_at == observed[1][2]
    else:
        assert len(client.submits) == 1 and observed[0][1].reads is None
        assert not budget._load_binding(client.root)["qqq"]["orders"][-1]["closed"]


@pytest.mark.parametrize("stage", ["plan", "prewire", "custody_reconcile"])
@pytest.mark.parametrize("change", ["book", "state", "journal"])
def test_provider_query_cannot_rebase_changed_custody_or_journal(harness, stage, change):
    client, provider = harness["client"], harness["evidence_provider"]
    if stage == "custody_reconcile":
        client.unknown = True
        assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    elif stage == "plan" and change == "journal":
        assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
        harness["phase"] = "exit"
        client.now = harness["value"].exit_session.close_ts - timedelta(minutes=10)
    before_submits = len(client.submits)
    initial_calls = len(provider.calls)
    mutated = {}

    def during_query(evidence):
        if len(provider.calls) - initial_calls != (2 if stage == "prewire" else 1):
            return evidence
        client.now += timedelta(seconds=1)
        if change == "book":
            foreign_reservation(client.root)
            path = client.root / budget.BUDGET_FILE
        elif change == "state":
            states = cycle._book(client.root, client.pins, client.now)[1]
            state = next(iter(states.values()))
            path = client.root / (state.intent.run_id + ".json")
            budget._atomic_json(
                path,
                replace(state, updated_at=state.updated_at + timedelta(microseconds=1)).to_dict(),
            )
        else:
            path = client.root / ("h5qqq-" + client.pins.input_ref[7:] + ".json")
            document = record(harness)
            document["status"] = "no_intent"
            cycle._save(path, document)
        mutated[path] = path.read_bytes()
        return evidence

    provider.on_read = during_query
    with pytest.raises((_RecoveryRequired, ValueError)):
        cycle.run_qqq_h5_cycle(**harness)
    assert mutated and len(client.submits) == before_submits
    assert all(path.read_bytes() == payload for path, payload in mutated.items())
    if stage != "plan":
        assert not budget._load_binding(client.root)["qqq"]["orders"][-1]["closed"]


@pytest.mark.parametrize("boundary", ["proposal", "entry_close", "exit_close", "reads_ttl"])
def test_provider_query_expiration_is_checked_at_completion(harness, boundary):
    client, provider = harness["client"], harness["evidence_provider"]
    if boundary == "exit_close":
        assert cycle.run_qqq_h5_cycle(**harness).status == "advanced"
        harness["phase"] = "exit"
        client.now = harness["value"].exit_session.close_ts - timedelta(seconds=1)
    before_submits = len(client.submits)

    def expires(evidence):
        if boundary == "proposal":
            client.now = harness["value"].targets[0].proposal.valid_until
        elif boundary == "entry_close":
            client.now = harness["value"].entry_session.close_ts
        elif boundary == "exit_close":
            client.now = harness["value"].exit_session.close_ts
        else:
            client.now += timedelta(seconds=121)
        return replace(
            evidence, writer_boundary=replace(evidence.writer_boundary, observed_at=client.now)
        )

    provider.on_read = expires
    with pytest.raises((_RecoveryRequired, ValueError, KisPaperQuoteError)):
        cycle.run_qqq_h5_cycle(**harness)
    assert len(client.submits) == before_submits
    assert record(harness) is None or record(harness)["pending"] is None


@pytest.mark.parametrize("boundary", ["seed_ttl", "session_close"])
def test_provider_completion_cannot_extend_existing_seed_ttl(harness, boundary):
    client, provider = harness["client"], harness["evidence_provider"]
    if boundary == "session_close":
        client.now = harness["value"].entry_session.close_ts - timedelta(seconds=10)

    def expires_at_prewire(request):
        if provider.calls:
            client.now = pending_state(harness).intent.valid_until
        return provider(request)

    harness["evidence_provider"] = expires_at_prewire
    with pytest.raises(_RecoveryRequired, match="prewire_expired"):
        cycle.run_qqq_h5_cycle(**harness)
    assert not client.submits and record(harness)["pending"]["wire_started_at"] is None
    assert not budget._load_binding(client.root)["qqq"]["orders"][-1]["closed"]


@pytest.mark.parametrize("invalid", ["future", "stale", "holding_horizon"])
def test_post_provider_clock_keeps_writer_freshness_and_h5_retirement_bounds(harness, invalid):
    client, provider = harness["client"], harness["evidence_provider"]

    def invalid_boundary(evidence):
        boundary = evidence.writer_boundary
        if invalid == "future":
            boundary = replace(boundary, observed_at=client.now + timedelta(seconds=1))
        elif invalid == "stale":
            client.now += timedelta(seconds=121)
        else:
            boundary = replace(boundary, excluded_until=client.now + timedelta(minutes=5))
        return replace(evidence, writer_boundary=boundary)

    provider.on_read = invalid_boundary
    with pytest.raises(ValueError, match="writer"):
        cycle.run_qqq_h5_cycle(**harness)
    assert record(harness) is None and not client.submits


@pytest.mark.parametrize("stage", ["plan", "prewire", "custody_reconcile"])
def test_provider_clock_regression_never_stages_or_releases_unknown_request(harness, stage):
    client, provider = harness["client"], harness["evidence_provider"]
    if stage == "custody_reconcile":
        client.unknown = True
        assert cycle.run_qqq_h5_cycle(**harness).status == "pending"
    before_submits = len(client.submits)
    initial_calls = len(provider.calls)
    retained = record(harness)

    def regresses(evidence):
        if len(provider.calls) - initial_calls == (2 if stage == "prewire" else 1):
            client.now = provider.calls[-1].observed_at - timedelta(seconds=1)
        return evidence

    provider.on_read = regresses
    with pytest.raises(_RecoveryRequired, match="provider_clock_regressed"):
        cycle.run_qqq_h5_cycle(**harness)
    assert len(client.submits) == before_submits
    if stage == "plan":
        assert record(harness) is None
    else:
        current = record(harness)
        assert current["pending"]["wire_started_at"] == (
            None if stage == "prewire" else retained["pending"]["wire_started_at"]
        )
        if retained is not None:
            assert current == retained
        binding, _, projection, _, _ = cycle._book(
            client.root, client.pins, provider.calls[-1].observed_at
        )
        assert not binding["qqq"]["orders"][-1]["closed"]
        assert projection.reserved_buys == D(50)


def test_provider_completion_requires_aware_clock(harness):
    client, provider = harness["client"], harness["evidence_provider"]

    def naive_completion(evidence):
        client.now = client.now.replace(tzinfo=None)
        return evidence

    provider.on_read = naive_completion
    with pytest.raises(ValueError):
        cycle.run_qqq_h5_cycle(**harness)
    assert record(harness) is None and not client.submits
