"""Run the fixed KIS-native CUDA GRU smoke from the offline intraday cache."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from thericher_v2.data import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.research import run_kis_intraday_cuda_sequence_smoke

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
    args = parser.parse_args(argv)

    run_label = str(args.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")
    session_dates = _parse_session_dates(parser, args.session_date)
    artifact_root = Path(args.artifact_root)
    run_root = artifact_root / "kis-intraday-cuda-sequence-smoke" / run_label
    if run_root.exists():
        parser.error("--run-label already has external evidence; choose a new attempt label")

    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=Path(args.cache_root),
        repo_root=_REPO_ROOT,
        symbol="QQQ",
        exchange="NAS",
    )
    run = run_kis_intraday_cuda_sequence_smoke(
        catalog,
        session_dates=session_dates,
        artifact_root=artifact_root,
        run_label=run_label,
        repo_root=_REPO_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"))


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
