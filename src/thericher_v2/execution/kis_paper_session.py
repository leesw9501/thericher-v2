"""A small repeatable regular-session runner for the virtual KIS Paper canary."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session
from thericher_v2.research.kis_paper_canary_intent import KisPaperCanaryBuyDecision

from .emergency import DEFAULT_PAPER_EXECUTION_CONTROL_STATE, PaperExecutionControlStore
from .kis_paper_canary import (
    DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT,
    DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
    DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION,
    DEFAULT_KIS_PAPER_CANARY_STATE_ROOT,
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryOutcome,
    UrllibKisPaperCanaryTransport,
    exclusive_kis_paper_canary_state_lock,
    run_kis_paper_canary,
)
from .kis_paper_quote import (
    DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS,
    KisPaperQuoteError,
    derive_kis_paper_nonmarket_limit,
)
from .kis_readonly import (
    KisHttpTransport,
    KisPaperReadOnlyError,
    load_kis_paper_config_from_environment,
)

DEFAULT_KIS_PAPER_SESSION_VALID_SECONDS = 300
KIS_PAPER_SESSION_EVIDENCE_KIND = "kis_paper_canary_session_evidence"
_SAFE_SESSION_IDS = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SESSION_STATUSES = frozenset(
    {"preview", "not_due", "paused", "quote_unavailable", "canary_completed"}
)
_SESSION_REASONS = frozenset(
    {
        "preview",
        "outside_regular_session",
        "quote_unavailable",
        "quote_rejected",
        "quote_response_incomplete",
        "pause_buys_active",
        "session_unavailable",
    }
)


@dataclass(frozen=True)
class KisPaperCanarySessionOutcome:
    """Credential-free result of one scheduled virtual-paper session attempt."""

    session_id: str
    status: Literal["preview", "not_due", "paused", "quote_unavailable", "canary_completed"]
    reason_code: str
    observed_at: datetime
    evidence_path: Path
    run_id: str | None = None
    canary_phase: str | None = None
    canary_reason_code: str | None = None
    submit_upstream_code: str | None = None
    reconciliation_status: str | None = None
    reconciliation_reason_code: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if _SAFE_SESSION_IDS.fullmatch(self.session_id) is None:
            raise ValueError("session_id is invalid")
        if self.status not in _SESSION_STATUSES:
            raise ValueError("session status is invalid")
        if self.reason_code not in _SESSION_REASONS and self.status != "canary_completed":
            raise ValueError("session reason is invalid")
        if self.run_id is not None and _SAFE_SESSION_IDS.fullmatch(self.run_id) is None:
            raise ValueError("run_id is invalid")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))

    def safe_payload(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "observed_at": self.observed_at.isoformat(),
            "run_id": self.run_id,
            "canary_phase": self.canary_phase,
            "canary_reason_code": self.canary_reason_code,
            "submit_upstream_code": self.submit_upstream_code,
            "reconciliation_status": self.reconciliation_status,
            "reconciliation_reason_code": self.reconciliation_reason_code,
            "paper_only": True,
            "evidence_path": str(self.evidence_path),
        }


def is_us_equity_regular_session_window(now: datetime) -> bool:
    """Return whether ``now`` is inside the explicit supported US core session."""

    return _session_due_reason(now) is None


def _session_due_reason(
    now: datetime,
) -> Literal["outside_regular_session", "session_unavailable"] | None:
    """Classify one UTC timestamp without reaching credentials or a KIS route."""

    observed_at = require_utc(now, "now")
    eastern_date = observed_at.astimezone(US_EQUITY_EASTERN).date()
    try:
        session = us_equity_2026_session(eastern_date)
    except ValueError:
        return "session_unavailable"
    if session is None:
        return "session_unavailable"
    if session.window.open_ts <= observed_at < session.window.close_ts:
        return None
    return "outside_regular_session"


def run_kis_paper_quote_session(
    *,
    environment: Mapping[str, str],
    state_root: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    cancel_after_submit: bool,
    transport: KisHttpTransport | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    session_id: str | None = None,
    valid_seconds: int = DEFAULT_KIS_PAPER_SESSION_VALID_SECONDS,
    execution_control_path: Path = DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
) -> KisPaperCanarySessionOutcome:
    """Run one due virtual session without recording the source quote anywhere."""

    observed_at = _session_now(now=now, clock=clock)
    if valid_seconds <= 0:
        raise ValueError("valid_seconds must be positive")
    resolved_session_id = session_id or f"paper-session-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    if _SAFE_SESSION_IDS.fullmatch(resolved_session_id) is None:
        raise ValueError("session_id is invalid")
    run_id = f"canary-{resolved_session_id.removeprefix('paper-session-')}"
    if _SAFE_SESSION_IDS.fullmatch(run_id) is None:
        raise ValueError("run_id is invalid")

    with exclusive_kis_paper_canary_state_lock(state_root / ".session_execution"):
        if not execute:
            return _record_session_outcome(
                session_id=resolved_session_id,
                status="preview",
                reason_code="preview",
                observed_at=observed_at,
                artifact_root=artifact_root,
                repository_root=repository_root,
            )
        if (session_reason := _session_due_reason(observed_at)) is not None:
            return _record_session_outcome(
                session_id=resolved_session_id,
                status="not_due",
                reason_code=session_reason,
                observed_at=observed_at,
                artifact_root=artifact_root,
                repository_root=repository_root,
            )
        if PaperExecutionControlStore(execution_control_path).read().pause_buys:
            return _record_session_outcome(
                session_id=resolved_session_id,
                status="paused",
                reason_code="pause_buys_active",
                observed_at=observed_at,
                artifact_root=artifact_root,
                repository_root=repository_root,
            )
        try:
            config = load_kis_paper_config_from_environment(environment)
            client = KisPaperCanaryClient(
                config=config,
                transport=transport or UrllibKisPaperCanaryTransport(),
            )
            quote = client.fetch_spy_quote()
            decision_at = _session_now(now=now, clock=clock)
            if (session_reason := _session_due_reason(decision_at)) is not None:
                return _record_session_outcome(
                    session_id=resolved_session_id,
                    status="not_due",
                    reason_code=session_reason,
                    observed_at=decision_at,
                    artifact_root=artifact_root,
                    repository_root=repository_root,
                )
            decision = KisPaperCanaryBuyDecision(
                decision_id=f"decision-{run_id}",
                symbol="SPY",
                exchange="NASD",
                quantity=Decimal("1"),
                limit_price=derive_kis_paper_nonmarket_limit(
                    quote,
                    discount_bps=DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS,
                ),
                decision_as_of=decision_at,
                valid_until=decision_at + timedelta(seconds=valid_seconds),
            )
        except (
            KisPaperCanaryError,
            KisPaperQuoteError,
            KisPaperReadOnlyError,
            ValueError,
        ) as error:
            return _record_session_outcome(
                session_id=resolved_session_id,
                status="quote_unavailable",
                reason_code=_safe_quote_reason(error),
                observed_at=observed_at,
                artifact_root=artifact_root,
                repository_root=repository_root,
            )

        outcome = run_kis_paper_canary(
            decision=decision,
            run_id=run_id,
            environment=environment,
            state_path=state_root / f"{run_id}.json",
            runtime_projection_path=runtime_projection_path,
            paper_account_snapshot_path=paper_account_snapshot_path,
            emergency_state_path=emergency_state_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=True,
            cancel_after_submit=cancel_after_submit,
            transport=transport,
            client=client,
            now=now,
            clock=clock,
            submit_permitted=is_us_equity_regular_session_window,
            execution_control_path=execution_control_path,
        )
        return _record_canary_outcome(
            session_id=resolved_session_id,
            observed_at=decision_at,
            outcome=outcome,
            artifact_root=artifact_root,
            repository_root=repository_root,
        )


def _session_now(
    *,
    now: datetime | None,
    clock: Callable[[], datetime] | None,
) -> datetime:
    if now is not None and clock is not None:
        raise ValueError("now and clock are mutually exclusive")
    source = now if now is not None else (clock() if clock is not None else datetime.now(UTC))
    return require_utc(source, "now")


def _record_canary_outcome(
    *,
    session_id: str,
    observed_at: datetime,
    outcome: KisPaperCanaryOutcome,
    artifact_root: Path,
    repository_root: Path,
) -> KisPaperCanarySessionOutcome:
    return _record_session_outcome(
        session_id=session_id,
        status="canary_completed",
        reason_code=outcome.reason_code,
        observed_at=observed_at,
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id=outcome.run_id,
        canary_phase=outcome.phase,
        canary_reason_code=outcome.reason_code,
        submit_upstream_code=outcome.submit_upstream_code,
        reconciliation_status=outcome.reconciliation.status,
        reconciliation_reason_code=outcome.reconciliation.reason_code,
    )


def _record_session_outcome(
    *,
    session_id: str,
    status: Literal["preview", "not_due", "paused", "quote_unavailable", "canary_completed"],
    reason_code: str,
    observed_at: datetime,
    artifact_root: Path,
    repository_root: Path,
    run_id: str | None = None,
    canary_phase: str | None = None,
    canary_reason_code: str | None = None,
    submit_upstream_code: str | None = None,
    reconciliation_status: str | None = None,
    reconciliation_reason_code: str | None = None,
) -> KisPaperCanarySessionOutcome:
    destination = _session_evidence_path(artifact_root=artifact_root, session_id=session_id)
    outcome = KisPaperCanarySessionOutcome(
        session_id=session_id,
        status=status,
        reason_code=reason_code,
        observed_at=observed_at,
        evidence_path=destination,
        run_id=run_id,
        canary_phase=canary_phase,
        canary_reason_code=canary_reason_code,
        submit_upstream_code=submit_upstream_code,
        reconciliation_status=reconciliation_status,
        reconciliation_reason_code=reconciliation_reason_code,
    )
    _write_session_evidence(outcome, artifact_root=artifact_root, repository_root=repository_root)
    return outcome


def _safe_quote_reason(error: Exception) -> str:
    if isinstance(error, KisPaperCanaryError) and error.code in {
        "quote_rejected",
        "quote_response_incomplete",
    }:
        return error.code
    return "quote_unavailable"


def _session_evidence_path(*, artifact_root: Path, session_id: str) -> Path:
    return artifact_root / "execution" / "kis-paper-canary-session" / session_id / "evidence.json"


def _write_session_evidence(
    outcome: KisPaperCanarySessionOutcome,
    *,
    artifact_root: Path,
    repository_root: Path,
) -> None:
    if not _is_permitted_artifact_root(artifact_root, repository_root):
        raise ValueError("artifact_root must be outside the Git workspace")
    destination = outcome.evidence_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": KIS_PAPER_SESSION_EVIDENCE_KIND,
        "schema_version": SCHEMA_VERSION,
        **outcome.safe_payload(),
    }
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_permitted_artifact_root(artifact_root: Path, repository_root: Path) -> bool:
    resolved_artifact = artifact_root.resolve()
    resolved_repository = repository_root.resolve()
    if not _is_within(resolved_artifact, resolved_repository):
        return True
    return (
        os.name != "nt"
        and resolved_artifact == resolved_repository / "model_artifacts"
        and resolved_artifact.is_mount()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one quote-derived KIS virtual-paper session")
    parser.add_argument("--session-id")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cancel-after-submit", action="store_true")
    parser.add_argument(
        "--valid-seconds",
        type=int,
        default=DEFAULT_KIS_PAPER_SESSION_VALID_SECONDS,
    )
    parser.add_argument("--state-root", type=Path, default=DEFAULT_KIS_PAPER_CANARY_STATE_ROOT)
    parser.add_argument(
        "--runtime-projection",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION,
    )
    parser.add_argument(
        "--paper-account-snapshot",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT,
    )
    parser.add_argument(
        "--emergency-state",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    )
    parser.add_argument(
        "--execution-control",
        type=Path,
        default=DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(
            os.environ.get(
                "THERICHER_MODEL_ARTIFACT_ROOT",
                DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
            )
        ),
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        outcome = run_kis_paper_quote_session(
            environment=os.environ,
            state_root=arguments.state_root,
            runtime_projection_path=arguments.runtime_projection,
            paper_account_snapshot_path=arguments.paper_account_snapshot,
            emergency_state_path=arguments.emergency_state,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
            execute=arguments.execute,
            cancel_after_submit=arguments.cancel_after_submit,
            session_id=arguments.session_id,
            valid_seconds=arguments.valid_seconds,
            execution_control_path=arguments.execution_control,
        )
    except (KisPaperCanaryError, KisPaperReadOnlyError, KisPaperQuoteError, ValueError) as error:
        print(
            json.dumps(
                {"status": "failed", "reason_code": _safe_quote_reason(error), "paper_only": True}
            )
        )
        return 2
    print(json.dumps(outcome.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
