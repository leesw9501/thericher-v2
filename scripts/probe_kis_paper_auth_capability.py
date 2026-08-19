"""Run one source-safe, token-only KIS Paper authentication capability probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.data.kis_paper_auth_capability_probe import (
    KIS_PAPER_AUTH_CAPABILITY_PROBE_KIND,
    KisPaperAuthCapabilityProbeOutcome,
    categorize_kis_paper_auth_capability_error,
    write_kis_paper_auth_capability_probe,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_environment_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)

_CANONICAL_CONTROL_ROOT = Path("/app/collection_control")
_CANONICAL_ARTIFACT_ROOT = Path("/app/model_artifacts")
_CANONICAL_REPOSITORY_ROOT = Path("/app")
_NOT_EXECUTED_EXIT = 2
_UNAVAILABLE_EXIT = 20


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--control-root", type=Path, default=_CANONICAL_CONTROL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_CANONICAL_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_CANONICAL_REPOSITORY_ROOT)
    arguments = parser.parse_args(argv)
    if not arguments.execute:
        _emit({"status": "not_executed", "reason": "execute_flag_required"})
        return _NOT_EXECUTED_EXIT
    if not _canonical_roots(
        control_root=arguments.control_root,
        artifact_root=arguments.artifact_root,
        repository_root=arguments.repository_root,
    ):
        _emit({"status": "not_executed", "reason": "canonical_container_roots_required"})
        return _NOT_EXECUTED_EXIT

    observed_at = _require_utc(clock())
    outcome = _run_authentication_probe(
        control_root=arguments.control_root,
        observed_at=observed_at,
    )
    try:
        run = write_kis_paper_auth_capability_probe(
            outcome,
            artifact_root=arguments.artifact_root,
            repo_root=arguments.repository_root,
            run_label=f"auth-capability-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}",
        )
    except (OSError, ValueError):
        _emit(
            {
                "kind": KIS_PAPER_AUTH_CAPABILITY_PROBE_KIND,
                "status": "unavailable",
                "reason": "receipt_unavailable",
            }
        )
        return _UNAVAILABLE_EXIT
    _emit(
        {
            "kind": KIS_PAPER_AUTH_CAPABILITY_PROBE_KIND,
            "status": outcome.status,
            "reason": outcome.reason,
            "receipt_sha256": run.receipt_sha256,
            "receipt_path": str(run.receipt_path),
        }
    )
    return 0 if outcome.status == "authenticated" else _UNAVAILABLE_EXIT


def _run_authentication_probe(
    *,
    control_root: Path,
    observed_at: datetime,
) -> KisPaperAuthCapabilityProbeOutcome:
    try:
        rate_gate = KisPaperMarketDataRateGate(control_root=control_root)
        token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root)
        token_is_due = token_gate.token_request_is_due()
        request_gate_reason = _request_gate_reason(rate_gate, observed_at)
    except (OSError, ValueError):
        return KisPaperAuthCapabilityProbeOutcome(
            status="unavailable",
            observed_at=observed_at,
            reason="control_unavailable",
        )
    if not token_is_due:
        return KisPaperAuthCapabilityProbeOutcome(
            status="unavailable",
            observed_at=observed_at,
            reason="token_request_not_due",
        )
    if request_gate_reason is not None:
        return KisPaperAuthCapabilityProbeOutcome(
            status="unavailable",
            observed_at=observed_at,
            reason=request_gate_reason,
        )
    try:
        config = load_kis_paper_market_data_environment_config()
    except (KisPaperMarketDataError, OSError, ValueError) as error:
        return KisPaperAuthCapabilityProbeOutcome(
            status="unavailable",
            observed_at=observed_at,
            reason=categorize_kis_paper_auth_capability_error(error),
        )
    try:
        client = KisPaperMarketDataClient(
            config=config,
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=rate_gate,
                token_start_gate=token_gate,
            ),
        )
        client.authenticate_token_only()
    except (KisPaperMarketDataError, OSError, ValueError) as error:
        return KisPaperAuthCapabilityProbeOutcome(
            status="unavailable",
            observed_at=observed_at,
            reason=categorize_kis_paper_auth_capability_error(error),
        )
    return KisPaperAuthCapabilityProbeOutcome(status="authenticated", observed_at=observed_at)


def _request_gate_reason(
    rate_gate: KisPaperMarketDataRateGate,
    observed_at: datetime,
) -> str | None:
    snapshot = rate_gate.snapshot()
    if snapshot.retry_not_before_utc is not None and snapshot.retry_not_before_utc > observed_at:
        return "rate_limited"
    if (
        snapshot.last_request_started_at_utc is not None
        and snapshot.last_request_started_at_utc
        + timedelta(seconds=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS)
        > observed_at
    ):
        return "request_not_due"
    return None


def _canonical_roots(
    *,
    control_root: Path,
    artifact_root: Path,
    repository_root: Path,
) -> bool:
    return (
        control_root == _CANONICAL_CONTROL_ROOT
        and artifact_root == _CANONICAL_ARTIFACT_ROOT
        and repository_root == _CANONICAL_REPOSITORY_ROOT
    )


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("clock must return UTC")
    return value.astimezone(UTC)


def _emit(payload: dict[str, object]) -> None:
    _payload = {key: value for key, value in payload.items() if value is not None}
    print(json.dumps(_payload, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
