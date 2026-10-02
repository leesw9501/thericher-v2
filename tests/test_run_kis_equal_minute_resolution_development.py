"""Synthetic-only finite experiment and one-attempt orchestration tests."""

import copy
import importlib.util
import json
import socket
import sys
import time
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from test_kis_equal_minute_resolution import prepared as make_prepared
from test_kis_paper_intraday_index_metadata import _chunk_key, _valid_index
from thericher_v2.data.local import _cataloged_bars_from_verified_loader

SPEC = importlib.util.spec_from_file_location(
    "equal_resolution_runner",
    Path(__file__).resolve().parents[1] / "scripts/run_kis_equal_minute_resolution_development.py",
)
s = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = s
SPEC.loader.exec_module(s)
PIN = "sha256:" + "a" * 64


def forbidden(*_a, **_k):
    pytest.fail("actual source, GPU, network or weight IO forbidden")


@pytest.fixture(scope="module")
def torch():
    t = pytest.importorskip("torch")
    threads, deterministic = t.get_num_threads(), t.are_deterministic_algorithms_enabled()
    t.set_num_threads(2)
    t.use_deterministic_algorithms(True)
    yield t
    t.set_num_threads(threads)
    t.use_deterministic_algorithms(deterministic)


@pytest.fixture(autouse=True)
def isolate(monkeypatch, torch):
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(s.data, "load_verified_kis_paper_private_intraday_catalog", forbidden)
    monkeypatch.setattr(torch.cuda, "is_available", forbidden)
    monkeypatch.setattr(torch.cuda, "init", forbidden)
    monkeypatch.setattr(torch, "save", forbidden)
    for name in ("save", "savez", "savez_compressed"):
        monkeypatch.setattr(np, name, forbidden)


@pytest.fixture(scope="module")
def synthetic():
    prepared = make_prepared.__wrapped__()
    windows = tuple(w for p in prepared.values() for w in s.r.build_equal_minute_windows(p))
    catalogs = {symbol: {b.start_ts: b for b in p.catalog.bars} for symbol, p in prepared.items()}
    return SimpleNamespace(prepared=prepared, windows=windows, catalogs=catalogs)


@pytest.fixture(scope="module")
def experiment(torch, synthetic):
    counts = dict(linear=0, tcn=0)
    decisions, parameters = s.actions(
        torch, synthetic.windows, synthetic.catalogs, "cpu", time.monotonic() + 60, counts
    )
    result = dict(
        name=s.NAME,
        contract_sha256=PIN,
        phase="cuda",
        status="complete",
        fits_started=counts,
        parameters=parameters,
        **s.score(decisions, synthetic.catalogs),
    )
    s.validate_result(result, PIN, "cuda")
    return SimpleNamespace(result=result, decisions=decisions, parameters=parameters)


@pytest.fixture
def package(tmp_path, monkeypatch, torch):
    artifacts, inputs = tmp_path / "a", tmp_path / "i"
    (artifacts / "research").mkdir(parents=True)
    (inputs / "v1").mkdir(parents=True)
    index = _valid_index(key_kind="current")
    first, second = index["targets"]
    first.update(symbol="QQQ", exchange="NAS")
    second["chunks"] = [copy.deepcopy(first["chunks"][0])]
    chunk = second["chunks"][0]
    chunk["chunk_key"] = _chunk_key(
        target_key=second["target_key"],
        input_cursor=None,
        row_fingerprints=chunk["row_fingerprints"],
    )
    raw = s.encode(index)
    (inputs / "v1/index.json").write_bytes(raw)
    versions = s.h.study.runtime_versions()
    versions["torch"] = str(torch.__version__)
    monkeypatch.setattr(s, "runtime", lambda: dict(versions))
    return SimpleNamespace(
        artifacts=artifacts,
        inputs=inputs,
        index_pin=s.digest(raw),
        output=artifacts / "research" / s.NAME,
    )


def frozen(p):
    pin = s.freeze(p.artifacts, p.inputs, p.index_pin)
    return pin, s.verify(p.artifacts, p.inputs, pin)[1]


def cpu_result(pin):
    return dict(
        name=s.NAME,
        contract_sha256=pin,
        phase="cpu-smoke",
        status="complete",
        fits_started=dict(linear=0, tcn=0),
        smoke=dict(kernels=[30, 6, 120, 24], synthetic_tcn_fits=8, actual_fits=0),
    )


def cpu_complete(p, pin):
    result = cpu_result(pin)
    for suffix in ("started", "worker", "summary"):
        s.atomic(
            p.output / f"cpu-smoke-{suffix}.json",
            dict(contract_sha256=pin) if suffix == "started" else result,
        )
    return s.digest(s.encode(result))


def test_preview_never_reads_private_environment_files_or_runtime(monkeypatch, capsys):
    for name in ("runtime", "proposed", "paths", "freeze", "dispatch"):
        monkeypatch.setattr(s, name, forbidden)
    for name in ("open", "read_bytes", "read_text", "resolve"):
        monkeypatch.setattr(Path, name, forbidden)
    assert s.main([]) == 0
    assert json.loads(capsys.readouterr().out) == dict(
        status="preview", cells=120, fits=8, patterns=32, image=s.h.IMAGE
    )


def test_frozen_contract_metadata_only_exact_split_and_budget(package, monkeypatch):
    monkeypatch.setattr(s, "actions", forbidden)
    monkeypatch.setattr(s, "gross_bps", forbidden)
    pin, contract = frozen(package)
    assert s.digest((package.output / "precommit.json").read_bytes()) == pin
    assert len(contract["config"]["train"]) == 10
    assert len(contract["config"]["comparison"]) == 5
    assert contract["config"]["purge"] == "2026-07-07"
    assert contract["config"]["tcn"]["optimizer"] == "Adam"
    assert contract["config"]["tcn"]["weight_decay"] == "0"
    assert contract["config"]["kills"] == dict(
        nonpositive_stress_net="cost2 TCN M1 mean over2symbols/2contexts/5days/4cutoffs<=0",
        nonpositive_resolution_delta="cost2 TCN M1-minus-M5 daily mean over symbols/contexts;"
        "sum over5days<=0",
        single_day_dependence="drop each comparison day; remaining4-day resolution delta"
        "mean<=0; no TRAIN refit",
        positive_concentration="cost2 TCN resolution daily deltas: sum positive parts=0 or"
        "largest delta>50% of sum positive parts; not net-profit concentration",
    )
    assert contract["config"]["descriptive"] == (
        "12 contrasts=2contexts*2learned policies*3costs;5paired day blocks;"
        "32 sign patterns;max absolute signed mean over12 contrasts;"
        "fraction(pattern statistic>=observed max absolute mean)/32;not a p-value"
    )
    assert contract["config"]["budget"] == dict(
        linear_fits=4, tcn_fits=4, attempts=1, seconds=300, cpu_threads=2, memory_bytes=6 * 1024**3
    )
    assert [(v["symbol"], v["exchange"]) for v in contract["source"]["streams"]] == list(s.TARGETS)
    assert {p.name for p in package.output.iterdir()} == {"precommit.json"}
    with pytest.raises(ValueError, match="output_not_empty"):
        frozen(package)


@pytest.mark.parametrize("change", ["config", "runtime", "source", "code", "extra", "pin"])
def test_contract_changes_fail_before_prices(package, change):
    pin, contract = frozen(package)
    if change == "config":
        contract["config"]["tcn"]["epochs"] = 9
    elif change == "runtime":
        contract["runtime"]["torch"] = "foreign"
    elif change == "source":
        contract["source"]["streams"][0]["exchange"] = "NASD"
    elif change == "code":
        contract["code_sha256"][s.CODE[0]] = PIN
    elif change == "extra":
        contract["private"] = "synthetic"
    else:
        pin = PIN
    if change != "pin":
        (package.output / "precommit.json").write_bytes(s.encode(contract))
        pin = s.digest(s.encode(contract))
    with pytest.raises(ValueError):
        s.dispatch(package.artifacts, package.inputs, pin, "cpu-smoke")
    assert not (package.output / "cpu-smoke-started.json").exists()


def test_index_change_rejects_before_attempt(package):
    pin, _ = frozen(package)
    path = package.inputs / "v1/index.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="index_changed"):
        s.dispatch(package.artifacts, package.inputs, pin, "cpu-smoke")


@pytest.mark.parametrize("size", [2 * 1024**2 + 1, 4_232_279, 8 * 1024**2])
def test_index_metadata_local_cap_accepts_large_verified_json(package, size):
    path = package.inputs / "v1/index.json"
    raw = path.read_bytes()
    raw += b" " * (size - len(raw))
    path.write_bytes(raw)
    package.index_pin = s.digest(raw)
    with pytest.raises(ValueError, match="artifact_oversize"):
        s.h._read(path)
    pin, contract = frozen(package)
    assert contract["source"]["index_sha256"] == package.index_pin
    assert (
        contract["config"]["index_metadata_max_bytes"] == s.INDEX_METADATA_MAX_BYTES == 8 * 1024**2
    )
    assert s.verify(package.artifacts, package.inputs, pin)[1] == contract
    with pytest.raises(ValueError, match="index_changed"):
        s.source_metadata(package.inputs, PIN)


def test_index_metadata_oversize_fails_before_contract_or_fits(package, monkeypatch):
    monkeypatch.setattr(s, "actions", forbidden)
    path = package.inputs / "v1/index.json"
    raw = path.read_bytes()
    raw += b" " * (s.INDEX_METADATA_MAX_BYTES + 1 - len(raw))
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="artifact_oversize"):
        s.freeze(package.artifacts, package.inputs, s.digest(raw))
    assert not package.output.exists()


def test_cpu_smoke_real_models_all_kernels_no_real_input(torch):
    result = s.cpu_smoke(torch, time.monotonic() + 60)
    assert result == cpu_result(PIN)["smoke"]


def test_eight_pooled_fits_120_cells_32_paired_patterns(experiment):
    result = experiment.result
    assert result["fits_started"] == dict(linear=4, tcn=4)
    assert len(result["cells"]) == 120
    assert result["descriptive"]["patterns"] == 32 and result["descriptive"]["blocks"] == 5
    assert [p["kernel"] for p in result["parameters"]] == [30, 6, 120, 24]
    assert [p["tcn_parameters"] for p in result["parameters"]] == [1953, 417, 7713, 1569]
    assert all(c["decisions"] == 20 for c in result["cells"])
    forbidden_keys = {"rows", "labels", "predictions", "weights", "prices", "private"}
    assert not forbidden_keys.intersection(result)
    for start in range(0, 120, 3):
        batch = result["cells"][start : start + 3]
        assert len({c["trade_count"] for c in batch}) == 1
        assert all(
            Decimal(a["mean_net_unit_bps"]) >= Decimal(b["mean_net_unit_bps"])
            for a, b in zip(batch, batch[1:], strict=False)
        )


def test_train_only_logistic_and_sequence_normalization(torch, synthetic, monkeypatch):
    calls, norms = [], []
    original_fit, original_norm = s._fit_logistic, s.r.train_sequence_normalization

    def fit(samples, labels):
        assert len(samples) == len(labels) == 80
        assert {w.key.session_date for w in samples} == set(s.r.TRAIN_DATES)
        model = original_fit(samples, labels)
        np.testing.assert_allclose(model.means, np.asarray([w.features for w in samples]).mean(0))
        calls.append(model)
        return model

    def normalize(windows):
        norm = original_norm(windows)
        norms.append(norm)
        return norm

    monkeypatch.setattr(s, "_fit_logistic", fit)
    monkeypatch.setattr(s.r, "train_sequence_normalization", normalize)
    s.actions(
        torch,
        synthetic.windows,
        synthetic.catalogs,
        "cpu",
        time.monotonic() + 60,
        dict(linear=0, tcn=0),
    )
    assert len(calls) == len(norms) == 4
    assert [n.real_position_count for n in norms] == [2400, 480, 9600, 1920]


def test_comparison_actions_finish_before_any_comparison_payoff(torch, synthetic, monkeypatch):
    original = s.gross_bps
    comparison_allowed = False

    def gross(window, catalogs):
        assert comparison_allowed or window.key.session_date in s.r.TRAIN_DATES
        return original(window, catalogs)

    monkeypatch.setattr(s, "gross_bps", gross)
    decisions, _ = s.actions(
        torch,
        synthetic.windows,
        synthetic.catalogs,
        "cpu",
        time.monotonic() + 60,
        dict(linear=0, tcn=0),
    )
    comparison_allowed = True
    assert len(s.score(decisions, synthetic.catalogs)["cells"]) == 120


def test_future_payoff_bars_cannot_change_current_features_or_actions(torch, synthetic, experiment):
    prepared = synthetic.prepared["QQQ"]
    day = s.r.COMPARISON_DATES[0]
    cutoff = s.r.us_equity_2026_session(day).window.open_ts + 120 * s.r.MINUTE
    bars = tuple(
        replace(
            b,
            open=b.open * (3 if b.start_ts >= cutoff + 31 * s.r.MINUTE else 2),
            high=b.high * 4,
            close=b.close * 4,
        )
        if b.start_ts >= cutoff and b.start_ts.date() == day
        else b
        for b in prepared.catalog.bars
    )
    changed_catalog = _cataloged_bars_from_verified_loader(
        dataset_id=prepared.catalog.dataset_id,
        dataset_hash=prepared.catalog.dataset_hash,
        source_path=prepared.catalog.source_path,
        bars=bars,
    )
    changed = replace(prepared, catalog=changed_catalog)
    windows = tuple(
        w
        for symbol, p in synthetic.prepared.items()
        for w in s.r.build_equal_minute_windows(changed if symbol == "QQQ" else p)
    )
    catalogs = {**synthetic.catalogs, "QQQ": {b.start_ts: b for b in bars}}
    decisions, _ = s.actions(
        torch, windows, catalogs, "cpu", time.monotonic() + 60, dict(linear=0, tcn=0)
    )
    original = {
        (w.context_minutes, w.timeframe): w
        for w in synthetic.windows
        if w.key.symbol == "QQQ" and w.key.cutoff == cutoff
    }
    for w in windows:
        if w.key.symbol == "QQQ" and w.key.cutoff == cutoff:
            old = original[w.context_minutes, w.timeframe]
            assert old.features == w.features and old.sequence == w.sequence
            assert s.gross_bps(old, synthetic.catalogs) != s.gross_bps(w, catalogs)
            for p in s.r.POLICIES:
                key = "QQQ", w.context_minutes, w.timeframe, p
                assert experiment.decisions[key][w.key] == decisions[key][w.key]


@pytest.mark.parametrize("change", ["missing_window", "duplicate_key", "missing_target"])
def test_missing_support_cannot_produce_cell_subset(torch, synthetic, change):
    windows, catalogs = synthetic.windows, synthetic.catalogs
    if change == "missing_window":
        windows = windows[:-1]
    elif change == "duplicate_key":
        windows = list(windows)
        windows[-1] = replace(windows[-1], key=windows[-17].key)
    else:
        catalogs = {k: dict(v) for k, v in catalogs.items()}
        window = next(w for w in windows if w.key.session_date in s.r.TRAIN_DATES)
        catalogs[window.key.symbol].pop(window.key.exit)
    with pytest.raises((ValueError, KeyError)):
        s.actions(torch, windows, catalogs, "cpu", time.monotonic() + 60, dict(linear=0, tcn=0))


@pytest.mark.parametrize("field", ["shape", "dtype", "label", "nonfinite", "timeout"])
def test_strict_tcn_shape_or_budget_rejects(torch, field):
    train, comp, labels = (
        np.zeros((80, 6, 4), np.float32),
        np.zeros((40, 6, 4), np.float32),
        np.zeros(80),
    )
    deadline = time.monotonic() + 30
    if field == "shape":
        train = train[:, :-1]
    elif field == "dtype":
        train = train.astype(np.float64)
    elif field == "label":
        labels[0] = 2
    elif field == "nonfinite":
        comp[0, 0, 0] = np.nan
    else:
        deadline = 0
    with pytest.raises(ValueError):
        s.fit_tcn(torch, train, labels, comp, 6, "cpu", deadline)


@pytest.mark.parametrize(
    "change",
    [
        "extra",
        "cell_count",
        "identity",
        "fits",
        "bool",
        "params",
        "nonfinite",
        "cost_actions",
        "patterns",
    ],
)
def test_strict_aggregate_schema_rejects_mutations(experiment, change):
    value = copy.deepcopy(experiment.result)
    if change == "extra":
        value["weights"] = "synthetic-private"
    elif change == "cell_count":
        value["cells"].pop()
    elif change == "identity":
        value["cells"][0]["symbol"] = "IWM"
    elif change == "fits":
        value["fits_started"]["linear"] = 5
    elif change == "bool":
        value["cells"][0]["decisions"] = True
    elif change == "params":
        value["parameters"][0]["kernel"] = 1
    elif change == "nonfinite":
        value["cells"][0]["mean_net_unit_bps"] = "NaN"
    elif change == "cost_actions":
        value["cells"][1]["trade_count"] = 0 if value["cells"][0]["trade_count"] else 1
    else:
        value["descriptive"]["patterns"] = 31
    with pytest.raises(ValueError):
        s.validate_result(value, PIN, "cuda")


@pytest.mark.parametrize(
    "kills",
    [
        {},
        {"nonpositive_stress_net": True},
        {"nonpositive_stress_net"},
        ("nonpositive_stress_net",),
        [["nonpositive_stress_net"]],
        [{"nonpositive_stress_net": True}],
        [None],
        [1],
        ["foreign"],
        ["nonpositive_stress_net", "nonpositive_stress_net"],
    ],
)
def test_kill_categories_require_unique_whitelisted_string_list(experiment, kills):
    value = copy.deepcopy(experiment.result)
    value["descriptive"]["kill_categories"] = kills
    with pytest.raises(ValueError, match="descriptive_shape"):
        s.validate_result(value, PIN, "cuda")


def test_cpu_dispatch_is_single_attempt_synthetic_and_reaps_via_existing_supervisor(
    package, monkeypatch
):
    pin, _ = frozen(package)
    calls = []
    original = s.runpy.run_path

    def supervised(target, args, **kwargs):
        calls.append(kwargs)
        target(*args)
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(
        s.runpy,
        "run_path",
        lambda path: (
            {"supervise": supervised}
            if path.endswith("run_firstrate_m5_h30_lstm_dev_20260921.py")
            else original(path)
        ),
    )
    result = s.dispatch(package.artifacts, package.inputs, pin, "cpu-smoke")
    assert result["status"] == "complete" and len(calls) == 1
    assert 0 < calls[0]["seconds"] <= 300
    with pytest.raises(ValueError, match="single_attempt"):
        s.dispatch(package.artifacts, package.inputs, pin, "cpu-smoke")


@pytest.mark.parametrize("case", ["timeout", "nonzero", "foreign_pin", "extra_private", "late"])
def test_supervised_complete_candidate_cannot_override_failure(package, monkeypatch, case):
    pin, _ = frozen(package)

    def supervise(_target, args, **_kwargs):
        candidate = cpu_result(pin)
        if case == "foreign_pin":
            candidate["contract_sha256"] = PIN
        if case == "extra_private":
            candidate["private"] = "synthetic"
        s.atomic(package.output / "cpu-smoke-worker.json", candidate)
        if case == "late":
            monkeypatch.setattr(s.time, "monotonic", lambda: float("inf"))
        return dict(timed_out=case == "timeout", exit_code=1 if case == "nonzero" else 0)

    monkeypatch.setattr(s.runpy, "run_path", lambda _: {"supervise": supervise})
    assert s.dispatch(package.artifacts, package.inputs, pin, "cpu-smoke")["status"] == "failed"
    value = s.h._json(package.output / "cpu-smoke-summary.json")
    assert value["fits_started"] == (
        "unobserved" if case in ("foreign_pin", "extra_private") else dict(linear=0, tcn=0)
    )


@pytest.mark.parametrize("case", ["timeout", "nonzero", "exception", "missing", "foreign"])
def test_failed_cuda_never_invents_zero_fits(package, monkeypatch, case):
    pin, _ = frozen(package)
    cpu_pin = cpu_complete(package, pin)

    def supervise(_target, _args, **_kwargs):
        if case != "missing":
            candidate = dict(
                name=s.NAME,
                contract_sha256=PIN if case == "foreign" else pin,
                phase="cuda",
                status="failed",
                fits_started=dict(linear=3, tcn=2),
            )
            s.atomic(package.output / "cuda-worker.json", candidate)
        if case == "exception":
            raise RuntimeError("synthetic private error must not escape")
        return dict(timed_out=case == "timeout", exit_code=1 if case == "nonzero" else 0)

    monkeypatch.setattr(s, "GpuFileLock", lambda _: nullcontext())
    monkeypatch.setattr(s.runpy, "run_path", lambda _: {"supervise": supervise})
    assert s.dispatch(package.artifacts, package.inputs, pin, "cuda", cpu_pin)["status"] == "failed"
    result = s.h._json(package.output / "cuda-summary.json")
    assert result["fits_started"] == (
        "unobserved" if case in ("missing", "foreign") else dict(linear=3, tcn=2)
    )
    s.validate_result(result, pin, "cuda")
    assert "synthetic private" not in s.encode(result).decode()


def test_complete_result_cannot_claim_unobserved_fits(experiment):
    value = copy.deepcopy(experiment.result)
    value["fits_started"] = "unobserved"
    with pytest.raises(ValueError):
        s.validate_result(value, PIN, "cuda")


def test_cuda_uses_canonical_exclusive_lock_and_bound_cpu_summary(package, experiment, monkeypatch):
    pin, _ = frozen(package)
    cpu_pin = cpu_complete(package, pin)
    held, locks = [], []

    @contextmanager
    def lock(path):
        locks.append(path)
        held.append(True)
        try:
            yield
        finally:
            held.pop()

    def supervise(_target, _args, **_kwargs):
        assert held == [True]
        candidate = copy.deepcopy(experiment.result)
        candidate["contract_sha256"] = pin
        s.atomic(package.output / "cuda-worker.json", candidate)
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(s, "GpuFileLock", lock)
    monkeypatch.setattr(s.runpy, "run_path", lambda _: {"supervise": supervise})
    result = s.dispatch(package.artifacts, package.inputs, pin, "cuda", cpu_pin)
    assert result["status"] == "complete" and held == []
    assert locks == [s.resolve_agent_root(package.artifacts) / "locks/gpu.lock"]
    with pytest.raises(ValueError, match="single_attempt"):
        s.dispatch(package.artifacts, package.inputs, pin, "cuda", cpu_pin)


@pytest.mark.parametrize("case", ["missing", "pin", "failed"])
def test_cuda_requires_same_contract_cpu_receipt_before_lock(package, monkeypatch, case):
    pin, _ = frozen(package)
    cpu_pin = PIN
    if case != "missing":
        cpu_pin = cpu_complete(package, pin)
        if case == "pin":
            cpu_pin = PIN
        else:
            value = s.h._json(package.output / "cpu-smoke-summary.json")
            value["status"] = "failed"
            (package.output / "cpu-smoke-summary.json").write_bytes(s.encode(value))
            cpu_pin = s.digest(s.encode(value))
    monkeypatch.setattr(s, "GpuFileLock", forbidden)
    with pytest.raises((ValueError, FileNotFoundError)):
        s.dispatch(package.artifacts, package.inputs, pin, "cuda", cpu_pin)
