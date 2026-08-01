"""Run the small local Norgate D1 pilot from its qualified capability receipt.

Invoke with the isolated Windows-host Norgate runtime, not Docker.  It reads no
credentials and prints source-safe identity/scope facts only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thericher_v2.data.norgate_trial_daily_capability_probe import (  # noqa: E402
    fingerprint_norgate_us_database_build,
    verify_norgate_trial_daily_capability_probe,
)
from thericher_v2.data.norgate_trial_daily_pilot import (  # noqa: E402
    build_norgate_trial_daily_pilot,
    default_norgate_trial_daily_pilot_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--capability-receipt", required=True, type=Path)
    args = parser.parse_args()
    capability = verify_norgate_trial_daily_capability_probe(
        args.capability_receipt,
        repo_root=ROOT,
    )
    result = build_norgate_trial_daily_pilot(
        destination=default_norgate_trial_daily_pilot_dir(args.run_label),
        retrieved_at_utc=datetime.now(UTC),
        capability_probe=capability,
        database_build_metadata_sha256=fingerprint_norgate_us_database_build(),
        repo_root=ROOT,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
