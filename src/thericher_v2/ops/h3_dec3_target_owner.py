"""Run one Dec3 Data owner for the Dec4 feature input and Nov30 target custody."""

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Literal

from thericher_v2.data.kis_paper_h3_capture import _is_utc, _read_native
from thericher_v2.data.kis_paper_h3_producer import (
    CAPTURE_CLOSES_UTC,
    CAPTURE_OPENS_UTC,
    INPUT_HARD_STOP_UTC,
)
from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness, _safe_path
from thericher_v2.ops.h3_dec4_run import Dec4H3Run, run_dec3_data
from thericher_v2.research.prospective_h3_target_custody import (
    Nov30H3TargetPins,
    write_nov30_h3_target_custody,
)


@dataclass(frozen=True)
class Dec3TargetOwnerResult:
    ready_sha256: str
    target_custody_sha256: str | None
    target_status: Literal["not_bound", "seal_failed", "pin_failed", "pinned"]


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_once(path: Path, **document: object) -> str:
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
    if _safe_path(path) != path:
        raise ValueError("h3_dec3_owner_unsafe_member")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if _read_native(path.parent, str(path)) != raw:
        raise ValueError("h3_dec3_owner_member_changed")
    return _sha(raw)


def _overlap(roots: tuple[Path, ...]) -> bool:
    return any(a.is_relative_to(b) or b.is_relative_to(a) for a, b in combinations(roots, 2))


def run_dec3_target_owner(
    run: Dec4H3Run,
    *,
    attempt_root: Path,
    target_pins: Nov30H3TargetPins,
    prebind_sha256: str,
    clock: Callable[[], datetime],
    owner_ready: Callable[[], CaptureReadiness],
    config_loader: Callable[[], KisPaperMarketDataConfig],
    prefix_features: Callable,
    parse_input: Callable,
    monotonic: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> Dec3TargetOwnerResult:
    """Invoke the named capture once, with an independent, prebound target branch.

    The launcher attests source, process identity, callbacks, ACLs and the fixed
    attempt path before calling. Pass the separately retained prebind digest,
    not a runtime-generated substitute. The attempt is never reset or resumed.
    The block owner still needs positive external closure of the actual process;
    the pin here proves neither process exit nor permission to open target pages.
    """
    started = clock()
    if not _is_utc(started) or not CAPTURE_OPENS_UTC <= started < CAPTURE_CLOSES_UTC:
        raise ValueError("h3_dec3_owner_start_denied")
    run._preflight(data=True)
    roots = (run.market_root, run.artifact_root, run.input_root, run.point_root, attempt_root)
    if (
        not attempt_root.is_absolute()
        or _safe_path(attempt_root) != attempt_root
        or _overlap(roots)
    ):
        raise ValueError("h3_dec3_owner_attempt_root_invalid")
    # The shared launch name and attempt ID are required even without target admission.
    if (
        type(target_pins.owner) is not str
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", target_pins.owner)
        or type(target_pins.attempt_sha256) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", target_pins.attempt_sha256)
    ):
        raise ValueError("h3_dec3_owner_launch_identity_invalid")
    try:
        target_prebind = target_pins.prebind_sha256
    except ValueError:
        target_prebind = None
    target_bound = (
        target_prebind is not None
        and target_prebind == prebind_sha256
        and target_pins.source_sha256 == run.data_source_sha256
        and target_pins.market_root == run.market_root
        and target_pins.artifact_root == run.artifact_root
        and target_pins.synthetic is run.synthetic
        and not _overlap((*roots, target_pins.target_root))
    )

    attempt_root.mkdir()
    attempt_sha256 = _write_once(
        attempt_root / "ATTEMPT.json",
        schema="H3_DEC3_DATA_ATTEMPT_V1",
        owner=target_pins.owner,
        launch_attempt_sha256=target_pins.attempt_sha256,
        source_sha256=run.data_source_sha256,
        target_prebind_sha256=target_prebind if target_bound else None,
        started_at=started.isoformat(),
        pid=os.getpid(),
        synthetic=run.synthetic,
        roots=[str(root) for root in roots],
    )
    target_status: Literal["not_bound", "seal_failed", "pin_failed", "pinned"] = "not_bound"
    target_digest = None
    capture_reported = False

    def on_capture_closed(state_sha256: str, closed_at: datetime) -> None:
        nonlocal capture_reported, target_status, target_digest
        if capture_reported:
            raise ValueError("h3_dec3_owner_duplicate_capture_close")
        capture_reported = True
        if not target_bound:
            return
        target_status = "seal_failed"
        try:
            if closed_at < started:
                raise ValueError("h3_dec3_owner_capture_clock")
            digest = write_nov30_h3_target_custody(
                target_pins,
                prebind_sha256=prebind_sha256,
                capture_state_sha256=state_sha256,
                capture_closed_at=closed_at,
                clock=clock,
            )
            target_status = "pin_failed"
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("h3_dec3_owner_bad_target_digest")
            pending = attempt_root / "TARGET-PIN.pending"
            final = attempt_root / "TARGET-PIN.json"
            _write_once(
                pending,
                schema="H3_DEC3_TARGET_PIN_V1",
                attempt_record_sha256=attempt_sha256,
                prebind_sha256=prebind_sha256,
                capture_state_sha256=state_sha256,
                capture_closed_at=closed_at.isoformat(),
                target_custody_sha256=digest,
            )
            state = run.artifact_root / "capture-state.json"
            if _sha(_read_native(run.artifact_root, str(state))) != state_sha256:
                raise ValueError("h3_dec3_owner_capture_changed")
            now = clock()
            if not _is_utc(now) or not closed_at <= now < INPUT_HARD_STOP_UTC:
                raise ValueError("h3_dec3_owner_pin_clock")
            if _safe_path(final) != final or final.exists():
                raise FileExistsError("h3_dec3_owner_target_pin_exists")
            pending.rename(final)
        except (OSError, ValueError):
            # The producer independently rechecks shared capture custody and time.
            return
        target_digest = digest
        target_status = "pinned"

    ready = run_dec3_data(
        run,
        clock=clock,
        owner_ready=owner_ready,
        config_loader=config_loader,
        prefix_features=prefix_features,
        parse_input=parse_input,
        on_capture_closed=on_capture_closed,
        monotonic=monotonic,
        sleeper=sleeper,
    )
    return Dec3TargetOwnerResult(ready, target_digest, target_status)
