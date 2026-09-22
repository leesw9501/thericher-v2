"""Fixed-update, seen-data H30 successor; reuse the closed study's data/replay code."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_h30_train_learnability as learn

h30, d, require = learn.h30, learn.d, learn.require
NAME, CONTEXT, UPDATES, BATCH = "full-cohort-u256-v1", 12, 256, 128
SECONDS = {"cpu": 600, "cuda": 180}
KEYS = tuple((s, f, CONTEXT, seed) for s in h30.SYMBOLS for f in (1, 2) for seed in h30.SEEDS)
LEARN_HASH = "sha256:f2be555bc0b42f58237a6bc23ab258dcecd04491bcf70036f86a2cc9e4b663b2"
LEARN_SUMMARY = "sha256:833a5aafbdf1ea561be2d9fb4d449f19c0c0f4e0df88ab42ec747ecf6abf653d"
OWN_FILES = (
    "src/thericher_v2/research/firstrate_h30_full_cohort.py",
    "scripts/run_firstrate_h30_full_cohort.py",
    *d.OWN_FILES,
    *learn.OWN_FILES,
)


def contract(receipt):
    parent = h30.contract_payload(receipt)
    training = {k: v for k, v in parent["training"].items() if k != "epochs"}
    return {
        **parent,
        "name": NAME,
        "parent_contract_sha256": d.H30_HASH,
        "parent_summary_sha256": d.SUMMARY_HASHES,
        "diagnostic_contract_sha256": learn.DIAGNOSTIC_HASH,
        "diagnostic_summary_sha256": learn.DIAGNOSTIC_SUMMARY,
        "learnability_contract_sha256": LEARN_HASH,
        "learnability_summary_sha256": LEARN_SUMMARY,
        "code_sha256": {
            **parent["code_sha256"],
            **{p: h30.digest((h30.REPO / p).read_bytes()) for p in OWN_FILES},
        },
        "contexts": [CONTEXT],
        "image_sha256": "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039",
        "training": {
            **training,
            "updates_per_fit": UPDATES,
            "batch_size": BATCH,
            "order": "repeat chronological minibatch passes including short final batch; "
            "stop at exactly256 updates, no reshuffle or outcome-based stopping",
        },
        "budget": {
            **parent["budget"],
            "gpu_fits": 8,
            "ridge_fits": 4,
            "cost_cells": 72,
            "cpu_cells": 48,
            "cuda_cells": 24,
            "phase_seconds": SECONDS,
            "per_gpu_fit_seconds": None,
            "shared_max_optimizer_updates": 2048,
        },
        "fit_order": "SPY,QQQ / original fold1,2 / context12 / seed101,103",
        "retained_weights": "all8_final_update256_after_whole_phase_parity_and_numeric_reload",
        "report": "all fixed cells; full TRAIN initial/final MSE and train-mean ratio; "
        "intent/activity/censor counts; no selected winner",
        "artifact": f"research/{h30.FAMILY}/{NAME}",
        "preemption": "existing exclusive GpuFileLock and SIGINT/SIGTERM child reaping",
        "review": "Claude tool-disabled supported-with-limits: TRAIN loss change descriptive, "
        "not a success criterion; fixed final eval-side controls are descriptive only; "
        "no restart, fallback, selection, independent skill or promotion claim",
    }


def lineage(root):
    output, receipt, payload, cpu, cuda = d.bindings(root)
    for path, expected in (
        (output / d.NAME / "summary.json", learn.DIAGNOSTIC_SUMMARY),
        (h30.run_directory(root, learn.NAME) / "summary.json", LEARN_SUMMARY),
    ):
        require(h30.digest(path.read_bytes()) == expected, "lineage_changed")
    require(h30.digest(h30.encode(d.contract())) == learn.DIAGNOSTIC_HASH, "diagnostic_changed")
    require(h30.digest(h30.encode(learn.contract())) == LEARN_HASH, "learnability_changed")
    return receipt, payload, cpu, cuda


def freeze(root):
    receipt, _, _, _ = lineage(root)
    payload = contract(receipt)
    output = h30.run_directory(root, NAME)
    output.mkdir(parents=True, exist_ok=False)
    raw = h30.encode(payload)
    with (output / "contract.json").open("xb") as handle:
        handle.write(raw)
    h30.register_frozen_campaign(
        contract_hash=h30.digest(raw),
        dataset_hash=h30.digest(h30.encode(payload["source_pins"])),
        split_hash=h30.digest(h30.encode([payload[k] for k in ("split", "purge", "sampling")])),
        cost_model_hash=h30.digest(h30.encode([h30.COSTS, "fees_only", "independent_one_share"])),
        trial_family=h30.FAMILY,
        holdout_access="none",
        artifact_root=root,
        repo_root=h30.REPO,
    )
    return h30.digest(raw)


def verify(root, scope_hash):
    receipt, payload, cpu, cuda = lineage(root)
    output = h30.run_directory(root, NAME)
    raw = (output / "contract.json").read_bytes()
    require(
        h30.digest(raw) == scope_hash and raw == h30.encode(contract(receipt)), "contract_changed"
    )
    return output, receipt, payload, cpu, cuda


def expected_cells(phase):
    return [c for c in h30.expected_cells(phase) if c["context"] in (None, CONTEXT)]


def failure(phase, scope_hash, reason):
    return {
        **h30.result_base(phase),
        "name": NAME,
        "status": "failed_all_phase_cells",
        "contract_sha256": scope_hash,
        "reason": reason,
        "cells": [],
        "fits": [],
        "models": [],
        "unavailable_cells": len(expected_cells(phase)),
    }


def batch_slices(count):
    require(count >= h30.MIN_TRAIN, "training_support_shortfall")
    starts = tuple(range(0, count, BATCH))
    return tuple(
        slice(starts[i % len(starts)], min(count, starts[i % len(starts)] + BATCH))
        for i in range(UPDATES)
    )


def fit(torch, fold, seed, deadline, *, device="cuda:0"):
    started = time.monotonic()
    h30.check_time(deadline)
    torch.random.default_generator.manual_seed(seed)
    if device == "cuda:0":
        torch.cuda.manual_seed_all(seed)
    model = h30.build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm",
        feature_count=4,
        hidden_size=16,
        attention_heads=1,
        tcn_kernel_size=3,
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=0.001,
        weight_decay=0.01,
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    x = torch.tensor(fold.train_x[:, -CONTEXT:], dtype=torch.float32, device=device)
    y = torch.tensor(fold.train_y, dtype=torch.float32, device=device)
    baseline = float(np.var(fold.train_y.astype(np.float64)))
    require(baseline > 0, "constant_train_target")
    initial = learn.parameter_vector(torch, model)
    before = learn.checkpoint(torch, model, x, y, baseline)
    for update, batch in enumerate(batch_slices(len(y)), 1):
        h30.check_time(deadline)
        optimizer.zero_grad(set_to_none=True)
        loss = torch.nn.functional.mse_loss(model(x[batch]).flatten(), y[batch])
        require(bool(torch.isfinite(loss).item()), "nonfinite_loss")
        loss.backward()
        learn.parameter_vector(torch, model, gradients=True)
        optimizer.step()
        movement = learn.rms(learn.parameter_vector(torch, model) - initial)
        require(update != 1 or movement > 0, "no_first_update")
        h30.check_time(deadline)
    after = learn.checkpoint(torch, model, x, y, baseline)
    model.eval()
    with torch.inference_mode():
        predicted = model(torch.tensor(fold.eval_x[:, -CONTEXT:], device=device)).flatten()
        predicted = d.finite(predicted.cpu().numpy(), len(fold.evaluation))
    state = {"state." + k: v.detach().cpu().numpy().copy() for k, v in model.state_dict().items()}
    h30.check_time(deadline)
    return (
        predicted,
        state,
        {
            "symbol": fold.symbol,
            "fold": fold.fold,
            "context": CONTEXT,
            "seed": seed,
            "updates": UPDATES,
            "train_rows": len(y),
            "train_mean_baseline_mse": baseline,
            "initial": before,
            "final": after,
            "parameter_movement_rms": movement,
            "fit_wall_seconds": round(time.monotonic() - started, 6),
        },
    )


def compare(
    streams,
    phase,
    reference,
    emergency,
    deadline,
    *,
    torch=None,
    trainer=fit,
    ridge=h30.ridge_predict,
):
    result = {**h30.result_base(phase), "name": NAME, "fits": []}
    retained = []
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        for number, plan in enumerate(h30.plans(bars), 1):
            h30.check_time(deadline)
            expected = [(symbol, number) for symbol in h30.SYMBOLS for number in (1, 2)]
            require(
                len(result["folds"]) < len(expected)
                and (symbol, number) == expected[len(result["folds"])],
                "fold_matrix",
            )
            fold = h30.prepare_fold(symbol, number, index, plan)
            prior = next(
                f for f in reference["folds"] if (f["symbol"], f["fold"]) == (symbol, number)
            )
            require(fold.facts["train_supported"], "training_support_shortfall")
            for key in (*d.TRAIN_FACTS, "cohort_sha256", "evaluation_inputs"):
                require(fold.facts[key] == prior[key], "parent_cohort_or_scaler_changed")
            signals = {}
            for seed in h30.SEEDS if phase == "cuda" else (None,):
                if phase == "cuda":
                    predicted, state, facts = trainer(torch, fold, seed, deadline)
                    retained.append((fold, seed, state))
                    result["fits"].append(facts)
                else:
                    predicted = ridge(fold, CONTEXT)
                predicted = d.finite(predicted, len(fold.evaluation))
                signals[("lstm" if phase == "cuda" else "ridge", CONTEXT, seed)] = tuple(
                    bool(v > 0) for v in predicted * fold.y_scale + fold.y_mean
                )
            if phase == "cpu":
                signals.update(
                    {
                        ("always_flat", None, None): (False,) * len(fold.evaluation),
                        ("always_long", None, None): (True,) * len(fold.evaluation),
                        ("previous_bar_direction", None, None): tuple(
                            o.signal.close > o.signal.open for o in fold.evaluation
                        ),
                    }
                )
            facts, cells = h30.score(fold, index, signals, emergency, deadline)
            require(cells is not None, "evaluation_support_shortfall")
            require(
                facts["outcome_mask_sha256"] == prior["outcome_mask_sha256"], "outcome_mask_changed"
            )
            result["folds"].append(facts)
            result["cells"].extend(cells)
    require(
        [(f["symbol"], f["fold"]) for f in result["folds"]]
        == [(s, f) for s in h30.SYMBOLS for f in (1, 2)],
        "fold_matrix",
    )
    h30.add_deltas(result["cells"], reference["cells"] if phase == "cuda" else result["cells"])
    result["status"] = "complete"
    return result, retained


def validate_result(result, phase, scope_hash):
    require(
        result.get("contract_sha256") == scope_hash
        and result.get("name") == NAME
        and result.get("phase") == phase
        and result.get("status") == "complete",
        "worker_identity",
    )
    cells = result["cells"]
    require(
        len(cells) == len(expected_cells(phase))
        and {h30.cell_key(c) for c in cells} == {h30.cell_key(c) for c in expected_cells(phase)}
        and all(c["status"] == "complete" and c["parity_verified"] for c in cells),
        "cell_matrix",
    )
    keys = [tuple(f[k] for k in d.IDENTITY) for f in result["fits"]]
    require(
        keys == (list(KEYS) if phase == "cuda" else [])
        and all(f["updates"] == UPDATES for f in result["fits"]),
        "fit_matrix",
    )


def load_model(root, reference, scope_hash):
    raw = h30.within(root, reference["config_file"]).read_bytes()
    require(h30.digest(raw) == reference["config_sha256"], "model_config_hash")
    config = json.loads(raw)
    require(
        config["contract_sha256"] == scope_hash
        and config["name"] == NAME
        and config["final_update"] == UPDATES
        and config["architecture"] == "lstm"
        and tuple(config[k] for k in d.IDENTITY) in KEYS
        and all(config[k] == reference[k] for k in d.IDENTITY),
        "model_identity",
    )
    path = h30.within(root, reference["weights_file"])
    require(path.stat().st_size < 1024 * 1024, "model_archive_budget")
    raw = path.read_bytes()
    require(
        h30.digest(raw) == reference["weights_sha256"] == config["weights_sha256"], "model_hash"
    )
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        require(len(archive.files) == len(h30.STATE_SHAPES), "model_array_keys")
        arrays = {k: archive[k].copy() for k in archive.files}
    h30.validate_model_arrays(arrays)
    return config, arrays


def save_models(root, retained, scope_hash, pins, runtime, torch, deadline):
    require(
        [(f.symbol, f.fold, CONTEXT, seed) for f, seed, _ in retained] == list(KEYS), "model_matrix"
    )
    root.mkdir(exist_ok=False)
    refs = []
    for fold, seed, state in retained:
        h30.check_time(deadline)
        arrays = {
            **state,
            "channel_mean": fold.channel_mean,
            "channel_scale": fold.channel_scale,
            "target_mean": np.array([fold.y_mean]),
            "target_scale": np.array([fold.y_scale]),
        }
        h30.validate_model_arrays(arrays)
        name = f"{fold.symbol}-f{fold.fold}-c{CONTEXT}-s{seed}"
        with (root / f"{name}.npz").open("xb") as handle:
            np.savez(handle, **arrays)
        ref = dict(zip(d.IDENTITY, (fold.symbol, fold.fold, CONTEXT, seed), strict=True))
        ref.update(
            weights_file=f"{name}.npz",
            config_file=f"{name}.json",
            weights_sha256=h30.digest((root / f"{name}.npz").read_bytes()),
        )
        config = {
            **ref,
            "name": NAME,
            "family": h30.FAMILY,
            "architecture": "lstm",
            "hidden_size": 16,
            "layers": 1,
            "feature_count": 4,
            "final_update": UPDATES,
            "contract_sha256": scope_hash,
            "source_pins": pins,
            "runtime": runtime,
            "cohort_sha256": fold.facts["cohort_sha256"],
            "normalizer_sha256": fold.facts["normalizer_sha256"],
            "private_development_inference_only": True,
            "promotion": False,
        }
        raw = h30.encode(config)
        with (root / ref["config_file"]).open("xb") as handle:
            handle.write(raw)
        ref["config_sha256"] = h30.digest(raw)
        _, loaded = load_model(root, ref, scope_hash)
        require(all(np.array_equal(v, loaded[k]) for k, v in arrays.items()), "model_roundtrip")
        restored = h30.build_torch_sequence_model(
            torch=torch,
            architecture_id="lstm",
            feature_count=4,
            hidden_size=16,
            attention_heads=1,
            tcn_kernel_size=3,
        )
        restored.load_state_dict(
            {
                k.removeprefix("state."): torch.from_numpy(v)
                for k, v in loaded.items()
                if k.startswith("state.")
            },
            strict=True,
        )
        restored.eval()
        with torch.inference_mode():
            d.finite(restored(torch.zeros(2, CONTEXT, 4)).numpy(), 2)
        refs.append(ref)
    return refs


def worker(root, market, scope_hash, phase, cpu_hash, path):
    started = time.monotonic()
    deadline = started + SECONDS[phase]
    result = failure(phase, scope_hash, "runtime_or_binding_failure")
    try:
        output, receipt, payload, parent_cpu, parent_cuda = verify(root, scope_hash)
        environment = h30.runtime_identity()
        require(
            environment
            == parent_cpu["runtime"]["environment"]
            == parent_cuda["runtime"]["environment"],
            "runtime_identity",
        )
        reference = json.loads((h30.run_directory(root, d.RUN) / "cpu-summary.json").read_bytes())
        require(
            h30.digest(h30.encode(reference)) == d.SUMMARY_HASHES["cpu"], "parent_summary_changed"
        )
        if phase == "cuda":
            raw = (output / "cpu-summary.json").read_bytes()
            require(h30.digest(raw) == cpu_hash, "cpu_summary_changed")
            reference = json.loads(raw)
            validate_result(reference, "cpu", scope_hash)
        torch, runtime = h30.configure_cuda() if phase == "cuda" else (None, {"backend": "cpu"})
        runtime = {**runtime, "environment": environment}
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=1):
            result, retained = compare(
                h30.load_streams(market, receipt, deadline),
                phase,
                reference,
                h30.EmergencyStore(Path(path).parent / "emergency.json"),
                deadline,
                torch=torch,
            )
        result.update(contract_sha256=scope_hash, cpu_summary_sha256=cpu_hash, runtime=runtime)
        validate_result(result, phase, scope_hash)
        if phase == "cpu":
            old = {h30.cell_key(c): c for c in reference["cells"]}
            require(all(c == old[h30.cell_key(c)] for c in result["cells"]), "cpu_control_changed")
        else:
            result["models"] = save_models(
                Path(path).parent / "models",
                retained,
                scope_hash,
                payload["source_pins"],
                runtime,
                torch,
                deadline,
            )
            result["retained_weights"] = True
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        h30.check_time(deadline)
    except h30.StudyFailure as error:
        reason = str(error)
        result = failure(
            phase,
            scope_hash,
            reason
            if reason
            in {
                "budget_exhausted",
                "contract_changed",
                "lineage_changed",
                "runtime_identity",
                "cpu_control_changed",
                "cpu_summary_changed",
                "parent_cohort_or_scaler_changed",
                "outcome_mask_changed",
                "training_support_shortfall",
                "evaluation_support_shortfall",
                "nonfinite_loss",
                "nonfinite_gradient",
                "nonfinite_parameter",
                "loss_parity",
                "no_first_update",
                "target_fee_replay_parity",
                "model_roundtrip",
            }
            else "study_invariant_failed",
        )
    except Exception:
        result = failure(phase, scope_hash, "runtime_or_binding_failure")
    with Path(path).open("xb") as handle:
        handle.write(h30.encode(result))
