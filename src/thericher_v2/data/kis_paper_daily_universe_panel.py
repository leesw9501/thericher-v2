"""Offline, hash-bound panel for the completed six-symbol KIS daily probe.

This module deliberately consumes one already retained probe snapshot.  It has
no KIS client, credential lookup, network access, model, decision, or broker
dependency.  The current listing that selected the six symbols remains a
prospective-only source fact.
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
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.official_symbol_directory_nas_probe import (
    NAS_COMMON_STOCK_PROBE_SYMBOLS,
    OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_SOURCE_MANIFEST_SHA256,
)

KIS_PAPER_DAILY_UNIVERSE_PANEL_VERSION = "kis-paper-daily-universe-panel-v1"
KIS_PAPER_DAILY_UNIVERSE_PANEL_ID = "kis.paper.private.daily.universe.panel-v1"
KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-universe-probe/v1"
)
KIS_PAPER_DAILY_UNIVERSE_PROBE_EVIDENCE_ROOT = Path(
    "D:/thericher-v2/model-artifacts/kis-paper-daily-universe-probe-v1"
)
KIS_PAPER_DAILY_UNIVERSE_PANEL_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-universe-panel/v1"
)
KIS_PAPER_DAILY_UNIVERSE_PANEL_EVIDENCE_ROOT = Path(
    "D:/thericher-v2/model-artifacts/kis-paper-daily-universe-panel-v1"
)

KIS_PAPER_DAILY_UNIVERSE_PANEL_COMPLETION_RULE = (
    "observed_session_label_complete_for_offline_replay_only"
)
KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE = "MODP=0_unadjusted"
KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS = (
    "current_listing_registry_is_not_a_historical_point_in_time_universe",
    "corporate_action_semantics_not_qualified",
    "session_labels_do_not_prove_provider_close_availability",
    "offline_local_paper_validation_only",
)

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
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_PANEL_ATTESTATION = object()


@dataclass(frozen=True, slots=True)
class _FrozenPanelIdentity:
    snapshot_name: str
    evidence_run_name: str
    panel_snapshot_name: str
    cache_manifest_sha256: str
    evidence_sha256: str
    registry_sha256: str
    source_manifest_sha256: str
    source_file_sha256: str
    target_keys: tuple[str, ...]


_FROZEN_PANEL_IDENTITY = _FrozenPanelIdentity(
    snapshot_name="snapshot=20260726T163526Z-daily-universe-probe-v1",
    evidence_run_name="run=20260726T163526Z",
    panel_snapshot_name="panel=20260726T163526Z-six-symbol-current-d1-v1",
    cache_manifest_sha256=(
        "sha256:ffe91642bb024e7a9191c2abb774c97d529ec4b074d719b387da6dc460fd0eac"
    ),
    evidence_sha256=("sha256:02ce0b1004808644b0c69af6a546423508e13609aa658175f8ee09c3293e6bad"),
    registry_sha256=("sha256:58c894236425755cb18c60a576944e33f88f9c6221e75405d6de5b4a6fa27935"),
    source_manifest_sha256=OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_SOURCE_MANIFEST_SHA256,
    source_file_sha256=("sha256:cf9f42bbff4cdcec0335c5acf42c1ffe889039b5f1e48f60374120045513f6bb"),
    target_keys=tuple(f"{symbol}/NAS" for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS),
)


@dataclass(frozen=True, slots=True, init=False)
class KisPaperDailyUniversePanel:
    """One source-separated, common-session, per-symbol daily panel."""

    dataset_id: str
    dataset_hash: str
    cache_manifest_path: Path
    cache_manifest_sha256: str
    evidence_path: Path
    evidence_sha256: str
    registry_sha256: str
    source_manifest_sha256: str
    source_file_sha256: str
    adjustment_mode: str
    common_sessions: tuple[date, ...]
    bars_by_symbol: Mapping[str, CatalogedBars]
    alignment_excluded_rows: Mapping[str, int]
    completion_rule: str = KIS_PAPER_DAILY_UNIVERSE_PANEL_COMPLETION_RULE
    source_limitations: tuple[str, ...] = KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS
    schema_version: int = SCHEMA_VERSION
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified daily universe panel loader")

    def validation_series(self, symbol: str) -> CatalogedBars:
        """Return one immutable D1 stream for offline/local-paper validation only."""

        _require_attested_panel(self)
        resolved = symbol.strip().upper()
        if resolved not in self.bars_by_symbol:
            raise ValueError("daily universe panel symbol is unsupported")
        return self.bars_by_symbol[resolved]


@dataclass(frozen=True, slots=True, init=False)
class KisPaperDailyUniverseCompletedBarInput:
    """Typed per-symbol handoff to the existing offline local-paper validator."""

    panel_dataset_id: str
    panel_dataset_hash: str
    symbol: str
    cataloged_bars: CatalogedBars
    last_completed_session: date
    completion_rule: str
    source_limitations: tuple[str, ...]
    local_paper_only: bool = True
    paper_trading_eligible: bool = False
    schema_version: int = SCHEMA_VERSION
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified daily universe completed-bar adapter")

    def safe_payload(self) -> dict[str, object]:
        """Return timing and provenance facts without raw rows or prices."""

        _require_attested_completed_bar_input(self)
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_universe_completed_bar_input",
            "dataset_id": self.panel_dataset_id,
            "dataset_hash": self.panel_dataset_hash,
            "symbol": self.symbol,
            "market": "US",
            "timeframe": Timeframe.D1.value,
            "last_completed_session": self.last_completed_session.isoformat(),
            "completion_rule": self.completion_rule,
            "local_paper_only": self.local_paper_only,
            "paper_trading_eligible": self.paper_trading_eligible,
            "source_limitations": list(KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS),
        }


@dataclass(frozen=True, slots=True)
class KisPaperDailyUniversePanelMaterialization:
    """External immutable panel and source-safe evidence references."""

    panel: KisPaperDailyUniversePanel
    manifest_path: Path
    manifest_sha256: str
    evidence_path: Path
    evidence_sha256: str


def load_frozen_kis_paper_daily_universe_panel(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT,
    evidence_root: Path | str = KIS_PAPER_DAILY_UNIVERSE_PROBE_EVIDENCE_ROOT,
) -> KisPaperDailyUniversePanel:
    """Load only the exact completed six-symbol probe without external access."""

    return _load_panel(
        cache_root=Path(cache_root),
        evidence_root=Path(evidence_root),
        identity=_FROZEN_PANEL_IDENTITY,
        repository_root=_REPOSITORY_ROOT,
    )


def prepare_kis_paper_daily_universe_completed_bar_input(
    panel: KisPaperDailyUniversePanel,
    *,
    symbol: str,
) -> KisPaperDailyUniverseCompletedBarInput:
    """Adapt one panel stream without invoking Research, Execution, or a broker."""

    _require_attested_panel(panel)
    stream = panel.validation_series(symbol)
    return _completed_bar_input_from_verified_panel(
        panel_dataset_id=panel.dataset_id,
        panel_dataset_hash=panel.dataset_hash,
        symbol=symbol,
        cataloged_bars=stream,
        last_completed_session=panel.common_sessions[-1],
        completion_rule=panel.completion_rule,
        source_limitations=panel.source_limitations,
    )


def materialize_frozen_kis_paper_daily_universe_panel(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT,
    evidence_root: Path | str = KIS_PAPER_DAILY_UNIVERSE_PROBE_EVIDENCE_ROOT,
    panel_root: Path | str = KIS_PAPER_DAILY_UNIVERSE_PANEL_ROOT,
    artifact_root: Path | str = KIS_PAPER_DAILY_UNIVERSE_PANEL_EVIDENCE_ROOT,
) -> KisPaperDailyUniversePanelMaterialization:
    """Persist a raw-row-free panel manifest and linked external evidence."""

    panel = _load_panel(
        cache_root=Path(cache_root),
        evidence_root=Path(evidence_root),
        identity=_FROZEN_PANEL_IDENTITY,
        repository_root=_REPOSITORY_ROOT,
    )
    return _materialize_panel(
        panel=panel,
        panel_root=Path(panel_root),
        artifact_root=Path(artifact_root),
        identity=_FROZEN_PANEL_IDENTITY,
        repository_root=_REPOSITORY_ROOT,
    )


def _load_panel(
    *,
    cache_root: Path,
    evidence_root: Path,
    identity: _FrozenPanelIdentity,
    repository_root: Path,
) -> KisPaperDailyUniversePanel:
    _validate_identity(identity)
    cache = _external_existing_root(cache_root, repository_root, "daily universe cache")
    evidence = _external_existing_root(evidence_root, repository_root, "daily universe evidence")
    manifest_path = (
        _safe_child(cache, identity.snapshot_name, "daily universe snapshot") / "manifest.json"
    )
    evidence_path = (
        _safe_child(evidence, identity.evidence_run_name, "daily universe evidence")
        / "evidence.json"
    )
    manifest_payload, manifest = _read_json_mapping(manifest_path, "daily universe manifest")
    manifest_sha256 = _sha256(manifest_payload)
    if manifest_sha256 != identity.cache_manifest_sha256:
        raise ValueError("daily universe manifest hash mismatch")
    raw_documents = _validate_manifest(
        manifest,
        identity=identity,
        manifest_path=manifest_path,
    )
    evidence_payload, evidence_document = _read_json_mapping(
        evidence_path,
        "daily universe evidence",
    )
    evidence_sha256 = _sha256(evidence_payload)
    if evidence_sha256 != identity.evidence_sha256:
        raise ValueError("daily universe evidence hash mismatch")
    _validate_evidence(
        evidence_document,
        identity=identity,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
    )

    rows_by_symbol: dict[str, dict[date, Bar]] = {}
    for target_key in identity.target_keys:
        symbol, exchange = target_key.split("/", maxsplit=1)
        rows_by_symbol[symbol] = _load_verified_raw_rows(
            snapshot_root=manifest_path.parent,
            document=raw_documents[target_key],
            symbol=symbol,
            exchange=exchange,
        )
    common_sessions = tuple(
        sorted(set.intersection(*(set(rows) for rows in rows_by_symbol.values())))
    )
    if not common_sessions:
        raise ValueError("daily universe panel has no common sessions")
    dataset_hash = _panel_dataset_hash(
        manifest_sha256=manifest_sha256,
        evidence_sha256=evidence_sha256,
        target_keys=identity.target_keys,
        rows_by_symbol=rows_by_symbol,
        common_sessions=common_sessions,
    )
    alignment_excluded_rows = {
        symbol: len(rows) - len(common_sessions) for symbol, rows in rows_by_symbol.items()
    }
    bars_by_symbol: dict[str, CatalogedBars] = {}
    for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS:
        bars = tuple(rows_by_symbol[symbol][session] for session in common_sessions)
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_UNIVERSE_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=manifest_path,
            bars=bars,
        )
    return _panel_from_verified_load(
        dataset_id=KIS_PAPER_DAILY_UNIVERSE_PANEL_ID,
        dataset_hash=dataset_hash,
        cache_manifest_path=manifest_path,
        cache_manifest_sha256=manifest_sha256,
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
        registry_sha256=identity.registry_sha256,
        source_manifest_sha256=identity.source_manifest_sha256,
        source_file_sha256=identity.source_file_sha256,
        adjustment_mode=KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE,
        common_sessions=common_sessions,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        alignment_excluded_rows=MappingProxyType(alignment_excluded_rows),
    )


def _materialize_panel(
    *,
    panel: KisPaperDailyUniversePanel,
    panel_root: Path,
    artifact_root: Path,
    identity: _FrozenPanelIdentity,
    repository_root: Path,
) -> KisPaperDailyUniversePanelMaterialization:
    _require_attested_panel(panel)
    data_root = _external_output_root(panel_root, repository_root, "daily universe panel")
    evidence_root = _external_output_root(
        artifact_root,
        repository_root,
        "daily universe panel evidence",
    )
    if _path_contains(data_root, evidence_root) or _path_contains(evidence_root, data_root):
        raise ValueError("daily universe panel data and evidence roots must be separate")
    source_roots = (panel.cache_manifest_path.parent, panel.evidence_path.parent)
    for output_root in (data_root, evidence_root):
        if any(
            _path_contains(output_root, source_root) or _path_contains(source_root, output_root)
            for source_root in source_roots
        ):
            raise ValueError("daily universe panel output must not overlap its source")
    for output_root in (data_root, evidence_root):
        output_root.mkdir(parents=True, exist_ok=True)
        if output_root.is_symlink() or output_root.resolve() != output_root:
            raise ValueError("daily universe panel output root is invalid")
    manifest_path = (
        _safe_child(data_root, identity.panel_snapshot_name, "daily universe panel")
        / "manifest.json"
    )
    manifest = _panel_manifest(panel=panel, identity=identity)
    manifest_payload = _json_bytes(manifest)
    manifest_sha256 = _write_immutable_file(manifest_path, manifest_payload)
    evidence_path = (
        _safe_child(
            evidence_root,
            identity.panel_snapshot_name,
            "daily universe panel evidence",
        )
        / "evidence.json"
    )
    evidence_payload = _json_bytes(
        _panel_evidence(
            panel=panel,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
            identity=identity,
        )
    )
    evidence_sha256 = _write_immutable_file(evidence_path, evidence_payload)
    return KisPaperDailyUniversePanelMaterialization(
        panel=panel,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
    )


def _panel_from_verified_load(
    *,
    dataset_id: str,
    dataset_hash: str,
    cache_manifest_path: Path,
    cache_manifest_sha256: str,
    evidence_path: Path,
    evidence_sha256: str,
    registry_sha256: str,
    source_manifest_sha256: str,
    source_file_sha256: str,
    adjustment_mode: str,
    common_sessions: tuple[date, ...],
    bars_by_symbol: Mapping[str, CatalogedBars],
    alignment_excluded_rows: Mapping[str, int],
) -> KisPaperDailyUniversePanel:
    result = object.__new__(KisPaperDailyUniversePanel)
    object.__setattr__(result, "dataset_id", dataset_id)
    object.__setattr__(result, "dataset_hash", dataset_hash)
    object.__setattr__(result, "cache_manifest_path", cache_manifest_path)
    object.__setattr__(result, "cache_manifest_sha256", cache_manifest_sha256)
    object.__setattr__(result, "evidence_path", evidence_path)
    object.__setattr__(result, "evidence_sha256", evidence_sha256)
    object.__setattr__(result, "registry_sha256", registry_sha256)
    object.__setattr__(result, "source_manifest_sha256", source_manifest_sha256)
    object.__setattr__(result, "source_file_sha256", source_file_sha256)
    object.__setattr__(result, "adjustment_mode", adjustment_mode)
    object.__setattr__(result, "common_sessions", common_sessions)
    object.__setattr__(result, "bars_by_symbol", bars_by_symbol)
    object.__setattr__(result, "alignment_excluded_rows", alignment_excluded_rows)
    object.__setattr__(
        result,
        "completion_rule",
        KIS_PAPER_DAILY_UNIVERSE_PANEL_COMPLETION_RULE,
    )
    object.__setattr__(result, "source_limitations", KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _PANEL_ATTESTATION)
    return result


def _completed_bar_input_from_verified_panel(
    *,
    panel_dataset_id: str,
    panel_dataset_hash: str,
    symbol: str,
    cataloged_bars: CatalogedBars,
    last_completed_session: date,
    completion_rule: str,
    source_limitations: tuple[str, ...],
) -> KisPaperDailyUniverseCompletedBarInput:
    resolved_symbol = symbol.strip().upper()
    _validate_completed_bar_input_fields(
        panel_dataset_id=panel_dataset_id,
        panel_dataset_hash=panel_dataset_hash,
        symbol=resolved_symbol,
        cataloged_bars=cataloged_bars,
        last_completed_session=last_completed_session,
        completion_rule=completion_rule,
        source_limitations=source_limitations,
    )
    result = object.__new__(KisPaperDailyUniverseCompletedBarInput)
    object.__setattr__(result, "panel_dataset_id", panel_dataset_id)
    object.__setattr__(result, "panel_dataset_hash", panel_dataset_hash)
    object.__setattr__(result, "symbol", resolved_symbol)
    object.__setattr__(result, "cataloged_bars", cataloged_bars)
    object.__setattr__(result, "last_completed_session", last_completed_session)
    object.__setattr__(result, "completion_rule", completion_rule)
    object.__setattr__(result, "source_limitations", KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS)
    object.__setattr__(result, "local_paper_only", True)
    object.__setattr__(result, "paper_trading_eligible", False)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _PANEL_ATTESTATION)
    return result


def _require_attested_panel(panel: object) -> None:
    if (
        not isinstance(panel, KisPaperDailyUniversePanel)
        or getattr(panel, "_attestation", None) is not _PANEL_ATTESTATION
        or panel.dataset_id != KIS_PAPER_DAILY_UNIVERSE_PANEL_ID
        or not _is_sha256(panel.dataset_hash)
        or panel.adjustment_mode != KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE
        or panel.completion_rule != KIS_PAPER_DAILY_UNIVERSE_PANEL_COMPLETION_RULE
        or panel.source_limitations != KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS
        or tuple(panel.bars_by_symbol) != NAS_COMMON_STOCK_PROBE_SYMBOLS
        or tuple(panel.alignment_excluded_rows) != NAS_COMMON_STOCK_PROBE_SYMBOLS
        or not panel.common_sessions
    ):
        raise ValueError("daily universe panel requires a loader attestation")


def _require_attested_completed_bar_input(input: object) -> None:
    if (
        not isinstance(input, KisPaperDailyUniverseCompletedBarInput)
        or getattr(input, "_attestation", None) is not _PANEL_ATTESTATION
        or input.source_limitations != KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS
        or not input.local_paper_only
        or input.paper_trading_eligible
    ):
        raise ValueError("daily universe completed-bar input requires a loader attestation")


def _validate_completed_bar_input_fields(
    *,
    panel_dataset_id: str,
    panel_dataset_hash: str,
    symbol: str,
    cataloged_bars: CatalogedBars,
    last_completed_session: date,
    completion_rule: str,
    source_limitations: tuple[str, ...],
) -> None:
    if (
        not isinstance(cataloged_bars, CatalogedBars)
        or cataloged_bars.dataset_id != panel_dataset_id
        or cataloged_bars.dataset_hash != panel_dataset_hash
        or not cataloged_bars.bars
        or source_limitations != KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS
        or completion_rule != KIS_PAPER_DAILY_UNIVERSE_PANEL_COMPLETION_RULE
    ):
        raise ValueError("daily universe completed-bar input is incompatible")
    bars = cataloged_bars.bars
    if any(
        bar.symbol != symbol
        or bar.market != "US"
        or bar.timeframe is not Timeframe.D1
        or not bar.complete
        for bar in bars
    ):
        raise ValueError("daily universe completed-bar input is incompatible")
    sessions = tuple(bar.start_ts.date() for bar in bars)
    if (
        sessions != tuple(sorted(sessions))
        or len(set(sessions)) != len(sessions)
        or last_completed_session != sessions[-1]
    ):
        raise ValueError("daily universe completed-bar input is incompatible")


def _validate_manifest(
    manifest: Mapping[str, object],
    *,
    identity: _FrozenPanelIdentity,
    manifest_path: Path,
) -> Mapping[str, Mapping[str, object]]:
    registry = _required_mapping(manifest, "registry", "daily universe manifest")
    source = _required_mapping(manifest, "source", "daily universe manifest")
    files = _required_mapping(manifest, "files", "daily universe manifest")
    targets = manifest.get("targets")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("kind") != "kis_paper_daily_universe_capability_probe"
        or manifest.get("immutable_snapshot") is not True
        or manifest.get("dataset_id")
        != f"kis.paper.private.daily.universe.{identity.snapshot_name}"
        or registry.get("registry_sha256") != identity.registry_sha256
        or registry.get("source_manifest_sha256") != identity.source_manifest_sha256
        or registry.get("source_file_sha256") != identity.source_file_sha256
        or registry.get("target_keys") != list(identity.target_keys)
        or registry.get("prospective_only") is not True
        or registry.get("historical_point_in_time_eligible") is not False
        or source.get("provider") != "KIS Open API virtual paper"
        or source.get("endpoint") != "dailyprice"
        or source.get("adjustment_mode") != KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE
        or source.get("account_or_order_endpoints_used") is not False
        or not isinstance(targets, list)
    ):
        raise ValueError("daily universe manifest is incompatible")
    target_keys = tuple(
        target.get("target_key") if isinstance(target, Mapping) else None for target in targets
    )
    if target_keys != identity.target_keys or any(
        not isinstance(target, Mapping) or target.get("classification") != "accepted"
        for target in targets
    ):
        raise ValueError("daily universe manifest targets are incompatible")
    raw_documents = files.get("raw_daily_rows")
    if not isinstance(raw_documents, Mapping) or set(raw_documents) != set(identity.target_keys):
        raise ValueError("daily universe manifest raw documents are incompatible")
    result: dict[str, Mapping[str, object]] = {}
    for target_key in identity.target_keys:
        document = raw_documents[target_key]
        if not isinstance(document, Mapping):
            raise ValueError("daily universe manifest raw documents are incompatible")
        _safe_raw_path(manifest_path.parent, _required_text(document, "path", "raw document"))
        if (
            document.get("format") != "csv.gz"
            or document.get("ordering") != "session_date_ascending"
            or document.get("columns") != list(_RAW_COLUMNS)
            or not _is_sha256(document.get("sha256"))
            or type(document.get("size_bytes")) is not int
            or int(document["size_bytes"]) <= 0
        ):
            raise ValueError("daily universe manifest raw documents are incompatible")
        result[target_key] = document
    return MappingProxyType(result)


def _validate_evidence(
    evidence: Mapping[str, object],
    *,
    identity: _FrozenPanelIdentity,
    manifest_path: Path,
    manifest_sha256: str,
) -> None:
    cache_manifest = _required_mapping(evidence, "cache_manifest", "daily universe evidence")
    registry = _required_mapping(evidence, "registry", "daily universe evidence")
    redaction = _required_mapping(evidence, "redaction", "daily universe evidence")
    if (
        evidence.get("schema_version") != SCHEMA_VERSION
        or evidence.get("kind") != "kis_paper_daily_universe_capability_probe_evidence"
        or cache_manifest.get("path") != str(manifest_path)
        or cache_manifest.get("sha256") != manifest_sha256
        or registry.get("registry_sha256") != identity.registry_sha256
        or registry.get("source_manifest_sha256") != identity.source_manifest_sha256
        or registry.get("source_file_sha256") != identity.source_file_sha256
        or registry.get("target_keys") != list(identity.target_keys)
        or redaction.get("raw_rows_persisted") is not False
        or redaction.get("credentials_persisted") is not False
        or redaction.get("account_facts_persisted") is not False
        or redaction.get("order_facts_persisted") is not False
    ):
        raise ValueError("daily universe evidence is incompatible")
    targets = evidence.get("targets")
    if (
        not isinstance(targets, list)
        or tuple(
            target.get("target_key") if isinstance(target, Mapping) else None for target in targets
        )
        != identity.target_keys
        or any(
            not isinstance(target, Mapping) or target.get("classification") != "accepted"
            for target in targets
        )
    ):
        raise ValueError("daily universe evidence is incompatible")


def _load_verified_raw_rows(
    *,
    snapshot_root: Path,
    document: Mapping[str, object],
    symbol: str,
    exchange: str,
) -> dict[date, Bar]:
    raw_path = _safe_raw_path(snapshot_root, _required_text(document, "path", "raw document"))
    if raw_path.is_symlink() or not raw_path.is_file():
        raise ValueError("daily universe raw file is unavailable")
    try:
        payload = raw_path.read_bytes()
    except OSError as error:
        raise ValueError("daily universe raw file is unavailable") from error
    if _sha256(payload) != document["sha256"] or len(payload) != document["size_bytes"]:
        raise ValueError("daily universe raw file hash mismatch")
    try:
        decoded = gzip.decompress(payload).decode("utf-8")
    except (EOFError, OSError, UnicodeDecodeError) as error:
        raise ValueError("daily universe raw file is invalid") from error
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
        raise ValueError("daily universe raw schema is invalid")
    rows: dict[date, Bar] = {}
    prior_session: date | None = None
    for row in reader:
        if set(row) != set(_RAW_COLUMNS) or any(value is None for value in row.values()):
            raise ValueError("daily universe raw row is invalid")
        if row["symbol"] != symbol or row["exchange"] != exchange:
            raise ValueError("daily universe raw row is incompatible")
        session = _parse_session_date(row["session_date"])
        if prior_session is not None and session <= prior_session:
            raise ValueError("daily universe raw sessions are not strictly chronological")
        if session in rows:
            raise ValueError("daily universe raw sessions are duplicated")
        try:
            bar = Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=Decimal(row["volume"]),
                complete=True,
            )
        except (InvalidOperation, ValueError) as error:
            raise ValueError("daily universe raw row is invalid") from error
        rows[session] = bar
        prior_session = session
    if not rows:
        raise ValueError("daily universe raw file has no rows")
    return rows


def _panel_manifest(
    *,
    panel: KisPaperDailyUniversePanel,
    identity: _FrozenPanelIdentity,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_universe_panel",
        "version": KIS_PAPER_DAILY_UNIVERSE_PANEL_VERSION,
        "dataset_id": panel.dataset_id,
        "dataset_hash": panel.dataset_hash,
        "source": {
            "cache_manifest_path": str(panel.cache_manifest_path),
            "cache_manifest_sha256": panel.cache_manifest_sha256,
            "evidence_sha256": panel.evidence_sha256,
            "registry_sha256": panel.registry_sha256,
            "source_manifest_sha256": panel.source_manifest_sha256,
            "source_file_sha256": panel.source_file_sha256,
            "adjustment_mode": panel.adjustment_mode,
        },
        "scope": {
            "target_keys": list(identity.target_keys),
            "market": "US",
            "timeframe": Timeframe.D1.value,
            "completion_rule": panel.completion_rule,
            "historical_point_in_time_eligible": False,
            "corporate_action_qualified": False,
            "ranking_eligible": False,
            "paper_trading_eligible": False,
        },
        "alignment": {
            "common_session_count": len(panel.common_sessions),
            "start_session": panel.common_sessions[0].isoformat(),
            "end_session": panel.common_sessions[-1].isoformat(),
            "rows_excluded_by_alignment": {
                symbol: panel.alignment_excluded_rows[symbol]
                for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS
            },
        },
        "limitations": list(panel.source_limitations),
        "redaction": {"raw_rows_in_manifest": False, "credentials_persisted": False},
    }


def _panel_evidence(
    *,
    panel: KisPaperDailyUniversePanel,
    manifest_path: Path,
    manifest_sha256: str,
    identity: _FrozenPanelIdentity,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_universe_panel_evidence",
        "version": KIS_PAPER_DAILY_UNIVERSE_PANEL_VERSION,
        "panel_manifest": {"path": str(manifest_path), "sha256": manifest_sha256},
        "source": {
            "cache_manifest_sha256": panel.cache_manifest_sha256,
            "probe_evidence_sha256": panel.evidence_sha256,
            "registry_sha256": panel.registry_sha256,
            "target_keys": list(identity.target_keys),
        },
        "alignment": {
            "common_session_count": len(panel.common_sessions),
            "start_session": panel.common_sessions[0].isoformat(),
            "end_session": panel.common_sessions[-1].isoformat(),
        },
        "scope": {
            "offline_local_paper_validation_only": True,
            "paper_trading_eligible": False,
            "ranking_eligible": False,
        },
        "redaction": {"raw_rows_persisted": False, "credentials_persisted": False},
    }


def _panel_dataset_hash(
    *,
    manifest_sha256: str,
    evidence_sha256: str,
    target_keys: tuple[str, ...],
    rows_by_symbol: Mapping[str, Mapping[date, Bar]],
    common_sessions: tuple[date, ...],
) -> str:
    payload = {
        "version": KIS_PAPER_DAILY_UNIVERSE_PANEL_VERSION,
        "manifest_sha256": manifest_sha256,
        "evidence_sha256": evidence_sha256,
        "target_keys": list(target_keys),
        "common_sessions": [session.isoformat() for session in common_sessions],
        "source_rows": {
            symbol: [
                {
                    "session": session.isoformat(),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": str(bar.volume),
                }
                for session, bar in sorted(rows.items())
            ]
            for symbol, rows in sorted(rows_by_symbol.items())
        },
    }
    return _sha256(_json_bytes(payload))


def _validate_identity(identity: _FrozenPanelIdentity) -> None:
    if (
        not identity.snapshot_name.startswith("snapshot=")
        or not identity.evidence_run_name.startswith("run=")
        or not identity.panel_snapshot_name.startswith("panel=")
        or identity.target_keys
        != tuple(f"{symbol}/NAS" for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS)
        or any(
            not _is_sha256(value)
            for value in (
                identity.cache_manifest_sha256,
                identity.evidence_sha256,
                identity.registry_sha256,
                identity.source_manifest_sha256,
                identity.source_file_sha256,
            )
        )
    ):
        raise ValueError("daily universe panel identity is invalid")


def _external_existing_root(root: Path, repository_root: Path, label: str) -> Path:
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError(f"{label} root is invalid")
    resolved = candidate.resolve()
    if _path_contains(repository_root, resolved):
        raise ValueError(f"{label} root must stay outside Git")
    return resolved


def _external_output_root(root: Path, repository_root: Path, label: str) -> Path:
    candidate = Path(root)
    if candidate.is_symlink():
        raise ValueError(f"{label} root is invalid")
    resolved = candidate.resolve()
    if _path_contains(repository_root, resolved):
        raise ValueError(f"{label} root must stay outside Git")
    return resolved


def _safe_child(root: Path, name: str, label: str) -> Path:
    candidate = root / name
    if candidate.is_symlink():
        raise ValueError(f"{label} path is invalid")
    resolved = candidate.resolve()
    if not _path_contains(root, resolved):
        raise ValueError(f"{label} path is invalid")
    return resolved


def _safe_raw_path(snapshot_root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if (
        relative.is_absolute()
        or len(relative.parts) != 2
        or relative.parts[0] != "raw"
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("daily universe raw path is invalid")
    return _safe_child(snapshot_root, relative_path, "daily universe raw")


def _read_json_mapping(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is unavailable")
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not isinstance(document, Mapping):
        raise ValueError(f"{label} is invalid")
    return payload, document


def _write_immutable_file(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise ValueError("daily universe panel immutable output conflicts")
        return _sha256(payload)
    staging = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(payload)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)
    return _sha256(payload)


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


def _parse_session_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("daily universe raw session is invalid") from error


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
