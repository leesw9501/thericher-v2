"""Frozen, source-separated historical KIS daily CPU baseline campaign."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data import CatalogedBars
from thericher_v2.data.kis_paper_daily import KIS_PAPER_PRIVATE_DAILY_CATALOG_ID

from .campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
    NaiveBaselineId,
)
from .validation import NaiveBaselineRun, run_naive_cpu_baseline

HISTORICAL_KIS_DAILY_CAMPAIGN_ID = "historical-kis-daily-naive-v1"
HISTORICAL_KIS_DAILY_FOLD_ID = "chronological-holdout"
HISTORICAL_KIS_DAILY_MIN_SESSIONS = 60
HISTORICAL_KIS_DAILY_MIN_DEVELOPMENT_SESSIONS = 40
HISTORICAL_KIS_DAILY_MIN_HOLDOUT_SESSIONS = 12
HISTORICAL_KIS_DAILY_HOLDOUT_DIVISOR = 5
HISTORICAL_KIS_DAILY_PURGE_SESSIONS = 1
HISTORICAL_KIS_DAILY_SIGNAL_STRIDE_BARS = 2
HISTORICAL_KIS_DAILY_NAIVE_BASELINES: tuple[NaiveBaselineId, ...] = (
    "always_long",
    "previous_bar_direction",
)
HISTORICAL_KIS_DAILY_TARGET_KEYS = (
    "QQQ/NAS/MODP=0",
    "SPY/AMS/MODP=0",
)
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SUMMARY_FORBIDDEN_KEYS = frozenset(
    {
        "artifact_path",
        "dataset_source_path",
        "emergency_path",
        "event_jsonl_path",
        "source_path",
        "state_sqlite_path",
        "work_dir",
    }
)

HistoricalKisCpuPhase = Literal["development", "chronological_holdout"]


@dataclass(frozen=True)
class HistoricalKisFeatureAvailability:
    """Point-in-time feature rule for the fixed daily naive comparison."""

    feature_names: tuple[str, ...] = ("completed_daily_bar_direction",)
    available_at: Literal["completed_bar_end"] = "completed_bar_end"
    decision_rule: str = "decision_at_completed_bar_end"
    execution_rule: str = "next_daily_bar_open_then_following_daily_bar_open"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_names", tuple(self.feature_names))
        if not self.feature_names or any(not name.strip() for name in self.feature_names):
            raise ValueError("historical KIS feature names must be non-empty")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "feature_names": list(self.feature_names),
            "available_at": self.available_at,
            "decision_rule": self.decision_rule,
            "execution_rule": self.execution_rule,
        }


@dataclass(frozen=True)
class HistoricalKisDailySplit:
    """Chronological development, purge, and descriptive holdout boundaries."""

    development: CampaignWindow
    purge: CampaignWindow
    holdout: CampaignWindow
    development_session_count: int
    purge_session_count: int
    holdout_session_count: int
    holdout_status: str = "chronological_unsealed_descriptive_only"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        counts = (
            self.development_session_count,
            self.purge_session_count,
            self.holdout_session_count,
        )
        if any(count <= 0 for count in counts):
            raise ValueError("historical KIS split session counts must be positive")
        if self.development.end_utc > self.purge.start_utc:
            raise ValueError("historical KIS development and purge windows overlap")
        if self.purge.end_utc > self.holdout.start_utc:
            raise ValueError("historical KIS purge and holdout windows overlap")
        if self.holdout_status != "chronological_unsealed_descriptive_only":
            raise ValueError("historical KIS holdout status is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "development": _window_payload(self.development),
            "purge": _window_payload(self.purge),
            "holdout": _window_payload(self.holdout),
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "holdout_session_count": self.holdout_session_count,
            "holdout_status": self.holdout_status,
        }


@dataclass(frozen=True)
class HistoricalKisStopRules:
    """Bounded stop conditions for this research-only CPU campaign."""

    conditions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "conditions", tuple(self.conditions))
        if not self.conditions or any(not condition.strip() for condition in self.conditions):
            raise ValueError("historical KIS stop rules must be non-empty")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "conditions": list(self.conditions),
        }


@dataclass(frozen=True)
class HistoricalKisDecisionSchedule:
    """Fixed non-overlapping decision cadence for the next-open target."""

    signal_stride_bars: int = HISTORICAL_KIS_DAILY_SIGNAL_STRIDE_BARS
    first_signal_offset: int = 0
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.signal_stride_bars < 1 or self.first_signal_offset < 0:
            raise ValueError("historical KIS decision schedule is invalid")

    def eligible_signal_starts(
        self,
        bars: Sequence[Bar],
        *,
        target: ExecutableTarget,
    ) -> frozenset[datetime]:
        if self.signal_stride_bars < target.exit_bar_offset:
            raise ValueError("historical KIS decision schedule can overlap target exits")
        final_signal_index = len(bars) - target.exit_bar_offset
        return frozenset(
            bars[index].start_ts
            for index in range(
                self.first_signal_offset,
                final_signal_index,
                self.signal_stride_bars,
            )
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "signal_stride_bars": self.signal_stride_bars,
            "first_signal_offset": self.first_signal_offset,
            "rule": "next_signal_after_prior_target_exit_bar_opens",
        }


@dataclass(frozen=True)
class HistoricalKisDailyCampaign:
    """Immutable daily KIS contract plus its eligible Data-owned stream."""

    campaign: CampaignContract
    cataloged_bars: CatalogedBars
    split: HistoricalKisDailySplit
    feature_availability: HistoricalKisFeatureAvailability
    decision_schedule: HistoricalKisDecisionSchedule
    stop_rules: HistoricalKisStopRules
    artifact_root: Path
    limitations: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_root", Path(self.artifact_root).resolve())
        object.__setattr__(self, "limitations", tuple(self.limitations))
        if not isinstance(self.cataloged_bars, CatalogedBars):
            raise TypeError("historical KIS campaign requires Data-owned CatalogedBars")
        _validate_historical_kis_daily_source(self.cataloged_bars)
        self.campaign.verify_cataloged_dataset(
            dataset_id=self.cataloged_bars.dataset_id,
            dataset_hash=self.cataloged_bars.dataset_hash,
        )
        if self.campaign.timeframe != Timeframe.D1:
            raise ValueError("historical KIS campaign requires daily bars")
        self.decision_schedule.eligible_signal_starts(
            self.cataloged_bars.bars,
            target=self.campaign.target,
        )
        if (
            self.split.development_session_count
            + self.split.purge_session_count
            + self.split.holdout_session_count
            != len(self.cataloged_bars.bars)
        ):
            raise ValueError("historical KIS split does not cover the frozen daily source")
        if self.campaign.naive_baselines != HISTORICAL_KIS_DAILY_NAIVE_BASELINES:
            raise ValueError("historical KIS campaign naive baselines are invalid")
        if self.campaign.evidence_use != "development" or self.campaign.sealed_holdout is not None:
            raise ValueError("historical KIS campaign must remain descriptive and unsealed")
        development_fold, development = self.campaign.resolve_window(
            "development",
            fold_id=HISTORICAL_KIS_DAILY_FOLD_ID,
        )
        holdout_fold, holdout = self.campaign.resolve_window(
            "validation",
            fold_id=HISTORICAL_KIS_DAILY_FOLD_ID,
        )
        if (
            development_fold != HISTORICAL_KIS_DAILY_FOLD_ID
            or holdout_fold != HISTORICAL_KIS_DAILY_FOLD_ID
            or development != self.split.development
            or holdout != self.split.holdout
        ):
            raise ValueError("historical KIS split does not match the campaign contract")
        if not self.limitations or any(not limitation.strip() for limitation in self.limitations):
            raise ValueError("historical KIS limitations must be non-empty")

    @property
    def contract_hash(self) -> str:
        encoded = json.dumps(
            self._payload_without_hash(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def to_payload(self) -> dict[str, object]:
        return {
            **self._payload_without_hash(),
            "frozen_contract_hash": self.contract_hash,
        }

    def _payload_without_hash(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "historical_kis_daily_campaign",
            "campaign": self.campaign.to_payload(),
            "campaign_contract_hash": self.campaign.contract_hash,
            "input": {
                "dataset_id": self.cataloged_bars.dataset_id,
                "dataset_hash": self.cataloged_bars.dataset_hash,
                "loader": "load_kis_paper_private_daily_catalog",
                "source_separation": "KIS private daily source only; no source mixing",
            },
            "feature_availability": self.feature_availability.to_payload(),
            "decision_schedule": self.decision_schedule.to_payload(),
            "chronological_split": self.split.to_payload(),
            "artifact_root": str(self.artifact_root),
            "stop_rules": self.stop_rules.to_payload(),
            "candidate_scope": {
                "baseline_id": "always_long",
                "comparison_id": "previous_bar_direction",
                "prior_sequence_screens": "descriptive_only_not_selected",
                "model_promotion": "not_permitted_by_this_campaign",
            },
            "limitations": list(self.limitations),
        }

    def eligible_signal_starts(self, phase: HistoricalKisCpuPhase) -> frozenset[datetime]:
        campaign_phase = "development" if phase == "development" else "validation"
        _, window = self.campaign.resolve_window(
            campaign_phase,
            fold_id=HISTORICAL_KIS_DAILY_FOLD_ID,
        )
        phase_bars = tuple(
            bar
            for bar in self.cataloged_bars.bars
            if bar.start_ts >= window.start_utc and bar.end_ts <= window.end_utc
        )
        return self.decision_schedule.eligible_signal_starts(
            phase_bars,
            target=self.campaign.target,
        )


@dataclass(frozen=True)
class HistoricalKisCpuBaselineRun:
    phase: HistoricalKisCpuPhase
    baseline: NaiveBaselineRun
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class HistoricalKisCpuBaselineResult:
    """Bounded replay evidence; it makes no selected-model or PnL claim."""

    campaign: HistoricalKisDailyCampaign
    contract_path: Path
    baseline_runs: tuple[HistoricalKisCpuBaselineRun, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_path", Path(self.contract_path).resolve())
        expected_count = len(HISTORICAL_KIS_DAILY_NAIVE_BASELINES) * 2
        if len(self.baseline_runs) != expected_count:
            raise ValueError("historical KIS CPU campaign did not produce every fixed baseline")


def build_historical_kis_daily_campaign(
    cataloged_bars: CatalogedBars,
    *,
    artifact_root: Path,
    repo_root: Path,
    campaign_id: str = HISTORICAL_KIS_DAILY_CAMPAIGN_ID,
) -> HistoricalKisDailyCampaign:
    """Freeze a daily KIS-only 80/20 chronological development/holdout contract."""

    _validate_historical_kis_daily_source(cataloged_bars)
    resolved_artifact_root = _external_artifact_root(artifact_root, repo_root=repo_root)
    bars = tuple(cataloged_bars.bars)
    holdout_count = max(
        HISTORICAL_KIS_DAILY_MIN_HOLDOUT_SESSIONS,
        len(bars) // HISTORICAL_KIS_DAILY_HOLDOUT_DIVISOR,
    )
    development_count = len(bars) - HISTORICAL_KIS_DAILY_PURGE_SESSIONS - holdout_count
    if development_count < HISTORICAL_KIS_DAILY_MIN_DEVELOPMENT_SESSIONS:
        raise ValueError("historical KIS daily source leaves too little development history")

    development = CampaignWindow(bars[0].start_ts, bars[development_count - 1].end_ts)
    purge = CampaignWindow(
        bars[development_count].start_ts,
        bars[development_count].end_ts,
    )
    holdout_start_index = development_count + HISTORICAL_KIS_DAILY_PURGE_SESSIONS
    holdout = CampaignWindow(bars[holdout_start_index].start_ts, bars[-1].end_ts)
    split = HistoricalKisDailySplit(
        development=development,
        purge=purge,
        holdout=holdout,
        development_session_count=development_count,
        purge_session_count=HISTORICAL_KIS_DAILY_PURGE_SESSIONS,
        holdout_session_count=holdout_count,
    )
    campaign = CampaignContract(
        campaign_id=campaign_id,
        catalog=CatalogDatasetRef(
            catalog_id=f"{cataloged_bars.dataset_id}:historical-kis-daily-v1",
            dataset_id=cataloged_bars.dataset_id,
            dataset_hash=cataloged_bars.dataset_hash,
            constructed_as_of_utc=bars[-1].end_ts,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.D1,
        folds=(CampaignFold(HISTORICAL_KIS_DAILY_FOLD_ID, development, holdout),),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=Decimal("1"),
            slippage_bps=Decimal("2"),
            slippage_source_id="historical-kis-daily-fixed-cost-assumption-v1",
        ),
        purge=timedelta(days=1),
        embargo=timedelta(days=1),
        evidence_use="development",
        sealed_holdout=None,
        naive_baselines=HISTORICAL_KIS_DAILY_NAIVE_BASELINES,
        metrics=(
            "after_cost_pnl",
            "gross_pnl",
            "fee_cost",
            "slippage_cost",
            "trade_count",
            "decision_count",
        ),
        deterministic_seed=83,
    )
    return HistoricalKisDailyCampaign(
        campaign=campaign,
        cataloged_bars=cataloged_bars,
        split=split,
        feature_availability=HistoricalKisFeatureAvailability(),
        decision_schedule=HistoricalKisDecisionSchedule(),
        stop_rules=HistoricalKisStopRules(
            conditions=(
                "stop_when_the_hash_attested_KIS_daily_input_is_not_complete_and_chronological",
                "stop_when_the_source_is_not_the_KIS_private_daily_loader",
                "stop_when_the_external_attempt_or_artifact_name_already_exists",
                "stop_when_a_replay_breaks_the_local_paper_invariant",
                "stop_before_model_selection_promotion_or_sealed_holdout_use",
            )
        ),
        artifact_root=resolved_artifact_root,
        limitations=(
            "MODP=0 unadjusted daily prices; corporate-action semantics are not qualified",
            "chronological holdout is descriptive and unsealed because this is a historical cache",
            "results are CPU naive-baseline replay evidence only",
        ),
    )


def write_frozen_historical_kis_campaign_contract(
    campaign: HistoricalKisDailyCampaign,
    *,
    path: Path,
    repo_root: Path,
) -> Path:
    """Persist the contract before replay, preserving an immutable recovery point."""

    if not isinstance(campaign, HistoricalKisDailyCampaign):
        raise TypeError("historical KIS contract writer requires HistoricalKisDailyCampaign")
    resolved_path = _external_artifact_path(
        path,
        artifact_root=campaign.artifact_root,
        repo_root=repo_root,
    )
    _write_json_new(resolved_path, campaign.to_payload())
    return resolved_path


def run_historical_kis_daily_cpu_baselines(
    campaign: HistoricalKisDailyCampaign,
    *,
    contract_path: Path,
    work_root: Path,
    repo_root: Path,
    run_label: str,
    starting_cash: Decimal = Decimal("10000"),
    quantity: Decimal = Decimal("1"),
) -> HistoricalKisCpuBaselineResult:
    """Run exactly one naive baseline and one comparison for each fixed phase."""

    validate_historical_kis_run_label(run_label)
    resolved_contract_path = _external_artifact_path(
        contract_path,
        artifact_root=campaign.artifact_root,
        repo_root=repo_root,
    )
    _verify_frozen_contract(campaign, resolved_contract_path)
    resolved_work_root = _external_artifact_path(
        work_root,
        artifact_root=campaign.artifact_root,
        repo_root=repo_root,
    )

    runs: list[HistoricalKisCpuBaselineRun] = []
    for phase, campaign_phase in (
        ("development", "development"),
        ("chronological_holdout", "validation"),
    ):
        eligible_signal_starts = campaign.eligible_signal_starts(phase)
        for baseline_id in HISTORICAL_KIS_DAILY_NAIVE_BASELINES:
            baseline = run_naive_cpu_baseline(
                campaign.cataloged_bars,
                campaign=campaign.campaign,
                artifact_root=campaign.artifact_root,
                work_dir=resolved_work_root / phase / baseline_id,
                phase=campaign_phase,
                fold_id=HISTORICAL_KIS_DAILY_FOLD_ID,
                baseline_id=baseline_id,
                repo_root=repo_root,
                starting_cash=starting_cash,
                quantity=quantity,
                run_label=run_label,
                eligible_signal_starts=eligible_signal_starts,
            )
            if (
                baseline.fill_source != "local_paper"
                or baseline.replay_evidence.fill_source != "local_paper"
            ):
                raise RuntimeError("historical KIS CPU campaign requires local-paper replay")
            runs.append(HistoricalKisCpuBaselineRun(phase=phase, baseline=baseline))

    return HistoricalKisCpuBaselineResult(
        campaign=campaign,
        contract_path=resolved_contract_path,
        baseline_runs=tuple(runs),
    )


def build_sanitized_historical_kis_summary(
    result: HistoricalKisCpuBaselineResult,
    *,
    run_label: str,
) -> dict[str, object]:
    """Project aggregate replay evidence without paths, bar values, or credentials."""

    validate_historical_kis_run_label(run_label)
    campaign = result.campaign
    runs: list[dict[str, object]] = []
    for item in result.baseline_runs:
        baseline = item.baseline
        validation = baseline.result
        all_fills_local_paper = (
            baseline.fill_source == "local_paper"
            and baseline.replay_evidence.fill_source == "local_paper"
        )
        runs.append(
            {
                "phase": item.phase,
                "baseline_id": baseline.baseline_id,
                "bars_seen": validation.bars_seen,
                "decisions_seen": validation.decisions_seen,
                "trade_count": len(validation.trades),
                "event_count": validation.event_count,
                "fill_source": baseline.fill_source,
                "all_fills_local_paper": all_fills_local_paper,
                "gross_pnl": str(validation.gross_pnl),
                "after_cost_pnl": str(validation.after_cost_pnl),
                "total_fees": str(validation.total_fees),
                "total_slippage": str(validation.total_slippage),
                "event_jsonl_sha256": baseline.replay_evidence.event_jsonl_sha256,
                "state_sqlite_sha256": baseline.replay_evidence.state_sqlite_sha256,
            }
        )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_local_paper",
        "run_label": run_label,
        "contract": {
            "campaign_id": campaign.campaign.campaign_id,
            "campaign_contract_hash": campaign.campaign.contract_hash,
            "frozen_contract_hash": campaign.contract_hash,
            "artifact_name": result.contract_path.name,
        },
        "input": {
            "dataset_id": campaign.cataloged_bars.dataset_id,
            "dataset_hash": campaign.cataloged_bars.dataset_hash,
            "source_separation": "KIS private daily source only",
        },
        "feature_availability": campaign.feature_availability.to_payload(),
        "chronological_split": campaign.split.to_payload(),
        "cost_model": campaign.campaign.to_payload()["costs"],
        "metrics": list(campaign.campaign.metrics),
        "baseline_runs": runs,
        "all_fills_local_paper": all(item["all_fills_local_paper"] for item in runs),
        "claim": (
            "descriptive CPU baseline and fixed naive comparison only; not a model selection, "
            "profitability claim, Paper order, or sealed-holdout result"
        ),
    }
    _assert_sanitized_summary(summary)
    return summary


def write_sanitized_historical_kis_summary(
    summary: Mapping[str, object],
    *,
    path: Path,
    artifact_root: Path,
    repo_root: Path,
) -> Path:
    """Write a new sanitized summary under the external model-artifact root."""

    _assert_sanitized_summary(summary)
    resolved_path = _external_artifact_path(
        path,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    _write_json_new(resolved_path, summary)
    return resolved_path


def validate_historical_kis_run_label(value: str) -> None:
    if not isinstance(value, str) or _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("historical KIS run label must use 1-80 safe ASCII characters")


def validate_historical_kis_artifact_root(artifact_root: Path, *, repo_root: Path) -> Path:
    """Validate the external artifact root before the runner opens a data cache."""

    return _external_artifact_root(artifact_root, repo_root=repo_root)


def _validate_historical_kis_daily_source(cataloged_bars: CatalogedBars) -> None:
    if not isinstance(cataloged_bars, CatalogedBars):
        raise TypeError("historical KIS campaign requires Data-owned CatalogedBars")
    if cataloged_bars.dataset_id != KIS_PAPER_PRIVATE_DAILY_CATALOG_ID:
        raise ValueError("historical KIS campaign requires the verified KIS private daily loader")
    bars = tuple(cataloged_bars.bars)
    if len(bars) < HISTORICAL_KIS_DAILY_MIN_SESSIONS:
        raise ValueError("historical KIS daily source has too few completed sessions")
    first = bars[0]
    if (
        first.timeframe != Timeframe.D1
        or not first.complete
        or any(
            bar.timeframe != Timeframe.D1
            or not bar.complete
            or bar.symbol != first.symbol
            or bar.market != first.market
            for bar in bars
        )
    ):
        raise ValueError("historical KIS daily source must be complete and homogeneous")
    if any(
        current.start_ts <= prior.start_ts for prior, current in zip(bars, bars[1:], strict=False)
    ):
        raise ValueError("historical KIS daily source must be strictly chronological")


def _verify_frozen_contract(campaign: HistoricalKisDailyCampaign, path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("historical KIS campaign contract is unreadable") from error
    if (
        not isinstance(payload, dict)
        or payload.get("frozen_contract_hash") != campaign.contract_hash
    ):
        raise ValueError("historical KIS campaign contract does not match the frozen input")


def _assert_sanitized_summary(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in _SUMMARY_FORBIDDEN_KEYS:
                raise ValueError(f"historical KIS summary may not contain {key}")
            _assert_sanitized_summary(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_sanitized_summary(nested)


def _external_artifact_root(artifact_root: Path, *, repo_root: Path) -> Path:
    resolved_root = Path(artifact_root).resolve()
    resolved_repo = Path(repo_root).resolve()
    if resolved_root == resolved_repo or resolved_repo in resolved_root.parents:
        raise ValueError("historical KIS artifact root must stay outside the Git workspace")
    return resolved_root


def _external_artifact_path(path: Path, *, artifact_root: Path, repo_root: Path) -> Path:
    resolved_root = _external_artifact_root(artifact_root, repo_root=repo_root)
    resolved_path = Path(path).resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("historical KIS artifact path must stay under the artifact root")
    return resolved_path


def _window_payload(window: CampaignWindow) -> dict[str, str]:
    return {
        "start_utc": window.start_utc.isoformat(),
        "end_utc": window.end_utc.isoformat(),
    }


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
        handle.write("\n")
