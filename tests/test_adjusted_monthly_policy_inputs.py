"""Synthetic-only causal monthly input and realized-label separation checks."""

import builtins
import io
import os
import socket
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, localcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.data import tiingo_adjusted_etf_daily as data
from thericher_v2.research import adjusted_monthly_policy_inputs as s


@pytest.fixture(autouse=True)
def precise_test_arithmetic():
    with localcontext() as context:
        context.prec = 50
        yield


@pytest.fixture
def sample():
    holidays = {date(2012, 7, 4), date(2012, 11, 22), date(2012, 12, 25), date(2013, 1, 1)}
    current, dates = date(2000, 1, 3), []
    while current <= date(2013, 3, 1):
        if current.weekday() < 5 and current not in holidays:
            dates.append(current)
        current += timedelta(days=1)
    calendar = tuple(dates)
    rows = []
    previous = Decimal(100)
    for i, d in enumerate(calendar):
        opening = previous + Decimal(i % 5 - 2) / 10
        closing = Decimal(100) + Decimal(i) / 100 + Decimal(i % 9 - 4) / 10
        rows.append(
            data.AdjustedEtfRow(
                "SPY", d, opening, max(opening, closing) + 1, min(opening, closing) - 1, closing
            )
        )
        previous = closing
    return SimpleNamespace(calendar=calendar, rows=tuple(rows))


def bounds(p, year=2013, month=1):
    indices = [i for i, d in enumerate(p.calendar) if (d.year, d.month) == (year, month)]
    return indices[0], indices[-1] + 1


def build(p, *, rows=None, calendar=None, month_bounds=None, symbol="SPY"):
    return s.build_adjusted_monthly_policy_inputs(
        p.rows if rows is None else rows,
        symbol=symbol,
        calendar=p.calendar if calendar is None else calendar,
        month_bounds=bounds(p) if month_bounds is None else month_bounds,
    )


def change_close(row, closing):
    return replace(
        row,
        adj_close=closing,
        adj_high=max(row.adj_open, closing) + 1,
        adj_low=min(row.adj_open, closing) / 2,
    )


def test_exact253_prior_closes252_signed_returns_no_own_marks_in_model(sample):
    result = build(sample)
    start, stop = bounds(sample)
    expected_dates = sample.calendar[start - 253 : start]
    assert result.model.context_dates == expected_dates
    assert result.model.return_dates == expected_dates[1:]
    assert len(result.model.close_returns_bps) == 252
    assert result.model.source_date == sample.calendar[start - 1]
    assert result.identity.source_date == result.model.source_date < result.identity.decision_date
    assert result.identity.cohort_dates == sample.calendar[start - 253 : stop]
    with localcontext() as context:
        context.prec = 50
        expected = tuple(
            10000 * (b.adj_close / a.adj_close - 1)
            for a, b in zip(
                sample.rows[start - 253 : start - 1], sample.rows[start - 252 : start], strict=True
            )
        )
    assert result.model.close_returns_bps == expected
    assert any(v > 0 for v in expected) and any(v < 0 for v in expected)
    assert {f.name for f in fields(result.model)} == {"context_dates", "close_returns_bps"}
    assert all(d < result.identity.decision_date for d in result.model.context_dates)


def test_exact_history_boundary_accept253_reject252_and_ignore_older_rows(sample):
    start, stop = bounds(sample)
    calendar = sample.calendar[start - 253 :]
    exact = build(
        sample,
        calendar=calendar,
        month_bounds=(253, stop - start + 253),
        rows=sample.rows[start - 253 : stop],
    )
    assert exact.model == build(sample).model
    with pytest.raises(ValueError, match="month_bounds"):
        build(
            sample, calendar=sample.calendar[start - 252 :], month_bounds=(252, stop - start + 252)
        )
    old = change_close(sample.rows[start - 254], Decimal("100000"))
    rows = sample.rows[: start - 254] + (old,) + sample.rows[start - 253 :]
    assert build(sample, rows=rows) == build(sample)


def test_payoff_ratios_daily_targets_final_close_and_no_next_open_needed(sample):
    start, stop = bounds(sample, 2012, 12)
    result = build(sample, month_bounds=(start, stop), rows=sample.rows[:stop])
    assert result.identity.decision_date.year == result.identity.source_date.year == 2012
    assert result.payoff.target_dates == sample.calendar[start:stop]
    assert result.payoff.target_dates[-1] == date(2012, 12, 31)
    assert all(d.year == 2012 for d in result.payoff.target_dates)
    with localcontext() as context:
        context.prec = 50
        opening = sample.rows[start].adj_open
        assert result.payoff.open_over_previous_close == opening / sample.rows[start - 1].adj_close
        assert result.payoff.close_over_entry_open == tuple(
            r.adj_close / opening for r in sample.rows[start:stop]
        )
    assert result.payoff.final_close_growth == result.payoff.close_over_entry_open[-1]
    assert len(result.payoff.close_over_entry_open) == stop - start
    assert all(d < date(2013, 1, 1) for d in result.identity.cohort_dates)


@pytest.mark.parametrize("location", ["first_own_close", "last_own_close", "future_month"])
def test_future_payoff_mutation_never_changes_current_or_prior_model(sample, location):
    original = build(sample)
    start, stop = bounds(sample)
    j = (
        start
        if location == "first_own_close"
        else stop - 1
        if location == "last_own_close"
        else stop
    )
    rows = (
        sample.rows[:j]
        + (change_close(sample.rows[j], Decimal("987.654321")),)
        + sample.rows[j + 1 :]
    )
    modified = build(sample, rows=rows)
    assert modified.model == original.model and modified.identity == original.identity
    if location == "future_month":
        assert modified.payoff == original.payoff
    else:
        assert modified.payoff != original.payoff
        offset = j - start
        assert (
            modified.payoff.close_over_entry_open[:offset]
            == original.payoff.close_over_entry_open[:offset]
        )
    earlier = bounds(sample, 2012, 12)
    assert build(sample, rows=rows, month_bounds=earlier) == build(sample, month_bounds=earlier)


def test_own_open_changes_gap_growth_but_no_model_feature(sample):
    start, _ = bounds(sample)
    original = build(sample)
    row = sample.rows[start]
    opening = row.adj_open * 2
    row = replace(row, adj_open=opening, adj_high=max(opening, row.adj_close) + 1)
    modified = build(sample, rows=sample.rows[:start] + (row,) + sample.rows[start + 1 :])
    assert modified.model == original.model and modified.identity == original.identity
    assert modified.payoff.open_over_previous_close == original.payoff.open_over_previous_close * 2
    assert modified.payoff.close_over_entry_open != original.payoff.close_over_entry_open
    with localcontext() as context:
        context.prec = 50
        for a, b in zip(
            original.payoff.close_over_entry_open,
            modified.payoff.close_over_entry_open,
            strict=True,
        ):
            assert abs(a - 2 * b) < Decimal("1e-48")


@pytest.mark.parametrize("scale", ["0.00001", "100000"])
def test_global_adjusted_price_scale_invariance(sample, scale):
    rows = tuple(
        replace(
            r,
            **{
                k: getattr(r, k) * Decimal(scale)
                for k in ("adj_open", "adj_high", "adj_low", "adj_close")
            },
        )
        for r in sample.rows
    )
    assert build(sample, rows=rows) == build(sample)


def test_numeric_contract_independent_of_ambient_decimal_context(sample):
    original = build(sample)
    with localcontext() as context:
        context.prec, context.rounding = 12, ROUND_DOWN
        assert build(sample) == original


@pytest.mark.parametrize("year,month", [(2012, 3), (2012, 7), (2012, 11), (2013, 1)])
def test_complete_month_date_only_holiday_dst_boundaries(sample, year, month):
    result = build(sample, month_bounds=bounds(sample, year, month))
    assert all(type(d) is date for d in result.payoff.target_dates + result.model.context_dates)
    assert all((d.year, d.month) == (year, month) for d in result.payoff.target_dates)
    if month == 3:
        assert date(2012, 3, 9) in result.payoff.target_dates
        assert date(2012, 3, 12) in result.payoff.target_dates
    if month == 7:
        assert date(2012, 7, 4) not in result.payoff.target_dates
    if month == 1:
        assert result.identity.decision_date == date(2013, 1, 2)


@pytest.mark.parametrize(
    "where",
    [
        "context_first",
        "context_interior",
        "context_last",
        "target_first",
        "target_interior",
        "target_last",
    ],
)
def test_missing_exact_required_date_no_shift_or_backfill(sample, where):
    start, stop = bounds(sample)
    indices = {
        "context_first": start - 253,
        "context_interior": start - 100,
        "context_last": start - 1,
        "target_first": start,
        "target_interior": start + 4,
        "target_last": stop - 1,
    }
    j = indices[where]
    rows = sample.rows[:j] + sample.rows[j + 1 :]
    with pytest.raises(ValueError, match="missing_required_session"):
        build(sample, rows=rows)


@pytest.mark.parametrize(
    "bad",
    [
        "first",
        "last",
        "multiple_months",
        "calendar_tail",
        "bool",
        "negative",
        "mutable",
        "short",
        "order",
        "duplicate",
        "datetime",
    ],
)
def test_invalid_calendar_and_partial_month_rejected(sample, bad):
    start, stop = bounds(sample)
    calendar, requested = sample.calendar, (start, stop)
    if bad == "first":
        requested = (start + 1, stop)
    if bad == "last":
        requested = (start, stop - 1)
    if bad == "multiple_months":
        requested = (start, stop + 1)
    if bad == "calendar_tail":
        calendar = calendar[: stop - 1]
        requested = (start, stop - 1)
    if bad == "bool":
        requested = (True, stop)
    if bad == "negative":
        requested = (-1, stop)
    if bad == "mutable":
        calendar = list(calendar)
    if bad == "short":
        calendar = calendar[:2]
    if bad == "order":
        calendar = calendar[::-1]
    if bad == "duplicate":
        calendar = calendar[:start] + (calendar[start],) + calendar[start:]
    if bad == "datetime":
        calendar = (datetime(2000, 1, 3),) + calendar[1:]
    with pytest.raises(ValueError):
        build(sample, calendar=calendar, month_bounds=requested)


@pytest.mark.parametrize("symbol", ["SPY", "QQQ", "IWM"])
def test_one_explicit_symbol_only_no_cross_symbol_mix(sample, symbol):
    rows = tuple(replace(r, symbol=symbol) for r in sample.rows)
    assert build(sample, rows=rows, symbol=symbol).identity.symbol == symbol
    if symbol != "SPY":
        with pytest.raises(ValueError, match="source_identity"):
            build(sample, rows=rows)


@pytest.mark.parametrize(
    "bad", ["duplicate", "reverse", "wrong_symbol", "fake", "mutable", "unknown"]
)
def test_source_identity_order_and_fake_row_injection_blocked(sample, bad):
    rows, symbol = sample.rows, "SPY"
    if bad == "duplicate":
        rows = (rows[0],) + rows
    if bad == "reverse":
        rows = rows[::-1]
    if bad == "wrong_symbol":
        rows = (replace(rows[0], symbol="QQQ"),) + rows[1:]
    if bad == "fake":
        rows = (
            SimpleNamespace(
                symbol="SPY",
                session_date=rows[0].session_date,
                adj_open=Decimal(1),
                adj_close=Decimal(2),
                future=Decimal(999),
            ),
        ) + rows[1:]
    if bad == "mutable":
        rows = list(rows)
    if bad == "unknown":
        symbol = "FAKE"
    with pytest.raises(ValueError):
        build(sample, rows=rows, symbol=symbol)


@pytest.mark.parametrize(
    "field,value",
    [
        ("adj_close", Decimal("NaN")),
        ("adj_open", Decimal("Infinity")),
        ("adj_low", Decimal(0)),
        ("adj_high", Decimal(-1)),
        ("adj_close", 123.4),
        ("adj_high", Decimal("0.1")),
        ("adj_low", Decimal("1000000")),
    ],
)
def test_invalid_required_marks_rejected_even_forged_frozen_row(sample, field, value):
    start, _ = bounds(sample)
    row = replace(sample.rows[start - 5])
    object.__setattr__(row, field, value)
    rows = sample.rows[: start - 5] + (row,) + sample.rows[start - 4 :]
    with pytest.raises(ValueError, match="invalid_required_marks"):
        build(sample, rows=rows)


def test_unrequested_future_numeric_marks_not_read_or_used(sample):
    _, stop = bounds(sample)
    row = replace(sample.rows[stop])
    object.__setattr__(row, "adj_close", Decimal("NaN"))
    assert build(sample, rows=sample.rows[:stop] + (row,) + sample.rows[stop + 1 :]) == build(
        sample
    )


def test_immutable_records_repr_hidden_numeric_and_feature_injection_blocked(sample):
    result = build(sample)
    for record, attr, value in (
        (result, "model", result.model),
        (result.model, "close_returns_bps", (Decimal(999),)),
        (result.payoff, "open_over_previous_close", Decimal(999)),
        (result.identity, "symbol", "QQQ"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(record, attr, value)
    assert fields(result.model)[1].repr is False
    assert all(not f.repr for f in fields(result.payoff) if f.name != "target_dates")
    assert "Decimal" not in repr(result)
    with pytest.raises(TypeError):
        s.MonthlyModelInput(
            result.model.context_dates, result.model.close_returns_bps, own_open=Decimal(999)
        )
    with pytest.raises(TypeError):
        s.MonthlyModelInput(
            result.model.context_dates,
            result.model.close_returns_bps,
            future_known_covariates=(Decimal(999),),
        )
    with pytest.raises(ValueError, match="model_returns"):
        replace(result.model, close_returns_bps=result.payoff.close_over_entry_open)
    with pytest.raises(ValueError, match="input_binding"):
        replace(result, identity=replace(result.identity, source_date=date(2012, 12, 28)))


def test_pure_call_never_uses_files_network_credentials_or_source_loader(sample, monkeypatch):
    expected = build(sample)

    def forbidden(*args, **kwargs):
        pytest.fail("I/O/credential/source loader forbidden")

    with monkeypatch.context() as guard:
        for obj, attr in (
            (builtins, "open"),
            (io, "open"),
            (os, "open"),
            (os, "getenv"),
            (Path, "read_bytes"),
            (Path, "read_text"),
            (data, "load_verified_adjusted_etf_snapshot"),
            (socket, "create_connection"),
            (socket.socket, "connect"),
        ):
            guard.setattr(obj, attr, forbidden)
        assert build(sample) == expected
