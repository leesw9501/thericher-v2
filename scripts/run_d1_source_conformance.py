"""Write one offline Norgate/KIS D1 metadata-conformance receipt."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.d1_source_conformance import build_d1_source_conformance_receipt
from thericher_v2.research.validation import resolve_model_artifact_root


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=resolve_model_artifact_root())
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    receipt = build_d1_source_conformance_receipt(
        artifact_root=args.artifact_root,
        market_data_root=args.market_data_root,
        repo_root=args.repo_root,
    )
    print(
        json.dumps(
            {
                "conformance_sha256": receipt.conformance_sha256,
                "receipt_path": str(receipt.receipt_path),
                "receipt_sha256": receipt.receipt_sha256,
                "status": receipt.conformance.status,
                "shared_field_names": list(receipt.conformance.shared_field_names),
                "source_parameterized_only": receipt.conformance.source_parameterized_only,
                "model_eligible": receipt.conformance.model_eligible,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
