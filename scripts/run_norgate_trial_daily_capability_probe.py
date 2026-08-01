"""Run the local, host-only Norgate trial daily capability probe.

Invoke this file with the isolated host Norgate Python runtime, not Docker or
the project runtime.  It loads no credentials and makes no network, KIS, or
broker call.
"""

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

from thericher_v2.data.norgate_trial_daily_capability_probe import (  # noqa: E402
    DEFAULT_NORGATE_HOST_DATA_ROOT,
    build_norgate_trial_daily_capability_probe,
    default_norgate_trial_daily_capability_probe_dir,
    fingerprint_norgate_us_database_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--run-label")
    parser.add_argument("--norgate-data-root", type=Path, default=DEFAULT_NORGATE_HOST_DATA_ROOT)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    retrieved_at = datetime.now(UTC)
    run_label = arguments.run_label or retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    destination = arguments.destination or default_norgate_trial_daily_capability_probe_dir(
        run_label
    )
    result = build_norgate_trial_daily_capability_probe(
        destination=destination,
        retrieved_at_utc=retrieved_at,
        database_build_metadata_sha256=fingerprint_norgate_us_database_build(
            arguments.norgate_data_root
        ),
        repo_root=REPOSITORY_ROOT,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
