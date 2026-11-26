"""Read only the Scheduler leg of the Dec9 target owner's native proof.

Load from an independently protected launcher, before importing the frozen
project. This is not a ProtectedNativeOwner and has no entry point or config
loader. The launcher supplies independent file pins and protects the probe,
ancestor directories and PowerShell runtime/dependencies.
"""

import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
from contextlib import ExitStack
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

_TASK = r"\thericher-h3-dec9-modp1-target-owner-20261209-v1"
_SCRIPT = "read_h3_native_owner.ps1"
_MODULES = {
    "paper_native_pair_readback.psm1": "readback_module_sha256",
    "paper_task_registration.psm1": "registration_module_sha256",
}
_PROFILE_FIELDS = {
    "schema",
    "task_path",
    "action_sha256",
    "export_xml",
    "definition_xml",
    "acl7",
    *_MODULES.values(),
}
_REPLY_FIELDS = {
    "schema",
    "task_path",
    "action_sha256",
    "profile_sha256",
    "instance_guid",
    "engine_pid",
}
_HEX = re.compile(r"[0-9a-f]{64}")
_GUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


class Dec9SchedulerEvidence(NamedTuple):
    """Scoped observation, not a typed NativeOwnerProof or execution admission."""

    task_path: str
    action_sha256: str
    profile_sha256: str
    instance: UUID
    pid: int


def _digest(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _object(raw, encoding):
    def unique(items):
        result = dict(items)
        if len(result) != len(items):
            raise ValueError
        return result

    result = json.loads(raw.decode(encoding), object_pairs_hook=unique)
    if type(result) is not dict:
        raise ValueError
    return result


def _action_digest(action):
    # Same field order and printable-ASCII domain as the PowerShell reader.
    fields = {key: getattr(action, key) for key in ("arguments", "executable", "working_directory")}
    if action.task_path != _TASK or any(
        type(value) is not str or re.fullmatch(r"[ -~]+", value) is None
        for value in fields.values()
    ):
        raise ValueError
    return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode("ascii")).hexdigest()


def _file_stamp(info):
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or _reparse(info):
        raise ValueError
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _reparse(info):
    return getattr(info, "st_file_attributes", 0) & 0x400


def _path_stamp(path):
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or _reparse(info):
            raise ValueError
    if path.resolve(strict=True) != path:
        raise ValueError
    return _file_stamp(path.lstat())


def _open_locked(path):
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
    # Read-only; deny writes/deletes while PowerShell opens the same files.
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


def _windows_root():
    if os.name != "nt":
        raise ValueError
    read = ctypes.WinDLL("kernel32", use_last_error=True).GetSystemWindowsDirectoryW
    read.argtypes = (wintypes.LPWSTR, wintypes.UINT)
    read.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    if not 0 < read(buffer, len(buffer)) < len(buffer):
        raise ValueError
    return Path(buffer.value)


@dataclass(frozen=True, kw_only=True)
class Dec9SchedulerProbe:
    pwsh_path: Path
    pwsh_sha256: str
    script_path: Path
    script_sha256: str
    profile_path: Path
    profile_sha256: str

    def __post_init__(self):
        paths = self.pwsh_path, self.script_path, self.profile_path
        if (
            not all(
                _digest(pin) for pin in (self.pwsh_sha256, self.script_sha256, self.profile_sha256)
            )
            or any(
                not isinstance(path, Path)
                or not path.is_absolute()
                or (os.name == "nt" and re.fullmatch(r"[A-Za-z]:", path.drive) is None)
                or any(
                    part == ".." or ":" in part or part.endswith((" ", "."))
                    for part in path.parts[1:]
                )
                for path in paths
            )
            or self.pwsh_path.name.lower() != "pwsh.exe"
            or self.script_path.name != _SCRIPT
        ):
            raise ValueError("dec9_scheduler_pins")

    def read_current(self, action) -> Dec9SchedulerEvidence:
        """Compare the bootstrap's NativeAction; never accept a caller PID or task."""
        try:
            pid = os.getpid()
            if not 0 < pid <= 0x7FFFFFFF:
                raise ValueError
            return self._read(_action_digest(action), pid)
        except subprocess.TimeoutExpired:
            failure = "dec9_scheduler_timeout"
        except Exception:
            failure = "dec9_scheduler_unqualified"
        raise ValueError(failure)

    def _read(self, action_sha256, pid):
        root = _windows_root()
        with ExitStack() as stack:
            stamps = {}

            def pinned(path, pin, limit):
                if path in stamps or not _digest(pin):
                    raise ValueError
                stamp = _path_stamp(path)
                source = stack.enter_context(_open_locked(path))
                if _file_stamp(os.fstat(source.fileno())) != stamp or not 0 < stamp[2] <= limit:
                    raise ValueError
                raw = source.read(stamp[2] + 1)
                if (
                    len(raw) != stamp[2]
                    or hashlib.sha256(raw).hexdigest() != pin
                    or _path_stamp(path) != stamp
                ):
                    raise ValueError
                stamps[path] = stamp
                return raw

            profile = _object(pinned(self.profile_path, self.profile_sha256, 1 << 20), "utf-8")
            if (
                profile.keys() != _PROFILE_FIELDS
                or profile["schema"] != "PAPER_NATIVE_OWNER_PROFILE_V1"
                or profile["task_path"] != _TASK
                or profile["action_sha256"] != action_sha256
                or any(
                    type(profile[key]) is not str or not profile[key]
                    for key in ("export_xml", "definition_xml", "acl7")
                )
            ):
                raise ValueError
            pinned(self.pwsh_path, self.pwsh_sha256, 64 << 20)
            pinned(self.script_path, self.script_sha256, 1 << 18)
            for name, key in _MODULES.items():
                pinned(self.script_path.with_name(name), profile[key], 1 << 18)
            completed = subprocess.run(
                [
                    str(self.pwsh_path),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(self.script_path),
                    "-TaskPath",
                    _TASK,
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
                shell=False,
                check=False,
                timeout=5,
                creationflags=0x08000000,
                env={
                    "SystemRoot": str(root),
                    "TEMP": str(root / "Temp"),
                    "TMP": str(root / "Temp"),
                },
            )
            if completed.returncode != 0 or any(
                _path_stamp(path) != stamp for path, stamp in stamps.items()
            ):
                raise ValueError
            return self._parse(completed.stdout, action_sha256, pid)

    def _parse(self, raw, action_sha256, pid):
        if not 0 < len(raw) <= 1024:
            raise ValueError
        line = raw.removesuffix(b"\r\n") if raw.endswith(b"\r\n") else raw.removesuffix(b"\n")
        if not line.startswith(b"{") or not line.endswith(b"}") or b"\r" in line or b"\n" in line:
            raise ValueError
        row = _object(line, "ascii")
        if (
            row.keys() != _REPLY_FIELDS
            or row["schema"] != "PAPER_NATIVE_OWNER_READBACK_V1"
            or row["task_path"] != _TASK
            or row["action_sha256"] != action_sha256
            or row["profile_sha256"] != self.profile_sha256
            or type(row["engine_pid"]) is not int
            or row["engine_pid"] != pid
            or type(row["instance_guid"]) is not str
            or _GUID.fullmatch(row["instance_guid"]) is None
            or (instance := UUID(row["instance_guid"])).int == 0
        ):
            raise ValueError
        return Dec9SchedulerEvidence(_TASK, action_sha256, self.profile_sha256, instance, pid)
