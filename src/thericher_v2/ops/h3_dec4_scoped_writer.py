"""Join the exact BankLeg/guest to a fresh, bounded cross-owner custody decision."""

import time
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_docker_inventory import Dec4DockerInventory
from thericher_v2.ops.h3_dec4_guest_identity import CapsuleProcess, linux_argv_sha256
from thericher_v2.ops.h3_dec4_monitor_mount import validate_worker_control_mount
from thericher_v2.ops.h3_dec4_writer_census import Dec4WriterCensus
from thericher_v2.ops.h3_dec4_writer_identity import join_dec4_writer_actors


def _norm(value):
    return str(value).replace("\\", "/").casefold().rstrip("/")


class Dec4ScopedWriterGuard:
    """Source-binds a real census invocation; neither a cache nor a writer lease."""

    def __init__(self, census):
        if type(census) is not Dec4WriterCensus:
            raise ValueError("h3_writer_guard_scope")
        self.census = census

    @property
    def sha256(self):
        return self.census.profile.sha256

    def source_ready(self, leg, ready):
        leg.check()
        source = ready.source
        bank = dict(source["original_owner"]["bank"])
        protected = {_norm(path) for path in self.census.profile.protected}
        if self.census.profile.monitor is not None:
            if bank["volume"] != self.census.profile.monitor.bank_volume:
                raise ValueError("h3_writer_guard_scope")
            validate_worker_control_mount(source["capsule"]["mounts"], bank["volume"])
        retained = Path(source["retained_input_path"])
        if not retained.is_absolute() or ".." in retained.parts:
            raise ValueError("h3_writer_guard_scope")
        private_writes = {
            _norm(bank["volume"]),
            _norm(leg.root.parent),
            _norm(retained.parent),
        } | {_norm(row["source"]) for row in source["capsule"]["mounts"] if row["rw"] is True}
        if (
            source.get("writer_census_sha256") != self.sha256
            or source.get("synthetic_only", False) is not False
            or pv.bank_key(bank) != leg.key
            or leg.root.parent != Path(source["original_gate_root"])
            or not private_writes <= protected
        ):
            raise ValueError("h3_writer_guard_scope")
        return True

    def before_observer(self, leg, ready, watchdog, *, restore=None):
        return self._decide(leg, ready, watchdog, None, False, None, restore)

    def check(self, context, *, stage, visit):
        if stage not in {"BEFORE_CREDENTIALS", "BEFORE_CREATE", "AFTER_CREATE", "GUEST_ADMISSION"}:
            raise ValueError("h3_writer_guard_scope")
        guest = stage == "GUEST_ADMISSION"
        if guest:
            daemon, process = context.daemon_inventory, context.guest_process
            if (
                type(daemon) is not Dec4DockerInventory
                or daemon.container_process_count != 1
                or daemon.cid != visit.cid
                or type(process) is not CapsuleProcess
                or process.namespace_pid != 1
                or not 0 < process.start_ticks < 2**63
                or process.argv_sha256
                != linux_argv_sha256([*visit.spec["entrypoint"], *visit.spec["args"]])
            ):
                raise ValueError("h3_writer_guest_unbound")
        return self._decide(
            context.leg,
            context.readiness,
            context.watchdog_actor(),
            visit,
            guest,
            context.exchange_deadline,
            context.restore_actor(),
        )

    def _decide(self, leg, ready, watchdog, visit, guest, deadline, restore):
        self.source_ready(leg, ready)
        now = datetime.now(UTC)
        if not ready.plan.starts_at <= now < ready.plan.ends_at:
            raise ValueError("h3_writer_guard_clock")
        cap = time.monotonic() + (ready.plan.ends_at - now).total_seconds()
        if deadline is not None:
            cap = min(cap, deadline)
        proof = ready.owner.prove()
        own = visit.cid if visit is not None else None
        exact_verified = False

        def owned(facts):
            leg.check()
            return join_dec4_writer_actors(
                facts,
                owner=proof,
                bank_record=leg.record,
                watchdog=watchdog,
                restore=restore,
                attached_visit=visit if guest else None,
            )

        def exact(row):
            nonlocal exact_verified
            if own is None or row["Id"] != own or visit.cid != own:
                return False
            if not exact_verified:
                visit.exact(visit.inspect(own))
                exact_verified = True  # Only within this one fresh decision.
            return True

        result = self.census.evaluate(
            own=own, deadline=cap, bind_owned=owned, exact_scope=exact if own is not None else None
        )
        leg.check()
        if result is not True or time.monotonic() >= cap:
            raise ValueError("h3_writer_guard_denied")
        return True
