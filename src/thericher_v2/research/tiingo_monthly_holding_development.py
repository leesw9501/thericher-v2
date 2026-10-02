"""Fixed monthly adjusted-mark NAV development; not actual shares or broker parity."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import re
import time
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from functools import wraps
from statistics import median

from thericher_v2.data.tiingo_adjusted_etf_daily import RAW_SHA256
from thericher_v2.research import tiingo_month_start_development as base

NAME = "tiingo-adjusted-monthly-holding-development-v1"
REPO, SYMBOLS, SECONDS = base.REPO, base.SYMBOLS, 600
TRAIN = ("2001-01-01", "2012-12-31")
PERIODS = (("2013-2019", "2013-01-01", "2019-12-31"), ("2020-2026-07", "2020-01-01", "2026-07-31"))
COSTS = ("2.5", "5", "10")
POLICIES = ("vol_managed", "train_risk_matched", "always_long", "cash")
WINDOW, MEMORY_BYTES, EPS = 22, 2 * 1024**3, Decimal("1e-40")
encode, digest, require = base.encode, base.digest, base.require
atomic_new, _read, number = base.atomic_new, base._read, base._number
DATA_MODULE = "thericher_v2.data.tiingo_adjusted_etf_daily"
CODE = (
    *base.CODE,
    "src/thericher_v2/data/tiingo_adjusted_etf_daily.py",
    "src/thericher_v2/contracts.py",
    "src/thericher_v2/serialization.py",
    "src/thericher_v2/data/tiingo_eod.py",
    "src/thericher_v2/research/tiingo_monthly_holding_development.py",
    "scripts/run_tiingo_monthly_holding_development.py",
)
METRICS = (
    "final_nav",
    "max_close_drawdown",
    "daily_return_std",
    "fees_initial_nav",
    "turnover_initial_nav",
    "difference_vs_risk_matched_nav",
    "difference_vs_long_nav",
)
HASH = r"sha256:[0-9a-f]{64}"


def configuration():
    return dict(
        symbols=list(SYMBOLS),
        train=list(TRAIN),
        periods=[list(p) for p in PERIODS],
        policies=list(POLICIES),
        cells=72,
        costs_per_side_bps=list(COSTS),
        history_returns=WINDOW,
        signal="22 prior scheduled adjusted close-to-close signed bps returns, 23 closes; ddof0",
        calibration="TRAIN median positive daily prior22 variances; no EVAL inputs",
        monthly_target="min(1,vref/prior22variance) at first OPEN; missing/zero variance ->0",
        risk_control="min(1,std(TRAIN managed NAV returns)/std(passive)); zero fee, same warm rows",
        timing="prior completed CLOSE only; fixed monthly target, no daily rebalancing",
        ledger="initial OPEN NAV1; fractional adjusted-price units+cash; CLOSE marks/final exit",
        fees="actual traded notional; piecewise post-fee target; initial/final trades included",
        missing="calendar gap or invalid OHLC -> whole symbol/fold unavailable; no bridge/impute",
        numeric="Decimal50 HALF_EVEN; relative1e-40 arithmetic dust only; aggregate12dp",
        assumptions=[
            "seen revised non-PIT provider-adjusted marks; availability assumed not attested",
            "adjusted-mark proxy, not actual shares or dividend reinvestment qualification",
            "no divCash/splitFactor additions; provider adjustment already embedded",
            "cash earns no interest; no overnight financing, leverage, shorts or borrowing",
            "auction access, impact, capacity and broker fees unverified; no Execution parity",
            "surviving correlated ETFs and overlapping research; folds not fresh holdouts",
            "TRAIN calibration retrospective; EVAL decisions causal conditional on frozen TRAIN",
            "monthly ETF adaptation NOT replication of original monthly factor paper",
        ],
        strongest_kill="benefit solely exposure reduction versus TRAIN-risk-matched control",
        budget=dict(
            cpu_threads=1,
            memory_bytes=MEMORY_BYTES,
            wall_seconds=SECONDS,
            gpu=False,
            passes=1,
            retries=False,
        ),
        scope=base.configuration()["scope"],
        weights_retained=False,
        selection=False,
        references=[
            "https://law.yale.edu/sites/default/files/area/workshop/leo/leo17_moreira.pdf",
            "main re-retrieved official Tiingo adjustment semantics; no acquisition here",
        ],
        prior_families=base.configuration()["prior_families"]
        + [base.NAME, "tiingo-d1-volatility-allocation-development-v1"],
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


def source_identity():
    """Data-owned fixed raw pins; no provider row or metadata reads here."""
    return dict(
        base.source_identity(),
        view="provider_adjusted_OHLC_from_immutable_raw",
        raw_sha256=dict(RAW_SHA256),
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


def header(contract, pin):
    require(
        set(contract)
        == {"name", "config", "config_sha256", "source", "source_sha256", "plan", "code_sha256"},
        "contract_fields",
    )
    require(contract["name"] == NAME and digest(encode(contract)) == pin, "contract_binding")
    require(
        encode(contract["config"]) == encode(configuration())
        and contract["config_sha256"] == digest(encode(configuration())),
        "config_changed",
    )
    require(
        contract["source"] == source_identity()
        and contract["source_sha256"] == digest(encode(source_identity())),
        "source_changed",
    )
    require(
        encode(contract["plan"]) == encode(build_plan(contract["plan"]["days"])), "plan_changed"
    )
    require(
        set(contract["code_sha256"]) == set(CODE)
        and all(re.fullmatch(HASH, p) for p in contract["code_sha256"].values()),
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
    base.verify_metadata(artifact_root, market_data_root)
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
    base.verify_metadata(artifact_root, market_data_root)
    return output, json.loads(raw)


def valid(row):
    if row is None:
        return False
    values = (row.adj_open, row.adj_high, row.adj_low, row.adj_close)
    return all(isinstance(v, Decimal) and v.is_finite() and v > 0 for v in values) and (
        row.adj_low
        <= min(row.adj_open, row.adj_close)
        <= max(row.adj_open, row.adj_close)
        <= row.adj_high
    )


def variance(values):
    mean = sum(values, Decimal(0)) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def prior_variance(rows, days, i):
    history = [rows.get(d) for d in days[max(0, i - WINDOW - 1) : i]]
    if len(history) != WINDOW + 1 or not all(valid(r) for r in history):
        return None
    return variance(
        [
            10000 * (b.adj_close / a.adj_close - 1)
            for a, b in zip(history, history[1:], strict=False)
        ]
    )


def month_indices(days, bounds):
    return [i for i in range(*bounds) if i == bounds[0] or days[i][:7] != days[i - 1][:7]]


def targets(rows, days, bounds, vref):
    return {
        i: (
            min(Decimal(1), vref / v)
            if vref is not None and v is not None and v > 0
            else Decimal(0)
        )
        for i in month_indices(days, bounds)
        for v in [prior_variance(rows, days, i)]
    }


def _decimal(function):
    @wraps(function)
    def call(*args, **kwargs):
        with localcontext() as context:
            context.prec, context.rounding = 50, ROUND_HALF_EVEN
            return function(*args, **kwargs)

    return call


@_decimal
def rebalance(stock, nav, weight, fee):
    """Solve post-fee target exactly in notional space; suppress Decimal arithmetic dust."""
    require(nav > 0 and 0 <= stock <= nav and 0 <= weight <= 1 and 0 <= fee < 1, "ledger_input")
    buy = weight * nav >= stock
    new_stock = (
        weight * (nav + fee * stock) / (1 + weight * fee)
        if buy
        else weight * (nav - fee * stock) / (1 - weight * fee)
    )
    turnover = abs(new_stock - stock)
    if turnover <= EPS * nav:
        new_stock, turnover = stock, Decimal(0)
    paid = fee * turnover
    cash = nav - new_stock - paid
    if abs(cash) <= EPS * nav:
        cash = Decimal(0)
    require(
        cash >= 0
        and new_stock >= 0
        and new_stock + cash > 0
        and abs(new_stock + cash + paid - nav) <= EPS * nav,
        "ledger_closure",
    )
    require(abs(new_stock / (new_stock + cash) - weight) <= EPS, "postfee_weight")
    return new_stock, cash, paid, turnover


@_decimal
def replay(rows, days, bounds, actions, cost_bps, *, deadline):
    cash, units, previous = Decimal(1), Decimal(0), Decimal(1)
    fees, turnover, trades, navs, returns = Decimal(0), Decimal(0), 0, [], []
    fee = Decimal(cost_bps) / 10000
    for i in range(*bounds):
        require(time.monotonic() < deadline, "hard_timeout")
        row = rows.get(days[i])
        require(valid(row), "calendar_gap_or_invalid_bar")
        if i in actions:
            stock = units * row.adj_open
            value, cash, paid, traded = rebalance(stock, cash + stock, actions[i], fee)
            units = value / row.adj_open
            fees, turnover, trades = fees + paid, turnover + traded, trades + int(traded > 0)
        nav = cash + units * row.adj_close
        if i == bounds[1] - 1:
            stock = units * row.adj_close
            _, cash, paid, traded = rebalance(stock, nav, Decimal(0), fee)
            units, nav = Decimal(0), cash
            fees, turnover, trades = fees + paid, turnover + traded, trades + int(traded > 0)
        require(nav > 0 and cash >= 0 and units >= 0, "nonpositive_NAV")
        navs.append(nav)
        returns.append(nav / previous - 1)
        previous = nav
    require(units == 0 and cash == navs[-1], "final_cash_closure")
    peak, drawdown = Decimal(1), Decimal(0)
    for nav in navs:
        peak, drawdown = max(peak, nav), max(drawdown, 1 - nav / max(peak, nav))
    return dict(
        final_nav=navs[-1],
        max_close_drawdown=drawdown,
        daily_return_std=variance(returns).sqrt(),
        fees_initial_nav=fees,
        turnover_initial_nav=turnover,
        trades=trades,
        navs=navs,
        returns=returns,
    )


def gaps(rows, days, bounds):
    needed = [rows.get(d) for d in days[max(0, bounds[0] - WINDOW - 1) : bounds[1]]]
    return sum(r is None for r in needed), sum(r is not None and not valid(r) for r in needed)


@_decimal
def calibrate(rows, plan, *, deadline):
    days, bounds = plan["days"], plan["train"]
    variances = {i: prior_variance(rows, days, i) for i in range(*bounds)}
    positive = [v for v in variances.values() if v is not None and v > 0]
    warm = [i - bounds[0] for i, v in variances.items() if v is not None]
    missing, invalid = gaps(rows, days, bounds)
    facts = dict(
        sessions=bounds[1] - bounds[0],
        warm_sessions=len(warm),
        positive_variances=len(positive),
        missing=missing,
        invalid=invalid,
        calibration_sha256=None,
    )
    if missing or invalid or not positive or not warm:
        return None, None, facts
    ref = median(positive)
    managed = replay(rows, days, bounds, targets(rows, days, bounds, ref), "0", deadline=deadline)
    passive = replay(
        rows,
        days,
        bounds,
        {i: Decimal(1) for i in month_indices(days, bounds)},
        "0",
        deadline=deadline,
    )
    raw = variance([passive["returns"][i] for i in warm])
    if raw == 0:
        return ref, None, facts
    constant = min(Decimal(1), (variance([managed["returns"][i] for i in warm]) / raw).sqrt())
    facts["calibration_sha256"] = digest(encode([str(ref), str(constant)]))
    return ref, constant, facts


def evaluate(rows_by_symbol, contract, pin, *, deadline):
    result, groups, cells = header(contract, pin), [], []
    require(set(rows_by_symbol) == set(SYMBOLS), "symbol_set")
    with localcontext() as context:
        context.prec, context.rounding = 50, ROUND_HALF_EVEN
        for symbol in SYMBOLS:
            require(time.monotonic() < deadline, "hard_timeout")
            stream = rows_by_symbol[symbol]
            require(
                all(r.symbol == symbol and type(r.session_date) is date for r in stream),
                "row_identity",
            )
            require(
                all(
                    a.session_date < b.session_date
                    for a, b in zip(stream, stream[1:], strict=False)
                ),
                "row_order",
            )
            rows = {r.session_date.isoformat(): r for r in stream}
            ref, constant, training = calibrate(rows, contract["plan"], deadline=deadline)
            for period in contract["plan"]["periods"]:
                days, bounds = contract["plan"]["days"], period["bounds"]
                managed = targets(rows, days, bounds, ref)
                actions = dict(
                    vol_managed=managed,
                    train_risk_matched=dict.fromkeys(managed, constant or Decimal(0)),
                    always_long=dict.fromkeys(managed, Decimal(1)),
                    cash=dict.fromkeys(managed, Decimal(0)),
                )
                missing, invalid = gaps(rows, days, bounds)
                available = not (missing or invalid) and constant is not None
                group = dict(
                    symbol=symbol,
                    period=period["period"],
                    sessions=bounds[1] - bounds[0],
                    months=len(managed),
                    missing=missing,
                    invalid=invalid,
                    train=training,
                    status="evaluated" if available else "input_unavailable",
                    benchmark_growth=number(
                        rows[days[bounds[1] - 1]].adj_close / rows[days[bounds[0]]].adj_open
                    )
                    if available
                    else None,
                    cohort_sha256=digest(encode(days[max(0, bounds[0] - 23) : bounds[1]])),
                )
                groups.append(group)
                for cost in COSTS:
                    batch = []
                    for policy in POLICIES:
                        path = [(days[i], str(w.normalize())) for i, w in actions[policy].items()]
                        cell = dict(
                            symbol=symbol,
                            period=period["period"],
                            cost_per_side_bps=cost,
                            policy=policy,
                            status=group["status"],
                            trades=None,
                            action_sha256=digest(encode(path)) if constant is not None else None,
                            **dict.fromkeys(METRICS),
                        )
                        if available:
                            scored = replay(
                                rows, days, bounds, actions[policy], cost, deadline=deadline
                            )
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
    status = "complete" if all(g["status"] == "evaluated" for g in groups) else "input_unavailable"
    result.update(
        status=status, criterion="descriptive_only_no_selection", groups=groups, cells=cells
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
    training = {}
    for g in result["groups"]:
        counts = ("sessions", "months", "missing", "invalid")
        require(
            set(g)
            == set(counts)
            | {"symbol", "period", "train", "status", "benchmark_growth", "cohort_sha256"},
            "group_fields",
        )
        bounds = next(
            p["bounds"] for p in contract["plan"]["periods"] if p["period"] == g["period"]
        )
        require(
            all(type(g[k]) is int and g[k] >= 0 for k in counts)
            and g["sessions"] == bounds[1] - bounds[0]
            and g["months"] == len(month_indices(contract["plan"]["days"], bounds))
            and g["missing"] + g["invalid"] <= bounds[1] - max(0, bounds[0] - 23),
            "group_counts",
        )
        t = g["train"]
        require(
            set(t)
            == {
                "sessions",
                "warm_sessions",
                "positive_variances",
                "missing",
                "invalid",
                "calibration_sha256",
            },
            "train_fields",
        )
        b = contract["plan"]["train"]
        require(
            all(type(t[k]) is int and t[k] >= 0 for k in t if k != "calibration_sha256")
            and t["sessions"] == b[1] - b[0]
            and t["positive_variances"] <= t["warm_sessions"] <= t["sessions"]
            and t["missing"] + t["invalid"] <= b[1] - max(0, b[0] - 23),
            "train_counts",
        )
        require(training.setdefault(g["symbol"], t) == t, "TRAIN_recalibration")
        require(
            t["calibration_sha256"] is None
            or (
                t["positive_variances"] > 0
                and t["warm_sessions"] >= 2
                and t["missing"] == t["invalid"] == 0
                and re.fullmatch(HASH, t["calibration_sha256"])
            ),
            "calibration_hash",
        )
        available = t["calibration_sha256"] is not None and g["missing"] == g["invalid"] == 0
        require(
            g["status"] == ("evaluated" if available else "input_unavailable")
            and re.fullmatch(HASH, g["cohort_sha256"]),
            "group_status",
        )
        require(
            g["benchmark_growth"] is None
            if not available
            else type(g["benchmark_growth"]) is str
            and Decimal(g["benchmark_growth"]).is_finite()
            and Decimal(g["benchmark_growth"]) > 0,
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
    for c in cells:
        require(
            set(c)
            == {
                "symbol",
                "period",
                "cost_per_side_bps",
                "policy",
                "status",
                "trades",
                "action_sha256",
            }
            | set(METRICS),
            "cell_fields",
        )
        g = result["groups"][keys.index((c["symbol"], c["period"]))]
        require(c["status"] == g["status"], "cell_status")
        require(
            c["action_sha256"] is None
            if g["train"]["calibration_sha256"] is None
            else re.fullmatch(HASH, c["action_sha256"]),
            "action_hash",
        )
        key = c["symbol"], c["period"], c["policy"]
        require(
            paths.setdefault(key, c["action_sha256"]) == c["action_sha256"], "cost_changes_targets"
        )
        if c["status"] == "input_unavailable":
            require(
                c["trades"] is None and all(c[k] is None for k in METRICS), "unavailable_metrics"
            )
            continue
        for k in METRICS:
            require(
                type(c[k]) is str
                and len(c[k]) <= 80
                and Decimal(c[k]).is_finite()
                and c[k] == number(Decimal(c[k])),
                "metric_numeric",
            )
        nav, dd, std, fees, turnover = [Decimal(c[k]) for k in METRICS[:5]]
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
        tol = Decimal("3e-11") * (1 + nav + fees + turnover)
        require(
            abs(fees - Decimal(c["cost_per_side_bps"]) * turnover / 10000) <= tol, "fee_identity"
        )
        require(nav <= prior_nav.get(key, nav) + tol, "cost_NAV_monotonicity")
        prior_nav[key] = nav
        if c["policy"] == "cash":
            require(nav == 1 and dd == std == fees == turnover == c["trades"] == 0, "cash_identity")
        if c["policy"] == "always_long":
            growth, f = Decimal(g["benchmark_growth"]), Decimal(c["cost_per_side_bps"]) / 10000
            require(
                c["trades"] == 2
                and abs(nav - growth * (1 - f) / (1 + f)) <= tol
                and abs(turnover - (1 + growth) / (1 + f)) <= tol,
                "long_endpoints",
            )
        batch = [
            x
            for x in cells
            if (x["symbol"], x["period"], x["cost_per_side_bps"])
            == (c["symbol"], c["period"], c["cost_per_side_bps"])
        ]
        for field, control in zip(METRICS[5:], batch[1:3], strict=True):
            require(
                abs(nav - Decimal(control["final_nav"]) - Decimal(c[field])) <= tol,
                "paired_difference",
            )


def load_adjusted(snapshot_dir, market_data_root):
    # Import only at worker execution, once the independently owned Data module exists.
    module = importlib.import_module(DATA_MODULE)
    return module.load_verified_adjusted_etf_snapshot(
        snapshot_dir, market_data_root=market_data_root, repo_root=REPO
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
