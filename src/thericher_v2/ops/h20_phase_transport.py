"""Wire the pinned H20 read-only native transport to the Dec1 phase reader."""

import ast
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import ModuleType

from thericher_v2.execution.paper_peer_visit import _read, ordinary
from thericher_v2.ops.h20_phase_exit_boundary import prove_h20_exit_read_boundary
from thericher_v2.ops.h20_phase_host import (
    HARD_STOP,
    LAST_START,
    OPENS,
    _need,
    _strict_json,
    invoke_h20_phase_window,
)
from thericher_v2.ops.h20_phase_owner_probe import prove_h20_exit_outer_owner_closed
from thericher_v2.ops.h20_phase_web_census import bind_h20_web_census

_ROOT = Path(
    "D:/thericher-v2/model-artifacts/execution/"
    "current-h20-after-entry-read-worker-preparation-20261031-v1"
)
_SOURCES = {
    "transport-r2/transport.py": "75a0e1ad032bf95b4a3a2c6756467d2e86cf56e71a269d42cec8507f6ad0bcd8",
    "transport-r2/metadata_binding.py": (
        "f3e5a63252bc24b04883fb37b08b54859f672a45ecaf8adcd328b24a4d5cd852"
    ),
    "qualification-r3/qualify.py": (
        "2a1dff8a24f49d993fc3c47cfcbf6d1d6ea21642c9c5817751f4169d7dd97c4b"
    ),
}
_PHASES = ("before_create", "before_start", "before_read", "after_read", "after_remove")


def _native_sources():
    sources = {}
    for member, expected in _SOURCES.items():
        path = _ROOT / member
        data = _read(path)[0]
        _need(sha256(data).hexdigest() == expected)
        sources[member] = (path, data)

    def module(member):
        path, data = sources[member]
        scope = ModuleType("h20_phase_native")
        scope.__file__ = str(path)
        exec(compile(data, str(path), "exec"), vars(scope))
        return scope

    path, data = sources["qualification-r3/qualify.py"]
    names = {"BoundedTransport", "share_deadline"}
    body = [
        node
        for node in ast.parse(data).body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
    ]
    _need({node.name for node in body} == names and len(body) == len(names))
    native = {"transport": module("transport-r2/transport.py")}
    exec(compile(ast.Module(body, []), str(path), "exec"), native)
    return (
        module("transport-r2/metadata_binding.py").configure,
        native["BoundedTransport"],
        native["share_deadline"],
    )


def _utc_now():
    return datetime.now(UTC)


class _Dec1Deadline:
    def __init__(self):
        now = _utc_now()
        _need(OPENS <= now < LAST_START)
        self.started = time.monotonic()
        self.absolute = self.started + (HARD_STOP - now).total_seconds()

    def remaining(self, cleanup=False):
        reserve = 0 if cleanup else 30
        value = min(
            self.started + 180 - reserve - time.monotonic(),
            self.absolute - reserve - time.monotonic(),
            (HARD_STOP - _utc_now()).total_seconds() - reserve,
        )
        if value <= 0:
            raise TimeoutError("H20_PHASE_NATIVE_DEADLINE")
        return value


def run_h20_phase_transport(*, binding, out, entry_file, entry_sha256, guest_sha256, image):
    """Run only from a protected one-shot caller with separately pinned binding.

    The caller supplies the protected output claim and publication.
    The pinned outer probe is not replaceable by a caller claim.
    Current custody is rechecked by native admission. Do not
    feed this function the old November actual binding.
    Returns the categorical DTO, five admissions and joined process facts.
    """
    deadline = _Dec1Deadline()
    entry_file = Path(entry_file)
    entry_snapshot = _read(entry_file)
    _need(sha256(entry_snapshot[0]).hexdigest() == entry_sha256)
    out = Path(out)
    ordinary(out)
    _need(out.is_dir() and not any(out.iterdir()))

    def owner_closed(task, pid):
        return prove_h20_exit_outer_owner_closed(task, pid, timeout=min(8, deadline.remaining()))

    _need(prove_h20_exit_read_boundary(owner_closed=owner_closed) is True)
    deadline.remaining()
    configure, bounded_transport, share_deadline = _native_sources()
    configured = configure(binding, out, entry_file)
    bind_h20_web_census(configured, binding)
    namespace = configured.namespace
    _need(namespace["SOURCE"]["image"] == image)
    deadline.remaining()
    evidence = []
    caller = None

    def fresh(**kwargs):
        nonlocal caller
        phase = kwargs["phase"]
        deadline.remaining(cleanup=phase == "after_remove")
        _need(len(evidence) < len(_PHASES) and phase == _PHASES[len(evidence)])
        _need(configured.fresh(**kwargs) is True)
        path = out / ("CAPABILITY-" + phase + ".json")
        receipt = _read(path)[0]
        _need(_strict_json(receipt)["status"] == "NO_CURRENT_PRIVATE_CUSTODY_WRITER_OBSERVED")
        identity = namespace["PHASES"][-1]["exact_own"]
        _need(
            identity["source_sha256"] == entry_sha256
            and identity["origin"] == "actual_source_caller_not_OS_scheduler_proof"
        )
        key = (identity["pid"], identity["created_filetime"], identity["argv_sha256"])
        _need(caller is None or caller == key)
        caller = key
        evidence.append(
            dict(
                phase=phase,
                verdict=dict(
                    path=str(path), bytes=len(receipt), sha256=sha256(receipt).hexdigest()
                ),
                actual_caller=dict(identity),
            )
        )
        return True

    instance = bounded_transport(
        namespace["JOB"], binding["sanitized_environment"], fresh, deadline
    )
    share_deadline(configured, instance)
    result = invoke_h20_phase_window(
        at=_utc_now(),
        source_sha256=guest_sha256,
        image=image,
        mounts=binding["mounts"],
        transport=instance.invoke,
        admission_ready=lambda: _read(entry_file) == entry_snapshot and deadline.remaining() > 0,
    )
    deadline.remaining(cleanup=True)
    _need(_read(entry_file) == entry_snapshot)
    _need(
        len(evidence) == len(_PHASES)
        and instance.cid_absent is True
        and instance.jobs
        and all(j["exit"] == 0 and j["active"] == 0 and j["closed"] is True for j in instance.jobs)
    )
    return result, dict(status="PASS", CID_absent=True, Jobs=instance.jobs, admissions=evidence)
