"""Run a fresh, finite post-close capture for the strict H3 daily panel."""

import hashlib
import os
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanel,
    H3DailyPanelError,
    H3DailyPanelPlan,
    qualify_h3_daily_panel,
)
from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_paper_data_capture import (
    CaptureLimits,
    CaptureReadiness,
    KisPaperDataCaptureSession,
    _safe_path,
)


def _is_utc(value: object) -> bool:
    return isinstance(value, datetime) and value.utcoffset() == timedelta(0)


@dataclass(frozen=True)
class H3DailyCapture:
    panel: H3DailyPanel
    state_sha256: str
    closed_at: datetime


def _read_native(root: Path, reference: str) -> bytes:
    path = Path(reference)
    if not path.is_absolute() or path.parent != root or _safe_path(path) != path:
        raise H3DailyPanelError("h3_capture_native_outside_scope")
    try:
        before = path.stat()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            data = stream.read()
        _safe_path(path)
        after = path.stat()
    except OSError:
        raise H3DailyPanelError("h3_capture_native_unreadable") from None
    if (
        len({(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns) for s in (before, opened, after)}) != 1
        or len(data) != before.st_size
    ):
        raise H3DailyPanelError("h3_capture_native_unstable")
    return data


def _mkdir_private(path: Path) -> None:
    # CPython 3.13+ applies a protected, inheritable DACL at creation on Windows.
    if os.name == "nt" and sys.version_info < (3, 13):
        raise H3DailyPanelError("h3_capture_private_mkdir_unsupported")
    path.mkdir(mode=0o700)


def _private_root_identity(root: Path) -> tuple[int, int]:
    """Sample a plain directory name; this is not creator proof."""
    if _safe_path(root) != root:
        raise H3DailyPanelError("h3_capture_private_scope")
    current = root.stat(follow_symlinks=False)
    if not stat.S_ISDIR(current.st_mode) or getattr(current, "st_file_attributes", 0) & 0x400:
        raise H3DailyPanelError("h3_capture_private_scope")
    return current.st_dev, current.st_ino


def capture_h3_daily_panel_once(
    *,
    plan: H3DailyPanelPlan,
    market_root: Path,
    artifact_root: Path,
    window_opens_utc: datetime,
    window_closes_utc: datetime,
    clock: Callable[[], datetime],
    owner_ready: Callable[[], CaptureReadiness],
    config_loader: Callable[[], KisPaperMarketDataConfig],
    monotonic: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
    private_roots: bool = False,
    create_private_root: Callable[[Path], bool] | None = None,
) -> H3DailyCapture:
    """Return a qualified panel after successful session closure, not a publication seal.

    The caller pins the future window, roots and current owner probe. No resume,
    retry, reconciliation, credential fallback or schedule action is performed.
    A supplied creator owns each exclusive creation and its custody checks.
    Path identity checks only detect drift.
    """
    if type(private_roots) is not bool:
        raise H3DailyPanelError("h3_capture_private_scope")
    if create_private_root is not None and (not private_roots or not callable(create_private_root)):
        raise H3DailyPanelError("h3_capture_root_registration")
    opens, closes = window_opens_utc, window_closes_utc
    if type(plan) is not H3DailyPanelPlan or plan.axis != NET25_H3_AXIS:
        raise H3DailyPanelError("h3_capture_axis_refused")
    close = plan.as_of_close_utc
    if not (
        _is_utc(opens)
        and _is_utc(closes)
        and close < opens < closes
        and close.date() == opens.date() == closes.date()
    ):
        raise H3DailyPanelError("h3_capture_window_invalid")

    def now_in_window() -> datetime:
        now = clock()
        if not _is_utc(now) or not opens <= now < closes:
            raise H3DailyPanelError("h3_capture_outside_window")
        return now

    remaining = (closes - now_in_window()).total_seconds()
    roots = (market_root, artifact_root)
    for root in roots:
        if not root.is_absolute() or _safe_path(root) != root or root.exists():
            raise H3DailyPanelError("h3_capture_fresh_scope_required")

    created: dict[Path, tuple[int, int]] = {}

    def gated_ready() -> CaptureReadiness:
        now_in_window()
        fact = owner_ready()
        if any(_private_root_identity(path) != identity for path, identity in created.items()):
            raise H3DailyPanelError("h3_capture_private_scope_changed")
        now_in_window()
        return fact

    def require_ready() -> None:
        ready = gated_ready()
        if type(ready) is not CaptureReadiness or ready.ready is not True:
            raise H3DailyPanelError("h3_capture_private_scope")

    if private_roots:
        if (
            roots[0].is_relative_to(roots[1])
            or roots[1].is_relative_to(roots[0])
            or not all(root.parent.is_dir() for root in roots)
        ):
            raise H3DailyPanelError("h3_capture_private_scope")
        for root in roots:
            ready = gated_ready()
            if type(ready) is not CaptureReadiness or not ready.ready or _safe_path(root) != root:
                raise H3DailyPanelError("h3_capture_private_scope")
            if create_private_root is None:
                _mkdir_private(root)
            elif create_private_root(root) is not True:
                raise H3DailyPanelError("h3_capture_root_registration")
            created[root] = _private_root_identity(root)

    timing = {k: v for k, v in (("monotonic", monotonic), ("sleeper", sleeper)) if v is not None}
    if create_private_root is not None:
        # Session entry creates custody locks before the session uses owner_ready.
        require_ready()
    with KisPaperDataCaptureSession(
        queries=plan.queries,
        market_root=market_root,
        artifact_root=artifact_root,
        limits=CaptureLimits(max_get=19, max_retries=0, wall_seconds=remaining, max_auth=1),
        clock=clock,
        owner_ready=gated_ready,
        config_loader=config_loader,
        **timing,
    ) as session:
        progress = session.progress
        if progress["GET"] or progress["POST"] or progress["completed"]:
            raise H3DailyPanelError("h3_capture_fresh_scope_required")
        captures = []
        for query in plan.queries:
            now_in_window()
            result = session.capture(query)
            if result.cache_hit or result.status != "ACCEPTED" or result.native is None:
                raise H3DailyPanelError("h3_capture_page_unavailable")
            captures.append((result, _read_native(session.market_root, result.native["path"])))
        panel = qualify_h3_daily_panel(plan, captures)
        progress = session.progress
        if (progress["GET"], progress["POST"], progress["retry"], progress["pending"]) != (
            19,
            1,
            0,
            None,
        ):
            raise H3DailyPanelError("h3_capture_counters_mismatch")
        state_path = session.artifact_root / "capture-state.json"
        state = _read_native(session.artifact_root, str(state_path))
    if create_private_root is not None and any(
        _private_root_identity(path) != identity for path, identity in created.items()
    ):
        raise H3DailyPanelError("h3_capture_private_scope_changed")
    if _read_native(artifact_root, str(state_path)) != state:
        raise H3DailyPanelError("h3_capture_state_changed_on_close")
    return H3DailyCapture(panel, hashlib.sha256(state).hexdigest(), now_in_window())
