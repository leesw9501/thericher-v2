"""Source-local causal-window feasibility for the frozen QQQ MTF input."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Bar, Timeframe, require_utc
from thericher_v2.data.kis_paper_intraday import (
    KisPaperIntradayFeatureInput,
    prepare_kis_paper_intraday_feature_input,
)
from thericher_v2.data.kis_qqq_mtf_resampling_mechanics import (
    KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
    KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT,
    KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES,
    select_first_complete_kis_qqq_mtf_regular_session_dates,
    validate_kis_qqq_mtf_source_catalog,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow, resample_session_bars
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN
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

KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID = "source-local-qqq-mtf-window-feasibility-v1"
KIS_QQQ_MTF_WINDOW_PROFILE_ID = "kis_baseline"
KIS_QQQ_MTF_WINDOW_CUTOFF = time(15, 30)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SHA256_REFERENCE = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_RunStatus = Literal["complete", "input_unavailable"]
_InputUnavailableReason = Literal[
    "invalid_catalog",
    "invalid_mechanics_receipt",
    "mechanics_source_binding_mismatch",
    "insufficient_complete_regular_sessions",
    "incomplete_or_invalid_causal_window",
]


@dataclass(frozen=True)
class KisQqqMtfMechanicsReceipt:
    """Source-safe binding extracted from a completed MTF mechanics artifact."""

    contract_hash: str
    precommit_path: Path
    summary_path: Path
    source_dataset_id: str
    source_dataset_hash: str
    source_input_id: str
    source_input_hash: str
    selected_session_dates_sha256: str
    causal_completed_m1_prefix_commitment: str
    calendar_scope: str
    session_count: int

    def __post_init__(self) -> None:
        references = (
            self.contract_hash,
            self.source_dataset_hash,
            self.source_input_hash,
            self.selected_session_dates_sha256,
            self.causal_completed_m1_prefix_commitment,
        )
        if (
            any(_SHA256_REFERENCE.fullmatch(value) is None for value in references)
            or not isinstance(self.precommit_path, Path)
            or not isinstance(self.summary_path, Path)
            or self.precommit_path.is_symlink()
            or self.summary_path.is_symlink()
            or not self.precommit_path.is_file()
            or not self.summary_path.is_file()
            or not self.source_dataset_id
            or not self.source_input_id
            or self.calendar_scope != "2026"
            or self.session_count != KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT
        ):
            raise ValueError("QQQ MTF mechanics receipt is invalid")


@dataclass(frozen=True)
class QqqMtfWindowGeometry:
    """Aggregate completed bars for one target-free profile timeframe."""

    timeframe: Timeframe
    lookback: int
    completed_window_bar_count: int
    terminal_partial_exclusion_count: int
    causal_window_digest: str


@dataclass(frozen=True)
class KisQqqMtfWindowFeasibilityRun:
    """Immutable result for one source-local, target-free window attestation."""

    run_label: str
    status: _RunStatus
    contract_hash: str
    mechanics_contract_hash: str
    precommit_path: Path
    summary_path: Path
    eligible_session_count: int
    input_unavailable_reason: _InputUnavailableReason | None
    geometry: tuple[QqqMtfWindowGeometry, ...]


@dataclass(frozen=True)
class KisQqqMtfWindowFeasibilityReceipt:
    """Source-safe binding extracted from one completed baseline-window receipt."""

    contract_hash: str
    precommit_path: Path
    summary_path: Path
    mechanics_contract_hash: str
    source_dataset_id: str
    source_dataset_hash: str
    source_input_id: str
    source_input_hash: str
    selected_session_dates_sha256: str
    causal_completed_m1_prefix_commitment: str
    calendar_scope: str
    session_count: int
    profile_catalog_sha256: str
    geometry: tuple[QqqMtfWindowGeometry, ...]

    def __post_init__(self) -> None:
        references = (
            self.contract_hash,
            self.mechanics_contract_hash,
            self.source_dataset_hash,
            self.source_input_hash,
            self.selected_session_dates_sha256,
            self.causal_completed_m1_prefix_commitment,
            self.profile_catalog_sha256,
        )
        expected_profile = _profile()
        geometry = tuple(self.geometry)
        if (
            any(_SHA256_REFERENCE.fullmatch(value) is None for value in references)
            or not isinstance(self.precommit_path, Path)
            or not isinstance(self.summary_path, Path)
            or self.precommit_path.is_symlink()
            or self.summary_path.is_symlink()
            or not self.precommit_path.is_file()
            or not self.summary_path.is_file()
            or not self.source_dataset_id
            or not self.source_input_id
            or self.calendar_scope != "2026"
            or self.session_count != KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT
            or self.profile_catalog_sha256
            != CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256
            or tuple(item.timeframe for item in geometry) != KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
            or any(
                item.lookback != expected_profile.lookbacks[item.timeframe]
                or item.completed_window_bar_count
                != expected_profile.lookbacks[item.timeframe]
                * KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT
                or item.terminal_partial_exclusion_count
                != (
                    KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT
                    if item.timeframe in (Timeframe.H1, Timeframe.H3)
                    else 0
                )
                or _SHA256_REFERENCE.fullmatch(item.causal_window_digest) is None
                for item in geometry
            )
        ):
            raise ValueError("QQQ MTF window feasibility receipt is invalid")
        object.__setattr__(self, "geometry", geometry)


def load_kis_qqq_mtf_mechanics_receipt(
    *,
    precommit_path: Path,
    summary_path: Path,
    repo_root: Path = _REPOSITORY_ROOT,
) -> KisQqqMtfMechanicsReceipt:
    """Load one externally stored completed mechanics receipt without raw data."""

    precommit_file = _resolve_external_artifact_path(precommit_path, repo_root=repo_root)
    summary_file = _resolve_external_artifact_path(summary_path, repo_root=repo_root)
    if precommit_file.parent != summary_file.parent:
        raise ValueError("QQQ MTF mechanics receipt paths must share one run directory")
    precommit = _read_json_mapping(precommit_file)
    summary = _read_json_mapping(summary_file)
    return _mechanics_receipt_from_payloads(
        precommit=precommit,
        summary=summary,
        precommit_path=precommit_file,
        summary_path=summary_file,
    )


def load_kis_qqq_mtf_window_feasibility_receipt(
    *,
    precommit_path: Path,
    summary_path: Path,
    repo_root: Path = _REPOSITORY_ROOT,
) -> KisQqqMtfWindowFeasibilityReceipt:
    """Load one externally stored baseline-window receipt without raw data."""

    precommit_file = _resolve_external_artifact_path(precommit_path, repo_root=repo_root)
    summary_file = _resolve_external_artifact_path(summary_path, repo_root=repo_root)
    if precommit_file.parent != summary_file.parent:
        raise ValueError("QQQ MTF window receipt paths must share one run directory")
    precommit = _read_json_mapping(precommit_file)
    summary = _read_json_mapping(summary_file)
    return _window_feasibility_receipt_from_payloads(
        precommit=precommit,
        summary=summary,
        precommit_path=precommit_file,
        summary_path=summary_file,
    )


def run_kis_qqq_mtf_window_feasibility(
    catalog: CatalogedBars,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    artifact_root: Path,
    run_label: str,
    repo_root: Path = _REPOSITORY_ROOT,
) -> KisQqqMtfWindowFeasibilityRun:
    """Attest the canonical 15:30 ET QQQ causal profile without model work."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("QQQ MTF window feasibility requires CatalogedBars")
    if not isinstance(mechanics_receipt, KisQqqMtfMechanicsReceipt):
        raise TypeError("QQQ MTF window feasibility requires a mechanics receipt")
    _validate_run_label(run_label)
    run_directory = _new_run_directory(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        run_label=run_label,
    )
    try:
        input_data = prepare_kis_qqq_mtf_window_input(catalog, mechanics_receipt=mechanics_receipt)
    except _InputUnavailable as error:
        return _write_input_unavailable_run(
            catalog=catalog,
            mechanics_receipt=mechanics_receipt,
            run_directory=run_directory,
            run_label=run_label,
            reason=error.reason,
        )

    contract = _contract_payload(input_data, mechanics_receipt=mechanics_receipt)
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = run_directory / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_qqq_mtf_window_feasibility_precommit",
            "status": "frozen_before_materialization",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(run_directory),
        },
    )
    try:
        geometry = _materialize_geometry(input_data)
    except _InputUnavailable as error:
        status: _RunStatus = "input_unavailable"
        reason: _InputUnavailableReason | None = error.reason
        eligible_session_count = 0
        geometry = _empty_geometry()
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
            run_label=run_label,
            status=status,
            contract_hash=contract_hash,
            eligible_session_count=eligible_session_count,
            input_unavailable_reason=reason,
            geometry=geometry,
            artifact_directory=run_directory,
        ),
    )
    return KisQqqMtfWindowFeasibilityRun(
        run_label=run_label,
        status=status,
        contract_hash=contract_hash,
        mechanics_contract_hash=mechanics_receipt.contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        eligible_session_count=eligible_session_count,
        input_unavailable_reason=reason,
        geometry=geometry,
    )


def prepare_kis_qqq_mtf_window_input(
    catalog: CatalogedBars,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
) -> KisPaperIntradayFeatureInput:
    try:
        validate_kis_qqq_mtf_source_catalog(catalog)
        session_dates = select_first_complete_kis_qqq_mtf_regular_session_dates(catalog)
        input_data = prepare_kis_paper_intraday_feature_input(
            catalog,
            session_dates=session_dates,
        )
    except ValueError as error:
        message = str(error)
        if message == "requires twenty complete regular KIS M1 sessions":
            raise _InputUnavailable("insufficient_complete_regular_sessions") from error
        raise _InputUnavailable("invalid_catalog") from error
    _validate_mechanics_source_binding(input_data, mechanics_receipt=mechanics_receipt)
    return input_data


def _validate_mechanics_source_binding(
    input_data: KisPaperIntradayFeatureInput,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
) -> None:
    selected_dates_hash = "sha256:" + _sha256_json(
        [session_date.isoformat() for session_date in input_data.session_dates]
    )
    causal_commitment = build_causal_bar_source_contract(
        input_data.catalog.bars,
        contract_id="kis-qqq-mtf-resampling-completed-m1-prefix-v1",
        as_of=input_data.session_windows[-1].close_ts,
    ).contract_hash
    if (
        input_data.catalog.dataset_id != mechanics_receipt.source_dataset_id
        or input_data.catalog.dataset_hash != mechanics_receipt.source_dataset_hash
        or input_data.input_id != mechanics_receipt.source_input_id
        or input_data.input_hash != mechanics_receipt.source_input_hash
        or selected_dates_hash != mechanics_receipt.selected_session_dates_sha256
        or causal_commitment != mechanics_receipt.causal_completed_m1_prefix_commitment
    ):
        raise _InputUnavailable("mechanics_source_binding_mismatch")


def _contract_payload(
    input_data: KisPaperIntradayFeatureInput,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
) -> dict[str, object]:
    profile = _profile()
    return {
        "schema_version": 1,
        "feasibility_id": KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID,
        "source_mechanics": {
            "mechanics_id": KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
            "contract_hash": mechanics_receipt.contract_hash,
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
        "profile": {
            "profile_id": profile.profile_id,
            "catalog_sha256": CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256,
            "lookbacks": _profile_lookbacks_payload(profile),
            "cutoff": "15:30 America/New_York",
            "all_selected_window_ends_equal_cutoff": True,
        },
        "limits": _limits_payload(),
    }


def _materialize_geometry(
    input_data: KisPaperIntradayFeatureInput,
) -> tuple[QqqMtfWindowGeometry, ...]:
    profile = _profile()
    completed_counts = {timeframe: 0 for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES}
    terminal_counts = {timeframe: 0 for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES}
    records = {timeframe: [] for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES}
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
            feasibility = assess_profile_feasibility(
                catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
                profile_id=profile.profile_id,
                bars_by_timeframe=bars_by_timeframe,
                cutoff=cutoff,
            )
            terminal_results = {
                timeframe: _resample_terminal_bucket(
                    prefix,
                    timeframe=timeframe,
                    session=session,
                )
                for timeframe in (Timeframe.H1, Timeframe.H3)
            }
        except ValueError as error:
            raise _InputUnavailable("incomplete_or_invalid_causal_window") from error
        window = feasibility.window
        if any(sequence.end_ts != cutoff for sequence in window.windows.values()):
            raise _InputUnavailable("incomplete_or_invalid_causal_window")
        prefix_commitment = build_causal_bar_source_contract(
            prefix,
            contract_id="kis-qqq-mtf-window-feasibility-session-prefix-v1",
            as_of=cutoff,
        ).contract_hash
        for timeframe, sequence in window.windows.items():
            completed_counts[timeframe] += len(sequence.bars)
            records[timeframe].append(
                {
                    "timeframe": timeframe.value,
                    "cutoff": cutoff.isoformat(),
                    "prefix_commitment": prefix_commitment,
                    "window_bar_count": len(sequence.bars),
                    "window_end": sequence.end_ts.isoformat(),
                }
            )
        for timeframe in (Timeframe.H1, Timeframe.H3):
            expected_terminal = cutoff
            terminal_result = terminal_results[timeframe]
            if terminal_result != (expected_terminal,):
                raise _InputUnavailable("incomplete_or_invalid_causal_window")
            terminal_counts[timeframe] += 1

    return tuple(
        QqqMtfWindowGeometry(
            timeframe=timeframe,
            lookback=profile.lookbacks[timeframe],
            completed_window_bar_count=completed_counts[timeframe],
            terminal_partial_exclusion_count=terminal_counts[timeframe],
            causal_window_digest="sha256:" + _sha256_json(records[timeframe]),
        )
        for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
    )


def _resample_terminal_bucket(
    prefix: tuple[Bar, ...],
    *,
    timeframe: Timeframe,
    session: SessionWindow,
) -> tuple[datetime, ...]:
    """Read the existing session resampler's visible partial terminal bucket."""

    return resample_session_bars(prefix, timeframe, session=session).skipped_bucket_starts


def kis_qqq_mtf_window_cutoff(session_open: datetime) -> datetime:
    local_open = require_utc(session_open, "session_open").astimezone(US_EQUITY_EASTERN)
    return local_open.replace(
        hour=KIS_QQQ_MTF_WINDOW_CUTOFF.hour,
        minute=KIS_QQQ_MTF_WINDOW_CUTOFF.minute,
        second=0,
        microsecond=0,
    ).astimezone(session_open.tzinfo)


def _profile() -> CausalMtfWindowProfile:
    return CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile(KIS_QQQ_MTF_WINDOW_PROFILE_ID)


def _write_input_unavailable_run(
    *,
    catalog: CatalogedBars,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    run_directory: Path,
    run_label: str,
    reason: _InputUnavailableReason,
) -> KisQqqMtfWindowFeasibilityRun:
    contract = _input_unavailable_contract(
        catalog,
        mechanics_receipt=mechanics_receipt,
        reason=reason,
    )
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = run_directory / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_qqq_mtf_window_feasibility_precommit",
            "status": "frozen_input_unavailable",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(run_directory),
        },
    )
    geometry = _empty_geometry()
    summary_path = run_directory / "summary.json"
    _write_json(
        summary_path,
        _input_unavailable_summary_payload(
            catalog=catalog,
            mechanics_receipt=mechanics_receipt,
            run_label=run_label,
            contract_hash=contract_hash,
            reason=reason,
            geometry=geometry,
            artifact_directory=run_directory,
        ),
    )
    return KisQqqMtfWindowFeasibilityRun(
        run_label=run_label,
        status="input_unavailable",
        contract_hash=contract_hash,
        mechanics_contract_hash=mechanics_receipt.contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        eligible_session_count=0,
        input_unavailable_reason=reason,
        geometry=geometry,
    )


def _input_unavailable_contract(
    catalog: CatalogedBars,
    *,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    reason: _InputUnavailableReason,
) -> dict[str, object]:
    profile = _profile()
    return {
        "schema_version": 1,
        "feasibility_id": KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID,
        "source_mechanics": {
            "mechanics_id": KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
            "contract_hash": mechanics_receipt.contract_hash,
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
        "profile": {
            "profile_id": profile.profile_id,
            "catalog_sha256": CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256,
            "lookbacks": _profile_lookbacks_payload(profile),
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
    run_label: str,
    status: _RunStatus,
    contract_hash: str,
    eligible_session_count: int,
    input_unavailable_reason: _InputUnavailableReason | None,
    geometry: tuple[QqqMtfWindowGeometry, ...],
    artifact_directory: Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_qqq_mtf_window_feasibility_summary",
        "status": status,
        "mode": "offline_existing_local_catalog_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source_mechanics_contract_hash": mechanics_receipt.contract_hash,
        "source": {
            "dataset_id": input_data.catalog.dataset_id,
            "dataset_hash": input_data.catalog.dataset_hash,
            "input_id": input_data.input_id,
            "input_hash": input_data.input_hash,
            "session_count": len(input_data.session_dates),
        },
        "profile": _profile_summary_payload(),
        "eligible_session_count": eligible_session_count,
        "input_unavailable_reason": input_unavailable_reason,
        "geometry": [_geometry_payload(item) for item in geometry],
        "limits": _limits_payload(),
        "artifact_policy": _artifact_policy(artifact_directory),
        "claim": _claim_for_status(status),
    }


def _input_unavailable_summary_payload(
    *,
    catalog: CatalogedBars,
    mechanics_receipt: KisQqqMtfMechanicsReceipt,
    run_label: str,
    contract_hash: str,
    reason: _InputUnavailableReason,
    geometry: tuple[QqqMtfWindowGeometry, ...],
    artifact_directory: Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_qqq_mtf_window_feasibility_summary",
        "status": "input_unavailable",
        "mode": "offline_existing_local_catalog_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source_mechanics_contract_hash": mechanics_receipt.contract_hash,
        "source": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "input_id": None,
            "input_hash": None,
            "session_count": 0,
        },
        "profile": _profile_summary_payload(),
        "eligible_session_count": 0,
        "input_unavailable_reason": reason,
        "geometry": [_geometry_payload(item) for item in geometry],
        "limits": _limits_payload(),
        "artifact_policy": _artifact_policy(artifact_directory),
        "claim": _claim_for_status("input_unavailable"),
    }


def _profile_summary_payload() -> dict[str, object]:
    profile = _profile()
    return {
        "profile_id": profile.profile_id,
        "catalog_sha256": CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256,
        "lookbacks": _profile_lookbacks_payload(profile),
        "cutoff": "15:30 America/New_York",
    }


def _profile_lookbacks_payload(profile: CausalMtfWindowProfile) -> dict[str, int]:
    return {timeframe.value: lookback for timeframe, lookback in profile.lookbacks.items()}


def _geometry_payload(value: QqqMtfWindowGeometry) -> dict[str, object]:
    return {
        "timeframe": value.timeframe.value,
        "lookback": value.lookback,
        "completed_window_bar_count": value.completed_window_bar_count,
        "terminal_partial_exclusion_count": value.terminal_partial_exclusion_count,
        "causal_window_digest": value.causal_window_digest,
    }


def _empty_geometry() -> tuple[QqqMtfWindowGeometry, ...]:
    profile = _profile()
    return tuple(
        QqqMtfWindowGeometry(
            timeframe=timeframe,
            lookback=profile.lookbacks[timeframe],
            completed_window_bar_count=0,
            terminal_partial_exclusion_count=0,
            causal_window_digest="sha256:" + _sha256_json([]),
        )
        for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES
    )


def _mechanics_receipt_from_payloads(
    *,
    precommit: Mapping[str, object],
    summary: Mapping[str, object],
    precommit_path: Path,
    summary_path: Path,
) -> KisQqqMtfMechanicsReceipt:
    if (
        precommit.get("kind") != "kis_qqq_mtf_resampling_mechanics_precommit"
        or precommit.get("status") != "frozen_before_materialization"
        or summary.get("kind") != "kis_qqq_mtf_resampling_mechanics_summary"
        or summary.get("status") != "complete"
        or summary.get("input_unavailable_reason") is not None
        or precommit.get("contract_hash") != summary.get("contract_hash")
    ):
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    contract = _mapping(precommit.get("contract"))
    expected_contract_hash = "sha256:" + _sha256_json(contract)
    if precommit.get("contract_hash") != expected_contract_hash:
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    if contract.get("mechanics_id") != KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID:
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    source = _mapping(contract.get("source"))
    summary_source = _mapping(summary.get("source"))
    source_fields = ("dataset_id", "dataset_hash", "input_id", "input_hash", "session_count")
    if any(source.get(field) != summary_source.get(field) for field in source_fields):
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    _validate_mechanics_resampling_contract(_mapping(contract.get("resampling")))
    _validate_mechanics_summary_timeframes(summary.get("timeframes"))
    try:
        return KisQqqMtfMechanicsReceipt(
            contract_hash=_string(precommit.get("contract_hash")),
            precommit_path=precommit_path,
            summary_path=summary_path,
            source_dataset_id=_string(source.get("dataset_id")),
            source_dataset_hash=_string(source.get("dataset_hash")),
            source_input_id=_string(source.get("input_id")),
            source_input_hash=_string(source.get("input_hash")),
            selected_session_dates_sha256=_string(source.get("selected_session_dates_sha256")),
            causal_completed_m1_prefix_commitment=_string(
                source.get("causal_completed_m1_prefix_commitment")
            ),
            calendar_scope=_string(source.get("calendar_scope")),
            session_count=_integer(source.get("session_count")),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("QQQ MTF mechanics receipt is invalid") from error


def _window_feasibility_receipt_from_payloads(
    *,
    precommit: Mapping[str, object],
    summary: Mapping[str, object],
    precommit_path: Path,
    summary_path: Path,
) -> KisQqqMtfWindowFeasibilityReceipt:
    if (
        precommit.get("kind") != "kis_qqq_mtf_window_feasibility_precommit"
        or precommit.get("status") != "frozen_before_materialization"
        or summary.get("kind") != "kis_qqq_mtf_window_feasibility_summary"
        or summary.get("status") != "complete"
        or summary.get("input_unavailable_reason") is not None
        or precommit.get("contract_hash") != summary.get("contract_hash")
        or summary.get("mode") != "offline_existing_local_catalog_only"
        or summary.get("eligible_session_count") != KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT
        or summary.get("limits") != _limits_payload()
    ):
        raise ValueError("QQQ MTF window feasibility receipt is invalid")
    contract = _mapping(precommit.get("contract"))
    expected_contract_hash = "sha256:" + _sha256_json(contract)
    if (
        precommit.get("contract_hash") != expected_contract_hash
        or contract.get("feasibility_id") != KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID
    ):
        raise ValueError("QQQ MTF window feasibility receipt is invalid")
    source_mechanics = _mapping(contract.get("source_mechanics"))
    if (
        source_mechanics.get("mechanics_id") != KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID
        or source_mechanics.get("contract_hash") != summary.get("source_mechanics_contract_hash")
    ):
        raise ValueError("QQQ MTF window feasibility receipt is invalid")
    source = _mapping(contract.get("source"))
    summary_source = _mapping(summary.get("source"))
    source_fields = ("dataset_id", "dataset_hash", "input_id", "input_hash", "session_count")
    if any(source.get(field) != summary_source.get(field) for field in source_fields):
        raise ValueError("QQQ MTF window feasibility receipt is invalid")
    profile = _mapping(contract.get("profile"))
    expected_profile = _profile()
    expected_contract_profile = {
        "profile_id": expected_profile.profile_id,
        "catalog_sha256": CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256,
        "lookbacks": _profile_lookbacks_payload(expected_profile),
        "cutoff": "15:30 America/New_York",
        "all_selected_window_ends_equal_cutoff": True,
    }
    expected_summary_profile = {
        key: value
        for key, value in expected_contract_profile.items()
        if key != "all_selected_window_ends_equal_cutoff"
    }
    summary_profile = _mapping(summary.get("profile"))
    if profile != expected_contract_profile or summary_profile != expected_summary_profile:
        raise ValueError("QQQ MTF window feasibility receipt is invalid")
    try:
        return KisQqqMtfWindowFeasibilityReceipt(
            contract_hash=_string(precommit.get("contract_hash")),
            precommit_path=precommit_path,
            summary_path=summary_path,
            mechanics_contract_hash=_string(source_mechanics.get("contract_hash")),
            source_dataset_id=_string(source.get("dataset_id")),
            source_dataset_hash=_string(source.get("dataset_hash")),
            source_input_id=_string(source.get("input_id")),
            source_input_hash=_string(source.get("input_hash")),
            selected_session_dates_sha256=_string(source.get("selected_session_dates_sha256")),
            causal_completed_m1_prefix_commitment=_string(
                source.get("causal_completed_m1_prefix_commitment")
            ),
            calendar_scope=_string(source.get("calendar_scope")),
            session_count=_integer(source.get("session_count")),
            profile_catalog_sha256=_string(profile.get("catalog_sha256")),
            geometry=_window_geometry_from_payload(summary.get("geometry")),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("QQQ MTF window feasibility receipt is invalid") from error


def _window_geometry_from_payload(value: object) -> tuple[QqqMtfWindowGeometry, ...]:
    if not isinstance(value, list):
        raise ValueError("QQQ MTF window feasibility receipt is invalid")
    geometry: list[QqqMtfWindowGeometry] = []
    for timeframe, raw_item in zip(KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES, value, strict=False):
        item = _mapping(raw_item)
        if item.get("timeframe") != timeframe.value:
            raise ValueError("QQQ MTF window feasibility receipt is invalid")
        geometry.append(
            QqqMtfWindowGeometry(
                timeframe=timeframe,
                lookback=_integer(item.get("lookback")),
                completed_window_bar_count=_integer(item.get("completed_window_bar_count")),
                terminal_partial_exclusion_count=_integer(
                    item.get("terminal_partial_exclusion_count")
                ),
                causal_window_digest=_string(item.get("causal_window_digest")),
            )
        )
    if len(geometry) != len(KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES) or len(value) != len(geometry):
        raise ValueError("QQQ MTF window feasibility receipt is invalid")
    return tuple(geometry)


def _validate_mechanics_resampling_contract(resampling: Mapping[str, object]) -> None:
    expected_timeframes = [timeframe.value for timeframe in KIS_QQQ_MTF_RESAMPLING_TIMEFRAMES]
    if resampling != {
        "source_timeframe": Timeframe.M1.value,
        "target_timeframes": expected_timeframes,
        "bucket_anchor": "declared_regular_session_open",
        "partial_bucket_policy": "explicitly_skip_terminal_partial_bucket",
        "cross_session_carry_allowed": False,
        "future_bars_used": False,
    }:
        raise ValueError("QQQ MTF mechanics receipt is invalid")


def _validate_mechanics_summary_timeframes(value: object) -> None:
    if not isinstance(value, list):
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    by_timeframe = {
        item.get("timeframe"): item
        for raw_item in value
        if isinstance(raw_item, Mapping)
        for item in (_mapping(raw_item),)
    }
    expected_completed = {
        Timeframe.M1.value: 390 * KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT,
        Timeframe.M5.value: 78 * KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT,
        Timeframe.M10.value: 39 * KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT,
        Timeframe.H1.value: 6 * KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT,
        Timeframe.H3.value: 2 * KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT,
    }
    expected_terminal = {Timeframe.H1.value, Timeframe.H3.value}
    if set(by_timeframe) != set(expected_completed):
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    for timeframe, expected_count in expected_completed.items():
        item = by_timeframe[timeframe]
        if (
            _integer(item.get("completed_bucket_count")) != expected_count
            or _integer(item.get("incomplete_bucket_count")) != 0
            or _integer(item.get("terminal_partial_bucket_count"))
            != (KIS_QQQ_MTF_RESAMPLING_SESSION_COUNT if timeframe in expected_terminal else 0)
            or _SHA256_REFERENCE.fullmatch(_string(item.get("result_digest"))) is None
        ):
            raise ValueError("QQQ MTF mechanics receipt is invalid")


def _resolve_external_artifact_path(path: Path, *, repo_root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("QQQ MTF mechanics receipt path is invalid")
    resolved = candidate.resolve()
    if resolved.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("QQQ MTF mechanics receipt must stay outside the Git workspace")
    return resolved


def _read_json_mapping(path: Path) -> Mapping[str, object]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("QQQ MTF mechanics receipt is invalid") from error
    return _mapping(decoded)


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
            "target-free causal window geometry only; it does not establish a strategy, "
            "prediction, profitability, model selection, ensemble, GPU eligibility, Paper "
            "input, or broker action"
        )
    if status == "input_unavailable":
        return (
            "source-local causal-window input was unavailable or invalid before any model, "
            "target, Paper input, or broker claim"
        )
    raise ValueError(f"unsupported QQQ MTF window feasibility status: {status}")


def _new_run_directory(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    parent = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "data",
        KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID,
    )
    if (parent / run_label).exists():
        raise FileExistsError(
            f"QQQ MTF window feasibility artifact already exists: {parent / run_label}"
        )
    return ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "data",
        KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID,
        run_label,
    )


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("QQQ MTF mechanics receipt is invalid")
    return value


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class _InputUnavailable(ValueError):
    def __init__(self, reason: _InputUnavailableReason) -> None:
        self.reason = reason
        super().__init__(reason)
