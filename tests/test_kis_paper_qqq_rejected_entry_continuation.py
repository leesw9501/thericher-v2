from __future__ import annotations

import copy
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_kis_paper_portfolio_budget_integration import (
    ENV,
    Broker,
    legacy_spy,
    receipt,
    spy_args,
)
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryError,
    KisPaperCanaryStateStore,
    KisPaperSubmitRejected,
    UrllibKisPaperCanaryTransport,
)
from thericher_v2.execution.kis_readonly import (
    KisPaperCashSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperReadOnlyError,
)
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt, _derive_decision_id

D = Decimal


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("QQQ continuation tests must not access the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(UrllibKisPaperCanaryTransport, "request", forbidden)
    monkeypatch.setattr(UrllibKisPaperCanaryTransport, "request_before_deadline", forbidden)


class ContinuationBroker(Broker):
    def __init__(self, root):
        super().__init__(root)
        self.mode = "reject"
        self.exact_reads = []
        self.exact_funds = D(18000)
        self.exact_change = None

    def orderable_funds_at_limit(self, *, symbol, exchange, limit_price):
        assert (symbol, exchange, limit_price) == ("QQQ", "NASD", D("600.00"))
        self.exact_reads.append((symbol, exchange, limit_price))
        cash = KisPaperCashSnapshot("USD", self.exact_funds, self.now)
        funds = KisPaperOrderableFundsSnapshot(
            "USD",
            self.exact_funds,
            exchange,
            symbol,
            limit_price,
            self.now,
        )
        if self.exact_change:
            return self.exact_change(cash, funds, len(self.exact_reads))
        return cash, funds

    def submit_limit(self, intent, **kwargs):
        if self.mode in {"reject", "raw_category"}:
            state = KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
            assert state.phase == "submission_started"
            binding = budget._load_binding(self.root)
            assert binding["qqq"]["orders"][-1]["intent_ref"] == intent.fingerprint
            assert budget.project_budget(self.root, binding).reserved_buys >= intent.limit_price
            self.submits.append(intent)
            if self.mode == "reject":
                raise KisPaperSubmitRejected()
            raise KisPaperCanaryError(
                "submit_kis_rejected",
                submit_response_category="provider_rejected",
            )
        return super().submit_limit(intent, **kwargs)


@pytest.fixture
def harness(tmp_path):
    root = tmp_path / "synthetic-private"
    client = ContinuationBroker(root)
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
    yield root, client, args
    assert all(
        not path.is_symlink() and path.stat().st_nlink == 1 for path in tmp_path.rglob("*.json")
    )


def run(args, tag="entry-a", *, action="enter", digit="a"):
    return budget.run_kis_paper_budget_strategy(
        **(
            args
            | {
                "qqq_entry_request_id": tag,
                "receipt_loader": lambda at: receipt(at, action=action, digit=digit),
            }
        )
    )


def states(root, binding):
    return [
        KisPaperCanaryStateStore(root / (row["run_id"] + ".json")).read()
        for row in binding["qqq"]["orders"]
    ]


def reject(harness, tag="entry-a"):
    root, client, args = harness
    client.mode = "reject"
    assert run(args, tag).reason_code == "order_not_submitted_or_rejected"
    binding = budget._load_binding(root)
    row = binding["qqq"]["orders"][-1]
    state = states(root, binding)[-1]
    assert budget._qqq_rejected_entry(row, state, binding["terminal_evidence"][row["run_id"]])
    assert budget.project_budget(root, binding).reserved_buys == 0
    return binding


def persist_binding(root, binding):
    binding["qqq"]["owner_ref"] = budget._owner(
        binding,
        budget._owner_id(binding, "unit-cycle"),
        "QQQ",
        "NASD",
        binding["qqq"]["orders"],
    ).fingerprint
    budget._atomic_json(root / budget.BUDGET_FILE, binding)


def expire_unsubmitted(harness, monkeypatch):
    root, client, args = harness
    original = client.reconcile

    def slow_reconcile(state, *, now):
        client.now = state.intent.valid_until
        return original(state, now=client.now)

    with monkeypatch.context() as patch:
        patch.setattr(client, "reconcile", slow_reconcile)
        assert run(args).reason_code == "order_not_submitted_or_rejected"
    binding = budget._load_binding(root)
    state = states(root, binding)[0]
    assert state.reason_code == "intent_expired"
    assert not client.submits and state.submission_started_at is None
    return binding


def test_expired_never_submitted_prefix_allows_new_tag_not_old_tag(harness, monkeypatch):
    root, client, args = harness
    before = expire_unsubmitted(harness, monkeypatch)
    row = before["qqq"]["orders"][0]
    state = states(root, before)[0]
    old_bytes = (root / (row["run_id"] + ".json")).read_bytes()
    proof = before["terminal_evidence"][row["run_id"]]
    assert budget._qqq_closed_unfilled_entry(row, state, proof)
    assert not budget._qqq_rejected_entry(row, state, proof)
    client.mode = "accept"
    assert run(args).reason_code == "decision_already_processed"
    assert not client.submits
    client.now += timedelta(seconds=1)
    assert run(args, "entry-b", digit="b").status == "order_complete"
    client.now += timedelta(seconds=1)
    assert run(args, "entry-b", action="exit", digit="c").status == "order_complete"
    after = budget._load_binding(root)
    assert all(after[key] == before[key] for key in ("basis_ref", "allocated_usd", "legacy_spy"))
    assert after["terminal_evidence"][row["run_id"]] == proof
    assert (root / (row["run_id"] + ".json")).read_bytes() == old_bytes
    assert [intent.side for intent in client.submits] == ["buy", "sell"]
    assert budget.project_budget(root, after, qqq_cycle_id="unit-cycle").quantity == 0


@pytest.mark.parametrize("change", [
    "open", "unexpired", "unknown", "started", "ack", "category", "reason",
    "wrong_ref", "missing_proof", "changed_proof", "cancelled", "wrong_side",
])
def test_expired_prefix_requires_exact_no_side_effect_terminal_proof(
    harness, monkeypatch, change,
):
    root, _client, _args = harness
    binding = expire_unsubmitted(harness, monkeypatch)
    row = copy.deepcopy(binding["qqq"]["orders"][0])
    state = states(root, binding)[0]
    evidence = copy.deepcopy(binding["terminal_evidence"][row["run_id"]])
    if change == "open":
        row["closed"] = False
    elif change == "unexpired":
        state = replace(state, updated_at=state.intent.valid_until - timedelta(microseconds=1))
    elif change == "unknown":
        state = replace(state, phase="outcome_unknown")
    elif change == "started":
        state = replace(state, submission_started_at=state.intent.created_at)
    elif change == "ack":
        state = replace(state, broker_order_id="synthetic-ack")
    elif change == "category":
        state = replace(state, submit_response_category="payload_invalid")
    elif change == "reason":
        state = replace(state, reason_code="reconciliation_unavailable")
    elif change == "wrong_ref":
        row["intent_ref"] = "sha256:" + "0" * 64
    elif change == "missing_proof":
        evidence = None
    elif change == "changed_proof":
        evidence["state"]["updated_at"] = (state.updated_at + timedelta(seconds=1)).isoformat()
    elif change == "cancelled":
        state = replace(state, cancel_after_submit=True)
    else:
        state = replace(state, intent=replace(state.intent, side="sell"))
    # Keep the terminal bytes equal where testing a semantic contradiction.
    if evidence is not None and change not in {"changed_proof", "wrong_ref", "open"}:
        evidence["state"] = state.to_dict()
    assert not budget._qqq_closed_unfilled_entry(row, state, evidence)


def test_slow_snapshot_uses_one_pre_submit_reconciliation_not_an_extra_account_read(
    harness, monkeypatch,
):
    _root, client, args = harness
    client.mode = "accept"
    snapshot = client.snapshot
    calls = []

    def slow_snapshot():
        calls.append(client.now)
        client.now += timedelta(seconds=30 if len(calls) == 1 else 20)
        return snapshot()

    def short_receipt(at):
        fields = asdict(receipt(at))
        fields.pop("decision_id")
        fields["valid_until"] = at + timedelta(seconds=60)
        return ResearchDecisionReceipt(decision_id=_derive_decision_id(**fields), **fields)

    monkeypatch.setattr(client, "snapshot", slow_snapshot)
    outcome = budget.run_kis_paper_budget_strategy(
        **(args | {"qqq_entry_request_id": "entry-a", "receipt_loader": short_receipt})
    )
    assert outcome.status == "order_complete"
    assert len(client.submits) == 1 and len(calls) == 4
    assert len(client.exact_reads) == 2


@pytest.mark.parametrize("seconds", [-121, 6])
def test_reused_pre_submit_snapshot_rejects_stale_or_future_clock(
    harness, monkeypatch, seconds,
):
    _root, client, args = harness
    client.mode = "accept"
    reconcile = client.reconcile

    def changed(state, *, now):
        fact = reconcile(state, now=now)
        return replace(fact, snapshot=replace(
            fact.snapshot, captured_at=client.now + timedelta(seconds=seconds)
        ))

    monkeypatch.setattr(client, "reconcile", changed)
    assert run(args).reason_code == "snapshot_unavailable"
    assert not client.submits


def test_rejected_prefix_filled_buy_sell_preserves_custody_and_basis(harness):
    root, client, args = harness
    before = reject(harness)
    old = root / (before["qqq"]["orders"][0]["run_id"] + ".json")
    old_bytes = old.read_bytes()
    old_evidence = copy.deepcopy(before["terminal_evidence"])
    client.now += timedelta(seconds=1)
    client.funds *= 10
    client.mode = "accept"
    assert run(args, "entry-b", digit="b").status == "order_complete"
    after = budget._load_binding(root)
    assert after["qqq"]["orders"][:-1] == before["qqq"]["orders"]
    assert all(
        after[key] == before[key]
        for key in (
            "account_ref",
            "basis_usd",
            "allocated_usd",
            "at",
            "basis_ref",
            "spy_owner_ref",
        )
    )
    assert D(after["allocated_usd"]) == D(after["basis_usd"]) * D("0.10")
    assert after["qqq"]["cycle_id"] == before["qqq"]["cycle_id"]
    assert after["qqq"]["owner_ref"] != before["qqq"]["owner_ref"]
    assert all(after["terminal_evidence"][key] == value for key, value in old_evidence.items())
    assert (
        budget._qqq_filled_entry(
            after["qqq"]["orders"],
            states(root, after),
            after["terminal_evidence"],
        )
        == states(root, after)[1]
    )
    client.now += timedelta(seconds=1)
    assert run(args, "entry-b", action="exit", digit="c").status == "order_complete"
    assert [intent.side for intent in client.submits] == ["buy", "buy", "sell"]
    assert client.submits[-1].run_id == "bq-" + budget._digest(
        [
            "unit-cycle",
            receipt(client.now, action="exit", digit="c").decision_id,
        ]
    )
    assert old.read_bytes() == old_bytes
    assert (
        budget.project_budget(root, budget._load_binding(root), qqq_cycle_id="unit-cycle").quantity
        == 0
    )
    reads = len(client.exact_reads)
    assert run(args, "entry-c", digit="d").reason_code == "target_already_satisfied"
    assert len(client.submits) == 3 and len(client.exact_reads) == reads


def test_same_tag_is_consumed_despite_changed_time_receipt_and_history(harness):
    root, client, args = harness
    before = reject(harness, "named-entry")
    run_id = "bq-" + budget._digest(["unit-cycle", "entry-request-v1", "named-entry"])
    assert before["qqq"]["orders"][0]["run_id"] == run_id
    old_bytes = (root / (run_id + ".json")).read_bytes()
    for index, digit in enumerate(("b", "c", "d"), 1):
        client.now += timedelta(seconds=index)
        assert run(args, "named-entry", digit=digit).reason_code == "decision_already_processed"
        assert budget._load_binding(root) == before
        assert (root / (run_id + ".json")).read_bytes() == old_bytes
    assert len(client.submits) == 1 and len(client.exact_reads) == 2


def test_untagged_default_cannot_continue_but_explicit_tag_can(harness):
    root, client, args = harness
    before = reject(harness, None)
    assert len(client.exact_reads) == 1
    client.now += timedelta(seconds=1)
    assert run(args, None, digit="b").reason_code == "target_already_satisfied"
    assert len(client.submits) == 1 and budget._load_binding(root) == before
    assert run(args, "explicit-next", digit="b").reason_code == "order_not_submitted_or_rejected"
    assert len(client.submits) == 2 and len(client.exact_reads) == 3


@pytest.mark.parametrize("count", [1, 3])
def test_only_explicit_distinct_tags_extend_multiple_rejections(harness, count):
    root, client, args = harness
    for index in range(count):
        reject(harness, f"entry-{index}")
        client.now += timedelta(seconds=1)
    assert len(client.submits) == count
    client.mode = "accept"
    assert run(args, "final-entry").status == "order_complete"
    assert len(budget._load_binding(root)["qqq"]["orders"]) == count + 1


@pytest.mark.parametrize("tag", ["", "../bad", "bad tag", "a" * 81, "\uac00", True, 1])
def test_invalid_tag_is_rejected_before_any_io(harness, tag):
    root, client, args = harness
    with pytest.raises(ValueError, match="entry request identity"):
        run(args, tag)
    assert not root.exists() and not client.submits and not client.exact_reads


def test_tag_requires_qqq_owner_even_for_preview(harness):
    root, client, args = harness
    with pytest.raises(ValueError, match="entry request identity"):
        budget.run_kis_paper_budget_strategy(
            **(
                args
                | {
                    "qqq_cycle_id": None,
                    "qqq_entry_request_id": "entry",
                    "execute": False,
                }
            )
        )
    assert not root.exists() and not client.submits


@pytest.mark.parametrize("tag", ["A", "Entry._-09", "a" * 80])
def test_valid_tag_preview_has_no_io(harness, tag):
    root, client, args = harness
    result = budget.run_kis_paper_budget_strategy(
        **(
            args
            | {
                "qqq_entry_request_id": tag,
                "execute": False,
                "environment": {},
            }
        )
    )
    assert result.status == "preview" and not root.exists() and not client.submits


@pytest.mark.parametrize(
    "change",
    [
        "open",
        "reason",
        "category",
        "unknown",
        "not_started",
        "id",
        "wrong_side",
        "wrong_quantity",
        "wrong_ref",
        "missing_evidence",
        "changed_evidence",
        "invalid_evidence",
    ],
)
def test_rejection_helper_requires_positive_exact_closed_evidence(harness, change):
    root, _client, _args = harness
    binding = reject(harness)
    row = copy.deepcopy(binding["qqq"]["orders"][0])
    state = states(root, binding)[0]
    evidence = copy.deepcopy(binding["terminal_evidence"][row["run_id"]])
    if change == "open":
        row["closed"] = False
    elif change == "reason":
        state = replace(state, reason_code="submit_kis_rejected")
    elif change == "category":
        state = replace(state, submit_response_category="payload_invalid")
    elif change == "unknown":
        state = replace(state, phase="outcome_unknown")
    elif change == "not_started":
        state = replace(state, submission_started_at=None)
    elif change == "id":
        state = replace(state, broker_order_id="101")
    elif change == "wrong_side":
        state = replace(state, intent=replace(state.intent, side="sell"))
    elif change == "wrong_quantity":
        state = replace(state, intent=replace(state.intent, quantity=D(2)))
    elif change == "wrong_ref":
        row["intent_ref"] = "sha256:" + "0" * 64
    elif change == "missing_evidence":
        evidence = None
    elif change == "changed_evidence":
        evidence["state"]["updated_at"] = (state.updated_at + timedelta(seconds=1)).isoformat()
    else:
        evidence["state"]["schema_version"] = True
    assert not budget._qqq_rejected_entry(row, state, evidence)


@pytest.mark.parametrize("change", ["reason", "evidence_reason", "missing_evidence", "wrong_side"])
def test_nonpositive_history_cannot_append_a_new_buy(harness, change):
    root, client, args = harness
    binding = reject(harness)
    row = binding["qqq"]["orders"][0]
    state = states(root, binding)[0]
    if change == "reason":
        state = replace(state, reason_code="submit_kis_rejected")
        binding["terminal_evidence"][row["run_id"]]["state"] = state.to_dict()
    elif change == "evidence_reason":
        binding["terminal_evidence"][row["run_id"]]["state"]["reason_code"] = "submit_kis_rejected"
    elif change == "missing_evidence":
        del binding["terminal_evidence"][row["run_id"]]
    else:
        state = replace(state, intent=replace(state.intent, side="sell"))
        row["intent_ref"] = state.intent.fingerprint
        binding["terminal_evidence"][row["run_id"]]["state"] = state.to_dict()
    budget._atomic_json(root / (row["run_id"] + ".json"), state.to_dict())
    persist_binding(root, binding)
    client.now += timedelta(seconds=1)
    assert run(args, "entry-b").status in {"no_intent", "recovery_required"}
    assert len(client.submits) == 1 and len(client.exact_reads) == 2


def test_generic_category_stays_pending_and_recovery_never_selects_new_receipt(harness):
    root, client, args = harness
    client.mode = "raw_category"
    assert run(args).status == "pending"
    binding = budget._load_binding(root)
    assert states(root, binding)[0].phase == "outcome_unknown"
    client.mode = "accept"

    def forbidden_receipt(_at):
        pytest.fail("pending recovery must return before loading a new receipt")

    result = budget.run_kis_paper_budget_strategy(
        **(
            args
            | {
                "qqq_entry_request_id": "entry-b",
                "receipt_loader": forbidden_receipt,
            }
        )
    )
    assert result.status == "pending" and len(client.submits) == 1
    assert budget.project_budget(root, budget._load_binding(root)).reserved_buys == 600


def test_pending_entry_finishes_without_sell_in_same_visit(harness):
    root, client, args = harness
    reject(harness)
    client.now += timedelta(seconds=1)
    client.mode, client.fill_fraction = "accept", D(0)
    assert run(args, "entry-b").status == "pending"
    order = client.orders[client.submits[-1].run_id]
    order["filled"], order["remaining"] = D(1), D(0)
    client.now += timedelta(seconds=1)

    def forbidden_receipt(_at):
        pytest.fail("a recovered QQQ entry cannot select a SELL on the same visit")

    result = budget.run_kis_paper_budget_strategy(
        **(
            args
            | {
                "qqq_entry_request_id": "entry-b",
                "receipt_loader": forbidden_receipt,
            }
        )
    )
    assert result.status == "order_complete" and len(client.submits) == 2
    client.fill_fraction = D(1)
    assert run(args, "entry-b", action="exit").status == "order_complete"
    assert len(client.submits) == 3


@pytest.mark.parametrize("boundary", ["intent", "binding", "terminal"])
def test_persistence_crash_retains_history_and_recovers_exact_request(
    harness, monkeypatch, boundary
):
    root, client, args = harness
    before = reject(harness)
    client.now += timedelta(seconds=1)
    fixed_receipt = receipt(client.now, digit="b")
    opts = args | {"qqq_entry_request_id": "entry-b", "receipt_loader": lambda at: fixed_receipt}
    original_atomic = budget._atomic_json
    original_record = KisPaperCanaryStateStore.record_intent

    def crash_atomic(path, payload):
        if path == root / budget.BUDGET_FILE and len(payload["qqq"]["orders"]) == 2:
            if (
                boundary == "binding"
                or boundary == "terminal"
                and payload["qqq"]["orders"][-1]["closed"]
            ):
                raise OSError("synthetic persistence crash")
        return original_atomic(path, payload)

    def crash_intent(self, *args, **kwargs):
        original_record(self, *args, **kwargs)
        raise OSError("synthetic intent persistence crash")

    with monkeypatch.context() as patch:
        if boundary == "intent":
            patch.setattr(KisPaperCanaryStateStore, "record_intent", crash_intent)
        else:
            patch.setattr(budget, "_atomic_json", crash_atomic)
        assert budget.run_kis_paper_budget_strategy(**opts).status == "recovery_required"
    posts = len(client.submits)
    client.now += timedelta(seconds=1)

    def forbidden_receipt(_at):
        pytest.fail("Persisted request recovery must precede any refreshed receipt")

    assert (
        budget.run_kis_paper_budget_strategy(
            **(opts | {"receipt_loader": forbidden_receipt})
        ).reason_code
        == "order_not_submitted_or_rejected"
    )
    assert len(client.submits) == posts + (boundary != "terminal")
    binding = budget._load_binding(root)
    assert binding["qqq"]["orders"][:-1] == before["qqq"]["orders"]
    assert all(row["closed"] for row in binding["qqq"]["orders"])
    assert run(args, "entry-b", digit="c").reason_code == "decision_already_processed"


def stage_orphan(harness, monkeypatch, tag="orphan-entry"):
    root, client, args = harness
    original_receipt = receipt(client.now)
    original_record = KisPaperCanaryStateStore.record_intent

    def crash_after_intent(self, *values, **kwargs):
        original_record(self, *values, **kwargs)
        raise OSError("synthetic crash before budget reference")

    with monkeypatch.context() as patch:
        patch.setattr(KisPaperCanaryStateStore, "record_intent", crash_after_intent)
        assert run(args, tag).status == "recovery_required"
    run_id = "bq-" + budget._digest(
        ["unit-cycle", "entry-request-v1", tag]
        if tag is not None
        else ["unit-cycle", original_receipt.decision_id]
    )
    state = KisPaperCanaryStateStore(root / (run_id + ".json")).read()
    decision_path = (
        args["artifact_root"]
        / "execution"
        / "kis-paper-qqq-unit-cycle"
        / budget._digest("unit-cycle")
        / "decisions"
        / (original_receipt.decision_id.removeprefix("decision:sha256:") + ".json")
    )
    assert budget._read_json(decision_path) == original_receipt.to_payload()
    assert state.intent.decision_id == (
        "receipt-" + original_receipt.decision_id.removeprefix("decision:sha256:")
    )
    return state, decision_path


def test_untagged_orphan_recovers_original_default_identity_before_fresh_receipt(
    harness, monkeypatch
):
    root, client, args = harness
    state, path = stage_orphan(harness, monkeypatch, None)
    original_receipt = path.read_bytes()
    client.now += timedelta(seconds=1)

    def forbidden(_at):
        pytest.fail("Default orphan recovery must also precede any new receipt")

    result = budget.run_kis_paper_budget_strategy(**(args | {"receipt_loader": forbidden}))
    assert result.reason_code == "order_not_submitted_or_rejected"
    assert client.submits == [state.intent] and len(client.exact_reads) == 1
    assert path.read_bytes() == original_receipt
    assert len(budget._load_binding(root)["qqq"]["orders"]) == 1


@pytest.mark.parametrize("prefix", [0, 1, 3])
def test_orphan_recovery_preserves_original_receipt_price_ttl_and_history(
    harness, monkeypatch, prefix
):
    root, client, args = harness
    for index in range(prefix):
        reject(harness, f"prior-{index}")
        client.now += timedelta(seconds=1)
    state, decision_path = stage_orphan(harness, monkeypatch)
    original_receipt_bytes = decision_path.read_bytes()
    original_binding = budget._load_binding(root)
    original_state_bytes = (root / (state.intent.run_id + ".json")).read_bytes()
    client.now += timedelta(seconds=1)

    def forbidden(*args, **kwargs):
        pytest.fail("Orphan recovery must not refresh a receipt or quote")

    client.fetch_qqq_limit_input = forbidden
    result = budget.run_kis_paper_budget_strategy(
        **(
            args
            | {
                "qqq_entry_request_id": "orphan-entry",
                "receipt_loader": forbidden,
            }
        )
    )
    assert result.reason_code == "order_not_submitted_or_rejected"
    assert len(client.submits) == prefix + 1 and client.submits[-1] == state.intent
    binding = budget._load_binding(root)
    assert binding["qqq"]["orders"][:-1] == original_binding["qqq"]["orders"]
    assert binding["basis_ref"] == original_binding["basis_ref"]
    assert binding["qqq"]["owner_ref"] != original_binding["qqq"]["owner_ref"]
    assert decision_path.read_bytes() == original_receipt_bytes
    assert states(root, binding)[-1].intent.fingerprint == state.intent.fingerprint
    assert (root / (state.intent.run_id + ".json")).read_bytes() != original_state_bytes
    client.now += timedelta(seconds=1)
    assert run(args, "orphan-entry", digit="d").reason_code == "decision_already_processed"
    assert len(client.submits) == prefix + 1


@pytest.mark.parametrize("tag", [None, "distinct-entry"])
def test_unbound_orphan_cannot_be_bypassed_by_a_different_request(harness, monkeypatch, tag):
    root, client, args = harness
    _state, _path = stage_orphan(harness, monkeypatch)
    before = budget._load_binding(root)
    client.now += timedelta(seconds=1)
    assert run(args, tag, digit="b").reason_code == "orphan_intent_requires_reconciliation"
    assert not client.submits and budget._load_binding(root) == before


@pytest.mark.parametrize("change", ["missing", "tampered", "wrong_symbol", "extra_field"])
def test_orphan_receipt_custody_failure_never_uses_fresh_receipt(harness, monkeypatch, change):
    root, client, args = harness
    state, path = stage_orphan(harness, monkeypatch)
    before = budget._load_binding(root)
    if change == "missing":
        path.unlink()
    else:
        payload = budget._read_json(path)
        if change == "tampered":
            payload["proposal_ref"] = "ref:" + "b" * 32
        elif change == "wrong_symbol":
            payload = receipt(client.now, symbol="SPY").to_payload()
        else:
            payload["unexpected"] = True
        budget._atomic_json(path, payload)
    client.now += timedelta(seconds=1)
    assert run(args, "orphan-entry", digit="c").status == "recovery_required"
    assert not client.submits and budget._load_binding(root) == before
    assert KisPaperCanaryStateStore(root / (state.intent.run_id + ".json")).read() == state


def test_orphan_expiry_cannot_refresh_original_price_or_validity(harness, monkeypatch):
    root, client, args = harness
    state, path = stage_orphan(harness, monkeypatch)
    old_receipt = path.read_bytes()
    client.now = state.intent.valid_until
    result = run(args, "orphan-entry", digit="d")
    assert result.reason_code == "order_not_submitted_or_rejected" and not client.submits
    binding = budget._load_binding(root)
    assert binding["qqq"]["orders"][0]["closed"]
    assert states(root, binding)[0].intent == state.intent and path.read_bytes() == old_receipt
    assert run(args, "orphan-entry", digit="d").reason_code == "decision_already_processed"
    # A distinct tag may proceed without refreshing the original orphan.
    assert run(args, "distinct-entry", digit="d").reason_code == "order_not_submitted_or_rejected"
    assert len(client.submits) == 1
    assert states(root, budget._load_binding(root))[0].intent == state.intent
    assert path.read_bytes() == old_receipt


@pytest.mark.parametrize("change", ["started", "wrong_side", "wrong_symbol", "quantity"])
def test_orphan_with_possible_side_effect_or_wrong_identity_is_not_adopted(
    harness, monkeypatch, change
):
    root, client, args = harness
    state, _path = stage_orphan(harness, monkeypatch)
    payload = state.to_dict()
    if change == "started":
        payload["phase"] = "submission_started"
        payload["submission_started_at"] = client.now.isoformat()
    else:
        payload["intent"].update(
            {
                "wrong_side": {"side": "sell"},
                "wrong_symbol": {"symbol": "SPY", "exchange": "AMEX"},
                "quantity": {"quantity": "2"},
            }[change]
        )
    budget._atomic_json(root / (state.intent.run_id + ".json"), payload)
    before = budget._load_binding(root)
    assert run(args, "orphan-entry").status == "recovery_required"
    assert not client.submits and budget._load_binding(root) == before


def test_post_crash_cannot_repost_or_select_a_distinct_entry(harness):
    root, client, args = harness
    reject(harness)
    client.mode, client.crash = "accept", True
    client.now += timedelta(seconds=1)
    with pytest.raises(RuntimeError, match="post crash"):
        run(args, "entry-b")
    binding = budget._load_binding(root)
    assert states(root, binding)[-1].phase == "submission_started"
    client.crash = False
    assert run(args, "entry-c", digit="c").status == "pending"
    assert len(client.submits) == 2
    assert budget._load_binding(root)["qqq"]["orders"] == binding["qqq"]["orders"]


@pytest.mark.parametrize("kind", ["partial", "zero_cancel", "missing"])
def test_partial_cancelled_or_missing_entry_cannot_authorize_another_buy_or_sell(harness, kind):
    root, client, args = harness
    reject(harness)
    client.mode, client.fill_fraction = "accept", D(0)
    client.history_available = kind != "missing"
    client.now += timedelta(seconds=1)
    assert run(args, "entry-b").status == "pending"
    if kind == "partial":
        order = client.orders[client.submits[-1].run_id]
        order["filled"], order["remaining"] = D("0.5"), D(0)
        client.now += timedelta(seconds=1)
        assert run(args, "entry-b").status == "recovery_required"
    elif kind == "zero_cancel":
        client.now += timedelta(minutes=6)
        assert run(args, "entry-b").reason_code == "own_order_cancellation_observed"
        client.now += timedelta(seconds=1)
        assert run(args, "entry-b").status == "order_complete"
    assert run(args, "entry-c").status in {"no_intent", "pending", "recovery_required"}
    assert run(args, "entry-b", action="exit").status != "order_complete"
    assert len(client.submits) == 2
    binding = budget._load_binding(root)
    assert (
        budget._qqq_filled_entry(
            binding["qqq"]["orders"],
            states(root, binding),
            binding["terminal_evidence"],
        )
        is None
    )


@pytest.mark.parametrize("change", ["prefix_unknown", "duplicate_buy", "buy_after_fill"])
def test_filled_entry_helper_rejects_noncanonical_buy_history(harness, change):
    root, client, args = harness
    reject(harness)
    client.mode = "accept"
    client.now += timedelta(seconds=1)
    assert run(args, "entry-b").status == "order_complete"
    binding = budget._load_binding(root)
    rows, history = binding["qqq"]["orders"], states(root, binding)
    if change == "prefix_unknown":
        history[0] = replace(history[0], phase="outcome_unknown")
    else:
        index = 1 if change == "duplicate_buy" else 0
        rows.append(copy.deepcopy(rows[index]))
        history.append(history[index])
    assert budget._qqq_filled_entry(rows, history, binding["terminal_evidence"]) is None


def test_rejection_evidence_is_rechecked_at_submission_boundary(harness):
    root, client, args = harness
    before = reject(harness)
    client.now += timedelta(seconds=1)
    row = before["qqq"]["orders"][0]
    old = states(root, before)[0]
    prior_reads = len(client.exact_reads)

    def corrupt_previous_reason(cash, funds, count):
        if count == prior_reads + 2:
            changed = replace(old, reason_code="submit_kis_rejected")
            budget._atomic_json(root / (row["run_id"] + ".json"), changed.to_dict())
        return cash, funds

    client.exact_change = corrupt_previous_reason
    assert run(args, "entry-b").reason_code == "qqq_entry_history_not_rejected"
    assert len(client.submits) == 1


def test_same_tag_concurrent_visits_make_only_one_post(harness):
    _root, client, args = harness
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda digit: run(args, "entry-a", digit=digit), ("a", "b")))
    assert all(result.status == "no_intent" for result in results)
    assert len(client.submits) == 1


@pytest.mark.parametrize("change", ["owner", "alias", "cycle"])
def test_custody_collision_cannot_reset_or_submit(harness, change):
    root, client, args = harness
    binding = reject(harness)
    if change == "owner":
        binding["qqq"]["owner_ref"] = "sha256:" + "0" * 64
        budget._atomic_json(root / budget.BUDGET_FILE, binding)
    elif change == "alias":
        old = binding["qqq"]["orders"][0]
        alias = old | {"run_id": "bq-" + "0" * 64}
        binding["qqq"]["orders"].append(alias)
        state = states(root, binding | {"qqq": binding["qqq"] | {"orders": [old]}})[0]
        budget._atomic_json(root / (alias["run_id"] + ".json"), state.to_dict())
        binding["terminal_evidence"][alias["run_id"]] = binding["terminal_evidence"][old["run_id"]]
        persist_binding(root, binding)
    else:
        args = args | {"qqq_cycle_id": "new-owner"}
    assert run(args, "entry-b").status == "recovery_required"
    assert len(client.submits) == 1


def test_legacy_spy_unknown_and_pending_qqq_share_original_basis(harness):
    root, client, args = harness
    old = legacy_spy(root, client)
    reject(harness)
    client.mode, client.fill_fraction = "accept", D(0)
    client.now += timedelta(seconds=1)
    assert run(args, "entry-b").status == "pending"
    binding = budget._load_binding(root)
    projection = budget.project_budget(root, binding)
    assert projection.entry_cost == projection.reserved_buys == 600
    assert D(binding["allocated_usd"]) == 1800
    assert budget.run_kis_paper_budget_strategy(**spy_args(args)).reason_code == (
        "existing_inventory_or_order_conflict"
    )
    assert len(client.submits) == 2
    assert all(path.read_bytes() == original for path, original in old.items())


@pytest.mark.parametrize("change", ["symbol", "exchange", "price", "stale", "future", "currency"])
def test_exact_orderability_mismatch_has_no_post(harness, change):
    _root, client, args = harness

    def mutate(cash, funds, _count):
        fields = {
            "symbol": {"reference_symbol": "SPY"},
            "exchange": {"reference_exchange": "AMEX"},
            "price": {"reference_price": D(1)},
            "stale": {"captured_at": client.now - timedelta(seconds=121)},
            "future": {"captured_at": client.now + timedelta(seconds=6)},
            "currency": {"currency": "KRW"},
        }
        return cash, replace(funds, **fields[change])

    client.exact_change = mutate
    assert run(args).reason_code == "orderability_binding_mismatch"
    assert not client.submits


def test_exact_funds_shrink_before_post_prevents_submission(harness):
    root, client, args = harness

    def shrink(cash, funds, count):
        return cash, replace(funds, orderable_funds=D(599) if count == 2 else D(18000))

    client.exact_change = shrink
    assert run(args).reason_code == "buying_power_changed"
    assert not client.submits
    assert states(root, budget._load_binding(root))[0].phase == "intent_recorded"


@pytest.mark.parametrize("tag", [None, "entry-a", "different-entry"])
@pytest.mark.parametrize("failure", ["low", "unavailable", "wrong_price"])
def test_persisted_tagged_buy_always_rechecks_exact_funds_on_restart(harness, tag, failure):
    root, client, args = harness

    def shrink(cash, funds, count):
        return cash, replace(funds, orderable_funds=D(599) if count == 2 else D(18000))

    client.exact_change = shrink
    assert run(args).reason_code == "buying_power_changed"
    before = budget._load_binding(root)
    old_intent = states(root, before)[0].intent
    client.now += timedelta(seconds=1)

    def fail(cash, funds, _count):
        if failure == "unavailable":
            raise KisPaperReadOnlyError("orderable_funds_rejected")
        return cash, replace(
            funds,
            **({"orderable_funds": D(599)} if failure == "low" else {"reference_price": D(1)}),
        )

    client.exact_change = fail
    result = run(args, tag, digit="b")
    assert result.status == "recovery_required"
    assert len(client.exact_reads) == 3 and not client.submits
    assert budget._load_binding(root) == before
    assert states(root, before)[0].intent == old_intent


def test_unavailable_exact_funds_never_falls_back_to_generic_snapshot(harness):
    _root, client, args = harness

    def unavailable(**kwargs):
        raise KisPaperReadOnlyError("orderable_funds_rejected")

    client.orderable_funds_at_limit = unavailable
    assert run(args).status == "recovery_required"
    assert not client.submits


@pytest.mark.parametrize("source", ["exact", "cash", "shared_room"])
def test_all_three_funding_bounds_constrain_tagged_buy(harness, source):
    root, client, args = harness
    reject(harness, None)
    if source == "exact":
        client.exact_funds = D(599)
    elif source == "cash":
        client.funds = D(599)
    else:
        client.mode = "accept"
        client.spy_price = D(1800)
        assert budget.run_kis_paper_budget_strategy(**spy_args(args)).status == "order_complete"
    assert run(args, "entry-b").reason_code == "budget_below_one_share"
    assert len(client.submits) == (2 if source == "shared_room" else 1)
    assert D(budget._load_binding(root)["allocated_usd"]) == 1800
