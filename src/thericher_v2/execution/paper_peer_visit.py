"""Same-OS whole-bank Paper leg exclusion for source-qualified capsule adapters.

Hold BankLeg across seed/effect/postseed; compose Visit for each child/container
visit. This module never opens financial custody, calls Docker, or releases a
reservation. A frozen adapter, NOT model output, must supply fresh exact Job and
container closure evidence. Evidence hashes bind receipts; they do not attest
their truth. All adapters must share one control root and canonical engine name.
Windows byte locks and POSIX flock do NOT coordinate across operating systems.
Unknown/crashed claims deliberately have no automatic recovery/age reclaim API.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from uuid import uuid4


class Denied(RuntimeError):
    """Categorical operational failure; never includes raw payloads."""


class Held(Denied):
    """Locally defer without waiting, spending a visit, or clearing a claim."""


def _need(ok, reason):
    if not ok:
        raise Denied(reason)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def _same(left, right):
    try:
        return encode(left) == encode(right)
    except (ValueError, TypeError, RecursionError):
        return False


def _hash(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


def _run(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{32}", value) is not None


def _start(value):
    return (
        type(value) is str
        and re.fullmatch(r"(?:win-filetime|linux-startticks):[1-9][0-9]*", value) is not None
    )


def canonical_bank(engine: str, volume: str) -> dict:
    """Normalize a local daemon endpoint; aliases require adapter qualification."""
    _need(type(engine) is str and type(volume) is str, "bank_identity")
    engine = engine.replace("\\", "/")
    if re.fullmatch(r"npipe:////\./pipe/[A-Za-z0-9_.-]+", engine, re.IGNORECASE):
        engine = engine.casefold()
    else:
        _need(engine.startswith("unix:///") and "\x00" not in engine, "bank_engine")
        path = engine[7:]
        _need(str(PurePosixPath(path)) == path and ".." not in path.split("/"), "bank_engine")
    _need(re.fullmatch("[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", volume), "bank_volume")
    return {"engine": engine, "volume": volume}


def bank_key(bank: dict) -> str:
    _need(type(bank) is dict and set(bank) == {"engine", "volume"}, "bank_identity")
    _need(canonical_bank(**bank) == bank, "bank_not_canonical")
    return digest(bank)


def _identity(value, key):
    _need(
        type(value) is dict
        and set(value) == {"source", "release", "group", "member", "run", "argv_sha256", "bank"},
        "leg_identity",
    )
    _need(
        all(_hash(value[k]) for k in ("source", "release", "group", "argv_sha256", "bank"))
        and value["bank"] == key
        and _run(value["run"]),
        "leg_identity",
    )
    _need(
        type(value["member"]) is str
        and re.fullmatch("[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value["member"]),
        "leg_identity",
    )


def _signature(s):
    # Windows lstat/fstat can report different ctime meanings after replacement.
    return (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns)


def ordinary(path):
    """No links/reparse points, special files, or multiply linked regular files."""
    _need(path.is_absolute(), "path_absolute_required")
    for node in (path, *path.parents):
        try:
            s = node.lstat()
        except FileNotFoundError:
            continue
        _need(
            not stat.S_ISLNK(s.st_mode) and not getattr(s, "st_file_attributes", 0) & 1024,
            "path_reparse",
        )
        _need(
            stat.S_ISDIR(s.st_mode) or (stat.S_ISREG(s.st_mode) and s.st_nlink == 1),
            "path_type_or_hardlink",
        )


def _read(path):
    ordinary(path)
    before = path.lstat()
    _need(stat.S_ISREG(before.st_mode), "record_type")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        _need(_signature(before) == _signature(os.fstat(stream.fileno())), "file_changed")
        raw = stream.read(1024 * 1024 + 1)
        _need(len(raw) <= 1024 * 1024, "record_size")
        _need(_signature(before) == _signature(os.fstat(stream.fileno())), "file_changed")
    ordinary(path)
    _need(_signature(before) == _signature(path.lstat()), "file_changed")
    return raw, _signature(before)


def _new(path, raw):
    ordinary(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    actual = _read(path)
    _need(actual[0] == raw, "file_changed")
    return actual


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result, "record_duplicate_key")
            result[key] = value
        return result

    def constant(_):
        raise Denied("record_nonfinite")

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
        _need(encode(value) == raw, "record_noncanonical")
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Denied("record_malformed") from None


def process_start(pid):
    """Native start identity; None means positive OS absence/termination only."""
    _need(type(pid) is int and pid > 0, "process_identity")
    if os.name == "nt":
        from ctypes import wintypes as w

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        k.OpenProcess.restype = w.HANDLE
        k.GetProcessTimes.argtypes = [w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)]
        k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        k.CloseHandle.argtypes = [w.HANDLE]
        handle = k.OpenProcess(0x1000, False, pid)
        if not handle:
            _need(ctypes.get_last_error() == 87, "process_identity_unknown")
            return None
        try:
            code = w.DWORD()
            _need(k.GetExitCodeProcess(handle, ctypes.byref(code)), "process_identity_unknown")
            if code.value != 259:
                return None
            times = [w.FILETIME() for _ in range(4)]
            _need(
                k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)),
                "process_identity_unknown",
            )
            return "win-filetime:" + str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        finally:
            k.CloseHandle(handle)
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text()
    except FileNotFoundError:
        return None
    fields = raw[raw.rfind(")") + 2 :].split()
    return None if fields[0] == "Z" else "linux-startticks:" + fields[19]


class Gate:
    """Nonblocking same-OS file lock; its release never clears durable state."""

    def __init__(self, root):
        self.root, self.file = Path(root), None

    def __enter__(self):
        _need(self.file is None, "gate_already_owned")
        ordinary(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        ordinary(self.root)
        self.directories = [
            (p, (p.lstat().st_dev, p.lstat().st_ino)) for p in (self.root, *self.root.parents)
        ]
        self.path = self.root / "HOST-VISIT.lock"
        try:
            _new(self.path, b"0")
        except FileExistsError:
            pass
        ordinary(self.path)
        before = _signature(self.path.lstat())
        self.file = self.path.open("r+b")
        try:
            _need(_signature(os.fstat(self.file.fileno())) == before, "gate_changed")
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.__exit__()
            raise Held("bank_busy") from None
        except BaseException:
            self.__exit__()
            raise
        self.signature = before
        try:
            self.check()
        except BaseException:
            self.__exit__()
            raise
        return self

    def check(self):
        _need(self.file is not None and not self.file.closed, "gate_not_owned")
        for path, identity in self.directories:
            ordinary(path)
            current = path.lstat()
            _need((current.st_dev, current.st_ino) == identity, "gate_directory_changed")
        _need(_signature(os.fstat(self.file.fileno())) == self.signature, "gate_changed")
        ordinary(self.path)
        _need(_signature(self.path.lstat()) == self.signature, "gate_changed")
        self.file.seek(0)
        _need(self.file.read(2) == b"0", "gate_changed")
        self.file.seek(0)

    def __exit__(self, *_):
        if self.file is not None:
            self.file.close()
            self.file = None


def _record(value, key):
    _need(
        type(value) is dict
        and set(value)
        == {"schema", "identity", "owner", "sequence", "visits", "reservation_release"},
        "record_schema",
    )
    _need(
        value["schema"] == "paper-bank-leg-v1"
        and value["reservation_release"] is False
        and type(value["sequence"]) is int
        and value["sequence"] >= 0,
        "record_schema",
    )
    _identity(value["identity"], key)
    owner = value["owner"]
    _need(
        type(owner) is dict
        and set(owner) == {"pid", "native_start"}
        and type(owner["pid"]) is int
        and owner["pid"] > 0
        and _start(owner["native_start"]),
        "record_owner",
    )
    _need(type(value["visits"]) is list, "record_visits")
    seen = set()
    active_seen = False
    for visit in value["visits"]:
        _need(
            type(visit) is dict
            and set(visit) == {"run", "kind", "status", "children", "create", "closure"},
            "record_visit",
        )
        _need(not active_seen, "record_visit_order")
        active_seen = visit["status"] == "ACTIVE"
        _need(
            _run(visit["run"])
            and visit["run"] not in seen
            and visit["kind"] in ("seed", "effect", "postseed", "recovery")
            and visit["status"] in ("ACTIVE", "CLOSED")
            and type(visit["children"]) is list,
            "record_visit",
        )
        seen.add(visit["run"])
        create = visit["create"]
        _need(
            type(create) is dict and set(create) == {"resolution", "spec_sha256", "cid"},
            "record_create",
        )
        resolution = create["resolution"]
        _need(
            resolution
            in ("NOT_ATTEMPTED", "ATTEMPTED_UNRESOLVED", "ACK_EXACT_CID", "DISCOVERED_EXACT_SCOPE"),
            "record_create",
        )
        _need(
            (
                create["spec_sha256"] is None
                if resolution == "NOT_ATTEMPTED"
                else _hash(create["spec_sha256"])
            )
            and (
                create["cid"] is None
                if resolution in ("NOT_ATTEMPTED", "ATTEMPTED_UNRESOLVED")
                else _hash(create["cid"])
            ),
            "record_create",
        )
        tokens = set()
        for child in visit["children"]:
            _need(
                type(child) is dict
                and set(child) == {"token", "argv_sha256", "pid", "native_start", "status"},
                "record_child",
            )
            _need(
                _run(child["token"])
                and child["token"] not in tokens
                and _hash(child["argv_sha256"])
                and child["status"] in ("SPAWNING_PID_UNKNOWN", "RUNNING_OR_UNKNOWN", "JOINED")
                and (child["pid"] is None or type(child["pid"]) is int and child["pid"] > 0)
                and (child["native_start"] is None or _start(child["native_start"])),
                "record_child",
            )
            if child["status"] == "SPAWNING_PID_UNKNOWN":
                _need(child["pid"] is None and child["native_start"] is None, "record_child")
            else:
                _need(child["pid"] is not None, "record_child")
            if child["status"] == "JOINED":
                _need(_start(child["native_start"]), "record_child")
            tokens.add(child["token"])
        _need(
            visit["closure"] is None
            if visit["status"] == "ACTIVE"
            else _hash(visit["closure"])
            and all(c["status"] == "JOINED" for c in visit["children"]),
            "record_closure",
        )
        _need(visit["status"] != "CLOSED" or resolution != "ATTEMPTED_UNRESOLVED", "record_closure")


class BankLeg:
    """One whole-bank leg; callers debit only AFTER successful __enter__."""

    def __init__(self, root, *, bank, identity, process_probe=process_start):
        self.key = bank_key(bank)
        _identity(identity, self.key)
        self.identity = _decode(encode(identity))
        self.root = Path(root) / ("bank-" + self.key)
        self.active = self.root / "ACTIVE-LEG.json"
        self.gate = Gate(self.root)
        self.process_probe = process_probe
        self.record = None
        self.snapshot = None
        self.handles = []

    def __enter__(self):
        self.gate.__enter__()
        try:
            ordinary(self.active)
            if self.active.exists():
                value = _decode(_read(self.active)[0])
                _record(value, self.key)
                raise Held("durable_bank_leg_held")
            closed = self.root / ("CLOSED-" + self.identity["run"] + ".json")
            ordinary(closed)
            _need(not closed.exists(), "leg_run_already_closed")
            start = self.process_probe(os.getpid())
            _need(_start(start), "owner_start_unknown")
            self.record = dict(
                schema="paper-bank-leg-v1",
                identity=self.identity,
                owner=dict(pid=os.getpid(), native_start=start),
                sequence=0,
                visits=[],
                reservation_release=False,
            )
            self.snapshot = _new(self.active, encode(self.record))
            return self
        except BaseException:
            self.gate.__exit__()
            raise

    def check(self, expected_identity=None):
        self.gate.check()
        _need(self.record is not None and self.snapshot == _read(self.active), "claim_changed")
        _need(encode(self.record) == self.snapshot[0], "claim_memory_changed")
        _need(expected_identity is None or _same(expected_identity, self.identity), "leg_identity")
        owner = self.record["owner"]
        _need(
            owner["pid"] == os.getpid()
            and self.process_probe(owner["pid"]) == owner["native_start"],
            "owner_changed",
        )

    def _save(self, value):
        self.check()
        _record(value, self.key)
        _need(value["sequence"] == self.record["sequence"], "claim_stale_transition")
        value["sequence"] += 1
        raw = encode(value)
        temporary = self.root / ("ACTIVE-" + uuid4().hex + ".tmp")
        _new(temporary, raw)
        self.check()
        os.replace(temporary, self.active)
        snapshot = _read(self.active)
        _need(snapshot[0] == raw, "claim_changed")
        self.record, self.snapshot = value, snapshot

    def visit(self, run, *, kind):
        return Visit(self, run, kind=kind)

    def close(self):
        self.check()
        _need(all(v["status"] == "CLOSED" for v in self.record["visits"]), "visit_not_closed")
        receipt = {
            "status": "CLOSED_OPERATIONAL_ONLY",
            "record": self.record,
            "same_native_intent_reconciliation_required": True,
            "reservation_or_budget_release": False,
        }
        _new(self.root / ("CLOSED-" + self.identity["run"] + ".json"), encode(receipt))
        self.check()
        self.active.unlink()
        self.snapshot = None

    def __exit__(self, *_):
        self.gate.__exit__()


class Visit:
    """Durable child/create lifecycle inside a BankLeg, not a second lock."""

    def __init__(self, leg, run, *, kind):
        self.leg, self.run, self.kind = leg, run, kind

    def __enter__(self):
        self.leg.check()
        _need(
            _run(self.run) and self.kind in ("seed", "effect", "postseed", "recovery"),
            "visit_identity",
        )
        value = _decode(encode(self.leg.record))
        _need(
            all(v["status"] == "CLOSED" and v["run"] != self.run for v in value["visits"]),
            "visit_already_held",
        )
        value["visits"].append(
            dict(
                run=self.run,
                kind=self.kind,
                status="ACTIVE",
                children=[],
                create=dict(resolution="NOT_ATTEMPTED", spec_sha256=None, cid=None),
                closure=None,
            )
        )
        self.leg._save(value)
        return self

    def _value(self):
        self.leg.check()
        value = _decode(encode(self.leg.record))
        visit = next((v for v in value["visits"] if v["run"] == self.run), None)
        _need(visit is not None and visit["status"] == "ACTIVE", "visit_not_active")
        return value, visit

    def create_attempt(self, spec_sha256):
        value, visit = self._value()
        _need(
            _hash(spec_sha256) and visit["create"]["resolution"] == "NOT_ATTEMPTED",
            "create_already_attempted",
        )
        visit["create"] = dict(resolution="ATTEMPTED_UNRESOLVED", spec_sha256=spec_sha256, cid=None)
        self.leg._save(value)

    def create_ack(self, cid):
        value, visit = self._value()
        _need(
            _hash(cid) and visit["create"]["resolution"] == "ATTEMPTED_UNRESOLVED",
            "create_ack_unbound",
        )
        visit["create"].update(resolution="ACK_EXACT_CID", cid=cid)
        self.leg._save(value)

    def spawn(self, argv, *, factory=subprocess.Popen, pid_of=lambda p: p.pid, **kwargs):
        value, visit = self._value()
        _need(
            type(argv) in (list, tuple) and argv and all(type(a) is str for a in argv), "child_argv"
        )
        child = dict(
            token=uuid4().hex,
            argv_sha256=digest(list(argv)),
            pid=None,
            native_start=None,
            status="SPAWNING_PID_UNKNOWN",
        )
        visit["children"].append(child)
        self.leg._save(value)
        if factory is subprocess.Popen:
            kwargs.setdefault("stdin", subprocess.DEVNULL)
            kwargs.setdefault("stdout", subprocess.DEVNULL)
            kwargs.setdefault("stderr", subprocess.DEVNULL)
            if os.name == "nt":
                kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        handle = factory(list(argv), **kwargs)
        # Retain ownership BEFORE pid/start probing or persistence can fail.
        self.leg.handles.append(handle)
        value, visit = self._value()
        child = visit["children"][-1]
        child["pid"] = pid_of(handle)
        _need(type(child["pid"]) is int and child["pid"] > 0, "child_pid_unknown")
        child["status"] = "RUNNING_OR_UNKNOWN"
        self.leg._save(value)
        value, visit = self._value()
        child = visit["children"][-1]
        child["native_start"] = self.leg.process_probe(child["pid"])
        self.leg._save(value)
        _need(_start(child["native_start"]), "child_start_unknown")
        return handle

    def close(self, probe):
        """Invoke a frozen adapter only AFTER positive native child termination.

        Probe receives a detached full claim. It returns the exact closed schema
        below, binding identity/owner/visit/claim hash and per-child identities.
        An unresolved create needs DISCOVERED_EXACT_SCOPE plus an exact CID;
        an empty listing, missing CID, or caller bool can never settle it.
        """
        value, visit = self._value()
        for child in visit["children"]:
            _need(
                child["pid"] is not None and _start(child["native_start"]),
                "spawn_gap_requires_recovery",
            )
            now = self.leg.process_probe(child["pid"])
            _need(now is None or _start(now) and now != child["native_start"], "child_still_live")
        _need(callable(probe), "closure_probe_required")
        receipt = probe(_decode(encode(value)))
        self.leg.check()
        _need(_same(self.leg.record, value), "claim_changed_during_probe")
        _need(
            type(receipt) is dict
            and set(receipt)
            == {
                "schema",
                "identity",
                "owner",
                "visit",
                "record_sha256",
                "children",
                "create_resolution",
                "container",
                "container_status",
                "evidence_sha256",
            },
            "closure_schema",
        )
        _need(
            receipt["schema"] == "paper-bank-visit-closure-v1"
            and _same(receipt["identity"], self.leg.identity)
            and _same(receipt["owner"], value["owner"])
            and receipt["visit"] == self.run
            and receipt["record_sha256"] == digest(value)
            and _hash(receipt["evidence_sha256"]),
            "closure_identity",
        )
        expected = [
            {k: c[k] for k in ("token", "argv_sha256", "pid", "native_start")}
            | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
            for c in visit["children"]
        ]
        _need(_same(receipt["children"], expected), "child_closure_unbound")
        create = visit["create"]
        resolution, cid = receipt["create_resolution"], receipt["container"]
        if create["resolution"] == "NOT_ATTEMPTED":
            _need(resolution == "NOT_ATTEMPTED" and cid is None, "create_closure_unbound")
        elif create["resolution"] == "ATTEMPTED_UNRESOLVED":
            _need(resolution == "DISCOVERED_EXACT_SCOPE" and _hash(cid), "daemon_create_unresolved")
        else:
            _need(
                resolution == create["resolution"] and cid == create["cid"],
                "create_closure_unbound",
            )
        _need(
            receipt["container_status"] == "EXACT_CONTAINER_ABSENT_AFTER_JOIN",
            "container_closure_unknown",
        )
        visit["create"].update(resolution=resolution, cid=cid)
        for child in visit["children"]:
            child["status"] = "JOINED"
        visit.update(status="CLOSED", closure=digest(receipt))
        self.leg._save(value)

    def __exit__(self, *_):
        pass
