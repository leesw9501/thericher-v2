"""Fixed development preparation; past inputs never depend on future support."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.intraday_variance_targets import (
    IntradayVarianceTarget,
    build_intraday_variance_target,
)
from thericher_v2.research.paired_completed_context import (
    PairedCompletedContext,
    build_paired_completed_context,
)

SYMBOLS = ("QQQ", "SPY")
MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True, repr=False)
class TargetSupport:
    symbol: str
    status: str
    target: IntradayVarianceTarget | None


@dataclass(frozen=True, slots=True, repr=False)
class VarianceSmokeCase:
    decision_at: datetime
    input_status: str
    context: PairedCompletedContext | None
    targets: tuple[TargetSupport, ...]


def decision_at(session: SessionWindow) -> datetime:
    return min(session.open_ts + 150 * MINUTE, session.close_ts - 10 * MINUTE)


def _exact_support(bars: Sequence[Bar], start: datetime, count: int) -> bool:
    required = tuple(bar for bar in bars if start <= bar.start_ts < start + count * MINUTE)
    return (
        len(required) == count
        and tuple(bar.start_ts for bar in required)
        == tuple(start + index * MINUTE for index in range(count))
        and all(bar.complete is True for bar in required)
    )


def build_variance_smoke_case(
    qqq: Sequence[Bar], spy: Sequence[Bar], *, session: SessionWindow
) -> VarianceSmokeCase:
    """Inspect inputs first, then both targets independently, without filling gaps.

    Expected missing-key/completion/session shortfalls are categorical. Identity,
    value or other unexpected helper failures propagate as contract faults.
    """
    at = decision_at(session)
    context = None
    if at - 120 * MINUTE < session.open_ts:
        input_status = "session_context_shortfall"
    elif not all(_exact_support(stream, at - 120 * MINUTE, 120) for stream in (qqq, spy)):
        input_status = "required_past_m1_shortfall"
    else:
        context = build_paired_completed_context(
            qqq,
            spy,
            own_symbol="QQQ",
            peer_symbol="SPY",
            session=session,
            observed_at=at,
            timeframe=Timeframe.M1,
            context_bars=120,
        )
        input_status = "available"

    targets = []
    for symbol, stream in zip(SYMBOLS, (qqq, spy), strict=True):
        start = at + MINUTE
        if at + 62 * MINUTE > session.close_ts:
            targets.append(TargetSupport(symbol, "session_horizon_shortfall", None))
        elif not _exact_support(stream, start, 61):
            targets.append(TargetSupport(symbol, "required_forward_m1_shortfall", None))
        else:
            target = build_intraday_variance_target(
                stream,
                symbol=symbol,
                session=session,
                decision_at=at,
                observed_at=at + 62 * MINUTE,
                horizon_minutes=60,
            )
            targets.append(TargetSupport(symbol, "available", target))
    return VarianceSmokeCase(at, input_status, context, tuple(targets))
