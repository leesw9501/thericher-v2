"""Invented byte buffers and callback-only checks for the recovery guest."""

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from thericher_v2.execution import net25_pending_reconciliation as native
from thericher_v2.execution import paper_peer_visit as bank
from thericher_v2.ops import h3_dec4_recovery_guest as guest
from thericher_v2.ops.h3_dec4_guest import _binding


def _ref(digit):
    return "sha256:" + digit * 64


def _forbidden(*args, **kwargs):
    pytest.fail("unexpected recovery callback")


@pytest.fixture(autouse=True)
def fake_native_only(monkeypatch):
    monkeypatch.setattr(native, "reconcile_net25_pending_request", _forbidden)
    monkeypatch.setattr(native, "verify_net25_reconciled_terminal", _forbidden)


@pytest.fixture(params=("entry", "exit"))
def case(request):
    _, original = _binding(request.param, _ref("a"), _ref("b"), _ref("c"), "d" * 64)
    key = "e" * 64
    identity = dict(
        source="a" * 64, release="1" * 64, group="a" * 64, member="stock-ingress",
        run="2" * 32, argv_sha256="3" * 64, bank=key,
    )
    owner = dict(pid=10, native_start="win-filetime:125")
    child = dict(token="6" * 32, argv_sha256="7" * 64, pid=11, native_start="win-filetime:126")
    create = dict(resolution="ACK_EXACT_CID", spec_sha256="4" * 64, cid="5" * 64)
    visit = dict(
        run="9" * 32, kind="effect", status="ACTIVE", closure=None, create=create,
        children=[child | {"status": "RUNNING_OR_UNKNOWN"}],
    )
    claim = dict(
        schema="paper-bank-leg-v1", identity=identity, owner=owner, sequence=5, visits=[visit],
        reservation_release=False,
    )
    claim_sha = bank.digest(claim)
    receipt = dict(
        schema="h3-dec4-physical-recovery-v1", original_claim_sha256=claim_sha,
        host_exit_code=20, host_disposition="DEADLINE",
        closure=dict(
            schema="paper-bank-visit-closure-v1", identity=identity, owner=owner,
            visit=visit["run"],
            record_sha256=claim_sha, children=[child | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}],
            create_resolution="ACK_EXACT_CID", container=create["cid"],
            container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN", evidence_sha256="8" * 64,
        ),
        same_native_intent_reconciliation_required=True, bank_claim_released=False,
        reservation_or_budget_release=False,
    )
    start = original.slot.ends_at + timedelta(days=1)
    pins = guest.Dec4RecoveryPins(
        original, key, claim_sha, bank.digest(receipt), _ref("f"), "0" * 64,
        start, start + timedelta(minutes=2),
    )
    return dict(
        expected=pins, original_claim=bank.encode(claim), physical_receipt=bank.encode(receipt),
    )


def _frame(case):
    return guest.encode_dec4_recovery_guest(case["expected"])


def _run(case, **overrides):
    return guest.run_dec4_recovery_guest(_frame(case), **(case | dict(
        paths={"state_root": "invented"},
        owner_ready=lambda _: True,
        clock=lambda: case["expected"].effect_starts_at,
        make_credentials_and_transport=_forbidden,
        persist_prepared=_forbidden,
    ) | overrides))


def _proof(case):
    return native.Net25TerminalProof(
        _ref("1"), case["expected"].pending_ref, _ref("2"), _ref("3"), _ref("4"), _ref("5"),
        "broker_terminal_retained",
    )


def test_original_identity_unchanged_and_recovery_window_separate(case):
    pins = case["expected"]
    frame = _frame(case)
    header = bank._decode(frame[:-1])
    recovery = guest.parse_dec4_recovery_guest(frame, **case)
    original = pins.original_cohort
    assert header["phase"] == "recovery" and header["original_cohort"]["phase"] == original.mode
    assert header["original_cohort"]["starts_at"] == original.slot.starts_at.isoformat()
    assert recovery == replace(original, mode="recovery", slot=replace(
        original.slot, phase="exit", starts_at=pins.effect_starts_at, ends_at=pins.effect_ends_at,
    ))


@pytest.mark.parametrize("change", ["payload", "claim", "receipt", "pending", "account", "window"])
def test_changed_frame_or_bytes_denied(case, change):
    frame = _frame(case)
    pins = case["expected"]
    if change == "payload":
        frame += b"{}"
    elif change == "claim":
        case["original_claim"] += b" "
    elif change == "receipt":
        case["physical_receipt"] += b" "
    elif change == "pending":
        case["expected"] = replace(pins, pending_ref=_ref("9"))
    elif change == "account":
        case["expected"] = replace(pins, account_ref="9" * 64)
    else:
        case["expected"] = replace(pins, effect_ends_at=pins.effect_ends_at + timedelta(seconds=1))
    with pytest.raises(ValueError, match="frame_invalid|evidence_pin"):
        guest.parse_dec4_recovery_guest(frame, **case)


@pytest.mark.parametrize("change", ["claim_sha", "receipt_release", "container", "child", "source"])
def test_even_rehashed_evidence_must_bind_original_claim(case, change):
    receipt = bank._decode(case["physical_receipt"])
    pins = case["expected"]
    if change == "claim_sha":
        receipt["original_claim_sha256"] = "0" * 64
    elif change == "receipt_release":
        receipt["bank_claim_released"] = 0
    elif change == "container":
        receipt["closure"]["container"] = "0" * 64
    elif change == "child":
        receipt["closure"]["children"][0]["pid"] = 12
    else:
        pins = replace(pins, original_cohort=replace(pins.original_cohort, source_ref=_ref("0")))
    case["physical_receipt"] = bank.encode(receipt)
    case["expected"] = replace(pins, physical_receipt_sha256=bank.digest(receipt))
    with pytest.raises(ValueError, match="evidence_unbound"):
        guest.parse_dec4_recovery_guest(_frame(case), **case)


@pytest.mark.parametrize(
    "bad", ["early", "expired", "naive", "owner_truthy", "expires_in_admission"]
)
def test_admission_denies_before_native(case, bad):
    pins = case["expected"]
    owner = _forbidden
    now = pins.effect_starts_at
    if bad == "early":
        now -= timedelta(microseconds=1)
    elif bad == "expired":
        now = pins.effect_ends_at
    elif bad == "naive":
        now = datetime(2026, 12, 15)
    elif bad == "owner_truthy":
        def owner(_):
            return 1
    else:
        now = iter((pins.effect_starts_at, pins.effect_ends_at))
        with pytest.raises(ValueError, match="window_closed"):
            _run(case, clock=lambda: next(now), owner_ready=lambda _: True)
        return
    with pytest.raises(ValueError, match="window_closed|owner_denied"):
        _run(case, clock=lambda: now, owner_ready=owner)


def test_pending_and_reconciled_without_proof_never_claim_release(case, monkeypatch):
    expected = case["expected"]
    owners = []

    def reconcile(**kw):
        assert kw["cohort"].mode == "recovery"
        assert kw["account_ref"] == expected.account_ref
        assert kw["expected_pending_ref"] == expected.pending_ref
        assert kw["admissible"]() is True
        return result

    monkeypatch.setattr(native, "reconcile_net25_pending_request", reconcile)
    for result in (
        native.Net25PendingOutcome("pending", "exact_terminal_evidence_missing", 4, 1),
        native.Net25PendingOutcome("reconciled", "never_reserved_retired"),
    ):
        line = _run(case, owner_ready=lambda pins: owners.append(pins) is None)
        outcome = guest.verify_dec4_recovery_outcome(line, line, exit_code=0, expected=expected)
        assert outcome["status"] == result.status and outcome["terminal"] is None
        assert outcome["bank_claim_released"] is outcome["reservation_release"] is False
        assert outcome["financial_claim"] == "UNKNOWN"
    assert len(owners) == 6 and all(p is expected for p in owners)


def test_prepared_and_committed_exact_proof_projects_only_safe_fields(case, monkeypatch):
    proof = _proof(case)
    events = []

    def reconcile(**kw):
        assert kw["admissible"]() is True
        assert kw["make_credentials_and_transport"]("instrument") == ("cfg", "transport")
        kw["persist_prepared"](proof)
        events.append("commit")
        return native.Net25PendingOutcome(
            "reconciled", "exact_native_terminal_retained", 4, 1, proof
        )

    def verify(paths, account_ref, cohort, terminal, *, clock, admitted):
        assert paths == {"state_root": "invented"}
        assert account_ref == case["expected"].account_ref and cohort.mode == "recovery"
        assert terminal == proof and clock().tzinfo is UTC and admitted() is True
        events.append("readback")
        return terminal

    monkeypatch.setattr(native, "reconcile_net25_pending_request", reconcile)
    monkeypatch.setattr(native, "verify_net25_reconciled_terminal", verify)
    line = _run(
        case, persist_prepared=lambda value: events.append(("prepared", value)),
        make_credentials_and_transport=lambda instrument: (
            events.append(("factory", instrument)) or ("cfg", "transport")
        ),
    )
    assert events == [("factory", "instrument"), ("prepared", proof), "commit", "readback"]
    result = guest.verify_dec4_recovery_outcome(line, line, exit_code=0, expected=case["expected"])
    assert result["terminal"] == asdict(proof)
    assert case["expected"].account_ref.encode() not in line

    altered = bank.encode(result | {"reservation_release": True}) + b"\n"
    for stdout, retained, code in (
        (line, line, 1), (line, altered, 0), (altered, altered, 0), (line + b"\n", line + b"\n", 0),
    ):
        with pytest.raises(ValueError, match="outcome_unconfirmed"):
            guest.verify_dec4_recovery_outcome(stdout, retained, exit_code=code,
                                              expected=case["expected"])


@pytest.mark.parametrize("bad", ["unprepared", "different", "wrong_pending", "persist", "readback"])
def test_bad_proof_or_failed_durability_withholds_terminal(case, monkeypatch, bad):
    proof = _proof(case)
    persisted = []

    def persist(value):
        persisted.append(value)
        if bad == "persist":
            raise OSError("private_fixture")

    def reconcile(**kw):
        if bad != "unprepared":
            kw["persist_prepared"](replace(proof, pending_ref=_ref("8")) if bad == "wrong_pending"
                                   else proof)
        returned = replace(proof, evidence_ref=_ref("8")) if bad == "different" else proof
        return native.Net25PendingOutcome("reconciled", "exact_native_terminal_retained",
                                          terminal=returned)

    monkeypatch.setattr(native, "reconcile_net25_pending_request", reconcile)
    if bad == "readback":
        monkeypatch.setattr(native, "verify_net25_reconciled_terminal", lambda *a, **k: None)
    with pytest.raises(ValueError, match="^h3_recovery_.*unconfirmed$") as failed:
        _run(case, persist_prepared=persist)
    assert "private_fixture" not in str(failed.value)
    assert persisted == ([] if bad in {"unprepared", "wrong_pending"} else [proof])


@pytest.mark.parametrize("failure", ["owner_lost", "second_factory"])
def test_inflight_admission_or_factory_failure_withholds_outcome(case, monkeypatch, failure):
    ready = iter([True, False] if failure == "owner_lost" else [True, True])
    factory_calls = []

    def reconcile(**kw):
        if failure == "owner_lost":
            kw["admissible"]()
        else:
            kw["make_credentials_and_transport"]("original")
            kw["make_credentials_and_transport"]("original")
        pytest.fail("native should not advance after denial")

    monkeypatch.setattr(native, "reconcile_net25_pending_request", reconcile)
    with pytest.raises(ValueError, match="native_unconfirmed"):
        _run(
            case, owner_ready=lambda _: next(ready),
            make_credentials_and_transport=factory_calls.append,
        )
    assert factory_calls == ([] if failure == "owner_lost" else ["original"])
