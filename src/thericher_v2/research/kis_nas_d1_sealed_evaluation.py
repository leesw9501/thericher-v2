"""One fixed sealed NAS D1 evaluation with in-memory local-paper attribution.

This module deliberately consumes the frozen breadth artifacts only once.  It
keeps probabilities, labels, prices, orders, and local-paper event rows in
memory, then writes source-safe aggregate facts only.  No provider, credential,
KIS, or live-broker path is imported here.
"""

from __future__ import annotations

import hashlib
import json
import math
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
from thericher_v2.execution.local_paper import (
    LOCAL_PAPER_SOURCE,
    replay_local_paper_account,
)
from thericher_v2.research.kis_nas_d1_sequence_breadth import (
    KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_CONTRACT_HASH,
    KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_PRECOMMIT_HASH,
    KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS,
    KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS,
    KisNasD1L2LogisticModel,
    KisNasD1SequenceArchitectureSpec,
    KisNasD1SequenceBreadthInput,
    _require_attested_breadth_input,
    _validate_cpu_smoke_summary,
    build_kis_nas_d1_sequence_breadth_input,
    fit_kis_nas_d1_l2_logistic_smoke,
)
from thericher_v2.research.kis_nas_d1_sequence_campaign import (
    KIS_NAS_D1_SEQUENCE_COMPARATORS,
    KIS_NAS_D1_SEQUENCE_FEATURE_NAMES,
    KIS_NAS_D1_SEQUENCE_LENGTH,
    KisNasD1SequenceCampaignInput,
    KisNasD1ValidationSample,
    _after_cost_label,
    build_kis_nas_d1_sequence_campaign,
    calculate_kis_nas_d1_sequence_campaign_precommit_hash,
    require_attested_kis_nas_d1_sequence_campaign_input,
)
from thericher_v2.research.sequence_architecture_models import build_torch_sequence_model
from thericher_v2.research.validation import (
    InMemoryCampaignEventStore,
    _CampaignLocalPaperBroker,
)
from thericher_v2.state import Event

KIS_NAS_D1_SEALED_EVALUATION_ID = "kis-nas-d1-sealed-evaluation-v1"
KIS_NAS_D1_SEALED_EVALUATION_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts/research")
KIS_NAS_D1_SEALED_EVALUATION_EXPECTED_PANEL_HASH = (
    "sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e"
)
KIS_NAS_D1_SEALED_EVALUATION_EXPECTED_CPU_SUMMARY_HASH = (
    "sha256:e60cf92d82b5b6dadb361213e2425845cab4d2f7f64c34a08799b7fd73ffc4fa"
)
KIS_NAS_D1_SEALED_EVALUATION_EXPECTED_CUDA_SUMMARY_HASH = (
    "sha256:2c213d0a6aefa63c89aeddf551021d2e92370b59258cde672200301c84253a3f"
)
KIS_NAS_D1_SEALED_EVALUATION_THRESHOLD = 0.5
KIS_NAS_D1_SEALED_EVALUATION_STARTING_CASH = Decimal("10000")
KIS_NAS_D1_SEALED_EVALUATION_QUANTITY = Decimal("1")
_RUN_LABEL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"
_DOCKER_ENVIRONMENT_MARKER = Path("/.dockerenv")
_REVIEW_STATUSES = frozenset(
    {"unsupported", "uncertain", "supported-with-limits", "review_unavailable"}
)
_SEALED_EVALUATION_ALLOWED_REVIEW_STATUSES = frozenset({"review_unavailable"})


def _is_sha256(value: object) -> bool:
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


@dataclass(frozen=True, slots=True)
class KisNasD1SealedEvaluationEvidence:
    """Pinned artifact identities needed before the sealed target is opened."""

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
            raise ValueError("NAS D1 sealed evaluation evidence is invalid")


KIS_NAS_D1_SEALED_EVALUATION_EVIDENCE = KisNasD1SealedEvaluationEvidence(
    panel_dataset_hash=KIS_NAS_D1_SEALED_EVALUATION_EXPECTED_PANEL_HASH,
    campaign_contract_hash=KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_CONTRACT_HASH,
    campaign_precommit_hash=KIS_NAS_D1_SEQUENCE_BREADTH_EXPECTED_CAMPAIGN_PRECOMMIT_HASH,
    cpu_summary_hash=KIS_NAS_D1_SEALED_EVALUATION_EXPECTED_CPU_SUMMARY_HASH,
    cuda_summary_hash=KIS_NAS_D1_SEALED_EVALUATION_EXPECTED_CUDA_SUMMARY_HASH,
)


@dataclass(frozen=True, slots=True)
class KisNasD1SealedEvaluationInput:
    """Reattested source and all pinned breadth evidence for one evaluation."""

    source_input: KisPaperDailyHistorySequenceInput
    campaign_input: KisNasD1SequenceCampaignInput
    breadth_input: KisNasD1SequenceBreadthInput
    evidence: KisNasD1SealedEvaluationEvidence
    cpu_summary_path: Path
    cuda_summary_path: Path
    checkpoint_root: Path


@dataclass(frozen=True, slots=True)
class KisNasD1SealedEvaluationResult:
    """One aggregate-only candidate or comparator result."""

    result_id: str
    result_kind: Literal["candidate", "comparator"]
    model_family: str
    symbol: str
    lineage_hash: str | None
    true_positive_count: int
    false_positive_count: int
    true_negative_count: int
    false_negative_count: int
    long_slot_count: int
    fill_count: int
    after_cost_delta: Decimal
    gross_delta: Decimal
    fee_total: Decimal
    slippage_total: Decimal
    transcript_sha256: str
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
            or any(
                value < 0
                for value in (
                    self.true_positive_count,
                    self.false_positive_count,
                    self.true_negative_count,
                    self.false_negative_count,
                    self.long_slot_count,
                    self.fill_count,
                )
            )
            or self.fill_count != self.long_slot_count * 2
            or not _is_sha256(self.transcript_sha256)
            or not self.all_fills_local_paper
            or not self.replay_reconstructed
            or not self.terminal_position_zero
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 sealed evaluation result is invalid")

    @property
    def sample_count(self) -> int:
        return (
            self.true_positive_count
            + self.false_positive_count
            + self.true_negative_count
            + self.false_negative_count
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "result_id": self.result_id,
            "result_kind": self.result_kind,
            "model_family": self.model_family,
            "symbol": self.symbol,
            "lineage_hash": self.lineage_hash,
            "classification": {
                "sample_count": self.sample_count,
                "true_positive_count": self.true_positive_count,
                "false_positive_count": self.false_positive_count,
                "true_negative_count": self.true_negative_count,
                "false_negative_count": self.false_negative_count,
                "long_slot_count": self.long_slot_count,
            },
            "replay": {
                "fill_source": LOCAL_PAPER_SOURCE,
                "fill_count": self.fill_count,
                "after_cost_delta": _decimal_text(self.after_cost_delta),
                "gross_delta": _decimal_text(self.gross_delta),
                "fee_total": _decimal_text(self.fee_total),
                "slippage_total": _decimal_text(self.slippage_total),
                "transcript_sha256": self.transcript_sha256,
                "all_fills_local_paper": self.all_fills_local_paper,
                "replay_reconstructed": self.replay_reconstructed,
                "terminal_position_zero": self.terminal_position_zero,
                "event_rows_retained": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisNasD1SealedEvaluationRun:
    """External source-safe precommit and aggregate result paths."""

    evaluation_input: KisNasD1SealedEvaluationInput
    run_label: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    summary_hash: str
    candidate_results: tuple[KisNasD1SealedEvaluationResult, ...]
    comparator_results: tuple[KisNasD1SealedEvaluationResult, ...]
    review_status: str


@dataclass(frozen=True, slots=True)
class _PredictionBatch:
    result_id: str
    model_family: str
    symbol: str
    lineage_hash: str
    probabilities: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _ValidationSlot:
    sample: KisNasD1ValidationSample
    signal_bar: Bar
    entry_bar: Bar
    exit_bar: Bar


@dataclass(frozen=True, slots=True)
class _ClearEmergencyStore:
    """LocalPaperBroker's minimal no-I/O emergency dependency."""

    updated_at: datetime

    def read(self) -> EmergencyState:
        return EmergencyState(
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            reason="sealed_nas_d1_offline_evaluation",
            updated_at=self.updated_at,
        )


def build_kis_nas_d1_sealed_evaluation_input(
    source_input: KisPaperDailyHistorySequenceInput,
    *,
    evidence: KisNasD1SealedEvaluationEvidence,
    cpu_summary_path: Path | str,
    cuda_summary_path: Path | str,
    checkpoint_root: Path | str,
) -> KisNasD1SealedEvaluationInput:
    """Bind one reattested source view to frozen breadth evidence."""

    if evidence != KIS_NAS_D1_SEALED_EVALUATION_EVIDENCE:
        raise ValueError("NAS D1 sealed evaluation evidence is not frozen")
    require_attested_kis_paper_daily_history_sequence_input(source_input)
    campaign_input = build_kis_nas_d1_sequence_campaign(source_input)
    if (
        source_input.panel_dataset_hash != evidence.panel_dataset_hash
        or campaign_input.contract.contract_hash != evidence.campaign_contract_hash
        or calculate_kis_nas_d1_sequence_campaign_precommit_hash(campaign_input)
        != evidence.campaign_precommit_hash
    ):
        raise ValueError("NAS D1 sealed evaluation source evidence is not pinned")
    breadth_input = build_kis_nas_d1_sequence_breadth_input(
        campaign_input,
        campaign_precommit_hash=evidence.campaign_precommit_hash,
    )
    result = KisNasD1SealedEvaluationInput(
        source_input=source_input,
        campaign_input=campaign_input,
        breadth_input=breadth_input,
        evidence=evidence,
        cpu_summary_path=Path(cpu_summary_path),
        cuda_summary_path=Path(cuda_summary_path),
        checkpoint_root=Path(checkpoint_root),
    )
    require_attested_kis_nas_d1_sealed_evaluation_input(result)
    return result


def require_attested_kis_nas_d1_sealed_evaluation_input(value: object) -> None:
    """Reject any source, phase, or lineage drift before target reconstruction."""

    if not isinstance(value, KisNasD1SealedEvaluationInput):
        raise ValueError("NAS D1 sealed evaluation input is invalid")
    require_attested_kis_paper_daily_history_sequence_input(value.source_input)
    require_attested_kis_nas_d1_sequence_campaign_input(value.campaign_input)
    _require_attested_breadth_input(value.breadth_input)
    if (
        value.breadth_input.campaign_input is not value.campaign_input
        or value.evidence != KIS_NAS_D1_SEALED_EVALUATION_EVIDENCE
        or value.source_input.panel_dataset_hash != value.evidence.panel_dataset_hash
        or value.campaign_input.contract.contract_hash != value.evidence.campaign_contract_hash
        or value.breadth_input.campaign_precommit_hash != value.evidence.campaign_precommit_hash
        or calculate_kis_nas_d1_sequence_campaign_precommit_hash(value.campaign_input)
        != value.evidence.campaign_precommit_hash
        or tuple(value.campaign_input.validation_samples_by_symbol)
        != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or tuple(value.source_input.validation.bars_by_symbol)
        != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        raise ValueError("NAS D1 sealed evaluation input is not attested")


def run_kis_nas_d1_sealed_evaluation(
    evaluation_input: KisNasD1SealedEvaluationInput,
    *,
    artifact_root: Path | str = KIS_NAS_D1_SEALED_EVALUATION_ARTIFACT_ROOT,
    run_label: str,
    review_status: str,
    repo_root: Path | str | None = None,
) -> KisNasD1SealedEvaluationRun:
    """Evaluate exactly the frozen candidates after source-safe precommit."""

    require_attested_kis_nas_d1_sealed_evaluation_input(evaluation_input)
    if review_status not in _REVIEW_STATUSES:
        raise ValueError("NAS D1 sealed evaluation review status is invalid")
    if review_status not in _SEALED_EVALUATION_ALLOWED_REVIEW_STATUSES:
        raise ValueError("NAS D1 sealed evaluation review does not permit target opening")
    repository = Path(repo_root or Path.cwd()).resolve()
    _validate_run_label(run_label)
    cpu_summary = _load_cpu_summary(evaluation_input, repository=repository)
    cuda_summary = _load_cuda_summary(evaluation_input, repository=repository)
    output_dir = _prepare_output_dir(
        artifact_root=artifact_root,
        repository=repository,
        run_label=run_label,
    )
    precommit_payload = _precommit_payload(evaluation_input, review_status=review_status)
    _assert_source_safe(precommit_payload)
    precommit_path = output_dir / "precommit.json"
    precommit_hash = _write_json_new(precommit_path, precommit_payload)
    try:
        prediction_batches = _prediction_batches(
            evaluation_input,
            cpu_summary=cpu_summary,
            cuda_summary=cuda_summary,
            repository=repository,
        )
        slots_by_symbol = _validation_slots(evaluation_input)
        candidate_results = tuple(
            _evaluate_prediction_batch(batch, slots_by_symbol[batch.symbol], evaluation_input)
            for batch in prediction_batches
        )
        comparator_results = tuple(
            _evaluate_comparator(
                comparator,
                symbol,
                slots_by_symbol[symbol],
                evaluation_input,
            )
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            for comparator in KIS_NAS_D1_SEQUENCE_COMPARATORS
        )
        _validate_result_sets(candidate_results, comparator_results)
        summary_payload = _summary_payload(
            evaluation_input=evaluation_input,
            precommit_hash=precommit_hash,
            review_status=review_status,
            candidate_results=candidate_results,
            comparator_results=comparator_results,
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
        )
        _assert_source_safe(failure_payload)
        _write_json_new(output_dir / "failure.json", failure_payload)
        raise
    return KisNasD1SealedEvaluationRun(
        evaluation_input=evaluation_input,
        run_label=run_label,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        summary_hash=summary_hash,
        candidate_results=candidate_results,
        comparator_results=comparator_results,
        review_status=review_status,
    )


def _load_cpu_summary(
    evaluation_input: KisNasD1SealedEvaluationInput,
    *,
    repository: Path,
) -> dict[str, object]:
    path = _require_external_file(evaluation_input.cpu_summary_path, repository)
    summary_hash = _validate_cpu_smoke_summary(
        path,
        evaluation_input.breadth_input,
        repository=repository,
    )
    if summary_hash != evaluation_input.evidence.cpu_summary_hash:
        raise ValueError("NAS D1 sealed evaluation CPU summary hash drifted")
    payload = _load_json_object(path, "CPU summary")
    _assert_source_safe(payload)
    return payload


def _load_cuda_summary(
    evaluation_input: KisNasD1SealedEvaluationInput,
    *,
    repository: Path,
) -> dict[str, object]:
    summary_path = _require_external_file(evaluation_input.cuda_summary_path, repository)
    precommit_path = _require_external_file(summary_path.with_name("precommit.json"), repository)
    checkpoint_root = _require_external_directory(evaluation_input.checkpoint_root, repository)
    summary_hash = _sha256_file(summary_path)
    if summary_hash != evaluation_input.evidence.cuda_summary_hash:
        raise ValueError("NAS D1 sealed evaluation CUDA summary hash drifted")
    payload = _load_json_object(summary_path, "CUDA summary")
    precommit = _load_json_object(precommit_path, "CUDA precommit")
    _assert_source_safe(payload)
    _assert_source_safe(precommit)
    source = _breadth_source_payload(evaluation_input.breadth_input)
    if (
        set(payload)
        != {
            "schema_version",
            "kind",
            "status",
            "reason",
            "precommit_hash",
            "cpu_smoke_summary_hash",
            "source",
            "candidates",
            "validation",
            "artifact_policy",
            "reporting",
        }
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != "kis_nas_d1_sequence_cuda_breadth"
        or payload.get("status") != "completed"
        or payload.get("precommit_hash") != _sha256_file(precommit_path)
        or payload.get("cpu_smoke_summary_hash") != evaluation_input.evidence.cpu_summary_hash
        or payload.get("source") != source
        or payload.get("validation") != {"labels_materialized": False, "forward_only": True}
        or payload.get("artifact_policy")
        != {
            "repo_storage_allowed": False,
            "checkpoints_written": True,
            "raw_rows_persisted": False,
            "predictions_persisted": False,
        }
        or payload.get("reporting") != _breadth_reporting_payload()
        or not _matches_cuda_precommit(
            precommit,
            evaluation_input=evaluation_input,
        )
        or not _matches_cuda_summary_candidates(
            payload.get("candidates"),
            evaluation_input=evaluation_input,
            checkpoint_root=checkpoint_root,
        )
    ):
        raise ValueError("NAS D1 sealed evaluation CUDA evidence is invalid")
    return payload


def _prediction_batches(
    evaluation_input: KisNasD1SealedEvaluationInput,
    *,
    cpu_summary: Mapping[str, object],
    cuda_summary: Mapping[str, object],
    repository: Path,
) -> tuple[_PredictionBatch, ...]:
    batches = list(_cpu_prediction_batches(evaluation_input, cpu_summary=cpu_summary))
    batches.extend(
        _cuda_prediction_batches(
            evaluation_input,
            cuda_summary=cuda_summary,
            repository=repository,
        )
    )
    if len(batches) != len(KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS) + len(
        KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS
    ):
        raise ValueError("NAS D1 sealed evaluation candidate count is invalid")
    return tuple(batches)


def _cpu_prediction_batches(
    evaluation_input: KisNasD1SealedEvaluationInput,
    *,
    cpu_summary: Mapping[str, object],
) -> tuple[_PredictionBatch, ...]:
    summary_candidates = cpu_summary.get("candidates")
    if not isinstance(summary_candidates, list):
        raise ValueError("NAS D1 sealed evaluation CPU candidates are invalid")
    by_symbol = {
        item.get("symbol"): item
        for item in summary_candidates
        if isinstance(item, Mapping) and isinstance(item.get("symbol"), str)
    }
    if tuple(by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 sealed evaluation CPU symbol order is invalid")
    batches: list[_PredictionBatch] = []
    for spec in KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS:
        model = fit_kis_nas_d1_l2_logistic_smoke(evaluation_input.breadth_input, spec)
        receipt = by_symbol[spec.symbol]
        if (
            receipt.get("model_parameter_hash") != model.parameter_hash
            or receipt.get("standardizer_hash")
            != evaluation_input.breadth_input.standardizer(spec.symbol).standardizer_hash
            or receipt.get("development_sample_count")
            != len(evaluation_input.campaign_input.development_samples(spec.symbol))
        ):
            raise ValueError("NAS D1 sealed evaluation CPU model lineage drifted")
        probabilities = _cpu_probabilities(
            evaluation_input.breadth_input,
            model,
            evaluation_input.campaign_input.validation_samples(spec.symbol),
        )
        batches.append(
            _PredictionBatch(
                result_id=f"cpu_l2_logistic:{spec.symbol}",
                model_family="cpu_l2_logistic",
                symbol=spec.symbol,
                lineage_hash=model.parameter_hash,
                probabilities=probabilities,
            )
        )
    return tuple(batches)


def _cuda_prediction_batches(
    evaluation_input: KisNasD1SealedEvaluationInput,
    *,
    cuda_summary: Mapping[str, object],
    repository: Path,
) -> tuple[_PredictionBatch, ...]:
    candidates = cuda_summary.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("NAS D1 sealed evaluation CUDA candidates are invalid")
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - Docker runtime supplies torch.
        raise RuntimeError(
            "NAS D1 sealed evaluation requires PyTorch checkpoint inference"
        ) from exc
    batches: list[_PredictionBatch] = []
    for receipt, spec in zip(candidates, KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS, strict=True):
        if not isinstance(receipt, Mapping):
            raise ValueError("NAS D1 sealed evaluation CUDA candidate is invalid")
        checkpoint_path = _require_external_file(
            evaluation_input.checkpoint_root / f"{spec.architecture_id}-{spec.symbol}.pt",
            repository,
        )
        checkpoint_hash = receipt.get("checkpoint_sha256")
        if not _is_sha256(checkpoint_hash) or _sha256_file(checkpoint_path) != checkpoint_hash:
            raise ValueError("NAS D1 sealed evaluation checkpoint hash drifted")
        model = _load_cuda_checkpoint(
            checkpoint_path,
            breadth_input=evaluation_input.breadth_input,
            spec=spec,
            torch=torch,
        )
        probabilities = _cuda_probabilities(
            model,
            breadth_input=evaluation_input.breadth_input,
            spec=spec,
            torch=torch,
        )
        batches.append(
            _PredictionBatch(
                result_id=f"cuda_{spec.architecture_id}:{spec.symbol}",
                model_family=f"cuda_{spec.architecture_id}",
                symbol=spec.symbol,
                lineage_hash=checkpoint_hash,
                probabilities=probabilities,
            )
        )
    return tuple(batches)


def _cpu_probabilities(
    breadth_input: KisNasD1SequenceBreadthInput,
    model: KisNasD1L2LogisticModel,
    samples: Sequence[KisNasD1ValidationSample],
) -> tuple[float, ...]:
    standardizer = breadth_input.standardizer(model.spec.symbol)
    if (
        model.development_input_hash != standardizer.development_input_hash
        or model.standardizer_hash != standardizer.standardizer_hash
    ):
        raise ValueError("NAS D1 sealed evaluation CPU standardizer drifted")
    numpy = _numpy()
    features = numpy.asarray(
        [standardizer.transform(sample.close_returns) for sample in samples],
        dtype=numpy.float64,
    )
    weights = numpy.asarray(model.weights, dtype=numpy.float64)
    outputs = 1.0 / (1.0 + numpy.exp(-numpy.clip(features @ weights + model.intercept, -60, 60)))
    if (
        features.shape != (len(samples), KIS_NAS_D1_SEQUENCE_LENGTH)
        or outputs.shape != (len(samples),)
        or not numpy.isfinite(outputs).all()
        or not bool(((outputs >= 0.0) & (outputs <= 1.0)).all())
    ):
        raise ValueError("NAS D1 sealed evaluation CPU inference is invalid")
    return tuple(float(value) for value in outputs)


def _load_cuda_checkpoint(
    checkpoint_path: Path,
    *,
    breadth_input: KisNasD1SequenceBreadthInput,
    spec: KisNasD1SequenceArchitectureSpec,
    torch: object,
) -> object:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover - depends on a corrupt external checkpoint.
        raise ValueError("NAS D1 sealed evaluation checkpoint cannot be safely loaded") from exc
    standardizer = breadth_input.standardizer(spec.symbol)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != "kis_nas_d1_sequence_breadth_checkpoint"
        or payload.get("campaign_contract_hash")
        != breadth_input.campaign_input.contract.contract_hash
        or payload.get("development_input_hash") != standardizer.development_input_hash
        or payload.get("standardizer_hash") != standardizer.standardizer_hash
        or payload.get("architecture") != spec.safe_payload()
    ):
        raise ValueError("NAS D1 sealed evaluation checkpoint contract is invalid")
    model = build_torch_sequence_model(
        torch=torch,
        architecture_id=spec.architecture_id,
        feature_count=len(KIS_NAS_D1_SEQUENCE_FEATURE_NAMES),
        hidden_size=spec.hidden_size,
        attention_heads=spec.attention_heads,
        tcn_kernel_size=spec.tcn_kernel_size,
    )
    try:
        model.load_state_dict(payload["state_dict"], strict=True)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("NAS D1 sealed evaluation checkpoint state is incompatible") from exc
    model.eval()
    return model


def _cuda_probabilities(
    model: object,
    *,
    breadth_input: KisNasD1SequenceBreadthInput,
    spec: KisNasD1SequenceArchitectureSpec,
    torch: object,
) -> tuple[float, ...]:
    samples = breadth_input.campaign_input.validation_samples(spec.symbol)
    standardizer = breadth_input.standardizer(spec.symbol)
    values = [standardizer.transform(sample.close_returns) for sample in samples]
    tensor = torch.tensor(values, dtype=torch.float32).unsqueeze(2)
    with torch.no_grad():
        outputs = torch.sigmoid(model(tensor))
    if (
        tuple(outputs.shape) != (len(samples), 1)
        or not bool(torch.isfinite(outputs).all().item())
        or not bool(((outputs >= 0.0) & (outputs <= 1.0)).all().item())
    ):
        raise ValueError("NAS D1 sealed evaluation CUDA inference is invalid")
    return tuple(float(value) for value in outputs.flatten().tolist())


def _validation_slots(
    evaluation_input: KisNasD1SealedEvaluationInput,
) -> dict[str, tuple[_ValidationSlot, ...]]:
    slots_by_symbol: dict[str, tuple[_ValidationSlot, ...]] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        samples = evaluation_input.campaign_input.validation_samples(symbol)
        bars = evaluation_input.source_input.validation.stream(symbol).bars
        by_start = {bar.start_ts: index for index, bar in enumerate(bars)}
        if len(by_start) != len(bars):
            raise ValueError("NAS D1 sealed evaluation validation bars are ambiguous")
        slots: list[_ValidationSlot] = []
        for sample in samples:
            decision_index = by_start.get(sample.decision_start)
            if decision_index is None or decision_index + 2 >= len(bars):
                raise ValueError("NAS D1 sealed evaluation slot is outside validation")
            signal_bar = bars[decision_index]
            entry_bar = bars[decision_index + 1]
            exit_bar = bars[decision_index + 2]
            if (
                signal_bar.end_ts != sample.decision_end
                or entry_bar.start_ts != sample.entry_start
                or exit_bar.start_ts != sample.exit_start
                or signal_bar.start_ts != sample.decision_start
                or not (signal_bar.end_ts < entry_bar.end_ts < exit_bar.end_ts)
            ):
                raise ValueError("NAS D1 sealed evaluation slot timing drifted")
            slots.append(
                _ValidationSlot(
                    sample=sample,
                    signal_bar=signal_bar,
                    entry_bar=entry_bar,
                    exit_bar=exit_bar,
                )
            )
        _validate_slot_order(slots)
        slots_by_symbol[symbol] = tuple(slots)
    return slots_by_symbol


def _evaluate_prediction_batch(
    batch: _PredictionBatch,
    slots: Sequence[_ValidationSlot],
    evaluation_input: KisNasD1SealedEvaluationInput,
) -> KisNasD1SealedEvaluationResult:
    if len(batch.probabilities) != len(slots):
        raise ValueError("NAS D1 sealed evaluation prediction count drifted")
    actions = tuple(
        probability >= KIS_NAS_D1_SEALED_EVALUATION_THRESHOLD for probability in batch.probabilities
    )
    if any(
        not math.isfinite(probability) or not 0.0 <= probability <= 1.0
        for probability in batch.probabilities
    ):
        raise ValueError("NAS D1 sealed evaluation probability is invalid")
    return _evaluate_actions(
        result_id=batch.result_id,
        result_kind="candidate",
        model_family=batch.model_family,
        symbol=batch.symbol,
        lineage_hash=batch.lineage_hash,
        actions=actions,
        slots=slots,
        evaluation_input=evaluation_input,
    )


def _evaluate_comparator(
    comparator: str,
    symbol: str,
    slots: Sequence[_ValidationSlot],
    evaluation_input: KisNasD1SealedEvaluationInput,
) -> KisNasD1SealedEvaluationResult:
    if comparator == "flat":
        actions = (False,) * len(slots)
    elif comparator == "always_long":
        actions = (True,) * len(slots)
    elif comparator == "previous_bar_direction":
        actions = tuple(slot.sample.close_returns[-1] > 0.0 for slot in slots)
    else:
        raise ValueError("NAS D1 sealed evaluation comparator is invalid")
    return _evaluate_actions(
        result_id=f"comparator_{comparator}:{symbol}",
        result_kind="comparator",
        model_family=comparator,
        symbol=symbol,
        lineage_hash=None,
        actions=actions,
        slots=slots,
        evaluation_input=evaluation_input,
    )


def _evaluate_actions(
    *,
    result_id: str,
    result_kind: Literal["candidate", "comparator"],
    model_family: str,
    symbol: str,
    lineage_hash: str | None,
    actions: Sequence[bool],
    slots: Sequence[_ValidationSlot],
    evaluation_input: KisNasD1SealedEvaluationInput,
) -> KisNasD1SealedEvaluationResult:
    if len(actions) != len(slots) or not slots:
        raise ValueError("NAS D1 sealed evaluation actions are invalid")
    event_store = InMemoryCampaignEventStore()
    emergency_store = _ClearEmergencyStore(updated_at=slots[0].signal_bar.end_ts)
    broker = _CampaignLocalPaperBroker(
        event_store=event_store,
        emergency_store=emergency_store,  # type: ignore[arg-type]
        starting_cash=KIS_NAS_D1_SEALED_EVALUATION_STARTING_CASH,
        fee_bps=evaluation_input.campaign_input.contract.costs.fee_bps,
        slippage_bps=evaluation_input.campaign_input.contract.costs.slippage_bps,
    )
    true_positive = false_positive = true_negative = false_negative = 0
    gross_delta = Decimal("0")
    fee_total = Decimal("0")
    slippage_total = Decimal("0")
    for slot_index, (action, slot) in enumerate(zip(actions, slots, strict=True)):
        target = _after_cost_label(
            entry_bar=slot.entry_bar,
            exit_bar=slot.exit_bar,
            costs=evaluation_input.campaign_input.contract.costs,
        )
        if action and target == 1:
            true_positive += 1
        elif action:
            false_positive += 1
        elif target == 1:
            false_negative += 1
        else:
            true_negative += 1
        if not action:
            continue
        entry_order = OrderIntent(
            client_order_id=f"{result_id}-slot-{slot_index:03d}-entry",
            symbol=symbol,
            market="US",
            side="buy",
            quantity=KIS_NAS_D1_SEALED_EVALUATION_QUANTITY,
            limit_price=None,
            decision_id=f"{result_id}-slot-{slot_index:03d}",
            created_at=slot.signal_bar.end_ts,
        )
        entry = broker.submit_and_fill_next_bar(
            entry_order,
            signal_bar=slot.signal_bar,
            execution_bar=slot.entry_bar,
        )
        if entry.fill is None or entry.fill.source != LOCAL_PAPER_SOURCE:
            raise ValueError("NAS D1 sealed evaluation entry fill is invalid")
        exit_order = OrderIntent(
            client_order_id=f"{result_id}-slot-{slot_index:03d}-exit",
            symbol=symbol,
            market="US",
            side="sell",
            quantity=KIS_NAS_D1_SEALED_EVALUATION_QUANTITY,
            limit_price=None,
            decision_id=f"{result_id}-slot-{slot_index:03d}",
            created_at=slot.entry_bar.end_ts,
        )
        exit = broker.submit_and_fill_next_bar(
            exit_order,
            signal_bar=slot.entry_bar,
            execution_bar=slot.exit_bar,
        )
        if exit.fill is None or exit.fill.source != LOCAL_PAPER_SOURCE:
            raise ValueError("NAS D1 sealed evaluation exit fill is invalid")
        if broker.account().quantity(market="US", symbol=symbol) != Decimal("0"):
            raise ValueError("NAS D1 sealed evaluation slot left a position open")
        gross_delta += (
            slot.exit_bar.open - slot.entry_bar.open
        ) * KIS_NAS_D1_SEALED_EVALUATION_QUANTITY
        fee_total += entry.fill.fee + exit.fill.fee
        slippage_total += (
            entry.fill.price - slot.entry_bar.open + slot.exit_bar.open - exit.fill.price
        ) * KIS_NAS_D1_SEALED_EVALUATION_QUANTITY
    events = event_store.iter_events()
    fill_events = tuple(event for event in events if event.event_type == "fill")
    account = broker.account()
    replayed = replay_local_paper_account(
        event_store,  # type: ignore[arg-type]
        starting_cash=KIS_NAS_D1_SEALED_EVALUATION_STARTING_CASH,
    )
    if (
        account != replayed
        or account.quantity(market="US", symbol=symbol) != Decimal("0")
        or len(fill_events) != sum(actions) * 2
        or any(event.payload.get("source") != LOCAL_PAPER_SOURCE for event in fill_events)
    ):
        raise ValueError("NAS D1 sealed evaluation replay is not reconstructable")
    return KisNasD1SealedEvaluationResult(
        result_id=result_id,
        result_kind=result_kind,
        model_family=model_family,
        symbol=symbol,
        lineage_hash=lineage_hash,
        true_positive_count=true_positive,
        false_positive_count=false_positive,
        true_negative_count=true_negative,
        false_negative_count=false_negative,
        long_slot_count=sum(actions),
        fill_count=len(fill_events),
        after_cost_delta=account.cash - KIS_NAS_D1_SEALED_EVALUATION_STARTING_CASH,
        gross_delta=gross_delta,
        fee_total=fee_total,
        slippage_total=slippage_total,
        transcript_sha256=_event_transcript_hash(events),
        all_fills_local_paper=True,
        replay_reconstructed=True,
        terminal_position_zero=True,
    )


def _validate_slot_order(slots: Sequence[_ValidationSlot]) -> None:
    if not slots or tuple(slot.sample.decision_start for slot in slots) != tuple(
        sorted(slot.sample.decision_start for slot in slots)
    ):
        raise ValueError("NAS D1 sealed evaluation slots are unordered")
    for prior, current in zip(slots[:-1], slots[1:], strict=True):
        if prior.exit_bar.start_ts != current.signal_bar.start_ts:
            raise ValueError("NAS D1 sealed evaluation slots overlap or skip")


def _matches_cuda_precommit(
    payload: object,
    *,
    evaluation_input: KisNasD1SealedEvaluationInput,
) -> bool:
    if not isinstance(payload, Mapping):
        return False
    return (
        set(payload)
        == {
            "schema_version",
            "kind",
            "package_id",
            "source",
            "cpu_smoke_summary_hash",
            "candidates",
            "features",
            "validation",
            "checkpoint_policy",
            "reporting",
        }
        and payload.get("schema_version") == SCHEMA_VERSION
        and payload.get("kind") == "kis_nas_d1_sequence_cuda_breadth_precommit"
        and payload.get("package_id") == "nas-d1-per-symbol-sequence-breadth-v1"
        and payload.get("source") == _breadth_source_payload(evaluation_input.breadth_input)
        and payload.get("cpu_smoke_summary_hash") == evaluation_input.evidence.cpu_summary_hash
        and payload.get("candidates")
        == [spec.safe_payload() for spec in KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS]
        and payload.get("features")
        == {
            "sequence_length": KIS_NAS_D1_SEQUENCE_LENGTH,
            "feature_shape": [KIS_NAS_D1_SEQUENCE_LENGTH, 1],
            "per_symbol_only": True,
            "standardization": "per_symbol_development_only",
        }
        and payload.get("validation")
        == {"labels_materialized": False, "operation": "target_free_forward_shape_only"}
        and payload.get("checkpoint_policy")
        == {
            "repo_storage_allowed": False,
            "format": "torch_state_dict_only",
            "safe_weights_only_reload_required": True,
        }
        and payload.get("reporting") == _breadth_reporting_payload()
    )


def _matches_cuda_summary_candidates(
    value: object,
    *,
    evaluation_input: KisNasD1SealedEvaluationInput,
    checkpoint_root: Path,
) -> bool:
    if not isinstance(value, list) or len(value) != len(
        KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS
    ):
        return False
    for item, spec in zip(value, KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS, strict=True):
        standardizer = evaluation_input.breadth_input.standardizer(spec.symbol)
        checkpoint_path = checkpoint_root / f"{spec.architecture_id}-{spec.symbol}.pt"
        if (
            not isinstance(item, Mapping)
            or set(item)
            != {
                "architecture",
                "development_sample_count",
                "checkpoint_sha256",
                "backend",
                "device",
                "torch_version",
                "cuda_version",
                "initial_loss",
                "final_loss",
                "cuda_peak_memory_bytes",
                "safe_weights_only_reload",
                "validation_forward",
            }
            or item.get("architecture") != spec.safe_payload()
            or item.get("development_sample_count")
            != len(evaluation_input.campaign_input.development_samples(spec.symbol))
            or not _is_sha256(item.get("checkpoint_sha256"))
            or not checkpoint_path.is_file()
            or _sha256_file(checkpoint_path) != item.get("checkpoint_sha256")
            or item.get("backend") != "torch_cuda"
            or not isinstance(item.get("device"), str)
            or not isinstance(item.get("torch_version"), str)
            or item.get("cuda_version") is not None
            and not isinstance(item.get("cuda_version"), str)
            or not _is_finite_decimal_text(item.get("initial_loss"))
            or not _is_finite_decimal_text(item.get("final_loss"))
            or not isinstance(item.get("cuda_peak_memory_bytes"), int)
            or item.get("cuda_peak_memory_bytes") < 0
            or item.get("safe_weights_only_reload") is not True
            or item.get("validation_forward")
            != {
                "symbol": spec.symbol,
                "sample_count": len(
                    evaluation_input.campaign_input.validation_samples(spec.symbol)
                ),
                "output_shape": [
                    len(evaluation_input.campaign_input.validation_samples(spec.symbol)),
                    1,
                ],
                "all_finite": True,
                "output_bounds_valid": True,
                "labels_materialized": False,
            }
            or standardizer.standardizer_hash
            not in _breadth_source_payload(evaluation_input.breadth_input)["standardizer_hashes"]
        ):
            return False
    return True


def _validate_result_sets(
    candidate_results: Sequence[KisNasD1SealedEvaluationResult],
    comparator_results: Sequence[KisNasD1SealedEvaluationResult],
) -> None:
    if (
        len(candidate_results)
        != len(KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS)
        + len(KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS)
        or len(comparator_results)
        != len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS) * len(KIS_NAS_D1_SEQUENCE_COMPARATORS)
        or any(result.result_kind != "candidate" for result in candidate_results)
        or any(result.result_kind != "comparator" for result in comparator_results)
    ):
        raise ValueError("NAS D1 sealed evaluation result sets are invalid")
    sample_counts = {result.sample_count for result in candidate_results + comparator_results}
    if sample_counts != {313}:
        raise ValueError("NAS D1 sealed evaluation slot count drifted")


def _precommit_payload(
    evaluation_input: KisNasD1SealedEvaluationInput,
    *,
    review_status: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_sealed_evaluation_precommit",
        "evaluation_id": KIS_NAS_D1_SEALED_EVALUATION_ID,
        "evidence": {
            "panel_dataset_hash": evaluation_input.evidence.panel_dataset_hash,
            "campaign_contract_hash": evaluation_input.evidence.campaign_contract_hash,
            "campaign_precommit_hash": evaluation_input.evidence.campaign_precommit_hash,
            "cpu_summary_hash": evaluation_input.evidence.cpu_summary_hash,
            "cuda_summary_hash": evaluation_input.evidence.cuda_summary_hash,
        },
        "source": _source_payload(evaluation_input),
        "candidates": {
            "cpu_count": len(KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS),
            "cuda_count": len(KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS),
            "total_count": len(KIS_NAS_D1_SEQUENCE_CPU_LOGISTIC_SPECS)
            + len(KIS_NAS_D1_SEQUENCE_CUDA_ARCHITECTURE_SPECS),
        },
        "decision": {
            "threshold": "0.5",
            "long_rule": "probability_greater_than_or_equal_to_threshold",
            "quantity": "1",
            "decision_stride_sessions": 2,
            "entry_exit": "t_plus_1_open_to_t_plus_2_open",
        },
        "comparators": list(KIS_NAS_D1_SEQUENCE_COMPARATORS),
        "review_status": review_status,
        "execution_environment": _execution_environment_payload(),
        "artifact_policy": {
            "repo_storage_allowed": False,
            "raw_rows_persisted": False,
            "target_values_persisted": False,
            "prediction_values_persisted": False,
            "event_rows_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _summary_payload(
    *,
    evaluation_input: KisNasD1SealedEvaluationInput,
    precommit_hash: str,
    review_status: str,
    candidate_results: Sequence[KisNasD1SealedEvaluationResult],
    comparator_results: Sequence[KisNasD1SealedEvaluationResult],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_sealed_evaluation",
        "status": "completed",
        "precommit_hash": precommit_hash,
        "review_status": review_status,
        "execution_environment": _execution_environment_payload(),
        "source": _source_payload(evaluation_input),
        "candidates": [result.safe_payload() for result in candidate_results],
        "comparators": [result.safe_payload() for result in comparator_results],
        "artifact_policy": {
            "repo_storage_allowed": False,
            "raw_rows_persisted": False,
            "target_values_persisted": False,
            "prediction_values_persisted": False,
            "event_rows_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _failure_payload(
    *,
    evaluation_input: KisNasD1SealedEvaluationInput,
    precommit_hash: str,
    review_status: str,
    failure_class: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_sealed_evaluation_failure",
        "status": "failed_before_result_retention",
        "precommit_hash": precommit_hash,
        "review_status": review_status,
        "failure_class": failure_class,
        "execution_environment": _execution_environment_payload(),
        "source": _source_payload(evaluation_input),
        "artifact_policy": {
            "raw_rows_persisted": False,
            "target_values_persisted": False,
            "prediction_values_persisted": False,
            "event_rows_persisted": False,
        },
        "reporting": _reporting_payload(),
    }


def _source_payload(evaluation_input: KisNasD1SealedEvaluationInput) -> dict[str, object]:
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


def _breadth_source_payload(breadth_input: KisNasD1SequenceBreadthInput) -> dict[str, object]:
    return {
        "campaign_contract_hash": breadth_input.campaign_input.contract.contract_hash,
        "campaign_precommit_hash": breadth_input.campaign_precommit_hash,
        "development_input_hash": breadth_input.campaign_input.development_input_hash,
        "validation_input_hash": breadth_input.campaign_input.validation_input_hash,
        "symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
        "source_limitations": list(breadth_input.campaign_input.source_limitations),
        "standardizer_hashes": [
            breadth_input.standardizer(symbol).standardizer_hash
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        ],
    }


def _breadth_reporting_payload() -> dict[str, object]:
    return {
        "selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "replay_allowed": False,
        "pnl_materialized": False,
        "paper_trading_eligible": False,
    }


def _reporting_payload() -> dict[str, object]:
    return {
        "selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "paper_trading_eligible": False,
        "broker_submission_allowed": False,
        "candidate_ranking_allowed": False,
    }


def _execution_environment_payload() -> dict[str, str]:
    """Expose a source-safe container-marker observation, not a Compose attestation."""

    marker_present = _DOCKER_ENVIRONMENT_MARKER.is_file()
    return {
        "kind": "docker" if marker_present else "host",
        "detection": "dockerenv_marker_present" if marker_present else "dockerenv_marker_absent",
    }


def _prepare_output_dir(
    *,
    artifact_root: Path | str,
    repository: Path,
    run_label: str,
) -> Path:
    requested_root = Path(artifact_root).absolute()
    _reject_linked_path_components(requested_root)
    root = requested_root.resolve()
    _reject_repository_path(root, repository)
    _reject_repository_path(root, _MODULE_REPOSITORY_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    _require_external_output_path(root, repository)
    output_dir = root / KIS_NAS_D1_SEALED_EVALUATION_ID / run_label
    _require_external_output_path(output_dir, repository)
    if output_dir.exists():
        raise FileExistsError("NAS D1 sealed evaluation run label already exists")
    output_dir.mkdir(parents=True, exist_ok=False)
    _require_external_output_path(output_dir, repository)
    return output_dir


def _require_external_file(path: Path | str, repository: Path) -> Path:
    candidate = Path(path)
    _reject_linked_path_components(candidate)
    if not candidate.is_file():
        raise ValueError("NAS D1 sealed evaluation external file is invalid")
    resolved = candidate.resolve()
    _reject_repository_path(resolved, repository)
    _reject_repository_path(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _require_external_directory(path: Path | str, repository: Path) -> Path:
    candidate = Path(path)
    _reject_linked_path_components(candidate)
    if not candidate.is_dir():
        raise ValueError("NAS D1 sealed evaluation external directory is invalid")
    resolved = candidate.resolve()
    _reject_repository_path(resolved, repository)
    _reject_repository_path(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _reject_repository_path(path: Path, repository: Path) -> None:
    if not path.is_relative_to(repository):
        return
    docker_root = _DOCKER_ARTIFACT_ROOT.resolve()
    if (
        repository == _DOCKER_REPOSITORY_ROOT.resolve()
        and docker_root.is_mount()
        and path.is_relative_to(docker_root)
    ):
        return
    raise ValueError("NAS D1 sealed evaluation artifacts must stay outside the Git workspace")


def _require_external_output_path(path: Path, repository: Path) -> Path:
    _reject_linked_path_components(path)
    resolved = path.resolve()
    _reject_repository_path(resolved, repository)
    _reject_repository_path(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _reject_linked_path_components(path: Path) -> None:
    candidate = path.absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts:
        if part == candidate.anchor:
            continue
        current /= part
        if _is_link_or_junction(current):
            raise ValueError("NAS D1 sealed evaluation path cannot contain a symlink or junction")


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"NAS D1 sealed evaluation {label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"NAS D1 sealed evaluation {label} must be an object")
    return payload


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    _reject_linked_path_components(path.parent)
    if _is_link_or_junction(path):
        raise ValueError("NAS D1 sealed evaluation receipt path is invalid")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return _sha256_file(path)


def _assert_source_safe(payload: object) -> None:
    forbidden_keys = {
        "account",
        "account_number",
        "bar",
        "broker",
        "close_returns",
        "credential",
        "credentials",
        "event_rows",
        "feature_rows",
        "label",
        "labels",
        "order",
        "orders",
        "price",
        "prices",
        "prediction",
        "predictions",
        "probability",
        "probabilities",
        "raw_bars",
        "secret",
        "target",
        "targets",
    }
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key).lower() in forbidden_keys:
                raise ValueError("NAS D1 sealed evaluation receipt is not source-safe")
            _assert_source_safe(value)
    elif isinstance(payload, Sequence) and not isinstance(payload, str | bytes):
        for value in payload:
            _assert_source_safe(value)


def _event_transcript_hash(events: Sequence[Event]) -> str:
    payload = [event.to_record() for event in events]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _is_finite_decimal_text(value: object) -> bool:
    try:
        return isinstance(value, str) and Decimal(value).is_finite()
    except Exception:
        return False


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _validate_run_label(run_label: str) -> None:
    if (
        not isinstance(run_label, str)
        or not run_label
        or len(run_label) > 80
        or any(character not in _RUN_LABEL_CHARS for character in run_label)
    ):
        raise ValueError("NAS D1 sealed evaluation run label is invalid")


def _numpy():
    import numpy

    return numpy
