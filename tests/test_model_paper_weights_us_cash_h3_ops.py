"""Invented full-axis operational weights; run only after atomic Horizon integration."""

import copy
import hashlib
import json
import struct
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from test_model_paper_weights_h5 import POLICY, _encoded, _metadata, _prepared, _window
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research import model_paper_weights as weights
from thericher_v2.research.model_paper_horizon import (
    MODEL_PAPER_3_SESSION_PROFILE,
    prior_official_session_close,
)

D = Decimal
PROFILE = weights.MODEL_PAPER_WEIGHTS_US_CASH_3_SESSION_OPS_PROFILE
ROUTES = (
    "AAPL/NAS", "AMD/NAS", "AMZN/NAS", "GOOGL/NAS", "META/NAS", "MSFT/NAS",
    "NVDA/NAS", "TSLA/NAS", "JPM/NYS", "JNJ/NYS", "XOM/NYS", "PG/NYS",
    "KO/NYS", "HD/NYS", "V/NYS", "DIS/NYS", "UNH/NYS", "CASH",
)


def _rows(selected=(0, 8, 9, 16), *, unknown=()):
    # CASH is supplied explicitly. No call to the production residual helper.
    return tuple(
        weights.ModelPaperWeightRow(
            i, route, i not in unknown,
            D(".25") if i in selected else D(1) - D(".25") * len(selected)
            if i == 17 else D(0),
        )
        for i, route in enumerate(ROUTES)
    )


def metadata(rows=None, first=date(2026, 11, 9), last=date(2026, 11, 11), **changes):
    """Invented metadata for Parent's atomic codec/session/native tests."""
    return replace(
        _metadata(_window(first), _window(last), _rows() if rows is None else rows), **changes
    )


def make_input(rows=None, first=date(2026, 11, 9), last=date(2026, 11, 11), **changes):
    """Build a real typed full18 fixture; needs the integrated Horizon dependency."""
    return weights.prepare_model_paper_weights_input(
        metadata(rows, first, last, **changes), entry_session=_window(first),
        exit_session=_window(last), profile=PROFILE,
    )


_prepare = make_input


def _load(payload, **changes):
    arguments = dict(
        expected_sha256=hashlib.sha256(payload).hexdigest(), expected_policy_ref=POLICY,
    )
    return weights.load_model_paper_weights_input(payload, **dict(arguments, **changes))


def _replace_rows(metadata, rows):
    return replace(
        metadata, rows=rows, feature_mask_ref=weights.model_weight_mask_ref(rows),
        weight_bytes_ref=weights.model_weight_bytes_ref(rows),
    )


def test_explicit_profile_schema_basis_and_existing_types_only():
    value = _prepare()
    assert PROFILE == "model-weights-us-cash-inclusive3-open5-preclose15-2026-v1"
    assert weights.model_paper_weights_horizon_profile(PROFILE) == MODEL_PAPER_3_SESSION_PROFILE
    assert MODEL_PAPER_3_SESSION_PROFILE == "model-proposal-us-inclusive3-2026-v1"
    assert type(value) is weights.ModelPaperWeightsInput
    assert type(value.metadata) is weights.ModelPaperWeightsMetadata
    assert value.execution_basis == weights.US_CASH_H3_OPS_EXECUTION_BASIS
    assert "NON_PARITY_research_first_OPEN_to_third_session_CLOSE" in value.execution_basis
    assert "not_benchmark_fills" in value.execution_basis
    assert [f.name for f in fields(value)] == [
        "metadata", "targets", "entry_session", "exit_session", "profile",
        "weight_units", "execution_basis",
    ]
    assert weights.MODEL_PAPER_US_CASH_H3_OPS_ROUTES == ROUTES


def test_real_weights_producer_serializer_parser_to_typed_target_roundtrip():
    value = _prepare()
    payload = weights.serialize_model_paper_weights_input(value)
    restored = _load(payload)
    assert restored == value
    assert weights.serialize_model_paper_weights_input(restored) == payload
    assert restored.metadata.rows == _rows()
    assert len(restored.metadata.rows) == 18
    assert restored.input_ref == "sha256:" + hashlib.sha256(payload).hexdigest()
    assert [t.slot for t in restored.targets] == [0, 8, 9, 16]
    assert [t.route for t in restored.targets] == [ROUTES[i] for i in (0, 8, 9, 16)]
    for target in restored.targets:
        assert type(target) is weights.ModelPaperTarget
        assert target.research_weight == D(".25")
        assert target.proposal.target_exposure == D(".00125")
        assert target.proposal.valid_until == restored.entry_session.open_ts + timedelta(minutes=5)
        assert target.proposal.decided_at == restored.metadata.weights_observed_at
        assert target.receipt is not None
    assert restored.metadata.eligible_weight_for_profile(PROFILE) == 1
    assert restored.metadata.skipped_weight_for_profile(PROFILE) == 0
    assert restored.metadata.cash_weight == 0


@pytest.mark.parametrize("slot", range(17))
def test_every_exact_nas_nys_route_can_be_selected_without_relabel_or_renormalization(slot):
    value = _prepare(_rows((slot,)))
    restored = _load(weights.serialize_model_paper_weights_input(value))
    assert len(restored.targets) == 1
    target = restored.targets[0]
    assert target.slot == slot and target.route == ROUTES[slot]
    assert target.proposal.symbol == ROUTES[slot].split("/")[0]
    assert target.research_weight == D(".25")
    assert target.proposal.target_exposure == D(".00125")
    assert restored.metadata.cash_weight == Fraction(3, 4)
    assert restored.metadata.rows[slot].eligibility_for_profile(PROFILE) == "ELIGIBLE_US"


def test_all_cash_and_missing_zero_features_are_valid_without_any_target_or_rescue():
    rows = _rows((), unknown=tuple(range(17)))
    value = _prepare(rows)
    restored = _load(weights.serialize_model_paper_weights_input(value))
    assert restored.metadata.rows == rows and restored.targets == ()
    assert restored.metadata.cash_weight == 1
    assert restored.metadata.eligible_weight_for_profile(PROFILE) == 0
    assert all(not r.feature_known and r.weight == 0 for r in restored.metadata.rows[:17])
    assert restored.metadata.rows[17].route == "CASH"
    assert restored.metadata.rows[17].feature_known


def test_no_topk_or_renorm_all17_positive_keep_original_amount_and_cash():
    rows = tuple(
        weights.ModelPaperWeightRow(i, route, True, D(".03125") if i < 17 else D(".46875"))
        for i, route in enumerate(ROUTES)
    )
    value = _prepare(rows)
    assert len(value.targets) == 17
    assert [t.slot for t in value.targets] == list(range(17))
    assert all(t.proposal.target_exposure == D(".00015625") for t in value.targets)
    assert sum(Fraction(t.proposal.target_exposure) for t in value.targets) == Fraction(".00265625")
    assert value.metadata.rows == rows and value.metadata.cash_weight == Fraction(".46875")
    with localcontext() as context:
        context.prec = 4
        assert _prepare(rows) == value


def test_exact_rational_mass_is_not_naive_float_summation_order():
    rows = tuple(
        weights.ModelPaperWeightRow(
            i, route, True, D(".1") if i < 5 else D(".5") if i == 17 else D(0),
        )
        for i, route in enumerate(ROUTES)
    )
    floats = [float(row.weight) for row in rows]
    def naive_sum(values):
        total = 0.0
        for value in values:
            total += value
        return total

    assert naive_sum(floats) != naive_sum(reversed(floats))
    assert sum((Fraction(row.weight) for row in rows), Fraction()) == 1
    value = _prepare(rows)
    assert value.metadata.rows == rows and value.metadata.cash_weight == Fraction(1, 2)
    assert _load(weights.serialize_model_paper_weights_input(value)) == value


@pytest.mark.parametrize("first,last,open_hour,close_hour", [
    (date(2026, 11, 9), date(2026, 11, 11), 14, 21),
    (date(2026, 9, 8), date(2026, 9, 10), 13, 20),
    (date(2026, 11, 24), date(2026, 11, 27), 14, 18),
    (date(2026, 10, 30), date(2026, 11, 3), 13, 21),
    (date(2026, 3, 6), date(2026, 3, 10), 14, 20),
])
def test_exact_inclusive_three_official_sessions_dst_holiday_and_halfday(
    first, last, open_hour, close_hour,
):
    value = _prepare(first=first, last=last)
    bands = weights.model_paper_us_cash_h3_ops_window(value)
    assert value.entry_session.open_ts.hour == open_hour
    assert value.exit_session.close_ts.hour == close_hour
    assert value.metadata.feature_window_end == prior_official_session_close(value.entry_session)
    assert bands.entry_start == value.entry_session.open_ts
    assert bands.entry_end == value.entry_session.open_ts + timedelta(minutes=5)
    assert bands.exit_start == value.exit_session.close_ts - timedelta(minutes=15)
    assert bands.exit_end == value.exit_session.close_ts
    assert value.metadata.exit_not_before == bands.exit_start
    assert bands.entry_start < bands.entry_end < bands.exit_start < bands.exit_end
    assert _load(weights.serialize_model_paper_weights_input(value)) == value


def test_later_owned_exit_window_does_not_retag_original_entry_or_horizon():
    value = _prepare()
    later = _window(date(2026, 11, 12))
    window = weights.model_paper_us_cash_h3_ops_window(value, operational_session=later)
    assert window.exit_start == later.open_ts and window.exit_end == later.close_ts
    assert window.entry_end == value.entry_session.open_ts + timedelta(minutes=5)
    assert value.exit_session == _window(date(2026, 11, 11))
    assert value.metadata.exit_not_before == value.exit_session.close_ts - timedelta(minutes=15)
    with pytest.raises(ValueError, match="weights_sessions_invalid"):
        weights.model_paper_us_cash_h3_ops_window(value, operational_session=value.entry_session)
    fake = SessionWindow(later.open_ts, later.close_ts + timedelta(minutes=1))
    with pytest.raises(ValueError, match="weights_sessions_invalid"):
        weights.model_paper_us_cash_h3_ops_window(value, operational_session=fake)


@pytest.mark.parametrize("last", [date(2026, 11, 10), date(2026, 11, 12), date(2026, 11, 13)])
def test_two_four_or_five_sessions_are_not_inclusive_h3(last):
    with pytest.raises(ValueError):
        _prepare(last=last)


@pytest.mark.parametrize("minutes", [0, 5, 6])
def test_packet_observed_at_or_after_open_rejected_even_if_open5_not_yet_expired(minutes):
    with pytest.raises(ValueError):
        _prepare(
            weights_observed_at=_window(date(2026, 11, 9)).open_ts + timedelta(minutes=minutes)
        )


@pytest.mark.parametrize("delta", [timedelta(minutes=-1), timedelta(minutes=1), timedelta(days=-1)])
def test_feature_end_requires_exact_prior_official_close(delta):
    prior = prior_official_session_close(_window(date(2026, 11, 9)))
    with pytest.raises(ValueError, match="weights_prior_session_close_invalid"):
        _prepare(feature_window_end=prior + delta)


def test_source_causal_clock_disorder_and_wrong_exit_floor_reject():
    value = _prepare()
    with pytest.raises(ValueError, match="weights_causal_clocks_invalid"):
        _prepare(source_available_at=value.metadata.feature_window_end - timedelta(seconds=1))
    for minutes in (0, 14, 16, 45):
        with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
            _prepare(exit_not_before=value.exit_session.close_ts - timedelta(minutes=minutes))


@pytest.mark.parametrize("change", [
    "missing_cash", "missing_stock", "swapped", "nys_as_nas", "nas_as_nys", "unavailable",
    "ams", "other_symbol", "cash_alias", "duplicate", "unknown_positive",
])
def test_missing_ambiguous_or_aliased_axis_rejects_before_allocation(change, monkeypatch):
    value = _prepare()
    rows = list(value.metadata.rows)
    if change == "missing_cash":
        rows = rows[:-1]
    elif change == "missing_stock":
        rows.pop(7)
    elif change == "swapped":
        rows[1], rows[2] = replace(rows[2], slot=1), replace(rows[1], slot=2)
    elif change == "nys_as_nas":
        rows[8] = replace(rows[8], route="JPM/NAS")
    elif change == "nas_as_nys":
        rows[1] = replace(rows[1], route="AMD/NYS")
    elif change == "unavailable":
        rows[1] = replace(rows[1], route="AMD/UNAVAILABLE", feature_known=False)
    elif change == "ams":
        rows[1] = replace(rows[1], route="AMD/AMS")
    elif change == "other_symbol":
        rows[1] = replace(rows[1], route="QQQ/NAS")
    elif change == "cash_alias":
        rows[17] = replace(rows[17], route="CASH/NAS")
    elif change == "duplicate":
        rows[1] = replace(rows[1], route="AAPL/NAS")
    else:
        # Bypass construction only to prove validation rechecks a forged object.
        rows[0] = copy.deepcopy(rows[0])
        object.__setattr__(rows[0], "feature_known", False)

    def forbidden(*_args):
        pytest.fail("invalid_axis_reached_target_builder")

    monkeypatch.setattr(weights, "_weight_targets", forbidden)
    with pytest.raises(ValueError):
        metadata = _replace_rows(value.metadata, tuple(rows))
        weights.prepare_model_paper_weights_input(
            metadata, entry_session=value.entry_session, exit_session=value.exit_session,
            profile=PROFILE,
        )


@pytest.mark.parametrize("cash", ["0.5000000000001", "0.4", "0.6"])
def test_explicit_cash_mismatch_is_never_repaired_even_within_legacy_mass_tolerance(cash):
    rows = list(_rows((0, 8)))
    rows[17] = replace(rows[17], weight=D(cash))
    with pytest.raises(ValueError, match="weights_(unit_mass|us_cash_h3_ops_residual)_invalid"):
        _prepare(tuple(rows))


@pytest.mark.parametrize("field", ["feature_mask_ref", "weight_bytes_ref"])
def test_rehashed_wrong_mask_or_binary64_binding_denied(field):
    with pytest.raises(ValueError, match="weights_(mask|bytes)_mismatch"):
        _prepare(**{field: "sha256:" + "f" * 64})


@pytest.mark.parametrize("change", [
    "basis", "profile", "target_exposure", "deadline", "decision_clock", "target_route",
    "target_drop", "row_route", "feature_end", "exit_floor", "extra_metadata", "mask",
])
def test_rehashed_forged_serialization_cannot_upgrade_or_extend_input(change):
    document = json.loads(weights.serialize_model_paper_weights_input(_prepare()))
    if change == "basis":
        document["execution_basis"] = weights.EXECUTION_BASIS
    elif change == "profile":
        document["profile"] = weights.MODEL_PAPER_WEIGHTS_US_5_SESSION_PROFILE
    elif change == "target_exposure":
        document["targets"][0]["proposal"]["target_exposure"] = "0.005"
    elif change == "deadline":
        document["targets"][0]["proposal"]["valid_until"] = "2026-11-09T21:00:00+00:00"
    elif change == "decision_clock":
        document["targets"][0]["proposal"]["decided_at"] = "2026-11-09T14:31:00+00:00"
    elif change == "target_route":
        document["targets"][1]["route"] = "JPM/NAS"
    elif change == "target_drop":
        document["targets"].pop()
    elif change == "row_route":
        document["metadata"]["rows"][8]["route"] = "JPM/NAS"
    elif change == "feature_end":
        document["metadata"]["feature_window_end"] = "2026-11-06T20:59:00+00:00"
    elif change == "exit_floor":
        document["metadata"]["exit_not_before"] = "2026-11-11T20:44:00+00:00"
    elif change == "extra_metadata":
        document["metadata"]["modeled_fill_price"] = "not_allowed"
    else:
        document["metadata"]["rows"][1]["feature_known"] = False
    with pytest.raises(ValueError):
        _load(_encoded(document))


def test_full_body_hash_policy_and_canonical_json_are_required():
    raw = weights.serialize_model_paper_weights_input(_prepare())
    with pytest.raises(ValueError, match="weights_input_pin_mismatch"):
        _load(raw, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="weights_policy_pin_mismatch"):
        _load(raw, expected_policy_ref="sha256:" + "f" * 64)
    with pytest.raises(ValueError, match="weights_payload_not_canonical_or_derived"):
        _load(json.dumps(json.loads(raw), indent=2).encode())
    with pytest.raises(ValueError, match="model_duplicate_field"):
        _load(b'{"schema":"duplicate",' + raw[1:])
    wire = b"".join(struct.pack("<d", float(row.weight)) for row in _prepare().metadata.rows)
    assert _prepare().metadata.weight_bytes_ref == "sha256:" + hashlib.sha256(wire).hexdigest()


def test_forged_dataclass_revalidated_on_new_profile_serialization():
    value = copy.deepcopy(_prepare())
    object.__setattr__(value, "execution_basis", weights.EXECUTION_BASIS)
    with pytest.raises(ValueError, match="weights_semantics_invalid"):
        weights.serialize_model_paper_weights_input(value)


def test_old_nas_golden_bytes_and_us_h5_venue_semantics_remain_unchanged():
    old = _prepared()
    old_bytes = weights.serialize_model_paper_weights_input(old)
    assert hashlib.sha256(old_bytes).hexdigest() == (
        "f7eb678f452f299a5ea1700d769f6955c109642d961ec9467de625a17a51e25d"
    )
    assert [t.route for t in old.targets] == ["AAPL/NAS", "MSFT/NAS"]
    us = weights.prepare_model_paper_weights_input(
        old.metadata, entry_session=old.entry_session, exit_session=old.exit_session,
        profile=weights.MODEL_PAPER_WEIGHTS_US_5_SESSION_PROFILE,
    )
    assert [t.route for t in us.targets] == ["AAPL/NAS", "MSFT/NAS", "JPM/NYS"]
    assert all(t.proposal.valid_until == us.entry_session.close_ts for t in us.targets)
    assert us.execution_basis == weights.EXECUTION_BASIS
    assert us.metadata.rows[2].eligibility == "UNSUPPORTED_VENUE"
    assert us.metadata.rows[2].eligibility_for_profile(PROFILE) == "ELIGIBLE_US"
    assert weights.model_paper_cash_h3_window is not weights.model_paper_us_cash_h3_ops_window


def test_request_windows_are_metadata_not_actual_fill_or_execution_authority():
    value = _prepare()
    band = weights.model_paper_us_cash_h3_ops_window(value)
    assert band.entry_end == datetime(2026, 11, 9, 14, 35, tzinfo=UTC)
    assert band.exit_start == datetime(2026, 11, 11, 20, 45, tzinfo=UTC)
    assert value.exit_session.close_ts == datetime(2026, 11, 11, 21, 0, tzinfo=UTC)
    assert not hasattr(value, "broker_intent") and not hasattr(value, "fill_price")
    assert all(t.proposal.confidence == 0 for t in value.targets)
