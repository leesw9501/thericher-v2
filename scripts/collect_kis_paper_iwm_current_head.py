"""Collect one isolated KIS Paper IWM current-head page and a safe receipt."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_iwm_current_head import (
    KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_KIND,
    build_and_write_kis_paper_iwm_current_head_ingestion,
    validate_kis_paper_iwm_current_head_ingestion_artifact_root,
)
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
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_IWM_CURRENT_HEAD_CACHE_ROOT,
    KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,
    run_kis_paper_iwm_current_head_cycle,
    sanitize_kis_paper_private_intraday_failure_reason,
    validate_kis_paper_iwm_current_head_request,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    config_loader: Callable[[Path], KisPaperMarketDataConfig] = load_kis_paper_market_data_config,
    code_revision: Callable[[Path], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--target", default="IWM/AMS")
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_IWM_CURRENT_HEAD_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--dotenv-path", type=Path, default=_REPOSITORY_ROOT / ".env")
    args = parser.parse_args(argv)
    if not args.execute:
        print(
            json.dumps(
                {
                    "kind": KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_KIND,
                    "status": "not_executed",
                    "reason": "execute_flag_required",
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        target = _parse_target(args.target)
        artifact_root = validate_kis_paper_iwm_current_head_ingestion_artifact_root(
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
        )
        validate_kis_paper_iwm_current_head_request(
            target=target,
            cache_root=args.cache_root,
            repo_root=args.repository_root,
        )
        observed_at = clock()
        request_starts: list[datetime] = []
        control_root = (
            KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        client = KisPaperMarketDataClient(
            config=config_loader(args.dotenv_path),
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=KisPaperMarketDataRateGate(
                    control_root=control_root,
                    on_request_started=request_starts.append,
                ),
                token_start_gate=KisPaperMarketDataTokenStartGate(control_root=control_root),
            ),
            max_minute_page_attempts=1,
        )
        run = run_kis_paper_iwm_current_head_cycle(
            client=client,
            cache_root=args.cache_root,
            repo_root=args.repository_root,
            code_revision=(code_revision or _current_code_revision)(args.repository_root),
            target=target,
            observed_at=observed_at,
        )
        result = build_and_write_kis_paper_iwm_current_head_ingestion(
            run=run,
            call_counts=client.call_counts,
            request_start_count=len(request_starts),
            observed_at=observed_at,
            artifact_root=artifact_root,
            repository_root=args.repository_root,
        )
    except (KisPaperMarketDataError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "kind": KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_KIND,
                    "status": "unavailable",
                    "paper_only": True,
                    "route_class": "kis_paper_market_data",
                    "reason": sanitize_kis_paper_private_intraday_failure_reason(error),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result.outcome.safe_payload(), sort_keys=True))
    return 0


def _parse_target(value: str) -> tuple[str, str]:
    symbol, separator, exchange = value.partition("/")
    if not separator or not symbol or not exchange or "/" in exchange:
        raise ValueError("IWM current-head target is invalid")
    return symbol, exchange


def _current_code_revision(repository_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "git:unavailable"
    return f"git:{revision}" if revision else "git:unavailable"


if __name__ == "__main__":
    raise SystemExit(main())
