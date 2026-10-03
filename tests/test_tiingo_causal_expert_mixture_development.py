"""Synthetic causal feedback, continuous accounting, custody and console tests."""

import copy
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import time
from datetime import date, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.data.tiingo_adjusted_etf_daily import AdjustedEtfRow
from thericher_v2.research import tiingo_causal_expert_mixture_development as s

SCRIPT = s.REPO / "scripts/run_tiingo_causal_expert_mixture_development.py"
spec = importlib.util.spec_from_file_location("causal_mixture_launcher", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("actual market data/network forbidden")

    monkeypatch.setattr(s.fitted, "load_adjusted", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with localcontext() as context:
        context.prec = 50
        yield


@pytest.fixture(scope="module")
def sample():
    days, day = [], date(2000, 12, 1)
    while day <= date(2026, 8, 3):
        following = day + timedelta(days=1)
        while following.weekday() >= 5:
            following += timedelta(days=1)
        if day.weekday() < 5 and (day.year <= 2001 or day.day <= 3 or following.month != day.month):
            days.append(day.isoformat())
        day += timedelta(days=1)
    clocks = {d: (d + "T14:30:00+00:00", d + "T21:00:00+00:00") for d in days}
    plan = s.build_plan(days, clocks)
    rows = {}
    for symbol in s.SYMBOLS:
        stream, previous = [], Decimal(100)
        for i, d in enumerate(days):
            opening = previous + Decimal(i % 3 - 1) / 10
            closing = Decimal(100) + Decimal(i) / 100 + Decimal(i % 11 - 5) / 10
            stream.append(
                AdjustedEtfRow(
                    symbol,
                    date.fromisoformat(d),
                    opening,
                    max(opening, closing) + 1,
                    min(opening, closing) - 1,
                    closing,
                )
            )
            previous = closing
        rows[symbol] = tuple(stream)
    prepared = s.fitted.prepare(rows, plan)
    predictions = {
        (a, symbol, p["period"]): np.full(len(p["months"]), weight)
        for a, weight in zip(s.fitted.ARCHITECTURES, (0.4, 0.6), strict=True)
        for symbol in s.SYMBOLS
        for p in plan["periods"]
    }
    return SimpleNamespace(
        days=days,
        clocks=clocks,
        plan=plan,
        rows=rows,
        prepared=prepared,
        predictions=predictions,
        risks=dict.fromkeys(s.SYMBOLS, Decimal(".3")),
    )


@pytest.fixture
def contract(sample, monkeypatch):
    monkeypatch.setattr(s, "calendar", lambda: (sample.days, sample.clocks))
    return s.proposed_contract()


@pytest.fixture(scope="module")
def evaluated(sample):
    return s.evaluate(
        sample.prepared,
        sample.plan,
        sample.predictions,
        sample.risks,
        deadline=time.monotonic() + 60,
    )


def runtime(contract):
    free, total = 22 * 1024**3, 24 * 1024**3
    return dict(
        device="synthetic",
        torch=contract["runtime"]["torch"],
        cuda="12.8",
        torch_threads=2,
        free_before_bytes=free,
        total_bytes=total,
        memory_budget_bytes=min(int(total * 0.9), free - 1024**3),
        peak_allocated_bytes=123,
        training_device="cuda:0",
        inference_device="cpu",
    )


def complete(contract, evaluated):
    pin = s.digest(s.encode(contract))
    result = s.result_base(
        pin,
        "cuda",
        status="complete",
        counts=dict(fits_started=2, fits_completed=2),
        smoked=True,
        runtime=runtime(contract),
    )
    groups, cells = evaluated
    result.update(
        models=[
            dict(
                architecture=a,
                file=f"weights-{a}.npz",
                weights_sha256="sha256:" + "a" * 64,
                epochs=128,
                seed=101,
                reconstructed=True,
            )
            for a in s.fitted.ARCHITECTURES
        ],
        groups=copy.deepcopy(groups),
        cells=copy.deepcopy(cells),
        paired=s.paired_facts(cells),
    )
    return result, pin


def tiny():
    targets = np.tile(np.array([0.0, 1.0, 0.25, 0.75]), (4, 1))
    losses = np.array(
        [[0.0, -0.2, 0.1, -0.1], [0.1, 0.2, -0.1, 0.0], [-0.2, 0.1, 0.0, 0.2], [9.0, 8.0, 7.0, 6.0]]
    )
    clocks = [
        [f"2020-{m:02d}-01T14:30:00+00:00", f"2020-{m:02d}-28T21:00:00+00:00"] for m in range(1, 5)
    ]
    return targets, losses, clocks


def test_config_finite_exact_recipe_and_train_bounds(sample):
    config = s.configuration()
    assert config["fits"] == 2 and config["cells"] == 144
    assert config["optimizer"] == s.fitted.configuration()["optimizer"]
    assert config["optimizer"]["epochs"] == 128 and config["optimizer"]["seed"] == 101
    assert config["risk_constant"]["train"] == ["2002-01-01", "2012-12-31"]
    assert sample.plan["train"]["bounds"] == sample.plan["momentum"]["train"]["bounds"]
    assert len(sample.plan["train"]["months"]) == 132
    assert [len(p["months"]) for p in sample.plan["periods"]] == [84, 79]
    assert sample.days[sample.plan["train"]["bounds"][1] - 1] < "2013-01-01"
    assert config["mixture"]["rate"] == 0.1 and config["weights_retained"] is True
    assert len(s.CODE) == len(set(s.CODE))


def test_real_calendar_utc_dst_early_close_and_exact_month_end():
    days, clocks = s.calendar()
    plan = s.build_plan(days, clocks)
    assert clocks["2013-07-03"][1] == "2013-07-03T17:00:00+00:00"
    assert clocks["2013-01-02"][0].endswith("14:30:00+00:00")
    assert clocks["2013-07-01"][0].endswith("13:30:00+00:00")
    for segment, points in zip(plan["periods"], plan["clocks"], strict=True):
        for month, point in zip(segment["months"], points, strict=True):
            a, b = month["bounds"]
            assert point == [clocks[days[a]][0], clocks[days[b - 1]][1]]


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_current_future_feedback_and_terminal_mutation_cannot_change_earlier_actions(index):
    targets, losses, clocks = tiny()
    before = s.online_targets(targets, losses, clocks)
    losses[index:] += np.array([100.0, -100.0, 50.0, -50.0])
    after = s.online_targets(targets, losses, clocks)
    np.testing.assert_array_equal(before[: index + 1], after[: index + 1])


def test_prior_feedback_changes_next_action_but_not_current():
    targets, losses, clocks = tiny()
    before = s.online_targets(targets, losses, clocks)
    losses[0] = [0.0, -10.0, 0.0, 0.0]
    after = s.online_targets(targets, losses, clocks)
    assert before[0] == after[0] == 0.5 and before[1] != after[1]


@pytest.mark.parametrize("kind", ["equal", "future", "naive", "nonutc", "stale"])
def test_calendar_feedback_rejected(kind):
    targets, losses, clocks = tiny()
    if kind in {"equal", "future"}:
        clocks[0][1] = clocks[1][0] if kind == "equal" else "2020-02-02T21:00:00+00:00"
    elif kind == "naive":
        clocks[0][0] = "2020-01-01T14:30:00"
    elif kind == "nonutc":
        clocks[0][0] = "2020-01-01T14:30:00+01:00"
    else:
        clocks[1][1] = clocks[0][1]
    with pytest.raises(ValueError):
        s.online_targets(targets, losses, clocks)


def test_reset_only_symbol_fold_not_month():
    targets, losses, clocks = tiny()
    whole = s.online_targets(targets, losses, clocks)
    assert np.any(whole[1:] != 0.5)
    np.testing.assert_array_equal(whole, s.online_targets(targets, losses, clocks))
    assert s.online_targets(targets[2:], losses[2:], clocks[2:])[0] == 0.5


def test_month_feedback_increment_not_prefix_no_month_liquidation():
    segment = dict(bounds=[10, 14], months=[dict(bounds=[10, 12]), dict(bounds=[12, 14])])
    trace = [Decimal("1.1"), Decimal("1.2"), Decimal("1.4"), Decimal("1.8")]
    losses = s.month_losses([trace] * 4, segment)
    assert losses[0, 0] == s.feedback_loss(Decimal(1), Decimal("1.2"))
    assert losses[1, 0] == s.feedback_loss(Decimal("1.2"), Decimal("1.8"))
    assert losses[1, 0] != s.feedback_loss(Decimal(1), Decimal("1.8"))


@pytest.mark.parametrize(
    "value", [True, 1.0, 1, Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")]
)
def test_bad_feedback_nav(value):
    with pytest.raises(ValueError):
        s.feedback_loss(value, Decimal(1))


@pytest.mark.parametrize("kind", ["float32", "shape", "bool", "negative", "nonfinite"])
def test_targets_or_prior_losses_invalid(kind):
    targets, losses, clocks = tiny()
    if kind == "float32":
        targets = targets.astype(np.float32)
    elif kind == "shape":
        targets = targets[:, :3]
    elif kind == "bool":
        losses = losses.astype(bool)
    elif kind == "negative":
        targets[0, 0] = -0.1
    else:
        losses[0, 0] = np.nan
    with pytest.raises(ValueError):
        s.online_targets(targets, losses, clocks)


def test_identical_experts_same_target_own_ledger_and_postfee_closure(sample):
    targets, losses, clocks = tiny()
    targets[:] = 0.4
    online = s.online_targets(targets, losses, clocks)
    np.testing.assert_allclose(online, 0.4, atol=1e-15, rtol=0)
    segment = sample.plan["periods"][0]
    rows = sample.prepared[s.SYMBOLS[0], segment["period"]]["rows"]
    traces = [
        s.h.replay(
            rows,
            sample.days,
            segment["bounds"],
            s.fitted._actions(segment, np.full(len(segment["months"]), w)),
            "10",
            deadline=time.monotonic() + 30,
        )
        for w in (0.4, 0.6, 0.5)
    ]
    mixed = traces[2]
    assert mixed["final_nav"] != (traces[0]["final_nav"] + traces[1]["final_nav"]) / 2
    assert abs(mixed["fees_initial_nav"] - mixed["turnover_initial_nav"] / 1000) < Decimal("1e-40")
    stock, cash, paid, _ = s.h.rebalance(Decimal(".7"), Decimal(1), Decimal(".4"), Decimal(".001"))
    assert abs(stock / (stock + cash) - Decimal(".4")) < Decimal("1e-40")
    assert abs(stock + cash + paid - 1) < Decimal("1e-40")


def test_matrix_cost_actions_and_closed_result(contract, evaluated):
    result, pin = complete(contract, evaluated)
    s.validate_result(result, contract, pin)
    assert len(result["cells"]) == 144 and len(result["groups"]) == 6
    assert result["paired"]["kill_applied"] == (
        Decimal(result["paired"]["mean_stress_nav_delta"]) <= 0
    )
    for symbol in s.SYMBOLS:
        for period, *_ in s.PERIODS:
            for policy in s.POLICIES:
                assert (
                    len(
                        {
                            c["action_sha256"]
                            for c in result["cells"]
                            if (c["symbol"], c["period"], c["policy"]) == (symbol, period, policy)
                        }
                    )
                    == 1
                )


def test_reordered_cost_and_cohort_results_invariant(sample, evaluated, monkeypatch):
    monkeypatch.setattr(s, "COSTS", tuple(reversed(s.COSTS)))
    monkeypatch.setattr(s, "SYMBOLS", tuple(reversed(s.SYMBOLS)))
    groups, cells = s.evaluate(
        sample.prepared,
        sample.plan,
        sample.predictions,
        sample.risks,
        deadline=time.monotonic() + 60,
    )

    def keyed(records):
        return {
            (c["symbol"], c["period"], c.get("cost_per_side_bps"), c.get("policy")): c
            for c in records
        }

    assert keyed(cells) == keyed(evaluated[1]) and keyed(groups) == keyed(evaluated[0])


@pytest.mark.parametrize(
    "kind", ["cell_count", "extra", "fee", "cash", "fit", "boolcount", "hash", "paired", "risk"]
)
def test_result_tampering_rejected(contract, evaluated, kind):
    result, pin = complete(contract, evaluated)
    if kind == "cell_count":
        result["cells"].pop()
    elif kind == "extra":
        result["cells"][0]["private"] = "forbidden"
    elif kind == "fee":
        result["cells"][0]["fees_initial_nav"] = s.h.number(Decimal(999))
    elif kind == "cash":
        next(c for c in result["cells"] if c["policy"] == "cash")["trades"] = 1
    elif kind == "fit":
        result["fits_completed"] = 1
    elif kind == "boolcount":
        result["groups"][0]["feedback_updates"] = True
    elif kind == "hash":
        result["cells"][8]["action_sha256"] = "sha256:" + "f" * 64
    elif kind == "paired":
        result["paired"]["kill_applied"] = int(result["paired"]["kill_applied"])
    else:
        result["groups"][1]["risk_sha256"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError):
        s.validate_result(result, contract, pin)


def test_freeze_metadata_only_immutable_and_pin_mismatch(tmp_path, contract, monkeypatch):
    calls = []
    monkeypatch.setattr(s, "runtime_constraints", lambda: None)
    monkeypatch.setattr(s.base, "verify_metadata", lambda *args: calls.append("metadata"))
    monkeypatch.setattr(s, "register_contract", lambda *args: calls.append("register"))
    artifacts, market = tmp_path / "artifacts", tmp_path / "market"
    pin = s.freeze(artifacts, market)
    root, read = s.verify(artifacts, market, pin)
    assert read == contract and calls == ["metadata", "register", "metadata"]
    assert {p.name for p in root.iterdir()} == {"precommit.json"}
    with pytest.raises(FileExistsError):
        s.freeze(artifacts, market)
    with pytest.raises(ValueError, match="file_binding"):
        s.verify(artifacts, market, "sha256:" + "f" * 64)
    changed = copy.deepcopy(contract)
    changed["config"]["mixture"]["rate"] = 0.2
    root2 = tmp_path / "other"
    root2.mkdir()
    s.atomic_new(root2 / "changed.json", changed)
    monkeypatch.setattr(s, "read_json", lambda *args: (changed, s.digest(s.encode(changed))))
    with pytest.raises(ValueError, match="source_config"):
        s.verify(artifacts, market, s.digest(s.encode(changed)))


def test_summary_exact_bytes_and_duplicate_json_rejected(tmp_path, contract, evaluated):
    result, pin = complete(contract, evaluated)
    path = tmp_path / "summary.json"
    s.atomic_new(path, result)
    value, summary_pin = s.read_json(path, s.digest(s.encode(result)))
    assert value == result and summary_pin == s.digest(path.read_bytes())
    s.validate_result(value, contract, pin)
    with pytest.raises(ValueError):
        s.read_json(path, "sha256:" + "f" * 64)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(b'{"name":1,"name":2}\n')
    with pytest.raises(ValueError, match="canonical_json"):
        s.read_json(duplicate)


def test_preview_no_operational_io_or_environment_mutation(capsys, monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("preview IO")

    before = dict(cli.os.environ)
    for name in ("freeze", "verify", "runtime_constraints", "calendar"):
        monkeypatch.setattr(s, name, denied)
    monkeypatch.setattr(cli, "dispatch", denied)
    assert cli.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "preview" and payload["operational_io"] is False
    assert dict(cli.os.environ) == before


def test_native_console_import_without_pythonpath(tmp_path):
    process = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0 and process.stderr == ""
    assert json.loads(process.stdout)["status"] == "preview"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "job", [dict(timed_out=True, exit_code=0), dict(timed_out=False, exit_code=1)]
)
def test_dispatch_failure_unknown_fits_never_success(tmp_path, contract, monkeypatch, job):
    pin = s.digest(s.encode(contract))
    monkeypatch.setattr(s, "runtime_constraints", lambda: None)
    monkeypatch.setattr(s, "verify", lambda *args: (tmp_path, contract))
    monkeypatch.setattr(cli, "supervise", lambda *args, **kwargs: job)
    monkeypatch.setattr(cli, "register_campaign_outcome", lambda **kwargs: None)
    monkeypatch.setattr(cli, "GpuFileLock", lambda *args: cli.nullcontext())
    result = cli.dispatch(tmp_path, tmp_path, pin, "cuda")
    assert result["status"] == "failed" and result["fits_started"] is None
    assert result["fits_completed"] is None and result["cells"] == 0
    with pytest.raises(ValueError, match="attempt_already_exists"):
        cli.dispatch(tmp_path, tmp_path, pin, "cuda")


def test_cpu_smoke_worker_never_loads_rows_or_gpu(tmp_path, contract, monkeypatch):
    pin = s.digest(s.encode(contract))
    monkeypatch.setattr(s, "verify", lambda *args: (tmp_path, contract))
    monkeypatch.setattr(s, "runtime_constraints", lambda: None)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setattr(s.fitted, "cpu_smoke", lambda *args, **kwargs: dict(cpu_smoke_passed=True))
    s.atomic_new(tmp_path / "cpu-smoke-started.json", {"contract_sha256": pin})
    path = tmp_path / "cpu-smoke-result.json"
    s.worker(tmp_path, tmp_path, pin, path, time.monotonic() + 30, "cpu-smoke")
    result, _ = s.read_json(path)
    s.validate_result(result, contract, pin)
    assert result["status"] == "cpu_smoke_complete"
    assert result["fits_started"] == result["fits_completed"] == 0


def zero_weights(architecture):
    return {
        k: np.zeros(shape, dtype=np.float32)
        for k, shape in s.fitted.weight_shapes(architecture).items()
    }


@pytest.mark.parametrize("architecture", s.fitted.ARCHITECTURES)
@pytest.mark.parametrize("fault", ["missing", "corrupt", "pickle", "hardlink", "symlink"])
def test_existing_numeric_npz_reader_rejects_unsafe_files(
    tmp_path, architecture, fault, monkeypatch
):
    metadata = s.fitted.write_weights(tmp_path, zero_weights(architecture), architecture)
    result = dict(models=[metadata])
    path = tmp_path / metadata["file"]
    s.verify_weights(tmp_path, result)
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(path.read_bytes()[:-1])
    elif fault == "pickle":
        values = zero_weights(architecture)
        values[next(iter(values))] = np.array(["PRIVATE_SENTINEL"], dtype=object)
        buffer = io.BytesIO()
        np.savez(buffer, **values)
        path.write_bytes(buffer.getvalue())
        metadata["weights_sha256"] = s.digest(buffer.getvalue())
    elif fault == "hardlink":
        alias = tmp_path / "alias.npz"
        os.link(path, alias)
    else:
        monkeypatch.setattr(type(path), "is_symlink", lambda self: self == path)
    try:
        with pytest.raises((ValueError, FileNotFoundError)):
            s.verify_weights(tmp_path, result)
    finally:
        if fault == "hardlink":
            # Retire only this test's alias; retain the guard against linked scratch.
            alias.unlink()


def fake_cuda_worker(tmp_path, contract, sample, monkeypatch):
    pin = s.digest(s.encode(contract))
    monkeypatch.setattr(s, "verify", lambda *args: (tmp_path, contract))
    monkeypatch.setattr(s, "runtime_constraints", lambda: None)
    monkeypatch.setattr(s.fitted, "load_adjusted", lambda *args: sample.rows)
    monkeypatch.setattr(s.fitted, "prepare", lambda *args: sample.prepared)
    monkeypatch.setattr(s.fitted, "cpu_smoke", lambda *args, **kwargs: dict(cpu_smoke_passed=True))
    fake = SimpleNamespace(
        __version__=contract["runtime"]["torch"],
        version=SimpleNamespace(cuda="12.8"),
        set_num_threads=lambda _: None,
        get_num_threads=lambda: 2,
        use_deterministic_algorithms=lambda _: None,
        backends=SimpleNamespace(
            cudnn=SimpleNamespace(), cuda=SimpleNamespace(matmul=SimpleNamespace())
        ),
        cuda=SimpleNamespace(
            is_available=lambda: True,
            mem_get_info=lambda _: (22 * 1024**3, 24 * 1024**3),
            set_per_process_memory_fraction=lambda *args: None,
            reset_peak_memory_stats=lambda _: None,
            synchronize=lambda _: None,
            get_device_name=lambda _: "synthetic",
            max_memory_allocated=lambda _: 123,
        ),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    calls, rebuilt = [], []

    def fit(torch, arrays, architecture, *, device, deadline):
        assert tuple(arrays) == s.SYMBOLS and device == "cuda:0"
        assert all(
            arrays[symbol] is sample.prepared[symbol, "TRAIN"]["arrays"] for symbol in s.SYMBOLS
        )
        assert all(len(a.decision_dates) == 132 for a in arrays.values())
        calls.append(architecture)
        return zero_weights(architecture)

    def rebuild(torch, values, architecture):
        s.fitted.validate_weights(values, architecture)
        rebuilt.append(architecture)
        return architecture

    monkeypatch.setattr(s.fitted, "fit_policy", fit)
    monkeypatch.setattr(s.fitted, "rebuild_policy", rebuild)
    monkeypatch.setattr(
        s.fitted,
        "predict",
        lambda torch, model, arrays: np.full(
            len(arrays.decision_dates), 0.4 if model == "linear" else 0.6
        ),
    )
    s.atomic_new(tmp_path / "cuda-started.json", {"contract_sha256": pin})
    return pin, calls, rebuilt


def test_exact_two_fit_worker_retains_npz_and_cpu_reconstruction(
    tmp_path, contract, sample, monkeypatch
):
    pin, calls, rebuilt = fake_cuda_worker(tmp_path, contract, sample, monkeypatch)
    path = tmp_path / "cuda-result.json"
    s.worker(tmp_path, tmp_path, pin, path, time.monotonic() + 60, "cuda")
    result, _ = s.read_json(path)
    s.validate_result(result, contract, pin)
    s.verify_weights(tmp_path, result)
    assert result["status"] == "complete" and result["failure_stage"] is None
    assert calls == ["linear", "lstm"] and rebuilt == ["linear", "linear", "lstm", "lstm"]
    assert len(result["cells"]) == 144
    assert {p.name for p in tmp_path.iterdir()} == {
        "cuda-started.json",
        "cuda-result.json",
        "weights-linear.npz",
        "weights-lstm.npz",
    }
    assert sum((tmp_path / m["file"]).stat().st_size for m in result["models"]) < 1024**2


@pytest.mark.parametrize("stage", s.FAILURE_STAGES)
def test_failure_stage_and_observed_fit_counts_preserved(
    tmp_path, contract, sample, monkeypatch, stage
):
    pin, _, _ = fake_cuda_worker(tmp_path, contract, sample, monkeypatch)
    raw_error = "SECRET_OR_PRIVATE_DIAGNOSTIC_NEVER_SERIALIZED"

    def bad(*args, **kwargs):
        raise ValueError(raw_error)

    owner, attribute = {
        "cpu_smoke": (s.fitted, "cpu_smoke"),
        "load": (s.fitted, "load_adjusted"),
        "prepare": (s.fitted, "prepare"),
        "fit": (s.fitted, "fit_policy"),
        "inference": (s.fitted, "predict"),
        "evaluate": (s, "evaluate"),
        "validate": (s, "validate_result"),
    }[stage]
    monkeypatch.setattr(owner, attribute, bad)
    path = tmp_path / "cuda-result.json"
    s.worker(tmp_path, tmp_path, pin, path, time.monotonic() + 60, "cuda")
    result, _ = s.read_json(path)
    assert result["status"] == "failed" and result["failure_stage"] == stage
    assert result["fits_started"] == (
        0
        if stage in {"cpu_smoke", "load", "prepare"}
        else 1
        if stage in {"fit", "inference"}
        else 2
    )
    assert result["fits_completed"] == (
        0 if stage in {"cpu_smoke", "load", "prepare", "fit"} else 1 if stage == "inference" else 2
    )
    assert result["cells"] == [] and raw_error not in path.read_text()


def test_prediction_reconstruction_mismatch_fails_without_second_fit(
    tmp_path, contract, sample, monkeypatch
):
    pin, calls, _ = fake_cuda_worker(tmp_path, contract, sample, monkeypatch)
    count = 0

    def inconsistent(torch, model, arrays):
        nonlocal count
        count += 1
        return np.full(len(arrays.decision_dates), 0.4 if count == 1 else 0.5)

    monkeypatch.setattr(s.fitted, "predict", inconsistent)
    path = tmp_path / "cuda-result.json"
    s.worker(tmp_path, tmp_path, pin, path, time.monotonic() + 60, "cuda")
    result, _ = s.read_json(path)
    assert result["status"] == "failed" and result["failure_stage"] == "inference"
    assert calls == ["linear"] and result["fits_started"] == result["fits_completed"] == 1


def test_cli_verify_reads_exact_numeric_weight_files(
    tmp_path, contract, evaluated, monkeypatch, capsys
):
    result, pin = complete(contract, evaluated)
    result["models"] = [
        s.fitted.write_weights(tmp_path, zero_weights(a), a) for a in s.fitted.ARCHITECTURES
    ]
    s.atomic_new(tmp_path / "cuda-summary.json", result)
    summary_pin = s.digest(s.encode(result))
    monkeypatch.setattr(s, "verify", lambda *args: (tmp_path, contract))
    monkeypatch.setattr(s.base, "ensure_external_artifact_directory", lambda *args: tmp_path)
    args = ["--verify", "--contract-sha256", pin, "--summary-sha256", summary_pin]
    assert cli.main(args) == 0 and json.loads(capsys.readouterr().out)["status"] == "verified"
    (tmp_path / "weights-lstm.npz").unlink()
    assert cli.main(args) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "dispatch_unavailable"


@pytest.mark.parametrize("value", [True, {}, [], "private_exception", "source_load"])
def test_failure_stage_closed_enum(contract, value):
    pin = s.digest(s.encode(contract))
    result = s.result_base(pin, "cuda", failure_stage=value)
    with pytest.raises(ValueError, match="failure_stage"):
        s.validate_result(result, contract, pin)


def test_incomplete_runtime_payload_rejected(contract):
    pin = s.digest(s.encode(contract))
    result = s.result_base(pin, "cuda", runtime={"private_error": "forbidden"})
    with pytest.raises(ValueError, match="incomplete_scores"):
        s.validate_result(result, contract, pin)


def test_parent_readback_failure_preserves_verified_child_fit_counts(
    tmp_path, contract, evaluated, monkeypatch
):
    result, pin = complete(contract, evaluated)
    s.atomic_new(tmp_path / "cuda-result.json", result)
    monkeypatch.setattr(s, "runtime_constraints", lambda: None)
    monkeypatch.setattr(s, "verify", lambda *args: (tmp_path, contract))
    monkeypatch.setattr(
        cli, "supervise", lambda *args, **kwargs: dict(timed_out=False, exit_code=0)
    )
    monkeypatch.setattr(cli, "register_campaign_outcome", lambda **kwargs: None)
    monkeypatch.setattr(cli, "GpuFileLock", lambda *args: cli.nullcontext())
    # The verified child result exists, but its retained numeric files are missing.
    output = cli.dispatch(tmp_path, tmp_path, pin, "cuda")
    assert output["status"] == "failed" and output["failure_stage"] == "validate"
    assert output["fits_started"] == output["fits_completed"] == 2


def test_continuous_month_boundaries_include_gap_and_never_reset_capital():
    days = ["2020-01-02", "2020-02-03", "2020-03-02"]
    rows = {
        d: AdjustedEtfRow(
            "SPY", date.fromisoformat(d), Decimal(p), Decimal(p), Decimal(p), Decimal(p)
        )
        for d, p in zip(days, (1, 2, 4), strict=True)
    }
    segment = dict(bounds=[0, 3], months=[dict(bounds=[i, i + 1]) for i in range(3)])
    replay = s.h.replay(
        rows,
        days,
        [0, 3],
        dict.fromkeys(range(3), Decimal(".5")),
        "0",
        deadline=time.monotonic() + 30,
    )
    assert replay["navs"] == [Decimal(1), Decimal("1.5"), Decimal("2.25")]
    losses = s.month_losses([replay["navs"]] * 4, segment)
    assert losses[:, 0].tolist() == [
        0.0,
        s.feedback_loss(Decimal(1), Decimal("1.5")),
        s.feedback_loss(Decimal("1.5"), Decimal("2.25")),
    ]
