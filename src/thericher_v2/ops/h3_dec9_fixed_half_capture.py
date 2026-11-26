"""Seal one native Dec9 capture for the fixed-half block's target reader."""

import os
import re
from collections.abc import Callable
from datetime import datetime
from itertools import islice
from pathlib import Path

from thericher_v2.data.kis_paper_h3_capture import (
    H3DailyCapture,
    _mkdir_private,
    _private_root_identity,
)
from thericher_v2.execution.kis_paper_data_capture import _safe_path
from thericher_v2.execution.paper_peer_visit import process_start
from thericher_v2.ops import h3_dec9_fixed_half_target as target
from thericher_v2.research.prospective_h3_target_custody import _digest, _json, _sha

RootRegistration = Callable[[str, Path, tuple[int, int]], bool]
ChildRegistration = Callable[[Path, tuple[int, int]], bool]


def _members(root: Path):
    before = target._fingerprint(root, directory=True)
    with os.scandir(root) as entries:
        names = frozenset(item.name for item in islice(entries, 129))
    if len(names) > 128 or target._fingerprint(root, directory=True) != before:
        raise ValueError("dec9_capture_membership")
    return before, names


def write_dec9_fixed_half_capture(
    pins: target.Dec9TargetPins,
    *,
    prebind_sha256: str,
    capture_once: Callable[
        [target.H3DailyPanelPlan, ChildRegistration, Callable[[], None]], H3DailyCapture
    ],
    register_created_root: RootRegistration,
    owner_ready: Callable[[], bool],
    clock: Callable[[], datetime],
) -> str:
    """Run the metadata surround for the launcher's one native capture call.

    Supply independently retained pre-open pins and an owner probe attesting the
    actual source, isolated roots/ACLs and delegated launch. The callback must
    run synchronously in this process with the exact pinned roots/window and
    native effect-time gates, and return the original closed H3DailyCapture.
    Registration must independently bind exact creations under qualified parent
    boundaries; the observations passed here are not creator proof.
    This writer takes no credentials and reads no page or wire-body bytes.

    Retain the returned OWNER-CLOSED digest only on success, with independent
    positive process-tree closure before readout. The file itself is only a
    completion marker. A created run root consumes the attempt even on failure;
    never resume, clean up, or recover a success digest by scanning the files.
    """
    if type(pins) is not target.Dec9TargetPins or not _digest(prebind_sha256):
        raise ValueError("dec9_capture_binding")
    if not callable(register_created_root):
        raise ValueError("dec9_capture_root_registration")
    plan = target.H3DailyPanelPlan(target.NET25_H3_AXIS, target.INTERVAL.expiry)
    if pins._prebind(plan) != prebind_sha256:
        raise ValueError("dec9_capture_prebind")

    data, market = pins.data_root, pins.market_root
    run = data / "run"
    capture, owner, custody = (run / name for name in ("capture", "owner", "target"))
    source = data / "source/SOURCE.json"
    pid = os.getpid()
    last = pins.capture_opens
    expected_roots = (("run", run), ("market", market), ("capture", capture))
    registered: dict[Path, tuple[int, int]] = {}

    def verify_roots():
        if any(_private_root_identity(path) != identity for path, identity in registered.items()):
            raise ValueError("dec9_capture_root_changed")

    def time_check(deadline):
        nonlocal last
        now = clock()
        if not target._utc(now) or not last <= now < deadline:
            raise ValueError("dec9_capture_clock")
        last = now
        return now

    def gate(deadline):
        time_check(deadline)
        if process_start(pid) != birth or owner_ready() is not True:
            raise ValueError("dec9_capture_owner")
        verify_roots()
        return time_check(deadline)

    def register(path, identity):
        index = len(registered)
        if index >= len(expected_roots) or expected_roots[index][1] != path:
            raise ValueError("dec9_capture_root_registration")
        if (
            type(identity) is not tuple
            or len(identity) != 2
            or any(type(part) is not int for part in identity)
            or identity[0] < 0
            or identity[1] <= 0
            or _private_root_identity(path) != identity
        ):
            raise ValueError("dec9_capture_root_registration")
        # The new root exists but is not yet registered. Ordinary readiness may
        # require all unregistered roots to be absent; the registrar owns this transition.
        time_check(pins.capture_closes)
        if process_start(pid) != birth:
            raise ValueError("dec9_capture_owner")
        verify_roots()
        try:
            accepted = register_created_root(expected_roots[index][0], path, identity)
        except Exception:
            raise ValueError("dec9_capture_root_registration") from None
        if accepted is not True:
            raise ValueError("dec9_capture_root_registration")
        registered[path] = identity
        gate(pins.capture_closes)
        return True

    def register_child(path, identity):
        if not registered:
            raise ValueError("dec9_capture_root_registration")
        return register(path, identity)

    def observe(path, digest, limit):
        identity = target._fingerprint(path)
        raw = target._bounded_read(path, limit, identity)
        if _sha(raw) != digest:
            raise ValueError("dec9_capture_digest")
        return identity, raw

    written = {}

    def write(path, **document):
        raw = _json(document)
        if _safe_path(path) != path or not 0 < len(raw) <= target._META_LIMIT:
            raise ValueError("dec9_capture_path")
        digest = _sha(raw)
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        written[path] = digest, observe(path, digest, target._META_LIMIT)[0]
        return digest

    def verify_written():
        for path, (digest, identity) in written.items():
            if observe(path, digest, target._META_LIMIT)[0] != identity:
                raise ValueError("dec9_capture_changed")

    try:
        time_check(pins.capture_closes)
        birth = process_start(pid)
        if not (
            type(birth) is str
            and re.fullmatch(r"win-filetime:[0-9]{18}", birth)
            and target._ticks(pins.capture_opens) <= int(birth.split(":")[1])
            and 0 < pid < 2**32
        ):
            raise ValueError("dec9_capture_process")
        if any(_safe_path(path) != path or path.exists() for path in (run, market)):
            raise ValueError("dec9_capture_fresh_scope")
        source_id, _ = observe(source, pins.source_sha256, target._NATIVE_LIMIT)
        started = gate(pins.capture_closes)
        if int(birth.split(":")[1]) > target._ticks(started):
            raise ValueError("dec9_capture_process")
        _mkdir_private(run)
        register(run, _private_root_identity(run))
        owner.mkdir()
        attempt_sha = write(
            owner / "ATTEMPT.json",
            schema="H3_DEC9_DATA_ATTEMPT_V1",
            owner=pins.owner,
            launch_attempt_sha256=pins.attempt_sha256,
            source_sha256=pins.source_sha256,
            target_prebind_sha256=prebind_sha256,
            started_at=started.isoformat(),
            pid=pid,
            synthetic=False,
            roots=[str(path) for path in (market, capture, custody, owner)],
        )
        verify_written()
        if observe(source, pins.source_sha256, target._NATIVE_LIMIT)[0] != source_id:
            raise ValueError("dec9_capture_changed")
        dispatched = gate(pins.capture_closes)
        result = capture_once(plan, register_child, verify_roots)
        returned = gate(pins.seal_before)
        if len(registered) != len(expected_roots):
            raise ValueError("dec9_capture_root_registration")
        if not (
            type(result) is H3DailyCapture
            and _digest(result.state_sha256)
            and target._utc(result.closed_at)
            and dispatched <= result.closed_at < pins.capture_closes
            and result.closed_at <= returned
            and result.panel.plan == plan
        ):
            raise ValueError("dec9_capture_result")

        state_path = capture / "capture-state.json"
        state_id, raw = observe(state_path, result.state_sha256, target._NATIVE_LIMIT)
        pages = target._capture_members(raw, pins, plan, dispatched, result.closed_at)
        market_before, capture_before = _members(market), _members(capture)
        names = market_before[1]
        if (
            "owner.lock.d" in names
            or {name for name in names if name.endswith(".native.json")}
            != {path.name for path, _ in pages}
            or capture_before[1] != {"capture-state.json"}
        ):
            raise ValueError("dec9_capture_membership")
        page_ids = {path: target._fingerprint(path) for path, _ in pages}
        if any(not 0 < identity[2] <= target._NATIVE_LIMIT for identity in page_ids.values()):
            raise ValueError("dec9_capture_page_size")

        sealed = gate(pins.seal_before)
        custody.mkdir()
        custody_sha = write(
            custody / "TARGET-CUSTODY.json",
            schema=target._SCHEMA,
            cohort=[day.isoformat() for day in target.INTERVAL],
            prebind_sha256=prebind_sha256,
            capture_state_sha256=result.state_sha256,
            capture_closed_at=result.closed_at.isoformat(),
            sealed_at=sealed.isoformat(),
        )
        gate(pins.seal_before)
        write(
            owner / "TARGET-PIN.json",
            schema="H3_DEC9_TARGET_PIN_V1",
            attempt_record_sha256=attempt_sha,
            prebind_sha256=prebind_sha256,
            capture_state_sha256=result.state_sha256,
            capture_closed_at=result.closed_at.isoformat(),
            target_custody_sha256=custody_sha,
        )

        def verify():
            verify_written()
            if (
                observe(source, pins.source_sha256, target._NATIVE_LIMIT)[0] != source_id
                or observe(state_path, result.state_sha256, target._NATIVE_LIMIT)[0] != state_id
                or any(target._fingerprint(path) != identity for path, identity in page_ids.items())
                or _members(market) != market_before
                or _members(capture) != capture_before
                or _members(owner)[1] != {"ATTEMPT.json", "TARGET-PIN.json"}
                or _members(custody)[1] != {"TARGET-CUSTODY.json"}
            ):
                raise ValueError("dec9_capture_changed")

        verify()
        closed = gate(pins.seal_before)
        owner_sha = write(
            run / "OWNER-CLOSED.json",
            schema="H3_DEC9_OWNER_CLOSED_V1",
            source_sha256=pins.source_sha256,
            attempt_sha256=attempt_sha,
            native_start=birth,
            closed_at=closed.isoformat(),
            target_status="pinned",
            target_custody_sha256=custody_sha,
        )
        verify()
        gate(pins.seal_before)
        return owner_sha
    except OSError:
        raise ValueError("dec9_capture_io") from None
