"""One daily H180 decision with fixed sequence members and an equal forecast blend."""

from __future__ import annotations

import importlib.metadata
import io
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_family_comparison as family
from thericher_v2.research import firstrate_policy_graph as base
from thericher_v2.research import session_sequence_models as models

sessions, h30 = family.sessions, family.h30
NAME = "firstrate-m5-single-session-h180-development-v1"
REPO, SECONDS, HORIZON, COSTS = base.REPO, 1800, 180, (1, 3, 5)
CPU = ("cash", "always_long", "sma3_12", "train_mean", "ridge")
MEMBERS = tuple((name, seed) for name in family.models.ARCHITECTURES for seed in (101, 103))
GPU = tuple(f"{name}_{seed}" for name, seed in MEMBERS) + ("uniform_four",)
POLICIES = CPU + GPU
encode, digest, require, atomic_new, _read = (
    base.encode,
    base.digest,
    base.require,
    base.atomic_new,
    base._read,
)
CODE = tuple(
    dict.fromkeys(
        (
            *base.CODE,
            *family.CODE,
            "src/thericher_v2/research/session_sequence_models.py",
            "src/thericher_v2/research/firstrate_session_h180.py",
            "scripts/run_firstrate_session_h180.py",
        )
    )
)


def configuration():
    return dict(
        symbols=list(h30.SYMBOLS),
        horizon_minutes=180,
        context=36,
        policies=list(POLICIES),
        costs=list(COSTS),
        decision_threshold_bps=6,
        quantity=1,
        side="long_only; failed gate stays flat",
        timing="M5 start stamps assumed;36 bars end12:30;entry12:30 open;exit15:30 open",
        sampling="EVAL one open+180min/session;TRAIN every5min fromopen+180 while exit<close",
        early_closes="calendar-only exclusions when open+360min>=close; no future-price mask",
        split="calendar first50->next25 and first75->last25; fold2 TRAIN includes fold1 EVAL",
        purge="TRAIN exit strictly before first scheduled EVAL decision minus180min",
        normalization="TRAIN-only four OHLCV channels and grossbps target; no EVAL fitting",
        target="rounded exit open/rounded entry open minus1, inbps; same local_paper payoff",
        models="existing hidden16 TCN(RF63) and causal attention;seeds101/103;32epochs/batch128",
        optimization="AdamW.001/wd.01;chronological;no earlystop/tuning;all final models retained",
        ensemble="uniform mean of four normalized GPU forecasts;Ridge excluded;no learned weights",
        baseline="cash,matched3h long(notbuyhold),pastSMA3/12,TRAINmean,Ridgealpha1/SVD",
        gate="fixed nominal6bps all costs;not exact breakeven;cost changes accounting only",
        support="TRAIN>=128 and16historyblocks;EVAL>=32 and8blocks;common post-decision censoring",
        diagnostics="per-fold MSE inbps2 vs TRAINmean; support/actions/PnL; no pooled inference",
        fits=dict(ridge=4, cuda=16),
        cells=120,
        cpu_cells=60,
        budget=dict(seconds=SECONDS, epochs=32, batch=128, passes=1, gpu_lock=True),
        vram="min(90percent total,free minus1GiB); no inherited4GiB cap;no artificial padding",
        retention="16 numericNPZ weights/scalers/config hashes;reload prediction/decision parity",
        reload="rtol1e-5/atol1e-6;same >6bps decisions;deterministic kernels;no cross-runtime bits",
        kill="future changes earlier input/model;cohort/cost/payoff/reload mismatch;finite support",
        limits=[
            "seen_data_not_independent",
            "clock_revision_finality_unverified",
            "zero_latency_fills",
            "correlated_overlapping_TRAIN",
            "expanding_folds_dependent",
            "posthoc_common_outcome_censor",
            "one_share_not_NAV",
            "no_KIS_parity",
        ],
        promotion=False,
        selection=False,
        holdout=False,
        broker_input=False,
        image=sessions.IMAGE,
    )


def proposed_contract(root):
    raw = _read(Path(root) / h30.RECEIPT)
    source = h30.contract_payload(raw)["source_pins"]
    cfg = configuration()
    return dict(
        name=NAME,
        config=cfg,
        config_sha256=digest(encode(cfg)),
        receipt_sha256=digest(raw),
        source_pins=source,
        runtime={
            p: importlib.metadata.version(p)
            for p in ("numpy", "scipy", "scikit-learn", "torch", "pandas-market-calendars")
        },
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def header(contract, pin):
    require(digest(encode(contract)) == pin and contract["name"] == NAME, "contract_hash")
    require(
        contract["config"] == configuration()
        and contract["config_sha256"] == digest(encode(configuration())),
        "config_changed",
    )
    return dict(
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        evidence_grade="OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
    )


def register_contract(root, contract, pin):
    header(contract, pin)
    base.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=digest(encode(contract["source_pins"])),
        split_hash=digest(encode(configuration()["split"])),
        cost_model_hash=digest(encode([COSTS, "one_daily_H180_local_paper"])),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root, market_data_root):
    require(h30.source_root_allowed(Path(market_data_root).resolve(), REPO), "source_root")
    contract = proposed_contract(artifact_root)
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research") / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root, market_data_root, pin):
    require(h30.source_root_allowed(Path(market_data_root).resolve(), REPO), "source_root")
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research", NAME)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin and raw == encode(proposed_contract(artifact_root)), "binding")
    return output, json.loads(raw)


def plans(schedule):
    require(len(schedule) >= 4, "session_support")

    def grid(items, training):
        result = []
        for opening, closing in items:
            at = opening + timedelta(minutes=180)
            while at + timedelta(minutes=180) < closing:
                result.append(at)
                if not training:
                    break
                at += h30.STEP
        return tuple(result)

    result = []
    for left, right in (
        (len(schedule) // 2, 3 * len(schedule) // 4),
        (3 * len(schedule) // 4, len(schedule)),
    ):
        evaluation = grid(schedule[left:right], False)
        require(bool(evaluation), "evaluation_support")
        cutoff = evaluation[0] - timedelta(minutes=180)
        train = tuple(t for t in grid(schedule[:left], True) if t + timedelta(minutes=180) < cutoff)
        result.append((train, evaluation, cutoff, right - left))
    return tuple(result)


def cpu_predictions(fold, index):
    n = len(fold.evaluation)
    forecast = np.asarray(h30.ridge_predict(fold, 36), dtype=np.float64)
    require(forecast.shape == (n,) and np.isfinite(forecast).all(), "forecast")
    values = forecast * fold.y_scale + fold.y_mean
    selected = dict(
        cash=np.zeros(n, dtype=bool),
        always_long=np.ones(n, dtype=bool),
        sma3_12=np.asarray(
            [
                sum(index[o.at - i * h30.STEP].close for i in range(1, 4)) / 3
                > sum(index[o.at - i * h30.STEP].close for i in range(1, 13)) / 12
                for o in fold.evaluation
            ],
            dtype=bool,
        ),
        train_mean=np.full(n, fold.y_mean > 6, dtype=bool),
        ridge=values > 6,
    )
    for flags in selected.values():
        flags.setflags(write=False)
    return selected, dict(ridge=values, train_mean=np.full(n, fold.y_mean))


def score(fold, selected, forecasts, observed, emergency, deadline):
    require(
        all(v.shape == (len(observed),) and v.dtype == bool for v in selected.values()),
        "decision_geometry",
    )
    support = [i for i, outcome in enumerate(observed) if outcome is not None]
    require(
        len(support) >= 32 and h30.blocks([fold.evaluation[i] for i in support]) >= 8,
        "evaluation_outcome_support",
    )
    actual = np.asarray([observed[i].target_bps for i in support], dtype=np.float64)
    cells = []
    for cost in COSTS:
        replays = {}
        for i in support:
            h30.check_time(deadline)
            replays[i] = sessions.payoff(fold.evaluation[i], observed[i], cost, emergency)
        for name, flags in selected.items():
            included = [i for i in support if flags[i]]
            gross = sum((replays[i][0] for i in included), Decimal(0))
            fees = sum((replays[i][1] for i in included), Decimal(0))
            turnover = sum((observed[i].entry + observed[i].exit for i in included), Decimal(0))
            cells.append(
                dict(
                    symbol=fold.symbol,
                    fold=fold.fold,
                    policy=name,
                    cost=cost,
                    selected=int(flags.sum()),
                    censored=int(flags.sum()) - len(included),
                    roundtrips=len(included),
                    wins=sum(replays[i][0] > replays[i][1] for i in included),
                    gross=str(gross),
                    fees=str(fees),
                    net=str(gross - fees),
                    turnover=str(turnover),
                    exposure_minutes=len(included) * 180,
                    decision_sha256=digest(flags.tobytes()),
                    local_paper=True,
                )
            )
    metrics = {
        name: float(np.mean((values[support] - actual) ** 2)) for name, values in forecasts.items()
    }
    require(all(np.isfinite(v) for v in metrics.values()), "nonfinite_metric")
    return cells, metrics


def retain_model(root, fold, architecture, seed, state, predicted, pin, torch):
    root.mkdir(exist_ok=True)
    name = f"{fold.symbol}-{fold.fold}-{architecture}-{seed}"
    arrays = {**state, **family.scaler_arrays(fold)}
    buffer = io.BytesIO()
    np.savez(buffer, **arrays)
    raw = buffer.getvalue()
    path = root / f"{name}.npz"
    with path.open("xb") as handle:
        handle.write(raw)
    loaded = family.read_arrays(path)
    family.check_scalers(loaded, fold)
    restored = family.restore_sequence(torch, architecture, loaded)
    again = family.sequence_predict(torch, restored, fold.eval_x, "cuda")
    require(
        np.allclose(again, predicted, rtol=1e-5, atol=1e-6)
        and np.array_equal(to_bps(fold, again) > 6, to_bps(fold, predicted) > 6),
        "model_reload",
    )
    cfg = dict(
        symbol=fold.symbol,
        fold=fold.fold,
        architecture=architecture,
        seed=seed,
        name=NAME,
        contract_sha256=pin,
        weights_file=path.name,
        weights_sha256=digest(raw),
        normalizer_sha256=fold.facts["normalizer_sha256"],
        cohort_sha256=fold.facts["cohort_sha256"],
        horizon_minutes=180,
        epochs=32,
        numeric_only=True,
        reload_parity=True,
    )
    atomic_new(root / f"{name}.json", cfg)
    return dict(file=f"{name}.json", sha256=digest(encode(cfg)), **cfg), again


def to_bps(fold, values):
    return np.asarray(values, dtype=np.float64) * fold.y_scale + fold.y_mean


def prepare(streams):
    prepared = []
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        for number, plan in enumerate(plans(sessions.regular_sessions(bars)), 1):
            fold = sessions.prepare_fold(symbol, number, index, plan, HORIZON)
            selected, forecast = cpu_predictions(fold, index)
            prepared.append((fold, index, selected, forecast))
    require(
        [(f.symbol, f.fold) for f, *_ in prepared] == [(s, n) for s in h30.SYMBOLS for n in (1, 2)],
        "fold_matrix",
    )
    return prepared


def cpu_compare(prepared, emergency, deadline):
    folds, cells = [], []
    for fold, index, selected, forecasts in prepared:
        observed, support = sessions.outcomes(index, fold.evaluation, HORIZON)
        scored, metrics = score(fold, selected, forecasts, observed, emergency, deadline)
        cells.extend(scored)
        folds.append(dict(**fold.facts, outcome_support=support, mse_bps2=metrics))
    return dict(folds=folds, cells=cells)


def gpu_compare(prepared, root, pin, cpu, torch, emergency, deadline, trainer=models.fit):
    cells, fits, retained, diagnostics = [], [], [], []
    for number, (fold, index, _, _) in enumerate(prepared):
        selected, forecasts, normalized, reloaded = {}, {}, [], []
        for architecture, seed in MEMBERS:
            predicted, state, facts = trainer(torch, fold, architecture, seed, deadline)
            predicted = np.asarray(predicted)
            require(
                predicted.shape == (len(fold.evaluation),) and np.isfinite(predicted).all(),
                "gpu_forecast",
            )
            name = f"{architecture}_{seed}"
            forecasts[name] = to_bps(fold, predicted)
            normalized.append(predicted.astype(np.float64))
            ref, again = retain_model(root, fold, architecture, seed, state, predicted, pin, torch)
            retained.append(ref)
            reloaded.append(np.asarray(again, dtype=np.float64))
            fits.append(dict(symbol=fold.symbol, fold=fold.fold, policy=name, **facts))
        blend = np.mean(normalized, axis=0)
        replay_blend = np.mean(reloaded, axis=0)
        forecasts["uniform_four"] = to_bps(fold, blend)
        require(
            np.allclose(blend, replay_blend, rtol=1e-5, atol=1e-6)
            and np.array_equal(forecasts["uniform_four"] > 6, to_bps(fold, replay_blend) > 6),
            "ensemble_reload",
        )
        for name, values in forecasts.items():
            selected[name] = values > 6
            selected[name].setflags(write=False)
        observed, support = sessions.outcomes(index, fold.evaluation, HORIZON)
        require(support == cpu["folds"][number]["outcome_support"], "cpu_gpu_support")
        require(all(cpu["folds"][number][k] == v for k, v in fold.facts.items()), "cpu_gpu_cohort")
        scored, metrics = score(fold, selected, forecasts, observed, emergency, deadline)
        cells.extend(scored)
        diagnostics.append(dict(symbol=fold.symbol, fold=fold.fold, mse_bps2=metrics))
    return dict(cells=cells, fits=fits, models=retained, diagnostics=diagnostics)


def configure_cuda():
    torch, runtime = h30.configure_cuda()
    free, total = torch.cuda.mem_get_info()
    usable = min(int(total * 0.9), free - 1024**3)
    require(usable > 0, "cuda_memory_unavailable")
    torch.cuda.set_per_process_memory_fraction(usable / total, 0)
    runtime.update(memory_budget_bytes=usable, inherited_four_gib_cap=False)
    return torch, runtime


def failure(contract, pin, reason):
    require(reason in base.artifacts.FAILURES, "failure_reason")
    return dict(
        **header(contract, pin),
        status="failed",
        criterion=reason,
        cells=[],
        folds=[],
        fits=[],
        models=[],
        diagnostics=[],
        runtime={},
    )


def validate_result(result, contract, pin):
    if result.get("status") == "failed":
        require(result == failure(contract, pin, result["criterion"]), "failure_shape")
        return
    base._keys(
        result,
        "name contract_sha256 config_sha256 evidence_grade status criterion "
        "cells folds fits models diagnostics runtime",
        nested=("cells", "folds", "fits", "models", "diagnostics", "runtime"),
    )
    require(
        all(result[k] == v for k, v in header(contract, pin).items())
        and result["status"] == "complete"
        and result["criterion"] == "descriptive_no_selection",
        "result_identity",
    )
    require(
        len(result["folds"]) == 4
        and len(result["fits"]) == len(result["models"]) == 16
        and len(result["diagnostics"]) == 4,
        "result_matrix",
    )
    require(
        [(f["symbol"], f["fold"]) for f in result["folds"]]
        == [(s, n) for s in h30.SYMBOLS for n in (1, 2)],
        "fold_matrix",
    )
    expected_fits = [
        (s, n, f"{a}_{seed}") for s in h30.SYMBOLS for n in (1, 2) for a, seed in MEMBERS
    ]
    require(
        [(f["symbol"], f["fold"], f["policy"]) for f in result["fits"]] == expected_fits,
        "fit_matrix",
    )
    require(
        [(m["symbol"], m["fold"], f"{m['architecture']}_{m['seed']}") for m in result["models"]]
        == expected_fits,
        "model_matrix",
    )
    support = {}
    for fold in result["folds"]:
        base._keys(
            fold,
            "symbol fold horizon_minutes training_inputs training_outcomes "
            "evaluation_inputs evaluation_outcomes train_rows train_blocks_36 eval_blocks_36 "
            "eval_calendar_sessions strict_train_eval_separation normalizer_sha256 "
            "cohort_sha256 outcome_support mse_bps2",
            nested=(
                "training_inputs",
                "training_outcomes",
                "evaluation_inputs",
                "outcome_support",
                "mse_bps2",
            ),
        )
        for name in ("training_inputs", "evaluation_inputs"):
            counts = fold[name]
            base._keys(counts, "scheduled eligible past_missing past_incomplete")
            require(
                all(type(v) is int and v >= 0 for v in counts.values())
                and counts["scheduled"]
                == sum(counts[k] for k in ("eligible", "past_missing", "past_incomplete")),
                "input_counts",
            )
        for name in ("training_outcomes", "outcome_support"):
            counts = fold[name]
            base._keys(counts, "eligible observed future_missing")
            require(
                all(type(v) is int and v >= 0 for v in counts.values())
                and counts["eligible"] == counts["observed"] + counts["future_missing"],
                "outcome_counts",
            )
        require(
            fold["horizon_minutes"] == 180
            and fold["evaluation_outcomes"] is None
            and fold["strict_train_eval_separation"] is True
            and fold["train_rows"] == fold["training_outcomes"]["observed"] >= 128
            and fold["train_blocks_36"] >= 16
            and fold["eval_blocks_36"] >= 8
            and fold["outcome_support"]["eligible"] == fold["evaluation_inputs"]["eligible"]
            and 32 <= fold["outcome_support"]["observed"] <= fold["eval_calendar_sessions"],
            "fold_support",
        )
        base._keys(fold["mse_bps2"], "ridge train_mean")
        require(all(type(v) is float and v >= 0 for v in fold["mse_bps2"].values()), "metrics")
        support[fold["symbol"], fold["fold"]] = fold
    for number, diag in enumerate(result["diagnostics"]):
        base._keys(diag, "symbol fold mse_bps2", nested=("mse_bps2",))
        require(
            (diag["symbol"], diag["fold"])
            == (result["folds"][number]["symbol"], result["folds"][number]["fold"]),
            "metrics_fold",
        )
        base._keys(diag["mse_bps2"], " ".join(GPU))
        require(all(type(v) is float and v >= 0 for v in diag["mse_bps2"].values()), "metrics")
    require(
        [(c["symbol"], c["fold"], c["cost"], c["policy"]) for c in result["cells"]]
        == [
            (s, f, c, p)
            for phase in (CPU, GPU)
            for s in h30.SYMBOLS
            for f in (1, 2)
            for c in COSTS
            for p in phase
        ],
        "cell_matrix",
    )
    paths = {}
    for c in result["cells"]:
        base._keys(
            c,
            "symbol fold policy cost selected censored roundtrips wins gross fees net "
            "turnover exposure_minutes decision_sha256 local_paper",
        )
        money = {k: Decimal(c[k]) for k in ("gross", "fees", "net", "turnover")}
        require(
            all(v.is_finite() for v in money.values())
            and money["fees"] >= 0
            and money["turnover"] >= 0
            and money["net"] == money["gross"] - money["fees"],
            "accounting",
        )
        require(
            all(type(c[k]) is int for k in ("selected", "censored", "roundtrips", "wins"))
            and 0 <= c["wins"] <= c["roundtrips"] == c["selected"] - c["censored"]
            and c["censored"] >= 0
            and c["exposure_minutes"] == 180 * c["roundtrips"]
            and c["local_paper"] is True,
            "counts",
        )
        key = c["symbol"], c["fold"], c["policy"]
        counts = support[key[:2]]["outcome_support"]
        require(
            c["selected"] <= counts["eligible"]
            and c["roundtrips"] <= counts["observed"]
            and c["censored"] <= counts["future_missing"],
            "cell_support",
        )
        require(
            abs(money["fees"] - money["turnover"] * c["cost"] / 10000)
            <= Decimal("0.0001") * c["roundtrips"],
            "fee_bounds",
        )
        if c["policy"] == "cash":
            require(c["selected"] == 0 and all(v == 0 for v in money.values()), "cash_control")
        if c["policy"] == "always_long":
            require(
                c["selected"] == counts["eligible"] and c["roundtrips"] == counts["observed"],
                "long_control",
            )
        identity = tuple(
            c[k]
            for k in (
                "selected",
                "censored",
                "roundtrips",
                "gross",
                "turnover",
                "exposure_minutes",
                "decision_sha256",
            )
        )
        require(paths.setdefault(key, identity) == identity, "cost_changes_path")
    for fit in result["fits"]:
        base._keys(
            fit,
            "symbol fold policy epochs updates train_rows initial_train_mse "
            "final_train_mse train_mean_baseline_mse parameter_count peak_cuda_memory_bytes",
        )
        require(
            fit["epochs"] == 32
            and fit["updates"] == 32 * ((fit["train_rows"] + 127) // 128)
            and fit["train_rows"] == support[fit["symbol"], fit["fold"]]["train_rows"]
            and all(
                type(fit[k]) is float and fit[k] >= 0
                for k in ("initial_train_mse", "final_train_mse", "train_mean_baseline_mse")
            )
            and type(fit["parameter_count"]) is int
            and fit["parameter_count"] > 0
            and type(fit["peak_cuda_memory_bytes"]) is int
            and fit["peak_cuda_memory_bytes"] >= 0,
            "training_budget",
        )
    for model in result["models"]:
        base._keys(
            model,
            "file sha256 symbol fold architecture seed name contract_sha256 "
            "weights_file weights_sha256 normalizer_sha256 cohort_sha256 horizon_minutes "
            "epochs numeric_only reload_parity",
        )
        name = f"{model['symbol']}-{model['fold']}-{model['architecture']}-{model['seed']}"
        fold = support[model["symbol"], model["fold"]]
        require(
            model["file"] == name + ".json"
            and model["weights_file"] == name + ".npz"
            and model["name"] == NAME
            and model["contract_sha256"] == pin
            and model["horizon_minutes"] == 180
            and model["epochs"] == 32
            and model["normalizer_sha256"] == fold["normalizer_sha256"]
            and model["cohort_sha256"] == fold["cohort_sha256"]
            and model["numeric_only"] is model["reload_parity"] is True,
            "model_binding",
        )
    base._keys(
        result["runtime"],
        "torch cuda cudnn device cross_runtime_bitwise_claim "
        "cublas_workspace_config memory_budget_bytes inherited_four_gib_cap",
    )
    require(
        result["runtime"]["inherited_four_gib_cap"] is False
        and result["runtime"]["cross_runtime_bitwise_claim"] is False
        and type(result["runtime"]["memory_budget_bytes"]) is int
        and result["runtime"]["memory_budget_bytes"] > 0,
        "runtime",
    )


def verify_models(output, result, pin):
    for ref in result["models"]:
        raw = _read(output / "models" / ref["file"])
        require(digest(raw) == ref["sha256"], "model_config_hash")
        cfg = json.loads(raw)
        require(
            cfg == {k: v for k, v in ref.items() if k not in ("file", "sha256")}
            and cfg["contract_sha256"] == pin,
            "model_config_binding",
        )
        require(
            digest(_read(output / "models" / ref["weights_file"])) == ref["weights_sha256"],
            "model_weights_hash",
        )


def run_worker(artifact_root, market_data_root, pin, path, deadline):
    output, contract = verify(artifact_root, market_data_root, pin)
    require(
        path == output / "worker-result.json"
        and not path.exists()
        and not path.is_symlink()
        and not (output / "summary.json").exists(),
        "worker_path",
    )
    require(json.loads(_read(output / "started.json")) == {"contract_sha256": pin}, "attempt")
    try:
        streams = h30.load_streams(
            market_data_root, _read(Path(artifact_root) / h30.RECEIPT), deadline
        )
        prepared = prepare(streams)
        emergency = h30.EmergencyStore(output / "emergency.json")
        cpu = cpu_compare(prepared, emergency, deadline)
        atomic_new(output / "cpu-baseline.json", dict(**header(contract, pin), **cpu))
        torch, runtime = configure_cuda()
        gpu = gpu_compare(prepared, output / "models", pin, cpu, torch, emergency, deadline)
        result = dict(
            **header(contract, pin),
            status="complete",
            criterion="descriptive_no_selection",
            cells=cpu["cells"] + gpu.pop("cells"),
            folds=cpu["folds"],
            runtime=runtime,
            **gpu,
        )
        validate_result(result, contract, pin)
        verify_models(output, result, pin)
        verify(artifact_root, market_data_root, pin)
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure")
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None
