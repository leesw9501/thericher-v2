"""Materialize the current source-partitioned D1 eligibility receipt offline."""

from __future__ import annotations

import json
from pathlib import Path

from thericher_v2.data.d1_liquidity_eligibility import (
    materialize_source_partitioned_d1_liquidity_eligibility,
)


def main() -> int:
    result = materialize_source_partitioned_d1_liquidity_eligibility(
        repository_root=Path(__file__).resolve().parents[1]
    )
    print(
        json.dumps(
            {
                "receipt_path": str(result.receipt_path),
                "receipt_sha256": result.receipt_sha256,
                "partition_count": result.partition_count,
                "instrument_count": result.instrument_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
