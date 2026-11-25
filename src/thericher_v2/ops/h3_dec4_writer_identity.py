"""Join the Dec4 Paper launcher's exact actors to the R8 scoped census.

This supplies owned keys to the writer guard, not a writer decision. The caller
still owns source-pinned collection, freshness, mount scope, and observer checks.
"""

from __future__ import annotations

import ctypes as c
import hashlib
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from ctypes import wintypes as w
from dataclasses import dataclass
from typing import Protocol

from thericher_v2.execution.paper_peer_visit import digest
from thericher_v2.ops.h3_dec4_guest_identity import CapsuleProcess as CapsuleProcess
from thericher_v2.ops.h3_dec4_restore_process import RestoreProcessActor
from thericher_v2.ops.h3_dec4_root_watchdog import RootWatchdogActor

_EPOCH = 504911232000000000
_DOCKER = (
    "C:/Program Files/Docker/Docker/resources/bin/docker.exe",
    "--host",
    "npipe:////./pipe/dockerDesktopLinuxEngine",
)
OwnedKey = tuple[int, str, str]


def _need(condition: bool, category: str) -> None:
    if not condition:
        raise ValueError("h3_writer_" + category)


def _pid(value: object) -> bool:
    return type(value) is int and 0 < value <= 0xFFFFFFFF


def _hex(value: object, size: int = 64) -> bool:
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{size}}}", value) is not None


def _ticks(value: object) -> int:
    if type(value) is int:
        value = str(value)
    if type(value) is not str or not re.fullmatch(r"[1-9][0-9]{0,18}", value):
        return 0
    return int(value) if int(value) <= 2**63 - 1 else 0


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _path(value: str) -> str:
    return value.replace("\\", "/").casefold()


@dataclass(frozen=True)
class WindowsActor:
    pid: int
    filetime: str
    raw_command_sha256: str
    parsed_argv_sha256: str
    image: str


class _UnicodeString(c.Structure):
    _fields_ = [("length", w.USHORT), ("maximum", w.USHORT), ("buffer", c.c_void_p)]


def read_windows_actor(pid: int) -> WindowsActor:
    """Read only an explicit PID, on one live handle; no raw argv leave here."""
    _need(os.name == "nt" and _pid(pid), "native_actor_unavailable")
    k, nt, shell = c.WinDLL("kernel32"), c.WinDLL("ntdll"), c.WinDLL("shell32")
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    k.WaitForSingleObject.restype = w.DWORD
    k.GetProcessTimes.argtypes = [w.HANDLE, *([c.POINTER(w.FILETIME)] * 4)]
    k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
    k.LocalFree.argtypes = [c.c_void_p]
    k.LocalFree.restype = c.c_void_p
    nt.NtQueryInformationProcess.argtypes = [
        w.HANDLE,
        w.ULONG,
        c.c_void_p,
        w.ULONG,
        c.POINTER(w.ULONG),
    ]
    nt.NtQueryInformationProcess.restype = w.LONG
    shell.CommandLineToArgvW.argtypes = [w.LPCWSTR, c.POINTER(c.c_int)]
    shell.CommandLineToArgvW.restype = c.POINTER(w.LPWSTR)

    handle = k.OpenProcess(0x101000, False, pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
    _need(bool(handle), "native_actor_unavailable")
    try:
        stamps = [w.FILETIME() for _ in range(4)]
        _need(
            k.WaitForSingleObject(handle, 0) == 258
            and bool(k.GetProcessTimes(handle, *(c.byref(t) for t in stamps))),
            "native_actor_unavailable",
        )
        birth = stamps[0].dwHighDateTime << 32 | stamps[0].dwLowDateTime
        size = w.DWORD(32768)
        image = c.create_unicode_buffer(size.value)
        _need(
            bool(k.QueryFullProcessImageNameW(handle, 0, image, c.byref(size))),
            "native_actor_unavailable",
        )
        needed = w.ULONG()
        nt.NtQueryInformationProcess(handle, 60, None, 0, c.byref(needed))
        _need(c.sizeof(_UnicodeString) <= needed.value <= 131072, "native_command_unavailable")
        data = c.create_string_buffer(needed.value)
        _need(
            nt.NtQueryInformationProcess(handle, 60, data, len(data), c.byref(needed)) == 0,
            "native_command_unavailable",
        )
        text = _UnicodeString.from_buffer(data)
        start = c.addressof(data)
        _need(
            bool(text.buffer)
            and 0 < text.length <= text.maximum
            and text.length % 2 == 0
            and text.buffer % 2 == 0
            and start + c.sizeof(_UnicodeString) <= text.buffer
            and text.buffer + text.length <= start + len(data),
            "native_command_unavailable",
        )
        command = c.wstring_at(text.buffer, text.length // 2)
        _need("\0" not in command, "native_command_unavailable")
        count = c.c_int()
        argv = shell.CommandLineToArgvW(command, c.byref(count))
        _need(bool(argv), "native_command_unavailable")
        try:
            _need(0 < count.value <= 64, "native_command_unavailable")
            parsed = digest([argv[i] for i in range(count.value)])
        finally:
            k.LocalFree(c.cast(argv, c.c_void_p))
        _need(k.WaitForSingleObject(handle, 0) == 258, "native_actor_unavailable")
        return WindowsActor(pid, str(birth), _sha(command), parsed, image.value)
    finally:
        k.CloseHandle(handle)


class _AttachJob(Protocol):
    pid: int
    native_start: str
    joined: bool
    args: list[str]
    job: int | None

    def active(self) -> int: ...
    def poll(self) -> int | None: ...


class _CapsuleVisit(Protocol):
    cid: str | None
    run: str
    spec: dict
    jobs: list[_AttachJob]


def _attach_job(record: Mapping[str, object], visit: _CapsuleVisit) -> tuple[_AttachJob, str]:
    members = record.get("visits")
    _need(
        type(members) is list and len(members) == 1 and type(members[0]) is dict,
        "attach_unacknowledged",
    )
    active = members[0]
    cid = visit.cid
    _need(
        _hex(cid)
        and _hex(visit.run, 32)
        and active.get("run") == visit.run
        and active.get("kind") == "effect"
        and active.get("status") == "ACTIVE"
        and active.get("create")
        == dict(
            resolution="ACK_EXACT_CID",
            cid=cid,
            spec_sha256=digest(visit.spec),
        ),
        "attach_unacknowledged",
    )
    children = active.get("children")
    _need(
        type(children) is list
        and len(children) == 2
        and all(type(row) is dict for row in children)
        and len(visit.jobs) >= 2,
        "attach_unacknowledged",
    )
    jobs = tuple(visit.jobs)

    def recorded_job(child):
        matches = [
            job
            for job in jobs
            if job.pid == child.get("pid") and job.native_start == child.get("native_start")
        ]
        _need(len(matches) == 1, "attach_identity")
        return matches[0]

    created, child = children
    create, attach = recorded_job(created), recorded_job(child)
    argv = [*_DOCKER, "start", "--attach", "--interactive", cid]
    _need(
        create is not attach
        and all(job.joined is True and job.poll() is not None for job in jobs if job is not attach)
        and create.poll() == 0
        and attach.joined is False
        and bool(attach.job)
        and attach.poll() is None
        and _pid(attach.pid)
        and type(attach.native_start) is str
        and attach.native_start.startswith("win-filetime:")
        and child.get("status") == "RUNNING_OR_UNKNOWN"
        and type(attach.args) in (list, tuple)
        and list(attach.args) == argv
        and child.get("argv_sha256") == digest(argv),
        "attach_identity",
    )
    return attach, _sha(subprocess.list2cmdline(argv))


def _single_job_actor(job: _AttachJob) -> None:
    count = job.active()
    _need(type(count) is int and count == 1 and job.poll() is None, "attach_job_membership")


def join_dec4_writer_actors(
    facts: Mapping[str, object],
    *,
    owner: Mapping[str, object],
    bank_record: Mapping[str, object],
    watchdog: RootWatchdogActor,
    restore: RestoreProcessActor | None = None,
    attached_visit: _CapsuleVisit | None = None,
    read_actor: Callable[[int], WindowsActor] = read_windows_actor,
) -> frozenset[OwnedKey]:
    """Join current proof/BankLeg/watchdog and, at guest admission, the exact Job.

    Pass the live CapsuleVisit only after its attach is recorded. Other Job
    history, helper processes and unrelated actors do not acquire owned keys.
    Collect while the launcher's owner, watchdog and attach checks bracket the
    sample; a previously retained snapshot is not an admission input.
    """
    rows = facts.get("actors")
    _need(facts.get("complete") is True and type(rows) is list, "census_incomplete")
    by_pid = {}
    for row in rows:
        _need(
            type(row) is dict and _pid(row.get("pid")) and row["pid"] not in by_pid,
            "census_actor_ambiguous",
        )
        by_pid[row["pid"]] = row

    pid, filetime, parsed = (owner.get(k) for k in ("pid", "start_ticks", "argv_sha256"))
    bank_identity = bank_record.get("identity")
    _need(
        owner.get("schema") == "paper-stock-ingress-owner-v1"
        and owner.get("status") == "PASS_STOCK_INGRESS_SCHEDULED_OWNER"
        and owner.get("origin") == "ACTUAL_STOCK_INGRESS_TASK_SOURCE_ABI"
        and owner.get("no_old_model_self_rows") is True
        and _pid(pid)
        and type(filetime) is str
        and _ticks(filetime) > 0
        and _hex(parsed)
        and bank_record.get("schema") == "paper-bank-leg-v1"
        and type(bank_identity) is dict
        and bank_identity.get("argv_sha256") == parsed
        and bank_record.get("owner") == {"pid": pid, "native_start": f"win-filetime:{filetime}"},
        "scheduled_root",
    )
    _need(
        type(watchdog) is RootWatchdogActor
        and _pid(watchdog.pid)
        and watchdog.pid != pid
        and _hex(watchdog.argv_sha256),
        "watchdog_identity",
    )
    attach = _attach_job(bank_record, attached_visit) if attached_visit is not None else None
    if restore is not None:
        _need(
            type(restore) is RestoreProcessActor
            and _pid(restore.pid)
            and restore.pid not in {pid, watchdog.pid}
            and _hex(restore.argv_sha256),
            "restore_identity",
        )
    if attach:
        _need(
            attach[0].pid not in {pid, watchdog.pid, getattr(restore, "pid", None)},
            "attach_identity",
        )
        _single_job_actor(attach[0])

    def match(actor_pid, birth, *, raw=None, parsed=None, image=None, child=False):
        row = by_pid.get(actor_pid)
        _need(row is not None and _ticks(birth) > 0, "actor_not_inventoried")
        native = read_actor(actor_pid)
        stamp = _ticks(row.get("start_ticks"))
        exact = _ticks(birth) + _EPOCH
        # CIM/DMTF loses sub-microsecond FILETIME precision. Native birth must
        # match exactly; only the independently collected census key is coarse.
        _need(
            type(native) is WindowsActor
            and native.pid == actor_pid
            and native.filetime == birth
            and stamp > _EPOCH
            and stamp in (exact, exact // 10 * 10)
            and _hex(native.raw_command_sha256)
            and row.get("argv_sha256") == native.raw_command_sha256
            and (raw is None or raw == native.raw_command_sha256)
            and (parsed is None or parsed == native.parsed_argv_sha256)
            and (image is None or _path(image) == _path(native.image)),
            "actor_identity",
        )
        if child:
            children = by_pid[pid].get("children")
            _need(
                type(children) is list
                and children.count(actor_pid) == 1
                and row.get("parent_pid") == pid
                and row.get("children") == [],
                "actor_lineage",
            )
        return (actor_pid, str(stamp), native.raw_command_sha256), native

    root, native_root = match(pid, filetime, parsed=parsed)
    watch, _ = match(
        watchdog.pid,
        watchdog.start_ticks,
        raw=watchdog.argv_sha256,
        image=native_root.image,
        child=True,
    )
    owned = {root, watch}
    if restore is not None:
        restoring, _ = match(
            restore.pid,
            restore.start_ticks,
            raw=restore.argv_sha256,
            image=native_root.image,
            child=True,
        )
        owned.add(restoring)
    if not attach:
        return frozenset(owned)
    job, raw = attach
    attached, _ = match(
        job.pid,
        job.native_start.split(":")[1],
        raw=raw,
        parsed=digest(list(job.args)),
        image=_DOCKER[0],
        child=True,
    )
    _single_job_actor(job)
    check_job, check_raw = _attach_job(bank_record, attached_visit)
    _need(check_job is job and check_raw == raw, "attach_identity")
    return frozenset(owned | {attached})


@dataclass(frozen=True)
class CapsuleProcessInventory:
    cid: str
    complete: bool
    processes: tuple[CapsuleProcess, ...]


def require_dec4_capsule_processes(
    cid: str,
    inventory: CapsuleProcessInventory | None,
    *,
    guest: CapsuleProcess,
) -> None:
    """Check an independent role inventory after attach, in addition to inspect.

    The direct capsule is PID 1 and loads the pinned worker in-process. Its
    expected identity must come from an independently bound native source,
    never by selecting an expected row from the inventory being checked.
    """
    _need(
        _hex(cid)
        and type(inventory) is CapsuleProcessInventory
        and inventory.cid == cid
        and inventory.complete is True
        and type(inventory.processes) is tuple,
        "container_processes_unknown",
    )
    _need(
        type(guest) is CapsuleProcess
        and type(guest.namespace_pid) is int
        and guest.namespace_pid == 1
        and type(guest.start_ticks) is int
        and guest.start_ticks > 0
        and _hex(guest.argv_sha256),
        "container_guest_unbound",
    )
    _need(
        all(
            type(p) is CapsuleProcess
            and _pid(p.namespace_pid)
            and type(p.start_ticks) is int
            and p.start_ticks > 0
            and _hex(p.argv_sha256)
            for p in inventory.processes
        ),
        "container_processes_unknown",
    )
    _need(len(inventory.processes) <= 1, "container_extra_process")
    _need(inventory.processes == (guest,), "container_guest_unbound")
