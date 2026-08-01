"""Pure multi-timeframe evidence fusion into a model-side target proposal."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Final

from thericher_v2.contracts import (
    ModelPrediction,
    TargetExposureProposal,
    TargetInputStatus,
    Timeframe,
    decimal_value,
    require_utc,
)

_OPPORTUNITY_REFERENCE: Final = re.compile(r"ref:[0-9a-f]{32,128}")
_INPUT_STATUSES: Final = frozenset(
    {
        "ready",
        "missing",
        "stale",
        "incomplete",
        "duplicate",
        "non_contiguous",
        "misaligned",
        "future",
        "unqualified",
    }
)


@dataclass(frozen=True)
class OpportunityEligibility:
    """An already-computed opportunity fact consumed by the policy graph."""

    opportunity_ref: str
    symbol: str
    market: str
    eligible: bool
    input_status: TargetInputStatus
    observed_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if _OPPORTUNITY_REFERENCE.fullmatch(self.opportunity_ref) is None:
            raise ValueError("opportunity_ref must be an opaque reference")
        if not self.symbol.strip() or not self.market.strip():
            raise ValueError("opportunity symbol and market must be nonempty")
        if not isinstance(self.eligible, bool):
            raise TypeError("eligible must be boolean")
        if self.input_status not in _INPUT_STATUSES:
            raise ValueError("opportunity input_status is invalid")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.valid_until < self.observed_at:
            raise ValueError("opportunity validity is invalid")


@dataclass(frozen=True)
class TargetPositionPolicyConfig:
    """Frozen policy geometry; it deliberately contains no data or model weights."""

    policy_id: str
    feature_schema_id: str
    required_timeframes: tuple[Timeframe, ...]
    maximum_evidence_age: Mapping[Timeframe, timedelta]
    minimum_confidence: Decimal
    minimum_absolute_edge_bps: Decimal
    entry_target_exposure: Decimal
    decision_ttl: timedelta

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.feature_schema_id.strip():
            raise ValueError("policy identifiers must be nonempty")
        required_timeframes = tuple(self.required_timeframes)
        if (
            not required_timeframes
            or any(not isinstance(timeframe, Timeframe) for timeframe in required_timeframes)
            or len(set(required_timeframes)) != len(required_timeframes)
        ):
            raise ValueError("required_timeframes must be nonempty and unique")
        normalized_ages: dict[Timeframe, timedelta] = {}
        for timeframe, maximum_age in self.maximum_evidence_age.items():
            if not isinstance(timeframe, Timeframe) or not isinstance(maximum_age, timedelta):
                raise TypeError("maximum_evidence_age must map timeframes to timedeltas")
            if maximum_age <= timedelta(0):
                raise ValueError("maximum_evidence_age values must be positive")
            normalized_ages[timeframe] = maximum_age
        if set(normalized_ages) != set(required_timeframes):
            raise ValueError("maximum_evidence_age must cover exactly the required timeframes")
        if not isinstance(self.decision_ttl, timedelta) or self.decision_ttl <= timedelta(0):
            raise ValueError("decision_ttl must be positive")
        minimum_confidence = decimal_value(self.minimum_confidence, "minimum_confidence")
        entry_target_exposure = decimal_value(self.entry_target_exposure, "entry_target_exposure")
        minimum_absolute_edge_bps = decimal_value(
            self.minimum_absolute_edge_bps,
            "minimum_absolute_edge_bps",
        )
        if not 0 <= minimum_confidence <= 1 or not 0 < entry_target_exposure <= 1:
            raise ValueError("confidence and entry exposure bounds are invalid")
        if minimum_absolute_edge_bps <= 0:
            raise ValueError("minimum_absolute_edge_bps must be positive")
        object.__setattr__(self, "required_timeframes", required_timeframes)
        object.__setattr__(self, "maximum_evidence_age", MappingProxyType(normalized_ages))
        object.__setattr__(self, "minimum_confidence", minimum_confidence)
        object.__setattr__(self, "minimum_absolute_edge_bps", minimum_absolute_edge_bps)
        object.__setattr__(self, "entry_target_exposure", entry_target_exposure)


def propose_target_exposure(
    eligibility: OpportunityEligibility,
    predictions: Sequence[ModelPrediction],
    *,
    current_exposure: Decimal,
    config: TargetPositionPolicyConfig,
    as_of: datetime,
) -> TargetExposureProposal:
    """Fuse fresh completed-bar evidence without orders, I/O, or model selection."""

    if not isinstance(eligibility, OpportunityEligibility):
        raise TypeError("eligibility must be an OpportunityEligibility")
    if not isinstance(config, TargetPositionPolicyConfig):
        raise TypeError("config must be a TargetPositionPolicyConfig")
    now = require_utc(as_of, "as_of")
    normalized_current_exposure = decimal_value(current_exposure, "current_exposure")
    if not 0 <= normalized_current_exposure <= 1:
        raise ValueError("current_exposure must be between 0 and 1")
    if eligibility.input_status != "ready":
        return _abstain(
            eligibility,
            predictions,
            config=config,
            as_of=now,
            input_status=eligibility.input_status,
            reason=f"opportunity_{eligibility.input_status}",
        )
    if now < eligibility.observed_at:
        return _abstain(
            eligibility,
            predictions,
            config=config,
            as_of=now,
            input_status="future",
            reason="opportunity_future",
        )
    if now > eligibility.valid_until:
        return _abstain(
            eligibility,
            predictions,
            config=config,
            as_of=now,
            input_status="stale",
            reason="opportunity_stale",
        )
    if not eligibility.eligible:
        return _abstain(
            eligibility,
            predictions,
            config=config,
            as_of=now,
            input_status="ready",
            reason="opportunity_ineligible",
        )

    evidence_by_timeframe, input_status = _index_evidence(
        eligibility,
        predictions,
        config=config,
        as_of=now,
    )
    if input_status is not None:
        return _abstain(
            eligibility,
            predictions,
            config=config,
            as_of=now,
            input_status=input_status,
            reason=f"evidence_{input_status}",
        )

    ordered_evidence = tuple(
        evidence_by_timeframe[timeframe] for timeframe in config.required_timeframes
    )
    confidence = sum((item.confidence for item in ordered_evidence), Decimal("0")) / Decimal(
        len(ordered_evidence)
    )
    expected_edge_bps = sum(
        (item.expected_edge_bps for item in ordered_evidence),
        Decimal("0"),
    ) / Decimal(len(ordered_evidence))
    feature_window_end = max(item.feature_window_end for item in ordered_evidence)
    evidence_expiries = tuple(
        item.feature_window_end + config.maximum_evidence_age[item.signal.timeframe]
        for item in ordered_evidence
    )
    valid_until = min(
        eligibility.valid_until,
        now + config.decision_ttl,
        *evidence_expiries,
    )
    actions = {item.signal.action for item in ordered_evidence}
    if {"buy", "sell"}.issubset(actions):
        return _proposal(
            eligibility,
            ordered_evidence,
            config=config,
            as_of=now,
            action="abstain",
            target_exposure=Decimal("0"),
            confidence=confidence,
            input_status="ready",
            feature_window_end=feature_window_end,
            valid_until=valid_until,
            reason="expert_conflict",
        )
    if confidence < config.minimum_confidence:
        return _hold(
            eligibility,
            ordered_evidence,
            config=config,
            as_of=now,
            current_exposure=normalized_current_exposure,
            confidence=confidence,
            feature_window_end=feature_window_end,
            valid_until=valid_until,
            reason="confidence_below_threshold",
        )
    if actions == {"buy"} and expected_edge_bps >= config.minimum_absolute_edge_bps:
        if normalized_current_exposure < config.entry_target_exposure:
            return _proposal(
                eligibility,
                ordered_evidence,
                config=config,
                as_of=now,
                action="enter",
                target_exposure=config.entry_target_exposure,
                confidence=confidence,
                input_status="ready",
                feature_window_end=feature_window_end,
                valid_until=valid_until,
                reason="unanimous_entry",
            )
        return _hold(
            eligibility,
            ordered_evidence,
            config=config,
            as_of=now,
            current_exposure=normalized_current_exposure,
            confidence=confidence,
            feature_window_end=feature_window_end,
            valid_until=valid_until,
            reason="entry_target_already_held",
        )
    if actions == {"sell"} and expected_edge_bps <= -config.minimum_absolute_edge_bps:
        if normalized_current_exposure > 0:
            return _proposal(
                eligibility,
                ordered_evidence,
                config=config,
                as_of=now,
                action="exit",
                target_exposure=Decimal("0"),
                confidence=confidence,
                input_status="ready",
                feature_window_end=feature_window_end,
                valid_until=valid_until,
                reason="unanimous_exit",
            )
        return _hold(
            eligibility,
            ordered_evidence,
            config=config,
            as_of=now,
            current_exposure=normalized_current_exposure,
            confidence=confidence,
            feature_window_end=feature_window_end,
            valid_until=valid_until,
            reason="flat_exit_consensus",
        )
    return _hold(
        eligibility,
        ordered_evidence,
        config=config,
        as_of=now,
        current_exposure=normalized_current_exposure,
        confidence=confidence,
        feature_window_end=feature_window_end,
        valid_until=valid_until,
        reason="no_unanimous_net_edge",
    )


def _index_evidence(
    eligibility: OpportunityEligibility,
    predictions: Sequence[ModelPrediction],
    *,
    config: TargetPositionPolicyConfig,
    as_of: datetime,
) -> tuple[dict[Timeframe, ModelPrediction], TargetInputStatus | None]:
    indexed: dict[Timeframe, ModelPrediction] = {}
    for prediction in predictions:
        if not isinstance(prediction, ModelPrediction):
            raise TypeError("predictions must contain ModelPrediction values")
        if (
            prediction.symbol != eligibility.symbol
            or prediction.market != eligibility.market
            or prediction.signal.symbol != eligibility.symbol
            or prediction.signal.market != eligibility.market
            or prediction.signal.generated_at < prediction.feature_window_end
            or prediction.signal.timeframe not in config.required_timeframes
        ):
            return {}, "misaligned"
        if prediction.feature_window_end > as_of or prediction.signal.generated_at > as_of:
            return {}, "future"
        timeframe = prediction.signal.timeframe
        if timeframe in indexed:
            return {}, "duplicate"
        if as_of - prediction.feature_window_end > config.maximum_evidence_age[timeframe]:
            return {}, "stale"
        indexed[timeframe] = prediction
    if set(indexed) != set(config.required_timeframes):
        return {}, "missing"
    return indexed, None


def _abstain(
    eligibility: OpportunityEligibility,
    predictions: Sequence[ModelPrediction],
    *,
    config: TargetPositionPolicyConfig,
    as_of: datetime,
    input_status: TargetInputStatus,
    reason: str,
) -> TargetExposureProposal:
    return _proposal(
        eligibility,
        predictions,
        config=config,
        as_of=as_of,
        action="abstain",
        target_exposure=Decimal("0"),
        confidence=Decimal("0"),
        input_status=input_status,
        feature_window_end=None,
        valid_until=as_of,
        reason=reason,
    )


def _hold(
    eligibility: OpportunityEligibility,
    predictions: Sequence[ModelPrediction],
    *,
    config: TargetPositionPolicyConfig,
    as_of: datetime,
    current_exposure: Decimal,
    confidence: Decimal,
    feature_window_end: datetime,
    valid_until: datetime,
    reason: str,
) -> TargetExposureProposal:
    return _proposal(
        eligibility,
        predictions,
        config=config,
        as_of=as_of,
        action="hold",
        target_exposure=current_exposure,
        confidence=confidence,
        input_status="ready",
        feature_window_end=feature_window_end,
        valid_until=valid_until,
        reason=reason,
    )


def _proposal(
    eligibility: OpportunityEligibility,
    predictions: Sequence[ModelPrediction],
    *,
    config: TargetPositionPolicyConfig,
    as_of: datetime,
    action: str,
    target_exposure: Decimal,
    confidence: Decimal,
    input_status: TargetInputStatus,
    feature_window_end: datetime | None,
    valid_until: datetime,
    reason: str,
) -> TargetExposureProposal:
    return TargetExposureProposal(
        proposal_id=_proposal_id(
            eligibility,
            predictions,
            config=config,
            as_of=as_of,
            action=action,
            target_exposure=target_exposure,
            confidence=confidence,
            input_status=input_status,
            reason=reason,
        ),
        symbol=eligibility.symbol,
        market=eligibility.market,
        action=action,
        target_exposure=target_exposure,
        confidence=confidence,
        feature_schema_id=config.feature_schema_id,
        input_status=input_status,
        decided_at=as_of,
        valid_until=valid_until,
        feature_window_end=feature_window_end,
        reason=reason,
    )


def _proposal_id(
    eligibility: OpportunityEligibility,
    predictions: Sequence[ModelPrediction],
    *,
    config: TargetPositionPolicyConfig,
    as_of: datetime,
    action: str,
    target_exposure: Decimal,
    confidence: Decimal,
    input_status: TargetInputStatus,
    reason: str,
) -> str:
    evidence = [
        {
            "model_id": item.model_id,
            "model_version": item.model_version,
            "timeframe": item.signal.timeframe.value,
            "signal": item.signal.action,
            "confidence": str(item.confidence),
            "expected_edge_bps": str(item.expected_edge_bps),
            "feature_window_end": _timestamp(item.feature_window_end),
            "generated_at": _timestamp(item.signal.generated_at),
        }
        for item in sorted(
            (item for item in predictions if isinstance(item, ModelPrediction)),
            key=lambda item: (
                item.signal.timeframe.value,
                item.model_id,
                item.model_version,
                item.feature_window_end,
            ),
        )
    ]
    payload = {
        "policy_id": config.policy_id,
        "feature_schema_id": config.feature_schema_id,
        "policy_geometry": {
            "required_timeframes": [timeframe.value for timeframe in config.required_timeframes],
            "maximum_evidence_age_seconds": {
                timeframe.value: int(config.maximum_evidence_age[timeframe].total_seconds())
                for timeframe in config.required_timeframes
            },
            "minimum_confidence": str(config.minimum_confidence),
            "minimum_absolute_edge_bps": str(config.minimum_absolute_edge_bps),
            "entry_target_exposure": str(config.entry_target_exposure),
            "decision_ttl_seconds": int(config.decision_ttl.total_seconds()),
        },
        "opportunity_ref": eligibility.opportunity_ref,
        "symbol": eligibility.symbol,
        "market": eligibility.market,
        "as_of": _timestamp(as_of),
        "action": action,
        "target_exposure": str(target_exposure),
        "confidence": str(confidence),
        "input_status": input_status,
        "reason": reason,
        "evidence": evidence,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return f"policy:sha256:{hashlib.sha256(encoded).hexdigest()}"


def _timestamp(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")
