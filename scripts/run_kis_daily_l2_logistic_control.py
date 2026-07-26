"""Run the frozen offline QQQ/SPY daily L2 logistic control from an attested cache."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily import load_kis_paper_private_daily_catalog
from thericher_v2.research.historical_kis_campaign import HISTORICAL_KIS_DAILY_TARGET_KEYS
from thericher_v2.research.kis_daily_l2_logistic_control import (
    KIS_DAILY_L2_LOGISTIC_CONTROL_ID,
    run_kis_daily_l2_logistic_control,
)
from thericher_v2.research.kis_daily_sequence_architecture_screen import (
    KIS_DAILY_SEQUENCE_EXPECTED_FULL_DATASET_HASH,
    KIS_DAILY_SEQUENCE_EXPECTED_INDEX_HASH,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\daily")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    run_label = str(args.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")
    artifact_root = Path(args.artifact_root)
    output_dir = artifact_root / KIS_DAILY_L2_LOGISTIC_CONTROL_ID / run_label
    if output_dir.exists():
        parser.error("--run-label already has external evidence; choose a new attempt label")

    catalog = load_kis_paper_private_daily_catalog(
        cache_root=Path(args.cache_root),
        target_keys=HISTORICAL_KIS_DAILY_TARGET_KEYS,
        expected_index_hash=KIS_DAILY_SEQUENCE_EXPECTED_INDEX_HASH,
        expected_full_dataset_hash=KIS_DAILY_SEQUENCE_EXPECTED_FULL_DATASET_HASH,
        repo_root=_REPO_ROOT,
    )
    run = run_kis_daily_l2_logistic_control(
        catalog,
        artifact_root=artifact_root,
        run_label=run_label,
        repo_root=_REPO_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
