from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Context, Decimal, localcontext

import pytest

import thericher_v2.research.prospective_five_session_shadow_decision as s
from thericher_v2.contracts import TargetExposureProposal, decision_instrument_binding_ref
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.five_session_paper_decision import (
    FEATURE_SCHEMA_ID,
    FiveSessionPaperDecision,
)
from thericher_v2.research.prospective_five_session_shadow_decision import (
    ShadowDecisionError,
    restore_prospective_shadow_decision,
)

KEYS = tuple(f"S{i:04d}/NAS" for i in range(512))
OPEN = tuple(datetime(2026, 10, d, 13, 30, tzinfo=UTC) for d in range(19, 24))
CLOSE = tuple(datetime(2026, 10, d, 20, tzinfo=UTC) for d in range(19, 24))
PRIOR = datetime(2026, 10, 16, 20, tzinfo=UTC)
INFERRED = datetime(2026, 10, 16, 21, 25, tzinfo=UTC)


def pin(letter):
    return "sha256:" + letter * 64


def ref(value):
    return (
        "ref:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def encode(value):
    def default(item):
        return item.isoformat() if isinstance(item, datetime) else str(item)

    return json.dumps(value, default=default, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture
def packet(monkeypatch):
    # SYN identities only; no real model, market rows, numeric arrays or inference.
    monkeypatch.setattr(
        s, "_IDENTITY", s._sha(json.dumps(list(KEYS), separators=(",", ":")).encode())
    )
    campaign = "ref:" + "a" * 64
    instrument = decision_instrument_binding_ref(
        symbol="S0200", market="US", decision_class="enter"
    )
    base = dict(
        campaign=campaign,
        frame="b" * 64,
        input=pin("c"),
        model=s._TEACHER,
        sources=s._SOURCES,
        allocation="ref:" + "d" * 64,
        slot=200,
        instrument=instrument,
    )
    cohort = ref(base)
    target = Decimal("0.004998750312421894526368")
    proposal_ref = ref(
        dict(
            cohort=cohort,
            completed=INFERRED.isoformat(),
            valid_until=(OPEN[0] + timedelta(minutes=10)).isoformat(),
            target=str(target),
        )
    )
    with localcontext(Context(prec=64, rounding=ROUND_DOWN)):
        proposal = TargetExposureProposal(
            proposal_ref,
            "S0200",
            "US",
            "enter",
            target,
            Decimal("1"),
            FEATURE_SCHEMA_ID,
            "ready",
            INFERRED,
            OPEN[0] + timedelta(minutes=10),
            PRIOR,
            "frozen_tree_single_slot_engineering_marker_not_probability",
        )
        receipt = receipt_from_target_exposure_proposal(
            proposal,
            references=DecisionReceiptReferences(campaign, s._TEACHER, pin("c"), proposal_ref),
        )
        dto = FiveSessionPaperDecision(
            "prepared",
            "frozen_first_surviving_slot",
            cohort,
            200,
            KEYS[200],
            instrument,
            pin("b"),
            pin("e"),
            "ref:" + "d" * 64,
            s._SOURCES,
            pin("c"),
            s._TEACHER,
            proposal_ref,
            OPEN[0] - timedelta(hours=1),
            PRIOR,
            OPEN,
            CLOSE,
            OPEN[0] + timedelta(minutes=10),
            INFERRED,
            INFERRED,
            proposal,
            receipt,
        )
    result = dict(
        s._FIXED_LINKS,
        status="prepared",
        reason=dto.reason,
        phase="complete",
        decision=asdict(dto),
        plan_sha256=pin("a"),
        source_pins_sha256=pin("f"),
        source_count=40,
        data_source_count=28,
        physical_capture_sha256=pin("1"),
        source_chunks_sha256=pin("2"),
        input_manifest_sha256=pin("c"),
        input_captured_at="2026-10-16T21:20:00+00:00",
        frame_sha256=pin("b"),
        identity_count=512,
        eligible_count=200,
        original_eligible=100,
        added_eligible=100,
        complete_prior21_count=512,
        fit_calls=0,
        broker_calls=0,
        inference_calls=1,
        supported=True,
        sources_reattested=True,
        worker_started_at=(INFERRED - timedelta(seconds=1)).isoformat(),
        inference_completed_at=INFERRED.isoformat(),
        completed_at=(INFERRED + timedelta(seconds=1)).isoformat(),
        elapsed_seconds=2.0,
        shadow_only=True,
        order_consumer=False,
        raw_rows_retained=False,
        scores_retained=False,
        model_dump_retained=False,
        availability="assumed_not_observed",
        exposure_units="fraction_of_original_shared_basis",
        calendar_validation="Data_pinned_21plus5_not_regenerated_in_worker",
    )
    kwargs = dict(
        expected_links={k: result[k] for k in s._LINKS}
        | dict(
            result_sha256=s._sha(encode(result)),
            engine_started_at=(INFERRED - timedelta(seconds=2)).isoformat(),
            engine_finished_at=(INFERRED + timedelta(seconds=2)).isoformat(),
        ),
        identities=KEYS,
        prior_close_at=PRIOR,
        nominal_decision_at=OPEN[0] - timedelta(hours=1),
        session_opens=OPEN,
        session_closes=CLOSE,
        entry_valid_until=OPEN[0] + timedelta(minutes=10),
        as_of=INFERRED + timedelta(minutes=5),
    )
    return json.loads(encode(result)), kwargs, dto


def restore(packet, mutate=None, **changes):
    result, kwargs, _ = packet
    result, kwargs = copy.deepcopy(result), copy.deepcopy(kwargs)
    if mutate:
        mutate(result)
    raw = encode(result)
    kwargs["expected_links"]["result_sha256"] = s._sha(raw)
    return restore_prospective_shadow_decision(raw, **(kwargs | changes))


def test_typed_restore_preserves_added_slot_target_and_shadow_scope(packet):
    out = restore(packet)
    assert out.status == "bound_shadow_metadata" and out.decision == packet[2]
    assert out.decision.selected_slot == 200 and out.decision.proposal.target_exposure < Decimal(
        ".01"
    )
    assert (
        out.shadow_only
        and not out.order_consumer
        and out.calendar_ref == s._FIXED_LINKS["calendar26_sha256"]
    )
    assert out.decision.cohort_ref.startswith("ref:")
    with pytest.raises(FrozenInstanceError):
        out.order_consumer = True
    with pytest.raises(ShadowDecisionError):
        replace(out, order_consumer=True)


@pytest.mark.parametrize("precision", [2, 28, 80])
def test_fixed_local_context_does_not_change_receipt_or_global_precision(packet, precision):
    with localcontext() as ctx:
        ctx.prec = precision
        out = restore(packet)
        assert ctx.prec == precision
    assert out.decision == packet[2]
    assert out.decision.proposal.target_exposure == Decimal("0.004998750312421894526368")


def test_missing_result_is_unavailable_not_zero_or_permission(packet):
    out = restore_prospective_shadow_decision(None, **packet[1])
    assert out.status == "unavailable" and out.reason == "missing_result"
    assert out.decision is out.result_sha256 is None and not out.order_consumer


@pytest.mark.parametrize("where", ["result", "decision", "proposal", "receipt"])
def test_extra_fields_never_silently_drop(packet, where):
    def mutate(r):
        obj = r if where == "result" else r["decision"]
        if where in ("proposal", "receipt"):
            obj = obj[where]
        obj["unexpected"] = "SYN"

    with pytest.raises(ShadowDecisionError):
        restore(packet, mutate)


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_keys_at_all_levels(packet, nested):
    raw = encode(packet[0])
    raw = (
        raw.replace(b'"selected_slot":200', b'"selected_slot":200,"selected_slot":200')
        if nested
        else raw[:-1] + b',"status":"prepared"}'
    )
    kwargs = copy.deepcopy(packet[1])
    kwargs["expected_links"]["result_sha256"] = s._sha(raw)
    with pytest.raises(ShadowDecisionError, match="shadow_duplicate_key"):
        restore_prospective_shadow_decision(raw, **kwargs)


def test_result_byte_hash_and_expected_exact_fields(packet):
    with pytest.raises(ShadowDecisionError, match="shadow_result_hash"):
        restore_prospective_shadow_decision(encode(packet[0]) + b" ", **packet[1])
    links = packet[1]["expected_links"] | {"unused": "SYN"}
    with pytest.raises(ShadowDecisionError, match="shadow_expected_fields"):
        restore(packet, expected_links=links)


@pytest.mark.parametrize(
    "field", ["plan_sha256", "input_manifest_sha256", "source_pins_sha256", "worker_sha256"]
)
def test_rebound_chain_or_worker_rejected_even_rehashed_result(packet, field):
    with pytest.raises(ShadowDecisionError, match="shadow_expected_link"):
        restore(packet, lambda r: r.update({field: pin("9")}))


def test_caller_cannot_replace_known_fixed_worker(packet):
    links = packet[1]["expected_links"] | {"worker_sha256": pin("9")}
    with pytest.raises(ShadowDecisionError, match="shadow_fixed_source"):
        restore(packet, expected_links=links)


def test_r3_requires_explicit_independent_worker_pin(packet):
    result, kwargs, dto = copy.deepcopy(packet)
    result["worker_sha256"] = kwargs["expected_links"]["worker_sha256"] = s._WORKER_R3
    raw = encode(result)
    kwargs["expected_links"]["result_sha256"] = s._sha(raw)
    with pytest.raises(ShadowDecisionError, match="shadow_fixed_source"):
        restore_prospective_shadow_decision(raw, **kwargs)
    out = restore_prospective_shadow_decision(raw, **kwargs, expected_worker_sha256=s._WORKER_R3)
    assert out.decision == dto and not out.order_consumer


@pytest.mark.parametrize("worker", [pin("9"), "sha256:wrong", None, True])
def test_explicit_keyword_never_allows_arbitrary_incoming_worker(packet, worker):
    result, kwargs, _ = copy.deepcopy(packet)
    if type(worker) is str and s._PIN.fullmatch(worker):
        result["worker_sha256"] = kwargs["expected_links"]["worker_sha256"] = worker
    raw = encode(result)
    kwargs["expected_links"]["result_sha256"] = s._sha(raw)
    with pytest.raises(ShadowDecisionError, match="shadow_fixed_source"):
        restore_prospective_shadow_decision(raw, **kwargs, expected_worker_sha256=worker)


def test_explicit_r3_pin_does_not_relabel_old_result(packet):
    with pytest.raises(ShadowDecisionError, match="shadow_fixed_source"):
        restore(packet, expected_worker_sha256=s._WORKER_R3)


def test_actual_clocks_not_nominal_future_or_expired_audit(packet):
    for field, clock in (
        ("inference_completed_at", OPEN[0]),
        ("completed_at", packet[1]["entry_valid_until"]),
        ("worker_started_at", PRIOR - timedelta(seconds=1)),
    ):
        with pytest.raises(ShadowDecisionError, match="shadow_actual_clocks"):
            restore(
                packet, lambda r, field=field, clock=clock: r.update({field: clock.isoformat()})
            )
    with pytest.raises(ShadowDecisionError):
        restore(packet, nominal_decision_at=INFERRED)
    out = restore(packet, as_of=packet[1]["entry_valid_until"])
    assert out.reason == "entry_window_closed" and out.decision is None


def test_selected_slot_identity_and_no_replacement(packet):
    with pytest.raises(ShadowDecisionError):
        restore(packet, lambda r: r["decision"].update(selected_slot=201))
    keys = list(KEYS)
    keys[200], keys[201] = keys[201], keys[200]
    with pytest.raises(ShadowDecisionError, match="shadow_identity"):
        restore(packet, identities=tuple(keys))


def test_source_role_and_exact_decimal_cap_no_capping(packet):
    with pytest.raises(ShadowDecisionError):
        restore(packet, lambda r: r["decision"]["source_pins"][0].__setitem__(1, pin("9")))
    for target in ("0.010000000001", 0.005, "NaN", "1e-3"):
        with pytest.raises(ShadowDecisionError):
            restore(
                packet,
                lambda r, target=target: r["decision"]["proposal"].update(target_exposure=target),
            )


def test_post_audit_failure_or_relabelled_consumer_never_usable(packet):
    for change in (
        dict(status="failed"),
        dict(sources_reattested=False),
        dict(order_consumer=True),
        dict(exposure_units="fraction_of_account_capital"),
        dict(fit_calls=True),
        dict(availability="observed"),
    ):
        with pytest.raises(ShadowDecisionError, match="shadow_scope"):
            restore(packet, lambda r, change=change: r.update(change))


@pytest.mark.parametrize("reason", ["prior_causal_support", "selected_instrument_unavailable"])
def test_scoped_no_intent_preserves_slot_without_substitution(packet, reason):
    def mutate(r):
        d = r["decision"]
        d.update(status="no_intent", reason=reason, proposal=None, receipt=None, proposal_ref=None)
        r.update(status="no_intent", reason=reason)
        if reason == "prior_causal_support":
            d.update(selected_slot=None, instrument_key=None, instrument_binding_ref=None)
            r.update(supported=False, eligible_count=0, original_eligible=0, added_eligible=0)
        d["cohort_ref"] = ref(
            dict(
                campaign="ref:" + r["plan_sha256"][7:],
                frame=d["frame_ref"][7:],
                input=d["input_manifest_ref"],
                model=d["model_ref"],
                sources=d["source_pins"],
                allocation=d["allocation_ref"],
                slot=d["selected_slot"],
                instrument=d["instrument_binding_ref"],
            )
        )

    out = restore(packet, mutate)
    assert out.status == "unavailable" and out.reason == reason and not out.order_consumer
    assert out.decision.proposal is out.decision.receipt is None
    assert out.decision.selected_slot == (None if reason == "prior_causal_support" else 200)


def test_count_clock_and_constructor_normalization_must_not_be_ignored(packet):
    for change in (dict(added_eligible=99), dict(elapsed_seconds=True), dict(inference_calls=0)):
        with pytest.raises(ShadowDecisionError):
            restore(packet, lambda r, change=change: r.update(change))
    with pytest.raises(ShadowDecisionError, match="shadow_constructor_normalization"):
        restore(packet, lambda r: r["decision"]["proposal"].update(symbol="s0200"))
    with pytest.raises(ShadowDecisionError):
        restore(packet, session_closes=CLOSE[:-1] + (CLOSE[-1] + timedelta(minutes=1),))


@pytest.mark.parametrize("field", ["proposal", "receipt"])
@pytest.mark.parametrize("version", [2, 3])
def test_unsupported_nested_schema_versions_rejected(packet, field, version):
    with pytest.raises(ShadowDecisionError, match="shadow_schema_version"):
        restore(packet, lambda r: r["decision"][field].update(schema_version=version))


def test_lazy_import_and_restore_have_no_model_or_filesystem_operations(packet, monkeypatch):
    code = """
import sys
import thericher_v2.research.prospective_five_session_shadow_decision
assert not any(n in sys.modules for n in ('numpy','sklearn','torch','pickle',
 'thericher_v2.execution','thericher_v2.research.five_session_tree'))
"""
    assert (
        subprocess.run(
            [sys.executable, "-B", "-c", code], capture_output=True, timeout=10
        ).returncode
        == 0
    )
    import builtins

    def deny(*_args, **_kwargs):
        pytest.fail("pure restore attempted file I/O")

    monkeypatch.setattr(builtins, "open", deny)
    assert restore(packet).status == "bound_shadow_metadata"
