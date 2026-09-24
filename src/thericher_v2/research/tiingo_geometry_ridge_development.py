"""Fixed, source-local, seen-data OHLC geometry regression; no execution consumer."""

from __future__ import annotations

import importlib.metadata
import json
import time
from datetime import date
from decimal import Decimal, localcontext
from types import SimpleNamespace

from thericher_v2.data.tiingo_etf_daily import load_verified_tiingo_etf_d1_snapshot
from thericher_v2.research import tiingo_month_start_development as base
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory
from thericher_v2.research.campaign_registry import register_frozen_campaign

NAME = "tiingo-d1-ohlc-geometry-ridge-development-v1"
REPO, SYMBOLS, COSTS, SECONDS = base.REPO, base.SYMBOLS, base.COSTS, base.SECONDS
WINDOWS = (5, 20)
POLICIES = ("ridge5", "ridge20", "train_mean", "previous_intraday", "always_long", "cash")
FOLDS = (("2013-2019", "2013-01-01", "2019-12-31"), ("2020-2026-07", "2020-01-01", "2026-07-31"))
MIN_TRAIN, MIN_EVAL = 500, 100
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
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
            *base.CODE,
            "src/thericher_v2/research/tiingo_geometry_ridge_development.py",
            "scripts/run_tiingo_geometry_ridge_development.py",
            "src/thericher_v2/research/firstrate_m5_h30_lstm_dev_20260921.py",
            "src/thericher_v2/contracts.py",
            "src/thericher_v2/__init__.py",
            "src/thericher_v2/serialization.py",
            "src/thericher_v2/data/tiingo_eod.py",
            "src/thericher_v2/data/local.py",
            "src/thericher_v2/data/provider.py",
            "src/thericher_v2/data/resample.py",
            "src/thericher_v2/market/resample.py",
            "src/thericher_v2/data/firstrate_free_intraday_timeframe_mechanics.py",
            "src/thericher_v2/execution/__init__.py",
            "src/thericher_v2/execution/local_paper.py",
            "src/thericher_v2/research/sequence_architecture_models.py",
            "src/thericher_v2/research/engine_research_agent.py",
            "src/thericher_v2/research/validation.py",
        )
    )
)


def configuration():
    prior = base.configuration()
    return dict(
        symbols=list(SYMBOLS),
        windows=list(WINDOWS),
        policies=list(POLICIES),
        fits=12,
        cells=108,
        features=["(C-O)/O", "(H-L)/O", "2*(C-L)/(H-L)-1; zero_range=0"],
        target="10000*(next_scheduled_close/next_scheduled_open-1)",
        decision="after_completed_close; history_includes_decision_day; target=next_NYSE_session",
        action_domain=[0, 1],
        cohort="common20_within_symbol_only_not_cross_symbol",
        action="forecast_strictly_gt_20bps; always_long=1; cash=0",
        costs_all_in_roundtrip_bps=list(COSTS),
        payoff="action*(target_bps-cost_bps)",
        primary_cost_bps=10,
        stress_cost_bps=20,
        train_start="2001-01-01",
        folds=[list(f) for f in FOLDS],
        common_history_sessions=20,
        purge="train_target_strictly_before_first_eval_history",
        scaler="TRAIN_supported_20x3_only_population_mean_std; zero_std=1; shared_by_windows",
        ridge="alpha=1; solver=svd; fit_intercept=True; target_in_bps; no_target_scaling",
        minima=dict(train=MIN_TRAIN, observed_development=MIN_EVAL),
        insufficient="input_unavailable; retain_counts; suppress_all_scores",
        missing="no_bridge_or_backfill; past_only_eligibility; outcomes_censored_after_forecasts",
        events="no_dividend_split_discontinuity_or_volume_mask; no_cross_day_price_feature",
        calendar=prior["calendar"],
        excluded_tail="August2026_and_later_only",
        budget=dict(
            cpu_threads=1,
            memory_bytes=base.MEMORY_BYTES,
            wall_seconds=SECONDS,
            gpu=False,
            passes=1,
            retries=False,
        ),
        resource_owner=prior["resource_owner"],
        expected_main_owned_image=IMAGE,
        gpu_flags=False,
        prior_families=prior["prior_families"] + [base.NAME],
        assumptions=[a for a in prior["assumptions"] if not a.startswith("session_11_")]
        + [
            "completed_day_values_assumed_available_before_next_open_not_proven_PIT",
            "correlated_ETFs_overlapping_histories_not_independent_observations",
            "expanding_second_fold_reuses_first_fold_development_in_TRAIN",
            "expanding_folds_not_independent; previous_intraday_control_is_nested_feature",
            "always_long_and_cash_share_exact_eligible_decision_and_observed_outcome_basis",
            "unit_entry_notional_daily_roundtrips_not_portfolio_NAV",
            "same_flat_costs_assume_no_candidate_control_cost_differential",
        ],
        scope=prior["scope"],
        weights_retained=False,
        technical_kills=[
            "future_outcome_invariance_of_prior_inputs_scalers_forecasts_actions",
            "independent_positive_daily_OHLC_scale_invariance",
            "missing_target_does_not_change_prior_intent_or_shift_target",
            "strict_train_label_history_purge_and_source_binding",
        ],
        criterion="all_six_symbol_window_paired_MSE_tables_both_folds; no_binary_edge_or_selection",
    )


def calendar_days():
    require(importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version")
    import pandas_market_calendars as calendars

    return [
        t.date().isoformat()
        for t in calendars.get_calendar("NYSE")
        .schedule(start_date="2000-12-01", end_date="2026-07-31")
        .index
    ]


def build_plan(days):
    require(
        all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in days),
        "calendar_date",
    )
    require(all(a < b for a, b in zip(days, days[1:], strict=False)), "calendar_order")
    require(days and days[0] >= "2000-12-01" and days[-1] <= "2026-07-31", "calendar_scope")
    start = next(i for i, d in enumerate(days) if d >= "2001-01-01")
    folds = []
    for name, first, last in FOLDS:
        indices = [i for i, d in enumerate(days) if first <= d <= last]
        require(indices and indices[0] - 20 > start >= 20, "calendar_support")
        folds.append(
            dict(
                fold=name,
                train=[start, indices[0] - 20],
                evaluation=[indices[0], indices[-1] + 1],
                train_exit_before=days[indices[0] - 20],
                purged_sessions=20,
            )
        )
    return dict(days=list(days), folds=folds)


def proposed_contract():
    config, source = configuration(), base.source_identity()
    return dict(
        schema_version=1,
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=source,
        source_sha256=digest(encode(source)),
        plan=build_plan(calendar_days()),
        runtime={
            p: importlib.metadata.version(p)
            for p in ("numpy", "scipy", "scikit-learn", "pandas-market-calendars")
        },
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def header(contract, pin):
    require(digest(encode(contract)) == pin, "contract_binding")
    require(encode(contract["config"]) == encode(configuration()), "config_changed")
    require(contract["source"] == base.source_identity(), "source_changed")
    require(contract["config_sha256"] == digest(encode(configuration())), "config_hash")
    require(contract["source_sha256"] == digest(encode(base.source_identity())), "source_hash")
    require(
        encode(contract["plan"]) == encode(build_plan(contract["plan"]["days"])), "plan_changed"
    )
    return dict(
        schema_version=1,
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        source_sha256=contract["source_sha256"],
        scope=configuration()["scope"],
    )


def register_contract(root, contract, pin):
    header(contract, pin)
    register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=base.DATASET_HASH,
        split_hash=digest(encode(contract["plan"])),
        cost_model_hash=digest(encode(list(COSTS))),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root, market_data_root):
    base.verify_metadata(artifact_root, market_data_root)
    contract = proposed_contract()
    output = ensure_external_artifact_directory(artifact_root, REPO, "research") / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root, market_data_root, pin):
    output = ensure_external_artifact_directory(artifact_root, REPO, "research", NAME)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin and raw == encode(proposed_contract()), "precommit_changed")
    base.verify_metadata(artifact_root, market_data_root)
    return output, json.loads(raw)


def check_time(deadline):
    require(time.monotonic() < deadline, "hard_timeout")


def geometry(row):
    if row is None or not base._valid_ohlc(row):
        return None
    with localcontext() as context:
        context.prec = 50
        width = row.high - row.low
        return tuple(
            float(v)
            for v in (
                (row.close - row.open) / row.open,
                width / row.open,
                2 * (row.close - row.low) / width - 1 if width else Decimal(0),
            )
        )


def outcome(row):
    if row is None or not base._valid_ohlc(row):
        return None
    with localcontext() as context:
        context.prec = 50
        return Decimal(10000) * (row.close / row.open - 1)


def nonoverlap_blocks(indices):
    stop, count = -1, 0
    for i in indices:
        if i - 20 > stop:
            stop, count = i, count + 1
    return count


def observe(rows, days, bounds):
    indices, features = [], []
    for i in range(*bounds):
        chain = [geometry(rows.get(d)) for d in days[i - 20 : i]]
        if all(g is not None for g in chain):
            indices.append(i)
            features.append(chain)
    return indices, features


def prepare(rows, plan, fold, deadline):
    """TRAIN outcomes may enter fitting; development outcomes cannot enter this function."""
    import numpy as np

    check_time(deadline)
    days = plan["days"]
    train_i, train_x = observe(rows, days, fold["train"])
    train_y = [outcome(rows.get(days[i])) for i in train_i]
    supported = [n for n, y in enumerate(train_y) if y is not None]
    eval_i, eval_x = observe(rows, days, fold["evaluation"])
    fitted_i = [train_i[n] for n in supported]
    require(not fitted_i or max(fitted_i) < fold["evaluation"][0] - 20, "train_purge")
    facts = dict(
        train_planned=fold["train"][1] - fold["train"][0],
        train_eligible=len(train_i),
        train_observed=len(supported),
        train_input_excluded=fold["train"][1] - fold["train"][0] - len(train_i),
        train_censored=len(train_i) - len(supported),
        train_blocks=nonoverlap_blocks(fitted_i),
        eval_planned=fold["evaluation"][1] - fold["evaluation"][0],
        eval_eligible=len(eval_i),
        eval_input_excluded=fold["evaluation"][1] - fold["evaluation"][0] - len(eval_i),
        eval_blocks=nonoverlap_blocks(eval_i),
        dates=dict(
            train_first=days[fold["train"][0]],
            train_last=days[fold["train"][1] - 1],
            eval_first=days[fold["evaluation"][0]],
            eval_last=days[fold["evaluation"][1] - 1],
            train_exit_before=fold["train_exit_before"],
        ),
        cohort_sha256=digest(encode([[days[i] for i in fitted_i], [days[i] for i in eval_i]])),
    )
    return SimpleNamespace(
        train_x=np.asarray([train_x[n] for n in supported], dtype="float64").reshape(-1, 20, 3),
        train_y=np.asarray([float(train_y[n]) for n in supported]),
        eval_x=np.asarray(eval_x, dtype="float64").reshape(-1, 20, 3),
        eval_indices=eval_i,
        facts=facts,
    )


def forecasts(prepared, deadline):
    import numpy as np

    from thericher_v2.research.firstrate_m5_h30_lstm_dev_20260921 import ridge_predict

    require(len(prepared.train_y) >= MIN_TRAIN, "insufficient_train")
    check_time(deadline)
    mean = prepared.train_x.mean(axis=(0, 1))
    scale = prepared.train_x.std(axis=(0, 1))
    scale = np.where(scale == 0, 1.0, scale)
    previous = 10000 * prepared.eval_x[:, -1, 0]
    fold = SimpleNamespace(
        train_x=(prepared.train_x - mean) / scale,
        train_y=prepared.train_y,
        eval_x=(prepared.eval_x - mean) / scale,
    )
    require(
        all(np.isfinite(a).all() for a in (fold.train_x, fold.train_y, fold.eval_x)),
        "nonfinite_features",
    )
    predictions = {}
    for window in WINDOWS:
        check_time(deadline)
        predictions[f"ridge{window}"] = (
            ridge_predict(fold, window) if len(fold.eval_x) else np.empty(0)
        )
    predictions.update(
        train_mean=np.full(len(previous), prepared.train_y.mean()), previous_intraday=previous
    )
    require(all(np.isfinite(p).all() for p in predictions.values()), "nonfinite_forecast")
    return predictions, digest(encode([mean.tolist(), scale.tolist()])), 2 if len(previous) else 0


def _score(predictions, targets, dates):
    scores = []
    observed = [i for i, y in enumerate(targets) if y is not None]
    with localcontext() as context:
        context.prec = 50
        for policy in POLICIES:
            forecast = predictions.get(policy)
            actions = (
                [int(policy == "always_long")] * len(dates)
                if forecast is None
                else [int(p > 20) for p in forecast]
            )
            trades = [i for i in observed if actions[i]]
            gross = sum((targets[i] for i in trades), Decimal(0))
            mse = (
                sum(((Decimal(str(forecast[i])) - targets[i]) ** 2 for i in observed), Decimal(0))
                / len(observed)
                if forecast is not None and observed
                else None
            )
            scores.append(
                dict(
                    policy=policy,
                    selected_count=sum(bool(a) for a in actions),
                    action_sha256=digest(encode(list(zip(dates, actions, strict=True)))),
                    trade_count=len(trades),
                    selected_censored_count=sum(bool(a) for a in actions) - len(trades),
                    gross_sum_bps=base._number(gross),
                    mse_bps2=None if mse is None else base._number(mse),
                )
            )
    return scores


def evaluate(rows_by_symbol, contract, pin, *, deadline):
    header(contract, pin)
    require(set(rows_by_symbol) == set(SYMBOLS), "symbols")
    groups = []
    for symbol in SYMBOLS:
        rows = rows_by_symbol[symbol]
        require(all(r.symbol == symbol for r in rows), "row_symbol")
        require(
            all(a.session_date < b.session_date for a, b in zip(rows, rows[1:], strict=False)),
            "row_order",
        )
        indexed = {r.session_date.isoformat(): r for r in rows}
        for fold in contract["plan"]["folds"]:
            prepared = prepare(indexed, contract["plan"], fold, deadline)
            predictions, normalizer, fits = ({}, None, 0)
            if len(prepared.train_y) >= MIN_TRAIN:
                predictions, normalizer, fits = forecasts(prepared, deadline)
            # Only now attach future outcomes, after all eligible forecasts/actions are fixed.
            targets = [
                outcome(indexed.get(contract["plan"]["days"][i])) for i in prepared.eval_indices
            ]
            observed = sum(y is not None for y in targets)
            facts = prepared.facts
            facts.update(
                eval_observed=observed,
                eval_censored=len(targets) - observed,
                eval_observed_blocks=nonoverlap_blocks(
                    [
                        i
                        for i, y in zip(prepared.eval_indices, targets, strict=True)
                        if y is not None
                    ]
                ),
            )
            groups.append(
                dict(
                    symbol=symbol,
                    fold=fold["fold"],
                    counts=facts,
                    fits=fits,
                    normalizer_sha256=normalizer,
                    scores=_score(
                        predictions,
                        targets,
                        [contract["plan"]["days"][i] for i in prepared.eval_indices],
                    )
                    if predictions
                    else [],
                )
            )
            check_time(deadline)
    available = all(
        g["counts"]["train_observed"] >= MIN_TRAIN and g["counts"]["eval_observed"] >= MIN_EVAL
        for g in groups
    )
    if not available:
        for group in groups:
            for score in group["scores"]:
                score["gross_sum_bps"] = score["mse_bps2"] = None
    result = assemble(contract, pin, groups)
    validate_result(result, contract, pin)
    return result


def assemble(contract, pin, groups):
    available = all(
        g["counts"]["train_observed"] >= MIN_TRAIN and g["counts"]["eval_observed"] >= MIN_EVAL
        for g in groups
    )
    cells = []
    for g in groups:
        n = g["counts"]["eval_observed"]
        for policy in POLICIES:
            score = next((s for s in g["scores"] if s["policy"] == policy), None)
            for cost in COSTS:
                net, mse, trades, selected, censored = None, None, None, None, None
                if score is not None:
                    trades, selected = score["trade_count"], score["selected_count"]
                    censored, mse = score["selected_censored_count"], score["mse_bps2"]
                if available:
                    with localcontext() as ctx:
                        ctx.prec = 50
                        net = base._number((Decimal(score["gross_sum_bps"]) - trades * cost) / n)
                cells.append(
                    dict(
                        symbol=g["symbol"],
                        fold=g["fold"],
                        policy=policy,
                        cost_bps=cost,
                        observed_count=n,
                        trade_count=trades,
                        selected_count=selected,
                        action_sha256=score["action_sha256"] if score else None,
                        selected_censored_count=censored,
                        paired_mse_bps2=mse,
                        mean_net_bps=net,
                    )
                )
    comparisons = []
    for symbol in SYMBOLS:
        for window in WINDOWS:
            paired = [
                c
                for c in cells
                if c["symbol"] == symbol and c["policy"] == f"ridge{window}" and c["cost_bps"] == 20
            ]
            means = [
                c
                for c in cells
                if c["symbol"] == symbol and c["policy"] == "train_mean" and c["cost_bps"] == 20
            ]
            previous = [
                c
                for c in cells
                if c["symbol"] == symbol
                and c["policy"] == "previous_intraday"
                and c["cost_bps"] == 20
            ]
            comparisons.append(
                dict(
                    symbol=symbol,
                    window=window,
                    folds=[
                        dict(
                            fold=c["fold"],
                            paired_count=c["observed_count"],
                            ridge_mse_bps2=c["paired_mse_bps2"],
                            train_mean_mse_bps2=m["paired_mse_bps2"],
                            previous_mse_bps2=p["paired_mse_bps2"],
                            mean_net20_bps=c["mean_net_bps"],
                        )
                        for c, m, p in zip(paired, means, previous, strict=True)
                    ],
                )
            )
    return dict(
        **header(contract, pin),
        status="complete" if available else "input_unavailable",
        criterion="descriptive_only_no_selection",
        groups=groups,
        cells=cells,
        comparisons=comparisons,
    )


def failure(contract, pin, reason):
    require(reason in base.FAILURES, "failure_category")
    return dict(
        **header(contract, pin),
        status="failed",
        criterion=reason,
        groups=[],
        cells=[],
        comparisons=[],
    )


def validate_result(result, contract, pin):
    """Whitelist aggregates and regenerate derived cells with the same arithmetic."""
    if result.get("status") == "failed":
        require(
            encode(result) == encode(failure(contract, pin, result["criterion"])), "failure_shape"
        )
        return
    groups = result["groups"]
    require(len(groups) == 6, "group_count")
    count_fields = (
        "train_planned",
        "train_eligible",
        "train_observed",
        "train_censored",
        "train_blocks",
        "eval_planned",
        "eval_eligible",
        "eval_blocks",
        "eval_observed",
        "eval_censored",
        "eval_observed_blocks",
        "train_input_excluded",
        "eval_input_excluded",
    )
    available = all(
        g["counts"]["train_observed"] >= MIN_TRAIN and g["counts"]["eval_observed"] >= MIN_EVAL
        for g in groups
    )
    for g, (symbol, fold) in zip(
        groups, ((s, f) for s in SYMBOLS for f in contract["plan"]["folds"]), strict=True
    ):
        require(
            set(g) == {"symbol", "fold", "counts", "fits", "normalizer_sha256", "scores"}
            and (g["symbol"], g["fold"]) == (symbol, fold["fold"]),
            "group_fields",
        )
        c = g["counts"]
        require(set(c) == {*count_fields, "dates", "cohort_sha256"}, "count_fields")
        require(all(type(c[k]) is int and c[k] >= 0 for k in count_fields), "count_type")
        for phase, bounds in (("train", fold["train"]), ("eval", fold["evaluation"])):
            require(
                c[f"{phase}_planned"] == bounds[1] - bounds[0]
                and c[f"{phase}_observed"] + c[f"{phase}_censored"]
                == c[f"{phase}_eligible"]
                <= c[f"{phase}_planned"]
                and c[f"{phase}_eligible"] + c[f"{phase}_input_excluded"] == c[f"{phase}_planned"],
                "count_partition",
            )
        require(
            c["train_blocks"] <= c["train_observed"]
            and c["eval_observed_blocks"] <= c["eval_blocks"] <= c["eval_eligible"],
            "blocks",
        )
        days = contract["plan"]["days"]
        require(
            c["dates"]
            == dict(
                train_first=days[fold["train"][0]],
                train_last=days[fold["train"][1] - 1],
                eval_first=days[fold["evaluation"][0]],
                eval_last=days[fold["evaluation"][1] - 1],
                train_exit_before=fold["train_exit_before"],
            ),
            "dates",
        )
        for value in (c["cohort_sha256"], g["normalizer_sha256"]):
            require(
                value is None
                or (
                    type(value) is str
                    and len(value) == 71
                    and value.startswith("sha256:")
                    and all(x in "0123456789abcdef" for x in value[7:])
                ),
                "hash",
            )
        require(c["cohort_sha256"] is not None, "cohort_hash")
        fitted = c["train_observed"] >= MIN_TRAIN
        require(
            type(g["fits"]) is int
            and g["fits"] == (2 if fitted and c["eval_eligible"] else 0)
            and (g["normalizer_sha256"] is not None) == fitted,
            "fits",
        )
        require(len(g["scores"]) == (6 if fitted else 0), "scores_count")
        for score, policy in zip(g["scores"], POLICIES, strict=fitted):
            require(
                set(score)
                == {
                    "policy",
                    "selected_count",
                    "trade_count",
                    "selected_censored_count",
                    "gross_sum_bps",
                    "mse_bps2",
                    "action_sha256",
                }
                and score["policy"] == policy,
                "score_fields",
            )
            value = score["action_sha256"]
            require(
                type(value) is str
                and len(value) == 71
                and value.startswith("sha256:")
                and all(x in "0123456789abcdef" for x in value[7:]),
                "action_hash",
            )
            for k in ("selected_count", "trade_count", "selected_censored_count"):
                require(type(score[k]) is int and score[k] >= 0, "trade_count")
            require(
                score["trade_count"] + score["selected_censored_count"]
                == score["selected_count"]
                <= c["eval_eligible"]
                and score["trade_count"] <= c["eval_observed"]
                and score["selected_censored_count"] <= c["eval_censored"],
                "trade_partition",
            )
            for k in ("gross_sum_bps", "mse_bps2"):
                v = score[k]
                if not available:
                    require(v is None, "unavailable_metrics")
                    continue
                require(
                    (v is None and k == "mse_bps2" and policy in POLICIES[-2:])
                    or (
                        type(v) is str
                        and len(v) < 80
                        and Decimal(v).is_finite()
                        and base._number(Decimal(v)) == v
                    ),
                    "metric_type",
                )
            require(
                (score["mse_bps2"] is None) == (not available or policy in POLICIES[-2:]),
                "forecast_metric",
            )
            if score["mse_bps2"] is not None:
                require(Decimal(score["mse_bps2"]) >= 0, "mse_negative")
            if policy in POLICIES[-2:]:
                active = policy == "always_long"
                require(
                    score["selected_count"] == (c["eval_eligible"] if active else 0)
                    and score["trade_count"] == (c["eval_observed"] if active else 0),
                    "naive_action",
                )
            if available and not score["trade_count"]:
                require(Decimal(score["gross_sum_bps"]) == 0, "inactive_gross")
    require(
        encode(result) == encode(assemble(contract, pin, groups)), "result_binding_or_arithmetic"
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
    require(
        encode(json.loads(_read(output / "started.json"))) == encode({"contract_sha256": pin}),
        "attempt_binding",
    )
    try:
        check_time(deadline)
        snapshot = load_verified_tiingo_etf_d1_snapshot(
            market_data_root / base.SNAPSHOT,
            dataset_id=base.DATASET_ID,
            expected_dataset_hash=base.DATASET_HASH,
            expected_manifest_hash=base.MANIFEST_HASH,
            market_data_root=market_data_root,
            repo_root=REPO,
        )
        require(
            (
                snapshot.snapshot.dataset_id,
                snapshot.snapshot.dataset_hash,
                snapshot.snapshot.manifest_hash,
            )
            == (base.DATASET_ID, base.DATASET_HASH, base.MANIFEST_HASH),
            "loaded_source_binding",
        )
        result = evaluate(snapshot.rows_by_symbol, contract, pin, deadline=deadline)
        verify(artifact_root, market_data_root, pin)
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure")
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None
