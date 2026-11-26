"""Publish completed H20 transport evidence for the protected host reader."""

import json
import os
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from thericher_v2.execution.paper_peer_visit import _new, _read, ordinary
from thericher_v2.ops.h20_phase_host import (
    HARD_STOP,
    OPENS,
    _need,
    _validated_phase_projection,
    read_h20_phase_envelope,
)
from thericher_v2.ops.h20_phase_transport import _PHASES, _utc_now

_REFS = (
    "reader_source",
    "installed_host",
    "release",
    "plan",
    "contract",
    "input_ref",
    "policy_ref",
)


def _paths(run, protected_digest):
    run, protected_digest = Path(run), Path(protected_digest)
    for path in (run, protected_digest):
        ordinary(path)
        _need(".." not in path.parts)
    _need(run.is_dir() and protected_digest.parent.is_dir())
    _need(not protected_digest.resolve().is_relative_to(run.resolve()))
    return run, protected_digest


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _pointer(path, raw):
    return dict(path=str(path), bytes=len(raw), sha256=sha256(raw).hexdigest())


def _window(earliest=OPENS):
    now = _utc_now()
    _need(earliest <= now < HARD_STOP)
    return now


def _commit_digest(path, pin, observed, snapshots):
    # Expose only a flushed digest, with an atomic, no-replace directory entry.
    with NamedTemporaryFile(dir=path.parent, prefix=".h20-digest-", delete=False) as stream:
        pending = Path(stream.name)
        try:
            stream.write((pin + "\n").encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            ordinary(path)
            _need(all(_read(member) == snapshot for member, snapshot in snapshots.items()))
            _window(observed)
            os.link(pending, path)
        finally:
            stream.close()
            pending.unlink()


def publish_h20_phase_result(
    *, run, protected_digest, source_pin, binding, coordinator_pin, completed
):
    """Commit the (result, closure) returned by the current native transport.

    The protected caller owns the run claim, source/binding pins and both
    directory ACLs and supplies public evidence paths only. This function
    supplies neither admission nor ACL setup. A failure before commit leaves
    any exclusive evidence in place; never heal it by replaying the run.
    """
    observed = _window()
    run, protected_digest = _paths(run, protected_digest)
    closed_path, result_path = run / "CLOSED.json", run / "RESULT.json"
    for path in (closed_path, result_path, protected_digest):
        ordinary(path)
        _need(not path.exists())

    result, closure = completed
    _need(closure.keys() == {"status", "CID_absent", "Jobs", "admissions"})
    jobs, admissions = closure["Jobs"], closure["admissions"]
    _need(
        closure["status"] == "PASS"
        and closure["CID_absent"] is True
        and tuple(row["phase"] for row in admissions) == _PHASES
        and jobs
        and all(j["exit"] == 0 and j["active"] == 0 and j["closed"] is True for j in jobs)
    )
    closed_raw = _encode(closure)
    envelope = dict(
        source_sha256=source_pin,
        observed_utc=observed.isoformat(),
        result=result,
        admissions=admissions,
        closure=_pointer(closed_path, closed_raw),
        broker_calls=0,
        private_writes=0,
        reservation_released=False,
        current_read_not_historical_OS_origin=True,
        fees_settlement_netPnL="NOT_OBSERVED",
        **{("H20_source" if key == "installed_host" else key): binding[key] for key in _REFS},
    )
    result_raw = _encode(envelope)
    evidence = _pointer(result_path, result_raw)
    _validated_phase_projection(result, evidence, envelope["observed_utc"])

    _window(observed)
    closed_snapshot = _new(closed_path, closed_raw)
    _window(observed)
    result_snapshot = _new(result_path, result_raw)
    pin = evidence["sha256"]
    projection = read_h20_phase_envelope(
        run, source_pin, binding, coordinator_pin, published_result_pin=pin
    )
    snapshots = {closed_path: closed_snapshot, result_path: result_snapshot}
    _commit_digest(protected_digest, pin, observed, snapshots)
    return projection


def read_published_h20_phase_result(*, run, protected_digest, source_pin, binding, coordinator_pin):
    """Read a committed result using only the independently protected pin."""
    run, protected_digest = _paths(run, protected_digest)
    snapshot = _read(protected_digest)
    raw = snapshot[0]
    _need(len(raw) == 65 and raw[-1:] == b"\n" and all(c in b"0123456789abcdef" for c in raw[:-1]))
    projection = read_h20_phase_envelope(
        run, source_pin, binding, coordinator_pin, published_result_pin=raw[:-1].decode("ascii")
    )
    _need(_read(protected_digest) == snapshot)
    return projection
