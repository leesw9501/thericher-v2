"""Run the bounded local Norgate tail readiness kill test on the Windows host."""

from __future__ import annotations

import argparse
import contextlib
import io
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
    NorgateLocalSourcePreflightError,
    NorgateTrialTailReadinessError,
    build_norgate_trial_tail_readiness_receipt,
    collect_norgate_tail_reference_observation,
    default_norgate_trial_tail_readiness_dir,
    resolve_active_norgate_us_database_root,
)

_RECOVERY_EXIT_CODE = 20


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
    try:
        observation, active_root, database_build_metadata_sha256 = _collect_local_source(
            arguments
        )
        destination = arguments.artifact_root / default_norgate_trial_tail_readiness_dir(
            arguments.run_label
        ).name
        result = build_norgate_trial_tail_readiness_receipt(
            destination=destination,
            observation=observation,
            active_database_root=active_root,
            database_build_metadata_sha256=database_build_metadata_sha256,
            retrieved_at_utc=datetime.now(UTC),
            artifact_root=arguments.artifact_root,
            repo_root=REPOSITORY_ROOT,
        )
    except NorgateLocalSourcePreflightError as exc:
        recovery = (
            "restore_local_norgate_api_readiness"
            if exc.reason == "local_api_not_ready"
            else "configure_local_norgate_us_database"
        )
        print(
            json.dumps(
                {
                    "kind": "norgate_trial_tail_readiness",
                    "status": "unavailable",
                    "reason": exc.reason,
                    "recovery": recovery,
                },
                sort_keys=True,
            )
        )
        return _RECOVERY_EXIT_CODE
    except (NorgateTrialTailReadinessError, OSError, ValueError):
        print(
            json.dumps(
                {
                    "kind": "norgate_trial_tail_readiness",
                    "status": "unavailable",
                    "reason": "local_source_unavailable",
                    "recovery": "retry_after_local_source_recovery",
                },
                sort_keys=True,
            )
        )
        return _RECOVERY_EXIT_CODE
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return 0


def _collect_local_source(arguments: argparse.Namespace) -> tuple[object, Path, str]:
    """Keep third-party local-client output out of the source-safe result channel."""

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        observation = collect_norgate_tail_reference_observation(requested_end=arguments.as_of)
        active_root = resolve_active_norgate_us_database_root(
            observation.source_update_at_utc,
            candidates=tuple(
                arguments.candidate_root or DEFAULT_NORGATE_ACTIVE_DATABASE_ROOT_CANDIDATES
            ),
        )
        database_build_metadata_sha256 = fingerprint_norgate_us_database_build(active_root)
    return observation, active_root, database_build_metadata_sha256


if __name__ == "__main__":
    raise SystemExit(main())
