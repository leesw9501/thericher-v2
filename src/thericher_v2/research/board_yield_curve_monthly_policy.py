"""Fixed Board-direct, revised-data monthly basket/cash development study.

No prediction fitting, parameter selection or Paper qualification. Numeric
inputs and replay paths remain private; only categorical facts reach stdout.
"""

from __future__ import annotations

import importlib.metadata
import itertools
import json
import platform
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

from thericher_v2.contracts import require_utc
from thericher_v2.data import federal_reserve_h15 as board
from thericher_v2.data import tiingo_adjusted_etf_daily as etf
from thericher_v2.research import tiingo_month_start_development as common
from thericher_v2.research import tiingo_quarterly_joint_allocation as base
from thericher_v2.research.artifact_paths import (
    ensure_external_artifact_directory,
    reject_repo_artifact_path,
)
from thericher_v2.research.campaign_registry import register_campaign_outcome

NAME = "board-yield-curve-monthly-policy-development-v1"
REPO, SYMBOLS = base.REPO, base.SYMBOLS
TRAIN, PERIODS = base.TRAIN, base.PERIODS
COSTS = ("2.5", "5", "10")
POLICIES = ("yield_curve", "cash", "equal_weight", "train_activity_matched")
SECONDS, MEMORY_BYTES = 120, 2 * 1024**3
TOL, QUANTUM = Decimal("1e-10"), Decimal("1e-45")
CPU_IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
CODE = tuple(dict.fromkeys((
    *base.CODE, "src/thericher_v2/data/federal_reserve_h15.py",
    "src/thericher_v2/research/board_yield_curve_monthly_policy.py",
    "scripts/run_board_yield_curve_monthly_policy.py",
)))
encode, digest, require, atomic_new = base.encode, base.digest, base.require, base.atomic_new


def configuration() -> dict:
    """Source-free static API/contract; no file, calendar or runtime inspection."""
    return dict(
        name=NAME,
        symbols=list(SYMBOLS),
        train=list(TRAIN),
        periods=[list(row) for row in PERIODS],
        policies=list(POLICIES),
        costs_per_side_bps=list(COSTS),
        cells=24,
        decision="previous_scheduled_NYSE_CLOSE_before_first_monthly_OPEN",
        rate_selection=dict(
            anchor_calendar_days=30, maximum_pair_age_days=7,
            same_observation_date=True, select_latest_before_value_validation=True,
            older_invalid_fallback=False, individual_maturity_carry=False,
            missing_codes_are_observations=False,
        ),
        rule="exposure_1_if_10Y_minus_2Y_strictly_positive_else_0",
        matching="TRAIN_scheduled_session_weighted_monthly_target_activity",
        missing_train="entire_matrix_input_unavailable_no_denominator_reduction",
        missing_comparison="affected_period_input_unavailable_no_dropped_days",
        action_commitment="all_macro_targets_sealed_before_comparative_mark_parse",
        failure_binding="worker_bytes_equal_or_reaped_dispatch_worker_hash_or_confirmed_absence",
        target="45dp_HALF_EVEN_equal_thirds_last_residual_and_exact_cash",
        ledger="shared_NAV1_overnight_postfee_OPEN_actual_notional_final_CLOSE_liquidation",
        utility="252*(mean_daily_log_NAV_return-5*population_variance)",
        strongest_kill="10bps_NAV_growth_and_utility_beat_all_3_controls_in_both_periods",
        improvement_tolerance=str(TOL),
        same_actions_at_all_costs=True,
        prior_families=[
            "joint-etf-quarterly-allocation-development-v1",
            "joint-d1-direct-utility-development-v1",
            "firstrate-cross-day-clock-continuation-development-v1",
        ],
        novelty="Board_direct_exogenous_macro_rule_not_price_model_recipe_rescue",
        predictive_fits=0, parameter_searches=0, gpu=False, holdout_access="none",
        resource=dict(
            image=CPU_IMAGE, python="3.12.14", numpy="2.5.1", calendar="5.4.0",
            cpu_limit=2, memory_bytes=MEMORY_BYTES, network="none",
            evaluation_seconds=SECONDS, readonly_replay_seconds=SECONDS,
        ),
        limitations=[
            "revised_non_PIT_Board_rates_and_Tiingo_adjusted_marks",
            "30_day_lag_is_assumption_not_publication_or_revision_proof",
            "seen_development_periods_surviving_correlated_ETF_universe",
            "cash_interest_zero_fractional_adjusted_analytical_proxy",
            "no_broker_fill_dividend_settlement_or_Paper_parity",
            "not_Engstrom_Sharpe_near_term_forward_spread_replication",
        ],
        inspiration={
            "url": "https://www.federalreserve.gov/econres/feds/"
                   "the-near-term-forward-yield-spread-as-a-leading-indicator-a-less-distorted-mirror.htm",
            "scope": "mechanism_challenge_only_not_stock_profit_evidence",
        },
    )


@dataclass(frozen=True)
class MonthlyDecision:
    index: int
    decision_at: datetime
    exposure: Decimal | None = field(repr=False)


@dataclass(frozen=True)
class TrainActivity:
    fraction: Decimal | None = field(repr=False)
    scheduled_sessions: int
    available_sessions: int


def build_plan(schedule: Sequence[Mapping]) -> dict:
    """Calendar geometry only; a schedule row contains date/open/close strings."""
    rows = [dict(row) for row in schedule]
    require(len(rows) > 1, "calendar_empty")
    days = [row["session_date"] for row in rows]
    require(days == sorted(set(days)), "calendar_order")
    for row in rows:
        day = date.fromisoformat(row["session_date"])
        opening, closing = (datetime.fromisoformat(row[key]) for key in ("open_at", "close_at"))
        require(
            opening.tzinfo is not None and closing.tzinfo is not None
            and opening.utcoffset() == closing.utcoffset() == timedelta(0)
            and opening < closing and opening.date() == closing.date() == day,
            "calendar_clocks",
        )
        row["open_at"], row["close_at"] = (
            require_utc(value).isoformat() for value in (opening, closing)
        )
    months = []
    for index, row in enumerate(rows):
        if index and days[index][:7] != days[index - 1][:7]:
            require(datetime.fromisoformat(rows[index - 1]["close_at"])
                    < datetime.fromisoformat(row["open_at"]), "decision_not_past")
            months.append(dict(index=index, decision_at=rows[index - 1]["close_at"]))
    periods = []
    for label, start, end in (("TRAIN", *TRAIN), *PERIODS):
        indices = [i for i, day in enumerate(days) if start <= day <= end]
        require(len(indices) > 1, "period_calendar_empty")
        bounds = [indices[0], indices[-1] + 1]
        entries = [item for item in months if bounds[0] <= item["index"] < bounds[1]]
        require(entries and entries[0]["index"] == bounds[0], "initial_month_missing")
        periods.append(dict(period=label, bounds=bounds, months=entries))
    return dict(schedule=[dict(row) for row in rows], days=days, periods=periods)


def prepare_decisions(plan: dict, slope_at: Callable[[datetime], Decimal | None]):
    """Adapter boundary: Data supplies its fixed same-date, lagged as-of slope."""
    result = []
    for period in plan["periods"]:
        for entry in period["months"]:
            at = datetime.fromisoformat(entry["decision_at"])
            slope = slope_at(at)
            require(slope is None or (type(slope) is Decimal and slope.is_finite()), "slope_domain")
            exposure = None if slope is None else Decimal(int(slope > 0))
            result.append(MonthlyDecision(entry["index"], at, exposure))
    return tuple(result)


def train_activity(plan: dict, decisions: Sequence[MonthlyDecision]) -> TrainActivity:
    training = plan["periods"][0]
    require(training["period"] == "TRAIN", "train_period")
    entries = training["months"]
    by_index = {item.index: item for item in decisions}
    require(len(by_index) == len(decisions), "duplicate_decision")
    available, active = 0, 0
    for j, entry in enumerate(entries):
        end = entries[j + 1]["index"] if j + 1 < len(entries) else training["bounds"][1]
        span = end - entry["index"]
        require(span > 0 and entry["index"] in by_index, "train_schedule")
        exposure = by_index[entry["index"]].exposure
        require(exposure in (None, Decimal(0), Decimal(1)), "train_target")
        if exposure is not None:
            available += span
            active += span * int(exposure)
    count = training["bounds"][1] - training["bounds"][0]
    require(count > 1 and available <= count, "train_denominator")
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        fraction = (Decimal(active) / count).quantize(QUANTUM) if available == count else None
    return TrainActivity(fraction, count, available)


def equal_weight(fraction: Decimal) -> tuple[Decimal, ...]:
    require(
        type(fraction) is Decimal and fraction.is_finite() and 0 <= fraction <= 1,
        "target_domain",
    )
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        require(fraction == fraction.quantize(QUANTUM), "target_lattice")
    return base._scaled_equal_weight(fraction)


def policy_actions(period: dict, decisions, activity: TrainActivity, policy: str) -> dict:
    require(policy in POLICIES and activity.fraction is not None, "policy_input")
    by_index = {item.index: item for item in decisions}
    result = {}
    for entry in period["months"]:
        fraction = by_index[entry["index"]].exposure if policy == "yield_curve" else {
            "cash": Decimal(0), "equal_weight": Decimal(1),
            "train_activity_matched": activity.fraction,
        }.get(policy)
        require(fraction is not None, "period_input_unavailable")
        result[entry["index"]] = equal_weight(fraction)
    return result


def primary_kill(cells: Sequence[dict]) -> str:
    expected = set(itertools.product((p[0] for p in PERIODS), COSTS, POLICIES))
    require(len(cells) == 24 and {(r["period"], r["cost_bps"], r["policy"]) for r in cells}
            == expected, "cell_matrix")
    if any(row["status"] != "complete" for row in cells):
        return "input_unavailable"
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 50, ROUND_HALF_EVEN
        for period, *_ in PERIODS:
            selected = {r["policy"]: r for r in cells
                        if r["period"] == period and r["cost_bps"] == "10"}
            candidate = selected["yield_curve"]
            if Decimal(candidate["final_nav"]) <= 1 + TOL:
                return "rejected"
            for policy in POLICIES[1:]:
                for metric in ("final_nav", "utility"):
                    if Decimal(candidate[metric]) - Decimal(selected[policy][metric]) <= TOL:
                        return "rejected"
    return "development_survivor_non_promoting"


def runtime_identity() -> dict:
    actual = dict(python=platform.python_version(), numpy=importlib.metadata.version("numpy"),
                  calendar=importlib.metadata.version("pandas_market_calendars"))
    expected = {key: configuration()["resource"][key] for key in actual}
    require(actual == expected, "runtime_changed")
    return actual


def calendar_schedule() -> list[dict]:
    import pandas_market_calendars as calendars

    require(importlib.metadata.version("pandas_market_calendars") == "5.4.0", "calendar_version")
    schedule = calendars.get_calendar("NYSE").schedule("2001-12-01", "2026-07-31")
    return [dict(session_date=day.date().isoformat(),
                 open_at=row["market_open"].to_pydatetime().astimezone(UTC).isoformat(),
                 close_at=row["market_close"].to_pydatetime().astimezone(UTC).isoformat())
            for day, row in schedule.iterrows()]


def source_identity() -> dict:
    return dict(
        board=dict(snapshot=board.SNAPSHOT_RELATIVE_PATH.as_posix(), url=board.SOURCE_URL,
                   sha256=dict(board.SNAPSHOT_SHA256),
                   rights="Board_public_domain_unless_indicated_cite_Board",
                   rights_url="https://www.federalreserve.gov/disclaimer.htm"),
        etf=base.source_identity(),
    )


def proposed_contract() -> dict:
    return dict(name=NAME, config=configuration(), source=source_identity(),
                runtime=runtime_identity(), plan=build_plan(calendar_schedule()),
                code_sha256={p: digest((REPO / p).read_bytes()) for p in CODE})


def _read(path: Path) -> bytes:
    return common._read(path, limit=8 * 1024**2)


def check_metadata(root: Path, market: Path) -> None:
    """Hash-only precommit audit; never parse the Board or ETF numeric source."""
    common.verify_metadata(root, market)
    for relative, pin in board.SNAPSHOT_SHA256.items():
        path = market / board.SNAPSHOT_RELATIVE_PATH / relative
        require(all(not p.is_symlink() for p in (path, *path.parents)), "source_link")
        require(digest(_read(path)) == pin, "source_hash_mismatch")


def output_path(root: Path) -> Path:
    path = Path(root).absolute() / "research" / NAME
    reject_repo_artifact_path(path, REPO)
    require(path.is_dir() and all(not p.is_symlink() for p in (path, *path.parents)),
            "artifact_path")
    return path


def register_contract(root: Path, contract: dict, pin: str) -> None:
    require(pin == digest(encode(contract)), "contract_binding")
    common.register_frozen_campaign(
        contract_hash=pin, dataset_hash=digest(encode(contract["source"])),
        split_hash=digest(encode(contract["plan"])), cost_model_hash=digest(encode(COSTS)),
        trial_family=NAME, holdout_access="none", artifact_root=root, repo_root=REPO,
    )


def freeze(root: Path, market: Path) -> str:
    check_metadata(root, market)
    contract = proposed_contract()
    parent = ensure_external_artifact_directory(root, REPO, "research")
    output = parent / NAME
    output.mkdir()
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(root, contract, pin)
    return pin


def verify(root: Path, market: Path, pin: str) -> tuple[Path, dict]:
    output = output_path(root)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin and raw == encode(proposed_contract()), "contract_changed")
    check_metadata(root, market)
    return output, json.loads(raw)


def board_decisions(plan: dict, snapshot: board.H15Snapshot):
    def slope_at(at):
        pair = board.select_h15_asof_pair(snapshot, decision_at=at)
        return pair.spread_percent if pair.status == "available" else None
    return prepare_decisions(plan, slope_at)


def prepare_marks(rows_by_symbol, period: dict, days: Sequence[str]) -> tuple[dict, dict]:
    """Validate every fixed replay mark, never future support or a reduced path."""
    require(set(rows_by_symbol) == set(SYMBOLS), "symbol_set")
    required = days[slice(*period["bounds"])]
    required_set = set(required)
    rows, missing, invalid = {symbol: {} for symbol in SYMBOLS}, 0, 0
    for symbol in SYMBOLS:
        selected = {}
        for row in rows_by_symbol[symbol]:
            day = row.session_date.isoformat()
            if day not in required_set:
                continue
            if day in selected:
                invalid += 1
            selected[day] = row
        for day in required:
            row = selected.get(day)
            if row is None:
                missing += 1
                continue
            values = (row.adj_open, row.adj_high, row.adj_low, row.adj_close)
            if (row.symbol != symbol or any(type(v) is not Decimal or not v.is_finite() or v <= 0
                                            for v in values)):
                invalid += 1
                continue
            if row.adj_high < max(values) or row.adj_low > min(values):
                invalid += 1
                continue
            rows[symbol][day] = row
    return rows, dict(missing_marks=missing, invalid_marks=invalid)


def activity_record(activity: TrainActivity, decisions) -> dict:
    return dict(
        fraction=None if activity.fraction is None else str(activity.fraction),
        scheduled_sessions=activity.scheduled_sessions,
        available_sessions=activity.available_sessions,
        all_macro_targets_sha256=digest(encode([
            [row.index, row.decision_at.isoformat(),
             None if row.exposure is None else str(row.exposure)]
            for row in decisions
        ])),
    )


def evaluate(rows_by_symbol, snapshot, contract, pin, *, deadline, seal=lambda value: None,
             phase=lambda value: None):
    """One fixed 24-cell evaluation; no fit/search and no favorable row removal."""
    require(digest(encode(contract)) == pin and contract["config"] == configuration(),
            "contract_binding")
    require(time.monotonic() < deadline, "hard_timeout")
    plan = contract["plan"]
    phase("decisions")
    decisions = board_decisions(plan, snapshot)
    activity = train_activity(plan, decisions)
    matching = activity_record(activity, decisions)
    seal(matching)  # TRAIN matching plus all macro actions, before parsing comparison marks.
    phase("source_input")
    if callable(rows_by_symbol):
        rows_by_symbol = rows_by_symbol()
    phase("evaluate")
    cells, facts = [], []
    by_index = {row.index: row for row in decisions}
    for period in plan["periods"][1:]:
        rows, marks = prepare_marks(rows_by_symbol, period, plan["days"])
        missing_macro = sum(by_index[item["index"]].exposure is None for item in period["months"])
        facts.append(dict(period=period["period"], missing_macro=missing_macro, **marks))
        unavailable = activity.fraction is None or missing_macro or any(marks.values())
        actions = {} if unavailable else {
            policy: policy_actions(period, decisions, activity, policy) for policy in POLICIES
        }
        sessions = period["bounds"][1] - period["bounds"][0]
        for cost, policy in itertools.product(COSTS, POLICIES):
            require(time.monotonic() < deadline, "hard_timeout")
            cell = dict(period=period["period"], cost_bps=cost, policy=policy,
                        status="input_unavailable" if unavailable else "complete")
            if unavailable:
                cells.append(cell)
                continue
            raw = base.replay_joint(rows, plan["days"], period["bounds"], actions[policy], cost,
                                    deadline=deadline)
            path = base.checked_path(raw, sessions, cost)
            cell.update(final_nav=str(path.navs[-1]), utility=str(base.utility(path.navs)),
                        fees_initial_nav=str(path.fees), turnover_initial_nav=str(path.turnover),
                        trades=path.trades, sessions=sessions,
                        daily_path_sha256=digest(encode([str(nav) for nav in path.navs])))
            cells.append(cell)
    criterion = primary_kill(cells)
    result = dict(name=NAME, contract_sha256=pin,
                  status="input_unavailable" if criterion == "input_unavailable" else "complete",
                  criterion=criterion, matching=matching, input_facts=facts, cells=cells,
                  actual_fits=0, parameter_searches=0, gpu=False, paper_input=False)
    validate_result(result, contract, pin)
    require(time.monotonic() < deadline, "hard_timeout")
    return result


def validate_result(result, contract, pin):
    require(result["name"] == NAME and result["contract_sha256"] == pin, "result_binding")
    require(digest(encode(contract)) == pin, "contract_binding")
    require(result["actual_fits"] == result["parameter_searches"] == 0
            and result["gpu"] is False and result["paper_input"] is False, "result_scope")
    if result["status"] == "failed":
        require(result["criterion"] == "failed" and result["cells"] == []
                and result["phase"] in {
                    "source_input", "decisions", "evaluate", "validate", "dispatch"}
                and result["reason_code"] in FAILURES, "failure_shape")
        if result["phase"] == "dispatch":
            require(result["reason_code"] in DISPATCH_FAILURES, "failure_worker_missing")
            binding = result.get("dispatch_worker_binding")
            require(isinstance(binding, dict) and set(binding) == {"status", "sha256"}
                    and binding["status"] in {"present", "absent"}, "dispatch_worker_binding")
            require((binding["status"] == "absent" and binding["sha256"] is None)
                    or (binding["status"] == "present" and isinstance(binding["sha256"], str)
                        and re.fullmatch(base.HASH, binding["sha256"])), "dispatch_worker_binding")
        else:
            require("dispatch_worker_binding" not in result, "worker_failure_origin")
        return
    matching = result["matching"]
    require(isinstance(matching["all_macro_targets_sha256"], str)
            and re.fullmatch(base.HASH, matching["all_macro_targets_sha256"]),
            "action_hash")
    count = contract["plan"]["periods"][0]["bounds"]
    require(type(matching["scheduled_sessions"]) is int
            and type(matching["available_sessions"]) is int
            and matching["scheduled_sessions"] == count[1] - count[0]
            and 0 <= matching["available_sessions"] <= matching["scheduled_sessions"],
            "train_counts")
    if matching["fraction"] is not None:
        equal_weight(Decimal(matching["fraction"]))
        require(matching["available_sessions"] == matching["scheduled_sessions"], "train_missing")
    else:
        require(matching["available_sessions"] < matching["scheduled_sessions"], "train_missing")
    expected = list(itertools.product((p[0] for p in PERIODS), COSTS, POLICIES))
    require([(c["period"], c["cost_bps"], c["policy"]) for c in result["cells"]] == expected,
            "cell_matrix")
    for cell in result["cells"]:
        require(cell["status"] in {"complete", "input_unavailable"}, "cell_status")
        if cell["status"] == "complete":
            period = next(p for p in contract["plan"]["periods"] if p["period"] == cell["period"])
            require(type(cell["sessions"]) is int
                    and cell["sessions"] == period["bounds"][1] - period["bounds"][0],
                    "cell_sessions")
            require(type(cell["trades"]) is int and 0 <= cell["trades"] <= cell["sessions"],
                    "cell_trades")
            require(isinstance(cell["daily_path_sha256"], str)
                    and re.fullmatch(base.HASH, cell["daily_path_sha256"]), "cell_path_hash")
            for metric in ("final_nav", "utility", "fees_initial_nav", "turnover_initial_nav"):
                require(Decimal(cell[metric]).is_finite(), "cell_numeric")
            require(Decimal(cell["final_nav"]) > 0 and Decimal(cell["fees_initial_nav"]) >= 0
                    and Decimal(cell["turnover_initial_nav"]) >= 0, "cell_numeric")
    require(result["criterion"] == primary_kill(result["cells"]), "criterion_changed")
    require(result["status"] == ("input_unavailable" if result["criterion"] == "input_unavailable"
                                 else "complete"), "result_status")


FAILURES = {"hard_timeout", "worker_failed", "worker_result_invalid", "execution_preempted",
            "runtime_or_source_fault", "source_hash_mismatch", "contract_changed",
            "runtime_changed"}
DISPATCH_FAILURES = {
    "hard_timeout", "worker_failed", "worker_result_invalid", "execution_preempted",
}


def failure(pin, phase, reason):
    return dict(name=NAME, contract_sha256=pin, status="failed", criterion="failed", cells=[],
                phase=phase,
                reason_code=reason if reason in FAILURES else "runtime_or_source_fault",
                actual_fits=0, parameter_searches=0, gpu=False, paper_input=False,
                raw_error_suppressed=True)


def safe_result(result):
    return {key: result[key] for key in ("status", "criterion", "contract_sha256")} | {
        "cells": len(result["cells"]), "result_sha256": digest(encode(result)),
        **({"phase": result["phase"], "reason_code": result["reason_code"]}
           if result["status"] == "failed" else {}),
    }


def append_outcome(root, pin, result):
    return register_campaign_outcome(
        contract_hash=pin,
        outcome_class=("non_promoting_failed" if result["status"] == "failed"
                       else "non_promoting_completed"),
        outcome_reference_sha256=digest(encode(result)), artifact_root=root, repo_root=REPO,
    )


def dispatch_worker_binding(output: Path) -> dict:
    """Called after the supervisor reaps its child; hash bytes without parsing."""
    worker = output / "worker-result.json"
    try:
        worker.lstat()
    except FileNotFoundError:
        return dict(status="absent", sha256=None)
    return dict(status="present", sha256=digest(_read(worker)))


def check_worker_binding(output: Path, result: dict, raw: bytes) -> None:
    if result["status"] == "failed" and result["phase"] == "dispatch":
        require(dispatch_worker_binding(output) == result["dispatch_worker_binding"],
                "dispatch_worker_changed")
    else:
        worker = output / "worker-result.json"
        require(worker.exists() or worker.is_symlink(), "failure_worker_missing")
        require(_read(worker) == raw, "worker_summary_binding")


def worker_entry(root, market, pin, deadline):
    phase = ["source_input"]
    try:
        output, contract = verify(root, market, pin)
        require(json.loads(_read(output / "started.json")) == {"contract_sha256": pin},
                "attempt_binding")
        snapshot = board.read_federal_reserve_h15_snapshot(market / board.SNAPSHOT_RELATIVE_PATH)
        result = evaluate(lambda: base.load_adjusted(market), snapshot, contract, pin,
                          deadline=deadline,
                          seal=lambda value: atomic_new(output / "train-activity.json", value),
                          phase=lambda value: phase.__setitem__(0, value))
        phase[0] = "validate"
        verify(root, market, pin)
    except Exception as error:
        # Never retain source error bodies, identifiers or numeric inputs.
        reason = (str(error) if isinstance(error, ValueError) and str(error) in FAILURES
                  else "runtime_or_source_fault")
        result = failure(pin, phase[0], reason)
    atomic_new(output_path(root) / "worker-result.json", result)


def readback(root, market, pin, *, result_sha256, deadline):
    """ALL-RO: exact numeric replay, or binding-only validation of a failure."""
    output, contract = verify(root, market, pin)
    require(json.loads(_read(output / "started.json")) == {"contract_sha256": pin},
            "attempt_binding")
    raw = _read(output / "summary.json")
    require(digest(raw) == result_sha256, "result_hash")
    result = json.loads(raw)
    validate_result(result, contract, pin)
    check_worker_binding(output, result, raw)
    if result["status"] == "failed":
        require(raw == encode(result), "failure_result_encoding")
        verify(root, market, pin)
        require(time.monotonic() < deadline, "hard_timeout")
        return dict(safe_result(result), replay="failure_binding_only",
                    fits=0, searches=0, writes=0)
    def seal(value):
        require(_read(output / "train-activity.json") == encode(value), "train_activity_changed")
    snapshot = board.read_federal_reserve_h15_snapshot(market / board.SNAPSHOT_RELATIVE_PATH)
    rebuilt = evaluate(lambda: base.load_adjusted(market), snapshot, contract, pin,
                       deadline=deadline, seal=seal)
    verify(root, market, pin)
    require(encode(rebuilt) == raw, "exact_replay_mismatch")
    return dict(safe_result(result), replay="exact", fits=0, searches=0, writes=0)


def recover_registry(root, market, pin, *, result_sha256, deadline):
    output, contract = verify(root, market, pin)
    raw = _read(output / "summary.json")
    require(digest(raw) == result_sha256, "result_hash")
    result = json.loads(raw)
    validate_result(result, contract, pin)
    replayed = readback(root, market, pin, result_sha256=result_sha256, deadline=deadline)
    require(_read(output / "summary.json") == raw and time.monotonic() < deadline,
            "recovery_changed")
    require(json.loads(_read(output / "started.json")) == {"contract_sha256": pin},
            "attempt_binding")
    check_worker_binding(output, result, raw)
    entry = append_outcome(root, pin, result)
    return dict(safe_result(result), recovery="registry_only", replay=replayed["replay"],
                fits=0, searches=0,
                attempt_artifact_writes=0, outcome_record_sha256=entry.record_sha256)


def readback_entry(operation, root, market, pin, result_pin, deadline, connection):
    try:
        require(operation in {"verify", "recover-registry"}, "readback_operation")
        function = readback if operation == "verify" else recover_registry
        connection.send(function(root, market, pin, result_sha256=result_pin, deadline=deadline))
    except Exception:
        connection.send(dict(status="readback_unavailable", raw_error_suppressed=True))
        raise SystemExit(1) from None
    finally:
        connection.close()


def synthetic_inputs():
    """Small, explicitly synthetic schedule/marks/rates; no real-source access."""
    dates = tuple(date.fromisoformat(day) for day in (
        "2001-12-31", "2002-01-02", "2002-01-03", "2002-02-01", "2002-02-04",
        "2012-12-31", "2013-01-02", "2013-01-03", "2013-02-01", "2013-02-04",
        "2019-12-31", "2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04",
        "2026-07-01", "2026-07-02", "2026-07-31",
    ))
    schedule = [dict(session_date=day.isoformat(),
                     open_at=datetime(day.year, day.month, day.day, 14, 30, tzinfo=UTC).isoformat(),
                     close_at=datetime(day.year, day.month, day.day, 21, tzinfo=UTC).isoformat())
                for day in dates]
    plan = build_plan(schedule)
    observations = sorted({datetime.fromisoformat(entry["decision_at"]).date() - timedelta(days=30)
                           for p in plan["periods"] for entry in p["months"]})
    snapshot = board.H15Snapshot(
        tuple(board.H15Observation(day, Decimal(1)) for day in observations),
        tuple(board.H15Observation(day, Decimal(2 if i % 2 else 0))
              for i, day in enumerate(observations)),
    )
    rows = {symbol: tuple(etf.AdjustedEtfRow(symbol, day, *(Decimal(100),) * 4) for day in dates)
            for symbol in SYMBOLS}
    contract = dict(name=NAME, config=configuration(), plan=plan)
    return rows, snapshot, contract


def synthetic_smoke() -> dict:
    rows, snapshot, contract = synthetic_inputs()
    result = evaluate(rows, snapshot, contract, digest(encode(contract)),
                      deadline=time.monotonic() + SECONDS)
    require(len(result["cells"]) == 24 and result["criterion"] == "rejected", "synthetic_smoke")
    return dict(status="synthetic_smoke_passed", cells=24, actual_fits=0,
                parameter_searches=0, actual_source_reads=0, gpu=False)
