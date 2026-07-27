from __future__ import annotations

import hashlib
import json
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, EmergencyState, Timeframe
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import etf_d1_trend_regime as trend
from thericher_v2.research.validation import (
    InMemoryCampaignEventStore,
    ValidationConfig,
    run_local_paper_validation,
)


def test_fixed_control_is_deterministic_offline_and_local_paper_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    sources = _sources()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    first = trend.run_etf_d1_trend_regime_control(
        eligibility_receipt_sha256=_sha256("eligibility"),
        sources=sources,
        run_label="offline-a",
        artifact_root=artifact_root,
        repository_root=repo_root,
        require_approved_artifact_root=False,
    )
    second = trend.run_etf_d1_trend_regime_control(
        eligibility_receipt_sha256=_sha256("eligibility"),
        sources=sources,
        run_label="offline-b",
        artifact_root=artifact_root,
        repository_root=repo_root,
        require_approved_artifact_root=False,
    )

    assert first.precommit_hash == second.precommit_hash
    assert first.falsified is True
    assert [run.instrument_id for run in first.symbol_runs] == [
        "QQQ/NAS",
        "SPY/AMS",
        "IWM/AMS",
    ]
    for symbol_run in first.symbol_runs:
        if symbol_run.instrument_id == "IWM/AMS":
            assert "source_limited_history_scope" in symbol_run.limitations
        for phase in (symbol_run.development, symbol_run.validation):
            assert phase.candidate.decision_slot_count == phase.always_long.decision_slot_count
            assert phase.candidate.all_fills_local_paper is True
            assert phase.always_long.all_fills_local_paper is True
            assert phase.candidate.fill_source == "local_paper"
            assert phase.always_long.fill_source == "local_paper"
            assert phase.candidate.final_position == Decimal("0")
            assert phase.always_long.final_position == Decimal("0")

    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    assert summary["mode"] == "offline_cpu_local_paper"
    assert summary["falsified"] is True
    assert summary["artifact_policy"] == {
        "account_data_persisted": False,
        "broker_network_accessed": False,
        "checkpoints_persisted": False,
        "credentials_accessed": False,
        "external_artifacts_only": True,
        "feature_values_persisted": False,
        "gpu_used": False,
        "kis_accessed": False,
        "local_paper_only": True,
        "network_accessed": False,
        "order_data_persisted": False,
        "prices_persisted": False,
        "raw_market_data_persisted": False,
        "weights_persisted": False,
    }
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8") for path in artifact_root.rglob("*.json")
    )
    assert "private-source-path" not in artifact_text
    assert "109.999" not in artifact_text
    assert not list(artifact_root.rglob("*.jsonl"))
    assert not list(artifact_root.rglob("*.sqlite"))
    assert not list(artifact_root.rglob("*.pt"))
    assert not list(artifact_root.rglob("*.pkl"))
    assert not list(artifact_root.rglob("*.joblib"))
    assert first.precommit_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    assert not first.summary_path.is_relative_to(repo_root)


def test_qualifying_slot_fills_at_next_two_opens_with_local_paper_source() -> None:
    source = _sources()[0]
    bars = source.cataloged_bars.bars
    index = trend._decision_indices(bars)[0]
    actions, qualified_count = trend._candidate_actions(
        bars=bars,
        decision_indices=(index,),
    )
    event_store = InMemoryCampaignEventStore()

    result = run_local_paper_validation(
        source.cataloged_bars,
        event_store=event_store,
        emergency_store=trend._InMemoryEmergencyStore(
            state=EmergencyState(
                stop_new_orders=False,
                cancel_open_orders_requested=False,
                reason="trend-regime-fill-timing-test",
                updated_at=bars[0].start_ts,
            )
        ),
        model=trend._TrendRegimeReplayModel(
            model_id="trend-regime-fill-timing-test",
            action_by_feature_end=actions,
            reason="fixed_d1_trend_regime",
        ),
        config=ValidationConfig(run_id="trend-regime-fill-timing-test"),
        eligible_signal_starts=trend._eligible_signal_starts(
            bars=bars,
            decision_indices=(index,),
        ),
    )

    fills = tuple(event for event in event_store.iter_events() if event.event_type == "fill")
    assert qualified_count == 1
    assert result.decisions_seen == 2
    assert result.final_position == Decimal("0")
    assert [event.payload["source"] for event in fills] == ["local_paper", "local_paper"]
    assert [event.payload["side"] for event in fills] == ["buy", "sell"]
    assert [event.created_at for event in fills] == [
        bars[index + 1].start_ts,
        bars[index + 2].start_ts,
    ]


def test_rule_actions_are_causal_non_overlapping_and_split_chronologically() -> None:
    source = _sources()[0]
    bars = source.cataloged_bars.bars
    decision_indices = trend._decision_indices(bars)
    development, validation = trend._split_decision_indices(decision_indices)
    actions, qualified_count = trend._candidate_actions(
        bars=bars,
        decision_indices=decision_indices,
    )
    eligible_starts = trend._eligible_signal_starts(
        bars=bars,
        decision_indices=decision_indices,
    )

    first = decision_indices[0]
    assert trend.etf_d1_trend_regime_should_enter(completed_bars=bars[: first + 1]) is True
    assert actions[bars[first].end_ts] == "buy"
    assert actions[bars[first + 1].end_ts] == "sell"
    assert qualified_count == len(decision_indices)
    assert development[-1] + 2 == validation[0]
    assert len(eligible_starts) == len(decision_indices) * 2
    assert all(
        later - earlier == 2
        for earlier, later in zip(decision_indices, decision_indices[1:], strict=False)
    )


def test_control_rejects_artifacts_inside_repository(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        trend.run_etf_d1_trend_regime_control(
            eligibility_receipt_sha256=_sha256("eligibility"),
            sources=_sources(),
            run_label="bad-root",
            artifact_root=repo_root / "model-artifacts",
            repository_root=repo_root,
            require_approved_artifact_root=False,
        )


def _sources() -> tuple[trend.EtfD1TrendRegimeSource, ...]:
    return (
        _source("QQQ", "NAS", Decimal("100.000"), Decimal("0.200")),
        _source("SPY", "AMS", Decimal("200.000"), Decimal("0.100")),
        _source("IWM", "AMS", Decimal("109.999"), Decimal("0.050")),
    )


def _source(
    symbol: str,
    market: str,
    start_close: Decimal,
    daily_change: Decimal,
) -> trend.EtfD1TrendRegimeSource:
    bars = tuple(
        _bar(
            symbol=symbol,
            market=market,
            index=index,
            close=start_close + daily_change * Decimal(index),
        )
        for index in range(80)
    )
    cataloged_bars = _cataloged_bars_from_verified_loader(
        dataset_id=f"fixture.{symbol.lower()}.d1",
        dataset_hash=_sha256(f"dataset:{symbol}"),
        source_path=Path(f"private-source-path-{symbol}.csv"),
        bars=bars,
    )
    return trend.EtfD1TrendRegimeSource(
        instrument_id=f"{symbol}/{market}",
        source_snapshot_sha256=_sha256(f"snapshot:{symbol}"),
        limitations=("fixture-source-local",)
        if symbol != "IWM"
        else ("fixture-source-local", "source_limited_history_scope"),
        cataloged_bars=cataloged_bars,
    )


def _bar(*, symbol: str, market: str, index: int, close: Decimal) -> Bar:
    start_ts = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index)
    return Bar(
        symbol=symbol,
        market=market,
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=close - Decimal("0.010"),
        high=close + Decimal("0.010"),
        low=close - Decimal("0.020"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("the fixed ETF D1 control must stay offline")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(trend, "load_kis_paper_private_daily_catalog", forbidden)


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()
