"""Write one source-safe fixed market-data contract inventory receipt."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from thericher_v2.data.market_data_contract_inventory import (  # noqa: E402
    DEFAULT_ARTIFACT_ROOT,
    build_market_data_contract_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-label", required=True)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    arguments = parser.parse_args()
    receipt = build_market_data_contract_inventory(
        inventory_label=arguments.inventory_label,
        retrieved_at_utc=datetime.now(UTC),
        artifact_root=arguments.artifact_root,
        repo_root=REPOSITORY_ROOT,
    )
    print(json.dumps(receipt.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
