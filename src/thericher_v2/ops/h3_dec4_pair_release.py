"""Shared immutable release and phase-local restore pins for the Dec4/9 pair."""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.h3_dec4_native_host import dec4_native_plan_fields
from thericher_v2.ops.h3_dec4_scheduler_provider import _file_stamp, _open_locked, _path_stamp

_PHASES = ("entry", "exit")
_PINS = {
    "observer_plan_sha256",
    "observer_restore_daemon_sha256",
    "observer_restore_writer_guard_sha256",
}


def _need(ok):
    pv._need(ok, "h3_dec4_pair_release")


def _executable_sha256(path):
    pv.ordinary(path)
    stamp = _path_stamp(path)
    # Windows lstat adds executable mode bits based on the filename; fstat does not.
    with _open_locked(path) if os.name == "nt" else path.open("rb") as stream:
        _need(_file_stamp(os.fstat(stream.fileno())) == stamp)
        raw = stream.read(32 * 1024 * 1024 + 1)
        _need(len(raw) == stamp[2] <= 32 * 1024 * 1024 and _path_stamp(path) == stamp)
    return sha256(raw).hexdigest()


def phase_restore_pins(source, phase):
    _need(phase in _PHASES and type(source) is dict)
    rows = source.get("restore_native")
    _need(type(rows) is dict and rows.keys() == set(_PHASES))
    row = rows.get(phase)
    _need(type(row) is dict)
    pins = row.get("pins")
    _need(type(pins) is dict and pins.keys() == _PINS and all(map(pv._hash, pins.values())))
    return pins


def read_pair_release(source_root, phase, source_pin, release_pin):
    """Authenticate both static grants and select one; no sibling runtime check."""
    _need(phase in _PHASES and pv._hash(source_pin) and pv._hash(release_pin))
    raw, _ = pv._read(source_root.parent / "RELEASE.json")
    _need(sha256(raw).hexdigest() == release_pin)
    value = pv._decode(raw)
    _need(
        type(value) is dict
        and value.keys() == {"schema", "source", "phases"}
        and value["schema"] == "h3-dec4-protected-pair-release-v1"
        and value["source"] == source_pin
        and type(value["phases"]) is dict
        and value["phases"].keys() == set(_PHASES)
    )
    for name, grant in value["phases"].items():
        _need(
            type(grant) is dict
            and grant.keys() == {"phase", "allow_execute", "actual_financial_admission"}
            and grant["phase"] == name
            and grant["allow_execute"] is True
            and grant["actual_financial_admission"] is False
        )
    return {"source": source_pin, **value["phases"][phase]}


@dataclass(frozen=True, slots=True, repr=False)
class Dec4PairSource:
    """Keep the launcher's source verifier while fixing the release reader."""

    original: object
    phase: str

    @property
    def ROOT(self):
        return self.original.ROOT

    @property
    def ROUND(self):
        return self.original.ROUND

    @property
    def SLOTS(self):
        return self.original.SLOTS

    def check(self, pin):
        return self.original.check(pin)

    def release(self, value, pin, digest):
        _need(value.get("synthetic_only", False) is False)
        phase_restore_pins(value, self.phase)
        return read_pair_release(self.ROOT, self.phase, pin, digest)

    def action(self, pin, release_pin, phase):
        _need(phase == self.phase)
        return self.original.action(pin, release_pin, phase)

    def window(self, phase, at):
        _need(phase == self.phase)
        return self.original.window(phase, at)


@dataclass(frozen=True, slots=True, repr=False)
class _ScheduledSource:
    ROOT: Path
    phase: str
    pin: str
    release_pin: str
    action_text: str
    launcher: Path
    launcher_pin: str
    executable: Path
    executable_pin: str
    ROUND = ROUND

    @property
    def SLOTS(self):
        start, end, hard = _TIMES[self.phase]
        return {
            self.phase: dict(
                name=TASKS[self.phase],
                start_UTC=start.isoformat(),
                end_UTC=end.isoformat(),
                hard_UTC=hard.isoformat(),
            )
        }

    def check(self, pin):
        _need(pin == self.pin)
        raw, _ = pv._read(self.ROOT / "SOURCE.json")
        _need(sha256(raw).hexdigest() == pin)
        value = pv._decode(raw)
        _need(type(value) is dict)
        files, bootstrap = value.get("files"), value.get("restore_bootstrap")
        _need(
            value.get("synthetic_only", False) is False
            and type(files) is dict
            and type(bootstrap) is dict
            and files.get(self.launcher.relative_to(self.ROOT).as_posix()) == self.launcher_pin
            and bootstrap.get("executable") == str(self.executable)
            and bootstrap.get("executable_sha256") == self.executable_pin
            and sha256(pv._read(self.launcher)[0]).hexdigest() == self.launcher_pin
            and _executable_sha256(self.executable) == self.executable_pin
        )
        return value

    def action(self, pin, release_pin, phase):
        _need((pin, release_pin, phase) == (self.pin, self.release_pin, self.phase))
        return self.action_text

    def window(self, phase, at):
        _need(phase == self.phase)
        start, end, _ = _TIMES[self.phase]
        _need(isinstance(at, datetime) and at.utcoffset() == timedelta(0) and start <= at < end)
        return start, end


def bind_dec4_scheduled_pair_source(root, schedule_plan, pin, release_pin, phase):
    """Join the same protected install plan to the bank's source ABI.

    The outer bootstrap authenticates the plan and independently protected
    native profile pins. This is a static bind, never a Scheduler observation.
    """
    expected, argv, action = dec4_native_plan_fields(schedule_plan, pin, phase, release_pin)
    launcher, executable = Path(argv[4]), Path(argv[0])
    launcher_pin, executable_pin = (
        schedule_plan.get("launcher_sha256"),
        schedule_plan.get("pythonw_sha256"),
    )
    _need(
        isinstance(root, Path)
        and root.is_absolute()
        and ".." not in root.parts
        and expected["dispatcher_root"] == str(root)
        and launcher.is_absolute()
        and launcher.is_relative_to(root)
        and ".." not in launcher.parts
        and launcher.suffix.casefold() in {".py", ".pyw"}
        and executable.is_absolute()
        and ".." not in executable.parts
        and executable.name.casefold() == "pythonw.exe"
        and pv._hash(launcher_pin)
        and pv._hash(executable_pin)
    )
    return Dec4PairSource(
        _ScheduledSource(
            root,
            phase,
            pin,
            release_pin,
            action,
            launcher,
            launcher_pin,
            executable,
            executable_pin,
        ),
        phase,
    )
