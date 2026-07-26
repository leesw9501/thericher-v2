"""Frozen six-symbol D1 CPU local-paper control for the KIS current basket.

The module consumes only the attested daily-universe panel.  It is a bounded
per-symbol replay contract, not a stock selector, training job, ensemble, or
broker route.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType

from thericher_v2.contracts import SCHEMA_VERSION, Bar, ModelPrediction, Signal, Timeframe
from thericher_v2.data.kis_paper_daily_universe_panel import (
    KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_UNIVERSE_PANEL_ID,
    KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS,
    KisPaperDailyUniverseCompletedBarInput,
    KisPaperDailyUniversePanel,
    load_frozen_kis_paper_daily_universe_panel,
    prepare_kis_paper_daily_universe_completed_bar_input,
)
from thericher_v2.data.official_symbol_directory_nas_probe import (
    NAS_COMMON_STOCK_PROBE_SYMBOLS,
)
from thericher_v2.execution import (
    LOCAL_PAPER_SOURCE,
    EmergencyStore,
    FillEventArtifact,
    collect_fill_source_evidence,
    replay_local_paper_account,
)
from thericher_v2.execution.emergency import EmergencyState
from thericher_v2.models import MomentumModel
from thericher_v2.state import EventStore

from .campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from .validation import ValidationConfig, ValidationResult, run_local_paper_validation

KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID = "kis-paper-daily-universe-cpu-baseline-v1"
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_FOLD_ID = "chronological-validation"
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SESSION_COUNT = 199
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DEVELOPMENT_SESSIONS = 159
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_PURGE_SESSIONS = 1
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_VALIDATION_SESSIONS = 39
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DETERMINISTIC_SEED = 271
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_LOOKBACK = 3
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_BUY_THRESHOLD_BPS = Decimal("5")
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SELL_THRESHOLD_BPS = Decimal("-5")
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_FEE_BPS = Decimal("1")
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SLIPPAGE_BPS = Decimal("2")
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_STARTING_CASH = Decimal("10000")
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_QUANTITY = Decimal("1")
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DECISION_STRIDE_SESSIONS = 2
KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR = "always_long"
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_TRANSIENT_REPLAY_ROOT_NAME = "_transient"
_TRANSIENT_REPLAY_OWNER_FILE = "owner.json"
_TRANSIENT_REPLAY_PREFIX = f".{KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID}-"


@dataclass(frozen=True)
class KisPaperDailyUniverseCpuBaselineSplit:
    """Fixed chronological split shared by all six independent streams."""

    development: CampaignWindow
    purge: CampaignWindow
    validation: CampaignWindow
    development_session_count: int
    purge_session_count: int
    validation_session_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_session_count
            != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DEVELOPMENT_SESSIONS
            or self.purge_session_count != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_PURGE_SESSIONS
            or self.validation_session_count
            != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_VALIDATION_SESSIONS
            or self.development.end_utc > self.purge.start_utc
            or self.purge.end_utc > self.validation.start_utc
        ):
            raise ValueError("KIS daily universe CPU baseline split is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "development": _window_payload(self.development),
            "purge": _window_payload(self.purge),
            "validation": _window_payload(self.validation),
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
            "validation_feature_window_rule": "entire_momentum_window_inside_validation",
        }


@dataclass(frozen=True)
class KisPaperDailyUniverseCpuBaselineSpec:
    """The fixed non-learning model, comparator, economics, and sizing."""

    momentum_lookback: int = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_LOOKBACK
    momentum_buy_threshold_bps: Decimal = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_BUY_THRESHOLD_BPS
    momentum_sell_threshold_bps: Decimal = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SELL_THRESHOLD_BPS
    decision_stride_sessions: int = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DECISION_STRIDE_SESSIONS
    naive_comparator: str = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR
    fee_bps: Decimal = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_FEE_BPS
    slippage_bps: Decimal = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SLIPPAGE_BPS
    starting_cash: Decimal = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_STARTING_CASH
    quantity: Decimal = KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_QUANTITY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.momentum_lookback != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_LOOKBACK
            or self.momentum_buy_threshold_bps
            != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_BUY_THRESHOLD_BPS
            or self.momentum_sell_threshold_bps
            != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SELL_THRESHOLD_BPS
            or self.decision_stride_sessions
            != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DECISION_STRIDE_SESSIONS
            or self.naive_comparator != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR
            or self.fee_bps != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_FEE_BPS
            or self.slippage_bps != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SLIPPAGE_BPS
            or self.starting_cash != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_STARTING_CASH
            or self.quantity != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_QUANTITY
        ):
            raise ValueError("KIS daily universe CPU baseline spec is frozen")

    def momentum_model(self) -> MomentumModel:
        return MomentumModel(
            lookback=self.momentum_lookback,
            buy_threshold_bps=self.momentum_buy_threshold_bps,
            sell_threshold_bps=self.momentum_sell_threshold_bps,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": "momentum_close_v1",
            "candidate_version": "0.1.0",
            "family": "fixed_completed_bar_momentum",
            "lookback": self.momentum_lookback,
            "buy_threshold_bps": str(self.momentum_buy_threshold_bps),
            "sell_threshold_bps": str(self.momentum_sell_threshold_bps),
            "decision_stride_sessions": self.decision_stride_sessions,
            "naive_comparator": self.naive_comparator,
            "fee_bps": str(self.fee_bps),
            "slippage_bps": str(self.slippage_bps),
            "starting_cash": str(self.starting_cash),
            "quantity": str(self.quantity),
            "gpu_used": False,
            "training_used": False,
        }


@dataclass(frozen=True)
class KisPaperDailyUniverseCpuBaselineInput:
    """Attested panel and frozen contract consumed by the replay runner."""

    panel: KisPaperDailyUniversePanel
    inputs_by_symbol: Mapping[str, KisPaperDailyUniverseCompletedBarInput]
    split: KisPaperDailyUniverseCpuBaselineSplit
    campaign: CampaignContract
    spec: KisPaperDailyUniverseCpuBaselineSpec
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        normalized = dict(self.inputs_by_symbol)
        object.__setattr__(self, "inputs_by_symbol", MappingProxyType(normalized))
        if (
            self.panel.dataset_id != KIS_PAPER_DAILY_UNIVERSE_PANEL_ID
            or self.panel.adjustment_mode != KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE
            or tuple(normalized) != NAS_COMMON_STOCK_PROBE_SYMBOLS
            or len(self.panel.common_sessions)
            != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SESSION_COUNT
            or self.panel.source_limitations != KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS
            or self.campaign.catalog.dataset_id != self.panel.dataset_id
            or self.campaign.catalog.dataset_hash != self.panel.dataset_hash
            or self.campaign.timeframe != Timeframe.D1
            or self.campaign.evidence_use != "development"
            or self.campaign.sealed_holdout is not None
            or self.campaign.naive_baselines
            != (KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR,)
            or self.campaign.costs.fee_bps != self.spec.fee_bps
            or self.campaign.costs.slippage_bps != self.spec.slippage_bps
        ):
            raise ValueError("KIS daily universe CPU baseline input is invalid")
        for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS:
            completed = normalized[symbol]
            attested = prepare_kis_paper_daily_universe_completed_bar_input(
                self.panel,
                symbol=symbol,
            )
            payload = completed.safe_payload()
            if (
                completed.cataloged_bars is not attested.cataloged_bars
                or completed.last_completed_session != attested.last_completed_session
                or completed.symbol != symbol
                or completed.panel_dataset_id != self.panel.dataset_id
                or completed.panel_dataset_hash != self.panel.dataset_hash
                or not completed.local_paper_only
                or completed.paper_trading_eligible
                or payload["timeframe"] != Timeframe.D1.value
                or payload["source_limitations"] != list(KIS_PAPER_DAILY_UNIVERSE_PANEL_LIMITATIONS)
                or len(completed.cataloged_bars.bars)
                != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SESSION_COUNT
            ):
                raise ValueError("KIS daily universe completed-bar input is invalid")
            self.campaign.verify_cataloged_dataset(
                dataset_id=completed.cataloged_bars.dataset_id,
                dataset_hash=completed.cataloged_bars.dataset_hash,
            )


@dataclass(frozen=True)
class KisPaperDailyUniverseCpuBaselineReplayVerification:
    """Replayability facts retained without raw price or broker payload fields."""

    fill_source: str
    local_paper_fill_count: int
    expected_fill_count: int
    all_fills_local_paper: bool
    local_paper_replay_invariant_passed: bool
    event_jsonl_sha256: str
    emergency_sha256: str
    replayed_ending_cash: Decimal
    replayed_final_position: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.fill_source != LOCAL_PAPER_SOURCE
            or self.local_paper_fill_count < 0
            or self.expected_fill_count < 0
            or not self.all_fills_local_paper
            or not self.local_paper_replay_invariant_passed
            or self.local_paper_fill_count != self.expected_fill_count
            or self.replayed_final_position != 0
            or any(
                not _is_sha256(value)
                for value in (
                    self.event_jsonl_sha256,
                    self.emergency_sha256,
                )
            )
        ):
            raise ValueError("KIS daily universe local-paper replay is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "fill_source": self.fill_source,
            "local_paper_fill_count": self.local_paper_fill_count,
            "expected_fill_count": self.expected_fill_count,
            "all_fills_local_paper": self.all_fills_local_paper,
            "local_paper_replay_invariant_passed": self.local_paper_replay_invariant_passed,
            "event_jsonl_sha256": self.event_jsonl_sha256,
            "emergency_sha256": self.emergency_sha256,
            "replayed_ending_cash": str(self.replayed_ending_cash),
            "replayed_final_position": str(self.replayed_final_position),
        }


@dataclass(frozen=True)
class KisPaperDailyUniverseCpuBaselineCell:
    """One independent fixed-symbol local-paper replay cell."""

    symbol: str
    strategy_id: str
    result: ValidationResult
    verification: KisPaperDailyUniverseCpuBaselineReplayVerification
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        result = self.result
        if (
            self.symbol not in NAS_COMMON_STOCK_PROBE_SYMBOLS
            or self.strategy_id
            not in {"momentum_close_v1", KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR}
            or result.symbol != self.symbol
            or result.market != "US"
            or result.timeframe != Timeframe.D1
            or result.campaign_id != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID
            or result.campaign_phase != "validation"
            or result.campaign_fold_id != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_FOLD_ID
            or result.final_position != 0
            or (self.strategy_id == "momentum_close_v1" and result.baseline_id is not None)
            or (
                self.strategy_id == KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR
                and result.baseline_id != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR
            )
        ):
            raise ValueError("KIS daily universe CPU baseline cell is invalid")


@dataclass(frozen=True)
class KisPaperDailyUniverseCpuBaselineRun:
    """Complete descriptive six-symbol CPU baseline run."""

    baseline_input: KisPaperDailyUniverseCpuBaselineInput
    precommit_path: Path
    precommit_hash: str
    momentum_cells: tuple[KisPaperDailyUniverseCpuBaselineCell, ...]
    naive_cells: tuple[KisPaperDailyUniverseCpuBaselineCell, ...]
    summary_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "momentum_cells", tuple(self.momentum_cells))
        object.__setattr__(self, "naive_cells", tuple(self.naive_cells))
        if (
            tuple(cell.symbol for cell in self.momentum_cells) != NAS_COMMON_STOCK_PROBE_SYMBOLS
            or tuple(cell.strategy_id for cell in self.momentum_cells)
            != ("momentum_close_v1",) * len(NAS_COMMON_STOCK_PROBE_SYMBOLS)
            or tuple(cell.symbol for cell in self.naive_cells) != NAS_COMMON_STOCK_PROBE_SYMBOLS
            or tuple(cell.strategy_id for cell in self.naive_cells)
            != (KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR,)
            * len(NAS_COMMON_STOCK_PROBE_SYMBOLS)
            or not _is_sha256(self.precommit_hash)
            or not self.precommit_path.is_file()
            or not self.summary_path.is_file()
        ):
            raise ValueError("KIS daily universe CPU baseline did not complete the frozen plan")


def build_kis_paper_daily_universe_cpu_baseline_input() -> KisPaperDailyUniverseCpuBaselineInput:
    """Load the one exact panel and freeze its shared D1 replay contract."""

    resolved_panel = load_frozen_kis_paper_daily_universe_panel()
    inputs = {
        symbol: prepare_kis_paper_daily_universe_completed_bar_input(
            resolved_panel,
            symbol=symbol,
        )
        for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS
    }
    split = _build_split(inputs[NAS_COMMON_STOCK_PROBE_SYMBOLS[0]])
    spec = KisPaperDailyUniverseCpuBaselineSpec()
    campaign = _build_campaign(resolved_panel, split=split, spec=spec)
    return KisPaperDailyUniverseCpuBaselineInput(
        panel=resolved_panel,
        inputs_by_symbol=inputs,
        split=split,
        campaign=campaign,
        spec=spec,
    )


def run_kis_paper_daily_universe_cpu_baseline(
    *,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
) -> KisPaperDailyUniverseCpuBaselineRun:
    """Run the precommitted six-symbol local-paper control without external access."""

    _validate_run_label(run_label)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    _reject_repo_path(resolved_artifact_root, repo_root=resolved_repo_root)
    _reject_repo_path(resolved_artifact_root, repo_root=_MODULE_REPOSITORY_ROOT)
    output_root = (resolved_artifact_root / KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID).resolve()
    _reject_repo_path(output_root, repo_root=resolved_repo_root)
    _reject_repo_path(output_root, repo_root=_MODULE_REPOSITORY_ROOT)
    output_dir = (output_root / run_label).resolve()
    if not output_dir.is_relative_to(output_root):
        raise ValueError("KIS daily universe CPU baseline artifact path escapes its root")
    _reject_repo_path(output_dir, repo_root=resolved_repo_root)
    _reject_repo_path(output_dir, repo_root=_MODULE_REPOSITORY_ROOT)
    if output_dir.exists():
        raise FileExistsError("KIS daily universe CPU baseline artifact already exists")
    temporary_root = _prepare_transient_replay_root(resolved_artifact_root)

    baseline_input = build_kis_paper_daily_universe_cpu_baseline_input()
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_payload = _precommit_payload(baseline_input)
    precommit_hash = _sha256_payload(precommit_payload)
    _write_json_new(
        output_dir / "precommit.json",
        {
            **precommit_payload,
            "attempt": {"run_label": run_label},
            "precommit_hash": precommit_hash,
        },
    )
    precommit_path = output_dir / "precommit.json"

    try:
        momentum_cells = _run_momentum_cells(
            baseline_input=baseline_input,
            temporary_root=temporary_root,
            run_label=run_label,
        )
        naive_cells = _run_naive_cells(
            baseline_input=baseline_input,
            temporary_root=temporary_root,
            run_label=run_label,
        )
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "status": "incomplete",
                "baseline_id": KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID,
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "selection_allowed": False,
                "ensemble_allowed": False,
                "promotion_allowed": False,
                "raw_market_data_written": False,
            },
        )
        raise

    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            baseline_input=baseline_input,
            precommit_hash=precommit_hash,
            momentum_cells=momentum_cells,
            naive_cells=naive_cells,
        ),
    )
    return KisPaperDailyUniverseCpuBaselineRun(
        baseline_input=baseline_input,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        momentum_cells=momentum_cells,
        naive_cells=naive_cells,
        summary_path=summary_path,
    )


def _build_split(
    completed_input: KisPaperDailyUniverseCompletedBarInput,
) -> KisPaperDailyUniverseCpuBaselineSplit:
    bars = completed_input.cataloged_bars.bars
    if len(bars) != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SESSION_COUNT:
        raise ValueError("KIS daily universe CPU baseline requires the frozen 199-session panel")
    validation_start = (
        KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DEVELOPMENT_SESSIONS
        + KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_PURGE_SESSIONS
    )
    return KisPaperDailyUniverseCpuBaselineSplit(
        development=CampaignWindow(
            bars[0].start_ts,
            bars[KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DEVELOPMENT_SESSIONS - 1].end_ts,
        ),
        purge=CampaignWindow(
            bars[KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DEVELOPMENT_SESSIONS].start_ts,
            bars[validation_start - 1].end_ts,
        ),
        validation=CampaignWindow(bars[validation_start].start_ts, bars[-1].end_ts),
        development_session_count=KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DEVELOPMENT_SESSIONS,
        purge_session_count=KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_PURGE_SESSIONS,
        validation_session_count=KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_VALIDATION_SESSIONS,
    )


def _build_campaign(
    panel: KisPaperDailyUniversePanel,
    *,
    split: KisPaperDailyUniverseCpuBaselineSplit,
    spec: KisPaperDailyUniverseCpuBaselineSpec,
) -> CampaignContract:
    last_bar = panel.validation_series(NAS_COMMON_STOCK_PROBE_SYMBOLS[0]).bars[-1]
    gap = split.validation.start_utc - split.development.end_utc
    return CampaignContract(
        campaign_id=KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID,
        catalog=CatalogDatasetRef(
            catalog_id="kis-paper-daily-universe-current-basket-v1",
            dataset_id=panel.dataset_id,
            dataset_hash=panel.dataset_hash,
            constructed_as_of_utc=last_bar.end_ts,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.D1,
        folds=(
            CampaignFold(
                KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_FOLD_ID,
                split.development,
                split.validation,
            ),
        ),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=spec.fee_bps,
            slippage_bps=spec.slippage_bps,
            slippage_source_id="fixed-local-paper-cost-v1",
        ),
        purge=gap,
        embargo=gap,
        evidence_use="development",
        sealed_holdout=None,
        naive_baselines=(KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR,),
        metrics=(
            "after_cost_pnl",
            "gross_pnl",
            "fee_cost",
            "slippage_cost",
            "trade_count",
            "decision_count",
        ),
        deterministic_seed=KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DETERMINISTIC_SEED,
    )


def _precommit_payload(
    baseline_input: KisPaperDailyUniverseCpuBaselineInput,
) -> dict[str, object]:
    panel = baseline_input.panel
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "precommitted",
        "baseline_id": KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID,
        "claim": (
            "fixed per-symbol completed-bar momentum versus always-long "
            "CPU local-paper evidence only; no stock selection, winner, ensemble, "
            "promotion, profitability claim, paper order, or live behavior"
        ),
        "source": {
            "dataset_id": panel.dataset_id,
            "dataset_hash": panel.dataset_hash,
            "cache_manifest_sha256": panel.cache_manifest_sha256,
            "panel_evidence_sha256": panel.evidence_sha256,
            "registry_sha256": panel.registry_sha256,
            "source_manifest_sha256": panel.source_manifest_sha256,
            "source_file_sha256": panel.source_file_sha256,
            "symbols": list(NAS_COMMON_STOCK_PROBE_SYMBOLS),
            "market": "US",
            "timeframe": Timeframe.D1.value,
            "adjustment_mode": panel.adjustment_mode,
            "completion_rule": panel.completion_rule,
            "common_session_count": len(panel.common_sessions),
            "source_mixing_allowed": False,
            "limitations": list(panel.source_limitations),
        },
        "campaign_contract": baseline_input.campaign.to_payload(),
        "campaign_contract_hash": baseline_input.campaign.contract_hash,
        "chronological_split": baseline_input.split.to_payload(),
        "spec": baseline_input.spec.to_payload(),
        "replay": {
            "per_symbol": True,
            "cross_sectional_ranking": False,
            "decision": "completed_daily_bar_close",
            "entry": "next_observed_daily_open",
            "exit": "following_observed_daily_open",
            "long_only": True,
            "non_overlapping_decision_stride_sessions": (
                baseline_input.spec.decision_stride_sessions
            ),
            "fill_source": LOCAL_PAPER_SOURCE,
            "tuning_allowed": False,
        },
        "reporting": {
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "paper_order_allowed": False,
            "profitability_claim_allowed": False,
            "falsification_trigger": (
                "any positive per-symbol after-cost PnL delta versus the naive comparator"
            ),
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "raw_market_data_written": False,
            "replay_event_logs_retained": False,
            "credentials_read": False,
            "network_access": False,
            "broker_access": False,
            "gpu_used": False,
        },
    }


def _run_momentum_cells(
    *,
    baseline_input: KisPaperDailyUniverseCpuBaselineInput,
    temporary_root: Path,
    run_label: str,
) -> tuple[KisPaperDailyUniverseCpuBaselineCell, ...]:
    cells: list[KisPaperDailyUniverseCpuBaselineCell] = []
    for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS:
        completed = baseline_input.inputs_by_symbol[symbol]
        result, verification = _run_temporary_replay(
            completed=completed,
            baseline_input=baseline_input,
            model=baseline_input.spec.momentum_model(),
            baseline_id=None,
            strategy_id="momentum",
            run_id=(
                f"{KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID}-momentum-{symbol.lower()}-{run_label}"
            ),
            temporary_root=temporary_root,
        )
        cells.append(
            KisPaperDailyUniverseCpuBaselineCell(
                symbol=symbol,
                strategy_id="momentum_close_v1",
                result=result,
                verification=verification,
            )
        )
    return tuple(cells)


def _run_naive_cells(
    *,
    baseline_input: KisPaperDailyUniverseCpuBaselineInput,
    temporary_root: Path,
    run_label: str,
) -> tuple[KisPaperDailyUniverseCpuBaselineCell, ...]:
    cells: list[KisPaperDailyUniverseCpuBaselineCell] = []
    for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS:
        completed = baseline_input.inputs_by_symbol[symbol]
        result, verification = _run_temporary_replay(
            completed=completed,
            baseline_input=baseline_input,
            model=_AlwaysLongNaiveModel(),
            baseline_id=KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR,
            strategy_id="naive",
            run_id=(
                f"{KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID}-naive-{symbol.lower()}-{run_label}"
            ),
            temporary_root=temporary_root,
        )
        cells.append(
            KisPaperDailyUniverseCpuBaselineCell(
                symbol=symbol,
                strategy_id=KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR,
                result=result,
                verification=verification,
            )
        )
    return tuple(cells)


@dataclass(frozen=True)
class _AlwaysLongNaiveModel:
    """The precommitted market-direction comparator used on the same signal calendar."""

    lookback: int = 0

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if not bars:
            raise ValueError("always-long naive comparator requires a completed bar")
        latest = bars[-1]
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action="buy",
            strength=Decimal("1"),
            reason="always_long_naive_comparator",
            timeframe=Timeframe(latest.timeframe),
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id="naive_always_long",
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=Decimal("1"),
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={
                "baseline_id": KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_NAIVE_COMPARATOR,
                "deterministic_seed": KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_DETERMINISTIC_SEED,
            },
        )


def _run_temporary_replay(
    *,
    completed: KisPaperDailyUniverseCompletedBarInput,
    baseline_input: KisPaperDailyUniverseCpuBaselineInput,
    model: MomentumModel | _AlwaysLongNaiveModel,
    baseline_id: str | None,
    strategy_id: str,
    run_id: str,
    temporary_root: Path,
) -> tuple[ValidationResult, KisPaperDailyUniverseCpuBaselineReplayVerification]:
    with TemporaryDirectory(
        prefix=_TRANSIENT_REPLAY_PREFIX,
        dir=temporary_root,
    ) as temporary_name:
        work_dir = Path(temporary_name)
        _write_json_new(
            work_dir / _TRANSIENT_REPLAY_OWNER_FILE,
            {
                "baseline_id": KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID,
                "kind": "transient_local_paper_replay",
                "process_id": os.getpid(),
                "raw_market_data_written": False,
                "replay_event_logs_retained": False,
            },
        )
        events_path = work_dir / "events.jsonl"
        emergency_path = work_dir / "emergency.json"
        event_store = EventStore(
            work_dir / "unused-state.sqlite",
            events_path,
            rebuild_sqlite_on_append=False,
        )
        emergency_store = EmergencyStore(emergency_path)
        emergency_store.write(
            EmergencyState(
                stop_new_orders=False,
                cancel_open_orders_requested=False,
                reason="kis_daily_universe_cpu_baseline_validation_only",
                updated_at=baseline_input.split.validation.start_utc,
            )
        )
        result = run_local_paper_validation(
            completed.cataloged_bars,
            event_store=event_store,
            emergency_store=emergency_store,
            model=model,
            config=ValidationConfig(
                run_id=run_id,
                starting_cash=baseline_input.spec.starting_cash,
                quantity=baseline_input.spec.quantity,
                fee_bps=baseline_input.spec.fee_bps,
                slippage_bps=baseline_input.spec.slippage_bps,
            ),
            campaign=baseline_input.campaign,
            phase="validation",
            fold_id=KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_FOLD_ID,
            baseline_id=baseline_id,
            eligible_signal_starts=_eligible_signal_starts(
                completed=completed,
                baseline_input=baseline_input,
            ),
        )
        verification = _verify_local_paper_replay(
            result=result,
            event_store=event_store,
            events_path=events_path,
            emergency_path=emergency_path,
            symbol=completed.symbol,
            starting_cash=baseline_input.spec.starting_cash,
            bars=completed.cataloged_bars.bars,
        )
    return result, verification


def _eligible_signal_starts(
    *,
    completed: KisPaperDailyUniverseCompletedBarInput,
    baseline_input: KisPaperDailyUniverseCpuBaselineInput,
) -> frozenset[datetime]:
    bars = completed.cataloged_bars.bars
    validation_start = (
        baseline_input.split.development_session_count + baseline_input.split.purge_session_count
    )
    start = validation_start + baseline_input.spec.momentum_lookback
    stop = len(bars) - baseline_input.campaign.target.exit_bar_offset
    return frozenset(
        bars[index].start_ts
        for index in range(start, stop, baseline_input.spec.decision_stride_sessions)
    )


def _verify_local_paper_replay(
    *,
    result: ValidationResult,
    event_store: EventStore,
    events_path: Path,
    emergency_path: Path,
    symbol: str,
    starting_cash: Decimal,
    bars: tuple[Bar, ...],
) -> KisPaperDailyUniverseCpuBaselineReplayVerification:
    if result.symbol != symbol or result.final_position != 0 or len(result.trades) % 2:
        raise ValueError("KIS daily universe replay is not a flat local-paper result")
    fill_evidence = collect_fill_source_evidence(
        (
            FillEventArtifact(
                path=events_path,
                expected_fill_count=len(result.trades),
                label=f"{symbol}:{result.run_id}",
            ),
        )
    )
    if not fill_evidence.local_paper_replay_invariant_passed:
        raise ValueError("KIS daily universe replay fill source is not local-paper only")
    replayed_account = replay_local_paper_account(event_store, starting_cash=starting_cash)
    replayed_position = replayed_account.quantity(market="US", symbol=symbol)
    if replayed_account.cash != result.ending_cash or replayed_position != result.final_position:
        raise ValueError("KIS daily universe replay account cannot be reconstructed")
    bar_index_by_end = {bar.end_ts: index for index, bar in enumerate(bars)}
    if len(bar_index_by_end) != len(bars):
        raise ValueError("KIS daily universe replay bars must have unique completed ends")
    for entry, exit_fill in zip(result.trades[::2], result.trades[1::2], strict=True):
        entry_signal_index = bar_index_by_end.get(entry.signal_bar_end)
        exit_signal_index = bar_index_by_end.get(exit_fill.signal_bar_end)
        if (
            entry.side != "buy"
            or exit_fill.side != "sell"
            or entry.quantity != exit_fill.quantity
            or entry_signal_index is None
            or exit_signal_index is None
            or entry_signal_index + 2 >= len(bars)
            or exit_signal_index != entry_signal_index + 1
            or entry.filled_at != bars[entry_signal_index + 1].start_ts
            or exit_fill.filled_at != bars[exit_signal_index + 1].start_ts
            or exit_fill.filled_at < entry.filled_at
        ):
            raise ValueError("KIS daily universe replay timing is invalid")
    return KisPaperDailyUniverseCpuBaselineReplayVerification(
        fill_source=LOCAL_PAPER_SOURCE,
        local_paper_fill_count=fill_evidence.fill_source_counts.get(LOCAL_PAPER_SOURCE, 0),
        expected_fill_count=len(result.trades),
        all_fills_local_paper=fill_evidence.all_fills_local_paper,
        local_paper_replay_invariant_passed=fill_evidence.local_paper_replay_invariant_passed,
        event_jsonl_sha256=_sha256_file(events_path),
        emergency_sha256=_sha256_file(emergency_path),
        replayed_ending_cash=replayed_account.cash,
        replayed_final_position=replayed_position,
    )


def _summary_payload(
    *,
    baseline_input: KisPaperDailyUniverseCpuBaselineInput,
    precommit_hash: str,
    momentum_cells: tuple[KisPaperDailyUniverseCpuBaselineCell, ...],
    naive_cells: tuple[KisPaperDailyUniverseCpuBaselineCell, ...],
) -> dict[str, object]:
    naive_by_symbol = {cell.symbol: cell for cell in naive_cells}
    panel = baseline_input.panel
    outcomes = tuple(
        _per_symbol_outcome(momentum, naive_by_symbol[momentum.symbol])
        for momentum in momentum_cells
    )
    positive_delta_symbols = tuple(
        str(outcome["symbol"])
        for outcome in outcomes
        if Decimal(str(outcome["descriptive_after_cost_pnl_delta_momentum_minus_naive"]))
        > Decimal("0")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_cpu_local_paper",
        "claim": (
            "fixed per-symbol daily momentum and naive-comparator evidence only; not a "
            "winner, stock-selection result, ensemble, promotion, profitability claim, "
            "paper order, or live behavior"
        ),
        "source": {
            "dataset_id": panel.dataset_id,
            "dataset_hash": panel.dataset_hash,
            "cache_manifest_sha256": panel.cache_manifest_sha256,
            "panel_evidence_sha256": panel.evidence_sha256,
            "registry_sha256": panel.registry_sha256,
            "symbols": list(NAS_COMMON_STOCK_PROBE_SYMBOLS),
            "market": "US",
            "timeframe": Timeframe.D1.value,
            "adjustment_mode": panel.adjustment_mode,
            "completion_rule": panel.completion_rule,
            "limitations": list(panel.source_limitations),
            "source_mixing_allowed": False,
        },
        "campaign_contract_hash": baseline_input.campaign.contract_hash,
        "chronological_split": baseline_input.split.to_payload(),
        "spec": baseline_input.spec.to_payload(),
        "precommit": {
            "hash": precommit_hash,
            "written_before_validation_replay": True,
        },
        "outcomes": list(outcomes),
        "validation": {
            "all_cells_local_paper": all(
                cell.verification.local_paper_replay_invariant_passed
                for cell in (*momentum_cells, *naive_cells)
            ),
            "all_cells_replayed_flat": all(
                cell.verification.replayed_final_position == 0
                for cell in (*momentum_cells, *naive_cells)
            ),
            "tuning_allowed": False,
        },
        "reporting": {
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "paper_order_allowed": False,
            "profitability_claim_allowed": False,
        },
        "falsification": {
            "positive_delta_symbols": list(positive_delta_symbols),
            "falsification_note": (
                "Any positive momentum-minus-naive delta is descriptive only and requires "
                "independent leakage, survivorship, cost, and replication falsification "
                "before it can support a research claim."
                if positive_delta_symbols
                else "No momentum cell exceeded its naive comparator in this fixed replay."
            ),
            "selection_allowed": False,
            "promotion_allowed": False,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "raw_market_data_written": False,
            "source_safe_summary": True,
            "replay_event_logs_retained": False,
            "credentials_read": False,
            "network_access": False,
            "broker_access": False,
            "gpu_used": False,
        },
    }


def _per_symbol_outcome(
    momentum: KisPaperDailyUniverseCpuBaselineCell,
    naive: KisPaperDailyUniverseCpuBaselineCell,
) -> dict[str, object]:
    if momentum.symbol != naive.symbol:
        raise ValueError("KIS daily universe outcomes must remain per-symbol")
    return {
        "symbol": momentum.symbol,
        "momentum": _cell_payload(momentum),
        "naive_comparator": _cell_payload(naive),
        "descriptive_after_cost_pnl_delta_momentum_minus_naive": str(
            momentum.result.after_cost_pnl - naive.result.after_cost_pnl
        ),
        "ranking_allowed": False,
        "winner": None,
    }


def _cell_payload(cell: KisPaperDailyUniverseCpuBaselineCell) -> dict[str, object]:
    result = cell.result
    return {
        "strategy_id": cell.strategy_id,
        "fill_source": cell.verification.fill_source,
        "decisions_seen": result.decisions_seen,
        "trade_count": len(result.trades),
        "after_cost_pnl": str(result.after_cost_pnl),
        "gross_pnl": str(result.gross_pnl),
        "total_fees": str(result.total_fees),
        "total_slippage": str(result.total_slippage),
        "replay_verification": cell.verification.to_payload(),
    }


def _window_payload(window: CampaignWindow) -> dict[str, str]:
    return {
        "start_utc": window.start_utc.isoformat(),
        "end_utc": window.end_utc.isoformat(),
    }


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _prepare_transient_replay_root(artifact_root: Path) -> Path:
    transient_root = (
        artifact_root / _TRANSIENT_REPLAY_ROOT_NAME / KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID
    ).resolve()
    if not transient_root.is_relative_to(artifact_root):
        raise ValueError("KIS daily universe transient replay path escapes its artifact root")
    _reject_repo_path(transient_root, repo_root=_MODULE_REPOSITORY_ROOT)
    if transient_root.exists():
        if (
            not transient_root.is_dir()
            or transient_root.is_symlink()
            or transient_root.resolve() != transient_root
        ):
            raise ValueError("KIS daily universe transient replay root is invalid")
    else:
        transient_root.mkdir(parents=True, exist_ok=False)
    _cleanup_owned_stale_transient_replays(transient_root)
    return transient_root


def _cleanup_owned_stale_transient_replays(transient_root: Path) -> None:
    for child in transient_root.iterdir():
        if (
            not child.is_dir()
            or child.is_symlink()
            or not child.name.startswith(_TRANSIENT_REPLAY_PREFIX)
        ):
            continue
        marker_path = child / _TRANSIENT_REPLAY_OWNER_FILE
        if marker_path.is_symlink() or not marker_path.is_file():
            continue
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            not isinstance(marker, dict)
            or marker.get("baseline_id") != KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID
            or marker.get("kind") != "transient_local_paper_replay"
        ):
            continue
        if _process_is_active(marker.get("process_id")):
            continue
        resolved_child = child.resolve()
        if not resolved_child.is_relative_to(transient_root):
            raise ValueError("KIS daily universe transient replay path escapes its root")
        shutil.rmtree(resolved_child)


def _process_is_active(process_id: object) -> bool:
    if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id <= 0:
        return False
    if process_id == os.getpid():
        return True
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _is_sha256(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return True


def _validate_run_label(run_label: str) -> None:
    if (
        not isinstance(run_label, str)
        or not 1 <= len(run_label) <= 80
        or run_label in {".", ".."}
        or any(
            not character.isascii() or not (character.isalnum() or character in {".", "_", "-"})
            for character in run_label
        )
    ):
        raise ValueError("KIS daily universe CPU baseline run_label is invalid")


def _reject_repo_path(path: Path, *, repo_root: Path) -> None:
    if path.is_relative_to(repo_root):
        raise ValueError(
            "KIS daily universe CPU baseline artifacts must stay outside the Git workspace"
        )
