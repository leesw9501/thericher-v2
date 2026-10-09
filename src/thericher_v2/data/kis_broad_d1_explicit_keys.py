"""Frozen broad-D1 metadata binding and opt-in, explicit-key numeric readback.

Legacy UTC-midnight Bar timestamps identify dates, not exchange session clocks.
Calendar opens/closes and decision-time support belong to the caller. No key is
selected or replaced using retained coverage, source outcome or price values.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import Bar

from . import kis_paper_daily_broad_panel as panel
from .kis_paper_daily_broad_registry import load_kis_paper_daily_broad_registry

_CODES = frozenset(
    {
        "metadata_invalid",
        "selected_keys_invalid",
        "source_unavailable",
        "source_hash_changed",
        "calendar_invalid",
        "selected_source_invalid",
        "selected_source_conflict",
    }
)


class KisBroadD1ExplicitKeysUnavailable(ValueError):
    def __init__(self, code: str) -> None:
        if code not in _CODES:
            raise ValueError("invalid_unavailable_code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class KisBroadD1SourceBinding:
    path: Path
    sha256: str
    size_bytes: int

    def record(self) -> dict[str, object]:
        return {"path": str(self.path), "sha256": self.sha256, "size_bytes": self.size_bytes}


@dataclass(frozen=True, slots=True)
class KisBroadD1ChunkBinding:
    target_key: str
    manifest: KisBroadD1SourceBinding
    raw: KisBroadD1SourceBinding
    input_cursor_date: str
    output_cursor_date: str
    outcome: str


@dataclass(frozen=True, slots=True)
class KisBroadD1ExplicitKeysMetadata:
    manifest_path: Path
    materialization_receipt_path: Path
    calendar_path: Path
    cache_root: Path
    panel_root: Path
    repo_root: Path
    dataset_hash: str
    index_sha256: str
    index_generation: int
    full_target_count: int
    source_hashes: Mapping[str, str]
    selected_target_keys: tuple[str, ...]
    calendar_session_dates: tuple[date, ...]
    targets_by_key: Mapping[str, panel.KisPaperDailyBroadPanelTarget] = field(repr=False)
    chunks: tuple[KisBroadD1ChunkBinding, ...]
    source_bindings_before: tuple[KisBroadD1SourceBinding, ...]
    source_bindings_after: tuple[KisBroadD1SourceBinding, ...]
    _targets_document: bytes = field(repr=False)

    def record(self) -> dict[str, object]:
        return {
            "dataset_hash": self.dataset_hash,
            "index_sha256": self.index_sha256,
            "index_generation": self.index_generation,
            "full_target_count": self.full_target_count,
            "source_hashes": dict(self.source_hashes),
            "selected_target_keys": list(self.selected_target_keys),
            "selected_key_set_sha256": panel._sha256(
                panel._json_bytes({"target_keys": list(self.selected_target_keys)})
            ),
            "calendar_count": len(self.calendar_session_dates),
            "calendar_first": self.calendar_session_dates[0].isoformat(),
            "calendar_last": self.calendar_session_dates[-1].isoformat(),
            "targets": [
                {
                    "target_key": key,
                    "state": target.state,
                    "bar_count": target.bar_count,
                    "chunk_count": target.chunk_count,
                    "coverage_start": target.coverage_start,
                    "coverage_end": target.coverage_end,
                    "quarantined": target.quarantined,
                }
                for key, target in self.targets_by_key.items()
            ],
            "source_bindings": [item.record() for item in self.source_bindings_before],
            "metadata_before_after_equal": self.source_bindings_before
            == self.source_bindings_after,
            "chunks": [
                {
                    "target_key": item.target_key,
                    "manifest": item.manifest.record(),
                    "raw": item.raw.record(),
                    "input_cursor_date": item.input_cursor_date,
                    "output_cursor_date": item.output_cursor_date,
                    "outcome": item.outcome,
                }
                for item in self.chunks
            ],
            "raw_bytes_reattested": False,
            "limitations": list(panel._LIMITATIONS)
            + ["utc_midnight_labels_are_date_keys_only", "historical_code_revision_unattested"],
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1ExplicitKeysInput:
    metadata: KisBroadD1ExplicitKeysMetadata
    bars_by_target: Mapping[str, tuple[Bar, ...]] = field(repr=False)
    source_bindings_before: tuple[KisBroadD1SourceBinding, ...]
    source_bindings_after: tuple[KisBroadD1SourceBinding, ...]

    def safe_facts(self) -> dict[str, object]:
        return {
            "dataset_hash": self.metadata.dataset_hash,
            "selected_target_count": len(self.bars_by_target),
            "row_counts": {key: len(rows) for key, rows in self.bars_by_target.items()},
            "raw_bytes_reattested": True,
            "source_bindings_before_after_equal": (
                self.source_bindings_before == self.source_bindings_after
            ),
            "availability_and_finality": "not_observed",
        }


def lexicographic_target_keys(keys: tuple[str, ...], *, cap: int = 128) -> tuple[str, ...]:
    if (
        type(cap) is not int
        or not 1 <= cap <= 128
        or not isinstance(keys, tuple)
        or not keys
        or any(not panel._is_target_key(key) for key in keys)
        or len(set(keys)) != len(keys)
    ):
        raise KisBroadD1ExplicitKeysUnavailable("selected_keys_invalid")
    return tuple(sorted(keys))[:cap]


def bind_kis_broad_d1_explicit_keys(
    manifest_path: Path | str,
    *,
    materialization_receipt_path: Path | str,
    calendar_path: Path | str,
    selected_target_keys: tuple[str, ...] | None = None,
    cap: int = 128,
    cache_root: Path | str = panel.KIS_PAPER_DAILY_BROAD_CACHE_ROOT,
    panel_root: Path | str = panel.KIS_PAPER_DAILY_BROAD_PANEL_ROOT,
    repo_root: Path | str | None = None,
) -> KisBroadD1ExplicitKeysMetadata:
    """Bind metadata/chunk specifications without opening any raw price file."""
    try:
        repository = panel._repository_root(repo_root)
        root = panel._external_existing_root(cache_root, repository, "cache")
        output = panel._external_existing_root(panel_root, repository, "panel")
        manifest_path = panel._safe_child(Path(manifest_path), output)
        receipt_path = panel._external_file(
            Path(materialization_receipt_path), repository, "receipt"
        )
        calendar_path = panel._external_file(Path(calendar_path), repository, "calendar")
        registry_path = root / "kis-paper-daily-broad-registry.json"
        registry_binding, _ = _read(registry_path)
        registry = load_kis_paper_daily_broad_registry(output_root=root, repo_root=repository)
        panel._validate_registry(registry)
        if registry.registry_sha256 != registry_binding.sha256:
            raise KisBroadD1ExplicitKeysUnavailable("source_hash_changed")
        manifest_binding, data = _read(manifest_path)
        payload = _document(data)
        panel._reject_raw_fields(payload)
        index, index_hash = panel._snapshot_from_manifest(payload, registry=registry)
        snapshot = panel._source_snapshot_from_index(index, index_sha256=index_hash)
        summaries = panel._target_summaries_from_manifest(payload, registry=registry)
        dataset_hash = panel._dataset_hash(
            index_sha256=index_hash, registry=registry, snapshot=snapshot, targets=summaries
        )
        panel._validate_selection_manifest(
            payload=payload,
            registry=registry,
            source_snapshot=snapshot,
            index_sha256=index_hash,
            index_generation=index["generation"],
            target_summaries=summaries,
            dataset_hash=dataset_hash,
        )
        receipt_binding, data = _read(receipt_path)
        panel._validate_materialization_receipt(
            receipt=_document(data),
            manifest_sha256=manifest_binding.sha256,
            index_generation=index["generation"],
            target_summaries=summaries,
        )
        calendar_binding, data = _read(calendar_path)
        dates = _calendar_dates(_document(data))
        keys = (
            lexicographic_target_keys(registry.target_keys, cap=cap)
            if selected_target_keys is None
            else selected_target_keys
        )
        if (
            not isinstance(keys, tuple)
            or not 1 <= len(keys) <= 128
            or any(not isinstance(key, str) for key in keys)
            or tuple(sorted(set(keys))) != keys
            or not set(keys).issubset(registry.target_keys)
        ):
            raise KisBroadD1ExplicitKeysUnavailable("selected_keys_invalid")
        by_key = {target["target_key"]: target for target in index["targets"]}
        selected = [by_key[key] for key in keys]
        chunks = tuple(chunk for target in selected for chunk in _bind_chunks(target, root))
        before = _unique_bindings(
            (registry_binding, manifest_binding, receipt_binding, calendar_binding)
            + tuple(chunk.manifest for chunk in chunks)
        )
        after = _reattest(before)
        return KisBroadD1ExplicitKeysMetadata(
            manifest_path,
            receipt_path,
            calendar_path,
            root,
            output,
            repository,
            dataset_hash,
            index_hash,
            index["generation"],
            len(registry.target_keys),
            MappingProxyType(
                {
                    "registry_sha256": registry.registry_sha256,
                    "registry_identity_sha256": registry.registry_identity_sha256,
                    "source_manifest_sha256": registry.source_manifest_sha256,
                    "source_file_sha256": registry.source_file_sha256,
                }
            ),
            keys,
            dates,
            MappingProxyType({key: summaries[key] for key in keys}),
            chunks,
            before,
            after,
            panel._json_bytes({"targets": selected}),
        )
    except KisBroadD1ExplicitKeysUnavailable:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise KisBroadD1ExplicitKeysUnavailable("metadata_invalid") from None


def load_kis_broad_d1_explicit_keys(
    binding: KisBroadD1ExplicitKeysMetadata,
) -> KisBroadD1ExplicitKeysInput:
    """Explicit numeric opt-in; retain empty/sparse/partial accepted streams."""
    if type(binding) is not KisBroadD1ExplicitKeysMetadata:
        raise KisBroadD1ExplicitKeysUnavailable("metadata_invalid")
    _reattest(binding.source_bindings_before)
    current = bind_kis_broad_d1_explicit_keys(
        binding.manifest_path,
        materialization_receipt_path=binding.materialization_receipt_path,
        calendar_path=binding.calendar_path,
        selected_target_keys=binding.selected_target_keys,
        cache_root=binding.cache_root,
        panel_root=binding.panel_root,
        repo_root=binding.repo_root,
    )
    if current != binding:
        raise KisBroadD1ExplicitKeysUnavailable("source_hash_changed")
    if any(target.quarantined for target in binding.targets_by_key.values()):
        raise KisBroadD1ExplicitKeysUnavailable("selected_source_conflict")
    try:
        bars: dict[str, tuple[Bar, ...]] = {}
        for target in _document(binding._targets_document)["targets"]:
            rows, count, start, end, outcomes = panel._load_target_records(
                target=target,
                root=binding.cache_root,
                verify_index_fingerprints=False,
            )
            key = target["target_key"]
            panel._validate_selected_target_records(
                binding.targets_by_key[key],
                row_count=count,
                coverage_start=start,
                coverage_end=end,
                outcomes=outcomes,
            )
            bars[key] = rows
        before = _unique_bindings(
            binding.source_bindings_before + tuple(chunk.raw for chunk in binding.chunks)
        )
        after = _reattest(before)
        return KisBroadD1ExplicitKeysInput(binding, MappingProxyType(bars), before, after)
    except KisBroadD1ExplicitKeysUnavailable:
        raise
    except (OSError, EOFError, ValueError, TypeError, KeyError):
        raise KisBroadD1ExplicitKeysUnavailable("selected_source_invalid") from None


def _bind_chunks(target: Mapping[str, object], root: Path) -> tuple[KisBroadD1ChunkBinding, ...]:
    result = []
    cursor = target["initial_anchor_date"]
    for chunk in target["chunks"]:
        if chunk["input_cursor_date"] != cursor:
            raise KisBroadD1ExplicitKeysUnavailable("metadata_invalid")
        path = panel._safe_relative_child(root, panel._chunk_manifest_ref(chunk))
        manifest, data = _read(path, panel._chunk_manifest_sha256(chunk))
        document = _document(data)
        source, backfill = document["source"], document["backfill"]
        raw = document["files"]["raw_daily_rows"]
        if (
            document["collector_objective_id"] != panel.KIS_PAPER_DAILY_BROAD_CACHE_VERSION
            or document["collector_version"] != panel.KIS_PAPER_DAILY_BROAD_CACHE_VERSION
            or any(
                source.get(key) != value
                for key, value in {
                    "symbol": target["symbol"],
                    "exchange": target["exchange"],
                    "endpoint": "dailyprice",
                    "adjustment_mode": "MODP=0_unadjusted",
                }.items()
            )
            or backfill["target_key"] != target["target_key"] + "/MODP=0"
            or backfill["contract_version"] != panel.KIS_PAPER_DAILY_BROAD_CACHE_VERSION
            or backfill["cursor_strategy"] != "oldest_session_date_with_exact_overlap"
            or backfill["logical_cursor_persisted"] is not True
            or backfill["input_cursor_date"] != chunk["input_cursor_date"]
            or backfill["output_cursor_date"] != chunk["output_cursor_date"]
            or raw["format"] != "csv.gz"
            or raw["columns"] != list(panel._RAW_COLUMNS)
            or raw["ordering"] != "session_date_ascending"
            or raw["sha256"] != panel._chunk_raw_sha256(chunk)
            or type(raw["size_bytes"]) is not int
            or raw["size_bytes"] < 0
            or document["requests"]["accepted_pages"] != chunk["accepted_page_count"]
        ):
            raise KisBroadD1ExplicitKeysUnavailable("metadata_invalid")
        raw_binding = KisBroadD1SourceBinding(
            panel._safe_relative_child(path.parent, raw["path"]), raw["sha256"], raw["size_bytes"]
        )
        result.append(
            KisBroadD1ChunkBinding(
                target["target_key"],
                manifest,
                raw_binding,
                chunk["input_cursor_date"],
                chunk["output_cursor_date"],
                chunk["outcome"],
            )
        )
        if (
            chunk["outcome"] in panel._USABLE_CHUNK_OUTCOMES
            and chunk["output_cursor_date"] < cursor
        ):
            cursor = chunk["output_cursor_date"]
        elif chunk["outcome"] not in {"conflict", "source_limited"}:
            raise KisBroadD1ExplicitKeysUnavailable("metadata_invalid")
    if cursor != target["next_anchor_date"]:
        raise KisBroadD1ExplicitKeysUnavailable("metadata_invalid")
    return tuple(result)


def _read(path: Path, expected: str | None = None) -> tuple[KisBroadD1SourceBinding, bytes]:
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)) or not path.is_file():
            raise OSError
        data = path.read_bytes()
    except OSError:
        raise KisBroadD1ExplicitKeysUnavailable("source_unavailable") from None
    binding = KisBroadD1SourceBinding(path, panel._sha256(data), len(data))
    if expected is not None and binding.sha256 != expected:
        raise KisBroadD1ExplicitKeysUnavailable("source_hash_changed")
    return binding, data


def _unique_bindings(
    items: tuple[KisBroadD1SourceBinding, ...],
) -> tuple[KisBroadD1SourceBinding, ...]:
    by_path: dict[Path, KisBroadD1SourceBinding] = {}
    for item in items:
        if item.path in by_path and by_path[item.path] != item:
            raise KisBroadD1ExplicitKeysUnavailable("metadata_invalid")
        by_path[item.path] = item
    return tuple(by_path[path] for path in sorted(by_path))


def _reattest(items: tuple[KisBroadD1SourceBinding, ...]) -> tuple[KisBroadD1SourceBinding, ...]:
    result = tuple(_read(item.path, item.sha256)[0] for item in items)
    if result != items:
        raise KisBroadD1ExplicitKeysUnavailable("source_hash_changed")
    return result


def _document(data: bytes) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate_metadata_key")
            result[key] = value
        return result

    result = json.loads(data, object_pairs_hook=pairs)
    if not isinstance(result, dict):
        raise ValueError("metadata_object_required")
    return result


def _calendar_dates(document: Mapping[str, object]) -> tuple[date, ...]:
    try:
        values = document["session_dates"]
        if (
            not isinstance(values, list)
            or not values
            or any(type(item) is not str for item in values)
        ):
            raise ValueError
        dates = tuple(date.fromisoformat(item) for item in values)
        if (
            tuple(item.isoformat() for item in dates) != tuple(values)
            or tuple(sorted(set(dates))) != dates
        ):
            raise ValueError
        return dates
    except (KeyError, TypeError, ValueError):
        raise KisBroadD1ExplicitKeysUnavailable("calendar_invalid") from None
