"""Read the prebound Dec9 MODP1 target edition for the Dec4 fixed-half slot."""

import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import islice
from pathlib import Path

from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanelPlan,
    qualify_h3_daily_panel,
)
from thericher_v2.execution.kis_paper_data_capture import CaptureResult, _safe_path
from thericher_v2.ops.h3_dec4_fixed_half_plan import ENTRY_OPEN
from thericher_v2.ops.h3_dec4_fixed_half_reader import INTERVAL, Dec4FixedHalfForecast
from thericher_v2.ops.h3_fixed_half_block_readout import BLOCK_RELEASE_AT
from thericher_v2.ops.h3_fixed_half_slot_evaluate import evaluate_dec4_fixed_half_slot
from thericher_v2.research.prospective_h3_marks import (
    ProspectiveH3Marks,
    project_prospective_h3_marks,
)
from thericher_v2.research.prospective_h3_replay import ProspectiveH3Replay
from thericher_v2.research.prospective_h3_target_custody import (
    _digest,
    _document,
    _json,
    _sha,
    _stamp,
)

_SCHEMA = "DEC9_H3_TARGET_CUSTODY_V1"
_META_LIMIT = 16_384
_NATIVE_LIMIT = 1024 * 1024


def _utc(value):
    return type(value) is datetime and value.utcoffset() == timedelta(0)


@dataclass(frozen=True)
class Dec9TargetPins:
    """Evaluation prebind retained independently before the Dec4 US open."""

    owner: str
    source_sha256: str
    attempt_sha256: str
    data_root: Path
    market_root: Path
    prebound_at: datetime
    capture_opens: datetime
    capture_closes: datetime
    seal_before: datetime
    release_at: datetime = BLOCK_RELEASE_AT

    @property
    def prebind_sha256(self) -> str:
        return self._prebind(H3DailyPanelPlan(NET25_H3_AXIS, INTERVAL.expiry))

    def _prebind(self, plan):
        if not (
            type(self.owner) is str
            and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", self.owner)
            and all(_digest(value) for value in (self.source_sha256, self.attempt_sha256))
        ):
            raise ValueError("dec9_target_pins")
        a, b = self.data_root, self.market_root
        if (
            any(not p.is_absolute() or p == p.parent or ".." in p.parts for p in (a, b))
            or a.is_relative_to(b)
            or b.is_relative_to(a)
        ):
            raise ValueError("dec9_target_roots")
        clocks = (
            self.prebound_at,
            self.capture_opens,
            self.capture_closes,
            self.seal_before,
            self.release_at,
        )
        close = plan.as_of_close_utc
        if not (
            all(map(_utc, clocks))
            and self.prebound_at
            < ENTRY_OPEN
            < close
            < self.capture_opens
            < self.capture_closes
            < self.seal_before
            < close.replace(hour=0) + timedelta(days=1)
            and self.release_at >= BLOCK_RELEASE_AT
        ):
            raise ValueError("dec9_target_pin_clock")
        return _sha(
            _json(
                dict(
                    schema=_SCHEMA,
                    cohort=[day.isoformat() for day in INTERVAL],
                    owner=self.owner,
                    source=self.source_sha256,
                    attempt=self.attempt_sha256,
                    data_root=str(a),
                    market_root=str(b),
                    queries=[query.document() for query in plan.queries],
                    prebound_at=self.prebound_at.isoformat(),
                    capture_opens=self.capture_opens.isoformat(),
                    capture_closes=self.capture_closes.isoformat(),
                    seal_before=self.seal_before.isoformat(),
                    release_at=self.release_at.isoformat(),
                )
            )
        )


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _fingerprint(path, *, directory=False):
    if _safe_path(path) != path:
        raise ValueError("dec9_target_path")
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or (not directory and info.st_nlink != 1):
        raise ValueError("dec9_target_path")
    return _identity(info)


def _bounded_read(path, limit, expected_identity):
    if not 0 < expected_identity[2] <= limit:
        raise ValueError("dec9_target_size")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ValueError("dec9_target_path")
        if _identity(opened) != expected_identity:
            raise ValueError("dec9_target_member_changed")
        raw = stream.read(limit + 1)
        if len(raw) != expected_identity[2]:
            raise ValueError("dec9_target_member_changed")
    if _fingerprint(path) != expected_identity:
        raise ValueError("dec9_target_member_changed")
    return raw


def _record(raw, *keys):
    doc = _document(raw)
    if doc.keys() != set(keys) or _json(doc) != raw:
        raise ValueError("dec9_target_record")
    return doc


def _ticks(stamp):
    delta = stamp - datetime(1601, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def _capture_members(raw, pins, plan, started, captured):
    state = _document(raw)
    contract, completed = state.get("contract"), state.get("completed")
    if not (
        state.get("version") == "kis-paper-data-capture-v1"
        and type(contract) is dict
        and contract.get("market_root") == str(pins.market_root)
        and contract.get("artifact_root") == str(pins.data_root / "run/capture")
        and _json(contract.get("queries")) == _json([query.document() for query in plan.queries])
        and all(
            type(state.get(k)) is int and state[k] == n
            for k, n in (("GET", 19), ("POST", 1), ("retry", 0))
        )
        and "pending" in state
        and state["pending"] is None
        and state.get("failed_attempts") == []
        and started <= _stamp(state.get("started_utc")) <= captured
        and type(completed) is dict
        and completed.keys() == {query.key for query in plan.queries}
    ):
        raise ValueError("dec9_target_capture_contract")
    members = []
    for ordinal, query in enumerate(plan.queries, 1):
        item = completed[query.key]
        ref = item.get("native") if type(item) is dict else None
        path = pins.market_root / f"GET-{ordinal:06d}.native.json"
        if not (
            type(ref) is dict
            and ref.keys() == {"path", "sha256"}
            and ref["path"] == str(path)
            and _digest(ref["sha256"])
            and item.get("query_key") == query.key
            and item.get("status") == "ACCEPTED"
            and item.get("cache_hit") is False
            and item.get("reason") is None
            and type(item.get("row_count")) is int
            and len(plan.sessions) <= item["row_count"] <= len(plan.capture_sessions)
        ):
            raise ValueError("dec9_target_capture_member")
        members.append(
            (path, CaptureResult(query.key, "ACCEPTED", row_count=item["row_count"], native=ref))
        )
    return members


def read_dec9_fixed_half_target(
    pins: Dec9TargetPins,
    *,
    prebind_sha256: str,
    data_owner_sha256: str,
    data_owner_closed: Callable[[int, str, str], bool],
    reader_ready: Callable[[], bool],
    clock: Callable[[], datetime],
) -> ProspectiveH3Marks:
    """Return only OPEN4/CLOSE3 for the original Dec9 capture, or withhold.

    The launcher supplies independently retained pins, exact process-tree
    closure, and an outcome-free probe of one-shot authority, source, read-only
    isolation and no active/unknown custody writer. None can be inferred from
    local files. This reader never opens wire bodies, forecasts or feature input.
    """
    if (
        type(pins) is not Dec9TargetPins
        or not _utc(pins.release_at)
        or not all(_digest(value) for value in (prebind_sha256, data_owner_sha256))
    ):
        raise ValueError("dec9_target_binding")
    last = max(BLOCK_RELEASE_AT, pins.release_at)

    def time_check():
        nonlocal last
        now = clock()
        if not _utc(now) or now < last:
            raise ValueError("dec9_target_read_denied")
        last = now

    def gate():
        time_check()
        if reader_ready() is not True:
            raise ValueError("dec9_target_read_denied")
        time_check()

    gate()
    plan = H3DailyPanelPlan(NET25_H3_AXIS, INTERVAL.expiry)
    if pins._prebind(plan) != prebind_sha256:
        raise ValueError("dec9_target_prebind")
    data = pins.data_root
    run = data / "run"
    capture, owner, target = (run / name for name in ("capture", "owner", "target"))
    observed = {}

    def read(path, digest, limit=_META_LIMIT):
        gate()
        if not _digest(digest):
            raise ValueError("dec9_target_member_digest")
        fp = _fingerprint(path)
        raw = _bounded_read(path, limit, fp)
        if _sha(raw) != digest:
            raise ValueError("dec9_target_member_digest")
        if observed.setdefault(path, (digest, limit, fp)) != (digest, limit, fp):
            raise ValueError("dec9_target_member_changed")
        return raw

    def membership():
        gate()
        roots = (pins.market_root, capture, owner, target)
        result = []
        for root in roots:
            before = _fingerprint(root, directory=True)
            with os.scandir(root) as entries:
                names = frozenset(entry.name for entry in islice(entries, 129))
            if len(names) > 128 or _fingerprint(root, directory=True) != before:
                raise ValueError("dec9_target_membership")
            result.append((before, names))
        if (
            "owner.lock.d" in result[0][1]
            or {name for name in result[0][1] if name.endswith(".native.json")}
            != {f"GET-{i:06d}.native.json" for i in range(1, len(plan.queries) + 1)}
            or result[1][1] != {"capture-state.json"}
            or result[2][1] != {"ATTEMPT.json", "TARGET-PIN.json"}
            or result[3][1] != {"TARGET-CUSTODY.json"}
        ):
            raise ValueError("dec9_target_membership")
        return result

    try:
        read(data / "source/SOURCE.json", pins.source_sha256, _NATIVE_LIMIT)
        closure = _record(
            read(run / "OWNER-CLOSED.json", data_owner_sha256),
            "schema",
            "source_sha256",
            "attempt_sha256",
            "native_start",
            "closed_at",
            "target_status",
            "target_custody_sha256",
        )
        if (
            closure["schema"] != "H3_DEC9_OWNER_CLOSED_V1"
            or closure["source_sha256"] != pins.source_sha256
            or closure["target_status"] != "pinned"
            or not _digest(closure["target_custody_sha256"])
        ):
            raise ValueError("dec9_target_owner")
        attempt = _record(
            read(owner / "ATTEMPT.json", closure["attempt_sha256"]),
            "schema",
            "owner",
            "launch_attempt_sha256",
            "source_sha256",
            "target_prebind_sha256",
            "started_at",
            "pid",
            "synthetic",
            "roots",
        )
        started, closed = _stamp(attempt["started_at"]), _stamp(closure["closed_at"])
        pid, birth = attempt["pid"], closure["native_start"]
        if not (
            attempt["schema"] == "H3_DEC9_DATA_ATTEMPT_V1"
            and attempt["owner"] == pins.owner
            and attempt["launch_attempt_sha256"] == pins.attempt_sha256
            and attempt["source_sha256"] == pins.source_sha256
            and attempt["target_prebind_sha256"] == prebind_sha256
            and attempt["synthetic"] is False
            and attempt["roots"] == [str(p) for p in (pins.market_root, capture, target, owner)]
            and pins.capture_opens <= started < pins.capture_closes
            and started <= closed < pins.seal_before
            and type(pid) is int
            and 0 < pid < 2**32
            and type(birth) is str
            and re.fullmatch(r"win-filetime:[0-9]{18}", birth)
            and _ticks(pins.capture_opens) <= int(birth.split(":")[1]) <= _ticks(started)
        ):
            raise ValueError("dec9_target_attempt")
        gate()
        if data_owner_closed(pid, birth, data_owner_sha256) is not True:
            raise ValueError("dec9_target_owner_not_closed")
        before = membership()
        seal = _record(
            read(target / "TARGET-CUSTODY.json", closure["target_custody_sha256"]),
            "schema",
            "cohort",
            "prebind_sha256",
            "capture_state_sha256",
            "capture_closed_at",
            "sealed_at",
        )
        captured, sealed = _stamp(seal["capture_closed_at"]), _stamp(seal["sealed_at"])
        if not (
            seal["schema"] == _SCHEMA
            and seal["cohort"] == [day.isoformat() for day in INTERVAL]
            and seal["prebind_sha256"] == prebind_sha256
            and started <= captured < pins.capture_closes
            and captured <= sealed <= closed
        ):
            raise ValueError("dec9_target_custody")
        pin = _json(
            dict(
                schema="H3_DEC9_TARGET_PIN_V1",
                attempt_record_sha256=closure["attempt_sha256"],
                prebind_sha256=prebind_sha256,
                capture_state_sha256=seal["capture_state_sha256"],
                capture_closed_at=seal["capture_closed_at"],
                target_custody_sha256=closure["target_custody_sha256"],
            )
        )
        read(owner / "TARGET-PIN.json", _sha(pin))
        raw = read(capture / "capture-state.json", seal["capture_state_sha256"], _NATIVE_LIMIT)
        members = _capture_members(raw, pins, plan, started, captured)
        panel = qualify_h3_daily_panel(
            plan,
            ((item, read(path, item.native["sha256"], _NATIVE_LIMIT)) for path, item in members),
        )
        marks = project_prospective_h3_marks(panel, INTERVAL)
        for path, (digest, limit, _) in observed.items():
            read(path, digest, limit)
        if membership() != before:
            raise ValueError("dec9_target_membership")
        gate()
        return marks
    except OSError:
        raise ValueError("dec9_target_unreadable") from None


def evaluate_dec4_with_dec9_target(
    forecast: Dec4FixedHalfForecast,
    pins: Dec9TargetPins,
    *,
    prebind_sha256: str,
    data_owner_sha256: str,
    data_owner_closed: Callable[[int, str, str], bool],
    reader_ready: Callable[[], bool],
    clock: Callable[[], datetime],
) -> ProspectiveH3Replay:
    """Join an independently admitted Dec4 forecast to this exact target reader."""
    if type(forecast) is not Dec4FixedHalfForecast or forecast.interval != INTERVAL:
        raise ValueError("dec9_target_forecast")
    marks = read_dec9_fixed_half_target(
        pins,
        prebind_sha256=prebind_sha256,
        data_owner_sha256=data_owner_sha256,
        data_owner_closed=data_owner_closed,
        reader_ready=reader_ready,
        clock=clock,
    )
    return evaluate_dec4_fixed_half_slot(forecast, marks)
