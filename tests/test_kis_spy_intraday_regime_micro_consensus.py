from __future__ import annotations

import json
import os
import socket
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib import request

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import kis_spy_intraday_regime_micro_consensus as consensus

_SESSION_DATES = (
    date(2026, 6, 22),
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
    date(2026, 7, 16),
    date(2026, 7, 17),
    date(2026, 7, 20),
    date(2026, 7, 21),
)
_SCHEDULED_DECISIONS_PER_SESSION = 19


def test_preparation_freezes_10_1_10_geometry_and_complete_causal_multitimeframe_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    prepared = consensus.prepare_kis_spy_intraday_regime_micro_consensus(
        _catalog(profile="all_bullish"),
    )

    assert prepared.status == "ready"
    assert prepared.complete_regular_session_count == len(_SESSION_DATES)
    assert prepared.development.session_count == 10
    assert prepared.validation.session_count == 10
    assert prepared.development.scheduled_decision_count == 10 * _SCHEDULED_DECISIONS_PER_SESSION
    assert prepared.validation.scheduled_decision_count == 10 * _SCHEDULED_DECISIONS_PER_SESSION
    assert prepared.validation.structural_unavailable_count == 0
    assert prepared.validation.macro_rejected_count == 0
    assert prepared.validation.micro_rejected_count == 0
    assert prepared.validation.active_decision_count == 10 * _SCHEDULED_DECISIONS_PER_SESSION

    contract = prepared.safe_payload()["contract"]
    assert contract["split"] == {
        "development_sessions": 10,
        "purge_sessions": 1,
        "validation_sessions": 10,
        "development_target_access": "prohibited",
    }
    assert contract["decision_schedule"] == {
        "timezone": "America/New_York",
        "first_offset_minutes": 180,
        "last_offset_minutes": 360,
        "step_minutes": 10,
    }
    assert contract["feature_windows"] == {
        "m1_completed_bars": 31,
        "m1_close_to_close_lookback_minutes": 30,
        "m5_latest_completed_bar": True,
        "m10_latest_completed_bar": True,
        "h1_latest_completed_bar": True,
        "h3_latest_completed_bar": True,
    }
    assert contract["target"] == "decision_t_next_m1_open_to_t_plus_10m_m1_open"
    assert contract["target_non_overlapping"] is True

    incomplete = consensus.prepare_kis_spy_intraday_regime_micro_consensus(
        _catalog(profile="all_bullish", missing=(11, 179)),
    )
    assert incomplete.status == "input_unavailable"
    assert incomplete.reason == "insufficient_complete_regular_sessions"
    assert incomplete.complete_regular_session_count == len(_SESSION_DATES) - 1


def test_macro_gate_and_micro_rule_are_both_required_with_a_31_m1_floor() -> None:
    macro_only = consensus.prepare_kis_spy_intraday_regime_micro_consensus(
        _catalog(profile="macro_only"),
    )
    micro_without_macro = consensus.prepare_kis_spy_intraday_regime_micro_consensus(
        _catalog(profile="micro_without_macro"),
    )

    assert macro_only.status == "input_unavailable"
    assert macro_only.reason == "insufficient_validation_active_decisions"
    assert macro_only.validation.macro_rejected_count == 0
    assert macro_only.validation.micro_rejected_count == 10 * _SCHEDULED_DECISIONS_PER_SESSION
    assert macro_only.validation.active_decision_count == 0

    assert micro_without_macro.status == "input_unavailable"
    assert micro_without_macro.reason == "insufficient_validation_active_decisions"
    assert micro_without_macro.validation.macro_rejected_count == (
        10 * _SCHEDULED_DECISIONS_PER_SESSION
    )
    assert micro_without_macro.validation.active_decision_count == 0

    session = us_equity_2026_session(_SESSION_DATES[11])
    assert session is not None
    source_bars = tuple(
        bar
        for bar in _catalog(profile="macro_only").bars
        if session.window.open_ts <= bar.start_ts and bar.end_ts <= session.window.close_ts
    )[:180]
    assert consensus._decision_state(
        source_bars=source_bars,
        session=session.window,
        config=consensus.KisSpyIntradayRegimeMicroConsensusConfig(),
    ) == (True, 0)

    micro_session_bars = tuple(
        bar
        for bar in _catalog(profile="micro_without_macro").bars
        if session.window.open_ts <= bar.start_ts and bar.end_ts <= session.window.close_ts
    )[:180]
    assert consensus._decision_state(
        source_bars=micro_session_bars,
        session=session.window,
        config=consensus.KisSpyIntradayRegimeMicroConsensusConfig(),
    ) == (False, 3)


def test_preflight_ignores_future_target_values_and_unavailable_input_never_evaluates_targets() -> (
    None
):
    baseline = consensus.prepare_kis_spy_intraday_regime_micro_consensus(
        _catalog(profile="all_bullish"),
    )
    changed_target = consensus.prepare_kis_spy_intraday_regime_micro_consensus(
        _catalog(
            profile="all_bullish",
            final_validation_target_shift=Decimal("80"),
        ),
    )

    assert changed_target.status == baseline.status == "ready"
    assert changed_target.input_hash == baseline.input_hash
    assert changed_target.safe_payload() == baseline.safe_payload()

    unavailable = consensus.prepare_kis_spy_intraday_regime_micro_consensus(
        _catalog(profile="macro_only", poison_final_validation_target_open=True),
    )
    assert unavailable.status == "input_unavailable"
    assert unavailable.validation.active_decision_count < 30

    result = consensus.evaluate_kis_spy_intraday_regime_micro_consensus(unavailable)
    assert result.status == "input_unavailable"
    assert result.validation is None


def test_validation_uses_cost_band_macro_mean_per_active_comparator_and_both_kill_paths() -> None:
    prepared = consensus.prepare_kis_spy_intraday_regime_micro_consensus(
        _catalog(profile="all_bullish"),
    )
    result = consensus.evaluate_kis_spy_intraday_regime_micro_consensus(prepared)

    assert result.status == "falsified"
    assert result.validation is not None
    validation = result.validation
    assert validation.candidate_active_decision_count == 10 * _SCHEDULED_DECISIONS_PER_SESSION
    assert validation.macro_regime_decision_count == 10 * _SCHEDULED_DECISIONS_PER_SESSION
    assert validation.schedule_wide_decision_count == 10 * _SCHEDULED_DECISIONS_PER_SESSION
    assert validation.candidate_net_mean_bps_by_cost["10"] - (
        validation.candidate_net_mean_bps_by_cost["5"]
    ) == -Decimal("5")
    assert validation.candidate_net_mean_bps_by_cost["20"] - (
        validation.candidate_net_mean_bps_by_cost["10"]
    ) == -Decimal("10")
    assert validation.candidate_net_total_bps_by_cost["20"] <= 0
    assert validation.macro_regime_net_mean_bps_by_cost == (
        validation.candidate_net_mean_bps_by_cost
    )
    assert (
        validation.schedule_wide_net_total_bps_by_cost["10"]
        == (validation.candidate_net_total_bps_by_cost["10"])
    )
    assert validation.kill_reasons == (
        "candidate_net_total_flat_or_worse_at_20bp",
        "candidate_mean_no_better_than_macro_regime_across_cost_band",
    )

    payload = result.safe_payload()["validation"]
    assert payload["macro_regime_net_mean_bps_by_all_in_round_trip_cost"] == {
        "5": str(validation.macro_regime_net_mean_bps_by_cost["5"]),
        "10": str(validation.macro_regime_net_mean_bps_by_cost["10"]),
        "20": str(validation.macro_regime_net_mean_bps_by_cost["20"]),
    }
    assert payload["schedule_wide_always_long"] == "descriptive_only"


def test_run_writes_idempotent_external_source_safe_artifacts_and_rejects_repo_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "not-for-artifacts")
    monkeypatch.setenv("TIINGO_API_TOKEN", "not-for-artifacts")
    artifact_root = tmp_path / "model-artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    catalog = _catalog(profile="all_bullish", start_price=Decimal("123.456789"))

    first = consensus.run_kis_spy_intraday_regime_micro_consensus(
        catalog,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=repo_root,
    )
    rerun = consensus.run_kis_spy_intraday_regime_micro_consensus(
        catalog,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=repo_root,
    )

    assert first.result.status == "falsified"
    assert first.precommit_path == rerun.precommit_path
    assert first.summary_path == rerun.summary_path
    assert first.precommit_hash == rerun.precommit_hash
    assert first.precommit_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    precommit = json.loads(first.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    _assert_source_safe({"precommit": precommit, "summary": summary})
    serialized = json.dumps({"precommit": precommit, "summary": summary}, sort_keys=True)
    for forbidden in (
        "123.456789",
        "not-for-artifacts",
        "KIS_PAPER_APP_KEY",
        "TIINGO_API_TOKEN",
    ):
        assert forbidden not in serialized

    with pytest.raises(ValueError, match="outside Git"):
        consensus.run_kis_spy_intraday_regime_micro_consensus(
            catalog,
            artifact_root=repo_root / "model-artifacts",
            run_label="repo-r1",
            repo_root=repo_root,
        )


class _TargetOpenPoison(Decimal):
    """Raise only if an unavailable campaign performs target-price arithmetic."""

    def __add__(self, _other: object) -> Decimal:
        _target_accessed()

    def __radd__(self, _other: object) -> Decimal:
        _target_accessed()

    def __sub__(self, _other: object) -> Decimal:
        _target_accessed()

    def __rsub__(self, _other: object) -> Decimal:
        _target_accessed()

    def __mul__(self, _other: object) -> Decimal:
        _target_accessed()

    def __rmul__(self, _other: object) -> Decimal:
        _target_accessed()

    def __truediv__(self, _other: object) -> Decimal:
        _target_accessed()

    def __rtruediv__(self, _other: object) -> Decimal:
        _target_accessed()


def _target_accessed() -> None:
    raise AssertionError("input_unavailable campaign must not evaluate a target price")


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("intraday regime micro consensus must remain offline")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("intraday regime micro consensus must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)


def _assert_source_safe(value: object) -> None:
    forbidden_keys = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "start_ts",
        "end_ts",
        "timestamp",
        "session_date",
        "source_path",
        "raw_bars",
        "returns",
        "scores",
    }
    if isinstance(value, dict):
        assert not forbidden_keys.intersection(value)
        for nested in value.values():
            _assert_source_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_source_safe(nested)


def _catalog(
    *,
    profile: str,
    start_price: Decimal = Decimal("100"),
    missing: tuple[int, int] | None = None,
    final_validation_target_shift: Decimal = Decimal("0"),
    poison_final_validation_target_open: bool = False,
) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        for minute in range(390):
            if missing == (session_index, minute):
                continue
            opened, closed = _minute_prices(
                profile=profile,
                session_index=session_index,
                minute=minute,
                start_price=start_price,
            )
            if session_index == len(_SESSION_DATES) - 1 and minute == 370:
                opened += final_validation_target_shift
                closed += final_validation_target_shift
            high = max(opened, closed) + Decimal("0.01")
            low = min(opened, closed) - Decimal("0.01")
            if session_index == len(_SESSION_DATES) - 1 and minute == 370:
                if poison_final_validation_target_open:
                    opened = _TargetOpenPoison(str(opened))
            bars.append(
                Bar(
                    symbol="SPY",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                    open=opened,
                    high=high,
                    low=low,
                    close=closed,
                    volume=Decimal("1000") + Decimal(session_index) + Decimal(minute),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.spy.ams.m1.regime-micro-consensus-unit-v1",
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("D:/market_data/unit-kis-spy-regime-micro-consensus-index.json"),
        bars=tuple(bars),
    )


def _minute_prices(
    *,
    profile: str,
    session_index: int,
    minute: int,
    start_price: Decimal,
) -> tuple[Decimal, Decimal]:
    base = start_price + Decimal(session_index) * Decimal("10")
    if profile == "all_bullish":
        opened = base + Decimal(minute) / Decimal("100")
        return opened, opened + Decimal("0.005")
    if profile == "macro_only":
        # The six 10m blocks repeat L/H/H/L/H/H. Each 1h/3h bar therefore
        # rises from L to H, yet every completed 5m/10m bar is flat. The L/H
        # cycle also repeats after 30 minutes, making every decision-time M1
        # close equal to the one 30 minutes earlier.
        within_ten_minutes = (minute % 60) // 10
        low = base + Decimal("1")
        high = base + Decimal("10")
        level = low if within_ten_minutes in {0, 3} else high
        return level, level
    if profile == "micro_without_macro":
        opened = base - Decimal(minute) / Decimal("10")
        if 170 <= minute <= 179:
            opened = base - Decimal("17") + Decimal(minute - 170) / Decimal("2")
        return opened, opened + Decimal("0.02")
    raise AssertionError(f"unknown fixture profile: {profile}")
