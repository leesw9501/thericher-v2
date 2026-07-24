"""Metadata-only preparation for the first prospective KIS intraday observation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe, require_utc
from thericher_v2.data import (
    KisPaperPrivateIntradayV1RetainedChunkMetadata,
    raw_bar_end_is_complete,
    us_equity_2026_session,
    validate_kis_paper_private_intraday_v1_index_metadata,
)

KIS_INTRADAY_PROSPECTIVE_HEAD_OBSERVATION_ID = "kis-intraday-prospective-head-observation-r1"
KIS_INTRADAY_PROSPECTIVE_HEAD_CACHE_VERSION = "v1"
KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT = 5
KIS_INTRADAY_PROSPECTIVE_HEAD_REGULAR_SESSION_MINUTES = 390
KIS_INTRADAY_PROSPECTIVE_HEAD_FEATURE_WINDOWS = {
    "m1_completed_bars": 90,
    "m5_completed_bars": 18,
    "m10_completed_bars": 9,
}
KIS_INTRADAY_PROSPECTIVE_HEAD_CONTROLS = (
    "flat",
    "always_long",
    "previous_bar_direction",
    "regularized_linear",
)
KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES = (
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
)

_HEAD_TARGET_KEY = "QQQ/NAS/1m"
_HEAD_INDEX_FILENAME = "index.json"
_HEAD_EXPECTED_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


@dataclass(frozen=True)
class KisIntradayProspectiveHeadObservationContract:
    """The fixed prospective contract, recorded before later work consumes bars."""

    schema_version: int = SCHEMA_VERSION

    @property
    def contract_hash(self) -> str:
        return _sha256_payload(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "observation_id": KIS_INTRADAY_PROSPECTIVE_HEAD_OBSERVATION_ID,
            "source": {
                "cache": "independent_kis_intraday_head",
                "target_key": _HEAD_TARGET_KEY,
                "new_session_rule": "after_fixed_historical_development_prefix",
            },
            "historical_development_prefix": {
                "session_dates": [
                    session_date.isoformat()
                    for session_date in (
                        KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
                    )
                ],
                "session_count": len(
                    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
                ),
                "consumed_by_this_tool": False,
            },
            "prospective_observation": {
                "required_complete_regular_sessions": (
                    KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
                ),
                "regular_session_minutes": KIS_INTRADAY_PROSPECTIVE_HEAD_REGULAR_SESSION_MINUTES,
                "selection": "first_five_chronological_complete_head_sessions",
            },
            "feature_context": {
                **KIS_INTRADAY_PROSPECTIVE_HEAD_FEATURE_WINDOWS,
                "same_session_only": True,
            },
            "target": {
                "direction": "long_only",
                "decision": "completed_m1_bar_close",
                "entry": "next_m1_bar_open",
                "exit": "following_m1_bar_open",
                "cross_session_allowed": False,
            },
            "costs": {
                "fee_bps_per_side": "1",
                "slippage_bps_per_side": "2",
            },
            "controls": list(KIS_INTRADAY_PROSPECTIVE_HEAD_CONTROLS),
            "limits": {
                "metadata_only_preparation": True,
                "model_training": False,
                "bar_replay": False,
                "candidate_selection": False,
                "ensemble_selection": False,
                "candidate_promotion": False,
                "gpu_used": False,
                "network_access": False,
                "credentials_read": False,
            },
        }


@dataclass(frozen=True)
class KisIntradayProspectiveHeadObservationPreparation:
    """A retriable metadata result, never an approval or global collection latch."""

    contract: KisIntradayProspectiveHeadObservationContract
    status: Literal["pending", "prepared"]
    head_index_status: Literal["not_created", "available"]
    head_index_sha256: str | None
    available_complete_session_dates: tuple[date, ...]
    selected_session_dates: tuple[date, ...]
    precommit_path: Path | None = None
    planning_receipt_path: Path | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "available_complete_session_dates",
            tuple(self.available_complete_session_dates),
        )
        object.__setattr__(self, "selected_session_dates", tuple(self.selected_session_dates))
        if self.available_complete_session_dates != tuple(
            sorted(self.available_complete_session_dates)
        ):
            raise ValueError("prospective head sessions must be chronological")
        if self.selected_session_dates != self.available_complete_session_dates[
            :KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
        ]:
            raise ValueError("prospective head selection must use the first complete sessions")
        if self.status == "pending":
            if len(self.available_complete_session_dates) >= (
                KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
            ):
                raise ValueError("pending prospective head preparation already has enough sessions")
            if self.precommit_path is not None or self.planning_receipt_path is not None:
                raise ValueError("pending prospective head preparation cannot write artifacts")
        elif (
            len(self.selected_session_dates)
            != KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
            or self.precommit_path is None
            or self.planning_receipt_path is None
        ):
            raise ValueError("prepared prospective head observation is incomplete")

    @property
    def missing_session_count(self) -> int:
        return max(
            KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
            - len(self.available_complete_session_dates),
            0,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "pending_is_not_a_permission_latch": self.status == "pending",
            "head_index": {
                "status": self.head_index_status,
                "metadata_sha256": self.head_index_sha256,
                "target_key": _HEAD_TARGET_KEY,
            },
            "required_complete_session_count": (
                KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
            ),
            "available_complete_session_dates": [
                session_date.isoformat() for session_date in self.available_complete_session_dates
            ],
            "selected_session_dates": [
                session_date.isoformat() for session_date in self.selected_session_dates
            ],
            "missing_session_count": self.missing_session_count,
            "contract_hash": self.contract.contract_hash,
            "artifacts": {
                "precommit_path": (
                    None if self.precommit_path is None else str(self.precommit_path)
                ),
                "planning_receipt_path": (
                    None
                    if self.planning_receipt_path is None
                    else str(self.planning_receipt_path)
                ),
            },
        }


@dataclass(frozen=True)
class _HeadIndexInspection:
    """Validated head-index facts retained only while preparing the receipt."""

    status: Literal["not_created", "available"]
    metadata_sha256: str | None
    complete_session_dates: tuple[date, ...]
    first_seen_row_fingerprints: tuple[tuple[str, str], ...]


def prepare_kis_intraday_prospective_head_observation(
    *,
    head_cache_root: Path,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
    prepared_at: datetime | None = None,
) -> KisIntradayProspectiveHeadObservationPreparation:
    """Inspect head-index metadata and atomically precommit only when five sessions exist."""

    _validate_run_label(run_label)
    contract = KisIntradayProspectiveHeadObservationContract()
    inspection = _inspect_head_index_metadata(
        head_cache_root=Path(head_cache_root),
        repo_root=Path(repo_root or Path.cwd()),
    )
    index_status = inspection.status
    index_sha256 = inspection.metadata_sha256
    available_dates = inspection.complete_session_dates
    selected_dates = available_dates[:KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT]
    if len(selected_dates) < KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT:
        return KisIntradayProspectiveHeadObservationPreparation(
            contract=contract,
            status="pending",
            head_index_status=index_status,
            head_index_sha256=index_sha256,
            available_complete_session_dates=available_dates,
            selected_session_dates=selected_dates,
        )

    observed_at = require_utc(prepared_at or datetime.now(UTC), "prepared_at")
    artifact_slot_id = _artifact_slot_id(
        contract=contract,
        selected_session_dates=selected_dates,
    )
    selected_rows_fingerprint_sha256 = _selected_rows_fingerprint_sha256(
        first_seen_row_fingerprints=dict(inspection.first_seen_row_fingerprints),
        selected_session_dates=selected_dates,
    )
    precommit_payload = _precommit_payload(
        contract=contract,
        head_index_status=index_status,
        head_index_sha256=index_sha256,
        selected_session_dates=selected_dates,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
        prepared_at=observed_at,
    )
    precommit_hash = _sha256_payload(precommit_payload)
    precommit_payload["precommit_hash"] = precommit_hash
    receipt_payload = _planning_receipt_payload(
        contract=contract,
        precommit_hash=precommit_hash,
        selected_session_dates=selected_dates,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
        prepared_at=observed_at,
    )
    artifact_dir = _publish_artifact_pair(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root or Path.cwd()),
        run_label=run_label,
        precommit_payload=precommit_payload,
        receipt_payload=receipt_payload,
        contract=contract,
        selected_session_dates=selected_dates,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
    )
    return KisIntradayProspectiveHeadObservationPreparation(
        contract=contract,
        status="prepared",
        head_index_status=index_status,
        head_index_sha256=index_sha256,
        available_complete_session_dates=available_dates,
        selected_session_dates=selected_dates,
        precommit_path=artifact_dir / "precommit.json",
        planning_receipt_path=artifact_dir / "planning-receipt.json",
    )


def _inspect_head_index_metadata(
    *,
    head_cache_root: Path,
    repo_root: Path,
) -> _HeadIndexInspection:
    index_path = _head_index_path(head_cache_root=head_cache_root, repo_root=repo_root)
    if not index_path.exists():
        return _HeadIndexInspection(
            status="not_created",
            metadata_sha256=None,
            complete_session_dates=(),
            first_seen_row_fingerprints=(),
        )
    if index_path.is_symlink():
        raise ValueError("prospective head index path is invalid")
    try:
        index_text = index_path.read_text(encoding="utf-8")
        index = json.loads(index_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("prospective head index metadata is invalid") from error
    if not isinstance(index, Mapping):
        raise ValueError("prospective head index metadata is invalid")
    try:
        metadata = validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=_HEAD_EXPECTED_TARGETS,
        )
    except ValueError as error:
        raise ValueError("prospective head index metadata is invalid") from error
    qqq_target = next(
        target for target in metadata.targets if target.target_key == _HEAD_TARGET_KEY
    )
    complete_dates, first_seen_row_fingerprints = _complete_regular_session_metadata(
        qqq_target.retained_chunks
    )
    return _HeadIndexInspection(
        status="available",
        metadata_sha256=_sha256_text(index_text),
        complete_session_dates=complete_dates,
        first_seen_row_fingerprints=first_seen_row_fingerprints,
    )


def _head_index_path(*, head_cache_root: Path, repo_root: Path) -> Path:
    root = Path(head_cache_root)
    if root.is_symlink():
        raise ValueError("prospective head cache root is invalid")
    resolved_root = root.resolve()
    resolved_repo = Path(repo_root).resolve()
    if resolved_root.is_relative_to(resolved_repo):
        raise ValueError("prospective head cache must stay outside the Git workspace")
    version_root = resolved_root / KIS_INTRADAY_PROSPECTIVE_HEAD_CACHE_VERSION
    if version_root.is_symlink():
        raise ValueError("prospective head cache root is invalid")
    return version_root / _HEAD_INDEX_FILENAME


def _complete_regular_session_metadata(
    chunks: tuple[KisPaperPrivateIntradayV1RetainedChunkMetadata, ...],
) -> tuple[tuple[date, ...], tuple[tuple[str, str], ...]]:
    first_seen_completion: dict[str, bool] = {}
    first_seen_fingerprints: dict[str, str] = {}
    for chunk in chunks:
        for row_key, fingerprint in chunk.rows:
            if row_key in first_seen_completion:
                if first_seen_fingerprints[row_key] != fingerprint:
                    raise ValueError("prospective head index has conflicting retained rows")
                continue
            first_seen_fingerprints[row_key] = fingerprint
            first_seen_completion[row_key] = raw_bar_end_is_complete(
                start_ts=_korea_timestamp_to_utc(row_key),
                collected_at=chunk.collected_at,
            )
    completed_row_keys = frozenset(
        row_key for row_key, complete in first_seen_completion.items() if complete
    )
    candidate_dates = sorted(
        {
            _korea_timestamp_to_utc(row_key).date()
            for row_key in completed_row_keys
            if _korea_timestamp_to_utc(row_key).date()
            > KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES[-1]
        }
    )
    complete: list[date] = []
    for session_date in candidate_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            continue
        expected_keys = frozenset(
            _korea_timestamp_key(
                session.window.open_ts + Timeframe.M1.duration * minute_offset
            )
            for minute_offset in range(KIS_INTRADAY_PROSPECTIVE_HEAD_REGULAR_SESSION_MINUTES)
        )
        if expected_keys.issubset(completed_row_keys):
            complete.append(session_date)
    return tuple(complete), tuple(sorted(first_seen_fingerprints.items()))


def _artifact_slot_id(
    *,
    contract: KisIntradayProspectiveHeadObservationContract,
    selected_session_dates: tuple[date, ...],
) -> str:
    """Bind the reusable caller-owned run label to its immutable first-five selection."""

    return _sha256_payload(
        {
            "contract_hash": contract.contract_hash,
            "selected_session_dates": [
                session_date.isoformat() for session_date in selected_session_dates
            ],
            "target_key": _HEAD_TARGET_KEY,
        }
    )


def _selected_rows_fingerprint_sha256(
    *,
    first_seen_row_fingerprints: Mapping[str, str],
    selected_session_dates: tuple[date, ...],
) -> str:
    """Hash only expected regular-session metadata; never serialize it into artifacts."""

    selected_rows: dict[str, str] = {}
    for session_date in selected_session_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            raise ValueError("prospective head selected session is invalid")
        for minute_offset in range(KIS_INTRADAY_PROSPECTIVE_HEAD_REGULAR_SESSION_MINUTES):
            row_key = _korea_timestamp_key(
                session.window.open_ts + Timeframe.M1.duration * minute_offset
            )
            try:
                selected_rows[row_key] = first_seen_row_fingerprints[row_key]
            except KeyError as error:
                raise ValueError("prospective head selected rows are incomplete") from error
    return _sha256_payload({"selected_rows": selected_rows})


def _korea_timestamp_to_utc(row_key: str) -> datetime:
    return datetime.strptime(row_key, "%Y%m%dT%H%M%S").replace(
        tzinfo=_KOREA_TZ
    ).astimezone(UTC)


def _korea_timestamp_key(timestamp: datetime) -> str:
    return require_utc(timestamp, "timestamp").astimezone(_KOREA_TZ).strftime(
        "%Y%m%dT%H%M%S"
    )


def _publish_artifact_pair(
    *,
    artifact_root: Path,
    repo_root: Path,
    run_label: str,
    precommit_payload: Mapping[str, object],
    receipt_payload: Mapping[str, object],
    contract: KisIntradayProspectiveHeadObservationContract,
    selected_session_dates: tuple[date, ...],
    artifact_slot_id: str,
    selected_rows_fingerprint_sha256: str,
) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("prospective head artifact root is invalid")
    resolved_root = root.resolve()
    _reject_repo_artifact_root(resolved_root, repo_root=Path(repo_root).resolve())
    output_parent = resolved_root / "kis-intraday-prospective-head-observation"
    output_dir = output_parent / run_label
    _validate_artifact_component(output_parent, artifact_root=resolved_root, require_directory=True)
    _validate_artifact_component(output_dir, artifact_root=resolved_root, require_directory=False)
    if output_dir.exists() or output_dir.is_symlink():
        return _reuse_artifact_pair(
            output_dir=output_dir,
            artifact_root=resolved_root,
            contract=contract,
            selected_session_dates=selected_session_dates,
            artifact_slot_id=artifact_slot_id,
            selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
        )
    output_parent.mkdir(parents=True, exist_ok=True)
    _validate_artifact_component(output_parent, artifact_root=resolved_root, require_directory=True)
    staging_dir = resolved_root / f".prospective-head-{uuid.uuid4().hex[:8]}.stage"
    staging_dir.mkdir()
    try:
        _write_json_atomic_new(staging_dir / "precommit.json", precommit_payload)
        _write_json_atomic_new(staging_dir / "planning-receipt.json", receipt_payload)
        if output_dir.exists() or output_dir.is_symlink():
            return _reuse_artifact_pair(
                output_dir=output_dir,
                artifact_root=resolved_root,
                contract=contract,
                selected_session_dates=selected_session_dates,
                artifact_slot_id=artifact_slot_id,
                selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
            )
        try:
            os.replace(staging_dir, output_dir)
        except OSError:
            if output_dir.exists() or output_dir.is_symlink():
                return _reuse_artifact_pair(
                    output_dir=output_dir,
                    artifact_root=resolved_root,
                    contract=contract,
                    selected_session_dates=selected_session_dates,
                    artifact_slot_id=artifact_slot_id,
                    selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
                )
            raise
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
    return output_dir


def _reuse_artifact_pair(
    *,
    output_dir: Path,
    artifact_root: Path,
    contract: KisIntradayProspectiveHeadObservationContract,
    selected_session_dates: tuple[date, ...],
    artifact_slot_id: str,
    selected_rows_fingerprint_sha256: str,
) -> Path:
    """Validate an immutable pair before reusing the caller-owned run-label slot."""

    _validate_artifact_component(output_dir, artifact_root=artifact_root, require_directory=True)
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ValueError("prospective head artifact pair is invalid")
    expected_names = frozenset({"precommit.json", "planning-receipt.json"})
    try:
        entries = tuple(output_dir.iterdir())
    except OSError as error:
        raise ValueError("prospective head artifact pair is invalid") from error
    if (
        frozenset(entry.name for entry in entries) != expected_names
        or len(entries) != len(expected_names)
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise ValueError("prospective head artifact pair is invalid")

    precommit = _read_artifact_json(output_dir / "precommit.json")
    receipt = _read_artifact_json(output_dir / "planning-receipt.json")
    _validate_reusable_artifact_pair(
        precommit=precommit,
        receipt=receipt,
        contract=contract,
        selected_session_dates=selected_session_dates,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
    )
    return output_dir


def _validate_artifact_component(
    path: Path,
    *,
    artifact_root: Path,
    require_directory: bool,
) -> None:
    if path.is_symlink():
        raise ValueError("prospective head artifact path is invalid")
    try:
        resolved = path.resolve(strict=False)
    except OSError as error:
        raise ValueError("prospective head artifact path is invalid") from error
    if not resolved.is_relative_to(artifact_root):
        raise ValueError("prospective head artifact path is invalid")
    if path.exists() and require_directory and not path.is_dir():
        raise ValueError("prospective head artifact path is invalid")


def _read_artifact_json(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("prospective head artifact pair is invalid") from error
    if not isinstance(payload, Mapping):
        raise ValueError("prospective head artifact pair is invalid")
    return payload


def _validate_reusable_artifact_pair(
    *,
    precommit: Mapping[str, object],
    receipt: Mapping[str, object],
    contract: KisIntradayProspectiveHeadObservationContract,
    selected_session_dates: tuple[date, ...],
    artifact_slot_id: str,
    selected_rows_fingerprint_sha256: str,
) -> None:
    expected_dates = [session_date.isoformat() for session_date in selected_session_dates]
    expected_precommit_keys = {
        "schema_version",
        "kind",
        "status",
        "prepared_at_utc",
        "contract",
        "contract_hash",
        "head_index",
        "selected_session_dates",
        "artifact_slot_id",
        "selected_rows_fingerprint_sha256",
        "precommit_hash",
    }
    expected_receipt_keys = {
        "schema_version",
        "kind",
        "status",
        "prepared_at_utc",
        "contract_hash",
        "artifact_slot_id",
        "selected_session_dates",
        "selected_rows_fingerprint_sha256",
        "precommit_hash",
        "next_consumer_contract",
    }
    if set(precommit) != expected_precommit_keys or set(receipt) != expected_receipt_keys:
        raise ValueError("prospective head artifact pair is invalid")

    declared_precommit_hash = precommit.get("precommit_hash")
    precommit_without_hash = dict(precommit)
    precommit_without_hash.pop("precommit_hash", None)
    if (
        not isinstance(declared_precommit_hash, str)
        or declared_precommit_hash != _sha256_payload(precommit_without_hash)
    ):
        raise ValueError("prospective head artifact pair is invalid")

    expected_contract_payload = contract.to_payload()
    if (
        precommit.get("schema_version") != SCHEMA_VERSION
        or precommit.get("kind") != "kis_intraday_prospective_head_observation_precommit"
        or precommit.get("status") != "prepared"
        or precommit.get("contract") != expected_contract_payload
        or precommit.get("contract_hash") != contract.contract_hash
        or precommit.get("selected_session_dates") != expected_dates
    ):
        raise ValueError("prospective head artifact pair is invalid")
    _validate_head_index_binding(precommit.get("head_index"))
    _validate_utc_timestamp(precommit.get("prepared_at_utc"))

    _validate_immutable_artifact_identity(
        payload=precommit,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
    )

    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("kind") != "kis_intraday_prospective_head_observation_planning_receipt"
        or receipt.get("status") != "prepared"
        or receipt.get("prepared_at_utc") != precommit.get("prepared_at_utc")
        or receipt.get("contract_hash") != contract.contract_hash
        or receipt.get("selected_session_dates") != expected_dates
        or receipt.get("precommit_hash") != declared_precommit_hash
        or receipt.get("next_consumer_contract") != _next_consumer_contract_payload()
    ):
        raise ValueError("prospective head artifact pair is invalid")
    _validate_immutable_artifact_identity(
        payload=receipt,
        artifact_slot_id=artifact_slot_id,
        selected_rows_fingerprint_sha256=selected_rows_fingerprint_sha256,
    )


def _validate_head_index_binding(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "status",
        "metadata_sha256",
        "target_key",
    }:
        raise ValueError("prospective head artifact pair is invalid")
    if (
        value.get("status") != "available"
        or value.get("target_key") != _HEAD_TARGET_KEY
        or not isinstance(value.get("metadata_sha256"), str)
    ):
        raise ValueError("prospective head artifact pair is invalid")


def _validate_utc_timestamp(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("prospective head artifact pair is invalid")
    try:
        require_utc(datetime.fromisoformat(value), "prepared_at_utc")
    except ValueError as error:
        raise ValueError("prospective head artifact pair is invalid") from error


def _validate_immutable_artifact_identity(
    *,
    payload: Mapping[str, object],
    artifact_slot_id: str,
    selected_rows_fingerprint_sha256: str,
) -> None:
    if payload.get("artifact_slot_id") != artifact_slot_id:
        raise ValueError("prospective head artifact slot does not match selected sessions")
    if payload.get("selected_rows_fingerprint_sha256") != selected_rows_fingerprint_sha256:
        raise ValueError("prospective head selected-row fingerprints do not match")


def _reject_repo_artifact_root(artifact_root: Path, *, repo_root: Path) -> None:
    docker_repo_root = Path("/app").resolve()
    docker_artifact_root = docker_repo_root / "model_artifacts"
    if os.name != "nt" and repo_root == docker_repo_root and (
        artifact_root == docker_artifact_root or docker_artifact_root in artifact_root.parents
    ):
        return
    if artifact_root == repo_root or artifact_root.is_relative_to(repo_root):
        raise ValueError("prospective head artifacts must stay outside the Git workspace")


def _precommit_payload(
    *,
    contract: KisIntradayProspectiveHeadObservationContract,
    head_index_status: str,
    head_index_sha256: str | None,
    selected_session_dates: tuple[date, ...],
    artifact_slot_id: str,
    selected_rows_fingerprint_sha256: str,
    prepared_at: datetime,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_intraday_prospective_head_observation_precommit",
        "status": "prepared",
        "prepared_at_utc": prepared_at.isoformat(),
        "contract": contract.to_payload(),
        "contract_hash": contract.contract_hash,
        "head_index": {
            "status": head_index_status,
            "metadata_sha256": head_index_sha256,
            "target_key": _HEAD_TARGET_KEY,
        },
        "selected_session_dates": [
            session_date.isoformat() for session_date in selected_session_dates
        ],
        "artifact_slot_id": artifact_slot_id,
        "selected_rows_fingerprint_sha256": selected_rows_fingerprint_sha256,
    }


def _planning_receipt_payload(
    *,
    contract: KisIntradayProspectiveHeadObservationContract,
    precommit_hash: str,
    selected_session_dates: tuple[date, ...],
    artifact_slot_id: str,
    selected_rows_fingerprint_sha256: str,
    prepared_at: datetime,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_intraday_prospective_head_observation_planning_receipt",
        "status": "prepared",
        "prepared_at_utc": prepared_at.isoformat(),
        "contract_hash": contract.contract_hash,
        "precommit_hash": precommit_hash,
        "selected_session_dates": [
            session_date.isoformat() for session_date in selected_session_dates
        ],
        "artifact_slot_id": artifact_slot_id,
        "selected_rows_fingerprint_sha256": selected_rows_fingerprint_sha256,
        "next_consumer_contract": _next_consumer_contract_payload(),
    }


def _next_consumer_contract_payload() -> dict[str, int]:
    return {
        "historical_development_prefix_session_count": len(
            KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
        ),
        "prospective_session_receipts_required": (
            KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
        ),
    }


def _write_json_atomic_new(path: Path, payload: Mapping[str, object]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.parent / f".{uuid.uuid4().hex[:8]}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_run_label(run_label: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("prospective head run_label must use 1-80 safe ASCII characters")


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
