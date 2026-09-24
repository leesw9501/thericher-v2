"""Seen-data position-state ablation with fixed forecasts and local-paper replay."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_policy_graph as parent_study
from thericher_v2.research import policy_graph_models as models
from thericher_v2.research.policy_graph_replay import compare_policy, make_cached_payoff

base = parent_study
sessions, h30, positions = base.sessions, base.h30, base.positions
REPO, SECONDS, COSTS = base.REPO, 900, base.COSTS
NAME = "firstrate-m5-transition-cost-development-v1"
PARENT_PIN = "sha256:74087f84dc70001685689ffb1747fe47b6a76587aba4e5345c2952a9806688d4"
PARENT_RESULT = "sha256:9df32417e4e3abca22cf1f7540bb3c2ae51645a972c0aadd3da1486295f1a736"
POLICIES = (
    "ridge",
    "ridge_stateful",
    "ridge_stateless",
    "mean_stateful",
    "always_flat",
    "always_long",
)
TRANSITIONS = POLICIES[1:4]
CONTROLS = ("ridge", "always_flat", "always_long")
encode, digest, require, atomic_new, _read = (
    base.encode,
    base.digest,
    base.require,
    base.atomic_new,
    base._read,
)
CODE = (
    *base.CODE,
    "src/thericher_v2/research/firstrate_transition_policy.py",
    "src/thericher_v2/research/transition_cost_policy.py",
    "scripts/run_firstrate_transition_policy.py",
)


def configuration():
    return dict(
        symbols=list(h30.SYMBOLS),
        policies=list(POLICIES),
        context_bars=36,
        horizon_minutes=30,
        costs_bps_per_side=list(COSTS),
        decision_cost_bps_per_side=3,
        fit_budget=dict(ridge=4, wall_seconds=SECONDS, passes=1, gpu=False),
        paired_cells=96,
        source_and_split="same pinned parent M5 source/session grid/TRAIN-EVAL purge",
        model="same alpha1 SVD Ridge and TRAIN-only 36x4 channel scaler; no tree/OOF fit",
        mean="outer TRAIN mean gross H30bps only",
        utility="U(x,q)=x*forecast_bps-3*abs(x-q)-3*x*terminal; x,q in0/1; ties cash",
        state="previous chosen target only if adjacent30min same session; else flat",
        lease="each target expires at d+30m unless next contiguous valid decision continues it",
        terminal="known session calendar d+60m>=close; NOT last observed decision",
        controls="ridge>6bps, cash, long reproduce all48 pinned parent cells exactly",
        ablation="ridge_stateless uses q0 in utility but retains ordinary position accounting",
        sensitivity="all costs/planners re-account the same fixed3bps decision sequence",
        replay="one share; next open; local_paper; exact quantized fees; session-terminal flat",
        metrics="gross/net/fees/turnover/entries/holds/exits/open-mark drawdown",
        censoring="freeze all stateful decisions before whole-session common outcome censor",
        kill_test="future changes earlier target; held interval charged twice; expiry uncharged; "
        "parent control mismatch; within-policy paired gross/exposure/cost mismatch",
        limits=[
            "seen_data_outcome_informed_not_holdout",
            "one_step_heuristic_not_optimal_control",
            "forecast_return_basis_and_nominal_fees_not_exact_net_breakeven",
            "cross_policy_exposure_may_differ_not_pure_fee_attribution",
            "gap_expiry_assumes_instant_fill_at_scheduled_boundary",
            "source_clock_finality_revision_unverified_zero_latency",
            "posthoc_session_censor_not_live_rule",
            "not_portfolio_NAV_or_independent_folds",
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
    directory = Path(root) / "research" / base.NAME
    contract_raw, result_raw = (
        _read(directory / name) for name in ("precommit.json", "summary.json")
    )
    require(
        digest(contract_raw) == PARENT_PIN and digest(result_raw) == PARENT_RESULT, "parent_hash"
    )
    require(contract_raw == encode(base.proposed_contract(root)), "parent_code_or_source_changed")
    result = json.loads(result_raw)
    base.validate_result(result, json.loads(contract_raw), PARENT_PIN)
    return result


def proposed_contract(root):
    parent(root)
    payload = base.proposed_contract(root)
    cfg = configuration()
    return dict(
        schema_version=1,
        name=NAME,
        config=cfg,
        config_sha256=digest(encode(cfg)),
        source_pins=payload["source_pins"],
        receipt_sha256=payload["receipt_sha256"],
        runtime=payload["runtime"],
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def header(contract, pin):
    require(contract["name"] == NAME and digest(encode(contract)) == pin, "contract_hash")
    require(
        contract["config"] == configuration()
        and contract["config_sha256"] == digest(encode(configuration())),
        "config_changed",
    )
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
    from thericher_v2.research.transition_cost_policy import target_positions

    forecast, identity = models._ridge_predict(
        arrays["train_x"], arrays["train_y"], arrays["eval_x"], deadline
    )
    closing = dict(schedule)
    terminal = np.asarray(
        [o.at + 2 * h30.HOLD >= closing[k] for o, k in zip(observations, keys, strict=True)],
        dtype=bool,
    )
    mean = np.full(len(forecast), float(arrays["train_y"].mean()), dtype=np.float64)
    transitions = {}
    for policy, values, stateful in (
        ("ridge_stateful", forecast, True),
        ("ridge_stateless", forecast, False),
        ("mean_stateful", mean, True),
    ):
        transitions[policy] = target_positions(
            forecasts=values,
            times=arrays["eval_times"],
            session_keys=keys,
            terminal=terminal,
            cost_bps=3.0,
            stateful=stateful,
        )
    targets = dict(
        ridge=forecast > 6,
        **{p: transitions[p].targets for p in TRANSITIONS},
        always_flat=np.zeros(len(forecast), dtype=bool),
        always_long=np.ones(len(forecast), dtype=bool),
    )
    frozen = {}
    for key, value in targets.items():
        require(value.dtype == np.dtype(bool) and value.shape == (len(observations),), "targets")
        frozen[key] = value.copy()
        frozen[key].setflags(write=False)
    return frozen, dict(
        model=identity,
        terminal_decisions=int(terminal.sum()),
        forecast_sha256=models._hash(forecast),
        action_counts={p: dict(transitions[p].counts) for p in TRANSITIONS},
    )


def compare(streams, contract, pin, prior, emergency, deadline):
    header(contract, pin)
    old_cells = {
        (c["symbol"], c["fold"], c["cost_bps_per_side"], c["candidate"]): c for c in prior["cells"]
    }
    old_folds = {(f["symbol"], f["fold"]): f for f in prior["folds"]}
    folds, cells, matched = [], [], 0
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        schedule = sessions.regular_sessions(bars)
        for number, plan in enumerate(sessions.plans(schedule, 30), 1):
            h30.check_time(deadline)
            arrays, observations, facts = base.training_arrays(index, plan)
            keys = positions.session_keys(observations, schedule)
            targets, model_facts = decisions(arrays, observations, keys, schedule, deadline)
            require(
                model_facts["model"] == old_folds[symbol, number]["model_facts"]["final"],
                "parent_model_changed",
            )
            # State evolves from prior decisions, never EVAL payoff or posthoc censor flags.
            outcomes, _ = sessions.outcomes(index, observations, 30)
            keep, support = positions.common_support(observations, outcomes, keys)
            require(support == old_folds[symbol, number]["support"], "parent_support_changed")
            folds.append(dict(symbol=symbol, fold=number, **facts, support=support, **model_facts))
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
                        selected=targets[policy],
                        keys=keys,
                        keep=keep,
                        cost=cost,
                        emergency=emergency,
                        deadline=deadline,
                        replay=replay,
                    )
                    if policy in CONTROLS:
                        require(
                            cell == old_cells[symbol, number, cost, policy],
                            "parent_control_changed",
                        )
                        matched += 1
                    cells.append(cell)
    result = dict(
        **header(contract, pin),
        status="complete",
        criterion="descriptive_no_selection",
        folds=folds,
        cells=cells,
        parent_controls_reproduced=matched,
        comparisons=comparisons(cells),
    )
    validate_result(result, contract, pin)
    return result


def comparisons(cells):
    lookup = {(c["symbol"], c["fold"], c["cost_bps_per_side"], c["candidate"]): c for c in cells}
    return [
        dict(
            symbol=c["symbol"],
            fold=c["fold"],
            cost_bps_per_side=c["cost_bps_per_side"],
            candidate=c["candidate"],
            vs=baseline,
            persistent_net_delta=str(
                Decimal(c["persistent"]["net_dollars"])
                - Decimal(
                    lookup[c["symbol"], c["fold"], c["cost_bps_per_side"], baseline]["persistent"][
                        "net_dollars"
                    ]
                )
            ),
        )
        for c in cells
        for baseline in ("ridge", "ridge_stateless")
    ]


def failure(contract, pin, reason):
    require(reason in base.artifacts.FAILURES, "failure_reason")
    return dict(
        **header(contract, pin),
        status="failed",
        criterion=reason,
        folds=[],
        cells=[],
        parent_controls_reproduced=0,
        comparisons=[],
    )


def validate_result(result, contract, pin):
    if result.get("status") == "failed":
        require(result == failure(contract, pin, result["criterion"]), "failed_shape")
        return
    require(
        set(result)
        == {
            *header(contract, pin),
            "status",
            "criterion",
            "folds",
            "cells",
            "parent_controls_reproduced",
            "comparisons",
        },
        "result_keys",
    )
    require(
        all(result[k] == v for k, v in header(contract, pin).items())
        and result["status"] == "complete"
        and result["criterion"] == "descriptive_no_selection"
        and result["parent_controls_reproduced"] == 48,
        "result_identity",
    )
    require(
        [(f["symbol"], f["fold"]) for f in result["folds"]]
        == [(s, f) for s in h30.SYMBOLS for f in (1, 2)],
        "fold_matrix",
    )
    support = {}
    actions = {}
    for fold in result["folds"]:
        base._keys(
            fold,
            "symbol fold training_inputs training_outcomes evaluation_inputs train_rows "
            "support model terminal_decisions forecast_sha256 action_counts",
            nested=(
                "training_inputs",
                "training_outcomes",
                "evaluation_inputs",
                "support",
                "model",
                "action_counts",
            ),
        )
        for key in ("training_inputs", "evaluation_inputs"):
            base._keys(fold[key], "scheduled eligible past_missing past_incomplete")
        base._keys(fold["training_outcomes"], "eligible observed future_missing")
        base._keys(fold["model"], "scaler_sha256 model_sha256")
        base._keys(
            fold["support"],
            "eligible_decisions raw_future_missing censored_sessions "
            "common_censored_decisions common_scored_decisions common_scored_blocks",
        )
        support[fold["symbol"], fold["fold"]] = fold["support"]
        facts = fold["support"]
        require(
            all(type(v) is int and v >= 0 for v in facts.values())
            and facts["eligible_decisions"] == fold["evaluation_inputs"]["eligible"]
            and facts["eligible_decisions"]
            == facts["common_scored_decisions"] + facts["common_censored_decisions"]
            and facts["raw_future_missing"] <= facts["common_censored_decisions"]
            and facts["common_scored_decisions"] >= 32
            and 8 <= facts["common_scored_blocks"] <= facts["common_scored_decisions"]
            and 0 <= fold["terminal_decisions"] <= facts["eligible_decisions"]
            and fold["train_rows"] == fold["training_outcomes"]["observed"] >= 128,
            "fold_support",
        )
        base._keys(fold["action_counts"], " ".join(TRANSITIONS), nested=TRANSITIONS)
        actions[fold["symbol"], fold["fold"]] = fold["action_counts"]
        for counts in fold["action_counts"].values():
            base._keys(counts, "enter hold exit flat expiry_exit")
            require(all(type(v) is int and v >= 0 for v in counts.values()), "action_counts")
            require(
                sum(counts[k] for k in ("enter", "hold", "exit", "flat"))
                == fold["evaluation_inputs"]["eligible"],
                "action_count_total",
            )
            require(counts["enter"] == counts["exit"] + counts["expiry_exit"], "action_terminal")
    require(
        [(c["symbol"], c["fold"], c["cost_bps_per_side"], c["candidate"]) for c in result["cells"]]
        == [
            (s, f, cost, p) for s in h30.SYMBOLS for f in (1, 2) for cost in COSTS for p in POLICIES
        ],
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
            require(paths.setdefault(identity, path) == path, "cost_changes_decisions_or_exposure")
        facts = support[cell["symbol"], cell["fold"]]
        require(
            0 <= cell["selected_censored"] <= facts["common_censored_decisions"]
            and cell["selected_censored"]
            <= cell["selected_decisions"]
            <= facts["eligible_decisions"],
            "common_support",
        )
        require(
            cell["selected_decisions"] - cell["selected_censored"]
            <= facts["common_scored_decisions"],
            "common_support",
        )
        if cell["candidate"] in TRANSITIONS:
            counts = actions[cell["symbol"], cell["fold"]][cell["candidate"]]
            require(
                cell["selected_decisions"] == counts["enter"] + counts["hold"]
                and cell["persistent"]["roundtrips"] <= counts["enter"],
                "action_replay",
            )
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
        prior = parent(artifact_root)
        result = compare(
            h30.load_streams(market_data_root, _read(Path(artifact_root) / h30.RECEIPT), deadline),
            contract,
            pin,
            prior,
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
