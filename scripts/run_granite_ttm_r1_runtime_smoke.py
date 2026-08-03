"""Run the local-only Granite TTM R1 structural CPU/CUDA smoke."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.research import granite_ttm_runtime_smoke as granite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("/app/model_artifacts"))
    parser.add_argument("--repo-root", type=Path, default=Path("/app"))
    parser.add_argument("--phase", choices=("cpu", "both"), default="both")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        model = granite.load_verified_granite_ttm_r1_local_model(
            artifact_root=args.artifact_root,
            repository_root=args.repo_root,
        )
        contract = granite.freeze_granite_ttm_r1_runtime_smoke(
            model,
            artifact_root=args.artifact_root,
            repository_root=args.repo_root,
        )
        cpu, cuda = granite.run_granite_ttm_r1_runtime_smoke(
            contract,
            model,
            include_cuda=args.phase == "both",
        )
    except (ImportError, OSError, RuntimeError, ValueError):
        print(
            json.dumps(
                {
                    "kind": granite.GRANITE_TTM_RUNTIME_SMOKE_ID,
                    "phase": args.phase,
                    "status": "runtime_unavailable",
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 20
    print(
        json.dumps(
            {
                "kind": granite.GRANITE_TTM_RUNTIME_SMOKE_ID,
                "contract_sha256": contract.sha256,
                "cpu": _safe_run(cpu),
                "cuda": _safe_run(cuda) if cuda is not None else None,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if cpu.status != "completed":
        return 20
    return 0 if cuda is None or cuda.status == "completed" else 20


def _safe_run(run: granite.GraniteTtmRuntimeRun) -> dict[str, str]:
    return {
        "phase": run.phase,
        "status": run.status,
        "terminal_category": run.terminal_category,
        "receipt_sha256": run.receipt_sha256,
    }


if __name__ == "__main__":
    raise SystemExit(main())
