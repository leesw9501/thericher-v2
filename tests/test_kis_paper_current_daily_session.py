"""Synthetic daily pointer/restart tests; original native portfolio lifecycle."""

import ast
import copy
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from test_kis_paper_portfolio_cycle import call as call
from test_kis_paper_portfolio_cycle import owned as owned
from test_kis_paper_portfolio_execute import harness as harness
from test_kis_paper_portfolio_execute import (
    no_actual_provider_or_credentials as no_actual_provider_or_credentials,
)
from thericher_v2.execution import kis_paper_current_daily_session as daily
from thericher_v2.research.kis_paper_current_daily_control import CurrentDailyControl

PATHS = (
    "state_root",
    "repository_root",
    "artifact_root",
    "runtime_projection_path",
    "paper_account_snapshot_path",
    "emergency_state_path",
    "execution_control_path",
)
REF = "sha256:" + "f" * 64
PRIVATE_ERROR = "synthetic-private-error-text-must-not-escape"
TYPED_FAILURES = [
    (error_type, code, reason)
    for error_type, reasons in (
        (daily.KisPaperReadOnlyError, daily._READONLY_REASONS),
        (daily.canary.KisPaperCanaryError, daily._CANARY_REASONS),
        (daily.cycle._RecoveryRequired, daily._CYCLE_REASONS),
        (daily.KisPaperPortfolioBudgetError, daily._PORTFOLIO_BUDGET_REASONS),
    )
    for code, reason in reasons.items()
]


def opaque_error(error_type, code):
    class NoErrorText(error_type):
        def __str__(self):
            raise AssertionError("exception_text_must_not_be_inspected")

    error = NoErrorText(code)
    if isinstance(error, (daily.KisPaperReadOnlyError, daily.canary.KisPaperCanaryError)):
        error.args = (PRIVATE_ERROR,)
    error.diagnostic = {"body": PRIVATE_ERROR}
    error.__cause__ = ValueError(PRIVATE_ERROR)
    return error


@pytest.fixture
def session(call, monkeypatch):
    client = call["client"]
    control = CurrentDailyControl(
        call["input_ref"],
        call["control_ref"],
        client.now.date(),
        call["target_as_of"],
        client.now - timedelta(minutes=10),
        client.now.replace(hour=20, minute=0, second=0),
        call["weights_by_symbol"],
        call["covariance_by_symbol"],
    )
    loads = []

    def loader():
        loads.append(client.now)
        return control

    monkeypatch.setattr(daily, "build_current_daily_control", lambda c, as_of: c)
    args = {k: call[k] for k in PATHS}
    args.update(
        client=client,
        data_loader=loader,
        reads_factory=call["reads_factory"],
        clock=lambda: client.now,
        execute=True,
    )
    return args, control, loads


def record(session):
    return daily.budget._read_json(session[0]["state_root"] / daily.POINTER)


def fail(*a, **k):
    pytest.fail("forbidden_callback")


def test_default_false_has_no_client_clock_data_path_or_lock_io(monkeypatch):
    monkeypatch.setattr(daily, "_account", fail)
    monkeypatch.setattr(daily.Path, "resolve", fail)
    assert (
        daily.run_kis_paper_current_daily_session(
            **dict.fromkeys(PATHS),
            client=object(),
            clock=fail,
            data_loader=fail,
            reads_factory=fail,
        ).status
        == "inert"
    )


def test_real_native_no_delta_closes_once_then_dedups_changed_book(session, monkeypatch):
    args, control, loads = session
    basis = daily.budget._load_binding(args["state_root"])["basis_ref"]
    first = daily.run_kis_paper_current_daily_session(**args)
    assert first.status == "complete" and record(session)["completed"] is True
    assert record(session)["context"]["expected_basis_ref"] == basis
    assert record(session)["context"]["native"]["session_id"] == control.session_id
    before = (args["state_root"] / daily.POINTER).read_bytes()
    monkeypatch.setattr(daily.budget, "_load_binding", fail)
    monkeypatch.setattr(daily.cycle, "advance_kis_paper_portfolio_cycle", fail)
    again = daily.run_kis_paper_current_daily_session(**args)
    assert again.reason == "already_completed" and len(loads) == 2
    assert (args["state_root"] / daily.POINTER).read_bytes() == before


def mixed_control(session):
    args, control, _ = session
    current = replace(
        control, weights_by_symbol=dict(SPY=Decimal(".11"), TLT=Decimal(".41"), GLD=Decimal(".41"))
    )
    args["data_loader"] = lambda: current
    return args


def test_real_native_pending_restart_keeps_initial_basis_and_never_reloads_data(session):
    args = mixed_control(session)
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    first = copy.deepcopy(record(session))
    assert first["cycle_ref"] is not None and len(args["client"].wire) == 1
    args["data_loader"] = fail
    for _ in range(4):
        result = daily.run_kis_paper_current_daily_session(**args)
        if result.status == "complete":
            break
    assert result.status == "complete"
    assert record(session)["context"] == first["context"]
    assert record(session)["cycle_ref"] == first["cycle_ref"]
    assert len(args["client"].wire) == 3
    assert len({i.run_id for i in args["client"].submits}) == 3
    assert (
        daily.budget._load_binding(args["state_root"])["basis_ref"]
        == (first["context"]["expected_basis_ref"])
    )


def test_real_native_unknown_expired_recovers_without_data_or_second_submit(session, monkeypatch):
    args = mixed_control(session)
    args["client"].unknown = True
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    frozen = copy.deepcopy(record(session))
    intent = args["client"].submits[0]
    state = daily.canary.KisPaperCanaryStateStore(args["state_root"] / (intent.run_id + ".json"))
    assert state.read().phase == "outcome_unknown"
    args["data_loader"] = fail
    args["client"].now += timedelta(days=1)
    seen = []
    original = args["client"].reconcile

    def reconcile(retained, *, now):
        seen.append(retained.intent)
        return original(retained, now=now)

    monkeypatch.setattr(args["client"], "reconcile", reconcile)
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    assert seen == [intent] and state.read().phase == "outcome_unknown"
    assert record(session) == frozen and len(args["client"].wire) == 1


def test_real_native_crash_after_journal_preserves_intent_before_wire(session, monkeypatch):
    args = mixed_control(session)
    seen = []

    def crash(intent, **kwargs):
        state = daily.canary.KisPaperCanaryStateStore(
            args["state_root"] / (intent.run_id + ".json")
        ).read()
        assert state.intent == intent and state.phase == "submission_started"
        assert record(session)["completed"] is False
        seen.append(intent)
        raise RuntimeError("SYN-secret-not-output")

    monkeypatch.setattr(args["client"], "submit_limit", crash)
    result = daily.run_kis_paper_current_daily_session(**args)
    frozen = copy.deepcopy(record(session))
    assert result.status == "unavailable" and not args["client"].wire and len(seen) == 1
    assert "SYN-secret" not in json.dumps(result.safe_payload())
    args["data_loader"] = fail
    monkeypatch.setattr(args["client"], "submit_limit", fail)
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    assert not args["client"].wire and record(session)["context"] == frozen["context"]


def test_pending_persists_initial_before_native_and_resumes_without_data(session, monkeypatch):
    args, _, loads = session
    original = daily.budget._load_binding(args["state_root"])
    calls = []

    def native(**kwargs):
        retained = record(session)
        assert retained["context"]["expected_binding_ref"] == "sha256:" + daily.budget._digest(
            original
        )
        calls.append(kwargs)
        return daily.cycle.KisPaperPortfolioCycleOutcome(
            "pending", "exact_leg_advanced", "buy", cycle_ref=REF
        )

    monkeypatch.setattr(daily.cycle, "advance_kis_paper_portfolio_cycle", native)
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    frozen = copy.deepcopy(record(session))
    args["data_loader"] = fail
    monkeypatch.setattr(daily.budget, "_load_binding", fail)
    args["client"].now += timedelta(days=1)
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    assert len(loads) == 1 and record(session) == frozen
    assert calls[1]["expected_cycle_ref"] == REF
    for key in (
        "expected_account_ref",
        "expected_basis_ref",
        "expected_owner_refs",
        "expected_binding_ref",
    ):
        assert calls[0][key] == calls[1][key]
    assert calls[1]["client"]._delegate is args["client"]


def test_crash_after_native_effect_keeps_original_unknown_context(session, monkeypatch):
    args, _, loads = session

    def crashed(**kwargs):
        assert record(session)["completed"] is False
        raise RuntimeError("SYN-sensitive-message-never-published")

    monkeypatch.setattr(daily.cycle, "advance_kis_paper_portfolio_cycle", crashed)
    result = daily.run_kis_paper_current_daily_session(**args)
    before = copy.deepcopy(record(session))
    assert result.status == "unavailable" and "sensitive" not in json.dumps(result.safe_payload())
    args["data_loader"] = fail
    monkeypatch.setattr(
        daily.cycle,
        "advance_kis_paper_portfolio_cycle",
        lambda **k: daily.cycle.KisPaperPortfolioCycleOutcome(
            "pending", "exact_leg_advanced", "buy", cycle_ref=REF
        ),
    )
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    assert record(session)["context"] == before["context"] and len(loads) == 1


def test_completion_pointer_write_crash_replays_native_without_data_or_posts(session, monkeypatch):
    args, _, loads = session
    atomic = daily.budget._atomic_json

    def crash(path, payload):
        if path.name == daily.POINTER and payload["completed"]:
            raise OSError("SYN-write-crash")
        return atomic(path, payload)

    monkeypatch.setattr(daily.budget, "_atomic_json", crash)
    assert daily.run_kis_paper_current_daily_session(**args).status == "unavailable"
    assert record(session)["completed"] is False
    assert not args["client"].wire
    args["data_loader"] = fail
    monkeypatch.setattr(daily.budget, "_atomic_json", atomic)
    assert daily.run_kis_paper_current_daily_session(**args).status == "complete"
    assert not args["client"].wire and len(loads) == 1


@pytest.mark.parametrize("later_day", (False, True))
def test_later_control_replaces_only_completed_pointer_keeps_native_evidence(session, later_day):
    args, control, _ = session
    assert daily.run_kis_paper_current_daily_session(**args).status == "complete"
    old = copy.deepcopy(record(session))
    evidence = {
        p: p.read_bytes() for p in (args["state_root"] / ".portfolio_cycles").rglob("*.json")
    }
    shift = timedelta(days=int(later_day))
    args["client"].now += shift
    next_control = replace(
        control,
        input_ref="sha256:" + "e" * 64,
        control_ref="sha256:" + "a" * 64,
        session_date=control.session_date + shift,
        target_as_of=control.target_as_of + shift,
        available_at=control.available_at + shift,
        valid_until=control.valid_until + shift,
    )
    args["data_loader"] = lambda: next_control
    assert daily.run_kis_paper_current_daily_session(**args).status == "complete"
    assert record(session)["context"]["native"] != old["context"]["native"]
    assert record(session)["context"]["expected_basis_ref"] == old["context"]["expected_basis_ref"]
    assert all(p.read_bytes() == raw for p, raw in evidence.items())
    assert not args["client"].wire


@pytest.mark.parametrize("field", ("paths", "ref", "cycle_ref"))
def test_corrupt_or_different_original_context_is_retained_without_callbacks(
    session, monkeypatch, field
):
    args, _, _ = session
    assert daily.run_kis_paper_current_daily_session(**args).status == "complete"
    value = record(session)
    if field == "paths":
        args["emergency_state_path"] = args["emergency_state_path"].with_name("different.json")
    else:
        value[field] = "invalid"
        daily.budget._atomic_json(args["state_root"] / daily.POINTER, value)
    before = (args["state_root"] / daily.POINTER).read_bytes()
    args["data_loader"] = fail
    monkeypatch.setattr(daily.cycle, "advance_kis_paper_portfolio_cycle", fail)
    assert daily.run_kis_paper_current_daily_session(**args).status == "unavailable"
    assert (args["state_root"] / daily.POINTER).read_bytes() == before


def test_expired_submit_guard_keeps_recovery_reads_real_and_same_client(session, monkeypatch):
    args, _, _ = session
    context = dict(
        expected_account_ref=daily._account(args["client"]),
        available_at=(args["client"].now - timedelta(minutes=1)).isoformat(),
        valid_until=(args["client"].now + timedelta(seconds=1)).isoformat(),
    )
    view = daily._WindowClient(args["client"], context, args["clock"])
    args["client"].now += timedelta(days=1)
    assert view.snapshot().captured_at == args["client"].now
    seen = []

    def submit(intent, *, now, clock):
        clock()
        seen.append(intent)

    recovery = object()
    monkeypatch.setattr(args["client"], "submit_limit", submit)
    monkeypatch.setattr(args["client"], "reconcile", lambda s, now: (s, now))
    monkeypatch.setattr(args["client"], "cancel_order", lambda i, broker_order_id: i)
    assert view.reconcile(recovery, now=args["client"].now) == (recovery, args["client"].now)
    assert view.cancel_order(recovery, broker_order_id="SYN") is recovery
    with pytest.raises(daily.canary.KisPaperCanaryError):
        view.submit_limit(object())
    assert not seen


@pytest.mark.parametrize("reason", ("risk_changed", "identity_conflict"))
def test_final_caller_risk_clock_preserved_once_after_initial_check(session, monkeypatch, reason):
    args, _, _ = session
    context = dict(
        expected_account_ref=daily._account(args["client"]),
        available_at=(args["client"].now - timedelta(minutes=1)).isoformat(),
        valid_until=(args["client"].now + timedelta(minutes=1)).isoformat(),
    )
    clocks, wire = [], []
    changed = False
    intent = object()

    def guarded_clock():
        clocks.append(changed)
        if changed:
            raise daily.canary.KisPaperCanaryError(reason)
        return args["client"].now

    assert guarded_clock() == args["client"].now
    changed = True

    def submit(actual, *, now, clock):
        assert actual is intent and now == args["client"].now
        clock()
        wire.append(actual)

    monkeypatch.setattr(args["client"], "submit_limit", submit)
    view = daily._WindowClient(args["client"], context, fail)
    with pytest.raises(daily.canary.KisPaperCanaryError) as error:
        view.submit_limit(intent, now=args["client"].now, clock=guarded_clock)
    assert error.value.code == reason and clocks == [False, True] and not wire


def test_final_native_clock_guard_catches_expiry_after_pacing(session, monkeypatch):
    args, _, _ = session
    context = dict(
        expected_account_ref=daily._account(args["client"]),
        available_at=(args["client"].now - timedelta(minutes=1)).isoformat(),
        valid_until=(args["client"].now + timedelta(seconds=1)).isoformat(),
    )
    seen, clocks = [], []
    intent = object()

    def guarded_clock():
        clocks.append(args["client"].now)
        return args["client"].now

    def paced(actual, *, now, clock):
        assert actual is intent
        args["client"].now += timedelta(seconds=2)
        clock()
        seen.append(actual)

    monkeypatch.setattr(args["client"], "submit_limit", paced)
    view = daily._WindowClient(args["client"], context, fail)
    with pytest.raises(daily.canary.KisPaperCanaryError):
        view.submit_limit(intent, clock=guarded_clock)
    assert seen == [] and len(clocks) == 1


def test_virtual_host_and_client_type_fail_before_data_or_pointer(session):
    args, _, _ = session
    args["data_loader"] = fail
    assert (
        daily.run_kis_paper_current_daily_session(**(args | dict(client=object()))).status
        == "unavailable"
    )
    config = copy.copy(args["client"]._config)
    object.__setattr__(config, "base_url", "https://invalid.example")
    args["client"]._config = config
    assert daily.run_kis_paper_current_daily_session(**args).status == "unavailable"
    assert record(session) is None


def test_no_credentials_model_selection_or_secret_fields_in_source():
    source = Path(daily.__file__).read_text()
    tree = ast.parse(source)
    names = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert not names & {
        "getenv",
        "load_kis_paper_config",
        "load_kis_paper_config_from_environment",
        "observe",
        "evaluate_kis_paper_daily_spy_baseline",
    }
    assert "KIS_LIVE" not in source and ".env" not in source
    payload = daily.CurrentDailySessionOutcome("pending", "exact_cycle_advanced").safe_payload()
    assert set(payload) == {"kind", "status", "reason", "limitation"}


@pytest.mark.parametrize("error_type,code,reason", TYPED_FAILURES)
def test_outer_typed_failure_projects_only_exact_allowlisted_reason(
    session, monkeypatch, error_type, code, reason
):
    args, _, loads = session
    before = (args["state_root"] / daily.budget.BUDGET_FILE).read_bytes()
    wire_before = len(args["client"].wire)

    def read_failure(*_args):
        raise opaque_error(error_type, code)

    with monkeypatch.context() as patch:
        patch.setattr(daily.budget, "_read_json", read_failure)
        result = daily.run_kis_paper_current_daily_session(**args)
    assert result.safe_payload() == dict(
        kind="kis_paper_current_daily_session_v1",
        status="unavailable",
        reason=reason,
        limitation="cycle_status_not_current_inventory_or_net_pnl",
    )
    assert PRIVATE_ERROR not in json.dumps(result.safe_payload())
    assert not loads and len(args["client"].wire) == wire_before
    assert not (args["state_root"] / daily.POINTER).exists()
    assert (args["state_root"] / daily.budget.BUDGET_FILE).read_bytes() == before


@pytest.mark.parametrize("stage", ["configuration", "retained_context"])
@pytest.mark.parametrize(
    "fault",
    [
        "unknown_readonly",
        "unknown_canary",
        "unknown_cycle",
        "wrong_family_readonly",
        "wrong_family_canary",
        "missing_code",
        "nonstring_code",
        "unhashable_code",
        "string_subclass_code",
        "raising_code_property",
        "multiple_cycle_args",
        "nonstring_cycle_arg",
        "untyped_readonly_literal",
        "untyped_cycle_literal",
    ],
)
def test_unknown_or_malformed_outer_error_retains_original_generic(
    session, monkeypatch, stage, fault
):
    args, _, loads = session
    error = opaque_error(daily.KisPaperReadOnlyError, PRIVATE_ERROR)
    if fault == "unknown_canary":
        error = opaque_error(daily.canary.KisPaperCanaryError, PRIVATE_ERROR)
    elif fault == "unknown_cycle":
        error = opaque_error(daily.cycle._RecoveryRequired, PRIVATE_ERROR)
    elif fault == "wrong_family_readonly":
        error.code = "cycle_book_changed"
    elif fault == "wrong_family_canary":
        error = opaque_error(daily.canary.KisPaperCanaryError, "open_orders_response_incomplete")
    elif fault == "missing_code":
        del error.code
    elif fault == "nonstring_code":
        error.code = None
    elif fault == "unhashable_code":
        error.code = {"code": "open_orders_response_incomplete"}
    elif fault == "string_subclass_code":
        class HostileString(str):
            def __hash__(self):
                raise AssertionError("untrusted_string_subclass_must_not_be_hashed")

        error.code = HostileString("open_orders_response_incomplete")
    elif fault == "raising_code_property":
        class BrokenCode(daily.KisPaperReadOnlyError):
            def __getattribute__(self, name):
                if name == "code":
                    raise ValueError(PRIVATE_ERROR)
                return super().__getattribute__(name)

        error = BrokenCode("open_orders_response_incomplete")
    elif fault == "multiple_cycle_args":
        error = opaque_error(daily.cycle._RecoveryRequired, "cycle_book_changed")
        error.args = ("cycle_book_changed", PRIVATE_ERROR)
    elif fault == "nonstring_cycle_arg":
        error = opaque_error(daily.cycle._RecoveryRequired, {"code": "cycle_book_changed"})
    elif fault == "untyped_readonly_literal":
        error = opaque_error(ValueError, "open_orders_response_incomplete")
    elif fault == "untyped_cycle_literal":
        error = opaque_error(RuntimeError, "cycle_book_changed")

    def failure(*_args):
        raise error

    with monkeypatch.context() as patch:
        owner, name = (
            (daily, "_account") if stage == "configuration" else (daily.budget, "_read_json")
        )
        patch.setattr(owner, name, failure)
        result = daily.run_kis_paper_current_daily_session(**args)
    assert (result.status, result.reason) == (
        "unavailable",
        "session_configuration_invalid"
        if stage == "configuration"
        else "retained_context_recovery_required",
    )
    assert PRIVATE_ERROR not in json.dumps(result.safe_payload()) and not loads


@pytest.mark.parametrize(
    "error_type,code,reason",
    [
        (daily.KisPaperReadOnlyError, "open_orders_response_incomplete",
         "readonly_open_orders_response_incomplete"),
        (daily.canary.KisPaperCanaryError, "transport_failure", "canary_transport_failure"),
        (daily.cycle._RecoveryRequired, "cycle_book_changed", "cycle_book_changed"),
    ],
)
def test_typed_pending_recovery_failure_preserves_journal_before_data_or_alternative_order(
    session, monkeypatch, error_type, code, reason
):
    args = mixed_control(session)
    args["client"].unknown = True
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    pointer = args["state_root"] / daily.POINTER
    before = pointer.read_bytes()
    frozen = copy.deepcopy(record(session))
    native_evidence = {p: p.read_bytes() for p in args["state_root"].rglob("*.json")}
    before_wire = len(args["client"].wire)
    before_submits = list(args["client"].submits)
    args["data_loader"] = fail
    seen = []

    def recovery_failure(**kwargs):
        seen.append(kwargs["expected_cycle_ref"])
        raise opaque_error(error_type, code)

    with monkeypatch.context() as patch:
        patch.setattr(daily.cycle, "advance_kis_paper_portfolio_cycle", recovery_failure)
        result = daily.run_kis_paper_current_daily_session(**args)
    assert (result.status, result.reason) == ("unavailable", reason)
    assert seen == [frozen["cycle_ref"]]
    assert pointer.read_bytes() == before
    assert all(path.read_bytes() == raw for path, raw in native_evidence.items())
    assert len(args["client"].wire) == before_wire
    assert args["client"].submits == before_submits
    assert PRIVATE_ERROR not in json.dumps(result.safe_payload())
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    assert record(session) == frozen
    assert len(args["client"].wire) == before_wire
    assert args["client"].submits == before_submits


def _literal_call_codes(path, positions):
    codes = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        position = positions.get(node.func.id)
        if position is not None and len(node.args) > position:
            value = node.args[position]
            if isinstance(value, ast.Constant) and type(value.value) is str:
                codes.add(value.value)
    return codes


def test_finite_native_recovery_inventory_matches_existing_source_literals():
    root = Path(daily.__file__).parent
    codes = set().union(*(
        _literal_call_codes(root / (name + ".py"), {"_check": 1, "_RecoveryRequired": 0})
        for name in (
            "kis_paper_portfolio_cycle", "kis_paper_portfolio_execute",
            "kis_paper_portfolio_plan", "kis_paper_budget_strategy", "kis_paper_spy_fill_cycle",
        )
    ))
    assert daily._CYCLE_REASONS == {code: code for code in codes}
    codes = _literal_call_codes(root / "kis_paper_portfolio_budget.py", {
        "_check": 1, "_text": 2, "KisPaperPortfolioBudgetError": 0,
    })
    assert daily._PORTFOLIO_BUDGET_REASONS == {
        code: "portfolio_budget_" + code for code in codes
    }
    tree = ast.parse((root / "kis_paper_portfolio_cycle.py").read_text())
    unavailable = {
        node.args[1].value for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "KisPaperPortfolioCycleOutcome" and len(node.args) >= 2
        and isinstance(node.args[0], ast.Constant) and node.args[0].value == "unavailable"
        and isinstance(node.args[1], ast.Constant) and type(node.args[1].value) is str
    }
    assert daily._CYCLE_UNAVAILABLE_REASONS == {code: code for code in unavailable}


@pytest.mark.parametrize("error_type", [daily.cycle._RecoveryRequired,
                                       daily.KisPaperPortfolioBudgetError])
def test_native_recovery_unknown_and_hostile_codes_are_not_diagnostics(error_type):
    class HostileString(str):
        def __hash__(self):
            raise AssertionError("untrusted_string_subclass_must_not_be_hashed")

    for value in ("not_a_native_code", [], {}, None, HostileString("cycle_buy_unavailable")):
        assert daily._failure_reason(opaque_error(error_type, value)) is None
    error = opaque_error(error_type, "cycle_buy_unavailable")
    error.args = ("cycle_buy_unavailable", PRIVATE_ERROR)
    assert daily._failure_reason(error) is None
    assert daily._failure_reason(opaque_error(ValueError, "cycle_buy_unavailable")) is None


@pytest.mark.parametrize("reason,expected", [
    ("baseline_reduction_required", "baseline_reduction_required"),
    ("target_quantization_changed", "target_quantization_changed"),
    ("unknown_native_reason", "native_recovery_required"),
    ([], "native_recovery_required"),
    (None, "native_recovery_required"),
])
def test_unavailable_native_outcome_retains_only_finite_reason(
    session, monkeypatch, reason, expected
):
    args = session[0]
    monkeypatch.setattr(daily.cycle, "advance_kis_paper_portfolio_cycle", lambda **kwargs:
        daily.cycle.KisPaperPortfolioCycleOutcome("unavailable", reason, "buy"))
    result = daily.run_kis_paper_current_daily_session(**args)
    assert (result.status, result.reason) == ("unavailable", expected)
    assert not args["client"].wire


@pytest.mark.parametrize("change,expected", [
    ("orderability", "buying_power_insufficient"),
    ("risk", "rounded_risk_exceeds_cap"),
    ("quantization", "target_quantization_changed"),
])
def test_real_native_post_full_sell_diagnostic_keeps_exact_context_and_no_buy(
    session, monkeypatch, change, expected
):
    args = mixed_control(session)
    if change == "risk":
        control = args["data_loader"]()
        covariance = {
            symbol: {other: Decimal(".01") if symbol == other else Decimal(0)
                     for other in daily.cycle.SYMBOLS}
            for symbol in daily.cycle.SYMBOLS
        }
        args["data_loader"] = lambda: replace(control, covariance_by_symbol=covariance)
    assert daily.run_kis_paper_current_daily_session(**args).status == "pending"
    frozen = copy.deepcopy(record(session))
    journal = next(args["state_root"].glob(".portfolio_cycles/*/cycle.json"))
    original = journal.read_bytes()
    before = daily.budget._load_binding(args["state_root"])
    sell_intent = args["client"].submits[0]
    factory = args["reads_factory"]

    def fresh_reads():
        reads = factory()
        if change == "orderability":
            rows = tuple(replace(row, orderable=replace(row.orderable, orderable_funds=Decimal(0)))
                         for row in reads.instruments)
        elif change == "quantization":
            rows = tuple(replace(
                row,
                quote=replace(row.quote, last=Decimal(200), best_bid=Decimal("199.99"),
                              best_ask=Decimal(200)),
                buy_limit=Decimal(200),
                orderable=replace(row.orderable, reference_price=Decimal(200)),
            ) for row in reads.instruments)
        else:
            return reads
        return replace(reads, instruments=rows)

    previews = []
    preview = daily.cycle.project_kis_paper_portfolio_preview

    def real_preview(**kwargs):
        result = preview(**kwargs)
        previews.append(result)
        return result

    monkeypatch.setattr(daily.cycle, "project_kis_paper_portfolio_preview", real_preview)
    args["reads_factory"], args["data_loader"] = fresh_reads, fail
    result = daily.run_kis_paper_current_daily_session(**args)
    assert (result.status, result.reason) == ("unavailable", expected)
    assert len(previews) == 1
    targets = tuple(Decimal(daily.budget._read_json(journal)["targets"][s])
                    for s in daily.cycle.SYMBOLS)
    if change == "quantization":
        assert previews[0].target_quantities != targets
    else:
        assert previews[0].target_quantities == targets
        assert previews[0].reason == {
            "risk": "rounded_risk_exceeds_cap", "orderability": "buying_power_insufficient",
        }[change]
    book = daily.budget._load_binding(args["state_root"])
    assert book["basis_ref"] == before["basis_ref"]
    assert all(book["terminal_evidence"][run] == payload
               for run, payload in before["terminal_evidence"].items())
    state = daily.canary.KisPaperCanaryStateStore(
        args["state_root"] / (sell_intent.run_id + ".json")
    ).read()
    assert state.intent == sell_intent and daily.budget._terminal(state)
    assert state.cumulative_fill.quantity == sell_intent.quantity
    assert sell_intent.run_id in book["terminal_evidence"]
    assert daily.cycle._project(args["state_root"], book, args["clock"]())[-1].reserved_buys == 0
    assert args["client"].submits == [sell_intent] and len(args["client"].wire) == 1
    assert journal.read_bytes() == original and not journal.with_name("buy.json").exists()
    assert record(session)["context"] == frozen["context"]
    assert record(session)["cycle_ref"] == frozen["cycle_ref"]
    assert record(session)["completed"] is False
    assert PRIVATE_ERROR not in json.dumps(result.safe_payload())
