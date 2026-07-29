"""Append-only, source-safe custody records for frozen Research campaigns."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION

from .validation import _reject_repo_artifact_path, resolve_model_artifact_root

CAMPAIGN_REGISTRY_VERSION = 1
CAMPAIGN_FROZEN_RECORD_TYPE = "campaign_frozen"
CAMPAIGN_OUTCOME_RECORD_TYPE = "campaign_outcome"
_RECORD_TYPES = frozenset({CAMPAIGN_FROZEN_RECORD_TYPE, CAMPAIGN_OUTCOME_RECORD_TYPE})
_TRIAL_FAMILY_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,95}$")
_HOLDOUT_ACCESS = frozenset({"none", "sealed", "opened"})
_OUTCOME_CLASSES = frozenset(
    {"non_promoting_completed", "non_promoting_failed", "non_promoting_abandoned"}
)


class CampaignRegistryLockedError(RuntimeError):
    """Raised when another registry writer owns the short external lock."""


@dataclass(frozen=True, slots=True)
class FrozenCampaignRegistryEntry:
    """One idempotent frozen-contract record with a family-local trial index."""

    contract_hash: str
    dataset_hash: str
    split_hash: str
    cost_model_hash: str
    trial_family: str
    trial_index: int
    holdout_access: str
    recorded_at: datetime
    record_path: Path
    record_sha256: str


@dataclass(frozen=True, slots=True)
class CampaignOutcomeRegistryEntry:
    """One source-safe non-promoting terminal reference for a frozen contract."""

    contract_hash: str
    outcome_class: str
    outcome_reference_sha256: str
    recorded_at: datetime
    record_path: Path
    record_sha256: str


def register_frozen_campaign(
    *,
    contract_hash: str,
    dataset_hash: str,
    split_hash: str,
    cost_model_hash: str,
    trial_family: str,
    holdout_access: Literal["none", "sealed", "opened"],
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
    recorded_at: datetime | None = None,
) -> FrozenCampaignRegistryEntry:
    """Append one immutable campaign record or reattach its exact existing record."""

    identity = _campaign_identity(
        contract_hash=contract_hash,
        dataset_hash=dataset_hash,
        split_hash=split_hash,
        cost_model_hash=cost_model_hash,
        trial_family=trial_family,
        holdout_access=holdout_access,
    )
    now = _utc_datetime(recorded_at or datetime.now(UTC), "recorded_at")
    ledger_root = resolve_campaign_registry_root(
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    with _registry_lock(ledger_root):
        records = tuple(_iter_verified_records(ledger_root))
        existing = [
            (record, path)
            for record, path in records
            if record["record_type"] == CAMPAIGN_FROZEN_RECORD_TYPE
            and record["campaign_contract_hash"] == identity["campaign_contract_hash"]
        ]
        if existing:
            record, path = existing[0]
            if len(existing) != 1 or _frozen_identity(record) != identity:
                raise ValueError(
                    "campaign contract hash conflicts with an existing registry record"
                )
            return _frozen_entry_from_record(record, record_path=path)

        trial_index = 1 + sum(
            _same_trial_family(record, identity)
            for record, _path in records
            if record["record_type"] == CAMPAIGN_FROZEN_RECORD_TYPE
        )
        record = {
            "schema_version": SCHEMA_VERSION,
            "registry_version": CAMPAIGN_REGISTRY_VERSION,
            "record_type": CAMPAIGN_FROZEN_RECORD_TYPE,
            "record_id": f"campaign:{identity['campaign_contract_hash'][7:]}",
            "recorded_at": now.isoformat(),
            "role": "engine_research",
            **identity,
            "trial_index": trial_index,
            "promotion_eligible": False,
        }
        completed = _signed_record(record)
        path = _append_record(ledger_root, completed, recorded_at=now)
        return _frozen_entry_from_record(completed, record_path=path)


def register_campaign_outcome(
    *,
    contract_hash: str,
    outcome_class: Literal[
        "non_promoting_completed", "non_promoting_failed", "non_promoting_abandoned"
    ],
    outcome_reference_sha256: str,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
    recorded_at: datetime | None = None,
) -> CampaignOutcomeRegistryEntry:
    """Append one non-promoting outcome reference for a previously frozen contract."""

    _require_sha256(contract_hash, "campaign contract hash")
    if outcome_class not in _OUTCOME_CLASSES:
        raise ValueError("campaign outcome class is invalid")
    _require_sha256(outcome_reference_sha256, "outcome reference hash")
    now = _utc_datetime(recorded_at or datetime.now(UTC), "recorded_at")
    ledger_root = resolve_campaign_registry_root(
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    with _registry_lock(ledger_root):
        records = tuple(_iter_verified_records(ledger_root))
        if not any(
            record["record_type"] == CAMPAIGN_FROZEN_RECORD_TYPE
            and record["campaign_contract_hash"] == contract_hash
            for record, _path in records
        ):
            raise ValueError("campaign outcome requires a frozen registry record")
        existing = [
            (record, path)
            for record, path in records
            if record["record_type"] == CAMPAIGN_OUTCOME_RECORD_TYPE
            and record["campaign_contract_hash"] == contract_hash
            and record["outcome_reference_sha256"] == outcome_reference_sha256
        ]
        if existing:
            record, path = existing[0]
            if len(existing) != 1 or record["outcome_class"] != outcome_class:
                raise ValueError(
                    "campaign outcome reference conflicts with an existing registry record"
                )
            return _outcome_entry_from_record(record, record_path=path)

        record = {
            "schema_version": SCHEMA_VERSION,
            "registry_version": CAMPAIGN_REGISTRY_VERSION,
            "record_type": CAMPAIGN_OUTCOME_RECORD_TYPE,
            "record_id": (
                f"outcome:{contract_hash[7:19]}:{outcome_reference_sha256[7:19]}"
            ),
            "recorded_at": now.isoformat(),
            "role": "engine_research",
            "campaign_contract_hash": contract_hash,
            "outcome_class": outcome_class,
            "outcome_reference_sha256": outcome_reference_sha256,
            "promotion_eligible": False,
        }
        completed = _signed_record(record)
        path = _append_record(ledger_root, completed, recorded_at=now)
        return _outcome_entry_from_record(completed, record_path=path)


def resolve_campaign_registry_root(
    *,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Resolve the external append-only ledger root without creating repo state."""

    root = Path(artifact_root or resolve_model_artifact_root())
    if not root.is_dir() or root.is_symlink():
        raise ValueError("model artifact root must be an existing non-symlink directory")
    _reject_repo_artifact_path(root, repo_root or Path.cwd())
    resolved_root = root.resolve()
    ledger_root = resolved_root / "_control" / "ledger"
    if ledger_root.exists() and ledger_root.is_symlink():
        raise ValueError("campaign registry ledger root must not be a symlink")
    ledger_root.mkdir(parents=True, exist_ok=True)
    return ledger_root


def _campaign_identity(
    *,
    contract_hash: str,
    dataset_hash: str,
    split_hash: str,
    cost_model_hash: str,
    trial_family: str,
    holdout_access: str,
) -> dict[str, str]:
    _require_sha256(contract_hash, "campaign contract hash")
    _require_sha256(dataset_hash, "dataset hash")
    _require_sha256(split_hash, "split hash")
    _require_sha256(cost_model_hash, "cost model hash")
    if not _TRIAL_FAMILY_PATTERN.fullmatch(trial_family):
        raise ValueError("trial family must be a safe lowercase identifier")
    if holdout_access not in _HOLDOUT_ACCESS:
        raise ValueError("holdout access is invalid")
    return {
        "campaign_contract_hash": contract_hash,
        "dataset_hash": dataset_hash,
        "split_hash": split_hash,
        "cost_model_hash": cost_model_hash,
        "trial_family": trial_family,
        "holdout_access": holdout_access,
    }


def _iter_verified_records(ledger_root: Path) -> Iterator[tuple[dict[str, Any], Path]]:
    for path in sorted(ledger_root.glob("*.jsonl"), key=lambda candidate: candidate.name):
        if not path.is_file() or path.is_symlink():
            raise ValueError("campaign registry ledger entry is invalid")
        for line_number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not text:
                raise ValueError("campaign registry contains a blank record")
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("campaign registry contains malformed JSON") from exc
            if not isinstance(record, dict):
                raise ValueError("campaign registry record must be an object")
            _validate_record(record, source=f"{path.name}:{line_number}")
            yield record, path


@contextmanager
def _registry_lock(ledger_root: Path) -> Iterator[None]:
    lock_path = ledger_root / ".campaign-registry.lock"
    try:
        descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise CampaignRegistryLockedError("campaign registry is owned by another writer") from exc
    try:
        os.write(descriptor, b"campaign-registry\n")
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _append_record(ledger_root: Path, record: Mapping[str, Any], *, recorded_at: datetime) -> Path:
    path = ledger_root / f"{recorded_at:%Y-%m}.jsonl"
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _signed_record(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload["record_sha256"] = _sha256_json(payload)
    return payload


def _validate_record(record: Mapping[str, Any], *, source: str) -> None:
    if (
        record.get("schema_version") != SCHEMA_VERSION
        or record.get("registry_version") != CAMPAIGN_REGISTRY_VERSION
        or record.get("record_type") not in _RECORD_TYPES
        or record.get("role") != "engine_research"
        or record.get("promotion_eligible") is not False
    ):
        raise ValueError(f"campaign registry record is invalid: {source}")
    _utc_datetime(record.get("recorded_at"), "registry recorded_at")
    _require_sha256(record.get("record_sha256"), "registry record hash")
    unsigned = dict(record)
    actual_hash = unsigned.pop("record_sha256")
    if _sha256_json(unsigned) != actual_hash:
        raise ValueError(f"campaign registry record hash mismatch: {source}")
    if record["record_type"] == CAMPAIGN_FROZEN_RECORD_TYPE:
        identity = _campaign_identity(
            contract_hash=record.get("campaign_contract_hash"),
            dataset_hash=record.get("dataset_hash"),
            split_hash=record.get("split_hash"),
            cost_model_hash=record.get("cost_model_hash"),
            trial_family=record.get("trial_family"),
            holdout_access=record.get("holdout_access"),
        )
        if (
            record.get("record_id") != f"campaign:{identity['campaign_contract_hash'][7:]}"
            or not isinstance(record.get("trial_index"), int)
            or record["trial_index"] <= 0
        ):
            raise ValueError(f"campaign registry frozen record is invalid: {source}")
        return
    _require_sha256(record.get("campaign_contract_hash"), "campaign contract hash")
    _require_sha256(record.get("outcome_reference_sha256"), "outcome reference hash")
    if record.get("outcome_class") not in _OUTCOME_CLASSES:
        raise ValueError(f"campaign registry outcome record is invalid: {source}")
    expected_id = (
        f"outcome:{record['campaign_contract_hash'][7:19]}:"
        f"{record['outcome_reference_sha256'][7:19]}"
    )
    if record.get("record_id") != expected_id:
        raise ValueError(f"campaign registry outcome record is invalid: {source}")


def _frozen_identity(record: Mapping[str, Any]) -> dict[str, str]:
    return _campaign_identity(
        contract_hash=record["campaign_contract_hash"],
        dataset_hash=record["dataset_hash"],
        split_hash=record["split_hash"],
        cost_model_hash=record["cost_model_hash"],
        trial_family=record["trial_family"],
        holdout_access=record["holdout_access"],
    )


def _same_trial_family(record: Mapping[str, Any], identity: Mapping[str, str]) -> bool:
    return all(
        record[key] == identity[key]
        for key in ("dataset_hash", "split_hash", "cost_model_hash", "trial_family")
    )


def _frozen_entry_from_record(
    record: Mapping[str, Any],
    *,
    record_path: Path,
) -> FrozenCampaignRegistryEntry:
    return FrozenCampaignRegistryEntry(
        contract_hash=record["campaign_contract_hash"],
        dataset_hash=record["dataset_hash"],
        split_hash=record["split_hash"],
        cost_model_hash=record["cost_model_hash"],
        trial_family=record["trial_family"],
        trial_index=record["trial_index"],
        holdout_access=record["holdout_access"],
        recorded_at=_utc_datetime(record["recorded_at"], "registry recorded_at"),
        record_path=record_path,
        record_sha256=record["record_sha256"],
    )


def _outcome_entry_from_record(
    record: Mapping[str, Any],
    *,
    record_path: Path,
) -> CampaignOutcomeRegistryEntry:
    return CampaignOutcomeRegistryEntry(
        contract_hash=record["campaign_contract_hash"],
        outcome_class=record["outcome_class"],
        outcome_reference_sha256=record["outcome_reference_sha256"],
        recorded_at=_utc_datetime(record["recorded_at"], "registry recorded_at"),
        record_path=record_path,
        record_sha256=record["record_sha256"],
    )


def _utc_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO datetime") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _require_sha256(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")
    return value


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
