"""One Dec4 guest exchange inside an already-owned Windows Job and capsule visit."""

import json
import math
import time
from functools import partial
from queue import Empty, Queue
from threading import Thread

from thericher_v2.ops.h3_dec4_capsule import _json, verify_dec4_capsule_outcome

_LIMIT = 4096
_ACK = "current20-owner-answer-v1"
_REQUEST = "current20-owner-request-v1"


def exchange_dec4_guest(
    process, *, packet, guest, admit, read_retained, deadline, monotonic=time.monotonic
):
    """Use the attach child's exact terminal bytes; never create or settle a visit.

    The caller owns Job assignment, an independent hard stop for admission,
    abort/join after a fault, and exact daemon-side closure before releasing the
    lease. Its cleanup must kill the Job before closing a blocked pipe.
    """
    if (
        type(packet) is not bytes
        or not 0 < len(packet) <= 8192
        or any(separator in packet for separator in (b"\n", b"\r"))
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

    pipe(partial(send, packet + b"\n"))
    sequence = 0
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
        if body.get("kind") != _REQUEST:
            break
        sequence += 1
        if (
            body.keys() != {"kind", "sequence"}
            or type(body["sequence"]) is not int
            or body["sequence"] != sequence
            or sequence > 512
        ):
            raise ValueError("h3_host_exchange_sequence")
        remaining()
        try:
            owner_ready = admit(sequence)
        except Exception:
            raise ValueError("h3_host_exchange_owner_denied") from None
        if owner_ready is not True:
            raise ValueError("h3_host_exchange_owner_denied")
        remaining()
        ack = json.dumps(dict(kind=_ACK, sequence=sequence, ready=True)).encode("ascii")
        pipe(partial(send, ack + b"\n"))

    if sequence == 0:
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
