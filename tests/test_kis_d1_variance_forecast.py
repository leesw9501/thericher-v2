"""Synthetic variance targets, TRAIN scaling, fit accounting and bound cached replay."""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
from dataclasses import replace
from datetime import date
from decimal import ROUND_DOWN, Decimal, localcontext
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import kis_d1_variance_forecast as study

D = Decimal


@pytest.fixture(scope="module")
def plan():
    return study.build_plan()


@pytest.fixture(scope="module")
def rows(plan):
    dates = study.required_dates(plan, plan.train_indices + plan.dev_indices)
    dates |= study.required_dates(plan, plan.train_indices + plan.dev_indices, forward=True)
    return {s: tuple(study.base.PriceClose(s, d, "synthetic", D(100 + d.toordinal() % (17 + a)))
                     for d in sorted(dates)) for a, s in enumerate(study.base.INSTRUMENT_ORDER)}


@pytest.fixture(scope="module")
def prepared(plan):
    n, m = len(plan.train_indices), len(plan.dev_indices)
    raw = np.random.default_rng(101).normal(0, .01, (n + m, 3, 63))
    target = np.full((n, 3), .0001)
    return study.prepare_arrays(raw, target, plan)


def test_parent_interface_and_fixed_recipe():
    config = study.configuration()
    assert study.CANDIDATES == ("ols", "gru") and config["cells"] == 6
    assert config["metric_values"] == 12 and config["fits"] == 2
    assert config["accounting"] == "target-only variance; no NAV/trading costs/Paper"
    assert config["gru"]["updates"] == 512 and config["gru"]["parameters"] == 3651
    assert study.RUNTIME["torch"] == "2.7.0+cu128" and study.RUNTIME["safetensors"] == "0.8.0"
    assert config["geometry"]["train_entries"] == 503
    assert config["geometry_receipt"]["sha256"] == study.GEOMETRY_PIN
    assert config["paper_input"] is False and config["holdout_access"] == "none"
    assert "actions.json" not in study.ARTIFACTS and "predictions.json" in study.ARTIFACTS


def test_exact_train_dev_label_calendar(plan):
    assert len(plan.train_indices) == 503 and len(plan.dev_indices) == 33 and plan.block_cut == 12
    first, last = plan.train_indices[0], plan.train_indices[-1]
    assert plan.sessions[first - 64].session_date == date(2021, 8, 31)
    assert plan.sessions[first + 20].session_date == date(2021, 12, 30)
    assert plan.sessions[last + 20].session_date == date(2023, 12, 29)
    assert plan.sessions[last + 20].close_at == plan.sessions[plan.dev_indices[0] - 1].close_at
    assert plan.sessions[plan.dev_indices[-1] + 20].session_date == date(2026, 9, 30)
    required = study.required_dates(plan, plan.train_indices + plan.dev_indices)
    required |= study.required_dates(plan, plan.train_indices + plan.dev_indices, forward=True)
    assert len(required) == 1276 and min(required) == date(2021, 8, 31)
    train_sets = [set(s.session_date for s in plan.sessions[i:i + 21])
                  for i in plan.train_indices[::21]]
    assert len(train_sets) == 24 and sum(map(len, train_sets)) == len(set.union(*train_sets))
    windows = [set(s.session_date for s in plan.sessions[i:i + 21]) for i in plan.dev_indices]
    assert sum(bool(a & b) for a, b in zip(windows, windows[1:], strict=False)) == 12
    record = plan.record()
    december = next(j for j, i in enumerate(plan.dev_indices)
                    if plan.sessions[i].session_date == date(2024, 12, 2))
    assert record["decisions"][503 + december].endswith("18:00:00+00:00")
    assert "sessions=" not in repr(plan)


def test_calendar_gap_cannot_shorten_campaign(plan):
    i = plan.train_indices[1]
    with pytest.raises(study.base.StudyFault, match="train_target_cutoff"):
        study.build_plan(plan.sessions[:i] + plan.sessions[i + 1:])


def test_simple_returns_target_population_variance(rows, plan):
    i = plan.train_indices[0]
    dates = tuple(s.session_date for s in plan.sessions[i - 1:i + 21])
    result = study.forward_target(rows, plan, i, "synthetic")
    with localcontext(study.base.CONTEXT):
        matrix = np.asarray([[float((r[b].close - r[a].close) / r[a].close)
            for a, b in zip(dates, dates[1:], strict=False)]
            for symbol in study.base.INSTRUMENT_ORDER
            for r in [{v.session_date: v for v in rows[symbol]}]])
    np.testing.assert_array_equal(result, np.maximum(matrix.var(axis=1, ddof=0), study.FLOOR))
    assert not np.array_equal(result, matrix.var(axis=1, ddof=1))
    assert len(dates) == 22 and dates[0] == plan.sessions[i - 1].session_date
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        np.testing.assert_array_equal(result, study.forward_target(rows, plan, i, "synthetic"))


def test_constant_target_floor_and_price_scale(rows, plan):
    flat = {s: tuple(replace(r, close=D(100)) for r in values) for s, values in rows.items()}
    i = plan.train_indices[0]
    np.testing.assert_array_equal(study.forward_target(flat, plan, i, "synthetic"),
                                  np.full(3, study.FLOOR))
    scaled = {s: tuple(replace(r, close=r.close * D(a + 2)) for r in values)
              for a, (s, values) in enumerate(rows.items())}
    np.testing.assert_array_equal(study.past_features(rows, plan, i, "synthetic"),
                                  study.past_features(scaled, plan, i, "synthetic"))
    np.testing.assert_array_equal(study.forward_target(rows, plan, i, "synthetic"),
                                  study.forward_target(scaled, plan, i, "synthetic"))


def test_current_future_support_never_controls_past_features(rows, plan):
    i = plan.dev_indices[0]
    cutoff = plan.sessions[i - 1].session_date
    before = study.past_features(rows, plan, i, "synthetic")

    class Unread:
        def __init__(self, day):
            self.session_date = day

        @property
        def close(self):
            pytest.fail("future close consulted for past feature")

    changed = {s: tuple(r for r in values if r.session_date <= cutoff) + (
        Unread(plan.sessions[i].session_date), Unread(date(2027, 1, 1)))
        for s, values in rows.items()}
    np.testing.assert_array_equal(before, study.past_features(changed, plan, i, "synthetic"))
    np.testing.assert_array_equal(before, study.past_features(
        {s: tuple(reversed(v)) for s, v in changed.items()}, plan, i, "synthetic"))


@pytest.mark.parametrize("symbol", study.base.INSTRUMENT_ORDER)
@pytest.mark.parametrize("forward", [False, True])
def test_required_past_or_target_gap_never_substituted(rows, plan, symbol, forward):
    i = plan.dev_indices[0]
    day = plan.sessions[i + 3 if forward else i - 4].session_date
    changed = dict(rows)
    changed[symbol] = tuple(r for r in rows[symbol] if r.session_date != day)
    with pytest.raises(study.base.StudyFault, match="required_session_missing"):
        (study.forward_target if forward else study.past_features)(changed, plan, i, "synthetic")


@pytest.mark.parametrize("kind", ["duplicate", "vintage", "symbol"])
def test_required_price_identity(rows, plan, kind):
    i = plan.train_indices[0]
    day = plan.sessions[i - 64].session_date
    first = next(r for r in rows["SPY"] if r.session_date == day)
    changed = dict(rows)
    changed["SPY"] = rows["SPY"] + (first,) if kind == "duplicate" else tuple(
        replace(r, **({"vintage_ref": "another"} if kind == "vintage" else {"symbol": "TLT"}))
        if r.session_date == day else r for r in rows["SPY"])
    with pytest.raises(study.base.StudyFault, match="required_(session_duplicate|row_binding)"):
        study.past_features(changed, plan, i, "synthetic")


def test_train_only_scalers_har_1_5_22_and_zero_std(plan):
    n, m = len(plan.train_indices), len(plan.dev_indices)
    raw = np.random.default_rng(101).normal(0, .01, (n + m, 3, 63))
    targets = np.full((n, 3), .0001)
    before = study.prepare_arrays(raw, targets, plan)
    altered = raw.copy()
    altered[n:] *= 100
    after = study.prepare_arrays(altered, targets, plan)
    for key in ("mean", "divisor", "har_mean", "har_divisor", "target_log_mean",
                "train_raw_sha256", "train_x_sha256", "train_har_sha256", "labels_sha256"):
        assert before.scaler[key] == after.scaler[key]
    np.testing.assert_array_equal(before.train_x, after.train_x)
    expected_har = np.stack([np.mean(raw[:n, a, -k:]**2, axis=1)
                            for a in range(3) for k in (1, 5, 22)], axis=1)
    np.testing.assert_array_equal(expected_har.mean(axis=0), before.scaler["har_mean"])
    np.testing.assert_array_equal(before.baseline,
                                  np.maximum(raw[n:, :, -21:].var(axis=2, ddof=0), study.FLOOR))
    zero = study.prepare_arrays(np.zeros_like(raw), targets, plan)
    assert zero.scaler["divisor"] == [1.] * 3 and zero.scaler["har_divisor"] == [1.] * 9
    assert not zero.train_x.flags.writeable and not zero.labels.flags.writeable
    assert zero.train_x.shape == (503, 3, 63) and zero.train_har.shape == (503, 9)
    assert "train_x=" not in repr(before)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1000., -1000.])
def test_nonfinite_or_overflow_forecasts_not_rescued(value):
    with pytest.raises((study.base.StudyFault, FloatingPointError)):
        study.forecast_variance([[value] * 3] * 33, 33)


def test_predictions_are_not_floored_or_clipped():
    logs = np.array([[math.log(1e-20), math.log(.0001), math.log(.01)]])
    values = study.forecast_variance(logs, 1)
    np.testing.assert_array_equal(values, np.exp(logs))
    assert 0 < values[0, 0] < study.FLOOR
    assert "no prediction floor/clipping" in study.configuration()["forecast"]


def predictions(plan, value=.0001):
    logs = np.full((len(plan.dev_indices), 3), math.log(value)).tolist()
    return dict(plan=plan.record(), log_forecasts=dict(ols=logs, gru=logs),
                baseline=np.full((len(plan.dev_indices), 3), value).tolist())


def test_six_structured_cells_metrics_and_all_asset_diagnostics(plan):
    targets = np.full((33, 3), .0002)
    cells = study.evaluate(targets, predictions(plan), plan)
    assert len(cells) == 6 and sum(len(c["metrics"]) for c in cells) == 12
    for cell in cells:
        assert cell["decision_count"] == (12 if cell["block"] == 0 else 21)
        assert set(cell["asset_metrics"]) == set(study.base.INSTRUMENT_ORDER)
        assert float(cell["metrics"]["qlike"]) == pytest.approx(1 - math.log(2))
        assert float(cell["metrics"]["log_mse"]) == pytest.approx(math.log(2)**2)
    assert study.criterion(cells) == dict(ols="rejected", gru="rejected")
    with pytest.raises(study.base.StudyFault, match="target_numeric"):
        study.evaluate(targets[:-1], predictions(plan), plan)


def artificial_cells():
    return [dict(block=b, method=m, status="complete", metrics=dict(
        qlike=str({"baseline": 2, "ols": 1, "gru": .5}[m]),
        log_mse=str({"baseline": 2, "ols": 1, "gru": .5}[m])))
        for b in (0, 1) for m in study.METHODS]


@pytest.mark.parametrize("metric", study.METRICS)
@pytest.mark.parametrize("block", [0, 1])
def test_original_strict_both_block_kill(metric, block):
    cells = artificial_cells()
    assert study.criterion(cells) == dict(ols="development_survivor", gru="development_survivor")
    own = next(c for c in cells if c["method"] == "gru" and c["block"] == block)
    own["metrics"][metric] = ".9999999999"
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert study.criterion(cells)["gru"] == "rejected"
    own["metrics"][metric] = ".999999999899999999999"
    assert study.criterion(cells)["gru"] == "development_survivor"
    next(c for c in cells if c["method"] == "ols" and c["block"] == block)["metrics"][metric] = "2"
    assert study.criterion(cells)["ols"] == "rejected"


def test_missing_matrix_and_nonfinite_metric_rejected():
    cells = artificial_cells()
    with pytest.raises(study.base.StudyFault, match="cell_matrix"):
        study.criterion(cells[:-1])
    cells[-1]["metrics"]["qlike"] = "NaN"
    with pytest.raises(study.base.StudyFault, match="cell_metrics"):
        study.criterion(cells)


def synthetic_source(plan):
    dates = study.required_dates(plan, plan.train_indices + plan.dev_indices)
    dates |= study.required_dates(plan, plan.train_indices + plan.dev_indices, forward=True)
    files = []
    for symbol in study.base.INSTRUMENT_ORDER:
        text = io.StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(study.base.COLUMNS)
        writer.writerows((symbol, study.base.EXCHANGES[symbol], d.isoformat(), "NaN", "100", "toy")
                         for d in sorted(dates))
        files.append((symbol, gzip.compress(text.getvalue().encode(), mtime=0)))
    return study.base.SourceInputs(tuple(files), {}, SimpleNamespace(sessions=plan.sessions))


def test_prepare_close_only_targets_train_only_no_future_mask(plan):
    source = synthetic_source(plan)
    prepared = study.prepare_inputs(source, plan)
    assert prepared.train_x.shape == (503, 3, 63) and prepared.labels.shape == (503, 3)
    np.testing.assert_array_equal(prepared.labels, np.full((503, 3), math.log(study.FLOOR)))
    # Final DEV targets are not needed for inputs/scalers/fits, including the last entry CLOSE.
    final_entry = plan.sessions[plan.dev_indices[-1]].session_date
    files = tuple((s, gzip.compress("\n".join(
        line for line in gzip.decompress(raw).decode().splitlines()
        if not line.startswith(f"{s},{study.base.EXCHANGES[s]},{final_entry.isoformat()},"))
        .encode(), mtime=0)) for s, raw in source.files)
    changed = replace(source, files=files)
    altered = study.prepare_inputs(changed, plan)
    assert altered.scaler == prepared.scaler
    with pytest.raises(study.base.StudyFault, match="required_date_gap"):
        study.load_dev_targets(changed, plan)


@pytest.fixture
def worker(tmp_path, monkeypatch, plan, prepared):
    artifact = tmp_path / "artifacts"
    root = artifact / "research" / study.NAME
    root.mkdir(parents=True)
    contract = dict(plan=plan.record())
    study.base.atomic_new(root / "precommit.json", contract)
    pin = study.digest(study.encode(contract))
    monkeypatch.setattr(study, "read_contract", lambda *a: (contract, {}))
    monkeypatch.setattr(study.base, "load_committed_source",
                        lambda *a, **kw: synthetic_source(plan))
    monkeypatch.setattr(study, "prepare_inputs", lambda *a, **kw: prepared)

    def ols(*a, **kw):
        kw["progress"]()
        return np.log(prepared.baseline).tolist(), b"synthetic-numeric-NPZ", {}

    def gru(*a, **kw):
        for update in (128, 256, 384, 512):
            kw["progress"](update)
        return np.log(prepared.baseline).tolist(), b"synthetic-own-safetensors", {}

    monkeypatch.setattr(study, "fit_ols", ols)
    monkeypatch.setattr(study, "fit_gru", gru)
    return root, artifact, pin


def test_worker_seals_before_dev_targets_all_ro_cached_binding(worker, monkeypatch):
    root, artifact, pin = worker
    original = study.load_dev_targets

    def targets(source, plan, **kwargs):
        assert (root / "predictions.json").is_file()
        return original(source, plan, **kwargs)

    monkeypatch.setattr(study, "load_dev_targets", targets)
    result = study.run(root, artifact, artifact, pin)
    assert result["status"] == "complete" and result["phase"] == "validate" and result["cells"] == 6
    assert result["actual_fits"] == result["fit_starts"] == 2
    assert result["financial_nav_claim"] is False and "log_forecasts" not in json.dumps(result)
    originals = {p.name: p.read_bytes() for p in root.iterdir()}
    monkeypatch.setattr(study, "fit_ols", lambda *a, **k: pytest.fail("readback OLS refit"))
    monkeypatch.setattr(study, "fit_gru", lambda *a, **k: pytest.fail("readback GPU refit"))
    monkeypatch.setattr(study.base, "atomic_new", lambda *a: pytest.fail("readback wrote"))
    replay = study.verify(root, artifact, artifact, pin, result["result_sha256"])
    assert replay["replay"] == "exact_metrics/cached_prediction_binding"
    assert replay["actual_fits"] == 2
    assert all(replay[k] == 0 for k in ("fits", "inference", "searches", "writes"))
    assert originals == {p.name: p.read_bytes() for p in root.iterdir()}


@pytest.mark.parametrize("phase", ["prepare", "ols", "gru", "forward"])
def test_failure_fit_counts_before_training(worker, monkeypatch, phase):
    root, artifact, pin = worker

    def fail(*a, **kw):
        raise study.base.StudyFault("compute_stop")

    monkeypatch.setattr(study, {"prepare": "prepare_inputs", "ols": "fit_ols", "gru": "fit_gru",
                               "forward": "load_dev_targets"}[phase], fail)
    result = study.run(root, artifact, artifact, pin)
    assert result["actual_fits"] == {"prepare": 0, "ols": 0, "gru": 1, "forward": 2}[phase]
    assert result["fit_starts"] == {"prepare": 0, "ols": 1, "gru": 2, "forward": 2}[phase]
    assert result["cells"] == 0 and result["status"] == "failed"
    assert study.verify(root, artifact, artifact, pin, result["result_sha256"])["replay"] \
        == "failure_binding_only"
    with pytest.raises(study.base.StudyFault, match="attempt_exists"):
        study.run(root, artifact, artifact, pin)


@pytest.mark.parametrize("member", ["ols", "gru"])
@pytest.mark.parametrize("fault", ["prediction", "serialization", "deadline"])
def test_completed_fit_record_precedes_post_training_fault(worker, monkeypatch, member, fault):
    root, artifact, pin = worker

    def trained(*a, **kw):
        if member == "ols":
            kw["progress"]()
        else:
            for update in (128, 256, 384, 512):
                kw["progress"](update)
        if fault == "deadline":
            raise study.base.StudyFault("compute_stop")
        raise ValueError("private post-training value")

    monkeypatch.setattr(study, "fit_" + member, trained)
    result = study.run(root, artifact, artifact, pin)
    assert result["actual_fits"] == result["fit_starts"] == (1 if member == "ols" else 2)
    completion = json.loads((root / f"progress-{member}-complete.json").read_bytes())
    assert completion["completed_fits"] == result["actual_fits"]
    assert completion["training_completion"] == (
        "lstsq_returned" if member == "ols" else "512_optimizer_updates")
    assert b"private post-training" not in (root / "worker-result.json").read_bytes()
    assert study.verify(root, artifact, artifact, pin, result["result_sha256"])["replay"] \
        == "failure_binding_only"


@pytest.mark.parametrize("name", ["ols.npz", "gru.safetensors", "scaler.json", "predictions.json",
                                   "progress-gru-complete.json"])
def test_artifact_mutations_rejected(worker, name):
    root, artifact, pin = worker
    result = study.run(root, artifact, artifact, pin)
    (root / name).write_bytes(b"tampered")
    with pytest.raises(study.base.StudyFault, match="artifact_binding"):
        study.verify(root, artifact, artifact, pin, result["result_sha256"])


def test_false_counter_progress_rejected_even_if_rehashed(worker):
    root, artifact, pin = worker
    study.run(root, artifact, artifact, pin)
    path = root / "progress-gru-0128.json"
    progress = json.loads(path.read_bytes())
    progress["completed_fits"] = 2
    path.write_bytes(study.encode(progress))
    path = root / "worker-result.json"
    result = json.loads(path.read_bytes())
    result["artifact_sha256"] = study._artifacts(root)
    path.write_bytes(study.encode(result))
    with pytest.raises(study.base.StudyFault, match="progress_binding"):
        study.verify(root, artifact, artifact, pin, study.digest(path.read_bytes()))


def test_model_prediction_binding_not_reinference(worker):
    root, artifact, pin = worker
    study.run(root, artifact, artifact, pin)
    path = root / "predictions.json"
    predictions = json.loads(path.read_bytes())
    predictions["model_sha256"]["ols.npz"] = study.digest(b"different model")
    path.write_bytes(study.encode(predictions))
    path = root / "worker-result.json"
    result = json.loads(path.read_bytes())
    result["artifact_sha256"] = study._artifacts(root)
    path.write_bytes(study.encode(result))
    with pytest.raises(study.base.StudyFault, match="prediction_binding"):
        study.verify(root, artifact, artifact, pin, study.digest(path.read_bytes()))


def test_ols_progress_before_prediction_save_and_deadline(prepared, monkeypatch):
    events = []
    monkeypatch.setattr(np.linalg, "lstsq", lambda *a, **kw: (
        np.zeros((10, 3)), np.zeros(3), 10, np.ones(10)))
    original = np.column_stack

    def columns(values):
        if len(values[0]) == 33:
            assert events == ["completed"]
            raise ValueError("synthetic prediction failure")
        return original(values)

    monkeypatch.setattr(np, "column_stack", columns)
    with pytest.raises(ValueError, match="synthetic prediction"):
        study.fit_ols(prepared, deadline=float("inf"), progress=lambda: events.append("completed"))


def test_synthetic_ols_archive_contains_numeric_only(prepared):
    completion = []
    prediction, raw, resources = study.fit_ols(prepared, deadline=float("inf"),
                                              progress=lambda: completion.append(True))
    assert completion == [True] and np.asarray(prediction).shape == (33, 3)
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        assert set(archive.files) == {"coefficients", "rank", "singular_values"}
        assert archive["coefficients"].shape == (10, 3)
        assert all(not archive[k].dtype.hasobject for k in archive.files)
    assert resources["rank"] <= 10


def test_optional_cpu_gru_geometry_gradient_no_cuda():
    torch = pytest.importorskip("torch")
    with torch.random.fork_rng(devices=[]):
        torch.default_generator.manual_seed(study.SEED)
        model = study.make_gru()
        assert sum(p.numel() for p in model.parameters()) == 3651
        x = torch.zeros((2, 3, 63), dtype=torch.float32, device="cpu")
        output = model(x)
        assert output.shape == (2, 3) and torch.isfinite(output).all()
        output.square().mean().backward()
        assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())


def test_optional_cpu_smoke_has_zero_source_fits_steps_gpu(monkeypatch, plan):
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: pytest.fail("smoke CUDA probe"))
    monkeypatch.setattr(study.base, "_read", lambda *a: pytest.fail("smoke actual source read"))
    monkeypatch.setattr(study.base, "calendar_sessions", lambda: plan.sessions)
    monkeypatch.setattr(study, "fit_ols", lambda *a, **kw: pytest.fail("smoke fit"))
    monkeypatch.setattr(study, "fit_gru", lambda *a, **kw: pytest.fail("smoke actual GRU fit"))
    result = study.synthetic_smoke()
    assert result["cells"] == 6 and result["metric_values"] == 12
    assert result["train_entries"] == 503 and result["view_entries"] == [12, 21]
    assert result["actual_market_reads"] == result["actual_fits"] == result["optimizer_steps"] == 0
    assert result["gpu"] is False and len(result["synthetic_cpu_forward_backward_seconds"]) == 3


def test_source_code_runtime_geometry_binding(tmp_path, monkeypatch, plan):
    artifact, repo = tmp_path / "artifacts", tmp_path / "source"
    root = artifact / "research" / study.NAME
    root.mkdir(parents=True)
    monkeypatch.setattr(study, "REPO", repo)
    code = {}
    for relative in study.CODE:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic frozen source")
        code[relative] = study.digest(path.read_bytes())
    commitment = dict(calendar_sha256=study.base.CALENDAR_PIN,
        kind="kis-cross-asset-d1-price-only-input-v1", no_date_fill=True,
        source_pins={study.CODE[-1]: code[study.CODE[-1]]})
    input_path = artifact / study.base.INPUT_RELATIVE
    input_path.parent.mkdir(parents=True)
    study.base.atomic_new(input_path, commitment)
    monkeypatch.setattr(study.base, "INPUT_PIN", study.digest(input_path.read_bytes()))
    geometry = dict(goal=study.NAME, input=dict(sha256=study.base.INPUT_PIN),
        calendar=dict(sha256=study.base.CALENDAR_PIN), train=dict(entry_count=503),
        dev=dict(view_entry_counts=[12, 21]), geometry=dict(required_source_date_count=1276))
    path = artifact / study.GEOMETRY_RELATIVE
    path.parent.mkdir(parents=True)
    study.base.atomic_new(path, geometry)
    monkeypatch.setattr(study, "GEOMETRY_PIN", study.digest(path.read_bytes()))
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME))
    contract = dict(name=study.NAME, config=study.configuration(), runtime=dict(study.RUNTIME),
        source_root=str(repo), source_archive_root="D:/opaque-host-archive", code_sha256=code,
        input_commitment_sha256=study.base.INPUT_PIN, plan=plan.record())
    study.base.atomic_new(root / "precommit.json", contract)
    pin = study.digest(study.encode(contract))
    assert study.read_contract(root, artifact, pin) == (contract, commitment)
    monkeypatch.setattr(study, "runtime_identity", lambda: {})
    with pytest.raises(study.base.StudyFault, match="runtime_identity"):
        study.read_contract(root, artifact, pin)
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME))
    (repo / study.CODE[-1]).write_bytes(b"changed")
    with pytest.raises(study.base.StudyFault, match="code_changed"):
        study.read_contract(root, artifact, pin)


def test_cli_shape_and_safe_projection(monkeypatch, capsys):
    monkeypatch.setattr(study, "synthetic_smoke", lambda: dict(status="smoke_passed", cells=6,
                                                              actual_fits=0))
    assert study.main(["--phase", "smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["cells"] == 6
    with pytest.raises(SystemExit):
        study.main(["--phase", "run"])
    with pytest.raises(SystemExit):
        study.main(["--phase", "smoke", "--root", "D:/unused"])
