"""Two synthetic NYSE sessions; no model decoding, fits, providers or orders."""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import os
import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_UP, Decimal, Inexact, Rounded, localcontext
from pathlib import Path

import pandas_market_calendars as calendars
import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.execution.kis_paper_stock_quote import KisPaperStockInstrument
from thericher_v2.research import kis_stock_relative_features as feature
from thericher_v2.research import kis_stock_session_decision as k
from thericher_v2.research.decision_receipt import DecisionReceiptReferences

KEYS = tuple(f"opaque-{i:03}" for i in range(128))
D = Decimal


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("provider_call_forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)


def make_case(session=date(2026, 10, 12)):
    # Calendar acquisition is the installed pure library, never market values.
    schedule = calendars.get_calendar("NYSE").schedule("2026-01-01", session.isoformat()).tail(113)
    plan = feature.FeaturePlan(
        tuple(day.date() for day in schedule.index),
        KEYS,
        tuple(row.to_pydatetime() for row in schedule.market_open),
        tuple(row.to_pydatetime() for row in schedule.market_close),
    )
    instruments = {
        key: k.SessionInstrument(key, "SYN" + chr(65 + i // 26) + chr(65 + i % 26))
        for i, key in enumerate(KEYS)
    }
    as_of = plan.open_clocks[-1] - timedelta(hours=2)
    manifest = "sha256:" + ("c" if session.month == 10 else "e") * 64
    envelope = k.SessionEnvelope(
        plan=plan,
        instruments=instruments,
        observed_at_by_key={key: plan.close_clocks[-2] + timedelta(minutes=1) for key in KEYS},
        input_anchor_date=plan.sessions[-2],
        input_manifest_sha256=manifest,
        model_sha256=k.MODEL_SHA256,
        instrument_map_sha256=k.instrument_map_sha256(instruments),
        calendar_sha256=k.calendar_sha256(plan),
        references=DecisionReceiptReferences(
            "ref:" + "a" * 64,
            "ref:" + "b" * 64,
            manifest,
            "ref:" + ("d" if session.month == 10 else "f") * 64,
        ),
        as_of=as_of,
    )
    bars = {}
    for key_index, key in enumerate(KEYS):
        for index, day in enumerate(plan.sessions[51:112]):
            opened = D(100 + key_index) + D(index) / 10
            closed = opened + D((index + key_index) % 5 - 2) / 100
            bars[key, day] = Bar(
                symbol=instruments[key].symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(day, time(), UTC),
                open=opened,
                close=closed,
                high=max(opened, closed) + 1,
                low=min(opened, closed) - 1,
                volume=D(100000),
            )
    return envelope, bars


@pytest.fixture(scope="module")
def case():
    return make_case()


def decide(case, *, envelope=None, source=None, scorer=None, clocks=None):
    frozen, bars = case
    frozen = envelope or frozen
    moments = iter(
        clocks
        or [frozen.as_of, frozen.as_of + timedelta(seconds=1), frozen.as_of + timedelta(seconds=2)]
    )
    return k.decide_session(
        frozen,
        source or (lambda key, day: bars.get((key, day))),
        scorer=scorer or (lambda batch: {key: 0.5 for key in batch.keys}),
        clock=lambda: next(moments),
    )


def test_two_distinct_sessions_change_top1_without_renewing_original_refs(case):
    first = decide(case, scorer=lambda b: {key: float(key == KEYS[3]) for key in b.keys})
    original = (first.envelope.binding_sha256, first.proposal, first.receipt)
    second_case = make_case(date(2026, 11, 27))
    second = decide(second_case, scorer=lambda b: {key: float(key == KEYS[7]) for key in b.keys})
    assert first.status == second.status == "prepared"
    assert first.selected_key == KEYS[3] and second.selected_key == KEYS[7]
    assert first.proposal.target_exposure == second.proposal.target_exposure == D(".01")
    assert first.proposal.confidence == second.proposal.confidence == 0
    assert second.proposal.valid_until == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert first.proposal.valid_until == datetime(2026, 10, 12, 20, tzinfo=UTC)
    assert first.envelope.model_sha256 == second.envelope.model_sha256 == k.MODEL_SHA256
    assert first.receipt.model_ref == second.receipt.model_ref
    assert first.receipt.proposal_ref != second.receipt.proposal_ref
    assert original == (first.envelope.binding_sha256, first.proposal, first.receipt)


def test_only_prior61_accessed_once_missing_oldest12_does_not_block(case):
    calls = []
    envelope, bars = case

    def source(key, day):
        assert day in envelope.plan.sessions[51:112]
        calls.append((key, day))
        return bars[key, day]

    result = decide(case, source=source)
    assert result.status == "prepared" and type(result.feature_seal) is feature.FeatureSeal
    assert len(calls) == len(set(calls)) == 128 * 61
    assert not any(day in envelope.plan.sessions[:12] for _, day in calls)
    assert result.feature_seal.plan is envelope.plan
    assert len(envelope.plan.sessions) == 113
    assert result.feature_seal.entry_index == 112 and result.feature_seal.exit_session is None


def test_frozen_scorer_input_is_only_keys_and_past20_sequences(case):
    calls = []
    frozen, bars = case

    def source(key, day):
        calls.append((key, day))
        return bars[key, day]

    def scorer(batch):
        assert len(calls) == 128 * 61 and batch.keys == KEYS
        assert set(batch.__slots__) == {"keys", "sequences"}
        assert len(batch.sequences) == 128
        assert all(
            len(sequence) == 20 and all(len(step) == 2 for step in sequence)
            for sequence in batch.sequences
        )
        with pytest.raises(FrozenInstanceError):
            batch.keys = ()
        with pytest.raises(TypeError):
            batch.sequences[0][0] = (1, 1)
        return dict.fromkeys(batch.keys, 0.5)

    result = decide(case, source=source, scorer=scorer)
    shared = feature.features(
        frozen.plan, 112, lambda key, day: bars[key, day], include_sequence=True
    )
    assert result.feature_seal.sequences == shared.sequences
    assert result.selected_key == KEYS[0]


@pytest.mark.parametrize("fault", ["model", "map", "calendar", "references", "anchor"])
def test_scope_drift_is_no_intent_before_callbacks(case, fault):
    envelope, _ = case
    if fault == "references":
        altered = replace(envelope.references, input_manifest_ref="sha256:" + "f" * 64)
        envelope = replace(envelope, references=altered)
    elif fault == "anchor":
        envelope = replace(envelope, input_anchor_date=envelope.plan.sessions[-3])
    else:
        name = dict(model="model_sha256", map="instrument_map_sha256", calendar="calendar_sha256")[
            fault
        ]
        envelope = replace(envelope, **{name: "sha256:" + "f" * 64})
    result = decide(case, envelope=envelope, source=lambda *a: pytest.fail("unbound_past"))
    assert result.status == "no_intent" and result.proposal is result.receipt is None


@pytest.mark.parametrize("fault", ["future", "stale", "missing_key", "foreign_key"])
def test_observation_scope_mutations_do_not_read_source(case, fault):
    envelope, _ = case
    observed = dict(envelope.observed_at_by_key)
    if fault == "future":
        observed[KEYS[0]] = envelope.as_of + timedelta(microseconds=1)
    elif fault == "stale":
        observed[KEYS[0]] = envelope.plan.close_clocks[-2] - timedelta(microseconds=1)
    elif fault == "missing_key":
        observed.pop(KEYS[0])
    else:
        observed["foreign"] = envelope.as_of
    result = decide(
        case,
        envelope=replace(envelope, observed_at_by_key=observed),
        source=lambda *a: pytest.fail("invalid_observation"),
    )
    assert result.status == "no_intent"


@pytest.mark.parametrize("stage", [0, 1, 2])
def test_official_open_boundary_rejects_at_every_model_stage(case, stage):
    envelope, _ = case
    moments = [envelope.as_of + timedelta(seconds=i) for i in range(3)]
    moments[stage] = envelope.plan.open_clocks[-1]
    result = decide(case, clocks=moments)
    assert result.status == "no_intent" and result.reason == k.Reason.LATE
    assert result.proposal is result.receipt is None


@pytest.mark.parametrize("stage", [0, 1, 2])
def test_clock_retreat_never_backdates_model_success(case, stage):
    envelope, _ = case
    moments = [envelope.as_of + timedelta(seconds=i) for i in range(3)]
    moments[stage] = envelope.as_of - timedelta(microseconds=1)
    result = decide(case, clocks=moments)
    assert result.status == "no_intent" and result.reason == k.Reason.CLOCK


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1, True, "0.5", D(".5")])
def test_invalid_probabilities_are_categorical_no_intent(case, value):
    result = decide(case, scorer=lambda batch: dict.fromkeys(batch.keys, value))
    assert result.reason == k.Reason.SCORES and result.status == "no_intent"


@pytest.mark.parametrize("fault", ["missing", "extra", "not_mapping"])
def test_scores_must_cover_exact_frozen_eligible_peers(case, fault):
    def scorer(batch):
        result = dict.fromkeys(batch.keys, 0.5)
        if fault == "missing":
            result.pop(batch.keys[0])
        elif fault == "extra":
            result["foreign"] = 0.5
        else:
            return list(result.values())
        return result

    assert decide(case, scorer=scorer).reason == k.Reason.SCORES


def test_missing_peer_is_not_adopted_or_used_to_mask_other_available_peers(case):
    envelope, bars = case
    result = decide(case, source=lambda key, day: None if key == KEYS[0] else bars[key, day])
    assert result.status == "prepared" and len(result.feature_seal.rows) == 127
    assert KEYS[0] not in dict(result.scores) and result.selected_key == KEYS[1]
    observed = dict(envelope.observed_at_by_key)
    observed[KEYS[0]] = None
    result = decide(
        case,
        envelope=replace(envelope, observed_at_by_key=observed),
        source=lambda key, day: (
            bars[key, day] if key != KEYS[0] else pytest.fail("missing_clock_read")
        ),
    )
    assert result.status == "prepared" and result.selected_key == KEYS[1]


def test_fewer10_never_calls_scorer_or_creates_proposal(case):
    _, bars = case
    result = decide(
        case,
        source=lambda key, day: bars[key, day] if key in KEYS[:9] else None,
        scorer=lambda b: pytest.fail("too_few_scorer"),
    )
    assert result.status == "no_intent" and result.reason == k.Reason.FEWER


@pytest.mark.parametrize("fault", ["price", "volume", "jump"])
def test_fixed_prior20_screen_excludes_only_failing_key_before_scoring(case, fault):
    envelope, bars = case
    changed = dict(bars)
    days = envelope.plan.sessions[-21:-1]
    for day in days:
        bar = bars[KEYS[0], day]
        if fault == "price":
            changed[KEYS[0], day] = replace(bar, open=D(4), close=D(4), high=D(4), low=D(4))
        elif fault == "volume":
            changed[KEYS[0], day] = replace(bar, volume=D(1))
    if fault == "jump":
        bar = bars[KEYS[0], days[-1]]
        changed[KEYS[0], days[-1]] = replace(
            bar, open=D(200), close=D(200), high=D(200), low=D(200)
        )
    result = decide(case, source=lambda key, day: changed[key, day])
    assert result.status == "prepared" and KEYS[0] not in dict(result.scores)


def test_wrong_symbol_is_no_intent_not_opaque_key_adoption(case):
    _, bars = case
    result = decide(
        case,
        source=lambda key, day: (
            replace(bars[key, day], symbol="FOREIGN") if key == KEYS[0] else bars[key, day]
        ),
    )
    assert result.reason == k.Reason.IDENTITY


def test_hostile_decimal_context_and_sticky_flags_do_not_change_sequences(case):
    expected = decide(case)
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = context.traps[Rounded] = True
        context.flags[Inexact] = context.flags[Rounded] = True
        before = (context.prec, context.rounding, dict(context.flags), dict(context.traps))
        result = decide(case)
        assert result.proposal == expected.proposal and result.feature_seal == expected.feature_seal
        assert before == (context.prec, context.rounding, dict(context.flags), dict(context.traps))


def test_envelope_detaches_maps_and_results_use_existing_typed_contracts(case):
    envelope, _ = case
    instruments, observations = dict(envelope.instruments), dict(envelope.observed_at_by_key)
    frozen = replace(envelope, instruments=instruments, observed_at_by_key=observations)
    instruments.clear()
    observations.clear()
    result = decide(case, envelope=frozen)
    assert type(result.proposal) is TargetExposureProposal
    assert result.receipt.input_manifest_ref == envelope.input_manifest_sha256
    assert (
        result.proposal.proposal_id
        == result.receipt.proposal_ref
        == envelope.references.proposal_ref
    )
    assert result.proposal.decided_at == result.model_completed_at > envelope.as_of
    assert result.receipt.decided_at == result.model_completed_at
    assert result.model_started_at == envelope.as_of + timedelta(seconds=1)
    assert result.model_completed_at == envelope.as_of + timedelta(seconds=2)
    assert result.proposal.feature_window_end == envelope.plan.close_clocks[-2]
    assert envelope.instruments[KEYS[0]].symbol not in repr(result)
    assert "scores" not in result.safe_facts() and "symbol" not in result.safe_facts()
    with pytest.raises(FrozenInstanceError):
        frozen.input_anchor_date = date(2000, 1, 1)


@pytest.mark.parametrize("exchange", ["NYSE", "AMEX", "NAS", "LIVE"])
def test_instrument_scope_is_exact_nasd_not_generic_us(exchange):
    with pytest.raises(ValueError):
        k.SessionInstrument(KEYS[0], "SYNAA", exchange)


def test_old_envelope_not_renewed_by_new_calendar_or_changed_now(case):
    envelope, _ = case
    later, _ = make_case(date(2026, 11, 27))
    reused = replace(envelope, plan=later.plan, calendar_sha256=later.calendar_sha256)
    result = decide(case, envelope=reused, source=lambda *a: pytest.fail("old_input_read"))
    assert result.reason == k.Reason.STALE
    assert envelope.input_anchor_date == case[0].input_anchor_date


def test_scorer_failure_has_no_freeform_exception_output(case):
    def broken(batch):
        raise RuntimeError("synthetic-private-message")

    result = decide(case, scorer=broken)
    assert result.reason == k.Reason.SCORER and "synthetic-private-message" not in str(
        result.safe_facts()
    )


def test_no_fs_model_runtime_or_target_imports():
    tree = ast.parse(Path(k.__file__).read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports & {"os", "pathlib", "torch", "numpy", "subprocess", "socket", "importlib"}
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "target_labels" for node in ast.walk(tree)
    )


def test_pure_decision_does_not_read_files_or_environment(case, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pure_decision_io")

    with monkeypatch.context() as patch:
        for owner, name in (
            (builtins, "open"),
            (Path, "open"),
            (Path, "read_bytes"),
            (Path, "write_bytes"),
            (os, "getenv"),
        ):
            patch.setattr(owner, name, forbidden)
        result = decide(case)
    assert result.status == "prepared"


@pytest.mark.parametrize("fault", ["reason", "symbol", "quantity", "expiry"])
def test_result_constructor_cannot_fabricate_mismatched_prepared_proposal(case, fault):
    result = decide(case)
    with pytest.raises(ValueError):
        if fault == "reason":
            replace(result, reason=k.Reason.LATE)
        else:
            changes = dict(
                symbol=dict(symbol="FOREIGN"),
                quantity=dict(target_exposure=D(".1")),
                expiry=dict(valid_until=result.proposal.valid_until + timedelta(seconds=1)),
            )
            replace(result, proposal=replace(result.proposal, **changes[fault]))


def test_screen_fixed_exact_boundaries_and_unused_older_volume(case):
    envelope, bars = case
    selected = tuple(bars[KEYS[0], day] for day in envelope.plan.sessions[-21:-1])
    boundary = tuple(
        replace(bar, open=D(10), close=D(10), high=D(10), low=D(10), volume=D(500000))
        for bar in selected
    )
    assert k._screen(boundary)
    assert not k._screen(
        boundary[:-1] + (replace(boundary[-1], open=D(15), close=D(15), high=D(15), low=D(15)),)
    )
    assert not k._screen(
        tuple(
            replace(bar, open=D("4.9999"), close=D("4.9999"), high=D("4.9999"), low=D("4.9999"))
            for bar in boundary
        )
    )
    assert not k._screen(tuple(replace(bar, volume=D(499999)) for bar in boundary))
    changed = dict(bars)
    for day in envelope.plan.sessions[51:92]:
        changed[KEYS[0], day] = replace(changed[KEYS[0], day], volume=0)
    result = decide(case, source=lambda key, day: changed[key, day])
    assert result.status == "prepared" and KEYS[0] in dict(result.scores)


@pytest.mark.parametrize("field,value", [("volume", D(0)), ("close", D(1)), ("symbol", "FOREIGN")])
def test_later_key_callbacks_cannot_mutate_captured_bar_scalars(case, field, value):
    envelope, bars = case
    baseline = decide(case)
    provider_owned = {pair: replace(bar) for pair, bar in bars.items()}
    calls = []

    def source(key, day):
        calls.append((key, day))
        if key == KEYS[1] and day == envelope.plan.sessions[51]:
            for earlier in envelope.plan.sessions[51:112]:
                object.__setattr__(provider_owned[KEYS[0], earlier], field, value)
        return provider_owned[key, day]

    result = decide(case, source=source)
    assert result.status == "prepared"
    assert result.feature_seal == baseline.feature_seal
    assert result.scores == baseline.scores and result.selected_key == baseline.selected_key
    assert len(calls) == len(set(calls)) == 128 * 61


def test_new_decision_available_at_actual_scorer_completion_not_input_cutoff(case):
    envelope, _ = case
    completed = envelope.as_of + timedelta(minutes=3)
    result = decide(
        case,
        clocks=[envelope.as_of, envelope.as_of + timedelta(seconds=1), completed],
    )
    assert result.status == "prepared"
    assert result.envelope.as_of == envelope.as_of
    assert result.proposal.decided_at == result.receipt.decided_at == completed
    assert result.proposal.feature_window_end == envelope.plan.close_clocks[-2]
    assert result.proposal.valid_until == envelope.plan.close_clocks[-1]


def test_actual_initial_clock_cannot_retreat_even_when_start_is_after_input_cutoff(case):
    envelope, _ = case
    result = decide(
        case,
        clocks=[
            envelope.as_of + timedelta(minutes=5),
            envelope.as_of + timedelta(seconds=1),
            envelope.as_of + timedelta(seconds=2),
        ],
        scorer=lambda batch: pytest.fail("retreated_clock_scorer"),
    )
    assert result.status == "no_intent" and result.reason is k.Reason.CLOCK


@pytest.mark.parametrize("symbol", ["SYN003", "ABCDEFGHIJK", "abc", "A.B", "\u00c4APL"])
def test_symbol_scope_matches_existing_kis_stock_grammar_without_broadening(symbol):
    with pytest.raises(ValueError):
        k.SessionInstrument(KEYS[0], symbol)


def test_all128_supplied_session_symbols_cross_existing_paper_instrument_boundary(case):
    envelope, _ = case
    for instrument in envelope.instruments.values():
        bound = KisPaperStockInstrument(instrument.symbol, "ref:" + "a" * 64)
        assert bound.symbol == instrument.symbol and bound.order_exchange == instrument.exchange
    assert len({instrument.symbol for instrument in envelope.instruments.values()}) == 128


@pytest.mark.parametrize(
    "field",
    [
        "model",
        "map",
        "calendar",
        "manifest",
        "anchor",
        "past_clock",
        "missing_key",
        "future",
        "identity",
    ],
)
def test_prepared_constructor_revalidates_model_and_all_envelope_scope_bindings(case, field):
    result = decide(case)
    envelope = result.envelope
    if field in {"model", "map", "calendar", "manifest"}:
        name = {
            "model": "model_sha256",
            "map": "instrument_map_sha256",
            "calendar": "calendar_sha256",
            "manifest": "input_manifest_sha256",
        }[field]
        envelope = replace(envelope, **{name: "sha256:" + "f" * 64})
    elif field == "anchor":
        envelope = replace(envelope, input_anchor_date=envelope.plan.sessions[-3])
    elif field == "past_clock":
        envelope = replace(envelope, as_of=envelope.plan.close_clocks[-2] - timedelta(seconds=1))
    elif field == "identity":
        identities = dict(envelope.instruments)
        identities[KEYS[1]] = replace(identities[KEYS[1]], symbol="FOREIGN")
        envelope = replace(
            envelope,
            instruments=identities,
            instrument_map_sha256=k.instrument_map_sha256(identities),
        )
    else:
        clocks = dict(envelope.observed_at_by_key)
        if field == "missing_key":
            clocks.pop(KEYS[0])
        else:
            clocks[KEYS[0]] = envelope.as_of + timedelta(seconds=1)
        envelope = replace(envelope, observed_at_by_key=clocks)
    with pytest.raises(ValueError):
        replace(result, envelope=envelope)


def bound_route_envelope(case, *, supported=KEYS[:125], unsupported=()):
    original, _ = case
    categories = {
        key: (
            k.RouteCategory.SUPPORTED
            if key in supported
            else k.RouteCategory.UNSUPPORTED
            if key in unsupported
            else k.RouteCategory.UNVERIFIED
        )
        for key in KEYS
    }
    instruments = {
        key: replace(instrument, exchange="NASD" if key in supported else None)
        for key, instrument in original.instruments.items()
    }
    pins = {"official-reference": "sha256:" + "e" * 64, "matching-receipt": "sha256:" + "f" * 64}
    observed = original.as_of - timedelta(seconds=1)
    return replace(
        original,
        instruments=instruments,
        instrument_map_sha256=k.instrument_map_sha256(instruments),
        route_categories=categories,
        route_source_pins=pins,
        route_observed_at=observed,
        route_map_sha256=k.route_map_sha256(instruments, categories, pins, observed),
    )


def test_legacy_binding_bytes_and_declared_only_scope_are_preserved(case):
    envelope, _ = case
    payload = dict(
        calendar=envelope.calendar_sha256,
        instrument_map=envelope.instrument_map_sha256,
        input_manifest=envelope.input_manifest_sha256,
        model=envelope.model_sha256,
        cohort=k.COHORT_SHA256,
        arm=k.ARM,
        anchor=envelope.input_anchor_date.isoformat(),
        as_of=envelope.as_of.isoformat(),
        observations=[
            [key, observed.isoformat() if observed is not None else None]
            for key, observed in sorted(envelope.observed_at_by_key.items())
        ],
        references=vars(envelope.references),
    )
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert envelope.binding_sha256 == "sha256:" + hashlib.sha256(raw).hexdigest()
    result = decide(case)
    assert result.route_map_sha256 is None
    assert result.safe_facts()["selection_scope"] == "legacy_declared_only_unrestricted_rank1"
    assert result.safe_facts()["route_support_grade"] == "legacy_declared_only"
    assert result.safe_facts()["route_supported_eligible_count"] == 0


def test_route125_unknown3_keeps_all_features_and_scores_unchanged(case):
    baseline = decide(case, scorer=lambda batch: {key: i / 128 for i, key in enumerate(batch.keys)})
    envelope = bound_route_envelope(case)
    received = []

    def scorer(batch):
        received.append(batch)
        return {key: i / 128 for i, key in enumerate(batch.keys)}

    result = decide(case, envelope=envelope, scorer=scorer)
    assert result.status == "prepared"
    assert received[0].keys == KEYS and len(result.scores) == 128
    assert result.feature_seal == baseline.feature_seal and result.scores == baseline.scores
    assert baseline.selected_key == KEYS[-1] and result.selected_key == KEYS[124]
    assert all(envelope.instruments[key].exchange is None for key in KEYS[125:])
    facts = result.safe_facts()
    assert facts["selection_scope"] == "kis_nasd_reference_constrained_rank1"
    assert facts["route_support_grade"] == "current_kis_reference_not_primary_or_PIT"
    assert facts["route_supported_eligible_count"] == 125
    assert facts["primary_listing_attested"] is facts["broker_eligibility_attested"] is False
    assert result.route_map_sha256 == envelope.route_map_sha256


def test_unsupported_top_score_and_unknown_peers_do_not_stop_one_supported_route(case):
    envelope = bound_route_envelope(case, supported=(KEYS[3],), unsupported=(KEYS[0],))
    result = decide(
        case,
        envelope=envelope,
        scorer=lambda batch: {key: 1.0 if key == KEYS[0] else 0.5 for key in batch.keys},
    )
    assert result.status == "prepared" and result.selected_key == KEYS[3]
    assert len(result.feature_seal.rows) == len(result.scores) == 128
    assert envelope.instruments[KEYS[0]].exchange is None
    assert result.proposal.target_exposure == D(".01") and result.proposal.confidence == 0
    assert result.safe_facts()["route_supported_eligible_count"] == 1


def test_supported_lexical_tie_and_original_fewer10_rule(case):
    envelope = bound_route_envelope(case, supported=(KEYS[8], KEYS[3]))
    assert decide(case, envelope=envelope).selected_key == KEYS[3]
    _, bars = case
    result = decide(
        case,
        envelope=envelope,
        source=lambda key, day: bars[key, day] if key in KEYS[:9] else None,
        scorer=lambda batch: pytest.fail("too_few_original_cohort"),
    )
    assert result.reason == k.Reason.FEWER


@pytest.mark.parametrize("unsupported", [(), KEYS])
def test_no_supported_routes_is_local_no_intent_with_full_cached_scores(case, unsupported):
    envelope = bound_route_envelope(case, supported=(), unsupported=unsupported)
    result = decide(case, envelope=envelope)
    assert result.reason == k.Reason.NO_ROUTE and result.status == "no_intent"
    assert len(result.scores) == len(result.feature_seal.rows) == 128
    assert result.proposal is result.receipt is result.selected_key is None
    assert (
        decide(case, envelope=bound_route_envelope(case, supported=(KEYS[7],))).status == "prepared"
    )


def test_supported_but_missing_context_does_not_fallback_to_unverified_peer(case):
    envelope = bound_route_envelope(case, supported=(KEYS[0],))
    _, bars = case
    result = decide(
        case,
        envelope=envelope,
        source=lambda key, day: None if key == KEYS[0] else bars[key, day],
    )
    assert result.reason == k.Reason.NO_ROUTE and len(result.scores) == 127


def test_route_maps_and_pins_detach_from_caller_and_scorer_aliases(case):
    envelope = bound_route_envelope(case)
    categories, pins = dict(envelope.route_categories), dict(envelope.route_source_pins)
    owned = replace(envelope, route_categories=categories, route_source_pins=pins)

    def scorer(batch):
        categories.clear()
        pins.clear()
        return dict.fromkeys(batch.keys, 0.5)

    result = decide(case, envelope=owned, scorer=scorer)
    assert result.status == "prepared" and result.selected_key == KEYS[0]
    assert len(owned.route_categories) == 128 and len(owned.route_source_pins) == 2
    with pytest.raises(TypeError):
        owned.route_categories[KEYS[0]] = k.RouteCategory.UNVERIFIED


@pytest.mark.parametrize("fault", ["hash", "source_pin", "future_clock", "category", "exchange"])
def test_route_scope_faults_stop_before_source_or_scorer(case, fault):
    envelope = bound_route_envelope(case)
    if fault == "hash":
        changed = replace(envelope, route_map_sha256="sha256:" + "a" * 64)
    elif fault == "source_pin":
        changed = replace(envelope, route_source_pins={"official-reference": "sha256:" + "a" * 64})
    elif fault == "future_clock":
        clock = envelope.as_of + timedelta(microseconds=1)
        changed = replace(
            envelope,
            route_observed_at=clock,
            route_map_sha256=k.route_map_sha256(
                envelope.instruments, envelope.route_categories, envelope.route_source_pins, clock
            ),
        )
    elif fault == "category":
        categories = dict(envelope.route_categories)
        categories[KEYS[0]] = k.RouteCategory.UNVERIFIED
        changed = replace(envelope, route_categories=categories)
    else:
        instruments = dict(envelope.instruments)
        instruments[KEYS[0]] = replace(instruments[KEYS[0]], exchange=None)
        changed = replace(
            envelope,
            instruments=instruments,
            instrument_map_sha256=k.instrument_map_sha256(instruments),
        )
    result = decide(
        case,
        envelope=changed,
        source=lambda *args: pytest.fail("invalid_route_source"),
        scorer=lambda batch: pytest.fail("invalid_route_scorer"),
    )
    assert result.status == "no_intent"


@pytest.mark.parametrize(
    "field", ["route_categories", "route_source_pins", "route_observed_at", "route_map_sha256"]
)
def test_partial_route_contract_cannot_downgrade_to_legacy(case, field):
    envelope = bound_route_envelope(case)
    with pytest.raises(ValueError):
        replace(envelope, **{field: None})


def test_null_exchange_without_bound_route_metadata_is_not_a_legacy_nasd_claim(case):
    envelope, _ = case
    instruments = {
        key: replace(value, exchange=None) for key, value in envelope.instruments.items()
    }
    envelope = replace(
        envelope,
        instruments=instruments,
        instrument_map_sha256=k.instrument_map_sha256(instruments),
    )
    assert decide(case, envelope=envelope).status == "no_intent"


def test_prepared_result_rejects_internally_consistent_rebound_route_map(case):
    envelope = bound_route_envelope(case)
    result = decide(case, envelope=envelope)
    altered = bound_route_envelope(case, supported=KEYS[:124])
    assert altered.route_map_sha256 != result.route_map_sha256
    with pytest.raises(ValueError):
        replace(result, envelope=altered)
    with pytest.raises(ValueError):
        replace(result, route_map_sha256="sha256:" + "a" * 64)


def test_scorer_cannot_swap_valid_route_map_and_hash_after_prebinding(case):
    envelope = bound_route_envelope(case)
    altered = bound_route_envelope(case, supported=(KEYS[7],))

    def scorer(batch):
        for field in (
            "instruments",
            "instrument_map_sha256",
            "route_categories",
            "route_map_sha256",
        ):
            object.__setattr__(envelope, field, getattr(altered, field))
        return dict.fromkeys(batch.keys, 0.5)

    result = decide(case, envelope=envelope, scorer=scorer)
    assert result.status == "no_intent" and result.reason == k.Reason.CONTRACT


def test_two_route_bound_sessions_have_distinct_supported_choices_and_original_clocks(case):
    first = decide(case, envelope=bound_route_envelope(case, supported=(KEYS[2],)))
    retained = (first.proposal, first.receipt, first.route_map_sha256)
    later_case = make_case(date(2026, 11, 27))
    second = decide(later_case, envelope=bound_route_envelope(later_case, supported=(KEYS[9],)))
    assert first.status == second.status == "prepared"
    assert first.selected_key == KEYS[2] and second.selected_key == KEYS[9]
    assert second.proposal.valid_until == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert first.proposal.decided_at == first.model_completed_at > first.envelope.as_of
    assert second.proposal.decided_at == second.model_completed_at > second.envelope.as_of
    assert first.route_map_sha256 != second.route_map_sha256
    assert first.receipt.proposal_ref != second.receipt.proposal_ref
    assert first.envelope.model_sha256 == second.envelope.model_sha256 == k.MODEL_SHA256
    assert retained == (first.proposal, first.receipt, first.route_map_sha256)


def test_route_hash_requires_complete_keys_and_exact_supported_category(case):
    envelope = bound_route_envelope(case)
    categories = dict(envelope.route_categories)
    categories.pop(KEYS[0])
    with pytest.raises(ValueError):
        k.route_map_sha256(
            envelope.instruments, categories, envelope.route_source_pins, envelope.route_observed_at
        )
    categories = dict(envelope.route_categories)
    categories[KEYS[0]] = "primary_listing_verified"
    with pytest.raises(ValueError):
        k.route_map_sha256(
            envelope.instruments, categories, envelope.route_source_pins, envelope.route_observed_at
        )
