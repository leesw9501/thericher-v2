"""One frozen, seen-data, calendar-only Tiingo D1 development study.

Plans contain dates only. Rows enter only after immutable precommit and attempt
reservation; outputs contain aggregate bps, counts and dates, never source rows.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

from thericher_v2.data.tiingo_etf_daily import (
    TiingoEtfDailyRow,
    load_verified_tiingo_etf_d1_snapshot,
)
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory
from thericher_v2.research.campaign_registry import register_frozen_campaign

NAME = "tiingo-d1-first-session-month-development-v1"
REPO = Path(__file__).resolve().parents[3]
SYMBOLS = ("SPY", "QQQ", "IWM")
COSTS = (5, 10, 20)
POLICIES = ("month_start", "session_11", "cash")
PERIODS = (("2013-2019", "2013-01", "2019-12"), ("2020-2026-07", "2020-01", "2026-07"))
MIN_PAIRS = 60
SECONDS = 600
MEMORY_BYTES = 1024**3
SNAPSHOT = "us_equities/tiingo_etf_daily/canonical/snapshot=20260809T163557Z-tiingo-etf-d1-r1"
DATASET_ID = "us_equities.tiingo_etf_daily.snapshot=20260809T163557Z-tiingo-etf-d1-r1"
DATASET_HASH = "sha256:becc3e4b0ed4610da9325de3e6b88d1f24f869199d3d81a285b60b1b340df0aa"
MANIFEST_HASH = "sha256:4a2344b7ab8ec2eaf0b1a5e4afcd41e07cf0b4c14e13db64d07b41fd054883d2"
RECEIPT = "data-receipts/tiingo-etf-d1/" + MANIFEST_HASH[7:] + ".json"
RECEIPT_HASH = "sha256:626cb94b299779542a4e9fc585c3e0c302f0540875145c212df0f2b99910b127"
CODE = (
    "src/thericher_v2/research/tiingo_month_start_development.py",
    "scripts/run_tiingo_month_start_development.py",
    "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py",
    "src/thericher_v2/data/tiingo_etf_daily.py",
    "src/thericher_v2/data/__init__.py",
    "src/thericher_v2/research/__init__.py",
    "src/thericher_v2/research/artifact_paths.py",
    "src/thericher_v2/research/campaign_registry.py",
)
METRICS = (
    "observed_mean_gross_bps",
    "observed_mean_net_bps",
    "paired_mean_gross_bps",
    "paired_mean_net_bps",
    "paired_difference_vs_session_11_bps",
)
FAILURES = frozenset(
    {
        "worker_failed",
        "hard_timeout",
        "execution_preempted",
        "worker_result_invalid",
        "runtime_or_invariant_failure",
    }
)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def encode(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def source_identity() -> dict:
    return dict(
        dataset_id=DATASET_ID,
        dataset_sha256=DATASET_HASH,
        manifest_sha256=MANIFEST_HASH,
        receipt_sha256=RECEIPT_HASH,
        snapshot=SNAPSHOT,
        receipt=RECEIPT,
    )


def configuration() -> dict:
    return {
        "symbols": list(SYMBOLS),
        "costs_all_in_roundtrip_bps": list(COSTS),
        "primary_cost_bps": 10,
        "stress_cost_bps": 20,
        "policies": list(POLICIES),
        "cells": 54,
        "minimum_paired_months": MIN_PAIRS,
        "preparation": ["2001-01", "2012-12", "calendar_and_coverage_only_no_payoffs"],
        "periods": [list(p) for p in PERIODS],
        "tail_exclusion": "only_incomplete_August_2026_and_later_not_prior_Augusts",
        "calendar": "pandas-market-calendars==5.4.0 NYSE",
        "decision": "previous_scheduled_session_close_calendar_only",
        "entry_exit": "scheduled_session_open_to_same_session_close_no_overnight",
        "month_start_ordinal": 1,
        "control_ordinal": 11,
        "cost_formula": "10000*(close/open-1)-all_in_roundtrip_bps; cash=0",
        "aggregation": "independent_unit_entry_notional_trades_not_portfolio_NAV",
        "pairing": "within_symbol_period_month_both_fixed_sessions_observed",
        "criterion": (
            "every_six_groups_paired_candidate_mean_gt_0_and_paired_difference_gt_0_at_20bps"
        ),
        "insufficient": "any_group_below_60_pairs_input_unavailable_all_metrics_suppressed",
        "missing": "keep_planned_date_no_shift_or_backfill; postdecision_outcome_censoring",
        "events": "no_event_mask; keep_aggregate_event_counts; no_cross_day_price_feature",
        "numeric": "Decimal_precision_50_output_bps_12dp_ROUND_HALF_EVEN",
        "budget": {
            "cpu_threads": 1,
            "wall_seconds": SECONDS,
            "memory_bytes": MEMORY_BYTES,
            "gpu": False,
            "passes": 1,
            "training": False,
            "retries": False,
        },
        "resource_owner": "main_Docker_cpu_memory_network_mounts; existing_supervisor_wall_timeout",
        "technical_kills": [
            "future_rows_cannot_change_plan",
            "same_day_scale_invariance",
            "missing_rows_cannot_renumber_sessions",
            "source_contract_binding",
            "duplicate_or_nonmonotone_rows",
            "nonfinite_or_invalid_ohlc_censored",
        ],
        "assumptions": [
            "historical_calendar_is_not_contemporaneous_announcement_evidence",
            "calendar_closures_and_open_close_session_mapping_assumed",
            "revised_non_PIT_EOD_prices_and_finality_unverified",
            "auction_access_fill_capacity_latency_not_verified",
            "EOD_open_is_not_proven_primary_auction_execution",
            "revisions_can_change_open_and_close_independently_scale_invariance_does_not_cover_revision_bias",
            "identical_candidate_control_flat_cost_assumes_zero_cost_differential",
            "session_11_is_fixed_comparison_not_causally_clean_placebo",
            "positive_mean_can_be_tiny_or_outlier_driven_not_statistical_evidence",
            "all_in_cost_is_analytical_proxy_not_broker_fee_or_fill_parity",
            "same_session_positive_scale_cancels_not_full_corporate_action_qualification",
            "outcome_censoring_can_bias_paired_and_unpaired_means",
            "fixed_surviving_ETFs_not_PIT_universe_or_independent_replications",
            "seen_data_outcome_informed_development_not_holdout_or_replication",
            "prior_August1_trials_overlap_August9_refresh_not_new_independent_evidence",
        ],
        "prior_families": [
            "tiingo-etf-d1-cpu-baseline-v1",
            "tiingo-d1-sequence-breadth-v1",
            "tiingo-d1-trend-mean-reversion-rotation-v1",
            "tiingo-d1-trio-intraday-compression-continuation-falsification-v1",
        ],
        "scope": dict(
            descriptive_only=True,
            holdout_access="none",
            model_selection=False,
            promotion=False,
            paper_input=False,
            local_paper_parity=False,
            profitability_claim=False,
            independent_replication=False,
        ),
    }


def _months(first: str, last: str) -> list[str]:
    year, month = map(int, first.split("-"))
    result = []
    while f"{year:04d}-{month:02d}" <= last:
        result.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


def build_plan(sessions: Sequence[date]) -> list[dict]:
    """Select ordinal sessions on the supplied calendar, never on source rows."""
    require(all(type(day) is date for day in sessions), "invalid_calendar_date")
    require(all(a < b for a, b in zip(sessions, sessions[1:], strict=False)), "calendar_order")
    by_month: dict[str, list[int]] = {}
    for index, day in enumerate(sessions):
        by_month.setdefault(day.strftime("%Y-%m"), []).append(index)
    plan = []
    for month in _months("2001-01", "2026-07"):
        indices = by_month.get(month, [])
        require(len(indices) >= 11 and indices[0] > 0, "calendar_month_incomplete")
        first, control = indices[0], indices[10]
        phase = next((name for name, start, end in PERIODS if start <= month <= end), "preparation")
        plan.append(
            dict(
                period=phase,
                month=month,
                month_start=sessions[first].isoformat(),
                month_start_decision=sessions[first - 1].isoformat(),
                session_11=sessions[control].isoformat(),
                session_11_decision=sessions[control - 1].isoformat(),
            )
        )
    return plan


def calendar_plan() -> list[dict]:
    require(importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version")
    import pandas_market_calendars as calendars

    schedule = calendars.get_calendar("NYSE").schedule(
        start_date="2000-12-01", end_date="2026-07-31"
    )
    return build_plan(tuple(stamp.date() for stamp in schedule.index))


def proposed_contract() -> dict:
    config = configuration()
    source = source_identity()
    return dict(
        schema_version=1,
        name=NAME,
        config=config,
        config_sha256=digest(encode(config)),
        source=source,
        source_sha256=digest(encode(source)),
        plan=calendar_plan(),
        code_sha256={path: digest((REPO / path).read_bytes()) for path in CODE},
    )


def _read(path: Path, limit: int = 1024**2) -> bytes:
    require(path.is_file() and not path.is_symlink(), "artifact_not_regular")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    require(len(raw) <= limit, "artifact_oversize")
    return raw


def atomic_new(path: Path, payload: object) -> None:
    """Publish a fully synced file atomically, with no replacement even in a race."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encode(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_metadata(artifact_root: Path, market_data_root: Path) -> None:
    require(digest(_read(artifact_root / RECEIPT)) == RECEIPT_HASH, "receipt_hash")
    require(
        digest(_read(market_data_root / SNAPSHOT / "manifest.json")) == MANIFEST_HASH,
        "manifest_hash",
    )


def freeze(artifact_root: Path, market_data_root: Path) -> str:
    """Metadata only; never load market rows or reuse any prior attempt directory."""
    verify_metadata(artifact_root, market_data_root)
    contract = proposed_contract()
    parent = ensure_external_artifact_directory(artifact_root, REPO, "research")
    output = parent / NAME
    output.mkdir()  # Exclusive directory ownership also preserves interrupted freezes.
    atomic_new(output / "precommit.json", contract)
    pin = digest(encode(contract))
    register_contract(artifact_root, contract, pin)
    return pin


def register_contract(artifact_root: Path, contract: dict, pin: str) -> None:
    _header(contract, pin)
    register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=DATASET_HASH,
        split_hash=digest(encode(contract["plan"])),
        cost_model_hash=digest(encode(contract["config"]["costs_all_in_roundtrip_bps"])),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=REPO,
    )


def verify(artifact_root: Path, market_data_root: Path, pin: str) -> tuple[Path, dict]:
    output = ensure_external_artifact_directory(artifact_root, REPO, "research", NAME)
    raw = _read(output / "precommit.json")
    require(digest(raw) == pin, "precommit_hash")
    require(raw == encode(proposed_contract()), "source_config_code_or_plan_changed")
    verify_metadata(artifact_root, market_data_root)
    return output, json.loads(raw)


def _header(contract: dict, pin: str) -> dict:
    require(digest(encode(contract)) == pin, "contract_binding")
    require(encode(contract["config"]) == encode(configuration()), "config_not_frozen")
    require(contract["source"] == source_identity(), "source_not_frozen")
    require(contract["config_sha256"] == digest(encode(configuration())), "config_hash")
    require(contract["source_sha256"] == digest(encode(source_identity())), "source_hash")
    plan = contract["plan"]
    require([p["month"] for p in plan] == _months("2001-01", "2026-07"), "plan_months")
    for item in plan:
        require(
            set(item)
            == {
                "period",
                "month",
                "month_start",
                "month_start_decision",
                "session_11",
                "session_11_decision",
            },
            "plan_fields",
        )
        phase = next(
            (name for name, start, end in PERIODS if start <= item["month"] <= end), "preparation"
        )
        require(item["period"] == phase, "plan_period")
        for policy in POLICIES[:2]:
            session = date.fromisoformat(item[policy])
            decision = date.fromisoformat(item[policy + "_decision"])
            require(
                session.isoformat() == item[policy]
                and decision.isoformat() == item[policy + "_decision"]
                and session.strftime("%Y-%m") == item["month"]
                and decision < session,
                "plan_date",
            )
        require(
            item["month_start"] < item["session_11_decision"] < item["session_11"], "plan_order"
        )
    return dict(
        schema_version=1,
        name=NAME,
        contract_sha256=pin,
        config_sha256=contract["config_sha256"],
        source=contract["source"],
        source_sha256=contract["source_sha256"],
        scope=configuration()["scope"],
    )


def _number(value: Decimal) -> str:
    with localcontext() as context:
        context.prec = 50
        return format(value.quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_EVEN), "f")


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal(0)) / len(values)


def _valid_ohlc(row: TiingoEtfDailyRow) -> bool:
    values = (row.open, row.high, row.low, row.close)
    return (
        all(isinstance(v, Decimal) and v.is_finite() and v > 0 for v in values)
        and row.low <= min(row.open, row.close) <= max(row.open, row.close) <= row.high
    )


def evaluate(
    rows_by_symbol: Mapping[str, Sequence[TiingoEtfDailyRow]],
    contract: dict,
    pin: str,
    *,
    deadline: float,
) -> dict:
    """One pass; establish support without returns, then score the frozen plan."""
    result = _header(contract, pin)
    require(set(rows_by_symbol) == set(SYMBOLS), "symbol_set")
    groups, support, preparation = [], {}, []
    for symbol in SYMBOLS:
        rows = rows_by_symbol[symbol]
        require(
            all(r.symbol == symbol and type(r.session_date) is date for r in rows), "row_identity"
        )
        require(
            all(a.session_date < b.session_date for a, b in zip(rows, rows[1:], strict=False)),
            "duplicate_or_nonmonotone_rows",
        )
        index = {row.session_date.isoformat(): row for row in rows}
        preparation_plans = [p for p in contract["plan"] if p["period"] == "preparation"]
        preparation.append(
            dict(
                symbol=symbol,
                scheduled_months=len(preparation_plans),
                month_start_dates_present=sum(p["month_start"] in index for p in preparation_plans),
                session_11_dates_present=sum(p["session_11"] in index for p in preparation_plans),
            )
        )
        for period, _, _ in PERIODS:
            require(time.monotonic() < deadline, "wall_limit")
            plans = [p for p in contract["plan"] if p["period"] == period]
            group = dict(symbol=symbol, period=period, scheduled_count=len(plans), legs={})
            observed = {}
            for policy in POLICIES[:2]:
                valid, censored, events = {}, [], 0
                for plan in plans:
                    row = index.get(plan[policy])
                    reason = (
                        "missing_row"
                        if row is None
                        else (None if _valid_ohlc(row) else "invalid_ohlc")
                    )
                    if reason:
                        censored.append(dict(month=plan["month"], date=plan[policy], reason=reason))
                    else:
                        valid[plan["month"]] = row
                        events += int(row.div_cash != 0 or row.split_factor != 1)
                group["legs"][policy] = dict(
                    observed_months=list(valid), censored=censored, event_observed_count=events
                )
                observed[policy] = valid
            pairs = sorted(set(observed["month_start"]) & set(observed["session_11"]))
            group.update(
                paired_months=pairs,
                paired_count=len(pairs),
                pair_censored_count=len(plans) - len(pairs),
            )
            groups.append(group)
            support[symbol, period] = observed
    sufficient = all(g["paired_count"] >= MIN_PAIRS for g in groups)
    cells = []
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        for group in groups:
            require(time.monotonic() < deadline, "wall_limit")
            observed = support[group["symbol"], group["period"]]
            returns = {}
            if sufficient:
                returns = {
                    policy: {m: (r.close / r.open - 1) * 10000 for m, r in valid.items()}
                    for policy, valid in observed.items()
                }
            for cost in COSTS:
                for policy in POLICIES:
                    count = group["scheduled_count"] if policy == "cash" else len(observed[policy])
                    cell = dict(
                        symbol=group["symbol"],
                        period=group["period"],
                        cost_bps=cost,
                        policy=policy,
                        scheduled_count=group["scheduled_count"],
                        observed_count=count,
                        censored_count=group["scheduled_count"] - count,
                        paired_count=group["paired_count"],
                        status="evaluated" if sufficient else "input_unavailable",
                        **dict.fromkeys(METRICS),
                    )
                    if sufficient:
                        gross = paired = delta = Decimal(0)
                        debit = Decimal(0) if policy == "cash" else Decimal(cost)
                        control = _mean([returns["session_11"][m] for m in group["paired_months"]])
                        if policy != "cash":
                            gross = _mean(list(returns[policy].values()))
                            paired = _mean([returns[policy][m] for m in group["paired_months"]])
                        delta = paired - debit - (control - cost)
                        cell.update(
                            zip(
                                METRICS,
                                map(_number, (gross, gross - debit, paired, paired - debit, delta)),
                                strict=True,
                            )
                        )
                    cells.append(cell)
    result.update(
        status="complete" if sufficient else "input_unavailable",
        preparation=preparation,
        groups=groups,
        cells=cells,
    )
    result["criterion"] = criterion(cells) if sufficient else "not_evaluable"
    validate_result(result, contract, pin)
    return result


def criterion(cells: Sequence[dict]) -> str:
    stress = [c for c in cells if c["cost_bps"] == 20 and c["policy"] == "month_start"]
    require(len(stress) == 6, "stress_matrix")
    met = all(
        Decimal(c["paired_mean_net_bps"]) > 0
        and Decimal(c["paired_difference_vs_session_11_bps"]) > 0
        for c in stress
    )
    return "descriptive_criterion_met" if met else "descriptive_criterion_not_met"


def failure(contract: dict, pin: str, reason: str) -> dict:
    require(reason in FAILURES, "failure_category")
    return dict(
        _header(contract, pin),
        status="failed",
        reason=reason,
        criterion="not_evaluable",
        groups=[],
        cells=[],
    )


def validate_result(result: dict, contract: dict, pin: str) -> None:
    """Strict source-safe schema, exact matrix, support and cross-cost relations."""
    header = _header(contract, pin)
    if result.get("status") == "failed":
        require(
            encode(result) == encode(failure(contract, pin, result.get("reason"))),
            "invalid_failure",
        )
        return
    require(
        set(result) == set(header) | {"status", "criterion", "preparation", "groups", "cells"},
        "result_fields",
    )
    require(encode({k: result[k] for k in header}) == encode(header), "result_binding")
    preparation = result["preparation"]
    require(isinstance(preparation, list) and len(preparation) == 3, "preparation_count")
    require([p["symbol"] for p in preparation] == list(SYMBOLS), "preparation_symbols")
    for item in preparation:
        require(
            set(item)
            == {
                "symbol",
                "scheduled_months",
                "month_start_dates_present",
                "session_11_dates_present",
            },
            "preparation_fields",
        )
        require(
            type(item["scheduled_months"]) is int and item["scheduled_months"] == 144,
            "preparation_months",
        )
        for key in ("month_start_dates_present", "session_11_dates_present"):
            require(type(item[key]) is int and 0 <= item[key] <= 144, "preparation_coverage")
    groups = result["groups"]
    require(isinstance(groups, list) and len(groups) == 6, "group_count")
    expected_groups = [(s, p) for s in SYMBOLS for p, _, _ in PERIODS]
    require([(g["symbol"], g["period"]) for g in groups] == expected_groups, "group_keys")
    for group in groups:
        require(
            set(group)
            == {
                "symbol",
                "period",
                "scheduled_count",
                "legs",
                "paired_months",
                "paired_count",
                "pair_censored_count",
            },
            "group_fields",
        )
        plans = {p["month"]: p for p in contract["plan"] if p["period"] == group["period"]}
        require(
            type(group["scheduled_count"]) is int and group["scheduled_count"] == len(plans),
            "scheduled_count",
        )
        require(set(group["legs"]) == set(POLICIES[:2]), "leg_keys")
        for policy, leg in group["legs"].items():
            require(
                set(leg) == {"observed_months", "censored", "event_observed_count"}, "leg_fields"
            )
            months = leg["observed_months"]
            require(
                isinstance(months, list)
                and months == sorted(set(months))
                and set(months) <= set(plans),
                "observed_months",
            )
            require(
                type(leg["event_observed_count"]) is int
                and 0 <= leg["event_observed_count"] <= len(months),
                "event_count",
            )
            censored = leg["censored"]
            require(isinstance(censored, list), "censored_list")
            for item in censored:
                require(
                    set(item) == {"month", "date", "reason"} and item["month"] in plans,
                    "censor_fields",
                )
                require(
                    item["date"] == plans[item["month"]][policy]
                    and item["reason"] in {"missing_row", "invalid_ohlc"},
                    "censor_binding",
                )
            require(
                [x["month"] for x in censored] == sorted(set(plans) - set(months)),
                "censor_partition",
            )
        pairs = sorted(
            set(group["legs"]["month_start"]["observed_months"])
            & set(group["legs"]["session_11"]["observed_months"])
        )
        require(
            group["paired_months"] == pairs
            and type(group["paired_count"]) is int
            and group["paired_count"] == len(pairs)
            and type(group["pair_censored_count"]) is int
            and group["pair_censored_count"] == len(plans) - len(pairs),
            "paired_count",
        )
    sufficient = all(g["paired_count"] >= MIN_PAIRS for g in groups)
    require(
        result["status"] == ("complete" if sufficient else "input_unavailable"), "status_support"
    )
    cells = result["cells"]
    require(isinstance(cells, list) and len(cells) == 54, "cell_count")
    expected = [
        (s, p, cost, policy) for s, p in expected_groups for cost in COSTS for policy in POLICIES
    ]
    require(
        [(c["symbol"], c["period"], c["cost_bps"], c["policy"]) for c in cells] == expected,
        "cell_keys",
    )
    index = {}
    for cell in cells:
        require(
            set(cell)
            == {
                "symbol",
                "period",
                "cost_bps",
                "policy",
                "scheduled_count",
                "observed_count",
                "censored_count",
                "paired_count",
                "status",
            }
            | set(METRICS),
            "cell_fields",
        )
        group = groups[expected_groups.index((cell["symbol"], cell["period"]))]
        observed = (
            group["scheduled_count"]
            if cell["policy"] == "cash"
            else len(group["legs"][cell["policy"]]["observed_months"])
        )
        for key, value in dict(
            scheduled_count=group["scheduled_count"],
            observed_count=observed,
            censored_count=group["scheduled_count"] - observed,
            paired_count=group["paired_count"],
        ).items():
            require(type(cell[key]) is int and cell[key] == value, "cell_counts")
        require(type(cell["cost_bps"]) is int, "cost_type")
        require(
            cell["status"] == ("evaluated" if sufficient else "input_unavailable"), "cell_status"
        )
        for key in METRICS:
            value = cell[key]
            if not sufficient:
                require(value is None, "unavailable_metric")
            else:
                require(isinstance(value, str) and len(value) <= 80, "metric_type")
                number = Decimal(value)
                require(number.is_finite() and value == _number(number), "metric_numeric")
        index[cell["symbol"], cell["period"], cell["cost_bps"], cell["policy"]] = cell
    if sufficient:
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            for key, cell in index.items():
                symbol, period, cost, policy = key
                debit = Decimal(0 if policy == "cash" else cost)
                for prefix in ("observed", "paired"):
                    gross, net = (Decimal(cell[f"{prefix}_mean_{k}_bps"]) for k in ("gross", "net"))
                    require(abs(gross - debit - net) <= Decimal("2e-12"), "cost_arithmetic")
                    base = index[symbol, period, 5, policy]
                    require(
                        cell[f"{prefix}_mean_gross_bps"] == base[f"{prefix}_mean_gross_bps"],
                        "cross_cost_cohort",
                    )
                    if policy == "cash":
                        require(gross == net == 0, "cash_not_zero")
                control = index[symbol, period, cost, "session_11"]
                difference = Decimal(cell["paired_mean_net_bps"]) - Decimal(
                    control["paired_mean_net_bps"]
                )
                require(
                    abs(difference - Decimal(cell[METRICS[-1]])) <= Decimal("2e-12"),
                    "paired_difference",
                )
        require(result["criterion"] == criterion(cells), "criterion_mismatch")
    else:
        require(result["criterion"] == "not_evaluable", "unavailable_criterion")


def run_worker(
    artifact_root: Path, market_data_root: Path, pin: str, path: Path, deadline: float
) -> None:
    """Called by the supervised worker; main's Docker command owns resource limits."""
    output, contract = verify(artifact_root, market_data_root, pin)
    require(path == output / "worker-result.json", "worker_path")
    require(
        not path.exists() and not path.is_symlink() and not (output / "summary.json").exists(),
        "worker_output_exists",
    )
    require(
        json.loads(_read(output / "started.json")) == {"contract_sha256": pin}, "attempt_binding"
    )
    try:
        snapshot = load_verified_tiingo_etf_d1_snapshot(
            market_data_root / SNAPSHOT,
            dataset_id=DATASET_ID,
            expected_dataset_hash=DATASET_HASH,
            expected_manifest_hash=MANIFEST_HASH,
            market_data_root=market_data_root,
            repo_root=REPO,
        )
        require(
            snapshot.snapshot.dataset_id == DATASET_ID
            and snapshot.snapshot.dataset_hash == DATASET_HASH
            and snapshot.snapshot.manifest_hash == MANIFEST_HASH,
            "loaded_source_binding",
        )
        result = evaluate(snapshot.rows_by_symbol, contract, pin, deadline=deadline)
        verify(artifact_root, market_data_root, pin)
    except Exception:
        result = failure(contract, pin, "runtime_or_invariant_failure")
    atomic_new(path, result)
