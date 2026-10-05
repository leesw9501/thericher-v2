"""Frozen cross-asset information development; offline unit-bps evidence only."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, localcontext
from itertools import product
from math import isfinite
from pathlib import Path

import numpy as np

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_intraday as data
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.resample import SessionWindow
from thericher_v2.research import kis_equal_minute_resolution as resolution
from thericher_v2.research import kis_qqq_dated_downside_development as dated
from thericher_v2.research.sequence_architecture_models import build_torch_sequence_model

NAME = "kis-paired-lag-development-20261005-v1"
DATES = (
    date(2026, 8, 28),
    date(2026, 8, 31),
    date(2026, 9, 1),
    *dated.DATES,
    date(2026, 10, 1),
    date(2026, 10, 2),
)
TRAIN, EMBARGO, COMPARISON = DATES[:12], DATES[12], DATES[13:]
TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
TRAIN_OFFSETS, COMPARISON_OFFSETS = tuple(range(60, 326, 5)), (60, 150, 240, 300)
TRAIN_COUNT, COMPARISON_COUNT, WINDOW_COUNT = 1296, 96, 1392
MODELS = ("own_ridge", "paired_ridge", "paired_lstm", "paired_attention")
POLICIES = (*MODELS, "train_mean", "own_momentum", "cash", "always_long")
KILLS = (
    "nonpositive_stress_net",
    "nonpositive_increment",
    "ETF_dependence",
    "day_dependence",
    "future_peer_dependency",
    "target_replay_inconsistency",
)
CAUSAL_CHECKS = ("prefix_invariant", "normalization_invariant", "decision_inputs_invariant")
MINUTE, COSTS = dated.MINUTE, dated.COSTS
encode, digest, require = dated.encode, dated.digest, dated.require
us_equity_2026_session = dated.us_equity_2026_session


@dataclass(frozen=True, repr=False)
class PairedWindow:
    key: resolution.DecisionKey
    peer_key: resolution.DecisionKey
    source_minute_starts: tuple[datetime, ...]
    peer_minute_starts: tuple[datetime, ...]
    sequence: tuple[tuple[float, ...], ...]
    features: tuple[float, ...]


def configuration():
    return dict(
        dates=[str(d) for d in DATES],
        train=[str(d) for d in TRAIN],
        embargo=str(EMBARGO),
        comparison=[str(d) for d in COMPARISON],
        targets=[list(t) for t in TARGETS],
        geometry=dict(
            timeframe="5m",
            context_minutes=60,
            bars=12,
            own_channels=4,
            paired_channels=8,
            train_offsets=list(TRAIN_OFFSETS),
            comparison_offsets=list(COMPARISON_OFFSETS),
            history="[C-60min,C)",
        ),
        channel_order="prediction symbol own4 then exact other-symbol peer4; role-based pooling",
        per_bar_features="resolution._features: return_bps,range_bps,close_location,log1p_volume",
        aggregate="own4 then peer4: context return,mean range,last close location,relative volume",
        target="10000*(M1 OPEN C+61 / M1 OPEN C+1 - 1); 60min hold; NN grossbps/100",
        normalization="TRAIN-only float64 channel population mean/std floor1e-12; NN float32",
        ridge="pooled TRAIN aggregate4/8; L2=1; intercept unpenalized; NumPy solve",
        neural=dict(
            seed=109,
            epochs=128,
            batch=TRAIN_COUNT,
            optimizer="Adam",
            lr=0.001,
            weight_decay=0,
            loss="Huber",
            delta=0.1,
            hidden=16,
            heads=2,
            kernel=3,
            architectures=["lstm", "compact_attention"],
            dropout=0,
            final_epoch_only=True,
            selection=False,
        ),
        numeric="deterministic Torch; CUBLAS_WORKSPACE_CONFIG=:4096:8 set before import",
        action="forecast grossbps>6; TRAINmean>6; own_momentum context return>0",
        policies=list(POLICIES),
        costs_per_side_bps=list(COSTS),
        costs="1bp fee+2bp slip per side x1/1.5/2; immutable actions across costs",
        payoff="action*(grossbps-2*sidecost); descriptive unit bps NOT NAV or broker PnL",
        train_examples=TRAIN_COUNT,
        comparison_examples=COMPARISON_COUNT,
        shared_train_session_blocks=12,
        shared_session_blocks=12,
        source_count=50,
        cells=48,
        budget=dict(
            actual_fits=4,
            attempts=1,
            cpu_threads=2,
            memory_bytes=6 * 1024**3,
            seconds=500,
            gpu=True,
            synthetic_smoke_fits=8,
        ),
        smoke="two deterministic repeats; TRAIN16/comparison4 synthetic 12x8; 2 NN epochs",
        ordering="TRAIN targets -> two CPU ridge -> two CUDA NN -> immutable tuple/hash"
        " -> comparison targets/postdecision censoring -> replay",
        censoring="no future eligibility; retain every scheduled action; missing payoff is"
        " postdecision censored and kills target/replay consistency",
        kills=dict(
            nonpositive_stress_net="paired_attention stress mean net<=0",
            nonpositive_increment="attention-minus-own_ridge or paired_ridge mean<=0",
            ETF_dependence="either ETF deletion leaves either increment<=0; no refit",
            day_dependence="any shared-day deletion leaves either increment<=0; no refit",
            future_peer_dependency="future peer changes prefix, TRAIN scaler or decision inputs",
            target_replay_inconsistency="missing target or failed exact OPEN/action/cost replay",
        ),
        limitations=[
            "1296 overlapping TRAIN windows are12 shared blocks, not1296 IID examples",
            "96 comparison decisions are12 shared blocks, not24 independent ETF days",
            "revised/seen development, not untouched replication; PIT/finality unproved",
            "two ETFs; role-channel exchangeability/capacity/overlap confounds; no p-values",
            "ordinary causal temporal attention over8 features; not peer-specific lag"
            " cross-attention, DeltaLag reproduction or a strong lead-lag causal claim",
            "normalized gross-2sidecost approximation, not exact broker fee ledger or"
            " LocalPaper parity; latency/slippage/weight availability/source finality unobserved",
            "postdecision target missingness/skips visible; source inspiration only",
            "unretained learned inference is NOT independently reconstructed",
        ],
        scope="no forecasts/labels/weights/checkpoints/holdout spend/selection/promotion/Paper",
        lineage=dict(
            seen_development_families=[
                "kis-pooled-patch-return-development-v1",
                "kis-qqq-dated-downside-development-v1",
            ],
            inspiration_only=[
                "https://arxiv.org/html/2511.00390v1",
                "Garleanu author DynTrad.pdf",
                "https://arxiv.org/html/1904.04912v3",
            ],
            parent_retrieval_receipt="source-discovery/"
            "cross-asset-cost-20261005-engine-retrieval.json",
            original_source_receipt_sha256="sha256:"
            "3e3491b378a1c4401e67020b3e24bc286aa55d551093caa5d955d2271ab8ec8a",
            claim="distinct information family, shared seen sources; no position/cost learning",
        ),
    )


def dataset_id(target):
    return f"kis.paper.private.intraday.{target[0].lower()}.{target[1].lower()}.m1.v1"


def offsets(day):
    return TRAIN_OFFSETS if day in TRAIN else COMPARISON_OFFSETS if day in COMPARISON else ()


def _prefix(catalog, target, day, cutoff):
    require(
        isinstance(catalog, CatalogedBars)
        and catalog.dataset_id == dataset_id(target)
        and data._is_sha256(catalog.dataset_hash),
        "source_identity",
    )
    session = us_equity_2026_session(day).window
    start = cutoff - 60 * MINUTE
    expected = tuple(start + i * MINUTE for i in range(60))
    # Only timestamp-filtered past bars enter validation/resampling; future OHLCV is unread.
    bars = tuple(b for b in catalog.bars if start <= b.start_ts < cutoff)
    require(
        tuple(b.start_ts for b in bars) == expected
        and all(
            b.symbol == target[0]
            and b.market == "US"
            and b.timeframe == Timeframe.M1
            and b.complete
            and b.end_ts <= cutoff
            for b in bars
        ),
        "prefix_support",
    )
    require(session.open_ts <= start < cutoff < session.close_ts, "session_calendar")
    prefix = _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        source_path=catalog.source_path,
        bars=bars,
    )
    m5 = data.resample_verified_kis_paper_private_intraday_catalog(
        prefix, timeframe=Timeframe.M5, session=SessionWindow(start, cutoff)
    )
    require(
        not m5.skipped_bucket_starts
        and len(m5.bars) == 12
        and tuple(b.start_ts for b in m5.bars) == expected[::5],
        "M5_support",
    )
    with localcontext() as ctx:
        ctx.prec = 50
        seq = tuple(resolution._features(b) for b in m5.bars)
        volume = sum((b.volume for b in m5.bars), Decimal(0)) / 12
        aggregate = (
            float(10000 * (m5.bars[-1].close / m5.bars[0].open - 1)),
            sum(v[1] for v in seq) / 12,
            seq[-1][2],
            float(m5.bars[-1].volume / volume - 1) if volume else 0.0,
        )
    require(all(isfinite(v) for v in aggregate), "feature_finite")
    key = resolution.DecisionKey(
        catalog.dataset_id,
        catalog.dataset_hash,
        target[0],
        day,
        session.open_ts,
        cutoff,
        cutoff + MINUTE,
        cutoff + 61 * MINUTE,
    )
    return key, expected, seq, aggregate


def build_window(own, peer, *, day, offset):
    require(day in DATES and type(offset) is int and offset in offsets(day), "session_scope")
    target = next((t for t in TARGETS if own.dataset_id == dataset_id(t)), None)
    require(target is not None, "own_identity")
    peer_target = TARGETS[1 - TARGETS.index(target)]
    cutoff = us_equity_2026_session(day).window.open_ts + offset * MINUTE
    key, starts, seq, features = _prefix(own, target, day, cutoff)
    peer_key, peer_starts, peer_seq, peer_features = _prefix(peer, peer_target, day, cutoff)
    return PairedWindow(
        key,
        peer_key,
        starts,
        peer_starts,
        tuple(a + b for a, b in zip(seq, peer_seq, strict=True)),
        features + peer_features,
    )


def build_windows(own, peer, *, day):
    require(day in DATES, "session_scope")
    return tuple(build_window(own, peer, day=day, offset=o) for o in offsets(day))


def _key_identity(key, target, day, offset):
    require(isinstance(key, resolution.DecisionKey), "key_type")
    session = us_equity_2026_session(day).window
    cutoff = session.open_ts + offset * MINUTE
    require(
        key.dataset_id == dataset_id(target)
        and data._is_sha256(key.dataset_hash)
        and key.symbol == target[0]
        and key.session_date == day
        and key.session_open == session.open_ts
        and key.cutoff == cutoff
        and key.entry == cutoff + MINUTE
        and key.exit == cutoff + 61 * MINUTE
        and all(
            t.utcoffset() == 0 * MINUTE for t in (key.session_open, key.cutoff, key.entry, key.exit)
        ),
        "cohort_key",
    )


def check_cohort(windows):
    require(type(windows) is tuple and len(windows) == WINDOW_COUNT, "cohort_count")
    bindings, by_key = {}, {}
    expected = ((t, d, o) for t in TARGETS for d in DATES for o in offsets(d))
    for w, (target, day, offset) in zip(windows, expected, strict=True):
        require(type(w) is PairedWindow, "window_type")
        peer = TARGETS[1 - TARGETS.index(target)]
        _key_identity(w.key, target, day, offset)
        _key_identity(w.peer_key, peer, day, offset)
        starts = tuple(w.key.cutoff - 60 * MINUTE + i * MINUTE for i in range(60))
        require(
            type(w.sequence) is tuple
            and len(w.sequence) == 12
            and all(
                type(v) is tuple
                and len(v) == 8
                and all(type(x) is float and isfinite(x) for x in v)
                for v in w.sequence
            )
            and type(w.features) is tuple
            and len(w.features) == 8
            and all(type(v) is float and isfinite(v) for v in w.features)
            and w.source_minute_starts == starts
            and w.peer_minute_starts == starts,
            "cohort_geometry",
        )
        for key in (w.key, w.peer_key):
            binding = key.dataset_id, key.dataset_hash
            require(binding == bindings.setdefault((key.symbol, day), binding), "date_binding")
        by_key[target[0], day, offset] = w
    require(
        len(bindings) == 48 and len({v[1] for v in bindings.values()}) == 48,
        "distinct_source_bindings",
    )
    for (_symbol, day, offset), w in by_key.items():
        peer = by_key[w.peer_key.symbol, day, offset]
        require(
            w.peer_key == peer.key
            and w.features == peer.features[4:] + peer.features[:4]
            and w.sequence == tuple(v[4:] + v[:4] for v in peer.sequence),
            "peer_alignment",
        )


def split(windows, dates):
    return tuple(w for w in windows if w.key.session_date in dates)


def gross_bps(window, catalog, *, censor=False):
    require(
        (window.key.dataset_id, window.key.dataset_hash)
        == (catalog.dataset_id, catalog.dataset_hash),
        "payoff_source",
    )
    bars = tuple(b for b in catalog.bars if b.start_ts in (window.key.entry, window.key.exit))
    complete = (
        len(bars) == 2
        and tuple(b.start_ts for b in bars) == (window.key.entry, window.key.exit)
        and all(
            b.complete and b.timeframe == Timeframe.M1 and b.symbol == window.key.symbol
            for b in bars
        )
    )
    if censor and not complete:
        return None
    require(complete, "target_support")
    with localcontext() as ctx:
        ctx.prec = 50
        return 10000 * (bars[1].open / bars[0].open - 1)


def payoffs(windows, catalogs, dates):
    return tuple(
        gross_bps(w, catalogs[w.key.symbol, w.key.session_date], censor=dates == COMPARISON)
        for w in split(windows, dates)
    )


def controls(windows, train_gross):
    check_cohort(windows)
    dated._gross(train_gross, TRAIN_COUNT)
    with localcontext() as ctx:
        ctx.prec = 50
        mean = sum(train_gross, Decimal(0)) / TRAIN_COUNT
    return dict(
        train_mean=(mean > 6,) * COMPARISON_COUNT,
        own_momentum=tuple(w.features[0] > 0 for w in split(windows, COMPARISON)),
        cash=(False,) * COMPARISON_COUNT,
        always_long=(True,) * COMPARISON_COUNT,
    )


def standardized(train, comparison):
    require(
        type(train) is np.ndarray
        and type(comparison) is np.ndarray
        and train.dtype == comparison.dtype == np.float64
        and train.ndim in (2, 3)
        and train.shape[-1] in (4, 8)
        and train.shape[0] > 0
        and comparison.shape[0] > 0
        and comparison.shape[1:] == train.shape[1:]
        and (train.ndim == 2 or train.shape[1] == 12)
        and np.isfinite(train).all()
        and np.isfinite(comparison).all(),
        "input_shape",
    )
    axes = tuple(range(train.ndim - 1))
    mean, scale = train.mean(axis=axes), np.maximum(train.std(axis=axes), 1e-12)
    x, z = (train - mean) / scale, (comparison - mean) / scale
    require(np.isfinite(x).all() and np.isfinite(z).all(), "normalization_finite")
    return x, z


def fit_ridge(train, y, comparison):
    from threadpoolctl import threadpool_limits

    require(train.ndim == 2 and y.shape == (len(train),) and np.isfinite(y).all(), "ridge_shape")
    x, z = standardized(train, comparison)
    x, z = np.column_stack((x, np.ones(len(x)))), np.column_stack((z, np.ones(len(z))))
    penalty = np.diag([1.0] * train.shape[1] + [0.0])
    with threadpool_limits(limits=2):
        prediction = z @ np.linalg.solve(x.T @ x + penalty, x.T @ y)
    require(np.isfinite(prediction).all(), "prediction_finite")
    return prediction


def fit_network(torch, name, train, y, comparison, device, deadline, *, epochs=128, progress=None):
    require(
        name in MODELS[2:]
        and train.shape[1:] == (12, 8)
        and comparison.shape[1:] == (12, 8)
        and y.shape == (len(train),)
        and np.isfinite(y).all()
        and epochs in (2, 128),
        "network_shape",
    )
    torch.manual_seed(109)
    model = build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm" if name == "paired_lstm" else "compact_attention",
        feature_count=8,
        hidden_size=16,
        attention_heads=2,
        tcn_kernel_size=3,
    ).to(device)
    x = torch.as_tensor(train, dtype=torch.float32, device=device)
    target = torch.as_tensor(y / 100, dtype=torch.float32, device=device).reshape(len(y), 1)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=0)
    loss = torch.nn.HuberLoss(delta=0.1)
    model.train()
    for _ in range(epochs):
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
        prediction = model(torch.as_tensor(comparison, dtype=torch.float32, device=device))
        prediction = prediction.reshape(-1).detach().cpu().numpy().astype(np.float64) * 100
    require(
        prediction.shape == (len(comparison),) and np.isfinite(prediction).all(), "prediction_shape"
    )
    return prediction


def fit_actions(windows, train_gross, counts, deadline, *, device="cuda", progress=None):
    """Four final fits. Comparison labels and payoff eligibility cannot enter this API."""
    import torch

    result = controls(windows, train_gross)
    require(
        type(counts) is dict
        and counts == dict.fromkeys(MODELS, 0)
        and all(type(v) is int for v in counts.values()),
        "fit_retry_or_counts",
    )
    require(device == "cuda", "actual_CUDA_only")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    train, comparison = split(windows, TRAIN), split(windows, COMPARISON)
    y = np.asarray(train_gross, dtype=np.float64)
    seq, future_seq = standardized(
        *[
            np.asarray([w.sequence for w in stream], dtype=np.float64)
            for stream in (train, comparison)
        ]
    )
    a, b = [
        np.asarray([w.features for w in stream], dtype=np.float64) for stream in (train, comparison)
    ]
    for name in MODELS:
        if progress is not None:
            progress["stage"] = "fit"
        require(time.monotonic() < deadline, "hard_timeout")
        counts[name] += 1
        prediction = (
            fit_ridge(a[:, :4], y, b[:, :4])
            if name == "own_ridge"
            else fit_ridge(a, y, b)
            if name == "paired_ridge"
            else fit_network(torch, name, seq, y, future_seq, device, deadline, progress=progress)
        )
        require(
            prediction.shape == (COMPARISON_COUNT,) and np.isfinite(prediction).all(),
            "prediction_shape",
        )
        result[name] = tuple(bool(v > 6) for v in prediction)
    require(time.monotonic() < deadline, "hard_timeout")
    return tuple(result[p] for p in POLICIES)


def commitment(actions):
    require(
        type(actions) is tuple
        and len(actions) == len(POLICIES)
        and all(
            type(bits) is tuple
            and len(bits) == COMPARISON_COUNT
            and all(type(a) is bool for a in bits)
            for bits in actions
        ),
        "action_shape",
    )
    return digest(encode(actions))


def window_identity(w):
    return [
        [
            k.dataset_id,
            k.dataset_hash,
            k.symbol,
            str(k.session_date),
            k.cutoff.isoformat(),
            k.entry.isoformat(),
            k.exit.isoformat(),
        ]
        for k in (w.key, w.peer_key)
    ]


def action_hash(windows, actions):
    return digest(encode([[window_identity(w), a] for w, a in zip(windows, actions, strict=True)]))


def causal_audit(windows, catalogs):
    """Structural input audit, not reconstruction of unretained learned inference."""
    check_cohort(windows)
    comparison = split(windows, COMPARISON)
    rebuilt = []
    for w in comparison:
        own, peer = (catalogs[k.symbol, k.session_date] for k in (w.key, w.peer_key))
        prefix = _cataloged_bars_from_verified_loader(
            dataset_id=peer.dataset_id,
            dataset_hash=peer.dataset_hash,
            source_path=peer.source_path,
            bars=tuple(b for b in peer.bars if b.start_ts < w.key.cutoff),
        )
        corrupt = _cataloged_bars_from_verified_loader(
            dataset_id=peer.dataset_id,
            dataset_hash=peer.dataset_hash,
            source_path=peer.source_path,
            bars=tuple(
                replace(
                    b,
                    open=b.open * 7,
                    high=b.high * 7,
                    low=b.low * 7,
                    close=b.close * 7,
                    volume=b.volume * 11,
                    complete=False,
                )
                if b.start_ts >= w.key.cutoff
                else b
                for b in peer.bars
            ),
        )
        offset = int((w.key.cutoff - w.key.session_open) / MINUTE)
        a = build_window(own, prefix, day=w.key.session_date, offset=offset)
        b = build_window(own, corrupt, day=w.key.session_date, offset=offset)
        require(w == a == b, "future_peer_dependency")
        rebuilt.append(b)
    train = split(windows, TRAIN)
    for field in ("features", "sequence"):
        x = np.asarray([getattr(w, field) for w in train], dtype=np.float64)
        z = np.asarray([getattr(w, field) for w in comparison], dtype=np.float64)
        changed = np.asarray([getattr(w, field) for w in rebuilt], dtype=np.float64)
        before, after = standardized(x, z), standardized(x, changed)
        require(
            all(np.array_equal(a, b) for a, b in zip(before, after, strict=True)),
            "future_peer_dependency",
        )
    return dict.fromkeys(CAUSAL_CHECKS, True)


def aggregate(windows, comparison_gross, actions, *, causal_checks):
    check_cohort(windows)
    require(
        type(comparison_gross) is tuple
        and len(comparison_gross) == COMPARISON_COUNT
        and all(v is None or type(v) is Decimal and v.is_finite() for v in comparison_gross),
        "gross_shape",
    )
    require(
        type(causal_checks) is dict
        and set(causal_checks) == set(CAUSAL_CHECKS)
        and all(type(v) is bool for v in causal_checks.values()),
        "causal_checks",
    )
    pin = commitment(actions)
    comparison, daily = split(windows, COMPARISON), []
    with localcontext() as ctx:
        ctx.prec = 50
        for i, (target, day) in enumerate(product(TARGETS, COMPARISON)):
            a, b = 4 * i, 4 * (i + 1)
            gross = comparison_gross[a:b]
            daily.append(
                dict(
                    symbol=target[0],
                    date=str(day),
                    policies=[
                        dict(
                            policy=p,
                            decisions=4,
                            observed=sum(g is not None for g in gross),
                            trades=sum(
                                t and g is not None for t, g in zip(bits[a:b], gross, strict=True)
                            ),
                            scheduled_trades=sum(bits[a:b]),
                            gross_sum_unit_bps=str(
                                sum(
                                    (
                                        g * int(t)
                                        for g, t in zip(gross, bits[a:b], strict=True)
                                        if g is not None
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
        for symbol, _ in TARGETS:
            days = [d for d in daily if d["symbol"] == symbol]
            for j, p in enumerate(POLICIES):
                rows = [d["policies"][j] for d in days]
                trades, observed = sum(r["trades"] for r in rows), sum(r["observed"] for r in rows)
                gross = sum((Decimal(r["gross_sum_unit_bps"]) for r in rows), Decimal(0))
                # Fixed four scheduled anchors preserve equal shared-day deletion geometry.
                nets[symbol, p] = tuple(
                    (Decimal(r["gross_sum_unit_bps"]) - 12 * r["trades"]) / 4 for r in rows
                )
                for cost in COSTS:
                    cells.append(
                        dict(
                            symbol=symbol,
                            policy=p,
                            cost_per_side_bps=cost,
                            decisions=48,
                            observed=observed,
                            censored=48 - observed,
                            trades=trades,
                            scheduled_trades=sum(r["scheduled_trades"] for r in rows),
                            gross_sum_unit_bps=str(gross),
                            mean_net_unit_bps=str((gross - 2 * Decimal(cost) * trades) / 48),
                            action_sha256=digest(encode([r["action_sha256"] for r in rows])),
                        )
                    )
        primary = sum((sum(nets[s, "paired_attention"]) for s, _ in TARGETS), Decimal(0)) / 24
        increments, delete_etf, delete_day = {}, {}, {}
        for baseline in MODELS[:2]:
            deltas = {
                s: tuple(
                    a - b
                    for a, b in zip(nets[s, "paired_attention"], nets[s, baseline], strict=True)
                )
                for s, _ in TARGETS
            }
            total = sum((sum(v) for v in deltas.values()), Decimal(0))
            increments[baseline] = total / 24
            delete_etf[baseline] = min(sum(v) / 12 for v in deltas.values())
            delete_day[baseline] = min(
                (total - sum(v[i] for v in deltas.values())) / 22 for i in range(12)
            )
        flags = (
            primary <= 0,
            any(v <= 0 for v in increments.values()),
            any(v <= 0 for v in delete_etf.values()),
            any(v <= 0 for v in delete_day.values()),
            not all(causal_checks.values()),
            any(g is None for g in comparison_gross),
        )
        descriptive = dict(
            shared_session_blocks=12,
            stress_mean_net_unit_bps=str(primary),
            increments={p: str(v) for p, v in increments.items()},
            min_leave_one_ETF_out_increments={p: str(v) for p, v in delete_etf.items()},
            min_leave_one_shared_day_out_increments={p: str(v) for p, v in delete_day.items()},
            kill_categories=[k for k, f in zip(KILLS, flags, strict=True) if f],
        )
    return dict(
        commit_sha256=pin,
        daily=daily,
        cells=cells,
        descriptive=descriptive,
        causal_checks=causal_checks.copy(),
    )


def verify_evaluation(windows, train_gross, comparison_gross, value, *, causal_checks):
    """Reconstruct action commitments and exact replay; never fit or claim learned inference."""
    check_cohort(windows)
    require(
        type(value) is dict
        and set(value) == {"commit_sha256", "daily", "cells", "descriptive", "causal_checks"},
        "evaluation_fields",
    )
    require(type(value["daily"]) is list and len(value["daily"]) == 24, "daily_count")
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
            and len(record["policies"]) == 8,
            "daily_shape",
        )
        for j, (p, row) in enumerate(zip(POLICIES, record["policies"], strict=True)):
            require(
                type(row) is dict
                and set(row)
                == {
                    "policy",
                    "decisions",
                    "observed",
                    "trades",
                    "scheduled_trades",
                    "gross_sum_unit_bps",
                    "action_sha256",
                }
                and row["policy"] == p
                and all(
                    type(row[k]) is int and 0 <= row[k] <= 4
                    for k in ("decisions", "observed", "trades", "scheduled_trades")
                )
                and row["decisions"] == 4
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
    expected = controls(windows, train_gross)
    require(
        all(actions[POLICIES.index(p)] == bits for p, bits in expected.items()), "control_actions"
    )
    require(
        encode(value)
        == encode(
            aggregate(windows, comparison_gross, tuple(actions), causal_checks=causal_checks)
        ),
        "replay_identity",
    )


def synthetic_panel():
    catalogs = {}
    for symbol, exchange in TARGETS:
        for i, day in enumerate(DATES):
            session = us_equity_2026_session(day).window
            bars = []
            for minute in range(390):
                price = Decimal(100 + (symbol == "SPY")) + Decimal(minute) / 100 * (
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
                        Decimal(1000 + minute + (symbol == "SPY") * 100),
                    )
                )
            catalogs[symbol, day] = _cataloged_bars_from_verified_loader(
                dataset_id=dataset_id((symbol, exchange)),
                dataset_hash=digest(encode([symbol, str(day)])),
                source_path=Path("synthetic-index.json"),
                bars=tuple(bars),
            )
    windows = tuple(
        w
        for target in TARGETS
        for day in DATES
        for w in build_windows(
            catalogs[target[0], day], catalogs[TARGETS[1 - TARGETS.index(target)][0], day], day=day
        )
    )
    check_cohort(windows)
    return windows, catalogs


def smoke_result():
    return dict(
        synthetic_train=16,
        synthetic_comparison=4,
        sequence_shape=[12, 8],
        synthetic_epochs=2,
        synthetic_fits=8,
        actual_fits=0,
        verified=True,
    )


def cpu_smoke(deadline):
    """Small synthetic dimensions; never load a market panel or change the actual recipe."""
    import torch

    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    train = np.sin(np.arange(16 * 12 * 8, dtype=np.float64).reshape(16, 12, 8) / 37)
    future = np.cos(np.arange(4 * 12 * 8, dtype=np.float64).reshape(4, 12, 8) / 31)
    y = np.linspace(-17, 23, 16, dtype=np.float64)
    x, z = standardized(train, future)
    runs = []
    for _ in range(2):
        require(time.monotonic() < deadline, "hard_timeout")
        a, b = train.mean(axis=1), future.mean(axis=1)
        runs.append(
            (
                fit_ridge(a[:, :4], y, b[:, :4]),
                fit_ridge(a, y, b),
                *(
                    fit_network(torch, name, x, y, z, "cpu", deadline, epochs=2)
                    for name in MODELS[2:]
                ),
            )
        )
    require(all(np.array_equal(a, b) for a, b in zip(*runs, strict=True)), "synthetic_determinism")
    return smoke_result()
