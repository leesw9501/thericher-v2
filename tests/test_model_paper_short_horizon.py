"""Elapsed-horizon source contracts; invented inputs and inert native parsing only."""

import hashlib
import json
import socket
import subprocess
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from test_model_paper_weights_h5 import POLICY, _metadata, _window
from thericher_v2.execution import kis_paper_current_stock_cycle as native
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research import model_paper_horizon as horizon
from thericher_v2.research import model_paper_weights as weights

ELAPSED_PROFILES = (
    "model-weights-nas-elapsed-h1-prior-close-2026-v1",
    "model-weights-nas-elapsed-h3-prior-close-2026-v1",
    "model-weights-nas-elapsed-h5-prior-close-2026-v1",
)


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("short_horizon_source_test_external_effect_forbidden")

    for owner, name in (
        (socket, "create_connection"),
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
        (urllib.request, "urlopen"),
        (urllib.request.OpenerDirector, "open"),
        (subprocess, "Popen"),
    ):
        monkeypatch.setattr(owner, name, denied)


def _legacy(profile, first, last):
    first, last = _window(first), _window(last)
    return weights.prepare_model_paper_weights_input(
        _metadata(first, last), entry_session=first, exit_session=last, profile=profile
    )


def _load(payload):
    return weights.load_model_paper_weights_input(
        payload,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_policy_ref=POLICY,
    )


def _elapsed(profile, first=date(2026, 11, 2), last=date(2026, 11, 3), **changes):
    first, last = _window(first), _window(last)
    return weights.prepare_model_paper_weights_input(
        replace(_metadata(first, last), **changes),
        entry_session=first,
        exit_session=last,
        profile=profile,
    )


@pytest.mark.parametrize(
    "profile,first,last,size,digest,native_profile",
    [
        (
            weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
            date(2026, 10, 26),
            date(2026, 10, 30),
            4844,
            "f7eb678f452f299a5ea1700d769f6955c109642d961ec9467de625a17a51e25d",
            native.StockCycleProfile.MODEL_WEIGHTS_NAS_H5,
        ),
        (
            weights.MODEL_PAPER_WEIGHTS_PROFILE,
            date(2026, 10, 23),
            date(2026, 11, 19),
            4845,
            "41541738212e5f480400470a61a1135a75c395265f5661eabc19a22774e1062f",
            native.StockCycleProfile.MODEL_WEIGHTS_NAS,
        ),
    ],
)
def test_original_profiles_golden_bytes_and_inert_native_parser(
    profile, first, last, size, digest, native_profile
):
    value = _legacy(profile, first, last)
    payload = weights.serialize_model_paper_weights_input(value)
    assert len(payload) == size
    assert hashlib.sha256(payload).hexdigest() == digest
    loaded = _load(payload)
    parsed = native._unpack(native._pack(loaded))
    assert loaded == parsed == value
    assert weights.serialize_model_paper_weights_input(parsed) == payload
    native._validate_model_input(parsed, value.entry_session.open_ts, native_profile)
    assert value.metadata.exit_not_before == value.exit_session.close_ts - timedelta(minutes=15)


def test_existing_h5_admits_session_open_not_only_near_close():
    value = _legacy(
        weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
        date(2026, 10, 26),
        date(2026, 10, 30),
    )
    native._validate_model_input(
        value, value.entry_session.open_ts, native.StockCycleProfile.MODEL_WEIGHTS_NAS_H5
    )
    assert value.targets[0].proposal.decided_at < value.entry_session.open_ts
    assert value.targets[0].proposal.valid_until == value.entry_session.close_ts


@pytest.mark.parametrize("profile", ELAPSED_PROFILES)
def test_existing_native_enum_does_not_grant_elapsed_profile_execution(profile):
    with pytest.raises(ValueError):
        native.StockCycleProfile(profile)


def test_existing_early_exit_profile_and_window_are_not_short_horizon_aliases():
    first, last = _window(date(2026, 10, 30)), _window(date(2026, 11, 27))
    value = weights.prepare_model_paper_weights_input(
        replace(_metadata(first, last), exit_not_before=last.close_ts - timedelta(minutes=45)),
        entry_session=first,
        exit_session=last,
        profile=weights.MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE,
    )
    window = weights.model_paper_early_exit_window(value)
    assert window.entry_start == first.open_ts
    assert window.entry_end == first.close_ts
    assert window.exit_start == last.close_ts - timedelta(minutes=45)
    assert window.exit_end == last.close_ts - timedelta(minutes=25)
    assert window.cleanup_end == last.close_ts - timedelta(minutes=20)
    assert window.closure_before == last.close_ts - timedelta(minutes=15)
    assert _load(weights.serialize_model_paper_weights_input(value)) == value


@pytest.mark.parametrize("profile", ELAPSED_PROFILES)
def test_old_inclusive_five_session_payload_is_not_an_elapsed_alias(profile):
    value = _legacy(
        weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
        date(2026, 10, 26),
        date(2026, 10, 30),
    )
    document = json.loads(weights.serialize_model_paper_weights_input(value))
    document["profile"] = profile
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
    with pytest.raises(ValueError):
        _load(payload)


@pytest.mark.parametrize(
    "profile,horizon_profile,last",
    [
        (ELAPSED_PROFILES[0], horizon.MODEL_PAPER_ELAPSED_H1_PROFILE, date(2026, 11, 3)),
        (ELAPSED_PROFILES[1], horizon.MODEL_PAPER_ELAPSED_H3_PROFILE, date(2026, 11, 5)),
        (ELAPSED_PROFILES[2], horizon.MODEL_PAPER_ELAPSED_H5_PROFILE, date(2026, 11, 9)),
    ],
)
def test_explicit_elapsed_profile_roundtrip_and_real_native_parse_not_admission(
    profile, horizon_profile, last
):
    value = _elapsed(profile, last=last)
    assert weights.model_paper_weights_horizon_profile(profile) == horizon_profile
    payload = weights.serialize_model_paper_weights_input(value)
    loaded = _load(payload)
    parsed = native._unpack(native._pack(loaded))
    assert loaded == parsed == value
    assert parsed.input_ref == "sha256:" + hashlib.sha256(payload).hexdigest()
    assert weights.serialize_model_paper_weights_input(parsed) == payload
    assert value.metadata.feature_window_end == datetime(2026, 10, 30, 20, tzinfo=UTC)
    assert value.metadata.weights_observed_at < value.entry_session.open_ts
    assert value.metadata.exit_not_before == value.exit_session.close_ts - timedelta(minutes=15)
    assert value.execution_basis == weights.ELAPSED_EXECUTION_BASIS
    assert "replay_close_e_to_close_e_plus_h" in value.execution_basis
    assert "not_fresh_quote_fills_or_native_near_close_admission" in value.execution_basis
    for original in native._MODEL_WEIGHT_PROFILES:
        with pytest.raises(native._CycleFault, match="cycle_input_invalid"):
            native._validate_model_input(
                parsed, value.entry_session.close_ts - timedelta(minutes=5), original
            )
    with pytest.raises(ValueError, match="weights_profile_invalid"):
        weights.model_paper_early_exit_window(parsed)


@pytest.mark.parametrize(
    "profile,first,last,entry_hour,exit_hour",
    [
        (ELAPSED_PROFILES[0], date(2026, 10, 30), date(2026, 11, 2), 20, 21),
        (ELAPSED_PROFILES[0], date(2026, 3, 6), date(2026, 3, 9), 21, 20),
        (ELAPSED_PROFILES[0], date(2026, 4, 2), date(2026, 4, 6), 20, 20),
        (ELAPSED_PROFILES[0], date(2026, 11, 25), date(2026, 11, 27), 21, 18),
        (ELAPSED_PROFILES[0], date(2026, 11, 27), date(2026, 11, 30), 18, 21),
        (ELAPSED_PROFILES[1], date(2026, 11, 24), date(2026, 11, 30), 21, 21),
        (ELAPSED_PROFILES[2], date(2026, 11, 20), date(2026, 11, 30), 21, 21),
    ],
)
def test_elapsed_weekend_holiday_dst_and_early_close(profile, first, last, entry_hour, exit_hour):
    value = _elapsed(profile, first, last)
    assert value.entry_session.close_ts.hour == entry_hour
    assert value.exit_session.close_ts.hour == exit_hour
    assert value.metadata.exit_not_before == value.exit_session.close_ts - timedelta(minutes=15)
    assert _load(weights.serialize_model_paper_weights_input(value)) == value


@pytest.mark.parametrize(
    "profile,last",
    [
        (ELAPSED_PROFILES[0], date(2026, 11, 2)),
        (ELAPSED_PROFILES[0], date(2026, 11, 4)),
        (ELAPSED_PROFILES[1], date(2026, 11, 4)),
        (ELAPSED_PROFILES[1], date(2026, 11, 6)),
        (ELAPSED_PROFILES[2], date(2026, 11, 6)),
        (ELAPSED_PROFILES[2], date(2026, 11, 10)),
    ],
)
def test_wrong_elapsed_or_inclusive_horizon_is_rejected(profile, last):
    with pytest.raises(ValueError, match="model_(elapsed_horizon|session_clocks)_invalid"):
        _elapsed(profile, last=last)


@pytest.mark.parametrize("shift", [-86400, -1, 1])
def test_new_profile_requires_exact_prior_completed_close(shift):
    value = _elapsed(ELAPSED_PROFILES[0])
    with pytest.raises(ValueError, match="weights_prior_session_close_invalid"):
        weights.prepare_model_paper_weights_input(
            replace(
                value.metadata,
                feature_window_end=value.metadata.feature_window_end + timedelta(seconds=shift),
            ),
            entry_session=value.entry_session,
            exit_session=value.exit_session,
            profile=value.profile,
        )


def test_legacy_profiles_do_not_acquire_new_prior_close_restriction():
    value = _legacy(
        weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
        date(2026, 10, 26),
        date(2026, 10, 30),
    )
    changed = weights.prepare_model_paper_weights_input(
        replace(
            value.metadata, feature_window_end=value.metadata.feature_window_end - timedelta(days=1)
        ),
        entry_session=value.entry_session,
        exit_session=value.exit_session,
        profile=value.profile,
    )
    assert _load(weights.serialize_model_paper_weights_input(changed)) == changed


@pytest.mark.parametrize("field", ["entry_session", "exit_session"])
def test_shifted_official_session_cannot_change_elapsed_target(field):
    value = _elapsed(ELAPSED_PROFILES[0], date(2026, 11, 25), date(2026, 11, 27))
    session = getattr(value, field)
    changed = replace(session, close_ts=session.close_ts + timedelta(minutes=1))
    with pytest.raises(ValueError, match="model_elapsed_horizon_invalid"):
        replace(value, **{field: changed})


def test_weekend_entry_is_not_silently_advanced():
    first = SessionWindow(
        datetime(2026, 11, 1, 14, 30, tzinfo=UTC), datetime(2026, 11, 1, 21, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="model_elapsed_horizon_invalid"):
        horizon.validate_model_paper_horizon(
            first, _window(date(2026, 11, 3)), profile=horizon.MODEL_PAPER_ELAPSED_H1_PROFILE
        )


def test_missing_prior_year_calendar_is_unavailable():
    with pytest.raises(ValueError, match="model_prior_session_calendar_scope_invalid"):
        _elapsed(ELAPSED_PROFILES[0], date(2026, 1, 2), date(2026, 1, 5))


def test_elapsed_target_cannot_run_beyond_calendar_scope():
    first = _window(date(2026, 12, 31))
    last = SessionWindow(
        datetime(2027, 1, 4, 14, 30, tzinfo=UTC), datetime(2027, 1, 4, 21, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="model_elapsed_calendar_scope_invalid"):
        horizon.validate_model_paper_horizon(
            first, last, profile=horizon.MODEL_PAPER_ELAPSED_H1_PROFILE
        )


@pytest.mark.parametrize("offset", [0, 1, 300])
def test_new_profile_does_not_silently_allow_post_open_decision(offset):
    first = _window(date(2026, 11, 2))
    with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
        _elapsed(ELAPSED_PROFILES[0], weights_observed_at=first.open_ts + timedelta(seconds=offset))


@pytest.mark.parametrize("minutes", [0, 5, 14, 16, 45])
def test_new_exit_eligibility_does_not_claim_replay_close_execution(minutes):
    last = _window(date(2026, 11, 3))
    with pytest.raises(ValueError, match="weights_session_clocks_invalid"):
        _elapsed(ELAPSED_PROFILES[0], exit_not_before=last.close_ts - timedelta(minutes=minutes))


@pytest.mark.parametrize("phase", ["open", "near_close", "close", "exit_open", "exit_eligible"])
def test_existing_native_h5_phase_boundaries_remain_unchanged(phase):
    value = _legacy(
        weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE,
        date(2026, 10, 26),
        date(2026, 10, 30),
    )
    at = {
        "open": value.entry_session.open_ts,
        "near_close": value.entry_session.close_ts - timedelta(minutes=5),
        "close": value.entry_session.close_ts,
        "exit_open": value.exit_session.open_ts,
        "exit_eligible": value.metadata.exit_not_before,
    }[phase]
    if phase in {"open", "near_close"}:
        native._validate_model_input(value, at, native.StockCycleProfile.MODEL_WEIGHTS_NAS_H5)
    else:
        # The pure fresh-input validator is entry-only, not the retained exit/recovery path.
        with pytest.raises(native._CycleFault, match="cycle_session_invalid"):
            native._validate_model_input(value, at, native.StockCycleProfile.MODEL_WEIGHTS_NAS_H5)
