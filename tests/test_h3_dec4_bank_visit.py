import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from test_h3_dec4_retained_input import POINT, _native
from thericher_v2.execution.paper_peer_visit import digest
from thericher_v2.ops.h3_dec4_bank_visit import ROUND, TASKS, run_dec4_owned_bank_visit
from thericher_v2.ops.h3_dec4_guest import parse_dec4_guest_visit
from thericher_v2.ops.h3_dec4_retained_input import (
    _entry_reference_path,
    retain_dec4_h3_input,
)
from thericher_v2.research.model_paper_weights import serialize_model_paper_weights_input

PIN = "a" * 64
RELEASE = "b" * 64
BANK = {"engine": "npipe:////./pipe/docker_engine", "volume": "invented-bank"}
BASIS = "sha256:" + "9" * 64


class Source:
    ROUND = ROUND
    SLOTS = {
        "entry": dict(
            name=TASKS["entry"],
            start_UTC="2026-12-04T14:31:00+00:00",
            end_UTC="2026-12-04T14:35:00+00:00",
            hard_UTC="2026-12-04T14:37:00+00:00",
        ),
        "exit": dict(
            name=TASKS["exit"],
            start_UTC="2026-12-09T14:30:00+00:00",
            end_UTC="2026-12-09T14:35:00+00:00",
            hard_UTC="2026-12-09T14:37:00+00:00",
        ),
    }

    def __init__(self, root):
        self.ROOT = root
        self.gate = root / "existing-gate"
        self.gate.mkdir()
        self.native = _native()
        self.payload = serialize_model_paper_weights_input(self.native)
        self.retained = retain_dec4_h3_input(
            root / "retained",
            self.payload,
            source_sha256=PIN,
            point_sha256=POINT,
            policy_ref=self.native.policy_ref,
            synthetic=True,
        )

    def check(self, pin):
        assert pin == PIN
        return dict(
            synthetic_only=True,
            original_owner=dict(bank=BANK),
            original_gate_root=str(self.gate),
            original_basis_ref=BASIS,
            execution_policy_ref=self.retained.policy_ref,
            retained_input_path=str(self.retained.path),
        )

    def release(self, value, pin, release_pin):
        assert pin == PIN and release_pin == RELEASE
        return dict(source=pin, allow_execute=True, actual_financial_admission=False)

    def action(self, pin, release_pin, phase):
        return f"invocation scoped to {pin} {release_pin} {phase}"

    def window(self, phase, at):
        row = self.SLOTS[phase]
        return tuple(datetime.fromisoformat(row[key]) for key in ("start_UTC", "end_UTC"))


class Owner:
    def __init__(self, source, pin, phase, release):
        self.expected = dict(
            dispatcher_source=pin,
            dispatcher_release=release,
            dispatcher_root=str(source.ROOT),
            task_name=TASKS[phase],
            task_action_sha256=hashlib.sha256(
                source.action(pin, release, phase).encode()
            ).hexdigest(),
            round_id=ROUND,
        )
        self.birth = "321"

    def prove(self):
        return self.expected | dict(
            schema="paper-stock-ingress-owner-v1",
            status="PASS_STOCK_INGRESS_SCHEDULED_OWNER",
            origin="ACTUAL_STOCK_INGRESS_TASK_SOURCE_ABI",
            no_old_model_self_rows=True,
            pid=os.getpid(),
            start_ticks=self.birth,
            argv_sha256="c" * 64,
        )


def no_effect(*_args):
    pytest.fail("outer coordinator passed an unauthorized effect boundary")


def capsule(leg, ready, frame, admit):
    value = _native()
    payload = serialize_model_paper_weights_input(value)
    guest = parse_dec4_guest_visit(
        frame,
        expected_phase=ready.plan.phase,
        expected_source_ref="sha256:" + PIN,
        expected_basis_ref=BASIS,
        expected_policy_ref=value.policy_ref,
        expected_payload_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert guest.cohort.slot.slot == ready.plan.slot
    if ready.plan.phase == "entry":
        assert guest.target_loader() == value
    else:
        assert frame.endswith(b"\n") and frame.count(b"\n") == 1
        with pytest.raises(ValueError, match="exit_requires_native_retained_input"):
            guest.target_loader()
    with leg.visit("f" * 32, kind="effect") as visit:
        visit.create_attempt("d" * 64)
        visit.create_ack("e" * 64)
        child = visit.spawn(
            [sys.executable, "-c", "import sys; sys.stdin.read(1)"], stdin=subprocess.PIPE
        )
        child.communicate(b"x", timeout=5)
        assert admit() is True
        visit.close(
            lambda record: dict(
                schema="paper-bank-visit-closure-v1",
                identity=record["identity"],
                owner=record["owner"],
                visit=visit.run,
                record_sha256=digest(record),
                children=[
                    {k: c[k] for k in ("token", "argv_sha256", "pid", "native_start")}
                    | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
                    for c in record["visits"][0]["children"]
                ],
                create_resolution="ACK_EXACT_CID",
                container="e" * 64,
                container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN",
                evidence_sha256="0" * 64,
            )
        )
    return dict(pending=True)


def run(tmp, source, **overrides):
    evidence = tmp / "evidence"
    evidence.mkdir(exist_ok=True)
    args = dict(
        source=source,
        pin=PIN,
        release_pin=RELEASE,
        phase="entry",
        make_owner=lambda p, s, r: Owner(source, p, s, r),
        writer_and_observer_ready=lambda *_: True,
        prepare_phase_input=lambda *_: source.retained,
        invoke_capsule_once=capsule,
        fixture_clock=lambda: datetime(2026, 12, 4, 14, 31, tzinfo=UTC),
    )
    return run_dec4_owned_bank_visit(evidence, **(args | overrides))


def test_positive_operational_close_never_releases_unknown_reservation(tmp_path):
    source = Source(tmp_path)
    result = run(tmp_path, source)
    assert result == dict(
        status="CLOSED_OPERATIONAL_FINANCIAL_PENDING",
        native_visits=1,
        financial_claim="UNKNOWN",
        reservation_release=False,
    )
    assert not list(source.gate.glob("*/ACTIVE-LEG.json"))
    assert len(list(source.gate.glob("*/CLOSED-*.json"))) == 1
    result = run(
        tmp_path,
        source,
        phase="exit",
        prepare_phase_input=no_effect,
        fixture_clock=lambda: datetime(2026, 12, 9, 14, 30, tzinfo=UTC),
    )
    assert result["status"] == "CLOSED_OPERATIONAL_FINANCIAL_PENDING"
    assert result["reservation_release"] is False
    assert len(list(source.gate.glob("*/CLOSED-*.json"))) == 2
    with pytest.raises(FileExistsError):
        run(
            tmp_path,
            source,
            phase="exit",
            prepare_phase_input=no_effect,
            invoke_capsule_once=no_effect,
            fixture_clock=lambda: datetime(2026, 12, 9, 14, 30, tzinfo=UTC),
        )


@pytest.mark.parametrize("fault", ("no_reference", "no_closure", "changed_ref", "changed_payload"))
def test_exit_cannot_use_unbound_or_tampered_original_input(tmp_path, fault):
    source = Source(tmp_path)
    run(tmp_path, source)
    link = _entry_reference_path(source.retained.path)
    (closure,) = source.gate.glob("*/CLOSED-*.json")
    if fault == "no_reference":
        link.unlink()
    elif fault == "no_closure":
        closure.unlink()
    elif fault == "changed_ref":
        link.write_bytes(link.read_bytes().replace(BASIS.encode(), b"sha256:" + b"8" * 64))
    else:
        source.retained.path.write_bytes(source.retained.path.read_bytes() + b"x")
    with pytest.raises(ValueError):
        run(
            tmp_path,
            source,
            phase="exit",
            prepare_phase_input=no_effect,
            invoke_capsule_once=no_effect,
            fixture_clock=lambda: datetime(2026, 12, 9, 14, 30, tzinfo=UTC),
        )
    assert not list(source.gate.glob("*/ACTIVE-LEG.json"))


def test_entry_reference_must_survive_prepare_before_first_effect(tmp_path):
    source = Source(tmp_path)
    link = _entry_reference_path(source.retained.path)

    def mutate(*_args):
        assert link.is_file()
        link.write_bytes(b"changed")
        return no_effect

    with pytest.raises(ValueError, match="h3_entry_reference_changed"):
        run(tmp_path, source, prepare_capsule_once=mutate, invoke_capsule_once=None)
    assert not list(source.gate.glob("*/ACTIVE-LEG.json"))


def test_exit_restarts_in_new_process_without_entry_callback(tmp_path):
    source = Source(tmp_path)
    run(tmp_path, source)
    child = """
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
from test_h3_dec4_bank_visit import Source, no_effect, run

root = Path(sys.argv[2])
restarted = Source.__new__(Source)
restarted.ROOT = root
restarted.gate = root / "existing-gate"
restarted.retained = SimpleNamespace(path=root / "retained", policy_ref=sys.argv[3])
outcome = run(
    root, restarted, phase="exit", prepare_phase_input=no_effect,
    fixture_clock=lambda: datetime(2026, 12, 9, 14, 30, tzinfo=UTC),
)
assert outcome["status"] == "CLOSED_OPERATIONAL_FINANCIAL_PENDING"
assert outcome["reservation_release"] is False
"""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            child,
            os.path.dirname(__file__),
            str(tmp_path),
            source.retained.policy_ref,
        ],
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(list(source.gate.glob("*/CLOSED-*.json"))) == 2


def test_local_guard_denial_does_not_strand_untouched_bank(tmp_path):
    source = Source(tmp_path)
    with pytest.raises(ValueError, match="writer_admission_denied"):
        run(
            tmp_path,
            source,
            writer_and_observer_ready=lambda *_: False,
            prepare_phase_input=no_effect,
            invoke_capsule_once=no_effect,
        )
    assert not list(source.gate.glob("*/ACTIVE-LEG.json"))


def test_unbound_capsule_result_cannot_close_old_bank_or_reopen_slot(tmp_path):
    source = Source(tmp_path)
    with pytest.raises(ValueError, match="positive_capsule_closure_required"):
        run(tmp_path, source, invoke_capsule_once=lambda *_: dict(pending=False))
    (active,) = source.gate.glob("*/ACTIVE-LEG.json")
    snapshot = active.read_bytes()
    result = run(
        tmp_path,
        source,
        phase="exit",
        prepare_phase_input=no_effect,
        fixture_clock=lambda: datetime(2026, 12, 9, 14, 30, tzinfo=UTC),
    )
    assert result["status"] == "DEFER_SHARED_BANK_HELD"
    assert active.read_bytes() == snapshot
    with pytest.raises(FileExistsError):
        run(tmp_path, source, invoke_capsule_once=no_effect)


def test_effect_admission_rejects_changed_owner_birth(tmp_path):
    source = Source(tmp_path)
    owner = Owner(source, PIN, "entry", RELEASE)

    def changed(_leg, _ready, _frame, admit):
        owner.birth = "111"
        admit()

    with pytest.raises(ValueError, match="owner_changed"):
        run(tmp_path, source, make_owner=lambda *_: owner, invoke_capsule_once=changed)
    assert list(source.gate.glob("*/ACTIVE-LEG.json"))
