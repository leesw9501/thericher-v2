"""Pinned, offline local-paper falsification for NAS volatility/trend candidates.

This module opens validation targets only after it has reattested the frozen
source panel and candidate artifacts. It deliberately has no provider,
credential, KIS, or live-broker surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, EmergencyState, OrderIntent
from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KisPaperDailyHistorySequenceInput,
    require_attested_kis_paper_daily_history_sequence_input,
)
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE, replay_local_paper_account
from thericher_v2.research.kis_nas_d1_volatility_trend_breadth import (
    KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS,
    KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS,
    KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
    KisNasD1VolatilityTrendArchitectureSpec,
    KisNasD1VolatilityTrendBreadthInput,
    _require_attested_breadth_input,
    build_kis_nas_d1_volatility_trend_breadth_input,
    fit_kis_nas_d1_volatility_trend_l2_logistic_smoke,
)
from thericher_v2.research.kis_nas_d1_volatility_trend_campaign import (
    KIS_NAS_D1_VOLATILITY_TREND_COMPARATORS,
    KisNasD1VolatilityTrendCampaignInput,
    KisNasD1VolatilityTrendValidationSample,
    build_kis_nas_d1_volatility_trend_campaign,
    calculate_kis_nas_d1_volatility_trend_campaign_precommit_hash,
    require_attested_kis_nas_d1_volatility_trend_campaign_input,
    resolve_kis_nas_d1_volatility_trend_reference_long_from_attested_input,
)
from thericher_v2.research.sequence_architecture_models import build_torch_sequence_model
from thericher_v2.research.validation import InMemoryCampaignEventStore, _CampaignLocalPaperBroker
from thericher_v2.state import Event

KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ID = (
    "kis-nas-d1-volatility-trend-sealed-evaluation-v1"
)
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/research"
)
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_PANEL_HASH = (
    "sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e"
)
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CAMPAIGN_PRECOMMIT_HASH = (
    "sha256:9f71107718c3235c1a52a092f3362b114e16f33387d7afaafc4b9d390e57deb9"
)
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CAMPAIGN_CONTRACT_HASH = (
    "sha256:85fcaabf2d96fceaea03a8d5504ea730eb88a5adda95d692b250614da840ac0b"
)
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CPU_SUMMARY_HASH = (
    "sha256:65ba9f682bb6477bd7fdfa5d61761fb7ab67f3db23601187a92f88415bad69a8"
)
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CUDA_SUMMARY_HASH = (
    "sha256:3158ac0e69c002394d97dc5f52946d70637e082f292a7c549498f4c045e5bc2c"
)
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_THRESHOLD = 0.5
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_STARTING_CASH = Decimal("10000")
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_QUANTITY = Decimal("1")
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ALLOWED_REVIEW_STATUSES = frozenset(
    {"review_unavailable"}
)
KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_SLOT_COUNT = 308

_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendSealedEvaluationEvidence:
    """Artifact identities that must match before target reconstruction."""

    panel_dataset_hash: str
    campaign_contract_hash: str
    campaign_precommit_hash: str
    cpu_summary_hash: str
    cuda_summary_hash: str

    def __post_init__(self) -> None:
        if any(
            not _is_sha256(value)
            for value in (
                self.panel_dataset_hash,
                self.campaign_contract_hash,
                self.campaign_precommit_hash,
                self.cpu_summary_hash,
                self.cuda_summary_hash,
            )
        ):
            raise ValueError("NAS D1 volatility trend sealed evidence is invalid")


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendSealedEvaluationInput:
    """Reattested source and external frozen candidate-artifact paths."""

    source_input: KisPaperDailyHistorySequenceInput
    campaign_input: KisNasD1VolatilityTrendCampaignInput
    breadth_input: KisNasD1VolatilityTrendBreadthInput
    evidence: KisNasD1VolatilityTrendSealedEvaluationEvidence
    cpu_summary_path: Path
    cuda_summary_path: Path
    checkpoint_root: Path


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendEvaluationSlot:
    """One in-memory signal, entry, and exit triplet for a non-overlapping slot."""

    sample: KisNasD1VolatilityTrendValidationSample
    signal_bar: Bar
    entry_bar: Bar
    exit_bar: Bar

    def __post_init__(self) -> None:
        if (
            self.sample.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.signal_bar.symbol != self.sample.symbol
            or self.entry_bar.symbol != self.sample.symbol
            or self.exit_bar.symbol != self.sample.symbol
            or self.signal_bar.start_ts != self.sample.decision_start
            or self.signal_bar.end_ts != self.sample.decision_end
            or not (self.signal_bar.end_ts < self.entry_bar.end_ts < self.exit_bar.end_ts)
        ):
            raise ValueError("NAS D1 volatility trend evaluation slot is invalid")


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendEvaluationResult:
    """Source-safe aggregate result for one independently frozen candidate."""

    result_id: str
    result_kind: Literal["candidate", "comparator"]
    model_family: str
    symbol: str
    lineage_hash: str | None
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
            or self.result_kind not in {"candidate", "comparator"}
            or self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or (self.lineage_hash is not None and not _is_sha256(self.lineage_hash))
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
            raise ValueError("NAS D1 volatility trend evaluation result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "result_id": self.result_id,
            "result_kind": self.result_kind,
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
class KisNasD1VolatilityTrendKillRuleResult:
    """A categorical independent comparison, never a selection rank."""

    candidate_result_id: str
    comparator_result_id: str
    candidate_symbol: str
    kill_rule_met: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not self.candidate_result_id
            or not self.comparator_result_id
            or self.candidate_symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 volatility trend kill-rule result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "candidate_result_id": self.candidate_result_id,
            "comparator_result_id": self.comparator_result_id,
            "symbol": self.candidate_symbol,
            "kill_rule": (
                "strictly_improves_paired_after_cost_return_without_worse_maximum_drawdown"
            ),
            "kill_rule_met": self.kill_rule_met,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendSealedEvaluationRun:
    """External immutable evidence for one bounded sealed evaluation."""

    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput
    run_label: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    summary_hash: str
    candidate_results: tuple[KisNasD1VolatilityTrendEvaluationResult, ...]
    comparator_results: tuple[KisNasD1VolatilityTrendEvaluationResult, ...]
    kill_rule_results: tuple[KisNasD1VolatilityTrendKillRuleResult, ...]
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
            reason="sealed_nas_d1_volatility_trend_offline_evaluation",
            updated_at=self.updated_at,
        )


def build_kis_nas_d1_volatility_trend_sealed_evaluation_input(
    source_input: KisPaperDailyHistorySequenceInput,
    *,
    evidence: KisNasD1VolatilityTrendSealedEvaluationEvidence,
    cpu_summary_path: Path | str,
    cuda_summary_path: Path | str,
    checkpoint_root: Path | str,
    review_status: str,
) -> KisNasD1VolatilityTrendSealedEvaluationInput:
    """Reattest every non-target dependency before any sealed evaluation run."""

    if review_status not in KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ALLOWED_REVIEW_STATUSES:
        raise ValueError("NAS D1 volatility trend sealed review does not permit target opening")
    require_attested_kis_paper_daily_history_sequence_input(source_input)
    campaign_input = build_kis_nas_d1_volatility_trend_campaign(source_input)
    expected_precommit_hash = calculate_kis_nas_d1_volatility_trend_campaign_precommit_hash(
        campaign_input,
        review_status=review_status,
    )
    if (
        source_input.panel_dataset_hash != evidence.panel_dataset_hash
        or campaign_input.contract.contract_hash != evidence.campaign_contract_hash
        or expected_precommit_hash != evidence.campaign_precommit_hash
    ):
        raise ValueError("NAS D1 volatility trend sealed source evidence is not pinned")
    breadth_input = build_kis_nas_d1_volatility_trend_breadth_input(
        campaign_input,
        campaign_precommit_hash=evidence.campaign_precommit_hash,
        review_status=review_status,
    )
    result = KisNasD1VolatilityTrendSealedEvaluationInput(
        source_input=source_input,
        campaign_input=campaign_input,
        breadth_input=breadth_input,
        evidence=evidence,
        cpu_summary_path=Path(cpu_summary_path),
        cuda_summary_path=Path(cuda_summary_path),
        checkpoint_root=Path(checkpoint_root),
    )
    require_attested_kis_nas_d1_volatility_trend_sealed_evaluation_input(result)
    return result


def require_attested_kis_nas_d1_volatility_trend_sealed_evaluation_input(
    value: object,
) -> None:
    """Reject drift before any validation labels, predictions, or replay exist."""

    if not isinstance(value, KisNasD1VolatilityTrendSealedEvaluationInput):
        raise ValueError("NAS D1 volatility trend sealed input is invalid")
    require_attested_kis_paper_daily_history_sequence_input(value.source_input)
    require_attested_kis_nas_d1_volatility_trend_campaign_input(value.campaign_input)
    _require_attested_breadth_input(value.breadth_input)
    if (
        value.breadth_input.campaign_input is not value.campaign_input
        or value.source_input.panel_dataset_hash != value.evidence.panel_dataset_hash
        or value.campaign_input.contract.contract_hash != value.evidence.campaign_contract_hash
        or value.breadth_input.campaign_precommit_hash != value.evidence.campaign_precommit_hash
        or tuple(value.campaign_input.validation_samples_by_symbol)
        != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or tuple(value.source_input.validation.bars_by_symbol)
        != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        raise ValueError("NAS D1 volatility trend sealed input is not attested")


def run_kis_nas_d1_volatility_trend_sealed_evaluation(
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
    *,
    artifact_root: Path | str = KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ARTIFACT_ROOT,
    run_label: str,
    review_status: str,
    repo_root: Path | str | None = None,
) -> KisNasD1VolatilityTrendSealedEvaluationRun:
    """Open the sealed target only after the immutable precommit exists."""

    require_attested_kis_nas_d1_volatility_trend_sealed_evaluation_input(evaluation_input)
    if review_status not in KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ALLOWED_REVIEW_STATUSES:
        raise ValueError("NAS D1 volatility trend sealed review does not permit target opening")
    repository = _repository_root(repo_root)
    _validate_run_label(run_label)
    output_dir = _prepare_output_dir(
        artifact_root=artifact_root,
        repository=repository,
        run_label=run_label,
    )
    precommit_hash: str | None = None
    failure_stage = "candidate_evidence"
    try:
        _validate_external_candidate_evidence(evaluation_input, repository=repository)
        failure_stage = "precommit"
        precommit_payload = _precommit_payload(evaluation_input, review_status=review_status)
        _assert_source_safe(precommit_payload)
        precommit_path = output_dir / "precommit.json"
        precommit_hash = _write_json_new(precommit_path, precommit_payload)
        failure_stage = "evaluation"
        prediction_batches = _prediction_batches(evaluation_input, repository=repository)
        slots_by_symbol = _validation_slots(evaluation_input)
        candidate_results = tuple(
            _evaluate_actions(
                result_id=batch.result_id,
                result_kind="candidate",
                model_family=batch.model_family,
                symbol=batch.symbol,
                lineage_hash=batch.lineage_hash,
                actions=tuple(
                    probability >= KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_THRESHOLD
                    for probability in batch.probabilities
                ),
                slots=slots_by_symbol[batch.symbol],
                campaign_input=evaluation_input.campaign_input,
            )
            for batch in prediction_batches
        )
        comparator_results = tuple(
            _evaluate_comparator(
                comparator_id=comparator_id,
                symbol=symbol,
                slots=slots_by_symbol[symbol],
                campaign_input=evaluation_input.campaign_input,
            )
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            for comparator_id in KIS_NAS_D1_VOLATILITY_TREND_COMPARATORS
        )
        _validate_result_sets(candidate_results, comparator_results)
        kill_rule_results = _kill_rule_results(candidate_results, comparator_results)
        summary_payload = _summary_payload(
            evaluation_input=evaluation_input,
            precommit_hash=precommit_hash,
            review_status=review_status,
            candidate_results=candidate_results,
            comparator_results=comparator_results,
            kill_rule_results=kill_rule_results,
        )
        _assert_source_safe(summary_payload)
        summary_path = output_dir / "summary.json"
        summary_hash = _write_json_new(summary_path, summary_payload)
    except Exception as exc:
        failure_payload = _failure_payload(
            evaluation_input=evaluation_input,
            precommit_hash=precommit_hash,
            review_status=review_status,
            failure_class=type(exc).__name__,
            stage=failure_stage,
        )
        _assert_source_safe(failure_payload)
        _write_json_new(output_dir / "failure.json", failure_payload)
        raise
    return KisNasD1VolatilityTrendSealedEvaluationRun(
        evaluation_input=evaluation_input,
        run_label=run_label,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        summary_hash=summary_hash,
        candidate_results=candidate_results,
        comparator_results=comparator_results,
        kill_rule_results=kill_rule_results,
        review_status=review_status,
    )


def _validation_slots(
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
) -> dict[str, tuple[KisNasD1VolatilityTrendEvaluationSlot, ...]]:
    result: dict[str, tuple[KisNasD1VolatilityTrendEvaluationSlot, ...]] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        bars = evaluation_input.source_input.validation.stream(symbol).bars
        index_by_start = {bar.start_ts: index for index, bar in enumerate(bars)}
        if len(index_by_start) != len(bars):
            raise ValueError("NAS D1 volatility trend validation bars are ambiguous")
        slots: list[KisNasD1VolatilityTrendEvaluationSlot] = []
        for sample in evaluation_input.campaign_input.validation_samples(symbol):
            index = index_by_start.get(sample.decision_start)
            if index is None or index + 2 >= len(bars):
                raise ValueError("NAS D1 volatility trend validation slot is out of range")
            slots.append(
                KisNasD1VolatilityTrendEvaluationSlot(
                    sample=sample,
                    signal_bar=bars[index],
                    entry_bar=bars[index + 1],
                    exit_bar=bars[index + 2],
                )
            )
        _validate_slot_order(slots)
        result[symbol] = tuple(slots)
    return result


def _prediction_batches(
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
    *,
    repository: Path,
) -> tuple[_PredictionBatch, ...]:
    cpu_batches = _cpu_prediction_batches(
        evaluation_input,
        cpu_summary=_load_json_object(evaluation_input.cpu_summary_path, "CPU summary"),
    )
    cuda_batches = _cuda_prediction_batches(evaluation_input, repository=repository)
    return cpu_batches + cuda_batches


def _cpu_prediction_batches(
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
    *,
    cpu_summary: Mapping[str, object],
) -> tuple[_PredictionBatch, ...]:
    candidates = cpu_summary.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("NAS D1 volatility trend sealed CPU summary candidates are invalid")
    by_symbol = {
        receipt.get("symbol"): receipt
        for receipt in candidates
        if isinstance(receipt, Mapping) and isinstance(receipt.get("symbol"), str)
    }
    if tuple(by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 volatility trend sealed CPU summary symbol order is invalid")
    return tuple(
        _cpu_prediction_batch(
            evaluation_input.breadth_input,
            spec.symbol,
            receipt=by_symbol[spec.symbol],
        )
        for spec in KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS
    )


def _cpu_prediction_batch(
    breadth_input: KisNasD1VolatilityTrendBreadthInput,
    symbol: str,
    *,
    receipt: Mapping[str, object],
) -> _PredictionBatch:
    spec = next(
        spec
        for spec in KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS
        if spec.symbol == symbol
    )
    model = fit_kis_nas_d1_volatility_trend_l2_logistic_smoke(breadth_input, spec)
    standardizer = breadth_input.standardizer(symbol)
    samples = breadth_input.campaign_input.validation_samples(symbol)
    if (
        receipt.get("model_id") != "l2_logistic"
        or receipt.get("model_parameter_hash") != model.parameter_hash
        or receipt.get("standardizer_hash") != standardizer.standardizer_hash
        or receipt.get("development_sample_count")
        != len(breadth_input.campaign_input.development_samples(symbol))
        or receipt.get("steps") != spec.steps
        or receipt.get("seed") != spec.seed
    ):
        raise ValueError("NAS D1 volatility trend sealed CPU model lineage drifted")
    numpy = _numpy()
    values = numpy.asarray(
        [
            standardizer.transform(
                sample.feature_sequence,
                sequence_length=breadth_input.campaign_input.contract.features.sequence_length,
            )
            for sample in samples
        ],
        dtype=numpy.float64,
    ).reshape(len(samples), -1)
    weights = numpy.asarray(model.weights, dtype=numpy.float64)
    outputs = 1.0 / (1.0 + numpy.exp(-numpy.clip(values @ weights + model.intercept, -60, 60)))
    if (
        tuple(values.shape)
        != (
            len(samples),
            breadth_input.campaign_input.contract.features.sequence_length
            * KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT,
        )
        or tuple(outputs.shape) != (len(samples),)
        or not numpy.isfinite(outputs).all()
        or not bool(((outputs >= 0.0) & (outputs <= 1.0)).all())
    ):
        raise ValueError("NAS D1 volatility trend sealed CPU inference is invalid")
    return _PredictionBatch(
        result_id=f"cpu_l2_logistic:{symbol}",
        model_family="cpu_l2_logistic",
        symbol=symbol,
        lineage_hash=model.parameter_hash,
        probabilities=tuple(float(value) for value in outputs),
    )


def _cuda_prediction_batches(
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
    *,
    repository: Path,
) -> tuple[_PredictionBatch, ...]:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - Docker supplies PyTorch.
        raise RuntimeError("NAS D1 volatility trend sealed evaluation requires PyTorch") from exc
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    summary = _load_json_object(evaluation_input.cuda_summary_path, "CUDA summary")
    candidates = summary.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("NAS D1 volatility trend CUDA summary candidates are invalid")
    result: list[_PredictionBatch] = []
    for receipt, spec in zip(
        candidates,
        KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS,
        strict=True,
    ):
        if not isinstance(receipt, Mapping):
            raise ValueError("NAS D1 volatility trend CUDA receipt is invalid")
        checkpoint_path = _require_external_file(
            evaluation_input.checkpoint_root / f"{spec.architecture_id}-{spec.symbol.lower()}.pt",
            repository,
        )
        checkpoint_hash = receipt.get("checkpoint_sha256")
        if not _is_sha256(checkpoint_hash) or _sha256_file(checkpoint_path) != checkpoint_hash:
            raise ValueError("NAS D1 volatility trend CUDA checkpoint hash drifted")
        model = _load_cuda_checkpoint(
            checkpoint_path,
            breadth_input=evaluation_input.breadth_input,
            spec=spec,
            torch=torch,
        )
        model.to(device)
        samples = evaluation_input.campaign_input.validation_samples(spec.symbol)
        standardizer = evaluation_input.breadth_input.standardizer(spec.symbol)
        tensor = torch.tensor(
            [
                standardizer.transform(
                    sample.feature_sequence,
                    sequence_length=evaluation_input.campaign_input.contract.features.sequence_length,
                )
                for sample in samples
            ],
            dtype=torch.float32,
            device=device,
        )
        with torch.no_grad():
            outputs = torch.sigmoid(model(tensor))
        if (
            tuple(outputs.shape) != (len(samples), 1)
            or not bool(torch.isfinite(outputs).all().item())
            or not bool(((outputs >= 0.0) & (outputs <= 1.0)).all().item())
        ):
            raise ValueError("NAS D1 volatility trend sealed CUDA inference is invalid")
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
        raise ValueError("NAS D1 volatility trend checkpoint cannot be safely loaded") from exc
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
        raise ValueError("NAS D1 volatility trend checkpoint contract is invalid")
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
        raise ValueError("NAS D1 volatility trend checkpoint state is incompatible") from exc
    model.eval()
    return model


def _evaluate_comparator(
    *,
    comparator_id: str,
    symbol: str,
    slots: Sequence[KisNasD1VolatilityTrendEvaluationSlot],
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
) -> KisNasD1VolatilityTrendEvaluationResult:
    require_attested_kis_nas_d1_volatility_trend_campaign_input(campaign_input)
    actions = tuple(
        resolve_kis_nas_d1_volatility_trend_reference_long_from_attested_input(
            campaign_input,
            slot.sample,
            comparator_id=comparator_id,
        )
        for slot in slots
    )
    return _evaluate_actions(
        result_id=f"comparator_{comparator_id}:{symbol}",
        result_kind="comparator",
        model_family=comparator_id,
        symbol=symbol,
        lineage_hash=None,
        actions=actions,
        slots=slots,
        campaign_input=campaign_input,
    )


def _evaluate_actions(
    *,
    result_id: str,
    result_kind: Literal["candidate", "comparator"],
    model_family: str,
    symbol: str,
    lineage_hash: str | None,
    actions: Sequence[bool],
    slots: Sequence[KisNasD1VolatilityTrendEvaluationSlot],
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
) -> KisNasD1VolatilityTrendEvaluationResult:
    if len(actions) != len(slots) or not slots:
        raise ValueError("NAS D1 volatility trend evaluation actions are invalid")
    event_store = InMemoryCampaignEventStore()
    broker = _CampaignLocalPaperBroker(
        event_store=event_store,
        emergency_store=_ClearEmergencyStore(updated_at=slots[0].signal_bar.end_ts),  # type: ignore[arg-type]
        starting_cash=KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_STARTING_CASH,
        fee_bps=campaign_input.contract.costs.fee_bps,
        slippage_bps=campaign_input.contract.costs.slippage_bps,
    )
    high_water = KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_STARTING_CASH
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
        starting_cash=KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_STARTING_CASH,
    )
    if (
        account != replayed
        or account.quantity(market="US", symbol=symbol) != Decimal("0")
        or len(fills) != sum(actions) * 2
        or any(event.payload.get("source") != LOCAL_PAPER_SOURCE for event in fills)
    ):
        raise ValueError("NAS D1 volatility trend local-paper replay is invalid")
    return KisNasD1VolatilityTrendEvaluationResult(
        result_id=result_id,
        result_kind=result_kind,
        model_family=model_family,
        symbol=symbol,
        lineage_hash=lineage_hash,
        sample_count=len(slots),
        long_slot_count=sum(actions),
        fill_count=len(fills),
        after_cost_delta=account.cash - KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_STARTING_CASH,
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
    slot: KisNasD1VolatilityTrendEvaluationSlot,
) -> tuple[Decimal, Decimal, Decimal]:
    decision_id = f"{result_id}-slot-{slot_index:03d}"
    entry = broker.submit_and_fill_next_bar(
        OrderIntent(
            client_order_id=f"{decision_id}-entry",
            symbol=symbol,
            market="US",
            side="buy",
            quantity=KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_QUANTITY,
            limit_price=None,
            decision_id=decision_id,
            created_at=slot.signal_bar.end_ts,
        ),
        signal_bar=slot.signal_bar,
        execution_bar=slot.entry_bar,
    )
    exit = broker.submit_and_fill_next_bar(
        OrderIntent(
            client_order_id=f"{decision_id}-exit",
            symbol=symbol,
            market="US",
            side="sell",
            quantity=KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_QUANTITY,
            limit_price=None,
            decision_id=decision_id,
            created_at=slot.entry_bar.end_ts,
        ),
        signal_bar=slot.entry_bar,
        execution_bar=slot.exit_bar,
    )
    entry_account = entry.account
    exit_account = exit.account
    if (
        entry.fill is None
        or exit.fill is None
        or entry.fill.source != LOCAL_PAPER_SOURCE
        or exit.fill.source != LOCAL_PAPER_SOURCE
        or exit_account.quantity(market="US", symbol=symbol) != Decimal("0")
    ):
        raise ValueError("NAS D1 volatility trend local-paper fill is invalid")
    entry_quantity = entry_account.quantity(market="US", symbol=symbol)
    return (
        entry_account.cash + entry.fill.price * entry_quantity,
        entry_account.cash + slot.entry_bar.low * entry_quantity,
        exit_account.cash,
    )


def _kill_rule_results(
    candidates: Sequence[KisNasD1VolatilityTrendEvaluationResult],
    comparators: Sequence[KisNasD1VolatilityTrendEvaluationResult],
) -> tuple[KisNasD1VolatilityTrendKillRuleResult, ...]:
    ungated = {
        result.symbol: result
        for result in comparators
        if result.model_family == "ungated_5d_trend"
    }
    if tuple(sorted(ungated)) != tuple(sorted(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)):
        raise ValueError("NAS D1 volatility trend ungated comparator is incomplete")
    return tuple(
        KisNasD1VolatilityTrendKillRuleResult(
            candidate_result_id=candidate.result_id,
            comparator_result_id=ungated[candidate.symbol].result_id,
            candidate_symbol=candidate.symbol,
            kill_rule_met=(
                candidate.after_cost_delta > ungated[candidate.symbol].after_cost_delta
                and candidate.maximum_drawdown <= ungated[candidate.symbol].maximum_drawdown
            ),
        )
        for candidate in candidates
    )


def _validate_result_sets(
    candidates: Sequence[KisNasD1VolatilityTrendEvaluationResult],
    comparators: Sequence[KisNasD1VolatilityTrendEvaluationResult],
) -> None:
    if (
        len(candidates)
        != len(KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS)
        + len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS)
        or len(comparators)
        != len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
        * len(KIS_NAS_D1_VOLATILITY_TREND_COMPARATORS)
        or any(result.result_kind != "candidate" for result in candidates)
        or any(result.result_kind != "comparator" for result in comparators)
        or len({result.result_id for result in candidates + comparators})
        != len(candidates) + len(comparators)
    ):
        raise ValueError("NAS D1 volatility trend sealed result sets are invalid")
    counts = {result.sample_count for result in candidates + comparators}
    if counts != {KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_SLOT_COUNT}:
        raise ValueError("NAS D1 volatility trend sealed slot count drifted")


def _validate_slot_order(slots: Sequence[KisNasD1VolatilityTrendEvaluationSlot]) -> None:
    if not slots or tuple(slot.sample.decision_start for slot in slots) != tuple(
        sorted(slot.sample.decision_start for slot in slots)
    ):
        raise ValueError("NAS D1 volatility trend slots are unordered")
    for prior, current in zip(slots[:-1], slots[1:], strict=True):
        if prior.exit_bar.start_ts != current.signal_bar.start_ts:
            raise ValueError("NAS D1 volatility trend slots overlap or skip")


def _validate_external_candidate_evidence(
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
    *,
    repository: Path,
) -> None:
    cpu_summary = _require_external_file(evaluation_input.cpu_summary_path, repository)
    cuda_summary = _require_external_file(evaluation_input.cuda_summary_path, repository)
    checkpoint_root = _require_external_directory(evaluation_input.checkpoint_root, repository)
    if (
        _sha256_file(cpu_summary) != evaluation_input.evidence.cpu_summary_hash
        or _sha256_file(cuda_summary) != evaluation_input.evidence.cuda_summary_hash
        or evaluation_input.evidence.panel_dataset_hash
        != KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_PANEL_HASH
        or evaluation_input.evidence.campaign_precommit_hash
        != KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CAMPAIGN_PRECOMMIT_HASH
        or evaluation_input.evidence.cpu_summary_hash
        != KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CPU_SUMMARY_HASH
        or evaluation_input.evidence.cuda_summary_hash
        != KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CUDA_SUMMARY_HASH
    ):
        raise ValueError("NAS D1 volatility trend sealed candidate evidence drifted")
    cpu_payload = _load_json_object(cpu_summary, "CPU summary")
    cuda_payload = _load_json_object(cuda_summary, "CUDA summary")
    if (
        cpu_payload.get("kind") != "kis_nas_d1_volatility_trend_cpu_smoke"
        or cpu_payload.get("status") != "completed"
        or cuda_payload.get("kind") != "kis_nas_d1_volatility_trend_cuda_breadth"
        or cuda_payload.get("status") != "completed"
        or not isinstance(cuda_payload.get("candidates"), list)
        or len(cuda_payload["candidates"])
        != len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS)
    ):
        raise ValueError("NAS D1 volatility trend sealed candidate receipts are invalid")
    for receipt, spec in zip(
        cuda_payload["candidates"],
        KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS,
        strict=True,
    ):
        if not isinstance(receipt, Mapping):
            raise ValueError("NAS D1 volatility trend sealed CUDA receipt is invalid")
        checkpoint = _require_external_file(
            checkpoint_root / f"{spec.architecture_id}-{spec.symbol.lower()}.pt",
            repository,
        )
        if receipt.get("architecture") != spec.safe_payload() or (
            _sha256_file(checkpoint) != receipt.get("checkpoint_sha256")
        ):
            raise ValueError("NAS D1 volatility trend sealed checkpoint drifted")


def _precommit_payload(
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
    *,
    review_status: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_sealed_evaluation_precommit",
        "evaluation_id": KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ID,
        "evidence": {
            "panel_dataset_hash": evaluation_input.evidence.panel_dataset_hash,
            "campaign_contract_hash": evaluation_input.evidence.campaign_contract_hash,
            "campaign_precommit_hash": evaluation_input.evidence.campaign_precommit_hash,
            "cpu_summary_hash": evaluation_input.evidence.cpu_summary_hash,
            "cuda_summary_hash": evaluation_input.evidence.cuda_summary_hash,
        },
        "source": _source_payload(evaluation_input),
        "candidates": {
            "cpu_count": len(KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS),
            "cuda_count": len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS),
            "total_count": len(KIS_NAS_D1_VOLATILITY_TREND_CPU_LOGISTIC_SPECS)
            + len(KIS_NAS_D1_VOLATILITY_TREND_CUDA_ARCHITECTURE_SPECS),
        },
        "decision": {
            "threshold": "0.5",
            "long_rule": "probability_greater_than_or_equal_to_threshold",
            "quantity": "1",
            "decision_stride_sessions": 2,
            "entry_exit": "t_plus_1_open_to_t_plus_2_open",
            "drawdown_marks": "entry_fill_equity_entry_bar_low_and_exit_cash",
        },
        "comparators": list(KIS_NAS_D1_VOLATILITY_TREND_COMPARATORS),
        "kill_rule": (
            "strictly_improves_paired_after_cost_return_without_worse_maximum_drawdown"
        ),
        "review_status": review_status,
        "artifact_policy": {
            "repo_storage_allowed": False,
            "raw_rows_persisted": False,
            "target_values_persisted": False,
            "prediction_values_persisted": False,
            "event_rows_persisted": False,
            "checkpoint_copies_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _summary_payload(
    *,
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
    precommit_hash: str,
    review_status: str,
    candidate_results: Sequence[KisNasD1VolatilityTrendEvaluationResult],
    comparator_results: Sequence[KisNasD1VolatilityTrendEvaluationResult],
    kill_rule_results: Sequence[KisNasD1VolatilityTrendKillRuleResult],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_sealed_evaluation",
        "status": "completed",
        "precommit_hash": precommit_hash,
        "review_status": review_status,
        "source": _source_payload(evaluation_input),
        "candidates": [result.safe_payload() for result in candidate_results],
        "comparators": [result.safe_payload() for result in comparator_results],
        "kill_rule_results": [result.safe_payload() for result in kill_rule_results],
        "artifact_policy": {
            "repo_storage_allowed": False,
            "raw_rows_persisted": False,
            "target_values_persisted": False,
            "prediction_values_persisted": False,
            "event_rows_persisted": False,
            "checkpoint_copies_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _failure_payload(
    *,
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
    precommit_hash: str | None,
    review_status: str,
    failure_class: str,
    stage: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_sealed_evaluation_failure",
        "status": "failed_before_result_retention",
        "precommit_hash": precommit_hash,
        "review_status": review_status,
        "failure_class": failure_class,
        "stage": stage,
        "source": _source_payload(evaluation_input),
        "artifact_policy": {
            "raw_rows_persisted": False,
            "target_values_persisted": False,
            "prediction_values_persisted": False,
            "event_rows_persisted": False,
            "checkpoint_copies_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _source_payload(
    evaluation_input: KisNasD1VolatilityTrendSealedEvaluationInput,
) -> dict[str, object]:
    return {
        "panel_dataset_hash": evaluation_input.source_input.panel_dataset_hash,
        "campaign_contract_hash": evaluation_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": evaluation_input.breadth_input.campaign_precommit_hash,
        "development_input_hash": evaluation_input.campaign_input.development_input_hash,
        "validation_input_hash": evaluation_input.campaign_input.validation_input_hash,
        "symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
        "source_limitations": list(evaluation_input.campaign_input.source_limitations),
        "phase_session_counts": {
            "development": len(evaluation_input.source_input.development.common_sessions),
            "purge": len(evaluation_input.source_input.purge.common_sessions),
            "validation": len(evaluation_input.source_input.validation.common_sessions),
        },
    }


def _reporting_payload() -> dict[str, object]:
    return {
        "selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "paper_trading_eligible": False,
        "candidate_ranking_allowed": False,
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
    output = root / KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_ID / run_label
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
        raise ValueError("NAS D1 volatility trend external receipt is invalid")
    resolved = candidate.resolve()
    _reject_repository_artifact_path(resolved, repository)
    _reject_repository_artifact_path(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _require_external_directory(path: Path | str, repository: Path) -> Path:
    candidate = Path(path)
    _reject_link_or_junction_components(candidate)
    if not candidate.is_dir():
        raise ValueError("NAS D1 volatility trend external checkpoint root is invalid")
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
    raise ValueError("NAS D1 volatility trend artifacts must stay outside the Git workspace")


def _reject_link_or_junction_components(path: Path) -> None:
    candidate = path.absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts:
        if part == candidate.anchor:
            continue
        current /= part
        is_junction = getattr(current, "is_junction", None)
        if current.is_symlink() or (callable(is_junction) and is_junction()):
            raise ValueError("NAS D1 volatility trend artifact path cannot contain a link")


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    _reject_link_or_junction_components(path.parent)
    if path.exists():
        raise FileExistsError("NAS D1 volatility trend sealed receipt is immutable")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return _sha256_file(path)


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"NAS D1 volatility trend {label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"NAS D1 volatility trend {label} is invalid")
    return payload


def _event_transcript_hash(events: Sequence[Event]) -> str:
    return _sha256_payload({"events": [event.to_record() for event in events]})


def _repository_root(value: Path | str | None) -> Path:
    return Path(value or Path.cwd()).resolve()


def _validate_run_label(value: str) -> None:
    if not isinstance(value, str) or _RUN_LABEL.fullmatch(value) is None:
        raise ValueError("NAS D1 volatility trend sealed run label is invalid")


def _numpy() -> object:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - project runtime provides NumPy.
        raise RuntimeError("NAS D1 volatility trend sealed evaluation requires NumPy") from exc
    return numpy


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_payload(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
        "event_rows",
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
                raise ValueError("NAS D1 volatility trend receipt contains a source value field")
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


KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EVIDENCE = (
    KisNasD1VolatilityTrendSealedEvaluationEvidence(
        panel_dataset_hash=KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_PANEL_HASH,
        campaign_contract_hash=(
            KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CAMPAIGN_CONTRACT_HASH
        ),
        campaign_precommit_hash=(
            KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CAMPAIGN_PRECOMMIT_HASH
        ),
        cpu_summary_hash=KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CPU_SUMMARY_HASH,
        cuda_summary_hash=KIS_NAS_D1_VOLATILITY_TREND_SEALED_EVALUATION_EXPECTED_CUDA_SUMMARY_HASH,
    )
)


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")
