"""Restore the snapshot observer after the independent Dec4/9 Paper owner closes."""

import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.h3_dec4_crash_recovery import _terminated
from thericher_v2.ops.h3_dec4_job_closure import read_dec4_normal_job_close
from thericher_v2.ops.h3_dec4_native_host import _ticks
from thericher_v2.ops.h3_dec4_observer_lease import Dec4ObserverLease
from thericher_v2.ops.h3_dec4_observer_transport import Dec4NativeObserverTransport
from thericher_v2.ops.h3_dec4_pair_release import phase_restore_pins
from thericher_v2.ops.h3_dec4_restore_daemon import Dec4RestoreDaemon
from thericher_v2.ops.paper_scheduled_native import NativeScheduledSource


@dataclass(frozen=True, slots=True, repr=False)
class Dec4ObserverRestorePins:
    """Prebound launch pins and independently retained original run/owner identity."""

    source_sha256: str
    release_sha256: str
    observer_plan_sha256: str
    gate_root: Path
    bank_key: str
    run: str
    argv_sha256: str
    owner_pid: int
    owner_native_start: str


def retain_dec4_restore_owner(evidence_root, *, ready, leg, observer_plan):
    """Publish a separate startup-custody handoff before any observer switch."""
    plan = ready.plan
    slot = Path(evidence_root) / f"{plan.opportunity}-{plan.phase}"
    claim_path = slot / "CLAIM.json"
    claim = pv._read(claim_path)
    marker = pv._decode(claim[0])
    diagnostic = marker["diagnostic"]
    prefix = f"diagnostic-{plan.opportunity}-{plan.phase}-"
    pv._need(
        set(marker) == {"diagnostic", "attempt_sha256"}
        and diagnostic.startswith(prefix)
        and pv._run(diagnostic.removeprefix(prefix))
        and pv._hash(marker["attempt_sha256"]),
        "h3_observer_restore_startup_claim",
    )
    attempt = Path(evidence_root) / diagnostic / "ATTEMPT.json"
    terminal = attempt.with_name("STARTUP.json")
    started, qualified = pv._read(attempt), pv._read(terminal)
    start, done = pv._decode(started[0]), pv._decode(qualified[0])
    source = ready.source
    bank = dict(source["original_owner"]["bank"])
    leg.check()
    owner = ready.owner.prove()
    birth = "win-filetime:" + owner["start_ticks"]
    pv._need(
        pv.digest(start) == marker["attempt_sha256"] == done["attempt_sha256"]
        and start["source"] == plan.source_sha256
        and start["phase"] == plan.phase
        and start["opportunity"] == plan.opportunity
        and done["status"] == "ready"
        and done["category"] is None
        and plan.phase == observer_plan.phase
        and phase_restore_pins(source, plan.phase)["observer_plan_sha256"] == observer_plan.sha256
        and leg.key == pv.bank_key(bank)
        and leg.root.parent == Path(source["original_gate_root"])
        and leg.identity["source"] == plan.source_sha256
        and leg.identity["release"] == plan.release_sha256
        and leg.identity["argv_sha256"] == owner["argv_sha256"]
        and leg.record["owner"] == {"pid": owner["pid"], "native_start": birth}
        and not leg.record["visits"],
        "h3_observer_restore_startup_binding",
    )
    pins = Dec4ObserverRestorePins(
        plan.source_sha256,
        plan.release_sha256,
        observer_plan.sha256,
        leg.root.parent,
        leg.key,
        leg.identity["run"],
        leg.identity["argv_sha256"],
        owner["pid"],
        birth,
    )
    row = dict(
        schema="h3-dec4-observer-restore-owner-v1",
        phase=plan.phase,
        startup_claim_sha256=pv.digest(marker),
        startup_ready_sha256=pv.digest(done),
        source_sha256=pins.source_sha256,
        release_sha256=pins.release_sha256,
        observer_plan_sha256=pins.observer_plan_sha256,
        gate_root=str(pins.gate_root),
        bank_key=pins.bank_key,
        run=pins.run,
        argv_sha256=pins.argv_sha256,
        owner_pid=pins.owner_pid,
        owner_native_start=pins.owner_native_start,
        financial_admission=False,
    )
    leg.check()
    pv._need(
        (pv._read(claim_path), pv._read(attempt), pv._read(terminal))
        == (claim, started, qualified),
        "h3_observer_restore_startup_changed",
    )
    pv._new(slot / "RESTORE-OWNER.json", pv.encode(row))
    return pv.digest(row)


def read_dec4_restore_owner(evidence_root, *, plan, observer_plan, handoff_sha256):
    """Read only the protected startup handoff whose digest the restore owner retained."""
    slot = Path(evidence_root) / f"{plan.opportunity}-{plan.phase}"
    path = slot / "RESTORE-OWNER.json"
    snapshot = pv._read(path)
    row = pv._decode(snapshot[0])
    pv._need(
        pv.digest(row) == handoff_sha256
        and row["schema"] == "h3-dec4-observer-restore-owner-v1"
        and row["phase"] == plan.phase == observer_plan.phase
        and row["financial_admission"] is False
        and row["source_sha256"] == plan.source_sha256
        and row["release_sha256"] == plan.release_sha256
        and row["observer_plan_sha256"] == observer_plan.sha256
        and pv.digest(pv._decode(pv._read(slot / "CLAIM.json")[0])) == row["startup_claim_sha256"]
        and pv._read(path) == snapshot,
        "h3_observer_restore_handoff_changed",
    )
    return Dec4ObserverRestorePins(
        plan.source_sha256,
        plan.release_sha256,
        observer_plan.sha256,
        Path(row["gate_root"]),
        row["bank_key"],
        row["run"],
        row["argv_sha256"],
        row["owner_pid"],
        row["owner_native_start"],
    )


def _absent(path, reason):
    pv.ordinary(path)
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise pv.Held(reason)


def restore_dec4_observer_once(
    lease: Dec4ObserverLease,
    *,
    source: NativeScheduledSource,
    pins: Dec4ObserverRestorePins,
    hold_native_closure: Callable[[dict], AbstractContextManager[Callable[[], bool]]],
    daemon: Dec4RestoreDaemon | None = None,
    fixture_clock: Callable[[], datetime] | None = None,
) -> None:
    """Re-enable only the exact observer disabled by a normally closed Paper leg.

    The independent caller supplies pins from protected launch/owner custody,
    not from STARTED or CLOSED. Its bounded, source-qualified native guard
    must hold relevant-writer exclusion until context exit and freshly prove
    original owner/Job/descendant and exact daemon/container closure at every
    check. A census alone is not exclusion. The guard must not take the bank
    Gate itself, which the existing lease takes around the switch. The exact
    daemon probe runs only in that existing locked mutation path.

    No waiting, retries, abort repair, task start, or financial state changes.
    Once the lease writes RESTORE_STARTED, a failed result is unknown.
    """
    pv._need(
        type(lease) is Dec4ObserverLease
        and type(pins) is Dec4ObserverRestorePins
        and callable(hold_native_closure)
        and all(
            pv._hash(pin)
            for pin in (
                pins.source_sha256,
                pins.release_sha256,
                pins.observer_plan_sha256,
                pins.bank_key,
                pins.argv_sha256,
            )
        )
        and pv._run(pins.run)
        and isinstance(pins.gate_root, Path)
        and pins.gate_root.is_absolute()
        and type(pins.owner_pid) is int
        and pins.owner_pid > 0
        and pv._start(pins.owner_native_start)
        and pins.owner_native_start.startswith("win-filetime:")
        and lease.plan.sha256 == pins.observer_plan_sha256
        and lease.root == Path(lease.plan.output_root)
        and (
            (
                fixture_clock is not None
                and callable(fixture_clock)
                and daemon is None
                and type(lease.transport) is not Dec4NativeObserverTransport
            )
            or (
                fixture_clock is None
                and os.name == "nt"
                and type(daemon) is Dec4RestoreDaemon
                and type(lease.transport) is Dec4NativeObserverTransport
                and lease.transport.plan == lease.plan
                and lease.transport.bounded_normal_restore
            )
        ),
        "h3_observer_restore_scope",
    )
    phase = lease.plan.phase
    opens, closes, hard = _TIMES[phase]
    clock = fixture_clock or (lambda: datetime.now(UTC))
    deadline = hard + timedelta(seconds=30) if daemon is not None else None
    pv._need(deadline is None or clock() < deadline, "h3_observer_restore_deadline")
    identity = dict(
        source=pins.source_sha256,
        release=pins.release_sha256,
        group=pins.source_sha256,
        member="stock-ingress",
        run=pins.run,
        argv_sha256=pins.argv_sha256,
        bank=pins.bank_key,
    )
    owner = {"pid": pins.owner_pid, "native_start": pins.owner_native_start}

    def check_source():
        try:
            row = source.SLOTS[phase]
            value = source.check(pins.source_sha256)
            release = source.release(value, pins.source_sha256, pins.release_sha256)
            selected = phase_restore_pins(value, phase)
            bank = dict(value["original_owner"]["bank"])
            existing_gate = value.get("original_gate_identity") if daemon is not None else None
            valid = (
                source.ROOT.is_absolute()
                and source.ROUND == ROUND
                and row["name"] == TASKS[phase]
                and tuple(
                    datetime.fromisoformat(row[k]) for k in ("start_UTC", "end_UTC", "hard_UTC")
                )
                == (opens, closes, hard)
                and value.get("synthetic_only", False) is (fixture_clock is not None)
                and selected["observer_plan_sha256"] == pins.observer_plan_sha256
                and (daemon is None or selected["observer_restore_daemon_sha256"] == daemon.sha256)
                and Path(value["original_gate_root"]) == pins.gate_root
                and pv.bank_key(bank) == pins.bank_key
                and (daemon is None or pv._hash(existing_gate))
                and release.get("source") == pins.source_sha256
                and release.get("allow_execute") is True
                and release.get("actual_financial_admission") is False
            )
        except Exception:
            raise pv.Denied("h3_observer_restore_source_or_release") from None
        pv._need(valid, "h3_observer_restore_source_or_release")
        return bank, existing_gate

    bank, existing_gate = check_source()
    root = pins.gate_root / ("bank-" + pins.bank_key)
    active = root / "ACTIVE-LEG.json"
    closed = root / ("CLOSED-" + pins.run + ".json")
    started = lease.root / "STARTED.json"
    disabled = lease.root / "DISABLED.json"
    restored = lease.root / "RESTORED.json"
    pending = lease.root / "RESTORE_STARTED.json"
    recovery = (
        root / ("PHYSICAL-CLOSED-" + pins.run + ".json"),
        root / ("NATIVE-RECONCILED-" + pins.run + ".json"),
    )

    def check_markers():
        _absent(active, "h3_observer_restore_bank_active")
        _absent(restored, "h3_observer_restore_stale_marker")
        for marker in recovery:
            _absent(marker, "h3_observer_restore_abnormal_marker")

    check_markers()
    _absent(pending, "h3_observer_restore_stale_marker")
    snapshots = tuple(pv._read(path) for path in (closed, started, disabled))
    receipt, start = (pv._decode(snapshot[0]) for snapshot in snapshots[:2])
    pv._need(
        type(receipt) is dict
        and set(receipt)
        == {
            "status",
            "record",
            "same_native_intent_reconciliation_required",
            "reservation_or_budget_release",
        }
        and receipt["status"] == "CLOSED_OPERATIONAL_ONLY"
        and receipt["same_native_intent_reconciliation_required"] is True
        and receipt["reservation_or_budget_release"] is False,
        "h3_observer_restore_not_normal_closure",
    )
    record = receipt["record"]
    pv._record(record, pins.bank_key)
    pv._need(
        type(start) is dict
        and set(start) == {"schema", "plan", "identity", "owner", "at", "before"}
        and start["schema"] == "h3-dec4-observer-disable-v1"
        and start["plan"] == pins.observer_plan_sha256
        and pv._same(start["identity"], identity)
        and pv._same(start["owner"], owner)
        and record["identity"] == identity
        and record["owner"] == owner,
        "h3_observer_restore_original_mismatch",
    )
    at = datetime.fromisoformat(start["at"])
    pv._need(
        at.utcoffset() == timedelta(0)
        and opens <= at < closes
        and _ticks(opens) <= int(pins.owner_native_start.split(":")[1]) <= _ticks(at),
        "h3_observer_restore_stale_start",
    )
    visits = record["visits"]
    pv._need(
        len(visits) <= 1
        and all(
            visit["kind"] == "effect"
            and visit["status"] == "CLOSED"
            and visit["children"]
            and visit["create"]["resolution"] in {"ACK_EXACT_CID", "DISCOVERED_EXACT_SCOPE"}
            for visit in visits
        ),
        "h3_observer_restore_not_normal_closure",
    )

    job_close = read_dec4_normal_job_close(root, record) if daemon is not None and visits else None
    completed = False
    with hold_native_closure(deepcopy(record)) as check_native:
        pv._need(callable(check_native), "h3_observer_restore_native_unknown")

        def native_closed(current):
            pv._need(clock() >= at, "h3_observer_restore_stale_start")
            pv._need(deadline is None or clock() < deadline, "h3_observer_restore_deadline")
            pv._need(
                pv._same(current, record) and check_source() == (bank, existing_gate),
                "h3_observer_restore_original_mismatch",
            )
            for actor in (owner, *(child for visit in visits for child in visit["children"])):
                _terminated(pv.process_start, actor)
            pv._need(check_native() is True, "h3_observer_restore_native_unknown")
            if daemon is not None:
                if job_close is not None:
                    pv._need(
                        read_dec4_normal_job_close(root, current) == job_close,
                        "h3_observer_restore_job_closure_changed",
                    )
                pv._need(
                    daemon.check(bank=bank, record=current) is True,
                    "h3_observer_restore_daemon_unknown",
                )
            check_markers()
            pv._need(
                tuple(pv._read(path) for path in (closed, started, disabled)) == snapshots,
                "h3_observer_restore_evidence_changed",
            )
            return True

        _absent(pending, "h3_observer_restore_stale_marker")
        lease.restore_closed(
            pins.gate_root,
            bank=bank,
            identity=identity,
            native_closed=native_closed,
            clock=clock,
            existing_gate=existing_gate,
        )
        completed = True
    pv._need(completed, "h3_observer_restore_result_unknown")
