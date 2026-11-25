"""Produce the fresh Dec 3 daily panel input consumed by Dec 4 H3 inference."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from thericher_v2.data.kis_paper_h3_capture import (
    _is_utc,
    _read_native,
    capture_h3_daily_panel_once,
)
from thericher_v2.data.kis_paper_h3_daily_panel import (
    DEC3_AS_OF,
    NET25_H3_AXIS,
    H3DailyPanelPlan,
)
from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness, _safe_path
from thericher_v2.models.h3_publisher_input import H3InputBinding, write_h3_publisher_input

CAPTURE_OPENS_UTC = datetime(2026, 12, 3, 21, 30, tzinfo=UTC)
CAPTURE_CLOSES_UTC = datetime(2026, 12, 3, 21, 40, tzinfo=UTC)
INPUT_HARD_STOP_UTC = datetime(2026, 12, 3, 21, 45, tzinfo=UTC)
DECISION_UTC = datetime(2026, 12, 4, 14, 25, tzinfo=UTC)


@dataclass(frozen=True)
class H3ProducedInput:
    input_root: Path
    capture_state_path: Path
    binding: H3InputBinding
    ready_sha256: str


def produce_dec3_h3_publisher_input_once(
    *,
    market_root: Path,
    artifact_root: Path,
    input_root: Path,
    data_source_sha256: str,
    synthetic: bool,
    clock: Callable[[], datetime],
    owner_ready: Callable[[], CaptureReadiness],
    config_loader: Callable[[], KisPaperMarketDataConfig],
    prefix_features: Callable[..., tuple[np.ndarray, np.ndarray]],
    parse_input: Callable[..., tuple[dict, dict]],
    monotonic: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> H3ProducedInput:
    """Run the dated capture and return exact pins for the H3 input reader.

    The launcher must separately pin the current source, owned roots, runtime
    clock, owner probe, Paper config loader, feature kernel and consumer parser.
    Argument presence is not attestation. There is no default owner, credential
    lookup, historical DataREADY fallback or retry of an interrupted directory.
    """
    binding = H3InputBinding(data_source_sha256, DECISION_UTC, INPUT_HARD_STOP_UTC, synthetic)
    if not all(
        callable(fn) for fn in (clock, owner_ready, config_loader, prefix_features, parse_input)
    ):
        raise ValueError("h3_producer_pinned_callables_required")

    now = clock()
    if not _is_utc(now) or not CAPTURE_OPENS_UTC <= now < CAPTURE_CLOSES_UTC:
        raise ValueError("h3_producer_outside_capture_window")

    roots = (market_root, artifact_root, input_root)
    if any(not root.is_absolute() or _safe_path(root) != root or root.exists() for root in roots):
        raise ValueError("h3_producer_fresh_roots_required")
    if any(a.is_relative_to(b) for i, a in enumerate(roots) for j, b in enumerate(roots) if i != j):
        raise ValueError("h3_producer_roots_overlap")
    if not input_root.parent.is_dir():
        raise ValueError("h3_producer_input_parent_required")

    plan = H3DailyPanelPlan(NET25_H3_AXIS, DEC3_AS_OF)
    capture = capture_h3_daily_panel_once(
        plan=plan,
        market_root=market_root,
        artifact_root=artifact_root,
        window_opens_utc=CAPTURE_OPENS_UTC,
        window_closes_utc=CAPTURE_CLOSES_UTC,
        clock=clock,
        owner_ready=owner_ready,
        config_loader=config_loader,
        monotonic=monotonic,
        sleeper=sleeper,
    )
    state_path = artifact_root / "capture-state.json"

    def require_closed_state() -> None:
        raw = _read_native(artifact_root, str(state_path))
        if hashlib.sha256(raw).hexdigest() != capture.state_sha256:
            raise ValueError("h3_producer_capture_state_changed")

    def parse_with_custody(root: Path, **pins) -> tuple[dict, dict]:
        parsed = parse_input(root, **pins)
        require_closed_state()
        return parsed

    require_closed_state()
    ready_sha = write_h3_publisher_input(
        input_root,
        capture,
        binding=binding,
        clock=clock,
        prefix_features=prefix_features,
        parse_input=parse_with_custody,
    )
    require_closed_state()
    now = clock()
    if not _is_utc(now) or not capture.closed_at <= now < INPUT_HARD_STOP_UTC:
        raise ValueError("h3_producer_outside_input_window")
    return H3ProducedInput(input_root, state_path, binding, ready_sha)
