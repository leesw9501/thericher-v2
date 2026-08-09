"""Materialize the fixed local KIS intraday multi-timeframe availability receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_intraday_mtf_availability import (
    KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID,
    run_kis_intraday_mtf_availability_receipt,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_DEFAULT_RUN_LABEL = "local-cache-20260802-r2"
_EXPECTED_DATASET_HASHES = {
    "QQQ/NAS/1m": "sha256:8be6ad000631ecbc252708a223523e608631cf49c198703e5447921d805a8d40",
    "SPY/AMS/1m": "sha256:64f149f5ff1c9002107f001a44f78c54c8944e9c030d6153898b1229d9c742e6",
}
_CODE_PATHS = (
    Path("src/thericher_v2/contracts.py"),
    Path("src/thericher_v2/data/__init__.py"),
    Path("src/thericher_v2/data/kis_paper_intraday.py"),
    Path("src/thericher_v2/data/kis_intraday_mtf_availability.py"),
    Path("src/thericher_v2/data/local.py"),
    Path("src/thericher_v2/data/resample.py"),
    Path("src/thericher_v2/data/us_equity_session.py"),
    Path("src/thericher_v2/market/resample.py"),
    Path("src/thericher_v2/research/artifact_paths.py"),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--run-label", default=_DEFAULT_RUN_LABEL)
    parser.add_argument(
        "--allow-current-source-identities",
        action="store_true",
        help="omit the legacy fixed source-hash pin for one task-owned local receipt",
    )
    args = parser.parse_args(argv)

    result = run_kis_intraday_mtf_availability_receipt(
        cache_root=Path(args.cache_root),
        artifact_root=Path(args.artifact_root),
        repo_root=Path(args.repo_root),
        run_label=str(args.run_label),
        code_revision=_code_revision(),
        expected_dataset_hashes=(
            None if args.allow_current_source_identities else _EXPECTED_DATASET_HASHES
        ),
    )
    print(
        json.dumps(
            {
                "receipt_id": KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID,
                "contract_sha256": result.contract.contract_sha256,
                "receipt_sha256": result.receipt.receipt_sha256,
                "status": result.receipt.status,
                "reason": result.receipt.reason,
                "precommit_sha256": result.precommit_sha256,
                "summary_sha256": result.summary_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


def _code_revision() -> str:
    digest = hashlib.sha256()
    for relative_path in _CODE_PATHS:
        digest.update(relative_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update((_REPOSITORY_ROOT / relative_path).read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
