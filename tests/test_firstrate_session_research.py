"""Synthetic session/cohort/payoff tests; no retained data or broker access."""

import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff, synthetic_receipt
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import EmergencyStore
from thericher_v2.research import firstrate_session_research as s

HASH = "sha256:" + "a" * 64


@pytest.fixture(scope="module")
def source():
    sessions, bars = [], []
    day = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    while len(sessions) < 160:
        if day.weekday() < 5:
            sessions.append((day, day + timedelta(minutes=390)))
            for minute in range(0, 390, 5):
                p = Decimal(100) + Decimal((len(bars) * 17) % 113) / 100
                bars.append(
                    Bar(
                        symbol="SPY",
                        market="US",
                        timeframe=Timeframe.M5,
                        start_ts=day + timedelta(minutes=minute),
                        open=p,
                        close=p + Decimal(".01"),
                        high=p + Decimal(".1"),
                        low=p - Decimal(".1"),
                        volume=Decimal(100 + minute),
                        complete=True,
                    )
                )
        day += timedelta(days=1)
    return tuple(sessions), tuple(bars)


@pytest.mark.parametrize("horizon", s.HORIZONS)
def test_all_training_grid_and_nonoverlap_evaluation(source, horizon):
    sessions, _ = source
    train = s.session_grid(sessions[:1], horizon, training=True)
    evaluation = s.session_grid(sessions[:1], horizon, training=False)
    assert train[0] == sessions[0][0] + timedelta(minutes=180)
    assert all(b - a == timedelta(minutes=5) for a, b in zip(train, train[1:], strict=False))
    assert all(
        b - a == timedelta(minutes=horizon)
        for a, b in zip(evaluation, evaluation[1:], strict=False)
    )
    assert train[-1] + timedelta(minutes=horizon) < sessions[0][1]
    assert len(s.session_grid(sessions, horizon, training=True)) > 1024
    for training, ev, cutoff, count in s.plans(sessions, horizon):
        assert cutoff == ev[0] - timedelta(minutes=180)
        assert all(t + timedelta(minutes=horizon) < cutoff for t in training)
        assert count == 40


def test_real_calendar_dst_and_early_close(source):
    _, bars = source
    dates = (
        datetime(2025, 3, 7, tzinfo=UTC),
        datetime(2025, 3, 10, tzinfo=UTC),
        datetime(2025, 11, 28, tzinfo=UTC),
    )
    sessions = s.regular_sessions([replace(bars[0], start_ts=d) for d in dates])
    by_date = {o.date(): (o, c) for o, c in sessions}
    assert by_date[dates[0].date()][0].hour == 14
    assert by_date[dates[1].date()][0].hour == 13
    early = by_date[dates[2].date()]
    assert early[1] - early[0] == timedelta(minutes=210)
    assert s.session_grid((early,), 30, training=True) == ()


@pytest.mark.parametrize("horizon", s.HORIZONS)
def test_expanded_cohort_and_train_only_scalers(source, horizon):
    sessions, bars = source
    index = {b.start_ts: b for b in bars}
    plan = s.plans(sessions, horizon)[0]
    fold = s.prepare_fold("SPY", 1, index, plan, horizon)
    assert len(fold.train_y) > 1024
    assert fold.train_x.shape[1:] == (36, 4)
    assert np.isfinite(fold.train_x).all()
    changed = {
        t: replace(b, volume=b.volume * 100) if t >= plan[2] else b for t, b in index.items()
    }
    other = s.prepare_fold("SPY", 1, changed, plan, horizon)
    np.testing.assert_array_equal(fold.train_x, other.train_x)
    np.testing.assert_array_equal(fold.train_y, other.train_y)
    assert fold.facts["normalizer_sha256"] == other.facts["normalizer_sha256"]


def test_future_missing_does_not_change_decision_inputs(source):
    sessions, bars = source
    index = {b.start_ts: b for b in bars}
    at = s.session_grid(sessions[:1], 30, training=False)[0]
    observations, facts = s.h30.observe(index, (at,))
    before, _ = s.outcomes(index, observations, 30)
    del index[at + timedelta(minutes=30)]
    after_observations, after_facts = s.h30.observe(index, (at,))
    after, censor = s.outcomes(index, after_observations, 30)
    assert observations == after_observations and facts == after_facts
    assert before[0] is not None and after == (None,) and censor["future_missing"] == 1


def test_past_incomplete_no_fill_or_backfill(source):
    sessions, bars = source
    index = {b.start_ts: b for b in bars}
    at = s.session_grid(sessions[:1], 30, training=False)[0]
    index[at - s.h30.STEP] = replace(index[at - s.h30.STEP], complete=False)
    obs, facts = s.h30.observe(index, (at,))
    assert obs == () and facts["past_incomplete"] == 1


@pytest.mark.parametrize("horizon", s.HORIZONS)
@pytest.mark.parametrize("cost", s.COSTS)
def test_all_horizon_cost_payoffs_replay_local_paper(source, tmp_path, horizon, cost):
    sessions, bars = source
    index = {b.start_ts: b for b in bars}
    at = s.session_grid(sessions[:1], horizon, training=False)[0]
    obs, _ = s.h30.observe(index, (at,))
    out, _ = s.outcomes(index, obs, horizon)
    assert s.payoff(
        obs[0], out[0], cost, EmergencyStore(tmp_path / "emergency.json")
    ) == fast_payoff(obs[0], out[0], cost, None)
    assert out[0].bars[-1].start_ts - obs[0].at == timedelta(minutes=horizon)


def test_matrix_cpu_cuda_cohort_and_exact_full_training_passes(source):
    sessions, bars = source

    def streams():
        return tuple(
            (symbol, tuple(replace(b, symbol=symbol) for b in bars)) for symbol in s.h30.SYMBOLS
        )

    calls = []

    def trainer(torch, fold, context, seed, deadline):
        calls.append((fold.symbol, fold.fold, fold.facts["horizon_minutes"], context, seed))
        return (
            np.zeros(len(fold.evaluation)),
            {},
            dict(
                epochs=8,
                updates=8 * ((len(fold.train_y) + 127) // 128),
                train_rows=len(fold.train_y),
            ),
        )

    kwargs = dict(
        schedules=sessions, replay=fast_payoff, ridge=lambda f, c: np.zeros(len(f.evaluation))
    )
    cpu, retained = s.compare(streams(), "cpu", None, time.monotonic() + 60, **kwargs)
    cpu["contract_sha256"] = HASH
    s.validate_result(cpu, "cpu", HASH)
    assert len(cpu["cells"]) == 216 and retained == []
    cuda, retained = s.compare(
        streams(), "cuda", None, time.monotonic() + 60, reference=cpu, trainer=trainer, **kwargs
    )
    cuda["contract_sha256"] = HASH
    s.validate_result(cuda, "cuda", HASH)
    assert len(calls) == len(set(calls)) == len(retained) == 48
    assert len(cuda["cells"]) == 144 and cuda["folds"] == cpu["folds"]
    assert all(c["roundtrips"] == 0 for c in cpu["cells"] if c["candidate"] == "always_flat")
    bad = {**cuda, "cells": cuda["cells"][:-1]}
    with pytest.raises(ValueError, match="cell_matrix"):
        s.validate_result(bad, "cuda", HASH)
    cuda["fits"][0]["updates"] -= 1
    with pytest.raises(ValueError, match="training_passes"):
        s.validate_result(cuda, "cuda", HASH)


def test_contract_no_new_holdout_no_cap_and_external_artifacts(tmp_path, monkeypatch):
    receipt = synthetic_receipt(tmp_path / "market")
    contract = s.contract(receipt)
    assert contract["budget"]["sample_cap"] is None
    assert contract["budget"]["lstm_fits"] == 48 and contract["prediction_threshold_bps"] == 6
    assert all(contract[k] is False for k in ("promotion", "holdout_access", "selection", "retry"))
    with pytest.raises(ValueError, match="outside"):
        s.freeze(s.REPO / "generated-test-artifacts")
    root = tmp_path / "artifacts"
    path = root / s.h30.RECEIPT
    path.parent.mkdir(parents=True)
    path.write_bytes(receipt)
    parent = root / s.PARENT
    parent.parent.mkdir(parents=True)
    parent.write_bytes(b"{}")
    monkeypatch.setattr(s, "PARENT_HASH", s.h30.digest(b"{}"))
    monkeypatch.setattr(s.h30, "register_frozen_campaign", lambda **kw: None)
    scope = s.freeze(root)
    output, _, _ = s.verify(root, scope)
    assert output.is_relative_to(root)
    with pytest.raises(FileExistsError):
        s.freeze(root)
    with pytest.raises(ValueError, match="contract_changed"):
        s.verify(root, HASH)


def test_no_future_outcomes_is_unavailable_after_predictions(source, monkeypatch):
    sessions, bars = source
    first_eval = s.plans(sessions, 30)[0][1][0]
    original = s.outcomes
    calls = []

    def no_future(index, observations, horizon):
        if observations and observations[0].at >= first_eval:
            assert calls == [12, 36]
            return (None,) * len(observations), dict(
                eligible=len(observations), observed=0, future_missing=len(observations)
            )
        return original(index, observations, horizon)

    def ridge(fold, context):
        calls.append(context)
        return np.zeros(len(fold.evaluation))

    monkeypatch.setattr(s, "outcomes", no_future)
    with pytest.raises(s.OutcomeSupportShortfall) as caught:
        s.compare(
            (("SPY", bars),),
            "cpu",
            None,
            time.monotonic() + 30,
            schedules=sessions,
            ridge=ridge,
            replay=fast_payoff,
        )
    assert caught.value.support["observed"] == 0
    assert caught.value.support["eligible"] == caught.value.support["censored"] > 0
