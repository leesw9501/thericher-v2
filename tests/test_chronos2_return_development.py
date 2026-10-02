"""Deterministic synthetic study checks; no raw retained data, weights, GPU, or network."""

from __future__ import annotations

import builtins
import copy
import json
import runpy
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest

import test_timesfm_return_development as parent_tests
from thericher_v2.research import chronos2_return_development as s

days = parent_tests.days
rows = parent_tests.rows
parent_isolated = parent_tests.isolated
READ_PARENT = s._parent_result


@pytest.fixture(autouse=True)
def isolated(monkeypatch, parent_isolated):
    monkeypatch.setattr(s, "verify_assets", parent_tests.forbidden)
    monkeypatch.setattr(s, "_parent_result", parent_tests.forbidden)
    monkeypatch.setattr(s.local, "load_chronos2_local", parent_tests.forbidden)
    monkeypatch.setattr(s.local, "_verified_directory", parent_tests.forbidden)
    versions = {**s.local.PINNED_RUNTIME, "timesfm": "2.0.2", "pandas-market-calendars": "5.4.0"}
    monkeypatch.setattr(s.importlib.metadata, "version", versions.__getitem__)
    original_import = builtins.__import__

    def no_backend(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "chronos", "safetensors", "transformers"}:
            raise AssertionError("real model/backend imports are forbidden in synthetic tests")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_backend)


@pytest.fixture
def contract(days, monkeypatch):
    monkeypatch.setattr(s.geometry, "calendar_days", lambda: days)
    return s.proposed_contract()


@pytest.fixture
def prepared(rows, contract):
    return s.parent.prepare(rows, contract["plan"])


@dataclass
class SyntheticModel:
    calls: list = field(default_factory=list)

    def forecast(self, contexts, horizon, *, mode):
        assert horizon == 1
        values = s.local._validated_contexts(contexts, mode)
        self.calls.append((mode, tuple(replace(c, values=v.copy())
                                       for c, v in zip(contexts, values, strict=True))))
        last = np.array([v[-1] for v in values], dtype=np.float64)
        if mode == "same_origin_trio":
            last[:] = last.mean()
        return last[:, None], None


def _runtime(prepared):
    return dict(
        device="synthetic deterministic model; no GPU",
        peak_allocated_bytes=1024,
        memory_budget_bytes=2048,
        point_count=len(s.MODES) * sum(len(g["x"]) for g in prepared),
        training=False,
        predictions_retained=False,
        controls_reproduced=72,
    )


def _score(prepared, contract, model=None):
    forecasts = s.forecast_all(prepared, contract["plan"], model or SyntheticModel())
    return s.score(prepared, forecasts, contract, s.digest(s.encode(contract)), _runtime(prepared))


@pytest.fixture
def result(prepared, contract):
    return _score(prepared, contract)


@pytest.fixture
def reference(rows, days, monkeypatch):
    monkeypatch.setattr(s.geometry, "calendar_days", lambda: days)
    parent_contract = s.parent.proposed_contract()
    prepared = s.parent.prepare(rows, parent_contract["plan"])
    forecasts = s.parent.forecast_all(prepared, "synthetic", predictor=parent_tests.predictor)
    result = s.parent.score(
        prepared, forecasts, parent_contract, s.digest(s.encode(parent_contract)),
        parent_tests.runtime(prepared),
    )
    return parent_contract, result


@pytest.fixture
def frozen(tmp_path, monkeypatch, contract, reference):
    root, market = tmp_path / "artifacts", tmp_path / "synthetic-market"
    checks, registrations, parents = [], [], []
    monkeypatch.setattr(s.base, "verify_metadata", lambda *args: checks.append(args))
    monkeypatch.setattr(s, "verify_assets", lambda _: tmp_path / "unused-synthetic-model")
    monkeypatch.setattr(s.base, "register_frozen_campaign", lambda **kw: registrations.append(kw))

    def parent_result(root):
        parents.append(root)
        return reference[1]

    monkeypatch.setattr(s, "_parent_result", parent_result)
    pin = s.freeze(root, market)
    output, actual = s.verify(root, market, pin)
    assert actual == contract
    return SimpleNamespace(
        root=root, market=market, output=output, pin=pin, contract=actual,
        checks=checks, registrations=registrations, parents=parents,
    )


def test_contract_freezes_nonpromoting_modes_units_budget_and_lineage(contract):
    config = contract["config"]
    assert config["context"] == 128 and config["horizon"] == 1
    assert config["symbols"] == ["SPY", "QQQ", "IWM"]
    assert config["modes"] == ["isolated", "same_origin_trio", "duplicate_self"]
    assert config["costs"] == [5, 10, 20]
    assert config["cells"] == 6 * 3 * 7 == 126
    assert config["budget"] == dict(seconds=900, gpu=True, training=False, passes=1)
    assert all(config[key] is False for key in ("training", "selection", "holdout", "paper_input"))
    assert config["reference"] == {
        "name": s.parent.NAME, "contract": s.PARENT_CONTRACT, "summary": s.PARENT_SUMMARY
    }
    assert "signed return bps" in config["units"]
    assert "no future covariates" in config["grouping"]
    assert "no_untouched_holdout" in config["limitations"]
    assert contract["config_sha256"] == s.digest(s.encode(config))
    assert all(p["target"] > config["checkpoint_date"][:10] for p in contract["plan"])


def test_one_origin_per_call_and_duplicate_self_has_distinct_ids(prepared, contract):
    model = SyntheticModel()
    s.forecast_all(prepared, contract["plan"], model)
    assert len(model.calls) == len(contract["plan"]) * 5
    groups = {(g["symbol"], g["period"]): g for g in prepared}
    for offset, plan in enumerate(contract["plan"]):
        calls = model.calls[offset * 5:offset * 5 + 5]
        assert [mode for mode, _ in calls] == ["isolated"] + ["same_origin_trio"] * 4
        expected_times = tuple(datetime.fromisoformat(d).replace(tzinfo=UTC)
                               for d in plan["history"])
        origin = datetime.fromisoformat(plan["target"]).replace(tzinfo=UTC)
        for _, contexts in calls:
            assert len(contexts) == 3
            assert len({c.series_id for c in contexts}) == 3
            assert {c.forecast_origin for c in contexts} == {origin}
            assert all(c.timestamps == expected_times for c in contexts)
            assert all(c.timestamps[-1] < c.available_at <= origin for c in contexts)
            assert all(c.values.shape == (128,) and np.isfinite(c.values).all() for c in contexts)
            assert all(np.all(c.values == 30) for c in contexts)
        assert [c.series_id for c in calls[0][1]] == list(s.SYMBOLS)
        assert [c.series_id for c in calls[1][1]] == list(s.SYMBOLS)
        for symbol, (_, copies) in zip(s.SYMBOLS, calls[2:], strict=True):
            assert [c.series_id for c in copies] == [f"{symbol}-copy-{i}" for i in range(3)]
            group = groups[(symbol, plan["period"])]
            index = group["dates"].index(plan["target"])
            for c in copies:
                np.testing.assert_array_equal(c.values, group["x"][index])


def test_same_origin_peer_changes_group_not_isolated_or_duplicate_self(rows, contract):
    previous = contract["plan"][0]["history"][-1]
    changed = dict(rows)
    changed["QQQ"] = tuple(
        replace(row, close=Decimal(99)) if row.session_date.isoformat() == previous else row
        for row in rows["QQQ"]
    )
    before, after = (s.parent.prepare(r, contract["plan"]) for r in (rows, changed))
    left = s.forecast_all(before, contract["plan"], SyntheticModel())
    right = s.forecast_all(after, contract["plan"], SyntheticModel())
    for index in (0, 4):
        assert left[index][0]["isolated"][0] == right[index][0]["isolated"][0]
        assert left[index][0]["duplicate_self"][0] == right[index][0]["duplicate_self"][0]
        assert left[index][0]["same_origin_trio"][0] != right[index][0]["same_origin_trio"][0]
    assert left[2][0]["isolated"][0] != right[2][0]["isolated"][0]


def test_current_target_and_all_future_mutations_cannot_change_earlier_forecasts(rows, contract):
    boundary = contract["plan"][5]["target"]
    changed = {
        symbol: tuple(replace(row, close=Decimal(98))
                      if row.session_date.isoformat() >= boundary else row for row in stream)
        for symbol, stream in rows.items()
    }
    before, after = (s.parent.prepare(r, contract["plan"]) for r in (rows, changed))
    left = s.forecast_all(before, contract["plan"], SyntheticModel())
    right = s.forecast_all(after, contract["plan"], SyntheticModel())
    for i in (0, 2, 4):
        np.testing.assert_array_equal(before[i]["x"][:6], after[i]["x"][:6])
        for mode in s.FORECASTS:
            np.testing.assert_array_equal(left[i][0][mode][:6], right[i][0][mode][:6])
        for policy in s.POLICIES:
            np.testing.assert_array_equal(left[i][1][policy][:6], right[i][1][policy][:6])
        assert left[i][0]["isolated"][6] != right[i][0]["isolated"][6]


def test_missing_last_target_censors_outcome_without_changing_forecast_or_action(rows, contract):
    target = contract["plan"][-1]["target"]
    changed = {
        symbol: tuple(row for row in stream if row.session_date.isoformat() != target)
        for symbol, stream in rows.items()
    }
    before, after = (s.parent.prepare(r, contract["plan"]) for r in (rows, changed))
    left = s.forecast_all(before, contract["plan"], SyntheticModel())
    right = s.forecast_all(after, contract["plan"], SyntheticModel())
    for original, modified in zip(left, right, strict=True):
        for a, b in zip(original, modified, strict=True):
            for key in a:
                np.testing.assert_array_equal(a[key], b[key])
    scored = s.score(after, right, contract, s.digest(s.encode(contract)), _runtime(after))
    for group in scored["groups"][1::2]:
        assert group["eligible"] == group["planned"] == 84
        assert group["observed"] == 83 and group["censored"] == 1
    for cell in scored["cells"]:
        if cell["period"] == s.PERIODS[1][0] and cell["policy"] == "always_long":
            assert cell["selected"] == 84 and cell["trades"] == 83
            assert cell["selected_censored"] == 1


def test_inconsistent_past_cohort_is_rejected_before_model_calls(rows, contract):
    missing = contract["plan"][0]["history"][0]
    changed = dict(rows)
    changed["QQQ"] = tuple(r for r in rows["QQQ"] if r.session_date.isoformat() != missing)
    model = SyntheticModel()
    with pytest.raises(ValueError, match="cohort_mismatch"):
        s.forecast_all(s.parent.prepare(changed, contract["plan"]), contract["plan"], model)
    assert not model.calls


@pytest.mark.parametrize("stage", ["isolated", "trio", "duplicate"])
@pytest.mark.parametrize("bad", ["shape", "nan", "inf"])
def test_bad_forecasts_rejected_in_every_mode(prepared, contract, stage, bad):
    class InvalidModel(SyntheticModel):
        def forecast(self, contexts, horizon, *, mode):
            values, _ = super().forecast(contexts, horizon, mode=mode)
            current = ("isolated" if mode == "isolated" else
                       "duplicate" if "-copy-" in contexts[0].series_id else "trio")
            if current == stage:
                values = values.ravel() if bad == "shape" else np.full_like(
                    values, np.nan if bad == "nan" else np.inf
                )
            return values, None

    with pytest.raises(ValueError, match="forecast_shape"):
        s.forecast_all(prepared, contract["plan"], InvalidModel())


def test_strict_threshold_and_fixed_costs_change_accounting_not_actions(prepared, contract):
    class EdgeModel(SyntheticModel):
        def forecast(self, contexts, horizon, *, mode):
            values, _ = super().forecast(contexts, horizon, mode=mode)
            first = datetime(2026, 1, 2, tzinfo=UTC)
            elapsed = (contexts[0].forecast_origin - first).days
            values[:] = [-10, 0, 20, 20.01, 30][elapsed % 5]
            return values, None

    forecasts = s.forecast_all(prepared, contract["plan"], EdgeModel())
    for values, actions in forecasts:
        for mode in s.MODES:
            np.testing.assert_array_equal(actions[mode], values[mode] > 20)
            assert not actions[mode][values[mode] == 20].any()
            assert (values[mode] < 0).any()
    result = s.score(
        prepared, forecasts, contract, s.digest(s.encode(contract)), _runtime(prepared)
    )
    assert len(result["groups"]) == 6 and len(result["cells"]) == 126
    for cell in result["cells"]:
        assert Decimal(cell["gross_sum_bps"]) == Decimal(30) * cell["trades"]
        assert Decimal(cell["net_sum_bps"]) == (Decimal(30) - cell["cost"]) * cell["trades"]
        peers = [c for c in result["cells"]
                 if all(c[k] == cell[k] for k in ("symbol", "period", "policy"))]
        assert len(peers) == 3
        for key in ("action_sha256", "selected", "trades", "gross_sum_bps"):
            assert len({c[key] for c in peers}) == 1
        if cell["policy"] == "cash":
            assert cell["selected"] == cell["trades"] == 0


def test_forecasts_actions_and_published_evidence_are_immutable(tmp_path, prepared, contract):
    original = s.encode(contract)
    model = SyntheticModel()
    frozen = s.forecast_all(prepared, contract["plan"], model)
    for forecasts, actions in frozen:
        for value in (*forecasts.values(), *actions.values()):
            assert not value.flags.writeable
            with pytest.raises(ValueError):
                value[0] = 1000
    result = s.score(prepared, frozen, contract, s.digest(original), _runtime(prepared))
    assert s.encode(contract) == original
    path = tmp_path / "summary.json"
    s.atomic_new(path, result)
    raw = path.read_bytes()
    with pytest.raises(FileExistsError):
        s.atomic_new(path, {"replace": True})
    assert path.read_bytes() == raw == s.encode(result)
    for raw_field in ("open", "close", "dates", "targets", "predictions", "x", "index", "weights"):
        assert f'"{raw_field}"' not in raw.decode()


def test_all_72_parent_controls_and_cpu_metrics_reproduce_exactly(result, reference):
    s.reattest_controls(result, reference[1])
    controls = [c for c in result["cells"] if c["policy"] not in s.MODES]
    old_controls = [c for c in reference[1]["cells"] if c["policy"] != "timesfm"]
    assert len(controls) == len(old_controls) == 72
    assert controls == old_controls
    assert result["runtime"]["controls_reproduced"] == 72
    assert result["groups"][0]["metrics"]["isolated"] != reference[1]["groups"][0]["metrics"][
        "timesfm"
    ]


@pytest.mark.parametrize("mutation", [
    "cohort", "count", "mean", "previous", "zero", "cell", "order",
])
def test_parent_control_or_cohort_drift_is_rejected(result, reference, mutation):
    old = copy.deepcopy(reference[1])
    if mutation == "cohort":
        old["groups"][0]["cohort_sha256"] = parent_tests.OTHER
    elif mutation == "count":
        old["groups"][0]["observed"] -= 1
    elif mutation in {"mean", "previous", "zero"}:
        key = {"mean": "rolling_mean", "previous": "previous_return", "zero": "zero"}[mutation]
        old["groups"][0]["metrics"][key]["mse_bps2"] = "9999"
    elif mutation == "cell":
        old["cells"][1]["gross_sum_bps"] = "9999"
    else:
        old["cells"].reverse()
    with pytest.raises(ValueError, match="parent_(cohort|metrics|controls)_changed"):
        s.reattest_controls(result, old)


@pytest.mark.parametrize("mutation", [
    "extra", "group_order", "count_bool", "metric_nan", "cell_order", "cost",
    "cost_action", "cash", "runtime_count", "controls71", "training", "predictions",
])
def test_result_validator_rejects_corrupted_accounting_binding_and_runtime(
    result, contract, mutation,
):
    if mutation == "extra":
        result["raw_predictions"] = [1]
    elif mutation == "group_order":
        result["groups"].reverse()
    elif mutation == "count_bool":
        result["groups"][0]["censored"] = False
    elif mutation == "metric_nan":
        result["groups"][0]["metrics"]["isolated"]["mse_bps2"] = "NaN"
    elif mutation == "cell_order":
        result["cells"].reverse()
    elif mutation == "cost":
        result["cells"][0]["net_sum_bps"] = "9999"
    elif mutation == "cost_action":
        result["cells"][7]["action_sha256"] = parent_tests.OTHER
    elif mutation == "cash":
        result["cells"][6]["selected"] = 1
    elif mutation == "runtime_count":
        result["runtime"]["point_count"] += 1
    elif mutation == "controls71":
        result["runtime"]["controls_reproduced"] = 71
    elif mutation == "training":
        result["runtime"]["training"] = True
    else:
        result["runtime"]["predictions_retained"] = True
    with pytest.raises(ValueError):
        s.validate_result(result, contract, s.digest(s.encode(contract)))


@pytest.mark.parametrize("field", ["name", "config", "source", "runtime"])
def test_header_rejects_changed_fields_even_with_a_new_hash(contract, field):
    altered = copy.deepcopy(contract)
    if field == "name":
        altered[field] = "other-study"
    elif field == "config":
        altered[field]["horizon"] = 2
    elif field == "source":
        altered[field]["dataset_sha256"] = parent_tests.OTHER
    else:
        altered[field]["chronos-forecasting"] = "unfrozen"
    with pytest.raises(ValueError):
        s.header(altered, s.digest(s.encode(altered)))


def test_targets_on_checkpoint_date_are_not_eligible(days, monkeypatch):
    monkeypatch.setattr(s.geometry, "calendar_days", lambda: days)
    monkeypatch.setattr(s.local, "CHRONOS2_CHECKPOINT_DATE", "2026-01-02T00:00:00Z")
    with pytest.raises(ValueError, match="checkpoint_overlap"):
        s.proposed_contract()


def test_freeze_is_single_use_and_verify_detects_exact_byte_mutation(frozen):
    assert len(frozen.registrations) == 1
    assert frozen.registrations[0]["holdout_access"] == "none"
    assert frozen.registrations[0]["trial_family"] == s.NAME
    assert frozen.registrations[0]["split_hash"] == s.digest(s.encode(frozen.contract["plan"]))
    assert len(frozen.checks) == len(frozen.parents) == 2
    path = frozen.output / "precommit.json"
    raw = path.read_bytes()
    with pytest.raises(FileExistsError):
        s.freeze(frozen.root, frozen.market)
    assert path.read_bytes() == raw
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="precommit_changed"):
        s.verify(frozen.root, frozen.market, frozen.pin)


@pytest.mark.parametrize("mutation", ["none", "contract", "summary", "failed"])
def test_parent_receipt_requires_exact_pins_and_valid_complete_result(tmp_path, monkeypatch,
                                                                    reference, mutation):
    contract, result = copy.deepcopy(reference)
    if mutation == "failed":
        result = s.parent.failure(contract, s.digest(s.encode(contract)), "worker_failed")
    root = tmp_path / "artifacts"
    directory = root / "research" / s.parent.NAME
    directory.mkdir(parents=True)
    s.atomic_new(directory / "precommit.json", contract)
    s.atomic_new(directory / "summary.json", result)
    monkeypatch.setattr(s, "PARENT_CONTRACT", s.digest(s.encode(contract)))
    monkeypatch.setattr(s, "PARENT_SUMMARY", s.digest(s.encode(result)))
    if mutation in {"contract", "summary"}:
        path = directory / ("precommit.json" if mutation == "contract" else "summary.json")
        path.write_bytes(path.read_bytes() + b" ")
    if mutation == "none":
        assert READ_PARENT(root) == result
    else:
        with pytest.raises(ValueError, match="parent_(contract|summary|incomplete)"):
            READ_PARENT(root)


@pytest.mark.parametrize("kind", ["absent", "wrong_pin", "extra", "wrong_path", "existing_output"])
def test_worker_rejects_wrong_attempt_or_output_before_data_or_backend(frozen, kind):
    path = frozen.output / "worker-result.json"
    if kind != "absent":
        attempt = {"contract_sha256": parent_tests.OTHER if kind == "wrong_pin" else frozen.pin}
        if kind == "extra":
            attempt["extra"] = True
        s.atomic_new(frozen.output / "started.json", attempt)
    if kind == "wrong_path":
        path = frozen.root / "other.json"
    elif kind == "existing_output":
        s.atomic_new(path, {"existing": True})
    with pytest.raises((ValueError, FileNotFoundError)):
        s.run_worker(frozen.root, frozen.market, frozen.pin, path, time.monotonic() + 1)
    if kind == "existing_output":
        assert json.loads(path.read_bytes()) == {"existing": True}
    else:
        assert not path.exists()


def test_worker_data_failure_publishes_only_categorical_immutable_failure(frozen, monkeypatch):
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})

    def failed_data(*args, **kwargs):
        raise RuntimeError("synthetic sensitive provider detail")

    monkeypatch.setattr(s.base, "load_verified_tiingo_etf_d1_snapshot", failed_data)
    path = frozen.output / "worker-result.json"
    s.run_worker(frozen.root, frozen.market, frozen.pin, path, time.monotonic() + 1)
    raw = path.read_bytes()
    assert json.loads(raw) == s.failure(frozen.contract, frozen.pin, "runtime_or_invariant_failure")
    assert b"sensitive" not in raw
    with pytest.raises(ValueError, match="worker_path"):
        s.run_worker(frozen.root, frozen.market, frozen.pin, path, time.monotonic() + 1)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("mode", ["complete", "timeout", "raise", "interrupt"])
def test_runner_holds_mocked_gpu_owner_and_publishes_once(frozen, prepared, monkeypatch,
                                                         capsys, mode):
    launcher = runpy.run_path(str(s.REPO / "scripts/run_chronos2_return_development.py"))
    events, outcomes = [], []
    result = _score(prepared, frozen.contract)

    @contextmanager
    def fake_lock(path):
        assert path == frozen.root / "synthetic-owner" / "locks/gpu.lock"
        events.append("acquire")
        try:
            yield
        finally:
            events.append("release")

    def supervise(target, arguments, *, seconds):
        assert events == ["acquire"]
        assert target is s.worker_entry and 0 < seconds <= 900
        assert arguments[:3] == (frozen.root, frozen.market, frozen.pin)
        assert arguments[3] == frozen.output / "worker-result.json"
        events.append(mode)
        if mode == "raise":
            raise RuntimeError("synthetic private exception body")
        if mode == "interrupt":
            raise KeyboardInterrupt
        if mode == "complete":
            s.atomic_new(arguments[3], result)
        return dict(timed_out=mode == "timeout", exit_code=None if mode == "timeout" else 0)

    def configured_parent(path):
        assert path == str(s.REPO / "scripts/run_tiingo_month_start_development.py")
        runner = runpy.run_path(path)
        namespace = runner["main"].__globals__
        monkeypatch.setitem(namespace, "supervise", supervise)
        monkeypatch.setitem(
            namespace, "register_campaign_outcome", lambda **kw: outcomes.append(kw)
        )
        monkeypatch.setitem(namespace, "os", SimpleNamespace(environ={}))
        return runner

    entry = launcher["main"]
    monkeypatch.setitem(entry.__globals__, "runpy", SimpleNamespace(run_path=configured_parent))
    monkeypatch.setitem(entry.__globals__, "GpuFileLock", fake_lock)
    monkeypatch.setitem(entry.__globals__, "resolve_agent_root",
                        lambda _: frozen.root / "synthetic-owner")
    argv = ["--run", "--contract-sha256", frozen.pin, "--artifact-root", str(frozen.root),
            "--market-data-root", str(frozen.market)]
    assert entry(argv) == (0 if mode == "complete" else 1)
    assert events == ["acquire", mode, "release"]
    raw = (frozen.output / "summary.json").read_bytes()
    summary = json.loads(raw)
    criterion = {"complete": "descriptive_only_no_selection", "timeout": "hard_timeout",
                 "raise": "worker_result_invalid", "interrupt": "execution_preempted"}[mode]
    assert summary["criterion"] == criterion
    s.validate_result(summary, frozen.contract, frozen.pin)
    assert len(outcomes) == 1
    assert outcomes[0]["contract_hash"] == frozen.pin
    assert outcomes[0]["outcome_reference_sha256"] == s.digest(raw)
    assert outcomes[0]["outcome_class"] == (
        "non_promoting_completed" if mode == "complete" else "non_promoting_failed"
    )
    assert "private exception" not in capsys.readouterr().out
    assert entry(argv) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "dispatch_unavailable"
    assert (frozen.output / "summary.json").read_bytes() == raw
    assert events == ["acquire", mode, "release", "acquire", "release"]
    assert len(outcomes) == 1
