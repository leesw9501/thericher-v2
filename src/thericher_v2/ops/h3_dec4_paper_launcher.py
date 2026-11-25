"""Compose the Dec4/9 Paper leg from the prebound owner, bank and capsule."""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_bank_visit import run_dec4_owned_bank_visit
from thericher_v2.ops.h3_dec4_capsule import inspect_dec4_capsule
from thericher_v2.ops.h3_dec4_capsule_adapter import run_dec4_capsule_visit
from thericher_v2.ops.h3_dec4_paper_input import Dec4BankPhaseInput
from thericher_v2.ops.h3_dec4_scheduler_provider import make_dec4_windows_owner_factory

_CAPSULE = {"image", "network", "mounts", "workspace", "account_ref", "worker_sha256"}
_GUEST_PATHS = {
    "state_root": "/app/private/canary",
    "repository_root": "/app",
    "artifact_root": "/app/model_artifacts",
    "runtime_projection_path": "/app/runtime/state/kis_paper_canary.json",
    "paper_account_snapshot_path": "/app/runtime/state/paper_account_snapshot.json",
    "emergency_state_path": "/app/emergency/emergency_state.json",
    "execution_control_path": "/app/emergency/paper_execution_control.json",
}
_TOKEN_ROOT = "/app/market_data/us_equities/kis_paper_private/collection-control-v1"
_PRIVATE_EXECUTION_ROOT = Path("D:/thericher-v2/model-artifacts/execution")


class _Context:
    def __init__(self, leg, bank, ready, guard, admit):
        self.leg = leg
        self.bank = bank
        self.owner = ready.owner
        self.readiness = ready
        self.source_pin = leg.identity["source"]
        self.created_starts = {}
        self.writer_guard = guard
        self.admission = admit


def _mounts(rows, bank):
    targets = set()
    accepted = []
    for row in rows:
        if (
            type(row) is not dict
            or row.keys() != {"type", "source", "target", "rw"}
            or row["type"] not in ("bind", "volume")
            or type(row["rw"]) is not bool
            or any(
                type(row[k]) is not str or not row[k] or any(c in row[k] for c in ",\r\n\0")
                for k in ("source", "target")
            )
        ):
            raise ValueError("dec4_launcher_mount")
        target = PurePosixPath(row["target"])
        if (
            not target.is_absolute()
            or ".." in target.parts
            or str(target) != row["target"]
            or target in targets
            or any(
                target.is_relative_to(root) or root.is_relative_to(target)
                for root in (PurePosixPath("/admission"), PurePosixPath("/out"))
            )
        ):
            raise ValueError("dec4_launcher_mount")
        if row["type"] == "volume":
            if row["source"] != bank["volume"]:
                raise ValueError("dec4_launcher_bank_volume")
        else:
            pv.ordinary(Path(row["source"]))
            if not Path(row["source"]).exists():
                raise ValueError("dec4_launcher_mount")
        targets.add(target)
        accepted.append(dict(row))
    if not any(m["type"] == "volume" and m["rw"] for m in accepted):
        raise ValueError("dec4_launcher_bank_volume")
    return accepted


def _prepare_capsule(leg, ready, retained, frame, admit, *, writer_guard, load_paper_packet, clock):
    pins = ready.source["capsule"]
    bank = dict(ready.source["original_owner"]["bank"])
    if (
        type(pins) is not dict
        or pins.keys() != _CAPSULE
        or type(pins["mounts"]) is not list
        or not pv._hash(pins["account_ref"])
        or not pv._hash(pins["worker_sha256"])
        or type(pins["image"]) is not str
        or not pins["image"].startswith("sha256:")
        or not pv._hash(pins["image"].removeprefix("sha256:"))
        or type(pins["network"]) is not str
        or pins["network"] in ("", "host", "default", "bridge")
        or any(c in pins["network"] for c in ",\r\n\0")
        or pins["network"].startswith("container:")
    ):
        raise ValueError("dec4_launcher_capsule_pins")
    if pv.bank_key(bank) != leg.key:
        raise ValueError("dec4_launcher_bank_volume")
    mounts = _mounts(pins["mounts"], bank)
    root = Path(pins["workspace"])
    pv.ordinary(root)
    if (
        not root.is_dir()
        or any(c in str(root) for c in ",\r\n")
        or (
            ready.source.get("synthetic_only") is not True
            and (
                root == _PRIVATE_EXECUTION_ROOT or not root.is_relative_to(_PRIVATE_EXECUTION_ROOT)
            )
        )
    ):
        raise ValueError("dec4_launcher_workspace")
    raw = pv.encode(
        {
            "schema": "dec4-net25-capsule-binding-v1",
            "phase": ready.plan.phase,
            "source_ref": "sha256:" + ready.plan.source_sha256,
            "basis_ref": ready.source["original_basis_ref"],
            "policy_ref": retained.policy_ref,
            "payload_sha256": retained.payload_sha256,
            "frame_sha256": hashlib.sha256(frame).hexdigest(),
            "worker_sha256": pins["worker_sha256"],
            "account_ref": pins["account_ref"],
            "paths": _GUEST_PATHS,
            "token_root": _TOKEN_ROOT,
        }
    )
    pin = hashlib.sha256(raw).hexdigest()
    _, guest = inspect_dec4_capsule(raw, frame, binding_sha256=pin)
    child = root / leg.identity["run"]
    child.mkdir(exist_ok=False)
    admission, out = child / "admission", child / "out"
    admission.mkdir(exist_ok=False)
    out.mkdir(exist_ok=False)
    frame_path, binding_path = admission / "NET25.frame", admission / "CAPSULE-BINDING.json"
    frame_seal = pv._new(frame_path, frame)
    binding_seal = pv._new(binding_path, raw)
    spec = {
        "kind": "effect",
        "phase": ready.plan.phase,
        "image": pins["image"],
        "network": pins["network"],
        "mounts": mounts
        + [
            {"type": "bind", "source": str(admission), "target": "/admission", "rw": False},
            {"type": "bind", "source": str(out), "target": "/out", "rw": True},
        ],
        "entrypoint": ["python"],
        "args": [
            "/app/scripts/run_h3_dec4_account_capsule.py",
            "--binding-sha256",
            pin,
            "--execute",
        ],
    }

    def checked_admit():
        if (
            admit() is not True
            or pv._read(frame_path) != frame_seal
            or pv._read(binding_path) != binding_seal
        ):
            raise ValueError("dec4_launcher_admission_changed")
        return True

    def read_outcome():
        return pv._read(out / "RAW-PRODUCER.json")[0]

    used = False

    def dispatch():
        nonlocal used
        if used:
            raise ValueError("dec4_launcher_already_dispatched")
        used = True
        checked_admit()
        pv.ordinary(out)
        if any(out.iterdir()):
            raise ValueError("dec4_launcher_output_not_empty")
        left = (ready.plan.ends_at - clock()).total_seconds()
        if left <= 0:
            raise ValueError("dec4_launcher_window")
        return run_dec4_capsule_visit(
            _Context(leg, bank, ready, writer_guard, checked_admit),
            spec,
            guest=guest,
            load_packet=load_paper_packet,
            read_retained=read_outcome,
            exchange_deadline=time.monotonic() + left,
        )

    return dispatch


def run_dec4_windows_paper_leg(
    evidence_root,
    *,
    source,
    pin,
    release_pin,
    phase,
    schedule_plan,
    scheduler_providers,
    phase_input,
    writer_and_observer_ready,
    writer_guard,
    load_paper_packet,
):
    """Run a named leg; the pinned host still supplies hard stop and native guards.

    Only the actual guest worker decides account admission, order identity,
    risk and reconciliation. Planning or reaching this route is not a fill.
    The outer caller owns the absolute watchdog and exact daemon recovery.
    """
    if (
        type(phase_input) is not Dec4BankPhaseInput
        or phase_input.fixture_now is not None
        or phase_input.run.synthetic
        or not callable(getattr(writer_guard, "check", None))
        or not all(callable(cb) for cb in (writer_and_observer_ready, load_paper_packet))
    ):
        raise ValueError("dec4_launcher_missing_owned_admission")
    make_owner = make_dec4_windows_owner_factory(schedule_plan, scheduler_providers)

    def prepare(leg, ready, retained, frame, admit):
        return _prepare_capsule(
            leg,
            ready,
            retained,
            frame,
            admit,
            writer_guard=writer_guard,
            load_paper_packet=load_paper_packet,
            clock=lambda: datetime.now(UTC),
        )

    return run_dec4_owned_bank_visit(
        evidence_root,
        source=source,
        pin=pin,
        release_pin=release_pin,
        phase=phase,
        make_owner=make_owner,
        writer_and_observer_ready=writer_and_observer_ready,
        prepare_phase_input=phase_input,
        prepare_capsule_once=prepare,
    )
