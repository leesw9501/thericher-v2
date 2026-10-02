"""Pure seen-data descriptive math, not p-values or Paper qualification; no IO or fits."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from itertools import product
from math import isfinite, log1p

import numpy as np

from thericher_v2.contracts import Timeframe
from thericher_v2.data.kis_paper_intraday import (
    KisPaperIntradayFeatureInput,
    resample_verified_kis_paper_private_intraday_catalog,
)
from thericher_v2.data.us_equity_session import us_equity_2026_session

Feature4 = tuple[float, float, float, float]
MINUTE = timedelta(minutes=1)
TRAIN_DATES = tuple(date(2026, m, d) for m, days in
                    ((6, (22, 23, 24, 25, 26, 29, 30)), (7, (1, 2, 6))) for d in days)
COMPARISON_DATES = tuple(date(2026, 7, d) for d in (8, 9, 10, 13, 14))
CONTEXTS, TIMEFRAMES = (30, 120), (Timeframe.M1, Timeframe.M5)
POLICIES = ("momentum", "linear", "tcn", "cash", "always_long")
MULTIPLIERS = tuple(Decimal(s) for s in ("1", "1.5", "2"))
OFFSETS = (120, 180, 240, 300)


@dataclass(frozen=True, repr=False)
class DecisionKey:
    dataset_id: str
    dataset_hash: str
    symbol: str
    session_date: date
    session_open: datetime
    cutoff: datetime
    entry: datetime
    exit: datetime


@dataclass(frozen=True, repr=False)
class WindowFeatures:
    key: DecisionKey
    context_minutes: int
    timeframe: Timeframe
    source_minute_starts: tuple[datetime, ...]
    sequence: tuple[Feature4, ...]
    features: Feature4


@dataclass(frozen=True, repr=False)
class TrainNormalization:
    context_minutes: int
    timeframe: Timeframe
    source_bindings: tuple[tuple[str, str, str], ...]
    means: Feature4
    scales: Feature4
    training_window_count: int
    real_position_count: int


@dataclass(frozen=True, repr=False)
class CellKey:
    symbol: str
    context_minutes: int
    timeframe: Timeframe
    policy: str
    cost_multiplier: Decimal


@dataclass(frozen=True, repr=False)
class ResolutionSummary:
    cell_count: int
    block_count: int
    pattern_count: int
    family_tail_fraction: Decimal
    kill_categories: tuple[str, ...]


def _check(condition, reason):
    if not condition:
        raise ValueError(reason)


def _binding(window):
    return window.key.dataset_id, window.key.dataset_hash, window.key.symbol


def _key(key, dates):
    _check(isinstance(key, DecisionKey) and key.symbol in ("QQQ", "SPY")
           and key.session_date in dates, "payoff_identity")
    origin = us_equity_2026_session(key.session_date).window.open_ts
    _check(key.session_open == origin and key.cutoff in tuple(origin + i * MINUTE for i in OFFSETS)
           and key.entry == key.cutoff + MINUTE and key.exit == key.cutoff + 31 * MINUTE
           and all(v.utcoffset() == timedelta(0) for v in
                   (key.session_open, key.cutoff, key.entry, key.exit)),
           "payoff_identity")


def _features(bar):
    width = bar.high - bar.low
    values = (float(10000 * (bar.close / bar.open - 1)),
              float(10000 * width / bar.open),
              float((2 * bar.close - bar.high - bar.low) / width) if width else 0.0,
              log1p(float(bar.volume)))
    _check(all(isfinite(v) for v in values), "nonfinite_features")
    return values


def build_equal_minute_windows(
    prepared: KisPaperIntradayFeatureInput,
) -> tuple[WindowFeatures, ...]:
    _check(isinstance(prepared, KisPaperIntradayFeatureInput), "prepared_input_required")
    dates, catalog = TRAIN_DATES + COMPARISON_DATES, prepared.catalog
    _check(prepared.session_dates == dates and len(catalog.bars) == 390 * 15, "session_scope")
    _check(prepared.session_windows == tuple(us_equity_2026_session(d).window for d in dates),
           "session_anchors")
    symbol = catalog.bars[0].symbol
    _check(symbol in ("QQQ", "SPY") and all(b.symbol == symbol for b in catalog.bars), "symbols")
    output = []
    with localcontext() as ctx:
        ctx.prec = 50
        for day, session in zip(dates, prepared.session_windows, strict=True):
            streams = {}
            for tf in TIMEFRAMES:
                result = resample_verified_kis_paper_private_intraday_catalog(
                    catalog, timeframe=tf, session=session)
                _check(not result.skipped_bucket_starts, "incomplete_session")
                streams[tf] = result.bars
            for offset, minutes, tf in product(OFFSETS, CONTEXTS, TIMEFRAMES):
                cutoff = session.open_ts + offset * MINUTE
                step = tf.duration // MINUTE
                history = streams[tf][(offset - minutes) // step:offset // step]
                starts = tuple(cutoff - minutes * MINUTE + i * MINUTE for i in range(minutes))
                _check(len(history) == minutes // step and history[-1].end_ts == cutoff
                       and tuple(b.start_ts for b in history) == starts[::step], "window_support")
                seq = tuple(_features(b) for b in history)
                mean_volume = sum((b.volume for b in history), Decimal(0)) / len(history)
                features = (float(10000 * (history[-1].close / history[0].open - 1)),
                            sum(v[1] for v in seq) / len(seq), seq[-1][2],
                            float(history[-1].volume / mean_volume - 1) if mean_volume else 0.0)
                _check(all(isfinite(v) for v in features), "nonfinite_features")
                key = DecisionKey(catalog.dataset_id, catalog.dataset_hash, symbol, day,
                                  session.open_ts, cutoff, cutoff + MINUTE, cutoff + 31 * MINUTE)
                output.append(WindowFeatures(key, minutes, tf, starts, seq, features))
    return tuple(output)


def tcn_kernel_size(window: WindowFeatures) -> int:
    _key(window.key, TRAIN_DATES + COMPARISON_DATES)
    _check(type(window.context_minutes) is int and window.context_minutes in CONTEXTS
           and isinstance(window.timeframe, Timeframe) and window.timeframe in TIMEFRAMES,
           "window_geometry")
    count = window.context_minutes // (window.timeframe.duration // MINUTE)
    expected = tuple(window.key.cutoff - window.context_minutes * MINUTE + i * MINUTE
                     for i in range(window.context_minutes))
    _check(window.source_minute_starts == expected and len(window.sequence) == count,
           "window_support")
    _check(type(window.sequence) is tuple and all(type(v) is tuple and len(v) == 4
           and all(isfinite(x) for x in v) for v in window.sequence), "feature_shape")
    return min(count, 120)  # Parameter counts differ; this is not pure resolution attribution.


def train_sequence_normalization(train_windows: tuple[WindowFeatures, ...]) -> TrainNormalization:
    _check(type(train_windows) is tuple and len(train_windows) == 80, "TRAIN_scope")
    first = train_windows[0]
    geometry = first.context_minutes, first.timeframe
    expected = set(product(("QQQ", "SPY"), TRAIN_DATES, tuple(i * MINUTE for i in OFFSETS)))
    actual = set()
    for w in train_windows:
        tcn_kernel_size(w)
        _check((w.context_minutes, w.timeframe) == geometry, "normalization_geometry")
        actual.add((w.key.symbol, w.key.session_date, w.key.cutoff - w.key.session_open))
    bindings = tuple(sorted({_binding(w) for w in train_windows}))
    _check(actual == expected and len(bindings) == 2, "TRAIN_scope")
    values = np.asarray([v for w in train_windows for v in w.sequence], dtype=np.float64)
    means = values[0] + (values - values[0]).mean(axis=0)
    scales = np.maximum(np.sqrt(((values - means) ** 2).mean(axis=0)), 1e-12)
    _check(bool(np.isfinite(means).all() and np.isfinite(scales).all()), "normalization_finite")
    return TrainNormalization(*geometry, bindings, tuple(means), tuple(scales), 80, len(values))


def normalize_sequence(
    window: WindowFeatures, normalization: TrainNormalization,
) -> tuple[Feature4, ...]:
    tcn_kernel_size(window)
    _check((window.context_minutes, window.timeframe) ==
           (normalization.context_minutes, normalization.timeframe)
           and _binding(window) in normalization.source_bindings, "normalization_binding")
    _check(len(normalization.means) == len(normalization.scales) == 4
           and all(isfinite(v) for v in normalization.means)
           and all(isfinite(v) and v >= 1e-12 for v in normalization.scales), "scaler_values")
    result = tuple(tuple((v - m) / s for v, m, s in zip(row, normalization.means,
                   normalization.scales, strict=True)) for row in window.sequence)
    _check(all(isfinite(v) for row in result for v in row), "nonfinite_normalization")
    return result


def summarize_resolution(
    returns: Mapping[CellKey, Mapping[DecisionKey, Decimal]],
) -> ResolutionSummary:
    grid = {CellKey(*args) for args in product(("QQQ", "SPY"), CONTEXTS, TIMEFRAMES,
                                              POLICIES, MULTIPLIERS)}
    _check(set(returns) == grid, "cell_grid")
    references, sources = {}, {}
    for cell, rows in returns.items():
        _check(type(cell.context_minutes) is int and isinstance(cell.timeframe, Timeframe)
               and type(cell.cost_multiplier) is Decimal, "cell_types")
        _check(len(rows) == 20, "decision_count")
        identities = set()
        for key, value in rows.items():
            _key(key, COMPARISON_DATES)
            _check(key.symbol == cell.symbol, "payoff_symbol")
            _check(type(value) is Decimal and value.is_finite(), "net_bps_values")
            binding = key.dataset_id, key.dataset_hash
            _check(binding == sources.setdefault(cell.symbol, binding), "source_binding")
            identities.add((key.session_date, key.cutoff))
        _check(len(identities) == 20 and set(rows) == references.setdefault(cell.symbol, set(rows)),
               "paired_keys")
    with localcontext() as ctx:
        ctx.prec = 50
        def daily(symbol, minutes, tf, policy, cost, day):
            rows = returns[CellKey(symbol, minutes, tf, policy, cost)]
            return sum((v for k, v in rows.items() if k.session_date == day), Decimal(0)) / 4
        def paired(minutes, policy, cost, day):
            return sum((daily(s, minutes, Timeframe.M1, policy, cost, day) -
                        daily(s, minutes, Timeframe.M5, policy, cost, day)
                        for s in ("QQQ", "SPY")), Decimal(0)) / 2
        controls = ("momentum", "cash", "always_long")
        for s, w, p, c in product(("QQQ", "SPY"), CONTEXTS, controls, MULTIPLIERS):
            _check(returns[CellKey(s, w, Timeframe.M1, p, c)] ==
                   returns[CellKey(s, w, Timeframe.M5, p, c)], "control_identity")
        contrasts = tuple(product(CONTEXTS, ("linear", "tcn"), MULTIPLIERS))
        blocks = tuple(tuple(paired(w, p, c, d) for w, p, c in contrasts) for d in COMPARISON_DATES)
        stats = [max(abs(sum((sign * row[j] for sign, row in zip(signs, blocks, strict=True)),
                            Decimal(0)) / 5) for j in range(12))
                 for signs in product((-1, 1), repeat=5)]
        observed = max(abs(sum((row[j] for row in blocks), Decimal(0)) / 5) for j in range(12))
        delta = tuple(sum((paired(w, "tcn", Decimal(2), d) for w in CONTEXTS), Decimal(0)) / 2
                      for d in COMPARISON_DATES)
        net = sum((daily(s, w, Timeframe.M1, "tcn", Decimal(2), d) for s, w, d in
                   product(("QQQ", "SPY"), CONTEXTS, COMPARISON_DATES)), Decimal(0)) / 20
        total, positive = sum(delta, Decimal(0)), sum((max(v, 0) for v in delta), Decimal(0))
        kills = tuple(name for name, killed in (
            ("nonpositive_stress_net", net <= 0), ("nonpositive_resolution_delta", total <= 0),
            ("single_day_dependence", any((total - v) / 4 <= 0 for v in delta)),
            ("positive_concentration", positive == 0 or max(delta) > positive / 2),
        ) if killed)
        return ResolutionSummary(120, 5, 32, Decimal(sum(v >= observed for v in stats)) / 32, kills)
