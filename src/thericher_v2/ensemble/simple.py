"""Minimal ensemble decision policy.

This deliberately supports one or more predictions but does not over-optimize
the first implementation. Richer blending belongs in the research lane.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC
from decimal import Decimal

from thericher_v2.contracts import EnsembleDecision, ModelPrediction


def decide(
    predictions: list[ModelPrediction],
    *,
    min_confidence: Decimal = Decimal("0.05"),
) -> EnsembleDecision:
    if not predictions:
        raise ValueError("at least one prediction is required")
    symbol = predictions[0].symbol
    market = predictions[0].market
    if any(item.symbol != symbol or item.market != market for item in predictions):
        raise ValueError("predictions must target one market/symbol")

    votes = Counter(item.signal.action for item in predictions)
    action = votes.most_common(1)[0][0]
    count = Decimal(len(predictions))
    confidence = sum((item.confidence for item in predictions), Decimal("0")) / count
    expected_edge_bps = sum((item.expected_edge_bps for item in predictions), Decimal("0")) / count
    if confidence < min_confidence:
        action = "hold"
    return EnsembleDecision(
        symbol=symbol,
        market=market,
        action=action,
        confidence=confidence,
        expected_edge_bps=expected_edge_bps,
        risk_score=max(Decimal("0"), Decimal("1") - confidence),
        prediction_ids=tuple(f"{item.model_id}:{item.model_version}" for item in predictions),
        decided_at=max(item.feature_window_end for item in predictions).astimezone(UTC),
        reason="single_model_or_majority_vote",
    )
