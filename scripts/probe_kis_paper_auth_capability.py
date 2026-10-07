"""Run one source-safe, token-only KIS Paper authentication capability probe."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.data.kis_paper_auth_capability_probe import (
    KIS_PAPER_AUTH_CAPABILITY_PROBE_KIND,
    KisPaperAuthCapabilityProbeOutcome,
    KisPaperAuthPageProbeDetails,
    categorize_kis_paper_auth_capability_error,
    project_kis_paper_token_probe_envelope,
    write_kis_paper_auth_capability_probe,
)
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_MINUTE_PATH,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisMarketDataTransport,
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    KisPaperMinuteQuery,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_environment_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)

_CANONICAL_CONTROL_ROOT = Path("/app/collection_control")
_HEAD_CONTROL_ROOT = Path("/market_data/us_equities/kis_paper_private/collection-control-v1")
_CANONICAL_ARTIFACT_ROOT = Path("/app/model_artifacts")
_CANONICAL_REPOSITORY_ROOT = Path("/app")
_NOT_EXECUTED_EXIT = 2
_UNAVAILABLE_EXIT = 20


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
    pacing_sleeper: Callable[[float], None] = time.sleep,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--head-page-once", action="store_true")
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
        head_page_once=arguments.head_page_once,
    ):
        _emit({"status": "not_executed", "reason": "canonical_container_roots_required"})
        return _NOT_EXECUTED_EXIT

    observed_at = _require_utc(clock())
    if arguments.head_page_once:
        outcome = _run_head_page_probe(
            control_root=arguments.control_root,
            observed_at=observed_at,
            clock=clock,
            monotonic=monotonic,
            pacing_sleeper=pacing_sleeper,
        )
    else:
        outcome = _run_authentication_probe(
            control_root=arguments.control_root,
            observed_at=observed_at,
        )
    try:
        run = write_kis_paper_auth_capability_probe(
            outcome,
            artifact_root=arguments.artifact_root,
            repo_root=arguments.repository_root,
            run_label=("auth-page-" if arguments.head_page_once else "auth-capability-")
            + observed_at.strftime("%Y%m%dT%H%M%S%fZ"),
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
            "page_probe": outcome.page_probe.safe_payload() if outcome.page_probe else None,
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


class _ProbeTransport:
    """In-memory observation around the unchanged guarded transport."""

    def __init__(
        self,
        delegate: KisMarketDataTransport,
        *,
        deadline: float,
        monotonic: Callable[[], float],
    ) -> None:
        self._delegate = delegate
        self._deadline = deadline
        self._monotonic = monotonic
        self.token_calls = 0
        self.page_calls = 0
        self.token_envelope = None

    def check_deadline(self, _started_at: datetime | None = None) -> None:
        if self._monotonic() >= self._deadline:
            raise KisPaperMarketDataError("probe_expired")

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        self.check_deadline()
        is_token = request.method == "POST" and request.url == (
            KIS_PAPER_MARKET_DATA_BASE_URL + KIS_PAPER_TOKEN_PATH
        )
        is_page = (
            request.method == "GET"
            and request.url == KIS_PAPER_MARKET_DATA_BASE_URL + KIS_PAPER_MINUTE_PATH
            and request.query.get("SYMB") == "QQQ"
            and request.query.get("EXCD") == "NAS"
            and request.query.get("PINC") == "0"
            and not request.query.get("KEYB")
            and not request.query.get("NEXT")
        )
        if not is_token and not is_page:
            raise KisPaperMarketDataError("probe_request_not_allowed")
        if (is_token and self.token_calls) or (
            is_page and (self.page_calls or not self.token_calls)
        ):
            raise KisPaperMarketDataError("probe_request_budget_exhausted")
        if is_token:
            self.token_calls += 1
        else:
            self.page_calls += 1
        response = self._delegate.request(request)
        if is_token:
            self.token_envelope = project_kis_paper_token_probe_envelope(response)
        return response


def _run_head_page_probe(
    *,
    control_root: Path,
    observed_at: datetime,
    clock: Callable[[], datetime],
    monotonic: Callable[[], float],
    pacing_sleeper: Callable[[float], None] = time.sleep,
) -> KisPaperAuthCapabilityProbeOutcome:
    deadline = monotonic() + 60.0
    transport: _ProbeTransport | None = None
    rate_gate: KisPaperMarketDataRateGate | None = None
    token_gate: KisPaperMarketDataTokenStartGate | None = None
    token_status = "not_attempted"
    page_status = "not_attempted"
    accepted_rows = 0
    reason: str | None = None
    last_owned_request_start: datetime | None = None
    remaining_pacing = KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS

    def check_deadline(_started_at: datetime | None = None) -> None:
        nonlocal last_owned_request_start
        if monotonic() >= deadline:
            raise KisPaperMarketDataError("probe_expired")
        if _started_at is not None:
            last_owned_request_start = _started_at

    def bounded_pacing_sleep(seconds: float) -> None:
        nonlocal remaining_pacing
        assert rate_gate is not None
        snapshot = rate_gate.snapshot()
        if snapshot.retry_not_before_utc is not None and snapshot.retry_not_before_utc > clock():
            raise KisPaperMarketDataError("rate_limited")
        if (
            token_status != "accepted"
            or last_owned_request_start is None
            or snapshot.last_request_started_at_utc != last_owned_request_start
            or not 0 < seconds <= remaining_pacing
        ):
            raise KisPaperMarketDataError("request_not_due")
        if monotonic() + seconds >= deadline:
            raise KisPaperMarketDataError("probe_expired")
        remaining_pacing -= seconds
        pacing_sleeper(seconds)
        check_deadline()

    try:
        rate_gate = KisPaperMarketDataRateGate(
            control_root=control_root,
            clock=clock,
            sleeper=bounded_pacing_sleep,
            on_request_started=check_deadline,
        )
        token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root, clock=clock)
        if not token_gate.token_request_is_due():
            raise KisPaperMarketDataError("token_request_not_due")
        gate_reason = _request_gate_reason(rate_gate, clock())
        if gate_reason is not None:
            raise KisPaperMarketDataError(gate_reason)
        check_deadline()
        config = load_kis_paper_market_data_environment_config()
        transport = _ProbeTransport(
            UrllibKisPaperMarketDataTransport(
                timeout_seconds=15.0,
                request_gate=rate_gate,
                token_start_gate=token_gate,
            ),
            deadline=deadline,
            monotonic=monotonic,
        )
        client = KisPaperMarketDataClient(
            config=config,
            transport=transport,
            max_minute_page_attempts=1,
        )
        client.ensure_authenticated()
        token_status = "accepted"
        page_status = "deferred"
        check_deadline()
        gate_reason = _request_gate_reason(rate_gate, clock())
        if gate_reason == "rate_limited":
            raise KisPaperMarketDataError(gate_reason)
        page = client.fetch_minute_page(KisPaperMinuteQuery(symbol="QQQ", exchange="NAS"))
        accepted_rows = len(page.bars)
        del page
        page_status = "nonempty"
    except (KisPaperMarketDataError, OSError, ValueError) as error:
        reason = categorize_kis_paper_auth_capability_error(error, page_probe=True)
        if token_status != "accepted":
            local_without_http = reason in {
                "token_request_not_due",
                "request_not_due",
                "rate_limited",
                "probe_expired",
                "probe_request_not_allowed",
                "probe_request_budget_exhausted",
            } and (transport is None or transport.token_envelope is None)
            token_status = (
                "unavailable"
                if transport and transport.token_calls and not local_without_http
                else "not_attempted"
            )
        elif transport and transport.page_calls:
            page_status = {
                "minute_response_empty": "empty",
                "minute_response_invalid": "invalid",
                "response_invalid": "invalid",
                "minute_response_rejected": "rejected",
            }.get(reason, "deferred")

    next_due = None
    if reason in {"token_request_not_due", "request_not_due", "rate_limited"}:
        try:
            due_times = []
            if token_status != "accepted" and token_gate is not None:
                due = token_gate.snapshot().next_token_request_not_before_utc
                if due is not None:
                    due_times.append(due)
            if rate_gate is not None:
                snapshot = rate_gate.snapshot()
                if snapshot.retry_not_before_utc is not None:
                    due_times.append(snapshot.retry_not_before_utc)
                if snapshot.last_request_started_at_utc is not None:
                    due_times.append(
                        snapshot.last_request_started_at_utc
                        + timedelta(seconds=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS)
                    )
            next_due = max(due_times, default=None)
        except (OSError, ValueError):
            pass
    details = KisPaperAuthPageProbeDetails(
        completed_at=_require_utc(clock()),
        token_status=token_status,
        page_status=page_status,
        token_transport_calls=transport.token_calls if transport else 0,
        page_transport_calls=transport.page_calls if transport else 0,
        accepted_rows=accepted_rows,
        token_envelope=transport.token_envelope if transport else None,
        next_due=next_due,
    )
    return KisPaperAuthCapabilityProbeOutcome(
        status="authenticated" if page_status == "nonempty" else "unavailable",
        observed_at=observed_at,
        reason=reason,
        page_probe=details,
    )


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
    head_page_once: bool = False,
) -> bool:
    return (
        (
            control_root == _CANONICAL_CONTROL_ROOT
            or (head_page_once and control_root == _HEAD_CONTROL_ROOT)
        )
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
