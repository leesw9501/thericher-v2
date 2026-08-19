from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from thericher_v2.contracts import ModelPrediction, Signal, Timeframe
from thericher_v2.ensemble import decide


def test_tied_vote_holds_regardless_of_prediction_order() -> None:
    buy_prediction = _prediction(model_id="buy-model", action="buy")
    sell_prediction = _prediction(model_id="sell-model", action="sell")

    first = decide([buy_prediction, sell_prediction])
    reversed_order = decide([sell_prediction, buy_prediction])

    assert (first.action, first.reason) == ("hold", "tied_vote_hold")
    assert (reversed_order.action, reversed_order.reason) == ("hold", "tied_vote_hold")
    assert first == reversed_order


def _prediction(*, model_id: str, action: str) -> ModelPrediction:
    decided_at = datetime(2026, 8, 19, 14, 30, tzinfo=UTC)
    return ModelPrediction(
        model_id=model_id,
        model_version="1",
        symbol="QQQ",
        market="US",
        signal=Signal(
            symbol="QQQ",
            market="US",
            action=action,  # type: ignore[arg-type]
            strength=Decimal("0.7"),
            reason="test_vote",
            timeframe=Timeframe.M5,
            generated_at=decided_at,
        ),
        confidence=Decimal("0.7"),
        expected_edge_bps=Decimal("2"),
        feature_window_end=decided_at,
    )
