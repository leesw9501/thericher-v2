"""Write one offline categorical KIS D1 unexplained-discontinuity receipt."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_d1_adjustment_audit import (
    build_kis_d1_discontinuity_census_receipt,
)
from thericher_v2.research.validation import resolve_model_artifact_root


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=resolve_model_artifact_root())
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    receipt = build_kis_d1_discontinuity_census_receipt(
        artifact_root=args.artifact_root,
        market_data_root=args.market_data_root,
        repo_root=args.repo_root,
    )
    print(
        json.dumps(
            {
                "census_sha256": receipt.census_sha256,
                "receipt_sha256": receipt.receipt_sha256,
                "receipt_path": str(receipt.receipt_path),
                "status": receipt.census.status,
                "symbol_statuses": {
                    symbol: result.status
                    for symbol, result in receipt.census.results_by_symbol.items()
                },
                "model_eligible": receipt.census.model_eligible,
                "paper_trading_eligible": receipt.census.paper_trading_eligible,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
