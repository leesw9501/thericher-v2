"""Run one bounded broad KIS Paper D1 collection without broker routes."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.data.kis_paper_daily_broad_registry import (
    KIS_PAPER_DAILY_BROAD_REGISTRY_FILENAME,
    KisPaperDailyBroadRegistry,
    KisPaperDailyBroadRegistryError,
    build_kis_paper_daily_broad_registry,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_environment_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_daily_broad_backfill import (
    KIS_PAPER_DAILY_BROAD_BACKFILL_DEFAULT_MAX_CHUNKS,
    KIS_PAPER_DAILY_BROAD_BACKFILL_DEFAULT_MAX_RUNTIME,
    KisPaperDailyBroadBackfillError,
    KisPaperDailyBroadBackfillRun,
    run_kis_paper_daily_broad_backfill,
)

_CANONICAL_CACHE_ROOT = Path("/app/market_data")
_CANONICAL_CONTROL_ROOT = Path("/app/collection_control")
_CANONICAL_ARTIFACT_ROOT = Path("/app/model_artifacts")
_CANONICAL_REPOSITORY_ROOT = Path("/app")
_CANONICAL_SYMBOL_DIRECTORY_ROOT = Path("/app/symbol_directory")
_RECOVERY_EXIT = 20


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
    code_revision: Callable[[Path], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true")
    action.add_argument("--preflight", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--bootstrap-only", action="store_true")
    mode.add_argument("--continuation", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=_CANONICAL_CACHE_ROOT)
    parser.add_argument("--control-root", type=Path, default=_CANONICAL_CONTROL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_CANONICAL_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_CANONICAL_REPOSITORY_ROOT)
    parser.add_argument(
        "--symbol-directory-root",
        type=Path,
        default=_CANONICAL_SYMBOL_DIRECTORY_ROOT,
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=KIS_PAPER_DAILY_BROAD_BACKFILL_DEFAULT_MAX_CHUNKS,
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=KIS_PAPER_DAILY_BROAD_BACKFILL_DEFAULT_MAX_RUNTIME.total_seconds(),
    )
    args = parser.parse_args(argv)

    if not args.execute and not args.preflight:
        _emit({"status": "not_executed", "reason": "execute_flag_required"})
        return 2
    if args.max_chunks <= 0 or args.max_runtime_seconds <= 0:
        parser.error("worker bounds must be positive")
    if not _canonical_roots(
        cache_root=args.cache_root,
        control_root=args.control_root,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        symbol_directory_root=args.symbol_directory_root,
    ):
        _emit({"status": "not_executed", "reason": "canonical_container_roots_required"})
        return 2

    try:
        registry = build_kis_paper_daily_broad_registry(
            manifest_path=args.symbol_directory_root / "manifest.json",
            nasdaq_listing_path=args.symbol_directory_root / "nasdaqlisted.txt",
        )
    except (KisPaperDailyBroadRegistryError, OSError, ValueError):
        _emit({"status": "not_executed", "reason": "registry_unavailable"})
        return _RECOVERY_EXIT

    bootstrap_only = not args.continuation
    if args.preflight:
        _emit(_preflight_payload(registry_sha256=registry.registry_sha256, registry=registry))
        return 0

    request_gate = KisPaperMarketDataRateGate(control_root=args.control_root)
    token_start_gate = KisPaperMarketDataTokenStartGate(control_root=args.control_root)
    client: KisPaperMarketDataClient | None = None

    def client_factory() -> KisPaperMarketDataClient:
        nonlocal client
        if client is None:
            client = KisPaperMarketDataClient(
                config=load_kis_paper_market_data_environment_config(),
                transport=UrllibKisPaperMarketDataTransport(
                    request_gate=request_gate,
                    token_start_gate=token_start_gate,
                ),
                max_daily_page_attempts=args.max_chunks * 2,
            )
        return client

    try:
        result = run_kis_paper_daily_broad_backfill(
            registry=registry,
            client_factory=client_factory,
            request_gate=request_gate,
            token_start_gate=token_start_gate,
            cache_root=args.cache_root,
            evidence_root=args.artifact_root,
            repo_root=args.repository_root,
            code_revision=(code_revision or _current_code_revision)(args.repository_root),
            bootstrap_only=bootstrap_only,
            max_chunks=args.max_chunks,
            max_runtime=timedelta(seconds=args.max_runtime_seconds),
            clock=clock,
            sleeper=sleeper,
            monotonic_clock=monotonic_clock,
        )
    except (
        KisPaperDailyBroadBackfillError,
        KisPaperDailyBroadRegistryError,
        KisPaperMarketDataError,
        OSError,
        ValueError,
    ):
        _emit(_unavailable_payload(registry_sha256=registry.registry_sha256))
        return _RECOVERY_EXIT

    _emit(_run_payload(result))
    return 0


def _canonical_roots(
    *,
    cache_root: Path,
    control_root: Path,
    artifact_root: Path,
    repository_root: Path,
    symbol_directory_root: Path,
) -> bool:
    return (
        cache_root == _CANONICAL_CACHE_ROOT
        and control_root == _CANONICAL_CONTROL_ROOT
        and artifact_root == _CANONICAL_ARTIFACT_ROOT
        and repository_root == _CANONICAL_REPOSITORY_ROOT
        and symbol_directory_root == _CANONICAL_SYMBOL_DIRECTORY_ROOT
    )


def _preflight_payload(
    *,
    registry_sha256: str,
    registry: KisPaperDailyBroadRegistry,
) -> dict[str, object]:
    target_count = len(registry.targets)
    bootstrap_target_count = len(registry.bootstrap_targets)
    return {
        "status": "ready",
        "registry_sha256": registry_sha256,
        "target_count": target_count,
        "bootstrap_target_count": bootstrap_target_count,
        "scope": {
            "current_listing_only": True,
            "non_pit": True,
            "non_ranking": True,
            "provider_price_data": False,
        },
        "route_isolation": {
            "daily_market_data_only": True,
            "account_endpoints_used": False,
            "position_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
        },
        "configuration_loaded": False,
        "market_data_request_attempt_count": 0,
        "registry_filename": KIS_PAPER_DAILY_BROAD_REGISTRY_FILENAME,
    }


def _run_payload(result: KisPaperDailyBroadBackfillRun) -> dict[str, object]:
    return {
        "status": result.status,
        "bootstrap_only": result.bootstrap_only,
        "registry_sha256": result.registry_sha256,
        "chunk_attempt_count": result.chunk_attempt_count,
        "accepted_page_count": result.accepted_page_count,
        "categorical_failure_count": result.categorical_failure_count,
        "remaining_target_count": result.remaining_target_count,
        "next_due_utc": (
            None if result.next_due is None else result.next_due.isoformat().replace("+00:00", "Z")
        ),
        "recovery": result.recovery,
        "evidence_sha256": result.evidence_sha256,
        "route_isolation": {
            "daily_market_data_only": True,
            "account_endpoints_used": False,
            "position_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
        },
    }


def _unavailable_payload(*, registry_sha256: str) -> dict[str, object]:
    return {
        "status": "unavailable",
        "reason": "broad_daily_backfill_unavailable",
        "registry_sha256": registry_sha256,
        "route_isolation": {
            "daily_market_data_only": True,
            "account_endpoints_used": False,
            "position_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
        },
    }


def _current_code_revision(repository_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "git:unknown"
    revision = completed.stdout.strip()
    return f"git:{revision}" if revision else "git:unknown"


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
