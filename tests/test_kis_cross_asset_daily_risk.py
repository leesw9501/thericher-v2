"""Source-free tests: no actual market rows, fits, CUDA probes or broker paths."""

from __future__ import annotations

import csv
import gzip
import io
import json
from dataclasses import replace
from datetime import date
from decimal import ROUND_DOWN, Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace

import pytest

from thericher_v2.research import kis_cross_asset_daily_risk as study

D = Decimal


@pytest.fixture(scope="module")
def plan():
    return study.build_plan()


@pytest.fixture(scope="module")
def marks(plan):
    return tuple(study.nav.ThreeAssetDay(d, (D(100),) * 3, (D(100),) * 3) for d in plan.dates)


def predictions(plan, *, hgb=.25, attention=.75):
    return dict(plan=plan.record(), nonloss_fraction="0.5", probabilities=dict(
        hgb=[hgb] * len(plan.groups), attention=[attention] * len(plan.groups)))


@pytest.fixture(scope="module")
def actions(plan):
    return study.prepare_actions(predictions(plan), plan)


@pytest.fixture(scope="module")
def cells(marks, plan, actions):
    return study.evaluate(marks, actions, plan)


@pytest.fixture(scope="module")
def source(plan):
    files = []
    for symbol in study.base.INSTRUMENT_ORDER:
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(study.base.COLUMNS)
        for j, session in enumerate(plan.sessions):
            if date(2021, 8, 20) <= session.session_date <= date(2026, 10, 7):
                value = str(1000 + j % 17)
                writer.writerow([symbol, study.base.EXCHANGES[symbol],
                                 session.session_date.isoformat(), value, value, "synthetic"])
        files.append((symbol, gzip.compress(text.getvalue().encode(), mtime=0)))
    return study.base.SourceInputs(tuple(files), {}, study.base.build_plan(plan.sessions))


@pytest.fixture(scope="module")
def prepared(source, plan):
    return study.prepare_inputs(source, plan)


def test_static_contract_no_grid_or_daily_overwrite():
    c = study.configuration()
    assert c["cells"] == 42 and c["fits"] == 2 and c["seconds"] == 300
    assert c["runtime"]["scikit-learn"] == "1.9.1"
    assert c["attention"]["updates"] == 512 and c["attention"]["parameters"] == 2353
    assert c["hgb"]["early_stopping"] is False and c["hgb"]["class_weight"] is None
    assert "ln(CLOSE) differences" in c["features"] and "quantization" in c["null"]
    assert c["paper_input"] is False and c["holdout_access"] == "none"


def test_exact_geometry_and_calendar_context(plan):
    assert len(plan.train_indices) == 517 and len(plan.group_indices) == 137
    assert len(plan.dates) == 689 and plan.block_cut == 252
    assert tuple(d for g in plan.groups for d in g) == plan.dates[:685]
    assert plan.groups[-1] == (date(2026, 9, 18), date(2026, 9, 21), date(2026, 9, 22),
                               date(2026, 9, 23), date(2026, 9, 24))
    assert plan.dates[-4:] == (date(2026, 9, 25), date(2026, 9, 28), date(2026, 9, 29),
                               date(2026, 9, 30))
    i = plan.train_indices[0]
    assert plan.sessions[i - 64].session_date == date(2021, 8, 31)
    assert plan.sessions[i - 63].session_date == date(2021, 9, 1)
    assert tuple(s.session_date for s in plan.sessions[plan.train_indices[-1]:
                 plan.train_indices[-1] + 5]) == (
                     date(2023, 12, 20), date(2023, 12, 21), date(2023, 12, 22),
                     date(2023, 12, 26), date(2023, 12, 27))


def test_no_group_reset_at_view_or_month_boundary(plan):
    group = next(g for g in plan.groups if date(2025, 1, 2) in g)
    assert group == (date(2024, 12, 30), date(2024, 12, 31), date(2025, 1, 2),
                     date(2025, 1, 3), date(2025, 1, 6))
    assert any(g[0].month != g[-1].month for g in plan.groups)


@pytest.mark.parametrize("tail", range(5))
def test_all_tail_lengths_no_partial_roundtrip(plan, tail):
    small = replace(plan, dates=plan.dates[:10 + tail], group_indices=plan.group_indices[:2])
    targets = {g[0]: study.allocation() for g in small.groups}
    days = tuple(study.nav.ThreeAssetDay(d, (D(100),) * 3, (D(100),) * 3) for d in small.dates)
    ledger = study.replay_groups(days, targets, small, D(5))
    assert len(ledger.daily) == 10 + tail
    assert all(d.flat and d.fees == 0 and d.traded_notional == 0
               for d in ledger.daily[10:])
    assert all(d.nav == ledger.daily[9].nav for d in ledger.daily[10:])
    assert ledger.daily[5].nav < ledger.daily[0].nav  # no fresh NAV1 group accounts
    unit = ledger.daily[4].nav
    with localcontext(study.base.CONTEXT):
        assert abs(ledger.final_nav - unit * unit) < D("1e-43")


def test_held_inventory_and_denominator_cross_view(plan, marks):
    targets = {g[0]: study.allocation() for g in plan.groups}
    ledger = study.replay_groups(marks, targets, plan, D(5))
    assert not ledger.daily[plan.block_cut - 1].flat
    assert not ledger.daily[plan.block_cut].flat and ledger.daily[plan.block_cut].fees == 0
    assert ledger.daily[plan.block_cut].simple_return == 0
    assert ledger.daily[plan.block_cut + 2].flat  # fifth session Jan6


def test_intermediate_open_mutation_is_not_rebalance(plan, marks):
    targets = {g[0]: study.allocation() for g in plan.groups}
    entries = set(targets)
    changed = tuple(replace(d, adj_open3=(D(999999),) * 3) if d.date not in entries else d
                    for d in marks)
    assert study.replay_groups(changed, targets, plan, D(5)) \
        == study.replay_groups(marks, targets, plan, D(5))


def test_group_target_exact_endpoint_parity(plan):
    from thericher_v2.research.cross_asset_daily_risk_input import (
        RawD1Price,
        build_five_session_target,
    )

    i = plan.group_indices[0]
    sessions = plan.sessions[i:i + 5]
    prices = {s: tuple(RawD1Price(s, d.session_date, "synthetic", D(100), D(101))
                       for d in sessions) for s in study.base.INSTRUMENT_ORDER}
    target = build_five_session_target(prices, scheduled_forward=sessions, vintage_ref="synthetic")
    small = replace(plan, dates=plan.dates[:5], group_indices=plan.group_indices[:1])
    days = tuple(study.nav.ThreeAssetDay(d, (D(100),) * 3, (D(101),) * 3) for d in small.dates)
    ledger = study.replay_groups(days, {small.dates[0]: study.allocation()}, small, D(5))
    assert ledger.final_nav == target.net_factor


@pytest.mark.parametrize("fraction", ["0", "1", "0.01", "0.0000000000001",
    "0.058027079303675048355899419729206963249516441005803"])
def test_exact_fractional_null_cash_residual(fraction):
    with localcontext() as context:
        context.prec, context.rounding = 5, ROUND_DOWN
        target = study.allocation(D(fraction))
    assert sum(map(Fraction, target.weights3), Fraction(0)) + Fraction(target.cash_weight) == 1
    assert len(set(target.weights3)) == 1


def test_nonloss_fraction_no_dev_exposure_fit():
    with localcontext(study.base.CONTEXT):
        expected = D(30) / 517
    assert study.nonloss_fraction([0] * 30 + [1] * 487) == expected


def test_strict_probability_and_fixed_blend(plan):
    pred = predictions(plan, hgb=.5, attention=0.)
    actions = study.prepare_actions(pred, plan)["actions"]
    assert all(tuple(map(D, row[1:4])) == (D(0),) * 3 for row in actions["hgb"])
    assert all(row[1:4] == [str(study.base.THIRD)] * 3 for row in actions["blend"])
    assert len(actions["buyhold"]) == 1
    assert all(len(actions[p]) == 137 for p in study.POLICIES if p != "buyhold")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -.1, 1.1, True])
def test_invalid_probability_is_not_cash(plan, bad):
    with pytest.raises(study.base.StudyFault, match="probabilities"):
        study.prepare_actions(predictions(plan, hgb=bad), plan)


def test_42_cells_continuous_views_and_controls(cells):
    assert len(cells) == 42 and set(study.criterion(cells).values()) == {"rejected"}
    for policy in study.POLICIES:
        for cost in study.COSTS:
            a, b = [c["metrics"] for c in cells
                    if c["policy"] == policy and c["cost_bps"] == str(cost)]
            assert b["entering_nav"] == a["nav"]
            assert (a["days"], b["days"]) == (252, 437)
            assert a["group_entries"] + b["group_entries"] == (1 if policy == "buyhold" else 137)


def test_missing_mark_is_unavailable_not_zero_pnl(plan, actions, marks):
    with pytest.raises(study.base.StudyFault, match="forward_mark_gap"):
        study.evaluate(marks[:-1], actions, plan)
    with pytest.raises(study.base.StudyFault, match="action_keys"):
        study.replay_groups(marks, {}, plan, D(5))


def test_hostile_decimal_replay(plan, actions, marks, cells):
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_DOWN
        assert study.evaluate(marks, actions, plan) == cells


def economic_cells():
    metrics = {p: str(.1 * (1 + study.CANDIDATES.index(p))) if p in study.CANDIDATES else "0"
               for p in study.POLICIES}
    return [dict(block=b, policy=p, cost_bps=str(c), status="complete",
                 metrics=dict(growth=metrics[p], utility=metrics[p]))
            for b in (0, 1) for p in study.POLICIES for c in study.COSTS]


def test_kill_noncyclic_and_both_views():
    cells = economic_cells()
    assert set(study.criterion(cells).values()) == {"development_survivor"}
    next(c for c in cells if c["policy"] == "attention" and c["block"] == 1
         and c["cost_bps"] == "10")["metrics"]["utility"] = "0.1"
    assert study.criterion(cells) == dict(hgb="development_survivor", attention="rejected",
                                         blend="development_survivor")
    cells[-1]["metrics"]["growth"] = "NaN"
    with pytest.raises(study.base.StudyFault, match="cell_metrics"):
        study.criterion(cells)


def test_kill_exact_decimal_tolerance_and_positive_growth():
    cells = economic_cells()
    for cell in cells:
        if cell["policy"] == "hgb":
            cell["metrics"].update(growth="1e-12", utility="1e-12")
        elif cell["policy"] in study.CONTROLS:
            cell["metrics"].update(growth="-1", utility="-1")
    assert study.criterion(cells)["hgb"] == "development_survivor"
    for cell in cells:
        if cell["policy"] == "hgb":
            cell["metrics"].update(growth="0", utility="1")
    assert study.criterion(cells)["hgb"] == "rejected"
    with pytest.raises(study.base.StudyFault, match="cell_matrix"):
        study.criterion(cells[:-1])


def test_train_only_standardizer_and_zero_variance(prepared):
    import numpy as np

    assert prepared.train_x.shape == (517, 6, 63) and prepared.dev_x.shape == (137, 6, 63)
    assert prepared.train_x.dtype == prepared.dev_x.dtype == np.dtype("float32")
    assert np.all(np.isfinite(prepared.train_x))
    assert prepared.scaler["divisor"][1::2] == [1., 1., 1.]
    assert min(prepared.scaler["counts"]) >= 30
    assert prepared.scaler["independent_sample_count"] == "not_claimed"
    assert prepared.scaler["train_earliest_thinned_five_session_blocks"] == 104
    assert not prepared.labels.flags.writeable and not prepared.train_x.flags.writeable
    assert "array" not in repr(prepared)


def test_target_calls_train_only_and_no_tail_feature(source, plan, monkeypatch):
    from thericher_v2.research import cross_asset_daily_risk_input as data

    original, calls = data.build_five_session_target, []
    def target(*args, **kwargs):
        forward = kwargs["scheduled_forward"]
        calls.append((forward[0].session_date, forward[-1].session_date))
        return original(*args, **kwargs)
    monkeypatch.setattr(data, "build_five_session_target", target)
    study.prepare_inputs(source, plan)
    assert len(calls) == 517 and max(last for _, last in calls) == date(2023, 12, 27)
    fields = study.required_fields(plan)
    assert not any(d in fields for d in plan.dates[-4:])


def change_source(source, mutate):
    files = []
    for symbol, raw in source.files:
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=study.base.COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in csv.DictReader(io.StringIO(gzip.decompress(raw).decode())):
            changed = mutate(symbol, row)
            if changed is not None:
                writer.writerow(changed)
        files.append((symbol, gzip.compress(text.getvalue().encode(), mtime=0)))
    return replace(source, files=tuple(files))


def test_unneeded_future_and_tail_prices_do_not_change_inputs(source, prepared, plan):
    def mutate(symbol, row):
        if row["session_date"] >= "2026-09-25":
            row["open"] = row["close"] = "NaN"
        return row
    altered = study.prepare_inputs(change_source(source, mutate), plan)
    assert altered.scaler == prepared.scaler


def test_dev_mutation_cannot_change_train_scaler_or_labels(source, prepared, plan):
    def mutate(symbol, row):
        if row["session_date"] >= "2024-01-02":
            row["close"] = str(D(row["close"]) * D("1.01"))
        return row
    altered = study.prepare_inputs(change_source(source, mutate), plan)
    assert altered.scaler["mean"] == prepared.scaler["mean"]
    assert altered.scaler["divisor"] == prepared.scaler["divisor"]
    assert altered.scaler["labels_sha256"] == prepared.scaler["labels_sha256"]
    assert altered.scaler["dev_raw_sha256"] != prepared.scaler["dev_raw_sha256"]


def test_missing_required_past_no_older_fallback(source, plan):
    def mutate(symbol, row):
        return None if symbol == "TLT" and row["session_date"] == "2021-08-31" else row
    with pytest.raises(study.base.StudyFault, match="required_date_gap"):
        study.prepare_inputs(change_source(source, mutate), plan)


def test_one_class_not_fitted(source, plan):
    def mutate(symbol, row):
        row["open"] = row["close"] = "100"
        return row
    with pytest.raises(study.base.StudyFault, match="insufficient_classes"):
        study.prepare_inputs(change_source(source, mutate), plan)


def test_attention_cpu_shape_2353_params_zero_fit(monkeypatch):
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: pytest.fail("CPU test probed CUDA"))
    torch.set_num_threads(2)
    model = study.make_attention().eval()
    assert sum(p.numel() for p in model.parameters()) == 2353
    assert all(p.device.type == "cpu" and p.dtype == torch.float32 for p in model.parameters())
    with torch.inference_mode():
        result = model(torch.zeros((2, 6, 63), dtype=torch.float32, device="cpu"))
    assert result.shape == (2,) and bool(torch.isfinite(result).all())


def test_hgb_exact_one_mock_fit(prepared, monkeypatch):
    import numpy as np
    ensemble = pytest.importorskip("sklearn.ensemble")
    calls, completed = [], []
    class Fake:
        def __init__(self, **kwargs):
            assert kwargs == study.configuration()["hgb"]
            self.n_iter_, self.classes_ = 100, [0, 1]
        def fit(self, x, y):
            calls.append((x.shape, y.shape))
            return self
        def predict_proba(self, x):
            assert completed == ["fit_returned"]
            return np.tile([.4, .6], (len(x), 1))
    monkeypatch.setattr(ensemble, "HistGradientBoostingClassifier", Fake)
    _, probabilities, resources = study.fit_hgb(prepared, deadline=float("inf"),
        progress=lambda: completed.append("fit_returned"))
    assert calls == [((517, 378), (517,))]
    assert probabilities == [.6] * 137 and resources["iterations"] == 100


def test_hgb_archive_is_safe_numeric_not_pickle():
    import numpy as np
    nodes = np.zeros(1, dtype=[("value", "f8"), ("is_leaf", "u1")])
    model = SimpleNamespace(_predictors=[[SimpleNamespace(nodes=nodes)] for _ in range(100)],
                            _baseline_prediction=np.zeros((1, 1)))
    raw = study.hgb_archive(model)
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        assert len(archive.files) == 101
        assert not archive["nodes_000"].dtype.hasobject


@pytest.fixture
def worker(tmp_path, monkeypatch, source, prepared, plan):
    root = tmp_path / "artifacts" / "research" / study.NAME
    root.mkdir(parents=True)
    artifact = root.parent.parent
    contract = dict(plan=plan.record())
    study.base.atomic_new(root / "precommit.json", contract)
    pin = study.digest((root / "precommit.json").read_bytes())
    monkeypatch.setattr(study, "read_contract", lambda *a: (contract, {}))
    monkeypatch.setattr(study.base, "load_committed_source", lambda *a, **kw: source)
    monkeypatch.setattr(study, "prepare_inputs", lambda *a, **kw: prepared)
    def hgb(*args, **kwargs):
        kwargs["progress"]()
        return object(), [.25] * 137, dict(iterations=100)
    monkeypatch.setattr(study, "fit_hgb", hgb)
    monkeypatch.setattr(study, "hgb_archive", lambda *a: b"synthetic numeric archive")
    def attention(*args, **kwargs):
        for update in (128, 256, 384, 512):
            kwargs["progress"](update)
        return [.75] * 137, b"synthetic safe weights", dict(updates=512, peak_vram_bytes=0)
    monkeypatch.setattr(study, "fit_attention", attention)
    return root, artifact, pin


def test_worker_model_binding_seal_before_marks_and_all_ro(worker, monkeypatch):
    root, artifact, pin = worker
    original = study.load_marks
    def marks(source, plan):
        assert (root / "actions.json").is_file() and (root / "predictions.json").is_file()
        return original(source, plan)
    monkeypatch.setattr(study, "load_marks", marks)
    result = study.run(root, artifact / "unused-market", artifact, pin)
    assert result["status"] == "complete" and result["actual_fits"] == result["fit_starts"] == 2
    assert result["cells"] == 42 and "probabilities" not in json.dumps(result)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    monkeypatch.setattr(study, "fit_hgb", lambda *a, **kw: pytest.fail("readback refit HGB"))
    monkeypatch.setattr(study, "fit_attention", lambda *a, **kw: pytest.fail("readback refit GPU"))
    monkeypatch.setattr(study.base, "atomic_new", lambda *a: pytest.fail("readback wrote"))
    verified = study.verify(root, artifact, artifact, pin, result["result_sha256"])
    assert verified["replay"] == "exact_economic/cached_prediction_binding"
    assert all(verified[key] == 0 for key in ("fits", "inference", "searches", "writes"))
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


@pytest.mark.parametrize("phase", ["prepare", "fit_hgb", "fit_attention", "forward"])
def test_failure_fit_counts_and_immutable_binding(worker, monkeypatch, phase):
    root, artifact, pin = worker
    def fail(*a, **kw):
        raise study.base.StudyFault("compute_stop")
    monkeypatch.setattr(study, {"prepare": "prepare_inputs", "fit_hgb": "fit_hgb",
        "fit_attention": "fit_attention", "forward": "load_marks"}[phase], fail)
    result = study.run(root, artifact, artifact, pin)
    assert result["status"] == "failed" and result["cells"] == 0
    assert result["actual_fits"] == {"prepare": 0, "fit_hgb": 0,
                                     "fit_attention": 1, "forward": 2}[phase]
    assert result["fit_starts"] == {"prepare": 0, "fit_hgb": 1,
                                    "fit_attention": 2, "forward": 2}[phase]
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert study.verify(root, artifact, artifact, pin, result["result_sha256"])["replay"] \
        == "failure_binding_only"
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(study.base.StudyFault, match="attempt_exists"):
        study.run(root, artifact, artifact, pin)


@pytest.mark.parametrize("member", ["hgb", "attention"])
@pytest.mark.parametrize("fault", ["prediction", "serialization", "deadline"])
def test_post_training_failure_preserves_completed_fit(worker, monkeypatch, member, fault):
    root, artifact, pin = worker
    def fail():
        if fault == "deadline":
            raise study.base.StudyFault("compute_stop")
        raise ValueError("private post-training failure")
    if member == "hgb":
        def trained(*args, **kwargs):
            kwargs["progress"]()
            if fault != "serialization":
                fail()
            return object(), [.25] * 137, {}
        monkeypatch.setattr(study, "fit_hgb", trained)
        if fault == "serialization":
            monkeypatch.setattr(study, "hgb_archive", lambda *a: fail())
    else:
        def trained(*args, **kwargs):
            for update in (128, 256, 384, 512):
                kwargs["progress"](update)
            fail()
        monkeypatch.setattr(study, "fit_attention", trained)
    result = study.run(root, artifact, artifact, pin)
    assert result["status"] == "failed" and result["cells"] == 0
    assert result["actual_fits"] == result["fit_starts"] == (1 if member == "hgb" else 2)
    path = root / f"progress-{member}-complete.json"
    completion = json.loads(path.read_bytes())
    assert completion["completed_fits"] == result["actual_fits"]
    assert completion["training_completion"] == (
        "fit_method_returned" if member == "hgb" else "512_optimizer_updates")
    assert b"private post-training" not in (root / "worker-result.json").read_bytes()
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert study.verify(root, artifact, artifact, pin, result["result_sha256"])["replay"] \
        == "failure_binding_only"
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


@pytest.mark.parametrize("name", ["actions.json", "predictions.json", "attention.safetensors",
                                   "hgb.npz", "scaler.json"])
def test_mutated_artifact_cannot_replay(worker, name):
    root, artifact, pin = worker
    result = study.run(root, artifact, artifact, pin)
    (root / name).write_bytes(b"tampered")
    with pytest.raises(study.base.StudyFault, match="artifact_binding"):
        study.verify(root, artifact, artifact, pin, result["result_sha256"])


def test_cpu_smoke_no_actual_source_fit_or_gpu(monkeypatch):
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: pytest.fail("smoke probed GPU"))
    monkeypatch.setattr(study.base, "_read", lambda *a: pytest.fail("smoke read source"))
    monkeypatch.setattr(study, "fit_hgb", lambda *a, **kw: pytest.fail("smoke fit"))
    monkeypatch.setattr(study, "fit_attention", lambda *a, **kw: pytest.fail("smoke fit GPU"))
    result = study.synthetic_smoke()
    assert result["cells"] == 42 and result["dev_groups"] == 137
    assert result["tail_cash_days"] == 4
    assert result["actual_market_reads"] == result["actual_fits"] == 0
    assert result["cpu_attention_parameters"] == 2353
    assert result["synthetic_feature_shape"] == [6, 63]


@pytest.mark.parametrize("code", ["required_session_missing", "required_price_invalid",
                                  "numeric_range", "required_vintage_mismatch"])
def test_data_failure_is_scoped_and_categorical(worker, monkeypatch, code):
    root, artifact, pin = worker
    def unavailable(*a, **kw):
        raise study.CrossAssetInputUnavailable(code)
    monkeypatch.setattr(study, "prepare_inputs", unavailable)
    result = study.run(root, artifact, artifact, pin)
    assert result["status"] == "input_unavailable" and result["reason"] == code
    assert result["actual_fits"] == result["fit_starts"] == 0
    assert study.verify(root, artifact, artifact, pin, result["result_sha256"])["replay"] \
        == "failure_binding_only"


def test_failure_raw_exception_is_not_persisted_or_output(worker, monkeypatch):
    root, artifact, pin = worker
    def fail(*a, **kw):
        raise ValueError("untrusted private value must not escape")
    monkeypatch.setattr(study, "prepare_inputs", fail)
    result = study.run(root, artifact, artifact, pin)
    assert result["reason"] == "worker_failed" and result["phase"] == "prepare"
    assert b"untrusted" not in (root / "worker-result.json").read_bytes()


def test_progress_counter_binding_is_not_just_file_presence(worker):
    root, artifact, pin = worker
    result = study.run(root, artifact, artifact, pin)
    path = root / "progress-attention-0128.json"
    progress = json.loads(path.read_bytes())
    progress["completed_fits"] = 2
    path.write_bytes(study.encode(progress))
    path = root / "worker-result.json"
    full = json.loads(path.read_bytes())
    full["artifact_sha256"] = study._artifacts(root)
    path.write_bytes(study.encode(full))
    with pytest.raises(study.base.StudyFault, match="progress_binding"):
        study.verify(root, artifact, artifact, pin, study.digest(path.read_bytes()))
    assert result["actual_fits"] == 2


@pytest.fixture
def frozen(tmp_path, monkeypatch, plan):
    source_root = tmp_path / "frozen-source"
    root = tmp_path / "artifacts" / "research" / study.NAME
    root.mkdir(parents=True)
    monkeypatch.setattr(study, "REPO", source_root)
    for name in study.CODE + ("src/producer.py",):
        path = source_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic frozen source")
    commitment = dict(source_pins={"src/producer.py": study.digest(b"synthetic frozen source")},
        calendar_sha256=study.base.CALENDAR_PIN, kind="kis-cross-asset-d1-price-only-input-v1",
        no_date_fill=True)
    original = study.base._json
    def metadata(path, pin=None, **kwargs):
        if path.as_posix().endswith(study.base.INPUT_RELATIVE):
            assert pin == study.base.INPUT_PIN
            return commitment
        return original(path, pin, **kwargs)
    monkeypatch.setattr(study.base, "_json", metadata)
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME))
    monkeypatch.setattr(study, "build_plan", lambda *a: plan)
    pin = study.freeze_contract(root, runtime=dict(study.RUNTIME))
    return root, source_root, commitment, pin


def test_frozen_code_root_and_runtime_roundtrip_without_values(frozen):
    root, source_root, commitment, pin = frozen
    before = (root / "precommit.json").read_bytes()
    contract, actual = study.read_contract(root, root.parent.parent, pin)
    assert actual == commitment and contract["source_root"] == str(source_root)
    assert contract["runtime"]["safetensors"] == "0.8.0"
    assert (root / "precommit.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        study.freeze_contract(root, runtime=dict(study.RUNTIME))


@pytest.mark.parametrize("change", ["root", "code", "runtime", "producer"])
def test_frozen_binding_mismatch_not_rerouted(frozen, monkeypatch, change):
    root, source_root, commitment, pin = frozen
    if change == "code":
        (source_root / study.CODE[0]).write_bytes(b"changed")
        expected = "code_changed"
    elif change == "producer":
        commitment["source_pins"]["src/producer.py"] = study.digest(b"changed")
        expected = "producer_code_pins"
    elif change == "runtime":
        monkeypatch.setattr(study, "runtime_identity", lambda: dict(study.RUNTIME, torch="other"))
        expected = "runtime_identity"
    else:
        path = root / "precommit.json"
        contract = json.loads(path.read_bytes())
        contract["source_root"] = str(source_root.parent)
        path.write_bytes(study.encode(contract))
        pin, expected = study.digest(path.read_bytes()), "frozen_source_root"
    with pytest.raises(study.base.StudyFault, match=expected):
        study.read_contract(root, root.parent.parent, pin)


def test_cli_shape(monkeypatch, capsys):
    monkeypatch.setattr(study, "synthetic_smoke", lambda: {"status": "smoke_passed"})
    assert study.main(["--phase", "smoke"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "smoke_passed"}
    with pytest.raises(SystemExit):
        study.main(["--phase", "run"])
    with pytest.raises(SystemExit):
        study.main(["--phase", "smoke", "--root", "D:/somewhere"])
