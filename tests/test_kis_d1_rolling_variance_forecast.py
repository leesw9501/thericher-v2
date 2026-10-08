"""Source-free rolling membership, maturity, completion custody and cached replay."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import kis_d1_rolling_variance_forecast as study


@pytest.fixture(autouse=True)
def no_actual_dispatch(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("actual source/runtime/fit call outside synthetic stub")

    monkeypatch.setattr(study.base, "load_committed_source", forbidden)
    monkeypatch.setattr(study.base, "calendar_sessions", forbidden)
    monkeypatch.setattr(study.fixed, "fit_ols", forbidden)
    monkeypatch.setattr(study.fixed, "fit_gru", forbidden)
    monkeypatch.setattr(study.fixed, "runtime_identity", forbidden)


@pytest.fixture(scope="module")
def plan():
    return study.build_plan(study._synthetic_sessions())


@pytest.fixture(scope="module")
def rows(plan):
    return {
        symbol: tuple(
            study.base.PriceClose(
                symbol,
                session.session_date,
                "synthetic",
                Decimal(100 + session.session_date.toordinal() % (17 + asset)),
            )
            for session in plan.sessions
        )
        for asset, symbol in enumerate(study.base.INSTRUMENT_ORDER)
    }


@pytest.fixture(scope="module")
def prepared(plan):
    raw = np.random.default_rng(101).normal(0, 0.01, (505, 3, 63))
    return study.fixed.prepare_arrays(raw, np.full((504, 3), 0.0001), plan.month(0))


def test_fixed_parent_interface_recipe_and_lineage():
    config = study.configuration()
    assert config["fits"] == 66 and config["cells"] == 6 and config["seconds"] == 300
    assert config["verify_seconds"] == 120 and config["geometry"]["required_dates"] == 1278
    assert config["gru"]["updates"] == 512 and config["gru"]["parameters"] == 3651
    assert config["related_trial_number"] == 2 and "not forced" in config["registry_trial_index"]
    assert config["predecessor"]["contract_sha256"].startswith("sha256:b198df9d")
    assert config["geometry_receipt"]["sha256"] == study.GEOMETRY_PIN
    assert (
        "j+20<=d-2" in config["training"] and "no prediction floor/clipping" in config["forecast"]
    )
    assert "Torch" not in config["accounting"] and config["paper_input"] is False
    assert len(study.ARTIFACTS) == 398 and len(set(study.ARTIFACTS)) == 398


def test_all_33_windows_strict_maturity_and_latest_membership(plan):
    assert len(plan.dev_indices) == 33 and plan.block_cut == 12
    for m, d in enumerate(plan.dev_indices):
        window = plan.train_windows[m]
        assert window == tuple(range(d - 525, d - 21)) and len(window) == 504
        assert window[-1] + 20 == d - 2
        assert plan.sessions[window[-1] + 20].close_at < plan.sessions[d - 1].close_at
        assert d - 21 not in window  # This excluded entry exits exactly at decision CLOSE.
        assert plan.month(m).dev_indices == (d,)
        assert plan.record()["monthly_windows"][m]["train_count"] == 504
    assert "sessions=" not in repr(plan) and "train_windows=" not in repr(plan)


@pytest.mark.parametrize("month", [-1, 33, True, 1.5])
def test_invalid_month_rejected(plan, month):
    with pytest.raises(study.base.StudyFault, match="month_scope"):
        plan.month(month)


def test_bad_calendar_and_forged_window_rejected(plan, rows):
    with pytest.raises(study.base.StudyFault, match="calendar_order"):
        study.build_plan(tuple(reversed(plan.sessions)))
    forged = replace(
        plan,
        train_windows=(plan.train_windows[0][1:] + (plan.train_windows[0][-1] + 1,),)
        + plan.train_windows[1:],
    )
    with pytest.raises(study.base.StudyFault, match="plan_changed"):
        study.prepare_month(rows, forged, 0, vintage_ref="synthetic")


@pytest.mark.parametrize("mutation", ["changed", "absent", "unread"])
def test_all_future_values_and_support_leave_month_exact(plan, rows, mutation):
    before = study.prepare_month(rows, plan, 0, vintage_ref="synthetic")
    cutoff = plan.sessions[plan.dev_indices[0] - 1].session_date

    class Unread:
        def __init__(self, day):
            self.session_date = day

        @property
        def close(self):
            pytest.fail("future values inspected")

    changed = {
        s: tuple(
            r
            if r.session_date <= cutoff
            else replace(r, close=Decimal(999999))
            if mutation == "changed"
            else Unread(r.session_date)
            for r in values
            if mutation != "absent" or r.session_date <= cutoff
        )
        for s, values in rows.items()
    }
    after = study.prepare_month(changed, plan, 0, vintage_ref="synthetic")
    assert before.scaler == after.scaler
    for name in ("train_x", "train_har", "labels", "dev_x", "dev_har", "baseline"):
        np.testing.assert_array_equal(getattr(before, name), getattr(after, name))


def test_decision_close_is_feature_only_not_training_label(plan, rows):
    before = study.prepare_month(rows, plan, 0, vintage_ref="synthetic")
    day = plan.sessions[plan.dev_indices[0] - 1].session_date
    changed = {
        s: tuple(replace(r, close=r.close * 2) if r.session_date == day else r for r in values)
        for s, values in rows.items()
    }
    after = study.prepare_month(changed, plan, 0, vintage_ref="synthetic")
    for name in ("train_x", "train_har", "labels"):
        np.testing.assert_array_equal(getattr(before, name), getattr(after, name))
    for key in ("mean", "divisor", "har_mean", "har_divisor", "target_log_mean", "labels_sha256"):
        assert before.scaler[key] == after.scaler[key]
    assert not np.array_equal(before.dev_x, after.dev_x)


@pytest.mark.parametrize("symbol", study.base.INSTRUMENT_ORDER)
@pytest.mark.parametrize("scope", ["feature", "label", "decision"])
def test_required_gap_never_substituted(plan, rows, symbol, scope):
    month = plan.month(0)
    i = {
        "feature": month.train_indices[0] - 64,
        "label": month.train_indices[-1] + 20,
        "decision": month.dev_indices[0] - 1,
    }[scope]
    day = plan.sessions[i].session_date
    changed = dict(rows)
    changed[symbol] = tuple(r for r in rows[symbol] if r.session_date != day)
    with pytest.raises(study.base.StudyFault, match="required_session_missing"):
        study.prepare_month(changed, plan, 0, vintage_ref="synthetic")


def test_scalers_use_only_504_training_rows(plan, prepared):
    raw = np.random.default_rng(101).normal(0, 0.01, (505, 3, 63))
    raw[-1] *= 1000
    after = study.fixed.prepare_arrays(raw, np.full((504, 3), 0.0001), plan.month(0))
    for key in ("mean", "divisor", "har_mean", "har_divisor", "target_log_mean"):
        assert after.scaler[key] == prepared.scaler[key]
    assert prepared.train_x.shape == (504, 3, 63) and prepared.dev_x.shape == (1, 3, 63)
    assert not prepared.train_x.flags.writeable and not prepared.labels.flags.writeable


def test_memo_only_reuses_mature_values_and_revalidates_support(monkeypatch, plan, rows):
    calls, selections = [], []
    original = study.fixed.forward_target

    def target(selected, local, index, vintage):
        assert index + 20 <= local.dev_indices[0] - 2
        calls.append(index)
        return original(selected, local, index, vintage)

    def selected(source, dates):
        selections.append(dates)
        return rows

    monkeypatch.setattr(study.fixed, "load_closes", selected)
    monkeypatch.setattr(study.fixed, "forward_target", target)
    monkeypatch.setattr(study.base, "INPUT_PIN", "synthetic")
    cache = study.PreparationCache(object(), plan)
    first = cache.prepare(0, deadline=float("inf"))
    second = cache.prepare(1, deadline=float("inf"))
    assert len(calls) == len(set(plan.train_windows[0]) | set(plan.train_windows[1]))
    assert len(selections) == 2
    np.testing.assert_array_equal(
        first.train_x, study.prepare_month(rows, plan, 0, vintage_ref="synthetic").train_x
    )
    assert second.scaler["train_count"] == 504
    assert all(not values.flags.writeable for values in cache._features.values())


def fake_parts(plan, pin="synthetic"):
    return [
        dict(
            contract_sha256=pin,
            input_sha256=study.base.INPUT_PIN,
            window=plan.window_record(m),
            log_forecasts=dict(ols=[[math.log(0.0001)] * 3], gru=[[math.log(0.0001)] * 3]),
            baseline=[[0.0001] * 3],
            inference_kind="original_worker",
        )
        for m in range(33)
    ]


def test_exact_six_cells_and_unchanged_kill(plan):
    predictions = study.assemble_predictions(plan, fake_parts(plan), "synthetic")
    cells = study.evaluate(np.full((33, 3), 0.0001), predictions, plan, completed_fits=66)
    assert {(c["block"], c["method"]) for c in cells} == {
        (b, m) for b in (0, 1) for m in study.METHODS
    }
    assert {c["decision_count"] for c in cells} == {12, 21}
    assert all(set(c["asset_metrics"]) == set(study.base.INSTRUMENT_ORDER) for c in cells)
    assert study.criterion(cells) == {"ols": "rejected", "gru": "rejected"}


@pytest.mark.parametrize("count", [0, 2, 65, True])
def test_partial_fit_count_never_reaches_metrics(monkeypatch, plan, count):
    monkeypatch.setattr(study.fixed, "evaluate", lambda *a: pytest.fail("partial scoring"))
    with pytest.raises(study.base.StudyFault, match="incomplete_fits"):
        study.evaluate(None, {}, plan, completed_fits=count)


@pytest.mark.parametrize("mutation", ["missing", "reordered", "wrong_window"])
def test_prediction_seal_all_months_exact(plan, mutation):
    parts = fake_parts(plan)
    if mutation == "missing":
        parts.pop()
    elif mutation == "reordered":
        parts.reverse()
    else:
        parts[0]["window"]["train_last"] = "2099-01-01"
    with pytest.raises(study.base.StudyFault, match="incomplete_months|prediction_binding"):
        study.assemble_predictions(plan, parts, "synthetic")


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
    state = dict(month=0, forward_reads=0)

    def ols(p, *, deadline, progress):
        progress()
        return [[math.log(0.0001)] * 3], b"synthetic-ols", dict(seconds=0)

    def gru(p, *, deadline, progress):
        for update in (128, 256, 384, 512):
            progress(update)
        state["month"] += 1
        return [[math.log(0.0001)] * 3], b"synthetic-gru", dict(seconds=0)

    def forward(*args, **kwargs):
        assert state["month"] == 33 and (root / "predictions.json").exists()
        assert all((root / f"months/{m:02d}/predictions.json").exists() for m in range(33))
        state["forward_reads"] += 1
        return np.full((33, 3), 0.0001)

    monkeypatch.setattr(study.fixed, "fit_ols", ols)
    monkeypatch.setattr(study.fixed, "fit_gru", gru)
    monkeypatch.setattr(study.fixed, "load_dev_targets", forward)
    return SimpleNamespace(
        root=root, market=tmp_path / "M", artifact=artifact, pin=pin, state=state
    )


def invoke_run(fixture):
    return study.run(fixture.root, fixture.market, fixture.artifact, fixture.pin)


def invoke_verify(fixture, result):
    return study.verify(
        fixture.root, fixture.market, fixture.artifact, fixture.pin, result["result_sha256"]
    )


def bytes_snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_complete_66fit_counts_and_zero_fit_zero_write_replay(monkeypatch, mock_run):
    result = invoke_run(mock_run)
    assert result["status"] == "complete" and result["actual_fits"] == result["fit_starts"] == 66
    assert result["cells"] == 6 and mock_run.state["forward_reads"] == 1
    before = bytes_snapshot(mock_run.root)
    monkeypatch.setattr(study.fixed, "fit_ols", lambda *a, **k: pytest.fail("replay fit"))
    monkeypatch.setattr(study.fixed, "fit_gru", lambda *a, **k: pytest.fail("replay fit"))
    monkeypatch.setattr(study.base, "atomic_new", lambda *a, **k: pytest.fail("replay write"))
    replay = invoke_verify(mock_run, result)
    assert replay["replay"] == "exact_metrics/cached_prediction_binding"
    assert replay["fits"] == replay["inference"] == replay["writes"] == replay["searches"] == 0
    assert replay["actual_fits"] == 66 and before == bytes_snapshot(mock_run.root)


@pytest.mark.parametrize("method", ["ols", "gru"])
@pytest.mark.parametrize("fault", ["prediction", "serialization", "deadline"])
def test_posttraining_fault_records_completion_before_fault(monkeypatch, mock_run, method, fault):
    def bad(p, *, deadline, progress):
        if method == "ols":
            progress()
        else:
            for update in (128, 256, 384, 512):
                progress(update)
        raise study.base.StudyFault("compute_stop" if fault == "deadline" else "forecast_numeric")

    monkeypatch.setattr(study.fixed, "fit_" + method, bad)
    monkeypatch.setattr(
        study.fixed, "load_dev_targets", lambda *a, **k: pytest.fail("partial scoring")
    )
    result = invoke_run(mock_run)
    assert result["status"] == "failed" and result["cells"] == 0
    assert result["actual_fits"] == result["fit_starts"] == (1 if method == "ols" else 2)
    assert (mock_run.root / f"months/00/progress-{method}-complete.json").exists()
    replay = invoke_verify(mock_run, result)
    assert replay["replay"] == "failure_binding_only" and replay["fits"] == 0


def test_failure_after_completed_middle_month_never_scores(monkeypatch, mock_run):
    original = study.fixed.fit_gru

    def fail_after(p, **kwargs):
        result = original(p, **kwargs)
        if mock_run.state["month"] == 17:
            raise study.base.StudyFault("compute_stop")
        return result

    monkeypatch.setattr(study.fixed, "fit_gru", fail_after)
    result = invoke_run(mock_run)
    assert result["status"] == "failed" and result["actual_fits"] == 34 and result["cells"] == 0
    assert mock_run.state["forward_reads"] == 0
    assert invoke_verify(mock_run, result)["replay"] == "failure_binding_only"


def test_missing_required_source_is_scoped_unavailable(monkeypatch, mock_run):
    def gap(*args, **kwargs):
        raise study.base.StudyFault("required_date_gap")

    monkeypatch.setattr(study.PreparationCache, "prepare", gap)
    result = invoke_run(mock_run)
    assert result["status"] == "input_unavailable" and result["actual_fits"] == 0
    assert result["reason"] == "required_date_gap" and result["cells"] == 0
    assert invoke_verify(mock_run, result)["replay"] == "failure_binding_only"


@pytest.mark.parametrize(
    "artifact",
    [
        "months/00/scaler.json",
        "months/32/gru.safetensors",
        "months/16/predictions.json",
        "predictions.json",
        "months/08/progress-gru-0512.json",
    ],
)
def test_readback_rejects_mutated_artifact(mock_run, artifact):
    result = invoke_run(mock_run)
    path = mock_run.root / artifact
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(study.base.StudyFault, match="artifact_binding"):
        invoke_verify(mock_run, result)


def test_readback_rejects_rehashed_wrong_prediction(mock_run):
    result = invoke_run(mock_run)
    name = "months/00/predictions.json"
    path = mock_run.root / name
    part = json.loads(path.read_bytes())
    part["scaler_sha256"] = "sha256:" + "a" * 64
    path.write_bytes(study.encode(part))
    result_path = mock_run.root / "worker-result.json"
    raw = json.loads(result_path.read_bytes())
    raw["artifact_sha256"][name] = study.digest(path.read_bytes())
    result_path.write_bytes(study.encode(raw))
    result["result_sha256"] = study.digest(result_path.read_bytes())
    with pytest.raises(study.base.StudyFault, match="prediction_binding"):
        invoke_verify(mock_run, result)


def test_missing_or_wrong_geometry_pin_prevents_source_read(monkeypatch, tmp_path):
    monkeypatch.setattr(study, "GEOMETRY_PIN", None)
    with pytest.raises(study.base.StudyFault, match="geometry_not_ready"):
        study.read_contract(tmp_path, tmp_path, "ignored")


def synthetic_geometry(plan):
    needed, windows = set(), []
    for month in range(33):
        local, record = plan.month(month), plan.window_record(month)
        windows.append(
            dict(
                entry_date=record["entry"],
                decision_close_at_utc=record["decision_at"],
                first_train_entry_date=record["train_first"],
                last_train_entry_date=record["train_last"],
                train_entry_count=504,
                latest_train_target_close_date=local.sessions[
                    local.train_indices[-1] + 20
                ].session_date.isoformat(),
                train_required_close_support=dict(first_date=record["first_required_close"]),
                required_missing_date_counts_by_symbol={
                    scope: {s: 0 for s in study.base.INSTRUMENT_ORDER}
                    for scope in (
                        "rolling_train_required",
                        "prediction_features",
                        "forward_scoring_targets",
                    )
                },
            )
        )
        needed.update(study.fixed.required_dates(local, local.train_indices + local.dev_indices))
        needed.update(
            study.fixed.required_dates(local, local.train_indices + local.dev_indices, forward=True)
        )
    return dict(
        goal=study.NAME,
        kind="kis_d1_rolling_variance_geometry_v1",
        source_bindings={
            key: dict(sha256_before=pin[7:], sha256_after=pin[7:])
            for key, pin in (
                ("input_commitment", study.base.INPUT_PIN),
                ("calendar", study.base.CALENDAR_PIN),
            )
        },
        contract=dict(
            canonical_symbols=list(study.base.INSTRUMENT_ORDER),
            maturity_predicate="j+20<=d-2",
            training_entry_count_per_decision=504,
            monthly_entry_count=33,
            view_entry_counts=[12, 21],
        ),
        windows=windows,
        aggregate=dict(
            all_required_close_support=dict(
                first_date=min(needed).isoformat(),
                last_date=max(needed).isoformat(),
                session_count=len(needed),
            )
        ),
    )


def test_geometry_exact_windows_and_z_clock_equivalence(plan):
    geometry = synthetic_geometry(plan)
    geometry["windows"][0]["decision_close_at_utc"] = geometry["windows"][0][
        "decision_close_at_utc"
    ].replace("+00:00", "Z")
    study.validate_geometry(geometry, plan)


@pytest.mark.parametrize(
    "mutation", ["lag", "calendar", "first", "last", "missing", "clock", "count"]
)
def test_geometry_mismatch_rejected(plan, mutation):
    geometry = synthetic_geometry(plan)
    row = geometry["windows"][7]
    if mutation == "lag":
        geometry["contract"]["maturity_predicate"] = "j+20<=d-1"
    elif mutation == "calendar":
        geometry["source_bindings"]["calendar"]["sha256_after"] = "0" * 64
    elif mutation in ("first", "last"):
        row[mutation + "_train_entry_date"] = "2099-01-01"
    elif mutation == "missing":
        row["required_missing_date_counts_by_symbol"]["rolling_train_required"]["TLT"] = 1
    elif mutation == "clock":
        row["decision_close_at_utc"] = row["decision_close_at_utc"].replace("21:00", "22:00")
    else:
        geometry["aggregate"]["all_required_close_support"]["session_count"] -= 1
    with pytest.raises(study.base.StudyFault, match="geometry_binding"):
        study.validate_geometry(geometry, plan)


def test_current_source_contract_binding_before_any_numeric_loader(monkeypatch, tmp_path, plan):
    artifact = tmp_path / "A"
    root = artifact / "research" / study.NAME
    root.mkdir(parents=True)
    code_root = tmp_path / "code"
    pins = {}
    for name in study.CODE:
        path = code_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic source")
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
    geometry = synthetic_geometry(plan)

    def json_read(path, pin=None, **kwargs):
        return (
            contract
            if path.name == "precommit.json"
            else geometry
            if str(path).endswith(study.GEOMETRY_RELATIVE.replace("/", "\\"))
            or path.name == "geometry-20261008-v1.json"
            else commitment
        )

    monkeypatch.setattr(study, "REPO", code_root)
    monkeypatch.setattr(study.base, "_json", json_read)
    monkeypatch.setattr(study.fixed, "runtime_identity", lambda: study.RUNTIME)
    monkeypatch.setattr(study, "build_plan", lambda *a: plan)
    assert study.read_contract(root, artifact, "synthetic")[0] == contract
    next(iter(code_root.rglob("*.py"))).write_bytes(b"changed")
    with pytest.raises(study.base.StudyFault, match="code_changed"):
        study.read_contract(root, artifact, "synthetic")


def test_cli_smoke_interface_has_no_bound_roots(monkeypatch, capsys):
    monkeypatch.setattr(
        study, "synthetic_smoke", lambda: dict(status="smoke_passed", actual_fits=0)
    )
    assert study.main(["--phase", "smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["actual_fits"] == 0
    with pytest.raises(SystemExit):
        study.main(["--phase", "verify"])


def test_source_free_cpu_smoke_without_optimizer_or_cuda(monkeypatch):
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: pytest.fail("GPU probe"))
    monkeypatch.setattr(torch.optim.AdamW, "step", lambda *a: pytest.fail("optimizer step"))
    result = study.synthetic_smoke()
    assert result["status"] == "smoke_passed" and result["cells"] == 6
    assert result["actual_market_reads"] == result["actual_fits"] == result["optimizer_steps"] == 0
    assert (
        result["cpu_gru_parameters"] == 3651
        and len(result["synthetic_cpu_forward_backward_seconds"]) == 3
    )
