"""Source-safe readiness bridge for the future profiled-MTF campaign.

The bridge accepts only Data's aggregate forward-outcome inventory. It never
opens the immutable snapshot that the Data lane may retain for a later,
separately frozen predictive campaign.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_mtf_profiled_prospective_observer import (
    KisMtfProfiledForwardOutcomeInventory,
)

from .artifact_paths import ensure_external_artifact_directory, reject_repo_artifact_path

PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID: Final = "profiled-mtf-forward-campaign-readiness-v1"
PROFILED_MTF_FORWARD_CAMPAIGN_PROFILE_ID: Final = "short"
PROFILED_MTF_FORWARD_CAMPAIGN_REQUIRED_PAIR_COUNT: Final = 30
PROFILED_MTF_FORWARD_CAMPAIGN_TEMPORAL_SPLIT: Final = (20, 2, 8)
PROFILED_MTF_FORWARD_CAMPAIGN_ROUND_TRIP_COST_BPS: Final = 20
PROFILED_MTF_FORWARD_CAMPAIGN_CUDA_MAX_SECONDS: Final = 600
_SHA256_PREFIX: Final = "sha256:"
_ATTEMPT_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]{1,80}$", re.ASCII)

ReadinessStatus = Literal["input_unavailable", "ready_for_private_campaign_freeze"]


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCampaignShape:
    """The predeclared shape, not an opened target or training campaign."""

    profile_id: str = PROFILED_MTF_FORWARD_CAMPAIGN_PROFILE_ID
    required_pair_count: int = PROFILED_MTF_FORWARD_CAMPAIGN_REQUIRED_PAIR_COUNT
    train_pair_count: int = PROFILED_MTF_FORWARD_CAMPAIGN_TEMPORAL_SPLIT[0]
    purge_pair_count: int = PROFILED_MTF_FORWARD_CAMPAIGN_TEMPORAL_SPLIT[1]
    validation_pair_count: int = PROFILED_MTF_FORWARD_CAMPAIGN_TEMPORAL_SPLIT[2]
    round_trip_cost_bps: int = PROFILED_MTF_FORWARD_CAMPAIGN_ROUND_TRIP_COST_BPS
    naive_baseline: str = "no_trade"
    kill_test: str = "blocked_session_target_permutation"
    cpu_first: bool = True
    cuda_max_seconds: int = PROFILED_MTF_FORWARD_CAMPAIGN_CUDA_MAX_SECONDS

    def __post_init__(self) -> None:
        if (
            self.profile_id != PROFILED_MTF_FORWARD_CAMPAIGN_PROFILE_ID
            or self.required_pair_count != PROFILED_MTF_FORWARD_CAMPAIGN_REQUIRED_PAIR_COUNT
            or (
                self.train_pair_count,
                self.purge_pair_count,
                self.validation_pair_count,
            )
            != PROFILED_MTF_FORWARD_CAMPAIGN_TEMPORAL_SPLIT
            or self.train_pair_count + self.purge_pair_count + self.validation_pair_count
            != self.required_pair_count
            or self.round_trip_cost_bps != PROFILED_MTF_FORWARD_CAMPAIGN_ROUND_TRIP_COST_BPS
            or self.naive_baseline != "no_trade"
            or self.kill_test != "blocked_session_target_permutation"
            or self.cpu_first is not True
            or self.cuda_max_seconds != PROFILED_MTF_FORWARD_CAMPAIGN_CUDA_MAX_SECONDS
        ):
            raise ValueError("profiled MTF forward campaign shape is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "instrument_scope": "fixed_two_leg_us_equity_pair",
            "required_pair_count": self.required_pair_count,
            "temporal_allocation": {
                "train_pair_count": self.train_pair_count,
                "purge_pair_count": self.purge_pair_count,
                "validation_pair_count": self.validation_pair_count,
            },
            "round_trip_cost_bps": self.round_trip_cost_bps,
            "naive_baseline": self.naive_baseline,
            "kill_test": self.kill_test,
            "cpu_first": self.cpu_first,
            "cuda_max_seconds": self.cuda_max_seconds,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCampaignReadinessPolicy:
    """An immutable policy bound to one Data outcome-contract identity."""

    forward_outcome_contract_sha256: str
    code_revision_sha256: str
    shape: ProfiledMtfForwardCampaignShape
    policy_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.forward_outcome_contract_sha256)
            or not _is_sha256(self.code_revision_sha256)
            or self.policy_sha256
            != _sha256_json(
                {
                    "campaign_id": PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID,
                    "forward_outcome_contract_sha256": self.forward_outcome_contract_sha256,
                    "code_revision_sha256": self.code_revision_sha256,
                    "shape": self.shape.safe_payload(),
                }
            )
        ):
            raise ValueError("profiled MTF forward campaign readiness policy is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID,
            "forward_outcome_contract_sha256": self.forward_outcome_contract_sha256,
            "code_revision_sha256": self.code_revision_sha256,
            "shape": self.shape.safe_payload(),
            "policy_sha256": self.policy_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCampaignReadiness:
    """One source-safe, non-promoting result over an opaque Data inventory."""

    policy_sha256: str
    forward_outcome_contract_sha256: str
    source_inventory_sha256: str
    target_ready_manifest_sha256: str
    target_ready_pair_count: int
    source_status: Literal["zero_target_ready", "target_ready"]
    status: ReadinessStatus
    readiness_sha256: str

    def __post_init__(self) -> None:
        expected_status: ReadinessStatus = (
            "ready_for_private_campaign_freeze"
            if self.target_ready_pair_count >= PROFILED_MTF_FORWARD_CAMPAIGN_REQUIRED_PAIR_COUNT
            else "input_unavailable"
        )
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.policy_sha256,
                    self.forward_outcome_contract_sha256,
                    self.source_inventory_sha256,
                    self.target_ready_manifest_sha256,
                    self.readiness_sha256,
                )
            )
            or type(self.target_ready_pair_count) is not int
            or self.target_ready_pair_count < 0
            or self.source_status not in {"zero_target_ready", "target_ready"}
            or (self.target_ready_pair_count > 0) != (self.source_status == "target_ready")
            or self.status != expected_status
            or self.readiness_sha256
            != _readiness_sha256(
                policy_sha256=self.policy_sha256,
                forward_outcome_contract_sha256=self.forward_outcome_contract_sha256,
                source_inventory_sha256=self.source_inventory_sha256,
                target_ready_manifest_sha256=self.target_ready_manifest_sha256,
                target_ready_pair_count=self.target_ready_pair_count,
                source_status=self.source_status,
                status=self.status,
            )
        ):
            raise ValueError("profiled MTF forward campaign readiness is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID,
            "policy_sha256": self.policy_sha256,
            "forward_outcome_contract_sha256": self.forward_outcome_contract_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
            "target_ready_manifest_sha256": self.target_ready_manifest_sha256,
            "target_ready_pair_count": self.target_ready_pair_count,
            "source_status": self.source_status,
            "status": self.status,
            "scope": _readiness_scope(),
            "readiness_sha256": self.readiness_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCampaignReadinessReceipt:
    """An external immutable receipt for the exact inventory/policy pairing."""

    policy: ProfiledMtfForwardCampaignReadinessPolicy = field(repr=False)
    readiness: ProfiledMtfForwardCampaignReadiness = field(repr=False)
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.receipt_sha256)
            or self.receipt_path.name != "readiness-receipt.json"
            or self.receipt_path.is_symlink()
            or self.readiness.policy_sha256 != self.policy.policy_sha256
            or (
                self.readiness.forward_outcome_contract_sha256
                != self.policy.forward_outcome_contract_sha256
            )
        ):
            raise ValueError("profiled MTF forward readiness receipt is invalid")


def freeze_profiled_mtf_forward_campaign_readiness_policy(
    *,
    forward_outcome_contract_sha256: str,
    code_revision_sha256: str,
) -> ProfiledMtfForwardCampaignReadinessPolicy:
    """Freeze the fixed shape before looking at Data's count."""

    _require_sha256(forward_outcome_contract_sha256, "forward_outcome_contract_sha256")
    _require_sha256(code_revision_sha256, "code_revision_sha256")
    shape = ProfiledMtfForwardCampaignShape()
    fields = {
        "campaign_id": PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID,
        "forward_outcome_contract_sha256": forward_outcome_contract_sha256,
        "code_revision_sha256": code_revision_sha256,
        "shape": shape.safe_payload(),
    }
    return ProfiledMtfForwardCampaignReadinessPolicy(
        forward_outcome_contract_sha256=forward_outcome_contract_sha256,
        code_revision_sha256=code_revision_sha256,
        shape=shape,
        policy_sha256=_sha256_json(fields),
    )


def evaluate_profiled_mtf_forward_campaign_readiness(
    policy: ProfiledMtfForwardCampaignReadinessPolicy,
    inventory: KisMtfProfiledForwardOutcomeInventory,
) -> ProfiledMtfForwardCampaignReadiness:
    """Classify an opaque inventory without opening its snapshots or labels."""

    normalized_inventory = _validated_inventory(inventory)
    if normalized_inventory.contract_sha256 != policy.forward_outcome_contract_sha256:
        raise ValueError("forward campaign readiness inventory contract is stale or mismatched")
    source_inventory_sha256 = _inventory_sha256(normalized_inventory)
    status: ReadinessStatus = (
        "ready_for_private_campaign_freeze"
        if normalized_inventory.target_ready_pair_count >= policy.shape.required_pair_count
        else "input_unavailable"
    )
    fields = {
        "policy_sha256": policy.policy_sha256,
        "forward_outcome_contract_sha256": normalized_inventory.contract_sha256,
        "source_inventory_sha256": source_inventory_sha256,
        "target_ready_manifest_sha256": normalized_inventory.target_ready_manifest_sha256,
        "target_ready_pair_count": normalized_inventory.target_ready_pair_count,
        "source_status": normalized_inventory.status,
        "status": status,
    }
    return ProfiledMtfForwardCampaignReadiness(
        **fields,
        readiness_sha256=_readiness_sha256(**fields),
    )


def reattest_profiled_mtf_forward_campaign_readiness(
    readiness: ProfiledMtfForwardCampaignReadiness,
    *,
    policy: ProfiledMtfForwardCampaignReadinessPolicy,
    inventory: KisMtfProfiledForwardOutcomeInventory,
) -> None:
    """Reject a receipt whose opaque inventory identity has moved."""

    if readiness.policy_sha256 != policy.policy_sha256:
        raise ValueError("forward campaign readiness policy changed")
    if evaluate_profiled_mtf_forward_campaign_readiness(policy, inventory) != readiness:
        raise ValueError("forward campaign readiness receipt is stale")


def profiled_mtf_forward_campaign_inventory_sha256(
    inventory: KisMtfProfiledForwardOutcomeInventory,
) -> str:
    """Expose the canonical source-safe inventory identity to a later reader."""

    return _inventory_sha256(_validated_inventory(inventory))


def write_profiled_mtf_forward_campaign_readiness_receipt(
    readiness: ProfiledMtfForwardCampaignReadiness,
    *,
    policy: ProfiledMtfForwardCampaignReadinessPolicy,
    artifact_root: Path | str,
    repo_root: Path | str,
    attempt_id: str,
) -> ProfiledMtfForwardCampaignReadinessReceipt:
    """Write one idempotent source-safe receipt outside the repository."""

    _require_attempt_id(attempt_id)
    if (
        readiness.policy_sha256 != policy.policy_sha256
        or readiness.forward_outcome_contract_sha256 != policy.forward_outcome_contract_sha256
    ):
        raise ValueError("forward campaign readiness does not match its policy")
    directory = ensure_external_artifact_directory(
        Path(artifact_root),
        Path(repo_root),
        "research",
        PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID,
        attempt_id,
    )
    unsigned_payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID,
        "attempt_id": attempt_id,
        "policy": policy.safe_payload(),
        "readiness": readiness.safe_payload(),
        "artifact_policy": {
            "repository_storage_allowed": False,
            "raw_rows_persisted": False,
            "feature_values_persisted": False,
            "target_values_persisted": False,
            "predictions_persisted": False,
            "weights_persisted": False,
        },
    }
    payload = {**unsigned_payload, "receipt_sha256": _sha256_json(unsigned_payload)}
    receipt_path = directory / "readiness-receipt.json"
    recorded = _write_or_verify_json(receipt_path, payload)
    return ProfiledMtfForwardCampaignReadinessReceipt(
        policy=policy,
        readiness=readiness,
        receipt_path=receipt_path,
        receipt_sha256=_required_sha256_payload(recorded, "receipt_sha256"),
    )


def load_profiled_mtf_forward_campaign_readiness_receipt(
    receipt_path: Path | str,
    *,
    repo_root: Path | str,
) -> ProfiledMtfForwardCampaignReadinessReceipt:
    """Load one canonical external receipt without reopening Data snapshots."""

    path = Path(receipt_path)
    reject_repo_artifact_path(path, Path(repo_root))
    if path.is_symlink() or not path.is_file():
        raise ValueError("forward campaign readiness receipt is missing or invalid")
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("forward campaign readiness receipt is malformed") from error
    if not isinstance(payload, dict) or encoded != _canonical_json(payload):
        raise ValueError("forward campaign readiness receipt is malformed")
    if (
        set(payload)
        != {
            "schema_version",
            "campaign_id",
            "attempt_id",
            "policy",
            "readiness",
            "artifact_policy",
            "receipt_sha256",
        }
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("campaign_id") != PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID
        or not isinstance(payload.get("attempt_id"), str)
    ):
        raise ValueError("forward campaign readiness receipt is malformed")
    _require_attempt_id(payload["attempt_id"])
    receipt_sha256 = _required_sha256_payload(payload, "receipt_sha256")
    unsigned = dict(payload)
    unsigned.pop("receipt_sha256")
    if receipt_sha256 != _sha256_json(unsigned):
        raise ValueError("forward campaign readiness receipt checksum is invalid")
    if payload.get("artifact_policy") != _artifact_policy():
        raise ValueError("forward campaign readiness receipt artifact policy is invalid")
    policy = _policy_from_safe_payload(_required_mapping(payload, "policy"))
    readiness = _readiness_from_safe_payload(_required_mapping(payload, "readiness"))
    return ProfiledMtfForwardCampaignReadinessReceipt(
        policy=policy,
        readiness=readiness,
        receipt_path=path,
        receipt_sha256=receipt_sha256,
    )


def _validated_inventory(
    inventory: KisMtfProfiledForwardOutcomeInventory,
) -> KisMtfProfiledForwardOutcomeInventory:
    if not isinstance(inventory, KisMtfProfiledForwardOutcomeInventory):
        raise ValueError("forward campaign readiness requires a Data inventory")
    return KisMtfProfiledForwardOutcomeInventory(
        contract_sha256=inventory.contract_sha256,
        target_ready_pair_count=inventory.target_ready_pair_count,
        target_ready_manifest_sha256=inventory.target_ready_manifest_sha256,
        status=inventory.status,
    )


def _inventory_sha256(inventory: KisMtfProfiledForwardOutcomeInventory) -> str:
    return _sha256_json(
        {
            "contract_sha256": inventory.contract_sha256,
            "target_ready_pair_count": inventory.target_ready_pair_count,
            "target_ready_manifest_sha256": inventory.target_ready_manifest_sha256,
            "status": inventory.status,
        }
    )


def _readiness_sha256(
    *,
    policy_sha256: str,
    forward_outcome_contract_sha256: str,
    source_inventory_sha256: str,
    target_ready_manifest_sha256: str,
    target_ready_pair_count: int,
    source_status: str,
    status: str,
) -> str:
    return _sha256_json(
        {
            "policy_sha256": policy_sha256,
            "forward_outcome_contract_sha256": forward_outcome_contract_sha256,
            "source_inventory_sha256": source_inventory_sha256,
            "target_ready_manifest_sha256": target_ready_manifest_sha256,
            "target_ready_pair_count": target_ready_pair_count,
            "source_status": source_status,
            "status": status,
        }
    )


def _readiness_scope() -> dict[str, bool]:
    return {
        "source_safe_inventory_only": True,
        "raw_snapshots_opened": False,
        "feature_values_opened": False,
        "target_or_return_values_opened": False,
        "model_trained": False,
        "gpu_allocated": False,
        "paper_input": False,
        "pnl_or_profitability_claim": False,
        "live_behavior": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "repository_storage_allowed": False,
        "raw_rows_persisted": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "predictions_persisted": False,
        "weights_persisted": False,
    }


def _policy_from_safe_payload(
    payload: Mapping[str, object],
) -> ProfiledMtfForwardCampaignReadinessPolicy:
    if set(payload) != {
        "campaign_id",
        "forward_outcome_contract_sha256",
        "code_revision_sha256",
        "shape",
        "policy_sha256",
    } or payload.get("campaign_id") != PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID:
        raise ValueError("forward campaign readiness policy is malformed")
    return ProfiledMtfForwardCampaignReadinessPolicy(
        forward_outcome_contract_sha256=_required_string(
            payload, "forward_outcome_contract_sha256"
        ),
        code_revision_sha256=_required_string(payload, "code_revision_sha256"),
        shape=_shape_from_safe_payload(_required_mapping(payload, "shape")),
        policy_sha256=_required_string(payload, "policy_sha256"),
    )


def _shape_from_safe_payload(payload: Mapping[str, object]) -> ProfiledMtfForwardCampaignShape:
    if set(payload) != {
        "profile_id",
        "instrument_scope",
        "required_pair_count",
        "temporal_allocation",
        "round_trip_cost_bps",
        "naive_baseline",
        "kill_test",
        "cpu_first",
        "cuda_max_seconds",
    } or payload.get("instrument_scope") != "fixed_two_leg_us_equity_pair":
        raise ValueError("forward campaign readiness shape is malformed")
    temporal = _required_mapping(payload, "temporal_allocation")
    if set(temporal) != {
        "train_pair_count",
        "purge_pair_count",
        "validation_pair_count",
    }:
        raise ValueError("forward campaign readiness temporal allocation is malformed")
    cpu_first = payload.get("cpu_first")
    if type(cpu_first) is not bool:
        raise ValueError("forward campaign readiness shape is malformed")
    return ProfiledMtfForwardCampaignShape(
        profile_id=_required_string(payload, "profile_id"),
        required_pair_count=_required_int(payload, "required_pair_count"),
        train_pair_count=_required_int(temporal, "train_pair_count"),
        purge_pair_count=_required_int(temporal, "purge_pair_count"),
        validation_pair_count=_required_int(temporal, "validation_pair_count"),
        round_trip_cost_bps=_required_int(payload, "round_trip_cost_bps"),
        naive_baseline=_required_string(payload, "naive_baseline"),
        kill_test=_required_string(payload, "kill_test"),
        cpu_first=cpu_first,
        cuda_max_seconds=_required_int(payload, "cuda_max_seconds"),
    )


def _readiness_from_safe_payload(
    payload: Mapping[str, object],
) -> ProfiledMtfForwardCampaignReadiness:
    if set(payload) != {
        "campaign_id",
        "policy_sha256",
        "forward_outcome_contract_sha256",
        "source_inventory_sha256",
        "target_ready_manifest_sha256",
        "target_ready_pair_count",
        "source_status",
        "status",
        "scope",
        "readiness_sha256",
    } or (
        payload.get("campaign_id") != PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID
        or payload.get("scope") != _readiness_scope()
    ):
        raise ValueError("forward campaign readiness payload is malformed")
    return ProfiledMtfForwardCampaignReadiness(
        policy_sha256=_required_string(payload, "policy_sha256"),
        forward_outcome_contract_sha256=_required_string(
            payload, "forward_outcome_contract_sha256"
        ),
        source_inventory_sha256=_required_string(payload, "source_inventory_sha256"),
        target_ready_manifest_sha256=_required_string(
            payload, "target_ready_manifest_sha256"
        ),
        target_ready_pair_count=_required_int(payload, "target_ready_pair_count"),
        source_status=_required_string(payload, "source_status"),
        status=_required_string(payload, "status"),
        readiness_sha256=_required_string(payload, "readiness_sha256"),
    )


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    if path.is_symlink():
        raise ValueError("forward campaign readiness receipt path must not be a link")
    encoded = _canonical_json(payload)
    if path.exists():
        existing = _read_json_object(path)
        if _canonical_json(existing) != encoded:
            raise ValueError("forward campaign readiness receipt conflicts with its attempt")
        return existing
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded.decode("utf-8"))
    except FileExistsError:
        return _write_or_verify_json(path, payload)
    return dict(payload)


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("forward campaign readiness receipt is malformed") from error
    if not isinstance(payload, dict):
        raise ValueError("forward campaign readiness receipt must be an object")
    return payload


def _required_sha256_payload(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    _require_sha256(value, field_name)
    return value


def _required_mapping(payload: Mapping[str, object], field_name: str) -> Mapping[str, object]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _required_string(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _required_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if type(value) is not int:
        raise ValueError(f"{field_name} must be an integer")
    return value


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_json(payload: Mapping[str, object]) -> str:
    return _SHA256_PREFIX + hashlib.sha256(_canonical_json(payload)).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _require_sha256(value: object, field_name: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{field_name} must be a SHA-256 identity")


def _require_attempt_id(value: str) -> None:
    if _ATTEMPT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("forward campaign readiness attempt_id is invalid")
