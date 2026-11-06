"""Additive NET25 admission with invented rows and isolated synthetic custody."""

import copy
import hashlib
import json
import math
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

import test_kis_paper_weight_cycle as native
import test_liquid17_nas_nys_compatibility as us
import test_model_paper_raw_open_elapsed3 as raw
import test_model_paper_weights_h5 as old
from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution import paper_account_session as account
from thericher_v2.execution.paper_account_round import PaperRoundSlot
from thericher_v2.research import model_paper_weights as weights

PROFILE = weights.MODEL_PAPER_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3_PROFILE
NATIVE = core.StockCycleProfile.MODEL_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3


def metadata(selected=(0, 8)):
    # The source policy encodes half/17 downwards once, never normalizes survivors.
    half_slot = Fraction(1, 34)
    encoded = float(half_slot)
    if Fraction(Decimal(repr(encoded))) > half_slot:
        encoded = math.nextafter(encoded, 0)
    rows = weights.append_derived_cash_h3_row(
        tuple(
            weights.ModelPaperWeightRow(
                slot,
                route,
                True,
                Decimal(repr(encoded)) if slot in selected else Decimal(0),
            )
            for slot, route in enumerate(weights.MODEL_PAPER_US_CASH_H3_OPS_ROUTES[:17])
        )
    )
    first, last = raw.window(date(2026, 11, 9)), raw.window(date(2026, 11, 12))
    meta = old._metadata(first, last, rows)
    previous = meta.feature_window_end
    return replace(
        meta,
        model_id="invented-LSTM-H3-NET25-not-a-market-point",
        feature_schema_id="invented-raw60x12-ind8-not-tech19",
        source_available_at=previous + timedelta(minutes=1),
        input_asof=previous + timedelta(minutes=2),
        inference_started_at=previous + timedelta(minutes=3),
        inference_completed_at=previous + timedelta(minutes=4),
        weights_observed_at=previous + timedelta(minutes=5),
        original_basis_gross_ceiling=Decimal(".1"),
        exit_not_before=last.open_ts,
    )


def make(meta=None, *, profile=PROFILE):
    return weights.prepare_model_paper_weights_input(
        metadata() if meta is None else meta,
        entry_session=raw.window(date(2026, 11, 9)),
        exit_session=raw.window(date(2026, 11, 12)),
        profile=profile,
    )


def roundtrip(value):
    payload = weights.serialize_model_paper_weights_input(value)
    return weights.load_model_paper_weights_input(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_policy_ref=value.policy_ref,
    )


def account_visit(h, *, mode="entry", loader=None):
    value, now = h["data"], h["now"]
    slot = PaperRoundSlot(
        "invented-net25",
        "entry" if mode == "entry" else "exit",
        now,
        now + timedelta(minutes=1),
        value.input_ref,
        value.policy_ref,
    )
    cohort = account.PaperAccountCohort(slot, old.PIN, h["initial"]["basis_ref"], NATIVE, mode)
    paths = {k: v for k, v in h["call"].items() if k.endswith(("_path", "_root"))}
    return account.run_native_account_session(
        cohort=cohort,
        paths=paths,
        expected_account_ref=h["call"]["expected_account_ref"],
        target_loader=h["call"]["target_loader"] if loader is None else loader,
        client_factory=h["call"]["client_factory"],
        configure_early_exit=raw.forbidden,
        admit=lambda: True,
        deadline=slot.ends_at,
        clock=lambda: h["now"],
        monotonic=lambda: 0,
    )


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    raw.no_actual_calls.__wrapped__(monkeypatch)


@pytest.fixture
def h(tmp_path):
    state = us.us_h.__wrapped__(tmp_path)
    native.bind(state, make(), NATIVE)
    state["now"] = state["data"].entry_session.open_ts + timedelta(minutes=1)
    return state


def test_nonempty_point_actual_codec_typed_targets_and_account_input():
    value = roundtrip(make())
    assert value == core._unpack(core._pack(value))
    assert NATIVE.value == PROFILE == "model-weights-us-cash-net25-open-elapsed3-open5-2026-v1"
    assert value.execution_basis == weights.NET25_OPEN_ELAPSED3_EXECUTION_BASIS
    assert len(value.targets) == 2
    assert [t.route for t in value.targets] == ["AAPL/NAS", "JPM/NYS"]
    assert all(type(t.proposal) is TargetExposureProposal for t in value.targets)
    assert all("ABSOLUTE_NET25_PROVISIONAL_NON_PARITY" in t.proposal.reason for t in value.targets)
    assert core._validate_model_input(value, value.entry_session.open_ts, NATIVE) is value
    assert [core._target_instrument(t, NATIVE).order_exchange for t in value.targets] == [
        "NASD",
        "NYSE",
    ]
    at = value.entry_session.open_ts + timedelta(minutes=1)
    slot = PaperRoundSlot(
        "invented-net25", "entry", at, at + timedelta(minutes=1), value.input_ref, value.policy_ref
    )
    account.PaperAccountCohort(slot, old.PIN, old.PIN, NATIVE).validate()
    clocks = [
        getattr(value.metadata, name)
        for name in (
            "feature_window_end",
            "source_available_at",
            "input_asof",
            "inference_started_at",
            "inference_completed_at",
            "weights_observed_at",
        )
    ]
    assert clocks == sorted(set(clocks))


@pytest.mark.parametrize("count", [0, 1, 2, 17])
def test_one_original_tenth_scaling_no_survivor_renormalization(count):
    value = roundtrip(make(metadata(range(count))))
    assert len(value.targets) == count
    for target in value.targets:
        ceiling = Fraction(target.research_weight) / 10
        actual = Fraction(target.proposal.target_exposure)
        assert 0 <= ceiling - actual < Fraction(1, 10**24)
        assert Fraction(target.research_weight) <= Fraction(1, 34)
    gross = sum((Fraction(t.proposal.target_exposure) for t in value.targets), Fraction())
    assert gross <= Fraction(1, 20)
    assert value.metadata.rows == weights.append_derived_cash_h3_row(value.metadata.rows[:17])
    if count == 0:
        assert value.targets == () and value.metadata.rows[-1].weight == 1


@pytest.mark.parametrize(
    "field",
    [
        "source_available_at",
        "input_asof",
        "inference_started_at",
        "inference_completed_at",
        "weights_observed_at",
    ],
)
def test_metadata_chronology_not_replaced_by_publication_stamp(field):
    meta = metadata()
    with pytest.raises(ValueError, match="weights_causal_clocks_invalid"):
        replace(meta, **{field: meta.feature_window_end - timedelta(seconds=1)})
    with pytest.raises(ValueError, match="weights_causal_clocks_invalid"):
        replace(meta, **{field: getattr(meta, field).replace(tzinfo=None)})


@pytest.mark.parametrize("slot", [0, 8, 16])
def test_unknown_zero_weight_still_withholds_whole_net25_point(slot):
    meta = metadata(())
    rows = tuple(replace(r, feature_known=False) if r.slot == slot else r for r in meta.rows)
    meta = replace(meta, rows=rows, feature_mask_ref=weights.model_weight_mask_ref(rows))
    with pytest.raises(ValueError, match="weights_raw_open_unknown"):
        make(meta)


@pytest.mark.parametrize("fault", ["basis", "raw_profile", "ops_profile", "target", "extra"])
def test_rehashed_payload_cannot_relabel_semantics_or_forge_targets(fault):
    value = make()
    document = json.loads(weights.serialize_model_paper_weights_input(value))
    if fault == "basis":
        document["execution_basis"] = weights.RAW_OPEN_ELAPSED3_EXECUTION_BASIS
    elif fault == "raw_profile":
        document["profile"] = weights.MODEL_PAPER_WEIGHTS_US_CASH_RAW_OPEN_ELAPSED3_PROFILE
    elif fault == "ops_profile":
        document["profile"] = weights.MODEL_PAPER_WEIGHTS_US_CASH_3_SESSION_OPS_PROFILE
    elif fault == "target":
        document["targets"][0]["proposal"]["target_exposure"] = "0.1"
    else:
        document["metadata"]["publication_timestamp"] = document["metadata"]["weights_observed_at"]
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError):
        weights.load_model_paper_weights_input(
            payload,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            expected_policy_ref=value.policy_ref,
        )


def test_invalid_profile_controller_mismatch_and_budget_expansion_rejected():
    value = make()
    with pytest.raises(ValueError, match="weights_profile_invalid"):
        make(profile="model-weights-net25")
    with pytest.raises(core._CycleFault, match="cycle_input_invalid"):
        core._validate_model_input(value, value.entry_session.open_ts, raw.NATIVE)
    oversized = make(replace(metadata(), original_basis_gross_ceiling=Decimal(".100001")))
    with pytest.raises(core._CycleFault, match="cycle_input_invalid"):
        core._validate_model_input(oversized, value.entry_session.open_ts, NATIVE)


def test_native_positive_buy_exit_retains_same_bank_unknown_f9_and_open5_ttl(h):
    before = copy.deepcopy(core.budget._load_binding(h["root"]))
    states = {p.name: p.read_bytes() for p in h["root"].glob("*.json")}
    assert native.visit_all(h)[-1].status == "hold"
    assert [i.side for i in h["submits"]] == ["buy", "buy"]
    h["now"] = h["data"].exit_session.open_ts + timedelta(minutes=4)
    assert native.visit_all(h, target_loader=raw.forbidden)[-1].status == "complete"
    assert [i.side for i in h["submits"]] == ["buy", "buy", "sell", "sell"]
    assert all(
        i.valid_until == h["data"].exit_session.open_ts + timedelta(minutes=5)
        for i in h["submits"][2:]
    )
    after = core.budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "qqq", "orders", "portfolio", "legacy_spy"):
        assert after[key] == before[key]
    assert all(
        (h["root"] / name).read_bytes() == content
        for name, content in states.items()
        if name != core.budget.BUDGET_FILE
    )


def test_account_session_uses_existing_serial_owner_and_pending_recovery(h):
    assert account_visit(h)["stop"] == "yield_after_first_native_leg"
    assert account_visit(h, loader=raw.forbidden)["stop"] == "yield_after_first_native_leg"
    h["now"] = h["data"].exit_session.open_ts
    account_visit(h, mode="exit", loader=raw.forbidden)
    account_visit(h, mode="exit", loader=raw.forbidden)
    assert native.record(h)["active"] is None


def test_exact_unknown_remains_pending_before_loader_without_resubmission(h):
    h["unknown"] = True
    assert native.run(h).status == "pending"
    saved = copy.deepcopy(native.record(h)["pending"])
    bank = native.bank_bytes(h)
    h["now"] = h["data"].exit_session.close_ts + timedelta(days=1)
    for _ in range(2):
        assert native.run(h, target_loader=raw.forbidden).status == "pending"
    assert len(h["submits"]) == 1 and native.record(h)["pending"] == saved
    assert native.bank_bytes(h) == bank


@pytest.mark.parametrize("seconds", [-1, 300])
def test_entry_window_failure_has_no_client_or_bank_effect(h, seconds):
    h["now"] = h["data"].entry_session.open_ts + timedelta(seconds=seconds)
    before = native.bank_bytes(h)
    assert native.run(h).reason == "cycle_session_invalid"
    assert native.bank_bytes(h) == before and not h["submits"] and not h["factories"]


def test_raw_binary_contract_still_distinct_and_csco_legacy_h5_still_accepted():
    relative = raw.make()
    assert roundtrip(relative) == relative
    assert relative.execution_basis == weights.RAW_OPEN_ELAPSED3_EXECUTION_BASIS
    assert all("RELATIVE_SIGN_ONLY" in t.proposal.reason for t in relative.targets)
    first, last = raw.window(date(2026, 11, 9)), raw.window(date(2026, 11, 13))
    rows = (weights.ModelPaperWeightRow(0, "CSCO/NAS", True, Decimal(1)),)
    csco = weights.prepare_model_paper_weights_input(
        old._metadata(first, last, rows),
        entry_session=first,
        exit_session=last,
        profile=weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    )
    assert roundtrip(csco) == csco
    assert csco.execution_basis == weights.EXECUTION_BASIS
    assert (
        core._validate_model_input(csco, first.open_ts, core.StockCycleProfile.MODEL_WEIGHTS_NAS_H5)
        is csco
    )
    assert csco.targets[0].proposal.symbol == "CSCO"
    assert csco.targets[0].proposal.valid_until == first.close_ts
