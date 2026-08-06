"""Source-local VWAP feature mechanics preflight.

The preflight reads a supplied local ``CatalogedBars`` instance only.  It does
not create a strategy direction, execution intent, or performance result.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import (
    CatalogedBars,
    SessionWindow,
    require_complete_kis_paper_private_intraday_session,
    us_equity_2026_session,
)
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN
from thericher_v2.models.session_reset_vwap_feature import (
    SESSION_RESET_VWAP_FEATURE_SCHEMA_ID,
    build_session_reset_vwap_feature,
)

KIS_INTRADAY_SESSION_RESET_VWAP_FEATURE_MECHANICS_ID = (
    "kis-intraday-session-reset-vwap-feature-mechanics-v1"
)
KIS_INTRADAY_SESSION_RESET_VWAP_SESSION_COUNT = 20
KIS_INTRADAY_SESSION_RESET_VWAP_CUTS = (5, 10, 30, 60, 90)

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_REQUIRED_DATASET_ID_PREFIX = "kis.paper.private.intraday.qqq.nas.m1."
_REQUIRED_SYMBOL = "QQQ"
_REQUIRED_MARKET = "NAS"
_InputUnavailableReason = Literal[
    "insufficient_complete_regular_sessions",
    "invalid_completed_session_prefix",
]


@dataclass(frozen=True)
class KisIntradaySessionResetVwapFeatureMechanicsRun:
    """One immutable source-safe feature-mechanics attempt."""

    run_label: str
    status: Literal["complete", "input_unavailable"]
    contract_hash: str
    summary_path: Path
    session_count: int
    evaluated_window_count: int
    feature_window_hash: str | None
    input_unavailable_reason: _InputUnavailableReason | None


def run_kis_intraday_session_reset_vwap_feature_mechanics(
    catalog: CatalogedBars,
    *,
    artifact_root: Path,
    run_label: str,
) -> KisIntradaySessionResetVwapFeatureMechanicsRun:
    """Run one bounded, offline VWAP feature preflight.

    All numerical feature values remain process-local.  The artifact contains
    only source identity, aggregate counts, and an opaque feature-window hash.
    """

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("VWAP mechanics preflight requires CatalogedBars")
    _validate_run_label(run_label)
    _validate_source_catalog(catalog)
    root = _external_artifact_root(artifact_root)
    output_dir = _direct_output_directory(
        root,
        run_label=run_label,
    )

    contract = _contract_payload(catalog)
    contract_hash = "sha256:" + _sha256_json(contract)
    try:
        sessions = _select_first_complete_regular_sessions(catalog)
        feature_window_hash = _evaluate_feature_windows(catalog, sessions=sessions)
    except ValueError as error:
        reason = _input_unavailable_reason(error)
        summary_path = output_dir / "summary.json"
        _write_json(
            summary_path,
            _summary_payload(
                catalog=catalog,
                run_label=run_label,
                contract_hash=contract_hash,
                status="input_unavailable",
                session_count=0,
                evaluated_window_count=0,
                feature_window_hash=None,
                input_unavailable_reason=reason,
            ),
        )
        return KisIntradaySessionResetVwapFeatureMechanicsRun(
            run_label=run_label,
            status="input_unavailable",
            contract_hash=contract_hash,
            summary_path=summary_path,
            session_count=0,
            evaluated_window_count=0,
            feature_window_hash=None,
            input_unavailable_reason=reason,
        )

    summary_path = output_dir / "summary.json"
    _write_json(
        summary_path,
        _summary_payload(
            catalog=catalog,
            run_label=run_label,
            contract_hash=contract_hash,
            status="complete",
            session_count=len(sessions),
            evaluated_window_count=len(sessions) * len(KIS_INTRADAY_SESSION_RESET_VWAP_CUTS),
            feature_window_hash=feature_window_hash,
            input_unavailable_reason=None,
        ),
    )
    return KisIntradaySessionResetVwapFeatureMechanicsRun(
        run_label=run_label,
        status="complete",
        contract_hash=contract_hash,
        summary_path=summary_path,
        session_count=len(sessions),
        evaluated_window_count=len(sessions) * len(KIS_INTRADAY_SESSION_RESET_VWAP_CUTS),
        feature_window_hash=feature_window_hash,
        input_unavailable_reason=None,
    )


def _select_first_complete_regular_sessions(
    catalog: CatalogedBars,
) -> tuple[tuple[date, SessionWindow], ...]:
    if any(bar.timeframe != Timeframe.M1 for bar in catalog.bars):
        raise ValueError("VWAP mechanics preflight requires M1 catalog bars")
    candidate_dates = sorted(
        {
            bar.start_ts.astimezone(US_EQUITY_EASTERN).date()
            for bar in catalog.bars
            if bar.start_ts.astimezone(US_EQUITY_EASTERN).year == 2026
        }
    )
    selected: list[tuple[date, SessionWindow]] = []
    for session_date in candidate_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            continue
        try:
            require_complete_kis_paper_private_intraday_session(catalog, session=session.window)
        except ValueError:
            continue
        selected.append((session_date, session.window))
        if len(selected) == KIS_INTRADAY_SESSION_RESET_VWAP_SESSION_COUNT:
            return tuple(selected)
    raise ValueError("insufficient complete regular sessions")


def _validate_source_catalog(catalog: CatalogedBars) -> None:
    if not catalog.dataset_id.startswith(_REQUIRED_DATASET_ID_PREFIX):
        raise ValueError("VWAP mechanics preflight requires the QQQ/NAS M1 catalog")
    if any(
        bar.symbol != _REQUIRED_SYMBOL
        or bar.market != _REQUIRED_MARKET
        or bar.timeframe != Timeframe.M1
        for bar in catalog.bars
    ):
        raise ValueError("VWAP mechanics preflight requires QQQ/NAS M1 bars")


def _evaluate_feature_windows(
    catalog: CatalogedBars,
    *,
    sessions: Sequence[tuple[date, SessionWindow]],
) -> str:
    digests: list[str] = []
    for session_date, session in sessions:
        bars = _first_ninety_completed_session_bars(catalog, session=session)
        for cut in KIS_INTRADAY_SESSION_RESET_VWAP_CUTS:
            prefix = bars[:cut]
            feature = build_session_reset_vwap_feature(
                prefix,
                session=session,
                as_of=prefix[-1].end_ts,
            )
            digests.append(
                _sha256_json(
                    {
                        "session_date": session_date.isoformat(),
                        "cut": cut,
                        "feature_window_end": feature.feature_window_end.isoformat(),
                        "bar_count": feature.bar_count,
                        "cumulative_volume": str(feature.cumulative_volume),
                        "vwap": str(feature.vwap),
                    }
                )
            )
    return "sha256:" + _sha256_json(digests)


def _first_ninety_completed_session_bars(
    catalog: CatalogedBars,
    *,
    session: SessionWindow,
) -> tuple[Bar, ...]:
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.open_ts and bar.end_ts <= session.close_ts
    )
    prefix = bars[: max(KIS_INTRADAY_SESSION_RESET_VWAP_CUTS)]
    if len(prefix) != max(KIS_INTRADAY_SESSION_RESET_VWAP_CUTS):
        raise ValueError("invalid completed session prefix")
    try:
        build_session_reset_vwap_feature(prefix, session=session, as_of=prefix[-1].end_ts)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid completed session prefix") from error
    return prefix


def _contract_payload(catalog: CatalogedBars) -> dict[str, object]:
    return {
        "schema_version": 1,
        "preflight_id": KIS_INTRADAY_SESSION_RESET_VWAP_FEATURE_MECHANICS_ID,
        "source": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "selection": "first_20_complete_regular_sessions_ascending",
            "timeframe": Timeframe.M1.value,
        },
        "feature": {
            "schema_id": SESSION_RESET_VWAP_FEATURE_SCHEMA_ID,
            "formula": "cumulative_session_typical_price_volume_weighted_vwap",
            "typical_price": "(high + low + close) / 3",
            "cuts_completed_m1_bars": list(KIS_INTRADAY_SESSION_RESET_VWAP_CUTS),
            "maximum_completed_m1_bars_per_session": max(KIS_INTRADAY_SESSION_RESET_VWAP_CUTS),
            "future_bars_used": False,
        },
        "limits": {
            "source_local_only": True,
            "non_promoting": True,
            "strategy_direction_created": False,
            "performance_metrics_created": False,
            "paper_input_allowed": False,
            "gpu_eligible": False,
        },
    }


def _summary_payload(
    *,
    catalog: CatalogedBars,
    run_label: str,
    contract_hash: str,
    status: Literal["complete", "input_unavailable"],
    session_count: int,
    evaluated_window_count: int,
    feature_window_hash: str | None,
    input_unavailable_reason: _InputUnavailableReason | None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_intraday_session_reset_vwap_feature_mechanics_summary",
        "status": status,
        "mode": "offline_existing_local_catalog_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
        },
        "mechanics": {
            "session_count": session_count,
            "cuts_completed_m1_bars": list(KIS_INTRADAY_SESSION_RESET_VWAP_CUTS),
            "evaluated_window_count": evaluated_window_count,
            "feature_window_hash": feature_window_hash,
        },
        "input_unavailable_reason": input_unavailable_reason,
        "access": {
            "network_access": "not_invoked",
            "credential_access": "not_invoked",
            "broker_access": "not_invoked",
            "scheduler_access": "not_invoked",
            "gpu_access": "not_invoked",
        },
        "non_retention": {
            "raw_market_data_retained": False,
            "raw_price_values_retained": False,
            "raw_volume_values_retained": False,
            "feature_values_retained": False,
            "signals_retained": False,
            "orders_retained": False,
            "pnl_retained": False,
        },
        "limits": {
            "source_local_only": True,
            "non_promoting": True,
            "strategy_direction_created": False,
            "performance_metrics_created": False,
            "paper_input_allowed": False,
            "gpu_eligible": False,
            "decision_time_availability": "not_observed",
        },
    }


def _input_unavailable_reason(error: ValueError) -> _InputUnavailableReason:
    if str(error) == "insufficient complete regular sessions":
        return "insufficient_complete_regular_sessions"
    return "invalid_completed_session_prefix"


def _external_artifact_root(artifact_root: Path) -> Path:
    supplied_root = Path(artifact_root).absolute()
    _reject_linked_components(supplied_root)
    root = supplied_root.resolve(strict=False)
    repository = _REPOSITORY_ROOT.resolve(strict=False)
    if root == repository or root.is_relative_to(repository):
        raise ValueError("artifact root must stay outside the Git workspace")
    supplied_root.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse_point(supplied_root) or not supplied_root.is_dir():
        raise ValueError("artifact root must be a direct directory")
    root = supplied_root.resolve(strict=True)
    if root == repository or root.is_relative_to(repository):
        raise ValueError("artifact root must stay outside the Git workspace")
    return root


def _direct_output_directory(root: Path, *, run_label: str) -> Path:
    directory = root
    repository = _REPOSITORY_ROOT.resolve(strict=False)
    for part in ("research", KIS_INTRADAY_SESSION_RESET_VWAP_FEATURE_MECHANICS_ID, run_label):
        candidate = directory / part
        try:
            candidate.mkdir()
        except FileExistsError:
            if part == run_label:
                raise FileExistsError(
                    f"VWAP feature mechanics artifact already exists: {candidate}"
                ) from None
        if _is_link_or_reparse_point(candidate) or not candidate.is_dir():
            raise ValueError("artifact directory must be direct")
        resolved = candidate.resolve(strict=True)
        if (
            not resolved.is_relative_to(root)
            or resolved == repository
            or resolved.is_relative_to(repository)
        ):
            raise ValueError("artifact directory must stay outside the Git workspace")
        directory = resolved
    return directory


def _reject_linked_components(path: Path) -> None:
    components: list[Path] = []
    current = path
    while current != current.parent:
        components.append(current)
        current = current.parent
    components.append(current)
    for component in reversed(components):
        if component.exists() and _is_link_or_reparse_point(component):
            raise ValueError("artifact root must not traverse a symlink or junction")


def _is_link_or_reparse_point(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    if _is_link_or_reparse_point(path.parent) or not path.parent.is_dir():
        raise ValueError("artifact directory must be direct")
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
