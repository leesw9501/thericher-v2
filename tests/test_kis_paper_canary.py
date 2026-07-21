from __future__ import annotations

import json
import threading
import urllib.error
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution.kis_paper_canary import (
    KIS_PAPER_US_BUY_LIMIT_ORDER_PATH,
    KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID,
    KIS_PAPER_US_CANCEL_TR_ID,
    KIS_PAPER_US_CCNCL_PATH,
    KIS_PAPER_US_CCNCL_TR_ID,
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryIntent,
    KisPaperCanaryState,
    UrllibKisPaperCanaryTransport,
    run_kis_paper_canary,
)
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_BASE_URL,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperConfig,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    KisPaperRequestPacer,
)
from thericher_v2.execution.paper_account_snapshot import read_paper_account_snapshot
from thericher_v2.execution.paper_canary_runtime import read_paper_canary_runtime
from thericher_v2.research.kis_paper_canary_intent import KisPaperCanaryBuyDecision

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


@dataclass
class FakeKisPaperCanaryTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)
    fail_auth: bool = False
    fail_submit: bool = False
    submit_status_code: int | None = None
    submit_result_code: str | None = None
    retain_open_order_after_cancel: bool = False
    matching_ccnl_after_cancel: bool = False
    cancellation_seen: bool = False
    order_open: bool = False

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        tr_id = request.headers.get("tr_id", "")
        if request.method == "POST" and request.url.endswith("/oauth2/tokenP"):
            if self.fail_auth:
                return KisHttpResponse.from_payload({"error": "invalid"}, status_code=403)
            return KisHttpResponse.from_payload({"access_token": "test-access-token"})
        if tr_id == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID:
            if self.fail_submit:
                raise KisPaperCanaryError("transport_failure")
            if self.submit_status_code is not None:
                return KisHttpResponse.from_payload(
                    {"error": "temporary"},
                    status_code=self.submit_status_code,
                )
            if self.submit_result_code is not None:
                return KisHttpResponse.from_payload({"rt_cd": self.submit_result_code})
            self.order_open = True
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": {"ODNO": "ORD-123456789"}})
        if tr_id == KIS_PAPER_US_CANCEL_TR_ID:
            self.cancellation_seen = True
            if not self.retain_open_order_after_cancel:
                self.order_open = False
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": {}})
        if tr_id == KIS_PAPER_US_CCNCL_TR_ID:
            if self.matching_ccnl_after_cancel and self.cancellation_seen:
                return KisHttpResponse.from_payload(
                    {"rt_cd": "0", "output": [{"odno": "ORD-123456789"}]}
                )
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
            if self.order_open:
                if request.query["OVRS_EXCG_CD"] == "NASD":
                    return KisHttpResponse.from_payload(
                        {"rt_cd": "0", "output": [_matching_open_order_payload()]}
                    )
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
        if tr_id == KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "tr_crcy_cd": "USD",
                        "ord_psbl_frcr_amt": "1200.50",
                        "ovrs_ord_psbl_amt": "1199.75",
                    },
                }
            )
        raise AssertionError(f"unexpected KIS request: {request!r}")


@dataclass
class RecordingTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        raise AssertionError("invalid request reached injected transport")


class BlockingKisPaperCanaryTransport(FakeKisPaperCanaryTransport):
    def __init__(self) -> None:
        super().__init__()
        self.buy_started = threading.Event()
        self.release_buy = threading.Event()

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        if (
            request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
            and not self.buy_started.is_set()
        ):
            self.buy_started.set()
            assert self.release_buy.wait(timeout=5)
        return super().request(request)


def _paper_post_headers() -> dict[str, str]:
    return {
        "authorization": "Bearer test-token",
        "appkey": "paper-app-key",
        "appsecret": "paper-app-secret",
        "tr_id": KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID,
        "custtype": "P",
        "content-type": "application/json",
        "accept": "application/json",
    }


def _buy_limit_body() -> dict[str, str]:
    return {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",
        "PDNO": "QQQ",
        "ORD_QTY": "1",
        "OVRS_ORD_UNPR": "500.25",
        "CTAC_TLNO": "",
        "MGCO_APTM_ODNO": "",
        "SLL_TYPE": "",
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN": "00",
    }


def _ccnl_query() -> dict[str, str]:
    return {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "PDNO": "",
        "ORD_STRT_DT": "20260722",
        "ORD_END_DT": "20260722",
        "SLL_BUY_DVSN": "00",
        "CCLD_NCCS_DVSN": "00",
        "OVRS_EXCG_CD": "",
        "SORT_SQN": "DS",
        "ORD_DT": "",
        "ORD_GNO_BRNO": "",
        "ODNO": "",
        "CTX_AREA_NK200": "",
        "CTX_AREA_FK200": "",
    }


def _canary_transport_request() -> KisHttpRequest:
    return KisHttpRequest(
        method="POST",
        url=f"{KIS_PAPER_BASE_URL}{KIS_PAPER_US_BUY_LIMIT_ORDER_PATH}",
        headers=_paper_post_headers(),
        json_body=_buy_limit_body(),
    )


class _PacingResponse:
    status = 200
    headers: dict[str, str] = {}

    def __enter__(self) -> _PacingResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"rt_cd":"0","output":{}}'


def test_real_canary_transport_uses_shared_monotonic_pacing(monkeypatch) -> None:
    current_time = [200.0]
    sleep_calls: list[float] = []
    dispatch_times: list[float] = []

    def monotonic_clock() -> float:
        return current_time[0]

    def sleeper(delay: float) -> None:
        sleep_calls.append(delay)
        current_time[0] += delay

    class RecordingOpener:
        def open(self, _request: object, *, timeout: float) -> _PacingResponse:
            assert timeout == 15.0
            dispatch_times.append(monotonic_clock())
            return _PacingResponse()

    transport = UrllibKisPaperCanaryTransport(
        pacer=KisPaperRequestPacer(
            monotonic_clock=monotonic_clock,
            sleeper=sleeper,
        )
    )
    monkeypatch.setattr(transport, "_opener", RecordingOpener())
    request = _canary_transport_request()

    transport.request(request)
    transport.request(request)
    transport.request(request)

    assert dispatch_times == [200.0, 201.0, 202.0]
    assert sleep_calls == [1.0, 1.0]


def test_real_canary_transport_paces_after_a_failed_external_attempt(monkeypatch) -> None:
    current_time = [75.0]
    sleep_calls: list[float] = []
    dispatch_times: list[float] = []

    def monotonic_clock() -> float:
        return current_time[0]

    def sleeper(delay: float) -> None:
        sleep_calls.append(delay)
        current_time[0] += delay

    class FirstAttemptFails:
        attempts = 0

        def open(self, _request: object, *, timeout: float) -> _PacingResponse:
            assert timeout == 15.0
            self.attempts += 1
            dispatch_times.append(monotonic_clock())
            if self.attempts == 1:
                raise urllib.error.URLError("temporary-test-failure")
            return _PacingResponse()

    transport = UrllibKisPaperCanaryTransport(
        pacer=KisPaperRequestPacer(
            monotonic_clock=monotonic_clock,
            sleeper=sleeper,
        )
    )
    monkeypatch.setattr(transport, "_opener", FirstAttemptFails())
    request = _canary_transport_request()

    with pytest.raises(KisPaperCanaryError, match="transport_failure"):
        transport.request(request)
    transport.request(request)

    assert dispatch_times == [75.0, 76.0]
    assert sleep_calls == [1.0]


def test_real_canary_transport_rejects_invalid_request_before_pacing(monkeypatch) -> None:
    sleep_calls: list[float] = []
    open_calls: list[object] = []

    class FailingOpener:
        def open(self, request: object, *, timeout: float) -> None:
            open_calls.append(request)
            raise AssertionError(f"invalid request reached opener with timeout {timeout}")

    transport = UrllibKisPaperCanaryTransport(
        pacer=KisPaperRequestPacer(sleeper=sleep_calls.append)
    )
    monkeypatch.setattr(transport, "_opener", FailingOpener())
    invalid_request = KisHttpRequest(
        method="POST",
        url="https://openapi.koreainvestment.com:9443/uapi/overseas-stock/v1/trading/order",
        headers=_paper_post_headers(),
        json_body=_buy_limit_body(),
    )

    with pytest.raises(KisPaperCanaryError, match="paper_host_required"):
        transport.request(invalid_request)

    assert sleep_calls == []
    assert open_calls == []


def test_injected_clients_reject_live_or_unallowlisted_routes_before_transport() -> None:
    transport = RecordingTransport()
    config = _config()
    live_request = KisHttpRequest(
        method="POST",
        url="https://openapi.koreainvestment.com:9443/uapi/overseas-stock/v1/trading/order",
        headers={"content-type": "application/json", "accept": "application/json"},
        json_body={"grant_type": "client_credentials", "appkey": "test", "appsecret": "test"},
    )

    with pytest.raises(KisPaperReadOnlyError, match="paper_host_required"):
        KisPaperReadOnlyClient(config=config, transport=transport)._dispatch(live_request)
    with pytest.raises(KisPaperCanaryError, match="paper_host_required"):
        KisPaperCanaryClient(config=config, transport=transport)._dispatch(live_request)

    assert transport.requests == []


@pytest.mark.parametrize(
    "candidate_request",
    [
        KisHttpRequest(
            method="POST",
            url=(
                "https://openapivts.koreainvestment.com:29443"
                f"{KIS_PAPER_US_BUY_LIMIT_ORDER_PATH}"
            ),
            headers={
                **_paper_post_headers(),
                "tr_id": "VTTT9999U",
            },
            json_body=_buy_limit_body(),
        ),
        KisHttpRequest(
            method="POST",
            url=(
                "https://openapivts.koreainvestment.com:29443"
                f"{KIS_PAPER_US_BUY_LIMIT_ORDER_PATH}"
            ),
            headers=_paper_post_headers(),
            json_body={**_buy_limit_body(), "ORD_DVSN": "01"},
        ),
        KisHttpRequest(
            method="GET",
            url=(
                "https://openapivts.koreainvestment.com:29443"
                f"{KIS_PAPER_US_CCNCL_PATH}"
            ),
            headers={
                "authorization": "Bearer test-token",
                "appkey": "paper-app-key",
                "appsecret": "paper-app-secret",
                "tr_id": KIS_PAPER_US_CCNCL_TR_ID,
                "custtype": "P",
                "tr_cont": "",
            },
            query={**_ccnl_query(), "SLL_BUY_DVSN": "02"},
        ),
    ],
    ids=("wrong_tr_id", "wrong_buy_body", "wrong_ccnl_query"),
)
def test_canary_allowlist_rejects_bad_header_body_or_query_before_transport(
    candidate_request: KisHttpRequest,
) -> None:
    transport = RecordingTransport()
    client = KisPaperCanaryClient(config=_config(), transport=transport)

    with pytest.raises(KisPaperCanaryError, match="request_not_allowlisted"):
        client._dispatch(candidate_request)

    assert transport.requests == []


def test_preview_persists_intent_without_credentials_or_network(tmp_path: Path) -> None:
    class UnusedEnvironment(dict[str, str]):
        def get(self, key: str, default: str = "") -> str:
            raise AssertionError(f"preview must not read environment: {key}")

    transport = RecordingTransport()
    outcome = run_kis_paper_canary(
        decision=_decision(),
        run_id="preview-1",
        environment=UnusedEnvironment(),
        state_path=tmp_path / "private" / "preview-1.json",
        runtime_projection_path=tmp_path / "runtime" / "canary.json",
        paper_account_snapshot_path=tmp_path / "runtime" / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=False,
        cancel_after_submit=False,
        transport=transport,
        now=NOW,
    )

    assert outcome.phase == "intent_recorded"
    assert outcome.reason_code == "preview"
    assert transport.requests == []
    assert read_paper_canary_runtime(outcome.runtime_path, now=NOW).snapshot is not None
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert "QQQ" not in evidence
    assert "500.25" not in evidence


def test_expired_intent_never_reads_credentials_or_submits(tmp_path: Path) -> None:
    class UnusedEnvironment(dict[str, str]):
        def get(self, key: str, default: str = "") -> str:
            raise AssertionError(f"expired intent must not read environment: {key}")

    transport = RecordingTransport()
    outcome = run_kis_paper_canary(
        decision=_decision(),
        run_id="expired-1",
        environment=UnusedEnvironment(),
        state_path=tmp_path / "private" / "expired-1.json",
        runtime_projection_path=tmp_path / "runtime" / "canary.json",
        paper_account_snapshot_path=tmp_path / "runtime" / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        transport=transport,
        now=NOW + timedelta(minutes=6),
    )

    assert outcome.phase == "intent_recorded"
    assert outcome.reason_code == "intent_expired"
    assert transport.requests == []


def test_bind_mounted_docker_artifact_root_is_allowed_without_allowing_git_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    mounted_artifacts = repository_root / "model_artifacts"

    monkeypatch.setattr(
        Path,
        "is_mount",
        lambda path: path.resolve() == mounted_artifacts.resolve(),
    )
    outcome = run_kis_paper_canary(
        decision=_decision(),
        run_id="mounted-artifact-1",
        environment={},
        state_path=tmp_path / "private" / "mounted-artifact-1.json",
        runtime_projection_path=tmp_path / "runtime" / "canary.json",
        paper_account_snapshot_path=tmp_path / "runtime" / "account.json",
        emergency_state_path=tmp_path / "emergency.json",
        artifact_root=mounted_artifacts,
        repository_root=repository_root,
        execute=False,
        cancel_after_submit=False,
        now=NOW,
    )

    assert outcome.evidence_path.is_relative_to(mounted_artifacts)


def test_virtual_buy_canary_submits_once_cancels_and_publishes_only_sanitized_state(
    tmp_path: Path,
) -> None:
    transport = FakeKisPaperCanaryTransport()
    state_path = tmp_path / "private" / "canary-1.json"
    runtime_path = tmp_path / "runtime" / "canary.json"
    account_path = tmp_path / "runtime" / "account.json"
    outcome = run_kis_paper_canary(
        decision=_decision(),
        run_id="canary-1",
        environment=_paper_environment(),
        state_path=state_path,
        runtime_projection_path=runtime_path,
        paper_account_snapshot_path=account_path,
        emergency_state_path=tmp_path / "emergency.json",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path / "repo",
        execute=True,
        cancel_after_submit=True,
        transport=transport,
        now=NOW,
    )

    assert outcome.phase == "cancelled"
    assert outcome.reconciliation.status == "clean"
    assert [request.headers.get("tr_id") for request in transport.requests].count(
        KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
    ) == 1
    assert [request.headers.get("tr_id") for request in transport.requests].count(
        KIS_PAPER_US_CANCEL_TR_ID
    ) == 1
    assert all(
        request.url.startswith("https://openapivts.koreainvestment.com:29443/")
        for request in transport.requests
    )
    buy_request = next(
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
    )
    assert buy_request.json_body is not None
    assert buy_request.json_body["ORD_DVSN"] == "00"
    assert buy_request.json_body["ORD_QTY"] == "1"
    assert buy_request.json_body["OVRS_EXCG_CD"] == "NASD"

    runtime = read_paper_canary_runtime(runtime_path, now=NOW)
    assert runtime.status == "available"
    assert runtime.snapshot is not None
    assert runtime.snapshot.status == "cancelled"
    assert runtime.snapshot.order_reference is not None
    assert read_paper_account_snapshot(account_path, now=NOW).status == "available"

    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in ("paper-app-secret", "12345678", "ORD-123456789", "QQQ", "500.25"):
        assert forbidden not in evidence
    assert "ORD-123456789" in state_path.read_text(encoding="utf-8")


def test_unknown_submission_reconciles_without_duplicate_submit(tmp_path: Path) -> None:
    transport = FakeKisPaperCanaryTransport(fail_submit=True)
    state_path = tmp_path / "private" / "unknown-1.json"
    paths = _paths(tmp_path)
    first = run_kis_paper_canary(
        decision=_decision(),
        run_id="unknown-1",
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=NOW,
        **paths,
    )

    assert first.phase == "outcome_unknown"
    assert _submission_count(transport) == 1

    transport.fail_submit = False
    second = run_kis_paper_canary(
        decision=_decision(decision_as_of=NOW + timedelta(minutes=1)),
        run_id="unknown-1",
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=NOW + timedelta(minutes=1),
        **paths,
    )

    assert second.phase == "outcome_unknown"
    assert _submission_count(transport) == 1


def test_non_success_submit_response_is_unknown_and_never_resubmitted(tmp_path: Path) -> None:
    transport = FakeKisPaperCanaryTransport(submit_status_code=503)
    state_path = tmp_path / "private" / "http-unknown-1.json"
    paths = _paths(tmp_path)
    first = run_kis_paper_canary(
        decision=_decision(),
        run_id="http-unknown-1",
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=NOW,
        **paths,
    )

    assert first.phase == "outcome_unknown"
    assert first.reason_code == "submit_transport_unknown"
    assert _submission_count(transport) == 1

    transport.submit_status_code = None
    second = run_kis_paper_canary(
        decision=_decision(decision_as_of=NOW + timedelta(minutes=1)),
        run_id="http-unknown-1",
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=NOW + timedelta(minutes=1),
        **paths,
    )

    assert second.phase == "outcome_unknown"
    assert _submission_count(transport) == 1


def test_non_success_submit_result_is_unknown_and_never_resubmitted(tmp_path: Path) -> None:
    transport = FakeKisPaperCanaryTransport(submit_result_code="1")
    state_path = tmp_path / "private" / "result-unknown-1.json"
    paths = _paths(tmp_path)
    first = run_kis_paper_canary(
        decision=_decision(),
        run_id="result-unknown-1",
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=NOW,
        **paths,
    )

    assert first.phase == "outcome_unknown"
    assert first.reason_code == "submit_transport_unknown"
    assert _submission_count(transport) == 1

    transport.submit_result_code = None
    second = run_kis_paper_canary(
        decision=_decision(decision_as_of=NOW + timedelta(minutes=1)),
        run_id="result-unknown-1",
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=NOW + timedelta(minutes=1),
        **paths,
    )

    assert second.phase == "outcome_unknown"
    assert _submission_count(transport) == 1


def test_recovery_resumes_durable_cancel_after_acknowledged_submit(tmp_path: Path) -> None:
    decision = _decision()
    run_id = "recover-cancel-1"
    intent = KisPaperCanaryIntent.from_decision(decision, run_id=run_id)
    state = KisPaperCanaryState(
        intent=intent,
        phase="submitted",
        updated_at=NOW,
        reason_code="reconciliation_unresolved",
        broker_order_id="ORD-123456789",
        cancel_after_submit=True,
    )
    state_path = tmp_path / "private" / f"{run_id}.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    transport = FakeKisPaperCanaryTransport(order_open=True)

    outcome = run_kis_paper_canary(
        decision=decision,
        run_id=run_id,
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=NOW,
        **_paths(tmp_path),
    )

    assert outcome.phase == "cancelled"
    assert transport.cancellation_seen is True
    assert _submission_count(transport) == 0


def test_different_run_ids_cannot_submit_concurrently(tmp_path: Path) -> None:
    transport = BlockingKisPaperCanaryTransport()
    paths = _paths(tmp_path)
    failures: list[BaseException] = []

    def run(run_id: str) -> None:
        try:
            run_kis_paper_canary(
                decision=_decision(),
                run_id=run_id,
                environment=_paper_environment(),
                state_path=tmp_path / "private" / f"{run_id}.json",
                execute=True,
                cancel_after_submit=False,
                transport=transport,
                now=NOW,
                **paths,
            )
        except BaseException as error:  # pragma: no cover - surfaced below.
            failures.append(error)

    first = threading.Thread(target=run, args=("concurrent-1",))
    second = threading.Thread(target=run, args=("concurrent-2",))
    first.start()
    assert transport.buy_started.wait(timeout=5)
    second.start()

    assert _token_request_count(transport) == 1
    transport.release_buy.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    assert _submission_count(transport) == 1


def test_reconciliation_preserves_only_safe_auth_failure_detail(tmp_path: Path) -> None:
    transport = FakeKisPaperCanaryTransport(fail_auth=True)
    state_path = tmp_path / "private" / "auth-failure-1.json"
    paths = _paths(tmp_path)
    outcome = run_kis_paper_canary(
        decision=_decision(),
        run_id="auth-failure-1",
        environment=_paper_environment(),
        state_path=state_path,
        execute=True,
        cancel_after_submit=False,
        transport=transport,
        now=NOW,
        **paths,
    )

    assert outcome.phase == "intent_recorded"
    assert outcome.reason_code == "reconciliation_unavailable"
    assert outcome.reconciliation.reason_code == "auth_rejected"
    assert outcome.safe_payload()["reconciliation_reason_code"] == "auth_rejected"
    assert _submission_count(transport) == 0

    runtime = read_paper_canary_runtime(paths["runtime_projection_path"], now=NOW)
    assert runtime.status == "available"
    assert runtime.snapshot is not None
    assert runtime.snapshot.reconciliation_reason_code == "auth_rejected"

    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert '"reason_code":"auth_rejected"' in evidence
    for forbidden in ("paper-app-secret", "12345678", "test-access-token"):
        assert forbidden not in evidence


def test_successful_cancel_is_not_reported_clean_while_matching_order_remains(
    tmp_path: Path,
) -> None:
    transport = FakeKisPaperCanaryTransport(retain_open_order_after_cancel=True)
    outcome = run_kis_paper_canary(
        decision=_decision(),
        run_id="stale-open-1",
        environment=_paper_environment(),
        state_path=tmp_path / "private" / "stale-open-1.json",
        execute=True,
        cancel_after_submit=True,
        transport=transport,
        now=NOW,
        **_paths(tmp_path),
    )

    assert outcome.phase == "outcome_unknown"
    assert outcome.reason_code == "reconciliation_unresolved"
    assert outcome.reconciliation.matching_open_order is True


def test_cancel_with_matching_completion_is_not_reported_clean(tmp_path: Path) -> None:
    transport = FakeKisPaperCanaryTransport(matching_ccnl_after_cancel=True)
    outcome = run_kis_paper_canary(
        decision=_decision(),
        run_id="completion-after-cancel-1",
        environment=_paper_environment(),
        state_path=tmp_path / "private" / "completion-after-cancel-1.json",
        execute=True,
        cancel_after_submit=True,
        transport=transport,
        now=NOW,
        **_paths(tmp_path),
    )

    assert outcome.phase == "outcome_unknown"
    assert outcome.reason_code == "reconciliation_unresolved"
    assert outcome.reconciliation.matching_ccnl is True


def _config() -> KisPaperConfig:
    return KisPaperConfig(
        app_key="paper-app-key",
        app_secret="paper-app-secret",
        account_number="12345678",
        account_product_code="01",
    )


def _paper_environment() -> dict[str, str]:
    return {
        "KIS_PAPER_APP_KEY": "paper-app-key",
        "KIS_PAPER_APP_SECRET": "paper-app-secret",
        "KIS_PAPER_ACCOUNT_NO": "12345678",
        "KIS_PAPER_ACCOUNT_PRODUCT_CODE": "01",
        "KIS_LIVE_APP_KEY": "must-not-be-read",
    }


def _decision(*, decision_as_of: datetime = NOW) -> KisPaperCanaryBuyDecision:
    return KisPaperCanaryBuyDecision(
        decision_id="canary-qqq-20260722T143000Z",
        symbol="QQQ",
        exchange="NASD",
        quantity=Decimal("1"),
        limit_price=Decimal("500.25"),
        decision_as_of=decision_as_of,
        valid_until=decision_as_of + timedelta(minutes=5),
    )


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "runtime_projection_path": tmp_path / "runtime" / "canary.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": tmp_path / "repo",
    }


def _submission_count(transport: FakeKisPaperCanaryTransport) -> int:
    return sum(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


def _token_request_count(transport: FakeKisPaperCanaryTransport) -> int:
    return sum(request.url.endswith("/oauth2/tokenP") for request in transport.requests)


def _matching_open_order_payload() -> dict[str, str]:
    return {
        "odno": "ORD-123456789",
        "pdno": "QQQ",
        "ovrs_excg_cd": "NASD",
        "tr_crcy_cd": "USD",
        "sll_buy_dvsn_cd": "02",
        "ft_ord_qty": "1",
        "ft_ccld_qty": "0",
        "nccs_qty": "1",
        "ft_ord_unpr3": "500.25",
    }
