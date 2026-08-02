"""Run the fixed local Tiingo D1 compression-continuation falsification offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.tiingo_etf_daily import load_verified_tiingo_etf_d1_snapshot
from thericher_v2.research.tiingo_d1_trio_intraday_compression_continuation import (
    TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DEFAULT_ATTEMPT_ID,
    TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID,
    build_tiingo_d1_trio_intraday_compression_input,
    freeze_tiingo_d1_trio_intraday_compression_campaign,
    run_tiingo_d1_trio_intraday_compression_campaign,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SNAPSHOT = Path(
    r"D:\market_data\us_equities\tiingo_etf_daily\canonical\snapshot=20260801T173121Z-tiingo-etf-d1-r1"
)
_DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_EXPECTED_DATASET_ID = "us_equities.tiingo_etf_daily.snapshot=20260801T173121Z-tiingo-etf-d1-r1"
_EXPECTED_DATASET_HASH = "sha256:b47539a373bf2d625ad2380376808cf412219f6c5d932b66631bb3aa553683cf"
_EXPECTED_MANIFEST_HASH = "sha256:8b2e375a027e645ea2065ec61b252b7097da5e743155eb819129391125c072de"
_CAMPAIGN_CODE_PATHS = (
    Path("src/thericher_v2/contracts.py"),
    Path("src/thericher_v2/data/__init__.py"),
    Path("src/thericher_v2/data/tiingo_etf_daily.py"),
    Path("src/thericher_v2/research/__init__.py"),
    Path("src/thericher_v2/research/artifact_paths.py"),
    Path("src/thericher_v2/research/campaign_registry.py"),
    Path("src/thericher_v2/research/tiingo_d1_trio_intraday_compression_continuation.py"),
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=_DEFAULT_SNAPSHOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument(
        "--attempt-id",
        default=TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DEFAULT_ATTEMPT_ID,
    )
    args = parser.parse_args(argv)

    snapshot = load_verified_tiingo_etf_d1_snapshot(
        Path(args.snapshot),
        dataset_id=_EXPECTED_DATASET_ID,
        expected_dataset_hash=_EXPECTED_DATASET_HASH,
        expected_manifest_hash=_EXPECTED_MANIFEST_HASH,
        market_data_root=Path(args.market_data_root),
        repo_root=Path(args.repo_root),
    )
    campaign_input = build_tiingo_d1_trio_intraday_compression_input(snapshot)
    campaign = freeze_tiingo_d1_trio_intraday_compression_campaign(
        campaign_input,
        artifact_root=Path(args.artifact_root),
        repo_root=Path(args.repo_root),
        code_revision=_code_revision(),
        attempt_id=str(args.attempt_id),
    )
    result = run_tiingo_d1_trio_intraday_compression_campaign(campaign)
    print(
        json.dumps(
            {
                "campaign_id": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID,
                "contract_sha256": campaign.contract_sha256,
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
