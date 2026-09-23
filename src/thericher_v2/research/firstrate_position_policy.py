"""CPU DEVELOPMENT: remove redundant H30 roundtrips without changing exposure."""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from pathlib import Path

import numpy as np

from thericher_v2.research import firstrate_family_comparison as family

sessions, h30 = family.sessions, family.h30
require = sessions.require
NAME = "persistent-position-h30-c36-v1"
FAMILY, REPO = h30.FAMILY, h30.REPO
SECONDS = 600
CODE = (
    "src/thericher_v2/research/firstrate_position_policy.py",
    "scripts/run_firstrate_position_policy.py",
    *family.CODE,
)
CANDIDATES = tuple((n, None, None) for n in (*h30.NAIVES, "sma3_12")) + (
    ("lstm", 36, 101),
    ("lstm", 36, 103),
)
GRADE = "OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT"
INTERPRETATION = "merge_arithmetic_verified_boundary_counts_measured_not_discovered_alpha"


def lineage(root):
    """Metadata/model pins only; no market panel, inference, or LightGBM wheel."""
    parent, receipt, _ = sessions.verify(root, family.PARENT_CONTRACT)
    prior = {}
    for phase, pin in family.PARENT_HASHES.items():
        raw = (parent / f"{phase}-summary.json").read_bytes()
        require(h30.digest(raw) == pin, "lineage_changed")
        prior[phase] = json.loads(raw)
        sessions.validate_result(prior[phase], phase, family.PARENT_CONTRACT)
    refs = [r for r in prior["cuda"]["models"] if r["horizon_minutes"] == 30 and r["context"] == 36]
    require(
        [(r["symbol"], r["fold"], r["seed"]) for r in refs]
        == [(s, f, seed) for s in h30.SYMBOLS for f in (1, 2) for seed in h30.SEEDS],
        "parent_control_mismatch",
    )
    for ref in refs:
        directory = parent / "models"
        raw = h30.within(directory, ref["config_file"]).read_bytes()
        require(h30.digest(raw) == ref["config_sha256"], "parent_control_mismatch")
        cfg = json.loads(raw)
        require(
            cfg["name"] == sessions.NAME
            and cfg["contract_sha256"] == family.PARENT_CONTRACT
            and cfg["weights_file"] == ref["weights_file"]
            and all(cfg[k] == ref[k] for k in family.IDENTITY if k != "candidate"),
            "parent_control_mismatch",
        )
        require(
            h30.digest(h30.within(directory, ref["weights_file"]).read_bytes())
            == ref["weights_sha256"]
            == cfg["weights_sha256"],
            "parent_control_mismatch",
        )
    return parent, receipt, prior, refs


def contract(root):
    _, receipt, _, refs = lineage(root)
    return {
        "name": NAME,
        "family": FAMILY,
        "parent_contract_sha256": family.PARENT_CONTRACT,
        "parent_summary_sha256": family.PARENT_HASHES,
        "parent_models": refs,
        "parent_cohort_contract": sessions.contract(receipt),
        "code_sha256": {p: h30.digest((REPO / p).read_bytes()) for p in CODE},
        "evidence_grade": GRADE,
        "candidates": CANDIDATES,
        "symbols": h30.SYMBOLS,
        "folds": (1, 2),
        "horizon_minutes": 30,
        "context": 36,
        "prediction": "CPU re-inference of all8 retained LSTMs; parent72 cells must reproduce",
        "threshold": "LSTM gross forecast >6bps; unchanged across1/3/5bps costs",
        "decision": "existing H30 calendar grid;36 complete past M5 bars; all decisions first",
        "fill": "at d.open using last completed d-5min bar; zero latency, fees only",
        "repeated": "one share on each selected [d,d+30min) interval; sell then rebuy at ties",
        "persistent": "merge only adjacent selected H30 intervals in same regular session",
        "missing_decision": "target flat for ineligible/unscheduled intervals; never bridge gap",
        "terminal": "both exit last selected H30 interval; strictly before session close; "
        "no overnight or extension to closing price",
        "missing_outcome": "after all decisions, censor entire affected session for BOTH "
        "policies; no guessed fill, clairvoyant pre-gap exit or zero-return replacement",
        "minimums": "common scored32 decisions and8 disjoint180min history blocks per fold",
        "cost_bps_per_side": h30.COSTS,
        "quantity": 1,
        "pnl_semantics": "independent one-share segments; not portfolio NAV or alpha",
        "interpretation": INTERPRETATION,
        "strongest_kill_test": "parent mismatch; unequal exposure/gross; net improvement "
        "not exactly eliminated boundary fees; future censoring changes planned decisions",
        "budget": {"cpu_seconds": SECONDS, "paired_cells": 72, "policy_cells": 144},
        "selection": False,
        "promotion": False,
        "holdout_access": False,
        "training": False,
        "gpu": False,
        "retry": False,
        "limitations": [
            "seen_data",
            "source_clock_finality_actions_unverified",
            "no_KIS_parity",
            "common_session_censoring_not_live_policy",
            "fees_only_zero_latency",
        ],
    }


def freeze(root):
    root = h30.ensure_external_artifact_directory(root, REPO)
    payload = contract(root)
    raw = h30.encode(payload)
    output = h30.run_directory(root, NAME)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "contract.json").open("xb") as handle:
        handle.write(raw)
    h30.register_frozen_campaign(
        contract_hash=h30.digest(raw),
        dataset_hash=h30.digest(h30.encode(payload["parent_cohort_contract"]["source_pins"])),
        split_hash=h30.digest(h30.encode([family.PARENT_CONTRACT, "H30-context36"])),
        cost_model_hash=h30.digest(h30.encode([h30.COSTS, "same_exposure_position_policy"])),
        trial_family=FAMILY,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )
    return h30.digest(raw)


def verify(root, scope_hash):
    output = h30.run_directory(root, NAME)
    raw = (output / "contract.json").read_bytes()
    require(h30.digest(raw) == scope_hash and raw == h30.encode(contract(root)), "contract_changed")
    return output


def decisions(fold, index, torch, parent, prior):
    result = []
    for name, context, seed in CANDIDATES:
        ident = dict(
            zip(family.IDENTITY, (fold.symbol, fold.fold, 30, name, context, seed), strict=True)
        )
        if name == "lstm":
            values = np.asarray(family.parent_prediction(torch, fold, seed, parent, prior))
            require(
                values.shape == (len(fold.evaluation),) and np.isfinite(values).all(),
                "nonfinite_prediction",
            )
            selected = values * fold.y_scale + fold.y_mean > 6
        else:
            selected = np.asarray(
                [
                    name == "always_long"
                    or (name == "previous_bar_direction" and o.signal.close > o.signal.open)
                    or (
                        name == "sma3_12"
                        and sum(index[o.at - i * h30.STEP].close for i in range(1, 4)) / 3
                        > sum(index[o.at - i * h30.STEP].close for i in range(1, 13)) / 12
                    )
                    for o in fold.evaluation
                ],
                dtype=bool,
            )
        selected.setflags(write=False)
        result.append((ident, selected))
    return result


def session_keys(observations, schedule):
    by_time = {
        at: opening
        for opening, closing in schedule
        for at in sessions.session_grid(((opening, closing),), 30, training=False)
    }
    require(all(o.at in by_time for o in observations), "decision_grid")
    require(
        all(b.at > a.at for a, b in zip(observations, observations[1:], strict=False)),
        "decision_grid",
    )
    return tuple(by_time[o.at] for o in observations)


def plan_positions(observations, selected, keys):
    """Plans use timestamps/decisions only, never future path availability or prices."""
    require(
        len(observations) == len(keys) == len(selected) and np.asarray(selected).dtype == np.bool_,
        "decision_shape",
    )
    repeated, persistent = [], []
    for i, flag in enumerate(selected):
        if not flag:
            continue
        repeated.append((i, i))
        if (
            persistent
            and persistent[-1][1] == i - 1
            and keys[i] == keys[i - 1]
            and observations[i].at == observations[i - 1].at + h30.HOLD
        ):
            persistent[-1] = (persistent[-1][0], i)
        else:
            persistent.append((i, i))
    return tuple(repeated), tuple(persistent)


def common_support(observations, outcomes, keys):
    bad = {k for k, out in zip(keys, outcomes, strict=True) if out is None}
    keep = tuple(k not in bad for k in keys)
    supported = [o for o, flag in zip(observations, keep, strict=True) if flag]
    blocks = h30.blocks(supported)
    if len(supported) < 32 or blocks < 8:
        raise sessions.OutcomeSupportShortfall(len(observations), len(supported), blocks)
    return keep, {
        "eligible_decisions": len(observations),
        "raw_future_missing": sum(o is None for o in outcomes),
        "censored_sessions": len(bad),
        "common_censored_decisions": len(observations) - len(supported),
        "common_scored_decisions": len(supported),
        "common_scored_blocks": blocks,
    }


def replay_plan(
    observations, outcomes, spans, keep, cost, emergency, deadline, replay=sessions.payoff
):
    gross = fees = turnover = Decimal(0)
    held, trades, wins = [], 0, 0
    for first, last in spans:
        h30.check_time(deadline)
        if not keep[first]:
            continue
        require(all(keep[i] for i in range(first, last + 1)), "exposure_mismatch")
        path = list(outcomes[first].bars)
        for i in range(first + 1, last + 1):
            require(path[-1] == outcomes[i].bars[0], "exposure_mismatch")
            path.extend(outcomes[i].bars[1:])
        outcome = h30.Outcome(tuple(path))
        require(
            all(b.start_ts == a.start_ts + h30.STEP for a, b in zip(path, path[1:], strict=False)),
            "exposure_mismatch",
        )
        g, f = replay(observations[first], outcome, cost, emergency)
        gross += g
        fees += f
        turnover += outcome.entry + outcome.exit
        wins += g > f
        trades += 1
        held.extend(bar.start_ts.isoformat() for bar in path[:-1])
    require(len(held) == len(set(held)), "exposure_mismatch")
    return {
        "roundtrips": trades,
        "fills": 2 * trades,
        "wins": wins,
        "gross_dollars": str(gross),
        "fees_dollars": str(fees),
        "net_dollars": str(gross - fees),
        "turnover_dollars": str(turnover),
        "exposure_minutes": len(held) * 5,
        "exposure_sha256": h30.digest(h30.encode(held)),
        "terminal_flat": True,
        "local_paper_replay_parity": True,
    }


def paired_cell(
    ident,
    observations,
    outcomes,
    selected,
    plans,
    keep,
    cost,
    emergency,
    deadline,
    replay=sessions.payoff,
):
    repeated, persistent = [
        replay_plan(observations, outcomes, spans, keep, cost, emergency, deadline, replay)
        for spans in plans
    ]
    removed = [i for first, last in plans[1] if keep[first] for i in range(first + 1, last + 1)]
    saved_fees = sum(
        (2 * (outcomes[i].entry * cost / 10000).quantize(Decimal("0.0001")) for i in removed),
        Decimal(0),
    )
    saved_turnover = sum((2 * outcomes[i].entry for i in removed), Decimal(0))
    cell = {
        **ident,
        "cost_bps_per_side": cost,
        "selected_decisions": int(np.count_nonzero(selected)),
        "selected_censored": sum(
            bool(flag) and not supported for flag, supported in zip(selected, keep, strict=True)
        ),
        "decision_sha256": h30.digest(
            h30.encode(
                [
                    [o.at.isoformat(), bool(flag)]
                    for o, flag in zip(observations, selected, strict=True)
                ]
            )
        ),
        "repeated": repeated,
        "persistent": persistent,
        "removed_boundary_pairs": len(removed),
        "saved_fees_dollars": str(saved_fees),
        "saved_turnover_dollars": str(saved_turnover),
    }
    validate_pair(cell)
    return cell


def validate_pair(cell):
    a, b = cell["repeated"], cell["persistent"]
    for value in (a, b):
        require(
            all(
                Decimal(value[k]).is_finite()
                for k in ("gross_dollars", "fees_dollars", "net_dollars", "turnover_dollars")
            ),
            "result_accounting",
        )
        require(
            Decimal(value["gross_dollars"]) - Decimal(value["fees_dollars"])
            == Decimal(value["net_dollars"])
            and Decimal(value["fees_dollars"]) >= 0
            and value["fills"] == 2 * value["roundtrips"]
            and value["terminal_flat"] is True
            and value["local_paper_replay_parity"] is True,
            "result_accounting",
        )
    require(
        all(a[k] == b[k] for k in ("gross_dollars", "exposure_minutes", "exposure_sha256")),
        "exposure_mismatch",
    )
    require(
        a["roundtrips"] - b["roundtrips"] == cell["removed_boundary_pairs"] >= 0
        and a["exposure_minutes"] == 30 * (cell["selected_decisions"] - cell["selected_censored"]),
        "exposure_mismatch",
    )
    require(
        Decimal(a["fees_dollars"]) - Decimal(b["fees_dollars"])
        == Decimal(b["net_dollars"]) - Decimal(a["net_dollars"])
        == Decimal(cell["saved_fees_dollars"])
        >= 0
        and Decimal(a["turnover_dollars"]) - Decimal(b["turnover_dollars"])
        == Decimal(cell["saved_turnover_dollars"])
        >= 0,
        "cost_identity",
    )


def compare(streams, emergency, deadline, torch, parent, prior, scope_hash):
    result = {**failure(scope_hash, None), "status": "complete"}
    result.pop("reason")
    parents = {sessions.cell_key(c): c for p in prior.values() for c in p["cells"]}
    for symbol, bars in streams:
        index = {b.start_ts: b for b in bars}
        require(len(index) == len(bars) and list(index) == sorted(index), "source_order")
        schedule = sessions.regular_sessions(bars)
        for number, plan in enumerate(sessions.plans(schedule, 30), 1):
            h30.check_time(deadline)
            fold = sessions.prepare_fold(symbol, number, index, plan, 30)
            frozen = decisions(fold, index, torch, parent, prior)
            keys = session_keys(fold.evaluation, schedule)
            plans = [plan_positions(fold.evaluation, selected, keys) for _, selected in frozen]
            # Bind the existing result before applying the stricter common-session censor.
            controls = family.score(fold, frozen, index, emergency, deadline)
            require(
                all(c == parents.get(sessions.cell_key(c)) for c in controls),
                "parent_control_mismatch",
            )
            parent_fold = next(
                f
                for f in prior["cpu"]["folds"]
                if (f["symbol"], f["fold"], f["horizon_minutes"]) == (symbol, number, 30)
            )
            require(fold.facts == parent_fold, "parent_control_mismatch")
            result["parent_controls_reproduced"] += len(controls)
            outcomes, _ = sessions.outcomes(index, fold.evaluation, 30)
            keep, support = common_support(fold.evaluation, outcomes, keys)
            result["folds"].append({**fold.facts, "position_support": support})
            for cost in h30.COSTS:
                for (ident, selected), spans in zip(frozen, plans, strict=True):
                    result["cells"].append(
                        paired_cell(
                            ident,
                            fold.evaluation,
                            outcomes,
                            selected,
                            spans,
                            keep,
                            cost,
                            emergency,
                            deadline,
                        )
                    )
    validate_result(result, scope_hash)
    return result


def failure(scope_hash, reason):
    return dict(
        name=NAME,
        status="failed_all_cells",
        contract_sha256=scope_hash,
        reason=reason,
        cells=[],
        folds=[],
        parent_controls_reproduced=0,
        promotion=False,
        holdout_access=False,
        selection=False,
        training=False,
        gpu=False,
        evidence_grade=GRADE,
        interpretation=INTERPRETATION,
    )


def validate_result(result, scope_hash):
    require(
        result["name"] == NAME
        and result["status"] == "complete"
        and result["contract_sha256"] == scope_hash
        and result["evidence_grade"] == GRADE
        and result["interpretation"] == INTERPRETATION
        and all(
            result[k] is False
            for k in ("promotion", "holdout_access", "selection", "training", "gpu")
        ),
        "result_identity",
    )
    expected = [
        (s, f, 30, n, c, seed, cost)
        for s in h30.SYMBOLS
        for f in (1, 2)
        for cost in h30.COSTS
        for n, c, seed in CANDIDATES
    ]
    require([sessions.cell_key(c) for c in result["cells"]] == expected, "cell_matrix")
    require(
        [(f["symbol"], f["fold"], f["horizon_minutes"]) for f in result["folds"]]
        == [(s, f, 30) for s in h30.SYMBOLS for f in (1, 2)]
        and result["parent_controls_reproduced"] == 72,
        "parent_control_mismatch",
    )
    support_by_fold = {}
    for fold in result["folds"]:
        support = fold["position_support"]
        require(
            all(type(v) is int and v >= 0 for v in support.values())
            and support["eligible_decisions"] == fold["evaluation_inputs"]["eligible"]
            and support["eligible_decisions"]
            == support["common_scored_decisions"] + support["common_censored_decisions"]
            and support["raw_future_missing"] == fold["evaluation_outcomes"]["future_missing"]
            and support["raw_future_missing"] <= support["common_censored_decisions"]
            and support["censored_sessions"] <= fold["eval_calendar_sessions"]
            and support["common_scored_decisions"] >= 32
            and 8 <= support["common_scored_blocks"] <= support["common_scored_decisions"],
            "common_support_mismatch",
        )
        support_by_fold[fold["symbol"], fold["fold"]] = support
    decisions_by_identity = {}
    for cell in result["cells"]:
        support = support_by_fold[cell["symbol"], cell["fold"]]
        require(
            0 <= cell["selected_censored"] <= support["common_censored_decisions"]
            and cell["selected_censored"]
            <= cell["selected_decisions"]
            <= support["eligible_decisions"]
            and cell["selected_decisions"] - cell["selected_censored"]
            <= support["common_scored_decisions"],
            "common_support_mismatch",
        )
        key = tuple(cell[k] for k in family.IDENTITY)
        fingerprint = tuple(
            cell[k] for k in ("decision_sha256", "selected_decisions", "selected_censored")
        )
        require(
            decisions_by_identity.setdefault(key, fingerprint) == fingerprint,
            "decision_cost_changed",
        )
        validate_pair(cell)


def worker(root, market, scope_hash, result_path):
    deadline = time.monotonic() + SECONDS
    try:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        import torch
        from threadpoolctl import threadpool_limits

        require(
            h30.importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version"
        )
        verify(root, scope_hash)
        parent, receipt, prior, _ = lineage(root)
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        with threadpool_limits(limits=1):
            result = compare(
                h30.load_streams(market, receipt, deadline),
                h30.EmergencyStore(Path(result_path).parent / "emergency.json"),
                deadline,
                torch,
                parent,
                prior,
                scope_hash,
            )
        verify(root, scope_hash)
        h30.check_time(deadline)
        result["runtime"] = {"backend": "cpu", "environment": h30.runtime_identity()}
    except sessions.OutcomeSupportShortfall as error:
        result = failure(scope_hash, "common_outcome_support_shortfall")
        result["support"] = error.support
    except Exception:
        result = failure(scope_hash, "runtime_or_invariant_failure")
    with Path(result_path).open("xb") as handle:
        handle.write(h30.encode(result))
