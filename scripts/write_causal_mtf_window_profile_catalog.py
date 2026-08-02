"""Write one explicit, source-safe causal-window catalog registration."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from thericher_v2.research.causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
    write_catalog_registration_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--issued-at", required=True, type=datetime.fromisoformat)
    args = parser.parse_args()
    receipt = write_catalog_registration_receipt(
        catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
        artifact_root=args.artifact_root,
        issued_at=args.issued_at,
    )
    print(
        json.dumps(
            {
                "catalog_sha256": receipt.catalog_sha256,
                "receipt_sha256": receipt.receipt_sha256,
                "receipt_relative_path": receipt.receipt_path.name,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
