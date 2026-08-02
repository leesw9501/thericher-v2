from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, ModelPrediction, Signal, Timeframe
from thericher_v2.models.sequence_window import (
    CausalMultiTimeframeSequenceWindow,
    CausalSequenceWindow,
    build_causal_multitimeframe_sequence_window,
)
from thericher_v2.models.target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
    propose_target_exposure,
)

_NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
_TIMEFRAMES = (Timeframe.M1, Timeframe.M5, Timeframe.M10, Timeframe.H1, Timeframe.H3)


def test_window_bound_policy_accepts_exact_completed_bar_ends() -> None:
    window = _causal_window()

    proposal = propose_target_exposure(
        _eligibility(),
        _predictions(window),
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
        causal_window=window,
    )

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "enter",
        "ready",
        "unanimous_entry",
    )


def test_window_bound_policy_rejects_a_forged_slow_prediction_end() -> None:
    window = _causal_window()
    predictions = list(_predictions(window))
    h1_index = _TIMEFRAMES.index(Timeframe.H1)
    predictions[h1_index] = replace(predictions[h1_index], feature_window_end=_NOW)

    proposal = propose_target_exposure(
        _eligibility(),
        predictions,
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
        causal_window=window,
    )

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "abstain",
        "misaligned",
        "evidence_misaligned",
    )


def test_window_bound_policy_revalidates_a_future_bar() -> None:
    window = _causal_window()
    m1 = window.windows[Timeframe.M1]
    future_bar = replace(m1.bars[-1], start_ts=_NOW)
    future_window = CausalMultiTimeframeSequenceWindow(
        symbol=window.symbol,
        market=window.market,
        cutoff=window.cutoff,
        windows={
            **window.windows,
            Timeframe.M1: CausalSequenceWindow(
                timeframe=Timeframe.M1,
                bars=(*m1.bars[:-1], future_bar),
                cutoff=window.cutoff,
            ),
        },
    )

    proposal = propose_target_exposure(
        _eligibility(),
        _predictions(window),
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
        causal_window=future_window,
    )

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "abstain",
        "future",
        "evidence_future",
    )


def test_window_bound_policy_rejects_foreign_bars_under_a_matching_header() -> None:
    window = _causal_window()
    foreign_window = CausalMultiTimeframeSequenceWindow(
        symbol=window.symbol,
        market=window.market,
        cutoff=window.cutoff,
        windows={
            timeframe: CausalSequenceWindow(
                timeframe=timeframe,
                bars=tuple(replace(bar, symbol="SPY") for bar in item.bars),
                cutoff=item.cutoff,
            )
            for timeframe, item in window.windows.items()
        },
    )

    proposal = propose_target_exposure(
        _eligibility(),
        _predictions(window),
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
        causal_window=foreign_window,
    )

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "abstain",
        "misaligned",
        "evidence_misaligned",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", "SPY"),
        ("market", "NYSE"),
        ("cutoff", _NOW - timedelta(minutes=1)),
    ],
)
def test_window_bound_policy_rejects_a_misaligned_window_identity(
    field: str,
    value: str | datetime,
) -> None:
    window = _causal_window()
    mismatched_window = replace(window, **{field: value})

    proposal = propose_target_exposure(
        _eligibility(),
        _predictions(window),
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
        causal_window=mismatched_window,
    )

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "abstain",
        "misaligned",
        "evidence_misaligned",
    )


def _causal_window() -> CausalMultiTimeframeSequenceWindow:
    end_offsets = {
        Timeframe.M1: timedelta(),
        Timeframe.M5: timedelta(),
        Timeframe.M10: timedelta(),
        Timeframe.H1: timedelta(minutes=55),
        Timeframe.H3: timedelta(hours=2, minutes=30),
    }
    return build_causal_multitimeframe_sequence_window(
        {
            timeframe: _bars(timeframe, end_ts=_NOW - end_offsets[timeframe])
            for timeframe in _TIMEFRAMES
        },
        lookbacks={timeframe: 2 for timeframe in _TIMEFRAMES},
        cutoff=_NOW,
    )


def _bars(timeframe: Timeframe, *, end_ts: datetime) -> tuple[Bar, ...]:
    first_start = end_ts - timeframe.duration * 2
    return tuple(
        Bar(
            symbol="QQQ",
            market="US",
            timeframe=timeframe,
            start_ts=first_start + timeframe.duration * index,
            open=Decimal("100") + Decimal(index),
            high=Decimal("101") + Decimal(index),
            low=Decimal("99") + Decimal(index),
            close=Decimal("100.5") + Decimal(index),
            volume=Decimal("1000") + Decimal(index),
            complete=True,
        )
        for index in range(2)
    )


def _predictions(window: CausalMultiTimeframeSequenceWindow) -> tuple[ModelPrediction, ...]:
    return tuple(
        ModelPrediction(
            model_id=f"expert-{timeframe.value}",
            model_version="test-v1",
            symbol="QQQ",
            market="US",
            signal=Signal(
                symbol="QQQ",
                market="US",
                action="buy",
                strength=Decimal("0.80"),
                reason="window_bound_test",
                timeframe=timeframe,
                generated_at=_NOW,
            ),
            confidence=Decimal("0.80"),
            expected_edge_bps=Decimal("4"),
            feature_window_end=window.windows[timeframe].end_ts,
        )
        for timeframe in _TIMEFRAMES
    )


def _eligibility() -> OpportunityEligibility:
    return OpportunityEligibility(
        opportunity_ref="ref:" + "1" * 64,
        symbol="QQQ",
        market="US",
        eligible=True,
        input_status="ready",
        observed_at=_NOW - timedelta(minutes=1),
        valid_until=_NOW + timedelta(minutes=3),
    )


def _config() -> TargetPositionPolicyConfig:
    return TargetPositionPolicyConfig(
        policy_id="causal-window-binding-test-v1",
        feature_schema_id="causal-window-binding-features-v1",
        required_timeframes=_TIMEFRAMES,
        maximum_evidence_age={
            Timeframe.M1: timedelta(minutes=2),
            Timeframe.M5: timedelta(minutes=10),
            Timeframe.M10: timedelta(minutes=20),
            Timeframe.H1: timedelta(hours=1),
            Timeframe.H3: timedelta(hours=3),
        },
        minimum_confidence=Decimal("0.60"),
        minimum_absolute_edge_bps=Decimal("2"),
        entry_target_exposure=Decimal("0.20"),
        decision_ttl=timedelta(minutes=2),
    )
