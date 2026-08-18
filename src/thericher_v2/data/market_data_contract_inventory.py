"""Source-safe inventory of the current external market-data contracts.

This module deliberately reads only directory/file existence metadata for a
small allowlist plus source-safe receipt bytes.  It never opens a market-data
file, loads credentials, or creates a consumer beyond the categorical status
recorded here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
DEFAULT_RECEIPT_ROOT = DEFAULT_ARTIFACT_ROOT / "data-receipts" / "market-data-contract-inventory"
MARKET_DATA_CONTRACT_INVENTORY_ID = "market-data-contract-inventory-v1"
SCHEMA_VERSION = 1
_SAFE_LABEL = re.compile(r"[A-Za-z0-9_-]{1,100}", re.ASCII)

SourceClass = Literal[
    "kis_m1",
    "kis_d1",
    "firstrate_free_m1",
    "tiingo_etf_d1",
    "tiingo_iex_m5",
    "norgate_trial",
]
Presence = Literal["present", "unavailable"]
ConsumerStatus = Literal[
    "input_unavailable",
    "source_local_mechanics_only",
    "retrospective_control_only",
    "non_promoting_runtime_only",
]

_SOURCE_CLASSES: tuple[SourceClass, ...] = (
    "kis_m1",
    "kis_d1",
    "firstrate_free_m1",
    "tiingo_etf_d1",
    "tiingo_iex_m5",
    "norgate_trial",
)
_CONSUMER_STATUSES = frozenset(
    {
        "input_unavailable",
        "source_local_mechanics_only",
        "retrospective_control_only",
        "non_promoting_runtime_only",
    }
)


@dataclass(frozen=True)
class SourceFootprint:
    """Fixed source-safe locations for exactly one source class."""

    source_class: SourceClass
    metadata_root: Path
    receipt_relative_path: Path
    eligible_status: ConsumerStatus


DEFAULT_FOOTPRINTS: tuple[SourceFootprint, ...] = (
    SourceFootprint(
        "kis_m1",
        Path(r"D:\market_data\us_equities\fixed_etf_intraday"),
        Path(
            "execution/kis-paper-intraday-head-schedule/intraday-head-20260818T2120005941479Z.json"
        ),
        "input_unavailable",
    ),
    SourceFootprint(
        "kis_d1",
        Path(r"D:\market_data\us_equities\kis_overseas_daily"),
        Path(
            "data/kis-paper-daily-nas-broad-panel-postrun-v1/postrun-5b24100dc992a4fed2848593.json"
        ),
        "input_unavailable",
    ),
    SourceFootprint(
        "firstrate_free_m1",
        Path(r"D:\market_data\us_equities\firstrate_free_intraday\canonical"),
        Path(
            "data-receipts/firstrate-free-intraday/firstrate-free-intraday-source-local-normalization-v1.json"
        ),
        "source_local_mechanics_only",
    ),
    SourceFootprint(
        "tiingo_etf_d1",
        Path(r"D:\market_data\us_equities\tiingo_etf_daily"),
        Path(
            "data-receipts/tiingo-etf-d1/4a2344b7ab8ec2eaf0b1a5e4afcd41e07cf0b4c14e13db64d07b41fd054883d2.json"
        ),
        "retrospective_control_only",
    ),
    SourceFootprint(
        "tiingo_iex_m5",
        Path(r"D:\market_data\us_equities\fixed_etf_intraday"),
        Path(
            "research/tiingo-iex-r1-representation-integration-v1/r1-cuda-20260810-r1/summary.json"
        ),
        "non_promoting_runtime_only",
    ),
    SourceFootprint(
        "norgate_trial",
        Path(r"D:\market_data\us_equities\norgate_us_platinum_trial"),
        Path(
            "data-receipts/norgate-host-readiness-bridge/bridge-norgate-host-readiness-20260818T230439Z.json"
        ),
        "input_unavailable",
    ),
)


@dataclass(frozen=True)
class SourceContractEntry:
    """One fixed categorical consumer contract; no source content is retained."""

    source_class: SourceClass
    presence: Presence
    evidence_relative_path: str
    evidence_sha256: str | None
    consumer_status: ConsumerStatus

    def __post_init__(self) -> None:
        if (
            self.source_class not in _SOURCE_CLASSES
            or self.presence not in {"present", "unavailable"}
            or self.consumer_status not in _CONSUMER_STATUSES
            or not _safe_relative_path(self.evidence_relative_path)
            or (self.evidence_sha256 is not None and not _is_sha256(self.evidence_sha256))
        ):
            raise ValueError("market-data contract entry is invalid")
        if self.presence == "present" and self.evidence_sha256 is None:
            raise ValueError("present market-data contract needs evidence")
        if self.presence == "unavailable" and self.consumer_status != "input_unavailable":
            raise ValueError("unavailable market-data contract must be unavailable")

    def safe_payload(self) -> dict[str, object]:
        return {
            "source_class": self.source_class,
            "presence": self.presence,
            "evidence_binding": {
                "receipt_relative_path": self.evidence_relative_path,
                "receipt_sha256": self.evidence_sha256,
            },
            "consumer_status": self.consumer_status,
        }


@dataclass(frozen=True)
class MarketDataContractInventory:
    """Aggregate categorical inventory and its immutable receipt binding."""

    receipt_path: Path
    receipt_sha256: str
    entries: tuple[SourceContractEntry, ...]

    def categorical_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(entry.consumer_status for entry in self.entries).items()))

    def safe_payload(self) -> dict[str, object]:
        return {
            "receipt_sha256": self.receipt_sha256,
            "categorical_counts": self.categorical_counts(),
            "source_classes": [entry.source_class for entry in self.entries],
        }


def build_market_data_contract_inventory(
    *,
    inventory_label: str,
    retrieved_at_utc: datetime,
    artifact_root: Path | str = DEFAULT_ARTIFACT_ROOT,
    footprints: Sequence[SourceFootprint] = DEFAULT_FOOTPRINTS,
    repo_root: Path | str | None = None,
) -> MarketDataContractInventory:
    """Inspect only fixed directory metadata and safe receipt bytes, then write once."""

    root = _require_external_root(artifact_root, repo_root=repo_root)
    label = _safe_label(inventory_label)
    entries = _build_entries(root=root, footprints=footprints)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": MARKET_DATA_CONTRACT_INVENTORY_ID,
        "inventory_label": label,
        "retrieved_at_utc": _utc_isoformat(retrieved_at_utc),
        "entries": [entry.safe_payload() for entry in entries],
        "categorical_counts": dict(
            sorted(Counter(entry.consumer_status for entry in entries).items())
        ),
        "safety": {
            "credentials_read": False,
            "network_access": False,
            "raw_market_data_read": False,
            "raw_market_data_hashed": False,
            "kis_or_broker_called": False,
            "model_gpu_or_paper_used": False,
            "task_scheduler_called": False,
        },
        "limitations": [
            "directory_metadata_and_source_safe_receipts_only",
            "not_a_predictive_paper_or_gpu_input",
            "consumer_eligibility_is_scoped_to_each_source_class",
        ],
    }
    target = root / "data-receipts" / "market-data-contract-inventory" / f"{label}.json"
    _write_or_verify(target, payload)
    return MarketDataContractInventory(
        receipt_path=target,
        receipt_sha256=_sha256(target.read_bytes()),
        entries=entries,
    )


def read_market_data_contract_inventory(
    *,
    source: Path | str,
    artifact_root: Path | str = DEFAULT_ARTIFACT_ROOT,
    repo_root: Path | str | None = None,
) -> MarketDataContractInventory:
    """Reattach an inventory receipt using only its source-safe JSON payload."""

    root = _require_external_root(artifact_root, repo_root=repo_root)
    target = _inventory_receipt_path(source, root=root)
    if target.is_symlink() or not target.is_file():
        raise ValueError("market-data contract inventory receipt is unavailable")
    try:
        document = json.loads(target.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("market-data contract inventory receipt is invalid") from exc
    entries = _validate_document(document)
    return MarketDataContractInventory(
        receipt_path=target,
        receipt_sha256=_sha256(target.read_bytes()),
        entries=entries,
    )


def _build_entries(
    *, root: Path, footprints: Sequence[SourceFootprint]
) -> tuple[SourceContractEntry, ...]:
    _validate_footprints(footprints)
    entries: list[SourceContractEntry] = []
    for footprint in footprints:
        receipt = (root / footprint.receipt_relative_path).resolve(strict=False)
        if not receipt.is_relative_to(root):
            raise ValueError("market-data contract receipt pointer escapes artifact root")
        present = _is_plain_directory(footprint.metadata_root) and _is_plain_file(receipt)
        entries.append(
            SourceContractEntry(
                source_class=footprint.source_class,
                presence="present" if present else "unavailable",
                evidence_relative_path=footprint.receipt_relative_path.as_posix(),
                evidence_sha256=_sha256(receipt.read_bytes()) if present else None,
                consumer_status=footprint.eligible_status if present else "input_unavailable",
            )
        )
    return tuple(entries)


def _validate_footprints(footprints: Sequence[SourceFootprint]) -> None:
    if tuple(item.source_class for item in footprints) != _SOURCE_CLASSES:
        raise ValueError("market-data contract footprints must be fixed and ordered")
    for item in footprints:
        if item.eligible_status not in _CONSUMER_STATUSES or not _safe_relative_path(
            item.receipt_relative_path.as_posix()
        ):
            raise ValueError("market-data contract footprint is invalid")


def _validate_document(document: object) -> tuple[SourceContractEntry, ...]:
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "receipt_id",
        "inventory_label",
        "retrieved_at_utc",
        "entries",
        "categorical_counts",
        "safety",
        "limitations",
    }:
        raise ValueError("market-data contract inventory schema is invalid")
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["receipt_id"] != MARKET_DATA_CONTRACT_INVENTORY_ID
    ):
        raise ValueError("market-data contract inventory identity is invalid")
    if not isinstance(document["inventory_label"], str) or not _SAFE_LABEL.fullmatch(
        document["inventory_label"]
    ):
        raise ValueError("market-data contract inventory label is invalid")
    if not isinstance(document["retrieved_at_utc"], str):
        raise ValueError("market-data contract inventory timestamp is invalid")
    try:
        timestamp = datetime.fromisoformat(document["retrieved_at_utc"])
    except ValueError as exc:
        raise ValueError("market-data contract inventory timestamp is invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(None):
        raise ValueError("market-data contract inventory timestamp is invalid")
    entries_value = document["entries"]
    if not isinstance(entries_value, list) or len(entries_value) != len(_SOURCE_CLASSES):
        raise ValueError("market-data contract inventory entries are invalid")
    entries = tuple(_entry_from_payload(value) for value in entries_value)
    if tuple(entry.source_class for entry in entries) != _SOURCE_CLASSES:
        raise ValueError("market-data contract inventory source order is invalid")
    expected_counts = dict(sorted(Counter(entry.consumer_status for entry in entries).items()))
    if document["categorical_counts"] != expected_counts:
        raise ValueError("market-data contract inventory counts are invalid")
    expected_safety = {
        "credentials_read": False,
        "network_access": False,
        "raw_market_data_read": False,
        "raw_market_data_hashed": False,
        "kis_or_broker_called": False,
        "model_gpu_or_paper_used": False,
        "task_scheduler_called": False,
    }
    if document["safety"] != expected_safety:
        raise ValueError("market-data contract inventory safety is invalid")
    if document["limitations"] != [
        "directory_metadata_and_source_safe_receipts_only",
        "not_a_predictive_paper_or_gpu_input",
        "consumer_eligibility_is_scoped_to_each_source_class",
    ]:
        raise ValueError("market-data contract inventory limitations are invalid")
    return entries


def _entry_from_payload(value: object) -> SourceContractEntry:
    if not isinstance(value, dict) or set(value) != {
        "source_class",
        "presence",
        "evidence_binding",
        "consumer_status",
    }:
        raise ValueError("market-data contract entry payload is invalid")
    binding = value["evidence_binding"]
    if not isinstance(binding, dict) or set(binding) != {"receipt_relative_path", "receipt_sha256"}:
        raise ValueError("market-data contract evidence binding is invalid")
    return SourceContractEntry(
        source_class=value["source_class"],
        presence=value["presence"],
        evidence_relative_path=binding["receipt_relative_path"],
        evidence_sha256=binding["receipt_sha256"],
        consumer_status=value["consumer_status"],
    )


def _require_external_root(value: Path | str, *, repo_root: Path | str | None) -> Path:
    root = Path(value).resolve(strict=False)
    repository = Path(repo_root).resolve(strict=False) if repo_root is not None else _REPO_ROOT
    if root.is_relative_to(repository):
        raise ValueError("market-data contract inventory artifact root must stay outside Git")
    return root


def _inventory_receipt_path(source: Path | str, *, root: Path) -> Path:
    candidate = Path(source)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (root / candidate).resolve(strict=False)
    )
    expected_parent = (root / "data-receipts" / "market-data-contract-inventory").resolve(
        strict=False
    )
    if (
        not resolved.is_relative_to(expected_parent)
        or resolved.suffix != ".json"
        or not _SAFE_LABEL.fullmatch(resolved.stem)
    ):
        raise ValueError("market-data contract inventory receipt path is invalid")
    return resolved


def _is_plain_directory(path: Path) -> bool:
    return not path.is_symlink() and path.is_dir()


def _is_plain_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file()


def _safe_relative_path(value: str) -> bool:
    path = Path(value)
    return (
        bool(value) and not path.is_absolute() and ".." not in path.parts and path.suffix == ".json"
    )


def _is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _safe_label(value: str) -> str:
    if not _SAFE_LABEL.fullmatch(value):
        raise ValueError("market-data contract inventory label is invalid")
    return value


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("market-data contract inventory timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _write_or_verify(destination: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "ascii"
    )
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError(
                "market-data contract inventory receipt conflicts with immutable evidence"
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()
