"""Bind a finite native Paper coordinator to the tracked startup preflight."""

import hashlib
import os
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Protocol

from thericher_v2.ops.paper_scheduled_preflight import (
    ScheduledPaperPlan,
    ScheduledPaperPreflight,
    run_scheduled_preflight,
)
from thericher_v2.ops.paper_startup import Phase


class NativeOwnerProbe(Protocol):
    @property
    def expected(self) -> Mapping[str, object]: ...

    def prove(self) -> Mapping[str, object]: ...


class NativeScheduledSource(Protocol):
    ROOT: Path
    ROUND: str
    SLOTS: Mapping[str, Mapping[str, str]]

    def action(self, pin: str, release_pin: str, phase: Phase) -> str: ...

    def check(self, pin: str) -> Mapping[str, object]: ...

    def release(
        self, value: Mapping[str, object], pin: str, digest: str
    ) -> Mapping[str, object]: ...

    def window(self, phase: Phase, at: datetime) -> tuple[datetime, datetime]: ...


def run_native_scheduled_preflight(
    evidence_root: Path,
    *,
    source: NativeScheduledSource,
    pin: str,
    release_pin: str,
    phase: Phase,
    clock: Callable[[], datetime],
    make_owner: Callable[[str, Phase, str], NativeOwnerProbe],
) -> ScheduledPaperPreflight[Mapping[str, object], Mapping[str, object], NativeOwnerProbe]:
    """Run before the native attempt marker, input reads or financial callbacks.

    The isolated launcher must load and pin the source and native provider code;
    never construct this interface from task arguments or untrusted payloads.
    The provider owns native XML/API/ACL, instance and PID/birth verification.
    Retain the returned probe for effect-time checks; preflight is not admission.
    """
    if phase not in ("entry", "exit") or not source.ROOT.is_absolute():
        raise ValueError("Invalid native scheduled source binding")
    row = source.SLOTS[phase]
    plan = ScheduledPaperPlan(
        slot=source.ROUND,
        phase=phase,
        task_name=row["name"],
        action_sha256=hashlib.sha256(source.action(pin, release_pin, phase).encode()).hexdigest(),
        source_sha256=pin,
        release_sha256=release_pin,
        starts_at=datetime.fromisoformat(row["start_UTC"]),
        ends_at=datetime.fromisoformat(row["end_UTC"]),
        hard_stop=datetime.fromisoformat(row["hard_UTC"]),
    )
    binding = dict(
        dispatcher_source=pin,
        dispatcher_release=release_pin,
        dispatcher_root=str(source.ROOT),
        task_name=plan.task_name,
        task_action_sha256=plan.action_sha256,
        round_id=plan.slot,
    )

    def check_release(_plan, value):
        released = source.release(value, pin, release_pin)
        if (
            released.get("source") != pin
            or released.get("allow_execute") is not True
            or released.get("actual_financial_admission") is not False
        ):
            raise ValueError("Native scheduled execution release withheld")
        return released

    def check_window(_plan, at):
        if source.window(phase, at) != (plan.starts_at, plan.ends_at):
            raise ValueError("Native scheduled start window mismatch")

    def check_owner(_plan, _value):
        probe = make_owner(pin, phase, release_pin)
        if probe.expected != binding:
            raise ValueError("Native scheduled owner expectation mismatch")
        proof = probe.prove()
        if (
            any(proof.get(key) != value for key, value in binding.items())
            or proof.get("schema") != "paper-stock-ingress-owner-v1"
            or proof.get("status") != "PASS_STOCK_INGRESS_SCHEDULED_OWNER"
            or proof.get("origin") != "ACTUAL_STOCK_INGRESS_TASK_SOURCE_ABI"
            or proof.get("no_old_model_self_rows") is not True
            or type(proof.get("pid")) is not int
            or proof["pid"] != os.getpid()
            or type(proof.get("start_ticks")) is not str
            or re.fullmatch(r"[1-9][0-9]*", proof["start_ticks"]) is None
            or type(proof.get("argv_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", proof["argv_sha256"]) is None
        ):
            raise ValueError("Native scheduled owner proof mismatch")
        return probe

    return run_scheduled_preflight(
        evidence_root,
        plan=plan,
        source_sha256=pin,
        release_sha256=release_pin,
        phase=phase,
        clock=clock,
        check_source=lambda _plan: source.check(pin),
        check_release=check_release,
        check_window=check_window,
        check_owner=check_owner,
    )
