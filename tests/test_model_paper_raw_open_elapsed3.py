"""Portable invented forecasts -> native Paper weights, custody and recovery."""

import copy
import hashlib
import json
import struct
import urllib.request
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

import test_kis_paper_current_stock_cycle as legacy
import test_kis_paper_weight_cycle as native
import test_liquid17_nas_nys_compatibility as us
import test_model_paper_weights_h5 as old
import test_model_paper_weights_us_cash_h3_ops as inclusive
from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution import paper_account_session as account
from thericher_v2.execution.paper_account_round import PaperRoundSlot
from thericher_v2.research import model_paper_weights as weights
from thericher_v2.research import raw_open_elapsed3_proposal as policy
from thericher_v2.research.model_paper_horizon import MODEL_PAPER_ELAPSED_H3_PROFILE

PROFILE = weights.MODEL_PAPER_WEIGHTS_US_CASH_RAW_OPEN_ELAPSED3_PROFILE
NATIVE = core.StockCycleProfile.MODEL_WEIGHTS_US_CASH_RAW_OPEN_ELAPSED3
ROUTES = weights.MODEL_PAPER_US_CASH_H3_OPS_ROUTES


def window(day):
    return us_equity_2026_session(day).window


def metadata(first=date(2026, 11, 4), last=date(2026, 11, 9)):
    entry, exit_session = window(first), window(last)
    rows = tuple(
        weights.ModelPaperWeightRow(i, route, True, Decimal(int(route == "CASH")))
        for i, route in enumerate(ROUTES)
    )
    return replace(
        old._metadata(entry, exit_session, rows),
        exit_not_before=exit_session.open_ts,
        model_ref="sha256:" + policy.CHECKPOINT,
        feature_schema_id="ede-raw-return-causalC60F4-v1",
    )


def forecast(meta, selected=(0, 8)):
    """Invented parser result; real native score codec, no external adapter import."""
    observed = meta.inference_completed_at
    parsed = dict(
        schema="RAW_TCN_NONBROKER_SCORE_PROPOSAL_V1",
        model_checkpoint_sha256=policy.CHECKPOINT,
        forecast_horizon=policy.TARGET,
        model_input_status="ready", inference_status="scores_available",
        inference_observed_at=observed.isoformat(),
        score_rows=[dict(
            slot=i, route=route, symbol=route.split("/")[0],
            score_units=policy.UNITS, model_score_known=True,
            expected_excess_return_open_e_to_open_e_plus_3=(0.01 if i in selected else -0.01),
        ) for i, route in enumerate(ROUTES[:17])],
    )
    proposals = tuple(
        TargetExposureProposal(
            f"invented-score-{i}", route.split("/")[0], "US", "abstain", Decimal(0),
            Decimal(0), meta.feature_schema_id, "ready", observed, observed,
            meta.feature_window_end, "forecast_only_no_execution_mapping",
        ) for i, route in enumerate(ROUTES[:17])
    )
    return parsed, core._unpack(json.loads(json.dumps(core._pack(proposals))))


def make(first=date(2026, 11, 4), last=date(2026, 11, 9), selected=(0, 8)):
    meta = metadata(first, last)
    parsed, scores = forecast(meta, selected)
    return policy.prepare_raw_open_proposal(
        parsed, scores, meta, entry_session=window(first), exit_session=window(last),
    )


def forbidden(*args, **kwargs):
    pytest.fail("no_forecast_reload_or_external_effect_allowed")


@pytest.fixture(autouse=True)
def no_actual_calls(monkeypatch):
    legacy.no_actual_calls.__wrapped__(monkeypatch)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)


@pytest.fixture
def h(tmp_path):
    state = us.us_h.__wrapped__(tmp_path)
    native.bind(state, make(), NATIVE)
    state["now"] = state["data"].entry_session.open_ts + timedelta(seconds=30)
    return state


def test_pure_producer_real_codec_native_calendar_and_nys_route():
    meta = metadata()
    parsed, scores = forecast(meta)
    before = copy.deepcopy(parsed)
    value = policy.prepare_raw_open_proposal(
        parsed, scores, meta, entry_session=window(date(2026, 11, 4)),
        exit_session=window(date(2026, 11, 9)),
    )
    raw = weights.serialize_model_paper_weights_input(value)
    restored = weights.load_model_paper_weights_input(
        raw, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_policy_ref=value.policy_ref,
    )
    assert restored == value == core._unpack(core._pack(value))
    assert core._validate_model_input(value, value.entry_session.open_ts, NATIVE) is value
    assert parsed == before and value.metadata.original_basis_gross_ceiling == Decimal(".005")
    assert tuple(row.route for row in value.metadata.rows) == ROUTES
    assert [t.route for t in value.targets] == ["AAPL/NAS", "JPM/NYS"]
    assert [core._target_instrument(t, NATIVE).order_exchange for t in value.targets] == [
        "NASD", "NYSE",
    ]
    assert all("RELATIVE_SIGN_ONLY_NON_PARITY" in t.proposal.reason for t in value.targets)
    assert value.execution_basis == weights.RAW_OPEN_ELAPSED3_EXECUTION_BASIS
    assert weights.model_paper_weights_horizon_profile(PROFILE) == MODEL_PAPER_ELAPSED_H3_PROFILE


@pytest.mark.parametrize("count", range(18))
def test_exact_equal_weights_and_existing_binary64_cash_residual(count):
    parsed, _ = forecast(metadata(), selected=range(count))
    for row in parsed["score_rows"][:count]:
        row["expected_excess_return_open_e_to_open_e_plus_3"] = 1e-300
    rows = policy.rows_from_forecast(parsed)
    positive = [row.weight for row in rows[:17] if row.weight > 0]
    assert len(positive) == count and len(set(positive)) == int(count > 0)
    mass = sum((Fraction(row.weight) for row in rows[:17]), Fraction())
    assert mass <= 1
    expected_cash = Decimal(repr(float(1 - mass)))
    assert struct.pack("<d", float(rows[-1].weight)) == struct.pack("<d", float(expected_cash))
    assert rows == weights.append_derived_cash_h3_row(rows[:17])
    with localcontext() as context:
        context.prec = 4
        assert policy.rows_from_forecast(parsed) == rows
    value = make(selected=range(count))
    assert len(value.targets) == count
    assert sum((Fraction(t.proposal.target_exposure) for t in value.targets), Fraction()) <= (
        Fraction(value.metadata.original_basis_gross_ceiling)
    )
    if not count:
        assert rows[-1].weight == 1 and value.targets == ()


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -float("inf"), True, 0, "0"])
def test_missing_nonfinite_or_nonfloat_is_unavailable_not_cash(bad):
    meta = metadata()
    parsed, scores = forecast(meta, selected=())
    parsed["score_rows"][0]["expected_excess_return_open_e_to_open_e_plus_3"] = bad
    assert policy.rows_from_forecast(parsed) is None
    assert policy.prepare_raw_open_proposal(
        parsed, scores, meta, entry_session=window(date(2026, 11, 4)),
        exit_session=window(date(2026, 11, 9)),
    ) is None


@pytest.mark.parametrize("fault", [
    "empty", "unknown", "short", "reorder", "route", "units", "target", "checkpoint", "slot",
])
def test_wrong_source_axis_or_unknown_cannot_create_allcash(fault):
    parsed, _ = forecast(metadata(), selected=())
    if fault == "empty":
        parsed = {}
    elif fault == "unknown":
        parsed["score_rows"][0]["model_score_known"] = False
    elif fault == "short":
        parsed["score_rows"].pop()
    elif fault == "reorder":
        parsed["score_rows"].reverse()
    elif fault == "route":
        parsed["score_rows"][8]["route"] = "JPM/NAS"
    elif fault == "units":
        parsed["score_rows"][0]["score_units"] = "absolute_profit"
    elif fault == "target":
        parsed["forecast_horizon"] = "inclusive3"
    elif fault == "checkpoint":
        parsed["model_checkpoint_sha256"] = "f" * 64
    else:
        parsed["score_rows"][0]["slot"] = False
    assert policy.rows_from_forecast(parsed) is None


@pytest.mark.parametrize("fault", [
    "clock", "naive", "future", "before_inference", "stale", "model", "native_symbol",
    "native_schema", "native_clock", "native_missing", "native_action", "native_expiry",
])
def test_noncausal_or_mismatched_native_forecast_unavailable(fault):
    meta = metadata()
    parsed, scores = forecast(meta)
    entry, exit_session = window(date(2026, 11, 4)), window(date(2026, 11, 9))
    if fault in {"clock", "naive", "future", "before_inference"}:
        parsed["inference_observed_at"] = {
            "clock": "invalid", "naive": "2026-11-04T13:30:00",
            "future": (meta.inference_completed_at + timedelta(seconds=1)).isoformat(),
            "before_inference": (meta.inference_started_at - timedelta(seconds=1)).isoformat(),
        }[fault]
    elif fault == "stale":
        meta = metadata(date(2026, 11, 5), date(2026, 11, 10))
        entry, exit_session = window(date(2026, 11, 5)), window(date(2026, 11, 10))
    elif fault == "model":
        meta = replace(meta, model_ref=old.PIN)
    else:
        change = {
            "native_symbol": dict(symbol="AMD"),
            "native_schema": dict(feature_schema_id="another-schema"),
            "native_clock": dict(decided_at=meta.inference_completed_at - timedelta(seconds=1)),
            "native_missing": dict(input_status="missing"),
            "native_action": dict(action="hold"),
            "native_expiry": dict(valid_until=meta.inference_completed_at + timedelta(seconds=1)),
        }[fault]
        scores = (replace(scores[0], **change), *scores[1:])
    assert policy.prepare_raw_open_proposal(
        parsed, scores, meta, entry_session=entry, exit_session=exit_session,
    ) is None


@pytest.mark.parametrize("first,last,open_hour,exit_hour,close_hour", [
    (date(2026, 11, 4), date(2026, 11, 9), 14, 14, 21),
    (date(2026, 11, 23), date(2026, 11, 27), 14, 14, 18),
    (date(2026, 11, 24), date(2026, 11, 30), 14, 14, 21),
    (date(2026, 10, 30), date(2026, 11, 4), 13, 14, 21),
    (date(2026, 3, 6), date(2026, 3, 11), 14, 13, 20),
])
def test_four_official_sessions_holiday_halfday_and_both_dst_boundaries(
    first, last, open_hour, exit_hour, close_hour,
):
    value = make(first, last)
    bands = weights.model_paper_us_cash_h3_ops_window(value)
    assert value.entry_session.open_ts.hour == open_hour
    assert value.exit_session.open_ts.hour == exit_hour
    assert value.exit_session.close_ts.hour == close_hour
    assert bands.entry_start == value.entry_session.open_ts
    assert bands.entry_end == bands.entry_start + timedelta(minutes=5)
    assert bands.exit_start == value.exit_session.open_ts == value.metadata.exit_not_before
    assert bands.exit_end == bands.exit_start + timedelta(minutes=5)


@pytest.mark.parametrize("last", [date(2026, 11, 6), date(2026, 11, 10)])
def test_inclusive_three_or_elapsed_four_cannot_retag_elapsed_three(last):
    assert make(last=last) is None


@pytest.mark.parametrize("field", ["execution_basis", "profile", "target", "unknown"])
def test_rehashed_forgery_or_old_profile_cannot_pass_strict_codec(field):
    value = make()
    document = json.loads(weights.serialize_model_paper_weights_input(value))
    if field == "execution_basis":
        document[field] = weights.US_CASH_H3_OPS_EXECUTION_BASIS
    elif field == "profile":
        document[field] = weights.MODEL_PAPER_WEIGHTS_US_CASH_3_SESSION_OPS_PROFILE
    elif field == "target":
        document["targets"][0]["proposal"]["valid_until"] = value.entry_session.close_ts.isoformat()
    else:
        document["metadata"]["rows"][1]["feature_known"] = False
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError):
        weights.load_model_paper_weights_input(
            raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
            expected_policy_ref=value.policy_ref,
        )


@pytest.mark.parametrize("seconds", [-1, 300, 1800])
def test_outside_entry_open5_no_journal_no_client_no_bank_effect(h, seconds):
    h["now"] = h["data"].entry_session.open_ts + timedelta(seconds=seconds)
    before = native.bank_bytes(h)
    assert native.run(h).reason == "cycle_session_invalid"
    assert native.record(h) is None and not h["submits"] and not h["factories"]
    assert native.bank_bytes(h) == before


def test_known_nonpositive_allcash_has_no_native_effect(h):
    value = make(selected=())
    native.bind(h, value, NATIVE)
    h["now"] = value.entry_session.open_ts
    before = native.bank_bytes(h)
    assert native.run(h).status == "no_intent"
    assert native.record(h) is None and not h["submits"] and not h["factories"]
    assert native.bank_bytes(h) == before


@pytest.mark.parametrize("score", [0.0, -0.0, -1e-300])
def test_known_zero_and_negative_scores_are_valid_cash(score):
    parsed, _ = forecast(metadata())
    for row in parsed["score_rows"]:
        row["expected_excess_return_open_e_to_open_e_plus_3"] = score
    rows = policy.rows_from_forecast(parsed)
    assert rows[-1].weight == 1 and all(row.weight == 0 for row in rows[:17])


def test_missing_open5_does_not_erase_owned_exit_on_later_official_session(h):
    assert native.visit_all(h)[-1].status == "hold"
    value = h["data"]
    h["now"] = value.exit_session.open_ts + timedelta(minutes=5)
    retained, before = copy.deepcopy(native.record(h)), native.bank_bytes(h)
    factories = h["factories"]
    assert native.run(h, target_loader=forbidden).reason == "outside_declared_session"
    assert native.record(h) == retained and native.bank_bytes(h) == before
    assert h["factories"] == factories
    later = window(date(2026, 11, 10))
    band = weights.model_paper_us_cash_h3_ops_window(value, operational_session=later)
    assert band.exit_start == later.open_ts
    assert band.exit_end == later.open_ts + timedelta(minutes=5)
    assert value.exit_session == window(date(2026, 11, 9))
    h["now"] = later.open_ts + timedelta(minutes=4)
    assert native.visit_all(h, target_loader=forbidden)[-1].status == "complete"
    assert all(i.valid_until == band.exit_end for i in h["submits"][2:])


def test_real_native_nys_timed_exit_caps_ttl_keeps_one_bank_and_old_unknown(h):
    original = core.budget._load_binding(h["root"])
    original_states = {p.name: p.read_bytes() for p in h["root"].glob("*.json")}
    assert native.visit_all(h)[-1].status == "hold"
    assert [i.exchange for i in h["submits"]] == ["NASD", "NYSE"]
    h["now"] = h["data"].exit_session.open_ts + timedelta(minutes=4)
    assert native.visit_all(h, target_loader=forbidden)[-1].status == "complete"
    sells = h["submits"][2:]
    assert len(sells) == 2 and {i.exchange for i in sells} == {"NASD", "NYSE"}
    assert all(i.side == "sell" for i in sells)
    assert all(i.valid_until == h["data"].exit_session.open_ts + timedelta(minutes=5)
               for i in sells)
    after = core.budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "qqq", "orders", "portfolio", "legacy_spy"):
        assert after[key] == original[key]
    assert all((h["root"] / name).read_bytes() == raw
               for name, raw in original_states.items() if name != core.budget.BUDGET_FILE)


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_exact_unknown_recovery_precedes_loader_no_ttl_renewal_or_cash_release(h, side):
    if side == "sell":
        assert native.visit_all(h)[-1].status == "hold"
        h["now"] = h["data"].exit_session.open_ts + timedelta(minutes=4)
    h["unknown"] = True
    assert native.run(h).status == "pending"
    pending = copy.deepcopy(native.record(h)["pending"])
    before = native.bank_bytes(h)
    h["now"] = h["data"].exit_session.close_ts + timedelta(days=1)
    submits = tuple(h["submits"])
    for _ in range(2):
        assert native.run(h, target_loader=forbidden).status == "pending"
    assert native.record(h)["pending"]["arguments"] == pending["arguments"]
    assert tuple(h["submits"]) == submits and native.bank_bytes(h) == before
    assert core._unpack(pending["arguments"])["valid_until"] <= (
        h["data"].entry_session.open_ts if side == "buy" else h["data"].exit_session.open_ts
    ) + timedelta(minutes=5)


@pytest.mark.parametrize("fault", ["stale", "foreign", "late_funds"])
def test_native_risk_denial_never_submits_or_reweights(h, fault):
    h[fault] = True
    native.visit_all(h)
    assert not h["submits"]
    assert core._unpack(native.record(h)["active"]["model_input"]) == h["data"]
    if fault == "late_funds":
        assert native.record(h)["pending"] is not None


def account_visit(h, *, mode="entry", loader=None):
    value, now = h["data"], h["now"]
    slot = PaperRoundSlot(
        "invented-raw-open", "entry" if mode == "entry" else "exit", now,
        now + timedelta(minutes=1), value.input_ref, value.policy_ref,
    )
    cohort = account.PaperAccountCohort(slot, old.PIN, h["initial"]["basis_ref"], NATIVE, mode)
    paths = {k: v for k, v in h["call"].items() if k.endswith(("_path", "_root"))}
    return account.run_native_account_session(
        cohort=cohort, paths=paths, expected_account_ref=h["call"]["expected_account_ref"],
        target_loader=h["call"]["target_loader"] if loader is None else loader,
        client_factory=h["call"]["client_factory"], configure_early_exit=forbidden,
        admit=lambda: True, deadline=slot.ends_at, clock=lambda: h["now"], monotonic=lambda: 0,
    )


@pytest.mark.parametrize("skip_first", [False, True])
def test_account_pending_first_and_later_cohort_reuse_original_bank(h, monkeypatch, skip_first):
    assert account_visit(h)["stop"] == "yield_after_first_native_leg"
    assert account_visit(h, loader=forbidden)["stop"] == "yield_after_first_native_leg"
    h["now"] = h["data"].exit_session.open_ts
    for _ in range(2):
        account_visit(h, mode="exit", loader=forbidden)
    assert native.record(h)["active"] is None
    before = core.budget._load_binding(h["root"])
    value = make(date(2026, 11, 11), date(2026, 11, 16))
    native.bind(h, value, NATIVE)
    h["now"] = value.entry_session.open_ts
    h["unknown"] = True
    if skip_first:
        preview = us.VenueSyntheticClient.stock_preview_snapshot

        def skip(client, **kwargs):
            if client.instrument.symbol == "AAPL":
                raise core.KisPaperReadOnlyError("quote_timestamp_unavailable")
            return preview(client, **kwargs)

        monkeypatch.setattr(us.VenueSyntheticClient, "stock_preview_snapshot", skip)
    result = account_visit(h)
    assert result["pending"] and result["skipped"] == int(skip_first)
    saved = copy.deepcopy(native.record(h)["pending"]["arguments"])
    h["now"] = value.exit_session.close_ts + timedelta(days=1)
    result = account_visit(h, mode="recovery", loader=forbidden)
    assert result["stop"] == "initial_pending_recovery_once" and result["pending"]
    assert native.record(h)["pending"]["arguments"] == saved
    after = core.budget._load_binding(h["root"])
    for key in ("basis_ref", "allocated_usd", "qqq", "orders", "portfolio", "legacy_spy"):
        assert after[key] == before[key]


@pytest.mark.parametrize("profile,horizon,golden", [
    (weights.MODEL_PAPER_WEIGHTS_PROFILE, 19,
     "e89ddaeaecd6d0b5a8b2fa88d1dab62fdd8b6aaa7589a42a4387a8b9d328dce3"),
    (weights.MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE, 19,
     "fee27cb6189f6b451bd97cdb666b19225a8b29e1931279a7d8459b5022f5e926"),
    (weights.MODEL_PAPER_WEIGHTS_5_SESSION_PROFILE, 4,
     "a10a49803664b4fac92518c9795d685a45b3508cf4e51d1f96795b0a7901cdad"),
    (weights.MODEL_PAPER_WEIGHTS_CASH_5_SESSION_PROFILE, 4,
     "7d24692263364ddc3dc400e7790944ac35ca62490b056f1c4353fc661eeffb83"),
    (weights.MODEL_PAPER_WEIGHTS_US_5_SESSION_PROFILE, 4,
     "76ee76df83412dc00ac9a78c37756ef465e4562f52a7cf0b4aa9644c8c5fd376"),
    (weights.MODEL_PAPER_WEIGHTS_US_CASH_3_SESSION_OPS_PROFILE, 2,
     "badbded90e2c9894dba9a7f0d79e21b6248a2f9a0068c38b9c1b80825815e277"),
    (weights.MODEL_PAPER_WEIGHTS_ELAPSED_H1_PROFILE, 1,
     "4f7b29c8cee4792dcab2aa7276975997ca27328ff500c03fb3c252d36dc8b204"),
    (weights.MODEL_PAPER_WEIGHTS_ELAPSED_H3_PROFILE, 3,
     "3be6db018b5afe6eb5126e1c4948d6b450f3f38ea158bd0e13a0146cca408ffc"),
    (weights.MODEL_PAPER_WEIGHTS_ELAPSED_H5_PROFILE, 5,
     "d3562aa317b1e724b9c88ac29dcd1a7ecb429958ea9f1013013f474295b06d2d"),
    (weights.MODEL_PAPER_WEIGHTS_CASH_ELAPSED_H3_PROFILE, 3,
     "edfaf7fdc52c7e5f997ef2fbc878a2e7bed68595e0766cdb5b93e19b6b0cb284"),
])
def test_old_profile_binary_goldens_unchanged(profile, horizon, golden):
    first = date(2026, 10, 1)
    sessions = [window(first + timedelta(days=i)) for i in range(45)
                if us_equity_2026_session(first + timedelta(days=i))]
    rows = (
        weights.ModelPaperWeightRow(0, "AAPL/NAS", True, Decimal(".5")),
        weights.ModelPaperWeightRow(1, "AMD/NAS", True, Decimal(".5")),
    )
    if profile == weights.MODEL_PAPER_WEIGHTS_US_CASH_3_SESSION_OPS_PROFILE:
        rows = inclusive._rows((0, 8))
    elif profile == weights.MODEL_PAPER_WEIGHTS_CASH_ELAPSED_H3_PROFILE:
        rows = inclusive._rows((0,))
    elif profile == weights.MODEL_PAPER_WEIGHTS_CASH_5_SESSION_PROFILE:
        rows = (*rows, weights.ModelPaperWeightRow(2, "CASH", True, Decimal(0)))
    meta = old._metadata(sessions[0], sessions[horizon], rows)
    if profile == weights.MODEL_PAPER_WEIGHTS_H20_EARLY_EXIT_PROFILE:
        meta = replace(meta, exit_not_before=sessions[horizon].close_ts - timedelta(minutes=45))
    value = weights.prepare_model_paper_weights_input(
        meta, entry_session=sessions[0], exit_session=sessions[horizon], profile=profile,
    )
    assert hashlib.sha256(weights.serialize_model_paper_weights_input(value)).hexdigest() == golden
