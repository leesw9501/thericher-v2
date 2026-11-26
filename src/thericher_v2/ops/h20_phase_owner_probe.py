"""Pinned, read-only Scheduler probe for the installed H20 exit owner."""

import os
import subprocess
from contextlib import ExitStack
from datetime import UTC, datetime
from hashlib import file_digest
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import ordinary
from thericher_v2.ops.h3_dec4_scheduler_provider import (
    _file_stamp,
    _open_locked,
    _path_stamp,
    _windows_root,
)
from thericher_v2.ops.h20_phase_exit_boundary import TASK
from thericher_v2.ops.h20_phase_host import HARD_STOP, OPENS, _need, _strict_json

_SCRIPT = Path(
    "D:/thericher-v2/model-artifacts/execution/h20-dec1-phase-v2-code-20261126-v1/"
    "READ-EXACT-EXIT-PROFILE.ps1"
)
_SCRIPT_PIN = "a6302da7b28ab3042cd53e21e5ce7bc7a204df4fd7dcfca8f9e5d97295b06ec4"
_PS = Path("C:/Program Files/PowerShell/7/pwsh.exe")
_PS_PIN = "e94166ed9f376559c1359bafb08bc49e463a494c330f67644ec1d9f1ffeb5ee5"
_CREATE_NO_WINDOW = 0x08000000


def _clock():
    return datetime.now(UTC)


def _run(expected, *, pid=None, timeout):
    _need(0 < timeout <= 8)
    root = _windows_root()
    argv = [str(_PS), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(_SCRIPT)]
    if pid is not None:
        argv += ["-ClosedPid", str(pid)]
    with ExitStack() as locked:
        stamps = {}
        for path, pin in ((_PS, _PS_PIN), (_SCRIPT, _SCRIPT_PIN)):
            ordinary(path)
            stamp = _path_stamp(path)
            handle = locked.enter_context(_open_locked(path))
            _need(
                _file_stamp(os.fstat(handle.fileno())) == stamp
                and file_digest(handle, "sha256").hexdigest() == pin
                and _path_stamp(path) == stamp
            )
            stamps[path] = stamp
        # The native file handles deny writes and replacement until the child exits.
        answer = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            cwd=root / "System32",
            env={"SystemRoot": str(root), "TEMP": str(root / "Temp"), "TMP": str(root / "Temp")},
            creationflags=_CREATE_NO_WINDOW,
            timeout=timeout,
        )
        _need(
            answer.returncode == 0
            and not answer.stderr
            and 0 < len(answer.stdout) <= 256
            and _strict_json(answer.stdout) == {"status": expected, "private_custody_read": False}
            and all(_path_stamp(path) == stamp for path, stamp in stamps.items())
        )
    return True


def probe_h20_exit_pre_event():
    """Pre-event exact readiness only, never an owner-closure result."""
    _need(os.name == "nt")
    return _run("PRE_EVENT_EXACT_READY", timeout=8)


def prove_h20_exit_outer_owner_closed(task, pid, *, timeout):
    """No current instance or original PID, not financial or custody closure."""
    _need(
        os.name == "nt"
        and task == TASK
        and type(pid) is int
        and 0 < pid <= 2**31 - 1
        and OPENS <= _clock() < HARD_STOP
    )
    return (
        _run("EXACT_OUTER_NO_CURRENT_INSTANCE_OR_PID", pid=pid, timeout=timeout)
        and OPENS <= _clock() < HARD_STOP
    )
