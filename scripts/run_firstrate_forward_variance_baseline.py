"""One frozen, source-bound CPU variance comparison; replay never refits."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import time
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import run_firstrate_forward_variance_smoke as smoke

from thericher_v2.contracts import Timeframe
from thericher_v2.data.local import LocalCsvBarProvider
from thericher_v2.data.provider import BarQuery
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.campaign_registry import (
    register_campaign_outcome,
    register_frozen_campaign,
)
from thericher_v2.research.forward_variance_baseline import (
    SCALE_FLOOR,
    ForwardVarianceBaseline,
    ForwardVarianceBaselineConfig,
    ForwardVarianceRecord,
    _inputs,
    _target,
    compare_forward_variance_baseline,
    fit_forward_variance_baseline,
    predict_forward_variance_baseline,
)
from thericher_v2.research.forward_variance_evaluation import evaluate_variance_baselines
from thericher_v2.research.forward_variance_smoke import MINUTE, SYMBOLS, build_variance_smoke_case
from thericher_v2.research.intraday_variance_targets import build_intraday_variance_target

STUDY = "firstrate-forward-risk-baseline-development-20261007-v1"
SMOKE_CONTRACT = "sha256:ae8bffb356c82d4a99f885ce17aecf7e1b14ac12822e317efcaac95b183a2e11"
SMOKE_RESULT = "sha256:d7d3761265f6484b52db5e00c8f1a26fee7ba24e853da4e67bdc634179832ce8"
CODE = smoke.CODE + (
    "scripts/run_firstrate_forward_variance_baseline.py",
    "src/thericher_v2/research/forward_variance_baseline.py",
    "src/thericher_v2/research/forward_variance_evaluation.py",
    "src/thericher_v2/research/campaign_registry.py",
    "src/thericher_v2/research/artifact_paths.py",
)
FEATURES = ("own_past119_open_variance", "peer_past119_open_variance")
REPO = Path(__file__).resolve().parents[1]


def contract(pins):
    return {
        "study": STUDY,
        "grade": "non_promoting_seen_forward_risk_development",
        "smoke_contract_sha256": SMOKE_CONTRACT,
        "smoke_result_sha256": SMOKE_RESULT,
        "normalization_sha256": smoke.NORMALIZATION_HASH,
        "lineage_sha256": smoke.PARENT_HASH,
        "source_sha256": smoke.SOURCES,
        "scheduled_date_set_sha256": smoke.DATE_HASH,
        "split": {
            "scheduled": 251,
            "train": 160,
            "embargo": 1,
            "comparison": 90,
            "halves": [45, 45],
        },
        "decision": "min(open+150min,close-10min)",
        "features": list(FEATURES),
        "geometry": {
            "past_bars": 120,
            "past_returns": 119,
            "horizon": 60,
            "target_bars": 61,
            "target_available_minutes": 62,
        },
        "fit": "one L2=1 log-variance ridge per ETF; TRAIN-only population scaling",
        "controls": ["own_past_variance_times60_over119", "same_positive_TRAIN_mean"],
        "loss": "normalized_QLIKE_common_positive_target_cohort",
        "missingness": "scheduled split before exclusions; zero targets excluded, never floored",
        "kill": "ridge must strictly beat both controls for each ETF, all90/each45, "
        "and every shared-date deletion; future comparison outcomes cannot alter "
        "TRAIN state or prior predictions; future bars cannot alter causal inputs",
        "compute": {
            "cpu": 2,
            "memory_bytes": 2147483648,
            "seconds": 120,
            "image": smoke.IMAGE,
            "network": "none",
            "source": "read_only",
        },
        "runtime": {"python": "3.12.15", "numpy": "2.5.1", "pandas-market-calendars": "5.4.0"},
        "model_retention": "numeric JSON only outside Git; inference/loss replay without refit",
        "TRAIN_attestation": "exact cohort/scalers/intercept/mean and normal-equation residual",
        "normal_equation_atol": 1e-10,
        "costs": "not_applicable_variance_prediction_no_trades_or_PnL",
        "holdout": "none",
        "gpu": False,
        "paper_input": False,
        "limitations": [
            "seen/revised historical source; not independent validation",
            "source start convention assumed; actions/finality/PIT unqualified",
            "shared ETF date blocks, not independent samples",
            "physical parsing is not target-isolated",
            "conditional complete-case variance scores, not returns/profit",
        ],
        "code_sha256": pins,
    }


def check_pins(plan, market, lineage, normalization, preparation):
    smoke.require(plan == contract(plan["code_sha256"]), "contract_changed")
    smoke.require(set(plan["code_sha256"]) == set(CODE), "code_pin_set_changed")
    smoke.require(
        smoke.file_hash(preparation / "contract.json") == SMOKE_CONTRACT, "smoke_contract_changed"
    )
    smoke.require(
        smoke.file_hash(preparation / "result.json") == SMOKE_RESULT, "smoke_result_changed"
    )
    specs = smoke.check_metadata(lineage, normalization)
    for relative, pin in plan["code_sha256"].items():
        smoke.require(smoke.file_hash(REPO / relative) == pin, "code_changed")
    for spec in specs:
        source = market / spec.canonical_market_data_relative_path
        smoke.require(source.stat().st_size <= 134217728, "source_size_limit")
        smoke.require(smoke.file_hash(source) == smoke.SOURCES[spec.symbol], "source_changed")
    return specs


def register(plan, root, artifact_base):
    return register_frozen_campaign(
        contract_hash=smoke.file_hash(root / "contract.json"),
        dataset_hash=smoke.digest(smoke.encode(plan["source_sha256"])),
        split_hash=smoke.digest(smoke.encode([plan["scheduled_date_set_sha256"], plan["split"]])),
        cost_model_hash=smoke.digest(smoke.encode(plan["costs"])),
        trial_family="firstrate-forward-risk-baseline-development-v1",
        holdout_access="none",
        artifact_root=artifact_base,
        repo_root=REPO,
    )


def freeze(root, market, lineage, normalization, preparation, artifact_base):
    plan = contract({relative: smoke.file_hash(REPO / relative) for relative in CODE})
    check_pins(plan, market, lineage, normalization, preparation)
    if root.exists():
        smoke.require(
            (root / "contract.json").read_bytes() == smoke.encode(plan) + b"\n",
            "existing_contract_mismatch",
        )
    else:
        root.mkdir(parents=True, exist_ok=False)
        smoke.write_once(root / "contract.json", plan)
    registered = register(plan, root, artifact_base)
    return {
        "status": "frozen_before_source_value_parse",
        "contract_sha256": smoke.file_hash(root / "contract.json"),
        "registry_sha256": registered.record_sha256,
        "actual_fits": 0,
    }


def load_source_cases(specs, market, deadline):
    streams, calendars = {}, []
    for spec in specs:
        smoke.require(time.monotonic() < deadline, "compute_stop")
        bars = LocalCsvBarProvider(market / spec.canonical_market_data_relative_path).get_bars(
            BarQuery(symbol=spec.symbol, market="US", timeframe=Timeframe.M1)
        )
        smoke.validate_firstrate_canonical_bars(bars, spec)
        streams[spec.symbol] = bars
        calendars.append(smoke.regular_sessions(bars))
    smoke.require(calendars[0] == calendars[1], "source_calendar_mismatch")
    sessions = tuple(SessionWindow(*pair) for pair in calendars[0])
    dates = tuple(session.open_ts.date() for session in sessions)
    smoke.require(
        len(dates) == 251
        and smoke.digest(("\n".join(day.isoformat() for day in dates) + "\n").encode())
        == smoke.DATE_HASH,
        "scheduled_dates_changed",
    )
    lookup = {session.open_ts.date(): session for session in sessions}
    grouped = {symbol: {day: [] for day in dates} for symbol in SYMBOLS}
    for symbol, bars in streams.items():
        for bar in bars:
            session = lookup.get(bar.start_ts.date())
            if session is not None and session.open_ts <= bar.start_ts < session.close_ts:
                grouped[symbol][bar.start_ts.date()].append(bar)
    return sessions, grouped


def records_from_pair(pair, session):
    case = build_variance_smoke_case(*pair, session=session)
    variances = None
    if case.context is not None:
        variances = tuple(
            build_intraday_variance_target(
                bars,
                symbol=symbol,
                session=session,
                decision_at=case.decision_at - 121 * MINUTE,
                observed_at=case.decision_at,
                horizon_minutes=119,
            ).realized_variance
            for symbol, bars in zip(
                SYMBOLS, (case.context.own_bars, case.context.peer_bars), strict=True
            )
        )
    rows = []
    for index, support in enumerate(case.targets):
        features = None if variances is None else (variances[index], variances[1 - index])
        rows.append(
            ForwardVarianceRecord(
                session.open_ts.date(),
                support.symbol,
                case.decision_at,
                None if variances is None else case.decision_at,
                features,
                None if variances is None else variances[index],
                support.target,
                case.input_status,
                support.status,
            )
        )
    return tuple(rows)


def jsonable(value):
    return json.loads(json.dumps(value, default=lambda item: item.isoformat(), allow_nan=False))


def commitment(rows):
    return smoke.digest(smoke.encode([jsonable(asdict(row)) for row in rows]))


def read_model(payload, config):
    smoke.require(payload["config"] == jsonable(asdict(config)), "model_config_mismatch")
    expected = set(ForwardVarianceBaseline.__dataclass_fields__)
    smoke.require(
        set(payload) == expected and payload["scope"] == "non_promoting_forward_risk",
        "model_payload_invalid",
    )
    return ForwardVarianceBaseline(
        config,
        tuple(payload["feature_mean"]),
        tuple(payload["feature_scale"]),
        tuple(payload["coefficients"]),
        payload["intercept"],
        payload["train_mean_variance"],
        datetime.fromisoformat(payload["train_available_through"]),
        tuple(
            (date.fromisoformat(day), tuple(exclusions))
            for day, exclusions in payload["training_rows"]
        ),
    )


def attest_train(model, rows, tolerance):
    audit, eligible = [], []
    for row in rows:
        value, target_exclusions = _target(row, model.config)
        exclusions = _inputs(row, model.config) + target_exclusions
        audit.append((row.session_date, exclusions))
        if not exclusions:
            eligible.append((row, value))
    smoke.require(
        tuple(audit) == model.training_rows and len(eligible) >= 2, "TRAIN_cohort_mismatch"
    )
    x = np.asarray([row.features for row, _ in eligible], dtype=np.float64)
    y = np.asarray([value for _, value in eligible], dtype=np.float64)
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), SCALE_FLOOR)
    z, log_y = (x - mean) / scale, np.log(y)
    smoke.require(
        tuple(mean) == model.feature_mean
        and tuple(scale) == model.feature_scale
        and float(log_y.mean()) == model.intercept
        and float(y.mean()) == model.train_mean_variance
        and max(row.target.available_at for row, _ in eligible) == model.train_available_through,
        "TRAIN_transform_mismatch",
    )
    residual = (z.T @ z + np.eye(2)) @ model.coefficients - z.T @ (log_y - model.intercept)
    smoke.require(
        np.isfinite(residual).all() and float(np.max(np.abs(residual))) <= tolerance,
        "TRAIN_normal_equation_mismatch",
    )
    return {
        "scheduled": len(rows),
        "eligible": len(eligible),
        "excluded": len(rows) - len(eligible),
        "exclusions": dict(Counter(reason for _, reasons in audit for reason in reasons)),
    }


def compute(plan, market, lineage, normalization, preparation, deadline, models=None):
    smoke.require(platform.python_version() == plan["runtime"]["python"], "python_version")
    smoke.require(importlib.metadata.version("numpy") == plan["runtime"]["numpy"], "numpy_version")
    smoke.require(
        importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version"
    )
    specs = check_pins(plan, market, lineage, normalization, preparation)
    sessions, grouped = load_source_cases(specs, market, deadline)
    rows = {symbol: [] for symbol in SYMBOLS}
    mutations = Counter()
    for index, session in enumerate(sessions):
        smoke.require(time.monotonic() < deadline, "compute_stop")
        day = session.open_ts.date()
        pair = tuple(tuple(grouped[symbol][day]) for symbol in SYMBOLS)
        original = records_from_pair(pair, session)
        at = original[0].decision_at
        prefix = tuple(tuple(bar for bar in stream if bar.start_ts < at) for stream in pair)
        prefix_rows = records_from_pair(prefix, session)
        smoke.require(
            all(
                replace(a, target=None, target_status="not_inspected")
                == replace(b, target=None, target_status="not_inspected")
                for a, b in zip(original, prefix_rows, strict=True)
            ),
            "future_dependent_features",
        )
        mutations["prefix_future_removal"] += 1
        if index >= 161:
            for support_edit in (False, True):
                edited = tuple(
                    tuple(
                        replace(bar, complete=False)
                        if support_edit and bar.start_ts >= at
                        else replace(
                            bar,
                            open=bar.open * 3,
                            high=bar.high * 3,
                            low=bar.low * 3,
                            close=bar.close * 3,
                            volume=bar.volume * 7,
                        )
                        if not support_edit and bar.start_ts == at + MINUTE
                        else bar
                        for bar in stream
                    )
                    for stream in pair
                )
                changed = records_from_pair(edited, session)
                smoke.require(
                    all(
                        replace(a, target=None, target_status="not_inspected")
                        == replace(b, target=None, target_status="not_inspected")
                        for a, b in zip(original, changed, strict=True)
                    ),
                    "future_mutation_changed_features",
                )
                mutations[
                    "comparison_future_support" if support_edit else "comparison_future_value"
                ] += 1
        for row in original:
            rows[row.symbol].append(row)
    del grouped
    dates = tuple(session.open_ts.date() for session in sessions)
    state, comparisons, training, model_payload, commits = {}, {}, {}, {}, {}
    for symbol in SYMBOLS:
        smoke.require(time.monotonic() < deadline, "compute_stop")
        config = ForwardVarianceBaselineConfig(symbol, FEATURES, dates[159], dates[161], 60, 119)
        train, later = tuple(rows[symbol][:160]), tuple(rows[symbol][161:])
        model = (
            fit_forward_variance_baseline(train, config=config)
            if models is None
            else read_model(models[symbol], config)
        )
        training[symbol] = attest_train(model, train, plan["normal_equation_atol"])
        model_payload[symbol] = jsonable(asdict(model))
        later_without_targets = tuple(
            replace(row, target=None, target_status="not_inspected") for row in later
        )
        predictions = predict_forward_variance_baseline(model, later)
        smoke.require(
            predictions == predict_forward_variance_baseline(model, later_without_targets),
            "target_dependent_forecast",
        )
        mutations["target_blind_forecast"] += len(later)
        comparisons[symbol] = compare_forward_variance_baseline(model, later)
        state[symbol] = [jsonable(asdict(row)) for row in comparisons[symbol].rows]
        commits[symbol] = {
            "TRAIN": commitment(train),
            "comparison": commitment(later),
            "forecasts_and_losses": smoke.digest(smoke.encode(state[symbol])),
        }
    report = evaluate_variance_baselines(comparisons, comparison_dates=dates[161:])
    check_pins(plan, market, lineage, normalization, preparation)
    smoke.require(time.monotonic() < deadline, "compute_stop")
    result = {
        "status": "non_promoting_completed",
        "grade": plan["grade"],
        "study": STUDY,
        "scheduled": {"TRAIN": 160, "embargo": 1, "comparison": 90},
        "training": training,
        "comparison": report,
        "mutation_checks": dict(mutations),
        "commitments": commits,
        "model_sha256": smoke.digest(smoke.encode(model_payload)),
        "recipe_actual_fits": 2,
        "gpu": False,
        "holdout": False,
        "paper_input": False,
        "broker_calls": 0,
        "raw_market_rows_retained": False,
    }
    return jsonable(result), model_payload


def read_replay(root, result_pin):
    raw = (root / "result.json").read_bytes()
    smoke.require(smoke.digest(raw) == result_pin, "exact_result_pin_required")
    expected = json.loads(raw)
    models = json.loads((root / "models.json").read_bytes())
    smoke.require(smoke.digest(smoke.encode(models)) == expected["model_sha256"], "model_changed")
    return models, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", nargs="?", choices=("plan", "freeze", "run", "verify"), default="plan"
    )
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--artifact-base", type=Path)
    parser.add_argument("--market-root", type=Path)
    parser.add_argument("--normalization", type=Path)
    parser.add_argument("--lineage", type=Path)
    parser.add_argument("--preparation-root", type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    args = parser.parse_args()
    started = time.monotonic()
    try:
        if args.mode == "plan":
            print(
                json.dumps({"status": "plan", "study": STUDY, "actual_fits": 0, "broker_calls": 0})
            )
            return 0
        required = (
            args.artifact_root,
            args.artifact_base,
            args.market_root,
            args.normalization,
            args.lineage,
            args.preparation_root,
        )
        smoke.require(all(item is not None for item in required), "explicit_paths_required")
        allowed = (Path("D:/thericher-v2/model-artifacts/research") / STUDY).resolve()
        smoke.require(
            args.artifact_root.resolve() == (allowed if os.name == "nt" else Path("/study")),
            "artifact_root_outside_scope",
        )
        if args.mode == "freeze":
            result = freeze(
                args.artifact_root,
                args.market_root,
                args.lineage,
                args.normalization,
                args.preparation_root,
                args.artifact_base,
            )
        else:
            root = args.artifact_root
            raw = (root / "contract.json").read_bytes()
            smoke.require(smoke.digest(raw) == args.contract_sha256, "exact_contract_pin_required")
            plan = json.loads(raw)
            models = None
            if args.mode == "run":
                smoke.require(not (root / "result.json").exists(), "result_already_exists")
                register(plan, root, args.artifact_base)
                smoke.write_once(
                    root / "attempt.json",
                    {
                        "started_at": datetime.now(UTC).isoformat(),
                        "contract_sha256": args.contract_sha256,
                    },
                )
            else:
                models, expected_result = read_replay(root, args.result_sha256)
            result, fitted = compute(
                plan,
                args.market_root,
                args.lineage,
                args.normalization,
                args.preparation_root,
                started + 120,
                models,
            )
            result["contract_sha256"] = args.contract_sha256
            if args.mode == "run":
                smoke.write_once(root / "models.json", fitted)
                smoke.write_once(root / "result.json", result)
                register_campaign_outcome(
                    contract_hash=args.contract_sha256,
                    outcome_class="non_promoting_completed",
                    outcome_reference_sha256=smoke.file_hash(root / "result.json"),
                    artifact_root=args.artifact_base,
                    repo_root=REPO,
                )
            else:
                smoke.require(
                    smoke.digest(smoke.encode(models)) == result["model_sha256"], "model_changed"
                )
                smoke.require(expected_result == result, "readback_mismatch")
                result = {**result, "status": "verified_all_ro_no_refit", "verification_fits": 0}
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        reason = (
            str(error) if isinstance(error, smoke.SmokeFault) else "source_or_contract_reader_fault"
        )
        print(
            json.dumps(
                {"status": "input_unavailable", "reason": reason, "raw_error_suppressed": True}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
