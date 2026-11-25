"""Bind the Dec3 native edition for the Nov30 cohort's block-end replay.

This module handles private metadata only. The outer owners must independently
attest the prelaunch pin, sole capture attempt and closure, and enforce access
isolation and a one-shot block read. A receipt is not proof of those facts.
"""

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

from thericher_v2.data.kis_paper_h3_capture import _is_utc, _read_native
from thericher_v2.data.kis_paper_h3_daily_panel import NET25_H3_AXIS, H3DailyPanelPlan
from thericher_v2.data.kis_paper_h3_producer import (
    CAPTURE_CLOSES_UTC,
    CAPTURE_OPENS_UTC,
    INPUT_HARD_STOP_UTC,
)
from thericher_v2.execution.kis_paper_data_capture import _safe_path

_SCHEMA = "NOV30_H3_TARGET_CUSTODY_V1"
_COHORT = ("2026-11-30", "2026-12-03")
_EXPIRY_CLOSE = datetime(2026, 12, 3, 21, tzinfo=UTC)
_BLOCK_LAST_CLOSE = datetime(2026, 12, 28, 21, tzinfo=UTC)
_RECEIPT = "TARGET-CUSTODY.json"
_STATE = "capture-state.json"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _document(raw: bytes) -> dict:
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError
        return result

    def reject_constant(_value):
        raise ValueError

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)
        if type(value) is dict:
            return value
    except (ValueError, RecursionError):
        pass
    raise ValueError("h3_target_metadata_invalid")


def _stamp(value: object) -> datetime:
    if type(value) is str:
        try:
            result = datetime.fromisoformat(value)
            if _is_utc(result) and result.isoformat() == value:
                return result
        except ValueError:
            pass
    raise ValueError("h3_target_clock_invalid")


@dataclass(frozen=True)
class Nov30H3TargetPins:
    """Exact pins for an externally attested pre-close launch definition."""

    owner: str
    source_sha256: str
    attempt_sha256: str
    market_root: Path
    artifact_root: Path
    target_root: Path
    prebound_at: datetime
    release_at: datetime
    synthetic: bool

    @property
    def prebind_sha256(self) -> str:
        if (
            type(self.owner) is not str
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", self.owner)
            or not all(_digest(x) for x in (self.source_sha256, self.attempt_sha256))
            or type(self.synthetic) is not bool
        ):
            raise ValueError("h3_target_pins_invalid")
        roots = (self.market_root, self.artifact_root, self.target_root)
        if any(not p.is_absolute() or p == p.parent or ".." in p.parts for p in roots) or any(
            a.is_relative_to(b) or b.is_relative_to(a) for a, b in combinations(roots, 2)
        ):
            raise ValueError("h3_target_roots_invalid")
        if not (
            _is_utc(self.prebound_at)
            and self.prebound_at < _EXPIRY_CLOSE
            and _is_utc(self.release_at)
            and self.release_at >= _BLOCK_LAST_CLOSE
        ):
            raise ValueError("h3_target_pin_clock_invalid")
        plan = H3DailyPanelPlan(NET25_H3_AXIS)
        return _sha(
            _json(
                dict(
                    schema=_SCHEMA,
                    cohort=_COHORT,
                    owner=self.owner,
                    source=self.source_sha256,
                    attempt=self.attempt_sha256,
                    market_root=str(self.market_root),
                    artifact_root=str(self.artifact_root),
                    target_root=str(self.target_root),
                    queries=[q.document() for q in plan.queries],
                    capture_opens=CAPTURE_OPENS_UTC.isoformat(),
                    capture_closes=CAPTURE_CLOSES_UTC.isoformat(),
                    seal_before=INPUT_HARD_STOP_UTC.isoformat(),
                    prebound_at=self.prebound_at.isoformat(),
                    release_at=self.release_at.isoformat(),
                    synthetic=self.synthetic,
                )
            )
        )


@dataclass(frozen=True)
class Nov30H3TargetCustody:
    capture_state_sha256: str
    capture_closed_at: datetime
    sealed_at: datetime

    def _encode(self, prebind_sha256: str) -> bytes:
        if not _digest(self.capture_state_sha256):
            raise ValueError("h3_target_capture_digest_invalid")
        if not (
            _is_utc(self.capture_closed_at)
            and _is_utc(self.sealed_at)
            and CAPTURE_OPENS_UTC <= self.capture_closed_at < CAPTURE_CLOSES_UTC
            and self.capture_closed_at <= self.sealed_at < INPUT_HARD_STOP_UTC
        ):
            raise ValueError("h3_target_seal_clock_invalid")
        return _json(
            dict(
                schema=_SCHEMA,
                cohort=_COHORT,
                prebind_sha256=prebind_sha256,
                capture_state_sha256=self.capture_state_sha256,
                capture_closed_at=self.capture_closed_at.isoformat(),
                sealed_at=self.sealed_at.isoformat(),
            )
        )


def _require_prebind(pins: Nov30H3TargetPins, expected: str) -> None:
    if not _digest(expected) or pins.prebind_sha256 != expected:
        raise ValueError("h3_target_prebind_mismatch")


def _check_capture_state(pins: Nov30H3TargetPins, custody: Nov30H3TargetCustody) -> None:
    root = pins.artifact_root
    raw = _read_native(root, str(root / _STATE))
    if _sha(raw) != custody.capture_state_sha256:
        raise ValueError("h3_target_capture_digest_mismatch")
    state = _document(raw)
    plan = H3DailyPanelPlan(NET25_H3_AXIS)
    contract, completed = state.get("contract"), state.get("completed")
    if not (
        state.get("version") == "kis-paper-data-capture-v1"
        and type(contract) is dict
        and contract.get("market_root") == str(pins.market_root)
        and contract.get("artifact_root") == str(root)
        and _json(contract.get("queries")) == _json([q.document() for q in plan.queries])
        and all(
            type(state.get(k)) is int and state[k] == n
            for k, n in (("GET", 19), ("POST", 1), ("retry", 0))
        )
        and "pending" in state
        and state["pending"] is None
        and state.get("failed_attempts") == []
        and type(completed) is dict
        and set(completed) == {q.key for q in plan.queries}
    ):
        raise ValueError("h3_target_capture_contract_mismatch")
    started = _stamp(state.get("started_utc"))
    if not CAPTURE_OPENS_UTC <= started <= custody.capture_closed_at:
        raise ValueError("h3_target_capture_start_invalid")
    for ordinal, query in enumerate(plan.queries, 1):
        item = completed[query.key]
        ref = item.get("native") if type(item) is dict else None
        if not (
            type(ref) is dict
            and set(ref) == {"path", "sha256"}
            and ref["path"] == str(pins.market_root / f"GET-{ordinal:06d}.native.json")
            and _digest(ref["sha256"])
            and item.get("query_key") == query.key
            and item.get("status") == "ACCEPTED"
            and item.get("cache_hit") is False
            and type(item.get("row_count")) is int
            and 60 <= item["row_count"] <= len(plan.capture_sessions)
        ):
            raise ValueError("h3_target_capture_member_mismatch")


def write_nov30_h3_target_custody(
    pins: Nov30H3TargetPins,
    *,
    prebind_sha256: str,
    capture_state_sha256: str,
    capture_closed_at: datetime,
    clock: Callable[[], datetime],
) -> str:
    """Seal the closed native capture's two returned pins, without opening any pages.

    Call from the prebound owner, directly from the sole capture result, before
    feature publication. The owner must attest the returned seal digest only
    after successful closure; partial or late writes consume the destination.
    """
    _require_prebind(pins, prebind_sha256)
    custody = Nov30H3TargetCustody(capture_state_sha256, capture_closed_at, clock())
    raw = custody._encode(prebind_sha256)
    _check_capture_state(pins, custody)
    if _safe_path(pins.target_root) != pins.target_root:
        raise ValueError("h3_target_roots_invalid")
    pins.target_root.mkdir()
    path = pins.target_root / _RECEIPT
    if _safe_path(path) != path:
        raise ValueError("h3_target_roots_invalid")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if _read_native(pins.target_root, str(path)) != raw:
        raise ValueError("h3_target_seal_changed")
    now = clock()
    if not _is_utc(now) or not custody.sealed_at <= now < INPUT_HARD_STOP_UTC:
        raise ValueError("h3_target_seal_clock_invalid")
    return _sha(raw)


def read_nov30_h3_target_custody(
    pins: Nov30H3TargetPins,
    *,
    prebind_sha256: str,
    expected_sha256: str,
    now: datetime,
) -> Nov30H3TargetCustody:
    """Verify metadata after the prebound release; never read or return prices.

    The block owner must supply the independently retained prebind digest and
    final owner-closure seal digest, not digests discovered in the target root.
    A later mark reader must verify each original page against the bound state
    before qualifying/projecting it, under the same block-end read authority.
    """
    if not _is_utc(now) or not _is_utc(pins.release_at) or now < pins.release_at:
        raise ValueError("h3_target_release_denied")
    _require_prebind(pins, prebind_sha256)
    if not _digest(expected_sha256):
        raise ValueError("h3_target_seal_digest_invalid")
    raw = _read_native(pins.target_root, str(pins.target_root / _RECEIPT))
    if _sha(raw) != expected_sha256:
        raise ValueError("h3_target_seal_digest_mismatch")
    doc = _document(raw)
    custody = Nov30H3TargetCustody(
        doc.get("capture_state_sha256"),
        _stamp(doc.get("capture_closed_at")),
        _stamp(doc.get("sealed_at")),
    )
    if custody._encode(prebind_sha256) != raw:
        raise ValueError("h3_target_seal_binding_mismatch")
    _check_capture_state(pins, custody)
    return custody
