"""Read the current D1 pairing outcome without network or raw-data output."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_d1_prospective_observation_pairing import (
    KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS,
    KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_ROOT,
    KisPaperD1ProspectiveObservationPairingError,
    read_current_kis_paper_d1_prospective_observation_pairing_outcome,
)

_RECEIPTS_DIRECTORY = "receipts"
_SAFE_READER_REASONS = frozenset(
    {
        "artifact_root_invalid",
        "artifact_root_unavailable",
        "current_pointer_invalid",
        "current_pointer_unavailable",
        "current_receipt_unavailable",
        "receipt_directory_unavailable",
        "receipt_invalid",
        "receipt_unavailable",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read the current D1 pairing outcome")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_ROOT,
        help="model artifact root or the exact D1 pairing receipt root",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    artifact_root = _model_artifact_root(args.artifact_root)
    try:
        outcome = read_current_kis_paper_d1_prospective_observation_pairing_outcome(
            artifact_root=artifact_root,
            repository_root=args.repository_root,
        )
        payload = _safe_payload(outcome, artifact_root=artifact_root)
    except KisPaperD1ProspectiveObservationPairingError as error:
        payload = _unavailable_payload(str(error))
    print(json.dumps(payload, sort_keys=True))


def _model_artifact_root(path: Path) -> Path:
    parts = KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS
    suffix = tuple(part.casefold() for part in path.parts[-len(parts) :])
    if suffix == tuple(part.casefold() for part in parts):
        return path.parents[len(parts) - 1]
    return path


def _safe_payload(
    outcome: Mapping[str, object],
    *,
    artifact_root: Path,
) -> dict[str, object]:
    receipt_id = outcome.get("receipt_id")
    pairing_root = artifact_root.joinpath(
        *KIS_PAPER_D1_PROSPECTIVE_OBSERVATION_PAIRING_ARTIFACT_PARTS
    )
    receipt_path = (
        str(pairing_root / _RECEIPTS_DIRECTORY / f"{receipt_id}.json")
        if isinstance(receipt_id, str)
        else None
    )
    payload = {
        "first_receipt_binding": _safe_first_receipt_binding(outcome),
        "next_due_at_utc": outcome.get("next_due_at_utc"),
        "observed_at_utc": outcome.get("observed_at_utc"),
        "reason": outcome.get("reason"),
        "receipt_id": receipt_id,
        "receipt_path": receipt_path,
        "receipt_sha256": outcome.get("receipt_sha256"),
        "session_key": outcome.get("session_key"),
        "source_contract_sha256": outcome.get("source_contract_sha256"),
        "stage": outcome.get("stage"),
        "status": outcome.get("status"),
    }
    failure_codes = outcome.get("observation_failure_codes")
    if failure_codes:
        payload["observation_failure_codes"] = failure_codes
    return payload


def _safe_first_receipt_binding(outcome: Mapping[str, object]) -> dict[str, str] | None:
    binding = outcome.get("first_receipt_binding")
    if not isinstance(binding, Mapping):
        return None
    receipt_id = binding.get("receipt_id")
    receipt_sha256 = binding.get("receipt_sha256")
    if not isinstance(receipt_id, str) or not isinstance(receipt_sha256, str):
        return None
    return {
        "receipt_id": receipt_id,
        "receipt_sha256": receipt_sha256,
    }


def _unavailable_payload(reason: str) -> dict[str, object]:
    return {
        "first_receipt_binding": None,
        "next_due_at_utc": None,
        "observed_at_utc": None,
        "reason": reason if reason in _SAFE_READER_REASONS else "reader_unavailable",
        "receipt_id": None,
        "receipt_path": None,
        "receipt_sha256": None,
        "session_key": None,
        "source_contract_sha256": None,
        "stage": None,
        "status": "unavailable",
    }


if __name__ == "__main__":
    main()
