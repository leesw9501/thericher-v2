"""Finite seen-data Hedge-style adaptation; not BOA, a holdout or Paper input."""

from __future__ import annotations

import json
import socket
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.data.tiingo_adjusted_etf_daily import _unlinked_path
from thericher_v2.research import causal_expert_mixture as mixture
from thericher_v2.research import tiingo_monthly_momentum_development as momentum
from thericher_v2.research import tiingo_monthly_net_utility_development as fitted

h, base = fitted.monthly, fitted.base
NAME = "tiingo-causal-expert-mixture-development-v1"
REPO, SYMBOLS, PERIODS, COSTS = fitted.REPO, fitted.SYMBOLS, fitted.PERIODS, fitted.COSTS
SECONDS, MEMORY_BYTES = 900, 6 * 1024**3
EXPERTS = ("linear", "lstm", "abs_momentum", "momentum_train_risk_matched")
POLICIES = (*EXPERTS, "fixed_blend", "online_mixture", "cash", "always_long")
METRICS = (*h.METRICS[:5], "net_utility")
FAILURE_STAGES = ("cpu_smoke", "load", "prepare", "fit", "inference", "evaluate", "validate")
CODE = tuple(
    dict.fromkeys(
        (
            *fitted.CODE,
            *momentum.CODE,
            "src/thericher_v2/research/causal_expert_mixture.py",
            "src/thericher_v2/research/tiingo_causal_expert_mixture_development.py",
            "src/thericher_v2/research/campaign_registry.py",
            "scripts/run_tiingo_causal_expert_mixture_development.py",
            "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py",
        )
    )
)
encode, digest, require, atomic_new = (
    fitted.encode,
    fitted.digest,
    fitted.require,
    fitted.atomic_new,
)


def configuration():
    recipe = fitted.configuration()
    return dict(
        symbols=list(SYMBOLS),
        train=list(fitted.TRAIN),
        periods=[list(p) for p in PERIODS],
        experts=list(EXPERTS),
        policies=list(POLICIES),
        cells=144,
        fits=2,
        feature=recipe["feature"],
        models=recipe["models"],
        optimizer=recipe["optimizer"],
        objective=recipe["objective"],
        train_cost_per_side_bps="10",
        momentum=momentum.configuration()["signal"],
        risk_constant=dict(
            train=list(fitted.TRAIN),
            formula=(
                "min(1,sqrt(population variance(zero-fee TRAIN momentum daily NAV returns)/"
                "population variance(zero-fee TRAIN passive daily NAV returns))); "
                "zero passive variance -> unavailable; zero numerator ->0"
            ),
        ),
        mixture=dict(
            rate=0.1,
            initialization="uniform at each fold OPEN; no TRAIN feedback",
            loss="negative natural log consecutive month-end continuous expert NAV growth",
            feedback_cost_per_side_bps="10",
            feedback="previous completed month only, once",
            availability="NYSE scheduled month-final CLOSE UTC, strictly before next OPEN UTC",
            reset="only at original fold boundaries; no cross-fold feedback/capital",
            actions="same online coefficients/targets across all scoring costs",
        ),
        costs_per_side_bps=list(COSTS),
        timing=recipe["timing"],
        kills=dict(
            primary="mean of six online-minus-fixed-blend final NAV deltas at10bps <=0",
            controls="mean stress NAV deltas versus cash and momentum TRAIN risk constant",
            leave_one_etf_out="three four-pair stress mean deltas, descriptive; no refit/selection",
        ),
        budget=dict(
            wall_seconds=SECONDS,
            cpu_threads=2,
            memory_bytes=MEMORY_BYTES,
            gpu=True,
            attempts=1,
            pooled_fits=2,
            maximum_replays=150,
            cpu_smoke_wall_seconds=120,
        ),
        image=recipe["image"],
        scope=recipe["scope"],
        selection=False,
        holdout_access="none",
        weights_retained=True,
        weights="numeric float32 NPZ; existing strict hash/schema/link/no-pickle reader",
        action_reconstruction_atol="0.000001",
        lineage="fresh exact-recipe fits with current source pins, not old weight identity",
        reference="https://arxiv.org/abs/2111.15365v4; concept-only Hedge adaptation, not BOA",
        limitations=[
            "revised non-PIT surviving ETFs; comparison periods already seen",
            "analytical CLOSE availability assumption, not provider PIT evidence",
            "prequential adaptation uses prior comparison outcomes; not frozen-output validation",
            "separate sleeves, not a portfolio; mixed NAV is never averaged expert NAV",
            "no broker parity, strategy selection, holdout or Paper qualification",
        ],
    )


def calendar():
    require(fitted.runtime_versions()["pandas-market-calendars"] == "5.4.0", "calendar_version")
    import pandas_market_calendars as calendars

    schedule = calendars.get_calendar("NYSE").schedule(
        start_date="2000-12-01", end_date="2026-08-03"
    )
    return [t.date().isoformat() for t in schedule.index], {
        t.date().isoformat(): (row.market_open.isoformat(), row.market_close.isoformat())
        for t, row in schedule.iterrows()
    }


def build_plan(days, clocks):
    plan = fitted.build_plan(days)
    # Momentum needs no following-month bracket; its existing calendar stops in July.
    plan["momentum"] = momentum.build_plan([d for d in days if d <= "2026-07-31"])
    require(plan["train"]["bounds"] == plan["momentum"]["train"]["bounds"], "TRAIN_cohort")
    plan["clocks"] = []
    for segment, rule in zip(plan["periods"], plan["momentum"]["periods"], strict=True):
        require(segment["bounds"] == rule["bounds"], "expert_cohort")
        points = []
        for month, decision in zip(segment["months"], rule["decisions"], strict=True):
            a, b = month["bounds"]
            require(a == decision["index"], "expert_decision")
            opening, closing = clocks[days[a]][0], clocks[days[b - 1]][1]
            for value in (opening, closing):
                mixture._utc(datetime.fromisoformat(value), "calendar")
            require(
                datetime.fromisoformat(opening).date().isoformat() == days[a]
                and datetime.fromisoformat(closing).date().isoformat() == days[b - 1]
                and opening < closing,
                "calendar_clock",
            )
            points.append([opening, closing])
        require(
            all(
                datetime.fromisoformat(a[1]) < datetime.fromisoformat(b[0])
                for a, b in zip(points, points[1:], strict=False)
            ),
            "calendar_chronology",
        )
        plan["clocks"].append(points)
    return plan


def proposed_contract():
    days, clocks = calendar()
    return dict(
        name=NAME,
        config=configuration(),
        source=h.source_identity(),
        plan=build_plan(days, clocks),
        runtime=fitted.runtime_versions(),
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def _read(path):
    _unlinked_path(path)
    return fitted._read(path)


def read_json(path, pin=None):
    raw = _read(path)
    require(pin is None or (fitted._hash(pin) and digest(raw) == pin), "file_binding")
    value = json.loads(raw)
    require(raw == encode(value), "canonical_json_required")
    return value, digest(raw)


def register_contract(root, contract, pin):
    require(digest(encode(contract)) == pin, "contract_binding")
    base.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=digest(encode(contract["source"])),
        split_hash=digest(encode(contract["plan"])),
        cost_model_hash=digest(encode(COSTS)),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifacts, market):
    runtime_constraints()
    base.verify_metadata(artifacts, market)
    contract = proposed_contract()
    root = base.ensure_external_artifact_directory(artifacts, REPO, "research") / NAME
    root.mkdir()
    atomic_new(root / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifacts, contract, pin)
    return pin


def verify(artifacts, market, pin):
    root = base.ensure_external_artifact_directory(artifacts, REPO, "research", NAME)
    contract, _ = read_json(root / "precommit.json", pin)
    require(contract == proposed_contract(), "source_config_calendar_runtime_changed")
    base.verify_metadata(artifacts, market)
    return root, contract


@h._decimal
def feedback_loss(start_nav, end_nav):
    require(
        all(type(v) is Decimal and v.is_finite() and v > 0 for v in (start_nav, end_nav)),
        "feedback_NAV",
    )
    loss = float(start_nav.ln() - end_nav.ln())
    require(np.isfinite(loss), "feedback_loss")
    return loss


def online_targets(targets, losses, clocks):
    require(
        type(targets) is np.ndarray
        and targets.dtype == np.dtype("float64")
        and targets.ndim == 2
        and targets.shape[1] == 4
        and len(targets) > 0,
        "expert_shape",
    )
    require(
        type(losses) is np.ndarray
        and losses.dtype == np.dtype("float64")
        and losses.shape == targets.shape
        and len(clocks) == len(targets),
        "feedback_shape",
    )
    weights, watermark, actions = None, None, []
    for i, (opening, closing) in enumerate(clocks):
        decision, completed = datetime.fromisoformat(opening), datetime.fromisoformat(closing)
        mixture._utc(decision, "decision")
        mixture._utc(completed, "completed")
        require(decision < completed, "month_clock")
        if i:
            available = datetime.fromisoformat(clocks[i - 1][1])
            weights = mixture.update_weights(
                losses[i - 1],
                weights,
                rate=0.1,
                completed_loss_available_at=available,
                decision_at=decision,
                last_feedback_at=watermark,
            )
            watermark = available
        actions.append(mixture.project_target(targets[i], weights))
    return np.array(actions, dtype=np.float64)


def month_losses(traces, segment):
    require(
        len(traces) == 4
        and all(len(nav) == segment["bounds"][1] - segment["bounds"][0] for nav in traces),
        "expert_trace_count",
    )
    start = segment["bounds"][0]
    result = []
    for _, stop in (m["bounds"] for m in segment["months"]):
        previous_stop = start if not result else segment["months"][len(result) - 1]["bounds"][1]
        result.append(
            [
                feedback_loss(
                    Decimal(1) if previous_stop == start else nav[previous_stop - start - 1],
                    nav[stop - start - 1],
                )
                for nav in traces
            ]
        )
    return np.array(result, dtype=np.float64)


@h._decimal
def paired_facts(cells):
    index = {(c["symbol"], c["period"], c["cost_per_side_bps"], c["policy"]): c for c in cells}
    differences = {
        p: [
            (
                s,
                Decimal(index[s, period, "10", "online_mixture"]["final_nav"])
                - Decimal(index[s, period, "10", p]["final_nav"]),
            )
            for s in SYMBOLS
            for period, *_ in PERIODS
        ]
        for p in ("fixed_blend", "cash", "momentum_train_risk_matched")
    }

    def mean(values):
        return sum(values, Decimal(0)) / len(values)

    primary = mean([v for _, v in differences["fixed_blend"]])
    return dict(
        mean_stress_nav_delta=h.number(primary),
        kill_applied=primary <= 0,
        control_deltas={
            p: h.number(mean([v for _, v in values])) for p, values in differences.items()
        },
        leave_one_etf_out={
            s: h.number(mean([v for symbol, v in differences["fixed_blend"] if symbol != s]))
            for s in SYMBOLS
        },
    )


def evaluate(prepared, plan, predictions, risks, *, deadline):
    cells, groups = [], []
    for symbol in SYMBOLS:
        for segment, rule, clocks in zip(
            plan["periods"], plan["momentum"]["periods"], plan["clocks"], strict=True
        ):
            rows, days, bounds = (
                prepared[symbol, segment["period"]]["rows"],
                plan["days"],
                segment["bounds"],
            )
            count = len(segment["months"])
            vectors = [predictions[a, symbol, segment["period"]] for a in fitted.ARCHITECTURES]
            require(all(v.shape == (count,) for v in vectors), "prediction_shape")
            rule_actions = momentum.targets(rows, rule)
            require(
                all(v is not None for v in rule_actions.values()) and risks[symbol] is not None,
                "expert_input_unavailable",
            )
            targets = np.column_stack(
                (
                    *vectors,
                    [float(v) for v in rule_actions.values()],
                    np.full(count, float(risks[symbol])),
                )
            ).astype(np.float64)
            actions = {p: fitted._actions(segment, targets[:, k]) for k, p in enumerate(EXPERTS)}
            stress = {
                p: h.replay(rows, days, bounds, actions[p], "10", deadline=deadline)
                for p in EXPERTS
            }
            online = online_targets(
                targets, month_losses([stress[p]["navs"] for p in EXPERTS], segment), clocks
            )
            actions.update(
                fixed_blend=fitted._actions(segment, targets.mean(axis=1)),
                online_mixture=fitted._actions(segment, online),
                cash=fitted._actions(segment, np.zeros(count)),
                always_long=fitted._actions(segment, np.ones(count)),
            )
            groups.append(
                dict(
                    symbol=symbol,
                    period=segment["period"],
                    months=count,
                    feedback_updates=count - 1,
                    risk_sha256=digest(encode(str(risks[symbol]))),
                )
            )
            for cost in COSTS:
                for policy in POLICIES:
                    replay = (
                        stress[policy]
                        if cost == "10" and policy in EXPERTS
                        else h.replay(rows, days, bounds, actions[policy], cost, deadline=deadline)
                    )
                    cells.append(
                        dict(
                            symbol=symbol,
                            period=segment["period"],
                            cost_per_side_bps=cost,
                            policy=policy,
                            trades=replay["trades"],
                            action_sha256=digest(
                                encode(
                                    [
                                        (days[i], str(w.normalize()))
                                        for i, w in actions[policy].items()
                                    ]
                                )
                            ),
                            **{m: h.number(replay[m]) for m in METRICS[:-1]},
                            net_utility=h.number(
                                Decimal(
                                    str(
                                        fitted.math.numpy_net_utility(
                                            np.array([float(v) for v in replay["navs"]])
                                        )
                                    )
                                )
                            ),
                        )
                    )
    return groups, cells


def result_base(
    pin, phase, *, status="failed", counts=None, smoked=False, runtime=None, failure_stage=None
):
    counts = counts or dict(fits_started=None, fits_completed=None)
    return dict(
        name=NAME,
        contract_sha256=pin,
        phase=phase,
        status=status,
        **counts,
        cpu_smoke_passed=smoked,
        failure_stage=failure_stage,
        runtime=runtime,
        models=[],
        groups=[],
        cells=[],
        paired=None,
    )


def validate_result(result, contract, pin):
    require(contract["name"] == NAME and digest(encode(contract)) == pin, "contract_binding")
    fitted._fields(result, result_base(pin, "cuda"))
    require(result["name"] == NAME and result["contract_sha256"] == pin, "result_binding")
    require(
        result["phase"] in {"cuda", "cpu-smoke"} and type(result["cpu_smoke_passed"]) is bool,
        "result_phase",
    )
    require(
        result["failure_stage"] is None
        or (type(result["failure_stage"]) is str and result["failure_stage"] in FAILURE_STAGES),
        "failure_stage",
    )
    require(all(type(result[k]) is list for k in ("models", "groups", "cells")), "result_lists")
    for key in ("fits_started", "fits_completed"):
        require(
            result[key] is None or (type(result[key]) is int and 0 <= result[key] <= 2), "fit_count"
        )
    require(
        result["fits_completed"] is None
        or (
            result["fits_started"] is not None
            and result["fits_completed"] <= result["fits_started"]
        ),
        "fit_order",
    )
    if result["status"] != "complete":
        require(
            result["status"] in {"failed", "input_unavailable", "cpu_smoke_complete"}
            and result["models"] == result["groups"] == result["cells"] == []
            and result["paired"] is None
            and result["runtime"] is None,
            "incomplete_scores",
        )
        if result["status"] != "failed":
            require(result["fits_started"] == result["fits_completed"] == 0, "no_fit_phase")
        if result["status"] == "input_unavailable":
            require(
                result["phase"] == "cuda"
                and result["cpu_smoke_passed"]
                and result["failure_stage"] == "prepare",
                "input_unavailable_stage",
            )
        if result["status"] == "cpu_smoke_complete":
            require(
                result["phase"] == "cpu-smoke"
                and result["cpu_smoke_passed"]
                and result["failure_stage"] is None
                and result["runtime"] is None,
                "smoke_result",
            )
        return
    require(
        result["phase"] == "cuda"
        and result["cpu_smoke_passed"]
        and result["failure_stage"] is None
        and result["fits_started"] == result["fits_completed"] == 2,
        "complete_fit_count",
    )
    fitted._runtime(result["runtime"], contract)
    require(len(result["models"]) == 2, "models")
    for model, architecture in zip(result["models"], fitted.ARCHITECTURES, strict=True):
        fitted._fields(
            model, ("architecture", "file", "weights_sha256", "epochs", "seed", "reconstructed")
        )
        require(
            model["architecture"] == architecture
            and model["file"] == f"weights-{architecture}.npz"
            and fitted._hash(model["weights_sha256"])
            and type(model["epochs"]) is int
            and model["epochs"] == fitted.EPOCHS
            and type(model["seed"]) is int
            and model["seed"] == fitted.SEED
            and model["reconstructed"] is True,
            "model_binding",
        )
    expected = [(s, p[0]) for s in SYMBOLS for p in PERIODS]
    require(len(result["groups"]) == 6, "group_count")
    calibration_hashes = {}
    for group, (symbol, period) in zip(result["groups"], expected, strict=True):
        fitted._fields(group, ("symbol", "period", "months", "feedback_updates", "risk_sha256"))
        months = len(
            next(p for p in contract["plan"]["periods"] if p["period"] == period)["months"]
        )
        require(
            (group["symbol"], group["period"]) == (symbol, period)
            and type(group["months"]) is int
            and group["months"] == months
            and type(group["feedback_updates"]) is int
            and group["feedback_updates"] == months - 1
            and fitted._hash(group["risk_sha256"]),
            "group_binding",
        )
        require(
            calibration_hashes.setdefault(symbol, group["risk_sha256"]) == group["risk_sha256"],
            "TRAIN_recalibration",
        )
    matrix = [(s, p, c, n) for s, p in expected for c in COSTS for n in POLICIES]
    require(len(result["cells"]) == 144, "cell_count")
    hashes = {}
    for cell, key in zip(result["cells"], matrix, strict=True):
        fitted._fields(
            cell,
            (
                "symbol",
                "period",
                "cost_per_side_bps",
                "policy",
                "trades",
                "action_sha256",
                *METRICS,
            ),
        )
        require(
            tuple(cell[k] for k in ("symbol", "period", "cost_per_side_bps", "policy")) == key,
            "cell_matrix",
        )
        values = {m: fitted._numeric(cell[m]) for m in METRICS}
        require(
            values["final_nav"] > 0
            and 0 <= values["max_close_drawdown"] < 1
            and all(values[m] >= 0 for m in METRICS[2:5])
            and type(cell["trades"]) is int
            and 0
            <= cell["trades"]
            <= next(
                g["months"] + 1 for g in result["groups"] if (g["symbol"], g["period"]) == key[:2]
            ),
            "metric_domain",
        )
        fee, turnover = values["fees_initial_nav"], values["turnover_initial_nav"]
        require(
            abs(fee - Decimal(key[2]) * turnover / 10000)
            <= Decimal("3e-11") * (1 + fee + turnover),
            "fee_identity",
        )
        identity = key[0], key[1], key[3]
        require(
            fitted._hash(cell["action_sha256"])
            and hashes.setdefault(identity, cell["action_sha256"]) == cell["action_sha256"],
            "cost_action_binding",
        )
        if key[3] == "cash":
            require(
                values["final_nav"] == 1
                and cell["trades"] == 0
                and all(values[m] == 0 for m in METRICS[1:]),
                "cash_identity",
            )
    require(
        type(result["paired"]) is dict
        and type(result["paired"].get("kill_applied")) is bool
        and result["paired"] == paired_facts(result["cells"]),
        "paired_binding",
    )


def runtime_constraints():
    versions = fitted.runtime_versions()
    require(
        versions["torch"] == "2.7.0+cu128" and versions["pandas-market-calendars"] == "5.4.0",
        "pinned_runtime",
    )
    require(Path("/.dockerenv").is_file(), "Docker_required")
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    require(quota != "max" and 0 < int(quota) <= 2 * int(period), "CPU_confinement")
    memory = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    require(memory != "max" and 0 < int(memory) <= MEMORY_BYTES, "memory_confinement")
    require(Path("/sys/fs/cgroup/memory.swap.max").read_text().strip() == "0", "swap_confinement")
    require({name for _, name in socket.if_nameindex()} == {"lo"}, "network_none_required")


def verify_weights(root, result):
    for model in result["models"]:
        path = root / model["file"]
        _unlinked_path(path)
        fitted.read_weights(path, model["architecture"], model["weights_sha256"])


def worker(artifacts, market, pin, path, deadline, phase):
    require(phase in {"cuda", "cpu-smoke"}, "worker_phase")
    root, contract = verify(artifacts, market, pin)
    require(path == root / f"{phase}-result.json" and not path.exists(), "worker_path")
    require(
        read_json(root / f"{phase}-started.json")[0] == {"contract_sha256": pin}, "attempt_binding"
    )
    counts = dict(fits_started=0, fits_completed=0)
    result = result_base(pin, phase, counts=counts)
    stage = "cpu_smoke"
    try:
        runtime_constraints()
        import torch

        result["cpu_smoke_passed"] = fitted.cpu_smoke(torch, deadline=deadline)["cpu_smoke_passed"]
        require(result["cpu_smoke_passed"], "cpu_smoke_required")
        if phase == "cpu-smoke":
            result["status"] = "cpu_smoke_complete"
        else:
            torch.set_num_threads(2)
            require(torch.cuda.is_available() and str(torch.version.cuda) == "12.8", "CUDA_runtime")
            torch.use_deterministic_algorithms(True)
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.allow_tf32 = torch.backends.cuda.matmul.allow_tf32 = False
            free, total = torch.cuda.mem_get_info(0)
            budget = min(int(total * 0.9), free - 1024**3)
            require(budget > 0, "available_VRAM")
            torch.cuda.set_per_process_memory_fraction(budget / total, 0)
            torch.cuda.reset_peak_memory_stats(0)
            stage = "load"
            rows = fitted.load_adjusted(market / base.SNAPSHOT, market)
            stage = "prepare"
            prepared, plan = fitted.prepare(rows, contract["plan"]), contract["plan"]
            risks = {}
            available = all(item["arrays"] is not None for item in prepared.values())
            for symbol in SYMBOLS:
                risks[symbol], _ = momentum.calibrate(
                    prepared[symbol, "TRAIN"]["rows"], plan["momentum"], deadline=deadline
                )
                available &= risks[symbol] is not None and all(
                    momentum.gaps(prepared[symbol, p["period"]]["rows"], p) == (0, 0)
                    for p in plan["momentum"]["periods"]
                )
            if not available:
                result["status"] = "input_unavailable"
                result["failure_stage"] = "prepare"
            else:
                predictions, models = {}, []
                for architecture in fitted.ARCHITECTURES:
                    stage = "fit"
                    counts["fits_started"] += 1
                    weights = fitted.fit_policy(
                        torch,
                        {s: prepared[s, "TRAIN"]["arrays"] for s in SYMBOLS},
                        architecture,
                        device="cuda:0",
                        deadline=deadline,
                    )
                    counts["fits_completed"] += 1
                    stage = "inference"
                    metadata = fitted.write_weights(root, weights, architecture)
                    model = fitted.rebuild_policy(torch, weights, architecture)
                    recovered = fitted.rebuild_policy(
                        torch,
                        fitted.read_weights(
                            root / metadata["file"], architecture, metadata["weights_sha256"]
                        ),
                        architecture,
                    )
                    models.append(metadata)
                    for symbol in SYMBOLS:
                        for period, *_ in PERIODS:
                            arrays = prepared[symbol, period]["arrays"]
                            original = fitted.predict(torch, model, arrays)
                            readback = fitted.predict(torch, recovered, arrays)
                            require(
                                np.allclose(original, readback, rtol=0, atol=1e-6),
                                "weights_reconstruction",
                            )
                            predictions[architecture, symbol, period] = readback
                stage = "evaluate"
                groups, cells = evaluate(prepared, plan, predictions, risks, deadline=deadline)
                torch.cuda.synchronize(0)
                runtime = dict(
                    device=torch.cuda.get_device_name(0),
                    torch=str(torch.__version__),
                    cuda=str(torch.version.cuda),
                    torch_threads=torch.get_num_threads(),
                    free_before_bytes=free,
                    total_bytes=total,
                    memory_budget_bytes=budget,
                    peak_allocated_bytes=torch.cuda.max_memory_allocated(0),
                    training_device="cuda:0",
                    inference_device="cpu",
                )
                result.update(
                    status="complete",
                    models=models,
                    groups=groups,
                    cells=cells,
                    paired=paired_facts(cells),
                    runtime=runtime,
                )
        stage = "validate"
        result.update(counts)
        validate_result(result, contract, pin)
        verify_weights(root, result)
        require(time.monotonic() < deadline, "hard_timeout")
        verify(artifacts, market, pin)
    except Exception:
        result = result_base(
            pin, phase, counts=counts, smoked=result["cpu_smoke_passed"], failure_stage=stage
        )
    atomic_new(path, result)
