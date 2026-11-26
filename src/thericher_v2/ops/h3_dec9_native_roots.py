"""Windows creator custody for the Dec9 target capture and seal writer.

The scope holds the original creator and its entire parent chain, not path
stats. Borrowed handles belong to this scope and must not be closed by the
host. No share-delete is a namespace guard, not a sandbox: path-based writers
still require a qualified local filesystem, stable DOS namespace, trusted
source/runtime and independent exclusion of same-principal or privileged
writers. Handles alone do not protect attributes, ACLs or descendants.
"""

import ctypes as c
import re
import sys
from contextlib import ExitStack
from ctypes import wintypes as w
from pathlib import Path
from typing import NamedTuple

_SDDL = "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;OW)"
_P = c.c_void_p
_PP = c.POINTER(_P)
_FILE_OPEN, _FILE_CREATE, _FILE_CREATED = 1, 2, 2


class _Name(c.Structure):
    _fields_ = [("length", w.USHORT), ("maximum", w.USHORT), ("buffer", _P)]


class _Attributes(c.Structure):
    _fields_ = [
        ("length", w.ULONG), ("root", w.HANDLE), ("name", c.POINTER(_Name)),
        ("flags", w.ULONG), ("descriptor", _P), ("qos", _P),
    ]


class _IoStatus(c.Structure):
    _fields_ = [("status_or_pointer", _P), ("information", c.c_size_t)]


class _FileId(c.Structure):
    _fields_ = [("volume", c.c_uint64), ("id", c.c_ubyte * 16)]


class _FileBasic(c.Structure):
    _fields_ = [
        ("created", c.c_int64), ("accessed", c.c_int64), ("written", c.c_int64),
        ("changed", c.c_int64), ("attributes", w.DWORD),
    ]


class DirectoryIdentity(NamedTuple):
    volume: int
    file_id: int
    created: int


class HeldDirectory(NamedTuple):
    path: Path
    handle: int
    identity: DirectoryIdentity


def _need(ok):
    if not ok:
        raise ValueError("dec9_native_directory_custody")


def _bind(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, args
    return fn


class _Native:
    def __init__(self):
        _need(sys.platform == "win32")
        n, k, a = (c.WinDLL(name) for name in ("ntdll", "kernel32", "advapi32"))
        self.create = _bind(
            n, "NtCreateFile", w.LONG, _PP, w.ULONG, c.POINTER(_Attributes),
            c.POINTER(_IoStatus), _P, w.ULONG, w.ULONG, w.ULONG, w.ULONG, _P, w.ULONG,
        )
        self.info = _bind(
            k, "GetFileInformationByHandleEx", w.BOOL, w.HANDLE, c.c_int, _P, w.DWORD
        )
        self.drive_type = _bind(k, "GetDriveTypeW", w.UINT, w.LPCWSTR)
        self.close = _bind(k, "CloseHandle", w.BOOL, w.HANDLE)
        self.free = _bind(k, "LocalFree", _P, _P)
        self.parse_dacl = _bind(
            a, "ConvertStringSecurityDescriptorToSecurityDescriptorW",
            w.BOOL, w.LPCWSTR, w.DWORD, _PP, _P,
        )
        self.render_dacl = _bind(
            a, "ConvertSecurityDescriptorToStringSecurityDescriptorW",
            w.BOOL, _P, w.DWORD, w.DWORD, _PP, _P,
        )
        self.security = _bind(
            a, "GetSecurityInfo", w.DWORD, w.HANDLE, c.c_int, w.DWORD,
            _PP, _PP, _PP, _PP, _PP,
        )

    def directory(self, scope, path, parent, *, create=False):
        if parent is None:
            _need(not create and path == Path(path.anchor) and self.drive_type(path.anchor) == 3)
            name = "\\??\\" + path.anchor
        else:
            name = path.name
            _need(path.parent == parent.path and re.fullmatch(r'[^\\/:*?"<>|\x00-\x1f]+', name))
            _need(not name.endswith((" ", ".")))
        buf = c.create_unicode_buffer(name)
        _need(c.sizeof(buf) <= 65535)
        native_name = _Name(c.sizeof(buf) - 2, c.sizeof(buf), c.addressof(buf))
        with ExitStack() as buffers:
            sd = _P()
            if create:
                _need(self.parse_dacl(_SDDL, 1, c.byref(sd), None))
                buffers.callback(self.free, sd)
            attrs = _Attributes(
                c.sizeof(_Attributes), None if parent is None else parent.handle,
                c.pointer(native_name), 0x40, sd, None,  # OBJ_CASE_INSENSITIVE
            )
            handle, io = w.HANDLE(), _IoStatus()
            # LIST_DIRECTORY participates in sharing. Omit SHARE_DELETE.
            status = self.create(
                c.byref(handle), 0x1 | 0x80 | 0x20000, c.byref(attrs), c.byref(io),
                None, 0, 0x3, _FILE_CREATE if create else _FILE_OPEN,
                0x1 | 0x00200000, None, 0,  # DIRECTORY_FILE | OPEN_REPARSE_POINT
            )
        _need(status == 0 and handle.value)
        scope.callback(self.close_checked, handle.value)
        if create:
            _need(io.information == _FILE_CREATED)
            self.check_dacl(handle.value)
        identity = self.identity(handle.value)
        _need(parent is None or identity.volume == parent.identity.volume)
        return HeldDirectory(path, handle.value, identity)

    def close_checked(self, handle):
        _need(self.close(handle))

    def identity(self, handle):
        ident, basic = _FileId(), _FileBasic()
        for cls, obj in ((18, ident), (0, basic)):  # FileIdInfo, FileBasicInfo
            _need(self.info(handle, cls, c.byref(obj), c.sizeof(obj)))
        _need(basic.attributes & 0x10 and not basic.attributes & 0x400)
        file_id = int.from_bytes(ident.id, "little")
        _need(file_id > 0 and basic.created > 0)
        return DirectoryIdentity(ident.volume, file_id, basic.created)

    def check_dacl(self, handle):
        with ExitStack() as buffers:
            sd, rendered = _P(), _P()
            _need(self.security(handle, 1, 4, None, None, None, None, c.byref(sd)) == 0)
            buffers.callback(self.free, sd)
            _need(self.render_dacl(sd, 1, 4, c.byref(rendered), None))
            buffers.callback(self.free, rendered)
            flags, _, aces = c.wstring_at(rendered).partition("(")
            _need(flags in {"D:P", "D:PAI"} and aces == _SDDL.partition("(")[2])


class NativeRootScope:
    """Pin exact ancestors and create only relative to a held parent."""

    def __init__(self, lifetime: ExitStack):
        self._native = _Native()
        self._lifetime = lifetime
        self._held: dict[Path, HeldDirectory] = {}
        self._created: set[Path] = set()

    def parents(self, path: Path) -> tuple[HeldDirectory, ...]:
        _need(re.fullmatch(r"[A-Za-z]:\\", path.anchor) and path != Path(path.anchor))
        parent = None
        chain = []
        for part in reversed(path.parents):
            if part not in self._held:
                self._held[part] = self._native.directory(self._lifetime, part, parent)
            parent = self._held[part]
            chain.append(parent)
        return tuple(chain)

    def create(self, path: Path) -> HeldDirectory:
        _need(path not in self._held and path.parent in self._held)
        creator = self._native.directory(
            self._lifetime, path, self._held[path.parent], create=True
        )
        self._held[path] = creator
        self._created.add(path)
        return creator

    def verify(self) -> None:
        with ExitStack() as observations:
            for path, held in self._held.items():
                _need(self._native.identity(held.handle) == held.identity)
                parent = None if path == Path(path.anchor) else self._held[path.parent]
                current = self._native.directory(observations, path, parent)
                _need(current.identity == held.identity)
                if path in self._created:
                    self._native.check_dacl(held.handle)
