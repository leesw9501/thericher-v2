"""Pure offline QQQ target semantics for one verified D1 joint-event fold."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

from thericher_v2.kis_daily_joint_event_d1_materializer import (
    KIS_DAILY_JOINT_EVENT_D1_SYMBOLS,
    KisDailyJointEventD1Materializer,
    KisDailyJointEventD1Window,
    MaterializationPhase,
)
from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
)

KIS_DAILY_JOINT_EVENT_D1_TARGET_COST_SCHEMA_VERSION = 2
KIS_DAILY_JOINT_EVENT_D1_TARGET_COST_KIND = "kis_daily_joint_event_d1_target_cost_receipt"
KIS_DAILY_JOINT_EVENT_D1_TARGET_FORMULA_ID = (
    "qqq-next-open-to-following-open-after-cost-long-vs-flat-v2"
)
KIS_DAILY_JOINT_EVENT_D1_TARGET_SYMBOL = "QQQ"
KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL = Decimal("1")
KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL = Decimal("2")
KIS_DAILY_JOINT_EVENT_D1_TARGET_PRICE_QUANTUM = Decimal("0.0001")
KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE = "ROUND_HALF_EVEN"
KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION = 34

_BPS_SCALE = Decimal("10000")
_ALLOWED_RECEIPT_KEYS = frozenset(
    {
        "artifact_sha256",
        "candidate_selection_eligible",
        "catalog_dataset_hash",
        "catalog_index_hash",
        "credentials_persisted",
        "decision_end",
        "decision_index",
        "decision_start",
        "decimal_precision",
        "entry_index",
        "entry_start",
        "exit_index",
        "exit_start",
        "feature_end_index",
        "feature_row_count",
        "feature_start_index",
        "feature_values_persisted",
        "fee_bps_per_fill",
        "fold_input_identity",
        "formula_id",
        "kind",
        "materialized_window",
        "materializer_identity",
        "model_execution_eligible",
        "model_execution_review",
        "offline_only",
        "paper_decision_eligible",
        "parent_artifact_sha256",
        "parent_contract_identity",
        "phase",
        "predecessor_index",
        "price_quantum",
        "raw_market_data_persisted",
        "rounding_mode",
        "schema_version",
        "scope",
        "slippage_bps_per_fill",
        "source_fold_input",
        "source_materializer",
        "status",
        "target_cost_identity",
        "target_semantics",
        "target_symbol",
        "target_values_persisted",
    }
)


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1Target:
    """One in-memory QQQ long-versus-flat target for a materialized window."""

    phase: MaterializationPhase
    decision_index: int
    predecessor_index: int
    feature_start_index: int
    feature_end_index: int
    entry_index: int
    exit_index: int
    decision_start: datetime
    decision_end: datetime
    entry_start: datetime
    exit_start: datetime
    label: int
    target_cost_identity: str

    def __post_init__(self) -> None:
        if (
            self.phase not in {"development", "validation"}
            or type(self.decision_index) is not int
            or type(self.predecessor_index) is not int
            or type(self.feature_start_index) is not int
            or type(self.feature_end_index) is not int
            or type(self.entry_index) is not int
            or type(self.exit_index) is not int
            or self.predecessor_index != self.feature_start_index - 1
            or self.feature_end_index != self.decision_index
            or self.entry_index != self.decision_index + 1
            or self.exit_index != self.decision_index + 2
            or self.decision_start.tzinfo is None
            or self.decision_end.tzinfo is None
            or self.entry_start.tzinfo is None
            or self.exit_start.tzinfo is None
            or self.decision_end > self.entry_start
            or self.entry_start >= self.exit_start
            or type(self.label) is not int
            or self.label not in {0, 1}
        ):
            raise ValueError("joint D1 target is invalid")
        _require_sha256(self.target_cost_identity, "joint D1 target cost identity")


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1TargetCostAdapter:
    """A fixed-cost, non-executable target adapter for one verified materializer."""

    materializer: KisDailyJointEventD1Materializer

    def __post_init__(self) -> None:
        if not isinstance(self.materializer, KisDailyJointEventD1Materializer):
            raise ValueError("joint D1 target materializer is invalid")
        fold_input = self.materializer.fold_input
        if (
            fold_input.fold_id != "expanding-1"
            or not fold_input.reattested_against_parent
            or fold_input.model_execution_review
            != KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE
            or self.materializer.catalog_dataset_hash != fold_input.catalog_dataset_hash
            or self.materializer.catalog_index_hash != fold_input.catalog_index_hash
        ):
            raise ValueError("joint D1 target source lineage is invalid")
        _require_sha256(self.materializer.fold_artifact_sha256, "joint D1 target fold hash")
        _require_sha256(
            self.materializer.materializer_identity,
            "joint D1 target materializer identity",
        )

    @property
    def target_cost_identity(self) -> str:
        return _sha256_json(
            {
                "schema_version": KIS_DAILY_JOINT_EVENT_D1_TARGET_COST_SCHEMA_VERSION,
                "kind": KIS_DAILY_JOINT_EVENT_D1_TARGET_COST_KIND,
                "materializer_identity": self.materializer.materializer_identity,
                "formula_id": KIS_DAILY_JOINT_EVENT_D1_TARGET_FORMULA_ID,
                "target_symbol": KIS_DAILY_JOINT_EVENT_D1_TARGET_SYMBOL,
                "fee_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL),
                "slippage_bps_per_fill": str(
                    KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL
                ),
                "price_quantum": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_PRICE_QUANTUM),
                "rounding_mode": KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
                "decimal_precision": KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
            }
        )

    def derive(
        self,
        *,
        phase: MaterializationPhase,
        decision_index: int,
    ) -> KisDailyJointEventD1Target:
        """Reconstruct one eligible window and derive its in-memory binary target."""

        window = self.materializer.materialize(phase=phase, decision_index=decision_index)
        _validate_target_window(
            materializer=self.materializer,
            phase=phase,
            decision_index=decision_index,
            window=window,
        )
        target_references = window.target_references
        label = calculate_kis_daily_joint_event_d1_target_label(
            entry_open=target_references.entry_open_by_symbol[
                KIS_DAILY_JOINT_EVENT_D1_TARGET_SYMBOL
            ],
            exit_open=target_references.exit_open_by_symbol[
                KIS_DAILY_JOINT_EVENT_D1_TARGET_SYMBOL
            ],
        )
        return KisDailyJointEventD1Target(
            phase=phase,
            decision_index=window.decision_index,
            predecessor_index=window.predecessor_index,
            feature_start_index=window.feature_start_index,
            feature_end_index=window.feature_end_index,
            entry_index=target_references.entry_index,
            exit_index=target_references.exit_index,
            decision_start=window.decision_start,
            decision_end=window.decision_end,
            entry_start=target_references.entry_start,
            exit_start=target_references.exit_start,
            label=label,
            target_cost_identity=self.target_cost_identity,
        )

    def receipt_document(
        self,
        *,
        phase: MaterializationPhase,
        decision_index: int,
    ) -> dict[str, object]:
        target = self.derive(phase=phase, decision_index=decision_index)
        fold_input = self.materializer.fold_input
        document = {
            "schema_version": KIS_DAILY_JOINT_EVENT_D1_TARGET_COST_SCHEMA_VERSION,
            "kind": KIS_DAILY_JOINT_EVENT_D1_TARGET_COST_KIND,
            "status": "candidate",
            "source_fold_input": {
                "artifact_sha256": self.materializer.fold_artifact_sha256,
                "fold_input_identity": fold_input.fold_input_identity,
                "parent_artifact_sha256": fold_input.source_artifact_sha256,
                "parent_contract_identity": fold_input.source_contract_identity,
            },
            "source_materializer": {
                "materializer_identity": self.materializer.materializer_identity,
                "catalog_dataset_hash": self.materializer.catalog_dataset_hash,
                "catalog_index_hash": self.materializer.catalog_index_hash,
            },
            "target_semantics": {
                "formula_id": KIS_DAILY_JOINT_EVENT_D1_TARGET_FORMULA_ID,
                "target_symbol": KIS_DAILY_JOINT_EVENT_D1_TARGET_SYMBOL,
                "fee_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL),
                "slippage_bps_per_fill": str(
                    KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL
                ),
                "price_quantum": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_PRICE_QUANTUM),
                "rounding_mode": KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
                "decimal_precision": KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
            },
            "materialized_window": {
                "phase": target.phase,
                "decision_index": target.decision_index,
                "predecessor_index": target.predecessor_index,
                "feature_start_index": target.feature_start_index,
                "feature_end_index": target.feature_end_index,
                "entry_index": target.entry_index,
                "exit_index": target.exit_index,
                "feature_row_count": target.feature_end_index - target.feature_start_index + 1,
                "decision_start": target.decision_start.isoformat(),
                "decision_end": target.decision_end.isoformat(),
                "entry_start": target.entry_start.isoformat(),
                "exit_start": target.exit_start.isoformat(),
            },
            "scope": {
                "offline_only": True,
                "model_execution_eligible": False,
                "model_execution_review": fold_input.model_execution_review,
                "candidate_selection_eligible": False,
                "paper_decision_eligible": False,
                "raw_market_data_persisted": False,
                "feature_values_persisted": False,
                "target_values_persisted": False,
                "credentials_persisted": False,
            },
            "target_cost_identity": self.target_cost_identity,
        }
        _assert_source_safe(document)
        return document


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1TargetCostReceipt:
    path: Path
    content_hash: str
    adapter: KisDailyJointEventD1TargetCostAdapter
    phase: MaterializationPhase
    decision_index: int


def build_kis_daily_joint_event_d1_target_cost_adapter(
    *,
    materializer: KisDailyJointEventD1Materializer,
) -> KisDailyJointEventD1TargetCostAdapter:
    """Bind the fixed QQQ target semantics to one verified materializer."""

    return KisDailyJointEventD1TargetCostAdapter(materializer=materializer)


def calculate_kis_daily_joint_event_d1_target_label(
    *,
    entry_open: Decimal,
    exit_open: Decimal,
) -> int:
    """Mirror fixed local-paper two-fill economics without a replay or broker."""

    with localcontext() as context:
        context.prec = KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        entry = _positive_decimal(entry_open, "joint D1 target entry open")
        exit_value = _positive_decimal(exit_open, "joint D1 target exit open")
        entry_fill = _quantize(
            entry
            * (
                Decimal("1")
                + KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL / _BPS_SCALE
            )
        )
        exit_fill = _quantize(
            exit_value
            * (
                Decimal("1")
                - KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL / _BPS_SCALE
            )
        )
        entry_fee = _quantize(
            entry_fill * KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL / _BPS_SCALE
        )
        exit_fee = _quantize(
            exit_fill * KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL / _BPS_SCALE
        )
        return int(exit_fill - exit_fee > entry_fill + entry_fee)


def write_kis_daily_joint_event_d1_target_cost_receipt(
    *,
    destination: Path,
    adapter: KisDailyJointEventD1TargetCostAdapter,
    phase: MaterializationPhase,
    decision_index: int,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path,
) -> KisDailyJointEventD1TargetCostReceipt:
    """Persist source-safe target semantics without writing target values."""

    if not isinstance(adapter, KisDailyJointEventD1TargetCostAdapter):
        raise ValueError("joint D1 target adapter is invalid")
    path = _external_artifact_destination(
        destination=destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    document = adapter.receipt_document(phase=phase, decision_index=decision_index)
    encoded = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    content_hash = _sha256(encoded)
    with path.open("xb") as handle:
        handle.write(encoded)
    return KisDailyJointEventD1TargetCostReceipt(
        path=path,
        content_hash=content_hash,
        adapter=adapter,
        phase=phase,
        decision_index=decision_index,
    )


def _validate_target_window(
    *,
    materializer: KisDailyJointEventD1Materializer,
    phase: MaterializationPhase,
    decision_index: int,
    window: KisDailyJointEventD1Window,
) -> None:
    if not isinstance(window, KisDailyJointEventD1Window):
        raise ValueError("joint D1 target window is invalid")
    if decision_index not in materializer.eligible_decision_indices(phase):
        raise ValueError("joint D1 target decision index is not sparse-eligible")
    spec = materializer.fold_input.spec
    predecessor_index = decision_index - spec.feature_session_count
    feature_start_index = predecessor_index + 1
    exit_index = decision_index + spec.label_horizon_session_count
    if (
        window.phase != phase
        or window.decision_index != decision_index
        or window.predecessor_index != predecessor_index
        or window.feature_start_index != feature_start_index
        or window.feature_end_index != decision_index
        or len(window.feature_rows) != spec.feature_session_count
        or window.target_references.entry_index != decision_index + 1
        or window.target_references.exit_index != exit_index
        or window.decision_end > window.target_references.entry_start
        or window.target_references.entry_start >= window.target_references.exit_start
        or tuple(window.target_references.entry_open_by_symbol)
        != KIS_DAILY_JOINT_EVENT_D1_SYMBOLS
        or tuple(window.target_references.exit_open_by_symbol)
        != KIS_DAILY_JOINT_EVENT_D1_SYMBOLS
    ):
        raise ValueError("joint D1 target window geometry is invalid")
    _positive_decimal(
        window.target_references.entry_open_by_symbol[KIS_DAILY_JOINT_EVENT_D1_TARGET_SYMBOL],
        "joint D1 target entry open",
    )
    _positive_decimal(
        window.target_references.exit_open_by_symbol[KIS_DAILY_JOINT_EVENT_D1_TARGET_SYMBOL],
        "joint D1 target exit open",
    )


def _external_artifact_destination(
    *,
    destination: Path,
    artifact_root: Path,
    repo_root: Path,
) -> Path:
    resolved_repo = Path(repo_root).resolve()
    resolved_root = Path(artifact_root).resolve()
    if resolved_root == resolved_repo or resolved_root.is_relative_to(resolved_repo):
        raise ValueError("joint D1 target artifacts must stay outside the Git workspace")
    destination_path = Path(destination)
    if destination_path.is_symlink():
        raise ValueError("joint D1 target artifact destination is invalid")
    resolved_destination = destination_path.resolve()
    if not resolved_destination.is_relative_to(resolved_root):
        raise ValueError("joint D1 target artifact must stay under the artifact root")
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    if not resolved_destination.parent.resolve().is_relative_to(resolved_root):
        raise ValueError("joint D1 target artifact destination is invalid")
    return resolved_destination


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or key not in _ALLOWED_RECEIPT_KEYS:
                raise ValueError(f"joint D1 target receipt key is not source-safe: {key}")
            _assert_source_safe(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_source_safe(nested)


def _positive_decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{label} is invalid")
    return value


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(
        KIS_DAILY_JOINT_EVENT_D1_TARGET_PRICE_QUANTUM,
        rounding=ROUND_HALF_EVEN,
    )


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{label} must use the sha256 prefix")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        raise ValueError(f"{label} must contain a SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as error:
        raise ValueError(f"{label} must contain a SHA-256 digest") from error
    return value


def _sha256_json(value: object) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()
