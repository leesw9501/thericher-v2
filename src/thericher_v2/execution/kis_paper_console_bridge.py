"""Single-run KIS virtual-paper reader that publishes a sanitized local snapshot."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_readonly import (
    DEFAULT_KIS_PAPER_ARTIFACT_ROOT,
    KIS_PAPER_READ_ONLY_ENDPOINTS,
    KisHttpTransport,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    KisPaperReadOnlySnapshot,
    UrllibKisHttpTransport,
    load_kis_paper_config_from_environment,
)
from thericher_v2.execution.paper_account_snapshot import (
    PAPER_ACCOUNT_SNAPSHOT_TTL,
    PaperAccountOpenOrder,
    PaperAccountOrderableForeignFunds,
    PaperAccountPosition,
    PaperAccountReferenceOrderability,
    PaperAccountSnapshot,
    paper_account_snapshot_digest,
    read_paper_account_snapshot,
    write_paper_account_snapshot,
)

DEFAULT_RUNTIME_SNAPSHOT_PATH = Path("runtime/state/paper_account_snapshot.json")


@dataclass(frozen=True)
class KisPaperConsoleBridgeOutcome:
    status: Literal["complete", "unavailable"]
    reason_code: str | None
    observed_at: datetime
    snapshot_path: Path
    evidence_path: Path
    diagnostic: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.status == "complete" and self.reason_code is not None:
            raise ValueError("complete bridge outcome cannot have a reason")
        if self.status == "unavailable" and self.reason_code is None:
            raise ValueError("unavailable bridge outcome requires a reason")
        if self.status == "complete" and self.diagnostic:
            raise ValueError("complete bridge outcome cannot have a diagnostic")
        if self.diagnostic:
            _validate_failure_diagnostic(self.diagnostic)
        object.__setattr__(self, "diagnostic", dict(self.diagnostic))


def run_kis_paper_console_bridge(
    *,
    environment: Mapping[str, str],
    runtime_snapshot_path: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> KisPaperConsoleBridgeOutcome:
    """Publish unavailable before reading, then replace it only with a complete view."""

    started_at = require_utc(clock(), "clock")
    write_paper_account_snapshot(
        PaperAccountSnapshot.unavailable(
            observed_at=started_at,
            reason_code="refresh_in_progress",
        ),
        runtime_snapshot_path,
    )
    diagnostic: Mapping[str, str] = {}
    try:
        config = load_kis_paper_config_from_environment(environment)
        source_snapshot = KisPaperReadOnlyClient(
            config=config,
            transport=transport or UrllibKisHttpTransport(),
        ).snapshot()
        final_snapshot = paper_account_snapshot_from_kis_readonly(
            source_snapshot,
            observed_at=require_utc(clock(), "clock"),
        )
    except KisPaperReadOnlyError as error:
        diagnostic = error.diagnostic
        final_snapshot = PaperAccountSnapshot.unavailable(
            observed_at=require_utc(clock(), "clock"),
            reason_code=error.code,
        )
    except Exception:
        final_snapshot = PaperAccountSnapshot.unavailable(
            observed_at=require_utc(clock(), "clock"),
            reason_code="unexpected_failure",
        )

    snapshot_digest = write_paper_account_snapshot(final_snapshot, runtime_snapshot_path)
    evidence_path = write_kis_paper_console_bridge_evidence(
        final_snapshot,
        snapshot_digest=snapshot_digest,
        artifact_root=artifact_root,
        repository_root=repository_root,
        diagnostic=diagnostic,
    )
    return KisPaperConsoleBridgeOutcome(
        status=final_snapshot.status,
        reason_code=final_snapshot.reason_code,
        observed_at=final_snapshot.observed_at,
        snapshot_path=runtime_snapshot_path,
        evidence_path=evidence_path,
        diagnostic=diagnostic,
    )


def write_kis_paper_console_bridge_evidence(
    snapshot: PaperAccountSnapshot,
    *,
    snapshot_digest: str,
    artifact_root: Path,
    repository_root: Path,
    diagnostic: Mapping[str, str] | None = None,
) -> Path:
    """Persist an immutable fact-minimized result outside the repository."""

    resolved_root = artifact_root.resolve()
    resolved_repository = repository_root.resolve()
    if not _is_permitted_artifact_root(resolved_root, resolved_repository):
        raise ValueError("artifact_root_inside_repository")
    destination = (
        resolved_root
        / "execution"
        / "kis-paper-console-bridge"
        / f"{snapshot.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{snapshot.status}.json"
    )
    if destination.exists():
        raise ValueError("evidence_already_exists")
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_console_bridge",
        "status": snapshot.status,
        "observed_at": snapshot.observed_at.isoformat(),
        "expires_at": snapshot.expires_at.isoformat(),
        "paper_only": True,
        "submit_capability": False,
        "runtime_snapshot_sha256": snapshot_digest,
    }
    if snapshot.status == "unavailable":
        payload["reason_code"] = snapshot.reason_code
        if diagnostic:
            _validate_failure_diagnostic(diagnostic)
            payload["diagnostic"] = dict(diagnostic)
    elif diagnostic:
        raise ValueError("complete bridge evidence cannot have a diagnostic")
    else:
        assert snapshot.orderable_foreign_funds is not None
        assert snapshot.reference_orderability is not None
        payload["facts"] = {
            "orderable_foreign_funds_currency": snapshot.orderable_foreign_funds.currency,
            "reference_orderability_currency": snapshot.reference_orderability.currency,
            "position_count": len(snapshot.positions),
            "open_order_count": len(snapshot.open_orders),
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def recover_kis_paper_console_bridge_evidence(
    *,
    runtime_snapshot_path: Path,
    artifact_root: Path,
    repository_root: Path,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> KisPaperConsoleBridgeOutcome:
    """Record a missing artifact from a fresh sanitized runtime snapshot without KIS I/O."""

    current = read_paper_account_snapshot(
        runtime_snapshot_path,
        now=require_utc(clock(), "clock"),
    )
    if current.status != "available" or current.snapshot is None:
        raise ValueError("snapshot_not_recoverable")
    snapshot = current.snapshot
    evidence_path = write_kis_paper_console_bridge_evidence(
        snapshot,
        snapshot_digest=paper_account_snapshot_digest(snapshot),
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    return KisPaperConsoleBridgeOutcome(
        status="complete",
        reason_code=None,
        observed_at=snapshot.observed_at,
        snapshot_path=runtime_snapshot_path,
        evidence_path=evidence_path,
    )


def paper_account_snapshot_from_kis_readonly(
    source: KisPaperReadOnlySnapshot,
    *,
    observed_at: datetime,
) -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        status="complete",
        observed_at=observed_at,
        expires_at=observed_at + PAPER_ACCOUNT_SNAPSHOT_TTL,
        orderable_foreign_funds=PaperAccountOrderableForeignFunds(
            currency=source.cash.currency,
            amount=source.cash.available_cash,
        ),
        reference_orderability=PaperAccountReferenceOrderability(
            currency=source.orderable_funds.currency,
            orderable_funds=source.orderable_funds.orderable_funds,
            reference_exchange=source.orderable_funds.reference_exchange,
            reference_symbol=source.orderable_funds.reference_symbol,
            reference_price=source.orderable_funds.reference_price,
        ),
        positions=tuple(
            PaperAccountPosition(
                exchange=position.exchange,
                symbol=position.symbol,
                currency=position.currency,
                quantity=position.quantity,
            )
            for position in source.positions
        ),
        open_orders=tuple(
            PaperAccountOpenOrder(
                exchange=order.exchange,
                symbol=order.symbol,
                currency=order.currency,
                side=order.side,
                requested_quantity=order.requested_quantity,
                filled_quantity=order.filled_quantity,
                remaining_quantity=order.remaining_quantity,
                limit_price=order.limit_price,
            )
            for order in source.open_orders.orders
        ),
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_permitted_artifact_root(artifact_root: Path, repository_root: Path) -> bool:
    if not _is_within(artifact_root, repository_root):
        return True
    return artifact_root == repository_root / "model_artifacts" and artifact_root.is_mount()


def _validate_failure_diagnostic(diagnostic: Mapping[str, str]) -> None:
    """Allow request identity only; broker message bodies remain private."""

    required = {"endpoint", "tr_id", "http_status"}
    if set(diagnostic) != required or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in diagnostic.items()
    ):
        raise ValueError("bridge diagnostic is invalid")
    endpoint_by_name = {endpoint.name: endpoint.tr_id for endpoint in KIS_PAPER_READ_ONLY_ENDPOINTS}
    if endpoint_by_name.get(diagnostic["endpoint"]) != diagnostic["tr_id"]:
        raise ValueError("bridge diagnostic is invalid")
    status = diagnostic["http_status"]
    if not status.isdecimal() or not 100 <= int(status) <= 599:
        raise ValueError("bridge diagnostic is invalid")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish one KIS paper console snapshot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--recover-evidence", action="store_true")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(
            os.environ.get("THERICHER_MODEL_ARTIFACT_ROOT", DEFAULT_KIS_PAPER_ARTIFACT_ROOT)
        ),
    )
    parser.add_argument(
        "--runtime-snapshot",
        type=Path,
        default=Path(
            os.environ.get(
                "THERICHER_PAPER_ACCOUNT_SNAPSHOT_PATH",
                DEFAULT_RUNTIME_SNAPSHOT_PATH,
            )
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.recover_evidence:
        outcome = recover_kis_paper_console_bridge_evidence(
            runtime_snapshot_path=arguments.runtime_snapshot,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
        )
    elif not arguments.execute:
        print(json.dumps({"status": "dry_run", "submit_capability": False}, sort_keys=True))
        return 0
    else:
        outcome = run_kis_paper_console_bridge(
            environment=os.environ,
            runtime_snapshot_path=arguments.runtime_snapshot,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
        )
    print(
        json.dumps(
            {
                "status": outcome.status,
                "reason_code": outcome.reason_code,
                "observed_at": outcome.observed_at.isoformat(),
                "evidence_path": str(outcome.evidence_path),
                "scope": "read_only",
                "account_snapshot_complete": outcome.status == "complete",
            },
            sort_keys=True,
        )
    )
    return 0 if outcome.status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
