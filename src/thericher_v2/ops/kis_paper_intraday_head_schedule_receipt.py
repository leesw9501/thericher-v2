"""Persist source-safe terminal evidence for one intraday-head dispatch."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_KIND = "kis_paper_intraday_head_schedule_receipt"
KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY = (
    "execution/kis-paper-intraday-head-schedule"
)
DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT = Path(
    r"D:\thericher-v2\model-artifacts"
)
SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE = 20
_DEFAULT_REPOSITORY_ROOT = Path.cwd()

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_LOOP_STATUSES = frozenset({"embedded", "preview", "no_intent", "unavailable"})
_SESSION_STATUSES = frozenset({"no_intent", "canary_completed", "unavailable"})
_VALIDATION_STATUSES = frozenset({"validated", "not_run", "unavailable"})
_OBSERVATION_STATUSES = frozenset({"pending", "unavailable", "complete"})


@dataclass(frozen=True)
class KisPaperIntradayHeadScheduleReceipt:
    """One immutable terminal result for the existing scheduled dispatch."""

    run_id: str
    observed_at: datetime
    collection_exit_code: int
    prospective_loop_exit_code: int
    prospective_loop_status: str
    prospective_session_exit_code: int
    prospective_session_status: str
    prospective_session_id: str | None
    prospective_validation_exit_code: int
    prospective_validation_status: str
    prospective_validation_session_id: str | None
    observation_exit_code: int
    observation_status: str
    terminal_status: str
    recovery_class: str
    scheduler_exit_code: int
    evidence_path: Path

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_KIND,
            "status": self.terminal_status,
            "run_id": self.run_id,
            "observed_at": _utc_marker(self.observed_at),
            "stages": {
                "collection": {
                    "exit_code": self.collection_exit_code,
                    "status": "exit_zero" if self.collection_exit_code == 0 else "exit_nonzero",
                },
                "prospective_loop": {
                    "exit_code": self.prospective_loop_exit_code,
                    "status": self.prospective_loop_status,
                },
                "prospective_session": {
                    "exit_code": self.prospective_session_exit_code,
                    "status": self.prospective_session_status,
                    "session_id": self.prospective_session_id,
                },
                "prospective_validation": {
                    "exit_code": self.prospective_validation_exit_code,
                    "status": self.prospective_validation_status,
                    "session_id": self.prospective_validation_session_id,
                },
                "observation": {
                    "exit_code": self.observation_exit_code,
                    "status": self.observation_status,
                    "required_for_qqq_cycle": False,
                },
            },
            "terminal": {
                "status": self.terminal_status,
                "recovery_class": self.recovery_class,
                "scheduler_exit_code": self.scheduler_exit_code,
            },
            "artifact_policy": {
                "credentials_in_receipt": False,
                "account_data_in_receipt": False,
                "raw_market_data_in_receipt": False,
                "broker_order_data_in_receipt": False,
                "repo_storage_allowed": False,
            },
            "claim": (
                "scheduled dispatch observability only; not a model result, PnL claim, "
                "or broker action"
            ),
        }


def write_kis_paper_intraday_head_schedule_receipt(
    *,
    run_id: str,
    collection_exit_code: int,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
    observation_exit_code: int,
    observation_status: str,
    artifact_root: Path = DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    observed_at: datetime,
) -> KisPaperIntradayHeadScheduleReceipt:
    """Write a terminal receipt without retaining provider, account, or order data.

    The collection process remains the authority for its own exit code. Once
    collection succeeds, the execution session's embedded prospective loop, and
    exact offline validation are all required to publish an allowlisted terminal
    outcome. The older observation remains explicitly optional for this QQQ
    cycle. `preview` remains accepted only for immutable historical receipts.
    """

    _require_safe_id(run_id, "run id")
    _require_exit_codes(
        collection_exit_code,
        prospective_loop_exit_code,
        prospective_session_exit_code,
        prospective_validation_exit_code,
        observation_exit_code,
    )
    _require_status(prospective_loop_status, _LOOP_STATUSES, "prospective loop")
    _require_status(prospective_session_status, _SESSION_STATUSES, "prospective session")
    _require_status(prospective_validation_status, _VALIDATION_STATUSES, "prospective validation")
    _require_status(observation_status, _OBSERVATION_STATUSES, "observation")
    _require_optional_safe_id(prospective_session_id, "prospective session id")
    _require_optional_safe_id(
        prospective_validation_session_id,
        "prospective validation session id",
    )

    terminal_status, recovery_class, scheduler_exit_code = _terminal_outcome(
        collection_exit_code=collection_exit_code,
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
    )
    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    result = KisPaperIntradayHeadScheduleReceipt(
        run_id=run_id,
        observed_at=require_utc(observed_at, "observed_at"),
        collection_exit_code=collection_exit_code,
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
        observation_exit_code=observation_exit_code,
        observation_status=observation_status,
        terminal_status=terminal_status,
        recovery_class=recovery_class,
        scheduler_exit_code=scheduler_exit_code,
        evidence_path=(
            root / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY / f"{run_id}.json"
        ),
    )
    _write_json_atomically(result.evidence_path, result.safe_payload())
    return result


def _terminal_outcome(
    *,
    collection_exit_code: int,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
) -> tuple[str, str, int]:
    if collection_exit_code != 0:
        return "recovery", "collection_exit_nonzero", collection_exit_code

    recovery_class = _first_downstream_recovery_class(
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
    )
    if recovery_class is None:
        return "complete", "complete", 0
    return "recovery", recovery_class, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


def _first_downstream_recovery_class(
    *,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
) -> str | None:
    if prospective_loop_exit_code != 0:
        return "prospective_loop_exit_nonzero"
    if prospective_loop_status not in {"embedded", "preview", "no_intent"}:
        return "prospective_loop_payload_unavailable"
    if prospective_session_exit_code != 0:
        return "prospective_session_exit_nonzero"
    if prospective_session_status not in {"no_intent", "canary_completed"}:
        return "prospective_session_payload_unavailable"
    if prospective_session_id is None:
        return "prospective_session_id_unavailable"
    if prospective_validation_exit_code != 0:
        return "prospective_validation_exit_nonzero"
    if prospective_validation_status != "validated":
        return "prospective_validation_payload_unavailable"
    if prospective_validation_session_id != prospective_session_id:
        return "prospective_validation_session_mismatch"
    return None


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    root = Path(artifact_root).resolve()
    repository = Path(repository_root).resolve()
    mounted_artifact_root = root == repository / "model_artifacts" and root.is_mount()
    if (root.is_relative_to(repository) and not mounted_artifact_root) or root.is_symlink():
        raise ValueError("schedule receipt root must stay outside Git")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_json_atomically(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="ascii") != rendered:
            raise ValueError("schedule receipt evidence identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    try:
        if path.exists():
            if path.read_text(encoding="ascii") != rendered:
                raise ValueError("schedule receipt evidence identity conflicts")
            return
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _require_exit_codes(*values: int) -> None:
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("schedule stage exit codes must be non-negative integers")


def _require_safe_id(value: str, name: str) -> None:
    if _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")


def _require_optional_safe_id(value: str | None, name: str) -> None:
    if value is not None:
        _require_safe_id(value, name)


def _require_status(value: str, allowed: frozenset[str], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{name} status is invalid")


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "observed_at").isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("observed_at must be a UTC timestamp") from error
    if parsed.tzinfo is not UTC:
        raise argparse.ArgumentTypeError("observed_at must be a UTC timestamp")
    return require_utc(parsed, "observed_at")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write source-safe terminal evidence for one intraday-head dispatch"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--collection-exit-code", type=int, required=True)
    parser.add_argument("--prospective-loop-exit-code", type=int, required=True)
    parser.add_argument("--prospective-loop-status", required=True)
    parser.add_argument("--prospective-session-exit-code", type=int, required=True)
    parser.add_argument("--prospective-session-status", required=True)
    parser.add_argument("--prospective-session-id")
    parser.add_argument("--prospective-validation-exit-code", type=int, required=True)
    parser.add_argument("--prospective-validation-status", required=True)
    parser.add_argument("--prospective-validation-session-id")
    parser.add_argument("--observation-exit-code", type=int, required=True)
    parser.add_argument("--observation-status", required=True)
    parser.add_argument("--observed-at", type=_parse_utc, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = write_kis_paper_intraday_head_schedule_receipt(
        run_id=args.run_id,
        collection_exit_code=args.collection_exit_code,
        prospective_loop_exit_code=args.prospective_loop_exit_code,
        prospective_loop_status=args.prospective_loop_status,
        prospective_session_exit_code=args.prospective_session_exit_code,
        prospective_session_status=args.prospective_session_status,
        prospective_session_id=args.prospective_session_id,
        prospective_validation_exit_code=args.prospective_validation_exit_code,
        prospective_validation_status=args.prospective_validation_status,
        prospective_validation_session_id=args.prospective_validation_session_id,
        observation_exit_code=args.observation_exit_code,
        observation_status=args.observation_status,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        observed_at=args.observed_at,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()
