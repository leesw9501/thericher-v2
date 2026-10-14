"""Pure frozen-five ordinal targets for a provisional Paper baseline.

Only caller-attested, independently checked supported rows enter the common
pool. No model loading, calendar acquisition, accounts, sizing or orders live
here. Publication clocks come from bound producer receipts, never file mtimes.
Targets are desired fractions of the ORIGINAL basis, not allocated cash or
risk permission. Native Execution may reduce or reject every proposal.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Final

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

MODELS: Final = ("ridge_raw20", "ridge_indicator", "mlp20", "tcn20", "tcn60")
FEATURE_SCHEMA_ID: Final = "current-nas-frozen5-fixed-ordinal-mean-top10-sleeve-v1"
RESEARCH_GROSS: Final = Decimal("0.5")
RESEARCH_NAME_CAP: Final = Decimal("0.1")
RESEARCH_WEIGHT: Final = Decimal("0.05")
ORIGINAL_BASIS_GROSS: Final = Decimal("0.05")
ORIGINAL_BASIS_WEIGHT: Final = Decimal("0.005")
_PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_SYMBOL = re.compile(r"[A-Z]{1,10}", re.ASCII)


def _require(ok: bool, category: str) -> None:
    if not ok:
        raise ValueError(category)


def _utc(value: datetime) -> datetime:
    _require(type(value) is datetime and value.utcoffset() == timedelta(0), "clock_invalid")
    return require_utc(value)


def _pin(value: str) -> None:
    _require(type(value) is str and _PIN.fullmatch(value) is not None, "source_pin_invalid")


@dataclass(frozen=True, slots=True, repr=False)
class SupportedScore:
    """One frozen NAS512 slot; normalize NumPy scalars explicitly upstream."""

    slot: int
    symbol: str
    risk_scores: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        _require(type(self.slot) is int and 0 <= self.slot < 512, "slot_invalid")
        _require(
            type(self.symbol) is str
            and _SYMBOL.fullmatch(self.symbol) is not None
            and self.symbol not in {"SPY", "QQQ", "TLT", "GLD"},
            "NAS_stock_identity_required",
        )
        _require(
            type(self.risk_scores) is tuple
            and len(self.risk_scores) == len(MODELS)
            and all(type(value) is Decimal and value.is_finite() for value in self.risk_scores),
            "all_five_scores_finite",
        )


@dataclass(frozen=True, slots=True, repr=False)
class FrozenScoreMetadata:
    """Caller-attested source identities and distinct causal event meanings.

    Producer refs must bind these publication/completion clocks to the exact
    input/score bytes. This type checks shape/order, not receipt authenticity,
    PIT coverage, provider finality, listing support or profitability.
    """

    score_ref: str
    input_ref: str
    independent_readback_ref: str
    data_producer_ref: str
    score_producer_ref: str
    feature_window_end: datetime
    data_first_available_at: datetime
    input_asof: datetime
    inference_completed_at: datetime
    score_first_available_at: datetime

    def __post_init__(self) -> None:
        for value in (
            self.score_ref,
            self.input_ref,
            self.independent_readback_ref,
            self.data_producer_ref,
            self.score_producer_ref,
        ):
            _pin(value)
        clocks = tuple(
            _utc(value)
            for value in (
                self.feature_window_end,
                self.data_first_available_at,
                self.input_asof,
                self.inference_completed_at,
                self.score_first_available_at,
            )
        )
        _require(clocks == tuple(sorted(clocks)), "causal_score_clocks_required")


@dataclass(frozen=True, slots=True, repr=False)
class FrozenScoreInput:
    rows: tuple[SupportedScore, ...]
    models: tuple[str, ...]
    metadata: FrozenScoreMetadata


@dataclass(frozen=True, slots=True, repr=False)
class PreparedTarget:
    slot: int
    mean_ordinal_rank: Fraction
    research_weight: Decimal
    proposal: TargetExposureProposal
    receipt: ResearchDecisionReceipt
    metadata: FrozenScoreMetadata


def prepare_targets(
    panel: FrozenScoreInput,
    *,
    intended_session: SessionWindow,
    latest_completed_close: datetime,
    official_calendar_ref: str,
    decided_at: datetime,
    valid_until: datetime,
) -> tuple[PreparedTarget, ...]:
    """Select fixed top10 and emit untrusted desired-exposure proposals only.

    The caller attests that the calendar ref binds this intended official
    session and its immediate previous completed close. Preparation may occur
    before OPEN; this does not authorize an off-session order. Missing rows
    stay missing, and downstream route/funding failures never select backups.
    Confidence zero means uncalibrated, not an instruction to bypass Risk.
    """
    _require(type(panel) is FrozenScoreInput, "score_input_invalid")
    _require(type(panel.models) is tuple and panel.models == MODELS, "exact_five_models_required")
    _require(type(panel.metadata) is FrozenScoreMetadata, "score_metadata_required")
    metadata = panel.metadata
    metadata.__post_init__()
    _pin(official_calendar_ref)
    _require(type(intended_session) is SessionWindow, "intended_session_required")
    opened, closed = _utc(intended_session.open_ts), _utc(intended_session.close_ts)
    previous, at, until = map(_utc, (latest_completed_close, decided_at, valid_until))
    _require(
        metadata.feature_window_end == previous
        and previous < opened < closed
        and metadata.score_first_available_at <= at
        and max(at, opened) < until <= closed,
        "causal_intended_session_required",
    )
    _require(type(panel.rows) is tuple and len(panel.rows) >= 128, "supported_pool_insufficient")
    slots, symbols = set(), set()
    for row in panel.rows:
        _require(type(row) is SupportedScore, "score_row_invalid")
        row.__post_init__()
        _require(row.slot not in slots and row.symbol not in symbols, "duplicate_slot_or_symbol")
        slots.add(row.slot)
        symbols.add(row.symbol)
    _require(sum(slot >= 128 for slot in slots) >= 64, "outside_first128_insufficient")

    # Fraction avoids ambient Decimal rounding, including unary negation ties.
    totals = dict.fromkeys(slots, 0)
    for expert in range(len(MODELS)):
        ordered = sorted(panel.rows, key=lambda row: (-Fraction(row.risk_scores[expert]), row.slot))
        for ordinal, row in enumerate(ordered, 1):
            totals[row.slot] += ordinal
    selected = sorted(panel.rows, key=lambda row: (totals[row.slot], row.slot))[:10]
    controls = {
        "schema": FEATURE_SCHEMA_ID,
        "models": MODELS,
        "refs": [
            metadata.score_ref,
            metadata.input_ref,
            metadata.independent_readback_ref,
            metadata.data_producer_ref,
            metadata.score_producer_ref,
            official_calendar_ref,
        ],
        "clocks": [
            value.isoformat()
            for value in (
                metadata.feature_window_end,
                metadata.data_first_available_at,
                metadata.input_asof,
                metadata.inference_completed_at,
                metadata.score_first_available_at,
                previous,
                opened,
                closed,
                at,
                until,
            )
        ],
        "rows": [
            [row.slot, row.symbol, [str(Fraction(value)) for value in row.risk_scores]]
            for row in sorted(panel.rows, key=lambda row: row.slot)
        ],
        "research_gross": str(RESEARCH_GROSS),
        "research_name_cap": str(RESEARCH_NAME_CAP),
        "original_basis_weight": str(ORIGINAL_BASIS_WEIGHT),
    }
    policy_hash = hashlib.sha256(
        json.dumps(controls, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "ascii"
        )
    ).hexdigest()
    references = DecisionReceiptReferences(
        campaign_ref="ref:" + policy_hash,
        model_ref="ref:" + metadata.score_ref[7:],
        input_manifest_ref=metadata.input_ref,
        proposal_ref="ref:" + policy_hash,
    )
    results = []
    for row in selected:
        proposal = TargetExposureProposal(
            proposal_id=f"current-nas-{policy_hash}-{row.slot}",
            symbol=row.symbol,
            market="US",
            action="enter",
            target_exposure=ORIGINAL_BASIS_WEIGHT,
            confidence=Decimal("0"),
            feature_schema_id=FEATURE_SCHEMA_ID,
            input_status="ready",
            decided_at=at,
            valid_until=until,
            feature_window_end=metadata.feature_window_end,
            reason="fixed_five_ordinal_mean_untrusted_uncalibrated_not_profit_qualified",
        )
        results.append(
            PreparedTarget(
                slot=row.slot,
                mean_ordinal_rank=Fraction(totals[row.slot], len(MODELS)),
                research_weight=RESEARCH_WEIGHT,
                proposal=proposal,
                receipt=receipt_from_target_exposure_proposal(proposal, references=references),
                metadata=metadata,
            )
        )
    return tuple(results)
