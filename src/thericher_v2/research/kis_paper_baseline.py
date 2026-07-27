"""Fixed 90-bar KIS-native target-state baseline with no broker dependency."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Bar,
    TargetAction,
    TargetExposureProposal,
    TargetInputStatus,
    Timeframe,
    require_utc,
)
from thericher_v2.data.kis_capability import (
    CompletedBarCache,
    KisCapabilityState,
    KisMarketDataCapability,
    trusted_kis_paper_baseline_qualifications,
)
from thericher_v2.data.resample import resample_bars

KIS_PAPER_BASELINE_SCHEMA_ID = "kis-paper-baseline-1m-90-v1"
KIS_PAPER_BASELINE_M1_BARS = 90
KIS_PAPER_BASELINE_MAX_AGE = timedelta(minutes=2)
KIS_PAPER_BASELINE_TARGET_EXPOSURE = Decimal("0.05")
KIS_PAPER_BASELINE_REDUCED_EXPOSURE = Decimal("0.025")
KIS_PAPER_BASELINE_MARKET = "US"
KIS_PAPER_BASELINE_SYMBOL = "QQQ"
KIS_PAPER_BASELINE_ENDPOINT_CATEGORY = "overseas_stock_intraday"
KIS_PAPER_BASELINE_PROVISIONAL_SCOPE_ID = "prospective-qqq-nas-1m-paper-v1"
_KIS_PAPER_BASELINE_REQUIRED_FIELDS = frozenset({"open", "high", "low", "last", "evol"})
BaselineCapabilityAuthorization = Literal["qualified", "provisional", "unqualified"]
_FIXED_TARGET_DECISION_TABLE: dict[
    tuple[int, int],
    tuple[TargetAction, Decimal, Decimal, str],
] = {
    (1, 1): (
        "enter",
        KIS_PAPER_BASELINE_TARGET_EXPOSURE,
        Decimal("0.55"),
        "fixed_10m_trend_up_5m_momentum_up_enter",
    ),
    (1, 0): (
        "hold",
        KIS_PAPER_BASELINE_TARGET_EXPOSURE,
        Decimal("0.55"),
        "fixed_10m_trend_up_5m_momentum_flat_hold",
    ),
    (1, -1): (
        "reduce",
        KIS_PAPER_BASELINE_REDUCED_EXPOSURE,
        Decimal("0.45"),
        "fixed_10m_trend_up_5m_momentum_down_reduce",
    ),
    (0, 1): (
        "hold",
        KIS_PAPER_BASELINE_TARGET_EXPOSURE,
        Decimal("0.55"),
        "fixed_10m_trend_flat_5m_momentum_up_hold",
    ),
    (0, 0): (
        "abstain",
        Decimal("0"),
        Decimal("0"),
        "fixed_10m_trend_flat_5m_momentum_flat_abstain",
    ),
    (0, -1): (
        "reduce",
        KIS_PAPER_BASELINE_REDUCED_EXPOSURE,
        Decimal("0.45"),
        "fixed_10m_trend_flat_5m_momentum_down_reduce",
    ),
    (-1, 1): (
        "reduce",
        KIS_PAPER_BASELINE_REDUCED_EXPOSURE,
        Decimal("0.45"),
        "fixed_10m_trend_down_5m_momentum_up_reduce",
    ),
    (-1, 0): (
        "exit",
        Decimal("0"),
        Decimal("0.45"),
        "fixed_10m_trend_down_5m_momentum_flat_exit",
    ),
    (-1, -1): (
        "exit",
        Decimal("0"),
        Decimal("0.55"),
        "fixed_10m_trend_down_5m_momentum_down_exit",
    ),
}


@dataclass(frozen=True)
class KisPaperBaselineAuthorization:
    """Hash-bound, single-scope permission for one observed QQQ Paper input."""

    capability_id: str
    capability_contract_sha256: str
    evidence_reference: str
    scope_id: str = KIS_PAPER_BASELINE_PROVISIONAL_SCOPE_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("provisional capability_id is required")
        if not _is_exact_sha256_reference(self.capability_contract_sha256):
            raise ValueError("provisional capability_contract_sha256 must be an exact sha256")
        if not _is_exact_sha256_reference(self.evidence_reference):
            raise ValueError("provisional evidence_reference must be an exact sha256")
        if self.scope_id != KIS_PAPER_BASELINE_PROVISIONAL_SCOPE_ID:
            raise ValueError("provisional authorization scope is not this Paper experiment")

    def binds(self, capability: KisMarketDataCapability) -> bool:
        return (
            self.capability_id == capability.capability_id
            and self.capability_contract_sha256 == capability.contract_sha256
            and self.evidence_reference == capability.evidence_reference
        )


@dataclass(frozen=True)
class KisPaperBaselineInput:
    m1_bars: tuple[Bar, ...]
    m5_bars: tuple[Bar, ...]
    m10_bars: tuple[Bar, ...]
    feature_window_end: datetime
    schema_id: str = KIS_PAPER_BASELINE_SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "m1_bars", tuple(self.m1_bars))
        object.__setattr__(self, "m5_bars", tuple(self.m5_bars))
        object.__setattr__(self, "m10_bars", tuple(self.m10_bars))
        object.__setattr__(
            self,
            "feature_window_end",
            require_utc(self.feature_window_end, "feature_window_end"),
        )
        if len(self.m1_bars) != KIS_PAPER_BASELINE_M1_BARS:
            raise ValueError("baseline input requires exactly 90 completed 1m bars")
        if len(self.m5_bars) != 18 or len(self.m10_bars) != 9:
            raise ValueError("baseline input requires complete 5m and 10m local resamples")
        if any(bar.timeframe != Timeframe.M1 for bar in self.m1_bars):
            raise ValueError("baseline raw input must be 1m")
        if any(bar.timeframe != Timeframe.M5 for bar in self.m5_bars):
            raise ValueError("baseline 5m input must be locally resampled")
        if any(bar.timeframe != Timeframe.M10 for bar in self.m10_bars):
            raise ValueError("baseline 10m input must be locally resampled")
        _require_complete_contiguous_stream(self.m1_bars, "baseline raw input")
        _require_complete_contiguous_stream(self.m5_bars, "baseline 5m input")
        _require_complete_contiguous_stream(self.m10_bars, "baseline 10m input")
        if (
            self.m5_bars[-1].end_ts != self.feature_window_end
            or self.m10_bars[-1].end_ts != self.feature_window_end
            or self.m1_bars[-1].end_ts != self.feature_window_end
        ):
            raise ValueError("baseline feature window end must match all complete inputs")
        if self.m5_bars != tuple(resample_bars(self.m1_bars, Timeframe.M5)):
            raise ValueError("baseline 5m input must match local raw resampling")
        if self.m10_bars != tuple(resample_bars(self.m1_bars, Timeframe.M10)):
            raise ValueError("baseline 10m input must match local raw resampling")


@dataclass(frozen=True)
class KisPaperBaselineEvaluation:
    proposal: TargetExposureProposal
    baseline_input: KisPaperBaselineInput | None
    capability_authorization: BaselineCapabilityAuthorization = "unqualified"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.capability_authorization not in {"qualified", "provisional", "unqualified"}:
            raise ValueError("baseline capability authorization is invalid")


def evaluate_kis_paper_baseline(
    bars: Sequence[Bar],
    *,
    capability: KisMarketDataCapability,
    symbol: str,
    market: str,
    as_of: datetime,
    max_age: timedelta = KIS_PAPER_BASELINE_MAX_AGE,
    provisional_authorization: KisPaperBaselineAuthorization | None = None,
) -> KisPaperBaselineEvaluation:
    """Return a target-state proposal; this module never creates an order."""

    resolved_symbol = symbol.strip().upper()
    resolved_market = market.strip().upper()
    if not resolved_symbol or not resolved_market:
        raise ValueError("symbol and market are required")
    observed_at = require_utc(as_of, "as_of")
    capability_authorization = _resolve_baseline_capability_authorization(
        capability,
        symbol=resolved_symbol,
        market=resolved_market,
        provisional_authorization=provisional_authorization,
    )
    if capability_authorization == "unqualified":
        return KisPaperBaselineEvaluation(
            proposal=_abstain(
                symbol=resolved_symbol,
                market=resolved_market,
                decided_at=observed_at,
                status="unqualified",
                reason="baseline_input_capability_unqualified",
            ),
            baseline_input=None,
            capability_authorization=capability_authorization,
        )
    assert capability.freshness_budget is not None
    window = CompletedBarCache(tuple(bars)).latest_window(
        count=KIS_PAPER_BASELINE_M1_BARS,
        as_of=observed_at,
        max_age=min(max_age, capability.freshness_budget),
    )
    if window.status != "ready":
        return KisPaperBaselineEvaluation(
            proposal=_abstain(
                symbol=resolved_symbol,
                market=resolved_market,
                decided_at=observed_at,
                status=window.status,
                reason=f"baseline_input_{window.status}",
            ),
            baseline_input=None,
            capability_authorization=capability_authorization,
        )

    raw_bars = window.bars
    _require_expected_stream(raw_bars, symbol=resolved_symbol, market=resolved_market)
    if not _ends_on_ten_minute_boundary(raw_bars[-1].end_ts):
        return KisPaperBaselineEvaluation(
            proposal=_abstain(
                symbol=resolved_symbol,
                market=resolved_market,
                decided_at=observed_at,
                status="misaligned",
                reason="baseline_input_misaligned_10m_boundary",
                feature_window_end=raw_bars[-1].end_ts,
                input_fingerprint=_bar_window_fingerprint(raw_bars),
            ),
            baseline_input=None,
            capability_authorization=capability_authorization,
        )

    m5_bars = tuple(resample_bars(raw_bars, Timeframe.M5))
    m10_bars = tuple(resample_bars(raw_bars, Timeframe.M10))
    try:
        baseline_input = KisPaperBaselineInput(
            m1_bars=raw_bars,
            m5_bars=m5_bars,
            m10_bars=m10_bars,
            feature_window_end=raw_bars[-1].end_ts,
        )
    except ValueError:
        return KisPaperBaselineEvaluation(
            proposal=_abstain(
                symbol=resolved_symbol,
                market=resolved_market,
                decided_at=observed_at,
                status="incomplete",
                reason="baseline_input_resample_incomplete",
                feature_window_end=raw_bars[-1].end_ts,
                input_fingerprint=_bar_window_fingerprint(raw_bars),
            ),
            baseline_input=None,
            capability_authorization=capability_authorization,
        )

    if observed_at >= baseline_input.feature_window_end + Timeframe.M10.duration:
        return KisPaperBaselineEvaluation(
            proposal=_abstain(
                symbol=resolved_symbol,
                market=resolved_market,
                decided_at=observed_at,
                status="stale",
                reason="baseline_input_expired",
                feature_window_end=baseline_input.feature_window_end,
                input_fingerprint=_bar_window_fingerprint(baseline_input.m1_bars),
            ),
            baseline_input=None,
            capability_authorization=capability_authorization,
        )

    trend_sign = _price_change_sign(
        baseline_input.m10_bars[-1].close,
        baseline_input.m10_bars[0].close,
    )
    momentum_sign = _price_change_sign(
        baseline_input.m5_bars[-1].close,
        baseline_input.m5_bars[-2].close,
    )
    action, exposure, confidence, reason = _FIXED_TARGET_DECISION_TABLE[
        (trend_sign, momentum_sign)
    ]
    proposal = TargetExposureProposal(
        proposal_id=_proposal_id(
            resolved_symbol,
            resolved_market,
            input_status="ready",
            reason=reason,
            feature_window_end=baseline_input.feature_window_end,
            input_fingerprint=_bar_window_fingerprint(baseline_input.m1_bars),
        ),
        symbol=resolved_symbol,
        market=resolved_market,
        action=action,
        target_exposure=exposure,
        confidence=confidence,
        feature_schema_id=KIS_PAPER_BASELINE_SCHEMA_ID,
        input_status="ready",
        decided_at=observed_at,
        valid_until=baseline_input.feature_window_end + Timeframe.M10.duration,
        feature_window_end=baseline_input.feature_window_end,
        reason=reason,
    )
    return KisPaperBaselineEvaluation(
        proposal=proposal,
        baseline_input=baseline_input,
        capability_authorization=capability_authorization,
    )


def _abstain(
    *,
    symbol: str,
    market: str,
    decided_at: datetime,
    status: TargetInputStatus,
    reason: str,
    feature_window_end: datetime | None = None,
    input_fingerprint: str | None = None,
) -> TargetExposureProposal:
    return TargetExposureProposal(
        proposal_id=_proposal_id(
            symbol,
            market,
            input_status=status,
            reason=reason,
            feature_window_end=feature_window_end,
            input_fingerprint=input_fingerprint,
        ),
        symbol=symbol,
        market=market,
        action="abstain",
        target_exposure=Decimal("0"),
        confidence=Decimal("0"),
        feature_schema_id=KIS_PAPER_BASELINE_SCHEMA_ID,
        input_status=status,
        decided_at=decided_at,
        valid_until=decided_at + Timeframe.M1.duration,
        feature_window_end=feature_window_end,
        reason=reason,
    )


def _proposal_id(
    symbol: str,
    market: str,
    *,
    input_status: TargetInputStatus,
    reason: str,
    feature_window_end: datetime | None,
    input_fingerprint: str | None,
) -> str:
    feature_marker = (
        "none"
        if feature_window_end is None
        else feature_window_end.strftime("%Y%m%dT%H%M%SZ")
    )
    fingerprint_marker = input_fingerprint or "none"
    return ":".join(
        (
            KIS_PAPER_BASELINE_SCHEMA_ID,
            market,
            symbol,
            input_status,
            reason,
            feature_marker,
            fingerprint_marker,
        )
    )


def _bar_window_fingerprint(bars: Sequence[Bar]) -> str:
    payload = [
        {
            "close": _decimal_marker(bar.close),
            "complete": bar.complete,
            "high": _decimal_marker(bar.high),
            "low": _decimal_marker(bar.low),
            "market": bar.market,
            "open": _decimal_marker(bar.open),
            "schema_version": bar.schema_version,
            "start_ts": bar.start_ts.isoformat(),
            "symbol": bar.symbol,
            "timeframe": bar.timeframe.value,
            "volume": _decimal_marker(bar.volume),
        }
        for bar in bars
    ]
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decimal_marker(value: Decimal) -> str:
    sign, digits, exponent = value.as_tuple()
    if not any(digits):
        return "0"
    last_significant = len(digits)
    while digits[last_significant - 1] == 0:
        last_significant -= 1
        exponent += 1
    prefix = "-" if sign else ""
    significand = "".join(str(digit) for digit in digits[:last_significant])
    return f"{prefix}{significand}e{exponent}"


def _ends_on_ten_minute_boundary(timestamp: datetime) -> bool:
    return timestamp.minute % 10 == 0 and timestamp.second == 0 and timestamp.microsecond == 0


def _require_expected_stream(bars: tuple[Bar, ...], *, symbol: str, market: str) -> None:
    if any(
        bar.symbol != symbol or bar.market != market or bar.timeframe != Timeframe.M1
        for bar in bars
    ):
        raise ValueError("baseline bars do not match the expected complete 1m stream")


def _is_eligible_baseline_capability(
    capability: KisMarketDataCapability,
    *,
    symbol: str,
    market: str,
) -> bool:
    return (
        capability.paper_model_eligible
        and _has_trusted_baseline_qualification(capability)
        and _has_required_baseline_capability_scope(
            capability,
            symbol=symbol,
            market=market,
        )
    )


def _resolve_baseline_capability_authorization(
    capability: KisMarketDataCapability,
    *,
    symbol: str,
    market: str,
    provisional_authorization: KisPaperBaselineAuthorization | None,
) -> BaselineCapabilityAuthorization:
    if _is_eligible_baseline_capability(capability, symbol=symbol, market=market):
        return "qualified"
    if _is_eligible_provisional_baseline_capability(
        capability,
        symbol=symbol,
        market=market,
        provisional_authorization=provisional_authorization,
    ):
        return "provisional"
    return "unqualified"


def _is_eligible_provisional_baseline_capability(
    capability: KisMarketDataCapability,
    *,
    symbol: str,
    market: str,
    provisional_authorization: KisPaperBaselineAuthorization | None,
) -> bool:
    return (
        provisional_authorization is not None
        and capability.state == KisCapabilityState.OBSERVED
        and _is_exact_sha256_reference(capability.evidence_reference)
        and provisional_authorization.binds(capability)
        and _has_required_baseline_capability_scope(
            capability,
            symbol=symbol,
            market=market,
        )
    )


def _has_required_baseline_capability_scope(
    capability: KisMarketDataCapability,
    *,
    symbol: str,
    market: str,
) -> bool:
    return (
        capability.endpoint_category == KIS_PAPER_BASELINE_ENDPOINT_CATEGORY
        and capability.timeframe == Timeframe.M1
        and "NAS" in capability.exchange_scope
        and symbol == KIS_PAPER_BASELINE_SYMBOL
        and KIS_PAPER_BASELINE_SYMBOL in capability.symbol_scope
        and market == KIS_PAPER_BASELINE_MARKET
        and _KIS_PAPER_BASELINE_REQUIRED_FIELDS.issubset(capability.raw_fields)
        and capability.freshness_budget is not None
        and capability.freshness_budget > timedelta(0)
    )


def _has_trusted_baseline_qualification(capability: KisMarketDataCapability) -> bool:
    return any(
        qualification.binds(capability)
        for qualification in trusted_kis_paper_baseline_qualifications()
    )


def _price_change_sign(current: Decimal, previous: Decimal) -> int:
    if current > previous:
        return 1
    if current < previous:
        return -1
    return 0


def _is_exact_sha256_reference(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdefABCDEF" for character in digest)


def _require_complete_contiguous_stream(bars: tuple[Bar, ...], label: str) -> None:
    first = bars[0]
    if any(
        not bar.complete
        or bar.symbol != first.symbol
        or bar.market != first.market
        or bar.timeframe != first.timeframe
        for bar in bars
    ):
        raise ValueError(f"{label} must be complete and from one stream")
    if any(
        current.start_ts != previous.end_ts
        for previous, current in zip(bars, bars[1:], strict=False)
    ):
        raise ValueError(f"{label} must be contiguous")
