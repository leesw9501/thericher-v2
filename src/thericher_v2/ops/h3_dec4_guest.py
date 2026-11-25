"""Decode one Dec4/Dec9 NET25 visit for the packaged Paper account guest."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, DecimalException

from thericher_v2.execution.kis_paper_current_stock_cycle import StockCycleProfile
from thericher_v2.execution.paper_account_round import PaperRoundSlot
from thericher_v2.execution.paper_account_session import PaperAccountCohort
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.model_paper_weights import (
    ModelPaperWeightsInput,
    load_model_paper_weights_input,
)

DEC4_ROUND = "dec4-h3-net25-20261204-v1"
_PROFILE = StockCycleProfile.MODEL_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3
_MAX_NATIVE_BYTES = 1024 * 1024
_REF = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True, repr=False)
class Dec4GuestVisit:
    cohort: PaperAccountCohort
    target_loader: Callable[[], ModelPaperWeightsInput]


def _at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 12, day, hour, minute, tzinfo=UTC)


def _binding(
    phase: str, source_ref: str, basis_ref: str, policy_ref: str, payload_sha256: str
) -> tuple[bytes, PaperAccountCohort]:
    if (
        type(phase) is not str
        or phase not in ("entry", "exit")
        or type(payload_sha256) is not str
        or len(payload_sha256) != 64
    ):
        raise ValueError("h3_guest_pin_invalid")
    input_ref = "sha256:" + payload_sha256
    if any(
        type(ref) is not str or _REF.fullmatch(ref) is None
        for ref in (source_ref, basis_ref, policy_ref, input_ref)
    ):
        raise ValueError("h3_guest_pin_invalid")

    day, minute = (4, 31) if phase == "entry" else (9, 30)
    slot = PaperRoundSlot(
        DEC4_ROUND,
        phase,
        _at(day, 14, minute),
        _at(day, 14, 35),
        input_ref,
        policy_ref,
    )
    header = dict(
        schema="dec4-h3-guest-visit-v1",
        slot=slot.slot,
        phase=phase,
        starts_at=slot.starts_at.isoformat(),
        ends_at=slot.ends_at.isoformat(),
        profile=_PROFILE.value,
        source_ref=source_ref,
        basis_ref=basis_ref,
        input_ref=input_ref,
        policy_ref=policy_ref,
    )
    return (
        json.dumps(header, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n",
        PaperAccountCohort(slot, source_ref, basis_ref, _PROFILE, phase),
    )


def encode_dec4_guest_visit(
    *,
    phase: str,
    source_ref: str,
    basis_ref: str,
    policy_ref: str,
    payload_sha256: str,
    payload: bytes | None = None,
) -> bytes:
    """Frame a visit as canonical ASCII JSON, LF, and entry-only native bytes."""
    header, _ = _binding(phase, source_ref, basis_ref, policy_ref, payload_sha256)
    if phase == "exit" and payload is None:
        return header
    if phase == "entry" and type(payload) is bytes and 0 < len(payload) <= _MAX_NATIVE_BYTES:
        return header + payload
    raise ValueError("h3_guest_payload_invalid")


def _no_exit_load() -> ModelPaperWeightsInput:
    raise ValueError("h3_guest_exit_requires_native_retained_input")


def parse_dec4_guest_visit(
    packet: bytes,
    *,
    expected_phase: str,
    expected_source_ref: str,
    expected_basis_ref: str,
    expected_policy_ref: str,
    expected_payload_sha256: str,
) -> Dec4GuestVisit:
    """Use independent owner pins; exit's digest must come from the Dec4 retention.

    Exit carries no proposal. The account guest checks the matching native
    custody and never gets a fresh loader for this phase. No ownership,
    current clock, or ability to execute is established by this parser.
    """
    header, cohort = _binding(
        expected_phase,
        expected_source_ref,
        expected_basis_ref,
        expected_policy_ref,
        expected_payload_sha256,
    )
    if (
        type(packet) is not bytes
        or len(packet) > len(header) + _MAX_NATIVE_BYTES
        or not packet.startswith(header)
    ):
        raise ValueError("h3_guest_packet_invalid")
    cohort.validate()
    if expected_phase == "exit":
        if packet != header:
            raise ValueError("h3_guest_exit_payload_forbidden")
        return Dec4GuestVisit(cohort, _no_exit_load)

    try:
        value = load_model_paper_weights_input(
            packet[len(header) :],
            expected_sha256=expected_payload_sha256,
            expected_policy_ref=expected_policy_ref,
        )
    except (ValueError, TypeError, OverflowError, RecursionError, DecimalException):
        raise ValueError("h3_guest_native_payload_invalid") from None
    if (
        value.profile != _PROFILE.value
        or value.entry_session != SessionWindow(_at(4, 14, 30), _at(4, 21, 0))
        or value.exit_session != SessionWindow(_at(9, 14, 30), _at(9, 21, 0))
        or value.metadata.exit_not_before != _at(9, 14, 30)
        or value.metadata.original_basis_gross_ceiling != Decimal("0.1")
    ):
        raise ValueError("h3_guest_native_contract_mismatch")
    return Dec4GuestVisit(cohort, lambda: value)
