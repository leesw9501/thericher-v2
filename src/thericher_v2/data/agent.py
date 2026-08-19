"""Single-shot Data Agent queue runner."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

AGENT_NAME = "data_agent"
AGENT_ROOT_NAME = "data-agent"
DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
DEFAULT_INVENTORY_JOB_ID = "data-agent-market-data-inventory"
SUPPORTED_DATA_JOB_KINDS = ("market_data_inventory",)
MAX_SAMPLED_ROWS_PER_FILE = 1000
MAX_RECORDED_SYMBOLS_PER_FILE = 20

RUNNER_COMPLETED = 0
RUNNER_EMPTY_QUEUE = 20
RUNNER_FAILED = 1

DataJobKind = Literal["market_data_inventory"]
DataRunStatus = Literal["completed", "failed", "queue_empty"]

_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DISALLOWED_PATH_MARKERS = (
    ".env",
    "kis",
    "broker",
    "credential",
    "secret",
    "password",
    "api-key",
    "api_key",
    "token",
)


@dataclass(frozen=True)
class DataAgentJobSpec:
    job_id: str
    kind: DataJobKind
    market_data_root: Path
    queued_at: datetime
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _JOB_ID_PATTERN.match(self.job_id):
            raise ValueError("job_id must be path-safe and non-empty")
        if self.kind not in SUPPORTED_DATA_JOB_KINDS:
            raise ValueError(f"unsupported Data Agent job kind: {self.kind}")
        _reject_suspicious_path(self.market_data_root, label="market_data_root")
        object.__setattr__(self, "market_data_root", Path(self.market_data_root))
        object.__setattr__(self, "queued_at", self.queued_at.astimezone(UTC))


@dataclass(frozen=True)
class DataAgentClaim:
    spec: DataAgentJobSpec
    run_dir: Path
    claimed_job_path: Path


@dataclass(frozen=True)
class DataAgentRunResult:
    status: DataRunStatus
    checked_at: datetime
    reason: str
    agent_root: Path
    job_id: str | None = None
    run_dir: Path | None = None
    claimed_job_path: Path | None = None
    recovery_queue_path: Path | None = None
    status_artifact: Path | None = None
    inventory_artifact: Path | None = None
    market_data_root: Path | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


class DataJobIdConflictError(ValueError):
    """Raised when a queued job would collide with prior run state."""

    def __init__(
        self,
        *,
        job_id: str,
        run_dir: Path,
        state: Literal["terminal", "interrupted"],
        recovery_queue_path: Path | None = None,
    ) -> None:
        self.job_id = job_id
        self.run_dir = run_dir
        self.state = state
        self.recovery_queue_path = recovery_queue_path
        if state == "terminal":
            reason = (
                f"data job ID {job_id!r} already has immutable terminal evidence; "
                "leave it unchanged and enqueue recovery under a new job ID"
            )
        else:
            reason = (
                f"data job ID {job_id!r} already has an interrupted claim; "
                "leave it unchanged and enqueue recovery under a new job ID"
            )
        if recovery_queue_path is not None:
            reason += f"; preserved duplicate queue item at {recovery_queue_path}"
        super().__init__(reason)


def resolve_model_artifact_root() -> Path:
    configured = os.environ.get("THERICHER_HOST_MODEL_ARTIFACT_ROOT") or os.environ.get(
        "THERICHER_MODEL_ARTIFACT_ROOT"
    )
    return Path(configured) if configured else DEFAULT_MODEL_ARTIFACT_ROOT


def resolve_data_agent_root(artifact_root: Path | None = None) -> Path:
    root = artifact_root or resolve_model_artifact_root()
    return root / AGENT_ROOT_NAME


def enqueue_data_job(
    *,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
    job_id: str = DEFAULT_INVENTORY_JOB_ID,
    kind: str = "market_data_inventory",
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    queued_at: datetime | None = None,
    reason: str = "bounded market-data inventory",
) -> Path:
    root = artifact_root or resolve_model_artifact_root()
    _validate_roots(
        artifact_root=root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    if kind not in SUPPORTED_DATA_JOB_KINDS:
        raise ValueError(f"unsupported Data Agent job kind: {kind}")
    spec = DataAgentJobSpec(
        job_id=job_id,
        kind=kind,  # type: ignore[arg-type]
        market_data_root=market_data_root,
        queued_at=queued_at or datetime.now(UTC),
        reason=reason,
    )
    return _write_queue_spec(spec, root)


def claim_next_job(agent_root: Path) -> DataAgentClaim | None:
    queue_dir = agent_root / "queue"
    if not queue_dir.exists():
        return None
    for queue_path in sorted(queue_dir.glob("*.json"), key=lambda path: path.name):
        spec = _read_data_job_spec(queue_path)
        run_dir = agent_root / "runs" / spec.job_id
        if _run_dir_has_terminal_evidence(run_dir):
            recovery_queue_path = _preserve_conflicting_queue_item(
                queue_path,
                agent_root=agent_root,
                job_id=spec.job_id,
            )
            raise DataJobIdConflictError(
                job_id=spec.job_id,
                run_dir=run_dir,
                state="terminal",
                recovery_queue_path=recovery_queue_path,
            )
        if _is_bare_interrupted_claim_dir(run_dir):
            run_dir.rmdir()
        elif run_dir.exists() or run_dir.is_symlink():
            recovery_queue_path = _preserve_conflicting_queue_item(
                queue_path,
                agent_root=agent_root,
                job_id=spec.job_id,
            )
            raise DataJobIdConflictError(
                job_id=spec.job_id,
                run_dir=run_dir,
                state="interrupted",
                recovery_queue_path=recovery_queue_path,
            )
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            recovery_queue_path = _preserve_conflicting_queue_item(
                queue_path,
                agent_root=agent_root,
                job_id=spec.job_id,
            )
            raise DataJobIdConflictError(
                job_id=spec.job_id,
                run_dir=run_dir,
                state="interrupted",
                recovery_queue_path=recovery_queue_path,
            ) from exc
        claimed_path = run_dir / "job.json"
        queue_path.replace(claimed_path)
        return DataAgentClaim(spec=spec, run_dir=run_dir, claimed_job_path=claimed_path)
    return None


def run_once(
    *,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
    now: datetime | None = None,
) -> DataAgentRunResult:
    checked_at = now or datetime.now(UTC)
    root = artifact_root or resolve_model_artifact_root()
    agent_root = resolve_data_agent_root(root)
    _reject_repo_artifact_path(root, repo_root)
    try:
        claim = claim_next_job(agent_root)
    except DataJobIdConflictError as exc:
        return DataAgentRunResult(
            status="failed",
            checked_at=checked_at,
            reason=str(exc),
            agent_root=agent_root,
            job_id=exc.job_id,
            run_dir=exc.run_dir,
            recovery_queue_path=exc.recovery_queue_path,
        )
    if claim is None:
        return DataAgentRunResult(
            status="queue_empty",
            checked_at=checked_at,
            reason="no queued Data Agent jobs",
            agent_root=agent_root,
        )
    return _run_claim(
        claim,
        artifact_root=root,
        repo_root=repo_root,
        checked_at=checked_at,
    )


def discover_market_data_inventory(
    market_data_root: Path,
    *,
    max_sampled_rows_per_file: int = MAX_SAMPLED_ROWS_PER_FILE,
) -> dict[str, Any]:
    root = Path(market_data_root)
    notes: list[str] = []
    warnings: list[str] = []
    useful_files: list[dict[str, Any]] = []
    if not root.exists():
        return {
            "root": str(root),
            "root_exists": False,
            "known_folder_count": 0,
            "snapshot_count": 0,
            "useful_file_count": 0,
            "useful_files": [],
            "notes": ["market data root missing"],
            "warnings": ["market data root does not exist"],
        }

    known_roots = (
        (
            "us_equities_yahoo_intraday_1m",
            root / "us_equities" / "yahoo_intraday_starter" / "canonical" / "ohlcv_1m",
            "ohlcv_1m.csv.gz",
            3,
        ),
        (
            "us_equities_yahoo_daily",
            root / "us_equities" / "yahoo_daily_universe" / "canonical" / "ohlcv_daily",
            "ohlcv_daily.csv.gz",
            2,
        ),
    )
    known_folder_count = 0
    snapshot_count = 0
    for dataset_id, dataset_root, expected_name, snapshot_limit in known_roots:
        if not dataset_root.exists():
            continue
        known_folder_count += 1
        notes.append(f"found {dataset_id} root")
        snapshots = sorted(dataset_root.glob("snapshot=*"))[-snapshot_limit:]
        snapshot_count += len(snapshots)
        for snapshot in snapshots:
            csv_path = snapshot / expected_name
            if csv_path.exists():
                useful_files.append(
                    _summarize_market_data_file(
                        csv_path,
                        root=root,
                        dataset_id=dataset_id,
                        max_sampled_rows=max_sampled_rows_per_file,
                    )
                )
            else:
                warnings.append(f"missing expected file: {csv_path}")

    if not notes:
        notes.append("no known useful market-data folders found")
    if not useful_files:
        warnings.append("no known useful market-data files found")
    return {
        "root": str(root),
        "root_exists": True,
        "known_folder_count": known_folder_count,
        "snapshot_count": snapshot_count,
        "useful_file_count": len(useful_files),
        "useful_files": useful_files,
        "notes": notes,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    enqueue = subparsers.add_parser("enqueue-data-job")
    enqueue.add_argument("--job-id", default=DEFAULT_INVENTORY_JOB_ID)
    enqueue.add_argument(
        "--kind",
        default="market_data_inventory",
        choices=SUPPORTED_DATA_JOB_KINDS,
    )
    enqueue.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    enqueue.add_argument("--reason", default="bounded market-data inventory")

    subparsers.add_parser("run-once")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root or resolve_model_artifact_root()
    if args.command == "enqueue-data-job":
        queue_path = enqueue_data_job(
            artifact_root=artifact_root,
            repo_root=args.repo_root,
            job_id=args.job_id,
            kind=args.kind,
            market_data_root=args.market_data_root,
            reason=args.reason,
        )
        print(
            json.dumps(
                {
                    "status": "queued",
                    "agent": AGENT_NAME,
                    "queue_path": str(queue_path),
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(RUNNER_COMPLETED)

    result = run_once(artifact_root=artifact_root, repo_root=args.repo_root)
    print(json.dumps(_data_agent_run_payload(result, artifact_root), indent=2, sort_keys=True))
    raise SystemExit(_exit_code_for(result.status))


def _run_claim(
    claim: DataAgentClaim,
    *,
    artifact_root: Path,
    repo_root: Path | None,
    checked_at: datetime,
) -> DataAgentRunResult:
    started_at = datetime.now(UTC)
    try:
        _validate_roots(
            artifact_root=artifact_root,
            market_data_root=claim.spec.market_data_root,
            repo_root=repo_root,
        )
        inventory_artifact = _write_inventory_artifact(
            spec=claim.spec,
            artifact_root=artifact_root,
        )
        result = DataAgentRunResult(
            status="completed",
            checked_at=checked_at,
            reason="market-data inventory completed",
            agent_root=claim.run_dir.parent.parent,
            job_id=claim.spec.job_id,
            run_dir=claim.run_dir,
            claimed_job_path=claim.claimed_job_path,
            inventory_artifact=inventory_artifact,
            market_data_root=claim.spec.market_data_root,
        )
    except Exception as exc:  # noqa: BLE001 - the agent records bounded job failures.
        result = DataAgentRunResult(
            status="failed",
            checked_at=checked_at,
            reason=f"market-data inventory failed: {exc}",
            agent_root=claim.run_dir.parent.parent,
            job_id=claim.spec.job_id,
            run_dir=claim.run_dir,
            claimed_job_path=claim.claimed_job_path,
            market_data_root=claim.spec.market_data_root,
        )
    status_artifact = _write_run_status(
        result,
        artifact_root=artifact_root,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )
    return DataAgentRunResult(
        status=result.status,
        checked_at=result.checked_at,
        reason=result.reason,
        agent_root=result.agent_root,
        job_id=result.job_id,
        run_dir=result.run_dir,
        claimed_job_path=result.claimed_job_path,
        recovery_queue_path=result.recovery_queue_path,
        status_artifact=status_artifact,
        inventory_artifact=result.inventory_artifact,
        market_data_root=result.market_data_root,
    )


def _write_inventory_artifact(
    *,
    spec: DataAgentJobSpec,
    artifact_root: Path,
) -> Path:
    output_dir = resolve_data_agent_root(artifact_root) / "market-data-inventory" / spec.job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "metrics.json"
    inventory = discover_market_data_inventory(spec.market_data_root)
    payload = _inventory_payload(spec=spec, artifact_root=artifact_root, inventory=inventory)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _summarize_market_data_file(
    path: Path,
    *,
    root: Path,
    dataset_id: str,
    max_sampled_rows: int,
) -> dict[str, Any]:
    sampled_rows = 0
    sampled_symbols: set[str] = set()
    first_timestamp: str | None = None
    last_sample_timestamp: str | None = None
    error: str | None = None
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if sampled_rows >= max_sampled_rows:
                    break
                sampled_rows += 1
                symbol = str(row.get("symbol", "")).upper()
                if symbol:
                    sampled_symbols.add(symbol)
                timestamp = row.get("timestamp_utc") or row.get("date")
                if timestamp:
                    first_timestamp = first_timestamp or str(timestamp)
                    last_sample_timestamp = str(timestamp)
    except (OSError, UnicodeError, csv.Error) as exc:
        error = str(exc)
    relative_path = _relative_text(path, root)
    summary: dict[str, Any] = {
        "dataset_id": dataset_id,
        "path": str(path),
        "relative_path": relative_path,
        "snapshot": path.parent.name,
        "file_name": path.name,
        "size_bytes": path.stat().st_size,
        "sample_scope": {
            "mode": "bounded_head_sample",
            "max_rows": max_sampled_rows,
            "sampled_rows": sampled_rows,
            "symbol_count_is_sampled": True,
        },
        "sampled_symbol_count": len(sampled_symbols),
        "sampled_symbols": sorted(sampled_symbols)[:MAX_RECORDED_SYMBOLS_PER_FILE],
        "first_sample_timestamp": first_timestamp,
        "last_sample_timestamp": last_sample_timestamp,
    }
    if error is not None:
        summary["sample_error"] = error
    return summary


def _inventory_payload(
    *,
    spec: DataAgentJobSpec,
    artifact_root: Path,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": spec.schema_version,
            "agent": AGENT_NAME,
            "status": "market_data_inventory_recorded",
            "job_id": spec.job_id,
            "kind": spec.kind,
            "checked_at": datetime.now(UTC),
            "reason": "bounded market-data inventory completed",
            "inventory": inventory,
            "result_scope": {
                "mode": "data_collection_inventory_only",
                "descriptive_only": True,
                "blocks_research": False,
                "promotion_gate": False,
            },
            "artifact_policy": {
                "host_model_artifact_root": str(artifact_root),
                "agent_root": str(resolve_data_agent_root(artifact_root)),
                "artifact_owner": AGENT_NAME,
                "repo_storage_allowed": False,
            },
            "boundaries": {
                "kis_api": False,
                "broker_submit": False,
                "credential_read": False,
                "env_file_read": False,
                "network": False,
                "public_dashboard": False,
                "writes_market_data": False,
                "docker_required": False,
                "gpu_required": False,
            },
        }
    )


def _write_queue_spec(spec: DataAgentJobSpec, artifact_root: Path) -> Path:
    agent_root = resolve_data_agent_root(artifact_root)
    run_dir = agent_root / "runs" / spec.job_id
    if _run_dir_has_terminal_evidence(run_dir):
        raise DataJobIdConflictError(
            job_id=spec.job_id,
            run_dir=run_dir,
            state="terminal",
        )
    if (run_dir.exists() or run_dir.is_symlink()) and not _is_bare_interrupted_claim_dir(run_dir):
        raise DataJobIdConflictError(
            job_id=spec.job_id,
            run_dir=run_dir,
            state="interrupted",
        )
    queue_dir = agent_root / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    queue_path = queue_dir / f"{spec.job_id}.json"
    if queue_path.exists():
        return queue_path
    temp_path = queue_path.with_name(f".{queue_path.name}.tmp")
    temp_path.write_text(
        json.dumps(_data_agent_job_payload(spec, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(queue_path)
    return queue_path


def _run_dir_has_terminal_evidence(run_dir: Path) -> bool:
    status_path = run_dir / "status.json"
    return status_path.exists() or status_path.is_symlink()


def _is_bare_interrupted_claim_dir(run_dir: Path) -> bool:
    return run_dir.is_dir() and not run_dir.is_symlink() and not any(run_dir.iterdir())


def _preserve_conflicting_queue_item(
    queue_path: Path,
    *,
    agent_root: Path,
    job_id: str,
) -> Path:
    queued_bytes = queue_path.read_bytes()
    digest = hashlib.sha256(queued_bytes).hexdigest()
    recovery_path = agent_root / "recovery" / "job-id-conflict" / f"{job_id}.{digest}.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    if recovery_path.exists() or recovery_path.is_symlink():
        if recovery_path.is_symlink() or recovery_path.read_bytes() != queued_bytes:
            raise ValueError("Data Agent job-ID recovery evidence conflicts")
    else:
        try:
            with recovery_path.open("xb") as stream:
                stream.write(queued_bytes)
        except FileExistsError:
            if recovery_path.is_symlink() or recovery_path.read_bytes() != queued_bytes:
                raise ValueError("Data Agent job-ID recovery evidence conflicts") from None
    queue_path.unlink()
    return recovery_path


def _read_data_job_spec(path: Path) -> DataAgentJobSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DataAgentJobSpec(
        job_id=str(payload["job_id"]),
        kind=payload["kind"],
        market_data_root=Path(str(payload["market_data_root"])),
        queued_at=datetime.fromisoformat(str(payload["queued_at"])),
        reason=str(payload.get("reason", "")),
        schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
    )


def _data_agent_job_payload(spec: DataAgentJobSpec, artifact_root: Path) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": spec.schema_version,
            "agent": AGENT_NAME,
            "status": "queued",
            "job_id": spec.job_id,
            "kind": spec.kind,
            "queued_at": spec.queued_at,
            "reason": spec.reason,
            "market_data_root": str(spec.market_data_root),
            "execution": {
                "mode": "single_data_agent_job",
                "one_job_per_invocation": True,
                "docker_required": False,
                "gpu_required": False,
            },
            "artifact_policy": {
                "host_model_artifact_root": str(artifact_root),
                "agent_root": str(resolve_data_agent_root(artifact_root)),
                "artifact_owner": AGENT_NAME,
                "repo_storage_allowed": False,
            },
            "boundaries": {
                "kis_api": False,
                "broker_submit": False,
                "credential_read": False,
                "env_file_read": False,
                "network": False,
                "public_dashboard": False,
                "writes_market_data": False,
            },
        }
    )


def _write_run_status(
    result: DataAgentRunResult,
    *,
    artifact_root: Path,
    started_at: datetime,
    completed_at: datetime,
) -> Path:
    if result.run_dir is None:
        raise ValueError("run_dir is required to write run status")
    path = result.run_dir / "status.json"
    result_with_path = DataAgentRunResult(
        status=result.status,
        checked_at=result.checked_at,
        reason=result.reason,
        agent_root=result.agent_root,
        job_id=result.job_id,
        run_dir=result.run_dir,
        claimed_job_path=result.claimed_job_path,
        recovery_queue_path=result.recovery_queue_path,
        status_artifact=path,
        inventory_artifact=result.inventory_artifact,
        market_data_root=result.market_data_root,
    )
    payload = _data_agent_run_payload(
        result_with_path,
        artifact_root,
        started_at=started_at,
        completed_at=completed_at,
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    last_run = result.agent_root / "last-run.json"
    last_run.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _data_agent_run_payload(
    result: DataAgentRunResult,
    artifact_root: Path,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "agent": AGENT_NAME,
            "status": result.status,
            "checked_at": result.checked_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "reason": result.reason,
            "job_id": result.job_id,
            "agent_root": str(result.agent_root),
            "run_dir": None if result.run_dir is None else str(result.run_dir),
            "claimed_job_path": (
                None if result.claimed_job_path is None else str(result.claimed_job_path)
            ),
            "recovery_queue_path": (
                None if result.recovery_queue_path is None else str(result.recovery_queue_path)
            ),
            "status_artifact": (
                None if result.status_artifact is None else str(result.status_artifact)
            ),
            "inventory_artifact": (
                None if result.inventory_artifact is None else str(result.inventory_artifact)
            ),
            "market_data_root": None
            if result.market_data_root is None
            else str(result.market_data_root),
            "artifact_policy": {
                "host_model_artifact_root": str(artifact_root),
                "agent_root": str(resolve_data_agent_root(artifact_root)),
                "artifact_owner": AGENT_NAME,
                "repo_storage_allowed": False,
            },
            "execution": {
                "one_job_per_invocation": True,
                "docker_required": False,
                "gpu_required": False,
            },
            "boundaries": {
                "kis_api": False,
                "broker_submit": False,
                "credential_read": False,
                "env_file_read": False,
                "network": False,
                "public_dashboard": False,
                "writes_market_data": False,
            },
        }
    )


def _validate_roots(
    *,
    artifact_root: Path,
    market_data_root: Path,
    repo_root: Path | None,
) -> None:
    _reject_repo_artifact_path(artifact_root, repo_root)
    _reject_repo_market_data_path(market_data_root, repo_root)
    _reject_suspicious_path(market_data_root, label="market_data_root")
    _reject_artifact_inside_market_data(artifact_root, market_data_root)


def _reject_repo_artifact_path(artifact_root: Path, repo_root: Path | None) -> None:
    if repo_root is None:
        return
    resolved_artifact = artifact_root.resolve()
    resolved_repo = repo_root.resolve()
    if resolved_artifact == resolved_repo or resolved_repo in resolved_artifact.parents:
        raise ValueError("artifact_root must be outside the Git workspace")


def _reject_repo_market_data_path(market_data_root: Path, repo_root: Path | None) -> None:
    if repo_root is None:
        return
    resolved_market_data = market_data_root.resolve()
    resolved_repo = repo_root.resolve()
    if resolved_market_data == resolved_repo or resolved_repo in resolved_market_data.parents:
        raise ValueError("market_data_root must be outside the Git workspace")


def _reject_artifact_inside_market_data(artifact_root: Path, market_data_root: Path) -> None:
    resolved_artifact = artifact_root.resolve()
    resolved_market_data = market_data_root.resolve()
    if (
        resolved_artifact == resolved_market_data
        or resolved_market_data in resolved_artifact.parents
    ):
        raise ValueError("artifact_root must not be inside the market data root")


def _reject_suspicious_path(path: Path, *, label: str) -> None:
    lowered = str(path).lower()
    if any(marker in lowered for marker in _DISALLOWED_PATH_MARKERS):
        raise ValueError(f"{label} must not contain credential, KIS, or broker terms")


def _relative_text(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _exit_code_for(status: DataRunStatus) -> int:
    if status == "completed":
        return RUNNER_COMPLETED
    if status == "queue_empty":
        return RUNNER_EMPTY_QUEUE
    return RUNNER_FAILED


if __name__ == "__main__":
    main()
