"""Carry the Dec4 native proposal bytes to the Dec9 exit loader."""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.execution.kis_paper_data_capture import _safe_path
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.model_paper_weights import (
    MODEL_PAPER_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3_PROFILE,
    ModelPaperWeightsInput,
    load_model_paper_weights_input,
)

_ENTRY = SessionWindow(
    datetime(2026, 12, 4, 14, 30, tzinfo=UTC), datetime(2026, 12, 4, 21, tzinfo=UTC)
)
_EXIT = SessionWindow(
    datetime(2026, 12, 9, 14, 30, tzinfo=UTC), datetime(2026, 12, 9, 21, tzinfo=UTC)
)
_MAX_PAYLOAD = 1024 * 1024  # Native codec limit.


@dataclass(frozen=True)
class Dec4H3RetainedRef:
    """Pins supplied by the named owner, not discovered from retained storage."""

    path: Path
    source_sha256: str
    point_sha256: str
    policy_ref: str
    payload_sha256: str
    synthetic: bool

    def _header(self) -> bytes:
        pins = (self.source_sha256, self.point_sha256, self.payload_sha256)
        if (
            any(type(pin) is not str or re.fullmatch(r"[0-9a-f]{64}", pin) is None for pin in pins)
            or type(self.policy_ref) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.policy_ref) is None
            or type(self.synthetic) is not bool
        ):
            raise ValueError("h3_retained_pin_invalid")
        return (
            json.dumps(
                dict(
                    schema="DEC4_H3_RETAINED_INPUT_V2",
                    source_sha256=self.source_sha256,
                    point_sha256=self.point_sha256,
                    policy_ref=self.policy_ref,
                    payload_sha256=self.payload_sha256,
                    synthetic=self.synthetic,
                    entry_open=_ENTRY.open_ts.isoformat(),
                    exit_open=_EXIT.open_ts.isoformat(),
                ),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
            + b"\n"
        )


def _checked_path(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or _safe_path(path) != path:
        raise ValueError("h3_retained_path_invalid")
    return path


def _load(payload: bytes, expected: Dec4H3RetainedRef) -> ModelPaperWeightsInput:
    value = load_model_paper_weights_input(
        payload,
        expected_sha256=expected.payload_sha256,
        expected_policy_ref=expected.policy_ref,
    )
    if (
        value.profile != MODEL_PAPER_WEIGHTS_US_CASH_NET25_OPEN_ELAPSED3_PROFILE
        or value.entry_session != _ENTRY
        or value.exit_session != _EXIT
        or value.metadata.original_basis_gross_ceiling != Decimal("0.1")
        or value.metadata.full_output_ref != "sha256:" + expected.point_sha256
    ):
        raise ValueError("h3_retained_contract_mismatch")
    return value


def retain_dec4_h3_input(
    path: Path,
    payload: bytes,
    *,
    source_sha256: str,
    point_sha256: str,
    policy_ref: str,
    synthetic: bool,
) -> Dec4H3RetainedRef:
    """Bind caller-attested source/POINT digests to the exact native bytes once."""
    if type(payload) is not bytes or not 0 < len(payload) <= _MAX_PAYLOAD:
        raise ValueError("h3_retained_payload_invalid")
    ref = Dec4H3RetainedRef(
        path,
        source_sha256,
        point_sha256,
        policy_ref,
        hashlib.sha256(payload).hexdigest(),
        synthetic,
    )
    header = ref._header()
    _load(payload, ref)
    with _checked_path(path).open("xb") as stream:
        stream.write(header + payload)
        stream.flush()
        os.fsync(stream.fileno())
    return ref


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns)


def restore_dec4_h3_input(
    expected: Dec4H3RetainedRef, *, synthetic_fixture: bool = False
) -> ModelPaperWeightsInput:
    """Read only the exact retained path; never discover, regenerate or recover it."""
    if type(expected) is not Dec4H3RetainedRef:
        raise ValueError("h3_retained_reference_required")
    if expected.synthetic is not synthetic_fixture:
        raise ValueError("h3_retained_fixture_mode_mismatch")
    header = expected._header()
    path = _checked_path(expected.path)
    before = path.lstat()
    limit = len(header) + _MAX_PAYLOAD
    if not stat.S_ISREG(before.st_mode) or not len(header) < before.st_size <= limit:
        raise ValueError("h3_retained_file_invalid")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if _identity(opened) != _identity(before):
            raise ValueError("h3_retained_file_unstable")
        raw = stream.read(limit + 1)
        finished = os.fstat(stream.fileno())
    after = _checked_path(path).lstat()
    if len(raw) != before.st_size or any(
        _identity(info) != _identity(before) for info in (finished, after)
    ):
        raise ValueError("h3_retained_file_unstable")
    if not raw.startswith(header):
        raise ValueError("h3_retained_binding_mismatch")
    return _load(raw[len(header) :], expected)


def _entry_reference_path(retained: Path) -> Path:
    retained = _checked_path(retained)
    return retained.with_name(retained.name + ".entry-reference.json")


def _entry_reference_scope(leg, basis, policy):
    return {
        "schema": "DEC4_H3_ORIGINAL_ENTRY_REFERENCE_V1",
        "source": leg.identity["source"],
        "release": leg.identity["release"],
        "bank": leg.key,
        "basis": basis,
        "policy": policy,
    }


def _stable_reference(leg, *files):
    def check():
        leg.check()
        if any(pv._read(path) != snapshot for path, snapshot in files):
            raise ValueError("h3_entry_reference_changed")

    check()
    return check


def publish_dec4_entry_reference(leg, ref: Dec4H3RetainedRef, *, basis: str):
    """Publish once, inside the verified entry leg and before its first visit."""
    leg.check()
    if (
        type(ref) is not Dec4H3RetainedRef
        or ref.source_sha256 != leg.identity["source"]
        or leg.record["visits"]
    ):
        raise ValueError("h3_entry_reference_scope")
    ref._header()  # Validate its exact reference format before writing.
    link = _entry_reference_scope(leg, basis, ref.policy_ref) | {
        "entry_identity": leg.identity,
        "entry_owner": leg.record["owner"],
        "point": ref.point_sha256,
        "payload": ref.payload_sha256,
        "synthetic": ref.synthetic,
    }
    path = _entry_reference_path(ref.path)
    return _stable_reference(leg, (path, pv._new(path, pv.encode(link))))


def read_dec4_entry_reference(leg, path: Path, *, basis: str, policy: str, synthetic: bool):
    """Bind original input to a positively closed leg; this proves no fill."""
    leg.check()
    reference_path = _entry_reference_path(path)
    try:
        snapshot = pv._read(reference_path)
        link = pv._decode(snapshot[0])
        scope = _entry_reference_scope(leg, basis, policy)
        if (
            type(link) is not dict
            or link.keys()
            != scope.keys() | {"entry_identity", "entry_owner", "point", "payload", "synthetic"}
            or any(link[k] != val for k, val in scope.items())
            or link["synthetic"] is not synthetic
        ):
            raise ValueError
        original = link["entry_identity"]
        pv._identity(original, leg.key)
        if original["run"] == leg.identity["run"] or any(
            original[k] != leg.identity[k] for k in ("source", "release", "group", "member")
        ):
            raise ValueError
        closure_path = leg.root / ("CLOSED-" + original["run"] + ".json")
        closure_snapshot = pv._read(closure_path)
        closure = pv._decode(closure_snapshot[0])
        record = closure["record"]
        pv._record(record, leg.key)
        if (
            closure.keys()
            != {
                "status",
                "record",
                "same_native_intent_reconciliation_required",
                "reservation_or_budget_release",
            }
            or closure["status"] != "CLOSED_OPERATIONAL_ONLY"
            or closure["same_native_intent_reconciliation_required"] is not True
            or closure["reservation_or_budget_release"] is not False
            or record["identity"] != original
            or record["owner"] != link["entry_owner"]
            or len(record["visits"]) != 1
            or (record["visits"][0]["kind"], record["visits"][0]["status"]) != ("effect", "CLOSED")
            or not record["visits"][0]["children"]
            or record["visits"][0]["create"]["resolution"]
            not in {"ACK_EXACT_CID", "DISCOVERED_EXACT_SCOPE"}
        ):
            raise ValueError
        ref = Dec4H3RetainedRef(
            path, scope["source"], link["point"], policy, link["payload"], synthetic
        )
        ref._header()
        stable = _stable_reference(
            leg, (reference_path, snapshot), (closure_path, closure_snapshot)
        )
    except (OSError, AttributeError, KeyError, TypeError, ValueError, pv.Denied):
        raise ValueError("h3_original_entry_reference_withheld") from None
    return ref, stable
