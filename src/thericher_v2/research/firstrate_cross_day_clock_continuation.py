"""One bounded, seen-data same-clock study; actual dispatch belongs to the parent."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

NAME = "firstrate-cross-day-clock-continuation-development-v1"
SYMBOLS = ("QQQ", "SPY")
CLOCKS = (10, 12, 14)
COSTS = (Decimal(1), Decimal("2.5"), Decimal(5))
POLICIES = ("same_clock", "pooled", "long", "cash", "same_clock_matched", "pooled_matched")
THRESHOLD = Decimal(10)
TOL = Decimal("1e-10")
MINUTE = timedelta(minutes=1)
EASTERN = ZoneInfo("America/New_York")
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
REPO = Path(__file__).resolve().parents[3]
SOURCES = {
    "QQQ": "sha256:27a6f601d41b7a96d38db663cc63c821471d511bbb196a88021acf81b8d92c3c",
    "SPY": "sha256:db797f4355dc3cd82113730e1689ee0750226b16568687d86b6ca3e407053777",
}
DATE_HASH = "sha256:adcb51614f5ea08ddf02773444be6833d997861aeb700260d05f229febdd05e3"
CODE = (
    "src/thericher_v2/research/firstrate_cross_day_clock_continuation.py",
    "src/thericher_v2/research/cross_day_clock_context.py",
    "src/thericher_v2/research/clock_portfolio_nav.py",
    "src/thericher_v2/research/three_asset_nav.py",
    "scripts/run_firstrate_forward_variance_baseline.py",
    "scripts/run_firstrate_forward_variance_smoke.py",
    "src/thericher_v2/data/firstrate_free_intraday_timeframe_mechanics.py",
    "src/thericher_v2/data/local.py",
    "src/thericher_v2/data/provider.py",
    "src/thericher_v2/contracts.py",
    "src/thericher_v2/market/resample.py",
    "src/thericher_v2/execution/local_paper.py",
    "src/thericher_v2/execution/emergency.py",
    "src/thericher_v2/state/__init__.py",
    "src/thericher_v2/state/event_log.py",
    "src/thericher_v2/research/validation.py",
    "src/thericher_v2/research/campaign_registry.py",
)


class ClockFault(ValueError):
    """Categorical faults only; no source values or exception bodies."""


def require(ok, reason):
    if not ok:
        raise ClockFault(reason)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def contract(pins):
    return {
        "study": NAME,
        "grade": "revised_seen_development_only",
        "sources": SOURCES,
        "scheduled_dates_sha256": DATE_HASH,
        "calendar": "pandas-market-calendars==5.4.0 NYSE",
        "mechanism_reference": {
            "url": "https://arxiv.org/abs/1005.3535",
            "authors": "Heston/Korajczyk/Sadka",
            "submitted": "2010-05-19",
            "scope": "abstract cross-sectional stock half-hour continuation at exact day "
            "multiples for at least40days; inspiration only, not a20day/3clock/twoETF replication",
            "adopted_code_or_weights": False,
        },
        "split": {"TRAIN": 160, "embargo": 1, "comparison": 90, "halves": [45, 45]},
        "clocks_eastern": list(CLOCKS),
        "history": "exact20 prior scheduled NYSE sessions; own ETF all three clocks; "
        "common past-only eligibility for all six policies; no older-date replacement",
        "return": "10000*(OPEN(C+31min)/OPEN(C+1min)-1); mean signed return",
        "pooled": "same ETF/same20 dates/all three clocks; no current-day or peer pooling",
        "early_close": "current nonexistent clocks unscheduled; a required nonexistent "
        "historical clock makes its common past input unavailable, never zero",
        "rule": "strict mean>10bps; same actions at all costs; equality flat",
        "policies": list(POLICIES),
        "matching": "TRAIN input-eligible active fraction per policy/ETF/clock; "
        "Decimal50 HALF_EVEN; no labels/beta/profit/search; empty denominator unresolved",
        "weights": "QQQ/SPY each 0 or0.5; matched each 0.5*TRAIN fraction; "
        "other allocation stays cash; never renormalize",
        "ledger": "one shared continuous cash account; fractions of post-entry-fee NAV; "
        "simultaneous endpoint OPEN analytical fill projection through local_paper accounting; "
        "Decimal50 HALF_EVEN; quantity ROUND_DOWN1e-40; unquantized "
        "actual notional entry/exit fees; not LocalPaperBroker0.0001 rounding or broker parity",
        "reconciliation": "1e-45*(before NAV+after NAV) for shared slot/day/path cashflows; "
        "ETF attribution is descriptive, not an independently funded sleeve",
        "missing": "past unavailable => scoped flat across controls; future support never "
        "changes actions; a missing required payoff makes its evaluation path unavailable; "
        "no dropped days or zero loss imputation",
        "cost_bps_side": [str(cost) for cost in COSTS],
        "matrix": {"policies": 6, "costs": 3, "paths": ["continuous90", "first45", "last45"],
                   "cells": 54, "effective_samples": "90 shared dates, not ETF/slot IID rows"},
        "utility": "252*(mean daily log growth-5*population daily log variance); "
        "all scheduled flat days included; half metrics from continuous90 daily path",
        "kill": "primary5bps same-clock positive shared net growth and utility increment "
        "over cash/pooled/own TRAIN activity-matched in BOTH45 halves; tolerance1e-10; "
        "zero trades fails; ETF attribution descriptive, no ETF/clock/cost rescue",
        "compute": {"seconds": 120, "cpu": 2, "memory_bytes": 2 * 1024**3,
                    "network": "none", "source": "read_only", "image": IMAGE},
        "stop": "one exclusive immutable attempt; categorical exception terminal where possible; "
        "parent owns exact hard-timeout receipt, absent result is unknown; no automatic retry",
        "runtime": {"python": "3.12.14", "numpy": "2.5.1", "pandas-market-calendars": "5.4.0"},
        "actual_fits": 0,
        "action_commitment": "immutable fsync before comparison marks/payoffs; source "
        "physical parsing is not target-isolated",
        "gpu": False,
        "holdout": False,
        "paper_input": False,
        "broker_calls": 0,
        "artifact_root": "D:/thericher-v2/model-artifacts/research/" + NAME,
        "limitations": ["revised/seen source; no independent replication",
                        "timestamps/actions/finality/as-of remain assumptions",
                        "execution-open analytical sizing not causal broker quantity proof",
                        "critical source pins, not a full transitive runtime lock"],
        "code_sha256": pins,
    }


@dataclass(frozen=True, slots=True)
class ClockDecision:
    session_date: date
    symbol: str
    clock: int
    decision_at: datetime
    entry_at: datetime
    exit_at: datetime
    eligible: bool
    same_clock_bps: Decimal | None = field(default=None, repr=False)
    pooled_bps: Decimal | None = field(default=None, repr=False)

    def __post_init__(self):
        require(type(self.session_date) is date and self.symbol in SYMBOLS
                and type(self.clock) is int and self.clock in CLOCKS
                and type(self.eligible) is bool, "decision_identity")
        require(all(isinstance(at, datetime) and at.utcoffset() == timedelta(0)
                    for at in (self.decision_at, self.entry_at, self.exit_at))
                and self.entry_at == self.decision_at + MINUTE
                and self.exit_at == self.entry_at + 30 * MINUTE, "decision_geometry")
        local = self.decision_at.astimezone(EASTERN)
        require(local.date() == self.session_date and local.hour == self.clock
                and not (local.minute or local.second or local.microsecond), "decision_clock")
        values = (self.same_clock_bps, self.pooled_bps)
        require(all(isinstance(v, Decimal) and v.is_finite() for v in values)
                if self.eligible else all(v is None for v in values), "decision_features")


@dataclass(frozen=True, slots=True)
class TrainActivity:
    fractions: Mapping[tuple[str, str, int], Decimal | None] = field(repr=False)
    counts: Mapping[tuple[str, str, int], tuple[int, int]] = field(repr=False)


def validate_dates(dates):
    require(len(dates) == 251 and all(type(d) is date for d in dates)
            and all(a < b for a, b in zip(dates, dates[1:], strict=False)), "scheduled_dates")


def freeze_train_activity(decisions: Sequence[ClockDecision], dates) -> TrainActivity:
    from types import MappingProxyType

    validate_dates(dates)
    require(len({(r.session_date, r.symbol, r.clock) for r in decisions}) == len(decisions)
            and all(r.session_date in dates for r in decisions), "decision_keys")
    training = set(dates[:160])
    fractions, counts = {}, {}
    with localcontext() as context:
        context.prec, context.rounding = 50, ROUND_HALF_EVEN
        for policy in ("same_clock", "pooled"):
            for symbol in SYMBOLS:
                for clock in CLOCKS:
                    rows = [r for r in decisions if r.session_date in training
                            and r.symbol == symbol and r.clock == clock and r.eligible]
                    selected = sum((r.same_clock_bps if policy == "same_clock" else r.pooled_bps)
                                   > THRESHOLD for r in rows)
                    key = policy, symbol, clock
                    counts[key] = selected, len(rows)
                    fractions[key] = Decimal(selected) / len(rows) if rows else None
    return TrainActivity(MappingProxyType(fractions), MappingProxyType(counts))


def prepare_decisions(sessions, grouped, *, deadline=float("inf")):
    from thericher_v2.research.cross_day_clock_context import (
        ClockSession,
        CrossDayClockInputUnavailable,
        build_cross_day_clock_context,
    )

    dates = tuple(s.open_ts.astimezone(EASTERN).date() for s in sessions)
    validate_dates(dates)
    calendar = tuple(ClockSession(day, s.open_ts, s.close_ts)
                     for day, s in zip(dates, sessions, strict=True))
    # Endpoint selection is calendar-only. Keep duplicates for the Data reader
    # to reject; never test a whole current/future session for input eligibility.
    endpoints = {}
    for symbol in SYMBOLS:
        endpoints[symbol] = {}
        for session in calendar:
            keys = {datetime.combine(session.session_date, clock_time(clock), EASTERN)
                    .astimezone(UTC) + offset * MINUTE
                    for clock in CLOCKS for offset in (1, 31)}
            endpoints[symbol][session.session_date] = tuple(
                bar for bar in grouped[symbol].get(session.session_date, ())
                if bar.start_ts in keys)
    decisions, reasons = [], Counter()
    for index, session in enumerate(calendar):
        require(time.monotonic() < deadline, "compute_stop")
        scheduled = []
        for clock in CLOCKS:
            at = datetime.combine(session.session_date, clock_time(clock), EASTERN).astimezone(UTC)
            if session.open_ts <= at and at + 32 * MINUTE <= session.close_ts:
                scheduled.append((clock, at))
        for symbol in SYMBOLS:
            context = None
            if index < 20:
                reasons["history_boundary_shortfall"] += len(scheduled)
            elif scheduled:
                prior = calendar[index - 20:index]
                bars = tuple(bar for past in prior
                             for bar in endpoints[symbol][past.session_date])
                try:
                    context = build_cross_day_clock_context(
                        bars, symbol=symbol, scheduled_sessions=prior, decision_at=scheduled[0][1])
                except CrossDayClockInputUnavailable as error:
                    reasons[error.reason_code] += len(scheduled)
            for clock, at in scheduled:
                decisions.append(ClockDecision(
                    session.session_date, symbol, clock, at, at + MINUTE, at + 31 * MINUTE,
                    context is not None,
                    None if context is None else context.mean_return_bps_by_clock[f"{clock}:00"],
                    None if context is None else context.pooled_mean_return_bps))
    return tuple(decisions), dict(sorted(reasons.items()))


def target_fraction(row: ClockDecision, policy: str, activity: TrainActivity) -> Decimal | None:
    require(policy in POLICIES, "policy")
    if not row.eligible or policy == "cash":
        return Decimal(0)
    if policy == "long":
        return Decimal("0.5")
    if policy.endswith("_matched"):
        fraction = activity.fractions[policy.removesuffix("_matched"), row.symbol, row.clock]
        with localcontext() as context:
            context.prec, context.rounding = 50, ROUND_HALF_EVEN
            return None if fraction is None else Decimal("0.5") * fraction
    value = row.same_clock_bps if policy == "same_clock" else row.pooled_bps
    return Decimal("0.5") if value > THRESHOLD else Decimal(0)


def decision_commitment(decisions, activity):
    return digest(encode([
        [r.session_date.isoformat(), r.symbol, r.clock, r.decision_at.isoformat(), r.eligible,
         None if r.same_clock_bps is None else str(r.same_clock_bps),
         None if r.pooled_bps is None else str(r.pooled_bps),
         [None if (w := target_fraction(r, policy, activity)) is None else str(w)
          for policy in POLICIES]]
        for r in decisions
    ]))


def daily_metrics(navs: Sequence[Decimal], *, initial_nav: Decimal):
    require(navs and isinstance(initial_nav, Decimal) and initial_nav.is_finite()
            and initial_nav > 0 and all(isinstance(n, Decimal) and n.is_finite() and n > 0
                                      for n in navs), "daily_nav")
    with localcontext() as context:
        context.prec, context.rounding = 50, ROUND_HALF_EVEN
        previous, logs = initial_nav, []
        for nav in navs:
            logs.append((nav / previous).ln())
            previous = nav
        mean = sum(logs, Decimal(0)) / len(logs)
        variance = sum(((v - mean) ** 2 for v in logs), Decimal(0)) / len(logs)
        return {"net_growth": navs[-1] / initial_nav - 1,
                "utility": Decimal(252) * (mean - 5 * variance)}


def primary_kill(metrics):
    """The two predeclared halves, not a best-cost/ETF/clock selection."""
    for half in ("first45", "last45"):
        candidate = metrics.get(("same_clock", "5", half))
        controls = [metrics.get((p, "5", half)) for p in ("cash", "pooled", "same_clock_matched")]
        if candidate is None or any(control is None for control in controls):
            return "input_unavailable"
        if (candidate["net_growth"] <= TOL or candidate["trades"] == 0
                or any(candidate["utility"] - control["utility"] <= TOL for control in controls)):
            return "rejected"
    return "development_criterion_met"


def source_helpers():
    scripts = str(REPO / "scripts")
    sys.path.insert(0, scripts)
    try:
        return (importlib.import_module("run_firstrate_forward_variance_smoke"),
                importlib.import_module("run_firstrate_forward_variance_baseline"))
    finally:
        sys.path.remove(scripts)


def check_runtime(plan):
    require(platform.python_version() == plan["runtime"]["python"], "python_version")
    for name in ("numpy", "pandas-market-calendars"):
        require(importlib.metadata.version(name) == plan["runtime"][name], "dependency_version")


def check_pins(plan, market, lineage, normalization):
    require(set(plan["code_sha256"]) == set(CODE)
            and plan == contract(plan["code_sha256"]), "contract_changed")
    smoke, _ = source_helpers()
    specs = smoke.check_metadata(lineage, normalization)
    require(smoke.SOURCES == SOURCES and smoke.DATE_HASH == DATE_HASH, "source_constants")
    require(len(specs) == 2 and {s.symbol for s in specs} == set(SYMBOLS), "source_symbols")
    for relative, expected in plan["code_sha256"].items():
        require(file_hash(REPO / relative) == expected, "code_changed")
    for spec in specs:
        path = market / spec.canonical_market_data_relative_path
        require(not path.is_symlink() and path.stat().st_size <= 134217728, "source_path")
        require(file_hash(path) == SOURCES[spec.symbol], "source_changed")
    return specs


def register(plan, root, artifact_base):
    from thericher_v2.research.campaign_registry import register_frozen_campaign

    return register_frozen_campaign(
        contract_hash=file_hash(root / "contract.json"), dataset_hash=digest(encode(SOURCES)),
        split_hash=digest(encode([DATE_HASH, plan["split"], CLOCKS])),
        cost_model_hash=digest(encode([plan["ledger"], plan["cost_bps_side"]])),
        trial_family=NAME, holdout_access="none", artifact_root=artifact_base, repo_root=REPO)


def freeze(root, market, lineage, normalization, artifact_base):
    plan = contract({relative: file_hash(REPO / relative) for relative in CODE})
    check_pins(plan, market, lineage, normalization)
    if root.exists():
        require((root / "contract.json").read_bytes() == encode(plan) + b"\n", "contract_changed")
    else:
        root.mkdir(parents=True, exist_ok=False)
        write_once(root / "contract.json", plan)
    register(plan, root, artifact_base)
    return {"status": "frozen", "contract_sha256": file_hash(root / "contract.json")}


def opportunities(decisions, grouped, comparison_dates):
    from thericher_v2.contracts import Bar, Timeframe
    from thericher_v2.research.clock_portfolio_nav import ClockOpportunity

    pairs = {}
    for row in decisions:
        if row.session_date in comparison_dates:
            pairs.setdefault(row.entry_at, {})[row.symbol] = row
    result, shortfalls = [], Counter()
    for entry, pair in sorted(pairs.items()):
        require(set(pair) == set(SYMBOLS), "paired_decision_missing")
        if not any(row.eligible for row in pair.values()):
            continue
        representative = pair[SYMBOLS[0]]
        opened, exited, valid = {}, {}, True
        for symbol in SYMBOLS:
            rows = grouped[symbol].get(representative.session_date, ())
            for at, dest in ((entry, opened), (representative.exit_at, exited)):
                selected = tuple(bar for bar in rows if bar.start_ts == at)
                if (len(selected) != 1 or not isinstance(selected[0], Bar)
                        or selected[0].symbol != symbol or selected[0].market != "US"
                        or selected[0].timeframe is not Timeframe.M1
                        or selected[0].complete is not True
                        or not selected[0].open.is_finite() or selected[0].open <= 0):
                    valid = False
                    shortfalls["required_forward_endpoint"] += 1
                else:
                    dest[symbol] = selected[0].open
        if valid:
            result.append(ClockOpportunity.from_mapping(
                representative.session_date, entry, representative.exit_at, opened, exited))
    # No incomplete account path is ever replayed with a missing loss-day.
    return tuple(result), dict(shortfalls)


def summarize_replay(replay, half):
    selected = {"continuous90": replay.daily, "first45": replay.daily[:45],
                "last45": replay.daily[45:]}[half]
    initial = Decimal(1) if half != "last45" else replay.daily[44].nav
    metrics = daily_metrics(tuple(day.nav for day in selected), initial_nav=initial)
    selected_dates = {day.date for day in selected}
    slots = tuple(slot for slot in replay.slots if slot.entry_at.date() in selected_dates)
    with localcontext() as context:
        context.prec, context.rounding = 50, ROUND_HALF_EVEN
        flows = {symbol: {name: sum((getattr(f, name) for day in selected
                                    for f in day.asset_cashflows if f.symbol == symbol), Decimal(0))
                          for name in ("gross_pnl", "entry_fee", "exit_fee", "net_pnl")}
                 for symbol in SYMBOLS}
        require(abs(sum((f["net_pnl"] for f in flows.values()), Decimal(0))
                    - (selected[-1].nav - initial)) <= TOL, "cashflow_attribution")
        metrics.update(
            trades=sum(fill.side == "buy" for slot in slots for fill in slot.fills),
            fees=sum((day.fees for day in selected), Decimal(0)),
            traded_notional=sum((day.traded_notional for day in selected), Decimal(0)),
            daily_count=len(selected), asset_cashflow=flows)
    return metrics


def evaluate(decisions, activity, ops, dates, *, deadline=float("inf")):
    from thericher_v2.research.clock_portfolio_nav import ClockTarget, replay

    lookup = {(r.entry_at, r.symbol): r for r in decisions}
    metrics, paths = {}, {}
    for policy in POLICIES:
        targets = {}
        for opportunity in ops:
            weights = tuple(target_fraction(lookup[opportunity.entry_at, symbol], policy, activity)
                            for symbol in SYMBOLS)
            if any(weight is None for weight in weights):
                break
            targets[opportunity.entry_at] = ClockTarget(weights)
        else:
            for cost in COSTS:
                require(time.monotonic() < deadline, "compute_stop")
                result = replay(ops, targets, cost, session_dates=dates)
                require(tuple(day.date for day in result.daily) == tuple(dates)
                        and all(day.flat for day in result.daily), "daily_ledger_dates")
                paths[policy, str(cost)] = digest(encode([
                    [day.date.isoformat(), str(day.nav), str(day.fees), str(day.traded_notional)]
                    for day in result.daily]))
                for half in ("continuous90", "first45", "last45"):
                    metrics[policy, str(cost), half] = summarize_replay(result, half)
    return metrics, paths


def json_numbers(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_numbers(v) for key, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_numbers(v) for v in value]
    return value


def compute(plan, market, lineage, normalization, *, deadline, seal, phase=lambda value: None):
    phase("source_input")
    check_runtime(plan)
    specs = check_pins(plan, market, lineage, normalization)
    _, source = source_helpers()
    sessions, grouped = source.load_source_cases(specs, market, deadline)
    dates = tuple(s.open_ts.astimezone(EASTERN).date() for s in sessions)
    phase("decisions")
    rows, reasons = prepare_decisions(sessions, grouped, deadline=deadline)
    activity = freeze_train_activity(rows, dates)
    action_hash = decision_commitment(rows, activity)
    commitment = {"actions_sha256": action_hash,
                  "TRAIN_counts": [[p, s, c, *activity.counts[p, s, c]]
                                   for p in ("same_clock", "pooled")
                                   for s in SYMBOLS for c in CLOCKS]}
    seal(commitment)
    phase("evaluate")
    ops, missing = opportunities(rows, grouped, dates[161:])
    metrics, paths = ({}, {}) if missing else evaluate(
        rows, activity, ops, dates[161:], deadline=deadline)
    phase("validate")
    check_pins(plan, market, lineage, normalization)
    require(time.monotonic() < deadline, "compute_stop")
    return {
        "status": "non_promoting_completed", "study": NAME,
        "classification": primary_kill(metrics), "cells": len(metrics),
        "input_counts": {"scheduled": len(rows), "eligible": sum(r.eligible for r in rows),
                         "comparison": sum(r.session_date in dates[161:] for r in rows)},
        "input_unavailable": reasons, "future_unavailable": missing,
        "commitment": commitment,
        "metrics": [{"policy": p, "cost_bps": c, "period": h, **json_numbers(v)}
                    for (p, c, h), v in metrics.items()],
        "daily_path_sha256": [[p, c, pin] for (p, c), pin in paths.items()],
        "actual_fits": 0, "gpu": False, "broker_calls": 0, "holdout": False,
        "paper_input": False, "raw_market_rows_retained": False,
    }


def write_once(path, value):
    raw = encode(value) + b"\n"
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def append_outcome(root, artifact_base, contract_pin, result):
    from thericher_v2.research.campaign_registry import register_campaign_outcome

    require(result["status"] in ("non_promoting_completed", "non_promoting_failed"),
            "result_status")
    return register_campaign_outcome(
        contract_hash=contract_pin, outcome_class=result["status"],
        outcome_reference_sha256=file_hash(root / "result.json"),
        artifact_root=artifact_base, repo_root=REPO)


def failure_result(phase, error, contract_pin):
    allowlisted = {"compute_stop", "code_changed", "source_changed", "contract_changed",
                  "actions_changed", "scheduled_dates", "paired_decision_missing",
                  "daily_ledger_dates", "daily_nav", "cashflow_attribution",
                  "python_version", "dependency_version", "decision_features", "decision_keys"}
    reason = (str(error) if isinstance(error, ClockFault) and str(error) in allowlisted
              else "runtime_or_source_fault")
    return {"status": "non_promoting_failed", "classification": "failed", "study": NAME,
            "phase": phase, "reason": reason, "raw_error_suppressed": True,
            "contract_sha256": contract_pin, "cells": 0, "actual_fits": 0, "gpu": False,
            "broker_calls": 0, "paper_input": False}


def synthetic_smoke():
    from thericher_v2.contracts import Bar, Timeframe
    from thericher_v2.research.clock_portfolio_nav import ClockOpportunity
    from thericher_v2.research.cross_day_clock_context import (
        ClockSession,
        build_cross_day_clock_context,
    )

    dates = tuple(date(2022, 1, 1) + timedelta(days=i) for i in range(251))
    history = tuple(ClockSession(
        day, datetime.combine(day, clock_time(9, 30), EASTERN).astimezone(UTC),
        datetime.combine(day, clock_time(16), EASTERN).astimezone(UTC)) for day in dates[:20])
    training, later = [], []
    for symbol in SYMBOLS:
        bars = []
        for session in history:
            for clock in CLOCKS:
                at = datetime.combine(
                    session.session_date, clock_time(clock), EASTERN).astimezone(UTC)
                for offset, price in ((1, Decimal(100)), (31, Decimal("100.2"))):
                    bars.append(Bar(symbol=symbol, market="US", timeframe=Timeframe.M1,
                                    start_ts=at + offset * MINUTE, open=price, high=price,
                                    low=price, close=price, volume=Decimal(0), complete=True))
        context = build_cross_day_clock_context(
            bars, symbol=symbol, scheduled_sessions=history,
            decision_at=datetime.combine(dates[20], clock_time(10), EASTERN).astimezone(UTC))
        for clock in CLOCKS:
            for day, destination in ((dates[20], training), (dates[161], later)):
                at = datetime.combine(day, clock_time(clock), EASTERN).astimezone(UTC)
                destination.append(ClockDecision(
                    day, symbol, clock, at, at + MINUTE, at + 31 * MINUTE, True,
                    context.mean_return_bps_by_clock[f"{clock}:00"],
                    context.pooled_mean_return_bps))
    activity = freeze_train_activity(training, dates)
    first = later[0]
    opportunity = ClockOpportunity(first.session_date, first.entry_at, first.exit_at,
                                   (Decimal(100), Decimal(100)),
                                   (Decimal("100.2"), Decimal("100.2")))
    metrics, paths = evaluate(later, activity, (opportunity,), dates[161:])
    require(len(metrics) == 54 and len(paths) == 18
            and primary_kill(metrics) == "rejected", "synthetic_smoke")
    return {"status": "synthetic_cpu_smoke_passed", "synthetic_cells": 54,
            "actual_fits": 0, "actual_source_reads": 0, "registry_writes": 0, "gpu": False}


def check_scope(root):
    expected = Path("D:/thericher-v2/model-artifacts/research") / NAME
    require(root.resolve() == (expected.resolve() if os.name == "nt" else Path("/study")),
            "artifact_scope")
    require(not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                    for p in (root, *root.parents)), "artifact_link")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?",
                        choices=("plan", "smoke", "freeze", "run", "verify", "recover-registry"),
                        default="plan")
    for name in ("artifact-root", "artifact-base", "market-root", "lineage", "normalization"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(json.dumps({"status": "plan", "study": NAME, "actual_fits": 0,
                          "gpu": False, "broker_calls": 0}))
        return 0
    if args.mode == "smoke":
        try:
            print(json.dumps(synthetic_smoke(), sort_keys=True))
            return 0
        except Exception:
            print(json.dumps({"status": "failed", "phase": "synthetic_smoke",
                              "reason": "invariant_or_runtime_failure",
                              "raw_error_suppressed": True}))
            return 1
    phase = "contract"
    started = time.monotonic()
    root = args.artifact_root
    attempt_owned = False
    try:
        require(all(p is not None for p in (root, args.artifact_base, args.market_root,
                                            args.lineage, args.normalization)), "explicit_paths")
        check_scope(root)
        if args.mode == "freeze":
            result = freeze(
                root, args.market_root, args.lineage, args.normalization, args.artifact_base)
        else:
            raw = (root / "contract.json").read_bytes()
            require(digest(raw) == args.contract_sha256, "exact_contract_pin")
            plan = json.loads(raw)
            check_pins(plan, args.market_root, args.lineage, args.normalization)
            if args.mode == "run":
                require(not (root / "result.json").exists(), "result_already_exists")
                write_once(root / "attempt.json", {"started_at": datetime.now(UTC).isoformat(),
                                                   "contract_sha256": args.contract_sha256})
                attempt_owned = True
                register(plan, root, args.artifact_base)

            def stage(value):
                nonlocal phase
                phase = value

            def seal(commitment):
                if args.mode == "run":
                    write_once(root / "actions.json", commitment)
                else:
                    require((root / "actions.json").read_bytes() == encode(commitment) + b"\n",
                            "actions_changed")

            if args.mode in ("verify", "recover-registry"):
                result_raw = (root / "result.json").read_bytes()
                require(digest(result_raw) == args.result_sha256, "exact_result_pin")
                expected_result = json.loads(result_raw)
            if args.mode != "run" and expected_result.get("status") == "non_promoting_failed":
                require(expected_result["contract_sha256"] == args.contract_sha256
                        and expected_result["actual_fits"] == 0 and not expected_result["gpu"],
                        "failure_binding")
                result = expected_result
            else:
                result = compute(plan, args.market_root, args.lineage, args.normalization,
                                 deadline=started + 120, seal=seal, phase=stage)
                result["contract_sha256"] = args.contract_sha256
                if args.mode == "run":
                    write_once(root / "result.json", result)
                else:
                    require(result == expected_result, "readback_changed")
            if args.mode != "verify":
                phase = "registry"
                append_outcome(root, args.artifact_base, args.contract_sha256, result)
            result = {"status": "verified_all_ro" if args.mode == "verify" else "completed",
                      "classification": result["classification"], "cells": result["cells"],
                      "result_sha256": file_hash(root / "result.json"), "actual_fits": 0,
                      "gpu": False, "broker_calls": 0}
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        failure = failure_result(phase, error, args.contract_sha256)
        if attempt_owned and not (root / "result.json").exists():
            try:
                write_once(root / "result.json", failure)
                append_outcome(root, args.artifact_base, args.contract_sha256, failure)
            except Exception:
                pass
        print(json.dumps(failure))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
