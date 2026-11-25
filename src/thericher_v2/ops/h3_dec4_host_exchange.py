"""One Dec4 guest exchange inside an already-owned Windows Job and capsule visit."""

import json
import math
import time
from functools import partial
from queue import Empty, Queue
from secrets import token_hex
from threading import Thread

from thericher_v2.ops.h3_dec4_capsule import _json, verify_dec4_capsule_outcome
from thericher_v2.ops.h3_dec4_guest_identity import (
    ANSWER,
    CHALLENGE,
    REQUEST,
    is_hex,
    parse_guest_process,
)

_LIMIT = 4096
_LOCAL_ACK_SECONDS = 12  # The guest's 13-second limit also covers transport.


def exchange_dec4_guest(
    process,
    *,
    load_packet,
    guest,
    guest_argv_sha256,
    admit,
    read_retained,
    deadline,
    monotonic=time.monotonic,
):
    """Use the attach child's exact terminal bytes; never create or settle a visit.

    The caller owns Job assignment, an independent hard stop for admission,
    abort/join after a fault, and exact daemon-side closure before releasing the
    lease. Its cleanup must kill the Job before closing a blocked pipe.
    """
    if (
        not callable(load_packet)
        or not is_hex(guest_argv_sha256, 64)
        or type(deadline) not in (int, float)
        or not math.isfinite(deadline)
    ):
        raise ValueError("h3_host_exchange_invalid")

    def remaining():
        left = deadline - monotonic()
        if left <= 0:
            raise ValueError("h3_host_exchange_deadline")
        return left

    def pipe(operation):
        # Windows anonymous pipes can block on write as well as read. Only
        # one operation can be pending when the enclosing visit needs to abort.
        result = Queue(maxsize=1)

        def run():
            try:
                result.put_nowait((True, operation()))
            except Exception:
                result.put_nowait((False, None))

        remaining()
        Thread(target=run, daemon=True).start()
        try:
            ok, value = result.get(timeout=remaining())
        except Empty:
            raise ValueError("h3_host_exchange_deadline") from None
        remaining()
        if not ok:
            raise ValueError("h3_host_exchange_pipe_failed")
        return value

    def send(data):
        if process.stdin.write(data) != len(data):
            raise ValueError("h3_host_exchange_short_write")
        process.stdin.flush()

    def receive():
        return process.stdout.readline(_LIMIT + 1)

    def frame(value):
        pipe(partial(send, json.dumps(value).encode("ascii") + b"\n"))

    challenge = token_hex(32)
    frame(dict(kind=CHALLENGE, challenge=challenge))
    sequence = 0
    initial = None
    while True:
        line = pipe(receive)
        if type(line) is not bytes or not 1 < len(line) <= _LIMIT or not line.endswith(b"\n"):
            raise ValueError("h3_host_exchange_frame")
        try:
            body = _json(line)
        except (ValueError, RecursionError):
            raise ValueError("h3_host_exchange_frame") from None
        if type(body) is not dict:
            raise ValueError("h3_host_exchange_frame")
        if body.get("kind") != REQUEST:
            break
        sequence += 1
        if (
            body.keys() != {"kind", "sequence", "challenge", "process"}
            or type(body["sequence"]) is not int
            or body["sequence"] != sequence
            or body["challenge"] != challenge
            or sequence > 512
        ):
            raise ValueError("h3_host_exchange_sequence")
        identity = parse_guest_process(body["process"])
        if identity.argv_sha256 != guest_argv_sha256 or initial not in (None, identity):
            raise ValueError("h3_host_exchange_guest_changed")
        initial = identity
        remaining()
        began = monotonic()
        try:
            owner_ready = admit(sequence, identity)
        except Exception:
            raise ValueError("h3_host_exchange_owner_denied") from None
        if owner_ready is not True:
            raise ValueError("h3_host_exchange_owner_denied")
        remaining()
        if not 0 <= monotonic() - began <= _LOCAL_ACK_SECONDS:
            raise ValueError("h3_host_exchange_owner_late")
        frame(dict(kind=ANSWER, sequence=sequence, challenge=challenge, ready=True))
        if sequence == 1:
            remaining()
            if not 0 <= monotonic() - began <= _LOCAL_ACK_SECONDS:
                raise ValueError("h3_host_exchange_owner_late")
            try:
                packet = load_packet()
            except Exception:
                raise ValueError("h3_host_exchange_packet_unavailable") from None
            if (
                type(packet) is not bytes
                or not 0 < len(packet) <= 8192
                or any(sep in packet for sep in (b"\n", b"\r"))
            ):
                raise ValueError("h3_host_exchange_packet_invalid")
            pipe(partial(send, packet + b"\n"))
            del packet

    if sequence < 2:
        raise ValueError("h3_host_exchange_owner_missing")
    pipe(process.stdin.close)
    if pipe(receive) != b"":
        raise ValueError("h3_host_exchange_trailing_output")
    try:
        exit_code = process.wait(timeout=remaining())
        remaining()
        retained = read_retained()
        remaining()
    except Exception:
        raise ValueError("h3_host_exchange_unconfirmed") from None
    return verify_dec4_capsule_outcome(line, retained, exit_code=exit_code, guest=guest)
