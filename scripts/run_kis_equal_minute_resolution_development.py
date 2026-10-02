"""One finite, seen-data resolution comparison; parent owns Docker and registry."""

from __future__ import annotations

import json
import runpy
import signal
import socket
import sys
import time
from contextlib import nullcontext
from decimal import Decimal, localcontext
from itertools import product
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402

from thericher_v2.data import kis_paper_intraday as data  # noqa: E402
from thericher_v2.data import select_complete_kis_paper_private_intraday_sessions  # noqa: E402
from thericher_v2.research import kis_equal_minute_resolution as r  # noqa: E402
from thericher_v2.research.engine_research_agent import (  # noqa: E402
    GpuFileLock,
    resolve_agent_root,
)
from thericher_v2.research.kis_intraday_window_matrix import _fit_logistic  # noqa: E402
from thericher_v2.research.sequence_architecture_models import (  # noqa: E402
    build_torch_sequence_model,
)

REPO = Path(__file__).resolve().parents[1]
h = SimpleNamespace(**runpy.run_path(
    str(REPO / "scripts/run_tiingo_monthly_frozen_policy_readback.py")))
NAME, SECONDS, MEMORY = "kis-equal-minute-resolution-development-v1", 300, 6 * 1024**3
INDEX_METADATA_MAX_BYTES = 8 * 1024**2  # Historical index measured at 4,232,279 bytes.
HELPER = "sha256:5adb809155c2f63011e2d9f753d5642882f9d9af8dd04219db17c62dd8b1fc17"
TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
GEOMETRIES = tuple(product(r.CONTEXTS, r.TIMEFRAMES))
CODE = tuple(dict.fromkeys((*h.CODE, "scripts/run_kis_equal_minute_resolution_development.py",
    "src/thericher_v2/research/kis_equal_minute_resolution.py",
    "src/thericher_v2/research/kis_intraday_window_matrix.py",
    "src/thericher_v2/research/sequence_architecture_models.py",
    "src/thericher_v2/data/kis_paper_intraday.py",
    "src/thericher_v2/data/kis_paper_intraday_index_metadata.py",
    "src/thericher_v2/data/local.py", "src/thericher_v2/data/resample.py",
    "src/thericher_v2/data/us_equity_session.py",
    "src/thericher_v2/execution/kis_market_data.py",
    "src/thericher_v2/execution/kis_private_intraday_backfill.py")))
encode, digest, require, atomic = h.encode, h.digest, h.require, h.study.atomic_new


def configuration():
    return dict(index_metadata_max_bytes=INDEX_METADATA_MAX_BYTES,
        train=[str(d) for d in r.TRAIN_DATES], purge="2026-07-07",
        comparison=[str(d) for d in r.COMPARISON_DATES], latest_five="excluded/already seen",
        geometries=[[w, tf.value] for w, tf in GEOMETRIES], anchors=list(r.OFFSETS),
        target="M1 OPEN C+1 to M1 OPEN C+31; TRAIN label gross_bps>6",
        policies=list(r.POLICIES), costs_per_side_bps=["3", "4.5", "6"],
        cost_basis="fee1bp+slippage2bp each side; multipliers1/1.5/2; no cost tuning",
        cells=120, decisions_per_symbol=20, patterns=32, effective_blocks=5,
        linear="pooled80TRAIN;features4;TRAINmean/std min1e-12;zero-init64steps/lr.05",
        tcn=dict(hidden=16, channels=4, kernel="full window", seed=103, epochs=8,
                 optimizer="Adam", lr="0.001", weight_decay="0", objective="BCEWithLogits",
                 batch=80, architecture="single Conv1d4->16/paddingK-1/crop/last/ReLU/Linear16->1"),
        threshold="logit>0; momentum aggregate feature0>0; final epoch only",
        normalization="TRAIN only: aggregated4 for linear, real sequence positions for TCN",
        budget=dict(linear_fits=4, tcn_fits=4, attempts=1, seconds=SECONDS,
                    cpu_threads=2, memory_bytes=MEMORY), image=h.IMAGE,
        kills=dict(
            nonpositive_stress_net="cost2 TCN M1 mean over2symbols/2contexts/5days/4cutoffs<=0",
            nonpositive_resolution_delta="cost2 TCN M1-minus-M5 daily mean over symbols/contexts;"
                "sum over5days<=0",
            single_day_dependence="drop each comparison day; remaining4-day resolution delta"
                "mean<=0; no TRAIN refit",
            positive_concentration="cost2 TCN resolution daily deltas: sum positive parts=0 or"
                "largest delta>50% of sum positive parts; not net-profit concentration"),
        descriptive="12 contrasts=2contexts*2learned policies*3costs;5paired day blocks;"
            "32 sign patterns;max absolute signed mean over12 contrasts;"
            "fraction(pattern statistic>=observed max absolute mean)/32;not a p-value",
        limitations="seen/revised/non-PIT; capacity confounded; descriptive patterns not p-values",
        scope="no selection/weights/portfolio NAV/broker PnL/holdout/Paper/promotion")


def source_metadata(root, pin):
    require(h._hash(pin), "index_pin")
    raw = h._read(root / "v1/index.json", limit=INDEX_METADATA_MAX_BYTES)
    require(digest(raw) == pin, "index_changed")
    index = json.loads(raw, object_pairs_hook=h._object, parse_constant=h._invalid_constant)
    metadata = data.validate_kis_paper_private_intraday_v1_index_metadata(
        index, expected_targets=TARGETS)
    sources = []
    for symbol, exchange in TARGETS:
        target = next(t for t in metadata.targets if (t.symbol, t.exchange) == (symbol, exchange))
        lineage = [dict(manifest_hash=c.manifest_hash, raw_sha256=c.raw_sha256)
            for c in target.retained_chunks if data._is_consumable_retained_chunk(
                outcome=c.outcome, reason=c.reason, conflict_origin=c.conflict_origin)]
        require(bool(lineage), "source_empty")
        sources.append(dict(symbol=symbol, exchange=exchange,
            dataset_id=f"kis.paper.private.intraday.{symbol.lower()}.{exchange.lower()}.m1.v1",
            dataset_sha256=data._dataset_hash(index_bytes=raw, lineage=lineage)))
    return dict(index_sha256=pin, streams=sources)


def paths(artifacts, inputs):
    for root in (artifacts, inputs):
        h._unlinked_path(root)
        require(root.is_dir() and not root.resolve().is_relative_to(REPO), "external_root")
    output = artifacts / "research" / NAME
    require(not inputs.resolve().is_relative_to(output.resolve())
            and not output.resolve().is_relative_to(inputs.resolve()), "input_output_overlap")
    h._unlinked_path(output.parent)
    return output


def runtime():
    versions = h.study.runtime_versions()
    require(versions["torch"] == "2.7.0+cu128" and Path("/.dockerenv").is_file(), "pinned_Docker")
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    memory = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    require(quota != "max" and 0 < int(quota) <= 2 * int(period), "CPU_bound")
    require(memory != "max" and 0 < int(memory) <= MEMORY
            and Path("/sys/fs/cgroup/memory.swap.max").read_text().strip() == "0", "memory_bound")
    require({n for _, n in socket.if_nameindex()} == {"lo"}, "network_none")
    return versions


def proposed(inputs, index_pin):
    helper_path = REPO / "src/thericher_v2/research/kis_equal_minute_resolution.py"
    require(digest(h._read(helper_path)) == HELPER, "frozen_helper_changed")
    return dict(name=NAME, config=configuration(), runtime=runtime(),
        source=source_metadata(inputs, index_pin),
        code_sha256={p: digest(h._read(REPO / p)) for p in CODE})


def freeze(artifacts, inputs, index_pin):
    output, contract = paths(artifacts, inputs), proposed(inputs, index_pin)
    output.mkdir(exist_ok=True)
    h._unlinked_path(output)
    require(not any(output.iterdir()), "output_not_empty")
    atomic(output / "precommit.json", contract)
    return digest(encode(contract))


def verify(artifacts, inputs, pin):
    require(h._hash(pin), "contract_pin")
    output = paths(artifacts, inputs)
    contract = h._json(output / "precommit.json", pin)
    require(encode(contract) == encode(proposed(inputs, contract["source"]["index_sha256"])),
            "contract_changed")
    return output, contract


def fit_tcn(torch, train, labels, comparison, kernel, device, deadline):
    require(train.shape == (80, kernel, 4) and comparison.shape == (40, kernel, 4)
            and train.dtype == comparison.dtype == np.float32 and labels.shape == (80,)
            and np.isin(labels, (0, 1)).all() and np.isfinite(train).all()
            and np.isfinite(comparison).all(), "model_shape")
    torch.manual_seed(103)
    model = build_torch_sequence_model(torch=torch, architecture_id="causal_tcn", feature_count=4,
        hidden_size=16, attention_heads=1, tcn_kernel_size=kernel).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=.001, weight_decay=0)
    x = torch.tensor(train, device=device)
    y = torch.tensor(labels, dtype=torch.float32, device=device)
    before = [p.detach().clone() for p in model.parameters()]
    for _ in range(8):
        require(time.monotonic() < deadline, "hard_timeout")
        optimizer.zero_grad(set_to_none=True)
        logits = model(x).squeeze(-1)
        require(tuple(logits.shape) == (80,), "logit_shape")
        loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, y)
        require(bool(torch.isfinite(loss)), "nonfinite_loss")
        loss.backward()
        optimizer.step()
    model.eval()
    with torch.no_grad():
        result = model(torch.tensor(comparison, device=device)).squeeze(-1).cpu().numpy()
    require(result.shape == (40,) and np.isfinite(result).all()
            and any(not torch.equal(a, b) for a, b in zip(before, model.parameters(), strict=True)),
            "model_update")
    return result, sum(p.numel() for p in model.parameters())


def gross_bps(window, catalogs):
    bars = catalogs[window.key.symbol]
    with localcontext() as ctx:
        ctx.prec = 50
        return 10000 * (bars[window.key.exit].open / bars[window.key.entry].open - 1)


def actions(torch, windows, catalogs, device, deadline, counts):
    cohorts = [tuple(w for w in windows if (w.context_minutes, w.timeframe) == g)
               for g in GEOMETRIES]
    common = {w.key for w in cohorts[0] if w.key.session_date in r.COMPARISON_DATES}
    require(len(windows) == 480 and len(common) == 40 and all(
        len(c) == 120 and {w.key for w in c if w.key.session_date in r.COMPARISON_DATES} == common
        for c in cohorts), "common_cohort")
    result, parameters = {}, []
    for (minutes, tf), cohort in zip(GEOMETRIES, cohorts, strict=True):
        train = tuple(w for w in cohort if w.key.session_date in r.TRAIN_DATES)
        comparison = tuple(w for w in cohort if w.key.session_date in r.COMPARISON_DATES)
        require(len(train) == 80 and len(comparison) == 40, "split_counts")
        norm = r.train_sequence_normalization(train)
        labels = np.asarray([int(gross_bps(w, catalogs) > 6) for w in train])
        counts["linear"] += 1
        require(time.monotonic() < deadline, "hard_timeout")
        linear = _fit_logistic(train, labels.tolist())
        x = np.asarray([w.features for w in comparison], dtype=np.float64)
        logits = (x - linear.means) / linear.scales @ np.asarray(linear.weights) + linear.bias
        require(logits.shape == (40,) and np.isfinite(logits).all(), "linear_shape")
        seq = [np.asarray([r.normalize_sequence(w, norm) for w in stream], dtype=np.float32)
               for stream in (train, comparison)]
        kernel = r.tcn_kernel_size(train[0])
        counts["tcn"] += 1
        tcn, parameter_count = fit_tcn(torch, seq[0], labels, seq[1], kernel, device, deadline)
        parameters.append(dict(context_minutes=minutes, timeframe=tf.value, kernel=kernel,
                               tcn_parameters=parameter_count))
        for i, w in enumerate(comparison):
            for policy, action in zip(r.POLICIES,
                    (w.features[0] > 0, logits[i] > 0, tcn[i] > 0, False, True), strict=True):
                result.setdefault((w.key.symbol, minutes, tf, policy), {})[w.key] = bool(action)
    require(counts == dict(linear=4, tcn=4), "fit_budget")
    return result, parameters


def score(decisions, catalogs):
    returns, cells = {}, []
    with localcontext() as ctx:
        ctx.prec = 50
        for symbol, minutes, tf, policy, cost in product(
                ("QQQ", "SPY"), r.CONTEXTS, r.TIMEFRAMES, r.POLICIES, r.MULTIPLIERS):
            chosen = decisions[symbol, minutes, tf, policy]
            values = {key: (gross_bps(SimpleNamespace(key=key), catalogs) - 6 * cost) * int(action)
                      for key, action in chosen.items()}
            returns[r.CellKey(symbol, minutes, tf, policy, cost)] = values
            cells.append(dict(symbol=symbol, context_minutes=minutes, timeframe=tf.value,
                policy=policy, cost_multiplier=str(cost), decisions=20,
                mean_net_unit_bps=str(sum(values.values(), Decimal(0)) / 20),
                trade_count=sum(chosen.values())))
        summary = r.summarize_resolution(returns)
    return dict(cells=cells, descriptive=dict(cells=summary.cell_count, blocks=summary.block_count,
        patterns=summary.pattern_count, family_tail_fraction=str(summary.family_tail_fraction),
        kill_categories=list(summary.kill_categories)))


def cpu_smoke(torch, deadline):
    kernels = [minutes // (tf.duration // r.MINUTE) for minutes, tf in GEOMETRIES]
    rng = np.random.default_rng(103)
    for kernel in kernels:
        train, comparison = [rng.normal(size=(n, kernel, 4)).astype(np.float32) for n in (80, 40)]
        labels = np.asarray([0, 1] * 40)
        a, count = fit_tcn(torch, train, labels, comparison, kernel, "cpu", deadline)
        b, _ = fit_tcn(torch, train, labels, comparison, kernel, "cpu", deadline)
        require(np.array_equal(a, b) and count == 16 * (4 * kernel + 1) + 17, "smoke_determinism")
        samples = tuple(SimpleNamespace(features=tuple(row)) for row in train.mean(axis=1))
        require(_fit_logistic(samples, labels.tolist()) == _fit_logistic(samples, labels.tolist()),
                "linear_determinism")
    return dict(kernels=kernels, synthetic_tcn_fits=8, actual_fits=0)


def validate_result(value, pin, phase):
    complete = value.get("status") == "complete"
    base = ("name", "contract_sha256", "phase", "status", "fits_started")
    extras = ("smoke",) if phase == "cpu-smoke" else ("parameters", "cells", "descriptive")
    h._fields(value, (*base, *(extras if complete else ())))
    require(value["name"] == NAME and value["contract_sha256"] == pin and value["phase"] == phase
            and value["status"] in ("complete", "failed"), "result_binding")
    if not complete and value["fits_started"] == "unobserved":
        return
    h._fields(value["fits_started"], ("linear", "tcn"))
    require(all(type(n) is int and 0 <= n <= 4 for n in value["fits_started"].values()),
            "fit_counts")
    if not complete:
        return
    if phase == "cpu-smoke":
        require(value["fits_started"] == dict(linear=0, tcn=0) and encode(value["smoke"]) == encode(
            dict(kernels=[30, 6, 120, 24], synthetic_tcn_fits=8, actual_fits=0)), "smoke_shape")
        return
    require(value["fits_started"] == dict(linear=4, tcn=4) and value["parameters"] == [
        dict(context_minutes=w, timeframe=tf.value, kernel=w // (tf.duration // r.MINUTE),
             tcn_parameters=16 * (4 * (w // (tf.duration // r.MINUTE)) + 1) + 17)
        for w, tf in GEOMETRIES], "parameter_counts")
    expected = product(("QQQ", "SPY"), r.CONTEXTS, r.TIMEFRAMES, r.POLICIES, r.MULTIPLIERS)
    require(len(value["cells"]) == 120, "cell_count")
    trades = {}
    for cell, (s, w, tf, p, c) in zip(value["cells"], expected, strict=True):
        h._fields(cell, ("symbol", "context_minutes", "timeframe", "policy", "cost_multiplier",
                        "decisions", "trade_count", "mean_net_unit_bps"))
        keys = ("symbol", "context_minutes", "timeframe", "policy", "cost_multiplier")
        require(encode([cell[k] for k in keys]) == encode([s, w, tf.value, p, str(c)])
                and type(cell["decisions"]) is int
                and cell["decisions"] == 20 and type(cell["trade_count"]) is int
                and 0 <= cell["trade_count"] <= 20
                and h._numeric(cell["mean_net_unit_bps"]).is_finite()
                and trades.setdefault((s, w, tf, p), cell["trade_count"]) == cell["trade_count"],
                "cell_shape")
    d = value["descriptive"]
    h._fields(d, ("cells", "blocks", "patterns", "family_tail_fraction", "kill_categories"))
    sizes = (("cells", 120), ("blocks", 5), ("patterns", 32))
    kills = d["kill_categories"]
    require(all(type(d[k]) is int and d[k] == n for k, n in sizes)
            and 0 <= h._numeric(d["family_tail_fraction"]) <= 1
            and type(kills) is list and all(type(k) is str for k in kills)
            and len(kills) == len(set(kills)) and set(kills) <= set(configuration()["kills"]),
            "descriptive_shape")


def worker(artifacts, inputs, pin, phase, deadline):
    output, contract = verify(artifacts, inputs, pin)
    require(h._json(output / (phase + "-started.json")) == dict(contract_sha256=pin), "attempt")
    counts = dict(linear=0, tcn=0)
    result = dict(name=NAME, contract_sha256=pin, phase=phase, status="failed", fits_started=counts)
    try:
        import torch
        require(str(torch.__version__) == contract["runtime"]["torch"], "torch_changed")
        torch.set_num_threads(2)
        torch.use_deterministic_algorithms(True)
        require(time.monotonic() < deadline, "hard_timeout")
        if phase == "cpu-smoke":
            result["smoke"] = cpu_smoke(torch, deadline)
        else:
            require(phase == "cuda" and torch.cuda.is_available(), "CUDA_required")
            windows, catalogs = [], {}
            for source in contract["source"]["streams"]:
                catalog = data.load_verified_kis_paper_private_intraday_catalog(cache_root=inputs,
                    repo_root=REPO, symbol=source["symbol"], exchange=source["exchange"],
                    expected_index_metadata_sha256=contract["source"]["index_sha256"])
                require(catalog.dataset_hash == source["dataset_sha256"]
                        and catalog.dataset_id == source["dataset_id"], "dataset_changed")
                selected = select_complete_kis_paper_private_intraday_sessions(catalog,
                    session_dates=r.TRAIN_DATES + r.COMPARISON_DATES)
                prepared = data.prepare_kis_paper_intraday_feature_input(selected,
                    session_dates=r.TRAIN_DATES + r.COMPARISON_DATES)
                windows.extend(r.build_equal_minute_windows(prepared))
                catalogs[source["symbol"]] = {bar.start_ts: bar for bar in selected.bars}
            decisions, result["parameters"] = actions(
                torch, windows, catalogs, "cuda:0", deadline, counts)
            result.update(score(decisions, catalogs))
        verify(artifacts, inputs, pin)
        require(time.monotonic() < deadline, "hard_timeout")
        result["status"] = "complete"
        validate_result(result, pin, phase)
    except Exception:
        result = dict(name=NAME, contract_sha256=pin, phase=phase, status="failed",
                      fits_started=counts)
    atomic(output / (phase + "-worker.json"), result)


def dispatch(artifacts, inputs, pin, phase, cpu_pin=None):
    deadline = time.monotonic() + SECONDS
    output, _ = verify(artifacts, inputs, pin)
    require(phase in ("cpu-smoke", "cuda"), "phase")
    allowed = {"precommit.json"}
    if phase == "cuda":
        require(h._hash(cpu_pin), "cpu_summary_pin")
        cpu = h._json(output / "cpu-smoke-summary.json", cpu_pin)
        validate_result(cpu, pin, "cpu-smoke")
        require(cpu["status"] == "complete", "CPU_binding")
        allowed |= {"cpu-smoke-started.json", "cpu-smoke-worker.json", "cpu-smoke-summary.json"}
    require({p.name for p in output.iterdir()} == allowed, "single_attempt")
    helper = REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"
    supervisor = runpy.run_path(str(helper))["supervise"]
    lock = (GpuFileLock(resolve_agent_root(artifacts) / "locks/gpu.lock")
            if phase == "cuda" else nullcontext())
    with lock:
        atomic(output / (phase + "-started.json"), dict(contract_sha256=pin))
        result = dict(name=NAME, contract_sha256=pin, phase=phase, status="failed",
                      fits_started="unobserved")
        try:
            job = supervisor(worker, (artifacts, inputs, pin, phase, deadline),
                             seconds=max(0, deadline - time.monotonic()), name=NAME + "-" + phase)
            require(job["timed_out"] is False and type(job["exit_code"]) is int
                    and job["exit_code"] == 0 and time.monotonic() < deadline, "worker_failed")
            candidate = h._json(output / (phase + "-worker.json"))
            validate_result(candidate, pin, phase)
            verify(artifacts, inputs, pin)
            require({p.name for p in output.iterdir()} == allowed | {phase + "-started.json",
                    phase + "-worker.json"} and time.monotonic() < deadline, "output_changed")
            result = candidate
        except (Exception, KeyboardInterrupt):
            try:
                candidate = h._json(output / (phase + "-worker.json"))
                validate_result(candidate, pin, phase)
                result["fits_started"] = candidate["fits_started"]
            except Exception:
                pass
        atomic(output / (phase + "-summary.json"), result)
    return dict(status=result["status"], phase=phase, contract_sha256=pin,
                summary_sha256=digest(encode(result)))


def main(argv=None):
    try:
        parser = h._Parser(description=__doc__, allow_abbrev=False)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--freeze", action="store_true")
        mode.add_argument("--phase", choices=("cpu-smoke", "cuda"))
        parser.add_argument("--artifact-root", type=Path, default=Path("/artifacts"))
        parser.add_argument("--input-root", type=Path, default=Path("/input"))
        parser.add_argument("--index-sha256")
        parser.add_argument("--contract-sha256")
        parser.add_argument("--cpu-summary-sha256")
        args = parser.parse_args(argv)
        if args.freeze:
            require(args.contract_sha256 is None and args.cpu_summary_sha256 is None, "arguments")
            result = dict(status="frozen_metadata_only", contract_sha256=freeze(
                args.artifact_root, args.input_root, args.index_sha256))
        elif args.phase:
            require(args.index_sha256 is None
                    and (args.phase == "cuda" or args.cpu_summary_sha256 is None),
                    "arguments")
            previous = signal.signal(signal.SIGTERM, h._interrupt)
            try:
                result = dispatch(args.artifact_root, args.input_root, args.contract_sha256,
                                  args.phase, args.cpu_summary_sha256)
            finally:
                signal.signal(signal.SIGTERM, previous)
        else:
            result = dict(status="preview", cells=120, fits=8, patterns=32, image=h.IMAGE)
    except (Exception, KeyboardInterrupt):
        result = dict(status="unavailable", raw_error_suppressed=True)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"] in ("preview", "frozen_metadata_only", "complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
