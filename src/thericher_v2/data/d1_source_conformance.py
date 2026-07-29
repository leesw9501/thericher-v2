"""Offline D1 source-metadata conformance for future KIS-reconstructible inputs.

This module deliberately compares source contracts, not source values. It
reattests existing local Norgate and KIS panels, writes only compact metadata to
the external artifact root, and never constructs a label, feature, model, or
broker-facing object.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KisPaperDailyHistoryPanel,
    build_kis_paper_daily_history_panel,
)
from thericher_v2.data.norgate_trial_development_panel import (
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
    NorgateTrialDevelopmentPanelCatalog,
    load_verified_norgate_trial_development_panel_catalog,
)
from thericher_v2.research.validation import _reject_repo_artifact_path, resolve_model_artifact_root

D1_SOURCE_CONFORMANCE_ID = "norgate-kis-d1-metadata-conformance-v1"
D1_SOURCE_CONFORMANCE_VERSION = 1
D1_SOURCE_CONFORMANCE_DIRECTORY = "data/d1-source-conformance"
D1_OHLCV_FIELDS = tuple(sorted(("open", "high", "low", "close", "volume")))
ConformanceStatus = Literal[
    "metadata_conforming_with_limits",
    "semantics_conflict",
    "input_unavailable",
]
_KNOWN_SOURCE_NAMES = frozenset({"norgate", "kis_paper"})
_UNCERTAIN_SEMANTICS = frozenset(
    {"unknown", "unqualified", "unverified", "unverified_requested_none"}
)
_RAW_PAYLOAD_KEYS = frozenset(
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
        "timestamp",
        "timestamps",
        "sourcepath",
        "workdir",
        "statesqlite",
        "eventjsonl",
        "eventlog",
    }
)


@dataclass(frozen=True, slots=True)
class D1SourceMetadata:
    """One source-safe, reattested D1 metadata projection."""

    source_name: Literal["norgate", "kis_paper"]
    dataset_id: str
    dataset_sha256: str
    lineage_sha256: str
    field_names: tuple[str, ...]
    timeframe: str
    completed_bar_semantics: str
    adjustment_semantics: str
    corporate_action_semantics: str
    symbol_identity_semantics: str
    session_timezone_semantics: str
    gap_halt_semantics: str
    stream_count: int
    common_session_count: int

    def __post_init__(self) -> None:
        if (
            self.source_name not in _KNOWN_SOURCE_NAMES
            or not self.dataset_id
            or not _is_sha256(self.dataset_sha256)
            or not _is_sha256(self.lineage_sha256)
            or tuple(sorted(set(self.field_names))) != self.field_names
            or not self.field_names
            or self.timeframe != "1d"
            or self.stream_count <= 0
            or self.common_session_count < 0
        ):
            raise ValueError("D1 source metadata is invalid")
        for value in (
            self.completed_bar_semantics,
            self.adjustment_semantics,
            self.corporate_action_semantics,
            self.symbol_identity_semantics,
            self.session_timezone_semantics,
            self.gap_halt_semantics,
        ):
            if not value:
                raise ValueError("D1 source metadata semantics are invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "lineage_sha256": self.lineage_sha256,
            "field_names": list(self.field_names),
            "timeframe": self.timeframe,
            "completed_bar_semantics": self.completed_bar_semantics,
            "adjustment_semantics": self.adjustment_semantics,
            "corporate_action_semantics": self.corporate_action_semantics,
            "symbol_identity_semantics": self.symbol_identity_semantics,
            "session_timezone_semantics": self.session_timezone_semantics,
            "gap_halt_semantics": self.gap_halt_semantics,
            "stream_count": self.stream_count,
            "common_session_count": self.common_session_count,
        }


@dataclass(frozen=True, slots=True)
class D1MetadataConformance:
    """A source-parameterized interface map with no value-level comparison."""

    norgate: D1SourceMetadata
    kis_paper: D1SourceMetadata
    status: ConformanceStatus
    shared_field_names: tuple[str, ...]
    norgate_only_field_names: tuple[str, ...]
    kis_paper_only_field_names: tuple[str, ...]
    semantics: Mapping[str, str]

    def __post_init__(self) -> None:
        semantics = dict(self.semantics)
        if (
            self.norgate.source_name != "norgate"
            or self.kis_paper.source_name != "kis_paper"
            or self.status not in {
                "metadata_conforming_with_limits",
                "semantics_conflict",
                "input_unavailable",
            }
            or tuple(sorted(set(self.shared_field_names))) != self.shared_field_names
            or tuple(sorted(set(self.norgate_only_field_names))) != self.norgate_only_field_names
            or tuple(sorted(set(self.kis_paper_only_field_names)))
            != self.kis_paper_only_field_names
            or set(semantics) != {
                "completed_bar",
                "adjustment",
                "corporate_actions",
                "symbol_identity",
                "session_timezone",
                "gap_halts",
            }
            or any(
                value not in {"metadata_conforming", "unknown", "semantics_conflict"}
                for value in semantics.values()
            )
        ):
            raise ValueError("D1 metadata conformance is invalid")
        object.__setattr__(self, "semantics", MappingProxyType(semantics))

    @property
    def source_parameterized_only(self) -> bool:
        return True

    @property
    def price_transfer_eligible(self) -> bool:
        return False

    @property
    def model_eligible(self) -> bool:
        return False

    def to_payload(self) -> dict[str, object]:
        return {
            "norgate": self.norgate.to_payload(),
            "kis_paper": self.kis_paper.to_payload(),
            "status": self.status,
            "shared_field_names": list(self.shared_field_names),
            "norgate_only_field_names": list(self.norgate_only_field_names),
            "kis_paper_only_field_names": list(self.kis_paper_only_field_names),
            "semantics": dict(self.semantics),
            "interface_scope": {
                "source_parameterized_only": True,
                "price_transfer_eligible": False,
                "model_eligible": False,
                "point_in_time_eligible": False,
                "ranking_eligible": False,
                "paper_trading_eligible": False,
                "pnl_or_profitability_claim": False,
            },
        }


@dataclass(frozen=True, slots=True)
class D1SourceConformanceReceipt:
    """Immutable external receipt for a metadata-only comparison."""

    conformance: D1MetadataConformance
    conformance_sha256: str
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.conformance_sha256)
            or not _is_sha256(self.receipt_sha256)
            or not self.receipt_path.is_file()
            or self.receipt_path.is_symlink()
        ):
            raise ValueError("D1 source conformance receipt is invalid")


NorgateMetadataLoader = Callable[[Path, Path | None], D1SourceMetadata]
KisMetadataLoader = Callable[[Path, Path | None], D1SourceMetadata]


def build_d1_source_conformance_receipt(
    *,
    artifact_root: Path | None = None,
    market_data_root: Path,
    repo_root: Path | None = None,
    norgate_loader: NorgateMetadataLoader | None = None,
    kis_loader: KisMetadataLoader | None = None,
) -> D1SourceConformanceReceipt:
    """Reattest both existing local sources and write one compact receipt."""

    root = _external_artifact_root(artifact_root or resolve_model_artifact_root(), repo_root)
    load_norgate = norgate_loader or _load_norgate_metadata
    load_kis = kis_loader or _load_kis_paper_metadata
    norgate = load_norgate(Path(market_data_root), repo_root)
    kis_paper = load_kis(Path(market_data_root), repo_root)
    conformance = assess_d1_metadata_conformance(norgate=norgate, kis_paper=kis_paper)
    conformance_payload = conformance.to_payload()
    conformance_sha256 = _sha256_json(conformance_payload)
    receipt_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "d1_source_metadata_conformance_receipt",
        "version": D1_SOURCE_CONFORMANCE_VERSION,
        "conformance_id": D1_SOURCE_CONFORMANCE_ID,
        "conformance_sha256": conformance_sha256,
        "conformance": conformance_payload,
        "artifact_policy": {
            "external_artifact_only": True,
            "network_accessed": False,
            "credentials_accessed": False,
            "kis_accessed": False,
            "broker_accessed": False,
            "source_rows_persisted": False,
            "market_values_persisted": False,
            "labels_persisted": False,
            "predictions_persisted": False,
            "model_artifacts_persisted": False,
            "pnl_persisted": False,
        },
    }
    _reject_raw_payload_keys(receipt_payload)
    target = root / D1_SOURCE_CONFORMANCE_DIRECTORY / conformance_sha256[7:] / "receipt.json"
    _write_or_verify_json(target, receipt_payload)
    return D1SourceConformanceReceipt(
        conformance=conformance,
        conformance_sha256=conformance_sha256,
        receipt_path=target,
        receipt_sha256=_sha256(target.read_bytes()),
    )


def assess_d1_metadata_conformance(
    *, norgate: D1SourceMetadata, kis_paper: D1SourceMetadata
) -> D1MetadataConformance:
    """Compare only source metadata and explicitly retain semantic uncertainty."""

    norgate_fields = set(norgate.field_names)
    kis_fields = set(kis_paper.field_names)
    shared = tuple(sorted(norgate_fields & kis_fields))
    semantics = {
        "completed_bar": _same_or_conflict(
            norgate.completed_bar_semantics, kis_paper.completed_bar_semantics
        ),
        "adjustment": _same_or_unknown(
            norgate.adjustment_semantics, kis_paper.adjustment_semantics
        ),
        "corporate_actions": _same_or_unknown(
            norgate.corporate_action_semantics, kis_paper.corporate_action_semantics
        ),
        "symbol_identity": _same_or_conflict(
            norgate.symbol_identity_semantics, kis_paper.symbol_identity_semantics
        ),
        "session_timezone": _same_or_unknown(
            norgate.session_timezone_semantics, kis_paper.session_timezone_semantics
        ),
        "gap_halts": _same_or_unknown(
            norgate.gap_halt_semantics, kis_paper.gap_halt_semantics
        ),
    }
    field_match = (
        norgate.timeframe == kis_paper.timeframe == "1d"
        and shared == D1_OHLCV_FIELDS
        and not (norgate_fields - kis_fields)
        and not (kis_fields - norgate_fields)
    )
    status: ConformanceStatus = (
        "metadata_conforming_with_limits"
        if field_match and "semantics_conflict" not in semantics.values()
        else "semantics_conflict"
    )
    return D1MetadataConformance(
        norgate=norgate,
        kis_paper=kis_paper,
        status=status,
        shared_field_names=shared,
        norgate_only_field_names=tuple(sorted(norgate_fields - kis_fields)),
        kis_paper_only_field_names=tuple(sorted(kis_fields - norgate_fields)),
        semantics=semantics,
    )


def _load_norgate_metadata(
    market_data_root: Path, repo_root: Path | None
) -> D1SourceMetadata:
    snapshot_dir = _rebase_market_data_path(
        FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
        market_data_root=market_data_root,
    )
    catalog = load_verified_norgate_trial_development_panel_catalog(
        snapshot_dir,
        expected_dataset_id=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
        expected_dataset_hash=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _require_completed_d1_catalog(catalog, label="Norgate")
    return D1SourceMetadata(
        source_name="norgate",
        dataset_id=catalog.source.dataset_id,
        dataset_sha256=catalog.source.dataset_hash,
        lineage_sha256=catalog.source.manifest_hash,
        field_names=D1_OHLCV_FIELDS,
        timeframe="1d",
        completed_bar_semantics="completed_bar_attested",
        adjustment_semantics=(
            "unverified_requested_none"
            if not catalog.source.adjustment_semantics_verified
            else "qualified"
        ),
        corporate_action_semantics="unqualified",
        symbol_identity_semantics="static_survivorship_selected_non_pit",
        session_timezone_semantics="unknown",
        gap_halt_semantics="unknown",
        stream_count=catalog.selected_symbol_count,
        common_session_count=len(catalog.common_sessions),
    )


def _load_kis_paper_metadata(
    market_data_root: Path, repo_root: Path | None
) -> D1SourceMetadata:
    cache_root = _rebase_market_data_path(
        KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
        market_data_root=market_data_root,
    )
    panel = build_kis_paper_daily_history_panel(cache_root=cache_root, repo_root=repo_root)
    _require_completed_d1_panel(panel)
    if panel.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE:
        raise ValueError("KIS paper D1 adjustment metadata is invalid")
    return D1SourceMetadata(
        source_name="kis_paper",
        dataset_id=panel.dataset_id,
        dataset_sha256=panel.dataset_hash,
        lineage_sha256=panel.index_hash,
        field_names=D1_OHLCV_FIELDS,
        timeframe="1d",
        completed_bar_semantics="completed_bar_attested",
        adjustment_semantics="declared_unadjusted",
        corporate_action_semantics="unqualified",
        symbol_identity_semantics="current_listing_registry_non_pit",
        session_timezone_semantics="unknown",
        gap_halt_semantics="unknown",
        stream_count=len(panel.bars_by_symbol),
        common_session_count=len(panel.common_sessions),
    )


def _require_completed_d1_catalog(
    catalog: NorgateTrialDevelopmentPanelCatalog, *, label: str
) -> None:
    if (
        not catalog.bars_by_symbol
        or any(
            bar.timeframe is not Timeframe.D1 or not bar.complete
            for stream in catalog.bars_by_symbol.values()
            for bar in stream.bars
        )
    ):
        raise ValueError(f"{label} D1 metadata is not completed-bar attested")


def _require_completed_d1_panel(panel: KisPaperDailyHistoryPanel) -> None:
    if (
        not panel.bars_by_symbol
        or any(
            bar.timeframe is not Timeframe.D1 or not bar.complete
            for stream in panel.bars_by_symbol.values()
            for bar in stream.bars
        )
    ):
        raise ValueError("KIS paper D1 metadata is not completed-bar attested")


def _rebase_market_data_path(path: Path, *, market_data_root: Path) -> Path:
    default_root = Path("D:/market_data")
    try:
        relative = Path(path).relative_to(default_root)
    except ValueError as error:
        raise ValueError("D1 source metadata path must be beneath the market-data root") from error
    return Path(market_data_root) / relative


def _same_or_conflict(left: str, right: str) -> str:
    if left == right and left not in _UNCERTAIN_SEMANTICS:
        return "metadata_conforming"
    if left == right:
        return "unknown"
    return "semantics_conflict"


def _same_or_unknown(left: str, right: str) -> str:
    if left == right and left not in _UNCERTAIN_SEMANTICS:
        return "metadata_conforming"
    if left == right:
        return "unknown"
    return "semantics_conflict"


def _external_artifact_root(root: Path, repo_root: Path | None) -> Path:
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("D1 source conformance artifact root is invalid")
    _reject_repo_artifact_path(candidate, repo_root or Path.cwd())
    return candidate.resolve()


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> None:
    encoded = _json_bytes(payload)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or path.read_bytes() != encoded:
            raise FileExistsError("D1 source conformance receipt is immutable")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_name(f".{uuid.uuid4().hex}.stage")
    try:
        stage.write_bytes(encoded)
        if path.exists() or path.is_symlink():
            raise FileExistsError("D1 source conformance receipt is immutable")
        os.replace(stage, path)
    finally:
        stage.unlink(missing_ok=True)


def _reject_raw_payload_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in _RAW_PAYLOAD_KEYS:
                raise ValueError("D1 source conformance receipt contains a raw field")
            _reject_raw_payload_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_raw_payload_keys(nested)


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_json(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )
