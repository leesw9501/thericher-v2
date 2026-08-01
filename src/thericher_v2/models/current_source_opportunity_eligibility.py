"""Monotone current-source validation for an upstream opportunity fact.

This module is deliberately not a universe, ranking, liquidity, data-loading,
or broker interface. It only lets a caller preserve an already-eligible
opportunity when a matching current source contract remains usable.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from thericher_v2.contracts import Bar, TargetInputStatus, require_utc
from thericher_v2.models.target_position_policy import OpportunityEligibility

CAUSAL_BAR_SOURCE_CONTRACT_SCHEMA_ID = "causal-bar-source-contract-v1"
_COMPACT_IDENTIFIER: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", re.ASCII)
_SHA256_REFERENCE: Final = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_INPUT_STATUSES: Final = frozenset(
    {
        "ready",
        "missing",
        "stale",
        "incomplete",
        "duplicate",
        "non_contiguous",
        "misaligned",
        "future",
        "unqualified",
    }
)


@dataclass(frozen=True, slots=True)
class CurrentSourceContract:
    """The caller-pinned identity of one current source contract."""

    contract_id: str
    contract_hash: str

    def __post_init__(self) -> None:
        if _COMPACT_IDENTIFIER.fullmatch(self.contract_id) is None:
            raise ValueError("source contract_id must be a compact stable identifier")
        if _SHA256_REFERENCE.fullmatch(self.contract_hash) is None:
            raise ValueError("source contract_hash must be a lowercase sha256 reference")


@dataclass(frozen=True, slots=True)
class CurrentSourceMetadata:
    """Caller-owned categorical status for the source of one opportunity."""

    contract: CurrentSourceContract
    symbol: str
    market: str
    input_status: TargetInputStatus
    complete: bool
    observed_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.contract, CurrentSourceContract):
            raise TypeError("source contract must be a CurrentSourceContract")
        if not self.symbol.strip() or not self.market.strip():
            raise ValueError("source symbol and market must be nonempty")
        if self.input_status not in _INPUT_STATUSES:
            raise ValueError("source input_status is invalid")
        if not isinstance(self.complete, bool):
            raise TypeError("source complete must be boolean")
        observed_at = require_utc(self.observed_at, "source observed_at")
        valid_until = require_utc(self.valid_until, "source valid_until")
        if valid_until < observed_at:
            raise ValueError("source validity is invalid")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "valid_until", valid_until)


@dataclass(frozen=True, slots=True)
class CurrentSourceOpportunityEligibility:
    """A source-attested, non-expansive projection of an upstream candidate."""

    upstream_candidate: OpportunityEligibility
    source: CurrentSourceMetadata
    expected_contract: CurrentSourceContract
    as_of: datetime
    eligibility: OpportunityEligibility
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.upstream_candidate, OpportunityEligibility):
            raise TypeError("upstream_candidate must be an OpportunityEligibility")
        if not isinstance(self.source, CurrentSourceMetadata):
            raise TypeError("source must be a CurrentSourceMetadata")
        if not isinstance(self.expected_contract, CurrentSourceContract):
            raise TypeError("expected_contract must be a CurrentSourceContract")
        if not isinstance(self.eligibility, OpportunityEligibility):
            raise TypeError("eligibility must be an OpportunityEligibility")
        now = require_utc(self.as_of, "as_of")
        object.__setattr__(self, "as_of", now)
        expected_eligibility, expected_reason = _project_eligibility(
            self.upstream_candidate,
            self.source,
            expected_contract=self.expected_contract,
            as_of=now,
        )
        if self.eligibility != expected_eligibility or self.reason != expected_reason:
            raise ValueError("eligibility must match the deterministic monotone projection")

    @property
    def eligible(self) -> bool:
        """Expose the projected eligibility without granting a new candidate."""

        return self.eligibility.eligible

    @property
    def input_status(self) -> TargetInputStatus:
        """Expose the projected categorical input status."""

        return self.eligibility.input_status


def build_causal_bar_source_contract(
    bars: Sequence[Bar],
    *,
    contract_id: str,
    as_of: datetime,
) -> CurrentSourceContract:
    """Hash only the completed source-bar prefix observable at ``as_of``."""

    cutoff = require_utc(as_of, "as_of")
    normalized_bars = tuple(bars)
    if any(not isinstance(bar, Bar) for bar in normalized_bars):
        raise TypeError("bars must contain Bar values")
    prefix = tuple(bar for bar in normalized_bars if bar.end_ts <= cutoff)
    payload = {
        "schema_id": CAUSAL_BAR_SOURCE_CONTRACT_SCHEMA_ID,
        "as_of": cutoff.isoformat(),
        "bars": [_bar_payload(bar) for bar in sorted(prefix, key=_bar_sort_key)],
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return CurrentSourceContract(
        contract_id=contract_id,
        contract_hash=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
    )


def adapt_current_source_opportunity_eligibility(
    upstream_candidate: OpportunityEligibility,
    source: CurrentSourceMetadata,
    *,
    expected_contract: CurrentSourceContract,
    as_of: datetime,
) -> CurrentSourceOpportunityEligibility:
    """Preserve or downgrade one candidate using current-source facts only.

    The result retains the upstream opportunity reference and can never make a
    false candidate eligible. It does not select symbols or create a target.
    """

    if not isinstance(upstream_candidate, OpportunityEligibility):
        raise TypeError("upstream_candidate must be an OpportunityEligibility")
    if not isinstance(source, CurrentSourceMetadata):
        raise TypeError("source must be a CurrentSourceMetadata")
    if not isinstance(expected_contract, CurrentSourceContract):
        raise TypeError("expected_contract must be a CurrentSourceContract")
    now = require_utc(as_of, "as_of")
    eligibility, reason = _project_eligibility(
        upstream_candidate,
        source,
        expected_contract=expected_contract,
        as_of=now,
    )
    return CurrentSourceOpportunityEligibility(
        upstream_candidate=upstream_candidate,
        source=source,
        expected_contract=expected_contract,
        as_of=now,
        eligibility=eligibility,
        reason=reason,
    )


def _project_eligibility(
    upstream_candidate: OpportunityEligibility,
    source: CurrentSourceMetadata,
    *,
    expected_contract: CurrentSourceContract,
    as_of: datetime,
) -> tuple[OpportunityEligibility, str]:
    status, reason = _effective_status(
        upstream_candidate,
        source,
        expected_contract=expected_contract,
        as_of=as_of,
    )
    if status == "ready" and upstream_candidate.eligible:
        observed_at = max(upstream_candidate.observed_at, source.observed_at)
        valid_until = min(upstream_candidate.valid_until, source.valid_until)
        return (
            OpportunityEligibility(
                opportunity_ref=upstream_candidate.opportunity_ref,
                symbol=upstream_candidate.symbol,
                market=upstream_candidate.market,
                eligible=True,
                input_status="ready",
                observed_at=observed_at,
                valid_until=valid_until,
            ),
            reason,
        )
    return (
        OpportunityEligibility(
            opportunity_ref=upstream_candidate.opportunity_ref,
            symbol=upstream_candidate.symbol,
            market=upstream_candidate.market,
            eligible=False,
            input_status=status,
            observed_at=as_of,
            valid_until=as_of,
        ),
        reason,
    )


def _effective_status(
    upstream_candidate: OpportunityEligibility,
    source: CurrentSourceMetadata,
    *,
    expected_contract: CurrentSourceContract,
    as_of: datetime,
) -> tuple[TargetInputStatus, str]:
    if upstream_candidate.input_status != "ready":
        return upstream_candidate.input_status, f"upstream_{upstream_candidate.input_status}"
    if as_of < upstream_candidate.observed_at:
        return "future", "upstream_future"
    if as_of > upstream_candidate.valid_until:
        return "stale", "upstream_stale"
    if source.contract != expected_contract:
        return "misaligned", "source_contract_mismatch"
    if source.symbol != upstream_candidate.symbol or source.market != upstream_candidate.market:
        return "misaligned", "source_symbol_market_mismatch"
    if source.input_status != "ready":
        return source.input_status, f"source_{source.input_status}"
    if not source.complete:
        return "incomplete", "source_incomplete"
    if as_of < source.observed_at:
        return "future", "source_future"
    if as_of > source.valid_until:
        return "stale", "source_stale"
    if not upstream_candidate.eligible:
        return "ready", "upstream_ineligible"
    return "ready", "source_compatible"


def _bar_payload(bar: Bar) -> dict[str, str | bool | int]:
    return {
        "symbol": bar.symbol,
        "market": bar.market,
        "timeframe": bar.timeframe.value,
        "start_ts": bar.start_ts.isoformat(),
        "end_ts": bar.end_ts.isoformat(),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
        "complete": bar.complete,
        "schema_version": bar.schema_version,
    }


def _bar_sort_key(bar: Bar) -> tuple[object, ...]:
    return (
        bar.symbol,
        bar.market,
        bar.timeframe.value,
        bar.start_ts,
        bar.end_ts,
        str(bar.open),
        str(bar.high),
        str(bar.low),
        str(bar.close),
        str(bar.volume),
        bar.complete,
        bar.schema_version,
    )
