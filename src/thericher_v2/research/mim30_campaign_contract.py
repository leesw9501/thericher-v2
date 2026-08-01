"""Pure frozen contract for the MIM-30 SPY long-only derivative.

This module defines a research hypothesis only.  It deliberately performs no
market-data access, training, artifact I/O, network access, KIS access,
execution, or model work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Literal

MIM30_CAMPAIGN_ID = "mim30-spy-long-only-derivative-v1"
MIM30_SOURCE_TITLE = "Market intraday momentum"
MIM30_SOURCE_DOI = "10.1016/j.jfineco.2018.05.009"
MIM30_SOURCE_SSRN_ID = "2440866"
MIM30_SOURCE_SAMPLE_START = date(1993, 2, 1)
MIM30_SOURCE_SAMPLE_END = date(2013, 12, 31)
MIM30_MINIMUM_QUALIFYING_SESSIONS = 252
MIM30_MINIMUM_SEALED_ENTRIES = 30


@dataclass(frozen=True)
class Mim30SourceReference:
    """Short identifiers and stated scope for the source finding."""

    title: str = MIM30_SOURCE_TITLE
    doi: str = MIM30_SOURCE_DOI
    ssrn_id: str = MIM30_SOURCE_SSRN_ID
    sample_start: date = MIM30_SOURCE_SAMPLE_START
    sample_end: date = MIM30_SOURCE_SAMPLE_END
    primary_instrument: str = "SPY"
    sample_granularity: str = "high_frequency"
    publisher_rights: str = "Elsevier B.V. copyright; source used as a research reference"

    def __post_init__(self) -> None:
        if (
            self.title != MIM30_SOURCE_TITLE
            or self.doi != MIM30_SOURCE_DOI
            or self.ssrn_id != MIM30_SOURCE_SSRN_ID
            or self.sample_start != MIM30_SOURCE_SAMPLE_START
            or self.sample_end != MIM30_SOURCE_SAMPLE_END
            or self.primary_instrument != "SPY"
            or self.sample_granularity != "high_frequency"
            or not self.publisher_rights
        ):
            raise ValueError("MIM30 source reference must remain frozen")


@dataclass(frozen=True)
class Mim30SessionContract:
    """Source research window geometry, expressed in New York time."""

    timezone: str = "America/New_York"
    timeframe: str = "1m"
    prior_regular_close: time = time(16, 0)
    signal_cutoff: time = time(10, 0)
    entry_time: time = time(15, 30)
    exit_time: time = time(16, 0)
    require_completed_bars: bool = True
    exclude_early_prior_session: bool = True
    exclude_early_trade_session: bool = True
    require_prior_regular_close: bool = True
    exact_source_execution_reproduction_claimed: bool = False

    def __post_init__(self) -> None:
        if (
            self.timezone != "America/New_York"
            or self.timeframe != "1m"
            or self.prior_regular_close != time(16, 0)
            or self.signal_cutoff != time(10, 0)
            or self.entry_time != time(15, 30)
            or self.exit_time != time(16, 0)
            or not self.require_completed_bars
            or not self.exclude_early_prior_session
            or not self.exclude_early_trade_session
            or not self.require_prior_regular_close
            or self.exact_source_execution_reproduction_claimed
        ):
            raise ValueError("MIM30 session contract must remain frozen")


@dataclass(frozen=True)
class Mim30SignalContract:
    """Long-only derivative of the source's directional strategy."""

    signal_definition: str = "previous_regular_close_to_current_1000_return"
    positive_signal_action: Literal["long"] = "long"
    nonpositive_signal_action: Literal["flat"] = "flat"
    shorting_allowed: bool = False
    source_replication: bool = False
    additional_filters: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "additional_filters", tuple(self.additional_filters))
        if (
            self.signal_definition != "previous_regular_close_to_current_1000_return"
            or self.positive_signal_action != "long"
            or self.nonpositive_signal_action != "flat"
            or self.shorting_allowed
            or self.source_replication
            or self.additional_filters
        ):
            raise ValueError("MIM30 is a filter-free long-only derivative, not a replication")


@dataclass(frozen=True)
class Mim30ChronologicalSplit:
    """Fixed non-overlapping 60/20/20 split applied after session qualification."""

    development_percent: int = 60
    validation_percent: int = 20
    sealed_percent: int = 20

    def __post_init__(self) -> None:
        if (
            self.development_percent,
            self.validation_percent,
            self.sealed_percent,
        ) != (60, 20, 20):
            raise ValueError("MIM30 chronological split must remain 60/20/20")

    def counts_for(self, qualifying_session_count: int) -> Mim30SplitCounts:
        if qualifying_session_count < MIM30_MINIMUM_QUALIFYING_SESSIONS:
            raise ValueError("MIM30 requires at least 252 qualifying sessions")
        development = qualifying_session_count * self.development_percent // 100
        validation = qualifying_session_count * self.validation_percent // 100
        sealed = qualifying_session_count - development - validation
        return Mim30SplitCounts(
            development_sessions=development,
            validation_sessions=validation,
            sealed_sessions=sealed,
        )


@dataclass(frozen=True)
class Mim30SplitCounts:
    """Resolved session counts; order is always development, validation, sealed."""

    development_sessions: int
    validation_sessions: int
    sealed_sessions: int

    def __post_init__(self) -> None:
        if min(
            self.development_sessions,
            self.validation_sessions,
            self.sealed_sessions,
        ) <= 0:
            raise ValueError("MIM30 split requires non-empty chronological partitions")

    @property
    def total_sessions(self) -> int:
        return self.development_sessions + self.validation_sessions + self.sealed_sessions


@dataclass(frozen=True)
class Mim30CostBand:
    """Fixed round-trip sensitivity band that a later execution attestation must explain."""

    multipliers: tuple[Decimal, ...] = (
        Decimal("1.0"),
        Decimal("1.5"),
        Decimal("2.0"),
    )
    round_trip_bps: tuple[Decimal, ...] = (
        Decimal("10"),
        Decimal("15"),
        Decimal("20"),
    )
    base_cost_semantics: str = "round_trip_total_bps_with_explicit_per_fill_breakdown"
    execution_attestation_required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "multipliers", tuple(self.multipliers))
        object.__setattr__(self, "round_trip_bps", tuple(self.round_trip_bps))
        if (
            self.multipliers != (Decimal("1.0"), Decimal("1.5"), Decimal("2.0"))
            or self.round_trip_bps != (Decimal("10"), Decimal("15"), Decimal("20"))
            or self.base_cost_semantics
            != "round_trip_total_bps_with_explicit_per_fill_breakdown"
            or not self.execution_attestation_required
        ):
            raise ValueError("MIM30 cost band must remain execution-attestation-required")

    @property
    def middle_multiplier(self) -> Decimal:
        return Decimal("1.5")


@dataclass(frozen=True)
class Mim30Comparators:
    """Predeclared controls evaluated on the same final-thirty-minute window."""

    ids: tuple[str, ...] = ("always_flat", "same_window_always_long")

    def __post_init__(self) -> None:
        object.__setattr__(self, "ids", tuple(self.ids))
        if self.ids != ("always_flat", "same_window_always_long"):
            raise ValueError("MIM30 comparators must remain fixed")


@dataclass(frozen=True)
class Mim30KillCondition:
    """Fixed minimum-n and sealed-result rejection rule with no retuning path."""

    minimum_qualifying_sessions: int = MIM30_MINIMUM_QUALIFYING_SESSIONS
    minimum_sealed_entries: int = MIM30_MINIMUM_SEALED_ENTRIES
    required_cost_multiplier: Decimal = Decimal("1.5")
    require_positive_after_cost: bool = True
    require_improvement_over: str = "same_window_always_long"
    retuning_allowed_after_rejection: bool = False

    def __post_init__(self) -> None:
        if (
            self.minimum_qualifying_sessions != MIM30_MINIMUM_QUALIFYING_SESSIONS
            or self.minimum_sealed_entries != MIM30_MINIMUM_SEALED_ENTRIES
            or self.required_cost_multiplier != Decimal("1.5")
            or not self.require_positive_after_cost
            or self.require_improvement_over != "same_window_always_long"
            or self.retuning_allowed_after_rejection
        ):
            raise ValueError("MIM30 kill condition must remain frozen and non-retunable")


@dataclass(frozen=True)
class Mim30ExecutionParityAttestation:
    """Explicit future execution facts required before interpreting cost-sensitive evidence.

    It documents the current local-paper incompatibility with the source close.
    It does not make this data/research contract eligible for Paper use.
    """

    entry_price_basis: str
    exit_price_basis: str
    latency_basis: str
    round_trip_bps: tuple[Decimal, ...]
    per_fill_bps: tuple[tuple[Decimal, Decimal], ...]
    close_or_auction_fill_available: bool
    source_window_compatible: bool
    attested_by_execution: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "round_trip_bps", tuple(self.round_trip_bps))
        object.__setattr__(self, "per_fill_bps", tuple(tuple(item) for item in self.per_fill_bps))
        if (
            not self.entry_price_basis
            or not self.exit_price_basis
            or not self.latency_basis
            or self.round_trip_bps != (Decimal("10"), Decimal("15"), Decimal("20"))
            or len(self.per_fill_bps) != len(self.round_trip_bps)
            or not self.attested_by_execution
        ):
            raise ValueError("MIM30 execution parity attestation is incomplete")
        if self.source_window_compatible:
            if not self.close_or_auction_fill_available:
                raise ValueError("source-window-compatible execution requires a close fill")
        elif (
            self.entry_price_basis != "next_completed_bar_open"
            or self.exit_price_basis != "terminal_1559_open"
            or self.latency_basis != "decision_to_next_completed_bar_open"
            or self.close_or_auction_fill_available
        ):
            raise ValueError("MIM30 current proxy execution facts are invalid")
        for per_fill, round_trip_bps in zip(
            self.per_fill_bps,
            self.round_trip_bps,
            strict=True,
        ):
            if len(per_fill) != 2:
                raise ValueError("MIM30 per-fill cost must name entry and exit")
            entry_bps, exit_bps = per_fill
            if min(entry_bps, exit_bps) < 0 or entry_bps + exit_bps != round_trip_bps:
                raise ValueError("MIM30 per-fill and round-trip costs disagree")


@dataclass(frozen=True)
class Mim30SealedEvidence:
    """Aggregate Boolean evidence supplied by a later evaluator, never loaded here."""

    qualifying_session_count: int
    sealed_session_count: int
    sealed_entry_count: int
    observed_cost_multipliers: tuple[Decimal, ...]
    execution_parity_attestation: Mim30ExecutionParityAttestation | None
    positive_after_cost_at_middle_band: bool | None
    beats_same_window_always_long_at_middle_band: bool | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_cost_multipliers", tuple(self.observed_cost_multipliers))
        counts = (
            self.qualifying_session_count,
            self.sealed_session_count,
            self.sealed_entry_count,
        )
        if min(counts) < 0:
            raise ValueError("MIM30 sealed evidence counts must be non-negative")


@dataclass(frozen=True)
class Mim30EvidenceDecision:
    """Pure disposition; it cannot create a trading, model, or execution action."""

    disposition: Literal["input_unavailable", "rejected", "not_rejected"]
    reasons: tuple[str, ...]
    retuning_allowed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if not self.reasons or self.retuning_allowed:
            raise ValueError("MIM30 evidence decision must retain reasons and forbid retuning")


@dataclass(frozen=True)
class Mim30CampaignContract:
    """The complete frozen contract for a future MIM-30 evaluation."""

    campaign_id: str = MIM30_CAMPAIGN_ID
    symbol: str = "SPY"
    market: str = "AMS"
    source: Mim30SourceReference = Mim30SourceReference()
    session: Mim30SessionContract = Mim30SessionContract()
    signal: Mim30SignalContract = Mim30SignalContract()
    split: Mim30ChronologicalSplit = Mim30ChronologicalSplit()
    costs: Mim30CostBand = Mim30CostBand()
    comparators: Mim30Comparators = Mim30Comparators()
    kill_condition: Mim30KillCondition = Mim30KillCondition()
    paper_eligible: bool = False
    later_execution_reattestation_required: bool = True

    def __post_init__(self) -> None:
        if (
            self.campaign_id != MIM30_CAMPAIGN_ID
            or self.symbol != "SPY"
            or self.market != "AMS"
            or self.paper_eligible
            or not self.later_execution_reattestation_required
        ):
            raise ValueError("MIM30 campaign identity must remain frozen")

    @property
    def contract_hash(self) -> str:
        encoded = json.dumps(
            self.to_payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def assess_sealed_evidence(self, evidence: Mim30SealedEvidence) -> Mim30EvidenceDecision:
        """Classify aggregate evidence against the fixed no-retuning condition."""

        required_counts = self.split.counts_for(evidence.qualifying_session_count) if (
            evidence.qualifying_session_count >= self.kill_condition.minimum_qualifying_sessions
        ) else None
        if required_counts is None:
            return Mim30EvidenceDecision(
                disposition="input_unavailable",
                reasons=("insufficient_qualifying_sessions",),
                retuning_allowed=False,
            )
        if evidence.sealed_session_count < required_counts.sealed_sessions:
            return Mim30EvidenceDecision(
                disposition="input_unavailable",
                reasons=("insufficient_sealed_sessions",),
                retuning_allowed=False,
            )
        if evidence.execution_parity_attestation is None:
            return Mim30EvidenceDecision(
                disposition="input_unavailable",
                reasons=("execution_parity_attestation_required",),
                retuning_allowed=False,
            )
        if not evidence.execution_parity_attestation.source_window_compatible:
            return Mim30EvidenceDecision(
                disposition="input_unavailable",
                reasons=("source_execution_window_unavailable",),
                retuning_allowed=False,
            )
        if evidence.observed_cost_multipliers != self.costs.multipliers:
            return Mim30EvidenceDecision(
                disposition="input_unavailable",
                reasons=("fixed_cost_band_not_observed",),
                retuning_allowed=False,
            )

        rejection_reasons: list[str] = []
        if evidence.sealed_entry_count < self.kill_condition.minimum_sealed_entries:
            rejection_reasons.append("insufficient_sealed_entries")
        if evidence.positive_after_cost_at_middle_band is not True:
            rejection_reasons.append("not_positive_after_cost_at_1_5x")
        if evidence.beats_same_window_always_long_at_middle_band is not True:
            rejection_reasons.append("does_not_beat_same_window_always_long_at_1_5x")
        if rejection_reasons:
            return Mim30EvidenceDecision(
                disposition="rejected",
                reasons=tuple(rejection_reasons),
                retuning_allowed=False,
            )
        return Mim30EvidenceDecision(
            disposition="not_rejected",
            reasons=("fixed_kill_condition_not_triggered",),
            retuning_allowed=False,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "instrument": {"symbol": self.symbol, "market": self.market},
            "source": {
                "title": self.source.title,
                "doi": self.source.doi,
                "ssrn_id": self.source.ssrn_id,
                "sample_start": self.source.sample_start.isoformat(),
                "sample_end": self.source.sample_end.isoformat(),
                "primary_instrument": self.source.primary_instrument,
                "sample_granularity": self.source.sample_granularity,
                "publisher_rights": self.source.publisher_rights,
            },
            "session": {
                "timezone": self.session.timezone,
                "timeframe": self.session.timeframe,
                "prior_regular_close": self.session.prior_regular_close.isoformat(),
                "signal_cutoff": self.session.signal_cutoff.isoformat(),
                "entry_time": self.session.entry_time.isoformat(),
                "exit_time": self.session.exit_time.isoformat(),
                "require_completed_bars": self.session.require_completed_bars,
                "exclude_early_prior_session": self.session.exclude_early_prior_session,
                "exclude_early_trade_session": self.session.exclude_early_trade_session,
                "require_prior_regular_close": self.session.require_prior_regular_close,
                "exact_source_execution_reproduction_claimed": (
                    self.session.exact_source_execution_reproduction_claimed
                ),
            },
            "signal": {
                "definition": self.signal.signal_definition,
                "positive_signal_action": self.signal.positive_signal_action,
                "nonpositive_signal_action": self.signal.nonpositive_signal_action,
                "shorting_allowed": self.signal.shorting_allowed,
                "source_replication": self.signal.source_replication,
                "additional_filters": list(self.signal.additional_filters),
            },
            "chronological_split": {
                "development_percent": self.split.development_percent,
                "validation_percent": self.split.validation_percent,
                "sealed_percent": self.split.sealed_percent,
            },
            "cost_band": {
                "multipliers": [str(multiplier) for multiplier in self.costs.multipliers],
                "round_trip_bps": [str(bps) for bps in self.costs.round_trip_bps],
                "base_cost_semantics": self.costs.base_cost_semantics,
                "execution_attestation_required": self.costs.execution_attestation_required,
            },
            "comparators": list(self.comparators.ids),
            "kill_condition": {
                "minimum_qualifying_sessions": self.kill_condition.minimum_qualifying_sessions,
                "minimum_sealed_entries": self.kill_condition.minimum_sealed_entries,
                "required_cost_multiplier": str(self.kill_condition.required_cost_multiplier),
                "require_positive_after_cost": self.kill_condition.require_positive_after_cost,
                "require_improvement_over": self.kill_condition.require_improvement_over,
                "retuning_allowed_after_rejection": (
                    self.kill_condition.retuning_allowed_after_rejection
                ),
            },
            "scope": {
                "training_allowed": False,
                "data_load_allowed": False,
                "network_allowed": False,
                "artifact_write_allowed": False,
                "kis_allowed": False,
                "execution_allowed": False,
                "model_path_allowed": False,
                "paper_eligible": self.paper_eligible,
                "later_execution_reattestation_required": (
                    self.later_execution_reattestation_required
                ),
            },
        }


def build_mim30_campaign_contract() -> Mim30CampaignContract:
    """Return the only supported MIM-30 campaign-contract identity."""

    return Mim30CampaignContract()
