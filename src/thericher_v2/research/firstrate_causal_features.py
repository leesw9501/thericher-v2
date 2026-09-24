"""Fixed causal-feature comparison on the existing seen-data transition study."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import causal_feature_ridge as learner
from thericher_v2.research import firstrate_transition_policy as parent_study
from thericher_v2.research.policy_graph_replay import compare_policy, make_cached_payoff
from thericher_v2.research.transition_cost_policy import target_positions

base = parent_study.base
sessions, h30, positions = base.sessions, base.h30, base.positions
REPO, SECONDS, COSTS = base.REPO, 900, parent_study.COSTS
NAME = "firstrate-m5-causal-features-development-v1"
PARENT_PIN = "sha256:140944b6be72926440582fa317dc1de1cabc98440fb1cd140f680cec717e53d1"
PARENT_RESULT = "sha256:a164d95f7632c0e181c08c6fbbde4b2eb64da347fcb592c0cc3d72f24390080f"
POLICIES = ("feature_ridge", "feature_stateful")
encode, digest, require, atomic_new, _read = (
    base.encode,
    base.digest,
    base.require,
    base.atomic_new,
    base._read,
)
CODE = (
    *parent_study.CODE,
    "src/thericher_v2/research/causal_feature_ridge.py",
    "src/thericher_v2/research/firstrate_causal_features.py",
    "scripts/run_firstrate_causal_features.py",
)


def configuration():
    return dict(
        symbols=list(h30.SYMBOLS),
        policies=list(POLICIES),
        context_bars=36,
        horizon_minutes=30,
        features=list(learner.FEATURES),
        feature_windows_bars=[3, 12, 36],
        feature_formulas="per window: last close/first open-1; population std close returns; "
        "mean normalized range; mean body; mean logvolume recent third minus whole window",
        model="alpha1 SVD Ridge/intercept; per-feature TRAIN-only mean/std; zero std=>1",
        fit_budget=dict(raw_ridge=4, feature_ridge=4, wall_seconds=SECONDS, passes=1, gpu=False),
        paired_cells=32,
        baseline_paired_cells=96,
        costs_bps_per_side=list(COSTS),
        decision_cost_bps_per_side=3,
        policy="fixed gross>6bps versus unchanged position-state utility with fixed3bps",
        source_and_split="exact parent source/session/36-bar history/H30 labels/TRAIN purge",
        outcomes="all feature targets frozen before EVAL payoff and common-session censor",
        replay="unchanged one-share local_paper lease/expiry/fees/repeated and persistent",
        controls="recompute entire parent result exactly including96 cells/model identities",
        kill_test="future input changes earlier feature/target; EVAL enters scaler; "
        "parent/control/support mismatch; cost changes target; lease/replay fee mismatch",
        limits=parent_study.configuration()["limits"]
        + [
            "feature_and_per_feature_scaling_bundle_not_single_feature_causal_attribution",
            "TRAIN_overlap_and_reused_seen_data_not_independent_evidence",
            "no_search_or_posthoc_winner_selection",
        ],
        parent_contract=PARENT_PIN,
        parent_summary=PARENT_RESULT,
        promotion=False,
        holdout=False,
        selection=False,
        broker_input=False,
        fitted_weights_retained=False,
        image=sessions.IMAGE,
        resources="oneCPU/twoGiB/networknone/readonlysourceanddata/externalartifacts",
    )


def parent(root):
    directory = Path(root) / "research" / parent_study.NAME
    raw, summary = (_read(directory / n) for n in ("precommit.json", "summary.json"))
    require(digest(raw) == PARENT_PIN and digest(summary) == PARENT_RESULT, "parent_hash")
    require(raw == encode(parent_study.proposed_contract(root)), "parent_changed")
    contract, result = json.loads(raw), json.loads(summary)
    parent_study.validate_result(result, contract, PARENT_PIN)
    return contract, result


def proposed_contract(root):
    contract, _ = parent(root)
    cfg = configuration()
    return dict(
        schema_version=1,
        name=NAME,
        config=cfg,
        config_sha256=digest(encode(cfg)),
        parent_contract=contract,
        source_pins=contract["source_pins"],
        receipt_sha256=contract["receipt_sha256"],
        runtime=contract["runtime"],
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def header(contract, pin):
    require(contract["name"] == NAME and digest(encode(contract)) == pin, "contract_hash")
    require(
        contract["config"] == configuration()
        and contract["config_sha256"] == digest(encode(configuration())),
        "config_changed",
    )
    require(digest(encode(contract["parent_contract"])) == PARENT_PIN, "parent_contract")
    return dict(
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        evidence_grade="OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
    )


def register_contract(root, contract, pin):
    header(contract, pin)
    base.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=digest(encode(contract["source_pins"])),
        split_hash=digest(encode([PARENT_PIN, "same_outer_folds"])),
        cost_model_hash=digest(encode([COSTS, "exact_local_paper_repeated_and_merged"])),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root, market_data_root):
    require(h30.source_root_allowed(Path(market_data_root).resolve(), REPO), "source_root")
    contract = proposed_contract(artifact_root)
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research") / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root, market_data_root, pin):
    require(h30.source_root_allowed(Path(market_data_root).resolve(), REPO), "source_root")
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research", NAME)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin and raw == encode(proposed_contract(artifact_root)), "binding")
    return output, json.loads(raw)


def decisions(arrays, observations, keys, schedule, deadline):
    forecast, model = learner.fit_predict(
        **{k: arrays[k] for k in ("train_x", "train_closes", "train_y", "eval_x", "eval_closes")},
        deadline=deadline,
    )
    closing = dict(schedule)
    terminal = np.asarray(
        [o.at + 2 * h30.HOLD >= closing[k] for o, k in zip(observations, keys, strict=True)],
        dtype=bool,
    )
    state = target_positions(
        forecasts=forecast,
        times=arrays["eval_times"],
        session_keys=keys,
        terminal=terminal,
        cost_bps=3.0,
    )
    hurdle = forecast > 6.0
    hurdle.setflags(write=False)
    return dict(feature_ridge=hurdle, feature_stateful=state.targets), dict(
        model=model,
        forecast_sha256=parent_study.models._hash(forecast),
        terminal_decisions=int(terminal.sum()),
        action_counts=dict(state.counts),
    )


def compare(streams, contract, pin, grandparent, emergency, deadline):
    header(contract, pin)
    streams = tuple(streams)
    baseline = parent_study.compare(
        streams, contract["parent_contract"], PARENT_PIN, grandparent, emergency, deadline
    )
    require(digest(encode(baseline)) == PARENT_RESULT, "parent_replay_changed")
    old_folds = {(f["symbol"], f["fold"]): f for f in baseline["folds"]}
    folds, cells = [], []
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        schedule = sessions.regular_sessions(bars)
        for number, plan in enumerate(sessions.plans(schedule, 30), 1):
            h30.check_time(deadline)
            arrays, observations, facts = base.training_arrays(index, plan)
            keys = positions.session_keys(observations, schedule)
            targets, model = decisions(arrays, observations, keys, schedule, deadline)
            # No EVAL payoff, missing-future mask or outcome enters the learned targets.
            outcomes, _ = sessions.outcomes(index, observations, 30)
            keep, support = positions.common_support(observations, outcomes, keys)
            previous = old_folds[symbol, number]
            require(
                all(facts[k] == previous[k] for k in facts) and support == previous["support"],
                "parent_support_changed",
            )
            folds.append(dict(symbol=symbol, fold=number, **model))
            replay = make_cached_payoff()
            for cost in COSTS:
                for policy in POLICIES:
                    cells.append(
                        compare_policy(
                            ident=dict(
                                symbol=symbol,
                                fold=number,
                                horizon_minutes=30,
                                candidate=policy,
                                context=36,
                                seed=None,
                            ),
                            observations=observations,
                            outcomes=outcomes,
                            selected=targets[policy],
                            keys=keys,
                            keep=keep,
                            cost=cost,
                            emergency=emergency,
                            deadline=deadline,
                            replay=replay,
                        )
                    )
    result = dict(
        **header(contract, pin),
        status="complete",
        criterion="descriptive_no_selection",
        baseline_replay=baseline,
        folds=folds,
        cells=cells,
    )
    validate_result(result, contract, pin)
    return result


def failure(contract, pin, reason):
    require(reason in base.artifacts.FAILURES, "failure_reason")
    return dict(
        **header(contract, pin),
        status="failed",
        criterion=reason,
        baseline_replay=None,
        folds=[],
        cells=[],
    )


def validate_result(result, contract, pin):
    if result.get("status") == "failed":
        require(result == failure(contract, pin, result["criterion"]), "failed_shape")
        return
    base._keys(
        result,
        "name contract_sha256 config_sha256 evidence_grade status criterion "
        "baseline_replay folds cells",
        nested=("baseline_replay", "folds", "cells"),
    )
    require(
        all(result[k] == v for k, v in header(contract, pin).items())
        and result["status"] == "complete"
        and result["criterion"] == "descriptive_no_selection",
        "result_identity",
    )
    baseline = result["baseline_replay"]
    require(digest(encode(baseline)) == PARENT_RESULT, "parent_replay_changed")
    parent_study.validate_result(baseline, contract["parent_contract"], PARENT_PIN)
    prior = {(f["symbol"], f["fold"]): f for f in baseline["folds"]}
    require([(f["symbol"], f["fold"]) for f in result["folds"]] == list(prior), "fold_matrix")
    actions = {}
    for fold in result["folds"]:
        base._keys(
            fold,
            "symbol fold model forecast_sha256 terminal_decisions action_counts",
            nested=("model", "action_counts"),
        )
        base._keys(fold["model"], "scaler_sha256 model_sha256")
        previous = prior[fold["symbol"], fold["fold"]]
        require(
            type(fold["terminal_decisions"]) is int
            and fold["terminal_decisions"] == previous["terminal_decisions"],
            "terminal",
        )
        counts = fold["action_counts"]
        base._keys(counts, "enter hold exit flat expiry_exit")
        require(
            all(type(v) is int and v >= 0 for v in counts.values())
            and sum(counts[k] for k in ("enter", "hold", "exit", "flat"))
            == previous["evaluation_inputs"]["eligible"]
            and counts["enter"] == counts["exit"] + counts["expiry_exit"],
            "actions",
        )
        actions[fold["symbol"], fold["fold"]] = counts
    require(
        [(c["symbol"], c["fold"], c["cost_bps_per_side"], c["candidate"]) for c in result["cells"]]
        == [(s, f, c, p) for s in h30.SYMBOLS for f in (1, 2) for c in COSTS for p in POLICIES],
        "cell_matrix",
    )
    paths = {}
    for cell in result["cells"]:
        base._keys(
            cell,
            "symbol fold horizon_minutes candidate context seed cost_bps_per_side "
            "selected_decisions selected_censored decision_sha256 repeated persistent "
            "removed_boundary_pairs saved_fees_dollars saved_turnover_dollars risk",
            nested=("repeated", "persistent", "risk"),
        )
        require(
            cell["horizon_minutes"] == 30 and cell["context"] == 36 and cell["seed"] is None,
            "cell_identity",
        )
        positions.validate_pair(cell)
        base._keys(cell["risk"], "repeated persistent", nested=("repeated", "persistent"))
        for kind in ("repeated", "persistent"):
            totals, risk = cell[kind], cell["risk"][kind]
            base._keys(
                totals,
                "roundtrips fills wins gross_dollars fees_dollars net_dollars "
                "turnover_dollars exposure_minutes exposure_sha256 terminal_flat "
                "local_paper_replay_parity",
            )
            base._keys(
                risk, "max_mark_to_market_drawdown_dollars max_holding_minutes mean_holding_minutes"
            )
            dd = Decimal(risk["max_mark_to_market_drawdown_dollars"])
            require(
                dd.is_finite()
                and dd >= 0
                and 0 <= risk["mean_holding_minutes"] <= risk["max_holding_minutes"] <= 180,
                "risk_bounds",
            )
            identity = cell["symbol"], cell["fold"], cell["candidate"], kind
            path = (
                cell["decision_sha256"],
                cell["selected_decisions"],
                cell["selected_censored"],
                *(
                    totals[k]
                    for k in (
                        "gross_dollars",
                        "turnover_dollars",
                        "exposure_minutes",
                        "exposure_sha256",
                        "roundtrips",
                    )
                ),
            )
            require(paths.setdefault(identity, path) == path, "cost_changes_path")
        support = prior[cell["symbol"], cell["fold"]]["support"]
        require(
            0 <= cell["selected_censored"] <= support["common_censored_decisions"]
            and cell["selected_censored"]
            <= cell["selected_decisions"]
            <= support["eligible_decisions"]
            and cell["selected_decisions"] - cell["selected_censored"]
            <= support["common_scored_decisions"],
            "common_support",
        )
        if cell["candidate"] == "feature_stateful":
            counts = actions[cell["symbol"], cell["fold"]]
            require(
                cell["selected_decisions"] == counts["enter"] + counts["hold"]
                and cell["persistent"]["roundtrips"] <= counts["enter"],
                "action_replay",
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
        result = compare(
            h30.load_streams(market_data_root, _read(Path(artifact_root) / h30.RECEIPT), deadline),
            contract,
            pin,
            parent_study.parent(artifact_root),
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
