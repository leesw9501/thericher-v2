"""Run a bounded token-reusing fixed-NAS KIS Paper daily-history continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    load_kis_paper_market_data_environment_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_daily_history import (
    KIS_PAPER_DAILY_HISTORY_DEFAULT_MAX_CHUNKS,
    KIS_PAPER_DAILY_HISTORY_DEFAULT_MAX_RUNTIME,
    KisPaperDailyHistoryError,
    KisPaperDailyHistoryRun,
    UrllibKisPaperDailyHistoryTransport,
    run_kis_paper_daily_history_collection,
)

_CANONICAL_CACHE_ROOT = Path("/app/market_data")
_CANONICAL_CONTROL_ROOT = Path("/app/collection_control")
_CANONICAL_ARTIFACT_ROOT = Path("/app/model_artifacts")
_CANONICAL_REPOSITORY_ROOT = Path("/app")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
    code_revision: Callable[[Path], str] | None = None,
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=_CANONICAL_CACHE_ROOT)
    parser.add_argument("--control-root", type=Path, default=_CANONICAL_CONTROL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_CANONICAL_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_CANONICAL_REPOSITORY_ROOT)
    parser.add_argument(
        "--max-chunks", type=int, default=KIS_PAPER_DAILY_HISTORY_DEFAULT_MAX_CHUNKS
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=KIS_PAPER_DAILY_HISTORY_DEFAULT_MAX_RUNTIME.total_seconds(),
    )
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return
    if args.max_chunks <= 0 or args.max_runtime_seconds <= 0:
        parser.error("worker bounds must be positive")

    cache_root = Path(args.cache_root)
    control_root = Path(args.control_root)
    artifact_root = Path(args.artifact_root)
    repository_root = Path(args.repository_root)
    if not _canonical_execution_roots(
        cache_root,
        control_root,
        artifact_root,
        repository_root,
    ):
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": "canonical_container_roots_required",
                }
            )
        )
        return
    if not _distinct_paths(cache_root, control_root, artifact_root):
        print(json.dumps({"status": "not_executed", "reason": "dedicated_storage_required"}))
        return
    request_gate = KisPaperMarketDataRateGate(control_root=control_root)
    token_start_gate = KisPaperMarketDataTokenStartGate(control_root=control_root)
    client: KisPaperMarketDataClient | None = None
    revision = (code_revision or _current_code_revision)(repository_root)

    def client_factory() -> KisPaperMarketDataClient:
        nonlocal client
        if client is None:
            client = KisPaperMarketDataClient(
                config=load_kis_paper_market_data_environment_config(),
                transport=UrllibKisPaperDailyHistoryTransport(
                    request_gate=request_gate,
                    token_start_gate=token_start_gate,
                ),
                max_daily_page_attempts=args.max_chunks * 2,
            )
        return client

    started_at = clock()
    started_monotonic = monotonic_clock()
    remaining_chunks = args.max_chunks
    runs: list[KisPaperDailyHistoryRun] = []
    accepted_page_count = 0
    categorical_failure_count = 0
    chunk_attempt_count = 0
    retry_wait_count = 0
    client_reused_across_internal_cycles = False
    stop_reason = "global_runtime_exhausted"
    execution_unavailable = False

    try:
        while remaining_chunks > 0:
            elapsed_seconds = _elapsed_seconds(started_monotonic, monotonic_clock)
            remaining_runtime_seconds = args.max_runtime_seconds - elapsed_seconds
            if remaining_runtime_seconds <= 0:
                stop_reason = "global_runtime_exhausted"
                break

            collection_kwargs: dict[str, object] = {
                "client_factory": client_factory,
                "request_gate": request_gate,
                "token_start_gate": token_start_gate,
                "cache_root": cache_root,
                "evidence_root": artifact_root,
                "repo_root": repository_root,
                "code_revision": revision,
                "max_chunks": remaining_chunks,
                "max_runtime": timedelta(seconds=remaining_runtime_seconds),
                "clock": clock,
                "monotonic_clock": monotonic_clock,
            }
            client_was_reused_for_cycle = client is not None
            if client_was_reused_for_cycle:
                # The core runner owns request pacing; this preserves its valid in-memory token.
                collection_kwargs["client"] = client
            result = run_kis_paper_daily_history_collection(**collection_kwargs)
            runs.append(result)
            if client_was_reused_for_cycle and result.chunk_attempt_count > 0:
                client_reused_across_internal_cycles = True
            if result.chunk_attempt_count > remaining_chunks:
                raise ValueError("daily history core exceeded the global chunk budget")
            remaining_chunks -= result.chunk_attempt_count
            accepted_page_count += result.accepted_page_count
            categorical_failure_count += result.categorical_failure_count
            chunk_attempt_count += result.chunk_attempt_count

            if result.status == "complete":
                stop_reason = "cache_complete"
                break
            if result.status == "storage_floor_would_be_crossed":
                stop_reason = "storage_floor_would_be_crossed"
                break
            if result.status == "busy":
                stop_reason = "worker_lock_busy"
                break
            if remaining_chunks <= 0:
                stop_reason = "global_chunk_budget_exhausted"
                break

            elapsed_seconds = _elapsed_seconds(started_monotonic, monotonic_clock)
            remaining_runtime_seconds = args.max_runtime_seconds - elapsed_seconds
            if remaining_runtime_seconds <= 0:
                stop_reason = "global_runtime_exhausted"
                break

            next_due = result.next_due
            if next_due is None:
                stop_reason = "no_future_retry_due_observed"
                break
            due_seconds = (next_due - clock()).total_seconds()
            if due_seconds <= 0:
                stop_reason = "retry_due_not_future"
                break
            if due_seconds >= remaining_runtime_seconds:
                stop_reason = "runtime_budget_before_next_due"
                break
            sleeper(due_seconds)
            retry_wait_count += 1
        else:
            stop_reason = "global_chunk_budget_exhausted"
    except (KisPaperDailyHistoryError, KisPaperMarketDataError, OSError, ValueError):
        execution_unavailable = True
        stop_reason = "worker_unavailable"

    completed_at = clock()
    last_run = runs[-1] if runs else None
    summary = _source_safe_continuation_summary(
        started_at=started_at,
        completed_at=completed_at,
        elapsed_seconds=_elapsed_seconds(started_monotonic, monotonic_clock),
        runs=runs,
        max_chunks=args.max_chunks,
        max_total_runtime_seconds=args.max_runtime_seconds,
        accepted_page_count=accepted_page_count,
        categorical_failure_count=categorical_failure_count,
        chunk_attempt_count=chunk_attempt_count,
        retry_wait_count=retry_wait_count,
        client_reused_across_internal_cycles=client_reused_across_internal_cycles,
        stop_reason=stop_reason,
        final_run=last_run,
        recovery="reconcile" if execution_unavailable else None,
    )
    try:
        continuation_summary_sha256 = _write_source_safe_continuation_summary(
            artifact_root=artifact_root,
            repository_root=repository_root,
            summary=summary,
            observed_at=completed_at,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "unavailable", "reason": "continuation_summary_unavailable"}))
        return

    payload = _safe_console_payload(last_run)
    if execution_unavailable:
        payload["status"] = "unavailable"
        payload["reason"] = "daily_history_unavailable"
        payload["recovery"] = "reconcile"
    payload["continuation"] = {
        "internal_cycle_count": len(runs),
        "cumulative_accepted_page_count": accepted_page_count,
        "cumulative_categorical_failure_count": categorical_failure_count,
        "cumulative_chunk_attempt_count": chunk_attempt_count,
        "retry_wait_count": retry_wait_count,
        "client_reused_across_internal_cycles": client_reused_across_internal_cycles,
        "client_reuse_outcome": _client_reuse_outcome(
            client_reused_across_internal_cycles=client_reused_across_internal_cycles,
            stop_reason=stop_reason,
        ),
        "stop_reason": stop_reason,
    }
    payload["continuation_summary_sha256"] = continuation_summary_sha256
    print(json.dumps(payload, sort_keys=True))


def _safe_console_payload(result: KisPaperDailyHistoryRun | None) -> dict[str, object]:
    if result is None:
        return {
            "status": "not_started",
            "reason": "global_runtime_exhausted",
            "accepted_page_count": 0,
            "categorical_failure_count": 0,
            "chunk_attempt_count": 0,
            "measured_accepted_pages_per_minute": None,
            "remaining_page_estimate": None,
            "eta_bucket": "unknown",
            "next_due_utc": None,
            "recovery": "restart",
            "registry_sha256": None,
            "evidence_sha256": None,
            "targets": [],
        }
    return {
        "status": result.status,
        "accepted_page_count": result.accepted_page_count,
        "categorical_failure_count": result.categorical_failure_count,
        "chunk_attempt_count": result.chunk_attempt_count,
        "measured_accepted_pages_per_minute": result.measured_accepted_pages_per_minute,
        "remaining_page_estimate": result.remaining_page_estimate,
        "eta_bucket": result.eta_bucket,
        "next_due_utc": _format_utc(result.next_due),
        "recovery": result.recovery,
        "registry_sha256": result.registry_sha256,
        "evidence_sha256": result.evidence_sha256,
        "targets": [target.source_safe_document() for target in result.target_states],
    }


def _source_safe_continuation_summary(
    *,
    started_at: datetime,
    completed_at: datetime,
    elapsed_seconds: float,
    runs: Sequence[KisPaperDailyHistoryRun],
    max_chunks: int,
    max_total_runtime_seconds: float,
    accepted_page_count: int,
    categorical_failure_count: int,
    chunk_attempt_count: int,
    retry_wait_count: int,
    client_reused_across_internal_cycles: bool,
    stop_reason: str,
    final_run: KisPaperDailyHistoryRun | None,
    recovery: str | None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_paper_daily_nas_history_continuation_summary",
        "scope": {
            "provider": "KIS Open API virtual paper",
            "endpoint": "dailyprice",
            "mode": "off",
            "fixed_registry_only": True,
        },
        "started_at_utc": _format_utc(started_at),
        "completed_at_utc": _format_utc(completed_at),
        "worker_bounds": {
            "max_total_runtime_seconds": max_total_runtime_seconds,
            "max_global_chunks": max_chunks,
            "max_daily_page_attempts": max_chunks * 2,
        },
        "outcome": {
            "internal_cycle_count": len(runs),
            "accepted_page_count": accepted_page_count,
            "categorical_failure_count": categorical_failure_count,
            "chunk_attempt_count": chunk_attempt_count,
            "retry_wait_count": retry_wait_count,
            "elapsed_bucket": _elapsed_bucket(elapsed_seconds),
            "client_reused_across_internal_cycles": client_reused_across_internal_cycles,
            "client_reuse_outcome": _client_reuse_outcome(
                client_reused_across_internal_cycles=client_reused_across_internal_cycles,
                stop_reason=stop_reason,
            ),
            "stop_reason": stop_reason,
            "recovery": recovery or ("restart" if final_run is None else final_run.recovery),
            "next_due_utc": None if final_run is None else _format_utc(final_run.next_due),
        },
        "targets": [] if final_run is None else [
            target.source_safe_document() for target in final_run.target_states
        ],
        "route_isolation": {
            "daily_market_data_only": True,
            "account_endpoints_used": False,
            "position_endpoints_used": False,
            "open_order_endpoints_used": False,
            "quote_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
            "tiingo_used": False,
        },
        "artifact_policy": {
            "raw_market_data_in_summary": False,
            "credentials_in_summary": False,
            "account_data_in_summary": False,
            "request_headers_in_summary": False,
            "broker_response_bodies_in_summary": False,
            "repo_storage_allowed": False,
        },
    }


def _write_source_safe_continuation_summary(
    *,
    artifact_root: Path,
    repository_root: Path,
    summary: dict[str, object],
    observed_at: datetime,
) -> str:
    """Write one immutable, source-safe aggregate only to the external artifact mount."""

    if artifact_root.is_symlink():
        raise ValueError("continuation artifact root is invalid")
    resolved_artifact_root = artifact_root.resolve()
    resolved_repository_root = repository_root.resolve()
    is_repository_child = resolved_artifact_root.is_relative_to(resolved_repository_root)
    if is_repository_child and not _is_external_mount_path(
        resolved_artifact_root, repository_root=resolved_repository_root
    ):
        raise ValueError("continuation summary must stay outside the Git workspace")
    artifact_root.mkdir(parents=True, exist_ok=True)
    resolved_artifact_root = artifact_root.resolve(strict=True)
    payload = (json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    content_hash = "sha256:" + hashlib.sha256(payload).hexdigest()
    stamp = observed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = resolved_artifact_root / f"continuation={stamp}-{uuid.uuid4().hex[:12]}"
    destination.mkdir()
    temporary = destination / f".summary-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination / "summary.json")
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return content_hash


def _is_external_mount_path(path: Path, *, repository_root: Path) -> bool:
    current = path
    while current != repository_root:
        if current.is_mount():
            return True
        current = current.parent
    return False


def _elapsed_seconds(started_monotonic: float, monotonic_clock: Callable[[], float]) -> float:
    return max(0.0, monotonic_clock() - started_monotonic)


def _elapsed_bucket(elapsed_seconds: float) -> str:
    if elapsed_seconds < 60:
        return "under_1m"
    if elapsed_seconds < 5 * 60:
        return "1_to_5m"
    if elapsed_seconds < 15 * 60:
        return "5_to_15m"
    if elapsed_seconds < 30 * 60:
        return "15_to_30m"
    return "30m_or_more"


def _client_reuse_outcome(*, client_reused_across_internal_cycles: bool, stop_reason: str) -> str:
    if client_reused_across_internal_cycles:
        return "reused_after_owned_retry_due"
    return f"not_observed_{stop_reason}"


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _distinct_paths(*paths: Path) -> bool:
    resolved = [path.resolve() for path in paths]
    return len(set(resolved)) == len(resolved)


def _canonical_execution_roots(
    cache_root: Path,
    control_root: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    """Keep credentialed execution inside the dedicated Compose mounts."""
    return (
        cache_root.as_posix() == _CANONICAL_CACHE_ROOT.as_posix()
        and control_root.as_posix() == _CANONICAL_CONTROL_ROOT.as_posix()
        and artifact_root.as_posix() == _CANONICAL_ARTIFACT_ROOT.as_posix()
        and repository_root.as_posix() == _CANONICAL_REPOSITORY_ROOT.as_posix()
    )


def _current_code_revision(repo_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = (
            subprocess.run(
                ["git", "diff", "--quiet"],
                cwd=repo_root,
                check=False,
                capture_output=True,
            ).returncode
            != 0
        )
    except (OSError, subprocess.SubprocessError):
        return "git:unavailable"
    return f"git:{revision}" + ("+dirty" if dirty else "")


if __name__ == "__main__":
    main()
