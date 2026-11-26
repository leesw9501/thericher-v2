import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops import h3_dec4_restore_child as child
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.h3_dec4_observer_lease import Dec4ObserverLease
from thericher_v2.ops.h3_dec4_observer_plan import Dec4ObserverPlan
from thericher_v2.ops.h3_dec4_restore_daemon import Dec4RestoreDaemon
from thericher_v2.ops.paper_scheduled_preflight import ScheduledPaperPlan


def _entry():
    script = Path(__file__).resolve().parents[1] / "scripts/run_h3_dec4_restore_child.py"
    spec = importlib.util.spec_from_file_location("fixture_restore_bootstrap", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_import_executes_verified_bytes_not_later_disk_contents(tmp_path):
    entry = _entry()
    files = {
        entry._ENTRY: b"# entry",
        entry._ZONE: b"TZif-test",
        entry._BINDING: b"# binding",
        "src/thericher_v2/__init__.py": b"# init",
        "src/thericher_v2/known.py": b"sentinel = 'verified'",
    }
    for name, raw in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    pins = {name: entry._sha(raw) for name, raw in files.items()}
    snapshot = entry._snapshot(tmp_path, pins)
    loader = entry._PinnedImports(tmp_path, snapshot)
    (tmp_path / "src/thericher_v2/known.py").write_bytes(b"raise RuntimeError('wrong code')")
    spec = loader.find_spec("thericher_v2.known")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    assert module.sentinel == "verified"
    with pytest.raises(ImportError, match="dependency_unpinned"):
        loader.find_spec("thericher_v2.foreign")
    assert loader.find_spec("pathlib") is None
    with pytest.raises(ValueError):
        entry._snapshot(tmp_path, pins)
    (tmp_path / "src/thericher_v2/known.py").write_bytes(files["src/thericher_v2/known.py"])
    (tmp_path / "src/thericher_v2/foreign.py").write_bytes(b"# extra")
    with pytest.raises(ValueError):
        entry._snapshot(tmp_path, pins)


@pytest.mark.skipif(not Path("C:/").is_absolute(), reason="requires Windows plan paths")
@pytest.mark.parametrize("fault", [None, "receipt_pid", "root", "source", "retirement"])
def test_runtime_waits_for_exact_root_and_rechecks_source_under_held_writer_guard(
    tmp_path, monkeypatch, fault
):
    a, b, c = ("a" * 64, "b" * 64, "c" * 64)
    plan = ScheduledPaperPlan(ROUND, "entry", TASKS["entry"], a, b, c, *_TIMES["entry"])
    observer = Dec4ObserverPlan("entry", str(tmp_path), a, b)
    lease = Dec4ObserverLease(
        observer, Path(observer.output_root), SimpleNamespace(bounded_normal_restore=True)
    )
    daemon = Dec4RestoreDaemon(a, b, tmp_path)
    values = dict(
        observer_plan_sha256=observer.sha256, observer_restore_daemon_sha256=daemon.sha256
    )
    source = SimpleNamespace(
        check=lambda _: values,
        release=lambda *_: dict(source=b, allow_execute=True, actual_financial_admission=False),
    )
    events = []
    status = [True]

    def read(*_, **kwargs):
        assert kwargs["handoff_sha256"] == a
        events.append("handoff")
        return SimpleNamespace(
            owner_pid=41 if fault == "receipt_pid" else 42, owner_native_start="win-filetime:123"
        )

    def wait(**kwargs):
        assert kwargs["pid"] == 42 and kwargs["birth"] == "123"
        events.append("wait")
        return fault != "root"

    @contextmanager
    def hold(record):
        events.append("held")
        assert record == {"invented": True}
        yield lambda: True

    def restore(_lease, *, hold_native_closure, **_kwargs):
        events.append("restore")
        with hold_native_closure({"invented": True}) as check:
            assert check()
            status[0] = False
            assert not check()

    monkeypatch.setattr(child, "read_dec4_restore_owner", read)
    monkeypatch.setattr(child, "wait_for_dec4_normal_root", wait)
    monkeypatch.setattr(child, "restore_dec4_observer_once", restore)
    binding = child.Dec4RestoreChildBinding(
        source, plan, tmp_path, lease, daemon, hold, lambda: fault != "retirement"
    )
    args = ("entry", b, c, a, "9", "10", "42", "123", str(plan.hard_stop.timestamp()), "88")
    if fault is None:
        child.run_dec4_restore_child(binding, args, source_ready=lambda: status[0])
        assert events == ["handoff", "wait", "restore", "held"]
    else:
        status[0] = fault != "source"
        with pytest.raises(pv.Denied):
            child.run_dec4_restore_child(binding, args, source_ready=lambda: status[0])
        assert "restore" not in events
        if fault == "retirement":
            assert events == ["handoff"]
