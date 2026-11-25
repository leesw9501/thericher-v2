import json
import os
import runpy
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution import paper_peer_visit
from thericher_v2.ops import h3_dec4_point_join as join
from thericher_v2.ops import h3_dec4_point_owner as owner
from thericher_v2.ops.h3_dec4_watchdog import supervise_host

ENTRY = Path(__file__).resolve().parents[1] / "scripts/run_h3_dec4_supervised_point.py"
PINS = (r"C:\base\pythonw.exe", "a" * 64, "b" * 64, "c" * 64, "d" * 64)
PARENT = "win-filetime:100"
CHILD = "win-filetime:200"


@pytest.fixture
def launcher():
    return runpy.run_path(str(ENTRY))["_run"].__globals__


@pytest.fixture
def bound(launcher, tmp_path, monkeypatch):
    source, control = tmp_path / "source-v3", tmp_path / "point-control-v3"
    source.mkdir()
    control.mkdir()
    clock = SimpleNamespace(value=owner.OPENS, now=lambda _: clock.value)
    monkeypatch.setitem(launcher, "datetime", clock)
    monkeypatch.setitem(launcher, "SOURCE", source)
    monkeypatch.setitem(launcher, "CONTROL", control)
    monkeypatch.setitem(launcher, "_runtime", lambda pins, args: lambda: pins == PINS)
    monkeypatch.setattr(paper_peer_visit, "process_start", lambda p: {12: PARENT, 34: CHILD}[p])
    monkeypatch.setattr(os, "getpid", lambda: 12)
    monkeypatch.setattr(sys, "argv", [str(ENTRY), "supervise", *PINS])
    return clock, source, control


def test_only_join_return_is_published(launcher, bound, monkeypatch):
    _, source, control = bound
    seen = []

    def supervise(**kwargs):
        seen.append(kwargs)
        assert not list(control.iterdir()) and kwargs.pop("owner_ready")()
        assert kwargs == dict(
            argv=(
                PINS[0],
                "-I",
                "-S",
                "-B",
                str(source / launcher["ENTRY"]),
                "child",
                *PINS,
                "12",
                PARENT,
            ),
            cwd=source,
            control=control,
            point_source_sha256=PINS[2],
        )
        return "e" * 64

    monkeypatch.setattr(join, "supervise_dec4_point", supervise)
    assert launcher["main"]() == 0
    assert (control / launcher["HANDOFF"]).read_bytes() == b"e" * 64
    assert launcher["main"]() == 20
    assert len(seen) == 1


@pytest.mark.parametrize("failure", ["job", "late", "malformed", "prior_pending", "early"])
def test_denial_never_publishes_handoff(launcher, bound, monkeypatch, failure):
    clock, _, control = bound

    def supervise(**_):
        assert failure in {"job", "late", "malformed"}
        (control / "POINT-LAUNCH.json").write_bytes(b"consumed")
        if failure == "job":
            raise TimeoutError
        if failure == "late":
            clock.value = owner.HARD_STOP
        return "e" * 64 if failure == "late" else "invalid"

    if failure == "early":
        clock.value -= timedelta(microseconds=1)
        monkeypatch.setitem(launcher, "_runtime", lambda *a: pytest.fail("early bootstrap"))
    if failure == "prior_pending":
        (control / (launcher["HANDOFF"] + ".pending")).touch()
    monkeypatch.setattr(join, "supervise_dec4_point", supervise)
    assert launcher["main"]() == 20
    assert not (control / launcher["HANDOFF"]).exists()
    assert (control / "POINT-LAUNCH.json").exists() == (failure in {"job", "late", "malformed"})


@pytest.mark.parametrize(
    "fault", [None, "job", "parent", "birth", "env", "argv", "command", "link"]
)
def test_child_only_forwards_exact_join_binding(launcher, bound, monkeypatch, fault):
    _, source, control = bound
    monkeypatch.setattr(os, "getpid", lambda: 34)
    monkeypatch.setattr(os, "getppid", lambda: 13 if fault == "parent" else 12)
    monkeypatch.setitem(launcher, "_in_job", lambda: fault != "job")
    env = {"SystemRoot": r"C:\Windows"}
    monkeypatch.setattr(os, "environ", env | ({"UNEXPECTED": "invented"} if fault == "env" else {}))
    argv = launcher["_child_argv"](PINS, 12, PARENT if fault != "birth" else CHILD)
    command = owner._sha(owner._json([argv, str(source), env]))
    raw = owner._json({"command_sha256": "0" * 64 if fault == "command" else command})
    launch_pin = "0" * 64 if fault == "link" else owner._sha(raw)
    (control / "POINT-LAUNCH.json").write_bytes(raw)
    monkeypatch.setattr(sys, "orig_argv", [*argv, launch_pin if fault != "argv" else "wrong"])
    monkeypatch.setattr(sys, "argv", [argv[4], *argv[5:], launch_pin])
    calls = []

    def closure(probe):
        assert probe(12) == PARENT
        return lambda *facts: facts == (56, "win-filetime:300", "e" * 64)

    def child(**kwargs):
        calls.append(kwargs)
        assert kwargs.pop("owner_ready")()
        assert kwargs.pop("data_owner_closed")(56, "win-filetime:300", "e" * 64)
        assert kwargs == dict(
            control=control, point_source_sha256=PINS[2], launch_sha256=launch_pin
        )

    monkeypatch.setitem(launcher, "_data_closure", closure)
    monkeypatch.setattr(join, "run_supervised_point_child", child)
    assert launcher["main"]() == (0 if fault is None else 20)
    assert len(calls) == (fault is None)
    assert not (control / launcher["HANDOFF"]).exists()


def test_manifest_rejects_wrong_pin_members_and_extra_bytecode(launcher, tmp_path, monkeypatch):
    monkeypatch.setitem(launcher, "SOURCE", tmp_path)
    members = {}
    for key in launcher["REQUIRED"]:
        path = tmp_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# fixture\n")
        members[key] = owner._sha(path.read_bytes())
    raw = owner._json(
        dict(schema="H3_DEC4_SUPERVISED_POINT_SOURCE_V1", run=launcher["NAME"], files=members)
    )
    (tmp_path / "SOURCE.json").write_bytes(raw)
    pin = owner._sha(raw)
    verify = launcher["_verify_source"]
    verify(pin)
    with pytest.raises(ValueError):
        verify("0" * 64)
    extra = tmp_path / "src/thericher_v2/__pycache__"
    extra.mkdir()
    with pytest.raises(ValueError):
        verify(pin)
    extra.rmdir()
    (tmp_path / launcher["ENTRY"]).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        verify(pin)


def test_runtime_requires_pinned_bootstrap_and_rechecks_control_identity(
    launcher, tmp_path, monkeypatch
):
    exe = tmp_path / "pythonw.exe"
    source, control, site = (tmp_path / name for name in ("source", "control", "site"))
    entry = source / launcher["ENTRY"]
    pins = (str(exe), *PINS[1:])
    args = ("supervise", *pins)
    flags = SimpleNamespace(isolated=1, no_site=1)
    runtime = SimpleNamespace(
        executable=str(exe),
        _base_executable=str(exe),
        flags=flags,
        dont_write_bytecode=True,
        orig_argv=[str(exe), *launcher["FLAGS"], str(entry), *args],
        modules={},
        path=[],
    )
    monkeypatch.chdir(source.parent)
    for key, value in dict(
        sys=runtime,
        os=SimpleNamespace(name="nt"),
        SOURCE=source,
        CONTROL=control,
        SITE=site,
        __file__=str(entry),
    ).items():
        monkeypatch.setitem(launcher, key, value)
    monkeypatch.setitem(launcher, "_path", lambda p, **kw: (1, 2))
    monkeypatch.setitem(launcher, "_acl_sha256", {source: PINS[3], control: PINS[4]}.__getitem__)
    monkeypatch.setitem(launcher, "_read", lambda p, limit: b"exe" if p == exe else b"source")
    monkeypatch.setitem(launcher, "_sha", {b"exe": PINS[1], b"source": PINS[2]}.__getitem__)
    monkeypatch.setitem(launcher, "_verify_source", lambda pin: None)
    bootstrap = launcher["_runtime"]
    with pytest.raises(ValueError):
        bootstrap(pins, args)
    source.mkdir()
    monkeypatch.chdir(source)
    runtime._base_executable = str(exe.with_name("redirector.exe"))
    with pytest.raises(ValueError):
        bootstrap(pins, args)
    runtime._base_executable = str(exe)
    ready = bootstrap(pins, args)
    assert ready() and runtime.path == [str(source / "src"), str(site)]
    monkeypatch.setitem(launcher, "_path", lambda p, **kw: (1, 3 if p == control else 2))
    assert not ready()


def test_frozen_data_closure_is_loaded_by_digest_only(launcher, tmp_path, monkeypatch):
    source = tmp_path / "source"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    writer = scripts / "run_h3_nov27_data_owner.py"
    manifest = source / "SOURCE.json"
    manifest.write_bytes(b"invented frozen Data source")
    pin = owner._sha(manifest.read_bytes())
    writer.write_text(
        f"""from pathlib import Path
DEC3_SOURCE = Path({str(source)!r})
def verify_source(root, pin, *, dec3):
    assert dec3 and root == DEC3_SOURCE and pin == {pin!r}
""",
        encoding="ascii",
    )
    run = tmp_path / "run"
    claim = run / "owner" / "ATTEMPT.json"
    claim.parent.mkdir(parents=True)
    claim.write_bytes(
        owner._json(dict(schema="H3_DEC3_DATA_ATTEMPT_V1", source_sha256=pin, pid=19))
    )
    receipt = run / "OWNER-CLOSED.json"
    receipt.write_bytes(
        owner._json(
            dict(
                schema="H3_DEC3_OWNER_CLOSED_V1",
                source_sha256=pin,
                attempt_sha256=owner._sha(claim.read_bytes()),
                native_start="win-filetime:50",
            )
        )
    )
    digest = owner._sha(receipt.read_bytes())
    monkeypatch.setitem(launcher, "DEC3_SOURCE", source)
    monkeypatch.setitem(launcher, "DEC3_WRITER_PIN", owner._sha(writer.read_bytes()))
    monkeypatch.setitem(launcher, "DEC3_PIN", pin)
    closure = launcher["_data_closure"](lambda pid: None)
    assert closure(19, "win-filetime:50", digest)
    assert not closure(18, "win-filetime:50", digest)
    assert not closure(19, "win-filetime:51", digest)
    assert not launcher["_data_closure"](lambda _pid: "win-filetime:50")(
        19, "win-filetime:50", digest
    )
    manifest.write_bytes(b"changed")
    assert not closure(19, "win-filetime:50", digest)
    writer.write_bytes(b"raise AssertionError('must not execute')")
    with pytest.raises(ValueError):
        launcher["_data_closure"](lambda pid: None)


@pytest.mark.skipif(os.name != "nt", reason="native Windows security descriptor")
def test_acl_pin_requires_protected_directory_and_detects_change(launcher, tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    icacls = Path(os.environ["SystemRoot"]) / "System32/icacls.exe"

    def inheritance(mode):
        subprocess.run(
            [str(icacls), str(control), f"/inheritance:{mode}"],
            check=True,
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    inheritance("d")
    pin = launcher["_acl_sha256"](control)
    assert launcher["_digest"](pin) and launcher["_acl_sha256"](control) == pin
    inheritance("e")
    with pytest.raises(ValueError):
        launcher["_acl_sha256"](control)


@pytest.mark.skipif(os.name != "nt", reason="native Windows pythonw Job")
def test_native_job_gives_direct_pythonw_exact_identity_and_environment(tmp_path):
    base = Path(sys._base_executable).with_name("pythonw.exe")
    probe = tmp_path / "probe.py"
    marker = tmp_path / "marker.json"
    probe.write_text(
        """import json, os, pathlib, runpy, sys
entry, marker = sys.argv[1:]
launcher = runpy.run_path(entry)
assert sys.executable == sys._base_executable
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert launcher['_in_job']()
pathlib.Path(marker).write_text(json.dumps([sys.orig_argv, os.getppid(), sorted(os.environ),
                                           str(pathlib.Path.cwd())]), encoding='ascii')
""",
        encoding="ascii",
    )
    argv = (str(base), "-I", "-S", "-B", str(probe), str(ENTRY), str(marker))
    result = supervise_host(
        argv,
        cwd=tmp_path,
        env={"SystemRoot": os.environ["SystemRoot"]},
        deadline=time.monotonic() + 10,
    )
    assert (result.disposition, result.exit_code) == ("EXITED", 0)
    assert json.loads(marker.read_bytes()) == [
        list(argv),
        os.getpid(),
        ["SYSTEMROOT"],
        str(tmp_path),
    ]
