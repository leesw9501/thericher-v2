"""One fixed, seen-source activity experiment; no execution or market-data I/O."""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

import numpy as np

from thericher_v2.contracts import Timeframe, require_utc
from thericher_v2.research.paired_completed_context import build_paired_completed_context
from thericher_v2.research.sequence_architecture_models import build_torch_sequence_model

MINUTE = timedelta(minutes=1)
SYMBOLS = ("QQQ", "SPY")
SLOTS = (120, 180, 240, 300)
KNOWN_FEATURES = (
    "is_QQQ",
    *tuple(f"slot_{slot}" for slot in SLOTS),
    *tuple(f"weekday_{day}" for day in range(5)),
    "scheduled_session_minutes_div390",
)
FEATURES = ("log1p_own_M5_volume", "log1p_peer_M5_volume", *KNOWN_FEATURES)
SUMMARIES = (
    *tuple(
        f"log1p_{side}_past{minutes}_volume"
        for side in ("own", "peer")
        for minutes in (120, 60, 30, 5)
    ),
    *KNOWN_FEATURES,
)
METHODS = ("gru", "train_slot_mean", "persistence", "seasonality", "ridge")
EPOCHS, BATCH_SIZE, SEED = 128, 128, 101


class VolumeFault(ValueError):
    """A categorical fault belonging only to this experiment."""


def require(condition, reason):
    if not condition:
        raise VolumeFault(reason)


@dataclass(frozen=True, slots=True, repr=False)
class VolumeRecord:
    session_date: date
    symbol: str
    slot: int
    decision_at: datetime
    features: tuple[tuple[float, ...], ...] | None
    summaries: tuple[float, ...] | None
    past30: float | None
    input_status: str
    target: float | None
    target_status: str
    target_available_at: datetime | None
    input_m1_count: int
    target_m1_count: int

    @property
    def key(self):
        return self.session_date, self.symbol, self.slot


def _target(bars, symbol, session, at):
    end = at + 31 * MINUTE
    selected = tuple(bar for bar in bars if at + MINUTE <= bar.start_ts < end)
    count = len(selected)
    if end > session.close_ts:
        return None, "calendar_target_unavailable", None, count
    require(len({bar.start_ts for bar in selected}) == count, "duplicate_target_keys")
    expected = tuple(at + index * MINUTE for index in range(1, 31))
    if tuple(bar.start_ts for bar in selected) != expected:
        return None, "required_forward_m1_shortfall", None, count
    require(
        all(
            bar.symbol == symbol and bar.market == "US" and bar.timeframe is Timeframe.M1
            for bar in selected
        ),
        "target_identity",
    )
    if any(bar.complete is not True or bar.end_ts > end for bar in selected):
        return None, "required_forward_m1_shortfall", None, count
    values = tuple(float(replace(bar).volume) for bar in selected)
    value = math.fsum(values)
    require(math.isfinite(value) and value >= 0, "target_volume_invalid")
    return value, "available", end, count


def records_from_pair(pair, session):
    """Keep all eight scheduled keys, even outside an early-close session."""
    require(len(pair) == 2, "pair_cardinality")
    result = []
    for slot in SLOTS:
        at = session.open_ts + slot * MINUTE
        context, input_status = None, "calendar_input_unavailable"
        past = tuple(
            tuple(bar for bar in bars if at - 120 * MINUTE <= bar.start_ts < at) for bars in pair
        )
        if at <= session.close_ts:
            for bars, symbol in zip(past, SYMBOLS, strict=True):
                require(len({bar.start_ts for bar in bars}) == len(bars), "duplicate_input_keys")
                require(
                    all(
                        bar.symbol == symbol
                        and bar.market == "US"
                        and bar.timeframe is Timeframe.M1
                        for bar in bars
                    ),
                    "input_identity",
                )
            try:
                context = build_paired_completed_context(
                    *past,
                    own_symbol="QQQ",
                    peer_symbol="SPY",
                    session=session,
                    observed_at=at,
                    timeframe=Timeframe.M5,
                    context_bars=24,
                )
                input_status = "available"
            except ValueError:
                input_status = "required_past_m1_shortfall"
        for index, symbol in enumerate(SYMBOLS):
            features, summaries, past30 = None, None, None
            if context is not None:
                volumes = tuple(
                    tuple(float(bar.volume) for bar in bars)
                    for bars in (context.own_bars, context.peer_bars)
                )
                own, peer = volumes[index], volumes[1 - index]
                known = (
                    float(symbol == "QQQ"),
                    *(float(slot == item) for item in SLOTS),
                    *(float(session.open_ts.weekday() == day) for day in range(5)),
                    (session.close_ts - session.open_ts) / MINUTE / 390,
                )
                features = tuple(
                    (math.log1p(a), math.log1p(b), *known) for a, b in zip(own, peer, strict=True)
                )
                summaries = (
                    tuple(
                        math.log1p(math.fsum(values[-count:]))
                        for values in (own, peer)
                        for count in (24, 12, 6, 1)
                    )
                    + known
                )
                past30 = math.fsum(own[-6:])
            target, target_status, available, target_count = _target(
                pair[index], symbol, session, at
            )
            result.append(
                VolumeRecord(
                    session.open_ts.date(),
                    symbol,
                    slot,
                    at,
                    features,
                    summaries,
                    past30,
                    input_status,
                    target,
                    target_status,
                    available,
                    len(past[index]),
                    target_count,
                )
            )
    return tuple(result)


def validate_records(rows, dates):
    require(
        len(dates) == 251 and len(set(dates)) == 251 and tuple(sorted(dates)) == tuple(dates),
        "scheduled_date_cardinality_or_order",
    )
    expected = {(day, symbol, slot) for day in dates for symbol in SYMBOLS for slot in SLOTS}
    keys = [row.key for row in rows]
    require(len(keys) == len(set(keys)) and set(keys) == expected, "scheduled_key_cardinality")
    for row in rows:
        at = require_utc(row.decision_at, "decision_at")
        require(at.date() == row.session_date, "decision_date")
        if row.features is not None:
            require(
                row.input_status == "available"
                and row.input_m1_count == 120
                and np.asarray(row.features).shape == (24, len(FEATURES))
                and np.asarray(row.summaries).shape == (len(SUMMARIES),)
                and np.isfinite(row.features).all()
                and np.isfinite(row.summaries).all()
                and row.past30 is not None
                and math.isfinite(row.past30)
                and row.past30 >= 0,
                "input_geometry_or_values",
            )
        else:
            require(
                row.input_status != "available" and row.summaries is None and row.past30 is None,
                "input_status_conflict",
            )
        if row.target is not None:
            require(
                row.target_status == "available"
                and row.target_m1_count == 30
                and row.target_available_at == at + 31 * MINUTE
                and math.isfinite(row.target)
                and row.target >= 0,
                "target_geometry_or_values",
            )
        else:
            require(
                row.target_status != "available" and row.target_available_at is None,
                "target_status_conflict",
            )


def split_records(rows, dates):
    validate_records(rows, dates)
    ordered = sorted(rows, key=lambda row: (row.session_date, row.slot, row.symbol))
    train_days, later_days = set(dates[:160]), set(dates[161:])
    return (
        tuple(row for row in ordered if row.session_date in train_days),
        tuple(row for row in ordered if row.session_date in later_days),
    )


def _scale(values):
    mean, scale = values.mean(axis=0), values.std(axis=0)
    # A constant feature/target uses unit scale, not a volume floor or imputation.
    return mean, np.where(scale == 0, 1.0, scale)


def _weights(rows):
    counts = Counter((row.session_date, row.symbol) for row in rows)
    symbols = Counter(day for day, _ in counts)
    return np.asarray(
        [
            len(rows)
            / (len(symbols) * symbols[row.session_date] * counts[row.session_date, row.symbol])
            for row in rows
        ]
    )


def train_statistics(train):
    """Feature scales use input-eligible TRAIN only; labels never mask input statistics."""
    inputs = [row for row in train if row.features is not None]
    fit_rows = [row for row in inputs if row.target is not None]
    require(len(fit_rows) >= 2, "TRAIN_target_shortfall")
    x = np.asarray([row.features for row in inputs], dtype=np.float64)
    summaries = np.asarray([row.summaries for row in inputs], dtype=np.float64)
    xm, xs = _scale(x.reshape(-1, len(FEATURES)))
    sm, ss = _scale(summaries)
    ym, ys = _scale(np.log1p([row.target for row in fit_rows]))
    means = []
    for symbol in SYMBOLS:
        for slot in SLOTS:
            group = [row for row in fit_rows if row.symbol == symbol and row.slot == slot]
            means.append(
                [None, None]
                if not group
                else [
                    math.fsum(row.target for row in group) / len(group),
                    math.fsum(row.past30 for row in group) / len(group),
                ]
            )
    return {
        "feature_mean": xm.tolist(),
        "feature_scale": xs.tolist(),
        "summary_mean": sm.tolist(),
        "summary_scale": ss.tolist(),
        "target_mean": float(ym),
        "target_scale": float(ys),
        "slot_means": means,
        "input_rows": len(inputs),
        "fit_rows": len(fit_rows),
    }


def training_arrays(train, stats):
    rows = tuple(row for row in train if row.features is not None and row.target is not None)
    x = (np.asarray([row.features for row in rows]) - stats["feature_mean"]) / stats[
        "feature_scale"
    ]
    z = (np.asarray([row.summaries for row in rows]) - stats["summary_mean"]) / stats[
        "summary_scale"
    ]
    y = (np.log1p([row.target for row in rows]) - stats["target_mean"]) / stats["target_scale"]
    return x, z, y, _weights(rows)


def fit_ridge(z, y, weights):
    design = np.column_stack((np.ones(len(z)), z))
    penalty = np.diag([0.0, *([1.0] * z.shape[1])])
    return np.linalg.solve(
        design.T @ (weights[:, None] * design) + penalty, design.T @ (weights * y)
    ).tolist()


def _model(torch):
    return build_torch_sequence_model(
        torch=torch,
        architecture_id="gru",
        feature_count=len(FEATURES),
        hidden_size=32,
        attention_heads=1,
        tcn_kernel_size=3,
    ).double()


def fit_gru(x, y, weights, *, deadline, device="cuda", vram_bytes=2 * 1024**3):
    """CPU is for synthetic tests only; the source runner always requests CUDA."""
    import torch

    require(device in ("cpu", "cuda"), "device")
    require(time.monotonic() < deadline, "compute_stop")
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    if device == "cuda":
        require(torch.cuda.is_available(), "CUDA_unavailable")
        free, total = torch.cuda.mem_get_info()
        require(0 < vram_bytes <= min(4 * 1024**3, free - 1024**3), "VRAM_headroom")
        torch.cuda.set_per_process_memory_fraction(vram_bytes / total)
        torch.cuda.manual_seed_all(SEED)
        torch.cuda.reset_peak_memory_stats()
    model = _model(torch).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    x, y, weights = (
        torch.tensor(value, dtype=torch.float64, device=device) for value in (x, y, weights)
    )
    require(
        x.shape[1:] == (24, len(FEATURES))
        and len(x) == len(y) == len(weights)
        and all(bool(torch.isfinite(value).all()) for value in (x, y, weights)),
        "training_array_geometry",
    )
    for _ in range(EPOCHS):
        for start in range(0, len(x), BATCH_SIZE):
            require(time.monotonic() < deadline, "compute_stop")
            optimizer.zero_grad(set_to_none=True)
            stop = start + BATCH_SIZE
            error = model(x[start:stop])[:, 0] - y[start:stop]
            loss = (weights[start:stop] * error.square()).mean()
            require(bool(torch.isfinite(loss)), "nonfinite_loss")
            loss.backward()
            require(
                all(
                    p.grad is None or bool(torch.isfinite(p.grad).all()) for p in model.parameters()
                ),
                "nonfinite_gradient",
            )
            optimizer.step()
            if device == "cuda":
                torch.cuda.synchronize()
                require(torch.cuda.max_memory_allocated() <= vram_bytes, "VRAM_stop")
    require(time.monotonic() < deadline, "compute_stop")
    state = {name: tensor.detach().cpu().tolist() for name, tensor in model.state_dict().items()}
    require(all(np.isfinite(value).all() for value in state.values()), "nonfinite_state")
    return state


def fit_models(train, *, deadline, vram_bytes):
    stats = train_statistics(train)
    x, z, y, weights = training_arrays(train, stats)
    return {
        "statistics": stats,
        "ridge": fit_ridge(z, y, weights),
        "gru": fit_gru(x, y, weights, deadline=deadline, vram_bytes=vram_bytes),
    }


def attest_train(models, train):
    require(models["statistics"] == train_statistics(train), "TRAIN_statistics_mismatch")
    _, z, y, weights = training_arrays(train, models["statistics"])
    design = np.column_stack((np.ones(len(z)), z))
    coefficients = np.asarray(models["ridge"])
    require(
        coefficients.shape == (len(SUMMARIES) + 1,) and np.isfinite(coefficients).all(),
        "ridge_state",
    )
    residual = design.T @ (weights * (design @ coefficients - y))
    residual[1:] += coefficients[1:]
    require(np.max(np.abs(residual)) <= 1e-8, "TRAIN_ridge_normal_equation")


def predict(models, rows, *, deadline=float("inf")):
    """Rebuild only on CPU, from numeric state; never inspect a target or fit."""
    import torch

    require(set(models) == {"statistics", "ridge", "gru"}, "model_payload")
    torch.set_num_threads(2)
    model = _model(torch)
    template = model.state_dict()
    require(set(models["gru"]) == set(template), "GRU_state_keys")
    state = {}
    for name, value in models["gru"].items():
        array = np.asarray(value, dtype=np.float64)
        require(
            array.shape == tuple(template[name].shape) and np.isfinite(array).all(),
            "GRU_state_geometry",
        )
        state[name] = torch.tensor(array, dtype=torch.float64)
    model.load_state_dict(state, strict=True)
    model.eval()
    stats, eligible = models["statistics"], [row for row in rows if row.features is not None]
    require(len({row.key for row in rows}) == len(rows), "duplicate_prediction_keys")
    result = {row.key: {method: None for method in METHODS} for row in rows}
    with torch.no_grad():
        for start in range(0, len(eligible), BATCH_SIZE):
            require(time.monotonic() < deadline, "compute_stop")
            batch = eligible[start : start + BATCH_SIZE]
            x = (np.asarray([row.features for row in batch]) - stats["feature_mean"]) / stats[
                "feature_scale"
            ]
            predicted = model(torch.tensor(x, dtype=torch.float64))[:, 0].numpy()
            for row, value in zip(batch, predicted, strict=True):
                mean, denominator = stats["slot_means"][
                    SYMBOLS.index(row.symbol) * 4 + SLOTS.index(row.slot)
                ]
                z = (np.asarray(row.summaries) - stats["summary_mean"]) / stats["summary_scale"]
                ridge = float(np.dot([1.0, *z], models["ridge"]))
                ratio = (
                    None if mean is None or denominator == 0 else mean / denominator * row.past30
                )
                result[row.key] = {
                    "gru": float(value),
                    "ridge": ridge,
                    "train_slot_mean": None
                    if mean is None
                    else (math.log1p(mean) - stats["target_mean"]) / stats["target_scale"],
                    "persistence": (math.log1p(row.past30) - stats["target_mean"])
                    / stats["target_scale"],
                    "seasonality": None
                    if ratio is None
                    else (math.log1p(ratio) - stats["target_mean"]) / stats["target_scale"],
                }
    require(
        all(
            value is None or math.isfinite(value)
            for values in result.values()
            for value in values.values()
        ),
        "nonfinite_forecast",
    )
    return result


def evaluate(rows, forecasts, stats, comparison_dates):
    """Same ETF/slot cohort for all controls; dates/halves precede exclusions."""
    require(
        len(comparison_dates) == 90
        and len(set(comparison_dates)) == 90
        and tuple(sorted(comparison_dates)) == tuple(comparison_dates),
        "comparison_dates",
    )
    expected = {
        (day, symbol, slot) for day in comparison_dates for symbol in SYMBOLS for slot in SLOTS
    }
    require(
        len(rows) == len(expected)
        and {row.key for row in rows} == expected
        and set(forecasts) == expected,
        "comparison_cardinality",
    )
    losses, exclusions = {}, Counter()
    for row in rows:
        prediction = forecasts[row.key]
        require(set(prediction) == set(METHODS), "forecast_methods")
        reason = (
            row.input_status
            if row.features is None
            else row.target_status
            if row.target is None
            else "control_unknown"
            if any(value is None for value in prediction.values())
            else None
        )
        if reason is not None:
            exclusions[reason] += 1
            continue
        require(all(math.isfinite(value) for value in prediction.values()), "forecast_values")
        target = (math.log1p(row.target) - stats["target_mean"]) / stats["target_scale"]
        losses[row.key] = {method: (prediction[method] - target) ** 2 for method in METHODS}

    def score(symbol, days):
        days = set(days)
        grouped = {}
        for (day, etf, _), values in losses.items():
            if etf == symbol and day in days:
                grouped.setdefault(day, []).append(values)
        means = {
            method: None
            if not grouped
            else math.fsum(
                math.fsum(values[method] for values in items) / len(items)
                for items in grouped.values()
            )
            / len(grouped)
            for method in METHODS
        }
        passes = bool(grouped) and all(
            means[control] > 0 and means["gru"] <= 0.95 * means[control] for control in METHODS[1:]
        )
        return {
            "scheduled_days": len(days),
            "eligible_days": len(grouped),
            "eligible_keys": sum(map(len, grouped.values())),
            "loss": means,
            "passes": passes,
        }

    groups = {
        "all90": comparison_dates,
        "first45": comparison_dates[:45],
        "last45": comparison_dates[45:],
    }
    report, passed = {}, True
    for symbol in SYMBOLS:
        report[symbol] = {}
        for name, dates in groups.items():
            base = score(symbol, dates)
            deletions = {
                day.isoformat(): score(symbol, [other for other in dates if other != day])
                for day in dates
            }
            base["delete_each_shared_date"] = deletions
            base["passes"] = base["passes"] and all(item["passes"] for item in deletions.values())
            passed = passed and base["passes"]
            report[symbol][name] = base
    return {
        "status": "survived_seen_development_kill" if passed else "rejected",
        "etfs": report,
        "exclusions": dict(exclusions),
        "paper_input": False,
    }
