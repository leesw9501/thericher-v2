"""One fixed, offline opening-range DEVELOPMENT study on already-seen data.

Decisions are frozen before full-session outcome censoring. The time-matched
long is a descriptive within-fold benchmark, not an independent strategy.
"""

from __future__ import annotations

import importlib.metadata
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import firstrate_session_research as sessions

h30, require = sessions.h30, sessions.require
REPO, STEP = h30.REPO, h30.STEP
NAME = FAMILY = "firstrate-m5-opening-range-development-20260923-v1"
GRADE = "OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT"
SECONDS, MIN_SESSIONS, MIN_TRADES = 600, 16, 8
COSTS, SYMBOLS = (1, 3, 5), ("SPY", "QQQ")
FLAGS = ("training", "gpu", "selection", "promotion", "holdout_access")
SOURCE_PINS = {
    "SPY": ("db797f4355dc3cd82113730e1689ee0750226b16568687d86b6ca3e407053777", 207824),
    "QQQ": ("27a6f601d41b7a96d38db663cc63c821471d511bbb196a88021acf81b8d92c3c", 210482),
}
CODE = (
    "src/thericher_v2/research/firstrate_opening_range.py",
    "scripts/run_firstrate_opening_range.py",
    "scripts/run_firstrate_position_policy.py",
    "src/thericher_v2/research/firstrate_session_research.py",
    *h30.CODE_PATHS,
)
DECISIONS = ("selected", "no_breakout", "opening_unavailable", "scan_unavailable")
COUNTS = (*DECISIONS, "sessions", "observed", "censored", "selected_observed", "selected_censored")
METRICS = ("gross_dollars", "fees_dollars", "net_dollars", "net_bps_sum")


def contract(receipt):
    specs = h30.parse_firstrate_normalization_receipt(receipt)
    require(
        {s.symbol: (s.canonical_sha256.removeprefix("sha256:"), s.bar_count) for s in specs}
        == SOURCE_PINS,
        "source_pins_changed",
    )
    return dict(
        name=NAME,
        family=FAMILY,
        evidence_grade=GRADE,
        interpretation="descriptive source-local implementation/comparison only",
        normalization_sha256=h30.digest(receipt),
        source_pins=[
            dict(
                symbol=s.symbol,
                path=s.canonical_market_data_relative_path.as_posix(),
                sha256=s.canonical_sha256,
                rows=s.bar_count,
                timestamps_sha256=s.emitted_timestamp_set_sha256,
            )
            for s in specs
        ],
        prior_seen_family=h30.FAMILY,
        prior_diagnostic_summary_sha256=(
            "sha256:47ed62aa043511e01f5550a5e81fb26a5d0d4b8081ce373453ea1d4b8aeb0b8f"
        ),
        code_sha256={p: h30.digest((REPO / p).read_bytes()) for p in CODE},
        calendar="pandas-market-calendars==5.4.0 NYSE; same source-span sessions as parent",
        split="all scheduled sessions before masks: [floor(N/2),floor(3N/4)); [floor(3N/4),N)",
        training_rule="none; earlier sessions unused, no fitted features or thresholds",
        range="max high of six complete M5 bars at session open through open+30min",
        signal="first subsequent completed M5 close STRICTLY above range high",
        entry="next M5 open; first possible open+35min; last possible close-10min",
        exit="scheduled close-5min OPEN, including early closes; at most one long/session",
        session_rule="NYSE full/early sessions; no extended hours, overnight, carry or reentry",
        missing_rule="missing/incomplete opening or pre-signal scan bar ends that session scan",
        outcome_rule="after decisions require ALL session M5 bars, including exit bar, complete; "
        "common mask for ORB/controls; missing payoff is censored, never zero or backfilled",
        control="for each scored ORB entry offset, mean unconditional one-share long payoff "
        "at SAME entry offset AND session duration over ALL common complete fold sessions, "
        "including the signal session; sum those means, cash=0; no signal filtering of pool",
        control_limits="descriptive in-fold matched-time mean, not a deployable strategy or "
        "independent estimate; repeated control rows are NOT independent observations",
        target="rounded exit open / rounded entry open - 1; observed path only",
        quantity=1,
        roundtrip_cash=10000,
        fees_bps_per_side=list(COSTS),
        slippage_bps=0,
        rounding="LocalPaperBroker Decimal 0.0001 ROUND_HALF_EVEN for price and each side fee",
        minimums=dict(
            complete_sessions_per_symbol_fold=MIN_SESSIONS,
            scored_orb_trades_per_symbol_fold=MIN_TRADES,
        ),
        metrics=list(METRICS) + ["support", "control_pool_sizes", "paired_net_bps_delta"],
        effective_sample="unique session blocks; correlated symbols/folds, no p-values",
        budget=dict(
            cpu_seconds=SECONDS,
            cpu_threads=1,
            fits=0,
            cells=12,
            max_m1_rows_per_symbol=250000,
            max_source_bytes=134217728,
            retries=0,
        ),
        strongest_kill_test="any future-dependent decision or replay/identity mismatch "
        "invalidates all cells; insufficient complete sessions/trades is input_unavailable; "
        "criterion is ORB above cash AND matched long in net bps at 3bps/side for EACH symbol "
        "in BOTH seen folds; no 1/5bps rescue or retuning; fixed descriptive 3bps comparison "
        "across four symbol/folds, not economic rejection/survival, confidence or evidence "
        "against ORB mechanism",
        limitations=[
            "already_seen_not_independent",
            "source_clock_boundary_unverified",
            "provider_finality_not_observed",
            "corporate_actions_unqualified",
            "complete_session_posthoc_censoring",
            "fees_only_zero_latency",
            "independent_one_share_trades_not_NAV",
            "no_KIS_parity",
        ],
        **dict.fromkeys(FLAGS, False),
    )


def directory(root):
    root = h30.ensure_external_artifact_directory(root, REPO)
    return h30.within(root, Path("research") / NAME)


def freeze(root):
    payload = contract(h30.within(root, h30.RECEIPT).read_bytes())
    output = directory(root)
    output.mkdir(parents=True, exist_ok=False)
    raw = h30.encode(payload)
    with (output / "contract.json").open("xb") as handle:
        handle.write(raw)
    h30.register_frozen_campaign(
        contract_hash=h30.digest(raw),
        dataset_hash=h30.digest(h30.encode(payload["source_pins"])),
        split_hash=h30.digest(h30.encode(payload["split"])),
        cost_model_hash=h30.digest(h30.encode([COSTS, payload["control"]])),
        trial_family=FAMILY,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )
    return h30.digest(raw)


def verify(root, scope_hash):
    output = directory(root)
    raw = (output / "contract.json").read_bytes()
    require(
        h30.digest(raw) == scope_hash
        and raw == h30.encode(contract(h30.within(root, h30.RECEIPT).read_bytes())),
        "contract_changed",
    )
    return output


@dataclass(frozen=True)
class Decision:
    opening: datetime
    closing: datetime
    status: str
    signal: Bar | None = None

    @property
    def at(self):
        return None if self.signal is None else self.signal.end_ts


def checked_bar(index, at, symbol):
    bar = index.get(at)
    if bar is None:
        return None
    require(
        (bar.start_ts, bar.symbol, bar.market, bar.timeframe) == (at, symbol, "US", Timeframe.M5),
        "bar_identity",
    )
    return bar if bar.complete else None


def decide(index, symbol, opening, closing):
    """Look up only the causal prefix, stopping permanently at its first signal/gap."""
    require(
        opening + 8 * STEP < closing <= opening + 78 * STEP
        and (closing - opening) % STEP == STEP * 0,
        "session_geometry",
    )
    first = tuple(checked_bar(index, opening + i * STEP, symbol) for i in range(6))
    if any(b is None for b in first):
        return Decision(opening, closing, "opening_unavailable")
    high = max(b.high for b in first)
    at = opening + 6 * STEP
    while at + STEP < closing - STEP:
        bar = checked_bar(index, at, symbol)
        if bar is None:
            return Decision(opening, closing, "scan_unavailable")
        if bar.close > high:
            return Decision(opening, closing, "selected", bar)
        at += STEP
    return Decision(opening, closing, "no_breakout")


def complete_path(index, symbol, opening, closing):
    bars = tuple(
        checked_bar(index, opening + i * STEP, symbol) for i in range((closing - opening) // STEP)
    )
    return None if any(b is None for b in bars) else bars


def folds(schedule):
    n = len(schedule)
    require(
        n >= 4 and all(a[1] < b[0] for a, b in zip(schedule, schedule[1:], strict=False)),
        "session_order",
    )
    return (schedule[n // 2 : 3 * n // 4], schedule[3 * n // 4 :])


def metric(gross, fees, entry):
    return dict(
        zip(METRICS, (gross, fees, gross - fees, (gross - fees) / entry * 10000), strict=True)
    )


def sum_metrics(values):
    return {k: sum((v[k] for v in values), Decimal(0)) for k in METRICS}


def strings(values):
    return {k: str(v) for k, v in values.items()}


def compare_fold(symbol, number, index, schedule, emergency, deadline, *, replay=sessions.payoff):
    decisions = tuple(decide(index, symbol, o, c) for o, c in schedule)
    # Outcome support is attached only after every session's causal decision is fixed.
    paths = tuple(complete_path(index, symbol, o, c) for o, c in schedule)
    counts = dict.fromkeys(COUNTS, 0)
    counts.update(Counter(d.status for d in decisions))
    counts.update(sessions=len(schedule), observed=sum(p is not None for p in paths))
    counts["censored"] = counts["sessions"] - counts["observed"]
    selected = [
        (d, p)
        for d, p in zip(decisions, paths, strict=True)
        if d.status == "selected" and p is not None
    ]
    counts["selected_observed"] = len(selected)
    counts["selected_censored"] = counts["selected"] - len(selected)
    facts = dict(
        symbol=symbol,
        fold=number,
        counts=counts,
        decision_sha256=h30.digest(
            h30.encode(
                [
                    [d.opening.isoformat(), d.status, None if d.at is None else d.at.isoformat()]
                    for d in decisions
                ]
            )
        ),
        outcome_mask_sha256=h30.digest(h30.encode([p is not None for p in paths])),
    )
    supported = counts["observed"] >= MIN_SESSIONS and len(selected) >= MIN_TRADES
    if not supported:
        return facts, []
    cells = []
    pools = {}
    for decision, path in selected:
        key = (len(path), (decision.at - decision.opening) // STEP)
        pools[key] = [p for p in paths if p is not None and len(p) == key[0]]
    facts["control_pool_sizes"] = [
        dict(session_bars=n, entry_offset_bars=t, sessions=len(p))
        for (n, t), p in sorted(pools.items())
    ]
    for cost in COSTS:
        cache = {}

        def payoff(path, offset, *, cache=cache, cost=cost):
            key = (path[0].start_ts, offset)
            if key not in cache:
                h30.check_time(deadline)
                signal = path[offset - 1]
                observation = h30.Observation(at=signal.end_ts, signal=signal, features=())
                outcome = h30.Outcome(path[offset:])
                require(outcome.entry > 0 and outcome.exit > 0, "rounded_price")
                gross, fees = replay(observation, outcome, cost, emergency)
                cache[key] = metric(gross, fees, outcome.entry)
            return cache[key]

        orb, controls = [], []
        means = {}
        for decision, path in selected:
            offset = (decision.at - decision.opening) // STEP
            key = (len(path), offset)
            orb.append(payoff(path, offset))
            if key not in means:
                pool = pools[key]
                totals = sum_metrics([payoff(p, offset) for p in pool])
                means[key] = {k: v / len(pool) for k, v in totals.items()}
            controls.append(means[key])
        a, b = sum_metrics(orb), sum_metrics(controls)
        cells.append(
            dict(
                symbol=symbol,
                fold=number,
                cost_bps_per_side=cost,
                trades=len(selected),
                orb=strings(a),
                matched_long=strings(b),
                cash=strings(sum_metrics([])),
                paired_net_bps_delta=str(a["net_bps_sum"] - b["net_bps_sum"]),
            )
        )
    return facts, cells


def failure(scope_hash, reason):
    return dict(
        name=NAME,
        family=FAMILY,
        evidence_grade=GRADE,
        contract_sha256=scope_hash,
        status="failed_all_cells",
        reason=reason,
        folds=[],
        cells=[],
        **dict.fromkeys(FLAGS, False),
    )


def conclusion(cells):
    primary = [c for c in cells if c["cost_bps_per_side"] == 3]
    return (
        "descriptive_criterion_met"
        if all(
            Decimal(c["orb"]["net_bps_sum"]) > 0 and Decimal(c["paired_net_bps_delta"]) > 0
            for c in primary
        )
        else "descriptive_criterion_not_met"
    )


def compare(streams, emergency, deadline, scope_hash, *, schedule=None, replay=sessions.payoff):
    result = failure(scope_hash, None)
    del result["reason"]
    seen = []
    for symbol, bars in streams:
        h30.check_time(deadline)
        require(symbol in SYMBOLS and symbol not in seen, "source_identity")
        seen.append(symbol)
        require(
            bool(bars)
            and all(a.start_ts < b.start_ts for a, b in zip(bars, bars[1:], strict=False)),
            "source_order",
        )
        require(
            all((b.symbol, b.market, b.timeframe) == (symbol, "US", Timeframe.M5) for b in bars),
            "source_identity",
        )
        index = {b.start_ts: b for b in bars}
        calendar = sessions.regular_sessions(bars) if schedule is None else schedule
        for number, part in enumerate(folds(calendar), 1):
            facts, cells = compare_fold(
                symbol, number, index, part, emergency, deadline, replay=replay
            )
            result["folds"].append(facts)
            result["cells"].extend(cells)
    require(set(seen) == set(SYMBOLS), "source_identity")
    if len(result["cells"]) != 12:
        result.update(status="input_unavailable", cells=[], conclusion="insufficient_support")
    else:
        result.update(status="complete", conclusion=conclusion(result["cells"]))
    validate_result(result, scope_hash)
    return result


def validate_result(result, scope_hash):
    expected = failure(scope_hash, None)
    for key in ("name", "family", "evidence_grade", "contract_sha256", *FLAGS):
        require(
            type(result[key]) is type(expected[key]) and result[key] == expected[key],
            "result_identity",
        )
    require(set(result) == (set(expected) - {"reason"}) | {"conclusion"}, "result_fields")
    require(
        [(f["symbol"], f["fold"]) for f in result["folds"]]
        == [(s, f) for s in SYMBOLS for f in (1, 2)],
        "fold_matrix",
    )
    shortfall = False
    for fold in result["folds"]:
        require(type(fold["fold"]) is int, "fold_identity_type")
        counts = fold["counts"]
        require(
            set(counts) == set(COUNTS)
            and all(type(v) is int and 0 <= v <= 250000 for v in counts.values()),
            "support_counts",
        )
        require(
            sum(counts[k] for k in DECISIONS) == counts["sessions"]
            and counts["observed"] + counts["censored"] == counts["sessions"]
            and counts["selected_observed"] + counts["selected_censored"] == counts["selected"]
            and counts["selected_observed"] <= counts["observed"]
            and counts["selected_censored"] <= counts["censored"],
            "support_counts",
        )
        for key in ("decision_sha256", "outcome_mask_sha256"):
            require(re.fullmatch(r"sha256:[0-9a-f]{64}", fold[key]) is not None, "support_hash")
        low = counts["observed"] < MIN_SESSIONS or counts["selected_observed"] < MIN_TRADES
        shortfall |= low
        require(
            set(fold)
            == {"symbol", "fold", "counts", "decision_sha256", "outcome_mask_sha256"}
            | (set() if low else {"control_pool_sizes"}),
            "fold_fields",
        )
        if not low:
            keys = []
            for pool in fold["control_pool_sizes"]:
                require(
                    set(pool) == {"session_bars", "entry_offset_bars", "sessions"}
                    and all(type(v) is int for v in pool.values())
                    and 9 <= pool["session_bars"] <= 78
                    and 7 <= pool["entry_offset_bars"] <= pool["session_bars"] - 2
                    and 1 <= pool["sessions"] <= counts["observed"],
                    "control_pool",
                )
                keys.append((pool["session_bars"], pool["entry_offset_bars"]))
            require(bool(keys) and len(keys) == len(set(keys)), "control_pool")
    if shortfall:
        require(
            result["status"] == "input_unavailable"
            and result["cells"] == []
            and result["conclusion"] == "insufficient_support",
            "shortfall_result",
        )
        return
    require(result["status"] == "complete" and len(result["cells"]) == 12, "cell_matrix")
    keys = []
    previous = {}
    for cell in result["cells"]:
        require(
            set(cell)
            == {
                "symbol",
                "fold",
                "cost_bps_per_side",
                "trades",
                "orb",
                "matched_long",
                "cash",
                "paired_net_bps_delta",
            },
            "cell_fields",
        )
        require(
            type(cell["fold"]) is int and type(cell["cost_bps_per_side"]) is int,
            "cell_identity_type",
        )
        keys.append((cell["symbol"], cell["fold"], cell["cost_bps_per_side"]))
        fold = next(f for f in result["folds"] if (f["symbol"], f["fold"]) == keys[-1][:2])
        require(
            type(cell["trades"]) is int and cell["trades"] == fold["counts"]["selected_observed"],
            "cell_support",
        )
        for candidate in ("orb", "matched_long", "cash"):
            values = cell[candidate]
            require(
                set(values) == set(METRICS)
                and all(isinstance(v, str) and Decimal(v).is_finite() for v in values.values()),
                "metric_fields",
            )
            gross, fees, net, bps = (Decimal(values[k]) for k in METRICS)
            require(fees >= 0 and abs(gross - fees - net) < Decimal("1e-20"), "cell_accounting")
            if candidate == "cash":
                require(all(Decimal(v) == 0 for v in values.values()), "cash_nonzero")
            identity = (cell["symbol"], cell["fold"], candidate)
            if identity in previous:
                prior_gross, prior_fees, prior_net, prior_bps = previous[identity]
                require(
                    gross == prior_gross
                    and fees >= prior_fees
                    and net <= prior_net
                    and bps <= prior_bps
                    and (fees == prior_fees) == (bps == prior_bps),
                    "cross_cost_consistency",
                )
            previous[identity] = (gross, fees, net, bps)
        require(
            Decimal(cell["paired_net_bps_delta"]).is_finite()
            and Decimal(cell["paired_net_bps_delta"])
            == Decimal(cell["orb"]["net_bps_sum"]) - Decimal(cell["matched_long"]["net_bps_sum"]),
            "cell_delta",
        )
    require(keys == [(s, f, c) for s in SYMBOLS for f in (1, 2) for c in COSTS], "cell_matrix")
    require(result["conclusion"] == conclusion(result["cells"]), "result_conclusion")


def worker(root, market, scope_hash, result_path):
    try:
        verify(root, scope_hash)
        require(
            importlib.metadata.version("pandas-market-calendars") == "5.4.0", "calendar_version"
        )
        receipt = h30.within(root, h30.RECEIPT).read_bytes()
        deadline = time.monotonic() + SECONDS
        result = compare(
            h30.load_streams(market, receipt, deadline),
            h30.EmergencyStore(result_path.parent / "emergency.json"),
            deadline,
            scope_hash,
        )
        verify(root, scope_hash)
    except Exception:
        result = failure(scope_hash, "runtime_or_invariant_failure")
    with result_path.open("xb") as handle:
        handle.write(h30.encode(result))
