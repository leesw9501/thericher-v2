"""Pure prospective SPY intraday baseline over a causal sequence record."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from thericher_v2.contracts import TargetExposureProposal, Timeframe, require_utc

from .prospective_spy_intraday_session import ProspectiveSpyIntradaySessionRecord
from .sequence_window import (
    SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
    CausalMultiTimeframeSequenceWindow,
)

PROSPECTIVE_SPY_INTRADAY_BASELINE_ID = "prospective-spy-intraday-baseline-v1"
PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID = (
    "prospective-spy-intraday-baseline-features-v1"
)
PROSPECTIVE_SPY_INTRADAY_BASELINE_TARGET_EXPOSURE = Decimal("0.02")
PROSPECTIVE_SPY_INTRADAY_BASELINE_ROUND_TRIP_COST_BPS = Decimal("10")
PROSPECTIVE_SPY_INTRADAY_BASELINE_DECISION_TTL = timedelta(minutes=1)
_EXPECTED_SYMBOL = "SPY"
_EXPECTED_MARKET = "US"
_EXPECTED_LOOKBACKS = {
    Timeframe.M1: 30,
    Timeframe.M5: 6,
    Timeframe.M10: 3,
    Timeframe.H1: 2,
    Timeframe.H3: 2,
}
_SHA256_PREFIX = "sha256:"
_FORBIDDEN_SAFE_KEYS = frozenset({"open", "high", "low", "close", "volume", "ohlcv", "price"})


@dataclass(frozen=True, slots=True)
class ProspectiveSpyIntradayBaselineEvaluation:
    """One deterministic target proposal plus non-value-bearing contract facts."""

    proposal: TargetExposureProposal
    safe_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "safe_metadata", MappingProxyType(dict(self.safe_metadata)))


@dataclass(frozen=True, slots=True)
class _ValidatedRecord:
    sequence_window: CausalMultiTimeframeSequenceWindow
    source_contract_hash: str
    contract_hash: str
    cutoff: datetime


def evaluate_prospective_spy_intraday_baseline(
    record: ProspectiveSpyIntradaySessionRecord,
) -> ProspectiveSpyIntradayBaselineEvaluation:
    """Apply one unanimous trailing-return rule without I/O or execution behavior.

    This is a prospective research baseline only.  It treats every required
    timeframe equally: all five final closes must exceed their first closes to
    propose a small long target.  Any nonpositive return is an abstain/no-trade.
    """

    validated = _validate_record(record)
    enters_long = all(
        window.bars[-1].close > window.bars[0].close
        for window in validated.sequence_window.windows.values()
    )
    proposal = TargetExposureProposal(
        proposal_id=_proposal_id(validated, enters_long=enters_long),
        symbol=_EXPECTED_SYMBOL,
        market=_EXPECTED_MARKET,
        action="enter" if enters_long else "abstain",
        target_exposure=(
            PROSPECTIVE_SPY_INTRADAY_BASELINE_TARGET_EXPOSURE
            if enters_long
            else Decimal("0")
        ),
        confidence=Decimal("0.50") if enters_long else Decimal("0"),
        feature_schema_id=PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID,
        input_status="ready",
        decided_at=validated.cutoff,
        valid_until=validated.cutoff + PROSPECTIVE_SPY_INTRADAY_BASELINE_DECISION_TTL,
        feature_window_end=max(
            window.end_ts for window in validated.sequence_window.windows.values()
        ),
        reason=(
            "unanimous_trailing_return_enter"
            if enters_long
            else "trailing_return_not_unanimous_abstain"
        ),
    )
    return ProspectiveSpyIntradayBaselineEvaluation(
        proposal=proposal,
        safe_metadata=_safe_metadata(validated, enters_long=enters_long),
    )


def _validate_record(record: ProspectiveSpyIntradaySessionRecord) -> _ValidatedRecord:
    if not isinstance(record, ProspectiveSpyIntradaySessionRecord):
        raise TypeError("record must be a ProspectiveSpyIntradaySessionRecord")
    strict_record = ProspectiveSpyIntradaySessionRecord(
        source_contract_hash=record.source_contract_hash,
        contract_hash=record.contract_hash,
        cutoff=record.cutoff,
        session=record.session,
        sequence_window=record.sequence_window,
    )
    sequence_window = strict_record.sequence_window
    if not isinstance(sequence_window, CausalMultiTimeframeSequenceWindow):
        raise ValueError("record sequence_window must be a causal multi-timeframe window")
    cutoff = require_utc(strict_record.cutoff, "record.cutoff")
    if sequence_window.cutoff != cutoff:
        raise ValueError("record cutoff must match sequence window cutoff")
    if (sequence_window.symbol, sequence_window.market) != (_EXPECTED_SYMBOL, _EXPECTED_MARKET):
        raise ValueError("record sequence window identity must be SPY/US")
    if tuple(sequence_window.windows) != SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        raise ValueError("record sequence window must contain the frozen timeframe structure")
    if {
        timeframe: len(window.bars)
        for timeframe, window in sequence_window.windows.items()
    } != _EXPECTED_LOOKBACKS:
        raise ValueError("record sequence window lookbacks must match the frozen structure")

    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        window = sequence_window.windows[timeframe]
        if window.timeframe != timeframe:
            raise ValueError("record timeframe mapping must match its windows")
        if not window.bars:
            raise ValueError("record timeframe windows must not be empty")
        if any(
            bar.symbol != _EXPECTED_SYMBOL
            or bar.market != _EXPECTED_MARKET
            or not bar.complete
            or bar.end_ts > cutoff
            for bar in window.bars
        ):
            raise ValueError("record contains an invalid or future source bar")

    source_contract_hash = _require_identity(
        strict_record.source_contract_hash,
        "source_contract_hash",
    )
    contract_hash = _require_identity(strict_record.contract_hash, "contract_hash")
    safe_payload = _require_safe_payload(strict_record.safe_payload())
    if (
        safe_payload.get("source_contract_hash") != source_contract_hash
        or safe_payload.get("contract_hash") != contract_hash
    ):
        raise ValueError("record safe_payload identities must match the record")
    return _ValidatedRecord(
        sequence_window=sequence_window,
        source_contract_hash=source_contract_hash,
        contract_hash=contract_hash,
        cutoff=cutoff,
    )


def _safe_metadata(
    record: _ValidatedRecord,
    *,
    enters_long: bool,
) -> dict[str, object]:
    structural_window = _require_safe_payload(record.sequence_window.structural_metadata())
    return {
        "baseline_id": PROSPECTIVE_SPY_INTRADAY_BASELINE_ID,
        "feature_schema_id": PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID,
        "source_contract_hash": record.source_contract_hash,
        "record_contract_hash": record.contract_hash,
        "symbol": _EXPECTED_SYMBOL,
        "market": _EXPECTED_MARKET,
        "cutoff": _utc_marker(record.cutoff),
        "required_timeframes": [
            timeframe.value for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
        ],
        "sequence_window": structural_window,
        "rule": "unanimous_trailing_return",
        "decision": "enter_long" if enters_long else "abstain_no_trade",
        "target_exposure": str(PROSPECTIVE_SPY_INTRADAY_BASELINE_TARGET_EXPOSURE),
        "decision_ttl_seconds": int(
            PROSPECTIVE_SPY_INTRADAY_BASELINE_DECISION_TTL.total_seconds()
        ),
        "round_trip_cost_bps": str(PROSPECTIVE_SPY_INTRADAY_BASELINE_ROUND_TRIP_COST_BPS),
        "naive_comparator": "always_flat",
        "training_or_tuning": False,
        "ensemble": False,
        "execution_authority": False,
    }


def _proposal_id(record: _ValidatedRecord, *, enters_long: bool) -> str:
    payload = {
        "baseline_id": PROSPECTIVE_SPY_INTRADAY_BASELINE_ID,
        "source_contract_hash": record.source_contract_hash,
        "record_contract_hash": record.contract_hash,
        "cutoff": _utc_marker(record.cutoff),
        "sequence_window": record.sequence_window.structural_metadata(),
        "enters_long": enters_long,
    }
    return f"{PROSPECTIVE_SPY_INTRADAY_BASELINE_ID}:sha256:{_sha256_json(payload)}"


def _require_identity(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != len(_SHA256_PREFIX) + 64
        or not value.startswith(_SHA256_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    ):
        raise ValueError(f"record {field_name} must use sha256:<64 lowercase hex> format")
    return value


def _require_safe_payload(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("record safe_payload must be a mapping")
    _reject_forbidden_safe_keys(value)
    return value


def _reject_forbidden_safe_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_SAFE_KEYS:
                raise ValueError("safe metadata must not contain OHLCV values")
            _reject_forbidden_safe_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_forbidden_safe_keys(nested)


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_marker(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
