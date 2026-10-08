from __future__ import annotations

import builtins
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.research import kis_sector_relative_strength as study
from thericher_v2.research.cross_asset_etf_input import (
    CrossAssetInputUnavailable,
    CrossAssetSession,
)

D = Decimal
VINTAGE = "synthetic-sector-vintage"
EASTERN = ZoneInfo("America/New_York")


def session(day, close_hour=16):
    return CrossAssetSession(
        day,
        datetime.combine(day, time(9, 30), EASTERN).astimezone(UTC),
        datetime.combine(day, time(close_hour), EASTERN).astimezone(UTC),
    )


@pytest.fixture(scope="module")
def schedule():
    days = []
    day = date(2023, 8, 1)
    while len(days) < 180:
        if day.weekday() < 5:
            days.append(session(day))
        day += timedelta(days=1)
    return tuple(days)


def rows(schedule, final=("110", "130", "120", "90")):
    history = schedule[:127]
    return {
        s: tuple(
            study.SectorPriceClose(s, d.session_date, VINTAGE, D(value) if i == 126 else D(100))
            for i, d in enumerate(history)
        )
        for s, value in zip(study.SYMBOLS, final, strict=True)
    }


def build(schedule, source=None, history=None, entry=None, decision=None):
    history = schedule[:127] if history is None else history
    return study.build_sector_relative_strength(
        rows(schedule) if source is None else source,
        scheduled_history=history,
        entry_session=schedule[127] if entry is None else entry,
        decision_at=history[-1].close_at if decision is None else decision,
        vintage_ref=VINTAGE,
    )


@pytest.mark.parametrize(
    "final,winner",
    [
        (("110", "130", "120", "90"), "XLK"),
        (("110", "120", "140", "90"), "XLF"),
        (("110", "120", "90", "150"), "XLE"),
        (("130", "120", "110", "90"), "SPY"),
        (("90", "101", "99", "80"), "XLK"),
        (("90", "80", "70", "60"), None),
        (("100", "100", "100", "100"), None),
        (("110", "120", "120", "90"), None),
        (("120", "120", "110", "90"), None),
    ],
)
def test_fixed_absolute_relative_gates_and_cash_first_exact_ties(schedule, final, winner):
    result = build(schedule, rows(schedule, final))
    assert result.action.selected_symbol == winner
    assert result.action.weights == tuple(D(int(s == winner)) for s in study.SYMBOLS)
    assert (
        sum(map(Fraction, result.action.weights), Fraction(0)) + Fraction(result.action.cash_weight)
        == 1
    )
    if winner not in (None, "SPY"):
        index = study.SYMBOLS.index(winner)
        assert result.momentum[index] > max(D(0), result.momentum[0])


def test_exact126_intervals127_completed_closes_and_price_scale(schedule):
    source = rows(schedule)
    original = build(schedule, source)
    assert original.momentum == (D(".1"), D(".3"), D(".2"), D("-.1"))
    scaled = {
        s: tuple(replace(r, close=r.close * D(i + 2)) for r in rs)
        for i, (s, rs) in enumerate(source.items())
    }
    assert build(schedule, scaled) == original


@pytest.mark.parametrize("mode", ["mutate", "remove", "invalid_duplicate"])
def test_current_future_prices_and_support_never_change_choice_or_availability(schedule, mode):
    source = rows(schedule)
    original = build(schedule, source)
    if mode != "remove":
        future = schedule[127].session_date
        for symbol in study.SYMBOLS:
            extra = SimpleNamespace(
                session_date=future, close=D("NaN"), symbol="FOREIGN", vintage_ref="foreign"
            )
            source[symbol] += (
                (extra, extra)
                if mode == "invalid_duplicate"
                else (study.SectorPriceClose(symbol, future, VINTAGE, D("99999")),)
            )
    assert build(schedule, source) == original


def test_unused_old_values_do_not_fill_gaps_and_input_order_is_irrelevant(schedule):
    source = rows(schedule)
    original = build(schedule, source)
    old = SimpleNamespace(
        session_date=schedule[0].session_date - timedelta(days=10), close=D("NaN")
    )
    shuffled = {s: (old, *reversed(source[s])) for s in reversed(study.SYMBOLS)}
    assert build(schedule, shuffled) == original
    shuffled["XLE"] = tuple(
        r for r in shuffled["XLE"] if r.session_date != schedule[70].session_date
    )
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        build(schedule, shuffled)


@pytest.mark.parametrize("index", [0, 70, 126])
def test_missing_anchor_interior_or_decision_is_scoped_not_stale_fallback(schedule, index):
    source = rows(schedule)
    source["XLF"] = source["XLF"][:index] + source["XLF"][index + 1 :]
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing") as error:
        build(schedule, source)
    assert error.value.safe_facts()["status"] == "input_unavailable"


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("missing_symbol", "source_symbols_invalid"),
        ("trio_relabel", "source_symbols_invalid"),
        ("wrong_day", "required_session_missing"),
        ("wrong_symbol", "required_row_symbol_mismatch"),
        ("wrong_vintage", "required_vintage_mismatch"),
        ("duplicate", "required_session_duplicate"),
        ("wrong_type", "required_row_type_invalid"),
        ("wrong_sequence", "source_sequence_invalid"),
    ],
)
def test_required_contract_faults_are_not_cash_decisions(schedule, mode, reason):
    source = rows(schedule)
    row = source["XLK"][30]
    if mode == "missing_symbol":
        del source["XLE"]
    elif mode == "trio_relabel":
        source["TLT"] = source.pop("XLK")
    elif mode == "wrong_sequence":
        source["XLK"] = "not rows"
    else:
        if mode == "wrong_day":
            row = replace(row, session_date=schedule[150].session_date)
        elif mode == "wrong_symbol":
            row = replace(row, symbol="XLF")
        elif mode == "wrong_vintage":
            row = replace(row, vintage_ref="another")
        elif mode == "wrong_type":
            row = SimpleNamespace(session_date=row.session_date)
        if mode == "duplicate":
            source["XLK"] += (row,)
        else:
            source["XLK"] = (*source["XLK"][:30], row, *source["XLK"][31:])
    with pytest.raises(CrossAssetInputUnavailable, match=reason):
        build(schedule, source)


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("short", "scheduled_history_missing"),
        ("long", "scheduled_history_missing"),
        ("disordered", "calendar_order_invalid"),
        ("stale", "decision_not_previous_close"),
        ("nonutc", "decision_not_previous_close"),
        ("entry_before", "decision_not_previous_close"),
    ],
)
def test_insufficient_stale_and_invalid_decision_calendar(schedule, mode, reason):
    history, entry, decision = schedule[:127], schedule[127], schedule[126].close_at
    if mode == "short":
        history = history[1:]
    elif mode == "long":
        history = schedule[:128]
    elif mode == "disordered":
        history = tuple(reversed(history))
    elif mode == "stale":
        decision = schedule[127].close_at
    elif mode == "nonutc":
        decision = decision.astimezone(EASTERN)
    elif mode == "entry_before":
        entry = history[-1]
    with pytest.raises(CrossAssetInputUnavailable, match=reason):
        build(schedule, history=history, entry=entry, decision=decision)


@pytest.mark.parametrize("value", [D(0), D(-1), D("NaN"), D("Infinity"), 100.0])
def test_invalid_required_close_fails_not_flat_or_older_observation(schedule, value):
    with pytest.raises(CrossAssetInputUnavailable, match="price_close_invalid"):
        study.SectorPriceClose("XLK", schedule[0].session_date, VINTAGE, value)


def test_early_close_and_dst_caller_calendar_no_hardcoded_close(schedule):
    history = (*schedule[:126], session(schedule[126].session_date, close_hour=13))
    result = build(schedule, history=history)
    assert result.decision_at == history[-1].close_at
    with pytest.raises(CrossAssetInputUnavailable, match="decision_not_previous_close"):
        build(schedule, history=history, decision=schedule[126].close_at)
    assert session(date(2024, 3, 8)).open_at.hour == 14
    assert session(date(2024, 3, 11)).open_at.hour == 13


def test_21_session_phase_from_explicit_calendar_no_month_year_or_presence_reset(schedule):
    entries = study.rebalance_entry_dates(
        schedule, first_entry_session_date=schedule[127].session_date
    )
    assert entries == tuple(schedule[i].session_date for i in (127, 148, 169))
    extended = (*schedule, session(schedule[-1].session_date + timedelta(days=1)))
    assert (
        study.rebalance_entry_dates(extended, first_entry_session_date=schedule[127].session_date)
        == entries
    )
    with pytest.raises(CrossAssetInputUnavailable, match="scheduled_history_missing"):
        study.rebalance_entry_dates(schedule, first_entry_session_date=schedule[126].session_date)


def test_forged_decision_action_must_match_momentum_and_vintage(schedule):
    original = build(schedule)
    with pytest.raises(CrossAssetInputUnavailable, match="action_momentum_mismatch"):
        replace(original, action=study.SectorAction("SPY"))
    with pytest.raises(CrossAssetInputUnavailable, match="momentum_invalid"):
        replace(original, momentum=(D(0),) * 3)
    with pytest.raises(CrossAssetInputUnavailable, match="vintage_invalid"):
        replace(original, vintage_ref=" ")
    with pytest.raises(FrozenInstanceError):
        original.action.selected_symbol = "XLE"
    assert "synthetic-sector-vintage" not in repr(original)
    assert "momentum=" not in repr(original) and "close=" not in repr(rows(schedule)["SPY"][0])


def test_decimal_precision_metadata_safe_facts_and_source_io_isolation(schedule, monkeypatch):
    source = rows(schedule)
    expected = build(schedule, source)

    def forbidden(*args, **kwargs):
        raise AssertionError("IO/provider not allowed")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    with localcontext() as context:
        context.prec = 3
        assert build(schedule, source) == expected
    facts = expected.safe_facts()
    assert facts["paper_input"] is False and facts["availability"] == "not_observed"
    assert not {"momentum", "close", "selected_symbol", "weights", "vintage_ref"} & set(facts)
    config = study.configuration()
    assert config["symbols"] == ["SPY", "XLK", "XLF", "XLE"]
    assert config["required_completed_closes"] == 127 and config["fits"] == 0
    assert config["gpu"] is False and config["paper_input"] is False
    config["symbols"].clear()
    assert study.configuration()["symbols"] == list(study.SYMBOLS)
