"""Synthetic-only geometry, normalization and paired-math checks; no model fits."""

import os
import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal, localcontext
from itertools import product
from math import fsum
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import prepare_kis_paper_intraday_feature_input
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import kis_equal_minute_resolution as r


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("external IO, credentials or runtime are forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    for name in ("open", "read_bytes", "read_text", "write_bytes", "write_text"):
        monkeypatch.setattr(Path, name, forbidden)


@pytest.fixture(scope="module")
def prepared():
    output = {}
    dates = r.TRAIN_DATES + r.COMPARISON_DATES
    for symbol in ("QQQ", "SPY"):
        bars = []
        for day in dates:
            session = us_equity_2026_session(day).window
            for minute in range(390):
                price = Decimal(100) + Decimal(minute) / 100
                bars.append(Bar(symbol, "US", Timeframe.M1, session.open_ts + minute * r.MINUTE,
                                price, price + 1, price - 1, price + Decimal(".01"),
                                Decimal(1000 + minute % 11)))
        catalog = _cataloged_bars_from_verified_loader(
            dataset_id=f"kis.paper.private.intraday.{symbol.lower()}.unit",
            dataset_hash="sha256:" + "1" * 64, source_path=Path("synthetic-index.json"),
            bars=tuple(bars))
        output[symbol] = prepare_kis_paper_intraday_feature_input(catalog, session_dates=dates)
    return output


@pytest.fixture(scope="module")
def windows(prepared):
    return tuple(w for p in prepared.values() for w in r.build_equal_minute_windows(p))


def test_exact_common_anchors_real_support_and_kernels(windows):
    assert len(windows) == 2 * 15 * 4 * 4
    for w in windows:
        assert w.key.entry == w.key.cutoff + r.MINUTE
        assert w.key.exit == w.key.cutoff + 31 * r.MINUTE
        step = w.timeframe.duration // r.MINUTE
        assert len(w.sequence) == w.context_minutes // step == r.tcn_kernel_size(w)
        assert len(w.source_minute_starts) == w.context_minutes
    for key, context in {(w.key, w.context_minutes) for w in windows}:
        pair = [w for w in windows if w.key == key and w.context_minutes == context]
        assert len(pair) == 2
        assert pair[0].source_minute_starts == pair[1].source_minute_starts
        assert pair[0].features[0] == pair[1].features[0]
    assert {w.key.session_date for w in windows} == set(r.TRAIN_DATES + r.COMPARISON_DATES)
    assert date(2026, 7, 7) not in {w.key.session_date for w in windows}
    assert not {date(2026, 7, d) for d in (15, 16, 17, 20, 21)} & {
        w.key.session_date for w in windows}


@pytest.mark.parametrize(
    "change", ("missing", "duplicate", "incomplete", "symbol", "anchors", "scope"))
def test_rejects_broken_prepared_support(prepared, change):
    p = prepared["QQQ"]
    bars = list(p.catalog.bars)
    if change == "missing":
        bars.pop()
    elif change == "duplicate":
        bars[33] = bars[32]
    elif change == "incomplete":
        bars[33] = replace(bars[33], complete=False)
    elif change == "symbol":
        bars = [replace(b, symbol="IWM") for b in bars]
    elif change == "anchors":
        p = replace(p, session_windows=tuple(replace(s, open_ts=s.open_ts + r.MINUTE)
                                            for s in p.session_windows))
    else:
        p = replace(p, session_dates=p.session_dates + (date(2026, 7, 15),))
    catalog = _cataloged_bars_from_verified_loader(
        dataset_id=p.catalog.dataset_id, dataset_hash=p.catalog.dataset_hash,
        source_path=p.catalog.source_path, bars=tuple(bars))
    with pytest.raises(ValueError):
        r.build_equal_minute_windows(replace(p, catalog=catalog))


def test_no_preceding_close_or_payoff_bar_features(prepared):
    p = prepared["QQQ"]
    baseline = r.build_equal_minute_windows(p)[0]
    bars = list(p.catalog.bars)
    for minute in (89, 120, 121, 151):
        b = bars[minute]
        bars[minute] = replace(b, open=b.open * 2, high=b.high * 2,
                               low=b.low * 2, close=b.close * 2)
    catalog = _cataloged_bars_from_verified_loader(
        dataset_id=p.catalog.dataset_id, dataset_hash=p.catalog.dataset_hash,
        source_path=p.catalog.source_path, bars=tuple(bars))
    assert r.build_equal_minute_windows(replace(p, catalog=catalog))[0] == baseline


@pytest.mark.parametrize("context,tf", tuple(product(r.CONTEXTS, r.TIMEFRAMES)))
def test_train_only_normalization_no_padding(windows, context, tf):
    train = tuple(w for w in windows if w.context_minutes == context and w.timeframe == tf
                  and w.key.session_date in r.TRAIN_DATES)
    norm = r.train_sequence_normalization(train)
    raw = np.asarray([row for w in train for row in w.sequence])
    assert norm.real_position_count == 80 * context // (tf.duration // r.MINUTE)
    reference = tuple(fsum(raw[:, i]) / len(raw) for i in range(4))
    assert np.allclose(norm.means, reference, rtol=0, atol=1e-12)
    normalized = np.asarray([row for w in train for row in r.normalize_sequence(w, norm)])
    assert np.allclose(normalized.mean(axis=0), 0, atol=1e-8)
    comparison = next(w for w in windows if w.context_minutes == context and w.timeframe == tf
                      and w.key.session_date in r.COMPARISON_DATES)
    changed = replace(comparison, sequence=tuple((99., 98., 97., 96.) for _ in comparison.sequence))
    assert r.normalize_sequence(changed, norm) != r.normalize_sequence(comparison, norm)
    assert r.train_sequence_normalization(train) == norm


@pytest.mark.parametrize(
    "change", ("comparison", "duplicate", "geometry", "nonfinite", "shape", "source"))
def test_normalization_rejects_wrong_scope_and_values(windows, change):
    train = tuple(w for w in windows if w.context_minutes == 30 and w.timeframe == Timeframe.M1
                  and w.key.session_date in r.TRAIN_DATES)
    norm = r.train_sequence_normalization(train)
    changed = list(train)
    if change == "comparison":
        changed[0] = replace(train[0], key=replace(train[0].key,
                            session_date=r.COMPARISON_DATES[0]))
    elif change == "duplicate":
        changed[0] = changed[1]
    elif change == "geometry":
        changed[0] = replace(train[0], timeframe=Timeframe.M5)
    elif change == "nonfinite":
        changed[0] = replace(train[0], sequence=((float("nan"), 1., 2., 3.),) * 30)
    elif change == "shape":
        changed[0] = replace(train[0], sequence=((1., 2.),) * 30)
    else:
        changed[0] = replace(train[0], key=replace(train[0].key, dataset_hash="sha256:" + "2" * 64))
        with pytest.raises(ValueError, match="binding"):
            r.normalize_sequence(changed[0], norm)
    with pytest.raises(ValueError):
        r.train_sequence_normalization(tuple(changed))


def scored(windows, deltas=(Decimal(1),) * 5):
    returns = {}
    for symbol, minutes, tf, policy, cost in product(("QQQ", "SPY"), r.CONTEXTS, r.TIMEFRAMES,
                                                    r.POLICIES, r.MULTIPLIERS):
        cell = r.CellKey(symbol, minutes, tf, policy, cost)
        returns[cell] = {
            w.key: (Decimal(0) if policy == "cash" else Decimal(10) - cost +
                    (deltas[r.COMPARISON_DATES.index(w.key.session_date)]
                     if policy in ("linear", "tcn") and tf == Timeframe.M1 else Decimal(0)))
            for w in windows if w.key.symbol == symbol and w.context_minutes == minutes
            and w.timeframe == tf and w.key.session_date in r.COMPARISON_DATES}
    return returns


def test_exact_grid_joint_patterns_and_decimal_context_independence(windows):
    returns = scored(windows)
    with localcontext() as ctx:
        ctx.prec = 5
        result = r.summarize_resolution(returns)
    assert (result.cell_count, result.block_count, result.pattern_count) == (120, 5, 32)
    assert result.family_tail_fraction == Decimal(2) / 32
    assert result.kill_categories == ()
    assert r.summarize_resolution(dict(reversed(tuple(returns.items())))) == result


@pytest.mark.parametrize(
    "change", ("missing", "extra", "keys", "source", "anchor", "exit", "value", "control"))
def test_scoring_rejects_misalignment_and_invalid_values(windows, change):
    returns = scored(windows)
    cell = r.CellKey("QQQ", 30, Timeframe.M1, "linear", Decimal(1))
    key = next(iter(returns[cell]))
    if change == "missing":
        returns.pop(cell)
    elif change == "extra":
        returns[replace(cell, symbol="IWM")] = returns[cell]
    elif change == "value":
        returns[cell][key] = Decimal("NaN")
    elif change == "control":
        returns[r.CellKey("QQQ", 30, Timeframe.M1, "momentum", Decimal(1))][key] += 1
    else:
        replacement = {"keys": dict(cutoff=key.cutoff + r.MINUTE),
                       "source": dict(dataset_hash="sha256:" + "9" * 64),
                       "anchor": dict(session_open=key.session_open + r.MINUTE),
                       "exit": dict(exit=key.exit + r.MINUTE)}[change]
        returns[cell][replace(key, **replacement)] = returns[cell].pop(key)
    with pytest.raises(ValueError):
        r.summarize_resolution(returns)


@pytest.mark.parametrize("deltas,expected", [
    ((1, 1, 1, 1, 4), ()),
    ((1, 1, 1, 1, 5), ("positive_concentration",)),
    ((0, 0, 0, 0, 1), ("single_day_dependence", "positive_concentration")),
    ((0, 0, 0, 0, 0), ("nonpositive_resolution_delta", "single_day_dependence",
                       "positive_concentration")),
    ((-1, -1, -1, -1, -1), ("nonpositive_resolution_delta", "single_day_dependence",
                            "positive_concentration")),
])
def test_predeclared_single_day_kill_boundaries(windows, deltas, expected):
    result = r.summarize_resolution(scored(windows, tuple(map(Decimal, deltas))))
    assert result.kill_categories == expected


@pytest.mark.parametrize("change", ("relabeled_comparison", "open", "cutoff", "entry", "exit"))
def test_canonical_train_anchors_before_normalization(windows, monkeypatch, change):
    train = tuple(w for w in windows if w.context_minutes == 30 and w.timeframe == Timeframe.M1
                  and w.key.session_date in r.TRAIN_DATES)
    norm = r.train_sequence_normalization(train)
    candidate = train[0]
    if change == "relabeled_comparison":
        candidate = next(w for w in windows if w.context_minutes == 30
                         and w.timeframe == Timeframe.M1 and w.key.symbol == "QQQ"
                         and w.key.session_date == r.COMPARISON_DATES[0])
        candidate = replace(candidate, key=replace(candidate.key,
                            session_date=train[0].key.session_date))
    else:
        field = "session_open" if change == "open" else change
        candidate = replace(candidate, key=replace(candidate.key,
                            **{field: getattr(candidate.key, field) + r.MINUTE}))
    def forbidden(*_args, **_kwargs):
        pytest.fail("normalization values read before canonical identity validation")
    monkeypatch.setattr(r.np, "asarray", forbidden)
    with pytest.raises(ValueError, match="payoff_identity"):
        r.train_sequence_normalization((candidate,) + train[1:])
    with pytest.raises(ValueError, match="payoff_identity"):
        r.normalize_sequence(candidate, norm)


def test_nonpositive_stress_net_and_immutable_no_value_repr(windows):
    returns = scored(windows)
    for cell, rows in returns.items():
        if cell.policy == "tcn" and cell.timeframe == Timeframe.M1 and cell.cost_multiplier == 2:
            returns[cell] = dict.fromkeys(rows, Decimal(0))
    assert "nonpositive_stress_net" in r.summarize_resolution(returns).kill_categories
    window = windows[0]
    with pytest.raises(FrozenInstanceError):
        window.context_minutes = 120
    assert isinstance(window.sequence, tuple) and isinstance(window.sequence[0], tuple)
    assert "source_minute_starts" not in repr(window) and "dataset_hash" not in repr(window.key)
