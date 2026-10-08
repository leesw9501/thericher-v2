"""Frozen KIS five-session risk development; parent owns GPU lease/containment.

No credentials, provider, network, broker, registration or public model code.
Cached predictions are immutable model-bound evidence, not fresh model inference
in readback. Logical past selection is not physically target-isolated byte IO.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import io
import json
import math
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

from thericher_v2.research import kis_cross_asset_monthly_momentum as base
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable

NAME = "kis-cross-asset-daily-risk-development-v1"
REPO = Path(__file__).resolve().parents[3]
SECONDS, VERIFY_SECONDS, SEED, UPDATES = 300, 120, 101, 512
CANDIDATES = ("hgb", "attention", "blend")
CONTROLS = ("cash", "five_session_balanced", "buyhold", "train_prior")
POLICIES = CANDIDATES + CONTROLS
COSTS = base.COSTS
RUNTIME = dict(base.RUNTIME, **{"numpy": "2.5.1", "scikit-learn": "1.9.1",
                              "torch": "2.7.0+cu128", "cuda": "12.8",
                              "safetensors": "0.8.0"})
CODE = tuple(dict.fromkeys(base.CORE + tuple("src/thericher_v2/research/" + p for p in (
    "kis_cross_asset_daily_risk.py", "cross_asset_daily_risk_input.py",
    "cross_asset_hedge_failure_input.py"))))
PHASES = ("source_input", "prepare", "fit_hgb", "fit_attention", "decision_seal",
          "forward_input", "evaluate", "validate")
PROGRESS = ("progress-hgb-start.json", "progress-hgb-complete.json",
            "progress-attention-start.json", "progress-attention-complete.json") + tuple(
                f"progress-attention-{n:04d}.json" for n in (128, 256, 384, 512))
ARTIFACTS = ("started.json", "scaler.json", "hgb.npz", "attention.safetensors",
             "predictions.json", "actions.json") + PROGRESS
require, encode, digest = base.require, base.encode, base.digest


def configuration():
    return dict(name=NAME, image=base.IMAGE, runtime=dict(RUNTIME),
        symbols=list(base.INSTRUMENT_ORDER),
        input_commitment_sha256=base.INPUT_PIN, calendar_sha256=base.CALENDAR_PIN,
        train_entries=["2021-12-01", "2023-12-20"], train_last_exit="2023-12-27",
        embargo_entries=["2023-12-21", "2023-12-29"],
        dev_views=[["2024-01-02", "2024-12-31"], ["2025-01-02", "2026-09-30"]],
        features="6x63 asset-major ln(CLOSE) differences and ln(CLOSE)-ln(OPEN); "
                 "64 exact prior CLOSEs/63 OPENs, previous scheduled CLOSE decision",
        target="TRAIN-only daily-entry first OPEN->fifth CLOSE balanced thirds; "
               "canonical ledger 5bps/side; loss iff factor<1; require30/class",
        standardization="TRAIN-only float64 population channel mean/std across samples/time; "
                        "zero std divisor1; resulting tensors float32",
        hgb=dict(loss="log_loss", learning_rate=.05, max_iter=100, max_leaf_nodes=3,
                 max_depth=2, min_samples_leaf=20, l2_regularization=1, random_state=SEED,
                 early_stopping=False, class_weight=None, categorical_features=None),
        attention=dict(projection=[6, 16], layers=1, heads=2, feedforward=32, activation="gelu",
                       dropout=0, pool="mean", position="fixed sinusoidal base10000",
                       parameters=2353, dtype="float32", seed=SEED, updates=UPDATES,
                       loss="unweighted BCE", optimizer="AdamW", lr=.001, weight_decay=.01,
                       norm_first=False, layer_norm_eps=1e-5, tf32=False, deterministic=True,
                       sdpa_backend="math", mha_fastpath=False),
        actions="P(loss)<.5 basket else cash; blend=(HGB+attention)/2; seal before DEV payoffs",
        groups="successive disjoint5 scheduled sessions from DEV first, no view reset; "
               "hold quantities unchanged, fifth CLOSE exit; final<=4 days cash except buyhold",
        policies=list(POLICIES), costs_bps_side=[str(c) for c in COSTS], cells=42,
        geometry=dict(train_entries=517, valuation_days=689, view_days=[252, 437],
                      complete_groups=137, tail_cash_days=4),
        null="TRAIN non-loss count/total Decimal50 HALF_EVEN; each sleeve=fraction*same "
             "finite THIRD Decimal50; higher precision solely for exact residual cash; "
             "not exposure-matched, no extra quantization",
        accounting="NAV1 once per policy/cost; Decimal50 HALF_EVEN actual-notional fee; "
                   "all scheduled daily marks; inventory/denominators cross view boundary",
        utility="252*(mean daily log-5*population variance)",
        kill="10bps BOTH views positive growth and growth/utility improvements>1e-10; "
             "HGB vs four controls; attention/blend vs controls+HGB; noncyclic",
        fits=2, seconds=SECONDS, verify_seconds=VERIFY_SECONDS, cpu=2, memory_bytes=6 * 1024**3,
        fit_accounting="completed HGB fit() return or512 synchronized optimizer updates; "
                       "recipe validation/prediction/serialization are separate, no refit",
        network="none", parent_gpu_lease=True, cublas_workspace_config=":4096:8",
        model_format="own safetensors + numeric HGB nodes NPZ allow_pickle=False",
        readback="reprepare TRAIN scalers/inputs; immutable model/prediction binding; "
                 "rebuild actions and42 economic cells; zero fit/inference/search/write",
        selection="one final fit/member; no grid/early stop/calibration/refit/weight selection",
        missing="required past/mark gap or insufficient TRAIN classes => scoped input_unavailable",
        grade="RAW_PRICE_ONLY_SEEN_SOURCE_DEVELOPMENT", paper_input=False, holdout_access="none",
        limitations=["MODP0 opaque", "splits/dividends/TR not applied", "chunk vintages differ",
                     "PIT/finality/availability unverified", "ideal fractional fills",
                     "overlapping TRAIN5D/63D contexts; counts not independent samples",
                     "seen DEV data; no deployment/replication", "cached prediction binding only"])


@dataclass(frozen=True, slots=True)
class StudyPlan:
    sessions: tuple = field(repr=False)
    train_indices: tuple[int, ...]
    dates: tuple[date, ...]
    group_indices: tuple[int, ...]
    block_cut: int

    @property
    def groups(self):
        return tuple(tuple(s.session_date for s in self.sessions[i:i + 5])
                     for i in self.group_indices)

    def record(self):
        return dict(train_entries=[self.sessions[i].session_date.isoformat()
                                   for i in self.train_indices],
                    valuation_dates=[d.isoformat() for d in self.dates],
                    groups=[[d.isoformat() for d in g] for g in self.groups],
                    block_cut=self.block_cut, tail_cash_days=len(self.dates) % 5,
                    decisions=[self.sessions[i - 1].close_at.isoformat()
                               for i in self.train_indices + self.group_indices])


def build_plan(sessions=None):
    sessions = base.calendar_sessions() if sessions is None else sessions
    require(type(sessions) is tuple and bool(sessions), "calendar_scope")
    for s in sessions:
        require(type(s) is base.CrossAssetSession, "calendar_type")
        s.__post_init__()
    require(all(a.session_date < b.session_date and a.close_at < b.open_at
                for a, b in zip(sessions, sessions[1:], strict=False)), "calendar_order")
    train = tuple(i for i, s in enumerate(sessions)
                  if date(2021, 12, 1) <= s.session_date <= date(2023, 12, 20))
    dev = tuple(i for i, s in enumerate(sessions)
                if date(2024, 1, 2) <= s.session_date <= date(2026, 9, 30))
    require(bool(train) and bool(dev) and sessions[train[0]].session_date == date(2021, 12, 1)
            and sessions[train[-1]].session_date == date(2023, 12, 20), "train_calendar")
    require(sessions[train[-1] + 4].session_date == date(2023, 12, 27), "train_target_cutoff")
    require(sessions[dev[0]].session_date == date(2024, 1, 2)
            and sessions[dev[-1]].session_date == date(2026, 9, 30)
            and dev == tuple(range(dev[0], dev[-1] + 1)), "dev_calendar")
    groups = tuple(dev[k] for k in range(0, len(dev) - len(dev) % 5, 5))
    require(all(i >= 64 for i in train + groups), "past_calendar")
    dates = tuple(sessions[i].session_date for i in dev)
    cut = sum(d <= date(2024, 12, 31) for d in dates)
    require(0 < cut < len(dates) and dates[cut - 1] == date(2024, 12, 31)
            and dates[cut] == date(2025, 1, 2), "view_calendar")
    require((len(train), len(dates), cut, len(groups), len(dates) % 5)
            == (517, 689, 252, 137, 4), "calendar_geometry")
    return StudyPlan(sessions, train, dates, groups, cut)


def partition_five(dates):
    require(type(dates) is tuple and bool(dates) and all(type(d) is date for d in dates)
            and all(a < b for a, b in zip(dates, dates[1:], strict=False)), "group_calendar")
    return tuple(dates[i:i + 5] for i in range(0, len(dates) - len(dates) % 5, 5))


@nav._decimal
def replay_groups(days, targets, plan, cost_bps):
    """Five-session closes on one cash/quantity state, including cash tail days."""
    require(type(plan) is StudyPlan, "plan_type")
    groups = plan.groups
    require(groups == partition_five(plan.dates), "group_partition")
    entries, exits = {g[0] for g in groups}, {g[-1] for g in groups}
    require(set(targets) == entries, "action_keys")
    records = tuple(days)
    require(tuple(d.date for d in records) == plan.dates, "forward_mark_gap")
    for d in records:
        require(type(d) is nav.ThreeAssetDay, "mark_type")
        d.__post_init__()
    for t in targets.values():
        require(type(t) is nav.ThreeAssetTarget, "target_type")
        t.__post_init__()
    fee = nav._fee(cost_bps)
    state, previous = nav.ThreeAssetState(Decimal(1)), Decimal(1)
    fees = notional = Decimal(0)
    trace = []
    for d in records:
        paid = traded = Decimal(0)
        if d.date in entries:
            require(all(q == 0 for q in state.quantities), "group_entry_not_flat")
            t = targets[d.date]
            move = nav._rebalance(state, nav.ThreeAssetPrices(d.adj_open3),
                                  t.weights3, t.cash_weight, fee)
            state, paid, traded = move.state, move.fees, move.turnover
        prices = nav.ThreeAssetPrices(d.adj_close3)
        if d.date in exits:
            move = nav.liquidate_close(state, prices, cost_bps)
            state, paid, traded = move.state, paid + move.fees, traded + move.turnover
        marked = nav.mark_close(state, prices)
        require(marked.nav > 0, "nonpositive_nav")
        factor = marked.nav / previous
        trace.append(nav.ThreeAssetDaily(d.date, marked.nav, paid, traded, state.cash,
            all(q == 0 for q in state.quantities), factor - 1, factor.ln()))
        fees, notional, previous = fees + paid, notional + traded, marked.nav
    require(trace[-1].flat, "final_not_flat")
    return nav.ThreeAssetReplay(tuple(trace), state, fees, notional)


def allocation(fraction=Decimal(1)):
    require(type(fraction) is Decimal and fraction.is_finite() and 0 <= fraction <= 1, "fraction")
    with localcontext(base.CONTEXT):
        weights = (fraction * base.THIRD,) * 3
    with localcontext(base.CONTEXT) as context:
        context.prec = max(100, max(-w.as_tuple().exponent for w in weights) + 2)
        cash = 1 - sum(weights, Decimal(0))
    return nav.ThreeAssetTarget(weights, cash)


def nonloss_fraction(labels):
    require(bool(len(labels)) and all(v in (0, 1) for v in labels), "labels")
    with localcontext(base.CONTEXT):
        return Decimal(sum(int(v) == 0 for v in labels)) / len(labels)


def prepare_actions(predictions, plan):
    require(build_plan(plan.sessions) == plan, "plan_changed")
    require(set(predictions["probabilities"]) == {"hgb", "attention"}, "probability_members")
    require(predictions["plan"] == plan.record(), "prediction_plan")
    count = len(plan.groups)
    probabilities = predictions["probabilities"]
    require(all(type(v) is list and len(v) == count and all(
        type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1 for p in v)
        for v in probabilities.values()), "probabilities")
    prior = allocation(Decimal(predictions["nonloss_fraction"]))
    full, cash = allocation(), allocation(Decimal(0))
    actions = {}
    for policy in POLICIES:
        chosen = []
        for j, group in enumerate(plan.groups):
            h, a = probabilities["hgb"][j], probabilities["attention"][j]
            score = h if policy == "hgb" else a if policy == "attention" else (h + a) / 2
            t = (full if score < .5 else cash) if policy in CANDIDATES else (
                cash if policy == "cash" else prior if policy == "train_prior" else full)
            if policy != "buyhold" or j == 0:
                chosen.append([group[0].isoformat(), *map(str, t.weights3), str(t.cash_weight)])
        actions[policy] = chosen
    return dict(plan=plan.record(), predictions_sha256=digest(encode(predictions)), actions=actions)


def evaluate(days, actions, plan, *, deadline=float("inf")):
    require(build_plan(plan.sessions) == plan, "plan_changed")
    require(actions["plan"] == plan.record() and set(actions["actions"]) == set(POLICIES),
            "action_binding")
    require(tuple(d.date for d in days) == plan.dates, "forward_mark_gap")
    seal, cells = digest(encode(actions)), []
    for cost in COSTS:
        for policy in POLICIES:
            require(time.monotonic() < deadline, "compute_stop")
            rows = actions["actions"][policy]
            expected = [g[0].isoformat() for g in plan.groups]
            require([r[0] for r in rows] == (expected[:1] if policy == "buyhold" else expected),
                    "action_keys")
            targets = {date.fromisoformat(r[0]): nav.ThreeAssetTarget(
                tuple(Decimal(w) for w in r[1:4]), Decimal(r[4])) for r in rows}
            ledger = (nav.replay(days, targets, cost) if policy == "buyhold" else
                      replay_groups(days, targets, plan, cost))
            cut = plan.block_cut
            for block, subset, entering in ((0, ledger.daily[:cut], Decimal(1)),
                                           (1, ledger.daily[cut:], ledger.daily[cut - 1].nav)):
                metrics = base._metrics(subset, entering, None)
                metrics.pop("months")
                metrics["group_entries"] = sum(d.date in targets for d in subset)
                cells.append(dict(block=block, policy=policy, cost_bps=str(cost),
                                  status="complete", metrics=metrics))
    require(digest(encode(actions)) == seal, "action_changed")
    return cells


def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for p in POLICIES for c in COSTS}
    require(len(cells) == 42 and {(c["block"], c["policy"], c["cost_bps"]) for c in cells}
            == expected and all(c["status"] == "complete" for c in cells), "cell_matrix")
    verdicts = {}
    with localcontext(base.CONTEXT):
        require(all(type(c["metrics"][k]) is str and Decimal(c["metrics"][k]).is_finite()
                    for c in cells for k in ("growth", "utility")), "cell_metrics")
        for candidate in CANDIDATES:
            passed = True
            controls = CONTROLS + (() if candidate == "hgb" else ("hgb",))
            for block in (0, 1):
                group = {c["policy"]: c["metrics"] for c in cells
                         if c["block"] == block and c["cost_bps"] == "10"}
                own = group[candidate]
                passed &= Decimal(own["growth"]) > 0 and all(
                    Decimal(own[k]) - Decimal(group[p][k]) > base.TOLERANCE
                    for p in controls for k in ("growth", "utility"))
            verdicts[candidate] = "development_survivor" if passed else "rejected"
    return verdicts


def required_fields(plan):
    result = {}
    def add(day, key):
        result.setdefault(day, set()).add(key)
    for i in plan.train_indices + plan.group_indices:
        for j, s in enumerate(plan.sessions[i - 64:i]):
            add(s.session_date, "close")
            if j:
                add(s.session_date, "open")
    for i in plan.train_indices:
        add(plan.sessions[i].session_date, "open")
        add(plan.sessions[i + 4].session_date, "close")
    return result


def load_required_prices(source, fields):
    from thericher_v2.research.cross_asset_hedge_failure_input import RawD1Price

    selected = {}
    for key in ("open", "close"):
        dates = {d.isoformat() for d, keys in fields.items() if key in keys}
        selected[key] = base._selected(source, dates, (key,))
    return {s: {d: RawD1Price(s, d, base.INPUT_PIN, **{
        key: selected[key][s][d.isoformat()][key] for key in keys}) for d, keys in fields.items()}
        for s in base.INSTRUMENT_ORDER}


def input_hash(array):
    return digest(encode(dict(shape=list(array.shape), dtype=array.dtype.str)) + array.tobytes())


@dataclass(frozen=True, slots=True)
class Prepared:
    plan: StudyPlan = field(repr=False)
    train_x: object = field(repr=False)
    dev_x: object = field(repr=False)
    labels: object = field(repr=False)
    scaler: dict = field(repr=False)


def prepare_inputs(source, plan, *, deadline=float("inf")):
    import numpy as np

    from thericher_v2.research.cross_asset_daily_risk_input import (
        build_five_session_target,
        prepare_daily_features,
    )

    require(build_plan(plan.sessions) == plan, "plan_changed")
    rows = load_required_prices(source, required_fields(plan))
    features, labels = [], []
    for i in plan.train_indices + plan.group_indices:
        require(time.monotonic() < deadline, "compute_stop")
        history, entry = plan.sessions[i - 64:i], plan.sessions[i]
        past = {s: tuple(rows[s][day.session_date] for day in history)
                for s in base.INSTRUMENT_ORDER}
        context = prepare_daily_features(past, scheduled_history=history, entry_session=entry,
            decision_at=history[-1].close_at, vintage_ref=base.INPUT_PIN)
        features.append(context.features)
    for i in plan.train_indices:
        require(time.monotonic() < deadline, "compute_stop")
        forward = plan.sessions[i:i + 5]
        endpoints = {s: tuple(rows[s][d.session_date] for d in (forward[0], forward[-1]))
                     for s in base.INSTRUMENT_ORDER}
        target = build_five_session_target(endpoints, scheduled_forward=forward,
                                           vintage_ref=base.INPUT_PIN)
        labels.append(int(target.loss_label))
    raw = np.asarray(features, dtype="<f8")
    y = np.asarray(labels, dtype="u1")
    n = len(plan.train_indices)
    require(raw.shape == (n + len(plan.groups), 6, 63) and np.isfinite(raw).all(), "feature_shape")
    counts = [int((y == v).sum()) for v in (0, 1)]
    require(min(counts) >= 30, "insufficient_classes")
    mean, std = raw[:n].mean(axis=(0, 2)), raw[:n].std(axis=(0, 2), ddof=0)
    divisor = np.where(std == 0, 1., std)
    normalized = ((raw - mean[None, :, None]) / divisor[None, :, None]).astype("<f4")
    require(np.isfinite(normalized).all(), "feature_numeric")
    scaler = dict(mean=mean.tolist(), divisor=divisor.tolist(), counts=counts,
        train_count=n, dev_count=len(plan.groups), nonloss_fraction=str(nonloss_fraction(y)),
        train_raw_sha256=input_hash(raw[:n]), dev_raw_sha256=input_hash(raw[n:]),
        labels_sha256=input_hash(y), train_x_sha256=input_hash(normalized[:n]),
        dev_x_sha256=input_hash(normalized[n:]),
        train_earliest_thinned_five_session_blocks=len(plan.train_indices[::5]),
        dev_disjoint_five_session_blocks=len(plan.groups), independent_sample_count="not_claimed")
    for array in (normalized, y):
        array.flags.writeable = False
    return Prepared(plan, normalized[:n], normalized[n:], y, scaler)


def make_attention():
    import torch

    class Attention(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.project = torch.nn.Linear(6, 16, device="cpu", dtype=torch.float32)
            self.encoder = torch.nn.TransformerEncoderLayer(
                16, 2, dim_feedforward=32, dropout=0, activation="gelu", batch_first=True,
                norm_first=False, layer_norm_eps=1e-5, device="cpu", dtype=torch.float32)
            self.output = torch.nn.Linear(16, 1, device="cpu", dtype=torch.float32)
            positions = torch.arange(63, dtype=torch.float32, device="cpu")[:, None]
            scales = torch.exp(torch.arange(0, 16, 2, dtype=torch.float32, device="cpu")
                               * (-math.log(10000.) / 16))
            encoding = torch.empty(63, 16, dtype=torch.float32, device="cpu")
            encoding[:, 0::2], encoding[:, 1::2] = torch.sin(positions * scales), torch.cos(
                positions * scales)
            self.register_buffer("position", encoding)
            self.to(dtype=torch.float32)

        def forward(self, x):
            with torch.nn.attention.sdpa_kernel(torch.nn.attention.SDPBackend.MATH):
                return self.output(self.encoder(
                    self.project(x.transpose(1, 2)) + self.position).mean(dim=1)).squeeze(-1)
    return Attention()


def fit_hgb(prepared, *, deadline, progress):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from threadpoolctl import threadpool_limits

    require(time.monotonic() < deadline, "compute_stop")
    started = time.monotonic()
    model = HistGradientBoostingClassifier(**configuration()["hgb"])
    with threadpool_limits(limits=2):
        model.fit(prepared.train_x.reshape(len(prepared.labels), 378), prepared.labels)
        progress()
        require(model.n_iter_ == 100 and list(model.classes_) == [0, 1], "hgb_final")
        probabilities = model.predict_proba(prepared.dev_x.reshape(len(prepared.dev_x), 378))[:, 1]
    require(time.monotonic() < deadline, "compute_stop")
    return model, probabilities.tolist(), dict(seconds=time.monotonic() - started, iterations=100)


def fit_attention(prepared, *, deadline, progress):
    import numpy as np
    import torch
    from safetensors.torch import save

    require(time.monotonic() < deadline, "compute_stop")
    require(torch.cuda.is_available(), "cuda_unavailable")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.mha.set_fastpath_enabled(False)
    torch.manual_seed(SEED)
    model = make_attention().to("cuda")
    require(sum(p.numel() for p in model.parameters()) == 2353, "attention_parameters")
    x = torch.from_numpy(np.array(prepared.train_x, copy=True)).to("cuda")
    y = torch.from_numpy(np.array(prepared.labels, dtype="float32", copy=True)).to("cuda")
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.01)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    model.train()
    for update in range(1, UPDATES + 1):
        require(time.monotonic() < deadline, "compute_stop")
        optimizer.zero_grad(set_to_none=True)
        loss = torch.nn.functional.binary_cross_entropy_with_logits(model(x), y)
        require(bool(torch.isfinite(loss).item()), "fit_nonfinite")
        loss.backward()
        optimizer.step()
        if update % 128 == 0:
            torch.cuda.synchronize()
            progress(update)
    require(all(bool(torch.isfinite(p).all().item()) for p in model.parameters()), "fit_nonfinite")
    model.eval()
    with torch.inference_mode():
        dev = torch.from_numpy(np.array(prepared.dev_x, copy=True)).to("cuda")
        probabilities = torch.sigmoid(model(dev)).cpu().tolist()
    torch.cuda.synchronize()
    resources = dict(seconds=time.monotonic() - started, updates=UPDATES,
                     peak_vram_bytes=int(torch.cuda.max_memory_allocated()))
    weights = save({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()})
    require(time.monotonic() < deadline, "compute_stop")
    return probabilities, weights, resources


def hgb_archive(model):
    import numpy as np

    require(len(model._predictors) == 100, "hgb_tree_count")
    arrays = {"baseline": np.asarray(model._baseline_prediction, dtype="float64")}
    for i, predictors in enumerate(model._predictors):
        require(len(predictors) == 1 and not predictors[0].nodes.dtype.hasobject, "hgb_tree_format")
        arrays[f"nodes_{i:03d}"] = predictors[0].nodes
    buffer = io.BytesIO()
    np.savez(buffer, **arrays)
    return buffer.getvalue()


def runtime_identity():
    import torch

    versions = base.runtime_identity()
    for name in ("numpy", "scikit-learn", "torch", "safetensors"):
        versions[name] = importlib.metadata.version(name)
    versions["cuda"] = torch.version.cuda
    return versions


def _root(root, artifact_root):
    root, artifact_root = Path(root).absolute(), Path(artifact_root).absolute()
    require(root == artifact_root / "research" / NAME, "study_root")
    base.reject_repo_artifact_path(root, REPO)
    require(root.is_dir(), "study_root")
    return root


def freeze_contract(root, *, artifact_root=None, runtime=None, source_root=None):
    """Parent-invoked only: hash metadata/code, never parse source numeric rows."""
    root = Path(root).absolute()
    artifact_root = root.parent.parent if artifact_root is None else artifact_root
    root = _root(root, artifact_root)
    source_root = REPO if source_root is None else Path(source_root).absolute()
    require(source_root == REPO, "frozen_source_root")
    commitment = base._json(base._relative(artifact_root, base.INPUT_RELATIVE), base.INPUT_PIN)
    paths = tuple(dict.fromkeys(CODE + tuple(commitment["source_pins"])))
    pins = {p: digest(base._read(base._relative(source_root, p))) for p in paths}
    require(all(pins[p] == h for p, h in commitment["source_pins"].items()), "producer_code_pins")
    observed = runtime_identity() if runtime is None else runtime
    require(all(observed.get(k) == v for k, v in RUNTIME.items())
            and bool(observed.get("safetensors")), "runtime_identity")
    contract = dict(name=NAME, config=configuration(), runtime=observed, code_sha256=pins,
                    source_root=str(source_root),
                    input_commitment_sha256=base.INPUT_PIN, plan=build_plan().record())
    base.atomic_new(root / "precommit.json", contract)
    return digest(encode(contract))


def read_contract(root, artifact_root, pin):
    root = _root(root, artifact_root)
    contract = base._json(root / "precommit.json", pin)
    require(contract["name"] == NAME and contract["config"] == configuration(), "contract_config")
    require(contract["runtime"] == runtime_identity() and all(
        contract["runtime"].get(k) == v for k, v in RUNTIME.items()), "runtime_identity")
    source_root = Path(contract["source_root"]).absolute()
    require(source_root == REPO, "frozen_source_root")
    require(set(contract["code_sha256"]) >= set(CODE), "code_pins")
    for p, expected in contract["code_sha256"].items():
        require(digest(base._read(base._relative(source_root, p))) == expected, "code_changed")
    require(contract["input_commitment_sha256"] == base.INPUT_PIN, "input_commitment_binding")
    commitment = base._json(base._relative(artifact_root, base.INPUT_RELATIVE), base.INPUT_PIN)
    require(commitment["calendar_sha256"] == base.CALENDAR_PIN
            and commitment["kind"] == "kis-cross-asset-d1-price-only-input-v1"
            and commitment["no_date_fill"] is True, "input_identity")
    require(all(contract["code_sha256"].get(p) == h
                for p, h in commitment["source_pins"].items()), "producer_code_pins")
    return contract, commitment


def atomic_bytes(path, raw):
    import os

    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _artifacts(root):
    return {name: digest(base._read(root / name)) for name in ARTIFACTS if (root / name).exists()}


def _verify_progress(root, result, pin):
    expected = {PROGRESS[0]: (0, 1, None), PROGRESS[1]: (1, 1, None),
                PROGRESS[2]: (1, 2, None), PROGRESS[3]: (2, 2, UPDATES)}
    expected.update({f"progress-attention-{n:04d}.json": (2 if n == UPDATES else 1, 2, n)
                     for n in (128, 256, 384, 512)})
    for name, (completed, starts, updates) in expected.items():
        if name in result["artifact_sha256"]:
            record = dict(contract_sha256=pin, completed_fits=completed,
                          fit_starts=starts, updates=updates)
            if name in (PROGRESS[1], PROGRESS[3]):
                record["training_completion"] = (
                    "fit_method_returned" if name == PROGRESS[1] else "512_optimizer_updates")
            require(base._json(root / name, canonical=True) == record
                and result["actual_fits"] >= completed and result["fit_starts"] >= starts,
                "progress_binding")


def load_marks(source, plan):
    rows = base._selected(source, {d.isoformat() for d in plan.dates}, ("open", "close"))
    return tuple(nav.ThreeAssetDay(d,
        tuple(rows[s][d.isoformat()]["open"] for s in base.INSTRUMENT_ORDER),
        tuple(rows[s][d.isoformat()]["close"] for s in base.INSTRUMENT_ORDER)) for d in plan.dates)


def _safe(result):
    return {k: result[k] for k in ("status", "reason", "phase", "actual_fits", "fit_starts",
                                 "contract_sha256", "elapsed_seconds", "criterion")} | dict(
        cells=len(result["cells"]), result_sha256=digest(encode(result)),
        paper_input=False, holdout_access="none")


def run(root, market_root, artifact_root, pin):
    start = time.monotonic()
    deadline = start + SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    require(not _artifacts(root) and not (root / "worker-result.json").exists(), "attempt_exists")
    base.atomic_new(root / "started.json", dict(contract_sha256=pin, input_sha256=base.INPUT_PIN))
    result = dict(status="failed", reason="worker_failed", phase="source_input", actual_fits=0,
        fit_starts=0, contract_sha256=pin, elapsed_seconds=0, criterion={}, cells=[],
        artifact_sha256={}, resources={})
    def progress(name, updates=None, completion=None):
        record = dict(contract_sha256=pin, completed_fits=result["actual_fits"],
                      fit_starts=result["fit_starts"], updates=updates)
        if completion is not None:
            record["training_completion"] = completion
        base.atomic_new(root / name, record)
    def hgb_completed():
        result["actual_fits"] = 1
        progress("progress-hgb-complete.json", completion="fit_method_returned")
    def attention_progress(update):
        if update == UPDATES:
            result["actual_fits"] = 2
        progress(f"progress-attention-{update:04d}.json", update)
        if update == UPDATES:
            progress("progress-attention-complete.json", update, "512_optimizer_updates")
    try:
        source = base.load_committed_source(commitment, artifact_root, market_root,
                                            deadline=deadline)
        plan = build_plan(source.plan.sessions)
        require(plan.record() == contract["plan"], "plan_changed")
        result["phase"] = "prepare"
        prepared = prepare_inputs(source, plan, deadline=deadline)
        base.atomic_new(root / "scaler.json", prepared.scaler)
        result["phase"], result["fit_starts"] = "fit_hgb", 1
        progress("progress-hgb-start.json")
        model, hgb, resources = fit_hgb(prepared, deadline=deadline, progress=hgb_completed)
        result["resources"]["hgb"] = resources
        atomic_bytes(root / "hgb.npz", hgb_archive(model))
        result["phase"], result["fit_starts"] = "fit_attention", 2
        progress("progress-attention-start.json")
        attention, weights, resources = fit_attention(prepared, deadline=deadline,
                                                     progress=attention_progress)
        result["resources"]["attention"] = resources
        atomic_bytes(root / "attention.safetensors", weights)
        result["phase"] = "decision_seal"
        predictions = dict(contract_sha256=pin, input_sha256=base.INPUT_PIN, plan=plan.record(),
            scaler_sha256=digest(encode(prepared.scaler)), nonloss_fraction=prepared.scaler[
                "nonloss_fraction"], model_sha256={name: digest(base._read(root / name))
                for name in ("hgb.npz", "attention.safetensors")},
            probabilities=dict(hgb=hgb, attention=attention), inference_kind="original_worker")
        base.atomic_new(root / "predictions.json", predictions)
        actions = prepare_actions(predictions, plan)
        base.atomic_new(root / "actions.json", actions)
        require(time.monotonic() < deadline, "compute_stop")
        result["phase"] = "forward_input"
        marks = load_marks(source, plan)
        result["phase"] = "evaluate"
        cells = evaluate(marks, actions, plan, deadline=deadline)
        result["phase"] = "validate"
        verdict = criterion(cells)
        require(base.load_committed_source(commitment, artifact_root, market_root,
                    deadline=deadline).files == source.files, "source_changed")
        require(time.monotonic() < deadline, "compute_stop")
        result.update(status="complete", reason=None, criterion=verdict, cells=cells)
    except Exception as error:
        allowed = {"compute_stop", "insufficient_classes", "required_date_gap", "required_price",
            "source_changed", "forward_mark_gap", "feature_shape", "feature_numeric",
            "fit_nonfinite", "cuda_unavailable", "hgb_final", "plan_changed",
            "required_session_missing", "required_price_invalid", "required_session_duplicate",
            "required_vintage_mismatch", "price_basis_invalid", "numeric_range",
            "target_ledger_unavailable"}
        code = str(error) if isinstance(error, (
            base.StudyFault, nav.ThreeAssetNavError, CrossAssetInputUnavailable)) \
            and str(error) in allowed else "worker_failed"
        result["reason"] = code
        if code in {"insufficient_classes", "required_date_gap", "required_price",
                    "forward_mark_gap", "required_session_missing", "required_price_invalid",
                    "required_session_duplicate", "required_vintage_mismatch",
                    "price_basis_invalid", "numeric_range", "target_ledger_unavailable"}:
            result["status"] = "input_unavailable"
    result.update(elapsed_seconds=time.monotonic() - start, artifact_sha256=_artifacts(root))
    base.atomic_new(root / "worker-result.json", result)
    return _safe(result)


def verify(root, market_root, artifact_root, pin, result_pin):
    deadline = time.monotonic() + VERIFY_SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    result = base._json(root / "worker-result.json", result_pin, canonical=True)
    require(set(result) == {"status", "reason", "phase", "actual_fits", "fit_starts",
        "contract_sha256", "elapsed_seconds", "criterion", "cells", "artifact_sha256", "resources"}
        and result["contract_sha256"] == pin and result["phase"] in PHASES
        and type(result["actual_fits"]) is int and type(result["fit_starts"]) is int
        and 0 <= result["actual_fits"] <= result["fit_starts"] <= 2
        and type(result["elapsed_seconds"]) in (int, float)
        and math.isfinite(result["elapsed_seconds"]) and result["elapsed_seconds"] >= 0,
        "result_binding")
    require(result["artifact_sha256"] == _artifacts(root), "artifact_binding")
    require(base._json(root / "started.json", canonical=True) == dict(
        contract_sha256=pin, input_sha256=base.INPUT_PIN), "start_binding")
    _verify_progress(root, result, pin)
    if result["status"] in {"failed", "input_unavailable"}:
        require(result["reason"] is not None and result["cells"] == []
                and result["criterion"] == {}, "failure_binding")
        return _safe(result) | dict(replay="failure_binding_only", fits=0, inference=0,
                                   searches=0, writes=0)
    require(result["status"] == "complete" and result["reason"] is None
            and result["phase"] == "validate" and result["actual_fits"] == result["fit_starts"] == 2
            and set(result["artifact_sha256"]) == set(ARTIFACTS), "complete_binding")
    source = base.load_committed_source(commitment, artifact_root, market_root, deadline=deadline)
    plan = build_plan(source.plan.sessions)
    require(plan.record() == contract["plan"], "plan_changed")
    prepared = prepare_inputs(source, plan, deadline=deadline)
    require(base._json(root / "scaler.json", canonical=True) == prepared.scaler, "scaler_replay")
    predictions = base._json(root / "predictions.json", canonical=True)
    require(predictions["contract_sha256"] == pin and predictions["input_sha256"] == base.INPUT_PIN
        and predictions["scaler_sha256"] == digest(encode(prepared.scaler))
        and predictions["nonloss_fraction"] == prepared.scaler["nonloss_fraction"]
        and predictions["inference_kind"] == "original_worker"
        and predictions["model_sha256"] == {name: result["artifact_sha256"][name]
            for name in ("hgb.npz", "attention.safetensors")}, "prediction_binding")
    actions = prepare_actions(predictions, plan)
    require(base._read(root / "actions.json") == encode(actions), "action_replay")
    cells = evaluate(load_marks(source, plan), actions, plan, deadline=deadline)
    require(encode(cells) == encode(result["cells"]) and criterion(cells) == result["criterion"],
            "numeric_replay")
    require(base.load_committed_source(commitment, artifact_root, market_root,
                deadline=deadline).files == source.files, "source_changed")
    require(time.monotonic() < deadline, "compute_stop")
    return _safe(result) | dict(replay="exact_economic/cached_prediction_binding", fits=0,
                               inference=0, searches=0, writes=0)


def synthetic_smoke():
    import torch

    from thericher_v2.research.cross_asset_daily_risk_input import (
        RawD1Price,
        build_five_session_target,
        prepare_daily_features,
    )

    plan = build_plan()
    i = plan.train_indices[0]
    history = plan.sessions[i - 64:i]
    rows = {s: tuple(RawD1Price(s, d.session_date, "synthetic", Decimal(100), Decimal(100))
                     for d in history) for s in base.INSTRUMENT_ORDER}
    features = prepare_daily_features(rows, scheduled_history=history,
        entry_session=plan.sessions[i], decision_at=history[-1].close_at, vintage_ref="synthetic")
    forward = plan.sessions[i:i + 5]
    target_rows = {s: tuple(RawD1Price(s, d.session_date, "synthetic", Decimal(100), Decimal(100))
                           for d in forward) for s in base.INSTRUMENT_ORDER}
    target = build_five_session_target(target_rows, scheduled_forward=forward,
                                      vintage_ref="synthetic")
    require(target.loss_label and len(features.features) == 6, "smoke_input")
    fastpath = torch.backends.mha.get_fastpath_enabled()
    try:
        torch.backends.mha.set_fastpath_enabled(False)
        with torch.random.fork_rng(devices=[]), torch.inference_mode():
            torch.manual_seed(SEED)
            model = make_attention().eval()
            tensor = torch.tensor([features.features], dtype=torch.float32, device="cpu")
            require(sum(p.numel() for p in model.parameters()) == 2353
                    and bool(torch.isfinite(model(tensor)).all()), "smoke_model")
    finally:
        torch.backends.mha.set_fastpath_enabled(fastpath)
    count = len(plan.groups)
    predictions = dict(plan=plan.record(), nonloss_fraction="0.5", probabilities=dict(
        hgb=[.25 if i % 2 else .75 for i in range(count)], attention=[.5] * count))
    actions = prepare_actions(predictions, plan)
    marks = tuple(nav.ThreeAssetDay(d, (Decimal(100),) * 3, (Decimal(100),) * 3)
                  for d in plan.dates)
    cells = evaluate(marks, actions, plan)
    require(len(cells) == 42 and set(criterion(cells).values()) == {"rejected"}, "smoke_matrix")
    return dict(status="smoke_passed", train_entries=len(plan.train_indices),
        dev_groups=count, tail_cash_days=len(plan.dates) % 5, cells=42, actual_fits=0,
        actual_market_reads=0, gpu=False, paper_input=False, synthetic_feature_shape=[6, 63],
        cpu_attention_parameters=2353)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("smoke", "run", "verify"))
    for name in ("root", "market-root", "artifact-root"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    args = parser.parse_args(argv)
    bound = args.phase != "smoke"
    if any(bool(v) != bound for v in (args.root, args.market_root, args.artifact_root,
                                      args.contract_sha256)) or bool(args.result_sha256) != (
                                          args.phase == "verify"):
        parser.error("run/verify require roots+contract pin; verify requires result pin; "
                     "smoke none")
    try:
        result = (synthetic_smoke() if not bound else run(args.root, args.market_root,
            args.artifact_root, args.contract_sha256) if args.phase == "run" else verify(
                args.root, args.market_root, args.artifact_root, args.contract_sha256,
                args.result_sha256))
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if result["status"] in {"complete", "smoke_passed"} else 2
    except Exception:
        print(json.dumps(dict(status="failed", reason="study_unavailable")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
