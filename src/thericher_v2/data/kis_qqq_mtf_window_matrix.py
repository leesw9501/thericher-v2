"""Source-local canonical causal-window matrix for the frozen QQQ MTF input."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_intraday import KisPaperIntradayFeatureInput
from thericher_v2.data.kis_qqq_mtf_resampling_mechanics import (
    KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
    KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES,
)
from thericher_v2.data.kis_qqq_mtf_window_feasibility import (
    KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID,
    KisQqqMtfMechanicsReceipt,
    KisQqqMtfWindowFeasibilityReceipt,
    QqqMtfWindowGeometry,
    kis_qqq_mtf_window_cutoff,
    load_kis_qqq_mtf_mechanics_receipt,
    load_kis_qqq_mtf_window_feasibility_receipt,
    prepare_kis_qqq_mtf_window_input,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow, resample_session_bars
from thericher_v2.models.current_source_opportunity_eligibility import (
    build_causal_bar_source_contract,
)
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory
from thericher_v2.research.causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
    CausalMtfWindowProfile,
    assess_profile_feasibility,
)
from thericher_v2.research.kis_mtf_profiled_feature_input_preflight import (
    completed_causal_minute_prefix,
    resample_completed_causal_prefix,
)

KIS_QQQ_MTF_WINDOW_MATRIX_ID = "source-local-qqq-mtf-window-matrix-v1"

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SHA256_REFERENCE = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_RunStatus = Literal["complete", "input_unavailable"]
_InputUnavailableReason = Literal[
    "invalid_catalog",
    "insufficient_complete_regular_sessions",
    "mechanics_source_binding_mismatch",
    "baseline_source_binding_mismatch",
    "baseline_geometry_mismatch",
    "incomplete_or_invalid_causal_window",
]


@dataclass(frozen=True)
class QqqMtfWindowMatrixProfileGeometry:
    """Aggregate target-free causal geometry for one frozen matrix profile."""

    profile_id: str
    geometry: tuple[QqqMtfWindowGeometry, ...]
    profile_commitment: str

    def __post_init__(self) -> None:
        profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile(self.profile_id)
        geometry = tuple(self.geometry)
        if (
            tuple(item.timeframe for item in geometry) != KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
            or any(item.lookback != profile.lookbacks[item.timeframe] for item in geometry)
            or _SHA256_REFERENCE.fullmatch(self.profile_commitment) is None
        ):
            raise ValueError("QQQ MTF window-matrix profile geometry is invalid")
        object.__setattr__(self, "geometry", geometry)


@dataclass(frozen=True)
class KisQqqMtfWindowMatrixRun:
    """Immutable source-safe result for one canonical observation-window matrix."""

    run_label: str
    status: _RunStatus
    contract_hash: str
    mechanics_contract_hash: str
    baseline_contract_hash: str
    precommit_path: Path
    summary_path: Path
    eligible_session_count: int
    input_unavailable_reason: _InputUnavailableReason | None
    profiles: tuple[QqqMtfWindowMatrixProfileGeometry, ...]


def run_kis_qqq_mtf_window_matrix(
    catalog: CatalogedBars,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    baseline_receipt: KisQqqMtfWindowFeasibilityReceipt,
    artifact_root: Path,
    run_label: str,
    repo_root: Path = _REPOSITORY_ROOT,
) -> KisQqqMtfWindowMatrixRun:
    """Attest the canonical six-profile matrix without creating any target or model."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("QQQ MTF window matrix requires CatalogedBars")
    if not isinstance(mechanics_receipt, KisQqqMtfMechanicsReceipt):
        raise TypeError("QQQ MTF window matrix requires a mechanics receipt")
    if not isinstance(baseline_receipt, KisQqqMtfWindowFeasibilityReceipt):
        raise TypeError("QQQ MTF window matrix requires a baseline-window receipt")
    _validate_run_label(run_label)
    mechanics_receipt, baseline_receipt = _reattest_parent_receipts(
        mechanics_receipt,
        baseline_receipt,
        repo_root=Path(repo_root),
    )
    run_directory = _new_run_directory(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        run_label=run_label,
    )
    try:
        input_data = _prepare_matrix_input(catalog, mechanics_receipt=mechanics_receipt)
        _validate_baseline_source_binding(
            input_data,
            mechanics_receipt=mechanics_receipt,
            baseline_receipt=baseline_receipt,
        )
    except _InputUnavailable as error:
        return _write_input_unavailable_run(
            catalog=catalog,
            mechanics_receipt=mechanics_receipt,
            baseline_receipt=baseline_receipt,
            run_directory=run_directory,
            run_label=run_label,
            reason=error.reason,
        )

    contract = _contract_payload(
        input_data,
        mechanics_receipt=mechanics_receipt,
        baseline_receipt=baseline_receipt,
    )
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = run_directory / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_qqq_mtf_window_matrix_precommit",
            "status": "frozen_before_materialization",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(run_directory),
        },
    )
    try:
        profiles = _materialize_matrix(input_data)
        baseline_profile = next(
            profile for profile in profiles if profile.profile_id == "kis_baseline"
        )
        if baseline_profile.geometry != baseline_receipt.geometry:
            raise _InputUnavailable("baseline_geometry_mismatch")
    except _InputUnavailable as error:
        status: _RunStatus = "input_unavailable"
        reason: _InputUnavailableReason | None = error.reason
        eligible_session_count = 0
        profiles = _empty_profiles()
    else:
        status = "complete"
        reason = None
        eligible_session_count = len(input_data.session_dates)

    summary_path = run_directory / "summary.json"
    _write_json(
        summary_path,
        _summary_payload(
            input_data=input_data,
            mechanics_receipt=mechanics_receipt,
            baseline_receipt=baseline_receipt,
            run_label=run_label,
            status=status,
            contract_hash=contract_hash,
            eligible_session_count=eligible_session_count,
            input_unavailable_reason=reason,
            profiles=profiles,
            artifact_directory=run_directory,
        ),
    )
    return KisQqqMtfWindowMatrixRun(
        run_label=run_label,
        status=status,
        contract_hash=contract_hash,
        mechanics_contract_hash=mechanics_receipt.contract_hash,
        baseline_contract_hash=baseline_receipt.contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        eligible_session_count=eligible_session_count,
        input_unavailable_reason=reason,
        profiles=profiles,
    )


def _reattest_parent_receipts(
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    baseline_receipt: KisQqqMtfWindowFeasibilityReceipt,
    *,
    repo_root: Path,
) -> tuple[KisQqqMtfMechanicsReceipt, KisQqqMtfWindowFeasibilityReceipt]:
    reattached_mechanics = load_kis_qqq_mtf_mechanics_receipt(
        precommit_path=mechanics_receipt.precommit_path,
        summary_path=mechanics_receipt.summary_path,
        repo_root=repo_root,
    )
    reattached_baseline = load_kis_qqq_mtf_window_feasibility_receipt(
        precommit_path=baseline_receipt.precommit_path,
        summary_path=baseline_receipt.summary_path,
        repo_root=repo_root,
    )
    if reattached_mechanics != mechanics_receipt or reattached_baseline != baseline_receipt:
        raise ValueError("QQQ MTF window matrix requires externally reattested parent receipts")
    return reattached_mechanics, reattached_baseline


def _prepare_matrix_input(
    catalog: CatalogedBars,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
) -> KisPaperIntradayFeatureInput:
    try:
        return prepare_kis_qqq_mtf_window_input(catalog, mechanics_receipt=mechanics_receipt)
    except ValueError as error:
        reason = str(error)
        if reason in {
            "invalid_catalog",
            "insufficient_complete_regular_sessions",
            "mechanics_source_binding_mismatch",
        }:
            raise _InputUnavailable(reason) from error
        raise _InputUnavailable("invalid_catalog") from error


def _validate_baseline_source_binding(
    input_data: KisPaperIntradayFeatureInput,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    baseline_receipt: KisQqqMtfWindowFeasibilityReceipt,
) -> None:
    selected_session_dates_sha256 = "sha256:" + _sha256_json(
        [session_date.isoformat() for session_date in input_data.session_dates]
    )
    causal_completed_m1_prefix_commitment = build_causal_bar_source_contract(
        input_data.catalog.bars,
        contract_id="kis-qqq-mtf-resampling-completed-m1-prefix-v1",
        as_of=input_data.session_windows[-1].close_ts,
    ).contract_hash
    if (
        baseline_receipt.mechanics_contract_hash != mechanics_receipt.contract_hash
        or baseline_receipt.source_dataset_id != input_data.catalog.dataset_id
        or baseline_receipt.source_dataset_hash != input_data.catalog.dataset_hash
        or baseline_receipt.source_input_id != input_data.input_id
        or baseline_receipt.source_input_hash != input_data.input_hash
        or baseline_receipt.selected_session_dates_sha256 != selected_session_dates_sha256
        or baseline_receipt.causal_completed_m1_prefix_commitment
        != causal_completed_m1_prefix_commitment
        or baseline_receipt.calendar_scope != mechanics_receipt.calendar_scope
        or baseline_receipt.session_count != len(input_data.session_dates)
        or baseline_receipt.profile_catalog_sha256
        != CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256
    ):
        raise _InputUnavailable("baseline_source_binding_mismatch")


def _contract_payload(
    input_data: KisPaperIntradayFeatureInput,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    baseline_receipt: KisQqqMtfWindowFeasibilityReceipt,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "matrix_id": KIS_QQQ_MTF_WINDOW_MATRIX_ID,
        "parent_receipts": {
            "mechanics": {
                "mechanics_id": KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
                "contract_hash": mechanics_receipt.contract_hash,
            },
            "baseline_window": {
                "feasibility_id": KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID,
                "contract_hash": baseline_receipt.contract_hash,
            },
        },
        "source": {
            "dataset_id": input_data.catalog.dataset_id,
            "dataset_hash": input_data.catalog.dataset_hash,
            "input_id": input_data.input_id,
            "input_hash": input_data.input_hash,
            "session_count": len(input_data.session_dates),
            "calendar_scope": mechanics_receipt.calendar_scope,
            "selected_session_dates_sha256": mechanics_receipt.selected_session_dates_sha256,
            "causal_completed_m1_prefix_commitment": (
                mechanics_receipt.causal_completed_m1_prefix_commitment
            ),
        },
        "profile_catalog": {
            "catalog_sha256": CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256,
            "ordered_profiles": [_profile_contract_payload(profile) for profile in _profiles()],
            "cutoff": "15:30 America/New_York",
            "all_selected_window_ends_equal_cutoff": True,
        },
        "limits": _limits_payload(),
    }


def _materialize_matrix(
    input_data: KisPaperIntradayFeatureInput,
) -> tuple[QqqMtfWindowMatrixProfileGeometry, ...]:
    profiles = _profiles()
    completed_counts = {
        profile.profile_id: {timeframe: 0 for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES}
        for profile in profiles
    }
    terminal_counts = {
        profile.profile_id: {timeframe: 0 for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES}
        for profile in profiles
    }
    records = {
        profile.profile_id: {timeframe: [] for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES}
        for profile in profiles
    }
    for session in input_data.session_windows:
        cutoff = kis_qqq_mtf_window_cutoff(session.open_ts)
        if cutoff <= session.open_ts or cutoff >= session.close_ts:
            raise _InputUnavailable("incomplete_or_invalid_causal_window")
        try:
            prefix = completed_causal_minute_prefix(
                input_data.catalog.bars,
                expected_symbol="QQQ",
                session=session,
                cutoff=cutoff,
            )
            bars_by_timeframe = resample_completed_causal_prefix(
                prefix,
                session=session,
                cutoff=cutoff,
            )
            terminal_results = {
                timeframe: _resample_terminal_bucket(prefix, timeframe=timeframe, session=session)
                for timeframe in (Timeframe.H1, Timeframe.H3)
            }
        except ValueError as error:
            raise _InputUnavailable("incomplete_or_invalid_causal_window") from error
        prefix_commitment = build_causal_bar_source_contract(
            prefix,
            contract_id="kis-qqq-mtf-window-feasibility-session-prefix-v1",
            as_of=cutoff,
        ).contract_hash
        for profile in profiles:
            try:
                feasibility = assess_profile_feasibility(
                    catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
                    profile_id=profile.profile_id,
                    bars_by_timeframe=bars_by_timeframe,
                    cutoff=cutoff,
                )
            except ValueError as error:
                raise _InputUnavailable("incomplete_or_invalid_causal_window") from error
            if any(sequence.end_ts != cutoff for sequence in feasibility.window.windows.values()):
                raise _InputUnavailable("incomplete_or_invalid_causal_window")
            for timeframe, sequence in feasibility.window.windows.items():
                completed_counts[profile.profile_id][timeframe] += len(sequence.bars)
                records[profile.profile_id][timeframe].append(
                    {
                        "timeframe": timeframe.value,
                        "cutoff": cutoff.isoformat(),
                        "prefix_commitment": prefix_commitment,
                        "window_bar_count": len(sequence.bars),
                        "window_end": sequence.end_ts.isoformat(),
                    }
                )
            for timeframe in (Timeframe.H1, Timeframe.H3):
                if terminal_results[timeframe] != (cutoff,):
                    raise _InputUnavailable("incomplete_or_invalid_causal_window")
                terminal_counts[profile.profile_id][timeframe] += 1

    return tuple(
        _profile_geometry(
            profile,
            geometry=tuple(
                QqqMtfWindowGeometry(
                    timeframe=timeframe,
                    lookback=profile.lookbacks[timeframe],
                    completed_window_bar_count=completed_counts[profile.profile_id][timeframe],
                    terminal_partial_exclusion_count=terminal_counts[profile.profile_id][timeframe],
                    causal_window_digest="sha256:"
                    + _sha256_json(records[profile.profile_id][timeframe]),
                )
                for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
            ),
        )
        for profile in profiles
    )


def _resample_terminal_bucket(
    prefix: tuple[Bar, ...],
    *,
    timeframe: Timeframe,
    session: SessionWindow,
) -> tuple[datetime, ...]:
    return resample_session_bars(prefix, timeframe, session=session).skipped_bucket_starts


def _profile_geometry(
    profile: CausalMtfWindowProfile,
    *,
    geometry: tuple[QqqMtfWindowGeometry, ...],
) -> QqqMtfWindowMatrixProfileGeometry:
    return QqqMtfWindowMatrixProfileGeometry(
        profile_id=profile.profile_id,
        geometry=geometry,
        profile_commitment="sha256:"
        + _sha256_json(
            {
                "profile_id": profile.profile_id,
                "lookbacks": _profile_lookbacks_payload(profile),
                "geometry": [_geometry_payload(item) for item in geometry],
            }
        ),
    )


def _empty_profiles() -> tuple[QqqMtfWindowMatrixProfileGeometry, ...]:
    return tuple(
        _profile_geometry(
            profile,
            geometry=tuple(
                QqqMtfWindowGeometry(
                    timeframe=timeframe,
                    lookback=profile.lookbacks[timeframe],
                    completed_window_bar_count=0,
                    terminal_partial_exclusion_count=0,
                    causal_window_digest="sha256:" + _sha256_json([]),
                )
                for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
            ),
        )
        for profile in _profiles()
    )


def _write_input_unavailable_run(
    *,
    catalog: CatalogedBars,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    baseline_receipt: KisQqqMtfWindowFeasibilityReceipt,
    run_directory: Path,
    run_label: str,
    reason: _InputUnavailableReason,
) -> KisQqqMtfWindowMatrixRun:
    contract = _input_unavailable_contract(
        catalog,
        mechanics_receipt=mechanics_receipt,
        baseline_receipt=baseline_receipt,
        reason=reason,
    )
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = run_directory / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_qqq_mtf_window_matrix_precommit",
            "status": "frozen_input_unavailable",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(run_directory),
        },
    )
    profiles = _empty_profiles()
    summary_path = run_directory / "summary.json"
    _write_json(
        summary_path,
        _input_unavailable_summary_payload(
            catalog=catalog,
            mechanics_receipt=mechanics_receipt,
            baseline_receipt=baseline_receipt,
            run_label=run_label,
            contract_hash=contract_hash,
            reason=reason,
            profiles=profiles,
            artifact_directory=run_directory,
        ),
    )
    return KisQqqMtfWindowMatrixRun(
        run_label=run_label,
        status="input_unavailable",
        contract_hash=contract_hash,
        mechanics_contract_hash=mechanics_receipt.contract_hash,
        baseline_contract_hash=baseline_receipt.contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        eligible_session_count=0,
        input_unavailable_reason=reason,
        profiles=profiles,
    )


def _input_unavailable_contract(
    catalog: CatalogedBars,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    baseline_receipt: KisQqqMtfWindowFeasibilityReceipt,
    reason: _InputUnavailableReason,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "matrix_id": KIS_QQQ_MTF_WINDOW_MATRIX_ID,
        "parent_receipts": {
            "mechanics": {
                "mechanics_id": KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
                "contract_hash": mechanics_receipt.contract_hash,
            },
            "baseline_window": {
                "feasibility_id": KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID,
                "contract_hash": baseline_receipt.contract_hash,
            },
        },
        "source": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "input_id": None,
            "input_hash": None,
            "session_count": 0,
            "calendar_scope": mechanics_receipt.calendar_scope,
            "selected_session_dates_sha256": None,
            "causal_completed_m1_prefix_commitment": None,
        },
        "profile_catalog": {
            "catalog_sha256": CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256,
            "ordered_profiles": [_profile_contract_payload(profile) for profile in _profiles()],
            "cutoff": "15:30 America/New_York",
            "all_selected_window_ends_equal_cutoff": False,
        },
        "input_unavailable_reason": reason,
        "limits": _limits_payload(),
    }


def _summary_payload(
    *,
    input_data: KisPaperIntradayFeatureInput,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    baseline_receipt: KisQqqMtfWindowFeasibilityReceipt,
    run_label: str,
    status: _RunStatus,
    contract_hash: str,
    eligible_session_count: int,
    input_unavailable_reason: _InputUnavailableReason | None,
    profiles: tuple[QqqMtfWindowMatrixProfileGeometry, ...],
    artifact_directory: Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_qqq_mtf_window_matrix_summary",
        "status": status,
        "mode": "offline_existing_local_catalog_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source_mechanics_contract_hash": mechanics_receipt.contract_hash,
        "source_baseline_window_contract_hash": baseline_receipt.contract_hash,
        "source": {
            "dataset_id": input_data.catalog.dataset_id,
            "dataset_hash": input_data.catalog.dataset_hash,
            "input_id": input_data.input_id,
            "input_hash": input_data.input_hash,
            "session_count": len(input_data.session_dates),
        },
        "profile_catalog": _profile_catalog_summary_payload(),
        "eligible_session_count": eligible_session_count,
        "input_unavailable_reason": input_unavailable_reason,
        "profiles": [_profile_summary_payload(profile) for profile in profiles],
        "limits": _limits_payload(),
        "artifact_policy": _artifact_policy(artifact_directory),
        "claim": _claim_for_status(status),
    }


def _input_unavailable_summary_payload(
    *,
    catalog: CatalogedBars,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    baseline_receipt: KisQqqMtfWindowFeasibilityReceipt,
    run_label: str,
    contract_hash: str,
    reason: _InputUnavailableReason,
    profiles: tuple[QqqMtfWindowMatrixProfileGeometry, ...],
    artifact_directory: Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_qqq_mtf_window_matrix_summary",
        "status": "input_unavailable",
        "mode": "offline_existing_local_catalog_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source_mechanics_contract_hash": mechanics_receipt.contract_hash,
        "source_baseline_window_contract_hash": baseline_receipt.contract_hash,
        "source": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "input_id": None,
            "input_hash": None,
            "session_count": 0,
        },
        "profile_catalog": _profile_catalog_summary_payload(),
        "eligible_session_count": 0,
        "input_unavailable_reason": reason,
        "profiles": [_profile_summary_payload(profile) for profile in profiles],
        "limits": _limits_payload(),
        "artifact_policy": _artifact_policy(artifact_directory),
        "claim": _claim_for_status("input_unavailable"),
    }


def _profiles() -> tuple[CausalMtfWindowProfile, ...]:
    return CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profiles


def _profile_contract_payload(profile: CausalMtfWindowProfile) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "lookbacks": _profile_lookbacks_payload(profile),
    }


def _profile_catalog_summary_payload() -> dict[str, object]:
    return {
        "catalog_sha256": CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256,
        "ordered_profiles": [_profile_contract_payload(profile) for profile in _profiles()],
        "cutoff": "15:30 America/New_York",
    }


def _profile_lookbacks_payload(profile: CausalMtfWindowProfile) -> dict[str, int]:
    return {timeframe.value: lookback for timeframe, lookback in profile.lookbacks.items()}


def _profile_summary_payload(value: QqqMtfWindowMatrixProfileGeometry) -> dict[str, object]:
    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile(value.profile_id)
    return {
        "profile_id": value.profile_id,
        "lookbacks": _profile_lookbacks_payload(profile),
        "geometry": [_geometry_payload(item) for item in value.geometry],
        "profile_commitment": value.profile_commitment,
    }


def _geometry_payload(value: QqqMtfWindowGeometry) -> dict[str, object]:
    return {
        "timeframe": value.timeframe.value,
        "lookback": value.lookback,
        "completed_window_bar_count": value.completed_window_bar_count,
        "terminal_partial_exclusion_count": value.terminal_partial_exclusion_count,
        "causal_window_digest": value.causal_window_digest,
    }


def _limits_payload() -> dict[str, object]:
    return {
        "decision_time_availability": "not_observed",
        "provider_finality": "not_observed",
        "predictive_campaign_allowed": False,
        "target_or_decision_created": False,
        "local_paper_input_allowed": False,
        "pnl_or_performance_created": False,
        "gpu_eligible": False,
    }


def _artifact_policy(artifact_directory: Path) -> dict[str, object]:
    return {
        "root": str(artifact_directory.parents[2]),
        "repo_storage_allowed": False,
        "raw_market_data_written": False,
        "raw_price_values_retained": False,
        "credential_read": False,
        "network_called": False,
        "broker_called": False,
    }


def _claim_for_status(status: _RunStatus) -> str:
    if status == "complete":
        return (
            "target-free causal window-matrix geometry only; it does not establish a strategy, "
            "prediction, profitability, model selection, ensemble, GPU eligibility, Paper input, "
            "or broker action"
        )
    if status == "input_unavailable":
        return (
            "source-local causal window-matrix input was unavailable or invalid before any model, "
            "target, Paper input, or broker claim"
        )
    raise ValueError(f"unsupported QQQ MTF window-matrix status: {status}")


def _new_run_directory(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    parent = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "data",
        KIS_QQQ_MTF_WINDOW_MATRIX_ID,
    )
    if (parent / run_label).exists():
        raise FileExistsError(
            f"QQQ MTF window-matrix artifact already exists: {parent / run_label}"
        )
    return ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "data",
        KIS_QQQ_MTF_WINDOW_MATRIX_ID,
        run_label,
    )


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class _InputUnavailable(ValueError):
    def __init__(self, reason: _InputUnavailableReason) -> None:
        self.reason = reason
        super().__init__(reason)
