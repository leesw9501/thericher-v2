import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

from thericher_v2.ops import h20_phase_owner_probe as probe


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    for name in ("PS", "SCRIPT"):
        path = tmp_path / name
        raw = name.encode("ascii")
        path.write_bytes(raw)
        monkeypatch.setattr(probe, "_" + name, path)
        monkeypatch.setattr(probe, "_" + name + "_PIN", sha256(raw).hexdigest())
    monkeypatch.setattr(probe, "_clock", lambda: probe.OPENS)


@pytest.mark.parametrize(
    "fault",
    [None, "wrong_pid", "wrong_task", "early", "drift", "bad_reply", "changed", "timeout"],
)
def test_pinned_outer_probe_writes_no_custody(monkeypatch, fixture, fault):
    calls = []
    pid = True if fault == "wrong_pid" else 123
    task = "other" if fault == "wrong_task" else probe.TASK
    if fault == "early":
        monkeypatch.setattr(probe, "_clock", lambda: probe.OPENS.replace(minute=40))
    if fault == "drift":
        probe._SCRIPT.write_bytes(b"unapproved")

    def run(argv, **kwargs):
        calls.append(argv)
        assert argv[-2:] == ["-ClosedPid", "123"]
        root = probe._windows_root()
        assert kwargs["env"] == {
            "SystemRoot": str(root),
            "TEMP": str(root / "Temp"),
            "TMP": str(root / "Temp"),
        }
        assert kwargs["creationflags"] == probe._CREATE_NO_WINDOW
        assert kwargs["timeout"] == 2.0
        if fault == "timeout":
            raise probe.subprocess.TimeoutExpired(argv, 2)
        if fault == "changed":
            probe._SCRIPT.write_bytes(b"changed")
        status = (
            "PRE_EVENT_EXACT_READY"
            if fault == "bad_reply"
            else ("EXACT_OUTER_NO_CURRENT_INSTANCE_OR_PID")
        )
        raw = json.dumps(dict(status=status, private_custody_read=False)).encode()
        return SimpleNamespace(stdout=raw, stderr=b"", returncode=0)

    monkeypatch.setattr(probe.subprocess, "run", run)
    if fault is None:
        if probe.os.name != "nt":
            pytest.skip("exact native probe requires Windows")
        assert probe.prove_h20_exit_outer_owner_closed(task, pid, timeout=2.0) is True
    else:
        if fault in {"bad_reply", "changed", "timeout"} and probe.os.name != "nt":
            pytest.skip("exact native probe requires Windows")
        with pytest.raises((ValueError, PermissionError, probe.subprocess.TimeoutExpired)):
            probe.prove_h20_exit_outer_owner_closed(task, pid, timeout=2.0)
    if fault in {"wrong_pid", "wrong_task", "early", "drift"}:
        assert calls == []
