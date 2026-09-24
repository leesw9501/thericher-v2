"""Seen-data policy composition, using existing same-session local-paper replay."""

from __future__ import annotations

import importlib.metadata
import json
import math
import re
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_position_policy as positions
from thericher_v2.research import tiingo_month_start_development as artifacts
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory
from thericher_v2.research.campaign_registry import register_frozen_campaign

sessions, h30 = positions.sessions, positions.h30
REPO = h30.REPO
NAME = "firstrate-m5-policy-graph-development-v1"
SECONDS = 900
COSTS = (1, 3, 5, 10)
POLICIES = (
    "trend",
    "reversion",
    "ridge",
    "majority",
    "gate",
    "without_trend",
    "without_reversion",
    "without_ridge",
    "always_flat",
    "always_long",
)
encode, digest, require = artifacts.encode, artifacts.digest, artifacts.require
atomic_new, _read = artifacts.atomic_new, artifacts._read
CODE = tuple(
    dict.fromkeys(
        (
            *positions.CODE,
            "src/thericher_v2/research/firstrate_policy_graph.py",
            "src/thericher_v2/research/policy_graph_models.py",
            "src/thericher_v2/research/policy_graph_replay.py",
            "scripts/run_firstrate_policy_graph.py",
            "scripts/run_tiingo_month_start_development.py",
            "src/thericher_v2/research/tiingo_month_start_development.py",
            "src/thericher_v2/research/artifact_paths.py",
            "src/thericher_v2/research/campaign_registry.py",
            "src/thericher_v2/research/validation.py",
            "src/thericher_v2/contracts.py",
            "src/thericher_v2/data/provider.py",
            "src/thericher_v2/data/resample.py",
            "src/thericher_v2/execution/emergency.py",
            "src/thericher_v2/state/event_log.py",
        )
    )
)


def configuration():
    return dict(
        symbols=list(h30.SYMBOLS),
        policies=list(POLICIES),
        horizon_minutes=30,
        context_bars=36,
        costs_bps_per_side=list(COSTS),
        paired_cells=160,
        policy_cells=320,
        quantity=1,
        slippage_bps=0,
        calendar="pandas-market-calendars==5.4.0 NYSE regular/early-close sessions",
        decisions=(
            "every30min from open+180min; H30 exit strictly before close; last full-day15:00ET"
        ),
        bars="pinned canonical M1 start timestamps; existing UTC-aligned complete M5 resampler",
        training="every5min; same36 past bars; future TRAIN labels may be censored",
        split="first50%->next25%; first75%->last25% of source calendar sessions",
        purge="TRAIN exit strictly before first scheduled EVAL history start",
        experts=dict(
            trend="past close SMA3>SMA12",
            reversion="last completed close < mean12-std12; population std",
            ridge="alpha1/SVD/intercept; 36x4; TRAIN-only channel scaler; grossbps>6",
        ),
        blend="at least2/3 votes; each leave-one-out requires both remaining votes",
        decision_basis=(
            "fixed3bps/side standalone; cost/planner sweep only re-accounts fixed targets"
        ),
        gate=dict(
            estimator="DecisionTreeRegressor depth2 min_samples_leaf64 random_state811",
            features="three votes; SMA3/SMA12-1; lastclose/mean12-1; body std12",
            target="three votes times standalone exact3bps/side netH30bps",
            choice="largest expectedutility>0 and chosen expert active else cash; fixed tie order",
            oof="three expanding TRAIN-date quarters; label exit < next history start",
            inputs="no position, evaluation target, future availability or price level",
            minimums="inner train128; pooled OOF128; no profitability prerequisite",
        ),
        fit_budget=dict(ridge=16, tree=4, gpu=False, wall_seconds=SECONDS, passes=1),
        holding="same frozen targets: independent H30 vs merge adjacent selected intervals",
        terminal="flat before close; never bridge gap, missing input, session or fold",
        censoring="whole affected session for all policies AFTER freezing every target",
        sizing="one share; independent spans, not multiasset NAV or capital allocation",
        risk="cumulative fixed-share marked PnL drawdown at M5 opens and fee instants",
        comparison="every policy versus majority on matched support; no selected winner",
        kill_test=(
            "future/EVAL labels affect earlier targets or TRAIN scaling; "
            "OOF timing leaks; policies differ in scoring support; "
            "gross/exposure or eliminated-fee identities fail"
        ),
        limits=[
            "already_seen_outcome_informed_not_holdout",
            "expanding_folds_and_correlated_ETFs_not_independent",
            "source_clock_finality_revision_unverified",
            "no_overnight_or_corporate_action_reconstruction",
            "posthoc_common_session_censoring_not_live_rule",
            "tree_label_standalone_cost_not_actual_switching_or_persistent_policy_utility",
            "6bps_gross_vote_is_nominal_hurdle_not_exact_net_breakeven",
            "cost_and_planner_cells_are_dependent_accounting_sensitivity_not_new_evidence",
            "fees_only_zero_latency_no_KIS_parity",
            "drawdown_at_bar_opens_not_intrabar_high_low",
            "no_statistical_significance_or_causal_attribution_claim",
        ],
        lineage=[h30.FAMILY, sessions.NAME, positions.NAME],
        promotion=False,
        holdout=False,
        selection=False,
        broker_input=False,
        fitted_weights_retained=False,
        image=sessions.IMAGE,
        resources="oneCPU/twoGiB/networknone/readonlysourceanddata/externalartifacts",
    )


def proposed_contract(root):
    receipt = _read(Path(root) / h30.RECEIPT)
    pins = h30.contract_payload(receipt)["source_pins"]
    config = configuration()
    return dict(
        schema_version=1,
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source_pins=pins,
        receipt_sha256=digest(receipt),
        runtime={
            p: importlib.metadata.version(p)
            for p in ("numpy", "scikit-learn", "pandas-market-calendars")
        },
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def header(contract, pin):
    require(digest(encode(contract)) == pin, "contract_hash")
    require(contract["config"] == configuration(), "config_changed")
    require(contract["config_sha256"] == digest(encode(configuration())), "config_hash")
    return dict(
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        evidence_grade="OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
    )


def register_contract(root, contract, pin):
    header(contract, pin)
    register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=digest(encode(contract["source_pins"])),
        split_hash=digest(encode([configuration()[k] for k in ("split", "purge")])),
        cost_model_hash=digest(encode([COSTS, "exact_local_paper_repeated_and_merged"])),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root, market_data_root):
    require(h30.source_root_allowed(Path(market_data_root).resolve(), REPO), "source_root")
    contract = proposed_contract(artifact_root)
    output = ensure_external_artifact_directory(artifact_root, REPO, "research") / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root, market_data_root, pin):
    require(h30.source_root_allowed(Path(market_data_root).resolve(), REPO), "source_root")
    output = ensure_external_artifact_directory(artifact_root, REPO, "research", NAME)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin and raw == encode(proposed_contract(artifact_root)), "binding")
    return output, json.loads(raw)


def training_arrays(index, plan):
    train_times, eval_times, cutoff, _ = plan
    train_obs, train_counts = h30.observe(index, train_times)
    train_out, censor = sessions.outcomes(index, train_obs, 30)
    pairs = [(o, y) for o, y in zip(train_obs, train_out, strict=True) if y is not None]
    evaluation, eval_counts = h30.observe(index, eval_times)
    require(128 <= len(pairs) <= 40000, "train_support")
    require(h30.blocks([o for o, _ in pairs]) >= 16, "train_blocks")
    require(len(evaluation) >= 32 and h30.blocks(evaluation) >= 8, "eval_support")
    require(all(y.bars[-1].start_ts < cutoff for _, y in pairs), "train_purge")

    def closes(observations):
        return np.asarray(
            [
                [float(index[o.at - n * h30.STEP].close) for n in range(36, 0, -1)]
                for o in observations
            ]
        )

    fitted = [o for o, _ in pairs]
    net = []
    for _, out in pairs:
        fees = sum(
            ((p * 3 / 10000).quantize(Decimal("0.0001")) for p in (out.entry, out.exit)), Decimal(0)
        )
        net.append(float((out.exit - out.entry - fees) / out.entry * 10000))
    return (
        dict(
            train_x=np.asarray([o.features for o in fitted], dtype=np.float64),
            train_closes=closes(fitted),
            train_times=tuple(o.at for o in fitted),
            train_y=np.asarray([out.target_bps for _, out in pairs]),
            train_net_y=np.asarray(net),
            eval_x=np.asarray([o.features for o in evaluation], dtype=np.float64),
            eval_closes=closes(evaluation),
            eval_times=tuple(o.at for o in evaluation),
        ),
        evaluation,
        dict(
            training_inputs=train_counts,
            training_outcomes=censor,
            evaluation_inputs=eval_counts,
            train_rows=len(fitted),
        ),
    )


def compare(streams, contract, pin, emergency, deadline):
    from thericher_v2.research.policy_graph_models import fit_predict_graph
    from thericher_v2.research.policy_graph_replay import compare_policy, make_cached_payoff

    header(contract, pin)
    folds, cells = [], []
    for symbol, bars in streams:
        h30.check_time(deadline)
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        schedule = sessions.regular_sessions(bars)
        for number, plan in enumerate(sessions.plans(schedule, 30), 1):
            arrays, observations, facts = training_arrays(index, plan)
            prediction = fit_predict_graph(**arrays, deadline=deadline)
            require(tuple(prediction.targets) == POLICIES, "policy_order")
            require(
                all(
                    isinstance(v, np.ndarray)
                    and v.dtype == np.dtype(bool)
                    and v.shape == (len(observations),)
                    for v in prediction.targets.values()
                ),
                "policy_target_shape",
            )
            keys = positions.session_keys(observations, schedule)
            # All experts, fusion and target states exist before reading EVAL outcomes.
            frozen = {
                key: np.array(value, dtype=bool, copy=True)
                for key, value in prediction.targets.items()
            }
            outcomes, _ = sessions.outcomes(index, observations, 30)
            keep, support = positions.common_support(observations, outcomes, keys)
            folds.append(
                dict(
                    symbol=symbol,
                    fold=number,
                    **facts,
                    support=support,
                    model_facts=prediction.diagnostics,
                )
            )
            replay = make_cached_payoff()
            for cost in COSTS:
                for policy in POLICIES:
                    ident = dict(
                        symbol=symbol,
                        fold=number,
                        horizon_minutes=30,
                        candidate=policy,
                        context=36,
                        seed=None,
                    )
                    cell = compare_policy(
                        ident=ident,
                        observations=observations,
                        outcomes=outcomes,
                        selected=frozen[policy],
                        keys=keys,
                        keep=keep,
                        cost=cost,
                        emergency=emergency,
                        deadline=deadline,
                        replay=replay,
                    )
                    cells.append(cell)
            h30.check_time(deadline)
    result = dict(
        **header(contract, pin),
        status="complete",
        criterion="descriptive_no_selection",
        folds=folds,
        cells=cells,
        comparisons=comparisons(cells),
    )
    validate_result(result, contract, pin)
    return result


def comparisons(cells):
    lookup = {(c["symbol"], c["fold"], c["cost_bps_per_side"], c["candidate"]): c for c in cells}
    result = []
    for c in cells:
        baseline = lookup[c["symbol"], c["fold"], c["cost_bps_per_side"], "majority"]
        result.append(
            dict(
                symbol=c["symbol"],
                fold=c["fold"],
                cost_bps_per_side=c["cost_bps_per_side"],
                candidate=c["candidate"],
                persistent_net_delta_vs_majority=str(
                    Decimal(c["persistent"]["net_dollars"])
                    - Decimal(baseline["persistent"]["net_dollars"])
                ),
                persistent_roundtrip_delta_vs_majority=(
                    c["persistent"]["roundtrips"] - baseline["persistent"]["roundtrips"]
                ),
            )
        )
    return result


def failure(contract, pin, reason):
    require(reason in artifacts.FAILURES, "failure_reason")
    return dict(
        **header(contract, pin),
        status="failed",
        criterion=reason,
        folds=[],
        cells=[],
        comparisons=[],
    )


def _keys(record, names, nested=()):
    require(type(record) is dict and set(record) == set(names.split()), "nested_result_keys")
    for key, value in record.items():
        if key in nested:
            continue
        require(value is None or type(value) in (str, int, float, bool), "result_scalar")
        if type(value) is float:
            require(math.isfinite(value), "result_finite")
        if key.endswith("_sha256"):
            require(
                type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value), "result_hash"
            )


def _fold_shape(fold):
    _keys(
        fold,
        "symbol fold training_inputs training_outcomes evaluation_inputs "
        "train_rows support model_facts",
        nested=(
            "training_inputs",
            "training_outcomes",
            "evaluation_inputs",
            "support",
            "model_facts",
        ),
    )
    for key in ("training_inputs", "evaluation_inputs"):
        _keys(fold[key], "scheduled eligible past_missing past_incomplete")
    _keys(fold["training_outcomes"], "eligible observed future_missing")
    _keys(
        fold["support"],
        "eligible_decisions raw_future_missing censored_sessions "
        "common_censored_decisions common_scored_decisions common_scored_blocks",
    )
    model = fold["model_facts"]
    _keys(
        model,
        "train_count eval_count oof_count ridge_fits tree_fits "
        "decision_cost_bps_per_side gate_depth gate_leaves train_last eval_first "
        "outer_label_end outer_history_start inner final oof_sha256 gate_sha256 "
        "gate_choice_counts gate_leaf_ids gate_leaf_train_counts gate_leaf_eval_counts "
        "mean_chosen_gate_utility_bps target_sha256",
        nested=(
            "inner",
            "final",
            "target_sha256",
            "gate_choice_counts",
            "gate_leaf_ids",
            "gate_leaf_train_counts",
            "gate_leaf_eval_counts",
        ),
    )
    require(type(model["inner"]) is list and len(model["inner"]) == 3, "inner_matrix")
    for inner in model["inner"]:
        _keys(
            inner,
            "train_count validation_count train_last train_label_end "
            "validation_first validation_last validation_history_start train_times_sha256 "
            "validation_times_sha256 scaler_sha256 model_sha256",
        )
    _keys(model["final"], "scaler_sha256 model_sha256")
    _keys(model["target_sha256"], " ".join(POLICIES))
    require(
        all(
            type(v) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", v)
            for v in model["target_sha256"].values()
        ),
        "target_hashes",
    )
    for key in (
        "gate_choice_counts",
        "gate_leaf_ids",
        "gate_leaf_train_counts",
        "gate_leaf_eval_counts",
    ):
        require(
            type(model[key]) is list and all(type(v) is int and v >= 0 for v in model[key]),
            "gate_counts",
        )
    require(
        len(model["gate_choice_counts"]) == 4
        and sum(model["gate_choice_counts"]) == model["eval_count"]
        and model["decision_cost_bps_per_side"] == 3,
        "decision_basis",
    )


def validate_result(result, contract, pin):
    if result.get("status") == "failed":
        require(
            encode(result) == encode(failure(contract, pin, result["criterion"])), "failed_shape"
        )
        return
    require(
        set(result)
        == {*header(contract, pin), "status", "criterion", "folds", "cells", "comparisons"},
        "result_keys",
    )
    require(all(result[k] == v for k, v in header(contract, pin).items()), "result_header")
    require(
        result["status"] == "complete" and result["criterion"] == "descriptive_no_selection",
        "result_status",
    )
    expected = [
        (s, f, cost, p) for s in h30.SYMBOLS for f in (1, 2) for cost in COSTS for p in POLICIES
    ]
    require(
        [(c["symbol"], c["fold"], c["cost_bps_per_side"], c["candidate"]) for c in result["cells"]]
        == expected,
        "cell_matrix",
    )
    require(
        [(f["symbol"], f["fold"]) for f in result["folds"]]
        == [(s, f) for s in h30.SYMBOLS for f in (1, 2)],
        "fold_matrix",
    )
    support = {(f["symbol"], f["fold"]): f["support"] for f in result["folds"]}
    for fold in result["folds"]:
        _fold_shape(fold)
        facts, model = fold["support"], fold["model_facts"]
        require(
            model["ridge_fits"] == 4
            and model["tree_fits"] == 1
            and model["train_count"] == fold["train_rows"]
            and model["eval_count"] == facts["eligible_decisions"]
            and model["oof_count"] >= 128
            and model["gate_depth"] <= 2
            and 1 <= model["gate_leaves"] <= 4,
            "model_budget",
        )
        require(
            all(type(v) is int and v >= 0 for v in facts.values())
            and facts["eligible_decisions"]
            == facts["common_scored_decisions"] + facts["common_censored_decisions"]
            and facts["raw_future_missing"] <= facts["common_censored_decisions"]
            and facts["common_scored_decisions"] >= 32
            and facts["common_scored_blocks"] >= 8,
            "fold_support",
        )
    identities = {}
    for cell in result["cells"]:
        _keys(
            cell,
            "symbol fold horizon_minutes candidate context seed cost_bps_per_side "
            "selected_decisions selected_censored decision_sha256 repeated persistent "
            "removed_boundary_pairs saved_fees_dollars saved_turnover_dollars risk",
            nested=("repeated", "persistent", "risk"),
        )
        for kind in ("repeated", "persistent"):
            _keys(
                cell[kind],
                "roundtrips fills wins gross_dollars fees_dollars net_dollars "
                "turnover_dollars exposure_minutes exposure_sha256 terminal_flat "
                "local_paper_replay_parity",
            )
        positions.validate_pair(cell)
        require(set(cell["risk"]) == {"repeated", "persistent"}, "risk_keys")
        for kind, risk in cell["risk"].items():
            require(
                set(risk)
                == {
                    "max_mark_to_market_drawdown_dollars",
                    "max_holding_minutes",
                    "mean_holding_minutes",
                },
                "risk_keys",
            )
            drawdown = Decimal(risk["max_mark_to_market_drawdown_dollars"])
            require(
                drawdown.is_finite()
                and drawdown >= 0
                and 0 <= risk["mean_holding_minutes"] <= risk["max_holding_minutes"] <= 180,
                "risk_bounds",
            )
            require(
                (cell[kind]["roundtrips"] == 0) == (risk["max_holding_minutes"] == 0),
                "holding_consistency",
            )
            if kind == "repeated" and cell[kind]["roundtrips"]:
                require(
                    risk["max_holding_minutes"] == risk["mean_holding_minutes"] == 30,
                    "repeated_holding",
                )
        require(
            cell["context"] == 36 and cell["seed"] is None and cell["horizon_minutes"] == 30,
            "cell_identity",
        )
        facts = support[cell["symbol"], cell["fold"]]
        require(
            0
            <= cell["selected_censored"]
            <= cell["selected_decisions"]
            <= facts["eligible_decisions"],
            "support",
        )
        require(
            cell["selected_decisions"] - cell["selected_censored"]
            <= facts["common_scored_decisions"],
            "support",
        )
        key = cell["symbol"], cell["fold"], cell["candidate"]
        decision = cell["decision_sha256"], cell["selected_decisions"], cell["selected_censored"]
        require(identities.setdefault(key, decision) == decision, "cost_changes_decisions")
        for kind in ("repeated", "persistent"):
            path = tuple(
                cell[kind][k]
                for k in (
                    "gross_dollars",
                    "turnover_dollars",
                    "exposure_minutes",
                    "exposure_sha256",
                    "roundtrips",
                )
            )
            require(identities.setdefault((*key, kind), path) == path, "cost_changes_exposure")
    require(result["comparisons"] == comparisons(result["cells"]), "comparison_arithmetic")


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
        receipt = _read(Path(artifact_root) / h30.RECEIPT)
        result = compare(
            h30.load_streams(market_data_root, receipt, deadline),
            contract,
            pin,
            h30.EmergencyStore(output / "emergency.json"),
            deadline,
        )
        verify(artifact_root, market_data_root, pin)
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure")
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None
