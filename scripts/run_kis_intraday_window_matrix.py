"""Run the offline KIS intraday window-sensitivity CPU preflight."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from thericher_v2.data import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.research.kis_intraday_window_matrix import (
    run_kis_intraday_window_matrix_preflight,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--session-date", action="append", required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    arguments = parser.parse_args(argv)

    run_label = str(arguments.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")
    artifact_root = Path(arguments.artifact_root)
    output_dir = artifact_root / "research" / "kis-intraday-window-matrix-v1" / run_label
    if output_dir.exists():
        parser.error("--run-label already has external evidence; choose a new attempt label")

    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=Path(arguments.cache_root),
        repo_root=_REPO_ROOT,
        symbol="QQQ",
        exchange="NAS",
    )
    run = run_kis_intraday_window_matrix_preflight(
        catalog,
        session_dates=_parse_session_dates(parser, arguments.session_date),
        artifact_root=artifact_root,
        run_label=run_label,
        repo_root=_REPO_ROOT,
    )
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    main()
