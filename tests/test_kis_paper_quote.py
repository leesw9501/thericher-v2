from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution.kis_paper_canary import (
    KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID,
    KIS_PAPER_US_CANCEL_TR_ID,
    KIS_PAPER_US_CCNCL_TR_ID,
    KisPaperCanaryError,
    validate_kis_paper_canary_request,
)
from thericher_v2.execution.kis_paper_quote import (
    KIS_PAPER_US_SPY_QUOTE_TR_ID,
    KisPaperQuoteError,
    build_kis_paper_spy_quote_request,
    derive_kis_paper_nonmarket_limit,
    parse_kis_paper_spy_quote,
    validate_kis_paper_spy_quote_request,
)
from thericher_v2.execution.kis_paper_session import run_kis_paper_quote_session
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperConfig,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


@dataclass
class FakeKisPaperQuoteTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)
    quote_status_code: int = 200
    quote_payload: dict[str, object] = field(
        default_factory=lambda: {"rt_cd": "0", "output": {"last": "600.12", "zdiv": "2"}}
    )
    order_open: bool = False

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        tr_id = request.headers.get("tr_id", "")
        if request.method == "POST" and request.url.endswith("/oauth2/tokenP"):
            return KisHttpResponse.from_payload({"access_token": "test-access-token"})
        if tr_id == KIS_PAPER_US_SPY_QUOTE_TR_ID:
            return KisHttpResponse.from_payload(
                self.quote_payload,
                status_code=self.quote_status_code,
            )
        if tr_id == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
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
        if tr_id == KIS_PAPER_US_CCNCL_TR_ID:
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID:
            self.order_open = True
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": {"ODNO": "ORD-123456789"}})
        if tr_id == KIS_PAPER_US_CANCEL_TR_ID:
            self.order_open = False
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": {}})
        raise AssertionError(f"unexpected KIS request: {request!r}")


def test_quote_request_is_virtual_only_and_limit_rounds_down() -> None:
    request = build_kis_paper_spy_quote_request(config=_config(), access_token="test-access-token")

    validate_kis_paper_spy_quote_request(request)
    validate_kis_paper_canary_request(request)
    quote = parse_kis_paper_spy_quote(
        {"rt_cd": "0", "output": {"last": "600.12", "zdiv": "2"}}
    )

    assert derive_kis_paper_nonmarket_limit(quote) == Decimal("598.61")
    assert "600.12" not in repr(quote)
    with pytest.raises(KisPaperQuoteError, match="quote_request_not_allowlisted"):
        validate_kis_paper_spy_quote_request(
            replace(request, query={**request.query, "EXCD": "NYS"})
        )
    with pytest.raises(KisPaperCanaryError, match="quote_request_not_allowlisted"):
        validate_kis_paper_canary_request(replace(request, query={**request.query, "EXCD": "NYS"}))


@pytest.mark.parametrize(
    "payload",
    (
        {"rt_cd": "0"},
        {"rt_cd": "0", "output": {"last": "0", "zdiv": "2"}},
        {"rt_cd": "0", "output": {"last": "600.12", "zdiv": "7"}},
        {"rt_cd": "0", "output": {"last": "600.12", "zdiv": "not-a-scale"}},
    ),
)
def test_quote_parser_rejects_incomplete_or_invalid_values(payload: dict[str, object]) -> None:
    with pytest.raises(KisPaperQuoteError, match="quote_response_incomplete"):
        parse_kis_paper_spy_quote(payload)


def test_quote_parser_rejects_a_success_http_response_with_kis_error_code() -> None:
    with pytest.raises(KisPaperQuoteError, match="quote_rejected"):
        parse_kis_paper_spy_quote(
            {"rt_cd": "1", "output": {"last": "600.12", "zdiv": "2"}}
        )


def test_session_outside_regular_window_never_reads_credentials_or_dispatches(
    tmp_path: Path,
) -> None:
    class UnusedEnvironment(dict[str, str]):
        def get(self, key: str, default: str = "") -> str:
            raise AssertionError(f"outside-session runner must not read environment: {key}")

    transport = FakeKisPaperQuoteTransport()
    outcome = run_kis_paper_quote_session(
        environment=UnusedEnvironment(),
        transport=transport,
        now=NOW.replace(hour=1),
        session_id="outside-session-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "not_due"
    assert outcome.reason_code == "outside_regular_session"
    assert transport.requests == []
    assert outcome.evidence_path.exists()


def test_due_session_uses_transient_quote_and_sanitizes_all_public_outputs(tmp_path: Path) -> None:
    raw_quote_text = "600.12"
    derived_limit_text = "598.61"
    transport = FakeKisPaperQuoteTransport()
    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="due-session-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.run_id == "canary-due-session-1"
    assert outcome.canary_phase == "cancelled"
    buy_request = next(
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
    )
    assert buy_request.json_body is not None
    assert buy_request.json_body["OVRS_ORD_UNPR"] == derived_limit_text
    quote_request = next(
        request
        for request in transport.requests
        if request.headers.get("tr_id") == KIS_PAPER_US_SPY_QUOTE_TR_ID
    )
    assert quote_request.query == {"AUTH": "", "EXCD": "NAS", "SYMB": "SPY"}
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    safe_output = str(outcome.safe_payload())
    for forbidden in (raw_quote_text, derived_limit_text, "paper-app-secret", "12345678"):
        assert forbidden not in evidence
        assert forbidden not in safe_output


def test_repeated_due_sessions_create_distinct_intents_without_a_one_shot_latch(
    tmp_path: Path,
) -> None:
    transport = FakeKisPaperQuoteTransport()
    first = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="due-session-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )
    second = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW + timedelta(minutes=15),
        session_id="due-session-2",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert first.run_id != second.run_id
    assert first.status == second.status == "canary_completed"
    assert sum(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    ) == 2


def test_quote_failure_writes_safe_no_submit_evidence(tmp_path: Path) -> None:
    raw_broker_text = "paper-app-secret account 12345678 broker detail"
    transport = FakeKisPaperQuoteTransport(
        quote_status_code=503,
        quote_payload={"msg1": raw_broker_text},
    )
    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="quote-failure-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "quote_unavailable"
    assert outcome.reason_code == "quote_rejected"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )
    evidence = outcome.evidence_path.read_text(encoding="utf-8")
    assert raw_broker_text not in evidence
    assert "paper-app-secret" not in evidence
    assert "12345678" not in evidence


def test_kis_quote_error_code_writes_safe_no_submit_evidence(tmp_path: Path) -> None:
    transport = FakeKisPaperQuoteTransport(
        quote_payload={"rt_cd": "1", "output": {"last": "600.12", "zdiv": "2"}}
    )
    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        now=NOW,
        session_id="quote-result-error-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "quote_unavailable"
    assert outcome.reason_code == "quote_rejected"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


@dataclass
class SteppingClock:
    values: list[datetime]

    def __call__(self) -> datetime:
        if not self.values:
            raise AssertionError("clock ran more often than expected")
        return self.values.pop(0)


def test_session_rechecks_the_regular_window_immediately_before_submit(tmp_path: Path) -> None:
    before_close = datetime(2026, 7, 22, 19, 59, 59, tzinfo=UTC)
    clock = SteppingClock(
        [
            before_close,
            before_close,
            before_close,
            before_close + timedelta(seconds=1),
        ]
    )
    transport = FakeKisPaperQuoteTransport()

    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        clock=clock,
        session_id="session-close-1",
        execute=True,
        cancel_after_submit=True,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.reason_code == "session_closed"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


def test_session_rechecks_limit_validity_immediately_before_submit(tmp_path: Path) -> None:
    clock = SteppingClock([NOW, NOW, NOW, NOW + timedelta(seconds=2)])
    transport = FakeKisPaperQuoteTransport()

    outcome = run_kis_paper_quote_session(
        environment=_paper_environment(),
        transport=transport,
        clock=clock,
        session_id="session-expiry-1",
        execute=True,
        cancel_after_submit=True,
        valid_seconds=1,
        **_paths(tmp_path),
    )

    assert outcome.status == "canary_completed"
    assert outcome.reason_code == "intent_expired"
    assert all(
        request.headers.get("tr_id") != KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )


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


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "state_root": tmp_path / "private" / "canary",
        "runtime_projection_path": tmp_path / "runtime" / "canary.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": tmp_path / "repo",
    }
