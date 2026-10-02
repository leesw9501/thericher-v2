from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import urllib.request
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from test_kis_paper_portfolio_budget_integration import ENV, NOW
from test_kis_paper_portfolio_budget_integration import Broker as PortfolioBroker
from thericher_v2.contracts import decision_instrument_binding_ref, decision_target_binding_ref
from thericher_v2.execution.kis_paper_canary import KisPaperCanaryStateStore
from thericher_v2.execution.kis_readonly import KisPaperConfig

SPEC = importlib.util.spec_from_file_location(
    "qqq_unit_runner",
    Path(__file__).resolve().parents[1] / "scripts" / "run_kis_paper_qqq_unit_cycle.py",
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)
NAMED_CYCLE = "synthetic-named-cycle"
CYCLE = runner._canonical_cycle_id(NAMED_CYCLE)
D = Decimal


def forbidden(*args, **kwargs):
    raise AssertionError("unexpected external or credential IO")


class GuardedEnvironment(Mapping):
    def __init__(self, values, *, all_values=False):
        self.values, self.all_values, self.reads = values, all_values, []

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)

    def __getitem__(self, key):
        self.reads.append(key)
        if self.all_values or key.upper().startswith("KIS_"):
            raise AssertionError("forbidden environment value read")
        return self.values[key]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    environment = GuardedEnvironment(
        {
            "PATH": "synthetic-path",
            "THERICHER_HOST_MODEL_ARTIFACT_ROOT": str(tmp_path / "external-artifacts"),
            "KIS_LIVE_APP_KEY": "private-live-key",
            "kis_live_app_secret": "private-live-secret",
            "KIS_PAPER_APP_KEY": "inherited-private-paper-key",
            "KIS_PAPER_BASE_URL": "private-route",
        }
    )
    monkeypatch.setattr(runner, "os", SimpleNamespace(environ=environment))
    monkeypatch.setattr(
        runner,
        "subprocess",
        SimpleNamespace(
            run=forbidden,
            PIPE=subprocess.PIPE,
            DEVNULL=subprocess.DEVNULL,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    monkeypatch.setattr(runner, "load_kis_paper_config", forbidden)
    monkeypatch.setattr(runner, "load_kis_paper_config_from_environment", forbidden)
    monkeypatch.setattr(runner, "KisPaperCanaryClient", forbidden)
    return environment


@pytest.mark.parametrize("mode", ["host", "worker", "cli"])
def test_preview_has_no_environment_file_broker_or_docker_io(monkeypatch, mode, capsys):
    monkeypatch.setattr(
        runner,
        "os",
        SimpleNamespace(
            environ=GuardedEnvironment({"KIS_LIVE_APP_KEY": "private"}, all_values=True),
        ),
    )
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(runner.budget, "run_kis_paper_budget_strategy", forbidden)
    monkeypatch.setattr(runner, "_inspect_cycle", forbidden)
    if mode == "host":
        result = runner.run(project_root=Path("unused"), execute=False, cycle_id=NAMED_CYCLE)
    elif mode == "worker":
        result = runner.run_worker(cycle_id=CYCLE, execute=False)
    else:
        assert runner.main(["--cycle-id", NAMED_CYCLE]) == 0
        result = json.loads(capsys.readouterr().out)
    assert result["status"] == "preview"
    assert result["visits_completed"] == 0
    assert NAMED_CYCLE not in json.dumps(result)


def complete_result(cycle_id=CYCLE, visits=2):
    return runner._summary(
        cycle_id,
        "unit_cycle_complete",
        visits,
        runner._CycleView("complete", 1, 1, "sha256:" + "a" * 64),
    )


@pytest.fixture
def dispatch(monkeypatch, tmp_path):
    calls, loads = [], []
    config = KisPaperConfig(*ENV.values())

    def load(path):
        loads.append(path)
        return config

    def run(command, **kwargs):
        calls.append((command, {**kwargs, "env": dict(kwargs["env"])}))
        if command[:3] == ["docker", "container", "inspect"]:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0, stdout=json.dumps(complete_result()))

    monkeypatch.setattr(runner, "load_kis_paper_config", load)
    monkeypatch.setattr(runner.subprocess, "run", run)
    return (
        calls,
        loads,
        dict(project_root=tmp_path / "repo", execute=True, cycle_id=NAMED_CYCLE, visits=24),
    )


def test_host_filters_live_names_before_values_and_uses_named_paper_loader(dispatch, isolated):
    calls, loads, args = dispatch
    result = runner.run(**args)
    assert result == complete_result()
    assert not any(key.upper().startswith("KIS_") for key in isolated.reads)
    assert loads == [args["project_root"].resolve() / ".env"]
    assert not any(key.upper().startswith("KIS_") for key in calls[0][1]["env"])
    command, options = calls[1]
    assert options["timeout"] == 1350
    assert options["stdout"] == subprocess.PIPE and options["stderr"] == subprocess.DEVNULL
    assert command[command.index("--env-file") + 1] == str(loads[0].with_name(".env.example"))
    assert command[command.index("--profile") + 1] == "kis-paper-daily-spy-session"
    assert command.count("kis-paper-daily-spy-session") == 2
    assert command[command.index("--cycle-id") + 1] == CYCLE
    assert "1260s" in command and "--worker" in command and "--execute" in command
    assert command[command.index("--visits") + 1] == "24"
    assert "--no-deps" in command and "never" in command
    assert {k: v for k, v in options["env"].items() if k.startswith("KIS_")} == ENV
    assert NAMED_CYCLE not in " ".join(command)
    assert all(value not in " ".join(command) for value in ENV.values())
    assert "SPY" not in json.dumps(result)


def test_live_mode_stops_before_paper_loader_or_dispatch(monkeypatch):
    environment = GuardedEnvironment({"THERICHER_MODE": "KIS_LIVE", "KIS_LIVE_KEY": "private"})
    monkeypatch.setattr(runner, "os", SimpleNamespace(environ=environment))
    result = runner.run(project_root=Path("unused"), execute=True, cycle_id=NAMED_CYCLE)
    assert result["status"] == "dispatch_unavailable"
    assert environment.reads == ["THERICHER_MODE"]


def test_present_cycle_container_is_not_adopted_or_relaunched(dispatch, monkeypatch):
    calls, loads, args = dispatch
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    assert runner.run(**args)["status"] == "owned_container_present"
    assert loads == [] and calls == []


@pytest.mark.parametrize(
    "variant",
    [
        "empty",
        "private",
        "wrong_cycle",
        "buy_only",
        "zero_visits",
        "extra_field",
        "wrong_instrument",
        "wrong_exit",
        "bool_count",
        "preview",
    ],
)
def test_task_exit_or_invalid_summary_cannot_claim_roundtrip(dispatch, monkeypatch, variant):
    _, _, args = dispatch
    payload, exit_code = complete_result(), 0
    if variant == "empty":
        output = ""
    elif variant == "private":
        output = "private broker error secret=synthetic-secret"
    else:
        if variant == "wrong_cycle":
            payload["owned_cycle_ref"] = "sha256:" + "f" * 64
        elif variant == "buy_only":
            payload["closed_sell_fill_count"] = 0
        elif variant == "zero_visits":
            payload["visits_completed"] = 0
        elif variant == "extra_field":
            payload["price"] = "private"
        elif variant == "wrong_instrument":
            payload["instrument"] = "SPY"
        elif variant == "wrong_exit":
            exit_code = 21
        elif variant == "bool_count":
            payload["closed_sell_fill_count"] = True
        elif variant == "preview":
            payload = runner._summary(CYCLE, "preview")
        output = json.dumps(payload)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda command, **kw: SimpleNamespace(
            returncode=1 if command[1] == "container" else exit_code,
            stdout=output,
        ),
    )
    result = runner.run(**args)
    assert result["status"] == "worker_failed"
    assert "private" not in json.dumps(result) and "synthetic-secret" not in json.dumps(result)


@pytest.mark.parametrize("foreign", [False, True])
def test_timeout_stops_only_exact_invocation_container_and_retains_cycle(
    dispatch, monkeypatch, foreign
):
    calls, _, args = dispatch
    invocation = None
    owned_id = "d" * 64

    def run(command, **kwargs):
        nonlocal invocation
        calls.append((command, kwargs))
        if command[1] == "compose":
            invocation = command[command.index("--label") + 1].split("=", 1)[1]
            raise subprocess.TimeoutExpired(command, 1350, output="private error")
        if "--format" in command:
            assert ".Config.Env" not in " ".join(command)
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "id": owned_id,
                        "invocation": "foreign" if foreign else invocation,
                    }
                ),
            )
        return SimpleNamespace(returncode=1 if command[1] == "container" else 0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    first = runner.run(**args)
    second = runner.run(**args)
    assert first["owned_cycle_ref"] == second["owned_cycle_ref"] == runner._cycle_ref(CYCLE)
    assert first["status"] == second["status"] == "worker_timeout"
    assert first["container_stop_status"] == ("ownership_unconfirmed" if foreign else "confirmed")
    commands = [c for c, _ in calls]
    launches = [c for c in commands if c[1] == "compose"]
    assert all(c[c.index("--cycle-id") + 1] == CYCLE for c in launches)
    stops = [c for c in commands if c[1] == "stop"]
    assert stops == ([] if foreign else [["docker", "stop", "--time", "30", owned_id]] * 2)
    assert "private" not in json.dumps(first)


class Broker(PortfolioBroker):
    def __init__(self, root):
        super().__init__(root)
        self.reject = False
        self.unknown_sell = False

    def submit_limit(self, intent, **kwargs):
        binding = runner.budget._load_binding(self.root)
        # Reuse the synthetic broker while selecting the caller's opaque cycle.
        original = binding["qqq"]["cycle_id"]
        if original != "unit-cycle":
            return self._submit_selected(intent, binding)
        return super().submit_limit(intent, **kwargs)

    def _submit_selected(self, intent, binding):
        state = KisPaperCanaryStateStore(self.root / (intent.run_id + ".json")).read()
        assert state.phase == "submission_started"
        assert intent.symbol == "QQQ" and intent.exchange == "NASD" and intent.quantity == 1
        rows = runner.budget._orders(binding, CYCLE)
        assert rows[-1]["intent_ref"] == intent.fingerprint
        projection = runner.budget.project_budget(self.root, binding, qqq_cycle_id=CYCLE)
        assert projection.entry_cost + projection.reserved_buys <= D(binding["allocated_usd"])
        self.submits.append(intent)
        if self.reject:
            return False, None
        filled = (intent.quantity * self.fill_fraction).to_integral_value(rounding="ROUND_FLOOR")
        self.orders[intent.run_id] = {
            "intent": intent,
            "filled": filled,
            "remaining": intent.quantity - filled,
            "id": str(100 + len(self.submits)),
            "cancelled": False,
        }
        if self.unknown or (self.unknown_sell and intent.side == "sell"):
            from thericher_v2.execution.kis_paper_canary import KisPaperCanaryError

            raise KisPaperCanaryError("submit_transport_unknown")
        return True, self.orders[intent.run_id]["id"]


@pytest.fixture
def worker(monkeypatch, tmp_path):
    root = tmp_path / "synthetic-private"
    client, created, sleeps = Broker(root), [], []
    elapsed = 0

    def make_client(**kwargs):
        created.append(kwargs)
        return client

    def sleep(seconds):
        nonlocal elapsed
        sleeps.append(seconds)
        elapsed += seconds
        client.now += timedelta(seconds=seconds)

    monkeypatch.setattr(runner, "KisPaperCanaryClient", make_client)
    monkeypatch.setattr(
        runner,
        "load_kis_paper_config_from_environment",
        lambda environment: KisPaperConfig(*ENV.values()),
    )
    monkeypatch.setattr(runner, "UrllibKisPaperCanaryTransport", lambda: "synthetic-transport")
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: elapsed, sleep=sleep))
    args = dict(
        cycle_id=CYCLE,
        execute=True,
        environment=ENV,
        state_root=root,
        runtime_projection_path=tmp_path / "runtime.json",
        paper_account_snapshot_path=tmp_path / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        execution_control_path=tmp_path / "controls.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        clock=lambda: client.now,
    )
    return client, created, sleeps, args


def test_worker_one_client_buy_then_exact_sell_and_same_cycle_never_rebuys(worker):
    client, created, sleeps, args = worker
    result = runner.run_worker(**args)
    assert result == complete_result()
    assert len(created) == 1 and sleeps == [15]
    assert [intent.side for intent in client.submits] == ["buy", "sell"]
    binding = runner.budget._load_binding(args["state_root"])
    assert D(binding["allocated_usd"]) == D(binding["basis_usd"]) * D("0.10")
    assert (
        runner.budget.project_budget(args["state_root"], binding, qqq_cycle_id=CYCLE).quantity == 0
    )
    assert runner.run_worker(**args)["status"] == "unit_cycle_complete"
    assert len(client.submits) == 2
    assert all(value not in json.dumps(result) for value in ENV.values())
    assert all(intent.run_id not in json.dumps(result) for intent in client.submits)


def test_buy_complete_is_not_a_roundtrip(worker):
    client, _, sleeps, args = worker
    result = runner.run_worker(**args, visits=1)
    assert result["status"] == "visit_budget_exhausted"
    assert result["replay_status"] == "exit_ready"
    assert (result["closed_buy_fill_count"], result["closed_sell_fill_count"]) == (1, 0)
    assert [intent.side for intent in client.submits] == ["buy"] and sleeps == []
    assert runner._exit_code(result) != 0


def test_post_visit_readback_locks_before_clock_under_compatible_writer(worker, monkeypatch):
    client, created, sleeps, args = worker
    original_core = runner.budget.run_kis_paper_budget_strategy
    original_lock = runner.budget.exclusive_kis_paper_canary_state_lock
    original_inspect = runner._inspect_cycle
    ready, update, updated = Event(), Event(), Event()
    post_visit, held, clock_scopes, inspection_scopes = False, [], [], []
    futures = []
    root = args["state_root"].resolve()
    expected = (".session_execution", ".canary_execution")

    def compatible_writer():
        with original_lock(root / expected[0]), original_lock(root / expected[1]):
            ready.set()
            assert update.wait(5), "synthetic writer was not released"
            binding = runner.budget._load_binding(root)
            record = runner.budget._orders(binding, CYCLE)[-1]
            state = runner.budget._state(root, record, symbol="QQQ", exchange="NASD")
            client.now += timedelta(seconds=1)
            runner.budget._atomic_json(
                root / (record["run_id"] + ".json"), replace(state, updated_at=client.now).to_dict()
            )
            updated.set()

    @contextmanager
    def observed_lock(path):
        if post_visit and path.name == expected[0]:
            update.set()
        assert path.name not in held, "receipt loader recursively acquired a core lock"
        with original_lock(path):
            held.append(path.name)
            try:
                yield
            finally:
                assert held.pop() == path.name

    def clock():
        if post_visit:
            clock_scopes.append(tuple(held))
        return client.now

    def inspect(*positional):
        if post_visit:
            inspection_scopes.append(tuple(held))
            # The old unlocked path samples an older clock before this update.
            update.set()
            assert updated.wait(5), "synthetic writer did not update the referenced state"
        return original_inspect(*positional)

    monkeypatch.setattr(runner.budget, "exclusive_kis_paper_canary_state_lock", observed_lock)
    monkeypatch.setattr(runner, "_inspect_cycle", inspect)
    with ThreadPoolExecutor(max_workers=1) as pool:

        def core(**kwargs):
            nonlocal post_visit
            outcome = original_core(**kwargs)
            assert outcome.status == "order_complete", outcome.safe_payload()
            post_visit = True
            futures.append(pool.submit(compatible_writer))
            assert ready.wait(5), "synthetic writer did not acquire the shared locks"
            return outcome

        monkeypatch.setattr(runner.budget, "run_kis_paper_budget_strategy", core)
        try:
            result = runner.run_worker(**{**args, "clock": clock}, visits=1)
        finally:
            update.set()
            for future in futures:
                future.result(timeout=5)

    assert result["status"] == "visit_budget_exhausted"
    assert result["replay_status"] == "exit_ready" and result["closed_buy_fill_count"] == 1
    assert result["closed_sell_fill_count"] == 0
    assert clock_scopes == inspection_scopes == [expected]
    assert len(client.submits) == len(created) == 1 and sleeps == []


def test_pending_unknown_identity_is_reconciled_without_new_receipt_or_repost(worker, monkeypatch):
    client, _, sleeps, args = worker
    client.unknown = True
    loaded = []
    original = runner._receipt

    def receipt(*positional):
        loaded.append(1)
        return original(*positional)

    monkeypatch.setattr(runner, "_receipt", receipt)
    first = runner.run_worker(**args, visits=3)
    second = runner.run_worker(**args, visits=2)
    assert first["status"] == second["status"] == "visit_budget_exhausted"
    assert len(client.submits) == 1 and loaded == [1] and sleeps == [15, 15, 15]
    state = KisPaperCanaryStateStore(
        args["state_root"] / (client.submits[0].run_id + ".json")
    ).read()
    assert state.phase == "outcome_unknown" and state.intent.side == "buy"


def test_unknown_sell_does_not_mean_flat_or_repeat_post(worker):
    client, _, _, args = worker
    client.unknown_sell = True
    result = runner.run_worker(**args, visits=4)
    assert result["status"] == "visit_budget_exhausted"
    assert result["replay_status"] == "pending"
    assert result["closed_buy_fill_count"] == 1 and result["closed_sell_fill_count"] == 0
    assert [intent.side for intent in client.submits] == ["buy", "sell"]


def test_foreign_qqq_inventory_is_not_adopted_as_owned_buy(worker):
    client, _, _, args = worker
    client.foreign["QQQ"] = D(1)
    result = runner.run_worker(**args)
    assert result["status"] == "no_intent" and result["replay_status"] == "entry_ready"
    assert result["closed_buy_fill_count"] == result["closed_sell_fill_count"] == 0
    assert client.submits == []


def test_rejected_entry_finalizes_without_rebuy(worker):
    client, _, _, args = worker
    client.reject = True
    result = runner.run_worker(**args)
    assert result["status"] == "unit_cycle_not_completed"
    assert result["replay_status"] == "entry_finalized"
    assert runner.run_worker(**args)["status"] == "unit_cycle_not_completed"
    assert len(client.submits) == 1


def test_canceled_zero_fill_sell_does_not_complete_cycle(worker):
    client, _, _, args = worker
    assert runner.run_worker(**args, visits=1)["replay_status"] == "exit_ready"
    client.fill_fraction = D(0)
    assert runner.run_worker(**args, visits=1)["replay_status"] == "pending"
    client.now += timedelta(minutes=6)
    canceled = runner.run_worker(**args, visits=1)
    assert client.cancels and canceled["status"] != "unit_cycle_complete"
    assert canceled["closed_sell_fill_count"] == 0
    continued = runner.run_worker(**args, visits=2)
    assert continued["status"] != "unit_cycle_complete"
    assert continued["closed_buy_fill_count"] == 1 and continued["closed_sell_fill_count"] == 0


def test_missing_exact_sell_state_cannot_attest_flat(worker):
    client, _, _, args = worker
    assert runner.run_worker(**args)["status"] == "unit_cycle_complete"
    (args["state_root"] / (client.submits[-1].run_id + ".json")).unlink()
    assert runner.run_worker(**args)["status"] == "recovery_required"
    assert len(client.submits) == 2


def test_receipts_bind_exact_owned_projection_and_qqq_not_market_data(worker):
    _, _, _, args = worker
    enter = runner._receipt(args["state_root"], CYCLE, NOW)
    assert enter == runner._receipt(args["state_root"], CYCLE, NOW)
    assert enter.decision_class == "enter" and enter.input_status == "ready"
    assert enter.instrument_binding_ref == decision_instrument_binding_ref(
        symbol="QQQ",
        market="US",
        decision_class="enter",
    )
    assert enter.target_binding_ref == decision_target_binding_ref(
        symbol="QQQ",
        market="US",
        decision_class="enter",
        target_exposure=D("0.10"),
    )
    assert runner.run_worker(**args, visits=1)["replay_status"] == "exit_ready"
    exit_receipt = runner._receipt(args["state_root"], CYCLE, NOW)
    assert exit_receipt.decision_class == "exit"
    assert exit_receipt.campaign_ref == enter.campaign_ref
    assert exit_receipt.model_ref == enter.model_ref
    assert exit_receipt.input_manifest_ref != enter.input_manifest_ref
    assert exit_receipt.proposal_ref != enter.proposal_ref
    assert all(value not in exit_receipt.canonical_json() for value in ENV.values())


def test_worker_wall_time_bound_preserves_buy_without_claiming_completion(worker, monkeypatch):
    client, created, _, args = worker
    elapsed = 0

    def sleep(seconds):
        nonlocal elapsed
        assert seconds == 15
        elapsed = 1200

    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: elapsed, sleep=sleep))
    result = runner.run_worker(**args)
    assert result["status"] == "worker_time_budget_exhausted"
    assert result["visits_completed"] == 1 and result["closed_sell_fill_count"] == 0
    assert len(created) == len(client.submits) == 1


def test_full_24_visit_bound_keeps_one_client_and_unknown_identity(worker):
    client, created, sleeps, args = worker
    client.unknown = True
    result = runner.run_worker(**args, visits=24)
    assert result["status"] == "visit_budget_exhausted" and result["visits_completed"] == 24
    assert len(created) == len(client.submits) == 1 and sleeps == [15] * 23


def test_core_call_finishing_after_worker_budget_is_not_success(worker, monkeypatch):
    client, _, _, args = worker
    elapsed = 0
    original = runner.budget.run_kis_paper_budget_strategy

    def core(**kwargs):
        nonlocal elapsed
        outcome = original(**kwargs)
        elapsed = 1200
        return outcome

    monkeypatch.setattr(runner.budget, "run_kis_paper_budget_strategy", core)
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: elapsed, sleep=forbidden))
    result = runner.run_worker(**args)
    assert result["status"] == "worker_time_budget_exhausted"
    assert result["visits_completed"] == 1 and len(client.submits) == 1


def test_worker_live_mode_reads_no_credential_values(monkeypatch):
    environment = GuardedEnvironment({"THERICHER_MODE": "kis_live", "KIS_LIVE_KEY": "private"})
    assert (
        runner.run_worker(cycle_id=CYCLE, execute=True, environment=environment)["status"]
        == "recovery_required"
    )
    assert environment.reads == ["THERICHER_MODE"]


def test_different_cycle_cannot_adopt_existing_owned_buy(worker):
    client, _, _, args = worker
    assert runner.run_worker(**args, visits=1)["replay_status"] == "exit_ready"
    result = runner.run_worker(**{**args, "cycle_id": runner._canonical_cycle_id("foreign-cycle")})
    assert result["status"] == "recovery_required" and len(client.submits) == 1


def test_worker_configuration_exception_never_outputs_raw_error(monkeypatch, capsys):
    def load(environment):
        raise ValueError("private-account=12345678 price=600 synthetic-secret")

    monkeypatch.setattr(runner, "load_kis_paper_config_from_environment", load)
    assert runner.main(["--worker", "--execute", "--cycle-id", CYCLE]) == 20
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "recovery_required"
    assert "private" not in captured.out and "12345678" not in captured.out
    assert "synthetic-secret" not in captured.out and captured.err == ""


@pytest.mark.parametrize("visits", [0, 25, True, 1.5])
def test_visit_bounds_rejected_before_io(visits):
    with pytest.raises(ValueError, match="invalid_visit_bound"):
        runner.run(project_root=Path("unused"), execute=True, cycle_id=NAMED_CYCLE, visits=visits)
    with pytest.raises(ValueError, match="invalid_visit_bound"):
        runner.run_worker(cycle_id=CYCLE, execute=True, visits=visits)


@pytest.mark.parametrize(
    "argv",
    [[], ["--cycle-id", "private/value"], ["--cycle-id", NAMED_CYCLE, "--visits", "private"]],
)
def test_cli_errors_are_categorical_without_echoing_private_input(argv, capsys):
    assert runner.main(argv) == 20
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "arguments_unavailable"
    assert captured.err == "" and "private" not in captured.out and NAMED_CYCLE not in captured.out
