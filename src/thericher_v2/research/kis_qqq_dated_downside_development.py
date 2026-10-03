"""Finite QQQ downside-hurdle development, never NAV, a holdout or Paper input."""

from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal, localcontext
from itertools import product
from math import isfinite
from pathlib import Path

import numpy as np

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_intraday as data
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import kis_equal_minute_resolution as resolution
from thericher_v2.research.kis_intraday_window_matrix import _fit_logistic
from thericher_v2.research.tiingo_monthly_net_utility_development import digest, encode, require

NAME = "kis-qqq-dated-downside-development-v1"
DATES = tuple(
    date(2026, 9, d)
    for d in (2, 3, 4, 8, 9, 10, 11, 14, 15, 16, 17, 18, 21, 22, 23, 24, 25, 28, 29, 30)
)
TRAIN, EMBARGO, COMPARISON = DATES[:10], DATES[10], DATES[11:]
OFFSETS, MINUTE = resolution.OFFSETS, timedelta(minutes=1)
POLICIES = ("downside_q25", "linear", "momentum", "train_q25", "cash", "always_long")
COSTS = ("3", "4.5", "6")
PARAMETERS = dict(
    loss="quantile",
    quantile=0.25,
    max_iter=16,
    max_depth=1,
    max_leaf_nodes=2,
    min_samples_leaf=10,
    max_bins=8,
    learning_rate=0.1,
    l2_regularization=1.0,
    early_stopping=False,
    random_state=103,
)
KILLS = (
    "nonpositive_stress_net",
    "nonpositive_linear_increment",
    "nonpositive_momentum_increment",
    "single_day_dependence",
)


def configuration():
    return dict(
        train=[str(d) for d in TRAIN],
        embargo=str(EMBARGO),
        comparison=[str(d) for d in COMPARISON],
        dates=[str(d) for d in DATES],
        symbol="QQQ",
        exchange="NAS",
        timeframe="5m",
        context_minutes=120,
        anchors=list(OFFSETS),
        features="equal-minute aggregate4; history [C-120min,C)",
        target="M1 OPEN C+1 to OPEN C+31; gross=10000*(exit/entry-1)",
        policies=list(POLICIES),
        costs_per_side_bps=list(COSTS),
        fee_slippage="1bp fee+2bp slippage/side; fixed multipliers1/1.5/2",
        payoff="action*(gross-2*side_cost); binary exposure; unit bps, not NAV",
        parameters=PARAMETERS,
        linear="TRAIN mean/std floor1e-12;zero-init64steps/lr.05",
        thresholds="q25>6bps; linear TRAINlabel gross>6/logit>0; momentum feature0>0",
        train_quantile="NumPy quantile(.25,method=linear);TRAIN only; one fixed statistic",
        train_examples=40,
        comparison_examples=36,
        session_blocks=9,
        cells=18,
        budget=dict(
            fits=2,
            attempts=1,
            cpu_threads=2,
            memory_bytes=2 * 1024**3,
            seconds=120,
            gpu=False,
            synthetic_smoke_fits=4,
        ),
        kills=dict(
            nonpositive_stress_net="mean of9 daily four-anchor downside net at6bps/side<=0",
            nonpositive_linear_increment="same9day mean downside-minus-linear stress net<=0",
            nonpositive_momentum_increment="same9day mean downside-minus-momentum stress net<=0",
            single_day_dependence="any day deletion leaves nonpositive stress increment against"
            " either linear or momentum; no refit",
        ),
        limitations=[
            "one ETF;10 TRAIN/9 comparison session blocks, not independent anchors",
            "independent storage is not untouched outcomes; September previously seen",
            "revised/non-PIT/provider finality unproved; assumed fees and slippage",
            "binary action commitments reconstruct replay, not unretained model inference",
        ],
        scope="no weights/raw forecasts/labels/holdout/selection/promotion/Paper/portfolio NAV",
    )


def build_windows(prepared):
    require(
        isinstance(prepared, data.KisPaperIntradayFeatureInput)
        and len(prepared.session_dates) == 1
        and prepared.session_dates[0] in DATES,
        "session_scope",
    )
    day = prepared.session_dates[0]
    session = us_equity_2026_session(day).window
    require(prepared.session_windows == (session,), "session_calendar")
    catalog = prepared.catalog
    data.require_complete_kis_paper_private_intraday_session(catalog, session=session)
    require(all(b.symbol == "QQQ" for b in catalog.bars), "symbol")
    resampled = data.resample_verified_kis_paper_private_intraday_catalog(
        catalog, timeframe=Timeframe.M5, session=session
    )
    require(not resampled.skipped_bucket_starts and len(resampled.bars) == 78, "M5_support")
    output = []
    with localcontext() as ctx:
        ctx.prec = 50
        for offset in OFFSETS:
            cutoff = session.open_ts + offset * MINUTE
            history = resampled.bars[(offset - 120) // 5 : offset // 5]
            require(len(history) == 24 and history[-1].end_ts == cutoff, "window_support")
            seq = tuple(resolution._features(b) for b in history)
            volume = sum((b.volume for b in history), Decimal(0)) / 24
            features = (
                float(10000 * (history[-1].close / history[0].open - 1)),
                sum(v[1] for v in seq) / 24,
                seq[-1][2],
                float(history[-1].volume / volume - 1) if volume else 0.0,
            )
            require(all(isfinite(v) for v in features), "feature_finite")
            key = resolution.DecisionKey(
                catalog.dataset_id,
                catalog.dataset_hash,
                "QQQ",
                day,
                session.open_ts,
                cutoff,
                cutoff + MINUTE,
                cutoff + 31 * MINUTE,
            )
            starts = tuple(cutoff - 120 * MINUTE + i * MINUTE for i in range(120))
            output.append(resolution.WindowFeatures(key, 120, Timeframe.M5, starts, seq, features))
    return tuple(output)


def check_cohort(windows):
    require(type(windows) is tuple and len(windows) == 80, "cohort_count")
    bindings = {}
    for w, (day, offset) in zip(windows, product(DATES, OFFSETS), strict=True):
        session = us_equity_2026_session(day).window
        cutoff = session.open_ts + offset * MINUTE
        require(
            w.key.symbol == "QQQ"
            and w.key.session_date == day
            and w.key.session_open == session.open_ts
            and w.key.cutoff == cutoff
            and w.key.entry == cutoff + MINUTE
            and w.key.exit == cutoff + 31 * MINUTE
            and w.context_minutes == 120
            and w.timeframe == Timeframe.M5
            and len(w.features) == 4
            and all(isfinite(v) for v in w.features)
            and w.source_minute_starts
            == tuple(cutoff - 120 * MINUTE + i * MINUTE for i in range(120))
            and len(w.sequence) == 24
            and all(len(v) == 4 and all(isfinite(x) for x in v) for v in w.sequence),
            "cohort_geometry",
        )
        binding = w.key.dataset_id, w.key.dataset_hash
        require(
            type(binding[0]) is str
            and binding[0].startswith("kis.paper.private.intraday.qqq.nas.m1.v1:")
            and data._is_sha256(binding[1]),
            "source_identity",
        )
        require(binding == bindings.setdefault(day, binding), "date_binding")
    require(len({v[1] for v in bindings.values()}) == 20, "independent_date_bindings")


def gross_bps(window, catalog):
    require(
        (window.key.dataset_id, window.key.dataset_hash)
        == (catalog.dataset_id, catalog.dataset_hash),
        "payoff_source",
    )
    bars = {b.start_ts: b for b in catalog.bars}
    with localcontext() as ctx:
        ctx.prec = 50
        return 10000 * (bars[window.key.exit].open / bars[window.key.entry].open - 1)


def _gross(values, count):
    require(
        type(values) is tuple
        and len(values) == count
        and all(type(v) is Decimal and v.is_finite() for v in values),
        "gross_shape",
    )


def controls(windows, train_gross):
    check_cohort(windows)
    _gross(train_gross, 40)
    q25 = float(np.quantile(np.asarray(train_gross, dtype=np.float64), 0.25, method="linear"))
    require(isfinite(q25), "quantile_finite")
    comparison = tuple(w for w in windows if w.key.session_date in COMPARISON)
    return dict(
        momentum=tuple(w.features[0] > 0 for w in comparison),
        train_q25=(q25 > 6,) * 36,
        cash=(False,) * 36,
        always_long=(True,) * 36,
    )


def fit_actions(windows, train_gross, counts, deadline):
    """Comparison payoffs are deliberately absent from the fit/predict API."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from threadpoolctl import threadpool_limits

    result = controls(windows, train_gross)
    train = tuple(w for w in windows if w.key.session_date in TRAIN)
    comparison = tuple(w for w in windows if w.key.session_date in COMPARISON)
    x, future = [
        np.asarray([w.features for w in stream], dtype=np.float64) for stream in (train, comparison)
    ]
    y = np.asarray(train_gross, dtype=np.float64)
    require(
        np.isfinite(y).all()
        and type(counts) is dict
        and counts == dict(linear=0, downside=0)
        and all(type(v) is int for v in counts.values()),
        "fit_inputs",
    )
    with threadpool_limits(limits=2):
        require(time.monotonic() < deadline, "hard_timeout")
        counts["linear"] += 1
        linear = _fit_logistic(train, [int(v > 6) for v in train_gross])
        logits = (future - linear.means) / linear.scales @ np.asarray(linear.weights) + linear.bias
        require(logits.shape == (36,) and np.isfinite(logits).all(), "linear_shape")
        require(time.monotonic() < deadline, "hard_timeout")
        counts["downside"] += 1
        model = HistGradientBoostingRegressor(**PARAMETERS).fit(x, y)
        forecast = model.predict(future)
        require(
            model.n_iter_ == 16 and forecast.shape == (36,) and np.isfinite(forecast).all(),
            "downside_shape",
        )
        require(time.monotonic() < deadline, "hard_timeout")
    result.update(
        linear=tuple(bool(v > 0) for v in logits), downside_q25=tuple(bool(v > 6) for v in forecast)
    )
    return result


def action_hash(windows, actions):
    return digest(
        encode(
            [
                [w.key.dataset_id, w.key.dataset_hash, w.key.cutoff.isoformat(), a]
                for w, a in zip(windows, actions, strict=True)
            ]
        )
    )


def aggregate(windows, comparison_gross, actions):
    check_cohort(windows)
    _gross(comparison_gross, 36)
    require(
        type(actions) is dict
        and set(actions) == set(POLICIES)
        and all(
            type(v) is tuple and len(v) == 36 and all(type(a) is bool for a in v)
            for v in actions.values()
        ),
        "action_shape",
    )
    comparison = tuple(w for w in windows if w.key.session_date in COMPARISON)
    daily = []
    with localcontext() as ctx:
        ctx.prec = 50
        for i, day in enumerate(COMPARISON):
            a, b = 4 * i, 4 * i + 4
            daily.append(
                dict(
                    date=str(day),
                    policies=[
                        dict(
                            policy=p,
                            decisions=4,
                            trades=sum(actions[p][a:b]),
                            gross_sum_unit_bps=str(
                                sum(
                                    (
                                        g * int(t)
                                        for g, t in zip(
                                            comparison_gross[a:b], actions[p][a:b], strict=True
                                        )
                                    ),
                                    Decimal(0),
                                )
                            ),
                            action_sha256=action_hash(comparison[a:b], actions[p][a:b]),
                        )
                        for p in POLICIES
                    ],
                )
            )
        cells = []
        for i, p in enumerate(POLICIES):
            rows = [d["policies"][i] for d in daily]
            trades = sum(r["trades"] for r in rows)
            gross = sum((Decimal(r["gross_sum_unit_bps"]) for r in rows), Decimal(0))
            for cost in COSTS:
                cells.append(
                    dict(
                        policy=p,
                        cost_per_side_bps=cost,
                        decisions=36,
                        trades=trades,
                        gross_sum_unit_bps=str(gross),
                        mean_net_unit_bps=str((gross - 2 * Decimal(cost) * trades) / 36),
                        action_sha256=digest(encode([r["action_sha256"] for r in rows])),
                    )
                )
        nets = {
            p: [
                (Decimal(d["policies"][i]["gross_sum_unit_bps"]) - 12 * d["policies"][i]["trades"])
                / 4
                for d in daily
            ]
            for i, p in enumerate(POLICIES)
        }
        primary = sum(nets["downside_q25"]) / 9
        deltas = {
            p: tuple(a - b for a, b in zip(nets["downside_q25"], nets[p], strict=True))
            for p in ("linear", "momentum")
        }
        means = {p: sum(v) / 9 for p, v in deltas.items()}
        minimum = {p: min((sum(v) - x) / 8 for x in v) for p, v in deltas.items()}
        killed = (
            primary <= 0,
            means["linear"] <= 0,
            means["momentum"] <= 0,
            any(v <= 0 for v in minimum.values()),
        )
        descriptive = dict(
            session_blocks=9,
            stress_mean_net_unit_bps=str(primary),
            increments={p: str(v) for p, v in means.items()},
            min_leave_one_day_out_increments={p: str(v) for p, v in minimum.items()},
            kill_categories=[k for k, flag in zip(KILLS, killed, strict=True) if flag],
        )
    return dict(daily=daily, cells=cells, descriptive=descriptive)


def verify_evaluation(windows, train_gross, comparison_gross, value):
    """Read back committed binary actions, not unretained model inference."""
    check_cohort(windows)
    require(
        type(value) is dict and set(value) == {"daily", "cells", "descriptive"}, "result_fields"
    )
    require(type(value["daily"]) is list and len(value["daily"]) == 9, "daily_count")
    comparison = tuple(w for w in windows if w.key.session_date in COMPARISON)
    actions = {p: () for p in POLICIES}
    for i, (day, record) in enumerate(zip(COMPARISON, value["daily"], strict=True)):
        require(
            type(record) is dict
            and set(record) == {"date", "policies"}
            and record["date"] == str(day)
            and type(record["policies"]) is list
            and len(record["policies"]) == 6,
            "daily_shape",
        )
        for p, row in zip(POLICIES, record["policies"], strict=True):
            require(
                type(row) is dict
                and set(row)
                == {"policy", "decisions", "trades", "gross_sum_unit_bps", "action_sha256"}
                and row["policy"] == p
                and type(row["decisions"]) is int
                and row["decisions"] == 4
                and type(row["trades"]) is int
                and 0 <= row["trades"] <= 4
                and type(row["gross_sum_unit_bps"]) is str,
                "policy_day_shape",
            )
            matches = [
                bits
                for bits in product((False, True), repeat=4)
                if action_hash(comparison[4 * i : 4 * i + 4], bits) == row["action_sha256"]
            ]
            require(len(matches) == 1, "action_commitment")
            actions[p] += matches[0]
    expected = controls(windows, train_gross)
    require(all(actions[p] == bits for p, bits in expected.items()), "control_actions")
    require(
        encode(value) == encode(aggregate(windows, comparison_gross, actions)), "replay_identity"
    )


def synthetic_panel():
    windows, catalogs = (), {}
    for i, day in enumerate(DATES):
        session = us_equity_2026_session(day).window
        bars = []
        for minute in range(390):
            price = Decimal(100) + Decimal(minute) / 100 * (1 if i % 2 else -1)
            bars.append(
                Bar(
                    "QQQ",
                    "US",
                    Timeframe.M1,
                    session.open_ts + minute * MINUTE,
                    price,
                    price + 1,
                    price - 1,
                    price + Decimal(".01"),
                    Decimal(1000),
                )
            )
        catalog = _cataloged_bars_from_verified_loader(
            dataset_id="kis.paper.private.intraday.qqq.nas.m1.v1",
            dataset_hash=digest(encode(str(day))),
            source_path=Path("synthetic-index.json"),
            bars=tuple(bars),
        )
        prepared = data.prepare_kis_paper_intraday_feature_input(catalog, session_dates=(day,))
        windows += build_windows(prepared)
        catalogs[day] = prepared.catalog
    check_cohort(windows)
    return windows, catalogs


def cpu_smoke(deadline):
    windows, catalogs = synthetic_panel()
    train = tuple(
        gross_bps(w, catalogs[w.key.session_date]) for w in windows if w.key.session_date in TRAIN
    )
    gross = tuple(
        gross_bps(w, catalogs[w.key.session_date])
        for w in windows
        if w.key.session_date in COMPARISON
    )
    first = fit_actions(windows, train, dict(linear=0, downside=0), deadline)
    second = fit_actions(windows, train, dict(linear=0, downside=0), deadline)
    require(first == second, "synthetic_determinism")
    verify_evaluation(windows, train, gross, aggregate(windows, gross, first))
    return dict(synthetic_windows=80, synthetic_fits=4, actual_fits=0, cells=18, verified=True)
