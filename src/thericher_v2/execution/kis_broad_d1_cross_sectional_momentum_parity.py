"""Pure replay-parity attestation for the frozen broad D1 benchmark.

The attestation deliberately has no persistence or external-route surface.  It
only states whether a pair of supplied completed daily bars has the timing
shape that the existing broker-free replay contract can represent.  It cannot
turn a research decision into an executable request.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from thericher_v2.contracts import Bar, Timeframe

ROUND_TRIP_STRESS_BPS = (Decimal("5"), Decimal("10"), Decimal("20"))

BROAD_D1_SOURCE_LIMITATIONS = (
    "current_listing_only_not_point_in_time_universe",
    "non_pit_registry_scope",
    "MODP_0_unadjusted",
    "corporate_action_semantics_not_qualified",
    "session_finality_unattested",
    "alternate_daily_representation_semantics_unproven",
)


@dataclass(frozen=True, slots=True)
class D1CrossSectionalMomentumParityAttestation:
    """Source-safe execution-semantics evidence with no execution authority."""

    input_contract_ref: str | None
    source_limitations: tuple[str, ...]
    timing_rule: Literal["completed_d1_t_to_next_observed_d1_open"]
    next_observed_execution_bar_attested: bool
    semantic_representability: Literal["represented"]
    executable_or_paper_eligibility: Literal["not_evaluated_by_semantic_attestation"]
    round_trip_stress_bps: tuple[Decimal, Decimal, Decimal]
    cost_assumption_status: Literal[
        "research_accounting_assumption_not_verified_fill_cost_or_liquidity_model"
    ]

    def safe_payload(self) -> dict[str, object]:
        """Return an in-memory integration payload without raw bars or side effects."""

        return {
            "input_contract_ref": self.input_contract_ref,
            "source_limitations": list(self.source_limitations),
            "timing": {
                "rule": self.timing_rule,
                "next_observed_execution_bar_attested": self.next_observed_execution_bar_attested,
                "semantic_representability": self.semantic_representability,
                "executable_or_paper_eligibility": self.executable_or_paper_eligibility,
            },
            "round_trip_stress": {
                "bps": [str(value) for value in self.round_trip_stress_bps],
                "status": self.cost_assumption_status,
            },
        }


def attest_broad_d1_cross_sectional_momentum_parity(
    *,
    signal_bar: Bar,
    execution_bar: Bar,
    next_observed_execution_bar: bool,
    source_limitations: tuple[str, ...],
    input_contract_ref: str | None = None,
) -> D1CrossSectionalMomentumParityAttestation:
    """Attest timing compatibility without creating a request or touching a route.

    The supplied boolean is intentionally explicit: two daily bars alone cannot
    prove that no intervening observed session exists.  The Data/Engine contract
    must establish that the execution bar is the next observed daily bar before
    this timing statement can be used.
    """

    _validate_bars(signal_bar=signal_bar, execution_bar=execution_bar)
    if not isinstance(next_observed_execution_bar, bool) or not next_observed_execution_bar:
        raise ValueError("next_observed_execution_bar must be explicitly attested")
    normalized_limitations = _validate_source_limitations(source_limitations)
    normalized_contract_ref = _validate_input_contract_ref(input_contract_ref)
    return D1CrossSectionalMomentumParityAttestation(
        input_contract_ref=normalized_contract_ref,
        source_limitations=normalized_limitations,
        timing_rule="completed_d1_t_to_next_observed_d1_open",
        next_observed_execution_bar_attested=True,
        semantic_representability="represented",
        executable_or_paper_eligibility="not_evaluated_by_semantic_attestation",
        round_trip_stress_bps=ROUND_TRIP_STRESS_BPS,
        cost_assumption_status=(
            "research_accounting_assumption_not_verified_fill_cost_or_liquidity_model"
        ),
    )


def _validate_bars(*, signal_bar: Bar, execution_bar: Bar) -> None:
    if not isinstance(signal_bar, Bar) or not isinstance(execution_bar, Bar):
        raise TypeError("signal_bar and execution_bar must be Bar instances")
    if signal_bar.timeframe is not Timeframe.D1 or execution_bar.timeframe is not Timeframe.D1:
        raise ValueError("parity attestation accepts only completed D1 bars")
    if signal_bar.symbol != execution_bar.symbol or signal_bar.market != execution_bar.market:
        raise ValueError("signal_bar and execution_bar must share market and symbol")
    if not signal_bar.complete or not execution_bar.complete:
        raise ValueError("signal_bar and execution_bar must both be complete")
    if (
        execution_bar.start_ts <= signal_bar.start_ts
        or execution_bar.start_ts.date() <= signal_bar.start_ts.date()
    ):
        raise ValueError("execution_bar must be on a later observed UTC date")


def _validate_source_limitations(source_limitations: tuple[str, ...]) -> tuple[str, ...]:
    if not source_limitations or not isinstance(source_limitations, tuple) or not all(
        isinstance(value, str) and value for value in source_limitations
    ):
        raise TypeError("source_limitations must be a non-empty tuple of non-empty strings")
    if len(set(source_limitations)) != len(source_limitations):
        raise ValueError("source_limitations must not contain duplicates")
    missing = tuple(
        value for value in BROAD_D1_SOURCE_LIMITATIONS if value not in source_limitations
    )
    if missing:
        raise ValueError(f"source_limitations missing required values: {', '.join(missing)}")
    return source_limitations


def _validate_input_contract_ref(input_contract_ref: str | None) -> str | None:
    if input_contract_ref is None:
        return None
    if not isinstance(input_contract_ref, str) or not input_contract_ref.strip():
        raise ValueError("input_contract_ref must be a non-empty string when supplied")
    return input_contract_ref


__all__ = [
    "BROAD_D1_SOURCE_LIMITATIONS",
    "ROUND_TRIP_STRESS_BPS",
    "D1CrossSectionalMomentumParityAttestation",
    "attest_broad_d1_cross_sectional_momentum_parity",
]
