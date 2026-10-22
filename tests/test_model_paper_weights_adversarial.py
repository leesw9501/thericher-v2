"""Invented CPU-only attacks on weight admission, not broker/runtime qualification.

Unassigned gross-ceiling mass is not broker cash, measured fees or settlement.
"""

import hashlib
import json
import struct
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta, timezone
from decimal import ROUND_FLOOR, ROUND_UP, Decimal, Inexact, Rounded, localcontext
from fractions import Fraction

import pytest

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import model_paper_proposal as legacy
from thericher_v2.research import model_paper_weights as weights

D = Decimal
PIN = "sha256:" + "a" * 64
POLICY = "sha256:" + "b" * 64
OTHER_PIN = "sha256:" + "c" * 64
CEILING = Fraction(5, 1000)


def _rows(overrides=None):
    values = {0: "0.125", 1: "0.25", 2: "0.375", 5: "0.25"}
    if overrides is not None:
        values = overrides
    return tuple(
        weights.ModelPaperWeightRow(
            slot,
            "W" + chr(65 + slot // 26) + chr(65 + slot % 26)
            + ("/NYS" if slot == 1 else "/NAS"),
            slot != 4,
            D(values.get(slot, "0")),
        )
        for slot in range(100)
    )


def _metadata(rows=None):
    rows = _rows() if rows is None else rows
    first = us_equity_2026_session(date(2026, 10, 23)).window
    last = us_equity_2026_session(date(2026, 11, 19)).window
    previous = us_equity_2026_session(date(2026, 10, 22)).window.close_ts
    stamp = first.open_ts - timedelta(hours=1)
    return weights.ModelPaperWeightsMetadata(
        model_id="invented-weight-adversary",
        feature_schema_id="invented-input-only",
        model_ref=PIN,
        adapter_ref=PIN,
        affine_ref=PIN,
        input_manifest_ref=PIN,
        calendar_ref=PIN,
        policy_ref=POLICY,
        full_output_ref=PIN,
        feature_mask_ref=weights.model_weight_mask_ref(rows),
        weight_bytes_ref=weights.model_weight_bytes_ref(rows),
        feature_window_end=previous,
        source_available_at=previous + timedelta(minutes=1),
        input_asof=stamp,
        inference_started_at=stamp,
        inference_completed_at=stamp,
        weights_observed_at=stamp,
        exit_not_before=last.close_ts - timedelta(minutes=15),
        original_basis_gross_ceiling=D("0.005"),
        rows=rows,
    )


def _prepared(metadata=None):
    return weights.prepare_model_paper_weights_input(
        _metadata() if metadata is None else metadata,
        entry_session=us_equity_2026_session(date(2026, 10, 23)).window,
        exit_session=us_equity_2026_session(date(2026, 11, 19)).window,
    )


def _encoded(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")


def _load(payload):
    return weights.load_model_paper_weights_input(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_policy_ref=POLICY,
    )


def _document():
    return json.loads(weights.serialize_model_paper_weights_input(_prepared()))


def _assert_original_slot_caps(value):
    rows = {row.slot: row for row in value.metadata.rows}
    expected = {
        slot for slot, row in rows.items()
        if row.eligibility == "ELIGIBLE_NAS"
        and CEILING * Fraction(row.weight) >= Fraction(1, 10**24)
    }
    assert {target.slot for target in value.targets} == expected
    assert len(value.targets) == len(expected)
    gross = Fraction()
    for target in value.targets:
        row = rows[target.slot]
        assert target.route == row.route
        assert target.research_weight == row.weight
        exposure = Fraction(target.proposal.target_exposure)
        assert 0 < exposure <= CEILING * Fraction(row.weight)
        gross += exposure
    assert gross <= CEILING
    assert gross <= CEILING * sum((Fraction(rows[s].weight) for s in expected), Fraction())
    return gross


def test_full_axis_hash_mask_and_unspent_mass_do_not_enter_legacy_scorer(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("legacy payoff/scorer path entered")

    for name in (
        "_targets", "prepare_model_paper_input", "validate_model_paper_input",
        "load_model_paper_input",
    ):
        monkeypatch.setattr(legacy, name, forbidden)
    value = _prepared()
    rows = value.metadata.rows
    assert tuple(row.slot for row in rows) == tuple(range(100))
    expected_bytes = b"".join(struct.pack("<d", float(row.weight)) for row in rows)
    expected_mask = json.dumps(
        [row.feature_known for row in rows], separators=(",", ":")
    ).encode("ascii")
    assert value.metadata.weight_bytes_ref == "sha256:" + hashlib.sha256(expected_bytes).hexdigest()
    assert value.metadata.feature_mask_ref == "sha256:" + hashlib.sha256(expected_mask).hexdigest()
    assert rows[1].eligibility == "UNSUPPORTED_VENUE"
    assert rows[3].eligibility == "ZERO_WEIGHT"
    assert rows[4].eligibility == "FEATURE_UNAVAILABLE"
    assert _assert_original_slot_caps(value) == CEILING * Fraction(3, 4)
    assert _load(weights.serialize_model_paper_weights_input(value)) == value
    assert value.execution_basis == "gross_limit_cost_not_fees_settlement_or_replay_equivalence"


def test_processing_priority_keeps_all_targets_and_original_slot_ties():
    value = _prepared(_metadata(_rows({0: "0.25", 2: "0.5", 5: "0.25"})))
    _assert_original_slot_caps(value)
    assert [target.slot for target in value.targets] == [2, 0, 5]
    assert [row.slot for row in value.metadata.rows] == list(range(100))


def test_unavailable_route_roundtrip_rejects_known_rebinding_even_with_repaired_mask():
    rows = list(_rows())
    rows[4] = replace(rows[4], route="WAE/UNAVAILABLE")
    value = _prepared(_metadata(tuple(rows)))
    payload = weights.serialize_model_paper_weights_input(value)
    loaded = _load(payload)
    assert loaded == value
    assert tuple(row.slot for row in loaded.metadata.rows) == tuple(range(100))
    assert loaded.metadata.rows[4] == rows[4]
    assert rows[4].weight == 0 and rows[4].feature_known is False
    assert rows[4].eligibility == "FEATURE_UNAVAILABLE"
    assert all(target.slot != 4 and target.proposal.symbol != "WAE" for target in loaded.targets)
    assert _assert_original_slot_caps(loaded) == CEILING * Fraction(3, 4)
    with pytest.raises(ValueError, match="weights_route_invalid"):
        replace(rows[4], feature_known=True)
    document = json.loads(payload)
    document["metadata"]["rows"][4]["feature_known"] = True
    mask = [row["feature_known"] for row in document["metadata"]["rows"]]
    document["metadata"]["feature_mask_ref"] = "sha256:" + hashlib.sha256(
        _encoded(mask)
    ).hexdigest()
    with pytest.raises(ValueError, match="weights_route_invalid"):
        _load(_encoded(document))


def test_rehashed_reordered_axis_and_cross_venue_duplicate_instrument_are_rejected():
    rows = _rows()
    reversed_axis = (rows[1], rows[0], *rows[2:])
    duplicate_instrument = (
        rows[0], replace(rows[1], route=rows[0].route.split("/")[0] + "/NYS"), *rows[2:]
    )
    for changed in (reversed_axis, duplicate_instrument):
        with pytest.raises(ValueError, match="weights_full_axis_invalid"):
            _metadata(changed)


def test_high_precision_same_binary64_cannot_reach_proposal_generation(monkeypatch):
    hidden = D("0.12500000000000000000000000000000000001")
    assert struct.pack("<d", float(hidden)) == struct.pack("<d", 0.125)
    assert hidden > D("0.125")
    with pytest.raises(ValueError, match="weights_not_binary64_canonical"):
        weights.ModelPaperWeightRow(0, "WAA/NAS", True, hidden)

    meta = _metadata()
    original_bytes_ref = meta.weight_bytes_ref
    object.__setattr__(meta.rows[0], "weight", hidden)
    assert weights.model_weight_bytes_ref(meta.rows) == original_bytes_ref

    def forbidden(*args, **kwargs):
        pytest.fail("noncanonical weight reached proposal generation")

    monkeypatch.setattr(weights, "_weight_targets", forbidden)
    with pytest.raises(ValueError, match="weights_not_binary64_canonical"):
        _prepared(meta)


def test_signed_zero_bytes_and_repaired_mask_cannot_splice_old_derived_bindings():
    meta = _metadata()
    rows = list(meta.rows)
    rows[3] = replace(rows[3], weight=D("-0.0"))
    assert rows[3].weight == meta.rows[3].weight
    assert weights.model_weight_bytes_ref(tuple(rows)) != meta.weight_bytes_ref
    with pytest.raises(ValueError, match="weights_bytes_mismatch"):
        replace(meta, rows=tuple(rows))

    document = _document()
    document["metadata"]["rows"][4]["feature_known"] = True
    mask = [row["feature_known"] for row in document["metadata"]["rows"]]
    document["metadata"]["feature_mask_ref"] = "sha256:" + hashlib.sha256(
        _encoded(mask)
    ).hexdigest()
    with pytest.raises(ValueError, match="weights_payload_not_canonical_or_derived"):
        _load(_encoded(document))


def test_tiny_oversum_only_trims_and_material_oversum_never_normalizes():
    value = _prepared(_metadata(_rows({0: "0.5", 2: "0.5000000000005"})))
    assert sum((Fraction(row.weight) for row in value.metadata.rows), Fraction()) > 1
    assert _assert_original_slot_caps(value) <= CEILING
    with pytest.raises(ValueError, match="weights_unit_mass_invalid"):
        _metadata(_rows({0: "0.5", 2: "0.500000000002"}))


def test_decimal_exponent_boundaries_reject_equal_value_scale_expansion():
    zero = weights.ModelPaperWeightRow(4, "WAE/NAS", False, D("0e-324"))
    assert zero.weight == 0
    for weight in (D("0e-325"), D("0e+1")):
        with pytest.raises(ValueError, match="weights_value_invalid"):
            replace(zero, weight=weight)
    meta = _metadata()
    boundary = D((0, (5,) + (0,) * 21, -24))
    too_fine = D((0, (5,) + (0,) * 22, -25))
    assert boundary == too_fine == meta.original_basis_gross_ceiling
    assert replace(meta, original_basis_gross_ceiling=boundary).rows == meta.rows
    with pytest.raises(ValueError, match="weights_cohort_ceiling_invalid"):
        replace(meta, original_basis_gross_ceiling=too_fine)


def test_subquantum_weights_stay_bound_and_unspent_without_renormalization():
    baseline = _prepared()
    rows = list(_rows())
    rows[6] = replace(rows[6], weight=D("5e-324"))
    rows[7] = replace(rows[7], weight=D("1e-22"))
    rows[8] = replace(rows[8], weight=D("2e-22"))
    assert float(rows[6].weight) > 0
    assert rows[6].eligibility == "ELIGIBLE_NAS"
    value = _prepared(_metadata(tuple(rows)))
    quantum = Fraction(1, 10**24)
    gross = _assert_original_slot_caps(value)
    targets = {target.slot: target for target in value.targets}
    assert set(targets) == {0, 2, 5, 8}
    assert Fraction(targets[8].proposal.target_exposure) == quantum
    for target in baseline.targets:
        assert targets[target.slot].proposal.target_exposure == target.proposal.target_exposure
        assert targets[target.slot].research_weight == target.research_weight
    assert gross == _assert_original_slot_caps(baseline) + quantum
    assert gross < CEILING * value.metadata.eligible_weight
    assert value.metadata.rows == tuple(rows)
    binary64 = b"".join(struct.pack("<d", float(row.weight)) for row in rows)
    assert value.metadata.weight_bytes_ref == "sha256:" + hashlib.sha256(binary64).hexdigest()
    assert value.metadata.weight_bytes_ref != baseline.metadata.weight_bytes_ref
    loaded = _load(weights.serialize_model_paper_weights_input(value))
    assert loaded == value
    assert loaded.metadata.rows[6].weight == D("5e-324")
    assert tuple(row.slot for row in loaded.metadata.rows) == tuple(range(100))


def test_decimal_precision_rounding_and_traps_cannot_change_proposals_or_hashes():
    meta = _metadata(_rows({0: "0.3333333333333333", 2: "0.3333333333333333",
                            5: "0.3333333333333334"}))
    normal = _prepared(meta)
    canonical = weights.serialize_model_paper_weights_input(normal)
    for precision, rounding in ((2, ROUND_UP), (60, ROUND_FLOOR)):
        with localcontext() as context:
            context.prec = precision
            context.rounding = rounding
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            changed = _prepared(meta)
            assert changed == normal
            assert weights.serialize_model_paper_weights_input(changed) == canonical
            assert _load(canonical) == normal
            _assert_original_slot_caps(changed)


def test_nested_duplicate_escaped_keys_and_nonfinite_json_are_rejected():
    raw = weights.serialize_model_paper_weights_input(_prepared())
    duplicate_weight = raw.replace(
        b'"weight":"0.125"', b'"weight":"0.125","weight":"0.125"', 1
    )
    escaped_duplicate = raw.replace(
        b'"weight":"0.125"', b'"\\u0077eight":"0.125","weight":"0.125"', 1
    )
    for payload in (duplicate_weight, escaped_duplicate):
        assert payload != raw
        with pytest.raises(ValueError, match="model_duplicate_field"):
            _load(payload)
    for token in (b"NaN", b"Infinity", b"-Infinity"):
        payload = raw.replace(b'"weight":"0.125"', b'"weight":' + token, 1)
        with pytest.raises(ValueError, match="weights_nonfinite"):
            _load(payload)
    document = _document()
    document["metadata"]["rows"][0]["weight"] = "NaN"
    with pytest.raises(ValueError, match="weights_value_invalid"):
        _load(_encoded(document))


def test_rank_score_and_nested_execution_instructions_cannot_enter_weight_abi():
    for location, field in (("row", "rank"), ("metadata", "score"),
                            ("top", "rank"), ("proposal", "quantity")):
        document = _document()
        target = {
            "row": document["metadata"]["rows"][0],
            "metadata": document["metadata"],
            "top": document,
            "proposal": document["targets"][0]["proposal"],
        }[location]
        target[field] = "1"
        with pytest.raises(ValueError):
            _load(_encoded(document))


def test_causal_clock_equivalent_offset_and_nonofficial_session_are_rejected():
    meta = _metadata()
    with pytest.raises(ValueError, match="weights_causal_clocks_invalid"):
        replace(meta, inference_completed_at=meta.inference_started_at - timedelta(seconds=1))
    document = _document()
    document["metadata"]["weights_observed_at"] = meta.weights_observed_at.astimezone(
        timezone(timedelta(hours=9))
    ).isoformat()
    with pytest.raises(ValueError, match="weights_payload_not_canonical_or_derived"):
        _load(_encoded(document))
    for session, field in (("entry_session", "open_ts"), ("exit_session", "close_ts")):
        value = _prepared()
        window = getattr(value, session)
        with pytest.raises(ValueError, match="model_20session_horizon_invalid"):
            replace(value, **{session: replace(window, **{field: getattr(window, field)
                                                          + timedelta(seconds=1)})})
    with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
        _prepared(replace(meta, exit_not_before=meta.exit_not_before + timedelta(seconds=1)))


def test_derived_targets_and_references_are_recomputed_after_outer_hash_repair():
    for mutation in ("duplicate_target", "receipt_binding", "manifest", "output", "policy"):
        document = _document()
        if mutation == "duplicate_target":
            document["targets"].append(document["targets"][0])
        elif mutation == "receipt_binding":
            document["targets"][0]["receipt"]["instrument_binding_ref"] = "ref:" + "d" * 64
        else:
            field = {"manifest": "input_manifest_ref", "output": "full_output_ref",
                     "policy": "policy_ref"}[mutation]
            document["metadata"][field] = OTHER_PIN
        with pytest.raises(ValueError):
            _load(_encoded(document))


def test_frozen_mutation_and_hostile_properties_fail_before_trusting_targets():
    value = _prepared()
    with pytest.raises(FrozenInstanceError):
        value.targets = ()
    first = value.targets[0]
    changed = replace(first, proposal=replace(first.proposal, target_exposure=D(".005")))
    object.__setattr__(value, "targets", (changed, *value.targets[1:]))
    with pytest.raises(ValueError, match="weights_target_composition_changed"):
        weights.validate_model_paper_weights_input(value)
    with pytest.raises(ValueError, match="weights_payload_not_canonical_or_derived"):
        _load(weights.serialize_model_paper_weights_input(value))

    class HostileRow:
        @property
        def weight(self):
            pytest.fail("untrusted row property evaluated before exact-type rejection")

    meta = _metadata()
    with pytest.raises(ValueError, match="weights_row_type_invalid"):
        replace(meta, rows=(HostileRow(), *meta.rows[1:]))
