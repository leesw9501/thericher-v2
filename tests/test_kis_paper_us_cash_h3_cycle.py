"""Inclusive H3 native routes and custody with invented broker facts only."""

import copy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_kis_paper_elapsed_cash_h3 as elapsed
import test_kis_paper_weight_cycle as weights
import test_liquid17_nas_nys_compatibility as us
import test_model_paper_weights_us_cash_h3_ops as inputs
from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution import paper_account_session as session
from thericher_v2.execution.paper_account_round import PaperRoundSlot

D = Decimal
PROFILE = core.StockCycleProfile.MODEL_WEIGHTS_US_CASH_H3_OPS


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)


@pytest.fixture
def h(tmp_path):
    state = us.us_h.__wrapped__(tmp_path)
    bind(state, inputs.make_input())
    return state


@pytest.fixture(params=["us_open5", "nas_preclose5"])
def window_h(request, tmp_path):
    if request.param == "us_open5":
        return h.__wrapped__(tmp_path)
    state = elapsed.h.__wrapped__(tmp_path)
    rows = elapsed.stock_rows([D(".25"), D(".25"), *([D(0)] * 15)])
    weights.bind(state, elapsed.point(rows), elapsed.PROFILE)
    state["now"] = state["data"].entry_session.close_ts - timedelta(minutes=4)
    return state


def bind(h, value):
    weights.bind(h, value, PROFILE)
    h["now"] = value.entry_session.open_ts + timedelta(seconds=30)


def forbidden(*args, **kwargs):
    pytest.fail("retained_request_must_not_load_or_replace_input")


def test_full18_native_codec_routes_and_account_cohort(h):
    value = h["data"]
    assert core._unpack(core._pack(value)) == value
    assert core._validate_model_input(value, h["now"], PROFILE) is value
    assert len(value.metadata.rows) == 18 and value.metadata.rows[-1].route == "CASH"
    assert {core._target_instrument(t, PROFILE).order_exchange for t in value.targets} == {
        "NASD", "NYSE",
    }
    item = session.PaperAccountCohort(
        PaperRoundSlot("invented-inclusive3", "entry", value.entry_session.open_ts,
                       value.entry_session.open_ts + timedelta(minutes=5),
                       value.input_ref, value.policy_ref),
        "sha256:" + "a" * 64, h["initial"]["basis_ref"], PROFILE,
    )
    item.validate()


def test_exact_buys_then_third_preclose_exits_keep_original_bank_and_f9(h):
    before = core.budget._load_binding(h["root"])
    old_qqq = copy.deepcopy(before["qqq"])
    old_states = {
        row["run_id"]: (h["root"] / (row["run_id"] + ".json")).read_bytes()
        for row in before["qqq"]["orders"]
    }
    assert weights.visit_all(h)[-1].status == "hold"
    buys = tuple(h["submits"])
    assert len(buys) == 4 and {i.symbol for i in buys} == {"AAPL", "JPM", "JNJ", "UNH"}
    assert {i.exchange for i in buys} == {"NASD", "NYSE"}
    assert core._unpack(weights.record(h)["active"]["model_input"]) == h["data"]
    h["now"] = h["data"].metadata.exit_not_before - timedelta(seconds=1)
    assert weights.run(h, target_loader=forbidden).status == "hold"
    h["now"] += timedelta(seconds=1)
    assert weights.visit_all(h, target_loader=forbidden)[-1].status == "complete"
    assert len(h["submits"]) == 2 * len(buys)
    assert all(i.side == "sell" for i in h["submits"][len(buys):])
    after = core.budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "qqq", "orders", "portfolio", "legacy_spy"):
        assert after[key] == before[key]
    assert after["qqq"] == old_qqq
    assert all((h["root"] / (run + ".json")).read_bytes() == raw
               for run, raw in old_states.items())


@pytest.mark.parametrize("seconds", [-1, 300, 1800])
def test_fresh_entry_outside_open5_never_creates_journal_or_client(h, seconds):
    h["now"] = h["data"].entry_session.open_ts + timedelta(seconds=seconds)
    before = weights.bank_bytes(h)
    result = weights.run(h)
    assert result.status == "unavailable" and result.reason == "cycle_session_invalid"
    assert weights.record(h) is None and h["factories"] == 0 and not h["submits"]
    assert weights.bank_bytes(h) == before


def test_all_cash_does_not_create_owner_or_spend(h):
    bind(h, inputs.make_input(rows=inputs._rows(selected=())))
    before = weights.bank_bytes(h)
    assert weights.run(h).status == "no_intent"
    assert weights.record(h) is None and h["factories"] == 0 and not h["submits"]
    assert weights.bank_bytes(h) == before


def test_retained_unfinished_basket_abstains_at_open5_without_client_or_cursor_work(h):
    assert weights.run(h).status == "advanced"
    retained = copy.deepcopy(weights.record(h))
    before = weights.bank_bytes(h)
    factories = h["factories"]
    h["now"] = h["data"].entry_session.open_ts + timedelta(minutes=5)
    result = weights.run(h, target_loader=forbidden)
    assert result.status == "hold" and result.reason == "outside_declared_session"
    assert h["factories"] == factories and len(h["submits"]) == 1
    assert weights.record(h) == retained and weights.bank_bytes(h) == before


def test_crossing_open5_during_quote_read_never_reserves_or_advances_cursor(h, monkeypatch):
    preview = us.VenueSyntheticClient.stock_preview_snapshot

    def cross_deadline(client, **kwargs):
        reads = preview(client, **kwargs)
        h["now"] += timedelta(seconds=2)
        return reads

    monkeypatch.setattr(us.VenueSyntheticClient, "stock_preview_snapshot", cross_deadline)
    h["now"] = h["data"].entry_session.open_ts + timedelta(minutes=5, seconds=-1)
    before = weights.bank_bytes(h)
    result = weights.run(h)
    assert result.status == "hold" and result.reason == "outside_declared_session"
    assert weights.record(h)["active"]["entries_done"] == []
    assert weights.record(h)["pending"] is None
    assert not h["submits"] and weights.bank_bytes(h) == before


def test_crossing_open5_then_quote_timestamp_unavailable_preserves_retained_basket(
    h, monkeypatch,
):
    assert weights.run(h).status == "advanced"
    retained = copy.deepcopy(weights.record(h))
    before = weights.bank_bytes(h)
    submits, cancels = tuple(h["submits"]), tuple(h["cancels"])
    deadline = h["data"].entry_session.open_ts + timedelta(minutes=5)
    h["now"] = deadline - timedelta(seconds=1)
    reads = []

    def cross_deadline_then_unavailable(client, **kwargs):
        assert client.instrument.symbol == "JPM"
        assert client.instrument.order_exchange == "NYSE"
        reads.append(client.instrument.symbol)
        h["now"] = deadline
        raise core.KisPaperReadOnlyError("quote_timestamp_unavailable")

    monkeypatch.setattr(
        us.VenueSyntheticClient, "stock_preview_snapshot", cross_deadline_then_unavailable,
    )
    result = weights.run(h, target_loader=forbidden)

    assert reads == ["JPM"] and h["now"] == deadline
    assert result.status == "hold" and result.reason == "outside_declared_session"
    assert weights.record(h) == retained and weights.bank_bytes(h) == before
    assert tuple(h["submits"]) == submits and tuple(h["cancels"]) == cancels


@pytest.mark.parametrize("budget_field", [None, "remaining_cap", "remaining_gross_cash"])
def test_projection_crossing_entry_end_preserves_cursor_and_bank(
    window_h, monkeypatch, budget_field,
):
    h = window_h
    assert weights.run(h).status == "advanced"
    retained = copy.deepcopy(weights.record(h))
    before = weights.bank_bytes(h)
    factories, submits = h["factories"], tuple(h["submits"])
    deadline = h["data"].targets[0].proposal.valid_until
    h["now"] = deadline - timedelta(seconds=1)
    project = core._projection
    calls = []

    def cross_deadline(*args, **kwargs):
        states, replayed, proofs, projection = project(*args, **kwargs)
        if budget_field is not None:
            projection = replace(projection, **{budget_field: D(0)})
        calls.append(True)
        h["now"] = deadline
        return states, replayed, proofs, projection

    monkeypatch.setattr(core, "_projection", cross_deadline)
    result = weights.run(h, target_loader=forbidden)
    assert calls == [True]
    assert result.status == "hold" and result.reason == "outside_declared_session"
    assert weights.record(h) == retained and weights.bank_bytes(h) == before
    assert h["factories"] == factories and tuple(h["submits"]) == submits


@pytest.mark.parametrize("prepared", [False, True])
def test_planner_crossing_entry_end_cannot_skip_or_journal_plan(window_h, monkeypatch, prepared):
    h = window_h
    assert weights.run(h).status == "advanced"
    retained = copy.deepcopy(weights.record(h))
    before = weights.bank_bytes(h)
    submits = tuple(h["submits"])
    deadline = h["data"].targets[0].proposal.valid_until
    h["now"] = deadline - timedelta(seconds=1)
    build = core.entries.build_kis_paper_stock_plan
    calls = []

    def cross_deadline(**kwargs):
        if not prepared:
            reads, price = kwargs["reads"], D(1000000)
            quote = core.KisPaperSpyLimitInput(price, 4, D(".0001"), h["now"], price, price)
            orderable = replace(reads.orderable, reference_price=price)
            kwargs["reads"] = replace(
                reads, quote=quote, buy_limit=price, orderable=orderable,
                snapshot=replace(reads.snapshot, orderable_funds=orderable),
            )
        result = build(**kwargs)
        assert result.status == ("prepared" if prepared else "no_intent")
        calls.append(result.status)
        h["now"] = deadline
        return result

    monkeypatch.setattr(core.entries, "build_kis_paper_stock_plan", cross_deadline)
    result = weights.run(h, target_loader=forbidden)
    assert len(calls) == 1
    assert result.status == "hold" and result.reason == "outside_declared_session"
    assert weights.record(h) == retained and weights.bank_bytes(h) == before
    assert tuple(h["submits"]) == submits and not h["cancels"]


@pytest.mark.parametrize("cross", [False, True])
def test_final_no_order_completion_rechecks_its_own_projection(h, monkeypatch, cross):
    client_class = us.VenueSyntheticClient
    preview = client_class.stock_preview_snapshot

    def expensive(client, **kwargs):
        reads, price = preview(client, **kwargs), D(1000000)
        quote = core.KisPaperSpyLimitInput(price, 4, D(".0001"), h["now"], price, price)
        orderable = replace(reads.orderable, reference_price=price)
        return replace(
            reads, quote=quote, buy_limit=price, orderable=orderable,
            snapshot=replace(reads.snapshot, orderable_funds=orderable),
        )

    monkeypatch.setattr(client_class, "stock_preview_snapshot", expensive)
    for _ in h["data"].targets[:-1]:
        assert weights.run(h).status == "no_intent"
    retained = copy.deepcopy(weights.record(h))
    before = weights.bank_bytes(h)
    deadline = h["data"].targets[0].proposal.valid_until
    h["now"] = deadline - timedelta(seconds=1)
    project = core._projection
    calls = []

    def cross_nested_projection(*args, **kwargs):
        result = project(*args, **kwargs)
        calls.append(True)
        if cross and len(calls) == 2:
            h["now"] = deadline
        return result

    monkeypatch.setattr(core, "_projection", cross_nested_projection)
    result = weights.run(h, target_loader=forbidden)
    assert len(calls) == 2
    if cross:
        assert result.status == "hold" and result.reason == "outside_declared_session"
        assert weights.record(h) == retained
    else:
        assert result.status == "complete" and result.reason == "policy_no_order_complete"
        assert weights.record(h)["active"] is None
    assert weights.bank_bytes(h) == before
    assert not h["submits"] and not h["cancels"]


@pytest.mark.parametrize("stage", ["loader", "client"])
def test_entry_setup_crossing_end_never_reads_quote_or_changes_cursor(window_h, monkeypatch, stage):
    h = window_h
    deadline = h["data"].targets[0].proposal.valid_until
    if stage == "client":
        assert weights.run(h).status == "advanced"
    retained = copy.deepcopy(weights.record(h))
    before = weights.bank_bytes(h)
    submits = tuple(h["submits"])
    h["now"] = deadline - timedelta(seconds=1)
    calls = []

    def cross_loader():
        calls.append(True)
        h["now"] = deadline
        return h["data"]

    factory = h["call"]["client_factory"]

    def cross_client(instrument):
        client = factory(instrument)
        calls.append(True)
        h["now"] = deadline
        monkeypatch.setattr(client, "stock_preview_snapshot", forbidden)
        return client

    changes = ({"target_loader": cross_loader} if stage == "loader" else
               {"target_loader": forbidden, "client_factory": cross_client})
    result = weights.run(h, **changes)
    assert calls == [True]
    assert result.status == "hold" and result.reason == "outside_declared_session"
    assert weights.record(h) == retained and weights.bank_bytes(h) == before
    assert tuple(h["submits"]) == submits and not h["cancels"]


@pytest.mark.parametrize("stage", ["projection", "planner", "quote"])
def test_sell_crossing_close_keeps_inventory_and_pending_absent(window_h, monkeypatch, stage):
    h = window_h
    assert weights.visit_all(h)[-1].status == "hold"
    deadline = h["data"].exit_session.close_ts
    h["now"] = deadline - timedelta(seconds=1)
    # Retain the real first decision before testing a subsequent delayed visit.
    reads_name = "stock_exit_snapshot"
    client_class = (us.VenueSyntheticClient if h["call"]["profile"] is PROFILE
                    else elapsed.model.SyntheticClient)
    preview = getattr(client_class, reads_name)

    def missing_quote(*args, **kwargs):
        raise core.KisPaperReadOnlyError("quote_timestamp_unavailable")

    with monkeypatch.context() as setup:
        setup.setattr(client_class, reads_name, missing_quote)
        assert weights.run(h, target_loader=forbidden).status == "unavailable"
    retained = copy.deepcopy(weights.record(h))
    before = weights.bank_bytes(h)
    submits, factories = tuple(h["submits"]), h["factories"]
    owner, name = (
        (core, "_projection") if stage == "projection" else
        (core.exits, "build_kis_paper_stock_exit_plan") if stage == "planner" else
        (client_class, reads_name)
    )
    original = preview if stage == "quote" else getattr(owner, name)
    calls = []

    def cross_deadline(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        h["now"] = deadline
        return result

    monkeypatch.setattr(owner, name, cross_deadline)
    result = weights.run(h, target_loader=forbidden)
    assert calls == [True]
    assert result.status == "hold" and result.reason == "outside_declared_session"
    assert weights.record(h) == retained and weights.bank_bytes(h) == before
    assert tuple(h["submits"]) == submits and not h["cancels"]
    if stage == "projection":
        assert h["factories"] == factories


def test_owned_exit_after_missed_third_close_uses_current_session_without_new_weights(h):
    assert weights.visit_all(h)[-1].status == "hold"
    buys = len(h["submits"])
    h["now"] = h["data"].exit_session.open_ts + timedelta(days=1, minutes=1)
    assert weights.visit_all(h, target_loader=forbidden)[-1].status == "complete"
    assert len(h["submits"]) == 2 * buys
    assert all(intent.side == "sell" for intent in h["submits"][buys:])


def test_oversized_cohort_cannot_expand_original_shared_tenth(h):
    bind(h, inputs.make_input(original_basis_gross_ceiling=D(".1001")))
    before = weights.bank_bytes(h)
    assert weights.run(h).reason == "cycle_input_invalid"
    assert weights.record(h) is None and h["factories"] == 0 and not h["submits"]
    assert weights.bank_bytes(h) == before


def test_nys_unknown_request_reconciles_after_open5_without_replacement(h):
    bind(h, inputs.make_input(rows=inputs._rows(selected=(8,))))
    h["unknown"] = True
    assert weights.run(h).status == "pending"
    pending = copy.deepcopy(weights.record(h)["pending"])
    before = weights.bank_bytes(h)
    intent = h["submits"][0]
    assert intent.exchange == "NYSE"
    h["now"] = intent.valid_until + timedelta(seconds=1)
    assert weights.run(h, target_loader=forbidden).status == "pending"
    assert weights.record(h)["pending"] == pending
    assert weights.bank_bytes(h) == before and len(h["submits"]) == 1
    assert not h["cancels"]


def test_retained_nys_venue_cannot_be_swapped_to_nas(h):
    bind(h, inputs.make_input(rows=inputs._rows(selected=(8,))))
    h["unknown"] = True
    assert weights.run(h).status == "pending"
    saved = weights.record(h)
    pending = copy.deepcopy(saved["pending"])
    args = core._unpack(saved["pending"]["arguments"])
    args["instrument"] = replace(args["instrument"], venue="NAS")
    saved["pending"]["arguments"] = core._pack(args)
    with pytest.raises(core._CycleFault, match="cycle_input_binding_mismatch"):
        core._model_record_input(saved, h["data"].input_ref, h["data"].policy_ref, PROFILE)
    assert weights.record(h)["pending"] == pending


def test_cross_profile_recovery_cannot_release_unknown_reservation(h):
    h["unknown"] = True
    assert weights.run(h).status == "pending"
    saved = weights.record(h)
    pending = copy.deepcopy(saved["pending"])
    saved["profile"] = core.StockCycleProfile.MODEL_WEIGHTS_US_H5.value
    core._save(weights.pointer(h), saved)
    before = weights.bank_bytes(h)
    result = weights.run(
        h, profile=core.StockCycleProfile.MODEL_WEIGHTS_US_H5,
        target_loader=forbidden, client_factory=forbidden,
    )
    assert result.status == "unavailable" and weights.record(h)["pending"] == pending
    assert weights.bank_bytes(h) == before and len(h["submits"]) == 1


def test_zero_share_target_completes_without_redistributing_its_quarter(h, monkeypatch):
    preview = us.VenueSyntheticClient.stock_preview_snapshot

    def expensive_one(client, **kwargs):
        reads = preview(client, **kwargs)
        if client.instrument.symbol != "JPM":
            return reads
        price = D(1000000)
        quote = core.KisPaperSpyLimitInput(price, 4, D(".0001"), h["now"], price, price)
        orderable = replace(reads.orderable, reference_price=price)
        return replace(reads, quote=quote, buy_limit=price, orderable=orderable,
                       snapshot=replace(reads.snapshot, orderable_funds=orderable))

    monkeypatch.setattr(us.VenueSyntheticClient, "stock_preview_snapshot", expensive_one)
    value = h["data"]
    assert weights.visit_all(h)[-1].status == "hold"
    saved = weights.record(h)
    assert saved["active"]["entries_done"] == ["AAPL", "JPM", "JNJ", "UNH"]
    assert saved["active"]["entry_no_order"] == {"JPM": "target_already_satisfied"}
    assert {i.symbol for i in h["submits"]} == {"AAPL", "JNJ", "UNH"}
    assert core._unpack(saved["active"]["model_input"]) == value
    assert all(t.proposal.target_exposure == D(".00125") for t in value.targets)


@pytest.mark.parametrize("field", ["pending", "owners", "reservation"])
def test_session_no_order_prefix_never_waives_other_mutations(field):
    old = dict(entries_done=["AAPL"], entry_no_order={}, pending="same-request",
               owners="same-owner", reservation="same-reservation")
    new = old | dict(entries_done=["AAPL", "JPM"],
                     entry_no_order={"JPM": "target_already_satisfied"})
    assert session._same_skip_active(old, new, PROFILE, "JPM")
    assert not session._same_skip_active(old, new | {field: "changed"}, PROFILE, "JPM")
