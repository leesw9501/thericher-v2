"""Materialize the offline, source-local KIS Paper NAS D1 history panel."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    KIS_PAPER_DAILY_HISTORY_PANEL_EVIDENCE_ROOT,
    KIS_PAPER_DAILY_HISTORY_PANEL_ROOT,
    materialize_kis_paper_daily_history_panel,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_DAILY_HISTORY_CACHE_ROOT)
    parser.add_argument("--panel-root", type=Path, default=KIS_PAPER_DAILY_HISTORY_PANEL_ROOT)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=KIS_PAPER_DAILY_HISTORY_PANEL_EVIDENCE_ROOT,
    )
    args = parser.parse_args(argv)
    result = materialize_kis_paper_daily_history_panel(
        cache_root=Path(args.cache_root),
        panel_root=Path(args.panel_root),
        artifact_root=Path(args.artifact_root),
        repo_root=_REPOSITORY_ROOT,
    )
    print(result.receipt_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
