from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_causal_volume_sequence import pair, projection, synthetic_rows
from thericher_v2.research import causal_volume_sequence as v

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "volume_test_runner", SCRIPTS / "run_firstrate_causal_volume_sequence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_plan_no_io_network_credentials_or_fit(runner, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("plan performed I/O, networking, credential access or fit")

    for name in (
        "freeze",
        "compute",
        "check_runtime",
        "check_pins",
        "load_source_cases",
        "register",
    ):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(runner.os, "getenv", forbidden)
    monkeypatch.setattr(sys, "argv", ["runner"])
    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "plan",
        "study": runner.STUDY,
        "actual_fits": 0,
        "broker_calls": 0,
    }


def test_contract_freezes_all_axes_formulas_and_runtime(runner):
    plan = runner.contract({})
    assert plan["runtime"] == {
        "python": "3.12.14",
        "torch": "2.7.0+cu128",
        "numpy": "2.5.1",
        "pandas-market-calendars": "5.4.0",
    }
    assert plan["source_sha256"] == runner.smoke.SOURCES
    assert plan["scheduled_date_set_sha256"] == runner.smoke.DATE_HASH
    assert plan["decisions"] == [120, 180, 240, 300]
    assert plan["matrix"]["cells"] == 1
    assert plan["split"] == {
        "TRAIN": 160,
        "embargo": 1,
        "comparison": 90,
        "halves": [45, 45],
        "rule": "shared scheduled chronological dates BEFORE any exclusion",
    }
    assert plan["model"]["epochs"] == 128 and plan["model"]["selection"] == "final_epoch_only"
    assert set(plan["controls"]) == set(v.METHODS[1:])
    assert plan["compute"]["seconds"] == 600
    assert plan["compute"]["cpu"] == 2 and plan["compute"]["memory_bytes"] == 6 * 1024**3
    assert plan["compute"]["image"] == runner.IMAGE
    assert plan["holdout"] == "none" and not plan["paper_input"]


@pytest.mark.parametrize("budget", [0, -1, True, 4 * 1024**3 + 1])
def test_vram_bound_is_new_study_local(runner, budget):
    with pytest.raises(v.VolumeFault, match="VRAM_contract"):
        runner.contract({}, budget)


def test_freeze_before_source_values_with_exact_code_snapshots_and_registry_recovery(
    runner,
    monkeypatch,
    tmp_path,
):
    root = tmp_path / "study"
    attempts = []
    monkeypatch.setattr(runner, "check_runtime", lambda *args: None)
    monkeypatch.setattr(runner, "check_pins", lambda *args: ())
    monkeypatch.setattr(runner, "load_source_cases", lambda *args: pytest.fail("source values"))

    def register(plan, actual_root, artifact_base):
        assert actual_root == root
        assert json.loads((root / "contract.json").read_bytes()) == plan
        assert all(
            runner.smoke.file_hash(root / "code" / relative) == pin
            for relative, pin in plan["code_sha256"].items()
        )
        attempts.append((root / "contract.json").read_bytes())
        if len(attempts) == 1:
            raise RuntimeError("synthetic registry contention")
        return SimpleNamespace(record_sha256="sha256:" + "b" * 64)

    monkeypatch.setattr(runner, "register", register)
    args = (root, tmp_path, tmp_path, tmp_path, tmp_path)
    with pytest.raises(RuntimeError, match="registry contention"):
        runner.freeze(*args)
    result = runner.freeze(*args)
    assert result["actual_fits"] == 0 and attempts[0] == attempts[1]
    (root / "code" / runner.CODE[-1]).write_bytes(b"modified")
    with pytest.raises(v.VolumeFault, match="frozen_code_changed"):
        runner.freeze(*args)


def test_check_pins_rejects_contract_before_source_reader(runner, monkeypatch):
    plan = runner.contract({})
    plan["model"]["epochs"] = 127
    monkeypatch.setattr(runner.smoke, "check_metadata", lambda *args: pytest.fail("metadata"))
    with pytest.raises(v.VolumeFault, match="contract_changed"):
        runner.check_pins(plan, None, None, None)


def test_inherited_loader_and_metadata_are_reused_not_reimplemented(runner):
    assert runner.load_source_cases is runner.baseline.load_source_cases
    assert runner.smoke.check_metadata.__module__ == "run_firstrate_forward_variance_smoke"
    assert set(runner.baseline.CODE).issubset(runner.CODE)


def synthetic_compute(runner, monkeypatch):
    torch = pytest.importorskip("torch", reason="synthetic GRU replay requires optional PyTorch")

    dates, rows = synthetic_rows()
    by_day = {day: tuple(row for row in rows if row.session_date == day) for day in dates}
    sessions = tuple(pair(day, minutes=1)[1] for day in dates)
    grouped = {symbol: {day: () for day in dates} for symbol in v.SYMBOLS}
    train, _ = v.split_records(rows, dates)
    stats = v.train_statistics(train)
    _, z, y, weights = v.training_arrays(train, stats)
    state = {
        "statistics": stats,
        "ridge": v.fit_ridge(z, y, weights),
        "gru": {
            name: value.detach().tolist() for name, value in v._model(torch).state_dict().items()
        },
    }
    monkeypatch.setattr(runner, "check_runtime", lambda *args: None)
    monkeypatch.setattr(runner, "check_pins", lambda *args: ())
    monkeypatch.setattr(runner, "load_source_cases", lambda *args: (sessions, grouped))
    monkeypatch.setattr(
        v, "records_from_pair", lambda bars, session: by_day[session.open_ts.date()]
    )
    return dates, by_day, state


def test_bounded_adapter_single_train_dispatch_and_all_ro_replay(runner, monkeypatch):
    dates, _, state = synthetic_compute(runner, monkeypatch)
    fits = []

    def fit(train, *, deadline, vram_bytes):
        fits.append(tuple(row.session_date for row in train))
        assert vram_bytes == runner.contract({})["compute"]["vram_bytes"]
        return state

    monkeypatch.setattr(v, "fit_models", fit)
    args = (runner.contract({}), None, None, None, float("inf"))
    result, models = runner.compute(*args)
    assert len(fits) == 1 and len(fits[0]) == 1280 and max(fits[0]) == dates[159]
    assert result["scheduled"] == {"TRAIN": 160, "embargo": 1, "comparison": 90, "keys": 2008}
    assert result["mutation_checks"] == {
        "prefix_future_removal": 1004,
        "future_support": 1004,
        "future_value": 1004,
        "target_blind_forecast": 720,
    }
    monkeypatch.setattr(v, "fit_models", lambda *a, **k: pytest.fail("refit"))
    actual, restored = runner.compute(*args, models=json.loads(json.dumps(models)))
    assert actual == result and restored == models


def test_comparison_target_mutation_does_not_change_train_model_or_forecasts(runner, monkeypatch):
    from dataclasses import replace

    dates, by_day, state = synthetic_compute(runner, monkeypatch)
    monkeypatch.setattr(v, "fit_models", lambda *a, **k: state)
    args = (runner.contract({}), None, None, None, float("inf"))
    original, _ = runner.compute(*args)
    for day in dates[161:]:
        by_day[day] = tuple(replace(row, target=row.target * 1000) for row in by_day[day])
    changed, models = runner.compute(*args, models=state)
    assert models == state
    for field in ("TRAIN", "inputs", "forecasts"):
        assert original["commitments"][field] == changed["commitments"][field]
    assert original["commitments"]["targets"] != changed["commitments"]["targets"]
    assert original["comparison"] != changed["comparison"]


def test_read_replay_anchors_result_before_weights_and_rejects_weight_corruption(runner, tmp_path):
    models = {"gru": {"head.bias": [0.5]}}
    result = {"model_sha256": runner.smoke.digest(runner.smoke.encode(models))}
    runner.smoke.write_once(tmp_path / "models.json", models)
    runner.smoke.write_once(tmp_path / "result.json", result)
    pin = runner.smoke.file_hash(tmp_path / "result.json")
    assert runner.read_replay(tmp_path, pin) == (models, result)
    with pytest.raises(v.VolumeFault, match="exact_result_pin_required"):
        runner.read_replay(tmp_path, "sha256:" + "0" * 64)
    (tmp_path / "models.json").write_text('{"gru":{"head.bias":[0.6]}}', encoding="ascii")
    with pytest.raises(v.VolumeFault, match="model_changed"):
        runner.read_replay(tmp_path, pin)


def test_input_commitment_projection_has_no_target_or_forward_support(runner):
    _, rows = synthetic_rows()
    projected = runner.input_projection(rows)
    assert projected == tuple(map(projection, rows))
    assert all(row.target is None and row.target_m1_count == 0 for row in projected)


def test_expired_budget_never_dispatches_fit(runner, monkeypatch):
    synthetic_compute(runner, monkeypatch)
    monkeypatch.setattr(v, "fit_models", lambda *a, **k: pytest.fail("fit after deadline"))
    with pytest.raises(v.VolumeFault, match="compute_stop"):
        runner.compute(runner.contract({}), None, None, None, 0)


def test_missing_torch_skips_only_synthetic_compute_not_plan(runner, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(pytest.skip.Exception):
        synthetic_compute(runner, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["runner"])
    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out)["actual_fits"] == 0


@pytest.fixture
def recovery_case(runner, monkeypatch, tmp_path):
    base, root = tmp_path / "artifacts", tmp_path / "artifacts/research/study"
    root.mkdir(parents=True)
    market = tmp_path / "market"
    market.mkdir()
    lineage, normalization = tmp_path / "lineage.json", tmp_path / "normalization.json"
    lineage.write_bytes(b"synthetic lineage")
    normalization.write_bytes(b"synthetic normalization")
    pins = {}
    for relative in runner.CODE:
        path = root / "code" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (runner.REPO / relative).read_bytes()
        if relative == runner.CODE[-1]:
            raw += b"\n# Synthetic prior frozen runner, not the current recovery runner.\n"
        path.write_bytes(raw)
        pins[relative] = runner.smoke.digest(raw)
    plan = runner.contract(pins)
    runner.smoke.write_once(root / "contract.json", plan)
    contract_pin = runner.smoke.file_hash(root / "contract.json")
    models = {"gru": {"head.bias": [0.5]}}
    result = {
        "contract_sha256": contract_pin,
        "study": runner.STUDY,
        "grade": plan["grade"],
        "status": "non_promoting_completed",
        "recipe_actual_fits": plan["model"]["fits"],
        "holdout": False,
        "paper_input": False,
        "broker_calls": 0,
        "model_sha256": runner.smoke.digest(runner.smoke.encode(models)),
    }
    runner.smoke.write_once(root / "result.json", result)
    runner.smoke.write_once(root / "models.json", models)
    runner.smoke.write_once(
        root / "attempt.json",
        {
            "contract_sha256": contract_pin,
            "started_at": "2026-10-08T00:00:00+00:00",
        },
    )
    result_pin = runner.smoke.file_hash(root / "result.json")
    monkeypatch.setattr(runner, "recovery_runtime", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "replay_frozen",
        lambda *args: {
            "status": "verified_all_ro_no_refit",
            "verification_fits": 0,
            "model_sha256": result["model_sha256"],
        },
    )
    return SimpleNamespace(
        root=root,
        base=base,
        market=market,
        lineage=lineage,
        normalization=normalization,
        plan=plan,
        result=result,
        contract_pin=contract_pin,
        result_pin=result_pin,
        args=(root, market, lineage, normalization, base, contract_pin, result_pin),
    )


def test_recovery_uses_old_snapshots_and_appends_exact_outcome_idempotently(
    runner,
    recovery_case,
    monkeypatch,
):
    case = recovery_case
    assert case.plan["code_sha256"][runner.CODE[-1]] != runner.smoke.file_hash(
        runner.REPO / runner.CODE[-1]
    )
    runner.register(case.plan, case.root, case.base)
    before = {path: path.read_bytes() for path in case.root.rglob("*") if path.is_file()}
    events = []
    original_append = runner.register_campaign_outcome

    def replay(*args):
        events.append("independent_replay")
        return {
            "status": "verified_all_ro_no_refit",
            "verification_fits": 0,
            "model_sha256": case.result["model_sha256"],
        }

    def append(**kwargs):
        events.append("append")
        assert kwargs["contract_hash"] == case.contract_pin
        assert kwargs["outcome_reference_sha256"] == case.result_pin
        return original_append(**kwargs)

    monkeypatch.setattr(runner, "replay_frozen", replay)
    monkeypatch.setattr(runner, "register_campaign_outcome", append)
    for name in ("freeze", "compute", "register"):
        monkeypatch.setattr(runner, name, lambda *a, **k: pytest.fail("refit/refreeze"))
    first = runner.recover(*case.args, time.monotonic() + 600)
    second = runner.recover(*case.args, time.monotonic() + 600)
    assert first == second and first["verification_fits"] == 0
    assert events == ["independent_replay", "append", "independent_replay", "append"]
    assert before == {path: path.read_bytes() for path in case.root.rglob("*") if path.is_file()}
    records = [
        json.loads(line)
        for path in (case.base / "_control/ledger").glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert [item["record_type"] for item in records].count("campaign_outcome") == 1


@pytest.mark.parametrize(
    "fault", ["contract_pin", "result_pin", "model", "snapshot", "attempt", "link"]
)
def test_recovery_rejects_unanchored_or_modified_evidence_before_child(
    runner,
    recovery_case,
    monkeypatch,
    fault,
):
    case, args = recovery_case, list(recovery_case.args)
    if fault == "contract_pin":
        args[5] = "sha256:" + "0" * 64
    elif fault == "result_pin":
        args[6] = "sha256:" + "0" * 64
    elif fault == "model":
        (case.root / "models.json").write_text('{"gru": {"head.bias": [0.6]}}')
    elif fault == "snapshot":
        (case.root / "code" / runner.CODE[-1]).write_bytes(b"modified")
    elif fault == "attempt":
        (case.root / "attempt.json").write_text('{"contract_sha256": "wrong"}')
    else:
        original = Path.is_symlink
        linked = case.root / "code"
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == linked or original(path))
    monkeypatch.setattr(
        runner, "replay_frozen", lambda *a: pytest.fail("child with invalid evidence")
    )
    monkeypatch.setattr(runner, "register_campaign_outcome", lambda **k: pytest.fail("append"))
    with pytest.raises(v.VolumeFault):
        runner.recover(*args, time.monotonic() + 600)


@pytest.mark.parametrize(
    "fault", ["fit_count", "model", "status", "changed_after_replay", "deadline"]
)
def test_recovery_failed_or_changed_replay_never_appends(runner, recovery_case, monkeypatch, fault):
    case = recovery_case

    def replay(*args):
        result = {
            "status": "verified_all_ro_no_refit",
            "verification_fits": 0,
            "model_sha256": case.result["model_sha256"],
        }
        if fault == "fit_count":
            result["verification_fits"] = 1
        elif fault == "model":
            result["model_sha256"] = "sha256:" + "0" * 64
        elif fault == "status":
            result["status"] = "completed"
        elif fault == "changed_after_replay":
            with (case.root / "attempt.json").open("ab") as handle:
                handle.write(b"\n")
        return result

    monkeypatch.setattr(runner, "replay_frozen", replay)
    monkeypatch.setattr(runner, "register_campaign_outcome", lambda **k: pytest.fail("append"))
    deadline = 0 if fault == "deadline" else time.monotonic() + 600
    with pytest.raises(v.VolumeFault):
        runner.recover(*case.args, deadline)


def test_recovery_registry_contention_can_retry_without_refit(runner, recovery_case, monkeypatch):
    case, attempts = recovery_case, []

    def append(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise RuntimeError("synthetic registry contention")
        return SimpleNamespace(record_sha256="sha256:" + "c" * 64)

    monkeypatch.setattr(runner, "register_campaign_outcome", append)
    with pytest.raises(RuntimeError, match="synthetic registry contention"):
        runner.recover(*case.args, time.monotonic() + 600)
    assert runner.recover(*case.args, time.monotonic() + 600)["status"] == "recovered_exact_outcome"
    assert attempts[0] == attempts[1]


@pytest.mark.parametrize("fault", ["none", "network", "cpu", "memory", "writable", "not_Docker"])
def test_recovery_runtime_requires_owned_networkless_bounded_read_only_container(
    runner,
    monkeypatch,
    tmp_path,
    fault,
):
    class RuntimePath:
        def __init__(self, value):
            self.value = value

        def is_file(self):
            return fault != "not_Docker"

        def read_text(self):
            if self.value.endswith("cpu.max"):
                return "max 100000" if fault == "cpu" else "200000 100000"
            return "max" if fault == "memory" else str(6 * 1024**3)

    monkeypatch.setattr(runner, "Path", RuntimePath)
    monkeypatch.setattr(
        runner,
        "os",
        SimpleNamespace(
            name="posix",
            ST_RDONLY=1,
            statvfs=lambda path: SimpleNamespace(f_flag=0 if fault == "writable" else 1),
        ),
    )
    monkeypatch.setattr(
        runner,
        "socket",
        SimpleNamespace(
            if_nameindex=lambda: [(1, "lo"), (2, "eth0")] if fault == "network" else [(1, "lo")],
        ),
    )
    monkeypatch.setattr(runner, "check_runtime", lambda *a: None)
    if fault == "none":
        runner.recovery_runtime(runner.contract({}), (tmp_path,))
    else:
        with pytest.raises(v.VolumeFault):
            runner.recovery_runtime(runner.contract({}), (tmp_path,))


@pytest.mark.parametrize(
    "fault", ["none", "exit", "invalid_json", "too_large", "timeout", "launch"]
)
def test_frozen_replay_subprocess_is_bounded_sanitized_and_structured_only(
    runner,
    tmp_path,
    monkeypatch,
    fault,
):
    expected = {"status": "verified_all_ro_no_refit", "verification_fits": 0, "model_sha256": "pin"}

    def launch(command, **kwargs):
        assert command[1:4] == ["-I", "-B", "-c"]
        assert command[4] == runner.FROZEN_REPLAY_BOOTSTRAP
        assert command[5] == str(tmp_path / "code")
        assert command[7] == "verify" and "run" not in command
        assert kwargs["cwd"] == tmp_path / "code"
        assert 0 < kwargs["timeout"] <= 600
        assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == ""
        assert not any(name.startswith("KIS_") for name in kwargs["env"])
        if fault == "timeout":
            raise subprocess.TimeoutExpired(command, 1, output=b"private error")
        if fault == "launch":
            raise OSError("private error")
        return SimpleNamespace(
            returncode=1 if fault == "exit" else 0,
            stdout=b"x" * 4097
            if fault == "too_large"
            else b"invalid private error"
            if fault == "invalid_json"
            else json.dumps(expected).encode(),
        )

    monkeypatch.setattr(runner.subprocess, "run", launch)
    args = (tmp_path, tmp_path, tmp_path, tmp_path, "contract", "result", time.monotonic() + 600)
    if fault == "none":
        assert runner.replay_frozen(*args) == expected
    else:
        with pytest.raises(v.VolumeFault) as error:
            runner.replay_frozen(*args)
        assert "private error" not in str(error.value)


def test_frozen_bootstrap_loads_original_critical_modules_and_forbids_fit(runner, tmp_path):
    code = tmp_path / "code"
    scripts = code / "scripts"
    research = code / "src/thericher_v2/research"
    scripts.mkdir(parents=True)
    research.mkdir(parents=True)
    (research / "causal_volume_sequence.py").write_text(
        'marker = "original_snapshot"\n'
        'def fit_models(*a, **k): return "fit"\n'
        'def fit_gru(*a, **k): return "fit"\n'
        'def fit_ridge(*a, **k): return "fit"\n',
    )
    (scripts / "torch.py").write_text(
        "from types import SimpleNamespace\n"
        "optim = SimpleNamespace(AdamW=None)\n"
        "cuda = SimpleNamespace(is_available=None)\n",
    )
    (scripts / "run_firstrate_causal_volume_sequence.py").write_text(
        "import json, sys\n"
        "from thericher_v2.research import causal_volume_sequence as volume\n"
        "def main():\n"
        '    assert sys.argv[1] == "verify"\n'
        '    assert volume.marker == "original_snapshot"\n'
        '    for name in ("fit_models", "fit_gru", "fit_ridge"):\n'
        "        try: getattr(volume, name)()\n"
        "        except RuntimeError: pass\n"
        '        else: raise AssertionError("fit not blocked")\n'
        '    print(json.dumps({"status": "verified_all_ro_no_refit", '
        '"verification_fits": 0, "model_sha256": "synthetic"}))\n'
        "    return 0\n",
    )
    result = runner.replay_frozen(
        tmp_path,
        tmp_path,
        tmp_path,
        tmp_path,
        "contract",
        "result",
        time.monotonic() + 30,
    )
    assert result["model_sha256"] == "synthetic" and result["verification_fits"] == 0


@pytest.mark.parametrize("fail", [False, True])
def test_recover_cli_routes_only_recovery_and_suppresses_raw_fault(
    runner, monkeypatch, capsys, fail
):
    base = (
        Path("D:/thericher-v2/model-artifacts")
        if runner.os.name == "nt"
        else Path("/app/model_artifacts")
    )
    root = base / "research" / runner.STUDY
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "recover",
            "--artifact-root",
            str(root),
            "--artifact-base",
            str(base),
            "--market-root",
            str(base),
            "--lineage",
            str(base),
            "--normalization",
            str(base),
            "--contract-sha256",
            "contract-pin",
            "--result-sha256",
            "result-pin",
        ],
    )

    def recover(*args):
        assert args[5:7] == ("contract-pin", "result-pin")
        if fail:
            raise RuntimeError("private source error must not leak")
        return {"status": "recovered_exact_outcome", "verification_fits": 0}

    monkeypatch.setattr(runner, "recover", recover)
    monkeypatch.setattr(runner, "compute", lambda *a: pytest.fail("current-source compute"))
    monkeypatch.setattr(runner, "freeze", lambda *a: pytest.fail("refreeze"))
    monkeypatch.setattr(runner, "register", lambda *a: pytest.fail("new frozen registry entry"))
    assert runner.main() == (1 if fail else 0)
    printed = capsys.readouterr().out
    assert "private source error" not in printed
    result = json.loads(printed)
    assert result["status"] == ("input_unavailable" if fail else "recovered_exact_outcome")
