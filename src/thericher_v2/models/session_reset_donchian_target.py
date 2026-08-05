"""Pure SessionResetDonchianRule adaptation into model target state.

This module has no market-provider, broker, scheduling, or order dependency.
Callers supply the completed in-memory bars, one declared session, a UTC
decision time, an explicit long/flat model position, and an explicit target
exposure/confidence/TTL configuration.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

from thericher_v2.contracts import (
    Bar,
    TargetExposureProposal,
    Timeframe,
    decimal_value,
    require_utc,
)
from thericher_v2.market.resample import SessionWindow

from .session_reset_donchian import DonchianPosition, SessionResetDonchianRule

SESSION_RESET_DONCHIAN_TARGET_ADAPTER_ID: Final = "session-reset-donchian-target-v1"
SESSION_RESET_DONCHIAN_TARGET_FEATURE_SCHEMA_ID: Final = "session-reset-donchian-target-v1"
_POSITIONS: Final = frozenset({"flat", "long"})
_ZERO: Final = Decimal("0")


@dataclass(frozen=True, slots=True)
class SessionResetDonchianTargetConfig:
    """Caller-declared target-state geometry for one instrument/timeframe.

    There is deliberately no default exposure, confidence, or TTL. Confidence
    is caller-declared decision metadata: this adapter does not calibrate it or
    make a performance claim. Supplying the fields makes this an adapter
    boundary rather than an automatically active strategy.
    """

    symbol: str
    market: str
    timeframe: Timeframe
    target_exposure: Decimal | int | str
    confidence: Decimal | int | str
    decision_ttl: timedelta

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _identity_text(self.symbol, "symbol"))
        object.__setattr__(self, "market", _identity_text(self.market, "market"))
        try:
            timeframe = Timeframe(self.timeframe)
        except (TypeError, ValueError) as error:
            raise ValueError("timeframe must be a supported Timeframe") from error
        target_exposure = decimal_value(self.target_exposure, "target_exposure")
        if not _ZERO < target_exposure <= Decimal("1"):
            raise ValueError("target_exposure must be greater than zero and at most one")
        confidence = decimal_value(self.confidence, "confidence")
        if not _ZERO < confidence <= Decimal("1"):
            raise ValueError("confidence must be greater than zero and at most one")
        if not isinstance(self.decision_ttl, timedelta) or self.decision_ttl <= timedelta(0):
            raise ValueError("decision_ttl must be a positive timedelta")
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "target_exposure", target_exposure)
        object.__setattr__(self, "confidence", confidence)


def propose_session_reset_donchian_target(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    as_of: datetime,
    model_position: DonchianPosition,
    rule: SessionResetDonchianRule,
    config: SessionResetDonchianTargetConfig,
) -> TargetExposureProposal:
    """Translate one causal Donchian decision into a target exposure proposal.

    An insufficient completed-bar window is a scoped missing-input abstain. A
    valid channel hold remains a target state at the caller-declared model
    position; it is not translated into an order or a new position inference.
    """

    if not isinstance(config, SessionResetDonchianTargetConfig):
        raise TypeError("config must be a SessionResetDonchianTargetConfig")
    if not isinstance(rule, SessionResetDonchianRule):
        raise TypeError("rule must be a SessionResetDonchianRule")
    if model_position not in _POSITIONS:
        raise ValueError("model_position must be flat or long")
    if not isinstance(session, SessionWindow):
        raise TypeError("session must be a SessionWindow")
    now = require_utc(as_of, "as_of")
    source = tuple(bars)
    decision = rule.decide(
        source,
        position=model_position,
        session=session,
        as_of=now,
    )
    _require_session_identity(source, session=session, config=config)

    if decision.reason.startswith("insufficient_"):
        return _proposal(
            config=config,
            rule=rule,
            session=session,
            as_of=now,
            model_position=model_position,
            action="abstain",
            target_exposure=_ZERO,
            confidence=_ZERO,
            input_status="missing",
            feature_window_end=decision.feature_window_end,
            valid_until=now,
            reason=f"donchian_{decision.reason}",
        )

    if decision.action == "enter":
        action = "enter"
        target_exposure = config.target_exposure
    elif decision.action == "exit":
        action = "exit"
        target_exposure = _ZERO
    else:
        action = "hold"
        target_exposure = config.target_exposure if model_position == "long" else _ZERO

    return _proposal(
        config=config,
        rule=rule,
        session=session,
        as_of=now,
        model_position=model_position,
        action=action,
        target_exposure=target_exposure,
        confidence=config.confidence,
        input_status="ready",
        feature_window_end=decision.feature_window_end,
        valid_until=min(now + config.decision_ttl, session.close_ts),
        reason=f"donchian_{decision.reason}",
    )


def _require_session_identity(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    config: SessionResetDonchianTargetConfig,
) -> None:
    """Bind any declared-session input bars to the output proposal identity."""

    for bar in bars:
        inside_session = session.open_ts <= bar.start_ts and bar.end_ts <= session.close_ts
        if inside_session and (
            bar.symbol != config.symbol
            or bar.market != config.market
            or bar.timeframe != config.timeframe
        ):
            raise ValueError("session bar identity must match config")


def _proposal(
    *,
    config: SessionResetDonchianTargetConfig,
    rule: SessionResetDonchianRule,
    session: SessionWindow,
    as_of: datetime,
    model_position: DonchianPosition,
    action: str,
    target_exposure: Decimal,
    confidence: Decimal,
    input_status: str,
    feature_window_end: datetime | None,
    valid_until: datetime,
    reason: str,
) -> TargetExposureProposal:
    return TargetExposureProposal(
        proposal_id=_proposal_id(
            config=config,
            rule=rule,
            session=session,
            as_of=as_of,
            model_position=model_position,
            action=action,
            target_exposure=target_exposure,
            confidence=confidence,
            input_status=input_status,
            feature_window_end=feature_window_end,
            reason=reason,
        ),
        symbol=config.symbol,
        market=config.market,
        action=action,  # type: ignore[arg-type]
        target_exposure=target_exposure,
        confidence=confidence,
        feature_schema_id=SESSION_RESET_DONCHIAN_TARGET_FEATURE_SCHEMA_ID,
        input_status=input_status,  # type: ignore[arg-type]
        decided_at=as_of,
        valid_until=valid_until,
        feature_window_end=feature_window_end,
        reason=reason,
    )


def _proposal_id(
    *,
    config: SessionResetDonchianTargetConfig,
    rule: SessionResetDonchianRule,
    session: SessionWindow,
    as_of: datetime,
    model_position: DonchianPosition,
    action: str,
    target_exposure: Decimal,
    confidence: Decimal,
    input_status: str,
    feature_window_end: datetime | None,
    reason: str,
) -> str:
    """Hash only structural, temporal, and categorical proposal facts."""

    payload = {
        "adapter_id": SESSION_RESET_DONCHIAN_TARGET_ADAPTER_ID,
        "feature_schema_id": SESSION_RESET_DONCHIAN_TARGET_FEATURE_SCHEMA_ID,
        "instrument": {
            "symbol": config.symbol,
            "market": config.market,
            "timeframe": config.timeframe.value,
        },
        "rule": {
            "entry_lookback": rule.entry_lookback,
            "exit_lookback": rule.exit_lookback,
        },
        "session": {
            "open": _timestamp(session.open_ts),
            "close": _timestamp(session.close_ts),
        },
        "as_of": _timestamp(as_of),
        "model_position": model_position,
        "action": action,
        "target_exposure": _decimal_marker(target_exposure),
        "confidence": _decimal_marker(confidence),
        "input_status": input_status,
        "feature_window_end": (
            _timestamp(feature_window_end) if feature_window_end is not None else None
        ),
        "decision_ttl_microseconds": _timedelta_microseconds(config.decision_ttl),
        "reason": reason,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{SESSION_RESET_DONCHIAN_TARGET_ADAPTER_ID}:sha256:{digest}"


def _identity_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a nonempty trimmed string")
    return value.upper()


def _timestamp(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")


def _timedelta_microseconds(value: timedelta) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _decimal_marker(value: Decimal) -> str:
    return "0" if value == _ZERO else format(value.normalize(), "f")
