"""One frozen, source-local DEVELOPMENT comparison; never a promotion consumer.

Only ``run_frozen`` reads retained bars. ``freeze`` reads source-safe metadata.
Features/intent eligibility are deliberately separate from outcome attachment.
No rows, estimator, predictions, or local simulation events are persisted.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Bar, OrderIntent, Timeframe
from thericher_v2.data.firstrate_free_intraday_timeframe_mechanics import (
    parse_firstrate_normalization_receipt,
    validate_firstrate_canonical_bars,
)
from thericher_v2.data.local import LocalCsvBarProvider
from thericher_v2.data.provider import BarQuery
from thericher_v2.data.resample import resample_bars
from thericher_v2.execution import (
    LOCAL_PAPER_SOURCE,
    EmergencyStore,
    LocalPaperBroker,
    replay_local_paper_account,
    replay_local_paper_realized_pnl,
)
from thericher_v2.research.validation import InMemoryCampaignEventStore

FAMILY = "firstrate-m5-open-open-development-20260921-v1"
SYMBOLS = ("SPY", "QQQ")
CANDIDATES = ("sma20_gt_sma60", "ridge_l2", "previous_bar_direction", "always_flat")
COSTS = (1, 3, 5)
WINDOW = 60
TRAIN_CAP = 1024
EVAL_CAP = 256
MIN_TRAIN = 32
MIN_EVAL = 16
MIN_BLOCKS = 2
WALL_SECONDS = 600
STEP = Timeframe.M5.duration
GRID = timedelta(minutes=10)
REPO = Path(__file__).resolve().parents[3]
RECEIPT = Path(
    "data-receipts/firstrate-free-intraday/"
    "firstrate-free-intraday-source-local-normalization-v1.json"
)
PRIOR_RESULTS = (
    (
        "firstrate-5m-after-cost-control-v1/20260820-r2/summary.json",
        "249a55dc53605e5381cfbaaef370ce9d36302c93594abc421a65b6685857fb2c",
    ),
    (
        "firstrate-m5-trend-rule-after-cost-control-v1/20260820-r1/summary.json",
        "539463a0d6cb84ba16fd75e750493277adc5e9f00f94a5e51f00d1cb44a78d00",
    ),
    (
        "firstrate-m5-mean-reversion-after-cost-control-v1/20260820-r1/summary.json",
        "b437e8e39e9cb3963e13bf4778daee7e92d0de6c32cec6e9dac24e462f16266f",
    ),
)


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _encode(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _external(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise ValueError("external_root_required")
    return resolved


def _within(root: Path, relative: Path) -> Path:
    path = (root / relative).resolve()
    if root not in path.parents:
        raise ValueError("path_outside_root")
    return path


def _run_dir(root: Path, label: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", label):
        raise ValueError("invalid_run_label")
    return _within(_external(root), Path("research") / FAMILY / label)


def proposed_contract(receipt_bytes: bytes) -> dict[str, object]:
    specs = parse_firstrate_normalization_receipt(receipt_bytes)
    return {
        "family": FAMILY,
        "evidence_grade": "DEVELOPMENT_ONLY_ALREADY_SEEN",
        "implementation_sha256": sha256(Path(__file__).read_bytes()),
        "normalization_receipt_sha256": sha256(receipt_bytes),
        "sources": [
            {
                "symbol": s.symbol,
                "canonical_sha256": s.canonical_sha256,
                "bar_count": s.bar_count,
                "timestamp_sha256": s.emitted_timestamp_set_sha256,
            }
            for s in specs
        ],
        "prior_rejected_results": [
            {"relative_path": path, "sha256": "sha256:" + digest, "result": "rejected"}
            for path, digest in PRIOR_RESULTS
        ],
        "observation_windows_m5": [WINDOW],
        "candidates": list(CANDIDATES),
        "feature": "SMA20(close)/SMA60(close)-1; complete contiguous past only",
        "ridge": {
            "alpha": 1.0,
            "solver": "svd",
            "fit_intercept": True,
            "scaler": "training_only_StandardScaler",
            "long_when": "prediction>0",
        },
        "target": "rounded_open(t+2)/rounded_open(t+1)-1",
        "rounding": "LocalPaperBroker Decimal 0.0001 ROUND_HALF_EVEN",
        "execution": "t.end decision; t+1.open entry; t+2.open mandatory exit",
        "quantity": "1",
        "starting_cash_each_independent_roundtrip": "10000",
        "fees_bps_per_side": list(COSTS),
        "slippage_bps": 0,
        "folds": [[0, 50, 75], [0, 75, 100]],
        "fold_axis": "ordered UTC source dates, floor percentage boundaries",
        "sampling": "full 10minute UTC grid on source dates, evenly spaced indices before masks",
        "training_timestamp_cap": TRAIN_CAP,
        "evaluation_timestamp_cap": EVAL_CAP,
        "purge": "training following-open strictly before eval start minus 60 M5 bars",
        "input_eligibility": "past 60 complete adjacent M5 bars, no imputation or price mask",
        "outcome_censoring": "missing/incomplete entry or exit bar; never an intent mask",
        "minimums": {
            "fit_scored": MIN_TRAIN,
            "eval_scored": MIN_EVAL,
            "nonoverlapping_observation_blocks_per_partition": MIN_BLOCKS,
        },
        "effective_sample": "greedy disjoint 60bar history intervals; also report UTC date count",
        "budget": {
            "fits": 4,
            "cells": 48,
            "wall_seconds": WALL_SECONDS,
            "cpu_threads": 1,
            "max_m1_rows_per_symbol": 250000,
            "max_source_bytes": 134217728,
            "search": False,
            "retry": False,
        },
        "metrics": [
            "gross_pnl",
            "net_pnl",
            "fees",
            "net_bps_sum",
            "trades",
            "nonoverlap_blocks",
            "eligibility_counts",
            "outcome_censoring_counts",
        ],
        "kill_test": "future-invariant inputs/decisions AND exact target/broker/accounting parity",
        "limitations": [
            "source_clock_and_bar_boundary_unverified",
            "not_point_in_time",
            "provider_finality_not_observed",
            "corporate_actions_unqualified",
            "UTC_dates_not_exchange_sessions",
            "gaps_and_zero_volume_omissions",
            "censored_payoffs_not_a_live_missing_data_policy",
            "sample_caps_are_not_full_history_results",
            "no_KIS_parity",
            "overlapping_training_and_history_not_independent_samples",
        ],
        "holdout_access": False,
        "promotion": False,
        "generalization_claim": False,
        "independent_performance_claim": False,
        "retained_weights": False,
        "rank_or_select_winner": False,
    }


def freeze(*, artifact_root: Path, run_label: str) -> str:
    """Create a metadata-only contract; do not open canonical market files."""
    root = _external(artifact_root)
    contract = proposed_contract(_within(root, RECEIPT).read_bytes())
    output = _run_dir(root, run_label)
    output.mkdir(parents=True, exist_ok=False)
    payload = _encode(contract)
    with (output / "contract.json").open("xb") as handle:
        handle.write(payload)
    return sha256(payload)


@dataclass(frozen=True)
class Observation:
    decision_end: datetime
    history_start: datetime
    feature: float
    rule_long: bool
    previous_long: bool
    signal_bar: Bar


@dataclass(frozen=True)
class Outcome:
    entry_bar: Bar
    exit_bar: Bar

    @property
    def entry_open(self) -> Decimal:
        return self.entry_bar.open.quantize(Decimal("0.0001"))

    @property
    def exit_open(self) -> Decimal:
        return self.exit_bar.open.quantize(Decimal("0.0001"))

    @property
    def target(self) -> float:
        return float(self.exit_open / self.entry_open - 1)


def past_observation(
    bars_by_start: Mapping[datetime, Bar], decision_end: datetime
) -> tuple[Observation | None, str]:
    """This function never looks up an entry or exit timestamp."""
    history = [bars_by_start.get(decision_end - STEP * i) for i in range(WINDOW, 0, -1)]
    if any(bar is None for bar in history):
        return None, "past_missing"
    if any(not bar.complete for bar in history):
        return None, "past_incomplete"
    if any(bar.timeframe != Timeframe.M5 for bar in history):
        raise ValueError("past_timeframe_mismatch")
    latest = history[-1]
    if any((b.symbol, b.market) != (latest.symbol, latest.market) for b in history):
        raise ValueError("past_identity_mismatch")
    short = sum((b.close for b in history[-20:]), Decimal(0)) / 20
    long = sum((b.close for b in history), Decimal(0)) / WINDOW
    feature = float(short / long - 1)
    if not math.isfinite(feature):
        raise ValueError("nonfinite_feature")
    return Observation(
        decision_end,
        decision_end - WINDOW * STEP,
        feature,
        short > long,
        latest.close > latest.open,
        latest,
    ), "eligible"


def attach_outcome(
    bars_by_start: Mapping[datetime, Bar], observation: Observation
) -> tuple[Outcome | None, str]:
    entry = bars_by_start.get(observation.decision_end)
    if entry is None or not entry.complete:
        return None, "future_entry_missing_or_incomplete"
    exit_bar = bars_by_start.get(observation.decision_end + STEP)
    if exit_bar is None or not exit_bar.complete:
        return None, "future_exit_missing_or_incomplete"
    for bar in (entry, exit_bar):
        if (bar.symbol, bar.market, bar.timeframe) != (
            observation.signal_bar.symbol,
            observation.signal_bar.market,
            Timeframe.M5,
        ):
            raise ValueError("outcome_identity_mismatch")
    outcome = Outcome(entry, exit_bar)
    if outcome.entry_open <= 0 or outcome.exit_open <= 0:
        raise ValueError("rounded_open_nonpositive")
    return outcome, "observed"


def _sample(times: Sequence[datetime], cap: int) -> tuple[datetime, ...]:
    if len(times) <= cap:
        return tuple(times)
    return tuple(times[i * (len(times) - 1) // (cap - 1)] for i in range(cap))


def fold_schedules(bars: Sequence[Bar]) -> tuple[tuple[tuple, tuple, datetime], ...]:
    """Freeze grids by source dates, before consulting masks or labels."""
    dates = sorted({bar.start_ts.date() for bar in bars})
    if len(dates) < 4:
        return ()
    grids = [
        tuple(datetime.combine(day, datetime.min.time(), UTC) + GRID * i for i in range(144))
        for day in dates
    ]
    folds = []
    for start, stop in ((len(dates) // 2, 3 * len(dates) // 4), (3 * len(dates) // 4, len(dates))):
        evaluation = _sample([t for day in grids[start:stop] for t in day], EVAL_CAP)
        cutoff = evaluation[0] - WINDOW * STEP
        training = _sample(
            [t for day in grids[:start] for t in day if t + STEP < cutoff], TRAIN_CAP
        )
        folds.append((training, evaluation, cutoff))
    return tuple(folds)


def _observations(index: Mapping[datetime, Bar], times: Sequence[datetime]):
    observations = []
    counts = Counter(
        {"scheduled": len(times), "eligible": 0, "past_missing": 0, "past_incomplete": 0}
    )
    for timestamp in times:
        observation, reason = past_observation(index, timestamp)
        counts[reason] += 1
        if observation is not None:
            observations.append(observation)
    return observations, dict(counts)


def _outcomes(index: Mapping[datetime, Bar], observations: Sequence[Observation]):
    outcomes = []
    counts = Counter(
        {
            "eligible": len(observations),
            "observed": 0,
            "future_entry_missing_or_incomplete": 0,
            "future_exit_missing_or_incomplete": 0,
        }
    )
    for observation in observations:
        outcome, reason = attach_outcome(index, observation)
        outcomes.append(outcome)
        counts[reason] += 1
    return outcomes, dict(counts)


def disjoint_blocks(observations: Sequence[Observation]) -> int:
    end = None
    count = 0
    for observation in sorted(observations, key=lambda item: item.history_start):
        if end is None or observation.history_start >= end:
            count += 1
            end = observation.decision_end
    return count


def fit_control(observations: Sequence[Observation], outcomes: Sequence[Outcome]):
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0, solver="svd", fit_intercept=True))
    model.fit([[item.feature] for item in observations], [item.target for item in outcomes])
    return model


def decisions(observations: Sequence[Observation], model) -> dict[str, tuple[bool, ...]]:
    predictions = model.predict([[item.feature] for item in observations]) if observations else []
    if any(not math.isfinite(value) for value in predictions):
        raise ValueError("nonfinite_prediction")
    return {
        "sma20_gt_sma60": tuple(item.rule_long for item in observations),
        "ridge_l2": tuple(bool(value > 0) for value in predictions),
        "previous_bar_direction": tuple(item.previous_long for item in observations),
        "always_flat": tuple(False for _ in observations),
    }


def replay_roundtrip(
    observation: Observation, outcome: Outcome, cost: int, emergency: EmergencyStore
) -> tuple[Decimal, Decimal, Decimal]:
    """Bounded isolated one-share payoff, not a chained-capital strategy claim."""
    if cost not in COSTS:
        raise ValueError("unfrozen_cost")
    store = InMemoryCampaignEventStore()
    cash = Decimal("10000")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=emergency,
        starting_cash=cash,
        fee_bps=Decimal(cost),
        slippage_bps=Decimal(0),
    )
    fills = []
    for side, signal, execution in (
        ("buy", observation.signal_bar, outcome.entry_bar),
        ("sell", outcome.entry_bar, outcome.exit_bar),
    ):
        order = OrderIntent(
            client_order_id=side,
            symbol=signal.symbol,
            market=signal.market,
            side=side,
            quantity=Decimal(1),
            limit_price=None,
            decision_id=side,
            created_at=signal.end_ts,
        )
        if broker.submit_order(order).status != "accepted":
            raise ValueError("local_roundtrip_rejected")
        result = broker.fill_next_bar(side, signal_bar=signal, execution_bar=execution)
        if result.fill is None or result.fill.source != LOCAL_PAPER_SOURCE:
            raise ValueError("local_fill_missing")
        fills.append(result.fill)
    gross = outcome.exit_open - outcome.entry_open
    fee = sum(
        (
            (price * cost / 10000).quantize(Decimal("0.0001"))
            for price in (outcome.entry_open, outcome.exit_open)
        ),
        Decimal(0),
    )
    account = replay_local_paper_account(store, starting_cash=cash)
    pnl = replay_local_paper_realized_pnl(store.iter_events())
    if (
        fills[0].price != outcome.entry_open
        or fills[1].price != outcome.exit_open
        or fills[0].filled_at != observation.decision_end
        or fills[1].filled_at != observation.decision_end + STEP
        or fills[0].fee + fills[1].fee != fee
        or account.positions
        or account.cash - cash != gross - fee
        or pnl.realized_after_cost_pnl != gross - fee
        or pnl.open_quantity != 0
        or pnl.local_paper_fill_count != 2
    ):
        raise ValueError("target_replay_parity_failed")
    return gross, fee, (gross - fee) / outcome.entry_open * 10000


def _check_time(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError("family_cpu_budget_exhausted")


def compare_stream(bars: Sequence[Bar], emergency: EmergencyStore, *, deadline: float):
    """Run both folds; call only with synthetic fixtures or dispatched frozen data."""
    index = {bar.start_ts: bar for bar in bars}
    if len(index) != len(bars) or list(index) != sorted(index):
        raise ValueError("duplicate_or_unordered_bars")
    results = []
    for fold_id, (train_times, eval_times, cutoff) in enumerate(fold_schedules(bars), 1):
        _check_time(deadline)
        train_obs, train_inputs = _observations(index, train_times)
        train_y, train_censoring = _outcomes(index, train_obs)
        pairs = [(x, y) for x, y in zip(train_obs, train_y, strict=True) if y is not None]
        fit_x, fit_y = [x for x, _ in pairs], [y for _, y in pairs]
        eval_obs, eval_inputs = _observations(index, eval_times)
        record = {
            "fold": fold_id,
            "evidence_grade": "DEVELOPMENT_ONLY_ALREADY_SEEN",
            "training_inputs": train_inputs,
            "training_outcomes": train_censoring,
            "evaluation_inputs": eval_inputs,
            "training_nonoverlap_blocks": disjoint_blocks(fit_x),
            "fit_count": len(fit_x),
            "cells": [],
        }
        if any(y.exit_bar.start_ts >= cutoff for y in fit_y):
            raise ValueError("training_outcome_crosses_purge")
        if eval_obs and any(
            y.exit_bar.start_ts >= min(x.history_start for x in eval_obs) for y in fit_y
        ):
            raise ValueError("training_label_overlaps_evaluation_history")
        record["strict_label_history_separation"] = True
        if len(fit_x) < MIN_TRAIN or disjoint_blocks(fit_x) < MIN_BLOCKS:
            record["status"] = "input_unavailable_training_support"
            results.append(record)
            continue
        model = fit_control(fit_x, fit_y)
        signals = decisions(eval_obs, model)
        # Evaluation outcomes are attached only after every eligible decision exists.
        eval_y, eval_censoring = _outcomes(index, eval_obs)
        scored_obs = [x for x, y in zip(eval_obs, eval_y, strict=True) if y is not None]
        record.update(
            {
                "evaluation_outcomes": eval_censoring,
                "evaluation_nonoverlap_blocks": disjoint_blocks(scored_obs),
                "evaluation_utc_dates": len({x.decision_end.date() for x in scored_obs}),
            }
        )
        if len(scored_obs) < MIN_EVAL or disjoint_blocks(scored_obs) < MIN_BLOCKS:
            record["status"] = "input_unavailable_evaluation_support"
            results.append(record)
            continue
        for cost in COSTS:
            payoffs = {}
            for i, (observation, outcome) in enumerate(zip(eval_obs, eval_y, strict=True)):
                _check_time(deadline)
                if outcome is not None and any(signals[c][i] for c in CANDIDATES):
                    payoffs[i] = replay_roundtrip(observation, outcome, cost, emergency)
            for candidate in CANDIDATES:
                active = signals[candidate]
                scored = [payoffs[i] for i in payoffs if active[i]]
                gross = sum((p[0] for p in scored), Decimal(0))
                fees = sum((p[1] for p in scored), Decimal(0))
                record["cells"].append(
                    {
                        "candidate": candidate,
                        "cost_bps_per_side": cost,
                        "eligible_decisions": len(eval_obs),
                        "scored_decisions": len(scored_obs),
                        "long_intents_before_censoring": sum(active),
                        "long_intents_censored": sum(
                            flag and outcome is None
                            for flag, outcome in zip(active, eval_y, strict=True)
                        ),
                        "trades": len(scored),
                        "gross_pnl": str(gross),
                        "fees": str(fees),
                        "net_pnl": str(gross - fees),
                        "net_bps_sum": str(sum((p[2] for p in scored), Decimal(0))),
                        "fill_source": LOCAL_PAPER_SOURCE,
                        "parity_verified": True,
                        "terminal_flat": True,
                    }
                )
        record["status"] = "development_complete"
        results.append(record)
    return results


def run_frozen(
    *, market_data_root: Path, artifact_root: Path, run_label: str, contract_sha256: str
) -> dict[str, object]:
    """Explicit offline dispatch boundary. No automatic freeze or real-data retry."""
    from threadpoolctl import threadpool_limits

    root, market = _external(artifact_root), _external(market_data_root)
    output = _run_dir(root, run_label)
    contract_bytes = (output / "contract.json").read_bytes()
    receipt_bytes = _within(root, RECEIPT).read_bytes()
    if sha256(contract_bytes) != contract_sha256 or json.loads(contract_bytes) != proposed_contract(
        receipt_bytes
    ):
        raise ValueError("frozen_contract_changed")
    # Exclusive namespace ownership preserves failed attempts, not an approval gate.
    with (output / "run-started.json").open("xb") as handle:
        handle.write(_encode({"contract_sha256": contract_sha256, "family": FAMILY}))
    summary = {
        "family": FAMILY,
        "contract_sha256": contract_sha256,
        "evidence_grade": "DEVELOPMENT_ONLY_ALREADY_SEEN",
        "promotion": False,
        "generalization_claim": False,
        "independent_performance_claim": False,
        "holdout_access": False,
        "retained_weights": False,
        "streams": [],
    }
    deadline = time.monotonic() + WALL_SECONDS
    try:
        specs = parse_firstrate_normalization_receipt(receipt_bytes)
        with tempfile.TemporaryDirectory(prefix="offline-", dir=output) as temporary:
            emergency = EmergencyStore(Path(temporary) / "emergency.json")
            with threadpool_limits(limits=1):
                for spec in specs:
                    _check_time(deadline)
                    path = _within(market, spec.canonical_market_data_relative_path)
                    if spec.bar_count > 250000 or path.stat().st_size > 134217728:
                        raise ValueError("source_exceeds_frozen_budget")
                    if sha256(path.read_bytes()) != spec.canonical_sha256:
                        raise ValueError("source_hash_mismatch")
                    source = LocalCsvBarProvider(path).get_bars(
                        BarQuery(symbol=spec.symbol, market=spec.market, timeframe=Timeframe.M1)
                    )
                    validate_firstrate_canonical_bars(source, spec)
                    if sha256(path.read_bytes()) != spec.canonical_sha256:
                        raise ValueError("source_changed_during_read")
                    bars = resample_bars(source, Timeframe.M5)
                    del source
                    folds = compare_stream(bars, emergency, deadline=deadline)
                    _check_time(deadline)
                    summary["streams"].append(
                        {"symbol": spec.symbol, "m5_count": len(bars), "folds": folds}
                    )
        complete = all(
            len(s["folds"]) == 2 and all(f["status"] == "development_complete" for f in s["folds"])
            for s in summary["streams"]
        )
        summary["status"] = "development_complete" if complete else "input_unavailable"
    except (ValueError, OSError, TimeoutError, ArithmeticError):
        # Never disclose exception text, paths from malformed input, or provider rows.
        summary["status"] = "failed_no_comparative_result"
        summary["streams"] = []
    with (output / "summary.json").open("xb") as handle:
        handle.write(_encode(summary))
    return summary
