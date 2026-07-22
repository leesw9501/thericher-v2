"""Run one frozen KIS-native intraday CPU baseline campaign offline."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.research import (
    KIS_INTRADAY_CPU_CAMPAIGN_ID,
    build_kis_intraday_cpu_campaign_plan,
    run_kis_intraday_cpu_naive_baselines,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SYMBOL_EXCHANGES = {"QQQ": "NAS", "SPY": "AMS"}
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=tuple(_SYMBOL_EXCHANGES), default="QQQ")
    parser.add_argument("--session-date", action="append", required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    session_dates = _parse_session_dates(parser, args.session_date)
    run_label = str(args.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")

    symbol = str(args.symbol).upper()
    exchange = _SYMBOL_EXCHANGES[symbol]
    artifact_root = Path(args.artifact_root)
    run_root = artifact_root / "kis-intraday-cpu-campaign" / run_label
    summary_path = run_root / "summary.json"
    if run_root.exists():
        parser.error("--run-label already has external evidence; choose a new attempt label")

    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=Path(args.cache_root),
        repo_root=_REPO_ROOT,
        symbol=symbol,
        exchange=exchange,
    )
    plan = build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=session_dates,
        campaign_id=f"{KIS_INTRADAY_CPU_CAMPAIGN_ID}-{run_label}",
    )
    result = run_kis_intraday_cpu_naive_baselines(
        plan,
        artifact_root=artifact_root,
        work_root=run_root / "work",
        repo_root=_REPO_ROOT,
        run_label=run_label,
    )
    summary = _summary(
        result,
        symbol=symbol,
        exchange=exchange,
        run_label=run_label,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


def _parse_session_dates(
    parser: argparse.ArgumentParser,
    values: Sequence[str],
) -> tuple[date, ...]:
    try:
        return tuple(date.fromisoformat(value) for value in values)
    except ValueError:
        parser.error("--session-date must use YYYY-MM-DD")
    raise AssertionError("argparse.error must terminate")


def _summary(result: object, *, symbol: str, exchange: str, run_label: str) -> dict[str, object]:
    plan = result.plan  # type: ignore[attr-defined]
    campaign = plan.campaign
    catalog = plan.cataloged_bars
    baseline_runs = []
    for item in result.baseline_runs:  # type: ignore[attr-defined]
        baseline = item.baseline
        validation = baseline.result
        evidence = baseline.replay_evidence
        local_paper_only = (
            baseline.fill_source == "local_paper" and evidence.fill_source == "local_paper"
        )
        baseline_runs.append(
            {
                "phase": item.phase,
                "baseline_id": baseline.baseline_id,
                "bars_seen": validation.bars_seen,
                "decisions_seen": validation.decisions_seen,
                "trade_count": len(validation.trades),
                "event_count": validation.event_count,
                "fill_source": baseline.fill_source,
                "all_fills_local_paper": local_paper_only,
                "gross_pnl": str(validation.gross_pnl),
                "after_cost_pnl": str(validation.after_cost_pnl),
                "total_fees": str(validation.total_fees),
                "total_slippage": str(validation.total_slippage),
                "validation_artifact_path": str(baseline.artifact_path),
                "event_jsonl_sha256": evidence.event_jsonl_sha256,
                "state_sqlite_sha256": evidence.state_sqlite_sha256,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_local_paper",
        "run_label": run_label,
        "symbol": symbol,
        "exchange": exchange,
        "session_dates": [session_date.isoformat() for session_date in plan.session_dates],
        "split": {
            "development_session_dates": [
                session_date.isoformat() for session_date in plan.development_session_dates
            ],
            "purge_session_date": plan.purge_session_date.isoformat(),
            "validation_session_dates": [
                session_date.isoformat() for session_date in plan.validation_session_dates
            ],
        },
        "catalog": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
        },
        "campaign": {
            "campaign_id": campaign.campaign_id,
            "contract_hash": campaign.contract_hash,
            "naive_baselines": list(campaign.naive_baselines),
        },
        "all_fills_local_paper": all(
            item["all_fills_local_paper"] for item in baseline_runs
        ),
        "baselines": baseline_runs,
        "claim": (
            "descriptive CPU naive-baseline replay only; not a model promotion or "
            "profitability claim"
        ),
    }


if __name__ == "__main__":
    main()
