"""Run one fixed offline D1 trio momentum falsification and emit safe evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from thericher_v2.data.norgate_d1_diagnostic_source import (
    load_verified_norgate_d1_diagnostic_panel,
)
from thericher_v2.research.norgate_d1_trio_momentum_falsification import (
    NorgateD1TrioMomentumResult,
    frozen_norgate_d1_trio_momentum_contract,
    run_norgate_d1_trio_momentum_falsification,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_CAMPAIGN_ID = "norgate-d1-trio-momentum-falsification-v1"
_CONTRACT_VERSION = "v1"
_EXPECTED_DATASET_HASH = "sha256:efa1b14ff60c6a107688179617d428546de68ca1d1756c62292e1206e15c58e7"
_EXPECTED_MANIFEST_HASH = "sha256:7f30253d035f248889849b7a9a5933cdc41b2f2525b405690ef653ca69a33d45"
_RECEIPT_NAME = "validation-receipt.json"
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", re.ASCII)
_SOURCE_LIMITATIONS = (
    "source_local_offline_only",
    "requested_adjustment_setting_none_not_verified",
    "corporate_action_semantics_unverified",
    "availability_time_semantics_unverified",
    "point_in_time_semantics_unverified",
)


def main(argv: Sequence[str] | None = None) -> None:
    """Reattest the pinned panel, run it once, and emit only aggregate evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    arguments = parser.parse_args(argv)
    artifact_root = _validated_artifact_root(arguments.artifact_root, _REPOSITORY_ROOT)
    panel = load_verified_norgate_d1_diagnostic_panel(
        arguments.snapshot,
        expected_dataset_hash=_EXPECTED_DATASET_HASH,
        expected_manifest_hash=_EXPECTED_MANIFEST_HASH,
        repo_root=_REPOSITORY_ROOT,
    )
    result = run_norgate_d1_trio_momentum_falsification(panel.bars_by_symbol)
    if not isinstance(result, NorgateD1TrioMomentumResult):
        raise TypeError("D1 trio momentum runner requires its typed result")
    receipt = _receipt_payload(result)
    encoded = _canonical_json(receipt)
    receipt_path = _receipt_path(
        artifact_root=artifact_root,
        run_label=_validated_segment(arguments.run_label),
    )
    _write_or_verify(receipt_path, encoded)
    print(
        json.dumps(
            {
                "campaign_id": receipt["campaign_id"],
                "contract_hash": receipt["contract"]["hash"],
                "receipt_sha256": _sha256(encoded),
                "status": receipt["outcome"]["status"],
                "validation": receipt["outcome"]["target_free"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def _receipt_payload(result: NorgateD1TrioMomentumResult) -> dict[str, object]:
    outcome = result.safe_payload()
    if outcome.get("campaign_id") != _CAMPAIGN_ID:
        raise ValueError("D1 trio momentum result identity is invalid")
    contract = frozen_norgate_d1_trio_momentum_contract()
    if contract.get("campaign_id") != _CAMPAIGN_ID:
        raise ValueError("D1 trio momentum contract identity is invalid")
    return {
        "schema_version": 1,
        "kind": "norgate_d1_trio_momentum_falsification_validation_receipt",
        "campaign_id": _CAMPAIGN_ID,
        "contract": {
            "version": _CONTRACT_VERSION,
            "hash": _sha256(_canonical_json(contract)),
        },
        "source": {
            "dataset_hash": _EXPECTED_DATASET_HASH,
            "manifest_hash": _EXPECTED_MANIFEST_HASH,
            "limitations": list(_SOURCE_LIMITATIONS),
        },
        "outcome": outcome,
        "raw_market_data_written": False,
        "promotion_allowed": False,
        "paper_input_allowed": False,
        "profitability_claim_allowed": False,
    }


def _receipt_path(*, artifact_root: Path, run_label: str) -> Path:
    destination = artifact_root / "research" / _CAMPAIGN_ID / run_label / _RECEIPT_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    parent = destination.parent.resolve(strict=False)
    if destination.parent.is_symlink() or not parent.is_relative_to(artifact_root):
        raise ValueError("D1 trio momentum receipt destination is invalid")
    return parent / _RECEIPT_NAME


def _validated_artifact_root(root: Path, repository: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved_repository = repository.resolve(strict=False)
    if resolved_root.is_relative_to(resolved_repository):
        raise ValueError("D1 trio momentum receipts must stay outside Git")
    if resolved_root.exists() and (resolved_root.is_symlink() or not resolved_root.is_dir()):
        raise ValueError("D1 trio momentum receipt root is invalid")
    resolved_root.mkdir(parents=True, exist_ok=True)
    return resolved_root.resolve(strict=False)


def _write_or_verify(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            raise ValueError("D1 trio momentum receipt conflicts with existing evidence")
        return
    stage = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage")
    try:
        stage.write_bytes(content)
        os.replace(stage, path)
    finally:
        stage.unlink(missing_ok=True)


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _validated_segment(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_SEGMENT.fullmatch(value):
        raise ValueError("D1 trio momentum run label is invalid")
    return value


if __name__ == "__main__":
    main()
