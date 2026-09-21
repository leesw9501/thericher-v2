"""Fixed TRAIN-only inference appendix to the closed H30 development campaign."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as h30

RUN = "20260921-h30-r1"
NAME = "train-diagnostic-v1"
SECONDS = 600
H30_HASH = "sha256:be785361611db683afb3bd4bb80d245fc69e93fb90279e9ec8a1fafe459e22fe"
SUMMARY_HASHES = {
    "cpu": "sha256:06dc794bd575f42aa4079f5f7dac9a61d64f58659664a5587608a74c68b14142",
    "cuda": "sha256:4329cf2727bd8adeded60742507ce596be6b20e134e6639db61dd71bdb95d99e",
}
OWN_FILES = (
    "src/thericher_v2/research/firstrate_h30_train_diagnostic.py",
    "scripts/run_firstrate_h30_train_diagnostic.py",
)
TRAIN_FACTS = ("training_inputs", "training_outcomes", "train_blocks_36", "normalizer_sha256")
IDENTITY = ("symbol", "fold", "context", "seed")
SCOPE = {
    "appendix": NAME,
    "h30_contract_sha256": H30_HASH,
    "summary_sha256": SUMMARY_HASHES,
    "fits": "all16: SPY,QQQ / fold1,2 / context12,36 / seed101,103; no selection",
    "inputs": "per-fold TRAIN only; pinned loader/plan; pre-cutoff index; empty eval_times",
    "binding": "exact source/code/snapshot identities and saved TRAIN normalizer/counts",
    "cohort": "do not reproduce original train+eval cohort hash",
    "metrics": [
        "TRAIN standardized-target MSE: final,initial,train-mean (zero standardized prediction)",
        "all-parameter RMS(final-initial)",
        "TRAIN raw-bps prediction population std and negative/zero/positive fractions",
        "context36 final/initial: oldest24 normalized-to-zero; last12 unchanged; "
        "RMS prediction change bps and sign-decision disagreement fraction",
    ],
    "initialization": "same seed on CPU default generator before existing model factory",
    "runtime": "exact saved Python/numpy/sklearn/torch environment; CPU float32, one thread",
    "budget_seconds": SECONDS,
    "failure": "any binding/nonfinite/timeout failure discards all16 fit metrics; no retry",
    "strongest_kill_test": "any EVAL target/input construction, optimizer call, or identity drift",
    "optimizer_steps": 0,
    "gpu": False,
    "evaluation_predictions": False,
    "payoff": False,
    "promotion": False,
    "generalization_claim": False,
    "cross_device_bitwise_claim": False,
}


def contract():
    return {**SCOPE, "code_sha256": {p: h30.digest((h30.REPO / p).read_bytes()) for p in OWN_FILES}}


def fit_keys():
    return [
        (s, f, c, seed)
        for s in h30.SYMBOLS
        for f in (1, 2)
        for c in h30.CONTEXTS
        for seed in h30.SEEDS
    ]


def require(condition, reason):
    if not condition:
        raise h30.StudyFailure(reason)


def bindings(root):
    output, receipt = h30.verify_contract(root, RUN, H30_HASH)
    payload = json.loads((output / "contract.json").read_bytes())
    summaries = {}
    for phase, expected in SUMMARY_HASHES.items():
        raw = (output / f"{phase}-summary.json").read_bytes()
        require(h30.digest(raw) == expected, "summary_identity")
        metadata = json.loads(raw)
        summaries[phase] = {
            k: metadata[k]
            for k in (
                "status",
                "contract_sha256",
                "cpu_summary_sha256",
                "runtime",
                "folds",
                "models",
            )
            if k in metadata
        }
        require(
            summaries[phase]["status"] == "complete"
            and summaries[phase]["contract_sha256"] == H30_HASH,
            "summary_status",
        )
    cpu, cuda = summaries["cpu"], summaries["cuda"]
    require(cuda["cpu_summary_sha256"] == SUMMARY_HASHES["cpu"], "cpu_binding")
    refs = cuda["models"]
    require(
        len(refs) == 16 and {tuple(r[k] for k in IDENTITY) for r in refs} == set(fit_keys()),
        "model_matrix",
    )
    return output, receipt, payload, cpu, cuda


def prepare_train(symbol, number, bars, plan, expected):
    train_times, _, cutoff = plan
    # The loader verifies the whole snapshot; only pre-EVAL-history bars reach target code.
    index = {b.start_ts: b for b in bars if b.end_ts <= cutoff}
    fold = h30.prepare_fold(symbol, number, index, (train_times, (), cutoff))
    require(
        fold.facts["train_supported"] and len(fold.eval_x) == len(fold.evaluation) == 0,
        "train_geometry",
    )
    require(all(fold.facts[k] == expected[k] for k in TRAIN_FACTS), "train_binding")
    return fold


def bind_model(config, arrays, fold, payload):
    require(
        config["source_pins"] == payload["source_pins"]
        and config["normalizer_sha256"] == fold.facts["normalizer_sha256"],
        "model_train_binding",
    )
    expected = {
        "channel_mean": fold.channel_mean,
        "channel_scale": fold.channel_scale,
        "target_mean": np.asarray([fold.y_mean]),
        "target_scale": np.asarray([fold.y_scale]),
    }
    require(all(np.array_equal(arrays[k], v) for k, v in expected.items()), "model_scaler_binding")


def finite(values, count):
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    require(len(values) == count and np.isfinite(values).all(), "prediction_geometry")
    return values


def describe(predicted, fold):
    raw = predicted * fold.y_scale + fold.y_mean
    require(np.isfinite(raw).all(), "prediction_nonfinite")
    return {
        "std_bps": float(raw.std()),
        "negative_fraction": float(np.mean(raw < 0)),
        "zero_fraction": float(np.mean(raw == 0)),
        "positive_fraction": float(np.mean(raw > 0)),
    }


def measure(torch, fold, tensor, arrays, context, seed, deadline):
    h30.check_time(deadline)
    # Unlike torch.manual_seed, this seeds CPU initialization without touching CUDA RNGs.
    torch.random.default_generator.manual_seed(seed)
    model = h30.build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm",
        feature_count=4,
        hidden_size=16,
        attention_heads=1,
        tcn_kernel_size=3,
    )
    model.eval()
    initial = {"state." + k: v.detach().cpu().numpy().copy() for k, v in model.state_dict().items()}
    require(set(initial) == {k for k in arrays if k.startswith("state.")}, "state_geometry")
    x = tensor[:, -context:]
    masked = x.clone() if context == 36 else None
    if masked is not None:
        masked[:, :24] = 0
        require(torch.equal(masked[:, -12:], x[:, -12:]), "mask_tail_changed")
    predictions, sensitivity = {}, {}
    with torch.inference_mode():
        for label in ("initial", "final"):
            if label == "final":
                model.load_state_dict(
                    {k.removeprefix("state."): torch.from_numpy(arrays[k]) for k in initial},
                    strict=True,
                )
            values = finite(model(x).cpu().numpy(), len(fold.train_y))
            predictions[label] = values
            if masked is not None:
                changed = finite(model(masked).cpu().numpy(), len(values))
                sensitivity[label] = {
                    "rms_change_bps": float(
                        np.sqrt(np.mean((values - changed) ** 2)) * fold.y_scale
                    ),
                    "decision_disagreement_fraction": float(
                        np.mean(
                            (values * fold.y_scale + fold.y_mean > 0)
                            != (changed * fold.y_scale + fold.y_mean > 0)
                        )
                    ),
                }
            h30.check_time(deadline)
    squared = sum(
        float(np.sum((arrays[k].astype(np.float64) - v) ** 2)) for k, v in initial.items()
    )
    result = {
        "train_count": len(fold.train_y),
        "parameter_count": sum(v.size for v in initial.values()),
        "parameter_movement_rms": float(np.sqrt(squared / sum(v.size for v in initial.values()))),
        "train_mse_standardized": {
            k: float(np.mean((v - fold.train_y) ** 2)) for k, v in predictions.items()
        },
        "prediction_distribution": {k: describe(v, fold) for k, v in predictions.items()},
        "oldest24_mask": sensitivity if context == 36 else None,
    }
    result["train_mse_standardized"]["train_mean"] = float(
        np.mean(fold.train_y.astype(np.float64) ** 2)
    )
    h30.encode(result)  # Reject nonfinite aggregate metrics before any publication.
    return result


def diagnose(streams, output, payload, cpu, cuda, torch, deadline):
    expected = {(f["symbol"], f["fold"]): f for f in cpu["folds"]}
    require(len(expected) == len(cpu["folds"]) == 4, "fold_matrix")
    require(len(cuda["folds"]) == 4, "fold_matrix")
    for f in cuda["folds"]:
        require(
            all(f[k] == expected[(f["symbol"], f["fold"])][k] for k in TRAIN_FACTS), "fold_binding"
        )
    refs = {tuple(r[k] for k in IDENTITY): r for r in cuda["models"]}
    result, facts = [], []
    for symbol, bars in streams:
        for number, plan in enumerate(h30.plans(bars), 1):
            fold = prepare_train(symbol, number, bars, plan, expected[(symbol, number)])
            tensor = torch.tensor(fold.train_x, dtype=torch.float32, device="cpu")
            facts.append(
                {"symbol": symbol, "fold": number, **{k: fold.facts[k] for k in TRAIN_FACTS}}
            )
            for context in h30.CONTEXTS:
                for seed in h30.SEEDS:
                    h30.check_time(deadline)
                    ref = refs[(symbol, number, context, seed)]
                    config, arrays = h30.load_model_arrays(output / "models", ref, H30_HASH)
                    bind_model(config, arrays, fold, payload)
                    result.append(
                        {
                            **{k: ref[k] for k in IDENTITY},
                            "weights_sha256": ref["weights_sha256"],
                            "config_sha256": ref["config_sha256"],
                            **measure(torch, fold, tensor, arrays, context, seed, deadline),
                        }
                    )
    require([tuple(r[k] for k in IDENTITY) for r in result] == fit_keys(), "fit_matrix")
    return facts, result


def failure(scope_hash, reason):
    return {
        "status": "failed_all16",
        "reason": reason,
        "diagnostic_contract_sha256": scope_hash,
        "h30_contract_sha256": H30_HASH,
        "summary_sha256": SUMMARY_HASHES,
        "promotion": False,
        "generalization_claim": False,
        "fits": [],
        "unavailable_fits": 16,
    }


def worker(root, market, scope_hash, result_path):
    deadline = time.monotonic() + SECONDS
    result = failure(scope_hash, "runtime_or_binding_failure")
    try:
        scope = contract()
        require(h30.digest(h30.encode(scope)) == scope_hash, "diagnostic_contract_changed")
        output, receipt, payload, cpu, cuda = bindings(root)
        require(
            h30.runtime_identity()
            == cpu["runtime"]["environment"]
            == cuda["runtime"]["environment"],
            "runtime_identity",
        )
        import torch
        from threadpoolctl import threadpool_limits

        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        require(not torch.cuda.is_initialized(), "cuda_initialized")
        with threadpool_limits(limits=1):
            folds, fits = diagnose(
                h30.load_streams(market, receipt, deadline),
                output,
                payload,
                cpu,
                cuda,
                torch,
                deadline,
            )
        h30.check_time(deadline)
        require(not torch.cuda.is_initialized(), "cuda_initialized")
        result = {
            "status": "complete",
            "diagnostic_contract_sha256": scope_hash,
            "scope": scope,
            "normalization_sha256": payload["normalization_sha256"],
            "source_pins": payload["source_pins"],
            "runtime": cpu["runtime"]["environment"],
            "promotion": False,
            "generalization_claim": False,
            "gpu_used": False,
            "optimizer_steps": 0,
            "evaluation_access": False,
            "unavailable_fits": 0,
            "folds": folds,
            "fits": fits,
        }
    except h30.StudyFailure as error:
        result = failure(scope_hash, str(error))
    except Exception:
        pass  # Fail closed without private paths, data values, or partial model metrics.
    with Path(result_path).open("xb") as handle:
        handle.write(h30.encode(result))
