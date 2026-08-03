"""Prepare the pinned Granite TTM R1 files in the external artifact root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.research import granite_ttm_runtime_smoke as granite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("/app/model_artifacts"))
    parser.add_argument("--repo-root", type=Path, default=Path("/app"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        model = granite.prepare_granite_ttm_r1_local_model(
            artifact_root=args.artifact_root,
            repository_root=args.repo_root,
        )
    except (ImportError, OSError, RuntimeError, ValueError):
        print(
            json.dumps(
                {
                    "kind": granite.GRANITE_TTM_RUNTIME_SMOKE_ID,
                    "status": "acquisition_unavailable",
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
                "model_id": granite.GRANITE_TTM_MODEL_ID,
                "model_revision": granite.GRANITE_TTM_MODEL_REVISION,
                "manifest_sha256": model.manifest_sha256,
                "status": "prepared",
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
