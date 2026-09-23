"""Fixed-weight, CPU-only forecast diagnostics on seen H30 development folds."""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_position_policy as position
from thericher_v2.research.forecast_diagnostics import summarize_forecast

family, sessions, h30 = position.family, position.sessions, position.h30
require = sessions.require
NAME = "fixed-forecast-diagnostic-h30-c36-v1"
REPO, SECONDS = h30.REPO, 600
FAMILY_CONTRACT = "sha256:9625f31d0fc0d879a106cc0fad3d058752658728c6a310d0684b9610c749cb0a"
SUMMARIES = {
    "cpu": "sha256:c514f0a4a2da5a9a4c5e3a5d66279de7f43971e53af22bfb819347ffbc686b41",
    "cuda": "sha256:db1cfc4d127449615c824cc4550e3d4bd103c456830e0056c91b2eb7006ab813",
}
CANDIDATES = (("lstm", 101), ("lstm", 103), ("lightgbm", 101)) + tuple(
    (name, seed) for name in family.models.ARCHITECTURES for seed in h30.SEEDS
)
CODE = (
    "src/thericher_v2/research/forecast_diagnostics.py",
    "src/thericher_v2/research/firstrate_forecast_diagnostic.py",
    "scripts/run_firstrate_forecast_diagnostic.py",
    *position.CODE,
)
FLAGS = ("training", "gpu", "selection", "promotion", "holdout_access")
FOLD_COUNTS = (
    "train_rows",
    "train_blocks_36",
    "eval_blocks_36",
    "scored_blocks_36",
    "eval_calendar_sessions",
)
FOLD_KEYS = (
    "symbol",
    "fold",
    "horizon_minutes",
    "cohort_sha256",
    "normalizer_sha256",
    *FOLD_COUNTS,
)


def lineage(root):
    parent, receipt, prior, lstms = position.lineage(root)
    directory, _, _ = family.verify(root, FAMILY_CONTRACT)
    results = {}
    for phase, pin in SUMMARIES.items():
        raw = (directory / f"{phase}-summary.json").read_bytes()
        require(h30.digest(raw) == pin, "lineage_changed")
        results[phase] = json.loads(raw)
        family.validate_result(results[phase], phase, FAMILY_CONTRACT)
        for ref in results[phase]["models"]:
            model_root = directory / f"{phase}-models"
            for field in ("config", "weights", "scalers"):
                require(
                    h30.digest(h30.within(model_root, ref[field + "_file"]).read_bytes())
                    == ref[field + "_sha256"],
                    "model_reload",
                )
    return parent, receipt, prior, directory, results, lstms


def contract(root):
    _, receipt, _, _, results, lstms = lineage(root)
    return dict(
        name=NAME,
        family=h30.FAMILY,
        parent_contract_sha256=FAMILY_CONTRACT,
        parent_summaries=SUMMARIES,
        parent_models=lstms + [r for p in results.values() for r in p["models"]],
        cohort=sessions.contract(receipt),
        code_sha256={p: h30.digest((REPO / p).read_bytes()) for p in CODE},
        candidates=CANDIDATES,
        horizon_minutes=30,
        context=36,
        target="rounded open(d+30)/open(d) return bps; predictions precede outcome censoring",
        primary="prediction dispersion, fixed bins [-inf,-6),[-6,0),[0,6],(6,inf), counts",
        secondary="MSE vs zero/TRAIN mean; Pearson/tied Spearman; descriptive OLS; no inference",
        session_metrics="equal-session mean Pearson with defined-session count, no p-values",
        parity="all28 retained models; all84 parent model/cost cells and four folds identical",
        censoring="same post-decision outcome mask for all models; no missing return as zero",
        minimums="32 scored rows and8 nonoverlapping history blocks per fold",
        review="supported-with-limits; counts/dispersion primary; no skill/selection from slopes",
        evidence_grade=position.GRADE,
        cpu_seconds=SECONDS,
        strongest_kill_test="source/model/cohort/scaler/decision parity mismatch or partial result",
        limitations=[
            "seen_data",
            "repeated_descriptive_reads",
            "source_timing_unverified",
            "corporate_actions_finality_unverified",
            "no_KIS_parity",
            "no_generalization",
        ],
        **dict.fromkeys(FLAGS, False),
    )


def freeze(root):
    root = h30.ensure_external_artifact_directory(root, REPO)
    payload = contract(root)
    raw = h30.encode(payload)
    output = h30.run_directory(root, NAME)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "contract.json").open("xb") as handle:
        handle.write(raw)
    h30.register_frozen_campaign(
        contract_hash=h30.digest(raw),
        dataset_hash=h30.digest(h30.encode(payload["cohort"]["source_pins"])),
        split_hash=h30.digest(h30.encode([FAMILY_CONTRACT, "H30-context36"])),
        cost_model_hash=h30.digest(h30.encode([h30.COSTS, "fixed_forecast_diagnostic"])),
        trial_family=h30.FAMILY,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )
    return h30.digest(raw)


def verify(root, scope_hash):
    output = h30.run_directory(root, NAME)
    raw = (output / "contract.json").read_bytes()
    require(h30.digest(raw) == scope_hash and raw == h30.encode(contract(root)), "contract_changed")
    return output


def forecasts(fold, torch, parent, prior, directory, results):
    frozen = []
    for name, seed in CANDIDATES:
        ident = dict(
            zip(family.IDENTITY, (fold.symbol, fold.fold, 30, name, 36, seed), strict=True)
        )
        if name == "lstm":
            values = family.parent_prediction(torch, fold, seed, parent, prior)
        else:
            phase = "cpu" if name == "lightgbm" else "cuda"
            ref = next(
                r for r in results[phase]["models"] if all(r[k] == v for k, v in ident.items())
            )
            root = directory / f"{phase}-models"
            model, arrays = family.load_model(root, ref, FAMILY_CONTRACT, torch)
            family.check_scalers(arrays, fold)
            cfg = json.loads(h30.within(root, ref["config_file"]).read_bytes())
            require(cfg["cohort_sha256"] == fold.facts["cohort_sha256"], "parent_control_mismatch")
            values = (
                model.predict(fold.eval_x.reshape(len(fold.eval_x), -1), num_threads=1)
                if name == "lightgbm"
                else family.sequence_predict(torch, model, fold.eval_x)
            )
        values = np.asarray(values, dtype=float) * fold.y_scale + fold.y_mean
        require(values.shape == (len(fold.evaluation),) and np.isfinite(values).all(), "prediction")
        values.setflags(write=False)
        frozen.append((ident, values))
    return frozen


def compare(streams, torch, parent, prior, directory, results, emergency, deadline, scope_hash):
    result = {**failure(scope_hash, None), "status": "complete"}
    result.pop("reason")
    expected = {sessions.cell_key(c): c for p in results.values() for c in p["cells"]}
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        schedule = sessions.regular_sessions(bars)
        for number, plan in enumerate(sessions.plans(schedule, 30), 1):
            h30.check_time(deadline)
            fold = sessions.prepare_fold(symbol, number, index, plan, 30)
            predicted = forecasts(fold, torch, parent, prior, directory, results)
            selected = [(ident, values > 6) for ident, values in predicted]
            # Outcomes cannot influence the already-computed predictions or decisions.
            parity = family.score(fold, selected, index, emergency, deadline)
            require(
                all(c == expected.get(sessions.cell_key(c)) for c in parity),
                "parent_control_mismatch",
            )
            parent_fold = next(
                f for f in results["cpu"]["folds"] if (f["symbol"], f["fold"]) == (symbol, number)
            )
            require(fold.facts == parent_fold, "parent_control_mismatch")
            result["parent_controls_reproduced"] += len(parity)
            observed, _ = sessions.outcomes(index, fold.evaluation, 30)
            keep = np.array([out is not None for out in observed])
            targets = np.array([out.target_bps for out in observed if out is not None])
            keys = [
                k.isoformat()
                for k, use in zip(
                    position.session_keys(fold.evaluation, schedule), keep, strict=True
                )
                if use
            ]
            result["folds"].append(
                {
                    **{k: fold.facts[k] for k in FOLD_KEYS},
                    "evaluation_inputs": {"eligible": fold.facts["evaluation_inputs"]["eligible"]},
                    "evaluation_outcomes": {
                        k: fold.facts["evaluation_outcomes"][k]
                        for k in ("eligible", "observed", "future_missing")
                    },
                }
            )
            for ident, values in predicted:
                result["cells"].append(
                    dict(
                        **ident,
                        eligible_decisions=len(values),
                        future_censored=int((~keep).sum()),
                        selected_censored=int(((values > 6) & ~keep).sum()),
                        metrics=summarize_forecast(
                            values[keep], targets, keys, train_mean_bps=fold.y_mean
                        ),
                    )
                )
    validate_result(result, scope_hash)
    return result


def failure(scope_hash, reason):
    return dict(
        name=NAME,
        contract_sha256=scope_hash,
        status="failed_all_cells",
        reason=reason,
        cells=[],
        folds=[],
        parent_controls_reproduced=0,
        evidence_grade=position.GRADE,
        **dict.fromkeys(FLAGS, False),
    )


def validate_result(result, scope_hash):
    require(set(result) == set(failure(scope_hash, None)) - {"reason"}, "result_fields")
    require(
        result["name"] == NAME
        and result["contract_sha256"] == scope_hash
        and result["status"] == "complete"
        and result["evidence_grade"] == position.GRADE
        and all(result[k] is False for k in FLAGS),
        "result_identity",
    )
    wanted = [
        (s, f, 30, n, 36, seed) for s in h30.SYMBOLS for f in (1, 2) for n, seed in CANDIDATES
    ]
    require(
        [tuple(c[k] for k in family.IDENTITY) for c in result["cells"]] == wanted
        and result["parent_controls_reproduced"] == 84,
        "cell_matrix",
    )
    require(
        [(f["symbol"], f["fold"], f["horizon_minutes"]) for f in result["folds"]]
        == [(s, f, 30) for s in h30.SYMBOLS for f in (1, 2)],
        "fold_matrix",
    )
    template = summarize_forecast([0.0], [0.0], ["synthetic"], train_mean_bps=0.0)
    folds = {(f["symbol"], f["fold"]): f for f in result["folds"]}
    for fold in result["folds"]:
        require(
            set(fold) == set(FOLD_KEYS) | {"evaluation_inputs", "evaluation_outcomes"}
            and set(fold["evaluation_inputs"]) == {"eligible"}
            and set(fold["evaluation_outcomes"]) == {"eligible", "observed", "future_missing"},
            "fold_fields",
        )
        require(
            all(
                type(v) is int and v >= 0
                for v in (
                    *(fold[k] for k in FOLD_COUNTS),
                    *fold["evaluation_inputs"].values(),
                    *fold["evaluation_outcomes"].values(),
                )
            )
            and fold["train_rows"] >= 128
            and fold["scored_blocks_36"] >= 8,
            "fold_support",
        )
        for key in ("cohort_sha256", "normalizer_sha256"):
            value = fold[key]
            require(
                isinstance(value, str)
                and value.startswith("sha256:")
                and len(value) == 71
                and all(c in "0123456789abcdef" for c in value[7:]),
                "fold_hash",
            )
    for cell in result["cells"]:
        require(
            set(cell)
            == set(family.IDENTITY)
            | {"eligible_decisions", "future_censored", "selected_censored", "metrics"},
            "cell_fields",
        )
        metrics = cell["metrics"]
        require(_metric_shape(metrics, template), "metric_fields")
        fold = folds[cell["symbol"], cell["fold"]]
        count = metrics["n"]
        bins = metrics["predicted_bins"]
        selected = metrics["selected_gt_6bps"]
        require(
            all(
                type(v) is int and v >= 0
                for v in (
                    count,
                    metrics["session_count"],
                    metrics["valid_session_count"],
                    cell["eligible_decisions"],
                    cell["future_censored"],
                    cell["selected_censored"],
                    selected["n"],
                    *(b["n"] for b in bins.values()),
                )
            ),
            "metric_support",
        )
        require(
            count >= 32
            and count + cell["future_censored"]
            == cell["eligible_decisions"]
            == fold["evaluation_inputs"]["eligible"]
            and cell["future_censored"] == fold["evaluation_outcomes"]["future_missing"]
            and cell["selected_censored"] <= cell["future_censored"]
            and 0 <= metrics["valid_session_count"] <= metrics["session_count"] <= count
            and sum(b["n"] for b in bins.values()) == count
            and selected["n"] == bins["(6,inf)"]["n"]
            and selected["share"] == selected["n"] / count,
            "metric_support",
        )
    # Persist only aggregate metrics, never per-observation forecasts or targets.
    json.dumps(result, allow_nan=False)


def _metric_shape(value, template):
    if isinstance(template, dict):
        return (
            isinstance(value, dict)
            and set(value) == set(template)
            and all(_metric_shape(value[k], template[k]) for k in template)
        )
    return value is None or (type(value) in (int, float) and math.isfinite(value))


def worker(root, market, scope_hash, result_path):
    deadline = time.monotonic() + SECONDS
    try:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        import torch
        from threadpoolctl import threadpool_limits

        require(
            h30.importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version"
        )
        require(h30.importlib.metadata.version("lightgbm") == "4.6.0", "lightgbm_version")
        verify(root, scope_hash)
        parent, receipt, prior, directory, results, _ = lineage(root)
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        with threadpool_limits(limits=1):
            result = compare(
                h30.load_streams(market, receipt, deadline),
                torch,
                parent,
                prior,
                directory,
                results,
                h30.EmergencyStore(Path(result_path).parent / "emergency.json"),
                deadline,
                scope_hash,
            )
        verify(root, scope_hash)
        h30.check_time(deadline)
    except Exception:
        result = failure(scope_hash, "runtime_or_invariant_failure")
    with Path(result_path).open("xb") as handle:
        handle.write(h30.encode(result))
