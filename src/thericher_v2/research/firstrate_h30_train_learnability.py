"""Four fixed TRAIN-only learnability fits; no evaluation or model retention."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_h30_train_diagnostic as d

h30, require = d.h30, d.require
NAME, SECONDS, UPDATES = "train-learnability-v1", 180, 256
CHECKPOINTS = (0, 1, 16, 64, 256)
KEYS = tuple((arm, seed) for arm in ("synthetic64", "spy_train16") for seed in h30.SEEDS)
DIAGNOSTIC_HASH = "sha256:d4334e56edc55368662c9a94ef0428a49365e6669102abc8f14730826311849f"
DIAGNOSTIC_SUMMARY = "sha256:8dac1484b6e67087004fe79f3d65c4927a7bedd05b779c99f74f9e39cc800034"
OWN_FILES = (
    "src/thericher_v2/research/firstrate_h30_train_learnability.py",
    "scripts/run_firstrate_h30_train_learnability.py",
)
FAILURES = frozenset(
    (
        "contract_changed",
        "diagnostic_code_changed",
        "diagnostic_summary_changed",
        "runtime_identity",
        "source_order",
        "subset_shortfall",
        "batch_geometry",
        "batch_nonfinite",
        "constant_batch_target",
        "missing_gradient",
        "nonfinite_gradient",
        "nonfinite_parameter",
        "nonfinite_movement",
        "loss_parity",
        "nonfinite_loss",
        "no_first_update",
        "budget_exhausted",
        "runtime_or_binding_failure",
        "worker_failed_or_timed_out",
        "execution_preempted",
    )
)


def contract():
    return {
        "name": NAME,
        "h30_contract_sha256": d.H30_HASH,
        "parent_summary_sha256": d.SUMMARY_HASHES,
        "diagnostic_contract_sha256": DIAGNOSTIC_HASH,
        "diagnostic_summary_sha256": DIAGNOSTIC_SUMMARY,
        "code_sha256": {p: h30.digest((h30.REPO / p).read_bytes()) for p in OWN_FILES},
        "fits": KEYS,
        "context": 12,
        "hidden_size": 16,
        "layers": 1,
        "synthetic": "NumPy default_rng(0) Gaussian (64,12,4); target last-bar channel0, z-scored",
        "real": "SPY fold1 first16 observed TRAIN rows in original chronological hash order; "
        "original full-TRAIN scalers; no backfill, new sort, or outcome filtering",
        "inputs": "pinned source loader/plan; cutoff-trimmed index and empty eval_times",
        "optimizer": "fresh AdamW lr=.001 weight_decay=.01 betas=(.9,.999) eps=1e-8; "
        "float32 MSE, full batch, no shuffle, no scheduler, no early stopping",
        "updates_per_fit": UPDATES,
        "total_updates": 1024,
        "checkpoints": CHECKPOINTS,
        "baseline": "each exact batch's target mean; report MSE and ratio, no selection",
        "strongest_kill": "independent fresh-forward NumPy MSE vs Torch loss rtol1e-5 atol1e-7; "
        "finite gradients/parameters/movement each update; nonzero first update",
        "synthetic_criterion": "final MSE <= .1*batch-mean MSE, independently for both seeds; "
        "miss is learnability_not_demonstrated, never evidence of a code bug",
        "budget_seconds": SECONDS,
        "cpu_threads": 1,
        "gpu_memory_cap_gib": 4,
        "failure": "timeout/nonfinite/parity/binding/preemption discards all4 metrics; "
        "no retry/fallback",
        "preemption": "existing exclusive GpuFileLock; main-owned SIGINT/SIGTERM reaps child",
        "runtime": "same pinned H30 environment; Torch2.7.0+cu128 CUDA12.8 CUBLAS=:4096:8",
        "artifact": f"research/{h30.FAMILY}/{NAME}/summary.json (sibling of closed r1)",
        "evidence_grade": "OUTCOME_INFORMED_SEEN_DATA_TRAIN_ONLY_DIAGNOSTIC",
        "evaluation_access": False,
        "payoff": False,
        "weights_retained": False,
        "promotion": False,
        "generalization_claim": False,
        "cross_runtime_bitwise_claim": False,
    }


def batches(streams, cpu):
    expected = next(f for f in cpu["folds"] if (f["symbol"], f["fold"]) == ("SPY", 1))
    symbol, bars = next(iter(streams))  # Original receipt order is SPY first; never load QQQ.
    require(symbol == "SPY", "source_order")
    fold = d.prepare_train(symbol, 1, bars, h30.plans(bars)[0], expected)
    require(len(fold.train_y) >= 16, "subset_shortfall")
    x = np.random.default_rng(0).normal(size=(64, 12, 4))
    y = x[:, -1, 0].copy()
    synthetic = (x.astype(np.float32), ((y - y.mean()) / y.std()).astype(np.float32))
    real = (np.array(fold.train_x[:16, -12:]), np.array(fold.train_y[:16]))
    facts = {k: fold.facts[k] for k in d.TRAIN_FACTS}
    facts["train_only_cohort_sha256"] = fold.facts["cohort_sha256"]
    facts["subset_order"] = "original observed TRAIN positions 0..15; no reordering"
    return (synthetic, real), facts


def batch_facts(x, y):
    require(x.shape == (len(y), 12, 4) and len(y) in (16, 64), "batch_geometry")
    require(np.isfinite(x).all() and np.isfinite(y).all(), "batch_nonfinite")
    baseline = float(np.mean((y.astype(np.float64) - y.mean(dtype=np.float64)) ** 2))
    require(baseline > 0, "constant_batch_target")
    pairs = [(i, j) for i in range(len(y)) for j in range(i) if np.array_equal(x[i], x[j])]
    return {
        "count": len(y),
        "ordered_batch_sha256": h30.digest(x.tobytes() + y.tobytes()),
        "mean_baseline_mse": baseline,
        "duplicate_input_pairs": len(pairs),
        "conflicting_target_pairs": int(sum(y[i] != y[j] for i, j in pairs)),
    }


def parameter_vector(torch, model, *, gradients=False):
    values = [p.grad if gradients else p.detach() for p in model.parameters()]
    require(all(v is not None for v in values), "missing_gradient")
    array = torch.cat([v.detach().reshape(-1) for v in values]).cpu().numpy().astype(np.float64)
    require(np.isfinite(array).all(), "nonfinite_gradient" if gradients else "nonfinite_parameter")
    return array


def rms(values):
    result = float(np.sqrt(np.mean(values**2)))
    require(np.isfinite(result), "nonfinite_movement")
    return result


def checkpoint(torch, model, x, y, baseline):
    model.eval()
    with torch.inference_mode():
        predicted = d.finite(model(x).cpu().numpy(), len(y))
    mse = float(np.mean((predicted - y.detach().cpu().numpy().astype(np.float64)) ** 2))
    model.train()
    with torch.no_grad():
        loss = float(torch.nn.functional.mse_loss(model(x).flatten(), y).item())
    require(np.isfinite(mse) and np.isclose(mse, loss, rtol=1e-5, atol=1e-7), "loss_parity")
    return {"mse": mse, "mean_baseline_ratio": mse / baseline}


def fit(torch, x, y, arm, seed, baseline, deadline):
    torch.random.default_generator.manual_seed(seed)
    if x.is_cuda:
        torch.cuda.manual_seed_all(seed)
    model = h30.build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm",
        feature_count=4,
        hidden_size=16,
        attention_heads=1,
        tcn_kernel_size=3,
    ).to(x.device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=0.001,
        weight_decay=0.01,
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    initial = previous = parameter_vector(torch, model)
    metrics = [{"update": 0, **checkpoint(torch, model, x, y, baseline)}]
    for update in range(1, UPDATES + 1):
        h30.check_time(deadline)
        optimizer.zero_grad(set_to_none=True)
        loss = torch.nn.functional.mse_loss(model(x).flatten(), y)
        require(bool(torch.isfinite(loss).item()), "nonfinite_loss")
        loss.backward()
        gradient = rms(parameter_vector(torch, model, gradients=True))
        optimizer.step()
        current = parameter_vector(torch, model)
        movement, step = rms(current - initial), rms(current - previous)
        require(update != 1 or step > 0, "no_first_update")
        previous = current
        if update in CHECKPOINTS:
            metrics.append(
                {
                    "update": update,
                    **checkpoint(torch, model, x, y, baseline),
                    "gradient_rms": gradient,
                    "step_rms": step,
                    "movement_rms": movement,
                }
            )
        h30.check_time(deadline)
    return {
        "arm": arm,
        "seed": seed,
        "updates": UPDATES,
        "checkpoints": metrics,
        "classification": (
            "learnability_demonstrated"
            if metrics[-1]["mean_baseline_ratio"] <= 0.1
            else "learnability_not_demonstrated"
        )
        if arm == "synthetic64"
        else "train_capacity_measurement_only",
    }


def failure(scope_hash, reason):
    return {
        "status": "failed_all4",
        "reason": reason if reason in FAILURES else "runtime_or_binding_failure",
        "contract_sha256": scope_hash,
        "fits": [],
        "unavailable_fits": 4,
        "evaluation_access": False,
        "promotion": False,
        "generalization_claim": False,
    }


def worker(root, market, scope_hash, result_path):
    started = time.monotonic()
    deadline = started + SECONDS
    result = failure(scope_hash, "runtime_or_binding_failure")
    try:
        scope = contract()
        require(h30.digest(h30.encode(scope)) == scope_hash, "contract_changed")
        require(h30.digest(h30.encode(d.contract())) == DIAGNOSTIC_HASH, "diagnostic_code_changed")
        output, receipt, payload, cpu, cuda = d.bindings(root)
        require(
            h30.digest((output / d.NAME / "summary.json").read_bytes()) == DIAGNOSTIC_SUMMARY,
            "diagnostic_summary_changed",
        )
        require(
            h30.runtime_identity()
            == cpu["runtime"]["environment"]
            == cuda["runtime"]["environment"],
            "runtime_identity",
        )
        data, train_facts = batches(h30.load_streams(market, receipt, deadline), cpu)
        facts = [batch_facts(x, y) for x, y in data]
        torch, runtime = h30.configure_cuda()
        from threadpoolctl import threadpool_limits

        tensors = [
            (torch.tensor(x, device="cuda:0"), torch.tensor(y, device="cuda:0")) for x, y in data
        ]
        with threadpool_limits(limits=1):
            fits = [
                fit(
                    torch, *tensors[i // 2], arm, seed, facts[i // 2]["mean_baseline_mse"], deadline
                )
                for i, (arm, seed) in enumerate(KEYS)
            ]
        result = {
            "status": "complete",
            "contract_sha256": scope_hash,
            "contract": scope,
            "source_pins": payload["source_pins"],
            "normalization_sha256": payload["normalization_sha256"],
            "runtime": {**runtime, "environment": h30.runtime_identity()},
            "train": train_facts,
            "batches": facts,
            "fits": fits,
            "unavailable_fits": 0,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "evaluation_access": False,
            "promotion": False,
            "generalization_claim": False,
        }
        h30.check_time(deadline)
    except h30.StudyFailure as error:
        result = failure(scope_hash, str(error))
    except Exception:
        pass  # No raw exceptions, source values, or partial fits escape the worker.
    with Path(result_path).open("xb") as handle:
        handle.write(h30.encode(result))
