import math
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import kis_pooled_equity_components as core


@pytest.fixture
def plan():
    sessions = tuple(date(2020, 1, 1) + timedelta(days=i) for i in range(800))
    return core.ComponentPlan(
        sessions,
        tuple(f"key{i:03}" for i in range(12)),
        tuple(datetime.combine(day, time(14, 30), UTC) for day in sessions),
        tuple(datetime.combine(day, time(21), UTC) for day in sessions),
    )


@pytest.fixture
def past(plan):
    indices = {day: i for i, day in enumerate(plan.sessions)}

    def source(key, day):
        asset = int(key[3:])
        opening = Decimal(100 + asset) + Decimal(indices[day]) / 10
        closing = opening * (1 + Decimal(asset + 1) / 1000)
        return Bar(
            symbol=key,
            market="US",
            timeframe=Timeframe.D1,
            start_ts=datetime.combine(day, time(), UTC),
            open=opening,
            high=max(opening, closing) * Decimal("1.01"),
            low=min(opening, closing) * Decimal("0.99"),
            close=closing,
            volume=Decimal(1000),
        )

    return source


def state(plan, index, count=12):
    return core.EligibilitySnapshot(
        index,
        plan.sessions[index - 1],
        plan.sessions[index],
        tuple(
            core.FeatureRow(key, ((0.0,) * 20, (0.0,) * 20), (0.0,) * 3, 0.0)
            for key in plan.keys[:count]
        ),
        plan.keys[count:],
        plan.close_clocks[index - 1],
        plan.open_clocks[index],
        plan.close_clocks[index],
    )


def prediction(snapshot):
    return core.seal(snapshot, dict.fromkeys(snapshot.eligible_keys, 0.0))


def constant_target(value):
    return lambda _key, _day: core.OpenClose(100.0, 100 * (1 + value))


def test_exact_frozen_geometry_and_prefix_label_clocks(plan):
    assert tuple(core.TRAIN_ENTRIES) == tuple(range(61, 520))
    assert core.FIT_COUNT == 10 and core.FAMILY_SECONDS == 600
    assert core.CELL_COUNT == 48 and len(core.POLICIES) == 8
    assert core.ROUND_TRIP_BPS == (5, 10, 20)
    assert tuple(day for fold in core.OOF_FOLDS for day in fold.score_entries) == tuple(
        core.OOF_ENTRIES
    )
    assert len(core.OOF_ENTRIES) == 364
    for fold, cutoff in zip(core.OOF_FOLDS, (154, 245, 336, 427), strict=True):
        assert tuple(fold.fit_entries) == tuple(range(61, cutoff + 1))
        assert len(fold.score_entries) == 91
        assert plan.close_clocks[cutoff] < plan.close_clocks[fold.score_entries.start - 1]
    assert tuple(core.DEV_VIEWS[0]) == tuple(range(540, 670))
    assert tuple(core.DEV_VIEWS[1]) == tuple(range(670, 800))


@pytest.mark.parametrize(
    "fault",
    [
        "short",
        "duplicate_date",
        "unsorted_keys",
        "duplicate_keys",
        "too_many_keys",
        "missing_clocks",
        "overlap_clocks",
    ],
)
def test_plan_requires_exact_calendar_keys_and_clocks(plan, fault):
    kwargs = {}
    if fault == "short":
        kwargs["sessions"] = plan.sessions[:-1]
    elif fault == "duplicate_date":
        kwargs["sessions"] = (plan.sessions[0], *plan.sessions[:-1])
    elif fault == "unsorted_keys":
        kwargs["keys"] = tuple(reversed(plan.keys))
    elif fault == "duplicate_keys":
        kwargs["keys"] = (plan.keys[0], *plan.keys)
    elif fault == "too_many_keys":
        kwargs["keys"] = tuple(f"key{i:03}" for i in range(129))
    elif fault == "missing_clocks":
        kwargs["open_clocks"] = plan.open_clocks[:-1]
    else:
        kwargs["close_clocks"] = plan.open_clocks
    with pytest.raises(ValueError):
        replace(plan, **kwargs)


@pytest.mark.parametrize("index", [60, 800, True, 61.0])
def test_unsupported_entry_never_calls_source(plan, index):
    def forbidden(*_args):
        pytest.fail("unexpected source read")

    with pytest.raises(ValueError):
        core.snapshot(plan, index, forbidden)


def test_exact_past_window_components_controls_and_explicit_clocks(plan, past):
    calls = []
    index = 100

    def source(key, day):
        assert day < plan.sessions[index]
        calls.append((key, day))
        return past(key, day)

    snapshot = core.snapshot(plan, index, source)
    assert calls == [(key, day) for key in plan.keys for day in plan.sessions[index - 61 : index]]
    assert snapshot.eligible_keys == plan.keys and snapshot.unavailable_keys == ()
    row = snapshot.rows[0]
    expected_overnight = tuple(
        math.log(
            float(past(row.key, plan.sessions[i]).open / past(row.key, plan.sessions[i - 1]).close)
        )
        for i in range(index - 20, index)
    )
    expected_intraday = tuple(
        math.log(
            float(past(row.key, plan.sessions[i]).close / past(row.key, plan.sessions[i]).open)
        )
        for i in range(index - 20, index)
    )
    assert row.components[0] == pytest.approx(expected_overnight)
    assert row.components[1] == pytest.approx(expected_intraday)
    assert row.flattened == row.components[0] + row.components[1]
    assert len(row.flattened) == 40
    assert row.component_score == pytest.approx(sum(expected_intraday) - sum(expected_overnight))
    for i, lookback in enumerate((5, 20, 60)):
        assert row.momentum[i] == pytest.approx(
            float(
                past(row.key, plan.sessions[index - 1]).close
                / past(row.key, plan.sessions[index - lookback]).close
                - 1
            )
        )
    assert snapshot.decision_at == plan.close_clocks[index - 1]
    assert snapshot.entry_open_at == plan.open_clocks[index]
    assert snapshot.target_close_at == plan.close_clocks[index]
    assert snapshot.decision_at != past(row.key, plan.sessions[index - 1]).end_ts
    assert set(core.controls(snapshot)) == {
        "component",
        "momentum5",
        "momentum20",
        "momentum60",
        "equal_weight",
        "cash",
    }


@pytest.mark.parametrize("index", [61, 156, 540, 799])
def test_future_mutation_cannot_change_features_eligibility_or_seal(plan, past, index):
    before = core.snapshot(plan, index, past)

    def poisoned(key, day):
        if day >= plan.sessions[index]:
            pytest.fail("future numeric lookup before seal")
        return past(key, day)

    after = core.snapshot(plan, index, poisoned)
    assert before == after
    assert core.controls(before) == core.controls(after)
    assert prediction(before) == prediction(after)


@pytest.mark.parametrize(
    "fault", ["missing", "incomplete", "wrong_date", "mixed_symbol", "high_low_gt2"]
)
def test_all_61_required_past_bars_define_one_shared_eligibility(plan, past, fault):
    key = plan.keys[0]
    day = plan.sessions[0]

    def source(current_key, current_day):
        bar = past(current_key, current_day)
        if (current_key, current_day) != (key, day):
            return bar
        if fault == "missing":
            return None
        if fault == "incomplete":
            return replace(bar, complete=False)
        if fault == "wrong_date":
            return replace(bar, start_ts=bar.start_ts - timedelta(days=1))
        if fault == "mixed_symbol":
            return replace(bar, symbol="OTHER")
        return replace(bar, low=Decimal(90), high=Decimal("180.01"))

    snapshot = core.snapshot(plan, 61, source)
    assert snapshot.unavailable_keys == (key,)
    assert key not in snapshot.eligible_keys
    for policy in core.controls(snapshot).values():
        assert tuple(k for k, _ in policy.scores) == snapshot.eligible_keys


def test_hygiene_boundary_two_is_allowed(plan, past):
    def source(key, day):
        return replace(past(key, day), low=Decimal(90), high=Decimal(180))

    assert core.snapshot(plan, 61, source).eligible_keys == plan.keys


def test_feature_and_prediction_seals_are_deeply_immutable(plan):
    values = [[0.0] * 20, [0.0] * 20]
    row = core.FeatureRow("key000", values, [0.0] * 3, 0.0)
    values[0][0] = 999
    assert row.components[0][0] == 0
    snapshot = state(plan, 61)
    scores = dict.fromkeys(plan.keys, 0.0)
    sealed = core.seal(snapshot, scores)
    scores[plan.keys[-1]] = 999
    assert sealed.selected_keys == plan.keys[:10]
    with pytest.raises(FrozenInstanceError):
        sealed.selected_keys = ()
    with pytest.raises(TypeError):
        sealed.scores[0] = ("foreign", 10)


def test_aligned_decimal_and_string_scores_preserve_exact_order_and_ties(plan):
    snapshot = state(plan, 61)
    scores = ["1.00000000000000000000000000000000000"] * 12
    scores[-1] = Decimal("1.00000000000000000000000000000000001")
    sealed = core.seal(snapshot, scores)
    assert sealed.selected_keys == (plan.keys[-1], *plan.keys[:9])
    assert sealed.scores[-1][1] == scores[-1]
    scores[-1] = "0"
    assert sealed.selected_keys[0] == plan.keys[-1]
    with pytest.raises(ValueError):
        core.seal(snapshot, scores[:-1])
    with pytest.raises(ValueError):
        core.seal(snapshot, ["NaN"] * 12)


@pytest.mark.parametrize("fault", ["missing", "extra", "nan", "boolean"])
def test_every_eligible_score_must_be_bound_and_finite(plan, fault):
    snapshot = state(plan, 61)
    scores = dict.fromkeys(plan.keys, 0.0)
    if fault == "missing":
        del scores[plan.keys[0]]
    elif fault == "extra":
        scores["foreign"] = 0.0
    else:
        scores[plan.keys[0]] = float("nan") if fault == "nan" else True
    with pytest.raises(ValueError):
        core.seal(snapshot, scores)


@pytest.mark.parametrize("count", [0, 9])
def test_below_ten_is_flat_for_all_policies_with_no_execution_reads(plan, count):
    snapshot = state(plan, 61, count)

    def forbidden(*_args):
        pytest.fail("flat policy must not read execution outcomes")

    for policy in (prediction(snapshot), *core.controls(snapshot).values()):
        assert policy.selected_keys == ()
        for cost in core.ROUND_TRIP_BPS:
            day = core.replay_day(policy, forbidden, round_trip_bps=cost)
            assert day.complete and day.gross_return == day.net_return == 0
            assert day.entry_turnover == day.exit_turnover == 0


def test_tied_rank_labels_use_entire_frozen_cross_section(plan):
    snapshot = state(plan, 61)
    calls = []

    def target(key, day):
        calls.append((key, day))
        return core.OpenClose(100.0, 100.0 + int(key[3:]) // 2)

    labels = core.target_labels(snapshot, target)
    assert calls == [(key, snapshot.entry_session) for key in plan.keys]
    assert labels.coverage == (12, 12) and labels.missing_keys == ()
    values = dict(labels.labels)
    assert values[plan.keys[0]] == values[plan.keys[1]] == pytest.approx(0.5 / 11 - 0.5)
    assert values[plan.keys[-1]] == pytest.approx(10.5 / 11 - 0.5)
    assert labels.available_at == plan.close_clocks[61]
    assert snapshot.decision_at < labels.available_at


def test_day_evaluator_seals_all_cached_policies_before_target_callback(plan, monkeypatch):
    snapshot = state(plan, 61)
    sealed = []
    original = core.seal

    def traced(*args, **kwargs):
        result = original(*args, **kwargs)
        sealed.append(result)
        return result

    monkeypatch.setattr(core, "seal", traced)
    reads = []

    def target(key, day):
        assert len(sealed) == 8
        reads.append((key, day))
        return core.OpenClose(100.0, 100.0 + int(key[3:]))

    evaluation = core.evaluate_day(snapshot, {"tcn": [0.0] * 12, "ridge": ["0"] * 12}, target)
    assert tuple(name for name, _ in evaluation.policies) == core.POLICIES
    assert len(evaluation.replays) == 24
    assert reads == [(key, snapshot.entry_session) for key in plan.keys]
    assert evaluation.labels.coverage == (12, 12)
    assert all(day.seal.snapshot == snapshot for _, _, day in evaluation.replays)
    assert all(day.complete for _, _, day in evaluation.replays)


@pytest.mark.parametrize("fault", ["missing_arm", "extra_arm", "missing_score", "invalid_score"])
def test_invalid_cached_scores_never_reach_target_callback(plan, fault):
    scores = {"tcn": [0.0] * 12, "ridge": [0.0] * 12}
    if fault == "missing_arm":
        del scores["ridge"]
    elif fault == "extra_arm":
        scores["extra"] = [0.0] * 12
    elif fault == "missing_score":
        scores["ridge"] = [0.0] * 11
    else:
        scores["ridge"][-1] = "Infinity"
    with pytest.raises(ValueError):
        core.evaluate_day(
            state(plan, 61), scores, lambda *_args: pytest.fail("unexpected target callback")
        )


def test_missing_unselected_peer_invalidates_labels_not_sealed_winners(plan):
    snapshot = state(plan, 61)
    sealed = prediction(snapshot)
    omitted = plan.keys[-1]

    def target(key, _day):
        return None if key == omitted else core.OpenClose(100.0, 101.0)

    labels = core.target_labels(snapshot, target)
    assert labels.coverage == (11, 12) and labels.missing_keys == (omitted,)
    assert labels.labels is None
    assert core.replay_day(sealed, target).complete
    assert not core.replay_day(core.controls(snapshot)["equal_weight"], target).complete
    assert sealed.selected_keys == plan.keys[:10]
    with pytest.raises(ValueError, match="complete_cross_section"):
        replace(labels, labels=tuple((key, 0.0) for key, _ in labels.observed_returns))


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        core.OpenClose(0.0, 100.0),
        core.OpenClose(-1.0, 100.0),
        core.OpenClose(100.0, float("nan")),
        core.OpenClose(100.0, float("inf")),
    ],
)
def test_selected_target_missing_or_invalid_never_replaced(plan, invalid):
    snapshot = state(plan, 61)
    sealed = prediction(snapshot)

    def target(key, _day):
        return invalid if key == plan.keys[0] else core.OpenClose(100.0, 200.0)

    day = core.replay_day(sealed, target)
    assert not day.complete and day.net_return is None and day.gross_return is None
    assert day.missing_selected == (plan.keys[0],)
    assert day.reason == "selected_target_missing"
    assert sealed.selected_keys == plan.keys[:10]
    assert core.target_labels(snapshot, target).labels is None


def test_future_high_low_is_not_a_hindsight_event_filter(plan, past):
    snapshot = state(plan, 61)
    sealed = prediction(snapshot)

    def target(key, day):
        return replace(past(key, day), high=Decimal(1000), low=Decimal(1))

    assert core.replay_day(sealed, target).complete
    assert core.target_labels(snapshot, target).labels is not None
    lost = core.replay_day(sealed, constant_target(-0.5))
    assert lost.complete and lost.net_return == pytest.approx(-0.501)
    assert lost.seal == sealed


@pytest.mark.parametrize("cost", [5, 10, 20])
def test_full_entry_exit_cash_turnover_is_one_round_trip_each_day(plan, cost):
    days = tuple(
        core.replay_day(prediction(state(plan, i)), constant_target(0), round_trip_bps=cost)
        for i in (61, 62)
    )
    for day in days:
        assert day.entry_turnover == day.exit_turnover == 1
        assert day.net_return == pytest.approx(-cost / 10000)
    metrics = core.portfolio_metrics(days, expected_entries=(61, 62))
    assert metrics.complete
    assert metrics.growth == pytest.approx((1 - cost / 10000) ** 2 - 1)
    assert metrics.utility == pytest.approx(252 * math.log1p(-cost / 10000))
    for name, policy in core.controls(state(plan, 61)).items():
        day = core.replay_day(policy, constant_target(0), round_trip_bps=cost)
        assert day.net_return == pytest.approx(0 if name == "cash" else -cost / 10000)


def test_nonpositive_net_nav_is_unavailable_not_clipped(plan):
    day = core.replay_day(prediction(state(plan, 61)), constant_target(-0.9999), round_trip_bps=20)
    assert not day.complete and day.net_return is None
    assert day.reason == "net_nav_nonpositive_or_nonfinite"
    metrics = core.portfolio_metrics((day,), expected_entries=(61,))
    assert not metrics.complete and metrics.missing_entries == (61,)
    assert metrics.growth is metrics.utility is None


def test_metrics_keep_missing_sessions_and_compound_without_view_reset(plan):
    first = core.replay_day(prediction(state(plan, 61)), constant_target(0.02))
    second = core.replay_day(prediction(state(plan, 62)), constant_target(-0.01))
    assert not core.portfolio_metrics((first,), expected_entries=(61, 62)).complete
    metrics = core.portfolio_metrics((first, second), expected_entries=(61, 62))
    logs = (math.log1p(first.net_return), math.log1p(second.net_return))
    mean = sum(logs) / 2
    variance = sum((value - mean) ** 2 for value in logs) / 2
    assert metrics.growth == pytest.approx((1 + first.net_return) * (1 + second.net_return) - 1)
    assert metrics.utility == pytest.approx(252 * (mean - 5 * variance))
    assert metrics.maximum_drawdown == pytest.approx(-second.net_return)
    with pytest.raises(ValueError, match="replay_session_binding"):
        core.portfolio_metrics((first, first), expected_entries=(61, 62))
    with pytest.raises(ValueError, match="mixed_replay"):
        core.portfolio_metrics(
            (first, replace(second, round_trip_bps=20)), expected_entries=(61, 62)
        )


def test_oof_spearman_is_session_equal_not_row_weighted(plan):
    pairs = []
    for i, count, direction in ((156, 10, 1), (157, 12, -1)):
        snapshot = state(plan, i, count)
        scores = {key: direction * int(key[3:]) for key in snapshot.eligible_keys}
        targets = core.target_labels(
            snapshot, lambda key, _day: core.OpenClose(100.0, 100.0 + int(key[3:]))
        )
        pairs.append((core.seal(snapshot, scores), targets))
    metric = core.session_equal_spearman(pairs, expected_entries=(156, 157))
    assert metric.complete and metric.mean_spearman == pytest.approx(0)
    missing = core.session_equal_spearman(pairs[:1], expected_entries=(156, 157))
    assert not missing.complete and missing.missing_entries == (157,)
    assert missing.mean_spearman == pytest.approx(1)


def test_oof_incomplete_labels_constant_scores_and_cross_section_mismatch(plan):
    snapshot = state(plan, 156)
    sealed = prediction(snapshot)
    complete = core.target_labels(
        snapshot, lambda key, _day: core.OpenClose(100.0, 100.0 + int(key[3:]))
    )
    assert not core.session_equal_spearman(((sealed, complete),), expected_entries=(156,)).complete
    incomplete = core.target_labels(
        snapshot, lambda key, _day: None if key == plan.keys[-1] else core.OpenClose(100.0, 101.0)
    )
    assert not core.session_equal_spearman(
        ((sealed, incomplete),), expected_entries=(156,)
    ).complete
    foreign = core.target_labels(state(plan, 156, 10), constant_target(0.01))
    with pytest.raises(ValueError, match="cross_section_binding"):
        core.session_equal_spearman(((sealed, foreign),), expected_entries=(156,))
    with pytest.raises(ValueError):
        core.OOFRankMetric(364, (), float("nan"))


@pytest.fixture
def evidence(plan):
    oof = {
        name: core.OOFRankMetric(364, (), 0.9 if name == "tcn" else 0.1)
        for name in ("tcn", *core.RANK_CONTROLS)
    }
    dev = {name: [] for name in core.POLICIES}
    for index in range(540, 800):
        snapshot = state(plan, index)
        for name in core.POLICIES:
            policy = core.controls(snapshot).get(name, prediction(snapshot))
            dev[name].append(
                core.replay_day(policy, constant_target(0.01 if name == "tcn" else 0.002))
            )
    return oof, dev


def test_strong_kill_requires_all_controls_both_views_and_complete_oof(evidence):
    oof, dev = evidence
    assert core.strongest_kill(oof, dev).survives
    assert all(
        metrics.session_count == 130 and metrics.complete
        for metrics in core.view_metrics(dev["tcn"])
    )
    oof["tcn"] = core.OOFRankMetric(364, (156,), 0.9)
    result = core.strongest_kill(oof, dev)
    assert not result.survives and "required_oof_evidence_missing" in result.reasons


@pytest.mark.parametrize(
    "fault",
    [
        "second_view_loss",
        "ridge_equal",
        "missing_selected",
        "missing_day",
        "missing_control",
        "equal_oof",
    ],
)
def test_strong_kill_cannot_average_away_a_failed_or_missing_comparison(plan, evidence, fault):
    oof, dev = evidence
    if fault == "second_view_loss":
        dev["tcn"] = [
            day
            if day.seal.snapshot.entry_index < 670
            else core.replay_day(day.seal, constant_target(-0.01))
            for day in dev["tcn"]
        ]
    elif fault == "ridge_equal":
        dev["ridge"] = dev["tcn"]
    elif fault == "missing_selected":
        dev["tcn"][0] = core.replay_day(dev["tcn"][0].seal, lambda _key, _day: None)
    elif fault == "missing_day":
        del dev["tcn"][0]
    elif fault == "missing_control":
        del dev["momentum60"]
    else:
        oof["momentum60"] = oof["tcn"]
    assert not core.strongest_kill(oof, dev).survives


def test_strong_kill_requires_primary_cost_and_matched_past_eligibility(plan, evidence):
    oof, dev = evidence
    original = dev["ridge"][0]
    dev["ridge"][0] = replace(original, round_trip_bps=20)
    with pytest.raises(ValueError, match="primary_10bps"):
        core.strongest_kill(oof, dev)
    dev["ridge"][0] = core.replay_day(prediction(state(plan, 540, 10)), constant_target(0.002))
    with pytest.raises(ValueError, match="matched_policy_eligibility"):
        core.strongest_kill(oof, dev)


@pytest.mark.parametrize("cost", [0, 15, 10.0, True])
def test_unfrozen_stress_is_rejected_before_target_read(plan, cost):
    with pytest.raises(ValueError, match="cost_stress_not_frozen"):
        core.replay_day(
            prediction(state(plan, 61)),
            lambda *_args: pytest.fail("unexpected target read"),
            round_trip_bps=cost,
        )
