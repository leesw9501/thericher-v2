"""Run one network-disabled Chronos-T5 Tiny D1 research probe phase."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.chronos_t5_norgate_d1_probe import (
    CHRONOS_T5_NORGATE_D1_PROBE_ID,
    DEFAULT_MODEL_ARTIFACT_ROOT,
    load_actual_chronos_t5_probe_inputs,
    run_chronos_t5_norgate_d1_probe,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if _REPO_ROOT == Path("/app"):
    _DEFAULT_MARKET_DATA_ROOT = Path("/app/market_data")
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
    _DEFAULT_ARTIFACT_ROOT = DEFAULT_MODEL_ARTIFACT_ROOT


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-id", default=CHRONOS_T5_NORGATE_D1_PROBE_ID)
    parser.add_argument("--code-revision-sha256")
    args = parser.parse_args(argv)
    try:
        contract, dataset, model = load_actual_chronos_t5_probe_inputs(
            artifact_root=args.artifact_root,
            market_data_root=args.market_data_root,
            repository_root=_REPO_ROOT,
            run_id=args.run_id,
            code_revision=args.code_revision_sha256 or _code_revision(_REPO_ROOT),
        )
        result = run_chronos_t5_norgate_d1_probe(
            contract,
            dataset,
            model,
            phase=args.phase,
        )
    except (ImportError, OSError, RuntimeError, ValueError):
        print(
            json.dumps(
                {
                    "kind": CHRONOS_T5_NORGATE_D1_PROBE_ID,
                    "phase": args.phase,
                    "status": "input_or_runtime_unavailable",
                },
                sort_keys=True,
            )
        )
        return 20
    print(
        json.dumps(
            {
                "kind": CHRONOS_T5_NORGATE_D1_PROBE_ID,
                "phase": result.phase,
                "status": result.status,
                "summary_sha256": result.summary_sha256,
            },
            sort_keys=True,
        )
    )
    return 0 if result.status == "completed" else 20


def _code_revision(repo_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = "git-unavailable"
    return "sha256:" + hashlib.sha256(revision.encode("ascii")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
