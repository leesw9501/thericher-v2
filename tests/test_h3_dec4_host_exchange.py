"""Exercise the host transport with an inert pipe child and exact fixture bytes."""

import subprocess
import sys
import time

import pytest

from test_h3_dec4_capsule import _outcome, _parse
from thericher_v2.ops.h3_dec4_host_exchange import exchange_dec4_guest

_CHILD = r"""
import json, sys, time
mode, final = sys.argv[1:]
reader, writer = sys.stdin.buffer, sys.stdout.buffer
assert reader.readline() == b'{"invented":true}\n'
if mode == "stall":
    time.sleep(30)
count = 2 if mode == "two" else 1
for n in range(1, count + 1):
    seq = n if mode != "out_of_order" else True
    writer.write(json.dumps(dict(kind="current20-owner-request-v1", sequence=seq)).encode()+b"\n")
    writer.flush()
    answer = json.loads(reader.readline())
    assert answer == dict(kind="current20-owner-answer-v1", sequence=n, ready=True)
writer.write(bytes.fromhex(final))
if mode == "trailing":
    writer.write(b"unexpected\n")
writer.flush()
assert reader.read() == b""
raise SystemExit(20 if mode == "fault" else 0)
"""


@pytest.mark.parametrize(
    ("mode", "denial", "expected"),
    [
        ("two", False, None),
        ("two", True, "h3_host_exchange_owner_denied"),
        ("out_of_order", False, "h3_host_exchange_sequence"),
        ("trailing", False, "h3_host_exchange_trailing_output"),
        ("fault", False, "h3_capsule_outcome_unconfirmed"),
        ("stall", False, "h3_host_exchange_deadline"),
    ],
)
def test_exact_duplex_with_native_pipes(mode, denial, expected):
    _, guest = _parse()
    retained = _outcome(guest)
    owner = []

    def admit(sequence):
        owner.append(sequence)
        return not denial

    child = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", _CHILD, mode, retained.hex()],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        options = dict(
            packet=b'{"invented":true}',
            guest=guest,
            admit=admit,
            read_retained=lambda: retained,
            deadline=time.monotonic() + (0.25 if mode == "stall" else 5),
        )
        if expected:
            with pytest.raises(ValueError, match=f"^{expected}$"):
                exchange_dec4_guest(child, **options)
        else:
            result = exchange_dec4_guest(child, **options)
            assert result == dict(
                pending=False,
                native_status="no_intent",
                financial_claim="UNKNOWN",
                reservation_release=False,
            )
            assert owner == [1, 2]
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()
