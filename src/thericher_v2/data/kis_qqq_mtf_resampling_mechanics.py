"""Source-local mechanics attestation for QQQ/NAS multi-timeframe inputs.

The module consumes an already verified local KIS-private QQQ/NAS M1 catalog.
It reuses the declared-session resampler and writes only aggregate external
evidence. It creates no provider, credential, broker, model, target, or GPU
surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Timeframe
from thericher_v2.data.kis_paper_intraday import (
    KisPaperIntradayFeatureInput,
    prepare_kis_paper_intraday_feature_input,
    require_complete_kis_paper_private_intraday_session,
    resample_verified_kis_paper_private_intraday_catalog,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session
from thericher_v2.models.current_source_opportunity_eligibility import (
    build_causal_bar_source_contract,
)
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID = "source-local-qqq-mtf-resampling-mechanics-v1"
KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M10,
    Timeframe.H1,
    Timeframe.H3,
)
KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT = 20

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_REQUIRED_DATASET_ID_PREFIX = "kis.paper.private.intraday.qqq.nas.m1."
_SELECTION_CALENDAR_SCOPE = "2026"
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_InputUnavailableReason = Literal[
    "invalid_catalog",
    "insufficient_complete_regular_sessions",
    "incomplete_resample_bucket",
]
_RunStatus = Literal["complete", "input_unavailable"]


@dataclass(frozen=True)
class QqqMtfTimeframeMechanics:
    """Aggregate completed and explicitly skipped buckets for one timeframe."""

    timeframe: Timeframe
    completed_bucket_count: int
    incomplete_bucket_count: int
    terminal_partial_bucket_count: int
    result_digest: str


@dataclass(frozen=True)
class KisQqqMtfResamplingMechanicsRun:
    """Immutable external evidence paths and source-safe terminal result."""

    run_label: str
    status: _RunStatus
    contract_hash: str
    precommit_path: Path
    summary_path: Path
    session_count: int
    input_unavailable_reason: _InputUnavailableReason | None
    timeframe_mechanics: tuple[QqqMtfTimeframeMechanics, ...]


def run_kis_qqq_mtf_resampling_mechanics(
    catalog: CatalogedBars,
    *,
    artifact_root: Path,
    run_label: str,
    repo_root: Path = _REPOSITORY_ROOT,
) -> KisQqqMtfResamplingMechanicsRun:
    """Attest one frozen, session-aligned local QQQ/NAS timeframe input."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("QQQ MTF resampling mechanics requires CatalogedBars")
    _validate_run_label(run_label)
    run_directory = _new_run_directory(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        run_label=run_label,
    )
    try:
        validate_kis_qqq_mtf_source_catalog(catalog)
        session_dates = select_first_complete_kis_qqq_mtf_regular_session_dates(catalog)
        input_data = prepare_kis_paper_intraday_feature_input(
            catalog,
            session_dates=session_dates,
        )
    except ValueError as error:
        return _write_input_unavailable_run(
            catalog=catalog,
            run_directory=run_directory,
            run_label=run_label,
            reason=_input_unavailable_reason(error),
        )

    contract = _contract_payload(input_data)
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = run_directory / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_qqq_mtf_resampling_mechanics_precommit",
            "status": "frozen_before_materialization",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(run_directory),
        },
    )

    mechanics = _materialize_timeframe_mechanics(input_data)
    incomplete = sum(item.incomplete_bucket_count for item in mechanics)
    status: _RunStatus = "complete" if incomplete == 0 else "input_unavailable"
    reason: _InputUnavailableReason | None = (
        None if status == "complete" else "incomplete_resample_bucket"
    )
    summary_path = run_directory / "summary.json"
    _write_json(
        summary_path,
        _summary_payload(
            input_data=input_data,
            run_label=run_label,
            status=status,
            contract_hash=contract_hash,
            mechanics=mechanics,
            input_unavailable_reason=reason,
            artifact_directory=run_directory,
        ),
    )
    return KisQqqMtfResamplingMechanicsRun(
        run_label=run_label,
        status=status,
        contract_hash=contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        session_count=len(input_data.session_dates),
        input_unavailable_reason=reason,
        timeframe_mechanics=mechanics,
    )


def _write_input_unavailable_run(
    *,
    catalog: CatalogedBars,
    run_directory: Path,
    run_label: str,
    reason: _InputUnavailableReason,
) -> KisQqqMtfResamplingMechanicsRun:
    contract = _input_unavailable_contract(catalog, reason=reason)
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = run_directory / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_qqq_mtf_resampling_mechanics_precommit",
            "status": "frozen_input_unavailable",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(run_directory),
        },
    )
    mechanics = _empty_mechanics()
    summary_path = run_directory / "summary.json"
    _write_json(
        summary_path,
        _input_unavailable_summary_payload(
            catalog=catalog,
            run_label=run_label,
            contract_hash=contract_hash,
            mechanics=mechanics,
            input_unavailable_reason=reason,
            artifact_directory=run_directory,
        ),
    )
    return KisQqqMtfResamplingMechanicsRun(
        run_label=run_label,
        status="input_unavailable",
        contract_hash=contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        session_count=0,
        input_unavailable_reason=reason,
        timeframe_mechanics=mechanics,
    )


def _materialize_timeframe_mechanics(
    input_data: KisPaperIntradayFeatureInput,
) -> tuple[QqqMtfTimeframeMechanics, ...]:
    results: list[QqqMtfTimeframeMechanics] = []
    for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES:
        completed_bucket_count = 0
        incomplete_bucket_count = 0
        terminal_partial_bucket_count = 0
        session_shapes: list[dict[str, int]] = []
        for session in input_data.session_windows:
            resampled = resample_verified_kis_paper_private_intraday_catalog(
                input_data.catalog,
                timeframe=timeframe,
                session=session,
            )
            terminal_partial = int(session.duration % timeframe.duration != timedelta(0))
            terminal_start = session.open_ts + timeframe.duration * (
                session.duration // timeframe.duration
            )
            if terminal_partial:
                if resampled.skipped_bucket_starts[-1:] != (terminal_start,):
                    raise ValueError(
                        "session resampler omitted its declared terminal partial bucket"
                    )
            elif terminal_start != session.close_ts:
                raise ValueError("session resampler terminal bucket plan is invalid")
            completed_bucket_count += len(resampled.bars)
            terminal_partial_bucket_count += terminal_partial
            incomplete_bucket_count += len(resampled.skipped_bucket_starts) - terminal_partial
            session_shapes.append(
                {
                    "completed_bucket_count": len(resampled.bars),
                    "incomplete_bucket_count": len(resampled.skipped_bucket_starts)
                    - terminal_partial,
                    "terminal_partial_bucket_count": terminal_partial,
                }
            )
        results.append(
            QqqMtfTimeframeMechanics(
                timeframe=timeframe,
                completed_bucket_count=completed_bucket_count,
                incomplete_bucket_count=incomplete_bucket_count,
                terminal_partial_bucket_count=terminal_partial_bucket_count,
                result_digest="sha256:" + _sha256_json(session_shapes),
            )
        )
    return tuple(results)


def select_first_complete_kis_qqq_mtf_regular_session_dates(
    catalog: CatalogedBars,
) -> tuple[date, ...]:
    """Choose the shared first twenty complete QQQ/NAS regular sessions."""

    validate_kis_qqq_mtf_source_catalog(catalog)
    candidate_dates = sorted(
        {
            bar.start_ts.astimezone(US_EQUITY_EASTERN).date()
            for bar in catalog.bars
            if bar.start_ts.astimezone(US_EQUITY_EASTERN).year == int(_SELECTION_CALENDAR_SCOPE)
        }
    )
    selected: list[date] = []
    for session_date in candidate_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            continue
        try:
            require_complete_kis_paper_private_intraday_session(catalog, session=session.window)
        except ValueError:
            continue
        selected.append(session_date)
        if len(selected) == KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT:
            return tuple(selected)
    raise ValueError("requires twenty complete regular KIS M1 sessions")


def validate_kis_qqq_mtf_source_catalog(catalog: CatalogedBars) -> None:
    """Require the verified local QQQ/NAS M1 source used by MTF mechanics."""

    if not catalog.dataset_id.startswith(_REQUIRED_DATASET_ID_PREFIX):
        raise ValueError("requires the KIS private QQQ/NAS M1 catalog")
    if any(
        bar.symbol != "QQQ" or bar.market != "US" or bar.timeframe != Timeframe.M1
        for bar in catalog.bars
    ):
        raise ValueError("requires QQQ/US M1 bars loaded from NAS")


def _contract_payload(input_data: KisPaperIntradayFeatureInput) -> dict[str, object]:
    selection_dates = [session_date.isoformat() for session_date in input_data.session_dates]
    causal_prefix = build_causal_bar_source_contract(
        input_data.catalog.bars,
        contract_id="kis-qqq-mtf-resampling-completed-m1-prefix-v1",
        as_of=input_data.session_windows[-1].close_ts,
    )
    return {
        "schema_version": 1,
        "mechanics_id": KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
        "source": {
            "dataset_id": input_data.catalog.dataset_id,
            "dataset_hash": input_data.catalog.dataset_hash,
            "input_id": input_data.input_id,
            "input_hash": input_data.input_hash,
            "session_count": len(input_data.session_dates),
            "selection": "first_20_complete_regular_sessions_ascending_within_2026_scope",
            "calendar_scope": _SELECTION_CALENDAR_SCOPE,
            "selected_session_dates_sha256": "sha256:" + _sha256_json(selection_dates),
            "causal_completed_m1_prefix_commitment": causal_prefix.contract_hash,
        },
        "resampling": {
            "source_timeframe": Timeframe.M1.value,
            "target_timeframes": [
                timeframe.value for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
            ],
            "bucket_anchor": "declared_regular_session_open",
            "partial_bucket_policy": "explicitly_skip_terminal_partial_bucket",
            "cross_session_carry_allowed": False,
            "future_bars_used": False,
        },
        "limits": _limits_payload(),
    }


def _input_unavailable_contract(
    catalog: CatalogedBars,
    *,
    reason: _InputUnavailableReason,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mechanics_id": KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
        "source": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "input_id": None,
            "input_hash": None,
            "session_count": 0,
            "selection": "first_20_complete_regular_sessions_ascending_within_2026_scope",
            "calendar_scope": _SELECTION_CALENDAR_SCOPE,
            "selected_session_dates_sha256": None,
            "causal_completed_m1_prefix_commitment": None,
        },
        "input_unavailable_reason": reason,
        "resampling": {
            "source_timeframe": Timeframe.M1.value,
            "target_timeframes": [
                timeframe.value for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
            ],
            "bucket_anchor": "declared_regular_session_open",
            "partial_bucket_policy": "explicitly_skip_terminal_partial_bucket",
            "cross_session_carry_allowed": False,
            "future_bars_used": False,
        },
        "limits": _limits_payload(),
    }


def _summary_payload(
    *,
    input_data: KisPaperIntradayFeatureInput,
    run_label: str,
    status: _RunStatus,
    contract_hash: str,
    mechanics: tuple[QqqMtfTimeframeMechanics, ...],
    input_unavailable_reason: _InputUnavailableReason | None,
    artifact_directory: Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_qqq_mtf_resampling_mechanics_summary",
        "status": status,
        "mode": "offline_existing_local_catalog_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source": {
            "dataset_id": input_data.catalog.dataset_id,
            "dataset_hash": input_data.catalog.dataset_hash,
            "input_id": input_data.input_id,
            "input_hash": input_data.input_hash,
            "session_count": len(input_data.session_dates),
        },
        "timeframes": [_timeframe_payload(item) for item in mechanics],
        "input_unavailable_reason": input_unavailable_reason,
        "limits": _limits_payload(),
        "artifact_policy": _artifact_policy(artifact_directory),
        "claim": _claim_for_status(status),
    }


def _input_unavailable_summary_payload(
    *,
    catalog: CatalogedBars,
    run_label: str,
    contract_hash: str,
    mechanics: tuple[QqqMtfTimeframeMechanics, ...],
    input_unavailable_reason: _InputUnavailableReason,
    artifact_directory: Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_qqq_mtf_resampling_mechanics_summary",
        "status": "input_unavailable",
        "mode": "offline_existing_local_catalog_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "input_id": None,
            "input_hash": None,
            "session_count": 0,
        },
        "timeframes": [_timeframe_payload(item) for item in mechanics],
        "input_unavailable_reason": input_unavailable_reason,
        "limits": _limits_payload(),
        "artifact_policy": _artifact_policy(artifact_directory),
        "claim": _claim_for_status("input_unavailable"),
    }


def _timeframe_payload(value: QqqMtfTimeframeMechanics) -> dict[str, object]:
    return {
        "timeframe": value.timeframe.value,
        "completed_bucket_count": value.completed_bucket_count,
        "incomplete_bucket_count": value.incomplete_bucket_count,
        "terminal_partial_bucket_count": value.terminal_partial_bucket_count,
        "result_digest": value.result_digest,
    }


def _empty_mechanics() -> tuple[QqqMtfTimeframeMechanics, ...]:
    return tuple(
        QqqMtfTimeframeMechanics(
            timeframe=timeframe,
            completed_bucket_count=0,
            incomplete_bucket_count=0,
            terminal_partial_bucket_count=0,
            result_digest="sha256:" + _sha256_json([]),
        )
        for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
    )


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
            "session-aligned completed-bar input mechanics only; it does not establish "
            "a strategy, prediction, profitability, model selection, ensemble, GPU "
            "eligibility, Paper input, or broker action"
        )
    if status == "input_unavailable":
        return (
            "source-local input was unavailable or incomplete before a usable multi-timeframe "
            "attestation; it creates no strategy, prediction, model, Paper input, or broker claim"
        )
    raise ValueError(f"unsupported MTF resampling mechanics status: {status}")


def _input_unavailable_reason(error: ValueError) -> _InputUnavailableReason:
    message = str(error)
    if message == "requires twenty complete regular KIS M1 sessions":
        return "insufficient_complete_regular_sessions"
    if message in {
        "requires the KIS private QQQ/NAS M1 catalog",
        "requires QQQ/US M1 bars loaded from NAS",
    }:
        return "invalid_catalog"
    return "incomplete_resample_bucket"


def _new_run_directory(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    parent = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "data",
        KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
    )
    if (parent / run_label).exists():
        raise FileExistsError(
            f"MTF resampling mechanics artifact already exists: {parent / run_label}"
        )
    return ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "data",
        KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
        run_label,
    )


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
