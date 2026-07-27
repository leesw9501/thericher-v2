"""Pure Research handoff for source-partitioned D1 eligibility facts.

The handoff has no bar, score, model, replay, provider, credential, or broker
surface.  It preserves source partitions so a later layer cannot silently turn
current local coverage into a cross-sectional selection rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from thericher_v2.data.d1_liquidity_eligibility import (
    D1LiquidityEligibilityInstrument,
    SourcePartitionedD1LiquidityEligibility,
    require_attested_source_partitioned_d1_liquidity_eligibility,
)

D1_RESEARCH_ELIGIBILITY_INPUT_ID = "d1-research-eligibility-input-v1"
_D1_RESEARCH_INPUT_ATTESTATION = object()


@dataclass(frozen=True, slots=True)
class D1ResearchEligibilityInstrument:
    """One categorical offline Research eligibility fact."""

    instrument_id: str
    source_partition_id: str
    dataset_id: str
    dataset_hash: str
    source_snapshot_sha256: str
    d1_research_eligible: bool
    ineligibility_reasons: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class D1ResearchEligibilityPartition:
    """A preserved source-local collection of eligibility facts."""

    source_partition_id: str
    instruments: tuple[D1ResearchEligibilityInstrument, ...]


@dataclass(frozen=True, slots=True, init=False)
class D1ResearchEligibilityInput:
    """Attested input for future offline opportunity research only."""

    input_id: str
    receipt_id: str
    receipt_sha256: str
    partitions: tuple[D1ResearchEligibilityPartition, ...]
    historical_membership_eligible: bool
    ranking_eligible: bool
    model_selection_eligible: bool
    paper_trading_eligible: bool
    executable_liquidity_eligible: bool
    cross_partition_alignment_eligible: bool
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified D1 research-eligibility input builder")

    def safe_payload(self) -> dict[str, object]:
        """Return categorical source-local facts without a score or action."""

        require_attested_d1_research_eligibility_input(self)
        return {
            "input_id": self.input_id,
            "receipt_id": self.receipt_id,
            "receipt_sha256": self.receipt_sha256,
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
            "executable_liquidity_eligible": self.executable_liquidity_eligible,
            "cross_partition_alignment_eligible": self.cross_partition_alignment_eligible,
        }


def build_d1_research_eligibility_input(
    eligibility: SourcePartitionedD1LiquidityEligibility,
) -> D1ResearchEligibilityInput:
    """Build one source-preserving, categorical offline Research handoff."""

    verified = require_attested_source_partitioned_d1_liquidity_eligibility(eligibility)
    result = object.__new__(D1ResearchEligibilityInput)
    object.__setattr__(result, "input_id", D1_RESEARCH_ELIGIBILITY_INPUT_ID)
    object.__setattr__(result, "receipt_id", verified.receipt_id)
    object.__setattr__(result, "receipt_sha256", verified.receipt_sha256)
    object.__setattr__(
        result,
        "partitions",
        tuple(
            D1ResearchEligibilityPartition(
                source_partition_id=partition.source_partition_id,
                instruments=tuple(
                    _instrument_from_eligibility(item) for item in partition.instruments
                ),
            )
            for partition in verified.partitions
        ),
    )
    object.__setattr__(result, "historical_membership_eligible", False)
    object.__setattr__(result, "ranking_eligible", False)
    object.__setattr__(result, "model_selection_eligible", False)
    object.__setattr__(result, "paper_trading_eligible", False)
    object.__setattr__(result, "executable_liquidity_eligible", False)
    object.__setattr__(result, "cross_partition_alignment_eligible", False)
    object.__setattr__(result, "_attestation", _D1_RESEARCH_INPUT_ATTESTATION)
    return result


def require_attested_d1_research_eligibility_input(
    value: object,
) -> D1ResearchEligibilityInput:
    """Reject forged inputs or attempts to widen the consumer's scope."""

    if (
        not isinstance(value, D1ResearchEligibilityInput)
        or getattr(value, "_attestation", None) is not _D1_RESEARCH_INPUT_ATTESTATION
        or getattr(value, "input_id", None) != D1_RESEARCH_ELIGIBILITY_INPUT_ID
        or not getattr(value, "receipt_id", None)
        or not getattr(value, "receipt_sha256", None)
        or getattr(value, "historical_membership_eligible", None) is not False
        or getattr(value, "ranking_eligible", None) is not False
        or getattr(value, "model_selection_eligible", None) is not False
        or getattr(value, "paper_trading_eligible", None) is not False
        or getattr(value, "executable_liquidity_eligible", None) is not False
        or getattr(value, "cross_partition_alignment_eligible", None) is not False
        or not getattr(value, "partitions", ())
    ):
        raise ValueError("D1 research eligibility input requires builder attestation")
    if any(
        not partition.instruments
        or any(
            instrument.source_partition_id != partition.source_partition_id
            for instrument in partition.instruments
        )
        for partition in value.partitions
    ):
        raise ValueError("D1 research eligibility input partitions are incompatible")
    return value


def _instrument_from_eligibility(
    instrument: D1LiquidityEligibilityInstrument,
) -> D1ResearchEligibilityInstrument:
    return D1ResearchEligibilityInstrument(
        instrument_id=instrument.instrument_id,
        source_partition_id=instrument.source_partition_id,
        dataset_id=instrument.dataset_id,
        dataset_hash=instrument.dataset_hash,
        source_snapshot_sha256=instrument.source_snapshot_sha256,
        d1_research_eligible=instrument.d1_research_eligible,
        ineligibility_reasons=instrument.ineligibility_reasons,
        limitations=instrument.limitations,
    )
