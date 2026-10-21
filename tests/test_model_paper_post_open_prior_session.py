"""Explicit late-publication DTO, invented inputs and no broker/state effects."""

import hashlib
import json
import socket
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.research.model_paper_horizon import (
    MODEL_PAPER_20_SESSION_PROFILE,
    MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE,
    model_paper_horizon_valid,
)
from thericher_v2.research.model_paper_proposal import (
    MODEL_PAPER_PROFILE,
    ModelPaperMetadata,
    ModelPaperRow,
    load_model_paper_input,
    prepare_model_paper_input,
    serialize_model_paper_input,
)

D = Decimal
LATE = MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pure_timing_test_cannot_use_network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def window(day):
    return us_equity_2026_session(day).window


def sessions(entry=date(2026, 10, 21), count=5):
    result = []
    for offset in range(60):
        session = us_equity_2026_session(entry + timedelta(days=offset))
        if session is not None:
            result.append(session.window)
            if len(result) == count:
                return result
    raise AssertionError("synthetic_calendar_scope")


def metadata(first, last, *, late=True):
    entry = first.open_ts.date()
    for offset in range(1, 15):
        previous = us_equity_2026_session(entry - timedelta(days=offset))
        if previous is not None:
            break
    stamp = first.open_ts + timedelta(minutes=11) if late else first.open_ts - timedelta(hours=1)
    return ModelPaperMetadata(
        "synthetic-post-open-compat",
        "synthetic-prior-close",
        *("sha256:" + str(i) * 64 for i in range(1, 8)),
        previous.window.close_ts,
        previous.window.close_ts + timedelta(hours=1),
        stamp,
        stamp,
        stamp,
        stamp,
        last.close_ts - timedelta(minutes=15),
        D(".005"),
        (
            ModelPaperRow(3, "AAA/NAS", D(-1), 3, D(".2")),
            ModelPaperRow(4, "BBB/NYS", D(0), 2, D(".3")),
            ModelPaperRow(27, "CCC/NAS", D(1), 1, D(".5")),
        ),
    )


def value(*, entry=date(2026, 10, 21), profile=LATE, late=True):
    days = sessions(entry, 20 if profile == MODEL_PAPER_20_SESSION_PROFILE else 5)
    return prepare_model_paper_input(
        metadata(days[0], days[-1], late=late),
        entry_session=days[0],
        exit_session=days[-1],
        profile=profile,
    )


def load(original, **kwargs):
    raw = serialize_model_paper_input(original)
    return load_model_paper_input(
        raw,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        expected_policy_ref=original.policy_ref,
        **kwargs,
    )


@pytest.mark.parametrize(
    "profile,expected",
    [
        (MODEL_PAPER_PROFILE, "99c555208d89aaa1c97c0157c50eada280a4649711cce9984d538e086a2d268e"),
        (
            MODEL_PAPER_20_SESSION_PROFILE,
            "b05fd79d23272352906fa8ec0ceaf1b68742d48ccaf2ecdd88418185188feda4",
        ),
    ],
)
def test_pre_edit_golden_bytes_ids_and_all18_metadata_fields_unchanged(profile, expected):
    original = value(profile=profile, late=False)
    raw = serialize_model_paper_input(original)
    assert hashlib.sha256(raw).hexdigest() == expected
    assert original.input_ref == "sha256:" + expected
    assert len(fields(original.metadata)) == 18
    assert serialize_model_paper_input(load(original, expected_profile=profile)) == raw


def test_explicit_late_roundtrip_preserves_actual_clocks_slots_venue_and_bank_fraction():
    original = value()
    assert load(original, expected_profile=LATE) == original
    assert original.metadata.score_observed_at == datetime(2026, 10, 21, 13, 41, tzinfo=UTC)
    assert original.entry_session.open_ts == datetime(2026, 10, 21, 13, 30, tzinfo=UTC)
    assert original.metadata.feature_window_end == datetime(2026, 10, 20, 20, tzinfo=UTC)
    assert [t.slot for t in original.targets] == [3, 27]
    assert original.metadata.skipped_weight == Fraction(3, 10)
    assert sum(Fraction(t.proposal.target_exposure) for t in original.targets) == Fraction(7, 2000)
    assert all(
        t.proposal.decided_at == original.metadata.score_observed_at for t in original.targets
    )
    assert (
        cycle._validate_input(
            original,
            datetime(2026, 10, 21, 16, tzinfo=UTC),
            cycle.StockCycleProfile.MODEL_PROPOSAL_NAS,
        )
        == original
    )


@pytest.mark.parametrize(
    "explicit", [False, MODEL_PAPER_PROFILE, MODEL_PAPER_20_SESSION_PROFILE, None]
)
def test_old_or_absent_loader_expectation_cannot_admit_new_profile(explicit):
    options = {} if explicit is False else dict(expected_profile=explicit)
    with pytest.raises(ValueError):
        load(value(), **options)


@pytest.mark.parametrize("profile", [MODEL_PAPER_PROFILE, MODEL_PAPER_20_SESSION_PROFILE])
def test_old_constructor_profiles_still_reject_post_open(profile):
    with pytest.raises(ValueError, match="model_session_clocks_invalid"):
        value(profile=profile)


@pytest.mark.parametrize("offset", [-1, 0, 390, 391])
def test_new_profile_requires_score_strictly_after_open_and_before_close(offset):
    first, last = sessions()[0], sessions()[-1]
    at = first.open_ts + timedelta(minutes=offset)
    meta = replace(
        metadata(first, last),
        input_asof=at,
        inference_started_at=at,
        inference_completed_at=at,
        score_observed_at=at,
    )
    with pytest.raises(ValueError, match="model_session_clocks_invalid|valid_until cannot precede"):
        prepare_model_paper_input(meta, entry_session=first, exit_session=last, profile=LATE)


@pytest.mark.parametrize(
    "field", ["source_available_at", "input_asof", "inference_started_at", "inference_completed_at"]
)
def test_clock_ordering_is_not_weakened(field):
    first, last = sessions()[0], sessions()[-1]
    meta = metadata(first, last)
    with pytest.raises(ValueError, match="model_causal_clocks_invalid"):
        replace(meta, **{field: meta.score_observed_at + timedelta(microseconds=1)})


@pytest.mark.parametrize(
    "shift", [timedelta(microseconds=-1), timedelta(microseconds=1), timedelta(days=-1)]
)
def test_only_exact_immediately_prior_official_close_is_allowed(shift):
    first, last = sessions()[0], sessions()[-1]
    meta = metadata(first, last)
    meta = replace(meta, feature_window_end=meta.feature_window_end + shift)
    with pytest.raises(ValueError, match="model_prior_session_close_invalid"):
        prepare_model_paper_input(meta, entry_session=first, exit_session=last, profile=LATE)


@pytest.mark.parametrize(
    "entry,prior",
    [
        (date(2026, 10, 26), datetime(2026, 10, 23, 20, tzinfo=UTC)),
        (date(2026, 2, 17), datetime(2026, 2, 13, 21, tzinfo=UTC)),
        (date(2026, 11, 2), datetime(2026, 10, 30, 20, tzinfo=UTC)),
        (date(2026, 11, 27), datetime(2026, 11, 25, 21, tzinfo=UTC)),
    ],
)
def test_weekend_holiday_dst_and_early_close_calendar(entry, prior):
    original = value(entry=entry)
    assert original.metadata.feature_window_end == prior
    assert load(original, expected_profile=LATE) == original


@pytest.mark.parametrize("count", [4, 6, 20])
def test_new_profile_never_changes_five_session_horizon(count):
    first, last = sessions(count=count)[0], sessions(count=count)[-1]
    with pytest.raises(ValueError, match="model_5session_horizon_invalid"):
        prepare_model_paper_input(
            metadata(first, last), entry_session=first, exit_session=last, profile=LATE
        )


@pytest.mark.parametrize("which", ["entry_open", "entry_close", "exit_open", "exit_close"])
def test_official_windows_cannot_be_shifted(which):
    first, last = sessions()[0], sessions()[-1]
    meta = metadata(first, last)
    field = "open_ts" if which.endswith("open") else "close_ts"
    if which.startswith("entry"):
        first = replace(first, **{field: getattr(first, field) + timedelta(minutes=1)})
    else:
        last = replace(last, **{field: getattr(last, field) + timedelta(minutes=1)})
    with pytest.raises(ValueError, match="model_5session_horizon_invalid"):
        prepare_model_paper_input(meta, entry_session=first, exit_session=last, profile=LATE)


def test_missing_prior_year_calendar_is_unavailable_not_a_fallback():
    first, last = window(date(2026, 1, 2)), window(date(2026, 1, 8))
    base = value().metadata
    stamp = first.open_ts + timedelta(minutes=11)
    meta = replace(
        base,
        feature_window_end=datetime(2026, 1, 1, 21, tzinfo=UTC),
        source_available_at=datetime(2026, 1, 1, 22, tzinfo=UTC),
        input_asof=stamp,
        inference_started_at=stamp,
        inference_completed_at=stamp,
        score_observed_at=stamp,
        exit_not_before=last.close_ts - timedelta(minutes=15),
    )
    with pytest.raises(ValueError, match="model_prior_session_calendar_scope_invalid"):
        prepare_model_paper_input(meta, entry_session=first, exit_session=last, profile=LATE)


def test_native_effect_clock_still_cannot_precede_publication():
    original = value()
    with pytest.raises(cycle._CycleFault, match="cycle_target_invalid"):
        cycle._validate_input(
            original,
            original.metadata.score_observed_at - timedelta(microseconds=1),
            cycle.StockCycleProfile.MODEL_PROPOSAL_NAS,
        )


def test_old_execution_profile_and_exact_pending_pack_are_unchanged():
    original = value()
    assert len(cycle.StockCycleProfile) == 3
    assert cycle._unpack(cycle._pack(original)) == original
    assert [t.proposal.target_exposure for t in original.targets] == [D(".001"), D(".0025")]


def test_pinned_wire_rejects_clock_substitution_even_with_same_profile():
    original = value()
    raw = serialize_model_paper_input(original)
    changed = json.loads(raw)
    changed["metadata"]["score_observed_at"] = "2026-10-21T16:00:00+00:00"
    tampered = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode("ascii")
    with pytest.raises(ValueError, match="model_input_pin_mismatch"):
        load_model_paper_input(
            tampered,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            expected_policy_ref=original.policy_ref,
            expected_profile=LATE,
        )


def test_unknown_profile_does_not_default_and_no_implicit_20session_extension():
    original = value()
    assert not model_paper_horizon_valid(
        original.entry_session, original.exit_session, profile=None
    )
    with pytest.raises(ValueError, match="model_profile_invalid"):
        prepare_model_paper_input(
            original.metadata,
            entry_session=original.entry_session,
            exit_session=original.exit_session,
            profile="postopen",
        )
