"""Synthetic-only fixed pooled fitting, accounting, NPZ and one-attempt tests."""

import copy
import io
import json
import runpy
import socket
import time
import zipfile
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.data.tiingo_adjusted_etf_daily import AdjustedEtfRow
from thericher_v2.research import tiingo_monthly_net_utility_development as s

REAL_CALENDAR = s.calendar_days


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("actual loader/network forbidden")

    monkeypatch.setattr(s, "load_adjusted", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with localcontext() as context:
        context.prec = 50
        yield


@pytest.fixture(scope="module")
def torch():
    t = pytest.importorskip("torch")
    old = t.get_num_threads()
    t.set_num_threads(1)
    yield t
    t.set_num_threads(old)


@pytest.fixture(scope="module")
def source():
    days, d = [], date(2000, 12, 1)
    while d <= date(2026, 8, 3):
        if d.weekday() < 5 and (
            d.year <= 2001 or d.day <= 3 or (d + timedelta(days=1)).month != d.month
        ):
            days.append(d.isoformat())
        d += timedelta(days=1)
    rows = {}
    for symbol in s.SYMBOLS:
        previous, stream = Decimal(100), []
        for i, stamp in enumerate(days):
            opening = previous + Decimal(i % 3 - 1) / 10
            closing = Decimal(100) + Decimal(i) / 100 + Decimal(i % 11 - 5) / 10
            stream.append(
                AdjustedEtfRow(
                    symbol,
                    date.fromisoformat(stamp),
                    opening,
                    max(opening, closing) + 1,
                    min(opening, closing) - 1,
                    closing,
                )
            )
            previous = closing
        rows[symbol] = tuple(stream)
    return SimpleNamespace(days=days, rows=rows, plan=s.build_plan(days))


@pytest.fixture
def sample(source, monkeypatch):
    monkeypatch.setattr(s, "calendar_days", lambda: source.days)
    contract = s.proposed_contract()
    return SimpleNamespace(**vars(source), contract=contract, pin=s.digest(s.encode(contract)))


@pytest.fixture(scope="module")
def prepared(source):
    return s.prepare(source.rows, source.plan)


def runtime(p):
    total, free = 24 * 1024**3, 22 * 1024**3
    return dict(
        device="synthetic GPU identity",
        torch=p.contract["runtime"]["torch"],
        cuda="12.8",
        torch_threads=2,
        total_bytes=total,
        free_before_bytes=free,
        memory_budget_bytes=min(int(total * 0.9), free - 1024**3),
        peak_allocated_bytes=1234,
        training_device="cuda:0",
        inference_device="cpu",
    )


def predictions(p):
    result = {}
    for symbol in s.SYMBOLS:
        for architecture, weight in zip(s.ARCHITECTURES, (0.4, 0.6), strict=True):
            result[architecture, symbol] = np.full(len(p.plan["train"]["months"]), weight)
            for segment in p.plan["periods"]:
                result[architecture, symbol, segment["period"]] = np.full(
                    len(segment["months"]), weight
                )
    return result


def model_metadata():
    return [
        dict(
            architecture=a,
            file=f"weights-{a}.npz",
            weights_sha256="sha256:" + "a" * 64,
            epochs=128,
            seed=101,
            reconstructed=True,
        )
        for a in s.ARCHITECTURES
    ]


def evaluated(p, data):
    preds = predictions(p)
    risks = s.risk_constants(data, p.plan, preds, deadline=time.monotonic() + 30)
    return s.evaluate(
        data,
        p.contract,
        p.pin,
        model_metadata(),
        preds,
        risks,
        runtime=runtime(p),
        deadline=time.monotonic() + 30,
    )


def tiny_arrays(symbol):
    return s.math.MonthlyUtilityArrays(
        symbol,
        (date(2002, 1, 2), date(2002, 2, 1)),
        (date(2001, 12, 31), date(2002, 1, 31)),
        np.linspace(-0.5, 0.5, 504, dtype=np.float32).reshape(2, 252, 1),
        np.array([1.2, 0.99]),
        np.array([[1.03, 0.98], [1.04, 1.0]]),
        np.array([[True, True], [True, False]]),
    )


def test_fixed_plan_warmup_train_targets_end_bracket_and_inputs_pins(sample, prepared):
    plan = sample.contract["plan"]
    assert len(plan["train"]["months"]) == 132
    assert [len(p["months"]) for p in plan["periods"]] == [84, 79]
    first, last = plan["train"]["months"][0], plan["train"]["months"][-1]
    assert set(first) == {"bounds"}
    a, b = first["bounds"]
    assert plan["days"][a][:7] == "2002-01" and len(plan["days"][a - 253 : a]) == 253
    assert plan["days"][a - 1] < plan["days"][a]
    assert all(d < "2013-01-01" for d in plan["days"][slice(*last["bounds"])])
    assert plan["days"][-1] == "2026-08-03"
    assert all(d < "2026-08-01" for d in plan["periods"][-1]["support"])
    assert s.configuration()["optimizer"]["epochs"] == 128 and s.configuration()["cells"] == 126
    assert len(s.CODE) == len(set(s.CODE)) and set(s.monthly.CODE) <= set(s.CODE)
    for symbol in s.SYMBOLS:
        for name in ("TRAIN", *[p[0] for p in s.PERIODS]):
            item = prepared[symbol, name]
            assert all(r.model.source_date < r.identity.decision_date for r in item["records"])
            assert item["arrays"].features.shape[1:] == (252, 1)
    with pytest.raises(ValueError):
        s.build_plan(plan["days"][:-1])


def test_cpu_smoke_real_torch_gradient_update_reconstruction_and_ragged_parity(torch, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("CPU smoke must precede CUDA")

    monkeypatch.setattr(torch.cuda, "is_available", forbidden)
    monkeypatch.setattr(torch.cuda, "mem_get_info", forbidden)
    assert s.cpu_smoke(torch) == dict(cpu_smoke_passed=True, cpu_smoke_models=2)
    assert torch.get_num_threads() == 1
    with pytest.raises(ValueError, match="hard_timeout"):
        s.cpu_smoke(torch, deadline=0)


def test_full_real_calendar_compact_metadata_roundtrip_below_inherited_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "calendar_days", REAL_CALENDAR)
    contract = s.proposed_contract()
    raw = s.encode(contract)
    assert len(raw) <= 1024**2
    assert len(contract["plan"]["train"]["months"]) == 132
    assert [len(p["months"]) for p in contract["plan"]["periods"]] == [84, 79]
    for segment in [contract["plan"]["train"], *contract["plan"]["periods"]]:
        assert all(set(m) == {"bounds"} for m in segment["months"])
        assert segment["support"] == sorted(
            {
                d
                for m in segment["months"]
                for d in contract["plan"]["days"][m["bounds"][0] - 253 : m["bounds"][1]]
            }
        )
    path = tmp_path / "metadata-only-precommit.json"
    s.atomic_new(path, contract)
    assert s._read(path) == raw and path.stat().st_nlink == 1
    assert s.header(json.loads(s._read(path)), s.digest(raw))["name"] == s.NAME


@pytest.mark.parametrize("architecture", s.ARCHITECTURES)
def test_exact128_fullbatch_pooled_adam_steps_no_eval_or_selection(
    torch, monkeypatch, architecture
):
    arrays = {symbol: tiny_arrays(symbol) for symbol in s.SYMBOLS}
    steps, navs, original = [], [], torch.optim.Adam

    class Adam(original):
        def step(self, *args, **kwargs):
            steps.append(self.param_groups[0])
            return super().step(*args, **kwargs)

    nav = s.math.torch_monthly_nav

    def ledger(t, w, a, *, cost_bps=10):
        assert any(a is value for value in arrays.values()) and cost_bps == 10
        navs.append(a.symbol)
        return nav(t, w, a, cost_bps=cost_bps)

    monkeypatch.setattr(torch.optim, "Adam", Adam)
    monkeypatch.setattr(s.math, "torch_monthly_nav", ledger)
    values = s.fit_policy(
        torch, arrays, architecture, device="cpu", deadline=time.monotonic() + 120
    )
    assert len(steps) == 128 and navs == list(s.SYMBOLS) * 128
    assert all(group["lr"] == 0.003 and group["weight_decay"] == 0.001 for group in steps)
    assert all(group["betas"] == (0.9, 0.999) and group["eps"] == 1e-8 for group in steps)
    s.validate_weights(values, architecture)
    with pytest.raises(ValueError, match="hard_timeout"):
        s.fit_policy(torch, arrays, architecture, device="cpu", deadline=0)


@pytest.mark.parametrize("architecture", s.ARCHITECTURES)
def test_safe_npz_hash_schema_readonly_numeric_rebuild_and_exclusive_write(
    torch, tmp_path, architecture
):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(101)
        model = s.math.build_torch_monthly_policy(torch, architecture)
    values = s.extract_weights(model, architecture)
    metadata = s.write_weights(tmp_path, values, architecture)
    path = tmp_path / metadata["file"]
    read = s.read_weights(path, architecture, metadata["weights_sha256"])
    assert all(not a.flags.writeable for a in read.values()) and path.stat().st_nlink == 1
    assert {p.name for p in tmp_path.iterdir()} == {metadata["file"]}
    assert all(np.array_equal(values[k], read[k]) for k in values)
    arrays = tiny_arrays("SPY")
    assert np.allclose(
        s.predict(torch, model, arrays),
        s.predict(torch, s.rebuild_policy(torch, read, architecture), arrays),
        rtol=0,
        atol=1e-6,
    )
    with pytest.raises(FileExistsError):
        s.write_weights(tmp_path, values, architecture)
    with pytest.raises(ValueError, match="weights_hash"):
        s.read_weights(path, architecture, "sha256:" + "0" * 64)


@pytest.mark.parametrize("bad", ["keys", "shape", "float64", "nan", "object", "duplicate_archive"])
def test_untrusted_npz_rejects_extra_missing_bad_dtype_shape_object_and_duplicates(tmp_path, bad):
    values = {
        k: np.zeros(shape, dtype=np.float32) for k, shape in s.weight_shapes("linear").items()
    }
    if bad == "keys":
        values["fake"] = np.array([1], dtype=np.float32)
    if bad == "shape":
        values["head_weight"] = np.zeros((1, 253), dtype=np.float32)
    if bad == "float64":
        values["head_weight"] = values["head_weight"].astype(np.float64)
    if bad == "nan":
        values["head_bias"][0] = np.nan
    if bad == "object":
        values["head_bias"] = np.array([object()], dtype=object)
    b = io.BytesIO()
    np.savez(b, **values)
    raw = b.getvalue()
    if bad == "duplicate_archive":
        with zipfile.ZipFile(io.BytesIO(raw)) as original:
            payload = original.read("head_bias.npy")
        with zipfile.ZipFile(b, "a") as archive, pytest.warns(UserWarning):
            archive.writestr("head_bias.npy", payload)
        raw = b.getvalue()
    path = tmp_path / "untrusted.npz"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        s.read_weights(path, "linear", s.digest(raw))


def test_train_risk_constants_same_train_dates_only_zero_passive_variance_scoped(sample, prepared):
    class TrainOnly(dict):
        def get(self, d):
            assert d <= s.TRAIN[1]
            return super().get(d)

    data = {k: dict(v) for k, v in prepared.items()}
    for symbol in s.SYMBOLS:
        data[symbol, "TRAIN"]["rows"] = TrainOnly(data[symbol, "TRAIN"]["rows"])
    preds = predictions(sample)
    risks = s.risk_constants(data, sample.plan, preds, deadline=time.monotonic() + 30)
    segment = sample.plan["train"]
    rows = data["SPY", "TRAIN"]["rows"]
    passive = s.monthly.replay(
        rows,
        sample.days,
        segment["bounds"],
        s._actions(segment, np.ones(132)),
        "0",
        deadline=time.monotonic() + 30,
    )
    for arch in s.ARCHITECTURES:
        managed = s.monthly.replay(
            rows,
            sample.days,
            segment["bounds"],
            s._actions(segment, preds[arch, "SPY"]),
            "0",
            deadline=time.monotonic() + 30,
        )
        assert len(managed["returns"]) == len(passive["returns"])
        assert risks["SPY"][arch] == min(
            Decimal(1),
            (
                s.monthly.variance(managed["returns"]) / s.monthly.variance(passive["returns"])
            ).sqrt(),
        )
    data["SPY", "TRAIN"]["rows"] = {
        d: replace(
            r,
            adj_open=Decimal(100),
            adj_close=Decimal(100),
            adj_high=Decimal(100),
            adj_low=Decimal(100),
        )
        for d, r in prepared["SPY", "TRAIN"]["rows"].items()
    }
    flat = s.risk_constants(data, sample.plan, preds, deadline=time.monotonic() + 30)
    assert flat["SPY"] == dict.fromkeys(s.ARCHITECTURES) and all(
        v is not None for v in flat["QQQ"].values()
    )
    result = s.evaluate(
        data,
        sample.contract,
        sample.pin,
        model_metadata(),
        preds,
        flat,
        runtime=runtime(sample),
        deadline=time.monotonic() + 30,
    )
    assert result["status"] == "input_unavailable"
    assert all(c["final_nav"] is None for c in result["cells"][:42])


def test_126cells_cost_invariant_paths_cash_long_fees_controls_and_closed_output(sample, prepared):
    r = evaluated(sample, prepared)
    assert r["status"] == "complete" and len(r["groups"]) == 6 and len(r["cells"]) == 126
    assert r["cpu_smoke_passed"] is True and r["cpu_smoke_models"] == 2
    assert not any(token in s.encode(r) for token in (b'"weights":', b'"features":', b'"navs":'))
    for c in r["cells"]:
        if c["policy"] == "cash":
            assert c["final_nav"] == "1.000000000000" and c["trades"] == 0
        if c["policy"] == "always_long":
            assert c["trades"] == 2
        selected = [
            other
            for other in r["cells"]
            if (other["symbol"], other["period"], other["policy"])
            == (c["symbol"], c["period"], c["policy"])
        ]
        assert len({other["action_sha256"] for other in selected}) == 1


@pytest.mark.parametrize(
    "bad",
    [
        "extra",
        "matrix",
        "cost_path",
        "cash",
        "fees",
        "long",
        "nan",
        "cohort",
        "weights",
        "epochs",
        "seed",
        "runtime",
        "smoke",
        "risk",
    ],
)
def test_closed_result_tamper_and_runtime_weight_attestation_rejected(sample, prepared, bad):
    r = evaluated(sample, prepared)
    if bad == "extra":
        r["weights"] = []
    if bad == "matrix":
        r["cells"].pop()
    if bad == "cost_path":
        r["cells"][7]["action_sha256"] = "sha256:" + "0" * 64
    if bad == "cash":
        r["cells"][6]["final_nav"] = "2.000000000000"
    if bad == "fees":
        r["cells"][0]["fees_initial_nav"] = "99.000000000000"
    if bad == "long":
        r["cells"][5]["trades"] = 4
    if bad == "nan":
        r["cells"][0]["net_utility"] = "NaN"
    if bad == "cohort":
        r["groups"][0]["inputs_sha256"] = "sha256:" + "0" * 64
    if bad == "weights":
        r["models"][0]["file"] = "../../evil.npz"
    if bad == "epochs":
        r["models"][0]["epochs"] = 127
    if bad == "seed":
        r["models"][0]["seed"] = 102
    if bad == "runtime":
        r["runtime"]["peak_allocated_bytes"] = r["runtime"]["memory_budget_bytes"] + 1
    if bad == "smoke":
        r["cpu_smoke_passed"] = False
    if bad == "risk":
        r["groups"][1]["risk_sha256"] = dict.fromkeys(s.ARCHITECTURES, "sha256:" + "0" * 64)
    with pytest.raises(ValueError):
        s.validate_result(r, sample.contract, sample.pin)


@pytest.mark.parametrize(
    "field", ["config", "source", "inputs_sha256", "runtime", "code_sha256", "plan"]
)
def test_contract_binding_even_rehashed_invalid_fields(sample, field):
    contract = copy.deepcopy(sample.contract)
    contract[field] = "sha256:" + "0" * 64 if field == "inputs_sha256" else {}
    with pytest.raises((ValueError, KeyError)):
        s.header(contract, s.digest(s.encode(contract)))


def test_train_gap_means_no_pooled_fit_and_eval_gap_scoped(sample, torch, tmp_path, monkeypatch):
    rows = dict(sample.rows)
    removed = sample.days[sample.plan["train"]["months"][0]["bounds"][0] - 253 + 5]
    rows["SPY"] = tuple(r for r in rows["SPY"] if r.session_date.isoformat() != removed)
    data = s.prepare(rows, sample.plan)

    def forbidden(*args, **kwargs):
        pytest.fail("incomplete pooled TRAIN must not fit")

    monkeypatch.setattr(s, "fit_policy", forbidden)
    r = s.execute(
        torch,
        data,
        sample.contract,
        sample.pin,
        tmp_path,
        device="cpu",
        runtime=runtime(sample),
        deadline=time.monotonic() + 30,
    )
    assert r["status"] == "input_unavailable" and r["models"] == [] and not list(tmp_path.iterdir())
    assert all(c["final_nav"] is None for c in r["cells"])


def test_two_fits_train_only_no_eval_recalibration_final_npz_reconstruction(
    torch, sample, prepared, tmp_path, monkeypatch
):
    calls = []

    def fit(t, arrays, arch, *, device, deadline):
        assert tuple(arrays) == s.SYMBOLS and all(
            a is prepared[symbol, "TRAIN"]["arrays"] for symbol, a in arrays.items()
        )
        calls.append(arch)
        return {k: np.zeros(shape, np.float32) for k, shape in s.weight_shapes(arch).items()}

    monkeypatch.setattr(s, "fit_policy", fit)
    r = s.execute(
        torch,
        prepared,
        sample.contract,
        sample.pin,
        tmp_path,
        device="cpu",
        runtime=runtime(sample),
        deadline=time.monotonic() + 60,
    )
    assert calls == ["linear", "lstm"] and r["status"] == "complete"
    assert {p.name for p in tmp_path.iterdir()} == {"weights-linear.npz", "weights-lstm.npz"}
    for model in r["models"]:
        assert (tmp_path / model["file"]).stat().st_nlink == 1
        s.read_weights(tmp_path / model["file"], model["architecture"], model["weights_sha256"])


def test_eval_target_gap_suppresses_only_exact_fold_not_train_or_other_etfs(sample, prepared):
    segment = sample.plan["periods"][1]
    removed = next(d for d in sample.days if d.startswith("2025-01"))
    rows = dict(sample.rows)
    rows["SPY"] = tuple(r for r in rows["SPY"] if r.session_date.isoformat() != removed)
    altered = s.prepare(rows, sample.plan)
    assert np.array_equal(
        prepared["SPY", "TRAIN"]["arrays"].features, altered["SPY", "TRAIN"]["arrays"].features
    )
    assert altered["SPY", segment["period"]]["facts"]["missing"] == 1
    r = evaluated(sample, altered)
    assert r["groups"][1]["status"] == "input_unavailable"
    assert all(c["final_nav"] is None for c in r["cells"][21:42])
    assert all(c["final_nav"] is not None for c in r["cells"][:21] + r["cells"][42:])


def test_future_target_mutation_leaves_train_inputs_and_current_features(sample, prepared):
    first = sample.plan["periods"][0]["months"][0]
    d = sample.days[first["bounds"][0]]
    rows = dict(sample.rows)
    changed = []
    for row in rows["SPY"]:
        if row.session_date.isoformat() == d:
            close = row.adj_close * 2
            row = replace(row, adj_close=close, adj_high=max(row.adj_open, close) + 1)
        changed.append(row)
    rows["SPY"] = tuple(changed)
    altered = s.prepare(rows, sample.plan)
    assert np.array_equal(
        prepared["SPY", "TRAIN"]["arrays"].features, altered["SPY", "TRAIN"]["arrays"].features
    )
    assert np.array_equal(
        prepared["SPY", "TRAIN"]["arrays"].close_growth,
        altered["SPY", "TRAIN"]["arrays"].close_growth,
    )
    assert np.array_equal(
        prepared["SPY", "2013-2019"]["arrays"].features[0],
        altered["SPY", "2013-2019"]["arrays"].features[0],
    )
    assert not np.array_equal(
        prepared["SPY", "2013-2019"]["arrays"].close_growth[0],
        altered["SPY", "2013-2019"]["arrays"].close_growth[0],
    )


def synthetic_freeze(p, tmp_path, monkeypatch):
    artifact, market = tmp_path / "artifact", tmp_path / "market"
    manifest = market / s.base.SNAPSHOT / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(b"synthetic")
    monkeypatch.setattr(
        s,
        "verify_metadata",
        lambda a, m: s.require(manifest.read_bytes() == b"synthetic", "metadata_changed"),
    )
    pin = s.freeze(artifact, market)
    output, contract = s.verify(artifact, market, pin)
    return artifact, market, pin, output, contract


@pytest.mark.parametrize("mode", ["success", "timeout", "interrupt", "tamper", "weights_tamper"])
def test_existing_supervisor_oneattempt_immutable_summary_synthetic_freeze(
    sample, prepared, tmp_path, monkeypatch, mode
):
    artifact, market, pin, output, contract = synthetic_freeze(sample, tmp_path, monkeypatch)
    runner = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    ns = runner["main"].__globals__
    ns["study"], ns["worker"] = s, s.worker_entry

    def supervise(target, args, *, seconds):
        assert target is s.worker_entry and 0 < seconds <= 900
        assert json.loads((output / "started.json").read_bytes()) == {"contract_sha256": pin}
        if mode == "interrupt":
            raise KeyboardInterrupt
        if mode != "timeout":
            result = evaluated(
                SimpleNamespace(**(vars(sample) | {"pin": pin, "contract": contract})), prepared
            )
            for m in result["models"]:
                values = {
                    k: np.zeros(shape, np.float32)
                    for k, shape in s.weight_shapes(m["architecture"]).items()
                }
                m.update(s.write_weights(output, values, m["architecture"]))
            if mode == "tamper":
                result["unsafe_weights"] = []
            if mode == "weights_tamper":
                (output / result["models"][0]["file"]).write_bytes(b"tampered")
            s.atomic_new(args[-2], result)
        return dict(timed_out=mode == "timeout", exit_code=None if mode == "timeout" else 0)

    ns["supervise"] = supervise
    dispatch = runner["dispatch"](artifact, market, pin)
    assert dispatch["status"] == ("complete" if mode == "success" else "failed")
    original = (output / "summary.json").read_bytes()
    s.validate_result(json.loads(original), contract, pin)
    with pytest.raises(ValueError):
        runner["dispatch"](artifact, market, pin)
    assert (output / "summary.json").read_bytes() == original
    for path in tmp_path.rglob("*"):
        assert not path.is_symlink()
        if path.is_file():
            assert path.stat().st_nlink == 1


def test_spawn_missing_precommit_bounded_no_source_read(tmp_path):
    ns = runpy.run_path(str(s.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    r = ns["supervise"](
        s.worker_entry,
        (tmp_path / "a", tmp_path / "m", "invalid", tmp_path / "unused", time.monotonic() + 10),
        seconds=10,
        name="net-utility-synthetic",
    )
    assert r["exit_code"] == 1 and r["timed_out"] is False


def test_worker_cpu_preflight_precedes_cuda_and_rows_and_allocator_guard(
    torch, sample, prepared, tmp_path, monkeypatch
):
    versions = s.runtime_versions() | {"torch": str(torch.__version__)}
    monkeypatch.setattr(s, "runtime_versions", lambda: versions)
    artifact, market, pin, output, contract = synthetic_freeze(sample, tmp_path, monkeypatch)
    s.atomic_new(output / "started.json", {"contract_sha256": pin})
    calls = []
    monkeypatch.setattr(
        s,
        "cpu_smoke",
        lambda t, **kw: calls.append("cpu") or dict(cpu_smoke_passed=True, cpu_smoke_models=2),
    )
    monkeypatch.setattr(torch.cuda, "is_available", lambda: calls.append("cuda") or True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    monkeypatch.setattr(torch.cuda, "mem_get_info", lambda device: (22 * 1024**3, 24 * 1024**3))
    monkeypatch.setattr(
        torch.cuda,
        "set_per_process_memory_fraction",
        lambda fraction, device: calls.append(("fraction", fraction)),
    )
    monkeypatch.setattr(torch.cuda, "reset_peak_memory_stats", lambda device: None)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda device: "synthetic GPU identity")
    monkeypatch.setattr(torch.cuda, "synchronize", lambda device: None)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda device: 1234)
    monkeypatch.setattr(torch.version, "cuda", "12.8")
    monkeypatch.setattr(torch, "use_deterministic_algorithms", lambda enabled: None)
    monkeypatch.setattr(s, "load_adjusted", lambda *args: calls.append("rows") or sample.rows)
    monkeypatch.setattr(s, "prepare", lambda rows, plan: prepared)

    def execute(t, data, con, p, out, *, device, runtime, deadline):
        assert device == "cuda:0" and calls[:2] == ["cpu", "cuda"] and calls[-1] == "rows"
        r = evaluated(SimpleNamespace(**(vars(sample) | {"pin": p, "contract": con})), prepared)
        r["runtime"] = runtime
        for m in r["models"]:
            m.update(
                s.write_weights(
                    out,
                    {
                        k: np.zeros(shape, np.float32)
                        for k, shape in s.weight_shapes(m["architecture"]).items()
                    },
                    m["architecture"],
                )
            )
        return r

    monkeypatch.setattr(s, "execute", execute)
    path = output / "worker-result.json"
    s.run_worker(artifact, market, pin, path, time.monotonic() + 30)
    r = json.loads(path.read_bytes())
    assert r["status"] == "complete" and r["cpu_smoke_passed"] is True, (r, calls)
    assert (
        calls[2][0] == "fraction"
        and calls[2][1] == r["runtime"]["memory_budget_bytes"] / r["runtime"]["total_bytes"]
    )
    assert (
        r["runtime"]["peak_allocated_bytes"] == 1234 and r["runtime"]["inference_device"] == "cpu"
    )
    s.validate_result(r, contract, pin)


@pytest.mark.parametrize("smoke", [False, {"cpu_smoke_passed": True, "cpu_smoke_models": 1}])
def test_failed_cpu_preflight_never_queries_cuda_or_loads_market_rows(
    torch, sample, tmp_path, monkeypatch, smoke
):
    artifact, market, pin, output, contract = synthetic_freeze(sample, tmp_path, monkeypatch)
    s.atomic_new(output / "started.json", {"contract_sha256": pin})
    monkeypatch.setattr(s, "cpu_smoke", lambda *args, **kwargs: smoke)

    def forbidden(*args, **kwargs):
        pytest.fail("failed CPU preflight must not query CUDA or load actual rows")

    monkeypatch.setattr(torch.cuda, "is_available", forbidden)
    monkeypatch.setattr(s, "load_adjusted", forbidden)
    path = output / "worker-result.json"
    s.run_worker(artifact, market, pin, path, time.monotonic() + 30)
    r = json.loads(path.read_bytes())
    assert r["status"] == "failed" and r["cpu_smoke_passed"] is False
    assert r["cpu_smoke_models"] == 0 and r["runtime"] is None
    s.validate_result(r, contract, pin)


def test_launcher_uses_canonical_lock_without_touching_actual_lock(sample, monkeypatch):
    namespace = runpy.run_path(
        str(s.REPO / "scripts/run_tiingo_monthly_net_utility_development.py")
    )
    calls, parent = [], {"__builtins__": __builtins__}
    exec("def dispatch(a,m,p):\n return a,m,p\ndef main(argv):\n return dispatch(*argv)", parent)
    monkeypatch.setattr(runpy, "run_path", lambda path: {"main": parent["main"]})

    class Lock:
        def __init__(self, path):
            calls.append(path)

        def __enter__(self):
            calls.append("enter")

        def __exit__(self, *args):
            calls.append("exit")

    monkeypatch.setitem(namespace["main"].__globals__, "GpuFileLock", Lock)
    from pathlib import Path

    a, m = Path("synthetic-artifact"), Path("synthetic-market")
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "CUBLAS_WORKSPACE_CONFIG",
    ):
        monkeypatch.setenv(key, "old")
    assert namespace["main"]([a, m, sample.pin]) == (a, m, sample.pin)
    assert calls == [a / "engine-research-agent/locks/gpu.lock", "enter", "exit"]
