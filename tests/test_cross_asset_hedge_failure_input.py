from __future__ import annotations

import builtins
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.research import cross_asset_hedge_failure_input as prep
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import (
    INSTRUMENT_ORDER,
    CrossAssetAdjustedRow,
    CrossAssetInputUnavailable,
    CrossAssetSession,
)

D = Decimal
VINTAGE = "synthetic-kis-raw-vintage"
EASTERN = ZoneInfo("America/New_York")
DECISION = date(2024, 2, 29)
ENTRY = date(2024, 3, 1)
EXIT = date(2024, 3, 28)


def session(day, close_hour=16):
    opening = datetime.combine(day, time(9, 30), EASTERN).astimezone(UTC)
    closing = datetime.combine(day, time(close_hour), EASTERN).astimezone(UTC)
    return CrossAssetSession(day, opening, closing)


def history(last=DECISION):
    days = []
    day = last
    while len(days) < 64:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    # Synthetic caller calendar, not an assertion of actual NYSE holiday coverage.
    return tuple(map(session, reversed(days)))


def past_rows(schedule=None):
    schedule = history() if schedule is None else schedule
    return {symbol: tuple(prep.RawD1Price(
        symbol, s.session_date, VINTAGE,
        open=None if index == 0 else D(100 + index + asset),
        close=D(101 + index + asset),
    ) for index, s in enumerate(schedule))
        for asset, symbol in enumerate(INSTRUMENT_ORDER)}


def features(rows=None, schedule=None, entry=None, decision_at=None):
    schedule = history() if schedule is None else schedule
    return prep.prepare_monthly_features(
        past_rows(schedule) if rows is None else rows,
        scheduled_history=schedule, entry_session=session(ENTRY) if entry is None else entry,
        decision_at=schedule[-1].close_at if decision_at is None else decision_at,
        vintage_ref=VINTAGE,
    )


def month():
    return (session(ENTRY), session(date(2024, 3, 15)), session(EXIT))


def target_rows(closes=("110", "95", "100")):
    return {symbol: (prep.RawD1Price(symbol, ENTRY, VINTAGE, open=D(100)),
                     prep.RawD1Price(symbol, EXIT, VINTAGE, close=D(close)))
            for symbol, close in zip(INSTRUMENT_ORDER, closes, strict=True)}


def target(rows=None, schedule=None):
    return prep.build_monthly_target(
        target_rows() if rows is None else rows,
        scheduled_month=month() if schedule is None else schedule, vintage_ref=VINTAGE,
    )


def test_exact_asset_major_six_channels_and_63_past_observations():
    schedule, rows = history(), past_rows()
    result = features(rows)
    assert result.observation_dates == tuple(s.session_date for s in schedule[1:])
    assert len(result.features) == 6 and all(len(c) == 63 for c in result.features)
    with localcontext(prep.CONTEXT):
        for asset, symbol in enumerate(INSTRUMENT_ORDER):
            close_returns, intraday = result.features[2 * asset:2 * asset + 2]
            expected_close = tuple((b.close / a.close).ln()
                                   for a, b in zip(rows[symbol], rows[symbol][1:], strict=False))
            expected_intraday = tuple((row.close / row.open).ln() for row in rows[symbol][1:])
            assert close_returns == expected_close
            assert intraday == expected_intraday
    assert prep.CHANNELS[0].startswith("SPY:") and prep.CHANNELS[4].startswith("GLD:")


def test_independent_asset_price_scale_invariance_and_decimal_context():
    rows = past_rows()
    expected = features(rows)
    scaled = {symbol: tuple(replace(row, open=None if row.open is None else row.open * scale,
                                   close=row.close * scale) for row in rows[symbol])
              for symbol, scale in zip(INSTRUMENT_ORDER, (2, 3, 5), strict=True)}
    assert features(scaled) == expected
    with localcontext() as context:
        context.prec = 6
        assert features(rows) == expected
        assert context.prec == 6


def test_leap_day_early_close_and_dst_use_frozen_session_times():
    assert features().observation_dates[-1] == date(2024, 2, 29)
    schedule = (*history(date(2024, 11, 29))[:-1], session(date(2024, 11, 29), 13))
    result = features(schedule=schedule, entry=session(date(2024, 12, 2)))
    assert result.decision_at.hour == 18 and result.entry_at.hour == 14
    assert session(date(2024, 3, 8)).open_at.hour == 14
    assert session(date(2024, 3, 11)).open_at.hour == 13
    with pytest.raises(CrossAssetInputUnavailable, match="decision_not_previous_month_close"):
        features(schedule=schedule, entry=session(date(2024, 12, 2)),
                 decision_at=session(date(2024, 11, 29)).close_at)


@pytest.mark.parametrize("case,code", [
    ("63", "history_count_invalid"),
    ("duplicate", "calendar_order_invalid"),
    ("reversed", "calendar_order_invalid"),
    ("nonutc", "time_not_utc"),
    ("same_month", "decision_not_previous_month_close"),
])
def test_feature_calendar_and_cutoff_failures(case, code):
    schedule, entry, cutoff = history(), session(ENTRY), session(DECISION).close_at
    if case == "63":
        schedule = schedule[1:]
    elif case == "duplicate":
        schedule = (schedule[1], *schedule[1:])
    elif case == "reversed":
        schedule = tuple(reversed(schedule))
    elif case == "nonutc":
        cutoff = cutoff.astimezone(EASTERN)
    else:
        entry = session(DECISION)
    with pytest.raises(CrossAssetInputUnavailable, match=code):
        features(schedule=schedule, entry=entry, decision_at=cutoff)


@pytest.mark.parametrize("symbol,index,key", [
    ("SPY", 0, "close"), ("TLT", 31, "open"), ("GLD", 31, "close"), ("SPY", 63, "row"),
])
def test_required_missing_history_never_substitutes_older_rows(symbol, index, key):
    rows = past_rows()
    changed = list(rows[symbol])
    if key == "row":
        changed.pop(index)
        code = "required_session_missing"
    else:
        changed[index] = (replace(changed[index], open=D(100), close=None) if index == 0
                          else replace(changed[index], **{key: None}))
        code = "required_price_invalid"
    rows[symbol] = (*changed, prep.RawD1Price(symbol, date(2020, 1, 1), VINTAGE,
                                           open=D(77), close=D(78)))
    with pytest.raises(CrossAssetInputUnavailable, match=code):
        features(rows)


def test_old_current_future_mutations_missing_and_payoff_poison_do_not_affect_features():
    class Outside:
        def __init__(self, day):
            self.session_date = day

        def __getattr__(self, _name):
            raise AssertionError("unneeded source/payoff field inspected")

    rows = past_rows()
    expected = features(rows)
    mutated = {symbol: (*value, Outside(date(2020, 1, 1)), Outside(ENTRY), Outside(EXIT))
               for symbol, value in rows.items()}
    assert features(mutated) == expected
    mutated["SPY"] = (*rows["SPY"], prep.RawD1Price("SPY", EXIT, "unrelated", close=D("9e99")))
    assert features(mutated) == expected
    assert features(dict(reversed(tuple(rows.items())))) == expected
    assert features({symbol: tuple(reversed(value)) for symbol, value in rows.items()}) == expected


@pytest.mark.parametrize("case,code", [
    ("vintage", "required_vintage_mismatch"),
    ("symbol", "required_symbol_mismatch"),
    ("adjusted", "required_row_type_invalid"),
    ("duplicate", "required_session_duplicate"),
])
def test_source_grade_and_exact_required_identity(case, code):
    rows = past_rows()
    first, *rest = rows["SPY"]
    if case == "vintage":
        first = replace(first, vintage_ref="different")
    elif case == "symbol":
        first = replace(first, symbol="GLD")
    elif case == "adjusted":
        first = CrossAssetAdjustedRow("SPY", first.session_date, VINTAGE,
                                      D(100), D(100), D(100), D(100))
    else:
        rest.append(first)
    rows["SPY"] = (first, *rest)
    with pytest.raises(CrossAssetInputUnavailable, match=code):
        features(rows)


@pytest.mark.parametrize("closes", [("100", "100", "100"), ("110", "110", "110"),
                                   ("130", "85", "101")])
def test_fixed_target_factor_matches_shared_nav_actual_entry_and_exit_notional_cost(closes):
    result = target(target_rows(closes))
    weights = (prep.THIRD,) * 3
    with localcontext(prep.CONTEXT):
        cash = 1 - sum(weights)
        factor = (cash + (1 - D(".0005")) * sum(w * D(p) / 100
                  for w, p in zip(weights, closes, strict=True))) / (1 + D(".0005") * sum(weights))
        assert abs(result.net_factor - factor) < D("1e-45")
        assert cash == D("1e-45")
    ledger_target = nav.ThreeAssetTarget(weights, cash)
    replay = nav.replay((nav.ThreeAssetDay(ENTRY, (D(100),) * 3, (D(100),) * 3),
                         nav.ThreeAssetDay(EXIT, (D(100),) * 3, tuple(map(D, closes)))),
                        {ENTRY: ledger_target}, D(5))
    with localcontext(prep.CONTEXT):
        assert result.net_factor == replay.final_nav
        assert result.loss_label == (replay.final_nav < 1)
        assert abs(replay.total_fees - D(".0005") * replay.total_traded_notional) < D("1e-45")
    assert replay.final_state.quantities == (D(0),) * 3
    assert nav.SYMBOLS == ("SPY", "QQQ", "IWM")


@pytest.mark.parametrize("symbol,index", [("SPY", 0), ("TLT", 0), ("GLD", 0),
                                         ("SPY", 1), ("TLT", 1), ("GLD", 1)])
def test_target_endpoints_required_no_older_observation_fallback(symbol, index):
    rows = target_rows()
    rows[symbol] = tuple(row for i, row in enumerate(rows[symbol]) if i != index) + (
        prep.RawD1Price(symbol, date(2024, 2, 29), VINTAGE, open=D(100), close=D(100)),
    )
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        target(rows)


@pytest.mark.parametrize("schedule,code", [
    ((session(ENTRY), session(date(2024, 4, 1))), "target_month_invalid"),
    ((session(EXIT), session(ENTRY)), "calendar_order_invalid"),
])
def test_target_window_calendar_rejects_cross_month_or_disorder(schedule, code):
    with pytest.raises(CrossAssetInputUnavailable, match=code):
        target(schedule=schedule)


def test_target_scaling_and_hostile_context_and_mapping_order_do_not_change_factor():
    rows = target_rows()
    expected = target(rows)
    scaled = {symbol: (replace(rows[symbol][0], open=rows[symbol][0].open * scale),
                       replace(rows[symbol][1], close=rows[symbol][1].close * scale))
              for symbol, scale in zip(INSTRUMENT_ORDER, (2, 3, 5), strict=True)}
    with localcontext(prep.CONTEXT):
        assert abs(target(scaled).net_factor - expected.net_factor) < D("1e-45")
    assert target(scaled).loss_label == expected.loss_label
    assert target(dict(reversed(tuple(rows.items())))) == expected
    with localcontext() as context:
        context.prec = 6
        assert target(rows) == expected
        assert context.prec == 6


def test_target_ignores_unrequired_endpoint_fields_and_intermediate_marks():
    rows = target_rows()
    expected = target(rows)
    for symbol in INSTRUMENT_ORDER:
        first, last = rows[symbol]
        first = replace(first, close=D("999999"))
        last = replace(last, open=D(".000001"))
        rows[symbol] = (first, last,
                        prep.RawD1Price(symbol, date(2024, 3, 15), "other", close=D(1)))
    assert target(rows) == expected
    assert expected.safe_facts()["daily_mark_support"] == "not_checked"
    assert target({symbol: value[:2] for symbol, value in rows.items()}) == expected


def test_output_immutable_private_and_direct_constructor_label_shape_checks():
    f, t = features(), target()
    assert VINTAGE not in repr(f) + repr(t) + repr(past_rows()["SPY"][0])
    assert "net_factor" not in repr(t) and "features" not in repr(f)
    with pytest.raises(FrozenInstanceError):
        t.loss_label = not t.loss_label
    with pytest.raises(CrossAssetInputUnavailable, match="target_label_mismatch"):
        replace(t, loss_label=not t.loss_label)
    with pytest.raises(CrossAssetInputUnavailable, match="feature_matrix_invalid"):
        replace(f, features=f.features[:5])
    with pytest.raises(CrossAssetInputUnavailable, match="price_basis_invalid"):
        replace(past_rows()["SPY"][0], price_basis="adjusted")
    for result in (f, t):
        facts = result.safe_facts()
        assert facts["splits_and_dividends"] == "not_applied"
        assert facts["publication_availability"] == "not_observed"
        assert facts["paper_input"] is False
        assert all(not isinstance(value, Decimal) for value in facts.values())


def test_no_file_network_provider_model_or_future_target_dependency(monkeypatch):
    past, forward = past_rows(), target_rows()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unexpected IO")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    original = features(past)
    actual_target = target(forward)
    monkeypatch.setattr(prep, "build_monthly_target", forbidden)
    assert features(past) == original
    assert actual_target.entry_at == original.entry_at


def test_extreme_required_numeric_range_fails_categorically():
    rows = target_rows()
    first, last = rows["SPY"]
    rows["SPY"] = (replace(first, open=D("1e-999999")), replace(last, close=D("1e999999")))
    with pytest.raises(CrossAssetInputUnavailable, match="numeric_range") as caught:
        target(rows)
    assert str(caught.value) == "numeric_range"


def test_single_declared_session_target_has_both_fields_and_same_day_roundtrip():
    schedule = (session(date(2024, 11, 29), 13),)
    rows = {symbol: (prep.RawD1Price(symbol, schedule[0].session_date, VINTAGE,
                                    open=D(100), close=D(100)),) for symbol in INSTRUMENT_ORDER}
    result = target(rows, schedule)
    assert result.entry_at < result.exit_at and result.exit_at.hour == 18
    assert result.loss_label is True


def test_first_history_open_is_not_required_or_read():
    rows = past_rows()
    expected = features(rows)
    for symbol in INSTRUMENT_ORDER:
        first = replace(rows[symbol][0])
        object.__setattr__(first, "open", D("NaN"))
        rows[symbol] = (first, *rows[symbol][1:])
    assert features(rows) == expected


@pytest.mark.parametrize("offset", [D("-1e-47"), D(0), D("1e-47")])
def test_near_break_even_target_uses_exact_canonical_ledger_not_ideal_formula(offset):
    with localcontext(prep.CONTEXT):
        invested = 3 * prep.THIRD
        cash = 1 - invested
        fee = D(".0005")
        ratio = (1 + fee * invested - cash) / ((1 - fee) * invested) + offset
        opens = (D(7), D(11), D(13))
        closes = tuple(value * ratio for value in opens)
    rows = {symbol: (prep.RawD1Price(symbol, ENTRY, VINTAGE, open=opening),
                     prep.RawD1Price(symbol, EXIT, VINTAGE, close=closing))
            for symbol, opening, closing in zip(INSTRUMENT_ORDER, opens, closes, strict=True)}
    result = target(rows)
    canonical = nav.replay((nav.ThreeAssetDay(ENTRY, opens, opens),
                            nav.ThreeAssetDay(EXIT, closes, closes)),
                           {ENTRY: nav.ThreeAssetTarget((prep.THIRD,) * 3, cash)}, D(5))
    assert result.net_factor == canonical.final_nav
    assert result.loss_label == (canonical.final_nav < 1)
    with localcontext(prep.CONTEXT):
        assert abs(result.net_factor - 1) < D("1e-45")


def test_price_scaled_rounding_edge_matches_each_exact_canonical_replay():
    with localcontext(prep.CONTEXT):
        invested = 3 * prep.THIRD
        cash = 1 - invested
        ratio = (1 + D(".0005") * invested - cash) / ((1 - D(".0005")) * invested)
        factors = []
        for scales in ((1, 1, 1), (2, 3, 5)):
            opens = tuple(D(p) * scale for p, scale in zip((7, 11, 13), scales, strict=True))
            closes = tuple(value * ratio for value in opens)
            rows = {symbol: (prep.RawD1Price(symbol, ENTRY, VINTAGE, open=opening),
                             prep.RawD1Price(symbol, EXIT, VINTAGE, close=closing))
                    for symbol, opening, closing in zip(INSTRUMENT_ORDER, opens, closes,
                                                        strict=True)}
            result = target(rows)
            canonical = nav.replay((nav.ThreeAssetDay(ENTRY, opens, opens),
                                    nav.ThreeAssetDay(EXIT, closes, closes)),
                                   {ENTRY: nav.ThreeAssetTarget((prep.THIRD,) * 3, cash)}, D(5))
            assert result.net_factor == canonical.final_nav
            assert result.loss_label == (canonical.final_nav < 1)
            factors.append(result.net_factor)
        assert abs(factors[0] - factors[1]) < D("1e-45")
