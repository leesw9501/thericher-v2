"""Full regular-session development cohorts and a fixed cost/horizon comparison."""

from __future__ import annotations

import io
import json
import math
import time
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as h30

NAME = "regular-session-cost-matrix-v2"
FAMILY, REPO = h30.FAMILY, h30.REPO
HORIZONS, CONTEXTS, SEEDS, COSTS = (30, 60, 120), (12, 36), (101, 103), (1, 3, 5)
SECONDS = {"cpu": 1200, "cuda": 1800}
EPOCHS, BATCH = 8, 128
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
PARENT = "research/" + FAMILY + "/fixed-nominal-hurdle-v1/summary.json"
PARENT_HASH = "sha256:8a54c24785716d04bd1958bcce951a6e9bbaa7881d24a47e7b9fd4ada24db86b"
OWN_FILES = (
    "src/thericher_v2/research/firstrate_session_research.py",
    "scripts/run_firstrate_session_research.py",
    *h30.CODE_PATHS,
)


def require(condition, reason):
    if not condition:
        raise h30.StudyFailure(reason)


class OutcomeSupportShortfall(h30.StudyFailure):
    def __init__(self, eligible, observed, blocks):
        super().__init__("evaluation_outcome_support_shortfall")
        self.support = {
            "eligible": eligible,
            "observed": observed,
            "censored": eligible - observed,
            "blocks": blocks,
        }


def contract(receipt):
    base = h30.contract_payload(receipt)
    return {
        "name": NAME,
        "family": FAMILY,
        "source_pins": base["source_pins"],
        "normalization_sha256": h30.digest(receipt),
        "parent_summary_sha256": PARENT_HASH,
        "code_sha256": {p: h30.digest((REPO / p).read_bytes()) for p in OWN_FILES},
        "image_sha256": IMAGE,
        "evidence_grade": "OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
        "calendar": "pandas-market-calendars==5.4.0 NYSE regular sessions, DST/early closes",
        "timestamp_assumption": "existing New-York converted M1 start timestamps; NOT verified",
        "split": "calendar sessions first50%->next25%, first75%->last25%",
        "purge": "TRAIN exit strictly before first scheduled EVAL decision minus180minutes",
        "training_sampling": "EVERY5min from session open+180min; exit strictly before close",
        "evaluation_sampling": "every H minutes from session open+180min; exit before close",
        "eligibility": "same36 complete contiguous past M5 bars for every model/context",
        "censoring": "future path unavailable censored AFTER decisions; no backfill",
        "horizons_minutes": list(HORIZONS),
        "contexts": list(CONTEXTS),
        "seeds": list(SEEDS),
        "features": base["features"],
        "normalization": "scored TRAIN only, per fold/horizon",
        "target": "10000*(rounded open(d+H)/rounded open(d)-1)",
        "rule": "SMA3 of past closes > SMA12 of past closes",
        "naives": list(h30.NAIVES),
        "ridge": base["linear"],
        "lstm": base["model"],
        "training": base["training"],
        "prediction_threshold_bps": 6,
        "threshold_use": "fixed rule, NOT cost breakeven",
        "cost_bps_per_side": list(COSTS),
        "slippage_bps": 0,
        "quantity": 1,
        "pnl_semantics": "independent nonoverlapping one-share trades, NOT NAV",
        "budget": {
            "ridge_fits": 24,
            "lstm_fits": 48,
            "cpu_cells": 216,
            "cuda_cells": 144,
            "phase_seconds": SECONDS,
            "max_train_rows_per_fit": 40000,
            "epochs_per_fit": EPOCHS,
            "sample_cap": None,
        },
        "effective_sample": "count greedy nonoverlapping180min history blocks; rows correlated",
        "minimums": {
            "train": 128,
            "evaluation": 32,
            "train_blocks": 16,
            "eval_blocks": 8,
            "scored": 32,
            "scored_blocks": 8,
        },
        "strongest_kill_test": "future changes past input/scaler, TRAIN label overlaps EVAL "
        "history, outcome missingness changes decisions, or target/local-paper replay mismatch",
        "cpu_cuda_binding": "same frozen cohort/scalers/outcome counts; no PnL screening",
        "retained_weights": "all48 final epoch8 models, numeric-only NPZ and hashed config",
        "limitations": [
            "seen_data_not_independent",
            "clock_finality_actions_unverified",
            "overlapping_train_histories_and_labels",
            "posthoc_payoff_censoring",
            "fees_only_zero_latency",
            "no_KIS_parity",
            "not_continuous_capital",
        ],
        "promotion": False,
        "holdout_access": False,
        "selection": False,
        "retry": False,
    }


def freeze(root):
    root = h30.ensure_external_artifact_directory(root, REPO)
    receipt = h30.within(root, h30.RECEIPT).read_bytes()
    require(h30.digest(h30.within(root, PARENT).read_bytes()) == PARENT_HASH, "lineage_changed")
    payload = contract(receipt)
    output = h30.run_directory(root, NAME)
    output.mkdir(parents=True, exist_ok=False)
    raw = h30.encode(payload)
    (output / "contract.json").write_bytes(raw)
    h30.register_frozen_campaign(
        contract_hash=h30.digest(raw),
        dataset_hash=h30.digest(h30.encode(payload["source_pins"])),
        split_hash=h30.digest(
            h30.encode([payload[k] for k in ("split", "purge", "training_sampling")])
        ),
        cost_model_hash=h30.digest(h30.encode([COSTS, "fees_only", "independent_one_share"])),
        trial_family=FAMILY,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )
    return h30.digest(raw)


def verify(root, scope_hash):
    output = h30.run_directory(root, NAME)
    raw = (output / "contract.json").read_bytes()
    receipt = h30.within(root, h30.RECEIPT).read_bytes()
    require(
        h30.digest(raw) == scope_hash and raw == h30.encode(contract(receipt)), "contract_changed"
    )
    require(h30.digest(h30.within(root, PARENT).read_bytes()) == PARENT_HASH, "lineage_changed")
    return output, receipt, json.loads(raw)


def regular_sessions(bars):
    import pandas_market_calendars as calendars

    require(len(bars) > 0, "empty_source")
    dates = [b.start_ts.date() for b in bars]
    schedule = calendars.get_calendar("NYSE").schedule(start_date=min(dates), end_date=max(dates))
    return tuple(
        (r.market_open.to_pydatetime(), r.market_close.to_pydatetime())
        for r in schedule.itertuples()
    )


def session_grid(sessions, horizon, *, training):
    require(horizon in HORIZONS, "horizon_invalid")
    result = []
    for opening, closing in sessions:
        at = opening + 36 * h30.STEP
        while at + timedelta(minutes=horizon) < closing:
            result.append(at)
            at += h30.STEP if training else timedelta(minutes=horizon)
    return tuple(result)


def plans(sessions, horizon):
    require(len(sessions) >= 4, "session_support_shortfall")
    result = []
    for left, right in (
        (len(sessions) // 2, 3 * len(sessions) // 4),
        (3 * len(sessions) // 4, len(sessions)),
    ):
        evaluation = session_grid(sessions[left:right], horizon, training=False)
        require(bool(evaluation), "evaluation_support_shortfall")
        cutoff = evaluation[0] - 36 * h30.STEP
        training = tuple(
            t
            for t in session_grid(sessions[:left], horizon, training=True)
            if t + timedelta(minutes=horizon) < cutoff
        )
        result.append((training, evaluation, cutoff, right - left))
    return tuple(result)


def outcomes(index, observations, horizon):
    result, counts = [], Counter(eligible=len(observations), observed=0, future_missing=0)
    for obs in observations:
        path = tuple(index.get(obs.at + i * h30.STEP) for i in range(horizon // 5 + 1))
        if any(b is None or not b.complete for b in path):
            result.append(None)
            counts["future_missing"] += 1
            continue
        require(
            all(
                (b.symbol, b.market, b.timeframe) == (obs.signal.symbol, "US", h30.Timeframe.M5)
                for b in path
            ),
            "outcome_identity",
        )
        outcome = h30.Outcome(path)
        require(outcome.entry > 0 and outcome.exit > 0, "rounded_price")
        result.append(outcome)
        counts["observed"] += 1
    return tuple(result), dict(counts)


def prepare_fold(symbol, number, index, plan, horizon):
    train_times, eval_times, cutoff, eval_sessions = plan
    train_obs, train_counts = h30.observe(index, train_times)
    train_out, train_censor = outcomes(index, train_obs, horizon)
    pairs = [(o, y) for o, y in zip(train_obs, train_out, strict=True) if y is not None]
    fit_obs = [o for o, _ in pairs]
    evaluation, eval_counts = h30.observe(index, eval_times)
    require(all(y.bars[-1].start_ts < cutoff for _, y in pairs), "train_label_crosses_eval_history")
    require(128 <= len(pairs) <= 40000 and h30.blocks(fit_obs) >= 16, "training_support_shortfall")
    require(len(evaluation) >= 32 and h30.blocks(evaluation) >= 8, "evaluation_support_shortfall")
    train = np.asarray([o.features for o in fit_obs], dtype=np.float64)
    ev = np.asarray([o.features for o in evaluation], dtype=np.float64)
    y = np.asarray([v.target_bps for _, v in pairs], dtype=np.float64)
    mean, scale = train.mean(axis=(0, 1)), train.std(axis=(0, 1))
    scale = np.where(scale == 0, 1.0, scale)
    ym, ys = float(y.mean()), float(y.std()) or 1.0
    arrays = [
        np.asarray((train - mean) / scale, dtype=np.float32),
        np.asarray((ev - mean) / scale, dtype=np.float32),
        np.asarray((y - ym) / ys, dtype=np.float32),
    ]
    require(all(np.isfinite(a).all() for a in arrays), "normalization_invalid")
    for a in arrays:
        a.setflags(write=False)
    facts = {
        "symbol": symbol,
        "fold": number,
        "horizon_minutes": horizon,
        "training_inputs": train_counts,
        "training_outcomes": train_censor,
        "evaluation_inputs": eval_counts,
        "evaluation_outcomes": None,
        "train_rows": len(y),
        "train_blocks_36": h30.blocks(fit_obs),
        "eval_blocks_36": h30.blocks(evaluation),
        "eval_calendar_sessions": eval_sessions,
        "strict_train_eval_separation": True,
        "normalizer_sha256": h30.digest(mean.tobytes() + scale.tobytes() + h30.encode([ym, ys])),
        "cohort_sha256": h30.digest(
            h30.encode(
                [[o.at.isoformat() for o in fit_obs], [o.at.isoformat() for o in evaluation]]
            )
            + train.tobytes()
            + ev.tobytes()
            + y.tobytes()
        ),
    }
    return h30.PreparedFold(symbol, number, *arrays, ym, ys, mean, scale, evaluation, facts)


def candidates(phase):
    if phase == "cpu":
        return [(n, None, None) for n in (*h30.NAIVES, "sma3_12")] + [
            ("ridge", c, None) for c in CONTEXTS
        ]
    return [("lstm", c, seed) for c in CONTEXTS for seed in SEEDS]


def expected_keys(phase):
    return [
        (s, f, h, n, c, seed, cost)
        for s in h30.SYMBOLS
        for h in HORIZONS
        for f in (1, 2)
        for cost in COSTS
        for n, c, seed in candidates(phase)
    ]


def cell_key(cell):
    return tuple(
        cell[k]
        for k in (
            "symbol",
            "fold",
            "horizon_minutes",
            "candidate",
            "context",
            "seed",
            "cost_bps_per_side",
        )
    )


def payoff(obs, outcome, cost, emergency):
    store = h30.InMemoryCampaignEventStore()
    broker = h30.LocalPaperBroker(
        event_store=store,
        emergency_store=emergency,
        starting_cash=Decimal(10000),
        fee_bps=Decimal(cost),
        slippage_bps=Decimal(0),
    )
    fills = []
    for side, signal, bar in (
        ("buy", obs.signal, outcome.bars[0]),
        ("sell", outcome.bars[-2], outcome.bars[-1]),
    ):
        order = h30.OrderIntent(
            client_order_id=side,
            symbol=signal.symbol,
            market=signal.market,
            side=side,
            quantity=Decimal(1),
            limit_price=None,
            decision_id=side,
            created_at=signal.end_ts,
        )
        require(broker.submit_order(order).status == "accepted", "roundtrip_rejected")
        fill = broker.fill_next_bar(side, signal_bar=signal, execution_bar=bar).fill
        require(fill is not None and fill.source == "local_paper", "fill_missing")
        fills.append(fill)
    gross = outcome.exit - outcome.entry
    fees = sum(
        ((p * cost / 10000).quantize(Decimal("0.0001")) for p in (outcome.entry, outcome.exit)),
        Decimal(0),
    )
    account = h30.replay_local_paper_account(store, starting_cash=Decimal(10000))
    pnl = h30.replay_local_paper_realized_pnl(store.iter_events())
    require(
        fills[0].filled_at == obs.at
        and fills[1].filled_at == outcome.bars[-1].start_ts
        and fills[0].price == outcome.entry
        and fills[1].price == outcome.exit
        and sum(f.fee for f in fills) == fees
        and not account.positions
        and account.cash - 10000 == gross - fees
        and pnl.realized_after_cost_pnl == gross - fees
        and pnl.open_quantity == 0
        and pnl.local_paper_fill_count == 2,
        "target_fee_replay_parity",
    )
    return gross, fees


def fit(torch, fold, context, seed, deadline):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    model = h30.build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm",
        feature_count=4,
        hidden_size=16,
        attention_heads=1,
        tcn_kernel_size=3,
    ).cuda()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    x = torch.tensor(fold.train_x[:, -context:], device="cuda")
    y = torch.tensor(fold.train_y, device="cuda")
    before, updates = None, 0
    model.eval()
    with torch.inference_mode():
        before = float(torch.nn.functional.mse_loss(model(x).flatten(), y).item())
    model.train()
    for _ in range(EPOCHS):
        for start in range(0, len(y), BATCH):
            h30.check_time(deadline)
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.mse_loss(
                model(x[start : start + BATCH]).flatten(), y[start : start + BATCH]
            )
            require(bool(torch.isfinite(loss).item()), "nonfinite_loss")
            loss.backward()
            require(
                all(
                    p.grad is None or bool(torch.isfinite(p.grad).all().item())
                    for p in model.parameters()
                ),
                "nonfinite_gradient",
            )
            optimizer.step()
            updates += 1
    model.eval()
    with torch.inference_mode():
        after = float(torch.nn.functional.mse_loss(model(x).flatten(), y).item())
        predicted = (
            model(torch.tensor(fold.eval_x[:, -context:], device="cuda")).flatten().cpu().numpy()
        )
    require(np.isfinite([before, after]).all() and np.isfinite(predicted).all(), "nonfinite_fit")
    state = {"state." + k: v.detach().cpu().numpy().copy() for k, v in model.state_dict().items()}
    return (
        predicted,
        state,
        {
            "epochs": EPOCHS,
            "updates": updates,
            "train_rows": len(y),
            "initial_train_mse": before,
            "final_train_mse": after,
            "train_mean_baseline_mse": float(np.var(fold.train_y)),
        },
    )


def compare(
    streams,
    phase,
    emergency,
    deadline,
    *,
    torch=None,
    reference=None,
    trainer=fit,
    ridge=h30.ridge_predict,
    replay=payoff,
    schedules=None,
):
    result = {
        "status": "complete",
        "phase": phase,
        "name": NAME,
        "cells": [],
        "folds": [],
        "fits": [],
        "models": [],
        "promotion": False,
        "holdout_access": False,
        "evidence_grade": "OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
    }
    retained = []
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        sessions = regular_sessions(bars) if schedules is None else schedules
        for horizon in HORIZONS:
            for number, plan in enumerate(plans(sessions, horizon), 1):
                h30.check_time(deadline)
                fold = prepare_fold(symbol, number, index, plan, horizon)
                decisions = []
                for name, context, seed in candidates(phase):
                    if name == "ridge":
                        values = np.asarray(ridge(fold, context))
                        selected = values * fold.y_scale + fold.y_mean > 6
                    elif name == "lstm":
                        values, state, facts = trainer(torch, fold, context, seed, deadline)
                        values = np.asarray(values)
                        selected = values * fold.y_scale + fold.y_mean > 6
                        ident = dict(
                            symbol=symbol,
                            fold=number,
                            horizon_minutes=horizon,
                            context=context,
                            seed=seed,
                        )
                        result["fits"].append({**ident, **facts})
                        retained.append((fold, context, seed, state))
                    else:
                        values = np.zeros(len(fold.evaluation))
                        selected = np.asarray(
                            [
                                name == "always_long"
                                or (
                                    name == "previous_bar_direction"
                                    and o.signal.close > o.signal.open
                                )
                                or (
                                    name == "sma3_12"
                                    and sum(index[o.at - i * h30.STEP].close for i in range(1, 4))
                                    / 3
                                    > sum(index[o.at - i * h30.STEP].close for i in range(1, 13))
                                    / 12
                                )
                                for o in fold.evaluation
                            ]
                        )
                    require(
                        values.shape == (len(fold.evaluation),) and np.isfinite(values).all(),
                        "prediction_shape_or_finiteness",
                    )
                    decisions.append((name, context, seed, selected))
                observed, censor = outcomes(index, fold.evaluation, horizon)
                fold.facts["evaluation_outcomes"] = censor
                supported = [
                    o for o, y in zip(fold.evaluation, observed, strict=True) if y is not None
                ]
                scored_blocks = h30.blocks(supported)
                if len(supported) < 32 or scored_blocks < 8:
                    raise OutcomeSupportShortfall(len(observed), len(supported), scored_blocks)
                fold.facts["scored_blocks_36"] = scored_blocks
                if phase == "cuda":
                    prior = next(
                        f
                        for f in reference["folds"]
                        if (f["symbol"], f["fold"], f["horizon_minutes"])
                        == (symbol, number, horizon)
                    )
                    require(fold.facts == prior, "cpu_cuda_cohort_changed")
                result["folds"].append(fold.facts)
                for cost in COSTS:
                    replays = []
                    for obs, out in zip(fold.evaluation, observed, strict=True):
                        h30.check_time(deadline)
                        replays.append(None if out is None else replay(obs, out, cost, emergency))
                    for name, context, seed, selected in decisions:
                        trades = [
                            r
                            for flag, r in zip(selected, replays, strict=True)
                            if flag and r is not None
                        ]
                        gross = sum((r[0] for r in trades), Decimal(0))
                        fees = sum((r[1] for r in trades), Decimal(0))
                        net = gross - fees
                        turnover = sum(
                            (
                                o.entry + o.exit
                                for flag, o in zip(selected, observed, strict=True)
                                if flag and o is not None
                            ),
                            Decimal(0),
                        )
                        result["cells"].append(
                            {
                                "symbol": symbol,
                                "fold": number,
                                "horizon_minutes": horizon,
                                "candidate": name,
                                "context": context,
                                "seed": seed,
                                "cost_bps_per_side": cost,
                                "eligible_decisions": len(selected),
                                "selected_decisions": int(selected.sum()),
                                "future_censored": censor["future_missing"],
                                "selected_censored": sum(
                                    bool(v) and r is None
                                    for v, r in zip(selected, replays, strict=True)
                                ),
                                "roundtrips": len(trades),
                                "gross_dollars": str(gross),
                                "fees_dollars": str(fees),
                                "net_dollars": str(net),
                                "turnover_dollars": str(turnover),
                                "roundtrips_per_session": len(trades) / plan[3],
                                "wins": sum(g > f for g, f in trades),
                                "local_paper_replay_parity": True,
                            }
                        )
    return result, retained


def failure(phase, scope_hash, reason):
    return {
        "name": NAME,
        "phase": phase,
        "status": "failed_all_phase_cells",
        "contract_sha256": scope_hash,
        "reason": reason,
        "cells": [],
        "folds": [],
        "fits": [],
        "models": [],
        "promotion": False,
        "holdout_access": False,
    }


def validate_result(result, phase, scope_hash):
    require(
        result["status"] == "complete"
        and result["contract_sha256"] == scope_hash
        and result["phase"] == phase
        and result["name"] == NAME
        and result["promotion"] is False
        and result["holdout_access"] is False,
        "result_identity",
    )
    require([cell_key(c) for c in result["cells"]] == expected_keys(phase), "cell_matrix")
    require(
        len(result["folds"]) == 12 and len(result["fits"]) == (48 if phase == "cuda" else 0),
        "fit_matrix",
    )
    for f in result["fits"]:
        require(
            f["epochs"] == EPOCHS and f["updates"] == EPOCHS * math.ceil(f["train_rows"] / BATCH),
            "training_passes",
        )
    for cell in result["cells"]:
        require(
            Decimal(cell["gross_dollars"]) - Decimal(cell["fees_dollars"])
            == Decimal(cell["net_dollars"])
            and cell["local_paper_replay_parity"] is True,
            "result_accounting",
        )


def save_models(root, retained, scope_hash):
    require(len(retained) == 48, "model_matrix")
    root.mkdir(exist_ok=False)
    refs = []
    for fold, context, seed, state in retained:
        arrays = {
            **state,
            "channel_mean": fold.channel_mean,
            "channel_scale": fold.channel_scale,
            "target_mean": np.array([fold.y_mean]),
            "target_scale": np.array([fold.y_scale]),
        }
        h30.validate_model_arrays(arrays)
        identity = dict(
            symbol=fold.symbol,
            fold=fold.fold,
            horizon_minutes=fold.facts["horizon_minutes"],
            context=context,
            seed=seed,
        )
        name = "-".join(str(v) for v in identity.values())
        with (root / (name + ".npz")).open("xb") as handle:
            np.savez(handle, **arrays)
        config = {
            **identity,
            "name": NAME,
            "contract_sha256": scope_hash,
            "epochs": EPOCHS,
            "architecture": "lstm",
            "hidden_size": 16,
            "feature_count": 4,
            "cohort_sha256": fold.facts["cohort_sha256"],
            "weights_sha256": h30.digest((root / (name + ".npz")).read_bytes()),
            "weights_file": name + ".npz",
            "private_development_only": True,
        }
        raw = h30.encode(config)
        with (root / (name + ".json")).open("xb") as handle:
            handle.write(raw)
        refs.append(
            {
                **identity,
                "config_file": name + ".json",
                "config_sha256": h30.digest(raw),
                "weights_file": name + ".npz",
                "weights_sha256": config["weights_sha256"],
            }
        )
    return refs


def verify_models(root, result, scope_hash):
    expected = [
        (s, f, h, c, seed)
        for s in h30.SYMBOLS
        for h in HORIZONS
        for f in (1, 2)
        for c in CONTEXTS
        for seed in SEEDS
    ]
    require(
        [
            tuple(r[k] for k in ("symbol", "fold", "horizon_minutes", "context", "seed"))
            for r in result["models"]
        ]
        == expected,
        "model_matrix",
    )
    import torch

    for ref in result["models"]:
        raw = h30.within(root, ref["config_file"]).read_bytes()
        require(h30.digest(raw) == ref["config_sha256"], "model_config_hash")
        cfg = json.loads(raw)
        require(
            cfg["contract_sha256"] == scope_hash
            and cfg["name"] == NAME
            and cfg["epochs"] == EPOCHS
            and all(
                cfg[k] == ref[k] for k in ("symbol", "fold", "horizon_minutes", "context", "seed")
            ),
            "model_config_identity",
        )
        path = h30.within(root, ref["weights_file"])
        require(path.stat().st_size < 1024**2, "model_size")
        raw = path.read_bytes()
        require(
            h30.digest(raw) == cfg["weights_sha256"] == ref["weights_sha256"], "model_weights_hash"
        )
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            arrays = {k: archive[k].copy() for k in archive.files}
        h30.validate_model_arrays(arrays)
        model = h30.build_torch_sequence_model(
            torch=torch,
            architecture_id="lstm",
            feature_count=4,
            hidden_size=16,
            attention_heads=1,
            tcn_kernel_size=3,
        )
        model.load_state_dict(
            {
                k.removeprefix("state."): torch.from_numpy(v)
                for k, v in arrays.items()
                if k.startswith("state.")
            },
            strict=True,
        )
        model.eval()
        with torch.inference_mode():
            require(
                bool(torch.isfinite(model(torch.zeros(2, ref["context"], 4))).all().item()),
                "model_reload",
            )


def worker(root, market, scope_hash, phase, cpu_hash, path):
    deadline = time.monotonic() + SECONDS[phase]
    result = failure(phase, scope_hash, "runtime_or_binding_failure")
    try:
        require(
            h30.importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version"
        )
        output, receipt, _payload = verify(root, scope_hash)
        reference = None
        if phase == "cuda":
            raw = (output / "cpu-summary.json").read_bytes()
            require(h30.digest(raw) == cpu_hash, "cpu_summary_hash")
            reference = json.loads(raw)
            validate_result(reference, "cpu", scope_hash)
        torch, runtime = h30.configure_cuda() if phase == "cuda" else (None, {"backend": "cpu"})
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=1):
            result, retained = compare(
                h30.load_streams(market, receipt, deadline),
                phase,
                h30.EmergencyStore(Path(path).parent / "emergency.json"),
                deadline,
                torch=torch,
                reference=reference,
            )
        result.update(
            contract_sha256=scope_hash,
            runtime={**runtime, "environment": h30.runtime_identity()},
            cpu_summary_sha256=cpu_hash,
        )
        validate_result(result, phase, scope_hash)
        if phase == "cuda":
            result["models"] = save_models(Path(path).parent / "models", retained, scope_hash)
            verify_models(Path(path).parent / "models", result, scope_hash)
        h30.check_time(deadline)
    except OutcomeSupportShortfall as error:
        result = failure(phase, scope_hash, "evaluation_outcome_support_shortfall")
        result["support"] = error.support
    except h30.StudyFailure as error:
        reason = str(error)
        result = failure(
            phase,
            scope_hash,
            reason
            if reason
            in {
                "calendar_version",
                "contract_changed",
                "lineage_changed",
                "cpu_summary_hash",
                "training_support_shortfall",
                "evaluation_support_shortfall",
                "source_hash",
                "source_changed",
                "source_order",
                "train_label_crosses_eval_history",
                "cpu_cuda_cohort_changed",
                "target_fee_replay_parity",
                "budget_exhausted",
                "nonfinite_loss",
                "nonfinite_gradient",
                "nonfinite_fit",
                "model_reload",
                "cell_matrix",
                "fit_matrix",
                "training_passes",
                "result_accounting",
            }
            else "study_invariant_failed",
        )
    except Exception:
        result = failure(phase, scope_hash, "runtime_or_invariant_failure")
    with Path(path).open("xb") as handle:
        handle.write(h30.encode(result))
