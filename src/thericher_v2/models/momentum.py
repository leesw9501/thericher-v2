"""A tiny deterministic momentum model used to prove the v2 harness."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from thericher_v2.contracts import Bar, ModelPrediction, Signal, Timeframe


@dataclass(frozen=True)
class MomentumModel:
    model_id: str = "momentum_close_v1"
    model_version: str = "0.1.0"
    lookback: int = 3
    buy_threshold_bps: Decimal = Decimal("5")
    sell_threshold_bps: Decimal = Decimal("-5")

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) <= self.lookback:
            raise ValueError("not enough bars for momentum prediction")
        latest = bars[-1]
        prior = bars[-1 - self.lookback]
        if latest.timeframe != prior.timeframe:
            raise ValueError("mixed timeframe window")
        change_bps = ((latest.close / prior.close) - Decimal("1")) * Decimal("10000")
        if change_bps >= self.buy_threshold_bps:
            action = "buy"
            reason = "positive_momentum"
        elif change_bps <= self.sell_threshold_bps:
            action = "sell"
            reason = "negative_momentum"
        else:
            action = "hold"
            reason = "momentum_inside_threshold"

        confidence = min(Decimal("1"), abs(change_bps) / Decimal("100"))
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason=reason,
            timeframe=Timeframe(latest.timeframe),
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=self.model_id,
            model_version=self.model_version,
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=confidence,
            expected_edge_bps=change_bps / Decimal("2"),
            feature_window_end=latest.end_ts,
            metadata={
                "lookback": self.lookback,
                "change_bps": str(change_bps.quantize(Decimal("0.0001"))),
            },
        )
