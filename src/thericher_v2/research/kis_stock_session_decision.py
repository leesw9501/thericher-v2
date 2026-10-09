"""Pure pre-OPEN TCN20 session preparation, never an order or model loader.

Callers attest official NYSE clocks, manifest bytes, the original model and
trusted numeric scorer. Raw/current-listed/non-PIT/finality limits remain.
The 3126ba5b prior20 engineering screen is unchanged, not qualification.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from enum import StrEnum
from fractions import Fraction
from types import MappingProxyType

from thericher_v2.contracts import Bar, TargetExposureProposal, require_utc
from thericher_v2.research import kis_stock_relative_features as feature
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

MODEL_SHA256 = "sha256:9de279445b01a7abf03bdbd038145cf8daeecaff2bdb69580eee1df17be58df4"
COHORT_SHA256 = "sha256:3126ba5be86368083a12f7fa11cbd9067faa0241b21737fb700b5983e2c1168d"
ARM = "tcn20"
FEATURE_SCHEMA_ID = "kis_stock_prior20_on_id_session_v1"
SessionPlan = feature.FeaturePlan


class Reason(StrEnum):
    PREPARED = "prepared"
    CONTRACT = "contract_mismatch"
    STALE = "stale_input"
    FUTURE = "future_observation"
    CLOCK = "clock_invalid"
    LATE = "late_session"
    MISSING = "input_unavailable"
    IDENTITY = "identity_mismatch"
    FEWER = "fewer_than_10"
    SCORER = "scoring_unavailable"
    SCORES = "score_binding_invalid"


class _Fault(ValueError):
    def __init__(self, reason: Reason):
        self.reason = reason
        super().__init__(reason.value)


def _require(ok: bool, reason: Reason = Reason.CONTRACT) -> None:
    if not ok:
        raise _Fault(reason)


def _utc(value: datetime) -> datetime:
    _require(type(value) is datetime and value.utcoffset() == timedelta(0), Reason.CLOCK)
    return require_utc(value)


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _pin(value: str) -> bool:
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


@dataclass(frozen=True, slots=True, repr=False)
class SessionInstrument:
    key: str
    symbol: str
    exchange: str = "NASD"
    market: str = "US"

    def __post_init__(self) -> None:
        _require(
            type(self.key) is str
            and bool(self.key)
            and type(self.symbol) is str
            and re.fullmatch(r"[A-Z]{1,10}", self.symbol, re.ASCII) is not None
            and self.exchange == "NASD"
            and self.market == "US",
            Reason.IDENTITY,
        )


def instrument_map_sha256(instruments: Mapping[str, SessionInstrument]) -> str:
    _require(isinstance(instruments, Mapping), Reason.IDENTITY)
    rows = []
    for key, value in sorted(instruments.items()):
        _require(type(value) is SessionInstrument and key == value.key, Reason.IDENTITY)
        value.__post_init__()
        rows.append([key, value.symbol, value.exchange, value.market])
    return _digest(rows)


def calendar_sha256(plan: SessionPlan) -> str:
    _require(type(plan) is SessionPlan and len(plan.sessions) == 113)
    return _digest(
        [
            [day.isoformat(), opened.isoformat(), closed.isoformat()]
            for day, opened, closed in zip(
                plan.sessions, plan.open_clocks, plan.close_clocks, strict=True
            )
        ]
    )


@dataclass(frozen=True, slots=True, repr=False)
class SessionEnvelope:
    """113 official calendar labels, 100 raw input sessions, only 61 prices used."""

    plan: SessionPlan
    instruments: Mapping[str, SessionInstrument]
    observed_at_by_key: Mapping[str, datetime | None]
    input_anchor_date: date
    input_manifest_sha256: str
    model_sha256: str
    instrument_map_sha256: str
    calendar_sha256: str
    references: DecisionReceiptReferences
    as_of: datetime

    def __post_init__(self) -> None:
        _require(type(self.plan) is SessionPlan and len(self.plan.sessions) == 113)
        _require(type(self.input_anchor_date) is date)
        _require(type(self.references) is DecisionReceiptReferences)
        _require(
            isinstance(self.instruments, Mapping) and isinstance(self.observed_at_by_key, Mapping)
        )
        object.__setattr__(self, "instruments", MappingProxyType(dict(self.instruments)))
        object.__setattr__(
            self, "observed_at_by_key", MappingProxyType(dict(self.observed_at_by_key))
        )
        object.__setattr__(self, "as_of", _utc(self.as_of))
        _require(
            all(
                _pin(pin)
                for pin in (
                    self.input_manifest_sha256,
                    self.model_sha256,
                    self.instrument_map_sha256,
                    self.calendar_sha256,
                )
            )
        )

    @property
    def binding_sha256(self) -> str:
        return _digest(
            dict(
                calendar=self.calendar_sha256,
                instrument_map=self.instrument_map_sha256,
                input_manifest=self.input_manifest_sha256,
                model=self.model_sha256,
                cohort=COHORT_SHA256,
                arm=ARM,
                anchor=self.input_anchor_date.isoformat(),
                as_of=self.as_of.isoformat(),
                observations=[
                    [key, value.isoformat() if value is not None else None]
                    for key, value in sorted(self.observed_at_by_key.items())
                ],
                references=vars(self.references),
            )
        )


def _validate_envelope(envelope: SessionEnvelope) -> None:
    _require(type(envelope) is SessionEnvelope)
    plan = envelope.plan
    _require(
        envelope.model_sha256 == MODEL_SHA256
        and envelope.instrument_map_sha256 == instrument_map_sha256(envelope.instruments)
        and envelope.calendar_sha256 == calendar_sha256(plan)
        and tuple(sorted(envelope.instruments)) == plan.keys
        and tuple(sorted(envelope.observed_at_by_key)) == plan.keys
        and type(envelope.references) is DecisionReceiptReferences
        and envelope.references.input_manifest_ref == envelope.input_manifest_sha256
    )
    _require(envelope.input_anchor_date == plan.sessions[-2], Reason.STALE)
    _require(plan.close_clocks[-2] <= _utc(envelope.as_of), Reason.STALE)
    _require(envelope.as_of < plan.open_clocks[-1], Reason.LATE)
    for observed in envelope.observed_at_by_key.values():
        if observed is not None:
            _require(_utc(observed) <= envelope.as_of, Reason.FUTURE)
            _require(observed >= plan.close_clocks[-2], Reason.STALE)


@dataclass(frozen=True, slots=True, repr=False)
class ScoringBatch:
    keys: tuple[str, ...]
    sequences: tuple[tuple[tuple[float, float], ...], ...]


@dataclass(frozen=True, slots=True, repr=False)
class SessionDecision:
    envelope: SessionEnvelope
    reason: Reason
    feature_seal: feature.FeatureSeal | None = None
    scores: tuple[tuple[str, float], ...] = ()
    selected_key: str | None = None
    model_started_at: datetime | None = None
    model_completed_at: datetime | None = None
    proposal: TargetExposureProposal | None = None
    receipt: ResearchDecisionReceipt | None = None

    def __post_init__(self) -> None:
        _require(isinstance(self.reason, Reason))
        object.__setattr__(self, "scores", tuple(self.scores))
        if self.reason is not Reason.PREPARED:
            _require(self.proposal is None and self.receipt is None and self.selected_key is None)
            return
        _validate_envelope(self.envelope)
        _require(
            type(self.envelope) is SessionEnvelope
            and isinstance(self.feature_seal, feature.FeatureSeal)
            and self.feature_seal.plan == self.envelope.plan
            and self.feature_seal.entry_index == 112
            and self.feature_seal.include_sequence
            and tuple(key for key, _ in self.scores) == self.feature_seal.eligible_keys
            and len(self.scores) >= 10
            and all(
                (row.symbol, row.market)
                == (
                    self.envelope.instruments[row.key].symbol,
                    self.envelope.instruments[row.key].market,
                )
                and self.envelope.observed_at_by_key[row.key] is not None
                for row in self.feature_seal.rows
            )
            and all(
                type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
                for _, value in self.scores
            )
            and self.selected_key == min(self.scores, key=lambda row: (-row[1], row[0]))[0]
            and type(self.proposal) is TargetExposureProposal
            and type(self.receipt) is ResearchDecisionReceipt
        )
        _require(
            self.envelope.as_of <= _utc(self.model_started_at) <= _utc(self.model_completed_at)
            and self.envelope.as_of < self.model_completed_at < self.envelope.plan.open_clocks[-1]
            and self.proposal.action == "enter"
            and self.proposal.target_exposure == Decimal(".01")
            and self.proposal.confidence == 0
            and self.proposal.feature_schema_id == FEATURE_SCHEMA_ID
            and self.proposal.input_status == "ready"
            and self.proposal.decided_at == self.model_completed_at
            and self.proposal.valid_until == self.envelope.plan.close_clocks[-1]
            and self.proposal.feature_window_end == self.envelope.plan.close_clocks[-2]
            and self.proposal.symbol == self.envelope.instruments[self.selected_key].symbol
            and self.proposal.market == "US"
            and self.proposal.proposal_id == self.envelope.references.proposal_ref
            and self.receipt
            == receipt_from_target_exposure_proposal(
                self.proposal, references=self.envelope.references
            )
        )

    @property
    def status(self) -> str:
        return "prepared" if self.proposal is not None else "no_intent"

    def safe_facts(self) -> dict:
        return dict(
            status=self.status,
            reason=self.reason.value,
            eligible_count=len(self.feature_seal.rows) if self.feature_seal is not None else 0,
            original_key_count=128,
            metadata_calendar_count=113,
            input_scheduled_session_count=100,
            prior_context_count=61,
            sequence_context_count=20,
            fits=0,
            automatic_order=False,
            confidence_calibrated=False,
            historical_PIT_claim=False,
        )


def _screen(bars: tuple[Bar, ...]) -> bool:
    if Fraction(bars[-1].close) < 5:
        return False
    if not all(
        isinstance(bar.volume, Decimal) and bar.volume.is_finite() and bar.volume >= 0
        for bar in bars
    ):
        return False
    volumes = sorted(Fraction(bar.close) * Fraction(bar.volume) for bar in bars)
    return (volumes[9] + volumes[10]) / 2 >= 5_000_000 and all(
        abs(Fraction(later.close) / Fraction(prior.close) - 1) < Fraction(1, 2)
        for prior, later in zip(bars, bars[1:], strict=False)
    )


def _freeze(envelope: SessionEnvelope, past_source) -> feature.FeatureSeal:
    plan = envelope.plan
    days = plan.sessions[51:112]
    captured = {}

    def past(key, day):
        _require(key in plan.keys and day in days and (key, day) not in captured)
        observed = envelope.observed_at_by_key[key]
        value = past_source(key, day) if observed is not None else None
        if value is not None:
            _require(isinstance(value, Bar), Reason.IDENTITY)
            # Own scalar fields before later callbacks can mutate the provider object.
            value = Bar(
                symbol=value.symbol,
                market=value.market,
                timeframe=value.timeframe,
                start_ts=value.start_ts,
                open=value.open,
                high=value.high,
                low=value.low,
                close=value.close,
                volume=value.volume,
                complete=value.complete,
                schema_version=value.schema_version,
            )
            identity = envelope.instruments[key]
            _require(
                value.symbol == identity.symbol and value.market == identity.market, Reason.IDENTITY
            )
        captured[key, day] = value
        return value

    # Core Decimal intermediates cannot inherit a caller's low precision/traps.
    with localcontext(Context(prec=28)):
        original = feature.features(plan, 112, past, include_sequence=True)
    _require(len(captured) == 128 * 61)
    rows = tuple(
        row for row in original.rows if _screen(tuple(captured[row.key, day] for day in days[-20:]))
    )
    means = tuple(math.fsum(row.values[j] / len(rows) for row in rows) for j in range(3))
    rows = tuple(
        feature.StockRow(
            row.key,
            row.symbol,
            row.market,
            tuple(row.values[j] - means[j] for j in range(3)) + (row.values[3],),
            row.sequence,
        )
        for row in rows
    )
    keys = {row.key for row in rows}
    return feature.FeatureSeal(
        plan, 112, rows, tuple(key for key in plan.keys if key not in keys), True
    )


def decide_session(
    envelope: SessionEnvelope,
    past_source: Callable[[str, date], Bar | None],
    *,
    scorer: Callable[[ScoringBatch], Mapping[str, float]],
    clock: Callable[[], datetime],
) -> SessionDecision:
    """Freeze cohort first; trusted scorer gets only immutable past sequences.

    The caller reattests bytes and distinct persisted session/proposal identities.
    No calendar acquisition, model decoding, persistence or broker access occurs.
    """
    seal, scores, started, completed = None, (), None, None
    try:
        _validate_envelope(envelope)
        plan = envelope.plan
        _require(callable(past_source) and callable(scorer) and callable(clock))
        now = _utc(clock())
        _require(now >= envelope.as_of, Reason.CLOCK)
        _require(now < plan.open_clocks[-1], Reason.LATE)
        try:
            seal = _freeze(envelope, past_source)
        except _Fault:
            raise
        except Exception:
            raise _Fault(Reason.MISSING) from None
        _require(len(seal.rows) >= 10, Reason.FEWER)
        started = _utc(clock())
        _require(now <= started, Reason.CLOCK)
        _require(started < plan.open_clocks[-1], Reason.LATE)
        batch = ScoringBatch(seal.eligible_keys, seal.sequences)
        try:
            supplied = scorer(batch)
        except Exception:
            raise _Fault(Reason.SCORER) from None
        completed = _utc(clock())
        _require(started <= completed and envelope.as_of < completed, Reason.CLOCK)
        _require(completed < plan.open_clocks[-1], Reason.LATE)
        _require(isinstance(supplied, Mapping) and set(supplied) == set(batch.keys), Reason.SCORES)
        bound = []
        for key in batch.keys:
            value = supplied[key]
            _require(
                type(value) in (int, float) and math.isfinite(float(value)) and 0 <= value <= 1,
                Reason.SCORES,
            )
            bound.append((key, float(value)))
        scores = tuple(bound)
        selected = min(scores, key=lambda row: (-row[1], row[0]))[0]
        instrument = envelope.instruments[selected]
        proposal = TargetExposureProposal(
            proposal_id=envelope.references.proposal_ref,
            symbol=instrument.symbol,
            market=instrument.market,
            action="enter",
            target_exposure=Decimal(".01"),
            confidence=Decimal(0),
            feature_schema_id=FEATURE_SCHEMA_ID,
            input_status="ready",
            decided_at=completed,
            valid_until=plan.close_clocks[-1],
            feature_window_end=plan.close_clocks[-2],
            reason="source_prototype_session_enter_no_automatic_order",
        )
        return SessionDecision(
            envelope,
            Reason.PREPARED,
            seal,
            scores,
            selected,
            started,
            completed,
            proposal,
            receipt_from_target_exposure_proposal(proposal, references=envelope.references),
        )
    except _Fault as error:
        return SessionDecision(envelope, error.reason, seal, scores, None, started, completed)
    except Exception:
        return SessionDecision(envelope, Reason.CONTRACT, seal, scores, None, started, completed)
