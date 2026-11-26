"""Bind qualified Windows observations to the Dec4/9 bank visit owner ABI."""

import ctypes
import hashlib
import os
import re
from collections.abc import Callable, Mapping
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime
from subprocess import list2cmdline
from uuid import UUID

from thericher_v2.execution.paper_peer_visit import digest, encode, process_start
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.paper_scheduled_native import NativeOwnerProbe
from thericher_v2.ops.paper_startup import Phase

_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)


def _ticks(when: datetime) -> int:
    elapsed = when - _FILETIME_EPOCH
    return (elapsed.days * 86400 + elapsed.seconds) * 10_000_000 + elapsed.microseconds * 10


@dataclass(frozen=True)
class QualifiedSchedulerInstance:
    """Live readback for the exact local definition, already verified against source.

    The pinned provider verifies full XML/API/ACL and direct Exec semantics,
    then reads Get-PaperNativeActiveInstance for that task. Its observation
    alone cannot qualify a definition or establish the process identity.
    """

    task_path: str
    action_sha256: str
    readback: Mapping[str, object]


@dataclass(frozen=True)
class NativeProcessIdentity:
    """Image, creation FILETIME and parsed native command line of the exact PID."""

    pid: int
    image: str
    start_ticks: str
    argv: tuple[str, ...]


def read_current_dec4_process(pid: int) -> NativeProcessIdentity:
    """Read the actual direct Windows process, never an expected launch plan."""
    if os.name != "nt" or type(pid) is not int or pid != os.getpid():
        raise ValueError("h3_bank_current_native_process_required")

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.GetCommandLineW.restype = wintypes.LPWSTR
    k.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    k.QueryFullProcessImageNameW.restype = wintypes.BOOL
    k.LocalFree.argtypes = (ctypes.c_void_p,)
    k.LocalFree.restype = ctypes.c_void_p
    shell.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)

    image = ctypes.create_unicode_buffer(32_768)
    size = wintypes.DWORD(len(image))
    birth = process_start(pid)
    if (
        not birth
        or not birth.startswith("win-filetime:")
        or not k.QueryFullProcessImageNameW(k.GetCurrentProcess(), 0, image, ctypes.byref(size))
    ):
        raise ValueError("h3_bank_current_native_process_unconfirmed")
    count = ctypes.c_int()
    command_line = k.GetCommandLineW()
    if not command_line:
        raise ValueError("h3_bank_current_native_process_unconfirmed")
    pointer = shell.CommandLineToArgvW(command_line, ctypes.byref(count))
    if not pointer:
        raise ValueError("h3_bank_current_native_process_unconfirmed")
    try:
        if not 0 < count.value <= 64:
            raise ValueError("h3_bank_current_native_process_unconfirmed")
        argv = tuple(pointer[index] for index in range(count.value))
    finally:
        k.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))
    if not image.value or not all(type(arg) is str for arg in argv) or process_start(pid) != birth:
        raise ValueError("h3_bank_current_native_process_unconfirmed")
    return NativeProcessIdentity(pid, image.value, birth.split(":", 1)[1], argv)


class _Dec4Owner:
    def __init__(
        self,
        expected: dict[str, str],
        argv: tuple[str, ...],
        birth_window: tuple[int, int],
        read_scheduler: Callable[[str, int], QualifiedSchedulerInstance],
        read_process: Callable[[int], NativeProcessIdentity],
    ):
        self._expected = expected
        self._argv = argv
        self._argv_sha256 = digest(list(argv))
        self._birth_window = birth_window
        self._read_scheduler = read_scheduler
        self._read_process = read_process
        self._identity: tuple[int, UUID, str] | None = None

    @property
    def expected(self) -> dict[str, object]:
        return self._expected.copy()

    def _instance(self, pid: int) -> UUID:
        path = "\\" + self._expected["task_name"]
        sample = self._read_scheduler(path, pid)
        row = sample.readback
        if (
            sample.task_path != path
            or sample.action_sha256 != self._expected["task_action_sha256"]
            or row.get("Claim") != "SCHEDULER_INSTANCE_OBSERVED"
            or type(row.get("Matches")) is not int
            or row["Matches"] != 1
            or type(row.get("EnginePid")) is not int
            or row["EnginePid"] != pid
        ):
            raise ValueError
        guid = row.get("InstanceGuid")
        if type(guid) is str:
            guid = UUID(guid)
        if type(guid) is not UUID or guid.int == 0:
            raise ValueError
        return guid

    def prove(self) -> dict[str, object]:
        pid = os.getpid()
        try:
            before = self._instance(pid)
            process = self._read_process(pid)
            if (
                type(process.pid) is not int
                or process.pid != pid
                or process.image != self._argv[0]
                or process.argv != self._argv
                or type(process.start_ticks) is not str
                or re.fullmatch(r"[1-9][0-9]{0,18}", process.start_ticks) is None
                or not self._birth_window[0] <= int(process.start_ticks) < self._birth_window[1]
                or self._instance(pid) != before
            ):
                raise ValueError
            identity = (pid, before, process.start_ticks)
            if self._identity is not None and self._identity != identity:
                raise ValueError
        except Exception:
            raise ValueError("h3_bank_owner_changed") from None
        self._identity = identity
        return self.expected | dict(
            schema="paper-stock-ingress-owner-v1",
            status="PASS_STOCK_INGRESS_SCHEDULED_OWNER",
            origin="ACTUAL_STOCK_INGRESS_TASK_SOURCE_ABI",
            no_old_model_self_rows=True,
            pid=pid,
            start_ticks=process.start_ticks,
            argv_sha256=self._argv_sha256,
        )


def dec4_native_plan_fields(
    schedule_plan: Mapping[str, object], pin: str, phase: Phase, release_pin: str
) -> tuple[dict[str, str], tuple[str, ...], str]:
    """Derive static owner fields and the exact action from a protected plan."""
    if phase not in TASKS or any(
        type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (pin, release_pin)
    ):
        raise ValueError("h3_bank_native_plan_mismatch")
    try:
        leg = schedule_plan["phases"][phase]
        argv = tuple(leg["expected_argv"])
        owner = leg["owner_expected"]
        action = encode(
            dict(
                executable=argv[0],
                arguments=list2cmdline(argv[1:]),
                working_directory=owner["dispatcher_root"],
            )
        )
        expected = dict(
            dispatcher_source=pin,
            dispatcher_release=release_pin,
            dispatcher_root=owner["dispatcher_root"],
            task_name=TASKS[phase],
            task_action_sha256=hashlib.sha256(action).hexdigest(),
            round_id=ROUND,
        )
        launch_pins = ("--phase", phase, "--source-sha256", pin, "--release-sha256", release_pin)
        opens, closes, hard_stop = _TIMES[phase]
        if (
            schedule_plan["round_id"] != ROUND
            or leg["slot"]
            != dict(
                name=TASKS[phase],
                start_UTC=opens.isoformat(),
                end_UTC=closes.isoformat(),
                hard_UTC=hard_stop.isoformat(),
            )
            or owner != expected
            or len(argv) != 11
            or argv[1:4] != ("-I", "-S", "-B")
            or argv[5:] != launch_pins
            or leg["action"] != action.decode("ascii")
            or leg["expected_argv_sha256"] != digest(list(argv))
        ):
            raise ValueError
    except (IndexError, KeyError, TypeError, ValueError):
        raise ValueError("h3_bank_native_plan_mismatch") from None
    return expected, argv, action.decode("ascii")


def bind_dec4_native_owner(
    schedule_plan: Mapping[str, object],
    pin: str,
    phase: Phase,
    release_pin: str,
    *,
    read_scheduler: Callable[[str, int], QualifiedSchedulerInstance],
    read_process: Callable[[int], NativeProcessIdentity],
) -> NativeOwnerProbe:
    """Readers must sample anew, never reconstruct native facts from the plan."""
    expected, argv, _ = dec4_native_plan_fields(schedule_plan, pin, phase, release_pin)
    opens, closes, _ = _TIMES[phase]
    return _Dec4Owner(expected, argv, (_ticks(opens), _ticks(closes)), read_scheduler, read_process)
