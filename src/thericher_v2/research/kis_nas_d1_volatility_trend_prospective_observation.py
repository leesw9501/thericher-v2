"""Offline prospective shadow observations for the frozen NAS D1 candidates.

The sealed evaluation remains immutable candidate-only evidence.  This module
uses only a local reattested cache and the already-frozen r2/r5 artifact
lineage to create new, separately bounded observations.  It has no provider,
credential, KIS, account, order-route, or live-broker surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, EmergencyState, OrderIntent
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    build_kis_paper_daily_history_panel,
)
from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KisPaperDailyHistorySequenceInput,
    require_attested_kis_paper_daily_history_sequence_input,
)
from thericher_v2.data.kis_paper_daily_history_volatility_trend_prospective_input import (
    KisPaperDailyHistoryVolatilityTrendProspectiveInput,
    build_kis_paper_daily_history_volatility_trend_prospective_input,
    require_attested_kis_paper_daily_history_volatility_trend_prospective_input,
)
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE, replay_local_paper_account
from thericher_v2.research.causal_bar_features import (
    KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS,
    KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH,
    build_kis_nas_d1_volatility_trend_feature_sequence,
)
from thericher_v2.research.kis_nas_d1_volatility_trend_breadth import (
    KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS,
    KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS,
    KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
    KisNasD1VolatilityTrendArchitectureSpec,
    KisNasD1VolatilityTrendBreadthInput,
    build_kis_nas_d1_volatility_trend_breadth_input,
    fit_kis_nas_d1_volatility_trend_l2_logistic_smoke,
)
from thericher_v2.research.kis_nas_d1_volatility_trend_campaign import (
    KisNasD1VolatilityTrendCampaignInput,
    build_kis_nas_d1_volatility_trend_campaign,
    require_attested_kis_nas_d1_volatility_trend_campaign_input,
)
from thericher_v2.research.sequence_architecture_models import build_torch_sequence_model
from thericher_v2.research.validation import InMemoryCampaignEventStore, _CampaignLocalPaperBroker
from thericher_v2.state import Event

KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ID = (
    "kis-nas-d1-volatility-trend-prospective-observation-v1"
)
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/research"
)
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_STARTING_CASH = Decimal("10000")
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_QUANTITY = Decimal("1")
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_THRESHOLD = 0.5
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_DECISION_STRIDE = 3
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ALLOWED_REVIEW_STATUSES = frozenset(
    {"review_unavailable"}
)

# These are identities, not r5 outcomes.  The observer never consumes a score,
# ranking, kill-rule flag, or any other result from the sealed receipt.
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_PANEL_HASH = (
    "sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e"
)
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_CAMPAIGN_CONTRACT_HASH = (
    "sha256:85fcaabf2d96fceaea03a8d5504ea730eb88a5adda95d692b250614da840ac0b"
)
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_CAMPAIGN_PRECOMMIT_HASH = (
    "sha256:9f71107718c3235c1a52a092f3362b114e16f33387d7afaafc4b9d390e57deb9"
)
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_CPU_SUMMARY_HASH = (
    "sha256:65ba9f682bb6477bd7fdfa5d61761fb7ab67f3db23601187a92f88415bad69a8"
)
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_CUDA_SUMMARY_HASH = (
    "sha256:3158ac0e69c002394d97dc5f52946d70637e082f292a7c549498f4c045e5bc2c"
)
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_R5_PRECOMMIT_HASH = (
    "sha256:e7bd2cd8b17959a9b6df5c49c8bfa5a22ae875d9b2a53311890d55e51d7b4618"
)
KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_R5_SUMMARY_HASH = (
    "sha256:803ead4440415dd2818c2bc81a5579f5ae01354a43955ad97e5a526a8634d010"
)

_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"
_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendProspectiveEvidence:
    """Immutable artifact identities required before opening a new target."""

    panel_dataset_hash: str
    campaign_contract_hash: str
    campaign_precommit_hash: str
    cpu_summary_hash: str
    cuda_summary_hash: str
    r5_precommit_hash: str
    r5_summary_hash: str

    def __post_init__(self) -> None:
        if any(
            not _is_sha256(value)
            for value in (
                self.panel_dataset_hash,
                self.campaign_contract_hash,
                self.campaign_precommit_hash,
                self.cpu_summary_hash,
                self.cuda_summary_hash,
                self.r5_precommit_hash,
                self.r5_summary_hash,
            )
        ):
            raise ValueError("NAS D1 prospective evidence is invalid")


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendProspectiveObservationInput:
    """Reattested frozen and local prospective inputs held only in memory."""

    source_input: KisPaperDailyHistorySequenceInput
    prospective_panel: KisPaperDailyHistoryPanel
    prospective_input: KisPaperDailyHistoryVolatilityTrendProspectiveInput
    campaign_input: KisNasD1VolatilityTrendCampaignInput
    evidence: KisNasD1VolatilityTrendProspectiveEvidence
    cpu_summary_path: Path
    cuda_summary_path: Path
    checkpoint_root: Path
    r5_precommit_path: Path
    r5_summary_path: Path
    frozen_boundary: date


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendProspectiveSlot:
    """One causal, newly observed decision with a complete local-paper target."""

    symbol: str
    feature_sequence: tuple[tuple[float, ...], ...]
    signal_bar: Bar
    entry_bar: Bar
    exit_bar: Bar
    frozen_boundary: date

    def __post_init__(self) -> None:
        sequence = tuple(tuple(float(value) for value in row) for row in self.feature_sequence)
        object.__setattr__(self, "feature_sequence", sequence)
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.signal_bar.symbol != self.symbol
            or self.entry_bar.symbol != self.symbol
            or self.exit_bar.symbol != self.symbol
            or len(sequence) != KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH
            or any(len(row) != KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT for row in sequence)
            or self.signal_bar.start_ts.date() <= self.frozen_boundary
            or self.entry_bar.start_ts.date() <= self.frozen_boundary
            or self.exit_bar.start_ts.date() <= self.frozen_boundary
            or not (
                self.signal_bar.end_ts < self.entry_bar.end_ts < self.exit_bar.end_ts
            )
        ):
            raise ValueError("NAS D1 prospective slot is invalid")


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendProspectiveCandidateResult:
    """One source-safe aggregate local-paper replay result."""

    result_id: str
    model_family: str
    symbol: str
    lineage_hash: str
    sample_count: int
    long_slot_count: int
    fill_count: int
    after_cost_delta: Decimal
    maximum_drawdown: Decimal
    transcript_sha256: str
    fill_source: str
    all_fills_local_paper: bool
    replay_reconstructed: bool
    terminal_position_zero: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not self.result_id
            or not self.model_family
            or self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or not _is_sha256(self.lineage_hash)
            or self.sample_count <= 0
            or not 0 <= self.long_slot_count <= self.sample_count
            or self.fill_count != self.long_slot_count * 2
            or self.maximum_drawdown < 0
            or not _is_sha256(self.transcript_sha256)
            or self.fill_source != LOCAL_PAPER_SOURCE
            or not self.all_fills_local_paper
            or not self.replay_reconstructed
            or not self.terminal_position_zero
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 prospective candidate result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "result_id": self.result_id,
            "model_family": self.model_family,
            "symbol": self.symbol,
            "lineage_hash": self.lineage_hash,
            "sample_count": self.sample_count,
            "long_slot_count": self.long_slot_count,
            "fill_count": self.fill_count,
            "after_cost_delta": _decimal_text(self.after_cost_delta),
            "maximum_drawdown": _decimal_text(self.maximum_drawdown),
            "transcript_sha256": self.transcript_sha256,
            "fill_source": self.fill_source,
            "all_fills_local_paper": self.all_fills_local_paper,
            "replay_reconstructed": self.replay_reconstructed,
            "terminal_position_zero": self.terminal_position_zero,
            "event_rows_retained": False,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendProspectiveObservationRun:
    """One immutable prospective receipt and any in-memory candidate aggregates."""

    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput
    run_label: str
    status: Literal["completed", "input_unavailable"]
    precommit_path: Path
    precommit_hash: str
    receipt_path: Path
    receipt_hash: str
    candidate_results: tuple[KisNasD1VolatilityTrendProspectiveCandidateResult, ...]
    review_status: str


@dataclass(frozen=True, slots=True)
class _PredictionBatch:
    result_id: str
    model_family: str
    symbol: str
    lineage_hash: str
    probabilities: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _ClearEmergencyStore:
    updated_at: datetime

    def read(self) -> EmergencyState:
        return EmergencyState(
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            reason="prospective_nas_d1_volatility_trend_shadow_observation",
            updated_at=self.updated_at,
        )


def build_kis_nas_d1_volatility_trend_prospective_observation_input(
    source_input: KisPaperDailyHistorySequenceInput,
    prospective_panel: KisPaperDailyHistoryPanel,
    *,
    evidence: KisNasD1VolatilityTrendProspectiveEvidence,
    cpu_summary_path: Path | str,
    cuda_summary_path: Path | str,
    checkpoint_root: Path | str,
    r5_precommit_path: Path | str,
    r5_summary_path: Path | str,
    review_status: str,
) -> KisNasD1VolatilityTrendProspectiveObservationInput:
    """Bind frozen candidate lineage to a new local-cache observation boundary."""

    if (
        review_status
        not in KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ALLOWED_REVIEW_STATUSES
    ):
        raise ValueError("NAS D1 prospective review does not permit target opening")
    require_attested_kis_paper_daily_history_sequence_input(source_input)
    campaign_input = build_kis_nas_d1_volatility_trend_campaign(source_input)
    if (
        source_input.panel_dataset_hash != evidence.panel_dataset_hash
        or campaign_input.contract.contract_hash != evidence.campaign_contract_hash
    ):
        raise ValueError("NAS D1 prospective frozen source evidence is not pinned")
    frozen_boundary = source_input.validation.common_sessions[-1]
    prospective_input = build_kis_paper_daily_history_volatility_trend_prospective_input(
        prospective_panel,
        frozen_boundary=frozen_boundary,
    )
    result = KisNasD1VolatilityTrendProspectiveObservationInput(
        source_input=source_input,
        prospective_panel=prospective_panel,
        prospective_input=prospective_input,
        campaign_input=campaign_input,
        evidence=evidence,
        cpu_summary_path=Path(cpu_summary_path),
        cuda_summary_path=Path(cuda_summary_path),
        checkpoint_root=Path(checkpoint_root),
        r5_precommit_path=Path(r5_precommit_path),
        r5_summary_path=Path(r5_summary_path),
        frozen_boundary=frozen_boundary,
    )
    require_attested_kis_nas_d1_volatility_trend_prospective_observation_input(result)
    return result


def require_attested_kis_nas_d1_volatility_trend_prospective_observation_input(
    value: object,
) -> None:
    """Reject lineage, freshness, and source drift before a receipt is opened."""

    if not isinstance(value, KisNasD1VolatilityTrendProspectiveObservationInput):
        raise ValueError("NAS D1 prospective observation input is invalid")
    require_attested_kis_paper_daily_history_sequence_input(value.source_input)
    require_attested_kis_paper_daily_history_volatility_trend_prospective_input(
        value.prospective_input
    )
    require_attested_kis_nas_d1_volatility_trend_campaign_input(value.campaign_input)
    if (
        value.campaign_input.contract.contract_hash != value.evidence.campaign_contract_hash
        or value.source_input.panel_dataset_hash != value.evidence.panel_dataset_hash
        or value.frozen_boundary != value.source_input.validation.common_sessions[-1]
        or value.prospective_input.frozen_boundary != value.frozen_boundary
        or value.prospective_input.panel_dataset_hash != value.prospective_panel.dataset_hash
        or value.prospective_input.index_hash != value.prospective_panel.index_hash
        or value.prospective_input.source_index_path != value.prospective_panel.index_path
        or value.prospective_panel.index_path.is_symlink()
        or value.prospective_panel.source_root.is_symlink()
        or not value.prospective_panel.index_path.is_file()
        or tuple(value.prospective_panel.bars_by_symbol)
        != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        raise ValueError("NAS D1 prospective observation input is not attested")


def run_kis_nas_d1_volatility_trend_prospective_observation(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    artifact_root: Path | str = KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ARTIFACT_ROOT,
    run_label: str,
    review_status: str,
    repo_root: Path | str | None = None,
) -> KisNasD1VolatilityTrendProspectiveObservationRun:
    """Write one immutable complete or input-unavailable shadow observation."""

    require_attested_kis_nas_d1_volatility_trend_prospective_observation_input(
        observation_input
    )
    if (
        review_status
        not in KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ALLOWED_REVIEW_STATUSES
    ):
        raise ValueError("NAS D1 prospective review does not permit target opening")
    repository = _repository_root(repo_root)
    _validate_run_label(run_label)
    output_dir = _prepare_output_dir(
        artifact_root=artifact_root,
        repository=repository,
        run_label=run_label,
    )
    precommit_hash: str | None = None
    failure_stage = "frozen_lineage"
    try:
        cpu_summary, cuda_summary = _validate_frozen_external_artifacts(
            observation_input,
            repository=repository,
        )
        failure_stage = "precommit"
        precommit_payload = _precommit_payload(observation_input, review_status=review_status)
        _assert_source_safe(precommit_payload)
        precommit_path = output_dir / "precommit.json"
        precommit_hash = _write_json_new(precommit_path, precommit_payload)
        failure_stage = "freshness_reattest"
        reattested_panel = _require_unchanged_prospective_input(
            observation_input,
            repository=repository,
        )
        failure_stage = "slot_opening"
        slots_by_symbol = _prospective_slots(observation_input, panel=reattested_panel)
        if not any(slots_by_symbol.values()):
            unavailable_payload = _input_unavailable_payload(
                observation_input,
                precommit_hash=precommit_hash,
                review_status=review_status,
            )
            _assert_source_safe(unavailable_payload)
            receipt_path = output_dir / "input_unavailable.json"
            receipt_hash = _write_json_new(receipt_path, unavailable_payload)
            return KisNasD1VolatilityTrendProspectiveObservationRun(
                observation_input=observation_input,
                run_label=run_label,
                status="input_unavailable",
                precommit_path=precommit_path,
                precommit_hash=precommit_hash,
                receipt_path=receipt_path,
                receipt_hash=receipt_hash,
                candidate_results=(),
                review_status=review_status,
            )
        failure_stage = "candidate_replay"
        prediction_batches = _prediction_batches(
            observation_input,
            cpu_summary=cpu_summary,
            cuda_summary=cuda_summary,
            repository=repository,
            slots_by_symbol=slots_by_symbol,
            review_status=review_status,
        )
        candidate_results = tuple(
            _evaluate_actions(
                result_id=batch.result_id,
                model_family=batch.model_family,
                symbol=batch.symbol,
                lineage_hash=batch.lineage_hash,
                actions=tuple(
                    probability
                    >= KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_THRESHOLD
                    for probability in batch.probabilities
                ),
                slots=slots_by_symbol[batch.symbol],
                campaign_input=observation_input.campaign_input,
            )
            for batch in prediction_batches
        )
        _validate_candidate_results(candidate_results, slots_by_symbol)
        summary_payload = _summary_payload(
            observation_input,
            precommit_hash=precommit_hash,
            review_status=review_status,
            candidate_results=candidate_results,
        )
        _assert_source_safe(summary_payload)
        receipt_path = output_dir / "summary.json"
        receipt_hash = _write_json_new(receipt_path, summary_payload)
    except Exception as exc:
        failure_payload = _failure_payload(
            observation_input,
            precommit_hash=precommit_hash,
            review_status=review_status,
            failure_class=type(exc).__name__,
            stage=failure_stage,
        )
        _assert_source_safe(failure_payload)
        _write_json_new(output_dir / "failure.json", failure_payload)
        raise
    return KisNasD1VolatilityTrendProspectiveObservationRun(
        observation_input=observation_input,
        run_label=run_label,
        status="completed",
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        receipt_path=receipt_path,
        receipt_hash=receipt_hash,
        candidate_results=candidate_results,
        review_status=review_status,
    )


def _require_unchanged_prospective_input(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    repository: Path,
) -> KisPaperDailyHistoryPanel:
    """Reject a cache mutation between the source-safe precommit and target use."""

    reattested_panel = build_kis_paper_daily_history_panel(
        cache_root=observation_input.prospective_panel.source_root,
        repo_root=repository,
    )
    reattested = build_kis_paper_daily_history_volatility_trend_prospective_input(
        reattested_panel,
        frozen_boundary=observation_input.frozen_boundary,
    )
    if (
        reattested.prospective_input_hash
        != observation_input.prospective_input.prospective_input_hash
    ):
        raise ValueError("NAS D1 prospective cache changed after precommit")
    return reattested_panel


def _prospective_slots(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    panel: KisPaperDailyHistoryPanel | None = None,
) -> dict[str, tuple[KisNasD1VolatilityTrendProspectiveSlot, ...]]:
    """Open only complete, all-symbol D1 target windows after the frozen boundary."""

    panel = panel or observation_input.prospective_panel
    sessions = panel.common_sessions
    by_session = {session: index for index, session in enumerate(sessions)}
    if len(by_session) != len(sessions):
        raise ValueError("NAS D1 prospective sessions are ambiguous")
    candidate_indices = tuple(
        index
        for index, session in enumerate(sessions)
        if (
            session > observation_input.frozen_boundary
            and index >= KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS - 1
            and index + 2 < len(sessions)
            and sessions[index + 1] > observation_input.frozen_boundary
            and sessions[index + 2] > observation_input.frozen_boundary
        )
    )
    selected_indices: list[int] = []
    next_allowed = 0
    for index in candidate_indices:
        if index < next_allowed:
            continue
        selected_indices.append(index)
        next_allowed = index + KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_DECISION_STRIDE
    result: dict[str, tuple[KisNasD1VolatilityTrendProspectiveSlot, ...]] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        bars = panel.bars_by_symbol[symbol].bars
        bars_by_session = {bar.start_ts.date(): bar for bar in bars}
        if len(bars_by_session) != len(bars):
            raise ValueError("NAS D1 prospective bars are ambiguous")
        try:
            common_bars = tuple(bars_by_session[session] for session in sessions)
        except KeyError as exc:  # Defensive: panel.common_sessions is expected to prove this.
            raise ValueError("NAS D1 prospective common bars are incomplete") from exc
        slots: list[KisNasD1VolatilityTrendProspectiveSlot] = []
        for common_index in selected_indices:
            signal_bar = common_bars[common_index]
            entry_bar = common_bars[common_index + 1]
            exit_bar = common_bars[common_index + 2]
            if (
                signal_bar.start_ts.date() != sessions[common_index]
                or entry_bar.start_ts.date() != sessions[common_index + 1]
                or exit_bar.start_ts.date() != sessions[common_index + 2]
            ):
                raise ValueError("NAS D1 prospective common-session timing is invalid")
            feature_sequence = build_kis_nas_d1_volatility_trend_feature_sequence(
                common_bars,
                symbol=symbol,
                decision_index=common_index,
            )
            slots.append(
                KisNasD1VolatilityTrendProspectiveSlot(
                    symbol=symbol,
                    feature_sequence=feature_sequence,
                    signal_bar=signal_bar,
                    entry_bar=entry_bar,
                    exit_bar=exit_bar,
                    frozen_boundary=observation_input.frozen_boundary,
                )
            )
        _validate_slot_order(slots)
        result[symbol] = tuple(slots)
    counts = {len(slots) for slots in result.values()}
    if len(counts) != 1:
        raise ValueError("NAS D1 prospective symbol slot coverage is inconsistent")
    return result


def _prediction_batches(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    cpu_summary: Mapping[str, object],
    cuda_summary: Mapping[str, object],
    repository: Path,
    slots_by_symbol: Mapping[str, Sequence[KisNasD1VolatilityTrendProspectiveSlot]],
    review_status: str,
) -> tuple[_PredictionBatch, ...]:
    breadth_input = _build_runtime_breadth_input(
        observation_input,
        review_status=review_status,
    )
    return _cpu_prediction_batches(
        observation_input,
        cpu_summary=cpu_summary,
        slots_by_symbol=slots_by_symbol,
        breadth_input=breadth_input,
    ) + _cuda_prediction_batches(
        observation_input,
        cuda_summary=cuda_summary,
        repository=repository,
        slots_by_symbol=slots_by_symbol,
        breadth_input=breadth_input,
    )


def _build_runtime_breadth_input(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    review_status: str,
) -> KisNasD1VolatilityTrendBreadthInput:
    """Reconstruct model runtime only after an eligible new target exists."""

    return build_kis_nas_d1_volatility_trend_breadth_input(
        observation_input.campaign_input,
        campaign_precommit_hash=observation_input.evidence.campaign_precommit_hash,
        review_status=review_status,
    )


def _cpu_prediction_batches(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    cpu_summary: Mapping[str, object],
    slots_by_symbol: Mapping[str, Sequence[KisNasD1VolatilityTrendProspectiveSlot]],
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
) -> tuple[_PredictionBatch, ...]:
    candidates = _candidate_receipts(
        cpu_summary,
        expected_count=len(KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS),
    )
    by_symbol = {
        receipt.get("symbol"): receipt
        for receipt in candidates
        if isinstance(receipt, Mapping) and isinstance(receipt.get("symbol"), str)
    }
    if tuple(by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 prospective CPU candidate order is invalid")
    numpy = _numpy()
    result: list[_PredictionBatch] = []
    for spec in KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS:
        receipt = by_symbol[spec.symbol]
        model = fit_kis_nas_d1_volatility_trend_l2_logistic_smoke(
            breadth_input,
            spec,
        )
        standardizer = breadth_input.standardizer(spec.symbol)
        slots = slots_by_symbol[spec.symbol]
        if (
            receipt.get("model_id") != "l2_logistic"
            or receipt.get("model_parameter_hash") != model.parameter_hash
            or receipt.get("standardizer_hash") != standardizer.standardizer_hash
            or receipt.get("development_sample_count")
            != len(observation_input.campaign_input.development_samples(spec.symbol))
            or receipt.get("steps") != spec.steps
            or receipt.get("seed") != spec.seed
        ):
            raise ValueError("NAS D1 prospective CPU model lineage drifted")
        values = numpy.asarray(
            [
                standardizer.transform(
                    slot.feature_sequence,
                    sequence_length=observation_input.campaign_input.contract.features.sequence_length,
                )
                for slot in slots
            ],
            dtype=numpy.float64,
        ).reshape(len(slots), -1)
        weights = numpy.asarray(model.weights, dtype=numpy.float64)
        outputs = 1.0 / (1.0 + numpy.exp(-numpy.clip(values @ weights + model.intercept, -60, 60)))
        if (
            tuple(values.shape)
            != (
                len(slots),
                observation_input.campaign_input.contract.features.sequence_length
                * KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
            )
            or tuple(outputs.shape) != (len(slots),)
            or not numpy.isfinite(outputs).all()
            or not bool(((outputs >= 0.0) & (outputs <= 1.0)).all())
        ):
            raise ValueError("NAS D1 prospective CPU inference is invalid")
        result.append(
            _PredictionBatch(
                result_id=f"cpu_l2_logistic:{spec.symbol}",
                model_family="cpu_l2_logistic",
                symbol=spec.symbol,
                lineage_hash=model.parameter_hash,
                probabilities=tuple(float(value) for value in outputs),
            )
        )
    return tuple(result)


def _cuda_prediction_batches(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    cuda_summary: Mapping[str, object],
    repository: Path,
    slots_by_symbol: Mapping[str, Sequence[KisNasD1VolatilityTrendProspectiveSlot]],
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
) -> tuple[_PredictionBatch, ...]:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - Docker provides PyTorch.
        raise RuntimeError("NAS D1 prospective observation requires PyTorch") from exc
    candidates = _candidate_receipts(
        cuda_summary,
        expected_count=len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS),
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    result: list[_PredictionBatch] = []
    for receipt, spec in zip(
        candidates,
        KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS,
        strict=True,
    ):
        if not isinstance(receipt, Mapping):
            raise ValueError("NAS D1 prospective CUDA candidate is invalid")
        checkpoint_path = _require_external_file(
            observation_input.checkpoint_root / f"{spec.architecture_id}-{spec.symbol.lower()}.pt",
            repository,
        )
        checkpoint_hash = receipt.get("checkpoint_sha256")
        if (
            receipt.get("architecture") != spec.safe_payload()
            or receipt.get("safe_weights_only_reload") is not True
            or not _is_sha256(checkpoint_hash)
            or _sha256_file(checkpoint_path) != checkpoint_hash
        ):
            raise ValueError("NAS D1 prospective CUDA checkpoint lineage drifted")
        model = _load_cuda_checkpoint(
            checkpoint_path,
            breadth_input=breadth_input,
            spec=spec,
            torch=torch,
        )
        model.to(device)
        standardizer = breadth_input.standardizer(spec.symbol)
        slots = slots_by_symbol[spec.symbol]
        tensor = torch.tensor(
            [
                standardizer.transform(
                    slot.feature_sequence,
                    sequence_length=observation_input.campaign_input.contract.features.sequence_length,
                )
                for slot in slots
            ],
            dtype=torch.float32,
            device=device,
        )
        with torch.no_grad():
            outputs = torch.sigmoid(model(tensor))
        if (
            tuple(outputs.shape) != (len(slots), 1)
            or not bool(torch.isfinite(outputs).all().item())
            or not bool(((outputs >= 0.0) & (outputs <= 1.0)).all().item())
        ):
            raise ValueError("NAS D1 prospective CUDA inference is invalid")
        result.append(
            _PredictionBatch(
                result_id=f"cuda_{spec.architecture_id}:{spec.symbol}",
                model_family=f"cuda_{spec.architecture_id}",
                symbol=spec.symbol,
                lineage_hash=checkpoint_hash,
                probabilities=tuple(
                    float(value) for value in outputs.flatten().detach().cpu().tolist()
                ),
            )
        )
        del model, tensor, outputs
        if device.type == "cuda":
            torch.cuda.empty_cache()
    return tuple(result)


def _load_cuda_checkpoint(
    checkpoint_path: Path,
    *,
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    spec: KisNasD1VolatilityTrendArchitectureSpec,
    torch: object,
) -> object:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover - corrupt external artifact.
        raise ValueError("NAS D1 prospective checkpoint cannot be safely loaded") from exc
    standardizer = breadth_input.standardizer(spec.symbol)
    if (
        not isinstance(payload, dict)
        or payload.get("kind") != "kis_nas_d1_volatility_trend_breadth_checkpoint"
        or payload.get("campaign_contract_hash")
        != breadth_input.campaign_input.contract.contract_hash
        or payload.get("development_input_hash") != standardizer.development_input_hash
        or payload.get("standardizer_hash") != standardizer.standardizer_hash
        or payload.get("architecture") != spec.safe_payload()
    ):
        raise ValueError("NAS D1 prospective checkpoint contract is invalid")
    model = build_torch_sequence_model(
        torch=torch,
        architecture_id=spec.architecture_id,
        feature_count=KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
        hidden_size=spec.hidden_size,
        attention_heads=spec.attention_heads,
        tcn_kernel_size=spec.tcn_kernel_size,
    )
    try:
        model.load_state_dict(payload["state_dict"], strict=True)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("NAS D1 prospective checkpoint state is incompatible") from exc
    model.eval()
    return model


def _evaluate_actions(
    *,
    result_id: str,
    model_family: str,
    symbol: str,
    lineage_hash: str,
    actions: Sequence[bool],
    slots: Sequence[KisNasD1VolatilityTrendProspectiveSlot],
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
) -> KisNasD1VolatilityTrendProspectiveCandidateResult:
    if len(actions) != len(slots) or not slots:
        raise ValueError("NAS D1 prospective replay actions are invalid")
    event_store = InMemoryCampaignEventStore()
    broker = _CampaignLocalPaperBroker(
        event_store=event_store,
        emergency_store=_ClearEmergencyStore(updated_at=slots[0].signal_bar.end_ts),
        starting_cash=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_STARTING_CASH,
        fee_bps=campaign_input.contract.costs.fee_bps,
        slippage_bps=campaign_input.contract.costs.slippage_bps,
    )
    high_water = KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_STARTING_CASH
    maximum_drawdown = Decimal("0")
    for index, (action, slot) in enumerate(zip(actions, slots, strict=True)):
        equity_marks = (
            _submit_and_close_slot(
                broker=broker,
                result_id=result_id,
                slot_index=index,
                symbol=symbol,
                slot=slot,
            )
            if action
            else (broker.account().cash,)
        )
        for equity in equity_marks:
            high_water = max(high_water, equity)
            maximum_drawdown = max(maximum_drawdown, high_water - equity)
    events = event_store.iter_events()
    fills = tuple(event for event in events if event.event_type == "fill")
    account = broker.account()
    replayed = replay_local_paper_account(
        event_store,  # type: ignore[arg-type]
        starting_cash=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_STARTING_CASH,
    )
    if (
        account != replayed
        or account.quantity(market="US", symbol=symbol) != Decimal("0")
        or len(fills) != sum(actions) * 2
        or any(event.payload.get("source") != LOCAL_PAPER_SOURCE for event in fills)
    ):
        raise ValueError("NAS D1 prospective local-paper replay is invalid")
    return KisNasD1VolatilityTrendProspectiveCandidateResult(
        result_id=result_id,
        model_family=model_family,
        symbol=symbol,
        lineage_hash=lineage_hash,
        sample_count=len(slots),
        long_slot_count=sum(actions),
        fill_count=len(fills),
        after_cost_delta=(
            account.cash - KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_STARTING_CASH
        ),
        maximum_drawdown=maximum_drawdown,
        transcript_sha256=_event_transcript_hash(events),
        fill_source=LOCAL_PAPER_SOURCE,
        all_fills_local_paper=True,
        replay_reconstructed=True,
        terminal_position_zero=True,
    )


def _submit_and_close_slot(
    *,
    broker: object,
    result_id: str,
    slot_index: int,
    symbol: str,
    slot: KisNasD1VolatilityTrendProspectiveSlot,
) -> tuple[Decimal, Decimal, Decimal]:
    decision_id = f"{result_id}-slot-{slot_index:03d}"
    entry = broker.submit_and_fill_next_bar(
        OrderIntent(
            client_order_id=f"{decision_id}-entry",
            symbol=symbol,
            market="US",
            side="buy",
            quantity=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_QUANTITY,
            limit_price=None,
            decision_id=decision_id,
            created_at=slot.signal_bar.end_ts,
        ),
        signal_bar=slot.signal_bar,
        execution_bar=slot.entry_bar,
    )
    exit_fill = broker.submit_and_fill_next_bar(
        OrderIntent(
            client_order_id=f"{decision_id}-exit",
            symbol=symbol,
            market="US",
            side="sell",
            quantity=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_QUANTITY,
            limit_price=None,
            decision_id=decision_id,
            created_at=slot.entry_bar.end_ts,
        ),
        signal_bar=slot.entry_bar,
        execution_bar=slot.exit_bar,
    )
    entry_account = entry.account
    exit_account = exit_fill.account
    if (
        entry.fill is None
        or exit_fill.fill is None
        or entry.fill.source != LOCAL_PAPER_SOURCE
        or exit_fill.fill.source != LOCAL_PAPER_SOURCE
        or exit_account.quantity(market="US", symbol=symbol) != Decimal("0")
    ):
        raise ValueError("NAS D1 prospective local-paper fill is invalid")
    entry_quantity = entry_account.quantity(market="US", symbol=symbol)
    return (
        entry_account.cash + entry.fill.price * entry_quantity,
        entry_account.cash + slot.entry_bar.low * entry_quantity,
        exit_account.cash,
    )


def _validate_frozen_external_artifacts(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    repository: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    """Reattest r2 candidate lineage and r5 boundary evidence without outcomes."""

    r5_precommit = _require_external_file(observation_input.r5_precommit_path, repository)
    r5_summary = _require_external_file(observation_input.r5_summary_path, repository)
    cpu_summary_path = _require_external_file(observation_input.cpu_summary_path, repository)
    cuda_summary_path = _require_external_file(observation_input.cuda_summary_path, repository)
    checkpoint_root = _require_external_directory(observation_input.checkpoint_root, repository)
    if (
        _sha256_file(r5_precommit) != observation_input.evidence.r5_precommit_hash
        or _sha256_file(r5_summary) != observation_input.evidence.r5_summary_hash
        or _sha256_file(cpu_summary_path) != observation_input.evidence.cpu_summary_hash
        or _sha256_file(cuda_summary_path) != observation_input.evidence.cuda_summary_hash
    ):
        raise ValueError("NAS D1 prospective frozen artifact hash drifted")
    r5_precommit_payload = _load_json_object(r5_precommit, "r5 precommit")
    r5_summary_payload = _load_json_object(r5_summary, "r5 summary")
    _validate_r5_receipts(observation_input, r5_precommit_payload, r5_summary_payload)
    cpu_summary = _load_json_object(cpu_summary_path, "CPU summary")
    cuda_summary = _load_json_object(cuda_summary_path, "CUDA summary")
    _validate_r2_summaries(observation_input, cpu_summary, cuda_summary, checkpoint_root)
    return cpu_summary, cuda_summary


def _validate_r5_receipts(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    precommit: Mapping[str, object],
    summary: Mapping[str, object],
) -> None:
    evidence = _mapping(precommit.get("evidence"), "r5 evidence")
    source = _mapping(summary.get("source"), "r5 source")
    reporting = _mapping(summary.get("reporting"), "r5 reporting")
    if (
        precommit.get("kind") != "kis_nas_d1_volatility_trend_sealed_evaluation_precommit"
        or precommit.get("evaluation_id") != "kis-nas-d1-volatility-trend-sealed-evaluation-v1"
        or summary.get("kind") != "kis_nas_d1_volatility_trend_sealed_evaluation"
        or summary.get("status") != "completed"
        or summary.get("precommit_hash") != observation_input.evidence.r5_precommit_hash
        or evidence
        != {
            "panel_dataset_hash": observation_input.evidence.panel_dataset_hash,
            "campaign_contract_hash": observation_input.evidence.campaign_contract_hash,
            "campaign_precommit_hash": observation_input.evidence.campaign_precommit_hash,
            "cpu_summary_hash": observation_input.evidence.cpu_summary_hash,
            "cuda_summary_hash": observation_input.evidence.cuda_summary_hash,
        }
        or source.get("panel_dataset_hash") != observation_input.evidence.panel_dataset_hash
        or source.get("campaign_contract_hash") != observation_input.evidence.campaign_contract_hash
        or source.get("campaign_precommit_hash")
        != observation_input.evidence.campaign_precommit_hash
        or not isinstance(summary.get("candidates"), list)
        or len(summary["candidates"]) != 24
        or any(reporting.get(name) is not False for name in reporting)
    ):
        raise ValueError("NAS D1 prospective r5 receipt is not an immutable boundary")


def _validate_r2_summaries(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    cpu_summary: Mapping[str, object],
    cuda_summary: Mapping[str, object],
    checkpoint_root: Path,
) -> None:
    _validate_summary_source(
        observation_input,
        cpu_summary,
        kind="kis_nas_d1_volatility_trend_cpu_smoke",
    )
    _validate_summary_source(
        observation_input,
        cuda_summary,
        kind="kis_nas_d1_volatility_trend_cuda_breadth",
    )
    cpu_candidates = _candidate_receipts(
        cpu_summary,
        expected_count=len(KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS),
    )
    cuda_candidates = _candidate_receipts(
        cuda_summary,
        expected_count=len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS),
    )
    for receipt, spec in zip(
        cpu_candidates,
        KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS,
        strict=True,
    ):
        if (
            not isinstance(receipt, Mapping)
            or receipt.get("symbol") != spec.symbol
            or receipt.get("model_id") != "l2_logistic"
            or receipt.get("steps") != spec.steps
            or receipt.get("seed") != spec.seed
            or not _is_sha256(receipt.get("model_parameter_hash"))
            or not _is_sha256(receipt.get("standardizer_hash"))
        ):
            raise ValueError("NAS D1 prospective CPU receipt is invalid")
    for receipt, spec in zip(
        cuda_candidates,
        KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS,
        strict=True,
    ):
        if (
            not isinstance(receipt, Mapping)
            or receipt.get("architecture") != spec.safe_payload()
            or receipt.get("safe_weights_only_reload") is not True
            or not _is_sha256(receipt.get("checkpoint_sha256"))
        ):
            raise ValueError("NAS D1 prospective CUDA receipt is invalid")
        checkpoint = checkpoint_root / f"{spec.architecture_id}-{spec.symbol.lower()}.pt"
        if not checkpoint.is_file() or _sha256_file(checkpoint) != receipt.get("checkpoint_sha256"):
            raise ValueError("NAS D1 prospective CUDA checkpoint is invalid")


def _validate_summary_source(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    payload: Mapping[str, object],
    *,
    kind: str,
) -> None:
    source = _mapping(payload.get("source"), "r2 source")
    if (
        payload.get("kind") != kind
        or payload.get("status") != "completed"
        or payload.get("campaign_contract_hash")
        != observation_input.evidence.campaign_contract_hash
        or payload.get("campaign_precommit_hash")
        != observation_input.evidence.campaign_precommit_hash
        or source.get("campaign_contract_hash") != observation_input.evidence.campaign_contract_hash
        or source.get("campaign_precommit_hash")
        != observation_input.evidence.campaign_precommit_hash
    ):
        raise ValueError("NAS D1 prospective r2 source lineage is invalid")


def _candidate_receipts(payload: Mapping[str, object], *, expected_count: int) -> list[object]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != expected_count:
        raise ValueError("NAS D1 prospective candidate receipt count is invalid")
    return candidates


def _validate_candidate_results(
    results: Sequence[KisNasD1VolatilityTrendProspectiveCandidateResult],
    slots_by_symbol: Mapping[str, Sequence[KisNasD1VolatilityTrendProspectiveSlot]],
) -> None:
    expected_count = len(KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS) + len(
        KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS
    )
    if len(results) != expected_count:
        raise ValueError("NAS D1 prospective candidate population is incomplete")
    expected_ids = tuple(
        [
            f"cpu_l2_logistic:{spec.symbol}"
            for spec in KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS
        ]
        + [
            f"cuda_{spec.architecture_id}:{spec.symbol}"
            for spec in KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS
        ]
    )
    if tuple(result.result_id for result in results) != expected_ids:
        raise ValueError("NAS D1 prospective candidate identity drifted")
    if any(result.sample_count != len(slots_by_symbol[result.symbol]) for result in results):
        raise ValueError("NAS D1 prospective candidate slot count drifted")


def _validate_slot_order(slots: Sequence[KisNasD1VolatilityTrendProspectiveSlot]) -> None:
    for prior, current in zip(slots, slots[1:], strict=False):
        if current.signal_bar.end_ts < prior.exit_bar.end_ts:
            raise ValueError("NAS D1 prospective target windows overlap")


def _precommit_payload(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    review_status: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_prospective_observation_precommit",
        "observation_id": KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ID,
        "review_status": review_status,
        "frozen": _frozen_payload(observation_input),
        "prospective_input": observation_input.prospective_input.safe_payload(),
        "decision": {
            "context_completed_d1_bars": KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS,
            "decision_after_boundary_only": True,
            "entry_exit": "t_plus_1_open_to_t_plus_2_open",
            "decision_stride_sessions": (
                KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_DECISION_STRIDE
            ),
            "quantity": "1",
            "long_rule": "probability_greater_than_or_equal_to_threshold",
            "threshold": str(KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_THRESHOLD),
            "local_paper_costs_frozen": True,
        },
        "candidate_population": {
            "cpu_count": len(KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS),
            "cuda_count": len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS),
            "total_count": (
                len(KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS)
                + len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS)
            ),
            "r5_outcomes_consumed": False,
        },
        "artifact_policy": _artifact_policy(),
        "reporting": _reporting_payload(),
    }


def _summary_payload(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    precommit_hash: str,
    review_status: str,
    candidate_results: Sequence[KisNasD1VolatilityTrendProspectiveCandidateResult],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_prospective_observation",
        "status": "completed",
        "precommit_hash": precommit_hash,
        "review_status": review_status,
        "frozen": _frozen_payload(observation_input),
        "prospective_input": observation_input.prospective_input.safe_payload(),
        "observation": {
            "candidate_count": len(candidate_results),
            "per_symbol_slot_count": candidate_results[0].sample_count,
            "all_replays_local_paper": True,
            "all_replays_terminal_flat": True,
            "r5_outcomes_consumed": False,
        },
        "candidates": [result.safe_payload() for result in candidate_results],
        "artifact_policy": _artifact_policy(),
        "reporting": _reporting_payload(),
    }


def _input_unavailable_payload(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    precommit_hash: str,
    review_status: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_prospective_observation",
        "status": "input_unavailable",
        "reason": "no_complete_all_symbol_post_boundary_t_plus_2_window",
        "precommit_hash": precommit_hash,
        "review_status": review_status,
        "frozen": _frozen_payload(observation_input),
        "prospective_input": observation_input.prospective_input.safe_payload(),
        "artifact_policy": _artifact_policy(),
        "reporting": _reporting_payload(),
    }


def _failure_payload(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
    *,
    precommit_hash: str | None,
    review_status: str,
    failure_class: str,
    stage: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_prospective_observation_failure",
        "status": "failed",
        "stage": stage,
        "failure_class": failure_class,
        "precommit_hash": precommit_hash,
        "review_status": review_status,
        "frozen": _frozen_payload(observation_input),
        "prospective_input": observation_input.prospective_input.safe_payload(),
        "artifact_policy": _artifact_policy(),
        "reporting": _reporting_payload(),
    }


def _frozen_payload(
    observation_input: KisNasD1VolatilityTrendProspectiveObservationInput,
) -> dict[str, object]:
    return {
        "panel_dataset_hash": observation_input.evidence.panel_dataset_hash,
        "campaign_contract_hash": observation_input.evidence.campaign_contract_hash,
        "campaign_precommit_hash": observation_input.evidence.campaign_precommit_hash,
        "cpu_summary_hash": observation_input.evidence.cpu_summary_hash,
        "cuda_summary_hash": observation_input.evidence.cuda_summary_hash,
        "r5_precommit_hash": observation_input.evidence.r5_precommit_hash,
        "r5_summary_hash": observation_input.evidence.r5_summary_hash,
        "r5_terminal_session": observation_input.frozen_boundary.isoformat(),
        "r5_outcomes_consumed": False,
    }


def _artifact_policy() -> dict[str, object]:
    return {
        "external_artifact_only": True,
        "raw_rows_persisted": False,
        "target_values_persisted": False,
        "prediction_values_persisted": False,
        "event_rows_persisted": False,
        "checkpoint_copies_persisted": False,
    }


def _reporting_payload() -> dict[str, object]:
    return {
        "candidate_ranking_allowed": False,
        "selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "paper_trading_eligible": False,
    }


def _prepare_output_dir(*, artifact_root: Path | str, repository: Path, run_label: str) -> Path:
    _validate_run_label(run_label)
    root = Path(artifact_root).absolute()
    _reject_link_or_junction_components(root)
    root = root.resolve()
    _reject_repository_artifact_path(root, repository)
    _reject_repository_artifact_path(root, _MODULE_REPOSITORY_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    _reject_link_or_junction_components(root)
    output = root / KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_ID / run_label
    _reject_link_or_junction_components(output)
    _reject_repository_artifact_path(output.resolve(), repository)
    _reject_repository_artifact_path(output.resolve(), _MODULE_REPOSITORY_ROOT)
    output.mkdir(parents=True, exist_ok=False)
    _reject_link_or_junction_components(output)
    return output


def _require_external_file(path: Path | str, repository: Path) -> Path:
    candidate = Path(path)
    _reject_link_or_junction_components(candidate)
    if not candidate.is_file():
        raise ValueError("NAS D1 prospective external receipt is invalid")
    resolved = candidate.resolve()
    _reject_repository_artifact_path(resolved, repository)
    _reject_repository_artifact_path(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _require_external_directory(path: Path | str, repository: Path) -> Path:
    candidate = Path(path)
    _reject_link_or_junction_components(candidate)
    if not candidate.is_dir():
        raise ValueError("NAS D1 prospective external checkpoint root is invalid")
    resolved = candidate.resolve()
    _reject_repository_artifact_path(resolved, repository)
    _reject_repository_artifact_path(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _reject_repository_artifact_path(path: Path, repository: Path) -> None:
    if not path.is_relative_to(repository):
        return
    if (
        repository == _DOCKER_REPOSITORY_ROOT.resolve()
        and _DOCKER_ARTIFACT_ROOT.is_mount()
        and path.is_relative_to(_DOCKER_ARTIFACT_ROOT.resolve())
    ):
        return
    raise ValueError("NAS D1 prospective artifacts must stay outside the Git workspace")


def _reject_link_or_junction_components(path: Path) -> None:
    candidate = path.absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts:
        if part == candidate.anchor:
            continue
        current /= part
        is_junction = getattr(current, "is_junction", None)
        if current.is_symlink() or (callable(is_junction) and is_junction()):
            raise ValueError("NAS D1 prospective artifact path cannot contain a link")


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    _reject_link_or_junction_components(path.parent)
    if path.exists():
        raise FileExistsError("NAS D1 prospective receipt is immutable")
    with path.open("x", encoding="ascii") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return _sha256_file(path)


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"NAS D1 prospective {label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"NAS D1 prospective {label} is invalid")
    return payload


def _event_transcript_hash(events: Sequence[Event]) -> str:
    return _sha256_payload({"events": [event.to_record() for event in events]})


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"NAS D1 prospective {name} is invalid")
    return value


def _repository_root(value: Path | str | None) -> Path:
    return Path(value or Path.cwd()).resolve()


def _validate_run_label(value: str) -> None:
    if not isinstance(value, str) or _RUN_LABEL.fullmatch(value) is None:
        raise ValueError("NAS D1 prospective run label is invalid")


def _numpy() -> object:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - project runtime provides NumPy.
        raise RuntimeError("NAS D1 prospective observation requires NumPy") from exc
    return numpy


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_payload(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _assert_source_safe(value: object) -> None:
    forbidden = {
        "account",
        "bar",
        "bars",
        "close",
        "credential",
        "entry",
        "event",
        "exit",
        "feature_sequence",
        "high",
        "label",
        "labels",
        "low",
        "open",
        "order",
        "orders",
        "prediction",
        "predictions",
        "price",
        "prices",
        "probability",
        "probabilities",
        "raw_bars",
        "secret",
        "target",
        "targets",
        "volume",
        "weights",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in forbidden:
                raise ValueError("NAS D1 prospective receipt contains a source value field")
            _assert_source_safe(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _assert_source_safe(nested)


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        return False
    return True


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_OBSERVATION_EVIDENCE = (
    KisNasD1VolatilityTrendProspectiveEvidence(
        panel_dataset_hash=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_PANEL_HASH,
        campaign_contract_hash=(
            KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_CAMPAIGN_CONTRACT_HASH
        ),
        campaign_precommit_hash=(
            KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_CAMPAIGN_PRECOMMIT_HASH
        ),
        cpu_summary_hash=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_CPU_SUMMARY_HASH,
        cuda_summary_hash=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_CUDA_SUMMARY_HASH,
        r5_precommit_hash=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_R5_PRECOMMIT_HASH,
        r5_summary_hash=KIS_NAS_D1_VOLATILITY_TREND_PROSPECTIVE_EXPECTED_R5_SUMMARY_HASH,
    )
)
