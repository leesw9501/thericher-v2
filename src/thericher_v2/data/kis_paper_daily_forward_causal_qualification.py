"""Fail-closed causal qualification for the private QQQ/SPY D1 forward cache.

This module reads only the existing external cache and one explicitly named
source-safe collection receipt. It never constructs a KIS client, reads local
configuration, or reaches an execution path. Raw daily rows are used only in
memory for structural checks and are never exposed in a payload or receipt.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.kis_paper_daily_history_panel import (
    has_complete_us_equity_session_coverage,
)
from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ID,
    KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT,
    KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_VERSION,
    KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS,
    KisPaperDailyPairForwardCache,
    load_verified_kis_paper_daily_pair_forward_cache,
)
from thericher_v2.research.artifact_paths import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    ensure_external_artifact_directory,
)

KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_ID = (
    "kis-daily-forward-causal-qualification-v1"
)
KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_RECEIPT_DIRECTORY = (
    "kis-daily-forward-causal-qualification-v1"
)
KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_PARENT_DIRECTORY = (
    "kis-paper-daily-pair-forward-v1"
)
KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_CONDITION_IDS = (
    "source_pair_identity",
    "complete_bar_calendar_continuity",
    "named_clock_session_rule",
    "non_overlapping_chronological_boundary",
    "decision_time_availability",
    "provider_finality",
)

KisDailyForwardCausalConditionId = Literal[
    "source_pair_identity",
    "complete_bar_calendar_continuity",
    "named_clock_session_rule",
    "non_overlapping_chronological_boundary",
    "decision_time_availability",
    "provider_finality",
]
KisDailyForwardCausalConditionStatus = Literal[
    "satisfied", "not_observed", "not_satisfied"
]
KisDailyForwardCausalQualificationStatus = Literal["qualified", "input_unavailable"]

_CONDITION_STATUSES = frozenset({"satisfied", "not_observed", "not_satisfied"})
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SOURCE_SAFE_FORBIDDEN_KEYS = frozenset(
    {
        "account",
        "bars",
        "close",
        "credentials",
        "high",
        "low",
        "open",
        "order",
        "orders",
        "position",
        "price",
        "prices",
        "raw_row",
        "raw_rows",
        "rows",
        "volume",
    }
)


class KisDailyForwardCausalQualificationError(ValueError):
    """The source-safe D1 forward qualification boundary could not be proven."""


@dataclass(frozen=True, slots=True)
class KisDailyForwardCausalCondition:
    """One explicit causal-input condition with no market-value payload."""

    condition_id: KisDailyForwardCausalConditionId
    status: KisDailyForwardCausalConditionStatus

    def __post_init__(self) -> None:
        if (
            self.condition_id not in KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_CONDITION_IDS
            or self.status not in _CONDITION_STATUSES
        ):
            raise KisDailyForwardCausalQualificationError("causal condition is invalid")

    def safe_payload(self) -> dict[str, str]:
        return {"condition_id": self.condition_id, "status": self.status}


@dataclass(frozen=True, slots=True)
class KisDailyForwardCausalQualificationEvidence:
    """Source-safe evidence passed to the deterministic qualification rule."""

    cache_id: str
    cache_version: str
    cache_index_sha256: str
    cache_sha256: str
    frozen_boundary: date
    forward_common_session_count: int
    forward_common_sessions_sha256: str
    parent_receipt_sha256: str
    parent_receipt_relative_path: str
    conditions: tuple[KisDailyForwardCausalCondition, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "conditions", tuple(self.conditions))
        if (
            self.cache_id != KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ID
            or self.cache_version != KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_VERSION
            or not _is_sha256(self.cache_index_sha256)
            or not _is_sha256(self.cache_sha256)
            or type(self.frozen_boundary) is not date
            or self.forward_common_session_count < 0
            or not _is_sha256(self.forward_common_sessions_sha256)
            or not _is_sha256(self.parent_receipt_sha256)
            or not _is_safe_relative_path(self.parent_receipt_relative_path)
            or tuple(item.condition_id for item in self.conditions)
            != KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_CONDITION_IDS
            or self.schema_version != SCHEMA_VERSION
        ):
            raise KisDailyForwardCausalQualificationError(
                "causal qualification evidence is invalid"
            )

    def source_payload(self) -> dict[str, object]:
        return {
            "cache_id": self.cache_id,
            "cache_version": self.cache_version,
            "cache_index_sha256": self.cache_index_sha256,
            "cache_sha256": self.cache_sha256,
            "frozen_boundary": self.frozen_boundary.isoformat(),
            "forward_common_session_count": self.forward_common_session_count,
            "forward_common_sessions_sha256": self.forward_common_sessions_sha256,
            "parent_receipt": {
                "relative_path": self.parent_receipt_relative_path,
                "sha256": self.parent_receipt_sha256,
            },
        }


@dataclass(frozen=True, slots=True)
class KisDailyForwardCausalQualificationResult:
    """A deterministic, source-safe classification with no downstream authority."""

    evidence: KisDailyForwardCausalQualificationEvidence
    status: KisDailyForwardCausalQualificationStatus
    missing_condition_ids: tuple[KisDailyForwardCausalConditionId, ...]
    qualification_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_condition_ids", tuple(self.missing_condition_ids))
        expected_missing = tuple(
            condition.condition_id
            for condition in self.evidence.conditions
            if condition.status != "satisfied"
        )
        expected_status: KisDailyForwardCausalQualificationStatus = (
            "qualified" if not expected_missing else "input_unavailable"
        )
        if (
            self.status != expected_status
            or self.missing_condition_ids != expected_missing
            or not _is_sha256(self.qualification_sha256)
            or self.schema_version != SCHEMA_VERSION
            or self.qualification_sha256 != _qualification_hash(self.evidence, self.status)
        ):
            raise KisDailyForwardCausalQualificationError("causal qualification result is invalid")

    def safe_payload(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "kind": KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_ID,
            "status": self.status,
            "qualification_sha256": self.qualification_sha256,
            "source": self.evidence.source_payload(),
            "conditions": [condition.safe_payload() for condition in self.evidence.conditions],
            "missing_condition_ids": list(self.missing_condition_ids),
            "limits": {
                "network_access": False,
                "credentials_read": False,
                "kis_client_constructed": False,
                "docker_or_scheduler_invoked": False,
                "broker_or_paper_action": False,
                "gpu_used": False,
                "raw_market_data_in_receipt": False,
                "research_or_execution_consumer_allowed": False,
            },
        }
        _assert_source_safe(payload)
        return payload


@dataclass(frozen=True, slots=True)
class KisDailyForwardCausalQualificationReceipt:
    """The immutable external receipt produced for one labeled qualification."""

    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if not self.receipt_path.is_absolute() or not _is_sha256(self.receipt_sha256):
            raise KisDailyForwardCausalQualificationError("causal qualification receipt is invalid")


@dataclass(frozen=True, slots=True)
class _ParentReceipt:
    cache_index_sha256: str
    cache_sha256: str
    frozen_boundary: date
    parent_receipt_sha256: str
    parent_receipt_relative_path: str


def evaluate_kis_daily_forward_causal_qualification(
    evidence: KisDailyForwardCausalQualificationEvidence,
) -> KisDailyForwardCausalQualificationResult:
    """Classify only the explicit evidence conditions; unknowns fail closed."""

    missing = tuple(
        condition.condition_id
        for condition in evidence.conditions
        if condition.status != "satisfied"
    )
    status: KisDailyForwardCausalQualificationStatus = (
        "qualified" if not missing else "input_unavailable"
    )
    return KisDailyForwardCausalQualificationResult(
        evidence=evidence,
        status=status,
        missing_condition_ids=missing,
        qualification_sha256=_qualification_hash(evidence, status),
    )


def qualify_current_kis_paper_daily_pair_forward_cache(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT,
    parent_receipt_path: Path | str,
    artifact_root: Path | str = DEFAULT_MODEL_ARTIFACT_ROOT,
    repository_root: Path | str | None = None,
) -> KisDailyForwardCausalQualificationResult:
    """Reattest the current cache and classify only facts it actually proves."""

    repository = Path(repository_root or Path.cwd()).resolve(strict=False)
    artifact = _require_external_artifact_root(Path(artifact_root), repository)
    cache = load_verified_kis_paper_daily_pair_forward_cache(
        cache_root=cache_root,
        repo_root=repository,
    )
    parent = _load_parent_receipt(
        receipt_path=Path(parent_receipt_path),
        artifact_root=artifact,
    )
    safe_cache = cache.safe_payload()
    evidence = KisDailyForwardCausalQualificationEvidence(
        cache_id=str(safe_cache["kind"]),
        cache_version=str(safe_cache["version"]),
        cache_index_sha256=cache.index_hash,
        cache_sha256=cache.cache_hash,
        frozen_boundary=cache.frozen_boundary,
        forward_common_session_count=len(cache.common_sessions),
        forward_common_sessions_sha256=str(safe_cache["forward_common_sessions_sha256"]),
        parent_receipt_sha256=parent.parent_receipt_sha256,
        parent_receipt_relative_path=parent.parent_receipt_relative_path,
        conditions=(
            KisDailyForwardCausalCondition(
                "source_pair_identity",
                _source_pair_identity_status(cache, parent),
            ),
            KisDailyForwardCausalCondition(
                "complete_bar_calendar_continuity",
                _calendar_continuity_status(cache),
            ),
            KisDailyForwardCausalCondition("named_clock_session_rule", "not_observed"),
            KisDailyForwardCausalCondition(
                "non_overlapping_chronological_boundary",
                _chronological_boundary_status(cache, parent),
            ),
            KisDailyForwardCausalCondition("decision_time_availability", "not_observed"),
            KisDailyForwardCausalCondition("provider_finality", "not_observed"),
        ),
    )
    return evaluate_kis_daily_forward_causal_qualification(evidence)


def write_kis_daily_forward_causal_qualification_receipt(
    *,
    result: KisDailyForwardCausalQualificationResult,
    artifact_root: Path | str = DEFAULT_MODEL_ARTIFACT_ROOT,
    repository_root: Path | str | None = None,
    run_label: str,
) -> KisDailyForwardCausalQualificationReceipt:
    """Persist exactly one immutable source-safe result below the external root."""

    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise KisDailyForwardCausalQualificationError("qualification run label is invalid")
    repository = Path(repository_root or Path.cwd()).resolve(strict=False)
    root = ensure_external_artifact_directory(
        Path(artifact_root),
        repository,
        "data",
        KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_RECEIPT_DIRECTORY,
        f"run={run_label}",
    )
    target = root / "receipt.json"
    if target.exists() or target.is_symlink():
        raise KisDailyForwardCausalQualificationError("qualification receipt already exists")
    payload = _canonical_json_bytes(result.safe_payload())
    try:
        with target.open("xb") as handle:
            handle.write(payload)
    except OSError as error:
        raise KisDailyForwardCausalQualificationError(
            "qualification receipt is unavailable"
        ) from error
    return KisDailyForwardCausalQualificationReceipt(
        receipt_path=target.resolve(strict=True),
        receipt_sha256=_sha256(payload),
    )


def _source_pair_identity_status(
    cache: KisPaperDailyPairForwardCache,
    parent: _ParentReceipt,
) -> KisDailyForwardCausalConditionStatus:
    expected_targets = tuple(
        f"{symbol}/{exchange}"
        for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
    )
    if (
        tuple(cache.rows_by_target) != expected_targets
        or tuple(cache.targets_by_key) != expected_targets
        or parent.cache_sha256 != cache.cache_hash
        or parent.cache_index_sha256 != cache.index_hash
    ):
        return "not_satisfied"
    return "satisfied"


def _calendar_continuity_status(
    cache: KisPaperDailyPairForwardCache,
) -> KisDailyForwardCausalConditionStatus:
    if not cache.common_sessions or any(
        not cache.rows_by_target[target_key]
        for target_key in tuple(cache.rows_by_target)
    ):
        return "not_satisfied"
    try:
        return (
            "satisfied"
            if has_complete_us_equity_session_coverage(cache.common_sessions)
            else "not_satisfied"
        )
    except ValueError:
        return "not_observed"


def _chronological_boundary_status(
    cache: KisPaperDailyPairForwardCache,
    parent: _ParentReceipt,
) -> KisDailyForwardCausalConditionStatus:
    if parent.frozen_boundary != cache.frozen_boundary:
        return "not_satisfied"
    if any(
        row.session_date <= cache.frozen_boundary
        for rows in cache.rows_by_target.values()
        for row in rows
    ):
        return "not_satisfied"
    return "satisfied"


def _load_parent_receipt(*, receipt_path: Path, artifact_root: Path) -> _ParentReceipt:
    path = _require_direct_parent_receipt_path(receipt_path, artifact_root)
    try:
        encoded = path.read_bytes()
        document = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisDailyForwardCausalQualificationError("parent receipt is unreadable") from error
    if not isinstance(document, dict) or set(document) != {
        "kind",
        "observed_at_bucket",
        "payload",
        "artifact_policy",
    }:
        raise KisDailyForwardCausalQualificationError("parent receipt schema is invalid")
    if encoded != _canonical_json_bytes(document):
        raise KisDailyForwardCausalQualificationError("parent receipt is not canonical")
    payload = document["payload"]
    policy = document["artifact_policy"]
    if (
        document["kind"] != "kis_paper_daily_pair_forward_receipt"
        or not isinstance(document["observed_at_bucket"], str)
        or not isinstance(payload, Mapping)
        or not isinstance(policy, Mapping)
    ):
        raise KisDailyForwardCausalQualificationError("parent receipt scope is invalid")
    _assert_source_safe(document)
    _validate_parent_policy(policy)
    cache_payload = payload.get("cache")
    if not isinstance(cache_payload, Mapping):
        raise KisDailyForwardCausalQualificationError("parent receipt cache is unavailable")
    cache_index_sha256, cache_sha256, frozen_boundary = _validate_parent_cache_payload(
        cache_payload
    )
    relative = path.relative_to(artifact_root).as_posix()
    return _ParentReceipt(
        cache_index_sha256=cache_index_sha256,
        cache_sha256=cache_sha256,
        frozen_boundary=frozen_boundary,
        parent_receipt_sha256=_sha256(encoded),
        parent_receipt_relative_path=relative,
    )


def _validate_parent_policy(policy: Mapping[str, object]) -> None:
    expected = {
        "raw_market_data_in_receipt": False,
        "credentials_in_receipt": False,
        "account_data_in_receipt": False,
        "repo_storage_allowed": False,
    }
    if dict(policy) != expected:
        raise KisDailyForwardCausalQualificationError("parent receipt policy is invalid")


def _validate_parent_cache_payload(payload: Mapping[str, object]) -> tuple[str, str, date]:
    required = {
        "kind",
        "version",
        "frozen_boundary",
        "index_sha256",
        "cache_sha256",
        "forward_common_session_count",
        "forward_common_sessions_sha256",
        "targets",
        "source",
        "raw_rows_persisted",
        "raw_rows_in_payload",
        "credentials_in_payload",
        "account_or_order_data_in_payload",
    }
    if not required.issubset(payload):
        raise KisDailyForwardCausalQualificationError("parent receipt cache schema is invalid")
    try:
        frozen_boundary = date.fromisoformat(str(payload["frozen_boundary"]))
    except ValueError as error:
        raise KisDailyForwardCausalQualificationError(
            "parent receipt boundary is invalid"
        ) from error
    cache_index_sha256 = payload["index_sha256"]
    cache_sha256 = payload["cache_sha256"]
    source = payload["source"]
    targets = payload["targets"]
    expected_source_targets = [
        {"symbol": symbol, "exchange": exchange}
        for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
    ]
    if (
        payload["kind"] != KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ID
        or payload["version"] != KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_VERSION
        or not _is_sha256(cache_index_sha256)
        or not _is_sha256(cache_sha256)
        or type(payload["forward_common_session_count"]) is not int
        or int(payload["forward_common_session_count"]) < 0
        or not _is_sha256(payload["forward_common_sessions_sha256"])
        or not isinstance(source, Mapping)
        or source.get("provider") != "KIS Open API virtual paper"
        or source.get("endpoint") != "dailyprice"
        or source.get("targets") != expected_source_targets
        or not isinstance(targets, list)
        or len(targets) != len(KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS)
        or payload["raw_rows_persisted"] is not True
        or payload["raw_rows_in_payload"] is not False
        or payload["credentials_in_payload"] is not False
        or payload["account_or_order_data_in_payload"] is not False
    ):
        raise KisDailyForwardCausalQualificationError("parent receipt cache scope is invalid")
    return str(cache_index_sha256), str(cache_sha256), frozen_boundary


def _require_direct_parent_receipt_path(path: Path, artifact_root: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise KisDailyForwardCausalQualificationError("parent receipt path is invalid")
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(artifact_root)
    except ValueError as error:
        raise KisDailyForwardCausalQualificationError(
            "parent receipt is outside artifacts"
        ) from error
    if (
        len(relative.parts) != 4
        or relative.parts[0] != "data"
        or relative.parts[1] != KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_PARENT_DIRECTORY
        or relative.parts[3] != "receipt.json"
        or not relative.parts[2].startswith("run=")
    ):
        raise KisDailyForwardCausalQualificationError("parent receipt path is not direct")
    current = artifact_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise KisDailyForwardCausalQualificationError("parent receipt path is not direct")
    return resolved


def _require_external_artifact_root(root: Path, repository: Path) -> Path:
    return ensure_external_artifact_directory(root, repository)


def _qualification_hash(
    evidence: KisDailyForwardCausalQualificationEvidence,
    status: KisDailyForwardCausalQualificationStatus,
) -> str:
    return _sha256_json(
        {
            "kind": KIS_DAILY_FORWARD_CAUSAL_QUALIFICATION_ID,
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "source": evidence.source_payload(),
            "conditions": [condition.safe_payload() for condition in evidence.conditions],
        }
    )


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _SOURCE_SAFE_FORBIDDEN_KEYS:
                raise KisDailyForwardCausalQualificationError("receipt contains source values")
            _assert_source_safe(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_source_safe(nested)


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (canonical + "\n").encode("utf-8")


def _sha256_json(value: Mapping[str, object]) -> str:
    return _sha256(_canonical_json_bytes(value))


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _is_safe_relative_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts
