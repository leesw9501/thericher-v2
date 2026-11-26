"""Join the fixed-half owner's returned digest to its exact Windows Job exit.

No CLI: a separately protected host must bind the actual supervisor/child
entrypoints, identities, runtime, ACLs, network denial and independent receipt
retention. This module does not create that authority or discover a seal.
"""

import ctypes as C
import hashlib
import json
import os
import re
import stat
import sys
import time
from ctypes import wintypes as W
from datetime import UTC, datetime
from pathlib import Path

SOURCE = Path(
    "D:/thericher-v2/model-artifacts/research/h3-dec4-fixed-half-forecast-20261204-v1/source"
)
SOURCE_PIN = "30b37958da1b7412e2e07ddaea36f7b067147c3e52d0c657135b5415fde14953"
ENTRY_PIN = "afcae97f8618989d964fb794d5720bfb7694bafd2fa67e4b5adca64baf2aa194"
WATCHDOG = SOURCE / "src/thericher_v2/ops/h3_dec4_watchdog.py"
WATCHDOG_PIN = "3cb73f46044c55475290e30e04d92ad4fca0ac517c07c2676d814d5477877723"
OPENS = datetime(2026, 12, 4, 14, 12, tzinfo=UTC)
LAST_START = OPENS.replace(minute=13)
HARD_STOP = OPENS.replace(minute=25)
LAUNCH, RETURN, COMPLETE = (f"FIXED-HALF-{name}.json" for name in ("LAUNCH", "RETURN", "JOB"))


def _require(condition):
    if not condition:
        raise ValueError("dec4_fixed_half_host_binding")


def _now():
    return datetime.now(UTC)


def _gate(host_ready, end, earliest=None):
    before = _now()
    _require((OPENS if earliest is None else earliest) <= before < end and host_ready() is True)
    after = _now()
    _require(before <= after < end)
    return after


def _scope(control):
    _require(
        isinstance(control, Path)
        and control.is_absolute()
        and not control.is_relative_to(SOURCE.parent)
        and not SOURCE.parent.is_relative_to(control)
        and control.resolve(strict=True) == control
        and all(stat.S_ISDIR(_ordinary(path).st_mode) for path in (control, *control.parents))
    )


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _ordinary(path):
    info = path.lstat()
    _require(not getattr(info, "st_file_attributes", 0) & 0x400)
    return info


def _read(path, limit=16_384):
    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

    info = _ordinary(path)
    _require(stat.S_ISREG(info.st_mode) and info.st_size <= limit)
    before = identity(info)
    with path.open("rb") as stream:
        _require(identity(os.fstat(stream.fileno())) == before)
        raw = stream.read(limit + 1)
        _require(identity(os.fstat(stream.fileno())) == before)
    _require(identity(_ordinary(path)) == before and len(raw) == info.st_size)
    return raw


def _absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise FileExistsError("dec4_fixed_half_host_consumed")


def _write_once(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _require(_read(path) == raw)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _record(raw, fields):
    value = json.loads(raw)
    _require(type(value) is dict and value.keys() == fields and _json(value) == raw)
    return value


def _stamp(value):
    stamp = datetime.fromisoformat(value)
    _require(stamp.utcoffset() == UTC.utcoffset(stamp) and stamp.isoformat() == value)
    return stamp


def _ticks(at):
    delta = at - datetime(1601, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def _birth(value):
    _require(type(value) is str and re.fullmatch(r"win-filetime:[1-9][0-9]{0,18}", value))
    return int(value.split(":")[1])


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _self_birth():
    kernel = C.WinDLL("kernel32", use_last_error=True)
    check = kernel.IsProcessInJob
    check.argtypes = [W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)]
    check.restype = W.BOOL
    current = W.HANDLE(-1)
    inside = W.BOOL()
    _require(check(current, None, C.byref(inside)) and inside.value)
    get = kernel.GetProcessTimes
    get.argtypes = [W.HANDLE, *([C.POINTER(W.FILETIME)] * 4)]
    get.restype = W.BOOL
    stamps = [W.FILETIME() for _ in range(4)]
    _require(get(current, *(C.byref(stamp) for stamp in stamps)))
    birth = stamps[0]
    return f"win-filetime:{(birth.dwHighDateTime << 32) | birth.dwLowDateTime}"


def _load_pinned(path, pin):
    raw = _read(path, 64 * 1024)
    _require(_sha(raw) == pin)
    namespace = {"__file__": str(path), "__name__": "_fixed_half_pinned_source"}
    exec(compile(raw, str(path), "exec", dont_inherit=True), namespace)
    return namespace


def _released_owner():
    entry = SOURCE / "scripts/run_h3_dec4_fixed_half.py"
    # Load by exact bytes without preloading thericher_v2 in the isolated child.
    runner = _load_pinned(entry, ENTRY_PIN)
    _require(
        (runner["OPENS"], runner["LAST_START"], runner["HARD_STOP"])
        == (OPENS, LAST_START, HARD_STOP)
    )
    return runner["run_fixed_half_owner"]


def _command(argv, cwd, env):
    return _sha(_json([argv, str(cwd), env]))


def run_fixed_half_job_child(*, control, launch_sha256, host_ready):
    """Called only by the prebound direct Job entrypoint; failures must exit nonzero."""
    _scope(control)
    started = _gate(host_ready, LAST_START)
    path = control / LAUNCH
    raw = _read(path)
    _require(_sha(raw) == launch_sha256)
    launch = _record(raw, {"source_sha256", "command_sha256", "armed_at"})
    argv = tuple(sys.orig_argv)
    _require(
        argv[-1:] == (launch_sha256,)
        and {name.upper() for name in os.environ} == {"SYSTEMROOT"}
        and sys.flags.isolated
        and sys.flags.no_site
        and sys.dont_write_bytecode
        and launch["source_sha256"] == SOURCE_PIN
        and launch["command_sha256"]
        == _command(argv[:-1], Path.cwd(), {"SystemRoot": os.environ["SystemRoot"]})
    )
    armed = _stamp(launch["armed_at"])
    pid = os.getpid()
    birth = _self_birth()
    _require(OPENS <= armed <= started and _ticks(armed) <= _birth(birth) <= _ticks(started))
    digest = _released_owner()(SOURCE_PIN, host_ready=host_ready)
    returned = _gate(host_ready, HARD_STOP, started)
    _require(_digest(digest) and _self_birth() == birth and _read(path) == raw)
    _write_once(
        control / RETURN,
        _json(
            dict(
                launch_sha256=launch_sha256,
                pid=pid,
                native_start=birth,
                seal_sha256=digest,
                started_at=started.isoformat(),
                returned_at=returned.isoformat(),
            )
        ),
    )


def supervise_fixed_half_job(*, argv, cwd, control, host_ready):
    """Return the receipt SHA256 for independent retention, never a seal lookup.

    argv must be the independently bound direct child command, without the
    final launch digest. The caller attests both entrypoints and sole custody
    of the control directory; the child has its own host attestation probe.
    A consumed or partial claim is never resumed here.
    """
    _scope(control)
    tick = time.monotonic()
    armed = _gate(host_ready, LAST_START)
    _require(
        type(argv) is tuple
        and argv
        and all(type(arg) is str and "\0" not in arg for arg in argv)
        and Path(argv[0]).is_absolute()
        and cwd.is_absolute()
    )
    deadline = tick + (HARD_STOP - armed).total_seconds()
    start_deadline = tick + (LAST_START - armed).total_seconds()
    env = {"SystemRoot": os.environ["SystemRoot"]}
    for name in (LAUNCH, RETURN, COMPLETE):
        _absent(control / name)
    supervise_host = _load_pinned(WATCHDOG, WATCHDOG_PIN)["supervise_host"]
    launch = _json(
        dict(
            source_sha256=SOURCE_PIN,
            command_sha256=_command(argv, cwd, env),
            armed_at=armed.isoformat(),
        )
    )
    _write_once(control / LAUNCH, launch)
    launch_sha256 = _sha(launch)
    before_start = _gate(host_ready, LAST_START, armed)
    _require(time.monotonic() < start_deadline)
    result = supervise_host((*argv, launch_sha256), env=env, cwd=cwd, deadline=deadline)
    joined = _gate(host_ready, HARD_STOP, before_start)
    _require(
        result.disposition == "EXITED"
        and type(result.exit_code) is int
        and result.exit_code == 0
        and type(result.pid) is int
        and 0 < result.pid < 2**32
    )
    raw = _read(control / RETURN)
    returned = _record(
        raw, {"launch_sha256", "pid", "native_start", "seal_sha256", "started_at", "returned_at"}
    )
    start, end = (_stamp(returned[key]) for key in ("started_at", "returned_at"))
    _require(
        returned["launch_sha256"] == launch_sha256
        and type(returned["pid"]) is int
        and returned["pid"] == result.pid
        and returned["native_start"] == result.native_start
        and _digest(returned["seal_sha256"])
        and before_start <= start < LAST_START
        and start <= end <= joined
        and _ticks(before_start) <= _birth(result.native_start) <= _ticks(start)
        and _read(control / LAUNCH) == launch
        and _read(control / RETURN) == raw
    )
    receipt = _json(
        dict(
            schema="H3_DEC4_FIXED_HALF_JOB_V1",
            source_sha256=SOURCE_PIN,
            launch_sha256=launch_sha256,
            child_return_sha256=_sha(raw),
            pid=result.pid,
            native_start=result.native_start,
            disposition=result.disposition,
            exit_code=result.exit_code,
            closed_at=joined.isoformat(),
            seal_sha256=returned["seal_sha256"],
        )
    )
    _gate(host_ready, HARD_STOP, joined)
    _require(time.monotonic() < deadline)
    _write_once(control / COMPLETE, receipt)
    _gate(host_ready, HARD_STOP, joined)
    _require(time.monotonic() < deadline)
    return _sha(receipt)
