"""Materialize the current-source-scoped liquid-universe manifest offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.data.source_scoped_liquid_universe import (
    SOURCE_SCOPED_LIQUID_UNIVERSE_OUTPUT_ROOT,
    materialize_source_scoped_liquid_universe_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=SOURCE_SCOPED_LIQUID_UNIVERSE_OUTPUT_ROOT,
    )
    args = parser.parse_args()
    result = materialize_source_scoped_liquid_universe_manifest(
        output_root=args.output_root,
        repository_root=Path(__file__).resolve().parents[1],
    )
    print(
        json.dumps(
            {
                "manifest_path": str(result.manifest_path),
                "manifest_sha256": result.manifest_sha256,
                "instrument_count": result.instrument_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
