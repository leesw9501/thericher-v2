"""Quiet, one-shot Dec4 proposal supervisor and its direct Windows Job child."""

import ctypes as C
import hashlib
import json
import os
import re
import stat
import sys
from ctypes import wintypes as W
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

NAME = "h3-dec4-lstm-point-20261204-v1"
ROOT = Path("D:/thericher-v2/model-artifacts")
SOURCE = ROOT / "research" / NAME / "source-v3"
CONTROL = SOURCE.with_name("point-control-v3")
DEC3_SOURCE = ROOT / "data/h3-dec3-modp1-owner-20261203-v1/source"
DEC3_PIN = "878615272a71b035f61438d3242163c50f548350842409e6bc64dd6415b861bf"
DEC3_WRITER_PIN = "bdc42ce518780b8b83ac217803fe75c972ece93c89559572706132ad532eeafb"
SITE = Path("C:/Users/Public/Documents/thericher-v2/.venv/Lib/site-packages")
ENTRY = "scripts/run_h3_dec4_supervised_point.py"
FLAGS = ("-I", "-S", "-B")
OPENS = datetime(2026, 12, 3, 21, 47, tzinfo=UTC)
LAST_START = OPENS.replace(minute=52)
HARD_STOP = OPENS.replace(hour=22, minute=0)
HANDOFF = "POINT-SUPERVISOR-DIGEST"
REQUIRED = {
    ENTRY,
    "src/thericher_v2/__init__.py",
    "src/thericher_v2/ops/h3_dec4_point_join.py",
    "src/thericher_v2/ops/h3_dec4_point_owner.py",
    "src/thericher_v2/ops/h3_dec4_watchdog.py",
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _require(condition):
    if not condition:
        raise ValueError("dec4_point_launcher_binding")


def _ordinary(path):
    info = path.lstat()
    _require(not (getattr(info, "st_file_attributes", 0) & 0x400))
    _require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
    return info


def _path(path, *, directory):
    _require(path.is_absolute() and path.resolve(strict=True) == path)
    _require(all(stat.S_ISDIR(_ordinary(p).st_mode) for p in path.parents))
    info = _ordinary(path)
    _require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode))
    return info.st_dev, info.st_ino


def _read(path, limit):
    def signature(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

    info = _ordinary(path)
    _require(stat.S_ISREG(info.st_mode) and info.st_size <= limit)
    before = signature(info)
    with path.open("rb") as stream:
        _require(signature(os.fstat(stream.fileno())) == before)
        raw = stream.read(limit + 1)
        _require(signature(os.fstat(stream.fileno())) == before)
    _require(signature(_ordinary(path)) == before and len(raw) == info.st_size)
    return raw


def _acl_sha256(path):
    """Hash the native self-relative OWNER/GROUP/DACL descriptor (security info 7)."""
    get = C.WinDLL("advapi32", use_last_error=True).GetFileSecurityW
    get.argtypes = [W.LPCWSTR, W.DWORD, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
    get.restype = W.BOOL
    size = W.DWORD()
    _require(not get(str(path), 7, None, 0, C.byref(size)))
    _require(C.get_last_error() == 122 and 20 <= size.value <= 65_536)
    raw = C.create_string_buffer(size.value)
    _require(get(str(path), 7, raw, len(raw), C.byref(size)) and size.value == len(raw))
    # SECURITY_DESCRIPTOR_RELATIVE: require protected, present, non-null DACL.
    _require(int.from_bytes(raw.raw[2:4], "little") & 0x9004 == 0x9004)
    _require(20 <= int.from_bytes(raw.raw[16:20], "little") < len(raw))
    return _sha(raw.raw)


def _in_job():
    check = C.WinDLL("kernel32", use_last_error=True).IsProcessInJob
    check.argtypes = [W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)]
    check.restype = W.BOOL
    inside = W.BOOL()
    _require(check(W.HANDLE(-1), None, C.byref(inside)))
    return bool(inside.value)


def _verify_source(pin):
    raw = _read(SOURCE / "SOURCE.json", 1024 * 1024)
    _require(_sha(raw) == pin)
    manifest = json.loads(raw)
    _require(set(manifest) == {"schema", "run", "files"})
    _require(manifest["schema"] == "H3_DEC4_SUPERVISED_POINT_SOURCE_V1")
    files = manifest["files"]
    _require(manifest["run"] == NAME and type(files) is dict and REQUIRED <= files.keys())
    directories = {"scripts", "src", "src/thericher_v2"}
    for key, digest in files.items():
        _require(
            _digest(digest)
            and (
                key == ENTRY
                or re.fullmatch(r"src/thericher_v2/(?:[a-zA-Z0-9_]+/)*[a-zA-Z0-9_]+\.py", key)
            )
        )
        directories.update(p.as_posix() for p in Path(key).parents if p != Path("."))
    observed = set()
    pending = [SOURCE]
    while pending:
        for member in pending.pop().iterdir():
            key = member.relative_to(SOURCE).as_posix()
            if stat.S_ISDIR(_ordinary(member).st_mode):
                _require(key in directories)
                pending.append(member)
            elif key != "SOURCE.json":
                _require(key in files and _sha(_read(member, 2 * 1024 * 1024)) == files[key])
                observed.add(key)
    _require(observed == files.keys())
    _require(_read(SOURCE / "SOURCE.json", 1024 * 1024) == raw)


def _runtime(pins, arguments):
    base, base_pin, source_pin, source_acl, control_acl = pins
    exe = Path(base)
    _require(os.name == "nt" and exe.name.lower() == "pythonw.exe")
    _require(all(_digest(pin) for pin in pins[1:]))
    _require(exe == Path(sys.executable) == Path(sys._base_executable))
    _require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
    _require(tuple(sys.orig_argv) == (base, *FLAGS, str(SOURCE / ENTRY), *arguments))
    _require(Path(__file__) == SOURCE / ENTRY and Path.cwd() == SOURCE)
    exe_identity = _path(exe, directory=False)
    source_identity = _path(SOURCE, directory=True)
    control_identity = _path(CONTROL, directory=True)
    _path(SITE, directory=True)

    def ready():
        return (
            Path.cwd() == SOURCE
            and _path(exe, directory=False) == exe_identity
            and _path(SOURCE, directory=True) == source_identity
            and _path(CONTROL, directory=True) == control_identity
            and _acl_sha256(SOURCE) == source_acl
            and _acl_sha256(CONTROL) == control_acl
            and _sha(_read(SOURCE / "SOURCE.json", 1024 * 1024)) == source_pin
        )

    _require(ready() and _sha(_read(exe, 32 * 1024 * 1024)) == base_pin)
    _verify_source(source_pin)
    _require(ready() and not any(n.split(".")[0] == "thericher_v2" for n in sys.modules))
    sys.path.insert(0, str(SOURCE / "src"))
    sys.path.append(str(SITE))
    return ready


def _data_closure(probe):
    _path(DEC3_SOURCE, directory=True)
    writer = DEC3_SOURCE / "scripts/run_h3_nov27_data_owner.py"
    _path(writer, directory=False)
    raw = _read(writer, 128 * 1024)
    _require(_sha(raw) == DEC3_WRITER_PIN)
    frozen = ModuleType("dec4_frozen_dec3_owner")
    exec(compile(raw, "<frozen Dec3 writer>", "exec"), vars(frozen))
    _require(frozen.DEC3_SOURCE == DEC3_SOURCE)
    frozen.verify_source(DEC3_SOURCE, DEC3_PIN, dec3=True)

    def closed(pid, birth, digest):
        if (
            type(pid) is not int
            or not 0 < pid < 2**32
            or type(birth) is not str
            or re.fullmatch(r"win-filetime:[1-9][0-9]{0,18}", birth) is None
            or not _digest(digest)
            or _sha(_read(DEC3_SOURCE / "SOURCE.json", 1024 * 1024)) != DEC3_PIN
        ):
            return False
        run = DEC3_SOURCE.parent / "run"
        receipt, claim = run / "OWNER-CLOSED.json", run / "owner/ATTEMPT.json"
        _path(receipt, directory=False)
        _path(claim, directory=False)
        raw, attempt = _read(receipt, 16_384), _read(claim, 16_384)
        done, started = json.loads(raw), json.loads(attempt)
        # The frozen Data writer predates the point launch ABI. Its canonical
        # attempt records the real synchronous worker PID; its receipt binds
        # that attempt and creation FILETIME, not Scheduler origin.
        return (
            _sha(raw) == digest
            and done["schema"] == "H3_DEC3_OWNER_CLOSED_V1"
            and done["source_sha256"] == DEC3_PIN
            and done["attempt_sha256"] == _sha(attempt)
            and done["native_start"] == birth
            and started["schema"] == "H3_DEC3_DATA_ATTEMPT_V1"
            and started["source_sha256"] == DEC3_PIN
            and type(started["pid"]) is int
            and started["pid"] == pid
            and probe(pid) is None
            and _read(receipt, 16_384) == raw
            and _read(claim, 16_384) == attempt
        )

    return closed


def _child_argv(pins, pid, birth):
    return (pins[0], *FLAGS, str(SOURCE / ENTRY), "child", *pins, str(pid), birth)


def _run(arguments):
    _require(OPENS <= datetime.now(UTC) < LAST_START)
    mode, *values = arguments
    _require((mode, len(values)) in {("supervise", 5), ("child", 8)})
    pins = tuple(values[:5])
    source_pin = pins[2]
    runtime_ready = _runtime(pins, arguments)

    from thericher_v2.execution.paper_peer_visit import process_start
    from thericher_v2.ops import h3_dec4_point_join as join
    from thericher_v2.ops import h3_dec4_point_owner as owner

    _require((OPENS, LAST_START, HARD_STOP) == (owner.OPENS, owner.LAST_START, owner.HARD_STOP))
    _require((DEC3_SOURCE, DEC3_PIN) == (owner._DATA / "source", owner.DATA_SOURCE_SHA256))
    pid = os.getpid()
    birth = process_start(pid)
    owner._birth(birth)

    def ready():
        return process_start(pid) == birth and runtime_ready() is True

    if mode == "child":
        parent, parent_birth, launch_pin = values[5:]
        _require(parent == str(os.getppid()) and _digest(launch_pin))
        parent_pid = int(parent)
        owner._birth(parent_birth)
        argv = _child_argv(pins, parent_pid, parent_birth)
        _require(tuple(sys.orig_argv) == (*argv, launch_pin))
        env = {"SystemRoot": os.environ["SystemRoot"]}
        _require({k.upper() for k in os.environ} == {"SYSTEMROOT"} and _in_job())
        record = json.loads(owner._pinned(CONTROL / "POINT-LAUNCH.json", launch_pin, 16_384))
        _require(record["command_sha256"] == _sha(owner._json([argv, str(SOURCE), env])))

        def child_ready():
            return process_start(parent_pid) == parent_birth and ready()

        _require(child_ready())
        join.run_supervised_point_child(
            control=CONTROL,
            point_source_sha256=source_pin,
            launch_sha256=launch_pin,
            owner_ready=child_ready,
            data_owner_closed=_data_closure(process_start),
        )
        return

    handoff, pending = CONTROL / HANDOFF, CONTROL / (HANDOFF + ".pending")
    owner._absent(handoff)
    owner._absent(pending)
    digest = join.supervise_dec4_point(
        argv=_child_argv(pins, pid, birth),
        cwd=SOURCE,
        control=CONTROL,
        point_source_sha256=source_pin,
        owner_ready=ready,
    )
    _require(_digest(digest) and ready() and datetime.now(UTC) < HARD_STOP)
    owner._write_once(pending, digest.encode("ascii"))
    _require(ready() and datetime.now(UTC) < HARD_STOP)
    owner._absent(handoff)
    pending.rename(handoff)


def main():
    try:
        _run(tuple(sys.argv[1:]))
    except Exception:
        return 20
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
