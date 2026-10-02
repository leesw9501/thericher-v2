"""Fixed Chronos-2 single-series versus same-origin ETF development comparison."""

from __future__ import annotations

import importlib.metadata
import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

import numpy as np

from thericher_v2.research import chronos2_local as local
from thericher_v2.research import timesfm_return_development as parent

base, geometry = parent.base, parent.geometry
NAME = "chronos2-tiingo-return-group-development-v1"
REPO, SYMBOLS, COSTS, PERIODS = parent.REPO, parent.SYMBOLS, parent.COSTS, parent.PERIODS
SECONDS = 900
MODES = ("isolated", "same_origin_trio", "duplicate_self")
FORECASTS = MODES + ("rolling_mean", "previous_return", "zero")
POLICIES = FORECASTS[:-1] + ("always_long", "cash")
PARENT_CONTRACT = "sha256:f8947da5f099267348e61f492e22462a319172edbbcbe1fcb662031ccf5d9ff9"
PARENT_SUMMARY = "sha256:ba936e9d99a34f7366351c9a1337801005a6d49ae24fe55e894ea44eee7244b3"
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
            *parent.CODE,
            "src/thericher_v2/research/chronos2_local.py",
            "src/thericher_v2/research/chronos2_return_development.py",
            "scripts/run_chronos2_return_development.py",
        )
    )
)


def configuration():
    return dict(
        context=128,
        horizon=1,
        symbols=list(SYMBOLS),
        periods=[list(p) for p in PERIODS],
        modes=list(MODES),
        policies=list(POLICIES),
        costs=list(COSTS),
        cells=126,
        feature="128 prior raw daily10000*(close/open-1) returns",
        target="next scheduled session raw intraday open-close bps",
        action="long iff median forecast>20bps; cost changes accounting only",
        timing="prior session completed; revised data assumed available before target open",
        grouping="one identical past calendar and forecast origin per trio; no future covariates",
        placebo="each target duplicated three times under distinct IDs in its own trio",
        units="signed return bps; no price level, positivity clamp or learned scaling",
        model_id=local.CHRONOS2_MODEL_ID,
        revision=local.CHRONOS2_REVISION,
        checkpoint_date=local.CHRONOS2_CHECKPOINT_DATE,
        model_sha256=local.CHRONOS2_SHA256,
        runtime=local.PINNED_RUNTIME,
        image=local.CHRONOS2_IMAGE,
        source_urls=[
            f"https://huggingface.co/{local.CHRONOS2_MODEL_ID}/tree/{local.CHRONOS2_REVISION}",
            "https://arxiv.org/abs/2510.15821",
        ],
        corpus_scope="exact instrument/context membership not disclosed",
        reference=dict(name=parent.NAME, contract=PARENT_CONTRACT, summary=PARENT_SUMMARY),
        budget=dict(seconds=SECONDS, gpu=True, training=False, passes=1),
        kill="future origin contaminates earlier group; hash/device mismatch; cost changes actions",
        limitations=[
            "seen_data_adaptive_development",
            "revised_non_PIT_OHLC",
            "correlated_ETFs_overlapping_contexts",
            "assumed_next_open_availability",
            "unit_notional_cost_proxy_not_NAV_or_broker_parity",
            "no_untouched_holdout",
        ],
        training=False,
        selection=False,
        holdout=False,
        paper_input=False,
    )


def _parent_result(root):
    directory = base.ensure_external_artifact_directory(root, REPO, "research", parent.NAME)
    raw = _read(directory / "precommit.json")
    require(digest(raw) == PARENT_CONTRACT, "parent_contract")
    raw_result = _read(directory / "summary.json")
    require(digest(raw_result) == PARENT_SUMMARY, "parent_summary")
    contract, result = json.loads(raw), json.loads(raw_result)
    parent.validate_result(result, contract, PARENT_CONTRACT)
    require(result["status"] == "complete", "parent_incomplete")
    return result


def verify_assets(root):
    model = base.ensure_external_artifact_directory(
        root, REPO, "foundation-models", "chronos-2", local.CHRONOS2_REVISION
    )
    local._verified_directory(model)
    return model


def proposed_contract():
    config = configuration()
    plan = parent.build_plan(geometry.calendar_days())
    require(all(p["target"] > config["checkpoint_date"][:10] for p in plan), "checkpoint_overlap")
    return dict(
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=base.source_identity(),
        plan=plan,
        runtime={
            p: importlib.metadata.version(p)
            for p in (*local.PINNED_RUNTIME, "pandas-market-calendars")
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
    require(contract["source"] == base.source_identity(), "source_changed")
    require(
        all(contract["runtime"][p] == v for p, v in local.PINNED_RUNTIME.items()), "runtime_changed"
    )
    return dict(
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        evidence_grade="POST_CHECKPOINT_SEEN_DATA_DEVELOPMENT",
    )


def register_contract(root, contract, pin):
    header(contract, pin)
    base.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=base.DATASET_HASH,
        split_hash=digest(encode(contract["plan"])),
        cost_model_hash=digest(encode(COSTS)),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root, market_data_root):
    base.verify_metadata(artifact_root, market_data_root)
    verify_assets(artifact_root)
    _parent_result(artifact_root)
    contract = proposed_contract()
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research") / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root, market_data_root, pin):
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research", NAME)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin and raw == encode(proposed_contract()), "precommit_changed")
    base.verify_metadata(artifact_root, market_data_root)
    verify_assets(artifact_root)
    _parent_result(artifact_root)
    return output, json.loads(raw)


def forecast_all(prepared, plan, model):
    by_key = {(g["symbol"], g["period"]): g for g in prepared}
    predictions = {key: {mode: [] for mode in MODES} for key in by_key}
    for period, _, _ in PERIODS:
        plans = [p for p in plan if p["period"] == period]
        dates = [p["target"] for p in plans]
        require(all(by_key[(s, period)]["dates"] == dates for s in SYMBOLS), "cohort_mismatch")
        # Only one origin enters a cross-learning call, even when later contexts exist.
        for index, p in enumerate(plans):
            stamps = tuple(datetime.fromisoformat(d).replace(tzinfo=UTC) for d in p["history"])
            origin = datetime.fromisoformat(p["target"]).replace(tzinfo=UTC)
            contexts = tuple(
                local.Chronos2Context(
                    s,
                    origin,
                    stamps,
                    stamps[-1] + timedelta(days=1),
                    by_key[(s, period)]["x"][index],
                )
                for s in SYMBOLS
            )
            for mode in MODES[:2]:
                values, _ = model.forecast(contexts, 1, mode=mode)
                require(
                    values.shape == (len(SYMBOLS), 1) and np.isfinite(values).all(),
                    "forecast_shape",
                )
                for j, s in enumerate(SYMBOLS):
                    predictions[(s, period)][mode].append(float(values[j, 0]))
            for c in contexts:
                duplicates = tuple(
                    replace(c, series_id=f"{c.series_id}-copy-{i}") for i in range(3)
                )
                values, _ = model.forecast(duplicates, 1, mode="same_origin_trio")
                require(values.shape == (3, 1) and np.isfinite(values).all(), "forecast_shape")
                predictions[(c.series_id, period)]["duplicate_self"].append(float(values[0, 0]))
    frozen = []
    for g in prepared:
        forecasts = {
            m: np.asarray(v, dtype=np.float64)
            for m, v in predictions[(g["symbol"], g["period"])].items()
        }
        forecasts.update(parent.cpu_forecasts(g))
        actions = {
            p: forecasts[p] > 20
            if p in forecasts
            else np.full(len(g["x"]), p == "always_long", dtype=bool)
            for p in POLICIES
        }
        for v in (*forecasts.values(), *actions.values()):
            v.setflags(write=False)
        frozen.append((forecasts, actions))
    return frozen


def score(prepared, frozen, contract, pin, runtime):
    groups, cells = [], []
    with localcontext() as ctx:
        ctx.prec = 50
        for g, (forecasts, actions) in zip(prepared, frozen, strict=True):
            targets = [geometry.outcome(g["index"].get(d)) for d in g["dates"]]
            observed = [i for i, y in enumerate(targets) if y is not None]
            require(bool(observed), "outcome_unavailable")
            n, metrics = len(observed), {}
            for name in FORECASTS:
                errors = [Decimal(str(float(forecasts[name][i]))) - targets[i] for i in observed]
                metrics[name] = dict(
                    mse_bps2=base._number(sum(e * e for e in errors) / n),
                    mae_bps=base._number(sum(abs(e) for e in errors) / n),
                )
            identity = dict(symbol=g["symbol"], period=g["period"])
            groups.append(
                dict(
                    **identity,
                    planned=g["planned"],
                    eligible=len(targets),
                    observed=n,
                    past_excluded=g["planned"] - len(targets),
                    censored=len(targets) - n,
                    metrics=metrics,
                    cohort_sha256=digest(encode(g["dates"])),
                )
            )
            for cost in COSTS:
                for policy in POLICIES:
                    flags = actions[policy]
                    traded = [i for i in observed if flags[i]]
                    gross = sum((targets[i] for i in traded), Decimal(0))
                    net = gross - cost * len(traded)
                    cells.append(
                        dict(
                            **identity,
                            policy=policy,
                            cost=cost,
                            observed=n,
                            selected=int(flags.sum()),
                            trades=len(traded),
                            selected_censored=int(flags.sum()) - len(traded),
                            gross_sum_bps=base._number(gross),
                            net_sum_bps=base._number(net),
                            mean_net_bps=base._number(net / n),
                            action_sha256=digest(
                                encode(list(zip(g["dates"], map(bool, flags), strict=True)))
                            ),
                        )
                    )
    result = dict(
        **header(contract, pin),
        status="complete",
        criterion="descriptive_only_no_selection",
        groups=groups,
        cells=cells,
        runtime=runtime,
    )
    validate_result(result, contract, pin)
    return result


def failure(contract, pin, reason):
    require(reason in base.FAILURES, "failure_category")
    return dict(
        **header(contract, pin), status="failed", criterion=reason, groups=[], cells=[], runtime={}
    )


def validate_result(result, contract, pin):
    if result.get("status") == "failed":
        require(result == failure(contract, pin, result["criterion"]), "failure_shape")
        return
    expected = header(contract, pin)
    require(
        set(result) == set(expected) | {"status", "criterion", "groups", "cells", "runtime"}
        and all(result[k] == v for k, v in expected.items())
        and result["status"] == "complete"
        and result["criterion"] == "descriptive_only_no_selection",
        "result_binding",
    )
    keys = [(s, p) for s in SYMBOLS for p, _, _ in PERIODS]
    require([(g["symbol"], g["period"]) for g in result["groups"]] == keys, "group_matrix")
    for g in result["groups"]:
        require(
            set(g)
            == {
                "symbol",
                "period",
                "planned",
                "eligible",
                "observed",
                "past_excluded",
                "censored",
                "metrics",
                "cohort_sha256",
            },
            "group_fields",
        )
        require(
            all(
                type(g[k]) is int and g[k] >= 0
                for k in ("planned", "eligible", "observed", "past_excluded", "censored")
            ),
            "count_type",
        )
        require(
            g["planned"] == sum(p["period"] == g["period"] for p in contract["plan"])
            and g["planned"] == g["eligible"] + g["past_excluded"]
            and g["eligible"] == g["observed"] + g["censored"]
            and g["observed"] > 0,
            "counts",
        )
        require(
            isinstance(g["cohort_sha256"], str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", g["cohort_sha256"]) is not None,
            "cohort_hash",
        )
        require(set(g["metrics"]) == set(FORECASTS), "metric_matrix")
        for metrics in g["metrics"].values():
            require(set(metrics) == {"mse_bps2", "mae_bps"}, "metric_fields")
            require(
                all(
                    isinstance(v, str) and Decimal(v).is_finite() and Decimal(v) >= 0
                    for v in metrics.values()
                ),
                "metric_value",
            )
    require(
        [(c["symbol"], c["period"], c["cost"], c["policy"]) for c in result["cells"]]
        == [(s, p, c, n) for s, p in keys for c in COSTS for n in POLICIES],
        "cell_matrix",
    )
    paths = {}
    for c in result["cells"]:
        require(
            set(c)
            == {
                "symbol",
                "period",
                "policy",
                "cost",
                "observed",
                "selected",
                "trades",
                "selected_censored",
                "gross_sum_bps",
                "net_sum_bps",
                "mean_net_bps",
                "action_sha256",
            },
            "cell_fields",
        )
        g = result["groups"][keys.index((c["symbol"], c["period"]))]
        require(
            all(
                type(c[k]) is int
                for k in ("observed", "selected", "trades", "selected_censored", "cost")
            )
            and c["observed"] == g["observed"]
            and 0 <= c["trades"] <= g["observed"]
            and c["trades"] == c["selected"] - c["selected_censored"]
            and 0 <= c["selected"] <= g["eligible"]
            and 0 <= c["selected_censored"] <= g["censored"],
            "cell_counts",
        )
        values = [Decimal(c[k]) for k in ("gross_sum_bps", "net_sum_bps", "mean_net_bps")]
        require(all(v.is_finite() for v in values), "money_finite")
        gross, net, mean = values
        require(
            abs(gross - c["cost"] * c["trades"] - net) < Decimal("2e-12")
            and abs(net / c["observed"] - mean) < Decimal("2e-12"),
            "accounting",
        )
        if c["policy"] == "cash":
            require(c["selected"] == 0 and all(v == 0 for v in values), "cash_control")
        if c["policy"] == "always_long":
            require(c["selected"] == g["eligible"] and c["trades"] == g["observed"], "long_control")
        require(
            isinstance(c["action_sha256"], str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", c["action_sha256"]) is not None,
            "action_hash",
        )
        key = c["symbol"], c["period"], c["policy"]
        path = tuple(
            c[k]
            for k in ("selected", "trades", "selected_censored", "gross_sum_bps", "action_sha256")
        )
        require(paths.setdefault(key, path) == path, "cost_changes_action")
    r = result["runtime"]
    require(
        set(r)
        == {
            "device",
            "peak_allocated_bytes",
            "memory_budget_bytes",
            "point_count",
            "training",
            "predictions_retained",
            "controls_reproduced",
        }
        and r["training"] is r["predictions_retained"] is False
        and type(r["point_count"]) is int
        and r["point_count"] == len(MODES) * sum(g["eligible"] for g in result["groups"])
        and type(r["controls_reproduced"]) is int
        and r["controls_reproduced"] == 72
        and isinstance(r["device"], str)
        and 0 < len(r["device"]) <= 128
        and all(
            type(r[k]) is int and r[k] > 0 for k in ("peak_allocated_bytes", "memory_budget_bytes")
        ),
        "runtime",
    )


def reattest_controls(result, reference):
    for g, old in zip(result["groups"], reference["groups"], strict=True):
        require(
            {k: v for k, v in g.items() if k != "metrics"}
            == {k: v for k, v in old.items() if k != "metrics"},
            "parent_cohort_changed",
        )
        require(
            all(
                g["metrics"][k] == old["metrics"][k]
                for k in ("rolling_mean", "previous_return", "zero")
            ),
            "parent_metrics_changed",
        )
    controls = [c for c in result["cells"] if c["policy"] not in MODES]
    old_controls = [c for c in reference["cells"] if c["policy"] != "timesfm"]
    require(controls == old_controls and len(controls) == 72, "parent_controls_changed")


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
        snapshot = base.load_verified_tiingo_etf_d1_snapshot(
            market_data_root / base.SNAPSHOT,
            dataset_id=base.DATASET_ID,
            expected_dataset_hash=base.DATASET_HASH,
            expected_manifest_hash=base.MANIFEST_HASH,
            market_data_root=market_data_root,
            repo_root=REPO,
        )
        prepared = parent.prepare(snapshot.rows_by_symbol, contract["plan"])
        atomic_new(
            output / "cpu-baseline.json",
            dict(
                **header(contract, pin),
                groups=[
                    dict(
                        symbol=g["symbol"],
                        period=g["period"],
                        eligible=len(g["x"]),
                        context_sha256=digest(g["x"].tobytes()),
                        baseline_sha256=digest(
                            encode({k: v.tolist() for k, v in parent.cpu_forecasts(g).items()})
                        ),
                    )
                    for g in prepared
                ],
            ),
        )
        geometry.check_time(deadline)
        import torch

        require(
            torch.__version__ == "2.7.0+cu128" and torch.cuda.is_available(), "cuda_unavailable"
        )
        torch.set_num_threads(2)
        free, total = torch.cuda.mem_get_info()
        budget = min(int(total * 0.9), free - 1024**3)
        require(budget > 0, "cuda_memory_unavailable")
        torch.cuda.set_per_process_memory_fraction(budget / total, 0)
        torch.cuda.reset_peak_memory_stats(0)
        model = local.load_chronos2_local(verify_assets(artifact_root), device="cuda")
        frozen = forecast_all(prepared, contract["plan"], model)
        torch.cuda.synchronize()
        geometry.check_time(deadline)
        runtime = dict(
            device=torch.cuda.get_device_name(0),
            peak_allocated_bytes=torch.cuda.max_memory_allocated(0),
            memory_budget_bytes=budget,
            point_count=len(MODES) * sum(len(g["x"]) for g in prepared),
            training=False,
            predictions_retained=False,
            controls_reproduced=72,
        )
        result = score(prepared, frozen, contract, pin, runtime)
        reattest_controls(result, _parent_result(artifact_root))
        verify(artifact_root, market_data_root, pin)
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure")
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None
