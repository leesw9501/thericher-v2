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
from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    build_kis_paper_daily_nas_historical_forward_projection,
    load_verified_kis_paper_daily_nas_forward_cache,
)
from thericher_v2.research.kis_nas_d1_volatility_trend_breadth import (
    KIS_NAS_D1_VOLATILITY_TREND_BREADTH_ID,
)
from thericher_v2.research.kis_nas_d1_volatility_trend_prospective_observation import (
    KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_EVIDENCE,
    build_kis_nas_d1_volatility_trend_prospective_observation_input,
    run_kis_nas_d1_volatility_trend_prospective_observation,
    write_kis_nas_d1_volatility_trend_prospective_recovery_receipt,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
_DEFAULT_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
_CACHE_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-history/v1")
_PANEL_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-history-panel/v1")
_FORWARD_CACHE_RELATIVE_ROOT = Path("us_equities/kis_paper_private/daily-nas-forward/v1")
_CPU_LABEL = "cpu-20260728-r2"
_CUDA_LABEL = "cuda-20260728-r2"
_R5_LABEL = "sealed-20260728-r5"
_RECOVERY_EXIT = 20


def _resolve_forward_cache_root(
    *,
    market_data_root: Path,
    forward_cache_root: Path | None,
) -> Path:
    """Keep the forward cache colocated with an overridden market-data root."""

    return forward_cache_root or market_data_root / _FORWARD_CACHE_RELATIVE_ROOT


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument(
        "--forward-cache-root",
        type=Path,
    )
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
    forward_cache_root = _resolve_forward_cache_root(
        market_data_root=market_data_root,
        forward_cache_root=args.forward_cache_root,
    )
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
    try:
        forward_cache = load_verified_kis_paper_daily_nas_forward_cache(
            cache_root=forward_cache_root,
            repo_root=_REPOSITORY_ROOT,
        )
        forward_projection = build_kis_paper_daily_nas_historical_forward_projection(
            frozen_panel=prospective_panel,
            forward_cache=forward_cache,
            frozen_boundary=source_input.validation.common_sessions[-1],
        )
    except (OSError, RuntimeError, ValueError):
        receipt_path = write_kis_nas_d1_volatility_trend_prospective_recovery_receipt(
            artifact_root=artifact_root / "research",
            run_label=args.run_label,
            repo_root=_REPOSITORY_ROOT,
        )
        print(receipt_path.read_text(encoding="ascii"))
        return _RECOVERY_EXIT
    observation_input = build_kis_nas_d1_volatility_trend_prospective_observation_input(
        source_input,
        prospective_panel,
        forward_projection=forward_projection,
        forward_cache_root=forward_cache_root,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
