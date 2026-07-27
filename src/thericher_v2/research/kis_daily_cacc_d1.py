"""CPU-only closing-auction co-confirmation research over pinned D1 folds.

The candidate is deliberately a fixed rule, not a trained model.  It uses the
existing QQQ/SPY joint-event materializer and target-cost adapter, runs every
replay through the broker-free local-paper simulator in memory, and persists
only source-safe aggregate evidence outside the repository.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    EmergencyState,
    ModelPrediction,
    Signal,
    Timeframe,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.kis_daily_joint_event_d1_materializer import (
    KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID,
    KisDailyJointEventD1Materializer,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_FORMULA_ID,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
    KisDailyJointEventD1TargetCostAdapter,
)
from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    is_container_external_mount,
)

from .campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)

KIS_DAILY_CACC_D1_ID = "kis-daily-cacc-d1-v1"
KIS_DAILY_CACC_D1_RULE_ID = "qqq-spy-closing-auction-co-confirmation-v1"
KIS_DAILY_CACC_D1_FOLD_IDS = ("expanding-1", "expanding-2", "expanding-3")
KIS_DAILY_CACC_D1_TOP_RANGE_FRACTION = Decimal("0.75")
KIS_DAILY_CACC_D1_STARTING_CASH = Decimal("10000")
KIS_DAILY_CACC_D1_QUANTITY = Decimal("1")
KIS_DAILY_CACC_D1_DETERMINISTIC_SEED = 619

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SOURCE_SAFE_FORBIDDEN_KEYS = frozenset(
    {
        "account",
        "cash",
        "close",
        "equity",
        "high",
        "label",
        "low",
        "open",
        "order",
        "position",
        "price",
        "raw_row",
        "raw_rows",
        "weight",
        "weights",
    }
)


@dataclass(frozen=True, slots=True)
class KisDailyCaccD1FoldBinding:
    """One verified sparse fold and its fixed target/cost semantics."""

    materializer: KisDailyJointEventD1Materializer
    target_adapter: KisDailyJointEventD1TargetCostAdapter
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.materializer, KisDailyJointEventD1Materializer)
            or not isinstance(self.target_adapter, KisDailyJointEventD1TargetCostAdapter)
            or self.materializer.fold_input.fold_id not in KIS_DAILY_CACC_D1_FOLD_IDS
            or self.target_adapter.materializer.materializer_identity
            != self.materializer.materializer_identity
            or not _is_sha256(self.target_adapter.target_cost_identity)
        ):
            raise ValueError("CACC-D1 fold binding is invalid")


@dataclass(frozen=True, slots=True)
class KisDailyCaccD1ReplayMetrics:
    """Aggregate local-paper facts with no prices, labels, or account values."""

    decision_count: int
    trade_count: int
    local_paper_fill_count: int
    after_cost_pnl: Decimal
    fill_source: str
    all_fills_local_paper: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.decision_count < 0
            or self.trade_count < 0
            or self.local_paper_fill_count < 0
            or self.local_paper_fill_count != self.trade_count * 2
            or not self.after_cost_pnl.is_finite()
            or self.fill_source != "local_paper"
            or not self.all_fills_local_paper
        ):
            raise ValueError("CACC-D1 local-paper replay metrics are invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "decision_count": self.decision_count,
            "trade_count": self.trade_count,
            "local_paper_fill_count": self.local_paper_fill_count,
            "after_cost_pnl": str(self.after_cost_pnl),
            "fill_source": self.fill_source,
            "all_fills_local_paper": self.all_fills_local_paper,
        }


@dataclass(frozen=True, slots=True)
class KisDailyCaccD1KillResult:
    """Precommitted fold-local rejection rule for the fixed candidate."""

    zero_trades: bool
    nonpositive_after_cost_pnl: bool
    does_not_beat_always_long: bool
    falsified: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.falsified != (
            self.zero_trades
            or self.nonpositive_after_cost_pnl
            or self.does_not_beat_always_long
        ):
            raise ValueError("CACC-D1 kill result is inconsistent")

    def to_payload(self) -> dict[str, bool]:
        return {
            "zero_trades": self.zero_trades,
            "nonpositive_after_cost_pnl": self.nonpositive_after_cost_pnl,
            "does_not_beat_time_matched_always_long": self.does_not_beat_always_long,
            "falsified": self.falsified,
        }


@dataclass(frozen=True, slots=True)
class KisDailyCaccD1FoldRun:
    fold_id: str
    validation_eligible_decision_count: int
    validation_eligible_decision_identity: str
    candidate: KisDailyCaccD1ReplayMetrics
    always_long: KisDailyCaccD1ReplayMetrics
    flat: KisDailyCaccD1ReplayMetrics
    kill_result: KisDailyCaccD1KillResult
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.fold_id not in KIS_DAILY_CACC_D1_FOLD_IDS
            or self.validation_eligible_decision_count <= 0
            or not _is_sha256(self.validation_eligible_decision_identity)
            or any(
                item.decision_count != self.validation_eligible_decision_count
                for item in (self.candidate, self.always_long, self.flat)
            )
        ):
            raise ValueError("CACC-D1 fold run is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "fold_id": self.fold_id,
            "validation": {
                "eligible_decision_count": self.validation_eligible_decision_count,
                "eligible_decision_identity": self.validation_eligible_decision_identity,
            },
            "candidate": self.candidate.to_payload(),
            "time_matched_always_long": self.always_long.to_payload(),
            "flat": self.flat.to_payload(),
            "kill_rule": self.kill_result.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class KisDailyCaccD1Run:
    bindings: tuple[KisDailyCaccD1FoldBinding, ...]
    precommit_path: Path
    precommit_hash: str
    fold_runs: tuple[KisDailyCaccD1FoldRun, ...]
    falsified: bool
    summary_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "fold_runs", tuple(self.fold_runs))
        if (
            tuple(binding.materializer.fold_input.fold_id for binding in self.bindings)
            != KIS_DAILY_CACC_D1_FOLD_IDS
            or tuple(run.fold_id for run in self.fold_runs) != KIS_DAILY_CACC_D1_FOLD_IDS
            or self.falsified != any(run.kill_result.falsified for run in self.fold_runs)
            or not _is_sha256(self.precommit_hash)
        ):
            raise ValueError("CACC-D1 run is invalid")


@dataclass(frozen=True, slots=True)
class _CaccD1ReplayDecisionAdapter:
    """Fixed decision adapter used only by the broker-free replay harness."""

    model_id: str
    action_by_feature_end: Mapping[datetime, str]
    reason: str
    lookback: int = 0

    def __post_init__(self) -> None:
        normalized = dict(self.action_by_feature_end)
        if (
            not self.model_id
            or self.lookback != 0
            or not normalized
            or any(action not in {"buy", "hold"} for action in normalized.values())
        ):
            raise ValueError("CACC-D1 replay decision adapter is invalid")
        object.__setattr__(self, "action_by_feature_end", MappingProxyType(normalized))

    def predict(self, bars: list[object]) -> ModelPrediction:
        if not bars:
            raise ValueError("CACC-D1 replay requires one completed decision bar")
        latest = bars[-1]
        feature_end = getattr(latest, "end_ts", None)
        action = self.action_by_feature_end.get(feature_end)
        if action is None:
            raise ValueError("CACC-D1 replay received an unqualified decision bar")
        if (
            getattr(latest, "symbol", None) != "QQQ"
            or getattr(latest, "market", None) != "US"
            or getattr(latest, "timeframe", None) != Timeframe.D1
            or not getattr(latest, "complete", False)
        ):
            raise ValueError("CACC-D1 replay decision bar is invalid")
        strength = Decimal("1") if action == "buy" else Decimal("0")
        signal = Signal(
            symbol="QQQ",
            market="US",
            action=action,
            strength=strength,
            reason=self.reason,
            timeframe=Timeframe.D1,
            generated_at=feature_end,
        )
        return ModelPrediction(
            model_id=self.model_id,
            model_version="1.0.0",
            symbol="QQQ",
            market="US",
            signal=signal,
            confidence=strength,
            expected_edge_bps=Decimal("0"),
            feature_window_end=feature_end,
            metadata={"rule_id": KIS_DAILY_CACC_D1_RULE_ID},
        )


@dataclass(slots=True)
class _InMemoryEmergencyStore:
    """Minimal no-file emergency boundary for an offline replay."""

    state: EmergencyState

    def read(self) -> EmergencyState:
        return self.state

    def write(self, state: EmergencyState) -> EmergencyState:
        self.state = state
        return state


def cacc_d1_should_buy(*, qqq_bar: object, spy_bar: object) -> bool:
    """Apply the fixed co-confirmation rule to one completed daily bar pair."""

    return _qualifies_closing_auction(qqq_bar) and _qualifies_closing_auction(spy_bar)


def evaluate_kis_daily_cacc_d1_kill_rule(
    *,
    candidate: KisDailyCaccD1ReplayMetrics,
    always_long: KisDailyCaccD1ReplayMetrics,
) -> KisDailyCaccD1KillResult:
    """Reject one fold when the precommitted CACC-D1 condition fails."""

    zero_trades = candidate.trade_count == 0
    nonpositive_after_cost_pnl = candidate.after_cost_pnl <= Decimal("0")
    does_not_beat_always_long = candidate.after_cost_pnl <= always_long.after_cost_pnl
    return KisDailyCaccD1KillResult(
        zero_trades=zero_trades,
        nonpositive_after_cost_pnl=nonpositive_after_cost_pnl,
        does_not_beat_always_long=does_not_beat_always_long,
        falsified=(zero_trades or nonpositive_after_cost_pnl or does_not_beat_always_long),
    )


def run_kis_daily_cacc_d1(
    *,
    bindings: Sequence[KisDailyCaccD1FoldBinding],
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | None = None,
) -> KisDailyCaccD1Run:
    """Run the fixed CACC-D1 rule separately on the three pinned folds."""

    _validate_run_label(run_label)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    output_dir = _create_external_output_dir(
        artifact_root=resolved_artifact_root,
        repo_root=resolved_repo_root,
        run_label=run_label,
    )
    normalized_bindings = _validate_bindings(bindings)
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_payload = _precommit_payload(normalized_bindings)
    precommit_hash = _sha256_json(precommit_payload)
    precommit_payload["precommit_hash"] = precommit_hash
    precommit_path = output_dir / "precommit.json"
    _write_source_safe_json_new(precommit_path, precommit_payload)

    try:
        fold_runs = tuple(
            _run_fold(binding, run_label=run_label) for binding in normalized_bindings
        )
    except Exception as error:
        _write_source_safe_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "kind": KIS_DAILY_CACC_D1_ID,
                "status": "incomplete",
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "artifact_policy": _artifact_policy_payload(),
            },
        )
        raise

    falsified = any(fold_run.kill_result.falsified for fold_run in fold_runs)
    summary_path = output_dir / "summary.json"
    _write_source_safe_json_new(
        summary_path,
        _summary_payload(
            bindings=normalized_bindings,
            precommit_hash=precommit_hash,
            fold_runs=fold_runs,
            falsified=falsified,
        ),
    )
    return KisDailyCaccD1Run(
        bindings=normalized_bindings,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        fold_runs=fold_runs,
        falsified=falsified,
        summary_path=summary_path,
    )


def _run_fold(
    binding: KisDailyCaccD1FoldBinding,
    *,
    run_label: str,
) -> KisDailyCaccD1FoldRun:
    materializer = binding.materializer
    fold_id = materializer.fold_input.fold_id
    eligible_indices = materializer.eligible_decision_indices("validation")
    if not eligible_indices:
        raise ValueError("CACC-D1 validation fold has no sparse eligible decisions")

    candidate_actions: dict[datetime, str] = {}
    eligible_starts: set[datetime] = set()
    for decision_index in eligible_indices:
        window = materializer.materialize(phase="validation", decision_index=decision_index)
        target = binding.target_adapter.derive(
            phase="validation",
            decision_index=decision_index,
        )
        if (
            target.target_cost_identity != binding.target_adapter.target_cost_identity
            or target.decision_index != decision_index
            or target.decision_end != window.decision_end
            or target.entry_start != window.target_references.entry_start
            or target.exit_start != window.target_references.exit_start
        ):
            raise ValueError("CACC-D1 target/cost path is incompatible")
        qqq_bar = materializer.bars_by_symbol["QQQ"][decision_index]
        spy_bar = materializer.bars_by_symbol["SPY"][decision_index]
        candidate_actions[window.decision_end] = (
            "buy" if cacc_d1_should_buy(qqq_bar=qqq_bar, spy_bar=spy_bar) else "hold"
        )
        eligible_starts.add(window.decision_start)

    if (
        len(candidate_actions) != len(eligible_indices)
        or len(eligible_starts) != len(eligible_indices)
    ):
        raise ValueError("CACC-D1 sparse decision geometry is invalid")
    campaign = _build_campaign(materializer)
    cataloged_qqq = _cataloged_qqq_bars(materializer)
    allowed_starts = frozenset(eligible_starts)
    candidate = _run_ephemeral_local_paper_replay(
        cataloged_qqq=cataloged_qqq,
        campaign=campaign,
        fold_id=fold_id,
        eligible_signal_starts=allowed_starts,
        model=_CaccD1ReplayDecisionAdapter(
            model_id="cacc_d1_candidate",
            action_by_feature_end=candidate_actions,
            reason="cacc_d1_co_confirmed" ,
        ),
        run_id=f"{KIS_DAILY_CACC_D1_ID}-{fold_id}-candidate-{run_label}",
    )
    always_long = _run_ephemeral_local_paper_replay(
        cataloged_qqq=cataloged_qqq,
        campaign=campaign,
        fold_id=fold_id,
        eligible_signal_starts=allowed_starts,
        model=_CaccD1ReplayDecisionAdapter(
            model_id="cacc_d1_time_matched_always_long",
            action_by_feature_end={timestamp: "buy" for timestamp in candidate_actions},
            reason="cacc_d1_time_matched_always_long",
        ),
        run_id=f"{KIS_DAILY_CACC_D1_ID}-{fold_id}-always-long-{run_label}",
    )
    flat = _run_ephemeral_local_paper_replay(
        cataloged_qqq=cataloged_qqq,
        campaign=campaign,
        fold_id=fold_id,
        eligible_signal_starts=allowed_starts,
        model=_CaccD1ReplayDecisionAdapter(
            model_id="cacc_d1_flat",
            action_by_feature_end={timestamp: "hold" for timestamp in candidate_actions},
            reason="cacc_d1_flat",
        ),
        run_id=f"{KIS_DAILY_CACC_D1_ID}-{fold_id}-flat-{run_label}",
    )
    kill_result = evaluate_kis_daily_cacc_d1_kill_rule(
        candidate=candidate,
        always_long=always_long,
    )
    return KisDailyCaccD1FoldRun(
        fold_id=fold_id,
        validation_eligible_decision_count=len(eligible_indices),
        validation_eligible_decision_identity=(
            materializer.fold_input.validation_eligible_decision_identity
        ),
        candidate=candidate,
        always_long=always_long,
        flat=flat,
        kill_result=kill_result,
    )


def _run_ephemeral_local_paper_replay(
    *,
    cataloged_qqq: CatalogedBars,
    campaign: CampaignContract,
    fold_id: str,
    eligible_signal_starts: frozenset[datetime],
    model: _CaccD1ReplayDecisionAdapter,
    run_id: str,
) -> KisDailyCaccD1ReplayMetrics:
    """Use existing local-paper mechanics without writing replay data to disk.

    CACC-D1 is a stateless, fixed-one-share target-window control. Adjacent
    signals use half-open windows: the prior exit at a shared open is recorded
    before the next entry at that same open. This is not a portfolio simulator
    for cash-dependent sizing, position-dependent signals, or multi-symbol
    allocation.
    """

    from thericher_v2.research.validation import (
        InMemoryCampaignEventStore,
        ValidationConfig,
        run_local_paper_validation,
    )

    event_store = InMemoryCampaignEventStore()
    emergency_store = _InMemoryEmergencyStore(
        state=EmergencyState(
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            reason="cacc_d1_offline_replay",
            updated_at=campaign.resolve_window("validation", fold_id=fold_id)[1].start_utc,
        )
    )
    with localcontext() as context:
        context.prec = KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        result = run_local_paper_validation(
            cataloged_qqq,
            event_store=event_store,
            emergency_store=emergency_store,  # type: ignore[arg-type]
            model=model,
            config=ValidationConfig(
                run_id=run_id,
                starting_cash=KIS_DAILY_CACC_D1_STARTING_CASH,
                quantity=KIS_DAILY_CACC_D1_QUANTITY,
                fee_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
                slippage_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
            ),
            campaign=campaign,
            phase="validation",
            fold_id=fold_id,
            eligible_signal_starts=eligible_signal_starts,
        )
    fill_events = tuple(event for event in event_store.iter_events() if event.event_type == "fill")
    if (
        result.decisions_seen != len(eligible_signal_starts)
        or result.final_position != Decimal("0")
        or len(fill_events) != len(result.trades)
        or any(event.payload.get("source") != "local_paper" for event in fill_events)
        or len(fill_events) % 2 != 0
    ):
        raise RuntimeError("CACC-D1 local-paper replay invariants failed")
    return KisDailyCaccD1ReplayMetrics(
        decision_count=result.decisions_seen,
        trade_count=len(fill_events) // 2,
        local_paper_fill_count=len(fill_events),
        after_cost_pnl=result.after_cost_pnl,
        fill_source="local_paper",
        all_fills_local_paper=True,
    )


def _build_campaign(materializer: KisDailyJointEventD1Materializer) -> CampaignContract:
    fold = materializer.fold_input
    qqq_bars = materializer.bars_by_symbol["QQQ"]
    development = CampaignWindow(
        qqq_bars[fold.development_start_index].start_ts,
        qqq_bars[fold.development_end_index - 1].end_ts,
    )
    validation = CampaignWindow(
        qqq_bars[fold.validation_start_index].start_ts,
        qqq_bars[fold.validation_end_index - 1].end_ts,
    )
    gap = validation.start_utc - development.end_utc
    return CampaignContract(
        campaign_id=f"{KIS_DAILY_CACC_D1_ID}-{fold.fold_id}",
        catalog=CatalogDatasetRef(
            catalog_id=f"{KIS_DAILY_CACC_D1_ID}:{KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID}",
            dataset_id=KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID,
            dataset_hash=materializer.catalog_dataset_hash,
            constructed_as_of_utc=qqq_bars[-1].end_ts,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.D1,
        folds=(CampaignFold(fold.fold_id, development, validation),),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
            slippage_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
            slippage_source_id="kis-daily-joint-event-d1-target-cost-v2",
        ),
        purge=gap,
        embargo=gap,
        evidence_use="development",
        sealed_holdout=None,
        naive_baselines=("always_long", "flat"),
        metrics=("after_cost_pnl", "gross_pnl", "fee_cost", "slippage_cost", "trade_count"),
        deterministic_seed=KIS_DAILY_CACC_D1_DETERMINISTIC_SEED,
    )


def _cataloged_qqq_bars(materializer: KisDailyJointEventD1Materializer) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID,
        dataset_hash=materializer.catalog_dataset_hash,
        source_path=Path("cacc-d1-materializer-in-memory"),
        bars=materializer.bars_by_symbol["QQQ"],
    )


def _qualifies_closing_auction(bar: object) -> bool:
    high = getattr(bar, "high", None)
    low = getattr(bar, "low", None)
    opening = getattr(bar, "open", None)
    closing = getattr(bar, "close", None)
    if (
        not all(
            isinstance(value, Decimal) and value.is_finite()
            for value in (high, low, opening, closing)
        )
        or high <= low
        or closing <= opening
    ):
        return False
    return (closing - low) / (high - low) >= KIS_DAILY_CACC_D1_TOP_RANGE_FRACTION


def _validate_bindings(
    bindings: Sequence[KisDailyCaccD1FoldBinding],
) -> tuple[KisDailyCaccD1FoldBinding, ...]:
    normalized = tuple(bindings)
    if (
        len(normalized) != len(KIS_DAILY_CACC_D1_FOLD_IDS)
        or any(not isinstance(item, KisDailyCaccD1FoldBinding) for item in normalized)
        or tuple(item.materializer.fold_input.fold_id for item in normalized)
        != KIS_DAILY_CACC_D1_FOLD_IDS
    ):
        raise ValueError("CACC-D1 requires expanding-1, expanding-2, and expanding-3 in order")
    return normalized


def _precommit_payload(bindings: tuple[KisDailyCaccD1FoldBinding, ...]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_DAILY_CACC_D1_ID,
        "status": "precommitted",
        "claim": (
            "fixed QQQ/SPY closing-auction co-confirmation rule; fold-local descriptive "
            "local-paper validation only, with no tuning, model fitting, GPU, selection, "
            "ensemble, checkpoint, Paper route, or KIS access"
        ),
        "rule": {
            "rule_id": KIS_DAILY_CACC_D1_RULE_ID,
            "requires_positive_body_for_both_symbols": True,
            "requires_nonzero_range_for_both_symbols": True,
            "top_range_fraction": str(KIS_DAILY_CACC_D1_TOP_RANGE_FRACTION),
            "long_symbol": "QQQ",
            "reference_symbol": "SPY",
        },
        "target_cost": {
            "formula_id": KIS_DAILY_JOINT_EVENT_D1_TARGET_FORMULA_ID,
            "fee_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL),
            "slippage_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL),
            "decimal_precision": KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
            "rounding_mode": KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
            "starting_cash": str(KIS_DAILY_CACC_D1_STARTING_CASH),
            "quantity": str(KIS_DAILY_CACC_D1_QUANTITY),
        },
        "comparators": ("time_matched_always_long", "flat"),
        "adjacent_rollover": {
            "position_window": "[next_bar_open,following_bar_open)",
            "shared_timestamp_order": "exit_before_entry",
            "scope": "stateless_fixed_one_share_only",
        },
        "kill_rule": {
            "zero_trades_falsifies": True,
            "nonpositive_after_cost_pnl_falsifies": True,
            "does_not_beat_time_matched_always_long_falsifies": True,
            "folds_are_pooled": False,
        },
        "folds": [_binding_source_payload(binding) for binding in bindings],
        "artifact_policy": _artifact_policy_payload(),
    }


def _summary_payload(
    *,
    bindings: tuple[KisDailyCaccD1FoldBinding, ...],
    precommit_hash: str,
    fold_runs: tuple[KisDailyCaccD1FoldRun, ...],
    falsified: bool,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_DAILY_CACC_D1_ID,
        "status": "complete",
        "mode": "offline_cpu_local_paper",
        "precommit_hash": precommit_hash,
        "falsified": falsified,
        "folds": [fold_run.to_payload() for fold_run in fold_runs],
        "source": [_binding_source_payload(binding) for binding in bindings],
        "artifact_policy": _artifact_policy_payload(),
    }


def _binding_source_payload(binding: KisDailyCaccD1FoldBinding) -> dict[str, object]:
    fold = binding.materializer.fold_input
    return {
        "fold_id": fold.fold_id,
        "fold_artifact_sha256": binding.materializer.fold_artifact_sha256,
        "fold_input_identity": fold.fold_input_identity,
        "materializer_identity": binding.materializer.materializer_identity,
        "target_cost_identity": binding.target_adapter.target_cost_identity,
        "catalog_dataset_hash": binding.materializer.catalog_dataset_hash,
        "catalog_index_hash": binding.materializer.catalog_index_hash,
        "validation_eligible_decision_count": len(
            binding.materializer.eligible_decision_indices("validation")
        ),
        "validation_eligible_decision_identity": fold.validation_eligible_decision_identity,
    }


def _artifact_policy_payload() -> dict[str, bool]:
    return {
        "external_artifacts_only": True,
        "raw_market_data_persisted": False,
        "labels_persisted": False,
        "prices_persisted": False,
        "account_data_persisted": False,
        "weights_persisted": False,
        "checkpoints_persisted": False,
        "network_accessed": False,
        "credentials_accessed": False,
        "kis_accessed": False,
        "broker_network_accessed": False,
        "local_paper_only": True,
        "gpu_used": False,
    }


def _create_external_output_dir(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    if (
        artifact_root == repo_root or artifact_root.is_relative_to(repo_root)
    ) and not is_container_external_mount(artifact_root, repo_root):
        raise ValueError("CACC-D1 artifacts must stay outside the Git workspace")
    output_root = (artifact_root / KIS_DAILY_CACC_D1_ID).resolve()
    output_dir = (output_root / run_label).resolve()
    if not output_dir.is_relative_to(output_root):
        raise ValueError("CACC-D1 artifact destination is invalid")
    if output_dir.exists():
        raise FileExistsError("CACC-D1 run label already has external evidence")
    return output_dir


def _write_source_safe_json_new(path: Path, payload: Mapping[str, object]) -> None:
    _assert_source_safe(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(encoded)


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or key in _SOURCE_SAFE_FORBIDDEN_KEYS:
                raise ValueError("CACC-D1 artifact is not source-safe")
            _assert_source_safe(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _assert_source_safe(nested)
    elif isinstance(value, (str, int, float, bool)) or value is None:
        return
    else:
        raise ValueError("CACC-D1 artifact is not source-safe")


def _validate_run_label(run_label: str) -> None:
    if not isinstance(run_label, str) or _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("CACC-D1 run label is invalid")


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        return False
    return True


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
