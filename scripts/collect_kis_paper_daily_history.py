"""Run one bounded fixed-NAS KIS Paper daily-history collection cycle."""

from __future__ import annotations

import argparse
import json
import subprocess
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

    try:
        result = run_kis_paper_daily_history_collection(
            client_factory=client_factory,
            request_gate=request_gate,
            token_start_gate=token_start_gate,
            cache_root=cache_root,
            evidence_root=artifact_root,
            repo_root=repository_root,
            code_revision=(code_revision or _current_code_revision)(repository_root),
            max_chunks=args.max_chunks,
            max_runtime=timedelta(seconds=args.max_runtime_seconds),
            clock=clock,
        )
    except (KisPaperDailyHistoryError, KisPaperMarketDataError, OSError, ValueError):
        print(json.dumps({"status": "unavailable", "reason": "daily_history_unavailable"}))
        return

    print(
        json.dumps(
            {
                "status": result.status,
                "accepted_page_count": result.accepted_page_count,
                "categorical_failure_count": result.categorical_failure_count,
                "chunk_attempt_count": result.chunk_attempt_count,
                "measured_accepted_pages_per_minute": result.measured_accepted_pages_per_minute,
                "remaining_page_estimate": result.remaining_page_estimate,
                "eta_bucket": result.eta_bucket,
                "next_due_utc": (
                    None
                    if result.next_due is None
                    else result.next_due.isoformat().replace("+00:00", "Z")
                ),
                "recovery": result.recovery,
                "registry_sha256": result.registry_sha256,
                "evidence_sha256": result.evidence_sha256,
                "targets": [
                    {
                        "target_key": target.target_key,
                        "state": target.state,
                        "cursor_date": target.cursor_date,
                        "coverage_bucket": target.coverage_bucket,
                        "accepted_page_count": target.accepted_page_count,
                        "categorical_failure_count": target.categorical_failure_count,
                        "last_reason": target.last_reason,
                    }
                    for target in result.target_states
                ],
            },
            sort_keys=True,
        )
    )


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
