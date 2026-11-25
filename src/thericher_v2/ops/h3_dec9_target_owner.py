"""Run the prebound Dec9 Data owner for the fixed-half slot's target reader."""

from collections.abc import Callable
from datetime import datetime

from thericher_v2.data.kis_paper_h3_capture import (
    H3DailyCapture,
    capture_h3_daily_panel_once,
)
from thericher_v2.data.kis_paper_h3_daily_panel import H3DailyPanelPlan
from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness
from thericher_v2.ops.h3_dec9_fixed_half_capture import write_dec9_fixed_half_capture
from thericher_v2.ops.h3_dec9_fixed_half_target import Dec9TargetPins, _utc


def run_dec9_target_owner(
    pins: Dec9TargetPins,
    *,
    prebind_sha256: str,
    clock: Callable[[], datetime],
    owner_ready: Callable[[], CaptureReadiness],
    config_loader: Callable[[], KisPaperMarketDataConfig],
    monotonic: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> str:
    """Return only the original owner-close digest for the sealed target.

    The caller supplies the independently retained prebind digest, prebound
    native owner probe and exact deferred Paper market-data config loader.
    The probe must attest source, delegated process and isolated roots/ACLs
    before attempt creation, at native effects and through sealing. It must
    work before ATTEMPT exists and after the capture window; the two existing
    primitives enforce their own distinct deadlines.

    This entry does not bootstrap a source, retry, or establish process exit.
    The reader still requires independent positive process-tree closure.
    """
    if not all(callable(fn) for fn in (clock, owner_ready, config_loader)):
        raise ValueError("dec9_owner_pinned_callables_required")

    def seal_ready() -> bool:
        fact = owner_ready()
        return type(fact) is CaptureReadiness and fact.ready is True

    def load_config() -> KisPaperMarketDataConfig:
        if not seal_ready():
            raise ValueError("dec9_owner_config_denied")
        now = clock()
        if not _utc(now) or not pins.capture_opens <= now < pins.capture_closes:
            raise ValueError("dec9_owner_config_denied")
        return config_loader()

    def capture_once(plan: H3DailyPanelPlan) -> H3DailyCapture:
        return capture_h3_daily_panel_once(
            plan=plan,
            market_root=pins.market_root,
            artifact_root=pins.data_root / "run/capture",
            window_opens_utc=pins.capture_opens,
            window_closes_utc=pins.capture_closes,
            clock=clock,
            owner_ready=owner_ready,
            config_loader=load_config,
            monotonic=monotonic,
            sleeper=sleeper,
        )

    return write_dec9_fixed_half_capture(
        pins,
        prebind_sha256=prebind_sha256,
        capture_once=capture_once,
        owner_ready=seal_ready,
        clock=clock,
    )
