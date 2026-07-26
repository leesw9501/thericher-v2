"""Run the frozen historical KIS daily CPU baseline offline."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily import load_kis_paper_private_daily_catalog
from thericher_v2.research.historical_kis_campaign import (
    HISTORICAL_KIS_DAILY_TARGET_KEYS,
    build_historical_kis_daily_campaign,
    build_sanitized_historical_kis_summary,
    run_historical_kis_daily_cpu_baselines,
    validate_historical_kis_artifact_root,
    validate_historical_kis_run_label,
    write_frozen_historical_kis_campaign_contract,
    write_sanitized_historical_kis_summary,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\daily")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SYMBOLS = ("QQQ", "SPY")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=_SYMBOLS, default="QQQ")
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    run_label = str(args.run_label)
    try:
        validate_historical_kis_run_label(run_label)
        artifact_root = validate_historical_kis_artifact_root(
            Path(args.artifact_root),
            repo_root=_REPO_ROOT,
        )
    except ValueError as error:
        parser.error(str(error))

    run_root = artifact_root / "historical-kis-daily-cpu-baseline" / run_label
    if run_root.exists():
        parser.error("--run-label already has external evidence; choose a new attempt label")

    daily_catalog = load_kis_paper_private_daily_catalog(
        cache_root=Path(args.cache_root),
        repo_root=_REPO_ROOT,
        target_keys=HISTORICAL_KIS_DAILY_TARGET_KEYS,
    )
    source = daily_catalog.bars_by_symbol[str(args.symbol)]
    campaign = build_historical_kis_daily_campaign(
        source,
        artifact_root=artifact_root,
        repo_root=_REPO_ROOT,
    )
    contract_path = write_frozen_historical_kis_campaign_contract(
        campaign,
        path=run_root / "campaign-contract.json",
        repo_root=_REPO_ROOT,
    )
    result = run_historical_kis_daily_cpu_baselines(
        campaign,
        contract_path=contract_path,
        work_root=run_root / "work",
        repo_root=_REPO_ROOT,
        run_label=run_label,
    )
    summary = build_sanitized_historical_kis_summary(result, run_label=run_label)
    write_sanitized_historical_kis_summary(
        summary,
        path=run_root / "summary.json",
        artifact_root=artifact_root,
        repo_root=_REPO_ROOT,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
