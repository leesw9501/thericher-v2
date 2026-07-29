"""Collect or reattest the private QQQ/SPY D1 forward cache in Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY,
    KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS,
    KisPaperDailyPairForwardCacheError,
    commit_kis_paper_daily_pair_forward_observation,
    load_verified_kis_paper_daily_pair_forward_cache,
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
from thericher_v2.execution.kis_paper_daily_nas_forward import latest_completed_us_equity_d1_session
from thericher_v2.execution.kis_paper_daily_pair_forward import (
    KisPaperDailyPairForwardError,
    UrllibKisPaperDailyPairForwardTransport,
    collect_kis_paper_daily_pair_forward_once,
)

_CANONICAL_CACHE_ROOT = Path("/app/market_data")
_CANONICAL_CONTROL_ROOT = Path("/app/collection_control")
_CANONICAL_ARTIFACT_ROOT = Path("/app/model_artifacts")
_CANONICAL_REPOSITORY_ROOT = Path("/app")
_NOT_EXECUTED_EXIT = 2
_COLLECTION_REQUIRED_EXIT = 10
_RECOVERY_EXIT = 20
_TARGET_KEYS = tuple(
    f"{symbol}/{exchange}" for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
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
        default=KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY.isoformat(),
    )
    parser.add_argument(
        "--schedule-guard-failed",
        choices=("host_timezone_not_kst", "shared_dispatcher_busy"),
    )
    args = parser.parse_args(argv)
    if not args.execute and not args.preflight:
        _emit({"status": "not_executed", "reason": "execute_flag_required"})
        return _NOT_EXECUTED_EXIT
    if args.schedule_guard_failed is not None and not args.preflight:
        _emit({"status": "not_executed", "reason": "preflight_flag_required"})
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
        _emit({"status": "not_executed", "reason": "canonical_container_roots_required"})
        return _NOT_EXECUTED_EXIT
    try:
        frozen_boundary = datetime.fromisoformat(args.frozen_boundary).date()
    except ValueError:
        _emit({"status": "not_executed", "reason": "frozen_boundary_invalid"})
        return _NOT_EXECUTED_EXIT
    observed_at = _require_utc(clock())
    if args.preflight:
        return _run_preflight(
            cache_root=args.cache_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            frozen_boundary=frozen_boundary,
            observed_at=observed_at,
            schedule_guard_failed=args.schedule_guard_failed,
        )
    return _run_credentialed_collection(
        cache_root=args.cache_root,
        control_root=args.control_root,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        frozen_boundary=frozen_boundary,
        observed_at=observed_at,
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
    rate_gate = KisPaperMarketDataRateGate(control_root=control_root)
    token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root)
    token_request_is_due = token_gate.can_start_token_request()
    rate_gate_is_deferred = _rate_gate_is_deferred(rate_gate, observed_at)
    if not token_request_is_due or rate_gate_is_deferred:
        result = _defer_pair_cache(
            cache_root=cache_root,
            repository_root=repository_root,
            frozen_boundary=frozen_boundary,
            observed_at=observed_at,
            reason="token_request_not_due" if not token_request_is_due else "rate_limited",
        )
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=result.safe_payload(),
            exit_code=_RECOVERY_EXIT,
        )
    try:
        client = KisPaperMarketDataClient(
            config=load_kis_paper_market_data_environment_config(),
            transport=UrllibKisPaperDailyPairForwardTransport(
                request_gate=rate_gate,
                token_start_gate=token_gate,
            ),
            max_daily_page_attempts=2,
        )
        result = collect_kis_paper_daily_pair_forward_once(
            client,
            cache_root=cache_root,
            repository_root=repository_root,
            frozen_boundary=frozen_boundary,
            observed_at=observed_at,
        )
        payload = result.safe_payload()
    except (
        KisPaperDailyPairForwardCacheError,
        KisPaperDailyPairForwardError,
        KisPaperMarketDataError,
        OSError,
        ValueError,
    ):
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_unavailable_payload(observed_at, "collector_unavailable"),
            exit_code=_RECOVERY_EXIT,
        )
    return _emit_source_safe_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
        payload=payload,
        exit_code=_RECOVERY_EXIT if result.status in {"partial", "deferred"} else 0,
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
    """Reattest only local pair-cache state without a KIS or credential path."""

    if schedule_guard_failed is not None:
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_unavailable_payload(observed_at, schedule_guard_failed),
            exit_code=_RECOVERY_EXIT,
        )
    eligible_through = latest_completed_us_equity_d1_session(observed_at)
    if eligible_through is None:
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_unavailable_payload(observed_at, "eligible_session_unavailable"),
            exit_code=_RECOVERY_EXIT,
        )
    try:
        cache = load_verified_kis_paper_daily_pair_forward_cache(
            cache_root=cache_root,
            repo_root=repository_root,
        )
    except (KisPaperDailyPairForwardCacheError, OSError, ValueError):
        cache_exists = _cache_index_exists(cache_root)
        payload = (
            _unavailable_payload(observed_at, "forward_cache_reattest_unavailable")
            if cache_exists
            else _collection_required_payload(observed_at, eligible_through)
        )
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=payload,
            exit_code=_RECOVERY_EXIT if cache_exists else _COLLECTION_REQUIRED_EXIT,
        )
    if cache.frozen_boundary != frozen_boundary:
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=_unavailable_payload(observed_at, "forward_cache_boundary_conflict"),
            exit_code=_RECOVERY_EXIT,
        )
    if all(
        cache.targets_by_key[target_key].latest_session == eligible_through
        for target_key in _TARGET_KEYS
    ) and eligible_through in cache.common_sessions:
        payload = {
            "status": "cache_current",
            "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
            "eligible_through": eligible_through.isoformat(),
            "cache": cache.safe_payload(),
            "route_isolation": _route_isolation_payload(),
        }
        return _emit_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            observed_at=observed_at,
            payload=payload,
            exit_code=0,
        )
    return _emit_source_safe_receipt(
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
        payload=_collection_required_payload(observed_at, eligible_through),
        exit_code=_COLLECTION_REQUIRED_EXIT,
    )


def _defer_pair_cache(
    *,
    cache_root: Path,
    repository_root: Path,
    frozen_boundary: date,
    observed_at: datetime,
    reason: str,
):
    return commit_kis_paper_daily_pair_forward_observation(
        rows_by_target={},
        failure_reasons_by_target={target_key: reason for target_key in _TARGET_KEYS},
        cache_root=cache_root,
        repo_root=repository_root,
        frozen_boundary=frozen_boundary,
        observed_at=observed_at,
    )


def _rate_gate_is_deferred(rate_gate: KisPaperMarketDataRateGate, observed_at: datetime) -> bool:
    snapshot = rate_gate.snapshot()
    return snapshot.retry_not_before_utc is not None and snapshot.retry_not_before_utc > observed_at


def _collection_required_payload(
    observed_at: datetime,
    eligible_through: date,
) -> dict[str, object]:
    return {
        "status": "collection_required",
        "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
        "eligible_through": eligible_through.isoformat(),
        "route_isolation": _route_isolation_payload(),
    }


def _unavailable_payload(observed_at: datetime, reason: str) -> dict[str, object]:
    return {
        "status": "unavailable",
        "reason": reason,
        "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
        "recovery": "resume",
        "route_isolation": _route_isolation_payload(),
    }


def _route_isolation_payload() -> dict[str, bool]:
    return {
        "daily_market_data_only": True,
        "account_endpoints_used": False,
        "position_endpoints_used": False,
        "open_order_endpoints_used": False,
        "quote_endpoints_used": False,
        "order_endpoints_used": False,
        "live_endpoints_used": False,
    }


def _cache_index_exists(cache_root: Path) -> bool:
    path = cache_root / "index.json"
    return path.is_file() and not path.is_symlink()


def _emit_source_safe_receipt(
    *,
    artifact_root: Path,
    repository_root: Path,
    observed_at: datetime,
    payload: Mapping[str, object],
    exit_code: int,
) -> int:
    receipt = {
        "kind": "kis_paper_daily_pair_forward_receipt",
        "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
        "payload": dict(payload),
        "artifact_policy": {
            "raw_market_data_in_receipt": False,
            "credentials_in_receipt": False,
            "account_data_in_receipt": False,
            "repo_storage_allowed": False,
        },
    }
    try:
        path, digest = _write_source_safe_receipt(
            artifact_root=artifact_root,
            repository_root=repository_root,
            receipt=receipt,
        )
    except OSError:
        _emit({"status": "unavailable", "reason": "receipt_unavailable"})
        return _RECOVERY_EXIT
    _emit(
        {
            "status": str(payload.get("status", "unavailable")),
            "receipt_sha256": digest,
            "receipt_path": str(path),
        }
    )
    return exit_code


def _write_source_safe_receipt(
    *,
    artifact_root: Path,
    repository_root: Path,
    receipt: Mapping[str, object],
) -> tuple[Path, str]:
    root = _external_artifact_root(artifact_root, repository_root)
    label = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"run={label}-{uuid.uuid4().hex[:16]}"
    directory.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    path = directory / "receipt.json"
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return path, digest


def _external_artifact_root(root: Path, repository_root: Path) -> Path:
    if root.is_symlink():
        raise OSError("artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    resolved = root.resolve(strict=True)
    repository = repository_root.resolve()
    mounted_artifacts = repository / "model_artifacts"
    if resolved.is_relative_to(repository) and not (
        mounted_artifacts.is_mount() and resolved.is_relative_to(mounted_artifacts)
    ):
        raise OSError("artifact root is inside repository")
    return resolved


def _canonical_roots(
    *,
    cache_root: Path,
    control_root: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    return (
        cache_root == _CANONICAL_CACHE_ROOT
        and control_root == _CANONICAL_CONTROL_ROOT
        and artifact_root == _CANONICAL_ARTIFACT_ROOT
        and repository_root == _CANONICAL_REPOSITORY_ROOT
    )


def _canonical_preflight_roots(
    *,
    cache_root: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    return (
        cache_root == _CANONICAL_CACHE_ROOT
        and artifact_root == _CANONICAL_ARTIFACT_ROOT
        and repository_root == _CANONICAL_REPOSITORY_ROOT
    )


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("clock must return UTC")
    return value.astimezone(UTC)


def _emit(payload: Mapping[str, object]) -> None:
    print(json.dumps(dict(payload), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
