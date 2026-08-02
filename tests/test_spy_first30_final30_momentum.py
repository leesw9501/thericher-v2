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

momentum = pytest.importorskip(
    "thericher_v2.research.spy_first30_final30_momentum",
    reason="awaiting the Engine Research first-30/final-30 implementation",
)

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


def test_preparation_requires_exact_complete_21_session_split_and_causal_inputs() -> None:
    prepared = momentum.prepare_spy_first30_final30_momentum(_catalog(profile="favorable"))

    assert prepared.status == "ready"
    assert prepared.complete_regular_session_count == len(_SESSION_DATES)
    assert prepared.development.session_count == 10
    assert prepared.validation.session_count == 10
    assert prepared.development.structural_unavailable_count == 1
    assert prepared.development.active_decision_count == 9
    assert prepared.validation.structural_unavailable_count == 0
    assert prepared.validation.active_decision_count == 10

    payload = prepared.safe_payload()
    assert payload["contract"]["split"] == {
        "development_sessions": 10,
        "purge_sessions": 1,
        "validation_sessions": 10,
        "development_target_access": "prohibited",
    }
    assert payload["contract"]["input"] == {
        "prior_session": "completed_1600_et_final_m1_close",
        "current_session": "completed_0930_to_1000_et_first_30m_close",
        "direction": "sign_current_first_30m_return_from_prior_close",
    }
    assert payload["contract"]["target"] == {
        "entry": "1530_et_m1_open",
        "exit": "completed_1600_et_final_m1_close",
        "signed": True,
    }
    assert payload["contract"]["cost"]["all_in_round_trip_bps"] == ["5", "10", "20"]

    incomplete = momentum.prepare_spy_first30_final30_momentum(
        _catalog(profile="favorable", missing=(11, 179)),
    )
    assert incomplete.status == "input_unavailable"
    assert incomplete.reason == "insufficient_complete_regular_sessions"
    assert incomplete.complete_regular_session_count == len(_SESSION_DATES) - 1


def test_preflight_uses_only_prior_1559_and_completed_first_30_minutes() -> None:
    baseline = momentum.prepare_spy_first30_final30_momentum(_catalog(profile="favorable"))
    shifted_prior_close = momentum.prepare_spy_first30_final30_momentum(
        _catalog(profile="favorable", shifted_purge_prior_close=True),
    )
    changed_first_30 = momentum.prepare_spy_first30_final30_momentum(
        _catalog(profile="favorable", signal_override={19: -1}),
    )

    assert baseline.status == shifted_prior_close.status == changed_first_30.status == "ready"

    baseline_result = momentum.evaluate_spy_first30_final30_momentum(baseline)
    shifted_prior_close_result = momentum.evaluate_spy_first30_final30_momentum(
        shifted_prior_close,
    )
    changed_first_30_result = momentum.evaluate_spy_first30_final30_momentum(
        changed_first_30,
    )

    assert baseline_result.validation is not None
    assert shifted_prior_close_result.validation is not None
    assert changed_first_30_result.validation is not None
    baseline_total = baseline_result.validation.candidate_net_total_bps_by_cost["10"]
    assert shifted_prior_close_result.validation.candidate_net_total_bps_by_cost["10"] < (
        baseline_total - Decimal("100")
    )
    assert changed_first_30_result.validation.candidate_net_total_bps_by_cost["10"] < (
        baseline_total - Decimal("100")
    )


def test_preflight_never_reads_final_target_and_unavailable_input_cannot_evaluate_it() -> None:
    baseline = momentum.prepare_spy_first30_final30_momentum(_catalog(profile="favorable"))
    shifted_target = momentum.prepare_spy_first30_final30_momentum(
        _catalog(
            profile="favorable",
            final_validation_target_shift=Decimal("80"),
        ),
    )
    poisoned_ready = momentum.prepare_spy_first30_final30_momentum(
        _catalog(profile="favorable", poison_target_prices=True),
    )

    assert shifted_target.status == baseline.status == poisoned_ready.status == "ready"
    assert shifted_target.input_hash == baseline.input_hash
    assert shifted_target.safe_payload() == baseline.safe_payload()

    unavailable = momentum.prepare_spy_first30_final30_momentum(
        _catalog(profile="seven_active", poison_target_prices=True),
    )
    assert unavailable.status == "input_unavailable"
    assert unavailable.reason == "insufficient_validation_active_decisions"
    assert unavailable.validation.active_decision_count == 7

    result = momentum.evaluate_spy_first30_final30_momentum(unavailable)
    assert result.status == "input_unavailable"
    assert result.validation is None


def test_evaluation_uses_signed_target_direction_inverted_control_and_cost_kill() -> None:
    prepared = momentum.prepare_spy_first30_final30_momentum(_catalog(profile="favorable"))
    result = momentum.evaluate_spy_first30_final30_momentum(prepared)

    assert result.status == "non_promoting_validation"
    assert result.validation is not None
    validation = result.validation
    assert validation.candidate_active_decision_count == 10
    assert (
        validation.direction_inverted_decision_count == validation.candidate_active_decision_count
    )
    assert validation.candidate_net_total_bps_by_cost["10"] - (
        validation.candidate_net_total_bps_by_cost["5"]
    ) == -Decimal("5") * Decimal(validation.candidate_active_decision_count)
    assert validation.candidate_net_total_bps_by_cost["20"] - (
        validation.candidate_net_total_bps_by_cost["10"]
    ) == -Decimal("10") * Decimal(validation.candidate_active_decision_count)
    assert validation.candidate_net_total_bps_by_cost["20"] > 0
    assert (
        validation.candidate_net_total_bps_by_cost["10"]
        > (validation.direction_inverted_net_total_bps_by_cost["10"])
    )
    assert validation.kill_reasons == ()

    killed = momentum.evaluate_spy_first30_final30_momentum(
        momentum.prepare_spy_first30_final30_momentum(
            _catalog(profile="favorable", target_bps=Decimal("10")),
        )
    )
    assert killed.status == "falsified"
    assert killed.validation is not None
    assert killed.validation.candidate_net_total_bps_by_cost["20"] <= 0
    assert "candidate_signed_net_total_flat_or_worse_at_20bp" in killed.validation.kill_reasons


def test_run_writes_idempotent_external_aggregate_only_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    monkeypatch.setenv("KIS_PAPER_APP_KEY", "not-for-artifacts")
    monkeypatch.setenv("TIINGO_API_TOKEN", "not-for-artifacts")
    artifact_root = tmp_path / "model-artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    catalog = _catalog(profile="favorable", start_price=Decimal("123.456789"))

    first = momentum.run_spy_first30_final30_momentum(
        catalog,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=repo_root,
    )
    rerun = momentum.run_spy_first30_final30_momentum(
        catalog,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=repo_root,
    )

    assert first.result.status == "non_promoting_validation"
    assert first.precommit_path == rerun.precommit_path
    assert first.summary_path == rerun.summary_path
    assert first.precommit_hash == rerun.precommit_hash
    assert first.precommit_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (first.precommit_path, first.summary_path)
    ]
    _assert_source_safe(payloads)
    serialized = json.dumps(payloads, sort_keys=True)
    for forbidden in (
        "123.456789",
        "not-for-artifacts",
        "KIS_PAPER_APP_KEY",
        "TIINGO_API_TOKEN",
    ):
        assert forbidden not in serialized

    with pytest.raises(ValueError, match="outside Git"):
        momentum.run_spy_first30_final30_momentum(
            catalog,
            artifact_root=repo_root / "model-artifacts",
            run_label="repo-r1",
            repo_root=repo_root,
        )


class _TargetPricePoison(Decimal):
    """Raise only when the target price is touched before it is eligible."""

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
    raise AssertionError("preflight or unavailable input evaluated a final-thirty target price")


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("first-30/final-30 validation must remain offline")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("first-30/final-30 validation must not read credentials")

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
        "signals",
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
    target_bps: Decimal = Decimal("60"),
    missing: tuple[int, int] | None = None,
    signal_override: dict[int, int] | None = None,
    shifted_purge_prior_close: bool = False,
    final_validation_target_shift: Decimal = Decimal("0"),
    poison_target_prices: bool = False,
) -> CatalogedBars:
    signal_override = signal_override or {}
    bars: list[Bar] = []
    positions: dict[tuple[int, int], int] = {}
    previous_close = start_price
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        natural_signal = 1 if session_index % 2 else -1
        signal = signal_override.get(session_index, natural_signal)
        if profile == "seven_active" and session_index in {11, 12, 13}:
            signal = 0
        elif profile != "favorable" and profile != "seven_active":
            raise AssertionError(f"unknown fixture profile: {profile}")
        morning_close = _morning_close(
            previous_close=previous_close,
            signal=signal if session_index else 0,
        )
        entry_price = morning_close + Decimal("0.50")
        target_direction = natural_signal if session_index else 1
        final_close = entry_price * (
            Decimal("1") + Decimal(target_direction) * target_bps / Decimal("10000")
        )
        for minute in range(390):
            if missing == (session_index, minute):
                continue
            opened, closed = _minute_prices(
                minute=minute,
                morning_close=morning_close,
                entry_price=entry_price,
                final_close=final_close,
            )
            bar = Bar(
                symbol="SPY",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                open=opened,
                high=max(opened, closed) + Decimal("0.01"),
                low=min(opened, closed) - Decimal("0.01"),
                close=closed,
                volume=Decimal("1000") + Decimal(session_index) + Decimal(minute),
                complete=True,
            )
            positions[(session_index, minute)] = len(bars)
            bars.append(bar)
        previous_close = final_close

    if shifted_purge_prior_close:
        source = bars[positions[(10, 389)]]
        current_first_thirty_close = bars[positions[(11, 29)]].close
        bars[positions[(10, 389)]] = _replace_close(
            source,
            close=current_first_thirty_close + Decimal("10"),
        )
    if final_validation_target_shift:
        for minute in (360, 389):
            source = bars[positions[(20, minute)]]
            bars[positions[(20, minute)]] = _replace_prices(
                source,
                open=source.open + final_validation_target_shift,
                close=source.close + final_validation_target_shift,
            )
    if poison_target_prices:
        for session_index in range(11, 21):
            entry = bars[positions[(session_index, 360)]]
            close = bars[positions[(session_index, 389)]]
            object.__setattr__(entry, "open", _TargetPricePoison(str(entry.open)))
            object.__setattr__(close, "close", _TargetPricePoison(str(close.close)))
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.spy.ams.m1.first30-final30-unit-v1",
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("D:/market_data/unit-kis-spy-first30-final30-index.json"),
        bars=tuple(bars),
    )


def _morning_close(*, previous_close: Decimal, signal: int) -> Decimal:
    if signal == 0:
        return previous_close
    return previous_close * (Decimal("1") + Decimal(signal) / Decimal("100"))


def _minute_prices(
    *,
    minute: int,
    morning_close: Decimal,
    entry_price: Decimal,
    final_close: Decimal,
) -> tuple[Decimal, Decimal]:
    if minute < 30:
        closed = morning_close - Decimal(29 - minute) / Decimal("1000")
        return closed - Decimal("0.001"), closed
    if minute < 360:
        return morning_close, morning_close
    if minute == 360:
        return entry_price, entry_price
    if minute < 389:
        return entry_price, entry_price
    return final_close, final_close


def _replace_close(bar: Bar, *, close: Decimal) -> Bar:
    return _replace_prices(bar, open=bar.open, close=close)


def _replace_prices(bar: Bar, *, open: Decimal, close: Decimal) -> Bar:
    return Bar(
        symbol=bar.symbol,
        market=bar.market,
        timeframe=bar.timeframe,
        start_ts=bar.start_ts,
        open=open,
        high=max(open, close) + Decimal("0.01"),
        low=min(open, close) - Decimal("0.01"),
        close=close,
        volume=bar.volume,
        complete=bar.complete,
    )
