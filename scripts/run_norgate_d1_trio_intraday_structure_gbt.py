"""Run one source-local, non-promoting Norgate D1 GBT discrimination preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from thericher_v2.data.norgate_active_build_revision import (
    DEFAULT_NORGATE_ACTIVE_BUILD_REVISION_ARTIFACT_ROOT,
    FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH,
    FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH,
    FROZEN_NORGATE_FIXED_TRIO_D1_SNAPSHOT_DIR,
    verify_norgate_active_build_revision_receipt,
)
from thericher_v2.data.norgate_d1_diagnostic_source import (
    load_verified_norgate_d1_diagnostic_panel,
)
from thericher_v2.data.norgate_trial_raw_d1 import DEFAULT_MARKET_DATA_ROOT
from thericher_v2.research.norgate_d1_trio_intraday_structure_gbt import (
    NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_PREFLIGHT_ID,
    NorgateD1TrioIntradayStructureGbtPreflightResult,
    frozen_norgate_d1_trio_intraday_structure_gbt_contract,
    run_norgate_d1_trio_intraday_structure_gbt_preflight,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_DEFAULT_CONTAINER_MARKET_DATA_ROOT = Path("/app/market_data")
_DEFAULT_REVISION_RECEIPT = (
    DEFAULT_NORGATE_ACTIVE_BUILD_REVISION_ARTIFACT_ROOT / "revision-active-build-20260802-r2"
)
_RECEIPT_NAME = "preflight-receipt.json"
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", re.ASCII)
_SOURCE_LIMITATIONS = (
    "source_local_offline_only",
    "requested_adjustment_setting_none_not_verified",
    "corporate_action_semantics_unverified",
    "availability_time_semantics_unverified",
    "point_in_time_semantics_unverified",
)


def main(argv: Sequence[str] | None = None) -> None:
    """Reattach the fixed input, run one CPU preflight, and write safe evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=FROZEN_NORGATE_FIXED_TRIO_D1_SNAPSHOT_DIR)
    parser.add_argument("--market-data-root", type=Path, default=_default_market_data_root())
    parser.add_argument("--revision-receipt", type=Path, default=_DEFAULT_REVISION_RECEIPT)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    arguments = parser.parse_args(argv)

    artifact_root = _validated_artifact_root(arguments.artifact_root, _REPOSITORY_ROOT)
    revision = verify_norgate_active_build_revision_receipt(
        arguments.revision_receipt,
        artifact_root=arguments.revision_receipt.parent,
        repo_root=_REPOSITORY_ROOT,
    )
    if (
        revision.status != "matching"
        or revision.reference_dataset_hash != FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH
        or revision.reference_manifest_hash != FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH
    ):
        raise ValueError("Norgate active-build revision receipt is not eligible for this preflight")
    panel = load_verified_norgate_d1_diagnostic_panel(
        arguments.snapshot,
        expected_dataset_hash=FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH,
        expected_manifest_hash=FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH,
        market_data_root=arguments.market_data_root,
        repo_root=_REPOSITORY_ROOT,
    )
    result = run_norgate_d1_trio_intraday_structure_gbt_preflight(panel.bars_by_symbol)
    receipt = _receipt_payload(result, revision_receipt_sha256=revision.receipt_sha256)
    encoded = _canonical_json(receipt)
    receipt_path = _receipt_path(
        artifact_root=artifact_root,
        run_label=_validated_segment(arguments.run_label),
    )
    _write_or_verify(receipt_path, encoded)
    outcome = receipt["outcome"]
    assert isinstance(outcome, Mapping)
    print(
        json.dumps(
            {
                "campaign_id": receipt["campaign_id"],
                "contract_sha256": receipt["contract"]["sha256"],
                "receipt_sha256": _sha256(encoded),
                "status": outcome["status"],
                "reason": outcome["reason"],
                "validation_date_group_count": outcome["validation_date_group_count"],
                "metrics": outcome["metrics"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def _receipt_payload(
    result: object,
    *,
    revision_receipt_sha256: str,
) -> dict[str, object]:
    canonical_result = _canonical_result(result)
    if not _is_sha256(revision_receipt_sha256):
        raise ValueError("Norgate active-build receipt hash is invalid")
    contract = frozen_norgate_d1_trio_intraday_structure_gbt_contract()
    contract_bytes = _canonical_json(contract)
    return {
        "schema_version": 1,
        "kind": "norgate_d1_trio_intraday_structure_gbt_preflight_receipt",
        "campaign_id": NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_PREFLIGHT_ID,
        "contract": {
            "sha256": _sha256(contract_bytes),
        },
        "source": {
            "dataset_hash": FROZEN_NORGATE_FIXED_TRIO_D1_DATASET_HASH,
            "manifest_hash": FROZEN_NORGATE_FIXED_TRIO_D1_MANIFEST_HASH,
            "active_build_revision_receipt_sha256": revision_receipt_sha256,
            "limitations": list(_SOURCE_LIMITATIONS),
        },
        "outcome": NorgateD1TrioIntradayStructureGbtPreflightResult.safe_payload(
            canonical_result
        ),
        "raw_market_data_written": False,
        "row_level_predictions_written": False,
        "model_weights_written": False,
        "network_access": False,
        "credential_access": False,
        "broker_access": False,
        "paper_input_allowed": False,
        "pnl_evaluated": False,
        "gpu_used": False,
    }


def _default_market_data_root() -> Path:
    if _REPOSITORY_ROOT == Path("/app"):
        return _DEFAULT_CONTAINER_MARKET_DATA_ROOT
    return DEFAULT_MARKET_DATA_ROOT


def _canonical_result(result: object) -> NorgateD1TrioIntradayStructureGbtPreflightResult:
    if type(result) is not NorgateD1TrioIntradayStructureGbtPreflightResult:
        raise TypeError("Norgate D1 intraday-structure runner requires its exact typed result")
    try:
        return NorgateD1TrioIntradayStructureGbtPreflightResult(
            status=result.status,
            reason=result.reason,
            development_row_count=result.development_row_count,
            validation_row_count=result.validation_row_count,
            validation_date_group_count=result.validation_date_group_count,
            feature_count=result.feature_count,
            always_flat_decision_count=result.always_flat_decision_count,
            actual_balanced_accuracy=result.actual_balanced_accuracy,
            always_long_balanced_accuracy=result.always_long_balanced_accuracy,
            null_p95_balanced_accuracy=result.null_p95_balanced_accuracy,
            one_session_shift_balanced_accuracy=result.one_session_shift_balanced_accuracy,
            effect_floor_met=result.effect_floor_met,
            null_threshold_met=result.null_threshold_met,
            alignment_control_passed=result.alignment_control_passed,
            schema_version=result.schema_version,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Norgate D1 intraday-structure result semantics are invalid") from exc


def _receipt_path(*, artifact_root: Path, run_label: str) -> Path:
    directory = (
        artifact_root
        / "research"
        / NORGATE_D1_TRIO_INTRADAY_STRUCTURE_GBT_PREFLIGHT_ID
        / run_label
    )
    directory.mkdir(parents=True, exist_ok=True)
    resolved_directory = directory.resolve(strict=False)
    if directory.is_symlink() or not resolved_directory.is_relative_to(artifact_root):
        raise ValueError("Norgate D1 intraday-structure receipt destination is invalid")
    return resolved_directory / _RECEIPT_NAME


def _validated_artifact_root(root: Path, repository: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved_repository = repository.resolve(strict=False)
    container_repository = Path("/app").resolve()
    container_artifacts = container_repository / "model_artifacts"
    is_container_mount = resolved_repository == container_repository and (
        resolved_root == container_artifacts or resolved_root.is_relative_to(container_artifacts)
    )
    if resolved_root.is_relative_to(resolved_repository) and not is_container_mount:
        raise ValueError("Norgate D1 intraday-structure artifacts must stay outside Git")
    if resolved_root.exists() and (resolved_root.is_symlink() or not resolved_root.is_dir()):
        raise ValueError("Norgate D1 intraday-structure artifact root is invalid")
    resolved_root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(resolved_root)
    if usage.total <= 0 or usage.free / usage.total < 0.15:
        raise ValueError("Norgate D1 intraday-structure artifact storage is below the floor")
    return resolved_root.resolve(strict=False)


def _write_or_verify(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            raise ValueError(
                "Norgate D1 intraday-structure receipt conflicts with existing evidence"
            )
        return
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        if path.is_symlink() or path.read_bytes() != content:
            raise ValueError(
                "Norgate D1 intraday-structure receipt conflicts with existing evidence"
            ) from exc
        return
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _validated_segment(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_SEGMENT.fullmatch(value):
        raise ValueError("Norgate D1 intraday-structure run label is invalid")
    return value


if __name__ == "__main__":
    main()
