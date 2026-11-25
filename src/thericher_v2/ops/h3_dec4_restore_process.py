"""Arm a separately source-pinned, credential-free normal restore process."""

import ctypes as c
import hashlib
import math
import os
import subprocess
import time
from contextlib import ExitStack
from ctypes import wintypes as w
from dataclasses import dataclass
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import _hash, digest

_ROOT_RIGHTS = 0x101000  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION; never TERMINATE
_EVENT_RIGHTS = 2


def _need(ok):
    if not ok:
        raise ValueError("h3_restore_process_unavailable")


def _kernel():
    k = c.WinDLL("kernel32", use_last_error=True)
    handle, ptr, uint, yes = w.HANDLE, c.c_void_p, w.DWORD, w.BOOL
    for name, result, params in (
        ("OpenProcess", handle, (uint, yes, uint)),
        ("GetProcessId", uint, (handle,)),
        ("GetProcessTimes", yes, (handle, *([c.POINTER(w.FILETIME)] * 4))),
        ("GetExitCodeProcess", yes, (handle, c.POINTER(uint))),
        ("CreateEventW", handle, (ptr, yes, yes, w.LPCWSTR)),
        ("GetCurrentProcess", handle, ()),
        ("DuplicateHandle", yes, (handle, handle, handle, c.POINTER(handle), uint, yes, uint)),
        ("SetEvent", yes, (handle,)),
        ("WaitForSingleObject", uint, (handle, uint)),
        ("CloseHandle", yes, (handle,)),
    ):
        fn = getattr(k, name)
        fn.restype, fn.argtypes = result, params
    return k


def _birth(k, handle):
    times = [w.FILETIME() for _ in range(4)]
    _need(bool(k.GetProcessTimes(handle, *(c.byref(stamp) for stamp in times))))
    return str(times[0].dwHighDateTime << 32 | times[0].dwLowDateTime)


@dataclass(frozen=True, slots=True)
class RestoreProcessActor:
    pid: int
    start_ticks: str
    argv_sha256: str


@dataclass(slots=True)
class _Armed:
    process: subprocess.Popen
    actor: RestoreProcessActor

    def check(self):
        _need(self.process.poll() is None)
        return True


@dataclass(frozen=True, slots=True, repr=False)
class Dec4RestoreProcess:
    executable: Path
    executable_sha256: str
    script: Path
    script_sha256: str

    @property
    def sha256(self):
        return digest(
            {
                "schema": "h3-dec4-restore-process-v1",
                "exe": str(self.executable),
                "exe_sha256": self.executable_sha256,
                "script": str(self.script),
                "script_sha256": self.script_sha256,
            }
        )

    def arm(self, *, pid, start_ticks, cutoff, phase, source, release, handoff):
        from thericher_v2.ops.h3_dec4_scheduler_provider import (
            _file_stamp,
            _open_locked,
            _path_stamp,
        )

        _need(
            os.name == "nt"
            and pid == os.getpid()
            and phase in ("entry", "exit")
            and all(
                _hash(pin)
                for pin in (source, release, handoff, self.executable_sha256, self.script_sha256)
            )
            and type(cutoff) in (int, float)
            and math.isfinite(cutoff)
            and all(
                isinstance(p, Path) and p.is_absolute() and p.resolve(strict=True) == p
                for p in (self.executable, self.script)
            )
        )
        seconds = cutoff - time.time()
        _need(0 < seconds <= 8 * 60)
        mono = time.monotonic() + seconds
        k = _kernel()
        process, armed = None, False
        with ExitStack() as stack:
            pins = {self.executable: self.executable_sha256, self.script: self.script_sha256}
            stamps = {}
            for path, pin in pins.items():
                before = _path_stamp(path)
                file = stack.enter_context(_open_locked(path))
                _need(
                    _file_stamp(os.fstat(file.fileno())) == before
                    and hashlib.file_digest(file, "sha256").hexdigest() == pin
                    and _path_stamp(path) == before
                )
                stamps[path] = before
            root = k.OpenProcess(_ROOT_RIGHTS, True, pid)
            _need(bool(root))
            stack.callback(k.CloseHandle, root)
            _need(k.GetProcessId(root) == pid and _birth(k, root) == start_ticks)
            event = k.CreateEventW(None, True, False, None)
            _need(bool(event))
            stack.callback(k.CloseHandle, event)
            current, event_child = k.GetCurrentProcess(), w.HANDLE()
            _need(
                bool(
                    k.DuplicateHandle(
                        current, event, current, c.byref(event_child), _EVENT_RIGHTS, True, 0
                    )
                )
            )
            stack.callback(k.CloseHandle, event_child)
            argv = [
                str(self.executable),
                "-I",
                "-S",
                "-B",
                str(self.script),
                phase,
                source,
                release,
                handoff,
                str(root),
                str(event_child.value),
                str(pid),
                start_ticks,
                str(cutoff),
                str(mono),
            ]
            startup = subprocess.STARTUPINFO(
                lpAttributeList={"handle_list": [root, event_child.value]}
            )
            try:
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={
                        key: os.environ[key]
                        for key in ("SystemRoot", "WINDIR")
                        if key in os.environ
                    },
                    cwd=self.script.parent,
                    startupinfo=startup,
                    close_fds=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                actor = RestoreProcessActor(
                    process.pid,
                    _birth(k, int(process._handle)),
                    hashlib.sha256(subprocess.list2cmdline(argv).encode()).hexdigest(),
                )
                end = min(mono, time.monotonic() + 3)
                while time.monotonic() < end and process.poll() is None:
                    state = k.WaitForSingleObject(event, 20)
                    if state == 0:
                        lease = _Armed(process, actor)
                        _need(
                            lease.check()
                            and time.monotonic() < end
                            and time.time() < cutoff
                            and all(_path_stamp(path) == stamp for path, stamp in stamps.items())
                        )
                        armed = True
                        return lease
                    _need(state == 258)
                _need(False)
            finally:
                if process is not None and not armed:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=2)


def wait_for_dec4_normal_root(*, root, arm, pid, birth, cutoff, monotonic_cutoff):
    """Call after protected child preflight, before any restore. Consumes both handles."""
    _need(os.name == "nt" and root != arm and all(type(h) is int and h > 0 for h in (root, arm)))
    k = _kernel()
    try:
        _need(
            k.GetProcessId(root) == pid
            and _birth(k, root) == birth
            and k.WaitForSingleObject(root, 0) == 258
            and all(
                type(t) in (int, float) and math.isfinite(t) for t in (cutoff, monotonic_cutoff)
            )
            and 0 < min(cutoff - time.time(), monotonic_cutoff - time.monotonic()) <= 8 * 60
            and bool(k.SetEvent(arm))
        )
        while True:
            left = min(cutoff - time.time(), monotonic_cutoff - time.monotonic())
            _need(left > 0)
            state = k.WaitForSingleObject(root, math.ceil(min(left, 0.1) * 1000))
            if state == 0:
                status = w.DWORD()
                _need(
                    bool(k.GetExitCodeProcess(root, c.byref(status)))
                    and status.value == 0
                    and time.time() < cutoff
                    and time.monotonic() < monotonic_cutoff
                )
                return True
            _need(state == 258)
    finally:
        k.CloseHandle(arm)
        k.CloseHandle(root)
