"""Bounded outcome-informed DEVELOPMENT study; no deployment or selection path.

The CLI supervises a named process. This module adds only the source-specific
30-minute payoff and finite comparison, reusing the loader, model and broker.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path, PurePosixPath

import numpy as np

from thericher_v2.contracts import Bar, OrderIntent, Timeframe
from thericher_v2.data.firstrate_free_intraday_timeframe_mechanics import (
    parse_firstrate_normalization_receipt,
    validate_firstrate_canonical_bars,
)
from thericher_v2.data.local import LocalCsvBarProvider
from thericher_v2.data.provider import BarQuery
from thericher_v2.data.resample import resample_bars
from thericher_v2.execution import (
    EmergencyStore,
    LocalPaperBroker,
    replay_local_paper_account,
    replay_local_paper_realized_pnl,
)
from thericher_v2.research.artifact_paths import (
    ensure_external_artifact_directory,
    reject_repo_artifact_path,
)
from thericher_v2.research.campaign_registry import register_frozen_campaign
from thericher_v2.research.sequence_architecture_models import build_torch_sequence_model
from thericher_v2.research.validation import InMemoryCampaignEventStore

FAMILY = "firstrate-m5-h30-lstm-development-20260921-v1"
SYMBOLS, CONTEXTS, SEEDS, COSTS = ("SPY", "QQQ"), (12, 36), (101, 103), (1, 3, 5)
NAIVES = ("always_flat", "always_long", "previous_bar_direction")
MAX_CONTEXT, HOLD_BARS = 36, 6
STEP, CADENCE = Timeframe.M5.duration, timedelta(hours=1)
HOLD = HOLD_BARS * STEP
TRAIN_CAP, EVAL_CAP = 1024, 256
MIN_TRAIN, MIN_EVAL, TRAIN_BLOCKS, EVAL_BLOCKS = 128, 32, 16, 8
TIMEOUTS = {"cpu": 600, "cuda": 1200}
FIT_SECONDS, EPOCHS, BATCH_SIZE = 60, 8, 128
REPO = Path(__file__).resolve().parents[3]
RECEIPT = Path(
    "data-receipts/firstrate-free-intraday/"
    "firstrate-free-intraday-source-local-normalization-v1.json"
)
PRIOR = (
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
    (
        "research/firstrate-m5-open-open-development-20260921-v1/20260921-proposed-r1/summary.json",
        "2a0d4c9632f569ce2308ddcf306c986591d36cff908cf17562d318327b9a3ce5",
    ),
)
CODE_PATHS = (
    "src/thericher_v2/research/firstrate_m5_h30_lstm_dev_20260921.py",
    "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py",
    "src/thericher_v2/research/sequence_architecture_models.py",
    "src/thericher_v2/execution/local_paper.py",
    "src/thericher_v2/data/local.py",
    "src/thericher_v2/market/resample.py",
    "src/thericher_v2/data/firstrate_free_intraday_timeframe_mechanics.py",
)


class StudyFailure(ValueError):
    """Only fixed source-safe categorical messages may be emitted by this study."""


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def check_time(deadline):
    if time.monotonic() >= deadline:
        raise StudyFailure("budget_exhausted")


def within(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if root not in path.parents:
        raise StudyFailure("path_outside_root")
    return path


def source_root_allowed(root, repo):
    """Pure path policy: exact read-only Docker input mount, or a host external root."""
    if root == PurePosixPath("/app/market_data") and repo == PurePosixPath("/app"):
        return True
    return root != repo and repo not in root.parents


def run_directory(root, label):
    reject_repo_artifact_path(root, REPO)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", label):
        raise StudyFailure("invalid_run_label")
    return within(root, Path("research") / FAMILY / label)


def contract_payload(receipt_bytes):
    specs = parse_firstrate_normalization_receipt(receipt_bytes)
    return {
        "family": FAMILY,
        "evidence_grade": "OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
        "normalization_sha256": digest(receipt_bytes),
        "source_pins": [
            {
                "symbol": s.symbol,
                "sha256": s.canonical_sha256,
                "rows": s.bar_count,
                "timestamps_sha256": s.emitted_timestamp_set_sha256,
            }
            for s in specs
        ],
        "code_sha256": {p: digest((REPO / p).read_bytes()) for p in CODE_PATHS},
        "prior_summaries": [{"path": p, "sha256": "sha256:" + h} for p, h in PRIOR],
        "contexts": list(CONTEXTS),
        "seeds": list(SEEDS),
        "architecture": "lstm",
        "model": {"layers": 1, "hidden_size": 16, "dropout": 0, "head": "linear_scalar"},
        "features": ["close/open-1", "high/open-1", "low/open-1", "log1p(volume)"],
        "scalers": "channel and target scalers refit on scored TRAIN only each fold",
        "linear": {
            "alpha": 1.0,
            "solver": "svd",
            "fit_intercept": True,
            "input": "same channel-scaled context flattened, no second scaler",
        },
        "naives": list(NAIVES),
        "decision_threshold_gross_return_bps": 0,
        "target": "10000*(rounded_open(d+30min)/rounded_open(d)-1)",
        "rounding": "Decimal 0.0001 ROUND_HALF_EVEN",
        "schedule": "hourly UTC decision d; long d.open to d+30min.open then flat to d+60min",
        "always_long_is_buy_and_hold": False,
        "quantity": "1",
        "roundtrip_cash": "10000",
        "cost_bps_per_side": list(COSTS),
        "slippage_bps": 0,
        "split": "ordered source UTC dates: first50%->next25%; first75%->last25%",
        "purge": "train decision+30min < earliest scheduled eval decision-180min",
        "sampling": "hourly full-day grid; evenly spaced indices BEFORE any mask/label",
        "sample_caps": {"train": TRAIN_CAP, "evaluation": EVAL_CAP},
        "eligibility": "common 36 complete adjacent past bars; no context-specific backfill",
        "censoring": "future entry/holding/exit missing or incomplete, after all decisions",
        "minimums": [MIN_TRAIN, MIN_EVAL, TRAIN_BLOCKS, EVAL_BLOCKS],
        "effective_sample": "greedy disjoint fixed36bar history blocks, not eval-label embargo",
        "training": {
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "shuffle": False,
            "optimizer": "AdamW",
            "lr": 0.001,
            "weight_decay": 0.01,
            "betas": [0.9, 0.999],
            "eps": 1e-8,
            "loss": "MSE",
            "precision": "float32",
            "cpu_threads": 1,
        },
        "runtime": {
            "torch": "2.7.0+cu128",
            "cuda": "12.8",
            "device": 0,
            "torch_memory_cap_bytes": 4 * 1024**3,
            "record_actual_runtime": True,
            "cross_runtime_bitwise_claim": False,
            "cublas_workspace_config": ":4096:8",
        },
        "budget": {
            "gpu_fits": 16,
            "ridge_fits": 8,
            "cost_cells": 108,
            "cpu_cells": 60,
            "cuda_cells": 48,
            "phase_seconds": TIMEOUTS,
            "per_gpu_fit_seconds": FIT_SECONDS,
            "max_source_rows": 250000,
            "max_source_bytes": 134217728,
        },
        "failure_semantics": (
            "ANY timeout/fit/parity failure invalidates ALL phase cells; no partial PnL"
        ),
        "unavailable_counts": "retain known fold/cell counts; null means not observed before stop",
        "strongest_kill_test": (
            "reject any TRAIN exit >= first EVAL max36-history start, or any independent "
            "target/fee/broker mismatch at 1/3/5bps; invalidate all phase cells"
        ),
        "shortfall_semantics": (
            "entire named phase input_unavailable; counts retained, no subset fit"
        ),
        "cpu_filtering": "geometry/identity only; PnL never filters contexts/seeds/GPU cells",
        "fit_order": "SPY,QQQ / fold1,2 / context12,36 / seed101,103",
        "report": "per-fold/cell counts, matched-cadence baseline net-dollar deltas, fees, trades",
        "limitations": [
            "already_seen_outcome_informed",
            "source_clock_and_finality_unverified",
            "corporate_actions_unqualified",
            "UTC_dates_not_exchange_sessions",
            "evaluation_histories_dependent",
            "sample_capped_not_full_history",
            "future_censoring_not_live_policy",
            "independent_one_share_trades_not_NAV",
            "fees_only_not_full_execution_costs",
            "no_KIS_parity",
        ],
        "promotion": False,
        "generalization_claim": False,
        "holdout_access": False,
        "retained_weights": "all16_final_epoch8_lstm_fits_after_whole_phase_parity",
        "model_format": "numeric_only_npz_read_allow_pickle_false_plus_hash_bound_config",
        "model_use": "private_development_inference_only_no_execution_consumer",
        "ranking": False,
        "retries": False,
        "early_stopping": False,
        "oom_fallback": False,
    }


def freeze(root, label):
    """Metadata only. Called only after reviewed dispatch, never by preparation."""
    root = ensure_external_artifact_directory(root, REPO)
    payload = contract_payload(within(root, RECEIPT).read_bytes())
    for reference in payload["prior_summaries"]:
        if digest(within(root, reference["path"]).read_bytes()) != reference["sha256"]:
            raise StudyFailure("prior_lineage_mismatch")
    output = run_directory(root, label)
    output.mkdir(parents=True, exist_ok=False)
    raw = encode(payload)
    with (output / "contract.json").open("xb") as handle:
        handle.write(raw)
    register_frozen_campaign(
        contract_hash=digest(raw),
        dataset_hash=digest(encode(payload["source_pins"])),
        split_hash=digest(encode([payload["split"], payload["purge"], payload["sampling"]])),
        cost_model_hash=digest(encode([COSTS, "fees_only", "independent_one_share"])),
        trial_family=FAMILY,
        holdout_access="none",
        artifact_root=root,
        repo_root=REPO,
    )
    return digest(raw)


def verify_contract(root, label, expected):
    output = run_directory(root, label)
    raw = (output / "contract.json").read_bytes()
    receipt = within(root, RECEIPT).read_bytes()
    if digest(raw) != expected or json.loads(raw) != contract_payload(receipt):
        raise StudyFailure("frozen_contract_changed")
    return output, receipt


def load_streams(market_root, receipt, deadline):
    """One verified CSV parse per symbol per phase, independent of matrix size."""
    if not source_root_allowed(Path(market_root).resolve(), REPO):
        raise StudyFailure("market_root_inside_repo")
    for spec in parse_firstrate_normalization_receipt(receipt):
        check_time(deadline)
        path = within(market_root, spec.canonical_market_data_relative_path)
        if spec.bar_count > 250000 or path.stat().st_size > 134217728:
            raise StudyFailure("source_budget")
        if digest(path.read_bytes()) != spec.canonical_sha256:
            raise StudyFailure("source_hash")
        source = LocalCsvBarProvider(path).get_bars(
            BarQuery(symbol=spec.symbol, market=spec.market, timeframe=Timeframe.M1)
        )
        validate_firstrate_canonical_bars(source, spec)
        if digest(path.read_bytes()) != spec.canonical_sha256:
            raise StudyFailure("source_changed")
        bars = resample_bars(source, Timeframe.M5)
        del source
        yield spec.symbol, bars


def sample_grid(times, cap):
    return (
        tuple(times)
        if len(times) <= cap
        else tuple(times[i * (len(times) - 1) // (cap - 1)] for i in range(cap))
    )


def plans(bars):
    dates = sorted({bar.start_ts.date() for bar in bars})
    if len(dates) < 4:
        raise StudyFailure("source_dates_short")
    grids = [
        tuple(datetime.combine(day, datetime.min.time(), UTC) + i * CADENCE for i in range(24))
        for day in dates
    ]
    result = []
    for left, right in ((len(dates) // 2, 3 * len(dates) // 4), (3 * len(dates) // 4, len(dates))):
        evaluation = sample_grid([t for day in grids[left:right] for t in day], EVAL_CAP)
        cutoff = evaluation[0] - MAX_CONTEXT * STEP
        training = sample_grid(
            [t for day in grids[:left] for t in day if t + HOLD < cutoff], TRAIN_CAP
        )
        result.append((training, evaluation, cutoff))
    return tuple(result)


@dataclass(frozen=True)
class Observation:
    at: datetime
    features: tuple = field(repr=False)
    signal: Bar = field(repr=False)


def observe(index, times):
    observations = []
    counts = Counter(scheduled=len(times), eligible=0, past_missing=0, past_incomplete=0)
    for at in times:
        history = [index.get(at - i * STEP) for i in range(MAX_CONTEXT, 0, -1)]
        if any(b is None for b in history):
            counts["past_missing"] += 1
            continue
        if any(not b.complete for b in history):
            counts["past_incomplete"] += 1
            continue
        if any(
            (b.symbol, b.market, b.timeframe) != (history[-1].symbol, "US", Timeframe.M5)
            for b in history
        ):
            raise StudyFailure("past_identity")
        values = tuple(
            (
                float(b.close / b.open - 1),
                float(b.high / b.open - 1),
                float(b.low / b.open - 1),
                math.log1p(float(b.volume)),
            )
            for b in history
        )
        if not all(math.isfinite(v) for row in values for v in row):
            raise StudyFailure("nonfinite_feature")
        observations.append(Observation(at, values, history[-1]))
        counts["eligible"] += 1
    return tuple(observations), dict(counts)


@dataclass(frozen=True)
class Outcome:
    bars: tuple[Bar, ...] = field(repr=False)

    @property
    def entry(self):
        return self.bars[0].open.quantize(Decimal("0.0001"))

    @property
    def exit(self):
        return self.bars[-1].open.quantize(Decimal("0.0001"))

    @property
    def target_bps(self):
        return float((self.exit / self.entry - 1) * 10000)


def outcomes(index, observations):
    result = []
    counts = Counter(
        eligible=len(observations), observed=0, future_entry=0, future_holding_path=0, future_exit=0
    )
    for obs in observations:
        path = tuple(index.get(obs.at + i * STEP) for i in range(HOLD_BARS + 1))
        missing = [i for i, b in enumerate(path) if b is None or not b.complete]
        if missing:
            counts[
                "future_entry"
                if missing[0] == 0
                else "future_exit"
                if missing[0] == HOLD_BARS
                else "future_holding_path"
            ] += 1
            result.append(None)
            continue
        if any(
            (b.symbol, b.market, b.timeframe) != (obs.signal.symbol, "US", Timeframe.M5)
            for b in path
        ):
            raise StudyFailure("outcome_identity")
        outcome = Outcome(path)
        if outcome.entry <= 0 or outcome.exit <= 0:
            raise StudyFailure("rounded_price")
        result.append(outcome)
        counts["observed"] += 1
    return tuple(result), dict(counts)


def blocks(observations):
    end, count = None, 0
    for obs in observations:
        if end is None or obs.at - MAX_CONTEXT * STEP >= end:
            end, count = obs.at, count + 1
    return count


@dataclass(frozen=True)
class PreparedFold:
    symbol: str
    fold: int
    train_x: np.ndarray = field(repr=False)
    eval_x: np.ndarray = field(repr=False)
    train_y: np.ndarray = field(repr=False)
    y_mean: float = field(repr=False)
    y_scale: float = field(repr=False)
    channel_mean: np.ndarray = field(repr=False)
    channel_scale: np.ndarray = field(repr=False)
    evaluation: tuple[Observation, ...] = field(repr=False)
    facts: dict


def prepare_fold(symbol, number, index, plan):
    train_times, eval_times, cutoff = plan
    train_obs, train_counts = observe(index, train_times)
    train_outcomes, train_censor = outcomes(index, train_obs)
    pairs = [(x, y) for x, y in zip(train_obs, train_outcomes, strict=True) if y is not None]
    fit_obs = [x for x, _ in pairs]
    eval_obs, eval_counts = observe(index, eval_times)
    if any(y.bars[-1].start_ts >= cutoff for _, y in pairs):
        raise StudyFailure("train_label_crosses_eval_history")
    if eval_obs and any(
        y.bars[-1].start_ts >= eval_obs[0].at - MAX_CONTEXT * STEP for _, y in pairs
    ):
        raise StudyFailure("train_label_crosses_eval_history")
    facts = {
        "symbol": symbol,
        "fold": number,
        "training_inputs": train_counts,
        "training_outcomes": train_censor,
        "evaluation_inputs": eval_counts,
        "evaluation_outcomes": None,
        "eval_blocks_36": None,
        "train_blocks_36": blocks(fit_obs),
        "strict_train_eval_separation": True,
        "train_supported": len(pairs) >= MIN_TRAIN and blocks(fit_obs) >= TRAIN_BLOCKS,
        "evaluation_histories_may_overlap": True,
    }
    train = np.asarray([x.features for x in fit_obs], dtype=np.float64).reshape(-1, 36, 4)
    evaluation = np.asarray([x.features for x in eval_obs], dtype=np.float64).reshape(-1, 36, 4)
    y = np.asarray([v.target_bps for _, v in pairs], dtype=np.float64)
    mean = train.mean(axis=(0, 1)) if len(train) else np.zeros(4)
    scale = train.std(axis=(0, 1)) if len(train) else np.ones(4)
    scale = np.where(scale == 0, 1.0, scale)
    y_mean, y_scale = (float(y.mean()), float(y.std()) or 1.0) if len(y) else (0.0, 1.0)
    facts["normalizer_sha256"] = digest(
        mean.tobytes() + scale.tobytes() + encode([y_mean, y_scale])
    )
    facts["cohort_sha256"] = digest(
        encode([[x.at.isoformat() for x in fit_obs], [x.at.isoformat() for x in eval_obs]])
        + train.tobytes()
        + evaluation.tobytes()
        + y.tobytes()
    )
    arrays = [
        np.asarray((train - mean) / scale, dtype=np.float32),
        np.asarray((evaluation - mean) / scale, dtype=np.float32),
        np.asarray((y - y_mean) / y_scale, dtype=np.float32),
    ]
    for array in arrays:
        if not np.isfinite(array).all():
            raise StudyFailure("nonfinite_normalization")
        array.setflags(write=False)
    return PreparedFold(symbol, number, *arrays, y_mean, y_scale, mean, scale, eval_obs, facts)


def ridge_predict(fold, context):
    from sklearn.linear_model import Ridge

    model = Ridge(alpha=1.0, solver="svd", fit_intercept=True)
    model.fit(fold.train_x[:, -context:].reshape(len(fold.train_x), -1), fold.train_y)
    return model.predict(fold.eval_x[:, -context:].reshape(len(fold.eval_x), -1))


def configure_cuda():
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise StudyFailure("cublas_workspace_config_mismatch")
    import torch

    if str(torch.__version__) != "2.7.0+cu128" or str(torch.version.cuda) != "12.8":
        raise StudyFailure("runtime_version_mismatch")
    if not torch.cuda.is_available():
        raise StudyFailure("cuda_unavailable")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(1.0, 4 * 1024**3 / total), 0)
    return torch, {
        "torch": str(torch.__version__),
        "cuda": str(torch.version.cuda),
        "cudnn": torch.backends.cudnn.version(),
        "device": torch.cuda.get_device_name(0),
        "cross_runtime_bitwise_claim": False,
        "cublas_workspace_config": os.environ["CUBLAS_WORKSPACE_CONFIG"],
    }


def runtime_identity():
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scikit_learn": importlib.metadata.version("scikit-learn"),
        "torch": importlib.metadata.version("torch"),
    }


def cuda_predictor_factory(fold, deadline, torch, retained):
    # Exactly one CPU tensor materialization per fold, sliced across contexts/seeds.
    train = torch.tensor(fold.train_x, dtype=torch.float32, device="cpu")
    evaluation = torch.tensor(fold.eval_x, dtype=torch.float32, device="cpu")
    labels = torch.tensor(fold.train_y, dtype=torch.float32, device="cpu").unsqueeze(1)

    def predict(context, seed):
        fit_deadline = min(deadline, time.monotonic() + FIT_SECONDS)
        check_time(fit_deadline)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        model = optimizer = features = targets = tensor = None
        try:
            model = build_torch_sequence_model(
                torch=torch,
                architecture_id="lstm",
                feature_count=4,
                hidden_size=16,
                attention_heads=1,
                tcn_kernel_size=3,
            ).to("cuda:0")
            optimizer = torch.optim.AdamW(
                model.parameters(), lr=0.001, weight_decay=0.01, betas=(0.9, 0.999), eps=1e-8
            )
            features = train[:, -context:].to("cuda:0")
            targets = labels.to("cuda:0")
            loss_fn = torch.nn.MSELoss()
            model.train()
            for _ in range(EPOCHS):
                for start in range(0, len(train), BATCH_SIZE):
                    check_time(fit_deadline)
                    optimizer.zero_grad(set_to_none=True)
                    loss = loss_fn(
                        model(features[start : start + BATCH_SIZE]),
                        targets[start : start + BATCH_SIZE],
                    )
                    if not bool(torch.isfinite(loss).item()):
                        raise StudyFailure("nonfinite_loss")
                    loss.backward()
                    optimizer.step()
                    torch.cuda.synchronize()
                    check_time(fit_deadline)
            model.eval()
            with torch.no_grad():
                tensor = evaluation[:, -context:].to("cuda:0")
                predicted = model(tensor).flatten().cpu().numpy()
            torch.cuda.synchronize()
            check_time(fit_deadline)
            retained.append(
                (
                    fold,
                    context,
                    seed,
                    {
                        "state." + key: value.detach().cpu().numpy().copy()
                        for key, value in model.state_dict().items()
                    },
                )
            )
            return predicted
        finally:
            del model, optimizer, features, targets, tensor
            torch.cuda.empty_cache()

    return predict


def roundtrip(obs, outcome, cost, emergency):
    store = InMemoryCampaignEventStore()
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=emergency,
        starting_cash=Decimal(10000),
        fee_bps=Decimal(cost),
        slippage_bps=Decimal(0),
    )
    fills = []
    for side, signal, execution in (
        ("buy", obs.signal, outcome.bars[0]),
        ("sell", outcome.bars[-2], outcome.bars[-1]),
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
            raise StudyFailure("roundtrip_rejected")
        fill = broker.fill_next_bar(side, signal_bar=signal, execution_bar=execution).fill
        if fill is None or fill.source != "local_paper":
            raise StudyFailure("fill_missing")
        fills.append(fill)
    gross = outcome.exit - outcome.entry
    fees = sum(
        ((p * cost / 10000).quantize(Decimal("0.0001")) for p in (outcome.entry, outcome.exit)),
        Decimal(0),
    )
    account = replay_local_paper_account(store, starting_cash=Decimal(10000))
    pnl = replay_local_paper_realized_pnl(store.iter_events())
    if (
        fills[0].filled_at != obs.at
        or fills[1].filled_at != obs.at + HOLD
        or fills[0].price != outcome.entry
        or fills[1].price != outcome.exit
        or sum((f.fee for f in fills), Decimal(0)) != fees
        or account.positions
        or account.cash - 10000 != gross - fees
        or pnl.realized_after_cost_pnl != gross - fees
        or pnl.open_quantity != 0
        or pnl.local_paper_fill_count != 2
    ):
        raise StudyFailure("target_fee_replay_parity")
    return gross, fees


def expected_cells(phase):
    candidates = [("ridge", c, None) for c in CONTEXTS] + [(n, None, None) for n in NAIVES]
    if phase == "cuda":
        candidates = [("lstm", c, seed) for c in CONTEXTS for seed in SEEDS]
    return [
        {
            "symbol": s,
            "fold": f,
            "candidate": name,
            "context": c,
            "seed": seed,
            "cost_bps_per_side": cost,
        }
        for s in SYMBOLS
        for f in (1, 2)
        for name, c, seed in candidates
        for cost in COSTS
    ]


def cell_key(cell):
    return tuple(
        cell[name]
        for name in ("symbol", "fold", "candidate", "context", "seed", "cost_bps_per_side")
    )


def result_base(phase):
    return {
        "family": FAMILY,
        "phase": phase,
        "evidence_grade": "OUTCOME_INFORMED_SEEN_DATA_DEVELOPMENT",
        "promotion": False,
        "generalization_claim": False,
        "holdout_access": False,
        "retained_weights": False,
        "cross_runtime_bitwise_claim": False,
        "pnl_semantics": "independent_one_share_roundtrips_not_continuous_capital",
        "always_long_semantics": "30min_long_30min_flat_not_buy_and_hold",
        "folds": [],
        "cells": [],
        "runtime": None,
    }


def invalidate(result, reason, status="failed_all_phase_cells"):
    result["status"], result["reason"] = status, reason
    result["retained_weights"], result["models"] = False, []
    facts = {(f["symbol"], f["fold"]): f for f in result["folds"]}
    cells = []
    for cell in expected_cells(result["phase"]):
        fold = facts.get((cell["symbol"], cell["fold"]), {})
        eligible = fold.get("evaluation_inputs", {}).get("eligible")
        observed = (fold.get("evaluation_outcomes") or {}).get("observed")
        cells.append(
            {
                **cell,
                "status": "unavailable",
                "reason": reason,
                "eligible_decisions": eligible,
                "scored_decisions": observed,
                "future_censored": (
                    eligible - observed if eligible is not None and observed is not None else None
                ),
            }
        )
    result["cells"] = cells
    return result


STATE_SHAPES = {
    "state.encoder.weight_ih_l0": (64, 4),
    "state.encoder.weight_hh_l0": (64, 16),
    "state.encoder.bias_ih_l0": (64,),
    "state.encoder.bias_hh_l0": (64,),
    "state.head.weight": (1, 16),
    "state.head.bias": (1,),
    "channel_mean": (4,),
    "channel_scale": (4,),
    "target_mean": (1,),
    "target_scale": (1,),
}


def validate_model_arrays(arrays):
    if set(arrays) != set(STATE_SHAPES):
        raise StudyFailure("model_array_keys")
    for name, shape in STATE_SHAPES.items():
        value = arrays[name]
        dtype = np.dtype("float32" if name.startswith("state.") else "float64")
        if value.shape != shape or value.dtype != dtype or not np.isfinite(value).all():
            raise StudyFailure("model_array_geometry_or_finiteness")
    if np.any(arrays["channel_scale"] <= 0) or arrays["target_scale"][0] <= 0:
        raise StudyFailure("model_scaler_invalid")


def load_model_arrays(root, reference, contract_hash):
    """No pickle/code deserialization; exact bounded numeric schema and hash chain."""
    config_bytes = within(root, reference["config_file"]).read_bytes()
    if digest(config_bytes) != reference["config_sha256"]:
        raise StudyFailure("model_config_hash")
    config = json.loads(config_bytes)
    if (
        config["contract_sha256"] != contract_hash
        or config["family"] != FAMILY
        or config["context"] not in CONTEXTS
        or config["seed"] not in SEEDS
        or config["final_epoch"] != EPOCHS
        or config["architecture"] != "lstm"
        or config["symbol"] not in SYMBOLS
        or config["fold"] not in (1, 2)
        or any(reference[key] != config[key] for key in ("symbol", "fold", "context", "seed"))
    ):
        raise StudyFailure("model_config_identity")
    path = within(root, reference["weights_file"])
    if path.stat().st_size > 1024 * 1024:
        raise StudyFailure("model_archive_budget")
    raw = path.read_bytes()
    if digest(raw) != reference["weights_sha256"] or config["weights_sha256"] != digest(raw):
        raise StudyFailure("model_weights_hash")
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        if set(archive.files) != set(STATE_SHAPES) or len(archive.files) != len(STATE_SHAPES):
            raise StudyFailure("model_array_keys")
        arrays = {key: archive[key].copy() for key in archive.files}
    validate_model_arrays(arrays)
    return config, arrays


def save_final_models(root, retained, contract_hash, source_pins, runtime, deadline):
    expected = {
        (s, f, c, seed) for s in SYMBOLS for f in (1, 2) for c in CONTEXTS for seed in SEEDS
    }
    if (
        len(retained) != 16
        or {(f.symbol, f.fold, c, seed) for f, c, seed, _ in retained} != expected
    ):
        raise StudyFailure("final_model_matrix_incomplete")
    root.mkdir(exist_ok=False)
    references = []
    for fold, context, seed, state in retained:
        check_time(deadline)
        arrays = {
            **state,
            "channel_mean": np.asarray(fold.channel_mean, dtype=np.float64),
            "channel_scale": np.asarray(fold.channel_scale, dtype=np.float64),
            "target_mean": np.asarray([fold.y_mean], dtype=np.float64),
            "target_scale": np.asarray([fold.y_scale], dtype=np.float64),
        }
        validate_model_arrays(arrays)
        name = f"{fold.symbol}-f{fold.fold}-c{context}-s{seed}"
        path = root / (name + ".npz")
        # Only the validated numeric arrays reach savez; reads always forbid pickle.
        with path.open("xb") as handle:
            np.savez(handle, **arrays)
        weight_hash = digest(path.read_bytes())
        config = {
            "family": FAMILY,
            "symbol": fold.symbol,
            "fold": fold.fold,
            "context": context,
            "seed": seed,
            "architecture": "lstm",
            "hidden_size": 16,
            "layers": 1,
            "feature_count": 4,
            "final_epoch": EPOCHS,
            "contract_sha256": contract_hash,
            "source_pins": source_pins,
            "cohort_sha256": fold.facts["cohort_sha256"],
            "normalizer_sha256": fold.facts["normalizer_sha256"],
            "runtime": runtime,
            "weights_sha256": weight_hash,
            "private_development_inference_only": True,
            "promotion": False,
        }
        config_bytes = encode(config)
        with (root / (name + ".json")).open("xb") as handle:
            handle.write(config_bytes)
        reference = {
            "symbol": fold.symbol,
            "fold": fold.fold,
            "context": context,
            "seed": seed,
            "weights_file": path.name,
            "weights_sha256": weight_hash,
            "config_file": name + ".json",
            "config_sha256": digest(config_bytes),
        }
        _, loaded = load_model_arrays(root, reference, contract_hash)
        if any(not np.array_equal(arrays[k], loaded[k]) for k in arrays):
            raise StudyFailure("model_roundtrip_mismatch")
        references.append(reference)
    check_time(deadline)
    return references


def restore_predictor(root, reference, contract_hash, torch):
    """Restore only this fixed LSTM for private CPU inference, never an execution adapter."""
    config, arrays = load_model_arrays(root, reference, contract_hash)
    model = build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm",
        feature_count=4,
        hidden_size=16,
        attention_heads=1,
        tcn_kernel_size=3,
    )
    model.load_state_dict(
        {
            k.removeprefix("state."): torch.from_numpy(v)
            for k, v in arrays.items()
            if k.startswith("state.")
        },
        strict=True,
    )
    model.eval()

    def predict(features):
        values = np.asarray(features, dtype=np.float64)
        if values.ndim != 3 or values.shape[1:] != (config["context"], 4):
            raise StudyFailure("inference_geometry")
        normalized = ((values - arrays["channel_mean"]) / arrays["channel_scale"]).astype("float32")
        if not np.isfinite(normalized).all():
            raise StudyFailure("inference_nonfinite")
        with torch.no_grad():
            predictions = model(torch.from_numpy(normalized)).flatten().numpy()
        predictions = predictions * arrays["target_scale"][0] + arrays["target_mean"][0]
        if not np.isfinite(predictions).all():
            raise StudyFailure("inference_nonfinite")
        return predictions

    return predict


def score(fold, index, signals, emergency, deadline):
    attached, counts = outcomes(index, fold.evaluation)
    supported = [obs for obs, y in zip(fold.evaluation, attached, strict=True) if y is not None]
    facts = {
        **fold.facts,
        "evaluation_outcomes": counts,
        "eval_blocks_36": blocks(supported),
        "evaluation_utc_dates": len({obs.at.date() for obs in supported}),
        "outcome_mask_sha256": digest(encode([y is not None for y in attached])),
    }
    if counts["observed"] < MIN_EVAL or blocks(supported) < EVAL_BLOCKS:
        return facts, None
    cells = []
    for cost in COSTS:
        payoffs = []
        for obs, outcome in zip(fold.evaluation, attached, strict=True):
            check_time(deadline)
            payoffs.append(None if outcome is None else roundtrip(obs, outcome, cost, emergency))
        for (candidate, context, seed), flags in signals.items():
            if len(flags) != len(attached):
                raise StudyFailure("prediction_cardinality")
            values = [p for p, flag in zip(payoffs, flags, strict=True) if p is not None and flag]
            gross, fees = (sum((p[i] for p in values), Decimal(0)) for i in (0, 1))
            cells.append(
                {
                    "symbol": fold.symbol,
                    "fold": fold.fold,
                    "candidate": candidate,
                    "context": context,
                    "seed": seed,
                    "cost_bps_per_side": cost,
                    "status": "complete",
                    "eligible_decisions": len(attached),
                    "scored_decisions": len(supported),
                    "future_censored": len(attached) - len(supported),
                    "long_intents": sum(flags),
                    "long_censored": sum(
                        flag and y is None for flag, y in zip(flags, attached, strict=True)
                    ),
                    "trades": len(values),
                    "gross_dollars": str(gross),
                    "fees_dollars": str(fees),
                    "net_dollars": str(gross - fees),
                    "parity_verified": True,
                    "terminal_flat": True,
                    "fill_source": "local_paper",
                }
            )
    return facts, cells


def bind_cpu_summary(summary, contract_hash):
    if (
        summary.get("status") != "complete"
        or summary.get("phase") != "cpu"
        or summary.get("contract_sha256") != contract_hash
        or summary.get("family") != FAMILY
        or {cell_key(c) for c in summary.get("cells", [])}
        != {cell_key(c) for c in expected_cells("cpu")}
        or len(summary["cells"]) != 60
        or any(c["status"] != "complete" for c in summary["cells"])
    ):
        raise StudyFailure("cpu_identity_or_geometry_unavailable")
    return summary


def add_deltas(cells, baseline_cells):
    lookup = {cell_key(c): c for c in baseline_cells}
    for cell in cells:
        if cell["candidate"] not in {"ridge", "lstm"}:
            continue
        names = list(NAIVES) + (["ridge"] if cell["candidate"] == "lstm" else [])
        cell["matched_baseline_delta_net_dollars"] = {}
        for name in names:
            key = (
                cell["symbol"],
                cell["fold"],
                name,
                cell["context"] if name == "ridge" else None,
                None,
                cell["cost_bps_per_side"],
            )
            baseline = lookup[key]
            if any(
                cell[k] != baseline[k]
                for k in ("eligible_decisions", "scored_decisions", "future_censored")
            ):
                raise StudyFailure("baseline_cohort_mismatch")
            cell["matched_baseline_delta_net_dollars"][name] = str(
                Decimal(cell["net_dollars"]) - Decimal(baseline["net_dollars"])
            )


def compare(
    streams,
    phase,
    emergency,
    deadline,
    *,
    cpu_summary=None,
    ridge_predictor=None,
    cuda_factory=None,
    runtime=None,
):
    """Fixture injection is internal only; CLI never accepts trainer overrides."""
    result = result_base(phase)
    result["runtime"] = runtime
    prepared = []
    try:
        for symbol, bars in streams:
            check_time(deadline)
            index = {b.start_ts: b for b in bars}
            if len(index) != len(bars) or list(index) != sorted(index):
                raise StudyFailure("duplicate_or_unordered_source")
            for number, plan in enumerate(plans(bars), 1):
                fold = prepare_fold(symbol, number, index, plan)
                prepared.append((fold, index))
        if [(p.symbol, p.fold) for p, _ in prepared] != [(s, f) for s in SYMBOLS for f in (1, 2)]:
            raise StudyFailure("fold_matrix_mismatch")
        result["folds"] = [p.facts for p, _ in prepared]
        if any(not p.facts["train_supported"] for p, _ in prepared):
            for p, index in prepared:
                attached, counts = outcomes(index, p.evaluation)
                p.facts["evaluation_outcomes"] = counts
                p.facts["eval_blocks_36"] = blocks(
                    [obs for obs, y in zip(p.evaluation, attached, strict=True) if y is not None]
                )
            return invalidate(result, "training_support_shortfall", "input_unavailable")
        prior_folds = (
            {(f["symbol"], f["fold"]): f for f in cpu_summary["folds"]}
            if cpu_summary is not None
            else {}
        )
        for row, (fold, index) in enumerate(prepared):
            check_time(deadline)
            signals = {}
            predictor = None
            if phase == "cuda":
                prior = prior_folds[(fold.symbol, fold.fold)]
                for key in ("cohort_sha256", "normalizer_sha256"):
                    if prior[key] != fold.facts[key]:
                        raise StudyFailure("cpu_cuda_cohort_mismatch")
                predictor = cuda_factory(fold, deadline)
            for context in CONTEXTS:
                for seed in SEEDS if phase == "cuda" else (None,):
                    check_time(deadline)
                    predicted = (
                        predictor(context, seed)
                        if phase == "cuda"
                        else (ridge_predictor or ridge_predict)(fold, context)
                    )
                    predicted = np.asarray(predicted, dtype=np.float64)
                    if (
                        predicted.shape != (len(fold.evaluation),)
                        or not np.isfinite(predicted).all()
                    ):
                        raise StudyFailure("nonfinite_or_mismatched_prediction")
                    signals[("lstm" if phase == "cuda" else "ridge", context, seed)] = tuple(
                        bool(v > 0) for v in predicted * fold.y_scale + fold.y_mean
                    )
            if phase == "cpu":
                signals.update(
                    {
                        ("always_flat", None, None): (False,) * len(fold.evaluation),
                        ("always_long", None, None): (True,) * len(fold.evaluation),
                        ("previous_bar_direction", None, None): tuple(
                            x.signal.close > x.signal.open for x in fold.evaluation
                        ),
                    }
                )
            facts, cells = score(fold, index, signals, emergency, deadline)
            result["folds"][row] = facts
            if cells is None:
                return invalidate(result, "evaluation_support_shortfall", "input_unavailable")
            if phase == "cuda" and facts["outcome_mask_sha256"] != prior["outcome_mask_sha256"]:
                raise StudyFailure("cpu_cuda_outcome_mask_mismatch")
            result["cells"].extend(cells)
        if {cell_key(c) for c in result["cells"]} != {cell_key(c) for c in expected_cells(phase)}:
            raise StudyFailure("cell_matrix_mismatch")
        add_deltas(result["cells"], cpu_summary["cells"] if phase == "cuda" else result["cells"])
        check_time(deadline)
        result["status"] = "complete"
        return result
    except StudyFailure as error:
        return invalidate(result, str(error))
    except Exception:
        return invalidate(result, "runtime_or_source_failure_no_fallback")


def worker_entry(market_root, root, label, contract_hash, phase, cpu_hash, result_path):
    """Child-only entry point; all exceptions yield categorical, metric-free failure."""
    from threadpoolctl import threadpool_limits

    result = result_base(phase)
    deadline = time.monotonic() + TIMEOUTS[phase]
    try:
        output, receipt = verify_contract(root, label, contract_hash)
        cpu = None
        if phase == "cuda":
            raw = (output / "cpu-summary.json").read_bytes()
            if digest(raw) != cpu_hash:
                raise StudyFailure("cpu_summary_hash_mismatch")
            cpu = bind_cpu_summary(json.loads(raw), contract_hash)
        environment = runtime_identity()
        if cpu is not None and cpu["runtime"]["environment"] != environment:
            raise StudyFailure("cpu_cuda_runtime_mismatch")
        torch, runtime = (
            configure_cuda()
            if phase == "cuda"
            else (None, {"numpy": np.__version__, "backend": "cpu"})
        )
        runtime["environment"] = environment
        retained = []
        with threadpool_limits(limits=1):
            result = compare(
                load_streams(market_root, receipt, deadline),
                phase,
                EmergencyStore(Path(result_path).parent / "emergency.json"),
                deadline,
                cpu_summary=cpu,
                runtime=runtime,
                cuda_factory=lambda fold, end: cuda_predictor_factory(fold, end, torch, retained),
            )
        if phase == "cuda" and result["status"] == "complete":
            payload = json.loads((output / "contract.json").read_bytes())
            result["models"] = save_final_models(
                Path(result_path).parent / "models",
                retained,
                contract_hash,
                payload["source_pins"],
                runtime,
                deadline,
            )
            result["retained_weights"] = True
        check_time(deadline)
    except StudyFailure as error:
        result = invalidate(result, str(error))
    except Exception:
        result = invalidate(result, "runtime_or_source_failure_no_fallback")
    result["contract_sha256"] = contract_hash
    result["cpu_summary_sha256"] = cpu_hash
    with Path(result_path).open("xb") as handle:
        handle.write(encode(result))
