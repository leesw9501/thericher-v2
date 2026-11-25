"""Supervise one credential-free Dec4 point publication, not a financial effect."""

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from thericher_v2.execution.kis_paper_data_capture import _safe_path
from thericher_v2.execution.paper_peer_visit import process_start
from thericher_v2.ops import h3_dec4_point_owner as owner
from thericher_v2.ops.h3_dec4_watchdog import supervise_host

_LAUNCH = "POINT-LAUNCH.json"
_START = "POINT-CHILD-START.json"
_RETURN = "POINT-CHILD-RETURN.json"
_COMPLETE = "POINT-SUPERVISED.json"
_PENDING = "POINT-SUPERVISED.pending"
_LINKS = {
    "attempt_sha256": "POINT-ATTEMPT.json",
    "data_attempt_sha256": "owner/ATTEMPT.json",
    "data_owner_sha256": "OWNER-CLOSED.json",
    "ready_sha256": "input/READY.json",
    "data_ready_sha256": "input/DATA-READY.json",
    "point_sha256": "point/POINT.json",
}


def _identity(paths):
    return tuple(
        (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        for stat in (_safe_path(path).lstat() for path in paths)
    )


def _now():
    return datetime.now(UTC)


def _monotonic():
    return time.monotonic()


def _window(now, end):
    if not owner._is_utc(now) or not owner.OPENS <= now < end:
        raise ValueError("dec4_point_join_clock")
    return now


def _scope(control, source):
    run = owner._DATA / "run"
    if (
        not owner._digest(source)
        or not control.is_absolute()
        or _safe_path(control) != control
        or not control.is_dir()
        or control.is_relative_to(run)
        or run.is_relative_to(control)
    ):
        raise ValueError("dec4_point_join_scope")
    return run


def _read_record(path, schema, *fields):
    raw = owner._read(path)
    record = owner._record(raw, {"schema", *fields})
    if record["schema"] != schema:
        raise ValueError("dec4_point_join_schema")
    return raw, record


def _launch(control, source, expected):
    raw, record = _read_record(
        control / _LAUNCH,
        "H3_DEC4_POINT_LAUNCH_V1",
        "nonce",
        "source_sha256",
        "command_sha256",
        "started_at",
    )
    if (
        owner._sha(raw) != expected
        or record["source_sha256"] != source
        or not owner._digest(record["command_sha256"])
    ):
        raise ValueError("dec4_point_join_launch")
    return _window(owner._stamp(record["started_at"]), owner.LAST_START)


def _publication(run, source):
    owner._absent(run / "point/OWNER-CLOSED.pending")
    owner._absent(run / "point/POINT.pending")
    raw, closed = _read_record(
        run / "point/OWNER-CLOSED.json",
        "H3_DEC4_POINT_OWNER_CLOSED_V1",
        "source_sha256",
        "source72_sha256",
        "data_source_sha256",
        "closed_at",
        "financial_authority",
        *_LINKS,
    )
    if (
        closed["source_sha256"] != source
        or closed["source72_sha256"] != owner.SOURCE72_SHA256
        or closed["data_source_sha256"] != owner.DATA_SOURCE_SHA256
        or closed["financial_authority"] is not False
        or not all(owner._digest(closed[key]) for key in _LINKS)
    ):
        raise ValueError("dec4_point_join_owner")
    linked = {key: owner._pinned(run / path, closed[key], 16_384) for key, path in _LINKS.items()}
    attempt = owner._record(linked["attempt_sha256"], {"schema", "source_sha256", "started_at"})
    if attempt["schema"] != "H3_DEC4_POINT_ATTEMPT_V1" or attempt["source_sha256"] != source:
        raise ValueError("dec4_point_join_attempt")
    started = _window(owner._stamp(attempt["started_at"]), owner.LAST_START)
    closed_at = _window(owner._stamp(closed["closed_at"]), owner.HARD_STOP)
    if started > closed_at:
        raise ValueError("dec4_point_join_clock")
    return owner._sha(raw), closed, started, closed_at


def run_supervised_point_child(
    *, control: Path, point_source_sha256: str, launch_sha256: str, owner_ready, data_owner_closed
) -> None:
    """Entry for the pinned direct Job root, never an intermediate launcher."""
    run = _scope(control, point_source_sha256)
    armed = _launch(control, point_source_sha256, launch_sha256)
    pid = os.getpid()
    birth = process_start(pid)
    started = _window(_now(), owner.LAST_START)
    if not (
        owner._ticks(armed) <= owner._birth(birth) <= owner._ticks(started)
        and owner_ready() is True
    ):
        raise ValueError("dec4_point_join_child")
    start = owner._json(
        dict(
            schema="H3_DEC4_POINT_CHILD_START_V1",
            launch_sha256=launch_sha256,
            pid=pid,
            native_start=birth,
            started_at=started.isoformat(),
        )
    )
    owner._write_once(control / _START, start)
    point_sha256 = owner.run_dec4_point_owner(
        point_source_sha256=point_source_sha256,
        owner_ready=owner_ready,
        data_owner_closed=data_owner_closed,
        clock=_now,
    )
    digest, closed, attempt_at, closed_at = _publication(run, point_source_sha256)
    returned = _window(_now(), owner.HARD_STOP)
    if not (
        started <= attempt_at <= closed_at <= returned
        and point_sha256 == closed["point_sha256"]
        and owner._read(control / _START) == start
        and owner_ready() is True
    ):
        raise ValueError("dec4_point_join_child_return")
    owner._write_once(
        control / _RETURN,
        owner._json(
            dict(
                schema="H3_DEC4_POINT_CHILD_RETURN_V1",
                child_start_sha256=owner._sha(start),
                owner_closed_sha256=digest,
                returned_at=returned.isoformat(),
            )
        ),
    )


def _join(control, run, source, launch_sha256, pid, birth, joined):
    paths = (
        *(control / name for name in (_LAUNCH, _START, _RETURN)),
        run / "point/OWNER-CLOSED.json",
        *(run / path for path in _LINKS.values()),
    )
    before = _identity(paths)
    armed = _launch(control, source, launch_sha256)
    start_raw, start = _read_record(
        control / _START,
        "H3_DEC4_POINT_CHILD_START_V1",
        "launch_sha256",
        "pid",
        "native_start",
        "started_at",
    )
    returned_raw, returned = _read_record(
        control / _RETURN,
        "H3_DEC4_POINT_CHILD_RETURN_V1",
        "child_start_sha256",
        "owner_closed_sha256",
        "returned_at",
    )
    closure, closed, attempt_at, closed_at = _publication(run, source)
    started = owner._stamp(start["started_at"])
    returned_at = owner._stamp(returned["returned_at"])
    if (
        start["launch_sha256"] != launch_sha256
        or type(pid) is not int
        or not 0 < pid < 2**32
        or type(start["pid"]) is not int
        or start["pid"] != pid
        or start["native_start"] != birth
        or returned["child_start_sha256"] != owner._sha(start_raw)
        or returned["owner_closed_sha256"] != closure
        or not owner._ticks(armed) <= owner._birth(birth) <= owner._ticks(started)
        or not started <= attempt_at <= closed_at <= returned_at <= joined < owner.HARD_STOP
    ):
        raise ValueError("dec4_point_join_mismatch")
    if before != _identity(paths):
        raise ValueError("dec4_point_join_changed")
    return before, owner._json(
        dict(
            schema="H3_DEC4_POINT_SUPERVISED_V1",
            source_sha256=source,
            launch_sha256=launch_sha256,
            pid=pid,
            native_start=birth,
            disposition="EXITED",
            exit_code=0,
            joined_at=joined.isoformat(),
            child_return_sha256=owner._sha(returned_raw),
            owner_closed_sha256=closure,
            point_sha256=closed["point_sha256"],
        )
    )


def supervise_dec4_point(
    *, argv: tuple[str, ...], cwd: Path, control: Path, point_source_sha256: str, owner_ready
) -> str:
    """Return a completion digest, or raise with no conclusion about effects.

    The caller must attest an ACL-protected control directory, pinned source,
    exact direct interpreter/argv/cwd and sole ownership. The child entry must
    forward the appended launch digest, exit zero only on success, and have
    no broker/daemon capability. No inherited environment except SystemRoot.
    Consumed claims (including partial writes) are never removed or resumed.
    """
    run = _scope(control, point_source_sha256)
    first_tick = _monotonic()
    armed = _window(_now(), owner.LAST_START)
    deadline = first_tick + (owner.HARD_STOP - armed).total_seconds()
    start_deadline = first_tick + (owner.LAST_START - armed).total_seconds()
    if (
        type(argv) is not tuple
        or not argv
        or any(type(arg) is not str or "\0" in arg for arg in argv)
        or not Path(argv[0]).is_absolute()
        or not cwd.is_absolute()
        or owner_ready() is not True
    ):
        raise ValueError("dec4_point_join_not_ready")
    env = {"SystemRoot": os.environ["SystemRoot"]}
    for name in (_LAUNCH, _START, _RETURN, _COMPLETE, _PENDING):
        owner._absent(control / name)
    owner._absent(run / "POINT-ATTEMPT.json")
    owner._absent(run / "point")

    last = armed

    def before_start():
        nonlocal last
        now = _window(_now(), owner.LAST_START)
        if now < last or _monotonic() >= start_deadline:
            raise ValueError("dec4_point_join_clock")
        last = now

    before_start()
    launch = owner._json(
        dict(
            schema="H3_DEC4_POINT_LAUNCH_V1",
            source_sha256=point_source_sha256,
            nonce=uuid4().hex,
            command_sha256=owner._sha(owner._json([argv, str(cwd), env])),
            started_at=armed.isoformat(),
        )
    )
    owner._write_once(control / _LAUNCH, launch)
    launch_sha256 = owner._sha(launch)
    before_start()
    result = supervise_host((*argv, launch_sha256), env=env, cwd=cwd, deadline=deadline)
    joined = _window(_now(), owner.HARD_STOP)
    if _monotonic() >= deadline or joined < last:
        raise ValueError("dec4_point_join_clock")
    if result.disposition != "EXITED" or type(result.exit_code) is not int or result.exit_code != 0:
        raise ValueError("dec4_point_join_unproven")
    snapshot = _join(
        control, run, point_source_sha256, launch_sha256, result.pid, result.native_start, joined
    )
    _, raw = snapshot
    owner._write_once(control / _PENDING, raw)
    if owner_ready() is not True or snapshot != _join(
        control, run, point_source_sha256, launch_sha256, result.pid, result.native_start, joined
    ):
        raise ValueError("dec4_point_join_changed")
    if _window(_now(), owner.HARD_STOP) < joined or _monotonic() >= deadline:
        raise ValueError("dec4_point_join_clock")
    owner._absent(control / _COMPLETE)
    (control / _PENDING).rename(control / _COMPLETE)
    digest = owner._sha(raw)
    read_supervised_point(
        control=control, point_source_sha256=point_source_sha256, completion_sha256=digest
    )
    return digest


def read_supervised_point(
    *, control: Path, point_source_sha256: str, completion_sha256: str
) -> str:
    """Read only: return the canonical owner closure digest or withhold proof.

    The caller supplies the independently retained supervisor digest and the
    protected source/control binding. A bare owner file or a digest echoed
    from an unqualified directory is not proof. This never certifies no effect.
    """
    run = _scope(control, point_source_sha256)
    owner._absent(control / _PENDING)
    raw = owner._pinned(control / _COMPLETE, completion_sha256, 16_384)
    receipt = owner._record(
        raw,
        {
            "schema",
            "source_sha256",
            "launch_sha256",
            "pid",
            "native_start",
            "disposition",
            "exit_code",
            "joined_at",
            "child_return_sha256",
            "owner_closed_sha256",
            "point_sha256",
        },
    )
    joined = _window(owner._stamp(receipt["joined_at"]), owner.HARD_STOP)
    _, rebuilt = _join(
        control,
        run,
        point_source_sha256,
        receipt["launch_sha256"],
        receipt["pid"],
        receipt["native_start"],
        joined,
    )
    if raw != rebuilt:
        raise ValueError("dec4_point_join_receipt")
    owner._absent(control / _PENDING)
    if owner._read(control / _COMPLETE) != raw:
        raise ValueError("dec4_point_join_changed")
    return receipt["owner_closed_sha256"]
