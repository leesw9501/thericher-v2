"""Synthetic canonical reservation/recovery; no actual private or provider IO."""

from __future__ import annotations

import builtins
import copy
import json
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import ROUND_UP, Decimal, localcontext
from pathlib import Path

import pytest

from test_kis_paper_portfolio_preview import _scope, _state
from test_kis_paper_stock_plan import AT, REFS
from test_kis_paper_stock_plan import _arguments as _sizing_arguments
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.execution import kis_paper_stock_plan as stock
from thericher_v2.execution import kis_readonly
from thericher_v2.execution.kis_paper_canary import (
    KisPaperCanaryClient,
    KisPaperCanaryState,
)
from thericher_v2.execution.kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from thericher_v2.execution.kis_paper_spy_fill_cycle import _RecoveryRequired
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.research.decision_receipt import receipt_from_target_exposure_proposal

D = Decimal


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("synthetic_plan_cannot_use_provider_or_credentials")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(KisPaperCanaryClient, "submit_limit", deny)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(budget, "load_kis_paper_config_from_environment", deny)


def _refs(binding):
    return {owner.owner_ref: ref for owner, ref in budget._owners(binding)}


def _arguments(*states, **sizing):
    typed = _sizing_arguments(**sizing)
    args = _scope(*states)
    binding = args["binding"]
    binding.update(
        version=3, portfolio={"owner_refs": dict.fromkeys(("SPY", "TLT", "GLD")), "plans": []}
    )
    for owner, _ in budget._owners(binding):
        if owner.owner_ref.startswith("portfolio-"):
            binding["portfolio"]["owner_refs"][owner.symbol] = owner.fingerprint
    return dict(
        binding=binding,
        states=args["states"],
        expected_account_ref=args["expected_account_ref"],
        expected_basis_ref=binding["basis_ref"],
        expected_owner_refs=_refs(binding),
        expected_binding_ref="sha256:" + budget._digest(binding),
        request_id="synthetic-stock-1",
        input_ref="sha256:" + "d" * 64,
        **{key: typed[key] for key in ("instrument", "proposal", "receipt", "reads")},
        as_of=AT,
        valid_until=AT + timedelta(minutes=5),
    )


def _retained(args, result, *, original_refs=False):
    return args | dict(
        binding=result.binding,
        states=dict(args["states"]) | budget._stock_seed_states(result.binding),
        expected_owner_refs=args["expected_owner_refs"] if original_refs else _refs(result.binding),
    )


def _persist(tmp_path, args):
    root = tmp_path / "p"
    root.mkdir()
    budget._atomic_json(root / budget.BUDGET_FILE, args["binding"])
    for run, state in args["states"].items():
        budget._atomic_json(root / (run + ".json"), state.to_dict())
    return dict(
        state_root=root,
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "artifacts",
        **{key: value for key, value in args.items() if key not in {"binding", "states"}},
    )


def _reconcile(io, result, **changes):
    allowed = {
        "state_root",
        "repository_root",
        "artifact_root",
        "expected_account_ref",
        "expected_basis_ref",
        "expected_binding_ref",
        "input_ref",
        "instrument",
        "request_id",
    }
    return dict(
        **{key: value for key, value in io.items() if key in allowed},
        expected_owner_refs=_refs(result.binding),
        expected_plan_ref=result.plan_ref,
        as_of=AT + timedelta(minutes=6),
        **changes,
    )


def _observed(intent, *, filled="0", phase="submitted", unavailable=False, remaining=None):
    started = intent.created_at + timedelta(seconds=1)
    observed = started + timedelta(seconds=1)
    fill = KisPaperCumulativeFill(
        fill_identity_ref(
            raw_order_id="SYNTHETIC-ORDER",
            order_at=started,
            symbol=intent.symbol,
            exchange=intent.exchange,
            side="buy",
            quantity=intent.quantity,
        ),
        intent.quantity,
        D(filled),
        D(filled) * intent.limit_price,
        observed,
        intent.quantity - D(filled) if remaining is None else D(remaining),
    )
    return KisPaperCanaryState(
        intent,
        phase,
        observed + timedelta(seconds=1),
        "reconciliation_unresolved",
        broker_order_id="SYNTHETIC-ORDER",
        submission_started_at=started,
        submitted_at=started,
        cumulative_fill=fill,
        fill_observation_status="unavailable" if unavailable else "available",
        fill_observed_at=observed + timedelta(seconds=1) if unavailable else observed,
    )


def test_pure_builder_v3_to_v4_preserves_every_existing_owner_and_original_bank(monkeypatch):
    args = _arguments()
    before = copy.deepcopy(args)
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", lambda *a, **k: pytest.fail("pure_builder_io"))
        patch.setattr(Path, "read_bytes", lambda *a, **k: pytest.fail("pure_builder_io"))
        result = stock.build_kis_paper_stock_plan(**args)
    assert args == before and result.status == "prepared"
    assert result.binding["version"] == 4
    assert {
        key: value for key, value in result.binding.items() if key not in {"stocks", "version"}
    } == {key: value for key, value in args["binding"].items() if key != "version"}
    assert result.binding["basis_usd"] == "10000" and result.binding["allocated_usd"] == "1000"
    assert _refs(result.binding).items() >= args["expected_owner_refs"].items()
    (intent,) = result.intents
    assert (intent.quantity, intent.limit_price, intent.created_at, intent.valid_until) == (
        D(10),
        D(10),
        AT,
        args["valid_until"],
    )
    identity = budget._stock_identity(result.binding, intent.symbol, args["request_id"], "buy")
    assert intent.run_id == "bk-" + identity
    assert intent.client_order_id == intent.decision_id == "stock-" + identity
    assert result.reservation == 100
    assert result.plan_ref == "sha256:" + budget._digest(
        result.binding["stocks"][intent.symbol]["plans"][0]
    )
    projection = budget.project_shared_budget(
        **{key: args[key] for key in ("expected_account_ref", "expected_basis_ref", "as_of")},
        binding=result.binding,
        states=budget._stock_seed_states(result.binding),
        expected_owner_refs=_refs(result.binding),
    )
    assert projection.reserved_buys == 100 and projection.remaining_cap == 900


@pytest.mark.parametrize("original_refs", [True, False])
def test_exact_retry_after_expiry_never_uses_new_quote_proposal_or_ttl(original_refs):
    args = _arguments()
    first = stock.build_kis_paper_stock_plan(**args)
    retry = _retained(args, first, original_refs=original_refs)
    retry.update(
        as_of=AT + timedelta(days=1),
        valid_until=AT + timedelta(days=2),
        proposal=None,
        receipt=None,
        reads=None,
    )
    result = stock.build_kis_paper_stock_plan(**retry)
    assert result.status == "replayed"
    assert result.intents == first.intents and result.plan_ref == first.plan_ref
    assert result.binding == first.binding and result.reservation == first.reservation


def test_retry_after_later_trio_change_requires_current_pins_but_keeps_original_parent():
    args = _arguments()
    first = stock.build_kis_paper_stock_plan(**args)
    retry = _retained(args, first)
    # A separate current-book fact changes the complete binding hash, not this request.
    retry["binding"] = copy.deepcopy(retry["binding"])
    retry["binding"]["qqq"]["cycle_id"] = "synthetic-new-unattempted-qqq"
    retry["binding"]["qqq"]["owner_ref"] = budget._owners(retry["binding"])[1][0].fingerprint
    retry["expected_owner_refs"] = _refs(retry["binding"])
    result = stock.build_kis_paper_stock_plan(**retry)
    assert result.status == "replayed" and result.intents == first.intents
    assert result.plan_ref == first.plan_ref
    retry["expected_owner_refs"] = args["expected_owner_refs"]
    with pytest.raises(_RecoveryRequired):
        stock.build_kis_paper_stock_plan(**retry)


@pytest.mark.parametrize(
    "field",
    [
        "expected_account_ref",
        "expected_basis_ref",
        "expected_owner_refs",
        "expected_binding_ref",
        "input_ref",
        "instrument",
    ],
)
def test_exact_retry_rejects_wrong_external_scope(field):
    args = _arguments()
    first = stock.build_kis_paper_stock_plan(**args)
    retry = _retained(args, first)
    retry[field] = (
        {}
        if field == "expected_owner_refs"
        else KisPaperStockInstrument(args["instrument"].symbol, "ref:" + "f" * 64)
        if field == "instrument"
        else "f" * 64
        if field == "expected_account_ref"
        else "sha256:" + "f" * 64
    )
    with pytest.raises(_RecoveryRequired):
        stock.build_kis_paper_stock_plan(**retry)


@pytest.mark.parametrize("minutes", [0, -1, 6])
def test_new_plan_cannot_extend_order_lifetime(minutes):
    args = _arguments()
    args["valid_until"] = AT + timedelta(minutes=minutes)
    with pytest.raises(_RecoveryRequired, match="stock_validity_invalid"):
        stock.build_kis_paper_stock_plan(**args)


def test_original_proposal_expiry_is_stricter_than_order_lifetime():
    args = _arguments()
    args["proposal"] = replace(args["proposal"], valid_until=AT + timedelta(seconds=30))
    args["receipt"] = receipt_from_target_exposure_proposal(args["proposal"], references=REFS)
    with pytest.raises(_RecoveryRequired, match="stock_validity_invalid"):
        stock.build_kis_paper_stock_plan(**args)
    args["valid_until"] = args["proposal"].valid_until
    assert (
        stock.build_kis_paper_stock_plan(**args).intents[0].valid_until
        == args["proposal"].valid_until
    )


@pytest.mark.parametrize("kind", ["expired", "no_funds", "foreign_position", "wrong_funds"])
def test_no_intent_does_not_create_owner_or_reservation(tmp_path, kind):
    args = _arguments(
        funds="0" if kind == "no_funds" else "1000",
        broker_quantity="1" if kind == "foreign_position" else None,
    )
    if kind == "expired":
        args["as_of"] = args["proposal"].valid_until
    if kind == "wrong_funds":
        args["reads"] = replace(
            args["reads"], orderable=replace(args["reads"].orderable, reference_symbol="QQQ")
        )
    io = _persist(tmp_path, args)
    before = (io["state_root"] / budget.BUDGET_FILE).read_bytes()
    result = stock.reserve_kis_paper_stock_plan(**io)
    assert result.status == "no_intent" and result.binding is None
    assert (io["state_root"] / budget.BUDGET_FILE).read_bytes() == before
    assert not list(io["state_root"].glob("bk-*.json"))


def test_reservation_is_durable_without_materializing_order_file_and_restart_is_identical(tmp_path):
    args = _arguments()
    io = _persist(tmp_path, args)
    result = stock.reserve_kis_paper_stock_plan(**io)
    assert result.status == "reserved"
    assert not list(io["state_root"].glob("bk-*.json"))
    assert budget._load_binding(io["state_root"]) == result.binding
    before = (io["state_root"] / budget.BUDGET_FILE).read_bytes()
    restarted = stock.reserve_kis_paper_stock_plan(
        **(io | dict(as_of=AT + timedelta(days=1), proposal=None, receipt=None, reads=None))
    )
    assert restarted.status == "replayed" and restarted.intents == result.intents
    assert (io["state_root"] / budget.BUDGET_FILE).read_bytes() == before


def test_two_competing_exact_reservations_create_only_one_seed(tmp_path):
    io = _persist(tmp_path, _arguments())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: stock.reserve_kis_paper_stock_plan(**io), range(2)))
    assert sorted(r.status for r in results) == ["replayed", "reserved"]
    assert results[0].intents == results[1].intents
    binding = budget._load_binding(io["state_root"])
    assert len(budget._stock_seed_states(binding)) == 1


def test_materialized_state_missing_cannot_fall_back_to_seed(tmp_path):
    io = _persist(tmp_path, _arguments())
    result = stock.reserve_kis_paper_stock_plan(**io)
    run = result.intents[0].run_id
    (io["state_root"] / ("." + run + ".json.lock")).touch()
    with pytest.raises(_RecoveryRequired, match="portfolio_materialized_state_missing"):
        stock.reserve_kis_paper_stock_plan(**io)


@pytest.mark.parametrize("phase", ["submission_started", "outcome_unknown", "submitted"])
def test_unknown_or_unfilled_after_expiry_never_releases(tmp_path, phase):
    io = _persist(tmp_path, _arguments())
    result = stock.reserve_kis_paper_stock_plan(**io)
    state = _observed(result.intents[0], phase=phase)
    if phase != "submitted":
        state = replace(
            state,
            broker_order_id=None,
            submitted_at=None,
            cumulative_fill=None,
            fill_observation_status="not_observed",
            fill_observed_at=None,
        )
    budget._atomic_json(io["state_root"] / (state.intent.run_id + ".json"), state.to_dict())
    reconciled = stock.reconcile_kis_paper_stock_plan(**_reconcile(io, result))
    assert reconciled.status == "pending" and not reconciled.binding["terminal_evidence"]
    assert (
        budget.project_budget(
            io["state_root"],
            reconciled.binding,
            as_of=AT + timedelta(minutes=6),
            stock_symbol=state.intent.symbol,
        ).reserved_buys
        == 100
    )


@pytest.mark.parametrize(
    "filled,unavailable", [("3", False), ("3", True), ("10", False), ("10", True)]
)
def test_cumulative_fill_preserved_with_later_unavailable(tmp_path, filled, unavailable):
    io = _persist(tmp_path, _arguments())
    result = stock.reserve_kis_paper_stock_plan(**io)
    state = _observed(result.intents[0], filled=filled, unavailable=unavailable)
    budget._atomic_json(io["state_root"] / (state.intent.run_id + ".json"), state.to_dict())
    reconciled = stock.reconcile_kis_paper_stock_plan(**_reconcile(io, result))
    assert reconciled.status == ("reconciled" if filled == "10" else "pending")
    projection = budget.project_budget(
        io["state_root"],
        reconciled.binding,
        as_of=AT + timedelta(minutes=6),
        stock_symbol=state.intent.symbol,
    )
    assert projection.quantity == D(filled) and projection.entry_cost == D(filled) * 10
    assert projection.reserved_buys == (10 - D(filled)) * 10
    before = (io["state_root"] / budget.BUDGET_FILE).read_bytes()
    again = stock.reconcile_kis_paper_stock_plan(**_reconcile(io, reconciled))
    assert again == reconciled and (io["state_root"] / budget.BUDGET_FILE).read_bytes() == before


@pytest.mark.parametrize("kind", ["expired", "provider_rejected"])
def test_proven_no_wire_expiry_or_positive_rejection_closes_only_exact_request(tmp_path, kind):
    io = _persist(tmp_path, _arguments())
    result = stock.reserve_kis_paper_stock_plan(**io)
    intent = result.intents[0]
    state = KisPaperCanaryState(intent, "intent_recorded", intent.valid_until, "intent_expired")
    if kind == "provider_rejected":
        state = replace(
            state,
            phase="rejected",
            reason_code="submit_rejected",
            submission_started_at=AT + timedelta(seconds=1),
            submit_response_category="provider_rejected",
        )
    budget._atomic_json(io["state_root"] / (intent.run_id + ".json"), state.to_dict())
    reconciled = stock.reconcile_kis_paper_stock_plan(**_reconcile(io, result))
    assert reconciled.status == "reconciled"
    assert reconciled.binding["stocks"] == result.binding["stocks"]
    assert reconciled.binding["basis_ref"] == result.binding["basis_ref"]
    projection = budget.project_budget(
        io["state_root"],
        reconciled.binding,
        as_of=AT + timedelta(minutes=6),
        stock_symbol=intent.symbol,
    )
    assert projection.quantity == projection.entry_cost == projection.reserved_buys == 0


def test_unmaterialized_expired_seed_requires_persisted_expiry_fact(tmp_path):
    io = _persist(tmp_path, _arguments())
    result = stock.reserve_kis_paper_stock_plan(**io)
    reconciled = stock.reconcile_kis_paper_stock_plan(**_reconcile(io, result))
    assert reconciled.status == "pending"
    assert reconciled.binding["terminal_evidence"] == {}


def test_exact_zero_fill_cancellation_requires_typed_proof(tmp_path):
    io = _persist(tmp_path, _arguments())
    result = stock.reserve_kis_paper_stock_plan(**io)
    state = _observed(result.intents[0], phase="cancelled", remaining="0")
    budget._atomic_json(io["state_root"] / (state.intent.run_id + ".json"), state.to_dict())
    assert stock.reconcile_kis_paper_stock_plan(**_reconcile(io, result)).status == "pending"
    proof = KisPaperExecutionObservation(
        2, True, "available", state.current_fill, state.fill_observed_at, True
    )
    closed = stock.reconcile_kis_paper_stock_plan(
        **_reconcile(io, result, cancellation_proofs={state.intent.run_id: proof})
    )
    assert closed.status == "reconciled"
    assert closed.binding["terminal_evidence"][state.intent.run_id]["cancellation"] is not None


@pytest.mark.parametrize("bad", ["foreign", "raw", "wrong_plan", "wrong_input", "wrong_parent"])
def test_reconcile_scope_failure_never_changes_binding(tmp_path, bad):
    io = _persist(tmp_path, _arguments())
    result = stock.reserve_kis_paper_stock_plan(**io)
    args = _reconcile(io, result)
    if bad == "foreign":
        args["cancellation_proofs"] = {"unrelated": None}
    elif bad == "raw":
        args["cancellation_proofs"] = {result.intents[0].run_id: {"cancellation_confirmed": True}}
    else:
        field = {
            "wrong_plan": "expected_plan_ref",
            "wrong_input": "input_ref",
            "wrong_parent": "expected_binding_ref",
        }[bad]
        args[field] = "sha256:" + "f" * 64
    before = (io["state_root"] / budget.BUDGET_FILE).read_bytes()
    with pytest.raises(_RecoveryRequired):
        stock.reconcile_kis_paper_stock_plan(**args)
    assert (io["state_root"] / budget.BUDGET_FILE).read_bytes() == before


def test_result_projection_does_not_expose_private_numbers_or_identifiers():
    result = stock.build_kis_paper_stock_plan(**_arguments())
    public = json.dumps(result.safe_payload()) + repr(result)
    assert result.intents[0].symbol not in public and result.plan_ref not in public
    assert result.binding["account_ref"] not in public and result.intents[0].run_id not in public
    assert result.safe_payload()["new_submits"] == 0
    with pytest.raises(FrozenInstanceError):
        result.status = "reserved"


def test_atomic_publication_failure_retains_original_bank(tmp_path, monkeypatch):
    io = _persist(tmp_path, _arguments())
    before = (io["state_root"] / budget.BUDGET_FILE).read_bytes()

    def fail(*args):
        raise OSError("synthetic_publish_failure")

    monkeypatch.setattr(budget, "_atomic_json", fail)
    with pytest.raises(OSError):
        stock.reserve_kis_paper_stock_plan(**io)
    assert (io["state_root"] / budget.BUDGET_FILE).read_bytes() == before


def test_missing_canonical_basis_never_initializes_a_new_bank(tmp_path):
    io = _persist(tmp_path, _arguments())
    (io["state_root"] / budget.BUDGET_FILE).unlink()
    with pytest.raises(_RecoveryRequired, match="stock_existing_basis_required"):
        stock.reserve_kis_paper_stock_plan(**io)
    assert not (io["state_root"] / budget.BUDGET_FILE).exists()


@pytest.mark.parametrize("precision", [2, 6, 28])
def test_new_plan_exact_reservation_ignores_decimal_precision(precision):
    args = _arguments(price="33.3333")
    with localcontext() as context:
        context.prec = precision
        context.rounding = ROUND_UP
        result = stock.build_kis_paper_stock_plan(**args)
    assert result.intents[0].quantity == 3
    assert result.reservation == D("99.9999")


def test_existing_qqq_unknown_consumes_capacity_without_global_pause():
    state = _state(symbol="QQQ", pending=True)
    state = replace(
        state,
        intent=replace(state.intent, limit_price=D(950)),
        phase="outcome_unknown",
        submission_started_at=state.intent.created_at,
        reason_code="submit_transport_unknown",
    )
    args = _arguments(state)
    args["binding"]["qqq"]["orders"][0]["closed"] = False
    args["expected_binding_ref"] = "sha256:" + budget._digest(args["binding"])
    result = stock.build_kis_paper_stock_plan(**args)
    assert result.status == "prepared" and result.intents[0].quantity == 5
    assert result.reservation == 50 and result.binding["qqq"] == args["binding"]["qqq"]
    assert result.binding["basis_ref"] == args["binding"]["basis_ref"]


def test_registered_owner_pending_blocks_only_new_stock_request():
    args = _arguments()
    first = stock.build_kis_paper_stock_plan(**args)
    other = _retained(args, first)
    other.update(
        request_id="synthetic-stock-2",
        expected_binding_ref="sha256:" + budget._digest(first.binding),
    )
    result = stock.build_kis_paper_stock_plan(**other)
    assert result.status == "no_intent" and result.reason == "stock_owner_pending"
    assert first.binding == other["binding"] and len(budget._stock_seed_states(first.binding)) == 1


def test_retry_remains_original_after_second_closed_stock_plan(tmp_path):
    args = _arguments()
    io = _persist(tmp_path, args)
    first = stock.reserve_kis_paper_stock_plan(**io)
    intent = first.intents[0]
    state = KisPaperCanaryState(intent, "intent_recorded", intent.valid_until, "intent_expired")
    budget._atomic_json(io["state_root"] / (intent.run_id + ".json"), state.to_dict())
    closed = stock.reconcile_kis_paper_stock_plan(**_reconcile(io, first))
    # Use a separate fresh proposal clock and fresh reads for the distinct request.
    later = AT + timedelta(minutes=6)
    fresh = _retained(args, closed)
    fresh["states"][intent.run_id] = state
    reads = args["reads"]
    snapshot = reads.snapshot
    fresh["reads"] = replace(
        reads,
        started_at=later,
        completed_at=later,
        quote=replace(reads.quote, quoted_at=later),
        cash=replace(reads.cash, captured_at=later),
        orderable=replace(reads.orderable, captured_at=later),
        snapshot=replace(
            snapshot,
            captured_at=later,
            identity=replace(snapshot.identity, captured_at=later),
            cash=replace(snapshot.cash, captured_at=later),
            orderable_funds=replace(snapshot.orderable_funds, captured_at=later),
            open_orders=replace(snapshot.open_orders, captured_at=later),
        ),
    )
    fresh.update(
        request_id="synthetic-stock-2",
        as_of=later,
        valid_until=later + timedelta(minutes=5),
        expected_binding_ref="sha256:" + budget._digest(closed.binding),
    )
    second = stock.build_kis_paper_stock_plan(**fresh)
    assert second.status == "prepared" and second.intents[0].run_id != intent.run_id
    retry = args | dict(
        binding=second.binding,
        states=budget._stock_seed_states(second.binding) | {intent.run_id: state},
        expected_owner_refs=_refs(second.binding),
        as_of=later,
        proposal=None,
        receipt=None,
        reads=None,
    )
    reused = stock.build_kis_paper_stock_plan(**retry)
    assert reused.status == "replayed" and reused.intents == first.intents
    assert reused.plan_ref == first.plan_ref
    assert (
        second.binding["stocks"][intent.symbol]["plans"][0]
        == first.binding["stocks"][intent.symbol]["plans"][0]
    )


def test_foreign_stock_registry_is_not_replaced_or_adopted():
    args = _arguments()
    first = stock.build_kis_paper_stock_plan(**args)
    retry = _retained(args, first)
    retry["instrument"] = KisPaperStockInstrument("DIFFERENT", args["instrument"].binding_ref)
    with pytest.raises(_RecoveryRequired, match="stock_registry_conflict"):
        stock.build_kis_paper_stock_plan(**retry)


def test_trio_request_identity_collision_rejected():
    from test_kis_paper_portfolio_plan import _arguments as trio_arguments
    from thericher_v2.execution.kis_paper_portfolio_plan import build_kis_paper_portfolio_plan

    trio_args = trio_arguments()
    trio = build_kis_paper_portfolio_plan(**trio_args)
    args = _arguments()
    args.update(
        binding=trio.binding,
        states=budget._portfolio_seed_states(trio.binding),
        expected_owner_refs=_refs(trio.binding),
        expected_binding_ref="sha256:" + budget._digest(trio.binding),
        request_id=trio_args["request_id"],
    )
    with pytest.raises(_RecoveryRequired, match="stock_request_conflict"):
        stock.build_kis_paper_stock_plan(**args)


def test_reconcile_never_silently_accepts_foreign_intent_state(tmp_path):
    io = _persist(tmp_path, _arguments())
    first = stock.reserve_kis_paper_stock_plan(**io)
    intent = first.intents[0]
    state = KisPaperCanaryState(replace(intent, quantity=D(1)), "intent_recorded", AT, "preview")
    budget._atomic_json(io["state_root"] / (intent.run_id + ".json"), state.to_dict())
    before = (io["state_root"] / budget.BUDGET_FILE).read_bytes()
    with pytest.raises(_RecoveryRequired, match="budget_intent_mismatch"):
        stock.reconcile_kis_paper_stock_plan(**_reconcile(io, first))
    assert (io["state_root"] / budget.BUDGET_FILE).read_bytes() == before


def test_readback_failure_does_not_delete_retained_reservation(tmp_path, monkeypatch):
    io = _persist(tmp_path, _arguments())
    native = budget._load_binding
    calls = 0

    def changed(*args):
        nonlocal calls
        calls += 1
        binding = native(*args)
        if calls == 2:
            binding = copy.deepcopy(binding)
            binding["at"] = (AT - timedelta(days=2)).isoformat()
        return binding

    monkeypatch.setattr(budget, "_load_binding", changed)
    with pytest.raises(_RecoveryRequired, match="stock_reservation_readback_mismatch"):
        stock.reserve_kis_paper_stock_plan(**io)
    assert len(budget._stock_seed_states(native(io["state_root"]))) == 1


def test_lock_order_matches_existing_session_then_canary(tmp_path, monkeypatch):
    from contextlib import contextmanager

    io = _persist(tmp_path, _arguments())
    native = stock.exclusive_kis_paper_canary_state_lock
    events = []

    @contextmanager
    def tracked(path):
        events.append(("enter", path.name))
        with native(path):
            yield
        events.append(("exit", path.name))

    monkeypatch.setattr(stock, "exclusive_kis_paper_canary_state_lock", tracked)
    first = stock.reserve_kis_paper_stock_plan(**io)
    stock.reconcile_kis_paper_stock_plan(**_reconcile(io, first))
    assert (
        events
        == [
            ("enter", ".session_execution"),
            ("enter", ".canary_execution"),
            ("exit", ".canary_execution"),
            ("exit", ".session_execution"),
        ]
        * 2
    )


def test_distinct_request_with_stale_parent_cannot_double_reserve(tmp_path):
    io = _persist(tmp_path, _arguments())

    def attempt(request):
        try:
            return stock.reserve_kis_paper_stock_plan(**(io | {"request_id": request})).status
        except _RecoveryRequired:
            return "scope_conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ("synthetic-stock-1", "synthetic-stock-2")))
    assert sorted(outcomes) == ["reserved", "scope_conflict"]
    binding = budget._load_binding(io["state_root"])
    assert len(budget._stock_seed_states(binding)) == 1
    assert (
        budget.project_budget(
            io["state_root"], binding, as_of=AT, stock_symbol=io["instrument"].symbol
        ).reserved_buys
        == 100
    )


@pytest.mark.parametrize("extra", [False, True])
def test_incomplete_or_extra_state_scope_cannot_replay(extra):
    args = _arguments()
    first = stock.build_kis_paper_stock_plan(**args)
    retry = _retained(args, first)
    if extra:
        retry["states"]["foreign-run"] = _state()
    else:
        retry["states"].clear()
    with pytest.raises(_RecoveryRequired, match="budget_owner_scope_invalid"):
        stock.build_kis_paper_stock_plan(**retry)
