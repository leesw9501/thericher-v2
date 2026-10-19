"""Post-folder publication faults only; every operational effect is synthetic."""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "current20_publication_test_host", REPO / "scripts/run_current20_paper_candidate.py"
)
host = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = host
SPEC.loader.exec_module(host)
IDENTITY = "b" * 32
IMAGE = "sha256:" + "a" * 64
PRIVATE = "synthetic-private-never-publish"


class PrivateError(ValueError):
    def __str__(self):
        raise AssertionError("exception_text_forbidden")

    def __repr__(self):
        raise AssertionError("exception_repr_forbidden")


@pytest.fixture(autouse=True)
def no_real_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("real_process_network_or_credential_effect_forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(host.subprocess, "run", deny)
    monkeypatch.setattr(host.subprocess, "Popen", deny)
    monkeypatch.setattr(host, "_docker", deny)
    monkeypatch.setattr(host, "_legacy", deny)
    monkeypatch.setattr(host, "_identity", deny)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    events, writes = [], []
    before = {"synthetic-source": "c" * 64}
    success = dict(status="hold", reason="await_declared_exit", paper_only=True)

    def cleanup(name, identity, environment):
        assert identity == IDENTITY
        events.append(("cleanup", name))
        return True

    def config():
        events.append(("config",))
        return SimpleNamespace(
            app_key=PRIVATE,
            app_secret=PRIVATE,
            account_number="synthetic-account",
            account_product_code="synthetic-product",
        )

    native = SimpleNamespace(
        VOLUMES=("synthetic-owned-volume",),
        cleanup=cleanup,
        os_environment=lambda: {"PATHEXT": ".COM;.EXE;.BAT;.CMD"},
        load_paper_config=config,
    )

    def docker(args, **kwargs):
        events.append(("docker", args[1]))
        assert PRIVATE not in repr(args) + repr(kwargs.get("env"))
        if args[1] == "run":
            assert "--network" in args and args[args.index("--network") + 1] == "none"
            return SimpleNamespace(returncode=0, stdout=host._encode(before))
        assert args[1:3] == ["volume", "inspect"]
        return SimpleNamespace(returncode=0, stdout=b"")

    def admission(**kwargs):
        events.append(("admission", kwargs["context"]["sequence"]))
        assert kwargs["folder"] == folder
        return True

    def exchange(args, packet, admission, **kwargs):
        events.append(("exchange",))
        assert json.loads(packet)["KIS_PAPER_APP_SECRET"] == PRIVATE
        assert kwargs["deadline"] == 145
        return dict(success)

    original_new = host._new

    def new(path, raw):
        writes.append((path, raw))
        return original_new(path, raw)

    monkeypatch.setattr(host, "ARTIFACT", tmp_path)
    monkeypatch.setattr(host, "read_source_manifest", lambda *a: dict(before))
    monkeypatch.setattr(host, "read_input_manifest", lambda *a: {})
    monkeypatch.setattr(host, "_read", lambda *a: b"synthetic-probe")
    monkeypatch.setattr(host, "execution_window", lambda *a: True)
    monkeypatch.setattr(
        host, "_identity", lambda: dict(executable=str(host.PYTHONW), console_window=0)
    )
    monkeypatch.setattr(host, "uuid4", lambda: SimpleNamespace(hex=IDENTITY))
    monkeypatch.setattr(host, "_legacy", lambda: native)
    monkeypatch.setattr(host, "command", lambda *a, **kw: ["synthetic-worker"])
    monkeypatch.setattr(host, "launch_argv", lambda **kw: ["synthetic-pythonw", "synthetic-host"])
    monkeypatch.setattr(host, "_docker", docker)
    monkeypatch.setattr(host, "owner_admission", admission)
    monkeypatch.setattr(host, "_exchange", exchange)
    monkeypatch.setattr(host, "source_map", lambda: dict(before))
    monkeypatch.setattr(host, "_new", new)
    folder = tmp_path / host.RUNTIME_RELATIVE / "runs" / IDENTITY

    def invoke():
        return host.run(
            execute=True,
            image=IMAGE,
            source_manifest=tmp_path / "source.json",
            source_manifest_ref=IMAGE,
            input_manifest=tmp_path / "input.json",
            input_manifest_ref=IMAGE,
            owner_probe=tmp_path / "probe.ps1",
            owner_probe_ref=IMAGE,
            clock=lambda: datetime(2026, 10, 19, 16, tzinfo=UTC),
            monotonic=lambda: 0,
        )

    return SimpleNamespace(
        invoke=invoke,
        folder=folder,
        events=events,
        writes=writes,
        native=native,
        success=success,
        docker=docker,
        before=before,
    )


def assert_record(rig, result):
    assert len(rig.writes) == 1
    assert rig.writes[0][0] == rig.folder / "result.json"
    assert json.loads((rig.folder / "result.json").read_bytes()) == result
    assert PRIVATE not in (rig.folder / "result.json").read_text()
    if result["status"] == "unavailable":
        assert set(result) == {"status", "reason", "paper_only", "unknown_effects_not_assumed_zero"}
        assert result["unknown_effects_not_assumed_zero"] is True
        assert "calls" not in result


@pytest.mark.parametrize("raises", [False, True])
def test_prefix_denied_or_exception_publishes_same_folder_without_credentials(
    rig, monkeypatch, raises
):
    def admission(**kwargs):
        if raises:
            raise PrivateError(PRIVATE)
        return False

    monkeypatch.setattr(host, "owner_admission", admission)
    result = rig.invoke()
    expected = host._failure() if raises else host._failure("owner_admission_unavailable")
    assert result == expected
    assert_record(rig, result)
    assert not any(event[0] in {"config", "exchange"} for event in rig.events)
    assert [event for event in rig.events if event[0] == "cleanup"] == [
        ("cleanup", host.PREFIX + "source-" + IDENTITY)
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "context",
        "probe_exception",
        "probe_nonzero",
        "probe_empty",
        "probe_mismatch",
        "probe_oversize",
        "volume",
        "config",
        "packet",
        "exchange",
        "source_changed",
    ],
)
def test_each_post_folder_failure_has_one_safe_final_record(rig, monkeypatch, fault):
    def fail(*args, **kwargs):
        raise PrivateError(PRIVATE)

    if fault == "context":
        monkeypatch.setattr(host, "launch_argv", fail)
    elif fault.startswith("probe_") or fault == "volume":

        def docker(args, **kwargs):
            if fault == "volume" and args[1] == "volume":
                fail()
            if args[1] != "run" or fault == "volume":
                return rig.docker(args, **kwargs)
            if fault == "probe_exception":
                fail()
            return SimpleNamespace(
                returncode=1 if fault == "probe_nonzero" else 0,
                stdout={
                    "probe_nonzero": b"",
                    "probe_empty": b"",
                    "probe_mismatch": b"{}",
                    "probe_oversize": b"x" * (1024 * 1024 + 1),
                }[fault],
            )

        monkeypatch.setattr(host, "_docker", docker)
    elif fault == "config":
        monkeypatch.setattr(rig.native, "load_paper_config", fail)
    elif fault == "packet":
        original = host._encode

        def encode(value):
            if "KIS_PAPER_APP_KEY" in value:
                fail()
            return original(value)

        monkeypatch.setattr(host, "_encode", encode)
    elif fault == "exchange":
        monkeypatch.setattr(host, "_exchange", fail)
    else:
        monkeypatch.setattr(host, "source_map", lambda: {})
    result = rig.invoke()
    assert result == host._failure()
    assert_record(rig, result)


@pytest.mark.parametrize("actor", ["source", "worker"])
@pytest.mark.parametrize("raises", [False, True])
def test_cleanup_false_or_exception_overrides_result(rig, monkeypatch, actor, raises):
    original = rig.native.cleanup

    def cleanup(name, *args):
        if ("source-" in name) == (actor == "source"):
            if raises:
                raise PrivateError(PRIVATE)
            return False
        return original(name, *args)

    monkeypatch.setattr(rig.native, "cleanup", cleanup)
    result = rig.invoke()
    assert result == host._failure("worker_cleanup_unresolved")
    assert_record(rig, result)
    if actor == "source":
        assert not any(event[0] in {"config", "exchange"} for event in rig.events)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize(
    "stage", ["probe", "exchange", "source_changed", "cleanup", "source_cleanup"]
)
def test_interrupts_propagate_after_safe_failure_publication(rig, monkeypatch, interrupt, stage):
    def fail(*args, **kwargs):
        raise interrupt()

    if stage == "probe":
        monkeypatch.setattr(host, "_docker", fail)
    elif stage == "exchange":
        monkeypatch.setattr(host, "_exchange", fail)
    elif stage == "source_changed":
        monkeypatch.setattr(host, "source_map", fail)
    else:
        original = rig.native.cleanup

        def cleanup(name, *args):
            if ("source-" in name) == (stage == "source_cleanup"):
                fail()
            return original(name, *args)

        monkeypatch.setattr(rig.native, "cleanup", cleanup)
    with pytest.raises(interrupt):
        rig.invoke()
    expected = (
        host._failure("worker_cleanup_unresolved")
        if stage in {"cleanup", "source_cleanup"}
        else host._failure()
    )
    assert_record(rig, expected)


@pytest.mark.parametrize("actor", ["source", "worker"])
@pytest.mark.parametrize("raises", [False, True])
def test_cleanup_uncertainty_precedes_an_original_operation_failure(
    rig, monkeypatch, actor, raises
):
    def fail(*args, **kwargs):
        raise PrivateError(PRIVATE)

    monkeypatch.setattr(host, "_docker" if actor == "source" else "_exchange", fail)
    original = rig.native.cleanup

    def cleanup(name, *args):
        if ("source-" in name) == (actor == "source"):
            if raises:
                fail()
            return False
        return original(name, *args)

    monkeypatch.setattr(rig.native, "cleanup", cleanup)
    result = rig.invoke()
    assert result == host._failure("worker_cleanup_unresolved")
    assert_record(rig, result)


def test_success_retains_guards_and_result_then_refuses_overwrite(rig):
    result = rig.invoke()
    assert result == rig.success
    assert_record(rig, result)
    kinds = [event[0] for event in rig.events]
    assert kinds.index("admission") < kinds.index("config") < kinds.index("exchange")
    assert [event for event in rig.events if event[0] == "cleanup"] == [
        ("cleanup", host.PREFIX + "source-" + IDENTITY),
        ("cleanup", host.PREFIX + IDENTITY),
    ]
    raw = (rig.folder / "result.json").read_bytes()
    with pytest.raises(FileExistsError):
        rig.invoke()
    assert (rig.folder / "result.json").read_bytes() == raw
    assert len(rig.writes) == 1


@pytest.mark.parametrize("stage", ["source", "input", "probe_pin", "physical", "command"])
def test_pre_folder_errors_stay_exceptions_without_invented_run(rig, monkeypatch, stage):
    def fail(*args, **kwargs):
        raise PrivateError(PRIVATE)

    name = {
        "source": "read_source_manifest",
        "input": "read_input_manifest",
        "probe_pin": "_read",
        "physical": "_identity",
        "command": "command",
    }[stage]
    monkeypatch.setattr(host, name, fail)
    with pytest.raises(PrivateError):
        rig.invoke()
    assert not rig.folder.exists()
    assert rig.writes == []


@pytest.mark.parametrize(
    "identity",
    [
        dict(executable="synthetic-foreign-python", console_window=0),
        dict(executable=str(host.PYTHONW), console_window=1),
    ],
)
def test_physical_identity_guard_still_precedes_run_creation(rig, monkeypatch, identity):
    monkeypatch.setattr(host, "_identity", lambda: identity)
    with pytest.raises(ValueError, match="^physical_quiet_pythonw_required$"):
        rig.invoke()
    assert not rig.folder.exists()
    assert rig.writes == []


def test_publication_collision_never_overwrites_or_retries(rig, monkeypatch):
    original = host._exchange

    def exchange(*args, **kwargs):
        result = original(*args, **kwargs)
        (rig.folder / "result.json").write_bytes(b"immutable-prior-record")
        return result

    monkeypatch.setattr(host, "_exchange", exchange)
    with pytest.raises(FileExistsError):
        rig.invoke()
    assert len(rig.writes) == 1
    assert (rig.folder / "result.json").read_bytes() == b"immutable-prior-record"
