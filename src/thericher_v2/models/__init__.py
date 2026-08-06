"""Model implementations."""

from .current_source_opportunity_eligibility import (
    CAUSAL_BAR_SOURCE_CONTRACT_SCHEMA_ID,
    CurrentSourceContract,
    CurrentSourceMetadata,
    CurrentSourceOpportunityEligibility,
    adapt_current_source_opportunity_eligibility,
    build_causal_bar_source_contract,
)
from .momentum import MomentumModel
from .multitimeframe_momentum import (
    MultiTimeframeMomentumConfig,
    MultiTimeframeMomentumEvidence,
    MultiTimeframeMomentumSpec,
    build_multitimeframe_momentum_evidence,
    build_multitimeframe_momentum_evidence_from_causal_window,
)
from .sequence_window import (
    CAUSAL_SEQUENCE_WINDOW_SCHEMA_ID,
    SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
    CausalMultiTimeframeSequenceWindow,
    CausalSequenceWindow,
    SequenceWindowInputError,
    build_causal_multitimeframe_sequence_window,
)
from .target_exposure_allocator import (
    TargetExposureAllocationConfig,
    TargetExposureAllocationInput,
    allocate_target_exposure,
)
from .target_exposure_cycle_allocator import (
    TargetExposureAllocationCycleEntry,
    allocate_target_exposure_cycle,
)
from .target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
    propose_target_exposure,
)

__all__ = [
    "MomentumModel",
    "CAUSAL_SEQUENCE_WINDOW_SCHEMA_ID",
    "CAUSAL_BAR_SOURCE_CONTRACT_SCHEMA_ID",
    "SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES",
    "CausalMultiTimeframeSequenceWindow",
    "CausalSequenceWindow",
    "CurrentSourceContract",
    "CurrentSourceMetadata",
    "CurrentSourceOpportunityEligibility",
    "MultiTimeframeMomentumConfig",
    "MultiTimeframeMomentumEvidence",
    "MultiTimeframeMomentumSpec",
    "OpportunityEligibility",
    "TargetExposureAllocationConfig",
    "TargetExposureAllocationCycleEntry",
    "TargetExposureAllocationInput",
    "TargetPositionPolicyConfig",
    "SequenceWindowInputError",
    "allocate_target_exposure",
    "allocate_target_exposure_cycle",
    "adapt_current_source_opportunity_eligibility",
    "build_causal_bar_source_contract",
    "build_causal_multitimeframe_sequence_window",
    "build_multitimeframe_momentum_evidence",
    "build_multitimeframe_momentum_evidence_from_causal_window",
    "propose_target_exposure",
]
