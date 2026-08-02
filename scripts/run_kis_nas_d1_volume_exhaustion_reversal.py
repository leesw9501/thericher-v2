"""Run the fixed KIS NAS D1 volume-exhaustion falsification offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_nas_d1_volume_exhaustion_reversal import (
    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEFAULT_ATTEMPT_ID,
    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID,
    freeze_kis_nas_d1_volume_exhaustion_reversal_campaign,
    load_kis_nas_d1_volume_exhaustion_reversal_input,
    run_kis_nas_d1_volume_exhaustion_reversal,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_IN_DOCKER = Path("/.dockerenv").is_file()
_DEFAULT_MARKET_DATA_ROOT = (
    Path("/app/market_data")
    if _IN_DOCKER and Path("/app/market_data").is_dir()
    else Path(r"D:\market_data")
)
_DEFAULT_ARTIFACT_ROOT = (
    Path("/app/model_artifacts")
    if _IN_DOCKER and Path("/app/model_artifacts").is_dir()
    else Path(r"D:\thericher-v2\model-artifacts")
)
_PANEL_NAME = "panel=7e8d6fe54dd5252fc4b9"
_CAMPAIGN_CODE_PATHS = (
    Path("src/thericher_v2/contracts.py"),
    Path("src/thericher_v2/research/__init__.py"),
    Path("src/thericher_v2/research/artifact_paths.py"),
    Path("src/thericher_v2/research/campaign_registry.py"),
    Path("src/thericher_v2/research/kis_nas_d1_volume_exhaustion_reversal.py"),
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument(
        "--attempt-id",
        default=KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEFAULT_ATTEMPT_ID,
    )
    args = parser.parse_args(argv)

    market_data_root = Path(args.market_data_root)
    cache_root = market_data_root / "us_equities" / "kis_paper_private" / "daily-nas-history" / "v1"
    panel_root = (
        market_data_root
        / "us_equities"
        / "kis_paper_private"
        / "daily-nas-history-panel"
        / "v1"
    )
    input = load_kis_nas_d1_volume_exhaustion_reversal_input(
        manifest_path=panel_root / _PANEL_NAME / "manifest.json",
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=Path(args.repo_root),
    )
    contract = freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
        input,
        artifact_root=Path(args.artifact_root),
        repo_root=Path(args.repo_root),
        code_revision=_code_revision(),
        attempt_id=str(args.attempt_id),
    )
    result = run_kis_nas_d1_volume_exhaustion_reversal(contract)
    print(
        json.dumps(
            {
                "campaign_id": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID,
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
    for relative_path in _CAMPAIGN_CODE_PATHS:
        digest.update(relative_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update((_REPOSITORY_ROOT / relative_path).read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


if __name__ == "__main__":
    main()
