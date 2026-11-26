"""No-site Windows entry for the protected Dec4/Dec9 normal restore child."""

import ctypes as C
import hashlib
import importlib.abc
import importlib.util
import json
import os
import re
import stat
import sys
import zoneinfo
from ctypes import wintypes as W
from pathlib import Path

_BASE = Path("D:/thericher-v2/model-artifacts/execution")
_ENTRY = "scripts/run_h3_dec4_restore_child.py"
_ZONE = "zoneinfo/America/New_York"
_BINDING = "src/thericher_v2/ops/h3_dec4_restore_native_binding.py"
_DEP = re.compile(r"src/thericher_v2/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.py")


def _require(ok):
    if not ok:
        raise ValueError("h3_restore_child_bootstrap")


def _digest(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    result = {}
    for name, value in pairs:
        _require(name not in result)
        result[name] = value
    return result


def _stamp(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _ordinary(path):
    info = path.lstat()
    _require(
        not getattr(info, "st_file_attributes", 0) & 0x400
        and (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    )
    return info


def _read(path, limit):
    original = _ordinary(path)
    _require(stat.S_ISREG(original.st_mode) and 0 < original.st_size <= limit)
    stamp = _stamp(original)
    with path.open("rb") as stream:
        _require(_stamp(os.fstat(stream.fileno())) == stamp)
        raw = stream.read(limit + 1)
        _require(_stamp(os.fstat(stream.fileno())) == stamp)
    _require(len(raw) == original.st_size and _stamp(_ordinary(path)) == stamp)
    return raw


def _acl(path):
    native = C.WinDLL("advapi32", use_last_error=True).GetFileSecurityW
    native.argtypes = [W.LPCWSTR, W.DWORD, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
    native.restype = W.BOOL
    size = W.DWORD()
    _require(not native(str(path), 7, None, 0, C.byref(size)))
    _require(C.get_last_error() == 122 and 20 <= size.value <= 65_536)
    value = C.create_string_buffer(size.value)
    _require(native(str(path), 7, value, len(value), C.byref(size)) and size.value == len(value))
    _require(int.from_bytes(value.raw[2:4], "little") & 0x9004 == 0x9004)
    _require(20 <= int.from_bytes(value.raw[16:20], "little") < len(value))
    return _sha(value.raw)


def _snapshot(root, files):
    _require(type(files) is dict and 5 <= len(files) <= 256)
    _require({_ENTRY, _ZONE, _BINDING, "src/thericher_v2/__init__.py"} <= files.keys())
    parents = set()
    for key, pin in files.items():
        _require(
            _digest(pin)
            and (
                key == _ZONE or _DEP.fullmatch(key) or re.fullmatch(r"scripts/[a-z0-9_]+\.py", key)
            )
        )
        parents.update(p.as_posix() for p in Path(key).parents if p != Path("."))
    found = {}
    pending = [root]
    while pending:
        for path in pending.pop().iterdir():
            key = path.relative_to(root).as_posix()
            if stat.S_ISDIR(_ordinary(path).st_mode):
                _require(key in parents)
                pending.append(path)
            elif key != "SOURCE.json":
                _require(key in files)
                raw = _read(path, 2 * 1024 * 1024)
                _require(_sha(raw) == files[key])
                found[key] = raw
    _require(found.keys() == files.keys())
    return found


class _PinnedImports(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, root, files):
        self.root = root
        self.modules = {}
        for key, raw in files.items():
            if not _DEP.fullmatch(key):
                continue
            name = key.removeprefix("src/").removesuffix(".py").replace("/", ".")
            package = name.endswith(".__init__")
            if package:
                name = name.removesuffix(".__init__")
            _require(name not in self.modules)
            self.modules[name] = key, raw, package

    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] != "thericher_v2":
            return None
        if fullname not in self.modules or target is not None:
            raise ImportError("restore_child_dependency_unpinned")
        key, _, package = self.modules[fullname]
        spec = importlib.util.spec_from_loader(
            fullname, self, origin=str(self.root / key), is_package=package
        )
        spec.has_location = True
        return spec

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        _, raw, _ = self.modules[module.__name__]
        exec(compile(raw, module.__file__, "exec", dont_inherit=True), vars(module))


def main():
    args = tuple(sys.argv[1:])
    _require(len(args) == 10 and args[0] in ("entry", "exit") and all(map(_digest, args[1:4])))
    script = Path(__file__)
    root, exe = script.parent.parent, Path(sys.executable)
    _require(
        os.name == "nt"
        and root.is_relative_to(_BASE)
        and root != _BASE
        and script == root / _ENTRY
        and script.resolve(strict=True) == script
        and all(stat.S_ISDIR(_ordinary(path).st_mode) for path in script.parents)
        and Path.cwd() == script.parent
        and exe == Path(sys._base_executable)
        and exe.name.lower() == "pythonw.exe"
        and sys.flags.isolated
        and sys.flags.no_site
        and sys.dont_write_bytecode
        and tuple(sys.orig_argv) == (str(exe), "-I", "-S", "-B", str(script), *args)
        and not any(name.partition(".")[0] == "thericher_v2" for name in sys.modules)
    )
    origin = root / "SOURCE.json"
    raw = _read(origin, 1024 * 1024)
    _require(_sha(raw) == args[1])
    doc = json.loads(raw, object_pairs_hook=_unique)
    profile = doc["restore_bootstrap"]
    _require(
        set(profile) == {"executable", "executable_sha256", "source_acl_sha256"}
        and profile["executable"] == str(exe)
        and _sha(_read(exe, 32 * 1024 * 1024)) == profile["executable_sha256"]
    )
    root_id = _stamp(_ordinary(root))
    zone = root / _ZONE
    source = _snapshot(root, doc["files"])

    def ready():
        return (
            _stamp(_ordinary(root)) == root_id
            and _acl(root) == profile["source_acl_sha256"]
            and _read(origin, 1024 * 1024) == raw
            and _read(zone, 128 * 1024) == source[_ZONE]
            and Path.cwd() == script.parent
        )

    _require(ready())
    zoneinfo.reset_tzpath((str(root / "zoneinfo"),))
    sys.meta_path.insert(0, _PinnedImports(root, source))
    from thericher_v2.ops.h3_dec4_restore_native_binding import build_dec4_restore_binding

    from thericher_v2.ops.h3_dec4_restore_child import run_dec4_restore_child

    binding = build_dec4_restore_binding(root, args[0], args[1], args[2])
    run_dec4_restore_child(binding, args, source_ready=ready)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)
