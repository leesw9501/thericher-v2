"""Post-checkpoint, seen-data zero-shot intraday-return study; no broker consumer."""

from __future__ import annotations

import importlib.metadata
import json
import re
import runpy
from datetime import date
from decimal import Decimal, localcontext

import numpy as np

from thericher_v2.research import tiingo_geometry_ridge_development as geometry
from thericher_v2.research import tiingo_month_start_development as base
from thericher_v2.research.timesfm_local import forecast_timesfm_2p5

NAME = "timesfm-2p5-tiingo-intraday-return-development-v1"
REPO, SYMBOLS, COSTS, SECONDS = base.REPO, base.SYMBOLS, base.COSTS, 600
CONTEXT = 128
PERIODS = (("2026-Q1", "2026-01-01", "2026-03-31"), ("2026-Apr-Jul", "2026-04-01", "2026-07-31"))
PUBLIC_BEFORE = "2025-10-03"
FORECASTS = ("timesfm", "rolling_mean", "previous_return", "zero")
POLICIES = FORECASTS[:3] + ("always_long", "cash")
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
            *geometry.CODE,
            "src/thericher_v2/research/timesfm_local.py",
            "scripts/run_timesfm_2p5_smoke.py",
            "src/thericher_v2/research/timesfm_return_development.py",
            "scripts/run_timesfm_return_development.py",
        )
    )
)


def public_assets():
    return runpy.run_path(str(REPO / "scripts/run_timesfm_2p5_smoke.py"))


def configuration():
    public = public_assets()
    return dict(
        symbols=list(SYMBOLS),
        context=CONTEXT,
        horizon=1,
        periods=[list(p) for p in PERIODS],
        policies=list(POLICIES),
        forecast_controls=list(FORECASTS),
        costs=list(COSTS),
        cells=90,
        feature="128 completed same-session raw10000*(close/open-1) returns; float32",
        target="next scheduled session raw10000*(close/open-1); no overnight position",
        timing="decision after previous completed session; available before next open assumed",
        cohort="calendar-first Jan-Jul2026, past-only eligibility; no bridging/backfill",
        missing="future outcome censoring only after all forecasts/actions are frozen",
        action="long iff forecast>20bps else flat; cost changes accounting only",
        accounting=(
            "action*(intraday_return-cost); unit-notional daily trades; not NAV/local_paper parity"
        ),
        metrics="per-symbol/period MSE,MAE and net per observed session; no pooled inference",
        normalization="fixed TimesFM per-input normalization; no target/other-series fitting",
        output_statistic="point forecast is median; signed bps; no positivity clamp",
        warmup="128 prior sessions may precede checkpoint; targets alone are post-checkpoint",
        model_id=public["MODEL_ID"],
        model_revision=public["REVISION"],
        files=public["PINS"],
        weight_public_before=PUBLIC_BEFORE,
        provenance=dict(
            model_card=f"https://huggingface.co/{public['MODEL_ID']}/blob/{public['REVISION']}/README.md",
            weights=f"https://huggingface.co/{public['MODEL_ID']}/blob/{public['REVISION']}/model.safetensors",
            commits=f"https://huggingface.co/{public['MODEL_ID']}/commits/{public['REVISION']}",
            observed_on="2026-09-25",
            license="Apache-2.0",
            weight_commit="d418f3e8a8fa79d655b391c158f0ee8d68fe68c9",
            weight_commit_date="2025-10-01",
            interpretation=(
                "official dated revision/hash predate targets; trusted publisher, "
                "not independent timestamp notarization"
            ),
            corpus_scope="not_disclosed; no claim of unseen instruments or contexts",
        ),
        image=public["IMAGE"],
        prior_families=[base.NAME, geometry.NAME, public["NAME"]],
        budget=dict(seconds=SECONDS, gpu=True, passes=1, training=False),
        kill=(
            "future changes earlier forecast; weight/date/source mismatch; "
            "cost changes action; nonfinite/device fallback"
        ),
        limitations=[
            "seen_data_adaptive_development",
            "correlated_ETFs_and_overlapping_contexts",
            "revised_non_PIT_OHLC",
            "open_close_independent_revisions_not_cancelled",
            "calendar_and_next_open_availability_assumed",
            "all_in_cost_proxy_not_broker_parity",
            "checkpoint_date_excludes_later_target_memorization_only",
            "return_series_not_price_level_benchmark",
        ],
        training=False,
        selection=False,
        holdout=False,
        paper_input=False,
    )


def build_plan(days):
    require(
        all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in days),
        "calendar_date",
    )
    require(all(a < b for a, b in zip(days, days[1:], strict=False)), "calendar_order")
    plan = []
    for name, first, last in PERIODS:
        indices = [i for i, day in enumerate(days) if first <= day <= last]
        require(indices and indices[0] >= CONTEXT, "calendar_support")
        for i in indices:
            require(days[i] > PUBLIC_BEFORE, "target_predates_checkpoint")
            plan.append(dict(period=name, target=days[i], history=list(days[i - CONTEXT : i])))
    return plan


def proposed_contract():
    config = configuration()
    return dict(
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=base.source_identity(),
        plan=build_plan(geometry.calendar_days()),
        runtime={
            p: importlib.metadata.version(p)
            for p in (
                "torch",
                "timesfm",
                "numpy",
                "safetensors",
                "huggingface-hub",
                "pandas-market-calendars",
            )
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
        contract["runtime"]["torch"] == "2.7.0+cu128" and contract["runtime"]["timesfm"] == "2.0.2",
        "runtime_changed",
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


def verify_assets(root):
    public = public_assets()
    model = base.ensure_external_artifact_directory(
        root, REPO, "foundation-models", "timesfm-2.5-200m", public["REVISION"]
    )
    public["verify_files"](model)
    return model


def freeze(artifact_root, market_data_root):
    base.verify_metadata(artifact_root, market_data_root)
    verify_assets(artifact_root)
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
    return output, json.loads(raw)


def prepare(rows_by_symbol, plan):
    require(set(rows_by_symbol) == set(SYMBOLS), "symbols")
    prepared = []
    for symbol in SYMBOLS:
        rows = rows_by_symbol[symbol]
        require(
            all(r.symbol == symbol and type(r.session_date) is date for r in rows), "row_identity"
        )
        require(
            all(a.session_date < b.session_date for a, b in zip(rows, rows[1:], strict=False)),
            "row_order",
        )
        indexed = {r.session_date.isoformat(): r for r in rows}
        for period, _, _ in PERIODS:
            planned = [p for p in plan if p["period"] == period]
            contexts, dates = [], []
            for p in planned:
                chain = [geometry.outcome(indexed.get(d)) for d in p["history"]]
                if all(v is not None for v in chain):
                    contexts.append(chain)
                    dates.append(p["target"])
            x = np.asarray(contexts, dtype=np.float32).reshape(-1, CONTEXT)
            require(np.isfinite(x).all(), "nonfinite_context")
            prepared.append(
                dict(
                    symbol=symbol,
                    period=period,
                    planned=len(planned),
                    dates=dates,
                    x=x,
                    index=indexed,
                )
            )
    return prepared


def cpu_forecasts(group):
    x = group["x"].astype(np.float64)
    return dict(rolling_mean=x.mean(axis=1), previous_return=x[:, -1].copy(), zero=np.zeros(len(x)))


def forecast_all(prepared, model, *, predictor=forecast_timesfm_2p5):
    require(all(len(g["x"]) for g in prepared), "input_unavailable")
    contexts = np.concatenate([g["x"] for g in prepared])
    public = public_assets()
    points, _ = predictor(
        model,
        {k: public["PINS"][k] for k in ("config.json", "model.safetensors")},
        contexts,
        horizon=1,
        device="cuda",
    )
    require(points.shape == (len(contexts), 1) and np.isfinite(points).all(), "forecast_shape")
    cursor, result = 0, []
    for group in prepared:
        end = cursor + len(group["x"])
        forecasts = dict(timesfm=points[cursor:end, 0].astype(np.float64), **cpu_forecasts(group))
        actions = {
            p: forecasts[p] > 20
            if p in forecasts
            else np.full(end - cursor, p == "always_long", dtype=bool)
            for p in POLICIES
        }
        for v in (*forecasts.values(), *actions.values()):
            v.setflags(write=False)
        result.append((forecasts, actions))
        cursor = end
    return result


def score(prepared, frozen, contract, pin, runtime):
    groups, cells = [], []
    with localcontext() as ctx:
        ctx.prec = 50
        for g, (forecasts, actions) in zip(prepared, frozen, strict=True):
            targets = [geometry.outcome(g["index"].get(d)) for d in g["dates"]]
            observed = [i for i, y in enumerate(targets) if y is not None]
            require(bool(observed), "outcome_unavailable")
            n = len(observed)
            metrics = {}
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
            isinstance(g["cohort_sha256"], str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", g["cohort_sha256"]) is not None,
            "cohort_hash",
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
        require(set(g["metrics"]) == set(FORECASTS), "metric_matrix")
        for metrics in g["metrics"].values():
            require(set(metrics) == {"mse_bps2", "mae_bps"}, "metric_fields")
            for value in metrics.values():
                require(
                    isinstance(value, str) and Decimal(value).is_finite() and Decimal(value) >= 0,
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
        key = c["symbol"], c["period"], c["policy"]
        require(
            isinstance(c["action_sha256"], str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", c["action_sha256"]) is not None,
            "action_hash",
        )
        path = tuple(
            c[k]
            for k in ("selected", "trades", "selected_censored", "gross_sum_bps", "action_sha256")
        )
        require(paths.setdefault(key, path) == path, "cost_changes_action")
    runtime = result["runtime"]
    require(
        set(runtime)
        == {
            "torch",
            "cuda",
            "device",
            "peak_allocated_bytes",
            "memory_budget_bytes",
            "point_count",
            "training",
            "predictions_retained",
        }
        and runtime["training"] is runtime["predictions_retained"] is False
        and type(runtime["point_count"]) is int
        and runtime["point_count"] == sum(g["eligible"] for g in result["groups"])
        and runtime["torch"] == "2.7.0+cu128"
        and runtime["cuda"] == "12.8"
        and isinstance(runtime["device"], str)
        and 0 < len(runtime["device"]) <= 128
        and type(runtime["peak_allocated_bytes"]) is int
        and runtime["peak_allocated_bytes"] > 0
        and type(runtime["memory_budget_bytes"]) is int
        and runtime["memory_budget_bytes"] > 0,
        "runtime",
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
        snapshot = base.load_verified_tiingo_etf_d1_snapshot(
            market_data_root / base.SNAPSHOT,
            dataset_id=base.DATASET_ID,
            expected_dataset_hash=base.DATASET_HASH,
            expected_manifest_hash=base.MANIFEST_HASH,
            market_data_root=market_data_root,
            repo_root=REPO,
        )
        prepared = prepare(snapshot.rows_by_symbol, contract["plan"])
        require(all(len(g["x"]) for g in prepared), "input_unavailable")
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
                            encode({k: v.tolist() for k, v in cpu_forecasts(g).items()})
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
        frozen = forecast_all(prepared, verify_assets(artifact_root))
        torch.cuda.synchronize()
        geometry.check_time(deadline)
        runtime = dict(
            torch=torch.__version__,
            cuda=torch.version.cuda,
            device=torch.cuda.get_device_name(0),
            peak_allocated_bytes=torch.cuda.max_memory_allocated(0),
            memory_budget_bytes=budget,
            point_count=sum(len(g["x"]) for g in prepared),
            training=False,
            predictions_retained=False,
        )
        result = score(prepared, frozen, contract, pin, runtime)
        verify(artifact_root, market_data_root, pin)
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure")
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None
