"""Read-only sanitized lifecycle facts for KIS virtual-paper canary evidence."""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

_LIFECYCLE_STATES = frozenset(
    {"not_submitted", "acknowledged", "rejected", "outcome_unknown", "cancelled"}
)
_ATTRIBUTION_ELIGIBILITY = frozenset(
    {"not_eligible", "pending_reconciliation", "open", "realized", "unavailable"}
)
_SUBMIT_RESPONSE_CATEGORIES = frozenset(
    {
        "acknowledged_order_reference",
        "http_non_200",
        "legacy_response_incomplete",
        "not_observed",
        "payload_invalid",
        "provider_rejected",
        "success_order_reference_missing",
        "success_output_missing",
        "transport_unavailable",
    }
)
_SESSION_EVIDENCE_KIND = "kis_paper_canary_session_evidence"
_SESSION_STATUSES = frozenset(
    {
        "preview",
        "not_due",
        "paused",
        "quote_unavailable",
        "recovery_required",
        "canary_completed",
    }
)
_SESSION_STATUS_REASONS = {
    "preview": frozenset({"preview"}),
    "not_due": frozenset({"outside_regular_session", "session_unavailable"}),
    "paused": frozenset({"pause_buys_active"}),
    "quote_unavailable": frozenset(
        {
            "quote_unavailable",
            "quote_rejected",
            "quote_response_blank",
            "quote_response_incomplete",
            "quote_price_off_tick",
            "quote_scale_mismatch",
            "quote_tick_invalid",
            "quote_timestamp_invalid",
            "quote_timestamp_stale",
        }
    ),
    "recovery_required": frozenset(
        {"prior_state_unavailable", "prior_submission_unresolved"}
    ),
}
_CANARY_PHASES = frozenset(
    {
        "intent_recorded",
        "submission_started",
        "submitted",
        "rejected",
        "outcome_unknown",
        "cancel_started",
        "cancelled",
    }
)
_PENDING_CANARY_PHASES = frozenset(
    {"submission_started", "submitted", "outcome_unknown", "cancel_started"}
)
_SESSION_EVIDENCE_KEYS = frozenset(
    {
        "kind",
        "schema_version",
        "session_id",
        "status",
        "reason_code",
        "observed_at",
        "run_id",
        "canary_phase",
        "canary_reason_code",
        "submit_upstream_code",
        "reconciliation_status",
        "reconciliation_reason_code",
        "paper_only",
        "evidence_path",
    }
)


class PaperCanaryLifecycleError(ValueError):
    """External virtual-Paper evidence is missing, malformed, or unsafe."""


@dataclass(frozen=True)
class PaperCanaryLifecycleFact:
    """One read-only attribution input with no broker body or account value."""

    run_id: str
    intent_ref: str
    decision_ref: str | None
    observed_at: datetime
    lifecycle_state: str
    decision_class: Literal["enter", "exit"]
    reconciliation_status: Literal["not_run", "clean", "unresolved"]
    submit_response_category: str
    attribution_eligibility: str
    sizing_status: Literal["fixed_canary", "not_submitted"]
    evidence_sha256: str
    attribution_ref: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _safe_id(self.run_id, "run_id")
        _sha256_ref(self.intent_ref, "intent_ref")
        if self.decision_ref is not None:
            _decision_ref(self.decision_ref)
        if self.attribution_ref is not None:
            _sha256_ref(self.attribution_ref, "attribution_ref")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.lifecycle_state not in _LIFECYCLE_STATES:
            raise PaperCanaryLifecycleError("lifecycle_state_invalid")
        if self.decision_class not in {"enter", "exit"}:
            raise PaperCanaryLifecycleError("decision_class_invalid")
        if self.reconciliation_status not in {"not_run", "clean", "unresolved"}:
            raise PaperCanaryLifecycleError("reconciliation_status_invalid")
        if self.submit_response_category not in _SUBMIT_RESPONSE_CATEGORIES:
            raise PaperCanaryLifecycleError("submit_response_category_invalid")
        if self.attribution_eligibility not in _ATTRIBUTION_ELIGIBILITY:
            raise PaperCanaryLifecycleError("attribution_eligibility_invalid")
        if self.sizing_status not in {"fixed_canary", "not_submitted"}:
            raise PaperCanaryLifecycleError("sizing_status_invalid")
        _sha256_ref(self.evidence_sha256, "evidence_sha256")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_canary_lifecycle_fact",
            "route": "kis_paper",
            "paper_only": True,
            "run_id": self.run_id,
            "intent_ref": self.intent_ref,
            "decision_ref": self.decision_ref,
            "attribution_ref": self.attribution_ref,
            "decision_class": self.decision_class,
            "model_ref": "deterministic_canary",
            "observed_at": self.observed_at.isoformat(),
            "lifecycle_state": self.lifecycle_state,
            "reconciliation_status": self.reconciliation_status,
            "submit_response_category": self.submit_response_category,
            "attribution_eligibility": self.attribution_eligibility,
            "sizing_status": self.sizing_status,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True)
class PaperCanarySessionFact:
    """One explicit-session fact that cannot be mistaken for a lifecycle result."""

    session_id: str
    status: str
    result_class: Literal[
        "no_new_intent",
        "recovery_required",
        "direct_lifecycle_required",
    ]
    reason_code: str
    observed_at: datetime
    evidence_sha256: str
    run_id: str | None = None
    canary_phase: str | None = None
    reconciliation_status: Literal["clean", "unresolved"] | None = None
    schema_version: int = SCHEMA_VERSION

    def safe_payload(self) -> dict[str, object]:
        """Project only source-safe routing and recovery facts from one session."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_canary_session_fact",
            "route": "kis_paper",
            "paper_only": True,
            "session_id": self.session_id,
            "status": self.status,
            "result_class": self.result_class,
            "reason_code": (
                None if self.result_class == "direct_lifecycle_required" else self.reason_code
            ),
            "observed_at": self.observed_at.isoformat(),
            "run_id": self.run_id,
            "canary_phase": self.canary_phase,
            "reconciliation_status": self.reconciliation_status,
            "evidence_sha256": self.evidence_sha256,
        }


def read_paper_canary_lifecycle_fact(evidence_path: Path) -> PaperCanaryLifecycleFact:
    """Derive one safe lifecycle fact from an existing external evidence file."""

    try:
        encoded = evidence_path.read_bytes()
        payload = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid") from error
    if not isinstance(payload, Mapping):
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid")
    return paper_canary_lifecycle_fact_from_evidence(
        payload,
        evidence_sha256="sha256:" + hashlib.sha256(encoded).hexdigest(),
    )


def read_paper_canary_lifecycle_fact_from_artifact_root(
    artifact_root: Path,
    run_id: str,
) -> PaperCanaryLifecycleFact:
    """Read one direct-child external receipt and bind it to the requested run."""

    _safe_id(run_id, "run_id")
    evidence_path = _direct_canary_evidence_path(artifact_root, run_id)
    fact = read_paper_canary_lifecycle_fact(evidence_path)
    if fact.run_id != run_id:
        raise PaperCanaryLifecycleError("lifecycle_run_id_mismatch")
    return fact


def read_paper_canary_session_fact(evidence_path: Path) -> PaperCanarySessionFact:
    """Derive one safe session fact from a directly selected external receipt."""

    try:
        encoded = evidence_path.read_bytes()
        payload = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaperCanaryLifecycleError("session_evidence_invalid") from error
    if not isinstance(payload, Mapping):
        raise PaperCanaryLifecycleError("session_evidence_invalid")
    return paper_canary_session_fact_from_evidence(
        payload,
        evidence_sha256="sha256:" + hashlib.sha256(encoded).hexdigest(),
    )


def read_paper_canary_session_fact_from_artifact_root(
    artifact_root: Path,
    session_id: str,
) -> PaperCanarySessionFact:
    """Read one exact session receipt without selecting a latest artifact."""

    _session_id(session_id, "session_id")
    evidence_path = _direct_session_evidence_path(artifact_root, session_id)
    fact = read_paper_canary_session_fact(evidence_path)
    if fact.session_id != session_id:
        raise PaperCanaryLifecycleError("session_id_mismatch")
    return fact


def _direct_canary_evidence_path(artifact_root: Path, run_id: str) -> Path:
    execution_root = artifact_root / "execution"
    canary_root = execution_root / "kis-paper-canary"
    run_root = canary_root / run_id
    evidence_path = run_root / "evidence.json"
    for path in (artifact_root, execution_root, canary_root, run_root, evidence_path):
        _require_non_link(path)
    if not artifact_root.is_dir() or not execution_root.is_dir() or not canary_root.is_dir():
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid")
    if not run_root.is_dir() or not evidence_path.is_file():
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid")
    try:
        is_regular_file = stat.S_ISREG(evidence_path.stat().st_mode)
    except OSError as error:
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid") from error
    if not is_regular_file:
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid")
    return evidence_path


def _direct_session_evidence_path(artifact_root: Path, session_id: str) -> Path:
    execution_root = artifact_root / "execution"
    session_root = execution_root / "kis-paper-canary-session"
    selected_session_root = session_root / session_id
    evidence_path = selected_session_root / "evidence.json"
    for path in (
        artifact_root,
        execution_root,
        session_root,
        selected_session_root,
        evidence_path,
    ):
        _require_non_link(path)
    if not artifact_root.is_dir() or not execution_root.is_dir() or not session_root.is_dir():
        raise PaperCanaryLifecycleError("session_evidence_invalid")
    if not selected_session_root.is_dir() or not evidence_path.is_file():
        raise PaperCanaryLifecycleError("session_evidence_invalid")
    try:
        is_regular_file = stat.S_ISREG(evidence_path.stat().st_mode)
    except OSError as error:
        raise PaperCanaryLifecycleError("session_evidence_invalid") from error
    if not is_regular_file:
        raise PaperCanaryLifecycleError("session_evidence_invalid")
    return evidence_path


def _require_non_link(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid") from error
    is_reparse_point = bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point:
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid")


def paper_canary_lifecycle_fact_from_evidence(
    payload: Mapping[str, Any],
    *,
    evidence_sha256: str,
) -> PaperCanaryLifecycleFact:
    """Validate and project only the allowlisted fields from canary evidence."""

    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != "kis_paper_canary_evidence"
        or payload.get("paper_only") is not True
    ):
        raise PaperCanaryLifecycleError("lifecycle_evidence_invalid")
    reconciliation = payload.get("reconciliation")
    if not isinstance(reconciliation, Mapping):
        raise PaperCanaryLifecycleError("lifecycle_reconciliation_invalid")
    phase = _text(payload.get("phase"), "phase")
    lifecycle_state = _lifecycle_state(phase)
    reconciliation_status = _reconciliation_status(reconciliation.get("status"))
    account_status = _account_status(reconciliation.get("account_status"))
    matching_open_order = reconciliation.get("matching_open_order") is True
    category = _submit_response_category(
        payload.get("submit_response_category"),
        payload.get("reason_code"),
    )
    return PaperCanaryLifecycleFact(
        run_id=_text(payload.get("run_id"), "run_id"),
        intent_ref=_text(payload.get("intent_fingerprint"), "intent_fingerprint"),
        decision_ref=(
            None
            if payload.get("decision_ref") is None
            else _text(payload.get("decision_ref"), "decision_ref")
        ),
        observed_at=_utc(payload.get("observed_at"), "observed_at"),
        lifecycle_state=lifecycle_state,
        decision_class=_decision_class(payload.get("order_side")),
        reconciliation_status=reconciliation_status,
        submit_response_category=category,
        attribution_eligibility=_attribution_eligibility(
            lifecycle_state=lifecycle_state,
            reconciliation_status=reconciliation_status,
            account_status=account_status,
            matching_open_order=matching_open_order,
        ),
        sizing_status=("not_submitted" if lifecycle_state == "not_submitted" else "fixed_canary"),
        evidence_sha256=evidence_sha256,
        attribution_ref=(
            None
            if payload.get("attribution_ref") is None
            else _text(payload.get("attribution_ref"), "attribution_ref")
        ),
    )


def paper_canary_session_fact_from_evidence(
    payload: Mapping[str, Any],
    *,
    evidence_sha256: str,
) -> PaperCanarySessionFact:
    """Validate an exact scheduled-session envelope without claiming a lifecycle."""

    if (
        frozenset(payload) != _SESSION_EVIDENCE_KEYS
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != _SESSION_EVIDENCE_KIND
        or payload.get("paper_only") is not True
        or not isinstance(payload.get("evidence_path"), str)
        or not payload["evidence_path"]
    ):
        raise PaperCanaryLifecycleError("session_evidence_invalid")
    session_id = _required_session_id(payload["session_id"], "session_id")
    status = payload["status"]
    if not isinstance(status, str) or status not in _SESSION_STATUSES:
        raise PaperCanaryLifecycleError("session_status_invalid")
    reason_code = _required_session_token(payload["reason_code"], "reason_code")
    run_id = _optional_session_id(payload["run_id"], "run_id")
    canary_phase = _optional_session_token(payload["canary_phase"], "canary_phase")
    canary_reason_code = _optional_session_token(
        payload["canary_reason_code"],
        "canary_reason_code",
    )
    submit_upstream_code = _optional_session_token(
        payload["submit_upstream_code"],
        "submit_upstream_code",
    )
    reconciliation_status = _optional_reconciliation_status(payload["reconciliation_status"])
    reconciliation_reason_code = _optional_session_token(
        payload["reconciliation_reason_code"],
        "reconciliation_reason_code",
    )
    if status in {"preview", "not_due", "paused", "quote_unavailable"}:
        if reason_code not in _SESSION_STATUS_REASONS[status] or any(
            value is not None
            for value in (
                run_id,
                canary_phase,
                canary_reason_code,
                submit_upstream_code,
                reconciliation_status,
                reconciliation_reason_code,
            )
        ):
            raise PaperCanaryLifecycleError("session_no_intent_invalid")
        result_class: Literal[
            "no_new_intent",
            "recovery_required",
            "direct_lifecycle_required",
        ] = "no_new_intent"
    elif status == "recovery_required":
        if reason_code == "prior_state_unavailable":
            if any(
                value is not None
                for value in (
                    run_id,
                    canary_phase,
                    canary_reason_code,
                    submit_upstream_code,
                    reconciliation_status,
                    reconciliation_reason_code,
                )
            ):
                raise PaperCanaryLifecycleError("session_recovery_invalid")
        elif (
            reason_code != "prior_submission_unresolved"
            or run_id is None
            or canary_phase not in _PENDING_CANARY_PHASES
            or canary_reason_code is None
            or reconciliation_status not in {"clean", "unresolved"}
        ):
            raise PaperCanaryLifecycleError("session_recovery_invalid")
        result_class = "recovery_required"
    else:
        if (
            run_id is None
            or canary_phase not in _CANARY_PHASES
            or canary_reason_code != reason_code
            or reconciliation_status not in {"clean", "unresolved"}
        ):
            raise PaperCanaryLifecycleError("session_completion_invalid")
        result_class = "direct_lifecycle_required"
    _sha256_ref(evidence_sha256, "evidence_sha256")
    return PaperCanarySessionFact(
        session_id=session_id,
        status=status,
        result_class=result_class,
        reason_code=reason_code,
        observed_at=_utc(payload["observed_at"], "observed_at"),
        evidence_sha256=evidence_sha256,
        run_id=run_id,
        canary_phase=canary_phase,
        reconciliation_status=reconciliation_status,
    )


def _required_session_token(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise PaperCanaryLifecycleError(f"session_{field_name}_invalid")
    _session_token(value, field_name)
    return value


def _optional_session_token(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_session_token(value, field_name)


def _required_session_id(value: object, field_name: str) -> str:
    text = _required_session_token(value, field_name)
    _session_id(text, field_name)
    return text


def _optional_session_id(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_session_id(value, field_name)


def _optional_reconciliation_status(value: object) -> Literal["clean", "unresolved"] | None:
    if value is None:
        return None
    if value not in {"clean", "unresolved"}:
        raise PaperCanaryLifecycleError("session_reconciliation_invalid")
    return value  # type: ignore[return-value]


def _session_id(value: str, field_name: str) -> None:
    if (
        not value
        or value in {".", ".."}
        or len(value) > 80
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in value
        )
    ):
        raise PaperCanaryLifecycleError(f"session_{field_name}_invalid")


def _session_token(value: str, field_name: str) -> None:
    if (
        not value
        or len(value) > 96
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in value
        )
    ):
        raise PaperCanaryLifecycleError(f"session_{field_name}_invalid")


def _lifecycle_state(phase: str) -> str:
    if phase == "intent_recorded":
        return "not_submitted"
    if phase == "submitted":
        return "acknowledged"
    if phase == "rejected":
        return "rejected"
    if phase == "cancelled":
        return "cancelled"
    if phase in {"submission_started", "cancel_started", "outcome_unknown"}:
        return "outcome_unknown"
    raise PaperCanaryLifecycleError("lifecycle_phase_invalid")


def _decision_class(order_side: object) -> Literal["enter", "exit"]:
    """Map the durable order side without inventing a fill or PnL fact."""

    if order_side in {None, "buy"}:
        return "enter"
    if order_side == "sell":
        return "exit"
    raise PaperCanaryLifecycleError("lifecycle_order_side_invalid")


def _submit_response_category(value: object, reason_code: object) -> str:
    if isinstance(value, str) and value in _SUBMIT_RESPONSE_CATEGORIES:
        return value
    if reason_code in {"submit_http_4xx", "submit_http_5xx", "submit_rate_limited"}:
        return "http_non_200"
    if reason_code == "submit_kis_rejected":
        return "provider_rejected"
    if reason_code == "submit_response_incomplete":
        return "legacy_response_incomplete"
    if reason_code == "submit_transport_unknown":
        return "transport_unavailable"
    return "not_observed"


def _attribution_eligibility(
    *,
    lifecycle_state: str,
    reconciliation_status: str,
    account_status: str,
    matching_open_order: bool,
) -> str:
    if account_status == "unavailable":
        return "unavailable"
    if lifecycle_state == "outcome_unknown" or reconciliation_status == "unresolved":
        return "pending_reconciliation"
    if lifecycle_state == "acknowledged" and matching_open_order:
        return "open"
    return "not_eligible"


def _reconciliation_status(value: object) -> Literal["not_run", "clean", "unresolved"]:
    if value in {"not_run", "clean", "unresolved"}:
        return value
    raise PaperCanaryLifecycleError("lifecycle_reconciliation_invalid")


def _account_status(value: object) -> Literal["unknown", "available", "unavailable"]:
    if value in {"unknown", "available", "unavailable"}:
        return value
    raise PaperCanaryLifecycleError("lifecycle_account_invalid")


def _utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise PaperCanaryLifecycleError(f"lifecycle_{field_name}_invalid")
    try:
        return require_utc(datetime.fromisoformat(value), field_name).astimezone(UTC)
    except ValueError as error:
        raise PaperCanaryLifecycleError(f"lifecycle_{field_name}_invalid") from error


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PaperCanaryLifecycleError(f"lifecycle_{field_name}_invalid")
    return value


def _safe_id(value: str, field_name: str) -> None:
    if (
        not value
        or value in {".", ".."}
        or len(value) > 96
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in value
        )
    ):
        raise PaperCanaryLifecycleError(f"lifecycle_{field_name}_invalid")


def _sha256_ref(value: str, field_name: str) -> None:
    if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        raise PaperCanaryLifecycleError(f"lifecycle_{field_name}_invalid")
    if any(character not in "0123456789abcdef" for character in value.removeprefix("sha256:")):
        raise PaperCanaryLifecycleError(f"lifecycle_{field_name}_invalid")


def _decision_ref(value: str) -> None:
    if (
        not value.startswith("decision-")
        or len(value) != len("decision-") + 16
        or any(character not in "0123456789abcdef" for character in value.removeprefix("decision-"))
    ):
        raise PaperCanaryLifecycleError("lifecycle_decision_ref_invalid")
