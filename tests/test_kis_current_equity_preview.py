import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import kis_current_equity_preview as current
from thericher_v2.research import kis_pooled_equity_components as core


@pytest.fixture
def plan():
    # Artificial scheduled weekdays, not a claim to have loaded an exchange calendar.
    days = []
    day = date(2026, 10, 9)
    while len(days) < 800:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    sessions = tuple(reversed(days))
    return core.ComponentPlan(
        sessions,
        tuple(f"opaque:{i:03}" for i in range(12)),
        tuple(datetime.combine(day, time(13, 30), UTC) for day in sessions),
        tuple(datetime.combine(day, time(20), UTC) for day in sessions),
    )


@pytest.fixture
def observed(plan):
    return {
        key: plan.close_clocks[-2] + timedelta(minutes=i + 1) for i, key in enumerate(plan.keys)
    }


@pytest.fixture
def at(plan):
    return plan.open_clocks[-1] - timedelta(hours=1)


@pytest.fixture
def past(plan):
    indices = {day: i for i, day in enumerate(plan.sessions)}
    assets = {key: i for i, key in enumerate(plan.keys)}

    def source(key, day):
        opening = Decimal("100.000000000000000000001") + Decimal(indices[day]) / 10
        closing = opening * (1 + Decimal(assets[key] + 1) / 1000)
        return Bar(
            symbol=f"SYNTHETIC{assets[key]}",
            market="US",
            timeframe=Timeframe.D1,
            start_ts=datetime.combine(day, time(), UTC),
            open=opening,
            high=closing * Decimal("1.01"),
            low=opening * Decimal("0.99"),
            close=closing,
            volume=Decimal(1000),
        )

    return source


def forbidden(*_args):
    pytest.fail("unexpected source/target access")


def test_exact_current_core_control_and_clocks(plan, past, observed, at):
    calls = []

    def source(key, day):
        assert day < plan.sessions[-1]
        calls.append((key, day))
        return past(key, day)

    result = current.preview(plan, source, observed, preview_at=at)
    state = core.snapshot(plan, 799, past)
    assert result.selected_keys == core.controls(state)["component"].selected_keys
    assert result.eligible_keys == result.plan_keys == plan.keys
    assert result.unavailable_keys == result.missing_observation_keys == ()
    assert result.status == "top10_preview"
    assert result.required_sessions == plan.sessions[-62:-1]
    assert calls == [(key, day) for key in plan.keys for day in plan.sessions[-62:-1]]
    assert result.past_source_call_count == 12 * 61
    assert result.nominal_decision_close_at == state.decision_at == plan.close_clocks[-2]
    assert result.nominal_entry_open_at == state.entry_open_at == plan.open_clocks[-1]
    assert result.nominal_target_close_at == state.target_close_at == plan.close_clocks[-1]
    assert result.nominal_decision_close_at != past(plan.keys[0], plan.sessions[-2]).end_ts
    assert result.source_observed_at == tuple(observed.items())
    assert result.latest_source_observed_at == max(observed.values())
    assert result.preview_at == at
    assert result.historical_decision_time_availability == "not_observed"
    assert tuple(key for key, _ in result.weights) == plan.keys
    assert sum(weight for _, weight in result.weights) == Decimal(1)
    assert all(
        weight == (Decimal("0.1") if key in result.selected_keys else 0)
        for key, weight in result.weights
    )


def test_future_callback_strict_and_target_mutation_invariant(
    plan, past, observed, at, monkeypatch
):
    before = current.preview(plan, past, observed, preview_at=at)
    monkeypatch.setattr(core, "target_labels", forbidden)
    monkeypatch.setattr(core, "evaluate_day", forbidden)
    monkeypatch.setattr(core, "replay_day", forbidden)
    future_reads = []

    def source(key, day):
        if day >= plan.sessions[-1]:
            future_reads.append((key, day))
            pytest.fail("entry/target numeric read")
        return past(key, day)

    assert current.preview(plan, source, observed, preview_at=at) == before
    assert future_reads == []


@pytest.mark.parametrize("escape", ["entry", "older", "foreign_key"])
def test_callback_boundary_rejects_core_window_escape_before_source(
    plan, observed, at, monkeypatch, escape
):
    def escaped_snapshot(_plan, _index, source):
        key = "foreign" if escape == "foreign_key" else plan.keys[0]
        day = plan.sessions[-1] if escape == "entry" else plan.sessions[-63]
        if escape == "foreign_key":
            day = plan.sessions[-2]
        return source(key, day)

    monkeypatch.setattr(core, "snapshot", escaped_snapshot)
    with pytest.raises(ValueError, match="past_callback_outside_frozen_window"):
        current.preview(plan, forbidden, observed, preview_at=at)


@pytest.mark.parametrize("bad_day_index", [-62, -42, -2])
def test_61_consecutive_required_sessions_not_100_row_count(
    plan, past, observed, at, bad_day_index
):
    bad_key = plan.keys[-1]
    rows = {
        day: past(bad_key, day)
        for day in plan.sessions[-102:-1]
        if day != plan.sessions[bad_day_index]
    }
    assert len(rows) == 100

    def source(key, day):
        return rows.get(day) if key == bad_key else past(key, day)

    result = current.preview(plan, source, observed, preview_at=at)
    assert result.eligible_keys == plan.keys[:-1]
    assert result.unavailable_keys == (bad_key,)
    assert bad_key not in result.selected_keys
    assert result.plan_keys == plan.keys


@pytest.mark.parametrize("fault", ["incomplete", "entry_bar", "wrong_timeframe", "mixed_identity"])
def test_core_rejects_invalid_past_bar_without_shrinking_plan(plan, past, observed, at, fault):
    bad_key, bad_day = plan.keys[0], plan.sessions[-62]

    def source(key, day):
        bar = past(key, day)
        if (key, day) != (bad_key, bad_day):
            return bar
        if fault == "incomplete":
            return replace(bar, complete=False)
        if fault == "entry_bar":
            return past(key, plan.sessions[-1])
        if fault == "wrong_timeframe":
            return replace(bar, timeframe=Timeframe.H1)
        return replace(bar, symbol="OTHER")

    result = current.preview(plan, source, observed, preview_at=at)
    assert result.unavailable_keys == (bad_key,)
    assert result.plan_keys == plan.keys
    assert result.eligible_keys == plan.keys[1:]


@pytest.mark.parametrize("explicit_none", [False, True])
def test_missing_observation_excludes_only_its_key_without_read(
    plan, past, observed, at, explicit_none
):
    bad_key = plan.keys[0]
    if explicit_none:
        observed[bad_key] = None
    else:
        del observed[bad_key]
    calls = []

    def source(key, day):
        assert key != bad_key
        calls.append((key, day))
        return past(key, day)

    result = current.preview(plan, source, observed, preview_at=at)
    assert result.eligible_keys == plan.keys[1:]
    assert result.unavailable_keys == result.missing_observation_keys == (bad_key,)
    assert dict(result.source_observed_at)[bad_key] is None
    assert len(calls) == result.past_source_call_count == 11 * 61
    assert len(result.selected_keys) == 10


def test_observation_before_latest_close_cannot_read_uncompleted_bar(plan, past, observed, at):
    bad_key = plan.keys[0]
    observed[bad_key] = plan.close_clocks[-2] - timedelta(seconds=1)

    def source(key, day):
        assert plan.close_clocks[plan.sessions.index(day)] <= observed[key]
        return past(key, day)

    result = current.preview(plan, source, observed, preview_at=at)
    assert result.unavailable_keys == (bad_key,)
    assert result.missing_observation_keys == ()
    assert result.past_source_call_count == 12 * 61 - 1


@pytest.mark.parametrize("bad_key_index", [0, -1])
def test_future_observation_rejected_before_any_callback(plan, observed, at, bad_key_index):
    observed[plan.keys[bad_key_index]] = at + timedelta(microseconds=1)
    with pytest.raises(ValueError, match="source_observation_after_preview"):
        current.preview(plan, forbidden, observed, preview_at=at)


@pytest.mark.parametrize("field", ["preview", "observation"])
@pytest.mark.parametrize("fault", ["naive", "non_utc", "string", "date"])
def test_actual_clocks_require_aware_utc_before_callbacks(plan, observed, at, field, fault):
    value = at if field == "preview" else observed[plan.keys[0]]
    if fault == "naive":
        value = value.replace(tzinfo=None)
    elif fault == "non_utc":
        value = value.astimezone(timezone(timedelta(hours=9)))
    elif fault == "string":
        value = value.isoformat()
    else:
        value = value.date()
    if field == "preview":
        at = value
    else:
        observed[plan.keys[0]] = value
    with pytest.raises(ValueError, match="must_be_aware_UTC"):
        current.preview(plan, forbidden, observed, preview_at=at)


def test_preview_must_follow_nominal_close_even_with_no_observations(plan):
    with pytest.raises(ValueError, match="preview_before_nominal_decision_close"):
        current.preview(
            plan, forbidden, {}, preview_at=plan.close_clocks[-2] - timedelta(microseconds=1)
        )


def test_exact_observation_and_nominal_close_equality_allowed(plan, past):
    at = plan.close_clocks[-2]
    result = current.preview(plan, past, dict.fromkeys(plan.keys, at), preview_at=at)
    assert result.eligible_keys == plan.keys
    assert result.latest_source_observed_at == result.preview_at == result.nominal_decision_close_at
    assert result.historical_decision_time_availability == "not_observed"


def test_latest_observation_of_data_unavailable_key_still_bounds_preview(plan, observed, at):
    observed[plan.keys[-1]] = at + timedelta(microseconds=1)
    with pytest.raises(ValueError, match="source_observation_after_preview"):
        current.preview(plan, lambda *_args: None, observed, preview_at=at)


def test_foreign_observation_key_rejected_before_callback(plan, observed, at):
    observed["foreign"] = at
    with pytest.raises(ValueError, match="observation_keys_outside_frozen_plan"):
        current.preview(plan, forbidden, observed, preview_at=at)


def test_stale_entry_plan_rejected_before_callback(plan, observed, at):
    stale = replace(
        plan,
        sessions=tuple(day - timedelta(days=1) for day in plan.sessions),
        open_clocks=tuple(clock - timedelta(days=1) for clock in plan.open_clocks),
        close_clocks=tuple(clock - timedelta(days=1) for clock in plan.close_clocks),
    )
    with pytest.raises(ValueError, match="frozen_current_entry_plan_required"):
        current.preview(stale, forbidden, observed, preview_at=at)


def test_lexicographic_ties_and_observation_mapping_order_deterministic(plan, past, observed, at):
    def tied(_key, day):
        return past(plan.keys[0], day)

    result = current.preview(plan, tied, observed, preview_at=at)
    reversed_clocks = dict(reversed(tuple(observed.items())))
    again = current.preview(plan, tied, reversed_clocks, preview_at=at)
    assert result == again
    assert result.selected_keys == plan.keys[:10]
    assert json.dumps(result.source_safe_document()) == json.dumps(again.source_safe_document())


@pytest.mark.parametrize("count", [0, 1, 9, 10])
def test_flat_preview_retains_all_keys_and_does_not_block_independent_preview(
    plan, past, observed, at, count
):
    result = current.preview(
        plan, past, {key: observed[key] for key in plan.keys[:count]}, preview_at=at
    )
    assert result.plan_keys == plan.keys
    assert result.eligible_keys == plan.keys[:count]
    assert result.unavailable_keys == plan.keys[count:]
    assert result.missing_observation_keys == plan.keys[count:]
    assert len(result.selected_keys) == (10 if count == 10 else 0)
    assert result.status == ("top10_preview" if count == 10 else "flat_preview")
    assert sum(weight for _, weight in result.weights) == (1 if count == 10 else 0)
    assert result.latest_source_observed_at == (observed[plan.keys[count - 1]] if count else None)
    assert current.preview(plan, past, observed, preview_at=at).status == "top10_preview"


def test_source_safe_document_has_only_keys_weights_clocks_counts_and_preview_scope(
    plan, past, observed, at
):
    result = current.preview(plan, past, observed, preview_at=at)
    document = result.source_safe_document()
    assert document["counts"] == {
        "plan_sessions": 800,
        "required_past_sessions": 61,
        "component_context": 20,
        "top_k": 10,
        "plan_keys": 12,
        "eligible_keys": 12,
        "unavailable_keys": 0,
        "missing_observation_keys": 0,
        "selected_keys": 10,
        "past_source_calls": 732,
    }
    assert document["scope"]["preview_only"] is True
    assert all(value is False for key, value in document["scope"].items() if key != "preview_only")
    assert document["historical_decision_time_availability"] == "not_observed"
    assert document["control"] == "component"
    encoded = json.dumps(document, allow_nan=False)
    for forbidden_field in ("component_score", "confidence", "edge", "OrderIntent", "SYNTHETIC"):
        if forbidden_field == "confidence":
            assert '"confidence":' not in encoded
        else:
            assert forbidden_field not in encoded
    assert all(isinstance(weight, str) for weight in document["weights"].values())
    document["eligible_keys"].clear()
    document["weights"].clear()
    document["scope"]["paper_input"] = True
    assert result.source_safe_document()["eligible_keys"] == list(plan.keys)
    assert result.source_safe_document()["scope"]["paper_input"] is False


def test_no_price_float_mutation_and_inputs_not_modified(plan, past, observed, at):
    bars = {(key, day): past(key, day) for key in plan.keys for day in plan.sessions[-62:-1]}
    before_records = {
        identity: (bar, tuple(str(getattr(bar, name)) for name in ("open", "high", "low", "close")))
        for identity, bar in bars.items()
    }
    before_observed, before_plan = dict(observed), replace(plan)
    result = current.preview(plan, lambda key, day: bars[key, day], observed, preview_at=at)
    assert observed == before_observed
    assert plan == before_plan
    price_fields = ("open", "high", "low", "close")
    for identity, bar in bars.items():
        original, strings = before_records[identity]
        assert bar is original
        assert all(isinstance(getattr(bar, name), Decimal) for name in price_fields)
        assert tuple(str(getattr(bar, name)) for name in price_fields) == strings
    observed.clear()
    bars.clear()
    assert result.source_observed_at == tuple(before_observed.items())
    with pytest.raises(FrozenInstanceError):
        result.preview_at = at + timedelta(days=1)
    with pytest.raises(TypeError):
        result.weights[0] = (plan.keys[0], Decimal(1))
