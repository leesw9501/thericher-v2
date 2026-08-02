from __future__ import annotations

import ast
import inspect
import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE, LocalPaperBroker
from thericher_v2.execution.paper_decision_bridge import LocalPaperTargetBinding
from thericher_v2.models.momentum import MomentumModel
from thericher_v2.models.sequence_window import (
    SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
    SequenceWindowInputError,
)
from thericher_v2.models.target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
)
from thericher_v2.research import injected_multitimeframe_local_paper_replay as replay_module
from thericher_v2.research.decision_receipt import DecisionReceiptReferences
from thericher_v2.state import EventStore

_CUTOFF = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
_LOOKBACKS = {timeframe: 4 for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES}


def test_injected_replay_traverses_existing_paths_and_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    calls: list[str] = []
    _wrap_existing_path(monkeypatch, "build_causal_multitimeframe_sequence_window", calls)
    _wrap_existing_path(monkeypatch, "propose_target_exposure", calls)
    _wrap_existing_path(monkeypatch, "prepare_local_paper_intent", calls)
    _wrap_existing_path(monkeypatch, "run_next_bar_backtest", calls)

    first, first_store = _run(tmp_path / "first")
    second, second_store = _run(tmp_path / "second")

    assert calls == [
        "build_causal_multitimeframe_sequence_window",
        "propose_target_exposure",
        "prepare_local_paper_intent",
        "run_next_bar_backtest",
        "build_causal_multitimeframe_sequence_window",
        "propose_target_exposure",
        "prepare_local_paper_intent",
        "run_next_bar_backtest",
    ]
    assert first.safe_payload() == second.safe_payload()
    assert first.status == "filled"
    assert first.reason == "eligible"
    assert first.timeframe_bar_counts == _LOOKBACKS
    assert first.prediction_count == len(SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES)
    assert first.all_windows_available_at_cutoff
    assert first.proposal_action == "enter"
    assert first.proposal_input_status == "ready"
    assert first.decision_identity_matches
    assert first.local_paper_fill_source == LOCAL_PAPER_SOURCE
    assert first.local_paper_replay_matches
    assert first.fill_is_next_bar
    assert first.backtest_trade_count > 0
    assert first.backtest_next_bar_timing_valid
    assert _fill_sources(first_store) == [LOCAL_PAPER_SOURCE]
    assert _fill_sources(second_store) == [LOCAL_PAPER_SOURCE]

    serialized = json.dumps(first.safe_payload(), sort_keys=True)
    for forbidden in (
        "open\"",
        "close\"",
        "volume\"",
        "price\"",
        "2026-08-03",
        "c:\\\\",
        "path\"",
    ):
        assert forbidden not in serialized


def test_stale_opportunity_produces_no_intent_without_local_paper_event(tmp_path: Path) -> None:
    result, store = _run(
        tmp_path,
        opportunity=_opportunity(
            observed_at=_CUTOFF - timedelta(minutes=2),
            valid_until=_CUTOFF - timedelta(minutes=1),
        ),
    )

    assert result.status == "no_intent"
    assert result.proposal_action == "abstain"
    assert result.proposal_input_status == "stale"
    assert not result.decision_identity_matches
    assert result.local_paper_fill_source is None
    assert not tuple(store.iter_events())


def test_same_store_retry_recovers_the_original_fill_without_a_rejection(tmp_path: Path) -> None:
    first, store = _run(tmp_path)
    event_count = len(tuple(store.iter_events()))

    second, retried_store = _run(tmp_path)

    assert first.safe_payload() == second.safe_payload()
    events = tuple(retried_store.iter_events())
    assert len(events) == event_count
    assert not [event for event in events if event.event_type == "local_paper_order_rejected"]
    assert _fill_sources(retried_store) == [LOCAL_PAPER_SOURCE]


def test_short_backtest_input_fails_before_any_local_paper_event(tmp_path: Path) -> None:
    bars_by_timeframe, execution_bar = _bars()
    short_m1 = bars_by_timeframe[Timeframe.M1][-4:]
    shortened = {**bars_by_timeframe, Timeframe.M1: short_m1}
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")

    with pytest.raises(ValueError, match="at least 6 bars"):
        replay_module.run_injected_multitimeframe_local_paper_replay(
            shortened,
            lookbacks=_LOOKBACKS,
            cutoff=_CUTOFF,
            momentum_model=_momentum_model(),
            opportunity=_opportunity(),
            policy_config=_policy_config(),
            current_exposure=Decimal("0"),
            receipt_references=_references(),
            local_binding=_local_binding(),
            local_paper_broker=_broker(store, tmp_path),
            execution_bar=execution_bar,
            backtest_bars=(*short_m1, execution_bar),
        )

    assert not tuple(store.iter_events())


@pytest.mark.parametrize("mutation", ["incomplete", "future"])
def test_invalid_injected_windows_never_mint_an_intent(
    tmp_path: Path,
    mutation: str,
) -> None:
    bars_by_timeframe, execution_bar = _bars()
    altered = dict(bars_by_timeframe)
    latest = altered[Timeframe.M1][-1]
    if mutation == "incomplete":
        altered[Timeframe.M1] = (*altered[Timeframe.M1][:-1], replace(latest, complete=False))
    else:
        altered[Timeframe.M1] = (*altered[Timeframe.M1][:-1], replace(latest, start_ts=_CUTOFF))
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = _broker(store, tmp_path)

    with pytest.raises(SequenceWindowInputError, match=mutation):
        replay_module.run_injected_multitimeframe_local_paper_replay(
            altered,
            lookbacks=_LOOKBACKS,
            cutoff=_CUTOFF,
            momentum_model=_momentum_model(),
            opportunity=_opportunity(),
            policy_config=_policy_config(),
            current_exposure=Decimal("0"),
            receipt_references=_references(),
            local_binding=_local_binding(),
            local_paper_broker=broker,
            execution_bar=execution_bar,
            backtest_bars=(*altered[Timeframe.M1], execution_bar),
        )

    assert not tuple(store.iter_events())


def test_module_has_no_provider_or_credential_surface() -> None:
    source = inspect.getsource(replay_module).lower()
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imported_modules <= {
        "__future__",
        "collections.abc",
        "dataclasses",
        "datetime",
        "decimal",
        "types",
        "typing",
        "thericher_v2.backtest.simple",
        "thericher_v2.contracts",
        "thericher_v2.execution.local_paper",
        "thericher_v2.execution.paper_decision_bridge",
        "thericher_v2.models.momentum",
        "thericher_v2.models.sequence_window",
        "thericher_v2.models.target_position_policy",
        "thericher_v2.research.decision_receipt",
    }
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import)]
    for forbidden in (
        "norgate",
        "tiingo",
        "kis",
        "socket",
        "urllib",
        "dotenv",
        ".env",
        "getenv",
        "environ",
        "open(",
        "read_text",
        "read_bytes",
    ):
        assert forbidden not in source


def _run(
    root: Path,
    *,
    opportunity: OpportunityEligibility | None = None,
) -> tuple[replay_module.InjectedMultitimeframeLocalPaperReplayResult, EventStore]:
    bars_by_timeframe, execution_bar = _bars()
    store = EventStore(root / "state.sqlite", root / "events.jsonl")
    result = replay_module.run_injected_multitimeframe_local_paper_replay(
        bars_by_timeframe,
        lookbacks=_LOOKBACKS,
        cutoff=_CUTOFF,
        momentum_model=_momentum_model(),
        opportunity=opportunity or _opportunity(),
        policy_config=_policy_config(),
        current_exposure=Decimal("0"),
        receipt_references=_references(),
        local_binding=_local_binding(),
        local_paper_broker=_broker(store, root),
        execution_bar=execution_bar,
        backtest_bars=(*bars_by_timeframe[Timeframe.M1], execution_bar),
    )
    return result, store


def _bars() -> tuple[dict[Timeframe, tuple[Bar, ...]], Bar]:
    bars_by_timeframe: dict[Timeframe, tuple[Bar, ...]] = {}
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        count = 8 if timeframe is Timeframe.M1 else _LOOKBACKS[timeframe]
        start = _CUTOFF - timeframe.duration * count
        bars_by_timeframe[timeframe] = tuple(
            _bar(timeframe=timeframe, start_ts=start + timeframe.duration * index, index=index)
            for index in range(count)
        )
    execution = _bar(timeframe=Timeframe.M1, start_ts=_CUTOFF, index=8)
    return bars_by_timeframe, execution


def _bar(*, timeframe: Timeframe, start_ts: datetime, index: int) -> Bar:
    opened = Decimal("100") + Decimal(index)
    closed = opened + Decimal("0.50")
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=timeframe,
        start_ts=start_ts,
        open=opened,
        high=closed + Decimal("0.25"),
        low=opened - Decimal("0.25"),
        close=closed,
        volume=Decimal("1000") + Decimal(index),
        complete=True,
    )


def _momentum_model() -> MomentumModel:
    return MomentumModel(
        model_id="injected-momentum-v1",
        lookback=3,
        buy_threshold_bps=Decimal("1"),
        sell_threshold_bps=Decimal("-1"),
    )


def _policy_config() -> TargetPositionPolicyConfig:
    return TargetPositionPolicyConfig(
        policy_id="injected-multitimeframe-local-paper-replay-seam-v1",
        feature_schema_id="injected-completed-bar-momentum-v1",
        required_timeframes=SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
        maximum_evidence_age={
            timeframe: timeframe.duration for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
        },
        minimum_confidence=Decimal("0.01"),
        minimum_absolute_edge_bps=Decimal("0.01"),
        entry_target_exposure=Decimal("0.50"),
        decision_ttl=timedelta(minutes=1),
    )


def _opportunity(
    *,
    observed_at: datetime = _CUTOFF,
    valid_until: datetime = _CUTOFF + timedelta(minutes=1),
) -> OpportunityEligibility:
    return OpportunityEligibility(
        opportunity_ref="ref:" + "a" * 64,
        symbol="QQQ",
        market="US",
        eligible=True,
        input_status="ready",
        observed_at=observed_at,
        valid_until=valid_until,
    )


def _references() -> DecisionReceiptReferences:
    return DecisionReceiptReferences(
        campaign_ref="ref:" + "b" * 64,
        model_ref="ref:" + "c" * 64,
        input_manifest_ref="sha256:" + "d" * 64,
        proposal_ref="ref:" + "e" * 64,
    )


def _local_binding() -> LocalPaperTargetBinding:
    return LocalPaperTargetBinding(
        proposal_ref="ref:" + "e" * 64,
        symbol="QQQ",
        target_exposure=Decimal("0.50"),
        current_quantity=Decimal("0"),
        maximum_quantity=Decimal("10"),
    )


def _broker(store: EventStore, root: Path) -> LocalPaperBroker:
    return LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(root / "emergency.json"),
    )


def _fill_sources(store: EventStore) -> list[str]:
    return [
        str(event.payload["source"])
        for event in store.iter_events()
        if event.event_type == "fill"
    ]


def _wrap_existing_path(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    calls: list[str],
) -> None:
    original = getattr(replay_module, name)

    def wrapped(*args: object, **kwargs: object) -> object:
        calls.append(name)
        return original(*args, **kwargs)

    monkeypatch.setattr(replay_module, name, wrapped)


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("injected replay must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
