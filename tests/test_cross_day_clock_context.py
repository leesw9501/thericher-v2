from __future__ import annotations

import builtins
import json
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from decimal import ROUND_DOWN, Decimal, Inexact, localcontext
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research.cross_day_clock_context import (
    CLOCKS,
    CONTEXT_SESSIONS,
    ClockSession,
    CrossDayClockInputUnavailable,
    build_cross_day_clock_context,
)

EASTERN = ZoneInfo("America/New_York")


def session(day: date, *, close_hour: int = 16) -> ClockSession:
    return ClockSession(
        session_date=day,
        open_ts=datetime.combine(day, time(9, 30), EASTERN).astimezone(UTC),
        close_ts=datetime.combine(day, time(close_hour), EASTERN).astimezone(UTC),
    )


def endpoint(item: ClockSession, label: str, *, exit_bar: bool = False) -> datetime:
    return datetime.combine(item.session_date, time.fromisoformat(label), EASTERN).astimezone(
        UTC
    ) + timedelta(minutes=31 if exit_bar else 1)


def bar(start: datetime, value: Decimal = Decimal(100), *, symbol: str = "SPY") -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=Decimal(0),
    )


def altered(original: Bar, **changes: object) -> Bar:
    result = replace(original)
    for key, value in changes.items():
        object.__setattr__(result, key, value)
    return result


@pytest.fixture
def panel():
    # Exactly 20 caller-attested sessions, crossing the March 2023 DST change.
    dates = tuple(
        date(2023, 2, 21) + timedelta(days=offset)
        for offset in range(28)
        if (date(2023, 2, 21) + timedelta(days=offset)).weekday() < 5
    )
    assert len(dates) == CONTEXT_SESSIONS
    sessions = tuple(session(day) for day in dates)
    bars = tuple(
        row
        for index, item in enumerate(sessions)
        for column, label in enumerate(CLOCKS)
        for row in (
            bar(endpoint(item, label)),
            bar(
                endpoint(item, label, exit_bar=True),
                Decimal(100) + Decimal((index + 1) * (column - 1)) / Decimal(100),
            ),
        )
    )
    return bars, {
        "symbol": "SPY",
        "scheduled_sessions": sessions,
        "decision_at": datetime(2023, 3, 21, 14, 0, tzinfo=UTC),
    }


def build(panel, bars=None, **changes):
    source, arguments = panel
    return build_cross_day_clock_context(source if bars is None else bars, **(arguments | changes))


def test_exact_signed_clock_means_and_unrounded_60_observation_pool(panel):
    result = build(panel)
    assert tuple(result.mean_return_bps_by_clock) == CLOCKS == ("10:00", "12:00", "14:00")
    assert result.mean_return_bps_by_clock == {
        "10:00": Decimal("-10.5"),
        "12:00": Decimal(0),
        "14:00": Decimal("10.5"),
    }
    assert result.pooled_mean_return_bps == 0
    assert result.scheduled_sessions == panel[1]["scheduled_sessions"]
    assert result.completed_through == endpoint(
        result.scheduled_sessions[-1], "14:00", exit_bar=True
    ) + timedelta(minutes=1)
    assert build(panel, tuple(reversed(panel[0]))) == result


def test_immutable_private_means_and_safe_geometry_only(panel):
    result = build(panel)
    assert "Decimal" not in repr(result) and "mean_return" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.pooled_mean_return_bps = Decimal(0)
    with pytest.raises(TypeError):
        result.mean_return_bps_by_clock["10:00"] = Decimal(0)
    with pytest.raises(FrozenInstanceError):
        result.scheduled_sessions[0].close_ts = result.decision_at
    facts = result.safe_facts()
    assert set(facts) == {
        "status",
        "session_count",
        "clocks_et",
        "clock_count",
        "observation_count_per_clock",
        "pooled_observation_count",
        "required_endpoint_count",
        "entry_offset_minutes",
        "exit_horizon_minutes",
        "history_start",
        "history_last_session",
        "completed_through",
        "decision_at",
    }
    assert facts["session_count"] == facts["observation_count_per_clock"] == 20
    assert facts["clock_count"] == 3 and facts["pooled_observation_count"] == 60
    assert facts["required_endpoint_count"] == 120
    assert "Decimal" not in json.dumps(facts)
    facts["session_count"] = 0
    assert result.safe_facts()["session_count"] == 20


@pytest.mark.parametrize("symbol", ["SPY", "QQQ", "IWM"])
def test_each_symbol_is_independent_and_has_same_clock_geometry(panel, symbol):
    bars = tuple(replace(item, symbol=symbol) for item in panel[0])
    result = build(panel, bars, symbol=symbol)
    assert result.symbol == symbol
    assert result.mean_return_bps_by_clock == build(panel).mean_return_bps_by_clock


@pytest.mark.parametrize("mutation", ["remove", "prices", "support", "complete", "identity"])
@pytest.mark.parametrize("future", [False, True])
def test_current_future_values_presence_and_completeness_do_not_mask_history(
    panel, mutation, future
):
    baseline = build(panel)
    start = panel[1]["decision_at"] + timedelta(days=5 if future else 0)
    outside = [bar(start), bar(start + timedelta(minutes=31))]
    if mutation == "remove":
        outside = []
    elif mutation == "prices":
        outside = [altered(item, open=Decimal("NaN")) for item in outside]
    elif mutation == "support":
        outside += [outside[0], SimpleNamespace(start_ts=start)]
    elif mutation == "complete":
        outside = [replace(item, complete=False) for item in outside]
    elif mutation == "identity":
        outside = [altered(item, symbol="OTHER", market="KR", timeframe=None) for item in outside]
    assert build(panel, (*outside, *panel[0], *outside)) == baseline


class _PoisonTimezone(tzinfo):
    def utcoffset(self, _value):
        raise ValueError("unusable timestamp")


@pytest.mark.parametrize(
    "start",
    [
        None,
        "synthetic-unusable-timestamp",
        datetime(2023, 3, 21, 14, 0),
        datetime(2023, 3, 21, 14, 0, tzinfo=_PoisonTimezone()),
        datetime.max.replace(tzinfo=timezone(timedelta(hours=-1))),
    ],
)
def test_unselectable_outside_timestamp_poison_is_irrelevant(panel, start):
    outside = SimpleNamespace(start_ts=start, open=Decimal("NaN"), complete=False)
    assert build(panel, (outside, *panel[0])) == build(panel)


def test_only_endpoint_open_values_are_consumed(panel):
    bars = tuple(
        altered(item, high=Decimal("NaN"), low=None, close=Decimal("Infinity"), volume=-1)
        for item in panel[0]
    )
    interior = tuple(
        SimpleNamespace(start_ts=item.start_ts + timedelta(minutes=1), open=None, complete=False)
        for item in bars
    )
    assert build(panel, (*bars, *interior)) == build(panel)


@pytest.mark.parametrize("clock", CLOCKS)
@pytest.mark.parametrize("exit_bar", [False, True])
def test_missing_required_endpoint_is_unavailable_without_older_date_imputation(
    panel, clock, exit_bar
):
    target = endpoint(panel[1]["scheduled_sessions"][5], clock, exit_bar=exit_bar)
    old = session(panel[1]["scheduled_sessions"][0].session_date - timedelta(days=4))
    substitutes = tuple(
        bar(endpoint(old, label, exit_bar=exit_flag))
        for label in CLOCKS
        for exit_flag in (False, True)
    )
    bars = tuple(item for item in panel[0] if item.start_ts != target)
    with pytest.raises(CrossDayClockInputUnavailable, match="^required_endpoint_missing$"):
        build(panel, (*substitutes, *bars))


@pytest.mark.parametrize("conflicting", [False, True])
def test_identical_or_conflicting_required_duplicate_is_unavailable(panel, conflicting):
    duplicate = panel[0][0]
    if conflicting:
        duplicate = bar(duplicate.start_ts, Decimal(101))
    with pytest.raises(CrossDayClockInputUnavailable, match="^required_endpoint_duplicate$"):
        build(panel, (*panel[0], duplicate))


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"symbol": "QQQ"}, "required_endpoint_identity"),
        ({"market": "KR"}, "required_endpoint_identity"),
        ({"timeframe": Timeframe.M5}, "required_endpoint_identity"),
        ({"complete": False}, "required_endpoint_incomplete"),
        ({"complete": 1}, "required_endpoint_incomplete"),
        ({"open": Decimal(0)}, "required_endpoint_open_invalid"),
        ({"open": Decimal(-1)}, "required_endpoint_open_invalid"),
        ({"open": Decimal("NaN")}, "required_endpoint_open_invalid"),
        ({"open": Decimal("Infinity")}, "required_endpoint_open_invalid"),
        ({"open": 100}, "required_endpoint_open_invalid"),
    ],
)
def test_invalid_required_endpoint_is_scoped_unavailable(panel, changes, reason):
    bars = (altered(panel[0][0], **changes), *panel[0][1:])
    with pytest.raises(CrossDayClockInputUnavailable, match=f"^{reason}$") as raised:
        build(panel, bars)
    assert raised.value.safe_facts() == {"status": "input_unavailable", "reason_code": reason}
    assert "Decimal" not in str(raised.value)


def test_required_non_bar_object_is_unavailable(panel):
    bars = (SimpleNamespace(start_ts=panel[0][0].start_ts), *panel[0][1:])
    with pytest.raises(CrossDayClockInputUnavailable, match="^required_endpoint_identity$"):
        build(panel, bars)


def test_required_timestamp_non_utc_identity_is_unavailable(panel):
    original = panel[0][0]
    changed = altered(original, start_ts=original.start_ts.astimezone(EASTERN))
    with pytest.raises(CrossDayClockInputUnavailable, match="^required_endpoint_identity$"):
        build(panel, (changed, *panel[0][1:]))


@pytest.mark.parametrize("index", [0, 19])
def test_prior_early_close_makes_common_three_clock_history_unavailable(panel, index):
    sessions = list(panel[1]["scheduled_sessions"])
    sessions[index] = session(sessions[index].session_date, close_hour=13)
    with pytest.raises(
        CrossDayClockInputUnavailable, match="^required_clock_geometry_unsupported$"
    ):
        build(panel, scheduled_sessions=sessions)


def test_current_early_close_clock_is_not_in_history_contract(panel):
    # Current-date scheduling is the consumer's separate plan, not this past join.
    current = session(panel[1]["decision_at"].date(), close_hour=13)
    unsupported = bar(endpoint(current, "14:00"))
    assert build(panel, (*panel[0], unsupported)) == build(panel)


def test_dst_conversion_uses_fixed_eastern_clocks_not_fixed_utc(panel):
    sessions = panel[1]["scheduled_sessions"]
    assert endpoint(sessions[0], "10:00").hour == 15
    assert endpoint(sessions[-1], "10:00").hour == 14
    assert build(panel).safe_facts()["required_endpoint_count"] == 120


@pytest.mark.parametrize("count", [0, 19, 21])
def test_exact_20_scheduled_dates_not_available_rows(panel, count):
    sessions = panel[1]["scheduled_sessions"][:count]
    if count == 21:
        sessions = (session(date(2023, 2, 17)), *sessions)
    with pytest.raises(ValueError, match="^scheduled_sessions$"):
        build(panel, scheduled_sessions=sessions)


@pytest.mark.parametrize("mutation", ["duplicate", "reversed", "wrong_type", "current"])
def test_caller_schedule_must_be_ordered_exact_past_sessions(panel, mutation):
    sessions = list(panel[1]["scheduled_sessions"])
    if mutation == "duplicate":
        sessions[1] = sessions[0]
    elif mutation == "reversed":
        sessions.reverse()
    elif mutation == "wrong_type":
        sessions[0] = sessions[0].session_date
    elif mutation == "current":
        sessions[-1] = session(panel[1]["decision_at"].date())
    with pytest.raises(ValueError, match="^scheduled_sessions(_not_past)?$"):
        build(panel, scheduled_sessions=sessions)


@pytest.mark.parametrize(
    "changes",
    [
        {"session_date": "2023-03-20"},
        {"open_ts": datetime(2023, 3, 20, 13, 30)},
        {"open_ts": datetime(2023, 3, 20, 9, 30, tzinfo=EASTERN)},
        {"close_ts": datetime(2023, 3, 20, 13, 0, tzinfo=UTC)},
        {"session_date": date(2023, 3, 21)},
    ],
)
def test_session_dto_rejects_invalid_date_utc_or_boundaries(changes):
    with pytest.raises(ValueError):
        replace(session(date(2023, 3, 20)), **changes)


@pytest.mark.parametrize(
    "decision", [None, datetime(2023, 3, 21, 14, 0), datetime(2023, 3, 21, 10, 0, tzinfo=EASTERN)]
)
def test_decision_requires_explicit_utc(panel, decision):
    with pytest.raises(ValueError, match="^decision_at_utc$"):
        build(panel, decision_at=decision)


def test_decimal_arithmetic_is_signed_and_ambient_context_independent(panel):
    bars = tuple(
        bar(item.start_ts, Decimal(3) if index % 2 == 0 else Decimal(1))
        for index, item in enumerate(panel[0])
    )
    expected = build(panel, bars)
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        assert build(panel, bars) == expected
    assert all(
        type(value) is Decimal and value.is_finite() and value < 0
        for value in expected.mean_return_bps_by_clock.values()
    )
    assert expected.pooled_mean_return_bps < 0


def test_pure_helper_has_no_io_or_current_value_lookup(panel, monkeypatch):
    baseline = build(panel)

    def deny(*_args, **_kwargs):
        raise AssertionError("I/O forbidden")

    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    assert build(panel) == baseline
