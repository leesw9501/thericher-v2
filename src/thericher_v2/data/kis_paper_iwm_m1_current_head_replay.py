"""Offline replay for one isolated IWM/AMS current-head snapshot.

The collector stores an immutable raw snapshot and a source-safe receipt. This
module treats their completion timing as usable only when the receipt contains
the matching immutable snapshot identity. Legacy unbound snapshots remain
replayable as incomplete Bars, never as completed data.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.data.kis_paper_iwm_m1_current_head import (
    KIS_PAPER_IWM_M1_CURRENT_HEAD_ARTIFACT_DIRECTORY,
    KIS_PAPER_IWM_M1_CURRENT_HEAD_CACHE_ROOT,
    KIS_PAPER_IWM_M1_CURRENT_HEAD_RECEIPT_VERSION,
    KIS_PAPER_IWM_M1_CURRENT_HEAD_SNAPSHOT_DIRECTORY,
    KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY,
    KIS_PAPER_IWM_M1_CURRENT_HEAD_VERSION,
    KIS_PAPER_MARKET_DATA_ROOT,
    validate_kis_paper_iwm_m1_current_head_cache_root,
)
from thericher_v2.execution.kis_market_data import KisPaperMarketDataError, KisPaperMinuteRawBar
from thericher_v2.market.resample import SUPPORTED_RESAMPLE_TIMEFRAMES, resample_bars

KIS_PAPER_IWM_M1_CURRENT_HEAD_REPLAY_VERSION = "v1"
KIS_PAPER_IWM_M1_CURRENT_HEAD_OBSERVATION_SELECTION_VERSION = "v1"
KIS_PAPER_IWM_M1_CURRENT_HEAD_REPLAY_ARTIFACT_DIRECTORY = (
    "data/kis-paper-iwm-m1-current-head-replayability-v1"
)

_RAW_MINUTE_COLUMNS = (
    "xymd",
    "xhms",
    "kymd",
    "khms",
    "open",
    "high",
    "low",
    "last",
    "evol",
)
_SNAPSHOT_ID_PATTERN = re.compile(r"[0-9a-f]{64}")
_OBSERVATION_ID_PATTERN = re.compile(r"iwm-observation:[0-9a-f]{64}")
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_EXPECTED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "collection_version",
        "target_key",
        "collection_scope",
        "content_sha256",
        "raw_sha256",
        "raw_filename",
        "row_count",
        "exact_duplicate_rows",
        "continuation_observed",
    }
)
_LEGACY_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "paper_only",
        "route_class",
        "target_key",
        "collection_scope",
        "observed_at",
        "accepted_page_count",
        "accepted_row_category",
        "continuation_category",
        "cache_disposition",
        "response_class",
        "raw_market_data_retained",
        "storage",
        "next_recovery",
    }
)
_BOUND_RECEIPT_FIELDS = _LEGACY_RECEIPT_FIELDS | {
    "receipt_version",
    "snapshot_content_sha256",
}


@dataclass(frozen=True)
class KisPaperIwmM1CurrentHeadObservation:
    """Source-safe identity for one immutable collection receipt."""

    observation_id: str
    receipt_sha256: str
    snapshot_content_sha256: str | None
    observed_at: datetime | None
    completion_basis: Literal[
        "receipt_snapshot_content_binding",
        "completion_evidence_unavailable",
    ]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not _OBSERVATION_ID_PATTERN.fullmatch(self.observation_id)
            or not _valid_digest(self.receipt_sha256)
        ):
            raise ValueError("IWM current-head observation is invalid")
        if self.observed_at is not None:
            object.__setattr__(
                self,
                "observed_at",
                require_utc(self.observed_at, "observed_at"),
            )
        if self.completion_basis == "receipt_snapshot_content_binding":
            if self.observed_at is None or not _valid_digest(self.snapshot_content_sha256):
                raise ValueError("IWM current-head observation is invalid")
            return
        if self.observed_at is not None or self.snapshot_content_sha256 is not None:
            raise ValueError("IWM current-head observation is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return selection metadata without paths, raw rows, or prices."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_iwm_m1_current_head_observation",
            "selection_version": KIS_PAPER_IWM_M1_CURRENT_HEAD_OBSERVATION_SELECTION_VERSION,
            "target_key": KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY,
            "observation_id": self.observation_id,
            "receipt_sha256": self.receipt_sha256,
            "snapshot_content_sha256": self.snapshot_content_sha256,
            "observed_at": None if self.observed_at is None else self.observed_at.isoformat(),
            "completion_basis": self.completion_basis,
        }


@dataclass(frozen=True)
class KisPaperIwmM1CurrentHeadReplay:
    """Verified local Bars from one explicitly identified observation."""

    bars: tuple[Bar, ...]
    source_identity: str
    observation_id: str
    receipt_sha256: str
    snapshot_content_sha256: str
    observed_at: datetime | None
    completion_basis: Literal[
        "receipt_snapshot_content_binding",
        "completion_evidence_unavailable",
    ]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))
        if self.observed_at is not None:
            object.__setattr__(
                self,
                "observed_at",
                require_utc(self.observed_at, "observed_at"),
            )
        if (
            not self.bars
            or not _valid_digest(self.source_identity)
            or not _OBSERVATION_ID_PATTERN.fullmatch(self.observation_id)
            or not _valid_digest(self.receipt_sha256)
            or not _valid_digest(self.snapshot_content_sha256)
        ):
            raise ValueError("IWM current-head replay is invalid")
        if any(
            bar.symbol != "IWM" or bar.market != "US" or bar.timeframe != Timeframe.M1
            for bar in self.bars
        ):
            raise ValueError("IWM current-head replay is invalid")
        starts = tuple(bar.start_ts for bar in self.bars)
        if starts != tuple(sorted(set(starts))):
            raise ValueError("IWM current-head replay is invalid")
        if (
            self.completion_basis == "receipt_snapshot_content_binding"
            and self.observed_at is None
        ) or (
            self.completion_basis == "completion_evidence_unavailable"
            and self.observed_at is not None
        ):
            raise ValueError("IWM current-head replay is invalid")

    def safe_payload(
        self,
        *,
        resampled: Mapping[Timeframe, tuple[Bar, ...]],
    ) -> dict[str, object]:
        """Return aggregate-only evidence for the local replay smoke."""

        timeframe_counts = {
            timeframe.value: len(resampled[timeframe])
            for timeframe in SUPPORTED_RESAMPLE_TIMEFRAMES
        }
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_iwm_m1_current_head_replayability",
            "replay_version": KIS_PAPER_IWM_M1_CURRENT_HEAD_REPLAY_VERSION,
            "status": (
                "replayed"
                if self.completion_basis == "receipt_snapshot_content_binding"
                else "completion_evidence_unavailable"
            ),
            "paper_only": True,
            "route_class": "offline_local_cache",
            "target_key": KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY,
            "source_identity": self.source_identity,
            "observation_id": self.observation_id,
            "receipt_sha256": self.receipt_sha256,
            "snapshot_content_sha256": self.snapshot_content_sha256,
            "completion_basis": self.completion_basis,
            "provider_finality": "not_observed",
            "decision_time_availability": "not_observed",
            "model_input_eligibility": False,
            "broker_or_network_used": False,
            "completed_bucket_counts": timeframe_counts,
        }


@dataclass(frozen=True)
class _CollectionReceipt:
    observation: KisPaperIwmM1CurrentHeadObservation


def load_verified_kis_paper_iwm_m1_current_head_replay(
    *,
    cache_root: Path = KIS_PAPER_IWM_M1_CURRENT_HEAD_CACHE_ROOT,
    artifact_root: Path,
    repository_root: Path,
    market_data_root: Path = KIS_PAPER_MARKET_DATA_ROOT,
    observation_id: str | None = None,
) -> KisPaperIwmM1CurrentHeadReplay:
    """Reattach one isolated observation without network or credential access.

    A caller may omit ``observation_id`` only while the receipt root contains
    exactly one bound receipt, or exactly one legacy receipt.  This is a
    compatibility path for the first observation, never a latest-record rule.
    Repeated v2 observations require an explicit immutable observation ID.
    """

    _reject_linked_ancestors(path=Path(cache_root), label="IWM current-head cache root")
    _reject_linked_ancestors(path=Path(market_data_root), label="market-data root")
    cache = validate_kis_paper_iwm_m1_current_head_cache_root(
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=market_data_root,
    )
    artifact = _external_root(
        root=artifact_root,
        repository_root=repository_root,
        label="IWM current-head replay artifact root",
    )
    receipt = _select_collection_receipt(
        _load_collection_receipts(artifact),
        observation_id=observation_id,
    )
    snapshot = _snapshot_path(
        cache,
        snapshot_identity=receipt.observation.snapshot_content_sha256,
    )
    manifest, raw_bars, snapshot_identity = _load_verified_snapshot(snapshot)
    if (
        receipt.observation.snapshot_content_sha256 is not None
        and receipt.observation.snapshot_content_sha256 != snapshot_identity
    ):
        raise ValueError("IWM current-head collection receipt is invalid")
    source_identity = _sha256(
        _canonical_json_bytes(
            {
                "kind": "kis_paper_iwm_m1_current_head_replay_source_v1",
                "receipt_sha256": receipt.observation.receipt_sha256,
                "snapshot_sha256": snapshot_identity,
            }
        )
    )
    bars = tuple(
        _bar_from_raw(raw_bar=raw_bar, observed_at=receipt.observation.observed_at)
        for raw_bar in raw_bars
    )
    if manifest["content_sha256"] != snapshot_identity:
        raise ValueError("IWM current-head snapshot is invalid")
    return KisPaperIwmM1CurrentHeadReplay(
        bars=bars,
        source_identity=source_identity,
        observation_id=receipt.observation.observation_id,
        receipt_sha256=receipt.observation.receipt_sha256,
        snapshot_content_sha256=snapshot_identity,
        observed_at=receipt.observation.observed_at,
        completion_basis=receipt.observation.completion_basis,
    )


def list_verified_kis_paper_iwm_m1_current_head_observations(
    *,
    artifact_root: Path,
    repository_root: Path,
) -> tuple[KisPaperIwmM1CurrentHeadObservation, ...]:
    """List immutable receipt metadata without opening any raw snapshot."""

    artifact = _external_root(
        root=artifact_root,
        repository_root=repository_root,
        label="IWM current-head replay artifact root",
    )
    observations = tuple(receipt.observation for receipt in _load_collection_receipts(artifact))
    if not observations:
        raise ValueError("IWM current-head replay requires a collection receipt")
    return observations


def load_selected_verified_kis_paper_iwm_m1_current_head_replay(
    *,
    observation_id: str,
    cache_root: Path = KIS_PAPER_IWM_M1_CURRENT_HEAD_CACHE_ROOT,
    artifact_root: Path,
    repository_root: Path,
    market_data_root: Path = KIS_PAPER_MARKET_DATA_ROOT,
) -> KisPaperIwmM1CurrentHeadReplay:
    """Require one caller-selected immutable observation for replay."""

    if not _OBSERVATION_ID_PATTERN.fullmatch(observation_id):
        raise ValueError("IWM current-head observation ID is invalid")
    return load_verified_kis_paper_iwm_m1_current_head_replay(
        cache_root=cache_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        market_data_root=market_data_root,
        observation_id=observation_id,
    )


def resample_verified_kis_paper_iwm_m1_current_head_replay(
    replay: KisPaperIwmM1CurrentHeadReplay,
) -> dict[Timeframe, tuple[Bar, ...]]:
    """Return generic UTC-anchored completed buckets for the fixed timeframe set."""

    return {
        timeframe: tuple(resample_bars(replay.bars, timeframe))
        for timeframe in SUPPORTED_RESAMPLE_TIMEFRAMES
    }


def write_kis_paper_iwm_m1_current_head_replay_evidence(
    *,
    replay: KisPaperIwmM1CurrentHeadReplay,
    resampled: Mapping[Timeframe, tuple[Bar, ...]],
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    """Atomically persist only source-safe aggregate local replay evidence."""

    root = _external_root(
        root=artifact_root,
        repository_root=repository_root,
        label="IWM current-head replay artifact root",
    )
    payload = _canonical_json_bytes(replay.safe_payload(resampled=resampled)) + b"\n"
    digest = _sha256(payload)
    destination_directory = root / KIS_PAPER_IWM_M1_CURRENT_HEAD_REPLAY_ARTIFACT_DIRECTORY
    _ensure_external_descendant_directory(root=root, path=destination_directory)
    destination = destination_directory / f"{digest}.json"
    _validate_descendant(root=root, path=destination, label="IWM current-head replay evidence")
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != payload:
            raise ValueError("IWM current-head replay evidence conflicts")
        return destination

    staging = destination.with_name(f".{digest}.{uuid.uuid4().hex[:8]}.stage")
    try:
        staging.write_bytes(payload)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def _snapshot_path(cache_root: Path, *, snapshot_identity: str | None) -> Path:
    snapshot_root = (
        cache_root
        / KIS_PAPER_IWM_M1_CURRENT_HEAD_VERSION
        / KIS_PAPER_IWM_M1_CURRENT_HEAD_SNAPSHOT_DIRECTORY
    )
    if snapshot_root.is_symlink() or not snapshot_root.is_dir():
        raise ValueError("IWM current-head snapshot root is invalid")
    _validate_descendant(
        root=cache_root,
        path=snapshot_root,
        label="IWM current-head snapshot root",
    )
    candidates = tuple(snapshot_root.iterdir())
    if snapshot_identity is None:
        if len(candidates) != 1:
            raise ValueError("IWM current-head replay requires exactly one legacy snapshot")
        snapshot = candidates[0]
    else:
        if not _valid_digest(snapshot_identity):
            raise ValueError("IWM current-head collection receipt is invalid")
        snapshot = snapshot_root / snapshot_identity
    if (
        snapshot.is_symlink()
        or not snapshot.is_dir()
        or not _SNAPSHOT_ID_PATTERN.fullmatch(snapshot.name)
    ):
        raise ValueError("IWM current-head snapshot is invalid")
    _validate_descendant(root=snapshot_root, path=snapshot, label="IWM current-head snapshot")
    return snapshot


def _load_verified_snapshot(
    snapshot: Path,
) -> tuple[dict[str, object], tuple[KisPaperMinuteRawBar, ...], str]:
    if snapshot.is_symlink() or set(path.name for path in snapshot.iterdir()) != {
        "manifest.json",
        "rows.csv.gz",
    }:
        raise ValueError("IWM current-head snapshot is invalid")
    manifest_path = snapshot / "manifest.json"
    raw_path = snapshot / "rows.csv.gz"
    if (
        manifest_path.is_symlink()
        or raw_path.is_symlink()
        or not manifest_path.is_file()
        or not raw_path.is_file()
    ):
        raise ValueError("IWM current-head snapshot is invalid")

    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("IWM current-head snapshot is invalid") from error
    if not isinstance(manifest, dict) or manifest_bytes != _canonical_json_bytes(manifest) + b"\n":
        raise ValueError("IWM current-head snapshot is invalid")
    _validate_snapshot_manifest(manifest=manifest, snapshot_identity=snapshot.name)

    raw_bytes = raw_path.read_bytes()
    if _sha256(raw_bytes) != manifest["raw_sha256"]:
        raise ValueError("IWM current-head raw hash mismatch")
    raw_bars = _decode_raw_bars(raw_bytes=raw_bytes, expected_row_count=manifest["row_count"])
    content_identity = _sha256(
        _canonical_json_bytes([raw_bar.as_document() for raw_bar in raw_bars])
    )
    if content_identity != manifest["content_sha256"] or content_identity != snapshot.name:
        raise ValueError("IWM current-head content hash mismatch")
    return manifest, raw_bars, content_identity


def _validate_snapshot_manifest(*, manifest: Mapping[str, object], snapshot_identity: str) -> None:
    if set(manifest) != _EXPECTED_MANIFEST_FIELDS:
        raise ValueError("IWM current-head snapshot is invalid")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("kind") != "kis_paper_iwm_m1_current_head_snapshot"
        or manifest.get("collection_version") != KIS_PAPER_IWM_M1_CURRENT_HEAD_VERSION
        or manifest.get("target_key") != KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY
        or manifest.get("collection_scope") != "one_current_day_head_page_no_continuation"
        or manifest.get("raw_filename") != "rows.csv.gz"
        or not isinstance(manifest.get("continuation_observed"), bool)
        or not _valid_digest(manifest.get("content_sha256"))
        or not _valid_digest(manifest.get("raw_sha256"))
        or manifest.get("content_sha256") != snapshot_identity
        or not _non_negative_int(manifest.get("row_count"))
        or not _non_negative_int(manifest.get("exact_duplicate_rows"))
        or manifest["row_count"] <= 0
    ):
        raise ValueError("IWM current-head snapshot is invalid")


def _decode_raw_bars(
    *,
    raw_bytes: bytes,
    expected_row_count: int,
) -> tuple[KisPaperMinuteRawBar, ...]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes), mode="rb") as handle:
            decoded = handle.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded))
        if tuple(reader.fieldnames or ()) != _RAW_MINUTE_COLUMNS:
            raise ValueError("IWM current-head raw file is invalid")
        records = tuple(reader)
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as error:
        raise ValueError("IWM current-head raw file is invalid") from error
    if len(records) != expected_row_count or any(
        set(record) != set(_RAW_MINUTE_COLUMNS) for record in records
    ):
        raise ValueError("IWM current-head raw file is invalid")
    try:
        raw_bars = tuple(
            KisPaperMinuteRawBar(
                exchange_date=record["xymd"],
                exchange_time=record["xhms"],
                korea_date=record["kymd"],
                korea_time=record["khms"],
                open=record["open"],
                high=record["high"],
                low=record["low"],
                last=record["last"],
                volume=record["evol"],
            )
            for record in records
        )
    except (KeyError, TypeError, ValueError, KisPaperMarketDataError) as error:
        raise ValueError("IWM current-head raw file is invalid") from error
    keys = tuple(raw_bar.exchange_date + raw_bar.exchange_time for raw_bar in raw_bars)
    if keys != tuple(sorted(set(keys))):
        raise ValueError("IWM current-head raw file is invalid")
    return raw_bars


def _load_collection_receipts(artifact_root: Path) -> tuple[_CollectionReceipt, ...]:
    receipt_root = artifact_root / KIS_PAPER_IWM_M1_CURRENT_HEAD_ARTIFACT_DIRECTORY
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise ValueError("IWM current-head collection receipt is invalid")
    _validate_descendant(
        root=artifact_root,
        path=receipt_root,
        label="IWM current-head collection receipt root",
    )
    candidates = tuple(receipt_root.iterdir())
    if not candidates:
        raise ValueError("IWM current-head replay requires a collection receipt")
    receipts = tuple(_read_collection_receipt(path) for path in candidates)
    ordered = tuple(
        sorted(
            receipts,
            key=lambda receipt: (
                receipt.observation.observed_at is None,
                receipt.observation.observed_at or datetime.min.replace(tzinfo=UTC),
                receipt.observation.observation_id,
            ),
        )
    )
    observation_ids = tuple(receipt.observation.observation_id for receipt in ordered)
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("IWM current-head observation receipts are duplicated")
    return ordered


def _select_collection_receipt(
    receipts: tuple[_CollectionReceipt, ...],
    *,
    observation_id: str | None,
) -> _CollectionReceipt:
    if observation_id is not None:
        if not _OBSERVATION_ID_PATTERN.fullmatch(observation_id):
            raise ValueError("IWM current-head observation ID is invalid")
        selected = tuple(
            receipt for receipt in receipts if receipt.observation.observation_id == observation_id
        )
        if len(selected) != 1:
            raise ValueError("IWM current-head observation is unavailable")
        return selected[0]

    bound = tuple(
        receipt
        for receipt in receipts
        if receipt.observation.completion_basis == "receipt_snapshot_content_binding"
    )
    if len(bound) == 1:
        return bound[0]
    if len(bound) > 1:
        raise ValueError("IWM current-head replay requires an explicit observation ID")
    if len(receipts) != 1:
        raise ValueError("IWM current-head replay requires exactly one legacy receipt")
    return receipts[0]


def _read_collection_receipt(path: Path) -> _CollectionReceipt:
    if path.is_symlink() or not path.is_file() or path.suffix != ".json":
        raise ValueError("IWM current-head collection receipt is invalid")
    receipt_bytes = path.read_bytes()
    try:
        receipt = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("IWM current-head collection receipt is invalid") from error
    if not isinstance(receipt, dict) or receipt_bytes != _canonical_json_bytes(receipt) + b"\n":
        raise ValueError("IWM current-head collection receipt is invalid")
    observed_at, snapshot_identity, completion_basis = _validate_collection_receipt(receipt)
    receipt_identity = _sha256(receipt_bytes)
    return _CollectionReceipt(
        observation=KisPaperIwmM1CurrentHeadObservation(
            observation_id=_observation_id(
                receipt_sha256=receipt_identity,
                snapshot_content_sha256=snapshot_identity,
            ),
            receipt_sha256=receipt_identity,
            snapshot_content_sha256=snapshot_identity,
            observed_at=observed_at,
            completion_basis=completion_basis,
        )
    )


def _validate_collection_receipt(
    receipt: Mapping[str, object],
) -> tuple[
    datetime | None,
    str | None,
    Literal["receipt_snapshot_content_binding", "completion_evidence_unavailable"],
]:
    receipt_fields = frozenset(receipt)
    if receipt_fields not in {_LEGACY_RECEIPT_FIELDS, _BOUND_RECEIPT_FIELDS} or (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("kind") != "kis_paper_iwm_m1_current_head"
        or receipt.get("status") != "collected"
        or receipt.get("paper_only") is not True
        or receipt.get("route_class") != "kis_paper_market_data"
        or receipt.get("target_key") != KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY
        or receipt.get("collection_scope") != "one_current_day_head_page_no_continuation"
        or receipt.get("accepted_page_count") != 1
        or receipt.get("accepted_row_category") != "nonempty"
        or receipt.get("continuation_category") not in {"not_observed", "observed_not_followed"}
        or receipt.get("cache_disposition") not in {"retained", "already_retained"}
        or receipt.get("response_class") != "accepted"
        or receipt.get("raw_market_data_retained") is not True
        or receipt.get("storage") != "external_market_data_only"
        or receipt.get("next_recovery") != "new_isolated_current_head_observation"
    ):
        raise ValueError("IWM current-head collection receipt is invalid")
    if receipt_fields == _LEGACY_RECEIPT_FIELDS:
        return None, None, "completion_evidence_unavailable"
    snapshot_identity = receipt.get("snapshot_content_sha256")
    if (
        receipt.get("receipt_version") != KIS_PAPER_IWM_M1_CURRENT_HEAD_RECEIPT_VERSION
        or not _valid_digest(snapshot_identity)
    ):
        raise ValueError("IWM current-head collection receipt is invalid")
    value = receipt.get("observed_at")
    if not isinstance(value, str):
        raise ValueError("IWM current-head collection receipt is invalid")
    try:
        observed_at = require_utc(
            datetime.fromisoformat(value.replace("Z", "+00:00")),
            "observed_at",
        )
    except ValueError as error:
        raise ValueError("IWM current-head collection receipt is invalid") from error
    return observed_at, snapshot_identity, "receipt_snapshot_content_binding"


def _bar_from_raw(*, raw_bar: KisPaperMinuteRawBar, observed_at: datetime | None) -> Bar:
    start_ts = _korea_timestamp_to_utc(raw_bar)
    return Bar(
        symbol="IWM",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=raw_bar.open,
        high=raw_bar.high,
        low=raw_bar.low,
        close=raw_bar.last,
        volume=raw_bar.volume,
        complete=(
            observed_at is not None
            and start_ts + Timeframe.M1.duration
            <= observed_at.replace(second=0, microsecond=0)
        ),
    )


def _korea_timestamp_to_utc(raw_bar: KisPaperMinuteRawBar) -> datetime:
    try:
        return datetime.strptime(
            f"{raw_bar.korea_date}{raw_bar.korea_time}", "%Y%m%d%H%M%S"
        ).replace(tzinfo=_KOREA_TZ).astimezone(UTC)
    except ValueError as error:
        raise ValueError("IWM current-head Korea timestamp is invalid") from error


def _external_root(*, root: Path, repository_root: Path, label: str) -> Path:
    supplied = Path(root)
    _reject_linked_ancestors(path=supplied, label=label)
    resolved = supplied.resolve()
    repository = Path(repository_root).resolve()
    if resolved.is_relative_to(repository):
        raise ValueError(f"{label} must stay outside Git")
    return resolved


def _ensure_external_descendant_directory(*, root: Path, path: Path) -> None:
    _validate_descendant(root=root, path=path, label="IWM current-head replay evidence directory")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("IWM current-head replay evidence directory is invalid")
    current = root
    for component in path.relative_to(root).parts:
        candidate = current / component
        if candidate.exists():
            if candidate.is_symlink() or not candidate.is_dir():
                raise ValueError("IWM current-head replay evidence directory is invalid")
        else:
            candidate.mkdir()
            if candidate.is_symlink() or not candidate.is_dir():
                raise ValueError("IWM current-head replay evidence directory is invalid")
        current = candidate


def _reject_linked_ancestors(*, path: Path, label: str) -> None:
    for candidate in (path, *path.parents):
        if candidate.exists() and candidate.is_symlink():
            raise ValueError(f"{label} is invalid")


def _validate_descendant(*, root: Path, path: Path, label: str) -> None:
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(root):
        raise ValueError(f"{label} is invalid")


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _SNAPSHOT_ID_PATTERN.fullmatch(value) is not None


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _observation_id(*, receipt_sha256: str, snapshot_content_sha256: str | None) -> str:
    return "iwm-observation:" + _sha256(
        _canonical_json_bytes(
            {
                "kind": "kis_paper_iwm_m1_current_head_observation_v1",
                "receipt_sha256": receipt_sha256,
                "snapshot_content_sha256": snapshot_content_sha256,
            }
        )
    )


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
