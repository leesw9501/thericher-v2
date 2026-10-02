"""One fixed daily ETF adaptation, not a Moreira/Muir replication or Paper input."""

from __future__ import annotations

import importlib.metadata
import json
import re
import time
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from statistics import median

from thericher_v2.research import tiingo_geometry_ridge_development as geometry
from thericher_v2.research import tiingo_month_start_development as base

NAME = "tiingo-d1-volatility-allocation-development-v1"
REPO, SYMBOLS, COSTS, SECONDS = base.REPO, base.SYMBOLS, base.COSTS, 600
WINDOW = 22
TRAIN = ("2001-01-01", "2012-12-31")
PERIODS = geometry.FOLDS
POLICIES = ("vol_managed", "train_risk_matched", "always_long", "cash")
encode, digest, require = base.encode, base.digest, base.require
atomic_new, _read = base.atomic_new, base._read
CODE = (
    *geometry.CODE,
    "src/thericher_v2/research/tiingo_volatility_allocation_development.py",
    "scripts/run_tiingo_volatility_allocation_development.py",
)
METRICS = (
    "mean_gross_bps",
    "paired_mean_net_bps",
    "net_std_bps",
    "mean_exposure",
    "rms_exposure",
    "paired_difference_vs_risk_matched_bps",
    "paired_difference_vs_always_long_bps",
)
COUNT_FIELDS = {"planned", "eligible", "observed", "past_excluded", "censored", "zero_variance"}
HASH = r"sha256:[0-9a-f]{64}"


def configuration():
    prior = base.configuration()
    return dict(
        symbols=list(SYMBOLS),
        train=list(TRAIN),
        periods=[list(p) for p in PERIODS],
        policies=list(POLICIES),
        cells=72,
        history_sessions=WINDOW,
        costs_all_in_roundtrip_bps=list(COSTS),
        returns="signed raw10000*(close/open-1); prior22 scheduled completed sessions; ddof=0",
        calibration="per_symbol TRAIN median positive prior22 variance; no EVAL input",
        earliest_history="calendar warmup from 2000-12; TRAIN targets start 2001-01",
        exposure="min(1,TRAIN_vref/prior22variance); zero_if_zero_variance_or_missing_history",
        risk_control="min(1,std(TRAIN_w*y)/std(TRAIN_y)); ddof0; eligible observed TRAIN once",
        eligibility="complete prior22 including zero variance; all four policies same cohort",
        missing="no shift/impute/bridge; target missing censored after exposure fixed",
        insufficient="no_positive_TRAIN_variance_or_zero_target_std; symbol_scoped_unavailable",
        timing="past completed closes assumed available before target open; same-day close exit",
        accounting="w*(target_bps-roundtrip_bps); daily entry/exit; no overnight/leverage/shorting",
        metrics="paired means/population net std, mean/RMS exposure; no NAV/drawdown/Sharpe",
        strongest_kill="apparent benefit entirely exposure reduction vs TRAIN-risk-matched control",
        technical_kills=[
            "future_changes_prior_exposure",
            "missing_history_or_target_shift",
            "calibration_reads_EVAL",
            "source_or_availability_binding_failure",
        ],
        reference=dict(
            url="https://law.yale.edu/sites/default/files/area/workshop/leo/leo17_moreira.pdf",
            custody="main independently re-retrieved; no download by this implementation",
            original="monthly factor inverse-realized-variance; daily ETFs NOT replication",
        ),
        calendar=prior["calendar"],
        numeric="Decimal50; aggregate12dp ROUND_HALF_EVEN",
        budget=dict(
            cpu_threads=1,
            wall_seconds=SECONDS,
            memory_bytes=base.MEMORY_BYTES,
            gpu=False,
            passes=1,
            retries=False,
        ),
        resource_owner=prior["resource_owner"],
        scope=prior["scope"],
        weights_retained=False,
        tuning=False,
        selection=False,
        prior_families=prior["prior_families"] + [base.NAME, geometry.NAME],
        assumptions=[a for a in prior["assumptions"] if not a.startswith("session_11_")]
        + [
            "TRAIN calibration is retrospective; EVAL weights past-only conditional on fixed TRAIN",
            "prior22 histories overlap; ETFs correlated; no pooled independent sample claim",
            "TRAIN risk matching is gross and need not match EVAL realized risk",
            "raw intraday corporate-action/availability and auction fills remain unqualified",
            "flat proportional costs omit capacity/impact; not Execution-attested replay parity",
        ],
    )


def build_plan(days):
    require(
        days and all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in days),
        "calendar_date",
    )
    require(all(a < b for a, b in zip(days, days[1:], strict=False)), "calendar_order")
    require(days[0] >= "2000-12-01" and days[-1] <= "2026-07-31", "calendar_scope")

    def bounds(first, last):
        indices = [i for i, d in enumerate(days) if first <= d <= last]
        require(bool(indices), "calendar_support")
        return [indices[0], indices[-1] + 1]

    return dict(
        days=list(days),
        train=bounds(*TRAIN),
        periods=[dict(period=p, bounds=bounds(a, b)) for p, a, b in PERIODS],
    )


def proposed_contract():
    config, source = configuration(), base.source_identity()
    return dict(
        schema_version=1,
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=source,
        source_sha256=digest(encode(source)),
        plan=build_plan(geometry.calendar_days()),
        runtime={"pandas-market-calendars": importlib.metadata.version("pandas-market-calendars")},
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def header(contract, pin):
    require(
        set(contract)
        == {
            "schema_version",
            "name",
            "config",
            "config_sha256",
            "source",
            "source_sha256",
            "plan",
            "runtime",
            "code_sha256",
        },
        "contract_fields",
    )
    require(
        digest(encode(contract)) == pin
        and contract["name"] == NAME
        and type(contract["schema_version"]) is int
        and contract["schema_version"] == 1,
        "contract_binding",
    )
    require(
        encode(contract["config"]) == encode(configuration())
        and contract["config_sha256"] == digest(encode(configuration())),
        "config_changed",
    )
    require(
        contract["source"] == base.source_identity()
        and contract["source_sha256"] == digest(encode(base.source_identity())),
        "source_changed",
    )
    require(
        encode(contract["plan"]) == encode(build_plan(contract["plan"]["days"])), "plan_changed"
    )
    require(contract["runtime"] == {"pandas-market-calendars": "5.4.0"}, "runtime_changed")
    require(
        set(contract["code_sha256"]) == set(CODE)
        and all(re.fullmatch(HASH, v) for v in contract["code_sha256"].values()),
        "code_pins",
    )
    return dict(
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        source_sha256=contract["source_sha256"],
        scope=configuration()["scope"],
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
    return output, json.loads(raw)


def moments(values):
    mean = sum(values, Decimal(0)) / len(values)
    return mean, sum((v - mean) ** 2 for v in values) / len(values)


def prior_variances(rows, days, bounds):
    result = []
    for i in range(*bounds):
        history = [geometry.outcome(rows.get(d)) for d in days[max(0, i - WINDOW) : i]]
        result.append(
            moments(history)[1]
            if len(history) == WINDOW and all(v is not None for v in history)
            else None
        )
    return result


def exposures(variances, vref):
    return [min(Decimal(1), vref / v) if v is not None and v > 0 else Decimal(0) for v in variances]


def calibrate(rows, plan):
    """Only TRAIN targets and earlier scheduled history can enter this calibration."""
    days, bounds = plan["days"], plan["train"]
    variances = prior_variances(rows, days, bounds)
    positive = [v for v in variances if v is not None and v > 0]
    eligible = [i for i, v in zip(range(*bounds), variances, strict=True) if v is not None]
    targets = [geometry.outcome(rows.get(days[i])) for i in eligible]
    observed = [i for i, y in enumerate(targets) if y is not None]
    facts = dict(
        planned=bounds[1] - bounds[0],
        eligible=len(eligible),
        observed=len(observed),
        positive_variance=len(positive),
        censored=len(eligible) - len(observed),
    )
    vref, constant = None, None
    if positive and observed:
        vref = median(positive)
        weights = exposures(variances, vref)
        y = [targets[i] for i in observed]
        var_y = moments(y)[1]
        if var_y > 0:
            managed = [weights[eligible[i] - bounds[0]] * targets[i] for i in observed]
            constant = min(Decimal(1), (moments(managed)[1] / var_y).sqrt())
    facts["calibration_sha256"] = (
        digest(encode([str(vref), str(constant)])) if constant is not None else None
    )
    return vref, constant, facts


def evaluate(rows_by_symbol, contract, pin, *, deadline):
    result = header(contract, pin)
    require(set(rows_by_symbol) == set(SYMBOLS), "symbol_set")
    groups, cells = [], []
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        for symbol in SYMBOLS:
            require(time.monotonic() < deadline, "hard_timeout")
            rows = rows_by_symbol[symbol]
            require(
                all(r.symbol == symbol and type(r.session_date) is date for r in rows),
                "row_identity",
            )
            require(
                all(a.session_date < b.session_date for a, b in zip(rows, rows[1:], strict=False)),
                "duplicate_or_nonmonotone_rows",
            )
            indexed = {r.session_date.isoformat(): r for r in rows}
            vref, constant, train = calibrate(indexed, contract["plan"])
            for period in contract["plan"]["periods"]:
                require(time.monotonic() < deadline, "hard_timeout")
                days, bounds = contract["plan"]["days"], period["bounds"]
                variances = prior_variances(indexed, days, bounds)
                eligible = [i for i, v in enumerate(variances) if v is not None]
                # Fix every decision before attaching its outcome; missing history is flat/excluded.
                actions = dict(
                    vol_managed=exposures(variances, vref)
                    if vref is not None
                    else [Decimal(0)] * len(variances),
                    train_risk_matched=[constant or Decimal(0)] * len(variances),
                    always_long=[Decimal(1)] * len(variances),
                    cash=[Decimal(0)] * len(variances),
                )
                targets = {i: geometry.outcome(indexed.get(days[bounds[0] + i])) for i in eligible}
                observed = [i for i in eligible if targets[i] is not None]
                available = constant is not None and bool(observed)
                group = dict(
                    symbol=symbol,
                    period=period["period"],
                    planned=len(variances),
                    eligible=len(eligible),
                    observed=len(observed),
                    past_excluded=len(variances) - len(eligible),
                    censored=len(eligible) - len(observed),
                    zero_variance=sum(v == 0 for v in variances),
                    train=train,
                    status="evaluated" if available else "input_unavailable",
                    cohort_sha256=digest(
                        encode(
                            [
                                [days[bounds[0] + i] for i in indices]
                                for indices in (eligible, observed)
                            ]
                        )
                    ),
                )
                groups.append(group)
                for cost in COSTS:
                    batch = []
                    for policy in POLICIES:
                        cell = dict(
                            symbol=symbol,
                            period=period["period"],
                            cost_bps=cost,
                            policy=policy,
                            observed=len(observed),
                            status=group["status"],
                            action_sha256=digest(
                                encode(
                                    [
                                        (days[bounds[0] + i], str(actions[policy][i]))
                                        for i in eligible
                                    ]
                                )
                            )
                            if constant is not None
                            else None,
                            **dict.fromkeys(METRICS),
                        )
                        if available:
                            w = [actions[policy][i] for i in observed]
                            gross = [actions[policy][i] * targets[i] for i in observed]
                            net = [g - cost * a for g, a in zip(gross, w, strict=True)]
                            cell.update(
                                zip(
                                    METRICS[:5],
                                    map(
                                        base._number,
                                        (
                                            moments(gross)[0],
                                            moments(net)[0],
                                            moments(net)[1].sqrt(),
                                            moments(w)[0],
                                            (sum(a * a for a in w) / len(w)).sqrt(),
                                        ),
                                    ),
                                    strict=True,
                                )
                            )
                        batch.append(cell)
                    if available:
                        for cell in batch:
                            for field, control in zip(METRICS[5:], batch[1:3], strict=True):
                                cell[field] = base._number(
                                    Decimal(cell[METRICS[1]]) - Decimal(control[METRICS[1]])
                                )
                    cells.extend(batch)
    result.update(
        status="complete"
        if all(g["status"] == "evaluated" for g in groups)
        else "input_unavailable",
        criterion="descriptive_only_no_selection",
        groups=groups,
        cells=cells,
    )
    validate_result(result, contract, pin)
    return result


def failure(contract, pin, reason):
    require(reason in base.FAILURES, "failure_category")
    return dict(
        header(contract, pin),
        status="failed",
        reason=reason,
        criterion="not_evaluable",
        groups=[],
        cells=[],
    )


def validate_result(result, contract, pin):
    expected = header(contract, pin)
    if result.get("status") == "failed":
        require(
            encode(result) == encode(failure(contract, pin, result.get("reason"))), "failure_shape"
        )
        return
    require(
        set(result) == set(expected) | {"status", "criterion", "groups", "cells"}
        and encode({k: result[k] for k in expected}) == encode(expected)
        and result["criterion"] == "descriptive_only_no_selection",
        "result_binding",
    )
    keys = [(s, p) for s in SYMBOLS for p, _, _ in PERIODS]
    require([(g["symbol"], g["period"]) for g in result["groups"]] == keys, "group_matrix")
    trains = {}
    for g in result["groups"]:
        require(
            set(g) == COUNT_FIELDS | {"symbol", "period", "train", "status", "cohort_sha256"},
            "group_fields",
        )
        require(all(type(g[k]) is int and g[k] >= 0 for k in COUNT_FIELDS), "count_type")
        bounds = next(
            p["bounds"] for p in contract["plan"]["periods"] if p["period"] == g["period"]
        )
        require(
            g["planned"] == bounds[1] - bounds[0] == g["eligible"] + g["past_excluded"]
            and g["eligible"] == g["observed"] + g["censored"]
            and g["zero_variance"] <= g["eligible"],
            "counts",
        )
        t = g["train"]
        require(
            set(t)
            == {
                "planned",
                "eligible",
                "observed",
                "positive_variance",
                "censored",
                "calibration_sha256",
            },
            "train_fields",
        )
        require(
            all(type(t[k]) is int and t[k] >= 0 for k in t if k != "calibration_sha256")
            and t["planned"] == contract["plan"]["train"][1] - contract["plan"]["train"][0]
            and t["observed"] + t["censored"] == t["eligible"] <= t["planned"]
            and t["positive_variance"] <= t["eligible"],
            "train_counts",
        )
        require(trains.setdefault(g["symbol"], t) == t, "recalibration")
        require(
            t["calibration_sha256"] is None
            or (
                t["positive_variance"] > 0
                and t["observed"] >= 2
                and re.fullmatch(HASH, t["calibration_sha256"])
            ),
            "calibration_hash",
        )
        require(re.fullmatch(HASH, g["cohort_sha256"]), "cohort_hash")
        require(
            g["status"]
            == (
                "evaluated"
                if t["calibration_sha256"] is not None and g["observed"] > 0
                else "input_unavailable"
            ),
            "group_status",
        )
    require(
        result["status"]
        == (
            "complete"
            if all(g["status"] == "evaluated" for g in result["groups"])
            else "input_unavailable"
        ),
        "status",
    )
    cells = result["cells"]
    require(
        [(c["symbol"], c["period"], c["cost_bps"], c["policy"]) for c in cells]
        == [(s, p, cost, policy) for s, p in keys for cost in COSTS for policy in POLICIES],
        "cell_matrix",
    )
    paths, constants = {}, {}
    for c in cells:
        require(
            set(c)
            == {"symbol", "period", "cost_bps", "policy", "observed", "status", "action_sha256"}
            | set(METRICS),
            "cell_fields",
        )
        g = result["groups"][keys.index((c["symbol"], c["period"]))]
        require(
            type(c["observed"]) is int
            and c["observed"] == g["observed"]
            and type(c["cost_bps"]) is int
            and c["status"] == g["status"],
            "cell_counts",
        )
        require(
            c["action_sha256"] is None
            if g["train"]["calibration_sha256"] is None
            else re.fullmatch(HASH, c["action_sha256"]),
            "action_hash",
        )
        path_key = (c["symbol"], c["period"], c["policy"])
        require(
            paths.setdefault(path_key, c["action_sha256"]) == c["action_sha256"],
            "cost_changes_exposure",
        )
        if c["status"] == "input_unavailable":
            require(all(c[k] is None for k in METRICS), "unavailable_metrics")
            continue
        for k in METRICS:
            v = c[k]
            require(
                type(v) is str
                and len(v) <= 80
                and Decimal(v).is_finite()
                and v == base._number(Decimal(v)),
                "metric_numeric",
            )
        gross, net, std, mean, rms = [Decimal(c[k]) for k in METRICS[:5]]
        tolerance = Decimal("3e-11")
        require(
            std >= 0 and 0 <= mean <= rms <= 1 and rms * rms <= mean + tolerance, "exposure_moments"
        )
        require(abs(gross - c["cost_bps"] * mean - net) <= tolerance, "cost_identity")
        if c["policy"] == "cash":
            require(gross == net == std == mean == rms == 0, "cash_identity")
        if c["policy"] == "always_long":
            require(mean == rms == 1, "long_identity")
        if c["policy"] == "train_risk_matched":
            require(mean == rms, "constant_identity")
            require(constants.setdefault(c["symbol"], mean) == mean, "EVAL_recalibration")
        path = (c["action_sha256"], c["observed"], c[METRICS[0]], c[METRICS[3]], c[METRICS[4]])
        metric_key = (*path_key, "metrics")
        require(paths.setdefault(metric_key, path) == path, "cost_changes_exposure")
        batch = [
            x
            for x in cells
            if (x["symbol"], x["period"], x["cost_bps"])
            == (c["symbol"], c["period"], c["cost_bps"])
        ]
        for field, control in zip(METRICS[5:], batch[1:3], strict=True):
            require(
                abs(net - Decimal(control[METRICS[1]]) - Decimal(c[field])) <= tolerance,
                "paired_difference",
            )
        if c["policy"] == "train_risk_matched":
            scale = 1 + abs(Decimal(batch[2][METRICS[0]])) + Decimal(batch[2][METRICS[2]])
            require(
                abs(gross - mean * Decimal(batch[2][METRICS[0]])) <= tolerance * scale
                and abs(std - mean * Decimal(batch[2][METRICS[2]])) <= tolerance * scale,
                "risk_control_identity",
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
        json.loads(_read(output / "started.json")) == {"contract_sha256": pin}, "attempt_binding"
    )
    try:
        snapshot = base.load_verified_tiingo_etf_d1_snapshot(
            market_data_root / base.SNAPSHOT,
            dataset_id=base.DATASET_ID,
            expected_dataset_hash=base.DATASET_HASH,
            expected_manifest_hash=base.MANIFEST_HASH,
            market_data_root=market_data_root,
            repo_root=REPO,
        )
        require(
            snapshot.snapshot.dataset_id == base.DATASET_ID
            and snapshot.snapshot.dataset_hash == base.DATASET_HASH
            and snapshot.snapshot.manifest_hash == base.MANIFEST_HASH,
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
