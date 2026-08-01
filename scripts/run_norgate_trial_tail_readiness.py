"""Run the bounded local Norgate tail readiness kill test on the Windows host."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from thericher_v2.data.norgate_trial_daily_capability_probe import (  # noqa: E402
    fingerprint_norgate_us_database_build,
)
from thericher_v2.data.norgate_trial_tail_readiness import (  # noqa: E402
    DEFAULT_NORGATE_ACTIVE_DATABASE_ROOT_CANDIDATES,
    DEFAULT_NORGATE_TRIAL_TAIL_READINESS_ROOT,
    build_norgate_trial_tail_readiness_receipt,
    collect_norgate_tail_reference_observation,
    default_norgate_trial_tail_readiness_dir,
    resolve_active_norgate_us_database_root,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--as-of", type=_parse_date, default=date.today())
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_NORGATE_TRIAL_TAIL_READINESS_ROOT,
    )
    parser.add_argument("--candidate-root", type=Path, action="append")
    arguments = parser.parse_args()
    observation = collect_norgate_tail_reference_observation(requested_end=arguments.as_of)
    active_root = resolve_active_norgate_us_database_root(
        observation.source_update_at_utc,
        candidates=tuple(
            arguments.candidate_root or DEFAULT_NORGATE_ACTIVE_DATABASE_ROOT_CANDIDATES
        ),
    )
    destination = arguments.artifact_root / default_norgate_trial_tail_readiness_dir(
        arguments.run_label
    ).name
    result = build_norgate_trial_tail_readiness_receipt(
        destination=destination,
        observation=observation,
        active_database_root=active_root,
        database_build_metadata_sha256=fingerprint_norgate_us_database_build(active_root),
        retrieved_at_utc=datetime.now(UTC),
        artifact_root=arguments.artifact_root,
        repo_root=REPOSITORY_ROOT,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
