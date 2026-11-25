"""Sample the Dec4/9 owner through the pinned, read-only native Scheduler probe."""

import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from contextlib import ExitStack
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from thericher_v2.ops.h3_dec4_bank_visit import TASKS
from thericher_v2.ops.h3_dec4_native_host import (
    QualifiedSchedulerInstance,
    bind_dec4_native_owner,
    read_current_dec4_process,
)

_TASK_PATHS = frozenset(f"\\{name}" for name in TASKS.values())
_SCHEMA = "PAPER_NATIVE_OWNER_READBACK_V1"
_FIELDS = {"schema", "task_path", "action_sha256", "instance_guid", "engine_pid", "profile_sha256"}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_TIMEOUT_SECONDS = 5
_MAX_REPLY_BYTES = 1024
_CREATE_NO_WINDOW = 0x08000000


def _windows_root() -> Path:
    if os.name != "nt":
        raise ValueError
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_root = kernel.GetSystemWindowsDirectoryW
    get_root.argtypes = (wintypes.LPWSTR, wintypes.UINT)
    get_root.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    if not 0 < get_root(buffer, len(buffer)) < len(buffer):
        raise ValueError
    return Path(buffer.value)


def _open_locked(path: Path) -> BinaryIO:
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    # GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT.
    handle = create(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise ValueError
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT)
    except OSError:
        kernel.CloseHandle(handle)
        raise
    try:
        return os.fdopen(fd, "rb")
    except Exception:
        os.close(fd)
        raise


def _file_stamp(info: os.stat_result) -> tuple[int, ...]:
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _path_stamp(path: Path) -> tuple[int, ...]:
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError
    if path.resolve(strict=True) != path:
        raise ValueError
    return _file_stamp(path.lstat())


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def make_dec4_windows_owner_factory(
    schedule_plan: Mapping[str, object],
    providers: Mapping[str, "Dec4SchedulerProvider"],
):
    """Supply the bank's make_owner callback from two authenticated launcher legs."""
    if set(providers) != set(TASKS):
        raise ValueError("h3_bank_scheduler_plan_mismatch")
    frozen_providers = dict(providers)

    def make_owner(pin, phase, release_pin):
        try:
            provider = frozen_providers[phase]
            if (
                type(provider) is not Dec4SchedulerProvider
                or provider.task_path != "\\" + TASKS[phase]
                or provider.action_sha256
                != schedule_plan["phases"][phase]["owner_expected"]["task_action_sha256"]
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("h3_bank_scheduler_plan_mismatch") from None
        return bind_dec4_native_owner(
            schedule_plan,
            pin,
            phase,
            release_pin,
            read_scheduler=provider,
            read_process=read_current_dec4_process,
        )

    return make_owner


@dataclass(frozen=True, kw_only=True)
class Dec4SchedulerProvider:
    """Callable for one pinned task leg; paths must be in launcher-protected trees.

    The launcher owns the pins and protects their parent directories and pwsh
    runtime dependencies. The script authenticates its sibling modules and
    independently verifies the native task definition, ACL and running instance.
    """

    task_path: str
    action_sha256: str
    pwsh_path: Path
    pwsh_sha256: str
    script_path: Path
    script_sha256: str
    profile_path: Path
    profile_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.task_path) is not str
            or self.task_path not in _TASK_PATHS
            or any(
                type(pin) is not str or _SHA256.fullmatch(pin) is None
                for pin in (
                    self.action_sha256,
                    self.pwsh_sha256,
                    self.script_sha256,
                    self.profile_sha256,
                )
            )
            or any(
                not isinstance(path, Path)
                or not path.is_absolute()
                or (os.name == "nt" and re.fullmatch(r"[A-Za-z]:", path.drive) is None)
                or any(
                    part == ".." or ":" in part or part.endswith((" ", "."))
                    for part in path.parts[1:]
                )
                for path in (self.pwsh_path, self.script_path, self.profile_path)
            )
            or self.pwsh_path.name.lower() != "pwsh.exe"
            or self.script_path.suffix.lower() != ".ps1"
        ):
            raise ValueError("h3_bank_scheduler_pin_invalid")

    def __call__(self, task_path: str, pid: int) -> QualifiedSchedulerInstance:
        if type(task_path) is not str or task_path != self.task_path:
            raise ValueError("h3_bank_scheduler_scope_mismatch")
        if type(pid) is not int or not 0 < pid <= 0x7FFFFFFF:
            raise ValueError("h3_bank_scheduler_scope_mismatch")

        try:
            return self._read(pid)
        except subprocess.TimeoutExpired:
            failure = "h3_bank_scheduler_timeout"
        except Exception:
            failure = "h3_bank_scheduler_readback_unqualified"
        # Do not attach child output, command line or filesystem errors to the exception.
        raise ValueError(failure)

    def _read(self, pid: int) -> QualifiedSchedulerInstance:
        root = _windows_root()
        with ExitStack() as stack:
            stamps = {}
            for path, pin in (
                (self.pwsh_path, self.pwsh_sha256),
                (self.script_path, self.script_sha256),
                (self.profile_path, self.profile_sha256),
            ):
                stamp = _path_stamp(path)
                source = stack.enter_context(_open_locked(path))
                if (
                    _file_stamp(os.fstat(source.fileno())) != stamp
                    or hashlib.file_digest(source, "sha256").hexdigest() != pin
                    or _path_stamp(path) != stamp
                ):
                    raise ValueError
                stamps[path] = stamp

            # All three read handles deny writes/deletes through child exit.
            completed = subprocess.run(
                [
                    str(self.pwsh_path),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(self.script_path),
                    "-TaskPath",
                    self.task_path,
                    "-ExpectedEnginePid",
                    str(pid),
                    "-ExpectedProfileSha256",
                    self.profile_sha256,
                    "-ProfilePath",
                    str(self.profile_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=root / "System32",
                env={
                    "SystemRoot": str(root),
                    "TEMP": str(root / "Temp"),
                    "TMP": str(root / "Temp"),
                },
                creationflags=_CREATE_NO_WINDOW,
                timeout=_TIMEOUT_SECONDS,
                check=False,
                shell=False,
            )
            if completed.returncode != 0 or any(
                _path_stamp(path) != stamp for path, stamp in stamps.items()
            ):
                raise ValueError
            return self._parse(completed.stdout, pid)

    def _parse(self, output: bytes, pid: int) -> QualifiedSchedulerInstance:
        if not 0 < len(output) <= _MAX_REPLY_BYTES:
            raise ValueError
        line = output.removesuffix(b"\n").removesuffix(b"\r") if output.endswith(b"\n") else output
        if not line.startswith(b"{") or not line.endswith(b"}") or b"\n" in line or b"\r" in line:
            raise ValueError
        row = json.loads(line.decode("ascii"), object_pairs_hook=_unique_object)
        if (
            row.keys() != _FIELDS
            or row["schema"] != _SCHEMA
            or row["task_path"] != self.task_path
            or row["action_sha256"] != self.action_sha256
            or row["profile_sha256"] != self.profile_sha256
            or type(row["engine_pid"]) is not int
            or row["engine_pid"] != pid
        ):
            raise ValueError
        guid = row["instance_guid"]
        if type(guid) is not str:
            raise ValueError
        if guid.startswith("{") and guid.endswith("}"):
            guid = guid[1:-1]
        if _GUID.fullmatch(guid) is None or (instance := UUID(guid)).int == 0:
            raise ValueError
        return QualifiedSchedulerInstance(
            row["task_path"],
            row["action_sha256"],
            {
                "Claim": "SCHEDULER_INSTANCE_OBSERVED",
                "Matches": 1,
                "EnginePid": row["engine_pid"],
                "InstanceGuid": instance,
            },
        )
