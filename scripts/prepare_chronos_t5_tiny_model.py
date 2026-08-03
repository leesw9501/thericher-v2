"""Download the approved Chronos-T5 Tiny safe files into the artifact root."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.chronos_t5_norgate_d1_probe import (
    CHRONOS_T5_MODEL_ID,
    CHRONOS_T5_MODEL_REVISION,
    DEFAULT_MODEL_ARTIFACT_ROOT,
    prepare_chronos_t5_tiny_local_model,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = (
    Path("/app/model_artifacts") if _REPO_ROOT == Path("/app") else DEFAULT_MODEL_ARTIFACT_ROOT
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)
    try:
        model = prepare_chronos_t5_tiny_local_model(
            artifact_root=args.artifact_root,
            repository_root=_REPO_ROOT,
        )
    except (OSError, RuntimeError, ValueError):
        print(
            json.dumps(
                {
                    "kind": "chronos_t5_tiny_local_model_manifest",
                    "status": "acquisition_unavailable",
                },
                sort_keys=True,
            )
        )
        return 20
    print(
        json.dumps(
            {
                "kind": "chronos_t5_tiny_local_model_manifest",
                "status": "prepared",
                "model_id": CHRONOS_T5_MODEL_ID,
                "model_revision": CHRONOS_T5_MODEL_REVISION,
                "manifest_sha256": model.manifest_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
