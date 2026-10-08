"""Source-free loss alignment, causal preparation, truthful fits and cached replay."""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
import warnings
from dataclasses import replace
from decimal import ROUND_DOWN, localcontext
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import kis_d1_qlike_variance_forecast as study

GRU_FIT = study.fit_gru


@pytest.fixture(autouse=True)
def no_actual_dispatch(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("actual source/runtime/fit access outside synthetic stub")

    monkeypatch.setattr(study.base, "load_committed_source", forbidden)
    monkeypatch.setattr(study.base, "calendar_sessions", forbidden)
    monkeypatch.setattr(study, "runtime_identity", forbidden)
    monkeypatch.setattr(study, "_gamma_model", forbidden)
    monkeypatch.setattr(study, "fit_gru", forbidden)
    monkeypatch.setattr(study.fixed, "fit_ols", forbidden)
    monkeypatch.setattr(study.fixed, "fit_gru", forbidden)


@pytest.fixture(scope="module")
def plan():
    return study.build_plan(study.rolling._synthetic_sessions())


@pytest.fixture(scope="module")
def prepared(plan):
    raw = np.random.default_rng(101).normal(0, 0.01, (505, 3, 63))
    labels = np.full((504, 3), 0.0001)
    return study.fixed.prepare_arrays(raw, labels, plan.month(0))


def parts(plan, pin="synthetic"):
    return [
        dict(
            contract_sha256=pin,
            input_sha256=study.base.INPUT_PIN,
            window=plan.window_record(m),
            log_forecasts=dict(gamma=[[math.log(0.0001)] * 3], gru=[[math.log(0.0001)] * 3]),
            baseline=[[0.0001] * 3],
            inference_kind="original_worker",
        )
        for m in range(33)
    ]


def test_frozen_parent_api_and_truthful_lineage(plan):
    config = study.configuration()
    assert study.CANDIDATES == ("gamma", "gru")
    assert config["fits"] == 132 and config["cells"] == 6
    assert config["seconds"] == 300 and config["verify_seconds"] == 120
    assert config["related_trial_number"] == 3 and "not forced" in config["registry_trial_index"]
    assert config["predecessor"]["study"] == study.rolling.NAME
    assert config["predecessor"]["contract_sha256"].startswith("sha256:9087641d")
    assert config["geometry_receipt"]["sha256"] == study.rolling.GEOMETRY_PIN
    assert config["geometry"]["required_dates"] == 1278
    assert config["gru"]["parameters"] == 3651 and config["gru"]["updates"] == 512
    assert "expm1" in config["gru"]["loss"] and config["gamma"]["alpha"] == 0
    assert config["gamma"]["solver"] == "lbfgs" and config["gamma"]["max_iter"] == 100
    assert config["gamma"]["tol"] == 1e-4 and "ols" not in config
    assert study.RUNTIME["sklearn"] == "1.9.1"
    assert config["accounting"] == "target-only variance; no NAV/trading costs/Paper"
    assert config["paper_input"] is False and config["holdout_access"] == "none"
    assert len(study.ARTIFACTS) == len(set(study.ARTIFACTS)) == 596
    assert "j+20<=d-2" in config["training"] and len(plan.dev_indices) == 33
    assert all(
        w[-1] + 20 == d - 2 for d, w in zip(plan.dev_indices, plan.train_windows, strict=True)
    )


def source_bytes(plan, *, cutoff=None, mutation=None):
    files = []
    for asset, symbol in enumerate(study.base.INSTRUMENT_ORDER):
        text = io.StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(study.base.COLUMNS)
        for session in plan.sessions:
            day = session.session_date
            if cutoff and day > cutoff and mutation == "absent":
                continue
            close = str(100 + day.toordinal() % (17 + asset))
            if cutoff and day > cutoff and mutation == "changed":
                close = "not-a-numeric-future-price"
            writer.writerow(
                (
                    symbol,
                    study.base.EXCHANGES[symbol],
                    day.isoformat(),
                    "unused-invalid-open",
                    close,
                    "synthetic",
                )
            )
        files.append((symbol, gzip.compress(text.getvalue().encode(), mtime=0)))
    return study.base.SourceInputs(tuple(files), {}, SimpleNamespace(sessions=plan.sessions))


@pytest.fixture(scope="module")
def past_prepared(plan):
    source = source_bytes(plan)
    return study.PreparationCache(source, plan).prepare(0, deadline=float("inf"))


@pytest.mark.parametrize("mutation", ["changed", "absent"])
def test_future_bytes_and_support_leave_membership_scalers_predictions_exact(
    plan, past_prepared, mutation
):
    cutoff = plan.sessions[plan.dev_indices[0] - 1].session_date
    source = source_bytes(plan, cutoff=cutoff, mutation=mutation)
    after = study.PreparationCache(source, plan).prepare(0, deadline=float("inf"))
    assert after.plan == past_prepared.plan
    assert after.scaler == past_prepared.scaler
    for name in ("train_x", "train_har", "labels", "dev_x", "dev_har", "baseline"):
        np.testing.assert_array_equal(getattr(after, name), getattr(past_prepared, name))
    # Frozen deterministic synthetic log-link parameters; no training or labels consulted.
    coefficients = np.arange(27, dtype=float).reshape(9, 3) / 100
    np.testing.assert_array_equal(
        np.exp(after.dev_har @ coefficients), np.exp(past_prepared.dev_har @ coefficients)
    )
    if mutation == "absent":
        with pytest.raises(study.base.StudyFault, match="required_date_gap"):
            study.fixed.load_dev_targets(source, plan)


def test_missing_required_past_not_older_fallback(plan):
    source = source_bytes(plan)
    day = plan.sessions[plan.train_windows[0][0] - 64].session_date.isoformat()
    raw = gzip.decompress(source.files[0][1]).decode().splitlines()
    changed = gzip.compress("\n".join(r for r in raw if f",{day}," not in r).encode(), mtime=0)
    source = replace(source, files=((source.files[0][0], changed),) + source.files[1:])
    with pytest.raises(study.base.StudyFault, match="required_date_gap"):
        study.PreparationCache(source, plan).prepare(0, deadline=float("inf"))


def test_train_only_scaling_and_center(plan, prepared):
    raw = np.random.default_rng(101).normal(0, 0.01, (505, 3, 63))
    raw[-1] *= 1000
    changed = study.fixed.prepare_arrays(raw, np.full((504, 3), 0.0001), plan.month(0))
    for key in (
        "mean",
        "divisor",
        "har_mean",
        "har_divisor",
        "target_log_mean",
        "train_x_sha256",
        "train_har_sha256",
        "labels_sha256",
    ):
        assert changed.scaler[key] == prepared.scaler[key]
    assert not prepared.train_x.flags.writeable and "train_x=" not in repr(prepared)


@pytest.fixture
def fake_gamma(monkeypatch):
    pytest.importorskip("sklearn")
    from sklearn.exceptions import ConvergenceWarning

    state = dict(events=[], fault=None, target=None)

    class Model:
        coef_ = np.arange(9, dtype=float) / 100
        intercept_ = -9.0
        n_iter_ = 10

        def fit(self, x, y):
            state["events"].append("fit_return")
            state["target"] = y.copy()
            if state["fault"] == "convergence":
                warnings.warn("synthetic nonconvergence", ConvergenceWarning, stacklevel=2)
            if state["fault"] == "coefficients":
                self.coef_ = np.full(9, np.nan)
            return self

        def predict(self, x):
            state["events"].append("predict")
            if state["fault"] == "prediction_exception":
                raise RuntimeError("synthetic private error must not leak")
            if state["fault"] in ("zero", "negative", "infinite"):
                return np.array(
                    [{"zero": 0.0, "negative": -1.0, "infinite": np.inf}[state["fault"]]]
                )
            return np.exp(x @ self.coef_ + self.intercept_)

    monkeypatch.setattr(study, "_gamma_model", Model)
    state["callback"] = lambda: state["events"].append("completed")
    return state


def test_gamma_single_output_positive_target_and_numeric_npz(prepared, fake_gamma):
    logs, weights, resources = study.fit_gamma(
        prepared, 1, deadline=float("inf"), progress=fake_gamma["callback"]
    )
    assert fake_gamma["events"] == ["fit_return", "completed", "predict"]
    np.testing.assert_array_equal(fake_gamma["target"], np.exp(prepared.labels[:, 1]))
    assert len(logs) == 1 and resources["rank"] == 10
    with np.load(io.BytesIO(weights), allow_pickle=False) as saved:
        assert set(saved.files) == {"coefficients", "intercept", "iterations", "asset"}
        assert int(saved["asset"]) == 1 and saved["coefficients"].shape == (9,)
        assert all(saved[name].dtype.kind in "fi" for name in saved.files)


def test_gamma_rank_failure_prevents_any_fit_or_fallback(prepared, fake_gamma):
    invalid = replace(prepared, train_har=np.zeros((504, 9)))
    with pytest.raises(study.base.StudyFault, match="gamma_rank"):
        study.fit_gamma(invalid, 0, deadline=float("inf"), progress=fake_gamma["callback"])
    assert fake_gamma["events"] == []


@pytest.mark.parametrize(
    "fault,code",
    [
        ("convergence", "gamma_convergence"),
        ("coefficients", "fit_nonfinite"),
        ("zero", "forecast_numeric"),
        ("negative", "forecast_numeric"),
        ("infinite", "forecast_numeric"),
        ("prediction_exception", "synthetic private"),
    ],
)
def test_gamma_fit_completed_before_postfit_failures(prepared, fake_gamma, fault, code):
    fake_gamma["fault"] = fault
    with pytest.raises((study.base.StudyFault, RuntimeError), match=code):
        study.fit_gamma(prepared, 0, deadline=float("inf"), progress=fake_gamma["callback"])
    assert fake_gamma["events"][:2] == ["fit_return", "completed"]


@pytest.mark.parametrize("fault", ["deadline", "serialization"])
def test_gamma_completion_precedes_deadline_or_serialization(
    monkeypatch, prepared, fake_gamma, fault
):
    if fault == "deadline":
        clock = dict(value=0.0)
        monkeypatch.setattr(study.time, "monotonic", lambda: clock["value"])

        def completed():
            fake_gamma["events"].append("completed")
            clock["value"] = 2.0

        callback = completed
    else:

        def fail(*a, **k):
            raise OSError("synthetic private serialization")

        monkeypatch.setattr(study.np, "savez", fail)
        callback = fake_gamma["callback"]
    with pytest.raises((study.base.StudyFault, OSError)):
        study.fit_gamma(
            prepared, 0, deadline=1.0 if fault == "deadline" else float("inf"), progress=callback
        )
    assert fake_gamma["events"][:2] == ["fit_return", "completed"]


def test_qlike_loss_exact_ratio_center_cancellation_and_gradients():
    torch = pytest.importorskip("torch")
    prediction = torch.tensor([[0.0, 0.25, -0.5]], dtype=torch.float64, requires_grad=True)
    target = torch.tensor([[0.5, -0.75, 1.0]], dtype=torch.float64)
    loss = study.qlike_train_loss(prediction, target)
    expected = (torch.exp(target - prediction) - (target - prediction) - 1).mean()
    assert loss.item() == pytest.approx(expected.item(), abs=1e-15)
    loss.backward()
    np.testing.assert_allclose(
        prediction.grad.numpy(), ((1 - torch.exp(target - prediction)) / 3).detach().numpy()
    )
    assert study.qlike_train_loss(prediction + 2, target + 2).item() == loss.item()
    assert study.qlike_train_loss(prediction, prediction).item() == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1000.0])
def test_qlike_nonfinite_not_clipped(value):
    torch = pytest.importorskip("torch")
    with pytest.raises(study.base.StudyFault, match="fit_nonfinite"):
        study.qlike_train_loss(torch.zeros((1, 3)), torch.full((1, 3), value))


@pytest.mark.parametrize("fault", ["prediction", "serialization", "deadline"])
def test_gru_real_control_flow_counts_before_postfit_fault_without_gpu_or_updates(
    monkeypatch, prepared, fault
):
    torch = pytest.importorskip("torch")
    serialization = pytest.importorskip("safetensors.torch")
    state = dict(steps=0, clock=0.0, completed=[])

    class SyntheticModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.parameter = torch.nn.Parameter(torch.zeros(3651))

        def to(self, *a, **k):
            return self

        def forward(self, x):
            if not self.training and fault == "prediction":
                raise RuntimeError("synthetic private postfit prediction")
            return self.parameter.mean().expand(len(x), 3)

    class NoUpdateOptimizer:
        def __init__(self, parameters, **kwargs):
            self.parameters = tuple(parameters)
            assert kwargs == dict(lr=0.001, weight_decay=0.01)

        def zero_grad(self, **kwargs):
            for parameter in self.parameters:
                parameter.grad = None

        def step(self):
            state["steps"] += 1  # Stub only; no parameter is changed.

    original_to = torch.Tensor.to

    def cpu_only(tensor, *args, **kwargs):
        return tensor if args == ("cuda",) else original_to(tensor, *args, **kwargs)

    def progress(update):
        state["completed"].append(update)
        if update == 512 and fault == "deadline":
            state["clock"] = 2.0

    def fail_save(*a, **k):
        raise OSError("synthetic private postfit serialization")

    monkeypatch.setattr(study, "fit_gru", GRU_FIT)
    monkeypatch.setattr(study.fixed, "make_gru", SyntheticModel)
    monkeypatch.setattr(torch.Tensor, "to", cpu_only)
    monkeypatch.setattr(torch.optim, "AdamW", NoUpdateOptimizer)
    for name in ("set_num_threads", "manual_seed", "use_deterministic_algorithms"):
        monkeypatch.setattr(torch, name, lambda *a, **k: None)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    for name in ("synchronize", "reset_peak_memory_stats"):
        monkeypatch.setattr(torch.cuda, name, lambda: None)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda: 0)
    monkeypatch.setattr(torch.backends.cuda.matmul, "allow_tf32", False)
    monkeypatch.setattr(torch.backends.cudnn, "allow_tf32", False)
    monkeypatch.setattr(torch.backends.cudnn, "benchmark", False)
    monkeypatch.setattr(torch.backends.cudnn, "deterministic", True)
    monkeypatch.setattr(study.time, "monotonic", lambda: state["clock"])
    monkeypatch.setattr(serialization, "save", fail_save)
    with pytest.raises((RuntimeError, OSError, study.base.StudyFault)):
        study.fit_gru(prepared, deadline=1.0, progress=progress)
    assert state["steps"] == 512 and state["completed"] == [128, 256, 384, 512]


def test_predictions_not_floored():
    result = study.fixed.forecast_variance([[math.log(1e-20)] * 3], 1)
    assert 0 < result[0, 0] < study.fixed.FLOOR


def test_six_cells_identical_original_scoring_and_renamed_kill(plan):
    predictions = study.assemble_predictions(plan, parts(plan), "synthetic")
    target = np.full((33, 3), 0.0002)
    cells = study.evaluate(target, predictions, plan, completed_fits=132)
    legacy = dict(
        predictions,
        log_forecasts=dict(
            ols=predictions["log_forecasts"]["gamma"], gru=predictions["log_forecasts"]["gru"]
        ),
    )
    original = study.fixed.evaluate(target, legacy, plan)
    assert [
        dict(c, method="ols" if c["method"] == "gamma" else c["method"]) for c in cells
    ] == original
    assert len(cells) == 6 and {c["decision_count"] for c in cells} == {12, 21}
    assert all(set(c["asset_metrics"]) == set(study.base.INSTRUMENT_ORDER) for c in cells)
    assert study.criterion(cells) == dict(gamma="rejected", gru="rejected")


@pytest.mark.parametrize("metric", study.METRICS)
@pytest.mark.parametrize("block", [0, 1])
def test_original_strict_both_block_and_metric_kill(metric, block):
    cells = [
        dict(
            block=b,
            method=m,
            status="complete",
            metrics=dict(
                qlike=str({"baseline": 2, "gamma": 1, "gru": 0.5}[m]),
                log_mse=str({"baseline": 2, "gamma": 1, "gru": 0.5}[m]),
            ),
        )
        for b in (0, 1)
        for m in study.METHODS
    ]
    assert set(study.criterion(cells).values()) == {"development_survivor"}
    own = next(c for c in cells if c["method"] == "gru" and c["block"] == block)
    own["metrics"][metric] = ".9999999999"
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert study.criterion(cells)["gru"] == "rejected"
    own["metrics"][metric] = ".999999999899999999999"
    assert study.criterion(cells)["gru"] == "development_survivor"


@pytest.mark.parametrize("count", [0, 66, 131, True])
def test_incomplete_fit_count_never_scores(monkeypatch, count, plan):
    monkeypatch.setattr(study.fixed, "evaluate", lambda *a: pytest.fail("partial score"))
    with pytest.raises(study.base.StudyFault, match="incomplete_fits"):
        study.evaluate(None, {}, plan, completed_fits=count)


@pytest.fixture
def mock_run(monkeypatch, tmp_path, plan, prepared):
    artifact = tmp_path / "A"
    root = artifact / "research" / study.NAME
    root.mkdir(parents=True)
    pin = "sha256:" + "1" * 64
    source = SimpleNamespace(
        files=(("synthetic", b"synthetic"),), plan=SimpleNamespace(sessions=plan.sessions)
    )
    monkeypatch.setattr(study, "read_contract", lambda *a: ({"plan": plan.record()}, {}))
    monkeypatch.setattr(study.base, "load_committed_source", lambda *a, **k: source)
    monkeypatch.setattr(study.PreparationCache, "prepare", lambda *a, **k: prepared)
    state = dict(gamma=0, gru=0, forward_reads=0)

    def gamma(p, asset, *, deadline, progress):
        assert asset == state["gamma"] % 3
        progress()
        state["gamma"] += 1
        return [math.log(0.0001)], b"synthetic-gamma", dict(seconds=0)

    def gru(p, *, deadline, progress):
        for update in (128, 256, 384, 512):
            progress(update)
        state["gru"] += 1
        return [[math.log(0.0001)] * 3], b"synthetic-gru", dict(seconds=0)

    def forward(*a, **k):
        assert state["gamma"] == 99 and state["gru"] == 33
        assert (root / "predictions.json").exists()
        assert all((root / f"months/{m:02d}/predictions.json").exists() for m in range(33))
        state["forward_reads"] += 1
        return np.full((33, 3), 0.0001)

    monkeypatch.setattr(study, "fit_gamma", gamma)
    monkeypatch.setattr(study, "fit_gru", gru)
    monkeypatch.setattr(study.fixed, "load_dev_targets", forward)
    return SimpleNamespace(
        root=root, market=tmp_path / "M", artifact=artifact, pin=pin, state=state
    )


def invoke_run(f):
    return study.run(f.root, f.market, f.artifact, f.pin)


def invoke_verify(f, result):
    return study.verify(f.root, f.market, f.artifact, f.pin, result["result_sha256"])


def bytes_snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_all_132_fits_seal_before_payoff_and_zero_fit_write_readback(monkeypatch, mock_run):
    result = invoke_run(mock_run)
    assert result["status"] == "complete" and result["actual_fits"] == result["fit_starts"] == 132
    assert result["cells"] == 6 and mock_run.state["forward_reads"] == 1
    assert len(list(mock_run.root.glob("months/*/progress-*-complete.json"))) == 132
    before = bytes_snapshot(mock_run.root)

    def forbidden(*a, **k):
        pytest.fail("readback attempted fit/inference/write")

    for name in ("fit_gamma", "fit_gru", "_gamma_model"):
        monkeypatch.setattr(study, name, forbidden)
    monkeypatch.setattr(study.fixed, "make_gru", forbidden)
    monkeypatch.setattr(study.base, "atomic_new", forbidden)
    monkeypatch.setattr(study.lifecycle, "atomic_bytes", forbidden)
    replay = invoke_verify(mock_run, result)
    assert replay["replay"] == "exact_metrics/cached_prediction_binding"
    assert replay["actual_fits"] == 132
    assert replay["fits"] == replay["inference"] == replay["searches"] == replay["writes"] == 0
    assert before == bytes_snapshot(mock_run.root)


@pytest.mark.parametrize("asset", [0, 1, 2])
@pytest.mark.parametrize("fault", ["gamma_convergence", "forecast_numeric", "compute_stop"])
def test_each_gamma_completion_recorded_before_failure(monkeypatch, mock_run, asset, fault):
    original = study.fit_gamma

    def failed(p, a, *, deadline, progress):
        if a == asset:
            progress()
            raise study.base.StudyFault(fault)
        return original(p, a, deadline=deadline, progress=progress)

    monkeypatch.setattr(study, "fit_gamma", failed)
    result = invoke_run(mock_run)
    assert result["status"] == "failed" and result["reason"] == fault
    assert result["actual_fits"] == result["fit_starts"] == asset + 1
    assert (mock_run.root / f"months/00/progress-gamma-{asset}-complete.json").exists()
    assert result["cells"] == mock_run.state["forward_reads"] == 0
    assert invoke_verify(mock_run, result)["replay"] == "failure_binding_only"


def test_gamma_rank_failure_records_start_not_completion(monkeypatch, mock_run):
    def rank(*a, **k):
        raise study.base.StudyFault("gamma_rank")

    monkeypatch.setattr(study, "fit_gamma", rank)
    result = invoke_run(mock_run)
    assert result["actual_fits"] == 0 and result["fit_starts"] == 1
    assert result["reason"] == "gamma_rank" and result["cells"] == 0
    assert invoke_verify(mock_run, result)["replay"] == "failure_binding_only"


@pytest.mark.parametrize("fault", ["forecast_numeric", "compute_stop"])
def test_gru_completion_before_posttraining_fault(monkeypatch, mock_run, fault):
    def bad(p, *, deadline, progress):
        for update in (128, 256, 384, 512):
            progress(update)
        raise study.base.StudyFault(fault)

    monkeypatch.setattr(study, "fit_gru", bad)
    result = invoke_run(mock_run)
    assert result["actual_fits"] == result["fit_starts"] == 4
    assert result["cells"] == mock_run.state["forward_reads"] == 0
    assert invoke_verify(mock_run, result)["replay"] == "failure_binding_only"


def test_middle_month_failure_never_scores_partial_path(monkeypatch, mock_run):
    original = study.fit_gru

    def bad(p, **kwargs):
        result = original(p, **kwargs)
        if mock_run.state["gru"] == 17:
            raise study.base.StudyFault("compute_stop")
        return result

    monkeypatch.setattr(study, "fit_gru", bad)
    result = invoke_run(mock_run)
    assert result["actual_fits"] == 68 and result["status"] == "failed"
    assert result["cells"] == mock_run.state["forward_reads"] == 0
    assert invoke_verify(mock_run, result)["replay"] == "failure_binding_only"


def test_required_input_gap_scoped_no_fit(monkeypatch, mock_run):
    def missing(*a, **k):
        raise study.base.StudyFault("required_date_gap")

    monkeypatch.setattr(study.PreparationCache, "prepare", missing)
    result = invoke_run(mock_run)
    assert result["status"] == "input_unavailable" and result["actual_fits"] == 0
    assert result["cells"] == 0
    assert invoke_verify(mock_run, result)["replay"] == "failure_binding_only"


@pytest.mark.parametrize(
    "artifact",
    [
        "months/00/gamma-1.npz",
        "months/32/gru.safetensors",
        "months/16/scaler.json",
        "months/08/progress-gamma-2-complete.json",
        "predictions.json",
    ],
)
def test_readback_rejects_mutated_bound_artifact(mock_run, artifact):
    result = invoke_run(mock_run)
    path = mock_run.root / artifact
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(study.base.StudyFault, match="artifact_binding"):
        invoke_verify(mock_run, result)


def test_rehashed_progress_count_forgery_rejected(mock_run):
    result = invoke_run(mock_run)
    name = "months/00/progress-gamma-1-complete.json"
    path = mock_run.root / name
    raw = json.loads(path.read_bytes())
    raw["completed_fits"] = 3
    path.write_bytes(study.encode(raw))
    result_path = mock_run.root / "worker-result.json"
    raw_result = json.loads(result_path.read_bytes())
    raw_result["artifact_sha256"][name] = study.digest(path.read_bytes())
    result_path.write_bytes(study.encode(raw_result))
    result["result_sha256"] = study.digest(result_path.read_bytes())
    with pytest.raises(study.base.StudyFault, match="progress_binding"):
        invoke_verify(mock_run, result)


def test_contract_recipe_and_code_are_bound_before_market_read(monkeypatch, tmp_path, plan):
    artifact = tmp_path / "A"
    root = artifact / "research" / study.NAME
    root.mkdir(parents=True)
    code_root = tmp_path / "code"
    pins = {}
    for name in study.CODE:
        path = code_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic code")
        pins[name] = study.digest(path.read_bytes())
    commitment = dict(
        calendar_sha256=study.base.CALENDAR_PIN,
        kind="kis-cross-asset-d1-price-only-input-v1",
        no_date_fill=True,
        source_pins=pins,
    )
    contract = dict(
        name=study.NAME,
        config=study.configuration(),
        runtime=study.RUNTIME,
        source_root=str(code_root),
        code_sha256=pins,
        input_commitment_sha256=study.base.INPUT_PIN,
        plan=plan.record(),
    )
    checked = []

    def json_read(path, pin=None, **k):
        return (
            contract
            if path.name == "precommit.json"
            else ({} if path.name == "geometry-20261008-v1.json" else commitment)
        )

    monkeypatch.setattr(study, "REPO", code_root)
    monkeypatch.setattr(study.base, "_json", json_read)
    monkeypatch.setattr(study, "runtime_identity", lambda: study.RUNTIME)
    monkeypatch.setattr(study, "build_plan", lambda: plan)
    monkeypatch.setattr(study.rolling, "validate_geometry", lambda g, p: checked.append(p))
    assert study.read_contract(root, artifact, "synthetic")[0] == contract
    assert checked == [plan]
    contract["config"]["gamma"]["alpha"] = 1
    with pytest.raises(study.base.StudyFault, match="contract_config"):
        study.read_contract(root, artifact, "synthetic")
    contract["config"] = study.configuration()
    next(iter(code_root.rglob("*.py"))).write_bytes(b"changed")
    with pytest.raises(study.base.StudyFault, match="code_changed"):
        study.read_contract(root, artifact, "synthetic")


def test_cli_source_free_smoke_and_strict_roots(monkeypatch, capsys):
    monkeypatch.setattr(
        study, "synthetic_smoke", lambda: dict(status="smoke_passed", actual_fits=0)
    )
    assert study.main(["--phase", "smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["actual_fits"] == 0
    with pytest.raises(SystemExit):
        study.main(["--phase", "verify"])
    with pytest.raises(SystemExit):
        study.main(["--phase", "smoke", "--root", "not-allowed"])


def test_source_free_smoke_zero_fit_optimizer_or_gpu(monkeypatch):
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(study, "_gamma_model", lambda: object())
    monkeypatch.setattr(torch.cuda, "is_available", lambda: pytest.fail("GPU query"))
    monkeypatch.setattr(torch.optim.AdamW, "step", lambda *a: pytest.fail("optimizer step"))
    result = study.synthetic_smoke()
    assert result["status"] == "smoke_passed" and result["planned_fits"] == 132
    assert result["actual_market_reads"] == result["actual_fits"] == result["optimizer_steps"] == 0
    assert result["gpu"] is False and len(result["synthetic_cpu_forward_backward_seconds"]) == 3
