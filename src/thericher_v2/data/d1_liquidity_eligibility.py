"""Source-partitioned D1 eligibility facts for offline opportunity research.

This module evaluates only retained, verified daily bars.  Its receipt stores
categorical eligibility, provenance, and fixed thresholds; it never stores raw
bars, observed prices, volumes, or observed turnover values.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS,
    load_kis_paper_private_daily_catalog,
)
from thericher_v2.data.kis_paper_daily_universe_panel import (
    load_frozen_kis_paper_daily_universe_panel,
)
from thericher_v2.data.source_scoped_liquid_universe import (
    SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
    SOURCE_SCOPED_LIQUID_UNIVERSE_ID,
    SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
    SourceScopedLiquidUniverse,
    SourceScopedLiquidUniverseInstrument,
    load_source_scoped_liquid_universe_manifest,
    materialize_source_scoped_liquid_universe_manifest,
    require_attested_source_scoped_liquid_universe,
)

D1_LIQUIDITY_ELIGIBILITY_VERSION = "source-partitioned-d1-liquidity-eligibility-v1"
D1_LIQUIDITY_ELIGIBILITY_ID = "source.partitioned.d1.liquidity.eligibility-v1"
D1_LIQUIDITY_ELIGIBILITY_OUTPUT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/d1-liquidity-eligibility/v1"
)
D1_LIQUIDITY_ELIGIBILITY_APPROVED_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
D1_LIQUIDITY_ELIGIBILITY_MINIMUM_COMPLETED_BARS = 60
D1_LIQUIDITY_ELIGIBILITY_RECENT_WINDOW_BARS = 20
D1_LIQUIDITY_ELIGIBILITY_MINIMUM_MEDIAN_DOLLAR_TURNOVER = Decimal("10000000")

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_ELIGIBILITY_ATTESTATION = object()
_ETF_TARGET_KEY_BY_INSTRUMENT_ID = {
    "QQQ/NAS": "QQQ/NAS/MODP=0",
    "SPY/AMS": "SPY/AMS/MODP=0",
    "IWM/AMS": "IWM/AMS/MODP=0",
}
_NAS_INSTRUMENT_IDS = (
    "AAPL/NAS",
    "AMZN/NAS",
    "GOOGL/NAS",
    "META/NAS",
    "MSFT/NAS",
    "NVDA/NAS",
)
_EXPECTED_INSTRUMENT_IDS = tuple(_ETF_TARGET_KEY_BY_INSTRUMENT_ID) + _NAS_INSTRUMENT_IDS
_GLOBAL_LIMITATIONS = (
    "observed_d1_turnover_is_offline_eligibility_proxy_only",
    "not_intraday_liquidity_spread_depth_or_fillability_evidence",
    "not_historical_membership_or_cross_sectional_rank",
    "not_model_selection_or_paper_trading_input",
    "source_partitions_must_not_be_aligned_compared_or_blended",
)
_REASON_INSUFFICIENT_COMPLETED_BARS = "insufficient_completed_d1_bars"
_REASON_NONPOSITIVE_RECENT_VOLUME = "recent_completed_d1_volume_not_all_positive"
_REASON_TURNOVER_BELOW_THRESHOLD = "recent_completed_d1_median_turnover_below_threshold"


@dataclass(frozen=True, slots=True)
class D1LiquidityEligibilitySpec:
    """The fixed small D1 eligibility contract."""

    minimum_completed_bars: int = D1_LIQUIDITY_ELIGIBILITY_MINIMUM_COMPLETED_BARS
    recent_window_bars: int = D1_LIQUIDITY_ELIGIBILITY_RECENT_WINDOW_BARS
    minimum_median_dollar_turnover: Decimal = (
        D1_LIQUIDITY_ELIGIBILITY_MINIMUM_MEDIAN_DOLLAR_TURNOVER
    )

    def __post_init__(self) -> None:
        if self.minimum_completed_bars < self.recent_window_bars:
            raise ValueError("D1 eligibility completed-bar threshold is incompatible")
        if self.recent_window_bars <= 0 or self.recent_window_bars % 2 != 0:
            raise ValueError("D1 eligibility recent window must be a positive even count")
        if self.minimum_median_dollar_turnover <= 0:
            raise ValueError("D1 eligibility turnover threshold must be positive")


D1_LIQUIDITY_ELIGIBILITY_SPEC = D1LiquidityEligibilitySpec()


@dataclass(frozen=True, slots=True)
class D1LiquidityEligibilityInstrument:
    """One categorical D1 research-eligibility result with no observed values."""

    instrument_id: str
    symbol: str
    venue: str
    source_partition_id: str
    dataset_id: str
    dataset_hash: str
    source_snapshot_sha256: str
    d1_research_eligible: bool
    ineligibility_reasons: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class D1LiquidityEligibilityPartition:
    """A source-local group that must not be aligned with another group."""

    source_partition_id: str
    instruments: tuple[D1LiquidityEligibilityInstrument, ...]


@dataclass(frozen=True, slots=True)
class D1LiquidityEligibilityMaterialization:
    """One immutable external receipt identity."""

    receipt_path: Path
    receipt_sha256: str
    partition_count: int
    instrument_count: int


@dataclass(frozen=True, slots=True, init=False)
class SourcePartitionedD1LiquidityEligibility:
    """An attested source-local D1 fact set for one offline Research handoff."""

    receipt_id: str
    receipt_sha256: str
    receipt_path: Path
    source_universe_manifest_id: str
    source_universe_manifest_sha256: str
    spec: D1LiquidityEligibilitySpec
    partitions: tuple[D1LiquidityEligibilityPartition, ...]
    historical_membership_eligible: bool
    ranking_eligible: bool
    model_selection_eligible: bool
    paper_trading_eligible: bool
    liquidity_qualified: bool
    executable_liquidity_eligible: bool
    cross_partition_alignment_eligible: bool
    limitations: tuple[str, ...]
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified D1 liquidity-eligibility receipt loader")

    def safe_payload(self) -> dict[str, object]:
        """Return only categorical facts and provenance for an offline consumer."""

        require_attested_source_partitioned_d1_liquidity_eligibility(self)
        return {
            "receipt_id": self.receipt_id,
            "receipt_sha256": self.receipt_sha256,
            "source_universe_manifest_id": self.source_universe_manifest_id,
            "source_universe_manifest_sha256": self.source_universe_manifest_sha256,
            "partitions": [
                {
                    "source_partition_id": partition.source_partition_id,
                    "instruments": [
                        {
                            "instrument_id": instrument.instrument_id,
                            "source_partition_id": instrument.source_partition_id,
                            "dataset_id": instrument.dataset_id,
                            "dataset_hash": instrument.dataset_hash,
                            "source_snapshot_sha256": instrument.source_snapshot_sha256,
                            "d1_research_eligible": instrument.d1_research_eligible,
                            "ineligibility_reasons": list(instrument.ineligibility_reasons),
                            "limitations": list(instrument.limitations),
                        }
                        for instrument in partition.instruments
                    ],
                }
                for partition in self.partitions
            ],
            "historical_membership_eligible": self.historical_membership_eligible,
            "ranking_eligible": self.ranking_eligible,
            "model_selection_eligible": self.model_selection_eligible,
            "paper_trading_eligible": self.paper_trading_eligible,
            "liquidity_qualified": self.liquidity_qualified,
            "executable_liquidity_eligible": self.executable_liquidity_eligible,
            "cross_partition_alignment_eligible": self.cross_partition_alignment_eligible,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class _D1LiquidityEligibilityComputation:
    source_universe_manifest_id: str
    source_universe_manifest_sha256: str
    spec: D1LiquidityEligibilitySpec
    partitions: tuple[D1LiquidityEligibilityPartition, ...]


def evaluate_d1_liquidity_eligibility(
    *,
    instrument: SourceScopedLiquidUniverseInstrument,
    bars: Sequence[Bar],
    dataset_hash: str,
) -> D1LiquidityEligibilityInstrument:
    """Classify one verified D1 stream without returning an observed metric."""

    _validate_instrument(instrument)
    _require_sha256(dataset_hash, "D1 eligibility dataset hash")
    stream = tuple(bars)
    _validate_d1_stream(instrument=instrument, bars=stream)
    completed = tuple(bar for bar in stream if bar.complete)
    reasons: list[str] = []
    if len(completed) < D1_LIQUIDITY_ELIGIBILITY_SPEC.minimum_completed_bars:
        reasons.append(_REASON_INSUFFICIENT_COMPLETED_BARS)
    if len(completed) >= D1_LIQUIDITY_ELIGIBILITY_SPEC.recent_window_bars:
        recent = completed[-D1_LIQUIDITY_ELIGIBILITY_SPEC.recent_window_bars :]
        if any(bar.volume <= 0 for bar in recent):
            reasons.append(_REASON_NONPOSITIVE_RECENT_VOLUME)
        else:
            median_turnover = _median(
                tuple(bar.close * bar.volume for bar in recent)
            )
            if median_turnover < D1_LIQUIDITY_ELIGIBILITY_SPEC.minimum_median_dollar_turnover:
                reasons.append(_REASON_TURNOVER_BELOW_THRESHOLD)
    eligible = not reasons
    return D1LiquidityEligibilityInstrument(
        instrument_id=instrument.instrument_id,
        symbol=instrument.symbol,
        venue=instrument.venue,
        source_partition_id=instrument.source_id,
        dataset_id=instrument.dataset_id,
        dataset_hash=dataset_hash,
        source_snapshot_sha256=instrument.source_snapshot_sha256,
        d1_research_eligible=eligible,
        ineligibility_reasons=tuple(reasons),
        limitations=instrument.limitations,
    )


def materialize_source_partitioned_d1_liquidity_eligibility(
    *,
    output_root: Path | str = D1_LIQUIDITY_ELIGIBILITY_OUTPUT_ROOT,
    repository_root: Path | str | None = None,
) -> D1LiquidityEligibilityMaterialization:
    """Compute and write the one current source-safe D1 eligibility receipt."""

    repository = _repository_root(repository_root)
    computation = _compute_current_d1_liquidity_eligibility(repository_root=repository)
    return _materialize_source_partitioned_d1_liquidity_eligibility(
        computation=computation,
        output_root=output_root,
        repository_root=repository,
        require_approved_output_root=True,
    )


def load_source_partitioned_d1_liquidity_eligibility(
    receipt_path: Path | str,
    *,
    repository_root: Path | str | None = None,
) -> SourcePartitionedD1LiquidityEligibility:
    """Recompute and reattest one receipt from the approved local sources."""

    repository = _repository_root(repository_root)
    computation = _compute_current_d1_liquidity_eligibility(repository_root=repository)
    return _load_source_partitioned_d1_liquidity_eligibility(
        receipt_path=receipt_path,
        computation=computation,
        repository_root=repository,
        require_approved_receipt_root=True,
    )


def require_attested_source_partitioned_d1_liquidity_eligibility(
    value: object,
) -> SourcePartitionedD1LiquidityEligibility:
    """Reject forged or misuse-expanded D1 eligibility facts."""

    if (
        not isinstance(value, SourcePartitionedD1LiquidityEligibility)
        or getattr(value, "_attestation", None) is not _ELIGIBILITY_ATTESTATION
        or getattr(value, "receipt_id", None) != D1_LIQUIDITY_ELIGIBILITY_ID
        or not _is_sha256(getattr(value, "receipt_sha256", None))
        or getattr(value, "source_universe_manifest_id", None)
        != SOURCE_SCOPED_LIQUID_UNIVERSE_ID
        or not _is_sha256(getattr(value, "source_universe_manifest_sha256", None))
        or getattr(value, "spec", None) != D1_LIQUIDITY_ELIGIBILITY_SPEC
        or getattr(value, "historical_membership_eligible", None) is not False
        or getattr(value, "ranking_eligible", None) is not False
        or getattr(value, "model_selection_eligible", None) is not False
        or getattr(value, "paper_trading_eligible", None) is not False
        or getattr(value, "liquidity_qualified", None) is not False
        or getattr(value, "executable_liquidity_eligible", None) is not False
        or getattr(value, "cross_partition_alignment_eligible", None) is not False
        or getattr(value, "limitations", None) != _GLOBAL_LIMITATIONS
        or tuple(partition.source_partition_id for partition in getattr(value, "partitions", ()))
        != (
            SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
            SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
        )
    ):
        raise ValueError("D1 liquidity eligibility requires receipt attestation")
    for partition in value.partitions:
        if not partition.instruments or any(
            item.source_partition_id != partition.source_partition_id
            for item in partition.instruments
        ):
            raise ValueError("D1 liquidity eligibility partition is incompatible")
    return value


def _compute_current_d1_liquidity_eligibility(
    *,
    repository_root: Path,
) -> _D1LiquidityEligibilityComputation:
    source_manifest = materialize_source_scoped_liquid_universe_manifest(
        repository_root=repository_root
    )
    universe = load_source_scoped_liquid_universe_manifest(
        source_manifest.manifest_path,
        repository_root=repository_root,
    )
    return _compute_d1_liquidity_eligibility_from_universe(
        universe=universe,
        repository_root=repository_root,
    )


def _compute_d1_liquidity_eligibility_from_universe(
    *,
    universe: SourceScopedLiquidUniverse,
    repository_root: Path,
) -> _D1LiquidityEligibilityComputation:
    verified = require_attested_source_scoped_liquid_universe(universe)
    if tuple(item.instrument_id for item in verified.instruments) != _EXPECTED_INSTRUMENT_IDS:
        raise ValueError("D1 eligibility source universe instrument set is incompatible")
    etf_instruments = tuple(
        item
        for item in verified.instruments
        if item.source_id == SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID
    )
    nas_instruments = tuple(
        item
        for item in verified.instruments
        if item.source_id == SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID
    )
    if (
        tuple(item.instrument_id for item in etf_instruments)
        != tuple(_ETF_TARGET_KEY_BY_INSTRUMENT_ID)
        or tuple(item.instrument_id for item in nas_instruments) != _NAS_INSTRUMENT_IDS
    ):
        raise ValueError("D1 eligibility source partitions are incompatible")

    etf_facts: list[D1LiquidityEligibilityInstrument] = []
    for instrument in etf_instruments:
        target_key = _ETF_TARGET_KEY_BY_INSTRUMENT_ID[instrument.instrument_id]
        if target_key not in KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS:
            raise ValueError("D1 eligibility ETF target is unsupported")
        catalog = load_kis_paper_private_daily_catalog(
            target_keys=(target_key,),
            expected_index_hash=instrument.source_snapshot_sha256,
            repo_root=repository_root,
        )
        if (
            catalog.dataset_id != instrument.dataset_id
            or catalog.index_hash != instrument.source_snapshot_sha256
            or instrument.symbol not in catalog.bars_by_symbol
        ):
            raise ValueError("D1 eligibility ETF source provenance is incompatible")
        cataloged_bars = catalog.bars_by_symbol[instrument.symbol]
        etf_facts.append(
            evaluate_d1_liquidity_eligibility(
                instrument=instrument,
                bars=cataloged_bars.bars,
                dataset_hash=cataloged_bars.dataset_hash,
            )
        )

    expected_nas_dataset_hash = _source_dataset_content_hash(
        universe=verified,
        source_id=SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
    )
    panel = load_frozen_kis_paper_daily_universe_panel()
    nas_facts: list[D1LiquidityEligibilityInstrument] = []
    for instrument in nas_instruments:
        if (
            panel.dataset_id != instrument.dataset_id
            or panel.dataset_hash != expected_nas_dataset_hash
        ):
            raise ValueError("D1 eligibility NAS source provenance is incompatible")
        cataloged_bars = panel.validation_series(instrument.symbol)
        nas_facts.append(
            evaluate_d1_liquidity_eligibility(
                instrument=instrument,
                bars=cataloged_bars.bars,
                dataset_hash=cataloged_bars.dataset_hash,
            )
        )

    return _D1LiquidityEligibilityComputation(
        source_universe_manifest_id=verified.manifest_id,
        source_universe_manifest_sha256=verified.manifest_sha256,
        spec=D1_LIQUIDITY_ELIGIBILITY_SPEC,
        partitions=(
            D1LiquidityEligibilityPartition(
                source_partition_id=SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
                instruments=tuple(etf_facts),
            ),
            D1LiquidityEligibilityPartition(
                source_partition_id=SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
                instruments=tuple(nas_facts),
            ),
        ),
    )


def _materialize_source_partitioned_d1_liquidity_eligibility(
    *,
    computation: _D1LiquidityEligibilityComputation,
    output_root: Path | str,
    repository_root: Path,
    require_approved_output_root: bool,
) -> D1LiquidityEligibilityMaterialization:
    payload = _receipt_payload(computation)
    encoded = _json_bytes(payload)
    receipt_sha256 = _sha256(encoded)
    root = _external_output_root(
        output_root,
        repository_root,
        "D1 eligibility output root",
        approved_parent=(
            D1_LIQUIDITY_ELIGIBILITY_APPROVED_ARTIFACT_ROOT
            if require_approved_output_root
            else None
        ),
    )
    path = root / f"{D1_LIQUIDITY_ELIGIBILITY_ID}-{receipt_sha256[7:23]}.json"
    _write_immutable_file(path, encoded)
    return D1LiquidityEligibilityMaterialization(
        receipt_path=path,
        receipt_sha256=receipt_sha256,
        partition_count=len(computation.partitions),
        instrument_count=sum(len(partition.instruments) for partition in computation.partitions),
    )


def _load_source_partitioned_d1_liquidity_eligibility(
    *,
    receipt_path: Path | str,
    computation: _D1LiquidityEligibilityComputation,
    repository_root: Path,
    require_approved_receipt_root: bool,
) -> SourcePartitionedD1LiquidityEligibility:
    path = _external_existing_file(
        receipt_path,
        repository_root,
        "D1 eligibility receipt",
        approved_parent=(
            D1_LIQUIDITY_ELIGIBILITY_OUTPUT_ROOT
            if require_approved_receipt_root
            else None
        ),
    )
    payload_bytes, payload = _read_json_mapping(path, "D1 eligibility receipt")
    expected = _receipt_payload(computation)
    if payload != expected or payload_bytes != _json_bytes(expected):
        raise ValueError("D1 eligibility receipt source provenance is incompatible")
    return _attested_eligibility(
        computation=computation,
        receipt_path=path,
        receipt_sha256=_sha256(payload_bytes),
    )


def _attested_eligibility(
    *,
    computation: _D1LiquidityEligibilityComputation,
    receipt_path: Path,
    receipt_sha256: str,
) -> SourcePartitionedD1LiquidityEligibility:
    result = object.__new__(SourcePartitionedD1LiquidityEligibility)
    object.__setattr__(result, "receipt_id", D1_LIQUIDITY_ELIGIBILITY_ID)
    object.__setattr__(result, "receipt_sha256", receipt_sha256)
    object.__setattr__(result, "receipt_path", receipt_path)
    object.__setattr__(
        result,
        "source_universe_manifest_id",
        computation.source_universe_manifest_id,
    )
    object.__setattr__(
        result,
        "source_universe_manifest_sha256",
        computation.source_universe_manifest_sha256,
    )
    object.__setattr__(result, "spec", computation.spec)
    object.__setattr__(result, "partitions", computation.partitions)
    object.__setattr__(result, "historical_membership_eligible", False)
    object.__setattr__(result, "ranking_eligible", False)
    object.__setattr__(result, "model_selection_eligible", False)
    object.__setattr__(result, "paper_trading_eligible", False)
    object.__setattr__(result, "liquidity_qualified", False)
    object.__setattr__(result, "executable_liquidity_eligible", False)
    object.__setattr__(result, "cross_partition_alignment_eligible", False)
    object.__setattr__(result, "limitations", _GLOBAL_LIMITATIONS)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _ELIGIBILITY_ATTESTATION)
    return result


def _receipt_payload(computation: _D1LiquidityEligibilityComputation) -> dict[str, object]:
    if (
        computation.source_universe_manifest_id != SOURCE_SCOPED_LIQUID_UNIVERSE_ID
        or not _is_sha256(computation.source_universe_manifest_sha256)
        or computation.spec != D1_LIQUIDITY_ELIGIBILITY_SPEC
    ):
        raise ValueError("D1 eligibility computation is incompatible")
    expected_partition_ids = (
        SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
        SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
    )
    if (
        tuple(partition.source_partition_id for partition in computation.partitions)
        != expected_partition_ids
    ):
        raise ValueError("D1 eligibility computation partitions are incompatible")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "source_partitioned_d1_liquidity_eligibility",
        "version": D1_LIQUIDITY_ELIGIBILITY_VERSION,
        "receipt_id": D1_LIQUIDITY_ELIGIBILITY_ID,
        "contract": {
            "timeframe": Timeframe.D1.value,
            "minimum_completed_bars": computation.spec.minimum_completed_bars,
            "recent_completed_window_bars": computation.spec.recent_window_bars,
            "minimum_median_dollar_turnover": str(
                computation.spec.minimum_median_dollar_turnover
            ),
        },
        "source_universe": {
            "manifest_id": computation.source_universe_manifest_id,
            "manifest_sha256": computation.source_universe_manifest_sha256,
        },
        "partitions": [
            {
                "source_partition_id": partition.source_partition_id,
                "instruments": [_instrument_payload(item) for item in partition.instruments],
            }
            for partition in computation.partitions
        ],
        "scope": {
            "offline_d1_research_eligibility_only": True,
            "historical_membership_eligible": False,
            "ranking_eligible": False,
            "model_selection_eligible": False,
            "paper_trading_eligible": False,
            "liquidity_qualified": False,
            "executable_liquidity_eligible": False,
            "cross_partition_alignment_eligible": False,
        },
        "limitations": list(_GLOBAL_LIMITATIONS),
        "redaction": {
            "raw_rows_persisted": False,
            "observed_prices_persisted": False,
            "observed_volumes_persisted": False,
            "observed_turnover_values_persisted": False,
            "credentials_persisted": False,
            "account_facts_persisted": False,
            "order_facts_persisted": False,
        },
    }


def _instrument_payload(instrument: D1LiquidityEligibilityInstrument) -> dict[str, object]:
    if (
        instrument.source_partition_id
        not in {
            SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
            SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_SOURCE_ID,
        }
        or not _is_sha256(instrument.dataset_hash)
        or not _is_sha256(instrument.source_snapshot_sha256)
    ):
        raise ValueError("D1 eligibility instrument provenance is incompatible")
    return {
        "instrument_id": instrument.instrument_id,
        "symbol": instrument.symbol,
        "venue": instrument.venue,
        "source_partition_id": instrument.source_partition_id,
        "dataset_id": instrument.dataset_id,
        "dataset_hash": instrument.dataset_hash,
        "source_snapshot_sha256": instrument.source_snapshot_sha256,
        "d1_research_eligible": instrument.d1_research_eligible,
        "ineligibility_reasons": list(instrument.ineligibility_reasons),
        "limitations": list(instrument.limitations),
    }


def _source_dataset_content_hash(
    *,
    universe: SourceScopedLiquidUniverse,
    source_id: str,
) -> str:
    path = universe.manifest_path
    if path.is_symlink() or not path.is_file():
        raise ValueError("D1 eligibility source universe manifest is unavailable")
    payload_bytes, payload = _read_json_mapping(path, "D1 eligibility source universe manifest")
    if _sha256(payload_bytes) != universe.manifest_sha256:
        raise ValueError("D1 eligibility source universe manifest changed after attestation")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("D1 eligibility source universe manifest is incompatible")
    for source in sources:
        if not isinstance(source, Mapping) or source.get("source_id") != source_id:
            continue
        return _require_sha256(
            source.get("dataset_content_sha256"),
            "D1 eligibility source dataset hash",
        )
    raise ValueError("D1 eligibility source dataset hash is unavailable")


def _validate_instrument(instrument: SourceScopedLiquidUniverseInstrument) -> None:
    if (
        instrument.supported_timeframes != (Timeframe.D1,)
        or not instrument.instrument_id
        or not instrument.symbol
        or not instrument.venue
        or not instrument.dataset_id
        or not _is_sha256(instrument.source_snapshot_sha256)
    ):
        raise ValueError("D1 eligibility requires a verified D1 source instrument")


def _validate_d1_stream(
    *,
    instrument: SourceScopedLiquidUniverseInstrument,
    bars: tuple[Bar, ...],
) -> None:
    previous_start = None
    for bar in bars:
        if (
            bar.timeframe is not Timeframe.D1
            or bar.symbol != instrument.symbol
            or bar.market != "US"
        ):
            raise ValueError("D1 eligibility stream is incompatible")
        if previous_start is not None and bar.start_ts <= previous_start:
            raise ValueError("D1 eligibility stream must be chronological and unique")
        previous_start = bar.start_ts


def _median(values: tuple[Decimal, ...]) -> Decimal:
    if not values or len(values) % 2 != 0:
        raise ValueError("D1 eligibility median requires a nonempty even window")
    ordered = tuple(sorted(values))
    upper_index = len(ordered) // 2
    return (ordered[upper_index - 1] + ordered[upper_index]) / Decimal("2")


def _repository_root(repository_root: Path | str | None) -> Path:
    root = Path(repository_root) if repository_root is not None else _REPOSITORY_ROOT
    if root.is_symlink() or not root.is_dir():
        raise ValueError("D1 eligibility repository root is invalid")
    return root.resolve()


def _external_existing_file(
    path: Path | str,
    repository_root: Path,
    label: str,
    *,
    approved_parent: Path | None,
) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"{label} is unavailable")
    resolved = candidate.resolve()
    if _path_contains(repository_root, resolved):
        raise ValueError(f"{label} must stay outside Git")
    if approved_parent is not None and not _path_contains(approved_parent, resolved):
        raise ValueError(f"{label} must stay under the approved external root")
    return resolved


def _external_output_root(
    root: Path | str,
    repository_root: Path,
    label: str,
    *,
    approved_parent: Path | None,
) -> Path:
    candidate = Path(root)
    if candidate.is_symlink():
        raise ValueError(f"{label} is invalid")
    resolved = candidate.resolve()
    if _path_contains(repository_root, resolved):
        raise ValueError(f"{label} must stay outside Git")
    if approved_parent is not None and not _path_contains(approved_parent, resolved):
        raise ValueError(f"{label} must stay under the approved external root")
    return resolved


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


def _write_immutable_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise ValueError("D1 eligibility immutable output conflicts")
        return
    staging = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(payload)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _require_sha256(value: object, label: str) -> str:
    if not _is_sha256(value):
        raise ValueError(f"{label} is invalid")
    return str(value)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
