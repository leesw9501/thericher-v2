"""Write source-safe start and terminal receipts for one intraday-head invocation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_KIND = "kis_paper_intraday_head_invocation_receipt"
KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY = (
    "execution/kis-paper-intraday-head-invocation-v1"
)
KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_ARTIFACT_NAME = "current.json"
KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_KIND = "kis_paper_intraday_head_invocation_runtime"
DEFAULT_KIS_PAPER_INTRADAY_HEAD_INVOCATION_ARTIFACT_ROOT = Path(
    r"D:\thericher-v2\model-artifacts"
)

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_ARTIFACT_POLICY = {
    "credentials_in_receipt": False,
    "account_data_in_receipt": False,
    "raw_market_data_in_receipt": False,
    "broker_order_data_in_receipt": False,
    "repo_storage_allowed": False,
}
_CLAIM = (
    "scheduler invocation observability only; not proof of Task Scheduler origin, "
    "a provider result, a model result, PnL claim, or broker action"
)
_START_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "phase",
        "run_id",
        "started_at",
        "artifact_policy",
        "claim",
    }
)
_TERMINAL_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "phase",
        "run_id",
        "started_at",
        "schedule_observed_at",
        "completed_at",
        "started_receipt_sha256",
        "collection_outcome",
        "schedule_receipt_outcome",
        "terminal_outcome",
        "artifact_policy",
        "claim",
    }
)
_TERMINAL_KEYS_WITH_COLLECTION_FAILURE_CATEGORY = _TERMINAL_KEYS | frozenset(
    {"collection_failure_category"}
)
_RUNTIME_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "phase",
        "run_id",
        "observed_at",
        "receipt_sha256",
        "artifact_policy",
        "claim",
    }
)
_COLLECTION_FAILURE_CATEGORIES = frozenset(
    {"reason_unavailable", "dispatcher_config", "collector_provider"}
)


@dataclass(frozen=True, slots=True)
class KisPaperIntradayHeadInvocationReceiptResult:
    status: Literal["written", "already_written", "not_written"]
    reason: str | None
    phase: Literal["started", "terminal"]
    receipt_sha256: str | None

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_KIND,
            "phase": self.phase,
            "status": self.status,
            "reason": self.reason,
            "receipt_sha256": self.receipt_sha256,
            "artifact_policy": dict(_ARTIFACT_POLICY),
            "claim": _CLAIM,
        }


@dataclass(frozen=True, slots=True)
class KisPaperIntradayHeadInvocationRuntimeFact:
    """A source-safe pointer to the one latest immutable invocation receipt."""

    phase: Literal["started", "terminal"]
    run_id: str
    observed_at: datetime
    receipt_sha256: str

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_KIND,
            "phase": self.phase,
            "run_id": self.run_id,
            "observed_at": _utc_marker(self.observed_at),
            "receipt_sha256": self.receipt_sha256,
            "artifact_policy": dict(_ARTIFACT_POLICY),
            "claim": _CLAIM,
        }


@dataclass(frozen=True, slots=True)
class KisPaperIntradayHeadInvocationTerminalFact:
    """One validated terminal marker with its exact schedule-observed binding."""

    run_id: str
    started_at: datetime
    schedule_observed_at: datetime
    completed_at: datetime
    receipt_sha256: str
    collection_outcome: Literal["succeeded", "nonzero"]
    schedule_receipt_outcome: Literal["complete", "recovery", "unavailable"]
    terminal_outcome: Literal["succeeded", "nonzero"]
    collection_failure_category: Literal[
        "reason_unavailable", "dispatcher_config", "collector_provider"
    ] = "reason_unavailable"

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "kis_paper_intraday_head_invocation_terminal_fact",
            "run_id": self.run_id,
            "started_at": _utc_marker(self.started_at),
            "schedule_observed_at": _utc_marker(self.schedule_observed_at),
            "completed_at": _utc_marker(self.completed_at),
            "receipt_sha256": self.receipt_sha256,
            "collection_outcome": self.collection_outcome,
            "collection_failure_category": self.collection_failure_category,
            "schedule_receipt_outcome": self.schedule_receipt_outcome,
            "terminal_outcome": self.terminal_outcome,
            "artifact_policy": dict(_ARTIFACT_POLICY),
            "claim": _CLAIM,
        }


def write_started_kis_paper_intraday_head_invocation_receipt(
    *, artifact_root: Path, repository_root: Path, run_id: str, started_at: datetime
) -> KisPaperIntradayHeadInvocationReceiptResult:
    """Write an immutable marker before the dispatcher opens its collector path."""

    root = _external_root(artifact_root=artifact_root, repository_root=repository_root)
    normalized_run_id = _require_run_id(run_id)
    started_at = require_utc(started_at, "started_at")
    encoded = _canonical_json(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_KIND,
            "phase": "started",
            "run_id": normalized_run_id,
            "started_at": _utc_marker(started_at),
            "artifact_policy": dict(_ARTIFACT_POLICY),
            "claim": _CLAIM,
        }
    )
    result = _write_result(
        root=root,
        run_id=normalized_run_id,
        phase="started",
        encoded=encoded,
    )
    if result.receipt_sha256 is not None:
        _write_runtime_pointer(
            root=root,
            phase="started",
            run_id=normalized_run_id,
            observed_at=started_at,
            receipt_sha256=result.receipt_sha256,
        )
    return result


def write_terminal_kis_paper_intraday_head_invocation_receipt(
    *,
    artifact_root: Path,
    repository_root: Path,
    run_id: str,
    started_at: datetime,
    schedule_observed_at: datetime,
    completed_at: datetime,
    collection_exit_code: int,
    schedule_receipt_status: str,
    terminal_exit_code: int,
    collection_failure_category: str = "reason_unavailable",
) -> KisPaperIntradayHeadInvocationReceiptResult:
    """Bind a source-safe terminal category to an existing immutable start marker."""

    root = _external_root(artifact_root=artifact_root, repository_root=repository_root)
    normalized_run_id = _require_run_id(run_id)
    started_at = require_utc(started_at, "started_at")
    schedule_observed_at = require_utc(schedule_observed_at, "schedule_observed_at")
    completed_at = require_utc(completed_at, "completed_at")
    if completed_at < started_at:
        return _not_written("terminal_before_start", phase="terminal")
    if not started_at <= schedule_observed_at <= completed_at:
        return _not_written("schedule_observed_time_invalid", phase="terminal")
    if type(collection_exit_code) is not int or type(terminal_exit_code) is not int:
        return _not_written("exit_code_invalid", phase="terminal")
    if (
        not isinstance(collection_failure_category, str)
        or collection_failure_category not in _COLLECTION_FAILURE_CATEGORIES
    ):
        return _not_written("collection_failure_category_invalid", phase="terminal")
    if collection_exit_code == 0 and collection_failure_category != "reason_unavailable":
        return _not_written("collection_failure_category_invalid", phase="terminal")
    if schedule_receipt_status not in {"complete", "recovery", "unavailable"}:
        return _not_written("schedule_receipt_status_invalid", phase="terminal")
    try:
        started_bytes = _read_exact_start(
            root=root,
            run_id=normalized_run_id,
            started_at=started_at,
        )
    except (FileNotFoundError, ValueError):
        return _not_written("started_receipt_unavailable", phase="terminal")
    encoded = _canonical_json(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_KIND,
            "phase": "terminal",
            "run_id": normalized_run_id,
            "started_at": _utc_marker(started_at),
            "schedule_observed_at": _utc_marker(schedule_observed_at),
            "completed_at": _utc_marker(completed_at),
            "started_receipt_sha256": _sha256(started_bytes),
            "collection_outcome": _exit_outcome(collection_exit_code),
            "collection_failure_category": collection_failure_category,
            "schedule_receipt_outcome": schedule_receipt_status,
            "terminal_outcome": _exit_outcome(terminal_exit_code),
            "artifact_policy": dict(_ARTIFACT_POLICY),
            "claim": _CLAIM,
        }
    )
    result = _write_result(
        root=root,
        run_id=normalized_run_id,
        phase="terminal",
        encoded=encoded,
    )
    if result.receipt_sha256 is not None:
        _write_runtime_pointer(
            root=root,
            phase="terminal",
            run_id=normalized_run_id,
            observed_at=completed_at,
            receipt_sha256=result.receipt_sha256,
        )
    return result


def read_current_kis_paper_intraday_head_invocation_runtime_fact(
    *, artifact_root: Path, repository_root: Path
) -> KisPaperIntradayHeadInvocationRuntimeFact:
    """Validate the mutable pointer against its exact immutable receipt."""

    root = _external_root(artifact_root=artifact_root, repository_root=repository_root)
    runtime_path = root / KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY / (
        KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_ARTIFACT_NAME
    )
    _require_regular_external_file(root=root, path=runtime_path)
    try:
        runtime_bytes = runtime_path.read_bytes()
        runtime_payload = json.loads(runtime_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invocation runtime is invalid") from error
    if not isinstance(runtime_payload, dict) or frozenset(runtime_payload) != _RUNTIME_KEYS:
        raise ValueError("invocation runtime is invalid")
    phase = runtime_payload.get("phase")
    run_id = runtime_payload.get("run_id")
    observed_at = runtime_payload.get("observed_at")
    receipt_sha256 = runtime_payload.get("receipt_sha256")
    if (
        runtime_payload.get("schema_version") != SCHEMA_VERSION
        or runtime_payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_KIND
        or not isinstance(phase, str)
        or phase not in {"started", "terminal"}
        or not isinstance(run_id, str)
        or not isinstance(observed_at, str)
        or not isinstance(receipt_sha256, str)
        or runtime_payload.get("artifact_policy") != _ARTIFACT_POLICY
        or runtime_payload.get("claim") != _CLAIM
        or _canonical_json(runtime_payload) != runtime_bytes
    ):
        raise ValueError("invocation runtime is invalid")
    normalized_run_id = _require_run_id(run_id)
    normalized_observed_at = _utc(observed_at, "runtime observed_at")
    if not _is_sha256(receipt_sha256):
        raise ValueError("invocation runtime is invalid")
    receipt_path = _receipt_path(root=root, run_id=normalized_run_id, phase=phase)
    _require_regular_external_file(root=root, path=receipt_path)
    receipt_bytes = receipt_path.read_bytes()
    if _sha256(receipt_bytes) != receipt_sha256:
        raise ValueError("invocation runtime receipt mismatch")
    if phase == "started":
        _read_exact_start(
            root=root,
            run_id=normalized_run_id,
            started_at=normalized_observed_at,
        )
    else:
        _read_exact_terminal(
            root=root,
            run_id=normalized_run_id,
            observed_at=normalized_observed_at,
        )
    return KisPaperIntradayHeadInvocationRuntimeFact(
        phase=phase,
        run_id=normalized_run_id,
        observed_at=normalized_observed_at,
        receipt_sha256=receipt_sha256,
    )


def read_current_kis_paper_intraday_head_invocation_terminal_fact(
    *, artifact_root: Path, repository_root: Path
) -> KisPaperIntradayHeadInvocationTerminalFact:
    """Read the current terminal marker without exposing an external path."""

    runtime = read_current_kis_paper_intraday_head_invocation_runtime_fact(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    if runtime.phase != "terminal":
        raise ValueError("invocation terminal marker is unavailable")
    root = _external_root(artifact_root=artifact_root, repository_root=repository_root)
    encoded = _read_exact_terminal(
        root=root,
        run_id=runtime.run_id,
        observed_at=runtime.observed_at,
    )
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("terminal receipt is invalid") from error
    if not isinstance(payload, dict):
        raise ValueError("terminal receipt is invalid")
    started_at = _utc_value(payload.get("started_at"), "terminal started_at")
    schedule_observed_at = _utc_value(
        payload.get("schedule_observed_at"), "terminal schedule_observed_at"
    )
    completed_at = _utc_value(payload.get("completed_at"), "terminal completed_at")
    collection_outcome = payload.get("collection_outcome")
    schedule_receipt_outcome = payload.get("schedule_receipt_outcome")
    terminal_outcome = payload.get("terminal_outcome")
    collection_failure_category = _collection_failure_category_from_terminal_payload(payload)
    if (
        collection_outcome not in {"succeeded", "nonzero"}
        or schedule_receipt_outcome not in {"complete", "recovery", "unavailable"}
        or terminal_outcome not in {"succeeded", "nonzero"}
    ):
        raise ValueError("terminal receipt is invalid")
    return KisPaperIntradayHeadInvocationTerminalFact(
        run_id=runtime.run_id,
        started_at=started_at,
        schedule_observed_at=schedule_observed_at,
        completed_at=completed_at,
        receipt_sha256=runtime.receipt_sha256,
        collection_outcome=collection_outcome,
        collection_failure_category=collection_failure_category,
        schedule_receipt_outcome=schedule_receipt_outcome,
        terminal_outcome=terminal_outcome,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("started", "terminal"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--schedule-observed-at")
    parser.add_argument("--completed-at")
    parser.add_argument("--collection-exit-code", type=int)
    parser.add_argument("--collection-failure-category", default="reason_unavailable")
    parser.add_argument("--schedule-receipt-status")
    parser.add_argument("--terminal-exit-code", type=int)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_INTRADAY_HEAD_INVOCATION_ARTIFACT_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args(argv)
    try:
        started_at = _utc(arguments.started_at, "started_at")
        if arguments.phase == "started":
            result = write_started_kis_paper_intraday_head_invocation_receipt(
                artifact_root=arguments.artifact_root,
                repository_root=arguments.repository_root,
                run_id=arguments.run_id,
                started_at=started_at,
            )
        else:
            if (
                arguments.completed_at is None
                or arguments.schedule_observed_at is None
                or arguments.collection_exit_code is None
                or arguments.schedule_receipt_status is None
                or arguments.terminal_exit_code is None
            ):
                parser.error("terminal receipts require completion and outcome arguments")
            result = write_terminal_kis_paper_intraday_head_invocation_receipt(
                artifact_root=arguments.artifact_root,
                repository_root=arguments.repository_root,
                run_id=arguments.run_id,
                started_at=started_at,
                schedule_observed_at=_utc(
                    arguments.schedule_observed_at, "schedule_observed_at"
                ),
                completed_at=_utc(arguments.completed_at, "completed_at"),
                collection_exit_code=arguments.collection_exit_code,
                collection_failure_category=arguments.collection_failure_category,
                schedule_receipt_status=arguments.schedule_receipt_status,
                terminal_exit_code=arguments.terminal_exit_code,
            )
    except (OSError, ValueError):
        result = _not_written("receipt_unavailable", phase=arguments.phase)
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return 0


def _read_exact_start(*, root: Path, run_id: str, started_at: datetime) -> bytes:
    path = _receipt_path(root=root, run_id=run_id, phase="started")
    _require_regular_external_file(root=root, path=path)
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("started receipt is invalid") from error
    if (
        not isinstance(payload, dict)
        or frozenset(payload) != _START_KEYS
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_KIND
        or payload.get("phase") != "started"
        or payload.get("run_id") != run_id
        or payload.get("started_at") != _utc_marker(started_at)
        or payload.get("artifact_policy") != _ARTIFACT_POLICY
        or payload.get("claim") != _CLAIM
    ):
        raise ValueError("started receipt is invalid")
    if _canonical_json(payload) != encoded:
        raise ValueError("started receipt is invalid")
    return encoded


def _read_exact_terminal(*, root: Path, run_id: str, observed_at: datetime) -> bytes:
    path = _receipt_path(root=root, run_id=run_id, phase="terminal")
    _require_regular_external_file(root=root, path=path)
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("terminal receipt is invalid") from error
    if (
        not isinstance(payload, dict)
        or frozenset(payload)
        not in {_TERMINAL_KEYS, _TERMINAL_KEYS_WITH_COLLECTION_FAILURE_CATEGORY}
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_KIND
        or payload.get("phase") != "terminal"
        or payload.get("run_id") != run_id
        or payload.get("completed_at") != _utc_marker(observed_at)
        or not _is_sha256(payload.get("started_receipt_sha256"))
        or payload.get("collection_outcome") not in {"succeeded", "nonzero"}
        or payload.get("schedule_receipt_outcome") not in {"complete", "recovery", "unavailable"}
        or payload.get("terminal_outcome") not in {"succeeded", "nonzero"}
        or payload.get("artifact_policy") != _ARTIFACT_POLICY
        or payload.get("claim") != _CLAIM
        or _canonical_json(payload) != encoded
    ):
        raise ValueError("terminal receipt is invalid")
    started_at = payload.get("started_at")
    schedule_observed_at = payload.get("schedule_observed_at")
    completed_at = payload.get("completed_at")
    if (
        not isinstance(started_at, str)
        or not isinstance(schedule_observed_at, str)
        or not isinstance(completed_at, str)
    ):
        raise ValueError("terminal receipt is invalid")
    normalized_started_at = _utc(started_at, "terminal started_at")
    normalized_schedule_observed_at = _utc(
        schedule_observed_at, "terminal schedule_observed_at"
    )
    normalized_completed_at = _utc(completed_at, "terminal completed_at")
    if not normalized_started_at <= normalized_schedule_observed_at <= normalized_completed_at:
        raise ValueError("terminal receipt is invalid")
    started_bytes = _read_exact_start(
        root=root,
        run_id=run_id,
        started_at=normalized_started_at,
    )
    if payload.get("started_receipt_sha256") != _sha256(started_bytes):
        raise ValueError("terminal receipt is invalid")
    _collection_failure_category_from_terminal_payload(payload)
    return encoded


def _collection_failure_category_from_terminal_payload(
    payload: dict[str, object],
) -> Literal["reason_unavailable", "dispatcher_config", "collector_provider"]:
    value = payload.get("collection_failure_category", "reason_unavailable")
    if value == "reason_unavailable":
        category: Literal["reason_unavailable", "dispatcher_config", "collector_provider"] = value
    elif value == "dispatcher_config":
        category = value
    elif value == "collector_provider":
        category = value
    else:
        raise ValueError("terminal receipt is invalid")
    if payload.get("collection_outcome") == "succeeded" and category != "reason_unavailable":
        raise ValueError("terminal receipt is invalid")
    return category


def _write_result(
    *, root: Path, run_id: str, phase: Literal["started", "terminal"], encoded: bytes
) -> KisPaperIntradayHeadInvocationReceiptResult:
    destination = _receipt_path(root=root, run_id=run_id, phase=phase)
    try:
        created = _write_or_verify(root=root, destination=destination, encoded=encoded)
    except (OSError, ValueError):
        return _not_written("receipt_conflict", phase=phase)
    return KisPaperIntradayHeadInvocationReceiptResult(
        status="written" if created else "already_written",
        reason=None,
        phase=phase,
        receipt_sha256=_sha256(encoded),
    )


def _not_written(
    reason: str, *, phase: Literal["started", "terminal"]
) -> KisPaperIntradayHeadInvocationReceiptResult:
    return KisPaperIntradayHeadInvocationReceiptResult(
        status="not_written", reason=reason, phase=phase, receipt_sha256=None
    )


def _external_root(*, artifact_root: Path, repository_root: Path) -> Path:
    requested = artifact_root.absolute()
    _require_no_link_ancestors(requested)
    root = requested.resolve()
    if not root.is_dir() or root.is_symlink() or root.is_relative_to(repository_root.resolve()):
        raise ValueError("invocation artifact root is invalid")
    return root


def _receipt_path(*, root: Path, run_id: str, phase: Literal["started", "terminal"]) -> Path:
    return root / KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY / run_id / f"{phase}.json"


def _write_or_verify(*, root: Path, destination: Path, encoded: bytes) -> bool:
    _require_no_link_ancestors(destination)
    if not destination.resolve(strict=False).is_relative_to(root):
        raise ValueError("invocation receipt destination is invalid")
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != encoded:
            raise ValueError("invocation receipt conflicts")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_no_link_ancestors(destination.parent)
    staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        if destination.exists():
            if destination.is_symlink() or destination.read_bytes() != encoded:
                raise ValueError("invocation receipt conflicts")
            return False
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return True


def _write_runtime_pointer(
    *,
    root: Path,
    phase: Literal["started", "terminal"],
    run_id: str,
    observed_at: datetime,
    receipt_sha256: str,
) -> None:
    directory = root / KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    _require_no_link_ancestors(directory)
    destination = directory / KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_ARTIFACT_NAME
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_KIND,
        "phase": phase,
        "run_id": run_id,
        "observed_at": _utc_marker(observed_at),
        "receipt_sha256": receipt_sha256,
        "artifact_policy": dict(_ARTIFACT_POLICY),
        "claim": _CLAIM,
    }
    encoded = _canonical_json(payload)
    if destination.exists():
        _require_regular_external_file(root=root, path=destination)
        try:
            current_payload = json.loads(destination.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invocation runtime is invalid") from error
        if not isinstance(current_payload, dict):
            raise ValueError("invocation runtime is invalid")
        current_observed_at = current_payload.get("observed_at")
        current_run_id = current_payload.get("run_id")
        if not isinstance(current_observed_at, str) or not isinstance(current_run_id, str):
            raise ValueError("invocation runtime is invalid")
        current_time = _utc(current_observed_at, "runtime observed_at")
        if current_time > observed_at:
            return
        if current_time == observed_at and current_run_id != run_id:
            raise ValueError("invocation runtime pointer conflicts")
        if destination.read_bytes() == encoded:
            return
    staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)


def _require_regular_external_file(*, root: Path, path: Path) -> None:
    _require_no_link_ancestors(path)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("invocation receipt is invalid")


def _require_no_link_ancestors(path: Path) -> None:
    current = path.absolute()
    while True:
        if current.exists() and current.is_symlink():
            raise ValueError("invocation receipt path is invalid")
        if current.parent == current:
            return
        current = current.parent


def _require_run_id(value: str) -> str:
    if _SAFE_ID.fullmatch(value) is None:
        raise ValueError("invocation run id is invalid")
    return value


def _exit_outcome(value: int) -> Literal["succeeded", "nonzero"]:
    return "succeeded" if value == 0 else "nonzero"


def _utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is invalid") from error
    return require_utc(parsed, label)


def _utc_value(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid")
    return _utc(value, label)


def _utc_marker(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str):
        return False
    prefix, separator, digest = value.partition(":")
    return (
        prefix == "sha256"
        and separator == ":"
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


if __name__ == "__main__":
    raise SystemExit(main())
