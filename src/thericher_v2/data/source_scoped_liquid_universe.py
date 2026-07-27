"""A small current-source-scoped liquid-universe contract.

The contract binds only already attested local source metadata.  It deliberately
does not open raw bars, infer historical membership, rank instruments, or
create an input that can be sent to Paper execution.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    KIS_PAPER_PRIVATE_DAILY_INDEX_RELATIVE_PATH,
    KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS,
)
from thericher_v2.data.kis_paper_daily_universe_panel import (
    KIS_PAPER_DAILY_UNIVERSE_PANEL_EVIDENCE_ROOT,
)

SOURCE_SCOPED_LIQUID_UNIVERSE_VERSION = "source-scoped-liquid-universe-v1"
SOURCE_SCOPED_LIQUID_UNIVERSE_ID = "us.equities.source-scoped-liquid-universe-v1"
SOURCE_SCOPED_LIQUID_UNIVERSE_OUTPUT_ROOT = Path(
    "D:/market_data/us_equities/source-scoped-liquid-universe/v1"
)
SOURCE_SCOPED_LIQUID_UNIVERSE_MEMBERSHIP_SCOPE = "current_source_scoped_only"
SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID = "kis-paper-private-daily-etf-catalog-v1"
SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID = "kis-paper-current-nas-daily-panel-v1"
SOURCE_SCOPED_LIQUID_UNIVERSE_APPROVED_MARKET_DATA_ROOT = Path("D:/market_data")
DEFAULT_SOURCE_SCOPED_LIQUID_UNIVERSE_PRIVATE_DAILY_INDEX_PATH = (
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT / KIS_PAPER_PRIVATE_DAILY_INDEX_RELATIVE_PATH
)
DEFAULT_SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_PANEL_EVIDENCE_PATH = (
    KIS_PAPER_DAILY_UNIVERSE_PANEL_EVIDENCE_ROOT
    / "panel=20260726T163526Z-six-symbol-current-d1-v1"
    / "evidence.json"
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_UNIVERSE_ATTESTATION = object()
_ETF_TARGETS = (
    ("QQQ", "NAS", "QQQ/NAS/MODP=0"),
    ("SPY", "AMS", "SPY/AMS/MODP=0"),
    ("IWM", "AMS", "IWM/AMS/MODP=0"),
)
_NAS_TARGETS = (
    ("AAPL", "NAS"),
    ("AMZN", "NAS"),
    ("GOOGL", "NAS"),
    ("META", "NAS"),
    ("MSFT", "NAS"),
    ("NVDA", "NAS"),
)
_BASE_LIMITATIONS = (
    "current_source_scoped_only",
    "not_historical_point_in_time_membership",
    "corporate_action_semantics_not_qualified",
    "not_ranking_eligible",
    "not_paper_trading_eligible",
    "d1_only",
)


@dataclass(frozen=True, slots=True)
class _ApprovedSourceIdentity:
    private_daily_index_sha256: str
    nas_panel_evidence_sha256: str
    nas_panel_manifest_sha256: str


_APPROVED_SOURCE_IDENTITY = _ApprovedSourceIdentity(
    private_daily_index_sha256=(
        "sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660"
    ),
    nas_panel_evidence_sha256=(
        "sha256:55bfaaa68d29e8040dc08fa0c5459a7c7123fc242389b4da3f30394ae9250978"
    ),
    nas_panel_manifest_sha256=(
        "sha256:99ba614688e199e6c40d9c20d5d22bebbe586e4e479deeee0c40a9a40417e6f4"
    ),
)


@dataclass(frozen=True, slots=True)
class _SourceScopedLiquidUniverseSourcePaths:
    """Injected source-safe documents used to reattest one universe snapshot."""

    private_daily_index_path: Path | str
    nas_panel_evidence_path: Path | str


@dataclass(frozen=True, slots=True)
class SourceScopedLiquidUniverseInstrument:
    """One current local instrument reference with no price or decision payload."""

    instrument_id: str
    symbol: str
    venue: str
    source_id: str
    dataset_id: str
    source_snapshot_sha256: str
    supported_timeframes: tuple[Timeframe, ...]
    availability_scope: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceScopedLiquidUniverseMaterialization:
    """External immutable manifest identity."""

    manifest_path: Path
    manifest_sha256: str
    instrument_count: int


@dataclass(frozen=True, slots=True, init=False)
class SourceScopedLiquidUniverse:
    """Reattested current-source-scoped universe for offline consumers only."""

    manifest_id: str
    manifest_sha256: str
    manifest_path: Path
    instruments: tuple[SourceScopedLiquidUniverseInstrument, ...]
    membership_scope: str
    historical_membership_eligible: bool
    ranking_eligible: bool
    paper_trading_eligible: bool
    model_selection_eligible: bool
    liquidity_qualified: bool
    cross_partition_alignment_eligible: bool
    limitations: tuple[str, ...]
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified source-scoped liquid-universe loader")

    def safe_payload(self) -> dict[str, object]:
        """Return source-safe identity and limitation facts only."""

        require_attested_source_scoped_liquid_universe(self)
        return {
            "manifest_id": self.manifest_id,
            "manifest_sha256": self.manifest_sha256,
            "instrument_ids": [instrument.instrument_id for instrument in self.instruments],
            "membership_scope": self.membership_scope,
            "historical_membership_eligible": self.historical_membership_eligible,
            "ranking_eligible": self.ranking_eligible,
            "paper_trading_eligible": self.paper_trading_eligible,
            "model_selection_eligible": self.model_selection_eligible,
            "liquidity_qualified": self.liquidity_qualified,
            "cross_partition_alignment_eligible": self.cross_partition_alignment_eligible,
            "limitations": list(self.limitations),
        }


def _default_source_scoped_liquid_universe_source_paths() -> _SourceScopedLiquidUniverseSourcePaths:
    """Return the one currently attested local-source pair without reading either file."""

    return _SourceScopedLiquidUniverseSourcePaths(
        private_daily_index_path=DEFAULT_SOURCE_SCOPED_LIQUID_UNIVERSE_PRIVATE_DAILY_INDEX_PATH,
        nas_panel_evidence_path=DEFAULT_SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_PANEL_EVIDENCE_PATH,
    )


def materialize_source_scoped_liquid_universe_manifest(
    *,
    output_root: Path | str = SOURCE_SCOPED_LIQUID_UNIVERSE_OUTPUT_ROOT,
    repository_root: Path | str | None = None,
) -> SourceScopedLiquidUniverseMaterialization:
    """Write or reattach one deterministic source-safe manifest outside Git.

    This validates manifests, evidence, and catalog metadata only.  It does not
    open raw cache rows or construct ``Bar`` objects.
    """

    repository = _repository_root(repository_root)
    return _materialize_source_scoped_liquid_universe_manifest(
        source_paths=_default_source_scoped_liquid_universe_source_paths(),
        output_root=output_root,
        repository_root=repository,
        approved_source_identity=_APPROVED_SOURCE_IDENTITY,
        require_approved_output_root=True,
    )


def _materialize_source_scoped_liquid_universe_manifest(
    *,
    source_paths: _SourceScopedLiquidUniverseSourcePaths,
    output_root: Path | str,
    repository_root: Path,
    approved_source_identity: _ApprovedSourceIdentity | None,
    require_approved_output_root: bool,
) -> SourceScopedLiquidUniverseMaterialization:
    sources, instrument_payloads, source_roots = _reattested_source_payloads(
        source_paths=source_paths,
        repository_root=repository_root,
        approved_source_identity=approved_source_identity,
    )
    payload = _manifest_payload(sources=sources, instruments=instrument_payloads)
    encoded = _json_bytes(payload)
    manifest_sha256 = _sha256(encoded)
    root = _external_output_root(
        output_root,
        repository_root,
        "liquid-universe output root",
        approved_parent=(
            SOURCE_SCOPED_LIQUID_UNIVERSE_APPROVED_MARKET_DATA_ROOT
            if require_approved_output_root
            else None
        ),
    )
    _reject_output_overlap(output_root=root, source_roots=source_roots)
    path = root / f"{SOURCE_SCOPED_LIQUID_UNIVERSE_ID}-{manifest_sha256[7:23]}.json"
    _write_immutable_file(path, encoded)
    return SourceScopedLiquidUniverseMaterialization(
        manifest_path=path,
        manifest_sha256=manifest_sha256,
        instrument_count=len(instrument_payloads),
    )


def load_source_scoped_liquid_universe_manifest(
    manifest_path: Path | str,
    *,
    repository_root: Path | str | None = None,
    requested_membership_scope: str = SOURCE_SCOPED_LIQUID_UNIVERSE_MEMBERSHIP_SCOPE,
) -> SourceScopedLiquidUniverse:
    """Reattest a manifest from its existing source-safe local documents."""

    if requested_membership_scope != SOURCE_SCOPED_LIQUID_UNIVERSE_MEMBERSHIP_SCOPE:
        raise ValueError("liquid universe does not support historical membership interpretation")
    repository = _repository_root(repository_root)
    return _load_source_scoped_liquid_universe_manifest(
        manifest_path=manifest_path,
        source_paths=_default_source_scoped_liquid_universe_source_paths(),
        repository_root=repository,
        requested_membership_scope=requested_membership_scope,
        approved_source_identity=_APPROVED_SOURCE_IDENTITY,
        require_approved_manifest_root=True,
    )


def _load_source_scoped_liquid_universe_manifest(
    *,
    manifest_path: Path | str,
    source_paths: _SourceScopedLiquidUniverseSourcePaths,
    repository_root: Path,
    requested_membership_scope: str,
    approved_source_identity: _ApprovedSourceIdentity | None,
    require_approved_manifest_root: bool,
) -> SourceScopedLiquidUniverse:
    if requested_membership_scope != SOURCE_SCOPED_LIQUID_UNIVERSE_MEMBERSHIP_SCOPE:
        raise ValueError("liquid universe does not support historical membership interpretation")
    path = _external_existing_file(
        manifest_path,
        repository_root,
        "liquid-universe manifest",
        approved_parent=(
            SOURCE_SCOPED_LIQUID_UNIVERSE_OUTPUT_ROOT
            if require_approved_manifest_root
            else None
        ),
    )
    manifest_bytes, manifest = _read_json_mapping(path, "liquid-universe manifest")
    sources, instrument_payloads, _source_roots = _reattested_source_payloads(
        source_paths=source_paths,
        repository_root=repository_root,
        approved_source_identity=approved_source_identity,
    )
    expected_payload = _manifest_payload(sources=sources, instruments=instrument_payloads)
    if manifest != expected_payload:
        raise ValueError("liquid-universe manifest source provenance is incompatible")
    instruments = tuple(_instrument_from_payload(payload) for payload in instrument_payloads)
    result = object.__new__(SourceScopedLiquidUniverse)
    object.__setattr__(result, "manifest_id", SOURCE_SCOPED_LIQUID_UNIVERSE_ID)
    object.__setattr__(result, "manifest_sha256", _sha256(manifest_bytes))
    object.__setattr__(result, "manifest_path", path)
    object.__setattr__(result, "instruments", instruments)
    object.__setattr__(result, "membership_scope", SOURCE_SCOPED_LIQUID_UNIVERSE_MEMBERSHIP_SCOPE)
    object.__setattr__(result, "historical_membership_eligible", False)
    object.__setattr__(result, "ranking_eligible", False)
    object.__setattr__(result, "paper_trading_eligible", False)
    object.__setattr__(result, "model_selection_eligible", False)
    object.__setattr__(result, "liquidity_qualified", False)
    object.__setattr__(result, "cross_partition_alignment_eligible", False)
    object.__setattr__(result, "limitations", _BASE_LIMITATIONS)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _UNIVERSE_ATTESTATION)
    return result


def require_attested_source_scoped_liquid_universe(
    universe: object,
) -> SourceScopedLiquidUniverse:
    """Reject a forged universe before it reaches an offline consumer."""

    if (
        not isinstance(universe, SourceScopedLiquidUniverse)
        or getattr(universe, "_attestation", None) is not _UNIVERSE_ATTESTATION
        or getattr(universe, "manifest_id", None) != SOURCE_SCOPED_LIQUID_UNIVERSE_ID
        or getattr(universe, "membership_scope", None)
        != SOURCE_SCOPED_LIQUID_UNIVERSE_MEMBERSHIP_SCOPE
        or getattr(universe, "historical_membership_eligible", None) is not False
        or getattr(universe, "ranking_eligible", None) is not False
        or getattr(universe, "paper_trading_eligible", None) is not False
        or getattr(universe, "model_selection_eligible", None) is not False
        or getattr(universe, "liquidity_qualified", None) is not False
        or getattr(universe, "cross_partition_alignment_eligible", None) is not False
        or getattr(universe, "limitations", None) != _BASE_LIMITATIONS
        or not getattr(universe, "instruments", ())
    ):
        raise ValueError("source-scoped liquid universe requires loader attestation")
    return universe


def _reattested_source_payloads(
    *,
    source_paths: _SourceScopedLiquidUniverseSourcePaths,
    repository_root: Path,
    approved_source_identity: _ApprovedSourceIdentity | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], tuple[Path, ...]]:
    if not isinstance(source_paths, _SourceScopedLiquidUniverseSourcePaths):
        raise TypeError("liquid-universe source paths are invalid")
    index_path = _external_existing_file(
        source_paths.private_daily_index_path,
        repository_root,
        "private daily catalog index",
    )
    etf_source, etf_instruments = _private_daily_etf_source(
        index_path=index_path,
        expected_index_sha256=(
            approved_source_identity.private_daily_index_sha256
            if approved_source_identity is not None
            else None
        ),
    )
    evidence_path = _external_existing_file(
        source_paths.nas_panel_evidence_path,
        repository_root=repository_root,
        label="NAS panel evidence",
    )
    nas_source, nas_instruments, panel_path = _nas_panel_source(
        evidence_path=evidence_path,
        repository_root=repository_root,
        expected_evidence_sha256=(
            approved_source_identity.nas_panel_evidence_sha256
            if approved_source_identity is not None
            else None
        ),
        expected_panel_manifest_sha256=(
            approved_source_identity.nas_panel_manifest_sha256
            if approved_source_identity is not None
            else None
        ),
    )
    combined_instruments = (*etf_instruments, *nas_instruments)
    instrument_ids = [str(payload["instrument_id"]) for payload in combined_instruments]
    if len(instrument_ids) != len(set(instrument_ids)):
        raise ValueError("liquid-universe source instruments contain a duplicate identity")
    return (
        [etf_source, nas_source],
        [*etf_instruments, *nas_instruments],
        (index_path.parent, evidence_path.parent, panel_path.parent),
    )


def _private_daily_etf_source(
    *,
    index_path: Path,
    expected_index_sha256: str | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    index_bytes, index = _read_json_mapping(index_path, "private daily catalog index")
    if (
        index.get("kind") != "kis_paper_private_daily_backfill_index"
        or index.get("backfill_version") != "kis-paper-private-daily-backfill-v1"
    ):
        raise ValueError("private daily catalog index is incompatible")
    redaction = _required_mapping(index, "redaction", "private daily catalog index")
    storage = _required_mapping(index, "storage", "private daily catalog index")
    if (
        redaction.get("account_facts_persisted") is not False
        or redaction.get("credentials_persisted") is not False
        or storage.get("private_local_only") is not True
        or storage.get("redistributed") is not False
        or storage.get("served") is not False
    ):
        raise ValueError("private daily catalog index redaction is incompatible")
    targets_document = index.get("targets")
    if not isinstance(targets_document, list):
        raise ValueError("private daily catalog index targets are invalid")
    targets: dict[str, Mapping[str, object]] = {}
    for target in targets_document:
        if not isinstance(target, Mapping):
            raise ValueError("private daily catalog index targets are invalid")
        target_key = target.get("target_key")
        if not isinstance(target_key, str) or target_key in targets:
            raise ValueError("private daily catalog index targets are invalid")
        targets[target_key] = target
    expected_target_keys = tuple(target_key for _symbol, _venue, target_key in _ETF_TARGETS)
    if (
        tuple(targets) != expected_target_keys
        or tuple(KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS) != expected_target_keys
    ):
        raise ValueError("private daily catalog target provenance is incompatible")
    index_sha256 = _sha256(index_bytes)
    if expected_index_sha256 is not None and index_sha256 != expected_index_sha256:
        raise ValueError("private daily catalog index hash is unapproved")
    instruments: list[dict[str, object]] = []
    for symbol, venue, target_key in _ETF_TARGETS:
        target = targets[target_key]
        state = target.get("state")
        if (
            target.get("symbol") != symbol
            or target.get("exchange") != venue
            or target.get("venue_status") != "verified_by_kis_response"
            or state not in {"complete", "source_limited"}
        ):
            raise ValueError("private daily catalog target provenance is incompatible")
        limitations = list(_BASE_LIMITATIONS)
        if state == "source_limited":
            limitations.append("source_limited_history_scope")
        instruments.append(
            _instrument_payload(
                symbol=symbol,
                venue=venue,
                source_id=SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
                dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
                source_snapshot_sha256=index_sha256,
                availability_scope=f"current_local_private_daily_cache:{state}",
                limitations=tuple(limitations),
            )
        )
    return (
        {
            "source_id": SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
            "dataset_id": KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
            "source_snapshot_sha256": index_sha256,
            "catalog_provenance": {"path": str(index_path), "sha256": index_sha256},
            "supported_timeframes": [Timeframe.D1.value],
            "availability_scope": "current_local_private_daily_cache",
            "limitations": list(_BASE_LIMITATIONS),
        },
        instruments,
    )


def _nas_panel_source(
    *,
    evidence_path: Path,
    repository_root: Path,
    expected_evidence_sha256: str | None,
    expected_panel_manifest_sha256: str | None,
) -> tuple[dict[str, object], list[dict[str, object]], Path]:
    evidence_bytes, evidence = _read_json_mapping(evidence_path, "NAS panel evidence")
    evidence_sha256 = _sha256(evidence_bytes)
    if expected_evidence_sha256 is not None and evidence_sha256 != expected_evidence_sha256:
        raise ValueError("NAS panel evidence hash is unapproved")
    if evidence.get("kind") != "kis_paper_daily_universe_panel_evidence":
        raise ValueError("NAS panel evidence is incompatible")
    evidence_redaction = _required_mapping(evidence, "redaction", "NAS panel evidence")
    if (
        evidence_redaction.get("credentials_persisted") is not False
        or evidence_redaction.get("raw_rows_persisted") is not False
    ):
        raise ValueError("NAS panel evidence redaction is incompatible")
    evidence_scope = _required_mapping(evidence, "scope", "NAS panel evidence")
    if (
        evidence_scope.get("offline_local_paper_validation_only") is not True
        or evidence_scope.get("paper_trading_eligible") is not False
        or evidence_scope.get("ranking_eligible") is not False
    ):
        raise ValueError("NAS panel evidence scope is incompatible")
    panel_reference = _required_mapping(evidence, "panel_manifest", "NAS panel evidence")
    panel_path = _external_existing_file(
        _required_text(panel_reference, "path", "NAS panel evidence"),
        repository_root,
        "NAS panel manifest",
    )
    panel_sha256 = _required_sha256(panel_reference.get("sha256"), "NAS panel manifest sha256")
    if (
        expected_panel_manifest_sha256 is not None
        and panel_sha256 != expected_panel_manifest_sha256
    ):
        raise ValueError("NAS panel manifest hash is unapproved")
    panel_bytes, panel = _read_json_mapping(panel_path, "NAS panel manifest")
    if _sha256(panel_bytes) != panel_sha256:
        raise ValueError("NAS panel manifest hash mismatch")
    if (
        panel.get("kind") != "kis_paper_daily_universe_panel"
        or panel.get("dataset_id") is None
    ):
        raise ValueError("NAS panel manifest is incompatible")
    dataset_id = _required_text(panel, "dataset_id", "NAS panel manifest")
    dataset_content_sha256 = _required_sha256(
        panel.get("dataset_hash"),
        "NAS panel dataset hash",
    )
    scope = _required_mapping(panel, "scope", "NAS panel manifest")
    target_keys = tuple(f"{symbol}/{venue}" for symbol, venue in _NAS_TARGETS)
    if (
        scope.get("market") != "US"
        or scope.get("timeframe") != Timeframe.D1.value
        or scope.get("historical_point_in_time_eligible") is not False
        or scope.get("paper_trading_eligible") is not False
        or scope.get("ranking_eligible") is not False
        or tuple(scope.get("target_keys", ())) != target_keys
    ):
        raise ValueError("NAS panel manifest scope is incompatible")
    panel_limitations = panel.get("limitations")
    if not isinstance(panel_limitations, list) or not {
        "current_listing_registry_is_not_a_historical_point_in_time_universe",
        "corporate_action_semantics_not_qualified",
        "offline_local_paper_validation_only",
    }.issubset(panel_limitations):
        raise ValueError("NAS panel limitations are incompatible")
    evidence_source = _required_mapping(evidence, "source", "NAS panel evidence")
    if tuple(evidence_source.get("target_keys", ())) != target_keys:
        raise ValueError("NAS panel evidence target provenance is incompatible")
    instruments = [
        _instrument_payload(
            symbol=symbol,
            venue=venue,
            source_id=SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
            dataset_id=dataset_id,
            source_snapshot_sha256=panel_sha256,
            availability_scope="current_local_current_listing_d1_panel",
            limitations=_BASE_LIMITATIONS,
        )
        for symbol, venue in _NAS_TARGETS
    ]
    return (
        {
            "source_id": SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
            "dataset_id": dataset_id,
            "source_snapshot_sha256": panel_sha256,
            "dataset_content_sha256": dataset_content_sha256,
            "catalog_provenance": {
                "panel_manifest": {"path": str(panel_path), "sha256": panel_sha256},
                "evidence": {"path": str(evidence_path), "sha256": evidence_sha256},
            },
            "supported_timeframes": [Timeframe.D1.value],
            "availability_scope": "current_local_current_listing_d1_panel",
            "limitations": list(_BASE_LIMITATIONS),
        },
        instruments,
        panel_path,
    )


def _manifest_payload(
    *,
    sources: list[dict[str, object]],
    instruments: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "source_scoped_liquid_universe",
        "version": SOURCE_SCOPED_LIQUID_UNIVERSE_VERSION,
        "manifest_id": SOURCE_SCOPED_LIQUID_UNIVERSE_ID,
        "scope": {
            "membership_scope": SOURCE_SCOPED_LIQUID_UNIVERSE_MEMBERSHIP_SCOPE,
            "historical_membership_eligible": False,
            "ranking_eligible": False,
            "paper_trading_eligible": False,
            "model_selection_eligible": False,
            "liquidity_qualified": False,
            "cross_partition_alignment_eligible": False,
        },
        "sources": sources,
        "instruments": instruments,
        "limitations": list(_BASE_LIMITATIONS),
        "redaction": {
            "raw_rows_persisted": False,
            "credentials_persisted": False,
            "account_facts_persisted": False,
            "order_facts_persisted": False,
        },
    }


def _instrument_payload(
    *,
    symbol: str,
    venue: str,
    source_id: str,
    dataset_id: str,
    source_snapshot_sha256: str,
    availability_scope: str,
    limitations: tuple[str, ...],
) -> dict[str, object]:
    return {
        "instrument_id": f"{symbol}/{venue}",
        "symbol": symbol,
        "venue": venue,
        "source_id": source_id,
        "dataset_id": dataset_id,
        "source_snapshot_sha256": source_snapshot_sha256,
        "supported_timeframes": [Timeframe.D1.value],
        "availability_scope": availability_scope,
        "limitations": list(limitations),
    }


def _instrument_from_payload(payload: Mapping[str, object]) -> SourceScopedLiquidUniverseInstrument:
    timeframes = tuple(Timeframe(value) for value in payload["supported_timeframes"])
    if timeframes != (Timeframe.D1,):
        raise ValueError("liquid-universe instrument timeframe is incompatible")
    return SourceScopedLiquidUniverseInstrument(
        instrument_id=_required_text(payload, "instrument_id", "liquid-universe instrument"),
        symbol=_required_text(payload, "symbol", "liquid-universe instrument"),
        venue=_required_text(payload, "venue", "liquid-universe instrument"),
        source_id=_required_text(payload, "source_id", "liquid-universe instrument"),
        dataset_id=_required_text(payload, "dataset_id", "liquid-universe instrument"),
        source_snapshot_sha256=_required_sha256(
            payload.get("source_snapshot_sha256"),
            "liquid-universe instrument source snapshot hash",
        ),
        supported_timeframes=timeframes,
        availability_scope=_required_text(
            payload,
            "availability_scope",
            "liquid-universe instrument",
        ),
        limitations=tuple(payload["limitations"]),
    )


def _repository_root(repository_root: Path | str | None) -> Path:
    return Path(repository_root).resolve() if repository_root is not None else _REPOSITORY_ROOT


def _external_existing_file(
    path_value: Path | str,
    repository_root: Path,
    label: str,
    *,
    approved_parent: Path | None = None,
) -> Path:
    path = Path(path_value)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is unreadable")
    try:
        resolved = path.resolve()
    except OSError as error:
        raise ValueError(f"{label} is unreadable") from error
    if resolved.is_relative_to(repository_root):
        raise ValueError(f"{label} must stay outside Git")
    if approved_parent is not None and not resolved.is_relative_to(approved_parent.resolve()):
        raise ValueError(f"{label} must stay under its approved external root")
    return resolved


def _external_output_root(
    path_value: Path | str,
    repository_root: Path,
    label: str,
    *,
    approved_parent: Path | None,
) -> Path:
    candidate = Path(path_value).resolve()
    if candidate.is_relative_to(repository_root):
        raise ValueError(f"{label} must stay outside Git")
    if approved_parent is not None and not candidate.is_relative_to(approved_parent.resolve()):
        raise ValueError(f"{label} must stay under its approved external root")
    candidate.mkdir(parents=True, exist_ok=True)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError(f"{label} is invalid")
    resolved = candidate.resolve()
    if resolved.is_relative_to(repository_root):
        raise ValueError(f"{label} must stay outside Git")
    if approved_parent is not None and not resolved.is_relative_to(approved_parent.resolve()):
        raise ValueError(f"{label} must stay under its approved external root")
    return resolved


def _reject_output_overlap(
    *,
    output_root: Path,
    source_roots: tuple[Path, ...],
) -> None:
    if any(
        output_root.is_relative_to(source_root) or source_root.is_relative_to(output_root)
        for source_root in source_roots
    ):
        raise ValueError("liquid-universe output root must not overlap its source evidence")


def _read_json_mapping(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not isinstance(document, Mapping):
        raise ValueError(f"{label} is invalid")
    return payload, document


def _required_mapping(value: Mapping[str, object], key: str, label: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError(f"{label} {key} is invalid")
    return result


def _required_text(value: Mapping[str, object], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{label} {key} is invalid")
    return result


def _required_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{label} is invalid")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{label} is invalid")
    return value


def _write_immutable_file(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as error:
        if path.is_symlink() or path.read_bytes() != payload:
            raise ValueError(
                "liquid-universe manifest identity conflicts with existing output"
            ) from error


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")
