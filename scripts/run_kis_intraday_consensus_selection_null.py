"""Run the frozen QQQ equal-count selection-null diagnostic offline."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from thericher_v2.data import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.research.kis_intraday_consensus_selection_null import (
    run_kis_intraday_consensus_selection_null,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_DEFAULT_BASELINE_SUMMARY = (
    _DEFAULT_ARTIFACT_ROOT
    / "research"
    / "kis-intraday-multitimeframe-consensus-replay-v1"
    / "qqq-20260623-20260721-consensus-r1"
    / "summary.json"
)
_DEFAULT_SESSION_DATES = (
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
    date(2026, 7, 16),
    date(2026, 7, 17),
    date(2026, 7, 20),
    date(2026, 7, 21),
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--session-date", action="append")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--baseline-summary", type=Path, default=_DEFAULT_BASELINE_SUMMARY)
    arguments = parser.parse_args(argv)
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=Path(arguments.cache_root),
        repo_root=_REPO_ROOT,
        symbol="QQQ",
        exchange="NAS",
    )
    run = run_kis_intraday_consensus_selection_null(
        catalog,
        session_dates=_parse_session_dates(parser, arguments.session_date),
        baseline_summary_path=Path(arguments.baseline_summary),
        artifact_root=Path(arguments.artifact_root),
        run_label=str(arguments.run_label),
        repo_root=_REPO_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"), end="")


def _parse_session_dates(
    parser: argparse.ArgumentParser,
    values: Sequence[str] | None,
) -> tuple[date, ...]:
    if values is None:
        return _DEFAULT_SESSION_DATES
    try:
        return tuple(date.fromisoformat(value) for value in values)
    except ValueError:
        parser.error("--session-date must use YYYY-MM-DD")
    raise AssertionError("argparse.error must terminate")


if __name__ == "__main__":
    main()
