from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.intraday_noise_band import (
    NoiseBandHistoryEntry,
    build_intraday_noise_band,
)


def _bar(start, opening="100", closing="100"):
    opening, closing = Decimal(opening), Decimal(closing)
    return Bar("SPY", "NYS", Timeframe.M5, start, opening, max(opening, closing),
               min(opening, closing), closing, Decimal(0))


def _inputs():
    # Explicit synthetic sessions around the US spring DST change; no calendar lookup.
    opening = datetime(2026, 3, 9, 13, 30, tzinfo=UTC)
    session = SessionWindow(opening, opening + timedelta(hours=6, minutes=30))
    bars = [_bar(opening, "200", "190"), _bar(opening + timedelta(minutes=5), "190", "199")]
    history = []
    for i, days in enumerate((20, 19, 18, 17, 16, 13, 12, 11, 10, 9, 6, 5, 4, 3)):
        start = (opening - timedelta(days=days)).replace(hour=14)
        prior = SessionWindow(start, start + timedelta(hours=6, minutes=30))
        close = str(100 + (i + 1) * (1 if i % 2 else -1))
        history.append(NoiseBandHistoryEntry(prior, [
            _bar(start), _bar(start + timedelta(minutes=5), "100", close),
        ]))
    return dict(bars=bars, history=history, session=session, as_of=bars[-1].end_ts)


def test_exact_mean_dst_alignment_frozen_output_and_unchanged_buffers():
    args = _inputs()
    originals = args["bars"].copy(), args["history"].copy()
    prior_buffers = [entry.bars.copy() for entry in args["history"]]
    result = build_intraday_noise_band(**args)
    assert (result.sigma, result.upper, result.lower) == (
        Decimal("0.075"), Decimal("215"), Decimal("185"),
    )
    assert (result.history_count, result.current_bar_count) == (14, 2)
    assert result.feature_window_end == args["as_of"]
    assert args["session"].open_ts.hour == 13
    assert all(entry.session.open_ts.hour == 14 for entry in args["history"])
    assert (args["bars"], args["history"]) == originals
    assert [entry.bars for entry in args["history"]] == prior_buffers
    with pytest.raises(FrozenInstanceError):
        result.sigma = Decimal(0)


@pytest.mark.parametrize("price,volume", [("1", "0"), ("1000000000", "999999999")])
def test_future_current_and_prior_tail_ohlcv_cannot_change_output(price, volume, monkeypatch):
    args = _inputs()
    expected = build_intraday_noise_band(**args)
    future = replace(_bar(args["as_of"], price, price), volume=Decimal(volume), complete=False)
    args["bars"].append(future)
    for entry in args["history"]:
        entry.bars.append(replace(future, start_ts=entry.bars[-1].end_ts))
    assert build_intraday_noise_band(**args) == expected
    future_ids = {id(future), *(id(entry.bars[-1]) for entry in args["history"])}
    original_get = Bar.__getattribute__

    def guarded_get(bar, name):
        if id(bar) in future_ids and name in {"open", "high", "low", "close", "volume"}:
            raise AssertionError("future price/volume was accessed")
        return original_get(bar, name)

    monkeypatch.setattr(Bar, "__getattribute__", guarded_get)
    assert build_intraday_noise_band(**args) == expected


def test_zero_sigma_and_unclamped_large_band_at_session_close():
    args = _inputs()
    args["session"] = replace(args["session"], close_ts=args["as_of"])
    for close, sigma in [("100", Decimal(0)), ("300", Decimal(2))]:
        for entry in args["history"]:
            entry.bars[-1] = _bar(entry.bars[-1].start_ts, "100", close)
        result = build_intraday_noise_band(**args)
        assert result.sigma == sigma
        assert result.lower == Decimal(200) * (1 - sigma)


@pytest.mark.parametrize("count", [0, 13, 15])
def test_requires_exactly_fourteen_chosen_sessions(count):
    args = _inputs()
    args["history"] = (args["history"] + args["history"][:1])[:count]
    with pytest.raises(ValueError, match="fourteen"):
        build_intraday_noise_band(**args)


@pytest.mark.parametrize("fault", ["duplicate", "reverse", "overlap", "history_overlap",
                                   "current", "same_day", "short", "history_gap", "history_symbol",
                                   "history_market"])
def test_rejects_invalid_history(fault):
    args = _inputs()
    entries = args["history"]
    if fault == "duplicate":
        entries[1] = entries[0]
    elif fault == "reverse":
        entries.reverse()
    elif fault == "history_overlap":
        entries[0] = replace(entries[0], session=replace(
            entries[0].session, close_ts=entries[1].session.open_ts + timedelta(minutes=5)))
    elif fault in {"overlap", "current", "same_day", "short"}:
        prior = entries[-1].session
        if fault == "overlap":
            prior = replace(prior, close_ts=args["session"].open_ts + timedelta(minutes=5))
        elif fault == "current":
            prior = args["session"]
        elif fault == "same_day":
            prior = SessionWindow(args["session"].open_ts - timedelta(hours=1),
                                  args["session"].open_ts)
        else:
            prior = replace(prior, close_ts=prior.open_ts + timedelta(minutes=5))
        entries[-1] = replace(entries[-1], session=prior)
    elif fault == "history_gap":
        entries[0].bars.pop()
    else:
        field, value = ("symbol", "QQQ") if fault == "history_symbol" else ("market", "NAS")
        entries[0] = replace(entries[0], bars=[replace(bar, **{field: value})
                                             for bar in entries[0].bars])
    with pytest.raises(ValueError):
        build_intraday_noise_band(**args)


@pytest.mark.parametrize("fault", ["empty", "opening", "middle", "last", "duplicate", "reverse",
                                   "incomplete", "bool", "symbol", "market", "timeframe",
                                   "outside", "future_symbol"])
def test_rejects_invalid_current_prefix(fault):
    args = _inputs()
    bars = args["bars"]
    if fault in {"empty", "opening", "last"}:
        args["bars"] = [] if fault == "empty" else bars[1:] if fault == "opening" else bars[:1]
    elif fault == "middle":
        bars.append(_bar(args["as_of"]))
        args["as_of"] = bars[-1].end_ts
        bars.pop(1)
    elif fault == "duplicate":
        bars.append(bars[-1])
    elif fault == "reverse":
        bars.reverse()
    elif fault == "bool":
        object.__setattr__(bars[0], "complete", 1)
    elif fault == "outside":
        bars.insert(0, _bar(args["session"].open_ts - timedelta(minutes=5)))
    elif fault == "future_symbol":
        bars.append(replace(_bar(args["as_of"]), symbol="QQQ"))
    else:
        field, value = {
            "incomplete": ("complete", False), "symbol": ("symbol", "QQQ"),
            "market": ("market", "NAS"), "timeframe": ("timeframe", Timeframe.M1),
        }[fault]
        bars[-1] = replace(bars[-1], **{field: value})
    with pytest.raises(ValueError):
        build_intraday_noise_band(**args)


@pytest.mark.parametrize("minutes", [-5, 0, 7, 395])
def test_rejects_invalid_elapsed_cutoff(minutes):
    args = _inputs()
    args["as_of"] = args["session"].open_ts + timedelta(minutes=minutes)
    with pytest.raises(ValueError, match="cutoff"):
        build_intraday_noise_band(**args)


@pytest.mark.parametrize("where", ["as_of", "current_bar", "prior_bar", "session", "prior_session"])
@pytest.mark.parametrize("zone", [None, timezone(timedelta(hours=9))])
def test_rejects_naive_and_non_utc_timestamps(where, zone):
    args = _inputs()
    invalid = args["as_of"].replace(tzinfo=zone)
    if where == "as_of":
        args[where] = invalid
    else:
        target = {"current_bar": args["bars"][0], "prior_bar": args["history"][0].bars[0],
                  "session": args["session"], "prior_session": args["history"][0].session}[where]
        object.__setattr__(target, "start_ts" if "bar" in where else "open_ts", invalid)
    with pytest.raises(ValueError, match="UTC"):
        build_intraday_noise_band(**args)


@pytest.mark.parametrize("field", ["open", "close"])
@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"),
                                   Decimal("-Infinity"), Decimal(0), Decimal(-1),
                                   True, False, 1, 1.0, "100", None])
@pytest.mark.parametrize("where", ["current", "prior"])
def test_rejects_invalid_consumed_prices(field, value, where):
    args = _inputs()
    bar = args["bars"][0] if where == "current" else args["history"][0].bars[-1]
    object.__setattr__(bar, field, value)
    error = ValueError if isinstance(value, Decimal) else TypeError
    with pytest.raises(error):
        build_intraday_noise_band(**args)


@pytest.mark.parametrize("field,value", [("as_of", True), ("as_of", "2026-03-09"),
                                        ("as_of", None), ("session", False), ("bars", [False]),
                                        ("history", [False] * 14), ("bars", None),
                                        ("history", None)])
def test_rejects_wrong_input_types(field, value):
    args = _inputs()
    args[field] = value
    with pytest.raises(TypeError):
        build_intraday_noise_band(**args)
