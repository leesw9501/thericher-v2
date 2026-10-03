"""Finite pooled return representation study; not PatchTST reproduction or NAV."""

from __future__ import annotations

import time
from decimal import Decimal, localcontext
from itertools import product
from math import isfinite
from pathlib import Path

import numpy as np

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_intraday as data
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_equal_minute_resolution as resolution
from thericher_v2.research import kis_qqq_dated_downside_development as dated
from thericher_v2.research.sequence_architecture_models import (
    build_torch_patch_sequence_model,
    build_torch_sequence_model,
)

NAME = "kis-pooled-patch-return-development-v1"
DATES, TRAIN, EMBARGO, COMPARISON = dated.DATES, dated.TRAIN, dated.EMBARGO, dated.COMPARISON
MINUTE, COSTS = dated.MINUTE, dated.COSTS
TRAIN_OFFSETS, COMPARISON_OFFSETS = tuple(range(120, 356, 5)), dated.OFFSETS
TRAIN_COUNT, COMPARISON_COUNT, WINDOW_COUNT = 960, 72, 1032
TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
MODELS = ("ridge", "lstm", "patch")
POLICIES = (*MODELS, "train_mean", "momentum", "cash", "always_long")
KILLS = ("nonpositive_stress_net", "nonpositive_increment", "ETF_dependence", "day_dependence")
encode, digest, require, gross_bps, action_hash = (
    dated.encode,
    dated.digest,
    dated.require,
    dated.gross_bps,
    dated.action_hash,
)


def configuration():
    return dict(
        dates=[str(d) for d in DATES],
        train=[str(d) for d in TRAIN],
        embargo=str(EMBARGO),
        comparison=[str(d) for d in COMPARISON],
        targets=[list(t) for t in TARGETS],
        geometry=dict(
            timeframe="5m",
            context_minutes=120,
            bars=24,
            features=4,
            train_offsets=list(TRAIN_OFFSETS),
            comparison_offsets=list(COMPARISON_OFFSETS),
            history="[C-120min,C); completed patches only",
        ),
        target="10000*(M1 OPEN C+31 / M1 OPEN C+1 - 1); gross_bps/100 NN regression",
        normalization="TRAIN-only channel mean/std over960x24; aggregate TRAIN960x4; floor1e-12",
        ridge="NumPy solve; standardized aggregate4; L2=1; intercept unpenalized",
        numeric="ridge/normalization float64; NN float32; population std ddof0;"
        " deterministic Torch;"
        " parent sets CUBLAS_WORKSPACE_CONFIG=:4096:8 before import",
        neural=dict(
            seed=107,
            epochs=128,
            batch=960,
            optimizer="Adam",
            lr=0.001,
            weight_decay=0,
            loss="Huber",
            delta=0.1,
            final_epoch_only=True,
            lstm_hidden=16,
            patch_hidden=16,
            patch_heads=2,
            patch_length=6,
            patch_layers=1,
            patch_dropout=0,
            channel_aggregation="equal mean",
        ),
        action="predicted gross_bps>6; pooled TRAIN mean>6; momentum aggregate feature0>0",
        policies=list(POLICIES),
        costs_per_side_bps=list(COSTS),
        costs="1bp fee+2bp slip per side x1/1.5/2; actions fixed across costs",
        payoff="action*(gross_bps-2*sidecost); unit bps NOT NAV or broker PnL",
        train_examples=TRAIN_COUNT,
        comparison_examples=COMPARISON_COUNT,
        shared_train_session_blocks=10,
        shared_session_blocks=9,
        cells=42,
        budget=dict(
            actual_fits=3,
            attempts=1,
            cpu_threads=2,
            memory_bytes=6 * 1024**3,
            seconds=300,
            gpu=True,
            synthetic_smoke_fits=6,
        ),
        ordering="TRAIN payoffs -> ridge CPU -> two NN fits/inference -> immutable actions"
        " + hash -> comparison payoffs -> scoring",
        kills=dict(
            nonpositive_stress_net="pooled patch mean net at6bps/side over72 decisions<=0",
            nonpositive_increment="pooled patch-minus-ridge or patch-minus-LSTM stress mean<=0",
            ETF_dependence="either ETF deletion leaves either increment<=0; no refit",
            day_dependence="any shared day deletion leaves either increment<=0; no refit",
        ),
        limitations=[
            "960 overlapping TRAIN windows are10 shared blocks, not960 independent observations",
            "two ETFs,10 TRAIN/9 shared comparison session blocks, not18 independent",
            "independent storage and source pins do not make seen September untouched",
            "revised/non-PIT/provider finality unproved; assumed costs; no p-values",
            "PatchTST-inspired idea only; differing parameter capacities confound",
            "shared per-channel weights plus equal-mean head impose feature-exchangeability;"
            " heterogeneous technical channels have no explicit feature identity;"
            " architectural regularization probe, not generic cross-feature attention",
            "action commitments reconstruct replay, not unretained learned inference",
        ],
        scope="no raw forecasts/labels/weights/checkpoints/holdout/selection/promotion/Paper",
    )


def build_windows(prepared):
    require(
        isinstance(prepared, data.KisPaperIntradayFeatureInput)
        and len(prepared.session_dates) == 1
        and prepared.session_dates[0] in DATES,
        "session_scope",
    )
    day, catalog = prepared.session_dates[0], prepared.catalog
    session = dated.us_equity_2026_session(day).window
    require(prepared.session_windows == (session,), "session_calendar")
    symbol = catalog.bars[0].symbol
    require(
        symbol in {t[0] for t in TARGETS} and all(b.symbol == symbol for b in catalog.bars),
        "symbol",
    )
    data.require_complete_kis_paper_private_intraday_session(catalog, session=session)
    if day == EMBARGO:
        return ()
    m5 = data.resample_verified_kis_paper_private_intraday_catalog(
        catalog, timeframe=Timeframe.M5, session=session
    )
    require(not m5.skipped_bucket_starts and len(m5.bars) == 78, "M5_support")
    windows = []
    with localcontext() as ctx:
        ctx.prec = 50
        for offset in TRAIN_OFFSETS if day in TRAIN else COMPARISON_OFFSETS:
            cutoff = session.open_ts + offset * MINUTE
            bars = m5.bars[(offset - 120) // 5 : offset // 5]
            require(len(bars) == 24 and bars[-1].end_ts == cutoff, "window_support")
            seq = tuple(resolution._features(b) for b in bars)
            volume = sum((b.volume for b in bars), Decimal(0)) / 24
            features = (
                float(10000 * (bars[-1].close / bars[0].open - 1)),
                sum(v[1] for v in seq) / 24,
                seq[-1][2],
                float(bars[-1].volume / volume - 1) if volume else 0.0,
            )
            key = resolution.DecisionKey(
                catalog.dataset_id,
                catalog.dataset_hash,
                symbol,
                day,
                session.open_ts,
                cutoff,
                cutoff + MINUTE,
                cutoff + 31 * MINUTE,
            )
            windows.append(
                resolution.WindowFeatures(
                    key,
                    120,
                    Timeframe.M5,
                    tuple(cutoff - 120 * MINUTE + i * MINUTE for i in range(120)),
                    seq,
                    features,
                )
            )
    return tuple(windows)


def check_cohort(windows):
    require(type(windows) is tuple and len(windows) == WINDOW_COUNT, "cohort_count")
    bindings = {}
    for w, ((symbol, exchange), day, offset) in zip(
        windows,
        (
            (target, d, offset)
            for target in TARGETS
            for d in DATES
            for offset in (
                TRAIN_OFFSETS if d in TRAIN else COMPARISON_OFFSETS if d in COMPARISON else ()
            )
        ),
        strict=True,
    ):
        session = dated.us_equity_2026_session(day).window
        cutoff = session.open_ts + offset * MINUTE
        require(
            w.key.symbol == symbol
            and w.key.session_date == day
            and w.key.session_open == session.open_ts
            and w.key.cutoff == cutoff
            and w.key.entry == cutoff + MINUTE
            and w.key.exit == cutoff + 31 * MINUTE
            and w.context_minutes == 120
            and w.timeframe == Timeframe.M5
            and len(w.features) == 4
            and all(isfinite(v) for v in w.features)
            and len(w.sequence) == 24
            and all(len(v) == 4 and all(isfinite(x) for x in v) for v in w.sequence)
            and w.source_minute_starts
            == tuple(cutoff - 120 * MINUTE + i * MINUTE for i in range(120)),
            "cohort_geometry",
        )
        binding = w.key.dataset_id, w.key.dataset_hash
        require(
            type(binding[0]) is str
            and binding[0].startswith(
                f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1:"
            )
            and data._is_sha256(binding[1]),
            "source_identity",
        )
        require(binding == bindings.setdefault((symbol, day), binding), "date_binding")
    require(len(set(v[1] for v in bindings.values())) == 38, "independent_date_bindings")


def split(windows, dates):
    return tuple(w for w in windows if w.key.session_date in dates)


def controls(windows, train_gross):
    check_cohort(windows)
    dated._gross(train_gross, TRAIN_COUNT)
    with localcontext() as ctx:
        ctx.prec = 50
        mean = sum(train_gross, Decimal(0)) / TRAIN_COUNT
    return dict(
        train_mean=(mean > 6,) * 72,
        momentum=tuple(w.features[0] > 0 for w in split(windows, COMPARISON)),
        cash=(False,) * 72,
        always_long=(True,) * 72,
    )


def standardized(train, comparison):
    require(
        train.shape in ((TRAIN_COUNT, 4), (TRAIN_COUNT, 24, 4))
        and comparison.shape == (72, *train.shape[1:])
        and np.isfinite(train).all()
        and np.isfinite(comparison).all(),
        "input_shape",
    )
    axes = tuple(range(train.ndim - 1))
    mean, scale = train.mean(axis=axes), np.maximum(train.std(axis=axes), 1e-12)
    return (train - mean) / scale, (comparison - mean) / scale


def fit_ridge(train, y, comparison):
    from threadpoolctl import threadpool_limits

    x, future = standardized(train, comparison)
    x, future = np.column_stack((x, np.ones(TRAIN_COUNT))), np.column_stack((future, np.ones(72)))
    penalty = np.diag([1.0] * 4 + [0.0])
    with threadpool_limits(limits=2):
        return future @ np.linalg.solve(x.T @ x + penalty, x.T @ y)


def fit_network(torch, name, train, y, comparison, device, deadline, *, progress=None):
    require(name in ("lstm", "patch"), "model")
    torch.manual_seed(107)
    model = (
        build_torch_sequence_model(
            torch=torch,
            architecture_id="lstm",
            feature_count=4,
            hidden_size=16,
            attention_heads=2,
            tcn_kernel_size=3,
        )
        if name == "lstm"
        else build_torch_patch_sequence_model(
            torch=torch, feature_count=4, hidden_size=16, attention_heads=2, patch_length=6
        )
    ).to(device)
    x = torch.as_tensor(train, dtype=torch.float32, device=device)
    target = torch.as_tensor(y / 100, dtype=torch.float32, device=device).reshape(TRAIN_COUNT, 1)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=0)
    loss = torch.nn.HuberLoss(delta=0.1)
    model.train()
    for _ in range(128):
        require(time.monotonic() < deadline, "hard_timeout")
        optimizer.zero_grad(set_to_none=True)
        objective = loss(model(x), target)
        require(bool(torch.isfinite(objective)), "loss_finite")
        objective.backward()
        optimizer.step()
    model.eval()
    if progress is not None:
        progress["stage"] = "inference"
    with torch.no_grad():
        future = torch.as_tensor(comparison, dtype=torch.float32, device=device)
        prediction = model(future).reshape(-1).detach().cpu().numpy().astype(np.float64) * 100
    require(prediction.shape == (72,) and np.isfinite(prediction).all(), "prediction_shape")
    return prediction


def fit_actions(windows, train_gross, counts, deadline, *, device="cpu", progress=None):
    """No comparison targets enter this API. Completed inference returns immutable streams."""
    import torch

    result = controls(windows, train_gross)
    require(
        type(counts) is dict
        and counts == dict.fromkeys(MODELS, 0)
        and all(type(v) is int for v in counts.values()),
        "fit_retry_or_counts",
    )
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    train, comparison = split(windows, TRAIN), split(windows, COMPARISON)
    y = np.asarray(train_gross, dtype=np.float64)
    require(np.isfinite(y).all(), "target_finite")
    seq, future_seq = standardized(
        *[
            np.asarray([w.sequence for w in stream], dtype=np.float64)
            for stream in (train, comparison)
        ]
    )
    aggregate, future_aggregate = [
        np.asarray([w.features for w in stream], dtype=np.float64) for stream in (train, comparison)
    ]
    for name in MODELS:
        if progress is not None:
            progress["stage"] = "fit"
        require(time.monotonic() < deadline, "hard_timeout")
        counts[name] += 1
        prediction = (
            fit_ridge(aggregate, y, future_aggregate)
            if name == "ridge"
            else fit_network(torch, name, seq, y, future_seq, device, deadline, progress=progress)
        )
        require(prediction.shape == (72,) and np.isfinite(prediction).all(), "prediction_shape")
        result[name] = tuple(bool(v > 6) for v in prediction)
    require(time.monotonic() < deadline, "hard_timeout")
    if progress is not None:
        progress["stage"] = "inference"
    return tuple(result[p] for p in POLICIES)


def commitment(actions):
    require(
        type(actions) is tuple
        and len(actions) == 7
        and all(
            type(v) is tuple and len(v) == 72 and all(type(a) is bool for a in v) for v in actions
        ),
        "action_shape",
    )
    return digest(encode(actions))


def aggregate(windows, comparison_gross, actions):
    check_cohort(windows)
    dated._gross(comparison_gross, 72)
    pin = commitment(actions)
    comparison, daily = split(windows, COMPARISON), []
    with localcontext() as ctx:
        ctx.prec = 50
        for i, (target, day) in enumerate(product(TARGETS, COMPARISON)):
            a, b = i * 4, (i + 1) * 4
            daily.append(
                dict(
                    symbol=target[0],
                    date=str(day),
                    policies=[
                        dict(
                            policy=p,
                            decisions=4,
                            trades=sum(bits[a:b]),
                            gross_sum_unit_bps=str(
                                sum(
                                    (
                                        g * int(t)
                                        for g, t in zip(
                                            comparison_gross[a:b], bits[a:b], strict=True
                                        )
                                    ),
                                    Decimal(0),
                                )
                            ),
                            action_sha256=action_hash(comparison[a:b], bits[a:b]),
                        )
                        for p, bits in zip(POLICIES, actions, strict=True)
                    ],
                )
            )
        cells, nets = [], {}
        for symbol, _exchange in TARGETS:
            days = [d for d in daily if d["symbol"] == symbol]
            for i, p in enumerate(POLICIES):
                rows = [d["policies"][i] for d in days]
                trades = sum(r["trades"] for r in rows)
                gross = sum((Decimal(r["gross_sum_unit_bps"]) for r in rows), Decimal(0))
                nets[symbol, p] = tuple(
                    (Decimal(r["gross_sum_unit_bps"]) - 12 * r["trades"]) / 4 for r in rows
                )
                for cost in COSTS:
                    cells.append(
                        dict(
                            symbol=symbol,
                            policy=p,
                            cost_per_side_bps=cost,
                            decisions=36,
                            trades=trades,
                            gross_sum_unit_bps=str(gross),
                            mean_net_unit_bps=str((gross - 2 * Decimal(cost) * trades) / 36),
                            action_sha256=digest(encode([r["action_sha256"] for r in rows])),
                        )
                    )
        primary = sum(sum(nets[s, "patch"]) for s, _ in TARGETS) / 18
        increments, delete_etf, delete_day = {}, {}, {}
        for baseline in ("ridge", "lstm"):
            deltas = {
                s: tuple(a - b for a, b in zip(nets[s, "patch"], nets[s, baseline], strict=True))
                for s, _ in TARGETS
            }
            total = sum(sum(v) for v in deltas.values())
            increments[baseline] = total / 18
            delete_etf[baseline] = min(sum(v) / 9 for v in deltas.values())
            delete_day[baseline] = min(
                (total - sum(v[i] for v in deltas.values())) / 16 for i in range(9)
            )
        flags = (
            primary <= 0,
            any(v <= 0 for v in increments.values()),
            any(v <= 0 for v in delete_etf.values()),
            any(v <= 0 for v in delete_day.values()),
        )
        descriptive = dict(
            shared_session_blocks=9,
            stress_mean_net_unit_bps=str(primary),
            increments={p: str(v) for p, v in increments.items()},
            min_leave_one_ETF_out_increments={p: str(v) for p, v in delete_etf.items()},
            min_leave_one_shared_day_out_increments={p: str(v) for p, v in delete_day.items()},
            kill_categories=[k for k, f in zip(KILLS, flags, strict=True) if f],
        )
    return dict(commit_sha256=pin, daily=daily, cells=cells, descriptive=descriptive)


def verify_evaluation(windows, train_gross, comparison_gross, value):
    """Finite binary commitment reconstruction proves ledger math, not learned inference."""
    check_cohort(windows)
    require(
        type(value) is dict and set(value) == {"commit_sha256", "daily", "cells", "descriptive"},
        "evaluation_fields",
    )
    require(type(value["daily"]) is list and len(value["daily"]) == 18, "daily_count")
    actions, comparison = [() for _ in POLICIES], split(windows, COMPARISON)
    for i, ((target, day), record) in enumerate(
        zip(product(TARGETS, COMPARISON), value["daily"], strict=True)
    ):
        require(
            type(record) is dict
            and set(record) == {"symbol", "date", "policies"}
            and record["symbol"] == target[0]
            and record["date"] == str(day)
            and type(record["policies"]) is list
            and len(record["policies"]) == 7,
            "daily_shape",
        )
        for j, (p, row) in enumerate(zip(POLICIES, record["policies"], strict=True)):
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
            actions[j] += matches[0]
    controls_expected = controls(windows, train_gross)
    require(
        all(actions[POLICIES.index(p)] == bits for p, bits in controls_expected.items()),
        "control_actions",
    )
    require(
        encode(value) == encode(aggregate(windows, comparison_gross, tuple(actions))),
        "replay_identity",
    )


def synthetic_panel():
    windows, catalogs = (), {}
    for symbol, exchange in TARGETS:
        for i, day in enumerate(DATES):
            session = dated.us_equity_2026_session(day).window
            bars = []
            for minute in range(390):
                price = Decimal(100) + Decimal(minute) / 100 * (
                    1 if (i + (symbol == "SPY")) % 2 else -1
                )
                bars.append(
                    Bar(
                        symbol,
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
                dataset_id=f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1",
                dataset_hash=digest(encode([symbol, str(day)])),
                source_path=Path("synthetic-index.json"),
                bars=tuple(bars),
            )
            prepared = data.prepare_kis_paper_intraday_feature_input(catalog, session_dates=(day,))
            windows += build_windows(prepared)
            catalogs[symbol, day] = prepared.catalog
    check_cohort(windows)
    return windows, catalogs


def payoffs(windows, catalogs, dates):
    return tuple(
        gross_bps(w, catalogs[w.key.symbol, w.key.session_date]) for w in split(windows, dates)
    )


def cpu_smoke(deadline):
    windows, catalogs = synthetic_panel()
    train = payoffs(windows, catalogs, TRAIN)
    first = fit_actions(windows, train, dict.fromkeys(MODELS, 0), deadline)
    second = fit_actions(windows, train, dict.fromkeys(MODELS, 0), deadline)
    require(first == second, "synthetic_determinism")
    gross = payoffs(windows, catalogs, COMPARISON)
    verify_evaluation(windows, train, gross, aggregate(windows, gross, first))
    return dict(
        synthetic_windows=WINDOW_COUNT, synthetic_fits=6, actual_fits=0, cells=42, verified=True
    )
