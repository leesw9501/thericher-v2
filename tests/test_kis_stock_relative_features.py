"""Synthetic stock-specific geometry/causality tests; no model or market I/O."""

from __future__ import annotations

import ast
import math
import statistics
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_relative_features as k

KEYS = tuple(f"opaque-{i:03}" for i in range(128))


def make_plan(count=113):
    # Deliberately nonconsecutive calendar dates: horizon means scheduled sessions.
    days = tuple(date(2030, 1, 1) + timedelta(days=i * 2) for i in range(count))
    return k.FeaturePlan(
        days,
        KEYS,
        tuple(datetime.combine(day, time(14, 30), UTC) for day in days),
        tuple(datetime.combine(day, time(21), UTC) for day in days),
    )


@pytest.fixture(scope="module")
def plan():
    return make_plan()


@pytest.fixture(scope="module")
def bars(plan):
    panel = {}
    for j, key in enumerate(KEYS):
        for i, day in enumerate(plan.sessions):
            opening = Decimal(100 + j) + Decimal(i) / 4
            closing = opening * (1 + Decimal((i + j) % 7 - 3) / 1000)
            panel[key, day] = Bar(
                symbol=f"SYN{j:03}",
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(day, time(), UTC),
                open=opening,
                high=max(opening, closing) * Decimal("1.01"),
                low=min(opening, closing) * Decimal("0.99"),
                close=closing,
                volume=Decimal(1000),
            )
    return panel


def build(plan, bars, *, entry=61, eligible=KEYS, sequence=False, calls=None):
    def source(key, day):
        assert day in plan.sessions[entry - 61 : entry]
        if calls is not None:
            calls.append((key, day))
        return bars.get((key, day)) if key in eligible else None

    return k.features(plan, entry, source, include_sequence=sequence)


def quotes(seal, *, faults=None, calls=None):
    identities = {row.key: row for row in seal.rows}
    offsets = {key: j for j, key in enumerate(seal.eligible_keys)}

    def source(key, day):
        assert key in seal.eligible_keys and day in (seal.entry_session, seal.exit_session)
        if calls is not None:
            calls.append((key, day))
        row = identities[key]
        value = k.OpenQuote(
            row.symbol,
            row.market,
            day,
            seal.entry_open_at if day == seal.entry_session else seal.exit_open_at,
            Decimal(100) if day == seal.entry_session else Decimal(100) + offsets[key],
        )
        return faults.get((key, day), value) if faults is not None else value

    return source


def test_separate_geometry_and_five_session_purge(plan):
    assert k.FEATURE_NAMES == ("meanID5", "meanID20", "meanON20", "close_return_vol20")
    assert k.MAX_FUTURE_FITS == 9
    assert tuple(plan.complete_entries) == tuple(range(61, 108))
    assert plan.complete_entries == plan.complete_target_entries
    assert tuple(plan.feature_entries) == tuple(range(61, 113))
    assert len(plan.feature_entries) == 52
    assert len(plan.complete_entries) == 47
    old = make_plan(800)
    assert len(old.complete_entries) == 734
    assert len(old.feature_entries) == 739
    for cutoff, last, count in [(427, 422, 362), (609, 604, 544), (799, 794, 734)]:
        prefix = k.purged_prefix_entries(old, cutoff)
        assert prefix[-1] == last and len(prefix) == count
        assert all(entry + 5 <= cutoff for entry in prefix)
    assert not k.purged_prefix_entries(plan, 65)
    assert tuple(k.purged_prefix_entries(plan, 66)) == (61,)
    assert k.purged_prefix_entries(plan, 112) == plan.complete_entries


@pytest.mark.parametrize("bad", [60, 113, 117, True, 61.0])
def test_unknown_or_invalid_entry_never_reads_source(plan, bad):
    with pytest.raises(ValueError, match="entry"):
        k.features(plan, bad, lambda *args: pytest.fail("source read"))


@pytest.mark.parametrize("bad", [-1, 113, True, 427.0])
def test_invalid_prefix_cutoff(plan, bad):
    with pytest.raises(ValueError):
        k.purged_prefix_entries(plan, bad)


@pytest.mark.parametrize(
    "fault",
    ["size", "merged", "dates", "keys", "count", "naive", "missing_clock", "overlap", "wrong_date"],
)
def test_fixed_plan_identity_and_calendar(plan, fault):
    changes = {}
    if fault == "size":
        changes["sessions"] = plan.sessions[:-1]
    elif fault == "merged":
        changes["sessions"] = plan.sessions + make_plan(800).sessions
    elif fault == "dates":
        changes["sessions"] = tuple(reversed(plan.sessions))
    elif fault == "keys":
        changes["keys"] = tuple(reversed(KEYS))
    elif fault == "count":
        changes["keys"] = KEYS[:-1]
    elif fault == "naive":
        changes["open_clocks"] = tuple(v.replace(tzinfo=None) for v in plan.open_clocks)
    elif fault == "missing_clock":
        changes["close_clocks"] = plan.close_clocks[:-1]
    elif fault == "overlap":
        changes["close_clocks"] = plan.open_clocks
    else:
        changes["open_clocks"] = tuple(v + timedelta(days=1) for v in plan.open_clocks)
    with pytest.raises(ValueError):
        replace(plan, **changes)


def test_prior61_exactly_once_core_eligibility_and_raw_sequence(plan, bars):
    calls = []
    seal = build(plan, bars, sequence=True, calls=calls)
    assert len(calls) == len(set(calls)) == 128 * 61
    assert calls == [(key, day) for key in KEYS for day in plan.sessions[:61]]
    reference = core.snapshot(plan, 61, lambda key, day: bars[key, day])
    assert seal.eligible_keys == reference.eligible_keys == KEYS
    assert seal.unavailable_keys == ()
    assert len(seal.features) == len(seal.sequences) == 128
    assert all(len(row) == 4 for row in seal.features)
    assert all(len(seq) == 20 and all(len(step) == 2 for step in seq) for seq in seal.sequences)
    for actual, original in zip(seal.rows, reference.rows, strict=True):
        assert actual.sequence == tuple(zip(*original.components, strict=True))
        assert (actual.symbol, actual.market) == (bars[actual.key, plan.sessions[60]].symbol, "US")
    assert seal.decision_at == plan.close_clocks[60]
    assert seal.entry_open_at == plan.open_clocks[61]
    assert seal.exit_index == 66 and seal.exit_open_at == plan.open_clocks[66]
    assert (seal.exit_session - seal.entry_session).days == 10


def test_three_centered_log_mean_features_volatility_not_centered(plan, bars):
    seal = build(plan, bars, sequence=True)
    snapshot = core.snapshot(plan, 61, lambda key, day: bars[key, day])
    raw = [
        (
            math.fsum(row.components[1][-5:]) / 5,
            math.fsum(row.components[1]) / 20,
            math.fsum(row.components[0]) / 20,
        )
        for row in snapshot.rows
    ]
    means = [math.fsum(row[j] / 128 for row in raw) for j in range(3)]
    for j in range(3):
        assert abs(math.fsum(row.values[j] for row in seal.rows)) < 1e-12
    for actual, original in zip(seal.rows, raw, strict=True):
        assert actual.values[:3] == tuple(original[j] - means[j] for j in range(3))
        closes = [bars[actual.key, day].close for day in plan.sessions[40:61]]
        returns = [
            float(Fraction(b) / Fraction(a) - 1) for a, b in zip(closes, closes[1:], strict=False)
        ]
        assert actual.values[-1] == pytest.approx(statistics.pstdev(returns), rel=1e-12)
        assert actual.values[-1] > 0


def test_sequence_optional_same_past_access_same_four_features(plan, bars):
    first_calls, second_calls = [], []
    first = build(plan, bars, calls=first_calls)
    second = build(plan, bars, sequence=True, calls=second_calls)
    assert first.features == second.features
    assert first_calls == second_calls and first.sequences is None


def test_current_last_complete_entry_requests_only_its_prior61_and_scheduled_exit(plan, bars):
    calls = []
    seal = build(plan, bars, entry=107, calls=calls)
    assert seal.exit_index == 112 and seal.exit_session == plan.sessions[-1]
    assert calls == [(key, day) for key in KEYS for day in plan.sessions[46:107]]
    targets = []
    result = k.target_labels(seal, quotes(seal, calls=targets))
    assert result.values is not None
    assert result.unavailable_reason is None
    assert result.available_at == plan.open_clocks[112]
    assert {day for _, day in targets} == {plan.sessions[107], plan.sessions[112]}


@pytest.mark.parametrize("entry", [108, 111, 112])
@pytest.mark.parametrize("sequence", [False, True])
def test_known_tail_entry_features_do_not_require_future_target_calendar(
    plan, bars, entry, sequence
):
    calls = []
    seal = build(plan, bars, entry=entry, sequence=sequence, calls=calls)
    assert calls == [(key, day) for key in KEYS for day in plan.sessions[entry - 61 : entry]]
    assert len(calls) == len(set(calls)) == 128 * 61
    assert seal.eligible_keys == KEYS and seal.unavailable_keys == ()
    assert len(seal.features) == 128 and all(len(row) == 4 for row in seal.features)
    assert seal.entry_session == plan.sessions[entry]
    assert seal.entry_open_at == plan.open_clocks[entry]
    assert seal.decision_at == plan.close_clocks[entry - 1]
    assert seal.exit_index == entry + 5
    assert seal.exit_session is None and seal.exit_open_at is None
    assert (seal.sequences is not None) == sequence
    result = k.target_labels(seal, lambda *args: pytest.fail("unknown horizon quote read"))
    assert result.values is None and result.available_at is None
    assert result.unavailable_reason == "target_horizon_not_in_calendar"
    assert result.observed_returns == () and result.missing_keys == ()
    assert result.seal is seal and result.seal.eligible_keys == KEYS
    assert result.historical_decision_time_availability == "not_observed"


def test_latest112_inference_reads_exactly_prior51_through111_no_price_graft(plan, bars):
    calls = []
    seal = build(plan, bars, entry=112, sequence=True, calls=calls)
    expected_days = plan.sessions[51:112]
    assert calls == [(key, day) for key in KEYS for day in expected_days]
    assert len(expected_days) == 61 and expected_days[-1] == plan.sessions[111]
    assert all(day != plan.sessions[112] for _, day in calls)
    # Even every entry quote being absent cannot affect this past-only seal.
    changed = bars.copy()
    for key in KEYS:
        changed[key, plan.sessions[112]] = None
    assert build(plan, changed, entry=112, sequence=True) == seal
    assert all(len(seq) == 20 and all(len(step) == 2 for step in seq) for seq in seal.sequences)
    result = k.target_labels(seal, lambda *args: pytest.fail("no label callback"))
    with pytest.raises(FrozenInstanceError):
        result.seal.entry_index = 107


def test_unknown_horizon_not_falsely_reported_as_missing_peer_quote(plan, bars):
    panel = bars.copy()
    panel[KEYS[-1], plan.sessions[111]] = None
    seal = build(plan, panel, entry=112)
    assert seal.unavailable_keys == (KEYS[-1],)
    result = k.target_labels(seal, lambda *args: pytest.fail("quote read"))
    assert result.unavailable_reason == "target_horizon_not_in_calendar"
    assert result.seal.eligible_keys == KEYS[:-1] and result.missing_keys == ()
    with pytest.raises(ValueError, match="unknown_horizon"):
        replace(result, observed_returns=((KEYS[0], Fraction(0)),))
    with pytest.raises(ValueError, match="unknown_horizon"):
        replace(result, missing_keys=(KEYS[0],))


def test_demeaning_uses_only_frozen_decision_eligible_cohort_not_all128(plan, bars):
    seal = build(plan, bars, eligible=KEYS[:3], sequence=True)
    raw = [
        (
            math.fsum(row.sequence[-i][1] for i in range(1, 6)) / 5,
            math.fsum(step[1] for step in row.sequence) / 20,
            math.fsum(step[0] for step in row.sequence) / 20,
        )
        for row in seal.rows
    ]
    means = [math.fsum(row[j] / 3 for row in raw) for j in range(3)]
    assert [row.values[:3] for row in seal.rows] == [
        tuple(row[j] - means[j] for j in range(3)) for row in raw
    ]
    assert seal.unavailable_keys == KEYS[3:]


def test_all_future_perturbations_leave_features_identity_eligibility_unchanged(plan, bars):
    baseline = build(plan, bars, sequence=True)
    mutated = {key: value for key, value in bars.items() if key[1] < plan.sessions[61]}
    for key in KEYS:
        for day in plan.sessions[61:]:
            mutated[key, day] = None
    assert build(plan, mutated, sequence=True) == baseline


@pytest.mark.parametrize("fault", ["missing", "incomplete", "M1", "wrong_date", "identity", "wide"])
def test_one_bad_prior_bar_excludes_only_its_key_never_counts_substitute61(plan, bars, fault):
    panel = bars.copy()
    key, day = KEYS[0], plan.sessions[30]
    original = panel[key, day]
    value = None
    if fault == "incomplete":
        value = replace(original, complete=False)
    elif fault == "M1":
        value = replace(original, timeframe=Timeframe.M1)
    elif fault == "wrong_date":
        value = replace(original, start_ts=original.start_ts + timedelta(days=1))
    elif fault == "identity":
        value = replace(original, symbol="OTHER")
    elif fault == "wide":
        value = replace(original, high=original.high * 3)
    panel[key, day] = value
    seal = build(plan, panel)
    assert seal.eligible_keys == KEYS[1:] and seal.unavailable_keys == KEYS[:1]
    calls = []
    result = k.target_labels(seal, quotes(seal, calls=calls))
    assert result.values is not None and len(calls) == 127 * 2
    assert all(key != KEYS[0] for key, _ in calls)


def test_target_after_identity_seal_exact_all_peers_simple_not_log_returns(plan, bars):
    seal = build(plan, bars)
    calls = []
    result = k.target_labels(seal, quotes(seal, calls=calls))
    assert len(calls) == 256
    assert calls == [(key, day) for key in KEYS for day in (seal.entry_session, seal.exit_session)]
    assert result.observed_returns == tuple((key, Fraction(j, 100)) for j, key in enumerate(KEYS))
    assert result.values == tuple(float(Fraction(j, 100) - Fraction(127, 200)) for j in range(128))
    assert abs(math.fsum(result.values)) < 1e-12
    assert result.available_at == seal.exit_open_at
    assert result.historical_decision_time_availability == "not_observed"


def test_target_unrounded_open_quotes_and_inputs_unmodified(plan, bars):
    seal = build(plan, bars, eligible=KEYS[:2])
    entry0 = quotes(seal)(KEYS[0], seal.entry_session)
    exit0 = replace(quotes(seal)(KEYS[0], seal.exit_session), price=Decimal("100.005"))
    faults = {(KEYS[0], seal.entry_session): entry0, (KEYS[0], seal.exit_session): exit0}
    original = faults.copy()
    result = k.target_labels(seal, quotes(seal, faults=faults))
    assert result.observed_returns[0][1] == Fraction(1, 20000)
    assert result.values == (
        float(Fraction(1, 20000) / 2 - Fraction(1, 100) / 2),
        float(Fraction(1, 100) / 2 - Fraction(1, 20000) / 2),
    )
    assert faults == original


def test_target_numeric_overflow_invalidates_date_without_replacement_peer(plan, bars):
    seal = build(plan, bars)
    quote = replace(quotes(seal)(KEYS[-1], seal.exit_session), price=Decimal("1e1000"))
    result = k.target_labels(seal, quotes(seal, faults={(KEYS[-1], seal.exit_session): quote}))
    assert result.values is None and result.missing_keys == (KEYS[-1],)


@pytest.mark.parametrize("key", [KEYS[0], KEYS[-1]])
@pytest.mark.parametrize("field", ["entry", "exit"])
def test_missing_selected_or_nonselected_peer_invalidates_entire_date(plan, bars, key, field):
    seal = build(plan, bars)
    day = seal.entry_session if field == "entry" else seal.exit_session
    calls = []
    result = k.target_labels(seal, quotes(seal, faults={(key, day): None}, calls=calls))
    assert result.missing_keys == (key,) and result.values is None
    assert result.unavailable_reason == "target_peer_unavailable"
    assert len(result.observed_returns) == 127 and len(calls) == 256
    assert result.seal is seal and result.seal.eligible_keys == KEYS


@pytest.mark.parametrize(
    "fault",
    [
        "zero",
        "negative",
        "NaN",
        "inf",
        "bool",
        "complex",
        "floatnan",
        "symbol",
        "market",
        "date",
        "second",
        "naive",
        "clock_type",
    ],
)
def test_invalid_target_quote_whole_date_not_peer_filter(plan, bars, fault):
    seal = build(plan, bars)
    key, day = KEYS[-1], seal.exit_session
    quote = quotes(seal)(key, day)
    prices = {
        "zero": Decimal(0),
        "negative": Decimal(-1),
        "NaN": Decimal("NaN"),
        "inf": Decimal("Infinity"),
        "bool": True,
        "complex": 1 + 2j,
        "floatnan": float("nan"),
    }
    if fault in prices:
        quote = replace(quote, price=prices[fault])
    elif fault == "symbol":
        quote = replace(quote, symbol="DIFFERENT")
    elif fault == "market":
        quote = replace(quote, market="DIFFERENT")
    elif fault == "date":
        quote = replace(quote, session=day + timedelta(days=1))
    elif fault == "second":
        quote = replace(quote, open_at=quote.open_at + timedelta(seconds=1))
    elif fault == "naive":
        quote = replace(quote, open_at=quote.open_at.replace(tzinfo=None))
    else:
        quote = replace(quote, open_at=None)
    result = k.target_labels(seal, quotes(seal, faults={(key, day): quote}))
    assert result.values is None and result.missing_keys == (key,)


def test_empty_eligible_no_labels_no_target_calls(plan, bars):
    seal = build(plan, bars, eligible=())
    assert seal.rows == () and seal.unavailable_keys == KEYS
    assert k.target_labels(seal, lambda *args: pytest.fail("empty target read")).values is None


def test_ties_and_fewer10_still_exact_frozen_peer_targets_no_policy_selection(plan, bars):
    seal = build(plan, bars, eligible=KEYS[:3])

    def source(key, day):
        row = next(row for row in seal.rows if row.key == key)
        return k.OpenQuote(
            row.symbol,
            row.market,
            day,
            seal.entry_open_at if day == seal.entry_session else seal.exit_open_at,
            Decimal("100"),
        )

    result = k.target_labels(seal, source)
    assert result.values == (0.0,) * 3 and seal.eligible_keys == KEYS[:3]
    assert not hasattr(result, "selected_keys")


def test_unsealed_target_request_rejected_before_any_callback():
    with pytest.raises(ValueError, match="seal"):
        k.target_labels(None, lambda *args: pytest.fail("unsealed target read"))


def test_inputs_state_immutable_and_forged_partial_target_rejected(plan, bars):
    original = bars.copy()
    seal = build(plan, bars, sequence=True)
    result = k.target_labels(seal, quotes(seal))
    assert bars == original
    with pytest.raises(FrozenInstanceError):
        seal.entry_index = 62
    with pytest.raises(FrozenInstanceError):
        seal.rows[0].values = ()
    with pytest.raises(ValueError):
        replace(seal, rows=seal.rows[:-1])
    with pytest.raises(ValueError):
        replace(result, observed_returns=result.observed_returns[:-1])
    with pytest.raises(ValueError):
        replace(result, missing_keys=(KEYS[0],))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 1 + 2j, True])
def test_row_nonfinite_complex_bool_rejected(plan, bars, bad):
    row = build(plan, bars).rows[0]
    with pytest.raises(ValueError):
        replace(row, values=(bad, *row.values[1:]))


def test_kernel_has_no_io_fit_model_order_or_network_surface(plan, bars, monkeypatch):
    tree = ast.parse(Path(k.__file__).read_text(encoding="utf-8"))
    forbidden = {
        "open",
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "fit",
        "predict",
        "OrderIntent",
        "torch",
        "requests",
        "socket",
        "subprocess",
    }
    assert not any(isinstance(node, ast.Name) and node.id in forbidden for node in ast.walk(tree))
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in forbidden for node in ast.walk(tree)
    )
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: pytest.fail("file I/O"))
    seal = build(plan, bars)
    assert k.target_labels(seal, quotes(seal)).values is not None
