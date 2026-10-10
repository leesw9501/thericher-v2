from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, Context, Decimal, localcontext
from fractions import Fraction

import numpy as np
import pytest

from thericher_v2.contracts import decision_instrument_binding_ref
from thericher_v2.research import five_session_paper_decision as paper
from thericher_v2.research import five_session_tree as tree
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.five_session_cohort import FiveSessionFrame

KEYS = tuple(f"S{i:04d}/NAS" for i in range(512))
IDENTITY = hashlib.sha256(json.dumps(list(KEYS), separators=(",", ":")).encode()).hexdigest()
SLOTS = (200, 5, 300, 2, 130, 7, 511, 128, 3, 6)
MANIFEST = "sha256:" + "a" * 64


def make_frame(**changes):
    opening = datetime(2026, 10, 12, 13, 30, tzinfo=UTC)
    prior = []
    at = datetime(2026, 10, 9, 20, tzinfo=UTC)
    while len(prior) < 21:
        if at.weekday() < 5:
            prior.append(at)
        at -= timedelta(days=1)
    opens = tuple(opening + timedelta(days=i) for i in range(5))
    tokens = np.zeros((512, 20, 5))
    tokens[list(SLOTS), 0, 0] = np.arange(10, 0, -1)
    values = dict(
        index=21,
        identities=KEYS,
        decision=opening - timedelta(hours=1),
        prior_closes=tuple(reversed(prior)),
        session_opens=opens,
        session_closes=tuple(at + timedelta(hours=6, minutes=30) for at in opens),
        tokens=tokens,
        eligible=np.ones(512, dtype=bool),
        momentum=np.full(512, 0.1),
        volatility=np.full(512, 0.2),
        feature_stamp="b" * 64,
    )
    return FiveSessionFrame(**(values | changes))


def infer(frame):
    # Actual frozen allocation API with a synthetic predictor; no loader or fitting.
    return tree._TreeInference(lambda x: x[:, 0], np.zeros(5), np.ones(5))(frame)


@pytest.fixture
def inputs(monkeypatch):
    monkeypatch.setattr(tree, "IDENTITY_SHA256", IDENTITY)
    frame = make_frame()
    bindings = {
        key: decision_instrument_binding_ref(symbol=key[:-4], market="US", decision_class="enter")
        for key in KEYS
    }
    complete = frame.prior_closes[-1] + timedelta(hours=20)
    kwargs = dict(
        campaign_ref="ref:" + "c" * 64,
        input_manifest_sha256=MANIFEST,
        expected_input_manifest_sha256=MANIFEST,
        feature_source_sha256="sha256:" + tree.FEATURE_SHA256,
        inference_source_sha256=paper.INFERENCE_SOURCE_SHA256,
        instrument_bindings=bindings,
        inference_completed_at=complete,
        as_of=complete + timedelta(minutes=1),
        entry_valid_until=frame.target_open + timedelta(minutes=5),
    )
    return frame, infer(frame), kwargs


def prepare(inputs, **changes):
    frame, decision, kwargs = inputs
    return paper.prepare_five_session_paper_decision(frame, decision, **(kwargs | changes))


def test_actual_typed_api_all_weight_fee_mapping_and_original_basis(inputs):
    _, decision, _ = inputs
    out = prepare(inputs)
    assert out.status == "prepared" and out.selected_slot == 200
    assert out.instrument_key == KEYS[200]  # ORIGINAL ranked slot, not original128-only.
    gross = sum((Fraction(Decimal(str(float(w)))) for w in decision.weights), Fraction())
    selected = Fraction(Decimal(str(float(decision.weights[200]))))
    exact = Fraction(1, 10) * selected / (1 + gross / 2000)
    actual = Fraction(out.proposal.target_exposure)
    assert 0 <= exact - actual < Fraction(1, 10**24)
    pilot_only = Fraction(1, 10) * selected / (1 + selected / 2000)
    assert actual < pilot_only
    assert out.proposal.target_exposure < Decimal(".01")
    assert out.proposal.confidence == Decimal("1")
    assert "not_probability" in out.proposal.reason


def test_lightweight_receipt_and_all_clock_source_bindings(inputs):
    frame, _, kwargs = inputs
    out = prepare(inputs)
    refs = DecisionReceiptReferences(
        kwargs["campaign_ref"], out.model_ref, MANIFEST, out.proposal_ref
    )
    assert out.receipt == receipt_from_target_exposure_proposal(out.proposal, references=refs)
    assert out.receipt.instrument_binding_ref == kwargs["instrument_bindings"][KEYS[200]]
    assert out.frame_ref == "sha256:" + frame.stamp
    assert out.feature_ref == "sha256:" + frame.feature_stamp
    assert out.model_ref == "ref:" + tree.TEACHER_SHA256
    assert out.source_pins == (
        ("feature", "sha256:" + tree.FEATURE_SHA256),
        ("inference", paper.INFERENCE_SOURCE_SHA256),
        ("teacher_metadata", "sha256:" + tree.METADATA_SHA256),
    )
    assert out.session_opens == frame.session_opens and out.session_closes == frame.session_closes
    assert out.first_open == frame.target_open and out.fifth_close == frame.target_close
    assert out.entry_valid_until < out.fifth_close
    assert out.availability == "assumed_not_observed"


def test_completion_not_backdated_to_future_nominal_preopen(inputs):
    frame, _, kwargs = inputs
    out = prepare(inputs)
    assert kwargs["inference_completed_at"] < frame.decision
    assert out.proposal.decided_at == out.receipt.decided_at == out.inference_completed_at
    assert out.nominal_decision_at == frame.decision
    assert out.proposal.feature_window_end == frame.prior_closes[-1]


def test_cash_veto_preserves_rank_order_and_never_redistributes(inputs):
    frame, _, kwargs = inputs
    momentum = frame.momentum.copy()
    momentum[SLOTS[0]] = 0
    changed = replace(frame, momentum=momentum)
    decision = infer(changed)
    out = paper.prepare_five_session_paper_decision(changed, decision, **kwargs)
    assert decision.original_slots == SLOTS and out.selected_slot == SLOTS[1]
    assert decision.weights[SLOTS[0]] == 0
    assert np.count_nonzero(decision.weights) == 9
    assert decision.weights[SLOTS[1]] == inputs[1].weights[SLOTS[1]]


@pytest.mark.parametrize("missing", [True, False])
def test_selected_binding_missing_or_conflict_never_selects_next(inputs, missing):
    kwargs = inputs[2]
    bindings = dict(kwargs["instrument_bindings"])
    if missing:
        del bindings[KEYS[200]]
    else:
        bindings[KEYS[200]] = bindings[KEYS[5]]
    out = prepare(inputs, instrument_bindings=bindings)
    assert out.status == "no_intent" and out.selected_slot == 200
    assert out.instrument_key == KEYS[200]
    assert out.reason == (
        "selected_instrument_unavailable" if missing else "selected_instrument_mismatch"
    )
    assert out.proposal is out.receipt is out.proposal_ref is None


@pytest.mark.parametrize("unsupported", [True, False])
def test_scoped_unavailable_or_all_cash_has_no_entry(inputs, unsupported):
    frame, _, kwargs = inputs
    if unsupported:
        eligible = np.zeros(512, dtype=bool)
        eligible[:128] = True  # Missing the added64 support; no global prohibition.
        frame = replace(frame, eligible=eligible)
    else:
        frame = replace(frame, momentum=np.zeros(512))
    out = paper.prepare_five_session_paper_decision(frame, infer(frame), **kwargs)
    assert out.status == "no_intent"
    assert out.reason == ("prior_causal_support" if unsupported else "model_cash_veto")
    assert out.selected_slot is out.instrument_key is out.instrument_binding_ref is None
    assert out.proposal is out.receipt is None
    assert out.fifth_close == frame.target_close


def test_tied_source_scores_keep_canonical_original_order(inputs):
    frame, _, kwargs = inputs
    frame = replace(frame, tokens=np.zeros((512, 20, 5)))
    decision = infer(frame)
    assert decision.original_slots == tuple(range(10))
    assert paper.prepare_five_session_paper_decision(frame, decision, **kwargs).selected_slot == 0


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("input_manifest_sha256", "sha256:" + "d" * 64, "manifest_binding"),
        ("expected_input_manifest_sha256", "a" * 64, "manifest_binding"),
        ("feature_source_sha256", "sha256:" + "d" * 64, "source_binding"),
        ("inference_source_sha256", "sha256:" + "d" * 64, "source_binding"),
    ],
)
def test_hash_and_source_mismatch_is_categorical(inputs, field, value, reason):
    with pytest.raises(paper.PaperDecisionError, match=reason):
        prepare(inputs, **{field: value})


@pytest.mark.parametrize("change", ["tokens", "clocks", "stamp"])
def test_frame_feature_clock_or_stamp_mismatch(inputs, change):
    frame, decision, kwargs = inputs
    if change == "tokens":
        frame = replace(frame, tokens=frame.tokens + 1)
    elif change == "clocks":
        closes = (*frame.session_closes[:-1], frame.target_close + timedelta(minutes=1))
        frame = replace(frame, session_closes=closes)
    else:
        decision = replace(decision, frame_stamp="f" * 64)
    with pytest.raises(paper.PaperDecisionError, match="frame_binding"):
        paper.prepare_five_session_paper_decision(frame, decision, **kwargs)


def test_exact_512_identity_permutation_not_set_membership(inputs):
    frame, decision, kwargs = inputs
    keys = list(frame.identities)
    keys[0], keys[128] = keys[128], keys[0]
    frame = replace(frame, identities=keys)
    decision = replace(decision, frame_stamp=frame.stamp)
    with pytest.raises(paper.PaperDecisionError, match="identity_binding"):
        paper.prepare_five_session_paper_decision(frame, decision, **kwargs)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("before_prior", "inference_before_prior"),
        ("future", "future_inference"),
        ("after_window", "entry_window_closed"),
        ("expired", "entry_window_closed"),
        ("window_at_open", "entry_window_invalid"),
        ("window_after_close", "entry_window_invalid"),
        ("naive", "clock_invalid"),
    ],
)
def test_actual_inference_and_entry_clock_bounds(inputs, case, reason):
    frame, _, kwargs = inputs
    changes = {
        "before_prior": dict(inference_completed_at=frame.prior_closes[-1] - timedelta(seconds=1)),
        "future": dict(inference_completed_at=kwargs["as_of"] + timedelta(seconds=1)),
        "after_window": dict(
            inference_completed_at=kwargs["entry_valid_until"] + timedelta(seconds=1),
            as_of=kwargs["entry_valid_until"] + timedelta(seconds=2),
        ),
        "expired": dict(as_of=kwargs["entry_valid_until"]),
        "window_at_open": dict(entry_valid_until=frame.target_open),
        "window_after_close": dict(
            entry_valid_until=frame.session_closes[0] + timedelta(seconds=1)
        ),
        "naive": dict(inference_completed_at=kwargs["inference_completed_at"].replace(tzinfo=None)),
    }[case]
    with pytest.raises(paper.PaperDecisionError, match=reason):
        prepare(inputs, **changes)


def test_declared_actual_clocks_not_five_calendar_days(inputs):
    frame, _, kwargs = inputs
    days = (23, 24, 25, 27, 30)  # Synthetic Thanksgiving/weekend and early-close geometry.
    opens = tuple(datetime(2026, 11, d, 14, 30, tzinfo=UTC) for d in days)
    closes = tuple(datetime(2026, 11, d, 18 if d == 27 else 21, tzinfo=UTC) for d in days)
    frame = replace(
        frame, decision=opens[0] - timedelta(hours=1), session_opens=opens, session_closes=closes
    )
    kwargs = kwargs | dict(entry_valid_until=opens[0] + timedelta(minutes=5))
    out = paper.prepare_five_session_paper_decision(frame, infer(frame), **kwargs)
    assert out.session_opens == opens and out.session_closes == closes
    assert out.fifth_close == closes[-1] and out.fifth_close.date().day == 30


def test_ambient_decimal_precision_and_asof_replay_do_not_change_identity(inputs):
    normal = prepare(inputs)
    with localcontext(Context(prec=3, rounding=ROUND_FLOOR)):
        low = prepare(inputs)
    assert low == normal
    later = prepare(inputs, as_of=inputs[2]["as_of"] + timedelta(minutes=10))
    assert later.cohort_ref == normal.cohort_ref
    assert later.proposal == normal.proposal and later.receipt == normal.receipt


def test_dto_is_immutable_lightweight_and_proposal_receipt_coupled(inputs):
    out = prepare(inputs)
    with pytest.raises(FrozenInstanceError):
        out.selected_slot = 5
    assert all(not isinstance(getattr(out, f.name), np.ndarray) for f in fields(out))
    with pytest.raises(paper.PaperDecisionError, match="dto_proposal_binding"):
        replace(out, proposal_ref="ref:" + "d" * 64)
    with pytest.raises(paper.PaperDecisionError, match="dto_identity_binding"):
        replace(out, proposal=replace(out.proposal, target_exposure=Decimal(".003")))
    with pytest.raises(paper.PaperDecisionError, match="dto_identity_binding"):
        replace(out, selected_slot=5)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("type", "typed_input"),
        ("teacher", "teacher_binding"),
        ("weights", "typed_input_invalid"),
        ("support", "frame_binding"),
        ("feature_hash", "feature_binding"),
        ("reason", "decision_reason_binding"),
    ],
)
def test_malformed_typed_input_is_not_reported_as_missing_data(inputs, case, reason):
    frame, decision, kwargs = inputs
    if case == "type":
        decision = object()
    elif case == "teacher":
        object.__setattr__(decision, "teacher_sha256", "0" * 64)
    elif case == "weights":
        object.__setattr__(decision, "weights", np.full(512, 0.1))
    elif case == "support":
        object.__setattr__(frame, "supported", False)
    elif case == "reason":
        decision = replace(decision, reason="unrelated_failure")
    else:
        frame = replace(frame, feature_stamp="not-a-hash")
        decision = replace(decision, frame_stamp=frame.stamp)
    with pytest.raises(paper.PaperDecisionError, match=reason):
        paper.prepare_five_session_paper_decision(frame, decision, **kwargs)


def test_no_transfer_of_selected_slot_after_dimensionless_underflow(inputs):
    frame, decision, kwargs = inputs
    weights = decision.weights.copy()
    weights[SLOTS[0]] = 1e-100
    decision = replace(decision, weights=weights)
    out = paper.prepare_five_session_paper_decision(frame, decision, **kwargs)
    assert out.status == "no_intent" and out.reason == "exposure_underflow"
    assert out.selected_slot == SLOTS[0] and out.proposal is None


def test_no_account_capacity_or_replacement_interface(inputs):
    parameters = inspect.signature(paper.prepare_five_session_paper_decision).parameters
    assert not (
        {"account", "amount", "cash", "capacity", "fit", "scorer", "replacement"} & set(parameters)
    )
    before = prepare(inputs)
    after = prepare(inputs)
    assert before == after  # Execution capacity failures cannot select another model slot.


def test_dto_import_does_not_load_numeric_model_data_or_broker_modules():
    code = """
import importlib.abc
import sys
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        prefixes = ('numpy', 'sklearn', 'torch', 'pickle', 'thericher_v2.execution',
                    'thericher_v2.data', 'thericher_v2.research.five_session_tree',
                    'thericher_v2.research.five_session_cohort')
        if any(fullname == p or fullname.startswith(p + '.') for p in prefixes):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Reject())
from thericher_v2.research.five_session_paper_decision import FiveSessionPaperDecision
assert FiveSessionPaperDecision.__dataclass_params__.frozen
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
