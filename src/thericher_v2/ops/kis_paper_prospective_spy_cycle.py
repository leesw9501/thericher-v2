"""Bounded Data-to-Paper cycle for the frozen prospective SPY baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_prospective_spy_capture import (
    capture_kis_paper_prospective_spy_observation,
)
from thericher_v2.execution.kis_paper_prospective_spy_session import (
    run_kis_paper_prospective_spy_session,
)
from thericher_v2.execution.kis_paper_receipt_canary import receipt_canary_run_id

KIS_PAPER_PROSPECTIVE_SPY_CYCLE_KIND = "kis_paper_prospective_spy_cycle"
KIS_PAPER_PROSPECTIVE_SPY_CYCLE_ARTIFACT_DIRECTORY = "ops/kis-paper-prospective-spy-cycle"
_EASTERN = ZoneInfo("America/New_York")
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if _DEFAULT_REPOSITORY_ROOT == Path("/app"):
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_CACHE_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/intraday-head"
    )
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_ARTIFACT_ROOT = Path("/app/model_artifacts")
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_STATE_ROOT = Path("/app/private/canary")
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_RUNTIME_PROJECTION = Path(
        "/app/runtime/state/kis_paper_prospective_spy_canary.json"
    )
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_ACCOUNT_SNAPSHOT = Path(
        "/app/runtime/state/paper_account_snapshot.json"
    )
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_EMERGENCY_STATE = Path(
        "/app/emergency/emergency_state.json"
    )
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_EXECUTION_CONTROL = Path(
        "/app/emergency/paper_execution_control.json"
    )
else:
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_CACHE_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\intraday-head"
    )
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_STATE_ROOT = Path(r"D:\thericher-v2\paper-canary-private")
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_RUNTIME_PROJECTION = Path(
        r"D:\thericher-v2\runtime\kis_paper_prospective_spy_canary.json"
    )
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_ACCOUNT_SNAPSHOT = Path(
        r"D:\thericher-v2\runtime\paper_account_snapshot.json"
    )
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_EMERGENCY_STATE = Path(
        r"D:\thericher-v2\emergency\emergency_state.json"
    )
    DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_EXECUTION_CONTROL = Path(
        r"D:\thericher-v2\emergency\paper_execution_control.json"
    )

CycleStatus = Literal["preview", "no_intent", "canary_completed"]


@dataclass(frozen=True, slots=True)
class KisPaperProspectiveSpyCycleOutcome:
    """One source-safe attempt using a single immutable observation receipt."""

    cycle_id: str
    observed_at: datetime
    session_date: date
    status: CycleStatus
    reason_code: str
    capture_status: str
    capture_reason_code: str | None
    execution_session_id: str | None
    execution_status: str | None
    execution_reason_code: str | None
    receipt_ref: str | None
    canary_run_id: str | None
    evidence_path: Path
    schema_version: int = SCHEMA_VERSION

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_PROSPECTIVE_SPY_CYCLE_KIND,
            "cycle_id": self.cycle_id,
            "observed_at": _utc_marker(self.observed_at),
            "session_date": self.session_date.isoformat(),
            "status": self.status,
            "reason_code": self.reason_code,
            "paper_only": True,
            "capture": {
                "status": self.capture_status,
                "reason_code": self.capture_reason_code,
            },
            "execution": {
                "attempted": self.execution_status is not None,
                "session_id": self.execution_session_id,
                "status": self.execution_status,
                "reason_code": self.execution_reason_code,
                "receipt_ref": self.receipt_ref,
                "canary_run_id": self.canary_run_id,
                "single_flight": "receipt_canary_state_lock",
            },
        }


def run_kis_paper_prospective_spy_cycle(
    *,
    environment: Mapping[str, str],
    observed_at: datetime,
    cache_root: Path = DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_CACHE_ROOT,
    artifact_root: Path = DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_ARTIFACT_ROOT,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    state_root: Path = DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_STATE_ROOT,
    runtime_projection_path: Path = DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_RUNTIME_PROJECTION,
    paper_account_snapshot_path: Path = DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_ACCOUNT_SNAPSHOT,
    emergency_state_path: Path = DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_EMERGENCY_STATE,
    execution_control_path: Path = DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_EXECUTION_CONTROL,
    execute: bool,
    cancel_after_submit: bool,
    cycle_id: str | None = None,
) -> KisPaperProspectiveSpyCycleOutcome:
    """Capture current completed bars, then delegate one eligible receipt to Paper.

    The collector is deliberately outside this function.  A scheduler invokes
    this only after its independent intraday-head collection has terminated.
    Receipt content supplies the durable canary identity and the existing
    canary lock serializes overlapping attempts across processes.
    """

    observed = require_utc(observed_at, "observed_at")
    resolved_cycle_id = cycle_id or _cycle_id(observed)
    _require_safe_id(resolved_cycle_id, "cycle id")
    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    session_date = observed.astimezone(_EASTERN).date()
    captured = capture_kis_paper_prospective_spy_observation(
        cache_root=cache_root,
        artifact_root=root,
        repo_root=repository_root,
        session_date=session_date,
        observed_at=observed,
    )
    if captured.status != "captured" or captured.receipt is None:
        return _record(
            cycle_id=resolved_cycle_id,
            observed_at=observed,
            session_date=session_date,
            status="no_intent" if execute else "preview",
            reason_code=captured.reason or "capture_not_ready",
            capture_status=captured.status,
            capture_reason_code=captured.reason,
            artifact_root=root,
        )

    receipt_ref = _receipt_ref(captured.receipt.canonical_json())
    canary_run_id = receipt_canary_run_id(receipt_ref)
    execution_session_id = f"{resolved_cycle_id}-execution"
    session = run_kis_paper_prospective_spy_session(
        environment=environment,
        artifact_root=root,
        repository_root=repository_root,
        state_root=state_root,
        runtime_projection_path=runtime_projection_path,
        paper_account_snapshot_path=paper_account_snapshot_path,
        emergency_state_path=emergency_state_path,
        execution_control_path=execution_control_path,
        execute=execute,
        cancel_after_submit=cancel_after_submit,
        now=observed,
        session_id=execution_session_id,
    )
    return _record(
        cycle_id=resolved_cycle_id,
        observed_at=observed,
        session_date=session_date,
        status=session.status,
        reason_code=session.reason_code,
        capture_status=captured.status,
        capture_reason_code=captured.reason,
        execution_session_id=session.session_id,
        execution_status=session.status,
        execution_reason_code=session.reason_code,
        receipt_ref=receipt_ref,
        canary_run_id=canary_run_id,
        artifact_root=root,
    )


def _record(
    *,
    cycle_id: str,
    observed_at: datetime,
    session_date: date,
    status: CycleStatus,
    reason_code: str,
    capture_status: str,
    capture_reason_code: str | None,
    artifact_root: Path,
    execution_session_id: str | None = None,
    execution_status: str | None = None,
    execution_reason_code: str | None = None,
    receipt_ref: str | None = None,
    canary_run_id: str | None = None,
) -> KisPaperProspectiveSpyCycleOutcome:
    evidence_path = _evidence_path(artifact_root=artifact_root, cycle_id=cycle_id)
    outcome = KisPaperProspectiveSpyCycleOutcome(
        cycle_id=cycle_id,
        observed_at=observed_at,
        session_date=session_date,
        status=status,
        reason_code=reason_code,
        capture_status=capture_status,
        capture_reason_code=capture_reason_code,
        execution_session_id=execution_session_id,
        execution_status=execution_status,
        execution_reason_code=execution_reason_code,
        receipt_ref=receipt_ref,
        canary_run_id=canary_run_id,
        evidence_path=evidence_path,
    )
    _write_or_verify(evidence_path, outcome.safe_payload(), artifact_root=artifact_root)
    return outcome


def _cycle_id(observed_at: datetime) -> str:
    return f"prospective-spy-cycle-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}"


def _receipt_ref(canonical_receipt: str) -> str:
    return "sha256:" + hashlib.sha256(canonical_receipt.encode("utf-8")).hexdigest()


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    root = Path(artifact_root).resolve(strict=False)
    repository = Path(repository_root).resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    mounted_artifacts = repository == docker_repository and root.is_relative_to(docker_artifacts)
    if root.is_relative_to(repository) and not mounted_artifacts:
        raise ValueError("prospective SPY cycle artifact root must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("prospective SPY cycle artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=False)


def _evidence_path(*, artifact_root: Path, cycle_id: str) -> Path:
    directory = artifact_root / KIS_PAPER_PROSPECTIVE_SPY_CYCLE_ARTIFACT_DIRECTORY / cycle_id
    _ensure_real_descendant(root=artifact_root, directory=directory)
    path = directory / "evidence.json"
    if path.exists() and path.is_symlink():
        raise ValueError("prospective SPY cycle evidence path is invalid")
    if not path.resolve(strict=False).is_relative_to(artifact_root):
        raise ValueError("prospective SPY cycle evidence path is invalid")
    return path


def _ensure_real_descendant(*, root: Path, directory: Path) -> None:
    try:
        relative_parts = directory.relative_to(root).parts
    except ValueError as error:
        raise ValueError("prospective SPY cycle evidence path is invalid") from error
    cursor = root
    for part in relative_parts:
        cursor = cursor / part
        if cursor.exists():
            if cursor.is_symlink() or not cursor.is_dir():
                raise ValueError("prospective SPY cycle evidence path is invalid")
        else:
            cursor.mkdir()
        if not cursor.resolve(strict=True).is_relative_to(root):
            raise ValueError("prospective SPY cycle evidence path is invalid")


def _write_or_verify(
    path: Path,
    payload: Mapping[str, object],
    *,
    artifact_root: Path,
) -> None:
    _ensure_real_descendant(root=artifact_root, directory=path.parent)
    encoded = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.is_symlink() or path.read_text(encoding="ascii") != encoded:
            raise ValueError("prospective SPY cycle evidence identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(encoded)
        temporary_path = Path(temporary.name)
    try:
        if path.exists():
            if path.read_text(encoding="ascii") != encoded:
                raise ValueError("prospective SPY cycle evidence identity conflicts")
            return
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _require_safe_id(value: str, name: str) -> None:
    if _SAFE_ID.fullmatch(value) is None or value in {".", ".."}:
        raise ValueError(f"prospective SPY {name} is invalid")


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "observed_at").isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("--observed-at must be UTC") from error
    if parsed.tzinfo is not UTC:
        raise argparse.ArgumentTypeError("--observed-at must be UTC")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one prospective SPY Data-to-Paper cycle")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cancel-after-submit", action="store_true")
    parser.add_argument("--observed-at", type=_parse_utc, default=datetime.now(UTC))
    parser.add_argument("--cycle-id")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_CACHE_ROOT,
    )
    parser.add_argument(
        "--artifact-root", type=Path, default=DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_ARTIFACT_ROOT
    )
    parser.add_argument("--repository-root", type=Path, default=_DEFAULT_REPOSITORY_ROOT)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_STATE_ROOT,
    )
    parser.add_argument(
        "--runtime-projection",
        type=Path,
        default=DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_RUNTIME_PROJECTION,
    )
    parser.add_argument(
        "--paper-account-snapshot",
        type=Path,
        default=DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_ACCOUNT_SNAPSHOT,
    )
    parser.add_argument(
        "--emergency-state", type=Path, default=DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_EMERGENCY_STATE
    )
    parser.add_argument(
        "--execution-control",
        type=Path,
        default=DEFAULT_KIS_PAPER_PROSPECTIVE_SPY_EXECUTION_CONTROL,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    outcome = run_kis_paper_prospective_spy_cycle(
        environment=os.environ,
        observed_at=args.observed_at,
        cache_root=args.cache_root,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        state_root=args.state_root,
        runtime_projection_path=args.runtime_projection,
        paper_account_snapshot_path=args.paper_account_snapshot,
        emergency_state_path=args.emergency_state,
        execution_control_path=args.execution_control,
        execute=args.execute,
        cancel_after_submit=args.cancel_after_submit,
        cycle_id=args.cycle_id,
    )
    print(json.dumps(outcome.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()
