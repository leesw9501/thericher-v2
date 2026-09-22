from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.data.kis_paper_daily_spy_input import KisPaperDailySpyInput
from thericher_v2.execution import kis_paper_daily_spy_session as session_module
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.kis_paper_daily_spy_baseline import evaluate_kis_paper_daily_spy_baseline

NOW = datetime(2026, 9, 22, 14, 50, tzinfo=UTC)
BUDGET_MODULE = "thericher_v2.execution.kis_paper_budget_strategy"


class NoCredentialEnvironment(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError("unexpected environment access")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("unexpected environment iteration")

    def __len__(self) -> int:
        raise AssertionError("unexpected environment inspection")


class StubBudgetOutcome:
    def __init__(self, status: str = "no_intent") -> None:
        self.status = status

    def safe_payload(self) -> dict[str, object]:
        return {"status": self.status, "reason_code": "test_recovery", "paper_only": True}


class ModeOnlyEnvironment(NoCredentialEnvironment):
    def __init__(self, mode: str = "kis_paper") -> None:
        self.mode = mode
        self.reads: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.reads.append(key)
        if key == "THERICHER_MODE":
            return self.mode
        return super().__getitem__(key)


class WorkerClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _unexpected(*_args, **_kwargs):
    raise AssertionError("unexpected legacy or external work")


def _install_budget_runner(monkeypatch: pytest.MonkeyPatch, runner: Callable) -> None:
    module = ModuleType(BUDGET_MODULE)
    monkeypatch.setattr(module, "run_kis_paper_budget_strategy", runner, raising=False)
    monkeypatch.setitem(sys.modules, BUDGET_MODULE, module)


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "cache_root": tmp_path / "cache",
        "head_cache_root": tmp_path / "head",
        "availability_root": tmp_path / "availability",
        "state_root": tmp_path / "state",
        "runtime_projection_path": tmp_path / "runtime.json",
        "paper_account_snapshot_path": tmp_path / "account.json",
        "emergency_state_path": tmp_path / "emergency.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": tmp_path / "repo",
        "execution_control_path": tmp_path / "execution-control.json",
    }


def _receipt(as_of: datetime) -> ResearchDecisionReceipt:
    return receipt_from_target_exposure_proposal(
        TargetExposureProposal(
            proposal_id="synthetic-budget-session",
            symbol="SPY",
            market="US",
            action="enter",
            target_exposure=Decimal("0.1"),
            confidence=Decimal("0.5"),
            feature_schema_id="synthetic-features",
            input_status="ready",
            decided_at=as_of,
            valid_until=as_of + timedelta(minutes=2),
            feature_window_end=as_of,
            reason="synthetic",
        ),
        references=DecisionReceiptReferences(
            campaign_ref="ref:" + "a" * 64,
            model_ref="ref:" + "b" * 64,
            input_manifest_ref="sha256:" + "c" * 64,
            proposal_ref="ref:" + "d" * 64,
        ),
    )


@pytest.fixture(autouse=True)
def block_external_and_legacy_order_work(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "KisPaperCanaryClient",
        "UrllibKisPaperCanaryTransport",
        "load_kis_paper_config_from_environment",
        "load_verified_kis_paper_daily_spy_head",
        "load_kis_paper_daily_spy_input",
        "attest_kis_paper_daily_spy_bars",
        "PaperExecutionControlStore",
        "is_us_equity_regular_session_window",
        "resolve_kis_paper_spy_position_target",
        "prepare_kis_paper_spy_receipt_decision",
        "run_kis_paper_receipt_canary",
        "observe_kis_paper_receipt",
        "probe_kis_paper_terminal_fields",
        "_record_session",
        "_load_preferred_daily_spy_input",
        "evaluate_kis_paper_daily_spy_baseline",
    ):
        monkeypatch.setattr(session_module, name, _unexpected)


@pytest.fixture(autouse=True)
def worker_clock(monkeypatch: pytest.MonkeyPatch) -> WorkerClock:
    clock = WorkerClock()
    monkeypatch.setattr(
        session_module, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)
    )
    return clock


@pytest.fixture
def budget_cli(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    fixture = SimpleNamespace(
        environment=ModeOnlyEnvironment(),
        config=object(),
        transport=object(),
        client=SimpleNamespace(_access_token=None),
        initialization=[],
    )

    def load_config(environment):
        fixture.initialization.append("config")
        assert environment is fixture.environment
        return fixture.config

    def transport():
        fixture.initialization.append("transport")
        return fixture.transport

    def client(**kwargs):
        fixture.initialization.append("client")
        assert kwargs == {"config": fixture.config, "transport": fixture.transport}
        return fixture.client

    monkeypatch.setattr(session_module, "os", SimpleNamespace(environ=fixture.environment))
    monkeypatch.setattr(session_module, "load_kis_paper_config_from_environment", load_config)
    monkeypatch.setattr(session_module, "UrllibKisPaperCanaryTransport", transport)
    monkeypatch.setattr(session_module, "KisPaperCanaryClient", client)
    return fixture


@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize("use_clock", [False, True])
@pytest.mark.parametrize("session_id", [None, "budget-session-test"])
def test_budget_branch_precedes_input_and_forwards_only_runner_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    execute: bool,
    use_clock: bool,
    session_id: str | None,
) -> None:
    captured = {}
    outcome = StubBudgetOutcome()

    def run_budget(**kwargs):
        captured.update(kwargs)
        return outcome

    _install_budget_runner(monkeypatch, run_budget)
    clock_calls = []

    def clock():
        clock_calls.append(NOW)
        return NOW

    paths = _paths(tmp_path)
    environment = NoCredentialEnvironment()
    transport = object()
    client = object()
    timing = {"now": None if use_clock else NOW, "clock": clock if use_clock else None}
    result = session_module.run_kis_paper_daily_spy_session(
        environment=environment,
        execute=execute,
        cancel_after_submit=False,
        budget_trial=True,
        transport=transport,
        client=client,
        session_id=session_id,
        **timing,
        **paths,
    )

    assert result is outcome
    assert callable(captured.pop("receipt_loader"))
    assert captured == {
        **{
            key: value
            for key, value in paths.items()
            if key not in {"cache_root", "head_cache_root", "availability_root"}
        },
        "environment": environment,
        "execute": execute,
        "transport": transport,
        "client": client,
        **timing,
        "session_id": session_id or "daily-spy-20260922T145000000000Z",
    }
    assert clock_calls == ([NOW] if use_clock else [])


def test_budget_runner_samples_decision_clock_after_recovery_and_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = []
    paths = _paths(tmp_path)
    as_of = NOW + timedelta(minutes=1)
    decision_at = as_of + timedelta(seconds=1)
    moments = iter((NOW, decision_at))
    input = object()
    receipt = _receipt(decision_at)
    outcome = StubBudgetOutcome()

    def clock():
        current = next(moments)
        if current == decision_at:
            events.append("decision_clock")
        return current

    def load_input(**kwargs):
        events.append("input")
        assert kwargs == {
            **{
                key: paths[key]
                for key in (
                    "cache_root", "head_cache_root", "availability_root", "repository_root"
                )
            },
            "attested_at": as_of,
        }
        return input

    def evaluate(received_input, **kwargs):
        events.append("evaluate")
        assert received_input is input
        assert kwargs == {"as_of": decision_at}
        return SimpleNamespace(receipt=receipt)

    def run_budget(*, receipt_loader, **_kwargs):
        assert events == []
        events.append("recovered")
        assert receipt_loader(as_of) is receipt
        events.append("recorded_by_budget_runner")
        return outcome

    monkeypatch.setattr(session_module, "_load_preferred_daily_spy_input", load_input)
    monkeypatch.setattr(session_module, "evaluate_kis_paper_daily_spy_baseline", evaluate)
    _install_budget_runner(monkeypatch, run_budget)

    assert session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        budget_trial=True,
        clock=clock,
        **paths,
    ) is outcome
    assert events == [
        "recovered", "input", "decision_clock", "evaluate", "recorded_by_budget_runner"
    ]


@pytest.mark.parametrize(
    "mode,decision_seconds,availability_seconds,status,reason",
    [
        ("clock", 1, 0, "ready", "two_close_momentum_enter"),
        ("wall", 1, 0, "ready", "two_close_momentum_enter"),
        ("clock", 1, 2, "future", "daily_input_not_yet_available"),
        ("clock", 0, 0, "future", "daily_input_not_yet_available"),
        ("now", 0, 0, "future", "daily_input_not_yet_available"),
        ("clock", -1, 0, "future", "daily_input_not_yet_available"),
        ("clock", 18601, 0, "stale", "daily_input_execution_window_expired"),
    ],
)
def test_budget_receipt_preserves_strict_availability_and_injected_clock(
    tmp_path, monkeypatch, mode, decision_seconds, availability_seconds, status, reason
):
    decision_at = NOW + timedelta(seconds=decision_seconds)
    moments = iter((NOW, decision_at))
    events, evaluations, inputs = [], [], []
    outcome = StubBudgetOutcome()

    def clock():
        events.append("clock")
        return next(moments)

    def load_input(*, attested_at, **_kwargs):
        events.append("input")
        assert attested_at == NOW
        bars = tuple(
            Bar(
                symbol="SPY", market="US", timeframe=Timeframe.D1,
                start_ts=datetime.combine(day, datetime.min.time(), UTC),
                open=Decimal(price), close=Decimal(price), high=Decimal(price + 1),
                low=Decimal(price - 1), volume=Decimal(1000), complete=True,
            )
            for day, price in ((date(2026, 9, 18), 100), (date(2026, 9, 21), 101))
        )
        input = KisPaperDailySpyInput(
            bars=bars, catalog_dataset_id="synthetic-daily-input",
            catalog_dataset_hash="sha256:" + "a" * 64,
            last_consumed_session=date(2026, 9, 21),
            first_available_at=attested_at + timedelta(seconds=availability_seconds),
            input_manifest_ref="sha256:" + "b" * 64,
            availability_record_path=tmp_path / "unused-availability.json",
        )
        inputs.append(input)
        return input

    def evaluate(input, *, as_of):
        events.append("evaluate")
        assert as_of == decision_at
        result = evaluate_kis_paper_daily_spy_baseline(input, as_of=as_of)
        evaluations.append(result)
        return result

    def run_budget(*, receipt_loader, **_kwargs):
        events.append("recovery")
        receipt = receipt_loader(NOW)
        assert receipt.input_status == status
        assert receipt.decision_class == ("enter" if status == "ready" else "abstain")
        return outcome

    timing = {"clock": clock} if mode == "clock" else {"now": NOW} if mode == "now" else {}
    if mode == "wall":
        def wall_now(zone):
            assert zone is UTC
            return clock()

        monkeypatch.setattr(session_module, "datetime", SimpleNamespace(now=wall_now))
    monkeypatch.setattr(session_module, "_load_preferred_daily_spy_input", load_input)
    monkeypatch.setattr(session_module, "evaluate_kis_paper_daily_spy_baseline", evaluate)
    _install_budget_runner(monkeypatch, run_budget)
    assert session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(), execute=True, cancel_after_submit=False,
        budget_trial=True, **timing, **_paths(tmp_path),
    ) is outcome
    expected = ["recovery", "input", "evaluate"]
    assert events == (expected if mode == "now" else ["clock", *expected[:2], "clock", "evaluate"])
    assert evaluations[0].proposal.reason == reason
    assert inputs[0].first_available_at == NOW + timedelta(seconds=availability_seconds)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("error_type", [OSError, ValueError])
def test_deferred_input_failure_belongs_to_budget_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]
) -> None:
    failure = error_type("synthetic missing input")
    outcome = StubBudgetOutcome()

    def load_input(**_kwargs):
        raise failure

    def run_budget(*, receipt_loader, **_kwargs):
        with pytest.raises(error_type) as exc_info:
            receipt_loader(NOW)
        assert exc_info.value is failure
        return outcome

    monkeypatch.setattr(session_module, "_load_preferred_daily_spy_input", load_input)
    _install_budget_runner(monkeypatch, run_budget)

    assert session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=False,
        budget_trial=True,
        now=NOW,
        **_paths(tmp_path),
    ) is outcome


@pytest.mark.parametrize("execute", [False, True])
def test_conflicting_modes_reject_before_clock_import_or_any_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, execute: bool
) -> None:
    monkeypatch.setitem(sys.modules, BUDGET_MODULE, None)
    with pytest.raises(ValueError, match="budget_trial and cancel_after_submit"):
        session_module.run_kis_paper_daily_spy_session(
            environment=NoCredentialEnvironment(),
            execute=execute,
            cancel_after_submit=True,
            budget_trial=True,
            clock=_unexpected,
            **_paths(tmp_path),
        )


def test_budget_mode_retains_safe_session_id_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, BUDGET_MODULE, None)
    with pytest.raises(ValueError, match="session id is invalid"):
        session_module.run_kis_paper_daily_spy_session(
            environment=NoCredentialEnvironment(),
            execute=True,
            cancel_after_submit=False,
            budget_trial=True,
            session_id="../invalid",
            now=NOW,
            **_paths(tmp_path),
        )


@pytest.mark.parametrize("explicit_default", [False, True])
@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize("cancel_after_submit", [False, True])
def test_default_keeps_legacy_missing_input_outcome_without_budget_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit_default: bool,
    execute: bool,
    cancel_after_submit: bool,
) -> None:
    monkeypatch.setitem(sys.modules, BUDGET_MODULE, None)
    paths = _paths(tmp_path)
    recorded = {}
    outcome = object()

    def load_input(**kwargs):
        assert kwargs["attested_at"] == NOW
        raise ValueError("synthetic unavailable input")

    def record(**kwargs):
        recorded.update(kwargs)
        return outcome

    monkeypatch.setattr(session_module, "_load_preferred_daily_spy_input", load_input)
    monkeypatch.setattr(session_module, "_record_session", record)
    assert session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=execute,
        cancel_after_submit=cancel_after_submit,
        now=NOW,
        session_id="legacy-session",
        **({"budget_trial": False} if explicit_default else {}),
        **paths,
    ) is outcome
    assert recorded == {
        "session_id": "legacy-session",
        "status": "no_intent" if execute else "preview",
        "reason_code": "daily_input_unavailable" if execute else "preview",
        "observed_at": NOW,
        "artifact_root": paths["artifact_root"],
        "repository_root": paths["repository_root"],
    }


@pytest.mark.parametrize("cancel_after_submit", [False, True])
def test_default_keeps_eligible_legacy_canary_and_cancellation_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel_after_submit: bool
) -> None:
    monkeypatch.setitem(sys.modules, BUDGET_MODULE, None)
    paths = _paths(tmp_path)
    receipt = _receipt(NOW)
    input = object()
    prepared = SimpleNamespace(
        status="ready",
        receipt_ref="sha256:" + receipt.decision_id.removeprefix("decision:sha256:"),
        kis_paper_decision=SimpleNamespace(side="buy"),
    )
    canary = SimpleNamespace(
        run_id=session_module.receipt_canary_run_id(prepared.receipt_ref),
        reason_code="synthetic_completed",
    )
    outcome = object()
    calls = []

    def run_canary(received_prepared, **kwargs):
        calls.append("canary")
        assert received_prepared is prepared
        assert kwargs["cancel_after_submit"] is cancel_after_submit
        assert kwargs["execute"] is True
        return canary

    def record(**kwargs):
        calls.append("record")
        assert kwargs["status"] == "canary_completed"
        assert kwargs["canary"] is canary
        assert kwargs["input"] is input
        assert kwargs["evaluation"].receipt is receipt
        return outcome

    monkeypatch.setattr(session_module, "_load_preferred_daily_spy_input", lambda **_kw: input)
    monkeypatch.setattr(
        session_module, "evaluate_kis_paper_daily_spy_baseline",
        lambda *_args, **_kw: SimpleNamespace(receipt=receipt),
    )
    monkeypatch.setattr(session_module, "is_us_equity_regular_session_window", lambda _at: True)
    monkeypatch.setattr(
        session_module, "PaperExecutionControlStore",
        lambda _path: SimpleNamespace(
            read=lambda: SimpleNamespace(pause_buys=False, pause_sells=False)
        ),
    )
    monkeypatch.setattr(
        session_module, "resolve_kis_paper_spy_position_target",
        lambda *_args, **_kw: SimpleNamespace(action="buy"),
    )
    monkeypatch.setattr(
        session_module, "prepare_kis_paper_spy_receipt_decision",
        lambda *_args, **_kw: prepared,
    )
    monkeypatch.setattr(session_module, "run_kis_paper_receipt_canary", run_canary)
    monkeypatch.setattr(session_module, "_observe_completed_canary", lambda **_kw: (None, None))
    monkeypatch.setattr(
        session_module, "_probe_completed_canary_terminal_fields",
        lambda **_kw: (None, None, None),
    )
    monkeypatch.setattr(session_module, "_record_session", record)

    assert session_module.run_kis_paper_daily_spy_session(
        environment=NoCredentialEnvironment(),
        execute=True,
        cancel_after_submit=cancel_after_submit,
        client=SimpleNamespace(snapshot=object, fetch_spy_limit_input=lambda **_kw: object()),
        now=NOW,
        **paths,
    ) is outcome
    assert calls == ["canary", "record"]


@pytest.mark.parametrize("budget_trial", [False, True])
def test_cli_forwards_opt_in_and_prints_only_safe_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_trial: bool,
    budget_cli: SimpleNamespace,
) -> None:
    captured = {}
    outcome = StubBudgetOutcome()

    def run_session(**kwargs):
        captured.update(kwargs)
        return outcome

    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", run_session)
    session_module.main(["--execute", "--budget-trial"] if budget_trial else ["--execute"])

    assert captured["environment"] is budget_cli.environment
    assert captured["budget_trial"] is budget_trial
    assert captured["execute"] is True
    assert captured["cancel_after_submit"] is False
    assert "now" not in captured and "clock" not in captured
    assert captured["client"] is (budget_cli.client if budget_trial else None)
    assert budget_cli.initialization == (["config", "transport", "client"] if budget_trial else [])
    assert budget_cli.environment.reads == (["THERICHER_MODE"] if budget_trial else [])
    assert json.loads(capsys.readouterr().out) == outcome.safe_payload()


def test_cli_rejects_conflicting_flags_before_dispatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", _unexpected)
    with pytest.raises(SystemExit) as exc_info:
        session_module.main(["--budget-trial", "--cancel-after-submit"])
    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_budget_visit_default_is_one() -> None:
    assert session_module.build_parser().parse_args([]).budget_visits == 1


@pytest.mark.parametrize("visits", ["1", "24"])
def test_budget_visit_parser_accepts_bounds(visits: str) -> None:
    assert session_module.build_parser().parse_args(["--budget-visits", visits]).budget_visits == (
        int(visits)
    )


@pytest.mark.parametrize("visits", ["0", "25", "-1", "1.5", "invalid"])
def test_invalid_visit_count_rejects_before_any_work(
    visits: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(session_module.time, "monotonic", _unexpected)
    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", _unexpected)
    with pytest.raises(SystemExit) as exc_info:
        session_module.main(["--execute", "--budget-trial", "--budget-visits", visits])
    assert exc_info.value.code == 2
    assert "--budget-visits" in capsys.readouterr().err


@pytest.mark.parametrize("visits", [1, 2, 24])
def test_pending_visits_reuse_one_client_and_token_until_visit_limit(
    visits: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_cli: SimpleNamespace,
    worker_clock: WorkerClock,
) -> None:
    calls = []
    token = object()

    def run_session(**kwargs):
        assert kwargs["client"] is budget_cli.client
        if not calls:
            kwargs["client"]._access_token = token
        assert kwargs["client"]._access_token is token
        assert kwargs["session_id"] == "bounded-budget-worker"
        calls.append(kwargs)
        return StubBudgetOutcome("pending")

    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", run_session)
    session_module.main([
        "--execute", "--budget-trial", "--budget-visits", str(visits),
        "--session-id", "bounded-budget-worker",
    ])

    assert len(calls) == visits
    assert budget_cli.initialization == ["config", "transport", "client"]
    assert budget_cli.environment.reads == ["THERICHER_MODE"]
    assert worker_clock.sleeps == [15] * (visits - 1)
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == [
        StubBudgetOutcome("pending").safe_payload()
    ] * visits


@pytest.mark.parametrize("prefix_pending", [False, True])
@pytest.mark.parametrize(
    "status", ["completed", "no_intent", "recovery_required", "not_due", "preview", "unknown"]
)
def test_worker_never_repeats_a_non_pending_outcome(
    prefix_pending: bool,
    status: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_cli: SimpleNamespace,
    worker_clock: WorkerClock,
) -> None:
    statuses = (["pending"] if prefix_pending else []) + [status]
    remaining = iter(statuses)

    def run_session(**kwargs):
        assert kwargs["client"] is budget_cli.client
        return StubBudgetOutcome(next(remaining))

    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", run_session)
    session_module.main(["--execute", "--budget-trial", "--budget-visits", "24"])

    assert [json.loads(line)["status"] for line in capsys.readouterr().out.splitlines()] == statuses
    assert worker_clock.sleeps == ([15] if prefix_pending else [])


def test_budget_preview_never_inspects_environment_or_constructs_client(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    worker_clock: WorkerClock,
) -> None:
    calls = []

    def run_session(**kwargs):
        calls.append(kwargs)
        assert kwargs["execute"] is False
        assert kwargs["client"] is None
        return StubBudgetOutcome("preview")

    monkeypatch.setattr(session_module, "os", SimpleNamespace(environ=NoCredentialEnvironment()))
    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", run_session)
    session_module.main(["--budget-trial", "--budget-visits", "24"])

    assert len(calls) == 1
    assert worker_clock.sleeps == []
    assert json.loads(capsys.readouterr().out)["status"] == "preview"


def test_legacy_cli_ignores_budget_visit_count_even_with_pending_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    worker_clock: WorkerClock,
) -> None:
    calls = []

    def run_session(**kwargs):
        calls.append(kwargs)
        assert kwargs["budget_trial"] is False
        assert kwargs["client"] is None
        return StubBudgetOutcome("pending")

    monkeypatch.setattr(session_module.time, "monotonic", _unexpected)
    monkeypatch.setattr(session_module, "os", SimpleNamespace(environ=NoCredentialEnvironment()))
    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", run_session)
    session_module.main(["--execute", "--budget-visits", "24"])

    assert len(calls) == 1
    assert worker_clock.sleeps == []
    assert json.loads(capsys.readouterr().out)["status"] == "pending"


@pytest.mark.parametrize("mode", ["kis_live", "KIS_LIVE", " kis_live "])
def test_live_mode_rejects_before_any_credential_or_client_work(
    mode: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = ModeOnlyEnvironment(mode)
    monkeypatch.setattr(session_module, "os", SimpleNamespace(environ=environment))
    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", _unexpected)

    with pytest.raises(SystemExit) as exc_info:
        session_module.main(["--execute", "--budget-trial", "--budget-visits", "24"])

    assert exc_info.value.code == 2
    assert environment.reads == ["THERICHER_MODE"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "live_mode_unavailable" in captured.err


def test_configuration_failure_prints_only_safe_category(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_cli: SimpleNamespace,
) -> None:
    def unavailable(_environment):
        raise ValueError("private-configuration-details-must-not-print")

    monkeypatch.setattr(session_module, "load_kis_paper_config_from_environment", unavailable)
    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", _unexpected)
    with pytest.raises(SystemExit) as exc_info:
        session_module.main(["--execute", "--budget-trial"])

    assert exc_info.value.code == 2
    assert budget_cli.initialization == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "paper_configuration_unavailable" in captured.err
    assert "private-configuration-details" not in captured.err


@pytest.mark.parametrize("elapsed", [1200, 1201])
def test_long_visit_stops_at_wall_budget_without_sleep_or_another_visit(
    elapsed: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_cli: SimpleNamespace,
    worker_clock: WorkerClock,
) -> None:
    calls = []

    def run_session(**kwargs):
        calls.append(kwargs)
        worker_clock.now += elapsed
        return StubBudgetOutcome("pending")

    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", run_session)
    session_module.main(["--execute", "--budget-trial", "--budget-visits", "24"])

    assert len(calls) == 1
    assert calls[0]["client"] is budget_cli.client
    assert worker_clock.sleeps == []
    assert json.loads(capsys.readouterr().out)["status"] == "pending"


def test_wall_budget_includes_client_setup_and_checks_before_first_visit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_cli: SimpleNamespace,
    worker_clock: WorkerClock,
) -> None:
    monotonic = iter([100.0, 1300.0])
    monkeypatch.setattr(session_module.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", _unexpected)
    session_module.main(["--execute", "--budget-trial", "--budget-visits", "24"])

    assert budget_cli.initialization == ["config", "transport", "client"]
    assert worker_clock.sleeps == []
    assert capsys.readouterr().out == ""


def test_sleep_is_capped_by_remaining_wall_budget_and_no_visit_starts_at_deadline(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_cli: SimpleNamespace,
    worker_clock: WorkerClock,
) -> None:
    calls = []

    def run_session(**kwargs):
        calls.append(kwargs)
        worker_clock.now += 1199
        return StubBudgetOutcome("pending")

    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", run_session)
    session_module.main(["--execute", "--budget-trial", "--budget-visits", "24"])

    assert len(calls) == 1
    assert calls[0]["client"] is budget_cli.client
    assert worker_clock.sleeps == [1]
    assert worker_clock.now == 1300
    assert json.loads(capsys.readouterr().out)["status"] == "pending"


def test_deadline_is_rechecked_after_sleep_overshoots(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    budget_cli: SimpleNamespace,
    worker_clock: WorkerClock,
) -> None:
    calls = []

    def run_session(**kwargs):
        calls.append(kwargs)
        worker_clock.now += 1180
        return StubBudgetOutcome("pending")

    def oversleep(seconds):
        worker_clock.sleep(seconds)
        worker_clock.now += 5

    monkeypatch.setattr(session_module.time, "sleep", oversleep)
    monkeypatch.setattr(session_module, "run_kis_paper_daily_spy_session", run_session)
    session_module.main(["--execute", "--budget-trial", "--budget-visits", "24"])

    assert len(calls) == 1
    assert calls[0]["client"] is budget_cli.client
    assert worker_clock.sleeps == [15]
    assert worker_clock.now == 1300
    assert json.loads(capsys.readouterr().out)["status"] == "pending"
