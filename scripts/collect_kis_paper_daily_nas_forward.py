"""Collect one private, current-D1 NAS forward-cache observation in Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    KIS_PAPER_DAILY_NAS_FORWARD_FROZEN_BOUNDARY,
    KisPaperDailyNasForwardCacheError,
    get_kis_paper_daily_nas_forward_failure_details,
    kis_paper_daily_nas_forward_failure_context,
    load_verified_kis_paper_daily_nas_forward_cache,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    load_kis_paper_market_data_environment_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_daily_nas_forward import (
    KisPaperDailyNasForwardError,
    UrllibKisPaperDailyNasForwardTransport,
    collect_kis_paper_daily_nas_forward_once,
    latest_completed_us_equity_d1_session,
)

_CANONICAL_CACHE_ROOT = Path("/app/market_data")
_CANONICAL_CONTROL_ROOT = Path("/app/collection_control")
_CANONICAL_ARTIFACT_ROOT = Path("/app/model_artifacts")
_CANONICAL_REPOSITORY_ROOT = Path("/app")
_NOT_EXECUTED_EXIT = 2
_PREFLIGHT_CACHE_CURRENT_EXIT = 0
_PREFLIGHT_COLLECTION_REQUIRED_EXIT = 10
_RECOVERY_EXIT = 20
_COLLECTOR_UNAVAILABLE_REASONS = frozenset(
    {
        "nas_forward_cache_unavailable",
        "nas_forward_market_data_unavailable",
        "nas_forward_collector_unavailable",
        "nas_forward_runtime_unavailable",
    }
)


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true")
    action.add_argument("--preflight", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=_CANONICAL_CACHE_ROOT)
    parser.add_argument("--control-root", type=Path, default=_CANONICAL_CONTROL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_CANONICAL_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_CANONICAL_REPOSITORY_ROOT)
    parser.add_argument(
        "--frozen-boundary",
        default=KIS_PAPER_DAILY_NAS_FORWARD_FROZEN_BOUNDARY.isoformat(),
    )
    parser.add_argument(
        "--schedule-guard-failed",
        choices=("host_timezone_not_kst",),
    )
    args = parser.parse_args(argv)
    if not args.execute and not args.preflight:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return _NOT_EXECUTED_EXIT
    if args.schedule_guard_failed is not None and not args.preflight:
        print(
            json.dumps({"status": "not_executed", "reason": "preflight_flag_required"})
        )
        return _NOT_EXECUTED_EXIT
    if args.preflight:
        roots_are_valid = _canonical_preflight_roots(
            cache_root=args.cache_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
        )
    else:
        roots_are_valid = _canonical_roots(
            cache_root=args.cache_root,
            control_root=args.control_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
        )
    if not roots_are_valid:
        print(
            json.dumps({"status": "not_executed", "reason": "canonical_container_roots_required"})
        )
        return _NOT_EXECUTED_EXIT
    try:
        frozen_boundary = datetime.fromisoformat(args.frozen_boundary).date()
    except ValueError:
        print(json.dumps({"status": "not_executed", "reason": "frozen_boundary_invalid"}))
        return _NOT_EXECUTED_EXIT
    observed = _require_utc(clock())
    if args.preflight:
        return _run_preflight(
            cache_root=args.cache_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            frozen_boundary=frozen_boundary,
            observed_at=observed,
            schedule_guard_failed=args.schedule_guard_failed,
        )
    return _run_credentialed_collection(
        cache_root=args.cache_root,
        control_root=args.control_root,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        frozen_boundary=frozen_boundary,
        observed_at=observed,
    )


def _run_credentialed_collection(
    *,
    cache_root: Path,
    control_root: Path,
    artifact_root: Path,
    repository_root: Path,
    frozen_boundary: date,
    observed_at: datetime,
) -> int:
    try:
        client = KisPaperMarketDataClient(
            config=load_kis_paper_market_data_environment_config(),
            transport=UrllibKisPaperDailyNasForwardTransport(
                request_gate=KisPaperMarketDataRateGate(control_root=control_root),
                token_start_gate=KisPaperMarketDataTokenStartGate(control_root=control_root),
            ),
            max_daily_page_attempts=6,
        )
        result = collect_kis_paper_daily_nas_forward_once(
            client,
            cache_root=cache_root,
            repository_root=repository_root,
            frozen_boundary=frozen_boundary,
            observed_at=observed_at,
        )
        payload = result.safe_payload()
    except (
        KisPaperDailyNasForwardCacheError,
        KisPaperMarketDataError,
        KisPaperDailyNasForwardError,
        OSError,
        ValueError,
    ) as error:
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_collector_unavailable_payload(observed_at, error=error),
            exit_code=_RECOVERY_EXIT,
        )
    return _emit_source_safe_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
        payload=payload,
        exit_code=(
            _RECOVERY_EXIT
            if result.status in {"partial", "deferred"}
            else 0
        ),
    )


def _run_preflight(
    *,
    cache_root: Path,
    artifact_root: Path,
    repository_root: Path,
    frozen_boundary: date,
    observed_at: datetime,
    schedule_guard_failed: str | None,
) -> int:
    """Reattest the local cache without credentials or a KIS client."""

    if schedule_guard_failed is not None:
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_preflight_unavailable_payload(
                observed_at,
                reason=schedule_guard_failed,
                recovery="restart",
            ),
            exit_code=_RECOVERY_EXIT,
        )
    eligible_through = latest_completed_us_equity_d1_session(observed_at)
    if eligible_through is None:
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_preflight_unavailable_payload(
                observed_at,
                reason="eligible_session_unavailable",
                recovery="resume",
            ),
            exit_code=_RECOVERY_EXIT,
        )
    try:
        with kis_paper_daily_nas_forward_failure_context("verified_base_load"):
            cache = load_verified_kis_paper_daily_nas_forward_cache(
                cache_root=cache_root,
                repo_root=repository_root,
            )
    except (KisPaperDailyNasForwardCacheError, OSError, ValueError) as error:
        if _cache_index_exists(cache_root):
            return _emit_source_safe_receipt(
                artifact_root=artifact_root,
                repository_root=repository_root,
                observed_at=observed_at,
                payload={
                    **_preflight_unavailable_payload(
                        observed_at,
                        reason="forward_cache_reattest_unavailable",
                        recovery="reconcile",
                    ),
                    **get_kis_paper_daily_nas_forward_failure_details(error),
                },
                exit_code=_RECOVERY_EXIT,
            )
        print(
            json.dumps(
                _collection_required_payload(
                    observed_at,
                    eligible_through=eligible_through,
                    cache_payload=None,
                ),
                sort_keys=True,
            )
        )
        return _PREFLIGHT_COLLECTION_REQUIRED_EXIT
    if cache.frozen_boundary != frozen_boundary:
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_preflight_unavailable_payload(
                observed_at,
                reason="forward_cache_boundary_conflict",
                recovery="reconcile",
            ),
            exit_code=_RECOVERY_EXIT,
        )
    targets_ready = all(target.status == "ready" for target in cache.targets_by_key.values())
    if targets_ready and all(
        any(row.session_date == eligible_through for row in cache.rows_by_symbol[symbol])
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_cache_current_payload(
                observed_at,
                eligible_through=eligible_through,
                cache_payload=cache.safe_payload(),
            ),
            exit_code=_PREFLIGHT_CACHE_CURRENT_EXIT,
        )
    print(
        json.dumps(
            _collection_required_payload(
                observed_at,
                eligible_through=eligible_through,
                cache_payload=cache.safe_payload(),
                targets_ready=targets_ready,
            ),
            sort_keys=True,
        )
    )
    return _PREFLIGHT_COLLECTION_REQUIRED_EXIT


def _cache_current_payload(
    observed_at: datetime,
    *,
    eligible_through: date,
    cache_payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "status": "unchanged",
        "reason": "verified_forward_cache_covers_latest_completed_session",
        "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
        "eligible_through_session": eligible_through.isoformat(),
        "configuration_loaded": False,
        "market_data_request_attempt_count": 0,
        "cache": dict(cache_payload),
        "route_isolation": _route_isolation_payload(),
    }


def _collection_required_payload(
    observed_at: datetime,
    *,
    eligible_through: date,
    cache_payload: Mapping[str, object] | None,
    targets_ready: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "collection_required",
        "reason": (
            "forward_cache_missing_latest_completed_session"
            if targets_ready else "forward_cache_targets_not_ready"
        ),
        "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
        "eligible_through_session": eligible_through.isoformat(),
        "configuration_loaded": False,
        "market_data_request_attempt_count": 0,
        "route_isolation": _route_isolation_payload(),
    }
    if cache_payload is not None:
        payload["cache"] = dict(cache_payload)
    return payload


def _preflight_unavailable_payload(
    observed_at: datetime,
    *,
    reason: str,
    recovery: str,
) -> dict[str, object]:
    return {
        "status": "unavailable",
        "reason": reason,
        "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
        "recovery": recovery,
        "configuration_loaded": False,
        "market_data_request_attempt_count": 0,
        "raw_rows_in_payload": False,
        "credentials_in_payload": False,
        "account_or_order_data_in_payload": False,
        "route_isolation": _route_isolation_payload(),
    }


def _collector_unavailable_payload(
    observed_at: datetime,
    *,
    error: BaseException,
) -> dict[str, object]:
    return {
        "status": "unavailable",
        "reason": _collector_unavailable_reason(error),
        **get_kis_paper_daily_nas_forward_failure_details(error),
        "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
        "recovery": "reconcile",
        "raw_rows_in_payload": False,
        "credentials_in_payload": False,
        "account_or_order_data_in_payload": False,
        "route_isolation": _route_isolation_payload(),
    }


def _collector_unavailable_reason(error: BaseException) -> str:
    """Classify the failure boundary without inspecting exception contents."""

    if isinstance(error, KisPaperDailyNasForwardCacheError):
        return "nas_forward_cache_unavailable"
    if isinstance(error, KisPaperMarketDataError):
        return "nas_forward_market_data_unavailable"
    if isinstance(error, KisPaperDailyNasForwardError):
        return "nas_forward_collector_unavailable"
    return "nas_forward_runtime_unavailable"


def _route_isolation_payload() -> dict[str, bool]:
    return {
        "daily_market_data_only": True,
        "account_endpoints_used": False,
        "order_endpoints_used": False,
        "live_endpoints_used": False,
    }


def _cache_index_exists(cache_root: Path) -> bool:
    try:
        return (cache_root / "index.json").is_file()
    except OSError:
        return False


def _emit_source_safe_receipt(
    *,
    artifact_root: Path,
    repository_root: Path,
    observed_at: datetime,
    payload: dict[str, object],
    exit_code: int,
) -> int:
    receipt_payload = dict(payload)
    try:
        receipt_hash = _write_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=receipt_payload,
        )
    except (OSError, ValueError):
        print(json.dumps(payload, sort_keys=True))
        return _RECOVERY_EXIT
    payload["receipt_sha256"] = receipt_hash
    print(json.dumps(payload, sort_keys=True))
    return exit_code


def _write_source_safe_receipt(
    *,
    artifact_root: Path,
    repository_root: Path,
    observed_at: datetime,
    payload: Mapping[str, object],
) -> str:
    if artifact_root.as_posix() != _CANONICAL_ARTIFACT_ROOT.as_posix():
        raise ValueError("NAS forward artifact root is invalid")
    if repository_root.as_posix() != _CANONICAL_REPOSITORY_ROOT.as_posix():
        raise ValueError("NAS forward repository root is invalid")
    if artifact_root.is_symlink():
        raise ValueError("NAS forward artifact root is invalid")
    artifact_root.mkdir(parents=True, exist_ok=True)
    if not artifact_root.is_dir() or artifact_root.is_symlink():
        raise ValueError("NAS forward artifact root is invalid")
    receipt_payload = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    content_hash = "sha256:" + hashlib.sha256(receipt_payload).hexdigest()
    label = observed_at.strftime("%Y%m%dT%H%M%S%fZ")
    destination = artifact_root / f"run={label}-{uuid.uuid4().hex[:12]}"
    destination.mkdir()
    temporary = destination / f".receipt-{uuid.uuid4().hex}.stage"
    try:
        with temporary.open("xb") as handle:
            handle.write(receipt_payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination / "receipt.json")
    finally:
        temporary.unlink(missing_ok=True)
    return content_hash


def _canonical_roots(
    *,
    cache_root: Path,
    control_root: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    return (
        cache_root.as_posix() == _CANONICAL_CACHE_ROOT.as_posix()
        and control_root.as_posix() == _CANONICAL_CONTROL_ROOT.as_posix()
        and artifact_root.as_posix() == _CANONICAL_ARTIFACT_ROOT.as_posix()
        and repository_root.as_posix() == _CANONICAL_REPOSITORY_ROOT.as_posix()
    )


def _canonical_preflight_roots(
    *,
    cache_root: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    return (
        cache_root.as_posix() == _CANONICAL_CACHE_ROOT.as_posix()
        and artifact_root.as_posix() == _CANONICAL_ARTIFACT_ROOT.as_posix()
        and repository_root.as_posix() == _CANONICAL_REPOSITORY_ROOT.as_posix()
    )


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("NAS forward clock must return UTC")
    return value.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
