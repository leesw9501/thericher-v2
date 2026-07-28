"""Read-only, source-local materialization for the active broad KIS D1 cache.

The broad collector owns its mutable index and raw snapshots.  This module is
deliberately an offline consumer: it never opens the collector lock, calls KIS,
reads an environment variable, or writes into the cache.  A materialized panel
is an immutable reference to one byte-stable index snapshot, not a claim that
the current-listing universe is point-in-time, adjusted, or research-ready.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.kis_paper_daily_broad_registry import (
    KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
    KisPaperDailyBroadRegistry,
    load_kis_paper_daily_broad_registry,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader

KIS_PAPER_DAILY_BROAD_PANEL_VERSION = "kis-paper-daily-nas-broad-panel-v1"
KIS_PAPER_DAILY_BROAD_PANEL_ID = "kis.paper.private.daily.nas.broad.panel-v1"
KIS_PAPER_DAILY_BROAD_CACHE_VERSION = "kis-paper-daily-nas-broad-v1"
KIS_PAPER_DAILY_BROAD_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-broad/v1"
)
KIS_PAPER_DAILY_BROAD_PANEL_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-broad-panel/v1"
)
KIS_PAPER_DAILY_BROAD_PANEL_EVIDENCE_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/kis-paper-daily-nas-broad-panel-v1"
)
KIS_PAPER_DAILY_BROAD_PANEL_CONTINUITY_ID = "kis.paper.private.daily.nas.broad.panel-continuity-v1"
KIS_PAPER_DAILY_BROAD_PANEL_CONTINUITY_EVIDENCE_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/kis-paper-daily-nas-broad-panel-continuity-v1"
)

_INDEX_FILENAME = "index.json"
_RAW_COLUMNS = (
    "symbol",
    "exchange",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
_TARGET_STATES = frozenset({"ready", "deferred", "source_limited", "complete"})
_CHUNK_OUTCOMES = frozenset(
    {"committed", "partial", "complete", "source_limited", "conflict"}
)
_USABLE_CHUNK_OUTCOMES = _CHUNK_OUTCOMES - {"conflict"}
_SAFE_FIELD_NAMES = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "eventjsonl",
        "eventlog",
        "sourcepath",
        "statesqlite",
        "workdir",
    }
)
_LIMITATIONS = (
    "current_listing_only_not_point_in_time_universe",
    "non_pit_registry_scope",
    "non_ranking_scope",
    "MODP_0_unadjusted",
    "corporate_action_semantics_not_qualified",
    "session_finality_unattested",
    "source_local_kis_only_no_cross_source_blend",
    "development_coverage_only_not_research_ready",
)


@dataclass(frozen=True, slots=True)
class KisPaperDailyBroadPanelTarget:
    """Source-safe coverage facts for one registry target."""

    target_key: str
    state: Literal["ready", "deferred", "source_limited", "complete"]
    next_anchor_date: str
    accepted_page_count: int
    categorical_failure_count: int
    last_reason: str | None
    chunk_count: int
    bar_count: int
    coverage_start: str | None
    coverage_end: str | None
    outcome_counts: Mapping[str, int]
    quarantined: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        outcomes = MappingProxyType(dict(self.outcome_counts))
        if (
            not _is_target_key(self.target_key)
            or self.state not in _TARGET_STATES
            or not _is_compact_date(self.next_anchor_date)
            or self.accepted_page_count < 0
            or self.categorical_failure_count < 0
            or self.chunk_count < 0
            or self.bar_count < 0
            or self.last_reason is not None and not isinstance(self.last_reason, str)
            or self.schema_version != SCHEMA_VERSION
            or any(
                outcome not in _CHUNK_OUTCOMES or count < 0
                for outcome, count in outcomes.items()
            )
        ):
            raise ValueError("broad daily panel target is invalid")
        if self.bar_count == 0 and (
            self.coverage_start is not None or self.coverage_end is not None
        ):
            raise ValueError("broad daily panel target coverage is invalid")
        if self.bar_count > 0 and (
            not _is_iso_date(self.coverage_start)
            or not _is_iso_date(self.coverage_end)
            or str(self.coverage_start) > str(self.coverage_end)
        ):
            raise ValueError("broad daily panel target coverage is invalid")
        if self.quarantined != (outcomes.get("conflict", 0) > 0):
            raise ValueError("broad daily panel target quarantine is invalid")
        object.__setattr__(self, "outcome_counts", outcomes)

    def to_payload(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "state": self.state,
            "next_anchor_date": self.next_anchor_date,
            "accepted_page_count": self.accepted_page_count,
            "categorical_failure_count": self.categorical_failure_count,
            "last_reason": self.last_reason,
            "chunk_count": self.chunk_count,
            "bar_count": self.bar_count,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "outcome_counts": dict(sorted(self.outcome_counts.items())),
            "quarantined": self.quarantined,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class KisPaperDailyBroadPanel:
    """A reattested source-local D1 coverage panel.

    ``bars_by_target`` contains only non-quarantined targets with retained
    chunks.  The companion target map keeps zero-coverage and quarantined facts
    visible instead of silently dropping them.
    """

    dataset_id: str
    dataset_hash: str
    registry_sha256: str
    source_manifest_sha256: str
    source_file_sha256: str
    index_sha256: str
    index_generation: int
    source_root: Path
    target_keys: tuple[str, ...]
    targets_by_key: Mapping[str, KisPaperDailyBroadPanelTarget]
    bars_by_target: Mapping[str, CatalogedBars]
    source_snapshot: Mapping[str, object]
    limitations: tuple[str, ...] = _LIMITATIONS
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        targets = MappingProxyType(dict(self.targets_by_key))
        bars = MappingProxyType(dict(self.bars_by_target))
        snapshot = MappingProxyType(dict(self.source_snapshot))
        if (
            self.dataset_id != KIS_PAPER_DAILY_BROAD_PANEL_ID
            or not _is_sha256(self.dataset_hash)
            or not _is_sha256(self.registry_sha256)
            or not _is_sha256(self.source_manifest_sha256)
            or not _is_sha256(self.source_file_sha256)
            or not _is_sha256(self.index_sha256)
            or self.index_generation < 0
            or tuple(targets) != self.target_keys
            or tuple(sorted(self.target_keys)) != self.target_keys
            or self.limitations != _LIMITATIONS
            or self.schema_version != SCHEMA_VERSION
            or self.source_root.is_symlink()
        ):
            raise ValueError("broad daily panel is invalid")
        for target_key, target in targets.items():
            if target.target_key != target_key:
                raise ValueError("broad daily panel target mapping is invalid")
        for target_key, catalog in bars.items():
            target = targets.get(target_key)
            if (
                target is None
                or target.quarantined
                or target.bar_count == 0
                or not isinstance(catalog, CatalogedBars)
                or catalog.dataset_id != self.dataset_id
                or catalog.dataset_hash != self.dataset_hash
                or catalog.source_path != self.source_root / _INDEX_FILENAME
                or len(catalog.bars) != target.bar_count
                or any(
                    bar.symbol != target_key.split("/", maxsplit=1)[0]
                    or bar.market != "US"
                    or bar.timeframe is not Timeframe.D1
                    or not bar.complete
                    for bar in catalog.bars
                )
            ):
                raise ValueError("broad daily panel stream is invalid")
        expected_present = {
            key
            for key, target in targets.items()
            if target.bar_count > 0 and not target.quarantined
        }
        if set(bars) != expected_present:
            raise ValueError("broad daily panel stream coverage is invalid")
        object.__setattr__(self, "targets_by_key", targets)
        object.__setattr__(self, "bars_by_target", bars)
        object.__setattr__(self, "source_snapshot", snapshot)

    @property
    def covered_target_count(self) -> int:
        return sum(target.bar_count > 0 for target in self.targets_by_key.values())

    @property
    def zero_coverage_target_count(self) -> int:
        return sum(target.bar_count == 0 for target in self.targets_by_key.values())

    @property
    def quarantined_target_count(self) -> int:
        return sum(target.quarantined for target in self.targets_by_key.values())


@dataclass(frozen=True, slots=True)
class KisPaperDailyBroadPanelMaterialization:
    """External immutable panel manifest and source-safe receipt."""

    panel: KisPaperDailyBroadPanel
    manifest_path: Path
    manifest_hash: str
    receipt_path: Path
    receipt_hash: str

    def __post_init__(self) -> None:
        if (
            not self.manifest_path.is_file()
            or not self.receipt_path.is_file()
            or not _is_sha256(self.manifest_hash)
            or not _is_sha256(self.receipt_hash)
        ):
            raise ValueError("broad daily panel materialization is invalid")


@dataclass(frozen=True, slots=True)
class KisPaperDailyBroadPanelContinuityComparison:
    """Source-safe immutable-overlap comparison for two frozen broad panels."""

    status: Literal["equal", "mismatch"]
    baseline_dataset_hash: str
    baseline_index_generation: int
    candidate_dataset_hash: str
    candidate_index_generation: int
    shared_target_count: int
    shared_row_count: int
    mismatched_target_count: int
    mismatched_row_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        counts = (
            self.baseline_index_generation,
            self.candidate_index_generation,
            self.shared_target_count,
            self.shared_row_count,
            self.mismatched_target_count,
            self.mismatched_row_count,
        )
        if (
            self.status not in {"equal", "mismatch"}
            or not _is_sha256(self.baseline_dataset_hash)
            or not _is_sha256(self.candidate_dataset_hash)
            or any(type(value) is not int or value < 0 for value in counts)
            or self.mismatched_target_count > self.shared_target_count
            or self.mismatched_row_count > self.shared_row_count
            or (self.status == "equal" and self.mismatched_row_count != 0)
            or (self.status == "mismatch" and self.mismatched_row_count == 0)
        ):
            raise ValueError("broad daily panel continuity comparison is invalid")

    def source_safe_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_DAILY_BROAD_PANEL_CONTINUITY_ID,
            "status": self.status,
            "baseline": {
                "dataset_hash": self.baseline_dataset_hash,
                "index_generation": self.baseline_index_generation,
            },
            "candidate": {
                "dataset_hash": self.candidate_dataset_hash,
                "index_generation": self.candidate_index_generation,
            },
            "comparison": {
                "shared_target_count": self.shared_target_count,
                "shared_row_count": self.shared_row_count,
                "mismatched_target_count": self.mismatched_target_count,
                "mismatched_row_count": self.mismatched_row_count,
            },
            "scope": _scope_payload(),
            "artifact_policy": {
                "external_artifact_only": True,
                "raw_market_data_persisted": False,
                "raw_rows_persisted": False,
                "prices_persisted": False,
                "volumes_persisted": False,
                "credentials_accessed": False,
                "network_accessed": False,
                "kis_accessed": False,
                "account_data_persisted": False,
                "order_data_persisted": False,
                "broker_accessed": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisPaperDailyBroadPanelContinuityMaterialization:
    """Immutable external receipt for one broad-panel continuity comparison."""

    comparison: KisPaperDailyBroadPanelContinuityComparison
    receipt_path: Path
    receipt_hash: str

    def __post_init__(self) -> None:
        if (
            not self.receipt_path.is_file()
            or not _is_sha256(self.receipt_hash)
            or not isinstance(self.comparison, KisPaperDailyBroadPanelContinuityComparison)
        ):
            raise ValueError("broad daily panel continuity materialization is invalid")


def build_kis_paper_daily_broad_panel(
    cache_root: Path | str = KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    *,
    repo_root: Path | str | None = None,
    stable_read_attempts: int = 3,
) -> KisPaperDailyBroadPanel:
    """Reattest one byte-stable broad-cache index without touching its lock."""

    if type(stable_read_attempts) is not int or stable_read_attempts <= 0:
        raise ValueError("broad daily panel stable read attempts are invalid")
    repository = _repository_root(repo_root)
    root = _external_existing_root(cache_root, repository, "broad cache")
    registry = load_kis_paper_daily_broad_registry(output_root=root, repo_root=repository)
    _validate_registry(registry)
    index_path = _safe_child(root / _INDEX_FILENAME, root)

    for _attempt in range(stable_read_attempts):
        before_bytes = _read_index_bytes(index_path)
        index = _json_document(before_bytes, "broad daily panel index")
        _validate_current_index(index, registry=registry)
        panel = _build_panel_from_index(
            index=index,
            index_sha256=_sha256(before_bytes),
            registry=registry,
            root=root,
            verify_index_fingerprints=True,
        )
        after_bytes = _read_index_bytes(index_path)
        if before_bytes == after_bytes:
            return panel
    raise ValueError("broad daily panel index changed during reattestation")


def materialize_kis_paper_daily_broad_panel(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    panel_root: Path | str = KIS_PAPER_DAILY_BROAD_PANEL_ROOT,
    artifact_root: Path | str = KIS_PAPER_DAILY_BROAD_PANEL_EVIDENCE_ROOT,
    repo_root: Path | str | None = None,
) -> KisPaperDailyBroadPanelMaterialization:
    """Write immutable, raw-row-free panel provenance outside the repository."""

    panel = build_kis_paper_daily_broad_panel(cache_root, repo_root=repo_root)
    repository = _repository_root(repo_root)
    output_root = _external_output_root(panel_root, repository, "panel root")
    evidence_root = _external_output_root(artifact_root, repository, "artifact root")
    label = f"panel={panel.dataset_hash.removeprefix('sha256:')[:20]}"
    manifest_payload = _manifest_payload(panel)
    manifest_bytes = _json_bytes(manifest_payload)
    manifest_path = output_root / label / "manifest.json"
    _write_or_verify_json(manifest_path, manifest_payload)
    receipt_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_broad_panel_materialization_receipt",
        "version": KIS_PAPER_DAILY_BROAD_PANEL_VERSION,
        "status": "complete",
        "manifest_sha256": _sha256(manifest_bytes),
        "coverage": _coverage_payload(panel),
        "scope": _scope_payload(),
        "artifact_policy": {
            "external_artifact_only": True,
            "raw_market_data_persisted": False,
            "raw_rows_persisted": False,
            "prices_persisted": False,
            "volumes_persisted": False,
            "credentials_accessed": False,
            "network_accessed": False,
            "kis_accessed": False,
            "account_data_persisted": False,
            "order_data_persisted": False,
            "broker_accessed": False,
        },
    }
    receipt_path = evidence_root / label / "receipt.json"
    _write_or_verify_json(receipt_path, receipt_payload)
    return KisPaperDailyBroadPanelMaterialization(
        panel=panel,
        manifest_path=manifest_path,
        manifest_hash=_sha256(manifest_bytes),
        receipt_path=receipt_path,
        receipt_hash=_sha256(receipt_path.read_bytes()),
    )


def load_materialized_kis_paper_daily_broad_panel(
    manifest_path: Path | str,
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    panel_root: Path | str = KIS_PAPER_DAILY_BROAD_PANEL_ROOT,
    repo_root: Path | str | None = None,
) -> KisPaperDailyBroadPanel:
    """Reattach a frozen panel snapshot without consulting the mutable index."""

    repository = _repository_root(repo_root)
    root = _external_existing_root(cache_root, repository, "broad cache")
    output_root = _external_existing_root(panel_root, repository, "panel root")
    path = _safe_child(Path(manifest_path), output_root)
    try:
        payload = _json_document(path.read_bytes(), "broad daily panel manifest")
    except OSError as error:
        raise ValueError("broad daily panel manifest is unreadable") from error
    _reject_raw_fields(payload)
    registry = load_kis_paper_daily_broad_registry(output_root=root, repo_root=repository)
    _validate_registry(registry)
    snapshot, index_sha256 = _snapshot_from_manifest(payload, registry=registry)
    panel = _build_panel_from_index(
        index=snapshot,
        index_sha256=index_sha256,
        registry=registry,
        root=root,
        verify_index_fingerprints=False,
    )
    if payload != _manifest_payload(panel):
        raise ValueError("broad daily panel manifest does not reattest")
    return panel


def compare_kis_paper_daily_broad_panels(
    baseline: KisPaperDailyBroadPanel,
    candidate: KisPaperDailyBroadPanel,
) -> KisPaperDailyBroadPanelContinuityComparison:
    """Compare canonical fingerprints for the two panels' shared target/session rows."""

    if not isinstance(baseline, KisPaperDailyBroadPanel) or not isinstance(
        candidate, KisPaperDailyBroadPanel
    ):
        raise TypeError("broad daily panel continuity comparison requires panels")
    if (
        baseline.registry_sha256 != candidate.registry_sha256
        or baseline.source_manifest_sha256 != candidate.source_manifest_sha256
        or baseline.source_file_sha256 != candidate.source_file_sha256
        or baseline.target_keys != candidate.target_keys
    ):
        raise ValueError("broad daily panels do not share one registry contract")

    shared_target_count = 0
    shared_row_count = 0
    mismatched_target_count = 0
    mismatched_row_count = 0
    for target_key in sorted(set(baseline.bars_by_target) & set(candidate.bars_by_target)):
        baseline_rows = _bar_fingerprints_by_start(baseline.bars_by_target[target_key].bars)
        candidate_rows = _bar_fingerprints_by_start(candidate.bars_by_target[target_key].bars)
        shared_starts = sorted(set(baseline_rows) & set(candidate_rows))
        if not shared_starts:
            continue
        shared_target_count += 1
        shared_row_count += len(shared_starts)
        target_mismatches = sum(
            baseline_rows[start] != candidate_rows[start] for start in shared_starts
        )
        if target_mismatches:
            mismatched_target_count += 1
            mismatched_row_count += target_mismatches

    return KisPaperDailyBroadPanelContinuityComparison(
        status="mismatch" if mismatched_row_count else "equal",
        baseline_dataset_hash=baseline.dataset_hash,
        baseline_index_generation=baseline.index_generation,
        candidate_dataset_hash=candidate.dataset_hash,
        candidate_index_generation=candidate.index_generation,
        shared_target_count=shared_target_count,
        shared_row_count=shared_row_count,
        mismatched_target_count=mismatched_target_count,
        mismatched_row_count=mismatched_row_count,
    )


def materialize_kis_paper_daily_broad_panel_continuity(
    *,
    baseline_manifest_path: Path | str,
    candidate_manifest_path: Path | str,
    cache_root: Path | str = KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    panel_root: Path | str = KIS_PAPER_DAILY_BROAD_PANEL_ROOT,
    artifact_root: Path | str = KIS_PAPER_DAILY_BROAD_PANEL_CONTINUITY_EVIDENCE_ROOT,
    repo_root: Path | str | None = None,
) -> KisPaperDailyBroadPanelContinuityMaterialization:
    """Reattest two frozen panels and write one raw-row-free comparison receipt."""

    repository = _repository_root(repo_root)
    evidence_root = _external_output_root(artifact_root, repository, "continuity evidence root")
    baseline = load_materialized_kis_paper_daily_broad_panel(
        baseline_manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repository,
    )
    candidate = load_materialized_kis_paper_daily_broad_panel(
        candidate_manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repository,
    )
    comparison = compare_kis_paper_daily_broad_panels(baseline, candidate)
    label = (
        "baseline="
        f"{comparison.baseline_dataset_hash.removeprefix('sha256:')[:20]}-candidate="
        f"{comparison.candidate_dataset_hash.removeprefix('sha256:')[:20]}"
    )
    receipt_path = evidence_root / label / "receipt.json"
    receipt = comparison.source_safe_document()
    _write_or_verify_json(receipt_path, receipt)
    return KisPaperDailyBroadPanelContinuityMaterialization(
        comparison=comparison,
        receipt_path=receipt_path,
        receipt_hash=_sha256(receipt_path.read_bytes()),
    )


def _bar_fingerprints_by_start(bars: tuple[Bar, ...]) -> dict[datetime, str]:
    fingerprints: dict[datetime, str] = {}
    for bar in bars:
        if bar.start_ts in fingerprints:
            raise ValueError("broad daily panel stream has duplicate sessions")
        fingerprints[bar.start_ts] = _sha256(
            "\x1f".join(
                (
                    bar.symbol,
                    bar.market,
                    bar.timeframe.value,
                    bar.start_ts.isoformat(),
                    str(bar.open),
                    str(bar.high),
                    str(bar.low),
                    str(bar.close),
                    str(bar.volume),
                    str(bar.complete).lower(),
                )
            ).encode("utf-8")
        )
    return fingerprints


def _build_panel_from_index(
    *,
    index: Mapping[str, object],
    index_sha256: str,
    registry: KisPaperDailyBroadRegistry,
    root: Path,
    verify_index_fingerprints: bool,
) -> KisPaperDailyBroadPanel:
    _validate_index_snapshot(
        index,
        registry=registry,
        require_fingerprints=verify_index_fingerprints,
    )
    target_summaries: dict[str, KisPaperDailyBroadPanelTarget] = {}
    bars_by_target: dict[str, CatalogedBars] = {}
    target_records: dict[str, tuple[Bar, ...]] = {}
    snapshot_targets: list[dict[str, object]] = []

    for target in _targets(index):
        target_key = str(target["target_key"])
        records, row_count, coverage_start, coverage_end, outcome_counts = _load_target_records(
            target=target,
            root=root,
            verify_index_fingerprints=verify_index_fingerprints,
        )
        quarantined = outcome_counts.get("conflict", 0) > 0
        target_summary = KisPaperDailyBroadPanelTarget(
            target_key=target_key,
            state=str(target["state"]),  # type: ignore[arg-type]
            next_anchor_date=str(target["next_anchor_date"]),
            accepted_page_count=int(target["accepted_page_count"]),
            categorical_failure_count=int(target["categorical_failure_count"]),
            last_reason=target.get("last_reason"),  # type: ignore[arg-type]
            chunk_count=len(_target_chunks(target)),
            bar_count=row_count,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            outcome_counts=outcome_counts,
            quarantined=quarantined,
        )
        target_summaries[target_key] = target_summary
        if records and not quarantined:
            target_records[target_key] = records
        snapshot_targets.append(_snapshot_target_payload(target))

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_broad_panel_source_snapshot",
        "cache_contract": KIS_PAPER_DAILY_BROAD_CACHE_VERSION,
        "index_generation": int(index["generation"]),
        "index_sha256": index_sha256,
        "targets": snapshot_targets,
    }
    dataset_hash = _dataset_hash(
        index_sha256=index_sha256,
        registry=registry,
        snapshot=snapshot,
        targets=target_summaries,
    )
    for target_key, records in target_records.items():
        bars_by_target[target_key] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=root / _INDEX_FILENAME,
            bars=records,
        )
    return KisPaperDailyBroadPanel(
        dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
        dataset_hash=dataset_hash,
        registry_sha256=registry.registry_sha256,
        source_manifest_sha256=registry.source_manifest_sha256,
        source_file_sha256=registry.source_file_sha256,
        index_sha256=index_sha256,
        index_generation=int(index["generation"]),
        source_root=root,
        target_keys=registry.target_keys,
        targets_by_key=MappingProxyType(target_summaries),
        bars_by_target=MappingProxyType(bars_by_target),
        source_snapshot=MappingProxyType(snapshot),
    )


def _load_target_records(
    *,
    target: Mapping[str, object],
    root: Path,
    verify_index_fingerprints: bool,
) -> tuple[tuple[Bar, ...], int, str | None, str | None, Mapping[str, int]]:
    target_key = str(target["target_key"])
    symbol, exchange = target_key.split("/", maxsplit=1)
    rows: dict[date, tuple[Bar, str]] = {}
    expected_cursor = str(target["initial_anchor_date"])
    outcomes: Counter[str] = Counter()
    for chunk in _target_chunks(target):
        input_cursor = str(chunk["input_cursor_date"])
        output_cursor = str(chunk["output_cursor_date"])
        if input_cursor != expected_cursor:
            raise ValueError("broad daily panel target cursor is invalid")
        outcome = str(chunk["outcome"])
        outcomes[outcome] += 1
        expected_fingerprints = chunk.get("row_fingerprints")
        chunk_rows = _load_chunk_records(
            chunk=chunk,
            root=root,
            symbol=symbol,
            exchange=exchange,
            target_key=target_key,
            expected_fingerprints=(
                expected_fingerprints if verify_index_fingerprints else None
            ),
        )
        for session, (bar, fingerprint) in chunk_rows.items():
            prior = rows.get(session)
            if prior is not None and prior[1] != fingerprint:
                raise ValueError("broad daily panel cross-chunk row drift")
            rows[session] = (bar, fingerprint)
        if outcome in _USABLE_CHUNK_OUTCOMES and output_cursor < input_cursor:
            expected_cursor = output_cursor
        elif outcome == "conflict":
            continue
        elif outcome == "source_limited":
            continue
        else:
            raise ValueError("broad daily panel chunk cursor is invalid")
    if str(target["next_anchor_date"]) != expected_cursor:
        raise ValueError("broad daily panel target cursor is invalid")
    sessions = tuple(sorted(rows))
    records = tuple(rows[session][0] for session in sessions)
    return (
        records,
        len(records),
        None if not sessions else sessions[0].isoformat(),
        None if not sessions else sessions[-1].isoformat(),
        MappingProxyType(dict(sorted(outcomes.items()))),
    )


def _load_chunk_records(
    *,
    chunk: Mapping[str, object],
    root: Path,
    symbol: str,
    exchange: str,
    target_key: str,
    expected_fingerprints: object | None,
) -> dict[date, tuple[Bar, str]]:
    manifest_path = _safe_relative_child(root, _chunk_manifest_ref(chunk))
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        raise ValueError("broad daily panel source manifest is unreadable") from error
    if _sha256(manifest_bytes) != _chunk_manifest_sha256(chunk):
        raise ValueError("broad daily panel source manifest hash mismatch")
    manifest = _json_document(manifest_bytes, "broad daily panel source manifest")
    source = _required_mapping(manifest, "source", "broad daily panel source manifest")
    backfill = _required_mapping(manifest, "backfill", "broad daily panel source manifest")
    files = _required_mapping(manifest, "files", "broad daily panel source manifest")
    raw_document = _required_mapping(files, "raw_daily_rows", "broad daily panel source manifest")
    if (
        manifest.get("collector_objective_id") != KIS_PAPER_DAILY_BROAD_CACHE_VERSION
        or manifest.get("collector_version") != KIS_PAPER_DAILY_BROAD_CACHE_VERSION
        or source.get("symbol") != symbol
        or source.get("exchange") != exchange
        or source.get("endpoint") != "dailyprice"
        or source.get("adjustment_mode") != "MODP=0_unadjusted"
        or backfill.get("contract_version") != KIS_PAPER_DAILY_BROAD_CACHE_VERSION
        or backfill.get("cursor_strategy") != "oldest_session_date_with_exact_overlap"
        or backfill.get("logical_cursor_persisted") is not True
        or backfill.get("target_key") != f"{target_key}/MODP=0"
        or backfill.get("input_cursor_date") != chunk["input_cursor_date"]
        or backfill.get("output_cursor_date") != chunk["output_cursor_date"]
        or raw_document.get("format") != "csv.gz"
        or raw_document.get("ordering") != "session_date_ascending"
        or raw_document.get("columns") != list(_RAW_COLUMNS)
        or raw_document.get("sha256") != _chunk_raw_sha256(chunk)
        or not isinstance(raw_document.get("size_bytes"), int)
    ):
        raise ValueError("broad daily panel source manifest is incompatible")
    raw_path = _safe_relative_child(
        manifest_path.parent,
        _required_text(raw_document, "path", "raw document"),
    )
    try:
        raw_bytes = raw_path.read_bytes()
    except OSError as error:
        raise ValueError("broad daily panel raw data is unreadable") from error
    if (
        len(raw_bytes) != raw_document["size_bytes"]
        or _sha256(raw_bytes) != _chunk_raw_sha256(chunk)
    ):
        raise ValueError("broad daily panel raw hash mismatch")
    records, fingerprints = _parse_raw_records(raw_bytes, symbol=symbol, exchange=exchange)
    if (
        not records
        or min(session.strftime("%Y%m%d") for session in records)
        != chunk["output_cursor_date"]
    ):
        raise ValueError("broad daily panel source cursor is invalid")
    if expected_fingerprints is not None:
        if not isinstance(expected_fingerprints, Mapping) or dict(expected_fingerprints) != {
            session.isoformat(): fingerprint for session, fingerprint in fingerprints.items()
        }:
            raise ValueError("broad daily panel index row lineage is invalid")
    requests = _required_mapping(manifest, "requests", "broad daily panel source manifest")
    if requests.get("accepted_pages") != chunk["accepted_page_count"]:
        raise ValueError("broad daily panel source request facts are invalid")
    return {
        session: (records[session], fingerprints[session])
        for session in sorted(records)
    }


def _parse_raw_records(
    raw_bytes: bytes,
    *,
    symbol: str,
    exchange: str,
) -> tuple[dict[date, Bar], dict[date, str]]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes), mode="rb") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
                    raise ValueError("schema")
                rows: dict[date, Bar] = {}
                fingerprints: dict[date, str] = {}
                prior_session: date | None = None
                for document in reader:
                    if set(document) != set(_RAW_COLUMNS) or any(
                        document.get(column) is None for column in _RAW_COLUMNS
                    ):
                        raise ValueError("contents")
                    if document["symbol"] != symbol or document["exchange"] != exchange:
                        raise ValueError("contents")
                    session = _parse_iso_date(str(document["session_date"]))
                    if prior_session is not None and session <= prior_session:
                        raise ValueError("contents")
                    record = tuple(str(document[column]) for column in _RAW_COLUMNS)
                    rows[session] = Bar(
                        symbol=symbol,
                        market="US",
                        timeframe=Timeframe.D1,
                        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
                        open=Decimal(record[3]),
                        high=Decimal(record[4]),
                        low=Decimal(record[5]),
                        close=Decimal(record[6]),
                        volume=Decimal(record[7]),
                        complete=True,
                    )
                    fingerprints[session] = _sha256("\x1f".join(record).encode("utf-8"))
                    prior_session = session
    except (OSError, UnicodeDecodeError, csv.Error, InvalidOperation, ValueError) as error:
        raise ValueError("broad daily panel raw contents are invalid") from error
    return rows, fingerprints


def _validate_current_index(
    index: Mapping[str, object], *, registry: KisPaperDailyBroadRegistry
) -> None:
    _validate_index_snapshot(index, registry=registry, require_fingerprints=True)
    expected_registry = {
        "version": registry.version,
        "registry_sha256": registry.registry_sha256,
        "source_manifest_sha256": registry.source_manifest_sha256,
        "source_file_sha256": registry.source_file_sha256,
        "target_count": len(registry.targets),
        "bootstrap_target_count": len(registry.bootstrap_targets),
        "current_listing_only": True,
        "non_pit": True,
        "non_ranking": True,
    }
    if (
        index.get("schema_version") != SCHEMA_VERSION
        or index.get("kind") != "kis_paper_daily_broad_backfill_index"
        or index.get("version") != KIS_PAPER_DAILY_BROAD_CACHE_VERSION
        or index.get("initial_anchor_date") != "20260728"
        or index.get("registry") != expected_registry
        or index.get("storage")
        != {"private_local_only": True, "served": False, "redistributed": False}
        or index.get("redaction")
        != {"credentials_persisted": False, "account_facts_persisted": False}
    ):
        raise ValueError("broad daily panel index is incompatible")


def _validate_index_snapshot(
    index: Mapping[str, object],
    *,
    registry: KisPaperDailyBroadRegistry,
    require_fingerprints: bool,
) -> None:
    if (
        not isinstance(index.get("generation"), int)
        or int(index["generation"]) < 0
        or not isinstance(index.get("targets"), list)
    ):
        raise ValueError("broad daily panel index is invalid")
    targets = _targets(index)
    if len(targets) != len(registry.targets):
        raise ValueError("broad daily panel index target count is invalid")
    for target, registry_target in zip(targets, registry.targets, strict=True):
        if (
            target.get("target_key") != registry_target.key
            or target.get("symbol") != registry_target.symbol
            or target.get("exchange") != registry_target.exchange
            or target.get("initial_anchor_date") != "20260728"
            or target.get("state") not in _TARGET_STATES
            or not _is_compact_date(target.get("next_anchor_date"))
            or not isinstance(target.get("accepted_page_count"), int)
            or int(target["accepted_page_count"]) < 0
            or not isinstance(target.get("categorical_failure_count"), int)
            or int(target["categorical_failure_count"]) < 0
            or (
                target.get("last_reason") is not None
                and not isinstance(target.get("last_reason"), str)
            )
        ):
            raise ValueError("broad daily panel index target is invalid")
        for chunk in _target_chunks(target):
            _validate_chunk(chunk, require_fingerprints=require_fingerprints)


def _validate_chunk(chunk: Mapping[str, object], *, require_fingerprints: bool) -> None:
    if (
        not _is_compact_date(chunk.get("input_cursor_date"))
        or not _is_compact_date(chunk.get("output_cursor_date"))
        or not _is_relative_ref(chunk.get("manifest_ref", chunk.get("manifest_path")))
        or not _is_sha256(chunk.get("manifest_sha256", chunk.get("manifest_hash")))
        or not _is_sha256(chunk.get("raw_sha256", chunk.get("raw_hash")))
        or not isinstance(chunk.get("accepted_page_count"), int)
        or int(chunk["accepted_page_count"]) < 0
        or not isinstance(chunk.get("exact_overlap_rows"), int)
        or int(chunk["exact_overlap_rows"]) < 0
        or not isinstance(chunk.get("conflicting_overlap_rows"), int)
        or int(chunk["conflicting_overlap_rows"]) < 0
        or chunk.get("outcome") not in _CHUNK_OUTCOMES
        or chunk.get("reason") is not None and not isinstance(chunk.get("reason"), str)
    ):
        raise ValueError("broad daily panel index chunk is invalid")
    fingerprints = chunk.get("row_fingerprints")
    if require_fingerprints:
        if not isinstance(fingerprints, Mapping) or not fingerprints:
            raise ValueError("broad daily panel index row lineage is invalid")
        if any(
            not _is_iso_date(session) or not _is_sha256(fingerprint)
            for session, fingerprint in fingerprints.items()
        ):
            raise ValueError("broad daily panel index row lineage is invalid")
    elif fingerprints is not None:
        raise ValueError("broad daily panel source snapshot is invalid")


def _snapshot_target_payload(target: Mapping[str, object]) -> dict[str, object]:
    return {
        "target_key": str(target["target_key"]),
        "symbol": str(target["symbol"]),
        "exchange": str(target["exchange"]),
        "initial_anchor_date": str(target["initial_anchor_date"]),
        "next_anchor_date": str(target["next_anchor_date"]),
        "state": str(target["state"]),
        "accepted_page_count": int(target["accepted_page_count"]),
        "categorical_failure_count": int(target["categorical_failure_count"]),
        "last_reason": target.get("last_reason"),
        "chunks": [
            {
                "input_cursor_date": str(chunk["input_cursor_date"]),
                "output_cursor_date": str(chunk["output_cursor_date"]),
                "manifest_ref": _chunk_manifest_ref(chunk),
                "manifest_sha256": _chunk_manifest_sha256(chunk),
                "raw_sha256": _chunk_raw_sha256(chunk),
                "accepted_page_count": int(chunk["accepted_page_count"]),
                "exact_overlap_rows": int(chunk["exact_overlap_rows"]),
                "conflicting_overlap_rows": int(chunk["conflicting_overlap_rows"]),
                "outcome": str(chunk["outcome"]),
                "reason": chunk.get("reason"),
            }
            for chunk in _target_chunks(target)
        ],
    }


def _chunk_manifest_ref(chunk: Mapping[str, object]) -> str:
    value = chunk.get("manifest_ref", chunk.get("manifest_path"))
    if not _is_relative_ref(value):
        raise ValueError("broad daily panel index chunk is invalid")
    return str(value)


def _chunk_manifest_sha256(chunk: Mapping[str, object]) -> str:
    value = chunk.get("manifest_sha256", chunk.get("manifest_hash"))
    if not _is_sha256(value):
        raise ValueError("broad daily panel index chunk is invalid")
    return str(value)


def _chunk_raw_sha256(chunk: Mapping[str, object]) -> str:
    value = chunk.get("raw_sha256", chunk.get("raw_hash"))
    if not _is_sha256(value):
        raise ValueError("broad daily panel index chunk is invalid")
    return str(value)


def _snapshot_from_manifest(
    payload: Mapping[str, object],
    *,
    registry: KisPaperDailyBroadRegistry,
) -> tuple[dict[str, object], str]:
    source = _required_mapping(payload, "source", "broad daily panel manifest")
    snapshot = _required_mapping(payload, "source_snapshot", "broad daily panel manifest")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_DAILY_BROAD_PANEL_ID
        or payload.get("version") != KIS_PAPER_DAILY_BROAD_PANEL_VERSION
        or source.get("cache_contract") != KIS_PAPER_DAILY_BROAD_CACHE_VERSION
        or source.get("registry_version") != KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION
        or source.get("registry_sha256") != registry.registry_sha256
        or source.get("source_manifest_sha256") != registry.source_manifest_sha256
        or source.get("source_file_sha256") != registry.source_file_sha256
        or snapshot.get("schema_version") != SCHEMA_VERSION
        or snapshot.get("kind") != "kis_paper_daily_broad_panel_source_snapshot"
        or snapshot.get("cache_contract") != KIS_PAPER_DAILY_BROAD_CACHE_VERSION
        or not isinstance(snapshot.get("index_generation"), int)
        or not _is_sha256(snapshot.get("index_sha256"))
        or not isinstance(snapshot.get("targets"), list)
    ):
        raise ValueError("broad daily panel manifest is invalid")
    index = {
        "generation": int(snapshot["index_generation"]),
        "targets": list(snapshot["targets"]),
    }
    _validate_index_snapshot(index, registry=registry, require_fingerprints=False)
    return index, str(snapshot["index_sha256"])


def _manifest_payload(panel: KisPaperDailyBroadPanel) -> dict[str, object]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_DAILY_BROAD_PANEL_ID,
        "version": KIS_PAPER_DAILY_BROAD_PANEL_VERSION,
        "status": "complete",
        "dataset": {
            "dataset_id": panel.dataset_id,
            "dataset_hash": panel.dataset_hash,
        },
        "source": {
            "cache_contract": KIS_PAPER_DAILY_BROAD_CACHE_VERSION,
            "registry_version": KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
            "registry_sha256": panel.registry_sha256,
            "source_manifest_sha256": panel.source_manifest_sha256,
            "source_file_sha256": panel.source_file_sha256,
            "index_sha256": panel.index_sha256,
        },
        "scope": _scope_payload(),
        "coverage": _coverage_payload(panel),
        "targets": [panel.targets_by_key[key].to_payload() for key in panel.target_keys],
        "source_snapshot": dict(panel.source_snapshot),
        "limitations": list(panel.limitations),
        "eligibility": {
            "source_local_development_input": True,
            "historical_point_in_time": False,
            "corporate_action_qualified": False,
            "ranking": False,
            "model_training": False,
            "paper": False,
            "live": False,
        },
        "artifact_policy": {
            "raw_market_data_in_manifest": False,
            "raw_rows_in_manifest": False,
            "prices_in_manifest": False,
            "volumes_in_manifest": False,
            "credentials_accessed": False,
            "network_accessed": False,
            "kis_accessed": False,
            "broker_accessed": False,
        },
    }
    _reject_raw_fields(payload)
    return payload


def _scope_payload() -> dict[str, object]:
    return {
        "provider": "KIS Open API virtual paper",
        "endpoint": "dailyprice",
        "market": "US",
        "timeframe": Timeframe.D1.value,
        "adjustment_mode": "MODP=0_unadjusted",
        "current_listing_only": True,
        "non_pit": True,
        "non_ranking": True,
        "corporate_action_qualified": False,
        "session_finality_attested": False,
        "cross_source_blending_allowed": False,
    }


def _coverage_payload(panel: KisPaperDailyBroadPanel) -> dict[str, object]:
    return {
        "target_count": len(panel.target_keys),
        "covered_target_count": panel.covered_target_count,
        "zero_coverage_target_count": panel.zero_coverage_target_count,
        "quarantined_target_count": panel.quarantined_target_count,
        "index_generation": panel.index_generation,
    }


def _dataset_hash(
    *,
    index_sha256: str,
    registry: KisPaperDailyBroadRegistry,
    snapshot: Mapping[str, object],
    targets: Mapping[str, KisPaperDailyBroadPanelTarget],
) -> str:
    return _sha256(
        _json_bytes(
            {
                "version": KIS_PAPER_DAILY_BROAD_PANEL_VERSION,
                "registry_sha256": registry.registry_sha256,
                "index_sha256": index_sha256,
                "source_snapshot": snapshot,
                "targets": [targets[key].to_payload() for key in registry.target_keys],
            }
        )
    )


def _validate_registry(registry: KisPaperDailyBroadRegistry) -> None:
    if (
        registry.version != KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION
        or not _is_sha256(registry.registry_sha256)
        or not _is_sha256(registry.source_manifest_sha256)
        or not _is_sha256(registry.source_file_sha256)
        or not registry.scope.current_listing_only
        or not registry.scope.non_pit
        or not registry.scope.non_ranking
        or registry.scope.provider_price_data
        or tuple(sorted(registry.target_keys)) != registry.target_keys
    ):
        raise ValueError("broad daily panel registry is invalid")


def _targets(index: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = index.get("targets")
    if not isinstance(value, list) or any(not isinstance(target, Mapping) for target in value):
        raise ValueError("broad daily panel index targets are invalid")
    return list(value)


def _target_chunks(target: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = target.get("chunks")
    if not isinstance(value, list) or any(not isinstance(chunk, Mapping) for chunk in value):
        raise ValueError("broad daily panel target chunks are invalid")
    return list(value)


def _read_index_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("broad daily panel index is unavailable")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValueError("broad daily panel index is unreadable") from error


def _external_existing_root(root: Path | str, repository: Path, label: str) -> Path:
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError(f"broad daily panel {label} is invalid")
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError(f"broad daily panel {label} is invalid") from error
    mounted_market_data = repository / "market_data"
    permitted_mount = (
        not mounted_market_data.is_symlink()
        and mounted_market_data.is_mount()
        and resolved.is_relative_to(mounted_market_data.resolve())
    )
    if resolved.is_relative_to(repository) and not permitted_mount:
        raise ValueError(f"broad daily panel {label} must stay outside Git")
    return resolved


def _external_output_root(root: Path | str, repository: Path, label: str) -> Path:
    candidate = Path(root)
    if candidate.is_symlink():
        raise ValueError(f"broad daily panel {label} is invalid")
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError(f"broad daily panel {label} is invalid") from error
    if resolved.is_relative_to(repository):
        raise ValueError(f"broad daily panel {label} must stay outside Git")
    return resolved


def _repository_root(repo_root: Path | str | None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("broad daily panel repository root is invalid")
    return root.resolve()


def _safe_child(path: Path, root: Path) -> Path:
    candidate = Path(os.path.abspath(path if path.is_absolute() else root / path))
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("broad daily panel path is invalid")
    current = candidate
    while current != root.resolve():
        if current.is_symlink():
            raise ValueError("broad daily panel path is invalid")
        parent = current.parent
        if parent == current:
            raise ValueError("broad daily panel path is invalid")
        current = parent
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError("broad daily panel path is invalid") from error
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("broad daily panel path is invalid")
    return resolved


def _safe_relative_child(root: Path, reference: str) -> Path:
    relative = Path(reference)
    if not _is_relative_ref(reference) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("broad daily panel source reference is invalid")
    return _safe_child(root / relative, root)


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> None:
    _reject_raw_fields(payload)
    encoded = _json_bytes(payload)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != encoded:
            raise FileExistsError("broad daily panel output is immutable")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        if path.exists() or path.is_symlink():
            raise FileExistsError("broad daily panel output is immutable")
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _json_document(payload: bytes, label: str) -> dict[str, object]:
    try:
        result = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not isinstance(result, dict):
        raise ValueError(f"{label} is invalid")
    return result


def _required_mapping(value: Mapping[str, object], key: str, label: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError(f"{label} is invalid")
    return result


def _required_text(value: Mapping[str, object], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{label} is invalid")
    return result


def _reject_raw_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in _SAFE_FIELD_NAMES:
                raise ValueError("broad daily panel output contains raw fields")
            _reject_raw_fields(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_raw_fields(nested)


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _is_compact_date(value: object) -> bool:
    return isinstance(value, str) and len(value) == 8 and value.isdigit()


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _parse_iso_date(value: str) -> date:
    if not _is_iso_date(value):
        raise ValueError("broad daily panel session date is invalid")
    return date.fromisoformat(value)


def _is_relative_ref(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _is_target_key(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip().upper() or value.count("/") != 1:
        return False
    symbol, exchange = value.split("/", maxsplit=1)
    return bool(symbol) and exchange == "NAS"
