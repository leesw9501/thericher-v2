"""Read-only structural probe for one persisted KIS Paper order history record.

The probe is intentionally narrower than reconciliation: it reads one existing
private canary state, compares its broker order ID only in memory, and writes a
categorical field-contract observation outside Git. It cannot submit, modify,
cancel, or infer a terminal lifecycle or realized PnL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_paper_canary import (
    KisPaperCanaryError,
    KisPaperCanaryState,
)
from .kis_readonly import (
    DEFAULT_KIS_PAPER_ARTIFACT_ROOT,
    KisHttpTransport,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    KisPaperTerminalFieldObservation,
    UrllibKisHttpTransport,
    load_kis_paper_config_from_environment,
)

DEFAULT_KIS_PAPER_TERMINAL_FIELD_PROBE_STATE_ROOT = Path("/app/private/canary")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,159}", re.ASCII)
_LEGACY_CANARY_RUN_ID = re.compile(r"canary-(\d{8}T\d{12}Z)", re.ASCII)
_EASTERN = ZoneInfo("America/New_York")
_LEGACY_RUN_TIMESTAMP_SKEW = timedelta(minutes=1)
_LEGACY_VALIDITY_MAXIMUM = timedelta(minutes=5)


class KisPaperTerminalFieldProbeError(RuntimeError):
    """A safe failure for the read-only terminal field probe."""


@dataclass(frozen=True)
class KisPaperTerminalFieldProbeOutcome:
    """Sanitized outcome for one pre-existing virtual Paper state."""

    run_ref: str
    state_phase: str | None
    observed_at: datetime
    status: Literal["observed", "not_observed", "unavailable"]
    reason_code: str
    field_observation: KisPaperTerminalFieldObservation | None = None
    order_date_anchor: Literal[
        "acknowledged_submission", "derived_created_at", "not_observed"
    ] = "not_observed"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.run_ref, str) or not self.run_ref.startswith("sha256:"):
            raise ValueError("terminal field probe run reference is invalid")
        if self.status == "observed" and self.field_observation is None:
            raise ValueError("observed terminal field probe requires field observation")
        if self.status != "observed" and self.field_observation is not None:
            raise ValueError("unobserved terminal field probe cannot retain field observation")
        if self.order_date_anchor not in {
            "acknowledged_submission",
            "derived_created_at",
            "not_observed",
        }:
            raise ValueError("terminal field probe order date anchor is invalid")
        if self.field_observation is not None and self.order_date_anchor == "not_observed":
            raise ValueError("observed terminal field probe needs a date anchor")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": "kis_paper_terminal_field_probe",
            "run_ref": self.run_ref,
            "state_phase": self.state_phase,
            "observed_at": self.observed_at.isoformat(),
            "status": self.status,
            "reason_code": self.reason_code,
            "paper_only": True,
            "submit_capability": False,
            "order_date_scope": {
                "acknowledged_submission": "acknowledged_submission_et_day",
                "derived_created_at": "derived_created_at_et_day",
                "not_observed": "not_observed",
            }[self.order_date_anchor],
            "terminal_state_support": "unqualified",
            "pnl_status": "not_observed",
        }
        if self.field_observation is not None:
            payload["field_observation"] = self.field_observation.safe_payload()
        return payload


@dataclass(frozen=True)
class KisPaperTerminalFieldProbeResult:
    outcome: KisPaperTerminalFieldProbeOutcome
    evidence_path: Path


def probe_kis_paper_terminal_fields(
    *,
    run_id: str,
    environment: Mapping[str, str],
    state_root: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    transport: KisHttpTransport | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> KisPaperTerminalFieldProbeResult:
    """Inspect one persisted SPY/AMEX Paper intent without an order side effect."""

    _validate_run_id(run_id)
    observed_at = _probe_now(now=now, clock=clock)
    run_ref = _run_ref(run_id)
    try:
        state = _read_private_state(Path(state_root) / f"{run_id}.json")
    except KisPaperCanaryError:
        outcome = KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=None,
            observed_at=observed_at,
            status="unavailable",
            reason_code="state_invalid",
        )
    else:
        outcome = _probe_state(
            requested_run_id=run_id,
            run_ref=run_ref,
            state=state,
            environment=environment,
            execute=execute,
            transport=transport,
            observed_at=observed_at,
        )
    evidence_path = _write_probe_evidence(
        outcome,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    return KisPaperTerminalFieldProbeResult(outcome=outcome, evidence_path=evidence_path)


def _read_private_state(state_path: Path) -> KisPaperCanaryState | None:
    """Read an atomically replaced canary state without creating a lock file.

    The terminal probe mounts the private state volume read-only. Canary writes
    replace complete JSON files atomically, so a direct parse preserves that
    snapshot guarantee without widening this observer into a state mutator.
    """

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return KisPaperCanaryState.from_dict(payload)
    except FileNotFoundError:
        return None
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise KisPaperCanaryError("state_invalid") from error


def _probe_state(
    *,
    requested_run_id: str,
    run_ref: str,
    state: KisPaperCanaryState | None,
    environment: Mapping[str, str],
    execute: bool,
    transport: KisHttpTransport | None,
    observed_at: datetime,
) -> KisPaperTerminalFieldProbeOutcome:
    if state is None:
        return KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=None,
            observed_at=observed_at,
            status="not_observed",
            reason_code="state_missing",
        )
    if state.intent.run_id != requested_run_id:
        return KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=None,
            observed_at=observed_at,
            status="unavailable",
            reason_code="state_run_mismatch",
        )
    identity_kind = _state_identity_kind(state, requested_run_id=requested_run_id)
    if identity_kind is None:
        return KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=None,
            observed_at=observed_at,
            status="unavailable",
            reason_code="state_receipt_identity_mismatch",
        )
    # This endpoint contract is intentionally scoped to the current SPY/AMEX Paper lane.
    if state.intent.symbol != "SPY" or state.intent.exchange != "AMEX":
        return KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=state.phase,
            observed_at=observed_at,
            status="not_observed",
            reason_code="scope_not_supported",
        )
    if state.phase in {"intent_recorded", "rejected"}:
        return KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=state.phase,
            observed_at=observed_at,
            status="not_observed",
            reason_code=(
                "intent_not_submitted" if state.phase == "intent_recorded" else "provider_rejected"
            ),
        )
    if state.broker_order_id is None:
        return KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=state.phase,
            observed_at=observed_at,
            status="not_observed",
            reason_code="broker_order_id_missing",
        )
    order_at = state.submitted_at
    order_date_anchor: Literal[
        "acknowledged_submission", "derived_created_at", "not_observed"
    ] = "acknowledged_submission"
    if order_at is None:
        if identity_kind != "legacy":
            return KisPaperTerminalFieldProbeOutcome(
                run_ref=run_ref,
                state_phase=state.phase,
                observed_at=observed_at,
                status="not_observed",
                reason_code="submission_time_missing",
            )
        order_at = _legacy_created_at_date_anchor(state, requested_run_id=requested_run_id)
        if order_at is None:
            return KisPaperTerminalFieldProbeOutcome(
                run_ref=run_ref,
                state_phase=state.phase,
                observed_at=observed_at,
                status="not_observed",
                reason_code="legacy_order_date_unqualified",
            )
        order_date_anchor = "derived_created_at"
    if not execute:
        return KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=state.phase,
            observed_at=observed_at,
            status="not_observed",
            reason_code="preview",
            order_date_anchor=order_date_anchor,
        )
    try:
        client = KisPaperReadOnlyClient(
            config=load_kis_paper_config_from_environment(environment),
            transport=transport or UrllibKisHttpTransport(),
        )
        field_observation = client.inspect_order_history_terminal_fields(
            state.broker_order_id,
            order_at=order_at,
        )
    except KisPaperReadOnlyError:
        return KisPaperTerminalFieldProbeOutcome(
            run_ref=run_ref,
            state_phase=state.phase,
            observed_at=observed_at,
            status="unavailable",
            reason_code="read_only_unavailable",
            order_date_anchor=order_date_anchor,
        )
    return KisPaperTerminalFieldProbeOutcome(
        run_ref=run_ref,
        state_phase=state.phase,
        observed_at=observed_at,
        status="observed",
        reason_code=(
            "history_observed_derived_date"
            if order_date_anchor == "derived_created_at"
            else "history_observed"
        ),
        field_observation=field_observation,
        order_date_anchor=order_date_anchor,
    )


def _state_identity_kind(
    state: KisPaperCanaryState,
    *,
    requested_run_id: str,
) -> Literal["current", "legacy"] | None:
    """Accept only the two deterministic state identity schemes this lane created."""

    if state.intent.client_order_id != f"canary-{requested_run_id}":
        return None
    if state.intent.decision_id == requested_run_id:
        return "current"
    if state.intent.decision_id == f"decision-{requested_run_id}":
        return "legacy"
    return None


def _legacy_created_at_date_anchor(
    state: KisPaperCanaryState,
    *,
    requested_run_id: str,
) -> datetime | None:
    """Return a legacy history date anchor only when its full ET interval is proven."""

    match = _LEGACY_CANARY_RUN_ID.fullmatch(requested_run_id)
    if match is None:
        return None
    try:
        run_timestamp = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S%fZ").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None
    created_at = state.intent.created_at
    valid_until = state.intent.valid_until
    if abs(created_at - run_timestamp) > _LEGACY_RUN_TIMESTAMP_SKEW:
        return None
    validity = valid_until - created_at
    if not timedelta(0) < validity <= _LEGACY_VALIDITY_MAXIMUM:
        return None
    if len(
        {
            run_timestamp.astimezone(_EASTERN).date(),
            created_at.astimezone(_EASTERN).date(),
            valid_until.astimezone(_EASTERN).date(),
        }
    ) != 1:
        return None
    return created_at


def _write_probe_evidence(
    outcome: KisPaperTerminalFieldProbeOutcome,
    *,
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    root = Path(artifact_root).resolve()
    repository = _source_repository_root(Path(repository_root))
    if not _is_permitted_artifact_root(root, repository):
        raise KisPaperTerminalFieldProbeError("artifact root must stay outside Git")
    encoded = (json.dumps(outcome.safe_payload(), ensure_ascii=True, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    run_digest = outcome.run_ref.removeprefix("sha256:")[:16]
    destination = (
        root
        / "execution"
        / "kis-paper-terminal-field-probe"
        / f"run-{run_digest}"
        / f"{outcome.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
    )
    if not _is_permitted_artifact_destination(destination, root, repository):
        raise KisPaperTerminalFieldProbeError("probe destination must stay outside Git")
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise KisPaperTerminalFieldProbeError("probe evidence conflicts")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not _is_permitted_artifact_destination(destination, root, repository):
        raise KisPaperTerminalFieldProbeError("probe destination must stay outside Git")
    staging = destination.with_name(f".{digest}.{uuid.uuid4().hex[:8]}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise KisPaperTerminalFieldProbeError("run id is invalid")


def _run_ref(run_id: str) -> str:
    return "sha256:" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()


def _probe_now(
    *,
    now: datetime | None,
    clock: Callable[[], datetime] | None,
) -> datetime:
    source = now if now is not None else (clock() if clock is not None else datetime.now(UTC))
    return require_utc(source, "now")


def _is_permitted_artifact_root(artifact_root: Path, repository_root: Path) -> bool:
    if not artifact_root.is_relative_to(repository_root):
        return True
    return artifact_root == repository_root / "model_artifacts" and artifact_root.is_mount()


def _source_repository_root(fallback_repository_root: Path) -> Path:
    source_root = Path(__file__).resolve().parents[3]
    if (source_root / "pyproject.toml").is_file():
        return source_root
    return fallback_repository_root.resolve()


def _is_permitted_artifact_destination(
    destination: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    resolved_destination = destination.resolve()
    try:
        resolved_destination.relative_to(artifact_root)
    except ValueError:
        return False
    if not resolved_destination.is_relative_to(repository_root):
        return True
    return artifact_root == repository_root / "model_artifacts" and artifact_root.is_mount()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe one KIS Paper terminal field contract")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_TERMINAL_FIELD_PROBE_STATE_ROOT,
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_KIS_PAPER_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = probe_kis_paper_terminal_fields(
        run_id=arguments.run_id,
        environment=os.environ,
        state_root=arguments.state_root,
        artifact_root=arguments.artifact_root,
        repository_root=arguments.repository_root,
        execute=arguments.execute,
    )
    print(json.dumps({**result.outcome.safe_payload(), "evidence_path": str(result.evidence_path)}))
    return 2 if result.outcome.status == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
