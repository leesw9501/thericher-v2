"""Run one bounded private KIS Paper 1m cache collection cycle."""

from __future__ import annotations

import argparse
import json
import os
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
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,
    KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
    run_kis_paper_private_intraday_backfill_cycle,
    sanitize_kis_paper_private_intraday_failure_reason,
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
    parser.add_argument("--pages-per-target", type=int, default=2)
    parser.add_argument("--mode", choices=("backfill", "head"), default="backfill")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return
    if args.pages_per_target <= 0:
        parser.error("--pages-per-target must be positive")

    try:
        config = _load_paper_config(dotenv_path)
        client = KisPaperMarketDataClient(
            config=config,
            transport=UrllibKisPaperMarketDataTransport(),
            max_minute_page_attempts=len(KIS_PAPER_PRIVATE_INTRADAY_TARGETS)
            * args.pages_per_target,
        )
        results = run_kis_paper_private_intraday_backfill_cycle(
            client=client,
            cache_root=_cache_root(args.mode),
            repo_root=_REPO_ROOT,
            code_revision=(code_revision or _current_code_revision)(_REPO_ROOT),
            pages_per_target=args.pages_per_target,
            resume_cursor=args.mode == "backfill",
            observed_at=clock(),
        )
    except KisPaperMarketDataError as error:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": sanitize_kis_paper_private_intraday_failure_reason(error),
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
                "status": "complete",
                "mode": args.mode,
                "targets": [
                    {
                        "target_key": result.target_key,
                        "status": result.status,
                        "row_count": result.row_count,
                        "exact_overlap_rows": result.exact_overlap_rows,
                        "reason": result.reason,
                    }
                    for result in results
                ],
            },
            sort_keys=True,
        )
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
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return "git:unavailable"
    return f"git:{revision}" + ("+dirty" if dirty else "")


def _load_paper_config(dotenv_path: Path) -> KisPaperMarketDataConfig:
    if os.environ.get("THERICHER_MODE", "off").strip().lower() in {"live", "kis_live"}:
        raise KisPaperMarketDataError("config_missing")
    app_key = os.environ.get("KIS_PAPER_APP_KEY")
    app_secret = os.environ.get("KIS_PAPER_APP_SECRET")
    if app_key is None and app_secret is None:
        return load_kis_paper_market_data_config(dotenv_path)
    if not app_key or not app_secret:
        raise KisPaperMarketDataError("config_missing")
    return KisPaperMarketDataConfig(app_key=app_key, app_secret=app_secret)


def _cache_root(mode: str = "backfill") -> Path:
    if mode not in {"backfill", "head"}:
        raise ValueError("private intraday mode is invalid")
    market_data_root = os.environ.get("THERICHER_MARKET_DATA_ROOT")
    if not market_data_root:
        base = KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT
    else:
        base = Path(market_data_root) / "us_equities" / "kis_paper_private" / "intraday"
    return base if mode == "backfill" else base.with_name(f"{base.name}-head")


if __name__ == "__main__":
    main()
