"""Synthetic exceptions and owned scratch only; no provider, credentials or state."""

from __future__ import annotations

import importlib.util
import io
import json
import socket
import sys
import urllib.request
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution import kis_paper_current_stock_cycle as cycle
from thericher_v2.execution import kis_readonly

ROOT = Path(__file__).resolve().parents[1]
SECRET = "synthetic-account-order-token-body-amount-do-not-output"


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker = load_script("first_failure_stock_worker", "run_kis_paper_current_stock_cycle_worker.py")
current20 = load_script("first_failure_current20", "run_current20_paper_candidate_worker.py")
host = load_script("first_failure_host", "run_current20_paper_candidate.py")


@pytest.fixture(autouse=True)
def deny_external_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("provider_credentials_or_native_client_forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", deny)
    monkeypatch.setattr(kis_readonly, "load_kis_paper_config", deny)
    monkeypatch.setattr(worker, "client_factory", deny)
    monkeypatch.setattr(cycle, "_client", deny)
    monkeypatch.setattr(host.subprocess, "Popen", deny)


def arguments(tmp_path):
    return dict(
        **{
            key: tmp_path / key
            for key in (
                "state_root",
                "repository_root",
                "artifact_root",
                "runtime_projection_path",
                "paper_account_snapshot_path",
                "emergency_state_path",
                "execution_control_path",
            )
        },
        expected_account_ref="a" * 64,
        execute=True,
    )


def failing_visit(monkeypatch, tmp_path, error, **kwargs):
    def fail(_path):
        raise error

    monkeypatch.setattr(cycle, "_unlinked", fail)
    return cycle.run_kis_paper_current_stock_cycle(**arguments(tmp_path), **kwargs)


def assert_native_failure(result):
    assert result.safe_payload() == dict(
        status="unavailable",
        reason="native_recovery_required",
        leg_count=0,
    )


def test_default_sink_none_has_no_diagnostic_effect(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "_first_failure_diagnostic", lambda _: pytest.fail("no_sink"))
    assert_native_failure(failing_visit(monkeypatch, tmp_path, RuntimeError(SECRET)))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "error,category",
    [
        (TypeError(SECRET), "type_error"),
        (ValueError(SECRET), "value_error"),
        (KeyError(SECRET), "key_error"),
        (IndexError(SECRET), "index_error"),
        (AttributeError(SECRET), "attribute_error"),
        (RuntimeError(SECRET), "runtime_error"),
        (OSError(SECRET), "os_error"),
        (FileNotFoundError(SECRET), "file_not_found"),
        (PermissionError(SECRET), "permission_error"),
        (TimeoutError(SECRET), "timeout_error"),
        (ZeroDivisionError(SECRET), "zero_division"),
        (AssertionError(SECRET), "assertion_error"),
    ],
)
def test_closed_builtin_categories_and_original_public_frame(
    monkeypatch,
    tmp_path,
    error,
    category,
):
    records = []
    assert_native_failure(
        failing_visit(
            monkeypatch,
            tmp_path,
            error,
            first_failure_sink=records.append,
        )
    )
    assert len(records) == 1
    value = records[0]
    assert value["error_category"] == category
    assert value["frame"]["module"] == cycle.__name__
    assert type(value["frame"]["line"]) is int
    source_line = Path(cycle.__file__).read_text().splitlines()[value["frame"]["line"] - 1]
    assert "_unlinked(path)" in source_line
    encoded = json.dumps(value)
    assert SECRET not in encoded and str(tmp_path) not in encoded
    assert set(value) == {"kind", "error_category", "frame"}


def test_unknown_subclass_never_reads_exception_attributes(monkeypatch, tmp_path):
    class Sensitive(ValueError):
        def __getattribute__(self, name):
            raise AssertionError("exception_attribute_access_forbidden")

        def __str__(self):
            raise AssertionError("exception_message_forbidden")

        def __repr__(self):
            raise AssertionError("exception_repr_forbidden")

    records = []
    assert_native_failure(
        failing_visit(
            monkeypatch,
            tmp_path,
            Sensitive(SECRET),
            first_failure_sink=records.append,
        )
    )
    assert records[0]["error_category"] == "unknown"
    assert SECRET not in json.dumps(records)


@pytest.mark.parametrize(
    "error",
    [
        cycle._CycleFault("cycle_input_invalid"),
        kis_readonly.KisPaperReadOnlyError("quote_timestamp_unavailable"),
    ],
)
def test_expected_failures_do_not_call_optional_sink(monkeypatch, tmp_path, error):
    result = failing_visit(
        monkeypatch, tmp_path, error, first_failure_sink=lambda _: pytest.fail("expected_failure")
    )
    assert result.status == "unavailable" and result.reason != "native_recovery_required"


def test_callback_failure_after_lock_cleanup_preserves_native_reason(monkeypatch, tmp_path):
    events = []

    @contextmanager
    def lock(_):
        events.append("enter")
        try:
            yield
        finally:
            events.append("cleanup")

    def fail(*_):
        raise RuntimeError(SECRET)

    def sink(_):
        events.append("sink")
        raise PermissionError(SECRET)

    monkeypatch.setattr(cycle, "_unlinked", lambda _: None)
    monkeypatch.setattr(cycle.budget, "_validate_paths", lambda *args: None)
    monkeypatch.setattr(cycle.budget, "_read_json", lambda _: None)
    monkeypatch.setattr(cycle.canary, "exclusive_kis_paper_canary_state_lock", lock)
    monkeypatch.setattr(cycle, "_book", fail)
    assert_native_failure(
        cycle.run_kis_paper_current_stock_cycle(
            **arguments(tmp_path),
            first_failure_sink=sink,
        )
    )
    assert events == ["enter", "cleanup", "sink"]


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(7)])
def test_process_interrupts_are_not_converted_to_normal_outcomes(monkeypatch, tmp_path, error):
    with pytest.raises(type(error)):
        failing_visit(
            monkeypatch,
            tmp_path,
            error,
            first_failure_sink=lambda _: pytest.fail("interrupt_not_diagnostic"),
        )


@pytest.mark.parametrize(
    "filename,namespace",
    [
        (cycle.__file__, {"__name__": cycle.__name__}),
        ("private-secret-path.py", cycle.__dict__),
        (cycle.__file__, cycle.__dict__),
    ],
)
def test_untrusted_code_cannot_spoof_public_frame(filename, namespace):
    # Even matching filename/globals are insufficient without a captured source code object.
    try:
        exec(compile("raise ValueError('sensitive')", filename, "exec"), namespace)
    except ValueError as error:
        value = cycle._first_failure_diagnostic(error)
    assert value == dict(kind="current-stock-first-failure-v1", error_category="value_error")


def test_innermost_trusted_original_frame_and_bounded_trace():
    try:
        cycle._unpack(dict(type="datetime", value=SECRET))
    except ValueError as error:
        value = cycle._first_failure_diagnostic(error)
    line = Path(cycle.__file__).read_text().splitlines()[value["frame"]["line"] - 1]
    assert "datetime.fromisoformat" in line

    def recurse(n):
        if n:
            return recurse(n - 1)
        cycle._unpack(dict(type="datetime", value=SECRET))

    try:
        recurse(40)
    except ValueError as error:
        value = cycle._first_failure_diagnostic(error)
    assert "frame" not in value


@pytest.mark.parametrize(
    "method,expected",
    [
        (lambda: cycle.canary.KisPaperCanaryClient.submit_limit(None, None), "intent.side"),
        (
            lambda: cycle.canary.KisPaperCanaryIntent.from_decision(None, run_id="synthetic"),
            "decision.decision_id",
        ),
    ],
)
def test_real_trusted_canary_methods_preserve_throw_line(method, expected):
    try:
        method()
    except AttributeError as error:
        value = cycle._first_failure_diagnostic(error)
    assert value["error_category"] == "attribute_error"
    assert value["frame"]["module"] == cycle.canary.__name__
    line = Path(cycle.canary.__file__).read_text().splitlines()[value["frame"]["line"] - 1]
    assert expected in line


def test_actual_worker_owner_callback_preserves_throw_line(monkeypatch):
    monkeypatch.setitem(sys.modules, "__main__", current20)
    callback = current20.OwnerAdmission(io.BytesIO(b""), io.StringIO())
    try:
        callback()
    except ValueError as error:
        value = cycle._first_failure_diagnostic(error)
    assert value["error_category"] == "value_error"
    assert value["frame"]["module"] == "scripts.run_current20_paper_candidate_worker"
    line = Path(current20.__file__).read_text().splitlines()[value["frame"]["line"] - 1]
    assert 'raise ValueError("owner_admission_unknown")' in line


def test_known_worker_alias_with_wrong_source_cannot_supply_frame(monkeypatch):
    fake = type(current20)("scripts.run_current20_paper_candidate_worker")
    fake.__file__ = "not-the-public-worker.py"
    monkeypatch.setitem(sys.modules, "__main__", fake)
    try:
        exec(compile("raise ValueError('sensitive')", current20.__file__, "exec"), vars(fake))
    except ValueError as error:
        value = cycle._first_failure_diagnostic(error)
    assert "frame" not in value


def test_known_worker_path_with_forged_code_and_globals_is_not_trusted(monkeypatch):
    fake = type(current20)("scripts.run_current20_paper_candidate_worker")
    fake.__file__ = current20.__file__
    monkeypatch.setitem(sys.modules, "__main__", fake)
    exec(compile("def forged(): raise ValueError('sensitive')", fake.__file__, "exec"), vars(fake))
    try:
        fake.forged()
    except ValueError as error:
        value = cycle._first_failure_diagnostic(error)
    assert "frame" not in value


@pytest.fixture
def output_child(tmp_path, monkeypatch):
    artifact = tmp_path / "artifacts"
    child = artifact / "execution" / "owned-worker" / "wake-1"
    child.mkdir(parents=True)
    monkeypatch.setattr(worker, "ARTIFACT", artifact)
    return child


def test_first_write_is_create_new_and_collision_preserves_original(output_child):
    sink = worker.first_failure_file_sink(output_child)
    first = dict(kind="current-stock-first-failure-v1", error_category="unknown")
    sink(first)
    path = output_child / "first-failure.json"
    before = path.read_bytes()
    assert json.loads(before) == first
    with pytest.raises(FileExistsError):
        sink(dict(first, error_category="type_error"))
    assert path.read_bytes() == before


@pytest.mark.parametrize("fault", ["missing", "outside", "root", "shallow", "linked"])
def test_output_child_is_existing_scoped_and_unlinked(output_child, monkeypatch, fault):
    path = output_child
    if fault == "missing":
        path = path / "missing"
    elif fault == "outside":
        path = output_child.parents[3]
    elif fault == "root":
        path = output_child.parents[1]
    elif fault == "shallow":
        path = output_child.parent
    else:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda self: self == path or original(self))
    with pytest.raises((ValueError, FileNotFoundError, RuntimeError)):
        worker.first_failure_file_sink(path)(
            dict(
                kind="current-stock-first-failure-v1",
                error_category="unknown",
            )
        )
    assert not (path / "first-failure.json").exists()


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "current-stock-first-failure-v1", "error_category": SECRET},
        {"kind": "current-stock-first-failure-v1", "error_category": "unknown", "message": SECRET},
        {
            "kind": "current-stock-first-failure-v1",
            "error_category": "unknown",
            "frame": {"module": SECRET, "line": 1},
        },
        {
            "kind": "current-stock-first-failure-v1",
            "error_category": "unknown",
            "frame": {"module": cycle.__name__, "line": True},
        },
    ],
)
def test_writer_rejects_mutated_or_private_fields(output_child, value):
    with pytest.raises(ValueError):
        worker.first_failure_file_sink(output_child)(value)
    assert list(output_child.iterdir()) == []


@pytest.mark.parametrize("present", [False, True])
def test_file_failure_never_changes_original_native_outcome(
    monkeypatch,
    tmp_path,
    output_child,
    present,
):
    path = output_child / "first-failure.json"
    if present:
        path.write_bytes(b"immutable-first")
    else:
        output_child.rmdir()
    assert_native_failure(
        failing_visit(
            monkeypatch,
            tmp_path,
            RuntimeError(SECRET),
            first_failure_sink=worker.first_failure_file_sink(output_child),
        )
    )
    if present:
        assert path.read_bytes() == b"immutable-first"
    else:
        assert not output_child.exists()


@pytest.mark.parametrize("module", [worker, current20])
def test_workers_default_and_cli_without_execute_have_no_effect(module, monkeypatch, capsys):
    assert module.run(None, first_failure_sink=lambda _: pytest.fail("inert"))["status"] == "inert"
    monkeypatch.setattr(module.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(SECRET.encode())))
    monkeypatch.setattr(module, "run", lambda *a, **k: pytest.fail("inert_cli"))
    args = ["--first-failure-output-child", "missing"] if module is worker else []
    assert module.main(args) == 0
    assert module.sys.stdin.buffer.tell() == 0
    assert json.loads(capsys.readouterr().out) == dict(
        status="inert",
        credential_reads=0,
        broker_calls=0,
    )


@pytest.mark.parametrize("which", ["stock", "current20"])
def test_workers_forward_optional_sink_without_public_abi_changes(which, monkeypatch):
    def sink(_):
        pass

    captured = []
    limits = SimpleNamespace(
        calls=dict(
            token_posts=0,
            get_requests=0,
            buy_posts=0,
            sell_posts=0,
            cancel_posts=0,
        ),
        starts=[],
    )
    config = SimpleNamespace(
        base_url="synthetic", account_number="synthetic", account_product_code="synthetic"
    )
    result = cycle.CurrentStockCycleOutcome("unavailable", "native_recovery_required")

    def native_call(**kwargs):
        captured.append(kwargs)
        return result if which == "stock" else (result,)

    monkeypatch.setattr(worker, "client_factory", lambda *a: None)
    if which == "stock":
        monkeypatch.setattr(worker, "RequestBudget", lambda **k: limits)
        monkeypatch.setattr(cycle, "run_kis_paper_current_stock_cycle", native_call)
        run = worker.run
        extra = {}
    else:
        monkeypatch.setattr(current20, "_helpers", lambda: worker)
        monkeypatch.setattr(
            current20,
            "_api",
            lambda: SimpleNamespace(
                run_current20_paper_visit=native_call,
            ),
        )
        monkeypatch.setattr(current20, "request_budget", lambda **k: limits)
        monkeypatch.setattr(current20, "_host", lambda: None)
        monkeypatch.setattr(
            current20,
            "load_input",
            lambda *a: (
                {},
                SimpleNamespace(input_ref="i", policy_ref="p"),
            ),
        )
        run = current20.run
        extra = dict(
            input_manifest=Path("synthetic"),
            source_manifest=Path("synthetic"),
            owner_ready=lambda: None,
        )
    default = run(config, execute=True, clock=lambda: datetime(2026, 10, 20, tzinfo=UTC), **extra)
    actual = run(
        config,
        execute=True,
        clock=lambda: datetime(2026, 10, 20, tzinfo=UTC),
        first_failure_sink=sink,
        **extra,
    )
    assert "first_failure_sink" not in captured[0]
    assert captured[1]["first_failure_sink"] is sink
    assert actual == default
    assert actual["reason"] == "native_recovery_required"
    assert "error_category" not in actual and "frame" not in actual


def terminal():
    return dict(
        kind=host.KIND,
        status="unavailable",
        reason="native_recovery_required",
        paper_only=True,
        unknown_effects_not_assumed_zero=True,
        request_counts="unknown",
    )


def diagnostic():
    return dict(
        kind="current-stock-first-failure-v1",
        error_category="value_error",
        frame=dict(module="scripts.run_current20_paper_candidate_worker", line=100),
    )


def ipc(monkeypatch, frames, sink=None):
    class Input(io.BytesIO):
        def close(self):
            self.saved = self.getvalue()
            super().close()

    class Process:
        def __init__(self):
            self.stdin = Input()
            self.stdout = io.BytesIO(
                b"".join(
                    value if type(value) is bytes else host._encode(value) + b"\n"
                    for value in frames
                )
            )
            self.code = None
            self.killed = False

        def poll(self):
            return self.code

        def wait(self, **_):
            if self.code is None:
                self.code = 20
            return self.code

        def kill(self):
            self.killed, self.code = True, -1

    process, admissions = Process(), []
    monkeypatch.setattr(host.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(host, "bootstrap", lambda: None)

    def call():
        return host._exchange(
            ["synthetic-no-process"],
            b"synthetic-packet",
            lambda sequence: admissions.append(sequence) or True,
            environment={},
            first_failure_sink=sink,
        )

    return call, process, admissions


@pytest.mark.parametrize("fault", [None, "collision", "permission"])
def test_ipc_diagnostic_persists_once_without_changing_terminal_or_admission(
    monkeypatch,
    tmp_path,
    fault,
):
    path = tmp_path / "first-failure.json"
    if fault == "collision":
        path.write_bytes(b"retained-first")

    def persist(value):
        if fault == "permission":
            raise PermissionError(SECRET)
        host._new(path, host._encode(value))

    call, process, admissions = ipc(
        monkeypatch,
        [
            dict(kind="current20-owner-request-v1", sequence=1),
            diagnostic(),
            terminal(),
        ],
        persist,
    )
    assert call() == terminal()
    assert admissions == [1]
    assert not process.killed and process.poll() == 20
    assert process.stdin.closed and process.stdout.closed
    if fault == "collision":
        assert path.read_bytes() == b"retained-first"
    elif fault == "permission":
        assert not path.exists()
    else:
        assert host._json(path.read_bytes()) == diagnostic()
    assert len(process.stdin.saved.splitlines()) == 2


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "private_extra",
        "category",
        "module",
        "line_bool",
        "line_zero",
        "line_large",
        "unknown_kind",
        "oversized",
        "not_object",
        "invalid_json",
    ],
)
def test_ipc_rejects_malformed_or_duplicate_metadata_without_new_authority(monkeypatch, fault):
    value = diagnostic()
    if fault == "private_extra":
        value["raw"] = SECRET
    elif fault == "category":
        value["error_category"] = SECRET
    elif fault == "module":
        value["frame"]["module"] = SECRET
    elif fault == "line_bool":
        value["frame"]["line"] = True
    elif fault == "line_zero":
        value["frame"]["line"] = 0
    elif fault == "line_large":
        value["frame"]["line"] = 1_000_001
    elif fault == "unknown_kind":
        value["kind"] = "unknown"
    elif fault == "oversized":
        value = b" " * 2048 + host._encode(value) + b"\n"
    elif fault == "not_object":
        value = []
    elif fault == "invalid_json":
        value = b"invalid\n"
    frames = [value, terminal()]
    if fault == "duplicate":
        frames.insert(0, diagnostic())
    records = []
    call, process, admissions = ipc(monkeypatch, frames, records.append)
    with pytest.raises(ValueError):
        call()
    assert admissions == [] and process.killed
    assert len(records) == (1 if fault == "duplicate" else 0)
    assert process.stdin.closed and process.stdout.closed
    assert SECRET not in json.dumps(records)


def test_stdio_sink_is_single_write_and_uses_same_closed_validator():
    output = io.StringIO()
    sink = current20.first_failure_stdio_sink(output)
    with pytest.raises(ValueError):
        sink(dict(diagnostic(), message=SECRET))
    sink(diagnostic())
    sink(dict(diagnostic(), error_category="unknown"))
    assert [json.loads(line) for line in output.getvalue().splitlines()] == [diagnostic()]


def test_f9_main_automatically_uses_metadata_ipc_and_unchanged_terminal(monkeypatch, capsys):
    monkeypatch.setattr(current20, "load_input", lambda *a: None)
    monkeypatch.setattr(current20, "_no_model_runtime", lambda: None)
    monkeypatch.setattr(current20, "_helpers", lambda: SimpleNamespace(parse_packet=lambda _: None))
    monkeypatch.setattr(current20.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"synthetic\n")))

    def run(*args, **kwargs):
        kwargs["first_failure_sink"](diagnostic())
        kwargs["first_failure_sink"](diagnostic())
        return terminal()

    monkeypatch.setattr(current20, "run", run)
    assert current20.main(["--execute", "--owner-admission-stdio"]) == 20
    frames = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert frames == [diagnostic(), terminal()]
