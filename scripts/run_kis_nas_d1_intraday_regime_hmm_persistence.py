"""Precommit, then run the fixed NAS D1 HMM persistence check offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_nas_d1_intraday_regime_hmm_persistence import (
    KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DEFAULT_ATTEMPT_ID,
    KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID,
    freeze_kis_nas_d1_intraday_regime_hmm_persistence_campaign,
    load_kis_nas_d1_intraday_regime_hmm_persistence_input,
    precommit_kis_nas_d1_intraday_regime_hmm_persistence,
    run_kis_nas_d1_intraday_regime_hmm_persistence,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PANEL_NAME = "panel=7e8d6fe54dd5252fc4b9"
_PARENT_CAMPAIGN = "kis-nas-d1-intraday-regime-hmm-preflight-v1"
_PARENT_ATTEMPT = "cpu-preflight-r1"


def _default_roots(*, system: str) -> tuple[Path, Path]:
    if system == "Windows":
        return Path(r"D:\market_data"), Path(r"D:\thericher-v2\model-artifacts")
    return Path("/app/market_data"), Path("/app/model_artifacts")


_DEFAULT_MARKET_DATA_ROOT, _DEFAULT_ARTIFACT_ROOT = _default_roots(system=platform.system())


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument(
        "--attempt-id", default=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DEFAULT_ATTEMPT_ID
    )
    args = parser.parse_args(argv)

    artifact_root = Path(args.artifact_root)
    repo_root = Path(args.repo_root)
    precommit = precommit_kis_nas_d1_intraday_regime_hmm_persistence(
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision=_code_revision(),
        attempt_id=str(args.attempt_id),
    )
    market_data_root = Path(args.market_data_root)
    panel_root = (
        market_data_root / "us_equities" / "kis_paper_private" / "daily-nas-history-panel" / "v1"
    )
    cache_root = market_data_root / "us_equities" / "kis_paper_private" / "daily-nas-history" / "v1"
    parent_root = artifact_root / "research" / _PARENT_CAMPAIGN / _PARENT_ATTEMPT
    input = load_kis_nas_d1_intraday_regime_hmm_persistence_input(
        manifest_path=panel_root / _PANEL_NAME / "manifest.json",
        cache_root=cache_root,
        panel_root=panel_root,
        parent_contract_path=parent_root / "campaign-contract.json",
        parent_summary_path=parent_root / "cpu-summary.json",
        repo_root=repo_root,
    )
    contract = freeze_kis_nas_d1_intraday_regime_hmm_persistence_campaign(
        input,
        precommit=precommit,
    )
    result = run_kis_nas_d1_intraday_regime_hmm_persistence(contract)
    print(
        json.dumps(
            {
                "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID,
                "precommit_sha256": precommit.precommit_sha256,
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
    digest = hashlib.sha256()
    for path in (
        _REPOSITORY_ROOT
        / "src"
        / "thericher_v2"
        / "research"
        / "kis_nas_d1_intraday_regime_hmm.py",
        _REPOSITORY_ROOT
        / "src"
        / "thericher_v2"
        / "research"
        / "kis_nas_d1_intraday_regime_hmm_persistence.py",
    ):
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


if __name__ == "__main__":
    main()
