"""Pure, source-safe receipt for one prospective SPY baseline evaluation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, require_utc

from .prospective_spy_intraday_baseline import (
    PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID,
    PROSPECTIVE_SPY_INTRADAY_BASELINE_ID,
    ProspectiveSpyIntradayBaselineEvaluation,
    evaluate_prospective_spy_intraday_baseline,
)
from .prospective_spy_intraday_session import ProspectiveSpyIntradaySessionRecord

PROSPECTIVE_SPY_INTRADAY_OBSERVATION_RECEIPT_ID = "prospective-spy-observation-receipt-v1"
_SHA256_PREFIX = "sha256:"
_RECEIPT_PREFIX = f"{PROSPECTIVE_SPY_INTRADAY_OBSERVATION_RECEIPT_ID}:sha256:"
_FORBIDDEN_SAFE_KEYS = frozenset(
    {
        "account",
        "broker",
        "close",
        "credential",
        "file",
        "fill",
        "high",
        "intent",
        "low",
        "ohlcv",
        "open",
        "order",
        "password",
        "path",
        "price",
        "position",
        "quantity",
        "secret",
        "token",
        "volume",
    }
)
ObservationDecisionClass = Literal["enter", "abstain"]
ObservationReasonClass = Literal["eligible_enter", "model_abstain"]


@dataclass(frozen=True, slots=True)
class ProspectiveSpyIntradayObservationReceipt:
    """Immutable evidence that binds the causal model input without exposing it."""

    source_contract_hash: str
    record_contract_hash: str
    bar_content_commitment_sha256: str
    session_open_ts: datetime
    session_close_ts: datetime
    cutoff: datetime
    decided_at: datetime
    valid_until: datetime
    decision_class: ObservationDecisionClass
    reason_class: ObservationReasonClass
    receipt_id: str
    input_status: Literal["ready"] = "ready"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.source_contract_hash, "source_contract_hash"),
            (self.record_contract_hash, "record_contract_hash"),
            (self.bar_content_commitment_sha256, "bar_content_commitment_sha256"),
        ):
            _require_sha256(value, field_name)
        for field_name in (
            "session_open_ts",
            "session_close_ts",
            "cutoff",
            "decided_at",
            "valid_until",
        ):
            object.__setattr__(self, field_name, require_utc(getattr(self, field_name), field_name))
        if self.session_open_ts >= self.session_close_ts:
            raise ValueError("receipt session geometry is invalid")
        if (
            self.cutoff != self.session_open_ts + timedelta(hours=6)
            or self.session_close_ts != self.cutoff + timedelta(minutes=30)
        ):
            raise ValueError("receipt session geometry is invalid")
        if not self.session_open_ts < self.cutoff < self.session_close_ts:
            raise ValueError("receipt cutoff is outside its session")
        if (
            self.decided_at != self.cutoff
            or self.valid_until != self.decided_at + timedelta(minutes=1)
        ):
            raise ValueError("receipt decision timing is invalid")
        if self.input_status != "ready":
            raise ValueError("receipt input_status is invalid")
        if self.decision_class not in {"enter", "abstain"}:
            raise ValueError("receipt decision_class is invalid")
        expected_reason = (
            "eligible_enter" if self.decision_class == "enter" else "model_abstain"
        )
        if self.reason_class != expected_reason:
            raise ValueError("receipt reason_class is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("receipt schema_version is invalid")
        if self.receipt_id != _receipt_id(self._identity_payload()):
            raise ValueError("receipt_id does not match the immutable receipt payload")

    def _identity_payload(self) -> dict[str, object]:
        return {
            "receipt_schema_id": PROSPECTIVE_SPY_INTRADAY_OBSERVATION_RECEIPT_ID,
            "baseline_id": PROSPECTIVE_SPY_INTRADAY_BASELINE_ID,
            "feature_schema_id": PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID,
            "source_contract_hash": self.source_contract_hash,
            "record_contract_hash": self.record_contract_hash,
            "bar_content_commitment_sha256": self.bar_content_commitment_sha256,
            "session_open_ts": _utc_marker(self.session_open_ts),
            "session_close_ts": _utc_marker(self.session_close_ts),
            "cutoff": _utc_marker(self.cutoff),
            "decided_at": _utc_marker(self.decided_at),
            "valid_until": _utc_marker(self.valid_until),
            "input_status": self.input_status,
            "decision_class": self.decision_class,
            "reason_class": self.reason_class,
            "schema_version": self.schema_version,
        }

    def to_payload(self) -> dict[str, object]:
        """Return deterministic receipt facts without raw bars or execution state."""

        payload = {"receipt_id": self.receipt_id, **self._identity_payload()}
        _require_safe_payload(payload)
        return payload

    def canonical_json(self) -> str:
        """Serialize this source-safe receipt in a byte-stable form."""

        return json.dumps(
            self.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> ProspectiveSpyIntradayObservationReceipt:
        """Rebuild one canonical source-safe receipt without touching its source."""

        expected_keys = {
            "receipt_id",
            "receipt_schema_id",
            "baseline_id",
            "feature_schema_id",
            "source_contract_hash",
            "record_contract_hash",
            "bar_content_commitment_sha256",
            "session_open_ts",
            "session_close_ts",
            "cutoff",
            "decided_at",
            "valid_until",
            "input_status",
            "decision_class",
            "reason_class",
            "schema_version",
        }
        if set(payload) != expected_keys:
            raise ValueError("receipt payload fields are invalid")
        if payload["receipt_schema_id"] != PROSPECTIVE_SPY_INTRADAY_OBSERVATION_RECEIPT_ID:
            raise ValueError("receipt schema id is invalid")
        if payload["baseline_id"] != PROSPECTIVE_SPY_INTRADAY_BASELINE_ID:
            raise ValueError("receipt baseline id is invalid")
        if (
            payload["feature_schema_id"]
            != PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID
        ):
            raise ValueError("receipt feature schema id is invalid")
        schema_version = payload["schema_version"]
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValueError("receipt schema version is invalid")
        return cls(
            source_contract_hash=_require_string(
                payload["source_contract_hash"], "source_contract_hash"
            ),
            record_contract_hash=_require_string(
                payload["record_contract_hash"], "record_contract_hash"
            ),
            bar_content_commitment_sha256=_require_string(
                payload["bar_content_commitment_sha256"],
                "bar_content_commitment_sha256",
            ),
            session_open_ts=_parse_utc_marker(payload["session_open_ts"], "session_open_ts"),
            session_close_ts=_parse_utc_marker(payload["session_close_ts"], "session_close_ts"),
            cutoff=_parse_utc_marker(payload["cutoff"], "cutoff"),
            decided_at=_parse_utc_marker(payload["decided_at"], "decided_at"),
            valid_until=_parse_utc_marker(payload["valid_until"], "valid_until"),
            decision_class=_require_string(payload["decision_class"], "decision_class"),  # type: ignore[arg-type]
            reason_class=_require_string(payload["reason_class"], "reason_class"),  # type: ignore[arg-type]
            receipt_id=_require_string(payload["receipt_id"], "receipt_id"),
            input_status=_require_string(payload["input_status"], "input_status"),  # type: ignore[arg-type]
            schema_version=schema_version,
        )


@dataclass(frozen=True, slots=True)
class ProspectiveSpyIntradayObservation:
    """In-memory evaluation plus its safe, immutable observation receipt."""

    record: ProspectiveSpyIntradaySessionRecord = field(repr=False)
    evaluation: ProspectiveSpyIntradayBaselineEvaluation = field(repr=False)
    receipt: ProspectiveSpyIntradayObservationReceipt

    def __post_init__(self) -> None:
        if not isinstance(self.record, ProspectiveSpyIntradaySessionRecord):
            raise TypeError("record must be a ProspectiveSpyIntradaySessionRecord")
        if not isinstance(self.evaluation, ProspectiveSpyIntradayBaselineEvaluation):
            raise TypeError("evaluation must be a ProspectiveSpyIntradayBaselineEvaluation")
        if not isinstance(self.receipt, ProspectiveSpyIntradayObservationReceipt):
            raise TypeError("receipt must be a ProspectiveSpyIntradayObservationReceipt")
        if self.receipt != _receipt_from(record=self.record, evaluation=self.evaluation):
            raise ValueError("observation receipt does not match the frozen baseline")

    def safe_payload(self) -> dict[str, object]:
        """Expose only the receipt; evaluated bar values stay in memory."""

        return self.receipt.to_payload()


def observe_prospective_spy_intraday_baseline(
    record: ProspectiveSpyIntradaySessionRecord,
) -> ProspectiveSpyIntradayObservation:
    """Evaluate one immutable record once and return its source-safe receipt."""

    if not isinstance(record, ProspectiveSpyIntradaySessionRecord):
        raise TypeError("record must be a ProspectiveSpyIntradaySessionRecord")
    evaluation = evaluate_prospective_spy_intraday_baseline(record)
    return ProspectiveSpyIntradayObservation(
        record=record,
        evaluation=evaluation,
        receipt=_receipt_from(record=record, evaluation=evaluation),
    )


def _receipt_from(
    *,
    record: ProspectiveSpyIntradaySessionRecord,
    evaluation: ProspectiveSpyIntradayBaselineEvaluation,
) -> ProspectiveSpyIntradayObservationReceipt:
    proposal = evaluation.proposal
    if proposal.action == "enter":
        decision_class: ObservationDecisionClass = "enter"
        reason_class: ObservationReasonClass = "eligible_enter"
    elif proposal.action == "abstain":
        decision_class = "abstain"
        reason_class = "model_abstain"
    else:
        raise ValueError("prospective baseline must emit enter or abstain")
    base = {
        "receipt_schema_id": PROSPECTIVE_SPY_INTRADAY_OBSERVATION_RECEIPT_ID,
        "baseline_id": PROSPECTIVE_SPY_INTRADAY_BASELINE_ID,
        "feature_schema_id": PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID,
        "source_contract_hash": record.source_contract_hash,
        "record_contract_hash": record.contract_hash,
        "bar_content_commitment_sha256": _bar_content_commitment(record),
        "session_open_ts": _utc_marker(record.session.open_ts),
        "session_close_ts": _utc_marker(record.session.close_ts),
        "cutoff": _utc_marker(record.cutoff),
        "decided_at": _utc_marker(proposal.decided_at),
        "valid_until": _utc_marker(proposal.valid_until),
        "input_status": proposal.input_status,
        "decision_class": decision_class,
        "reason_class": reason_class,
        "schema_version": SCHEMA_VERSION,
    }
    return ProspectiveSpyIntradayObservationReceipt(
        source_contract_hash=record.source_contract_hash,
        record_contract_hash=record.contract_hash,
        bar_content_commitment_sha256=str(base["bar_content_commitment_sha256"]),
        session_open_ts=record.session.open_ts,
        session_close_ts=record.session.close_ts,
        cutoff=record.cutoff,
        decided_at=proposal.decided_at,
        valid_until=proposal.valid_until,
        decision_class=decision_class,
        reason_class=reason_class,
        receipt_id=_receipt_id(base),
    )


def _bar_content_commitment(record: ProspectiveSpyIntradaySessionRecord) -> str:
    """Commit every selected model bar without serializing any bar value."""

    payload = {
        "kind": "prospective-spy-selected-bar-content-v1",
        "windows": [
            {
                "timeframe": timeframe.value,
                "bars": [_canonical_bar_payload(bar) for bar in window.bars],
            }
            for timeframe, window in record.sequence_window.windows.items()
        ],
    }
    return _SHA256_PREFIX + _sha256_json(payload)


def _canonical_bar_payload(bar: Bar) -> dict[str, object]:
    return {
        "symbol": bar.symbol,
        "market": bar.market,
        "timeframe": bar.timeframe.value,
        "start_ts": _utc_marker(bar.start_ts),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
        "complete": bar.complete,
    }


def _receipt_id(payload: Mapping[str, object]) -> str:
    return _RECEIPT_PREFIX + _sha256_json(payload)


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != len(_SHA256_PREFIX) + 64
        or not value.startswith(_SHA256_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _parse_utc_marker(value: object, field_name: str) -> datetime:
    marker = _require_string(value, field_name)
    try:
        parsed = datetime.fromisoformat(marker.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is invalid") from error
    normalized = require_utc(parsed, field_name)
    if _utc_marker(normalized) != marker:
        raise ValueError(f"{field_name} is not canonical UTC")
    return normalized


def _require_safe_payload(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN_SAFE_KEYS:
                raise ValueError("observation receipt contains a forbidden field")
            _require_safe_payload(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _require_safe_payload(nested)
        return
    if value is not None and not isinstance(value, (str, int, bool)):
        raise ValueError("observation receipt contains an unsafe value")


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _utc_marker(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")
