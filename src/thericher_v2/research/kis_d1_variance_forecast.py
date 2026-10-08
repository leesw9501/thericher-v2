"""Fixed daily variance-proxy forecasts; parent owns freeze, GPU lease and timeout.

No price/NAV prediction, trading authority, provider, credentials or public model.
Readback binds cached original predictions, not fresh saved-model inference.
Logical past selection is not physically target-isolated source-byte access.
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

import numpy as np

from thericher_v2.research import kis_cross_asset_daily_risk as lifecycle
from thericher_v2.research import kis_cross_asset_monthly_momentum as base
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable

NAME = "kis-d1-variance-forecast-development-v1"
REPO = Path(__file__).resolve().parents[3]
SECONDS, VERIFY_SECONDS, SEED, UPDATES = 300, 120, 101, 512
FLOOR, TOLERANCE = 1e-12, Decimal("1e-10")
GEOMETRY_RELATIVE = "data/" + NAME + "/geometry-20261008-v1.json"
GEOMETRY_PIN = "sha256:3536ee53137f0ff550f7e9c946e4db04c4cacaa3ee6f79ac171f42b5dacaa030"
CANDIDATES, METHODS, METRICS = ("ols", "gru"), ("baseline", "ols", "gru"), ("qlike", "log_mse")
RUNTIME = dict(base.RUNTIME, numpy="2.5.1", torch="2.7.0+cu128", cuda="12.8",
               safetensors="0.8.0")
CODE = base.CORE + ("src/thericher_v2/research/kis_cross_asset_daily_risk.py",
                    "src/thericher_v2/research/kis_d1_variance_forecast.py")
PHASES = ("source_input", "prepare", "fit_ols", "fit_gru", "prediction_seal",
          "forward_input", "evaluate", "validate")
PROGRESS = ("progress-ols-start.json", "progress-ols-complete.json",
            "progress-gru-start.json", "progress-gru-complete.json") + tuple(
                f"progress-gru-{n:04d}.json" for n in (128, 256, 384, 512))
ARTIFACTS = ("started.json", "scaler.json", "ols.npz", "gru.safetensors",
             "predictions.json") + PROGRESS
require, encode, digest = base.require, base.encode, base.digest


def configuration():
    return dict(name=NAME, image=base.IMAGE, runtime=dict(RUNTIME),
        symbols=list(base.INSTRUMENT_ORDER), input_commitment_sha256=base.INPUT_PIN,
        calendar_sha256=base.CALENDAR_PIN,
        geometry_receipt=dict(artifact_relative_path=GEOMETRY_RELATIVE, sha256=GEOMETRY_PIN),
        geometry=dict(train_entries=503, dev_entries=33, view_entries=[12, 21],
            required_dates=1276, train_disjoint_21_close_labels=24, effective_sample_size="unknown",
            dev_adjacent_label_overlaps=12, train_last_target_equals_first_dev_decision=True),
        train_entries=["2021-12-01", "2023-11-30"], embargo_entries="December2023",
        dev_entries="33 first scheduled monthly sessions2024Jan..2026Sep; views12/21",
        context="64 exact prior scheduled raw CLOSEs ->63 Decimal50 simple returns; "
                "asset-major3x63, previous scheduled CLOSE decision",
        har="asset-major9 trailing1/5/22 mean-squared simple-return features; "
            "daily proxy NOT intraday realized variance or HAR-RV replication",
        target="21 scheduled future close-to-close returns, previous decision CLOSE as "
               "anchor; population variance ddof0; log(max(variance,1e-12))",
        baseline="trailing21 past simple-return population variance ddof0, same1e-12 floor",
        scaler="TRAIN-only float64 population mean/std: sequence each asset over samples/time, "
               "HAR each9 columns; zero std=>1; GRU float32; targets centered TRAIN log mean only",
        ols="one joint multioutput numpy.linalg.lstsq, intercept+9 standardized HAR inputs; "
            "float64 rcond=None minimum-norm solution; no rank/feature/outcome selection",
        gru=dict(input_size=3, hidden_size=32, num_layers=1, batch_first=True, dropout=0,
                 bidirectional=False, output="last state linear32->3 +TRAIN log-target mean",
                 parameters=3651, dtype="float32", seed=SEED, updates=UPDATES,
                 optimizer="AdamW", lr=.001, weight_decay=.01,
                 loss="full-batch mean log-target MSE",
                 deterministic=True, tf32=False, cudnn_benchmark=False),
        forecast="exp(log_forecast), no prediction floor/clipping; finite log predictions "
                 "and strictly positive finite variance required; otherwise technical failure",
        metrics="equal mean over3 assets and every scheduled decision per view; "
                "QLIKE=y/v-log(y/v)-1 with floored variance y; log-MSE; "
                "6 structured cells/12 pooled metrics +fixed3-asset diagnostics",
        accounting="target-only variance; no NAV/trading costs/Paper",
        kill="both metrics BOTH views improvements strictly>1e-10: OLS vs baseline; "
             "GRU vs baseline AND OLS; no selection/rescue",
        cells=6, metric_values=12, fits=2, seconds=SECONDS, verify_seconds=VERIFY_SECONDS,
        fit_accounting="OLS lstsq return/GRU512 synchronized optimizer steps recorded BEFORE "
                       "validation/prediction/serialization/deadline checks",
        cpu=2, memory_bytes=6 * 1024**3, network="none", parent_gpu_lease=True,
        cublas_workspace_config=":4096:8", model_format="own numeric NPZ/own safetensors",
        readback="exact_metrics/cached_prediction_binding; reprepare inputs/scalers/targets; "
                 "no refit, saved-model reinference, search or write",
        source_receipt_sha256="sha256:08ea3d458fc2eff843f8fd1fb194e2d7a5e4b88ebedb1a183"
                              "5830e73781c81a6",
        sources=["https://academic.oup.com/jfec/article-abstract/7/2/174/856522",
                 "https://arch.readthedocs.io/en/stable/univariate/generated/arch.univariate.HARX.html"],
        source_scope="independent2026-10-08 04:01-04:02UTC publisher search abstract/HARX7.2.0; "
                     "Corsi full empirical period/instruments not verified; "
                     "no code/dependency adoption",
        grade="RAW_PRICE_ONLY_SEEN_SOURCE_DEVELOPMENT", paper_input=False, holdout_access="none",
        limitations=["no financial NAV/edge/alpha or risk-budget deployment claim",
                     "MODP0 opaque; splits/dividends/TR not applied; chunk vintages differ",
                     "PIT/finality/decision-time availability not observed",
                     "overlapping TRAIN labels and DEV horizons;33 dates NOT99 independent samples",
                     "variance proxy noise; only12/21 DEV dates; "
                     "no holdout/depth/Paper qualification"])


@dataclass(frozen=True, slots=True)
class StudyPlan:
    sessions: tuple = field(repr=False)
    train_indices: tuple[int, ...]
    dev_indices: tuple[int, ...]
    block_cut: int = 12

    def record(self):
        return dict(train_entries=[self.sessions[i].session_date.isoformat()
                                   for i in self.train_indices],
            dev_entries=[self.sessions[i].session_date.isoformat() for i in self.dev_indices],
            block_cut=self.block_cut, decisions=[self.sessions[i - 1].close_at.isoformat()
                for i in self.train_indices + self.dev_indices],
            label_exits=[self.sessions[i + 20].close_at.isoformat()
                         for i in self.train_indices + self.dev_indices])


def build_plan(sessions=None):
    sessions = base.calendar_sessions() if sessions is None else sessions
    require(type(sessions) is tuple and bool(sessions), "calendar_scope")
    for s in sessions:
        require(type(s) is base.CrossAssetSession, "calendar_type")
        s.__post_init__()
    require(all(a.session_date < b.session_date and a.close_at < b.open_at
                for a, b in zip(sessions, sessions[1:], strict=False)), "calendar_order")
    train = tuple(i for i, s in enumerate(sessions)
                  if date(2021, 12, 1) <= s.session_date <= date(2023, 11, 30))
    dev = tuple(i for i, s in enumerate(sessions) if date(2024, 1, 2) <= s.session_date
        <= date(2026, 9, 30) and i > 0 and (s.session_date.year, s.session_date.month)
        != (sessions[i - 1].session_date.year, sessions[i - 1].session_date.month))
    require(bool(train) and sessions[train[0]].session_date == date(2021, 12, 1)
            and sessions[train[-1]].session_date == date(2023, 11, 30), "train_calendar")
    require(len(dev) == 33 and sum(sessions[i].session_date.year == 2024 for i in dev) == 12
            and sessions[dev[0]].session_date == date(2024, 1, 2)
            and sessions[dev[-1]].session_date == date(2026, 9, 1), "dev_calendar")
    require(all(i >= 64 and i + 20 < len(sessions) for i in train + dev), "past_forward_calendar")
    require(len(train) == 503 and sessions[train[-1] + 20].session_date == date(2023, 12, 29)
            and sessions[train[-1] + 20].close_at <= sessions[dev[0] - 1].close_at,
            "train_target_cutoff")
    return StudyPlan(sessions, train, dev)


def required_dates(plan, indices, *, forward=False):
    return frozenset(s.session_date for i in indices
        for s in (plan.sessions[i - 1:i + 21] if forward else plan.sessions[i - 64:i]))


def load_closes(source, dates):
    selected = base._selected(source, {d.isoformat() for d in dates}, ("close",))
    return {s: tuple(base.PriceClose(s, date.fromisoformat(d), base.INPUT_PIN, row["close"])
                     for d, row in sorted(selected[s].items())) for s in base.INSTRUMENT_ORDER}


def returns_for_dates(rows_by_symbol, dates, vintage_ref):
    require(set(rows_by_symbol) == set(base.INSTRUMENT_ORDER), "source_symbols")
    require(type(dates) is tuple and len(dates) in (22, 64)
            and all(type(d) is date for d in dates)
            and all(a < b for a, b in zip(dates, dates[1:], strict=False)), "return_calendar")
    needed, result = frozenset(dates), []
    for symbol in base.INSTRUMENT_ORDER:
        selected = {}
        for row in rows_by_symbol[symbol]:
            day = getattr(row, "session_date", None)
            if day not in needed:
                continue
            require(day not in selected, "required_session_duplicate")
            require(type(row) is base.PriceClose and row.symbol == symbol
                    and row.vintage_ref == vintage_ref, "required_row_binding")
            row.__post_init__()
            selected[day] = row.close
        require(set(selected) == needed, "required_session_missing")
        with localcontext(base.CONTEXT):
            values = tuple((selected[b] - selected[a]) / selected[a]
                           for a, b in zip(dates, dates[1:], strict=False))
        converted = tuple(float(v) for v in values)
        require(all(math.isfinite(v) and v > -1 and (a == 0 or v != 0)
                    for a, v in zip(values, converted, strict=True)), "return_numeric")
        result.append(converted)
    return np.asarray(result, dtype="<f8")


def past_features(rows, plan, index, vintage):
    dates = tuple(s.session_date for s in plan.sessions[index - 64:index])
    return returns_for_dates(rows, dates, vintage)


def forward_target(rows, plan, index, vintage):
    dates = tuple(s.session_date for s in plan.sessions[index - 1:index + 21])
    returns = returns_for_dates(rows, dates, vintage)
    with np.errstate(over="raise", invalid="raise"):
        target = returns.var(axis=1, ddof=0)
    require(np.isfinite(target).all() and (target >= 0).all(), "target_numeric")
    return np.maximum(target, FLOOR)


@dataclass(frozen=True, slots=True)
class Prepared:
    plan: StudyPlan = field(repr=False)
    train_x: object = field(repr=False)
    dev_x: object = field(repr=False)
    train_har: object = field(repr=False)
    dev_har: object = field(repr=False)
    labels: object = field(repr=False)
    baseline: object = field(repr=False)
    scaler: dict = field(repr=False)


def prepare_arrays(raw, targets, plan):
    n, m = len(plan.train_indices), len(plan.dev_indices)
    raw, targets = np.asarray(raw, dtype="<f8"), np.asarray(targets, dtype="<f8")
    require(raw.shape == (n + m, 3, 63) and np.isfinite(raw).all(), "feature_shape")
    require(targets.shape == (n, 3) and np.isfinite(targets).all()
            and (targets >= FLOOR).all(), "target_numeric")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        har = np.stack([np.mean(raw[:, a, -k:]**2, axis=1)
                        for a in range(3) for k in (1, 5, 22)], axis=1)
        mean, std = raw[:n].mean(axis=(0, 2)), raw[:n].std(axis=(0, 2), ddof=0)
        hmean, hstd = har[:n].mean(axis=0), har[:n].std(axis=0, ddof=0)
        divisor, hdivisor = np.where(std == 0, 1., std), np.where(hstd == 0, 1., hstd)
        x = ((raw - mean[None, :, None]) / divisor[None, :, None]).astype("<f4")
        hx, y = (har - hmean) / hdivisor, np.log(targets)
        baseline = np.maximum(raw[n:, :, -21:].var(axis=2, ddof=0), FLOOR)
    require(all(np.isfinite(v).all() for v in (x, hx, y, baseline)), "feature_numeric")
    scaler = dict(mean=mean.tolist(), divisor=divisor.tolist(), har_mean=hmean.tolist(),
        har_divisor=hdivisor.tolist(), target_log_mean=y.mean(axis=0).tolist(),
        train_count=n, dev_count=m, train_raw_sha256=lifecycle.input_hash(raw[:n]),
        dev_raw_sha256=lifecycle.input_hash(raw[n:]), labels_sha256=lifecycle.input_hash(y),
        train_x_sha256=lifecycle.input_hash(x[:n]), dev_x_sha256=lifecycle.input_hash(x[n:]),
        train_har_sha256=lifecycle.input_hash(hx[:n]), dev_har_sha256=lifecycle.input_hash(hx[n:]),
        baseline_sha256=lifecycle.input_hash(baseline), independent_sample_count="not_claimed")
    for array in (x, hx, y, baseline):
        array.flags.writeable = False
    return Prepared(plan, x[:n], x[n:], hx[:n], hx[n:], y, baseline, scaler)


def prepare_inputs(source, plan, *, deadline=float("inf")):
    require(build_plan(plan.sessions) == plan, "plan_changed")
    indices = plan.train_indices + plan.dev_indices
    past = load_closes(source, required_dates(plan, indices))
    features = []
    for i in indices:
        require(time.monotonic() < deadline, "compute_stop")
        features.append(past_features(past, plan, i, base.INPUT_PIN))
    train = load_closes(source, required_dates(plan, plan.train_indices, forward=True))
    labels = []
    for i in plan.train_indices:
        require(time.monotonic() < deadline, "compute_stop")
        labels.append(forward_target(train, plan, i, base.INPUT_PIN))
    return prepare_arrays(features, labels, plan)


def make_gru():
    import torch

    class VarianceGRU(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = torch.nn.GRU(3, 32, num_layers=1, batch_first=True, dropout=0,
                                   device="cpu", dtype=torch.float32)
            self.output = torch.nn.Linear(32, 3, device="cpu", dtype=torch.float32)

        def forward(self, x):
            sequence, _ = self.gru(x.transpose(1, 2))
            return self.output(sequence[:, -1])
    return VarianceGRU()


def fit_ols(prepared, *, deadline, progress):
    from threadpoolctl import threadpool_limits

    require(time.monotonic() < deadline, "compute_stop")
    start = time.monotonic()
    train = np.column_stack((np.ones(len(prepared.labels)), prepared.train_har))
    with threadpool_limits(limits=2):
        coefficients, _, rank, singular = np.linalg.lstsq(train, prepared.labels, rcond=None)
        progress()
        require(np.isfinite(coefficients).all(), "fit_nonfinite")
        require(time.monotonic() < deadline, "compute_stop")
        prediction = np.column_stack((np.ones(len(prepared.dev_har)),
                                       prepared.dev_har)) @ coefficients
    buffer = io.BytesIO()
    np.savez(buffer, coefficients=coefficients, rank=np.asarray(rank), singular_values=singular)
    require(time.monotonic() < deadline, "compute_stop")
    return prediction.tolist(), buffer.getvalue(), dict(seconds=time.monotonic() - start,
                                                        rank=int(rank))


def fit_gru(prepared, *, deadline, progress):
    import torch
    from safetensors.torch import save

    require(time.monotonic() < deadline, "compute_stop")
    require(torch.cuda.is_available(), "cuda_unavailable")
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.manual_seed(SEED)
    model = make_gru().to("cuda")
    require(sum(p.numel() for p in model.parameters()) == 3651, "gru_parameters")
    x = torch.from_numpy(np.array(prepared.train_x, copy=True)).to("cuda")
    center = np.asarray(prepared.scaler["target_log_mean"], dtype="<f8")
    y = torch.from_numpy((prepared.labels - center).astype("<f4")).to("cuda")
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.01)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    start = time.monotonic()
    model.train()
    for update in range(1, UPDATES + 1):
        require(time.monotonic() < deadline, "compute_stop")
        optimizer.zero_grad(set_to_none=True)
        loss = torch.nn.functional.mse_loss(model(x), y)
        require(bool(torch.isfinite(loss).item()), "fit_nonfinite")
        loss.backward()
        optimizer.step()
        if update % 128 == 0:
            torch.cuda.synchronize()
            progress(update)
    require(all(bool(torch.isfinite(p).all().item()) for p in model.parameters()), "fit_nonfinite")
    require(time.monotonic() < deadline, "compute_stop")
    model.eval()
    with torch.inference_mode():
        dev = torch.from_numpy(np.array(prepared.dev_x, copy=True)).to("cuda")
        prediction = model(dev).cpu().numpy().astype("<f8") + center
    torch.cuda.synchronize()
    resources = dict(seconds=time.monotonic() - start, updates=UPDATES,
                     peak_vram_bytes=int(torch.cuda.max_memory_allocated()))
    weights = save({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()})
    require(time.monotonic() < deadline, "compute_stop")
    return prediction.tolist(), weights, resources


def forecast_variance(logs, count):
    values = np.asarray(logs, dtype="<f8")
    require(values.shape == (count, 3) and np.isfinite(values).all(), "forecast_numeric")
    with np.errstate(over="raise", invalid="raise"):
        result = np.exp(values)
    require(np.isfinite(result).all() and (result > 0).all(), "forecast_numeric")
    return result


def load_dev_targets(source, plan, *, deadline=float("inf")):
    rows = load_closes(source, required_dates(plan, plan.dev_indices, forward=True))
    targets = []
    for i in plan.dev_indices:
        require(time.monotonic() < deadline, "compute_stop")
        targets.append(forward_target(rows, plan, i, base.INPUT_PIN))
    return np.asarray(targets, dtype="<f8")


def evaluate(targets, predictions, plan):
    require(predictions["plan"] == plan.record() and set(predictions["log_forecasts"])
            == set(CANDIDATES), "prediction_plan")
    count = len(plan.dev_indices)
    targets = np.asarray(targets, dtype="<f8")
    require(targets.shape == (count, 3) and np.isfinite(targets).all()
            and (targets >= FLOOR).all(), "target_numeric")
    forecasts = {m: forecast_variance(predictions["log_forecasts"][m], count) for m in CANDIDATES}
    baseline = np.asarray(predictions["baseline"], dtype="<f8")
    require(baseline.shape == (count, 3) and np.isfinite(baseline).all()
            and (baseline >= FLOOR).all(), "baseline_binding")
    forecasts["baseline"] = baseline
    cells = []
    with np.errstate(over="raise", divide="raise", invalid="raise"):
        for method in METHODS:
            ratio = targets / forecasts[method]
            losses = dict(qlike=ratio - np.log(ratio) - 1,
                          log_mse=(np.log(targets) - np.log(forecasts[method]))**2)
            require(all(np.isfinite(v).all() for v in losses.values()), "metric_numeric")
            for block, section in ((0, slice(None, plan.block_cut)),
                                   (1, slice(plan.block_cut, None))):
                metrics = {k: str(float(v[section].mean())) for k, v in losses.items()}
                cells.append(dict(block=block, method=method, status="complete", metrics=metrics,
                    asset_metrics={s: {k: str(float(v[section, a].mean()))
                        for k, v in losses.items()} for a, s in enumerate(base.INSTRUMENT_ORDER)},
                    decision_count=len(targets[section]), asset_count=3, horizon_sessions=21,
                    target_sha256=lifecycle.input_hash(targets[section])))
    return cells


def criterion(cells):
    require(len(cells) == 6 and {(c["block"], c["method"]) for c in cells}
            == {(b, m) for b in (0, 1) for m in METHODS}
            and all(c["status"] == "complete" for c in cells), "cell_matrix")
    require(all(type(c["metrics"][k]) is str and Decimal(c["metrics"][k]).is_finite()
                for c in cells for k in METRICS), "cell_metrics")
    verdicts = {}
    with localcontext(base.CONTEXT):
        for candidate in CANDIDATES:
            controls = ("baseline",) if candidate == "ols" else ("baseline", "ols")
            passed = all(Decimal(next(c for c in cells if c["block"] == b and
                c["method"] == control)["metrics"][metric]) - Decimal(next(c for c in cells
                if c["block"] == b and c["method"] == candidate)["metrics"][metric]) > TOLERANCE
                for b in (0, 1) for control in controls for metric in METRICS)
            verdicts[candidate] = "development_survivor" if passed else "rejected"
    return verdicts


def runtime_identity():
    import torch

    versions = base.runtime_identity()
    for name in ("numpy", "torch", "safetensors"):
        versions[name] = importlib.metadata.version(name)
    versions["cuda"] = torch.version.cuda
    return versions


def _root(root, artifact_root):
    root, artifact_root = Path(root).absolute(), Path(artifact_root).absolute()
    require(root == artifact_root / "research" / NAME and root.is_dir(), "study_root")
    base.reject_repo_artifact_path(root, REPO)
    return root


def read_contract(root, artifact_root, pin):
    root = _root(root, artifact_root)
    contract = base._json(root / "precommit.json", pin)
    require(contract["name"] == NAME and contract["config"] == configuration(), "contract_config")
    require(contract["runtime"] == runtime_identity() == RUNTIME, "runtime_identity")
    require(Path(contract["source_root"]).absolute() == REPO, "frozen_source_root")
    require(set(contract["code_sha256"]) >= set(CODE), "code_pins")
    for relative, expected in contract["code_sha256"].items():
        require(digest(base._read(base._relative(REPO, relative))) == expected, "code_changed")
    commitment = base._json(base._relative(artifact_root, base.INPUT_RELATIVE), base.INPUT_PIN)
    require(contract["input_commitment_sha256"] == base.INPUT_PIN
            and commitment["calendar_sha256"] == base.CALENDAR_PIN
            and commitment["kind"] == "kis-cross-asset-d1-price-only-input-v1"
            and commitment["no_date_fill"] is True, "input_identity")
    require(all(contract["code_sha256"].get(p) == h for p, h in commitment["source_pins"].items()),
            "producer_code_pins")
    geometry = base._json(base._relative(artifact_root, GEOMETRY_RELATIVE), GEOMETRY_PIN)
    require(geometry["goal"] == NAME and geometry["input"]["sha256"] == base.INPUT_PIN
            and geometry["calendar"]["sha256"] == base.CALENDAR_PIN
            and geometry["train"]["entry_count"] == 503
            and geometry["dev"]["view_entry_counts"] == [12, 21]
            and geometry["geometry"]["required_source_date_count"] == 1276, "geometry_binding")
    return contract, commitment


def _artifacts(root):
    return {name: digest(base._read(root / name)) for name in ARTIFACTS if (root / name).exists()}


def _progress_specs():
    return {PROGRESS[0]: (0, 1, None, None), PROGRESS[1]: (1, 1, None, "lstsq_returned"),
        PROGRESS[2]: (1, 2, None, None), PROGRESS[3]: (2, 2, UPDATES, "512_optimizer_updates")} | {
            f"progress-gru-{n:04d}.json": (2 if n == UPDATES else 1, 2, n, None)
            for n in (128, 256, 384, 512)}


def _verify_progress(root, result, pin):
    for name, (fits, starts, updates, completion) in _progress_specs().items():
        if name in result["artifact_sha256"]:
            record = dict(contract_sha256=pin, completed_fits=fits,
                          fit_starts=starts, updates=updates)
            if completion is not None:
                record["training_completion"] = completion
            require(base._json(root / name, canonical=True) == record
                and result["actual_fits"] >= fits and result["fit_starts"] >= starts,
                "progress_binding")


def _safe(result):
    return {k: result[k] for k in ("status", "reason", "phase", "actual_fits", "fit_starts",
                                 "contract_sha256", "elapsed_seconds", "criterion")} | dict(
        cells=len(result["cells"]), result_sha256=digest(encode(result)),
        paper_input=False, holdout_access="none", financial_nav_claim=False)


def run(root, market_root, artifact_root, pin):
    start, deadline = time.monotonic(), time.monotonic() + SECONDS
    contract, commitment = read_contract(root, artifact_root, pin)
    root = _root(root, artifact_root)
    require(not _artifacts(root) and not (root / "worker-result.json").exists(), "attempt_exists")
    base.atomic_new(root / "started.json", dict(contract_sha256=pin, input_sha256=base.INPUT_PIN))
    result = dict(status="failed", reason="worker_failed", phase="source_input", actual_fits=0,
        fit_starts=0, contract_sha256=pin, elapsed_seconds=0, criterion={}, cells=[],
        artifact_sha256={}, resources={})

    def progress(name):
        fits, starts, updates, completion = _progress_specs()[name]
        record = dict(contract_sha256=pin, completed_fits=fits, fit_starts=starts, updates=updates)
        if completion is not None:
            record["training_completion"] = completion
        base.atomic_new(root / name, record)

    def ols_completed():
        result["actual_fits"] = 1
        progress("progress-ols-complete.json")

    def gru_progress(update):
        require(update in (128, 256, 384, 512), "progress_update")
        if update == UPDATES:
            result["actual_fits"] = 2
        progress(f"progress-gru-{update:04d}.json")
        if update == UPDATES:
            progress("progress-gru-complete.json")

    try:
        source = base.load_committed_source(commitment, artifact_root, market_root,
                                             deadline=deadline)
        plan = build_plan(source.plan.sessions)
        require(plan.record() == contract["plan"], "plan_changed")
        result["phase"] = "prepare"
        prepared = prepare_inputs(source, plan, deadline=deadline)
        base.atomic_new(root / "scaler.json", prepared.scaler)
        result["phase"], result["fit_starts"] = "fit_ols", 1
        progress("progress-ols-start.json")
        ols, weights, resources = fit_ols(prepared, deadline=deadline, progress=ols_completed)
        result["resources"]["ols"] = resources
        lifecycle.atomic_bytes(root / "ols.npz", weights)
        result["phase"], result["fit_starts"] = "fit_gru", 2
        progress("progress-gru-start.json")
        gru, weights, resources = fit_gru(prepared, deadline=deadline, progress=gru_progress)
        result["resources"]["gru"] = resources
        lifecycle.atomic_bytes(root / "gru.safetensors", weights)
        result["phase"] = "prediction_seal"
        for forecast in (ols, gru):
            forecast_variance(forecast, len(plan.dev_indices))
        predictions = dict(contract_sha256=pin, input_sha256=base.INPUT_PIN, plan=plan.record(),
            scaler_sha256=digest(encode(prepared.scaler)), model_sha256={name: digest(
                base._read(root / name)) for name in ("ols.npz", "gru.safetensors")},
            log_forecasts=dict(ols=ols, gru=gru), baseline=prepared.baseline.tolist(),
            inference_kind="original_worker")
        base.atomic_new(root / "predictions.json", predictions)
        require(time.monotonic() < deadline, "compute_stop")
        result["phase"] = "forward_input"
        targets = load_dev_targets(source, plan, deadline=deadline)
        result["phase"] = "evaluate"
        cells = evaluate(targets, predictions, plan)
        result["phase"] = "validate"
        verdict = criterion(cells)
        require(base.load_committed_source(commitment, artifact_root, market_root,
                    deadline=deadline).files == source.files, "source_changed")
        require(time.monotonic() < deadline, "compute_stop")
        result.update(status="complete", reason=None, cells=cells, criterion=verdict)
    except Exception as error:
        unavailable = {"required_date_gap", "required_price", "required_session_missing",
            "required_session_duplicate", "required_row_binding", "price_close_invalid",
            "price_basis_invalid", "return_numeric", "target_numeric", "feature_numeric"}
        allowed = unavailable | {"compute_stop", "source_changed", "plan_changed", "feature_shape",
            "fit_nonfinite", "cuda_unavailable", "forecast_numeric", "metric_numeric"}
        code = str(error) if isinstance(error, (base.StudyFault, CrossAssetInputUnavailable)) \
            and str(error) in allowed else "numeric_range" if isinstance(error, (
                ArithmeticError, np.linalg.LinAlgError)) else "worker_failed"
        result.update(reason=code, status="input_unavailable" if code in unavailable else "failed")
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
        and predictions["baseline"] == prepared.baseline.tolist()
        and predictions["inference_kind"] == "original_worker"
        and predictions["model_sha256"] == {name: result["artifact_sha256"][name]
            for name in ("ols.npz", "gru.safetensors")}, "prediction_binding")
    cells = evaluate(load_dev_targets(source, plan, deadline=deadline), predictions, plan)
    require(encode(cells) == encode(result["cells"]) and criterion(cells) == result["criterion"],
            "numeric_replay")
    require(base.load_committed_source(commitment, artifact_root, market_root,
                deadline=deadline).files == source.files, "source_changed")
    require(time.monotonic() < deadline, "compute_stop")
    return _safe(result) | dict(replay="exact_metrics/cached_prediction_binding", fits=0,
                               inference=0, searches=0, writes=0)


def synthetic_smoke():
    import torch

    plan = build_plan()
    n, m = len(plan.train_indices), len(plan.dev_indices)
    rng = np.random.default_rng(SEED)
    raw = rng.normal(0, .01, (n + m, 3, 63))
    targets = np.full((n, 3), .0001)
    prepared = prepare_arrays(raw, targets, plan)
    threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        with torch.random.fork_rng(devices=[]):
            torch.default_generator.manual_seed(SEED)
            model = make_gru()
            require(sum(p.numel() for p in model.parameters()) == 3651, "gru_parameters")
            tensor = torch.from_numpy(np.array(prepared.train_x, copy=True))
            elapsed = []
            for _ in range(3):
                model.zero_grad(set_to_none=True)
                start = time.monotonic()
                loss = model(tensor).square().mean()
                require(bool(torch.isfinite(loss).item()), "smoke_model")
                loss.backward()
                elapsed.append(time.monotonic() - start)
    finally:
        torch.set_num_threads(threads)
    logs = np.log(prepared.baseline).tolist()
    predictions = dict(plan=plan.record(), baseline=prepared.baseline.tolist(),
                       log_forecasts=dict(ols=logs, gru=logs))
    cells = evaluate(prepared.baseline, predictions, plan)
    require(len(cells) == 6 and set(criterion(cells).values()) == {"rejected"}, "smoke_matrix")
    return dict(status="smoke_passed", train_entries=n, dev_entries=m, view_entries=[12, 21],
        cells=6, metric_values=12, actual_market_reads=0, actual_fits=0, fit_starts=0,
        optimizer_steps=0, gpu=False, cpu_gru_parameters=3651,
        synthetic_cpu_forward_backward_seconds=elapsed,
        timing_scope="synthetic CPU kernels only, NOT CUDA allowance guarantee", paper_input=False)


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
        parser.error("run/verify require roots+contract pin; "
                     "verify requires result pin; smoke none")
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
