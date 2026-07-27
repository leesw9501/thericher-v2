from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, EmergencyState, Timeframe
from thericher_v2.kis_daily_joint_event_d1_materializer import (
    KisDailyJointEventD1Materializer,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    build_kis_daily_joint_event_d1_target_cost_adapter,
)
from thericher_v2.kis_daily_joint_event_window_contract import (
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    KisDailyJointEventFoldInput,
    KisDailyJointEventWindowSpec,
)
from thericher_v2.research import kis_daily_cacc_d1 as cacc
from thericher_v2.research.validation import (
    InMemoryCampaignEventStore,
    ValidationConfig,
    run_local_paper_validation,
)

_TOTAL_SESSION_COUNT = 4756
_FOLD_GEOMETRY = {
    "expanding-1": (3783, 2345, 146),
    "expanding-2": (4057, 2511, 128),
    "expanding-3": (4331, 2671, 145),
}


def test_cacc_rule_requires_both_positive_top_range_bars() -> None:
    qqq, spy = _bar_pair(index=40)
    assert cacc.cacc_d1_should_buy(qqq_bar=qqq, spy_bar=spy)

    negative_qqq, _ = _bar_pair(index=41)
    assert not cacc.cacc_d1_should_buy(qqq_bar=negative_qqq, spy_bar=spy)


def test_cacc_is_deterministic_offline_local_paper_and_source_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    bindings = _bindings()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    first = cacc.run_kis_daily_cacc_d1(
        bindings=bindings,
        artifact_root=artifact_root,
        run_label="cpu-a",
        repo_root=repo_root,
    )
    second = cacc.run_kis_daily_cacc_d1(
        bindings=bindings,
        artifact_root=artifact_root,
        run_label="cpu-b",
        repo_root=repo_root,
    )

    assert first.precommit_hash == second.precommit_hash
    assert first.falsified is True
    assert [fold.fold_id for fold in first.fold_runs] == list(cacc.KIS_DAILY_CACC_D1_FOLD_IDS)
    assert [fold.kill_result.falsified for fold in first.fold_runs] == [True, True, True]
    assert [fold.candidate.after_cost_pnl for fold in first.fold_runs] == [
        fold.candidate.after_cost_pnl for fold in second.fold_runs
    ]
    assert all(
        replay.fill_source == "local_paper"
        and replay.all_fills_local_paper
        for fold in first.fold_runs
        for replay in (fold.candidate, fold.always_long, fold.flat)
    )
    assert all(
        fold.candidate.decision_count == fold.validation_eligible_decision_count
        and fold.always_long.decision_count == fold.validation_eligible_decision_count
        and fold.flat.decision_count == fold.validation_eligible_decision_count
        for fold in first.fold_runs
    )

    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    assert summary["mode"] == "offline_cpu_local_paper"
    assert summary["artifact_policy"] == {
        "account_data_persisted": False,
        "broker_network_accessed": False,
        "checkpoints_persisted": False,
        "credentials_accessed": False,
        "external_artifacts_only": True,
        "gpu_used": False,
        "kis_accessed": False,
        "labels_persisted": False,
        "local_paper_only": True,
        "network_accessed": False,
        "prices_persisted": False,
        "raw_market_data_persisted": False,
        "weights_persisted": False,
    }
    _assert_source_safe(summary)
    assert not list(artifact_root.rglob("*.jsonl"))
    assert not list(artifact_root.rglob("*.sqlite"))
    assert not list(artifact_root.rglob("*.pt"))
    assert not list(artifact_root.rglob("*.pkl"))
    assert not list(artifact_root.rglob("*.joblib"))
    assert first.precommit_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    assert not first.summary_path.is_relative_to(repo_root)


def test_cacc_rejects_repo_artifact_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        cacc.run_kis_daily_cacc_d1(
            bindings=_bindings(),
            artifact_root=repo_root / "model-artifacts",
            run_label="bad-root",
            repo_root=repo_root,
        )


def test_cacc_kill_rule_is_fold_local_and_strict() -> None:
    candidate = _metrics(trade_count=2, after_cost_pnl=Decimal("1.00"))
    baseline = _metrics(trade_count=4, after_cost_pnl=Decimal("0.50"))
    survives = cacc.evaluate_kis_daily_cacc_d1_kill_rule(
        candidate=candidate,
        always_long=baseline,
    )
    assert not survives.falsified

    zero_trade = cacc.evaluate_kis_daily_cacc_d1_kill_rule(
        candidate=_metrics(trade_count=0, after_cost_pnl=Decimal("2.00")),
        always_long=baseline,
    )
    nonpositive = cacc.evaluate_kis_daily_cacc_d1_kill_rule(
        candidate=_metrics(trade_count=1, after_cost_pnl=Decimal("0")),
        always_long=baseline,
    )
    not_better = cacc.evaluate_kis_daily_cacc_d1_kill_rule(
        candidate=_metrics(trade_count=1, after_cost_pnl=Decimal("0.50")),
        always_long=baseline,
    )
    assert zero_trade.zero_trades and zero_trade.falsified
    assert nonpositive.nonpositive_after_cost_pnl and nonpositive.falsified
    assert not_better.does_not_beat_always_long and not_better.falsified


def test_cacc_adjacent_signals_roll_over_exit_first_without_overlapping_position() -> None:
    binding = _bindings()[0]
    materializer = binding.materializer
    eligible = tuple(materializer.eligible_decision_indices("validation"))
    first_index = next(index for index in eligible if index + 1 in set(eligible))
    decision_indices = (first_index, first_index + 1)
    windows = tuple(
        materializer.materialize(phase="validation", decision_index=index)
        for index in decision_indices
    )
    campaign = cacc._build_campaign(materializer)
    event_store = InMemoryCampaignEventStore()
    result = run_local_paper_validation(
        cacc._cataloged_qqq_bars(materializer),
        event_store=event_store,
        emergency_store=cacc._InMemoryEmergencyStore(
            state=EmergencyState(
                stop_new_orders=False,
                cancel_open_orders_requested=False,
                reason="cacc_adjacent_rollover",
                updated_at=(
                    campaign.resolve_window("validation", fold_id="expanding-1")[1].start_utc
                ),
            )
        ),
        model=cacc._CaccD1ReplayDecisionAdapter(
            model_id="cacc_adjacent_rollover",
            action_by_feature_end={window.decision_end: "buy" for window in windows},
            reason="cacc_adjacent_rollover",
        ),
        config=ValidationConfig(
            run_id="cacc-adjacent-rollover",
            starting_cash=cacc.KIS_DAILY_CACC_D1_STARTING_CASH,
            quantity=cacc.KIS_DAILY_CACC_D1_QUANTITY,
            fee_bps=cacc.KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
            slippage_bps=cacc.KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
        ),
        campaign=campaign,
        phase="validation",
        fold_id="expanding-1",
        eligible_signal_starts=frozenset(window.decision_start for window in windows),
    )

    fills = tuple(event for event in event_store.iter_events() if event.event_type == "fill")
    assert [event.payload["side"] for event in fills] == ["buy", "sell", "buy", "sell"]
    assert fills[1].created_at == fills[2].created_at
    position = Decimal("0")
    max_position = Decimal("0")
    cash_delta = Decimal("0")
    for event in fills:
        quantity = Decimal(str(event.payload["quantity"]))
        price = Decimal(str(event.payload["price"]))
        fee = Decimal(str(event.payload["fee"]))
        if event.payload["side"] == "buy":
            position += quantity
            cash_delta -= price * quantity + fee
        else:
            position -= quantity
            cash_delta += price * quantity - fee
        max_position = max(max_position, position)

    assert position == Decimal("0")
    assert max_position == cacc.KIS_DAILY_CACC_D1_QUANTITY
    assert result.after_cost_pnl == cash_delta


def test_cacc_cli_help_stays_offline() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_kis_daily_cacc_d1.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr
    assert "--run-label" in result.stdout


def _bindings() -> tuple[cacc.KisDailyCaccD1FoldBinding, ...]:
    sessions = _sessions()
    qqq_bars = tuple(_bar_pair(index=index)[0] for index in range(_TOTAL_SESSION_COUNT))
    spy_bars = tuple(_bar_pair(index=index)[1] for index in range(_TOTAL_SESSION_COUNT))
    result: list[cacc.KisDailyCaccD1FoldBinding] = []
    for fold_id in cacc.KIS_DAILY_CACC_D1_FOLD_IDS:
        fold_input = _fold_input(sessions, fold_id=fold_id)
        materializer = KisDailyJointEventD1Materializer(
            fold_input=fold_input,
            fold_artifact_sha256=_sha256(f"fold-artifact:{fold_id}"),
            catalog_dataset_hash=fold_input.catalog_dataset_hash,
            catalog_index_hash=fold_input.catalog_index_hash,
            common_sessions=sessions,
            bars_by_symbol=MappingProxyType({"QQQ": qqq_bars, "SPY": spy_bars}),
        )
        result.append(
            cacc.KisDailyCaccD1FoldBinding(
                materializer=materializer,
                target_adapter=build_kis_daily_joint_event_d1_target_cost_adapter(
                    materializer=materializer,
                ),
            )
        )
    return tuple(result)


def _fold_input(
    sessions: tuple[date, ...],
    *,
    fold_id: str,
) -> KisDailyJointEventFoldInput:
    development_end, development_count, validation_count = _FOLD_GEOMETRY[fold_id]
    gap_end = development_end + 22
    validation_end = gap_end + 252
    development_indices = tuple(range(20, 20 + development_count))
    validation_indices = tuple(
        range(gap_end + 20, gap_end + 20 + validation_count)
    )
    return KisDailyJointEventFoldInput(
        source_artifact_sha256=_sha256(f"parent:{fold_id}"),
        source_contract_identity=_sha256(f"contract:{fold_id}"),
        catalog_dataset_hash=_sha256("catalog-dataset"),
        catalog_index_hash=_sha256("catalog-index"),
        sidecar_dataset_hash=_sha256("sidecar-dataset"),
        sidecar_manifest_hash=_sha256("sidecar-manifest"),
        event_boundary_audit_sha256=_sha256("audit"),
        event_boundary_mask_identity=_sha256("mask"),
        event_boundary_partition_identity=_sha256("partition"),
        joint_event_identity=_sha256("joint"),
        fold_id=fold_id,
        development_start_index=0,
        development_end_index=development_end,
        pre_validation_gap_start_index=development_end,
        pre_validation_gap_end_index=gap_end,
        validation_start_index=gap_end,
        validation_end_index=validation_end,
        development_start_session=sessions[0],
        development_end_session=sessions[development_end - 1],
        pre_validation_gap_start_session=sessions[development_end],
        pre_validation_gap_end_session=sessions[gap_end - 1],
        validation_start_session=sessions[gap_end],
        validation_end_session=sessions[validation_end - 1],
        development_eligible_decision_indices=development_indices,
        validation_eligible_decision_indices=validation_indices,
        development_eligible_decision_identity=_sha256(f"development:{fold_id}"),
        validation_eligible_decision_identity=_sha256(f"validation:{fold_id}"),
        spec=KisDailyJointEventWindowSpec(),
        model_execution_review=KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
        reattested_against_parent=True,
    )


@lru_cache(maxsize=1)
def _sessions() -> tuple[date, ...]:
    start = date(2018, 1, 1)
    return tuple(start + timedelta(days=index) for index in range(_TOTAL_SESSION_COUNT))


def _bar_pair(*, index: int) -> tuple[Bar, Bar]:
    session = _sessions()[index]
    timestamp = datetime(session.year, session.month, session.day, tzinfo=UTC)
    return (
        _bar(symbol="QQQ", timestamp=timestamp, base=Decimal("100"), index=index),
        _bar(symbol="SPY", timestamp=timestamp, base=Decimal("200"), index=index),
    )


def _bar(*, symbol: str, timestamp: datetime, base: Decimal, index: int) -> Bar:
    opening = base + Decimal(index) / Decimal("10")
    qualified = index % 2 == 0
    closing = opening + (Decimal("1") if qualified else Decimal("-1"))
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=timestamp,
        open=opening,
        high=max(opening, closing) + Decimal("0.1"),
        low=min(opening, closing) - Decimal("1"),
        close=closing,
        volume=Decimal("1000"),
        complete=True,
    )


def _metrics(*, trade_count: int, after_cost_pnl: Decimal) -> cacc.KisDailyCaccD1ReplayMetrics:
    return cacc.KisDailyCaccD1ReplayMetrics(
        decision_count=5,
        trade_count=trade_count,
        local_paper_fill_count=trade_count * 2,
        after_cost_pnl=after_cost_pnl,
        fill_source="local_paper",
        all_fills_local_paper=True,
    )


def _assert_source_safe(value: object) -> None:
    forbidden = {
        "account",
        "cash",
        "close",
        "equity",
        "high",
        "label",
        "low",
        "open",
        "order",
        "position",
        "price",
        "raw_row",
        "raw_rows",
        "weight",
        "weights",
    }
    if isinstance(value, dict):
        assert not forbidden.intersection(value)
        for nested in value.values():
            _assert_source_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_source_safe(nested)


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("CACC-D1 must not access network or a broker endpoint")

    original_getenv = os.getenv

    def deny_secret_environment(name: str, default: str | None = None) -> str | None:
        if name.startswith(("KIS_", "TIINGO_", "THERICHER_DASHBOARD_")):
            raise AssertionError("CACC-D1 must not read credentials")
        return original_getenv(name, default)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", deny_secret_environment)


def _sha256(value: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
