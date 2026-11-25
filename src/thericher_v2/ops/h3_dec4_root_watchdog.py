"""Bound the exact scheduled root without changing its Scheduler EnginePID."""

import ctypes as c
import hashlib
import os
import subprocess
import time
from ctypes import wintypes as w
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

_ROOT_RIGHTS = 0x101001  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION | TERMINATE
_SET_EVENT = 0x0002
_ARM_SECONDS = 5
_CHILD = r"""
import ctypes as c
import math
import sys
import time
from ctypes import wintypes as w

k = c.WinDLL('kernel32', use_last_error=True)
for name, result, params in (
    ('GetProcessId', w.DWORD, [w.HANDLE]),
    ('GetProcessTimes', w.BOOL, [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4),
    ('SetEvent', w.BOOL, [w.HANDLE]),
    ('WaitForSingleObject', w.DWORD, [w.HANDLE, w.DWORD]),
    ('TerminateProcess', w.BOOL, [w.HANDLE, w.UINT]),
):
    fn = getattr(k, name)
    fn.restype, fn.argtypes = result, params
root, arm, pid, expected_birth = map(int, sys.argv[1:5])
cutoff, monotonic_cutoff = map(float, sys.argv[5:])
stamps = [w.FILETIME() for _ in range(4)]
if k.GetProcessId(root) != pid or not k.GetProcessTimes(root, *(c.byref(x) for x in stamps)):
    sys.exit(30)
if ((stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime) != expected_birth:
    sys.exit(31)
if not math.isfinite(cutoff) or not math.isfinite(monotonic_cutoff) or not k.SetEvent(arm):
    sys.exit(32)
while True:
    left = min(cutoff - time.time(), monotonic_cutoff - time.monotonic())
    result = k.WaitForSingleObject(root, max(0, math.ceil(min(left, 0.1) * 1000)))
    if result == 0:
        sys.exit(0)
    if result != 258:
        sys.exit(33)
    if min(cutoff - time.time(), monotonic_cutoff - time.monotonic()) <= 0:
        if not k.TerminateProcess(root, 20) and k.WaitForSingleObject(root, 0) != 0:
            sys.exit(34)
        sys.exit(0 if k.WaitForSingleObject(root, 2000) == 0 else 35)
"""


@dataclass(frozen=True, slots=True)
class RootWatchdogActor:
    pid: int
    start_ticks: str
    argv_sha256: str


class _RootLease:
    def __init__(self, process, actor, cutoff, monotonic_cutoff):
        self.process = process
        self.actor = actor
        self.cutoff = cutoff
        self.monotonic_cutoff = monotonic_cutoff

    def check(self):
        if (
            self.process.poll() is not None
            or time.time() >= self.cutoff
            or time.monotonic() >= self.monotonic_cutoff
        ):
            raise ValueError("h3_root_watchdog_unavailable")
        return True


def arm_root_watchdog(*, executable, pid, start_ticks, hard_cutoff):
    """Pass restricted handles to one child; never open or terminate by PID.

    The child must attest the root birth before signalling readiness. Only the
    still-owned root and inert event are passed, never a bank/Job/credential
    handle. Root exit is not daemon closure or financial reconciliation.
    """
    if type(hard_cutoff) is not datetime or hard_cutoff.utcoffset() != timedelta(0):
        raise ValueError("h3_root_watchdog_scope")
    cutoff = hard_cutoff.timestamp()
    duration = cutoff - time.time()
    if (
        os.name != "nt"
        or type(pid) is not int
        or pid != os.getpid()
        or type(start_ticks) is not str
        or not start_ticks.isascii()
        or not start_ticks.isdecimal()
        or not 0 < len(start_ticks) <= 19
        or not 0 < duration <= 8 * 60
        or not isinstance(executable, Path)
        or not executable.is_absolute()
        or executable.resolve(strict=True) != executable
    ):
        raise ValueError("h3_root_watchdog_scope")
    monotonic_cutoff = time.monotonic() + duration
    arm_end = min(monotonic_cutoff, time.monotonic() + _ARM_SECONDS)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    for name, result, params in (
        ("GetCurrentProcess", w.HANDLE, []),
        ("GetProcessTimes", w.BOOL, [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4),
        ("CreateEventW", w.HANDLE, [c.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]),
        (
            "DuplicateHandle",
            w.BOOL,
            [w.HANDLE, w.HANDLE, w.HANDLE, c.POINTER(w.HANDLE), w.DWORD, w.BOOL, w.DWORD],
        ),
        ("WaitForSingleObject", w.DWORD, [w.HANDLE, w.DWORD]),
        ("CloseHandle", w.BOOL, [w.HANDLE]),
    ):
        fn = getattr(kernel, name)
        fn.restype, fn.argtypes = result, params

    current = kernel.GetCurrentProcess()
    event = kernel.CreateEventW(None, True, False, None)
    if not event:
        raise ValueError("h3_root_watchdog_arm")
    root_copy, event_copy = w.HANDLE(), w.HANDLE()
    process = None
    armed = False
    try:
        try:
            if not kernel.DuplicateHandle(
                current, current, current, c.byref(root_copy), _ROOT_RIGHTS, True, 0
            ) or not kernel.DuplicateHandle(
                current, event, current, c.byref(event_copy), _SET_EVENT, True, 0
            ):
                raise ValueError("h3_root_watchdog_arm")
            startup = subprocess.STARTUPINFO(
                lpAttributeList={"handle_list": [root_copy.value, event_copy.value]}
            )
            argv = [
                str(executable), "-I", "-S", "-B", "-c", _CHILD,
                str(root_copy.value), str(event_copy.value), str(pid), start_ticks,
                str(cutoff), str(monotonic_cutoff),
            ]
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ},
                cwd=executable.parent,
                startupinfo=startup,
                close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        finally:
            for handle in (root_copy, event_copy):
                if handle:
                    kernel.CloseHandle(handle)
        stamps = [w.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(int(process._handle), *(c.byref(x) for x in stamps)):
            raise ValueError("h3_root_watchdog_arm")
        birth = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
        actor = RootWatchdogActor(
            process.pid,
            str(birth),
            hashlib.sha256(subprocess.list2cmdline(argv).encode()).hexdigest(),
        )
        lease = _RootLease(process, actor, cutoff, monotonic_cutoff)
        while time.monotonic() < arm_end and lease.check():
            waited = kernel.WaitForSingleObject(event, 20)
            if waited == 0:
                lease.check()
                armed = True
                return lease
            if waited != 258:
                break
        raise ValueError("h3_root_watchdog_arm")
    finally:
        kernel.CloseHandle(event)
        if process is not None and not armed:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=2)
