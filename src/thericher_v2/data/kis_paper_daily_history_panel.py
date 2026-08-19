"""Offline materialization of the terminal KIS Paper NAS daily-history cache.

The historical collector owns the raw cache.  This module only re-attests its
immutable snapshot chain, exposes source-local completed D1 streams, and writes
small provenance receipts outside Git.  It has no KIS client, environment
lookup, network, account, order, ranking, or model dependency.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import pandas_market_calendars as mcal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.local import (
    CatalogedBars,
    _cataloged_bars_from_verified_loader,
    _validate_sha256,
)
from thericher_v2.data.official_symbol_directory_nas_probe import (
    NAS_COMMON_STOCK_PROBE_SYMBOLS,
    NAS_EXCHANGE,
)

KIS_PAPER_DAILY_HISTORY_PANEL_VERSION = "kis-paper-daily-nas-history-panel-v1"
KIS_PAPER_DAILY_HISTORY_PANEL_ID = "kis.paper.private.daily.nas.history.panel-v1"
KIS_PAPER_DAILY_HISTORY_CACHE_VERSION = "kis-paper-daily-nas-history-v1"
KIS_PAPER_DAILY_HISTORY_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-history/v1"
)
KIS_PAPER_DAILY_HISTORY_PANEL_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-history-panel/v1"
)
KIS_PAPER_DAILY_HISTORY_PANEL_EVIDENCE_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/kis-paper-daily-nas-history-panel-v1"
)
KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE = "MODP=0_unadjusted"
KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS = tuple(NAS_COMMON_STOCK_PROBE_SYMBOLS)
KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS = tuple(
    f"{symbol}/{NAS_EXCHANGE}" for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
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
_TERMINAL_TARGET_STATES = frozenset({"complete", "source_limited"})
_USABLE_CHUNK_OUTCOMES = frozenset(
    {"committed", "partial", "complete", "source_limited"}
)
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "cross_chunk_duplicate_conflict",
        "daily_duplicate_conflict",
        "daily_page_limit_exceeded",
        "daily_response_invalid",
        "daily_response_rejected",
        "empty_daily_response",
        "no_cursor_progress",
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "token_request_not_due",
        "transport_failure",
        "unexpected_private_daily_collector_error",
    }
)
_SOURCE_REGISTRY = {
    "version": "official-symbol-directory-nas-probe-r1",
    "registry_sha256": "sha256:58c894236425755cb18c60a576944e33f88f9c6221e75405d6de5b4a6fa27935",
    "source_manifest_sha256": (
        "sha256:129e6aa02a27e8760139a901f13e2ee4e3fc9b5d4a3e615f9dcd431154aecea4"
    ),
    "source_file_sha256": "sha256:cf9f42bbff4cdcec0335c5acf42c1ffe889039b5f1e48f60374120045513f6bb",
    "target_keys": list(KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS),
    "prospective_only": True,
    "historical_point_in_time_eligible": False,
}
_INDEX_STORAGE = {"private_local_only": True, "served": False, "redistributed": False}
_INDEX_REDACTION = {
    "credentials_persisted": False,
    "account_facts_persisted": False,
    "request_headers_persisted": False,
    "response_bodies_persisted": False,
    "raw_rows_in_index": False,
}
_RAW_LIMITATIONS = (
    "MODP=0_unadjusted",
    "corporate_action_semantics_not_qualified",
    "current_listing_registry_not_point_in_time_universe",
    "source_local_only_no_cross_source_blend",
)
_SESSION_CALENDAR_ALIAS = "NASDAQ"
_SESSION_CALENDAR_NAME = "NYSE"
_SESSION_CALENDAR_PACKAGE = "pandas_market_calendars"
_SESSION_CALENDAR_VERSION = "5.4.0"
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


@dataclass(frozen=True, slots=True)
class KisPaperDailyHistoryPanelTarget:
    """Source-safe coverage and terminal state for one source-local stream."""

    target_key: str
    state: Literal["complete", "source_limited"]
    last_reason: str | None
    chunk_count: int
    bar_count: int
    coverage_start_bucket: str
    coverage_end_bucket: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.target_key not in KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
            or self.state not in _TERMINAL_TARGET_STATES
            or self.last_reason not in _SAFE_FAILURE_REASONS | {None}
            or self.chunk_count <= 0
            or self.bar_count <= 0
            or not _is_coverage_bucket(self.coverage_start_bucket)
            or not _is_coverage_bucket(self.coverage_end_bucket)
            or self.coverage_start_bucket > self.coverage_end_bucket
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS paper daily history panel target is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "state": self.state,
            "last_reason": self.last_reason,
            "chunk_count": self.chunk_count,
            "bar_count": self.bar_count,
            "coverage_start_bucket": self.coverage_start_bucket,
            "coverage_end_bucket": self.coverage_end_bucket,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class KisPaperDailyHistoryPanel:
    """Hash-attested source-local NAS D1 streams with an optional common subset."""

    dataset_id: str
    dataset_hash: str
    index_hash: str
    index_path: Path
    source_root: Path
    adjustment_mode: str
    bars_by_symbol: Mapping[str, CatalogedBars]
    targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget]
    common_sessions: tuple[date, ...]
    raw_price_limitations: tuple[str, ...] = _RAW_LIMITATIONS
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        streams = MappingProxyType(dict(self.bars_by_symbol))
        targets = MappingProxyType(dict(self.targets_by_key))
        sessions = tuple(self.common_sessions)
        if (
            self.dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
            or self.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE
            or tuple(streams) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or tuple(targets) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
            or self.raw_price_limitations != _RAW_LIMITATIONS
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS paper daily history panel is invalid")
        _validate_sha256(self.dataset_hash, "dataset_hash")
        _validate_sha256(self.index_hash, "index_hash")
        if self.index_path.is_symlink() or self.source_root.is_symlink():
            raise ValueError("KIS paper daily history panel path is invalid")
        for symbol, stream in streams.items():
            target_key = f"{symbol}/{NAS_EXCHANGE}"
            target = targets.get(target_key)
            if (
                target is None
                or stream.dataset_id != self.dataset_id
                or stream.dataset_hash != self.dataset_hash
                or stream.source_path != self.index_path
                or not stream.bars
                or len(stream.bars) != target.bar_count
                or any(
                    bar.symbol != symbol
                    or bar.market != "US"
                    or bar.timeframe is not Timeframe.D1
                    or not bar.complete
                    for bar in stream.bars
                )
                or tuple(bar.start_ts.date() for bar in stream.bars)
                != tuple(sorted(bar.start_ts.date() for bar in stream.bars))
            ):
                raise ValueError("KIS paper daily history panel stream is invalid")
        expected_common = _common_sessions(
            tuple(
                {bar.start_ts.date() for bar in stream.bars}
                for stream in streams.values()
            )
        )
        if sessions != expected_common:
            raise ValueError("KIS paper daily history panel common sessions are invalid")
        object.__setattr__(self, "bars_by_symbol", streams)
        object.__setattr__(self, "targets_by_key", targets)
        object.__setattr__(self, "common_sessions", sessions)

    @property
    def common_intersection_available(self) -> bool:
        return bool(self.common_sessions)


@dataclass(frozen=True, slots=True)
class KisPaperDailyHistoryPanelMaterialization:
    """Immutable local manifest and source-safe external receipt for one panel."""

    panel: KisPaperDailyHistoryPanel
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
            raise ValueError("KIS paper daily history panel materialization is invalid")


def build_kis_paper_daily_history_panel(
    cache_root: Path | str = KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    *,
    repo_root: Path | str | None = None,
) -> KisPaperDailyHistoryPanel:
    """Re-attest the terminal source cache and expose immutable D1 streams."""

    root = _external_existing_root(cache_root, repo_root, "history cache")
    index_path = _safe_child(root / _INDEX_FILENAME, root)
    try:
        index_bytes = index_path.read_bytes()
    except OSError as error:
        raise ValueError("KIS paper daily history panel index is unreadable") from error
    index_hash = _sha256(index_bytes)
    index = _json_document(index_bytes, "KIS paper daily history panel index")
    _validate_index(index)

    rows_by_target: dict[str, dict[date, tuple[str, ...]]] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for target in index["targets"]:
        if not isinstance(target, Mapping):  # _validate_index already proves this.
            raise ValueError("KIS paper daily history panel target is invalid")
        target_key = str(target["target_key"])
        rows = _load_target_rows(target=target, target_key=target_key, root=root)
        rows_by_target[target_key] = rows
        sessions = tuple(sorted(rows))
        targets_by_key[target_key] = KisPaperDailyHistoryPanelTarget(
            target_key=target_key,
            state=str(target["state"]),  # type: ignore[arg-type]
            last_reason=target.get("last_reason"),  # type: ignore[arg-type]
            chunk_count=len(target["chunks"]),
            bar_count=len(rows),
            coverage_start_bucket=_coverage_bucket(sessions[0]),
            coverage_end_bucket=_coverage_bucket(sessions[-1]),
        )

    common_sessions = _common_sessions(tuple(set(rows) for rows in rows_by_target.values()))
    _validate_expected_us_equity_session_coverage(common_sessions)
    dataset_hash = _dataset_hash(
        index_hash=index_hash,
        rows_by_target=rows_by_target,
        targets_by_key=targets_by_key,
        common_sessions=common_sessions,
    )
    bars_by_symbol: dict[str, CatalogedBars] = {}
    for target_key in KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS:
        symbol, _exchange = target_key.split("/", maxsplit=1)
        bars = tuple(
            _bar_from_record(rows_by_target[target_key][session])
            for session in sorted(rows_by_target[target_key])
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=dataset_hash,
        index_hash=index_hash,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=common_sessions,
    )


def materialize_kis_paper_daily_history_panel(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    panel_root: Path | str = KIS_PAPER_DAILY_HISTORY_PANEL_ROOT,
    artifact_root: Path | str = KIS_PAPER_DAILY_HISTORY_PANEL_EVIDENCE_ROOT,
    repo_root: Path | str | None = None,
) -> KisPaperDailyHistoryPanelMaterialization:
    """Write immutable local provenance and an external safe receipt."""

    panel = build_kis_paper_daily_history_panel(cache_root, repo_root=repo_root)
    repository = _repository_root(repo_root)
    output_root = _external_output_root(panel_root, repository, "panel root")
    evidence_root = _external_output_root(artifact_root, repository, "artifact root")
    label = f"panel={panel.dataset_hash.removeprefix('sha256:')[:20]}"
    manifest_path = output_root / label / "manifest.json"
    manifest_payload = _manifest_payload(panel)
    manifest_hash = _sha256(_json_bytes(manifest_payload))
    _write_or_verify_json(manifest_path, manifest_payload)

    receipt_path = evidence_root / label / "receipt.json"
    receipt_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_history_panel_materialization_receipt",
        "status": "complete",
        "manifest_sha256": manifest_hash,
        "panel": manifest_payload,
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
            "model_output_persisted": False,
        },
    }
    _write_or_verify_json(receipt_path, receipt_payload)
    return KisPaperDailyHistoryPanelMaterialization(
        panel=panel,
        manifest_path=manifest_path,
        manifest_hash=manifest_hash,
        receipt_path=receipt_path,
        receipt_hash=_sha256(receipt_path.read_bytes()),
    )


def load_materialized_kis_paper_daily_history_panel(
    manifest_path: Path | str,
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    panel_root: Path | str = KIS_PAPER_DAILY_HISTORY_PANEL_ROOT,
    repo_root: Path | str | None = None,
) -> KisPaperDailyHistoryPanel:
    """Rebuild and compare a source-local panel before a later consumer uses it."""

    repository = _repository_root(repo_root)
    root = _external_existing_root(panel_root, repository, "panel root")
    path = _safe_child(Path(manifest_path), root)
    try:
        payload = _json_document(path.read_bytes(), "KIS paper daily history panel manifest")
    except OSError as error:
        raise ValueError("KIS paper daily history panel manifest is unreadable") from error
    _reject_raw_fields(payload)
    panel = build_kis_paper_daily_history_panel(cache_root, repo_root=repository)
    if payload != _manifest_payload(panel):
        raise ValueError("KIS paper daily history panel manifest does not reattest")
    return panel


def _load_target_rows(
    *,
    target: Mapping[str, object],
    target_key: str,
    root: Path,
) -> dict[date, tuple[str, ...]]:
    chunks = target.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("KIS paper daily history panel target is invalid")
    symbol, exchange = target_key.split("/", maxsplit=1)
    rows: dict[date, tuple[str, ...]] = {}
    prior_cursor: str | None = None
    usable_chunk_count = 0
    for chunk in chunks:
        _validate_chunk(chunk)
        if not isinstance(chunk, Mapping):  # pragma: no cover - validated above.
            raise ValueError("KIS paper daily history panel chunk is invalid")
        outcome = str(chunk["outcome"])
        if outcome == "conflict":
            raise ValueError("KIS paper daily history panel has a conflicting source chunk")
        if outcome not in _USABLE_CHUNK_OUTCOMES:
            continue
        input_cursor = str(chunk["input_cursor_date"])
        output_cursor = str(chunk["output_cursor_date"])
        if prior_cursor is not None and input_cursor != prior_cursor:
            raise ValueError("KIS paper daily history panel cursor chain is invalid")
        if output_cursor > input_cursor or (
            output_cursor == input_cursor and outcome != "source_limited"
        ):
            raise ValueError("KIS paper daily history panel cursor progress is invalid")
        chunk_rows = _load_chunk_rows(
            chunk=chunk,
            root=root,
            symbol=symbol,
            exchange=exchange,
            target_key=target_key,
        )
        for session, record in chunk_rows.items():
            prior = rows.get(session)
            if prior is not None and prior != record:
                raise ValueError("KIS paper daily history panel duplicate conflict")
            rows[session] = record
        prior_cursor = output_cursor
        usable_chunk_count += 1
    if usable_chunk_count != len(chunks) or not rows:
        raise ValueError("KIS paper daily history panel source chunks are invalid")
    return rows


def _load_chunk_rows(
    *,
    chunk: Mapping[str, object],
    root: Path,
    symbol: str,
    exchange: str,
    target_key: str,
) -> dict[date, tuple[str, ...]]:
    manifest_path = _safe_child(root / str(chunk["manifest_path"]), root)
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        raise ValueError("KIS paper daily history panel manifest is unreadable") from error
    if _sha256(manifest_bytes) != chunk["manifest_sha256"]:
        raise ValueError("KIS paper daily history panel manifest hash is invalid")
    manifest = _json_document(manifest_bytes, "KIS paper daily history panel manifest")
    source = manifest.get("source")
    context = manifest.get("backfill")
    files = manifest.get("files")
    if (
        not isinstance(source, Mapping)
        or not isinstance(context, Mapping)
        or not isinstance(files, Mapping)
    ):
        raise ValueError("KIS paper daily history panel manifest is invalid")
    if (
        manifest.get("kind") != "kis_paper_private_daily_cache"
        or manifest.get("collector_objective_id") != KIS_PAPER_DAILY_HISTORY_CACHE_VERSION
        or manifest.get("collector_version") != KIS_PAPER_DAILY_HISTORY_CACHE_VERSION
        or source.get("symbol") != symbol
        or source.get("exchange") != exchange
        or source.get("endpoint") != "dailyprice"
        or source.get("adjustment_mode") != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE
        or context.get("contract_version") != KIS_PAPER_DAILY_HISTORY_CACHE_VERSION
        or context.get("target_key") != f"{target_key}/MODP=0"
        or context.get("cursor_strategy") != "oldest_session_date_with_exact_overlap"
        or context.get("logical_cursor_persisted") is not True
        or context.get("input_cursor_date") != chunk["input_cursor_date"]
        or context.get("output_cursor_date") != chunk["output_cursor_date"]
    ):
        raise ValueError("KIS paper daily history panel manifest is incompatible")
    raw_document = files.get("raw_daily_rows")
    if not isinstance(raw_document, Mapping):
        raise ValueError("KIS paper daily history panel raw document is invalid")
    raw_path = _raw_path(raw_document=raw_document, manifest_path=manifest_path, root=root)
    try:
        raw_bytes = raw_path.read_bytes()
    except OSError as error:
        raise ValueError("KIS paper daily history panel raw data is unreadable") from error
    raw_hash = _require_sha256(raw_document.get("sha256"), "raw sha256")
    if raw_hash != chunk["raw_sha256"] or _sha256(raw_bytes) != raw_hash:
        raise ValueError("KIS paper daily history panel raw hash is invalid")
    if raw_document.get("size_bytes") != len(raw_bytes):
        raise ValueError("KIS paper daily history panel raw size is invalid")
    rows, fingerprints = _parse_raw_rows(raw_bytes, symbol=symbol, exchange=exchange)
    if fingerprints != chunk["row_fingerprints"] or len(rows) != chunk["row_count"]:
        raise ValueError("KIS paper daily history panel row lineage is invalid")
    if _compact_date(min(session.isoformat() for session in rows)) != chunk["output_cursor_date"]:
        raise ValueError("KIS paper daily history panel output cursor is invalid")
    requests = manifest.get("requests")
    if (
        not isinstance(requests, Mapping)
        or requests.get("accepted_pages") != chunk["accepted_page_count"]
    ):
        raise ValueError("KIS paper daily history panel request facts are invalid")
    return rows


def _validate_index(index: Mapping[str, object]) -> None:
    if (
        index.get("schema_version") != 1
        or index.get("kind") != "kis_paper_daily_nas_history_index"
        or index.get("version") != KIS_PAPER_DAILY_HISTORY_CACHE_VERSION
        or index.get("initial_anchor_date") != "20260724"
        or index.get("terminal_date") != "19900101"
        or not isinstance(index.get("generation"), int)
        or int(index["generation"]) < 0
        or index.get("registry") != _SOURCE_REGISTRY
        or index.get("storage") != _INDEX_STORAGE
        or index.get("redaction") != _INDEX_REDACTION
    ):
        raise ValueError("KIS paper daily history panel index is invalid")
    targets = index.get("targets")
    if (
        not isinstance(targets, list)
        or tuple(
            item.get("target_key") if isinstance(item, Mapping) else None for item in targets
        )
        != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
    ):
        raise ValueError("KIS paper daily history panel targets are invalid")
    for target in targets:
        _validate_target(target)


def _validate_target(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("KIS paper daily history panel target is invalid")
    target_key = value.get("target_key")
    if target_key not in KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS:
        raise ValueError("KIS paper daily history panel target is invalid")
    symbol, exchange = str(target_key).split("/", maxsplit=1)
    if (
        value.get("symbol") != symbol
        or value.get("exchange") != exchange
        or value.get("state") not in _TERMINAL_TARGET_STATES
        or not _is_compact_date(value.get("next_anchor_date"))
        or not isinstance(value.get("accepted_page_count"), int)
        or int(value["accepted_page_count"]) < 0
        or not isinstance(value.get("categorical_failure_count"), int)
        or int(value["categorical_failure_count"]) < 0
        or value.get("last_reason") not in _SAFE_FAILURE_REASONS | {None}
        or not isinstance(value.get("chunks"), list)
        or not value["chunks"]
    ):
        raise ValueError("KIS paper daily history panel target is invalid")
    for chunk in value["chunks"]:
        _validate_chunk(chunk)


def _validate_chunk(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("KIS paper daily history panel chunk is invalid")
    fingerprints = value.get("row_fingerprints")
    if (
        value.get("outcome")
        not in {"committed", "partial", "complete", "conflict", "source_limited"}
        or not _is_compact_date(value.get("input_cursor_date"))
        or not _is_compact_date(value.get("output_cursor_date"))
        or not isinstance(value.get("manifest_path"), str)
        or not _is_sha256(value.get("manifest_sha256"))
        or not _is_sha256(value.get("raw_sha256"))
        or not isinstance(value.get("row_count"), int)
        or int(value["row_count"]) <= 0
        or not isinstance(value.get("accepted_page_count"), int)
        or int(value["accepted_page_count"]) < 0
        or not isinstance(value.get("exact_overlap_row_count"), int)
        or int(value["exact_overlap_row_count"]) < 0
        or not isinstance(fingerprints, Mapping)
        or len(fingerprints) != int(value["row_count"])
        or not isinstance(value.get("stop_outcome"), str)
    ):
        raise ValueError("KIS paper daily history panel chunk is invalid")
    for session, fingerprint in fingerprints.items():
        if not _is_iso_date(session) or not _is_sha256(fingerprint):
            raise ValueError("KIS paper daily history panel chunk is invalid")


def _manifest_payload(panel: KisPaperDailyHistoryPanel) -> dict[str, object]:
    common_start = _coverage_bucket(panel.common_sessions[0]) if panel.common_sessions else None
    common_end = _coverage_bucket(panel.common_sessions[-1]) if panel.common_sessions else None
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        "version": KIS_PAPER_DAILY_HISTORY_PANEL_VERSION,
        "status": "complete",
        "dataset": {
            "dataset_id": panel.dataset_id,
            "dataset_hash": panel.dataset_hash,
            "index_hash": panel.index_hash,
            "adjustment_mode": panel.adjustment_mode,
        },
        "source": {
            "provider": "KIS Open API virtual paper",
            "cache_contract": KIS_PAPER_DAILY_HISTORY_CACHE_VERSION,
            "target_keys": list(KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS),
            "registry_sha256": _SOURCE_REGISTRY["registry_sha256"],
            "source_manifest_sha256": _SOURCE_REGISTRY["source_manifest_sha256"],
            "source_file_sha256": _SOURCE_REGISTRY["source_file_sha256"],
            "current_listing_only": True,
            "historical_point_in_time_eligible": False,
            "cross_source_blending_allowed": False,
        },
        "streams": [
            panel.targets_by_key[target_key].to_payload()
            for target_key in KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        ],
        "common_intersection": {
            "available": panel.common_intersection_available,
            "session_count": len(panel.common_sessions),
            "coverage_start_bucket": common_start,
            "coverage_end_bucket": common_end,
            "exact_session_alignment_verified": panel.common_intersection_available,
        },
        "limitations": list(panel.raw_price_limitations),
        "eligibility": {
            "source_local_research_input": True,
            "historical_membership": False,
            "liquidity": False,
            "ranking": False,
            "model": False,
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
        },
    }
    _reject_raw_fields(payload)
    return payload


def _raw_path(
    *,
    raw_document: Mapping[str, object],
    manifest_path: Path,
    root: Path,
) -> Path:
    if (
        raw_document.get("format") != "csv.gz"
        or raw_document.get("ordering") != "session_date_ascending"
        or raw_document.get("columns") != list(_RAW_COLUMNS)
        or not isinstance(raw_document.get("path"), str)
        or type(raw_document.get("size_bytes")) is not int
    ):
        raise ValueError("KIS paper daily history panel raw document is invalid")
    _require_sha256(raw_document.get("sha256"), "raw sha256")
    relative = Path(str(raw_document["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("KIS paper daily history panel raw path is invalid")
    path = _safe_child(manifest_path.parent / relative, root)
    if not path.is_relative_to(manifest_path.parent.resolve()):
        raise ValueError("KIS paper daily history panel raw path is invalid")
    return path


def _parse_raw_rows(
    raw_bytes: bytes,
    *,
    symbol: str,
    exchange: str,
) -> tuple[dict[date, tuple[str, ...]], dict[str, str]]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes), mode="rb") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
                    raise ValueError("schema")
                rows: dict[date, tuple[str, ...]] = {}
                fingerprints: dict[str, str] = {}
                prior_session: date | None = None
                for document in reader:
                    if set(document) != set(_RAW_COLUMNS) or any(
                        document.get(column) is None for column in _RAW_COLUMNS
                    ):
                        raise ValueError("contents")
                    if document["symbol"] != symbol or document["exchange"] != exchange:
                        raise ValueError("contents")
                    session = _session_date(str(document["session_date"]))
                    if prior_session is not None and session <= prior_session:
                        raise ValueError("contents")
                    record = tuple(str(document[column]) for column in _RAW_COLUMNS)
                    rows[session] = record
                    fingerprints[session.isoformat()] = _row_fingerprint(record)
                    prior_session = session
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as error:
        raise ValueError("KIS paper daily history panel raw contents are invalid") from error
    if not rows:
        raise ValueError("KIS paper daily history panel raw contents are invalid")
    return rows, fingerprints


def _bar_from_record(record: tuple[str, ...]) -> Bar:
    if len(record) != len(_RAW_COLUMNS):
        raise ValueError("KIS paper daily history panel raw contents are invalid")
    (
        symbol,
        _exchange,
        session_text,
        open_value,
        high_value,
        low_value,
        close_value,
        volume_value,
    ) = record
    try:
        session = _session_date(session_text)
        return Bar(
            symbol=symbol,
            market="US",
            timeframe=Timeframe.D1,
            start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
            open=Decimal(open_value),
            high=Decimal(high_value),
            low=Decimal(low_value),
            close=Decimal(close_value),
            volume=Decimal(volume_value),
            complete=True,
        )
    except (InvalidOperation, ValueError) as error:
        raise ValueError("KIS paper daily history panel raw contents are invalid") from error


def _common_sessions(session_sets: tuple[set[date], ...]) -> tuple[date, ...]:
    if not session_sets:
        return ()
    return tuple(sorted(set.intersection(*session_sets)))


def _validate_expected_us_equity_session_coverage(sessions: tuple[date, ...]) -> None:
    if not sessions:
        return
    try:
        installed_version = version(_SESSION_CALENDAR_PACKAGE)
    except PackageNotFoundError as error:
        raise ValueError("KIS paper daily history session calendar is unavailable") from error
    if installed_version != _SESSION_CALENDAR_VERSION:
        raise ValueError("KIS paper daily history session calendar version is invalid")
    calendar = mcal.get_calendar(_SESSION_CALENDAR_ALIAS)
    if calendar.name != _SESSION_CALENDAR_NAME:
        raise ValueError("KIS paper daily history session calendar is invalid")
    expected = tuple(
        session.date()
        for session in calendar.schedule(
            start_date=sessions[0],
            end_date=sessions[-1],
        ).index
    )
    if sessions != expected:
        raise ValueError("KIS paper daily history panel has a normal US session gap")


def _dataset_hash(
    *,
    index_hash: str,
    rows_by_target: Mapping[str, Mapping[date, tuple[str, ...]]],
    targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget],
    common_sessions: tuple[date, ...],
) -> str:
    payload = {
        "panel_version": KIS_PAPER_DAILY_HISTORY_PANEL_VERSION,
        "index_hash": index_hash,
        "adjustment_mode": KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        "streams": [
            {
                "target": target_key,
                "terminal_state": targets_by_key[target_key].state,
                "rows": [
                    list(rows_by_target[target_key][session])
                    for session in sorted(rows_by_target[target_key])
                ],
            }
            for target_key in KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        ],
        "common_sessions": [session.isoformat() for session in common_sessions],
    }
    return _sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def _external_existing_root(
    root: Path | str,
    repo_root: Path | str | None,
    label: str,
) -> Path:
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError(f"KIS paper daily history panel {label} is invalid")
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError(f"KIS paper daily history panel {label} is invalid") from error
    repository = _repository_root(repo_root)
    mounted_market_data = repository / "market_data"
    permitted_mount = (
        not mounted_market_data.is_symlink()
        and mounted_market_data.is_mount()
        and resolved.is_relative_to(mounted_market_data.resolve())
    )
    if resolved.is_relative_to(repository) and not permitted_mount:
        raise ValueError(f"KIS paper daily history panel {label} must stay outside Git")
    return resolved


def _external_output_root(root: Path | str, repository: Path, label: str) -> Path:
    candidate = Path(root)
    if candidate.is_symlink():
        raise ValueError(f"KIS paper daily history panel {label} is invalid")
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError(f"KIS paper daily history panel {label} is invalid") from error
    if resolved.is_relative_to(repository):
        raise ValueError(f"KIS paper daily history panel {label} must stay outside Git")
    return resolved


def _repository_root(repo_root: Path | str | None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("KIS paper daily history panel repository root is invalid")
    return root.resolve()


def _safe_child(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    candidate = Path(os.path.abspath(path if path.is_absolute() else resolved_root / path))
    if not candidate.is_relative_to(resolved_root):
        raise ValueError("KIS paper daily history panel path is invalid")
    current = candidate
    while current != resolved_root:
        if current.is_symlink():
            raise ValueError("KIS paper daily history panel path is invalid")
        parent = current.parent
        if parent == current:
            raise ValueError("KIS paper daily history panel path is invalid")
        current = parent
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError("KIS paper daily history panel path is invalid") from error
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("KIS paper daily history panel path is invalid")
    return resolved


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> None:
    _reject_raw_fields(payload)
    encoded = _json_bytes(payload)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or path.read_bytes() != encoded:
            raise FileExistsError("KIS paper daily history panel output is immutable")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        if path.exists() or path.is_symlink():
            raise FileExistsError("KIS paper daily history panel output is immutable")
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _reject_raw_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in _SAFE_FIELD_NAMES:
                raise ValueError("KIS paper daily history panel output contains raw fields")
            _reject_raw_fields(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_raw_fields(nested)


def _json_document(payload: bytes, label: str) -> dict[str, object]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} is invalid")
    return document


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"KIS paper daily history panel {label} is invalid")
    try:
        _validate_sha256(value, label)
    except ValueError as error:
        raise ValueError(f"KIS paper daily history panel {label} is invalid") from error
    return value


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _row_fingerprint(record: tuple[str, ...]) -> str:
    return _sha256("\x1f".join(record).encode("utf-8"))


def _session_date(value: str) -> date:
    if not _is_iso_date(value):
        raise ValueError("KIS paper daily history panel session date is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("KIS paper daily history panel session date is invalid") from error


def _is_iso_date(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 10
        and value[4] == "-"
        and value[7] == "-"
        and value.replace("-", "").isdigit()
    )


def _is_compact_date(value: object) -> bool:
    return isinstance(value, str) and len(value) == 8 and value.isdigit()


def _compact_date(value: str) -> str:
    if not _is_iso_date(value):
        raise ValueError("KIS paper daily history panel session date is invalid")
    return value.replace("-", "")


def _coverage_bucket(value: date) -> str:
    return f"{value.year}-Q{((value.month - 1) // 3) + 1}"


def _is_coverage_bucket(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 7 or value[4:6] != "-Q":
        return False
    return value[:4].isdigit() and value[-1] in {"1", "2", "3", "4"}
