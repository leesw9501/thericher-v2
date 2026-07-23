"""Run one resumable private KIS Paper daily-cache backfill chunk."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_private_daily_backfill import (
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
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return
    cache_root = Path(args.cache_root)
    repository_root = Path(args.repository_root)

    def client_factory() -> KisPaperMarketDataClient:
        config = load_kis_paper_market_data_config(dotenv_path)
        return _client(config)

    try:
        result = run_kis_paper_private_daily_backfill_once(
            client_factory=client_factory,
            cache_root=cache_root,
            repo_root=repository_root,
            code_revision=(code_revision or _current_code_revision)(repository_root),
            observed_at=clock(),
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
        print(json.dumps({"status": "indeterminate", "reason": "backfill_worker_unavailable"}))
        return
    print(
        json.dumps(
            {
                "status": result.status,
                "target_key": result.target_key,
                "manifest_path": str(result.manifest_path) if result.manifest_path else None,
                "manifest_hash": result.manifest_hash,
                "row_count": result.row_count,
                "reason": result.reason,
            },
            sort_keys=True,
        )
    )


def _client(config: KisPaperMarketDataConfig) -> KisPaperMarketDataClient:
    return KisPaperMarketDataClient(
        config=config,
        transport=UrllibKisPaperMarketDataTransport(),
        max_daily_page_attempts=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
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
