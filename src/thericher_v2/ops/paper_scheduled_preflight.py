"""Preflight boundary for a finite scheduled native Paper phase."""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generic, TypeVar

from thericher_v2.ops.paper_startup import Phase, run_startup

Source = TypeVar("Source")
Release = TypeVar("Release")
Owner = TypeVar("Owner")


@dataclass(frozen=True)
class ScheduledPaperPlan:
    """One phase projected from the caller's frozen source and Task Definition.

    The slot is the fixed round identity shared by entry and exit.
    """

    slot: str
    phase: Phase
    task_name: str
    action_sha256: str
    source_sha256: str
    release_sha256: str
    starts_at: datetime
    ends_at: datetime
    hard_stop: datetime

    @property
    def opportunity(self) -> str:
        # Source revisions and launch UUIDs never reopen a phase of the same slot.
        key = f"paper-scheduled-slot-v1:{self.slot.lower()}"
        return hashlib.sha256(key.encode("ascii")).hexdigest()[:32]


@dataclass(frozen=True)
class ScheduledPaperPreflight(Generic[Source, Release, Owner]):
    """No-order preflight result; neither financial admission nor a submit permit."""

    plan: ScheduledPaperPlan
    source: Source
    release: Release
    owner: Owner
    checked_at: datetime


def _utc(value: datetime) -> bool:
    return type(value) is datetime and value.utcoffset() == timedelta(0)


def _not_denied(result: object) -> None:
    if result is False:
        raise ValueError("Scheduled Paper preflight check denied")


def run_scheduled_preflight(
    root: Path,
    *,
    plan: ScheduledPaperPlan,
    source_sha256: str,
    release_sha256: str,
    phase: Phase,
    clock: Callable[[], datetime],
    check_source: Callable[[ScheduledPaperPlan], Source],
    check_release: Callable[[ScheduledPaperPlan, Source], Release],
    check_window: Callable[[ScheduledPaperPlan, datetime], object],
    check_owner: Callable[[ScheduledPaperPlan, Source], Owner],
) -> ScheduledPaperPreflight[Source, Release, Owner]:
    """Record one no-order attempt, then return checked objects to the native caller.

    Use an existing, absolute, owned evidence root and a phase plan projected
    from pinned source, not assembled from launch arguments. The source, release,
    window and owner callbacks must raise on denial (literal False also denies).
    They may verify, but must not reconcile custody, load credentials or submit.
    The owner check must prove the actual owner for the plan, including its task,
    action, slot, source and release. This adapter does not grant source authority.

    R8 successor coordinator example, after binding the parent/child launch:

        def prove_release(plan, value):
            release = source.release(value, plan.source_sha256, plan.release_sha256)
            if release["allow_execute"] is not True:
                raise ValueError("Execution release withheld")
            return release

        def prove_window(plan, now):
            if source.window(plan.phase, now) != (plan.starts_at, plan.ends_at):
                raise ValueError("Scheduled window plan mismatch")

        def prove_owner(plan, _value):
            probe = scheduled.owner(metadata, plan.source_sha256, plan.phase,
                                    plan.release_sha256)
            if (probe.expected["round_id"], probe.expected["task_name"],
                probe.expected["task_action_sha256"]) != (
                    plan.slot, plan.task_name, plan.action_sha256):
                raise ValueError("Scheduled owner plan mismatch")
            probe.prove()
            return probe

        ready = run_scheduled_preflight(
            evidence_root, plan=phase_plan, source_sha256=pin,
            release_sha256=release_pin, phase=phase, clock=clock,
            check_source=lambda p: source.check(p.source_sha256),
            check_release=prove_release,
            check_window=prove_window,
            check_owner=prove_owner,
        )

    Derive the scheduled probe's expected values from the same frozen phase
    plan. After this returns, continue the existing financial marker/input-binding
    path using ready.source and ready.owner. The native caller still enforces
    effect-time checks and deadlines, including ready.plan.hard_stop.
    """
    if (
        phase not in ("entry", "exit")
        or (source_sha256, release_sha256, phase)
        != (plan.source_sha256, plan.release_sha256, plan.phase)
        or re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", plan.slot) is None
        or re.fullmatch(r"[A-Za-z0-9_-]{1,160}", plan.task_name) is None
        or any(
            re.fullmatch(r"[a-f0-9]{64}", digest) is None
            for digest in (plan.source_sha256, plan.release_sha256, plan.action_sha256)
        )
        or not all(map(_utc, (plan.starts_at, plan.ends_at, plan.hard_stop)))
        or not plan.starts_at < plan.ends_at <= plan.hard_stop
    ):
        raise ValueError("Invalid scheduled Paper plan binding")

    def now_in_window() -> datetime:
        now = clock()
        if not _utc(now) or not plan.starts_at <= now < plan.ends_at:
            raise ValueError("Outside scheduled Paper start window")
        return now

    def source_check() -> None:
        nonlocal source
        source = check_source(plan)
        _not_denied(source)

    def release_check() -> None:
        nonlocal release
        release = check_release(plan, source)
        _not_denied(release)

    def window_check() -> None:
        _not_denied(check_window(plan, now_in_window()))

    def owner_check() -> None:
        nonlocal owner
        owner = check_owner(plan, source)
        _not_denied(owner)

    def prepare() -> ScheduledPaperPreflight[Source, Release, Owner]:
        return ScheduledPaperPreflight(plan, source, release, owner, now_in_window())

    source: Source
    release: Release
    owner: Owner
    return run_startup(
        root,
        opportunity=plan.opportunity,
        source=plan.source_sha256,
        phase=plan.phase,
        checks=dict(
            source=source_check, release=release_check, window=window_check, owner=owner_check
        ),
        prepare=prepare,
    )
