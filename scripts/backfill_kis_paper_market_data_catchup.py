"""Drain finite private KIS Paper daily-history cursors at the shared safe pace."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_market_data_catchup import (
    KIS_PAPER_MARKET_DATA_CATCHUP_MAX_CHUNKS,
    KIS_PAPER_MARKET_DATA_CATCHUP_MAX_RUNTIME,
    run_kis_paper_market_data_catchup,
)
from thericher_v2.execution.kis_private_daily_backfill import (
    KisPaperPrivateDailyBackfillRun,
    run_kis_paper_private_daily_backfill_once,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
    sanitize_kis_paper_private_daily_collector_failure_reason,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    dotenv_path: Path = _REPO_ROOT / ".env",
    code_revision: Callable[[Path], str] | None = None,
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--max-chunks", type=int, default=KIS_PAPER_MARKET_DATA_CATCHUP_MAX_CHUNKS)
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=KIS_PAPER_MARKET_DATA_CATCHUP_MAX_RUNTIME.total_seconds(),
    )
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return
    if args.max_runtime_seconds <= 0:
        parser.error("--max-runtime-seconds must be positive")

    cache_root = Path(args.cache_root)
    repository_root = Path(args.repository_root)
    request_gate = KisPaperMarketDataRateGate(
        control_root=cache_root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    )
    token_start_gate = KisPaperMarketDataTokenStartGate(
        control_root=cache_root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    )
    revision = (code_revision or _current_code_revision)(repository_root)
    client: KisPaperMarketDataClient | None = None

    def client_factory() -> KisPaperMarketDataClient:
        nonlocal client
        if client is None:
            client = _client(
                load_kis_paper_market_data_config(dotenv_path),
                request_gate=request_gate,
                token_start_gate=token_start_gate,
                max_daily_page_attempts=(
                    args.max_chunks * KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS
                ),
            )
        return client

    def run_daily_chunk() -> KisPaperPrivateDailyBackfillRun:
        return run_kis_paper_private_daily_backfill_once(
            client_factory=client_factory,
            cache_root=cache_root,
            repo_root=repository_root,
            code_revision=revision,
            observed_at=clock(),
            inter_chunk_interval=timedelta(0),
        )

    try:
        result = run_kis_paper_market_data_catchup(
            run_daily_chunk=run_daily_chunk,
            max_chunks=args.max_chunks,
            max_runtime=timedelta(seconds=args.max_runtime_seconds),
            clock=clock,
        )
    except KisPaperMarketDataError as error:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": sanitize_kis_paper_private_daily_collector_failure_reason(error),
                },
                sort_keys=True,
            )
        )
        return
    except (OSError, ValueError):
        print(json.dumps({"status": "indeterminate", "reason": "catchup_worker_unavailable"}))
        return

    print(
        json.dumps(
            {
                "status": result.status,
                "chunk_attempt_count": result.chunk_attempt_count,
                "retained_chunk_count": result.retained_chunk_count,
                "completed_target_count": result.completed_target_count,
                "reason": result.last_reason,
            },
            sort_keys=True,
        )
    )


def _client(
    config: KisPaperMarketDataConfig,
    *,
    request_gate: KisPaperMarketDataRateGate,
    token_start_gate: KisPaperMarketDataTokenStartGate,
    max_daily_page_attempts: int = KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
) -> KisPaperMarketDataClient:
    return KisPaperMarketDataClient(
        config=config,
        transport=UrllibKisPaperMarketDataTransport(
            request_gate=request_gate,
            token_start_gate=token_start_gate,
        ),
        max_daily_page_attempts=max_daily_page_attempts,
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
        dirty = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        ).returncode != 0
    except (OSError, subprocess.SubprocessError):
        return "git:unavailable"
    return f"git:{revision}" + ("+dirty" if dirty else "")


if __name__ == "__main__":
    main()
