"""Bridge the named Dec3 DATA owner to the independent Dec4 shadow POINT owner."""

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path

from thericher_v2.data.kis_paper_h3_capture import _is_utc, _read_native
from thericher_v2.data.kis_paper_h3_producer import (
    CAPTURE_OPENS_UTC,
    DECISION_UTC,
    INPUT_HARD_STOP_UTC,
    produce_dec3_h3_publisher_input_once,
)
from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness, _safe_path
from thericher_v2.models.h3_publisher_input import H3InputBinding
from thericher_v2.models.h3_shadow_point import publish_dec4_h3_shadow_point

_RECEIPT = "DATA-READY.json"
_PENDING = "DATA-READY.pending"


@dataclass(frozen=True)
class Dec4H3Run:
    """Exact shared pins; the caller attests source/callbacks and owns these paths.

    The receipt is a local owned handoff, not authentication against another
    writer with access to the roots. Both callers must pin this same run plan.
    """

    market_root: Path
    artifact_root: Path
    input_root: Path
    point_root: Path
    data_source_sha256: str
    synthetic: bool

    def _preflight(self, *, data: bool) -> H3InputBinding:
        roots = (self.market_root, self.artifact_root, self.input_root, self.point_root)
        if any(not p.is_absolute() or _safe_path(p) != p for p in roots):
            raise ValueError("h3_run_invalid_root")
        if any(a.is_relative_to(b) or b.is_relative_to(a) for a, b in combinations(roots, 2)):
            raise ValueError("h3_run_overlapping_roots")
        if any(p.exists() for p in (roots if data else (self.point_root,))):
            raise FileExistsError("h3_run_consumed_root")
        if not self.point_root.parent.is_dir():
            raise ValueError("h3_run_point_parent_required")
        return H3InputBinding(
            self.data_source_sha256, DECISION_UTC, INPUT_HARD_STOP_UTC, self.synthetic
        )

    def _receipt(self, ready_sha256: str) -> bytes:
        if not isinstance(ready_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", ready_sha256):
            raise ValueError("h3_run_invalid_ready_digest")
        return json.dumps(
            dict(
                schema="DEC3_H3_DATA_READY_V1",
                market_root=str(self.market_root),
                artifact_root=str(self.artifact_root),
                input_root=str(self.input_root),
                point_root=str(self.point_root),
                source_sha256=self.data_source_sha256,
                synthetic=self.synthetic,
                ready_sha256=ready_sha256,
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")


def run_dec3_data(
    run: Dec4H3Run,
    *,
    clock: Callable[[], datetime],
    owner_ready: Callable[[], CaptureReadiness],
    config_loader: Callable[[], KisPaperMarketDataConfig],
    prefix_features: Callable,
    parse_input: Callable,
    on_capture_closed: Callable[[str, datetime], None] | None = None,
    monotonic: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> str:
    """Persist the native READY digest only after DATA returns successfully."""
    binding = run._preflight(data=True)
    produced = produce_dec3_h3_publisher_input_once(
        market_root=run.market_root,
        artifact_root=run.artifact_root,
        input_root=run.input_root,
        data_source_sha256=run.data_source_sha256,
        synthetic=run.synthetic,
        clock=clock,
        owner_ready=owner_ready,
        config_loader=config_loader,
        prefix_features=prefix_features,
        parse_input=parse_input,
        on_capture_closed=on_capture_closed,
        monotonic=monotonic,
        sleeper=sleeper,
    )
    if (
        produced.input_root != run.input_root
        or produced.capture_state_path != run.artifact_root / "capture-state.json"
        or produced.binding != binding
    ):
        raise ValueError("h3_run_producer_binding_mismatch")
    digest = produced.ready_sha256
    raw = run._receipt(digest)
    ready = _read_native(run.input_root, str(run.input_root / "READY.json"))
    if hashlib.sha256(ready).hexdigest() != digest:
        raise ValueError("h3_run_ready_digest_mismatch")

    pending = run.input_root / _PENDING
    receipt = run.input_root / _RECEIPT
    with pending.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if receipt.exists() or _safe_path(receipt) != receipt:
        raise FileExistsError("h3_run_receipt_exists")
    now = clock()
    if not _is_utc(now) or not CAPTURE_OPENS_UTC <= now < INPUT_HARD_STOP_UTC:
        raise ValueError("h3_run_receipt_clock_denied")
    pending.rename(receipt)
    return digest


def run_dec4_point(
    run: Dec4H3Run,
    *,
    clock: Callable[[], datetime],
    owner_ready: Callable[[], bool],
    validate_input: Callable,
    model_source: bytes,
    stats: bytes,
    weights: bytes,
) -> str:
    """Publish one shadow point; no DATA retry, credentials or financial effects."""
    if owner_ready() is not True:
        raise ValueError("h3_run_point_owner_denied")
    binding = run._preflight(data=False)
    if (run.input_root / _PENDING).exists():
        raise ValueError("h3_run_receipt_pending")
    raw = _read_native(run.input_root, str(run.input_root / _RECEIPT))
    receipt = json.loads(raw)
    if not isinstance(receipt, dict) or raw != run._receipt(receipt.get("ready_sha256")):
        raise ValueError("h3_run_receipt_binding_mismatch")
    return publish_dec4_h3_shadow_point(
        run.point_root,
        input_root=run.input_root,
        capture_state_path=run.artifact_root / "capture-state.json",
        binding=binding,
        ready_sha256=receipt["ready_sha256"],
        clock=clock,
        validate_input=validate_input,
        model_source=model_source,
        stats=stats,
        weights=weights,
    )
