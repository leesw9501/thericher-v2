"""Run one offline KIS broad-D1 invariant candle representation preflight."""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from thericher_v2.research.kis_broad_d1_invariant_candle_representation_cpu_preflight import (
    KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ARTIFACT_ROOT,
    KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ID,
    KisBroadD1InvariantCandleRepresentationInput,
    run_kis_broad_d1_invariant_candle_representation_cpu_preflight,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DATA_ADAPTER_MODULE = "thericher_v2.data.kis_broad_d1_cross_sectional_momentum_input"
_DATA_ADAPTER_BUILDER = "build_kis_broad_d1_cross_sectional_momentum_input"
_DATA_ADAPTER_UNAVAILABLE = "KisBroadD1CrossSectionalMomentumInputUnavailable"

if _REPOSITORY_ROOT == Path("/app"):
    _DEFAULT_CACHE_ROOT = Path("/app/market_data/us_equities/kis_paper_private/daily-nas-broad/v1")
    _DEFAULT_PANEL_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/daily-nas-broad-panel/v1"
    )
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\daily-nas-broad\v1")
    _DEFAULT_PANEL_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\daily-nas-broad-panel\v1"
    )
    _DEFAULT_ARTIFACT_ROOT = (
        KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ARTIFACT_ROOT
    )


class _AdapterInputUnavailable(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def main(argv: Sequence[str] | None = None) -> int:
    """Attach the named Data input and emit only a source-safe receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--materialization-receipt-path", type=Path, required=True)
    parser.add_argument("--geometry-audit-receipt-path", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--panel-root", type=Path, default=_DEFAULT_PANEL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-label", required=True)
    arguments = parser.parse_args(argv)
    try:
        source_input = _load_data_input(arguments)
    except _AdapterInputUnavailable as error:
        result = run_kis_broad_d1_invariant_candle_representation_cpu_preflight(
            source_input=None,
            input_unavailable_reason=error.code,
            artifact_root=arguments.artifact_root,
            run_label=arguments.run_label,
            repo_root=_REPOSITORY_ROOT,
        )
    else:
        result = run_kis_broad_d1_invariant_candle_representation_cpu_preflight(
            source_input=source_input,
            artifact_root=arguments.artifact_root,
            run_label=arguments.run_label,
            repo_root=_REPOSITORY_ROOT,
        )
    print(
        json.dumps(
            {
                "kind": KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ID,
                "receipt_sha256": result.receipt_sha256,
                "status": result.status,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


def _load_data_input(
    arguments: argparse.Namespace,
) -> KisBroadD1InvariantCandleRepresentationInput:
    """Call the Data-owned immutable loader only at this executable boundary."""

    try:
        adapter = importlib.import_module(_DATA_ADAPTER_MODULE)
        builder: Any = getattr(adapter, _DATA_ADAPTER_BUILDER)
        unavailable_type = getattr(adapter, _DATA_ADAPTER_UNAVAILABLE)
    except (AttributeError, ModuleNotFoundError) as error:
        raise _AdapterInputUnavailable("data_adapter_unavailable") from error
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
            code = _adapter_unavailable_code(getattr(error, "code", None))
            raise _AdapterInputUnavailable(code) from error
        if isinstance(error, (OSError, ValueError)):
            raise _AdapterInputUnavailable("source_drift") from error
        raise
    return _to_preflight_input(data_input)


def _to_preflight_input(value: Any) -> KisBroadD1InvariantCandleRepresentationInput:
    try:
        return KisBroadD1InvariantCandleRepresentationInput(
            dataset_id=value.dataset_id,
            dataset_hash=value.dataset_hash,
            manifest_sha256=value.manifest_sha256,
            materialization_receipt_sha256=value.materialization_receipt_sha256,
            source_index_hash=value.source_index_hash,
            target_key_set_hash=value.target_key_set_hash,
            geometry_audit_receipt_sha256=value.geometry_audit_receipt_sha256,
            geometry_audit_contract_sha256=value.geometry_audit_contract_sha256,
            geometry_audit_source_grid_sha256=value.geometry_audit_source_grid_sha256,
            geometry_audit_event_mask_sha256=value.geometry_audit_event_mask_sha256,
            full_target_count=value.full_target_count,
            coverage_eligible_target_count=value.coverage_eligible_target_count,
            raw_byte_attested_target_count=value.raw_byte_attested_target_count,
            selected_target_keys=value.selected_target_keys,
            decision_session_grid=value.decision_session_grid,
            terminal_execution_session=value.terminal_execution_session,
            grid_bars_by_target=value.grid_bars_by_target,
            terminal_execution_bars_by_target=value.terminal_execution_bars_by_target,
            range_event_flags_by_target=value.range_event_flags_by_target,
            limitations=value.limitations,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise _AdapterInputUnavailable("geometry_audit_mismatch") from error


def _adapter_unavailable_code(value: object) -> str:
    return {
        "geometry_audit_mismatch": "geometry_audit_mismatch",
        "insufficient_coverage": "insufficient_coverage",
        "insufficient_eligible_symbols": "insufficient_eligible_symbols",
        "malformed_or_changed_source": "source_drift",
    }.get(value, "source_drift")


if __name__ == "__main__":
    raise SystemExit(main())
