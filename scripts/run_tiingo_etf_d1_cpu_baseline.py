"""Run the source-local Tiingo three-ETF D1 CPU control without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from thericher_v2.data.tiingo_etf_daily import (
    DEFAULT_MARKET_DATA_ROOT,
    load_verified_tiingo_etf_d1_snapshot,
)
from thericher_v2.research.tiingo_etf_d1_cpu_baseline import (
    run_tiingo_etf_d1_cpu_baseline,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    arguments = parser.parse_args(argv)
    dataset_id, dataset_hash, manifest_hash = _manifest_identity(arguments.snapshot)
    snapshot = load_verified_tiingo_etf_d1_snapshot(
        arguments.snapshot,
        dataset_id=dataset_id,
        expected_dataset_hash=dataset_hash,
        expected_manifest_hash=manifest_hash,
        market_data_root=arguments.market_data_root,
        repo_root=_REPOSITORY_ROOT,
    )
    run = run_tiingo_etf_d1_cpu_baseline(
        snapshot,
        artifact_root=arguments.artifact_root,
        run_label=arguments.run_label,
        repo_root=_REPOSITORY_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"))


def _manifest_identity(snapshot_dir: Path) -> tuple[str, str, str]:
    manifest_path = Path(snapshot_dir) / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Tiingo ETF D1 snapshot manifest is unavailable") from error
    if not isinstance(manifest, Mapping):
        raise ValueError("Tiingo ETF D1 snapshot manifest is invalid")
    dataset_id = manifest.get("dataset_id")
    dataset_hash = manifest.get("dataset_hash")
    if not isinstance(dataset_id, str) or not isinstance(dataset_hash, str):
        raise ValueError("Tiingo ETF D1 snapshot identity is invalid")
    manifest_hash = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    return dataset_id, dataset_hash, manifest_hash


if __name__ == "__main__":
    main()
