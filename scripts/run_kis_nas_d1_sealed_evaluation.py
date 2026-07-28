"""Run one fixed NAS D1 sealed evaluation without provider or broker access."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH,
    load_kis_paper_daily_history_sequence_input,
)
from thericher_v2.research.kis_nas_d1_sealed_evaluation import (
    KIS_NAS_D1_SEALED_EVALUATION_EVIDENCE,
    build_kis_nas_d1_sealed_evaluation_input,
    run_kis_nas_d1_sealed_evaluation,
)
from thericher_v2.research.kis_nas_d1_sequence_breadth import (
    KIS_NAS_D1_SEQUENCE_BREADTH_ID,
    require_frozen_kis_nas_d1_sequence_breadth_campaign,
)
from thericher_v2.research.kis_nas_d1_sequence_campaign import (
    build_kis_nas_d1_sequence_campaign,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
_DEFAULT_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
_CACHE_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-history/v1")
_PANEL_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-history-panel/v1")
_CPU_RUN_LABEL = "cpu-smoke-20260728-docker-r2"
_CUDA_RUN_LABEL = "cuda-breadth-20260728-docker-r2"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--cpu-summary",
        type=Path,
        help="Pinned external CPU breadth summary; defaults below --artifact-root.",
    )
    parser.add_argument(
        "--cuda-summary",
        type=Path,
        help="Pinned external CUDA breadth summary; defaults below --artifact-root.",
    )
    parser.add_argument(
        "--checkpoint-root",
        type=Path,
        help="Pinned external CUDA checkpoint directory; defaults below --artifact-root.",
    )
    parser.add_argument(
        "--review-status",
        choices=("review_unavailable",),
        default="review_unavailable",
    )
    args = parser.parse_args(argv)

    market_data_root = Path(args.market_data_root)
    artifact_root = Path(args.artifact_root)
    panel_root = market_data_root / _PANEL_RELATIVE_ROOT
    manifest_path = (
        panel_root
        / KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH.parent.name
        / "manifest.json"
    )
    breadth_root = artifact_root / "research" / KIS_NAS_D1_SEQUENCE_BREADTH_ID
    cpu_summary = args.cpu_summary or (
        breadth_root / "cpu-smoke" / _CPU_RUN_LABEL / "summary.json"
    )
    cuda_run_root = breadth_root / "cuda-breadth" / _CUDA_RUN_LABEL
    cuda_summary = args.cuda_summary or cuda_run_root / "summary.json"
    checkpoint_root = args.checkpoint_root or cuda_run_root / "checkpoints"

    source_input = load_kis_paper_daily_history_sequence_input(
        manifest_path,
        cache_root=market_data_root / _CACHE_RELATIVE_ROOT,
        panel_root=panel_root,
        repo_root=_REPOSITORY_ROOT,
    )
    campaign_input = build_kis_nas_d1_sequence_campaign(source_input)
    require_frozen_kis_nas_d1_sequence_breadth_campaign(campaign_input)
    evaluation_input = build_kis_nas_d1_sealed_evaluation_input(
        source_input,
        evidence=KIS_NAS_D1_SEALED_EVALUATION_EVIDENCE,
        cpu_summary_path=cpu_summary,
        cuda_summary_path=cuda_summary,
        checkpoint_root=checkpoint_root,
    )
    run = run_kis_nas_d1_sealed_evaluation(
        evaluation_input,
        artifact_root=artifact_root / "research",
        run_label=args.run_label,
        review_status=args.review_status,
        repo_root=_REPOSITORY_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
