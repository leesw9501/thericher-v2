from __future__ import annotations

import builtins
import itertools
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time
from decimal import Decimal, localcontext
from fractions import Fraction
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.research import cross_asset_monthly_momentum as study
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import (
    INSTRUMENT_ORDER,
    CrossAssetAdjustedRow,
    CrossAssetInputUnavailable,
    CrossAssetSession,
)

D = Decimal
VINTAGE = "synthetic-raw-vintage"
ENTRY = date(2024, 3, 1)
ANCHOR = date(2023, 2, 28)
DECISION = date(2024, 2, 29)
EASTERN = ZoneInfo("America/New_York")


def session(day, close_hour=16):
    opening = datetime.combine(day, time(9, 30), EASTERN).astimezone(UTC)
    closing = datetime.combine(day, time(close_hour), EASTERN).astimezone(UTC)
    return CrossAssetSession(day, opening, closing)


def calendar():
    # Synthetic frozen schedules are supplied, never inferred from observed rows.
    return tuple(map(session, (date(2023, 2, 27), ANCHOR, date(2023, 3, 1),
                               date(2024, 2, 28), DECISION, ENTRY, date(2024, 3, 4))))


def rows(currents=("120", "80", "100"), anchor=ANCHOR, decision=DECISION):
    return {symbol: (study.PriceClose(symbol, anchor, VINTAGE, D(100)),
                     study.PriceClose(symbol, decision, VINTAGE, D(value)))
            for symbol, value in zip(INSTRUMENT_ORDER, currents, strict=True)}


def build(source=None, schedule=None, entry=ENTRY, decision_at=None):
    schedule = calendar() if schedule is None else schedule
    return study.build_monthly_momentum(
        rows() if source is None else source,
        scheduled_sessions=schedule,
        entry_session_date=entry,
        decision_at=session(DECISION).close_at if decision_at is None else decision_at,
        vintage_ref=VINTAGE,
    )


@pytest.mark.parametrize("day,expected", [
    (date(2024, 2, 29), date(2023, 2, 28)),
    (date(2025, 2, 28), date(2024, 2, 28)),
    (date(2024, 3, 28), date(2023, 3, 28)),
    (date(2024, 12, 31), date(2023, 12, 31)),
])
def test_exact_calendar_year_cutoff(day, expected):
    assert study.previous_year_cutoff(day) == expected


def test_leap_anchor_is_required_exactly_and_not_prior_march_month_end():
    result = build()
    assert result.plan.anchor_session_date == ANCHOR
    assert result.plan.previous_year_cutoff == ANCHOR
    assert result.plan.decision_at == session(DECISION).close_at
    assert result.plan.entry_at == session(ENTRY).open_at
    assert result.price_momentum == (D(".2"), D("-.2"), D(0))


@pytest.mark.parametrize("decision,entry,past,expected", [
    (date(2024, 3, 28), date(2024, 4, 1),
     (date(2023, 3, 27), date(2023, 3, 28), date(2023, 3, 31)), date(2023, 3, 28)),
    (date(2024, 12, 31), date(2025, 1, 2),
     (date(2023, 12, 28), date(2023, 12, 29), date(2024, 1, 2)), date(2023, 12, 29)),
])
def test_calendar_anchor_precedes_exact_cutoff_not_observed_or_month_end(
    decision, entry, past, expected,
):
    schedule = tuple(map(session, (*past, decision, entry)))
    result = study.plan_monthly_momentum(
        schedule, entry_session_date=entry, decision_at=session(decision).close_at,
    )
    assert result.anchor_session_date == expected
    assert result.previous_year_cutoff == study.previous_year_cutoff(decision)


def test_early_close_and_dst_use_actual_caller_schedule():
    decision, entry = date(2024, 11, 29), date(2024, 12, 2)
    schedule = (session(date(2023, 11, 29)), session(decision, 13), session(entry))
    result = study.plan_monthly_momentum(
        schedule, entry_session_date=entry, decision_at=schedule[1].close_at,
    )
    assert result.decision_at.hour == 18
    assert result.entry_at.hour == 14 and result.entry_at.minute == 30
    with pytest.raises(CrossAssetInputUnavailable, match="decision_not_previous_close"):
        study.plan_monthly_momentum(
            schedule, entry_session_date=entry, decision_at=session(decision).close_at,
        )
    assert session(date(2024, 3, 8)).open_at.hour == 14
    assert session(date(2024, 3, 11)).open_at.hour == 13


@pytest.mark.parametrize("case,reason", [
    ("same_month", "entry_not_next_month_first_session"),
    ("skip_month", "entry_not_next_month_first_session"),
    ("missing_entry", "entry_session_missing"),
    ("missing_anchor", "scheduled_year_history_missing"),
    ("first_entry", "previous_close_missing"),
    ("disorder", "calendar_order_invalid"),
    ("nonutc_decision", "decision_not_previous_close"),
])
def test_invalid_calendar_or_decision_is_categorical(case, reason):
    schedule, entry, decision_at = calendar(), ENTRY, session(DECISION).close_at
    if case == "same_month":
        entry, decision_at = date(2024, 3, 4), session(ENTRY).close_at
    elif case == "skip_month":
        entry = date(2024, 4, 1)
        schedule = (*schedule[:-2], session(entry))
    elif case == "missing_entry":
        entry = date(2024, 3, 5)
    elif case == "missing_anchor":
        schedule = schedule[3:]
    elif case == "first_entry":
        entry = schedule[0].session_date
    elif case == "disorder":
        schedule = tuple(reversed(schedule))
    else:
        decision_at = decision_at.astimezone(EASTERN)
    with pytest.raises(CrossAssetInputUnavailable, match=reason):
        study.plan_monthly_momentum(schedule, entry_session_date=entry, decision_at=decision_at)


@pytest.mark.parametrize("active", list(itertools.product((False, True), repeat=3)))
def test_all_sleeve_combinations_equal_thirds_residual_cash_no_renormalization(active):
    result = build(rows(tuple("101" if value else "100" for value in active)))
    assert result.target.weights3 == tuple(study.THIRD if value else D(0) for value in active)
    assert sum(map(Fraction, result.target.weights3), Fraction(0)) \
        + Fraction(result.target.cash_weight) == 1
    with localcontext(study.DECIMAL_CONTEXT):
        assert result.target.cash_weight == 1 - sum(result.target.weights3)
    if all(active):
        assert result.target.cash_weight == D("1e-45")
    assert nav.SYMBOLS == ("SPY", "QQQ", "IWM")


def test_tiny_positive_and_hostile_decimal_context_preserve_exact_sign_and_weights():
    source = rows(("100.000000000000000000000000000000000000000001", "99", "100"))
    expected = build(source)
    with localcontext() as context:
        context.prec = 6
        assert build(source) == expected
        assert context.prec == 6
    assert expected.price_momentum[0] > 0
    assert expected.target.weights3 == (study.THIRD, D(0), D(0))


@pytest.mark.parametrize(
    "symbol,day", list(itertools.product(INSTRUMENT_ORDER, (ANCHOR, DECISION))),
)
def test_required_gap_never_substitutes_older_observation_or_means_negative(symbol, day):
    source = rows()
    source[symbol] = tuple(row for row in source[symbol] if row.session_date != day) + (
        study.PriceClose(symbol, date(2023, 2, 27), VINTAGE, D("77")),
        study.PriceClose(symbol, date(2024, 2, 28), VINTAGE, D("88")),
    )
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        build(source)


def test_outside_rows_future_marks_and_future_missing_support_do_not_change_signal():
    class PoisonOutside:
        def __init__(self, day):
            self.session_date = day

        @property
        def close(self):
            raise AssertionError("outside price read")

        @property
        def vintage_ref(self):
            raise AssertionError("outside vintage read")

    expected = build()
    source = rows()
    for symbol in INSTRUMENT_ORDER:
        source[symbol] = (*source[symbol], PoisonOutside(date(2023, 2, 27)),
                          PoisonOutside(ENTRY), PoisonOutside(date(2024, 3, 4)))
    assert build(source) == expected
    mutated = {symbol: (*value[:2], study.PriceClose(symbol, ENTRY, "future-other", D("987654")))
               for symbol, value in source.items()}
    assert build(mutated) == expected
    assert build({symbol: tuple(reversed(value)) for symbol, value in rows().items()}) == expected
    assert build(dict(reversed(tuple(rows().items())))) == expected


@pytest.mark.parametrize("case,reason", [
    ("duplicate", "required_session_duplicate"),
    ("wrong_symbol", "required_row_symbol_mismatch"),
    ("wrong_vintage", "required_vintage_mismatch"),
    ("adjusted_row", "required_row_type_invalid"),
    ("invalid_close", "price_close_invalid"),
])
def test_exact_required_row_binding_rejects_invalid_support(case, reason):
    source = rows()
    anchor, current = source["SPY"]
    if case == "duplicate":
        source["SPY"] += (anchor,)
    elif case == "wrong_symbol":
        source["SPY"] = (replace(anchor, symbol="TLT"), current)
    elif case == "wrong_vintage":
        source["SPY"] = (replace(anchor, vintage_ref="another"), current)
    elif case == "adjusted_row":
        adjusted = CrossAssetAdjustedRow("SPY", ANCHOR, VINTAGE, D(100), D(100), D(100), D(100))
        source["SPY"] = (adjusted, current)
    else:
        poisoned = replace(anchor)
        object.__setattr__(poisoned, "close", D("NaN"))
        source["SPY"] = (poisoned, current)
    with pytest.raises(CrossAssetInputUnavailable, match=reason):
        build(source)


def test_explicit_raw_basis_privacy_immutability_and_source_isolation(monkeypatch):
    source = rows()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unexpected IO")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    result = build(source)
    assert source["SPY"][0].price_basis == "kis_modp0_raw"
    facts = result.safe_facts()
    assert facts["price_basis"] == "kis_modp0_raw"
    assert facts["splits_and_dividends"] == "not_applied"
    assert facts["publication_availability"] == "not_observed"
    assert facts["paper_input"] is False
    assert all(not isinstance(value, Decimal) for value in facts.values())
    assert VINTAGE not in repr(facts) + repr(result) + repr(source["SPY"][0])
    assert "120" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.vintage_ref = "changed"
    with pytest.raises(CrossAssetInputUnavailable, match="price_basis_invalid"):
        replace(source["SPY"][0], price_basis="adjusted")


def test_monthly_keys_exact_missing_is_not_carry_and_no_daily_repeat():
    signal = build()
    targets = study.monthly_targets((signal,), expected_entry_dates=(ENTRY,))
    assert tuple(targets) == (ENTRY,)
    assert targets[ENTRY] == signal.target
    with pytest.raises(TypeError):
        targets[date(2024, 3, 4)] = signal.target
    with pytest.raises(CrossAssetInputUnavailable, match="monthly_signal_missing_or_extra"):
        study.monthly_targets((), expected_entry_dates=(ENTRY,))
    with pytest.raises(CrossAssetInputUnavailable, match="monthly_signal_missing_or_extra"):
        study.monthly_targets((signal,), expected_entry_dates=(ENTRY, date(2024, 4, 1)))
    with pytest.raises(CrossAssetInputUnavailable, match="monthly_signal_duplicate"):
        study.monthly_targets((signal, signal), expected_entry_dates=(ENTRY,))
    with pytest.raises(CrossAssetInputUnavailable, match="monthly_keys_invalid"):
        study.monthly_targets((signal,), expected_entry_dates=(ENTRY, date(2024, 3, 4)))


@pytest.mark.parametrize("weights,cash", [
    ((D(0), D(0), D(0)), D(1)),
    ((D(1), D(0), D(0)), D(0)),
])
def test_signal_constructor_cannot_forge_different_rule_target(weights, cash):
    signal = build()
    with pytest.raises(CrossAssetInputUnavailable, match="signal_target_mismatch"):
        replace(signal, target=nav.ThreeAssetTarget(weights, cash))


def test_monthly_publication_rejects_mixed_vintage():
    first = build()
    april, decision = date(2024, 4, 1), date(2024, 3, 28)
    schedule = tuple(map(session, (date(2023, 3, 28), date(2023, 3, 31), decision, april)))
    second = build(rows(("120", "80", "100"), date(2023, 3, 28), decision),
                   schedule, april, session(decision).close_at)
    with pytest.raises(CrossAssetInputUnavailable, match="monthly_vintage_mismatch"):
        study.monthly_targets((first, replace(second, vintage_ref="different-vintage")),
                              expected_entry_dates=(ENTRY, april))


def test_shared_positional_nav_carry_fees_and_raw_price_scale_invariance():
    signal = build()
    targets = study.monthly_targets((signal,), expected_entry_dates=(ENTRY,))
    # Positional arithmetic only: no adjusted-source record or source-grade relabeling.
    days = (
        nav.ThreeAssetDay(ENTRY, (D(100), D(100), D(100)), (D(110), D(100), D(100))),
        nav.ThreeAssetDay(date(2024, 3, 4), (D(110), D(100), D(100)),
                          (D(120), D(100), D(100))),
        nav.ThreeAssetDay(date(2024, 3, 5), (D(120), D(100), D(100)),
                          (D(130), D(100), D(100))),
    )
    result = nav.replay(days, targets, D(5))
    with localcontext(study.DECIMAL_CONTEXT):
        fee = D(5) / 10000
        bought = study.THIRD / (1 + fee * study.THIRD)
        quantity = bought / 100
        cash = 1 - bought - fee * bought
        expected = (cash + quantity * 110, cash + quantity * 120,
                    cash + quantity * 130 * (1 - fee))
        assert all(abs(a - b) < D("1e-45")
                   for a, b in zip(result.navs, expected, strict=True))
        assert abs(result.total_fees - fee * (bought + quantity * 130)) < D("1e-45")
        scaled = tuple(nav.ThreeAssetDay(day.date,
                                        tuple(p * f for p, f in zip(day.adj_open3, (2, 3, 5),
                                                                    strict=True)),
                                        tuple(p * f for p, f in zip(day.adj_close3, (2, 3, 5),
                                                                    strict=True))) for day in days)
    assert result.daily[1].fees == 0
    assert result.daily[-1].flat is True
    scaled_result = nav.replay(scaled, targets, D(5))
    with localcontext(study.DECIMAL_CONTEXT):
        assert all(abs(a - b) < D("1e-45")
                   for a, b in zip(result.navs, scaled_result.navs, strict=True))
    assert nav.replay(days, targets, D(5)) == result
    changed_payoff = (*days[:-1], replace(days[-1], adj_close3=(D(70), D(100), D(100))))
    assert nav.replay(changed_payoff, targets, D(5)).final_nav != result.final_nav
    assert build() == signal


def test_same_monthly_target_rebalances_drift_not_capital_reset():
    first = build()
    april = date(2024, 4, 1)
    march_close = date(2024, 3, 28)
    schedule = tuple(map(session, (date(2023, 3, 28), date(2023, 3, 31), march_close, april)))
    second = build(rows(("120", "80", "100"), date(2023, 3, 28), march_close),
                   schedule, april, session(march_close).close_at)
    assert second.target == first.target
    targets = study.monthly_targets((second, first), expected_entry_dates=(ENTRY, april))
    days = (
        nav.ThreeAssetDay(ENTRY, (D(100),) * 3, (D(110), D(100), D(100))),
        nav.ThreeAssetDay(march_close, (D(110), D(100), D(100)),
                          (D(200), D(100), D(100))),
        nav.ThreeAssetDay(april, (D(200), D(100), D(100)), (D(200), D(100), D(100))),
        nav.ThreeAssetDay(date(2024, 4, 2), (D(200), D(100), D(100)),
                          (D(200), D(100), D(100))),
    )
    result = nav.replay(days, targets, D(5))
    assert result.daily[2].fees > 0
    assert result.daily[2].nav < result.daily[1].nav
    assert result.daily[2].nav > 1
    carry_only = nav.replay(days, {ENTRY: first.target}, D(5))
    assert carry_only.daily[2].fees == 0
    assert carry_only.daily[2].nav == carry_only.daily[1].nav


def test_required_numeric_range_is_categorical_not_raw_price_output():
    source = rows()
    source["SPY"] = (study.PriceClose("SPY", ANCHOR, VINTAGE, D("1e-999999")),
                     study.PriceClose("SPY", DECISION, VINTAGE, D("1e999999")))
    with pytest.raises(CrossAssetInputUnavailable, match="numeric_range") as caught:
        build(source)
    assert caught.value.safe_facts() == {"status": "input_unavailable",
                                         "reason_code": "numeric_range"}
