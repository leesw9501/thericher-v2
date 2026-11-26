"""Join the protected restore child handoff to the normal observer coordinator."""

from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path

from thericher_v2.execution.paper_peer_visit import _hash, _need
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.h3_dec4_observer_lease import Dec4ObserverLease
from thericher_v2.ops.h3_dec4_observer_restore import (
    read_dec4_restore_owner,
    restore_dec4_observer_once,
)
from thericher_v2.ops.h3_dec4_pair_release import phase_restore_pins
from thericher_v2.ops.h3_dec4_restore_daemon import Dec4RestoreDaemon
from thericher_v2.ops.h3_dec4_restore_process import wait_for_dec4_normal_root
from thericher_v2.ops.paper_scheduled_native import NativeScheduledSource
from thericher_v2.ops.paper_scheduled_preflight import ScheduledPaperPlan


@dataclass(frozen=True, slots=True, repr=False)
class Dec4RestoreChildBinding:
    source: NativeScheduledSource
    plan: ScheduledPaperPlan
    evidence_root: Path
    lease: Dec4ObserverLease
    daemon: Dec4RestoreDaemon
    hold_native_closure: Callable[[dict], AbstractContextManager[Callable[[], bool]]]
    retirement_ready: Callable[[], bool]


def run_dec4_restore_child(binding, argv, *, source_ready):
    """Arm only after the pinned startup handoff, then consume the exact root handle."""
    phase, source, release, handoff, root, arm, pid, birth, cutoff, mono = argv
    _need(type(binding) is Dec4RestoreChildBinding and callable(source_ready), "h3_restore_child")
    plan = binding.plan
    _need(
        type(plan) is ScheduledPaperPlan
        and phase in _TIMES
        and plan.phase == phase
        and plan.slot == ROUND
        and plan.task_name == TASKS[phase]
        and (plan.starts_at, plan.ends_at, plan.hard_stop) == _TIMES[phase]
        and plan.source_sha256 == source
        and plan.release_sha256 == release
        and all(_hash(pin) for pin in (source, release, handoff))
        and type(binding.lease) is Dec4ObserverLease
        and type(binding.daemon) is Dec4RestoreDaemon
        and callable(binding.hold_native_closure)
        and callable(binding.retirement_ready)
        and binding.evidence_root.is_absolute()
        and float(cutoff) == plan.hard_stop.timestamp()
        and source_ready() is True,
        "h3_restore_child_binding",
    )
    value = binding.source.check(source)
    grant = binding.source.release(value, source, release)
    selected = phase_restore_pins(value, phase)
    _need(
        value.get("synthetic_only", False) is False
        and selected["observer_plan_sha256"] == binding.lease.plan.sha256
        and selected["observer_restore_daemon_sha256"] == binding.daemon.sha256
        and getattr(binding.lease.transport, "bounded_normal_restore", False) is True
        and grant.get("source") == source
        and grant.get("allow_execute") is True
        and grant.get("actual_financial_admission") is False,
        "h3_restore_child_release",
    )
    pins = read_dec4_restore_owner(
        binding.evidence_root, plan=plan, observer_plan=binding.lease.plan, handoff_sha256=handoff
    )
    _need(
        pins.owner_pid == int(pid)
        and pins.owner_native_start == "win-filetime:" + birth
        and binding.retirement_ready() is True
        and source_ready() is True,
        "h3_restore_child_owner",
    )
    _need(
        wait_for_dec4_normal_root(
            root=int(root),
            arm=int(arm),
            pid=int(pid),
            birth=birth,
            cutoff=float(cutoff),
            monotonic_cutoff=float(mono),
        )
        is True,
        "h3_restore_child_root_not_closed",
    )

    @contextmanager
    def held(record):
        _need(source_ready() is True, "h3_restore_child_source_changed")
        with binding.hold_native_closure(record) as check:
            _need(callable(check), "h3_restore_child_exclusion")
            yield lambda: source_ready() is True and check() is True

    restore_dec4_observer_once(
        binding.lease,
        source=binding.source,
        pins=pins,
        hold_native_closure=held,
        daemon=binding.daemon,
    )
