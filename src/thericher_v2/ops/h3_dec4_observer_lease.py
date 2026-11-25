"""Durable, exact-bank ownership for the Dec4/9 observer definition switch."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES
from thericher_v2.ops.h3_dec4_observer_plan import (
    OBSERVER_API7_SHA256,
    OBSERVER_TASK_PATH,
    OBSERVER_XML_SHA256,
    Dec4ObserverPlan,
)


def _need(ok, code):
    if not ok:
        raise ValueError("h3_observer_" + code)


@dataclass(frozen=True, slots=True)
class ObserverSnapshot:
    task_path: str
    enabled: bool
    hidden_inclusive: bool
    instances: int
    xml_sha256: str
    api7_sha256: str
    shape_sha256: str
    last_run: int


def _sample(value, *, enabled):
    _need(
        type(value) is ObserverSnapshot
        and value.task_path == OBSERVER_TASK_PATH
        and value.enabled is enabled
        and value.hidden_inclusive is True
        and type(value.instances) is int
        and value.instances == 0
        and value.api7_sha256 == OBSERVER_API7_SHA256
        and pv._hash(value.xml_sha256)
        and (value.xml_sha256 == OBSERVER_XML_SHA256) is enabled
        and pv._hash(value.shape_sha256)
        and type(value.last_run) is int
        and 0 <= value.last_run < 2**63,
        "native_sample",
    )
    return value


def _same_activity(before, after):
    _need(
        (before.shape_sha256, before.last_run) == (after.shape_sha256, after.last_run),
        "definition_or_activity_changed",
    )


class ObserverTransport(Protocol):
    """Pinned native implementation; updates only Enabled and reopens readback."""

    def sample(self, *, enabled: bool) -> ObserverSnapshot: ...

    def switch(
        self, before: ObserverSnapshot, *, enabled: bool, attempt: Path, attempt_sha256: str
    ) -> ObserverSnapshot: ...


class Dec4ObserverLease:
    def __init__(self, plan: Dec4ObserverPlan, root: Path, transport: ObserverTransport):
        _need(type(plan) is Dec4ObserverPlan and root.is_absolute(), "scope")
        self.plan = plan
        self.root = root
        self.transport = transport
        self._leg = None
        self._disabled = None

    def _path(self, basename):
        pv.ordinary(self.root)
        _need(self.root.is_dir(), "protected_output_required")
        result = self.root / (basename + ".json")
        pv.ordinary(result)
        return result

    def _new(self, name, row):
        return pv._new(self._path(name), pv.encode(row))

    def _read(self, name):
        return pv._read(self._path(name))

    def _clock(self, timestamp, *, restore=False):
        opens, closes, _ = _TIMES[self.plan.phase]
        _need(
            type(timestamp) is datetime
            and timestamp.utcoffset() == timedelta(0)
            and opens <= timestamp
            and (restore or timestamp < closes),
            "clock",
        )

    def _switch(self, name, row, before, enabled):
        attempt = self._new(name, row)
        after = _sample(
            self.transport.switch(
                before,
                enabled=enabled,
                attempt=self._path(name),
                attempt_sha256=pv.digest(row),
            ),
            enabled=enabled,
        )
        _need(self._read(name) == attempt, "attempt_changed")
        _same_activity(before, after)
        return after, attempt

    def begin(self, leg, ready, *, clock=lambda: datetime.now(UTC)):
        """Called after local phase staging and before financial dispatch selection."""
        _need(type(leg) is pv.BankLeg and self._leg is None, "disable_already_attempted")
        _need(
            ready.plan.phase == self.plan.phase
            and ready.source["observer_plan_sha256"] == self.plan.sha256
            and leg.identity["source"] == ready.plan.source_sha256
            and leg.identity["release"] == ready.plan.release_sha256,
            "binding",
        )
        _need(
            not any(
                self._path(key).exists()
                for key in ("STARTED", "DISABLED", "RESTORE_STARTED", "RESTORED")
            ),
            "disable_already_attempted",
        )
        leg.check()
        self._clock(clock())
        before = _sample(self.transport.sample(enabled=True), enabled=True)
        leg.check()
        started_at = clock()
        self._clock(started_at)
        row = dict(
            schema="h3-dec4-observer-disable-v1",
            plan=self.plan.sha256,
            identity=leg.identity,
            owner=leg.record["owner"],
            at=started_at.isoformat(),
            before=asdict(before),
        )
        self._leg = leg
        after, attempt = self._switch("STARTED", row, before, False)
        leg.check()
        self._clock(clock())
        disabled = self._new(
            "DISABLED",
            dict(
                schema="h3-dec4-observer-disabled-v1",
                start_sha256=pv.digest(row),
                observed=asdict(after),
            ),
        )
        self._disabled = attempt, disabled, after

    def renew_if_started(self, leg):
        if self._leg is None:
            _need(not self._path("STARTED").exists(), "disable_already_attempted")
            return True  # The caller has not selected capsule dispatch yet.
        _need(self._leg is leg and self._disabled is not None, "disable_unknown")
        attempt, disabled, after = self._disabled

        def check_record():
            leg.check()
            _need(
                not self._path("RESTORE_STARTED").exists()
                and self._read("STARTED") == attempt
                and self._read("DISABLED") == disabled,
                "disable_changed",
            )

        check_record()
        current = _sample(self.transport.sample(enabled=False), enabled=False)
        check_record()
        _need(current == after, "disabled_readback_changed")
        return True

    def inspect_interrupted_disable(self):
        """Read-only classification for a missing result; never grants restoration."""
        try:
            raw, _ = self._read("STARTED")
            start = pv._decode(raw)
            _need(
                start["plan"] == self.plan.sha256 and not self._path("DISABLED").exists(),
                "interrupt_scope",
            )
            before = _sample(ObserverSnapshot(**start["before"]), enabled=True)
        except (OSError, KeyError, TypeError, ValueError, pv.Denied):
            return "unknown"
        for enabled, label in ((True, "original_observed"), (False, "disabled_shape_observed")):
            try:
                current = _sample(self.transport.sample(enabled=enabled), enabled=enabled)
                _same_activity(before, current)
                _need(self._read("STARTED")[0] == raw, "attempt_changed")
                return label
            except (OSError, ValueError, pv.Denied):
                continue
        return "unknown"

    def restore_closed(
        self,
        gate_root,
        *,
        bank,
        identity,
        native_closed,
        clock=lambda: datetime.now(UTC),
    ):
        """Restore only the exact original normally closed leg; no abort inference."""
        _need(self.root == Path(self.plan.output_root), "restore_output_scope")
        return self._restore_closed(
            gate_root, bank, identity, native_closed, clock, pv.process_start
        )

    def _restore_closed(self, gate_root, bank, identity, native_closed, clock, process_probe):
        key = pv.bank_key(bank)
        pv._identity(identity, key)
        root = Path(gate_root) / ("bank-" + key)
        _need(root.is_dir(), "restore_gate_missing")
        with pv.Gate(root) as gate:
            _need(not self._path("RESTORE_STARTED").exists(), "restore_already_attempted")
            started = self._read("STARTED")
            disabled = self._read("DISABLED")
            start, off = pv._decode(started[0]), pv._decode(disabled[0])
            _need(
                start["schema"] == "h3-dec4-observer-disable-v1"
                and start["plan"] == self.plan.sha256
                and start["identity"] == identity
                and off["schema"] == "h3-dec4-observer-disabled-v1"
                and off["start_sha256"] == pv.digest(start),
                "restore_binding",
            )
            self._clock(datetime.fromisoformat(start["at"]))
            original = _sample(ObserverSnapshot(**start["before"]), enabled=True)
            before = _sample(ObserverSnapshot(**off["observed"]), enabled=False)
            _same_activity(original, before)

            path = root / ("CLOSED-" + identity["run"] + ".json")
            closure = pv._read(path)
            receipt = pv._decode(closure[0])
            record = receipt["record"]
            pv._record(record, key)
            _need(
                receipt["status"] == "CLOSED_OPERATIONAL_ONLY"
                and receipt["same_native_intent_reconciliation_required"] is True
                and receipt["reservation_or_budget_release"] is False
                and record["identity"] == identity
                and record["owner"] == start["owner"]
                and identity["member"] == "stock-ingress"
                and len(record["visits"]) <= 1
                and all(
                    v["kind"] == "effect" and v["status"] == "CLOSED" for v in record["visits"]
                ),
                "restore_leg_not_closed",
            )
            owner = record["owner"]

            def check_closure():
                self._clock(clock(), restore=True)
                gate.check()
                active = root / "ACTIVE-LEG.json"
                pv.ordinary(active)
                _need(
                    not active.exists()
                    and self._read("STARTED") == started
                    and self._read("DISABLED") == disabled
                    and pv._read(path) == closure,
                    "restore_closure_changed",
                )
                current = process_probe(owner["pid"])
                _need(
                    owner["native_start"].startswith("win-filetime:")
                    and (
                        current is None
                        or (
                            pv._start(current)
                            and current.startswith("win-filetime:")
                            and current != owner["native_start"]
                        )
                    ),
                    "restore_owner_not_closed",
                )
                _need(native_closed(record) is True, "restore_native_closure_unknown")

            check_closure()
            _need(
                _sample(self.transport.sample(enabled=False), enabled=False) == before,
                "restore_disabled_changed",
            )
            check_closure()
            row = dict(
                schema="h3-dec4-observer-restore-v1",
                plan=self.plan.sha256,
                disabled_sha256=pv.digest(off),
                closure_sha256=pv.digest(receipt),
                identity=identity,
            )
            after, _ = self._switch("RESTORE_STARTED", row, before, True)
            check_closure()
            _need(after == original, "restore_original_changed")
            self._new(
                "RESTORED",
                dict(
                    schema="h3-dec4-observer-restored-v1",
                    attempt_sha256=pv.digest(row),
                    observed=asdict(after),
                ),
            )
