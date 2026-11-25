"""Invented host bytes into the packaged native account session."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from test_h3_dec4_retained_input import _native
from thericher_v2.execution.kis_paper_current_stock_cycle import StockCycleProfile
from thericher_v2.execution.paper_account_round import PaperRoundSlot
from thericher_v2.execution.paper_account_session import (
    PaperAccountCohort,
    PaperAccountSessionError,
    run_native_account_session,
)
from thericher_v2.ops.h3_dec4_guest import encode_dec4_guest_visit, parse_dec4_guest_visit
from thericher_v2.research import model_paper_weights as weights

SOURCE = "sha256:" + "a" * 64
BASIS = "sha256:" + "b" * 64
PROFILE = StockCycleProfile.MODEL_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3


def _wire(value, phase="entry", *, raw=None):
    payload = weights.serialize_model_paper_weights_input(value) if raw is None else raw
    pins = dict(
        phase=phase,
        source_ref=SOURCE,
        basis_ref=BASIS,
        policy_ref=value.policy_ref,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )
    packet = encode_dec4_guest_visit(**pins, payload=payload if phase == "entry" else None)
    return packet, {f"expected_{key}": pin for key, pin in pins.items()}


def test_entry_exact_native_bytes_and_guest_types_before_admission():
    value = _native()
    packet, pins = _wire(value)
    header, payload = packet.split(b"\n", 1)
    assert payload == weights.serialize_model_paper_weights_input(value)
    assert json.loads(header) == {
        "schema": "dec4-h3-guest-visit-v1",
        "slot": "dec4-h3-net25-20261204-v1",
        "phase": "entry",
        "starts_at": "2026-12-04T14:31:00+00:00",
        "ends_at": "2026-12-04T14:35:00+00:00",
        "profile": PROFILE.value,
        "source_ref": SOURCE,
        "basis_ref": BASIS,
        "policy_ref": value.policy_ref,
        "input_ref": value.input_ref,
    }
    assert packet == _wire(value)[0]

    visit = parse_dec4_guest_visit(packet, **pins)
    cohort = visit.cohort
    assert type(cohort) is PaperAccountCohort
    assert type(cohort.slot) is PaperRoundSlot
    assert cohort.profile is PROFILE and cohort.mode == "entry"
    loaded = visit.target_loader()
    assert type(loaded) is weights.ModelPaperWeightsInput
    assert loaded == value and loaded is not value

    def forbidden(*args):
        pytest.fail("native effect reached with owner admission denied")

    with pytest.raises(PaperAccountSessionError, match="^account_session_admission_denied$"):
        run_native_account_session(
            cohort=cohort,
            paths={},
            expected_account_ref=SOURCE,
            target_loader=visit.target_loader,
            client_factory=forbidden,
            configure_early_exit=forbidden,
            admit=lambda: False,
            deadline=cohort.slot.ends_at,
            clock=lambda: cohort.slot.starts_at,
            monotonic=lambda: 0,
        )


def test_exit_uses_same_owner_retained_digest_without_a_loader():
    value = _native()
    _, entry_pins = _wire(value)
    packet, pins = _wire(value, "exit")
    assert pins == entry_pins | {"expected_phase": "exit"}
    visit = parse_dec4_guest_visit(packet, **pins)
    slot = visit.cohort.slot
    assert slot.slot == "dec4-h3-net25-20261204-v1"
    assert visit.cohort.mode == slot.phase == "exit"
    assert slot.starts_at == datetime(2026, 12, 9, 14, 30, tzinfo=UTC)
    assert slot.ends_at == datetime(2026, 12, 9, 14, 35, tzinfo=UTC)
    assert slot.input_ref == value.input_ref
    with pytest.raises(ValueError, match="^h3_guest_exit_requires_native_retained_input$"):
        visit.target_loader()
    with pytest.raises(ValueError, match="^h3_guest_exit_payload_forbidden$"):
        parse_dec4_guest_visit(packet + weights.serialize_model_paper_weights_input(value), **pins)
    with pytest.raises(ValueError, match="^h3_guest_packet_invalid$"):
        parse_dec4_guest_visit(packet, **(pins | {"expected_payload_sha256": "e" * 64}))


@pytest.mark.parametrize(
    "old,new",
    [
        (b"20261204-v1", b"20261204-v1.entry"),
        (b'"phase":"entry"', b'"phase":"recovery"'),
        (b"2026-12-04", b"2026-12-07"),
        (b"14:31:00", b"14:30:00"),
        (b"14:35:00", b"14:37:00"),
        (b"+00:00", b"Z"),
        (PROFILE.value.encode(), b"wrong-profile"),
        (b'"starts_at":', b'"starts_at": '),
        (b"{", b'{"phase":"entry",'),
        (b"\n", b"\r\n"),
    ],
)
def test_rejects_altered_or_noncanonical_header(old, new):
    packet, pins = _wire(_native())
    header, payload = packet.split(b"\n", 1)
    changed = (header + b"\n").replace(old, new, 1)
    assert changed != header + b"\n"
    with pytest.raises(ValueError, match="^h3_guest_packet_invalid$"):
        parse_dec4_guest_visit(changed + payload, **pins)


@pytest.mark.parametrize("pin", ["source_ref", "basis_ref", "policy_ref"])
def test_packet_cannot_choose_owner_pin(pin):
    packet, pins = _wire(_native())
    with pytest.raises(ValueError, match="^h3_guest_packet_invalid$"):
        parse_dec4_guest_visit(packet, **(pins | {f"expected_{pin}": "sha256:" + "e" * 64}))


def test_entry_rejects_mutation_even_when_noncanonical_bytes_are_repinned():
    value = _native()
    packet, pins = _wire(value)
    with pytest.raises(ValueError, match="^h3_guest_native_payload_invalid$"):
        parse_dec4_guest_visit(packet + b" ", **pins)
    raw = weights.serialize_model_paper_weights_input(value) + b" "
    repinned, new_pins = _wire(value, raw=raw)
    with pytest.raises(ValueError, match="^h3_guest_native_payload_invalid$"):
        parse_dec4_guest_visit(repinned, **new_pins)


@pytest.mark.parametrize(
    "changes",
    [
        {"entry": 7, "exit": 10},
        {"ceiling": "0.09"},
        {"profile": weights.MODEL_PAPER_WEIGHTS_US_CASH_RAW_OPEN_ELAPSED3_PROFILE},
    ],
)
def test_wrong_native_contract_rejected_even_when_valid_native_codec(changes):
    packet, pins = _wire(_native(**changes))
    with pytest.raises(ValueError, match="^h3_guest_native_contract_mismatch$"):
        parse_dec4_guest_visit(packet, **pins)
