"""Run the bounded NAS D1 candle-state CPU or CUDA package offline."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH,
    load_kis_paper_daily_history_sequence_input,
)
from thericher_v2.research.kis_nas_d1_candle_state_breadth import (
    build_kis_nas_d1_candle_state_breadth_input,
    run_kis_nas_d1_candle_state_cuda_breadth,
    run_kis_nas_d1_candle_state_l2_logistic_smoke,
)
from thericher_v2.research.kis_nas_d1_candle_state_campaign import (
    KIS_NAS_D1_CANDLE_STATE_ALLOWED_REVIEW_STATUSES,
    KIS_NAS_D1_CANDLE_STATE_PRECOMMIT_ROOT,
    build_kis_nas_d1_candle_state_campaign,
    write_kis_nas_d1_candle_state_campaign_precommit,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
_DEFAULT_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
_CACHE_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-history/v1")
_PANEL_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-history-panel/v1")
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("cpu-smoke", "cuda-breadth"), required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--cpu-smoke-summary", type=Path)
    parser.add_argument(
        "--review-status",
        choices=tuple(sorted(KIS_NAS_D1_CANDLE_STATE_ALLOWED_REVIEW_STATUSES)),
        required=True,
    )
    args = parser.parse_args(argv)
    if args.mode == "cuda-breadth" and args.cpu_smoke_summary is None:
        parser.error("--cpu-smoke-summary is required for cuda-breadth")
    if args.mode == "cpu-smoke" and args.cpu_smoke_summary is not None:
        parser.error("--cpu-smoke-summary is only valid for cuda-breadth")

    market_data_root = Path(args.market_data_root)
    artifact_root = Path(args.artifact_root)
    if (
        _REPOSITORY_ROOT == _DOCKER_REPOSITORY_ROOT
        and not artifact_root.resolve().is_relative_to(_DOCKER_ARTIFACT_ROOT)
    ):
        parser.error("Docker research artifacts must stay under /app/model_artifacts")
    panel_root = market_data_root / _PANEL_RELATIVE_ROOT
    manifest_path = (
        panel_root
        / KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH.parent.name
        / "manifest.json"
    )
    source_input = load_kis_paper_daily_history_sequence_input(
        manifest_path,
        cache_root=market_data_root / _CACHE_RELATIVE_ROOT,
        panel_root=panel_root,
        repo_root=_REPOSITORY_ROOT,
    )
    campaign_input = build_kis_nas_d1_candle_state_campaign(source_input)
    campaign_precommit = write_kis_nas_d1_candle_state_campaign_precommit(
        campaign_input,
        review_status=args.review_status,
        artifact_root=artifact_root / "research" / KIS_NAS_D1_CANDLE_STATE_PRECOMMIT_ROOT.name,
        repo_root=_REPOSITORY_ROOT,
    )
    breadth_input = build_kis_nas_d1_candle_state_breadth_input(
        campaign_input,
        campaign_precommit_hash=campaign_precommit.precommit_hash,
        review_status=args.review_status,
    )
    if args.mode == "cpu-smoke":
        run = run_kis_nas_d1_candle_state_l2_logistic_smoke(
            breadth_input,
            artifact_root=artifact_root / "research",
            run_label=args.run_label,
            repo_root=_REPOSITORY_ROOT,
        )
    else:
        run = run_kis_nas_d1_candle_state_cuda_breadth(
            breadth_input,
            cpu_smoke_summary_path=args.cpu_smoke_summary,
            artifact_root=artifact_root / "research",
            run_label=args.run_label,
            repo_root=_REPOSITORY_ROOT,
        )
    print(run.summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
