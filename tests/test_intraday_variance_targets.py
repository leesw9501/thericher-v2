from copy import copy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_FLOOR, Decimal, Inexact, localcontext
from math import isfinite, log
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.intraday_variance_targets import (
    IntradayVarianceTarget,
    build_intraday_variance_target,
)
from thericher_v2.research.paired_completed_context import build_paired_completed_context

MINUTE = timedelta(minutes=1)
OPEN = datetime(2023, 7, 5, 13, 30, tzinfo=UTC)
SESSION = SessionWindow(OPEN, OPEN + 390 * MINUTE)
DECISION = OPEN + 150 * MINUTE
ENTRY = DECISION + MINUTE
END = ENTRY + 60 * MINUTE
AVAILABLE = END + MINUTE


def _bar(at, price=Decimal(100), **changes):
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=at,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(0),
        **changes,
    )


def _bars(prices=None):
    prices = [Decimal(100)] * 61 if prices is None else prices
    return tuple(_bar(ENTRY + index * MINUTE, price) for index, price in enumerate(prices))


def _build(bars=None, **changes):
    arguments = dict(
        symbol="QQQ", session=SESSION, decision_at=DECISION, observed_at=AVAILABLE
    )
    return build_intraday_variance_target(
        _bars() if bars is None else bars, **(arguments | changes)
    )


def _corrupt(value, **changes):
    result = copy(value)
    for name, replacement in changes.items():
        object.__setattr__(result, name, replacement)
    return result


def test_constant_series_and_exact_default_timing():
    target = _build()
    assert isinstance(target, IntradayVarianceTarget)
    assert target.symbol == "QQQ"
    assert target.decision_at == DECISION
    assert target.horizon_minutes == 60
    assert target.target_start == ENTRY
    assert target.target_end == END
    assert target.available_at == AVAILABLE
    assert target.realized_variance == 0.0
    assert _build(observed_at=SESSION.close_ts + MINUTE) == target


@pytest.mark.parametrize("factor", [Decimal(2), Decimal("0.5"), Decimal("1.01")])
def test_geometric_series(factor):
    bars = _bars([Decimal(100) * factor**index for index in range(61)])
    assert _build(bars).realized_variance == pytest.approx(60 * log(float(factor)) ** 2, rel=1e-13)


def test_target_is_immutable_and_exposes_no_source_rows():
    target = _build()
    assert tuple(field.name for field in fields(target)) == (
        "symbol",
        "decision_at",
        "horizon_minutes",
        "target_start",
        "target_end",
        "available_at",
        "realized_variance",
    )
    assert "QQQ" not in repr(target) and "Decimal" not in repr(target)
    assert not hasattr(target, "__dict__")
    with pytest.raises(FrozenInstanceError):
        target.realized_variance = 1.0


@pytest.mark.parametrize("symbol", ["", "qqq", " QQQ", "QQQ ", None, True, 1])
def test_reject_noncanonical_declared_symbol(symbol):
    with pytest.raises(ValueError, match="canonical symbol"):
        _build(symbol=symbol)


@pytest.mark.parametrize("horizon", [True, False, 0, -1, 60.0, "60", None, 10**100])
def test_reject_invalid_or_unbounded_horizon(horizon):
    with pytest.raises(ValueError, match="horizon_minutes"):
        _build(horizon_minutes=horizon)


def test_one_minute_horizon_requires_two_opens():
    target = _build(_bars([Decimal(100), Decimal(200)]), horizon_minutes=1)
    assert target.target_end == ENTRY + MINUTE
    assert target.available_at == ENTRY + 2 * MINUTE
    assert target.realized_variance == pytest.approx(log(2) ** 2)


@pytest.mark.parametrize("name", ["decision_at", "observed_at"])
@pytest.mark.parametrize("fault", ["naive", "offset", "seconds", "microseconds", "wrong_type"])
def test_strict_declared_time(name, fault):
    value = DECISION if name == "decision_at" else AVAILABLE
    values = {
        "naive": value.replace(tzinfo=None),
        "offset": value.astimezone(timezone(timedelta(hours=9))),
        "seconds": value + timedelta(seconds=1),
        "microseconds": value + timedelta(microseconds=1),
        "wrong_type": "2023-07-05T16:02:00Z",
    }
    with pytest.raises(ValueError, match="UTC and minute-aligned"):
        _build(**{name: values[fault]})


@pytest.mark.parametrize("endpoint", ["open_ts", "close_ts"])
@pytest.mark.parametrize("fault", ["naive", "offset", "seconds", "microseconds"])
def test_strict_session_time(endpoint, fault):
    value = getattr(SESSION, endpoint)
    values = {
        "naive": value.replace(tzinfo=None),
        "offset": value.astimezone(timezone(timedelta(hours=9))),
        "seconds": value + timedelta(seconds=1),
        "microseconds": value + timedelta(microseconds=1),
    }
    with pytest.raises(ValueError, match="UTC and minute-aligned"):
        _build(session=_corrupt(SESSION, **{endpoint: values[fault]}))


def test_reject_wrong_session_type_and_reversed_session():
    with pytest.raises(ValueError, match="SessionWindow"):
        _build(session=None)
    with pytest.raises(ValueError, match="inside the session"):
        _build(session=_corrupt(SESSION, close_ts=SESSION.open_ts))


@pytest.mark.parametrize("decision", [OPEN - MINUTE, SESSION.close_ts, SESSION.close_ts + MINUTE])
def test_decision_must_be_inside_session(decision):
    with pytest.raises(ValueError, match="inside the session"):
        _build(decision_at=decision)


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "SPY"},
        {"symbol": "qqq"},
        {"market": "KR"},
        {"market": "us"},
        {"timeframe": Timeframe.M5},
        {"timeframe": "1m"},
    ],
)
def test_required_bar_identity(changes):
    bars = list(_bars())
    bars[30] = _corrupt(bars[30], **changes)
    with pytest.raises(ValueError, match="identity"):
        _build(bars)


def test_reject_non_bar_with_required_start():
    bars = list(_bars())
    bars[30] = SimpleNamespace(start_ts=bars[30].start_ts)
    with pytest.raises(ValueError, match="identity"):
        _build(bars)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "duplicate_replacement", "reordered"])
def test_exact_ordered_unique_contiguous_starts(fault):
    bars = list(_bars())
    if fault == "missing":
        del bars[30]
    elif fault == "duplicate":
        bars.insert(30, bars[30])
    elif fault == "duplicate_replacement":
        bars[30] = bars[29]
    else:
        bars[29], bars[30] = bars[30], bars[29]
    with pytest.raises(ValueError, match="exact, ordered, unique and contiguous"):
        _build(bars)


@pytest.mark.parametrize("index", [0, 30, 60])
@pytest.mark.parametrize("fault", ["seconds", "offset", "naive"])
def test_required_start_timing(index, fault):
    bars = list(_bars())
    at = bars[index].start_ts
    at = {
        "seconds": at + timedelta(seconds=1),
        "offset": at.astimezone(timezone(timedelta(hours=9))),
        "naive": at.replace(tzinfo=None),
    }[fault]
    bars[index] = _corrupt(bars[index], start_ts=at)
    with pytest.raises(ValueError):
        _build(bars)


@pytest.mark.parametrize("index", [0, 30, 60])
@pytest.mark.parametrize("completion", [False, None, 1, "true"])
def test_all_required_bars_must_be_explicitly_complete(index, completion):
    bars = list(_bars())
    bars[index] = _corrupt(bars[index], complete=completion)
    with pytest.raises(ValueError, match="explicitly complete"):
        _build(bars)


@pytest.mark.parametrize("observed", [DECISION, END, AVAILABLE - MINUTE])
def test_final_open_does_not_make_incomplete_final_bar_available(observed):
    with pytest.raises(ValueError, match="completed by observed_at"):
        _build(observed_at=observed)


def test_early_close_accepts_last_open_one_minute_before_close():
    session = SessionWindow(OPEN, OPEN + 210 * MINUTE)
    decision = OPEN + 148 * MINUTE
    bars = tuple(_bar(decision + (index + 1) * MINUTE) for index in range(61))
    target = _build(bars, session=session, decision_at=decision, observed_at=session.close_ts)
    assert target.target_end == session.close_ts - MINUTE
    assert target.available_at == session.close_ts


@pytest.mark.parametrize("offset", [149, 150])
def test_early_close_rejects_end_open_at_or_after_close(offset):
    session = SessionWindow(OPEN, OPEN + 210 * MINUTE)
    with pytest.raises(ValueError, match="bounded by the session"):
        _build(session=session, decision_at=OPEN + offset * MINUTE)


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
@pytest.mark.parametrize("value", [Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")])
def test_required_price_values_must_be_positive_and_finite(field, value):
    bars = list(_bars())
    bars[30] = _corrupt(bars[30], **{field: value})
    with pytest.raises(ValueError):
        _build(bars)


@pytest.mark.parametrize(
    "changes",
    [
        {"open": "100"},
        {"high": Decimal(99)},
        {"low": Decimal(101)},
        {"volume": Decimal(-1)},
        {"volume": Decimal("NaN")},
    ],
)
def test_required_malformed_values_and_ohlc(changes):
    bars = list(_bars())
    bars[30] = _corrupt(bars[30], **changes)
    with pytest.raises(ValueError):
        _build(bars)


def test_unrelated_malformed_source_does_not_change_target():
    before = _corrupt(_bar(ENTRY - MINUTE), open=Decimal("NaN"), complete=None, symbol="wrong")
    after = _corrupt(_bar(AVAILABLE), open=Decimal(-1), market="KR", timeframe="bad")
    unlocated = [None, object(), SimpleNamespace(start_ts="not a timestamp")]
    assert _build([*unlocated, before, *_bars(), after]) == _build()
    assert _build([after, *_bars(), before, *unlocated]) == _build()


def test_later_future_price_and_missingness_are_irrelevant():
    later = tuple(_bar(AVAILABLE + index * MINUTE, Decimal(10) ** index) for index in range(8))
    assert _build([*_bars(), *later]) == _build()
    assert _build([*_bars(), *reversed(later)]) == _build()
    assert _build([*_bars(), _corrupt(later[0], open=Decimal("Infinity"))]) == _build()


def test_required_forward_open_mutation_changes_label_only():
    bars = list(_bars())
    bars[30] = _bar(bars[30].start_ts, Decimal(200))
    target = _build(bars)
    assert target.realized_variance == pytest.approx(2 * log(2) ** 2)
    assert (target.decision_at, target.target_start, target.target_end, target.available_at) == (
        DECISION, ENTRY, END, AVAILABLE
    )


@pytest.mark.parametrize("fault", ["price", "missing", "incomplete"])
def test_forward_target_faults_never_change_past_context_or_baseline(fault):
    own = tuple(_bar(OPEN + index * MINUTE) for index in range(212))
    peer = tuple(replace(bar, symbol="SPY") for bar in own)

    def context(source):
        return build_paired_completed_context(
            source,
            peer,
            own_symbol="QQQ",
            peer_symbol="SPY",
            session=SESSION,
            observed_at=DECISION,
            timeframe=Timeframe.M1,
            context_bars=120,
        )

    original = context(own)
    assert _build(own).realized_variance == 0.0
    changed = list(own)
    index = 180
    if fault == "price":
        changed[index] = _bar(changed[index].start_ts, Decimal(200))
        assert _build(changed).realized_variance > 0
    else:
        if fault == "missing":
            del changed[index]
        else:
            changed[index] = replace(changed[index], complete=False)
        with pytest.raises(ValueError):
            _build(changed)
    rebuilt = context(changed)
    assert rebuilt == original
    # The past-only naive risk forecast uses these same last 61 input OPENs.
    assert tuple(bar.open for bar in rebuilt.own_bars[-61:]) == tuple(
        bar.open for bar in original.own_bars[-61:]
    )


def test_non_open_values_do_not_enter_variance():
    bars = tuple(
        replace(bar, high=Decimal(200), low=Decimal(50), close=Decimal(150), volume=Decimal(7))
        for bar in _bars()
    )
    assert _build(bars) == _build()


@pytest.mark.parametrize("exponent", [-1000, 1000])
def test_prices_outside_float_range_retain_small_log_difference(exponent):
    left, right = Decimal(f"1e{exponent}"), Decimal(f"2e{exponent}")
    target = _build(_bars([left, right]), horizon_minutes=1)
    assert target.realized_variance == pytest.approx(log(2) ** 2, rel=1e-13)


@pytest.mark.parametrize("exponents", [(-10000, 10000), (10000, -10000)])
def test_ratio_overflow_and_underflow_are_avoided(exponents):
    prices = [Decimal(f"1e{exponent}") for exponent in exponents]
    target = _build(_bars(prices), horizon_minutes=1)
    assert isfinite(target.realized_variance)
    assert target.realized_variance == pytest.approx((20000 * log(10)) ** 2, rel=1e-13)


def test_tiny_change_at_huge_price_avoids_log_cancellation():
    prices = [Decimal("1e1000"), Decimal("1.000000000001e1000")]
    target = _build(_bars(prices), horizon_minutes=1)
    assert target.realized_variance == pytest.approx(1e-24, rel=2e-12)


def test_variance_does_not_depend_on_ambient_decimal_context():
    bars = _bars([Decimal(100) * Decimal(2) ** index for index in range(61)])
    expected = _build(bars)
    with localcontext() as context:
        context.prec = 1
        context.rounding = ROUND_FLOOR
        context.traps[Inexact] = True
        assert _build(bars) == expected
