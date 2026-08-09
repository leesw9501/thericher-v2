"""Run one source-isolated Tiingo IEX r1 reconstruction integration phase."""

from __future__ import annotations

import argparse
from pathlib import Path

from thericher_v2.research.tiingo_iex_r1_representation_integration import (
    TIINGO_IEX_R1_SNAPSHOT_DIR,
    freeze_tiingo_iex_r1_representation_contract,
    run_tiingo_iex_r1_representation_integration,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--snapshot-dir", type=Path, default=TIINGO_IEX_R1_SNAPSHOT_DIR)
    parser.add_argument("--market-data-root", type=Path, default=Path(r"D:\market_data"))
    parser.add_argument("--artifact-root", type=Path, default=_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args()

    contract = freeze_tiingo_iex_r1_representation_contract(
        snapshot_dir=args.snapshot_dir,
        market_data_root=args.market_data_root,
        repo_root=args.repo_root,
    )
    run = run_tiingo_iex_r1_representation_integration(
        contract,
        phase=args.phase,
        artifact_root=args.artifact_root,
        run_label=args.run_label,
        repo_root=args.repo_root,
    )
    print(run.summary_path.read_text(encoding="ascii"))


if __name__ == "__main__":
    main()
