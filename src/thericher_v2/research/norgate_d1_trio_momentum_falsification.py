"""Pure offline cross-ETF momentum falsification over a fixed D1 panel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, time
from decimal import Decimal, localcontext
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe

NORGATE_D1_TRIO_MOMENTUM_FALSIFICATION_ID = "norgate-d1-trio-momentum-falsification-v1"
NORGATE_D1_TRIO_MOMENTUM_SYMBOLS = ("SPY", "QQQ", "IWM")
NORGATE_D1_TRIO_MOMENTUM_SESSION_COUNT = 511
NORGATE_D1_TRIO_MOMENTUM_DEVELOPMENT_SESSIONS = 350
NORGATE_D1_TRIO_MOMENTUM_PURGE_SESSIONS = 21
NORGATE_D1_TRIO_MOMENTUM_VALIDATION_SESSIONS = 140
NORGATE_D1_TRIO_MOMENTUM_LOOKBACK_SESSIONS = 20
NORGATE_D1_TRIO_MOMENTUM_MIN_VALIDATION_LONG_DECISIONS = 30

_VALIDATION_START = (
    NORGATE_D1_TRIO_MOMENTUM_DEVELOPMENT_SESSIONS
    + NORGATE_D1_TRIO_MOMENTUM_PURGE_SESSIONS
)
_VALIDATION_END = NORGATE_D1_TRIO_MOMENTUM_SESSION_COUNT
_TARGET_EXIT_OFFSET = 2

ResultStatus = Literal["rejected", "inconclusive_non_promoting"]
ResultReason = Literal[
    "insufficient_validation_long_decisions",
    "rule_hit_rate_not_above_always_long",
    "rule_hit_rate_strictly_above_always_long",
]


def frozen_norgate_d1_trio_momentum_contract() -> dict[str, object]:
    """Return the exact source-safe contract used to identify this one diagnostic."""

    return {
        "campaign_id": NORGATE_D1_TRIO_MOMENTUM_FALSIFICATION_ID,
        "symbols": list(NORGATE_D1_TRIO_MOMENTUM_SYMBOLS),
        "session_count": NORGATE_D1_TRIO_MOMENTUM_SESSION_COUNT,
        "split": {
            "development_sessions": NORGATE_D1_TRIO_MOMENTUM_DEVELOPMENT_SESSIONS,
            "purge_sessions": NORGATE_D1_TRIO_MOMENTUM_PURGE_SESSIONS,
            "validation_sessions": NORGATE_D1_TRIO_MOMENTUM_VALIDATION_SESSIONS,
        },
        "feature": "20_completed_d1_close_to_close_return_through_t",
        "rule": "long_spy_only_when_spy_qqq_iwm_returns_are_strictly_positive",
        "target": "spy_open_t_plus_2_over_open_t_plus_1_minus_1_sign",
        "comparator": "always_long_across_every_structurally_eligible_validation_slot",
        "minimum_validation_long_decisions": NORGATE_D1_TRIO_MOMENTUM_MIN_VALIDATION_LONG_DECISIONS,
        "promotion_allowed": False,
        "paper_input_eligible": False,
        "gpu_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class NorgateD1TrioMomentumResult:
    """Aggregate outcome of the one fixed diagnostic; never an execution signal."""

    status: ResultStatus
    reason: ResultReason
    target_evaluation_performed: bool
    validation_long_decision_count: int
    validation_target_evaluable_slot_count: int
    rule_hit_count: int | None
    always_long_hit_count: int | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        expected_slots = NORGATE_D1_TRIO_MOMENTUM_VALIDATION_SESSIONS - _TARGET_EXIT_OFFSET
        if (
            self.schema_version != SCHEMA_VERSION
            or self.validation_target_evaluable_slot_count != expected_slots
            or self.validation_long_decision_count < 0
            or self.validation_long_decision_count > expected_slots
        ):
            raise ValueError("Norgate D1 trio momentum result geometry is invalid")
        if self.reason == "insufficient_validation_long_decisions":
            if (
                self.status != "rejected"
                or self.target_evaluation_performed
                or self.rule_hit_count is not None
                or self.always_long_hit_count is not None
                or self.validation_long_decision_count
                >= NORGATE_D1_TRIO_MOMENTUM_MIN_VALIDATION_LONG_DECISIONS
            ):
                raise ValueError("Norgate D1 trio momentum floor rejection is invalid")
            return
        if (
            not self.target_evaluation_performed
            or self.rule_hit_count is None
            or self.always_long_hit_count is None
            or not 0 <= self.rule_hit_count <= self.validation_long_decision_count
            or not 0 <= self.always_long_hit_count <= expected_slots
        ):
            raise ValueError("Norgate D1 trio momentum evaluated result is invalid")
        rule_rate = _rate(self.rule_hit_count, self.validation_long_decision_count)
        comparator_rate = _rate(self.always_long_hit_count, expected_slots)
        if self.reason == "rule_hit_rate_not_above_always_long":
            if self.status != "rejected" or rule_rate > comparator_rate:
                raise ValueError("Norgate D1 trio momentum comparator rejection is invalid")
        elif self.reason == "rule_hit_rate_strictly_above_always_long":
            if self.status != "inconclusive_non_promoting" or rule_rate <= comparator_rate:
                raise ValueError("Norgate D1 trio momentum inconclusive result is invalid")
        else:  # pragma: no cover - Literal values are exercised by public callers.
            raise ValueError("Norgate D1 trio momentum result reason is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return aggregate evidence without bars, dates, or individual decisions."""

        return {
            "campaign_id": NORGATE_D1_TRIO_MOMENTUM_FALSIFICATION_ID,
            "status": self.status,
            "reason": self.reason,
            "target_free": {
                "development_decision_count": (
                    NORGATE_D1_TRIO_MOMENTUM_DEVELOPMENT_SESSIONS
                    - NORGATE_D1_TRIO_MOMENTUM_LOOKBACK_SESSIONS
                ),
                "validation_decision_count": NORGATE_D1_TRIO_MOMENTUM_VALIDATION_SESSIONS,
                "validation_target_evaluable_slot_count": (
                    self.validation_target_evaluable_slot_count
                ),
                "validation_long_decision_count": self.validation_long_decision_count,
            },
            "target_evaluation_performed": self.target_evaluation_performed,
            "rule_hit_rate": _safe_hit_rate(
                self.rule_hit_count,
                self.validation_long_decision_count,
            ),
            "always_long_hit_rate": _safe_hit_rate(
                self.always_long_hit_count,
                self.validation_target_evaluable_slot_count,
            ),
            "promotion_allowed": False,
            "paper_input_eligible": False,
            "gpu_eligible": False,
        }


def run_norgate_d1_trio_momentum_falsification(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
) -> NorgateD1TrioMomentumResult:
    """Construct target-free decisions, then evaluate the exact frozen rule once."""

    streams = _validated_panel(bars_by_symbol)
    validation_indices, validation_long_indices = _target_free_validation_indices(streams)
    target_evaluable_indices = tuple(
        index for index in validation_indices if index + _TARGET_EXIT_OFFSET < _VALIDATION_END
    )
    target_evaluable_set = set(target_evaluable_indices)
    target_evaluable_longs = tuple(
        index for index in validation_long_indices if index in target_evaluable_set
    )
    if len(target_evaluable_longs) < NORGATE_D1_TRIO_MOMENTUM_MIN_VALIDATION_LONG_DECISIONS:
        return NorgateD1TrioMomentumResult(
            status="rejected",
            reason="insufficient_validation_long_decisions",
            target_evaluation_performed=False,
            validation_long_decision_count=len(target_evaluable_longs),
            validation_target_evaluable_slot_count=len(target_evaluable_indices),
            rule_hit_count=None,
            always_long_hit_count=None,
        )

    spy = streams["SPY"]
    rule_hits = _positive_target_count(spy, target_evaluable_longs)
    always_long_hits = _positive_target_count(spy, target_evaluable_indices)
    if _rate(rule_hits, len(target_evaluable_longs)) <= _rate(
        always_long_hits,
        len(target_evaluable_indices),
    ):
        status: ResultStatus = "rejected"
        reason: ResultReason = "rule_hit_rate_not_above_always_long"
    else:
        status = "inconclusive_non_promoting"
        reason = "rule_hit_rate_strictly_above_always_long"
    return NorgateD1TrioMomentumResult(
        status=status,
        reason=reason,
        target_evaluation_performed=True,
        validation_long_decision_count=len(target_evaluable_longs),
        validation_target_evaluable_slot_count=len(target_evaluable_indices),
        rule_hit_count=rule_hits,
        always_long_hit_count=always_long_hits,
    )


def _target_free_validation_indices(
    streams: Mapping[str, tuple[Bar, ...]],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Use only completed closes through ``t``; never read a target open."""

    development_indices = range(
        NORGATE_D1_TRIO_MOMENTUM_LOOKBACK_SESSIONS,
        NORGATE_D1_TRIO_MOMENTUM_DEVELOPMENT_SESSIONS,
    )
    for index in development_indices:
        _is_long_signal(streams, index)
    validation_indices = tuple(range(_VALIDATION_START, _VALIDATION_END))
    return validation_indices, tuple(
        index for index in validation_indices if _is_long_signal(streams, index)
    )


def _validated_panel(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
) -> dict[str, tuple[Bar, ...]]:
    if not isinstance(bars_by_symbol, Mapping):
        raise TypeError("bars_by_symbol must be a mapping")
    if set(bars_by_symbol) != set(NORGATE_D1_TRIO_MOMENTUM_SYMBOLS):
        raise ValueError("Norgate D1 trio momentum panel symbols are invalid")
    result: dict[str, tuple[Bar, ...]] = {}
    reference_starts: tuple[object, ...] | None = None
    for symbol in NORGATE_D1_TRIO_MOMENTUM_SYMBOLS:
        bars = tuple(bars_by_symbol[symbol])
        if len(bars) != NORGATE_D1_TRIO_MOMENTUM_SESSION_COUNT or any(
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.start_ts.tzinfo is not UTC
            or bar.start_ts.time() != time()
            for bar in bars
        ):
            raise ValueError("Norgate D1 trio momentum panel bars are invalid")
        starts = tuple(bar.start_ts for bar in bars)
        if any(later <= earlier for earlier, later in zip(starts, starts[1:], strict=False)):
            raise ValueError("Norgate D1 trio momentum sessions must be chronological")
        if reference_starts is None:
            reference_starts = starts
        elif starts != reference_starts:
            raise ValueError("Norgate D1 trio momentum panel sessions are misaligned")
        result[symbol] = bars
    return result


def _is_long_signal(streams: Mapping[str, tuple[Bar, ...]], index: int) -> bool:
    return all(
        _completed_close_return(streams[symbol], index) > Decimal("0")
        for symbol in NORGATE_D1_TRIO_MOMENTUM_SYMBOLS
    )


def _completed_close_return(bars: Sequence[Bar], index: int) -> Decimal:
    prior_index = index - NORGATE_D1_TRIO_MOMENTUM_LOOKBACK_SESSIONS
    if prior_index < 0 or index >= len(bars):
        raise ValueError("Norgate D1 trio momentum return index is invalid")
    with localcontext() as context:
        context.prec = 34
        return bars[index].close / bars[prior_index].close - Decimal("1")


def _positive_target_count(spy_bars: Sequence[Bar], indices: Sequence[int]) -> int:
    return sum(_target_is_strictly_positive(spy_bars, index) for index in indices)


def _target_is_strictly_positive(spy_bars: Sequence[Bar], index: int) -> bool:
    entry_index = index + 1
    exit_index = index + _TARGET_EXIT_OFFSET
    if exit_index >= len(spy_bars) or spy_bars[entry_index].open <= 0:
        raise ValueError("Norgate D1 trio momentum target is invalid")
    with localcontext() as context:
        context.prec = 34
        return spy_bars[exit_index].open / spy_bars[entry_index].open - Decimal("1") > 0


def _rate(hit_count: int, decision_count: int) -> Decimal:
    if decision_count <= 0 or not 0 <= hit_count <= decision_count:
        raise ValueError("Norgate D1 trio momentum hit rate is invalid")
    with localcontext() as context:
        context.prec = 34
        return Decimal(hit_count) / Decimal(decision_count)


def _safe_hit_rate(hit_count: int | None, decision_count: int) -> dict[str, int | str] | None:
    if hit_count is None:
        return None
    return {
        "hit_count": hit_count,
        "decision_count": decision_count,
        "hit_rate": str(_rate(hit_count, decision_count)),
    }
