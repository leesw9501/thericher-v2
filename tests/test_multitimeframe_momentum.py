from __future__ import annotations

import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import SessionWindow
from thericher_v2.models.multitimeframe_momentum import (
    MultiTimeframeMomentumConfig,
    MultiTimeframeMomentumSpec,
    build_multitimeframe_momentum_evidence,
)
from thericher_v2.models.target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
    propose_target_exposure,
)

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_TIMEFRAMES = (Timeframe.M1, Timeframe.M5, Timeframe.M10, Timeframe.H1, Timeframe.H3)


def test_completed_session_builds_all_five_causal_momentum_experts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    evidence = build_multitimeframe_momentum_evidence(
        _bars(),
        session=_SESSION,
        config=_config(),
        as_of=_SESSION.close_ts,
    )

    assert evidence.input_status == "ready"
    assert evidence.reason == "completed_bar_momentum_evidence"
    assert tuple(prediction.signal.timeframe for prediction in evidence.predictions) == _TIMEFRAMES
    assert all(prediction.signal.action == "buy" for prediction in evidence.predictions)
    assert evidence.feature_window_end == _SESSION.close_ts


def test_future_source_bars_do_not_change_an_earlier_as_of_evidence_window() -> None:
    as_of = _SESSION.open_ts + timedelta(hours=6)
    original = build_multitimeframe_momentum_evidence(
        _bars(),
        session=_SESSION,
        config=_config(),
        as_of=as_of,
    )
    changed = build_multitimeframe_momentum_evidence(
        _bars(future_price_shift=Decimal("1000")),
        session=_SESSION,
        config=_config(),
        as_of=as_of,
    )

    assert original == changed
    assert original.input_status == "ready"


def test_missing_terminal_source_bar_fails_closed_as_incomplete() -> None:
    bars = _bars()[:-1]

    evidence = build_multitimeframe_momentum_evidence(
        bars,
        session=_SESSION,
        config=_config(),
        as_of=_SESSION.close_ts,
    )

    assert (evidence.input_status, evidence.reason, evidence.predictions) == (
        "incomplete",
        "incomplete_1m",
        (),
    )


def test_generated_evidence_flows_to_the_target_policy_without_any_order_path() -> None:
    evidence = build_multitimeframe_momentum_evidence(
        _bars(),
        session=_SESSION,
        config=_config(),
        as_of=_SESSION.close_ts,
    )
    eligibility = OpportunityEligibility(
        opportunity_ref="ref:" + "1" * 64,
        symbol="QQQ",
        market="US",
        eligible=True,
        input_status=evidence.input_status,
        observed_at=_SESSION.close_ts,
        valid_until=_SESSION.close_ts + timedelta(minutes=2),
    )
    proposal = propose_target_exposure(
        eligibility,
        evidence.predictions,
        current_exposure=Decimal("0"),
        config=TargetPositionPolicyConfig(
            policy_id="multitimeframe-momentum-policy-test-v1",
            feature_schema_id="multitimeframe-momentum-features-v1",
            required_timeframes=_TIMEFRAMES,
            maximum_evidence_age={
                Timeframe.M1: timedelta(minutes=2),
                Timeframe.M5: timedelta(minutes=10),
                Timeframe.M10: timedelta(minutes=20),
                Timeframe.H1: timedelta(hours=1),
                Timeframe.H3: timedelta(hours=3),
            },
            minimum_confidence=Decimal("0.01"),
            minimum_absolute_edge_bps=Decimal("0.01"),
            entry_target_exposure=Decimal("0.20"),
            decision_ttl=timedelta(minutes=2),
        ),
        as_of=_SESSION.close_ts,
    )

    assert (proposal.action, proposal.input_status, proposal.reason) == (
        "enter",
        "ready",
        "unanimous_entry",
    )


def _config() -> MultiTimeframeMomentumConfig:
    return MultiTimeframeMomentumConfig(
        feature_schema_id="multitimeframe-momentum-features-v1",
        experts=(
            MultiTimeframeMomentumSpec(Timeframe.M1, 5, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.M5, 4, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.M10, 3, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.H1, 3, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.H3, 1, Decimal("1"), Decimal("-1")),
        ),
    )


def _bars(*, future_price_shift: Decimal = Decimal("0")) -> tuple[Bar, ...]:
    bars: list[Bar] = []
    cutoff = _SESSION.open_ts + timedelta(hours=6)
    for index in range(390):
        start = _SESSION.open_ts + timedelta(minutes=index)
        shift = future_price_shift if start >= cutoff else Decimal("0")
        opened = Decimal("100") + Decimal(index) / Decimal("100") + shift
        closed = opened + Decimal("0.02")
        bars.append(
            Bar(
                symbol="QQQ",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=start,
                open=opened,
                high=closed + Decimal("0.01"),
                low=opened - Decimal("0.01"),
                close=closed,
                volume=Decimal("1000") + Decimal(index),
                complete=True,
            )
        )
    return tuple(bars)


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("multitimeframe momentum evidence must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
