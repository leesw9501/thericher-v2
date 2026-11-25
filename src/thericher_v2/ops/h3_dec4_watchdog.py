"""Native host containment for one Dec4 capsule owner, not BankLeg recovery."""

import ctypes as C
import math
import os
import subprocess
import time
from contextlib import ExitStack
from ctypes import wintypes as W
from dataclasses import dataclass
from pathlib import Path


class _BasicLimits(C.Structure):
    _fields_ = [
        ("cpu", C.c_longlong * 2),
        ("flags", W.DWORD),
        ("working_set_min", C.c_size_t),
        ("working_set_max", C.c_size_t),
        ("active_limit", W.DWORD),
        ("affinity", C.c_size_t),
        ("priority", W.DWORD),
        ("scheduling", W.DWORD),
    ]


class _Limits(C.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", C.c_ulonglong * 6),
        ("memory", C.c_size_t * 4),
    ]


class _Accounting(C.Structure):
    _fields_ = [
        ("cpu", C.c_longlong * 4),
        ("faults", W.DWORD),
        ("total", W.DWORD),
        ("active", W.DWORD),
        ("terminated", W.DWORD),
    ]


class _Startup(C.Structure):
    _fields_ = [
        ("size", W.DWORD),
        ("strings", W.LPWSTR * 3),
        ("geometry", W.DWORD * 8),
        ("show", W.WORD),
        ("reserved_size", W.WORD),
        ("reserved", C.c_void_p),
        ("stdio", W.HANDLE * 3),
        ("attributes", C.c_void_p),
    ]


class _Process(C.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE), ("pid", W.DWORD), ("tid", W.DWORD)]


def _kernel():
    k = C.WinDLL("kernel32", use_last_error=True)
    ptr, handle, dword, size = C.c_void_p, W.HANDLE, W.DWORD, C.c_size_t
    signatures = {
        "CreateJobObjectW": (handle, ptr, W.LPCWSTR),
        "SetInformationJobObject": (W.BOOL, handle, C.c_int, ptr, dword),
        "QueryInformationJobObject": (W.BOOL, handle, C.c_int, ptr, dword, ptr),
        "InitializeProcThreadAttributeList": (W.BOOL, ptr, dword, dword, ptr),
        "UpdateProcThreadAttribute": (W.BOOL, ptr, dword, size, ptr, size, ptr, ptr),
        "DeleteProcThreadAttributeList": (None, ptr),
        "CreateProcessW": (
            W.BOOL,
            W.LPCWSTR,
            W.LPWSTR,
            ptr,
            ptr,
            W.BOOL,
            dword,
            ptr,
            W.LPCWSTR,
            ptr,
            ptr,
        ),
        "GetProcessTimes": (W.BOOL, handle, ptr, ptr, ptr, ptr),
        "ResumeThread": (dword, handle),
        "WaitForSingleObject": (dword, handle, dword),
        "GetExitCodeProcess": (W.BOOL, handle, ptr),
        "TerminateJobObject": (W.BOOL, handle, W.UINT),
        "CloseHandle": (W.BOOL, handle),
    }
    for name, (result, *args) in signatures.items():
        fn = getattr(k, name)
        fn.restype, fn.argtypes = result, args
    return k


def _require(ok, stage):
    if not ok:
        raise OSError(C.get_last_error(), "h3_host_" + stage)


@dataclass(frozen=True, slots=True)
class HostJobResult:
    """A signaled exact root and an empty outer Job, nothing about broker or daemon."""

    pid: int
    native_start: str
    exit_code: int
    # Only EXITED means no supervisor termination was needed.
    disposition: str


def supervise_host(argv, *, env, cwd, deadline, join_seconds=2.0):
    """Run a trusted absolute executable in a hidden, non-breakaway Windows Job.

    The separate caller owns the absolute monotonic deadline. It must provide a
    scoped environment and must not itself hold the worker's BankLeg. No output
    pipes, callbacks, or inherited handles. The worker owns all durable writes.
    The deadline triggers termination, not a guarantee of completion by then;
    the separate bounded join must establish containment before returning proof.
    Service-mediated work is outside this Job. No result authorizes replay,
    daemon closure, BankLeg recovery, or reservation release.
    """
    if os.name != "nt":
        raise RuntimeError("h3_host_windows_required")
    if (
        not isinstance(argv, (tuple, list))
        or not argv
        or any(type(arg) is not str or "\0" in arg for arg in argv)
        or not Path(argv[0]).is_absolute()
        or not Path(cwd).is_absolute()
        or type(env) is not dict
        or any(
            type(k) is not str or type(v) is not str or not k or "=" in k or "\0" in k + v
            for k, v in env.items()
        )
        or len({k.upper() for k in env}) != len(env)
        or type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or type(join_seconds) not in (int, float)
        or not 0 < join_seconds <= 5
    ):
        raise ValueError("h3_host_invalid_launch")
    if time.monotonic() >= deadline:
        raise TimeoutError("h3_host_deadline_before_launch")

    k = _kernel()
    command = C.create_unicode_buffer(subprocess.list2cmdline(argv))
    environment = C.create_unicode_buffer(
        "\0".join(f"{name}={env[name]}" for name in sorted(env, key=str.upper)) + "\0\0"
    )
    with ExitStack() as stack:
        job = k.CreateJobObjectW(None, None)
        _require(job, "job_create")
        stack.callback(k.CloseHandle, job)
        limits = _Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE only
        _require(k.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)), "limits")

        size = C.c_size_t()
        k.InitializeProcThreadAttributeList(None, 1, 0, C.byref(size))
        _require(size.value, "attribute_size")
        attributes = C.create_string_buffer(size.value)
        _require(k.InitializeProcThreadAttributeList(attributes, 1, 0, C.byref(size)), "init")
        stack.callback(k.DeleteProcThreadAttributeList, attributes)
        jobs = (W.HANDLE * 1)(job)
        _require(
            k.UpdateProcThreadAttribute(attributes, 0, 0x2000D, jobs, C.sizeof(jobs), None, None),
            "job_list",
        )
        startup = _Startup()
        startup.size = C.sizeof(startup)
        startup.attributes = C.addressof(attributes)
        proc = _Process()
        if time.monotonic() >= deadline:
            raise TimeoutError("h3_host_deadline_before_launch")
        # Assign at creation, not after CreateProcess. A killed supervisor cannot
        # strand an unassigned root; even a nested Job's suspended child inherits.
        flags = 0x80000 | 0x400 | 0x4 | subprocess.CREATE_NO_WINDOW
        _require(
            k.CreateProcessW(
                argv[0],
                command,
                None,
                None,
                False,
                flags,
                environment,
                os.fspath(cwd),
                C.byref(startup),
                C.byref(proc),
            ),
            "atomic_create",
        )
        stack.callback(k.CloseHandle, proc.process)
        stack.callback(k.CloseHandle, proc.thread)
        stamps = (W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME())
        _require(k.GetProcessTimes(proc.process, *(C.byref(s) for s in stamps)), "birth")
        birth = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime

        def signaled(ms):
            status = k.WaitForSingleObject(proc.process, ms)
            _require(status in (0, 258), "root_wait")
            return status == 0

        def active():
            info = _Accounting()
            _require(
                k.QueryInformationJobObject(job, 1, C.byref(info), C.sizeof(info), None),
                "job_query",
            )
            return info.active

        disposition = "DEADLINE"
        if time.monotonic() < deadline:
            _require(k.ResumeThread(proc.thread) == 1, "root_resume")
            while (left := deadline - time.monotonic()) > 0:
                if signaled(math.ceil(min(left * 1000, 100))):
                    if time.monotonic() < deadline:
                        # The process handle can signal before Job accounting catches up.
                        settle = min(deadline, time.monotonic() + 0.10)
                        while active() and (left := settle - time.monotonic()) > 0:
                            time.sleep(min(left, 0.01))
                        if time.monotonic() < deadline:
                            disposition = "EXITED_WITH_MEMBERS" if active() else "EXITED"
                    break
        if disposition != "EXITED":
            _require(k.TerminateJobObject(job, 20), "job_abort")
            join_deadline = time.monotonic() + join_seconds
            while not (signaled(0) and active() == 0):
                left = join_deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("h3_host_job_join_unproven")
                time.sleep(min(left, 0.01))
        code = W.DWORD()
        _require(k.GetExitCodeProcess(proc.process, C.byref(code)), "exit_code")
        return HostJobResult(proc.pid, f"win-filetime:{birth}", code.value, disposition)
