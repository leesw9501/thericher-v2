"""One frozen nominal-cost abstention comparison on all eight retained H30 models."""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_h30_full_cohort as parent

h30, d, require = parent.h30, parent.d, parent.require
NAME, SECONDS, HURDLE_BPS = "fixed-nominal-hurdle-v1", 300, 6.0
PARENT_HASH = "sha256:d7cceb5ab3642d2a727bc8f0f73ac3ee58a3b1393b196a553e057391c1ece596"
SUMMARY_HASHES = {
    "cpu": "sha256:5d8ecd2cf2e170a35b6115f8deda05c16f3d09736d42e433824e1d9071c50b3b",
    "cuda": "sha256:4b26bfffb377be6462ac56346526f5089dc6214d800a8b0e8491662fc6f15237",
}
OWN_FILES = (
    "src/thericher_v2/research/firstrate_h30_fixed_hurdle.py",
    "scripts/run_firstrate_h30_fixed_hurdle.py",
    "tests/test_firstrate_h30_fixed_hurdle.py",
)
INHERITED = (
    "evidence_grade",
    "source_pins",
    "normalization_sha256",
    "contexts",
    "seeds",
    "features",
    "target",
    "rounding",
    "schedule",
    "quantity",
    "roundtrip_cash",
    "cost_bps_per_side",
    "slippage_bps",
    "split",
    "purge",
    "sampling",
    "sample_caps",
    "eligibility",
    "censoring",
    "minimums",
    "effective_sample",
    "naives",
    "limitations",
    "model_format",
    "model_use",
    "image_sha256",
)


def bindings(root):
    output, receipt, *_ = parent.verify(root, PARENT_HASH)
    payload = json.loads((output / "contract.json").read_bytes())
    summaries = {}
    for phase, expected in SUMMARY_HASHES.items():
        raw = (output / f"{phase}-summary.json").read_bytes()
        require(h30.digest(raw) == expected, "parent_summary_changed")
        summaries[phase] = json.loads(raw)
        parent.validate_result(summaries[phase], phase, PARENT_HASH)
    refs = summaries["cuda"]["models"]
    require([tuple(r[k] for k in d.IDENTITY) for r in refs] == list(parent.KEYS), "model_matrix")
    for ref in refs:
        parent.load_model(output / "models", ref, PARENT_HASH)
    return output, receipt, payload, summaries["cpu"], summaries["cuda"]


def contract(payload, references):
    return {
        **{k: payload[k] for k in INHERITED},
        "family": h30.FAMILY,
        "name": NAME,
        "parent_contract_sha256": PARENT_HASH,
        "parent_summary_sha256": SUMMARY_HASHES,
        "models": references,
        "code_sha256": {
            **payload["code_sha256"],
            **{p: h30.digest((h30.REPO / p).read_bytes()) for p in OWN_FILES},
        },
        "scalers": "exact retained TRAIN scalers; recompute only to verify identity, no fitting",
        "decision": {
            "sign_only": "predicted_standardized * saved_target_scale + saved_target_mean > 0",
            "fixed_nominal_hurdle": "same inverse-transform > 6 gross return bps; equality flat",
            "hurdle_bps": HURDLE_BPS,
            "reference_cost_bps_per_side": 3,
            "cost_sensitivity": "same 6bps hurdle at 1/3/5bps, not a cost-matched sweep",
            "exact_breakeven_claim": False,
            "fee_alignment": "nominal 2*3bps; unrounded exit-notional breakeven is "
            "6/(1-0.0003) bps; actual per-side 0.0001-dollar rounding is price-dependent; "
            "no realized or future price enters the decision",
        },
        "matrix": {"models": 8, "folds": 4, "model_cells": 48, "naive_cells": 36},
        "comparators": "prior sign-only plus all3 matched-cadence naives; no Ridge refit",
        "reproduction": "all24 prior sign and all36 naive aggregate replay cells exactly equal",
        "strongest_kill_test": "any source/model/scaler/cohort/mask drift, premature censoring, "
        "prior sign/control mismatch or target/fee/fill/cash/FIFO replay mismatch fails ALL84",
        "report": "all84 cells; eligible/scored/censored intents, trades, gross/fees/net, "
        "paired sign and naive net deltas; no row-level data/predictions or winner",
        "budget": {"cpu_seconds": SECONDS, "parent_wall_seconds": SECONDS, "cpu_threads": 1},
        "runtime": "same pinned image/environment; CPU-only Torch inference; no CUDA init",
        "review": {
            "verdict": "supported-with-limits",
            "mode": "Claude supplied-facts-only, tools disabled, before contract/outcomes",
            "resolution": "nominal hurdle, not exact breakeven; 1/5bps are sensitivity only. "
            "Retain one hurdle: no suggested 2/6/10 arm or multiplicity-adjusted inference. "
            "All8 models, inverse TRAIN scaling, signal-before-censor and exact replay mandatory. "
            "Any gain is descriptive outcome-informed development, not independent skill.",
        },
        "optimizer_steps": 0,
        "gpu": False,
        "model_selection": False,
        "threshold_search": False,
        "holdout_access": False,
        "promotion": False,
        "generalization_claim": False,
        "retries": False,
        "fallback": False,
        "retained_new_weights": False,
    }


def freeze(root):
    _, _, payload, _, cuda = bindings(root)
    scope = contract(payload, cuda["models"])
    output = h30.run_directory(root, NAME)
    output.mkdir(parents=True, exist_ok=True)  # Docker may precreate this empty writable mount.
    require(not any(output.iterdir()), "output_namespace_used")
    raw = h30.encode(scope)
    with (output / "contract.json").open("xb") as handle:
        handle.write(raw)
    h30.register_frozen_campaign(
        contract_hash=h30.digest(raw),
        dataset_hash=h30.digest(h30.encode(scope["source_pins"])),
        split_hash=h30.digest(h30.encode([scope[k] for k in ("split", "purge", "sampling")])),
        cost_model_hash=h30.digest(h30.encode([h30.COSTS, "fees_only", "independent_one_share"])),
        trial_family=h30.FAMILY,
        holdout_access="none",
        artifact_root=root,
        repo_root=h30.REPO,
    )
    return h30.digest(raw)


def verify(root, scope_hash):
    bound = bindings(root)
    raw = (h30.run_directory(root, NAME) / "contract.json").read_bytes()
    require(
        h30.digest(raw) == scope_hash and raw == h30.encode(contract(bound[2], bound[4]["models"])),
        "contract_changed",
    )
    return bound


def decisions(standardized, mean, scale, count):
    require(np.isfinite(mean) and np.isfinite(scale) and scale > 0, "target_scaler")
    raw_bps = d.finite(standardized, count) * scale + mean
    require(np.isfinite(raw_bps).all(), "prediction_nonfinite")
    return tuple(bool(v > 0) for v in raw_bps), tuple(bool(v > HURDLE_BPS) for v in raw_bps)


def predict(torch, arrays, features):
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
        return d.finite(model(torch.tensor(features[:, -12:], device="cpu")).numpy(), len(features))


def expected_keys():
    candidates = [(n, 12, seed) for n in ("lstm_sign", "lstm_hurdle") for seed in h30.SEEDS]
    candidates += [(n, None, None) for n in h30.NAIVES]
    return [
        (s, f, n, c, seed, cost)
        for s in h30.SYMBOLS
        for f in (1, 2)
        for n, c, seed in candidates
        for cost in h30.COSTS
    ]


def reproduce(cells, cpu, cuda):
    old = {h30.cell_key(c): c for c in cpu["cells"] + cuda["cells"]}
    for cell in cells:
        if cell["candidate"] == "lstm_hurdle":
            continue
        original = {
            **cell,
            "candidate": "lstm" if cell["candidate"] == "lstm_sign" else cell["candidate"],
        }
        prior = old[h30.cell_key(original)]
        require(
            original
            == {k: v for k, v in prior.items() if k != "matched_baseline_delta_net_dollars"},
            "prior_replay_changed",
        )


def compare(streams, output, payload, cpu, cuda, torch, emergency, deadline):
    result = {**h30.result_base("cpu"), "name": NAME, "models": cuda["models"]}
    refs = {tuple(r[k] for k in d.IDENTITY): r for r in cuda["models"]}
    expected = [(s, f) for s in h30.SYMBOLS for f in (1, 2)]
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        for number, plan in enumerate(h30.plans(bars), 1):
            h30.check_time(deadline)
            require(
                len(result["folds"]) < 4 and (symbol, number) == expected[len(result["folds"])],
                "fold_matrix",
            )
            fold = h30.prepare_fold(symbol, number, index, plan)
            prior = next(f for f in cuda["folds"] if (f["symbol"], f["fold"]) == (symbol, number))
            require(fold.facts["train_supported"], "training_support_shortfall")
            require(
                all(
                    fold.facts[k] == prior[k]
                    for k in (*d.TRAIN_FACTS, "cohort_sha256", "evaluation_inputs")
                ),
                "cohort_or_scaler_changed",
            )
            signals = {}
            for seed in h30.SEEDS:
                h30.check_time(deadline)
                ref = refs[(symbol, number, 12, seed)]
                config, arrays = parent.load_model(output / "models", ref, PARENT_HASH)
                d.bind_model(config, arrays, fold, payload)
                require(config["cohort_sha256"] == fold.facts["cohort_sha256"], "model_cohort")
                sign, hurdle = decisions(
                    predict(torch, arrays, fold.eval_x),
                    arrays["target_mean"][0],
                    arrays["target_scale"][0],
                    len(fold.evaluation),
                )
                signals[("lstm_sign", 12, seed)] = sign
                signals[("lstm_hurdle", 12, seed)] = hurdle
            signals.update(
                {
                    ("always_flat", None, None): (False,) * len(fold.evaluation),
                    ("always_long", None, None): (True,) * len(fold.evaluation),
                    ("previous_bar_direction", None, None): tuple(
                        o.signal.close > o.signal.open for o in fold.evaluation
                    ),
                }
            )
            # Score attaches future outcomes only after every model/control decision is fixed.
            facts, cells = h30.score(fold, index, signals, emergency, deadline)
            require(cells is not None, "evaluation_support_shortfall")
            require(facts == prior, "outcome_mask_or_fold_changed")
            reproduce(cells, cpu, cuda)
            lookup = {h30.cell_key(c): c for c in cells}
            for cell in cells:
                if cell["candidate"] not in ("lstm_sign", "lstm_hurdle"):
                    continue
                cell["matched_delta_net_dollars"] = {}
                for name in (*h30.NAIVES, "lstm_sign"):
                    key = (
                        symbol,
                        number,
                        name,
                        12 if name == "lstm_sign" else None,
                        cell["seed"] if name == "lstm_sign" else None,
                        cell["cost_bps_per_side"],
                    )
                    cell["matched_delta_net_dollars"][name] = str(
                        Decimal(cell["net_dollars"]) - Decimal(lookup[key]["net_dollars"])
                    )
            result["folds"].append(facts)
            result["cells"].extend(cells)
    require([(f["symbol"], f["fold"]) for f in result["folds"]] == expected, "fold_matrix")
    return {**result, "status": "complete", "prior_replay_cells_reproduced": 60}


def validate_result(result, scope_hash):
    require(
        result.get("status") == "complete"
        and result.get("name") == NAME
        and result.get("contract_sha256") == scope_hash,
        "worker_identity",
    )
    cells = result["cells"]
    require(
        len(cells) == 84
        and {h30.cell_key(c) for c in cells} == set(expected_keys())
        and all(
            c["status"] == "complete" and c["parity_verified"] and c["terminal_flat"] for c in cells
        ),
        "cell_matrix",
    )
    require(
        [tuple(r[k] for k in d.IDENTITY) for r in result["models"]] == list(parent.KEYS),
        "model_matrix",
    )


def failure(scope_hash, reason):
    return {
        **h30.result_base("cpu"),
        "name": NAME,
        "status": "failed_all84",
        "contract_sha256": scope_hash,
        "reason": reason,
        "models": [],
        "unavailable_cells": 84,
        "optimizer_steps": 0,
        "gpu_used": False,
    }


def cpu_limit():
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (SECONDS, SECONDS))


def worker(root, market, scope_hash, path):
    started, cpu_started = time.monotonic(), time.process_time()
    deadline = started + SECONDS
    result = failure(scope_hash, "runtime_or_binding_failure")
    try:
        cpu_limit()
        output, receipt, payload, cpu, cuda = verify(root, scope_hash)
        environment = h30.runtime_identity()
        require(
            environment == cpu["runtime"]["environment"] == cuda["runtime"]["environment"],
            "runtime_identity",
        )
        import torch
        from threadpoolctl import threadpool_limits

        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        require(not torch.cuda.is_initialized(), "cuda_initialized")
        with threadpool_limits(limits=1):
            result = compare(
                h30.load_streams(market, receipt, deadline),
                output,
                payload,
                cpu,
                cuda,
                torch,
                h30.EmergencyStore(Path(path).parent / "emergency.json"),
                deadline,
            )
        verify(root, scope_hash)
        require(not torch.cuda.is_initialized(), "cuda_initialized")
        result.update(
            contract_sha256=scope_hash,
            parent_contract_sha256=PARENT_HASH,
            runtime=environment,
            optimizer_steps=0,
            gpu_used=False,
            elapsed_seconds=round(time.monotonic() - started, 3),
            cpu_seconds=round(time.process_time() - cpu_started, 3),
        )
        validate_result(result, scope_hash)
        h30.check_time(deadline)
    except h30.StudyFailure as error:
        result = failure(scope_hash, str(error))
    except Exception:
        result = failure(scope_hash, "runtime_or_binding_failure")
    with Path(path).open("xb") as handle:
        handle.write(h30.encode(result))
