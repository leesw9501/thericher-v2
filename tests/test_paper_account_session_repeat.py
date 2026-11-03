"""Repeat inclusive-H3 cohorts with real native journals and invented wire only."""

import copy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

import test_kis_paper_weight_cycle as weights
import test_model_paper_weights_us_cash_h3_ops as inputs
import test_paper_account_session as account
from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.research.model_paper_weights import prepare_model_paper_weights_input

PROFILE = core.StockCycleProfile.MODEL_WEIGHTS_US_CASH_H3_OPS


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    account.no_actual_calls.__wrapped__(monkeypatch)


@pytest.fixture
def h(tmp_path, monkeypatch):
    state = account.h.__wrapped__(tmp_path, monkeypatch)
    value = inputs.make_input(
        rows=inputs._rows(selected=(0, 1, 2, 3)), original_basis_gross_ceiling=Decimal(".1"),
    )
    weights.bind(state, value, PROFILE)
    state["now"] = state["data"].entry_session.open_ts + timedelta(seconds=20)
    state["first_failures"] = []
    return state


def complete(h):
    for index in range(4):
        result = account.visit(h, first_failure_sink=h["first_failures"].append)
        assert result["stop"] == "yield_after_first_native_leg" and not result["pending"], (
            result["native"], h["first_failures"]
        )
        if index < 3:
            account.advance(h, 61)
    h["now"] = h["data"].metadata.exit_not_before
    for index in range(4):
        account.visit(h, item=account.cohort(h, mode="exit"), loader=account.forbidden)
        if index < 3:
            account.advance(h, 61)
    saved = weights.record(h)
    assert saved["active"] is None and saved["pending"] is None
    assert saved["completed"] == [h["data"].input_ref]
    assert len(h["submits"]) == 8
    return h["data"]


def next_input(h, old):
    delta = timedelta(days=7)
    value = prepare_model_paper_weights_input(
        replace(
            old.metadata, full_output_ref="sha256:" + "d" * 64,
            input_manifest_ref="sha256:" + "e" * 64,
            **{key: getattr(old.metadata, key) + delta for key in (
                "feature_window_end", "source_available_at", "input_asof",
                "inference_started_at", "inference_completed_at", "weights_observed_at",
                "exit_not_before",
            )},
        ),
        entry_session=replace(old.entry_session, open_ts=old.entry_session.open_ts + delta,
                              close_ts=old.entry_session.close_ts + delta),
        exit_session=replace(old.exit_session, open_ts=old.exit_session.open_ts + delta,
                             close_ts=old.exit_session.close_ts + delta),
        profile=old.profile,
    )
    assert value.policy_ref == old.policy_ref and value.input_ref != old.input_ref
    weights.bind(h, value, PROFILE)
    h["now"] = value.entry_session.open_ts + timedelta(seconds=20)
    return value


def test_same_policy_two_dated_cohorts_keep_original_bank_f9_and_history(h):
    old = complete(h)
    bank = core.budget._load_binding(h["root"])
    prior = copy.deepcopy(weights.record(h))
    old_runs = {
        ref.run_id: (h["root"] / (ref.run_id + ".json")).read_bytes()
        for owner, _ in core.budget._owners(bank) for ref in owner.state_refs
    }
    fresh = next_input(h, old)
    for index in range(4):
        assert account.visit(h)["stop"] == "yield_after_first_native_leg"
        if index < 3:
            account.advance(h, 61)
    assert len(h["submits"]) == 12
    assert all(intent.side == "buy" for intent in h["submits"][8:])
    saved = weights.record(h)
    assert saved["completed"] == [old.input_ref]
    assert saved["active"]["input_ref"] == fresh.input_ref
    assert set(prior["owners"]) == set(saved["owners"])
    assert all(set(prior["owners"][symbol]["plans"]) <= set(saved["owners"][symbol]["plans"])
               for symbol in prior["owners"])
    h["now"] = fresh.metadata.exit_not_before
    for index in range(4):
        account.visit(h, item=account.cohort(h, mode="exit"), loader=account.forbidden)
        if index < 3:
            account.advance(h, 61)
    saved = weights.record(h)
    assert saved["active"] is None and saved["pending"] is None
    assert saved["completed"] == [old.input_ref, fresh.input_ref]
    assert len(h["submits"]) == 16
    assert all(intent.side == "sell" for intent in h["submits"][12:])
    after = core.budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "qqq", "orders", "portfolio", "legacy_spy"):
        assert after[key] == bank[key]
    assert all((h["root"] / (run + ".json")).read_bytes() == raw
               for run, raw in old_runs.items())


@pytest.mark.parametrize("mode", ["entry", "exit", "recovery"])
def test_completed_input_never_reloads_or_replays(h, mode):
    complete(h)
    before = weights.bank_bytes(h)
    saved = copy.deepcopy(weights.record(h))
    if mode == "entry":
        h["now"] = h["data"].entry_session.open_ts + timedelta(seconds=20)
    result = account.visit(h, item=account.cohort(h, mode=mode), loader=account.forbidden)
    assert result["native_calls"] == 0 and h["wires"] == 8
    assert result["stop"] == {
        "entry": "retained_completed_input", "exit": "retained_inactive_no_new_cohort",
        "recovery": "no_retained_pending",
    }[mode]
    assert weights.record(h) == saved and weights.bank_bytes(h) == before


def test_missing_terminal_proof_denies_new_loader_and_preserves_state(h):
    old = complete(h)
    next_input(h, old)
    bank = core.budget._load_binding(h["root"])
    symbol = next(iter(weights.record(h)["owners"]))
    run = next(iter(bank["stocks"][symbol]["plans"][0]["states"]))
    bank["terminal_evidence"].pop(run)
    core.budget._atomic_json(h["root"] / core.budget.BUDGET_FILE, bank)
    before = weights.bank_bytes(h)
    saved = copy.deepcopy(weights.record(h))
    with pytest.raises(core._CycleFault, match="cycle_owned_not_flat"):
        account.visit(h, loader=account.forbidden)
    assert weights.record(h) == saved and weights.bank_bytes(h) == before
    assert h["wires"] == 8


def test_inactive_without_positive_completion_cannot_start_new_cohort(h):
    old = complete(h)
    saved = weights.record(h)
    saved["completed"] = []
    saved["owners"] = {}
    core._save(weights.pointer(h), saved)
    next_input(h, old)
    before = weights.bank_bytes(h)
    with pytest.raises(ValueError, match="account_session_prior_completion_missing"):
        account.visit(h, loader=account.forbidden)
    assert weights.bank_bytes(h) == before and h["wires"] == 8


@pytest.mark.parametrize("stage", ["flat", "loader"])
def test_next_entry_expiring_during_flat_check_or_loader_has_no_effect(h, monkeypatch, stage):
    old = complete(h)
    fresh = next_input(h, old)
    h["now"] = fresh.entry_session.open_ts + timedelta(minutes=4, seconds=59)
    before = weights.bank_bytes(h)
    saved = copy.deepcopy(weights.record(h))
    flat = core._completed_flat

    def expire_flat(*args):
        flat(*args)
        if stage == "flat":
            h["now"] += timedelta(seconds=2)

    def loader():
        assert stage == "loader"
        h["now"] += timedelta(seconds=2)
        return fresh

    monkeypatch.setattr(core, "_completed_flat", expire_flat)
    item = account.cohort(h)
    item = replace(item, slot=replace(item.slot, ends_at=fresh.entry_session.open_ts
                                     + timedelta(minutes=5)))
    with pytest.raises(ValueError, match="account_session_deadline_closed"):
        account.visit(h, item=item, loader=loader, deadline=item.slot.ends_at)
    assert weights.bank_bytes(h) == before and weights.record(h) == saved
    assert h["wires"] == 8


@pytest.mark.parametrize("partial", [False, True])
def test_new_dated_input_cannot_replace_active_or_unknown_request(h, partial):
    h["partial"] = partial
    h["cancel_unknown"] = partial
    result = account.visit(h)
    assert result["pending"] is partial
    pending = copy.deepcopy(weights.record(h))
    before = weights.bank_bytes(h)
    old = h["data"]
    next_input(h, old)
    with pytest.raises(core._CycleFault, match="cycle_input_binding_mismatch"):
        account.visit(h, loader=account.forbidden)
    assert weights.bank_bytes(h) == before and weights.record(h) == pending
    assert len(h["submits"]) == 1


def test_other_policy_never_adopts_flat_prior_registrations(h):
    old = complete(h)
    fresh = next_input(h, old)
    changed = prepare_model_paper_weights_input(
        replace(fresh.metadata, policy_ref="sha256:" + "f" * 64),
        entry_session=fresh.entry_session, exit_session=fresh.exit_session, profile=fresh.profile,
    )
    weights.bind(h, changed, PROFILE)
    h["now"] = changed.entry_session.open_ts + timedelta(seconds=20)
    before = weights.bank_bytes(h)
    result = account.visit(h)
    assert result["skipped"] == 4 and result["native_calls"] == 4
    assert result["stop"] == "original_entry_prefix_exhausted"
    assert not weights.record(h)["owners"] and h["wires"] == 8
    assert weights.bank_bytes(h) == before


def test_native_rechecks_terminal_proof_after_new_loader_before_effect(h):
    old = complete(h)
    fresh = next_input(h, old)
    saved = copy.deepcopy(weights.record(h))

    def loader():
        bank = core.budget._load_binding(h["root"])
        symbol = next(iter(saved["owners"]))
        run = next(iter(bank["stocks"][symbol]["plans"][0]["states"]))
        bank["terminal_evidence"].pop(run)
        core.budget._atomic_json(h["root"] / core.budget.BUDGET_FILE, bank)
        return fresh

    factories = h["factories"]
    result = account.visit(h, loader=loader)
    assert result["native"] == dict(
        status="unavailable", reason="cycle_owned_not_flat", leg_count=0,
    )
    assert h["factories"] == factories and h["wires"] == 8
    assert weights.record(h) == saved


@pytest.mark.parametrize("first_skip", ["quote", "sizing", "foreign"])
def test_new_dated_cohort_first_skip_reaches_later_original_target(h, monkeypatch, first_skip):
    old = complete(h)
    fresh = next_input(h, old)
    if first_skip == "foreign":
        fresh = prepare_model_paper_weights_input(
            inputs._replace_rows(fresh.metadata, inputs._rows(selected=(4, 5, 6, 7))),
            entry_session=fresh.entry_session, exit_session=fresh.exit_session,
            profile=fresh.profile,
        )
        weights.bind(h, fresh, PROFILE)
        h["now"] = fresh.entry_session.open_ts
        account.reserve_foreign(h, fresh.targets[0])
        h["now"] += timedelta(seconds=20)
    first, second = [target.proposal.symbol for target in fresh.targets[:2]]
    if first_skip == "quote":
        h["quote_skip"].add(first)
    elif first_skip == "sizing":
        preview = account.legacy.NativeSyntheticStockClient.stock_preview_snapshot

        def expensive(client, **kwargs):
            reads = preview(client, **kwargs)
            if client.instrument.symbol != first:
                return reads
            price = Decimal(100000)
            orderable = replace(reads.orderable, reference_price=price)
            return replace(
                reads, buy_limit=price, orderable=orderable,
                quote=core.KisPaperSpyLimitInput(
                    price, 4, Decimal(".0001"), h["now"], price, price,
                ), snapshot=replace(reads.snapshot, orderable_funds=orderable),
            )

        monkeypatch.setattr(account.legacy.NativeSyntheticStockClient, "stock_preview_snapshot",
                            expensive)
    before = weights.bank_bytes(h)
    record = copy.deepcopy(weights.record(h))
    native = core.run_kis_paper_current_stock_cycle
    checked = []

    def checked_native(**kwargs):
        result = native(**kwargs)
        if result.status == "no_intent":
            assert weights.bank_bytes(h) == before
            current = weights.record(h)
            assert current["owners"] == record["owners"]
            assert current["completed"] == [old.input_ref]
            assert current["active"]["entries_done"] == [first]
            checked.append(True)
        return result

    monkeypatch.setattr(core, "run_kis_paper_current_stock_cycle", checked_native)
    result = account.visit(h)
    assert checked == [True]
    assert result["stop"] == "yield_after_first_native_leg"
    assert result["native_calls"] == 2 and result["skipped"] == 1
    assert len(h["submits"]) == 9 and h["submits"][-1].symbol == second
    assert weights.record(h)["active"]["entries_done"] == [first, second]
