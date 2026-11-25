"""Dec4 owner protocol: stream binding, not attestation against a hostile daemon."""

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

CHALLENGE = "dec4-owner-challenge-v2"
REQUEST = "dec4-owner-request-v2"
ANSWER = "dec4-owner-answer-v2"


def is_hex(value, size):
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{size}}}", value) is not None


@dataclass(frozen=True, slots=True)
class CapsuleProcess:
    namespace_pid: int
    start_ticks: int
    argv_sha256: str


def parse_guest_process(row):
    if (
        type(row) is not dict
        or row.keys() != {"namespace_pid", "start_ticks", "argv_sha256"}
        or type(row["namespace_pid"]) is not int
        or row["namespace_pid"] != 1
        or type(row["start_ticks"]) is not int
        or not 0 < row["start_ticks"] < 2**63
        or not is_hex(row["argv_sha256"], 64)
    ):
        raise ValueError("h3_guest_identity_unknown")
    return CapsuleProcess(**row)


def linux_argv_sha256(argv):
    if not argv or any(type(x) is not str or not x or "\0" in x for x in argv):
        raise ValueError("h3_guest_argv_invalid")
    return hashlib.sha256(("\0".join(argv) + "\0").encode("utf-8")).hexdigest()


def _read(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise ValueError("h3_guest_identity_unknown")
    return raw


def read_guest_process():
    if os.getpid() != 1:
        raise ValueError("h3_guest_identity_unknown")
    stat = _read("/proc/self/stat", 4096)
    command = _read("/proc/self/cmdline", 8192)
    prefix, sep, suffix = stat.rpartition(b") ")
    fields = suffix.split()
    if not sep or not prefix.startswith(b"1 (") or len(fields) <= 19 or not command.endswith(b"\0"):
        raise ValueError("h3_guest_identity_unknown")
    return parse_guest_process(
        dict(
            namespace_pid=1,
            start_ticks=int(fields[19]),
            argv_sha256=hashlib.sha256(command).hexdigest(),
        )
    )
