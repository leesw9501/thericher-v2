"""Source-safe offline mechanics for the isolated IWM current-head cache."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data.kis_paper_intraday import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.data.kis_paper_intraday_index_metadata import (
    KisPaperPrivateIntradayV1IndexMetadata,
    KisPaperPrivateIntradayV1TargetMetadata,
    validate_kis_paper_private_intraday_v1_index_metadata,
)
from thericher_v2.data.kis_paper_iwm_current_head import (
    validate_kis_paper_iwm_current_head_ingestion_artifact_root,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_IWM_CURRENT_HEAD_CACHE_ROOT,
    KIS_PAPER_IWM_CURRENT_HEAD_TARGET,
    KIS_PAPER_MARKET_DATA_ROOT,
    KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
    KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME,
    validate_kis_paper_iwm_current_head_request,
)

KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_KIND = "kis_paper_iwm_current_head_cache_mechanics"
KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_ARTIFACT_DIRECTORY = (
    "data/kis-paper-iwm-m1-current-head-cache-mechanics"
)
KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_TARGET_KEY = "IWM/AMS/1m"


@dataclass(frozen=True, slots=True)
class KisPaperIwmCurrentHeadCacheMechanics:
    """Aggregate cache facts after strict offline IWM integrity reattachment."""

    index_generation: int
    indexed_retained_chunk_count: int
    collection_scope: Literal["head"]
    bar_count: int
    complete_bar_count: int
    incomplete_bar_count: int
    adjacent_m1_pair_count: int
    non_adjacent_pair_count: int
    maximum_interbar_seconds: int
    target_key: str = KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_TARGET_KEY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        counts = (
            self.index_generation,
            self.indexed_retained_chunk_count,
            self.bar_count,
            self.complete_bar_count,
            self.incomplete_bar_count,
            self.adjacent_m1_pair_count,
            self.non_adjacent_pair_count,
            self.maximum_interbar_seconds,
        )
        if (
            self.target_key != KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_TARGET_KEY
            or self.schema_version != SCHEMA_VERSION
            or self.collection_scope != "head"
            or any(type(value) is not int or value < 0 for value in counts)
            or self.indexed_retained_chunk_count != 1
            or self.bar_count <= 0
            or self.complete_bar_count + self.incomplete_bar_count != self.bar_count
            or self.adjacent_m1_pair_count + self.non_adjacent_pair_count != self.bar_count - 1
            or (self.bar_count == 1 and self.maximum_interbar_seconds != 0)
            or (self.bar_count > 1 and self.maximum_interbar_seconds <= 0)
        ):
            raise ValueError("IWM current-head cache mechanics are invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return aggregate mechanics only; no paths, times, rows, or values."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_KIND,
            "status": "verified",
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "target_key": self.target_key,
            "integrity_status": "index_manifest_raw_verified",
            "cache": {
                "contract": (
                    "kis_paper_private_intraday_backfill/"
                    f"{KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION}"
                ),
                "index_generation": self.index_generation,
                "indexed_retained_chunk_count": self.indexed_retained_chunk_count,
                "collection_scope": self.collection_scope,
            },
            "geometry": {
                "bar_count": self.bar_count,
                "complete_bar_count": self.complete_bar_count,
                "incomplete_bar_count": self.incomplete_bar_count,
                "adjacent_m1_pair_count": self.adjacent_m1_pair_count,
                "non_adjacent_pair_count": self.non_adjacent_pair_count,
                "maximum_interbar_seconds": self.maximum_interbar_seconds,
            },
            "session_finality": "not_observed",
            "decision_time_availability": "not_observed",
            "model_input_eligibility": False,
            "network_access": False,
            "credentials_read": False,
            "paper_execution": False,
            "raw_market_data_emitted": False,
        }


@dataclass(frozen=True, slots=True)
class KisPaperIwmCurrentHeadCacheMechanicsReceipt:
    """External receipt location for a source-safe mechanics projection."""

    mechanics: KisPaperIwmCurrentHeadCacheMechanics
    evidence_path: Path = field(repr=False)
    evidence_sha256: str

    def __post_init__(self) -> None:
        if not _is_sha256(self.evidence_sha256):
            raise ValueError("IWM current-head cache mechanics receipt is invalid")


def inspect_kis_paper_iwm_current_head_cache_mechanics(
    *,
    cache_root: Path = KIS_PAPER_IWM_CURRENT_HEAD_CACHE_ROOT,
    repo_root: Path,
    market_data_root: Path = KIS_PAPER_MARKET_DATA_ROOT,
) -> KisPaperIwmCurrentHeadCacheMechanics:
    """Reattach only one IWM current-head cache without provider access.

    The strict index preflight occurs before the generic verified loader opens
    the retained raw file. The loader then verifies persisted manifest and raw
    bytes before decoding rows, while this function publishes aggregate facts
    only.
    """

    resolved_market_data_root = Path(market_data_root).resolve(strict=False)
    protected_cache_roots = (
        resolved_market_data_root / "us_equities" / "kis_paper_private" / "intraday",
        resolved_market_data_root / "us_equities" / "kis_paper_private" / "iwm_m1_current_head",
    )
    resolved_cache_root = validate_kis_paper_iwm_current_head_request(
        target=KIS_PAPER_IWM_CURRENT_HEAD_TARGET,
        cache_root=Path(cache_root),
        repo_root=Path(repo_root),
        market_data_root=Path(market_data_root),
        protected_cache_roots=protected_cache_roots,
    )
    index_path, index_metadata_sha256, metadata, target = _read_strict_iwm_index(
        cache_root=resolved_cache_root,
    )
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=resolved_cache_root,
        repo_root=Path(repo_root),
        symbol="IWM",
        exchange="AMS",
        expected_index_metadata_sha256=index_metadata_sha256,
    )
    expected_dataset_id = (
        "kis.paper.private.intraday.iwm.ams.m1."
        f"{KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION}"
    )
    if catalog.source_path != index_path or catalog.dataset_id != expected_dataset_id:
        raise ValueError("IWM current-head verified catalog is invalid")
    if any(
        bar.symbol != "IWM" or bar.market != "US" or bar.timeframe is not Timeframe.M1
        for bar in catalog.bars
    ):
        raise ValueError("IWM current-head verified catalog is invalid")
    geometry = _geometry_from_verified_bars(catalog.bars)
    return KisPaperIwmCurrentHeadCacheMechanics(
        index_generation=metadata.generation,
        indexed_retained_chunk_count=len(target.retained_chunks),
        collection_scope="head",
        **geometry,
    )


def inspect_and_write_kis_paper_iwm_current_head_cache_mechanics(
    *,
    cache_root: Path = KIS_PAPER_IWM_CURRENT_HEAD_CACHE_ROOT,
    artifact_root: Path,
    repo_root: Path,
    market_data_root: Path = KIS_PAPER_MARKET_DATA_ROOT,
) -> KisPaperIwmCurrentHeadCacheMechanicsReceipt:
    """Reattach the cache and retain its source-safe aggregate receipt."""

    mechanics = inspect_kis_paper_iwm_current_head_cache_mechanics(
        cache_root=cache_root,
        repo_root=repo_root,
        market_data_root=market_data_root,
    )
    return write_kis_paper_iwm_current_head_cache_mechanics_evidence(
        mechanics=mechanics,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )


def write_kis_paper_iwm_current_head_cache_mechanics_evidence(
    *,
    mechanics: KisPaperIwmCurrentHeadCacheMechanics,
    artifact_root: Path,
    repo_root: Path,
) -> KisPaperIwmCurrentHeadCacheMechanicsReceipt:
    """Atomically retain a deterministic external receipt with no provider rows."""

    root = _external_artifact_root(artifact_root=artifact_root, repo_root=repo_root)
    payload = _canonical_json_bytes(mechanics.safe_payload()) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()
    directory = root / KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_ARTIFACT_DIRECTORY
    _ensure_external_descendant_directory(root=root, path=directory)
    destination = directory / f"{digest[:16]}.json"
    _validate_destination(root=root, destination=destination)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("IWM current-head cache mechanics evidence conflicts")
    else:
        staging = destination.with_name(f".{digest[:16]}.{uuid.uuid4().hex[:8]}.stage")
        try:
            staging.write_bytes(payload)
            os.replace(staging, destination)
        finally:
            staging.unlink(missing_ok=True)
    return KisPaperIwmCurrentHeadCacheMechanicsReceipt(
        mechanics=mechanics,
        evidence_path=destination,
        evidence_sha256=f"sha256:{digest}",
    )


def validate_kis_paper_iwm_current_head_cache_mechanics_artifact_root(
    *,
    artifact_root: Path,
    repo_root: Path,
) -> Path:
    """Validate the external mechanics receipt root without creating it."""

    return validate_kis_paper_iwm_current_head_ingestion_artifact_root(
        artifact_root=artifact_root,
        repository_root=repo_root,
    )


def _read_strict_iwm_index(
    *,
    cache_root: Path,
) -> tuple[
    Path,
    str,
    KisPaperPrivateIntradayV1IndexMetadata,
    KisPaperPrivateIntradayV1TargetMetadata,
]:
    version_root = cache_root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
    index_path = version_root / KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME
    if (
        version_root.is_symlink()
        or (version_root.exists() and not version_root.is_dir())
        or index_path.is_symlink()
        or (index_path.exists() and not index_path.is_file())
    ):
        raise ValueError("IWM current-head cache index is invalid")
    try:
        index_bytes = index_path.read_bytes()
        index = json.loads(index_bytes)
        metadata = validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=(KIS_PAPER_IWM_CURRENT_HEAD_TARGET,),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("IWM current-head cache index is invalid") from error
    if len(metadata.targets) != 1:
        raise ValueError("IWM current-head cache index is invalid")
    target = metadata.targets[0]
    if (
        target.target_key != KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_TARGET_KEY
        or len(target.retained_chunks) != 1
        or target.retained_chunks[0].collection_scope != "head"
    ):
        raise ValueError("IWM current-head cache scope is invalid")
    return (
        index_path,
        "sha256:" + hashlib.sha256(index_bytes).hexdigest(),
        metadata,
        target,
    )


def _geometry_from_verified_bars(bars: tuple[object, ...]) -> dict[str, int]:
    if not bars:
        raise ValueError("IWM current-head verified catalog is invalid")
    complete_bar_count = sum(bool(getattr(bar, "complete", False)) for bar in bars)
    adjacent_m1_pair_count = 0
    non_adjacent_pair_count = 0
    maximum_interbar_seconds = 0
    previous = bars[0]
    for current in bars[1:]:
        previous_start = getattr(previous, "start_ts", None)
        current_start = getattr(current, "start_ts", None)
        if previous_start is None or current_start is None:
            raise ValueError("IWM current-head verified catalog is invalid")
        interval_seconds = int((current_start - previous_start).total_seconds())
        if interval_seconds <= 0:
            raise ValueError("IWM current-head verified catalog is invalid")
        maximum_interbar_seconds = max(maximum_interbar_seconds, interval_seconds)
        if interval_seconds == int(timedelta(minutes=1).total_seconds()):
            adjacent_m1_pair_count += 1
        else:
            non_adjacent_pair_count += 1
        previous = current
    return {
        "bar_count": len(bars),
        "complete_bar_count": complete_bar_count,
        "incomplete_bar_count": len(bars) - complete_bar_count,
        "adjacent_m1_pair_count": adjacent_m1_pair_count,
        "non_adjacent_pair_count": non_adjacent_pair_count,
        "maximum_interbar_seconds": maximum_interbar_seconds,
    }


def _external_artifact_root(*, artifact_root: Path, repo_root: Path) -> Path:
    root = validate_kis_paper_iwm_current_head_cache_mechanics_artifact_root(
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    _ensure_real_directory(root)
    return root


def _ensure_real_directory(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("IWM current-head cache mechanics artifact destination is invalid")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("IWM current-head cache mechanics artifact destination is invalid")


def _ensure_external_descendant_directory(*, root: Path, path: Path) -> None:
    if not path.is_relative_to(root):
        raise ValueError("IWM current-head cache mechanics artifact destination is invalid")
    current = root
    for component in path.relative_to(root).parts:
        current = current / component
        _ensure_real_directory(current)


def _validate_destination(*, root: Path, destination: Path) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("IWM current-head cache mechanics evidence destination is invalid")
    if not destination.resolve(strict=False).is_relative_to(root.resolve()):
        raise ValueError("IWM current-head cache mechanics evidence destination is invalid")


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _is_sha256(value: str) -> bool:
    prefix, separator, digest = value.partition(":")
    return (
        prefix == "sha256"
        and separator == ":"
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )
