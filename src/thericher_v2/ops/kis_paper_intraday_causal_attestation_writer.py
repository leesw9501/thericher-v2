"""Write one future-only, source-safe intraday causal-attestation artifact.

The writer is deliberately networkless and does not create or alter a scheduled
terminal. It accepts an external-observer input only after the current terminal
already proves its own capture, availability, and pair bindings. The external
observer remains assumed-honest provenance, not cryptographic proof of a
provider fact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION

from .kis_paper_intraday_head_schedule_receipt import (
    KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_ARTIFACT_DIRECTORY,
    KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_KIND,
    KisPaperIntradayHeadScheduleFact,
    KisPaperIntradayHeadScheduleReceiptError,
    read_kis_paper_intraday_head_schedule_fact_from_artifact_root,
)

KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_INPUT_DIRECTORY = (
    "kis-paper-intraday-causal-attestation-input-v1"
)
KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_INPUT_KIND = (
    "kis_paper_intraday_head_causal_attestation_input"
)
DEFAULT_KIS_PAPER_INTRADAY_HEAD_CAPTURE_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\intraday-head"
)

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_ARTIFACT_POLICY = {
    "credentials_in_receipt": False,
    "account_data_in_receipt": False,
    "raw_market_data_in_receipt": False,
    "broker_order_data_in_receipt": False,
    "repo_storage_allowed": False,
}
_INPUT_CLAIM = (
    "external causal-observation input only; assumed-honest external observer, "
    "not cryptographic proof of provider origin, a model result, PnL claim, or broker action"
)
_OUTPUT_CLAIM = (
    "independent source-safe causal-condition attestation only; not cryptographic "
    "proof of provider origin, a model result, PnL claim, or broker action"
)
_INPUT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "schedule_run_id",
        "schedule_observed_at",
        "decision_time_utc",
        "availability_observed_at",
        "finality_observed_at",
        "attestation_origin",
        "clock_authority",
        "timezone_dst_session_rule",
        "completed_bar_geometry",
        "chronological_boundary",
        "decision_time_availability",
        "provider_finality",
        "artifact_policy",
        "claim",
    }
)


@dataclass(frozen=True)
class KisPaperIntradayCausalAttestationInput:
    """The minimal, source-safe input supplied by an external observer."""

    schedule_run_id: str
    schedule_observed_at: datetime
    decision_time_utc: datetime
    availability_observed_at: datetime
    finality_observed_at: datetime


@dataclass(frozen=True)
class KisPaperIntradayCausalAttestationWriteResult:
    """One source-safe writer result with no market, account, or broker data."""

    status: Literal["written", "already_written", "not_written"]
    reason: str | None
    attestation_sha256: str | None
    evidence_path: Path | None

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_KIND,
            "status": self.status,
            "reason": self.reason,
            "attestation_sha256": self.attestation_sha256,
            "artifact_policy": dict(_ARTIFACT_POLICY),
            "claim": _OUTPUT_CLAIM,
        }


def write_current_kis_paper_intraday_causal_attestation(
    *,
    artifact_root: Path,
    repository_root: Path,
    capture_cache_root: Path = DEFAULT_KIS_PAPER_INTRADAY_HEAD_CAPTURE_CACHE_ROOT,
) -> KisPaperIntradayCausalAttestationWriteResult:
    """Bind one eligible current terminal to an existing external-observer input.

    A missing or incomplete input intentionally produces no artifact. The
    current task never calls this function; a future owner must still decide
    whether to bind the resulting hash into a new immutable terminal.
    """

    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    try:
        fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            root,
            repository_root=repository_root,
            capture_cache_root=capture_cache_root,
            observation_artifact_root=root,
        )
    except (KisPaperIntradayHeadScheduleReceiptError, OSError, ValueError):
        return _not_written("terminal_unavailable")

    base_reason = _base_input_unavailable_reason(fact)
    if base_reason is not None:
        return _not_written(base_reason)

    input_path = _input_path(root=root, run_id=fact.run_id)
    try:
        source_input = _read_input(path=input_path, root=root)
    except FileNotFoundError:
        return _not_written("input_missing")
    except ValueError:
        return _not_written("input_invalid")

    input_reason = _input_unavailable_reason(source_input=source_input, fact=fact)
    if input_reason is not None:
        return _not_written(input_reason)

    payload = _attestation_payload(source_input=source_input, fact=fact)
    encoded = _canonical_json(payload)
    attestation_sha256 = _sha256(encoded)
    destination = _output_path(root=root, run_id=fact.run_id)
    try:
        created = _write_or_verify(destination=destination, encoded=encoded, root=root)
    except ValueError:
        return _not_written("output_conflict")
    return KisPaperIntradayCausalAttestationWriteResult(
        status="written" if created else "already_written",
        reason=None,
        attestation_sha256=attestation_sha256,
        evidence_path=destination,
    )


def _not_written(reason: str) -> KisPaperIntradayCausalAttestationWriteResult:
    return KisPaperIntradayCausalAttestationWriteResult(
        status="not_written",
        reason=reason,
        attestation_sha256=None,
        evidence_path=None,
    )


def _base_input_unavailable_reason(fact: KisPaperIntradayHeadScheduleFact) -> str | None:
    if fact.terminal_status != "complete":
        return "terminal_recovery"
    if fact.coverage_binding_status != "verified":
        return "session_capture_unbound"
    if fact.current_session_cumulative_coverage_category != "complete":
        return "session_coverage_incomplete"
    if fact.session_capture_receipt_sha256 is None:
        return "session_capture_unbound"
    if (
        fact.availability_binding_status != "verified"
        or fact.availability_status != "qualified_for_prospective_input"
        or fact.availability_summary_sha256 is None
    ):
        return "availability_unavailable"
    if (
        fact.observation_binding_status != "verified"
        or fact.observation_attempt_status != "observed"
        or fact.observation_store_outcome != "appended"
        or fact.observation_attempt_sha256 is None
    ):
        return "prospective_observation_unavailable"
    if fact.causal_attestation_binding_status != "not_recorded":
        return "terminal_already_bound"
    return None


def _read_input(
    *,
    path: Path,
    root: Path,
) -> KisPaperIntradayCausalAttestationInput:
    _require_external_regular_file(root=root, path=path)
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("causal attestation input is invalid") from error
    if (
        not isinstance(payload, dict)
        or frozenset(payload) != _INPUT_KEYS
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_INPUT_KIND
        or payload.get("artifact_policy") != _ARTIFACT_POLICY
        or payload.get("claim") != _INPUT_CLAIM
        or payload.get("attestation_origin") != "independent_observer"
        or payload.get("clock_authority") != "independent_utc_clock"
        or payload.get("timezone_dst_session_rule") != "America_New_York_IANA_DST"
        or payload.get("completed_bar_geometry")
        != "m1_regular_session_complete_through_1530_et"
        or payload.get("chronological_boundary") != "non_overlapping"
        or payload.get("decision_time_availability") != "observed_at_decision_time"
        or payload.get("provider_finality") != "observed_final"
    ):
        raise ValueError("causal attestation input is invalid")
    return KisPaperIntradayCausalAttestationInput(
        schedule_run_id=_safe_id(payload.get("schedule_run_id"), "input run id"),
        schedule_observed_at=_utc(payload.get("schedule_observed_at"), "input observed at"),
        decision_time_utc=_utc(payload.get("decision_time_utc"), "decision time"),
        availability_observed_at=_utc(
            payload.get("availability_observed_at"), "availability observed at"
        ),
        finality_observed_at=_utc(payload.get("finality_observed_at"), "finality observed at"),
    )


def _input_unavailable_reason(
    *,
    source_input: KisPaperIntradayCausalAttestationInput,
    fact: KisPaperIntradayHeadScheduleFact,
) -> str | None:
    if (
        source_input.schedule_run_id != fact.run_id
        or source_input.schedule_observed_at != fact.observed_at
    ):
        return "input_binding_mismatch"
    if not (
        source_input.availability_observed_at <= source_input.decision_time_utc
        <= source_input.finality_observed_at <= fact.observed_at
    ):
        return "input_time_order_invalid"
    return None


def _attestation_payload(
    *,
    source_input: KisPaperIntradayCausalAttestationInput,
    fact: KisPaperIntradayHeadScheduleFact,
) -> dict[str, object]:
    assert fact.session_capture_receipt_sha256 is not None
    assert fact.availability_summary_sha256 is not None
    assert fact.observation_attempt_sha256 is not None
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_KIND,
        "schedule_run_id": source_input.schedule_run_id,
        "schedule_observed_at": _utc_marker(source_input.schedule_observed_at),
        "session_capture_receipt_sha256": fact.session_capture_receipt_sha256,
        "availability_summary_sha256": fact.availability_summary_sha256,
        "observation_attempt_sha256": fact.observation_attempt_sha256,
        "attestation_origin": "independent_observer",
        "clock_authority": "independent_utc_clock",
        "timezone_dst_session_rule": "America_New_York_IANA_DST",
        "completed_bar_geometry": "m1_regular_session_complete_through_1530_et",
        "chronological_boundary": "non_overlapping",
        "decision_time_availability": "observed_at_decision_time",
        "provider_finality": "observed_final",
        "artifact_policy": dict(_ARTIFACT_POLICY),
        "claim": _OUTPUT_CLAIM,
    }


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    requested = artifact_root.absolute()
    repository = repository_root.resolve()
    _require_no_link_ancestors(requested)
    root = requested.resolve()
    if not root.is_dir() or root.is_symlink() or root.is_relative_to(repository):
        raise ValueError("artifact root must be an external directory")
    return root


def _input_path(*, root: Path, run_id: str) -> Path:
    return root / "data" / KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_INPUT_DIRECTORY / (
        f"{run_id}.json"
    )


def _output_path(*, root: Path, run_id: str) -> Path:
    return root / "data" / KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_ARTIFACT_DIRECTORY / (
        f"{run_id}.json"
    )


def _require_external_regular_file(*, root: Path, path: Path) -> None:
    _require_no_link_ancestors(path)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("causal attestation input is invalid")


def _write_or_verify(*, destination: Path, encoded: bytes, root: Path) -> bool:
    _require_no_link_ancestors(destination)
    if not destination.resolve().is_relative_to(root):
        raise ValueError("causal attestation output is invalid")
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != encoded:
            raise ValueError("causal attestation output conflicts")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_no_link_ancestors(destination.parent)
    staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        if destination.exists():
            if destination.is_symlink() or destination.read_bytes() != encoded:
                raise ValueError("causal attestation output conflicts")
            return False
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return True


def _require_no_link_ancestors(path: Path) -> None:
    current = path.absolute()
    while True:
        if current.exists() and current.is_symlink():
            raise ValueError("causal attestation path is invalid")
        if current.parent == current:
            return
        current = current.parent


def _safe_id(value: object, label: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} is invalid")
    return parsed.astimezone(UTC)


def _utc_marker(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: dict[str, object]) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return (encoded + "\n").encode("ascii")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
