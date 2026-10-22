"""Invented weights only; no broker, credentials, model, market or filesystem reads."""

import hashlib
import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import model_paper_proposal as payoff
from thericher_v2.research.model_paper_weights import (
    EXECUTION_BASIS,
    MODEL_PAPER_WEIGHTS_PROFILE,
    WEIGHT_UNITS,
    ModelPaperWeightRow,
    ModelPaperWeightsInput,
    ModelPaperWeightsMetadata,
    load_model_paper_weights_input,
    model_weight_bytes_ref,
    model_weight_mask_ref,
    prepare_model_paper_weights_input,
    serialize_model_paper_weights_input,
)

D = Decimal
PIN = "sha256:" + "1" * 64
POLICY = "sha256:" + "2" * 64


def metadata(rows=None, **changes):
    first = us_equity_2026_session(date(2026, 10, 23)).window
    previous = us_equity_2026_session(date(2026, 10, 22)).window.close_ts
    last = us_equity_2026_session(date(2026, 11, 19)).window
    stamp = first.open_ts - timedelta(hours=1)
    if rows is None:
        rows = (
            ModelPaperWeightRow(0, "MSFT/NAS", True, D(".25")),
            ModelPaperWeightRow(1, "AAPL/NAS", True, D(".5")),
            ModelPaperWeightRow(2, "JPM/NYS", True, D(".25")),
            ModelPaperWeightRow(3, "AMZN/NAS", False, D(0)),
        )
    value = ModelPaperWeightsMetadata(
        "invented-joint-not-a-winner",
        "invented-raw-factor-context",
        PIN,
        PIN,
        PIN,
        PIN,
        PIN,
        POLICY,
        PIN,
        model_weight_mask_ref(rows),
        model_weight_bytes_ref(rows),
        previous,
        previous + timedelta(minutes=1),
        stamp,
        stamp,
        stamp,
        stamp,
        last.close_ts - timedelta(minutes=15),
        D(".005"),
        rows,
    )
    return replace(value, **changes)


def prepared(meta=None):
    return prepare_model_paper_weights_input(
        metadata() if meta is None else meta,
        entry_session=us_equity_2026_session(date(2026, 10, 23)).window,
        exit_session=us_equity_2026_session(date(2026, 11, 19)).window,
    )


def load(payload):
    return load_model_paper_weights_input(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_policy_ref=POLICY,
    )


def encoded(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def test_roundtrip_preserves_full_axis_original_weights_and_gross_units():
    value = prepared()
    raw = serialize_model_paper_weights_input(value)
    assert load(raw) == value
    assert type(value) is ModelPaperWeightsInput and not isinstance(value, payoff.ModelPaperInput)
    assert value.profile == MODEL_PAPER_WEIGHTS_PROFILE
    assert value.weight_units == WEIGHT_UNITS
    assert value.execution_basis == EXECUTION_BASIS
    assert value.metadata.eligible_weight == Fraction(3, 4)
    assert value.metadata.skipped_weight == Fraction(1, 4)
    assert [t.slot for t in value.targets] == [1, 0]
    assert [t.proposal.target_exposure for t in value.targets] == [D(".0025"), D(".00125")]
    assert sum(t.proposal.target_exposure for t in value.targets) == D(".00375")
    assert value.metadata.rows[3].eligibility == "FEATURE_UNAVAILABLE"
    assert not any(
        {"score", "rank", "quantity"} & set(r) for r in json.loads(raw)["metadata"]["rows"]
    )


def test_no_payoff_scorer_or_legacy_bridge_is_called(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("payoff path entered")

    monkeypatch.setattr(payoff, "_targets", forbidden)
    monkeypatch.setattr(payoff, "prepare_model_paper_input", forbidden)
    monkeypatch.setattr(payoff, "validate_model_paper_input", forbidden)
    monkeypatch.setattr(payoff, "load_model_paper_input", forbidden)
    value = prepared()
    assert load(serialize_model_paper_weights_input(value)) == value


@pytest.mark.parametrize("weight", [D("-0.1"), D("1.1"), D("NaN"), D("Infinity"), 0.25])
def test_bad_weights_rejected(weight):
    with pytest.raises(ValueError, match="weights_value_invalid"):
        ModelPaperWeightRow(0, "MSFT/NAS", True, weight)


@pytest.mark.parametrize("slot", [True, -1, 512, "0"])
def test_slot_type_and_range(slot):
    with pytest.raises(ValueError, match="weights_slot_invalid"):
        ModelPaperWeightRow(slot, "MSFT/NAS", True, D(1))


def test_unavailable_feature_cannot_have_positive_weight():
    with pytest.raises(ValueError, match="weights_unknown_positive"):
        ModelPaperWeightRow(0, "MSFT/NAS", False, D(".2"))


def test_unknown_axis_preserves_symbol_without_inventing_a_venue():
    original = metadata()
    rows = (*original.rows[:3], ModelPaperWeightRow(3, "AMZN/UNAVAILABLE", False, D(0)))
    value = prepared(replace(original, rows=rows))
    assert load(serialize_model_paper_weights_input(value)) == value
    assert [t.slot for t in value.targets] == [1, 0]
    with pytest.raises(ValueError, match="weights_route_invalid"):
        ModelPaperWeightRow(3, "AMZN/UNAVAILABLE", True, D(0))


def test_extra_decimal_precision_cannot_hide_behind_same_float_hash():
    with pytest.raises(ValueError, match="weights_not_binary64_canonical"):
        ModelPaperWeightRow(0, "MSFT/NAS", True, D(".250000000000000000001"))


def test_zero_exponent_and_cohort_scale_are_bounded_before_fraction_arithmetic():
    with pytest.raises(ValueError, match="weights_value_invalid"):
        ModelPaperWeightRow(0, "MSFT/NAS", False, D("0e-999999"))
    with pytest.raises(ValueError, match="weights_cohort_ceiling_invalid"):
        metadata(original_basis_gross_ceiling=D("1e-999999"))


@pytest.mark.parametrize(
    "replacement",
    [
        (ModelPaperWeightRow(1, "MSFT/NAS", True, D(1)),),
        (
            ModelPaperWeightRow(0, "MSFT/NAS", True, D(".5")),
            ModelPaperWeightRow(1, "MSFT/NAS", True, D(".5")),
        ),
    ],
)
def test_reordered_axis_or_duplicate_symbol(replacement):
    with pytest.raises(ValueError, match="weights_full_axis_invalid"):
        metadata(replacement)


@pytest.mark.parametrize("total", [D(".9"), D("1.00000000001")])
def test_unit_mass_not_rescaled(total):
    rows = (
        ModelPaperWeightRow(0, "MSFT/NAS", True, total / 2),
        ModelPaperWeightRow(1, "AAPL/NAS", True, total / 2),
    )
    with pytest.raises(ValueError, match="weights_unit_mass_invalid"):
        metadata(rows)


@pytest.mark.parametrize(
    "field, reason",
    [
        ("feature_mask_ref", "weights_mask_mismatch"),
        ("weight_bytes_ref", "weights_bytes_mismatch"),
    ],
)
def test_exact_mask_and_binary64_hashes(field, reason):
    with pytest.raises(ValueError, match=reason):
        metadata(**{field: "sha256:" + "3" * 64})


def test_per_slot_floor_and_roundoff_cap_ignore_decimal_context():
    rows = (
        ModelPaperWeightRow(0, "MSFT/NAS", True, D(".4")),
        ModelPaperWeightRow(1, "AAPL/NAS", True, D(".3")),
        ModelPaperWeightRow(2, "NVDA/NAS", True, D(".30000000000001")),
    )
    meta = metadata(rows)
    normal = prepared(meta)
    with localcontext() as ctx:
        ctx.prec = 3
        assert prepared(meta) == normal
    assert sum(map(lambda t: Fraction(t.proposal.target_exposure), normal.targets)) <= Fraction(
        ".005"
    )
    targets = {target.slot: target for target in normal.targets}
    for row in rows:
        target = targets[row.slot]
        assert Fraction(target.proposal.target_exposure) <= Fraction(".005") * Fraction(row.weight)


def test_wrong_horizon_or_late_weights_cannot_be_prepared():
    value = prepared()
    with pytest.raises(ValueError):
        replace(value, exit_session=us_equity_2026_session(date(2026, 11, 18)).window)
    with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
        prepared(metadata(weights_observed_at=value.entry_session.open_ts))


@pytest.mark.parametrize(
    "field, replacement",
    [
        ("schema", payoff.MODEL_PAPER_SCHEMA),
        ("profile", payoff.MODEL_PAPER_PROFILE),
        ("weight_units", "expected_return"),
        ("execution_basis", "net_profit"),
    ],
)
def test_incompatible_abi_is_rejected(field, replacement):
    raw = json.loads(serialize_model_paper_weights_input(prepared()))
    raw[field] = replacement
    with pytest.raises(ValueError, match="weights_input_schema_invalid"):
        load(encoded(raw))


def test_changed_derived_target_cannot_be_trusted_even_with_new_payload_hash():
    raw = json.loads(serialize_model_paper_weights_input(prepared()))
    raw["targets"][0]["proposal"]["target_exposure"] = ".005"
    with pytest.raises(ValueError, match="weights_payload_not_canonical_or_derived"):
        load(encoded(raw))


def test_score_rank_and_unknown_fields_do_not_enter_weight_row():
    raw = json.loads(serialize_model_paper_weights_input(prepared()))
    raw["metadata"]["rows"][0]["score"] = "1"
    with pytest.raises(ValueError, match="weights_row_fields_invalid"):
        load(encoded(raw))


def test_duplicate_json_fields_nonfinite_and_noncanonical_payload_rejected():
    value = prepared()
    raw = serialize_model_paper_weights_input(value)
    duplicate = b'{"schema":"x",' + raw[1:]
    with pytest.raises(ValueError, match="model_duplicate_field"):
        load(duplicate)
    with pytest.raises(ValueError, match="weights_nonfinite"):
        load(b'{"schema":NaN}')
    with pytest.raises(ValueError, match="weights_payload_not_canonical_or_derived"):
        load(json.dumps(json.loads(raw), indent=2).encode())


def test_input_pin_and_policy_identity():
    raw = serialize_model_paper_weights_input(prepared())
    with pytest.raises(ValueError, match="weights_input_pin_mismatch"):
        load_model_paper_weights_input(raw, expected_sha256="0" * 64, expected_policy_ref=POLICY)
    with pytest.raises(ValueError, match="weights_policy_pin_mismatch"):
        load_model_paper_weights_input(
            raw,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            expected_policy_ref=PIN,
        )
