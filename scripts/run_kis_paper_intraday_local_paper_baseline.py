"""Replay one complete KIS intraday session through the local-paper baseline."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from thericher_v2.data import (
    load_verified_kis_paper_private_intraday_catalog,
    require_complete_kis_paper_private_intraday_session,
    us_equity_2026_session,
)
from thericher_v2.research.validation import run_intraday_multitimeframe_local_paper_baseline

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SYMBOL_EXCHANGES = {"QQQ": "NAS", "SPY": "AMS"}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--symbol", choices=tuple(_SYMBOL_EXCHANGES), default="QQQ")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)

    try:
        session_date = date.fromisoformat(args.session_date)
    except ValueError:
        parser.error("--session-date must use YYYY-MM-DD")
    session = us_equity_2026_session(session_date)
    if session is None:
        parser.error("--session-date is not a 2026 US equity trading session")

    symbol = str(args.symbol).upper()
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=args.cache_root,
        repo_root=_REPO_ROOT,
        symbol=symbol,
        exchange=_SYMBOL_EXCHANGES[symbol],
    )
    source = require_complete_kis_paper_private_intraday_session(
        catalog,
        session=session.window,
    )
    run_id = args.run_id or f"kis-private-intraday-{session_date.isoformat()}-{symbol.lower()}-v1"
    result = run_intraday_multitimeframe_local_paper_baseline(
        source,
        run_id=run_id,
        work_root=args.artifact_root,
        repo_root=_REPO_ROOT,
        session=session.window,
    )
    summary = {
        "status": "complete",
        "mode": "offline_local_paper",
        "session_date": session.session_date.isoformat(),
        "session_kind": session.kind,
        "symbol": symbol,
        "exchange": _SYMBOL_EXCHANGES[symbol],
        "dataset_id": result.dataset_id,
        "dataset_hash": result.dataset_hash,
        "all_fills_local_paper": all(cell.all_fills_local_paper for cell in result.cells),
        "cells": [
            {
                "timeframe": cell.timeframe.value,
                "status": cell.status,
                "resampled_bar_count": cell.resampled_bar_count,
                "local_paper_fill_count": cell.local_paper_fill_count,
                "event_jsonl_sha256": cell.event_jsonl_sha256,
            }
            for cell in result.cells
        ],
        "claim": "deterministic local-paper replay only; not a profitability or model claim",
    }
    summary_path = args.artifact_root / "intraday-multitimeframe-baseline" / run_id / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
