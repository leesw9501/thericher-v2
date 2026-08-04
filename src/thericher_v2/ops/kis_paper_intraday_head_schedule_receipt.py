"""Persist source-safe terminal evidence for one intraday-head dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_KIND = "kis_paper_intraday_head_schedule_receipt"
KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY = (
    "execution/kis-paper-intraday-head-schedule"
)
KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME = "current.json"
KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_KIND = "kis_paper_intraday_head_schedule_runtime"
DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT = Path(
    r"D:\thericher-v2\model-artifacts"
)
SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE = 20
_DEFAULT_REPOSITORY_ROOT = Path.cwd()

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SCHEDULE_RECEIPT_CLAIM = (
    "scheduled dispatch observability only; not a model result, PnL claim, "
    "or broker action"
)
_SCHEDULE_RECEIPT_ARTIFACT_POLICY = {
    "credentials_in_receipt": False,
    "account_data_in_receipt": False,
    "raw_market_data_in_receipt": False,
    "broker_order_data_in_receipt": False,
    "repo_storage_allowed": False,
}
_SCHEDULE_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "run_id",
        "observed_at",
        "stages",
        "terminal",
        "artifact_policy",
        "claim",
    }
)
_SCHEDULE_RECEIPT_TERMINAL_KEYS = frozenset(
    {"status", "recovery_class", "scheduler_exit_code"}
)
_SCHEDULE_RUNTIME_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "run_id",
        "observed_at",
        "status",
        "recovery_class",
        "scheduler_exit_code",
        "receipt_sha256",
    }
)
_LOOP_STATUSES = frozenset({"embedded", "preview", "no_intent", "unavailable", "not_applicable"})
_SESSION_STATUSES = frozenset({"no_intent", "canary_completed", "unavailable", "not_applicable"})
_VALIDATION_STATUSES = frozenset({"validated", "not_run", "unavailable", "not_applicable"})
_SPY_CYCLE_STATUSES = frozenset(
    {"preview", "no_intent", "canary_completed", "unavailable", "not_applicable"}
)
_OBSERVATION_STATUSES = frozenset(
    {
        "pending",
        "unavailable",
        "complete",
        "not_applicable",
        "observed",
        "not_observed",
        "duplicate",
        "conflict",
        "cap_reached",
        "busy",
    }
)
_CAPTURE_CYCLE_STATUSES = frozenset(
    {
        "not_applicable",
        "unavailable",
        "outside_cycle_slot",
        "observed",
        "duplicate",
        "conflict",
        "input_unavailable",
        "outcome_unavailable",
        "input_mutated",
        "appended",
        "busy",
    }
)


@dataclass(frozen=True)
class KisPaperIntradayHeadScheduleReceipt:
    """One immutable terminal result for the existing scheduled dispatch."""

    run_id: str
    observed_at: datetime
    collection_exit_code: int
    prospective_spy_cycle_exit_code: int
    prospective_spy_cycle_status: str
    prospective_spy_cycle_id: str | None
    prospective_spy_canary_run_id: str | None
    prospective_loop_exit_code: int
    prospective_loop_status: str
    prospective_session_exit_code: int
    prospective_session_status: str
    prospective_session_id: str | None
    prospective_validation_exit_code: int
    prospective_validation_status: str
    prospective_validation_session_id: str | None
    observation_exit_code: int
    observation_status: str
    capture_cycle_exit_code: int
    capture_cycle_status: str
    terminal_status: str
    recovery_class: str
    scheduler_exit_code: int
    evidence_path: Path

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_KIND,
            "status": self.terminal_status,
            "run_id": self.run_id,
            "observed_at": _utc_marker(self.observed_at),
            "stages": {
                "collection": {
                    "exit_code": self.collection_exit_code,
                    "status": "exit_zero" if self.collection_exit_code == 0 else "exit_nonzero",
                },
                "prospective_spy_cycle": {
                    "exit_code": self.prospective_spy_cycle_exit_code,
                    "status": self.prospective_spy_cycle_status,
                    "cycle_id": self.prospective_spy_cycle_id,
                    "canary_run_id": self.prospective_spy_canary_run_id,
                    "collector_process_separate": True,
                },
                "prospective_loop": {
                    "exit_code": self.prospective_loop_exit_code,
                    "status": self.prospective_loop_status,
                },
                "prospective_session": {
                    "exit_code": self.prospective_session_exit_code,
                    "status": self.prospective_session_status,
                    "session_id": self.prospective_session_id,
                },
                "prospective_validation": {
                    "exit_code": self.prospective_validation_exit_code,
                    "status": self.prospective_validation_status,
                    "session_id": self.prospective_validation_session_id,
                },
                "observation": {
                    "exit_code": self.observation_exit_code,
                    "status": self.observation_status,
                    "required_for_qqq_cycle": False,
                    "data_only_pair_observation": True,
                },
                "profiled_mtf_forward_capture": {
                    "exit_code": self.capture_cycle_exit_code,
                    "status": self.capture_cycle_status,
                    "data_only": True,
                },
            },
            "terminal": {
                "status": self.terminal_status,
                "recovery_class": self.recovery_class,
                "scheduler_exit_code": self.scheduler_exit_code,
            },
            "artifact_policy": {
                **_SCHEDULE_RECEIPT_ARTIFACT_POLICY,
            },
            "claim": _SCHEDULE_RECEIPT_CLAIM,
        }


class KisPaperIntradayHeadScheduleReceiptError(ValueError):
    """A schedule receipt or its current runtime pointer is unsafe or malformed."""


@dataclass(frozen=True)
class KisPaperIntradayHeadScheduleFact:
    """One offline projection from the task-owned current terminal schedule receipt."""

    run_id: str
    observed_at: datetime
    terminal_status: Literal["complete", "recovery"]
    recovery_class: str
    scheduler_exit_code: int
    receipt_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schedule_run_id(self.run_id, "run id")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.terminal_status not in {"complete", "recovery"}:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_terminal_status_invalid")
        _require_exit_codes(self.scheduler_exit_code)
        _require_sha256(self.receipt_sha256, "receipt sha256")

    def safe_payload(self) -> dict[str, object]:
        """Expose only terminal scheduling categories, never external evidence paths."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_intraday_head_schedule_fact",
            "run_id": self.run_id,
            "observed_at": _utc_marker(self.observed_at),
            "status": self.terminal_status,
            "recovery_class": self.recovery_class,
            "scheduler_exit_code": self.scheduler_exit_code,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True)
class _ScheduleRuntimePointer:
    run_id: str
    observed_at: datetime
    terminal_status: Literal["complete", "recovery"]
    recovery_class: str
    scheduler_exit_code: int
    receipt_sha256: str


@dataclass(frozen=True)
class _ScheduleReceiptTerminal:
    run_id: str
    observed_at: datetime
    terminal_status: Literal["complete", "recovery"]
    recovery_class: str
    scheduler_exit_code: int


def write_kis_paper_intraday_head_schedule_receipt(
    *,
    run_id: str,
    collection_exit_code: int,
    prospective_spy_cycle_exit_code: int,
    prospective_spy_cycle_status: str,
    prospective_spy_cycle_id: str | None,
    prospective_spy_canary_run_id: str | None,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
    observation_exit_code: int,
    observation_status: str,
    capture_cycle_exit_code: int,
    capture_cycle_status: str,
    artifact_root: Path = DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    observed_at: datetime,
) -> KisPaperIntradayHeadScheduleReceipt:
    """Write a terminal receipt without retaining provider, account, or order data.

    The collection process remains the authority for its own exit code. A
    The newer SPY cycle is a separately dispatched post-collection stage. The
    legacy QQQ branch may remain ``not_applicable`` while the data-only pair
    observation continues to publish its own credential-free fact.
    """

    _validate_schedule_receipt_inputs(
        run_id=run_id,
        collection_exit_code=collection_exit_code,
        prospective_spy_cycle_exit_code=prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=prospective_spy_cycle_status,
        prospective_spy_cycle_id=prospective_spy_cycle_id,
        prospective_spy_canary_run_id=prospective_spy_canary_run_id,
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
        observation_exit_code=observation_exit_code,
        observation_status=observation_status,
        capture_cycle_exit_code=capture_cycle_exit_code,
        capture_cycle_status=capture_cycle_status,
    )

    terminal_status, recovery_class, scheduler_exit_code = _terminal_outcome(
        collection_exit_code=collection_exit_code,
        prospective_spy_cycle_exit_code=prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=prospective_spy_cycle_status,
        prospective_spy_cycle_id=prospective_spy_cycle_id,
        prospective_spy_canary_run_id=prospective_spy_canary_run_id,
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
        observation_exit_code=observation_exit_code,
        observation_status=observation_status,
        capture_cycle_exit_code=capture_cycle_exit_code,
        capture_cycle_status=capture_cycle_status,
    )
    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    result = KisPaperIntradayHeadScheduleReceipt(
        run_id=run_id,
        observed_at=require_utc(observed_at, "observed_at"),
        collection_exit_code=collection_exit_code,
        prospective_spy_cycle_exit_code=prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=prospective_spy_cycle_status,
        prospective_spy_cycle_id=prospective_spy_cycle_id,
        prospective_spy_canary_run_id=prospective_spy_canary_run_id,
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
        observation_exit_code=observation_exit_code,
        observation_status=observation_status,
        capture_cycle_exit_code=capture_cycle_exit_code,
        capture_cycle_status=capture_cycle_status,
        terminal_status=terminal_status,
        recovery_class=recovery_class,
        scheduler_exit_code=scheduler_exit_code,
        evidence_path=(
            root / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY / f"{run_id}.json"
        ),
    )
    _write_json_atomically(result.evidence_path, result.safe_payload())
    _write_schedule_runtime_pointer(
        root=root,
        receipt=result,
    )
    return result


def read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
    artifact_root: Path,
    *,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
) -> KisPaperIntradayHeadScheduleFact:
    """Read the one task-written pointer and its exact immutable terminal receipt.

    This never searches for the newest receipt. The current pointer is written by
    the same single-owner task that wrote the referenced immutable evidence.
    """

    root = _readable_external_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    runtime_path = root / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY / (
        KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    )
    _require_direct_regular_file(
        root=root,
        path=runtime_path,
        error_code="schedule_runtime_invalid",
    )
    _, runtime_payload = _read_json_payload(runtime_path, "schedule_runtime_invalid")
    runtime = _runtime_from_payload(runtime_payload)
    evidence_path = (
        root
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY
        / f"{runtime.run_id}.json"
    )
    _require_direct_regular_file(
        root=root,
        path=evidence_path,
        error_code="schedule_evidence_invalid",
    )
    receipt_bytes, receipt_payload = _read_json_payload(evidence_path, "schedule_evidence_invalid")
    receipt = _receipt_terminal_from_payload(receipt_payload)
    receipt_sha256 = _sha256(receipt_bytes)
    if (
        receipt_sha256 != runtime.receipt_sha256
        or receipt.run_id != runtime.run_id
        or receipt.observed_at != runtime.observed_at
        or receipt.terminal_status != runtime.terminal_status
        or receipt.recovery_class != runtime.recovery_class
        or receipt.scheduler_exit_code != runtime.scheduler_exit_code
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_receipt_mismatch")
    return KisPaperIntradayHeadScheduleFact(
        run_id=runtime.run_id,
        observed_at=runtime.observed_at,
        terminal_status=runtime.terminal_status,
        recovery_class=runtime.recovery_class,
        scheduler_exit_code=runtime.scheduler_exit_code,
        receipt_sha256=receipt_sha256,
    )


def _validate_schedule_receipt_inputs(
    *,
    run_id: str,
    collection_exit_code: int,
    prospective_spy_cycle_exit_code: int,
    prospective_spy_cycle_status: str,
    prospective_spy_cycle_id: str | None,
    prospective_spy_canary_run_id: str | None,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
    observation_exit_code: int,
    observation_status: str,
    capture_cycle_exit_code: int,
    capture_cycle_status: str,
) -> None:
    _require_schedule_run_id(run_id, "run id")
    _require_exit_codes(
        collection_exit_code,
        prospective_spy_cycle_exit_code,
        prospective_loop_exit_code,
        prospective_session_exit_code,
        prospective_validation_exit_code,
        observation_exit_code,
        capture_cycle_exit_code,
    )
    _require_status(prospective_loop_status, _LOOP_STATUSES, "prospective loop")
    _require_status(prospective_session_status, _SESSION_STATUSES, "prospective session")
    _require_status(prospective_validation_status, _VALIDATION_STATUSES, "prospective validation")
    _require_status(prospective_spy_cycle_status, _SPY_CYCLE_STATUSES, "prospective SPY cycle")
    _require_status(observation_status, _OBSERVATION_STATUSES, "observation")
    _require_status(capture_cycle_status, _CAPTURE_CYCLE_STATUSES, "capture cycle")
    _require_optional_safe_id(prospective_session_id, "prospective session id")
    _require_optional_safe_id(prospective_spy_cycle_id, "prospective SPY cycle id")
    _require_optional_safe_id(prospective_spy_canary_run_id, "prospective SPY canary run id")
    _require_optional_safe_id(
        prospective_validation_session_id,
        "prospective validation session id",
    )


def _write_schedule_runtime_pointer(
    *,
    root: Path,
    receipt: KisPaperIntradayHeadScheduleReceipt,
) -> None:
    """Advance the task-owned current pointer only after immutable evidence exists."""

    try:
        receipt_bytes = receipt.evidence_path.read_bytes()
    except OSError as error:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid") from error
    runtime_path = (
        root
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    )
    _replace_json_atomically(
        runtime_path,
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_KIND,
            "run_id": receipt.run_id,
            "observed_at": _utc_marker(receipt.observed_at),
            "status": receipt.terminal_status,
            "recovery_class": receipt.recovery_class,
            "scheduler_exit_code": receipt.scheduler_exit_code,
            "receipt_sha256": _sha256(receipt_bytes),
        },
    )


def _runtime_from_payload(payload: Mapping[str, Any]) -> _ScheduleRuntimePointer:
    if (
        frozenset(payload) != _SCHEDULE_RUNTIME_KEYS
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_KIND
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_invalid")
    run_id = _payload_schedule_run_id(payload.get("run_id"), "runtime run id")
    observed_at = _payload_utc(payload.get("observed_at"), "runtime observed at")
    terminal_status, recovery_class, scheduler_exit_code = _schedule_terminal_values(
        status=payload.get("status"),
        recovery_class=payload.get("recovery_class"),
        scheduler_exit_code=payload.get("scheduler_exit_code"),
        error_code="schedule_runtime_terminal_invalid",
    )
    return _ScheduleRuntimePointer(
        run_id=run_id,
        observed_at=observed_at,
        terminal_status=terminal_status,
        recovery_class=recovery_class,
        scheduler_exit_code=scheduler_exit_code,
        receipt_sha256=_payload_sha256(payload.get("receipt_sha256"), "runtime receipt sha256"),
    )


def _receipt_terminal_from_payload(payload: Mapping[str, Any]) -> _ScheduleReceiptTerminal:
    if (
        frozenset(payload) != _SCHEDULE_RECEIPT_KEYS
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_KIND
        or payload.get("artifact_policy") != _SCHEDULE_RECEIPT_ARTIFACT_POLICY
        or payload.get("claim") != _SCHEDULE_RECEIPT_CLAIM
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    terminal = payload.get("terminal")
    if not isinstance(terminal, Mapping) or frozenset(terminal) != _SCHEDULE_RECEIPT_TERMINAL_KEYS:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    terminal_status, recovery_class, scheduler_exit_code = _schedule_terminal_values(
        status=terminal.get("status"),
        recovery_class=terminal.get("recovery_class"),
        scheduler_exit_code=terminal.get("scheduler_exit_code"),
        error_code="schedule_evidence_invalid",
    )
    if payload.get("status") != terminal_status:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    return _ScheduleReceiptTerminal(
        run_id=_payload_schedule_run_id(payload.get("run_id"), "receipt run id"),
        observed_at=_payload_utc(payload.get("observed_at"), "receipt observed at"),
        terminal_status=terminal_status,
        recovery_class=recovery_class,
        scheduler_exit_code=scheduler_exit_code,
    )


def _schedule_terminal_values(
    *,
    status: object,
    recovery_class: object,
    scheduler_exit_code: object,
    error_code: str,
) -> tuple[Literal["complete", "recovery"], str, int]:
    terminal_status = _payload_text(status, "terminal status")
    parsed_recovery_class = _payload_safe_id(recovery_class, "terminal recovery class")
    parsed_exit_code = _payload_exit_code(scheduler_exit_code, "terminal scheduler exit code")
    if terminal_status == "complete":
        if parsed_recovery_class != "complete" or parsed_exit_code != 0:
            raise KisPaperIntradayHeadScheduleReceiptError(error_code)
        return "complete", parsed_recovery_class, parsed_exit_code
    if terminal_status == "recovery":
        if parsed_exit_code == 0:
            raise KisPaperIntradayHeadScheduleReceiptError(error_code)
        return "recovery", parsed_recovery_class, parsed_exit_code
    raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _payload_exit_code(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise KisPaperIntradayHeadScheduleReceiptError(f"schedule_{field_name}_invalid")
    return value


def _payload_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KisPaperIntradayHeadScheduleReceiptError(f"schedule_{field_name}_invalid")
    return value


def _payload_safe_id(value: object, field_name: str) -> str:
    text = _payload_text(value, field_name)
    try:
        _require_safe_id(text, field_name)
    except ValueError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error
    return text


def _payload_schedule_run_id(value: object, field_name: str) -> str:
    text = _payload_text(value, field_name)
    try:
        _require_schedule_run_id(text, field_name)
    except ValueError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error
    return text


def _payload_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise KisPaperIntradayHeadScheduleReceiptError(f"schedule_{field_name}_invalid")
    try:
        return _parse_utc(value)
    except argparse.ArgumentTypeError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error


def _payload_sha256(value: object, field_name: str) -> str:
    text = _payload_text(value, field_name)
    try:
        _require_sha256(text, field_name)
    except ValueError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error
    return text


def _terminal_outcome(
    *,
    collection_exit_code: int,
    prospective_spy_cycle_exit_code: int,
    prospective_spy_cycle_status: str,
    prospective_spy_cycle_id: str | None,
    prospective_spy_canary_run_id: str | None,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
    observation_exit_code: int,
    observation_status: str,
    capture_cycle_exit_code: int,
    capture_cycle_status: str,
) -> tuple[str, str, int]:
    if collection_exit_code != 0:
        return "recovery", "collection_exit_nonzero", collection_exit_code

    spy_cycle_recovery = _prospective_spy_cycle_recovery_class(
        prospective_spy_cycle_exit_code=prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=prospective_spy_cycle_status,
        prospective_spy_cycle_id=prospective_spy_cycle_id,
        prospective_spy_canary_run_id=prospective_spy_canary_run_id,
    )
    if spy_cycle_recovery is not None:
        return "recovery", spy_cycle_recovery, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE

    recovery_class = _first_downstream_recovery_class(
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
    )
    if recovery_class is None:
        if prospective_loop_status == "not_applicable":
            observation_recovery = _data_only_observation_recovery_class(
                observation_exit_code=observation_exit_code,
                observation_status=observation_status,
            )
            if observation_recovery is not None:
                return "recovery", observation_recovery, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE
            capture_recovery = _data_only_capture_cycle_recovery_class(
                capture_cycle_exit_code=capture_cycle_exit_code,
                capture_cycle_status=capture_cycle_status,
            )
            if capture_recovery is not None:
                return "recovery", capture_recovery, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE
        return "complete", "complete", 0
    return "recovery", recovery_class, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


def _prospective_spy_cycle_recovery_class(
    *,
    prospective_spy_cycle_exit_code: int,
    prospective_spy_cycle_status: str,
    prospective_spy_cycle_id: str | None,
    prospective_spy_canary_run_id: str | None,
) -> str | None:
    if prospective_spy_cycle_exit_code != 0:
        return "prospective_spy_cycle_exit_nonzero"
    if prospective_spy_cycle_status == "not_applicable":
        return None
    if prospective_spy_cycle_status not in {"preview", "no_intent", "canary_completed"}:
        return "prospective_spy_cycle_payload_unavailable"
    if prospective_spy_cycle_id is None:
        return "prospective_spy_cycle_id_unavailable"
    if (
        prospective_spy_cycle_status == "canary_completed"
        and prospective_spy_canary_run_id is None
    ):
        return "prospective_spy_canary_run_id_unavailable"
    return None


def _first_downstream_recovery_class(
    *,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
) -> str | None:
    if prospective_loop_exit_code != 0:
        return "prospective_loop_exit_nonzero"
    if prospective_loop_status == "not_applicable":
        if (
            prospective_session_exit_code == 0
            and prospective_session_status == "not_applicable"
            and prospective_session_id is None
            and prospective_validation_exit_code == 0
            and prospective_validation_status == "not_applicable"
            and prospective_validation_session_id is None
        ):
            return None
        return "not_applicable_execution_branch_invalid"
    if prospective_loop_status not in {"embedded", "preview", "no_intent"}:
        return "prospective_loop_payload_unavailable"
    if prospective_session_exit_code != 0:
        return "prospective_session_exit_nonzero"
    if prospective_session_status not in {"no_intent", "canary_completed"}:
        return "prospective_session_payload_unavailable"
    if prospective_session_id is None:
        return "prospective_session_id_unavailable"
    if prospective_validation_exit_code != 0:
        return "prospective_validation_exit_nonzero"
    if prospective_validation_status != "validated":
        return "prospective_validation_payload_unavailable"
    if prospective_validation_session_id != prospective_session_id:
        return "prospective_validation_session_mismatch"
    return None


def _data_only_observation_recovery_class(
    *,
    observation_exit_code: int,
    observation_status: str,
) -> str | None:
    """Require the current data-only branch to expose its own terminal fact."""

    if observation_exit_code != 0:
        return "observation_exit_nonzero"
    if observation_status not in {
        "pending",
        "observed",
        "not_observed",
        "duplicate",
        "conflict",
        "cap_reached",
    }:
        return "observation_payload_unavailable"
    return None


def _data_only_capture_cycle_recovery_class(
    *,
    capture_cycle_exit_code: int,
    capture_cycle_status: str,
) -> str | None:
    """Require the post-collection local forward capture to expose one fact."""

    if capture_cycle_exit_code != 0:
        return "capture_cycle_exit_nonzero"
    if capture_cycle_status not in {
        "outside_cycle_slot",
        "observed",
        "duplicate",
        "conflict",
        "input_unavailable",
        "outcome_unavailable",
        "input_mutated",
        "appended",
    }:
        return "capture_cycle_payload_unavailable"
    return None


def _readable_external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    requested_root = Path(artifact_root)
    _require_non_link(requested_root, "schedule_runtime_invalid")
    root = requested_root.resolve()
    repository = Path(repository_root).resolve()
    mounted_artifact_root = root == repository / "model_artifacts" and root.is_mount()
    if (root.is_relative_to(repository) and not mounted_artifact_root) or root.is_symlink():
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_invalid")
    if not root.is_dir():
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_invalid")
    return root


def _require_direct_regular_file(*, root: Path, path: Path, error_code: str) -> None:
    execution_root = root / "execution"
    schedule_root = execution_root / "kis-paper-intraday-head-schedule"
    for candidate in (root, execution_root, schedule_root, path):
        _require_non_link(candidate, error_code)
    if not root.is_dir() or not execution_root.is_dir() or not schedule_root.is_dir():
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    if not path.is_file():
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    try:
        is_regular_file = stat.S_ISREG(path.stat().st_mode)
    except OSError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    if not is_regular_file:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _require_non_link(path: Path, error_code: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    is_reparse_point = bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _read_json_payload(path: Path, error_code: str) -> tuple[bytes, Mapping[str, Any]]:
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    if not isinstance(payload, Mapping):
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    return encoded, payload


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    root = Path(artifact_root).resolve()
    repository = Path(repository_root).resolve()
    mounted_artifact_root = root == repository / "model_artifacts" and root.is_mount()
    if (root.is_relative_to(repository) and not mounted_artifact_root) or root.is_symlink():
        raise ValueError("schedule receipt root must stay outside Git")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_json_atomically(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="ascii") != rendered:
            raise ValueError("schedule receipt evidence identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    try:
        if path.exists():
            if path.read_text(encoding="ascii") != rendered:
                raise ValueError("schedule receipt evidence identity conflicts")
            return
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _replace_json_atomically(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically refresh the one task-owned current runtime pointer."""

    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _require_exit_codes(*values: int) -> None:
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("schedule stage exit codes must be non-negative integers")


def _require_safe_id(value: str, name: str) -> None:
    if value in {".", ".."} or _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")


def _require_schedule_run_id(value: str, name: str) -> None:
    _require_safe_id(value, name)
    if value.casefold() == KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME.removesuffix(
        ".json"
    ).casefold():
        raise ValueError(f"{name} is reserved")


def _require_optional_safe_id(value: str | None, name: str) -> None:
    if value is not None:
        _require_safe_id(value, name)


def _require_status(value: str, allowed: frozenset[str], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{name} status is invalid")


def _require_sha256(value: str, name: str) -> None:
    if (
        not value.startswith("sha256:")
        or len(value) != len("sha256:") + 64
        or any(character not in "0123456789abcdef" for character in value.removeprefix("sha256:"))
    ):
        raise ValueError(f"{name} is invalid")


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "observed_at").isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("observed_at must be a UTC timestamp") from error
    if parsed.tzinfo is not UTC:
        raise argparse.ArgumentTypeError("observed_at must be a UTC timestamp")
    return require_utc(parsed, "observed_at")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write source-safe terminal evidence for one intraday-head dispatch"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--collection-exit-code", type=int, required=True)
    parser.add_argument("--prospective-spy-cycle-exit-code", type=int, required=True)
    parser.add_argument("--prospective-spy-cycle-status", required=True)
    parser.add_argument("--prospective-spy-cycle-id")
    parser.add_argument("--prospective-spy-canary-run-id")
    parser.add_argument("--prospective-loop-exit-code", type=int, required=True)
    parser.add_argument("--prospective-loop-status", required=True)
    parser.add_argument("--prospective-session-exit-code", type=int, required=True)
    parser.add_argument("--prospective-session-status", required=True)
    parser.add_argument("--prospective-session-id")
    parser.add_argument("--prospective-validation-exit-code", type=int, required=True)
    parser.add_argument("--prospective-validation-status", required=True)
    parser.add_argument("--prospective-validation-session-id")
    parser.add_argument("--observation-exit-code", type=int, required=True)
    parser.add_argument("--observation-status", required=True)
    parser.add_argument("--capture-cycle-exit-code", type=int, required=True)
    parser.add_argument("--capture-cycle-status", required=True)
    parser.add_argument("--observed-at", type=_parse_utc, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = write_kis_paper_intraday_head_schedule_receipt(
        run_id=args.run_id,
        collection_exit_code=args.collection_exit_code,
        prospective_spy_cycle_exit_code=args.prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=args.prospective_spy_cycle_status,
        prospective_spy_cycle_id=args.prospective_spy_cycle_id,
        prospective_spy_canary_run_id=args.prospective_spy_canary_run_id,
        prospective_loop_exit_code=args.prospective_loop_exit_code,
        prospective_loop_status=args.prospective_loop_status,
        prospective_session_exit_code=args.prospective_session_exit_code,
        prospective_session_status=args.prospective_session_status,
        prospective_session_id=args.prospective_session_id,
        prospective_validation_exit_code=args.prospective_validation_exit_code,
        prospective_validation_status=args.prospective_validation_status,
        prospective_validation_session_id=args.prospective_validation_session_id,
        observation_exit_code=args.observation_exit_code,
        observation_status=args.observation_status,
        capture_cycle_exit_code=args.capture_cycle_exit_code,
        capture_cycle_status=args.capture_cycle_status,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        observed_at=args.observed_at,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()
