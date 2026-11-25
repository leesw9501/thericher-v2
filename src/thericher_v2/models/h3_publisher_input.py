"""Exact handoff from a closed H3 capture to the existing H123 publisher."""

import hashlib
import io
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from thericher_v2.data.kis_paper_h3_capture import H3DailyCapture, _read_native
from thericher_v2.execution.kis_paper_data_capture import _safe_path
from thericher_v2.models.h3_h123_input import write_h3_h123_input


def _utc(at):
    return isinstance(at, datetime) and at.utcoffset() == timedelta(0)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class H3InputBinding:
    source_sha256: str
    decision_at: datetime
    hard_stop: datetime
    synthetic: bool

    def __post_init__(self):
        if (
            re.fullmatch(r"[0-9a-f]{64}", self.source_sha256) is None
            or not _utc(self.decision_at)
            or not _utc(self.hard_stop)
            or not self.hard_stop < self.decision_at
            or type(self.synthetic) is not bool
        ):
            raise ValueError("h3_publisher_invalid_binding")


def write_h3_publisher_input(
    destination: Path,
    capture: H3DailyCapture,
    *,
    binding: H3InputBinding,
    clock: Callable[[], datetime],
    prefix_features: Callable,
    parse_input: Callable,
) -> str:
    """Use one fresh output directory and publish READY after real parser readback."""
    close = capture.closed_at

    def checked_clock():
        now = clock()
        if not (
            _utc(now)
            and _utc(close)
            and capture.panel.plan.as_of_close_utc < close <= now < binding.hard_stop
            and close.date() == binding.hard_stop.date() == capture.panel.plan.as_of
        ):
            raise ValueError("h3_publisher_outside_window")
        return now

    checked_clock()
    if re.fullmatch(r"[0-9a-f]{64}", capture.state_sha256) is None:
        raise ValueError("h3_publisher_invalid_capture")
    payload_sha = write_h3_h123_input(
        destination,
        capture.panel,
        data_source_sha256=binding.source_sha256,
        decision_at=binding.decision_at,
        synthetic=binding.synthetic,
        prefix_features=prefix_features,
        parse_input=parse_input,
    )
    header_sha = _digest(_read_native(destination, str(destination / "INPUT.json")))
    if payload_sha != _digest(_read_native(destination, str(destination / "INPUT.npz"))):
        raise ValueError("h3_publisher_payload_changed")
    ready = dict(
        schema="H3_PUBLISHER_INPUT_READY_V1",
        source_sha256=binding.source_sha256,
        synthetic=binding.synthetic,
        decision_at=binding.decision_at.isoformat(),
        closed_at=close.isoformat(),
        capture_state_sha256=capture.state_sha256,
        input_header_sha256=header_sha,
        input_payload_sha256=payload_sha,
        ready_at=checked_clock().isoformat(),
    )
    raw = json.dumps(ready, sort_keys=True, separators=(",", ":")).encode("ascii")
    pending = destination / "READY.pending"
    with pending.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    checked_clock()
    pending.rename(destination / "READY.json")
    checked_clock()
    return _digest(raw)


def read_h3_publisher_input(
    root: Path,
    capture_state_path: Path,
    *,
    binding: H3InputBinding,
    ready_sha256: str,
    clock: Callable[[], datetime],
    validate_input: Callable,
) -> tuple[dict, dict]:
    """Read exact READY, then parse the same verified byte buffers for inference.

    The caller pins both roots and the READY digest from the current owned run;
    this is not permission to infer from the latest directory or prove finality.
    """
    if not root.is_absolute() or _safe_path(root) != root:
        raise ValueError("h3_publisher_root_invalid")
    raw = _read_native(root, str(root / "READY.json"))
    if _digest(raw) != ready_sha256:
        raise ValueError("h3_publisher_ready_digest_mismatch")
    ready = json.loads(raw)
    if (
        ready["schema"] != "H3_PUBLISHER_INPUT_READY_V1"
        or ready["source_sha256"] != binding.source_sha256
        or ready["synthetic"] is not binding.synthetic
        or ready["decision_at"] != binding.decision_at.isoformat()
    ):
        raise ValueError("h3_publisher_ready_binding_mismatch")
    closed, recorded = (datetime.fromisoformat(ready[field]) for field in ("closed_at", "ready_at"))
    if not (
        _utc(closed)
        and _utc(recorded)
        and closed <= recorded < binding.hard_stop
        and closed.date() == binding.hard_stop.date()
    ):
        raise ValueError("h3_publisher_ready_clock_mismatch")

    def read_clock():
        now = clock()
        if not _utc(now) or not recorded <= now < binding.decision_at:
            raise ValueError("h3_publisher_read_clock_mismatch")

    def member(key, path):
        data = _read_native(path.parent, str(path))
        if _digest(data) != ready[key]:
            raise ValueError("h3_publisher_member_digest_mismatch")
        return data

    read_clock()
    member("capture_state_sha256", capture_state_path)
    header = json.loads(member("input_header_sha256", root / "INPUT.json"))
    payload = member("input_payload_sha256", root / "INPUT.npz")
    if header["payload_sha256"] != ready["input_payload_sha256"]:
        raise ValueError("h3_publisher_header_payload_mismatch")
    with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
        arrays = dict(archive)
    day = binding.decision_at.strftime("%Y%m%d")
    validate_input(
        arrays,
        header,
        expected_source=binding.source_sha256,
        role=f"FUTURE_{closed:%Y%m%d}_ASOF_{day}",
        expected_keys=[f"{day}|{i:02d}" for i in range(17)],
        synthetic=binding.synthetic,
    )
    read_clock()
    return arrays, header
