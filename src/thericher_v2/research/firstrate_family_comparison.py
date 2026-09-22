"""Fixed H30/context36 DEVELOPMENT comparison, with replayed parent controls."""

from __future__ import annotations

import io
import json
import math
import time
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_family_models as models
from thericher_v2.research import firstrate_session_research as sessions

h30 = sessions.h30
require = sessions.require
NAME = "model-family-h30-c36-v1"
FAMILY, REPO = h30.FAMILY, h30.REPO
SECONDS = {"cpu": 600, "cuda": 900}
PARENT_CONTRACT = "sha256:012497f503e322dcbc076aacc174dc10e039b1da185876b0744b07f33e4a0646"
PARENT_HASHES = {
    "cpu": "sha256:5198f95a0c6a8863cd18a9fa8e74431a1e0f4b827b4cebab47b59b58cb14523b",
    "cuda": "sha256:4bacb76827f3de667c331e37b65a5a7b603e6be51b94034041524b268350e3b1",
}
WHEEL = "public-runtime/lightgbm-4.6.0/lightgbm-4.6.0-py3-none-manylinux_2_28_x86_64.whl"
WHEEL_HASH = "sha256:cb19b5afea55b5b61cbb2131095f50538bd608a00655f23ad5d25ae3e3bf1c8d"
CODE = (
    "src/thericher_v2/research/firstrate_family_comparison.py",
    "src/thericher_v2/research/firstrate_family_models.py",
    "scripts/run_firstrate_family_comparison.py",
    *sessions.OWN_FILES,
)
IDENTITY = ("symbol", "fold", "horizon_minutes", "candidate", "context", "seed")
SCALERS = {"channel_mean", "channel_scale", "target_mean", "target_scale"}


def candidates(phase):
    if phase == "cpu":
        return [(n, None, None) for n in (*h30.NAIVES, "sma3_12")] + [
            ("ridge", 36, None),
            ("lightgbm", 36, 101),
            ("lstm", 36, 101),
            ("lstm", 36, 103),
        ]
    require(phase == "cuda", "phase")
    return [(n, 36, seed) for n in models.ARCHITECTURES for seed in h30.SEEDS]


def identities(phase, *, fitted=False):
    return [
        dict(zip(IDENTITY, (symbol, fold, 30, name, context, seed), strict=True))
        for symbol in h30.SYMBOLS
        for fold in (1, 2)
        for name, context, seed in candidates(phase)
        if not fitted or name in ("lightgbm", *models.ARCHITECTURES)
    ]


def lineage(root):
    output, _, _ = sessions.verify(root, PARENT_CONTRACT)
    prior = {}
    for phase, pin in PARENT_HASHES.items():
        raw = (output / f"{phase}-summary.json").read_bytes()
        require(h30.digest(raw) == pin, "lineage_changed")
        prior[phase] = json.loads(raw)
        sessions.validate_result(prior[phase], phase, PARENT_CONTRACT)
    require(h30.digest(h30.within(root, WHEEL).read_bytes()) == WHEEL_HASH, "lineage_changed")
    return output, prior


def contract(receipt):
    return {
        "name": NAME,
        "family": FAMILY,
        "parent_contract_sha256": PARENT_CONTRACT,
        "parent_summaries": PARENT_HASHES,
        "parent_cohort_contract": sessions.contract(receipt),
        "code_sha256": {p: h30.digest((REPO / p).read_bytes()) for p in CODE},
        "lightgbm": {
            "version": "4.6.0",
            "license": "MIT",
            "source": "https://github.com/lightgbm-org/LightGBM/tree/v4.6.0",
            "wheel": WHEEL,
            "wheel_sha256": WHEEL_HASH,
            "parameters": "64trees,7leaves,depth3,lr0.05,minchild64,lambda1,seed101,1thread",
            "runtime": "offline wheel install; import torch first for bundled OpenMP",
        },
        "horizon_minutes": 30,
        "context": 36,
        "cpu_candidates": candidates("cpu"),
        "cuda_candidates": candidates("cuda"),
        "sequence": "hidden16,8epochs,batch128,AdamW0.001/wd0.01,chronological,seeds101/103",
        "tcn": "5 left-padded kernel3 convolutions; dilations1/2/4/8/16; RF63; ReLU",
        "attention": "one causal Transformer encoder;2heads;FF32;sinusoidal position;dropout0",
        "comparison_budget": "4newLightGBM+16newDL;4Ridge;8parentLSTM reloads;144costcells",
        "compute_matching": "fixed epochs, NOT equal parameters/FLOPs; report counts",
        "phase_seconds": SECONDS,
        "selection": False,
        "promotion": False,
        "holdout_access": False,
        "retry": False,
        "strongest_kill_test": "parent84 control cells or cohort differs; reload changes decisions",
        "retention": "all20 new models; native LightGBM text or numeric NPZ; scalers/config/hash",
        "evidence_grade": "OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
        "review": "supported-with-limits; mounted verified wheel permits offline install; "
        "TCN is new arm; purge uses exit;1thread;no winner/generalization;preemption voids phase",
    }


def freeze(root):
    root = h30.ensure_external_artifact_directory(root, REPO)
    lineage(root)
    receipt = h30.within(root, h30.RECEIPT).read_bytes()
    payload = contract(receipt)
    raw = h30.encode(payload)
    output = h30.run_directory(root, NAME)
    output.mkdir(parents=True, exist_ok=False)
    (output / "contract.json").write_bytes(raw)
    h30.register_frozen_campaign(
        contract_hash=h30.digest(raw),
        dataset_hash=h30.digest(h30.encode(payload["parent_cohort_contract"]["source_pins"])),
        split_hash=h30.digest(h30.encode([PARENT_CONTRACT, "H30-context36"])),
        cost_model_hash=h30.digest(h30.encode([h30.COSTS, "fees_only", "independent_one_share"])),
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
    lineage(root)
    return output, receipt, json.loads(raw)


def sequence_predict(torch, model, values, device="cpu"):
    model.to(device).eval()
    with torch.inference_mode():
        return np.concatenate(
            [
                model(torch.tensor(values[i : i + 128], device=device)).flatten().cpu().numpy()
                for i in range(0, len(values), 128)
            ]
        )


def restore_sequence(torch, name, arrays):
    model = (
        h30.build_torch_sequence_model(
            torch=torch,
            architecture_id="lstm",
            feature_count=4,
            hidden_size=16,
            attention_heads=1,
            tcn_kernel_size=3,
        )
        if name == "lstm"
        else models.build_sequence(torch, name)
    )
    expected = model.state_dict()
    state = {k.removeprefix("state."): v for k, v in arrays.items() if k.startswith("state.")}
    require(set(state) == set(expected), "model_reload")
    require(
        all(
            v.dtype == np.float32 and v.shape == tuple(expected[k].shape) and np.isfinite(v).all()
            for k, v in state.items()
        ),
        "model_reload",
    )
    model.load_state_dict({k: torch.from_numpy(v) for k, v in state.items()}, strict=True)
    return model


def read_arrays(path):
    require(path.stat().st_size < 2 * 1024**2, "model_reload")
    with np.load(io.BytesIO(path.read_bytes()), allow_pickle=False) as archive:
        return {k: archive[k].copy() for k in archive.files}


def check_scalers(arrays, fold=None):
    require(SCALERS <= set(arrays), "model_reload")
    for key in SCALERS:
        v = arrays[key]
        require(
            v.dtype == np.float64
            and v.shape == ((4,) if key.startswith("channel") else (1,))
            and np.isfinite(v).all(),
            "model_reload",
        )
        if key.endswith("scale"):
            require(bool((v > 0).all()), "model_reload")
    if fold is not None:
        require(
            all(np.array_equal(arrays[k], v) for k, v in scaler_arrays(fold).items()),
            "parent_control_mismatch",
        )


def scaler_arrays(fold):
    return {
        "channel_mean": fold.channel_mean,
        "channel_scale": fold.channel_scale,
        "target_mean": np.array([fold.y_mean]),
        "target_scale": np.array([fold.y_scale]),
    }


def parent_prediction(torch, fold, seed, parent_root, prior):
    ref = next(
        r
        for r in prior["cuda"]["models"]
        if (r["symbol"], r["fold"], r["horizon_minutes"], r["context"], r["seed"])
        == (fold.symbol, fold.fold, 30, 36, seed)
    )
    root = parent_root / "models"
    raw = h30.within(root, ref["config_file"]).read_bytes()
    require(h30.digest(raw) == ref["config_sha256"], "parent_control_mismatch")
    cfg = json.loads(raw)
    require(
        cfg["contract_sha256"] == PARENT_CONTRACT
        and cfg["name"] == sessions.NAME
        and cfg["cohort_sha256"] == fold.facts["cohort_sha256"]
        and all(cfg[k] == ref[k] for k in IDENTITY if k != "candidate"),
        "parent_control_mismatch",
    )
    path = h30.within(root, ref["weights_file"])
    require(
        h30.digest(path.read_bytes()) == ref["weights_sha256"] == cfg["weights_sha256"],
        "parent_control_mismatch",
    )
    arrays = read_arrays(path)
    h30.validate_model_arrays(arrays)
    check_scalers(arrays, fold)
    return sequence_predict(torch, restore_sequence(torch, "lstm", arrays), fold.eval_x)


def save_model(root, fold, identity, state, prediction, scope_hash, torch):
    root.mkdir(exist_ok=True)
    name = "-".join(str(identity[k]) for k in IDENTITY)
    tree = identity["candidate"] == "lightgbm"
    weights = name + (".txt" if tree else ".npz")
    scalers = name + ".npz"
    arrays = scaler_arrays(fold) if tree else {**state, **scaler_arrays(fold)}
    with (root / scalers).open("xb") as handle:
        np.savez(handle, **arrays)
    if tree:
        with (root / weights).open("xb") as handle:
            handle.write(state.encode("utf-8"))
    cfg = {
        **identity,
        "name": NAME,
        "contract_sha256": scope_hash,
        "cohort_sha256": fold.facts["cohort_sha256"],
        "normalizer_sha256": fold.facts["normalizer_sha256"],
        "weights_file": weights,
        "weights_sha256": h30.digest((root / weights).read_bytes()),
        "scalers_file": scalers,
        "scalers_sha256": h30.digest((root / scalers).read_bytes()),
        "private_development_only": True,
    }
    raw = h30.encode(cfg)
    with (root / (name + ".json")).open("xb") as handle:
        handle.write(raw)
    ref = {
        **identity,
        "config_file": name + ".json",
        "config_sha256": h30.digest(raw),
        **{k: cfg[k] for k in ("weights_file", "weights_sha256", "scalers_file", "scalers_sha256")},
    }
    restored, loaded = load_model(root, ref, scope_hash, torch)
    check_scalers(loaded, fold)
    again = (
        restored.predict(fold.eval_x.reshape(len(fold.eval_x), -1))
        if tree
        else sequence_predict(torch, restored, fold.eval_x, "cuda")
    )
    require(
        np.allclose(again, prediction, rtol=1e-5, atol=1e-6)
        and np.array_equal(
            again * fold.y_scale + fold.y_mean > 6, prediction * fold.y_scale + fold.y_mean > 6
        ),
        "model_reload",
    )
    return ref


def load_model(root, ref, scope_hash, torch):
    raw = h30.within(root, ref["config_file"]).read_bytes()
    require(h30.digest(raw) == ref["config_sha256"], "model_reload")
    cfg = json.loads(raw)
    require(
        cfg["name"] == NAME
        and cfg["contract_sha256"] == scope_hash
        and cfg["private_development_only"] is True
        and all(cfg[k] == ref[k] for k in IDENTITY),
        "model_reload",
    )
    for key in ("weights", "scalers"):
        path = h30.within(root, ref[key + "_file"])
        require(
            path.stat().st_size < 2 * 1024**2
            and h30.digest(path.read_bytes()) == ref[key + "_sha256"] == cfg[key + "_sha256"]
            and cfg[key + "_file"] == ref[key + "_file"],
            "model_reload",
        )
    arrays = read_arrays(h30.within(root, ref["scalers_file"]))
    check_scalers(arrays)
    normalizer = h30.digest(
        arrays["channel_mean"].tobytes()
        + arrays["channel_scale"].tobytes()
        + h30.encode([float(arrays["target_mean"][0]), float(arrays["target_scale"][0])])
    )
    require(normalizer == cfg["normalizer_sha256"], "model_reload")
    if ref["candidate"] == "lightgbm":
        import lightgbm

        require(set(arrays) == SCALERS, "model_reload")
        model = lightgbm.Booster(model_file=str(h30.within(root, ref["weights_file"])))
        require(model.num_feature() == 144 and 1 <= model.num_trees() <= 64, "model_reload")
    else:
        require(
            ref["weights_file"] == ref["scalers_file"]
            and all(k in SCALERS or k.startswith("state.") for k in arrays),
            "model_reload",
        )
        model = restore_sequence(torch, ref["candidate"], arrays)
    return model, arrays


def verify_models(root, result, scope_hash):
    import torch

    require(
        [{k: r[k] for k in IDENTITY} for r in result["models"]]
        == identities(result["phase"], fitted=True),
        "model_reload",
    )
    for ref in result["models"]:
        load_model(root, ref, scope_hash, torch)
        cfg = json.loads(h30.within(root, ref["config_file"]).read_bytes())
        fold = next(
            f
            for f in result["folds"]
            if (f["symbol"], f["fold"], f["horizon_minutes"])
            == (ref["symbol"], ref["fold"], ref["horizon_minutes"])
        )
        require(
            all(cfg[k] == fold[k] for k in ("cohort_sha256", "normalizer_sha256")), "model_reload"
        )


def score(fold, decisions, index, emergency, deadline, replay=sessions.payoff):
    observed, censor = sessions.outcomes(index, fold.evaluation, 30)
    supported = [o for o, y in zip(fold.evaluation, observed, strict=True) if y is not None]
    blocks = h30.blocks(supported)
    if len(supported) < 32 or blocks < 8:
        raise sessions.OutcomeSupportShortfall(len(observed), len(supported), blocks)
    fold.facts.update(evaluation_outcomes=censor, scored_blocks_36=blocks)
    cells = []
    for cost in h30.COSTS:
        replays = []
        for obs, out in zip(fold.evaluation, observed, strict=True):
            h30.check_time(deadline)
            replays.append(None if out is None else replay(obs, out, cost, emergency))
        for ident, selected in decisions:
            trades = [
                r for flag, r in zip(selected, replays, strict=True) if flag and r is not None
            ]
            gross = sum((r[0] for r in trades), Decimal(0))
            fees = sum((r[1] for r in trades), Decimal(0))
            cells.append(
                {
                    **ident,
                    "cost_bps_per_side": cost,
                    "eligible_decisions": len(selected),
                    "selected_decisions": int(selected.sum()),
                    "future_censored": censor["future_missing"],
                    "selected_censored": sum(
                        bool(v) and r is None for v, r in zip(selected, replays, strict=True)
                    ),
                    "roundtrips": len(trades),
                    "gross_dollars": str(gross),
                    "fees_dollars": str(fees),
                    "net_dollars": str(gross - fees),
                    "turnover_dollars": str(
                        sum(
                            (
                                o.entry + o.exit
                                for flag, o in zip(selected, observed, strict=True)
                                if flag and o is not None
                            ),
                            Decimal(0),
                        )
                    ),
                    "roundtrips_per_session": len(trades) / fold.facts["eval_calendar_sessions"],
                    "wins": sum(g > f for g, f in trades),
                    "local_paper_replay_parity": True,
                }
            )
    return cells


def parent_parity(result, prior):
    validate_folds(result)
    for fold in result["folds"]:
        parent = next(
            f
            for f in prior["cpu"]["folds"]
            if (f["symbol"], f["fold"], f["horizon_minutes"]) == (fold["symbol"], fold["fold"], 30)
        )
        require(fold == parent, "parent_control_mismatch")
    controls = {sessions.cell_key(c): c for phase in prior.values() for c in phase["cells"]}
    matched = 0
    for cell in result["cells"]:
        if cell["candidate"] in (*h30.NAIVES, "sma3_12", "ridge", "lstm"):
            require(cell == controls.get(sessions.cell_key(cell)), "parent_control_mismatch")
            matched += 1
    require(matched == (84 if result["phase"] == "cpu" else 0), "parent_control_mismatch")
    return matched


def compare(
    streams, phase, emergency, deadline, torch, root, scope_hash, parent_root, prior, reference=None
):
    result = {**failure(phase, scope_hash, None), "status": "complete"}
    result.pop("reason")
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        for number, plan in enumerate(sessions.plans(sessions.regular_sessions(bars), 30), 1):
            h30.check_time(deadline)
            fold = sessions.prepare_fold(symbol, number, index, plan, 30)
            decisions = []
            for name, context, seed in candidates(phase):
                ident = dict(zip(IDENTITY, (symbol, number, 30, name, context, seed), strict=True))
                if name == "ridge":
                    prediction = h30.ridge_predict(fold, 36)
                elif name == "lstm":
                    prediction = parent_prediction(torch, fold, seed, parent_root, prior)
                elif name in ("lightgbm", *models.ARCHITECTURES):
                    prediction, state, facts = (
                        models.fit_lightgbm(fold)
                        if name == "lightgbm"
                        else models.fit_sequence(torch, fold, name, seed, deadline)
                    )
                    result["fits"].append({**ident, **facts})
                    result["models"].append(
                        save_model(root, fold, ident, state, prediction, scope_hash, torch)
                    )
                else:
                    selected = np.asarray(
                        [
                            name == "always_long"
                            or (name == "previous_bar_direction" and o.signal.close > o.signal.open)
                            or (
                                name == "sma3_12"
                                and sum(index[o.at - i * h30.STEP].close for i in range(1, 4)) / 3
                                > sum(index[o.at - i * h30.STEP].close for i in range(1, 13)) / 12
                            )
                            for o in fold.evaluation
                        ]
                    )
                    decisions.append((ident, selected))
                    continue
                prediction = np.asarray(prediction)
                require(
                    prediction.shape == (len(fold.evaluation),) and np.isfinite(prediction).all(),
                    "nonfinite_fit",
                )
                decisions.append((ident, prediction * fold.y_scale + fold.y_mean > 6))
            result["cells"].extend(score(fold, decisions, index, emergency, deadline))
            result["folds"].append(fold.facts)
    result["parent_controls_reproduced"] = parent_parity(result, prior)
    if phase == "cuda":
        require(result["folds"] == reference["folds"], "cpu_cuda_cohort_changed")
    return result


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
        "evidence_grade": "OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
    }


def validate_folds(result):
    require(
        [(f["symbol"], f["fold"], f["horizon_minutes"]) for f in result["folds"]]
        == [(symbol, number, 30) for symbol in h30.SYMBOLS for number in (1, 2)],
        "fit_matrix",
    )


def validate_result(result, phase, scope_hash):
    validate_folds(result)
    require(
        result["status"] == "complete"
        and result["name"] == NAME
        and result["phase"] == phase
        and result["contract_sha256"] == scope_hash
        and result["promotion"] is False
        and result["holdout_access"] is False,
        "result_identity",
    )
    expected = [
        (*tuple(i[k] for k in IDENTITY), cost)
        for symbol in h30.SYMBOLS
        for number in (1, 2)
        for cost in h30.COSTS
        for i in identities(phase)
        if i["symbol"] == symbol and i["fold"] == number
    ]
    require([sessions.cell_key(c) for c in result["cells"]] == expected, "cell_matrix")
    wanted = identities(phase, fitted=True)
    require(
        len(result["folds"]) == 4
        and [{k: f[k] for k in IDENTITY} for f in result["fits"]] == wanted
        and [{k: f[k] for k in IDENTITY} for f in result["models"]] == wanted,
        "fit_matrix",
    )
    require(
        result["parent_controls_reproduced"] == (84 if phase == "cpu" else 0),
        "parent_control_mismatch",
    )
    for fit in result["fits"]:
        require(
            all(
                math.isfinite(fit[k]) and fit[k] >= 0
                for k in ("initial_train_mse", "final_train_mse", "train_mean_baseline_mse")
            ),
            "nonfinite_fit",
        )
        if phase == "cuda":
            require(
                fit["epochs"] == 8 and fit["updates"] == 8 * math.ceil(fit["train_rows"] / 128),
                "training_passes",
            )
    for cell in result["cells"]:
        require(
            Decimal(cell["gross_dollars"]) - Decimal(cell["fees_dollars"])
            == Decimal(cell["net_dollars"])
            and cell["local_paper_replay_parity"] is True,
            "result_accounting",
        )


def worker(root, market, scope_hash, phase, cpu_hash, result_path):
    deadline = time.monotonic() + SECONDS[phase]
    try:
        import torch
        from threadpoolctl import threadpool_limits

        require(
            h30.importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version"
        )
        output, receipt, _ = verify(root, scope_hash)
        parent_root, prior = lineage(root)
        reference = None
        if phase == "cuda":
            raw = (output / "cpu-summary.json").read_bytes()
            require(h30.digest(raw) == cpu_hash, "cpu_summary_hash")
            reference = json.loads(raw)
            validate_result(reference, "cpu", scope_hash)
            torch, runtime = h30.configure_cuda()
        else:
            torch.set_num_threads(1)
            torch.use_deterministic_algorithms(True)
            runtime = {"backend": "cpu", "lightgbm": "4.6.0"}
        with threadpool_limits(limits=1):
            result = compare(
                h30.load_streams(market, receipt, deadline),
                phase,
                h30.EmergencyStore(Path(result_path).parent / "emergency.json"),
                deadline,
                torch,
                Path(result_path).parent / "models",
                scope_hash,
                parent_root,
                prior,
                reference,
            )
        result.update(
            runtime={**runtime, "environment": h30.runtime_identity()}, cpu_summary_sha256=cpu_hash
        )
        validate_result(result, phase, scope_hash)
        verify_models(Path(result_path).parent / "models", result, scope_hash)
        h30.check_time(deadline)
    except sessions.OutcomeSupportShortfall as error:
        result = failure(phase, scope_hash, "evaluation_outcome_support_shortfall")
        result["support"] = error.support
    except h30.StudyFailure as error:
        reason = str(error)
        allowed = {
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
            "parent_control_mismatch",
            "lightgbm_version",
        }
        result = failure(
            phase, scope_hash, reason if reason in allowed else "study_invariant_failed"
        )
    except Exception:
        result = failure(phase, scope_hash, "runtime_or_invariant_failure")
    with Path(result_path).open("xb") as handle:
        handle.write(h30.encode(result))
