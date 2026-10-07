from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import tiingo_joint_d1_policy as study


def synthetic_x(n=5):
    return np.sin(np.arange(n * 9 * 31, dtype=float).reshape(n, 9, 31) / 47) * 0.01


@pytest.fixture
def torch():
    return pytest.importorskip("torch")


@pytest.fixture
def cpu_only(monkeypatch, torch):
    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden capability")

    for name in ("is_available", "manual_seed_all", "mem_get_info", "synchronize"):
        monkeypatch.setattr(torch.cuda, name, forbidden)
    return forbidden


@pytest.mark.parametrize("method", study.METHODS)
def test_models_cpu_shapes_reproducible_and_numeric_restore(method, cpu_only, torch):
    x = torch.tensor(synthetic_x(), dtype=torch.float64)
    net = study.model(method)
    before = study.numeric_state(net)
    assert before == study.numeric_state(study.model(method))
    result = net(x)
    assert result.shape == (5, 4)
    assert torch.isfinite(result).all()
    assert torch.all(result > 0)
    assert torch.allclose(result.sum(1), torch.ones(5, dtype=torch.float64), atol=1e-14, rtol=0)
    restored = study.restore_model(method, json.loads(json.dumps(before)))
    assert torch.equal(result, restored(x))
    result[:, 0].sum().backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in net.parameters())


def test_tcn_internal_representation_is_causal_and_receptive_field_exact(cpu_only, torch):
    net = study.model("tcn")
    original = torch.tensor(synthetic_x(), dtype=torch.float64)
    mutated = original.clone()
    mutated[:, :, 17:] += 30
    assert torch.equal(
        net.representation(original)[:, :, :17], net.representation(mutated)[:, :, :17]
    )
    assert sum(2 * layer.dilation[0] for layer in net.layers) + 1 == 31
    assert [layer.out_channels for layer in net.layers] == [8] * 4
    assert [layer.kernel_size for layer in net.layers] == [(3,)] * 4


@pytest.mark.parametrize("method", study.METHODS)
def test_state_shape_keys_and_nonfinite_rejected(method, torch):
    state = study.numeric_state(study.model(method))
    with pytest.raises(ValueError, match="state_keys"):
        study.restore_model(method, dict(state, unexpected=[]))
    key = next(iter(state))
    with pytest.raises(ValueError, match="state_geometry"):
        study.restore_model(method, dict(state, **{key: [float("nan")]}))


def test_scaler_train_only_zero_channel_and_restore():
    train = synthetic_x()
    train[:, 0] = 0
    scaler = study.train_scaler(train)
    assert scaler.scale[0] == 1
    assert np.array_equal(
        study.ChannelScaler.restore(scaler.payload()).transform(train), scaler.transform(train)
    )
    future = synthetic_x(2) * 200
    before = scaler.payload()
    scaler.transform(future)
    assert scaler.payload() == before
    assert np.allclose(scaler.transform(train).mean((0, 2)), 0, atol=1e-14)
    with pytest.raises(ValueError, match="scaler_positive"):
        study.ChannelScaler.restore(dict(mean=[0] * 9, scale=[0] * 9))


@pytest.mark.parametrize("weights", ([0.25] * 4, [1, 0, 0, 0], [0, 0, 0, 1], [0.3, 0.2, 0.4, 0.1]))
def test_decimal_four_weights_sum_exact(weights):
    target = study.decimal_target(weights)
    assert sum(map(Fraction, (*target.weights3, target.cash_weight)), Fraction(0)) == 1


@pytest.mark.parametrize(
    "weights",
    (
        [0] * 4,
        [-1, 1, 1, 1],
        [float("inf")] * 4,
        [1] * 3,
        [2, 0, 0, 0],
        [0.3, 0.3, 0.3, 0.3],
        [0.1, 0.1, 0.1, 0.1],
    ),
)
def test_invalid_weights_rejected(weights):
    with pytest.raises(ValueError):
        study.decimal_target(weights)


def test_static_contract_has_strengthened_training_and_nonpromoting_scope():
    config = study.configuration()
    assert config["fit"]["final_updates"] == {"constant": 1024, "linear": 512, "tcn": 512}
    assert config["fit"]["learning_rate"]["constant"] == 0.01
    assert config["fit"]["weight_decay"]["constant"] == 0
    assert config["cells"] == 36
    assert config["scope"]["holdout_access"] == "none"
    assert not config["scope"]["paper_input"]
    assert "descriptive only" in config["stress"]


def rows_and_plan():
    days = [date(2001, 10, 1) + timedelta(days=i) for i in range(38)]
    rows = {
        symbol: tuple(
            SimpleNamespace(
                session_date=d,
                adj_open=Decimal(100 + i + j),
                adj_close=Decimal(101 + i + j),
                adj_high=Decimal(102 + i + j),
                adj_low=Decimal(99 + i + j),
            )
            for i, d in enumerate(days)
        )
        for j, symbol in enumerate(study.SYMBOLS)
    }
    spec = dict(
        period="TRAIN",
        bounds=[32, 36],
        quarters=[32],
        decisions=[
            dict(
                index=i,
                session_date=days[i].isoformat(),
                decision_at=datetime.combine(days[i], datetime.min.time(), UTC)
                .replace(hour=14, minute=30)
                .isoformat(),
                scheduled_dates=[d.isoformat() for d in days[i - 32 : i]],
            )
            for i in range(32, 36)
        ],
    )
    return rows, dict(days=[d.isoformat() for d in days], periods=[spec])


def test_adapter_separates_future_marks_from_past_feature_availability():
    rows, plan = rows_and_plan()
    ready = study.prepare_inputs(rows, plan, deadline=float("inf"))[0]
    for s in study.SYMBOLS:
        changed = dict(
            rows, **{s: tuple(r for r in rows[s] if r.session_date.isoformat() < plan["days"][35])}
        )
        result = study.prepare_inputs(changed, plan, deadline=float("inf"))[0]
        assert np.array_equal(result.x, ready.x)
        assert result.marks is None
        assert result.facts["inputs"] == ready.facts["inputs"]


def test_adapter_one_past_gap_invalidates_whole_learned_fold_not_cash_marks():
    rows, plan = rows_and_plan()
    rows["QQQ"] = rows["QQQ"][1:]
    result = study.prepare_inputs(rows, plan, deadline=float("inf"))[0]
    assert result.x is None
    assert result.marks is not None
    assert result.facts["missing_inputs"] == 1
    assert "array" not in repr(result)


def test_utility_population_initial_return_and_global_path():
    logs = tuple(map(Decimal, ("-.01", ".02", ".01")))
    mean = sum(logs) / 3
    expected = 252 * (mean - 5 * sum((v - mean) ** 2 for v in logs) / 3)
    assert abs(study.utility_logs(logs) - expected) < Decimal("1e-24")


def test_torch_utility_global_population_path(torch):
    logs = tuple(map(Decimal, ("-.01", ".02", ".01")))
    expected = study.utility_logs(logs)
    tensor = torch.tensor([float(v) for v in logs], dtype=torch.float64, requires_grad=True)
    value = study.torch_utility(SimpleNamespace(log_returns=tensor))
    assert abs(float(value.detach()) - float(expected)) < 1e-14
    value.backward()
    assert torch.isfinite(tensor.grad).all()


def runner():
    path = study.REPO / "scripts/run_tiingo_joint_d1_policy.py"
    spec = importlib.util.spec_from_file_location("joint_d1_runner_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_core_analytical_parity_before_models(cpu_only, monkeypatch):
    monkeypatch.setattr(study, "model", cpu_only)
    result = study.analytical_parity()
    assert result["scenarios"] == 12
    assert result["gradient_checks"] == 3
    assert result["gpu_probes"] == 0


def test_smoke_uses_no_source_registry_or_cuda(cpu_only, monkeypatch):
    for obj, name in (
        (study.prior, "load_adjusted"),
        (study.prior.base, "verify_metadata"),
        (study, "register_contract"),
        (study, "register_campaign_outcome"),
        (study, "fit_bundle"),
    ):
        monkeypatch.setattr(obj, name, cpu_only)
    result = study.smoke()
    assert result["status"] == "synthetic_cpu_passed"
    assert result["model_smokes"] == 3
    assert result["actual_source_rows"] == 0
    assert result["gpu_probes"] == 0
    assert result["code_sha256"] == study.code_identity()


def test_smoke_failure_prevents_model_construction(cpu_only, monkeypatch):
    def failure():
        raise ValueError("analytic_parity")

    monkeypatch.setattr(study, "analytical_parity", failure)
    monkeypatch.setattr(study, "model", cpu_only)
    with pytest.raises(ValueError, match="analytic_parity"):
        study.smoke()


@pytest.mark.parametrize("method", study.METHODS)
def test_one_update_full_path_loss_and_adam_parameters(method, torch, monkeypatch):
    inputs = study.synthetic_inputs()
    calls, optimizers = [], []
    replay = study.replay_torch
    optimizer = torch.optim.AdamW

    def observed(o, c, w, cost):
        calls.append((o.shape, c.shape, w.shape, cost, w.requires_grad))
        return replay(o, c, w, cost)

    def make_optimizer(*args, **kwargs):
        optimizers.append(kwargs)
        return optimizer(*args, **kwargs)

    monkeypatch.setattr(study, "replay_torch", observed)
    monkeypatch.setattr(torch.optim, "AdamW", make_optimizer)
    initial = study.numeric_state(study.model(method))
    fitted = study.fit_final(
        method, inputs, study.train_scaler(inputs.x), updates=2, device="cpu", deadline=float("inf")
    )
    assert fitted != initial
    assert calls == [(torch.Size([6, 3]), torch.Size([6, 3]), torch.Size([6, 4]), 10.0, True)] * 2
    config = study.configuration()["fit"]
    assert optimizers == [
        dict(lr=config["learning_rate"][method], weight_decay=config["weight_decay"][method])
    ]


def test_timeout_is_categorical_before_update(torch):
    inputs = study.synthetic_inputs()
    with pytest.raises(ValueError, match="hard_timeout"):
        study.fit_final(
            "constant", inputs, study.train_scaler(inputs.x), updates=1, device="cpu", deadline=0
        )


def test_static_cli_no_io_or_torch(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("not static")

    for name in ("torch_cpu", "code_identity", "runtime_identity", "freeze", "verify", "smoke"):
        monkeypatch.setattr(study, name, forbidden)
    assert runner().main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "static_plan"


def test_cli_smoke_no_artifact_by_default(cpu_only, monkeypatch, capsys):
    monkeypatch.setattr(study, "verify", cpu_only)
    monkeypatch.setattr(study, "_output", cpu_only)
    monkeypatch.setattr(study, "atomic_new", cpu_only)
    assert runner().main(["--smoke"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["gpu_probes"] == 0
    assert "weights" not in capsys.readouterr().out


def test_smoke_receipt_immutable_and_outside_repo(cpu_only, tmp_path, capsys):
    receipt = tmp_path / "smoke" / "receipt.json"
    assert runner().main(["--smoke", "--smoke-receipt", str(receipt)]) == 0
    saved = receipt.read_bytes()
    assert json.loads(saved)["status"] == "synthetic_cpu_passed"
    assert runner().main(["--smoke", "--smoke-receipt", str(receipt)]) == 1
    assert receipt.read_bytes() == saved
    assert runner().main(["--smoke", "--smoke-receipt", str(study.REPO / "forbidden.json")]) == 1
    assert not (study.REPO / "forbidden.json").exists()
    capsys.readouterr()


def mini_schedule():
    dates = [date(2001, 1, 1) + timedelta(days=i) for i in range(365)]
    for year in (2002, 2013, 2014, 2020, 2021, 2026):
        dates += [date(year, 1, 1) + timedelta(days=i) for i in range(4)]
    return [
        dict(session_date=d.isoformat(), open_at=f"{d.isoformat()}T14:30:00+00:00") for d in dates
    ]


@pytest.fixture
def campaign(tmp_path, monkeypatch, torch):
    monkeypatch.setattr(study.prior, "calendar_schedule", mini_schedule)
    expected_runtime = {
        k: study.configuration()["runtime"][k] for k in ("python", "torch", "numpy", "calendar")
    }
    monkeypatch.setattr(study, "runtime_identity", lambda: dict(expected_runtime))
    monkeypatch.setattr(study.prior.base, "verify_metadata", lambda *args: None)
    root, market = tmp_path / "artifacts", tmp_path / "market"
    pin = study.freeze(root, market)
    output, contract = study.verify(root, market, pin)
    rows = {
        s: tuple(
            SimpleNamespace(
                session_date=date.fromisoformat(d),
                adj_open=Decimal(100 + i + j),
                adj_close=Decimal(100 + i + j) * Decimal("1.001"),
                adj_high=Decimal(101 + i + j),
                adj_low=Decimal(99 + i + j),
            )
            for i, d in enumerate(contract["plan"]["days"])
        )
        for j, s in enumerate(study.SYMBOLS)
    }
    monkeypatch.setattr(study.prior, "load_adjusted", lambda *args: rows)
    prepared = study.prepare_inputs(rows, contract["plan"], deadline=float("inf"))
    bundle = dict(
        version=1,
        contract_sha256=pin,
        scaler=study.train_scaler(prepared[0].x).payload(),
        states={m: study.numeric_state(study.model(m)) for m in study.METHODS},
        updates=dict(study.UPDATES),
    )
    resources = dict(
        device="cuda",
        fits=3,
        peak_allocated_bytes=100,
        allocator_cap_bytes=200,
        fit_durations=[
            dict(method=m, updates=study.UPDATES[m], elapsed_seconds=0.01) for m in study.METHODS
        ],
    )
    monkeypatch.setattr(study, "fit_bundle", lambda *args, **kwargs: (bundle, resources))
    return SimpleNamespace(
        root=root,
        market=market,
        pin=pin,
        output=output,
        contract=contract,
        rows=rows,
        prepared=prepared,
        bundle=bundle,
        resources=resources,
    )


def test_freeze_is_immutable_metadata_only(campaign, monkeypatch):
    original = (campaign.output / "precommit.json").read_bytes()

    def forbidden(*args):
        raise AssertionError("source values accessed")

    monkeypatch.setattr(study.prior, "load_adjusted", forbidden)
    with pytest.raises(FileExistsError):
        study.freeze(campaign.root, campaign.market)
    assert (campaign.output / "precommit.json").read_bytes() == original
    plan = campaign.contract["plan"]
    assert all(len(d["scheduled_dates"]) == 32 for p in plan["periods"] for d in p["decisions"])
    assert all(
        d["scheduled_dates"][-1] < d["session_date"]
        for p in plan["periods"]
        for d in p["decisions"]
    )


def complete_mock_attempt(campaign):
    study.atomic_new(campaign.output / "started.json", dict(contract_sha256=campaign.pin))
    study.run_worker(
        campaign.root,
        campaign.market,
        campaign.pin,
        campaign.output / "worker-result.json",
        float("inf"),
    )
    result = json.loads((campaign.output / "worker-result.json").read_bytes())
    assert result["status"] != "failed"
    study.atomic_new(campaign.output / "summary.json", result)
    return result


def test_actual_adapter_36_cells_and_exact_zero_fit_readback(campaign, cpu_only, monkeypatch):
    result = complete_mock_attempt(campaign)
    assert len(result["cells"]) == 36
    assert result["criterion"] in {"rejected", "input_unavailable"}
    monkeypatch.setattr(study, "fit_bundle", cpu_only)
    monkeypatch.setattr(study, "fit_final", cpu_only)
    monkeypatch.setattr(study.prior, "match_beta", cpu_only)
    before = {p.name: p.read_bytes() for p in campaign.output.iterdir()}
    replayed = study.readback(
        campaign.root,
        campaign.market,
        campaign.pin,
        result_sha256=study.digest(study.encode(result)),
        deadline=float("inf"),
    )
    assert replayed["replay"] == "exact"
    assert replayed["refits"] == replayed["beta_searches"] == replayed["writes"] == 0
    assert {p.name: p.read_bytes() for p in campaign.output.iterdir()} == before


def test_post_summary_registry_failure_recovery_idempotent_immutable(campaign, monkeypatch):
    module = runner()

    def supervised(target, args, **kwargs):
        target(*args)
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(module, "supervise", supervised)

    def fail(**kwargs):
        raise OSError("synthetic registry append failure")

    monkeypatch.setattr(module, "register_campaign_outcome", fail)
    with pytest.raises(OSError):
        module.dispatch(campaign.root, campaign.market, campaign.pin)
    original = {p.name: p.read_bytes() for p in campaign.output.iterdir()}
    pin = study.digest(original["summary.json"])
    first = study.recover_registry(
        campaign.root, campaign.market, campaign.pin, result_sha256=pin, deadline=float("inf")
    )
    registry = tuple(sorted((campaign.root / "_control" / "ledger").rglob("*.jsonl")))
    before = {str(p): p.read_bytes() for p in registry}
    second = study.recover_registry(
        campaign.root, campaign.market, campaign.pin, result_sha256=pin, deadline=float("inf")
    )
    assert first == second
    assert {str(p): p.read_bytes() for p in registry} == before
    assert {p.name: p.read_bytes() for p in campaign.output.iterdir()} == original


def test_interrupted_parent_finalizes_original_worker_without_fit(campaign, cpu_only, monkeypatch):
    module = runner()

    def supervised(target, args, **kwargs):
        target(*args)
        return dict(timed_out=False, exit_code=0)

    monkeypatch.setattr(module, "supervise", supervised)
    original_writer = study.atomic_new

    def interrupted(path, payload):
        if path.name == "summary.json":
            raise KeyboardInterrupt
        return original_writer(path, payload)

    with monkeypatch.context() as interruption:
        interruption.setattr(study, "atomic_new", interrupted)
        with pytest.raises(KeyboardInterrupt):
            module.dispatch(campaign.root, campaign.market, campaign.pin)
    assert not (campaign.output / "summary.json").exists()
    original = {p.name: p.read_bytes() for p in campaign.output.iterdir()}
    pin = study.digest(original["worker-result.json"])
    monkeypatch.setattr(study, "fit_bundle", cpu_only)
    monkeypatch.setattr(study, "fit_final", cpu_only)
    monkeypatch.setattr(study.prior, "match_beta", cpu_only)
    first = study.recover_terminal(
        campaign.root,
        campaign.market,
        campaign.pin,
        result_sha256=pin,
        deadline=float("inf"),
    )
    assert first["summary_artifact_writes"] == 1 and first["model_writes"] == 0
    assert first["refits"] == first["beta_searches"] == 0
    assert (campaign.output / "summary.json").read_bytes() == original["worker-result.json"]
    assert all((campaign.output / name).read_bytes() == raw for name, raw in original.items())
    registry = campaign.root / "_control" / "ledger"
    before = {p.name: p.read_bytes() for p in registry.glob("*.jsonl")}
    second = study.recover_terminal(
        campaign.root,
        campaign.market,
        campaign.pin,
        result_sha256=pin,
        deadline=float("inf"),
    )
    assert second["summary_artifact_writes"] == 0
    assert second["outcome_record_sha256"] == first["outcome_record_sha256"]
    assert {p.name: p.read_bytes() for p in registry.glob("*.jsonl")} == before


@pytest.mark.parametrize("fault", ("owner", "worker_hash", "model_hash", "terminal_conflict"))
def test_terminal_finalizer_rejects_unowned_or_conflicting_evidence(campaign, monkeypatch, fault):
    result = complete_mock_attempt(campaign)
    terminal = campaign.output / "summary.json"
    terminal.unlink()
    pin = study.digest(study.encode(result))
    if fault == "owner":
        lock = campaign.root / study.configuration()["budget"]["gpu_lock"]
        lock.parent.mkdir(parents=True)
        lock.write_text("synthetic active owner")
    elif fault == "worker_hash":
        pin = "sha256:" + "0" * 64
    elif fault == "model_hash":
        model_path = campaign.output / "numeric-models.json"
        model_path.write_bytes(model_path.read_bytes() + b" ")
    else:
        terminal.write_bytes(
            study.encode(study.failure(campaign.contract, campaign.pin, "hard_timeout"))
        )
    before = {p.name: p.read_bytes() for p in campaign.output.iterdir()}
    with pytest.raises(ValueError):
        study.recover_terminal(
            campaign.root,
            campaign.market,
            campaign.pin,
            result_sha256=pin,
            deadline=float("inf"),
        )
    assert {p.name: p.read_bytes() for p in campaign.output.iterdir()} == before


def test_terminal_finalizer_cli_requires_both_pins():
    module = runner()
    with pytest.raises(SystemExit):
        module.main(["--recover-terminal"])
    with pytest.raises(SystemExit):
        module.main(["--recover-terminal", "--contract-sha256", "sha256:" + "a" * 64])


def test_failure_receipt_registry_recovery_never_source_or_fit(campaign, cpu_only, monkeypatch):
    study.atomic_new(campaign.output / "started.json", dict(contract_sha256=campaign.pin))
    failure = study.failure(campaign.contract, campaign.pin, "hard_timeout")
    study.atomic_new(campaign.output / "summary.json", failure)
    monkeypatch.setattr(study.prior, "load_adjusted", cpu_only)
    monkeypatch.setattr(study, "fit_bundle", cpu_only)
    result = study.recover_registry(
        campaign.root,
        campaign.market,
        campaign.pin,
        result_sha256=study.digest(study.encode(failure)),
        deadline=float("inf"),
    )
    assert result["replay"] == "immutable_failure"
    assert result["refits"] == 0


def test_fixed_path_year_deletion_is_not_reexecution_or_criterion(campaign):
    result = complete_mock_attempt(campaign)
    assert all(
        a["status"] in {"descriptive_only", "input_unavailable"} for a in result["year_deletions"]
    )
    result["year_deletions"] = []
    assert study.primary_verdict(result["cells"]) == result["criterion"]


def test_missing_past_input_no_repeat_targets_or_fitted_control(campaign):
    rows = dict(campaign.rows)
    rows["QQQ"] = rows["QQQ"][1:]
    # Drop a past key required by the first comparison, rather than by TRAIN.
    index = campaign.contract["plan"]["periods"][1]["bounds"][0] - 1
    rows["QQQ"] = tuple(
        r
        for r in rows["QQQ"]
        if r.session_date.isoformat() != campaign.contract["plan"]["days"][index]
    )
    prepared = study.prepare_inputs(rows, campaign.contract["plan"], deadline=float("inf"))
    assert prepared[1].x is None and prepared[1].marks is not None
    result = study.evaluate(
        prepared, campaign.bundle, campaign.contract, campaign.pin, deadline=float("inf")
    )
    result["resources"] = campaign.resources
    study.validate_result(result, campaign.contract, campaign.pin)
    for cell in result["cells"]:
        if cell["period"] == "2013-2019" and cell["policy"] in study.METHODS:
            assert cell["status"] == "input_unavailable"
            assert cell["action_sha256"] is None


@pytest.mark.parametrize(
    "phase, function, code",
    [
        ("synthetic_smoke", "smoke", "analytic_parity"),
        ("source_input", "prepare_inputs", "source_symbols"),
        ("fit", "fit_bundle", "gradient_nonfinite"),
        ("evaluate", "evaluate", "policy_residual"),
    ],
)
def test_phase_pinned_allowlisted_failure_only(campaign, monkeypatch, phase, function, code):
    def fail(*args, **kwargs):
        raise ValueError(code)

    if phase != "synthetic_smoke":
        monkeypatch.setattr(study, "smoke", lambda **kwargs: {"status": "synthetic_cpu_passed"})
    monkeypatch.setattr(study, function, fail)
    study.atomic_new(campaign.output / "started.json", dict(contract_sha256=campaign.pin))
    study.run_worker(
        campaign.root,
        campaign.market,
        campaign.pin,
        campaign.output / "worker-result.json",
        float("inf"),
    )
    saved = json.loads((campaign.output / "worker-result.json").read_bytes())
    assert saved["status"] == "failed"
    assert saved["phase"] == phase
    assert saved["invariant_code"] == code
    study.validate_result(saved, campaign.contract, campaign.pin)
    assert study.safe_result(saved)["invariant_code"] == code
    assert saved["cells"] == []


def test_unknown_error_body_not_retained(campaign, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("invented raw private body must not survive")

    monkeypatch.setattr(study, "fit_bundle", fail)
    study.atomic_new(campaign.output / "started.json", dict(contract_sha256=campaign.pin))
    study.run_worker(
        campaign.root,
        campaign.market,
        campaign.pin,
        campaign.output / "worker-result.json",
        float("inf"),
    )
    raw = (campaign.output / "worker-result.json").read_bytes()
    saved = json.loads(raw)
    assert b"invented raw private" not in raw
    assert saved["phase"] == "fit"
    assert saved["invariant_code"] is None


def test_missing_train_never_fit_or_evaluate_learned_comparison(campaign, monkeypatch):
    rows = dict(campaign.rows)
    rows["QQQ"] = rows["QQQ"][1:]
    # Earliest first TRAIN window in this synthetic calendar begins before day0? Pick exact key.
    first = campaign.contract["plan"]["periods"][0]["decisions"][0]["scheduled_dates"][0]
    rows["QQQ"] = tuple(r for r in rows["QQQ"] if r.session_date.isoformat() != first)
    monkeypatch.setattr(study.prior, "load_adjusted", lambda *args: rows)

    def no_fit(*args, **kwargs):
        raise AssertionError("fit after missing TRAIN")

    monkeypatch.setattr(study, "fit_bundle", no_fit)
    study.atomic_new(campaign.output / "started.json", dict(contract_sha256=campaign.pin))
    study.run_worker(
        campaign.root,
        campaign.market,
        campaign.pin,
        campaign.output / "worker-result.json",
        float("inf"),
    )
    saved = json.loads((campaign.output / "worker-result.json").read_bytes())
    assert saved["status"] == "input_unavailable"
    assert saved["model_sha256"] is None
    assert saved["resources"]["fits"] == 0
    assert not (campaign.output / "numeric-models.json").exists()
    assert all(
        c["status"] == "input_unavailable" for c in saved["cells"] if c["policy"] in study.METHODS
    )
    assert all(
        c["status"] == "evaluated" for c in saved["cells"] if c["policy"] in {"cash", "quarter_ew"}
    )


@pytest.mark.parametrize("payload", ([True] * 9, ["0.1"] * 9, [None] * 9))
def test_scaler_json_numeric_only(payload):
    with pytest.raises(ValueError, match="scaler_mean"):
        study.ChannelScaler.restore(dict(mean=payload, scale=[1] * 9))


@pytest.mark.parametrize("payload", ([True] * 4, ["0.1"] * 4, [None] * 4))
def test_weights_json_numeric_only(payload, torch):
    with pytest.raises(ValueError, match="state_geometry"):
        study.restore_model("constant", dict(logits=payload))


def winning_cells():
    return [
        dict(
            period=p,
            policy=m,
            cost_per_side_bps=c,
            status="evaluated",
            final_nav="1.3" if m == "tcn" else "1.1",
            utility=".3" if m == "tcn" else ".1",
        )
        for p, _, _ in study.PERIODS
        for c in study.COSTS
        for m in study.POLICIES
    ]


@pytest.mark.parametrize(
    "control", ("constant", "linear", "tcn_beta_matched_quarter_ew_cash", "quarter_ew")
)
@pytest.mark.parametrize("period", ("2013-2019", "2020-2026-07"))
def test_kill_requires_both_periods_and_every_predeclared_control(control, period):
    cells = winning_cells()
    assert study.primary_verdict(cells) == "supported_with_limits"
    next(
        c
        for c in cells
        if c["policy"] == control and c["period"] == period and c["cost_per_side_bps"] == "10"
    )["utility"] = ".3"
    assert study.primary_verdict(cells) == "rejected"


def test_matching_unresolved_and_nonpositive_growth_never_pass():
    cells = winning_cells()
    next(c for c in cells if c["policy"] == "tcn" and c["cost_per_side_bps"] == "10")[
        "final_nav"
    ] = "1"
    assert study.primary_verdict(cells) == "rejected"
    cells = winning_cells()
    next(
        c
        for c in cells
        if c["policy"] == "tcn_beta_matched_quarter_ew_cash" and c["cost_per_side_bps"] == "10"
    )["status"] = "input_unavailable"
    assert study.primary_verdict(cells) == "input_unavailable"


def test_restored_beta_no_search_fraction_or_bracket(campaign, monkeypatch):
    inputs = campaign.prepared[0]
    state = campaign.bundle["states"]["tcn"]
    weights = study.infer(
        "tcn", state, study.ChannelScaler.restore(campaign.bundle["scaler"]), inputs.x
    )
    matched = study.train_match(inputs, weights)

    def no_search(*args, **kwargs):
        raise AssertionError("new matching search")

    monkeypatch.setattr(study.prior, "match_beta", no_search)
    restored = study.restore_match(study.matching_payload(matched))
    assert study.train_match(inputs, weights, restored=restored) == restored


def test_byte_change_bound_result_and_model_rejected(campaign):
    result = complete_mock_attempt(campaign)
    pin = study.digest(study.encode(result))
    raw = (campaign.output / "numeric-models.json").read_bytes()
    (campaign.output / "numeric-models.json").write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="model_hash"):
        study.readback(
            campaign.root, campaign.market, campaign.pin, result_sha256=pin, deadline=float("inf")
        )


def test_failed_private_scope_not_promotion_or_gpu_utilization():
    config = study.configuration()
    assert config["budget"]["family_seconds"] == 600
    assert config["budget"]["actual_fits"] == 3
    assert "src/thericher_v2/research/engine_research_agent.py" in study.CODE
    assert "src/thericher_v2/research/validation.py" in study.CODE
    assert not config["scope"]["promotion"]
