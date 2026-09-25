"""One fixed nonlinear feature comparison, reusing the local-paper CPU loop."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import causal_feature_boosting as learner
from thericher_v2.research import firstrate_causal_features as prior_study
from thericher_v2.research.policy_graph_replay import compare_policy, make_cached_payoff
from thericher_v2.research.transition_cost_policy import target_positions

base, h30, sessions, positions = (
    prior_study.base,
    prior_study.h30,
    prior_study.sessions,
    prior_study.positions,
)
REPO, SECONDS, COSTS = base.REPO, 900, prior_study.COSTS
NAME = "firstrate-m5-feature-boosting-development-v1"
PARENT_PIN = "sha256:95f522834a8d846b9f600602e9a9a1efa8fbcaecbb55a328f9cfcbbc6995866d"
PARENT_RESULT = "sha256:57ded7f558db276fde1bdd058d67eae4db10356a91d279085f0c1f29f5ee417b"
CONTROLS = prior_study.POLICIES
POLICIES = (*CONTROLS, "boost_hurdle", "boost_stateful")
encode, digest, require, atomic_new, _read = (
    base.encode,
    base.digest,
    base.require,
    base.atomic_new,
    base._read,
)
CODE = (
    *prior_study.CODE,
    "src/thericher_v2/research/causal_feature_boosting.py",
    "src/thericher_v2/research/firstrate_feature_boosting.py",
    "scripts/run_firstrate_feature_boosting.py",
)


def configuration():
    return dict(
        symbols=list(h30.SYMBOLS),
        policies=list(POLICIES),
        features=list(learner.FEATURES),
        estimator=dict(learner.PARAMETERS),
        feature_transform="unchanged15 completed-bar features; no tree scaling",
        context_bars=36,
        horizon_minutes=30,
        fit_budget=dict(feature_ridge=4, boosted_tree=4, passes=1, wall_seconds=SECONDS, gpu=False),
        paired_cells=64,
        parent_controls=32,
        costs_bps_per_side=list(COSTS),
        decision_cost_bps_per_side=3,
        policy="gross>6bps and unchanged U=x*f-3*abs(x-q)-3*x*calendar_terminal; ties cash",
        source_split="exact parent M5 sessions/36-bar history/H30 label/TRAIN purge",
        training="TRAIN only;64 depth2 trees; no early stopping/EVAL validation/tuning",
        outcomes="targets before EVAL payoff and common missing-future session censor",
        replay="same one-share local_paper H30 leases/expiry fees/repeated versus persistent",
        control_reproduction="four feature Ridge folds/identities/actions/support;32 exact cells",
        historical_controls="96 raw/naive parent cells retained reference only; NOT recomputed",
        forecast_diagnostic="fold grossbps min/mean/max/population std/count above6; no tuning",
        kill_test="future changes earlier target; EVAL changes fitting; control/support mismatch; "
        "cost changes decisions or within-policy replay identities fail",
        limits=prior_study.configuration()["limits"]
        + [
            "estimator_scaling_capacity_bundle_not_proof_of_causal_feature_interactions",
            "single_fixed_tree_configuration_not_model_family_rejection",
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
    directory = Path(root) / "research" / prior_study.NAME
    raw, summary = (_read(directory / name) for name in ("precommit.json", "summary.json"))
    require(digest(raw) == PARENT_PIN and digest(summary) == PARENT_RESULT, "parent_hash")
    require(raw == encode(prior_study.proposed_contract(root)), "parent_changed")
    contract, result = json.loads(raw), json.loads(summary)
    prior_study.validate_result(result, contract, PARENT_PIN)
    return contract, result


def cell_key(cell):
    return f"{cell['symbol']}:{cell['fold']}:{cell['cost_bps_per_side']}:{cell['candidate']}"


def references(result):
    return dict(
        folds={f"{f['symbol']}:{f['fold']}": digest(encode(f)) for f in result["folds"]},
        cells={cell_key(c): digest(encode(c)) for c in result["cells"]},
        support={
            f"{f['symbol']}:{f['fold']}": f["support"] for f in result["baseline_replay"]["folds"]
        },
        train_rows={
            f"{f['symbol']}:{f['fold']}": f["train_rows"]
            for f in result["baseline_replay"]["folds"]
        },
        terminal={f"{f['symbol']}:{f['fold']}": f["terminal_decisions"] for f in result["folds"]},
    )


def proposed_contract(root):
    previous, result = parent(root)
    config = configuration()
    return dict(
        schema_version=1,
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source_pins=previous["source_pins"],
        receipt_sha256=previous["receipt_sha256"],
        runtime=previous["runtime"],
        reference=references(result),
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
    control_targets, control_facts = prior_study.decisions(
        arrays, observations, keys, schedule, deadline
    )
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
    return (
        dict(**control_targets, boost_hurdle=hurdle, boost_stateful=state.targets),
        dict(
            model=model,
            forecast_sha256=prior_study.parent_study.models._hash(forecast),
            forecast_distribution=dict(
                min_bps=float(forecast.min()),
                mean_bps=float(forecast.mean()),
                max_bps=float(forecast.max()),
                std_bps=float(forecast.std(ddof=0)),
                above_hurdle=int(hurdle.sum()),
            ),
            terminal_decisions=int(terminal.sum()),
            action_counts=dict(state.counts),
        ),
        control_facts,
    )


def compare(streams, contract, pin, emergency, deadline):
    header(contract, pin)
    ref = contract["reference"]
    folds, cells = [], []
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        schedule = sessions.regular_sessions(bars)
        for number, plan in enumerate(sessions.plans(schedule, 30), 1):
            h30.check_time(deadline)
            arrays, observations, facts = base.training_arrays(index, plan)
            keys = positions.session_keys(observations, schedule)
            targets, tree, control = decisions(arrays, observations, keys, schedule, deadline)
            fold_key = f"{symbol}:{number}"
            control_hash = digest(encode(dict(symbol=symbol, fold=number, **control)))
            require(control_hash == ref["folds"][fold_key], "parent_model_changed")
            # Neither model receives EVAL payoff or its subsequent missing-future mask.
            outcomes, _ = sessions.outcomes(index, observations, 30)
            keep, support = positions.common_support(observations, outcomes, keys)
            require(support == ref["support"][fold_key], "parent_support_changed")
            folds.append(
                dict(
                    symbol=symbol,
                    fold=number,
                    train_rows=facts["train_rows"],
                    control_facts_sha256=control_hash,
                    **tree,
                )
            )
            replay = make_cached_payoff()
            for cost in COSTS:
                for policy in POLICIES:
                    cell = compare_policy(
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
                    if policy in CONTROLS:
                        require(
                            digest(encode(cell)) == ref["cells"][cell_key(cell)],
                            "parent_cell_changed",
                        )
                    cells.append(cell)
    result = dict(
        **header(contract, pin),
        status="complete",
        criterion="descriptive_no_selection",
        parent_controls_reproduced=32,
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
        parent_controls_reproduced=0,
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
        "parent_controls_reproduced folds cells",
        nested=("folds", "cells"),
    )
    require(
        all(result[k] == v for k, v in header(contract, pin).items())
        and result["status"] == "complete"
        and result["criterion"] == "descriptive_no_selection"
        and type(result["parent_controls_reproduced"]) is int
        and result["parent_controls_reproduced"] == 32,
        "result_identity",
    )
    ref = contract["reference"]
    require(
        [(f["symbol"], f["fold"]) for f in result["folds"]]
        == [(s, f) for s in h30.SYMBOLS for f in (1, 2)],
        "fold_matrix",
    )
    actions = {}
    for fold in result["folds"]:
        base._keys(
            fold,
            "symbol fold train_rows control_facts_sha256 model forecast_sha256 "
            "terminal_decisions action_counts forecast_distribution",
            nested=("model", "action_counts", "forecast_distribution"),
        )
        base._keys(fold["model"], "model_sha256 training_features_sha256")
        key = f"{fold['symbol']}:{fold['fold']}"
        support = ref["support"][key]
        require(
            fold["control_facts_sha256"] == ref["folds"][key]
            and type(fold["train_rows"]) is int
            and fold["train_rows"] == ref["train_rows"][key] >= 128
            and type(fold["terminal_decisions"]) is int
            and fold["terminal_decisions"] == ref["terminal"][key]
            and 0 <= fold["terminal_decisions"] <= support["eligible_decisions"],
            "fold_binding",
        )
        dist = fold["forecast_distribution"]
        base._keys(dist, "min_bps mean_bps max_bps std_bps above_hurdle")
        require(
            all(type(dist[k]) is float for k in ("min_bps", "mean_bps", "max_bps", "std_bps"))
            and dist["min_bps"] <= dist["mean_bps"] <= dist["max_bps"]
            and dist["std_bps"] >= 0
            and type(dist["above_hurdle"]) is int
            and 0 <= dist["above_hurdle"] <= support["eligible_decisions"],
            "forecast_distribution",
        )
        counts = fold["action_counts"]
        base._keys(counts, "enter hold exit flat expiry_exit")
        require(
            all(type(v) is int and v >= 0 for v in counts.values())
            and sum(counts[k] for k in ("enter", "hold", "exit", "flat"))
            == support["eligible_decisions"]
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
        if cell["candidate"] in CONTROLS:
            require(digest(encode(cell)) == ref["cells"][cell_key(cell)], "parent_cell_changed")
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
        support = ref["support"][f"{cell['symbol']}:{cell['fold']}"]
        require(
            0 <= cell["selected_censored"] <= support["common_censored_decisions"]
            and cell["selected_censored"]
            <= cell["selected_decisions"]
            <= support["eligible_decisions"]
            and cell["selected_decisions"] - cell["selected_censored"]
            <= support["common_scored_decisions"],
            "common_support",
        )
        if cell["candidate"] == "boost_stateful":
            counts = actions[cell["symbol"], cell["fold"]]
            require(
                cell["selected_decisions"] == counts["enter"] + counts["hold"]
                and cell["persistent"]["roundtrips"] <= counts["enter"],
                "action_replay",
            )
        if cell["candidate"] == "boost_hurdle":
            fold = next(
                f
                for f in result["folds"]
                if (f["symbol"], f["fold"]) == (cell["symbol"], cell["fold"])
            )
            require(
                cell["selected_decisions"] == fold["forecast_distribution"]["above_hurdle"],
                "hurdle_count",
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
