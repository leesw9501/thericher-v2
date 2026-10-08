from __future__ import annotations

import builtins
import os
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from thericher_v2.research import cross_asset_daily_risk_input as prep
from thericher_v2.research import cross_asset_hedge_failure_input as monthly
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable

D = Decimal
VINTAGE = "synthetic-raw-vintage-hidden"
ENTRY = date(2024, 3, 6)


def session(day, close_hour=21, open_hour=14):
    return prep.CrossAssetSession(
        day,
        datetime.combine(day, time(open_hour, 30), UTC),
        datetime.combine(day, time(close_hour), UTC),
    )


def history():
    days, day = [], ENTRY - timedelta(days=1)
    while len(days) < 64:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    # Synthetic caller schedule; no assertion of actual NYSE holiday completeness.
    return tuple(session(day) for day in reversed(days))


def rows(schedule=None):
    schedule = history() if schedule is None else schedule
    return {
        symbol: tuple(
            prep.RawD1Price(
                symbol,
                s.session_date,
                VINTAGE,
                open=None if i == 0 else D(100 + i + 10 * asset),
                close=D(101 + i + 10 * asset),
            )
            for i, s in enumerate(schedule)
        )
        for asset, symbol in enumerate(prep.INSTRUMENT_ORDER)
    }


def features(source=None, schedule=None, entry=None, cutoff=None, vintage=VINTAGE):
    schedule = history() if schedule is None else schedule
    return prep.prepare_daily_features(
        rows(schedule) if source is None else source,
        scheduled_history=schedule,
        entry_session=session(ENTRY) if entry is None else entry,
        decision_at=schedule[-1].close_at if cutoff is None else cutoff,
        vintage_ref=vintage,
    )


def forward():
    return tuple(
        map(
            session,
            (
                date(2024, 2, 28),
                date(2024, 2, 29),
                date(2024, 3, 1),
                date(2024, 3, 4),
                date(2024, 3, 5),
            ),
        )
    )


def target_rows(closes=("110", "95", "100"), schedule=None):
    schedule = forward() if schedule is None else schedule
    return {
        symbol: (
            prep.RawD1Price(symbol, schedule[0].session_date, VINTAGE, open=D(100)),
            prep.RawD1Price(symbol, schedule[-1].session_date, VINTAGE, close=D(close)),
        )
        for symbol, close in zip(prep.INSTRUMENT_ORDER, closes, strict=True)
    }


def target(source=None, schedule=None, vintage=VINTAGE):
    schedule = forward() if schedule is None else schedule
    return prep.build_five_session_target(
        target_rows(schedule=schedule) if source is None else source,
        scheduled_forward=schedule,
        vintage_ref=vintage,
    )


def test_exact_six_by_63_asset_major_log_difference_channels_same_month_entry():
    schedule, source = history(), rows()
    result = features(source)
    assert result.observation_dates == tuple(s.session_date for s in schedule[1:])
    assert result.entry_at == session(ENTRY).open_at
    assert prep.INSTRUMENT_ORDER == ("SPY", "TLT", "GLD")
    assert result.safe_facts()["shape"] == (6, 63)
    assert result.safe_facts()["required_closes"] == 64
    assert result.safe_facts()["required_opens"] == 63
    with localcontext(prep.CONTEXT):
        for i, symbol in enumerate(prep.INSTRUMENT_ORDER):
            expected_close = tuple(
                b.close.ln() - a.close.ln()
                for a, b in zip(source[symbol], source[symbol][1:], strict=False)
            )
            expected_open = tuple(r.close.ln() - r.open.ln() for r in source[symbol][1:])
            assert result.features[2 * i : 2 * i + 2] == (expected_close, expected_open)


def test_daily_helpers_do_not_weaken_existing_month_boundary_guards():
    with pytest.raises(CrossAssetInputUnavailable, match="decision_not_previous_month_close"):
        monthly.prepare_monthly_features(
            rows(),
            scheduled_history=history(),
            entry_session=session(ENTRY),
            decision_at=history()[-1].close_at,
            vintage_ref=VINTAGE,
        )
    with pytest.raises(CrossAssetInputUnavailable, match="target_month_invalid"):
        monthly.build_monthly_target(target_rows(), scheduled_month=forward(), vintage_ref=VINTAGE)
    assert features().features and target().net_factor > 0


def test_context_fixed_scale_invariance_and_extreme_ratio_without_overflow():
    source = rows()
    expected = features(source)
    with localcontext() as context:
        context.prec = 6
        assert features(source) == expected
        assert context.prec == 6
    scaled = {
        s: tuple(
            replace(r, open=None if r.open is None else r.open * factor, close=r.close * factor)
            for r in source[s]
        )
        for s, factor in zip(prep.INSTRUMENT_ORDER, (D(2), D(3), D(5)), strict=True)
    }
    actual = features(scaled)
    assert all(
        abs(a - b) < D("1e-47")
        for x, y in zip(actual.features, expected.features, strict=True)
        for a, b in zip(x, y, strict=True)
    )
    extreme = {
        s: tuple(
            replace(
                r,
                open=None if r.open is None else D("1e-999999"),
                close=D("1e999999") if i % 2 else D("1e-999999"),
            )
            for i, r in enumerate(source[s])
        )
        for s in prep.INSTRUMENT_ORDER
    }
    assert all(v.is_finite() for channel in features(extreme).features for v in channel)


def test_repeated_context_log_cache_bounded_hits_do_not_change_output():
    prep._log.cache_clear()
    first = features()
    misses = prep._log.cache_info().misses
    assert features() == first and prep._log.cache_info().misses == misses
    assert prep._log.cache_info().maxsize == 16384


@pytest.mark.parametrize(
    "case,code",
    [
        ("63", "history_count_invalid"),
        ("65", "history_count_invalid"),
        ("list", "calendar_required"),
        ("reversed", "calendar_order_invalid"),
        ("duplicate", "calendar_order_invalid"),
        ("early", "decision_not_previous_close"),
        ("late", "decision_not_previous_close"),
        ("same_session", "decision_not_previous_close"),
        ("naive", "time_not_utc"),
    ],
)
def test_exact_history_and_previous_close_geometry(case, code):
    schedule, entry, cutoff = history(), session(ENTRY), history()[-1].close_at
    if case == "63":
        schedule = schedule[1:]
    elif case == "65":
        schedule = (session(schedule[0].session_date - timedelta(days=1)), *schedule)
    elif case == "list":
        schedule = list(schedule)
    elif case == "reversed":
        schedule = tuple(reversed(schedule))
    elif case == "duplicate":
        schedule = (schedule[1], *schedule[1:])
    elif case == "early":
        cutoff -= timedelta(microseconds=1)
    elif case == "late":
        cutoff += timedelta(microseconds=1)
    elif case == "same_session":
        entry = schedule[-1]
    else:
        cutoff = cutoff.replace(tzinfo=None)
    with pytest.raises(CrossAssetInputUnavailable, match=code):
        features(schedule=schedule, entry=entry, cutoff=cutoff)


def test_early_close_and_caller_entry_time_not_hardcoded():
    schedule = (*history()[:-1], session(history()[-1].session_date, close_hour=18))
    result = features(schedule=schedule, entry=session(ENTRY, open_hour=13))
    assert result.decision_at.hour == 18 and result.entry_at.hour == 13


@pytest.mark.parametrize(
    "symbol,index,key",
    [
        ("SPY", 0, "close"),
        ("TLT", 31, "open"),
        ("GLD", 63, "close"),
        ("SPY", 63, "row"),
    ],
)
def test_required_past_gap_no_older_substitution(symbol, index, key):
    source = rows()
    changed = list(source[symbol])
    if key == "row":
        changed.pop(index)
        code = "required_session_missing"
    else:
        if index == 0:
            changed[index] = replace(changed[index], open=D(1), close=None)
        else:
            changed[index] = replace(changed[index], **{key: None})
        code = "required_price_invalid"
    source[symbol] = (*changed, prep.RawD1Price(symbol, date(2020, 1, 1), VINTAGE, close=D(1)))
    with pytest.raises(CrossAssetInputUnavailable, match=code):
        features(source)


def test_current_future_presence_values_duplicates_and_poison_irrelevant():
    class Outside:
        def __init__(self, day):
            self.session_date = day

        def __getattr__(self, key):
            raise AssertionError("unneeded future field inspected")

    source = rows()
    expected = features(source)
    extras = (
        Outside(ENTRY),
        Outside(ENTRY),
        Outside(ENTRY + timedelta(days=20)),
        Outside(date(2020, 1, 1)),
        SimpleNamespace(session_date="invalid_future_date"),
    )
    mutated = {s: (*source[s], *extras) for s in prep.INSTRUMENT_ORDER}
    assert features(mutated) == expected
    for s in prep.INSTRUMENT_ORDER:
        first = replace(source[s][0])
        object.__setattr__(first, "open", D("NaN"))
        mutated[s] = (first, *source[s][1:], *extras)
    assert features(mutated) == expected


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("vintage_ref", "other", "required_vintage_mismatch"),
        ("symbol", "GLD", "required_symbol_mismatch"),
        ("price_basis", "adjusted", "price_basis_invalid"),
        ("open", D("NaN"), "required_price_invalid"),
        ("close", D(0), "required_price_invalid"),
        ("open", 1.0, "required_price_invalid"),
    ],
)
def test_selected_source_and_decimal_contracts(field, value, code):
    source = rows()
    changed = replace(source["SPY"][20])
    object.__setattr__(changed, field, value)
    source["SPY"] = (*source["SPY"][:20], changed, *source["SPY"][21:])
    with pytest.raises(CrossAssetInputUnavailable, match=code):
        features(source)


def test_required_duplicate_and_wrong_row_type_reject_without_mask():
    source = rows()
    source["SPY"] = (*source["SPY"], source["SPY"][20])
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_duplicate"):
        features(source)
    source = rows()
    source["SPY"] = (
        *source["SPY"][:20],
        SimpleNamespace(session_date=source["SPY"][20].session_date),
        *source["SPY"][21:],
    )
    with pytest.raises(CrossAssetInputUnavailable, match="required_row_type_invalid"):
        features(source)


def test_five_session_target_exact_canonical_finite_thirds_endpoint_replay():
    schedule = forward()
    source = target_rows()
    actual = target(source)
    opens = tuple(source[s][0].open for s in prep.INSTRUMENT_ORDER)
    closes = tuple(source[s][1].close for s in prep.INSTRUMENT_ORDER)
    with localcontext(prep.CONTEXT):
        allocation = nav.ThreeAssetTarget((prep.THIRD,) * 3, D(1) - 3 * prep.THIRD)
    expected = nav.replay(
        (
            nav.ThreeAssetDay(schedule[0].session_date, opens, opens),
            nav.ThreeAssetDay(schedule[-1].session_date, closes, closes),
        ),
        {schedule[0].session_date: allocation},
        D(5),
    ).final_nav
    assert actual.net_factor == expected and actual.loss_label is (expected < 1)
    assert actual.entry_at == schedule[0].open_at and actual.exit_at == schedule[-1].close_at
    assert actual.safe_facts()["scheduled_session_count"] == 5
    assert actual.safe_facts()["daily_mark_support"] == "not_checked"


@pytest.mark.parametrize(
    "closes,loss", [(("100",) * 3, True), (("101",) * 3, False), (("99",) * 3, True)]
)
def test_target_loss_threshold_includes_actual_entry_exit_costs(closes, loss):
    assert target(target_rows(closes)).loss_label is loss


def test_target_intermediate_rows_unneeded_endpoints_and_outer_poison_ignored():
    class Outside:
        def __init__(self, day):
            self.session_date = day

        def __getattr__(self, key):
            raise AssertionError("unused target field inspected")

    source = target_rows()
    expected = target(source)
    schedule = forward()
    for s in prep.INSTRUMENT_ORDER:
        first, last = map(replace, source[s])
        object.__setattr__(first, "close", D("NaN"))
        object.__setattr__(last, "open", D("NaN"))
        source[s] = (
            first,
            *(Outside(t.session_date) for t in schedule[1:-1]),
            last,
            Outside(schedule[-1].session_date + timedelta(days=1)),
        )
    assert target(source) == expected


@pytest.mark.parametrize(
    "case,code",
    [
        ("four", "forward_count_invalid"),
        ("six", "forward_count_invalid"),
        ("order", "calendar_order_invalid"),
        ("missing", "required_session_missing"),
        ("duplicate", "required_session_duplicate"),
        ("vintage", "required_vintage_mismatch"),
    ],
)
def test_target_exact_geometry_and_endpoint_source_failures(case, code):
    schedule, source = forward(), target_rows()
    if case == "four":
        schedule = schedule[:-1]
    elif case == "six":
        schedule = (*schedule, session(schedule[-1].session_date + timedelta(days=1)))
    elif case == "order":
        schedule = tuple(reversed(schedule))
    elif case == "missing":
        source["SPY"] = source["SPY"][:1]
    elif case == "duplicate":
        source["SPY"] += source["SPY"][:1]
    else:
        source["SPY"] = (replace(source["SPY"][0], vintage_ref="other"), source["SPY"][1])
    with pytest.raises(CrossAssetInputUnavailable, match=code):
        target(source, schedule)


def test_separate_adapters_never_access_io_env_network_or_models(monkeypatch):
    source, history_sessions, forward_sessions = rows(), history(), forward()
    future = target_rows()

    def forbidden(*args, **kwargs):
        raise AssertionError("external access")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    features(source, history_sessions)
    target(future, forward_sessions)


def test_immutable_outputs_and_safe_facts_hide_values_labels_vintage():
    context, label = features(), target()
    assert VINTAGE not in repr(context) + repr(label) + repr(context.safe_facts()) + repr(
        label.safe_facts()
    )
    assert "features=" not in repr(context) and "net_factor=" not in repr(label)
    assert "loss_label=" not in repr(label)
    with pytest.raises(FrozenInstanceError):
        context.vintage_ref = "other"
    with pytest.raises(FrozenInstanceError):
        label.loss_label = not label.loss_label
    with pytest.raises(CrossAssetInputUnavailable, match="feature_matrix_invalid"):
        replace(context, features=((D("NaN"),) * 63,) * 6)
    with pytest.raises(CrossAssetInputUnavailable, match="target_label_mismatch"):
        replace(label, loss_label=not label.loss_label)
