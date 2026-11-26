"""Exercise the host transport with an inert pipe child and exact fixture bytes."""

import hashlib
import io
import json
import subprocess
import sys
import time
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_h3_dec4_capsule import _PACKET, _PROCESS, _outcome, _parse
from thericher_v2.ops import h3_dec4_host_exchange
from thericher_v2.ops.h3_dec4_guest_identity import REQUEST
from thericher_v2.ops.h3_dec4_host_exchange import exchange_dec4_guest

_CHILD = r"""
import json, sys, time
mode, final, process, packet = sys.argv[1:]
process = json.loads(process)
reader, writer = sys.stdin.buffer, sys.stdout.buffer
init = json.loads(reader.readline())
assert set(init) == {"kind", "challenge"} and init["kind"] == "dec4-owner-challenge-v2"
challenge = init["challenge"]
assert len(challenge) == 64 and bytes.fromhex(challenge).hex() == challenge
if mode == "stall":
    time.sleep(30)
count = 1 if mode == "one" else 3
for n in range(1, count + 1):
    seq = n if mode != "out_of_order" else True
    nonce = challenge[:-1] + ("0" if challenge[-1] != "0" else "1")
    request = dict(kind="dec4-owner-request-v2", sequence=seq,
                   challenge=nonce if n == 2 and mode == "nonce" else challenge,
                   process=process)
    if n == 2 and mode == "birth":
        request["process"] = dict(process, start_ticks=process["start_ticks"] + 1)
    writer.write(json.dumps(request).encode() + b"\n")
    writer.flush()
    answer = json.loads(reader.readline())
    assert answer == dict(kind="dec4-owner-answer-v2", sequence=n, challenge=challenge, ready=True)
    if n == 1:
        assert reader.readline() == bytes.fromhex(packet) + b"\n"
writer.write(bytes.fromhex(final))
if mode == "trailing":
    writer.write(b"unexpected\n")
writer.flush()
assert reader.read() == b""
raise SystemExit(20 if mode == "fault" else 0)
"""


@pytest.mark.parametrize(
    ("mode", "deny_sequence", "expected", "admissions"),
    [
        ("three", None, None, [1, 2, 3]),
        ("three", 1, "h3_host_exchange_owner_denied", [1]),
        ("three", 2, "h3_host_exchange_owner_denied", [1, 2]),
        ("one", None, "h3_host_exchange_owner_missing", [1]),
        ("nonce", None, "h3_host_exchange_sequence", [1]),
        ("birth", None, "h3_host_exchange_guest_changed", [1]),
        ("out_of_order", None, "h3_host_exchange_sequence", []),
        ("trailing", None, "h3_host_exchange_trailing_output", [1, 2, 3]),
        ("fault", None, "h3_capsule_outcome_unconfirmed", [1, 2, 3]),
        ("stall", None, "h3_host_exchange_deadline", []),
    ],
)
def test_exact_duplex_with_native_pipes(mode, deny_sequence, expected, admissions):
    _, guest = _parse()
    retained = _outcome(guest)
    owner = []

    def admit(sequence, process):
        assert process == _PROCESS
        owner.append(sequence)
        return sequence != deny_sequence

    child = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _CHILD,
            mode,
            retained.hex(),
            json.dumps(asdict(_PROCESS)),
            _PACKET.hex(),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stdin = child.stdin
    child.stdin = Mock(wraps=stdin)

    def supply_packet():
        assert owner == [1]
        challenge, answer = [json.loads(call.args[0]) for call in child.stdin.write.call_args_list]
        assert answer == dict(
            kind="dec4-owner-answer-v2", sequence=1, challenge=challenge["challenge"], ready=True
        )
        assert child.stdin.flush.call_count == 2
        return _PACKET

    load_packet = Mock(side_effect=supply_packet)
    try:
        options = dict(
            load_packet=load_packet,
            guest=guest,
            guest_argv_sha256=_PROCESS.argv_sha256,
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
                accepted_stdout={"sha256": hashlib.sha256(retained).hexdigest(), "exit_code": 0},
            )
        assert owner == admissions
        sent = [call.args[0] for call in child.stdin.write.call_args_list]
        if not admissions or deny_sequence == 1:
            load_packet.assert_not_called()
            assert len(sent) == 1
        else:
            load_packet.assert_called_once_with()
            assert sent.count(_PACKET + b"\n") == 1
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        stdin.close()
        child.stdout.close()


def test_late_positive_first_admission_does_not_load_credentials(monkeypatch):
    _, guest = _parse()
    challenge = "7" * 64
    monkeypatch.setattr(h3_dec4_host_exchange, "token_hex", lambda _: challenge)
    request = dict(kind=REQUEST, sequence=1, challenge=challenge, process=asdict(_PROCESS))
    proc = SimpleNamespace(
        stdin=io.BytesIO(), stdout=io.BytesIO(json.dumps(request).encode() + b"\n")
    )
    clock = [0.0]

    def admit(*_args):
        clock[0] = 14.0
        return True

    def never():
        pytest.fail("after a late first admission, the credential loader must not run")

    with pytest.raises(ValueError, match="^h3_host_exchange_owner_late$"):
        exchange_dec4_guest(
            proc,
            load_packet=never,
            guest=guest,
            guest_argv_sha256=_PROCESS.argv_sha256,
            admit=admit,
            read_retained=never,
            deadline=60.0,
            monotonic=lambda: clock[0],
        )
    assert _PACKET not in proc.stdin.getvalue()
