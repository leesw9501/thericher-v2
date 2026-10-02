"""Fixed 12-calendar-month adjusted-close momentum; revised seen-data NAV proxy."""

from __future__ import annotations

import json
import re
import time
from datetime import date
from decimal import Decimal

from thericher_v2.research import tiingo_monthly_holding_development as monthly

base = monthly.base
NAME = "tiingo-adjusted-monthly-momentum-development-v1"
REPO, SYMBOLS, SECONDS = monthly.REPO, monthly.SYMBOLS, 600
TRAIN = ("2002-01-01", "2012-12-31")
PERIODS, COSTS = monthly.PERIODS, monthly.COSTS
POLICIES = ("abs_momentum", "train_risk_matched", "always_long", "cash")
CODE = (
    *monthly.CODE,
    "src/thericher_v2/research/tiingo_monthly_momentum_development.py",
    "scripts/run_tiingo_monthly_momentum_development.py",
)
METRICS = monthly.METRICS
encode, digest, require = monthly.encode, monthly.digest, monthly.require
atomic_new, _read, number = monthly.atomic_new, monthly._read, monthly.number
calendar_days, source_identity = monthly.calendar_days, monthly.source_identity
replay, variance, valid = monthly.replay, monthly.variance, monthly.valid
load_adjusted = monthly.load_adjusted
verify_metadata = base.verify_metadata
HASH = monthly.HASH
COUNTS = ("sessions", "months", "support_dates", "missing", "invalid")
TRAIN_FIELDS = (*COUNTS, "calibration_sha256")
GROUP_FIELDS = (*COUNTS, "symbol", "period", "train", "status", "benchmark_growth", "cohort_sha256")
CELL_FIELDS = (
    "symbol",
    "period",
    "cost_per_side_bps",
    "policy",
    "status",
    "trades",
    "action_sha256",
    *METRICS,
)


def configuration():
    return dict(
        symbols=list(SYMBOLS),
        train=list(TRAIN),
        periods=[list(p) for p in PERIODS],
        policies=list(POLICIES),
        cells=72,
        costs_per_side_bps=list(COSTS),
        signal="prior calendar month-end adjusted CLOSE / exactly12-month-earlier CLOSE -1 >0",
        target="binary long/cash at first scheduled month OPEN; equality flat; fixed all month",
        support="all scored sessions union13 exact prior calendar month-ends per decision",
        calibration="2002-2012 only; same complete daily NAV-return dates; population std ratio",
        risk_control="min(1,std(zero-fee TRAIN momentum)/std(passive)); zero numerator ->0",
        ledger="unit initial OPEN NAV; carry overnight; final CLOSE liquidation; cash interest0",
        fees="actual notional per side; piecewise post-fee target; initial/final trades included",
        missing="missing/invalid required date -> exact symbol/fold unavailable; no substitution",
        numeric="inherited Decimal50 HALF_EVEN ledger; relative1e-40 dust; aggregate12dp",
        assumptions=monthly.configuration()["assumptions"][:-1]
        + [
            "own zero-interest cash adaptation, NOT original Treasury-bill excess-return rule",
            "copyrighted Antonacci paper is concept reference only; no copied code/manuscript",
            "2001 prices are signal warmup only; no 2001 scored returns or risk calibration",
        ],
        strongest_kill="fails TRAIN-risk-matched control or advantage only surviving upmarket",
        budget=dict(
            cpu_threads=1,
            memory_bytes=2 * 1024**3,
            wall_seconds=SECONDS,
            gpu=False,
            passes=1,
            retries=False,
            fitting=False,
        ),
        scope=base.configuration()["scope"],
        weights_retained=False,
        selection=False,
        references=[
            "https://www.naaim.org/wp-content/uploads/2013/10/"
            "00D_Absolute-Momentum_gary_antonacci.pdf",
            "main independently retrieved official concept and Tiingo adjustment semantics",
        ],
        prior_families=monthly.configuration()["prior_families"] + [monthly.NAME],
    )


def build_plan(days):
    monthly.build_plan(days)  # Calendar shape/scope only; no parent TRAIN or signal reuse.
    ends = {d[:7]: d for d in days}

    def segment(first, last):
        indices = [i for i, d in enumerate(days) if first <= d <= last]
        require(bool(indices), "calendar_support")
        bounds = [indices[0], indices[-1] + 1]
        decisions = []
        for i in monthly.month_indices(days, bounds):
            d = date.fromisoformat(days[i])
            serial = d.year * 12 + d.month - 1
            months = [f"{n // 12:04d}-{n % 12 + 1:02d}" for n in range(serial - 13, serial)]
            require(all(m in ends for m in months), "historical_month_calendar_missing")
            history = [ends[m] for m in months]
            require(history[-1] < days[i], "incomplete_month_signal")
            decisions.append(dict(index=i, month_ends=history))
        support = sorted(
            set(days[bounds[0] : bounds[1]])
            | {d for action in decisions for d in action["month_ends"]}
        )
        return dict(bounds=bounds, decisions=decisions, support=support)

    return dict(
        days=list(days),
        train=segment(*TRAIN),
        periods=[dict(period=p, **segment(a, b)) for p, a, b in PERIODS],
    )


def proposed_contract(_market_data_root=None):
    config, source = configuration(), source_identity()
    return dict(
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=source,
        source_sha256=digest(encode(source)),
        plan=build_plan(calendar_days()),
        code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE},
    )


def _fields(value, keys):
    require(type(value) is dict and set(value) == set(keys), "closed_fields")


def _hash(value):
    return type(value) is str and re.fullmatch(HASH, value) is not None


def header(contract, pin):
    _fields(
        contract,
        ("name", "config", "config_sha256", "source", "source_sha256", "plan", "code_sha256"),
    )
    require(contract["name"] == NAME and digest(encode(contract)) == pin, "contract_binding")
    for key, expected in (("config", configuration()), ("source", source_identity())):
        require(
            encode(contract[key]) == encode(expected)
            and contract[key + "_sha256"] == digest(encode(expected)),
            key + "_changed",
        )
    require(
        encode(contract["plan"]) == encode(build_plan(contract["plan"]["days"])), "plan_changed"
    )
    require(
        set(contract["code_sha256"]) == set(CODE)
        and all(_hash(v) for v in contract["code_sha256"].values()),
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
        dataset_hash=digest(encode(contract["source"])),
        split_hash=digest(encode(contract["plan"])),
        cost_model_hash=digest(encode(COSTS)),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )


def freeze(artifact_root, market_data_root):
    verify_metadata(artifact_root, market_data_root)
    contract = proposed_contract(market_data_root)
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research") / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def verify(artifact_root, market_data_root, pin):
    output = base.ensure_external_artifact_directory(artifact_root, REPO, "research", NAME)
    raw = _read(output / "precommit.json")
    require(
        digest(raw) == pin and raw == encode(proposed_contract(market_data_root)),
        "precommit_changed",
    )
    verify_metadata(artifact_root, market_data_root)
    return output, json.loads(raw)


def gaps(rows, segment):
    needed = [rows.get(d) for d in segment["support"]]
    return sum(r is None for r in needed), sum(r is not None and not valid(r) for r in needed)


def targets(rows, segment):
    result = {}
    for decision in segment["decisions"]:
        history = [rows.get(d) for d in decision["month_ends"]]
        # Comparing positive closes gives the exact sign without ratio rounding at equality.
        result[decision["index"]] = (
            Decimal(int(history[-1].adj_close > history[0].adj_close))
            if all(valid(r) for r in history)
            else None
        )
    return result


@monthly._decimal
def calibrate(rows, plan, *, deadline):
    segment = plan["train"]
    missing, invalid = gaps(rows, segment)
    facts = dict(
        sessions=segment["bounds"][1] - segment["bounds"][0],
        months=len(segment["decisions"]),
        support_dates=len(segment["support"]),
        missing=missing,
        invalid=invalid,
        calibration_sha256=None,
    )
    if missing or invalid:
        return None, facts
    actions = targets(rows, segment)
    managed = replay(rows, plan["days"], segment["bounds"], actions, "0", deadline=deadline)
    passive = replay(
        rows,
        plan["days"],
        segment["bounds"],
        dict.fromkeys(actions, Decimal(1)),
        "0",
        deadline=deadline,
    )
    raw = variance(passive["returns"])
    if raw == 0:
        return None, facts
    constant = min(Decimal(1), (variance(managed["returns"]) / raw).sqrt())
    facts["calibration_sha256"] = digest(encode(str(constant)))
    return constant, facts


@monthly._decimal
def evaluate(rows_by_symbol, contract, pin, *, deadline):
    result = header(contract, pin)
    require(set(rows_by_symbol) == set(SYMBOLS), "symbol_set")
    groups, cells = [], []
    for symbol in SYMBOLS:
        require(time.monotonic() < deadline, "hard_timeout")
        stream = rows_by_symbol[symbol]
        require(
            all(r.symbol == symbol and type(r.session_date) is date for r in stream), "row_identity"
        )
        require(
            all(a.session_date < b.session_date for a, b in zip(stream, stream[1:], strict=False)),
            "row_order",
        )
        rows = {r.session_date.isoformat(): r for r in stream}
        constant, training = calibrate(rows, contract["plan"], deadline=deadline)
        for segment in contract["plan"]["periods"]:
            days, bounds = contract["plan"]["days"], segment["bounds"]
            missing, invalid = gaps(rows, segment)
            available = not (missing or invalid) and constant is not None
            managed = targets(rows, segment)
            actions = (
                managed,
                dict.fromkeys(managed, constant),
                dict.fromkeys(managed, Decimal(1)),
                dict.fromkeys(managed, Decimal(0)),
            )
            group = dict(
                symbol=symbol,
                period=segment["period"],
                sessions=bounds[1] - bounds[0],
                months=len(managed),
                support_dates=len(segment["support"]),
                missing=missing,
                invalid=invalid,
                train=training,
                status="evaluated" if available else "input_unavailable",
                cohort_sha256=digest(encode(segment["support"])),
                benchmark_growth=number(
                    rows[days[bounds[1] - 1]].adj_close / rows[days[bounds[0]]].adj_open
                )
                if available
                else None,
            )
            groups.append(group)
            for cost in COSTS:
                batch = []
                for policy, weights in zip(POLICIES, actions, strict=True):
                    fingerprint = (
                        digest(encode([(days[i], str(w.normalize())) for i, w in weights.items()]))
                        if available
                        else None
                    )
                    cell = dict(
                        symbol=symbol,
                        period=segment["period"],
                        cost_per_side_bps=cost,
                        policy=policy,
                        status=group["status"],
                        trades=None,
                        action_sha256=fingerprint,
                        **dict.fromkeys(METRICS),
                    )
                    if available:
                        scored = replay(rows, days, bounds, weights, cost, deadline=deadline)
                        cell.update({k: number(scored[k]) for k in METRICS[:5]})
                        cell["trades"] = scored["trades"]
                    batch.append(cell)
                if available:
                    for cell in batch:
                        for field, control in zip(METRICS[5:], batch[1:3], strict=True):
                            cell[field] = number(
                                Decimal(cell["final_nav"]) - Decimal(control["final_nav"])
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


def _counts(record, segment):
    require(all(type(record[k]) is int and record[k] >= 0 for k in COUNTS), "counts")
    require(
        record["sessions"] == segment["bounds"][1] - segment["bounds"][0]
        and record["months"] == len(segment["decisions"])
        and record["support_dates"] == len(segment["support"])
        and record["missing"] + record["invalid"] <= record["support_dates"],
        "support_counts",
    )


def _numeric(value):
    require(type(value) is str and len(value) <= 80, "metric_type")
    parsed = Decimal(value)
    require(parsed.is_finite() and value == number(parsed), "metric_numeric")
    return parsed


@monthly._decimal
def validate_result(result, contract, pin):
    expected = header(contract, pin)
    if result.get("status") == "failed":
        require(
            encode(result) == encode(failure(contract, pin, result.get("reason"))), "failure_shape"
        )
        return
    _fields(result, (*expected, "status", "criterion", "groups", "cells"))
    require(
        encode({k: result[k] for k in expected}) == encode(expected)
        and result["criterion"] == "descriptive_only_no_selection",
        "result_binding",
    )
    keys = [(s, p) for s in SYMBOLS for p, _, _ in PERIODS]
    require([(g["symbol"], g["period"]) for g in result["groups"]] == keys, "group_matrix")
    training = {}
    for g in result["groups"]:
        _fields(g, GROUP_FIELDS)
        segment = next(p for p in contract["plan"]["periods"] if p["period"] == g["period"])
        _counts(g, segment)
        t = g["train"]
        _fields(t, TRAIN_FIELDS)
        _counts(t, contract["plan"]["train"])
        require(training.setdefault(g["symbol"], t) == t, "TRAIN_recalibration")
        require(
            t["calibration_sha256"] is None
            or (_hash(t["calibration_sha256"]) and t["missing"] == t["invalid"] == 0),
            "calibration_hash",
        )
        available = t["calibration_sha256"] is not None and g["missing"] == g["invalid"] == 0
        require(
            g["status"] == ("evaluated" if available else "input_unavailable")
            and g["cohort_sha256"] == digest(encode(segment["support"])),
            "group_status",
        )
        require(
            _numeric(g["benchmark_growth"]) > 0 if available else g["benchmark_growth"] is None,
            "benchmark_growth",
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
        [(c["symbol"], c["period"], c["cost_per_side_bps"], c["policy"]) for c in cells]
        == [(s, p, c, n) for s, p in keys for c in COSTS for n in POLICIES],
        "cell_matrix",
    )
    paths, prior_nav = {}, {}
    for i, c in enumerate(cells):
        _fields(c, CELL_FIELDS)
        g = result["groups"][i // (len(COSTS) * len(POLICIES))]
        require(c["status"] == g["status"], "cell_status")
        key = c["symbol"], c["period"], c["policy"]
        require(
            paths.setdefault(key, c["action_sha256"]) == c["action_sha256"], "cost_changes_targets"
        )
        if c["status"] == "input_unavailable":
            require(
                c["action_sha256"] is None
                and c["trades"] is None
                and all(c[k] is None for k in METRICS),
                "unavailable_metrics",
            )
            continue
        require(_hash(c["action_sha256"]), "action_hash")
        nav, dd, std, fees, turnover, *_ = [_numeric(c[k]) for k in METRICS]
        require(
            nav > 0
            and 0 <= dd < 1
            and std >= 0
            and fees >= 0
            and turnover >= 0
            and type(c["trades"]) is int
            and 0 <= c["trades"] <= g["months"] + 1,
            "metric_domain",
        )
        tol, fee = (
            Decimal("3e-11") * (1 + nav + fees + turnover),
            Decimal(c["cost_per_side_bps"]) / 10000,
        )
        require(abs(fees - fee * turnover) <= tol, "fee_identity")
        require(nav <= prior_nav.get(key, nav) + tol, "cost_NAV_monotonicity")
        prior_nav[key] = nav
        if c["policy"] == "cash":
            require(nav == 1 and dd == std == fees == turnover == c["trades"] == 0, "cash_identity")
        if c["policy"] == "always_long":
            growth = Decimal(g["benchmark_growth"])
            require(
                c["trades"] == 2
                and abs(nav - growth * (1 - fee) / (1 + fee)) <= tol
                and abs(turnover - (1 + growth) / (1 + fee)) <= tol,
                "long_endpoints",
            )
        batch = cells[i // 4 * 4 : i // 4 * 4 + 4]
        for field, control in zip(METRICS[5:], batch[1:3], strict=True):
            require(
                abs(nav - Decimal(control["final_nav"]) - Decimal(c[field])) <= tol,
                "paired_difference",
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
        rows = load_adjusted(market_data_root / base.SNAPSHOT, market_data_root)
        result = evaluate(rows, contract, pin, deadline=deadline)
        verify(artifact_root, market_data_root, pin)
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure")
    atomic_new(path, result)


def worker_entry(*args):
    try:
        run_worker(*args)
    except BaseException:
        raise SystemExit(1) from None
