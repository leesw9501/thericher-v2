from __future__ import annotations

import builtins
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Context, Decimal, Inexact, localcontext
from itertools import permutations
from pathlib import Path

import pytest

from thericher_v2.data.tiingo_adjusted_etf_daily import AdjustedEtfRow
from thericher_v2.research import cross_asset_etf_input as cross
from thericher_v2.research import three_asset_nav as nav

D = Decimal
VINTAGE = "synthetic:same-adjusted-vintage"
DATES = (date(2026, 1, 15), date(2026, 1, 16), date(2026, 1, 20), date(2026, 1, 21))


@pytest.fixture(autouse=True)
def decimal50():
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        yield


def session(day, *, close_hour=21):
    return cross.CrossAssetSession(
        day,
        datetime(day.year, day.month, day.day, 14, 30, tzinfo=UTC),
        datetime(day.year, day.month, day.day, close_hour, tzinfo=UTC),
    )


def row(symbol, day, opening="10", closing="10", *, vintage=VINTAGE):
    opening, closing = D(opening), D(closing)
    return cross.CrossAssetAdjustedRow(
        symbol, day, vintage, opening, max(opening, closing), min(opening, closing), closing
    )


def source(dates=DATES):
    return {symbol: tuple(row(symbol, day) for day in dates) for symbol in cross.INSTRUMENT_ORDER}


def marks(rows=None, dates=DATES):
    return cross.prepare_cross_asset_marks(
        source(dates) if rows is None else rows,
        scheduled_sessions=tuple(map(session, dates)),
        vintage_ref=VINTAGE,
    )


def history(rows=None, **changes):
    kwargs = {
        "scheduled_sessions": tuple(map(session, DATES)),
        "entry_session_date": DATES[2],
        "history_session_count": 2,
        "decision_at": session(DATES[1]).close_at,
        "vintage_ref": VINTAGE,
    }
    kwargs.update(changes)
    return cross.build_cross_asset_history(source() if rows is None else rows, **kwargs)


def target(spy=".2", tlt=".3", gld=".4", cash=".1"):
    weights = dict(zip(cross.INSTRUMENT_ORDER, map(D, (spy, tlt, gld)), strict=True))
    return cross.CrossAssetTarget(weights, D(cash))


def close(actual, expected):
    assert abs(actual - expected) <= D("1e-44") * max(abs(expected), D(1))


def test_exact_calendar_previous_close_and_named_immutable_input():
    result = history()
    assert result.inputs.instrument_order == ("SPY", "TLT", "GLD")
    assert tuple(s.session_date for s in result.inputs.sessions) == DATES[:2]
    assert result.decision_at == session(DATES[1]).close_at
    assert result.entry_session_date == DATES[2]
    assert result.inputs.vintage_ref == VINTAGE
    assert result.safe_facts()["row_count_per_instrument"] == 2
    with pytest.raises(FrozenInstanceError):
        result.decision_at = session(DATES[2]).open_at
    with pytest.raises(FrozenInstanceError):
        result.inputs.rows_by_instrument[0][0].adj_close = D(12)


@pytest.mark.parametrize("symbol", cross.INSTRUMENT_ORDER)
@pytest.mark.parametrize("mode", ("remove", "price", "vintage", "duplicate", "malformed"))
@pytest.mark.parametrize("scope", ("old", "entry", "future"))
def test_unrequired_old_current_future_values_and_support_cannot_mask_history(symbol, mode, scope):
    rows = source()
    outside_day = {"old": date(2025, 12, 31), "entry": DATES[2], "future": DATES[3]}[scope]
    extras = [row(symbol, outside_day)]
    if mode == "remove":
        extras = []
    elif mode == "price":
        extras = [row(symbol, outside_day, "1e20", "1e-20")]
    elif mode == "vintage":
        extras = [row(symbol, outside_day, vintage="different-vintage")]
    elif mode == "duplicate":
        extras *= 2
    else:
        invalid = row(symbol, outside_day)
        object.__setattr__(invalid, "adj_close", D("NaN"))
        object.__setattr__(invalid, "symbol", "IWM")
        extras = [invalid]
    rows[symbol] = tuple(r for r in rows[symbol] if r.session_date != outside_day) + tuple(extras)
    assert history(rows) == history()
    assert history(rows).safe_facts() == history().safe_facts()


@pytest.mark.parametrize("symbol", cross.INSTRUMENT_ORDER)
@pytest.mark.parametrize("day", DATES[:2])
def test_missing_required_past_session_is_scoped_unavailable(symbol, day):
    rows = source()
    rows[symbol] = tuple(r for r in rows[symbol] if r.session_date != day)
    with pytest.raises(
        cross.CrossAssetInputUnavailable, match="^required_session_missing$"
    ) as error:
        history(rows)
    assert error.value.safe_facts() == {
        "status": "input_unavailable", "reason_code": "required_session_missing"
    }
    assert history().safe_facts()["status"] == "ready"


@pytest.mark.parametrize("symbol", cross.INSTRUMENT_ORDER)
def test_missing_future_mark_does_not_influence_history_but_invalidates_entire_replay_input(symbol):
    rows = source()
    rows[symbol] = rows[symbol][:-1]
    assert history(rows) == history()
    with pytest.raises(cross.CrossAssetInputUnavailable, match="required_session_missing"):
        marks(rows)


@pytest.mark.parametrize("symbol", cross.INSTRUMENT_ORDER)
@pytest.mark.parametrize("mode", ("duplicate", "vintage", "symbol", "nonfinite", "geometry"))
def test_selected_row_invalidity_is_not_repaired(symbol, mode):
    rows = source()
    selected = rows[symbol][0]
    expected = {
        "duplicate": "required_session_duplicate",
        "vintage": "required_vintage_mismatch",
        "symbol": "required_row_symbol_mismatch",
        "nonfinite": "adjusted_values_invalid",
        "geometry": "adjusted_geometry_invalid",
    }[mode]
    if mode == "duplicate":
        rows[symbol] += (selected,)
    else:
        field, value = {
            "vintage": ("vintage_ref", "different"),
            "symbol": ("symbol", "GLD" if symbol != "GLD" else "SPY"),
            "nonfinite": ("adj_close", D("NaN")),
            "geometry": ("adj_high", D(1)),
        }[mode]
        object.__setattr__(selected, field, value)
    with pytest.raises(cross.CrossAssetInputUnavailable, match=f"^{expected}$"):
        history(rows)


def test_legacy_adjusted_row_cannot_be_accepted_even_with_a_valid_named_source_key():
    rows = source()
    legacy = AdjustedEtfRow("SPY", DATES[0], D(10), D(10), D(10), D(10))
    rows["SPY"] = (legacy,) + rows["SPY"][1:]
    with pytest.raises(cross.CrossAssetInputUnavailable, match="required_row_type_invalid"):
        history(rows)
    rows = source()
    rows["QQQ"] = rows.pop("TLT")
    with pytest.raises(cross.CrossAssetInputUnavailable, match="source_symbols_invalid"):
        history(rows)
    with pytest.raises(cross.CrossAssetInputUnavailable, match="row_symbol_invalid"):
        row("QQQ", DATES[0])


@pytest.mark.parametrize("order", tuple(permutations(cross.INSTRUMENT_ORDER)))
def test_mapping_and_source_row_order_does_not_change_binding_or_replay(order):
    rows = source()
    shuffled = {symbol: tuple(reversed(rows[symbol])) for symbol in order}
    weights = {symbol: target().weights_by_symbol[symbol] for symbol in order}
    named = cross.CrossAssetTarget(weights, D(".1"))
    assert marks(shuffled) == marks(rows)
    assert history(shuffled) == history(rows)
    actual = cross.replay_cross_asset(marks(shuffled), {DATES[0]: named}, D(5))
    assert actual == cross.replay_cross_asset(marks(rows), {DATES[0]: target()}, D(5))


@pytest.mark.parametrize("cost", ("0", "2.5", "5", "10"))
def test_exact_named_positional_replay_parity_without_legacy_mapping_helpers(monkeypatch, cost):
    rows = {
        "SPY": (row("SPY", DATES[0], "2", "3"), row("SPY", DATES[1], "4", "5")),
        "TLT": (row("TLT", DATES[0], "7", "11"), row("TLT", DATES[1], "13", "17")),
        "GLD": (row("GLD", DATES[0], "19", "23"), row("GLD", DATES[1], "29", "31")),
    }
    expected = nav.replay(
        (
            nav.ThreeAssetDay(DATES[0], (D(2), D(7), D(19)), (D(3), D(11), D(23))),
            nav.ThreeAssetDay(DATES[1], (D(4), D(13), D(29)), (D(5), D(17), D(31))),
        ),
        {DATES[0]: nav.ThreeAssetTarget((D(".2"), D(".3"), D(".4")), D(".1"))},
        D(cost),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy named instrument helper invoked")

    monkeypatch.setattr(nav, "_named", forbidden)
    actual = cross.replay_cross_asset(marks(rows, DATES[:2]), {DATES[0]: target()}, D(cost))
    assert actual.ledger == expected
    assert actual.instrument_order == cross.INSTRUMENT_ORDER
    assert nav.SYMBOLS == ("SPY", "QQQ", "IWM")


@pytest.mark.parametrize("cost", ("0", "2.5", "5", "10"))
def test_entry_final_actual_notional_fees_and_shared_initial_capital(cost):
    fee = D(cost) / 10000
    result = cross.replay_cross_asset(marks(), {DATES[0]: target()}, D(cost)).ledger
    close(result.final_nav, (1 - D(".9") * fee) / (1 + D(".9") * fee))
    close(result.total_fees, 2 * D(".9") * fee / (1 + D(".9") * fee))
    close(result.total_traded_notional, 2 * D(".9") / (1 + D(".9") * fee))
    assert result.final_state.quantities == (D(0), D(0), D(0))
    close(sum(result.log_returns, D(0)), result.final_nav.ln())
    close(result.simple_returns[0], 1 / (1 + D(".9") * fee) - 1)
    close(result.simple_returns[-1], -D(".9") * fee)


def test_overnight_carry_uses_one_capital_account_and_no_implicit_asset_renormalization():
    rows = source(DATES[:2])
    rows["SPY"] = (row("SPY", DATES[0]), row("SPY", DATES[1], "20", "20"))
    result = cross.replay_cross_asset(
        marks(rows, DATES[:2]), {DATES[0]: target(".5", "0", "0", ".5")}, D(0)
    ).ledger
    assert result.navs == (D(1), D("1.5"))
    assert result.total_traded_notional == D("1.5")
    assert result.total_fees == 0


def test_future_loss_mark_is_accounted_without_filtering_or_changing_past_inputs():
    rows = source()
    rows["TLT"] = rows["TLT"][:-1] + (row("TLT", DATES[-1], "1", "1"),)
    assert history(rows) == history()
    result = cross.replay_cross_asset(
        marks(rows), {DATES[0]: target("0", "1", "0", "0")}, D(0)
    ).ledger
    assert len(result.daily) == 4 and result.final_nav == D(".1")
    assert result.log_returns[-1] < 0


@pytest.mark.parametrize("cost", ("0", "5", "10"))
def test_per_instrument_whole_path_price_scale_invariance(cost):
    rows = {
        symbol: tuple(row(symbol, day, str(10 + i), str(11 + i)) for i, day in enumerate(DATES))
        for symbol in cross.INSTRUMENT_ORDER
    }
    scales = {"SPY": D(".001"), "TLT": D(16), "GLD": D(1000)}
    scaled = {
        symbol: tuple(
            replace(
                r,
                adj_open=r.adj_open * scales[symbol],
                adj_high=r.adj_high * scales[symbol],
                adj_low=r.adj_low * scales[symbol],
                adj_close=r.adj_close * scales[symbol],
            )
            for r in values
        )
        for symbol, values in rows.items()
    }
    actions = {DATES[0]: target(), DATES[2]: target(".1", ".4", ".2", ".3")}
    baseline = cross.replay_cross_asset(marks(rows), actions, D(cost)).ledger
    alternate = cross.replay_cross_asset(marks(scaled), actions, D(cost)).ledger
    for left, right in zip(baseline.daily, alternate.daily, strict=True):
        for field in ("nav", "fees", "traded_notional", "cash", "simple_return", "log_return"):
            close(getattr(left, field), getattr(right, field))
    close(baseline.total_fees, alternate.total_fees)
    close(baseline.total_traded_notional, alternate.total_traded_notional)


def test_hostile_ambient_decimal_context_does_not_change_input_or_replay():
    inputs, actions = marks(), {DATES[0]: target()}
    expected = cross.replay_cross_asset(inputs, actions, D(5))
    with localcontext(Context(prec=3, rounding=ROUND_DOWN)) as ambient:
        ambient.traps[Inexact] = True
        assert marks() == inputs
        assert cross.replay_cross_asset(marks(), {DATES[0]: target()}, D(5)) == expected


def test_targets_are_copied_and_cash_is_exact_not_repaired():
    original = dict(target().weights_by_symbol)
    immutable = cross.CrossAssetTarget(original, D(".1"))
    original["SPY"] = D(1)
    assert immutable.weights_by_symbol["SPY"] == D(".2")
    with pytest.raises(TypeError):
        immutable.weights_by_symbol["SPY"] = D(1)
    with pytest.raises(nav.ThreeAssetNavError, match="cash_weight_mismatch"):
        target(cash=".100000000000000000000000000000000000000000000000001")
    with pytest.raises(nav.ThreeAssetNavError, match="targets_exceed_one"):
        target("1", ".01", "0", "0")


@pytest.mark.parametrize("bad", (None, True, 1, 1.0, "10", D(0), D(-1), D("NaN"), D("Infinity")))
def test_nonpositive_nondecimal_nonfinite_adjusted_marks_are_rejected(bad):
    with pytest.raises(cross.CrossAssetInputUnavailable, match="adjusted_values_invalid"):
        cross.CrossAssetAdjustedRow("SPY", DATES[0], VINTAGE, bad, D(10), D(10), D(10))


@pytest.mark.parametrize("vintage", (None, "", " ", " trailing ", 5))
def test_vintage_contract_is_explicit(vintage):
    with pytest.raises(cross.CrossAssetInputUnavailable, match="vintage_invalid"):
        row("SPY", DATES[0], vintage=vintage)


@pytest.mark.parametrize("order", (("GLD", "TLT", "SPY"), nav.SYMBOLS, ["SPY", "TLT", "GLD"]))
def test_noncanonical_positional_order_rejected_at_all_public_boundaries(order):
    inputs = marks()
    replay = cross.replay_cross_asset(inputs, {}, D(0))
    with pytest.raises(cross.CrossAssetInputUnavailable, match="instrument_order_invalid"):
        replace(inputs, instrument_order=order)
    with pytest.raises(cross.CrossAssetInputUnavailable, match="instrument_order_invalid"):
        replace(target(), instrument_order=order)
    with pytest.raises(cross.CrossAssetInputUnavailable, match="instrument_order_invalid"):
        replace(replay, instrument_order=order)


@pytest.mark.parametrize("mode", ("naive", "offset", "inverted", "wrong_day", "duplicate", "order"))
def test_invalid_calendar_is_not_inferred_or_repaired(mode):
    sessions = tuple(map(session, DATES))
    if mode == "duplicate":
        sessions = (sessions[0],) + sessions
    elif mode == "order":
        sessions = tuple(reversed(sessions))
    else:
        initial = sessions[0]
        changes = {
            "naive": {"open_at": initial.open_at.replace(tzinfo=None)},
            "offset": {"open_at": initial.open_at.astimezone(timezone(timedelta(hours=9)))},
            "inverted": {"close_at": initial.open_at},
            "wrong_day": {"close_at": initial.close_at + timedelta(days=1)},
        }[mode]
        with pytest.raises(cross.CrossAssetInputUnavailable):
            replace(initial, **changes)
        return
    with pytest.raises(cross.CrossAssetInputUnavailable, match="calendar_order_invalid"):
        history(scheduled_sessions=sessions)


@pytest.mark.parametrize(
    "changes,reason",
    (
        ({"history_session_count": 3}, "scheduled_history_missing"),
        ({"history_session_count": 0}, "history_count_invalid"),
        ({"history_session_count": True}, "history_count_invalid"),
        ({"entry_session_date": date(2026, 1, 19)}, "entry_session_missing"),
        ({"decision_at": session(DATES[2]).open_at}, "decision_not_previous_close"),
        ({"decision_at": session(DATES[0]).close_at}, "decision_not_previous_close"),
    ),
)
def test_exact_previous_scheduled_close_not_weekdays_or_latest_observed(changes, reason):
    with pytest.raises(cross.CrossAssetInputUnavailable, match=reason):
        history(**changes)


def test_early_close_is_a_calendar_clock_not_midnight_or_fixed_duration():
    sessions = (session(DATES[0]), session(DATES[1], close_hour=18), session(DATES[2]))
    result = history(scheduled_sessions=sessions, decision_at=sessions[1].close_at)
    assert result.decision_at.hour == 18 and len(result.inputs.sessions) == 2


def test_all_cash_requires_all_marks_and_preserves_every_scheduled_date():
    result = cross.replay_cross_asset(marks(), {}, D(10)).ledger
    assert result.navs == (D(1),) * 4 and result.total_fees == 0
    assert tuple(d.date for d in result.daily) == DATES
    rows = source()
    rows["GLD"] = rows["GLD"][:-1]
    with pytest.raises(cross.CrossAssetInputUnavailable, match="required_session_missing"):
        marks(rows)


def test_safe_facts_and_repr_never_expose_numeric_marks_targets_ledger_or_vintage():
    rows = {
        symbol: tuple(row(symbol, day, "123.456789", "987.654321") for day in DATES)
        for symbol in cross.INSTRUMENT_ORDER
    }
    inputs, past = marks(rows), history(rows)
    actions = target(".123456789", "0", "0", ".876543211")
    replay = cross.replay_cross_asset(inputs, {DATES[0]: actions}, D(5))
    safe = repr((inputs, past, actions, replay, rows["SPY"][0]))
    safe += repr((inputs.safe_facts(), past.safe_facts(), replay.safe_facts()))
    for private in ("123.456789", "987.654321", ".123456789", VINTAGE):
        assert private not in safe
    assert "TLT" in safe and "GLD" in safe


def test_source_free_call_path_needs_no_network_files_credentials(monkeypatch):
    rows, actions = source(), {DATES[0]: target()}

    def forbidden(*args, **kwargs):
        raise AssertionError("external access attempted")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    assert history(rows).safe_facts()["status"] == "ready"
    assert cross.replay_cross_asset(marks(rows), actions, D(5)).safe_facts()["status"] == "replayed"


def test_history_requires_no_calendar_tail_after_its_predeclared_entry():
    assert history(scheduled_sessions=tuple(map(session, DATES[:3]))) == history()


def test_unrequired_mark_rows_cannot_change_complete_replay():
    rows = source()
    poison = row("TLT", date(2026, 1, 22), vintage="unrelated-vintage")
    object.__setattr__(poison, "adj_open", D("NaN"))
    rows["TLT"] += (poison, poison)
    rows["GLD"] += (row("GLD", date(2025, 12, 31)),)
    assert marks(rows) == marks()
    assert cross.replay_cross_asset(marks(rows), {DATES[0]: target()}, D(5)) == (
        cross.replay_cross_asset(marks(), {DATES[0]: target()}, D(5))
    )


@pytest.mark.parametrize("day", DATES)
def test_any_required_mark_gap_is_unavailable_not_cash_or_a_shorter_path(day):
    rows = source()
    rows["GLD"] = tuple(r for r in rows["GLD"] if r.session_date != day)
    with pytest.raises(cross.CrossAssetInputUnavailable, match="required_session_missing"):
        marks(rows)


def test_legacy_targets_and_out_of_path_action_dates_are_rejected():
    with pytest.raises(cross.CrossAssetInputUnavailable, match="target_type_invalid"):
        cross.replay_cross_asset(
            marks(), {DATES[0]: nav.ThreeAssetTarget((D(0), D(0), D(0)), D(1))}, D(5)
        )
    with pytest.raises(nav.ThreeAssetNavError, match="target_dates_invalid"):
        cross.replay_cross_asset(marks(), {date(2026, 1, 19): target()}, D(5))
    with pytest.raises(cross.CrossAssetInputUnavailable, match="target_symbols_invalid"):
        cross.CrossAssetTarget(dict(zip(nav.SYMBOLS, (D(0), D(0), D(0)), strict=True)), D(1))
