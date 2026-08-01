"""Pure future-consumer outline for a qualified local Norgate daily probe.

It freezes no features, labels, model, score, ranking, allocation, broker
intent, or CUDA work.  Its purpose is to make the remaining timing and leakage
questions explicit before a separate campaign is allowed to consume source rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from thericher_v2.data.norgate_trial_daily_capability_probe import (
    NorgateTrialDailyCapabilityProbeResult,
    require_attested_norgate_trial_daily_capability_probe,
)

NORGATE_TRIAL_DAILY_CONSUMER_OUTLINE_ID = "norgate-trial-daily-consumer-outline-v1"
_OUTLINE_ATTESTATION = object()


@dataclass(frozen=True, slots=True, init=False)
class NorgateTrialDailyConsumerOutline:
    """An attested, non-executable daily-input outline for later research only."""

    outline_id: str
    receipt_hash: str
    source_namespace: str
    completed_bar_rule: str
    causal_decision_timestamp_rule: str
    temporal_split_rule: str
    cost_rule: str
    naive_baseline: str
    strongest_leakage_kill_test: str
    model_eligible: bool
    gpu_eligible: bool
    ranking_eligible: bool
    paper_trading_eligible: bool
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified Norgate trial daily consumer-outline builder")

    def safe_payload(self) -> dict[str, object]:
        require_attested_norgate_trial_daily_consumer_outline(self)
        return {
            "outline_id": self.outline_id,
            "receipt_hash": self.receipt_hash,
            "source_namespace": self.source_namespace,
            "completed_bar_rule": self.completed_bar_rule,
            "causal_decision_timestamp_rule": self.causal_decision_timestamp_rule,
            "temporal_split_rule": self.temporal_split_rule,
            "cost_rule": self.cost_rule,
            "naive_baseline": self.naive_baseline,
            "strongest_leakage_kill_test": self.strongest_leakage_kill_test,
            "model_eligible": self.model_eligible,
            "gpu_eligible": self.gpu_eligible,
            "ranking_eligible": self.ranking_eligible,
            "paper_trading_eligible": self.paper_trading_eligible,
        }


def build_norgate_trial_daily_consumer_outline(
    probe: NorgateTrialDailyCapabilityProbeResult,
    *,
    requested_use: str = "offline_research_outline",
) -> NorgateTrialDailyConsumerOutline:
    """Map only a qualified receipt to a future KIS-shaped D1 consumer boundary."""

    if requested_use != "offline_research_outline":
        raise ValueError("Norgate daily consumer outline is offline research only")
    verified = require_attested_norgate_trial_daily_capability_probe(probe)
    if verified.status != "qualified_for_offline_research":
        raise ValueError("Norgate daily source is not qualified for an offline outline")
    result = object.__new__(NorgateTrialDailyConsumerOutline)
    object.__setattr__(result, "outline_id", NORGATE_TRIAL_DAILY_CONSUMER_OUTLINE_ID)
    object.__setattr__(result, "receipt_hash", verified.receipt_hash)
    object.__setattr__(result, "source_namespace", verified.source_namespace)
    object.__setattr__(result, "completed_bar_rule", "consume completed D1 OHLCV only")
    object.__setattr__(
        result,
        "causal_decision_timestamp_rule",
        "candidate decision is no earlier than the next US regular-session open after a "
        "completed D1 bar; vendor availability time remains unknown",
    )
    object.__setattr__(
        result,
        "temporal_split_rule",
        "chronological source-session split with campaign-frozen lookback-plus-horizon purge",
    )
    object.__setattr__(
        result,
        "cost_rule",
        "use a separately Execution-attested KIS Paper cost, latency, and fill model",
    )
    object.__setattr__(result, "naive_baseline", "always_flat")
    object.__setattr__(
        result,
        "strongest_leakage_kill_test",
        "shift every source availability timestamp one session later; reject any result "
        "whose input, membership, or decision date changes",
    )
    object.__setattr__(result, "model_eligible", False)
    object.__setattr__(result, "gpu_eligible", False)
    object.__setattr__(result, "ranking_eligible", False)
    object.__setattr__(result, "paper_trading_eligible", False)
    object.__setattr__(result, "_attestation", _OUTLINE_ATTESTATION)
    return result


def require_attested_norgate_trial_daily_consumer_outline(
    value: object,
) -> NorgateTrialDailyConsumerOutline:
    """Reject a forged outline or an attempted route widening."""

    if (
        not isinstance(value, NorgateTrialDailyConsumerOutline)
        or getattr(value, "_attestation", None) is not _OUTLINE_ATTESTATION
        or getattr(value, "outline_id", None) != NORGATE_TRIAL_DAILY_CONSUMER_OUTLINE_ID
        or getattr(value, "source_namespace", None) != "norgate_trial_daily_offline_research_only"
        or not getattr(value, "receipt_hash", None)
        or getattr(value, "model_eligible", None) is not False
        or getattr(value, "gpu_eligible", None) is not False
        or getattr(value, "ranking_eligible", None) is not False
        or getattr(value, "paper_trading_eligible", None) is not False
    ):
        raise ValueError("Norgate daily consumer outline requires verified attestation")
    return value
