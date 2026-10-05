from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SUPPORTED_RESAMPLE_TIMEFRAMES, SessionWindow
from thericher_v2.research import paired_completed_context as context_module
from thericher_v2.research.paired_completed_context import build_paired_completed_context

MINUTE = timedelta(minutes=1)
OPEN = datetime(2023, 7, 5, 13, 30, tzinfo=UTC)
SESSION = SessionWindow(OPEN, OPEN + 390 * MINUTE)


def test_short_source_fails_before_allocating_a_large_expected_grid(monkeypatch):
    def forbidden(*_args):
        pytest.fail("an unavailable context must not allocate its expected grid")

    monkeypatch.setattr(context_module, "range", forbidden, raising=False)
    session = SessionWindow(OPEN, OPEN + timedelta(days=10000))
    with pytest.raises(ValueError, match="required M1 starts"):
        build_paired_completed_context(
            (),
            (),
            own_symbol="QQQ",
            peer_symbol="SPY",
            session=session,
            observed_at=session.close_ts,
            timeframe=Timeframe.M1,
            context_bars=10000000,
        )


def _minutes(symbol, session=SESSION):
    base = Decimal(100 if symbol == "QQQ" else 200)
    return tuple(
        Bar(
            symbol,
            "US",
            Timeframe.M1,
            session.open_ts + i * MINUTE,
            base + i,
            base + i + 2,
            base + i - 1,
            base + i + 1,
            Decimal(i + 1),
        )
        for i in range(session.duration // MINUTE)
    )


@pytest.fixture
def pair():
    return _minutes("QQQ"), _minutes("SPY")


def _context(own, peer, **changes):
    arguments = dict(
        own_symbol="QQQ",
        peer_symbol="SPY",
        session=SESSION,
        observed_at=OPEN + 240 * MINUTE,
        timeframe=Timeframe.M5,
        context_bars=12,
    )
    return build_paired_completed_context(own, peer, **(arguments | changes))


@pytest.mark.parametrize(
    "frame,count,offset,end",
    [
        (Timeframe.M1, 1, 240.5, 240),
        (Timeframe.M1, 7, 61, 61),
        (Timeframe.M5, 3, 61, 60),
        (Timeframe.M10, 4, 129, 120),
        (Timeframe.H1, 1, 239, 180),
        (Timeframe.H1, 3, 240, 240),
        (Timeframe.H3, 1, 240, 180),
        (Timeframe.H3, 2, 390, 360),
    ],
)
def test_exact_completed_context_and_ohlcv(pair, frame, count, offset, end):
    context = _context(
        *pair, timeframe=frame, context_bars=count, observed_at=OPEN + offset * MINUTE
    )
    assert context.completed_through == OPEN + end * MINUTE
    assert context.history_start == context.completed_through - count * frame.duration
    assert context.observed_at - context.completed_through == (offset - end) * MINUTE
    assert (context.own_symbol, context.peer_symbol, context.timeframe) == ("QQQ", "SPY", frame)
    for source, result in zip(pair, (context.own_bars, context.peer_bars), strict=True):
        assert isinstance(result, tuple) and len(result) == count
        for i, bar in enumerate(result):
            start = context.history_start + i * frame.duration
            minutes = tuple(b for b in source if start <= b.start_ts < start + frame.duration)
            assert (bar.start_ts, bar.end_ts, bar.timeframe, bar.complete) == (
                start,
                start + frame.duration,
                frame,
                True,
            )
            assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (
                minutes[0].open,
                minutes[-1].high,
                minutes[0].low,
                minutes[-1].close,
                sum(b.volume for b in minutes),
            )


@pytest.mark.parametrize(
    "opened,length",
    [
        (datetime(2022, 3, 11, 14, 30, tzinfo=UTC), 390),
        (datetime(2022, 3, 14, 13, 30, tzinfo=UTC), 390),
        (datetime(2023, 11, 24, 14, 30, tzinfo=UTC), 210),
    ],
)
@pytest.mark.parametrize("frame", SUPPORTED_RESAMPLE_TIMEFRAMES)
def test_actual_session_anchor_dst_and_early_close(opened, length, frame):
    session = SessionWindow(opened, opened + length * MINUTE)
    context = _context(
        _minutes("QQQ", session),
        _minutes("SPY", session),
        session=session,
        observed_at=session.close_ts,
        timeframe=frame,
        context_bars=1,
    )
    end = opened + (session.duration // frame.duration) * frame.duration
    assert context.completed_through == end <= session.close_ts
    assert context.own_bars[0].start_ts == context.peer_bars[0].start_ts == end - frame.duration


def test_context_is_frozen_and_has_no_provenance_or_target_surface(pair):
    context = _context(*pair)
    assert tuple(f.name for f in fields(context)) == (
        "own_symbol",
        "peer_symbol",
        "timeframe",
        "observed_at",
        "history_start",
        "completed_through",
        "own_bars",
        "peer_bars",
    )
    assert "QQQ" not in repr(context) and "Decimal" not in repr(context)
    with pytest.raises(FrozenInstanceError):
        context.completed_through = OPEN


@pytest.mark.parametrize("side", [0, 1])
@pytest.mark.parametrize("fault", ["missing", "duplicate", "incomplete", "order", "offgrid"])
def test_required_minute_fault_rejects_only_exact_context(pair, side, fault):
    sources = list(pair)
    bars = list(sources[side])
    if fault == "missing":
        del bars[205]
    elif fault == "duplicate":
        bars.insert(205, bars[205])
    elif fault == "incomplete":
        bars[205] = replace(bars[205], complete=False)
    elif fault == "order":
        bars[205], bars[206] = bars[206], bars[205]
    else:
        bars[205] = replace(bars[205], start_ts=bars[205].start_ts + timedelta(seconds=1))
    sources[side] = bars
    with pytest.raises(ValueError, match="required M1"):
        _context(*sources)
    assert _context(*sources, observed_at=OPEN + 300 * MINUTE) == _context(
        *pair, observed_at=OPEN + 300 * MINUTE
    )


@pytest.mark.parametrize("side", [0, 1])
@pytest.mark.parametrize(
    "change",
    [
        {"symbol": "IWM"},
        {"market": "KR"},
        {"timeframe": Timeframe.M5},
    ],
)
def test_required_identity_is_explicit(pair, side, change):
    sources = list(pair)
    bars = list(sources[side])
    bars[205] = replace(bars[205], **change)
    sources[side] = bars
    with pytest.raises(ValueError, match="declared symbol, US market and M1"):
        _context(*sources)


def test_wrong_entire_symbol_and_identical_pair_rejected(pair):
    with pytest.raises(ValueError, match="declared symbol"):
        _context(_minutes("IWM"), pair[1])
    with pytest.raises(ValueError, match="distinct"):
        _context(pair[0], pair[0], peer_symbol="QQQ")


@pytest.mark.parametrize("side", [0, 1])
@pytest.mark.parametrize("frame,count,end", [(Timeframe.M5, 12, 240), (Timeframe.H3, 1, 180)])
def test_outside_required_window_changes_and_removal_are_irrelevant(pair, side, frame, count, end):
    arguments = dict(timeframe=frame, context_bars=count)
    baseline = _context(*pair, **arguments)
    source = pair[side]
    required = tuple(
        b for b in source if baseline.history_start <= b.start_ts < OPEN + end * MINUTE
    )
    changed = list(required)
    for index in (0 if end == 240 else 200, end, 350):
        bar = replace(source[index])
        for name, value in dict(
            symbol="OTHER",
            market="KR",
            timeframe=Timeframe.H3,
            complete=False,
            open=Decimal("NaN"),
            volume=-1,
        ).items():
            object.__setattr__(bar, name, value)
        changed.insert(0, bar)
        changed.append(bar)
    changed.append(replace(source[0], start_ts=OPEN - MINUTE))
    changed.append(replace(source[0], start_ts=SESSION.close_ts + MINUTE))
    for replacement in (required, changed):
        sources = list(pair)
        sources[side] = replacement
        assert _context(*sources, **arguments) == baseline


@pytest.mark.parametrize(
    "field,value",
    [
        ("open", Decimal("NaN")),
        ("high", Decimal("0")),
        ("volume", Decimal("-1")),
    ],
)
def test_required_values_use_bar_contract_validation(pair, field, value):
    own = list(pair[0])
    own[205] = replace(own[205])
    object.__setattr__(own[205], field, value)
    with pytest.raises(ValueError):
        _context(own, pair[1])


@pytest.mark.parametrize("count", [True, False, 0, -1, 1.0, "1", None, 10**100])
def test_context_count_is_strict_and_session_bounded(pair, count):
    with pytest.raises(ValueError, match="context"):
        _context(*pair, context_bars=count)


@pytest.mark.parametrize(
    "observed",
    [
        OPEN.replace(tzinfo=None),
        OPEN - MINUTE,
        SESSION.close_ts + MINUTE,
        None,
    ],
)
def test_observation_must_be_utc_inside_session(pair, observed):
    with pytest.raises(ValueError, match="observed_at"):
        _context(*pair, observed_at=observed)


def test_offset_equivalent_observations_return_canonical_utc(pair):
    observed = OPEN + 240 * MINUTE
    context = _context(*pair, observed_at=observed.astimezone(timezone(timedelta(hours=9))))
    assert context == _context(*pair, observed_at=observed)
    assert context.observed_at.tzinfo is UTC


@pytest.mark.parametrize(
    "offset,frame,count",
    [
        (0, Timeframe.M1, 1),
        (4, Timeframe.M5, 1),
        (60, Timeframe.M5, 13),
        (240, Timeframe.H3, 2),
    ],
)
def test_context_cannot_cross_session_open_even_with_prior_session_data(pair, offset, frame, count):
    previous = replace(pair[0][0], start_ts=OPEN - MINUTE)
    with pytest.raises(ValueError, match="inside this session"):
        _context(
            (previous, *pair[0]),
            pair[1],
            observed_at=OPEN + offset * MINUTE,
            timeframe=frame,
            context_bars=count,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"timeframe": Timeframe.D1},
        {"timeframe": "5m"},
        {"session": None},
        {"own_symbol": ""},
        {"peer_symbol": "spy"},
        {"own_symbol": " QQQ"},
    ],
)
def test_invalid_declared_contract(pair, changes):
    with pytest.raises(ValueError):
        _context(*pair, **changes)
