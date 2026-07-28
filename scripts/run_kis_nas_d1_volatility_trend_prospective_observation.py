"""Run one offline NAS D1 prospective shadow observation from local evidence."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily_history_panel import build_kis_paper_daily_history_panel
from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH,
    load_kis_paper_daily_history_sequence_input,
)
from thericher_v2.research.kis_nas_d1_volatility_trend_breadth import (
    KIS_NAS_D1_VOLATILITY_TREND_BREADTH_ID,
)
from thericher_v2.research.kis_nas_d1_volatility_trend_prospective_observation import (
    KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_EVIDENCE,
    build_kis_nas_d1_volatility_trend_prospective_observation_input,
    run_kis_nas_d1_volatility_trend_prospective_observation,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
_DEFAULT_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
_CACHE_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-history/v1")
_PANEL_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-history-panel/v1")
_CPU_LABEL = "cpu-20260728-r2"
_CUDA_LABEL = "cuda-20260728-r2"
_R5_LABEL = "sealed-20260728-r5"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--cpu-summary", type=Path)
    parser.add_argument("--cuda-summary", type=Path)
    parser.add_argument("--checkpoint-root", type=Path)
    parser.add_argument("--r5-precommit", type=Path)
    parser.add_argument("--r5-summary", type=Path)
    parser.add_argument(
        "--review-status",
        choices=("review_unavailable",),
        default="review_unavailable",
    )
    args = parser.parse_args(argv)

    market_data_root = Path(args.market_data_root)
    artifact_root = Path(args.artifact_root)
    cache_root = market_data_root / _CACHE_RELATIVE_ROOT
    panel_root = market_data_root / _PANEL_RELATIVE_ROOT
    manifest_path = (
        panel_root
        / KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH.parent.name
        / "manifest.json"
    )
    breadth_root = artifact_root / "research" / KIS_NAS_D1_VOLATILITY_TREND_BREADTH_ID
    cpu_summary = args.cpu_summary or (breadth_root / "cpu-smoke" / _CPU_LABEL / "summary.json")
    cuda_root = breadth_root / "cuda-breadth" / _CUDA_LABEL
    cuda_summary = args.cuda_summary or (cuda_root / "summary.json")
    checkpoint_root = args.checkpoint_root or (cuda_root / "checkpoints")
    r5_root = (
        artifact_root
        / "research"
        / "kis-nas-d1-volatility-trend-sealed-evaluation-v1"
        / _R5_LABEL
    )
    r5_precommit = args.r5_precommit or (r5_root / "precommit.json")
    r5_summary = args.r5_summary or (r5_root / "summary.json")
    source_input = load_kis_paper_daily_history_sequence_input(
        manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=_REPOSITORY_ROOT,
    )
    prospective_panel = build_kis_paper_daily_history_panel(
        cache_root,
        repo_root=_REPOSITORY_ROOT,
    )
    observation_input = build_kis_nas_d1_volatility_trend_prospective_observation_input(
        source_input,
        prospective_panel,
        evidence=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_EVIDENCE,
        cpu_summary_path=cpu_summary,
        cuda_summary_path=cuda_summary,
        checkpoint_root=checkpoint_root,
        r5_precommit_path=r5_precommit,
        r5_summary_path=r5_summary,
        review_status=args.review_status,
    )
    run = run_kis_nas_d1_volatility_trend_prospective_observation(
        observation_input,
        artifact_root=artifact_root / "research",
        run_label=args.run_label,
        review_status=args.review_status,
        repo_root=_REPOSITORY_ROOT,
    )
    print(run.receipt_path.read_text(encoding="ascii"))


if __name__ == "__main__":
    main()
