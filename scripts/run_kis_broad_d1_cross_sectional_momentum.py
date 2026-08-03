"""Run the frozen KIS broad-D1 cross-sectional CPU benchmark once.

The Data adapter is deliberately imported only at this runner boundary.  The
benchmark core itself remains a pure in-memory consumer with no provider,
credential, network, KIS, broker, or Paper route.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from thericher_v2.research.kis_broad_d1_cross_sectional_momentum import (
    KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ARTIFACT_ROOT,
    KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ID,
    KisBroadD1CrossSectionalMomentumInput,
    KisBroadD1CrossSectionalMomentumInputUnavailable,
    run_kis_broad_d1_cross_sectional_momentum,
    validate_kis_broad_d1_cross_sectional_momentum_artifact_root,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DATA_ADAPTER_MODULE = "thericher_v2.data.kis_broad_d1_cross_sectional_momentum_input"
_DATA_ADAPTER_BUILDER = "build_kis_broad_d1_cross_sectional_momentum_input"
_DATA_ADAPTER_UNAVAILABLE = "KisBroadD1CrossSectionalMomentumInputUnavailable"
_EXECUTION_PARITY_MODULE = "thericher_v2.execution.kis_broad_d1_cross_sectional_momentum_parity"
_EXECUTION_PARITY_BUILDER = "attest_broad_d1_cross_sectional_momentum_parity"
_REVIEW_STATUSES = (
    "not_required_before_outcome",
    "unsupported",
    "uncertain",
    "supported-with-limits",
    "review_unavailable",
)


def main(argv: Sequence[str] | None = None) -> None:
    """Reattach the named Data input and emit a source-safe external receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--materialization-receipt-path", type=Path, required=True)
    parser.add_argument("--geometry-audit-receipt-path", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ARTIFACT_ROOT,
    )
    parser.add_argument("--run-label", required=True)
    parser.add_argument(
        "--review-status",
        choices=_REVIEW_STATUSES,
        default="not_required_before_outcome",
    )
    arguments = parser.parse_args(argv)

    validate_kis_broad_d1_cross_sectional_momentum_artifact_root(
        arguments.artifact_root,
        repo_root=_REPOSITORY_ROOT,
    )
    try:
        source_input = _load_data_input(arguments)
    except KisBroadD1CrossSectionalMomentumInputUnavailable as error:
        result = run_kis_broad_d1_cross_sectional_momentum(
            source_input=None,
            input_unavailable_reason=error.code,
            artifact_root=arguments.artifact_root,
            run_label=arguments.run_label,
            review_status=arguments.review_status,
            repo_root=_REPOSITORY_ROOT,
        )
    except ModuleNotFoundError as error:
        if error.name != _DATA_ADAPTER_MODULE:
            raise
        result = run_kis_broad_d1_cross_sectional_momentum(
            source_input=None,
            input_unavailable_reason="data_adapter_unavailable",
            artifact_root=arguments.artifact_root,
            run_label=arguments.run_label,
            review_status=arguments.review_status,
            repo_root=_REPOSITORY_ROOT,
        )
    except AttributeError as error:
        if _DATA_ADAPTER_BUILDER not in str(error):
            raise
        result = run_kis_broad_d1_cross_sectional_momentum(
            source_input=None,
            input_unavailable_reason="data_adapter_contract_unavailable",
            artifact_root=arguments.artifact_root,
            run_label=arguments.run_label,
            review_status=arguments.review_status,
            repo_root=_REPOSITORY_ROOT,
        )
    else:
        execution_parity = _attest_execution_parity(source_input)
        result = run_kis_broad_d1_cross_sectional_momentum(
            source_input=source_input,
            execution_parity=execution_parity,
            artifact_root=arguments.artifact_root,
            run_label=arguments.run_label,
            review_status=arguments.review_status,
            repo_root=_REPOSITORY_ROOT,
        )
    print(
        json.dumps(
            {
                "campaign_id": KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ID,
                "campaign_contract_hash": result.campaign_contract_hash,
                "receipt_sha256": result.receipt_sha256,
                "status": result.status,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def _load_data_input(arguments: argparse.Namespace) -> KisBroadD1CrossSectionalMomentumInput:
    """Load only the predeclared Data adapter at the executable boundary."""

    adapter = importlib.import_module(_DATA_ADAPTER_MODULE)
    builder: Any = getattr(adapter, _DATA_ADAPTER_BUILDER)
    unavailable_type = getattr(adapter, _DATA_ADAPTER_UNAVAILABLE, None)
    try:
        data_input = builder(
            manifest_path=arguments.manifest_path,
            materialization_receipt_path=arguments.materialization_receipt_path,
            geometry_audit_receipt_path=arguments.geometry_audit_receipt_path,
            cache_root=arguments.cache_root,
            panel_root=arguments.panel_root,
            repo_root=_REPOSITORY_ROOT,
        )
    except Exception as error:
        if isinstance(unavailable_type, type) and isinstance(error, unavailable_type):
            code = getattr(error, "code", None)
            if isinstance(code, str):
                raise KisBroadD1CrossSectionalMomentumInputUnavailable(code) from error
        raise
    return _to_benchmark_input(data_input)


def _to_benchmark_input(data_input: Any) -> KisBroadD1CrossSectionalMomentumInput:
    """Convert the narrow Data-owned immutable adapter into the pure core input."""

    try:
        return KisBroadD1CrossSectionalMomentumInput(
            dataset_id=data_input.dataset_id,
            dataset_hash=data_input.dataset_hash,
            source_index_hash=data_input.source_index_hash,
            panel_manifest_sha256=data_input.manifest_sha256,
            materialization_receipt_sha256=data_input.materialization_receipt_sha256,
            geometry_audit_receipt_sha256=data_input.geometry_audit_receipt_sha256,
            geometry_audit_contract_sha256=data_input.geometry_audit_contract_sha256,
            geometry_audit_source_grid_sha256=data_input.geometry_audit_source_grid_sha256,
            geometry_audit_event_mask_sha256=data_input.geometry_audit_event_mask_sha256,
            target_key_set_hash=data_input.target_key_set_hash,
            full_target_count=data_input.full_target_count,
            coverage_eligible_target_count=data_input.coverage_eligible_target_count,
            raw_byte_attested_target_count=data_input.raw_byte_attested_target_count,
            grid_bars_by_target=data_input.grid_bars_by_target,
            terminal_execution_bars_by_target=data_input.terminal_execution_bars_by_target,
            event_availability_by_lookback=data_input.event_availability_by_lookback,
            limitations=data_input.limitations,
        )
    except AttributeError as error:
        raise TypeError("KIS broad D1 momentum Data adapter returned an invalid input") from error


def _attest_execution_parity(
    source_input: KisBroadD1CrossSectionalMomentumInput,
) -> dict[str, object]:
    """Attach the independent pure timing and cost-semantics attestation."""

    parity_module = importlib.import_module(_EXECUTION_PARITY_MODULE)
    attester: Any = getattr(parity_module, _EXECUTION_PARITY_BUILDER)
    target_key = min(source_input.grid_bars_by_target)
    attestation = attester(
        signal_bar=source_input.grid_bars_by_target[target_key][-1],
        execution_bar=source_input.terminal_execution_bars_by_target[target_key],
        next_observed_execution_bar=True,
        source_limitations=source_input.limitations,
        input_contract_ref=source_input.input_bar_hash,
    )
    payload: Any = attestation.safe_payload()
    if not isinstance(payload, dict):
        raise TypeError("KIS broad D1 momentum execution parity payload is invalid")
    return payload


if __name__ == "__main__":
    main()
