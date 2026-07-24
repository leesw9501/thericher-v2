"""Collect one bounded, prior-session-only KIS Paper SPY daily head snapshot."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
)
from thericher_v2.execution.kis_paper_daily_spy_head import (
    KIS_PAPER_DAILY_SPY_HEAD_ROOT,
    KisPaperDailySpyHeadError,
    collect_kis_paper_daily_spy_head_once,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    dotenv_path: Path = _REPOSITORY_ROOT / ".env",
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_DAILY_SPY_HEAD_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return
    try:
        config = load_kis_paper_market_data_config(dotenv_path)
        request_gate = KisPaperMarketDataRateGate(
            control_root=_shared_control_root(Path(args.cache_root))
        )
        result = collect_kis_paper_daily_spy_head_once(
            KisPaperMarketDataClient(
                config=config,
                transport=UrllibKisPaperMarketDataTransport(request_gate=request_gate),
            ),
            cache_root=args.cache_root,
            repository_root=args.repository_root,
            observed_at=clock(),
        )
    except KisPaperMarketDataError:
        print(
            json.dumps(
                {"status": "unavailable", "reason": "market_data_unavailable"},
                sort_keys=True,
            )
        )
        return
    except (KisPaperDailySpyHeadError, OSError, ValueError):
        print(json.dumps({"status": "unavailable", "reason": "daily_head_unavailable"}))
        return
    print(json.dumps(result.safe_payload(), sort_keys=True))


def _shared_control_root(cache_root: Path) -> Path:
    """Locate the common gate beside every private KIS Paper cache lane."""

    if cache_root.name == "v1" and cache_root.parent.name == "daily-head":
        return cache_root.parent.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    return cache_root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY


if __name__ == "__main__":
    main()
