"""Bind the Dec4 exchange to the frozen R8 BankLeg/Job/daemon lifecycle."""

import ast
import hashlib
import json
import math
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_guest import Dec4GuestVisit
from thericher_v2.ops.h3_dec4_guest_identity import linux_argv_sha256
from thericher_v2.ops.h3_dec4_host_exchange import exchange_dec4_guest
from thericher_v2.ops.h3_dec4_job_closure import retain_dec4_normal_job_close

_CONTROLLER = Path("D:/thericher-v2/model-artifacts/execution/n9h3-control-r8/c1/controller")
_DAEMON = "38abb623556fdf08ba38253e369e369b019ffeb23221af3da9cdc37bed07fe8c"
_JOB = "76dab8660fcc39e0876d33dd8b2acfd00f0b1d0561d0e51f8a7b3e9757637ca2"
# Dec4 reuses the frozen R8 Job/daemon code with the current exact BankLeg API.
_BANK = "b204268e7ee1dd466b2e8184b40670c49bdbdbe01b93250b085dd3870fde3489"


def _verified(raw, digest):
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("h3_capsule_r8_source_mismatch")
    return raw


def _visit_tree(raw, filename):
    tree = ast.parse(_verified(raw, _DAEMON), filename=filename)
    assignments = {n.targets[0].id: n for n in tree.body if isinstance(n, ast.Assign)}
    helpers = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    (visit,) = (n for n in tree.body if isinstance(n, ast.ClassDef))
    methods = {n.name: n for n in visit.body}
    # The guest has its own fixed argument parser, not the R8 telemetry ABI.
    methods["__init__"].body[1].value = ast.parse("spec", mode="eval").body
    created = methods["_popen"].body[0]
    created.body[0].body.pop(1)  # Use the pinned Job module's LIMIT, not a sys.path import.

    execute = methods["execute"]
    execute.args = ast.parse("def f(self, *, renew, exchange): pass").body[0].args
    execute.body[1] = ast.parse("renew()").body[0]
    execute.body[2] = ast.parse(
        "need(ctx.writer_guard.check(ctx, stage='BEFORE_CREATE', visit=self) is True, "
        "'h3_capsule_visit_writer_denied')"
    ).body[0]
    owned_visit = execute.body[-1]
    lifecycle = owned_visit.body[-1]
    # Keep create/inspect/ack and Visit.spawn intact. Only the owned attach
    # handler changes; no old transport, plain mode, or default factory remains.
    lifecycle.body[-5] = ast.parse(
        "need(ctx.writer_guard.check(ctx, stage='AFTER_CREATE', visit=self) is True, "
        "'h3_capsule_visit_writer_denied')"
    ).body[0]
    lifecycle.body[-2:-1] = ast.parse(
        """
renew()
p = factory(args, env=ENV, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0))
result = exchange(p)
p.join_job()
"""
    ).body
    # An exited attach root can still have live Job descendants holding pipes.
    # On faults kill any unjoined Job before trying to wait or close the visit.
    lifecycle.finalbody[1].body[0].test = ast.parse("not p.joined", mode="eval").body
    close_probe = methods["_close_probe"]
    terminal = close_probe.body[-1]
    if not isinstance(terminal, ast.Return):
        raise ValueError("h3_capsule_r8_source_mismatch")
    close_probe.body[-1:] = [
        ast.Assign([ast.Name("receipt", ast.Store())], terminal.value),
        *ast.parse("self.dec4_close_proof = (record, receipt)\nreturn receipt").body,
    ]

    tree.body = [assignments["D"], assignments["ENV"], helpers["norm"], helpers["need"], visit]
    return ast.fix_missing_locations(tree)


def _compile_visit(raw, root, job_popen, job_limit):
    """Load only the pinned class and its helpers; R8 transport is not imported."""
    filename = str(root / "daemon.py")
    namespace = dict(
        __name__="_dec4_r8_capsule_visit",
        R=root,
        pv=pv,
        hashlib=hashlib,
        json=json,
        subprocess=subprocess,
        time=time,
        uuid4=uuid4,
        JobPopen=job_popen,
        LIMIT=job_limit,
    )
    exec(compile(_visit_tree(raw, filename), filename, "exec", dont_inherit=True), namespace)
    return namespace["CapsuleVisit"]


def _load_visit():
    _verified(Path(pv.__file__).read_bytes(), _BANK)
    job_path = _CONTROLLER / "job_popen.py"
    raw = _verified(job_path.read_bytes(), _JOB)
    job = {"__name__": "_dec4_r8_job_popen"}
    exec(compile(raw, str(job_path), "exec", dont_inherit=True), job)
    return _compile_visit(
        (_CONTROLLER / "daemon.py").read_bytes(), _CONTROLLER, job["JobPopen"], job["LIMIT"]
    )


def run_dec4_capsule_visit(context, spec, *, guest, load_packet, read_retained, exchange_deadline):
    """Run once on the caller's already-entered BankLeg, never opening another leg.

    The pinned launcher supplies the authenticated context/spec, receive-only
    packet loader and fresh retained-result reader. Context admission must
    recheck the coordinator's exact owner/window and relevant writer/observer
    state. The caller must independently enforce the hard stop (including
    blocked callbacks) and own daemon recovery if the host cannot run finally.
    The monotonic exchange deadline is not that hard stop.
    """
    return _run_visit(
        _load_visit(), context, spec, guest, load_packet, read_retained, exchange_deadline
    )


def _run_visit(
    visit_type,
    ctx,
    spec,
    guest,
    load_packet,
    read_retained,
    exchange_deadline,
    *,
    _clock=time.monotonic,
):
    leg = ctx.leg
    if (
        type(leg) is not pv.BankLeg
        or type(guest) is not Dec4GuestVisit
        or ctx.source_pin != leg.identity["source"]
        or guest.cohort.source_ref != "sha256:" + ctx.source_pin
        or pv.bank_key(ctx.bank) != leg.key
        or type(spec) is not dict
        or spec.get("kind") != "effect"
        or spec.get("phase") != guest.cohort.slot.phase
        or type(ctx.created_starts) is not dict
        or ctx.created_starts
        or type(exchange_deadline) not in (int, float)
        or not math.isfinite(exchange_deadline)
    ):
        raise ValueError("h3_capsule_visit_binding")

    def check_deadline():
        if _clock() >= exchange_deadline:
            raise ValueError("h3_capsule_visit_deadline")

    def renew():
        check_deadline()
        leg.check()
        if ctx.admission() is not True:
            raise ValueError("h3_capsule_visit_owner_denied")
        leg.check()
        check_deadline()
        return True

    leg.check()
    if leg.record["visits"]:
        raise ValueError("h3_capsule_visit_already_started")
    args = spec.get("args")
    if (
        type(args) is not list
        or len(args) != 4
        or args[:2] != ["/app/scripts/run_h3_dec4_account_capsule.py", "--binding-sha256"]
        or not pv._hash(args[2])
        or args[3] != "--execute"
    ):
        raise ValueError("h3_capsule_visit_binding")
    binding_sha256 = args[2]
    renew()
    visit = visit_type(ctx, deepcopy(spec))
    if ctx.writer_guard.check(ctx, stage="BEFORE_CREDENTIALS", visit=visit) is not True:
        raise ValueError("h3_capsule_visit_writer_denied")
    check_deadline()
    used = False

    def exchange(process):
        nonlocal used
        if used:
            raise ValueError("h3_capsule_exchange_already_started")
        used = True

        def check_attach():
            leg.check()
            (active,) = leg.record["visits"]
            # Exact daemon census reads can append joined metadata children.
            # The durably recorded attach, not list position, owns the stream.
            same_pid = [job for job in visit.jobs if job.pid == process.pid and not job.joined]
            if (
                active["run"] != visit.run
                or active["status"] != "ACTIVE"
                or active["create"]["resolution"] != "ACK_EXACT_CID"
                or active["create"]["cid"] != visit.cid
                or active["create"]["spec_sha256"] != pv.digest(visit.spec)
                or len(active["children"]) != 2
                or active["children"][-1]["pid"] != process.pid
                or active["children"][-1]["native_start"] != process.native_start
                or active["children"][-1]["status"] != "RUNNING_OR_UNKNOWN"
                or len(same_pid) != 1
                or same_pid[0] is not process
                or any(job is not process and not job.joined for job in visit.jobs)
                or process.joined
            ):
                raise ValueError("h3_capsule_attach_identity_changed")

        def admit_guest(_sequence, identity):
            renew()
            check_attach()
            ctx.guest_process = identity
            try:
                if ctx.writer_guard.check(ctx, stage="GUEST_ADMISSION", visit=visit) is not True:
                    raise ValueError("h3_capsule_visit_writer_denied")
            finally:
                ctx.guest_process = None
            check_attach()
            check_deadline()
            return True

        def credential_packet():
            check_attach()
            check_deadline()
            packet = load_packet()
            check_attach()
            check_deadline()
            return packet

        return exchange_dec4_guest(
            process,
            load_packet=credential_packet,
            guest=guest,
            guest_argv_sha256=linux_argv_sha256([*visit.spec["entrypoint"], *visit.spec["args"]]),
            admit=admit_guest,
            read_retained=read_retained,
            deadline=exchange_deadline,
        )

    original_probe = leg.process_probe

    def probe(pid):
        # Consume the birth recorded on the suspended Job child even if the
        # CLI is already gone. Closure queries current liveness via the old probe.
        if pid in ctx.created_starts:
            return ctx.created_starts.pop(pid)
        return original_probe(pid)

    leg.process_probe = probe
    try:
        result = visit.execute(renew=renew, exchange=exchange)
        stdout = result.pop("accepted_stdout")
        cohort, slot = guest.cohort, guest.cohort.slot
        retain_dec4_normal_job_close(
            leg,
            *visit.dec4_close_proof,
            accepted={
                "schema": "h3-dec4-accepted-capsule-stdout-v1",
                "phase": slot.phase,
                "source_ref": cohort.source_ref,
                "basis_ref": cohort.basis_ref,
                "input_ref": slot.input_ref,
                "policy_ref": slot.policy_ref,
                "binding_sha256": binding_sha256,
                "spec_sha256": pv.digest(visit.spec),
                "stdout_sha256": stdout["sha256"],
                "exit_code": stdout["exit_code"],
            },
        )
        return result
    finally:
        leg.process_probe = original_probe
        ctx.created_starts.clear()
