"""H5 never-submitted closure on invented custody only, without forcing trades."""

import copy
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_kis_paper_weight_cycle as weights
import test_kis_paper_weight_h5_cycle as h5
import test_model_paper_profile as native
from test_model_paper_proposal import prepared as payoff_point
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.research.model_paper_weights import (
    ModelPaperWeightRow,
    prepare_model_paper_weights_input,
)

D = Decimal


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)


@pytest.fixture
def h(tmp_path):
    return native.h.__wrapped__(tmp_path)


def bind(h, count=5, profile=h5.H5, *, eligible=True):
    original = h5.point(profile)
    rows = tuple(
        ModelPaperWeightRow(
            i, f"SYN{chr(65 + i)}/{'NAS' if eligible else 'NYS'}", True, D(1) / count
        )
        for i in range(count)
    )
    meta = weights.metadata(rows, exit_not_before=original.metadata.exit_not_before)
    value = prepare_model_paper_weights_input(
        meta,
        entry_session=original.entry_session,
        exit_session=original.exit_session,
        profile=profile.value,
    )
    weights.bind(h, value, profile)


def expensive_quotes(h, monkeypatch):
    original = native.SyntheticClient.stock_preview_snapshot

    def preview(client, **kwargs):
        reads = original(client, **kwargs)
        price = D(100000)
        quote = cycle.KisPaperSpyLimitInput(price, 4, D(".0001"), client.h["now"], price, price)
        orderable = replace(reads.orderable, reference_price=price)
        return replace(
            reads,
            quote=quote,
            buy_limit=price,
            orderable=orderable,
            snapshot=replace(reads.snapshot, orderable_funds=orderable),
        )

    monkeypatch.setattr(native.SyntheticClient, "stock_preview_snapshot", preview)


def shared_bytes(h):
    book = cycle.budget._load_binding(h["root"])
    paths = [h["root"] / cycle.budget.BUDGET_FILE]
    paths.extend(
        h["root"] / (ref.run_id + ".json")
        for owner, _ in cycle.budget._owners(book)
        for ref in owner.state_refs
    )
    return {path: path.read_bytes() for path in paths}


@pytest.mark.parametrize("count", [1, 2, 5, 8])
def test_last_zero_quantity_skip_closes_in_same_entry_visit(h, monkeypatch, count):
    bind(h, count)
    expensive_quotes(h, monkeypatch)
    before = shared_bytes(h)
    for _ in range(count - 1):
        assert weights.run(h).status == "no_intent"
        assert weights.record(h)["active"] is not None
        assert weights.record(h)["completed"] == []
    result = weights.run(h)
    assert result.safe_payload() == dict(
        status="complete",
        reason="policy_no_order_complete",
        leg_count=0,
    )
    saved = weights.record(h)
    assert saved["active"] is None and saved["pending"] is None and saved["owners"] == {}
    assert saved["completed"] == [h["data"].input_ref]
    assert not h["submits"] and not h["cancels"] and h["factories"] == count
    assert shared_bytes(h) == before
    factories = h["factories"]
    assert weights.run(h, target_loader=h5.forbidden).reason == "already_completed"
    assert h["factories"] == factories and shared_bytes(h) == before


def test_zero_eligible_keeps_original_no_record_path(h):
    bind(h, 2, eligible=False)
    before = shared_bytes(h)
    assert weights.run(h).reason == "native_risk_no_intent"
    assert weights.record(h) is None and h["factories"] == 0 and not h["submits"]
    assert shared_bytes(h) == before


def test_h20_zero_quantity_behavior_is_unchanged(h, monkeypatch):
    bind(h, 2, h5.H20)
    expensive_quotes(h, monkeypatch)
    assert [row.status for row in weights.visit_all(h)] == ["no_intent", "no_intent", "hold"]
    assert weights.record(h)["active"] is not None and not weights.record(h)["completed"]
    assert not h["submits"]


def test_missing_quote_keeps_original_reason_without_zero_quantity_proof(h, monkeypatch):
    bind(h, 2)

    def unavailable(*args, **kwargs):
        raise cycle.KisPaperReadOnlyError("quote_timestamp_unavailable")

    monkeypatch.setattr(native.SyntheticClient, "stock_preview_snapshot", unavailable)
    before = shared_bytes(h)
    assert weights.run(h).reason == "cycle_target_quote_unavailable"
    assert weights.run(h).reason == "cycle_target_quote_unavailable"
    assert weights.record(h)["active"] is not None and not h["submits"]
    assert not weights.record(h)["completed"]
    assert shared_bytes(h) == before


def test_one_technical_skip_cannot_be_combined_with_zero_quantity_evidence(h, monkeypatch):
    bind(h, 2)
    expensive_quotes(h, monkeypatch)
    original = native.SyntheticClient.stock_preview_snapshot
    first = h["data"].targets[0].proposal.symbol

    def preview(client, **kwargs):
        if client.instrument.symbol == first:
            raise cycle.KisPaperReadOnlyError("quote_timestamp_unavailable")
        return original(client, **kwargs)

    monkeypatch.setattr(native.SyntheticClient, "stock_preview_snapshot", preview)
    assert weights.run(h).reason == "cycle_target_quote_unavailable"
    assert weights.run(h).status == "no_intent"
    assert weights.record(h)["active"] is not None and not weights.record(h)["completed"]
    assert first not in weights.record(h)["active"]["entry_no_order"]
    assert not h["submits"]


def test_native_whole_share_capacity_zero_is_a_distinct_admitted_sizing_result(h, monkeypatch):
    bind(h, 1)
    h["funds"] = D(1)
    original = cycle.entries.build_kis_paper_stock_plan
    reasons = []

    def build(**kwargs):
        plan = original(**kwargs)
        reasons.append(plan.reason)
        return plan

    monkeypatch.setattr(cycle.entries, "build_kis_paper_stock_plan", build)
    before = shared_bytes(h)
    assert weights.run(h).reason == "policy_no_order_complete"
    assert reasons == ["whole_share_capacity_zero"]
    assert not h["submits"] and shared_bytes(h) == before


def test_any_positive_owned_entry_prevents_no_order_closure(h, monkeypatch):
    bind(h)
    assert weights.run(h).status == "advanced"
    assert len(h["submits"]) == 1
    expensive_quotes(h, monkeypatch)
    assert weights.visit_all(h)[-1].status == "hold"
    assert weights.record(h)["active"] is not None
    assert not weights.record(h)["completed"] and len(h["submits"]) == 1


def test_unknown_pending_is_recovered_not_retired_as_empty(h):
    bind(h)
    h["unknown"] = True
    assert weights.run(h).status == "pending"
    before = weights.record(h)["pending"]
    bank = weights.bank_bytes(h)
    assert weights.run(h, target_loader=h5.forbidden).status == "pending"
    assert weights.record(h)["pending"]["arguments"] == before["arguments"]
    assert weights.record(h)["active"] is not None
    assert len(h["submits"]) == 1 and weights.bank_bytes(h) == bank


def test_partial_fill_with_unknown_cancel_is_not_a_no_order_completion(h):
    bind(h, 1)
    h["partial"] = True
    h["cancel_unknown"] = True
    assert weights.run(h).status == "pending"
    before = weights.record(h)["pending"]["arguments"]
    bank = weights.bank_bytes(h)
    assert weights.run(h, target_loader=h5.forbidden).status == "pending"
    saved = weights.record(h)
    assert saved["pending"]["arguments"] == before and saved["active"] is not None
    assert not saved["completed"] and len(h["submits"]) == 1
    assert weights.bank_bytes(h) == bank


@pytest.mark.parametrize("after_save", [False, True])
def test_terminal_atomic_store_failure_replays_without_new_order(h, monkeypatch, after_save):
    bind(h, 2)
    expensive_quotes(h, monkeypatch)
    assert weights.run(h).status == "no_intent"
    before = shared_bytes(h)
    save = cycle._save

    def crash(path, record):
        if path == weights.pointer(h) and record["active"] is None and record["completed"]:
            if after_save:
                save(path, record)
            raise OSError("invented_atomic_store_failure")
        return save(path, record)

    monkeypatch.setattr(cycle, "_save", crash)
    assert weights.run(h).status == "unavailable"
    assert shared_bytes(h) == before and not h["submits"]
    monkeypatch.setattr(cycle, "_save", save)
    factories = h["factories"]
    assert weights.run(h).status == "complete"
    assert h["factories"] == factories + (0 if after_save else 1)
    assert weights.record(h)["completed"] == [h["data"].input_ref]
    assert weights.record(h)["active"] is None and shared_bytes(h) == before


@pytest.mark.parametrize("fault", ["missing", "reason", "extra", "done_duplicate"])
def test_missing_or_ambiguous_skip_evidence_never_closes(h, monkeypatch, fault):
    bind(h, 2)
    expensive_quotes(h, monkeypatch)
    assert weights.run(h).status == "no_intent"
    saved = weights.record(h)
    active = saved["active"]
    first = h["data"].targets[0].proposal.symbol
    if fault == "missing":
        del active["entry_no_order"]
    elif fault == "reason":
        active["entry_no_order"][first] = "unknown"
    elif fault == "extra":
        active["entry_no_order"]["OTHER"] = "target_already_satisfied"
    else:
        active["entries_done"].append(first)
    cycle._save(weights.pointer(h), saved)
    before = shared_bytes(h)
    assert weights.run(h).status != "complete"
    assert weights.record(h)["active"] is not None
    assert not weights.record(h)["completed"] and not h["submits"]
    assert shared_bytes(h) == before


def test_unrelated_unknown_shared_reservation_is_preserved(h, monkeypatch):
    bind(h, 2)
    expensive_quotes(h, monkeypatch)
    book = cycle.budget._load_binding(h["root"])
    run_id = book["qqq"]["orders"][0]["run_id"]
    path = h["root"] / (run_id + ".json")
    state = cycle.canary.KisPaperCanaryStateStore(path).read()
    unknown = replace(
        state,
        phase="outcome_unknown",
        reason_code="submit_transport_unknown",
        submission_started_at=state.intent.created_at,
    )
    cycle.budget._atomic_json(path, unknown.to_dict())
    before = shared_bytes(h)
    assert weights.run(h).status == "no_intent"
    assert weights.run(h).reason == "policy_no_order_complete"
    assert shared_bytes(h) == before
    assert run_id not in cycle.budget._load_binding(h["root"])["terminal_evidence"]


def test_other_policy_positive_inventory_does_not_block_or_get_adopted(h, monkeypatch):
    other = payoff_point(selected=(6, 8, 9, 10, 11), policy=weights.OTHER, entry=date(2026, 10, 23))
    weights.bind(h, other, cycle.StockCycleProfile.MODEL_PROPOSAL_NAS)
    assert weights.visit_all(h)[-1].status == "hold"
    assert len(h["submits"]) == 1 and h["submits"][0].symbol == "NVDA"
    other_pointer = weights.pointer(h)
    other_bytes = other_pointer.read_bytes()
    bind(h, 2)
    expensive_quotes(h, monkeypatch)
    before = shared_bytes(h)
    assert weights.run(h).status == "no_intent"
    assert weights.run(h).reason == "policy_no_order_complete"
    assert other_pointer.read_bytes() == other_bytes and shared_bytes(h) == before
    assert len(h["submits"]) == 1 and weights.record(h)["owners"] == {}


def test_terminal_save_keeps_original_policy_and_shared_locks(h, monkeypatch):
    bind(h, 1)
    expensive_quotes(h, monkeypatch)
    original_lock = cycle.canary.exclusive_kis_paper_canary_state_lock
    original_save = cycle._save
    held = []
    terminal_saves = []

    @contextmanager
    def lock(path):
        with original_lock(path):
            held.append(path.name)
            try:
                yield
            finally:
                assert held.pop() == path.name

    def save(path, record):
        if record["active"] is None:
            assert {
                ".model_paper_nas_" + h["data"].policy_ref[7:],
                ".session_execution",
                ".canary_execution",
            } <= set(held)
            terminal_saves.append(record)
        return original_save(path, record)

    monkeypatch.setattr(cycle.canary, "exclusive_kis_paper_canary_state_lock", lock)
    monkeypatch.setattr(cycle, "_save", save)
    assert weights.run(h).reason == "policy_no_order_complete"
    assert len(terminal_saves) == 1 and held == []


def retained_skips(h, monkeypatch):
    bind(h, 2)
    expensive_quotes(h, monkeypatch)
    assert weights.run(h).status == "no_intent"
    with monkeypatch.context() as retain:
        retain.setattr(cycle, "_complete_h5_no_order", lambda *args: False)
        assert weights.run(h).status == "no_intent"
    saved = weights.record(h)
    assert saved["active"]["entries_done"] == [t.proposal.symbol for t in h["data"].targets]
    return saved


def prepared_plan(h):
    """Ask the unchanged pure producer for its exact native run ID, not a copied ID formula."""
    value = h["data"]
    target = value.targets[0]
    instrument = cycle.KisPaperStockInstrument(
        target.proposal.symbol, target.receipt.instrument_binding_ref
    )
    client = native.SyntheticClient(h, instrument)
    reads = legacy.NativeSyntheticStockClient.stock_preview_snapshot(
        client, expected_account_ref=h["call"]["expected_account_ref"], clock=lambda: h["now"]
    )
    book = cycle.budget._load_binding(h["root"])
    states = cycle._projection(h["root"], book, h["now"])[0]
    result = cycle.entries.build_kis_paper_stock_plan(
        binding=book,
        states=states,
        expected_account_ref=book["account_ref"],
        expected_basis_ref=book["basis_ref"],
        expected_owner_refs=cycle._refs(book),
        expected_binding_ref="sha256:" + cycle.budget._digest(book),
        request_id="model-"
        + cycle.budget._digest(
            [
                value.policy_ref,
                value.input_ref,
                instrument.binding_ref,
                "buy",
                0,
                value.entry_session.open_ts.isoformat(),
            ]
        ),
        input_ref=value.input_ref,
        instrument=instrument,
        proposal=target.proposal,
        receipt=target.receipt,
        reads=reads,
        as_of=h["now"],
        valid_until=min(target.proposal.valid_until, h["now"] + cycle.budget._ORDER_LIFETIME),
    )
    assert result.status == "prepared" and len(result.intents) == 1
    return result


def withhold(h, saved):
    before = weights.pointer(h).read_bytes()
    try:
        assert cycle._complete_h5_no_order(h["root"], saved, weights.pointer(h), h["now"]) is False
    except (cycle._CycleFault, cycle._RecoveryRequired, ValueError, KeyError):
        pass
    assert weights.pointer(h).read_bytes() == before
    assert weights.record(h)["active"] is not None and not weights.record(h)["completed"]


@pytest.mark.parametrize("kind", ["state_file", "state_directory", "lock_file", "lock_directory"])
def test_exact_native_orphan_blocks_completion(h, monkeypatch, kind):
    saved = retained_skips(h, monkeypatch)
    plan = prepared_plan(h)
    path = h["root"] / (plan.intents[0].run_id + ".json")
    if kind.startswith("lock"):
        path = path.with_name("." + path.name + ".lock")
    if kind.endswith("directory"):
        path.mkdir()
    else:
        path.write_bytes(b"invented_orphan_not_empty_evidence")
    before = weights.bank_bytes(h)
    withhold(h, saved)
    assert path.exists() and weights.bank_bytes(h) == before and not h["submits"]


@pytest.mark.parametrize("unknown", [False, True])
def test_untracked_current_cohort_canonical_plan_blocks_completion(h, monkeypatch, unknown):
    saved = retained_skips(h, monkeypatch)
    plan = prepared_plan(h)
    cycle.budget._atomic_json(h["root"] / cycle.budget.BUDGET_FILE, plan.binding)
    if unknown:
        intent = plan.intents[0]
        state = cycle.canary.KisPaperCanaryState(
            intent,
            "outcome_unknown",
            h["now"],
            "submit_transport_unknown",
            submission_started_at=h["now"],
        )
        cycle.budget._atomic_json(h["root"] / (intent.run_id + ".json"), state.to_dict())
    before = weights.bank_bytes(h)
    withhold(h, saved)
    assert weights.bank_bytes(h) == before and not h["submits"]


@pytest.mark.parametrize(
    "fault", ["profile", "input", "policy", "account", "basis", "missing_book"]
)
def test_changed_scope_cannot_terminalize_retained_skip_proof(h, monkeypatch, fault):
    saved = retained_skips(h, monkeypatch)
    if fault == "profile":
        saved["profile"] = h5.H20.value
    elif fault == "input":
        saved["active"]["input_ref"] = weights.OTHER
    elif fault == "policy":
        saved["policy_ref"] = weights.OTHER
    elif fault == "account":
        saved["account_ref"] = "f" * 64
    elif fault == "basis":
        saved["basis_ref"] = weights.OTHER
    else:
        monkeypatch.setattr(cycle.budget, "_load_binding", lambda *args: None)
    withhold(h, saved)
    assert not h["submits"]


def test_fresh_disk_version_change_is_not_overwritten(h, monkeypatch):
    saved = retained_skips(h, monkeypatch)
    newer = copy.deepcopy(saved)
    newer["active"]["entry_no_order"][h["data"].targets[0].proposal.symbol] = "unknown"
    cycle._save(weights.pointer(h), newer)
    before = weights.pointer(h).read_bytes()
    with pytest.raises(cycle._CycleFault, match="cycle_no_order_state_changed"):
        cycle._complete_h5_no_order(h["root"], saved, weights.pointer(h), h["now"])
    assert weights.pointer(h).read_bytes() == before and not h["submits"]


def test_completed_replay_with_later_orphan_withholds_without_client(h, monkeypatch):
    bind(h, 2)
    expensive_quotes(h, monkeypatch)
    assert weights.run(h).status == "no_intent"
    assert weights.run(h).reason == "policy_no_order_complete"
    plan = prepared_plan(h)
    path = h["root"] / (plan.intents[0].run_id + ".json")
    path.write_bytes(b"invented_late_contradiction")
    before = weights.pointer(h).read_bytes()
    factories = h["factories"]
    # Existing shared-book admission rejects an unbound native file before the new helper.
    result = weights.run(h, target_loader=h5.forbidden, client_factory=h5.forbidden)
    assert result.status == "unavailable" and result.reason == "native_recovery_required"
    assert h["factories"] == factories and weights.pointer(h).read_bytes() == before


@pytest.mark.parametrize(
    "fault", ["technical", "status", "binding", "intent", "plan", "reservation"]
)
def test_sizing_reason_alone_cannot_qualify_a_nonempty_or_technical_plan(h, monkeypatch, fault):
    bind(h, 1)
    changes = {
        "technical": {"reason": "quote_timestamp_stale"},
        "status": {"status": "unavailable"},
        "binding": {"binding": {}},
        "intent": {"intents": (None,)},
        "plan": {"plan_ref": weights.OTHER},
        "reservation": {"reservation": D(0)},
    }[fault]
    plan = replace(
        cycle.entries.KisPaperStockPlan("no_intent", "target_already_satisfied"), **changes
    )
    monkeypatch.setattr(cycle.entries, "build_kis_paper_stock_plan", lambda **kwargs: plan)
    before = shared_bytes(h)
    assert weights.run(h).status == "no_intent"
    assert weights.record(h)["active"] is not None and not weights.record(h)["completed"]
    assert not h["submits"] and shared_bytes(h) == before


def test_no_extra_client_calls_relative_to_unchanged_h20(h, tmp_path, monkeypatch):
    bind(h, 2)
    other = native.h.__wrapped__(tmp_path / "h20")
    bind(other, 2, h5.H20)
    expensive_quotes(h, monkeypatch)
    calls = []
    for name in (
        "snapshot",
        "stock_preview_snapshot",
        "orderable_funds_at_limit",
        "submit_limit",
        "reconcile",
        "cancel_order",
    ):
        original = getattr(native.SyntheticClient, name)

        def counted(client, *args, _name=name, _original=original, **kwargs):
            calls.append((id(client.h), _name))
            return _original(client, *args, **kwargs)

        monkeypatch.setattr(native.SyntheticClient, name, counted)
    for _ in range(2):
        result = weights.run(h)
        assert weights.run(other).status == "no_intent"
    assert result.reason == "policy_no_order_complete"
    assert [name for owner, name in calls if owner == id(h)] == [
        name for owner, name in calls if owner == id(other)
    ]
    assert not h["submits"] and not other["submits"]
