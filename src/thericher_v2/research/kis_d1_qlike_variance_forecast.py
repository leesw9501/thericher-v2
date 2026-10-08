"""Final related variance-loss trial; parent owns freeze, dispatch and GPU lease.

No financial NAV, broker, credentials, provider or Paper input. Readback binds
cached original predictions, not fresh inference from saved numeric parameters.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import io
import json
import math
import time
import warnings
from pathlib import Path

import numpy as np

from thericher_v2.research import kis_d1_rolling_variance_forecast as rolling

fixed, base, lifecycle = rolling.fixed, rolling.base, rolling.lifecycle
require, encode, digest = rolling.require, rolling.encode, rolling.digest
NAME = "kis-d1-qlike-variance-forecast-development-v1"
REPO = Path(__file__).resolve().parents[3]
SECONDS, VERIFY_SECONDS, WINDOW, MONTHS, FITS = 300, 120, 504, 33, 132
UPDATES, SEED = fixed.UPDATES, fixed.SEED
CANDIDATES, METHODS, METRICS = ("gamma", "gru"), ("baseline", "gamma", "gru"), fixed.METRICS
RUNTIME = dict(rolling.RUNTIME, sklearn="1.9.1")
CODE = rolling.CODE + ("src/thericher_v2/research/kis_d1_qlike_variance_forecast.py",)
GEOMETRY_RELATIVE, GEOMETRY_PIN = rolling.GEOMETRY_RELATIVE, rolling.GEOMETRY_PIN
PHASES = tuple("fit_gamma" if p == "fit_ols" else p for p in fixed.PHASES)
PROGRESS = tuple(
    f"progress-gamma-{a}-{stage}.json" for a in range(3) for stage in ("start", "complete")
) + (
    "progress-gru-start.json",
    *(f"progress-gru-{n:04d}.json" for n in (128, 256, 384, 512)),
    "progress-gru-complete.json",
)
MONTH_FILES = (
    "scaler.json",
    *(f"gamma-{a}.npz" for a in range(3)),
    "gru.safetensors",
    "predictions.json",
) + PROGRESS
ARTIFACTS = ("started.json", "predictions.json") + tuple(
    f"months/{m:02d}/{name}" for m in range(MONTHS) for name in MONTH_FILES
)
build_plan, prepare_month, PreparationCache = (
    rolling.build_plan,
    rolling.prepare_month,
    rolling.PreparationCache,
)


def configuration():
    config = rolling.configuration()
    config.pop("ols")
    config.update(
        name=NAME,
        runtime=dict(RUNTIME),
        fits=FITS,
        refit="99 fresh single-output Gamma and33 fresh seed101 GRU; no warm starts",
        gamma=dict(
            alpha=0,
            fit_intercept=True,
            solver="lbfgs",
            max_iter=100,
            tol=1e-4,
            warm_start=False,
            verbose=0,
            link="log",
            dtype="float64",
            inputs="same nine standardized HAR columns, all three assets",
            target="exp(bound TRAIN float64 log-target); positive floored proxy",
            rank="intercept+9 TRAIN columns full rank10 before fit; no fallback",
            failure="ConvergenceWarning/nonfinite/nonpositive => technical failure",
        ),
        kill="both metrics BOTH views improvements strictly>1e-10: Gamma vs baseline; "
        "GRU vs baseline AND Gamma; original criterion unchanged",
        fit_accounting="132 starts/completions; each Gamma fit return/GRU512 synchronized "
        "updates recorded before convergence/checks/inference/save/deadline",
        model_format="three own numeric Gamma NPZ per month/own GRU safetensors; no pickle",
        sources=[
            "https://public.econ.duke.edu/~ap172/Patton_vol_proxies_JoE_2011.pdf",
            "https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.GammaRegressor.html",
            "https://scikit-learn.org/stable/modules/linear_model.html",
        ],
        source_scope="Engine independently retrieved2026-10-08 05:17UTC; Patton2011 "
        "IBM1993-2003/proxy-loss mechanism, official sklearn1.9.1 Gamma GLM; "
        "no author code/license adoption or ETF replication claim",
        related_trial_number=3,
        registry_trial_index="record actual index; not forced to3",
        predecessor=dict(
            study=rolling.NAME,
            contract_sha256="sha256:9087641db43afbc01c621b6d1ddf4fd9893e057b536c2f6725d87532a5ce46db",
            result_sha256="sha256:86181a7a1ae9f18a843ba49c79acf5bcc682dd22301bbb69cc6efd24ed67826b",
        ),
        lineage="closed static and rolling log-MSE variance families; related outcome-informed "
        "DEV trial3; original verdicts unchanged; NOT independent replication",
        stop="one132-fit/300s attempt, no clipping/fallback/partial scoring/budget extension; "
        "reject retires this variance-method question pending material new input "
        "or distinct operational hypothesis, not a hold on independent work",
    )
    config["gru"] = dict(
        config["gru"],
        loss="full-batch mean expm1(delta)-delta; "
        "delta=centered TRAIN log-target minus centered log-prediction",
    )
    config["limitations"] = [
        v.replace("incomplete66", "incomplete132") for v in config["limitations"]
    ] + [
        "floored population proxy not proven conditionally unbiased; no Patton ranking guarantee",
        "objective alignment is a hypothesis, not a proven cause of previous rejection",
        "log-MSE and QLIKE target different estimands; original AND kill still applies",
    ]
    return config


def runtime_identity():
    return dict(fixed.runtime_identity(), sklearn=importlib.metadata.version("scikit-learn"))


def _root(root, artifact_root):
    root, artifact_root = Path(root).absolute(), Path(artifact_root).absolute()
    require(root == artifact_root / "research" / NAME and root.is_dir(), "study_root")
    base.reject_repo_artifact_path(root, REPO)
    return root


def read_contract(root, artifact_root, pin):
    root = _root(root, artifact_root)
    contract = base._json(root / "precommit.json", pin)
    require(contract["name"] == NAME and contract["config"] == configuration(), "contract_config")
    require(contract["runtime"] == runtime_identity() == RUNTIME, "runtime_identity")
    require(Path(contract["source_root"]).absolute() == REPO, "frozen_source_root")
    require(set(contract["code_sha256"]) >= set(CODE), "code_pins")
    for relative, expected in contract["code_sha256"].items():
        require(digest(base._read(base._relative(REPO, relative))) == expected, "code_changed")
    commitment = base._json(base._relative(artifact_root, base.INPUT_RELATIVE), base.INPUT_PIN)
    require(
        contract["input_commitment_sha256"] == base.INPUT_PIN
        and commitment["calendar_sha256"] == base.CALENDAR_PIN
        and commitment["kind"] == "kis-cross-asset-d1-price-only-input-v1"
        and commitment["no_date_fill"] is True,
        "input_identity",
    )
    require(
        all(contract["code_sha256"].get(p) == h for p, h in commitment["source_pins"].items()),
        "producer_code_pins",
    )
    plan = build_plan()
    require(plan.record() == contract["plan"], "plan_changed")
    rolling.validate_geometry(
        base._json(base._relative(artifact_root, GEOMETRY_RELATIVE), GEOMETRY_PIN), plan
    )
    return contract, commitment


def _gamma_model():
    from sklearn.linear_model import GammaRegressor

    return GammaRegressor(
        alpha=0,
        fit_intercept=True,
        solver="lbfgs",
        max_iter=100,
        tol=1e-4,
        warm_start=False,
        verbose=0,
    )


def fit_gamma(prepared, asset, *, deadline, progress):
    from sklearn.exceptions import ConvergenceWarning
    from threadpoolctl import threadpool_limits

    require(type(asset) is int and 0 <= asset < 3, "gamma_asset")
    require(time.monotonic() < deadline, "compute_stop")
    train, dev = prepared.train_har, prepared.dev_har
    require(
        train.shape == (WINDOW, 9)
        and dev.shape == (1, 9)
        and np.isfinite(train).all()
        and np.isfinite(dev).all(),
        "feature_shape",
    )
    with np.errstate(over="raise", invalid="raise", under="ignore"):
        target = np.exp(prepared.labels[:, asset])
    require(
        target.shape == (WINDOW,) and np.isfinite(target).all() and (target > 0).all(),
        "target_numeric",
    )
    model, start = _gamma_model(), time.monotonic()
    with threadpool_limits(limits=2):
        require(
            np.linalg.matrix_rank(np.column_stack((np.ones(WINDOW), train))) == 10, "gamma_rank"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(train, target)
            progress()
        require(
            not any(issubclass(w.category, ConvergenceWarning) for w in caught), "gamma_convergence"
        )
        require(
            np.asarray(model.coef_).shape == (9,)
            and np.isfinite(model.coef_).all()
            and np.isfinite(model.intercept_),
            "fit_nonfinite",
        )
        require(time.monotonic() < deadline, "compute_stop")
        prediction = np.asarray(model.predict(dev), dtype="<f8")
    require(
        prediction.shape == (1,) and np.isfinite(prediction).all() and (prediction > 0).all(),
        "forecast_numeric",
    )
    logs = np.log(prediction)
    require(np.isfinite(logs).all(), "forecast_numeric")
    buffer = io.BytesIO()
    np.savez(
        buffer,
        coefficients=np.asarray(model.coef_, dtype="<f8"),
        intercept=np.asarray(model.intercept_, dtype="<f8"),
        iterations=np.asarray(model.n_iter_, dtype="<i8"),
        asset=np.asarray(asset),
    )
    require(time.monotonic() < deadline, "compute_stop")
    return (
        logs.tolist(),
        buffer.getvalue(),
        dict(seconds=time.monotonic() - start, iterations=int(model.n_iter_), rank=10),
    )


def qlike_train_loss(log_prediction, log_target):
    """Center cancels in this residual; no clipping or outcome-dependent floor."""
    import torch

    require(log_prediction.shape == log_target.shape, "feature_shape")
    delta = log_target - log_prediction
    losses = torch.expm1(delta) - delta
    require(bool(torch.isfinite(losses).all().item()), "fit_nonfinite")
    return losses.mean()


def fit_gru(prepared, *, deadline, progress):
    import torch
    from safetensors.torch import save

    require(time.monotonic() < deadline, "compute_stop")
    require(torch.cuda.is_available(), "cuda_unavailable")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.manual_seed(SEED)
    model = fixed.make_gru().to("cuda")
    require(sum(p.numel() for p in model.parameters()) == 3651, "gru_parameters")
    x = torch.from_numpy(np.array(prepared.train_x, copy=True)).to("cuda")
    center = np.asarray(prepared.scaler["target_log_mean"], dtype="<f8")
    y = torch.from_numpy((prepared.labels - center).astype("<f4")).to("cuda")
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    start = time.monotonic()
    model.train()
    for update in range(1, UPDATES + 1):
        require(time.monotonic() < deadline, "compute_stop")
        optimizer.zero_grad(set_to_none=True)
        loss = qlike_train_loss(model(x), y)
        loss.backward()
        require(
            all(
                p.grad is None or bool(torch.isfinite(p.grad).all().item())
                for p in model.parameters()
            ),
            "fit_nonfinite",
        )
        optimizer.step()
        if update % 128 == 0:
            torch.cuda.synchronize()
            progress(update)
    require(all(bool(torch.isfinite(p).all().item()) for p in model.parameters()), "fit_nonfinite")
    require(time.monotonic() < deadline, "compute_stop")
    model.eval()
    with torch.inference_mode():
        dev = torch.from_numpy(np.array(prepared.dev_x, copy=True)).to("cuda")
        prediction = model(dev).cpu().numpy().astype("<f8") + center
    fixed.forecast_variance(prediction, 1)
    torch.cuda.synchronize()
    resources = dict(
        seconds=time.monotonic() - start,
        updates=UPDATES,
        peak_vram_bytes=int(torch.cuda.max_memory_allocated()),
    )
    weights = save({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()})
    require(time.monotonic() < deadline, "compute_stop")
    return prediction.tolist(), weights, resources


def _artifacts(root):
    return {name: digest(base._read(root / name)) for name in ARTIFACTS if (root / name).exists()}


def _progress_specs(month, pin):
    offset, specs = month * 4, {}
    for asset in range(3):
        for stage in ("start", "complete"):
            specs[f"progress-gamma-{asset}-{stage}.json"] = dict(
                completed_fits=offset + asset + (stage == "complete"),
                fit_starts=offset + asset + 1,
                updates=0,
                **(
                    {
                        "training_completion": (
                            "GammaRegressor.fit returned; convergence not yet checked"
                        )
                    }
                    if stage == "complete"
                    else {}
                ),
            )
    specs["progress-gru-start.json"] = dict(
        completed_fits=offset + 3, fit_starts=offset + 4, updates=0
    )
    for update in (128, 256, 384, 512):
        specs[f"progress-gru-{update:04d}.json"] = dict(
            completed_fits=offset + 3 + (update == UPDATES), fit_starts=offset + 4, updates=update
        )
    specs["progress-gru-complete.json"] = dict(
        completed_fits=offset + 4,
        fit_starts=offset + 4,
        updates=UPDATES,
        training_completion="512 synchronized optimizer steps; recipe not yet validated",
    )
    return {
        f"months/{month:02d}/{name}": dict(contract_sha256=pin, month=month, **record)
        for name, record in specs.items()
    }


def _verify_progress(root, result, pin):
    completed = starts = 0
    stopped = False
    for month in range(MONTHS):
        specs = _progress_specs(month, pin)
        names = list(specs)
        present = [n for n in names if n in result["artifact_sha256"]]
        require(
            present == names[: len(present)] and (not stopped or not present), "progress_binding"
        )
        for name in present:
            record = specs[name]
            require(base._json(root / name, canonical=True) == record, "progress_binding")
            completed, starts = record["completed_fits"], record["fit_starts"]
        stopped |= len(present) != len(names)
    require(
        completed == result["actual_fits"] and starts == result["fit_starts"], "progress_binding"
    )


def _month_prediction(root, plan, month, prepared, pin, gamma, gru):
    for values in (gamma, gru):
        fixed.forecast_variance(values, 1)
    return dict(
        contract_sha256=pin,
        input_sha256=base.INPUT_PIN,
        window=plan.window_record(month),
        scaler_sha256=digest(encode(prepared.scaler)),
        model_sha256={
            n: digest(base._read(root / n))
            for n in (*(f"gamma-{a}.npz" for a in range(3)), "gru.safetensors")
        },
        log_forecasts=dict(gamma=gamma, gru=gru),
        baseline=prepared.baseline.tolist(),
        inference_kind="original_worker",
    )


def assemble_predictions(plan, parts, pin):
    # Reuse the fixed seal geometry; OLS here is only the predecessor's schema key.
    converted = [
        dict(p, log_forecasts=dict(ols=p["log_forecasts"]["gamma"], gru=p["log_forecasts"]["gru"]))
        for p in parts
    ]
    require(all(set(p["log_forecasts"]) == set(CANDIDATES) for p in parts), "prediction_binding")
    result = rolling.assemble_predictions(plan, converted, pin)
    result["month_prediction_sha256"] = [digest(encode(p)) for p in parts]
    result["log_forecasts"]["gamma"] = result["log_forecasts"].pop("ols")
    return result


def evaluate(targets, predictions, plan, *, completed_fits):
    require(type(completed_fits) is int and completed_fits == FITS, "incomplete_fits")
    require(len(predictions["month_prediction_sha256"]) == MONTHS, "incomplete_months")
    require(set(predictions["log_forecasts"]) == set(CANDIDATES), "prediction_binding")
    converted = dict(
        predictions,
        log_forecasts=dict(
            ols=predictions["log_forecasts"]["gamma"], gru=predictions["log_forecasts"]["gru"]
        ),
    )
    return [
        dict(c, method="gamma" if c["method"] == "ols" else c["method"])
        for c in fixed.evaluate(targets, converted, plan)
    ]


def criterion(cells):
    require(
        len(cells) == 6
        and {(c["block"], c["method"]) for c in cells} == {(b, m) for b in (0, 1) for m in METHODS},
        "cell_matrix",
    )
    verdict = fixed.criterion(
        [dict(c, method="ols" if c["method"] == "gamma" else c["method"]) for c in cells]
    )
    return dict(gamma=verdict["ols"], gru=verdict["gru"])


def _failure(error):
    if isinstance(error, base.StudyFault) and str(error) in {
        "gamma_rank",
        "gamma_convergence",
        "gamma_asset",
        "gru_parameters",
    }:
        return str(error), "failed"
    return rolling._failure(error)


def run(root, market_root, artifact_root, pin):
    start = time.monotonic()
    deadline = start + SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    require(not _artifacts(root) and not (root / "worker-result.json").exists(), "attempt_exists")
    base.atomic_new(root / "started.json", dict(contract_sha256=pin, input_sha256=base.INPUT_PIN))
    result = dict(
        status="failed",
        reason="worker_failed",
        phase="source_input",
        actual_fits=0,
        fit_starts=0,
        contract_sha256=pin,
        elapsed_seconds=0,
        criterion={},
        cells=[],
        artifact_sha256={},
        resources={},
    )
    try:
        source = base.load_committed_source(
            commitment, artifact_root, market_root, deadline=deadline
        )
        plan = build_plan(source.plan.sessions)
        require(plan.record() == contract["plan"], "plan_changed")
        cache, parts = PreparationCache(source, plan), []
        for month in range(MONTHS):
            result["phase"] = "prepare"
            prepared = cache.prepare(month, deadline=deadline)
            local = root / "months" / f"{month:02d}"
            local.mkdir(parents=True, exist_ok=False)
            base.atomic_new(local / "scaler.json", prepared.scaler)
            specs = _progress_specs(month, pin)

            def progress(name, *, month=month, specs=specs):
                path = f"months/{month:02d}/{name}"
                record = specs[path]
                result["actual_fits"], result["fit_starts"] = (
                    record["completed_fits"],
                    record["fit_starts"],
                )
                base.atomic_new(root / path, record)

            gamma = []
            for asset in range(3):
                result["phase"] = "fit_gamma"
                progress(f"progress-gamma-{asset}-start.json")
                logs, weights, resources = fit_gamma(
                    prepared,
                    asset,
                    deadline=deadline,
                    progress=lambda asset=asset: progress(f"progress-gamma-{asset}-complete.json"),
                )
                gamma.append(logs[0])
                lifecycle.atomic_bytes(local / f"gamma-{asset}.npz", weights)
                result["resources"][f"{month:02d}-gamma-{asset}"] = resources

            def gru_progress(update):
                require(update in (128, 256, 384, 512), "progress_update")
                progress(f"progress-gru-{update:04d}.json")
                if update == UPDATES:
                    progress("progress-gru-complete.json")

            result["phase"] = "fit_gru"
            progress("progress-gru-start.json")
            gru, weights, resources = fit_gru(prepared, deadline=deadline, progress=gru_progress)
            lifecycle.atomic_bytes(local / "gru.safetensors", weights)
            result["resources"][f"{month:02d}-gru"] = resources
            result["phase"] = "prediction_seal"
            part = _month_prediction(local, plan, month, prepared, pin, [gamma], gru)
            base.atomic_new(local / "predictions.json", part)
            parts.append(part)
            require(time.monotonic() < deadline, "compute_stop")
        predictions = assemble_predictions(plan, parts, pin)
        base.atomic_new(root / "predictions.json", predictions)
        result["phase"] = "forward_input"
        targets = fixed.load_dev_targets(source, plan, deadline=deadline)
        result["phase"] = "evaluate"
        cells = evaluate(targets, predictions, plan, completed_fits=result["actual_fits"])
        result["phase"] = "validate"
        require(
            base.load_committed_source(
                commitment, artifact_root, market_root, deadline=deadline
            ).files
            == source.files,
            "source_changed",
        )
        require(time.monotonic() < deadline, "compute_stop")
        result.update(status="complete", reason=None, cells=cells, criterion=criterion(cells))
    except Exception as error:
        reason, status = _failure(error)
        result.update(reason=reason, status=status)
    result.update(elapsed_seconds=time.monotonic() - start, artifact_sha256=_artifacts(root))
    base.atomic_new(root / "worker-result.json", result)
    return fixed._safe(result)


def verify(root, market_root, artifact_root, pin, result_pin):
    deadline = time.monotonic() + VERIFY_SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    result = base._json(root / "worker-result.json", result_pin, canonical=True)
    require(
        set(result)
        == {
            "status",
            "reason",
            "phase",
            "actual_fits",
            "fit_starts",
            "contract_sha256",
            "elapsed_seconds",
            "criterion",
            "cells",
            "artifact_sha256",
            "resources",
        }
        and result["contract_sha256"] == pin
        and result["phase"] in PHASES
        and type(result["actual_fits"]) is int
        and type(result["fit_starts"]) is int
        and 0 <= result["actual_fits"] <= result["fit_starts"] <= FITS
        and type(result["elapsed_seconds"]) in (int, float)
        and math.isfinite(result["elapsed_seconds"])
        and result["elapsed_seconds"] >= 0,
        "result_binding",
    )
    require(result["artifact_sha256"] == _artifacts(root), "artifact_binding")
    require(
        base._json(root / "started.json", canonical=True)
        == dict(contract_sha256=pin, input_sha256=base.INPUT_PIN),
        "start_binding",
    )
    _verify_progress(root, result, pin)
    if result["status"] in {"failed", "input_unavailable"}:
        require(
            type(result["reason"]) is str and result["cells"] == [] and result["criterion"] == {},
            "failure_binding",
        )
        return fixed._safe(result) | dict(
            replay="failure_binding_only", fits=0, inference=0, searches=0, writes=0
        )
    require(
        result["status"] == "complete"
        and result["reason"] is None
        and result["phase"] == "validate"
        and result["actual_fits"] == result["fit_starts"] == FITS
        and set(result["artifact_sha256"]) == set(ARTIFACTS),
        "complete_binding",
    )
    source = base.load_committed_source(commitment, artifact_root, market_root, deadline=deadline)
    plan = build_plan(source.plan.sessions)
    require(plan.record() == contract["plan"], "plan_changed")
    cache, parts = PreparationCache(source, plan), []
    for month in range(MONTHS):
        prepared = cache.prepare(month, deadline=deadline)
        local = root / "months" / f"{month:02d}"
        require(
            base._json(local / "scaler.json", canonical=True) == prepared.scaler, "scaler_replay"
        )
        part = base._json(local / "predictions.json", canonical=True)
        expected = _month_prediction(
            local,
            plan,
            month,
            prepared,
            pin,
            part["log_forecasts"]["gamma"],
            part["log_forecasts"]["gru"],
        )
        require(part == expected, "prediction_binding")
        parts.append(part)
    predictions = assemble_predictions(plan, parts, pin)
    require(
        base._json(root / "predictions.json", canonical=True) == predictions, "prediction_binding"
    )
    cells = evaluate(
        fixed.load_dev_targets(source, plan, deadline=deadline),
        predictions,
        plan,
        completed_fits=result["actual_fits"],
    )
    require(
        encode(cells) == encode(result["cells"]) and criterion(cells) == result["criterion"],
        "numeric_replay",
    )
    require(
        base.load_committed_source(commitment, artifact_root, market_root, deadline=deadline).files
        == source.files,
        "source_changed",
    )
    require(time.monotonic() < deadline, "compute_stop")
    return fixed._safe(result) | dict(
        replay="exact_metrics/cached_prediction_binding", fits=0, inference=0, searches=0, writes=0
    )


def synthetic_smoke():
    import torch

    plan = build_plan(rolling._synthetic_sessions())
    raw = np.random.default_rng(SEED).normal(0, 0.01, (WINDOW + 1, 3, 63))
    prepared = fixed.prepare_arrays(raw, np.full((WINDOW, 3), 0.0001), plan.month(0))
    require(
        np.linalg.matrix_rank(np.column_stack((np.ones(WINDOW), prepared.train_har))) == 10,
        "gamma_rank",
    )
    _gamma_model()  # Exercise optional constructor, never fit or predict.
    threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        with torch.random.fork_rng(devices=[]):
            torch.default_generator.manual_seed(SEED)
            model = fixed.make_gru()
            require(sum(p.numel() for p in model.parameters()) == 3651, "gru_parameters")
            x = torch.from_numpy(np.array(prepared.train_x, copy=True))
            center = np.asarray(prepared.scaler["target_log_mean"])
            y = torch.from_numpy((prepared.labels - center).astype("<f4"))
            elapsed = []
            for _ in range(3):
                model.zero_grad(set_to_none=True)
                start = time.monotonic()
                qlike_train_loss(model(x), y).backward()
                require(
                    all(
                        p.grad is None or bool(torch.isfinite(p.grad).all().item())
                        for p in model.parameters()
                    ),
                    "fit_nonfinite",
                )
                elapsed.append(time.monotonic() - start)
    finally:
        torch.set_num_threads(threads)
    parts = [
        dict(
            contract_sha256="synthetic",
            input_sha256=base.INPUT_PIN,
            window=plan.window_record(m),
            log_forecasts=dict(gamma=[[math.log(0.0001)] * 3], gru=[[math.log(0.0001)] * 3]),
            baseline=[[0.0001] * 3],
            inference_kind="original_worker",
        )
        for m in range(MONTHS)
    ]
    cells = evaluate(
        np.full((MONTHS, 3), 0.0001),
        assemble_predictions(plan, parts, "synthetic"),
        plan,
        completed_fits=FITS,
    )
    require(set(criterion(cells).values()) == {"rejected"}, "smoke_matrix")
    return dict(
        status="smoke_passed",
        cells=6,
        planned_fits=FITS,
        actual_fits=0,
        fit_starts=0,
        actual_market_reads=0,
        optimizer_steps=0,
        gpu=False,
        cpu_gru_parameters=3651,
        synthetic_cpu_forward_backward_seconds=elapsed,
        timing_scope="three source-free CPU kernels, not132-fit budget assurance",
        paper_input=False,
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("smoke", "run", "verify"))
    for name in ("root", "market-root", "artifact-root"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    args = parser.parse_args(argv)
    bound = args.phase != "smoke"
    if any(
        bool(v) != bound
        for v in (args.root, args.market_root, args.artifact_root, args.contract_sha256)
    ) or bool(args.result_sha256) != (args.phase == "verify"):
        parser.error("run/verify require roots+contract pin; verify result pin; smoke none")
    try:
        result = (
            synthetic_smoke()
            if not bound
            else run(args.root, args.market_root, args.artifact_root, args.contract_sha256)
            if args.phase == "run"
            else verify(
                args.root,
                args.market_root,
                args.artifact_root,
                args.contract_sha256,
                args.result_sha256,
            )
        )
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if result["status"] in {"complete", "smoke_passed"} else 2
    except Exception:
        print(json.dumps(dict(status="failed", reason="study_unavailable")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
