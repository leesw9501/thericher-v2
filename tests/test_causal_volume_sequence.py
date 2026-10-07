from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research import causal_volume_sequence as v


def pair(day=date(2023, 1, 3), minutes=390, zero=False):
    opening = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=14, minutes=30)
    session = SessionWindow(opening, opening + minutes * v.MINUTE)
    streams = tuple(
        tuple(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.M1,
                start_ts=opening + index * v.MINUTE,
                open=Decimal(100),
                high=Decimal(100),
                low=Decimal(100),
                close=Decimal(100),
                complete=True,
                volume=Decimal(0 if zero else (1 + index % 7) * (1 + number)),
            )
            for index in range(minutes)
        )
        for number, symbol in enumerate(v.SYMBOLS)
    )
    return streams, session


def projection(row):
    return replace(
        row, target=None, target_status="not_inspected", target_available_at=None, target_m1_count=0
    )


def synthetic_rows():
    dates = tuple(date(2022, 1, 1) + timedelta(days=index) for index in range(251))
    result = []
    for index, day in enumerate(dates):
        for slot in v.SLOTS:
            for number, symbol in enumerate(v.SYMBOLS):
                at = datetime.combine(day, datetime.min.time(), UTC) + (570 + slot) * v.MINUTE
                level = 1 + index % 11 + number
                features = tuple(
                    tuple(
                        float(level + step % 3 + channel % 2) for channel in range(len(v.FEATURES))
                    )
                    for step in range(24)
                )
                summary = tuple(float(level + channel % 5) for channel in range(len(v.SUMMARIES)))
                result.append(
                    v.VolumeRecord(
                        day,
                        symbol,
                        slot,
                        at,
                        features,
                        summary,
                        float(level * 30),
                        "available",
                        float(level * 35),
                        "available",
                        at + 31 * v.MINUTE,
                        120,
                        30,
                    )
                )
    return dates, tuple(result)


@pytest.mark.parametrize("slot", v.SLOTS)
def test_geometry_exact_complete24_m5_and30_future_m1(slot):
    streams, session = pair()
    rows = [row for row in v.records_from_pair(streams, session) if row.slot == slot]
    for row in rows:
        assert row.decision_at == session.open_ts + slot * v.MINUTE
        assert np.asarray(row.features).shape == (24, len(v.FEATURES))
        assert row.input_m1_count == 120 and row.target_m1_count == 30
        assert row.target_available_at == row.decision_at + 31 * v.MINUTE
        bars = streams[v.SYMBOLS.index(row.symbol)]
        assert row.target == sum(float(bar.volume) for bar in bars[slot + 1 : slot + 31])
        assert row.features[0][0] == math.log1p(
            sum(float(bar.volume) for bar in bars[slot - 120 : slot - 115])
        )
        assert row.past30 == sum(float(bar.volume) for bar in bars[slot - 30 : slot])
    assert [step[0] for step in rows[0].features] == [step[1] for step in rows[1].features]


@pytest.mark.parametrize("slot", v.SLOTS)
@pytest.mark.parametrize(
    "mutation", ["prefix", "future_values", "future_support", "missing_target"]
)
def test_input_does_not_depend_on_future_values_or_support(slot, mutation):
    streams, session = pair()
    original = [row for row in v.records_from_pair(streams, session) if row.slot == slot]
    at = session.open_ts + slot * v.MINUTE
    changed = []
    for bars in streams:
        changed.append(
            tuple(
                replace(bar, volume=bar.volume * 123)
                if mutation == "future_values" and bar.start_ts >= at
                else replace(bar, complete=False)
                if mutation == "future_support" and bar.start_ts >= at
                else bar
                for bar in bars
                if not (mutation == "prefix" and bar.start_ts >= at)
                and not (mutation == "missing_target" and bar.start_ts == at + v.MINUTE)
            )
        )
    rows = [row for row in v.records_from_pair(tuple(changed), session) if row.slot == slot]
    assert tuple(map(projection, original)) == tuple(map(projection, rows))
    if mutation in ("prefix", "future_support", "missing_target"):
        assert all(row.target is None for row in rows)
    else:
        assert all(
            row.target == previous.target * 123
            for row, previous in zip(rows, original, strict=True)
        )


@pytest.mark.parametrize("slot", v.SLOTS)
def test_target_only_slice_is_independent_of_past(slot):
    streams, session = pair()
    at = session.open_ts + slot * v.MINUTE
    original = [row for row in v.records_from_pair(streams, session) if row.slot == slot]
    sliced = tuple(
        tuple(bar for bar in bars if at < bar.start_ts < at + 31 * v.MINUTE) for bars in streams
    )
    later = [row for row in v.records_from_pair(sliced, session) if row.slot == slot]
    assert [row.target for row in original] == [row.target for row in later]
    assert all(row.features is None for row in later)


def test_early_close_never_clips_decision_keys():
    streams, session = pair(minutes=210)
    rows = v.records_from_pair(streams, session)
    assert len(rows) == 8
    assert [row.slot for row in rows] == [120, 120, 180, 180, 240, 240, 300, 300]
    assert [row.input_status for row in rows[::2]] == [
        "available",
        "available",
        "calendar_input_unavailable",
        "calendar_input_unavailable",
    ]
    assert [row.target_status for row in rows[::2]] == [
        "available",
        "calendar_target_unavailable",
        "calendar_target_unavailable",
        "calendar_target_unavailable",
    ]


def test_zero_volume_is_valid_for_input_and_target_without_floor():
    streams, session = pair(zero=True)
    rows = v.records_from_pair(streams, session)
    assert all(row.target == 0 and row.target_status == "available" for row in rows)
    assert all(row.past30 == 0 and all(step[:2] == (0, 0) for step in row.features) for row in rows)
    stats = v.train_statistics(rows)
    assert stats["target_mean"] == 0 and stats["target_scale"] == 1


@pytest.mark.parametrize("region", ["past", "target"])
def test_duplicate_keys_are_concrete_faults(region):
    streams, session = pair()
    index = 10 if region == "past" else 121
    edited = (streams[0][:index] + (streams[0][index],) + streams[0][index:], streams[1])
    with pytest.raises(v.VolumeFault, match="duplicate_.*_keys"):
        v.records_from_pair(edited, session)


@pytest.mark.parametrize("field", ["symbol", "market", "timeframe"])
def test_required_identity_mismatch_not_silently_censored(field):
    streams, session = pair()
    value = {"symbol": "IWM", "market": "KR", "timeframe": Timeframe.M5}[field]
    edited = ((replace(streams[0][0], **{field: value}), *streams[0][1:]), streams[1])
    with pytest.raises(v.VolumeFault, match="input_identity"):
        v.records_from_pair(edited, session)


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "wrong_slot", "wrong_dates", "reverse_dates"]
)
def test_fixed_split_rejects_duplicates_and_cardinality_changes(mutation):
    dates, rows = synthetic_rows()
    if mutation == "duplicate":
        rows = (*rows[:-1], rows[0])
    elif mutation == "missing":
        rows = rows[:-1]
    elif mutation == "wrong_slot":
        rows = (replace(rows[0], slot=121), *rows[1:])
    elif mutation == "wrong_dates":
        dates = dates[:-1]
    else:
        dates = dates[::-1]
    with pytest.raises(v.VolumeFault):
        v.split_records(rows, dates)


def test_split_and_statistics_are_train_only_and_feature_mask_is_target_blind():
    dates, rows = synthetic_rows()
    train, later = v.split_records(rows, dates)
    stats = v.train_statistics(train)
    assert len(train) == 160 * 8 and len(later) == 90 * 8
    assert max(row.session_date for row in train) == dates[159]
    assert min(row.session_date for row in later) == dates[161]
    changed = tuple(
        replace(row, target=row.target * 9000) if row.session_date >= dates[160] else row
        for row in rows
    )
    changed_train, _ = v.split_records(changed, dates)
    assert v.train_statistics(changed_train) == stats
    censored = (
        replace(
            train[0],
            target=None,
            target_status="required_forward_m1_shortfall",
            target_available_at=None,
            target_m1_count=29,
        ),
        *train[1:],
    )
    censored_stats = v.train_statistics(censored)
    for field in ("feature_mean", "feature_scale", "summary_mean", "summary_scale", "input_rows"):
        assert censored_stats[field] == stats[field]
    assert censored_stats["fit_rows"] == stats["fit_rows"] - 1


@pytest.fixture
def prepared_models():
    dates, rows = synthetic_rows()
    train, later = v.split_records(rows, dates)
    stats = v.train_statistics(train)
    _, z, y, weights = v.training_arrays(train, stats)
    return (
        dates,
        train,
        later,
        {"statistics": stats, "ridge": v.fit_ridge(z, y, weights), "gru": {}},
    )


@pytest.fixture
def models(prepared_models):
    torch = pytest.importorskip("torch", reason="numeric GRU replay requires optional PyTorch")
    dates, train, later, state = prepared_models
    torch.manual_seed(101)
    model = v._model(torch)
    state["gru"] = {name: tensor.detach().tolist() for name, tensor in model.state_dict().items()}
    return dates, train, later, state


def test_saved_numeric_weights_cpu_inference_and_loss_without_fit(models, monkeypatch):
    torch = pytest.importorskip("torch", reason="numeric GRU replay requires optional PyTorch")

    dates, train, later, state = models
    restored = json.loads(json.dumps(state, allow_nan=False))
    original = v.predict(state, later)
    for name in ("fit_models", "fit_gru", "fit_ridge"):
        monkeypatch.setattr(v, name, lambda *a, **k: pytest.fail("refit"))
    monkeypatch.setattr(torch.optim, "AdamW", lambda *a, **k: pytest.fail("optimizer"))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: pytest.fail("GPU probe"))
    v.attest_train(restored, train)
    actual = v.predict(restored, tuple(map(projection, later)))
    assert actual == original
    assert v.evaluate(later, actual, state["statistics"], dates[161:]) == v.evaluate(
        later, original, state["statistics"], dates[161:]
    )


def test_fixed128_epoch_synthetic_cpu_smoke_only():
    pytest.importorskip("torch", reason="synthetic GRU training requires optional PyTorch")
    _, rows = synthetic_rows()
    train = rows[:8]
    stats = v.train_statistics(train)
    x, _, y, weights = v.training_arrays(train, stats)
    state = v.fit_gru(x, y, weights, deadline=time.monotonic() + 60, device="cpu")
    assert set(state) == {
        "encoder.weight_ih_l0",
        "encoder.weight_hh_l0",
        "encoder.bias_ih_l0",
        "encoder.bias_hh_l0",
        "head.weight",
        "head.bias",
    }
    assert all(np.isfinite(value).all() for value in state.values())


def test_missing_torch_skips_only_model_fixture_and_training_smoke(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(pytest.skip.Exception):
        models.__wrapped__(None)
    with pytest.raises(pytest.skip.Exception):
        test_fixed128_epoch_synthetic_cpu_smoke_only()
    streams, session = pair()
    assert all(row.input_status == "available" for row in v.records_from_pair(streams, session))
    dates, _, later, state = prepared_models.__wrapped__()
    forecasts = ideal_forecasts(later, state["statistics"])
    assert v.evaluate(later, forecasts, state["statistics"], dates[161:])["status"] == (
        "survived_seen_development_kill"
    )


@pytest.mark.parametrize("field", ["feature_mean", "target_mean", "slot_means", "ridge", "gru"])
def test_modified_model_state_is_rejected(models, field):
    _, train, later, state = models
    state = json.loads(json.dumps(state))
    if field == "ridge":
        state[field][0] += 0.5
    elif field == "gru":
        state[field]["head.bias"] = [float("nan")]
    elif field == "target_mean":
        state["statistics"][field] += 0.5
    elif field == "slot_means":
        state["statistics"][field][0][0] += 1
    else:
        state["statistics"][field][0] += 0.5
    with pytest.raises(v.VolumeFault):
        v.attest_train(state, train)
        v.predict(state, later)


def test_zero_seasonality_denominator_is_scoped_unknown(models):
    dates, _, later, state = models
    state = json.loads(json.dumps(state))
    state["statistics"]["slot_means"][0][1] = 0
    forecasts = v.predict(state, later)
    assert all(
        forecasts[row.key]["seasonality"] is None
        for row in later
        if row.symbol == "QQQ" and row.slot == 120
    )
    assert all(
        forecasts[row.key]["seasonality"] is not None for row in later if row.symbol == "SPY"
    )
    report = v.evaluate(later, forecasts, state["statistics"], dates[161:])
    assert report["exclusions"]["control_unknown"] == 90
    assert report["etfs"]["QQQ"]["all90"]["eligible_keys"] == 270
    assert report["etfs"]["SPY"]["all90"]["eligible_keys"] == 360


def ideal_forecasts(rows, stats, error=0):
    return {
        row.key: {
            method: (math.log1p(row.target) - stats["target_mean"]) / stats["target_scale"]
            + (error if method == "gru" else 1)
            for method in v.METHODS
        }
        for row in rows
    }


def test_strict_kill_every_etf_control_half_and_shared_date_deletion(prepared_models):
    dates, _, later, state = prepared_models
    stats = state["statistics"]
    forecasts = ideal_forecasts(later, stats)
    report = v.evaluate(later, forecasts, stats, dates[161:])
    assert report["status"] == "survived_seen_development_kill"
    for symbol in v.SYMBOLS:
        assert len(report["etfs"][symbol]["all90"]["delete_each_shared_date"]) == 90
        assert len(report["etfs"][symbol]["first45"]["delete_each_shared_date"]) == 45
    for row in later:
        if row.symbol == "SPY":
            forecasts[row.key]["gru"] = forecasts[row.key]["ridge"]
    assert v.evaluate(later, forecasts, stats, dates[161:])["status"] == "rejected"


def test_day_weighting_halves_before_exclusions_and_missing_targets_not_imputed(prepared_models):
    dates, _, later, state = prepared_models
    stats = state["statistics"]
    forecasts = ideal_forecasts(later, stats)
    selected = tuple(
        replace(
            row,
            target=None,
            target_status="required_forward_m1_shortfall",
            target_available_at=None,
            target_m1_count=29,
        )
        if row.session_date == dates[161] and row.slot != 120
        else row
        for row in later
    )
    # One slot on the first ETF day has squared error9; all other ETF days error0.
    for row in selected:
        if row.session_date == dates[161] and row.slot == 120:
            forecasts[row.key]["gru"] += 3
    report = v.evaluate(selected, forecasts, stats, dates[161:])
    assert report["etfs"]["QQQ"]["all90"]["loss"]["gru"] == pytest.approx(9 / 90)
    assert report["etfs"]["QQQ"]["first45"]["loss"]["gru"] == pytest.approx(9 / 45)
    assert report["etfs"]["QQQ"]["last45"]["loss"]["gru"] == 0
    assert report["exclusions"] == {"required_forward_m1_shortfall": 6}


def test_date_deletion_can_kill_without_refit(prepared_models):
    dates, _, later, state = prepared_models
    stats = state["statistics"]
    forecasts = ideal_forecasts(later, stats, math.sqrt(0.951))
    for row in later:
        if row.session_date in (dates[161], dates[206]):
            forecasts[row.key]["gru"] -= math.sqrt(0.951)
    report = v.evaluate(later, forecasts, stats, dates[161:])
    first = report["etfs"]["QQQ"]["first45"]
    assert first["loss"]["gru"] < 0.95
    assert first["delete_each_shared_date"][dates[161].isoformat()]["passes"] is False
    assert report["status"] == "rejected"
