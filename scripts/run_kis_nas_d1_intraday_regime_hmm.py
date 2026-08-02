"""Run the fixed KIS NAS D1 HMM regime preflight offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_nas_d1_intraday_regime_hmm import (
    KIS_NAS_D1_INTRADAY_REGIME_HMM_DEFAULT_ATTEMPT_ID,
    KIS_NAS_D1_INTRADAY_REGIME_HMM_ID,
    freeze_kis_nas_d1_intraday_regime_hmm_campaign,
    load_kis_nas_d1_intraday_regime_hmm_input,
    run_kis_nas_d1_intraday_regime_hmm,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _default_roots(*, system: str) -> tuple[Path, Path]:
    """Use Docker mounts only in a non-Windows runtime, never host lookalikes."""

    if system == "Windows":
        return Path(r"D:\market_data"), Path(r"D:\thericher-v2\model-artifacts")
    return Path("/app/market_data"), Path("/app/model_artifacts")


_DEFAULT_MARKET_DATA_ROOT, _DEFAULT_ARTIFACT_ROOT = _default_roots(system=platform.system())
_PANEL_NAME = "panel=7e8d6fe54dd5252fc4b9"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--attempt-id", default=KIS_NAS_D1_INTRADAY_REGIME_HMM_DEFAULT_ATTEMPT_ID)
    args = parser.parse_args(argv)

    market_data_root = Path(args.market_data_root)
    cache_root = market_data_root / "us_equities" / "kis_paper_private" / "daily-nas-history" / "v1"
    panel_root = (
        market_data_root / "us_equities" / "kis_paper_private" / "daily-nas-history-panel" / "v1"
    )
    input = load_kis_nas_d1_intraday_regime_hmm_input(
        manifest_path=panel_root / _PANEL_NAME / "manifest.json",
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=Path(args.repo_root),
    )
    contract = freeze_kis_nas_d1_intraday_regime_hmm_campaign(
        input,
        artifact_root=Path(args.artifact_root),
        repo_root=Path(args.repo_root),
        code_revision=_code_revision(),
        attempt_id=str(args.attempt_id),
    )
    result = run_kis_nas_d1_intraday_regime_hmm(contract)
    print(
        json.dumps(
            {
                "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_ID,
                "contract_sha256": contract.contract_sha256,
                "status": result.status,
                "reason": result.reason,
                "summary_sha256": result.summary_sha256,
                "registry_outcome_sha256": result.registry_outcome.record_sha256,
            },
            sort_keys=True,
        )
    )


def _code_revision() -> str:
    module = (
        _REPOSITORY_ROOT / "src" / "thericher_v2" / "research" / "kis_nas_d1_intraday_regime_hmm.py"
    )
    return "sha256:" + hashlib.sha256(module.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
