"""Explicit H5 weight admission; invented inputs only, no broker or model runs."""

import hashlib
import json
import struct
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.model_paper_horizon import (
    MODEL_PAPER_5_SESSION_PROFILE,
    MODEL_PAPER_20_SESSION_PROFILE,
    MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE,
    model_paper_horizon_valid,
    prior_official_session_close,
    validate_model_paper_horizon,
)
from thericher_v2.research.model_paper_weights import (
    EXECUTION_BASIS,
    MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    MODEL_PAPER_WEIGHTS_PROFILE,
    WEIGHT_UNITS,
    ModelPaperWeightRow,
    ModelPaperWeightsMetadata,
    load_model_paper_weights_input,
    model_paper_weights_horizon_profile,
    model_weight_bytes_ref,
    model_weight_mask_ref,
    prepare_model_paper_weights_input,
    serialize_model_paper_weights_input,
)

PIN = "sha256:" + "1" * 64
POLICY = "sha256:" + "2" * 64
DEFAULT20_SHA256 = "41541738212e5f480400470a61a1135a75c395265f5661eabc19a22774e1062f"


def _window(day):
    return us_equity_2026_session(day).window


def _metadata(first, last, rows=None):
    if rows is None:
        rows = (
            ModelPaperWeightRow(0, "MSFT/NAS", True, Decimal(".25")),
            ModelPaperWeightRow(1, "AAPL/NAS", True, Decimal(".5")),
            ModelPaperWeightRow(2, "JPM/NYS", True, Decimal(".25")),
            ModelPaperWeightRow(3, "AMZN/NAS", False, Decimal(0)),
        )
    previous = prior_official_session_close(first)
    stamp = first.open_ts - timedelta(hours=1)
    return ModelPaperWeightsMetadata(
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
        Decimal(".005"),
        rows,
    )


def _prepared(first=date(2026, 10, 26), last=date(2026, 10, 30), **kwargs):
    first, last = _window(first), _window(last)
    return prepare_model_paper_weights_input(
        _metadata(first, last),
        entry_session=first,
        exit_session=last,
        profile=MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
        **kwargs,
    )


def _load(payload):
    return load_model_paper_weights_input(
        payload, expected_sha256=hashlib.sha256(payload).hexdigest(), expected_policy_ref=POLICY
    )


def _encoded(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")


def test_default20_golden_bytes_unchanged_and_explicit20_is_identical():
    first, last = _window(date(2026, 10, 23)), _window(date(2026, 11, 19))
    meta = _metadata(first, last)
    implicit = prepare_model_paper_weights_input(meta, entry_session=first, exit_session=last)
    explicit = prepare_model_paper_weights_input(
        meta, entry_session=first, exit_session=last, profile=MODEL_PAPER_WEIGHTS_PROFILE
    )
    payload = serialize_model_paper_weights_input(implicit)
    assert payload == serialize_model_paper_weights_input(explicit)
    assert hashlib.sha256(payload).hexdigest() == DEFAULT20_SHA256
    assert len(payload) == 4845
    assert _load(payload) == implicit


def test_finite_weight_to_horizon_profile_mapping():
    assert model_paper_weights_horizon_profile(MODEL_PAPER_WEIGHTS_PROFILE) == (
        MODEL_PAPER_20_SESSION_PROFILE
    )
    assert model_paper_weights_horizon_profile(MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE) == (
        MODEL_PAPER_5_SESSION_PROFILE
    )


@pytest.mark.parametrize("amex_weight", ["0.0", "0.5", "1.0"])
def test_amex_weights_preserve_full_axis_without_increasing_nas_target(amex_weight):
    first, last = _window(date(2026, 10, 26)), _window(date(2026, 10, 30))
    weight = Decimal(amex_weight)
    rows = (
        ModelPaperWeightRow(0, "SPY/AMS", True, weight),
        ModelPaperWeightRow(1, "QQQ/NAS", True, Decimal(1) - weight),
        ModelPaperWeightRow(2, "IWM/AMS", True, Decimal("0.0")),
    )
    value = prepare_model_paper_weights_input(
        _metadata(first, last, rows), entry_session=first, exit_session=last,
        profile=MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    )
    loaded = _load(serialize_model_paper_weights_input(value))
    assert loaded == value
    assert loaded.metadata.rows == rows
    assert loaded.metadata.skipped_weight == Fraction(weight)
    assert loaded.metadata.rows[0].eligibility == "UNSUPPORTED_VENUE"
    assert loaded.metadata.rows[2].eligibility == "UNSUPPORTED_VENUE"
    assert all(target.route == "QQQ/NAS" for target in loaded.targets)
    if weight == 1:
        assert loaded.targets == ()
    else:
        assert len(loaded.targets) == 1
        assert loaded.targets[0].proposal.target_exposure == Decimal(".005") * (1 - weight)


@pytest.mark.parametrize(
    "profile",
    [
        None,
        True,
        5,
        [],
        {},
        "",
        "model-weights-nas-6session-2026-v1",
        MODEL_PAPER_5_SESSION_PROFILE,
        MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE,
    ],
)
def test_unknown_or_legacy_alias_weight_profiles_fail_closed(profile):
    with pytest.raises(ValueError, match="weights_profile_invalid"):
        model_paper_weights_horizon_profile(profile)
    value = _prepared()
    with pytest.raises(ValueError, match="weights_profile_invalid"):
        replace(value, profile=profile)
    with pytest.raises(ValueError, match="weights_profile_invalid"):
        prepare_model_paper_weights_input(
            value.metadata,
            entry_session=value.entry_session,
            exit_session=value.exit_session,
            profile=profile,
        )


def test_h5_roundtrip_preserves_profile_weights_cohort_and_target_priority():
    value = _prepared()
    payload = serialize_model_paper_weights_input(value)
    loaded = _load(payload)
    assert loaded == value
    assert serialize_model_paper_weights_input(loaded) == payload
    assert loaded.profile == MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE
    assert json.loads(payload)["profile"] == MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE
    assert loaded.entry_session.open_ts == datetime(2026, 10, 26, 13, 30, tzinfo=UTC)
    assert loaded.exit_session.close_ts == datetime(2026, 10, 30, 20, tzinfo=UTC)
    assert loaded.metadata.exit_not_before == datetime(2026, 10, 30, 19, 45, tzinfo=UTC)
    assert loaded.metadata.original_basis_gross_ceiling == Decimal(".005")
    assert loaded.weight_units == WEIGHT_UNITS and loaded.execution_basis == EXECUTION_BASIS
    assert [target.slot for target in loaded.targets] == [1, 0]
    assert [t.proposal.target_exposure for t in loaded.targets] == [
        Decimal(".0025"),
        Decimal(".00125"),
    ]
    assert loaded.metadata.rows[2].eligibility == "UNSUPPORTED_VENUE"
    assert loaded.metadata.rows[3].eligibility == "FEATURE_UNAVAILABLE"
    assert loaded.metadata.rows == value.metadata.rows


@pytest.mark.parametrize("last", [date(2026, 10, 29), date(2026, 11, 2)])
def test_four_and_six_sessions_rejected(last):
    with pytest.raises(ValueError, match="model_5session_horizon_invalid"):
        _prepared(last=last)


@pytest.mark.parametrize(
    "first,last,open_hour,close_hour",
    [
        (date(2026, 10, 23), date(2026, 10, 29), 13, 20),  # Weekend.
        (date(2026, 3, 30), date(2026, 4, 6), 13, 20),  # Good Friday.
        (date(2026, 6, 29), date(2026, 7, 6), 13, 20),  # Observed July4 holiday.
        (date(2026, 11, 23), date(2026, 11, 30), 14, 21),  # Thanksgiving.
        (date(2026, 11, 20), date(2026, 11, 27), 14, 18),  # Half-day exit.
        (date(2026, 10, 28), date(2026, 11, 3), 13, 21),  # DST ends.
        (date(2026, 3, 4), date(2026, 3, 10), 14, 20),  # DST begins.
    ],
)
def test_official_calendar_weekends_holidays_half_day_and_dst(first, last, open_hour, close_hour):
    value = _prepared(first, last)
    assert value.entry_session.open_ts.hour == open_hour
    assert value.exit_session.close_ts.hour == close_hour
    assert value.metadata.exit_not_before == value.exit_session.close_ts - timedelta(minutes=15)
    assert _load(serialize_model_paper_weights_input(value)) == value
    assert model_paper_horizon_valid(
        value.entry_session, value.exit_session, profile=MODEL_PAPER_5_SESSION_PROFILE
    )


@pytest.mark.parametrize("first", [date(2026, 10, 24), date(2026, 7, 3)])
def test_forged_weekend_or_holiday_entry_session_is_not_admitted(first):
    fake = SessionWindow(
        datetime(first.year, first.month, first.day, 13, 30, tzinfo=UTC),
        datetime(first.year, first.month, first.day, 20, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="model_5session_horizon_invalid"):
        validate_model_paper_horizon(
            fake, _window(date(2026, 10, 30)), profile=MODEL_PAPER_5_SESSION_PROFILE
        )


def test_forged_dst_offset_and_half_day_close_cannot_be_used():
    for first, last, fake_close in (
        (date(2026, 10, 28), date(2026, 11, 3), datetime(2026, 11, 3, 20, tzinfo=UTC)),
        (date(2026, 11, 20), date(2026, 11, 27), datetime(2026, 11, 27, 21, tzinfo=UTC)),
    ):
        real = _window(last)
        with pytest.raises(ValueError, match="model_5session_horizon_invalid"):
            validate_model_paper_horizon(
                _window(first),
                SessionWindow(real.open_ts, fake_close),
                profile=MODEL_PAPER_5_SESSION_PROFILE,
            )


def test_h5_calendar_scope_remains_2026_only():
    with pytest.raises(ValueError, match="model_5session_calendar_scope_invalid"):
        validate_model_paper_horizon(
            _window(date(2026, 12, 28)),
            SessionWindow(
                datetime(2027, 1, 4, 14, 30, tzinfo=UTC), datetime(2027, 1, 4, 21, tzinfo=UTC)
            ),
            profile=MODEL_PAPER_5_SESSION_PROFILE,
        )


@pytest.mark.parametrize(
    "profile", [MODEL_PAPER_WEIGHTS_PROFILE, MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE]
)
def test_rehashed_cross_profile_retag_cannot_change_horizon(profile):
    value = (
        _prepared()
        if profile == MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE
        else prepare_model_paper_weights_input(
            _metadata(_window(date(2026, 10, 23)), _window(date(2026, 11, 19))),
            entry_session=_window(date(2026, 10, 23)),
            exit_session=_window(date(2026, 11, 19)),
        )
    )
    document = json.loads(serialize_model_paper_weights_input(value))
    other = (
        MODEL_PAPER_WEIGHTS_PROFILE
        if profile == MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE
        else MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE
    )
    document["profile"] = other
    with pytest.raises(ValueError, match="model_(5|20)session_horizon_invalid"):
        _load(_encoded(document))
    with pytest.raises(ValueError, match="model_(5|20)session_horizon_invalid"):
        replace(value, profile=other)


@pytest.mark.parametrize("profile", [None, [], "model-weights-nas-6session-2026-v1"])
def test_loader_unknown_or_missing_profile_never_defaults_to20(profile):
    document = json.loads(serialize_model_paper_weights_input(_prepared()))
    document["profile"] = profile
    with pytest.raises(ValueError, match="weights_input_schema_invalid"):
        _load(_encoded(document))
    del document["profile"]
    with pytest.raises(ValueError, match="weights_input_schema_invalid"):
        _load(_encoded(document))


@pytest.mark.parametrize("minutes", [14, 16])
def test_exit_floor_is_exactly_fifteen_minutes_before_actual_h5_close(minutes):
    value = _prepared()
    meta = replace(
        value.metadata, exit_not_before=value.exit_session.close_ts - timedelta(minutes=minutes)
    )
    with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
        prepare_model_paper_weights_input(
            meta,
            entry_session=value.entry_session,
            exit_session=value.exit_session,
            profile=MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
        )


def test_default_profile_does_not_infer_five_from_dates():
    first, last = _window(date(2026, 10, 26)), _window(date(2026, 10, 30))
    with pytest.raises(ValueError, match="model_20session_horizon_invalid"):
        prepare_model_paper_weights_input(
            _metadata(first, last), entry_session=first, exit_session=last
        )


def test_legacy_post_open_five_calendar_behavior_is_unchanged():
    first, last = _window(date(2026, 11, 20)), _window(date(2026, 11, 27))
    validate_model_paper_horizon(first, last, profile=MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE)
    with pytest.raises(ValueError, match="model_5session_horizon_invalid"):
        validate_model_paper_horizon(
            first, _window(date(2026, 11, 30)), profile=MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE
        )


def test_noncanonical_h5_payload_is_rejected_even_with_valid_hash():
    raw = serialize_model_paper_weights_input(_prepared())
    with pytest.raises(ValueError, match="weights_payload_not_canonical_or_derived"):
        _load(json.dumps(json.loads(raw), indent=2).encode())


def test_full100_known69_weights_keep_all_targets_without_topk_or_rescaling():
    first, last = _window(date(2026, 10, 26)), _window(date(2026, 10, 30))
    rows = tuple(
        ModelPaperWeightRow(
            i,
            "S" + chr(65 + i // 26) + chr(65 + i % 26) + ("/NAS" if i < 69 else "/UNAVAILABLE"),
            i < 69,
            Decimal(repr(float(1 / 69))) if i < 69 else Decimal(0),
        )
        for i in range(100)
    )
    value = prepare_model_paper_weights_input(
        _metadata(first, last, rows),
        entry_session=first,
        exit_session=last,
        profile=MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
    )
    restored = _load(serialize_model_paper_weights_input(value))
    assert restored.metadata.rows == rows
    assert len(restored.metadata.rows) == 100 and len(restored.targets) == 69
    assert [t.slot for t in restored.targets] == list(range(69))
    wire_weights = b"".join(struct.pack("<d", float(r.weight)) for r in rows)
    assert (
        restored.metadata.weight_bytes_ref == "sha256:" + hashlib.sha256(wire_weights).hexdigest()
    )
    assert sum(Fraction(t.proposal.target_exposure) for t in restored.targets) <= Fraction(".005")
