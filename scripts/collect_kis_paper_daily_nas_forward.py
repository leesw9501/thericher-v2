"""Collect one private, current-D1 NAS forward-cache observation in Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    KIS_PAPER_DAILY_NAS_FORWARD_FROZEN_BOUNDARY,
    KisPaperDailyNasForwardCacheError,
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
)

_CANONICAL_CACHE_ROOT = Path("/app/market_data")
_CANONICAL_CONTROL_ROOT = Path("/app/collection_control")
_CANONICAL_ARTIFACT_ROOT = Path("/app/model_artifacts")
_CANONICAL_REPOSITORY_ROOT = Path("/app")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=_CANONICAL_CACHE_ROOT)
    parser.add_argument("--control-root", type=Path, default=_CANONICAL_CONTROL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_CANONICAL_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_CANONICAL_REPOSITORY_ROOT)
    parser.add_argument(
        "--frozen-boundary",
        default=KIS_PAPER_DAILY_NAS_FORWARD_FROZEN_BOUNDARY.isoformat(),
    )
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return
    if not _canonical_roots(
        cache_root=args.cache_root,
        control_root=args.control_root,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
    ):
        print(
            json.dumps({"status": "not_executed", "reason": "canonical_container_roots_required"})
        )
        return
    try:
        frozen_boundary = datetime.fromisoformat(args.frozen_boundary).date()
    except ValueError:
        print(json.dumps({"status": "not_executed", "reason": "frozen_boundary_invalid"}))
        return
    observed = _require_utc(clock())
    try:
        client = KisPaperMarketDataClient(
            config=load_kis_paper_market_data_environment_config(),
            transport=UrllibKisPaperDailyNasForwardTransport(
                request_gate=KisPaperMarketDataRateGate(control_root=args.control_root),
                token_start_gate=KisPaperMarketDataTokenStartGate(control_root=args.control_root),
            ),
            max_daily_page_attempts=6,
        )
        result = collect_kis_paper_daily_nas_forward_once(
            client,
            cache_root=args.cache_root,
            repository_root=args.repository_root,
            frozen_boundary=frozen_boundary,
            observed_at=observed,
        )
        payload = result.safe_payload()
        receipt_hash = _write_source_safe_receipt(
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            observed_at=observed,
            payload=payload,
        )
    except (
        KisPaperDailyNasForwardCacheError,
        KisPaperMarketDataError,
        KisPaperDailyNasForwardError,
        OSError,
        ValueError,
    ):
        payload = _unavailable_payload(observed)
        try:
            receipt_hash = _write_source_safe_receipt(
                artifact_root=args.artifact_root,
                repository_root=args.repository_root,
                observed_at=observed,
                payload=payload,
            )
        except (OSError, ValueError):
            receipt_hash = None
        if receipt_hash is not None:
            payload["receipt_sha256"] = receipt_hash
        print(json.dumps(payload, sort_keys=True))
        return
    payload["receipt_sha256"] = receipt_hash
    print(json.dumps(payload, sort_keys=True))


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


def _unavailable_payload(observed_at: datetime) -> dict[str, object]:
    return {
        "status": "unavailable",
        "reason": "nas_forward_collection_unavailable",
        "observed_at_bucket": observed_at.strftime("%Y-%m-%dT%H:00Z"),
        "recovery": "reconcile",
        "raw_rows_in_payload": False,
        "credentials_in_payload": False,
        "account_or_order_data_in_payload": False,
        "route_isolation": {
            "daily_market_data_only": True,
            "account_endpoints_used": False,
            "order_endpoints_used": False,
            "live_endpoints_used": False,
        },
    }


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


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("NAS forward clock must return UTC")
    return value.astimezone(UTC)


if __name__ == "__main__":
    main()
