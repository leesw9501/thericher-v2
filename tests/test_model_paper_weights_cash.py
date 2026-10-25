"""Explicit nonbroker cash coordinates; invented inputs, no runtime authority."""

import copy
import hashlib
import json
import struct
from dataclasses import asdict, fields, replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from test_model_paper_weights_h5 import POLICY, _encoded, _metadata, _prepared, _window
from thericher_v2.research import model_paper_proposal as legacy
from thericher_v2.research import model_paper_weights as weights
from thericher_v2.research.model_paper_horizon import MODEL_PAPER_5_SESSION_PROFILE

D = Decimal
PROFILE = weights.MODEL_PAPER_WEIGHTS_CASH_5_SESSION_PROFILE


def _rows(q="0.5", cash="0.5"):
    return tuple(
        weights.ModelPaperWeightRow(i, route, True, D(weight))
        for i, (route, weight) in enumerate(
            (("SPY/AMS", "0.0"), ("QQQ/NAS", q), ("IWM/AMS", "0.0"), ("CASH", cash))
        )
    )


def _cash_input(q="0.5", cash="0.5", *, rows=None, profile=PROFILE):
    first, last = _window(date(2026, 10, 26)), _window(date(2026, 10, 30))
    return weights.prepare_model_paper_weights_input(
        _metadata(first, last, _rows(q, cash) if rows is None else rows),
        entry_session=first, exit_session=last, profile=profile,
    )


def _load(payload):
    return weights.load_model_paper_weights_input(
        payload, expected_sha256=hashlib.sha256(payload).hexdigest(), expected_policy_ref=POLICY
    )


@pytest.mark.parametrize(
    "q,cash",
    [("0.0", "1.0"), ("0.5", "0.5"), ("1.0", "0.0"),
     ("0.608380138874054", "0.39161986112594604")],
)
def test_cash_roundtrip_preserves_full_axis_binary64_and_original_slot_ceiling(q, cash):
    value = _cash_input(q, cash)
    payload = weights.serialize_model_paper_weights_input(value)
    assert _load(payload) == value
    assert weights.serialize_model_paper_weights_input(_load(payload)) == payload
    assert value.profile == PROFILE
    assert value.metadata.rows == _rows(q, cash)
    assert value.metadata.rows[3].eligibility == "CASH_ALLOCATION"
    assert value.metadata.cash_weight == Fraction(D(cash))
    assert value.metadata.eligible_weight == Fraction(D(q))
    assert value.metadata.skipped_weight == 0
    assert value.metadata.original_basis_gross_ceiling == D(".005")
    raw = b"".join(struct.pack("<d", float(r.weight)) for r in value.metadata.rows)
    assert value.metadata.weight_bytes_ref == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert value.metadata.feature_mask_ref == weights.model_weight_mask_ref(value.metadata.rows)
    assert value.metadata.exit_not_before == value.exit_session.close_ts - timedelta(minutes=15)
    if D(q) == 0:
        assert value.targets == ()  # Typed inert allocation, not runtime no-intent support.
    else:
        assert len(value.targets) == 1
        target = value.targets[0]
        assert target.slot == 1 and target.route == "QQQ/NAS"
        assert target.research_weight == D(q)
        cap = Fraction(".005") * Fraction(D(q))
        assert 0 <= cap - Fraction(target.proposal.target_exposure) < Fraction(1, 10**24)
        assert target.proposal.target_exposure <= D(".005")
        assert target.proposal.symbol == "QQQ"


def test_cash_is_not_a_broker_route_or_serialized_dataclass_extension():
    value = _cash_input()
    assert legacy._ROUTE.fullmatch("CASH") is None
    assert "cash_weight" not in asdict(value.metadata)
    assert [f.name for f in fields(weights.ModelPaperWeightRow)] == [
        "slot", "route", "feature_known", "weight"
    ]
    assert [f.name for f in fields(weights.ModelPaperWeightsInput)] == [
        "metadata", "targets", "entry_session", "exit_session", "profile",
        "weight_units", "execution_basis",
    ]
    assert set(json.loads(weights.serialize_model_paper_weights_input(value))["metadata"]) == {
        f.name for f in fields(weights.ModelPaperWeightsMetadata)
    }
    assert weights.model_paper_weights_horizon_profile(PROFILE) == MODEL_PAPER_5_SESSION_PROFILE


@pytest.mark.parametrize("profile", [
    weights.MODEL_PAPER_WEIGHTS_PROFILE, weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
])
@pytest.mark.parametrize("q,cash", [("0.5", "0.5"), ("1.0", "0.0")])
def test_old_profiles_reject_literal_cash_including_zero_cash(profile, q, cash):
    with pytest.raises(ValueError, match="weights_cash_profile_invalid"):
        _cash_input(q, cash, profile=profile)
    value = _cash_input(q, cash)
    with pytest.raises(ValueError, match="weights_cash_profile_invalid"):
        replace(value, profile=profile)
    document = json.loads(weights.serialize_model_paper_weights_input(value))
    document["profile"] = profile
    with pytest.raises(ValueError, match="weights_cash_profile_invalid"):
        _load(_encoded(document))


@pytest.mark.parametrize("route,known", [
    ("CASH/NAS", True), ("CASH/AMS", True), ("CASH/UNAVAILABLE", False),
])
def test_new_profile_requires_exact_nonbroker_coordinate_not_fake_cash_stock(route, known):
    rows = list(_rows("1.0", "0.0"))
    rows[-1] = replace(rows[-1], route=route, feature_known=known)
    with pytest.raises(ValueError, match="weights_cash_axis_invalid"):
        _cash_input(rows=tuple(rows))


@pytest.mark.parametrize("route", ["cash", "CASH/", "CASH/USD", " CASH", "CASH "])
def test_malformed_cash_route_rejected(route):
    with pytest.raises(ValueError, match="weights_route_invalid"):
        weights.ModelPaperWeightRow(0, route, True, D("1.0"))


@pytest.mark.parametrize("cash", ["0.0", "1.0"])
def test_cash_knownness_cannot_be_false_even_for_zero(cash):
    with pytest.raises(ValueError, match="weights_cash_knownness_invalid"):
        weights.ModelPaperWeightRow(0, "CASH", False, D(cash))


@pytest.mark.parametrize("weight", [D("NaN"), D("Infinity"), D("-.1"), D("1.1"),
                                    D("1E+1"), D("1E-325"), 0.5])
def test_invalid_cash_values_rejected(weight):
    with pytest.raises(ValueError, match="weights_value_invalid"):
        weights.ModelPaperWeightRow(0, "CASH", True, weight)


def test_hidden_decimal_cash_precision_does_not_share_binary64_authority():
    with pytest.raises(ValueError, match="weights_not_binary64_canonical"):
        weights.ModelPaperWeightRow(0, "CASH", True, D("0.5000000000000000000001"))


def test_cash_mass_mismatch_never_normalizes():
    with pytest.raises(ValueError, match="weights_unit_mass_invalid"):
        _cash_input("0.5", "0.7")


@pytest.mark.parametrize("change", ["absent", "middle", "duplicate", "gap", "only_cash"])
def test_cash_axis_must_be_unique_terminal_and_preserve_original_slots(change):
    rows = list(_rows())
    if change == "absent":
        rows = [replace(r, weight=D("1.0") if r.slot == 1 else D("0.0")) for r in rows[:-1]]
    elif change == "middle":
        rows[2], rows[3] = replace(rows[3], slot=2), replace(rows[2], slot=3)
    elif change == "duplicate":
        rows[2] = replace(rows[2], route="CASH")
    elif change == "gap":
        rows[3] = replace(rows[3], slot=4)
    else:
        rows = [weights.ModelPaperWeightRow(0, "CASH", True, D("1.0"))]
    with pytest.raises(ValueError, match="weights_(cash_axis|full_axis)_invalid"):
        _cash_input(rows=tuple(rows))


def test_unsupported_stock_weight_and_cash_never_redistribute_into_qqq():
    rows = list(_rows("0.25", "0.5"))
    rows[0] = replace(rows[0], weight=D("0.25"))
    value = _cash_input(rows=tuple(rows))
    assert value.metadata.skipped_weight == Fraction(1, 4)
    assert value.metadata.cash_weight == Fraction(1, 2)
    assert len(value.targets) == 1
    assert value.targets[0].proposal.target_exposure == D(".00125")


@pytest.mark.parametrize(
    "change", ["cash_weight", "cash_mask", "cash_route", "target", "extra_field"]
)
def test_rehashed_tampering_cannot_keep_old_derived_targets(change):
    document = json.loads(weights.serialize_model_paper_weights_input(_cash_input()))
    if change == "cash_weight":
        document["metadata"]["rows"][3]["weight"] = "0.6"
    elif change == "cash_mask":
        document["metadata"]["rows"][3]["feature_known"] = False
    elif change == "cash_route":
        document["metadata"]["rows"][3]["route"] = "CASH/NAS"
    elif change == "target":
        document["targets"][0]["proposal"]["target_exposure"] = "0.005"
    else:
        document["metadata"]["cash_weight"] = "0.5"
    with pytest.raises(ValueError):
        _load(_encoded(document))


def test_forged_dataclass_cash_mask_revalidated_before_target_build(monkeypatch):
    value = copy.deepcopy(_cash_input())
    object.__setattr__(value.metadata.rows[-1], "feature_known", False)

    def forbidden(*_args):
        pytest.fail("invalid_cash_reached_target_builder")

    monkeypatch.setattr(weights, "_weight_targets", forbidden)
    with pytest.raises(ValueError, match="weights_cash_knownness_invalid"):
        weights.validate_model_paper_weights_input(value)


def test_cash_generation_is_independent_of_local_decimal_precision():
    expected = weights.serialize_model_paper_weights_input(_cash_input())
    with localcontext() as context:
        context.prec = 4
        assert weights.serialize_model_paper_weights_input(_cash_input()) == expected


def test_original_h5_bytes_policy_and_proposal_ids_unchanged():
    value = _prepared()
    payload = weights.serialize_model_paper_weights_input(value)
    assert len(payload) == 4844
    assert hashlib.sha256(payload).hexdigest() == (
        "f7eb678f452f299a5ea1700d769f6955c109642d961ec9467de625a17a51e25d"
    )
    prefix = "model-weights-nas-8505918a77aff5b6050d9b4b82638f46fbe2c176d648623e8ea7041324f0295a-"
    assert [t.proposal.proposal_id for t in value.targets] == [prefix + "1", prefix + "0"]
    assert value.policy_ref == POLICY
    assert value.metadata.cash_weight == 0
    assert _load(payload) == value
