"""Sample Docker-side process cardinality for the active Dec4/9 CapsuleVisit."""

from __future__ import annotations

import math
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from threading import Thread
from typing import BinaryIO

from thericher_v2.execution.paper_peer_visit import digest
from thericher_v2.ops.h3_dec4_capsule import _json

_DOCKER = (
    "C:/Program Files/Docker/Docker/resources/bin/docker.exe",
    "--host",
    "npipe:////./pipe/dockerDesktopLinuxEngine",
)
_CONFIG_ROOT = "D:/thericher-v2/model-artifacts/execution/n9h3-control-r8/c1/controller"
_ENV = {
    "SystemRoot": "C:/Windows",
    "WINDIR": "C:/Windows",
    "PATH": "C:/Windows/System32;C:/Windows",
    "TEMP": _CONFIG_ROOT,
    "TMP": _CONFIG_ROOT,
    "DOCKER_CONFIG": f"{_CONFIG_ROOT}/empty-docker-config",
}
_FIELDS = {
    "id": ".Id",
    "name": ".Name",
    "image": ".Image",
    "visit": '(index .Config.Labels "thericher.single_owner.visit")',
    "source": '(index .Config.Labels "thericher.single_owner.source")',
    "pid_mode": ".HostConfig.PidMode",
    "init": '(index .HostConfig "Init")',
    "restart_policy": ".HostConfig.RestartPolicy",
    "restart_count": ".RestartCount",
    "state": ".State",
}
_FORMAT = "{" + ",".join(f'"{key}":{{{{json {expr}}}}}' for key, expr in _FIELDS.items()) + "}"
_LIVE = {
    "Status": "running",
    "Running": True,
    "Paused": False,
    "Restarting": False,
    "OOMKilled": False,
    "Dead": False,
    "ExitCode": 0,
    "Error": "",
    "FinishedAt": "0001-01-01T00:00:00Z",
}
_EPOCH = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(\.[0-9]{1,9})?Z")
_PID = re.compile(rb"[1-9][0-9]{0,9}")
_MAX_PID = 2**31 - 1
_MAX_REPLY = 4096
_MAX_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class Dec4DockerInventory:
    """A point sample, not kernel birth, a namespace inventory or admission.

    started_at is Docker's exact recorded container start epoch, not the
    daemon boot epoch or /proc start ticks. The PID is in the daemon's Linux
    PID view, not the Windows host or guest view.
    """

    cid: str
    daemon_pid: int
    started_at: str
    container_process_count: int


@dataclass(frozen=True, slots=True)
class _Ack:
    cid: str
    run: str
    image: str
    source: str
    spec_sha256: str


def _need(ok: bool, category: str) -> None:
    if not ok:
        raise ValueError("h3_docker_inventory_" + category)


def _hex(value: object, size: int) -> bool:
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{size}}}", value) is not None


def _ack(visit) -> _Ack:
    leg = visit.context.leg
    leg.check()
    record = leg.record
    rows = record.get("visits")
    identity = record.get("identity")
    cid, run, spec = visit.cid, visit.run, visit.spec
    _need(
        record.get("schema") == "paper-bank-leg-v1"
        and type(rows) is list
        and len(rows) == 1
        and type(rows[0]) is dict
        and type(identity) is dict
        and _hex(cid, 64)
        and _hex(run, 32)
        and type(spec) is dict
        and spec.get("kind") == "effect",
        "ack",
    )
    active = rows[0]
    source, image = identity.get("source"), spec.get("image")
    _need(
        _hex(source, 64)
        and type(image) is str
        and image.startswith("sha256:")
        and _hex(image[7:], 64),
        "ack",
    )
    try:
        spec_sha = digest(spec)
    except (TypeError, ValueError, RecursionError):
        raise ValueError("h3_docker_inventory_ack") from None
    _need(
        active.get("run") == run
        and active.get("kind") == "effect"
        and active.get("status") == "ACTIVE"
        and active.get("create") == dict(resolution="ACK_EXACT_CID", cid=cid, spec_sha256=spec_sha),
        "ack",
    )
    return _Ack(cid, run, image, source, spec_sha)


def _single_frame(raw: bytes) -> bool:
    return 1 < len(raw) <= _MAX_REPLY and raw.endswith(b"\n") and b"\r" not in raw


def _started_at(value: object) -> bool:
    match = _EPOCH.fullmatch(value) if type(value) is str else None
    if not match:
        return False
    try:
        return datetime.fromisoformat(match[1]).year >= 1970
    except ValueError:
        return False


def _inspect(raw: bytes, ack: _Ack) -> tuple[int, str]:
    _need(_single_frame(raw) and raw.count(b"\n") == 1, "inspect_frame")
    try:
        obj = _json(raw.decode("ascii"))
    except (ValueError, RecursionError):
        raise ValueError("h3_docker_inventory_inspect_frame") from None
    _need(type(obj) is dict and obj.keys() == _FIELDS.keys(), "inspect_shape")
    _need(
        obj["id"] == ack.cid
        and obj["name"] == "/thericher-single-owner-" + ack.run
        and obj["image"] == ack.image
        and obj["visit"] == ack.run
        and obj["source"] == ack.source,
        "inspect_identity",
    )
    policy = obj["restart_policy"]
    _need(obj["pid_mode"] == "" and obj["init"] is None, "pid_namespace")
    _need(
        type(obj["restart_count"]) is int
        and obj["restart_count"] == 0
        and type(policy) is dict
        and policy.keys() == {"Name", "MaximumRetryCount"}
        and policy["Name"] == "no"
        and type(policy["MaximumRetryCount"]) is int
        and policy["MaximumRetryCount"] == 0,
        "restart",
    )
    state = obj["state"]
    _need(
        type(state) is dict
        and state.keys() == _LIVE.keys() | {"Pid", "StartedAt"}
        and all(type(state[k]) is type(v) and state[k] == v for k, v in _LIVE.items())
        and type(state["Pid"]) is int
        and 1 < state["Pid"] <= _MAX_PID
        and _started_at(state["StartedAt"]),
        "inspect_state",
    )
    return state["Pid"], state["StartedAt"]


def _top(raw: bytes, daemon_pid: int) -> int:
    _need(_single_frame(raw), "top_frame")
    header, *rows = raw[:-1].split(b"\n")
    _need(header == b"PID" and bool(rows) and all(_PID.fullmatch(row) for row in rows), "top_shape")
    pids = tuple(int(row) for row in rows)
    _need(max(pids) <= _MAX_PID and len(set(pids)) == len(pids), "top_shape")
    _need(len(pids) == 1, "extra_process")
    _need(pids == (daemon_pid,), "top_pid_mismatch")
    return len(pids)


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    _need(left > 0, "timeout")
    return left


def _capture(pipe: BinaryIO, limit: int, result: list[bytes]) -> None:
    # Each reader owns its pipe; a deadline failure cannot block on its close.
    try:
        with pipe:
            raw = pipe.read(limit)
    except OSError:
        return
    result.append(raw)


def _docker(args: tuple[str, ...], deadline: float) -> bytes:
    _remaining(deadline)
    try:
        child = subprocess.Popen(
            (*_DOCKER, *args),
            cwd=_CONFIG_ROOT,
            env=_ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except OSError:
        raise ValueError("h3_docker_inventory_command") from None
    out: list[bytes] = []
    err: list[bytes] = []
    try:
        stdout = Thread(target=_capture, args=(child.stdout, _MAX_REPLY + 1, out), daemon=True)
        stderr = Thread(target=_capture, args=(child.stderr, 1, err), daemon=True)
        stdout.start()
        stderr.start()
        stdout.join(_remaining(deadline))
        stderr.join(_remaining(deadline))
        code = child.wait(timeout=_remaining(deadline))
        _remaining(deadline)
        _need(code == 0 and err == [b""] and len(out) == 1 and len(out[0]) <= _MAX_REPLY, "reply")
        return out[0]
    except subprocess.TimeoutExpired:
        raise ValueError("h3_docker_inventory_timeout") from None
    finally:
        if child.poll() is None:
            try:
                child.kill()
                child.wait(timeout=0.25)
            except (OSError, subprocess.TimeoutExpired):
                raise ValueError("h3_docker_inventory_cleanup") from None


def sample_dec4_docker_inventory(visit, *, deadline: float) -> Dec4DockerInventory:
    """Read only the BankLeg's ACK_EXACT_CID; deadline is absolute monotonic.

    Call within the guard's attach/owner checks and retain the epoch and PID
    for an independent exact guest join. This does not check other containers,
    prove continuous exclusivity, or replace original spec/mount validation.
    """
    _need(type(deadline) in (int, float) and -math.inf < deadline < math.inf, "deadline")
    cutoff = min(deadline, time.monotonic() + _MAX_SECONDS)
    _remaining(cutoff)
    ack = _ack(visit)
    inspect = ("container", "inspect", "--format", _FORMAT, ack.cid)
    before = _inspect(_docker(inspect, cutoff), ack)
    raw = _docker(("container", "top", ack.cid, "-o", "pid"), cutoff)
    after = _inspect(_docker(inspect, cutoff), ack)
    _need(before == after and _ack(visit) == ack, "changed")
    count = _top(raw, before[0])
    _remaining(cutoff)
    return Dec4DockerInventory(ack.cid, before[0], before[1], count)
