"""Bounded NET25 guest runtime; the host retains the physical bank and admission."""

import hashlib
import json
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.ops.h3_dec4_guest import Dec4GuestVisit, parse_dec4_guest_visit

_SHA = re.compile(r"[0-9a-f]{64}")
_PINS = {"phase", "source_ref", "basis_ref", "policy_ref", "payload_sha256"}
_FIELDS = _PINS | {"schema", "account_ref", "frame_sha256", "worker_sha256", "paths", "token_root"}
_NATIVE_STATUS = {"advanced", "hold", "complete", "no_intent", "pending"}
_OUTCOME_FIELDS = {
    "schema",
    "status",
    "pending",
    "phase",
    "input_ref",
    "policy_ref",
    "source_ref",
    "native_calls",
    "financial_claim",
    "reservation_release",
}


def _json(raw):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("h3_capsule_duplicate_field")
            obj[key] = value
        return obj

    return json.loads(raw, object_pairs_hook=unique)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_dec4_capsule(binding_raw, frame, *, binding_sha256):
    """Decode two exact caller-owned members without touching stdin or custody."""
    if (
        type(binding_raw) is not bytes
        or not 0 < len(binding_raw) <= 16_384
        or _digest(binding_raw) != binding_sha256
    ):
        raise ValueError("h3_capsule_binding_pin")
    binding = _json(binding_raw)
    if (
        type(binding) is not dict
        or binding.keys() != _FIELDS
        or binding["schema"] != "dec4-net25-capsule-binding-v1"
        or any(
            type(binding[k]) is not str or _SHA.fullmatch(binding[k]) is None
            for k in ("account_ref", "frame_sha256", "worker_sha256")
        )
        or type(frame) is not bytes
        or not 0 < len(frame) <= 2 * 1024 * 1024
        or _digest(frame) != binding["frame_sha256"]
        or type(binding["paths"]) is not dict
        or not all(type(v) is str for v in binding["paths"].values())
        or type(binding["token_root"]) is not str
    ):
        raise ValueError("h3_capsule_binding_invalid")
    guest = parse_dec4_guest_visit(frame, **{"expected_" + k: binding[k] for k in _PINS})
    return binding, guest


def verify_dec4_capsule_outcome(stdout, retained, *, exit_code, guest):
    """Validate a successful exact transport result, not process or financial closure."""
    if (
        type(guest) is not Dec4GuestVisit
        or type(exit_code) is not int
        or exit_code != 0
        or type(stdout) is not bytes
        or type(retained) is not bytes
        or not 1 < len(stdout) <= 4096
        or stdout != retained
        or not stdout.endswith(b"\n")
        or stdout.count(b"\n") != 1
    ):
        raise ValueError("h3_capsule_outcome_unconfirmed")
    try:
        outcome = _json(stdout)
    except (ValueError, RecursionError):
        raise ValueError("h3_capsule_outcome_unconfirmed") from None
    slot = guest.cohort.slot
    pins = dict(
        phase=slot.phase,
        input_ref=slot.input_ref,
        policy_ref=slot.policy_ref,
        source_ref=guest.cohort.source_ref,
    )
    if (
        type(outcome) is not dict
        or outcome.keys() != _OUTCOME_FIELDS
        or outcome["schema"] != "dec4-net25-capsule-outcome-v1"
        or type(outcome["status"]) is not str
        or outcome["status"] not in _NATIVE_STATUS
        or outcome["pending"] is not (True if outcome["status"] == "pending" else None)
        or type(outcome["native_calls"]) is not int
        or not 0 <= outcome["native_calls"] <= 32
        or outcome["financial_claim"] != "UNKNOWN"
        or outcome["reservation_release"] is not False
        or any(outcome[k] != v for k, v in pins.items())
    ):
        raise ValueError("h3_capsule_outcome_unconfirmed")
    # BankLeg still requires independent process/container closure. This boolean
    # reports a positive pending observation, not the absence of reservations.
    return {
        "pending": outcome["pending"] is True,
        "native_status": outcome["status"],
        "financial_claim": "UNKNOWN",
        "reservation_release": False,
    }


class OwnerChannel:
    """The current20 duplex protocol already spoken by the owned host transport."""

    def __init__(self, stream, sink, *, monotonic=time.monotonic):
        self.stream, self.sink, self.monotonic = stream, sink, monotonic
        self.sequence = 0

    def __call__(self):
        self.sequence += 1
        if self.sequence > 512:
            raise ValueError("h3_capsule_owner_count")
        started = self.monotonic()
        self.sink.write(
            (
                json.dumps(dict(kind="current20-owner-request-v1", sequence=self.sequence)) + "\n"
            ).encode("ascii")
        )
        self.sink.flush()
        raw = self.stream.readline(4097)
        if not raw.endswith(b"\n") or len(raw) > 4096:
            raise ValueError("h3_capsule_owner_unknown")
        answer = _json(raw)
        if (
            type(answer) is not dict
            or answer.keys() != {"kind", "sequence", "ready"}
            or answer["kind"] != "current20-owner-answer-v1"
            or type(answer["sequence"]) is not int
            or answer["sequence"] != self.sequence
            or answer["ready"] is not True
            or not 0 <= self.monotonic() - started <= 13
        ):
            raise ValueError("h3_capsule_owner_denied")
        return True


def run_dec4_account_capsule(binding, guest, *, stream, sink, load_worker, clock=None):
    """One native account-session call, with no implicit credentials or retries.

    The script reuses a receive-only credential line and the owner's duplex
    channel. The caller must enforce the capsule's process/job hard timeout;
    a blocked stdin read is not an independent deadline mechanism.
    """
    clock = (lambda: datetime.now(UTC)) if clock is None else clock
    slot = guest.cohort.slot

    def check_window():
        at = clock()
        if at.utcoffset() != timedelta(0) or not slot.starts_at <= at < slot.ends_at:
            raise ValueError("h3_capsule_outside_window")
        return True

    check_window()
    packet = stream.readline(8194)
    if not packet.endswith(b"\n") or len(packet) > 8193:
        raise ValueError("h3_capsule_packet_invalid")
    owner = OwnerChannel(stream, sink)

    def admit():
        check_window()
        owner()
        check_window()
        return True

    admit()
    worker = load_worker(binding["worker_sha256"])
    paths = worker["native_paths"]()
    token_root = worker["CONTROL"]
    if {k: str(v) for k, v in paths.items()} != binding["paths"] or str(token_root) != binding[
        "token_root"
    ]:
        raise ValueError("h3_capsule_custody_path_mismatch")
    config = worker["parse_packet"](packet[:-1])
    from thericher_v2.execution import kis_paper_budget_strategy as budget

    account_ref = budget._digest(
        [config.base_url, config.account_number, config.account_product_code]
    )
    if account_ref != binding["account_ref"]:
        raise ValueError("h3_capsule_account_mismatch")
    result = worker["run_account_session"](
        config,
        execute=True,
        cohort=guest.cohort,
        paths=paths,
        target_loader=guest.target_loader,
        owner_ready=admit,
        source_ready=check_window,
        deadline=slot.ends_at,
        control_root=Path(token_root),
        clock=clock,
    )
    if type(result) is not dict or type(result.get("pending")) is not bool:
        raise ValueError("h3_capsule_result_invalid")
    calls = result.get("native_calls")
    if type(calls) is not int or not 0 <= calls <= 32:
        raise ValueError("h3_capsule_result_invalid")
    native = result.get("native")
    status = native.get("status") if type(native) is dict else None
    if result["pending"]:
        status = "pending"
    elif status not in _NATIVE_STATUS - {"pending"}:
        status = "no_intent" if result.get("stop") == "empty_original_basket" else "unavailable"
    return dict(
        schema="dec4-net25-capsule-outcome-v1",
        status=status,
        pending=True if result["pending"] else None,
        phase=slot.phase,
        input_ref=slot.input_ref,
        policy_ref=slot.policy_ref,
        source_ref=guest.cohort.source_ref,
        native_calls=calls,
        financial_claim="UNKNOWN",
        reservation_release=False,
    )
