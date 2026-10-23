"""H5 terminal closure over invented native custody; never broker/account calls."""

import copy
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_kis_paper_weight_cycle as weights
import test_kis_paper_weight_h5_cycle as h5
import test_model_paper_profile as model_native
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
    result = model_native.h.__wrapped__(tmp_path)
    weights.bind(result, h5.point(), h5.H5)
    return result


def before_last_exit(h):
    assert weights.visit_all(h)[-1].status == "hold"
    buys = len(h["submits"])
    assert buys == 2
    h["now"] = h["data"].metadata.exit_not_before
    assert weights.run(h).status == "advanced"
    return buys


def test_last_exact_sell_completes_inside_original_visit(h):
    buys = before_last_exit(h)
    result = weights.run(h, target_loader=h5.forbidden)
    assert result.safe_payload() == {
        "status": "complete",
        "reason": "policy_owned_flat",
        "leg_count": 1,
    }
    saved = weights.record(h)
    assert saved["pending"] is None and saved["active"] is None
    assert saved["completed"] == [h["data"].input_ref]
    assert len(h["submits"]) == 2 * buys
    assert all(intent.side == "sell" for intent in h["submits"][buys:])


def test_h20_last_sell_still_requires_its_original_empty_visit(h):
    weights.bind(h, h5.point(h5.H20), h5.H20)
    before_last_exit(h)
    assert weights.run(h).safe_payload() == {
        "status": "advanced",
        "reason": "native_leg_closed",
        "leg_count": 1,
    }
    assert weights.record(h)["active"] is not None
    assert weights.run(h).status == "complete"
    saved = weights.record(h)
    assert saved["active"] is None and saved["pending"] is None
    assert saved["completed"] == [h["data"].input_ref]


def test_eight_owned_sells_need_no_ninth_native_visit(h, monkeypatch):
    original_preview = model_native.SyntheticClient.stock_preview_snapshot
    original_exit = model_native.SyntheticClient.stock_exit_snapshot

    def cheap_quote(at):
        return cycle.KisPaperSpyLimitInput(D(1), 4, D(".0001"), at, D(1), D(1))

    def preview(client, **kwargs):
        reads = original_preview(client, **kwargs)
        orderable = replace(reads.orderable, reference_price=D(1))
        return replace(
            reads,
            quote=cheap_quote(h["now"]),
            buy_limit=D(1),
            orderable=orderable,
            snapshot=replace(reads.snapshot, orderable_funds=orderable),
        )

    def exit_reads(client, **kwargs):
        return replace(original_exit(client, **kwargs), quote=cheap_quote(h["now"]))

    monkeypatch.setattr(model_native.SyntheticClient, "stock_preview_snapshot", preview)
    monkeypatch.setattr(model_native.SyntheticClient, "stock_exit_snapshot", exit_reads)
    original = h5.point()
    rows = tuple(ModelPaperWeightRow(i, f"SYN{chr(65 + i)}/NAS", True, D(".125")) for i in range(8))
    meta = weights.metadata(rows, exit_not_before=original.metadata.exit_not_before)
    value = prepare_model_paper_weights_input(
        meta,
        entry_session=original.entry_session,
        exit_session=original.exit_session,
        profile=h5.H5.value,
    )
    weights.bind(h, value, h5.H5)
    assert weights.visit_all(h)[-1].status == "hold"
    assert len(h["submits"]) == 8
    h["now"] = value.metadata.exit_not_before
    for index in range(8):
        result = weights.run(h, target_loader=h5.forbidden)
        assert result.status == ("complete" if index == 7 else "advanced")
        assert result.leg_count == 1
    assert len(h["submits"]) == 16
    assert weights.record(h)["active"] is None
    assert weights.record(h)["completed"] == [value.input_ref]
    assert weights.record(h)["pending"] is None


@pytest.mark.parametrize("after_save", [False, True])
def test_final_atomic_checkpoint_crash_replays_exact_request_once(h, monkeypatch, after_save):
    before_last_exit(h)
    original_save = cycle._save
    crashed = False

    def interrupted(path, value):
        nonlocal crashed
        if value["active"] is None and value["pending"] is None and not crashed:
            crashed = True
            if after_save:
                original_save(path, value)
            raise RuntimeError("invented_final_checkpoint_interrupt")
        original_save(path, value)

    with monkeypatch.context() as interrupt:
        interrupt.setattr(cycle, "_save", interrupted)
        assert weights.run(h).status == "unavailable"
    assert crashed and len(h["submits"]) == 4
    retained = weights.record(h)
    if not after_save:
        assert retained["pending"] is not None and retained["active"] is not None
        request = copy.deepcopy(retained["pending"]["arguments"])
        assert cycle._unpack(request)["request_id"].startswith("model-")
    else:
        assert retained["pending"] is None and retained["active"] is None
    bank = weights.bank_bytes(h)
    result = weights.run(h, target_loader=h5.forbidden)
    assert result.status == "complete"
    assert len(h["submits"]) == 4 and h["cancels"] == []
    assert weights.bank_bytes(h) == bank
    assert weights.record(h)["completed"] == [h["data"].input_ref]
    for _ in range(2):
        assert weights.run(h, target_loader=h5.forbidden, client_factory=h5.forbidden).reason == (
            "already_completed"
        )
    assert weights.record(h)["completed"] == [h["data"].input_ref]


def test_terminal_copy_is_saved_under_both_existing_shared_locks(h, monkeypatch):
    before_last_exit(h)
    original_shared, original_save = cycle._shared, cycle._save
    original_complete = cycle._complete_h5_exit
    original_lock = cycle.canary.exclusive_kis_paper_canary_state_lock
    depth, original_record, final_saves = 0, None, 0
    held = []

    @contextmanager
    def tracked_lock(path):
        with original_lock(path):
            held.append(path.name)
            try:
                yield
            finally:
                assert held.pop() == path.name

    @contextmanager
    def tracked_shared(root):
        nonlocal depth
        with original_shared(root):
            depth += 1
            try:
                yield
            finally:
                depth -= 1

    def capture_record(root, record, *args):
        nonlocal original_record
        original_record = record
        return original_complete(root, record, *args)

    def checked_save(path, value):
        nonlocal final_saves
        if value["active"] is None:
            if final_saves == 0:
                assert depth == 1 and original_record is not value
                assert original_record["active"] is not None
                assert original_record["pending"] is not None
                assert {
                    ".model_paper_nas_" + h["data"].policy_ref[7:],
                    ".session_execution",
                    ".canary_execution",
                } <= set(held)
            final_saves += 1
        original_save(path, value)

    monkeypatch.setattr(cycle, "_shared", tracked_shared)
    monkeypatch.setattr(cycle.canary, "exclusive_kis_paper_canary_state_lock", tracked_lock)
    monkeypatch.setattr(cycle, "_complete_h5_exit", capture_record)
    monkeypatch.setattr(cycle, "_save", checked_save)
    assert weights.run(h).status == "complete"
    assert final_saves == 1 and depth == 0
    assert held == []


@pytest.mark.parametrize("fault", ["unknown", "foreign", "missing_execution", "unbound_fill"])
def test_unproved_last_sell_never_becomes_terminal(h, monkeypatch, fault):
    before_last_exit(h)
    if fault in {"unknown", "foreign"}:
        h[fault] = True
    else:
        original = model_native.SyntheticClient.reconcile

        def incomplete(client, state, **kwargs):
            result = original(client, state, **kwargs)
            if result.execution is None:
                return result
            if fault == "missing_execution":
                return replace(result, execution=None)
            fill = replace(result.execution.fill, identity_ref="sha256:" + "8" * 64)
            return replace(result, execution=replace(result.execution, fill=fill))

        monkeypatch.setattr(model_native.SyntheticClient, "reconcile", incomplete)
    result = weights.run(h, target_loader=h5.forbidden)
    assert result.status != "complete"
    saved = weights.record(h)
    assert saved["active"] is not None and saved["completed"] == []
    if fault == "unknown":
        assert saved["pending"] is not None
        pending, bank, count = (
            copy.deepcopy(saved["pending"]),
            weights.bank_bytes(h),
            len(h["submits"]),
        )
        assert weights.run(h).status == "pending"
        assert weights.record(h)["pending"] == pending and weights.bank_bytes(h) == bank
        assert len(h["submits"]) == count


def retained_flat_pending(h, monkeypatch):
    before_last_exit(h)
    captured = []

    def retain(root, record, pointer, proof, at):
        captured.append((copy.deepcopy(record), proof, at))
        return False

    with monkeypatch.context() as old_behavior:
        old_behavior.setattr(cycle, "_complete_h5_exit", retain)
        assert weights.run(h).status == "advanced"
    assert len(captured) == 1
    return captured[0]


def test_partial_omission_cannot_hide_another_positive_owned_target(h, monkeypatch):
    assert weights.visit_all(h)[-1].status == "hold"
    h["now"] = h["data"].metadata.exit_not_before
    captured = []

    def retain(root, record, pointer, proof, at):
        captured.append((copy.deepcopy(record), proof, at))
        return False

    with monkeypatch.context() as capture:
        capture.setattr(cycle, "_complete_h5_exit", retain)
        assert weights.run(h).status == "advanced"
    record, proof, at = captured[0]
    remaining = next(symbol for symbol in record["owners"] if symbol != proof.instrument.symbol)
    binding = cycle.budget._load_binding(h["root"])
    projection = cycle._projection(h["root"], binding, at)[3]
    assert any(row.symbol == remaining and row.quantity > 0 for row in projection.stocks_by_owner)
    del record["owners"][remaining]
    before = weights.pointer(h).read_bytes()
    with pytest.raises(cycle._CycleFault, match="cycle_owner_missing"):
        cycle._complete_h5_exit(h["root"], record, weights.pointer(h), proof, at)
    assert weights.pointer(h).read_bytes() == before
    assert record["active"] is not None and record["pending"] is not None


@pytest.mark.parametrize(
    "fault",
    ["account", "basis", "input", "policy", "profile", "request", "plan", "owners"],
)
def test_exact_closure_rejects_changed_scope_before_publishing(h, monkeypatch, fault):
    record, proof, at = retained_flat_pending(h, monkeypatch)
    before = weights.pointer(h).read_bytes()
    if fault in {"account", "basis", "policy"}:
        record[fault + "_ref"] = weights.OTHER
    elif fault == "input":
        record["active"]["input_ref"] = weights.OTHER
    elif fault == "profile":
        record["profile"] = h5.H20.value
    elif fault == "request":
        record["pending"]["arguments"]["request_id"] = "model-invented-unbound"
    elif fault == "plan":
        record["pending"]["plan_ref"] = weights.OTHER
    else:
        record["owners"] = {}
    with pytest.raises((cycle._CycleFault, cycle._RecoveryRequired, ValueError, KeyError)):
        cycle._complete_h5_exit(h["root"], record, weights.pointer(h), proof, at)
    assert weights.pointer(h).read_bytes() == before
    assert record["active"] is not None and record["pending"] is not None


@pytest.mark.parametrize(
    "fault",
    ["missing_terminal", "missing_owner", "missing_state", "missing_row", "nonterminal_state"],
)
def test_flat_projection_is_not_sufficient_without_exact_owned_evidence(h, monkeypatch, fault):
    record, proof, at = retained_flat_pending(h, monkeypatch)
    before = weights.pointer(h).read_bytes()
    original_book, original_projection, original_owners = (
        cycle._book,
        cycle._projection,
        cycle.budget._owners,
    )
    if fault == "missing_terminal":

        def missing_book(*args):
            result = copy.deepcopy(original_book(*args))
            del result["terminal_evidence"][proof.run_id]
            return result

        monkeypatch.setattr(cycle, "_book", missing_book)
    elif fault == "missing_owner":
        monkeypatch.setattr(
            cycle.budget,
            "_owners",
            lambda binding: [
                (owner, ref)
                for owner, ref in original_owners(binding)
                if owner.owner_ref != cycle.budget._stock_owner_id(proof.instrument.binding_ref)
            ],
        )
    else:

        def incomplete_projection(*args):
            states, replayed, proofs, projection = original_projection(*args)
            if fault == "missing_state":
                del replayed[proof.run_id]
            elif fault == "nonterminal_state":
                replayed[proof.run_id] = cycle.budget._stock_seed_states(args[1])[proof.run_id]
            else:
                projection = replace(projection, stocks_by_owner=())
            return states, replayed, proofs, projection

        monkeypatch.setattr(cycle, "_projection", incomplete_projection)
    try:
        assert cycle._complete_h5_exit(h["root"], record, weights.pointer(h), proof, at) is False
    except (cycle._CycleFault, cycle._RecoveryRequired, ValueError, KeyError):
        pass
    assert weights.pointer(h).read_bytes() == before
    assert record["pending"] is not None and record["completed"] == []


def test_unrelated_shared_unknown_reservation_is_held(h):
    binding = cycle.budget._load_binding(h["root"])
    shared_run = binding["qqq"]["orders"][0]["run_id"]
    shared_path = h["root"] / (shared_run + ".json")
    shared = cycle.canary.KisPaperCanaryStateStore(shared_path).read()
    unknown = replace(
        shared,
        phase="outcome_unknown",
        reason_code="submit_transport_unknown",
        submission_started_at=shared.intent.created_at,
    )
    cycle.budget._atomic_json(shared_path, unknown.to_dict())
    before_last_exit(h)
    before = cycle.budget._load_binding(h["root"])
    shared_state_paths = [
        h["root"] / (ref.run_id + ".json")
        for owner, _ in cycle.budget._owners(before)
        if not owner.owner_ref.startswith("stock-")
        for ref in owner.state_refs
    ]
    shared_bytes = {path: path.read_bytes() for path in shared_state_paths}
    assert shared_path in shared_bytes and shared_run not in before["terminal_evidence"]
    assert weights.run(h).status == "complete"
    after = cycle.budget._load_binding(h["root"])
    for key in ("account_ref", "basis_ref", "allocated_usd", "orders", "qqq", "portfolio"):
        assert after[key] == before[key] == h["initial"][key]
    assert shared_run not in after["terminal_evidence"]
    assert {path: path.read_bytes() for path in shared_state_paths} == shared_bytes
    assert cycle.canary.KisPaperCanaryStateStore(shared_path).read() == unknown


def test_other_policy_positive_stock_is_neither_adopted_nor_closed(h):
    current = h["data"]
    other = payoff_point(selected=(6, 8, 9, 10, 11), policy=weights.OTHER, entry=date(2026, 10, 23))
    weights.bind(h, other, cycle.StockCycleProfile.MODEL_PROPOSAL_NAS)
    assert weights.visit_all(h)[-1].status == "hold"
    assert len(h["submits"]) == 1 and h["submits"][0].symbol == "NVDA"
    other_pointer = weights.pointer(h)
    other_bytes = other_pointer.read_bytes()
    other_entry = copy.deepcopy(cycle.budget._load_binding(h["root"])["stocks"]["NVDA"])
    other_state_path = h["root"] / (h["submits"][0].run_id + ".json")
    other_state = other_state_path.read_bytes()
    weights.bind(h, current, h5.H5)
    assert weights.visit_all(h)[-1].status == "hold"
    h["now"] = current.metadata.exit_not_before
    assert weights.run(h).status == "advanced"
    assert weights.run(h).status == "complete"
    assert len(h["submits"]) == 5
    assert "NVDA" not in weights.record(h)["owners"]
    assert other_pointer.read_bytes() == other_bytes
    assert other_state_path.read_bytes() == other_state
    binding = cycle.budget._load_binding(h["root"])
    assert binding["stocks"]["NVDA"] == other_entry
    projection = cycle._projection(h["root"], binding, h["now"])[3]
    assert any(row.symbol == "NVDA" and row.quantity > 0 for row in projection.stocks_by_owner)


def test_no_extra_native_read_or_effect_relative_to_original_h20(h, tmp_path, monkeypatch):
    other = model_native.h.__wrapped__(tmp_path / "h20")
    weights.bind(other, h5.point(h5.H20), h5.H20)
    before_last_exit(h)
    before_last_exit(other)
    calls = []
    for name in (
        "stock_exit_snapshot",
        "reconcile",
        "submit_limit",
        "cancel_order",
        "orderable_funds_at_limit",
    ):
        original = getattr(model_native.SyntheticClient, name)

        def counted(client, *args, _name=name, _original=original, **kwargs):
            calls.append((id(client.h), _name))
            return _original(client, *args, **kwargs)

        monkeypatch.setattr(model_native.SyntheticClient, name, counted)
    assert weights.run(h).status == "complete"
    assert weights.run(other).status == "advanced"
    h5_calls = [name for owner, name in calls if owner == id(h)]
    h20_calls = [name for owner, name in calls if owner == id(other)]
    assert h5_calls == h20_calls
    assert h5_calls.count("submit_limit") == 1 and "cancel_order" not in h5_calls
    assert "orderable_funds_at_limit" not in h5_calls
