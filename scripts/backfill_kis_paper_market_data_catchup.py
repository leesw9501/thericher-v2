"""Drain finite private KIS Paper daily-history cursors at the shared safe pace."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_paper_market_data_catchup import (
    KIS_PAPER_MARKET_DATA_CATCHUP_MAX_CHUNKS,
    KIS_PAPER_MARKET_DATA_CATCHUP_MAX_RUNTIME,
    KisPaperMarketDataCatchupResult,
    run_kis_paper_market_data_catchup,
)
from thericher_v2.execution.kis_private_daily_backfill import (
    KisPaperPrivateDailyBackfillRun,
    run_kis_paper_private_daily_backfill_once,
)
from thericher_v2.execution.kis_private_daily_collector import (
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
    sanitize_kis_paper_private_daily_collector_failure_reason,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CATCHUP_RECEIPT_KIND = "kis_paper_market_data_catchup_receipt"
_CATCHUP_RECEIPT_SCHEMA_VERSION = 1


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    dotenv_path: Path = _REPO_ROOT / ".env",
    code_revision: Callable[[Path], str] | None = None,
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--receipt-root", type=Path)
    parser.add_argument("--max-chunks", type=int, default=KIS_PAPER_MARKET_DATA_CATCHUP_MAX_CHUNKS)
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=KIS_PAPER_MARKET_DATA_CATCHUP_MAX_RUNTIME.total_seconds(),
    )
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return
    if args.max_runtime_seconds <= 0:
        parser.error("--max-runtime-seconds must be positive")

    cache_root = Path(args.cache_root)
    repository_root = Path(args.repository_root)
    request_gate = KisPaperMarketDataRateGate(
        control_root=cache_root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    )
    token_start_gate = KisPaperMarketDataTokenStartGate(
        control_root=cache_root.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    )
    revision = (code_revision or _current_code_revision)(repository_root)
    client: KisPaperMarketDataClient | None = None

    def client_factory() -> KisPaperMarketDataClient:
        nonlocal client
        if client is None:
            client = _client(
                load_kis_paper_market_data_config(dotenv_path),
                request_gate=request_gate,
                token_start_gate=token_start_gate,
                max_daily_page_attempts=(
                    args.max_chunks * KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS
                ),
            )
        return client

    def run_daily_chunk() -> KisPaperPrivateDailyBackfillRun:
        return run_kis_paper_private_daily_backfill_once(
            client_factory=client_factory,
            cache_root=cache_root,
            repo_root=repository_root,
            code_revision=revision,
            observed_at=clock(),
            inter_chunk_interval=timedelta(0),
        )

    try:
        result = run_kis_paper_market_data_catchup(
            run_daily_chunk=run_daily_chunk,
            max_chunks=args.max_chunks,
            max_runtime=timedelta(seconds=args.max_runtime_seconds),
            clock=clock,
        )
    except KisPaperMarketDataError as error:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": sanitize_kis_paper_private_daily_collector_failure_reason(error),
                },
                sort_keys=True,
            )
        )
        return
    except (OSError, ValueError):
        print(json.dumps({"status": "indeterminate", "reason": "catchup_worker_unavailable"}))
        return

    payload = _safe_result_payload(result)
    if args.receipt_root is not None:
        payload["receipt_sha256"] = _write_source_safe_receipt(
            receipt_root=Path(args.receipt_root),
            repo_root=repository_root,
            code_revision=revision,
            observed_at=clock(),
            result=result,
            client_constructed=client is not None,
            max_chunks=args.max_chunks,
            max_runtime_seconds=args.max_runtime_seconds,
        )
    print(json.dumps(payload, sort_keys=True))


def _safe_result_payload(result: KisPaperMarketDataCatchupResult) -> dict[str, object]:
    return {
        "status": result.status,
        "chunk_attempt_count": result.chunk_attempt_count,
        "retained_chunk_count": result.retained_chunk_count,
        "completed_target_count": result.completed_target_count,
        "reason": result.last_reason,
    }


def _write_source_safe_receipt(
    *,
    receipt_root: Path,
    repo_root: Path,
    code_revision: str,
    observed_at: datetime,
    result: KisPaperMarketDataCatchupResult,
    client_constructed: bool,
    max_chunks: int,
    max_runtime_seconds: float,
) -> str:
    """Persist one immutable outcome receipt without paths, rows, or credentials."""

    if receipt_root.is_symlink():
        raise ValueError("catch-up receipt root is invalid")
    receipt_root.mkdir(parents=True, exist_ok=True)
    resolved_root = receipt_root.resolve(strict=True)
    resolved_repo = repo_root.resolve()
    if resolved_root.is_relative_to(resolved_repo) and not _is_external_mount_path(
        resolved_root,
        repo_root=resolved_repo,
    ):
        raise ValueError("catch-up receipts must stay outside the Git workspace")
    payload = {
        "schema_version": _CATCHUP_RECEIPT_SCHEMA_VERSION,
        "kind": _CATCHUP_RECEIPT_KIND,
        "observed_at_utc": observed_at.astimezone(UTC).isoformat(),
        "code_revision": code_revision,
        "worker_bounds": {
            "max_chunks": max_chunks,
            "max_runtime_seconds": max_runtime_seconds,
        },
        "outcome": _safe_result_payload(result),
        "execution": {
            "client_constructed": client_constructed,
            "mode": "off",
            "route": "kis_paper_market_data_only",
        },
        "artifact_policy": {
            "raw_market_data_in_receipt": False,
            "credentials_in_receipt": False,
            "account_data_in_receipt": False,
            "broker_order_data_in_receipt": False,
            "repo_storage_allowed": False,
        },
    }
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    content_hash = "sha256:" + hashlib.sha256(encoded).hexdigest()
    stamp = observed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = resolved_root / f"catchup-{stamp}-{uuid.uuid4().hex[:12]}.json"
    with destination.open("xb") as handle:
        handle.write(encoded)
    return content_hash


def _is_external_mount_path(path: Path, *, repo_root: Path) -> bool:
    current = path
    while current != repo_root:
        if current.is_mount():
            return True
        current = current.parent
    return False


def _client(
    config: KisPaperMarketDataConfig,
    *,
    request_gate: KisPaperMarketDataRateGate,
    token_start_gate: KisPaperMarketDataTokenStartGate,
    max_daily_page_attempts: int = KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
) -> KisPaperMarketDataClient:
    return KisPaperMarketDataClient(
        config=config,
        transport=UrllibKisPaperMarketDataTransport(
            request_gate=request_gate,
            token_start_gate=token_start_gate,
        ),
        max_daily_page_attempts=max_daily_page_attempts,
    )


def _current_code_revision(repo_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        ).returncode != 0
    except (OSError, subprocess.SubprocessError):
        return "git:unavailable"
    return f"git:{revision}" + ("+dirty" if dirty else "")


if __name__ == "__main__":
    main()
