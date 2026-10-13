"""Current daily Data receipts to the original pure Paper portfolio recipe.

No credential, broker, private-book, filesystem or schedule access. Archived
readability is independent of this new-intent timing check.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

from thericher_v2.contracts import require_utc
from thericher_v2.data.kis_paper_etf_daily_context import DailyContext
from thericher_v2.research.kis_paper_daily_portfolio_control import (
    SYMBOLS,
    build_capped_thirds_control,
)
from thericher_v2.research.kis_paper_daily_spy_baseline import _next_session_after

RECIPE = "original253-population252-shrink90-10-capped-thirds-vol10-v1"


class CurrentDailyControlUnavailable(ValueError):
    """Only this requested new control is unavailable; not a permission hold."""


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, repr=False)
class CurrentDailyControl:
    input_ref: str
    control_ref: str
    session_date: date
    target_as_of: datetime
    available_at: datetime
    valid_until: datetime
    weights_by_symbol: Mapping[str, Decimal] = field(repr=False)
    covariance_by_symbol: Mapping[str, Mapping[str, Decimal]] = field(repr=False)

    @property
    def session_id(self) -> str:
        return (
            "daily-portfolio-" + self.session_date.strftime("%Y%m%d") + "-" + self.control_ref[7:23]
        )

    def native_arguments(self) -> dict[str, object]:
        return dict(
            session_id=self.session_id,
            input_ref=self.input_ref,
            control_ref=self.control_ref,
            weights_by_symbol=self.weights_by_symbol,
            covariance_by_symbol=self.covariance_by_symbol,
            target_as_of=self.target_as_of,
        )

    def safe_payload(self) -> dict[str, object]:
        return dict(
            kind=RECIPE,
            status="current_input_ready",
            input_ref=self.input_ref,
            control_ref=self.control_ref,
            session_date=self.session_date.isoformat(),
            target_as_of=self.target_as_of.isoformat(),
            available_at=self.available_at.isoformat(),
            valid_until=self.valid_until.isoformat(),
            symbol_count=3,
            closes_per_symbol=253,
            limitation="observed_raw_nonPIT_not_provider_finality_or_execution_permission",
        )


def build_current_daily_control(
    contexts_by_symbol: Mapping[str, DailyContext],
    *,
    as_of: datetime,
) -> CurrentDailyControl:
    """Use exact aligned253 tails; never retimestamp a source or a past decision."""
    at = require_utc(as_of, "as_of")
    if not isinstance(contexts_by_symbol, Mapping) or set(contexts_by_symbol) != set(SYMBOLS):
        raise CurrentDailyControlUnavailable("current_control_instrument_scope")
    contexts = tuple(contexts_by_symbol[symbol] for symbol in SYMBOLS)
    if any(
        type(context) is not DailyContext
        or len(context.observations) != 253
        or context.receipt.symbol != symbol
        or not context.receipt.complete_253
        for symbol, context in zip(SYMBOLS, contexts, strict=True)
    ):
        raise CurrentDailyControlUnavailable("current_control_context_incomplete")
    dates = tuple(observation.provider_date for observation in contexts[0].observations)
    closes = tuple(session.calendar_close_utc for session in contexts[0].receipt.calendar)
    if any(
        tuple(observation.provider_date for observation in context.observations) != dates
        or tuple(session.calendar_close_utc for session in context.receipt.calendar) != closes
        for context in contexts
    ):
        raise CurrentDailyControlUnavailable("current_control_sessions_mismatch")
    available = max(context.receipt.first_available_at_utc for context in contexts)
    target_at = closes[-1]
    session = _next_session_after(dates[-1])
    if session is None:
        raise CurrentDailyControlUnavailable("current_control_calendar_unavailable")
    if not target_at < available < at:
        raise CurrentDailyControlUnavailable("current_control_input_not_available")
    if not session.window.open_ts <= at < session.window.close_ts:
        raise CurrentDailyControlUnavailable("current_control_outside_next_session")
    weights, covariance = build_capped_thirds_control(
        {
            symbol: tuple(bar.close for bar in context.bars)
            for symbol, context in zip(SYMBOLS, contexts, strict=True)
        }
    )
    input_ref = _hash(
        {symbol: context.receipt_sha256 for symbol, context in zip(SYMBOLS, contexts, strict=True)}
    )
    control_ref = _hash(
        dict(
            recipe=RECIPE,
            input_ref=input_ref,
            target_as_of=target_at.isoformat(),
            weights={s: str(value) for s, value in weights.items()},
            covariance={
                s: {t: str(value) for t, value in row.items()} for s, row in covariance.items()
            },
        )
    )
    return CurrentDailyControl(
        input_ref,
        control_ref,
        session.session_date,
        target_at,
        available,
        session.window.close_ts,
        MappingProxyType(weights),
        MappingProxyType({s: MappingProxyType(row) for s, row in covariance.items()}),
    )
