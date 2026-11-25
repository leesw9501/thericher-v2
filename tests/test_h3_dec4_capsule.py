"""Guest pins, admission order, and result projection on synthetic input."""

import hashlib
import io
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from test_h3_dec4_guest import _wire
from test_h3_dec4_retained_input import _native
from thericher_v2.execution import kis_paper_budget_strategy as budget
from thericher_v2.ops import h3_dec4_capsule as capsule
from thericher_v2.ops.h3_dec4_capsule import (
    inspect_dec4_capsule,
    run_dec4_account_capsule,
    verify_dec4_capsule_outcome,
)
from thericher_v2.ops.h3_dec4_guest_identity import CapsuleProcess

CONFIG = SimpleNamespace(
    base_url="https://example.invalid", account_number="synthetic", account_product_code="test"
)
_PROCESS = CapsuleProcess(namespace_pid=1, start_ticks=123, argv_sha256="b" * 64)
_NONCE = "c" * 64
_PACKET = b'{"app_key":"fake-key","app_secret":"fake-secret"}'


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _case(phase="entry", **overrides):
    frame, refs = _wire(_native(), phase)
    binding = {k.removeprefix("expected_"): v for k, v in refs.items()} | dict(
        schema="dec4-net25-capsule-binding-v1",
        account_ref=budget._digest(
            [CONFIG.base_url, CONFIG.account_number, CONFIG.account_product_code]
        ),
        frame_sha256=_digest(frame),
        worker_sha256="a" * 64,
        paths={"state_root": "/app/state"},
        token_root="/app/control",
    )
    raw = json.dumps(binding | overrides).encode()
    return raw, frame


def _parse(phase="entry", **overrides):
    raw, frame = _case(phase, **overrides)
    return inspect_dec4_capsule(raw, frame, binding_sha256=_digest(raw))


def _frame(**body):
    return json.dumps(body).encode("ascii") + b"\n"


_CHALLENGE = _frame(kind="dec4-owner-challenge-v2", challenge=_NONCE)


def _answer(sequence, ready=True, challenge=_NONCE):
    return _frame(kind="dec4-owner-answer-v2", sequence=sequence, challenge=challenge, ready=ready)


def _requests(sink):
    return [json.loads(raw) for raw in sink.getvalue().splitlines()]


def _request(sequence):
    return dict(
        kind="dec4-owner-request-v2", sequence=sequence, challenge=_NONCE, process=asdict(_PROCESS)
    )


@pytest.fixture
def guest_identity(monkeypatch):
    monkeypatch.setattr(capsule, "read_guest_process", lambda: _PROCESS)


def _forbidden(*args, **kwargs):
    pytest.fail("crossed an unadmitted boundary")


def test_independent_binding_and_frame_pins():
    raw, frame = _case()
    with pytest.raises(ValueError, match="^h3_capsule_binding_pin$"):
        inspect_dec4_capsule(raw + b" ", frame, binding_sha256=_digest(raw))
    with pytest.raises(ValueError, match="^h3_capsule_binding_invalid$"):
        inspect_dec4_capsule(raw, frame + b" ", binding_sha256=_digest(raw))


def test_outside_window_precedes_stdin():
    binding, guest = _parse()
    stream = SimpleNamespace(readline=_forbidden)
    with pytest.raises(ValueError, match="^h3_capsule_outside_window$"):
        run_dec4_account_capsule(
            binding,
            guest,
            stream=stream,
            sink=None,
            load_worker=_forbidden,
            clock=lambda: guest.cohort.slot.ends_at,
        )


@pytest.mark.parametrize(
    ("sequence", "answer", "error"),
    [
        (1, _answer(1, False), "denied"),
        (1, _answer(2), "denied"),
        (1, b"", "unknown"),
        (2, _answer(2, False), "denied"),
        (2, _answer(2, challenge="d" * 64), "denied"),
        (2, b"", "unknown"),
    ],
)
def test_owner_denial_precedes_worker_and_packet_parsing(guest_identity, sequence, answer, error):
    binding, guest = _parse()
    sink = io.BytesIO()
    prefix = _CHALLENGE if sequence == 1 else _CHALLENGE + _answer(1) + _PACKET + b"\n"
    remainder = _PACKET + b"\n" if sequence == 1 and answer else b""
    stream = io.BytesIO(prefix + answer + remainder)
    with pytest.raises(ValueError, match=f"^h3_capsule_owner_{error}$"):
        run_dec4_account_capsule(
            binding,
            guest,
            stream=stream,
            sink=sink,
            load_worker=_forbidden,
            clock=lambda: guest.cohort.slot.starts_at,
        )
    assert stream.tell() == len(prefix + answer)
    assert _requests(sink) == [_request(n) for n in range(1, sequence + 1)]


@pytest.mark.parametrize("phase", ["entry", "exit"])
def test_exact_session_with_duplex_and_no_private_result(guest_identity, phase):
    binding, guest = _parse(phase)
    invoked = []
    sink = io.BytesIO()
    admitted = _CHALLENGE + _answer(1) + _PACKET + b"\n" + _answer(2)
    stream = io.BytesIO(admitted + _answer(3))

    def parse_packet(raw):
        assert raw == _PACKET
        assert stream.tell() == len(admitted)
        assert _requests(sink) == [_request(1), _request(2)]
        invoked.append("parse")
        return CONFIG

    def session(config, **kwargs):
        assert config is CONFIG and kwargs["execute"] is True
        assert kwargs["cohort"] is guest.cohort
        assert kwargs["deadline"] == guest.cohort.slot.ends_at
        assert kwargs["source_ready"]() and kwargs["owner_ready"]()
        if phase == "entry":
            assert kwargs["target_loader"]() == _native()
        else:
            with pytest.raises(ValueError, match="retained_input"):
                kwargs["target_loader"]()
        invoked.append("session")
        return dict(
            pending=True, native_calls=1, native={"opaque": "private"}, calls={"ignored": 9}
        )

    def load(ref):
        assert ref == binding["worker_sha256"]
        assert stream.tell() == len(admitted)
        invoked.append("load")
        return dict(
            native_paths=lambda: {"state_root": PurePosixPath("/app/state")},
            CONTROL=PurePosixPath("/app/control"),
            parse_packet=parse_packet,
            run_account_session=session,
        )

    result = run_dec4_account_capsule(
        binding,
        guest,
        stream=stream,
        sink=sink,
        load_worker=load,
        clock=lambda: guest.cohort.slot.starts_at + timedelta(seconds=1),
    )
    assert invoked == ["load", "parse", "session"]
    assert _requests(sink) == [_request(1), _request(2), _request(3)]
    assert _PACKET not in sink.getvalue()
    assert result["status"] == "pending"
    assert result["financial_claim"] == "UNKNOWN" and result["reservation_release"] is False
    assert "native" not in result and "calls" not in result and "private" not in str(result)


def _outcome(guest, **overrides):
    slot = guest.cohort.slot
    value = dict(
        schema="dec4-net25-capsule-outcome-v1",
        status="no_intent",
        pending=None,
        phase=slot.phase,
        input_ref=slot.input_ref,
        policy_ref=slot.policy_ref,
        source_ref=guest.cohort.source_ref,
        native_calls=1,
        financial_claim="UNKNOWN",
        reservation_release=False,
    )
    return json.dumps(value | overrides).encode() + b"\n"


@pytest.mark.parametrize("status,pending", [("no_intent", None), ("pending", True)])
def test_host_capsule_result_contract(status, pending):
    _, guest = _parse()
    raw = _outcome(guest, status=status, pending=pending)
    assert verify_dec4_capsule_outcome(raw, raw, exit_code=0, guest=guest) == dict(
        pending=pending is True,
        native_status=status,
        financial_claim="UNKNOWN",
        reservation_release=False,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"phase": "exit"},
        {"input_ref": "sha256:" + "0" * 64},
        {"status": "unavailable"},
        {"status": "pending"},
        {"pending": False},
        {"native_calls": True},
        {"reservation_release": 0},
        {"extra": "unrecognized"},
    ],
)
def test_host_capsule_result_rejects_malformed_response(overrides):
    _, guest = _parse()
    raw = _outcome(guest, **overrides)
    with pytest.raises(ValueError, match="^h3_capsule_outcome_unconfirmed$"):
        verify_dec4_capsule_outcome(raw, raw, exit_code=0, guest=guest)


def test_host_capsule_result_requires_exact_members_and_confirmed_exit():
    _, guest = _parse()
    raw = _outcome(guest)
    duplicate = b'{"status":"no_intent",' + raw[1:]
    for stdout, retained, rc in (
        (raw, raw[:-1], 0),
        (raw, raw, 20),
        (raw, raw, False),
        (duplicate, duplicate, 0),
    ):
        with pytest.raises(ValueError, match="^h3_capsule_outcome_unconfirmed$"):
            verify_dec4_capsule_outcome(stdout, retained, exit_code=rc, guest=guest)
