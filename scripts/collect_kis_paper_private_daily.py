"""Run the single bounded private KIS Paper daily collector."""

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
from thericher_v2.execution.kis_private_daily_collector import (
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
    KIS_PAPER_PRIVATE_DAILY_CONTROL_ROOT,
    mark_private_daily_collector_completed,
    mark_private_daily_collector_network_started,
    private_daily_cache_would_cross_free_space_floor,
    private_daily_collector_recovery_state,
    reserve_private_daily_collector_attempt,
    run_bounded_kis_paper_private_daily_collection,
    sanitize_kis_paper_private_daily_collector_failure_reason,
    write_kis_paper_private_daily_cache,
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
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return

    try:
        recovery = private_daily_collector_recovery_state(
            control_root=KIS_PAPER_PRIVATE_DAILY_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
        )
    except ValueError:
        print(json.dumps({"status": "not_executed", "reason": "private_daily_control_invalid"}))
        return
    if recovery != "restart":
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": "private_daily_attempt_already_reserved",
                    "recovery": recovery,
                },
                sort_keys=True,
            )
        )
        return

    try:
        if private_daily_cache_would_cross_free_space_floor(
            cache_root=KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
            repo_root=_REPO_ROOT,
        ):
            print(
                json.dumps(
                    {"status": "not_executed", "reason": "storage_floor_would_be_crossed"}
                )
            )
            return
    except (OSError, ValueError):
        print(json.dumps({"status": "not_executed", "reason": "storage_preflight_failed"}))
        return

    try:
        config = load_kis_paper_market_data_config(dotenv_path)
    except KisPaperMarketDataError as error:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": sanitize_kis_paper_private_daily_collector_failure_reason(error),
                }
            )
        )
        return

    reserved_at = clock()
    try:
        reserve_private_daily_collector_attempt(
            control_root=KIS_PAPER_PRIVATE_DAILY_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            observed_at=reserved_at,
        )
        network_started_at = clock()
        mark_private_daily_collector_network_started(
            control_root=KIS_PAPER_PRIVATE_DAILY_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            observed_at=network_started_at,
        )
    except ValueError:
        print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
        return

    client = _client(config)
    revision = (code_revision or _current_code_revision)(_REPO_ROOT)
    try:
        result = run_bounded_kis_paper_private_daily_collection(
            client,
            code_revision=revision,
            observed_at=network_started_at,
        )
    except (KisPaperMarketDataError, ValueError):
        print(json.dumps({"status": "indeterminate", "reason": "collector_result_unavailable"}))
        return
    run_id = reserved_at.strftime("%Y%m%dT%H%M%SZ")
    try:
        manifest_path, manifest_hash = write_kis_paper_private_daily_cache(
            result=result,
            cache_root=KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
            run_id=run_id,
            repo_root=_REPO_ROOT,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "indeterminate", "reason": "cache_write_failed"}))
        return
    try:
        mark_private_daily_collector_completed(
            control_root=KIS_PAPER_PRIVATE_DAILY_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            observed_at=clock(),
            manifest_hash=manifest_hash,
            manifest_path=manifest_path,
            result=result,
        )
    except ValueError:
        print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
        return
    print(
        json.dumps(
            {
                "status": result.status,
                "manifest_path": str(manifest_path),
                "manifest_hash": manifest_hash,
                "row_count": len(result.rows),
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
