"""Run a fresh, finite post-close capture for the strict H3 daily panel."""

import os
from collections.abc import Callable
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
) -> H3DailyPanel:
    """Return a qualified panel after successful session closure, not a publication seal.

    The caller pins the future window, roots and current owner probe. No resume,
    retry, reconciliation, credential fallback or schedule action is performed.
    """
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
    for root in (market_root, artifact_root):
        if not root.is_absolute() or _safe_path(root) != root or root.exists():
            raise H3DailyPanelError("h3_capture_fresh_scope_required")

    def gated_ready() -> CaptureReadiness:
        now_in_window()
        fact = owner_ready()
        now_in_window()
        return fact

    timing = {k: v for k, v in (("monotonic", monotonic), ("sleeper", sleeper)) if v is not None}
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
    now_in_window()
    return panel
