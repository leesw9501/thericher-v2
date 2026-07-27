"""Pure handoff from a current-source-scoped universe to future Research.

This module is intentionally metadata-only.  It cannot score, rank, choose a
trade, fit a model, load bars, or cross the execution boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from thericher_v2.contracts import Timeframe
from thericher_v2.data.source_scoped_liquid_universe import (
    SourceScopedLiquidUniverse,
    SourceScopedLiquidUniverseInstrument,
    require_attested_source_scoped_liquid_universe,
)

UNRANKED_OPPORTUNITY_SELECTION_INPUT_ID = "unranked-opportunity-selection-input-v1"
_UNRANKED_INPUT_ATTESTATION = object()


@dataclass(frozen=True, slots=True)
class UnrankedOpportunityInstrument:
    """Metadata-only candidate that has not been scored or selected."""

    instrument_id: str
    source_id: str
    dataset_id: str
    source_snapshot_sha256: str
    supported_timeframes: tuple[Timeframe, ...]
    availability_scope: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True, init=False)
class UnrankedOpportunitySelectionInput:
    """Attested unranked input for a future opportunity-selection layer."""

    input_id: str
    manifest_id: str
    manifest_sha256: str
    instruments: tuple[UnrankedOpportunityInstrument, ...]
    offline_only: bool
    historical_membership_eligible: bool
    ranking_eligible: bool
    paper_trading_eligible: bool
    model_selection_eligible: bool
    liquidity_qualified: bool
    cross_partition_alignment_eligible: bool
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified unranked opportunity-input builder")

    def safe_payload(self) -> dict[str, object]:
        require_attested_unranked_opportunity_selection_input(self)
        return {
            "input_id": self.input_id,
            "manifest_id": self.manifest_id,
            "manifest_sha256": self.manifest_sha256,
            "instrument_ids": [instrument.instrument_id for instrument in self.instruments],
            "offline_only": self.offline_only,
            "historical_membership_eligible": self.historical_membership_eligible,
            "ranking_eligible": self.ranking_eligible,
            "paper_trading_eligible": self.paper_trading_eligible,
            "model_selection_eligible": self.model_selection_eligible,
            "liquidity_qualified": self.liquidity_qualified,
            "cross_partition_alignment_eligible": self.cross_partition_alignment_eligible,
        }


def build_unranked_opportunity_selection_input(
    universe: SourceScopedLiquidUniverse,
    *,
    requested_use: str = "unranked_opportunity_selection",
) -> UnrankedOpportunitySelectionInput:
    """Expose every verified current instrument without any selection decision."""

    if requested_use != "unranked_opportunity_selection":
        raise ValueError("unranked opportunity input cannot be used for ranking or Paper trading")
    verified = require_attested_source_scoped_liquid_universe(universe)
    instruments = tuple(_instrument_from_universe(item) for item in verified.instruments)
    result = object.__new__(UnrankedOpportunitySelectionInput)
    object.__setattr__(result, "input_id", UNRANKED_OPPORTUNITY_SELECTION_INPUT_ID)
    object.__setattr__(result, "manifest_id", verified.manifest_id)
    object.__setattr__(result, "manifest_sha256", verified.manifest_sha256)
    object.__setattr__(result, "instruments", instruments)
    object.__setattr__(result, "offline_only", True)
    object.__setattr__(result, "historical_membership_eligible", False)
    object.__setattr__(result, "ranking_eligible", False)
    object.__setattr__(result, "paper_trading_eligible", False)
    object.__setattr__(result, "model_selection_eligible", False)
    object.__setattr__(result, "liquidity_qualified", False)
    object.__setattr__(result, "cross_partition_alignment_eligible", False)
    object.__setattr__(result, "_attestation", _UNRANKED_INPUT_ATTESTATION)
    return result


def require_attested_unranked_opportunity_selection_input(
    value: object,
) -> UnrankedOpportunitySelectionInput:
    """Reject a forged handoff before a later Research layer consumes it."""

    if (
        not isinstance(value, UnrankedOpportunitySelectionInput)
        or getattr(value, "_attestation", None) is not _UNRANKED_INPUT_ATTESTATION
        or getattr(value, "input_id", None) != UNRANKED_OPPORTUNITY_SELECTION_INPUT_ID
        or getattr(value, "offline_only", None) is not True
        or getattr(value, "historical_membership_eligible", None) is not False
        or getattr(value, "ranking_eligible", None) is not False
        or getattr(value, "paper_trading_eligible", None) is not False
        or getattr(value, "model_selection_eligible", None) is not False
        or getattr(value, "liquidity_qualified", None) is not False
        or getattr(value, "cross_partition_alignment_eligible", None) is not False
        or not getattr(value, "instruments", ())
    ):
        raise ValueError("unranked opportunity input requires builder attestation")
    return value


def _instrument_from_universe(
    instrument: SourceScopedLiquidUniverseInstrument,
) -> UnrankedOpportunityInstrument:
    if instrument.supported_timeframes != (Timeframe.D1,):
        raise ValueError("unranked opportunity input requires a D1-only source contract")
    return UnrankedOpportunityInstrument(
        instrument_id=instrument.instrument_id,
        source_id=instrument.source_id,
        dataset_id=instrument.dataset_id,
        source_snapshot_sha256=instrument.source_snapshot_sha256,
        supported_timeframes=instrument.supported_timeframes,
        availability_scope=instrument.availability_scope,
        limitations=instrument.limitations,
    )
